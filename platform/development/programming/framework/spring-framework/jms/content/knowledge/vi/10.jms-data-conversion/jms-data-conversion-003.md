# Chuyển đổi DTO sang JSON và lựa chọn converter theo phiên bản Spring

> **Chủ đề:** Chuyển đổi dữ liệu trong Spring Framework JMS. Bài học này hướng dẫn biến **Java DTO** thành JSON bên trong JMS `TextMessage`, giải mã JSON trở lại DTO và chọn đúng `MessageConverter` theo **Spring Framework 5/6/7, Spring Boot 2/3/4 và Jackson 2/3**. Trọng tâm không chỉ là “gửi được JSON”, mà còn là type alias ổn định, tương thích producer–consumer, bảo mật deserialization, kiểm thử và kế hoạch nâng cấp.

## 1. Bức tranh tổng thể

Trong ứng dụng JMS, phần **payload Java** và **wire message** không giống nhau. DTO như:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amountCents) {
}
~~~

là đối tượng Java. Broker không tự hiểu cấu trúc record này. Ta cần **serialization** sang JSON, rồi bọc JSON vào JMS message:

~~~text
Producer (Java/Spring)                             Broker/Consumer
-----------------------                            ---------------
OrderCreated DTO
   |
   v
JMS MessageConverter.toMessage(dto, session)
   |
   +--> JSON: {"eventId":"e-1","orderId":"O-42","amountCents":12500}
   +--> JMS TextMessage hoặc BytesMessage
   +--> type property: _type = "order-created.v1"
   |
   v
JmsTemplate.convertAndSend(...) -------> JMS queue
                                              |
                                              v
                                  JMS MessageConverter.fromMessage(...)
                                              |
                                              v
                                  OrderCreated DTO ở consumer
~~~

**Ba quyết định độc lập cần làm rõ:**

1. **Chọn định dạng body**: JSON trong `TextMessage` (dễ xem, dễ liên thông) hay `BytesMessage` (dạng bytes).
2. **Chọn converter/library**: Jackson 2 + `MappingJackson2MessageConverter` ở Spring 6, hay Jackson 3 + `JacksonJsonMessageConverter` ở Spring 7.
3. **Chọn hợp đồng type/schema**: JSON field names, version, alias, consumer DTO, allowlist và cách nâng cấp.

Mặc định, `JmsTemplate` dùng `SimpleMessageConverter` cho các kiểu JMS cơ bản. Nó **không tự biết chuyển mọi custom record/POJO thành JSON** chỉ vì dự án có Jackson trên classpath. Với DTO JSON, hãy đăng ký một converter chuyên dụng hoặc tự serialize bằng một JSON mapper trong lớp ứng dụng rồi gửi chuỗi (và tự giải mã ở consumer).

## 2. `MessageConverter` trong Spring JMS thực hiện việc gì?

Interface chính là:

~~~java
// Chữ ký API minh họa, KHÔNG tạo lại interface này trong ứng dụng.
package org.springframework.jms.support.converter;

public interface MessageConverter {
    jakarta.jms.Message toMessage(
            Object object, jakarta.jms.Session session)
            throws jakarta.jms.JMSException,
                   MessageConversionException;

    Object fromMessage(jakarta.jms.Message message)
            throws jakarta.jms.JMSException,
                   MessageConversionException;
}
~~~

**Hai chiều:**

- `toMessage`: Java object → `jakarta.jms.Message`, sử dụng `Session` do JMS runtime cung cấp để tạo `TextMessage`/`BytesMessage`.
- `fromMessage`: JMS `Message` → Java object, đọc body và metadata cần thiết để biết nên dùng kiểu Java nào.

`JmsTemplate.convertAndSend(queue, dto)` gọi `toMessage` trước khi gửi. `JmsTemplate.receiveAndConvert(queue)` hoặc `receiveSelectedAndConvert` gọi `fromMessage` khi nhận. `@JmsListener` cũng có thể dùng converter được cấu hình trên listener container, nhưng **không phải mọi listener tự động có cùng converter với mọi JmsTemplate** nếu nhiều factory hoặc nhiều bean.

### 2.1. Phân biệt hai loại `MessageConverter` của Spring

| API | Package | Làm việc với | Dùng ở đâu? |
| --- | --- | --- | --- |
| Spring **JMS** `MessageConverter` | `org.springframework.jms.support.converter.MessageConverter` | `jakarta.jms.Message` (Spring 6/7) | `JmsTemplate`, JMS listener container |
| Spring **Messaging** `MessageConverter` | `org.springframework.messaging.converter.MessageConverter` | `org.springframework.messaging.Message<?>` | `JmsMessagingTemplate`, `JmsClient` (Spring 7), các abstraction khác |
| Jackson JSON mapper | Jackson `ObjectMapper`/`JsonMapper` | Java objects ↔ JSON | Công cụ serialize mà converter gọi bên dưới |

**Đừng nhầm import:** hai lớp có thể cùng tên `MappingJackson2MessageConverter` hoặc `JacksonJsonMessageConverter` nhưng nằm ở **hai package khác nhau**. Trong bài này, mọi cấu hình `JmsTemplate` dùng package **`org.springframework.jms.support.converter`**.

### 2.2. `SimpleMessageConverter` không giải quyết JSON DTO

`SimpleMessageConverter` hỗ trợ phổ biến:
- `String` ↔ JMS `TextMessage`;
- `byte[]` ↔ `BytesMessage`;
- `Map` ↔ `MapMessage`;
- `Serializable` ↔ `ObjectMessage` (tùy cách dùng).

Với custom DTO, có thể gặp lỗi “cannot convert” hoặc tình cờ đi theo Java native serialization nếu DTO implements `Serializable`. **`ObjectMessage` không phải JSON**; việc giải mã Java object từ message lạ còn có các rủi ro deserialization và tương thích class. Không chuyển sang `ObjectMessage` chỉ để tránh viết converter JSON.

## 3. Ma trận lựa chọn converter theo phiên bản

Đây là phần dễ gây lỗi nhất khi sao chép code trên mạng:

| Stack đang dùng | Namespace JMS | Thế hệ Jackson | Converter JSON trong Spring JMS | Hướng chọn |
| --- | --- | --- | --- | --- |
| Spring Framework **5.3.x** / Spring Boot **2.7.x** | `javax.jms.*` | Jackson **2.x** | `MappingJackson2MessageConverter` | Legacy; không trộn code `jakarta.jms`; lập kế hoạch nâng cấp |
| Spring Framework **6.0–6.2** / Spring Boot **3.x** | `jakarta.jms.*` | Jackson **2.x** | `MappingJackson2MessageConverter` | Lựa chọn phù hợp cho dự án Boot 3; bản Spring 6.2 phải cập nhật security patch |
| Spring Framework **7.0+** / Spring Boot **4.x** | `jakarta.jms.*` | Jackson **3.x** (ưu tiên) | `JacksonJsonMessageConverter` | Lựa chọn chính cho ứng dụng mới Boot 4 |
| Spring Framework **7.0** còn giữ Jackson 2 | `jakarta.jms.*` | Jackson **2.x** | `MappingJackson2MessageConverter` **đã deprecated** | Chỉ là đường tương thích tạm thời để migration; không nên bắt đầu dự án mới bằng API này |

**Điểm phiên bản cần ghi nhớ:**

- Spring Framework **6.x** không dùng `JacksonJsonMessageConverter` của Spring Framework 7; dùng `MappingJackson2MessageConverter` cho Jackson 2.
- Spring Framework **7.x** giới thiệu `org.springframework.jms.support.converter.JacksonJsonMessageConverter` cho Jackson 3. `MappingJackson2MessageConverter` của Jackson 2 bị đánh dấu deprecated từ Spring 7.
- Jackson 3 chuyển các package lõi từ `com.fasterxml.jackson.*` sang `tools.jackson.*`; các annotation Jackson như `com.fasterxml.jackson.annotation.JsonProperty` vẫn thuộc `com.fasterxml.jackson.annotation`.
- Spring Boot **4** ưu tiên Jackson 3 và có modular starters; khi dùng Artemis + JSON, bảo đảm có JMS/Artemis starter và JSON/Jackson 3 starter/dependency.
- Spring Boot **3** thường quản lý Jackson 2; không copy code `tools.jackson.databind.*` vào project Boot 3 rồi mong Spring tự ánh xạ.
- Trong **Spring 5**, API JMS còn là `javax.jms`, khác namespace của Spring 6/7. Đây là thay đổi về loại class/bytecode, không thể khắc phục chỉ bằng đổi một import nếu thư viện JMS/provider chưa tương thích.

### 3.1. Bảo mật phiên bản: cảnh báo năm 2026

Spring công bố **CVE-2026-41855** liên quan deserialization không tin cậy ở các Jackson JMS converters. Các bản sửa tối thiểu được công bố gồm **Spring Framework 6.2.19** và **7.0.8** (cùng các nhánh hỗ trợ thương mại tương ứng). Từ các bản sửa này, API `setTrustedPackages(String...)` cho phép giới hạn package Java được phép dùng để giải mã kiểu được nêu trong message.

**Hệ quả thiết kế:**

1. Không đưa converter Jackson JMS phiên bản chưa vá lên queue có producer không tin cậy.
2. Ưu tiên **type alias hữu hạn** (ví dụ `order-created.v1`) ánh xạ vào DTO do ứng dụng xác định, thay vì nhận tên class tùy ý từ header.
3. Với môi trường cần xử lý message không tin cậy, giới hạn `trustedPackages` cùng việc kiểm soát vai trò broker, validate payload và cập nhật bản vá. `trustedPackages` không thay thế authorization/broker ACL.
4. Không dùng `"* "` hay một allowlist toàn bộ package tùy tiện; các kiểu được nhận nên được công bố rõ trong hợp đồng message.
5. Nếu dự án dùng Spring 6.1 hoặc 5.3 nhánh cũ, hãy kiểm tra bản vá khả dụng và lifecycle hỗ trợ chính thức; đừng giả định bản Boot cũ mặc nhiên đã an toàn.

Ví dụ thực hành phía dưới dùng **Spring Boot 4.0.9** (đi cùng Spring Framework 7.0.10 theo BOM), là bản sau mốc vá `7.0.8`. Các con số phiên bản ở đây nhằm mô tả **một bộ tương thích đã xác minh**, không phải khuyến nghị tự động nâng tất cả dự án lên bản lớn mới mà không kiểm thử.

## 4. Mục tiêu của một JSON message contract tốt

Trước khi viết Java, xác định hợp đồng trên wire thay vì phụ thuộc ngẫu nhiên vào tên class nội bộ.

Ví dụ JSON body của một sự kiện:

~~~json
{
  "eventId": "e-001",
  "orderId": "O-42",
  "amountCents": 12500
}
~~~

Metadata JMS dự kiến:

~~~text
_type = "order-created.v1"    (String property do converter tạo)
eventId = "e-001"            (String property do ứng dụng tạo)
schemaVersion = 1            (int/String property tùy contract)
JMSCorrelationID = "e-001"   (JMS header)
~~~

**Định hướng:**
- `eventId` trong body giúp consumer idempotent; eventId ở JMS property giúp dùng selector/broker tools.
- `_type` là một **application property** được converter đọc/ghi để lựa chọn DTO Java, không phải header `JMSType` tự động.
- `schemaVersion` là version của dữ liệu nghiệp vụ, không bắt buộc giống version của Spring/Jackson.
- Tránh gửi `demo.OrderCreated` làm type ID vì tên Java package có thể đổi khi refactor; một alias `order-created.v1` ổn định hơn.
- Đặt fields tiền tệ bằng `long amountCents` hoặc decimal có quy ước rõ, tránh `double` cho phép tính tiền.
- Đặt encoding rõ ràng (JSON `TextMessage` là chuỗi; `BytesMessage` cần thống nhất UTF-8) và payload size limit để không gây memory pressure.

**Quan trọng:** JSON hợp lệ chưa chắc schema tương thích. Khi consumer v1 gặp event v2 có field mới, cần policy: bỏ qua field không biết, từ chối version không hỗ trợ, hay chuyển tiếp theo schema registry. Không đổi ý nghĩa field nhưng giữ version cũ.

## 5. Cấu hình Jackson 2 JSON converter cho Spring Boot 3.x / Spring Framework 6.x

Khi còn ở Spring Boot 3 (ví dụ Spring 3.5.x đi với Framework 6.2.x), dùng:

~~~java
// Snippet cho Spring Framework 6.2.19+ / Jackson 2.
// Đặt trong @Configuration, import được liệt kê bên dưới.
@Bean
MappingJackson2MessageConverter jmsJsonConverter() {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(
            Map.of("order-created.v1", OrderCreated.class));

    // Có từ bản Spring Framework 6.2.19 (không có ở 6.2 cũ).
    converter.setTrustedPackages("demo");
    return converter;
}
~~~

Các imports tương ứng:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
~~~

Với code này, `OrderCreated` là DTO nằm trong package `demo` của dự án. Cần thêm Jackson 2 vào build nếu project chỉ kéo JMS/Artemis mà chưa có thư viện JSON:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

Hai đoạn trên là **snippet cấu hình**, không phải cả project Boot 3 runnable; version Spring Boot/Gradle và DTO phải do dự án cung cấp. Với Spring 6.1 hay 6.2 trước 6.2.19, API `setTrustedPackages` có thể chưa tồn tại; **nâng bản vá trước**, không bỏ giới hạn này chỉ để code biên dịch trên phiên bản chịu lỗ hổng.

**Các bước quan trọng:**
- `setTargetType(MessageType.TEXT)` tạo `TextMessage`; **mặc định Jackson JMS converter tạo `BytesMessage`**, không phải TextMessage.
- `setTypeIdPropertyName("_type")` tạo property dùng cho việc giải mã chiều nhận. Nếu không cấu hình, `fromMessage` có thể không biết loại DTO nào cần tạo.
- `setTypeIdMappings` ánh xạ alias cố định với Java class; consumer không phụ thuộc tên class serialized trên wire.
- `setTrustedPackages` là một lớp giới hạn thêm cho các tên class động không nằm trong map; alias map nên được kiểm soát riêng.
- Cấu hình converter nên là **singleton bean bất biến sau khởi tạo**. Không cập nhật mappings/trustedPackages theo request.

Nếu cần inject custom Jackson 2 `com.fasterxml.jackson.databind.ObjectMapper` để xử lý ngày giờ hoặc module đặc biệt, dùng constructor nhận mapper trong Spring 6.1+ hoặc `setObjectMapper` theo phiên bản. Tránh tạo một mapper ngầm khác với cấu hình dữ liệu của service rồi sinh JSON không nhất quán.

## 6. Cấu hình Jackson 3 converter cho Spring Boot 4.x / Spring Framework 7.x

Ở Spring Boot 4, dùng class mới:

~~~java
// Snippet Spring Framework 7.0.8+ / Jackson 3.
@Bean
JacksonJsonMessageConverter jmsJsonConverter() {
    JacksonJsonMessageConverter converter =
            new JacksonJsonMessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(
            Map.of("order-created.v1", OrderCreated.class));
    converter.setTrustedPackages("demo");
    return converter;
}
~~~

Imports khác Jackson 2 ở **tên converter**:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;
~~~

Nếu tự tạo JSON mapper của Jackson 3, import từ `tools.jackson.databind.*` / `tools.jackson.databind.json.JsonMapper` theo API Jackson 3 và cân nhắc dùng `JsonMapper.builder()`. **Không** truyền `com.fasterxml.jackson.databind.ObjectMapper` (Jackson 2) vào constructor converter Jackson 3; hai thế hệ không dùng chung Java type. Chỉ dùng mapper thực sự có module cần thiết, tránh tự động tin mọi loại class do message khai báo.

Với Spring Boot 4, một `MessageConverter` bean kiểu **Spring JMS** sẽ được gắn vào `JmsTemplate` được auto-configure và vào listener factory mặc định khi điều kiện auto-configuration thỏa. Nếu có template/factory được tạo thủ công, phải gọi `setMessageConverter(converter)` rõ ràng. Không suy ra rằng mọi custom listener factory đã nhận bean chỉ vì nó tồn tại.

## 7. Ví dụ thực hành đầy đủ: DTO → JSON TextMessage → DTO

Ví dụ sau dùng **Spring Boot 4.0.9 + Spring Framework 7.0.10 + Jackson 3 + Java 17**, với ActiveMQ Artemis bên ngoài ứng dụng. Mục tiêu là kiểm chứng cả **body JSON thực tế** và **giải mã DTO**. Vì chỉ có một thread/tác vụ kiểm tra, code nhận đồng bộ trên queue riêng và không triển khai listener song song tranh message.

### 7.1. Chuẩn bị môi trường

Cần:
- JDK `17+`, Gradle `8.14+` hoặc `9.x` và kết nối Maven Central để tải dependencies.
- Broker Artemis ở `tcp://localhost:61616`, tài khoản `demo/demo` **chỉ dành cho môi trường học cô lập** hoặc credentials phù hợp với broker thử nghiệm hiện có.
- Queue **anycast** tên `demo.json.dto` đã provision hoặc broker cho phép auto-create queue. Với môi trường thật, tạo queue trước để kiểm soát quyền.
- Không có consumer khác đang chiếm queue thử, hoặc chỉ sử dụng consumer có selector tương ứng.

Không dùng queue sản xuất để làm demo vì `receive` có thể xác nhận/tiêu thụ message. Khi dùng Docker, có thể chạy broker Artemis ở container có cổng 61616; phải xem tài liệu image/broker version để cấu hình credentials và persistence, không mặc định tất cả image có cùng account.

### 7.2. Cấu trúc dự án

~~~text
jms-dto-json/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/JsonJmsApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-dto-json'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.9'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-jackson'
}
~~~

Starter Artemis cung cấp JMS và client kết nối broker; starter Jackson cung cấp Jackson 3 và hạ tầng JSON. `io.spring.dependency-management` nhập BOM do Spring Boot quản lý. Giữ các versions tương thích trong một dependency set, tránh thêm Jackson 2/Jackson 3 ngẫu nhiên rồi sử dụng nhầm `ObjectMapper`.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
~~~

**Bảo mật:** username/password ở đây là dữ liệu giả định của broker học. Với hệ thống thật, đưa credentials qua `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` hoặc secret store; không commit mật khẩu thật. `mode: native` bảo đảm ứng dụng cố kết nối đến broker đã chỉ định, thay vì khởi chạy broker nhúng ngoài dự kiến.

### 7.3. Java runnable

`src/main/java/demo/JsonJmsApplication.java`:

~~~java
package demo;

import java.util.Map;
import java.util.UUID;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;

@SpringBootApplication
public class JsonJmsApplication {

    private static final String QUEUE = "demo.json.dto";

    public record OrderCreated(
            String eventId,
            String orderId,
            long amountCents) {
    }

    public static void main(String[] args) {
        SpringApplication.run(JsonJmsApplication.class, args);
    }

    @Bean
    JacksonJsonMessageConverter jsonJmsConverter() {
        JacksonJsonMessageConverter converter =
                new JacksonJsonMessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(
                "order-created.v1", OrderCreated.class));
        converter.setTrustedPackages("demo");
        return converter;
    }

    @Bean
    ApplicationRunner run(
            JmsTemplate jmsTemplate,
            JacksonJsonMessageConverter converter) {

        return args -> {
            String eventId = UUID.randomUUID().toString();

            OrderCreated outgoing =
                    new OrderCreated(eventId, "O-42", 12_500L);

            jmsTemplate.setReceiveTimeout(5_000L);

            // Converter chạy trước MessagePostProcessor.
            jmsTemplate.convertAndSend(QUEUE, outgoing, message -> {
                message.setJMSCorrelationID(eventId);
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            System.out.println("SEND_OK");

            String selector = "eventId = '" + eventId + "'";
            Message raw = jmsTemplate.receiveSelected(QUEUE, selector);

            if (!(raw instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "Expected TextMessage within 5000 ms");
            }
            System.out.println("WIRE_TEXT_MESSAGE=true");

            // Không khẳng định thứ tự property trong JSON.
            String json = text.getText();
            if (!json.contains("\"eventId\"")
                    || !json.contains("\"orderId\"")
                    || !json.contains("\"amountCents\"")) {
                throw new IllegalStateException("JSON fields missing");
            }
            System.out.println("JSON_FIELDS_PRESENT=true");

            String typeAlias = raw.getStringProperty("_type");
            if (!"order-created.v1".equals(typeAlias)
                    || raw.getIntProperty("schemaVersion") != 1) {
                throw new IllegalStateException(
                        "Type alias or schema version mismatch");
            }
            System.out.println("TYPE_ALIAS_OK=order-created.v1");

            Object restored = converter.fromMessage(raw);
            if (!(restored instanceof OrderCreated incoming)
                    || !outgoing.equals(incoming)) {
                throw new IllegalStateException("DTO mismatch");
            }

            System.out.println("DTO_ROUNDTRIP_OK=true");
        };
    }
}
~~~

**Điểm cần chú ý khi đọc chương trình:**

1. `@SpringBootApplication` bao gồm component scan và auto-configuration, tạo `JmsTemplate` từ Artemis `ConnectionFactory`.
2. Bean `JacksonJsonMessageConverter` thuộc **Spring JMS converter package**, nên Spring Boot có thể gắn nó cho auto-configured JmsTemplate.
3. `MessageType.TEXT` buộc converter tạo JMS `TextMessage` chứa JSON; nếu bỏ dòng này, mặc định là `BytesMessage`.
4. `_type` là property do converter ghi theo ánh xạ alias `order-created.v1` → `OrderCreated.class`. Alias giúp tránh truyền trực tiếp Java FQCN và giới hạn tập kiểu được xử lý.
5. `setTrustedPackages("demo")` dùng bản vá có API allowlist; demo chỉ chấp nhận package domain đã định trong phạm vi type lookup động. Mappings định nghĩa rõ loại event được sử dụng trong bài.
6. `MessagePostProcessor` đặt `eventId`, `schemaVersion` và correlation ID **sau khi DTO đã được convert**, trước khi gửi. Nó không tự serialize body.
7. `receiveSelected` nhận raw message có property eventId phù hợp; dùng UUID nhằm tách dữ liệu khỏi những lần thử khác.
8. Khi thấy `TextMessage`, chương trình đọc JSON gốc trên wire; kiểm tra ba field theo tên, **không phụ thuộc thứ tự JSON properties**.
9. `converter.fromMessage(raw)` dựa vào type alias để chọn `OrderCreated`, giải mã JSON và so sánh với record gốc.
10. Nếu broker không thể kết nối, queue/ACL sai, selector không khớp hoặc quá thời gian, chương trình ném exception; không báo PASS giả.

Cấu trúc trên là **một chương trình Spring Boot độc lập** trong project có các file kèm theo. `OrderCreated` là nested public record nằm trong `JsonJmsApplication`; Java record có `equals` dựa trên giá trị field nên phù hợp cho phép so sánh round-trip.

### 7.4. Chạy và đọc kết quả

Tại thư mục project, với Gradle, JDK và broker đã sẵn sàng:

~~~bash
gradle bootRun
~~~

Nếu gửi/nhận thành công, chương trình in các dòng sau (Spring Boot và Artemis còn có thể in thêm log):

~~~text
SEND_OK
WIRE_TEXT_MESSAGE=true
JSON_FIELDS_PRESENT=true
TYPE_ALIAS_OK=order-created.v1
DTO_ROUNDTRIP_OK=true
~~~

Ví dụ không in UUID để output mẫu ổn định. Nội dung JSON thực tế có thể khác thứ tự fields, cách escape ký tự hoặc whitespace tùy mapper; kiểm tra JSON bằng parsing/snapshot schema thay vì so sánh chuỗi byte-for-byte nếu không có nhu cầu canonical JSON.

**Với broker không có sẵn:** không nên biến lỗi `connect refused` thành lỗi converter. Đầu tiên kiểm tra `spring.artemis.broker-url`, credentials, queue existence, quyền send/consume. Trên máy không có Gradle hay broker, code đã được thiết kế để chạy nhưng chưa thể coi output này là kết quả thực thi tại máy người đọc.

### 7.5. Vì sao không dùng `receiveAndConvert` ngay trong demo?

Có thể rút ngắn:

~~~java
// Snippet: tạo selector như chương trình trên.
Object received =
        jmsTemplate.receiveSelectedAndConvert(
                "demo.json.dto", "eventId = 'e-001'");
~~~

Đoạn này là snippet (chỉ hoạt động nếu message tương ứng còn trong queue), không phải code thay thế trực tiếp khi chương trình dùng UUID ngẫu nhiên. Phương thức nhận và convert ngay trong một bước; trong thí nghiệm, ta chủ động nhận `raw Message` để **nhìn thấy body JSON, type alias và version trước khi gọi fromMessage**. Cả hai hướng đều hợp lệ.

### 7.6. Kiểm tra tự động mà không cần broker thật

Thử nghiệm **unit** nên tập trung vào converter:
1. Mock hoặc tạo fake `Session` trả về `TextMessage` phù hợp.
2. Gọi `converter.toMessage(dto, session)`, xác minh kiểu, JSON và alias.
3. Gọi `converter.fromMessage(message)`, so field values.
4. Kiểm tra trường hợp type alias không hợp lệ, JSON sai cấu trúc, thiếu field bắt buộc, thiếu metadata hoặc version chưa hỗ trợ.

Đây là **quy trình kiểm thử**, không phải code unit test runnable độc lập vì cần JMS Session implementation/mock framework cụ thể. Integration test dùng broker cô lập hoặc container thực để kiểm chứng rằng producer và consumer thật dùng cùng converter; đừng nhầm unit test converter với test kết nối/ACL/broker.

## 8. Khi dùng `@JmsListener`: producer và consumer phải cùng contract

Trong dự án thực tế, producer có thể là một app, consumer là app khác hoặc viết bằng ngôn ngữ khác. Khi sử dụng Spring Boot auto-configuration và một bean `MessageConverter` hợp lệ, default JMS listener factory cũng có thể dùng bean này. Nhưng **nếu có custom container factory** hoặc app khác, phải cấu hình converter tương ứng.

Ví dụ trong một Spring bean consumer (snippet, không chạy cùng queue với đồng bộ receive ở mục 7):

~~~java
// Đặt trong một @Component của ứng dụng có bật @EnableJms.
@JmsListener(destination = "orders.events")
public void handle(OrderCreated event) {
    System.out.println(event.orderId());
}
~~~

Khi metadata có type alias `order-created.v1` và converter nhận được đúng DTO, listener có thể nhận `OrderCreated`. Nếu annotation/method signature hoặc listener factory dùng converter khác, lỗi sẽ xuất hiện trước hoặc trong khi gọi handler.

**Đặc biệt lưu ý:**
- `@JmsListener` trên queue thật có thể cạnh tranh message với consumer khác. Không thêm nó vào cùng queue với `receiveSelected` của demo.
- Nếu consumer được viết bằng Node.js, Go hoặc một hệ thống khác, nó **không dùng được Java class name** trong `_type`. Hãy đưa schema version và event type ở dạng alias độc lập ngôn ngữ.
- Khi producer dùng JSON `TextMessage` nhưng consumer mong `BytesMessage`/`ObjectMessage`, kiểu body không khớp; thống nhất format trước khi triển khai.
- Với request–reply, JMSCorrelationID giúp liên kết luồng, nhưng nó không tự giải quyết schema/DTO mapping.

### 8.1. Có nên dùng `JmsMessagingTemplate` hoặc `JmsClient`?

- `JmsTemplate` là API cốt lõi dễ thấy rõ Spring JMS `MessageConverter`.
- `JmsMessagingTemplate` dùng tầng Spring Messaging và có cơ chế converter/header mapping riêng.
- Spring Framework **7.0** bổ sung `JmsClient` theo phong cách fluent; nó dựa trên `JmsTemplate` nhưng thiên về `org.springframework.messaging.Message`.
- Không thể lấy bean `org.springframework.jms.support.converter.JacksonJsonMessageConverter` rồi mặc nhiên xem nó là `org.springframework.messaging.converter.MessageConverter`. Khi chuyển abstraction, kiểm tra conversion chain và cấu hình phù hợp.

Bài học này dùng `JmsTemplate` để tránh trộn hai SPI. Với một dự án Boot 4 mới có `JmsClient`, lựa chọn API là chuyện riêng với lựa chọn định dạng JSON trên wire.

## 9. Chọn cách vận hành type ID an toàn và lâu dài

### 9.1. Tại sao `setTypeIdPropertyName` quan trọng?

Converter JSON cần biết **Java type đích** ở lần `fromMessage`. Với `MappingJackson2MessageConverter`/`JacksonJsonMessageConverter`, cấu hình `setTypeIdPropertyName("_type")` làm producer ghi loại dữ liệu vào JMS property và consumer đọc để tìm class phù hợp.

Nếu không đặt, phương thức `toMessage` có thể vẫn tạo JSON, nhưng nhận theo `fromMessage` có thể báo không tìm thấy type id, vì converter **không có đủ thông tin chọn DTO**. Đây là lỗi thường gặp khi chỉ test send mà chưa test nhận.

### 9.2. Vì sao alias tốt hơn FQCN?

**Kém ổn định:**

~~~text
_type = "com.example.internal.dto.OrderCreated"
~~~

**Bền hơn:**

~~~text
_type = "order-created.v1"
~~~

Việc rename package, tách module, di chuyển class hoặc consumer không viết bằng Java sẽ ít ảnh hưởng hơn với alias ổn định. Khi version mới không tương thích, dùng alias mới `order-created.v2` và duy trì bản đồ kiểu tương ứng trong giai đoạn migration.

Không nhất thiết alias phải nằm trong body; nó có thể là JMS application property. Nhưng phải thống nhất consumer nào có quyền đọc và lọc property này.

### 9.3. Trusted packages, alias map và kiểm soát producer

`setTrustedPackages("demo")` giới hạn việc resolve **class name được nêu trực tiếp** trong message khi không khớp một alias được định nghĩa. Vì vậy:
- **Alias map phải hữu hạn và được review**; đừng tự động quét classpath rồi mở tất cả DTO.
- **Không đưa message type do input người dùng chỉ định vào map động**.
- Với broker chia sẻ hoặc producer không tin cậy, hạn chế JMS `send` ACL trên queue, payload size, version và format; không tin mọi nội dung mang `_type` hợp lệ.
- Tránh polymorphic default typing Jackson không kiểm soát và native Java object deserialization trên payload không tin cậy.
- Áp dụng patch Spring/Jackson, scan dependencies và kiểm tra version thật của `spring-jms` trong dependency tree.

Các cơ chế này giải quyết các rủi ro khác nhau: **alias map** định nghĩa contract, **trusted packages** hạn chế dynamic resolution, **broker ACL** xác định ai được gửi/nhận, **validation** kiểm tra nội dung nghiệp vụ. Không cái nào thay thế hoàn toàn cái còn lại.

## 10. Versioning: DTO thay đổi thì sao?

Giả sử phiên bản v1:

~~~json
{
  "eventId": "e-001",
  "orderId": "O-42",
  "amountCents": 12500
}
~~~

v2 thêm field:

~~~json
{
  "eventId": "e-001",
  "orderId": "O-42",
  "amountCents": 12500,
  "currency": "VND"
}
~~~

Nếu consumer v1 không biết `currency`, có ba chiến lược:
1. **Tolerant reader:** bỏ qua field mới, nhưng phải kiểm tra cấu hình mapper và việc field mới có thực sự optional hay không.
2. **Tách alias:** gửi `order-created.v2`, consumer nâng cấp mapping để nhận cả v1/v2 trong giai đoạn chuyển tiếp.
3. **Versioned envelope:** tách event envelope có `schemaVersion`/`eventType` ra khỏi payload để chọn decoder và validate một cách tường minh.

Đừng nhầm **Spring Framework 7** với **business schema version 7**. Version converter/Jackson là sự lựa chọn nội bộ; producer Boot 3 và consumer Boot 4 có thể trao đổi dữ liệu với nhau **nếu cùng contract JSON/JMS properties**. Cùng Java class không bắt buộc; cùng ngôn ngữ Java cũng không bắt buộc.

### 10.1. Thay đổi tương thích/ngược không phải lúc nào cũng hiển nhiên

| Thay đổi | Rủi ro | Chiến lược |
| --- | --- | --- |
| Thêm field optional | Consumer cũ có thể từ chối unknown properties | Chính sách bỏ qua field chưa biết + test |
| Đổi tên `orderId` thành `id` | Consumer cũ không đọc được | Hỗ trợ alias, giai đoạn dual-write/dual-read |
| Đổi `amountCents` từ `long` sang `double` | Sai khác số tiền/precision | Giữ đơn vị và kiểu số ổn định |
| Đổi đơn vị tiền từ cent sang đồng | Cùng field, ý nghĩa khác | Field mới/schema version mới, migration rõ |
| Xóa field consumer đang cần | Thiếu dữ liệu/validation fail | Deprecation period, monitoring |
| Thêm subtype được chọn theo `_type` | Rủi ro deserialization và contract mới | Mapping allowlist + trusted packages |
| Thay Jackson 2 bằng Jackson 3 | JSON/naming/date/config có thể khác | Golden messages + cross-version tests |

Thiết lập fixtures JSON thực tế, kiểm tra wire content và consumer decode trên mọi cặp phiên bản cần hỗ trợ. Không chỉ biên dịch code của từng app rồi kết luận hai app tương thích.

## 11. Tình huống chuyển từ Spring Boot 3 sang Boot 4

Một kế hoạch chuyển đổi an toàn:

1. **Kiểm kê dependencies**: Boot version, Spring Framework/spring-jms, Jakarta Messaging, Jackson modules, Artemis JMS client, custom converter và listener factory.
2. **Chốt contract trước**: wire JSON, `MessageType.TEXT`, alias `_type`, schemaVersion, message selectors, naming/timezone/null handling.
3. **Vá bảo mật nhánh hiện tại**: đặc biệt với Spring 6.2.19+ nếu queue có producer không tin cậy.
4. **Thêm integration tests Boot 3 producer ↔ Boot 4 consumer** và ngược lại trên queue test; kiểm tra payload lẫn properties.
5. **Đổi converter Java API**: `MappingJackson2MessageConverter` → `JacksonJsonMessageConverter`, thay Jackson 2 mapper APIs bằng Jackson 3 tương ứng.
6. **Chuyển import Jackson** khi cần: lõi Jackson 3 là `tools.jackson.*`; Jackson annotations vẫn ở `com.fasterxml.jackson.annotation`.
7. **Giữ alias không đổi** nếu schema giữ nguyên, để consumer cũ còn nhận được message.
8. **Triển khai theo thứ tự tương thích**: consumer hỗ trợ định dạng cũ/mới trước, rồi mới bật producer format mới; bảo đảm có rollback plan.
9. **Theo dõi lỗi convert**: number of messages rejected, missing `_type`, unknown type alias, invalid JSON, schema mismatch, DLQ và replay.
10. **Dọn phụ thuộc legacy** khi mọi service đã chuyển, tránh tồn tại hai Jackson generations ngoài chủ ý.

**Không trộn các bean converter trong cùng một application context mà không chỉ định rõ dùng cái nào.** Nếu có nhiều `MessageConverter` bean cùng type interface, auto-configuration có thể thiếu một bean duy nhất để chọn; Spring có thể yêu cầu `@Primary`/`@Qualifier` hoặc cấu hình explicit trên từng template/factory.

## 12. Lỗi thường gặp khi DTO không chuyển được thành JSON

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `convertAndSend(dto)` tạo `ObjectMessage`, không phải JSON | Đang dùng `SimpleMessageConverter` | Đăng ký Jackson JMS converter |
| `NoClassDefFoundError: javax.jms...` | Thư viện Spring 5/JMS cũ dùng `javax.jms` trong app Boot 3/4 | Căn chỉnh `jakarta.jms` client và dependencies |
| `ClassNotFoundException: JacksonJsonMessageConverter` | App dùng Spring Framework 6 hoặc spring-jms chưa có class 7.0 | Dùng `MappingJackson2MessageConverter` trong Spring 6, không copy API 7 |
| `NoClassDefFoundError: com.fasterxml.jackson.databind...` | Dùng class Jackson 2 trong môi trường chỉ có Jackson 3 | Đổi sang converter/mapper Jackson 3 hoặc bổ sung dependency phù hợp |
| `NoClassDefFoundError: tools.jackson...` | Dùng Jackson 3 converter nhưng thiếu Jackson 3 runtime | Thêm `spring-boot-starter-jackson` hoặc thư viện Jackson 3 |
| Producer gửi được, consumer không giải mã | Không cấu hình `_type` hoặc không có mapping tương ứng | `setTypeIdPropertyName` và `setTypeIdMappings` thống nhất hai đầu |
| `MessageConversionException` về untrusted package | Type ID động không thuộc allowlist | Không bỏ allowlist; sửa alias/mapping hoặc cấu hình package được phép |
| Consumer mong `TextMessage` nhưng thấy `BytesMessage` | Converter mặc định dùng BYTES | `setTargetType(MessageType.TEXT)` ở producer, thống nhất wire contract |
| `@JmsListener` nhận `String` thay vì DTO | Container dùng converter khác, hoặc method signature không khớp | Cấu hình listener factory và chọn đúng converter |
| JSON field ngày giờ sai | Mapper khác module/format/zone | Đồng bộ Jackson modules và schema; test timestamp mẫu |
| Lỗi serialize record/DTO | Constructor, field visibility, module hoặc builder không phù hợp | Unit test mapper và DTO riêng, kiểm tra Jackson generation |
| Mã `_type` thay đổi sau refactor package | Type ID phụ thuộc Java FQCN | Dùng alias ổn định thay vì classname |
| Payload JSON hợp lệ nhưng nghiệp vụ từ chối | Field bắt buộc/null/number/schemaVersion sai | Validation + contract/schema tests |

### 12.1. Vì sao không sửa bằng cách “bỏ converter”?

Nếu bạn thay `convertAndSend(dto)` thành `convertAndSend(objectMapper.writeValueAsString(dto))`, body có thể là JSON, nhưng ở consumer, `SimpleMessageConverter` thường trả về **String** chứ không phải `OrderCreated`. Cách này **có thể hợp lệ** nếu các service chủ động quản lý serialization/deserialization ngoài Spring JMS converter. Nhưng không được giả định listener tự ánh xạ `String JSON` thành DTO.

Nếu chọn manual JSON, hãy ghi rõ phương pháp:
- Producer dùng Jackson serialize DTO → String, gửi `TextMessage`.
- Consumer nhận String → Jackson deserialize theo **schema/type cố định**, không tin raw class name từ message.
- Quản lý encoding/mapper/date/timezone, versioning và security.
- Không trộn một consumer dùng manual parse với một consumer kỳ vọng JMS converter tự động ở cùng queue mà chưa test.

### 12.2. Không tự ý đụng QoS

`MessageConverter` quyết định **body và một số metadata type-id**; nó không phải nơi điều khiển delivery mode, priority hay expiration. `JMSDeliveryMode`/`JMSPriority`/`JMSExpiration` do producer/provider áp dụng khi send. Nếu cần QoS, cấu hình producer/template/send operation riêng. Đừng set `message.setJMSExpiration(...)` trong converter rồi kỳ vọng TTL được giữ.

### 12.3. Cẩn thận với retry và dead-letter

Lỗi conversion lúc nhận có thể làm listener rollback và broker redeliver liên tục. Cần giới hạn retry, đưa message không hợp lệ vào DLQ theo broker policy, đo số lần retry và có hướng xử lý an toàn. Với message lỗi schema vĩnh viễn, retry vô hạn không giúp message hợp lệ. **Không xóa message production hoặc sửa trực tiếp payload** chỉ vì một bản converter mới không parse được, nếu chưa có kế hoạch đối soát/replay.

## 13. Checklist QA trước khi đưa vào production

- [ ] Đã xác định chính xác **Boot/Framework/Jackson/JMS provider** version và namespace `javax.jms`/`jakarta.jms`.
- [ ] Đã chọn đúng **Spring JMS converter package**, không nhầm với Spring Messaging converter.
- [ ] Với Boot 3: Jackson 2 + `MappingJackson2MessageConverter`; với Boot 4: Jackson 3 + `JacksonJsonMessageConverter`.
- [ ] Đã áp dụng bản vá bảo mật thích hợp; không sử dụng converter JMS nhận type không tin cậy trên Spring version chưa vá.
- [ ] Có `setTargetType(MessageType.TEXT)` nếu wire contract yêu cầu JSON TextMessage.
- [ ] Có `setTypeIdPropertyName` và alias mapping cố định cho consumer deserialize.
- [ ] Có kiểm soát type alias, `trustedPackages`, broker ACL và payload validation.
- [ ] Converter được gắn đúng vào JmsTemplate và listener container thực tế.
- [ ] SchemaVersion, eventType/eventId, JSON naming, timezone, null handling được ghi trong contract.
- [ ] Test converter hai chiều với DTO hợp lệ, JSON sai, thiếu field, alias lạ và field mới.
- [ ] Test tích hợp có broker thật/isolated container; producer/consumer cross-version khi migration.
- [ ] Có DLQ/backoff/idempotency khi consumer không đọc được JSON hoặc xử lý lỗi.
- [ ] Kiểm tra dependencies không vô tình kéo cả Jackson 2 và 3 hoặc hai loại JMS namespace ngoài chủ đích.

### Câu hỏi tự kiểm tra

1. Tại sao có `jackson-databind` trên classpath chưa đủ để `JmsTemplate.convertAndSend(OrderCreated)` tự tạo JSON?
2. Khi dùng Spring Boot 3.5.x, class JMS JSON converter nào phù hợp, và vì sao ví dụ Spring 7 không copy nguyên được?
3. Sự khác biệt giữa `org.springframework.jms.support.converter.MessageConverter` và `org.springframework.messaging.converter.MessageConverter` là gì?
4. Vì sao `MappingJackson2MessageConverter`/`JacksonJsonMessageConverter` mặc định gửi `BytesMessage`, và khi nào cần `MessageType.TEXT`?
5. Điều gì xảy ra nếu producer gửi JSON nhưng consumer thiếu `_type` hoặc ánh xạ alias?
6. Vì sao type alias `order-created.v1` tốt hơn tên Java class `demo.OrderCreated` trên wire?
7. Vì sao cần `setTrustedPackages` với converter JMS trên Spring 7.0.8+ hoặc Spring 6.2.19+ khi nhận message có nguồn không tin cậy?
8. Boot 3 producer và Boot 4 consumer có thể giao tiếp qua JMS mà không dùng cùng Jackson major version không?
9. Nếu schema thêm field `currency`, kiểm thử nào cần có trước khi đưa event v2 vào queue chung?
10. Nếu listener nhận message JSON sai rồi rollback liên tục, delivery mode persistent có tự khắc phục lỗi conversion không?

**Ghi nhớ:** DTO → JSON trong JMS là bài toán **converter + wire format + type/schema contract + version alignment + trust boundary**, không phải một dòng `convertAndSend`. Với **Spring Framework 6 / Boot 3**, dùng Jackson 2 và `MappingJackson2MessageConverter`; với **Framework 7 / Boot 4**, ưu tiên Jackson 3 và `JacksonJsonMessageConverter`. Duy trì alias ổn định, kiểm soát gói tin được tin cậy và kiểm thử xuyên phiên bản để nâng cấp không làm gián đoạn producer/consumer.

## Tài liệu tham khảo

1. Spring Framework 7 – Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
2. Spring Framework 6.2 – `MappingJackson2MessageConverter` API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
3. Spring Framework 7.0 – `JacksonJsonMessageConverter` API: https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html
4. Spring Boot 4 – JMS and Artemis: https://docs.spring.io/spring-boot/4.0/reference/messaging/jms.html
5. Spring Boot 4 – JSON/Jackson 3: https://docs.spring.io/spring-boot/4.0/reference/features/json.html
6. Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
7. Spring Framework Security Advisory, CVE-2026-41855: https://spring.io/security/cve-2026-41855/
8. Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
