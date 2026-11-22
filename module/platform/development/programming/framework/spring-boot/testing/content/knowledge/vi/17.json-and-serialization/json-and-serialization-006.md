# Custom serializer, deserializer, module và @JsonComponent

## 1. Mục tiêu của bài học

Trong Spring Boot, Jackson thường tự chuyển Java object thành JSON và JSON thành Java object. Tuy nhiên, ứng dụng thực tế có các **value object** cần wire format riêng: tiền tệ cần biểu diễn chính xác, mã đơn hàng cần là JSON string, type từ thư viện ngoài không thể gắn annotation, và dữ liệu đầu vào sai định dạng phải bị từ chối có chủ đích.

Bài học thuộc nhóm **JSON và serialization**, đi sâu vào bốn công cụ chính:

- **`JsonSerializer<T>`:** quyết định Jackson ghi JSON từ một kiểu Java như thế nào.
- **`JsonDeserializer<T>`:** đọc JSON và xây dựng kiểu Java đó, có thể kiểm tra kiểu token, trường bắt buộc và giá trị.
- **`SimpleModule`/`Module`:** đăng ký serializer/deserializer với một `ObjectMapper`.
- **`@JsonComponent`:** cơ chế Spring Boot tự phát hiện và đăng ký custom JSON component trong ứng dụng.

Ta cũng sẽ kiểm thử bằng `@JsonTest`, `JacksonTester`, `ObjectMapper` và `MockMvc`, đồng thời phân biệt **mapper thuần Jackson** với **mapper được Spring Boot auto-configure**.

Phạm vi: **Spring Boot 3.3.5**, Java 17+, Jackson 2 do Spring Boot BOM quản lý. Đây là một stack cụ thể để học và tái hiện; với Boot/Jackson phiên bản khác, phải kiểm tra package/API migration thay vì mặc nhiên thay imports. Mục tiêu là có mã đầy đủ theo cấu trúc Gradle, test độc lập và mô tả kết quả kỳ vọng có kiểm soát.

## 2. Vì sao JSON mặc định chưa chắc đúng hợp đồng?

Giả sử một value object Java:

```java
public record Money(BigDecimal amount, String currency) {}
```

Nếu không có custom serializer, Jackson thường serialize record này thành object với numeric field, ví dụ `{"amount":12.50,"currency":"USD"}`. Nhưng API của ta quy định amount phải là **JSON string**:

```json
{"amount":"12.50","currency":"USD"}
```

Lý do: `BigDecimal("12.50")` thể hiện giá trị thập phân và scale; không muốn client vô tình chuyển tiền qua IEEE-754 double rồi làm thay đổi representation. Một số API chọn amount theo integer minor units hoặc JSON number, nhưng mỗi cách phải được quy định bằng contract và test.

Value object thứ hai:

```java
public record OrderCode(String value) {}
```

API chỉ chấp nhận chuỗi như `"ORD-0007"`, không phải object `{"value":"ORD-0007"}`. Đây là bài toán phù hợp với một custom serializer và deserializer trên `OrderCode`.

**Bài kiểm thử phải bảo vệ cả hai chiều:**

```text
Java -> JsonSerializer -> JSON
Money(12.50, USD) -> {"amount":"12.50","currency":"USD"}
OrderCode(ORD-0007) -> "ORD-0007"

JSON -> JsonDeserializer -> Java
{"amount":"12.50","currency":"USD"} -> Money
"ORD-0007" -> OrderCode

Sai kiểu/shape/pattern -> lỗi rõ ràng, không tạo object sai
```

Round-trip là cần thiết nhưng **không đủ**: nếu serializer và deserializer cùng sai theo một kiểu, round-trip vẫn có thể trả object ban đầu. Vì vậy cần thêm literal JSON fixtures đại diện cho hợp đồng client-server.

## 3. Serialization, deserialization và registration là ba trách nhiệm khác nhau

| Thành phần | Làm gì | Sai sót phổ biến |
| --- | --- | --- |
| `JsonSerializer<T>` | Ghi token JSON bằng `JsonGenerator` | Tự nối string, mất escaping, ghi sai kiểu number/string |
| `JsonDeserializer<T>` | Đọc token bằng `JsonParser`; tạo `T` | Chấp nhận sai JSON shape, không validate field type |
| `JsonMappingException` | Mô tả lỗi mapping | Dùng exception không có ngữ cảnh, làm client khó chẩn đoán |
| `SimpleModule` | Đăng ký nhiều handlers cho mapper | Tạo module nhưng chưa đăng ký |
| `@JsonComponent` | Đưa handler vào cơ chế auto-registration Spring Boot | Component không nằm trong scan hoặc dùng ObjectMapper khác |
| `ObjectMapper` | Runtime thực hiện read/write | Test `new ObjectMapper()` nhưng HTTP converter dùng mapper khác |
| `@JsonTest` | JSON slice test với Boot-configured mapping | Tưởng nó nạp toàn bộ controller/DB/application |
| `MockMvc` | Kiểm tra JSON qua HTTP boundary của Spring MVC | Chỉ gọi trực tiếp Java method nên bỏ qua converter |

Có hai câu hỏi không được gộp:

1. **Serializer viết đúng chưa?** Test chính mã conversion, cả positive và negative.
2. **Ứng dụng có dùng serializer đó chưa?** Test registration và HTTP JSON boundary.

Một serializer có logic đúng nhưng không được Jackson mapper đăng ký vẫn giống như “không tồn tại” đối với endpoint.

## 4. Khi nào dùng Module, @JsonComponent hay Jackson annotation?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một value type và Spring Boot nên tự phát hiện handler | `@JsonComponent` |
| Một thư viện cần nhiều serializer/deserializer và có thể dùng cả ngoài Spring | `SimpleModule` |
| Type từ thư viện không chỉnh sửa mã nguồn | Module hoặc Jackson mix-in |
| Chỉ một property cần format riêng | `@JsonSerialize(using=...)` / `@JsonDeserialize(using=...)` |
| Cấu hình naming, inclusion, format chung | Boot `spring.jackson.*` hoặc builder customizer |
| Cần kiểm tra registration không mở server | `@JsonTest` |
| Cần kiểm tra client POST JSON và server response JSON | `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc HTTP thật |

Không đăng ký nhiều serializers tranh chấp cùng một Java type nếu không có lý do và precedence được xác định bằng test. Dùng `@JsonComponent` và `Module` cho **hai type khác nhau** trong ví dụ để thấy cả hai cơ chế mà không gây tranh chấp.

## 5. Project mẫu Java 17+ với Gradle

Cấu trúc đầy đủ:

```text
json-customization-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/jsonlab/
│   ├── JsonLabApplication.java
│   ├── Money.java
│   ├── MoneyJson.java
│   ├── OrderCode.java
│   ├── OrderCodeModule.java
│   ├── Receipt.java
│   └── ReceiptController.java
└── src/test/java/com/example/jsonlab/
    ├── ReceiptJsonTest.java
    ├── OrderCodeModuleStandaloneTest.java
    └── ReceiptMvcTest.java
```

### settings.gradle

```groovy
rootProject.name = 'json-customization-demo'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-web` mang theo Jackson qua Spring Boot JSON starter. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, `@JsonTest`, `JacksonTester`, Spring MVC test infrastructure và Mockito. Các phiên bản Jackson do BOM của Boot quản lý.

Dùng Gradle Wrapper (`./gradlew`/`gradlew.bat`) nếu dự án đã có wrapper; nếu chưa có, dùng `gradle` được cài với phiên bản tương thích. Demo không gọi database, payment gateway hoặc hệ thống ngoài nào.

### Application class

Tạo `src/main/java/com/example/jsonlab/JsonLabApplication.java`:

```java
package com.example.jsonlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLabApplication.class, args);
    }
}
```

Tất cả class thuộc package `com.example.jsonlab`, nên class root `@SpringBootApplication` có thể component scan chúng, bao gồm `@JsonComponent` và Jackson Module bean.

## 6. Khai báo các domain value objects

### 6.1. Money — BigDecimal và currency code

`src/main/java/com/example/jsonlab/Money.java`:

```java
package com.example.jsonlab;

import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "currency must have three uppercase letters");
        }
    }
}
```

`Money` từ chối null và currency sai pattern ngay cả khi Java code gọi constructor trực tiếp, **không** chỉ khi được tạo qua JSON. Đây là invariant cục bộ cho ví dụ, chưa phải kiểm tra toàn bộ tập ISO 4217: ba chữ in hoa không chứng minh currency đang được hỗ trợ trong sản phẩm.

Không dùng `new BigDecimal(12.50)` trong test tính tiền. Giá trị kiểu double có thể biểu diễn xấp xỉ ở mức nhị phân; dùng `new BigDecimal("12.50")` để xác định decimal amount chính xác.

### 6.2. OrderCode — mã định danh có cấu trúc

`src/main/java/com/example/jsonlab/OrderCode.java`:

```java
package com.example.jsonlab;

public record OrderCode(String value) {

    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "order code must look like ORD-0007");
        }
    }
}
```

`ORD-0007` hợp lệ; `ORD-7` hoặc `ord-0007` không hợp lệ theo contract mẫu. Sử dụng `[0-9]` thay vì một regex string đòi escape phức tạp giúp ví dụ Java dễ đọc.

### 6.3. Receipt — object tổng hợp dùng cả hai mapping

`src/main/java/com/example/jsonlab/Receipt.java`:

```java
package com.example.jsonlab;

import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonPropertyOrder({"id", "total", "code"})
public record Receipt(long id, Money total, OrderCode code) {

    public Receipt {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "receipt id must be positive");
        }
        Objects.requireNonNull(total, "total");
        Objects.requireNonNull(code, "code");
    }
}
```

Chúng ta sẽ chuyển một instance `Receipt` sang JSON:

```json
{
  "id": 7,
  "total": {
    "amount": "12.50",
    "currency": "USD"
  },
  "code": "ORD-0007"
}
```

`@JsonPropertyOrder` làm thứ tự xuất JSON dự đoán được khi cần, nhưng test quan trọng vẫn nên so sánh **cấu trúc và giá trị**, bởi JSON object properties không nhất thiết có nghĩa thứ tự trong giao thức.

Constructor Receipt ngăn `total` hay `code` null; điều này cần thiết vì một deserializer tùy biến không nhất thiết được gọi nếu JSON property vắng mặt hoặc là null. Những invariant đó nên tồn tại ngoài lớp serialization.

## 7. @JsonComponent: một cặp serializer và deserializer của Money

Tạo `src/main/java/com/example/jsonlab/MoneyJson.java`:

```java
package com.example.jsonlab;

import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJson {

    public static class Serializer extends JsonSerializer<Money> {

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {

            generator.writeStartObject();
            generator.writeStringField(
                    "amount", value.amount().toPlainString());
            generator.writeStringField(
                    "currency", value.currency());
            generator.writeEndObject();
        }
    }

    public static class Deserializer extends JsonDeserializer<Money> {

        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {

            JsonNode node = parser.getCodec().readTree(parser);

            if (node == null || !node.isObject()) {
                throw JsonMappingException.from(
                        parser, "Money must be a JSON object");
            }

            JsonNode amountNode = node.get("amount");
            JsonNode currencyNode = node.get("currency");

            if (amountNode == null || !amountNode.isTextual()
                    || currencyNode == null
                    || !currencyNode.isTextual()) {
                throw JsonMappingException.from(
                        parser,
                        "Money amount and currency must be strings");
            }

            try {
                return new Money(
                        new BigDecimal(amountNode.textValue()),
                        currencyNode.textValue());
            } catch (IllegalArgumentException exception) {
                throw JsonMappingException.from(
                        parser,
                        "Invalid Money: " + exception.getMessage(),
                        exception);
            }
        }
    }
}
```

### Vì sao @JsonComponent đặt trên class bao?

Spring Boot hỗ trợ `@JsonComponent` trực tiếp trên class `JsonSerializer`, `JsonDeserializer`, `KeyDeserializer`, **hoặc** trên class chứa các **static nested** serializer/deserializer. Kiểu thứ hai giúp gom hai chiều của một wire contract tại một nơi. `MoneyJson.Serializer` và `MoneyJson.Deserializer` được xử lý qua Boot `JsonComponentModule` khi component có mặt trong Spring context.

`@JsonComponent` là cơ chế Spring Boot, **không** phải tính năng tự có ở `new ObjectMapper()`. Nếu chạy Jackson thuần, cần module hoặc registration tương đương.

### Vì sao serialize dùng JsonGenerator?

`generator.writeStartObject()`, `writeStringField(...)` và `writeEndObject()` tạo JSON hợp lệ và thực hiện escaping. Không tự tạo JSON bằng `"{\"amount\":\"" + ...`, vì giá trị bất kỳ có thể chứa ký tự cần escape.

`BigDecimal.toPlainString()` giúp tránh biểu diễn exponent ở wire output. Với `new BigDecimal("12.50")`, nó viết ra `"12.50"`; với một số BigDecimal ở ký pháp scientific, có thể có lựa chọn format khác, nên phải xác định contract trước.

### Vì sao deserialize đọc JsonNode?

`parser.getCodec().readTree(parser)` lấy toàn bộ JSON value của Money thành `JsonNode`; ta kiểm tra root là object, hai field cần thiết là **textual**, rồi tạo `Money`. Đây là cách dễ hiểu cho object nhỏ. Với document rất lớn hoặc streaming, tree-based deserialization có chi phí bộ nhớ; có thể dùng streaming parser để hạn chế allocation, nhưng phải xử lý token order/unknown fields cẩn thận.

Điều quan trọng: serializer ghi amount thành string, deserializer **từ chối** amount dạng number. Như vậy hợp đồng là nhất quán, không lặng lẽ chấp nhận nhiều wire forms chưa được công bố.

Khi constructor hoặc `BigDecimal(String)` ném `IllegalArgumentException`, code bọc nó thành `JsonMappingException`. Tầng HTTP có thể chuyển lỗi đọc JSON thành `400 Bad Request`. Deserializer không nên trực tiếp quyết định HTTP status vì nó có thể được dùng trong message queue, file, cache hoặc unit test không có HTTP.

### Null, missing field và unknown field

- Với JSON literal `null`, Jackson thường xử lý bằng null handling riêng chứ không gọi method `deserialize(...)` của Money.
- Với property Money không xuất hiện trong Receipt, giá trị có thể thành null và constructor Receipt sẽ từ chối.
- Deserializer này đọc `amount` và `currency` rồi bỏ qua unknown fields. Muốn reject unknown properties cần logic hoặc cơ chế schema riêng; không giả định `FAIL_ON_UNKNOWN_PROPERTIES` sẽ tự kiểm tra các keys khi code đã chủ động đọc tree.

Không dùng serializer/deserializer như nơi thực hiện database I/O hoặc log dữ liệu nhạy cảm; chúng nên tập trung vào chuyển đổi, deterministic và dễ kiểm tra.

## 8. SimpleModule cho value object OrderCode

Thay vì `@JsonComponent`, OrderCode sẽ được xử lý bằng Jackson Module. Tạo `src/main/java/com/example/jsonlab/OrderCodeModule.java`:

```java
package com.example.jsonlab;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.module.SimpleModule;

import org.springframework.stereotype.Component;

@Component
public class OrderCodeModule extends SimpleModule {

    public OrderCodeModule() {
        super("OrderCodeModule");

        addSerializer(OrderCode.class, new JsonSerializer<OrderCode>() {

            @Override
            public void serialize(
                    OrderCode value,
                    JsonGenerator generator,
                    SerializerProvider provider) throws IOException {
                generator.writeString(value.value());
            }
        });

        addDeserializer(OrderCode.class, new JsonDeserializer<OrderCode>() {

            @Override
            public OrderCode deserialize(
                    JsonParser parser,
                    DeserializationContext context) throws IOException {

                if (!parser.hasToken(JsonToken.VALUE_STRING)) {
                    throw JsonMappingException.from(
                            parser, "OrderCode must be a JSON string");
                }

                try {
                    return new OrderCode(parser.getText());
                } catch (IllegalArgumentException exception) {
                    throw JsonMappingException.from(
                            parser,
                            "Invalid OrderCode: " + exception.getMessage(),
                            exception);
                }
            }
        });
    }
}
```

`SimpleModule.addSerializer` đăng ký converter từ OrderCode thành JSON string, còn `addDeserializer` đăng ký chiều ngược lại. Method `parser.hasToken(JsonToken.VALUE_STRING)` kiểm tra đầu vào đúng token, không tự ép JSON object/number thành string. Constructor OrderCode tiếp tục validate pattern.

### Spring Boot đăng ký Module như thế nào?

Trong Spring Boot 3.3, một Jackson `Module` bean trong ApplicationContext được auto-register với `ObjectMapper` do Boot cấu hình. `OrderCodeModule` là `@Component` và nằm dưới package application root, vì vậy nó trở thành module bean.

Một cách cấu hình khác khi muốn tách Jackson Module khỏi Spring component annotation là:

```java
@Configuration(proxyBeanMethods = false)
class ModulesConfiguration {
    @Bean
    Module orderCodeModule() {
        SimpleModule module = new SimpleModule("order-code");
        module.addSerializer(
                OrderCode.class, new OrderCodeSerializer());
        module.addDeserializer(
                OrderCode.class, new OrderCodeDeserializer());
        return module;
    }
}
```

**Đoạn này chỉ là snippet kiến trúc, không thuộc project chạy được.** `OrderCodeSerializer` và `OrderCodeDeserializer` giả định đã được định nghĩa riêng. Trong project mẫu, `OrderCodeModule` đã là bean, nên **không bổ sung** cấu hình thứ hai để tránh đăng ký trùng.

### Nếu dùng Jackson ngoài Spring

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new OrderCodeModule());
```

Khi đó module chỉ tác động lên **mapper này**. Một controller khác dùng Boot-configured mapper không tự thay đổi theo lời gọi `registerModule` trên object độc lập. Đây là lý do test Jackson thuần và test Spring Boot mapper cần được phân biệt.

### Chọn Module hay @JsonComponent

`@JsonComponent` gọn khi có một vài handler Spring-managed. `SimpleModule` hữu ích khi xây dựng thư viện/nhóm handlers, cần đăng ký trên mapper độc lập hoặc xử lý cả key serializer/deserializer. Hai lựa chọn không cạnh tranh nếu dùng cho các type khác nhau như ví dụ. Không đăng ký hai serializers cho cùng một type rồi dựa vào thứ tự module ngẫu nhiên.

## 9. REST controller để kiểm tra JSON ở HTTP boundary

`src/main/java/com/example/jsonlab/ReceiptController.java`:

```java
package com.example.jsonlab;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/receipts")
public class ReceiptController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Receipt> echo(
            @RequestBody Receipt receipt) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }
}
```

Endpoint chỉ echo input; không ghi DB hoặc tạo lệnh thanh toán. Mục đích duy nhất là kiểm tra:

1. Spring MVC route POST và yêu cầu `Content-Type: application/json`.
2. Jackson deserialize `Money` và `OrderCode` theo cấu hình.
3. Controller trả lại `Receipt`.
4. Jackson serialize đúng JSON output và HTTP status `201 Created`.

Nếu test chỉ gọi `controller.echo(receipt)` trực tiếp, nó bỏ qua JSON reader/writer của Spring MVC. Cần test với `MockMvc` hoặc real HTTP client khi muốn chứng minh mapper đã được đưa vào HTTP conversion.

## 10. @JsonTest kiểm tra mapping mà không khởi động server

Tạo `src/test/java/com/example/jsonlab/ReceiptJsonTest.java`:

```java
package com.example.jsonlab;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@JsonTest
class ReceiptJsonTest {

    @Autowired
    ObjectMapper mapper;

    @Autowired
    JacksonTester<Receipt> json;

    private Receipt sample() {
        return new Receipt(
                7L,
                new Money(new BigDecimal("12.50"), "USD"),
                new OrderCode("ORD-0007"));
    }

    @Test
    void serializesReceiptUsingBothCustomizations()
            throws Exception {
        assertThat(json.write(sample())).isEqualToJson("""
            {
              "id": 7,
              "total": {
                "amount": "12.50",
                "currency": "USD"
              },
              "code": "ORD-0007"
            }
            """);
    }

    @Test
    void deserializesReceiptUsingBothCustomizations()
            throws Exception {
        Receipt parsed = json.parseObject("""
            {
              "id": 7,
              "total": {
                "amount": "12.50",
                "currency": "USD"
              },
              "code": "ORD-0007"
            }
            """);

        assertThat(parsed).isEqualTo(sample());
    }

    @Test
    void preservesAmountScaleAcrossRoundTrip()
            throws Exception {
        String wire = mapper.writeValueAsString(sample());
        Receipt parsed = mapper.readValue(
                wire, Receipt.class);

        assertThat(parsed.total().amount())
                .isEqualTo(new BigDecimal("12.50"));
        assertThat(parsed.total().amount().scale())
                .isEqualTo(2);
    }

    @Test
    void standaloneMoneyHasCustomObjectShape()
            throws Exception {
        String wire = mapper.writeValueAsString(
                new Money(new BigDecimal("4.00"), "EUR"));

        assertThat(wire).isEqualTo(
                "{\"amount\":\"4.00\",\"currency\":\"EUR\"}");
    }

    @Test
    void rejectsNumericMoneyAmount() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("""
                    {"amount":12.50,"currency":"USD"}
                    """, Money.class));
    }

    @Test
    void rejectsUnparseableMoneyAmount() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("""
                    {"amount":"twelve","currency":"USD"}
                    """, Money.class));
    }

    @Test
    void rejectsInvalidCurrency() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("""
                    {"amount":"12.50","currency":"usd"}
                    """, Money.class));
    }

    @Test
    void rejectsInvalidOrderCode() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue(
                    "\"ORD-7\"", OrderCode.class));
    }

    @Test
    void nullMoneyUsesJacksonNullHandling()
            throws Exception {
        assertThat(mapper.writeValueAsString((Money) null))
                .isEqualTo("null");

        assertThat(mapper.readValue("null", Money.class))
                .isNull();
    }
}
```

**Có 9 phương thức test.** `@JsonTest` trong Boot 3.3 auto-configures ObjectMapper, các `@JsonComponent` beans và Jackson `Module` phù hợp với JSON test slice. `JacksonTester<Receipt>` cung cấp assertions JSON có ngữ nghĩa rõ.

### Vì sao cần cả JacksonTester và ObjectMapper?

`JacksonTester.write(...)` với `isEqualToJson(...)` so sánh JSON structure, không phụ thuộc format whitespace hoặc thứ tự key khi không cần. `ObjectMapper` giúp trực tiếp kiểm tra round-trip, scale của `BigDecimal`, và exception type khi input không hợp lệ.

Test dùng literal JSON input có ý nghĩa vì nó mô phỏng contract từ client. Nếu chỉ serialize rồi deserialize cùng một object, serializer và deserializer có thể đồng thời sai mà test vẫn PASS.

### Vì sao kiểm tra scale?

`new BigDecimal("12.50")` có scale 2. `BigDecimal("12.5")` có cùng giá trị số học theo `compareTo` nhưng scale khác; `BigDecimal.equals` phân biệt. Vì contract của ví dụ ghi amount thành decimal string, test bảo vệ `scale() == 2`. Nếu API của bạn không yêu cầu bảo toàn scale, hãy xác định chính sách làm tròn/chuẩn hóa và sửa kỳ vọng có chủ đích.

### Test invalid input bảo vệ điều gì?

- `rejectsNumericMoneyAmount`: trường amount là JSON number, bị từ chối dù giá trị số học trông hợp lệ.
- `rejectsUnparseableMoneyAmount`: chuỗi không tạo được `BigDecimal`.
- `rejectsInvalidCurrency`: currency không thỏa constructor Money.
- `rejectsInvalidOrderCode`: mã không đúng pattern.
- `nullMoneyUsesJacksonNullHandling`: JSON literal null được Jackson xử lý riêng, không nhất thiết gọi deserializer custom.

Không dựa vào exact nội dung thông báo lỗi Jackson trong mọi phiên bản; test type `JsonMappingException` đủ cho mức unit mapping. Tầng HTTP kiểm tra status 400.

## 11. Unit test Module không cần Spring context

Tạo `src/test/java/com/example/jsonlab/OrderCodeModuleStandaloneTest.java`:

```java
package com.example.jsonlab;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderCodeModuleStandaloneTest {

    @Test
    void moduleCanBeRegisteredWithPlainJacksonMapper()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new OrderCodeModule());

        OrderCode code = new OrderCode("ORD-0042");

        assertThat(mapper.writeValueAsString(code))
                .isEqualTo("\"ORD-0042\"");

        assertThat(mapper.readValue(
                "\"ORD-0042\"", OrderCode.class))
                .isEqualTo(code);
    }
}
```

**Có 1 test method.** Nó chứng minh cách registration độc lập của `SimpleModule`. Nhưng nó **không chứng minh** rằng Boot application đã đăng ký đúng Module bean hoặc `MoneyJson`; vì mapper được tạo mới nên không có các customizations được Boot auto-register khác.

Nếu project có người tạo `new ObjectMapper()` bên trong controller, @JsonTest có thể PASS còn HTTP behavior khác. Tốt hơn là inject Boot mapper hoặc cấu hình mapper dùng chung một cách rõ ràng.

## 12. Integration test: JSON thực sự qua Spring MVC

Tạo `src/test/java/com/example/jsonlab/ReceiptMvcTest.java`:

```java
package com.example.jsonlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReceiptMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validPayloadUsesCustomReadersAndWriters()
            throws Exception {
        mockMvc.perform(post("/api/receipts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id": 7,
                      "total": {
                        "amount": "12.50",
                        "currency": "USD"
                      },
                      "code": "ORD-0007"
                    }
                    """))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.total.amount").value("12.50"))
                .andExpect(jsonPath("$.total.currency").value("USD"))
                .andExpect(jsonPath("$.code").value("ORD-0007"));
    }

    @Test
    void invalidMoneyAmountIsBadRequest()
            throws Exception {
        mockMvc.perform(post("/api/receipts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id": 7,
                      "total": {
                        "amount": 12.50,
                        "currency": "USD"
                      },
                      "code": "ORD-0007"
                    }
                    """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void nonJsonContentTypeIsUnsupported()
            throws Exception {
        mockMvc.perform(post("/api/receipts")
                .contentType(MediaType.TEXT_PLAIN)
                .content("not json"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
```

**Có 3 test methods.** Đây là test HTTP contract qua **MockMvc**, không phải request TCP tới embedded Tomcat: `@SpringBootTest` dựng context ứng dụng, `@AutoConfigureMockMvc` cấu hình mock servlet infrastructure. Nó đủ để kiểm tra JSON body, content type, converter, controller mapping và status code. Nếu sản phẩm cần kiểm tra network/TLS/server port thực, thêm `@SpringBootTest(webEnvironment=RANDOM_PORT)` với HTTP client vào suite riêng.

Các assertion xác nhận đường đi của JSON:

```text
POST JSON body
  -> Spring MVC HttpMessageConverter
  -> Boot ObjectMapper
  -> MoneyJson.Deserializer + OrderCodeModule deserializer
  -> ReceiptController.echo(...)
  -> MoneyJson.Serializer + OrderCodeModule serializer
  -> JSON response, HTTP 201
```

Khi amount là JSON number, custom Money deserializer ném mapping exception; MVC thường bọc thành `HttpMessageNotReadableException` và trả 400 theo cơ chế mặc định. Với `Content-Type: text/plain` trong endpoint `consumes=application/json`, request bị từ chối bằng 415. Nếu ứng dụng có custom `@ControllerAdvice`, cần assert status/error schema theo policy thực tế.

## 13. Lệnh chạy và kết quả cần đối chiếu

| Class | Số `@Test` | Phạm vi |
| --- | ---: | --- |
| `ReceiptJsonTest` | 9 | @JsonTest, Boot mapper, @JsonComponent và Module |
| `OrderCodeModuleStandaloneTest` | 1 | Module với ObjectMapper thuần |
| `ReceiptMvcTest` | 3 | Full context + MockMvc HTTP JSON mapping |

Tổng **13 phương thức test** theo mã ví dụ.

Lệnh chạy nếu project đã có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.jsonlab.ReceiptJsonTest'
./gradlew test --tests 'com.example.jsonlab.OrderCodeModuleStandaloneTest'
./gradlew test --tests 'com.example.jsonlab.ReceiptMvcTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có Wrapper, dùng `gradle test` khi Gradle tương thích đã được cài. Không có stdout nghiệp vụ cố định; Gradle ghi test report ở `build/reports/tests/test/index.html` và dữ liệu XML ở `build/test-results/test/`.

**Đây là kỳ vọng theo source, không phải báo cáo CI đã chạy.** Khi thực hành, phải kiểm tra report thực, bao gồm số test thành công/thất bại, dependency versions và nguyên nhân exception nếu có.

## 14. Những ranh giới rất quan trọng

### 14.1. Null không luôn đi qua custom deserializer

Nếu JSON có `"total":null`, Jackson có thể bỏ qua `MoneyJson.Deserializer.deserialize(...)` để tạo Java null. `Receipt` trong ví dụ từ chối null qua constructor. Nếu endpoint muốn dùng Bean Validation thay vì constructor invariant, cần cấu hình `@NotNull`/`@Valid` và dependency validation thích hợp.

Nếu trong code test chỉ gọi `mapper.readValue("null", Money.class)`, kết quả theo cơ chế null mặc định có thể là Java null. Không kết luận custom deserializer đã “cho phép dữ liệu tiền trống” — nó có thể chưa từng được gọi.

### 14.2. Unknown fields và duplicate keys

Deserializer của Money đọc thành `JsonNode` rồi lấy hai field cố định. Một field JSON khác như `"unknown":"x"` sẽ không được handler này chủ động kiểm tra. Với duplicate key, tree-based processing có thể giữ một phiên bản giá trị tùy parser/features.

Nếu contract yêu cầu strict, thêm kiểm tra tập field cho phép và duplicate-detection policy. Không tin rằng `FAIL_ON_UNKNOWN_PROPERTIES` tự động bao phủ mọi object khi code custom deserializer **đã chủ động đọc tree**.

### 14.3. Numeric precision và scale

Không chuyển `BigDecimal` qua `double` để “đơn giản hóa” JSON. Với JSON number, client dùng JavaScript có thể làm thay đổi precision; với decimal string, server cần xác nhận string parse hợp lệ và quy tắc scale/rounding. `toPlainString()` viết không dùng exponent nhưng không tự áp dụng chính sách “hai chữ số thập phân cho mọi currency”.

Ví dụ `new BigDecimal("1E+3").toPlainString()` trả `"1000"`. Nếu wire contract cấm exponent ở **input**, cần validator regex hoặc quy tắc parser riêng; BigDecimal(String) có thể nhận ký pháp scientific notation.

### 14.4. Jackson DTO mapping không thay thế nghiệp vụ

Serializer có nhiệm vụ biểu diễn object, không phải tự gọi DB để kiểm tra mã tiền tệ được kích hoạt, trừ kho hoặc gửi event. Business validation nên diễn ra ở domain/service boundary thích hợp. Nếu custom deserializer có network call, nó làm request decoding chậm, khó retry và nguy cơ side effect trước khi controller nhận request.

### 14.5. Map key serializer khác value serializer

Nếu một API dùng `Map<OrderCode, String>`, Jackson object property names là **map keys**. Handler thêm bằng `addSerializer(OrderCode.class,...)` cho value không nhất thiết được dùng cho key. Khi cần custom map key, dùng `KeySerializer`/`KeyDeserializer` hoặc những đăng ký tương ứng của Module, rồi test riêng JSON object key.

### 14.6. Polymorphic deserialization và security

Không bật default typing không giới hạn cho phép client chỉ định tùy ý class Java cần khởi tạo. Nếu API cần subtype, dùng discriminator được quy định, allowlist subtype và kiểm tra unknown type bị từ chối. Một JSON field chứa class name do client cung cấp **không phải dữ liệu đáng tin để gọi reflection**.

### 14.7. Date/time: ưu tiên module chuẩn khi có thể

Đối với `Instant`, `OffsetDateTime` và `LocalDateTime`, kiểm tra Java Time module và Spring Boot/Jackson configuration trước khi tự viết custom serializer. `LocalDateTime` không chứa timezone; đừng ngầm coi giá trị đó là UTC. Nếu contract đòi epoch milliseconds hoặc RFC 3339, xác định timezone/offset và test cả hai chiều.

## 15. @JsonComponent, @JsonSerialize và module precedence

Khi chỉ **một field** của DTO cần format khác, có thể gắn annotation:

```java
public record ReportRow(
        @JsonSerialize(using = SpecialMoneySerializer.class)
        Money displayAmount
) {}
```

Đây là snippet minh họa không độc lập: `SpecialMoneySerializer` và các imports cần được khai báo trong ứng dụng sử dụng nó. Nó thể hiện property-level serializer, trong khi `SimpleModule.addSerializer(Money.class, ...)` thường có phạm vi type-level trên mapper.

Nếu dùng cả annotation ở property và module cho cùng type, Jackson có cơ chế resolution riêng; không đoán precedence dựa vào thứ tự đọc source code. Chỉ giữ các quy tắc cần thiết và bảo vệ kết quả bằng JSON contract tests.

Spring Boot 3.3 còn có `Jackson2ObjectMapperBuilderCustomizer` cho các cấu hình chung như naming strategy, inclusion hoặc indentation. Đừng tạo một `new ObjectMapper()` riêng trong mỗi controller chỉ để đổi một property; dùng configuration/Module/annotation phù hợp và inject mapper chung.

## 16. Testing theo lớp: vì sao không chỉ dùng một kiểu test?

| Mức test | Kết luận được | Chưa chứng minh |
| --- | --- | --- |
| Pure Java JUnit + `registerModule` | SimpleModule logic đúng trên mapper cụ thể | Boot có auto-register Module bean |
| `@JsonTest` + `JacksonTester` | Boot JSON slice dùng custom component/module | Controller HTTP đã wiring đúng hay chưa |
| `@SpringBootTest` + MockMvc | HTTP reader/writer của Spring MVC dùng mapper và trả status đúng | TCP server/TLS/proxy thực tế |
| `RANDOM_PORT` HTTP integration | Embedded server thật nhận HTTP và trả wire JSON | Hệ thống bên ngoài, DB consistency nếu không có |
| Contract test với consumer/provider | Hợp đồng JSON giữa service thật và client | Mọi hiệu ứng nghiệp vụ dưới failure/concurrency |

**Một lỗi thực tế:** `@JsonTest` PASS, nhưng controller có custom `MappingJackson2HttpMessageConverter` chứa mapper khác. MVC test sẽ thấy response JSON sai format. Khi đó không được “sửa” expected JSON cho khớp lỗi; phải kiểm tra mapper thực được HTTP converter sử dụng.

## 17. Cách điều tra khi custom mapping không hoạt động

1. Xác định lỗi ở chiều **write** hay **read**.
2. Kiểm tra JSON thực tế: string hay number, object hay primitive, missing field hay malformed JSON?
3. Kiểm tra application đang dùng **Spring Boot-managed ObjectMapper** hay một mapper tạo tay.
4. Xác nhận `@JsonComponent` có mặt trong component scan đúng package.
5. Kiểm tra `Module` bean có được tạo và đăng ký với đúng mapper chưa.
6. Nếu `@JsonTest` không load module từ một `@Configuration` riêng, cân nhắc `@Import` config vào slice hoặc test context đúng phạm vi.
7. Kiểm tra model invariant, custom constructor và exception wrapping.
8. Kiểm tra `Content-Type`, `Accept` và `consumes/produces` nếu lỗi xảy ra ở HTTP.
9. Tách một unit test module thuần khỏi Spring để khoanh vùng.
10. Sau khi sửa, chạy lại cả JSON slice và MVC test; không chỉ nhìn một test happy-path.

## 18. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Money viết amount dạng number | @JsonComponent chưa được scan/đăng ký hoặc dùng mapper khác | @JsonTest và MVC test |
| OrderCode thành object có `value` | SimpleModule chưa được đăng ký | Test Boot mapper và plain mapper |
| Mapper thuần PASS, Boot mapper FAIL | Module bean không có trong context | Package scan, @Component/@Bean |
| @JsonTest PASS, HTTP FAIL | Converter dùng mapper riêng | MockMvc và cấu hình converter |
| JSON amount number bị 400 | Deserializer cố ý chỉ nhận string | Kiểm tra payload đúng contract |
| JSON null không bị custom deserializer từ chối | Null handling riêng | Constructor invariant / validation |
| Unknown field bị bỏ qua | Custom tree handler không check extra keys | Strict schema test |
| Map key không theo custom format | Key serializer khác value serializer | addKeySerializer/addKeyDeserializer |
| BigDecimal thành kiểu double | Conversion qua floating point ở một bước | Literal JSON, scale và precision tests |
| Exception message đổi sau upgrade | Phụ thuộc wording nội bộ Jackson | Assert type/status/code thay vì full stack trace |
| JSON thời gian lệch múi giờ | Dùng sai Instant/LocalDateTime/config | Test time zone/offset |
| HTTP trả 415 | Content-Type không khớp consumes | MockMvc media-type assertion |
| HTTP trả 400 | JSON syntax/type/constructor validation sai | Kiểm tra root cause |
| Test suite flaky | Mapper mutate sau startup hoặc state dùng chung | Cấu hình trước khi dùng, isolate test data |

## 19. Checklist QA cho custom JSON

1. Wire format có được mô tả trước khi viết code?
2. Serializer ghi đúng JSON tokens và escaping?
3. Deserializer validate root shape, field type và value?
4. Có test cả literal JSON và round-trip?
5. Có phân biệt missing, null, malformed, wrong type và domain-invalid input?
6. Decimal amount có giữ precision và scale theo hợp đồng?
7. `@JsonComponent` có mặt trong Spring application context?
8. Module bean đã được Boot ObjectMapper đăng ký?
9. Có unit test module với `new ObjectMapper().registerModule(...)`?
10. Có `@JsonTest` cho serialization và deserialization trong Spring?
11. Có MVC/HTTP test kiểm tra request/response và status 400/415?
12. Có tránh hai serializers cạnh tranh cùng một Java type?
13. Serializer/deserializer có không giữ mutable state theo request?
14. Có tránh thay ObjectMapper configuration khi đang xử lý request đồng thời?
15. Có tránh auto-typing không giới hạn/unsafe subtype resolution?
16. Có kiểm tra các library khác (Kafka/Redis/WebClient) có dùng đúng mapper nếu contract cần không?
17. Có tránh log secret và side effect trong deserialize?
18. Test có chạy đúng Java/Boot/Jackson versions của dự án?
19. Report test thực có khớp số lượng, không suy từ source?
20. Mọi thay đổi wire contract có được versioning/communicate tới consumers nếu cần?

## 20. Bài thực hành có chủ đích

1. Chạy `ReceiptJsonTest` và quan sát amount có dạng JSON string.
2. Bỏ `@JsonComponent` khỏi `MoneyJson` rồi chạy lại; phân biệt lỗi registration với lỗi logic serializer.
3. Bỏ `@Component` trên `OrderCodeModule`, không đăng ký module ở nơi khác; kiểm tra JSON code đổi shape thế nào.
4. Dùng mapper thuần + `registerModule` để thấy Jackson không phụ thuộc Spring vẫn có module.
5. Thử gửi `"amount":12.50`; giải thích lỗi token type so với `"amount":"12.50"`.
6. Thử `"amount":"abc"`, `"currency":"usd"`, `"code":"ORD-7"`; phân biệt parse và domain invariant.
7. Thêm test `total=null` và thiếu total field để kiểm tra constructor Receipt.
8. Thử thêm unknown field vào Money; quyết định policy bỏ qua hay reject và viết test cho lựa chọn.
9. Kiểm tra `BigDecimal("12.50")` giữ scale 2 sau round-trip; sau đó thử scientific notation.
10. Tạo DTO khác dùng `@JsonSerialize` tại một field và so sánh phạm vi với module.
11. Mở rộng Module cho `Map<OrderCode,String>` bằng key serializer/deserializer riêng.
12. Viết test upgrade contract giữa hai phiên bản JSON; bảo vệ backward compatibility với consumer.
13. Thử MockMvc POST với `Content-Type: text/plain` để phân biệt lỗi media type với JSON parsing.
14. Khi cần, thêm HTTP test `RANDOM_PORT` để xác nhận behavior qua cổng thật.
15. Chạy `./gradlew test`, mở HTML report, xác nhận **13 test methods** và kiểm tra failure stack traces nếu có.

## 21. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — JSON / Jackson](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): `@JsonComponent`, custom serializers/deserializers, Jackson auto-configuration.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JsonTest`, `JacksonTester`, Module auto-config và Spring MVC test.
- [Jackson Databind 2.17 — JsonSerializer](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/JsonSerializer.html): serializer contract.
- [Jackson Databind 2.17 — JsonDeserializer](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/JsonDeserializer.html): deserializer contract.
- [Jackson Databind 2.17 — SimpleModule](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/module/SimpleModule.html): đăng ký handlers, key serializer/deserializer.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử JSON reader/writer qua Servlet MVC không cần real TCP.

## 22. Tổng kết

**Custom serializer** quy định Java object được ghi thành JSON; **custom deserializer** quy định JSON nào tạo được Java object và những trường hợp phải bị từ chối; **Module** đăng ký các quy tắc đó vào `ObjectMapper`; còn **`@JsonComponent`** là cơ chế Spring Boot 3.x giúp phát hiện và đăng ký JSON components theo component scan.

Một bộ kiểm thử đáng tin cần bảo vệ đồng thời **wire contract**, **domain invariants**, **registration vào mapper thực** và **HTTP behavior**. Dùng JUnit test module thuần để tách conversion logic, `@JsonTest` để xác minh cấu hình Boot, và `MockMvc` để khẳng định Spring MVC áp dụng cùng mapping vào request/response. Luôn xem xét null, missing/unknown fields, BigDecimal precision và sự khác nhau giữa một mapper tạo bằng `new` với mapper thực của ứng dụng.
