# Chuyển đổi JSON theo thư viện và phiên bản Spring đang dùng

Trong Spring Messaging, JSON là một định dạng trao đổi của payload. Để chuyển một Java object thành JSON khi gửi và khôi phục JSON thành object khi nhận, ứng dụng cần một **MessageConverter** tương thích với thư viện JSON và phiên bản Spring đang dùng.

Không nên chọn converter chỉ dựa vào tên thư viện có trong classpath. Cần xác định rõ ba yếu tố:

1. Phiên bản Spring Framework hoặc Spring Boot đang quản lý ứng dụng.
2. Thư viện JSON và major version đang dùng, chẳng hạn Jackson 2, Gson hoặc JSON-B.
3. Tầng chuyển đổi: Spring Messaging, JMS, Kafka, AMQP hay HTTP. Mỗi tầng có thể có một interface converter riêng.

Bài này tập trung vào **Spring Messaging** và cách dùng Jackson 2 với **MappingJackson2MessageConverter**, sau đó chỉ ra những điểm cần điều chỉnh khi dự án dùng thư viện hoặc dòng Spring khác.

## 1. MessageConverter trong Spring Messaging

Spring Messaging biểu diễn thông điệp bằng **Message<?>**, gồm payload và headers. Payload có thể là object Java, chuỗi hoặc mảng byte. Khi message đi qua ranh giới process hoặc network, payload thường phải được chuyển sang định dạng có thể truyền đi, ví dụ JSON bytes.

Interface **org.springframework.messaging.converter.MessageConverter** có hai thao tác chính:

- **toMessage(payload, headers):** chuyển object ứng dụng thành Spring Message.
- **fromMessage(message, targetClass):** chuyển payload trong Spring Message thành kiểu Java mà consumer yêu cầu.

Luồng gửi và nhận:

~~~text
Producer object
      |
      | toMessage(...)
      v
Spring Message
  payload: JSON String / byte[]
  headers: contentType, ...
      |
      | channel / adapter / transport
      v
Consumer Spring Message
      |
      | fromMessage(...)
      v
Target Java object
~~~

Một converter chịu trách nhiệm chuyển đổi payload và có thể dùng headers để xác định định dạng. Converter không tự gửi message qua broker, không chọn queue/topic và không thay thế serializer của mọi transport. Channel, adapter và transport vẫn chịu trách nhiệm giao nhận.

### Các converter cơ bản và JSON

Spring Messaging có các converter phục vụ những kiểu payload khác nhau:

| Converter | Dữ liệu chính | Công dụng |
|---|---|---|
| **StringMessageConverter** | String | Chuyển văn bản thành message và ngược lại. Không tự parse JSON thành DTO. |
| **ByteArrayMessageConverter** | byte[] | Giữ payload ở dạng bytes, phù hợp khi tầng khác chịu trách nhiệm serialize/deserialize. |
| **SimpleMessageConverter** | Một số kiểu đơn giản | Chuyển đổi các kiểu payload đơn giản được hỗ trợ; không phải JSON object mapper. |
| **MappingJackson2MessageConverter** | Java object và JSON | Dùng Jackson 2 để serialize object và deserialize JSON thành target type. |

Tên class và package rất quan trọng. **org.springframework.messaging.converter.MappingJackson2MessageConverter** là converter cho Spring Messaging. Các module Spring khác cũng có converter JSON riêng nhưng không nhất thiết triển khai cùng interface.

## 2. Chọn thư viện JSON theo dự án

### Jackson 2

Jackson 2 thường được dùng với Spring Messaging qua:

- **com.fasterxml.jackson.databind.ObjectMapper**
- **org.springframework.messaging.converter.MappingJackson2MessageConverter**
- Các module bổ sung như **jackson-datatype-jsr310** cho Java Time.

**ObjectMapper** quyết định cách JSON được đọc và ghi: tên field, naming strategy, định dạng ngày giờ, enum, null, unknown properties và các quy tắc khác. Nên cấu hình một mapper dùng chung cho ứng dụng thay vì tạo mapper mới cho từng message.

Ví dụ cấu hình Java Time:

~~~java
ObjectMapper objectMapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

**JavaTimeModule** giúp Jackson xử lý các kiểu như **Instant**, **LocalDate** và **LocalDateTime**. Tắt **WRITE_DATES_AS_TIMESTAMPS** giúp ngày giờ được biểu diễn dưới dạng chuỗi ISO thay vì số hoặc mảng theo cấu hình mặc định.

### Gson hoặc JSON-B

Nếu dự án dùng Gson hoặc JSON-B, hãy kiểm tra converter được cung cấp bởi đúng module Spring hoặc thư viện tích hợp. Không nên giả định rằng chỉ cần thêm dependency Gson/JSON-B thì **MappingJackson2MessageConverter** sẽ tự chuyển sang dùng thư viện đó.

Nếu Spring Messaging core không có converter phù hợp trong phiên bản đang dùng, có thể viết một adapter triển khai **MessageConverter** để gọi Gson hoặc JSON-B. Adapter cần xử lý ít nhất:

- Chuyển payload object thành JSON.
- Chuyển JSON thành target type.
- Đọc và ghi **contentType**.
- Xử lý payload dạng String hoặc byte[] theo hợp đồng đã chọn.
- Báo lỗi conversion rõ ràng khi JSON không hợp lệ hoặc target type không tương thích.

Không trộn object mapper của nhiều thư viện trong cùng một luồng nếu chưa có lý do cụ thể. Khác biệt về naming, date/time, enum và unknown fields có thể làm producer và consumer diễn giải cùng JSON theo cách khác nhau.

## 3. Phiên bản Spring và tương thích thư viện

Spring Framework và thư viện JSON có vòng đời phiên bản riêng. Chọn phiên bản phải theo dependency management của ứng dụng, không chỉ theo phiên bản mới nhất của từng thư viện.

| Dòng ứng dụng | Điểm cần kiểm tra |
|---|---|
| Spring Framework 5.3.x | Dùng đúng API của Spring 5.3 và phiên bản Jackson 2 tương thích. Spring 5.3 hỗ trợ các baseline Java cũ hơn Spring 6; không bê nguyên cấu hình Java 17 của dự án Spring 6 vào ứng dụng Java cũ. |
| Spring Framework 6.x | Yêu cầu Java 17 trở lên. Converter Spring Messaging dùng Jackson 2 có tên **MappingJackson2MessageConverter**; các lớp Jackson 2 thuộc namespace **com.fasterxml.jackson.***. |
| Spring Boot | Ưu tiên BOM/dependency management của đúng dòng Boot để căn chỉnh Spring Framework và Jackson. Tránh tự ghim từng module Spring ở các phiên bản khác nhau. |
| Dự án dùng Jackson 3 hoặc một major Spring mới hơn | Kiểm tra converter và package được hỗ trợ trong đúng release. Jackson 3 có API/package khác Jackson 2; không truyền **ObjectMapper** của Jackson 2 vào converter yêu cầu Jackson 3 hoặc ngược lại. |

Đối với ví dụ bên dưới, phiên bản được ghim cụ thể là **Spring Messaging 6.1.8, Jackson 2.17.1 và Java 17**. Đây là một bộ phiên bản minh họa để code có thể tái lập; dự án thực tế nên dùng các phiên bản đã được kiểm tra tương thích trong BOM hoặc build của chính dự án.

### Vì sao không nên nâng từng dependency riêng lẻ?

Một ứng dụng có thể gặp các lỗi như:

- **NoSuchMethodError** khi một module Spring được biên dịch với API khác phiên bản runtime.
- **ClassNotFoundException** hoặc **NoClassDefFoundError** khi thiếu module Jackson cần thiết.
- **NoSuchMethodError** hoặc lỗi linkage khi trộn Jackson major versions.
- **MessageConversionException** khi converter không đọc được payload hoặc target type.
- Ngày giờ serialize được nhưng deserialize thất bại vì thiếu module Java Time hoặc format không thống nhất.

Khi nâng cấp, kiểm tra dependency tree và chạy kiểm thử serialize/deserialize ở cả producer lẫn consumer.

## 4. Content type và dạng payload được serialize

Header **contentType** cho biết payload được biểu diễn theo định dạng nào. Với JSON, giá trị thông dụng là **application/json**.

Ví dụ một Spring Message có thể mang:

~~~text
payload:
  {"orderId":"ORD-1001","amount":125.50}

headers:
  contentType: application/json
  id: ...
  timestamp: ...
~~~

**MappingJackson2MessageConverter** dùng content type và cấu hình converter để xác định liệu payload có thể được chuyển đổi hay không. Nên đặt content type rõ ràng khi tạo message, đặc biệt nếu message đi qua nhiều adapter hoặc hệ thống.

### String và byte[] là hai cách lưu JSON

Sau khi serialize, JSON có thể được giữ trong Spring Message dưới dạng:

- **String:** thuận tiện khi cần xem nội dung trực tiếp hoặc làm việc với API nhận văn bản.
- **byte[]:** phù hợp với nhiều transport vì payload đã ở dạng bytes.

**MappingJackson2MessageConverter** hỗ trợ cấu hình kiểu payload đã serialize. Trong ví dụ, đặt **String.class** để JSON xuất hiện dưới dạng chuỗi và output dễ quan sát. Nếu giữ mặc định byte array, khi debug cần decode bytes bằng charset phù hợp, thường là UTF-8.

Không được nhầm **StringMessageConverter** với JSON converter. StringMessageConverter có thể chuyển một chuỗi JSON thành message văn bản, nhưng nó không tự tạo **OrderCreated** từ chuỗi JSON. Việc parse thành DTO cần Jackson hoặc một JSON library khác.

## 5. Ví dụ đầy đủ: serialize và deserialize bằng Jackson 2

Ví dụ này dùng **MappingJackson2MessageConverter** để chuyển một Java record thành JSON String rồi đọc lại thành record. Nó chạy độc lập trong JVM, không cần broker, WebSocket hay Spring application context.

### Cấu trúc project

~~~text
json-message-demo/
  pom.xml
  src/
    main/
      java/
        com/
          example/
            messaging/
              JsonMessageExample.java
~~~

### Maven dependencies

Tạo **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>json-message-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.1.8</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.1</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.datatype</groupId>
            <artifactId>jackson-datatype-jsr310</artifactId>
            <version>2.17.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Java source

Tạo **src/main/java/com/example/messaging/JsonMessageExample.java**:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

public class JsonMessageExample {

    public record OrderCreated(
            String orderId,
            BigDecimal amount,
            Instant occurredAt
    ) {
    }

    public static void main(String[] args) {
        ObjectMapper objectMapper = new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter(objectMapper);

        // Chọn String để payload JSON có thể đọc trực tiếp trong ví dụ.
        converter.setSerializedPayloadClass(String.class);

        OrderCreated event = new OrderCreated(
                "ORD-1001",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z")
        );

        MessageHeaders headers = new MessageHeaders(Map.of(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        ));

        Message<?> jsonMessage = converter.toMessage(event, headers);
        if (jsonMessage == null) {
            throw new IllegalStateException("Converter rejected the payload");
        }

        String json = (String) jsonMessage.getPayload();

        OrderCreated restored = (OrderCreated) converter.fromMessage(
                jsonMessage,
                OrderCreated.class
        );
        if (restored == null) {
            throw new IllegalStateException("Converter could not read the JSON");
        }

        System.out.println("contentType="
                + jsonMessage.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("json=" + json);
        System.out.println("restored=" + restored);
    }
}
~~~

### Chạy chương trình

Từ thư mục chứa **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.JsonMessageExample
~~~

Output:

~~~text
contentType=application/json
json={"orderId":"ORD-1001","amount":125.50,"occurredAt":"2026-11-07T03:00:00Z"}
restored=OrderCreated[orderId=ORD-1001, amount=125.50, occurredAt=2026-11-07T03:00:00Z]
~~~

Giải thích:

1. **ObjectMapper** được cấu hình với **JavaTimeModule** để xử lý **Instant**.
2. **MappingJackson2MessageConverter** dùng ObjectMapper đó để serialize và deserialize.
3. **setSerializedPayloadClass(String.class)** yêu cầu converter lưu JSON dưới dạng String trong payload.
4. **MessageHeaders** đặt **contentType** là **application/json**.
5. **toMessage** tạo Spring Message từ record.
6. **fromMessage** đọc JSON payload và tạo lại **OrderCreated**.
7. Kiểm tra output cho thấy thời điểm, mã đơn hàng và số tiền được giữ nguyên qua vòng round-trip.

Ví dụ này kiểm tra conversion trong bộ nhớ. Nó chưa gửi JSON qua broker; adapter hoặc transport thực tế vẫn cần cấu hình serialization, destination và delivery semantics riêng.

## 6. Tùy chỉnh ObjectMapper theo contract JSON

Cấu hình ObjectMapper phải nhất quán giữa producer và consumer. Nếu hai phía dùng quy tắc khác nhau, JSON có thể hợp lệ về cú pháp nhưng vẫn không deserialize đúng.

### Tên field

Có thể dùng annotation Jackson để giữ tên field trong JSON ổn định:

~~~java
public record CustomerEvent(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("display_name") String displayName
) {
}
~~~

Khi đó JSON dùng **customer_id** và **display_name** dù tên thành phần Java là camelCase.

### Trường không biết và tương thích phiên bản

Khi consumer nhận JSON có thêm field mới, chính sách **FAIL_ON_UNKNOWN_PROPERTIES** quyết định Jackson có từ chối hay bỏ qua field không được ánh xạ. Nếu cần hỗ trợ producer nâng cấp độc lập với consumer, hãy chọn chính sách tương thích có chủ đích và kiểm thử.

Không nên tắt mọi kiểm tra một cách mặc định. Các field bắt buộc, enum mới, kiểu số và định dạng ngày giờ vẫn có thể gây lỗi hoặc tạo dữ liệu sai nếu không được xác thực.

### Ngày giờ

- Dùng **Instant** cho một mốc thời gian tuyệt đối.
- Dùng **LocalDate** cho ngày lịch không có thời gian.
- Dùng **OffsetDateTime** khi cần giữ offset.
- Chỉ dùng **LocalDateTime** khi hợp đồng thực sự không gắn múi giờ và hai phía đã thống nhất ý nghĩa.

Không nên gửi một chuỗi ngày giờ không có timezone rồi giả định mọi service sẽ diễn giải giống nhau.

### Enum và giá trị số

Quy định cách biểu diễn enum ổn định. Nếu dùng ordinal, việc đổi thứ tự enum có thể làm dữ liệu cũ bị diễn giải sai; thường nên dùng tên hoặc code ổn định. Với tiền, dùng **BigDecimal** thay cho **double** để tránh sai số dấu phẩy động.

### Bảo mật khi deserialize

Không bật Jackson default typing rộng cho dữ liệu đến từ hệ thống không tin cậy. Polymorphic deserialization có thể tạo rủi ro nếu cho phép kiểu tùy ý. Nếu cần đa hình, dùng subtype allowlist và contract rõ ràng; xác thực payload trước khi đưa vào logic nghiệp vụ.

## 7. Khi nào cần converter khác hoặc adapter riêng?

### Dùng converter Spring Messaging

Dùng **MappingJackson2MessageConverter** khi:

- Message đang dùng **org.springframework.messaging.Message<?>**.
- Payload cần chuyển thành JSON bằng Jackson 2.
- Ứng dụng muốn kiểm soát ObjectMapper, content type và dạng payload String/byte[].

### Dùng converter của JMS, Kafka hoặc AMQP

Các tầng transport có API chuyển đổi riêng. Ví dụ:

- Spring JMS có **org.springframework.jms.support.converter.MessageConverter** để chuyển object ứng dụng với **jakarta.jms.Message**.
- Spring Kafka có serializer/deserializer cho key và value của Kafka record; đây không phải Spring Messaging **MessageConverter**.
- Spring AMQP có **org.springframework.amqp.support.converter.MessageConverter** để chuyển payload với AMQP message.

Dù các converter có thể cùng dùng Jackson, chúng không thể thay thế trực tiếp cho nhau vì message model và lifecycle khác nhau. Hãy dùng converter đúng tầng, hoặc xây dựng adapter rõ ràng giữa Spring Message và transport message.

### Dùng thư viện JSON khác

Nếu ứng dụng chuẩn hóa Gson hoặc JSON-B, triển khai **MessageConverter** phù hợp hoặc dùng adapter đã được module tích hợp hỗ trợ. Khi tự viết converter, nên kiểm tra:

- Chỉ chấp nhận MIME type được hỗ trợ, chẳng hạn **application/json**.
- Chuyển đổi đúng giữa String/byte[] và target class.
- Charset được quy định rõ, ưu tiên UTF-8.
- Lỗi parse được chuyển thành exception có nguyên nhân gốc.
- Header **contentType** được giữ nhất quán.
- Có test cho null, payload rỗng, field thiếu, field thừa và JSON sai cú pháp.

## 8. Kiểm thử conversion

Không nên chỉ kiểm tra rằng **toMessage** không ném exception. Một bài test tốt phải chứng minh payload JSON và object sau khi đọc lại có ý nghĩa tương đương.

Các trường hợp nên kiểm tra:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Round-trip DTO | Serialize rồi deserialize vẫn giữ các giá trị nghiệp vụ. |
| Content type | Message có **application/json** như contract yêu cầu. |
| Java Time | **Instant**, **LocalDate** hoặc kiểu thời gian được đọc/ghi đúng. |
| BigDecimal | Scale và giá trị tiền được giữ đúng theo yêu cầu. |
| Field mới | Consumer cũ xử lý field mới theo chính sách tương thích đã chọn. |
| Field bắt buộc bị thiếu | Conversion hoặc validation từ chối với thông báo rõ ràng. |
| JSON không hợp lệ | Lỗi parse được phát hiện và đi vào error handling. |
| Payload không đúng kiểu | Converter từ chối hoặc trả lỗi rõ ràng, không ép kiểu mù quáng. |
| Charset | JSON bytes được encode/decode nhất quán, thường là UTF-8. |

Với Spring Integration hoặc listener container, cần thêm integration test để xác nhận converter được đăng ký đúng endpoint và lỗi được chuyển theo error flow dự kiến. Unit test của ObjectMapper không chứng minh cấu hình adapter đã đúng.

## 9. Lỗi thường gặp

1. **Thêm Jackson dependency nhưng payload vẫn là String.** StringMessageConverter hoặc converter khác có thể đang được chọn. Cần kiểm tra converter thực tế trong chain.
2. **Dùng sai package MappingJackson2MessageConverter.** Spring Messaging, Spring JMS và các module khác có converter riêng; import sai có thể khiến method signature hoặc semantics không đúng.
3. **Không đặt contentType.** Converter có thể không chọn đúng MIME type hoặc message đi qua adapter bị hiểu sai định dạng.
4. **Thiếu JavaTimeModule.** Jackson không biết cách xử lý một số kiểu java.time nếu mapper chưa đăng ký module tương ứng.
5. **Producer và consumer dùng ObjectMapper khác nhau.** Naming strategy, date format, enum và unknown-field policy có thể khác nhau.
6. **Nhầm conversion với transport.** toMessage tạo Spring Message; nó không gửi message đến Kafka, JMS hay WebSocket.
7. **Trộn Jackson 2 và Jackson 3.** Package, ObjectMapper và converter phải thuộc cùng major version được Spring release hỗ trợ.
8. **Gửi trực tiếp JPA entity.** Entity có thể mang lazy relationship, proxy và field nội bộ. Dùng DTO/event contract riêng.
9. **Không kiểm tra schema evolution.** Thêm, đổi hoặc xóa field có thể phá consumer đang chạy phiên bản cũ.
10. **Bật polymorphic default typing không giới hạn.** Có thể tạo rủi ro deserialize kiểu không mong muốn từ payload không tin cậy.

## 10. Ghi nhớ

- **MessageConverter** của Spring Messaging chuyển payload thành Message và Message thành target object.
- **MappingJackson2MessageConverter** dùng Jackson 2; ObjectMapper quyết định quy tắc JSON.
- Đặt **contentType=application/json** và thống nhất schema giữa producer/consumer.
- **StringMessageConverter** xử lý văn bản; nó không thay thế JSON object mapper.
- Dùng **JavaTimeModule** khi contract có kiểu Java Time và chọn định dạng thời gian có timezone rõ ràng.
- Chọn Spring/Jackson versions theo BOM hoặc dependency management của dự án; không trộn module khác major version.
- JMS, Kafka và AMQP có converter/serializer riêng; dùng đúng converter của tầng transport.
- Kiểm thử round-trip, schema compatibility, lỗi parse và cấu hình converter tại endpoint.

Khi thay đổi thư viện JSON hoặc nâng cấp Spring, hãy kiểm tra lại converter được đăng ký, ObjectMapper, content type, schema và bài test round-trip. Nhờ đó producer và consumer tiếp tục hiểu cùng một hợp đồng dữ liệu.
