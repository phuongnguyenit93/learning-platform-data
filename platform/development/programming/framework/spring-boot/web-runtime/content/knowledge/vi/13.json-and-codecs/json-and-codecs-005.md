# Quan hệ giữa cấu hình Jackson dùng chung và tùy chỉnh JSON riêng từng web stack trong Spring Boot

## 1. Vấn đề thực tế cần giải quyết

Một dự án Spring Boot có thể khai báo `spring.jackson.*`, tạo một `ObjectMapper` bean dùng chung, rồi vẫn gặp tình huống JSON trả từ controller khác JSON do `ObjectMapper` được inject trực tiếp tạo ra. Khi thêm `WebMvcConfigurer`, `MappingJackson2HttpMessageConverter`, `CodecCustomizer`, `WebFluxConfigurer`, hoặc tự dựng `WebClient`, khác biệt càng dễ xuất hiện.

Chẳng hạn, hệ thống muốn không xuất các thuộc tính null:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

`objectMapper.writeValueAsString(new Reply("Lan", null))` có thể cho:

~~~json
{"name":"Lan"}
~~~

Nhưng một HTTP endpoint đặc biệt lại trả:

~~~json
{"name":"Lan","note":null}
~~~

Điều này hoàn toàn có thể đúng nếu endpoint sử dụng converter/codec có `ObjectMapper` riêng được cấu hình để **giữ** thuộc tính null. Đây không nhất thiết là lỗi Spring Boot không đọc được property.

Bài này làm rõ:
- Cấu hình Jackson dùng chung gồm những gì và áp dụng đến đâu?
- Spring MVC chuyển object thành JSON nhờ thành phần nào?
- Spring WebFlux chuyển request/response body bằng thành phần nào?
- Vì sao server và `WebClient`, hay hai endpoint trong một stack, có thể khác nhau?
- Cách tùy chỉnh cục bộ mà không vô tình thay đổi tất cả endpoint hoặc làm mất mặc định của Boot?
- Cách kiểm tra `ObjectMapper` thực sự được từng converter/codec dùng?
- Cách kiểm thử phản hồi trước/sau thay đổi, cả serialization và deserialization?

Ví dụ chính dùng **Java 17+, Spring Boot 3.5.x, Jackson 2.x** với các import thuộc thế hệ đó. Spring Boot 4 chuyển hệ JSON mặc định sang Jackson 3 ở nhiều phần; không được dùng nguyên các package và extension point 3.5 để suy ra 4.x. Nội dung phân biệt rõ code chạy đầy đủ và đoạn minh họa cần lắp vào project.

## 2. Ba tầng cấu hình: Jackson, web stack, HTTP client

Khi tìm nguyên nhân khác biệt JSON, phải phân tách ba tầng.

### Tầng A — Jackson dùng chung

Spring Boot tự cấu hình Jackson khi có các dependency phù hợp, bao gồm:
- `ObjectMapper` bean do Spring quản lý.
- `Jackson2ObjectMapperBuilder` và các builder customizer.
- Các property `spring.jackson.*`.
- `Module` beans, `@JsonComponent`, một số Jackson module được phát hiện.
- Các annotation trên DTO như `@JsonProperty`, `@JsonIgnore`, `@JsonInclude`, `@JsonFormat`.

Những thứ này xác định *mapper được Boot xây* có thể serialize/deserialize thế nào. Không có quy định rằng **mọi đối tượng `ObjectMapper` trong JVM đều tự động nhận** cùng cấu hình.

### Tầng B — Adapter JSON của từng server stack

- **Spring MVC / Servlet:** `HttpMessageConverter`, thường là `MappingJackson2HttpMessageConverter` cho JSON. Converter chứa hoặc tham chiếu một `ObjectMapper` và tham gia chọn representation dựa vào type, `Content-Type`, `Accept`, `produces` và `consumes`.
- **Spring WebFlux / reactive:** `HttpMessageReader` / `HttpMessageWriter` và `CodecConfigurer`. Jackson JSON thường dùng `Jackson2JsonDecoder`/`Jackson2JsonEncoder` dưới các reader/writer adapter.

Cả hai có thể hưởng cấu hình Jackson chung của Boot, nhưng **chúng không dùng cùng một danh sách HTTP converters/codecs và không bắt buộc cùng một mapper instance** nếu ứng dụng đã tùy chỉnh.

### Tầng C — Client HTTP riêng

- `RestClient`/`RestTemplate` dùng cơ chế converter ở phía client.
- `WebClient` dùng `ExchangeStrategies` và codecs phía client.
- Client được tạo bằng `new`, builder tự tạo hoặc cấu hình riêng có thể không dùng đầy đủ auto-configuration của Boot.

Ngay cả khi server WebFlux dùng codec chuẩn, một `WebClient` có cấu hình `ExchangeStrategies` riêng vẫn có thể có chính sách JSON khác. **Không đồng nhất “toàn ứng dụng” với “mọi đường HTTP đi ra và đi vào”.**

~~~text
spring.jackson.* + Jackson customizers + Modules
                       |
         ObjectMapper bean / builder của Boot
                       |
              +--------+---------+
              |                  |
         Spring MVC          Spring WebFlux
     HttpMessageConverter     HttpMessageReader/Writer
              |                  |
       Controller JSON     Controller JSON / streaming
              |                  |
          MVC cục bộ          WebFlux cục bộ
       converter/mapper      encoder/decoder/mapper
              |
          Client HTTP riêng (RestClient/WebClient)
          có thể được cấu hình độc lập
~~~

Sơ đồ là kiến trúc khái niệm; cần kiểm tra wiring của version và application context cụ thể trước khi khẳng định hai thành phần chia sẻ cùng một instance.

## 3. Cấu hình Jackson dùng chung: spring.jackson.*

Trong Spring Boot 3.5, `spring.jackson.*` cho phép khai báo chính sách serialization/deserialization mà không phải tự đăng ký converter.

Ví dụ:

~~~properties
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.indent_output=false
spring.jackson.deserialization.fail-on-unknown-properties=false
spring.jackson.serialization.write-dates-as-timestamps=false
~~~

Các key minh họa:
- `default-property-inclusion=non_null`: trường null thường không được xuất khi serializer sử dụng mapper đó, trừ khi có annotation hoặc cấu hình cụ thể ghi đè.
- `serialization.indent_output`: bật/tắt pretty printing JSON.
- `deserialization.fail-on-unknown-properties`: xử lý trường JSON không có trong DTO.
- `serialization.write-dates-as-timestamps`: tác động cách serializer có hỗ trợ kiểu thời gian biểu diễn dates/times.

Nhớ rằng `spring.jackson.*` cấu hình **Jackson mapper được Boot quản lý**, không tự tạo custom HTTP converter cho từng media type. Một `ObjectMapper` được tạo thủ công bằng `new ObjectMapper()` có thể không có Java Time module, `@JsonComponent` hoặc các feature mà Boot cung cấp.

### 3.1. Ưu tiên property

Khi property trùng key giữa `application.properties`, profile-specific YAML, environment variables và command line, Spring `Environment` giải quyết giá trị theo thứ tự ưu tiên nguồn cấu hình. Ví dụ:

~~~bash
java -jar target/my-app.jar --spring.jackson.default-property-inclusion=always
~~~

Tên `my-app.jar` cần thay bằng JAR thật đã build. Với mapper được Boot bind từ `Environment`, giá trị cuối trong ví dụ có thể chuyển chính sách từ `non_null` sang `always`.

Tuy nhiên, property có ưu tiên cao **không có quyền bắt buộc** một HTTP converter đã được thiết lập mapper riêng phải tuân theo. Phải tách ưu tiên `PropertySource` khỏi việc chọn converter/codec thực sự.

### 3.2. ObjectMapper bean mặc định và auto-configuration back off

Spring Boot tự đăng ký `ObjectMapper` phù hợp khi chưa có bean đáp ứng điều kiện của auto-configuration. Nếu ứng dụng khai báo một `@Bean ObjectMapper` khác, auto-config có thể rút khỏi việc tạo mapper mặc định. Mapper tự tạo cần được cấu hình đầy đủ, thay vì giả định tất cả `spring.jackson.*` vẫn áp dụng.

Nếu cần thêm hành vi chung, thường **ưu tiên customizer** thay cho thay toàn bộ mapper.

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer globalJacksonPolicy() {
    return builder ->
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
}
~~~

Đây là đoạn minh họa trong một class `@Configuration`, dùng:
- `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`;
- `com.fasterxml.jackson.annotation.JsonInclude`;
- `org.springframework.context.annotation.Bean`.

Customizer được áp dụng khi builder tạo mapper; không biến tất cả các mapper bên ngoài DI thành bean dùng chung. Khi có nhiều customizer, thứ tự `Ordered`/`@Order` và các bước cấu hình thực tế có thể ảnh hưởng setting cuối.

### 3.3. Module, @JsonComponent và DTO annotations

Các cách mở rộng Jackson có phạm vi khác nhau:

| Công cụ | Ảnh hưởng mong muốn | Giới hạn |
|---|---|---|
| `spring.jackson.*` | Chính sách chung của mapper do Boot cấu hình | Không tự thay mapper thủ công |
| `Jackson2ObjectMapperBuilderCustomizer` | Tùy chỉnh builder dùng chung | Chỉ mapper được xây theo builder đó |
| Jackson `Module` bean | Đăng ký serializers/deserializers cho mapper được quản lý | Không bảo đảm vào mapper được tạo hoàn toàn độc lập |
| `@JsonComponent` | Đăng ký serializer/deserializer qua cơ chế Boot | Theo application scanning và mapper integration |
| `@JsonInclude` trên DTO | Quy tắc inclusion của kiểu/field cụ thể | Có thể khác default global |
| `@JsonFormat` | Cách biểu diễn một field/type cụ thể | Không tạo HTTP codec mới |
| `@JsonIgnore`, `@JsonProperty` | Tên/loại trừ field khi bind/serialize | Cần xét chiều read/write và security |
| `ObjectMapper.copy()` | Tạo mapper độc lập từ cấu hình đã có | Thay đổi mapper copy không thay mapper gốc |

**Nguyên tắc quan trọng:** thư viện bổ sung module hoặc serializer có thể làm thay đổi output toàn hệ thống nếu nó được gắn vào mapper chung. Một converter/codec dùng mapper tự dựng có thể bỏ qua module đó.

## 4. Cơ chế JSON trong Spring MVC

Trong Spring MVC, khi controller trả object hoặc nhận `@RequestBody`, `RequestResponseBodyMethodProcessor` và các thành phần liên quan chọn một `HttpMessageConverter` phù hợp.

Ví dụ:

~~~java
@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<OrderView> create(@RequestBody OrderInput input) {
    return ResponseEntity.ok(service.create(input));
}
~~~

Đoạn trên là fragment trong controller đã có DTO/service. Với Jackson trên classpath, một `MappingJackson2HttpMessageConverter` thường được dùng:
1. Đọc request `application/json` rồi deserialize vào `OrderInput`.
2. Serialize `OrderView` trả về sang JSON khi response media type phù hợp.
3. Dựa vào `ObjectMapper` được gắn trong converter.

`@RequestBody` không đồng nghĩa “Jackson luôn đọc body”. Ví dụ text/binary có converter khác; khi không converter nào hỗ trợ media type và type, request có thể bị từ chối.

### 4.1. Cách tùy chỉnh riêng MVC

Các đường đi hay dùng:
- Bean `HttpMessageConverter` cụ thể qua Spring Boot `HttpMessageConverters`.
- `WebMvcConfigurer.extendMessageConverters(List<HttpMessageConverter<?>>)` để điều chỉnh danh sách đã hình thành.
- `WebMvcConfigurer.configureMessageConverters(...)` khi cần can thiệp sâu vào danh sách; trong framework thuần cách này có thể thay thế defaults, nên phải hiểu hành vi Boot/Framework theo phiên bản.
- Converter với `ObjectMapper` riêng cho một media type hoặc một phạm vi response.
- `ResponseBodyAdvice` cho việc chỉnh body/headers ở tầng MVC theo contract.
- `@JsonView` hoặc DTO/annotation khác khi chỉ cần thay biểu diễn của một nhóm fields.

Không dùng `@EnableWebMvc` chỉ để thay một JSON property, vì điều đó chuyển trách nhiệm một số mặc định MVC khỏi Spring Boot.

### 4.2. Converter được chọn theo media type và thứ tự

Thêm converter không đồng nghĩa converter đó chắc chắn được dùng. Spring MVC phải xét:
- Java type/return type.
- `Content-Type` của request và `Accept` của client.
- `consumes`/`produces` trên handler.
- `canRead`/`canWrite` và danh sách supported media types.
- Thứ tự converters trong danh sách.

Converter mặc định Jackson thường hỗ trợ `application/json` và các subtype JSON như `application/*+json`. Nếu thêm converter riêng cho một vendor media type nhưng đặt sau converter mặc định, converter mặc định có thể được chọn trước trong một số trường hợp. Do đó cần kiểm thử `Content-Type`, response body và nếu cần thì đưa converter chuyên biệt tới vị trí ưu tiên xác định.

## 5. Cơ chế JSON trong Spring WebFlux

Trong WebFlux, controller có thể trả `Mono<T>`/`Flux<T>` và nhận `@RequestBody Mono<T>`; mã hóa/giải mã được thực hiện qua reactive codecs:

- `HttpMessageReader`: đọc bytes từ request thành object.
- `HttpMessageWriter`: ghi object thành response bytes.
- `Jackson2JsonDecoder`: deserialize JSON qua Jackson.
- `Jackson2JsonEncoder`: serialize JSON qua Jackson.
- `ServerCodecConfigurer`, `ClientCodecConfigurer`, `CodecCustomizer`: những điểm cấu hình codec ở phạm vi khác nhau.

Spring Boot 3.5 áp dụng `spring.jackson.*` cho Jackson codec mặc định của WebFlux. Nhưng nếu một customizer thay default encoder/decoder bằng một instance có mapper riêng, **setting trên mapper đó** mới là thứ được dùng để serialize/deserialize HTTP request.

Ví dụ `WebFluxConfigurer` thay codec JSON phía server:

~~~java
@Configuration(proxyBeanMethods = false)
class LocalReactiveJsonConfiguration implements WebFluxConfigurer {

    private final ObjectMapper global;

    LocalReactiveJsonConfiguration(ObjectMapper global) {
        this.global = global;
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        ObjectMapper local = global.copy();
        local.setSerializationInclusion(JsonInclude.Include.ALWAYS);

        configurer.defaultCodecs()
                .jackson2JsonEncoder(new Jackson2JsonEncoder(local));
        configurer.defaultCodecs()
                .jackson2JsonDecoder(new Jackson2JsonDecoder(local));
    }
}
~~~

Đây là class minh họa với imports:
- `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.annotation.JsonInclude`;
- `org.springframework.context.annotation.Configuration`;
- `org.springframework.http.codec.ServerCodecConfigurer`;
- `org.springframework.http.codec.json.Jackson2JsonEncoder`/`Jackson2JsonDecoder`;
- `org.springframework.web.reactive.config.WebFluxConfigurer`.

Phải kiểm tra cả encode và decode nếu ứng dụng cần thay chính sách hai chiều. `ObjectMapper.copy()` kế thừa cấu hình hiện tại và cho phép chỉnh bản copy mà không làm thay đổi mapper được inject ở nơi khác.

### 5.1. CodecCustomizer khác WebFluxConfigurer

`CodecCustomizer` của Spring Boot 3.5 (package `org.springframework.boot.web.codec.CodecCustomizer`) tham gia tùy chỉnh các codec do Boot thiết lập. `WebFluxConfigurer.configureHttpMessageCodecs` là extension point trong server-side WebFlux configuration.

Không suy đoán rằng một `CodecCustomizer` tùy ý chỉ ảnh hưởng server hoặc chỉ ảnh hưởng `WebClient`: cần xem đối tượng `CodecConfigurer` nào đang được customizer áp dụng bởi auto-configuration. Nếu yêu cầu là một HTTP client cụ thể, thường nên tùy chỉnh trên builder của client đó.

Đừng dùng:

~~~java
configurer.registerDefaults(false);
~~~

một cách tùy tiện: lệnh này tắt default codecs và có thể làm mất JSON, text, form hoặc SSE support nếu không đăng ký thay thế đầy đủ. Để đổi Jackson, ưu tiên sửa `defaultCodecs().jackson2JsonEncoder/Decoder` hoặc các API cấu hình hẹp được hỗ trợ.

## 6. WebClient và RestClient có thể khác server

Một lỗi thường thấy: controller WebFlux trả JSON đúng nhưng outbound `WebClient` gửi body khác, hoặc test trực tiếp `ObjectMapper` thành công nhưng request qua client thất bại.

Lý do:
- `WebClient` sử dụng `ExchangeStrategies` với codecs phía client.
- `WebClient.Builder` được Boot auto-configure có thể nhận các customizers của Boot, nhưng `WebClient.builder()` tự gọi hoặc `WebClient.create()` không nhất thiết nhận mọi cấu hình từ container.
- `RestClient`/`RestTemplate` sử dụng client-side `HttpMessageConverters`, không phải danh sách server converters của MVC.
- Bean client riêng có thể thay codec/converter hoặc mapper bằng `ObjectMapper` riêng.

Đường kiểm thử đúng không phải “mapper bean serialize như mong muốn”, mà là **gửi/nhận HTTP thực qua đúng client instance được sử dụng tại runtime**.

### 6.1. Ví dụ cấu hình WebClient riêng

Fragment dưới đây minh họa cách đặt JSON codec vào **một WebClient riêng**, không thay mọi controller:

~~~java
@Bean
WebClient auditWebClient(WebClient.Builder builder, ObjectMapper commonMapper) {
    ObjectMapper local = commonMapper.copy();
    local.setSerializationInclusion(JsonInclude.Include.ALWAYS);

    return builder.clone()
            .codecs(codecs -> {
                codecs.defaultCodecs()
                        .jackson2JsonEncoder(new Jackson2JsonEncoder(local));
                codecs.defaultCodecs()
                        .jackson2JsonDecoder(new Jackson2JsonDecoder(local));
            })
            .baseUrl("https://audit.example.org")
            .build();
}
~~~

Đây là fragment trong configuration có imports `WebClient`, `ObjectMapper`, `JsonInclude`, `Jackson2JsonEncoder/Decoder`, `@Bean`. URL chỉ là địa chỉ ví dụ, không khuyến khích phát request vào đó. `clone()` tránh thay đổi shared builder được inject cho các client khác.

Nếu bạn tạo một client mới bằng `WebClient.builder()` thay vì nhận builder được Boot cấu hình, các customizer cho builder trong application context có thể không được sử dụng. Khi so sánh JSON, phải ghi rõ **client nào** và **cách nó được tạo**.

## 7. Ma trận phạm vi hiệu lực của các loại tùy chỉnh

| Cách cấu hình | Phạm vi tác động thường mong muốn | Điều cần xác minh |
|---|---|---|
| `spring.jackson.*` | Mapper/JSON codec mặc định do Boot cấu hình | Converter/codec thực dùng có kế thừa không |
| `Jackson2ObjectMapperBuilderCustomizer` | Mapper do builder chung tạo | Có mapper tự tạo/bean custom thay default không |
| Jackson `Module` bean | Mapper được Boot tích hợp module | Mapper thủ công hoặc codec custom có dùng module không |
| DTO `@JsonInclude`/`@JsonFormat` | Type/field có annotation | Annotation override global không, request/response nào dùng DTO |
| MVC `MappingJackson2HttpMessageConverter` riêng | MVC HTTP routes/media types phù hợp | Supported media types, canWrite, thứ tự converters |
| MVC `WebMvcConfigurer` | Servlet MVC server stack | Có `@EnableWebMvc`/converters khác can thiệp không |
| WebFlux `WebFluxConfigurer` | Reactive server codecs/configuration | Encoder/decoder nào được sử dụng, có customizer khác ghi đè không |
| Boot `CodecCustomizer` | Những CodecConfigurer được Boot đưa customizer vào | Phạm vi server/client và thứ tự customizers của version |
| `WebClient.Builder.codecs(...)` | WebClient được build từ builder đó | Có dùng đúng client instance không |
| `new ObjectMapper()` | Mapper độc lập vừa tạo | Thiếu properties/modules/config chung nào |
| `ObjectMapper.copy()` rồi cấu hình | Bản mapper riêng kế thừa cấu hình ban đầu | Có đang sửa nhầm shared mapper gốc không |
| `@Primary ObjectMapper` | Bean injection ưu tiên khi nhiều mapper | Không đảm bảo mọi converter/codec sẽ dùng nó |

Không nên gọi một cấu hình “global” chỉ vì nó được khai báo ở class `@Configuration`. Phải xem scope của bean, đường dependency và phần framework thực sự tiêu thụ bean đó.

## 8. Ví dụ chạy đầy đủ 1 — Spring MVC: global bỏ null, vendor JSON giữ null

Thí nghiệm này cố ý tạo **hai response JSON khác nhau trên cùng một MVC stack**, đồng thời cùng dùng một `ObjectMapper` gốc được Boot cấu hình.

Kết quả cần chứng minh:
- `GET /standard` dùng converter JSON mặc định: field `note=null` bị bỏ.
- `GET /vendor` dùng converter chuyên biệt và mapper copy: field `note=null` được giữ.
- `ObjectMapper` được inject ở các bean khác không bị thay bởi tùy chỉnh chỉ dành cho vendor media type.

### 8.1. Tạo Maven project

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>mvc-jackson-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

File `src/main/resources/application.properties`:

~~~properties
spring.jackson.default-property-inclusion=non_null
server.port=8080
~~~

File `src/main/java/example/mvc/JacksonMvcApplication.java`:

~~~java
package example.mvc;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class JacksonMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(JacksonMvcApplication.class, args);
    }
}

record Reply(String name, String note) {}

@RestController
class JsonController {

    @GetMapping(path = "/standard", produces = MediaType.APPLICATION_JSON_VALUE)
    Reply standard() {
        return new Reply("Lan", null);
    }

    @GetMapping(path = "/vendor",
            produces = "application/vnd.example.full+json")
    Reply vendor() {
        return new Reply("Lan", null);
    }
}

@Configuration(proxyBeanMethods = false)
class VendorConverterConfiguration implements WebMvcConfigurer {

    private final ObjectMapper sharedMapper;

    VendorConverterConfiguration(ObjectMapper sharedMapper) {
        this.sharedMapper = sharedMapper;
    }

    @Override
    public void extendMessageConverters(List<HttpMessageConverter<?>> converters) {
        ObjectMapper vendorMapper = sharedMapper.copy();
        vendorMapper.setSerializationInclusion(JsonInclude.Include.ALWAYS);

        MappingJackson2HttpMessageConverter vendorConverter =
                new MappingJackson2HttpMessageConverter(vendorMapper);
        vendorConverter.setSupportedMediaTypes(List.of(
                MediaType.parseMediaType("application/vnd.example.full+json")));

        converters.add(0, vendorConverter);
    }
}
~~~

Đây là **một file Java biên dịch được** với một public class đúng tên file. `Reply` là record package-private; controller và configuration cùng package được `@SpringBootApplication` quét. Converter chuyên biệt đứng trước converter chung và chỉ hỗ trợ vendor media type được nêu.

### 8.2. Chạy và xem JSON

Trong thư mục project:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/standard
curl -i -H "Accept: application/vnd.example.full+json" http://localhost:8080/vendor
~~~

Các phần quan trọng dự kiến:

| Request | Status | Content-Type | Body |
|---|---:|---|---|
| `/standard` | 200 | `application/json` | `{"name":"Lan"}` |
| `/vendor` | 200 | `application/vnd.example.full+json` | `{"name":"Lan","note":null}` |

Thứ tự header, `Content-Length`, charset và thứ tự JSON properties có thể phụ thuộc container/converter. Bảng chỉ nêu các giá trị có ý nghĩa cho thí nghiệm.

Giải thích từng bước:
1. Property chung khiến `ObjectMapper` auto-configured bỏ null.
2. Converter chung dùng mapper mang chính sách đó khi ghi `application/json`.
3. Configuration tạo **bản copy** của mapper, đổi inclusion thành `ALWAYS`, rồi đặt vào converter chỉ dành cho vendor JSON.
4. MVC chọn converter phù hợp với `produces` và media type, nên `/vendor` giữ `note:null`.
5. Mapper gốc không bị mutate; endpoint `/standard` vẫn bỏ null.

Nếu chuyển converter chuyên biệt sang cuối danh sách, cần kiểm tra lại behavior thực: converter chung có thể hỗ trợ `application/*+json` và được lựa chọn sớm hơn. Đây là lý do thí nghiệm chủ động gọi `converters.add(0, ...)`.

### 8.3. Kiểm thử bằng MockMvc

Thêm file `src/test/java/example/mvc/JacksonMvcApplicationTests.java`:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JacksonMvcApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void defaultJsonOmitsNull() throws Exception {
        mvc.perform(get("/standard").accept("application/json"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"name\":\"Lan\"}", true));
    }

    @Test
    void vendorJsonKeepsNull() throws Exception {
        mvc.perform(get("/vendor")
                    .accept("application/vnd.example.full+json"))
                .andExpect(status().isOk())
                .andExpect(content().contentType(
                        "application/vnd.example.full+json"))
                .andExpect(content().json(
                        "{\"name\":\"Lan\",\"note\":null}", true));
    }
}
~~~

Chạy `mvn test`. Hai test kiểm tra **response thực của MVC stack**, không chỉ gọi `ObjectMapper.writeValueAsString`. `content().json(..., true)` so sánh JSON ở chế độ strict; với trường `note` đã được ghi là null, cấu trúc khác với trường không tồn tại.

## 9. Ví dụ chạy đầy đủ 2 — WebFlux: ObjectMapper chung khác codec server

Ví dụ thứ hai là **project riêng**, không đặt cùng `pom.xml` của ví dụ MVC ở trên. Nó cho thấy:
- Mapper chung có `NON_NULL` do `spring.jackson.*`.
- Server-side WebFlux codec được thay bằng mapper copy có `ALWAYS`.
- Cùng record với `note=null`, serialization trực tiếp qua mapper chung khác JSON HTTP do WebFlux gửi.

Điều này minh họa việc `ObjectMapper` bean và Jackson encoder của WebFlux không bắt buộc cùng instance sau khi tùy chỉnh.

### 9.1. Maven dependencies và property

File `pom.xml` cho project WebFlux riêng:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-jackson-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/resources/application.properties`:

~~~properties
spring.jackson.default-property-inclusion=non_null
server.port=8080
~~~

Chỉ dùng starter WebFlux cho project này; nếu thêm MVC starter, Boot thường ưu tiên MVC runtime và `WebFluxConfigurer` có thể không điều khiển server đang chạy.

### 9.2. Java source đầy đủ

File `src/main/java/example/reactive/JacksonWebFluxApplication.java`:

~~~java
package example.reactive;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class JacksonWebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(JacksonWebFluxApplication.class, args);
    }
}

record Reply(String name, String note) {}

@RestController
class ReactiveJsonController {

    private final ObjectMapper commonMapper;

    ReactiveJsonController(ObjectMapper commonMapper) {
        this.commonMapper = commonMapper;
    }

    @GetMapping(path = "/direct", produces = MediaType.TEXT_PLAIN_VALUE)
    String direct() throws JsonProcessingException {
        return commonMapper.writeValueAsString(new Reply("Lan", null));
    }

    @GetMapping(path = "/http", produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Reply> http() {
        return Mono.just(new Reply("Lan", null));
    }
}

@Configuration(proxyBeanMethods = false)
class ServerJsonCodecConfiguration implements WebFluxConfigurer {

    private final ObjectMapper commonMapper;

    ServerJsonCodecConfiguration(ObjectMapper commonMapper) {
        this.commonMapper = commonMapper;
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        ObjectMapper serverMapper = commonMapper.copy();
        serverMapper.setSerializationInclusion(JsonInclude.Include.ALWAYS);

        configurer.defaultCodecs()
                .jackson2JsonEncoder(new Jackson2JsonEncoder(serverMapper));
        configurer.defaultCodecs()
                .jackson2JsonDecoder(new Jackson2JsonDecoder(serverMapper));
    }
}
~~~

Có đúng một public class trùng tên tệp. `/direct` chủ động serialize qua `ObjectMapper` bean rồi trả `text/plain`; response này không sử dụng Jackson2JsonEncoder để serialize object `Reply` lần nữa. `/http` trả `Mono<Reply>`, được WebFlux HTTP writer/encoder xử lý.

### 9.3. Chạy và kiểm tra

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/direct
curl -i -H "Accept: application/json" http://localhost:8080/http
~~~

Bảng kết quả cần quan sát:

| Request | Status | Content-Type | Body |
|---|---:|---|---|
| `GET /direct` | 200 | `text/plain` | `{"name":"Lan"}` |
| `GET /http` | 200 | `application/json` | `{"name":"Lan","note":null}` |

Điểm cốt lõi: controller cùng sử dụng `Reply` nhưng cách ghi phản hồi khác nhau. `/direct` dùng chung mapper; `/http` đi qua codec JSON của WebFlux đã tùy chỉnh. Sự khác biệt không chứng minh Boot bỏ qua property, mà chứng minh **đường serialize không cùng một mapper**.

Nếu trong dự án thực có thêm `CodecCustomizer` hoặc `WebFluxConfigurer` khác, thứ tự customizers và cấu hình sau cùng có thể thay encoder/decoder tiếp. Vì vậy, cần kiểm tra bằng HTTP test trên đúng application context khi đánh giá một hệ thống có nhiều thư viện.

## 10. Kiểm tra deserialization, không chỉ serialization

Khác biệt JSON không chỉ là field null xuất ra response. Phía nhận `@RequestBody` cũng có thể dùng decoder/converter riêng:

- Có cho phép unknown JSON fields không?
- Có chấp nhận case-insensitive property names không?
- Định dạng `LocalDateTime`, `Instant`, enum và số có nhất quán không?
- Có custom deserializer/serializer module được đăng ký ở cả hai đường không?
- Payload lớn có bị giới hạn bởi WebFlux buffer không?
- Endpoint nhận `application/json` hay vendor media type, và converter có `canRead` không?

Ví dụ, nếu một mapper cục bộ bật:

~~~java
localMapper.configure(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
~~~

thì JSON chứa field thừa có thể bị từ chối ở converter/decoder dùng mapper cục bộ, dù mapper chung vẫn bỏ qua field ấy.

**Đây chỉ là fragment** có imports `com.fasterxml.jackson.databind.DeserializationFeature` và biến `localMapper` đã tồn tại. Không thêm dòng này vào hai chương trình mẫu ở trên nếu bạn muốn giữ kết quả test của chúng nguyên như mô tả.

### 10.1. Đừng tự đoán HTTP status từ exception thấp hơn

Trong MVC, JSON không đọc được thường dẫn tới `HttpMessageNotReadableException` và status mặc định thường là 400. Trong WebFlux, lỗi decode/validation có thể đi qua `ServerWebInputException` hoặc các exception tương ứng, nhưng error mapping tùy framework version và handlers. Kích thước payload/buffer còn có thể làm request thất bại trước khi controller chạy.

Nếu `Content-Type` không được reader/converter hỗ trợ thì thường là 415; nếu `Accept` không có representation phù hợp thì có thể là 406. Đừng coi mọi lỗi JSON đều là lỗi mapper hoặc đều trả 400.

## 11. Khi nào dùng annotation DTO thay vì thay codec?

Không phải mọi yêu cầu JSON đều cần tạo converter hoặc codec mới.

Ví dụ một trường dữ liệu chỉ muốn dùng format khác ở một DTO:

~~~java
public record InvoiceView(
        String number,
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate issuedDate) {
}
~~~

Đây là fragment dùng Jackson annotation và `java.time.LocalDate`. Nó làm thay đổi field `issuedDate` của type này mà không làm tất cả `LocalDate` trong hệ thống đổi định dạng.

Một DTO muốn luôn giữ null:

~~~java
@JsonInclude(JsonInclude.Include.ALWAYS)
public record AuditEvent(String action, String reason) {
}
~~~

Lựa chọn phạm vi:
- Một field/DTO: ưu tiên annotation/DTO projection nếu không phá vỡ hợp đồng chung.
- Tất cả JSON trên ứng dụng: `spring.jackson.*`, shared mapper builder/customizer.
- Chỉ một MIME type hoặc một nhóm endpoint MVC: converter chuyên biệt, DTO view hoặc response advice có điều kiện.
- Reactive server nói chung: `WebFluxConfigurer`/codecs.
- Một `WebClient` riêng: cấu hình codec trên client builder cụ thể.

Với API public, thay đổi global inclusion hoặc date format là **thay đổi hợp đồng dữ liệu**. Cần versioning, compatibility tests và kiểm tra client thực tế trước khi áp dụng diện rộng.

## 12. ObjectMapper.copy, new ObjectMapper và thread safety

`ObjectMapper` thường được cấu hình một lần rồi dùng chung ở nhiều threads. Việc đăng ký module, thay setting hoặc đổi serializers **sau khi mapper đã được dùng trong runtime** có thể dẫn đến hành vi không nhất quán. Tránh sửa shared mapper bên trong một request handler.

Sai hướng:

~~~java
@GetMapping("/temporary")
String bad(@RequestParam boolean showNull) throws Exception {
    commonMapper.setSerializationInclusion(
            showNull ? JsonInclude.Include.ALWAYS : JsonInclude.Include.NON_NULL);
    return commonMapper.writeValueAsString(new Reply("Lan", null));
}
~~~

Đây là fragment minh họa **không nên sử dụng**: request song song có thể can thiệp chính sách của nhau.

Các chiến lược an toàn hơn:
1. Xây mapper chung trước khi ứng dụng nhận request.
2. Tạo mapper copy cho converter/codec có cấu hình khác, cũng tại startup.
3. Với cấu hình serialization theo một lời gọi, cân nhắc `ObjectWriter`/`ObjectReader` riêng, vốn phù hợp để chia sẻ và cấu hình cách đọc/ghi.
4. Dùng DTO/annotation nếu khác biệt chỉ ở trường cụ thể.

So sánh:
- `commonMapper.copy()`: kế thừa phần lớn cấu hình, serializers/modules đã đăng ký, sau đó cho phép tùy chỉnh bản mới.
- `new ObjectMapper()`: bắt đầu với cấu hình Jackson độc lập, **không có bảo đảm** nhận mọi module và feature từ Spring Boot.
- `Jackson2ObjectMapperBuilder`: có thể tạo mapper qua builder được cấu hình, phù hợp nếu muốn tận dụng pipeline customization của Boot.

Nếu bean mapper đang do thư viện khác tạo hoặc thay `@Primary`, hãy đo trực tiếp `ObjectMapper` nào thực sự được inject trước khi cho rằng `copy()` kế thừa đúng cấu hình bạn mong đợi.

## 13. Cách xác minh mapper và converter/codec thực dùng

Không nên dừng ở việc thấy `spring.jackson.default-property-inclusion=non_null` trong file. Quy trình QA nên có bốn lớp.

### 13.1. Xác minh property có hiệu lực

Đối chiếu `Environment`, các profile, biến môi trường và command line:

~~~java
String configured = environment.getProperty(
        "spring.jackson.default-property-inclusion");
~~~

Fragment trên giả định đã inject `Environment`. Actuator `/actuator/env` và `/actuator/configprops` (nếu được bật và bảo vệ) giúp xác định property sources và binding; chúng không tự chứng minh codec runtime đang dùng mapper nào.

### 13.2. Xác minh ObjectMapper trong context

Ví dụ fragment kiểm tra chính sách mapper qua serialization:

~~~java
String json = objectMapper.writeValueAsString(
        new Reply("Lan", null));
System.out.println(json);
~~~

Với mapper chung ở hai project ví dụ, kết quả kỳ vọng:

~~~text
{"name":"Lan"}
~~~

Nếu xuất ra `{"name":"Lan","note":null}`, có thể mapper bean đã bị thay, property không còn hiệu lực hoặc annotation/module khác ảnh hưởng inclusion. Đừng kết luận server HTTP chắc chắn có cùng output: còn tầng converter/codec.

### 13.3. Xác minh danh sách MVC converters

Trong ứng dụng MVC, có thể debug `RequestMappingHandlerAdapter.getMessageConverters()` để xem các converter, thứ tự và `ObjectMapper` của `MappingJackson2HttpMessageConverter`.

Ví dụ fragment trong class đã inject `RequestMappingHandlerAdapter adapter`:

~~~java
for (HttpMessageConverter<?> converter : adapter.getMessageConverters()) {
    if (converter instanceof MappingJackson2HttpMessageConverter json) {
        System.out.println(json.getSupportedMediaTypes());
        System.out.println(json.getObjectMapper()
                .getSerializationConfig()
                .getDefaultPropertyInclusion());
    }
}
~~~

Đây là mã quan sát trong môi trường debug; chưa phải test HTTP, không cần log toàn bộ cấu hình nhạy cảm. Với converter hỗ trợ nhiều mapper per-type hoặc custom converters, kiểm tra thêm cách chọn mapper tương ứng.

### 13.4. Xác minh WebFlux server và client bằng HTTP tests

Trong WebFlux, một bean `ObjectMapper` chưa đủ để chứng minh behavior của `Jackson2JsonEncoder` đang được gắn vào `ServerCodecConfigurer`. Cách chắc chắn nhất:
- Dùng `WebTestClient` hoặc curl gọi endpoint JSON qua **web stack thật**.
- Dùng mock HTTP server / test server riêng để quan sát JSON body mà **đúng WebClient instance** gửi ra.
- Kiểm tra cả status, `Content-Type`, body và lỗi decode.
- Khi cần, debug `CodecConfigurer` trong nơi nó được cấu hình, thay vì tự tạo một codec để đo rồi suy ra codec runtime.

Lưu ý: `@WebMvcTest` và `@WebFluxTest` là các test slice, thường không nhập toàn bộ third-party config/bean giống `@SpringBootTest`. Nếu lỗi nằm ở customizer của library, nên kiểm thử full application context với đúng dependencies.

## 14. Tình huống cần quan tâm khi cùng một ứng dụng có cả hai starters

Một ứng dụng có thể khai báo cả `spring-boot-starter-web` và `spring-boot-starter-webflux` để dùng `WebClient` bên trong MVC. Spring Boot mặc định **ưu tiên Spring MVC server** trong tình huống này.

Do đó:
- `WebMvcConfigurer` có thể là nơi ảnh hưởng response của controller.
- Một `WebFluxConfigurer` dành cho reactive server **không tự động** quyết định response của controller MVC.
- `WebClient` vẫn dùng reactive client codecs, có thể riêng biệt với MVC server converters.
- Không suy đoán “có Jackson2JsonEncoder thì controller chắc chắn dùng WebFlux”.

Nếu buộc sử dụng WebFlux server, chọn web application type phù hợp, kiểm tra auto-configuration và dependency. Không chuyển stack chỉ vì muốn tùy chỉnh serialization của một route.

## 15. Các lỗi thiết kế thường gặp

1. **Cho rằng `spring.jackson.*` sửa mọi `new ObjectMapper()`.** Property chỉ được tích hợp qua cấu hình Jackson mà Boot quản lý.
2. **Tạo `@Bean ObjectMapper` mới rồi quên module/date features.** Bean tự tạo có thể làm auto mapper mặc định rút lui.
3. **Thay mapper chung trong request handler.** Dễ gây race và JSON không ổn định giữa các requests.
4. **Nhầm `HttpMessageConverter` MVC với reactive `HttpMessageWriter`/encoder.** Chúng là hai pipeline khác nhau.
5. **Cấu hình WebFlux codec nhưng ứng dụng chạy MVC server.** Controller không dùng extension point bạn nghĩ.
6. **Tưởng mọi `CodecCustomizer` chỉ tác động WebFlux server.** Phải tìm nơi customizer được áp dụng.
7. **Tự tạo `WebClient.builder()` rồi trông chờ tất cả Boot customizers.** Các builder được quản lý/cấu hình có thể khác.
8. **Converter vendor đặt sau converter chung** dù media type cũng được converter chung hỗ trợ. Có thể không chọn converter mới.
9. **Thêm converter với `application/json` quá rộng** chỉ để sửa một route. Có thể thay đổi cả ứng dụng.
10. **Gọi `registerDefaults(false)` khi chỉ muốn đổi JSON.** Có thể tắt các codecs thiết yếu khác.
11. **Thấy ObjectMapper serialize đúng và kết luận HTTP đúng.** Phải test qua converter/codec được runtime chọn.
12. **Chỉ sửa encoder, bỏ decoder** trong khi yêu cầu có cả đọc và ghi JSON. Dẫn đến API bất đối xứng.
13. **Đổi `FAIL_ON_UNKNOWN_PROPERTIES` toàn cục mà không test client.** Có thể làm requests cũ bị từ chối.
14. **Dùng annotation Jackson trên domain entity nhạy cảm để “ẩn” field.** Serialization security không thay thế authorization và DTO.
15. **Không phân biệt unknown property và null inclusion.** Một là deserialization input, một là serialization output.
16. **Cho rằng properties date formatting ảnh hưởng mọi kiểu Java Date/Time như nhau.** Cần module, type và annotation phù hợp.
17. **Bỏ qua media type selection.** Một endpoint có thể trả 406/415 trước khi Jackson thực sự chạy.
18. **Dùng test slice rồi tin rằng thư viện production đã được import.** Cần full context khi phân tích third-party customizers.

## 16. Checklist trước khi triển khai tùy chỉnh Jackson

- [ ] Đã phân biệt nhu cầu đổi chung toàn app với đổi một endpoint/media type/client.
- [ ] Đã xác định Boot version, Jackson 2/3 version và web application type.
- [ ] Đã kiểm tra `spring.jackson.*` được bind từ nguồn cấu hình thực tế nào.
- [ ] Đã xác minh `ObjectMapper` bean hiện tại có phải mapper do Boot tạo/configure không.
- [ ] Đã kiểm tra `@JsonComponent`, Jackson `Module`, DTO annotations và customizers.
- [ ] Đã kiểm tra MVC `HttpMessageConverter` thực tế, supported media types và thứ tự.
- [ ] Nếu dùng WebFlux, đã phân biệt `ServerCodecConfigurer`, `CodecCustomizer` và `WebClient` codecs.
- [ ] Đã tránh sửa shared mapper sau khi ứng dụng nhận requests.
- [ ] Đã dùng mapper copy hoặc cấu hình cấp DTO nếu cần khác biệt cục bộ.
- [ ] Đã kiểm thử cả serialization và deserialization khi yêu cầu ảnh hưởng cả hai.
- [ ] Đã kiểm tra `Content-Type`, `Accept`, `produces` và `consumes`.
- [ ] Đã kiểm tra Jackson modules hỗ trợ Java Time, Kotlin hoặc custom types cần thiết.
- [ ] Đã có test HTTP thực cho MVC/WebFlux và từng client liên quan.
- [ ] Đã bao gồm null, unknown field, date, enum, malformed JSON và payload size trong hồi quy nếu liên quan.
- [ ] Đã tránh vô hiệu hóa hàng loạt default codecs hoặc dùng `@EnableWebMvc`/`@EnableWebFlux` không cần thiết.

## 17. Kết luận

**Jackson dùng chung và JSON của từng web stack liên quan nhưng không đồng nhất.** `spring.jackson.*`, builder customizers và Jackson modules thiết lập chính sách cho những mapper/codec được Spring Boot quản lý. Spring MVC ghi/đọc JSON qua `HttpMessageConverter`, còn WebFlux dùng `HttpMessageReader`/`HttpMessageWriter` và Jackson encoder/decoder. Một converter, codec hoặc WebClient được gắn mapper riêng có thể cố ý khác chính sách chung. Cách thiết kế tốt là chọn **phạm vi tùy chỉnh hẹp nhất** phù hợp với hợp đồng API, không mutate shared mapper khi đang phục vụ request, và xác nhận kết quả bằng HTTP test đúng runtime.

## Tài liệu chính thức để đối chiếu API

- Spring Boot 3.5 — JSON và Jackson: https://docs.spring.io/spring-boot/3.5/reference/features/json.html
- Spring Boot 3.5 — Reactive Web Applications và HTTP codecs: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Servlet Web Applications và HttpMessageConverters: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Spring MVC how-to: https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html
- Spring Framework 6.2 — MVC Message Converters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html
- Spring Framework 6.2 — WebFlux HTTP Codecs: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
