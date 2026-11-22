# Đăng ký Jackson module, serializer và deserializer trong Spring Boot

## 1. Mục tiêu và bối cảnh

Khi một REST API nhận hoặc trả JSON, Spring Boot thường sử dụng **Jackson** để chuyển đổi giữa cấu trúc JSON và các đối tượng Java. Phần lớn kiểu thông thường như record, JavaBean, List, Map, String và number được hỗ trợ bởi cấu hình mặc định. Nhưng có những kiểu dữ liệu nghiệp vụ cần biểu diễn JSON riêng: mã định danh, tiền tệ, số lượng có đơn vị, định dạng ngày không tiêu chuẩn hoặc contract phải tương thích với một hệ thống cũ.

Trong trường hợp đó, ba khái niệm trọng tâm là:

- **JsonSerializer<T>**: viết một đối tượng kiểu T thành JSON. Chiều Java → JSON.
- **JsonDeserializer<T>**: đọc JSON và tạo đối tượng T. Chiều JSON → Java.
- **Module / SimpleModule**: gói và đăng ký các serializer/deserializer cùng những cấu hình Jackson liên quan vào ObjectMapper.

Trong ứng dụng **Spring Boot 3.3.x (Jackson 2, Spring Framework 6.1.x, Java 17+)**, một bean com.fasterxml.jackson.databind.Module có thể được Spring Boot auto-configuration thu thập để cấu hình ObjectMapper do Boot quản lý. Với Spring WebFlux, Jackson encoder/decoder được lắp vào các HTTP codecs; với Spring MVC, Jackson làm việc trong HTTP message converters. Hai stack khác nhau, nhưng ở tầng dữ liệu có thể dùng cùng một Jackson module khi chúng dùng mapper đã được cấu hình module đó.

Bài này tập trung vào **đăng ký module, serializer và deserializer**, không phải thiết kế một HTTP server mới, không thay toàn bộ WebFlux framework, và không sử dụng những API Jackson 3 của Spring Boot 4.x. Phải đối chiếu API khi di chuyển ứng dụng sang các phiên bản lớn khác.

Mục tiêu sau bài học:

1. Phân biệt JsonSerializer, JsonDeserializer, SimpleModule, ObjectMapper và HTTP JSON codec.
2. Xây một serializer/deserializer đôi cho kiểu nghiệp vụ Price có hợp đồng JSON rõ ràng.
3. Đăng ký module bằng Spring bean, không gọi registerModule theo từng request.
4. Kiểm thử cả chiều Java → JSON và JSON → Java.
5. Xác minh module được dùng trong HTTP body thực của một Spring WebFlux endpoint.
6. Biết các lựa chọn thay thế như @JsonComponent, @JsonSerialize/@JsonDeserialize và Jackson2ObjectMapperBuilderCustomizer.
7. Chẩn đoán khi custom module hoạt động với ObjectMapper nhưng không hoạt động trong WebFlux codec hoặc MVC converter.
8. Nhận diện ảnh hưởng của null, lỗi dữ liệu, mức độ bao phủ module, thứ tự precedence, streaming và an toàn.

## 2. JSON codec nằm ở đâu trong Spring Boot?

Một luồng HTTP WebFlux annotation controller:

~~~mermaid
flowchart TD
    A["POST HTTP JSON body"] --> B["Reactive HTTP server / HttpHandler"]
    B --> C["DispatcherHandler + HandlerAdapter"]
    C --> D["HttpMessageReader / Jackson2JsonDecoder"]
    D --> E["ObjectMapper + Module + JsonDeserializer"]
    E --> F["Java request DTO"]
    F --> G["Controller / Service"]
    G --> H["Java response DTO"]
    H --> I["HandlerResultHandler + HttpMessageWriter"]
    I --> J["Jackson2JsonEncoder / ObjectMapper / JsonSerializer"]
    J --> K["HTTP JSON response"]
~~~

Trong **Spring MVC**, các nhánh đọc/ghi body JSON đi qua HttpMessageConverter, chẳng hạn MappingJackson2HttpMessageConverter, thay vì các HttpMessageReader/HttpMessageWriter reactive. Tuy nhiên custom serializer/deserializer vẫn là những thành phần Jackson tương ứng.

### Các lớp có trách nhiệm khác nhau

| Thành phần | Trách nhiệm |
| --- | --- |
| Java DTO / record | Dữ liệu trong code, không quy định toàn bộ biểu diễn wire format |
| ObjectMapper | Jackson engine quản lý cấu hình, module, serializer và deserializer |
| JsonSerializer<T> | Chuyển một đối tượng kiểu T thành JSON |
| JsonDeserializer<T> | Đọc JSON để tạo kiểu T |
| SimpleModule | Đăng ký serializer/deserializer theo kiểu cùng các phần mở rộng |
| @Bean Module | Đưa module vào cấu hình Jackson do Boot quản lý |
| Jackson2JsonDecoder | Dùng ObjectMapper để decode JSON body trong WebFlux |
| Jackson2JsonEncoder | Dùng ObjectMapper để encode JSON body trong WebFlux |
| HttpMessageReader/Writer | Abstraction đọc/ghi HTTP body của Spring WebFlux |
| MappingJackson2HttpMessageConverter | HTTP body conversion cho Spring MVC Servlet |
| @JsonComponent | Cách Spring Boot 3.x tự đăng ký serializer/deserializer qua component scanning |
| @JsonSerialize/@JsonDeserialize | Gắn cách chuyển đổi trực tiếp lên kiểu hoặc property |

**Serializer không tự tạo một REST endpoint; module không tự bật Jackson trong một ứng dụng thiếu Jackson dependency.** Ngược lại, một @RestController trả record bình thường thường không cần custom module vì Boot đã cấu hình Jackson.

## 3. Khi nào cần custom serializer và deserializer?

Hãy dùng cấu hình có sẵn trước khi viết code.

| Nhu cầu | Giải pháp nên thử trước | Khi nào cần module |
| --- | --- | --- |
| Đổi JSON field từ camelCase thành snake_case | @JsonProperty hoặc Jackson naming strategy | Khi contract phụ thuộc một kiểu phức tạp |
| Ẩn một field | @JsonIgnore hoặc DTO khác | Nếu quy tắc cần tích hợp với nhiều kiểu/thư viện |
| Định dạng thời gian ISO | JavaTimeModule và @JsonFormat | Nếu định dạng đặc thù không diễn đạt được |
| Loại các field null | spring.jackson.default-property-inclusion | Khi cần semantics null riêng cho một kiểu |
| Chuyển Price sang JSON string "USD:12.50" | Không có serializer mặc định theo contract này | JsonSerializer + JsonDeserializer trong SimpleModule |
| Serialize toàn bộ lớp legacy không có getter chuẩn | DTO/annotation/mixin | Khi không thể đổi class hoặc contract |
| Hỗ trợ kiểu ID/value object ở nhiều endpoint | @JsonValue/@JsonCreator khi đơn giản | Module nếu muốn gom quy tắc chung |
| Định nghĩa media type không phải JSON | HTTP codec/message converter phù hợp | Module Jackson một mình chưa đủ |
| Chỉ đổi một query parameter | Converter/Formatter | Không cần Jackson module |

Không nên thay global ObjectMapper chỉ vì một DTO có một field cần đổi tên.

## 4. Ví dụ contract xuyên suốt: kiểu Price

Một API nội bộ có đối tượng:

~~~java
public record Price(String currency, BigDecimal amount) {
}
~~~

Theo Jackson mặc định, JSON có thể được biểu diễn dạng object:

~~~json
{"currency":"USD","amount":12.50}
~~~

Nhưng hệ thống tích hợp yêu cầu Price là **một JSON string**, theo format:

~~~json
"USD:12.50"
~~~

Ví dụ một request/response:

~~~json
{
  "sku": "book-7",
  "price": "USD:12.50"
}
~~~

Hợp đồng trong bài:

- currency đúng ba chữ cái A-Z viết hoa; ví dụ USD, EUR, VND. Đây chỉ là **kiểm tra cú pháp**, không kiểm tra mã ISO-4217 có tồn tại thật hay không.
- Dấu ":" ngăn currency và số tiền.
- amount không âm và biểu diễn **đúng hai chữ số thập phân** trên wire, ví dụ 12.50 hoặc 0.00.
- Không chấp nhận số âm, format "USD 12.50", trường JSON object thay cho string, hoặc số không có hai số thập phân trong JSON.
- Không thực hiện phép đổi tiền; không khẳng định mọi loại tiền tệ thế giới đều có hai chữ số sau dấu phẩy. Đây chỉ là **hợp đồng ví dụ**, không dùng nguyên để làm thư viện tài chính quốc tế.

Vì cả chiều đọc và chiều ghi đều quan trọng, ta cần **một cặp** serializer/deserializer.

## 5. Cách Jackson gọi serializer

Khi Java DTO chứa một Price, ObjectMapper tra cứu serializer cho kiểu tương ứng và dùng JsonGenerator để ghi JSON token.

Chữ ký cốt lõi Jackson 2:

~~~java
public abstract class JsonSerializer<T> {

    public abstract void serialize(
            T value,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException;
}
~~~

Đây là **trích đoạn chữ ký minh họa**, không phải source class đầy đủ để biên dịch riêng.

Lưu ý:

- JsonGenerator.writeString ghi **JSON string token** và thực hiện escaping đúng tiêu chuẩn JSON, không đơn thuần nối dấu ngoặc kép.
- JsonGenerator.writeStartObject/writeEndObject dùng khi wire format là JSON object.
- SerializerProvider giúp tra cứu serializer khác hoặc thông tin cấu hình; không cần khi chỉ ghi một chuỗi.
- Một serializer chung phải tránh state theo request trong field mutable của singleton.
- Không dùng System.out hoặc ghi HTTP response trực tiếp từ JsonSerializer.
- Nếu kiểu có thể null, Jackson thường xử lý null qua null serializer trước; JsonSerializer.serialize không nhất thiết được gọi cho null.

### Serializer cho Price

File PriceJsonSerializer.java trong ứng dụng mẫu:

~~~java
package com.example.jsoncodec;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public final class PriceJsonSerializer extends JsonSerializer<Price> {

    @Override
    public void serialize(
            Price price,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        String wire = price.currency() + ":"
                + price.amount().toPlainString();

        generator.writeString(wire);
    }
}
~~~

Khi Price hợp lệ đã chuẩn hóa amount về scale 2, toPlainString cho "12.50", không dùng scientific notation kiểu 1.25E+1. Gọi writeString bảo đảm nó được escape theo JSON spec.

Không tự viết:

~~~java
generator.writeRaw("\"" + price.currency() + ":" +
        price.amount() + "\"");
~~~

Mẫu writeRaw không cần thiết và dễ bỏ sót escaping khi wire format có dữ liệu phức tạp. Với một JSON string, dùng writeString.

## 6. Cách Jackson gọi deserializer

Chiều ngược lại: ObjectMapper đọc JSON token qua JsonParser, chọn JsonDeserializer<Price> rồi tạo Java object.

Chữ ký cốt lõi:

~~~java
public abstract class JsonDeserializer<T> {

    public abstract T deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException;
}
~~~

Đây là mô tả hợp đồng, không phải class đầy đủ.

Deserializer tốt phải:

1. Xác nhận token loại gì được chấp nhận (ví dụ VALUE_STRING).
2. Parse theo hợp đồng rõ ràng, không đoán kiểu.
3. Từ chối malformed/unsupported input bằng Jackson mapping exception.
4. Trả domain object hợp lệ; tránh trả null cho invalid string rồi để lỗi trôi đến service.
5. Không làm blocking database/network call trong JSON decode.
6. Hạn chế dữ liệu không giới hạn kích thước và regex có thể gây công suất CPU cao.

### Deserializer cho Price

File PriceJsonDeserializer.java:

~~~java
package com.example.jsoncodec;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.InvalidFormatException;

public final class PriceJsonDeserializer extends JsonDeserializer<Price> {

    private static final Pattern WIRE =
            Pattern.compile("([A-Z]{3}):([0-9]+\\.[0-9]{2})");

    @Override
    public Price deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                    parser, "Price must be a JSON string");
        }

        String text = parser.getText();
        Matcher matcher = WIRE.matcher(text);

        if (!matcher.matches()) {
            throw InvalidFormatException.from(
                    parser,
                    "Expected price format CUR:12.34",
                    text,
                    Price.class);
        }

        return new Price(
                matcher.group(1),
                new BigDecimal(matcher.group(2)));
    }
}
~~~

**Giải thích kỹ:**

- JsonToken.VALUE_STRING loại trừ JSON number/object/array/bool cho Price.
- Pattern không cần ^...$ vì Matcher.matches kiểm tra **toàn bộ** chuỗi.
- Hai backslash trong Java string trước dấu chấm tạo regex \. để khớp **dấu chấm thực**, không phải một ký tự bất kỳ.
- new BigDecimal(String) giữ precision decimal, không đổi qua double vốn có thể đưa sai số floating point.
- InvalidFormatException có ngữ nghĩa Jackson: dữ liệu xuất hiện nhưng không đúng định dạng của kiểu.
- Tên tiền tệ là ví dụ; nếu muốn kiểm tra ISO currency thật có thể dùng java.util.Currency, nhưng phải chọn rõ cách xử lý currency có scale 0 hoặc 3.
- Dữ liệu không hợp lệ phát lỗi; khi exception đi qua HTTP body reader, Spring WebFlux thường trả **400 Bad Request** nếu không có error handler đặc biệt thay đổi status.

### Trường hợp null

JSON:

~~~json
{"sku":"book-7","price":null}
~~~

Jackson thường **không gọi deserialize** của một deserializer cho token VALUE_NULL mà dùng null-handling riêng. Bởi vậy custom deserializer ở trên **chưa bảo đảm price bắt buộc phải khác null**. Nếu API yêu cầu field đó có giá trị, cần DTO validation (@NotNull và provider Jakarta Validation phù hợp), constructor invariants, hoặc thiết kế input DTO kiểm tra rõ ràng. Serializer/deserializer không thay thế hoàn toàn validation tầng API và nghiệp vụ.

## 7. Domain record Price giữ invariant

Một serializer không nên phải đoán xem price.amount() âm hoặc có quá nhiều chữ số thập phân. Bản thân kiểu dữ liệu nên bảo vệ invariant của nó.

File Price.java:

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public record Price(String currency, BigDecimal amount) {

    public Price {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        currency = currency.trim().toUpperCase(Locale.ROOT);

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "currency must have three ASCII letters");
        }

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative");
        }

        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Cấu trúc **compact canonical constructor** của record trong Java 17 cho phép chuẩn hóa parameter trước khi record fields được gán tự động. Đối với amount, RoundingMode.UNNECESSARY từ chối giá trị cần làm tròn để về hai chữ số thập phân; ví dụ 12.345 sẽ ném ArithmeticException. Đây là policy chủ động của ví dụ, không phải yêu cầu chung từ Jackson.

Bảng:

| Giá trị Java tạo Price | Kết quả |
| --- | --- |
| new Price("usd", new BigDecimal("12.5")) | Giá trị chuẩn hóa currency USD, amount 12.50 |
| new Price("USD", new BigDecimal("12.50")) | Hợp lệ |
| new Price("EUR", new BigDecimal("0")) | Hợp lệ, amount 0.00 |
| new Price("USD", new BigDecimal("-1.00")) | IllegalArgumentException |
| new Price("USD", new BigDecimal("1.234")) | ArithmeticException do cần làm tròn |
| new Price("UNKNOWN", new BigDecimal("1")) | IllegalArgumentException |
| new Price(null, new BigDecimal("1")) | NullPointerException có thông báo currency |

**Quan trọng:** Java constructors ném lỗi có thể dẫn đến 500 nếu service của bạn tạo giá trị sai ngay trong request. Trong HTTP deserialization, hãy thiết kế mapping lỗi để phân loại client input thành 400 khi phù hợp; không trả toàn bộ stack trace cho client.

## 8. Đăng ký hai chiều bằng SimpleModule

Jackson 2 cung cấp com.fasterxml.jackson.databind.module.SimpleModule để đăng ký serializer/deserializer theo Java type.

Đoạn code cốt lõi:

~~~java
SimpleModule module = new SimpleModule("price-wire-v1");
module.addSerializer(Price.class, new PriceJsonSerializer());
module.addDeserializer(Price.class, new PriceJsonDeserializer());
~~~

Bản thân đoạn này **chưa có hiệu lực** nếu module chưa được đăng ký vào ObjectMapper mà framework sử dụng.

### Cách A: ObjectMapper thuần Java

Ngoài Spring, có thể làm:

~~~java
ObjectMapper mapper = new ObjectMapper();

SimpleModule module = new SimpleModule("price-wire-v1");
module.addSerializer(Price.class, new PriceJsonSerializer());
module.addDeserializer(Price.class, new PriceJsonDeserializer());

mapper.registerModule(module);
~~~

Đoạn minh họa này cần imports và các class Price*. Với một ứng dụng không dùng Spring, đây là cách hợp lệ. Nhưng **đừng tạo ObjectMapper mới cho mỗi request** hoặc gọi registerModule trên mapper đã phục vụ request đồng thời.

### Cách B: Spring Boot @Bean Module — trọng tâm của bài

Trong Spring Boot 3.3, phương án thường dùng:

~~~java
package com.example.jsoncodec;

import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PriceJacksonConfiguration {

    @Bean
    public Module priceWireModule() {
        SimpleModule module = new SimpleModule("price-wire-v1");

        module.addSerializer(
                Price.class, new PriceJsonSerializer());
        module.addDeserializer(
                Price.class, new PriceJsonDeserializer());

        return module;
    }
}
~~~

Đây là class hoàn chỉnh cho ví dụ Spring Boot ở mục 15. Boot auto-configuration có thể đưa các bean Module vào Jackson2ObjectMapperBuilder và ObjectMapper do Boot cấu hình. Kết quả là các JSON HTTP readers/writers dùng mapper đó có thể thấy module.

**Không yêu cầu thêm @EnableWebFlux** chỉ để đăng ký Module. Với Spring Boot, @EnableWebFlux thay mức độ auto-configuration WebFlux và có thể làm một số cấu hình của Boot không áp dụng như mong muốn.

### Vì sao @Bean Module hữu ích?

- Dễ dùng dependency injection và quản lý lifecycle lúc khởi tạo.
- Có thể gói nhiều serializer/deserializer liên quan vào một module.
- Không phải chỉnh từng controller.
- Tránh lặp new ObjectMapper trong handler.
- Dễ kiểm tra qua ObjectMapper bean và HTTP integration test.
- Tách contract serialization khỏi domain controller.

**Phạm vi áp dụng:** một Module bean chỉ ảnh hưởng tới mapper được cấu hình để sử dụng nó. Nếu một thư viện tạo new ObjectMapper độc lập, hoặc một custom HTTP codec cố tình dùng mapper khác, Module bean không tự chui vào mọi mapper trên JVM.

## 9. Tại sao Module bean có thể tác động tới Spring WebFlux codec?

Spring Boot 3.3 cung cấp cấu hình Jackson cho các HTTP codecs của WebFlux. Với auto-config mặc định, Jackson JSON encoder/decoder dùng mapper do Boot cấu hình, bao gồm các module được áp dụng qua cơ chế Jackson auto-configuration.

Luồng thực tế cho endpoint:

~~~text
POST Content-Type: application/json
          |
          v
HttpMessageReader / Jackson2JsonDecoder
          |
          v
Jackson ObjectMapper (đã có priceWireModule)
          |
          v
PriceJsonDeserializer.deserialize(...)
          |
          v
Quote(sku, Price)
          |
          v
Controller / HandlerResultHandler
          |
          v
Jackson2JsonEncoder (mapper có priceWireModule)
          |
          v
PriceJsonSerializer.serialize(...)
          |
          v
HTTP JSON string trong field price
~~~

**Đừng nhầm:**

- JsonDeserializer chỉ tham gia khi decode/deserialize JSON.
- Jackson2JsonDecoder là codec ở tầng HTTP, có thể dùng ObjectMapper để tạo object.
- Module không tự thay đổi Content-Type hoặc chuyển media type JSON sang CSV/XML.
- Một Java POJO không phải luôn cần custom deserializer; Jackson mặc định đã có cơ chế cho record/bean.
- WebClient có JSON codec riêng ở phía client; hãy xác minh cấu hình codec của WebClient cụ thể, đặc biệt nếu client được xây thủ công bằng ExchangeStrategies riêng.

### Vì sao kiểm thử ObjectMapper bean chưa đủ?

Một unit test gọi ObjectMapper.writeValueAsString có thể PASS nhưng request HTTP vẫn dùng mapper khác nếu ứng dụng đã tự thay HTTP codecs. Vì vậy cần **hai mức test**:

1. Test trực tiếp ObjectMapper để xác nhận module đã được đăng ký.
2. Test HTTP thật qua WebTestClient/MockMvc để xác nhận HTTP decoder và encoder đang dùng module.

## 10. Một lựa chọn khác: @JsonComponent của Spring Boot 3.x

Spring Boot cung cấp annotation **org.springframework.boot.jackson.JsonComponent** để đăng ký serializer/deserializer được component scan phát hiện.

Ví dụ ý tưởng:

~~~java
@JsonComponent
public class PriceJsonComponent {

    public static class Serializer extends JsonSerializer<Price> {
        @Override
        public void serialize(
                Price value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {
            generator.writeString(
                    value.currency() + ":" +
                    value.amount().toPlainString());
        }
    }

    public static class Deserializer extends JsonDeserializer<Price> {
        @Override
        public Price deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {
            // parse Price theo hợp đồng đã mô tả
            throw new UnsupportedOperationException(
                    "Example skeleton: use PriceJsonDeserializer logic");
        }
    }
}
~~~

**Đây là skeleton minh họa, KHÔNG phải class hoàn chỉnh có thể chạy**: cần imports và thay phần deserializer bằng implementation thực tế. Không dùng skeleton này trong project mục 15, nơi đã có cả hai class đầy đủ.

Sự khác nhau:

| Giải pháp | Thích hợp khi |
| --- | --- |
| @Bean Module + SimpleModule | Muốn đăng ký một tập serializer/deserializer trong một module tường minh |
| @JsonComponent | Muốn Boot auto-detect serializer/deserializer qua component scan, không cần tự viết Module bean |
| @JsonSerialize/@JsonDeserialize | Muốn cấu hình local cho một kiểu hoặc property cụ thể |
| Jackson2ObjectMapperBuilderCustomizer | Muốn chỉnh cách ObjectMapper được xây dựng theo chính sách của ứng dụng |
| mapper.registerModule(...) | Cấu hình mapper ngoài Spring Boot hoặc mapper tự quản |
| WebFlux HTTP codec customization | HTTP codec thật sự cần mapper/media type/codec khác mặc định |

Không dùng **đồng thời** @JsonComponent cùng Module bean để đăng ký hai implementation khác nhau cho cùng Java type nếu không có chủ đích kiểm soát precedence. Sự mơ hồ dễ dẫn đến hành vi không thống nhất giữa môi trường.

## 11. Gắn serializer/deserializer bằng Jackson annotations

Nếu chỉ một kiểu hoặc field riêng có contract đặc biệt, có thể gắn:

~~~java
@JsonSerialize(using = PriceJsonSerializer.class)
@JsonDeserialize(using = PriceJsonDeserializer.class)
public record Price(String currency, BigDecimal amount) {
    // ...
}
~~~

Snippet này là minh họa thiết kế annotation; trong project hoàn chỉnh mục 15 ta **không dùng** hai annotation này vì đã đăng ký module.

Cách annotation có ưu điểm là rõ ngay khi đọc class. Nhưng có nhược điểm:

- Buộc domain type biết đến Jackson.
- Khó thay contract tùy API/version/context.
- Thư viện third-party không sửa source được có thể cần mixin/module.
- Annotation trên property có precedence khác annotation trên type; cần test khi trộn.

Đôi khi **@JsonValue + @JsonCreator** là đủ cho value object đơn giản:

~~~java
public record ExternalCode(String value) {

    @JsonValue
    public String asJson() {
        return value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public ExternalCode {
        // chỉ minh họa annotation trên canonical constructor
    }
}
~~~

Đây là minh họa ý tưởng, không phải pattern bắt buộc: record canonical constructor, @JsonCreator mode, visibility, parameter types và version phải được xác minh. Với bài yêu cầu một module và custom parser rõ ràng, SimpleModule thích hợp để thấy đầy đủ API.

## 12. Thay đổi ObjectMapper bằng builder customizer

Spring Boot 3.3 cung cấp **Jackson2ObjectMapperBuilderCustomizer** để cấu hình mapper được xây từ Jackson2ObjectMapperBuilder.

Ví dụ khi muốn chuẩn hóa một property toàn cục:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer jacksonPolicy() {
    return builder -> builder.serializationInclusion(
            JsonInclude.Include.NON_NULL);
}
~~~

Đây là method minh họa trong @Configuration, cần imports org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer và com.fasterxml.jackson.annotation.JsonInclude. Trong nhiều trường hợp chỉ cần property:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

**Đừng thay toàn bộ ObjectMapper bean mặc định chỉ để thêm một module**. Khi tự khai báo @Bean ObjectMapper hoặc mapper mới bằng new ObjectMapper(), bạn có thể bỏ qua các module Java Time, naming strategy, Boot features và codec wiring được cấu hình sẵn. Nếu bắt buộc tự định nghĩa mapper, phải kiểm thử toàn bộ modules và codec paths thực tế.

### Trật tự và xung đột

- Module có thể đăng ký serializer cho cùng một Java type với một module khác.
- Annotation ở class/property có thể ảnh hưởng selection và precedence.
- Serializer/deserializer tùy biến toàn cục có thể thay đổi nhiều REST endpoints.
- Không nên dựa vào “module cuối cùng chắc chắn thắng” khi không xác định thứ tự, metadata và Jackson serializer resolution thực tế.
- Ưu tiên một chủ sở hữu rõ ràng cho JSON contract của từng type; có integration test như hàng rào khi nâng version.

## 13. JSON string, JSON object và JSON null — ba trường hợp khác nhau

Trong ví dụ, một Price được biểu diễn bằng JSON scalar:

~~~json
"USD:12.50"
~~~

không phải:

~~~json
{"currency":"USD","amount":12.50}
~~~

và cũng không phải:

~~~json
null
~~~

Quyết định này ảnh hưởng:

- Tất cả API request/response có Price dùng cùng mapper/module.
- Hợp đồng OpenAPI và generated client schemas.
- Các client không dùng Java, ví dụ JavaScript/Python/Go.
- Khả năng tìm kiếm, validate, schema evolution và versioning.
- Cách thể hiện null, invalid values và backward compatibility.

Nếu API công khai trước đây trả object và bây giờ chuyển thành string, đó thường là **breaking change**. Không nên thay module toàn cục mà không cập nhật API contract, test client, versioning hoặc kế hoạch migration.

### Vì sao JSON string đôi khi không tốt?

JSON string tiết kiệm cấu trúc nhưng client phải biết grammar đặc thù. Với dữ liệu có nhiều field hoặc dễ thay đổi, JSON object thường dễ mở rộng và debug hơn. Ví dụ Price có thêm tax/currencyScale/roundingPolicy sẽ khó giữ trong một string ngắn. Chọn wire format dựa trên contract, không phải vì serializer custom trông ngắn.

## 14. Lỗi deserialize, HTTP status và error contract

Deserializer từ chối dữ liệu khi:

- JSON token không phải string.
- Chuỗi không khớp regex đúng toàn bộ.
- Currency không đúng ba chữ A-Z.
- Amount có dấu âm, không có hai chữ số thập phân hoặc vượt giới hạn được parser chấp nhận.
- DTO có shape không tương thích.
- Request body quá lớn hoặc JSON malformed, dù chưa tới custom deserializer.

Trong WebFlux, các lỗi decode không hợp lệ thường được Spring dịch thành **400 Bad Request** khi đọc @RequestBody, nhưng kết quả cụ thể phụ thuộc exception, route mapping, controller advice, error handlers và response commit. Nếu JSON syntax sai, parser có thể fail trước cả JsonDeserializer<Price>. Nếu Content-Type không hợp lệ, có thể là 415 Unsupported Media Type; nếu Accept không thỏa mãn định dạng phản hồi, có thể 406 Not Acceptable.

**Không trả stack trace, classpath, path file nội bộ hoặc raw token cho client.** Với API thật, thiết kế một body lỗi nhất quán (ví dụ Problem Details) và log nội bộ có correlation ID. Tránh đưa nguyên chuỗi price do client gửi vào log nếu ứng dụng mở rộng sang dữ liệu nhạy cảm.

### Đừng biến mọi lỗi thành null

Mẫu nguy hiểm:

~~~java
try {
    return parse(text);
} catch (RuntimeException ex) {
    return null;
}
~~~

Với required field, return null làm lỗi bị trì hoãn, service có thể xuất NullPointerException và client nhận 500 thay vì 400. Hãy phát JsonMappingException rõ ràng cho dữ liệu JSON sai contract.

## 15. Ứng dụng hoàn chỉnh Spring Boot WebFlux + Jackson module (Java 17)

Project chạy độc lập chứng minh cả hai chiều qua REST API.

**Stack và phạm vi:** Java 17; Spring Boot 3.3.13; Reactor Netty từ spring-boot-starter-webflux; Jackson 2 do Boot quản lý. Không thêm spring-boot-starter-web để tránh Boot mặc định ưu tiên Spring MVC khi hai starter cùng có trên classpath.

### 15.1 Cấu trúc

~~~text
json-module-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/jsoncodec/
    │   ├── JsonCodecApplication.java
    │   ├── Price.java
    │   ├── PriceJsonSerializer.java
    │   ├── PriceJsonDeserializer.java
    │   ├── PriceJacksonConfiguration.java
    │   ├── Quote.java
    │   └── QuoteController.java
    └── test/java/com/example/jsoncodec/
        └── PriceCodecIntegrationTests.java
~~~

### 15.2 settings.gradle

~~~groovy
rootProject.name = 'json-module-demo'
~~~

### 15.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

starter-webflux kéo các dependency HTTP/Jackson phù hợp với Boot 3.3.x thông thường. Không cần thêm com.fasterxml.jackson.core:jackson-databind với version tự chọn vì Boot quản lý version. Nếu ứng dụng đã dùng dependency exclusions hoặc dependency platform khác, phải kiểm tra runtimeClasspath.

### 15.4 JsonCodecApplication.java

~~~java
package com.example.jsoncodec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonCodecApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonCodecApplication.class, args);
    }
}
~~~

### 15.5 Price.java

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public record Price(String currency, BigDecimal amount) {

    public Price {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        currency = currency.trim().toUpperCase(Locale.ROOT);

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "currency must have three ASCII letters");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative");
        }

        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

### 15.6 PriceJsonSerializer.java

~~~java
package com.example.jsoncodec;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public final class PriceJsonSerializer extends JsonSerializer<Price> {

    @Override
    public void serialize(
            Price price,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeString(
                price.currency() + ":" +
                price.amount().toPlainString());
    }
}
~~~

### 15.7 PriceJsonDeserializer.java

~~~java
package com.example.jsoncodec;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.InvalidFormatException;

public final class PriceJsonDeserializer extends JsonDeserializer<Price> {

    private static final Pattern WIRE =
            Pattern.compile("([A-Z]{3}):([0-9]+\\.[0-9]{2})");

    @Override
    public Price deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                    parser, "Price must be a JSON string");
        }

        String text = parser.getText();
        Matcher matcher = WIRE.matcher(text);

        if (!matcher.matches()) {
            throw InvalidFormatException.from(
                    parser,
                    "Expected price format CUR:12.34",
                    text,
                    Price.class);
        }

        return new Price(
                matcher.group(1),
                new BigDecimal(matcher.group(2)));
    }
}
~~~

### 15.8 PriceJacksonConfiguration.java

~~~java
package com.example.jsoncodec;

import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PriceJacksonConfiguration {

    @Bean
    public Module priceWireModule() {
        SimpleModule module = new SimpleModule("price-wire-v1");
        module.addSerializer(Price.class, new PriceJsonSerializer());
        module.addDeserializer(Price.class, new PriceJsonDeserializer());
        return module;
    }
}
~~~

Đăng ký module **một lần khi application context được xây dựng**, không phải trong controller. Không tự gọi ObjectMapper.registerModule tại mỗi HTTP request.

### 15.9 Quote.java

~~~java
package com.example.jsoncodec;

public record Quote(String sku, Price price) {
}
~~~

Đây là DTO Java để trả kết quả. Jackson xử lý Quote theo cơ chế record thông thường và khi gặp field price sẽ dùng serializer/deserializer của Price từ module đã đăng ký.

### 15.10 QuoteController.java

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    @GetMapping(
            path = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Quote> get(@PathVariable("sku") String sku) {
        return Mono.just(new Quote(
                sku, new Price("USD", new BigDecimal("12.50"))));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Quote> echo(@RequestBody Mono<Quote> incoming) {
        return incoming;
    }
}
~~~

GET minh họa chiều Java → JSON. POST /echo minh họa JSON → Java → JSON, vì cùng một field price vừa đi qua deserializer đầu vào, vừa đi qua serializer đầu ra. Trong ứng dụng thật, nên dùng request DTO và response DTO riêng khi contract hoặc quy tắc validation khác nhau.

### 15.11 PriceCodecIntegrationTests.java

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PriceCodecIntegrationTests {

    @LocalServerPort
    private int port;

    @Autowired
    private ObjectMapper objectMapper;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void objectMapperBeanSerializesAndDeserializesPrice()
            throws Exception {

        Price price = new Price(
                "usd", new BigDecimal("12.5"));

        String json = objectMapper.writeValueAsString(price);
        assertThat(json).isEqualTo("\"USD:12.50\"");

        Price decoded = objectMapper.readValue(
                "\"USD:12.50\"", Price.class);
        assertThat(decoded).isEqualTo(
                new Price("USD", new BigDecimal("12.50")));
    }

    @Test
    void httpResponseUsesCustomSerializer() {
        client().get()
                .uri("/api/quotes/book-7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("book-7")
                .jsonPath("$.price").isEqualTo("USD:12.50");
    }

    @Test
    void httpRequestUsesCustomDeserializer() {
        client().post()
                .uri("/api/quotes/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sku", "book-8",
                        "price", "EUR:9.50"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("book-8")
                .jsonPath("$.price").isEqualTo("EUR:9.50");
    }

    @Test
    void invalidPriceFormatReturnsBadRequest() {
        client().post()
                .uri("/api/quotes/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sku", "book-9",
                        "price", "EUR 9.50"))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void wrongJsonTokenReturnsBadRequest() {
        client().post()
                .uri("/api/quotes/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sku", "book-9",
                        "price", Map.of(
                                "currency", "EUR",
                                "amount", 9.50)))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Test dùng RANDOM_PORT thay vì port cố định, tránh va chạm trong CI. Nó kiểm tra **ObjectMapper bean** và **HTTP thật** qua Reactor Netty/WebFlux. JSONPath kiểm tra giá trị field thay vì thứ tự property trong object. Test không yêu cầu database hoặc service bên ngoài.

Với JUnit, các kết quả là **kỳ vọng logic của mã mẫu**, không phải báo cáo một lần chạy đã được thực thi sẵn trong tài liệu này. Hãy chạy lệnh test và xử lý các lỗi môi trường thật nếu có.

## 16. Chạy ví dụ và kiểm chứng bằng cURL

### 16.1 Build và test

Ở thư mục json-module-demo:

~~~bash
gradle clean test
~~~

Nếu project có Gradle wrapper:

~~~bash
./gradlew clean test
~~~

Với Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

### 16.2 Khởi động server

~~~bash
gradle bootRun
~~~

Theo cấu hình mặc định thông thường, embedded Reactor Netty lắng nghe port 8080 nếu port đó chưa được sử dụng và không có cấu hình ghi đè.

### 16.3 GET: kiểm chứng serializer

~~~bash
curl -i \
  'http://127.0.0.1:8080/api/quotes/book-7'
~~~

Kỳ vọng HTTP 200 và body tương đương:

~~~json
{"sku":"book-7","price":"USD:12.50"}
~~~

Điểm cần thấy: field price là **JSON string**, không phải JSON object có currency và amount. Đó là kết quả của PriceJsonSerializer.

### 16.4 POST: kiểm chứng deserializer và serializer

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/quotes/echo' \
  -H 'Content-Type: application/json' \
  -d '{"sku":"book-8","price":"EUR:9.50"}'
~~~

Kỳ vọng HTTP 200 và body:

~~~json
{"sku":"book-8","price":"EUR:9.50"}
~~~

Ý nghĩa: Jackson2JsonDecoder đọc JSON string của price thành một Price record. Controller trả lại Quote; Jackson2JsonEncoder ghi Price thành JSON string lần nữa. Kết quả khớp cho thấy **hai chiều** đã vận hành cùng contract.

### 16.5 POST với price không đúng định dạng

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/quotes/echo' \
  -H 'Content-Type: application/json' \
  -d '{"sku":"book-9","price":"EUR 9.50"}'
~~~

Kỳ vọng HTTP 400 vì custom deserializer từ chối dấu cách thay cho dấu hai chấm. Không khẳng định error body cụ thể, bởi Spring Boot có error handler và cấu hình hiển thị chi tiết khác nhau.

### 16.6 POST với JSON object thay cho JSON string

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/quotes/echo' \
  -H 'Content-Type: application/json' \
  -d '{"sku":"book-9","price":{"currency":"EUR","amount":9.50}}'
~~~

Kỳ vọng HTTP 400 do deserializer chỉ chấp nhận VALUE_STRING. Nếu muốn hỗ trợ cả hai định dạng để migration từ legacy API, phải triển khai tương thích rõ ràng và test cả hai; đừng silently chấp nhận mọi shape không kiểm soát.

## 17. JSON codec trong WebFlux không đồng nghĩa mọi định dạng HTTP

Trong Spring WebFlux:

- **HttpMessageReader** chọn cách đọc request body dựa trên kiểu đích và media type.
- **HttpMessageWriter** chọn cách ghi response body.
- **Jackson2JsonDecoder** và **Jackson2JsonEncoder** được dùng cho những JSON representations phù hợp.
- **ObjectMapper** quyết định kiểu Java chuyển thành những JSON tokens nào.
- **Module** cung cấp serializer/deserializer cho Java types cụ thể.

Nếu endpoint trả text/plain hoặc ứng dụng đang dùng XML/CBOR/Protobuf codec khác, custom Jackson module cho JSON không đương nhiên tham gia.

### HTTP Content-Type và Accept

Một POST muốn Jackson JSON decoder chạy thường phải gửi Content-Type: application/json đúng route contract. Với sai Content-Type, có thể nhận 415 Unsupported Media Type **trước khi** gọi PriceJsonDeserializer.

Với Accept: application/xml trong khi endpoint chỉ khai báo produces=application/json, có thể nhận 406 Not Acceptable. Đừng debug custom serializer khi request bị chặn ở tầng content negotiation.

## 18. Khi cần tùy chỉnh codec WebFlux rõ ràng

Với default Boot auto-config, đăng ký Module bean thường là đủ. Chỉ khi HTTP layer cần mapper khác hoặc custom media type mới xem tới CodecCustomizer / WebFluxConfigurer và ServerCodecConfigurer.

### 18.1 Điều chỉnh giới hạn buffering

Ví dụ:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Hoặc code:

~~~java
@Configuration
class WebFluxCodecs implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Đây là snippet minh họa: cần imports org.springframework.context.annotation.Configuration, org.springframework.web.reactive.config.WebFluxConfigurer và org.springframework.http.codec.ServerCodecConfigurer.

maxInMemorySize giới hạn việc aggregate nội dung trong memory ở một số codec, **không phải tổng giới hạn byte cho mọi body streaming**. Nếu payload JSON cần parse một object rất lớn, có thể phát sinh DataBufferLimitException hoặc lỗi codec liên quan. Khi dùng JSON streaming/NDJSON, semantics buffering khác, nên phải test đúng loại input.

### 18.2 Gắn mapper cụ thể vào Jackson2JsonEncoder/Decoder

Spring Boot 3.3 và Spring Framework 6.1 có hook CodecCustomizer. Snippet minh họa dưới đây chỉ dùng khi bạn **cố ý** yêu cầu một ObjectMapper nhất định trên WebFlux JSON HTTP codecs:

~~~java
@Bean
CodecCustomizer customJsonCodecs(ObjectMapper objectMapper) {
    return configurer -> {
        configurer.defaultCodecs().jackson2JsonEncoder(
                new Jackson2JsonEncoder(objectMapper));
        configurer.defaultCodecs().jackson2JsonDecoder(
                new Jackson2JsonDecoder(objectMapper));
    };
}
~~~

Cần imports:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.context.annotation.Bean;
~~~

**Không thêm đoạn này vào project mẫu nếu module đã hoạt động.** Việc thay decoder/encoder có thể bỏ qua những thiết lập codec khác của Boot nếu không duy trì cấu hình nhất quán (memory size, logging, streaming behavior và codec customizations). Khi tùy chỉnh codec, test HTTP thật cả hai chiều và các lỗi.

### 18.3 JSON streaming và NDJSON

Jackson encoder/decoder có khả năng xử lý các stream JSON theo cấu hình và media type được hỗ trợ, ví dụ application/x-ndjson trong một số trường hợp. Một Flux<Quote> có thể khiến serializer cho Price được gọi ở mỗi phần tử. Tuy nhiên:

- Không tự đoán kết quả chunking chỉ từ số phần tử Flux.
- JSON array và NDJSON là **hai wire formats khác nhau**.
- Backpressure không đảm bảo có thể xử lý mọi payload vô hạn mà không có giới hạn.
- Custom serializer vẫn phải stateless và không blocking.
- Test content negotiation, cancellation, memory limits và error sau response commit.

Module điều khiển JSON representation của **một type**, không tự quyết định transport chunk boundaries hay khi nào response được commit.

## 19. Jackson module trong Spring MVC

Nếu cùng kiểu Price được dùng trong một Spring MVC application với spring-boot-starter-web, Jackson thường nằm trong **MappingJackson2HttpMessageConverter** và ObjectMapper do Boot quản lý.

Đăng ký @Bean Module như ở mục 8 vẫn là lựa chọn phù hợp khi Boot auto-configure Jackson. Khác biệt là:

~~~text
Spring MVC:
  @RequestBody -> HttpMessageConverter (Jackson)
  @ResponseBody -> HttpMessageConverter (Jackson)

Spring WebFlux:
  @RequestBody -> HttpMessageReader / Jackson2JsonDecoder
  return body  -> HttpMessageWriter / Jackson2JsonEncoder
~~~

Không nên nhầm hai extension APIs. Không gọi WebMvcConfigurer.configureMessageConverters trong một WebFlux-only application rồi kỳ vọng thay WebFlux Jackson codec. Ngược lại, WebFluxConfigurer.configureHttpMessageCodecs không điều chỉnh Servlet MVC converter.

**Kiểm thử:** MVC dùng MockMvc trong nhiều trường hợp; WebFlux dùng WebTestClient. Với cả hai, test HTTP response body và invalid JSON request giúp xác minh module đến đúng mapper.

## 20. Module scope, serializer scope và KeyDeserializer

Custom module trong ví dụ đăng ký serializer/deserializer **cho values có kiểu Price**. Nếu bạn có:

~~~java
Map<Price, String> data
~~~

thì Price xuất hiện trong **JSON object key**, không phải value. JSON object keys là chuỗi, và Jackson dùng cơ chế key serializers/deserializers riêng. JsonSerializer<Price> dành cho object values chưa đủ để bảo đảm Map<Price, String> hoạt động theo hợp đồng mong đợi.

Jackson SimpleModule có các API liên quan:

~~~java
module.addKeySerializer(Price.class, ...);
module.addKeyDeserializer(Price.class, ...);
~~~

Dấu "..." ở đây là **placeholder API minh họa, không phải Java code có thể biên dịch**. Nếu không có use case Map key, không cần đăng ký key serializer. Nếu có, phải thiết kế escaping, format và object key uniqueness rõ ràng, nhất là nếu hai Price values khác nhau có thể tạo cùng key text.

Các kiểu container có thể gặp:

- List<Price>: module dùng value serializer/deserializer cho từng phần tử.
- Quote chứa Price: module dùng cho field price.
- Optional<Price>: phụ thuộc cấu hình Jackson JDK8 module và API contract.
- Map<String, Price>: module dùng value handling.
- Map<Price, String>: cần xem key handling; không tự lấy value serializer.
- Generic wrapper<T>: cần kiểm tra type information, Jackson JavaType và generic binding.

## 21. Jackson null, absent, default và unknown properties

JSON có nhiều trạng thái:

~~~json
{}
~~~

~~~json
{"price":null}
~~~

~~~json
{"price":"USD:0.00"}
~~~

Chúng **không tương đương**:

- Missing price: DTO có thể nhận null, default hoặc fail tùy creator/validation/Jackson setup.
- Explicit null: null-handling có thể bypass deserializer cho Price.
- Price hợp lệ 0.00: là một object Price đầy đủ.

Nếu price required, nên thiết kế request DTO và validation rõ ràng. Với Spring Boot 3.3, khi dùng Jakarta Bean Validation, thêm spring-boot-starter-validation khi cần provider, rồi test annotation @Valid/constraints đúng stack.

### Unknown fields

Jackson trong Spring Boot 3.3 mặc định có một số cấu hình khác Jackson new ObjectMapper thuần, ví dụ FAIL_ON_UNKNOWN_PROPERTIES thường bị tắt trong mapper được builder cấu hình theo Boot. Nếu muốn reject unknown JSON fields, cần quyết định policy rõ ràng và test với API contract.

Không coi việc không fail khi có extra fields là bằng chứng deserializer Price sai: unknown property handling có thể xảy ra ở DTO level trước hoặc ngoài custom value deserializer.

## 22. Thread safety, hiệu năng và bảo mật

### 22.1 Cấu hình module lúc startup

ObjectMapper thông thường được sử dụng đồng thời từ nhiều request. Theo hướng dẫn Jackson, nó phù hợp chia sẻ khi mọi cấu hình được hoàn tất **trước** lần read/write đầu tiên. Không thay module/serializer trên một mapper singleton đang phục vụ request đồng thời rồi giả định cache được cập nhật an toàn.

### 22.2 Serializer/deserializer nên stateless

Không giữ dữ liệu của request này trong instance field để dùng cho request kế tiếp. Dùng biến local trong serialize/deserialize. Pattern tĩnh immutable như trong ví dụ có thể dùng chung an toàn.

### 22.3 Không block reactive event loop

Trong Spring WebFlux, JSON decode/encode có thể chạy trên reactive pipeline gắn với event-loop threads. Tránh database lookup, HTTP call, Thread.sleep hoặc file I/O blocking trong JsonSerializer/JsonDeserializer. Đây không phải nơi thích hợp để validate quyền truy cập của user bằng một repository sync.

### 22.4 Không bật polymorphic default typing tùy tiện

Không dùng ObjectMapper.activateDefaultTyping với dữ liệu từ client không đáng tin mà không hiểu cơ chế subtype validators và security implications. Polymorphic deserialization rộng có thể dẫn tới rủi ro nghiêm trọng khi cho phép Jackson tạo các class không mong muốn. Với API REST, ưu tiên DTO rõ type và whitelist polymorphic subtypes khi cần.

### 22.5 Giới hạn kích thước và độ phức tạp JSON

Một JSON document có thể quá lớn, quá sâu hoặc chứa chuỗi/số rất dài. Trong production:

- Đặt giới hạn request body phù hợp ở gateway/server/codec.
- Test max-in-memory-size của WebFlux nếu decoder aggregate body.
- Sử dụng Jackson StreamReadConstraints khi version/requirements phù hợp.
- Tránh regex backtracking phức tạp trên chuỗi unbounded.
- Tránh recursive serialization trên object graph tuần hoàn mà không có policy.
- Không log raw payload chứa token, thông tin người dùng hoặc nội dung nhạy cảm.
- Thiết kế timeout, cancellation và error response hợp lý.

### 22.6 BigDecimal cho giá trị decimal

Từ BigDecimal(String) thay vì BigDecimal(double) để tránh sai số do floating point khi tạo số tiền. Đừng chuyển tiền tệ sang double chỉ để serializer dễ viết. Nhưng cũng không coi two-decimal example là quy tắc đúng cho mọi currency thực tế.

## 23. Test serializer/deserializer độc lập và qua HTTP khác nhau ra sao?

| Mức test | Điều xác minh | Không đủ để kết luận |
| --- | --- | --- |
| Unit test với ObjectMapper có module do test tạo | Logic serial/deserial hoạt động | Boot auto-registration |
| Test @Autowired ObjectMapper trong Spring context | Module được gắn vào mapper do Boot tạo | WebFlux HTTP codec chắc chắn dùng cùng mapper nếu có custom codec |
| WebTestClient bindToServer + RANDOM_PORT | HTTP request/response thật qua embedded server và codec | Mọi proxy hoặc client môi trường production giống local |
| MockMvc trong MVC | Servlet handler + message converter với mock request | TCP socket thật đã mở |
| Contract/integration test giữa các service | Wire format tương thích client/server | Tính chính xác nghiệp vụ bên ngoài contract |

Bài mẫu dùng **ObjectMapper bean + WebTestClient HTTP**. Đây là lớp bảo vệ tốt khi nâng phiên bản Boot/Jackson hoặc đổi việc đăng ký codec.

### Test nên thêm cho project thực tế

- Input null, missing property và empty string.
- Invalid currency, chữ thường, negative amount, quá nhiều decimal digits.
- JSON number/object/array thay cho string.
- Ràng buộc size của JSON body.
- Locale có ảnh hưởng không (ví dụ locale tr_TR không làm đổi currency wire format).
- Serializer/deserializer round-trip qua DTO lồng nhau.
- Hành vi khi proxy/client gửi Content-Type hoặc Accept không phù hợp.
- Test tương thích ngược nếu API trước đây dùng JSON object.
- Test thread safety với nhiều requests khi code custom có logic phức tạp.
- Test hợp đồng OpenAPI/schema để client nhận đúng JSON type string.

## 24. Những lỗi phổ biến và cách sửa

### Lỗi 1: Đăng ký module trên mapper khác mapper của HTTP codec

Triệu chứng: test với new ObjectMapper().registerModule(...) PASS nhưng WebFlux endpoint vẫn trả JSON object thay vì string.

Cách xử lý: dùng @Bean Module qua Boot configuration, kiểm tra ObjectMapper được inject, kiểm tra codec custom có dùng mapper riêng và test HTTP thật.

### Lỗi 2: Chỉ đăng ký serializer, quên deserializer

Triệu chứng: GET trả "USD:12.50" nhưng POST cùng field thất bại hoặc Jackson cố khởi tạo Price từ string theo default deserializer không phù hợp.

Cách xử lý: addDeserializer(Price.class, ...) và test POST, không chỉ GET.

### Lỗi 3: Quên @Bean hoặc package không được component scan

Triệu chứng: class PriceJacksonConfiguration tồn tại trong source nhưng Spring không đăng ký bean Module.

Cách xử lý: xác minh @Configuration, @Bean và package nằm dưới package của @SpringBootApplication, hoặc khai báo @Import phù hợp.

### Lỗi 4: Tự tạo ObjectMapper mới trong controller

Triệu chứng: HTTP converter và ObjectMapper trong service cho kết quả khác, hoặc Java Time modules bị thiếu.

Cách xử lý: dùng mapper được Boot quản lý hoặc builder cấu hình nhất quán; không new ObjectMapper() tại mỗi request.

### Lỗi 5: Dùng @EnableWebFlux để “bật” serializer

Triệu chứng: thay đổi auto-configuration hoặc hành vi endpoint ngoài mong muốn.

Cách xử lý: bỏ @EnableWebFlux nếu chỉ cần thêm Module bean trong Spring Boot.

### Lỗi 6: Dùng JsonSerializer cho object keys

Triệu chứng: Map<Price, String> serialize không như mong muốn.

Cách xử lý: xem KeySerializer/KeyDeserializer; không nhầm value serializer với key serializer.

### Lỗi 7: Parse number qua double

Triệu chứng: số tiền mất precision hoặc tạo chuỗi thập phân khác hợp đồng.

Cách xử lý: BigDecimal từ String và toPlainString theo scale/rounding policy đã document.

### Lỗi 8: Bắt mọi lỗi rồi trả null

Triệu chứng: JSON invalid thành object thiếu dữ liệu, controller trả 500 hoặc xử lý sai nghiệp vụ.

Cách xử lý: throw JsonMappingException/InvalidFormatException đúng ngữ nghĩa; validation required fields ở DTO/service layer.

### Lỗi 9: Đọc JSON body khi Content-Type không phù hợp

Triệu chứng: POST bị 415 trước khi chạy deserializer.

Cách xử lý: xác nhận consumes/Content-Type, body JSON syntax và HTTP codec lựa chọn.

### Lỗi 10: Không test kiểu nested DTO

Triệu chứng: serialize Price trực tiếp thành string nhưng nested Quote.price vẫn khác do annotations, mapper hoặc custom configuration.

Cách xử lý: test direct Price và nested Quote qua actual HTTP endpoints.

### Lỗi 11: Giả định custom serializer cũng tự validate null

Triệu chứng: price:null vẫn được chấp nhận.

Cách xử lý: thiết kế null policy và @NotNull/DTO validation hoặc custom NullValue handling khi thực sự cần.

### Lỗi 12: Thay global mapper khi chỉ cần một field

Triệu chứng: nhiều API không liên quan thay đổi wire format.

Cách xử lý: cân nhắc property-level @JsonSerialize/@JsonDeserialize hoặc DTO-specific mapper/module có phạm vi rõ ràng.

### Lỗi 13: Áp dụng ví dụ Jackson 2 vào Spring Boot 4/Jackson 3

Triệu chứng: package/class/API không khớp với dependency hiện tại.

Cách xử lý: xác định chính xác major version, API JsonMapper/Jackson 3, Spring Framework và Boot docs tương ứng trước khi port code.

## 25. Checklist triển khai production

1. Xác định JSON contract đang có và backward compatibility.
2. Cân nhắc Jackson annotations/config mặc định trước khi viết serializer mới.
3. Chọn đúng kiểu Java muốn customize, không bắt tất cả Object.class.
4. Chốt format và quy tắc invalid/null.
5. Viết serializer dùng JsonGenerator, tránh raw string concatenation cho JSON tokens.
6. Viết deserializer kiểm tra token, format và phát exception rõ ràng.
7. Dùng BigDecimal/Java Time đúng ý nghĩa nghiệp vụ, tránh chuyển sang double/String bừa bãi.
8. Gói hai chiều trong SimpleModule.
9. Đăng ký Module bean ở package được Spring Boot component scan.
10. Không tự thay ObjectMapper/HTTP codecs nếu cấu hình Boot mặc định đã đủ.
11. Viết test @Autowired ObjectMapper cho cả chiều đọc và ghi.
12. Viết HTTP integration tests qua WebTestClient/MockMvc.
13. Test malformed JSON, wrong token, null, missing và Content-Type/Accept.
14. Giữ serializer/deserializer stateless và không blocking.
15. Đặt giới hạn kích thước body, codec memory và parser depth theo use case.
16. Bảo vệ dữ liệu nhạy cảm, không log nguyên request body tùy tiện.
17. Document JSON field type và mẫu hợp đồng trong OpenAPI.
18. Kiểm tra JSON behavior sau khi nâng Boot/Jackson modules.
19. Khi dùng WebFlux, phân biệt codec configuration với MVC message converter.
20. Quan sát error rate, throughput và latency sau khi thêm custom serialization.

## 26. Tóm tắt

**JsonSerializer** giải quyết chiều Java → JSON; **JsonDeserializer** giải quyết chiều JSON → Java; **SimpleModule** đóng gói hai chiều để đăng ký vào Jackson **ObjectMapper**. Trong Spring Boot 3.3, cách tích hợp thuận tiện là khai báo một **@Bean Module** và để Jackson auto-configuration áp dụng nó tới mapper được framework quản lý.

Trong WebFlux, việc ghi/đọc body tiếp tục được quản lý bởi **Jackson2JsonEncoder / Jackson2JsonDecoder** và HTTP message codecs. Custom module thay representation của kiểu Java, không thay HTTP protocol hoặc tự xử lý media type. Cách kiểm chứng đáng tin nhất là test cả **ObjectMapper bean** lẫn **HTTP POST/GET qua server**, đặc biệt khi ứng dụng có custom codecs.

Bài thực hành cho Price với JSON string "USD:12.50" cho thấy module có thể làm một domain type được biểu diễn nhất quán ở cả request và response. Nhưng một global change cần được quản lý như thay đổi API contract: xác định null policy, validation, error status, backward compatibility và client expectations trước khi triển khai.

## 27. Tài liệu tham khảo

- Spring Boot 3.3 — JSON và @JsonComponent: https://docs.spring.io/spring-boot/3.3/reference/features/json.html
- Spring Boot 3.3 — Spring MVC và Jackson configuration: https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html
- Spring Boot 3.3 — Reactive Web Applications / HTTP Codecs: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Framework 6.1 — WebFlux Configuration: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/config.html
- Jackson 2 — Module API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/Module.html
- Jackson 2 — SimpleModule API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/module/SimpleModule.html
- Jackson 2 — JsonSerializer / JsonDeserializer: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/index.html
- Jackson databind — Introduction and usage: https://github.com/FasterXML/jackson-databind
