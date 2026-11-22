# Tùy chỉnh spring.jackson.* và Jackson2ObjectMapperBuilderCustomizer trong Spring Boot

Spring Boot dùng Jackson để chuyển **object Java ↔ JSON** khi ứng dụng nhận request hoặc trả response qua HTTP, đồng thời có thể dùng Jackson trong service, message converter, codec hoặc những nơi cần một ObjectMapper. Hai cách chỉnh cấu hình thường gặp là:

1. **spring.jackson.*** trong application.yml/application.properties: bề mặt cấu hình do Spring Boot cung cấp cho các tính năng phổ biến của Jackson.
2. **Jackson2ObjectMapperBuilderCustomizer**: một bean callback cho phép ứng dụng bổ sung cấu hình vào Jackson2ObjectMapperBuilder do Spring Boot quản lý. Dùng khi property chưa diễn tả được serializer, deserializer, module hay quy tắc đặc biệt.

Chủ đề chính là **Jackson 2 của Spring Boot 3.5.x / Spring Framework 6.2.x**, với package com.fasterxml.jackson.* và org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer. Spring Boot 4.x ưu tiên Jackson 3 với API và nhóm customizer khác; **không sao chép nguyên mã Jackson 2 vào Boot 4 mà chưa kiểm tra migration guide**.

Nguyên tắc: **property trước, annotation theo trường/kiểu khi cần, builder customizer cho phần mở rộng chung, thay ObjectMapper chỉ khi thật sự cần**. Việc thay toàn bộ mapper quá sớm dễ làm mất các mặc định của Spring Boot, module Java Time và cấu hình đã được thiết lập bởi các starter.

## 1. Luồng xử lý JSON trong Spring Boot

Một request HTTP có thể đi theo quy trình:

~~~text
Client
  |
  | POST /api/products
  | Content-Type: application/json
  | {"product_name":"Keyboard"}
  v
Spring MVC DispatcherServlet
  |
  v
HandlerMethod + @RequestBody
  |
  v
MappingJackson2HttpMessageConverter
  |
  | sử dụng ObjectMapper cấu hình bởi Boot
  v
CreateProductRequest Java record
  |
  v
ProductController / Service
  |
  v
ProductResponse Java record
  |
  v
Jackson serializer
  |
  | Content-Type: application/json
  v
JSON response
~~~

Trong ứng dụng WebFlux, quá trình đọc/ghi body được thực hiện qua **HttpMessageReader/HttpMessageWriter và JSON encoder/decoder** thay cho Servlet MVC HttpMessageConverter. Cả hai có thể sử dụng Jackson nhưng cần xác nhận mapper và codec nào được đăng ký ở ứng dụng thực.

Các lớp thường gặp:

- **com.fasterxml.jackson.databind.ObjectMapper**: đối tượng trung tâm của Jackson 2 để serialize/deserialize.
- **Jackson2ObjectMapperBuilder** của Spring Framework: giúp xây dựng và cấu hình ObjectMapper; có thể tự phát hiện một số module quen thuộc.
- **Jackson2ObjectMapperBuilderCustomizer** của Spring Boot: callback sửa builder do Boot quản lý.
- **JacksonAutoConfiguration**: auto-configuration tạo builder/mapper và áp dụng các customizer trong điều kiện thích hợp.
- **MappingJackson2HttpMessageConverter**: converter JSON thường dùng trong MVC.
- **Jackson2JsonEncoder/Jackson2JsonDecoder**: codec JSON thường dùng trong WebFlux.
- **@JsonProperty, @JsonFormat, @JsonInclude**: annotation Jackson điều khiển cách ánh xạ trên một kiểu hoặc thuộc tính cụ thể.

Không nên coi một JSON response bất thường là lỗi của controller ngay lập tức. Cần kiểm tra thứ tự: object Java → annotation → ObjectMapper/codec → content negotiation → response body.

## 2. Spring Boot cấu hình Jackson mặc định như thế nào?

Với spring-boot-starter-web hoặc spring-boot-starter-webflux trên Boot 3.5, starter JSON thường cung cấp các dependency Jackson cần thiết. Nếu các điều kiện auto-configuration được đáp ứng, Boot tạo **ObjectMapper** và **Jackson2ObjectMapperBuilder**, rồi áp dụng các mặc định thuận tiện cho ứng dụng web.

Những điểm hay gặp trong Boot 3.x:

- DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES thường **tắt** ở mapper được Boot cấu hình: JSON chứa field không biết thường không làm request tự động thất bại chỉ vì field đó.
- SerializationFeature.WRITE_DATES_AS_TIMESTAMPS thường **tắt**: những kiểu ngày giờ được module hỗ trợ thường có biểu diễn dạng text/ISO phù hợp, nhưng còn phụ thuộc loại Java và annotation.
- MapperFeature.DEFAULT_VIEW_INCLUSION bị tắt theo cách builder/framework cấu hình.
- Module cho Java 8 date/time, Optional và một số kiểu phổ biến được đăng ký khi có dependency thích hợp.
- Jackson2ObjectMapperBuilder có thể được nhiều thành phần dùng lại để tạo các mapper cùng hướng cấu hình.

Đây là **mặc định của mapper do Boot quản lý**, không phải giá trị bắt buộc của mọi ObjectMapper trong JVM. Lệnh new ObjectMapper() của ứng dụng tạo một object riêng, không tự động nhận toàn bộ property spring.jackson.* và các builder customizers.

Không phụ thuộc vào mặc định không được ghi rõ trong hợp đồng API của dự án. Với những yêu cầu như unknown field, date format, enum hoặc null field, nên đặt property rõ ràng và viết test để bảo vệ hành vi.

## 3. Những nhóm thuộc tính spring.jackson.* quan trọng

Spring Boot 3.5.x có nhiều nhóm property. Không phải mọi enum hoặc option của Jackson đều có một key độc lập được mô tả bằng tên đầy đủ trong metadata; các nhóm có dấu * cho phép bind feature theo tên enum được hỗ trợ.

| Nhóm property | Ý nghĩa | Ví dụ |
|---|---|---|
| spring.jackson.property-naming-strategy | Quy tắc tên thuộc tính JSON | SNAKE_CASE |
| spring.jackson.default-property-inclusion | Bao gồm hoặc bỏ những field theo giá trị | NON_NULL, NON_EMPTY |
| spring.jackson.serialization.* | Bật/tắt SerializationFeature | indent-output, write-dates-as-timestamps |
| spring.jackson.deserialization.* | Bật/tắt DeserializationFeature | fail-on-unknown-properties |
| spring.jackson.mapper.* | Bật/tắt MapperFeature | accept-case-insensitive-properties |
| spring.jackson.parser.* | Bật/tắt JsonParser.Feature | allow-comments (cần cân nhắc bảo mật) |
| spring.jackson.generator.* | Bật/tắt JsonGenerator.Feature | escape-non-ascii khi có hỗ trợ tương ứng |
| spring.jackson.time-zone | Múi giờ được dùng khi Jackson format các kiểu phù hợp | Asia/Ho_Chi_Minh |
| spring.jackson.date-format | Pattern cho date format tương ứng, thường là legacy java.util.Date | yyyy-MM-dd HH:mm:ss |
| spring.jackson.locale | Locale cho định dạng phụ thuộc locale | vi_VN |
| spring.jackson.visibility.* | Ngưỡng tự động phát hiện getter, field... | field: any |

**Lưu ý:** ví dụ "allow-comments" cho JSON parser được nhắc để phân biệt nhóm cấu hình, không phải khuyến nghị bật. JSON comment không thuộc cú pháp JSON tiêu chuẩn và có thể tạo khác biệt xử lý giữa các hệ thống.

### 3.1. Ví dụ application.yml

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
    serialization:
      indent-output: false
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

Ý nghĩa:

1. productName của Java được đặt tên product_name khi dùng chiến lược snake_case và không có annotation ghi đè.
2. Field có giá trị null sẽ được loại khỏi JSON response ở mức mặc định của mapper.
3. indent-output: false không bật pretty printing.
4. write-dates-as-timestamps: false hướng tới cách biểu diễn ngày giờ không dùng timestamp đối với kiểu được hỗ trợ.
5. fail-on-unknown-properties: false cho phép các field ngoài DTO trong quá trình deserialize theo quy tắc Jackson đang áp dụng.

Boot relaxed binding nhận các kiểu chữ hoa/chữ thường, dấu gạch nối và tên feature tương ứng; tuy vậy, nên dùng những key được tài liệu phiên bản liệt kê để dễ đọc và tránh nhầm lẫn.

### 3.2. application.properties tương đương

~~~properties
spring.jackson.property-naming-strategy=SNAKE_CASE
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.indent-output=false
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.fail-on-unknown-properties=false
~~~

Không cần khai báo cả YAML và properties trong cùng một project. Nếu nhiều PropertySource cùng chứa key, Spring Environment sẽ quyết định giá trị có hiệu lực theo quy tắc precedence của Boot. Các biến môi trường hoặc tham số CLI có thể ghi đè file cấu hình theo mức ưu tiên tương ứng.

## 4. Naming strategy: camelCase trong Java, snake_case ngoài JSON

Khi khai báo:

~~~java
public record ProductResponse(
        long id,
        String productName,
        String optionalNote) {
}
~~~

và cấu hình SNAKE_CASE, Jackson có thể serialize thành:

~~~json
{
  "id": 1,
  "product_name": "Keyboard",
  "optional_note": "Demo"
}
~~~

Khi deserialize, incoming JSON có khóa product_name có thể được ánh xạ về tham số productName của record. Điều này đặc biệt có ích khi API contract dùng snake_case nhưng code Java theo camelCase.

Không nhầm **naming strategy** với việc tự đổi tên mọi chuỗi trong JSON. Nó áp dụng cho tên property được Jackson ánh xạ, không tự đổi giá trị của String hoặc khóa nghiệp vụ theo mọi kiểu dữ liệu.

### 4.1. Ghi đè trên một field

Nếu một field phải giữ tên bên ngoài khác quy tắc global, dùng @JsonProperty:

~~~java
public record ProductView(
        @JsonProperty("external_id") long id,
        String productName) {
}
~~~

Với global SNAKE_CASE, JSON có thể là:

~~~json
{"external_id":1,"product_name":"Keyboard"}
~~~

@JsonProperty khai báo tên cụ thể cho property này, phù hợp khi schema đối tác có ngoại lệ. Không nên thay naming strategy toàn cục chỉ vì một field có tên bất thường.

### 4.2. Rủi ro đổi naming strategy sau khi phát hành API

Đổi property-naming-strategy từ mặc định sang SNAKE_CASE có thể là **breaking change**:

- Response field name có thể đổi từ productName sang product_name.
- Client gửi productName trước đây có thể không được bind như mong đợi.
- JSON snapshots, OpenAPI schema, frontend models và integration tests có thể không còn khớp.
- Hệ thống phát/nhận message dùng chung ObjectMapper cũng có thể bị ảnh hưởng nếu dùng cùng mapper.

Đối với API công khai đã ổn định, cân nhắc versioning/migration, DTO riêng hoặc annotation cục bộ thay vì bật global một cách vội vàng.

## 5. Null field: NON_NULL khác NON_EMPTY và NON_DEFAULT

spring.jackson.default-property-inclusion dùng giá trị của JsonInclude.Include.

| Giá trị | Ý nghĩa thực tế | Cảnh báo |
|---|---|---|
| ALWAYS | Thông thường vẫn serialize property kể cả null | Có thể tiết lộ cấu trúc dữ liệu không cần thiết |
| NON_NULL | Bỏ các property null | Không tự bỏ "", 0, false hoặc danh sách rỗng |
| NON_EMPTY | Bỏ null và một số giá trị rỗng theo serializer/kiểu | Định nghĩa empty phụ thuộc Jackson và kiểu |
| NON_DEFAULT | Bỏ các giá trị được coi là mặc định trong ngữ cảnh tương ứng | Cần test riêng, đặc biệt với primitive/record/POJO |

Ví dụ record:

~~~java
new ProductResponse(1L, "Keyboard", null)
~~~

với NON_NULL sẽ có thể cho:

~~~json
{"id":1,"product_name":"Keyboard"}
~~~

Không coi việc **field vắng mặt** đồng nghĩa **field có null** trong mọi API. Có client phân biệt hai trường hợp, nhất là PATCH, JSON Merge Patch hoặc thao tác cập nhật từng phần.

Nếu một trường riêng cần được serialize ngay cả khi null, có thể dùng @JsonInclude(JsonInclude.Include.ALWAYS) ở phạm vi field/type tương ứng và test kết quả. Annotation trên model thường được dùng để đặt ngoại lệ mang tính hợp đồng, trong khi property global là mặc định của ứng dụng.

## 6. Serialization và deserialization không phải một việc

**Serialization**: Java object → JSON. Ví dụ trả @ResponseBody hoặc response REST.

**Deserialization**: JSON → Java object. Ví dụ nhận @RequestBody.

Một số hiểu nhầm:

- serialization.indent-output chỉ điều khiển thụt dòng JSON được ghi ra, không quyết định JSON input hợp lệ hay không.
- deserialization.fail-on-unknown-properties chỉ kiểm soát cách xử lý những thuộc tính không có mapping. Nó **không** bỏ qua JSON sai cú pháp, body quá lớn, type sai hoặc quy tắc validation.
- default-property-inclusion chủ yếu tác động **output**, không có nghĩa field input có null sẽ tự bị từ chối.
- property-naming-strategy có thể ảnh hưởng cả đầu vào và đầu ra.
- Time zone/DateFormat tác động tới một số kiểu ngày giờ, không biến mọi String thành date hoặc thay timezone mặc định của JVM.
- Jackson annotation như @JsonFormat và @JsonIgnoreProperties có thể thay đổi behavior cục bộ so với mặc định.

Một POST với Content-Type application/json nhưng JSON sai cú pháp thường tạo lỗi HTTP 400 ở tầng đọc body. Một POST có Content-Type text/plain gửi vào handler chỉ consumes JSON có thể trả HTTP 415 trước khi Jackson được gọi. Đừng điều tra spring.jackson.* khi lỗi thực tế là consumes/Content-Type.

## 7. Jackson2ObjectMapperBuilderCustomizer dùng khi nào?

Trong Boot 3.5.x, Spring Boot nhận các bean kiểu:

~~~java
org.springframework.boot.autoconfigure.jackson
        .Jackson2ObjectMapperBuilderCustomizer
~~~

Giao diện có một phương thức:

~~~java
void customize(Jackson2ObjectMapperBuilder builder);
~~~

Đây là **định nghĩa API rút gọn**, không phải Java file độc lập. Bean customizer nhận builder do Spring Boot quản lý rồi bổ sung tùy chọn trước khi mapper được xây dựng.

Những trường hợp dùng hợp lý:

- Thêm serializer hoặc deserializer cho kiểu dữ liệu nghiệp vụ.
- Bổ sung date/time formatter chuyên biệt cho một loại kiểu, khi annotation không phù hợp.
- Thêm Jackson module hoặc mix-in qua một extension point đúng.
- Tinh chỉnh feature không được expose trực tiếp bằng property.
- Chuẩn hóa cấu hình nhiều mapper được tạo từ builder do Boot quản lý.

Ví dụ cấu trúc:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> {
        // Cấu hình bổ sung tại builder do Boot quản lý.
    };
}
~~~

**Đừng nhầm** với việc tạo new ObjectMapper(). Phần builder customizer chỉ tác động đến mapper được tạo qua builder có áp dụng customizer, không tự biến đổi mọi ObjectMapper mà thư viện khác tự tạo trong tiến trình.

## 8. Thứ tự customizer và quan hệ với spring.jackson.*

Spring Boot cho phép nhiều bean Jackson2ObjectMapperBuilderCustomizer. Chúng có thể được order bằng @Order/Ordered. Trong cơ chế được Boot 3.5 tài liệu hóa, customizer cấu hình property của Boot có order **0**; vì thế có thể thêm customizer chạy trước hoặc sau.

Ví dụ:

~~~java
@Bean
@Order(1)
Jackson2ObjectMapperBuilderCustomizer amountCustomizer() {
    return builder -> builder.serializerByType(
            MoneyAmount.class, new MoneyAmountSerializer());
}
~~~

Ở ví dụ này, @Order(1) yêu cầu customizer chạy sau customizer của Boot order 0. Tuy nhiên, serializerByType cho một kiểu nghiệp vụ cụ thể vốn không xung đột với naming strategy hay NON_NULL, nên ordering chỉ được khai báo để làm rõ nguyên tắc mở rộng.

Nếu nhiều customizer cùng gọi một setter cho cùng feature, kết quả có thể phụ thuộc thứ tự áp dụng. Đừng cấu hình property một giá trị và customizer một giá trị khác rồi giả định property luôn thắng hoặc customizer luôn thắng.

Thực hành nên làm:

1. Dùng property cho cấu hình phổ biến.
2. Dùng customizer cho hành vi mới **không chồng lên** property.
3. Nếu bắt buộc phải ghi đè, quy định rõ thứ tự và test mapper kết quả.
4. Đặt customizer tại package được component scan hoặc import trong ApplicationContext.
5. Không sửa cấu hình ObjectMapper sau khi ứng dụng đã bắt đầu xử lý request; mapper được kỳ vọng có cấu hình ổn định khi chia sẻ giữa thread.

## 9. Dự án mẫu Java 17+ chạy được

Bài toán: API JSON cần dùng snake_case, bỏ field null, không thất bại do unknown field trên input, đồng thời định dạng một kiểu MoneyAmount chuyên biệt thành chuỗi kết thúc bằng " VND". Ta dùng:

- **application.yml**: cấu hình các tính năng chung đã có property.
- **Jackson2ObjectMapperBuilderCustomizer**: đăng ký serializer cho MoneyAmount.
- **@RestController**: GET và POST để quan sát dữ liệu hai chiều.
- **MockMvc**: xác minh JSON output và input theo contract.
- **ObjectMapper bean**: đối chiếu rằng serializer được đăng ký vào mapper Boot quản lý.

Để tránh phụ thuộc đến database, ví dụ dùng response cố định với id=1. Đây là demo về JSON, **không phải hệ thống lưu sản phẩm**.

Cấu trúc:

~~~text
jackson-customization-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jsondemo/
    │   │   ├── JsonDemoApplication.java
    │   │   ├── MoneyAmount.java
    │   │   ├── MoneyAmountSerializer.java
    │   │   ├── JsonConfiguration.java
    │   │   ├── CreateProductRequest.java
    │   │   ├── ProductResponse.java
    │   │   └── ProductController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/jsondemo/
            └── ProductJsonTest.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jackson-customization-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>jackson-customization-demo</name>

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

Đây là pom.xml Maven đầy đủ. spring-boot-starter-web kéo theo Jackson 2 cần thiết cho JSON trong Boot 3.5.x, và Spring Boot parent quản lý dependency versions.

### 9.2. application.yml

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: NON_NULL
    serialization:
      indent-output: false
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

Ví dụ chọn các property rõ nghĩa và không cần gắn password hoặc dữ liệu bí mật vào file. Không dùng @EnableWebMvc; Spring Boot tự cấu hình MVC và JSON converter như bình thường.

### 9.3. JsonDemoApplication.java

~~~java
package com.example.jsondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonDemoApplication.class, args);
    }
}
~~~

@SpringBootApplication bật auto-configuration và component scan các class cùng package com.example.jsondemo.

### 9.4. MoneyAmount.java

~~~java
package com.example.jsondemo;

import java.math.BigDecimal;

public record MoneyAmount(BigDecimal value) {
}
~~~

MoneyAmount là kiểu nghiệp vụ đơn giản. JSON mặc định cho record này có thể là một object với property value; trong demo ta muốn ghi một chuỗi có đơn vị.

**Lưu ý thiết kế:** trong hệ thống tài chính thật, nên trao đổi số tiền và đơn vị tiền tệ bằng một schema rõ ràng (ví dụ amount + currency), không chỉ gửi chuỗi chứa " VND". Định dạng chuỗi ở đây là một ví dụ dễ quan sát serializer custom, không phải tiêu chuẩn của API thanh toán.

### 9.5. MoneyAmountSerializer.java

~~~java
package com.example.jsondemo;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public class MoneyAmountSerializer extends JsonSerializer<MoneyAmount> {

    @Override
    public void serialize(
            MoneyAmount amount,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        generator.writeString(
                amount.value().toPlainString() + " VND");
    }
}
~~~

Đây là serializer của Jackson **2**. Nó ghi MoneyAmount thành JSON string. writeString xử lý escaping cần thiết cho giá trị chuỗi; không nên tự thêm dấu nháy rồi dùng writeRawValue khi chỉ cần serialize một String.

### 9.6. JsonConfiguration.java

~~~java
package com.example.jsondemo;

import org.springframework.boot.autoconfigure.jackson
        .Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class JsonConfiguration {

    @Bean
    @Order(1)
    Jackson2ObjectMapperBuilderCustomizer moneyAmountCustomizer() {
        return builder -> builder.serializerByType(
                MoneyAmount.class, new MoneyAmountSerializer());
    }
}
~~~

**Quan trọng về Java import:** Java không cho phép xuống dòng giữa tên package và dấu chấm trong import? Thực tế Java cho phép whitespace giữa token dấu chấm và identifier, nhưng để mã dễ sao chép và tránh nhầm lẫn, hãy viết import trong **một dòng** như sau:

~~~java
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
~~~

Phần còn lại của file giữ nguyên. Bean có @Order(1) để chạy sau customizer của Spring Boot order 0. Nó không gọi new ObjectMapper(), không thay thế toàn bộ builder và không xóa property đang áp dụng.

### 9.7. CreateProductRequest.java

~~~java
package com.example.jsondemo;

public record CreateProductRequest(
        String productName,
        String optionalNote) {
}
~~~

Jackson được cấu hình SNAKE_CASE nên input có product_name, optional_note. Nếu request có extra field, fail-on-unknown-properties: false cho phép mapper bỏ qua field không có trong DTO.

### 9.8. ProductResponse.java

~~~java
package com.example.jsondemo;

public record ProductResponse(
        long id,
        String productName,
        String optionalNote,
        MoneyAmount totalPrice) {
}
~~~

Đây là Java record dùng cả thuộc tính String và kiểu MoneyAmount custom. Với NON_NULL, optionalNote=null được bỏ khỏi output; totalPrice được custom serializer chuyển thành String.

### 9.9. ProductController.java

~~~java
package com.example.jsondemo;

import java.math.BigDecimal;
import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductResponse> get(
            @PathVariable("id") long id) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(sample("Keyboard", null));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductResponse> create(
            @RequestBody CreateProductRequest body) {

        if (body.productName() == null
                || body.productName().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        ProductResponse response =
                sample(body.productName(), body.optionalNote());

        return ResponseEntity
                .created(URI.create("/api/products/1"))
                .body(response);
    }

    private ProductResponse sample(
            String productName,
            String optionalNote) {

        return new ProductResponse(
                1L,
                productName,
                optionalNote,
                new MoneyAmount(new BigDecimal("125000")));
    }
}
~~~

Controller trả response bằng Spring MVC; converter JSON dùng Jackson mapper mà Boot cấu hình. Việc POST trả id=1 là quy ước của demo, không chứng minh có lưu dữ liệu.

**Phân biệt ranh giới:** SNAKE_CASE và NON_NULL do property quyết định; chữ " VND" của totalPrice là do customizer đăng ký MoneyAmountSerializer.

## 10. Kiểm thử toàn bộ hành vi bằng MockMvc

**src/test/java/com/example/jsondemo/ProductJsonTest.java**

~~~java
package com.example.jsondemo;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductJsonTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void getUsesSnakeCaseNullExclusionAndSerializer() throws Exception {
        mvc.perform(get("/api/products/1")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.product_name")
                        .value("Keyboard"))
                .andExpect(jsonPath("$.total_price")
                        .value("125000 VND"))
                .andExpect(jsonPath("$.optional_note")
                        .doesNotExist());
    }

    @Test
    void postDeserializesSnakeCaseAndIgnoresUnknownField()
            throws Exception {

        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "product_name": "Mouse",
                              "optional_note": null,
                              "unknown_field": 123
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/products/1"))
                .andExpect(jsonPath("$.product_name").value("Mouse"))
                .andExpect(jsonPath("$.total_price")
                        .value("125000 VND"))
                .andExpect(jsonPath("$.optional_note").doesNotExist());
    }

    @Test
    void missingProductNameIsRejected() throws Exception {
        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"optional_note\":\"none\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void bootManagedObjectMapperHasCustomizer() throws Exception {
        ProductResponse response = new ProductResponse(
                1L, "Keyboard", null,
                new MoneyAmount(new BigDecimal("125000")));

        JsonNode tree = objectMapper.readTree(
                objectMapper.writeValueAsString(response));

        assertThat(tree.path("product_name").asText())
                .isEqualTo("Keyboard");
        assertThat(tree.path("total_price").asText())
                .isEqualTo("125000 VND");
        assertThat(tree.has("optional_note")).isFalse();
    }
}
~~~

Điểm mạnh của test:

- GET xác nhận cách **serialize** field với global naming + NON_NULL + custom serializer.
- POST xác nhận **deserialize** snake_case và xử lý unknown field theo property.
- Request thiếu product_name xác nhận controller chặn dữ liệu nghiệp vụ không hợp lệ.
- Test ObjectMapper cho thấy bean được Boot quản lý có serializer từ customizer, không chỉ converter HTTP đơn lẻ.

**Không dùng JSON string equality để kiểm tra thứ tự key**: JSON object không có nghĩa thứ tự thuộc tính phải giữ như ví dụ. Dùng jsonPath hoặc JsonNode để kiểm tra cấu trúc và giá trị.

Nếu test code sử dụng Java text block (dấu """ trong .content), cần Java 15+, nên Java 17 của dự án đáp ứng.

Chạy tại thư mục gốc:

~~~bash
mvn test
mvn spring-boot:run
~~~

Maven trả exit code 0 khi test/build thành công. Nếu dependency chưa nằm trong cache, Maven cần tải từ repository đã cấu hình; số dòng log và thứ tự test không ổn định, không lấy đó làm bằng chứng correctness.

## 11. Thử API bằng curl và đọc JSON thật

Khi ứng dụng chạy trên cổng 8080 mặc định:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/products/1
~~~

Response body về mặt nội dung:

~~~json
{"id":1,"product_name":"Keyboard","total_price":"125000 VND"}
~~~

Không khẳng định thứ tự field luôn giống chuỗi trên; test chỉ kiểm tra giá trị cần thiết.

POST:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"product_name":"Mouse","optional_note":null,"unknown_field":123}'
~~~

Kết quả mong đợi: HTTP 201 Created, Location: /api/products/1; JSON chứa product_name=Mouse, total_price="125000 VND", không có optional_note vì null. unknown_field được bỏ qua trong chế độ fail-on-unknown-properties=false.

Nếu đổi property sang true, request POST ở trên có thể bị Jackson từ chối vì unknown_field và tạo HTTP 400 (qua cơ chế đọc @RequestBody của Spring MVC). Việc bật/tắt cờ này là quyết định về API contract, không nên thay sau phát hành mà không test khách hàng tích hợp.

Với Windows PowerShell, có thể dùng curl.exe để tránh khác biệt alias của phiên bản PowerShell.

## 12. Thêm Jackson Module hoặc @JsonComponent khi nào?

Nếu custom serializer/deserializer cần tái sử dụng hoặc đóng gói một nhóm kiểu, Jackson **Module** có thể hợp lý hơn việc gọi builder.serializerByType cho từng lớp.

Ví dụ một bean module cho **cùng MoneyAmountSerializer**:

~~~java
@Bean
Module moneyModule() {
    SimpleModule module = new SimpleModule("money-module");
    module.addSerializer(
            MoneyAmount.class, new MoneyAmountSerializer());
    return module;
}
~~~

Cần import:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;
~~~

Trong Boot 3.5.x, các bean Jackson Module được phát hiện và áp dụng cho builder/mapper do Boot tạo theo cơ chế auto-configuration. Đây là **lựa chọn thay thế** cho customizer đăng ký MoneyAmountSerializer; **không đăng ký cả hai cùng kiểu chỉ để thử**, vì có thể tạo cấu hình trùng hoặc thứ tự khó hiểu.

Một lựa chọn khác là **@JsonComponent** cho serializer/deserializer theo cơ chế Spring Boot 3.x, khi muốn class serializer được tự phát hiện qua component scan. Cần đọc API của Boot hiện đang dùng và kiểm thử rằng serializer xuất hiện trong mapper mà HTTP converter thực sự sử dụng.

Quy tắc lựa chọn:

- Một hoặc hai thay đổi trên mapper: Jackson2ObjectMapperBuilderCustomizer thường đơn giản.
- Gói serializer/deserializer có thể dùng lại: Jackson Module.
- Muốn tập trung thay đổi trên một DTO: @JsonProperty, @JsonFormat, @JsonInclude hoặc annotation Jackson khác.
- Nhu cầu chỉ là common feature/naming/locale: spring.jackson.*.

## 13. Ngày giờ, múi giờ và Java Time: các góc dễ lỗi

Có ba nhóm ngày giờ thường gặp:

1. **java.util.Date / Calendar**: kiểu cũ, thường chịu ảnh hưởng date-format/time-zone của mapper.
2. **java.time.Instant / OffsetDateTime / ZonedDateTime**: có thông tin instant hoặc offset/zone; định dạng phụ thuộc Java Time module và cấu hình Jackson.
3. **java.time.LocalDate / LocalDateTime**: biểu diễn ngày hoặc ngày-giờ **không có timezone gắn sẵn**; thay time-zone global không tự làm LocalDateTime trở thành một instant có múi giờ.

Ví dụ:

~~~java
public record EventResponse(
        Instant createdAt,
        LocalDate eventDate) {
}
~~~

Với Java Time module có mặt và WRITE_DATES_AS_TIMESTAMPS=false, các kiểu này thường được serialize theo biểu diễn dạng text phù hợp. Nhưng nếu API cần chuẩn ISO cụ thể, phải viết test cho từng field và từng loại dữ liệu thay vì tin mọi kiểu được xử lý giống nhau.

### 13.1. @JsonFormat cho ngoại lệ cục bộ

~~~java
public record EventView(
        @JsonFormat(pattern = "yyyy-MM-dd")
        LocalDate eventDate) {
}
~~~

Khi yêu cầu chỉ là một field, @JsonFormat thường rõ hơn việc đặt spring.jackson.date-format toàn cục. Đặc biệt, pattern của java.util.Date không nên được giả định áp dụng y hệt cho mọi kiểu java.time.

Các bản ghi hoặc code sử dụng @JsonFormat cần import com.fasterxml.jackson.annotation.JsonFormat và java.time.LocalDate.

### 13.2. Không dựa vào timezone để sửa domain model

Nếu hệ thống cần lưu thời điểm tuyệt đối, Instant/OffsetDateTime thường biểu đạt rõ hơn LocalDateTime không kèm zone. Múi giờ dùng để **hiển thị** cho người dùng là một quyết định khác với thời điểm được lưu/trao đổi. Không sửa sai domain semantics bằng cách chỉ đổi spring.jackson.time-zone.

### 13.3. Không xóa module Java Time ngoài ý muốn

Tự tạo new ObjectMapper() rồi gọi writeValueAsString với LocalDate có thể thiếu JavaTimeModule, tùy dependency và cách mapper được khởi tạo. Boot-managed builder thường xử lý module hiện diện theo cơ chế tích hợp của Spring. Khi thay mapper, phải đăng ký những module cần thiết, cấu hình format và kiểm thử lại.

## 14. Khi nhiều ObjectMapper cùng tồn tại

Một ứng dụng có thể có:

- ObjectMapper bean do Boot tự cấu hình cho JSON web.
- ObjectMapper riêng cho Kafka, file export, cache hoặc external API.
- XmlMapper riêng cho XML.
- Mapper do thư viện bên thứ ba tự tạo.
- Mapper được build từ Jackson2ObjectMapperBuilder do Boot cấu hình.

**Customizer không tự bảo đảm mọi mapper trong JVM dùng cùng cấu hình.** Mapper nào được tạo qua builder đã áp dụng customizers mới nhận những tùy chỉnh đó theo cơ chế tương ứng.

Ví dụ tạo mapper riêng nhưng vẫn từ builder do Boot inject:

~~~java
@Bean("exportObjectMapper")
ObjectMapper exportObjectMapper(
        Jackson2ObjectMapperBuilder builder) {

    return builder.build();
}
~~~

Đây là ví dụ mở rộng **không thêm vào dự án mẫu ở mục 9**, vì nhiều ObjectMapper beans có thể gây ambiguity khi inject theo kiểu và thay đổi điều kiện auto-configuration. Khi ứng dụng có nhiều mapper thật, cần đặt tên/@Qualifier rõ ràng và test đúng converter/codec dùng mapper nào.

**Không khuyến nghị**:

~~~java
ObjectMapper mapper = new ObjectMapper();
~~~

nếu mục tiêu là kế thừa toàn bộ spring.jackson.* và customizers của Boot. Mapper thủ công có thể hoạt động nhưng thường thiếu các tích hợp mà dự án đang kỳ vọng.

### 14.1. Tự khai báo ObjectMapper bean có thể làm Boot back off

Nếu ứng dụng định nghĩa mapper riêng (đặc biệt @Primary), những điều kiện auto-configuration có thể thay đổi: mapper mặc định do Boot tạo có thể không còn được tạo hoặc các converters chọn mapper khác. Việc tự khai báo Jackson2ObjectMapperBuilder bean cũng có thể thay logic chuẩn bị builder.

Hãy coi việc thay mapper là thay đổi ở **cấp hạ tầng**, cần kiểm thử JSON HTTP, module, custom serializers, naming, null inclusion, date/time và các nơi inject mapper. Đừng dùng cách đó chỉ để bật pretty printing hay thay một serializer.

## 15. Jackson và Spring MVC: tránh nhầm với HttpMessageConverter

Spring MVC chọn converter dựa trên loại Java, Content-Type của request, Accept của client và media type mà converter hỗ trợ.

Những trường hợp:

- **400 Bad Request**: JSON body có lỗi cú pháp, không bind được DTO hoặc validation thất bại.
- **415 Unsupported Media Type**: Content-Type đầu vào không được consumes mapping/converter hỗ trợ.
- **406 Not Acceptable**: Accept đòi response media type mà mapping/converter không thể cung cấp.
- **500 hoặc lỗi response**: một exception serialization không được xử lý phù hợp khi ghi response.

spring.jackson.deserialization.fail-on-unknown-properties=false không có nghĩa mọi JSON sai đều được nhận. Nó chỉ bỏ qua **unknown properties** theo quy tắc Jackson; body sai cú pháp hoặc kiểu dữ liệu không tương thích vẫn có thể bị từ chối.

**Không cần @EnableWebMvc** để custom ObjectMapper trong Spring Boot. WebMvcConfigurer có extension points riêng cho message converters; thay hoặc xóa danh sách converters có thể làm ứng dụng mất các hành vi mặc định. Nếu mục tiêu chỉ là chỉnh JSON, bắt đầu từ spring.jackson.* và customizer.

### 15.1. JSON response không chỉ do controller quyết định

Khi @RestController trả ProductResponse, Spring MVC vẫn cần converter JSON và ObjectMapper phù hợp. Nếu chuyển sang ResponseEntity<String> chứa sẵn JSON, có thể đi qua String converter và không trải qua serialization của ObjectMapper. Điều này giải thích vì sao "đặt spring.jackson.* nhưng không thấy đổi" có thể là do endpoint trả String chứ không trả DTO.

Không ghép chuỗi JSON thủ công để né converter, trừ khi có yêu cầu protocol đặc biệt và bảo đảm escaping/content type hợp lệ.

## 16. Jackson và Spring WebFlux: khác vị trí gắn codec

Spring WebFlux reactive stack sử dụng Jackson2JsonEncoder/Decoder cho JSON nếu Jackson được chọn và codec được cấu hình phù hợp. Chúng đóng vai trò tương tự converter JSON MVC nhưng không cùng loại bean.

Ví dụ WebFlux controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ReactiveProductController {

    @GetMapping("/{id}")
    public Mono<ProductResponse> find(
            @PathVariable long id) {
        return service.findById(id);
    }
}
~~~

Đây là **đoạn minh họa**, chưa có biến service hoặc import tương ứng, không thuộc dự án MVC runnable ở mục 9. Nó nhấn mạnh Mono không tự quyết định JSON format; codec và mapper vẫn cần được cấu hình.

Khi WebFlux JSON response không phản ánh customizer:

1. Xác nhận ứng dụng thực sự chạy Spring WebFlux server, không phải MVC app có WebClient.
2. Xem CodecConfigurer, CodecCustomizer và những encoder/decoder tùy chỉnh.
3. Xác nhận Jackson mapper được Boot quản lý hay do ứng dụng thay.
4. Kiểm tra entity/DTO annotation có ghi đè global settings không.
5. Test WebTestClient với JSON body thực tế, không chỉ test ObjectMapper bean riêng.

Một dự án chỉ bổ sung spring-boot-starter-webflux để dùng WebClient trong MVC chưa chắc có reactive server. Thêm WebFlux dependency không đồng nghĩa toàn bộ HTTP server stack đổi từ Servlet sang reactive.

## 17. Thứ tự ưu tiên giữa property, annotation và Java config

Không có một công thức "mọi annotation luôn thắng mọi property" cho mọi kiểu/feature, nhưng có cách tư duy hữu ích:

- **spring.jackson.*** đặt mặc định của mapper do Boot cấu hình.
- **Jackson2ObjectMapperBuilderCustomizer** chỉnh builder, có thứ tự và có thể ghi đè một phần tùy chọn nếu dùng cùng setter.
- **@JsonProperty / @JsonFormat / @JsonInclude** đặt quy tắc cục bộ trên type/property, thường được Jackson xem xét khi chọn serializer/deserializer.
- **Jackson Module** đăng ký phần xử lý theo kiểu, có thể thay cách Jackson thực hiện mapping.
- **Message converter/codec** quyết định ObjectMapper nào được dùng ở HTTP boundary.
- **ObjectMapper/JsonMapper tự tạo** có thể không sử dụng toàn bộ cơ chế trên.

Khi có xung đột, phải xác nhận bằng **test serialize và deserialize của chính type/endpoint**. Không dùng suy luận chung từ tên property để khẳng định behavior cuối cùng.

## 18. Thiết kế API an toàn và ổn định

### 18.1. Unknown fields: linh hoạt hay nghiêm ngặt?

fail-on-unknown-properties=false giúp API backward/forward compatibility ở một số trường hợp, nhưng cũng có rủi ro client tưởng một field được hỗ trợ trong khi server âm thầm bỏ qua. Với API nhạy cảm, có thể dùng DTO chỉ nhận field hợp lệ, validation rõ ràng, hoặc bật strict mode tùy hợp đồng.

Đặc biệt tránh bind trực tiếp request body vào entity chứa field quản trị như admin, role, ownerId hoặc internalStatus. Jackson naming/inclusion không thay thế authorization và mass-assignment protection.

### 18.2. Không bật polymorphic default typing tùy tiện

Với JSON không tin cậy, tránh bật Jackson polymorphic default typing có thể cho phép nhận tên class tùy ý từ input. Những tính năng polymorphic cần ràng buộc loại hợp lệ và được rà soát bảo mật; đừng cấu hình chỉ để "deserialize object bất kỳ" mà không có whitelist/validator thích hợp.

### 18.3. Giới hạn JSON lớn và sâu

Jackson có các giới hạn parser/stream và Spring HTTP có giới hạn request size/buffer; các thuộc tính này khác nhau theo Boot/Jackson version. Tránh tắt mọi giới hạn để xử lý một payload lỗi. Khi cần nhận dữ liệu lớn, cân nhắc streaming, chunking, size limits và observability.

### 18.4. Không serialize dữ liệu nhạy cảm

NON_NULL không phải công cụ che mật khẩu hay token. Không có null chỉ có nghĩa field không có giá trị; field đã chứa secret vẫn có thể bị serialize. Dùng response DTO riêng, @JsonIgnore phù hợp và nguyên tắc tối thiểu dữ liệu.

## 19. Troubleshooting: vì sao cấu hình không có tác dụng?

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| productName vẫn xuất ra camelCase | Property không được load; controller trả String; ObjectMapper khác đang được dùng | Kiểm tra Environment, response DTO, converter/codec, test mapper bean |
| optionalNote=null vẫn xuất hiện | NON_NULL không áp dụng cho mapper đó hoặc @JsonInclude ghi đè | Test ObjectMapper và annotation trên DTO |
| MoneyAmount xuất thành object thay vì string | Customizer bean không được scan hoặc mapper không build qua builder của Boot | Kiểm tra bean/customizer, đúng package và JsonNode assertion |
| Jackson2ObjectMapperBuilderCustomizer không tìm thấy | Nhầm Boot 3/4, dependency hoặc import sai | Boot 3.5 dùng org.springframework.boot.autoconfigure.jackson.* |
| Chuyển Boot 4 xong import com.fasterxml.jackson.* lỗi | Boot 4 ưu tiên Jackson 3 với package tools.jackson.* | Đọc migration guide, chuyển API hoặc dùng Jackson 2 compatibility có chủ đích |
| JSON sai cú pháp vẫn bị từ chối dù unknown-properties=false | Cờ này không cho phép JSON cú pháp sai | Xem HttpMessageNotReadableException và lỗi parser |
| Đổi time-zone nhưng LocalDateTime không đổi | LocalDateTime không chứa offset/zone | Chọn domain type đúng hoặc @JsonFormat theo contract |
| Java Time không serialize được | Tự new ObjectMapper thiếu module thích hợp | Dùng mapper Boot quản lý hoặc đăng ký JavaTimeModule phù hợp |
| Có hai customizers xung đột | Cùng sửa một tính năng nhưng order khác | Quy định thứ tự rõ, giảm config trùng và test JSON |
| WebFlux endpoint dùng format khác MVC | Codec/mapper được đăng ký khác nhau | Kiểm tra custom CodecCustomizer, Jackson encoder/decoder |
| 406 khi Accept là XML | Server chỉ hỗ trợ JSON hoặc mapping chỉ produces JSON | Xem content negotiation/codec, không chỉ Jackson properties |
| 415 khi gửi text/plain vào JSON endpoint | Sai Content-Type hoặc consumes | Sửa request header/body contract |
| JSON field bị bỏ nhưng business validation không chạy | NON_NULL điều khiển output, không kiểm tra input | Dùng @Valid, Bean Validation và service constraints |

### 19.1. Chẩn đoán bằng test, không đoán từ log

Một cách tiếp cận có hệ thống:

1. Gọi objectMapper.writeValueAsString(new ProductResponse(...)) với bean mapper do ứng dụng inject.
2. Gọi API thật hoặc MockMvc/WebTestClient với DTO tương ứng.
3. So sánh JSON tại hai lớp.
4. Nếu ObjectMapper đúng nhưng HTTP sai, kiểm tra converter/codec và return type.
5. Nếu cả hai sai, kiểm tra property loading, @Configuration, component scanning và customizer order.
6. Nếu chỉ một field sai, tìm @JsonProperty/@JsonFormat/@JsonInclude hoặc custom serializer trên kiểu đó.
7. Nếu input sai, quan sát Content-Type, request body, validation và exception thực tế.

Với Spring Boot Actuator, một số endpoint như /actuator/configprops hoặc /actuator/env có thể hỗ trợ nhìn property hiệu lực khi được cài và bảo mật đúng. Tuyệt đối không mở toàn bộ cấu hình/secret công khai để debug JSON.

## 20. Checklist trước khi merge

- [ ] Đã xác định version Spring Boot/Jackson đang chạy; ví dụ Jackson2 chỉ áp dụng Boot 3.x tương ứng.
- [ ] Dùng spring.jackson.* cho phần đã có property, không vội tự tạo ObjectMapper.
- [ ] Naming strategy đúng hợp đồng của client, không phá API đã phát hành.
- [ ] Null inclusion/unknown field behavior được quyết định có chủ đích và có test.
- [ ] Không nhầm Accept/Content-Type/consumes/produces với serialization/deserialization.
- [ ] Các module Java Time hoặc Optional cần thiết không bị mất sau customization.
- [ ] Serializer/deserializer custom chỉ áp dụng cho type phù hợp và không ghi đè không chủ đích.
- [ ] Customizer bean ở package được Spring scan, có thứ tự rõ nếu xung đột.
- [ ] Không tự tạo nhiều ObjectMapper gây ambiguity và thay đổi converter ngoài ý muốn.
- [ ] Đã test serialize và deserialize qua đúng HTTP boundary, không chỉ test ObjectMapper đơn lẻ.
- [ ] Có kiểm tra security, secret fields, mass assignment và giới hạn JSON payload.
- [ ] Mọi thay đổi JSON global có test hồi quy cho client và message schema liên quan.

## 21. Ghi nhớ

Trong **Spring Boot 3.5.x**, spring.jackson.* là lớp cấu hình khai báo cho các tính năng phổ biến của Jackson 2: naming, null inclusion, date/time, serialization/deserialization features. Jackson2ObjectMapperBuilderCustomizer là extension point để bổ sung hành vi mà property chưa diễn tả tốt, đặc biệt serializer/deserializer cho kiểu riêng.

**Không cần thay ObjectMapper để đổi một setting nhỏ.** Dùng builder do Boot quản lý, đặt extension có phạm vi rõ và test mapper thật đang được MVC converter/WebFlux codec sử dụng. Trước khi nâng sang Spring Boot 4.x, kiểm tra migration Jackson 3 vì API và nhóm customizer mặc định đã thay đổi.

## Tài liệu chính thức

- [Spring Boot 3.5 — Common Application Properties: JSON](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5.16 — Jackson2ObjectMapperBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html)
- [Spring Boot 3.5 — Spring MVC JSON Customization](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html)
- [Spring Framework 6.2 — Jackson2ObjectMapperBuilder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/json/Jackson2ObjectMapperBuilder.html)
- [Spring Boot 4 — JSON (Jackson 3 and Jackson 2 compatibility)](https://docs.spring.io/spring-boot/reference/features/json.html)
