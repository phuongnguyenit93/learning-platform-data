# Message selector và các header/property có thể lọc trong Spring JMS

## 1. Vấn đề thực tế và mục tiêu

Trong một Queue hoặc Topic JMS, các hệ thống thường gửi nhiều loại thông điệp nhưng từng consumer chỉ cần xử lý một tập con. Ví dụ:

- Dịch vụ lập hóa đơn chỉ xử lý `eventType='INVOICE'`.
- Worker phục vụ khu vực châu Âu chỉ quan tâm `region='EU'`.
- Tác vụ giá trị lớn cần `amount >= 100` và `ready = TRUE`.
- Một tiến trình trả lời request cần `JMSCorrelationID='order-42'`.

**Message selector** là điều kiện được consumer cung cấp cho Jakarta Messaging provider khi tạo consumer hoặc subscription. Chỉ message có header/property phù hợp mới được giao cho consumer đó. Nó hữu ích khi một destination có nhiều loại message và bạn muốn lọc **trước bước xử lý ứng dụng**, thay vì gọi handler rồi mới dùng `if` để bỏ qua.

Mục tiêu: hiểu đường đi của selector; xác định chính xác header JMS nào dùng được; gắn đúng kiểu property, biểu thức SQL92, NULL và logic ba giá trị; triển khai Spring `JmsTemplate` và `@JmsListener`; phân biệt Queue và Topic; và chạy ví dụ Java 17 trên broker Artemis.

**Quy tắc quan trọng nhất:** selector có thể tham chiếu những **JMS message properties** và **sáu JMS header chuẩn** nhất định; **nó không đọc JSON/XML/binary body**. SQL selector không phải SQL truy vấn database hoàn chỉnh.

## 2. Selector được đánh giá ở đâu?

~~~text
Producer gửi JMS Message
   ├── Header: JMSCorrelationID, JMSType, JMSPriority, ...
   ├── Properties: eventType, region, amount, ready, ...
   └── Body: JSON / Text / Bytes / Object ...
          |
          v
    JMS Queue / Topic
          |
          v
  Provider đánh giá selector
    ├── TRUE                -> message có thể giao cho consumer
    └── FALSE hoặc UNKNOWN -> không giao cho consumer đó
~~~

Một consumer có selector:

~~~sql
eventType = 'INVOICE' AND region = 'EU'
~~~

sẽ nhận message có **JMS properties** `eventType=INVOICE` và `region=EU`. Nếu body là `{"eventType":"INVOICE","region":"EU"}` nhưng JMS properties không chứa những tên này, selector **không match**.

Selector giúp provider giảm truyền dữ liệu không cần thiết, nhưng **không** xác nhận schema hoặc quyền truy cập. Producer có thể gắn property sai, hoặc dùng loại dữ liệu khác với hợp đồng. Consumer vẫn phải kiểm tra body, authorization, idempotency, business rules, transaction và retry.

## 3. Header, property và body có vai trò khác nhau

~~~text
JMS Message
├── Headers do JMS định nghĩa
│   ├── JMSMessageID
│   ├── JMSCorrelationID
│   ├── JMSPriority
│   ├── JMSDeliveryMode
│   ├── JMSTimestamp
│   ├── JMSType
│   ├── JMSExpiration, JMSReplyTo, JMSDeliveryTime...
│   └── JMSDestination, JMSRedelivered...
├── Properties (được gắn trước khi send)
│   ├── eventType = "INVOICE"    [String]
│   ├── region = "EU"            [String]
│   ├── amount = 130             [int]
│   ├── ready = true             [boolean]
│   └── JMSXGroupID = "billing"  [JMS-defined]
└── Body
    └── {"orderId":"O-21", "items":[...]}
~~~

Trong Spring JMS, dùng `MessagePostProcessor` để bổ sung properties sau khi converter tạo `Message`:

~~~java
// Mảnh code trong service đã inject JmsTemplate.
jmsTemplate.convertAndSend("orders.events", jsonPayload, message -> {
    message.setStringProperty("eventType", "INVOICE");
    message.setStringProperty("region", "EU");
    message.setIntProperty("amount", 130);
    message.setBooleanProperty("ready", true);
    return message;
});
~~~

Ở đây `jsonPayload` đã có trước trong service. Đối với selector `amount >= 100`, property `amount` được gửi dưới kiểu **int**, không phải String "130". Message body và JMS property có thể trùng ý nghĩa, nhưng broker không tự trích field JSON ra thành property.

## 4. Chính xác sáu JMS header được lọc bằng selector chuẩn

Theo Jakarta Messaging 3.1, tham chiếu **header chuẩn** trong selector giới hạn ở:

| Header | Kiểu trong selector | Ví dụ | Điểm cần hiểu |
|---|---|---|---|
| `JMSDeliveryMode` | String `'PERSISTENT'` / `'NON_PERSISTENT'` | `JMSDeliveryMode = 'PERSISTENT'` | Dù API Java dùng int constants, selector dùng chuỗi. |
| `JMSPriority` | Số 0–9 | `JMSPriority >= 7` | Priority broker có thể chịu policy, không bảo đảm thứ tự xử lý tuyệt đối. |
| `JMSMessageID` | String do provider tạo | `JMSMessageID = 'ID:...'` | Không tự đặt trước send; cần có ID thật nếu lọc theo message ID. |
| `JMSTimestamp` | Số nguyên long epoch millis | `JMSTimestamp > 1700000000000` | Có thể được tắt và bằng 0; không đồng nhất với ngày nghiệp vụ. |
| `JMSCorrelationID` | String hoặc NULL | `JMSCorrelationID = 'order-42'` | Thường do producer đặt, phục vụ liên kết request/reply. |
| `JMSType` | String hoặc NULL | `JMSType = 'invoice.v1'` | Header do producer gắn, không phải tự động tên Java class. |

**Những header không thể dùng trực tiếp trong JMS selector chuẩn:** `JMSDestination`, `JMSReplyTo`, `JMSExpiration`, `JMSDeliveryTime` và `JMSRedelivered`. Một số có getter trên `jakarta.jms.Message` nhưng **getter tồn tại không đồng nghĩa selector được tham chiếu**.

Ví dụ không portable:

~~~sql
JMSExpiration > 1700000000000
JMSDeliveryTime < 1700000100000
JMSRedelivered = TRUE
~~~

Không suy luận từ các tên header trong tài liệu ứng dụng mà viết selector tùy tiện. Nếu vendor có extension riêng, phải đánh dấu phụ thuộc vendor và thử với phiên bản broker thực.

### 4.1. Điểm dễ nhầm: JMSDeliveryMode

~~~java
producer.send(message, jakarta.jms.DeliveryMode.PERSISTENT, 4, 60_000L);
~~~

Đây là mảnh code JMS API với `producer`, `message` có sẵn. Giá trị `DeliveryMode.PERSISTENT` là hằng số số nguyên khi gọi API, nhưng selector dùng:

~~~sql
JMSDeliveryMode = 'PERSISTENT'
~~~

không phải so sánh với `2`. `JMSPriority` thì ngược lại: sử dụng so sánh số như `JMSPriority > 4`.

### 4.2. Correlation ID và JMSType

~~~java
message.setJMSCorrelationID("request-729");
message.setJMSType("invoice.v1");
~~~

Cả hai header này có thể được producer đặt trước send và dùng trong selector. Nếu một hệ thống dùng cả `JMSType`, `eventType` và type id riêng cho JSON converter, hãy ghi rõ hợp đồng từng field. Chúng không tự đồng bộ với nhau.

## 5. Các message properties có thể lọc

Theo Jakarta Messaging, property value có thể là `boolean`, `byte`, `short`, `int`, `long`, `float`, `double` hoặc `String`.

| Property gửi bởi producer | Điều kiện hợp lệ |
|---|---|
| `setStringProperty("region", "EU")` | `region = 'EU'` |
| `setStringProperty("eventType", "INVOICE")` | `eventType IN ('INVOICE', 'REFUND')` |
| `setIntProperty("amount", 130)` | `amount >= 100` |
| `setLongProperty("createdAt", 1730000000000L)` | `createdAt >= 1720000000000` |
| `setBooleanProperty("ready", true)` | `ready = TRUE` |
| `setDoubleProperty("score", 0.8)` | `score > 0.5` |

JMS message property name phải là **selector identifier** hợp lệ theo quy tắc Java identifier; nên dùng tên CamelCase/lowerCamelCase dễ đọc như `eventType`, `region`, `orderCount`. Không dùng tên có dấu cách hoặc gạch ngang nếu muốn tham chiếu bằng selector chuẩn. Tên property phân biệt chữ hoa: `eventType` khác `EventType`.

Ba loại property theo tên:
1. **Application-defined:** không bắt đầu bằng `JMS`, chẳng hạn `eventType`, `tenantRegion`.
2. **JMSX-defined:** bắt đầu `JMSX`, ví dụ `JMSXGroupID`, `JMSXDeliveryCount`.
3. **Provider-specific:** có quy tắc `JMS_<vendor>` hoặc tên riêng do provider công bố.

Ứng dụng nên thống nhất **tên + kiểu + ý nghĩa** của mỗi property như một phần message contract. Nếu đổi `amount` từ `int` sang `String` hoặc `eventType` thành `EventType`, selector cũ có thể ngừng match dù Java consumer không thay đổi.

### JMSXGroupID và JMSXDeliveryCount khác nhau

- `JMSXGroupID` là property dùng nhận diện message group và có thể được client gắn trước send. Việc grouping/affinity theo consumer còn phụ thuộc broker, không phải hệ quả tự động của selector.
- `JMSXDeliveryCount` là property **bắt buộc** do provider đặt khi message được nhận: lần đầu thường bằng 1, redelivery từ 2. Dù thuộc họ JMSX properties, chuẩn nói **hiệu ứng dùng selector trên property do provider gắn khi receive là không xác định**.

Do vậy, **đừng** chọn message bằng:

~~~sql
JMSXDeliveryCount >= 3
~~~

để làm retry/DLQ policy portable. Có thể đọc count trong consumer để log/chẩn đoán; việc giới hạn số lần gửi lại nên cấu hình ở provider/broker hoặc tầng retry có kiểm soát.

## 6. Cú pháp: tập con của SQL92

Một JMS selector là một chuỗi biểu thức điều kiện, **không** phải câu truy vấn có `SELECT`, `FROM`, `WHERE`, join hoặc truy vấn JSON.

### 6.1. Các toán tử thông dụng

~~~sql
eventType = 'INVOICE'
eventType <> 'REFUND'
amount >= 100
ready = TRUE
eventType = 'INVOICE' AND region = 'EU'
region = 'EU' OR region = 'APAC'
NOT (ready = TRUE)
(eventType = 'INVOICE' OR eventType = 'REFUND') AND amount > 0
~~~

Các phép so sánh `=`, `<>`, `>`, `>=`, `<`, `<=`, toán tử logic `AND`, `OR`, `NOT` và dấu ngoặc đều có ý nghĩa theo selector. Thứ tự ưu tiên quyết định kết quả; khi có hai nhóm điều kiện nghiệp vụ, dùng ngoặc để tránh hiểu nhầm. Từ khóa toán tử không phân biệt chữ hoa/thường, nhưng identifier phân biệt chữ hoa/thường.

**Lưu ý dấu nháy:** String literal dùng **nháy đơn**, ví dụ `'EU'`; không dùng `"EU"`. Chuỗi `'EU'` khác `'eu'`; muốn chuẩn hóa, hãy chuẩn hóa property khi gửi.

### 6.2. IN, BETWEEN và LIKE

~~~sql
eventType IN ('INVOICE', 'REFUND', 'CANCEL')
amount BETWEEN 100 AND 500
orderCode LIKE 'INV-%'
orderCode LIKE 'INV_'
orderCode LIKE 'AB#_%' ESCAPE '#'
~~~

- `IN` hoạt động với tập literal String.
- `BETWEEN` bao gồm cả đầu mút thấp và cao; `amount BETWEEN 100 AND 500` phù hợp giá trị số từ 100 đến 500.
- `LIKE` dành cho String, `%` biểu thị chuỗi ký tự bất kỳ (có thể rỗng), `_` biểu thị đúng một ký tự.
- `ESCAPE '#'` chỉ định `#` để escape wildcard. Pattern `'AB#_%'` khớp chuỗi bắt đầu bằng literal `AB_`, tiếp sau là bất kỳ chuỗi ký tự nào.

Nếu cần match chuỗi có nháy đơn, lặp dấu nháy trong literal:

~~~sql
customerName = 'O''Brien'
~~~

Không nối dữ liệu người dùng trực tiếp vào selector mà không kiểm soát. JMS selector không có bind parameter JDBC `?`. Nên dùng selector cố định, allowlist enum/giá trị hoặc một bộ dựng biểu thức an toàn có escape chuẩn.

### 6.3. Kiểu property được giữ nguyên, không tự ép kiểu

Sai khác thường gặp:

~~~java
message.setStringProperty("amount", "130");
~~~

và selector:

~~~sql
amount > 100
~~~

Property `amount` có kiểu String, còn phép số yêu cầu numeric. **Quy tắc ép kiểu của các phương thức `getIntProperty()` không áp dụng cho biểu thức selector.** Hãy gửi bằng `setIntProperty("amount", 130)` nếu hợp đồng đòi so sánh số.

Tương tự, `setStringProperty("ready", "true")` không giống `setBooleanProperty("ready", true)`. Muốn `ready = TRUE` hoạt động, phải gửi property kiểu boolean. Tất cả producer vào chung Queue/Topic phải đồng ý về kiểu dữ liệu.

### 6.4. Lỗi cú pháp được báo khi thiết lập consumer

Provider phải xác minh selector syntax khi ứng dụng cung cấp biểu thức. Với selector như:

~~~sql
amount >=
~~~

JMS API báo `InvalidSelectorException`. Khi dùng Spring, ngoại lệ checked JMS có thể được Spring chuyển sang `JmsException` unchecked; lỗi có thể xảy ra lúc listener container khởi động hoặc lúc tạo lại consumer. Vì thế các selector cố định nên được integration test trước khi deploy.

## 7. NULL và logic ba giá trị

Nếu một property **không tồn tại** trong message, selector xem nó là NULL. Phép so sánh với NULL thường cho kết quả **UNKNOWN**. Chỉ khi biểu thức TRUE message mới được chọn.

| Biểu thức | Khi property region thiếu | Kết quả |
|---|---|---|
| `region = 'EU'` | Không có region | UNKNOWN |
| `region <> 'EU'` | Không có region | UNKNOWN |
| `NOT (region = 'EU')` | Không có region | UNKNOWN |
| `region IS NULL` | Không có region | TRUE |
| `region IS NOT NULL` | Không có region | FALSE |
| `region = 'EU' OR region IS NULL` | Không có region | TRUE |

Một hệ quả rất quan trọng: `NOT UNKNOWN` vẫn là UNKNOWN; `TRUE AND UNKNOWN` là UNKNOWN; `FALSE AND UNKNOWN` là FALSE; `TRUE OR UNKNOWN` là TRUE.

Nếu định nhận message “không thuộc EU” **bao gồm cả message không có region**, cần viết rõ:

~~~sql
region <> 'EU' OR region IS NULL
~~~

Nếu chỉ muốn message có region rõ ràng và khác EU:

~~~sql
region IS NOT NULL AND region <> 'EU'
~~~

Đừng giả định property thiếu tự biến thành Java default như `0`, `false` hoặc chuỗi rỗng. Ba trạng thái TRUE/FALSE/UNKNOWN giúp tránh điều kiện vô tình chọn/loại sai dữ liệu.

## 8. Nên lọc theo header hay application property?

| Nhu cầu | Cách phù hợp | Vì sao |
|---|---|---|
| Loại sự kiện | `eventType`, `schemaVersion` | Contract nghiệp vụ rõ ràng, không phụ thuộc Java class. |
| Khu vực, phân loại tác vụ | `region`, `category` | Cho producer/consumer thống nhất enum. |
| Mức độ ưu tiên nghiệp vụ | `businessPriority` | Không phụ thuộc broker QoS; chỉ so với JMSPriority nếu thực sự muốn QoS. |
| Một request/reply cụ thể | `JMSCorrelationID` | Header tiêu chuẩn để liên kết luồng. |
| Theo delivery mode | `JMSDeliveryMode` | Có hai chuỗi đặc biệt PERSISTENT/NON_PERSISTENT. |
| Phân loại quá nhiều lần giao lại | Đọc `JMSXDeliveryCount` trong handler | Không dùng selector trên receive-time property làm policy portable. |
| Field nằm sâu trong JSON | Đưa ra JMS property nếu thật sự cần lọc, hoặc chia destination | Broker không parse JSON body cho selector. |

Sao chép một field từ body sang JMS property chỉ khi cần: producer phải giữ chúng **nhất quán**. Ví dụ body có `region=US` nhưng property là `region=EU` sẽ khiến consumer EU nhận message không thuộc luồng mong đợi.

## 9. Spring JmsTemplate: receiveSelected và receiveSelectedAndConvert

Nhận đồng bộ một message có selector:

~~~java
// Mảnh code bên trong service đã inject JmsTemplate.
jakarta.jms.Message message = jmsTemplate.receiveSelected(
        "orders.events", "eventType = 'INVOICE' AND amount >= 100");
~~~

Nếu cần nhận rồi chuyển body qua MessageConverter của template:

~~~java
Object object = jmsTemplate.receiveSelectedAndConvert(
        "orders.events", "region = 'APAC'");
~~~

**Phân biệt:**
- `receiveSelected` trả `jakarta.jms.Message`, truy cập được `JMSCorrelationID`, `getIntProperty`, `getStringProperty` và body.
- `receiveSelectedAndConvert` trả payload Java; không giữ raw Message trong kết quả, nên nếu cần header/property thì chọn API/adapter phù hợp.
- `receiveTimeout` là cấu hình trên `JmsTemplate`; khi hết thời gian mà không có message match, trả `null`. Tránh thay `setReceiveTimeout` trên singleton theo từng request.
- Với tên destination String, template cần được cấu hình đúng Queue/Topic mode (`pubSubDomain`); một tên không tự chứng minh được loại destination.
- Đừng dùng receive đồng bộ trong request web nếu có thể treo lâu mà chưa có timeout/capacity plan.

Với ứng dụng nhận message liên tục, `@JmsListener` và listener container thường phù hợp hơn tự viết vòng lặp `receiveSelected` vô hạn.

## 10. @JmsListener(selector=...) cho consumer bất đồng bộ

Spring hỗ trợ khai báo selector ngay ở annotation:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class EuropeanInvoiceConsumer {
    @JmsListener(
            destination = "orders.events",
            selector = "eventType = 'INVOICE' AND region = 'EU'")
    public void process(String payload) {
        System.out.println("EU invoice: " + payload);
    }
}
~~~

Đây là một component consumer riêng, cần JMS infrastructure/`@EnableJms` hoặc cấu hình Spring Boot phù hợp và broker có destination `orders.events`. **Không bật component này đồng thời với demo nhận đồng bộ bên dưới** nếu muốn output deterministic: các consumer trên cùng Queue có thể cạnh tranh lấy message.

Có thể cấu hình selector bằng property môi trường:

~~~yaml
app:
  messaging:
    orders-queue: orders.events
    eu-selector: "eventType = 'INVOICE' AND region = 'EU'"
~~~

Trong class `@Component`:

~~~java
@JmsListener(
    destination = "${app.messaging.orders-queue}",
    selector = "${app.messaging.eu-selector}")
public void processEuropeanInvoice(String payload) {
    System.out.println(payload);
}
~~~

Spring xử lý placeholder cho các annotation attributes khi đăng ký listener endpoint. Việc thay đổi file cấu hình sau khi listener đang chạy **không** tự bảo đảm mọi consumer/subscription được tái tạo với selector mới; phải quản lý lifecycle và migration theo provider.

Với production:
- Thiết lập `DefaultJmsListenerContainerFactory`/transaction, concurrency, destination resolver và converter đúng contract.
- `selector` không quyết định transaction, ACK, retry hoặc DLQ.
- Đừng tin selector như phân quyền; message properties có thể do producer khác đặt sai hoặc cố ý giả mạo.
- Với Topic, selector áp dụng cho subscription chứ không phải mọi subscriber dùng chung một cursor Queue.

## 11. Demo Spring Boot và Artemis embedded dùng selector thật

Ví dụ chạy với Java 17, Spring Boot 3.5.16 (nhánh Spring Framework 6) và Artemis embedded. Mục tiêu: gửi ba message vào Queue, dùng ba selector khác nhau để nhận. Không có listener cạnh tranh và mỗi selector chỉ match một message, nên output không phụ thuộc thứ tự broker ưu tiên phân phối.

**Cấu trúc project:**

~~~text
jms-selector-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/SelectorLabApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-selector-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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

    // Chỉ cần để chạy Artemis broker nhúng trong lab.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Spring Boot 3.5.16 là bản cuối có OSS support của dòng 3.5.x (tháng 6/2026). Đây là mốc cố định cho bài lab; dự án production nên chọn nhánh Boot/JDK được hỗ trợ theo vòng đời ứng dụng và BOM tương ứng.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.selector
      persistent: false
~~~

`src/main/java/example/jms/SelectorLabApplication.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorLabApplication {
    private static final String QUEUE = "demo.selector";

    public static void main(String[] args) {
        SpringApplication.run(SelectorLabApplication.class, args);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Bean
    ApplicationRunner runCases(JmsTemplate template) {
        return args -> {
            publish(template, "invoice-eu",
                    "INVOICE", "EU", 130, true, "cid-eu");
            publish(template, "invoice-apac",
                    "INVOICE", "APAC", 85, false, "cid-apac");
            publish(template, "refund-apac",
                    "REFUND", "APAC", 65, true, "cid-refund");

            // Chọn message thứ nhất theo loại, số tiền và boolean.
            printMatch(template,
                    "eventType = 'INVOICE' AND amount >= 100 "
                    + "AND ready = TRUE",
                    "invoice-eu");

            // Lần này message APAC invoice vẫn còn trong Queue.
            printMatch(template,
                    "region = 'APAC' AND amount BETWEEN 80 AND 90",
                    "invoice-apac");

            // Kết hợp header chuẩn và app property.
            printMatch(template,
                    "JMSCorrelationID = 'cid-refund' "
                    + "AND eventType IN ('REFUND', 'REVERSAL')",
                    "refund-apac");

            Message remaining = template.receiveSelected(
                    QUEUE, "eventType = 'INVOICE'");
            if (remaining != null) {
                throw new IllegalStateException(
                        "Unexpected extra invoice message");
            }
            System.out.println("REMAINING=none");
        };
    }

    private static void publish(JmsTemplate template, String body,
            String eventType, String region, int amount,
            boolean ready, String correlationId) {

        template.convertAndSend(QUEUE, body, message -> {
            message.setStringProperty("eventType", eventType);
            message.setStringProperty("region", region);
            message.setIntProperty("amount", amount);
            message.setBooleanProperty("ready", ready);
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }

    private static void printMatch(JmsTemplate template,
            String selector, String expected) throws JMSException {

        Message message = template.receiveSelected(QUEUE, selector);
        if (!(message instanceof TextMessage text)) {
            throw new IllegalStateException(
                    "No TextMessage for selector: " + selector);
        }

        String actual = text.getText();
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "Expected " + expected + " but got " + actual);
        }

        System.out.println("MATCH=" + actual
                + "|eventType=" + message.getStringProperty("eventType")
                + "|amount=" + message.getIntProperty("amount"));
    }
}
~~~

**Giải thích code:**
1. `convertAndSend` tạo `TextMessage` từ payload String bằng converter mặc định.
2. `MessagePostProcessor` gắn application properties đúng kiểu; `JMSCorrelationID` là header chuẩn.
3. Consumer thứ nhất chọn invoice EU có amount=130 và ready=true. Consumer thứ hai chọn invoice APAC với amount=85. Consumer thứ ba lọc theo header `JMSCorrelationID` và tập `eventType`.
4. Các lần nhận không match message khác, nhưng message khác vẫn còn Queue để lần nhận tiếp theo chọn; không phải được drop.
5. `ApplicationRunner.run` khai báo có thể throw Exception, nên việc gọi `getText()`/`getIntProperty()` có checked `JMSException` trong helper vẫn biên dịch hợp lệ.
6. Một Runner chạy tuần tự, không có listener khác, không lệ thuộc thứ tự phân phối cho các message không đồng nhất.

**Chạy:** tại thư mục dự án, dùng JDK 17+ và Gradle phiên bản tương thích. Nếu dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có Wrapper, có thể dùng Gradle cài sẵn:

~~~bash
gradle bootRun
~~~

Sau các dòng log của Spring Boot và Artemis, stdout **do chương trình tự in** khi mọi bước thành công:

~~~text
MATCH=invoice-eu|eventType=INVOICE|amount=130
MATCH=invoice-apac|eventType=INVOICE|amount=85
MATCH=refund-apac|eventType=REFUND|amount=65
REMAINING=none
~~~

Nếu selector sai hoặc nhận không có message trong 2 giây, code sẽ báo lỗi rõ ràng. `persistent: false` là lựa chọn lab, không chứng minh durability/HA/TLS. Không copy các giả định về ordering và consumer đơn sang ứng dụng nhiều replica.

### Những biến thể nên thử

- Đổi `setIntProperty("amount", amount)` thành `setStringProperty("amount", Integer.toString(amount))`: selector numeric ngừng khớp.
- Đổi selector thành `eventType = 'invoice'`: literal String khác `'INVOICE'`, không khớp.
- Thử không gắn `region` và selector `region IS NULL` hoặc `region = 'EU' OR region IS NULL`.
- Gắn `message.setJMSType("invoice.v1")` rồi lọc `JMSType = 'invoice.v1'`.
- Thử cú pháp lỗi `amount >=`: consumer phải báo `InvalidSelectorException` thay vì chọn ngẫu nhiên.
- Đừng chạy component `EuropeanInvoiceConsumer` ở mục 10 trên cùng Queue trong demo này; nó có thể cạnh tranh và làm output thay đổi.

## 12. API Jakarta Messaging cấp thấp

JMS cổ điển cho phép tạo consumer với selector:

~~~java
// Mảnh code trong callback có jakarta.jms.Session và Queue thật.
jakarta.jms.MessageConsumer consumer =
        session.createConsumer(queue,
                "region = 'EU' AND eventType = 'INVOICE'");
~~~

Với API `JMSContext`:

~~~java
// Mảnh code khi đã có jakarta.jms.JMSContext và Queue thật.
jakarta.jms.JMSConsumer consumer =
        context.createConsumer(queue, "region = 'EU'");
~~~

Khi dùng classic API, cần `Connection.start()` trước khi nhận; `JmsTemplate` và Spring listener container thường quản lý connection/session giúp bạn. Null hoặc chuỗi selector rỗng có nghĩa **không lọc**.

Không tạo/destroy consumer mới cho từng request user một cách tùy tiện khi cần throughput lớn; số lượng và cache consumer, chi phí subscription, query evaluation và quyền truy cập đều ảnh hưởng vận hành. Dùng selector ổn định cho listener lâu dài, hoặc chọn mô hình định tuyến Queue/Topic rõ ràng khi workload có nhiều phân vùng.

## 13. Khác biệt quan trọng giữa Queue và Topic

### Queue: message không match không bị tự drop

Một JMS Queue có thể có nhiều consumer cạnh tranh. Với selector:
- Consumer EU chỉ nhận message có `region='EU'`.
- Consumer APAC chỉ nhận message có `region='APAC'`.
- Message có `region='US'` **không** được giao cho hai consumer này; có thể tiếp tục nằm trong Queue cho consumer khác trong tương lai, trừ khi expire/admin policy tác động.
- Một consumer **không selector** trên cùng Queue có thể nhận message mà nhóm EU/APAC mong chờ, vì nó cũng đủ điều kiện. Selector không “đặt quyền sở hữu” toàn bộ Queue.

~~~text
Queue orders.jobs
├── Consumer EU:    region = 'EU'
├── Consumer APAC:  region = 'APAC'
└── Consumer ANY:   không selector

Message EU   -> EU hoặc ANY (tùy broker phân phối)
Message APAC -> APAC hoặc ANY
Message US   -> ANY nếu có, nếu không có thể còn trong Queue
~~~

JMS không bắt buộc cách chia tải cụ thể giữa nhiều consumer hợp lệ. Khi cần strict isolation, SLA/backlog/ACL riêng hoặc data residency, cân nhắc Queue/broker namespace riêng thay vì chỉ lọc theo property.

### Topic: selector thuộc subscription

Với Topic, mỗi subscription nhận bản sao message đáp ứng selector tại **thời điểm publish**; những subscription khác có selector khớp có thể đồng thời nhận bản sao của cùng message.

~~~text
Topic sales.order.events
  ├── subscription billing  (eventType = 'PAID')
  └── subscription analytics (region IN ('EU', 'APAC'))
~~~

Nếu hai subscription cùng match, cả hai có thể có bản sao. Nếu subscription được tạo **sau khi** message đã publish, selector mới không biến nó thành truy vấn lịch sử. Durable subscription có identity và backlog riêng; thay selector hoặc tên subscription không đơn thuần là sửa một dòng String — phải có kế hoạch migration và kiểm tra policy provider. Shared subscription cho nhiều replica lại có semantics chia tải trong cùng nhóm, không đồng nghĩa nhiều subscription độc lập.

## 14. Selector không thay thế bảo mật, retry và transaction

**Bảo mật:** property `tenantId` hay `region` là giá trị producer gửi, nên không thể xem selector là rào chắn phân quyền. Dùng broker authentication/ACL, namespace hoặc Queue riêng, validate tenant ownership và chống giả mạo dữ liệu đầu vào.

**Retry:** selector không xử lý redelivery, backoff, giới hạn số lần thử hoặc DLQ. Với message bị rollback, transaction/ACK và broker redelivery policy quyết định. `JMSXDeliveryCount` nên được đọc sau nhận; không dùng selector vào property set-on-receive làm chính sách portable.

**Message bị kẹt:** nếu toàn bộ consumer có selector quá hẹp, message có thể tồn lâu trên Queue. Broker không tự xem “không match selector” là lỗi phải đẩy vào DLQ. Cần cảnh báo Queue depth, message age, expiry và selector/version đang hoạt động. Nếu producer đổi property từ `eventType` sang `EventType`, các message mới có thể trở thành unmatched mà không có exception rõ ràng.

**Performance:** message selector không phải query SQL với indexing đồng nhất mọi vendor. Tác động hiệu năng phụ thuộc số consumer, độ phức tạp predicate, message rate, provider implementation và protocol. Benchmark trên broker thật; khi cần hàng nghìn nhóm lọc hoặc phân phối độc lập, phân tuyến thành nhiều Queue/Topic có thể dễ kiểm soát hơn.

## 15. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| JSON body có `region=EU` mà listener không nhận | `region` chưa được gắn JMS property. | Gắn `setStringProperty("region","EU")` trước send. |
| `amount >= 100` không chọn `"130"` | Property có kiểu String, không phải int/long. | Sửa producer dùng numeric property. |
| `eventType='invoice'` không match | Dữ liệu thực là `INVOICE`; literal String có phân biệt hoa/thường. | Chuẩn hóa enum. |
| `EventType` không khớp `eventType` | Identifier case-sensitive. | Dùng một tên thống nhất trong contract. |
| `NOT (region = 'EU')` không nhận message thiếu region | UNKNOWN không trở thành TRUE khi NOT. | Dùng `OR region IS NULL` nếu muốn bao gồm thiếu region. |
| `JMSRedelivered=TRUE` hoặc `JMSExpiration>...` không portable | Không thuộc sáu header selector chuẩn. | Tách logic phù hợp hoặc dùng provider-specific feature có tài liệu. |
| `JMSXDeliveryCount >= 3` không đáng tin | Property được đặt khi receive, tác dụng selector không xác định. | Cấu hình retry/max attempts/DLQ ở broker. |
| Lỗi startup của listener | Selector sai cú pháp, name/quote ngoặc sai. | Test `InvalidSelectorException` và chuỗi sau placeholder resolution. |
| Queue backlog dù consumer online | Không message nào match, typo/kiểu property sai. | Inspect actual JMS properties, selectors và broker metrics. |
| Nhóm EU nhận message ngoài EU | Có consumer khác không selector hoặc dữ liệu property bị giả mạo. | Kiểm tra tất cả consumer trên Queue; dùng ACL/partition nếu cần. |
| Topic subscriber mới không nhận lịch sử | Subscription chưa tồn tại tại thời điểm publish. | Provision durable subscription trước khi publish và quản lý migration. |

Đừng chỉ nhìn tên method Java hay payload trong log. Hãy inspect raw JMS headers/properties của message trên broker và so với selector đang được container sử dụng.

## 16. Bộ kiểm thử cần có

Một hệ thống dùng selector nên kiểm thử:

1. Selector syntax được provider chấp nhận; selector sai phải báo rõ khi tạo consumer.
2. Property `String`/`int`/`boolean` được gửi đúng kiểu; thử sai kiểu để hiểu failure.
3. Property thiếu, `IS NULL`/`IS NOT NULL`, `NOT` và logic UNKNOWN.
4. Các header được phép (như `JMSCorrelationID`, `JMSType`, `JMSPriority`) được set/đọc chính xác.
5. Queue hai consumer có selector khác nhau; có/không có consumer unfiltered; backlog khi không match.
6. Topic hai subscription khớp; durable/shared và trường hợp subscription tạo sau publish.
7. Transaction rollback/ACK, retry/DLQ và message expiry không bị nhầm với selector.
8. Security: message giả mạo property tenant/region không vượt ACL.
9. Observability: metrics queue depth, eligible/unmatched, message age, DLQ, consumer count và selector version.
10. Throughput với số lượng selector/consumer thực tế; không suy ra performance từ demo embedded.

Nên lưu **selector contract** trong source control: destination, owner, loại Queue/Topic, thuộc tính bắt buộc/kiểu, selector expression, lifecycle subscription và kế hoạch thay đổi khi producer đổi schema. Selector không khớp có thể im lặng rất lâu nếu không có giám sát.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Body JSON có `{"region":"EU"}` nhưng message không có property region. `region = 'EU'` có match không?  
**Đáp án:** Không. Property thiếu tạo UNKNOWN; selector không đọc JSON body.

**Câu 2.** Producer dùng `setStringProperty("amount","130")`, consumer dùng `amount >= 100`. Vì sao sai?  
**Đáp án:** Property String không tự được chuyển sang numeric trong selector; phải dùng `setIntProperty`/`setLongProperty` đúng contract.

**Câu 3.** `JMSPriority`, `JMSReplyTo`, `JMSDeliveryTime`, `JMSCorrelationID` — header nào được phép trong selector chuẩn?  
**Đáp án:** `JMSPriority` và `JMSCorrelationID`. Hai header còn lại không thuộc tập sáu tên được phép.

**Câu 4.** Nếu region thiếu, `NOT (region = 'EU')` có match không?  
**Đáp án:** Không. NOT UNKNOWN vẫn UNKNOWN; dùng `OR region IS NULL` nếu business rule muốn bao gồm missing.

**Câu 5.** Với Queue có selector EU và APAC, message US có tự mất không?  
**Đáp án:** Không chỉ vì selector. Nó có thể ở lại Queue cho đến khi có consumer khác hoặc expiry/admin policy. Consumer unfiltered có thể nhận bất kỳ message đủ điều kiện.

**Câu 6.** Có nên dùng `JMSXDeliveryCount >= 3` làm điều kiện listener không?  
**Đáp án:** Không. Đó là property được provider đặt lúc receive; chuẩn không định nghĩa kết quả dùng nó làm selector. Cấu hình redelivery/DLQ và quan sát delivery count trong handler.

**Câu 7.** Trong Spring, cách phổ biến nhận bất đồng bộ theo selector là gì?  
**Đáp án:** `@JmsListener(destination=..., selector=...)` hoặc listener container đã cấu hình. `JmsTemplate.receiveSelected` là lựa chọn đồng bộ có timeout.

**Câu 8.** Một subscription Topic được tạo sau message publish có nhận lại lịch sử theo selector mới không?  
**Đáp án:** Không có bảo đảm. Selector được áp dụng vào subscription tồn tại tại lúc message được publish; nó không tạo lịch sử hồi tố.

## 18. Checklist cuối và tài liệu chính thức

- [ ] Không dùng JSON body như nguồn dữ liệu trực tiếp cho selector; đã gắn property cần lọc.
- [ ] Đã chọn đúng sáu header selector chuẩn hoặc application/JMSX properties phù hợp.
- [ ] Tên identifier, kiểu String/số/boolean, NULL, quote/escape và cú pháp SQL92 đều được test.
- [ ] Không dùng `JMSXDeliveryCount` làm selector để quyết định retry/DLQ.
- [ ] Đã phân biệt Queue consumer cạnh tranh và Topic subscription có bản sao.
- [ ] Có transaction/ACK và redelivery policy, monitoring message không match.
- [ ] Cấu hình selector lưu trong version control, được đánh giá trên provider/broker thật.
- [ ] Broker ACL và tenant isolation không dựa vào property do producer tự đặt.

**Tài liệu tham khảo:**
- [Jakarta Messaging 3.1 specification — mục 3.8 Message selection, 3.5 Message properties, 4 Queue/Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Jakarta Messaging API — Message selectors](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message).
- [Spring Framework — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework 6.2.14 JmsTemplate — receiveSelected](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring JMS @JmsListener Javadoc — selector](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/jms/annotation/JmsListener.html).
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/).
