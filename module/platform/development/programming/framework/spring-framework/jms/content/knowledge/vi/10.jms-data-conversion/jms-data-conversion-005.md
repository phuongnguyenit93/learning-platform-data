# Thông tin kiểu, ánh xạ type ID và danh sách kiểu cho phép trong Spring JMS

> **Mục tiêu:** Hiểu cách JMS message thể hiện kiểu dữ liệu, thiết lập ánh xạ type ID tới DTO khi chuyển JSON, thực thi **danh sách kiểu được phép (allowlist)** trước khi deserialize, bảo vệ consumer khỏi metadata giả mạo và duy trì hợp đồng liên dịch vụ qua nhiều phiên bản.

**Phạm vi kỹ thuật:** Java 17+, Jakarta Messaging, Spring JMS **6.2.19+** với Jackson 2, ví dụ thực hành Spring Boot 3.5.x có dependency đã vá. Spring Framework 7.x sử dụng các converter thế hệ Jackson 3 tương ứng; cần đối chiếu API riêng. Một bản vá quan trọng cho topic này là **CVE-2026-41855**, công bố ngày 08/06/2026, ảnh hưởng Jackson JMS converters khi xử lý message từ nguồn không tin cậy. Ví dụ minh họa kết hợp **type-ID allowlist chặt** và `setTrustedPackages(...)` trên Spring đã vá.

## 1. Vì sao cần thông tin kiểu?

Một producer có thể gửi chuỗi JSON:

~~~json
{"invoiceId":"INV-0007","totalMinor":5500}
~~~

Nhưng chỉ từ hai field trên, consumer không biết cần tạo đối tượng Java `InvoiceCreated`, `InvoicePaid` hay một kiểu khác. Nếu queue/topic chứa nhiều loại sự kiện, hệ thống phải có một **hợp đồng phân loại dữ liệu** độc lập với tình cờ trùng tên field.

Hợp đồng ví dụ:

~~~text
Destination: billing.events
JMS property: _type = "invoice-created-v1"
JMS body:     {"invoiceId":"INV-0007","totalMinor":5500}

Broker -> JMS TextMessage
           |
           +-- đọc property _type
           +-- kiểm tra alias thuộc ALLOWLIST
           +-- alias -> DTO Java đã đăng ký
           +-- Jackson parse JSON -> DTO
           +-- validation -> business handler
~~~

Ở đây `_type` là **JMS message property do ứng dụng quy ước**, không phải trường bắt buộc của chuẩn JMS. Nó là **dữ liệu chưa tin cậy** cho tới khi được kiểm tra. Bên gửi và bên nhận phải thống nhất tên property, giá trị alias, định dạng body, schema và cách xử lý version không được hỗ trợ.

### Mục tiêu của type ID

- **Dispatch:** chọn một DTO/handler từ một tập hợp loại message đã công bố.
- **Tương thích:** giữ tên wire type ổn định khi refactor package hoặc đổi Java class.
- **Liên ngôn ngữ:** producer ngoài Java hiểu `invoice-created-v1` mà không cần biết `com.example.billing.InvoiceCreatedV1`.
- **Quan sát:** ghi nhận type ID/phiên bản trên metrics, routing, DLQ và tracing.
- **Bảo mật:** chỉ tạo object thuộc tập type đã review; không cho payload chỉ định tùy ý Java class.
- **Versioning:** tách schema v1 và v2 có ý nghĩa khác nhau.

Type ID **không** tự kiểm tra giá trị `totalMinor` hợp lệ, không bảo đảm event đã được giao đúng một lần và không thay cơ chế transaction/ACK.

## 2. Phân biệt các lớp metadata thường gặp

| Thuật ngữ | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `TextMessage` / `BytesMessage` / `ObjectMessage` | JMS body type | Cách dữ liệu được chuyên chở; chưa xác định business DTO |
| `JMSType` | JMS standard header | Nhãn loại message theo hợp đồng của producer và consumer |
| `_type` | JMS property được ứng dụng đặt tên | Property mà `MappingJackson2MessageConverter` đọc để chọn Java type |
| `eventType` | Field trong JSON envelope | Loại sự kiện nghiệp vụ, độc lập framework |
| `schemaVersion` | Field trong JSON envelope hoặc metadata | Phiên bản schema và quy tắc tương thích |
| `@JsonTypeInfo` / `@class` | Cơ chế Jackson polymorphic JSON | Chọn subtype ở tầng JSON; có thể tạo bề mặt tấn công riêng |

**Không tự đồng nhất chúng.** `JMSType="InvoiceCreated"` không khiến converter tự đọc property `_type`, trừ khi bạn tự viết adapter tương ứng. `eventType` nằm trong JSON body không tự được JMS selector đọc. `TextMessage` là một chuỗi; việc biến JSON thành Java DTO là công việc của converter/parser. `ObjectMessage` dùng Java native serialization, hoàn toàn khác JSON `TextMessage` trong bài này.

Tổ chức có thể quy ước `_type=invoice-created-v1` để phục vụ Java converter và `eventType=InvoiceCreated, schemaVersion=1` trong body. Khi tồn tại cả hai, phải **validate tính nhất quán**, tránh thông tin mâu thuẫn giữa metadata và body.

## 3. MessageConverter trong Spring JMS

Spring có interface `org.springframework.jms.support.converter.MessageConverter` với hai chiều cơ bản:

~~~java
Message toMessage(Object object, Session session) throws JMSException;
Object fromMessage(Message message) throws JMSException;
~~~

Đây là chữ ký API minh họa, cần các imports `jakarta.jms.Message` và `Session`. `JmsTemplate.convertAndSend` dùng `toMessage`; `JmsTemplate.receiveAndConvert` dùng `fromMessage`. Listener adapter của `@JmsListener` cũng có cơ chế chuyển payload theo converter/factory được cấu hình.

Có nhiều loại converter:

| Converter / cách làm | Dữ liệu nhận | Cách chọn kiểu |
| --- | --- | --- |
| `SimpleMessageConverter` | `String`, `byte[]`, `Map`, `Serializable`... theo JMS body type | **Không parse JSON thành DTO tùy ý** |
| `MappingJackson2MessageConverter` (Spring 6.x) | JSON `TextMessage` hoặc `BytesMessage` | Sử dụng type ID property và Jackson |
| Parser JSON tường minh + DTO cố định | `String`/`TextMessage` rồi mapper | Class do code consumer chọn, không cần type ID class lookup |
| `ObjectMessage` / Java native serialization | Java object graph | Dựa trên Java serialization và classpath, không dùng thay JSON contract |

Nếu producer gửi `TextMessage` có JSON nhưng consumer đang dùng `SimpleMessageConverter`, `receiveAndConvert` thường trả **`String` JSON**. Không có phép màu tự tạo `InvoiceCreatedV1`.

### Hai hướng chuyển đổi

~~~text
Sender Java DTO
  -> MappingJackson2MessageConverter.toMessage
  -> JMS TextMessage/BytesMessage + _type
  -> Broker
  -> MappingJackson2MessageConverter.fromMessage
  -> Java DTO đã ánh xạ
  -> Business handler
~~~

Muốn `TextMessage`, phải dùng `setTargetType(MessageType.TEXT)`; converter Jackson 2 mặc định có thể tạo `BytesMessage`. Đừng nhầm việc chọn body type với type ID dùng cho Java DTO.

## 4. Type ID property và mapping hai chiều

Các cấu hình quan trọng của Spring Framework 6.2.x:

~~~java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

// Mảnh cấu hình trong một @Bean method, chưa phải chương trình độc lập.
var converter = new MappingJackson2MessageConverter();
converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(Map.of(
        "invoice-created-v1", InvoiceCreatedV1.class,
        "invoice-cancelled-v1", InvoiceCancelledV1.class));
~~~

`setTypeIdPropertyName("_type")` nói cho converter biết **property name phải tìm**. Theo Javadoc, nếu muốn tự khôi phục inbound message thành Java object bằng cơ chế mặc định, cần cấu hình tên property này.

`setTypeIdMappings(...)` nhận map có **key là alias wire type** và **value là Java class**:

~~~text
"invoice-created-v1"   -> InvoiceCreatedV1.class
"invoice-cancelled-v1" -> InvoiceCancelledV1.class
~~~

**Ở phía gửi**, converter thường tra class runtime để lấy alias, đặt alias vào JMS property `_type`. **Ở phía nhận**, converter đọc `_type`, tra alias để xác định Java type trước khi gọi Jackson. Cả hai phía phải có mapping tương thích nếu muốn conversion typed end-to-end.

### Tại sao nên dùng alias thay tên class đầy đủ?

Nếu class `com.shop.billing.InvoiceCreatedV1` được chuyển sang `com.shop.contract.events.InvoiceCreatedV1`, bạn có thể giữ alias `invoice-created-v1` không đổi. Người nhận không cần biết refactor Java. Ngược lại, truyền raw class name làm mọi rename/package/module đổi thành một thay đổi wire contract.

### Chú ý lựa chọn class theo map

Map chỉ chọn kiểu đích; các trường JSON vẫn cần:
- Kiểm tra required fields và độ hợp lệ của dữ liệu.
- Quy tắc enum, timestamp, số tiền, encoding.
- Giới hạn kích thước, nesting depth và resource.
- Cơ chế hỗ trợ/không hỗ trợ schema versions.
- Idempotency và transaction cho side effects.

## 5. Bẫy lớn: type mappings KHÔNG phải allowlist

Trong `MappingJackson2MessageConverter` của Spring 6.2.x, nếu type ID **không nằm trong map**, converter có thể dùng ID như một **tên class đầy đủ** để thử resolve. Việc chỉ định map **không tự đóng fallback này**.

~~~text
Đã cấu hình:
  "invoice-created-v1" -> InvoiceCreatedV1.class

Nhận _type="invoice-created-v1"
  -> map khớp -> InvoiceCreatedV1

Nhận _type="java.lang.ProcessBuilder"
  -> không khớp -> đường fallback class-name lookup (nếu không chặn)

Nhận _type="com.example.other.SomeClass"
  -> không khớp -> đường fallback class-name lookup (nếu không chặn)
~~~

Đây là vấn đề **dữ liệu điều khiển lựa chọn kiểu**. Một class có trên classpath không mặc nhiên an toàn để Jackson instantiate. Một số Java classes/libraries có nguy cơ được sử dụng như deserialization gadgets, đặc biệt trong môi trường có khả năng gửi message từ nguồn không đáng tin cậy.

**Không đủ an toàn nếu chỉ:**
- Gọi `setTypeIdMappings(Map.of(...))` rồi nghĩ mọi ID khác sẽ bị reject.
- Dùng `@JmsListener(InvoiceCreatedV1 event)` nhưng không biết converter chạy trước handler.
- Deserialize xong mới `instanceof`/cast; lúc đó object đã được tạo.
- Kiểm tra `eventType` trong body sau khi parser cho phép tùy ý class name.
- Tắt `ObjectMessage` nhưng lại cho JSON metadata chọn Java class không hạn chế.

Bảng tóm tắt:

| Cơ chế | Tác dụng | Không đảm bảo |
| --- | --- | --- |
| `setTypeIdPropertyName` | Chọn property chứa ID | Không giới hạn giá trị của ID |
| `setTypeIdMappings` | Khai báo alias ↔ class | Không chặn ID lạ dùng tên class |
| `setTrustedPackages` | Hạn chế package cho raw class-name fallback | Không phải exact class/alias allowlist |
| **Kiểm tra alias theo `Map/Set` trước deserialize** | Từ chối mọi ID không đăng ký | Vẫn cần schema/parser security |
| Broker ACL/TLS | Chặn publisher không có quyền | Không tự chặn JSON hợp lệ nhưng độc hại |
| DTO validation | Kiểm tra business semantics | Không thay thế chọn type an toàn |

## 6. Spring Security Advisory CVE-2026-41855

Ngày **08/06/2026**, Spring công bố **CVE-2026-41855**: các Jackson JMS converters cho phép instantiate class ngoài dự kiến khi môi trường JMS **không tin cậy**, có thể gây hành vi trái phép thông qua gadget deserialization.

Các phiên bản bị ảnh hưởng theo thông báo Spring bao gồm:
- Spring Framework **6.2.0 đến 6.2.18**.
- Spring Framework **7.0.0 đến 7.0.7**.
- Một số nhánh cũ theo bảng advisory.

Các bản sửa công khai:
- **6.2.19** cho nhánh 6.2.
- **7.0.8** cho nhánh 7.0.

Cơ chế giới hạn package mới:

~~~java
// API có từ Spring Framework 6.2.19 trong nhánh 6.2:
converter.setTrustedPackages("com.example.jmstypes");
~~~

Nó giới hạn package được phép **khi đi đường fallback raw Java class name**. Điều cần hiểu chính xác:

1. Alias đã có trong mapping thường được resolve trực tiếp tới class đã đăng ký.
2. Type ID lạ có dạng FQCN có thể bị chặn nếu package không được tin cậy.
3. Một FQCN khác **nằm trong package được tin cậy** có thể còn được resolve theo đường fallback; tức trusted packages không phải exact alias allowlist.
4. Không đặt `setTrustedPackages` vẫn không phải chính sách an toàn cho môi trường untrusted.
5. Đừng cấu hình cho phép mọi package hoặc lựa chọn package quá rộng để chữa lỗi triển khai.

**Khuyến nghị:** trên bản Spring đã vá, dùng `setTrustedPackages` như một lớp phòng thủ thêm, nhưng thực hiện **exact allowlist của wire aliases trước khi converter chọn class**. Đây là cách tránh nới quyền vì một DTO khác vô tình cùng package.

### Kiểm tra dependency thực tế

Trong Maven project:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-jms
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework:spring-jms
.\mvnw.cmd dependency:tree -Dincludes=org.springframework:spring-core
~~~

Không dựa vào tên Spring Boot starter để kết luận đã vá. Lab bên dưới cần phiên bản **spring-jms 6.2.19+**; nếu còn 6.2.18 thì phải cập nhật Spring Boot/Spring Framework theo khuyến nghị nhà phát hành trước khi biên dịch `setTrustedPackages`.

Tài liệu gốc: https://spring.io/security/cve-2026-41855/

## 7. Chính sách nhiều lớp: ID, package, DTO và business validation

Định nghĩa hợp đồng:

~~~text
Allowed wire aliases:
  invoice-created-v1
  invoice-cancelled-v1

Allowed mapped Java DTOs:
  InvoiceCreatedV1
  InvoiceCancelledV1

Trusted Java package (defense in depth):
  com.example.jmstypes
~~~

Một consumer nên thực hiện theo thứ tự:

1. Nhận đúng JMS body type đã thỏa thuận (ví dụ `TextMessage`).
2. Đọc `message.getStringProperty("_type")`.
3. Kiểm tra ID thuộc **tập alias chính xác** do service định nghĩa. Nếu thiếu hoặc không nằm trong tập, từ chối trước Jackson parse.
4. Tra ID sang DTO đã đăng ký. Không gọi `Class.forName(typeId)` trong mã nghiệp vụ.
5. Parse JSON vào DTO và kiểm tra schema.
6. Validate business invariants, ID, version, timestamps, enum và field bắt buộc.
7. Xử lý nghiệp vụ idempotent, chỉ ACK/commit trong transaction phù hợp.
8. Với message bị từ chối, thực hiện retry/DLQ/quarantine theo policy; không retry vô hạn.

**Fail closed** nghĩa là unknown ID luôn bị reject theo chính sách, không tự đoán DTO gần giống hoặc mở rộng trusted package.

### Ba lớp kiểm soát khác nhau

**Exact alias allowlist:** bảo đảm người gửi không chọn class tùy ý bằng property.  
**Trusted packages:** lớp bảo vệ nếu có đường code nào vẫn đi qua raw class-name fallback.  
**Jackson + DTO validation:** bảo đảm dữ liệu trong class được phép có cấu trúc và giá trị hợp lệ.

Một mã `_type="invoice-created-v1"` hợp lệ vẫn có thể chứa payload 500 MB, JSON quá sâu hoặc `totalMinor=-5`. Những việc đó cần parser limits/broker size limits/validation riêng.

## 8. Tạo StrictJsonMessageConverter (Java 17+)

Ví dụ này dùng Spring 6.2.19+, Jackson 2 và Jakarta Messaging. Tạo **ba file riêng** cùng package `com.example.jmstypes`.

**File 1 — `src/main/java/com/example/jmstypes/InvoiceCreatedV1.java`**

~~~java
package com.example.jmstypes;

public record InvoiceCreatedV1(String invoiceId, long totalMinor) {
}
~~~

**File 2 — `src/main/java/com/example/jmstypes/InvoiceCancelledV1.java`**

~~~java
package com.example.jmstypes;

public record InvoiceCancelledV1(String invoiceId, String reason) {
}
~~~

**File 3 — `src/main/java/com/example/jmstypes/StrictJsonMessageConverter.java`**

~~~java
package com.example.jmstypes;

import java.util.Map;

import com.fasterxml.jackson.databind.JavaType;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageType;

public final class StrictJsonMessageConverter
        extends MappingJackson2MessageConverter {

    private static final Map<String, Class<?>> TYPES = Map.of(
            "invoice-created-v1", InvoiceCreatedV1.class,
            "invoice-cancelled-v1", InvoiceCancelledV1.class);

    public StrictJsonMessageConverter() {
        setTargetType(MessageType.TEXT);
        setTypeIdPropertyName("_type");
        setTypeIdMappings(TYPES);
        setTrustedPackages("com.example.jmstypes");
    }

    @Override
    protected JavaType getJavaTypeForMessage(Message message)
            throws JMSException {

        if (!(message instanceof TextMessage)) {
            throw new MessageConversionException(
                    "Only JSON TextMessage is supported");
        }

        String typeId = message.getStringProperty("_type");
        if (typeId == null || !TYPES.containsKey(typeId)) {
            throw new MessageConversionException(
                    "Unrecognized JMS type ID");
        }

        // Đã chặn ID lạ: không để Spring đi vào fallback.
        return super.getJavaTypeForMessage(message);
    }
}
~~~

**Điểm bảo mật quan trọng:** `getJavaTypeForMessage` chạy trong quá trình `fromMessage`, trước khi converter gọi Jackson parse. Vì thế một `_type="java.lang.ProcessBuilder"`, dù class tồn tại, sẽ bị chặn do không nằm trong `TYPES`. Mặc dù đã dùng `setTrustedPackages`, bản kiểm tra `TYPES.containsKey(typeId)` mới là exact allowlist.

**Giới hạn của mẫu:** bảo vệ **đường nhận**. Converter gốc vẫn có thể phát raw Java class name cho một object outbound không nằm trong map. Trong production, phải giới hạn DTO được gửi qua publisher API typed hoặc validate loại object trước `convertAndSend`; nếu tùy biến converter để chặn gửi, cần bao phủ tất cả đường `toMessage` mà ứng dụng sử dụng, kể cả overload của `SmartMessageConverter` nếu có.

**DTO records không tự validate nghiệp vụ.** Bạn nên kiểm tra `invoiceId` khác rỗng, `totalMinor >= 0`, độ dài string và field bắt buộc trong handler/service validator sau khi JSON parse.

## 9. Lab chạy được: Spring Boot 3.5 + Artemis embedded

Lab này tạo ba queue và quan sát:
- JMS `_type` đúng alias ở message đã gửi.
- `receiveAndConvert` trả về Java record đúng loại.
- Unknown alias mang raw class name bị **từ chối trước deserialize**.

Stack: **Spring Boot 3.5.x patch sử dụng Spring Framework 6.2.19+**, Java 17, Jackson 2, Artemis embedded. Dùng môi trường local; đừng publish malformed message đến broker production.

### 9.1. Tạo Maven project

Dùng https://start.spring.io/:

- Project Maven, Java 17.
- Group `com.example`, artifact `jms-type-lab`, package `com.example.jmstypes`.
- Spring Boot 3.5.x cập nhật patch bảo mật.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).
- Đảm bảo có Jackson databind; có thể thêm `spring-boot-starter-json`.

Thêm dependency broker nhúng vào phần `<dependencies>` của `pom.xml` do Spring Initializr tạo:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-json</artifactId>
</dependency>
~~~

Boot parent/BOM quản lý version; không ghép spring-jms/Jackson/Artemis versions tùy tiện. Kiểm tra `spring-jms` đã đạt 6.2.19+ bằng Maven dependency tree.

### 9.2. Cấu hình lab

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-type-lab
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.raw,demo.converted,demo.unknown
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Broker embedded chỉ phục vụ demo converter, không chứng minh persistence/failover production. Ba queue tách riêng để việc nhận raw không làm mất chính message muốn thử conversion.

### 9.3. Java ứng dụng hoàn chỉnh

Thêm **File 4 — `src/main/java/com/example/jmstypes/JmsTypeLabApplication.java`**:

~~~java
package com.example.jmstypes;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConversionException;

@SpringBootApplication
public class JmsTypeLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsTypeLabApplication.class, args);
    }

    @Bean
    ApplicationRunner runTypeIdDemo(ConnectionFactory factory) {
        return args -> {
            JmsTemplate template = new JmsTemplate(factory);
            template.setMessageConverter(
                    new StrictJsonMessageConverter());
            template.setReceiveTimeout(2_000L);

            template.convertAndSend(
                    "demo.raw",
                    new InvoiceCreatedV1("INV-7", 5500));

            Message raw = template.receive("demo.raw");
            if (!(raw instanceof TextMessage)) {
                throw new IllegalStateException(
                        "Expected a TextMessage");
            }

            System.out.println("TYPE_ID="
                    + raw.getStringProperty("_type"));
            System.out.println("RAW_TYPE=TextMessage");

            template.convertAndSend(
                    "demo.converted",
                    new InvoiceCreatedV1("INV-8", 7000));

            Object payload =
                    template.receiveAndConvert("demo.converted");
            if (!(payload instanceof InvoiceCreatedV1 event)) {
                throw new IllegalStateException(
                        "Expected InvoiceCreatedV1");
            }

            System.out.println("DTO="
                    + event.invoiceId() + ":" + event.totalMinor());

            // Chỉ thử message giả mạo trong local lab.
            template.send("demo.unknown", session -> {
                TextMessage message = session.createTextMessage(
                        "{\"invoiceId\":\"INV-X\",\"totalMinor\":1}");
                message.setStringProperty(
                        "_type", "java.lang.ProcessBuilder");
                return message;
            });

            try {
                template.receiveAndConvert("demo.unknown");
                throw new IllegalStateException(
                        "Expected type ID rejection");
            } catch (MessageConversionException expected) {
                System.out.println(
                        "REJECTED_UNKNOWN_TYPE=true");
            }
        };
    }
}
~~~

Đây là **ứng dụng hoàn chỉnh khi kết hợp đủ bốn file** và dependencies/config đúng. `JmsTemplate` được tạo trực tiếp và gắn converter rõ ràng; lab không phụ thuộc việc auto-config toàn bộ listener factories của Boot.

### 9.4. Cách chạy

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Bỏ qua log khởi tạo Spring/Artemis, các dòng do application in ra theo thứ tự sẽ là:

~~~text
TYPE_ID=invoice-created-v1
RAW_TYPE=TextMessage
DTO=INV-8:7000
REJECTED_UNKNOWN_TYPE=true
~~~

**Giải thích:** converter dùng alias map để gắn property và giải mã JSON vào record `InvoiceCreatedV1`. Với message cuối, override `getJavaTypeForMessage` kiểm tra alias trước, ném `MessageConversionException` vì `java.lang.ProcessBuilder` không nằm trong map, nên Jackson không được yêu cầu instantiate class đó.

**Không suy luận sai từ demo:** `JmsTemplate.receiveAndConvert` đồng bộ có thể hoàn tất ack/local commit trong phần `receive` trước khi lỗi converter xảy ra. Một lần bị reject ở demo **không bảo đảm message còn ở queue để retry**. Nếu công việc cần xử lý đáng tin cậy, dùng transaction boundary đúng, listener container, DLQ và idempotency.

## 10. Cấu hình converter cho JmsTemplate và @JmsListener

Lab tạo một template trực tiếp để không mơ hồ về cấu hình. Trong ứng dụng thật, có thể khai báo converter bean:

~~~java
@Bean
StrictJsonMessageConverter strictJmsConverter() {
    return new StrictJsonMessageConverter();
}
~~~

Đây là mảnh method trong một Spring `@Configuration`. Nếu dự án tự tạo nhiều template hoặc container, phải **gắn converter vào từng đường gửi/nhận** tương ứng, không chỉ thấy có một bean là đủ.

JmsTemplate thủ công:

~~~java
@Bean("invoiceTemplate")
JmsTemplate invoiceTemplate(
        ConnectionFactory factory,
        StrictJsonMessageConverter converter) {
    JmsTemplate template = new JmsTemplate(factory);
    template.setMessageConverter(converter);
    return template;
}
~~~

Factory listener:

~~~java
@Bean("invoiceListenerFactory")
DefaultJmsListenerContainerFactory invoiceListenerFactory(
        ConnectionFactory factory,
        StrictJsonMessageConverter converter) {
    var factoryBean = new DefaultJmsListenerContainerFactory();
    factoryBean.setConnectionFactory(factory);
    factoryBean.setMessageConverter(converter);
    factoryBean.setSessionTransacted(true);
    return factoryBean;
}
~~~

Các đoạn này là **mảnh cấu hình**; cần imports `jakarta.jms.ConnectionFactory`, `@Bean`, `JmsTemplate` và `DefaultJmsListenerContainerFactory`, và đặt vào class Spring phù hợp. Với Boot, có thể dùng `DefaultJmsListenerContainerFactoryConfigurer` để giữ những defaults hữu ích; sau đó ghi đè converter/session transacted theo contract.

Listener minh họa:

~~~java
@Component
class InvoiceListener {

    @JmsListener(
        destination = "billing.events",
        containerFactory = "invoiceListenerFactory")
    public void onCreated(InvoiceCreatedV1 event) {
        // Validate event rồi xử lý idempotent.
        // Ném exception khi nghiệp vụ chưa thành công.
    }
}
~~~

Cần `@Component`, `@JmsListener`, cấu hình annotation-driven JMS thích hợp và imports tương ứng. **Không biến annotation method signature thành biện pháp bảo mật duy nhất**: phần conversion có thể chạy trước khi method được gọi. Test bằng broker thật với alias hợp lệ/lạ và JSON lỗi.

## 11. Phân biệt allowlist với JSON polymorphism

Một type ID ở JMS property không đồng nghĩa Jackson phải tin những field chọn class trong JSON:

~~~json
{
  "eventType": "InvoiceCreated",
  "schemaVersion": 1,
  "invoiceId": "INV-7",
  "totalMinor": 5500
}
~~~

**Cách an toàn phổ biến:** target DTO là record/class thuần dữ liệu, field types cố định. Tránh:
- `ObjectMapper.activateDefaultTyping(...)` không giới hạn với nguồn ngoài.
- `@JsonTypeInfo(use = JsonTypeInfo.Id.CLASS)` cho payload không tin cậy.
- Deserializing vào `Object` / interface quá chung kèm class name từ body.
- Nhận tên class trong JSON rồi tự `Class.forName(...)`.
- DTO có code/tác dụng phụ bất thường trong constructors/custom deserializers.
- Thư viện/Jackson versions lỗi thời hoặc thiếu parser limits.

**Một allowlist đúng ở tầng `_type` không thể sửa rủi ro polymorphic deserialization nằm sâu trong field của DTO.** Cần kiểm soát ObjectMapper, type hierarchy, JSON limits và validation độc lập.

### Lưu ý về ObjectMessage

`ObjectMessage` sử dụng **Java native serialization**, có vấn đề tương thích classpath và deserialization security khác. `MappingJackson2MessageConverter` thông thường chuyển JSON `TextMessage` hoặc `BytesMessage`; đừng cố coi `ObjectMessage` và JSON type ID như hai cách giống hệt nhau. Trong hệ thống liên dịch vụ, schema JSON/Avro/Protobuf thường có hợp đồng dễ kiểm soát hơn Java object serialization.

## 12. Versioning: type ID phải là wire contract ổn định

Giả sử v1:

~~~text
invoice-created-v1 -> com.shop.billing.InvoiceCreated
~~~

Sau refactor Java:

~~~text
invoice-created-v1 -> com.shop.contract.events.InvoiceCreatedV1
~~~

Nếu schema wire v1 không đổi, alias có thể giữ nguyên. Người gửi không cần hiểu package ở consumer. Nhưng class mới vẫn phải đọc đúng JSON cũ và giữ semantics cũ; refactor class **không thay thế test compatibility**.

Nếu phải đổi breaking schema:

~~~text
invoice-created-v1 -> InvoiceCreatedV1.class
invoice-created-v2 -> InvoiceCreatedV2.class
~~~

Quy trình triển khai an toàn:
1. Định nghĩa schema v2 và tài liệu mapping.
2. Consumer được nâng cấp để hiểu **cả v1 và v2**.
3. Producer bắt đầu phát alias v2 sau khi consumers hỗ trợ.
4. Đo số message v1 còn trong broker, DLQ, retry backlog.
5. Chỉ gỡ v1 khi retention/replay contract cho phép.
6. Kiểm thử rolling deployment và restore từ backup/broker failover.

Nếu một release mới chỉ đăng ký v2 rồi xóa v1, consumer có thể reject backlog v1 còn tồn tại; đây là thay đổi về hợp đồng giao tiếp chứ không chỉ thay Java package.

### Schema version và alias

Không nhất thiết cứ thêm một optional field là phải tạo alias mới. Có thể giữ v1 khi thay đổi **backward compatible** đã được hai bên thống nhất. Khi đổi kiểu field, nghĩa nghiệp vụ, required/optional semantics hoặc cấu trúc không tương thích, dùng v2 và cập nhật validator.

## 13. JMS property, JMSType và selector

Producer có thể đặt property:

~~~java
// Mảnh code trong một service có JmsTemplate:
jmsTemplate.send("billing.events", session -> {
    TextMessage message = session.createTextMessage(
            "{\"invoiceId\":\"INV-7\",\"totalMinor\":5500}");
    message.setStringProperty("_type", "invoice-created-v1");
    message.setStringProperty("contentType", "application/json");
    return message;
});
~~~

Đây là cách tạo message thủ công. Nếu thay bằng `convertAndSend(dto)` với converter đã cấu hình, converter tự sinh JSON body và type ID property theo mapping. **Không gửi hai lần cùng event** chỉ để thử hai cách.

Property name JMS tuân theo quy tắc identifier tương ứng; `_type` là tên hợp lệ cho ví dụ. Tránh đụng tên dành riêng. `JMSType` là **JMS header riêng**, không tự trở thành `_type`.

JMS selector có thể đọc JMS properties:

~~~sql
_type = 'invoice-created-v1'
~~~

Selector giúp chọn message theo metadata, **không phải authorization**. Producer không tin cậy có thể gán `_type` giả mạo nếu broker ACL cho phép publish; consumer vẫn phải validate allowlist và schema. Selector không parse JSON body `eventType` trừ khi producer cũng đặt property phù hợp.

## 14. Lỗi conversion và transaction/acknowledgement

Các giai đoạn:

~~~text
Broker
  -> nhận JMS Message
  -> kiểm tra type ID, body type
  -> chọn Java DTO
  -> Jackson parse
  -> schema/business validation
  -> business handler
  -> JMS ACK/COMMIT theo transaction boundary
~~~

**Trên thực tế, thời điểm ACK/COMMIT phụ thuộc đường nhận.** Với `JmsTemplate.receiveAndConvert` tự quản lý local session, phần nhận message có thể ACK/commit **trước** khi converter được gọi. Vì thế converter throw exception không nhất thiết khiến broker giao lại message. Nếu xử lý quan trọng, dùng transaction bên ngoài bao toàn bộ quá trình hoặc `@JmsListener` với session transacted và policy redelivery đúng.

Nếu dùng listener transacted:
- Converter/handler ném exception có thể làm rollback session.
- Message có thể được redeliver theo broker policy; cần max attempts/backoff/DLQ.
- JSON sai cố định sẽ trở thành **poison message** nếu retry vô hạn.
- Khi xử lý DB thành công nhưng JVM chết trước JMS commit, message có thể được giao lại; **idempotency** theo event/business key là bắt buộc cho side effect quan trọng.

Không viết `catch(Exception e) { log(e); return; }` trong handler nếu lỗi đó phải dẫn đến rollback: một method trả về bình thường có thể bị container coi là thành công.

### Phân loại lỗi để vận hành

| Loại lỗi | Ví dụ | Chính sách cần cân nhắc |
| --- | --- | --- |
| `UNKNOWN_TYPE_ID` | `_type="invoice-created-v99"` | Quarantine/DLQ, xác minh release/version |
| `RAW_CLASS_NAME_REJECTED` | `_type="java.lang.ProcessBuilder"` | Security alert và chặn publisher sai/độc hại |
| `BODY_TYPE_MISMATCH` | `BytesMessage` trong policy TEXT-only | Chặn trước Jackson; sửa contract |
| `JSON_SYNTAX_ERROR` | JSON không hợp lệ | DLQ sau policy retry rõ ràng |
| `SCHEMA_INVALID` | thiếu invoiceId, tổng âm | Business validation, quarantine |
| `CLASS_VERSION_DRIFT` | alias đúng nhưng DTO consumer không tương thích | Test contract/rolling deployment |
| `BROKER_UNAVAILABLE` | JMS connection/commit fail | Retry có giới hạn và phục hồi hạ tầng |
| `BUSINESS_FAILURE` | DB/API lỗi tạm thời | Transaction, retry và idempotency |

## 15. Hệ thống không cần dynamic type selection thì sao?

Nếu một destination chỉ chuyên chở một loại JSON message, cách tường minh có thể đơn giản và dễ audit hơn:

~~~java
// Mảnh code: objectMapper là Jackson mapper đã cấu hình.
Message message = jmsTemplate.receive("invoice-created.v1");
if (!(message instanceof TextMessage text)) {
    throw new IllegalStateException("Unexpected body type");
}
InvoiceCreatedV1 event = objectMapper.readValue(
        text.getText(), InvoiceCreatedV1.class);
~~~

Ở đây **consumer tự chọn class** cố định, không lấy tên class từ JMS property. Đánh đổi: nếu một queue chứa nhiều message types, cần dispatch table hoặc tách destination đã định nghĩa trước. Đây không phải lời khuyên dùng raw receive để giải quyết ACK: `JmsTemplate` vẫn quản lý tài nguyên/transaction; hãy thiết kế reliability riêng.

Với hệ thống đa ngôn ngữ, JSON Schema/Avro/Protobuf và một envelope `eventType + schemaVersion` có thể là hợp đồng phù hợp hơn. Java type ID nên là adapter metadata, không phải kiến trúc buộc mọi consumer biết Java FQCN.

## 16. Ma trận kiểm thử cần có

| Input | Kỳ vọng |
| --- | --- |
| Alias `invoice-created-v1`, body hợp lệ | Tạo đúng `InvoiceCreatedV1` |
| Alias `invoice-cancelled-v1`, body hợp lệ | Tạo đúng `InvoiceCancelledV1` |
| Không có property `_type` | Từ chối trước JSON parse |
| `_type=""` | Từ chối |
| `_type="invoice-created-v99"` | Từ chối hoặc đưa vào quarantine |
| `_type="java.lang.ProcessBuilder"` | Từ chối **trước** class fallback |
| FQCN trong **trusted package** nhưng không có alias | Vẫn từ chối nhờ exact ID allowlist |
| Type ID đúng nhưng `BytesMessage` khi chỉ chấp nhận Text | Từ chối body type |
| Type ID đúng nhưng JSON lỗi | Parse error, không gọi handler |
| Type ID đúng nhưng dữ liệu không hợp lệ | Validation error |
| JSON quá lớn/quá sâu | Broker/parser resource limits chặn |
| Class outbound chưa được map | Test phát hiện việc converter gửi raw FQCN |
| Consumer mới đọc message cũ v1 | Compatibility test pass hoặc có migration rõ |
| Listener ném lỗi sau conversion | Transaction rollback/redelivery theo policy |
| `receiveAndConvert` conversion fail | Không giả định message tự quay lại |
| JMS selector theo `_type` | Routing hợp lệ nhưng không thay bảo mật |
| Spring có bản bị ảnh hưởng CVE | CI dependency scan fail nếu hệ thống yêu cầu bản vá |

### Tại sao cần test broker thật?

Unit tests với fake JMS `Session`/`TextMessage` có thể kiểm chứng map và rejection, nhưng không chứng minh:
- JMS producer/consumer giữ properties thế nào trên broker.
- JMS transaction commit/rollback.
- Redelivery/poison-message/DLQ policy.
- Concurrency/queue/topic subscription.
- Restart/backlog và nhiều phiên bản consumer cùng chạy.

Dùng broker test/staging có cấu hình gần production. Không gửi payload bị coi là độc hại đến môi trường chung. Test negative case phải kiểm tra **type rejection xảy ra trước khi DTO bất kỳ được tạo**.

## 17. Vận hành khi xuất hiện type ID lạ

Một runbook thực tế:

1. Ghi nhận JMS message ID, destination, publisher identity, sanitized type ID, thời gian, deployment version và error category.
2. Kiểm tra alias chưa biết có nằm trong schema registry/change log đã công bố hay không.
3. Nếu alias là version mới hợp lệ, deploy consumer hỗ trợ alias đó với DTO/validator và contract tests, thường **consumer trước producer**.
4. Nếu alias mang FQCN đáng ngờ, xem đây là sự cố bảo mật; kiểm tra ACL và publisher, không mở trusted wildcard.
5. Cho message không thể xử lý vào DLQ/quarantine có retention phù hợp thay vì vòng retry vô tận.
6. Khi replay, dùng cơ chế kiểm soát quyền và idempotency để không tạo duplicate side effects.
7. Theo dõi tỷ lệ unknown IDs, parser errors, redelivery counts, DLQ, broker queue depth và client library version.
8. Sau nâng cấp, giữ mapping cũ đủ lâu để đọc backlog/retained messages theo hợp đồng.

Không log toàn bộ payload có PII/secret chỉ để chẩn đoán một type ID lỗi; log metadata an toàn hoặc tạo bản điều tra có kiểm soát quyền.

## 18. Checklist review trước production

- Hợp đồng thống nhất **JMS property name** dùng cho type ID chưa?
- Những alias nào được phép nhận, chúng ánh xạ tới Java DTO nào?
- `setTypeIdMappings` đã được hiểu là **mapping chứ không phải allowlist**?
- Unknown alias có bị chặn **trước** fallback raw FQCN và Jackson parse?
- `setTrustedPackages` được cấu hình trên Spring Framework **6.2.19+** hoặc bản đã vá tương ứng?
- Không mở wildcard hoặc package quá rộng khi xử lý JMS untrusted?
- DTO có cấu trúc cố định và Jackson parser không bật polymorphic class lookup tùy ý?
- Producer có test outbound type IDs để không phát raw Java class names ngoài ý muốn?
- Body type JSON TEXT/BYTES được chọn rõ, có schemaVersion và validate data?
- Broker auth/TLS/ACL chặn publisher ngoài quyền?
- Converter bean thực sự được gắn vào template và listener factory đang chạy?
- Transaction/ACK xảy ra đúng lúc, có idempotency và retry/DLQ?
- Consumer version mới vẫn hiểu backlog alias cũ?
- Có negative tests thiếu type ID, type ID độc hại, JSON sai, DTO mới chưa map?
- Có kiểm soát payload size/depth, metrics, cảnh báo và runbook?
- Có tài liệu cho Java 17+, Spring 6.2.x/Boot 3.5.x dependency tree đã vá?

## 19. Bài tập

1. Gửi `TextMessage` JSON không có `_type`. Dự đoán kết quả khi qua strict converter.
2. Thêm `InvoiceCancelledV1` vào lab, gửi và kiểm tra alias/DTO nhận được.
3. Vì sao chỉ thêm `setTypeIdMappings(Map.of("safe", Safe.class))` không ngăn raw FQCN fallback?
4. Type ID `com.example.jmstypes.NotMappedDto` nằm trong trusted package; strict converter có chấp nhận không? Vì sao?
5. Nếu Spring JMS còn ở 6.2.18, cần thao tác gì trước khi dùng `setTrustedPackages`?
6. Đổi package của Java DTO, giữ JSON schema/alias; chỉ ra nơi phải đổi và nơi không phải đổi.
7. Nếu message body có `eventType="InvoiceCancelled"` nhưng JMS `_type="invoice-created-v1"`, consumer phải xử lý thế nào?
8. Dùng JMS selector `_type='invoice-created-v1'` có khiến consumer an toàn nếu broker cho phép bất kỳ publisher nào gửi không?
9. Vì sao bắt `ClassCastException` sau `receiveAndConvert` không ngăn việc converter từng instantiate class khác?
10. Với `@JmsListener` transacted, JSON lỗi bị rollback nhiều lần; thiết kế retry budget và DLQ ra sao?
11. Một queue chỉ có `InvoiceCreatedV1` JSON; so sánh consumer dùng class cố định với dynamic type ID mapping.
12. Viết integration test cho tình huống publisher v2 gửi alias mới khi consumer v1 còn chạy.

## Tài liệu chính thức để đối chiếu

- Spring Framework 6.2.19 — `MappingJackson2MessageConverter` API (type ID property, mappings, trusted packages): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Spring Framework Security Advisory, **CVE-2026-41855** (công bố 08/06/2026): https://spring.io/security/cve-2026-41855/
- Spring Framework 6.2 — `JmsTemplate` và message conversion: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — annotated listener endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot 3.5 — JMS/Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — system requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Jakarta Messaging 3.1 — headers, properties, selectors, acknowledgement: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
