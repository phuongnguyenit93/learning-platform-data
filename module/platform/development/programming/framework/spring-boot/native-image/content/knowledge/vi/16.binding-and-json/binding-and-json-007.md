# Custom serializer, deserializer và module Jackson

## 1. Khi nào cần tùy biến JSON?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành GraalVM Native Image để đánh giá thời gian khởi động, bộ nhớ và khả năng tương thích. JSON là ranh giới quan trọng của ứng dụng: request từ client được chuyển thành object Java, còn response được chuyển ngược thành JSON.

Jackson mặc định xử lý tốt phần lớn Java bean, record, collection và kiểu dữ liệu phổ biến. Tuy nhiên, định dạng JSON bên ngoài đôi khi khác cấu trúc Java nội bộ. Ví dụ:

- API yêu cầu tiền tệ ở dạng object có hai trường amount và currency, trong khi code dùng value object Money.
- API cũ gửi ngày giờ theo chuỗi riêng, không theo ISO-8601.
- Một trường nhận nhiều dạng JSON nhưng ứng dụng muốn chuẩn hóa thành một kiểu Java.
- Một kiểu miền nghiệp vụ cần JSON contract ổn định, không phụ thuộc tên field nội bộ.

Khi đó, có thể viết **custom serializer** để điều khiển cách object Java trở thành JSON, **custom deserializer** để kiểm tra và chuyển JSON thành object Java, rồi đóng gói hai thành phần vào một **Jackson module** để tái sử dụng.

Với Native Image, cần kiểm tra thêm khả năng truy cập động của Jackson. Custom code gọi trực tiếp constructor/getter có thể không cần reflection cho chính lời gọi đó, nhưng DTO mà Jackson tự introspect vẫn có thể cần metadata để GraalVM giữ constructor, field, accessor hoặc kiểu lồng nhau.

## 2. Luồng serialize và deserialize

Hai luồng có chiều ngược nhau:

~~~mermaid
flowchart LR
    A["Java object"] --> S["JsonSerializer"]
    S --> G["JsonGenerator"]
    G --> J["JSON output"]
    I["JSON input"] --> P["JsonParser"]
    P --> D["JsonDeserializer"]
    D --> O["Java object"]
~~~

| Thành phần | Vai trò |
| --- | --- |
| JsonSerializer<T> | Chuyển object kiểu T thành các token JSON |
| JsonDeserializer<T> | Đọc token JSON và tạo object kiểu T |
| JsonGenerator | Ghi object, array, string, number, boolean và null |
| JsonParser | Đọc token từ JSON input |
| SerializerProvider | Cung cấp serializer và ngữ cảnh cho quá trình ghi |
| DeserializationContext | Cung cấp ngữ cảnh, cấu hình và tiện ích cho quá trình đọc |
| Module | Nhóm serializer, deserializer, mix-in và extension của Jackson |

Serializer/deserializer nên tập trung vào **hợp đồng JSON của một kiểu dữ liệu**. Logic nghiệp vụ như gọi database, kiểm tra quyền, gọi HTTP hoặc tạo giao dịch không nên đặt trong các lớp này.

## 3. Ví dụ miền nghiệp vụ: Money

Giả sử hệ thống hóa đơn dùng value object:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "currency must be a three-letter uppercase code"
            );
        }
    }
}
~~~

Định dạng JSON mà API công bố:

~~~json
{
  "amount": 125000.50,
  "currency": "VND"
}
~~~

Ứng dụng muốn ghi amount dưới dạng JSON number, ghi currency dưới dạng string, giữ độ chính xác của BigDecimal và từ chối dữ liệu thiếu hoặc sai kiểu. Ví dụ dùng record để minh họa; JavaBean có thể giữ cùng JSON contract và thay cách tạo object bằng constructor/setter phù hợp.

## 4. Viết custom serializer

Jackson cung cấp JsonSerializer<T>. Với serializer thông thường, có thể kế thừa StdSerializer<T>:

~~~java
package com.example.billing.json;

import java.io.IOException;
import com.example.billing.Money;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

public final class MoneySerializer extends StdSerializer<Money> {

    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeStartObject();
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

writeStartObject() mở JSON object; writeNumberField() ghi số; writeStringField() ghi mã tiền tệ; writeEndObject() đóng object. Dùng JsonGenerator thay vì nối chuỗi JSON thủ công để Jackson xử lý escaping, encoding và cấu trúc JSON chính xác.

Custom serializer hữu ích khi JSON contract khác cấu trúc field của object, cần chuẩn hóa format, biểu diễn value object thành scalar/object/array hoặc chỉ xuất các trường được phép công khai. Nếu chỉ cần đổi tên field, bỏ field hay format ngày giờ theo cấu hình phổ biến, hãy cân nhắc annotation hoặc module có sẵn trước khi viết serializer mới.

## 5. Viết custom deserializer

Deserializer kế thừa StdDeserializer<T>. Nó đọc JSON input, xác minh cấu trúc/kiểu dữ liệu rồi tạo object:

~~~java
package com.example.billing.json;

import java.io.IOException;
import com.example.billing.Money;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

public final class MoneyDeserializer extends StdDeserializer<Money> {

    public MoneyDeserializer() {
        super(Money.class);
    }

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {
        JsonNode node = parser.getCodec().readTree(parser);
        if (!node.isObject()) {
            throw JsonMappingException.from(
                parser, "Money must be represented as a JSON object"
            );
        }

        JsonNode amountNode = node.get("amount");
        JsonNode currencyNode = node.get("currency");
        if (amountNode == null || !amountNode.isNumber()) {
            throw JsonMappingException.from(
                parser, "Money.amount must be a JSON number"
            );
        }
        if (currencyNode == null || !currencyNode.isTextual()) {
            throw JsonMappingException.from(
                parser, "Money.currency must be a JSON string"
            );
        }

        try {
            return new Money(
                amountNode.decimalValue(),
                currencyNode.textValue()
            );
        }
        catch (IllegalArgumentException ex) {
            throw JsonMappingException.from(
                parser, "Money contains an invalid value"
            );
        }
    }
}
~~~

Deserializer xác nhận root là object, amount là JSON number, currency là JSON string, rồi để constructor miền nghiệp vụ kiểm tra invariant. Không nên trả về object không hợp lệ rồi để lỗi xuất hiện ở service hoặc database. Cũng không đưa payload nhạy cảm vào exception message.

### 5.1. Null, field thiếu và field không hợp lệ

Jackson xử lý JSON null qua cơ chế null value riêng; deserialize() không phải lúc nào cũng được gọi cho token null. Nếu hợp đồng API cần xử lý null đặc biệt, xem xét override getNullValue(DeserializationContext) và cấu hình null handling phù hợp.

| Input | Ý nghĩa | Cách xử lý nên chọn |
| --- | --- | --- |
| {"amount":10,"currency":"USD"} | Dữ liệu hợp lệ | Tạo Money |
| {"amount":10} | Thiếu field bắt buộc | Báo lỗi mapping |
| {"amount":"10","currency":"USD"} | Sai kiểu JSON theo contract | Báo lỗi hoặc hỗ trợ chuỗi nếu API quy định rõ |
| null | JSON null | Xử lý theo chính sách null của API |
| {} | Object rỗng | Báo thiếu dữ liệu bắt buộc |

Nếu API cần chấp nhận nhiều định dạng, hãy ghi rõ thứ tự ưu tiên và quy tắc chuyển đổi. Tránh tự động ép mọi giá trị sang string/number vì có thể che giấu client gửi dữ liệu sai.

## 6. Gom serializer và deserializer vào Jackson module

Một module gom các handler theo một nhóm kiểu dữ liệu. Với Jackson 2, có thể dùng SimpleModule:

~~~java
package com.example.billing.json;

import com.example.billing.Money;
import com.fasterxml.jackson.databind.module.SimpleModule;

public final class MoneyJacksonModule extends SimpleModule {
    public MoneyJacksonModule() {
        super("money-module");
        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
~~~

Module có tên rõ ràng để dễ nhận diện trong cấu hình và log. Có thể thêm handler cho nhiều kiểu value object nếu chúng thuộc cùng một hợp đồng JSON.

### 6.1. Đăng ký module với Spring Boot

Trong Spring Boot 3 sử dụng Jackson 2, một cách phổ biến là khai báo module thành Spring bean:

~~~java
package com.example.billing.config;

import com.example.billing.json.MoneyJacksonModule;
import com.fasterxml.jackson.databind.Module;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JacksonConfiguration {
    @Bean
    Module moneyJacksonModule() {
        return new MoneyJacksonModule();
    }
}
~~~

Spring Boot tự đăng ký các bean Jackson Module với ObjectMapper được auto-configure. Các controller dùng HTTP JSON, @RequestBody, @ResponseBody và thành phần dùng mapper do Spring quản lý có thể sử dụng module này.

**Không cần tạo ObjectMapper mới chỉ để đăng ký một module.** Nếu tự khai báo mapper, bạn có thể vô tình bỏ mất cấu hình mặc định, Java Time module, naming strategy, date format hoặc customizer khác của Spring Boot. Nếu dự án có mapper riêng, hãy xác định mapper đó được tạo ở đâu và module có được đăng ký vào đúng mapper mà HTTP converter sử dụng hay không.

### 6.2. Các cách đăng ký khác

| Cách | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| Spring bean kiểu Module | Mapper do Spring Boot quản lý | Module dùng chung cho một kiểu miền nghiệp vụ |
| @JsonComponent | Serializer/deserializer do Spring Boot phát hiện | Handler nhỏ, gắn với component scan |
| @JsonSerialize / @JsonDeserialize | Kiểu hoặc property được annotation | Chỉ một kiểu/property cần handler |
| Jackson2ObjectMapperBuilderCustomizer | Builder của Jackson 2 | Cần tùy chỉnh builder hoặc module installation |
| ObjectMapper tự tạo | Một mapper riêng | Khi thực sự cần mapper độc lập |

Không đăng ký cùng một serializer nhiều lần qua cả module bean, @JsonComponent và annotation nếu không có chủ đích. Nhiều handler cùng áp dụng cho một kiểu có thể làm kết quả phụ thuộc thứ tự đăng ký hoặc gây khó hiểu khi debug.

### 6.3. Dùng @JsonComponent

Spring Boot hỗ trợ @JsonComponent để tự phát hiện serializer/deserializer. Ví dụ rút gọn:

~~~java
@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {
            generator.writeStartObject();
            generator.writeNumberField("amount", value.amount());
            generator.writeStringField("currency", value.currency());
            generator.writeEndObject();
        }
    }

    public static class Deserializer extends JsonDeserializer<Money> {
        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {
            // Đọc và kiểm tra JSON theo cùng contract của Money.
            // Có thể tái sử dụng logic từ MoneyDeserializer.
            JsonNode node = parser.getCodec().readTree(parser);
            if (!node.isObject()
                    || node.get("amount") == null
                    || !node.get("amount").isNumber()
                    || node.get("currency") == null
                    || !node.get("currency").isTextual()) {
                throw JsonMappingException.from(parser, "Invalid Money JSON");
            }
            return new Money(
                node.get("amount").decimalValue(),
                node.get("currency").textValue()
            );
        }
    }
}
~~~

Đây là lựa chọn thay cho SimpleModule trong ứng dụng Spring Boot. Không cần giữ đồng thời ví dụ module bean và @JsonComponent cho cùng Money; hãy chọn một cơ chế đăng ký.

### 6.4. Annotation trên kiểu hoặc property

Nếu serializer chỉ áp dụng cho một property, có thể gắn annotation:

~~~java
public record InvoiceResponse(
    @JsonSerialize(using = MoneySerializer.class)
    @JsonDeserialize(using = MoneyDeserializer.class)
    Money total
) {
}
~~~

Cách này thể hiện rõ hợp đồng của property, nhưng serializer class phải được Jackson tạo và truy cập đúng cách. Nếu cùng một kiểu Money luôn có một JSON representation trong toàn ứng dụng, module bean thường dễ quản lý hơn.

## 7. Module và Jackson trong Spring Boot Native Image

### 7.1. Vì sao Jackson cần metadata?

Jackson thường introspect kiểu Java để tìm constructor/factory method, record components, getter/setter/field, annotation, kiểu lồng nhau, generic type và polymorphic subtype. Trên JVM, reflection có thể truy cập nhiều thông tin lúc chạy. Native Image cần biết trước các thành viên và kiểu nào phải giữ lại. Nếu DTO chỉ được Jackson phát hiện qua reflection mà không có metadata, request/response có thể lỗi trong native executable dù JAR chạy tốt.

### 7.2. Spring AOT và binding types

Spring Framework cung cấp @RegisterReflectionForBinding để đăng ký kiểu cần reflection cho data binding. Ví dụ:

~~~java
package com.example.billing.config;

import com.example.billing.api.CreateInvoiceRequest;
import com.example.billing.api.InvoiceResponse;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    CreateInvoiceRequest.class,
    InvoiceResponse.class
})
class JsonNativeHints {
}
~~~

Đăng ký DTO thực sự được Jackson bind trong request/response. Nếu chúng chứa kiểu lồng nhau cần introspection, kiểm tra metadata sinh ra và bổ sung kiểu cần thiết theo lỗi native thực tế. Không đăng ký mọi model trong ứng dụng chỉ để tránh lỗi.

### 7.3. Custom handler có cần reflection hints không?

Điều này phụ thuộc cách handler được tạo và những gì nó làm:

- Nếu Spring tạo MoneyJacksonModule bằng bean method và module gọi new MoneySerializer()/new MoneyDeserializer(), các lời gọi khởi tạo đó là lời gọi trực tiếp trong bytecode.
- Nếu serializer gọi trực tiếp value.amount() và deserializer gọi new Money(...), các lời gọi này cũng được biểu diễn tĩnh trong code.
- Nếu Jackson phải introspect CreateInvoiceRequest, InvoiceResponse hoặc DTO khác, những binding types đó vẫn có thể cần reflection hints.
- Nếu handler được tạo qua annotation, classpath scanning hoặc ServiceLoader, phải xác minh discovery và metadata tương ứng trong native executable.

Do đó, **không tự động thêm reflection hint cho mọi serializer class**. Hãy xác định lỗi liên quan đến việc tạo handler hay introspection DTO, rồi đăng ký đúng kiểu/thành viên bị thiếu.

### 7.4. Đăng ký module tường minh

Trong ứng dụng Spring Boot, khai báo module như bean giúp việc đăng ký rõ ràng:

~~~java
@Bean
Module moneyJacksonModule() {
    return new MoneyJacksonModule();
}
~~~

Nếu dùng ObjectMapper.findAndRegisterModules(), Jackson có thể dựa vào ServiceLoader để tìm module. Với native image, cần kiểm tra metadata/provider resource để service discovery hoạt động. Không dùng cơ chế tự dò module nếu một bean Spring hoặc cấu hình tường minh đã đáp ứng yêu cầu.

## 8. Jackson 2 và Jackson 3: không trộn API

Các ví dụ SimpleModule, JsonSerializer, JsonDeserializer trong bài dùng **Jackson 2** với package com.fasterxml.jackson.*, phổ biến trong ứng dụng Spring Boot 3.

Spring Boot 4 chuyển sang hệ sinh thái **Jackson 3** làm lựa chọn mặc định. Jackson 3 thay đổi package/API sang namespace tools.jackson.* và cách tích hợp tương ứng của Spring Boot. Vì vậy:

- Không đưa đồng thời dependency Jackson 2 và Jackson 3 vào chỉ để copy code từ hai tài liệu khác nhau.
- Chọn đúng Jackson major version theo Spring Boot đang dùng.
- Dùng serializer/deserializer/module API thuộc cùng major version với ObjectMapper và HTTP message converter.
- Kiểm tra package import, module registration và test khi nâng cấp Spring Boot.

Ý tưởng thiết kế vẫn giống nhau: serializer ghi JSON tokens, deserializer đọc và xác thực JSON, module gom handler, Spring Boot đăng ký module vào mapper được quản lý. **Tên package và API cụ thể phải khớp version.**

## 9. Kiểm thử serializer và deserializer

Custom JSON handler cần test cả chiều ghi lẫn chiều đọc. Ví dụ test với Jackson 2:

~~~java
class MoneyJacksonModuleTests {

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new MoneyJacksonModule())
        .build();

    @Test
    void serializesMoneyAsAmountAndCurrency() throws Exception {
        Money money = new Money(
            new BigDecimal("125000.50"),
            "VND"
        );
        String json = mapper.writeValueAsString(money);
        assertThat(json)
            .isEqualTo("{\"amount\":125000.50,\"currency\":\"VND\"}");
    }

    @Test
    void deserializesMoney() throws Exception {
        Money money = mapper.readValue(
            "{\"amount\":125000.50,\"currency\":\"VND\"}",
            Money.class
        );
        assertThat(money.amount()).isEqualByComparingTo("125000.50");
        assertThat(money.currency()).isEqualTo("VND");
    }
}
~~~

Test cũng nên bao phủ amount âm/dương, số nguyên/thập phân, currency thiếu/rỗng/sai định dạng, JSON root không phải object, amount là string/null/object, field không biết, JSON null và độ chính xác BigDecimal.

### 9.1. Kiểm tra module đã được Spring Boot đăng ký

Ngoài unit test tạo mapper thủ công, cần integration test dùng mapper do Spring quản lý:

~~~java
@SpringBootTest
class MoneyJacksonIntegrationTests {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void springManagedMapperUsesMoneyModule() throws Exception {
        Money value = new Money(new BigDecimal("10.25"), "USD");
        String json = objectMapper.writeValueAsString(value);
        assertThat(json)
            .isEqualTo("{\"amount\":10.25,\"currency\":\"USD\"}");
    }
}
~~~

Test này xác nhận module bean thực sự được đưa vào mapper mà Spring Boot quản lý. Nếu unit test pass nhưng integration test fail, kiểm tra component scan, bean registration, mapper riêng và cấu hình HTTP converter.

### 9.2. Kiểm thử endpoint HTTP

Nếu custom module dùng cho REST API, test cả request và response:

~~~java
mockMvc.perform(post("/invoices")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "total": {
                "amount": 125000.50,
                "currency": "VND"
              }
            }
            """))
    .andExpect(status().isCreated());
~~~

Đồng thời xác nhận response trả đúng JSON contract, không chỉ status code. Một mapper test độc lập không chứng minh message converter đang dùng cùng mapper trong ứng dụng.

## 10. Kiểm thử trên Native Image

Custom module hoạt động trên JVM chưa chắc hoạt động trong native executable. Native Image có thể thiếu metadata cho DTO hoặc đường discovery mà Jackson sử dụng.

Trình tự nên làm:

1. Chạy unit test serializer/deserializer trên JVM.
2. Chạy integration test với mapper do Spring Boot quản lý.
3. Build native executable bằng Maven/Gradle với Spring AOT.
4. Chạy native test hoặc executable và gửi JSON request thật.
5. Kiểm tra JSON hợp lệ và JSON không hợp lệ, đặc biệt các kiểu lồng nhau.

Với Gradle và Native Build Tools, dự án có thể cấu hình task nativeTest; với Maven, có thể cấu hình native test execution tương ứng. Tên task/goal và plugin version phụ thuộc hệ build, vì vậy hãy kiểm tra cấu hình thực tế của dự án.

### 10.1. Những lỗi native thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| JVM serialize được, native không tìm thấy serializer | Module chưa được đăng ký vào mapper native hoặc discovery không hoạt động | Dùng module bean/đăng ký tường minh; kiểm tra mapper thực tế |
| Deserialization báo không tạo được DTO | Thiếu constructor/field/accessor metadata cho DTO | Đăng ký binding type bằng @RegisterReflectionForBinding hoặc hints chính xác |
| Custom handler không được gọi | Module chưa vào đúng mapper, type registration không khớp hoặc mapper khác được dùng | Kiểm tra bean Module, HTTP converter và mapper instance |
| Record/constructor binding lỗi trên native | Native Image thiếu metadata cho constructor/introspection | Kiểm tra hints cho record/DTO và nested types |
| Chỉ lỗi khi chạy endpoint, unit test pass | HTTP converter dùng mapper khác hoặc DTO endpoint chưa được đăng ký | Test request/response qua Spring context và native executable |
| JSON sai kiểu nhưng được chấp nhận | Deserializer chuyển đổi quá dễ dãi | Kiểm tra token type, validate input và test dữ liệu biên |
| Module bị đăng ký hai lần | Kết hợp nhiều cơ chế như bean, @JsonComponent và annotation | Chọn một cơ chế chính cho mỗi kiểu/mapper |

## 11. Những vấn đề thiết kế cần chú ý

### 11.1. Giữ JSON contract ổn định

Không serialize trực tiếp toàn bộ object nội bộ nếu API chỉ cần một số trường. Custom serializer nên công bố rõ field nào xuất hiện và kiểu JSON của chúng. Khi đổi tên field hoặc chuyển number thành string, cần xem đó là thay đổi hợp đồng API.

### 11.2. Không làm mất độ chính xác số

Đối với tiền tệ và số thập phân, dùng BigDecimal và JsonGenerator.writeNumber(...). Không chuyển qua double/float chỉ để thuận tiện. Quy tắc làm tròn nên nằm ở domain/service theo nghiệp vụ, không được ẩn trong serializer.

### 11.3. Xử lý dữ liệu không tin cậy

Deserializer là ranh giới nhận input từ client. Cần kiểm tra kiểu token và giới hạn giá trị; tránh tạo object quá lớn từ mảng/chuỗi không giới hạn; không bật polymorphic default typing rộng cho dữ liệu không tin cậy; dùng allowlist subtype nếu JSON cần biểu diễn nhiều subtype; không log toàn bộ payload nếu có thông tin cá nhân hoặc secret.

### 11.4. Không đặt nghiệp vụ trong serializer

Serializer/deserializer nên thuần chuyển đổi dữ liệu. Không truy cập database, gọi HTTP, đọc secret store hoặc phụ thuộc request-scoped state. Các việc đó khiến mapping khó test, khó dùng lại và có thể tạo lỗi bất ngờ khi Jackson serialize trong log, cache hoặc message broker.

### 11.5. Generic type và contextual handler

Nếu handler phụ thuộc generic type như Envelope<T> hoặc annotation trên từng property, serializer/deserializer có thể cần triển khai ContextualSerializer/ContextualDeserializer để nhận thông tin kiểu và metadata của property. Không giả định một handler dùng chung cho mọi tham số generic nếu hành vi phụ thuộc T.

Với trường hợp đơn giản như Money, serializer/deserializer theo class thường đủ. Chỉ triển khai contextual handler khi có yêu cầu cụ thể.

## 12. Quy trình thực hành từ module đến native executable

Giả sử dịch vụ billing nhận request tạo hóa đơn với Money và trả về JSON có cùng cấu trúc.

**Bước 1 — xác định JSON contract**

- Viết ví dụ JSON hợp lệ và không hợp lệ.
- Chốt kiểu dữ liệu của amount, currency và chính sách null/field thiếu.
- Xác định serializer áp dụng toàn kiểu hay chỉ một property.

**Bước 2 — triển khai handler**

- Viết MoneySerializer và MoneyDeserializer.
- Giữ việc chuyển đổi thuần túy, không gọi service/database.
- Kiểm tra BigDecimal, currency và lỗi mapping.

**Bước 3 — đăng ký module**

- Với Spring Boot 3/Jackson 2, tạo bean Module chứa MoneyJacksonModule.
- Chọn @JsonComponent hoặc annotation theo property nếu phạm vi phù hợp hơn.
- Tránh đăng ký cùng handler qua nhiều cơ chế.

**Bước 4 — test JVM**

- Test serialize/deserialize trực tiếp.
- Test mapper do Spring quản lý.
- Test request/response HTTP.

**Bước 5 — chuẩn bị native metadata**

- Xác định DTO được Jackson introspect.
- Kiểm tra metadata Spring AOT/native support đã tạo.
- Dùng @RegisterReflectionForBinding hoặc hints chính xác nếu native runtime báo thiếu type/member.
- Xác minh module được đăng ký tường minh vào mapper.

**Bước 6 — build và chạy native**

Build bằng Maven hoặc Gradle theo cấu hình dự án. Chạy endpoint thực tế, kiểm tra JSON đúng định dạng và lỗi input không hợp lệ. Sau khi thay đổi serializer/module/hints, build lại native executable để kiểm tra đầu ra mới.

**Bước 7 — ghi nhận kết quả**

- Lưu JSON contract và test cases.
- Ghi phiên bản Spring Boot/Jackson/GraalVM.
- Ghi trạng thái JVM/native tests.
- Đo thời gian build, startup và RSS nếu bài toán cần so sánh hiệu năng.

## 13. Checklist trước khi hoàn tất

- [ ] JSON contract của kiểu dữ liệu được mô tả rõ.
- [ ] Serializer dùng JsonGenerator, không nối chuỗi JSON thủ công.
- [ ] Deserializer kiểm tra root, token type, field bắt buộc và giá trị miền.
- [ ] Chính sách null, field thiếu và unknown field được xác định.
- [ ] Module được đăng ký vào mapper Spring Boot thực sự sử dụng.
- [ ] Không đăng ký cùng handler qua nhiều cơ chế ngoài ý muốn.
- [ ] Jackson major version khớp với Spring Boot và dependency.
- [ ] DTO được Jackson introspect có metadata phù hợp cho native.
- [ ] Đã test unit, Spring integration, HTTP request/response và native runtime.
- [ ] Không mất độ chính xác BigDecimal và không log payload nhạy cảm.

**Ghi nhớ:** custom serializer định nghĩa cách Java object được ghi thành JSON; custom deserializer kiểm tra JSON và tạo object; Jackson module gom các handler để đăng ký nhất quán. Trong Spring Boot Native Image, cần kiểm tra cả mapper registration lẫn reflection metadata của DTO mà Jackson introspect. Test trên JVM là bước đầu, còn native executable phải được kiểm thử bằng request/response thực tế.

## Tài liệu tham khảo

- [Jackson Databind — Custom Serializers and Deserializers](https://github.com/FasterXML/jackson-databind): API JsonSerializer, JsonDeserializer, SimpleModule và databinding.
- [Spring Boot Reference — Jackson](https://docs.spring.io/spring-boot/reference/features/json.html): cấu hình JSON, module beans và tích hợp Jackson với Spring Boot.
- [Spring Framework — Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): Spring AOT, runtime hints và đăng ký reflection cho ứng dụng native.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata cần thiết cho reflection, resource, proxy và serialization.
