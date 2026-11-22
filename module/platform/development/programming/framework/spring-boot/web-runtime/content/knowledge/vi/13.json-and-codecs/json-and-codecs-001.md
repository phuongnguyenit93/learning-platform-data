# Jackson, ObjectMapper và cấu hình tự động của Spring Boot

## Mục tiêu học tập

Khi xây dựng REST API, ứng dụng Spring Boot thường cần biến JSON trong HTTP request thành đối tượng Java và chuyển đối tượng Java thành JSON response. **Jackson** là thư viện phổ biến thực hiện quá trình này. **ObjectMapper** là trung tâm của Jackson 2; Spring Boot còn bổ sung cơ chế tự cấu hình để các controller và HTTP clients có thể dùng Jackson mà không phải khởi tạo thủ công mọi thành phần.

Sau bài học, bạn có thể:

- Phân biệt serialization, deserialization, JSON mapper, module, HTTP message converter và reactive codec.
- Hiểu Spring Boot 3.5 tự tạo Jackson 2 ObjectMapper trong điều kiện nào và tích hợp với Spring MVC/WebFlux ra sao.
- Tùy chỉnh Jackson bằng application.properties, annotation, Jackson2ObjectMapperBuilderCustomizer, Module và @JsonComponent.
- Biết khi nào cần tự tạo ObjectMapper và những auto-configuration có thể mất khi thay bean mặc định.
- Chọn kiểu Java cho JSON đúng: record/DTO, Instant/LocalDate, optional field, generic List, JsonNode.
- Phân biệt lỗi JSON malformed, content negotiation và lỗi mapping trong HTTP API.
- Hiểu thay đổi lớn khi chuyển lên Spring Boot 4.x: Jackson 3, JsonMapper, package mới và các thiết lập cần rà soát.
- Viết và kiểm thử một endpoint JSON Java 17+ dựa trên mapper được Boot cấu hình.

## 1. Jackson nằm ở đâu trong pipeline HTTP?

Ví dụ client gửi JSON:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customer_name":"An","quantity":2}
~~~

Controller muốn nhận một Java record CreateOrderRequest và trả một OrderView. Về mặt khái niệm:

~~~text
HTTP request
  headers + JSON bytes
          |
          v
Spring HTTP message reader/converter
          |
          v
Jackson deserialization
          |
          v
CreateOrderRequest Java object
          |
          v
@Controller / @RestController
          |
          v
OrderView Java object
          |
          v
Jackson serialization
          |
          v
HTTP message writer/converter
          |
          v
HTTP response: Content-Type + JSON bytes
~~~

Phân biệt trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Jackson | Đọc/ghi định dạng JSON và ánh xạ sang Java type. |
| ObjectMapper trong Jackson 2 | Object-level API quản lý serializer, deserializer, module, naming, feature và JSON tree. |
| HttpMessageConverter trong Spring MVC | Kết nối việc đọc/ghi HTTP body với Java object theo media type. |
| HttpMessageReader/HttpMessageWriter trong Spring WebFlux | Kết nối body reactive với codec phù hợp, có thể truyền dữ liệu bất đồng bộ. |
| Spring Boot auto-configuration | Tạo/cấu hình mapper và tích hợp khi điều kiện classpath/bean phù hợp. |
| Bean/DTO annotation | Mô tả một số quy tắc serialization/deserialization theo từng kiểu/thuộc tính. |

Jackson không quyết định URL route hoặc status HTTP. Một JSON body đúng cú pháp vẫn có thể bị từ chối vì endpoint không hỗ trợ Content-Type. Ngược lại, status 200 không chứng minh JSON được serialize đúng hợp đồng API.

## 2. Serialization và deserialization

**Serialization** là chuyển Java object thành JSON:

~~~text
new User(7, "An")  ->  {"id":7,"name":"An"}
~~~

**Deserialization** là chuyển JSON thành Java object:

~~~text
{"id":7,"name":"An"}  ->  new User(7, "An")
~~~

Jackson thường ánh xạ các kiểu như:

| JSON | Kiểu Java điển hình | Lưu ý |
|---|---|---|
| string | String | Cần quy ước encoding và giới hạn độ dài từ API. |
| number nguyên | int, long, BigInteger | Số quá lớn có thể gây lỗi hoặc tràn nếu ép kiểu sai. |
| number thập phân | BigDecimal, double | Dùng BigDecimal khi cần độ chính xác thập phân, ví dụ tiền tệ. |
| boolean | boolean, Boolean | Kiểu wrapper có thể biểu diễn null. |
| null | Object reference null | Primitive không giữ được null; cần chiến lược xử lý rõ. |
| object | POJO, record, Map, JsonNode | Dùng DTO cụ thể khi biết contract. |
| array | List<T>, T[], Collection<T> | Generic type cần type information lúc deserialization thủ công. |
| ISO date/time string | Instant, OffsetDateTime, LocalDate | Cần module/format thích hợp; phân biệt timezone. |

Một DTO để truyền dữ liệu qua HTTP thường nên độc lập với JPA entity. Không expose trực tiếp quan hệ entity, lazy proxy, mật khẩu, trường nội bộ hoặc cấu trúc database trừ khi API contract thực sự yêu cầu.

### Java record và Jackson

Với Java 17+, record thường là lựa chọn gọn cho immutable DTO:

~~~java
public record UserView(long id, String name) {
}
~~~

Khi Jackson và phiên bản hỗ trợ records có mặt, nó có thể đọc/ghi các record components. Những annotation như @JsonProperty hoặc @JsonIgnore giúp điều chỉnh tên và việc xuất hiện của thuộc tính.

## 3. Spring Boot 3.5 tự cấu hình ObjectMapper như thế nào?

Phần lớn ví dụ runnable của bài dùng **Spring Boot 3.5.x + Java 17+**, mặc định Jackson 2.

Với Spring Boot 3.5:

1. Dependency phù hợp đưa Jackson lên classpath; thường starter Spring Web hoặc Spring Reactive Web đã kéo JSON starter cần thiết.
2. Spring Boot áp dụng **JacksonAutoConfiguration** khi các điều kiện thỏa mãn.
3. Boot auto-configure **Jackson2ObjectMapperBuilder**, rồi tạo **ObjectMapper bean** nếu chưa có bean làm điều kiện tự cấu hình rút lui.
4. Boot áp các **spring.jackson.*** properties và các **Jackson2ObjectMapperBuilderCustomizer** bean.
5. Những **com.fasterxml.jackson.databind.Module** bean được đăng ký vào builder do Boot quản lý.
6. MVC hoặc WebFlux tích hợp JSON mapper vào HTTP converter/codec khi được Boot/Spring cấu hình phù hợp.

Dạng rút gọn:

~~~text
spring-boot-starter-web / spring-boot-starter-webflux
                  |
                  v
            Jackson on classpath
                  |
                  v
         JacksonAutoConfiguration
                  |
      +-----------+--------------+
      |                          |
spring.jackson.*         Jackson2ObjectMapperBuilderCustomizer
      |                          |
      +------------+-------------+
                   |
                   v
          Jackson2ObjectMapperBuilder
                   |
                   +-- Module beans / Jackson support
                   |
                   v
             ObjectMapper bean
                   |
          +--------+---------+
          |                  |
        Spring MVC         Spring WebFlux
      HTTP converter        JSON codec
~~~

Sơ đồ biểu diễn đường đi phổ biến của auto-configuration, không khẳng định mọi ObjectMapper hoặc mọi HTTP client tự tạo thủ công đều sử dụng đúng cùng một object instance. Ví dụ một WebClient do bạn tự tạo với ExchangeStrategies riêng có thể sở hữu codec settings khác.

**Quan trọng:** Spring Boot không nhất thiết định nghĩa ObjectMapper bean nếu Jackson không có trên classpath, nếu bạn đã định nghĩa bean thay thế, hoặc nếu các điều kiện auto-configuration liên quan không thỏa mãn.

### Các mặc định của Boot 3.5 cần biết

Theo tài liệu chính thức của Spring Boot 3.5, mapper được Boot cấu hình thường có các lựa chọn sau:

- MapperFeature.DEFAULT_VIEW_INCLUSION: disabled.
- DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES: disabled.
- SerializationFeature.WRITE_DATES_AS_TIMESTAMPS: disabled.
- SerializationFeature.WRITE_DURATIONS_AS_TIMESTAMPS: disabled.

Như vậy:

- JSON có thuộc tính lạ thường có thể được bỏ qua theo mặc định khi deserialization, nhưng có thể đổi thành strict.
- Kiểu java.time có thể được serialize theo biểu diễn ngày/giờ phù hợp thay vì số timestamp khi hỗ trợ module tương ứng.
- Không nên lấy ObjectMapper tự new làm chuẩn để suy ra hành vi của mapper do Boot đã cấu hình.

Những mặc định này có thể khác khi chuyển lên Spring Boot 4.x/Jackson 3, khi ứng dụng tự thay bean hoặc có customizers khác.

## 4. Dependency và cách chọn version

### Maven cho Spring Boot 3.5

Dự án Spring MVC với Boot parent/BOM có thể dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Dự án WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Cả hai thường đưa Jackson 2 JSON support qua starter phù hợp. Không nên tự ấn định các version jackson-databind, jackson-core, jackson-annotations rời rạc trái với Spring Boot BOM.

### Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu sử dụng Spring Boot 4.x, starter và các module JSON đã được tổ chức lại theo major version: dùng starter tương ứng và kiểm tra dependency tree. Bài này cố ý giữ ví dụ Java chạy được nhất quán với Boot 3.5, còn phần nâng cấp Boot 4 sẽ nêu rõ khác biệt.

Kiểm tra dependency khi gặp lỗi class:

~~~bash
./mvnw dependency:tree
~~~

Hoặc:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Các dependency đến từ plugin hoặc thư viện bên ngoài có thể kéo thêm Jackson 2 trong ứng dụng Boot 4, vì vậy phải biết mình đang dùng mapper Jackson 2 hay Jackson 3.

## 5. Dùng ObjectMapper ngoài controller

Trong Jackson 2:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = ...;

String json = mapper.writeValueAsString(value);
UserView user = mapper.readValue(json, UserView.class);
~~~

Đây là đoạn API minh họa, cần object value và xử lý exception tương ứng. Những method này thuận tiện khi cần JSON ngoài HTTP, ví dụ message queue, file hoặc object mapping trong một số workflow.

### Ví dụ Java 17+ với ObjectMapper đã inject

~~~java
package com.example.json;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class JsonTextService {

    private final ObjectMapper mapper;

    public JsonTextService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String toJson(Object value) throws JsonProcessingException {
        return mapper.writeValueAsString(value);
    }
}
~~~

Ở đây, Spring sẽ inject một ObjectMapper bean mà nó có thể phân giải. Trong ứng dụng Boot 3.5 không có mapper thay thế, bean thường là mapper auto-configured.

**Không lạm dụng ObjectMapper trong @RestController:** Nếu controller trả object hoặc ResponseEntity<T> thì Spring đã dùng HTTP converter/codec phù hợp. Không cần gọi writeValueAsString rồi trả String, vì dễ khiến media type hoặc escaping bị sai, thậm chí JSON bị double-encoded.

### Generic List và JavaType

Đoạn mã này không giữ đủ generic type:

~~~java
List<?> values = mapper.readValue(json, List.class);
~~~

Khi deserializing object list, Jackson có thể tạo Map thay vì DTO. Với Jackson 2, dùng TypeReference hoặc JavaType:

~~~java
List<UserView> users = mapper.readValue(
    json,
    new com.fasterxml.jackson.core.type.TypeReference<List<UserView>>() {}
);
~~~

Trong ví dụ trên cần các imports List và UserView đã được định nghĩa. Đây là lý do không nên bỏ generic type information khi tự đọc JSON ngoài HTTP.

### JsonNode cho JSON tree

Nếu schema chỉ được biết ở runtime hoặc cần inspect một vài trường, có thể dùng:

~~~java
JsonNode root = mapper.readTree(json);
String name = root.path("name").asText("");
~~~

JsonNode là API tree của Jackson, phù hợp với dữ liệu linh hoạt; nhưng nếu contract ổn định thì DTO cụ thể dễ validate, test và maintain hơn.

## 6. Tùy chỉnh bằng application.properties

Với Spring Boot 3.5, cách đơn giản nhất để thay đổi chính sách JSON toàn ứng dụng do Boot cấu hình là đặt **spring.jackson.*** properties.

Ví dụ:

~~~properties
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.indent_output=true
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.fail-on-unknown-properties=false
~~~

Ý nghĩa:

| Property | Tác dụng | Lưu ý |
|---|---|---|
| spring.jackson.default-property-inclusion=non_null | Không xuất các thuộc tính có giá trị null theo chính sách inclusion toàn cục. | Không đồng nghĩa loại chuỗi rỗng hay list rỗng; cần chính sách khác nếu muốn. |
| spring.jackson.serialization.indent_output=true | Pretty-print JSON thay vì định dạng ngắn gọn. | Tăng số byte response; nên cân nhắc production. |
| spring.jackson.serialization.write-dates-as-timestamps=false | Khi module ngày/giờ phù hợp có mặt, ưu tiên biểu diễn date/time dạng chuỗi. | Không đồng nghĩa tự chọn múi giờ cho mọi trường. |
| spring.jackson.deserialization.fail-on-unknown-properties=true | Chuyển sang strict mode khi input có thuộc tính không được DTO nhận diện. | Có thể làm client cũ gặp 400 khi API thêm trường chưa hỗ trợ. |

Đoạn cấu hình trên minh họa **false** cho unknown-properties để bám default Boot 3.5. Nếu muốn strict, chuyển nó thành true một cách chủ đích và bổ sung integration tests.

Property binding không thay thế việc validate input. Ví dụ request có quantity = -3 là JSON hợp lệ và có thể deserialize thành int, nhưng nghiệp vụ vẫn cần Bean Validation hoặc kiểm tra riêng.

### YAML tương đương

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
    serialization:
      indent_output: true
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

Không đặt cùng một cấu hình mâu thuẫn ở nhiều file profile/env/command-line mà không xác định thứ tự override. Giá trị có hiệu lực cuối cùng phụ thuộc cơ chế externalized configuration của Spring Boot.

## 7. Annotation Jackson để điều chỉnh một DTO

Các annotation phổ biến trong Jackson 2 (và nhiều annotation tiếp tục có mặt khi chuyển sang Jackson 3):

| Annotation | Công dụng | Ví dụ |
|---|---|---|
| @JsonProperty | Đổi tên field trong JSON hoặc khai báo tên/metadata property. | orderId thành order_id. |
| @JsonIgnore | Bỏ qua một property trong serialization/deserialization theo cấu hình tương ứng. | Không xuất internalNote. |
| @JsonInclude | Chọn điều kiện property xuất hiện trong JSON. | NON_NULL cho DTO. |
| @JsonFormat | Điều chỉnh biểu diễn ngày/giờ, pattern hoặc shape. | LocalDate ở định dạng ngày cụ thể. |
| @JsonCreator | Chỉ cách Jackson tạo đối tượng bằng factory/constructor khi cần. | DTO immutable phức tạp. |
| @JsonAlias | Chấp nhận các tên input thay thế khi deserialization. | Hỗ trợ đổi tên property khi nhận JSON. |
| @JsonView | Phân nhóm thuộc tính theo JSON view. | Các API output khác nhau. |
| @JsonTypeInfo | Kiểm soát metadata đa hình có chủ đích. | Type hierarchy có hợp đồng rõ ràng. |

Không thêm annotation chỉ vì “cho chắc”: hãy chọn một hợp đồng JSON thống nhất. Ví dụ dùng naming strategy SNAKE_CASE toàn cục thì không nhất thiết viết @JsonProperty cho từng field.

### Ví dụ record có JSON name và trường nội bộ

~~~java
package com.example.json;

import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderView(
        @JsonProperty("order_id") long id,
        String customer,
        Instant createdAt,
        @JsonIgnore String internalNote,
        String note
) {
}
~~~

Khi Jackson 2 mapper được Boot cấu hình và chính sách NON_NULL được áp dụng:

~~~java
OrderView view = new OrderView(
    7,
    "An",
    Instant.parse("2026-01-02T03:04:05Z"),
    "not-for-clients",
    null
);
~~~

JSON tương đương về các giá trị (không yêu cầu thứ tự property cố định):

~~~json
{
  "order_id": 7,
  "customer": "An",
  "createdAt": "2026-01-02T03:04:05Z"
}
~~~

internalNote bị bỏ qua do @JsonIgnore; note null không được xuất do global NON_NULL. Với Jackson Java Time support và WRITE_DATES_AS_TIMESTAMPS=false, Instant được xuất dạng ISO-8601.

**Lưu ý bảo mật:** @JsonIgnore trên output DTO không phải thay thế hoàn toàn việc tách domain entity khỏi response schema. Nếu ứng dụng trả trực tiếp JPA entity, các quan hệ lazy, dữ liệu riêng tư hoặc cơ chế proxy có thể tạo hiệu ứng khó kiểm soát.

### @JsonFormat và timezone

~~~java
public record ReportView(
    @JsonFormat(pattern = "yyyy-MM-dd") LocalDate reportDate
) {
}
~~~

Định dạng LocalDate khác với Instant có offset/timezone. Không chuyển Instant sang chuỗi thời gian địa phương mà không nêu timezone. Đối với API liên hệ nhiều múi giờ, ưu tiên UTC hoặc OffsetDateTime/Instant theo contract rõ ràng.

## 8. Java Time: vì sao module quan trọng?

Jackson 2 cần hỗ trợ thích hợp cho java.time (như JavaTimeModule của jackson-datatype-jsr310). Spring Boot thông thường đăng ký các module quen thuộc khi chúng hiện diện qua dependency management/starter.

Nếu tự tạo ObjectMapper bằng new ObjectMapper() mà không có module cần thiết, những kiểu như LocalDate, Instant hoặc OffsetDateTime có thể không serialize/deserialize được như mapper của Boot.

Một phương án thủ công của Jackson 2:

~~~java
ObjectMapper custom = new ObjectMapper();
custom.registerModule(new JavaTimeModule());
custom.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Để compile cần import:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
~~~

Đoạn code trên chỉ minh họa Jackson 2, **không phải** hướng mặc định cho ứng dụng Boot: làm vậy bỏ qua nhiều tính năng auto-configuration khác nếu đem custom mapper này thay bean. Nên dùng mapper Boot đã cấu hình, properties hoặc builder customizer khi phù hợp.

Khi dùng Jackson 3 ở Boot 4, cơ chế module/feature và package thay đổi. Không copy các import Jackson 2 vào dự án Jackson 3 mà không kiểm tra migration guide.

## 9. Jackson2ObjectMapperBuilderCustomizer trong Boot 3.5

Một cách tùy chỉnh toàn cục mà vẫn giữ quá trình xây mapper của Spring Boot là khai báo **Jackson2ObjectMapperBuilderCustomizer** bean.

Ví dụ bật strict unknown-property handling:

~~~java
package com.example.json;

import com.fasterxml.jackson.databind.DeserializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JacksonConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer strictJson() {
        return builder -> builder.featuresToEnable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
        );
    }
}
~~~

Đây là **cấu hình thay thế** việc đặt fail-on-unknown-properties=false ở phần 6. Không nên khai báo cả hai với hai giá trị mâu thuẫn trong cùng demo; hãy chọn một chiến lược và test giá trị thực.

Ưu điểm:

- Boot vẫn tạo và quản lý ObjectMapper thông qua builder.
- Các cấu hình khác của Boot vẫn có thể được áp dụng.
- Có thể dùng nhiều customizer bean, nhưng nên tránh xung đột và xác định order khi các callback cùng chỉnh một feature.

Chỉ dùng customizer cho việc không thể mô tả thuận tiện bằng properties hoặc khi cần kết hợp logic có kiểm soát. Nếu chỉ muốn bỏ null khỏi JSON, property spring.jackson.default-property-inclusion thường dễ đọc và vận hành hơn.

### Thứ tự customizer

Spring Boot có customizer mặc định với order riêng. Những customizer của ứng dụng có thể dùng @Order hoặc Ordered để điều chỉnh trước/sau; thứ tự quan trọng khi cùng cấu hình một property. Không nên dựa vào thứ tự bean ngẫu nhiên hoặc assume customizer sau luôn override trong mọi tình huống nếu builder có các callback đặc thù.

## 10. Module và @JsonComponent cho serializer/deserializer riêng

Jackson hỗ trợ các module để đóng gói serializer, deserializer và tính năng bổ sung. Trong Boot 3.5, bean kiểu **com.fasterxml.jackson.databind.Module** được tự động tích hợp với mapper builder do Boot quản lý.

Nếu bạn cần định dạng đặc biệt cho một kiểu dữ liệu nghiệp vụ, có thể:

1. Dùng @JsonFormat hoặc @JsonProperty nếu nhu cầu đơn giản.
2. Tạo custom JsonSerializer/JsonDeserializer và đăng ký qua SimpleModule bean.
3. Hoặc dùng Spring Boot 3.5 **@JsonComponent** để đăng ký serializer/deserializer dạng bean một cách thuận tiện.

Ví dụ một serializer Jackson 2 cho kiểu Money, mô tả thành một chuỗi:

~~~java
package com.example.json;

import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public record Money(BigDecimal amount, String currency) {
}

class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money money,
            JsonGenerator out,
            SerializerProvider serializers
    ) throws IOException {
        out.writeString(money.amount().toPlainString()
            + " " + money.currency());
    }
}
~~~

Đây là mã minh họa hai type cùng logic trong một đoạn; trong source Java chuẩn phải tách public record Money vào **Money.java** và tạo **MoneySerializer.java** không public, hoặc tổ chức các class phù hợp với quy tắc Java. Custom serializer thay cách Money hiển thị trong response; cần bảo đảm API contract cho chuỗi tiền tệ rõ ràng.

Đăng ký bằng SimpleModule bean:

~~~java
@Configuration(proxyBeanMethods = false)
class MoneyModuleConfig {

    @Bean
    com.fasterxml.jackson.databind.Module moneyModule() {
        SimpleModule module = new SimpleModule();
        module.addSerializer(Money.class, new MoneySerializer());
        return module;
    }
}
~~~

Để biên dịch đoạn bean cần import @Bean, @Configuration và **com.fasterxml.jackson.databind.module.SimpleModule**, đồng thời các class Money/MoneySerializer ở đúng package.

**Không tự động khẳng định custom serializer hai chiều:** Serializer chỉ ghi JSON. Nếu muốn đọc ngược chuỗi "12.50 USD" thành Money, cần custom deserializer tương ứng, hoặc chọn một JSON object structure dễ deserialize hơn.

### @JsonComponent

Spring Boot 3.5 hỗ trợ annotation:

~~~java
import org.springframework.boot.jackson.JsonComponent;
~~~

Có thể đặt @JsonComponent trên JsonSerializer/JsonDeserializer bean hoặc class chứa implementation để Boot phát hiện và đưa vào mapper, theo hướng dẫn chính thức. Với Jackson 3/Spring Boot 4, tên được đổi thành **@JacksonComponent**; không dùng import cũ cho ví dụ Boot 4.

## 11. Khi nào KHÔNG nên tự khai báo @Bean ObjectMapper?

Ví dụ sau thường gây bất ngờ:

~~~java
@Configuration
public class JsonConfig {

    @Bean
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
~~~

Một bean kiểu ObjectMapper do ứng dụng khai báo có thể làm phần auto-configuration tạo ObjectMapper mặc định của Boot **back off**. Khi đó các tính năng trước đây đi qua builder Boot, properties và Module beans có thể không được áp dụng vào chính object bạn vừa new.

Tình huống quan sát:

- Instant hoặc LocalDate không còn được serialize như trước.
- JSON naming hoặc null inclusion khác với spring.jackson.*.
- Một custom Module bean hoặc @JsonComponent không được gắn vào mapper thay thế theo mong đợi.
- REST controller và object-to-JSON utility dùng hai mapper có behavior khác nhau.

Nên ưu tiên theo thứ tự:

1. Properties spring.jackson.* nếu đã có property phù hợp.
2. Jackson annotations cho quy tắc riêng một DTO/property.
3. Jackson2ObjectMapperBuilderCustomizer cho điều chỉnh builder của Boot 3.5.
4. Module hoặc @JsonComponent nếu cần serializer/deserializer.
5. Chỉ tự thay bean ObjectMapper khi chủ động muốn toàn quyền điều khiển, có test đầy đủ và hiểu phần auto-configuration rút lui.

Nếu cần một mapper khác chỉ cho **một** tính năng nội bộ, hãy tạo mapper riêng được đặt tên/qualifier rõ ràng và không vô tình làm nó trở thành ứng viên toàn cục thay mapper JSON của web layer. Với nhiều bean, cần @Primary/@Qualifier phù hợp và kiểm tra mapper nào thực sự được MVC/WebFlux sử dụng.

### Có nên thay ObjectMapper bằng new ObjectMapper() trên từng request?

Không. Tạo mapper lặp lại có chi phí cấu hình/khởi tạo và dễ tạo khác biệt cấu hình. Mapper thường an toàn để dùng chung khi **được cấu hình hoàn tất trước khi sử dụng**. Sau khi đã xử lý request, tránh mutate cấu hình toàn cục của mapper trong luồng concurrent; dùng ObjectReader/ObjectWriter hoặc mapper riêng cho nhu cầu đặc biệt.

## 12. Ví dụ Spring Boot 3.5 + Java 17+ hoàn chỉnh

Ví dụ sau dùng Spring Boot 3.5.x, Java 17+ và **spring-boot-starter-web**. Tạo project từ Spring Initializr hoặc Maven project có Spring Boot parent/BOM. Không cần khai báo ObjectMapper bean; Boot sẽ quản lý mapper.

### 12.1. application.properties

File: src/main/resources/application.properties

~~~properties
server.port=8080
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.write-dates-as-timestamps=false
~~~

Không dùng một customizer strict mode trong demo này. Khi POST có input hợp lệ, controller sẽ dùng Jackson để đọc DTO; khi GET, controller trả object để Spring ghi JSON.

### 12.2. JsonApplication.java

File: src/main/java/com/example/json/JsonApplication.java

~~~java
package com.example.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonApplication.class, args);
    }
}
~~~

### 12.3. OrderView.java

File: src/main/java/com/example/json/OrderView.java

~~~java
package com.example.json;

import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderView(
        @JsonProperty("order_id") long id,
        String customer,
        Instant createdAt,
        @JsonIgnore String internalNote,
        String note
) {
}
~~~

### 12.4. CreateOrderRequest.java

File: src/main/java/com/example/json/CreateOrderRequest.java

~~~java
package com.example.json;

import com.fasterxml.jackson.annotation.JsonProperty;

public record CreateOrderRequest(
        @JsonProperty("customer_name") String customer,
        int quantity
) {
}
~~~

### 12.5. OrderController.java

File: src/main/java/com/example/json/OrderController.java

~~~java
package com.example.json;

import java.net.URI;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final AtomicLong sequence = new AtomicLong(6);

    @GetMapping("/{id}")
    public OrderView get(@PathVariable long id) {
        return new OrderView(
            id,
            "An",
            Instant.parse("2026-01-02T03:04:05Z"),
            "internal-secret",
            null
        );
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @RequestBody CreateOrderRequest request) {

        if (request.customer() == null || request.customer().isBlank()
                || request.quantity() <= 0) {
            return ResponseEntity.badRequest().build();
        }

        long id = sequence.incrementAndGet();
        OrderView created = new OrderView(
            id,
            request.customer().trim(),
            Instant.parse("2026-01-02T03:04:05Z"),
            "internal-secret",
            null
        );

        return ResponseEntity
            .created(URI.create("/api/orders/" + id))
            .body(created);
    }
}
~~~

Controller minh họa JSON conversion, không dùng database. Việc GET trả dữ liệu giả lập cho mọi id chỉ nhằm tập trung vào JSON mapping, không biểu thị nghiệp vụ REST production.

**Lưu ý về validation:** Kiểm tra if trong controller là ví dụ tối giản; hệ thống thực tế nên dùng Bean Validation, DTO constraints, exception handling và business rules phù hợp.

### 12.6. Chạy ứng dụng và xem JSON

Chạy Maven Wrapper từ project root:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Gọi GET:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/orders/7
~~~

Status dự kiến 200, Content-Type tương thích application/json. JSON có các field và giá trị tương đương:

~~~json
{
  "order_id": 7,
  "customer": "An",
  "createdAt": "2026-01-02T03:04:05Z"
}
~~~

**internalNote** bị loại nhờ @JsonIgnore; **note** bị loại nhờ NON_NULL. Thứ tự field hoặc whitespace trong body không được dùng làm điều kiện thành công nếu API contract không bắt buộc thứ tự.

Gọi POST:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"customer_name":"Binh","quantity":2}'
~~~

Trong một tiến trình mới khởi động, sequence bắt đầu từ 6 nên POST đầu tiên tạo order_id 7. Response có status 201 Created và Location: /api/orders/7. Body JSON có customer: "Binh" và createdAt theo dữ liệu demo.

Gửi request sai nghiệp vụ:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer_name":"","quantity":0}'
~~~

Controller trả 400 Bad Request vì dữ liệu không hợp lệ. Đây **không phải** lỗi Jackson: JSON vẫn đúng cú pháp và đã deserialize được.

## 13. Kiểm thử JSON mapper và HTTP contract

Dùng **spring-boot-starter-test** với Spring Boot 3.5. Nếu project dùng Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 13.1. Kiểm thử HTTP bằng MockMvc

File: src/test/java/com/example/json/OrderControllerTest.java

~~~java
package com.example.json;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonUsesConfiguredNamingAndExclusion() throws Exception {
        mvc.perform(get("/api/orders/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.order_id").value(7))
            .andExpect(jsonPath("$.customer").value("An"))
            .andExpect(jsonPath("$.createdAt")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.internalNote").doesNotExist())
            .andExpect(jsonPath("$.note").doesNotExist());
    }
}
~~~

Test xác nhận kết quả **HTTP serializer thực tế** của Spring Boot, không chỉ ObjectMapper được gọi thủ công. Khi dự án dùng Spring Boot 4.x, một số package test auto-configuration đã thay đổi; cần dùng import theo version tương ứng.

### 13.2. Test mapper độc lập

Một test đơn vị cho ObjectMapper do Boot inject có thể kiểm tra cả serialization và deserialization:

~~~java
@Autowired
ObjectMapper mapper;

@Test
void jacksonReadsInputDto() throws Exception {
    String json = "{\"customer_name\":\"Binh\",\"quantity\":2}";
    CreateOrderRequest input =
        mapper.readValue(json, CreateOrderRequest.class);

    assertEquals("Binh", input.customer());
    assertEquals(2, input.quantity());
}
~~~

Đoạn này minh họa method trong class JUnit đã cấu hình Spring test context và imports, bao gồm assertEquals từ JUnit. Không dùng new ObjectMapper() trong test nếu mục tiêu là kiểm chứng bean Boot sử dụng trong ứng dụng.

### 13.3. Test strict unknown properties

Nếu bạn đặt spring.jackson.deserialization.fail-on-unknown-properties=true, hãy gửi JSON có một field không khai báo rồi xác nhận deserialization bị từ chối theo contract.

Nếu để default Boot 3.5, JSON có field lạ có thể vẫn deserialize được, nhưng việc bỏ qua field không nhất thiết là lựa chọn an toàn cho mọi nghiệp vụ. Chỉ chọn strict hoặc tolerant theo yêu cầu backward/forward compatibility rõ ràng.

## 14. JSON và Spring MVC: HttpMessageConverter

Trong Spring MVC, HTTP message converter chọn cách đọc/ghi body. Với Jackson 2, converter phổ biến là **MappingJackson2HttpMessageConverter**, kết hợp với mapper để chuyển JSON.

Ví dụ controller:

~~~java
@PostMapping(
    path = "/api/users",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public UserView create(@RequestBody UserView input) {
    return input;
}
~~~

Đây là method minh họa trong @RestController; cần imports tương ứng. Content-Type mô tả định dạng **request body**, còn Accept liên quan định dạng **response** được client mong muốn.

Nếu bạn tự cung cấp một MappingJackson2HttpMessageConverter bean, hãy chú ý: trong những cấu hình Boot, bean converter riêng có thể **thay thế** converter mặc định tương ứng. Điều này có thể làm các ObjectMapper features/module không được dùng như trước.

Không thêm @EnableWebMvc chỉ để làm JSON hoạt động trong dự án Boot thông thường. @EnableWebMvc có thể khiến Boot MVC auto-configuration rút lui, làm thay đổi cách converters, static resources và những tích hợp khác được cấu hình.

Một ứng dụng có thể sử dụng HTTP status 415 Unsupported Media Type khi request không có reader phù hợp hoặc Content-Type không được chấp nhận; 406 Not Acceptable khi không có writer cho response media type mà client yêu cầu. Đây không luôn là lỗi Jackson parser.

## 15. JSON và Spring WebFlux: codec thay vì converter kiểu Servlet

Trong WebFlux, body reactive được xử lý qua **HttpMessageReader/HttpMessageWriter** và Encoder/Decoder. Jackson vẫn có vai trò serialization/deserialization, nhưng việc xử lý gắn với reactive pipeline, DataBuffer và subscriber.

Ví dụ:

~~~java
@PostMapping("/api/echo")
public Mono<EchoResponse> echo(
        @RequestBody Mono<EchoRequest> input) {
    return input.map(value ->
        new EchoResponse(value.message())
    );
}
~~~

Đây là method minh họa thuộc WebFlux @RestController; cần DTO/imports cụ thể và không phải file chạy độc lập. Framework subscribe vào Publisher và dùng codec JSON phù hợp.

### maxInMemorySize không phải cấu hình Jackson thuần túy

Với WebFlux, JSON decoder có thể phải buffer dữ liệu để decode một object. Nếu vượt ngưỡng, có thể gặp DataBufferLimitException.

Ví dụ property trên các phiên bản Boot có hỗ trợ:

~~~properties
spring.http.codecs.max-in-memory-size=1MB
~~~

Property này liên quan **codec buffering**, không phải tính năng ObjectMapper hay độ dài lớn nhất của mọi upload. Đừng tự tăng lên hàng trăm MB thay vì cân nhắc streaming, giới hạn gateway, multipart và memory budget.

Trong Boot 3.5, có thể dùng **org.springframework.boot.web.codec.CodecCustomizer** để chỉnh CodecConfigurer do Boot quản lý. Với Boot 4.x, package của CodecCustomizer cũng có thay đổi. Các thay đổi codec/server/client cần được kiểm tra riêng với JSON mapper.

### WebClient có thể dùng mapper/configuration khác

WebClient được Spring Boot auto-configure có thể nhận các customizations thích hợp từ Boot. WebClient được tạo thủ công bằng WebClient.builder() với strategies riêng **không mặc nhiên** kế thừa mọi mapper/codec bean mà ứng dụng đã cấu hình.

Khi thấy response JSON từ outbound WebClient khác với response JSON của controller:

1. Xác định mapper/codec của **server**.
2. Xác định mapper/codec của **client**.
3. So sánh naming, module, media type, date handling và maxInMemorySize.
4. Kiểm tra có tự tạo JsonMapper/ObjectMapper hoặc ExchangeStrategies khác không.

## 16. Thay đổi quan trọng: Spring Boot 4.x và Jackson 3

**Đây là điểm cần phân biệt theo phiên bản.** Spring Boot 4.x ưu tiên **Jackson 3**, còn các ví dụ runnable bên trên dùng **Jackson 2 trong Boot 3.5**.

Theo tài liệu Spring Boot 4.x:

- Jackson 3 là thư viện JSON **mặc định và được ưu tiên**.
- Thay vì cấu hình ObjectMapper bean kiểu Jackson 2 như mặc định của Boot 3.5, Boot 4 auto-configure **JsonMapper** cho Jackson 3.
- Phần lớn package và Maven group ID của Jackson 3 đổi từ com.fasterxml.jackson sang **tools.jackson**. Một ngoại lệ quan trọng là **jackson-annotations**, vẫn dùng com.fasterxml.jackson.annotation và group ID lịch sử liên quan.
- Các lớp customizer được đổi tên hoặc điều chỉnh API: từ **Jackson2ObjectMapperBuilderCustomizer** sang **JsonMapperBuilderCustomizer**.
- Jackson 2 compatibility trong Boot 4 có module **spring-boot-jackson2**, nhưng hỗ trợ này đã được đánh dấu deprecated và chỉ nên dùng như cầu nối chuyển đổi.
- Spring Boot 4.0 có cơ chế nhận diện thêm các Jackson modules từ classpath; cần kiểm tra khác biệt serialization khi nâng cấp.
- Một số thuộc tính liên quan JSON read/write được chuyển vào namespace **spring.jackson.json.read.*** và **spring.jackson.json.write.***.
- Các annotation integration của Boot như **@JsonComponent** và **@JsonMixin** đã được đổi thành **@JacksonComponent** và **@JacksonMixin** theo tài liệu nâng cấp.

Bảng đối chiếu:

| Mục | Spring Boot 3.5 / Jackson 2 | Spring Boot 4.x / Jackson 3 |
|---|---|---|
| Mapper JSON mặc định | com.fasterxml.jackson.databind.ObjectMapper | JsonMapper từ Jackson 3, thuộc tools.jackson |
| Builder customizer | Jackson2ObjectMapperBuilderCustomizer | JsonMapperBuilderCustomizer |
| Namespace Jackson databind | com.fasterxml.jackson.databind | tools.jackson.databind (và các package con) |
| Jackson annotations | com.fasterxml.jackson.annotation | Nhiều annotation giữ com.fasterxml.jackson.annotation |
| Custom serializer API | JsonSerializer / JsonDeserializer của Jackson 2 | Các API serializer/deserializer Jackson 3 đã thay đổi, cần đối chiếu migration |
| Component annotation Boot | @JsonComponent | @JacksonComponent |
| Old mapper compatibility | Chính | Module spring-boot-jackson2 deprecated nếu còn cần |

### Cách tùy chỉnh mapper trong Boot 4

Trong Spring Boot 4, dùng **JsonMapperBuilderCustomizer** bean hoặc property phù hợp thay vì copy class Boot 3.5.

Tên interface và package được tài liệu Boot 4 công bố:

~~~java
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
~~~

Ví dụ nguyên tắc:

~~~java
@Bean
JsonMapperBuilderCustomizer jsonMapperCustomizer() {
    return builder -> {
        // Thay đổi có chủ đích trên JsonMapper.Builder.
    };
}
~~~

Đây là đoạn minh họa về điểm mở rộng, không phải file Java chạy độc lập; không sao chép một feature Jackson 2 bất kỳ sang Jackson 3 mà chưa đối chiếu API. Với nhu cầu đơn giản, properties của Boot 4 là lựa chọn dễ kiểm thử và di chuyển hơn.

Đặc biệt: **Trong Spring Boot 4, định nghĩa một ObjectMapper bean Jackson 2 không đủ để thay thế JsonMapper auto-configured của Jackson 3.** Nếu chủ động muốn thay JSON mapper mặc định của Jackson 3, cần quản lý bean **JsonMapper** phù hợp, hoặc tùy chỉnh builder/bean trong đúng framework version.

Một số thiết lập giúp giảm khác biệt khi migrate:

~~~properties
spring.jackson.use-jackson2-defaults=true
~~~

Đây là tùy chọn của Boot 4 để đưa default của JsonMapper gần hơn với Jackson 2/Boot 3. Không thay thế việc kiểm thử JSON contract và không bảo đảm mọi thư viện Jackson 2 hoạt động dưới Jackson 3.

Khi cả Jackson 2 và 3 cùng có mặt, Boot 4 có thể chọn preferred mapper cho từng phần tích hợp. Ví dụ các property liên quan có thể gồm **spring.http.codecs.preferred-json-mapper** cho WebFlux và **spring.http.converters.preferred-json-mapper** cho MVC. Chỉ đặt giá trị jackson2 khi có lý do chuyển tiếp rõ và đã kiểm tra tài liệu đúng phiên bản; đừng coi giải pháp tạm thời là mục tiêu dài hạn.

### Checklist khi migrate Boot 3.5 → 4.x

1. Xác nhận Boot BOM và Java version hỗ trợ của target.
2. Kiểm tra mọi dependency Jackson 2 và thư viện không tương thích Jackson 3.
3. Kiểm tra import com.fasterxml.jackson.databind so với tools.jackson.databind.
4. Kiểm tra ObjectMapper bean tự khai báo, Jackson2ObjectMapperBuilderCustomizer và Module beans.
5. Kiểm tra custom serializers/deserializers, @JsonComponent/@JsonMixin và JSON tree API.
6. Rà soát các spring.jackson.* feature properties, nhất là json.read/json.write.
7. Rà soát date/time, unknown fields, property inclusion, nulls, naming strategy và polymorphism.
8. So sánh JSON snapshot/contract tests ở Spring MVC và WebFlux.
9. Kiểm tra WebClient outbound nếu nó dùng mapper khác server.
10. Chỉ dùng spring-boot-jackson2 như bước chuyển tiếp có kế hoạch thay thế.

## 17. Những lỗi thường gặp và cách chẩn đoán

### 400 Bad Request khi JSON input lỗi

Nguyên nhân thường gặp: JSON sai cú pháp, kiểu dữ liệu không hợp lệ, thiếu constructor/creator hoặc strict unknown-field policy. Dùng logs exception cause, DTO schema và unit test readValue để phân biệt parse error với business validation.

Ví dụ:

~~~json
{"quantity": "not-a-number"}
~~~

Nếu DTO cần int, mapper có thể báo lỗi conversion tùy cấu hình coercion. Không sửa bằng cách tắt validation toàn bộ.

### 415 Unsupported Media Type

Client gửi Content-Type text/plain nhưng controller chỉ nhận application/json; hoặc không có reader phù hợp. Kiểm tra Content-Type, consumes và converters/codecs.

### 406 Not Acceptable

Client yêu cầu response media type mà endpoint/codec không hỗ trợ. Kiểm tra Accept, produces và writers. Đừng đổ lỗi cho ObjectMapper trước khi xem content negotiation.

### 500 hoặc lỗi serialization

Có thể do Java type không serialize được, vòng tham chiếu, custom serializer bị lỗi hoặc thiếu module. Cần xem root cause; không đưa stacktrace ra response production.

### Infinite recursion với entity quan hệ hai chiều

Một entity tham chiếu child và child lại tham chiếu parent có thể khiến serializer lặp vô hạn. Ưu tiên API DTO không có chu trình. Nếu buộc phải serialize graph, dùng Jackson annotations phù hợp có kiểm soát; không trả nguyên JPA entity rồi hy vọng Jackson tự hiểu quan hệ nghiệp vụ.

### Ngày/giờ khác mong đợi

Thường do mapper không có Java Time module, dùng timestamp numeric, timezone hoặc @JsonFormat không đồng nhất. Kiểm tra Instant so với LocalDateTime, kiểm thử timezone và schema contract.

### Null bị thiếu trong JSON

Nếu đặt NON_NULL, field null sẽ không được xuất. Điều này khác với JSON có "field": null. Một client có thể xem **missing** và **null** là hai trạng thái khác nhau. Chọn policy dựa trên API contract.

### @JsonIgnore che mất property cần nhập

Một annotation có thể ảnh hưởng cả serialization và deserialization. Khi một field chỉ được đọc hoặc chỉ được ghi, cân nhắc DTO input/output riêng hoặc access rules của @JsonProperty; đừng đặt @JsonIgnore tùy tiện rồi kỳ vọng client vẫn gửi được field đó.

### ObjectMapper tự tạo không nhận spring.jackson.*

Khi new ObjectMapper(), bạn không còn tự động dùng builder của Boot. Kiểm tra chỗ tạo bean, @Primary, @Qualifier, HTTP converter/codec được inject. Ưu tiên properties và customizer.

### Module bị thiếu hoặc đăng ký trùng

Đặc biệt khi có nhiều thư viện tích hợp, cần xác định mapper instance và danh sách modules thực sự được cấu hình. Custom serializer có thể bị override bởi module khác hoặc không được đăng ký vào mapper được dùng trong request.

### Đa hình trên input không tin cậy

Không bật default typing quá rộng hoặc deserialize loại Java tùy ý từ payload client không tin cậy. Cơ chế polymorphic type handling có rủi ro an toàn nếu cho phép tạo class ngoài danh sách được kiểm soát. Ưu tiên DTO cố định hoặc danh sách subtype cho phép.

### Trả String JSON thủ công trong controller

Nếu method trả String, Spring có thể dùng String converter thay vì JSON object converter, tạo Content-Type hoặc escaping khác mong đợi. Trả object/record hoặc ResponseEntity<DTO>, để framework sử dụng JSON serialization.

## 18. Checklist trước khi đưa thay đổi Jackson lên production

- **Version:** Đã phân biệt Jackson 2 trong Boot 3.5 và Jackson 3 trong Boot 4 chưa?
- **DTO contract:** Tên JSON field, bắt buộc/tùy chọn, null/missing, unknown fields có rõ không?
- **Data types:** Date/time, BigDecimal, enums, generic List và Unicode có test không?
- **Mapper ownership:** Có tự new hoặc @Bean ObjectMapper/JsonMapper làm Boot rút lui không?
- **Customization:** Có chọn property → annotation → customizer → module theo nhu cầu không?
- **Dependency:** Starter JSON, Jackson modules và BOM có đồng bộ không?
- **Web layer:** MVC converter hoặc WebFlux codec có dùng đúng mapper không?
- **Security:** Không trả domain entity nhạy cảm, không bật polymorphic typing rộng trên untrusted input?
- **Errors:** Có phân biệt parse/binding/validation với 406/415 và lỗi server không?
- **Regression:** Unit test mapper và integration test HTTP có kiểm tra status, Content-Type và body không?
- **Client:** Nếu có WebClient, có test JSON outbound/inbound không?
- **Performance:** Không khởi tạo mapper trong mỗi request, không serialize quá nhiều dữ liệu và không giữ body lớn trong RAM?
- **Migration:** Nếu lên Boot 4, đã test JSON diff và deprecated Jackson 2 modules chưa?

## 19. Câu hỏi tự kiểm tra

1. Serialization và deserialization khác nhau ở chiều chuyển đổi nào?
2. ObjectMapper trong Jackson 2 có vai trò gì; vì sao controller thường không cần gọi nó thủ công?
3. Với Boot 3.5, muốn bỏ null khỏi JSON toàn ứng dụng, property nào phù hợp?
4. Vì sao tự khai báo bean new ObjectMapper() có thể khiến chính sách spring.jackson.* không được áp dụng?
5. Khi nào nên dùng Jackson2ObjectMapperBuilderCustomizer thay vì application.properties?
6. @JsonProperty, @JsonIgnore và @JsonInclude phục vụ ba mục đích nào?
7. Vì sao Instant có thể lỗi trên ObjectMapper tự new mà vẫn chạy được trong Boot?
8. MappingJackson2HttpMessageConverter khác với JSON decoder trong WebFlux ở tầng nào?
9. Nếu request gửi Content-Type text/plain đến endpoint consumes application/json, status thường là gì?
10. Nếu client yêu cầu Accept application/xml nhưng endpoint chỉ có JSON writer, status thường là gì?
11. Boot 4 mặc định ưu tiên Jackson 2 ObjectMapper hay Jackson 3 JsonMapper?
12. Trong Boot 4, ObjectMapper bean Jackson 2 có tự thay JsonMapper mặc định không?
13. Rủi ro của việc deserialize polymorphic type từ JSON không tin cậy là gì?

### Đáp án gợi ý

1. Serialization Java → JSON; deserialization JSON → Java.
2. Mapper quản lý cách đọc/ghi JSON; Spring đã tích hợp converter/codec để controller trả DTO trực tiếp.
3. spring.jackson.default-property-inclusion=non_null.
4. Mapper tự tạo không được builder Boot áp dụng các properties, modules và customizers theo mặc định.
5. Khi cần điều chỉnh builder bằng code hoặc hỗ trợ tính năng không có property đơn giản.
6. Đổi tên JSON field, bỏ qua property, chọn điều kiện property xuất hiện.
7. Thiếu module Java Time hoặc settings tương ứng; Boot thường cấu hình các module quen thuộc.
8. MVC dùng HttpMessageConverter trên Servlet stack; WebFlux dùng reactive reader/writer và codecs.
9. Thường là 415 Unsupported Media Type.
10. Có thể là 406 Not Acceptable.
11. Jackson 3 JsonMapper.
12. Không; muốn thay mapper Jackson 3 phải cung cấp/tùy chỉnh JsonMapper tương ứng.
13. Có thể làm ứng dụng tạo hoặc sử dụng các type ngoài danh sách dự kiến, gây rủi ro bảo mật; cần whitelist/type constraints.

## 20. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — JSON](https://docs.spring.io/spring-boot/3.5/reference/features/json.html): Jackson 2 ObjectMapper, module và @JsonComponent.
- [Spring Boot 3.5 — Customize Jackson ObjectMapper](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html): builder, spring.jackson.* properties, Jackson2ObjectMapperBuilderCustomizer và HTTP converters.
- [Spring Boot 4.x — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3 JsonMapper mặc định và compatibility cho Jackson 2.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): package mới, Jackson 3, migration properties, @JacksonComponent và thay đổi defaults.
- [Spring Boot 4.x — Customize JsonMapper](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): JsonMapperBuilderCustomizer và các thuộc tính Jackson 3.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): Spring MVC HttpMessageConverter và JSON.
- [Spring Framework — WebFlux Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html#webflux-config-message-codecs): WebFlux HttpMessageReader/Writer và CodecConfigurer.
- [Jackson databind](https://github.com/FasterXML/jackson-databind): ObjectMapper, JsonNode, serialization/deserialization trong Jackson 2.
