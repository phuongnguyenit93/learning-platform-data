# Đối chiếu cấu hình mapper trong test với mapper ứng dụng thực tế

## 1. Vấn đề cốt lõi: test JSON xanh nhưng API thật trả JSON khác

Trong Spring Boot, ứng dụng có thể dùng Jackson để chuyển đổi dữ liệu Java ↔ JSON. Tuy nhiên, việc một bài test gọi thành công `new ObjectMapper().writeValueAsString(...)` **không chứng minh** rằng JSON trả về bởi Spring MVC hay một HTTP client của ứng dụng có cùng hình dạng. Lý do: mapper mà test tạo thủ công có thể **không mang cấu hình do Spring Boot, application properties, customizers, Jackson modules và message converters áp dụng**.

Ngay cả khi test inject được một bean `ObjectMapper`, vẫn nên xác minh output của **đường HTTP thực sự dùng mapper**. Ứng dụng có thể có nhiều mapper, `MappingJackson2HttpMessageConverter` tự định nghĩa, WebFlux codecs, Jackson custom serializer, hoặc module chỉ được nạp trong một profile.

Ví dụ lỗi thường gặp:

- Production quy định tên trường kiểu `snake_case`: `order_id`, nhưng test dùng mapper mặc định nên kỳ vọng `orderId`.
- Production bỏ các thuộc tính null, nhưng test tạo mapper mới nên JSON còn `"internalNote":null`.
- Production serialize `LocalDate` thành chuỗi ISO, nhưng mapper test thiếu module `java.time` nên ném lỗi hoặc dùng định dạng khác.
- Ứng dụng bật `FAIL_ON_UNKNOWN_PROPERTIES` để từ chối trường JSON không công bố, nhưng test dùng mapper mặc định của Boot nên không phát hiện contract khác.
- `@JsonTest` kiểm tra DTO pass, nhưng application có `@Configuration` tùy biến mapper **không thuộc phạm vi quét của slice**.
- Một `@Bean ObjectMapper` hoặc custom MVC converter làm thay đổi đường HTTP, trong khi test vẫn inject hoặc tạo **mapper khác**.
- Nâng từ Spring Boot 3/Jackson 2 lên Spring Boot 4/Jackson 3 và chỉ thay tên dependency mà không cập nhật `JsonMapper`/customizers/modules.

Bài học này tập trung vào một câu hỏi thực dụng:

> **Làm sao chứng minh JSON do test mong đợi cũng là JSON mà ứng dụng đang thực sự ghi/đọc tại ranh giới HTTP?**

Cách làm là **tái sử dụng cấu hình production trong JSON slice**, kiểm tra trực tiếp **bean mapper được auto-configure**, sau đó xác minh **Spring MVC request/response conversion** trên full test context; nếu hợp đồng cần transport, thêm test qua real HTTP server.

### Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Phân biệt mapper Jackson tạo thủ công với mapper do Spring Boot quản lý.
2. Hiểu các nguồn cấu hình: `spring.jackson.*`, builder customizer, `Module`, `@JsonComponent`, `@JsonMixin`, annotations trên DTO và `HttpMessageConverter`.
3. Dùng `@JsonTest` + `JacksonTester` và **`@Import` cấu hình dùng chung** một cách có chủ đích.
4. Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để assert JSON đúng tại controller, converter và exception handling.
5. Biết khi nào cần bổ sung `RANDOM_PORT` + HTTP client để chứng minh JSON đi qua socket.
6. Đọc đúng khác biệt Spring Boot 3.x/Jackson 2 và Spring Boot 4.x/Jackson 3.
7. Tránh test “xanh giả”, test lệch profile và các cấu hình mapper được áp dụng hai lần hoặc không áp dụng.

**Phạm vi chạy thử:** Java 17+, Spring Boot **3.x**, JUnit Jupiter, Spring MVC Servlet stack và Jackson 2. Những phần riêng cho Spring Boot 4.x chỉ là hướng dẫn tương thích, **không khẳng định** bạn có thể copy nguyên file Java 3.x sang Boot 4.x.

## 2. Ba đối tượng thường bị gọi chung là “mapper”

| Đối tượng | Vai trò | Điều test chứng minh khi sử dụng |
|---|---|---|
| `new ObjectMapper()` | Jackson 2 mapper được Java code tự tạo bằng cấu hình ban đầu | Chỉ hành vi của **instance đó**, không chứng minh đã nhận customizer/Boot modules |
| Bean `ObjectMapper` từ Spring ApplicationContext | Mapper do Boot auto-configure hoặc do application khai báo | Chính sách của **bean đã inject** trong context test tương ứng |
| Mapper/codec thực sự dùng bởi HTTP layer | Ví dụ mapper nằm trong `MappingJackson2HttpMessageConverter` hoặc codecs | Dạng JSON đi vào/ra **đường request/response** được test |

Ba đối tượng **có thể** sử dụng cùng chính sách, nhưng không tự động là cùng một instance trong mọi ứng dụng. Lớp thứ ba cần được xác minh nếu mục tiêu là HTTP contract.

### 2.1. Jackson có hai chiều độc lập

**Serialization**:

```text
PurchaseEvent Java record
    │
    └── ObjectMapper / HTTP message converter
           └── JSON: {"order_id":"PO-42","purchased_at":"2026-11-08"}
```

**Deserialization**:

```text
JSON request body
    │
    └── ObjectMapper / HTTP message converter
           └── PurchaseEvent Java record
```

Cấu hình có thể ảnh hưởng khác nhau:

- Naming strategy ảnh hưởng tên property trong cả hai chiều.
- Inclusion strategy (ví dụ `NON_NULL`) chủ yếu quyết định **trường nào được ghi ra**.
- `FAIL_ON_UNKNOWN_PROPERTIES` ảnh hưởng **đọc JSON**.
- `WRITE_DATES_AS_TIMESTAMPS` và Java time module ảnh hưởng biểu diễn temporal values.
- Custom serializer có thể tác động chiều ghi, custom deserializer chiều đọc.
- `@JsonView`, `@JsonProperty`, `@JsonIgnore`, `@JsonFormat` hoặc mixin có thể điều chỉnh riêng DTO/endpoint.

Một test chỉ ghi JSON không chứng minh chiều đọc đúng; một bài test chỉ parse JSON cũng không chứng minh response serialization.

### 2.2. Spring Boot 3.x và cấu hình Jackson 2

Với Spring Boot 3.x và Jackson trên classpath, Boot có khả năng tự cấu hình một `ObjectMapper`. Các nguồn cấu hình quan trọng:

- Application properties thuộc nhóm `spring.jackson.*`.
- `Jackson2ObjectMapperBuilderCustomizer` beans để tùy biến `Jackson2ObjectMapperBuilder`.
- Jackson `Module` beans và các module được Boot hỗ trợ tự đăng ký theo nhánh/version.
- `@JsonComponent` hoặc `@JsonMixin` được phát hiện theo cơ chế của Boot.
- Annotation đặt trên model/record, ví dụ `@JsonProperty`, `@JsonFormat`.
- `@Bean ObjectMapper` hoặc `@Bean MappingJackson2HttpMessageConverter` nếu ứng dụng muốn thay mặc định.

Các lớp cấu hình này không nhất thiết xuất hiện trong một **JSON test slice** nếu bạn chỉ đặt `@JsonTest` và mong Spring quét toàn bộ application configuration như `@SpringBootTest`.

## 3. Tại sao tự tạo `ObjectMapper` trong test dễ sai?

### 3.1. Phản ví dụ phổ biến

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(
        new PurchaseEvent("PO-42", LocalDate.of(2026, 11, 8), null));
```

Đây là **đoạn phản ví dụ**, giả định `PurchaseEvent` đã được khai báo và imports đầy đủ; **không phải test chạy độc lập**. Mapper vừa được tạo không tự nhận cấu hình Boot, customizer beans hoặc các module mà application context đã đăng ký. Với Java Time type như `LocalDate`, một mapper thuần có thể thiếu `JavaTimeModule` và không xử lý như mapper được Boot cấu hình.

Không “sửa” bằng cách chỉ thêm:

```java
mapper.registerModule(new JavaTimeModule());
```

vì bạn vẫn có thể bỏ sót naming, inclusion, custom serializers, date/time policies, mixins, unknown-field policy, custom converter và profile-specific settings.

### 3.2. Cách nên làm

- Nếu cần kiểm thử **thuần JSON mapping**: dùng `@JsonTest`, inject `JacksonTester<T>` và `ObjectMapper`; import cấu hình production quan trọng mà slice không tự nạp.
- Nếu cần kiểm thử **HTTP response/body**: dùng `@WebMvcTest` hoặc `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`, gửi request qua MockMvc và assert JSON thực sự trong response.
- Nếu cần kiểm thử **HTTP wire format** hoặc container-specific behavior: dùng `@SpringBootTest(RANDOM_PORT)` và client HTTP thực.
- Nếu test chỉ một hàm Java thuần tự tạo mapper với cấu hình tường minh, hãy assert đúng instance đó; nhưng đừng gọi kết quả là “production mapper parity” nếu application không dùng cùng cách tạo.

### 3.3. Một quy tắc quan trọng khi so sánh

**Đừng chỉ so hai kết quả đều được tạo từ cùng một mapper test** rồi kết luận controller đã dùng mapper ấy. Ví dụ:

```java
String left = mapper.writeValueAsString(event);
String right = mapper.writeValueAsString(event);
assertEquals(left, right);
```

Đây là phản mẫu: hai lần gọi cùng phương thức trên cùng instance chỉ chứng minh tính tự nhất quán của instance, **không hề đi qua Spring MVC**. Cần thêm phép đo độc lập trên `MockMvc.perform(...)` hoặc HTTP client.

## 4. Chọn lớp test: @JsonTest, @WebMvcTest hay @SpringBootTest?

| Kỹ thuật | Context / behavior | Nên dùng để |
|---|---|---|
| JUnit + `new ObjectMapper(...)` | Không Spring; mapper do bạn tạo | Unit test mapper được **chính code đó** sử dụng, cấu hình đầy đủ bằng tay |
| **`@JsonTest`** | JSON slice; auto-configure JSON mapper/tester, giới hạn scanned components | Test serializer/deserializer và JSON configuration được đưa vào slice |
| `@WebMvcTest(Controller.class)` | MVC slice có controller, converters, validation, advice; service thường cần mock | Test hợp đồng HTTP của web layer gọn và nhanh |
| **`@SpringBootTest(MOCK) + @AutoConfigureMockMvc`** | Full test ApplicationContext + MockMvc in-process, không mở server socket | Đối chiếu bean mapper và converter/HTTP output với cấu hình ứng dụng đầy đủ |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Embedded server thật và request qua socket | Kiểm tra JSON wire contract ở cổng HTTP + container/client |
| End-to-end ở staging | Hạ tầng/deployment theo staging | Kiểm tra proxy, TLS, routing, gateway và config được triển khai |

`@JsonTest` **không có nghĩa** “load mọi @Configuration mà ứng dụng production sử dụng”. Đây là slice chủ động giới hạn component scanning. Theo Spring Boot 3.x, những loại JSON component liên quan như `@JsonComponent`, Jackson `Module` được slice hỗ trợ. Các service/regular configuration beans khác không tự được quét như full context.

Nếu tùy biến mapper được khai báo trong một configuration class thông thường, **`@Import(SharedJsonConfiguration.class)`** là cách rõ ràng để cùng một class cấu hình phục vụ production và slice. Đừng copy lại các setter của mapper vào test: khi business đổi naming strategy, hai bản copy dễ lệch nhau.

### 4.1. Nguyên tắc ưu tiên

1. Xác nhận **chính xác HTTP/framework boundary** bạn cần chứng minh.
2. Tái sử dụng **production configuration** thay vì tạo một cấu hình chỉ để “làm test xanh”.
3. Assert **cả serialization và deserialization** theo contract.
4. Với HTTP, assert output/body tại ranh giới controller/converter, không chỉ inject một `ObjectMapper`.
5. Khi có nhiều mapper/converters, xác định rõ **mapper nào đang được code path đó dùng**.

## 5. Định nghĩa một JSON contract có thể đo lường

Ta sử dụng Java record:

```java
public record PurchaseEvent(
        String orderId,
        LocalDate purchasedAt,
        String internalNote
) {}
```

Đây là **snippet cấu trúc DTO**; file hoàn chỉnh ở phần 7.

Giả sử contract mà ứng dụng muốn cung cấp:

| Khía cạnh | Chính sách | Hợp đồng cụ thể |
|---|---|---|
| Tên trường | `SNAKE_CASE` | `orderId` → `order_id`, `purchasedAt` → `purchased_at` |
| Null inclusion | `NON_NULL` | Nếu `internalNote == null`, response **không có** key `internal_note` |
| Ngày Java Time | Chuỗi ISO, không timestamp array | `LocalDate.of(2026,11,8)` → `"2026-11-08"` |
| Unknown JSON keys | `FAIL_ON_UNKNOWN_PROPERTIES = true` | Input có key `unknown_field` → deserialization error; HTTP → 400 theo Spring MVC |
| Đối xứng đầu vào/đầu ra | Jackson mapping dùng cùng quy ước | JSON `snake_case` parse thành record và ghi lại đúng quy ước |

JSON đúng của event có `internalNote = null`:

```json
{
  "order_id": "PO-42",
  "purchased_at": "2026-11-08"
}
```

Một số JSON **không đúng** với contract ấy:

```json
{
  "orderId": "PO-42",
  "purchasedAt": "2026-11-08",
  "internalNote": null
}
```

Không phải tất cả dự án đều cần snake_case, NON_NULL hoặc reject unknown fields. Các chính sách này **được chọn có chủ đích để test thấy khác biệt**, không phải khuyến nghị bật mọi flag trong mọi API. Ví dụ, nhiều API công khai cần backward/forward compatibility và cố ý bỏ qua unknown fields.

## 6. Cấu hình production: properties, customizers, modules và converters

### 6.1. Application properties trên Spring Boot 3.x

Bạn có thể định nghĩa một số quy tắc mapper bằng file `application.properties`:

```properties
spring.jackson.property-naming-strategy=SNAKE_CASE
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Đây là **phương án cấu hình thay thế** cho ví dụ Java config ở phần 7, **không được đồng thời thêm vào sample đó rồi suy ra một cơ chế thứ tự ưu tiên mới**. Các property trên được Spring Boot 3.x hỗ trợ; nên xác nhận exact property keys ở version cụ thể của dự án.

Ưu điểm: dễ thấy chính sách ở config, có thể override theo profile. Hạn chế: test slice có thể đọc **khác file/profile** hoặc có property override khác, nên cần so cấu hình hiệu lực chứ không suy luận từ file mà bạn tưởng đang được load.

### 6.2. Jackson2ObjectMapperBuilderCustomizer

Khi cần tùy biến bằng code, Spring Boot 3.x hỗ trợ interface:

```java
org.springframework.boot.autoconfigure.jackson
        .Jackson2ObjectMapperBuilderCustomizer
```

Một bean kiểu này sửa cấu hình builder mà Boot sử dụng để tạo mapper. Đây là con đường thường phù hợp hơn việc tự thay hẳn `ObjectMapper`, vì nó giữ được nhiều phần Boot auto-configuration/modules đang áp dụng.

Một customizer có thể chỉnh:

- `propertyNamingStrategy(...)`;
- `serializationInclusion(...)`;
- `featuresToEnable(...)` hoặc `featuresToDisable(...)`;
- date/time format, deserializer/serializer, visibility hoặc modules tùy mức độ cần thiết.

**Chú ý ordering:** nếu dự án có nhiều customizers, thứ tự áp dụng cũng ảnh hưởng giá trị cuối cùng. Một test slice chỉ import một customizer mà production lại có thêm customizer khác có thể vẫn lệch. Để chứng minh hợp đồng, kiểm tra cả hiệu ứng thực tế ở full context.

### 6.3. Jackson Modules

Jackson modules có thể cung cấp:

- Java Time serializers/deserializers;
- support cho JDK8 types, optional hoặc domain types;
- serializers/deserializers tùy chỉnh;
- behavior theo mixin, subtype hoặc polymorphic typing.

Nếu test tạo `new ObjectMapper()` mà quên module, kết quả có thể khác Boot mapper. Nếu một module production chỉ được khai báo bằng một `@Bean Module` trong `@Configuration` bị slice loại, JSON slice có thể bỏ sót nó. Khi cần, import module/config đúng theo ý đồ.

**Tránh “đăng ký thật nhiều module cho chắc”.** Modules có thể thay behavior, xung đột serializer hoặc được Boot đăng ký tự động tùy version. Hãy xác định module cần thiết và tạo test hành vi cho nó.

### 6.4. @JsonComponent, @JsonMixin và DTO annotations

- `@JsonComponent` trong Boot 3.x là cách khai báo serializer/deserializer Jackson được tích hợp Spring.
- `@JsonMixin` cho phép thêm Jackson annotations cho một type mà không chỉnh source của type.
- `@JsonProperty("...")` có thể ghim tên trường cụ thể bất kể naming strategy chung.
- `@JsonFormat` có thể đặt format cho từng temporal property.
- `@JsonInclude`/`@JsonIgnore` có thể override chính sách toàn cục ở mức type/field.
- `@JsonView` có thể làm controller response khác direct mapper output nếu view khác.

Đừng kết luận “global mapper naming strategy hỏng” chỉ vì một DTO có `@JsonProperty` ghi đè tên. Khi một endpoint dùng Jackson view, test cần cấp đúng serialization view tương ứng hoặc assert HTTP response, không so đơn giản với `mapper.writeValueAsString(dto)` mặc định.

### 6.5. MVC HTTP message converters có thể dùng mapper khác

Spring MVC dùng `HttpMessageConverter` để đọc/ghi HTTP bodies. Trên Boot 3.x với Jackson, loại converter phổ biến là `MappingJackson2HttpMessageConverter`. Nhưng ứng dụng có thể:

- khai báo converter riêng với mapper riêng;
- customizers/converters thay đổi global configuration;
- chọn converter khác theo `Content-Type`/`Accept`;
- dùng serializer khác như Gson hoặc JSON-B ở những tình huống được cấu hình;
- dùng endpoint-specific view/response wrapper hoặc request body advice.

Vì vậy, **mapper bean cùng chính sách với HTTP converter** là điều cần chứng minh bằng **HTTP contract tests**. Suy đoán “inject được bean ObjectMapper A nên mọi endpoint đều dùng chính A” không đủ trong một ứng dụng nhiều converters.

## 7. Ví dụ chạy được Java 17+ / Spring Boot 3.x

Ví dụ bao gồm **một cấu hình production dùng chung**, một JSON test slice, một full-context MVC test và một test real HTTP để đối chiếu contract ở ba boundary. Nó **không cần Docker, database, external service hoặc Spring Security**.

Tất cả source production ở package `com.example.mapperparity`; test classes cùng package. Dùng Spring Boot 3.x (chẳng hạn nhánh 3.5), Java 17+, JUnit Jupiter, starter web và starter test. Không thêm production ObjectMapper khác hay custom MVC converter thứ hai vào đúng sample này.

### 7.1. Dependencies

Gradle Groovy DSL — phần dependencies/test task trong dự án **đã có** Spring Boot plugin, repositories, dependency management và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — phần dependencies trong dự án đã có Spring Boot parent/BOM, compiler/toolchain Java 17 và Surefire hỗ trợ JUnit Jupiter:

```xml
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
```

**Đây là snippets của build file, không phải toàn bộ `pom.xml`/`build.gradle`**. Starter web trong Boot 3.x bao gồm Jackson JSON support và Java Time modules qua dependencies được quản lý; test starter có Spring Test, JacksonTester integration, JUnit Jupiter và AssertJ.

### 7.2. Cấu trúc file

```text
src/
├── main/java/com/example/mapperparity/
│   ├── MapperParityApplication.java
│   ├── PurchaseEvent.java
│   ├── SharedJsonConfiguration.java
│   └── PurchaseEventController.java
└── test/java/com/example/mapperparity/
    ├── PurchaseEventJsonSliceTest.java
    ├── PurchaseEventMvcContractTest.java
    └── PurchaseEventLiveHttpTest.java
```

**Không cần tạo file properties riêng** để chạy ví dụ. Cấu hình production được đặt trong `SharedJsonConfiguration`, không bị copy thành logic khác trong test.

### 7.3. Application class

**File `src/main/java/com/example/mapperparity/MapperParityApplication.java`:**

```java
package com.example.mapperparity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MapperParityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MapperParityApplication.class, args);
    }
}
```

Đặt main class trong package gốc để component scanning nạp được cả controller và production JSON configuration ở full application context.

### 7.4. DTO là một Java record

**File `src/main/java/com/example/mapperparity/PurchaseEvent.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

public record PurchaseEvent(
        String orderId,
        LocalDate purchasedAt,
        String internalNote
) {}
```

Không đặt riêng `@JsonProperty` hay `@JsonFormat` lên DTO trong ví dụ để dễ thấy **tác dụng của cấu hình mapper chung**. Java record tạo accessors theo tên component; Jackson được starter web/Boot 3 cung cấp có hỗ trợ record và Java Time.

### 7.5. Cấu hình mapper thực sự dùng trong ứng dụng

**File `src/main/java/com/example/mapperparity/SharedJsonConfiguration.java`:**

```java
package com.example.mapperparity;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SharedJsonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jsonContractCustomizer() {
        return builder -> {
            builder.propertyNamingStrategy(
                    PropertyNamingStrategies.SNAKE_CASE);
            builder.serializationInclusion(
                    JsonInclude.Include.NON_NULL);
            builder.featuresToEnable(
                    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
            builder.featuresToDisable(
                    SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        };
    }
}
```

**Giải thích:**

1. `@Configuration` và `@Bean` tạo một customizer thuộc full application context.
2. `propertyNamingStrategy(SNAKE_CASE)` đổi `orderId` thành `order_id`, `purchasedAt` thành `purchased_at`, `internalNote` thành `internal_note`.
3. `serializationInclusion(NON_NULL)` làm null property vắng trong JSON response.
4. `FAIL_ON_UNKNOWN_PROPERTIES` khiến mapper reject JSON có trường không thuộc DTO.
5. `WRITE_DATES_AS_TIMESTAMPS` bị tắt; với JavaTimeModule trong starter cấu hình Boot 3, `LocalDate` được thể hiện bằng ISO string như `"2026-11-08"`.
6. Test slice **phải import configuration này** nếu nó không thuộc nhóm JSON components mặc định được scan; còn full `@SpringBootTest` dùng component scanning của application để nạp nó.

Điểm hay của thiết kế: khi thay đổi chính sách JSON, sửa **một class production** rồi cả JSON slice và HTTP tests phải phản ánh contract mới. Không có “test-only ObjectMapper” sao chép cấu hình.

### 7.6. Controller sử dụng response/request JSON của Spring MVC

**File `src/main/java/com/example/mapperparity/PurchaseEventController.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/purchases")
public class PurchaseEventController {

    @GetMapping("/sample")
    public PurchaseEvent sample() {
        return new PurchaseEvent(
                "PO-42",
                LocalDate.of(2026, 11, 8),
                null);
    }

    @PostMapping("/echo")
    public PurchaseEvent echo(@RequestBody PurchaseEvent event) {
        return event;
    }
}
```

Controller không nhận `ObjectMapper` trực tiếp. Spring MVC chọn HTTP message converter theo nội dung request/response. Đó là chủ đích: **HTTP test không thể thành công chỉ do test tự tạo mapper**, mà phải đi qua JSON converter đang được application cấu hình.

Endpoint:

- `GET /api/purchases/sample` → object với tên snake_case, ngày ISO và không có property null.
- `POST /api/purchases/echo` với JSON hợp lệ → deserialize thành record rồi serialize lại.
- POST có unknown field → HTTP 400 do converter không thể đọc request body khi bật strict unknown field policy.
- POST dùng camelCase key không được công bố → trong thiết lập strict này, converter từ chối vì unknown property.

Không thêm Bean Validation để tránh nhầm lỗi 400 do validation với lỗi 400 do Jackson deserialization.

### 7.7. JSON slice test — dùng lại configuration production

**File `src/test/java/com/example/mapperparity/PurchaseEventJsonSliceTest.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@JsonTest
@Import(SharedJsonConfiguration.class)
class PurchaseEventJsonSliceTest {

    @Autowired
    JacksonTester<PurchaseEvent> json;

    @Autowired
    ObjectMapper mapper;

    @Test
    void writesConfiguredNamesDatesAndNullInclusion()
            throws Exception {

        PurchaseEvent event = new PurchaseEvent(
                "PO-42", LocalDate.of(2026, 11, 8), null);

        assertThat(json.write(event)).isEqualToJson(
                """
                {
                  "order_id": "PO-42",
                  "purchased_at": "2026-11-08"
                }
                """);

        String encoded = mapper.writeValueAsString(event);
        assertThat(encoded)
                .contains("\"order_id\"")
                .contains("\"purchased_at\"")
                .doesNotContain("\"internal_note\"");
    }

    @Test
    void readsConfiguredSnakeCaseJsonIntoRecord()
            throws Exception {

        String content = """
                {
                  "order_id": "PO-42",
                  "purchased_at": "2026-11-08"
                }
                """;

        PurchaseEvent actual = json.parseObject(content);

        assertThat(actual).isEqualTo(new PurchaseEvent(
                "PO-42", LocalDate.of(2026, 11, 8), null));
    }

    @Test
    void rejectsUnknownJsonField()
            throws Exception {

        String invalid = """
                {
                  "order_id": "PO-42",
                  "purchased_at": "2026-11-08",
                  "unknown_field": "not-in-contract"
                }
                """;

        assertThatThrownBy(() ->
                mapper.readValue(invalid, PurchaseEvent.class))
                .isInstanceOf(UnrecognizedPropertyException.class);
    }

    @Test
    void confirmsEffectiveMapperFeatureConfiguration() {
        assertThat(mapper.getPropertyNamingStrategy())
                .isSameAs(PropertyNamingStrategies.SNAKE_CASE);

        assertThat(mapper.getSerializationConfig()
                .getDefaultPropertyInclusion()
                .getValueInclusion())
                .isEqualTo(JsonInclude.Include.NON_NULL);

        assertThat(mapper.isEnabled(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES))
                .isTrue();

        assertThat(mapper.isEnabled(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS))
                .isFalse();
    }
}
```

**Kỳ vọng:** 4 phương thức `@Test` pass trong Spring Boot 3.x với dependencies như mô tả. `@JsonTest` tạo JSON-focused context và tự cấu hình `JacksonTester`. `@Import(SharedJsonConfiguration.class)` buộc slice áp dụng **đúng customizer bean đã dùng ở production**, không sao chép chính sách mapper vào code test.

Bốn test kiểm tra những hợp đồng độc lập:

- JSON shape của serialization;
- deserialization từ snake_case + ISO date;
- strict unknown-field handling;
- effective mapper settings trong JSON slice.

Chú ý: `@JsonTest` không phải một full MVC test; nó **chưa** chứng minh HTTP converter của controller đang dùng cùng policy. Phần tiếp theo làm điều đó.

### 7.8. Full-context MockMvc test — xác minh actual HTTP converter

**File `src/test/java/com/example/mapperparity/PurchaseEventMvcContractTest.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = MapperParityApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class PurchaseEventMvcContractTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void mvcResponseMatchesConfiguredMapperContract()
            throws Exception {

        MvcResult result = mvc.perform(
                get("/api/purchases/sample")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.order_id").value("PO-42"))
                .andExpect(jsonPath("$.purchased_at")
                        .value("2026-11-08"))
                .andExpect(jsonPath("$.internal_note").doesNotExist())
                .andReturn();

        PurchaseEvent expectedValue = new PurchaseEvent(
                "PO-42", LocalDate.of(2026, 11, 8), null);

        JsonNode expectedFromBean = mapper.valueToTree(expectedValue);
        JsonNode actualFromMvc = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertThat(actualFromMvc).isEqualTo(expectedFromBean);
    }

    @Test
    void mvcRequestAndResponseUseSnakeCaseContract()
            throws Exception {

        mvc.perform(post("/api/purchases/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "order_id": "PO-99",
                          "purchased_at": "2026-11-09"
                        }
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.order_id").value("PO-99"))
                .andExpect(jsonPath("$.purchased_at")
                        .value("2026-11-09"))
                .andExpect(jsonPath("$.internal_note").doesNotExist());
    }

    @Test
    void mvcRejectsUnknownJsonFieldWithBadRequest()
            throws Exception {

        mvc.perform(post("/api/purchases/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "order_id": "PO-42",
                          "purchased_at": "2026-11-08",
                          "unknown_field": true
                        }
                        """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mvcRejectsCamelCaseKeyWhenStrictSnakeCaseIsRequired()
            throws Exception {

        mvc.perform(post("/api/purchases/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "orderId": "PO-42",
                          "purchased_at": "2026-11-08"
                        }
                        """))
                .andExpect(status().isBadRequest());
    }
}
```

**Kỳ vọng:** 4 test pass. Khác với JSON slice:

1. Spring Boot nạp **full application context** từ `MapperParityApplication`; `SharedJsonConfiguration` là bean production được component scan.
2. MockMvc đưa GET/POST request qua Spring MVC và configured HTTP converters.
3. Test kiểm tra JSON **trên response**, không chỉ kết quả trực tiếp của `mapper.writeValueAsString(...)`.
4. Test đọc HTTP response thành `JsonNode` rồi so với `mapper.valueToTree(expectedValue)`. Vì có thêm JSONPath assertions ở HTTP boundary, một converter lỡ dùng camelCase hoặc trả thêm trường null không được âm thầm chấp nhận.
5. POST xác minh chiều **HTTP request deserialization**; hai negative tests chứng minh policy reject unknown/camelCase được converter áp dụng.

**Không nên chỉ giữ assertion `JsonNode expected == actual`.** Vì test dùng mapper bean để đọc response, nếu mapper và converter lệch một cách nào đó nhưng vô tình cùng biểu diễn theo một ngữ nghĩa, bạn cần các JSONPath assertions độc lập để cố định **tên trường bên ngoài**. Bài này có cả hai.

### 7.9. Live HTTP smoke test — JSON đi qua server và socket

**File `src/test/java/com/example/mapperparity/PurchaseEventLiveHttpTest.java`:**

```java
package com.example.mapperparity;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = MapperParityApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class PurchaseEventLiveHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private URI endpoint(String path) {
        return URI.create(
                "http://127.0.0.1:" + port + path);
    }

    @Test
    void actualHttpResponseHasSameJsonFieldContract()
            throws Exception {

        assertThat(port).isGreaterThan(0);

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/purchases/sample"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers()
                .firstValue("Content-Type")
                .orElse(""))
                .contains("application/json");

        JsonNode body = mapper.readTree(response.body());
        assertThat(body.path("order_id").asText())
                .isEqualTo("PO-42");
        assertThat(body.path("purchased_at").asText())
                .isEqualTo("2026-11-08");
        assertThat(body.has("internal_note")).isFalse();
        assertThat(body.has("orderId")).isFalse();
    }

    @Test
    void actualHttpRequestRejectsUnknownField()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/purchases/echo"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        """
                        {
                          "order_id": "PO-42",
                          "purchased_at": "2026-11-08",
                          "unknown_field": "must-reject"
                        }
                        """, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(400);
    }
}
```

**Kỳ vọng:** 2 test pass trên project Spring Boot 3.x Servlet MVC hợp lệ; tổng ví dụ có **10 test: 4 JSON slice, 4 MVC full-context và 2 live HTTP**.

Phần real HTTP xác minh embedded server, client serialization và HTTP response body sau khi đi qua socket. Nó **không chứng minh** proxy/TLS/ingress hay production deployment đang sử dụng đúng config; vì trong ví dụ là `http://127.0.0.1` và test profile của JVM.

### 7.10. Chạy tests từ IDE/Gradle/Maven

Trên Linux/macOS:

```bash
# Gradle — chọn từng lớp:
./gradlew test --tests "com.example.mapperparity.PurchaseEventJsonSliceTest"
./gradlew test --tests "com.example.mapperparity.PurchaseEventMvcContractTest"
./gradlew test --tests "com.example.mapperparity.PurchaseEventLiveHttpTest"

# Hoặc Maven — chọn từng lớp:
./mvnw -Dtest=PurchaseEventJsonSliceTest test
./mvnw -Dtest=PurchaseEventMvcContractTest test
./mvnw -Dtest=PurchaseEventLiveHttpTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.mapperparity.PurchaseEventJsonSliceTest"
.\gradlew.bat test --tests "com.example.mapperparity.PurchaseEventMvcContractTest"
.\gradlew.bat test --tests "com.example.mapperparity.PurchaseEventLiveHttpTest"

# Hoặc Maven:
.\mvnw.cmd "-Dtest=PurchaseEventJsonSliceTest" test
.\mvnw.cmd "-Dtest=PurchaseEventMvcContractTest" test
.\mvnw.cmd "-Dtest=PurchaseEventLiveHttpTest" test
```

Chỉ dùng nhóm lệnh của build tool mà dự án đang dùng. Khi chạy ba lớp bằng ba lệnh riêng, mỗi lần chỉ chạy số test của lớp đó; nếu chạy toàn bộ suite bằng `./gradlew test` hoặc `./mvnw test`, ví dụ đóng góp 10 test bên cạnh những test khác của project.

Không có một dòng stdout cụ thể được source cố ý in ra. JUnit runner, Boot startup và build tool in log/report tùy version; hãy xác nhận **test count, pass/fail/skipped và root cause**. Dùng wrapper để IDE/CI có cùng phiên bản build tool.

### 7.11. Bảng đối chiếu ba boundary

| Hợp đồng | `@JsonTest` | Full-context MockMvc | Real HTTP |
|---|---|---|---|
| Dùng production `SharedJsonConfiguration` | `@Import` tường minh | Component scan của app | Component scan của app |
| Mapper bean viết snake_case | Kiểm tra trực tiếp | Có bean và quan sát response | Quan sát response qua socket |
| Null property bị loại | Assert serialization | JSONPath `doesNotExist()` | Parse body, `has(...) == false` |
| `LocalDate` là ISO string | Assert JSON tester | JSONPath response và POST parsing | GET response |
| Unknown field bị reject | Mapper `UnrecognizedPropertyException` | HTTP 400 sau request-body converter | HTTP 400 qua socket |
| MVC converter thực sự tuân thủ config | Không, slice không có endpoint | **Có** | **Có** |
| TCP/embedded container hoạt động | Không | Không | **Có** |
| Proxy/TLS/production ingress hoạt động | Không | Không | Không, trừ khi test đi qua chính hạ tầng đó |

## 8. Khi @JsonTest khác full application: các nguyên nhân cụ thể

### 8.1. Cấu hình production nằm ngoài phạm vi slice

`@JsonTest` cố ý thu hẹp component scanning. Ví dụ:

```java
@Configuration
class ApplicationJsonConfiguration {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer customize() {
        return builder ->
                builder.propertyNamingStrategy(
                        PropertyNamingStrategies.SNAKE_CASE);
    }
}
```

Đây là **snippet không độc lập**; nó mô tả một production configuration. Nếu test viết:

```java
@JsonTest
class OrderJsonTest {
    @Autowired JacksonTester<Order> json;
}
```

thì **không được mặc định kết luận** `ApplicationJsonConfiguration` đã được scan. Nếu builder customizer là thành phần bắt buộc của contract, có thể thêm `@Import(ApplicationJsonConfiguration.class)` ở test class. Tái sử dụng một cấu hình đang là production source-of-truth, không định nghĩa customizer khác chỉ để pass.

### 8.2. Config theo profile/property bị lệch

Giả sử production:

```properties
spring.jackson.default-property-inclusion=non_null
```

nhưng test:

```java
@JsonTest(properties = 
        "spring.jackson.default-property-inclusion=always")
class ProfileDependentJsonTest {
}
```

Nếu test cố ý override khác production, output lệch là **hành vi đúng theo cấu hình khác**. Đừng gắn nhãn “serialization bug” trước khi so:

- active Spring profiles;
- `application.properties`/`application-test.properties`/config imports;
- annotation `properties` trên `@JsonTest`/`@SpringBootTest`;
- `@TestPropertySource` hoặc `@DynamicPropertySource` nếu có;
- OS env/JVM system props/CLI args của runtime;
- customizer order và conditional bean creation.

Chỉ khi hai bên dùng **cùng yêu cầu hợp đồng** mới nên so đầu ra ngang nhau. Một số test cần profile riêng để cách ly DB/security, nhưng JSON contract thì phải được pin bằng assertions hoặc configuration import sao cho không trôi ngoài ý muốn.

### 8.3. @JsonComponent / Jackson Module có thể được scan khác nhau

Theo Spring Boot 3.x, `@JsonTest` scan hạn chế các thành phần như `@JsonComponent` và `Module` (khi Jackson hiện diện). Nhưng:

- `@Bean Module` được khai báo trong một configuration class không được đưa vào slice có thể vắng.
- Class `@JsonComponent` nằm ngoài package scan root cũng không tự nhiên xuất hiện.
- Auto-configuration/module discovery thay đổi theo Boot/Jackson version.
- Một module custom có serializer override cho DTO sẽ làm kết quả khác mapper chưa đăng ký module.

Nếu cần module production đó, import cấu hình đóng gói module một cách rõ ràng, hoặc dùng full-context test cho hợp đồng. Không clone logic serializer sang test.

### 8.4. Mapper bean có nhiều instance

Một application có thể khai báo:

```java
@Bean
@Primary
ObjectMapper apiMapper() {
    // Custom mapper cho API.
}
```

**Snippet này chỉ mô tả khái niệm, không phải source runnable** (body thiếu return và không phù hợp để copy nguyên). Các vấn đề phải xem:

- `@Primary` ảnh hưởng lựa chọn bean khi inject theo type, không bảo đảm mọi converter/client sử dụng nó.
- Một converter có thể giữ reference tới một mapper tạo riêng.
- Một HTTP client như `RestClient`/`WebClient` có codec/converter config khác.
- Producer của Kafka/Redis hoặc logging có thể dùng mapper khác.
- Thay `ObjectMapper` bean do Boot tạo có thể làm các builder defaults/customizers/modules không được áp dụng như trước.

Để kiểm tra, hãy xác minh mapper/converter trên **đường đi thực**, không chỉ `context.getBean(ObjectMapper.class)`.

## 9. Đo mapper mà MVC converter dùng, khi cần debug sâu

Trong Spring MVC Boot 3.x, có thể kiểm tra message converters được `RequestMappingHandlerAdapter` cấu hình:

```java
@Autowired
RequestMappingHandlerAdapter handlerAdapter;

@Test
void listJacksonMappersForDiagnostics() {
    handlerAdapter.getMessageConverters().stream()
            .filter(MappingJackson2HttpMessageConverter.class::isInstance)
            .map(MappingJackson2HttpMessageConverter.class::cast)
            .forEach(converter -> {
                ObjectMapper used = converter.getObjectMapper();
                assertNotNull(used);
            });
}
```

Đây là **snippet chẩn đoán**, không phải lớp runnable hoàn chỉnh; cần imports tương ứng, test context MVC phù hợp và assertions JUnit. Test chỉ assert non-null ở đây có giá trị hạn chế; để kiểm tra parity thực sự, bạn cần kiểm tra **mapper config hoặc JSON của response**.

Một vài lưu ý chuyên sâu:

1. Trong app có nhiều converter Jackson, `getMessageConverters()` có thể trả nhiều converter phục vụ media type khác nhau. Đừng mặc định “converter đầu tiên chính là converter cho mọi response”.
2. Jackson converter có thể có cấu hình riêng cho từng Java type/media type, tùy Spring Framework version.
3. `ObjectMapper` converter và injected bean có thể khác reference nhưng giống behavior. So sánh `==` không thay cho API-contract assertion.
4. Trên WebFlux, JSON encoding/decoding dùng reactive `Encoder/Decoder` và codec configuration; đừng tìm `RequestMappingHandlerAdapter` của MVC như giải pháp chung.
5. Khi có custom `@JsonView`, serializer xử lý view có thể tạo output khác `mapper.writeValueAsString(value)` mà đó lại là behavior đúng.

Trong sản phẩm thật, tốt nhất giữ một số tests **black-box** có JSONPath/JSON body assertions, còn code introspection mapper chỉ sử dụng khi truy nguyên drift.

## 10. Vì sao không nên tự thay ObjectMapper bean chỉ để sửa test?

Một phản ứng phổ biến với lỗi JSON slice là thêm:

```java
@TestConfiguration
class ExtraTestConfig {
    @Bean
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
```

Đây là **phản mẫu** cho mục tiêu parity; thiếu các imports và chỉ minh họa điều không nên làm. Cách này có thể khiến test khởi động, nhưng mapper mới không nhất thiết có modules, naming strategy hoặc serialization config từ production.

Một phản mẫu khác là dùng spy/mock `ObjectMapper` rồi stub `writeValueAsString(...)` bằng JSON hardcode: test lúc đó không kiểm tra Jackson thực, mà chỉ kiểm tra stub của chính mình.

Khi một bean JSON thiếu trong `@JsonTest`, hãy phân biệt:

- Bean là Jackson `Module` hoặc `@JsonComponent`? Xác nhận scanner/package/module registration.
- Bean là `Jackson2ObjectMapperBuilderCustomizer` trong configuration class? Dùng `@Import` source-of-truth.
- Bean phụ thuộc DB/service khác không cần cho JSON? Tách cấu hình mapper khỏi business infrastructure.
- Bạn chỉ muốn test DTO? Dùng mapper đúng contract, không lôi full context vào nếu không cần.
- Bạn cần chứng minh converter application? Dùng full-context MockMvc hoặc live HTTP.

### 10.1. Customizer và @Bean ObjectMapper không giống nhau

Trong Boot 3.x, auto-config thường tạo `ObjectMapper` từ builder do Boot tùy biến. Một `Jackson2ObjectMapperBuilderCustomizer` tham gia bước build, còn một `@Bean ObjectMapper` do người dùng tự khai báo có thể làm Boot **back off** khỏi việc tạo mapper mặc định.

Nếu tự tạo mapper, bạn nhận trách nhiệm:

- đăng ký modules cần thiết;
- giữ những defaults về date/time, unknown fields, naming;
- có thread-safe lifecycle/cấu hình trước khi dùng;
- bảo đảm converters/clients nhận đúng mapper;
- xử lý custom serialization và tests tương ứng.

Nếu chỉ muốn thay một vài quy tắc, sử dụng properties hoặc builder customizer thường ít rủi ro hơn.

## 11. Date/time: loại dữ liệu và múi giờ làm lệch JSON như thế nào?

### 11.1. LocalDate không phải Instant

Trong ví dụ, `LocalDate.of(2026,11,8)` là một **ngày không có giờ hoặc timezone**. JSON đúng là `"2026-11-08"` khi Jackson Java Time module và date configuration được thiết lập như sample.

Không lấy property timezone `spring.jackson.time-zone=Asia/Ho_Chi_Minh` rồi khẳng định `LocalDate` phải đổi thành ngày khác. `LocalDate` không mang offset hay instant để chuyển múi giờ theo cách `Date`/`Instant` có thể cần khi biểu diễn.

### 11.2. Instant và OffsetDateTime là hợp đồng khác

Với các loại như `Instant`, `OffsetDateTime` hoặc `ZonedDateTime`:

- phải thống nhất API format, UTC/offset và độ chính xác fractional seconds;
- phân biệt serialization dùng timezone/format cụ thể với giá trị thời gian thực;
- tránh test dựa vào system default timezone của developer/CI;
- dùng test values cố định, không `LocalDateTime.now()`/`Instant.now()` nếu expected JSON chính xác;
- kiểm tra Jackson modules và `@JsonFormat` có ghi đè rule chung hay không.

Ví dụ chỉ định theo domain: thời điểm giao dịch có thể chuẩn hóa UTC; lịch sinh nhật nên là `LocalDate`. Không thay loại Java time chỉ để làm test string match.

### 11.3. Null, missing, empty string là ba trạng thái

- `"internal_note": null`: trường **có mặt** với JSON null.
- Không có `internal_note`: trường **vắng mặt**.
- `"internal_note": ""`: trường có chuỗi rỗng.

Global `NON_NULL` thường bỏ null khi **serialize**; nó không mặc nhiên bỏ string rỗng, collection rỗng hoặc đổi behavior của deserialization. Test nên dùng `JsonNode.has(...)`/JSONPath để phân biệt rõ “vắng mặt” với “có key nhưng value null”.

### 11.4. Không ép JSON field order nếu không là contract

Hai JSON objects có cùng key/value nhưng thứ tự khác nhau vẫn biểu diễn cùng cấu trúc JSON. `JacksonTester.isEqualToJson(...)` hoặc so `JsonNode` thường phù hợp hơn so sánh một chuỗi JSON nguyên văn khi thứ tự field không là hợp đồng.

Nếu hệ thống ký payload theo byte sequence hoặc có canonical JSON spec, đó là hợp đồng khác: cần serializer/canonicalization cụ thể và test chính xác bytes, không suy ra từ JSON structural equality.

## 12. Unknown fields và backwards compatibility

### 12.1. Vì sao sample bật strict unknown fields?

Spring Boot 3/Jackson 2 có một số defaults được Boot điều chỉnh, trong đó có việc tắt `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` ở nhiều setup mặc định. Sample **chủ động bật** feature này để phát hiện JSON clients gửi key khác contract.

Nếu client gửi:

```json
{
  "order_id": "PO-42",
  "purchased_at": "2026-11-08",
  "unrecognized_key": 5
}
```

Jackson 2 `ObjectMapper` với strict mode sẽ reject unknown key; qua Spring MVC request converter, lỗi thường được quy thành `HttpMessageNotReadableException` và HTTP 400.

### 12.2. Strict không phải luôn là lựa chọn tốt nhất

Nếu API cho phép client gửi trường mới mà server cũ chưa biết, bỏ qua unknown fields có thể tăng tính tương thích. Nếu API là internal command nghiêm ngặt, strict mode có thể giúp phát hiện sai schema sớm.

**Hãy chọn chính sách bằng hợp đồng:** test đúng không phải test theo behavior mặc định của một phiên bản Jackson bất kỳ, mà theo chính sách API đã công bố và áp dụng nhất quán.

### 12.3. Lỗi 400 còn có nhiều nguồn

Một POST có thể trả 400 do:

- Jackson không parse được JSON syntax;
- JSON có field type sai;
- unknown field theo strict config;
- thiếu required creator property theo rule;
- Bean Validation `@Valid`/constraints;
- controller advice xử lý lỗi domain thành 400.

Khi debug, kiểm tra resolved exception/matched handler, đừng mặc định thấy 400 nghĩa là strict unknown property đã chạy. Mã sample không dùng `@Valid` để tách nguyên nhân cho rõ.

## 13. Multi-profile và test context cache

### 13.1. Test có thật sự dùng cùng cấu hình không?

Nếu production có profile `prod` với Jackson bean bổ sung, nhưng test có `@ActiveProfiles("test")` và những bean ấy bị `@Profile("prod")` loại, hai mapper không thể đồng nhất.

Nhiều ứng dụng **cố ý** không bật production profile trong test để tránh DB/external connections. Khi đó cần:

1. Đưa JSON contract configuration **độc lập với environment** nếu có thể.
2. Nếu config buộc profile-specific, xác định hợp đồng JSON cho từng profile và test riêng.
3. Không chạy test với secrets hoặc kết nối production chỉ vì muốn “mapper giống production”.
4. Dùng profile test nhưng **import/enable cùng JSON contract source-of-truth**.
5. Gắn regression tests tại HTTP boundary để phát hiện cấu hình thêm bởi full context.

### 13.2. Cache key và test state

Spring TestContext cache application contexts để giảm startup. Các cấu hình test (profiles, properties, imports, mock overrides) góp phần tạo context cache key.

Nếu một test gọi:

```java
mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.LOWER_CAMEL_CASE);
```

trên injected singleton mapper sau khi context đã chạy, bạn đã làm thay đổi **shared mutable config** của mapper, ảnh hưởng test khác hoặc converters đã được tạo. Đây là **phản mẫu**; Jackson 2 khuyến cáo cấu hình mapper **trước khi dùng** và sử dụng `ObjectReader/ObjectWriter` cho biến thể theo request.

Không sửa production mapper singleton trong `@BeforeEach` để tạo scenario; dùng annotation test config/beans riêng, `mapper.copy()` trong unit test khi phù hợp, hoặc tạo context khác cho cấu hình cần thử. Khi muốn test thay đổi runtime config, phải hiểu bean/converter lifecycle và concurrency thật.

### 13.3. @DirtiesContext không thay cho thiết kế

`@DirtiesContext` có thể loại context khỏi cache khi state thực sự bị làm bẩn, nhưng làm suite chậm và không giải quyết ý định cấu hình. Tốt hơn là giữ mapper immutable về mặt sử dụng, test classes độc lập theo contract và cấu hình nguồn duy nhất.

## 14. Jackson modules, Mixins và custom serializers: kiểm tra đường đăng ký

### 14.1. Cấu hình từ @JsonComponent

Một serializer riêng cho tiền tệ, enum hay value object có thể được khai báo `@JsonComponent` trong Boot 3.x. Nếu JSON slice scan được class ấy và full context cũng scan, behavior có thể giống nhau.

Nhưng nếu `@JsonComponent` nằm ngoài package root, hoặc bị loại theo filter, test slice có thể không thấy. Khi đó:

- kiểm tra package scanning, include filters/import;
- kiểm tra serializer/deserializer class đúng type;
- kiểm tra module/converter có override serializer không;
- thêm contract test cho type cụ thể.

Không chỉ assert bean tồn tại; hãy serialize một giá trị chứng minh serializer thật đã được dùng.

### 14.2. @JsonMixin ảnh hưởng annotation mà DTO không thấy

Mixin có thể thêm `@JsonIgnore`, `@JsonProperty` hoặc định dạng cho third-party class không sửa được source. Một test DTO viết bằng mapper mới không biết mixin thường cho output khác production.

Để kiểm tra parity, bảo đảm mixin registration được đưa vào test slice theo đúng cơ chế Boot, và có full-context HTTP test cho endpoint cần serializer này. Hãy chú ý annotation của Boot 3.x là `@JsonMixin` (khác với Boot 4 `@JacksonMixin`).

### 14.3. Module từ thư viện ngoài

Khi thêm thư viện hỗ trợ một type mới, mapper có thể cần module riêng. Đừng phỏng đoán `findAndRegisterModules()` chạy ở mọi phiên bản Boot theo cùng logic: Spring Boot 3 và Boot 4 có chính sách module discovery khác nhau.

Nếu module là part of API contract, test một giá trị thuộc type đó và xác nhận both read/write. Các lỗi khó chịu đôi khi chỉ xuất hiện ở **deserialization** dù serialization pass.

### 14.4. Nếu mapper dùng trong RestClient/WebClient khác MVC

Một ứng dụng vừa là HTTP server vừa là HTTP client có thể dùng:

- Spring MVC `MappingJackson2HttpMessageConverter`;
- `RestClient`/`RestTemplate` converters;
- WebFlux `Jackson2JsonEncoder`/`Jackson2JsonDecoder` hoặc codecs khác;
- message broker serializers;
- custom ObjectMapper trong business library.

Chúng không tự động đều sử dụng cùng bean mapper. Test từng **boundary cần đảm bảo**: server response, request to remote service, message payload hoặc cache representation. Một JSON slice pass chứng minh DTO contract theo test mapper; nó không thay thế outbound HTTP client test.

## 15. Spring Boot 3.x sang 4.x: đổi từ Jackson 2 sang Jackson 3

Đây là thay đổi lớn, **không chỉ đổi import của một annotation**.

| Chủ đề | Spring Boot 3.x / Jackson 2 | Spring Boot 4.x / Jackson 3 mặc định |
|---|---|---|
| Mapper phổ biến | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.json.JsonMapper` |
| Builder customizer | `Jackson2ObjectMapperBuilderCustomizer` | `JsonMapperBuilderCustomizer` |
| Customizer package ví dụ | `org.springframework.boot.autoconfigure.jackson` | `org.springframework.boot.jackson.autoconfigure` |
| JSON component | `@JsonComponent` | `@JacksonComponent` |
| Mixin annotation | `@JsonMixin` | `@JacksonMixin` |
| Jackson modules | Jackson 2 `Module` | Jackson 3 `JacksonModule` |
| Naming/date/property options | `spring.jackson.*` theo Boot 3 | `spring.jackson.*` cho Jackson 3, thay đổi một số tên nhóm/feature |
| Jackson 2 tương thích | Là stack mặc định của Boot 3 | Boot 4 có module hỗ trợ Jackson 2 **deprecated**, không nên coi là giải pháp dài hạn |
| JSON test | `@JsonTest` và `JacksonTester` của Jackson 2 | `@JsonTest` và test support của Jackson 3 (API tương ứng version) |

Spring Boot 4.0 migration guide ghi rõ `Jackson 3` là thư viện JSON ưu tiên và mặc định. Những package thuộc Jackson databind/core chuyển từ `com.fasterxml.jackson...` sang `tools.jackson...` (annotation package là một ngoại lệ quan trọng). Với Jackson 3, mapper định hướng JSON là `JsonMapper`; Boot có `JsonMapperBuilderCustomizer`.

**Không copy** class `SharedJsonConfiguration` của phần 7 vào Boot 4 mà chỉ sửa dependency. Phải viết customizer theo API Jackson 3, điều chỉnh imports, modules, properties và mapping tests theo nhánh Boot 4 đang dùng.

### 15.1. Mapper bean trong Boot 4 có contract khác

Với Boot 4/Jackson 3:

- `JsonMapper` được auto-configure cho JSON.
- `@JacksonComponent`, `@JacksonMixin` và Jackson 3 modules là những extension points tương ứng.
- Việc định nghĩa một `ObjectMapper` bean **không còn là cách mặc định để thay mapper JSON**; migration guide hướng dẫn cung cấp `JsonMapper` bean nếu muốn thay JSON mapper.
- `JsonMapperBuilderCustomizer` can thiệp builder của mapper do Boot auto-configure, tương tự mục đích nhưng không cùng type/API với Boot 3.
- Jackson 3 mặc định có một số behavior khác Jackson 2; vì vậy phải giữ **contract assertions ở HTTP boundary**, không chỉ rely vào migration compile.

### 15.2. Jackson 2 compatibility trên Boot 4

Spring Boot 4 có hỗ trợ Jackson 2 deprecated để chuyển đổi dần. Các properties tương ứng có prefix `spring.jackson2.*`, còn `spring.jackson.*` là cho Jackson 3 trong những mục đích liên quan. Khi cả hai mapper coexist, MVC/WebFlux/client có thể chọn mapper ưu tiên qua properties tương ứng như `spring.http.converters.preferred-json-mapper`.

Vì vậy một test `@Autowired ObjectMapper` Jackson 2 có thể pass trong Boot 4, nhưng **MVC endpoint thực tế lại dùng Jackson 3 JsonMapper**. Đây chính là dạng parity bug phải phòng ngừa.

**Không thiết kế mã sample Boot 3/Jackson 2 rồi mặc định test đó chứng minh ứng dụng Boot 4/Jackson 3.** Hãy cập nhật code và chạy contract tests trên stack đang deploy.

### 15.3. Kiểm tra đúng tài liệu phiên bản

- Spring Boot 3.5: docs JSON, @JsonTest, Jackson2ObjectMapperBuilderCustomizer và MVC converters.
- Spring Boot 4.x: JSON docs Jackson 3, JsonMapperBuilderCustomizer, migration guide và @JsonTest tương ứng.
- Với dự án dùng custom framework platform/BOM, phải xác nhận resolved dependency thực tế (đặc biệt Jackson 2 và 3 cùng tồn tại).

Đừng sửa test để “phù hợp snapshot” khi upgrade làm thay contract ngoài ý muốn; nếu cần giữ API backward compatibility, thêm regressions và nâng library/config một cách có chủ đích.

## 16. Debug khi JSON slice pass nhưng HTTP integration fail

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `@JsonTest` xuất `orderId`, HTTP xuất `order_id` | Slice không import production naming customizer | Reuse `@Import(SharedJsonConfiguration.class)` hoặc config cơ chế tương đương |
| `new ObjectMapper()` không serialize được LocalDate | Thiếu JavaTimeModule/Boot defaults | Inject đúng Boot mapper hoặc tạo mapper đầy đủ nếu unit test thực sự cần |
| Test bỏ null nhưng HTTP vẫn có null | Converter/mapper HTTP có include policy khác | Xem MVC converter, JSONPath và full-context config |
| Test chấp nhận unknown field nhưng HTTP 400 | Strict deserialization chỉ bật trong app | So `FAIL_ON_UNKNOWN_PROPERTIES` và config sources |
| JSON slice chỉ fail trên CI | Profiles, dependencies, locale/timezone hoặc test runner khác | Chạy wrapper; xác minh resolved BOM và active profiles |
| @JsonTest fail vì thiếu bean service | Slice không nạp regular service bean | Tách config JSON, import đúng class nhỏ; không kéo cả service graph |
| `@Import` làm JSON slice nạp database | Imported config chứa quá nhiều production infrastructure | Tách JSON-only configuration khỏi DB/service configs |
| HTTP body được ghi kiểu date array/timestamp | `WRITE_DATES_AS_TIMESTAMPS` hoặc Java time module khác | Kiểm tra mapper feature trên runtime và response thật |
| Field `@JsonProperty` không theo naming strategy | Annotation explicit đang override | Test property-level contract, không kết luận global config lỗi |
| HTTP content type không phải JSON | `Accept`/`Content-Type`, converter selection hoặc return type khác | Gửi media type đúng, kiểm tra response và converters |
| HTTP 400 do malformed JSON chứ không unknown | Request syntax sai hoặc DTO creator type mismatch | Inspect resolved exception và root cause trong test |
| Injected ObjectMapper đúng nhưng HTTP JSON sai | Custom `MappingJackson2HttpMessageConverter` dùng mapper khác | Assert HTTP response và inspect converters theo media type |
| Mapper bean mutate khiến suite flaky | Shared singleton config bị sửa sau khi dùng/context cache | Không mutate; cấu hình trước startup, isolate tests |
| Boot 4 vẫn inject ObjectMapper nhưng API JSON dùng JsonMapper | Jackson 3 đã trở thành mặc định; hai stack coexist | Kiểm tra preferred mapper và HTTP contract; không chỉ test Jackson2 |
| `@JsonTest` fail với custom Module | Module không có trong slice hoặc version incompatible | Kiểm tra bean/module registration và classpath |
| MockMvc pass nhưng live HTTP fail | Server, port, encoding, filter, proxy hoặc khác profile | Xác định boundary thực, thêm live HTTP/infra tests |
| Golden JSON quá chặt về thứ tự | So JSON raw string khi order không thuộc contract | Dùng JsonContent/JsonNode để so cấu trúc |

### 16.1. Checklist truy nguyên theo thứ tự

1. **Xác nhận phiên bản:** Boot major/minor, Jackson 2 hay 3, Spring Framework, Java toolchain.
2. **Xác nhận test đang dùng mapper nào:** new instance, `@JsonTest` bean hay full-context bean.
3. **Xác nhận properties/profiles:** `spring.jackson.*` và những test overrides đang có hiệu lực.
4. **Xác nhận customizers/modules:** có được đăng ký trong slice không? Trong full context không?
5. **Xác nhận DTO annotations:** `@JsonProperty`, `@JsonFormat`, `@JsonInclude`, `@JsonView`, mixins.
6. **Xác nhận converter/codec:** actual HTTP endpoint dùng Jackson, Gson, JSON-B hay custom mapper?
7. **So behavior:** stringify một DTO cố định, parse một JSON cố định, gửi HTTP GET/POST qua MockMvc.
8. **Nếu cần network:** gửi HTTP tới `RANDOM_PORT` và assert body sau encoding.
9. **Xác nhận error path:** unknown fields, malformed JSON, conversion errors và expected HTTP status.
10. **Chạy lại CI command:** dùng wrapper, kiểm tra test report và classpath dependency resolution.

### 16.2. Logging và bảo mật

Không in toàn bộ request/response body của production data vào test logs khi có thông tin nhạy cảm. JSON contract tests nên dùng fixture giả, ví dụ mã `PO-42` và ngày cố định. Tránh golden file chứa access token, PII hoặc production payload thật.

Khi inspect bean/converters, chỉ in type/names/features cần debug; không dump toàn bộ environment. Khi API dùng custom masking, cũng phải có test bảo đảm trường sensitive không vô tình xuất hiện trong JSON.

## 17. Bài tập củng cố

### Bài tập A — Phát hiện mapper lệch

Application dùng `spring.jackson.property-naming-strategy=SNAKE_CASE`, test tự tạo `new ObjectMapper()` và mong `"orderId"`. Test xanh có chứng minh API đúng không?

**Đáp án:** không. Test chỉ kiểm tra mapper mới chưa áp dụng Spring Boot config. Dùng `@JsonTest` với config giống app, sau đó kiểm tra HTTP JSON qua MockMvc/full context.

### Bài tập B — JSON slice không có customizer

Production định nghĩa `@Bean Jackson2ObjectMapperBuilderCustomizer` trong `@Configuration` thường; `@JsonTest` trả camelCase. Nên sửa thế nào?

**Đáp án:** xác định class config/bean module được nạp trong production, đưa nó vào slice một cách có chủ đích bằng `@Import(SharedJsonConfiguration.class)` hoặc thiết kế cấu hình JSON độc lập có thể reuse. Không sao chép customizer sang một `@TestConfiguration` khác vì hai bản sẽ drift.

### Bài tập C — Mapper bean giống nhau nhưng converter khác

Test inject `ObjectMapper mapper` và serialize event đúng snake_case; HTTP trả camelCase. Nên tin kết quả nào khi đánh giá API contract?

**Đáp án:** kết quả HTTP là điều client nhìn thấy. Điều tra custom `MappingJackson2HttpMessageConverter` hoặc converter/mapper selection, sửa cấu hình application rồi giữ regression test HTTP. Chỉ so mapper bean không đủ.

### Bài tập D — Null và missing

Client contract quy định không có trường `internal_note` nếu null. Test nên assert `jsonPath("$.internal_note").value(null)` hay `doesNotExist()`?

**Đáp án:** dùng `doesNotExist()` cùng kiểm tra JSON structure/JsonNode khi muốn chứng minh **key vắng mặt**. “Có field với giá trị null” và “không có field” không giống nhau. Với Spring MVC, JSONPath có các matcher cho null và missing cần chọn đúng mục tiêu.

### Bài tập E — Nâng cấp Boot 4

Dự án migrate từ Boot 3 sang 4, test vẫn inject `com.fasterxml.jackson.databind.ObjectMapper` và pass, nhưng production response lệch. Tại sao?

**Đáp án:** Boot 4 dùng Jackson 3 `tools.jackson.databind.json.JsonMapper` mặc định; Jackson 2 có thể coexist qua compatibility module. Test Jackson2 mapper không chứng minh HTTP converter dùng Jackson2. Cần migrate customizers/beans/modules và giữ HTTP response contract tests theo mapper thực tế.

### Bài tập F — LocalDate và timezone

Một test cố ép `LocalDate.of(2026,11,8)` thành ngày 2026-11-07 chỉ vì set timezone khác. Nhận định đó có đúng mặc định không?

**Đáp án:** không. `LocalDate` không có thời điểm/múi giờ; cách biểu diễn theo ISO local date không phải một phép chuyển UTC offset. Khi cần instant/timezone conversion, phải chọn domain type như `Instant`/`OffsetDateTime` và policy format tương ứng.

### Bài tập G — Không được dựa vào JSON text order

Một test fail vì response có keys đúng nhưng thứ tự đổi. Cần sửa business code để giữ property order không?

**Đáp án:** chỉ khi property order là hợp đồng thật (rất hiếm với JSON API thông thường). Thường dùng JSON structural comparison/JSONPath hoặc JsonNode; tách yêu cầu canonical JSON riêng nếu ký payload dựa trên bytes.

### Bài tập H — Unknown fields strict hay lenient?

Một public API yêu cầu forward compatibility với clients gửi thêm metadata; đội test bật `FAIL_ON_UNKNOWN_PROPERTIES` chỉ vì thấy dễ phát hiện lỗi. Có nên không?

**Đáp án:** tùy API contract. Strict mode có thể phá compatibility; nếu yêu cầu API cho phép unknown metadata thì phải kiểm tra accept/ignore đúng chính sách. Bài sample bật strict để minh họa drift, không coi strict là mặc định tốt cho mọi dịch vụ.

## 18. Checklist trước khi kết luận test JSON parity đạt

- [ ] Đã biết app dùng Jackson 2/Jackson 3, Gson hay JSON-B và resolved dependency thực.
- [ ] Đã xác định mapper **thật** của HTTP converter/codec cần test.
- [ ] Không coi `new ObjectMapper()` là cùng config với Boot bean khi chưa chứng minh.
- [ ] `@JsonTest` có nạp đúng production customizers/modules/mixins cần thiết.
- [ ] Dùng `@Import` source-of-truth thay vì copy mapper configuration cho test.
- [ ] Test cả serialization lẫn deserialization, không chỉ một chiều.
- [ ] Có assertion về naming strategy của API: camelCase/snake_case hoặc explicit names.
- [ ] Có assertion null vs missing, không nhầm với empty string.
- [ ] Có assertion về Java time, format/offset/timezone theo đúng domain type.
- [ ] Có assertion khi unknown fields, malformed JSON hoặc wrong type theo contract.
- [ ] Full-context MVC test kiểm tra JSON response/request thật qua converter.
- [ ] Nếu ứng dụng có nhiều converters, không suy luận từ một injected mapper rằng tất cả endpoints dùng nó.
- [ ] Profiles, application properties và customizer ordering không làm test drift.
- [ ] Không sửa shared mapper singleton sau khi context đã dùng.
- [ ] Không dùng `@DirtiesContext` để che mutation state.
- [ ] Không thay ObjectMapper bean bằng một instance đơn giản chỉ để test khởi động.
- [ ] Khi lên Boot 4, kiểm tra Jackson 3 JsonMapper, `@JacksonComponent`, `JsonMapperBuilderCustomizer` và preferred JSON mapper của HTTP.
- [ ] Khi cần real HTTP contract, có test `RANDOM_PORT`/client qua socket; không tự gán nhãn e2e cho localhost test.
- [ ] Fixtures dùng ngày, tên và dữ liệu giả cố định, không lộ secrets.
- [ ] Test được thực thi thực sự từ IDE/Gradle/Maven/CI và có báo cáo số lượng.
- [ ] Golden JSON assertions đo JSON structure, không phụ thuộc field order nếu không cần.

## 19. Kết luận

**Mapper parity là hợp đồng giữa cấu hình serialization/deserialization mà test kiểm tra và cấu hình thực sự tạo JSON ở boundary của ứng dụng.** Một `@JsonTest` dùng đúng production customizers giúp bắt lỗi JSON nhanh và cô lập; nhưng để xác minh HTTP API contract, hãy bổ sung `@SpringBootTest + @AutoConfigureMockMvc` hoặc real HTTP test theo rủi ro.

Một thiết kế vững chắc có ba đặc tính: **cấu hình JSON có nguồn duy nhất**, **assertions cố định public contract (field names, null, temporal values, errors)** và **kiểm chứng ở đúng mapper/converter thực tế**. Khi nâng cấp Boot/Jackson hay thay modules, những tests này giúp phân biệt thay đổi hợp lệ với drift có thể phá clients.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JsonTest`, `JacksonTester`, slice vs full context, MVC tests.
- [Spring Boot 3.5 — JsonTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html): phạm vi quét `@JsonComponent`/`Module` và test properties.
- [Spring Boot 3.5 — Jackson2ObjectMapperBuilderCustomizer Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html): tác dụng của builder customizer.
- [Spring Boot 3.5 — JSON Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jackson.*` và các feature toggles.
- [Spring Boot 3.x — Customize the Jackson ObjectMapper](https://docs.spring.io/spring-boot/3.4/how-to/spring-mvc.html): MVC HttpMessageConverters, ObjectMapper bean và builder configuration.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): cách MVC chọn converter đọc/ghi payload.
- [Spring Boot 4 — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3 `JsonMapper`, Jackson 2 compatibility, modules/mixins và preferred mapper.
- [Spring Boot 4.0 Migration Guide — Upgrading Jackson](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi packages, builders, components và format-specific mappers.
- [Spring Boot 4 — JsonMapperBuilderCustomizer Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/jackson/autoconfigure/JsonMapperBuilderCustomizer.html): customizer trên Jackson 3.
- [Spring Boot 4 — JsonTest Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html): phạm vi JSON slice mới.
