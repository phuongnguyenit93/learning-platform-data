# Chuyển JSON thành POJO với converter tùy chỉnh

## 1. Bài toán thực hành

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), các bean `Supplier`, `Function` và `Consumer` chứa logic nghiệp vụ có thể được tra cứu qua `FunctionCatalog` và tái sử dụng qua HTTP, hệ thống sự kiện hoặc môi trường serverless. Một tính năng quan trọng của framework là **chuyển đổi thông điệp**: adapter có thể nhận JSON hoặc byte array, còn hàm nghiệp vụ vẫn làm việc với đối tượng Java đã có kiểu.

Phần lớn trường hợp chỉ cần JSON converter mặc định. Nhưng giả sử một hệ thống đối tác gửi đơn hàng bằng **hợp đồng JSON cũ**:

~~~json
{
  "order_id": "O-201",
  "amount_vnd": 1500000,
  "source_code": "PARTNER-A"
}
~~~

Trong Java, ta muốn dùng một POJO bất biến với tên thuộc tính theo quy ước camelCase:

~~~java
public record OrderRequest(
        String orderId,
        long amountVnd,
        String sourceCode) {
}
~~~

Ngoài ra, hệ thống phải nhận diện rõ media type của đối tác:

~~~http
Content-Type: application/vnd.textlab.order+json
~~~

Không nên sửa từng `Function` để đọc `Map<String,Object>`, thay khóa JSON bằng tay rồi ép kiểu. Ta sẽ tạo một **Spring Messaging `MessageConverter` tùy chỉnh** chỉ xử lý loại payload này, chuyển JSON `snake_case` thành `OrderRequest` trước khi hàm nghiệp vụ chạy.

~~~text
Message<byte[]>
  contentType = application/vnd.textlab.order+json
  payload = {"order_id":"O-201","amount_vnd":1500000,...}
            |
            v
 VendorOrderJsonConverter
  - kiểm tra MIME
  - kiểm tra target class
  - giới hạn kích thước
  - Jackson snake_case / strict JSON
            |
            v
 OrderRequest("O-201",1500000,"PARTNER-A")
            |
            v
 Function<OrderRequest, ClassificationResult>
            |
            v
 ClassificationResult("O-201","PRIORITY")
            |
            v
 Adapter xuất dữ liệu theo hợp đồng riêng
~~~

**Sau bài này, bạn sẽ làm được:**

1. Phân biệt `contentType` với **kiểu đối số Java đích**.
2. Viết `AbstractMessageConverter` có thể chuyển `byte[]`/`String` thành Java record.
3. Đăng ký converter dưới dạng `@Bean` để Spring Cloud Function sử dụng.
4. Xác minh trực tiếp `fromMessage` và `toMessage` cùng các trường hợp MIME sai, JSON hỏng, thiếu trường.
5. Test một `Message<byte[]>` đi qua `FunctionCatalog` và vào `Function<OrderRequest,ClassificationResult>`.
6. Hiểu phần nào thuộc converter, phần nào thuộc nghiệp vụ và phần nào vẫn phải kiểm thử ở adapter HTTP hoặc Spring Cloud Stream.

> **Giới hạn:** Bài này thực hiện lab qua JUnit/Spring context, chưa yêu cầu broker thật, web server hoặc serverless deployment. Các tệp Java, Maven và YAML bên dưới là **nội dung hướng dẫn cho người học**, không phải tệp được Worker tạo trực tiếp.

## 2. Cần custom converter trong trường hợp nào?

Trước khi viết code, hãy nhận diện đúng vấn đề:

| Tình huống | Cách xử lý phù hợp |
| --- | --- |
| JSON thông thường, trường `orderId` khớp POJO | JSON converter mặc định thường đủ |
| JSON dùng tên khác, chỉ vài trường | Xem xét `@JsonProperty` hoặc naming strategy của Jackson |
| Một đối tác dùng định dạng JSON và quy tắc khác biệt rõ ràng | Custom `MessageConverter` gắn với media type riêng có thể hợp lý |
| Dữ liệu phi JSON như CSV, Avro hay binary riêng | Converter cho đúng media type hoặc schema system phù hợp |
| Input không phải `Message` mà là một giá trị Java thường | `ConversionService` hoặc logic conversion riêng có thể tham gia |
| Cần quyết định nhận/từ chối đơn hàng | Đó là **logic nghiệp vụ**, không phải trách nhiệm của converter |

Spring Cloud Function sử dụng hai cơ chế chính: `MessageConverter` cho dữ liệu dạng Spring `Message`, còn `ConversionService` có thể xử lý một số đầu vào **không phải Message**. Converter tùy chỉnh trong bài **không** nhằm thay thế toàn bộ cơ chế chuyển đổi của Spring.

### 2.1. Hai thông tin cần có để chuyển đổi

Ví dụ một thông điệp được gửi vào catalog:

~~~text
contentType = application/vnd.textlab.order+json
target Java type = OrderRequest
~~~

- **`contentType`** cho biết cách hiểu các byte: loại dữ liệu của thông điệp.
- **`target Java type`** đến từ chữ ký `Function<OrderRequest, ClassificationResult>`: đối tượng phải tạo.

Chỉ dựa vào `contentType` là **chưa đủ** để chọn tùy ý một class để deserialize. Ngược lại, chỉ nhìn `OrderRequest` mà bỏ qua media type có thể khiến dữ liệu của đối tác bị đọc sai quy tắc.

### 2.2. Vì sao dùng media type riêng?

Lab sử dụng:

~~~text
application/vnd.textlab.order+json
~~~

Suffix `+json` cho biết đây là một loại JSON có cấu trúc riêng. Ta tách nó khỏi `application/json` để converter tùy chỉnh **không giành mọi message JSON** trong ứng dụng.

Custom converter được Spring Cloud Function thêm vào tập converter và **ưu tiên trước converter tích hợp**. Vì vậy, một converter hỗ trợ `application/json` quá rộng có thể vô tình thay đổi behavior của các hàm khác. Hạn chế theo **MIME và target class** là cách giảm ảnh hưởng ngoài dự kiến.

## 3. Môi trường và cấu trúc dự án

Lab minh họa bằng **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0** và **Spring Cloud 2025.0.0**. Đây là cặp phiên bản ban đầu đã công bố tương thích; khi làm dự án mới, hãy chọn các bản vá còn được hỗ trợ và BOM phù hợp thay vì tự ghép các thế hệ Spring khác nhau. Ví dụ sử dụng **Jackson 2** của Spring Boot 3.x; Spring Boot 4.x sử dụng thế hệ Jackson khác và có thể cần thay dependency/import.

Tạo cấu trúc:

~~~text
vendor-json-converter-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/vendorjson/
    │   │   ├── ConverterLabApplication.java
    │   │   ├── OrderRequest.java
    │   │   ├── ClassificationResult.java
    │   │   ├── OrderPolicy.java
    │   │   ├── VendorOrderJsonConverter.java
    │   │   └── ConverterFunctions.java
    │   └── resources/application.yml
    └── test/java/com/example/vendorjson/
        ├── OrderPolicyTest.java
        ├── VendorOrderJsonConverterTest.java
        └── ConverterFunctionCatalogTest.java
~~~

Tất cả class dưới đây nằm trong package `com.example.vendorjson`. Không cần thêm Kafka, RabbitMQ, database hay web endpoint để chạy các test cơ bản.

## 4. pom.xml: Spring Cloud Function và Jackson

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>vendor-json-converter-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <!-- Jackson 2 và JSON support trong thế hệ Spring Boot 3.x -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**Giải thích:**

- `spring-boot-starter` tạo application context và cơ chế auto-configuration thông thường.
- `spring-cloud-function-context` cung cấp `FunctionCatalog` và chuyển đổi kiểu.
- `spring-boot-starter-json` cung cấp Jackson trong thế hệ Boot 3.x để converter đọc/ghi JSON.
- `spring-boot-starter-test` phục vụ JUnit 5 và `@SpringBootTest`.
- BOM Spring Cloud quản lý phiên bản `spring-cloud-function-context`. Không nên ghi một version khác trên dependency này.

**Không cần** `spring-cloud-function-web` để chứng minh converter hoạt động trong Spring context. Việc bổ sung web hoặc binder là một bước tích hợp riêng ở cuối bài.

## 5. Viết POJO và quy tắc nghiệp vụ

### 5.1. Record OrderRequest

Tạo `OrderRequest.java`:

~~~java
package com.example.vendorjson;

public record OrderRequest(
        String orderId,
        long amountVnd,
        String sourceCode) {
}
~~~

Java record là POJO bất biến, có constructor, các accessor `orderId()`, `amountVnd()`, `sourceCode()` và tự sinh `equals/hashCode/toString`. Converter sẽ chịu trách nhiệm ánh xạ:

| JSON của đối tác | Java record |
| --- | --- |
| `order_id` | `orderId` |
| `amount_vnd` | `amountVnd` |
| `source_code` | `sourceCode` |

### 5.2. Record ClassificationResult

Tạo `ClassificationResult.java`:

~~~java
package com.example.vendorjson;

public record ClassificationResult(
        String id,
        String category) {
}
~~~

Kết quả sử dụng hai trường `id` và `category`. Đây là DTO nghiệp vụ; converter có thể serialize nó thành JSON ở đầu ra khi media type phù hợp.

### 5.3. Business policy không phụ thuộc JSON

Tạo `OrderPolicy.java`:

~~~java
package com.example.vendorjson;

public final class OrderPolicy {

    private OrderPolicy() {
    }

    public static ClassificationResult classify(OrderRequest order) {
        if (order == null) {
            throw new IllegalArgumentException("order must not be null");
        }
        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (order.sourceCode() == null || order.sourceCode().isBlank()) {
            throw new IllegalArgumentException("sourceCode is required");
        }
        if (order.amountVnd() < 0) {
            throw new IllegalArgumentException("amountVnd must be >= 0");
        }

        return new ClassificationResult(
                order.orderId(),
                order.amountVnd() >= 1_000_000L
                        ? "PRIORITY"
                        : "STANDARD");
    }
}
~~~

Ở đây, **converter chỉ đổi biểu diễn dữ liệu**. Kiểm tra điều kiện doanh nghiệp (đơn âm tiền, ID rỗng, nguồn trống, ngưỡng ưu tiên) nằm trong `OrderPolicy`. Nhờ vậy cùng `OrderPolicy.classify` có thể tái sử dụng với `OrderRequest` được tạo từ JSON mặc định, vendor JSON, lời gọi trực tiếp hoặc adapter khác.

## 6. Viết converter tùy chỉnh bằng AbstractMessageConverter

Tạo `VendorOrderJsonConverter.java`:

~~~java
package com.example.vendorjson;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.util.MimeType;

public final class VendorOrderJsonConverter
        extends AbstractMessageConverter {

    public static final MimeType VENDOR_JSON =
            new MimeType("application", "vnd.textlab.order+json");

    private static final int MAX_PAYLOAD_BYTES = 16 * 1024;

    private final ObjectMapper mapper;

    public VendorOrderJsonConverter() {
        super(VENDOR_JSON);

        // Chỉ nhận đúng media type đã đăng ký.
        setStrictContentTypeMatch(true);

        // toMessage ưu tiên trả payload dạng byte[].
        setSerializedPayloadClass(byte[].class);

        this.mapper = new ObjectMapper()
                .setPropertyNamingStrategy(
                        PropertyNamingStrategies.SNAKE_CASE)
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
                .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
                .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return OrderRequest.class.equals(clazz)
                || ClassificationResult.class.equals(clazz);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        Object payload = message.getPayload();
        byte[] bytes;

        if (payload instanceof byte[] data) {
            bytes = data;
        } else if (payload instanceof String text) {
            bytes = text.getBytes(StandardCharsets.UTF_8);
        } else {
            // Không hiểu biểu diễn này: để converter khác thử.
            return null;
        }

        if (bytes.length > MAX_PAYLOAD_BYTES) {
            throw new MessageConversionException(
                    message, "Vendor JSON exceeds 16 KiB");
        }

        try {
            return mapper.readValue(bytes, targetClass);
        } catch (JsonProcessingException ex) {
            throw new MessageConversionException(
                    message, "Invalid vendor order JSON", ex);
        }
    }

    @Override
    protected Object convertToInternal(
            Object payload,
            MessageHeaders headers,
            Object conversionHint) {

        if (!supports(payload.getClass())) {
            return null;
        }

        try {
            byte[] bytes = mapper.writeValueAsBytes(payload);
            if (bytes.length > MAX_PAYLOAD_BYTES) {
                throw new MessageConversionException(
                        "Serialized vendor JSON exceeds 16 KiB");
            }
            return bytes;
        } catch (JsonProcessingException ex) {
            throw new MessageConversionException(
                    "Cannot serialize vendor JSON", ex);
        }
    }
}
~~~

### 6.1. Vì sao kế thừa AbstractMessageConverter?

`org.springframework.messaging.converter.AbstractMessageConverter` đã cung cấp phần khung của `MessageConverter`, ví dụ:

- Nhận diện MIME type được hỗ trợ.
- Kiểm tra xem class đích có thuộc tập hỗ trợ không.
- Gọi `convertFromInternal` để tạo đối tượng từ message.
- Gọi `convertToInternal` khi cần tạo message từ đối tượng.

Ta chỉ khai báo **media type, tập class và thuật toán chuyển đổi**. Bằng cách này, converter không cần tự triển khai mọi phương thức public của interface `MessageConverter`.

### 6.2. Tại sao supports chỉ chấp nhận hai class?

~~~java
return OrderRequest.class.equals(clazz)
        || ClassificationResult.class.equals(clazz);
~~~

Đây là **allowlist của loại POJO** mà converter biết xử lý. Nó tránh nhận mọi `Object`, `Map` hoặc `List` rồi tùy tiện deserialize. Khi cần thêm một DTO khác, hãy mở rộng có chủ đích, kèm test tương ứng.

Hàm `supports` là một phần của cơ chế chọn converter, **không phải** validation nghiệp vụ. Thông điệp đã chuyển thành `OrderRequest` vẫn có thể chứa `amountVnd` âm, và phải được xử lý bởi `OrderPolicy`.

### 6.3. MIME strict làm gì?

~~~java
setStrictContentTypeMatch(true);
~~~

Khi một message không có `contentType`, converter này **không tự nhận** chỉ vì class đích là `OrderRequest`. Với media type `application/json` thông thường, converter riêng không nên giành lượt khỏi converter JSON mặc định.

Một lớp converter được thêm vào **đầu danh sách ưu tiên** của Spring Cloud Function, nhưng nó chỉ hữu ích khi tự từ chối những gì không thuộc hợp đồng. Khi converter trả `null` cho loại payload/kiểu không hỗ trợ, framework có thể thử converter khác.

### 6.4. Hai chiều chuyển đổi

| Phương thức | Đầu vào | Kết quả |
| --- | --- | --- |
| `fromMessage(message, OrderRequest.class)` | Message có `byte[]` hoặc `String` JSON và đúng MIME | `OrderRequest` |
| `fromMessage(message, ClassificationResult.class)` | Message có JSON kết quả | `ClassificationResult` |
| `toMessage(orderRequest, headers)` | POJO + header MIME | Message có payload `byte[]` JSON snake_case |
| `toMessage(classificationResult, headers)` | DTO kết quả + header MIME | Message có payload `byte[]` JSON |

Đặc biệt trong messaging, `toMessage` nên tạo **wire payload** như `byte[]`, thay vì trả nguyên đối tượng chứa tham chiếu Java không thể truyền qua broker.

### 6.5. Cấu hình Jackson: tại sao strict?

Converter dùng:

- `PropertyNamingStrategies.SNAKE_CASE`: `orderId` ↔ `order_id`.
- `FAIL_ON_UNKNOWN_PROPERTIES`: không âm thầm bỏ trường lạ.
- `FAIL_ON_MISSING_CREATOR_PROPERTIES`: từ chối thiếu tham số constructor cần thiết.
- `FAIL_ON_NULL_CREATOR_PROPERTIES`: từ chối JSON null cho tham số creator.
- `FAIL_ON_NULL_FOR_PRIMITIVES`: không để `amount_vnd: null` bị chuyển ngầm thành `0L`.

Đây là **chính sách của lab**. Trong ứng dụng cần tương thích tiến hóa schema, có thể cho phép một số field bổ sung; nhưng phải quyết định có chủ đích và test versioning. Việc đặt các tùy chọn strict trong **ObjectMapper riêng của converter** giúp không thay đổi toàn bộ JSON mapping của ứng dụng.

### 6.6. Giới hạn 16 KiB

`MAX_PAYLOAD_BYTES` là một giới hạn minh họa để tránh nhận dữ liệu quá lớn trên đường custom JSON. Trong production còn cần kiểm soát payload size ở gateway/broker, số phần tử JSON lồng nhau, giới hạn depth, resource budget và chính sách logging/retention. Custom converter **không thể** bảo vệ toàn bộ ứng dụng chỉ bằng một điều kiện `bytes.length`.

## 7. Đăng ký converter và Function trong Spring

Tạo `ConverterFunctions.java`:

~~~java
package com.example.vendorjson;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MessageConverter;

@Configuration(proxyBeanMethods = false)
public class ConverterFunctions {

    @Bean
    public MessageConverter vendorOrderJsonConverter() {
        return new VendorOrderJsonConverter();
    }

    @Bean
    public Function<OrderRequest, ClassificationResult> classifyOrder() {
        return OrderPolicy::classify;
    }
}
~~~

Đăng ký như trên có **hai ý nghĩa khác nhau**:

1. `vendorOrderJsonConverter` là **bean MessageConverter**, không phải một function nghiệp vụ để gọi bằng `FunctionCatalog.lookup("vendorOrderJsonConverter")`.
2. `classifyOrder` là **functional bean**. Nó chỉ nhận một `OrderRequest`; không tự parse JSON hoặc đọc `MessageHeaders`.

Spring Cloud Function sẽ thu thập converter do người dùng định nghĩa và đặt chúng trước converter tích hợp. Khi catalog cần chuyển message vào `OrderRequest`, converter custom có cơ hội xử lý nếu **cả media type lẫn target class** khớp.

### 7.1. Ứng dụng khởi động

Tạo `ConverterLabApplication.java`:

~~~java
package com.example.vendorjson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConverterLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterLabApplication.class, args);
    }
}
~~~

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: vendor-json-converter-lab
  cloud:
    function:
      definition: classifyOrder
      single-function-fallback-enabled: false
~~~

`definition: classifyOrder` chỉ rõ function nghiệp vụ dự định dùng ở các adapter. Nó **không** có nghĩa converter sẽ tự chạy ngay khi ứng dụng khởi động. Việc không có web starter/binder trong `pom.xml` nghĩa là lab vẫn chủ yếu chứng minh thông qua test Spring context.

## 8. Kiểm thử logic nghiệp vụ độc lập với converter

Tạo `OrderPolicyTest.java`:

~~~java
package com.example.vendorjson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderPolicyTest {

    @Test
    void classifiesPriorityOrder() {
        var input = new OrderRequest("O-201", 1_500_000L, "PARTNER-A");
        var result = OrderPolicy.classify(input);

        assertEquals(
                new ClassificationResult("O-201", "PRIORITY"),
                result);
    }

    @Test
    void classifiesStandardOrder() {
        var input = new OrderRequest("O-202", 250_000L, "PARTNER-B");

        assertEquals(
                new ClassificationResult("O-202", "STANDARD"),
                OrderPolicy.classify(input));
    }

    @Test
    void rejectsBusinessInvalidOrders() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderPolicy.classify(
                        new OrderRequest("", 100L, "PARTNER-A")));

        assertThrows(IllegalArgumentException.class,
                () -> OrderPolicy.classify(
                        new OrderRequest("O-203", -1L, "PARTNER-A")));
    }
}
~~~

Đây là unit test **thuần Java**. Nó chứng minh quy tắc nghiệp vụ nhưng chưa chứng minh JSON converter đã biến đổi dữ liệu, cũng chưa chứng minh `FunctionCatalog` nhận diện bean.

## 9. Kiểm thử trực tiếp MessageConverter

Tạo `VendorOrderJsonConverterTest.java`:

~~~java
package com.example.vendorjson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

class VendorOrderJsonConverterTest {

    private final VendorOrderJsonConverter converter =
            new VendorOrderJsonConverter();

    private static final String VALID_JSON = """
            {
              "order_id": "O-201",
              "amount_vnd": 1500000,
              "source_code": "PARTNER-A"
            }
            """;

    private Message<byte[]> vendorMessage(String json) {
        return MessageBuilder
                .withPayload(json.getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        VendorOrderJsonConverter.VENDOR_JSON)
                .build();
    }

    @Test
    void parsesSnakeCaseJsonIntoRecord() {
        Object result = converter.fromMessage(
                vendorMessage(VALID_JSON), OrderRequest.class);

        assertInstanceOf(OrderRequest.class, result);
        assertEquals(
                new OrderRequest("O-201", 1_500_000L, "PARTNER-A"),
                result);
    }

    @Test
    void alsoAcceptsStringPayloadForVendorMime() {
        Message<String> input = MessageBuilder
                .withPayload(VALID_JSON)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        VendorOrderJsonConverter.VENDOR_JSON)
                .build();

        assertEquals(
                new OrderRequest("O-201", 1_500_000L, "PARTNER-A"),
                converter.fromMessage(input, OrderRequest.class));
    }

    @Test
    void doesNotHijackOrdinaryJsonOrOtherTargetClasses() {
        var input = MessageBuilder
                .withPayload(VALID_JSON.getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .build();

        assertNull(converter.fromMessage(input, OrderRequest.class));
        assertNull(converter.fromMessage(
                vendorMessage(VALID_JSON), String.class));
    }

    @Test
    void requiresExplicitVendorContentType() {
        var missingType = MessageBuilder
                .withPayload(VALID_JSON.getBytes(StandardCharsets.UTF_8))
                .build();

        assertNull(converter.fromMessage(
                missingType, OrderRequest.class));
    }

    @Test
    void rejectsMalformedAndIncompleteJson() {
        assertThrows(MessageConversionException.class,
                () -> converter.fromMessage(
                        vendorMessage("{bad-json"),
                        OrderRequest.class));

        assertThrows(MessageConversionException.class,
                () -> converter.fromMessage(
                        vendorMessage("""
                            {"order_id":"O-204","source_code":"P"}
                            """),
                        OrderRequest.class));
    }

    @Test
    void rejectsNullPrimitiveAndUnknownProperty() {
        assertThrows(MessageConversionException.class,
                () -> converter.fromMessage(
                        vendorMessage("""
                            {"order_id":"O-205","amount_vnd":null,
                             "source_code":"P"}
                            """),
                        OrderRequest.class));

        assertThrows(MessageConversionException.class,
                () -> converter.fromMessage(
                        vendorMessage("""
                            {"order_id":"O-205","amount_vnd":10,
                             "source_code":"P","unexpected":true}
                            """),
                        OrderRequest.class));
    }

    @Test
    void serializesRecordBackToSnakeCaseJson() throws Exception {
        var headers = vendorMessage(VALID_JSON).getHeaders();
        Message<?> result = converter.toMessage(
                new OrderRequest("O-206", 500_000L, "PARTNER-Z"),
                headers);

        assertNotNull(result);
        byte[] bytes = assertInstanceOf(byte[].class, result.getPayload());
        JsonNode json = new ObjectMapper().readTree(bytes);

        assertEquals("O-206", json.get("order_id").asText());
        assertEquals(500_000L, json.get("amount_vnd").asLong());
        assertEquals("PARTNER-Z", json.get("source_code").asText());
    }

    @Test
    void enforcesPayloadSizeLimit() {
        String oversized = "x".repeat(17 * 1024);

        assertThrows(MessageConversionException.class,
                () -> converter.fromMessage(
                        vendorMessage(oversized),
                        OrderRequest.class));
    }
}
~~~

Các test ở bước này xác nhận:

- Converter hoạt động với `Message<byte[]>` và `Message<String>`.
- MIME `application/json` thông thường **không bị custom converter nhận nhầm**.
- Sai target class thì converter trả `null` để converter khác có thể xem xét.
- JSON hỏng, thiếu trường, null primitive, trường lạ bị từ chối theo policy của lab.
- Chiều `toMessage` tạo ra JSON dạng `snake_case` dưới dạng `byte[]`.

**Lưu ý kiểm thử lỗi:** Ở cấp **gọi trực tiếp converter**, ta kiểm tra `MessageConversionException`. Khi đi qua **chuỗi nhiều converter** do Spring Cloud Function quản lý, framework có thể tiếp tục tìm converter khác hoặc bọc exception theo version; không mặc định mọi lỗi trên sẽ giữ nguyên class exception ở tầng HTTP/broker.

## 10. Kiểm thử converter qua FunctionCatalog

Đây là bước quan trọng nhất: `FunctionCatalog` phải dùng converter để chuyển `Message<byte[]>` thành `OrderRequest` **trước khi** gọi `Function<OrderRequest, ClassificationResult>`.

Tạo `ConverterFunctionCatalogTest.java`:

~~~java
package com.example.vendorjson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.nio.charset.StandardCharsets;
import java.util.function.Function;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.beans.factory.annotation.Qualifier;

@SpringBootTest(
        classes = ConverterLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ConverterFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    @Qualifier("vendorOrderJsonConverter")
    private MessageConverter vendorConverter;

    @Test
    void customConverterBeanIsRegistered() {
        assertNotNull(vendorConverter);
    }

    @Test
    void catalogConvertsMessageBeforeCallingBusinessFunction()
            throws Exception {

        String body = """
                {
                  "order_id": "O-301",
                  "amount_vnd": 1700000,
                  "source_code": "PARTNER-A"
                }
                """;

        Message<byte[]> incoming = MessageBuilder
                .withPayload(body.getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        VendorOrderJsonConverter.VENDOR_JSON)
                .build();

        // Tra cứu wrapper của SCF, KHÔNG phải bean Java Function gốc.
        Function<Object, Object> function =
                catalog.lookup("classifyOrder");
        assertNotNull(function);

        Object rawResult = function.apply(incoming);
        ClassificationResult decision = decodeResult(rawResult);

        assertEquals(
                new ClassificationResult("O-301", "PRIORITY"),
                decision);
    }

    private ClassificationResult decodeResult(Object raw)
            throws Exception {

        Object payload = raw instanceof Message<?> message
                ? message.getPayload()
                : raw;

        if (payload instanceof ClassificationResult decision) {
            return decision;
        }

        // Có adapter/wrapper trả dữ liệu đã serialize.
        ObjectMapper mapper = new ObjectMapper();
        if (payload instanceof byte[] bytes) {
            return mapper.readValue(bytes, ClassificationResult.class);
        }
        if (payload instanceof String text) {
            return mapper.readValue(text, ClassificationResult.class);
        }

        throw new AssertionError(
                "Unexpected function output type: "
                        + payload.getClass().getName());
    }
}
~~~

Test này không bắt buộc một dạng duy nhất của output wrapper: tùy đường gọi và phiên bản, một catalog function có thể trả **POJO**, **Message có POJO**, hoặc kết quả đã serialize. Nhưng test luôn kiểm tra **giá trị nghiệp vụ cuối**; nếu input không được chuyển thành `OrderRequest`, lời gọi bean Java sẽ không xử lý đúng theo chữ ký và test sẽ thất bại.

### 10.1. Vì sao lookup dùng Function<Object,Object>?

Trong ví dụ này, ta muốn **chủ động đưa một `Message<byte[]>`** vào wrapper, mặc dù bean gốc có kiểu:

~~~java
Function<OrderRequest, ClassificationResult>
~~~

`FunctionCatalog.lookup("classifyOrder")` trả một function đã được Spring Cloud Function *instrumented* để xử lý conversion. Phần generic `Function<Object,Object>` ở **biến test** chỉ giúp gửi giá trị raw vào wrapper; nó **không thay đổi chữ ký bean gốc**.

Không nên tự ép `Message<byte[]>` thành `OrderRequest` trước khi gọi, vì như thế sẽ bỏ qua phần converter mà bài đang cần kiểm thử.

### 10.2. Test so sánh với JSON mặc định

Nếu thay media type đầu vào thành `application/json` và gửi JSON camelCase:

~~~json
{
  "orderId": "O-302",
  "amountVnd": 500000,
  "sourceCode": "DIRECT"
}
~~~

thì **JSON converter mặc định** có thể chuyển payload sang `OrderRequest`. Custom converter không nên can thiệp vì nó chỉ hỗ trợ `application/vnd.textlab.order+json`.

Hãy bổ sung test tích hợp riêng trong dự án của bạn:

1. Gửi `Message<byte[]>` mang JSON camelCase và header `application/json`.
2. `lookup("classifyOrder")` và gọi hàm.
3. Kiểm tra kết quả `ClassificationResult("O-302","STANDARD")`.

Test này cho thấy ứng dụng có thể nhận **hai hợp đồng JSON** trên cùng một functional bean mà không phải nhân đôi business logic. Nếu kết quả khác mong đợi, hãy kiểm tra thông tin kiểu, cấu hình Jackson và converter thực tế đang được chọn.

## 11. Chạy bộ kiểm thử

Trong thư mục `vendor-json-converter-lab`, người học chạy:

~~~bash
mvn test
~~~

Kết quả cần kiểm tra:

| Nhóm test | Bảo đảm |
| --- | --- |
| `OrderPolicyTest` | Quy tắc phân loại, validation nghiệp vụ |
| `VendorOrderJsonConverterTest` | MIME, snake_case, byte[]/String, strict schema, chiều serialization |
| `ConverterFunctionCatalogTest` | Spring đăng ký converter, catalog thực sự chuyển message vào typed function |

**Phân biệt kết quả:** Test Spring context pass là bằng chứng **conversion tại tầng FunctionCatalog** hoạt động trong cấu hình lab. Nó chưa chứng minh một topic Kafka đã được tạo, HTTP endpoint đã được expose hoặc serverless event source đã kết nối.

Trong bước viết nội dung hướng dẫn này, **không có yêu cầu chạy Maven trên máy của hệ thống tạo bài học**; các lệnh là hướng dẫn để người học tự thực hiện.

## 12. Khi mở rộng sang Spring Cloud Stream

Spring Cloud Stream dùng các binding để nối functional bean với destination của broker. Nếu muốn biến lab thành consumer/processor messaging, cần:

1. Thêm dependency Spring Cloud Stream và binder phù hợp, ví dụ Kafka hoặc RabbitMQ.
2. Cung cấp broker chạy được và cấu hình connection.
3. Chỉ định `spring.cloud.function.definition=classifyOrder`.
4. Gắn **đúng media type vendor** cho input binding.

Ví dụ cấu hình **minh họa mở rộng**, không thể dùng với `pom.xml` hiện tại nếu chưa thêm Stream/binder:

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: partner.orders.received
          group: order-classifier
          content-type: application/vnd.textlab.order+json
        classifyOrder-out-0:
          destination: partner.orders.classified
          content-type: application/json
~~~

Ở đây:

| Binding | Hướng | Media type | Kiểu Java |
| --- | --- | --- | --- |
| `classifyOrder-in-0` | Input | `application/vnd.textlab.order+json` | `OrderRequest` |
| `classifyOrder-out-0` | Output | `application/json` | `ClassificationResult` |

Input đi qua converter custom, vì đó là hợp đồng vendor JSON. Output dùng JSON chuẩn do output binding chỉ định. **Không nhất thiết phải dùng converter custom để serialize output**; bài vẫn cài `convertToInternal` để minh họa đầy đủ hai chiều và phục vụ những ứng dụng cần gửi trả về định dạng vendor.

### 12.1. Content type đến từ đâu?

Trong Spring Cloud Stream, thứ tự thường gặp:

1. **Header `contentType` trên chính message** có độ ưu tiên cao nhất.
2. Nếu không có header, **cấu hình `content-type` của binding**.
3. Nếu cả hai không có, **giá trị mặc định** của framework, thường là `application/json`.

Vì vậy, khi nhận dữ liệu từ đối tác, cần kiểm tra producer gửi header gì. Nếu producer cố tình gửi `application/json` nhưng payload lại thuộc schema vendor, input binding cấu hình vendor MIME có thể **không ghi đè header**; converter custom có thể không được chọn.

**Đừng nhầm tên binding với destination.** `classifyOrder-in-0` là định danh binding trong ứng dụng; `partner.orders.received` là destination trên binder.

### 12.2. Kiểm thử adapter thật

Sau khi bổ sung binder, viết integration test với **Spring Cloud Stream Test Binder** hoặc broker dùng cho test:

- Phát byte[] JSON `snake_case` vào `classifyOrder-in-0`.
- Gắn header `contentType` đúng.
- Đọc output tại `classifyOrder-out-0`.
- Xác nhận dữ liệu nghiệp vụ được phân loại và output JSON phù hợp.
- Kiểm tra trường hợp JSON lỗi: retry/DLQ và acknowledgment theo binder, không tự suy từ exception trong unit test.

Custom converter **không quyết định** retry, offset commit, partition hay delivery guarantee. Những đặc tính đó nằm ở Spring Cloud Stream/binder và thiết kế nghiệp vụ.

## 13. Khi mở rộng sang HTTP hoặc serverless

Với **Spring Cloud Function web adapter**, HTTP request có header `Content-Type` và body; adapter có thể tạo Spring `Message` rồi dùng chuyển đổi của catalog. Tuy nhiên **Spring MVC/WebFlux cũng có converter riêng** cho một số kiểu request. Vì thế, việc `MessageConverter` được đăng ký đúng trong SCF **không có nghĩa** mọi đường gọi HTTP đều chắc chắn đi qua converter này.

Trước khi công bố endpoint:

- Thêm web adapter và Spring Boot web runtime tương thích.
- Gửi request với `Content-Type: application/vnd.textlab.order+json`.
- Kiểm thử response status, header, body và đường chọn converter qua HTTP thực tế.
- Không coi test `FunctionCatalog` là bằng chứng đầy đủ cho content negotiation và error handling của HTTP.

Tương tự với AWS Lambda, Azure Functions hoặc Google Cloud Functions: event có thể được wrapper thành message hoặc dùng cấu trúc event riêng. Phần **`OrderPolicy` và `Function<OrderRequest,ClassificationResult>`** vẫn có thể tái sử dụng, nhưng việc đưa custom media type vào trigger cần cấu hình và kiểm thử riêng cho adapter.

## 14. Converter, Function và Validation: tách trách nhiệm

Một thiết kế dễ bảo trì sẽ có ba tầng độc lập:

| Tầng | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| Custom converter | Nhận biết media type, deserialize/serialize, kiểm soát schema và payload size | Tự quyết định “đơn nào PRIORITY” |
| Functional bean | Thực thi quy tắc nghiệp vụ trên POJO có kiểu | Đọc raw byte[] và tự parse JSON lặp ở mỗi hàm |
| Adapter (HTTP/Stream/serverless) | Cung cấp transport, content type, routing, error mapping | Đặt quy tắc phân loại sâu trong controller/broker callback |

Ví dụ rõ ràng:

~~~java
// Một input có thể đến từ JSON mặc định, vendor JSON hoặc unit test.
Function<OrderRequest, ClassificationResult> function =
        OrderPolicy::classify;

var request = new OrderRequest(
        "O-501", 1_250_000L, "DIRECT");

ClassificationResult result = function.apply(request);
// ClassificationResult("O-501", "PRIORITY")
~~~

Converter không được tham gia khi đầu vào đã là `OrderRequest`. Điều này giúp Function và Unit Test không phụ thuộc quá trình chuyển dữ liệu.

### 14.1. Tại sao không truyền Map<String,Object> vào hàm?

Nếu bean khai báo `Function<Map<String,Object>,ClassificationResult>`:

- `amount_vnd` có thể là `Integer`, `Long`, `BigDecimal` hoặc `String` theo mapper/config.
- Mỗi bean phải biết tên trường `snake_case` của đối tác.
- Nhiều đoạn code tự ép kiểu dễ tạo lỗi runtime.
- Khi muốn hỗ trợ nguồn khác, nghiệp vụ bị buộc phải sửa.

`OrderRequest` tách cấu trúc dữ liệu bên ngoài khỏi business model; compiler giúp kiểm tra accessor và generic ngay tại mã nguồn.

### 14.2. Có nên dùng custom converter cho mọi JSON?

**Không phải mặc định.** Nếu chỉ khác một vài tên trường, bạn có thể dùng `@JsonProperty` trên DTO, `PropertyNamingStrategies.SNAKE_CASE` trong mapper riêng hoặc adapter-specific schema mapping. Custom converter phù hợp khi cần một quy tắc **theo media type**, định dạng legacy độc lập hoặc quá trình decode có kiểm soát rõ ràng.

Nếu custom converter nhận rộng `application/json` cho mọi `Object`, nó có thể “nuốt” cả dữ liệu của function khác vì converter do người dùng khai báo được ưu tiên trước converter tích hợp. Đây là một trong những lý do bài thiết kế **MIME riêng + target class allowlist**.

## 15. Kiểu generic và dữ liệu lồng nhau

Converter minh họa ở đây xử lý **một record `OrderRequest` tại một lần chuyển đổi**, vì `supports` chỉ nhận class cụ thể. Nếu đầu vào thực tế là:

~~~java
List<OrderRequest>
~~~

hoặc:

~~~java
Envelope<OrderRequest>
~~~

thì `Class<?> targetClass` **không mang đầy đủ thông tin generic** như `OrderRequest` của phần tử trong List, do **type erasure** trên JVM. Khi mở rộng:

- Xem `conversionHint` và generic metadata mà framework cung cấp.
- Dùng Jackson `JavaType`/`TypeReference` để deserialize list hoặc wrapper có kiểu cụ thể.
- Cập nhật `supports` có chủ đích và thêm test cả trường hợp hợp lệ/sai schema.
- Không mở `supports(Object.class)` chỉ để tránh phải quản lý generic.

Một ví dụ Jackson 2 đọc danh sách khi tự parse:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;

// Dùng mapper đã cấu hình naming strategy phù hợp.
List<OrderRequest> orders = mapper.readValue(
        jsonBytes,
        new TypeReference<List<OrderRequest>>() {});
~~~

Đây là mẫu mở rộng, không phải đoạn copy nguyên vào converter `OrderRequest` đơn lẻ. Để thêm chức năng batch thật, cần xây dựng converter mới hoặc mở rộng thiết kế một cách kiểm soát.

## 16. Bảo mật và kiểm soát dữ liệu không tin cậy

JSON đi từ HTTP hoặc broker là **dữ liệu bên ngoài**, không phải hướng dẫn cho framework chọn một class tùy ý. Khi có trường header kiểu `application/json;type=...`, Spring Cloud Function yêu cầu danh sách các lớp được phép trong `META-INF/deserializable.types` ở một số cơ chế dynamic typing nhằm tránh tạo class tùy tiện từ nguồn không tin cậy.

Trong lab này **không dùng dynamic target class từ header**: chữ ký `Function<OrderRequest,ClassificationResult>` cho biết kiểu đích ngay trong mã Java, còn converter chỉ chấp nhận hai DTO đã biết.

Checklist tối thiểu cho production:

1. **Không bật default typing / polymorphic deserialization tùy tiện** trên JSON từ bên ngoài.
2. Hạn chế class được converter xử lý thay vì deserialize `Object` không kiểm soát.
3. Giới hạn kích thước message và độ phức tạp JSON ở nhiều tầng.
4. Kiểm tra missing/null/unknown fields và versioning schema.
5. Không ghi nguyên JSON chứa thông tin cá nhân, token hoặc bí mật vào log exception.
6. Không coi `MessageConverter` là cơ chế authentication/authorization.
7. Tạo chính sách retry, DLQ hoặc phản hồi lỗi riêng theo adapter.
8. Cập nhật dependency Jackson/Spring theo nhánh còn được hỗ trợ.

Một `MessageConversionException` có thể chứa tham chiếu message thất bại; khi xuất log ở production cần tránh vô tình làm lộ payload nhạy cảm.

## 17. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Converter custom không được gọi | Bean chưa đăng ký hoặc MIME không khớp | Kiểm tra `@Bean MessageConverter` và `contentType` |
| JSON trả về `Map` thay vì `OrderRequest` | Kiểu đích suy luận quá rộng, dùng raw `Function`/`Object` | Khai báo `Function<OrderRequest,...>` |
| `fromMessage` trả null | Không hỗ trợ MIME/target class/payload | Kiểm tra `supports` và `setStrictContentTypeMatch` |
| `amount_vnd: null` thành 0 | Jackson primitive coercion không strict | Bật `FAIL_ON_NULL_FOR_PRIMITIVES` và test |
| JSON thiếu `source_code` vẫn lọt | Không bật kiểm tra creator properties | Xem `FAIL_ON_MISSING_CREATOR_PROPERTIES` |
| Hệ thống gửi camelCase nhưng converter đòi snake_case | Khác schema/media type | Gắn đúng MIME, tách converter mặc định và vendor |
| Dữ liệu bất hợp lệ nhưng business function vẫn chạy | Converter cho qua schema sai/validation thiếu | Tách strict deserialization và kiểm tra nghiệp vụ |
| `ClassCastException` ở Function | Wrapper không chuyển sang kiểu đã khai báo | Test input `Message<byte[]>` qua catalog, xem contentType/converter |
| Catalog test pass, HTTP vẫn lỗi | Web adapter có mapping/converter riêng | Viết HTTP integration test, kiểm tra content negotiation |
| Catalog test pass, Kafka không nhận message | Chưa có binder/destination, header sai | Kiểm tra Stream binding và broker thực tế |
| Converter tác động đến các function JSON khác | `supports` hoặc MIME quá rộng | Dùng media type và allowlist class cụ thể |
| JSON nested generic thành `Map` | Mất generic type ở `Class<?>` | Dùng `TypeReference`/`JavaType` và test |
| Lỗi conversion bị bọc thành exception khác | Composite converter/wrapper/adapter quản lý lỗi | Test riêng converter và integration adapter |
| Tăng heap khi đọc message lớn | Không giới hạn payload, depth/concurrency | Áp đặt size limit nhiều tầng và giám sát |

### 17.1. Trình tự debug đề xuất

1. Test riêng `OrderPolicy.classify` với DTO Java đã tạo sẵn.
2. Test `VendorOrderJsonConverter.fromMessage` với vendor MIME đúng.
3. Test converter từ chối message sai MIME/target.
4. Test `toMessage` trả `byte[]` JSON snake_case.
5. Xác minh Spring context có bean `vendorOrderJsonConverter`.
6. Lookup `classifyOrder` qua `FunctionCatalog`.
7. Gửi `Message<byte[]>` qua wrapper và assert kết quả cuối.
8. Chỉ sau đó mới thử HTTP hoặc broker, nơi còn nhiều cơ chế chuyển đổi và xử lý lỗi khác.

## 18. Bài tập mở rộng

### Bài A — Thêm một trường tùy chọn

Đối tác bổ sung:

~~~json
{
  "order_id": "O-601",
  "amount_vnd": 600000,
  "source_code": "PARTNER-A",
  "campaign_code": "BLACKFRIDAY"
}
~~~

**Yêu cầu:** mở rộng `OrderRequest` hoặc tạo DTO version mới có `campaignCode`; quyết định trường này có bắt buộc không. Cập nhật mapper/test để JSON cũ còn được xử lý theo chính sách versioning. Vì converter đang strict với trường lạ, không nên chỉ gửi payload mới rồi kỳ vọng nó tự được chấp nhận.

### Bài B — Tách JSON sai ra kênh lỗi

Giả sử người dùng gửi:

~~~json
{
  "order_id": "O-602",
  "amount_vnd": "not-a-number",
  "source_code": "PARTNER-A"
}
~~~

**Yêu cầu:** kiểm thử lỗi deserialize tại converter, rồi đề xuất cách adapter phản hồi: HTTP 4xx phù hợp, broker DLQ, hoặc event lỗi có schema rõ. Không đặt việc gửi DLQ trực tiếp trong `convertFromInternal`, vì điều đó làm converter phụ thuộc transport và khó tái sử dụng.

### Bài C — Thêm output vendor JSON

Lab đã có `convertToInternal`. Hãy viết test:

1. Tạo `ClassificationResult("O-603","STANDARD")`.
2. Gọi `vendorConverter.toMessage(...)` với media type vendor.
3. Xác nhận payload `byte[]` và JSON có `"id":"O-603"`, `"category":"STANDARD"`.

Điều này giúp phân biệt chiều **parse JSON → POJO** và chiều **POJO → JSON**.

### Bài D — Test media type của broker

Khi đã thêm Spring Cloud Stream Test Binder, gửi hai thông điệp:

- Message A: vendor JSON với header vendor MIME.
- Message B: JSON camelCase với header `application/json`.

**Yêu cầu:** cả hai có thể cùng gọi `classifyOrder` nếu đúng converter được chọn. Ghi nhận đường chuyển đổi thực tế và chắc chắn converter vendor không giành message chuẩn.

### Bài E — Thiết kế một schema mới không cần custom converter

Tạo DTO có annotation Jackson:

~~~java
public record AnnotatedOrder(
        @com.fasterxml.jackson.annotation.JsonProperty("order_id")
        String orderId,
        @com.fasterxml.jackson.annotation.JsonProperty("amount_vnd")
        long amountVnd) {
}
~~~

**Yêu cầu:** dùng Jackson mặc định đọc JSON snake_case vào DTO này, so sánh với custom converter. Nêu trường hợp nào phù hợp với annotation, trường hợp nào cần converter độc lập theo MIME/đối tác.

## 19. Tiêu chí hoàn thành

| Tiêu chí | Minh chứng |
| --- | --- |
| POJO typed | `OrderRequest` và `ClassificationResult` không phụ thuộc framework |
| Function nghiệp vụ | `Function<OrderRequest, ClassificationResult>` đăng ký bằng `@Bean` |
| Custom converter | Kế thừa `AbstractMessageConverter`, media type vendor rõ ràng |
| Chuyển đổi đầu vào | JSON `order_id/amount_vnd/source_code` thành Java record |
| Chuyển đổi đầu ra | `toMessage` phát `byte[]` JSON |
| Không chiếm converter mặc định | Message `application/json` không bị custom converter bắt nhầm |
| Xử lý lỗi | Test JSON hỏng, thiếu/null field, unknown field, vượt size limit |
| Spring integration | `FunctionCatalog.lookup("classifyOrder")` và `apply(Message<byte[]>)` hoạt động |
| Biết giới hạn | Catalog test không thay thế HTTP/broker/serverless integration test |
| Bảo mật | Không dùng dynamic class loading, có allowlist class/size limit |

**Tóm tắt:** Custom converter nên xử lý **định dạng**, còn functional bean xử lý **nghiệp vụ**. `FunctionCatalog` kết nối hai tầng bằng thông tin kiểu đầu vào và `contentType` của message. Với thiết kế này, cùng một `Function<OrderRequest,ClassificationResult>` vẫn có thể được triển khai qua nhiều adapter mà không phải copy logic parse JSON vào từng đường xử lý.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `application/vnd.textlab.order+json` không đủ để Spring Cloud Function tự biết phải tạo `OrderRequest`?

**Đáp án:** Content type chỉ mô tả định dạng. Kiểu đích còn đến từ chữ ký function hoặc metadata chuyển đổi; ở đây là `Function<OrderRequest,...>`.

**Câu 2.** Vì sao converter custom chỉ `supports` `OrderRequest` và `ClassificationResult` thay vì mọi `Object`?

**Đáp án:** Để không can thiệp vào converter cho những DTO khác và tránh deserialize kiểu không được phép.

**Câu 3.** Đặt converter custom ở đầu chuỗi có thể gây lỗi gì?

**Đáp án:** Nếu MIME và `supports` quá rộng, converter có thể chiếm message của các function khác trước khi converter mặc định được thử. Phải giới hạn điều kiện nhận message.

**Câu 4.** `FAIL_ON_NULL_FOR_PRIMITIVES` có ích gì với `long amountVnd`?

**Đáp án:** Ngăn trường JSON `null` bị chuyển ngầm thành giá trị primitive mặc định `0L`, làm sai nghĩa nghiệp vụ.

**Câu 5.** Vì sao test `OrderPolicy.classify(new OrderRequest(...))` pass chưa chứng minh custom converter hoạt động?

**Đáp án:** Test này bỏ qua JSON, MIME, `MessageConverter` và catalog wrapper. Cần test `fromMessage` và `FunctionCatalog` với `Message<byte[]>`.

**Câu 6.** Khi triển khai Spring Cloud Stream, header `contentType` và cấu hình binding `content-type` ưu tiên thế nào?

**Đáp án:** Header của message thường ưu tiên hơn binding, sau đó mới đến default. Nếu producer gửi sai header, custom converter có thể không được chọn dù binding cấu hình đúng.

**Câu 7.** Converter có nên tự gửi message lỗi vào Kafka DLQ khi JSON hỏng?

**Đáp án:** Không nên buộc converter vào Kafka. Nó nên thể hiện lỗi conversion; adapter/binder quyết định retry, DLQ, acknowledgment và telemetry.

**Câu 8.** Khi cần `List<OrderRequest>`, vì sao chỉ dùng `OrderRequest.class` hoặc `List.class` không đủ?

**Đáp án:** Generic element type có thể bị xóa ở runtime. Phải cung cấp `TypeReference`/`JavaType` hoặc metadata phù hợp để JSON mapper biết kiểu phần tử.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model, FunctionCatalog và user-defined MessageConverters](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — User-defined Message Converters](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-user-defined-message-converters.html)
- [Spring Cloud Stream — Content-type, message conversion và binding](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Framework — AbstractMessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Framework — MessageConversionException API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html)
- [Spring Cloud — Tương thích release train với Spring Boot](https://spring.io/projects/spring-cloud/)
- [Jackson — PropertyNamingStrategies và DeserializationFeature](https://github.com/FasterXML/jackson-databind)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
