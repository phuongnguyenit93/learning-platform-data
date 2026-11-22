# Quản lý module, annotation và cấu hình Jackson trong ứng dụng

Trong ứng dụng Spring, Jackson thường được dùng ở nhiều nơi: REST request/response, cấu hình JSON, message broker, cache và file import/export. Nếu mỗi service tự tạo một ObjectMapper, các phần của ứng dụng có thể xử lý cùng một dữ liệu theo những quy tắc khác nhau: nơi hiểu timestamp thành chuỗi, nơi khác lại ghi epoch; nơi đăng ký JavaTimeModule, nơi khác không; nơi bỏ qua field lạ, nơi khác từ chối.

Spring Boot cung cấp một mapper được cấu hình tập trung và các điểm mở rộng để đăng ký module, customizer, serializer/deserializer và mix-in. Muốn cấu hình ổn định, cần biết mỗi cơ chế tác động ở phạm vi nào và bảo đảm HTTP converter thực sự dùng mapper đã cấu hình.

Bài học này tập trung vào ứng dụng Spring dùng Jackson 2.x, thường gặp trong Spring Boot 2.x/3.x. Một số tên API và package trong ví dụ là API Jackson 2/Spring Boot 3; khi dự án chuyển sang release line Spring Boot/Jackson 3, cần dùng dependency và integration API tương ứng của phiên bản đó thay vì trộn hai thế hệ.

## 1. Jackson tham gia vào request/response Spring như thế nào?

Trong Spring MVC, request body và response body thường đi qua HttpMessageConverter. Jackson được dùng bởi converter JSON để chuyển đổi giữa HTTP body và Java object.

~~~text
HTTP request body (JSON)
          |
          v
MappingJackson2HttpMessageConverter
          |
          v
     ObjectMapper
          |
          v
      Java DTO
          |
       Controller
          |
          v
      Java DTO
          |
          v
     ObjectMapper
          |
          v
MappingJackson2HttpMessageConverter
          |
          v
HTTP response body (JSON)
~~~

Vì vậy, cấu hình đúng một ObjectMapper trong test nhưng để MVC dùng mapper khác sẽ tạo ra hành vi không nhất quán.

Spring Boot auto-configures các thành phần Jackson khi Jackson có trên classpath. Với ứng dụng Spring Boot dùng Jackson 2, thường có thể inject ObjectMapper được quản lý bởi Spring context:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final ObjectMapper mapper;

    public OrderController(ObjectMapper mapper) {
        this.mapper = mapper;
    }
}
~~~

Trong controller thực tế, không cần tự serialize response bằng mapper nếu Spring MVC đã trả DTO qua message converter. Việc inject mapper hữu ích cho những tác vụ JSON khác như đọc file hoặc tạo payload nội bộ.

## 2. Dependency và version alignment

Với Spring Boot, ưu tiên dependency management do Spring Boot cung cấp. Không ghim một version Jackson riêng lẻ nếu không có lý do tương thích cụ thể.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
~~~

Trong nhiều cấu hình Spring Boot, starter web đã kéo Jackson Databind và các thành phần cần thiết. Module Java Time có thể được tự phát hiện khi có trên classpath hoặc được đăng ký bởi auto-configuration, tùy release line và cấu hình ứng dụng.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Nếu dự án không dùng starter web nhưng cần Jackson, có thể khai báo module tương ứng:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

Các module thường gặp:

| Artifact | Công dụng |
|---|---|
| `jackson-datatype-jsr310` | Java Time: Instant, LocalDate, OffsetDateTime |
| `jackson-datatype-jdk8` | Optional và một số kiểu JDK 8 |
| `jackson-module-parameter-names` | Đọc tên tham số constructor từ metadata |
| `jackson-module-kotlin` | Hỗ trợ Kotlin data class và nullability |
| `jackson-dataformat-yaml` | Đọc/ghi YAML |
| `jackson-dataformat-cbor` | Đọc/ghi CBOR |
| `jackson-dataformat-smile` | Đọc/ghi Smile |

Giữ các module Jackson trên cùng release line. Nếu Spring Boot quản lý dependency bằng BOM, hãy để BOM chọn phiên bản tương thích. Kiểm tra dependency tree khi có module bị kéo về version khác.

## 3. ObjectMapper do Spring Boot quản lý

Trong ứng dụng Boot, mapper auto-configured được xây dựng từ Jackson builder và các cấu hình trong ApplicationContext.

Lợi ích:

- Controller và message converter có thể dùng chung quy tắc JSON.
- Các Jackson Module bean có thể được đăng ký tập trung.
- Các property `spring.jackson.*` được áp dụng ở startup.
- Customizer có thể thay đổi builder theo cấu hình ứng dụng.
- Test có thể inject cùng mapper mà ứng dụng dùng.

Không nên tạo mapper mới ở mọi service:

~~~java
// Tránh tạo mapper mới trong từng method.
ObjectMapper mapper = new ObjectMapper();
~~~

Mapper này có thể thiếu JavaTimeModule, Kotlin module, naming strategy hoặc custom serializer mà Spring Boot đã cấu hình.

Thay vào đó, inject mapper hoặc inject builder nếu thật sự cần tạo mapper theo một mục đích riêng:

~~~java
@Service
public class JsonFileService {
    private final ObjectMapper mapper;

    public JsonFileService(ObjectMapper mapper) {
        this.mapper = mapper;
    }
}
~~~

Nếu một ứng dụng có nhiều contract khác nhau, có thể tạo mapper riêng cho từng format/contract, nhưng cần đặt tên bean và phạm vi sử dụng rõ ràng. Không dùng mapper phụ một cách vô tình cho HTTP API.

## 4. Cấu hình cơ bản bằng application.yml

Spring Boot hỗ trợ nhóm property `spring.jackson.*`. Các property này là cách ngắn gọn để cấu hình mapper auto-configured.

Ví dụ:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
    time-zone: UTC
    serialization:
      indent-output: false
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: true
    mapper:
      accept-case-insensitive-enums: true
~~~

Ý nghĩa:

- `default-property-inclusion: non_null`: bỏ property có giá trị null khi serialize.
- `time-zone: UTC`: cấu hình timezone cho các kiểu/formatter có sử dụng timezone.
- `write-dates-as-timestamps: false`: ưu tiên date/time string thay vì timestamp number cho các kiểu được feature này điều khiển.
- `fail-on-unknown-properties: true`: từ chối JSON có property không được DTO nhận diện.
- `accept-case-insensitive-enums: true`: cho phép enum input không phân biệt chữ hoa/chữ thường theo mapper feature tương ứng.

Đây là cấu hình cấp ứng dụng. Trước khi bật FAIL_ON_UNKNOWN_PROPERTIES, cần xem API có chủ đích chấp nhận field mới từ client cũ hay không. Ngược lại, nếu payload là command/config cần strict schema, từ chối field lạ có thể giúp phát hiện lỗi đánh máy.

Property names và nhóm feature được hỗ trợ có thể thay đổi giữa Spring Boot/Jackson release line. Kiểm tra metadata configuration của đúng version dự án, không giả định mọi property trong ví dụ có mặt ở mọi phiên bản.

## 5. Jackson2ObjectMapperBuilderCustomizer

Khi cấu hình cần Java code, Spring Boot cung cấp `Jackson2ObjectMapperBuilderCustomizer` để thay đổi builder trước khi ObjectMapper được tạo.

~~~java
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.fasterxml.jackson.databind.SerializationFeature;

@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            );
        };
    }
}
~~~

Customizer phù hợp khi cần:

- Thêm hoặc tắt một feature.
- Cấu hình naming strategy.
- Đăng ký mix-in.
- Điều chỉnh visibility.
- Cấu hình serializer/deserializer hoặc handler chung.
- Áp dụng quy tắc nhất quán cho mapper được tạo từ builder đó.

Customizer chỉ tác động đến builder mà Spring Boot dùng. Một `new ObjectMapper()` tự tạo ở nơi khác không tự nhận các thay đổi này.

Nếu có nhiều customizer, thứ tự thực hiện có thể ảnh hưởng kết quả. Có thể dùng `@Order`/`Ordered` khi cần thứ tự rõ ràng, và nên giữ số lượng customizer nhỏ để tránh cấu hình bị ghi đè khó truy tìm.

## 6. Đăng ký Jackson Module dưới dạng Spring bean

Một cách mở rộng quan trọng là khai báo bean kiểu `com.fasterxml.jackson.databind.Module`. Spring Boot đưa các module bean vào builder auto-configured.

Ví dụ đăng ký `JavaTimeModule`:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonModuleConfiguration {

    @Bean
    Module javaTimeModule() {
        return new JavaTimeModule();
    }
}
~~~

Nếu ứng dụng có custom serializer, có thể tạo `SimpleModule`:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MoneyModuleConfiguration {

    @Bean
    Module moneyModule() {
        SimpleModule module = new SimpleModule("money-module");
        module.addSerializer(Money.class, new MoneySerializer());
        module.addDeserializer(Money.class, new MoneyDeserializer());
        return module;
    }
}
~~~

Boot có thể đăng ký mọi bean kiểu Jackson Module với builder auto-configured. Module đó sẽ được dùng bởi mapper được tạo từ builder. Một mapper được tạo thủ công bằng `new ObjectMapper()` không tự động nhận bean này.

Không đăng ký cùng một serializer/deserializer theo nhiều đường nếu không cần thiết. Nếu cùng một type được đăng ký bởi annotation, module và mix-in, cần hiểu precedence và kiểm thử mapper thực tế.

## 7. Tạo custom serializer và deserializer

Ví dụ kiểu Money cần biểu diễn theo hợp đồng riêng:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

JSON contract:

~~~json
{
  "amount": "1250.50",
  "currency": "VND"
}
~~~

Serializer:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("amount", value.amount().toPlainString());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Deserializer:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonNode;

import java.io.IOException;
import java.math.BigDecimal;

public class MoneyDeserializer extends JsonDeserializer<Money> {

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonNode node = parser.getCodec().readTree(parser);

        String amountText = node.path("amount").asText(null);
        String currency = node.path("currency").asText(null);

        if (amountText == null || currency == null) {
            throw JsonMappingException.from(
                parser,
                "Money requires amount and currency"
            );
        }

        return new Money(new BigDecimal(amountText), currency);
    }
}
~~~

Deserializer production nên xác thực currency, scale, số âm và field không hợp lệ theo nghiệp vụ. Không dùng asText() để âm thầm chuyển mọi kiểu JSON thành string nếu contract yêu cầu field phải là JSON string.

Sau khi đăng ký MoneyModule bean, mapper Spring Boot có thể sử dụng serializer/deserializer đó khi xử lý Money.

## 8. @JsonComponent cho serializer/deserializer theo phong cách Spring Boot

Spring Boot có `@JsonComponent` để phát hiện serializer/deserializer thông qua component scanning và đăng ký chúng với Jackson.

Ví dụ:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import org.springframework.boot.jackson.JsonComponent;

import java.io.IOException;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers) throws IOException {

            generator.writeStartObject();
            generator.writeStringField("amount", value.amount().toPlainString());
            generator.writeStringField("currency", value.currency());
            generator.writeEndObject();
        }
    }
}
~~~

`@JsonComponent` thuận tiện khi serializer/deserializer thuộc ứng dụng Spring Boot và cần được component scan. Nếu muốn module có thể tái sử dụng ngoài Spring, `SimpleModule` hoặc module Jackson độc lập thường phù hợp hơn.

Đừng nhầm `@JsonComponent` với `@JsonSerialize` hoặc `@JsonDeserialize`:

- `@JsonComponent` là cơ chế phát hiện component của Spring Boot.
- `@JsonSerialize` và `@JsonDeserialize` là annotation Jackson gắn trên type/property để chỉ định serializer/deserializer.

## 9. Annotation Jackson điều khiển contract ở cấp model

Annotation phù hợp khi quy tắc thuộc về một model hoặc một property cụ thể.

| Annotation | Mục đích |
|---|---|
| `@JsonProperty` | Đặt tên JSON hoặc access direction |
| `@JsonIgnore` | Bỏ qua property |
| `@JsonInclude` | Quy định khi nào property xuất hiện |
| `@JsonFormat` | Định dạng ngày giờ hoặc kiểu hỗ trợ |
| `@JsonCreator` | Chọn constructor/factory để tạo object |
| `@JsonAlias` | Chấp nhận tên property thay thế khi đọc |
| `@JsonTypeInfo` | Đưa discriminator/type metadata vào JSON |
| `@JsonView` | Chọn nhóm property cho view |
| `@JsonIgnoreProperties` | Bỏ qua hoặc xử lý nhóm property theo cấu hình |

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record UserResponse(
    @JsonProperty("user_name") String username,
    String displayName,
    String internalNote
) {}
~~~

Không dùng annotation để thay thế authorization. Ví dụ `@JsonView` không tự kiểm tra caller có quyền xem dữ liệu hay không; server phải chọn view theo quyền đã xác thực.

Annotation trên entity dùng chung cho nhiều endpoint có thể tạo contract khó kiểm soát. DTO riêng thường phù hợp hơn khi public response và internal model có mục đích khác nhau.

## 10. Dùng mix-in cho class bên thứ ba

Không phải lúc nào cũng sửa được source class. Mix-in cho phép Jackson áp dụng annotation từ một class khác lên target type.

Giả sử thư viện có class:

~~~java
public class ExternalUser {
    public String getName() { /* ... */ }
    public String getSecret() { /* ... */ }
}
~~~

Mixin:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public abstract class ExternalUserMixin {
    @JsonIgnore
    abstract String getSecret();
}
~~~

Đăng ký qua builder customizer:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer externalUserMixin() {
    return builder -> builder.mixIn(
        ExternalUser.class,
        ExternalUserMixin.class
    );
}
~~~

Mix-in hữu ích khi:

- Class đến từ dependency ngoài.
- Không muốn hoặc không thể sửa model gốc.
- Cần thay đổi annotation behavior cho một mapper cụ thể.
- Muốn giữ Jackson-specific metadata ngoài domain model.

Mixin vẫn là cấu hình của mapper. Nếu một mapper khác không đăng ký mix-in, nó sẽ không áp dụng quy tắc đó.

## 11. Tên property và naming strategy

Nếu API dùng snake_case còn Java dùng camelCase, có thể cấu hình naming strategy:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer namingCustomizer() {
    return builder -> builder.propertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE
    );
}
~~~

Java:

~~~java
public record UserProfile(String firstName, String lastName) {}
~~~

JSON:

~~~json
{
  "first_name": "An",
  "last_name": "Nguyen"
}
~~~

Naming strategy là quy tắc toàn mapper. Nếu chỉ một property có tên wire đặc biệt, dùng `@JsonProperty` tường minh thay vì thay đổi tên mọi property.

Khi chuyển đổi API cũ, có thể dùng `@JsonAlias` để chấp nhận tên cũ khi deserialize trong giai đoạn migration:

~~~java
public class UserRequest {
    @JsonAlias("firstName")
    private String first_name;
}
~~~

Cần phân biệt tên chuẩn dùng khi serialize với alias chỉ dùng để nhận input. Không duy trì alias vĩnh viễn nếu không còn consumer cũ.

## 12. Date/time module và cấu hình thời gian

Đối với Java Time, thêm module tương ứng và cấu hình rõ format:

~~~java
@Bean
Module javaTimeModule() {
    return new JavaTimeModule();
}

@Bean
Jackson2ObjectMapperBuilderCustomizer timeCustomizer() {
    return builder -> builder.featuresToDisable(
        SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
    );
}
~~~

Với cấu hình này, các kiểu Java Time được module hỗ trợ thường được serialize thành chuỗi ISO tương ứng thay vì timestamp number.

Ví dụ DTO:

~~~java
public record EventResponse(
    String name,
    Instant occurredAt
) {}
~~~

JSON:

~~~json
{
  "name": "created",
  "occurredAt": "2026-11-12T10:30:00Z"
}
~~~

Đừng chỉ dựa vào property spring.jackson.time-zone để biến LocalDateTime thành instant. LocalDateTime không chứa timezone hoặc offset. Chọn đúng Java Time type theo ý nghĩa dữ liệu và công bố format trong API schema.

## 13. Unknown properties và forward compatibility

`FAIL_ON_UNKNOWN_PROPERTIES` quyết định Databind phản ứng ra sao khi JSON chứa field mà DTO không nhận diện.

Strict mode:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Hoặc qua customizer:

~~~java
builder.featuresToEnable(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
~~~

Có thể bỏ qua field lạ trên một DTO cụ thể:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerPayload {
    private String id;
}
~~~

Lựa chọn phụ thuộc contract:

- Strict mode phù hợp với command/config cần phát hiện sai tên field.
- Ignore unknown có thể hữu ích khi nhận payload từ provider thường xuyên thêm field.
- DTO nội bộ nên có policy rõ ràng, không bật ignore toàn cục chỉ để một integration hết lỗi.

Nếu client gửi sai tên field quan trọng và server âm thầm bỏ qua, request có thể thành công nhưng dữ liệu không được cập nhật như mong muốn. Hãy test cả trường hợp typo và field mới hợp lệ.

## 14. Nhiều ObjectMapper trong một ứng dụng

Một ứng dụng có thể cần mapper khác nhau cho:

- Public HTTP API.
- Payload của đối tác.
- YAML config.
- Event message.
- Cache snapshot.
- Canonical JSON hoặc format ký số.

Không nên thay đổi một mapper dùng chung theo từng request. Cấu hình mapper trước khi sử dụng và tạo bean riêng khi contract thật sự khác nhau.

Ví dụ bean riêng:

~~~java
@Configuration
public class PartnerJsonConfiguration {

    @Bean("partnerObjectMapper")
    ObjectMapper partnerObjectMapper(
            Jackson2ObjectMapperBuilder builder) {

        return builder
            .featuresToEnable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
            )
            .build();
    }
}
~~~

Inject bằng qualifier:

~~~java
@Service
public class PartnerClient {
    private final ObjectMapper partnerMapper;

    public PartnerClient(
            @Qualifier("partnerObjectMapper") ObjectMapper partnerMapper) {
        this.partnerMapper = partnerMapper;
    }
}
~~~

Dùng builder được Spring cấu hình để giữ lại các module và defaults cần thiết. Tuy nhiên, bean riêng này vẫn có thể cần thêm các customizer hoặc feature riêng của integration. Không giả định mọi customizer sẽ được áp dụng lại khi gọi builder.build() từ một builder đã được inject; builder được cấu hình tại startup và module beans có thể đã được gắn vào.

Nếu cần mapper riêng hoàn toàn, khai báo rõ dependency, module và features thay vì dùng `new ObjectMapper()` rải rác.

`ObjectMapper` có thể được chia sẻ giữa các thread sau khi cấu hình hoàn tất. Không thay đổi feature, module hoặc mix-in trên mapper đang phục vụ request đồng thời. Dùng `ObjectReader`/`ObjectWriter` cho các biến thể thao tác theo từng lần đọc/ghi:

~~~java
ObjectReader strictReader = mapper
    .readerFor(PartnerPayload.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter prettyWriter = mapper
    .writer()
    .with(SerializationFeature.INDENT_OUTPUT);
~~~

Reader và writer là lựa chọn tốt cho cấu hình theo operation mà không phải mutate mapper gốc.

## 15. MVC message converter phải dùng đúng mapper

Spring MVC dùng `HttpMessageConverter` để đọc và ghi body. Nếu thay converter thủ công, có thể vô tình bỏ mất converter mặc định hoặc tạo một converter với mapper khác.

Khi chỉ cần tùy chỉnh converter hiện có, có thể mở rộng danh sách bằng `extendMessageConverters`:

~~~java
@Configuration
public class WebJsonConfiguration implements WebMvcConfigurer {

    private final ObjectMapper mapper;

    public WebJsonConfiguration(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {

        converters.stream()
            .filter(MappingJackson2HttpMessageConverter.class::isInstance)
            .map(MappingJackson2HttpMessageConverter.class::cast)
            .forEach(converter -> converter.setObjectMapper(mapper));
    }
}
~~~

Đoạn code này minh họa việc gắn mapper vào các Jackson converter hiện có. Trong một ứng dụng Boot đã auto-configure đúng mapper, thường không cần lặp lại bước này.

Cẩn thận với `configureMessageConverters`: tùy cách triển khai, việc thêm converter ở đây có thể thay thế hoặc ảnh hưởng danh sách mặc định. Chỉ override khi hiểu đầy đủ thứ tự và content negotiation.

Kiểm thử bằng MockMvc hoặc HTTP integration test để chứng minh request/response thực sự dùng naming strategy, module và annotation mong muốn.

## 16. Spring WebFlux và codec

Spring WebFlux không dùng MVC HttpMessageConverter theo cùng cách; nó sử dụng codec cho đọc/ghi body. Jackson được tích hợp qua Jackson JSON encoder/decoder tương ứng.

Nếu ứng dụng WebFlux cần cấu hình codec riêng, sử dụng cơ chế CodecConfigurer/ServerCodecConfigurer hoặc customizer do Spring Boot cung cấp trong release line của dự án. Đảm bảo encoder và decoder nhận đúng mapper đã cấu hình.

Không lấy cấu hình MVC converter rồi áp dụng nguyên xi cho WebFlux. Hai stack có extension point khác nhau. Kiểm thử bằng WebTestClient để xác nhận wire JSON thực tế.

## 17. Cấu hình serializer/deserializer bằng annotation hay Module?

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Một property có format riêng | `@JsonFormat`, `@JsonSerialize`, `@JsonDeserialize` |
| Quy tắc thuộc về model | Annotation Jackson |
| Class bên thứ ba cần annotation | Mix-in |
| Kiểu nghiệp vụ dùng chung nhiều DTO | Jackson `Module` |
| Serializer thuộc Spring Boot app | `@JsonComponent` |
| Defaults toàn ứng dụng | `spring.jackson.*` |
| Cấu hình Java trên builder | `Jackson2ObjectMapperBuilderCustomizer` |
| Cấu hình riêng cho một lần đọc/ghi | `ObjectReader` / `ObjectWriter` |
| Contract HTTP khác nhau | Mapper/codec/converter riêng có qualifier |

Chọn điểm mở rộng theo phạm vi. Nếu một kiểu Money luôn phải có representation duy nhất trong mọi nơi, module dùng chung có thể phù hợp. Nếu chỉ một API legacy có format khác, dùng DTO/annotation/mapper riêng để không ảnh hưởng API khác.

## 18. Kiểm thử cấu hình Jackson trong Spring

Không chỉ test `new ObjectMapper()` trong unit test. Cần test mapper do Spring tạo và, khi cần, test cả HTTP layer.

### 18.1. @JsonTest cho serialization slice

Spring Boot có `@JsonTest` để cấu hình test slice cho JSON serialization:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;

@JsonTest
class UserJsonTest {

    @Autowired
    ObjectMapper mapper;

    @Test
    void usesConfiguredNamingStrategy() throws Exception {
        UserProfile user = new UserProfile("An", "Nguyen");

        String json = mapper.writeValueAsString(user);

        assertThat(json).contains("\"first_name\":\"An\"");
        assertThat(json).contains("\"last_name\":\"Nguyen\"");
    }
}
~~~

`@JsonTest` phù hợp để kiểm tra module, annotation và serialization behavior trong slice. Nếu customizer/bean của ứng dụng không được load trong test slice do package/import cấu hình, hãy import cấu hình cần thiết vào test hoặc dùng context test đầy đủ.

### 18.2. @SpringBootTest để kiểm tra toàn bộ context

Dùng `@SpringBootTest` khi cần xác nhận:

- Customizer được đăng ký.
- Module bean có mặt.
- Mapper được auto-configure đúng.
- Qualifier chọn đúng mapper.
- Cấu hình profile/property được áp dụng.

~~~java
@SpringBootTest
class JacksonContextTest {

    @Autowired
    ObjectMapper mapper;

    @Test
    void mapperCanSerializeJavaTime() throws Exception {
        String json = mapper.writeValueAsString(
            Instant.parse("2026-11-12T10:30:00Z")
        );

        assertThat(json).contains("2026-11-12T10:30:00Z");
    }
}
~~~

### 18.3. MockMvc để kiểm tra HTTP contract

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class UserApiJsonTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void responseUsesConfiguredJsonContract() throws Exception {
        mockMvc.perform(get("/users/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.first_name").value("An"));
    }
}
~~~

Test này xác nhận đường HTTP, bao gồm converter và mapper thực sự được MVC sử dụng. Nó hữu ích khi cấu hình JSON đúng trong unit test nhưng response API lại khác.

Với WebFlux, dùng WebTestClient và kiểm tra response body tương tự.

## 19. Cấu hình profile và nhiều môi trường

Spring Boot có thể áp dụng Jackson properties theo profile:

~~~yaml
spring:
  jackson:
    serialization:
      indent-output: false
---
spring:
  config:
    activate:
      on-profile: local
  jackson:
    serialization:
      indent-output: true
~~~

Có thể bật pretty print ở local để debug và tắt ở production để giảm kích thước response. Nhưng không nên để profile thay đổi semantics của contract như timezone, null inclusion hoặc naming strategy nếu client phải nhận cùng một schema ở mọi môi trường.

Nếu profile thay đổi behavior, test từng profile hoặc kiểm tra cấu hình effective lúc khởi động. Đừng để cấu hình test khác production đến mức test không còn phản ánh wire format thực tế.

## 20. Thứ tự cấu hình và tránh ghi đè khó hiểu

Một mapper có thể nhận cấu hình từ nhiều nơi:

1. Defaults của Jackson.
2. Spring Boot `spring.jackson.*`.
3. Module bean.
4. `Jackson2ObjectMapperBuilderCustomizer`.
5. Annotation trên model.
6. Mix-in.
7. Cấu hình theo `ObjectReader`/`ObjectWriter`.
8. Converter/codec cụ thể.

Các lớp này có phạm vi và precedence khác nhau. Không nên giả định chúng luôn được hợp nhất theo một thứ tự đơn giản.

Ví dụ, một naming strategy global có thể được thay bằng `@JsonProperty` trên property. Một custom serializer có thể thay đổi representation cho cả type, còn serializer gắn trực tiếp trên property có thể chỉ tác động nơi đó. Một mapper riêng có thể không nhận module mà mapper mặc định có.

Để cấu hình dễ truy vết:

- Giữ một nơi cho defaults toàn ứng dụng.
- Đăng ký module theo type nghiệp vụ.
- Dùng annotation cho ngoại lệ của model.
- Dùng mapper riêng chỉ khi wire contract khác nhau thật sự.
- Không mutate mapper sau khi đã được dùng.
- Test output qua đúng mapper/converter production.

## 21. Các lỗi thường gặp

**Tạo `new ObjectMapper()` trong service.** Mapper có thể thiếu module và defaults mà Spring Boot đã cấu hình.

**Khai báo Module bean nhưng mapper thủ công không dùng nó.** Module bean được tích hợp vào builder do Spring quản lý; mapper tự tạo cần đăng ký module riêng.

**Tạo customizer nhưng mong nó tác động mọi mapper.** Customizer chỉ cấu hình builder trong integration Spring tương ứng.

**Đăng ký cùng module ở nhiều nơi.** Serializer/deserializer có thể bị đăng ký lặp hoặc behavior khó xác định; chọn một đường đăng ký rõ ràng.

**Thay converter mà bỏ mất cấu hình Boot.** HTTP layer có thể dùng mapper khác với mapper được inject vào service.

**Dùng `@JsonView` như authorization.** View chỉ chọn property; server vẫn phải kiểm tra quyền caller.

**Bật ignore unknown properties toàn cục mà không xem contract.** Lỗi đánh máy trong command/config có thể bị bỏ qua và tạo hành vi sai.

**Sửa ObjectMapper sau khi request đã chạy.** Mapper được chia sẻ; thay đổi cấu hình lúc runtime có thể gây race và behavior không nhất quán.

**Chỉ test mapper được tạo trong test.** Cần test bean/context hoặc HTTP converter thực tế nếu cấu hình Spring là mục tiêu.

**Trộn Jackson 2 và Jackson 3 API.** Giữ dependency và integration package đồng bộ với Spring Boot release line đang dùng.

## 22. Ghi nhớ

- Spring MVC dùng Jackson thông qua `MappingJackson2HttpMessageConverter`; WebFlux dùng codec tương ứng.
- Ưu tiên ObjectMapper auto-configured của Spring Boot và inject qua constructor.
- Dùng `spring.jackson.*` cho defaults đơn giản, `Jackson2ObjectMapperBuilderCustomizer` cho cấu hình Java.
- Đăng ký `com.fasterxml.jackson.databind.Module` bean để mở rộng mapper do Spring builder tạo.
- `@JsonComponent` là cơ chế Spring Boot phát hiện serializer/deserializer; `@JsonSerialize` và `@JsonDeserialize` là annotation Jackson.
- Dùng annotation cho model, mix-in cho class bên thứ ba và `SimpleModule` cho kiểu nghiệp vụ dùng chung.
- Giữ Jackson modules cùng release line và để dependency management của Spring Boot quản lý version khi có thể.
- Không tạo mapper mới rải rác hoặc mutate mapper sau khi bắt đầu phục vụ request.
- Dùng `ObjectReader`/`ObjectWriter` cho biến thể theo operation; dùng mapper riêng có qualifier khi contract thực sự khác.
- Test `@JsonTest`, `@SpringBootTest` và MockMvc/WebTestClient theo đúng lớp behavior cần xác nhận.
- Annotation, view và converter không thay thế validation hoặc authorization ở tầng ứng dụng.
- Với Spring Boot/Jackson 3, kiểm tra API integration của release line đó; không trộn ví dụ Jackson 2 vào runtime Jackson 3.

