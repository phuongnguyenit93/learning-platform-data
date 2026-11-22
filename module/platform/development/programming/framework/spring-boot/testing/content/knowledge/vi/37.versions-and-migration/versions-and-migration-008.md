# Thay đổi Jackson, JSON tester và dependency serialization

## 1. Vì sao chủ đề này quan trọng khi nâng Spring Boot?

Một service Spring Boot có thể khởi động thành công, chạy toàn bộ unit tests và vẫn làm hỏng client sau khi nâng Jackson hoặc thay dependency serialization. Hai JSON đều hợp lệ về cú pháp nhưng có thể không cùng hợp đồng:

**Trước khi nâng cấp:**

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "PAID"
}
~~~

**Sau khi cấu hình serializer vô tình thay đổi:**

~~~json
{
  "invoiceId": "INV-7",
  "issuedAt": 1767323045,
  "amount": {"cents": 1999},
  "state": "PAID",
  "memo": null
}
~~~

Khác biệt nằm ở tên field, dạng thời gian, kiểu dữ liệu money và chính sách xuất null. Một consumer cũ có thể báo lỗi ngay, hoặc nguy hiểm hơn, đọc sai giá trị rồi tiếp tục xử lý.

Bài thuộc nhóm **Phiên bản và chuyển đổi** của module **Spring Boot - testing**, đúng đề bài **Thay đổi Jackson, JSON tester và dependency serialization**.

Mục tiêu học tập:

1. Hiểu sự khác biệt giữa Jackson library, Spring Boot auto-configuration và MVC HTTP message converters.
2. Phân biệt Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`) với Jackson 3 (`tools.jackson.databind.json.JsonMapper`).
3. Biết Spring Boot 3.x dùng Jackson 2, còn Spring Boot 4.0 ưu tiên Jackson 3 và có Jackson 2 bridge tạm thời.
4. Dùng dependencyInsight để tìm version Jackson được giải quyết thật, tránh lệch Jackson core/databind/modules.
5. Dùng `@JsonTest`, `JacksonTester`, `JsonContent`, JSONPath, AssertJ và golden fixtures để bảo vệ JSON contract.
6. Kiểm custom `@JsonComponent` serializer/deserializer trong Spring Boot 3.3.5, và hiểu chuyển sang `@JacksonComponent` khi nâng Boot 4.
7. Phân biệt mapper do Boot inject với `new ObjectMapper()` tự tạo.
8. Bắt regression về snake_case, nullability, enum, numeric coercion, Java Time, timezone và trường bổ sung.
9. Chạy thử legacy consumer tolerant/strict với JSON candidate, không chỉ dùng round-trip của DTO mới.
10. Kiểm Spring MVC JSON thật bằng `@WebMvcTest` và wiring bằng `@SpringBootTest`.
11. Dựng project **Java 17, Spring Boot 3.3.5, Gradle 8.8, JUnit Jupiter**, có fixture và mã đầy đủ.
12. Có phương án nâng cấp Jackson 3, CI contract gate, xử lý dependency conflict và rollback.

**Tư duy chính:** “Compile được” không đồng nghĩa “JSON tương thích”. Một object Java đúng kiểu vẫn có thể chứa giá trị sai theo contract: cents đổi sang dollars, thời gian sai múi giờ hoặc enum mới không được client cũ hỗ trợ.

## 2. Ba lớp serialization thường bị nhầm

~~~text
Spring MVC Controller / RestClient / messaging producer
                       |
                       v
Spring HTTP MessageConverter / codec / serializer adapter
                       |
                       v
Spring Boot auto-configured JSON mapper
                       |
           +-----------+-----------+
           |           |           |
       Jackson     custom modules  settings
       library     serializers     profiles
           |
           v
       JSON wire bytes
           |
           v
Legacy client / new client / schema validator
~~~

Một test `new ObjectMapper().writeValueAsString(dto)` chỉ kiểm **mapper tự tạo**. Nó không tự chứng minh Spring Boot app dùng mapper ấy qua HTTP, và có thể bỏ sót module Java Time, @JsonComponent và config properties.

Một `@JsonTest` dùng mapper trong **JSON test slice**, còn `@WebMvcTest` kiểm JSON được tạo qua **Spring MVC converter**. `@SpringBootTest` giúp kiểm full application wiring khi custom configs/beans tác động lên mapper. Nếu client dùng một mapper khác, phải có test phía client.

## 3. Bản đồ phiên bản và API

| Nhánh | Mapper điển hình | JSON test support | Điểm cần chú ý |
| --- | --- | --- | --- |
| Boot 3.3.x | Jackson 2 `ObjectMapper` | `@JsonTest`, `JacksonTester` | `@JsonComponent`, JavaTimeModule, Boot BOM |
| Boot 3.4/3.5 | Jackson 2 `ObjectMapper` | `JacksonTester` | Jackson minor/Boot defaults có thể đổi |
| Boot 4.0 | Jackson 3 `JsonMapper` | `JacksonTester` cho Jackson 3 | New group/packages, @JacksonComponent, module discovery |
| Boot 4.0 bridge | Jackson 2 `ObjectMapper` phụ trợ | `Jackson2Tester` cho bridge | Deprecated, cần migration plan |

Dòng support cụ thể thay đổi theo thời điểm. Các versions trong lab là một **mốc kỹ thuật có chủ đích**, không phải lời khẳng định rằng chúng vẫn đang nhận security patches trong production.

### 3.1. Spring Boot 3.x / Jackson 2

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.JsonDeserializer;
~~~

Spring Boot 3.3.5 quản lý Jackson qua dependency BOM. Với `spring-boot-starter-web`, JSON mapper thường được cấu hình sẵn và tích hợp vào Spring MVC.

### 3.2. Spring Boot 4.0 / Jackson 3

~~~java
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.JsonNode;
~~~

Jackson 3 chuyển phần lớn group IDs và Java packages từ `com.fasterxml.jackson` sang `tools.jackson`. **Ngoại lệ quan trọng:** Jackson annotations vẫn nằm trong `com.fasterxml.jackson.annotation` và artifact annotations tiếp tục thuộc `com.fasterxml.jackson.core`, theo Spring Boot 4.0 Migration Guide. Vì vậy không chạy một replace-all tự động cho mọi import.

### 3.3. Mapper mới không tương đương mapper cũ

Một custom `ObjectMapper` bean mà ứng dụng Boot 3 dùng để thay JSON behavior **không tự thay thế** `JsonMapper` Jackson 3 do Boot 4 cấu hình. Nếu cả hai major tồn tại, application có thể có hai mapper với các converters/clients chọn khác nhau. Cần kiểm thực tế mapper nào tạo response.

## 4. Dependency serialization là một phần của hợp đồng

Những modules phổ biến trong JSON stack:

| Dependency | Vai trò |
| --- | --- |
| Jackson core | Streaming parser/generator |
| Jackson databind | Mapping Java objects và JSON tree |
| Jackson annotations | Property naming, include/ignore, format, subtype hints |
| JSR310/JavaTime module (Jackson 2) | Instant, LocalDate, OffsetDateTime |
| JDK8 module | Optional và Java 8 types |
| ParameterNames module | Constructor parameter names khi cần |
| Kotlin module | Kotlin data classes, nullability behavior |
| Jackson XML module | XML mapper, nếu app dùng XML |
| Jackson YAML/CBOR/Smile | Những wire formats khác |
| Spring Boot starters/BOM | Resolved versions và auto-configuration |
| Spring Boot test dependencies | JSON testers, JUnit, AssertJ, JsonPath/JSONAssert |

Một SDK thêm transitive Jackson dependency khác có thể kéo `jackson-databind`, `jackson-core`, datatype modules lệch nhau. Trường hợp này có thể biểu hiện thành `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError`, hoặc không báo exception nhưng JSON output thay đổi.

### 4.1. Chẩn đoán bằng Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-datatype-jsr310 --configuration runtimeClasspath
~~~

Kết quả cần phân biệt **requested version** với **resolved version**. Đọc dependency constraints của Spring Boot BOM và nguyên nhân Gradle chọn một phiên bản. Đừng tự pin Jackson databind phiên bản mới nhưng để core/datatype modules ở các versions khác mà không kiểm tương thích.

### 4.2. Test runtime có thể khác production runtime

Một module Jackson chỉ nằm ở `testImplementation` có thể giúp test pass nhưng application production thiếu module đó. Kiểm cả `runtimeClasspath` và `testRuntimeClasspath`. Với Spring Boot starter web, phần JSON phải hiện diện ở runtime; đừng gỡ một starter rồi chỉ add JSON module vào test scope.

### 4.3. Khi nâng Spring Boot minor

Không chỉ đọc version của Jackson databind. Kiểm Spring Framework message converters, Spring Data/JPA, WebFlux codecs, Jackson modules, test helper versions và dependency overrides. Nếu serialized JSON khác, cần biết đó là thay đổi từ code DTO, annotation, module hay Boot auto-config.

## 5. Một JSON contract đủ mạnh cần bảo vệ gì?

Giả sử invoice response baseline:

~~~json
{"invoice_id":"INV-7","issued_at":"2026-01-02T03:04:05Z","amount_cents":1999,"state":"PAID"}
~~~

Các thay đổi dễ làm client cũ hỏng:

| Thay đổi | Hệ quả |
| --- | --- |
| invoice_id → invoiceId | Client đọc field cũ nhận missing/null |
| amount_cents integer → string | Type mismatch/coercion khác |
| amount_cents → {"cents":1999} | Custom serializer không còn hiệu lực |
| issued_at ISO string → epoch | Date parser/contract khác |
| state PAID → PAID_FULL | Enum parser/generated client fail |
| state thêm ON_HOLD | Legacy exhaustive switch có thể fail |
| memo absent → memo:null | Khác null/absent semantics |
| price 1999 → 20 nhưng giữ type | Semantic corruption, schema không phát hiện |
| Thêm memo non-null | Có thể compatible với tolerant reader, breaking với strict reader |
| Response application/json → text/plain | HTTP consumer không deserialize |
| New required request field | Client cũ không gửi được |
| Error status 404 → 200 với null | Client cũ phân nhánh sai |
| Money Long → double | Precision/rounding mất tính chính xác |
| Unknown JSON property policy đổi | Client có thể từ chối hoặc bỏ qua dữ liệu |

**Đừng khẳng định “thêm field luôn tương thích”.** Nếu consumer dùng `FAIL_ON_UNKNOWN_PROPERTIES=true`, một trường mới cũng có thể gây lỗi. Cần kiểm **consumer versions thực sự được hỗ trợ**.

### 5.1. Frozen fixtures thay vì expected do mapper mới tạo

Một golden fixture được lưu từ **released contract** phải được giữ độc lập. Nếu test serialize DTO candidate rồi dùng chính output đó làm expected, cả actual và expected có thể đổi cùng nhau; test xanh mà contract gãy.

### 5.2. Structural vs semantic assertions

JSONPath/JsonNode kiểm key/type/nullability. Nhưng chúng không biết giá trị 20 cents có sai với business rule 1999 cents hay không. Vì vậy phải có expected values thực tế và domain invariants riêng.

### 5.3. JSON object equality và field order

Thứ tự các fields trong JSON object thường không mang ý nghĩa nghiệp vụ. So `JsonNode` cho phép kiểm cấu trúc mà không phụ thuộc whitespace/property order. Ngược lại, **JSON arrays** thường có thứ tự quan trọng. Nếu API ký/hash raw bytes, cần thêm canonicalization/byte-level tests.

## 6. @JsonTest và JSON testers

Trong Spring Boot 3.x, `@JsonTest` tạo một **JSON slice** với mapper, serializers/modules và các JSON test helpers. Nó không tự nạp business services/repositories như full context.

~~~java
@JsonTest
class InvoiceJsonSliceTest {
    @Autowired
    JacksonTester<InvoiceDto> json;
}
~~~

Các helper:

- `JacksonTester<T>`: write/parse cho Jackson.
- `JsonContent<T>`: kết quả `json.write(value)`, lấy text qua `getJson()`.
- `JsonContentAssert`: AssertJ-based assertions cho JSON equality/JSONPath.
- `BasicJsonTester`: JSON string assertions không cần DTO type.
- `GsonTester<T>`/`JsonbTester<T>`: nếu app chọn Gson/JSON-B.
- `@AutoConfigureJsonTesters`: cho phép bật JSON testers trong một context test phù hợp.

### 6.1. Hai loại test nên có

**Mapper test:** 

~~~java
JsonNode tree = mapper.readTree(
    json.write(dto).getJson());
assertTrue(tree.path("amount_cents").isIntegralNumber());
~~~

**HTTP test:**

~~~java
mvc.perform(get("/api/v1/invoices/INV-7"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.amount_cents").value(1999));
~~~

Hai snippet cần nằm trong test class đã inject các biến tương ứng. Chúng không phải hai Java source files độc lập.

### 6.2. Tránh new ObjectMapper trong test

~~~java
ObjectMapper adHocMapper = new ObjectMapper();
~~~

Trong Boot3, mapper này có thể thiếu JavaTimeModule và @JsonComponent custom serializers. Nó không đại diện cho mapper MVC thực dùng. Nếu đang kiểm behavior Spring Boot, hãy inject `ObjectMapper` từ `@JsonTest` hoặc full context.

### 6.3. JSON tester không chứng minh consumer compatibility

Nếu `JacksonTester<NewInvoiceDto>` serialize rồi deserialize lại thành NewInvoiceDto, cả hai phía có thể cùng đổi và round-trip vẫn pass. Phải thêm golden v1 fixture và legacy reader thật.

## 7. Các nguồn drift phổ biến

### 7.1. Property naming

Dùng `@JsonProperty("invoice_id")` để giữ wire name ngay cả khi Java field đổi tên. Nếu đã chọn global snake_case strategy thì vẫn phải có test và tránh đổi strategy chỉ vì refactor.

### 7.2. Null inclusion

`@JsonInclude(JsonInclude.Include.NON_NULL)` khiến memo null bị bỏ qua. Một API khác có thể cam kết luôn hiện memo:null. Test phải phân biệt absent key và explicit null.

### 7.3. Custom Money serializer

Một record `Money(long cents)` mặc định có thể serialize thành nested object. API contract muốn `amount_cents` là JSON integer. `@JsonComponent` của Boot3 đăng ký serializer cho Money. Migrate Boot4 cần chuyển custom serializers sang Jackson3 API và `@JacksonComponent`.

### 7.4. Java Time

Với `Instant`, mapper có JavaTime support và timestamp settings phù hợp mới xuất ISO string. Một mapper thiếu module có thể throw; mapper bật numeric timestamps có thể xuất epoch. Test string và giá trị.

### 7.5. Enum evolution

Enum value mới có thể phá client cũ. Đừng tự bật unknown-enum-to-null rồi coi tương thích nếu downstream vẫn dereference null. Nếu có fallback UNKNOWN, định nghĩa semantics rõ và test.

### 7.6. Coercion

JSON string `"1999"` và number `1999` không cùng type. Một số Jackson configs có thể coerce; money API nên có policy rõ và test negative cases. Lab bên dưới dùng strict deserializer.

### 7.7. BigDecimal, double và precision

Tiền tệ nên dùng minor units integer hoặc BigDecimal với scale/rounding quy định rõ. Chuyển sang double có thể gây floating-point drift. Với JavaScript consumer, integer cực lớn vượt safe integer cũng cần thiết kế wire representation.

### 7.8. Polymorphism

Các settings như `@JsonTypeInfo`, default typing và subtype registration có thể thay đổi khi nâng Jackson. Không bật permissive polymorphic deserialization trên dữ liệu từ clients không tin cậy. Kiểm whitelist subtypes, discriminators và security advisories.

## 8. Migration Boot 3.x → Boot 4.0 / Jackson 2 → Jackson 3

Phần này dựa theo **Spring Boot 4.0 Migration Guide** và tài liệu JSON chính thức. Các ví dụ Boot4 chỉ là **hướng chuyển đổi**; project runnable sau đó cố định Boot3.3.5.

### 8.1. Jackson 3 mặc định

Spring Boot 4.0 ưu tiên Jackson 3 `JsonMapper`. Các starters JSON/Jackson cung cấp Jackson 3. Một `ObjectMapper` Jackson2 do bạn tự định nghĩa **không tự thay JsonMapper3** trong Boot4.

### 8.2. Package và group IDs thay đổi

Jackson3 thường dùng `tools.jackson`, nhưng Jackson annotations vẫn giữ package `com.fasterxml.jackson.annotation`. Không chạy replace-all mù quáng.

### 8.3. Annotation và module migrations

Boot3 dùng `@JsonComponent`/`@JsonMixin`. Boot4 ưu tiên tên rõ như `@JacksonComponent`/`@JacksonMixin`. Custom serializers/deserializers chuyển sang types/signatures Jackson3 tương ứng. Không thể giữ Java serializer Jackson2 rồi chỉ thay annotation và giả định Boot4 tự áp dụng.

### 8.4. Module discovery

Theo Boot4 migration guide, Jackson3 auto-detect các modules trên classpath rộng hơn so với Boot3. Có thể cấu hình:

~~~properties
spring.jackson.find-and-add-modules=false
~~~

Chỉ dùng có chủ đích trong Boot4 khi muốn kiểm soát discovery và có golden contracts. Đừng thêm property không hiểu nguồn khác biệt.

### 8.5. Default gần Jackson2

Boot4 cung cấp:

~~~properties
spring.jackson.use-jackson2-defaults=true
~~~

Property này giúp defaults của JsonMapper3 gần hơn hành vi Jackson2 trong Boot3, **không bảo đảm byte-for-byte compatibility**. Vẫn cần kiểm custom modules/DTOs/HTTP converters/clients.

### 8.6. Jackson2 bridge tạm thời

Boot4 có module hỗ trợ Jackson2:

~~~groovy
implementation 'org.springframework.boot:spring-boot-jackson2'
~~~

Module này **deprecated** và được thiết kế để hỗ trợ chuyển tiếp. Jackson2-specific properties nằm dưới namespace `spring.jackson2.*`. Nếu cả hai Jackson majors tồn tại, cần chọn mapper theo HTTP stack cụ thể, ví dụ Spring MVC/imperative clients:

~~~properties
spring.http.converters.preferred-json-mapper=jackson2
~~~

Còn WebFlux/reactive codecs:

~~~properties
spring.http.codecs.preferred-json-mapper=jackson2
~~~

Không thêm cả hai cho mọi ứng dụng. Đây là đường migration có sunset plan, không phải giải pháp sử dụng vĩnh viễn.

### 8.7. JSON tester ở Boot4

~~~text
Spring Boot 3.x:
  JacksonTester<T>  -> Jackson 2 ObjectMapper

Spring Boot 4.x:
  JacksonTester<T>  -> Jackson 3 JsonMapper
  Jackson2Tester<T> -> Jackson 2 bridge (deprecated)
~~~

Dùng đúng JSON test starter/module của Boot4. Boot4 đã modularize các starters và test modules; kiểm `spring-boot-starter-jackson`, `spring-boot-starter-jackson-test` cùng tài liệu version bạn đang nâng. Không copy mù imports/dependencies của Boot3.

### 8.8. Jackson configuration property paths đổi

Boot4 có các nhánh như `spring.jackson.json.read.*`/`spring.jackson.json.write.*`. Những settings Jackson2 bridge ở `spring.jackson2.*`. Đọc migration guide và generated metadata thay vì giả định Boot3 property key vẫn điều khiển Jackson3.

### 8.9. Thứ tự nâng cấp thực tế

1. Ổn định baseline Spring Boot 3.x còn hỗ trợ.
2. Lưu frozen fixtures của public API versions đang được clients sử dụng.
3. Chạy @JsonTest, MockMvc, real consumer tests trên baseline.
4. Đọc migration guide và dependency constraints cho Boot4.
5. Nâng Boot/Gradle/JDK/test starters theo support policy.
6. Chuyển ObjectMapper2 → JsonMapper3, custom serializer/module code và @JacksonComponent.
7. Kiểm JSON test classes đã migrate, legacy DTO fixtures vẫn còn hiệu lực.
8. Chạy HTTP converter tests vì mapper của JSON slice chưa chắc là mapper thực tạo response.
9. Nếu tạm dùng Jackson2 bridge, ghi rõ transport nào dùng mapper nào và kế hoạch loại bridge.
10. Chạy schema diff/semantic assertions, staging/canary và rollback readiness.

## 9. Project runnable: Java 17, Spring Boot 3.3.5, Gradle

Lab được thiết kế để chạy **chỉ trên Boot 3.3.5/Jackson2**. Phần Boot4 cần migrate source trước khi chạy. Không có Docker, database hay external HTTP dependency.

### 9.1. Cấu trúc thư mục

~~~text
jackson-contract-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/jsonlab/
    │   ├── JsonLabApplication.java
    │   ├── domain/Money.java
    │   ├── domain/InvoiceState.java
    │   ├── api/InvoiceDto.java
    │   ├── api/CreateInvoiceRequest.java
    │   ├── api/InvoiceService.java
    │   ├── api/InvoiceController.java
    │   ├── api/InvoiceNotFoundException.java
    │   ├── api/InvoiceErrorHandler.java
    │   ├── json/MoneyJsonComponent.java
    │   └── consumer/LegacyInvoiceV1.java
    └── test/
        ├── resources/contracts/
        │   ├── invoice-v1.json
        │   ├── invoice-v2-additive.json
        │   ├── invoice-breaking-rename.json
        │   ├── invoice-breaking-units.json
        │   ├── invoice-breaking-enum.json
        │   └── invoice-breaking-null.json
        └── java/com/example/jsonlab/
            ├── InvoiceJsonTest.java
            ├── InvoiceMvcTest.java
            ├── InvoiceFullContextTest.java
            └── MapperWiringTest.java
~~~

Wrapper scripts/JAR do Gradle sinh hoặc được lấy từ repository. Không thể tạo file binary `gradle-wrapper.jar` bằng cách copy Markdown.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'jackson-contract-lab'
~~~

### 9.3. build.gradle

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Dependency management của Boot BOM chọn Jackson2 core/databind/modules tương thích. `spring-boot-starter-web` cung cấp Jackson/HTTP converters; `starter-validation` đưa Jakarta Bean Validation cho request body tests. `starter-test` có JUnit Jupiter, MockMvc và JSON tester support.

### 9.4. JsonLabApplication.java

~~~java
package com.example.jsonlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLabApplication.class, args);
    }
}
~~~

### 9.5. domain/Money.java

~~~java
package com.example.jsonlab.domain;

public record Money(long cents) {

    public Money {
        if (cents < 0L) {
            throw new IllegalArgumentException(
                "amount_cents must be nonnegative");
        }
    }
}
~~~

### 9.6. domain/InvoiceState.java

~~~java
package com.example.jsonlab.domain;

public enum InvoiceState {
    OPEN,
    PAID
}
~~~

### 9.7. api/InvoiceDto.java

~~~java
package com.example.jsonlab.api;

import java.time.Instant;
import com.example.jsonlab.domain.Money;
import com.example.jsonlab.domain.InvoiceState;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record InvoiceDto(
    @JsonProperty("invoice_id")
    String invoiceId,
    @JsonProperty("issued_at")
    Instant issuedAt,
    @JsonProperty("amount_cents")
    Money amount,
    @JsonProperty("state")
    InvoiceState state,
    @JsonProperty("memo")
    String memo) {
}
~~~

`@JsonProperty` giúp giữ snake_case kể cả Java record fields bị refactor. `@JsonInclude(NON_NULL)` làm memo vắng mặt khi null.

### 9.8. api/CreateInvoiceRequest.java

~~~java
package com.example.jsonlab.api;

import com.example.jsonlab.domain.Money;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateInvoiceRequest(
    @JsonProperty("invoice_id")
    @NotBlank String invoiceId,
    @JsonProperty("amount_cents")
    @NotNull Money amount,
    @JsonProperty("memo")
    String memo) {
}
~~~

`memo` optional, request cũ không gửi field đó vẫn hợp lệ. Field money được deserialize bằng custom deserializer kiểm JSON integer.

### 9.9. api/InvoiceService.java

~~~java
package com.example.jsonlab.api;

import java.time.Instant;

import com.example.jsonlab.domain.InvoiceState;
import com.example.jsonlab.domain.Money;

import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private static final Instant ISSUED_AT =
        Instant.parse("2026-01-02T03:04:05Z");

    public InvoiceDto find(String id) {
        if (!"INV-7".equals(id)) {
            throw new InvoiceNotFoundException(id);
        }
        return new InvoiceDto(
            "INV-7", ISSUED_AT,
            new Money(1999L), InvoiceState.PAID, null);
    }

    public InvoiceDto create(CreateInvoiceRequest request) {
        return new InvoiceDto(
            request.invoiceId(), ISSUED_AT,
            request.amount(), InvoiceState.OPEN,
            request.memo());
    }
}
~~~

Dữ liệu cố định để tests tái lập. Đây là service demo, không mô phỏng persistence/tiền tệ production.

### 9.10. api/InvoiceNotFoundException.java

~~~java
package com.example.jsonlab.api;

public class InvoiceNotFoundException
        extends RuntimeException {

    public InvoiceNotFoundException(String id) {
        super("Invoice not found: " + id);
    }
}
~~~

### 9.11. api/InvoiceController.java

~~~java
package com.example.jsonlab.api;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/invoices")
public class InvoiceController {

    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public InvoiceDto find(
            @PathVariable("id") String id) {
        return service.find(id);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public InvoiceDto create(
            @Valid @RequestBody CreateInvoiceRequest request) {
        return service.create(request);
    }
}
~~~

### 9.12. api/InvoiceErrorHandler.java

~~~java
package com.example.jsonlab.api;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InvoiceErrorHandler {

    @ExceptionHandler(InvoiceNotFoundException.class)
    public ResponseEntity<ApiError> missing() {
        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(new ApiError("INVOICE_NOT_FOUND"));
    }

    public record ApiError(String code) {
    }
}
~~~

### 9.13. json/MoneyJsonComponent.java

~~~java
package com.example.jsonlab.json;

import java.io.IOException;

import com.example.jsonlab.domain.Money;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer
            extends JsonSerializer<Money> {

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers)
                throws IOException {

            generator.writeNumber(value.cents());
        }
    }

    public static class Deserializer
            extends JsonDeserializer<Money> {

        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context)
                throws IOException {

            if (parser.currentToken()
                    != JsonToken.VALUE_NUMBER_INT) {
                throw JsonMappingException.from(
                    parser,
                    "amount_cents must be JSON integer");
            }

            return new Money(parser.getLongValue());
        }
    }
}
~~~

**Giải thích:** Serializer biến Money thành JSON number, deserializer nhận **chỉ number token nguyên** chứ không tự coerce `"1999"` từ string. Nếu bỏ component/module, value object có thể bị viết thành `{"cents":1999}`, và cả JSON test lẫn MVC test phải phát hiện.

### 9.14. consumer/LegacyInvoiceV1.java

~~~java
package com.example.jsonlab.consumer;

import java.time.Instant;

import com.example.jsonlab.domain.InvoiceState;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LegacyInvoiceV1(
    @JsonProperty("invoice_id")
    String invoiceId,
    @JsonProperty("issued_at")
    Instant issuedAt,
    @JsonProperty("amount_cents")
    Long amountCents,
    @JsonProperty("state")
    InvoiceState state) {

    public LegacyInvoiceV1 {
        if (invoiceId == null || invoiceId.isBlank()
                || issuedAt == null
                || amountCents == null
                || amountCents < 0L
                || state == null) {
            throw new IllegalArgumentException(
                "Invalid legacy invoice contract");
        }
    }
}
~~~

Client cũ này cố ý bỏ qua unknown JSON fields, nhưng fail-fast với các field cũ bị xóa/null. `Long` tránh missing amount bị silently coi là 0. Thêm enum value mới vẫn có thể fail; ignoreUnknown không áp dụng cho unknown enum constants.

## 10. Sáu golden JSON fixtures

Tất cả nằm trong `src/test/resources/contracts/`. Không tạo expected bằng mapper candidate tại runtime.

### invoice-v1.json

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "PAID"
}
~~~

### invoice-v2-additive.json

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "PAID",
  "memo": "Paid in full"
}
~~~

### invoice-breaking-rename.json

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_minor_units": 1999,
  "state": "PAID"
}
~~~

### invoice-breaking-units.json

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 20,
  "state": "PAID"
}
~~~

### invoice-breaking-enum.json

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "ON_HOLD"
}
~~~

### invoice-breaking-null.json

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": null,
  "state": "PAID"
}
~~~

Những fixtures “breaking” chỉ dùng để minh họa cơ chế bắt lỗi. Một test `assertThrows` pass khi phát hiện dữ liệu không tương thích **không có nghĩa** một provider thật trả breaking response là compatible. Provider candidate phải được kiểm bằng contract success assertions riêng.

## 11. InvoiceJsonTest: test mapper Spring Boot

**src/test/java/com/example/jsonlab/InvoiceJsonTest.java**

~~~java
package com.example.jsonlab;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

import com.example.jsonlab.api.InvoiceDto;
import com.example.jsonlab.api.InvoiceService;
import com.example.jsonlab.consumer.LegacyInvoiceV1;
import com.example.jsonlab.domain.InvoiceState;
import com.example.jsonlab.domain.Money;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

@JsonTest
class InvoiceJsonTest {

    @Autowired
    JacksonTester<InvoiceDto> json;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    ApplicationContext context;

    private static InvoiceDto sample(String memo) {
        return new InvoiceDto(
            "INV-7",
            Instant.parse("2026-01-02T03:04:05Z"),
            new Money(1999L),
            InvoiceState.PAID,
            memo);
    }

    private static String fixture(String name)
            throws IOException {

        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {

            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
        }
    }

    public record StrictInvoice(
        @JsonProperty("invoice_id")
        String invoiceId,
        @JsonProperty("issued_at")
        Instant issuedAt,
        @JsonProperty("amount_cents")
        Long amountCents,
        @JsonProperty("state")
        InvoiceState state) {
    }

    @Test
    void baselineMatchesFrozenWireContract()
            throws Exception {
        JsonNode expected = mapper.readTree(
            fixture("invoice-v1.json"));
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());

        assertEquals(expected, actual);
    }

    @Test
    void absentMemoIsNotRenderedAsNull()
            throws Exception {
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());
        assertFalse(actual.has("memo"));
    }

    @Test
    void additiveMemoRetainsOriginalFields()
            throws Exception {
        JsonNode expected = mapper.readTree(
            fixture("invoice-v2-additive.json"));
        JsonNode actual = mapper.readTree(
            json.write(sample("Paid in full")).getJson());
        assertEquals(expected, actual);
    }

    @Test
    void customMoneySerializerWritesInteger()
            throws Exception {
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());
        assertTrue(
            actual.path("amount_cents").isIntegralNumber());
        assertEquals(1999L,
            actual.path("amount_cents").longValue());
    }

    @Test
    void instantIsIsoText()
            throws Exception {
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());
        assertTrue(actual.path("issued_at").isTextual());
        assertEquals(
            "2026-01-02T03:04:05Z",
            actual.path("issued_at").textValue());
    }

    @Test
    void jacksonTesterParsesOriginalFixture()
            throws Exception {
        InvoiceDto result = json.parseObject(
            fixture("invoice-v1.json"));
        assertEquals(sample(null), result);
    }

    @Test
    void tolerantOldReaderAcceptsAddedField()
            throws Exception {
        LegacyInvoiceV1 result = mapper.readValue(
            fixture("invoice-v2-additive.json"),
            LegacyInvoiceV1.class);

        assertEquals("INV-7", result.invoiceId());
        assertEquals(1999L,
            result.amountCents().longValue());
        assertEquals(InvoiceState.PAID, result.state());
    }

    @Test
    void strictOldReaderRejectsAddedField()
            throws Exception {
        ObjectMapper strict = mapper.copy().configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            true);

        assertThrows(
            JsonProcessingException.class,
            () -> strict.readValue(
                fixture("invoice-v2-additive.json"),
                StrictInvoice.class));
    }

    @Test
    void renamedMoneyFieldBreaksLegacy()
            throws Exception {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                fixture("invoice-breaking-rename.json"),
                LegacyInvoiceV1.class));
    }

    @Test
    void unknownEnumBreaksLegacy()
            throws Exception {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                fixture("invoice-breaking-enum.json"),
                LegacyInvoiceV1.class));
    }

    @Test
    void missingRequiredMoneyFailsFast()
            throws Exception {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                fixture("invoice-breaking-null.json"),
                LegacyInvoiceV1.class));
    }

    @Test
    void semanticUnitChangeStillParses()
            throws Exception {
        LegacyInvoiceV1 result = mapper.readValue(
            fixture("invoice-breaking-units.json"),
            LegacyInvoiceV1.class);

        assertEquals(20L,
            result.amountCents().longValue());
        assertNotEquals(1999L,
            result.amountCents().longValue());
    }

    @Test
    void jsonSliceDoesNotLoadBusinessService() {
        assertEquals(0,
            context.getBeanNamesForType(
                InvoiceService.class).length);
    }
}
~~~

### Ý nghĩa 13 test methods

- Baseline JSON tree equality bắt field/type/date/enum/null policy drift.
- Money serialization khẳng định custom @JsonComponent có hiệu lực.
- JacksonTester parse fixture khẳng định reverse deserializer, không chỉ serialize.
- Legacy tolerant/strict tests phân biệt chính sách unknown fields.
- Rename, unknown enum, null amount được kiểm như intentional failure.
- Semantic amount=20 cho thấy **parser không phát hiện lỗi nghiệp vụ**.
- JSON slice assert không nạp business service; giữ test nhanh, đúng layer.

### Sử dụng JsonContent/AssertJ

`json.write(value)` trả `JsonContent<T>` với `getJson()`. Trong Boot 3.x có thể viết, trong một test method đã có `json` và `sample`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(json.write(sample(null)))
    .hasJsonPathNumberValue("@.amount_cents");
~~~

Đây là **snippet trong test class**, không phải một Java file hoàn chỉnh. `JacksonTester` cũng hỗ trợ những assertion khác qua `JsonContentAssert`. Với fixtures ở resource path riêng, lab dùng `ClassPathResource`/JsonNode để tránh mơ hồ relative resource naming và JSON object field order.

## 12. InvoiceMvcTest: kiểm HTTP conversion

**src/test/java/com/example/jsonlab/InvoiceMvcTest.java**

~~~java
package com.example.jsonlab;

import java.time.Instant;

import com.example.jsonlab.api.CreateInvoiceRequest;
import com.example.jsonlab.api.InvoiceController;
import com.example.jsonlab.api.InvoiceDto;
import com.example.jsonlab.api.InvoiceNotFoundException;
import com.example.jsonlab.api.InvoiceService;
import com.example.jsonlab.domain.InvoiceState;
import com.example.jsonlab.domain.Money;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(InvoiceController.class)
class InvoiceMvcTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    InvoiceService service;

    private static InvoiceDto sample(String memo) {
        return new InvoiceDto(
            "INV-7",
            Instant.parse("2026-01-02T03:04:05Z"),
            new Money(1999L),
            InvoiceState.PAID,
            memo);
    }

    @Test
    void httpGetPreservesOriginalContract()
            throws Exception {

        when(service.find("INV-7"))
            .thenReturn(sample(null));

        mvc.perform(get("/api/v1/invoices/INV-7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.invoice_id")
                .value("INV-7"))
            .andExpect(jsonPath("$.issued_at")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.amount_cents")
                .isNumber())
            .andExpect(jsonPath("$.amount_cents")
                .value(1999))
            .andExpect(jsonPath("$.state")
                .value("PAID"))
            .andExpect(jsonPath("$.memo")
                .doesNotExist());

        verify(service).find("INV-7");
    }

    @Test
    void httpGetAllowsAdditiveMemo()
            throws Exception {
        when(service.find("INV-7"))
            .thenReturn(sample("Paid in full"));

        mvc.perform(get("/api/v1/invoices/INV-7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.amount_cents")
                .value(1999))
            .andExpect(jsonPath("$.memo")
                .value("Paid in full"));
    }

    @Test
    void http404KeepsErrorCode()
            throws Exception {
        when(service.find("UNKNOWN"))
            .thenThrow(
                new InvoiceNotFoundException("UNKNOWN"));

        mvc.perform(get("/api/v1/invoices/UNKNOWN"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("INVOICE_NOT_FOUND"));
    }

    @Test
    void oldPostWithoutMemoIsStillAccepted()
            throws Exception {
        when(service.create(any(CreateInvoiceRequest.class)))
            .thenReturn(sample(null));

        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":1999}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.amount_cents")
                .value(1999));

        ArgumentCaptor<CreateInvoiceRequest> captor =
            ArgumentCaptor.forClass(
                CreateInvoiceRequest.class);

        verify(service).create(captor.capture());
        assertEquals("INV-9",
            captor.getValue().invoiceId());
        assertEquals(new Money(1999L),
            captor.getValue().amount());
        assertNull(captor.getValue().memo());
    }

    @Test
    void newPostMayHaveOptionalMemo()
            throws Exception {
        when(service.create(any(CreateInvoiceRequest.class)))
            .thenReturn(sample("Gift"));

        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":1999,"
                    + "\"memo\":\"Gift\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.memo")
                .value("Gift"));

        ArgumentCaptor<CreateInvoiceRequest> captor =
            ArgumentCaptor.forClass(
                CreateInvoiceRequest.class);

        verify(service).create(captor.capture());
        assertEquals("Gift",
            captor.getValue().memo());
    }

    @Test
    void quotedAmountIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":\"1999\"}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void missingAmountIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"invoice_id\":\"INV-9\"}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void negativeAmountIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":-1}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }
}
~~~

### Vì sao cần MockMvc nếu đã có @JsonTest?

`@JsonTest` có thể pass nhưng MVC message converter trong app dùng một mapper tùy chỉnh khác hoặc content negotiation khác. `@WebMvcTest` bảo vệ route/status/media type/serialization của Spring MVC. `verifyNoInteractions(service)` giúp đảm bảo malformed request không được chuyển thành business action.

## 13. InvoiceFullContextTest: wiring ứng dụng thật

**src/test/java/com/example/jsonlab/InvoiceFullContextTest.java**

~~~java
package com.example.jsonlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(classes = JsonLabApplication.class)
@AutoConfigureMockMvc
class InvoiceFullContextTest {

    @Autowired
    MockMvc mvc;

    @Test
    void fullAppUsesCorrectMapperAndSerializer()
            throws Exception {
        mvc.perform(get("/api/v1/invoices/INV-7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.invoice_id")
                .value("INV-7"))
            .andExpect(jsonPath("$.issued_at")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.amount_cents")
                .value(1999))
            .andExpect(jsonPath("$.memo")
                .doesNotExist());
    }

    @Test
    void fullAppStillReturns404ForUnknownInvoice()
            throws Exception {
        mvc.perform(get("/api/v1/invoices/UNKNOWN"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("INVOICE_NOT_FOUND"));
    }

    @Test
    void fullAppAcceptsOldPostRequest()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":2500}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.invoice_id")
                .value("INV-9"))
            .andExpect(jsonPath("$.amount_cents")
                .value(2500))
            .andExpect(jsonPath("$.state")
                .value("OPEN"));
    }
}
~~~

Full-context test dùng `InvoiceService` thật và `MoneyJsonComponent` thật. Không cần DB/network vì service demo deterministic. MockMvc không mở socket; nếu cần kiểm proxy/TLS/streaming, thêm random-port HTTP smoke riêng.

## 14. MapperWiringTest: kiểm Jackson runtime thực

**src/test/java/com/example/jsonlab/MapperWiringTest.java**

~~~java
package com.example.jsonlab;

import java.time.Instant;
import com.example.jsonlab.api.InvoiceDto;
import com.example.jsonlab.domain.Money;
import com.example.jsonlab.domain.InvoiceState;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = JsonLabApplication.class)
class MapperWiringTest {

    @Autowired
    ObjectMapper mapper;

    @Test
    void boot3RuntimeStillUsesJackson2() {
        assertEquals(
            2, mapper.version().getMajorVersion());
    }

    @Test
    void mapperHasJavaTimeAndMoneySupport()
            throws Exception {

        InvoiceDto dto = new InvoiceDto(
            "INV-7",
            Instant.parse("2026-01-02T03:04:05Z"),
            new Money(1999L),
            InvoiceState.PAID,
            null);

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(dto));

        assertTrue(json.path("amount_cents")
            .isIntegralNumber());
        assertEquals(1999L,
            json.path("amount_cents").longValue());
        assertEquals("2026-01-02T03:04:05Z",
            json.path("issued_at").asText());
    }
}
~~~

Method đầu **chỉ đúng cho Boot3/Jackson2 baseline**. Sau khi migrate Boot4, đổi test sang Jackson3 JsonMapper and corresponding version assertion; không giữ Jackson2 mapper injection rồi coi đó là kiểm được default Jackson3.

## 15. Tổng hợp test coverage và cách chạy

| Lớp | Số phương thức @Test | Vai trò |
| --- | ---: | --- |
| InvoiceJsonTest | 13 | JSON fixtures, JacksonTester, legacy clients, dates/money/enums |
| InvoiceMvcTest | 8 | MVC converter, request validation, status, JSON |
| InvoiceFullContextTest | 3 | Real service + application mapper wiring |
| MapperWiringTest | 2 | Jackson version, modules trong full context |
| **Tổng** | **26** | Contract regression tests nhiều tầng |

Lệnh chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu project chưa có Gradle Wrapper và môi trường đã cài Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Chạy nhóm JSON khi cần triage:

~~~bash
./gradlew test --tests 'com.example.jsonlab.InvoiceJsonTest'
./gradlew test --tests 'com.example.jsonlab.InvoiceMvcTest'
./gradlew test --tests 'com.example.jsonlab.InvoiceFullContextTest'
./gradlew test --tests 'com.example.jsonlab.MapperWiringTest'
~~~

Buộc test task chạy lại:

~~~bash
./gradlew test --rerun-tasks --stacktrace
~~~

Báo cáo sau khi chạy thường nằm tại:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.jsonlab.InvoiceJsonTest.xml
build/test-results/test/TEST-com.example.jsonlab.InvoiceMvcTest.xml
build/test-results/test/TEST-com.example.jsonlab.InvoiceFullContextTest.xml
build/test-results/test/TEST-com.example.jsonlab.MapperWiringTest.xml
~~~

**Expected:** 26 JUnit methods được phát hiện và pass nếu mọi source, fixtures, dependencies/JDK tương thích. Đây là **dự kiến từ source**, **chưa thực thi Gradle/JUnit tại thời điểm soạn bài**. Không bịa “BUILD SUCCESSFUL” hoặc execution time. Các negative fixtures pass khi assertions phát hiện breaking JSON như được thiết kế.

## 16. Các lỗi thường gặp sau khi nâng Jackson

### 16.1. NoClassDefFoundError

Nếu dependency vẫn cần Jackson2 nhưng runtime chỉ có Jackson3, bạn có thể gặp:

~~~text
NoClassDefFoundError: com/fasterxml/jackson/databind/ObjectMapper
~~~

Kiểm resolved classpath và libraries chưa nâng. Boot4 có Jackson2 bridge tạm thời nhưng phải có kế hoạch migrate, không assume Jackson2 support vĩnh viễn.

### 16.2. NoSuchMethodError

Nếu Jackson core/databind/datatype modules không tương thích, runtime có thể lỗi linkage:

~~~text
java.lang.NoSuchMethodError: ... Jackson API ...
~~~

Chẩn đoán bằng `dependencyInsight` và BOM. Không chữa lỗi linkage bằng `@JsonIgnoreProperties` hay nới JSON assertions.

### 16.3. JavaTimeModule thiếu

Một ad-hoc `new ObjectMapper()` có thể thiếu JavaTimeModule, không biết serialize `Instant`. Boot auto-configured mapper có modules/defaults. Test nên inject mapper thật, hoặc nếu app cố tình tự tạo mapper, cấu hình modules rõ.

### 16.4. JacksonTester không inject được

Kiểm test annotation `@JsonTest`, test starter, Json mapper classpath, generic type và Jackson2/Jackson3 tester API đang dùng. Trong Boot4, `JacksonTester` mặc định gắn Jackson3; `Jackson2Tester` là bridge deprecated. Đừng thêm toàn bộ production configs chỉ để inject một tester.

### 16.5. @JsonComponent không còn được đăng ký

Nếu Money thành `{"cents":1999}`, có thể component scanning sai, mapper tự tạo, module bị override hoặc version migration Jackson3 chưa hoàn chỉnh. Chạy cả @JsonTest và MockMvc để xác định boundary bị ảnh hưởng.

### 16.6. JSON slice pass nhưng HTTP fail

Có thể Spring MVC converter dùng mapper khác vì custom bean/config hoặc Boot4 preferred-json-mapper. Kiểm converter registry, `MappingJackson2HttpMessageConverter`/Jackson3 equivalents và wiring. Không suy luận converter behavior từ JSON slice duy nhất.

### 16.7. Enum parsing fail

Nếu provider thêm `ON_HOLD`, legacy Java enum không biết constant đó. Có thể thiết kế fallback UNKNOWN hoặc version contract; fallback chỉ đúng nếu downstream hiểu semantics. Không biến lỗi thành null im lặng.

### 16.8. Null thành 0

Nếu client dùng primitive `long` và field mất, Jackson có thể dùng 0 tùy cấu hình. LegacyInvoiceV1 dùng wrapper `Long` và constructor validation để fail-fast. Với payments, silent corruption cần được bắt bằng domain assertions.

### 16.9. JSON equality quá chặt hoặc quá lỏng

Một snapshot whole-object không chấp nhận field bổ sung dù consumer tolerant; một assertion chỉ contains key có thể bỏ sót type change. Chọn **provider contract** và **consumer contract** phù hợp, đồng thời bảo vệ required fields/values.

### 16.10. Chỉ kiểm DTO round-trip

New DTO serialize→deserialize có thể pass khi cả serializer/deserializer cùng đổi. Frozen fixture và legacy consumer tests mới phát hiện backward compatibility thực.

## 17. CI strategy khi nâng Boot/Jackson

Một pipeline tốt phân biệt hai giai đoạn:

~~~text
Baseline Boot3 source + frozen released JSON fixtures
    |
    +-- @JsonTest
    +-- @WebMvcTest
    +-- @SpringBootTest
    +-- legacy consumer fixture tests
    |
    v
Record baseline contract + test evidence
    |
    v
Candidate Boot4 source đã migrate APIs/imports/dependencies
    |
    +-- equivalent JSON tests using Jackson3
    +-- same frozen fixtures and legacy client interactions
    +-- HTTP converter tests
    +-- schema/semantic validations
    |
    v
PASS -> staging/canary
FAIL -> fix candidate or versioned migration
~~~

**Không tạo một matrix giả** bằng cách đổi Spring Boot plugin version từ 3.3.5 thành 4.0 trong cùng code Jackson2 rồi tuyên bố tất cả compiler errors là JSON breaking changes. Boot4 migration cần đổi APIs/test modules có chủ đích. Nhưng các **released wire contracts** không được đổi âm thầm.

### 17.1. CI artifacts nên lưu gì?

- Git commit và baseline/candidate IDs.
- JDK, Gradle Wrapper, Spring Boot và Jackson resolved versions.
- Test count/pass/fail/skipped từ JUnit XML.
- Golden fixtures version/consumer owner.
- JSON diff ở fields/types/values khi fail.
- HTTP method/path/status/media type của failing interaction.
- DependencyInsight outputs hoặc SBOM cho release.
- Không lưu tokens, PII hay credentials trong fixtures/logs.

### 17.2. Chạy baseline trên GitHub Actions

Snippet workflow minh họa cho source Boot3 đã có Wrapper:

~~~yaml
name: json-contract-tests

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  json-contract:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Execute JSON contract tests
        run: ./gradlew test --rerun-tasks
      - name: Upload JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: boot3-json-contracts
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore
~~~

Versions của GitHub Actions trong snippet là ví dụ, không phải khuyến nghị chọn latest; thực tế cần pin audited commit SHA phù hợp supply-chain policy. Candidate Boot4 cần source/test migration và workflow riêng hoặc job của branch candidate.

### 17.3. Không che lỗi bằng regenerate fixtures

Nếu Jackson3 serialize JSON khác, phân tích **tính tương thích thực**. Nếu breaking, giữ endpoint v1 hoặc thêm alias/version mới; không cập nhật expected v1 ngay trong cùng commit để làm suite xanh. Khi có waiver phải có owner/consumer impact/migration/sunset date.

## 18. Mutation tests: chứng minh tests sẽ đỏ khi contract bị phá

| Thay đổi trên branch sandbox | Test phát hiện |
| --- | --- |
| Xóa MoneyJsonComponent | JSON money number/whole baseline, MockMvc |
| Đổi @JsonProperty invoice_id → invoiceId | Frozen JSON + MVC |
| Bỏ @JsonInclude(NON_NULL) | Absent memo + frozen baseline |
| Thay JavaTime serializer ra epoch number | Instant string + MVC |
| Cho phép string "1999" thay integer | Invalid POST test |
| Bỏ @NotNull amount request | Missing amount POST test |
| Tăng enum state ngoài client cũ | Legacy enum negative test |
| Rename amount_cents thành amount_minor_units | Legacy missing amount test |
| Đổi amount_cents = 1999 thành 20 | Business value assertions |
| Chuyển Content-Type thành text/plain | MVC content-type assertion |
| Đổi missing resource từ 404 thành 200 | Error contract tests |
| Thêm mapper tùy ý trong @Configuration | Full mapper/MVC tests |
| Đổi Boot BOM, kéo lệch Jackson modules | Dependency insight + runtime tests |
| Update fixtures theo output mới | Không đáng coi là fix; cần review consumer contract |

Không phải mutation nào cũng được cả bốn test classes bắt: đó là lý do phải phối hợp đúng boundaries. Nếu một mutation làm client hỏng mà mọi tests vẫn xanh, cần bổ sung coverage.

## 19. Bài tập thực hành

**A.** Chạy lab trên Java17/Boot3.3.5, đọc report 26 tests và output JSON của InvoiceDto.

**B.** Bỏ `@JsonComponent` để JSON Money thành nested object; quan sát tests đỏ.

**C.** Bỏ `@JsonProperty("invoice_id")` và xem JSON field name đổi thế nào.

**D.** Bỏ `@JsonInclude(NON_NULL)`, quan sát memo null xuất hiện.

**E.** Tạo mapper riêng `new ObjectMapper()` và so Java Time/serializer behavior với injected mapper.

**F.** Chuyển Instant sang numeric timestamp trong sandbox, bảo vệ public contract ISO string.

**G.** Cho deserializer chấp nhận string amount; xem HTTP request negative test fail.

**H.** Dùng strict legacy reader để kiểm field additive memo, đối chiếu tolerant reader.

**I.** Gửi fixture có unknown enum ON_HOLD cho legacy DTO; thiết kế policy fallback.

**J.** Gửi null amount, kiểm wrapper Long + constructor validation fail-fast.

**K.** Giữ type number nhưng đổi amount value 1999 → 20; phân biệt parse correctness vs business semantics.

**L.** Chạy `dependencyInsight` cho Jackson databind/core/jsr310, ghi lại resolved versions.

**M.** Tạo một version override lệch trong sandbox và nghiên cứu vì sao link errors phát sinh; không merge override.

**N.** Đọc Boot4 Migration Guide, liệt kê imports của custom serializer cần đổi Jackson3.

**O.** Trên branch riêng, chuyển `@JsonComponent` sang `@JacksonComponent` + Jackson3 types và viết tests tương ứng.

**P.** Nếu dùng bridge, cấu hình `spring-boot-jackson2` và selected MVC converter; kiểm HTTP JSON giống baseline.

**Q.** Thử `spring.jackson.use-jackson2-defaults` trên Boot4 candidate và so JSON snapshot, không tự giả định mọi behavior giống.

**R.** Tạo OpenAPI schema diff và đối chiếu fixture type/nullability.

**S.** Thêm real HTTP RANDOM_PORT smoke và chạy legacy RestClient, nếu dự án có API clients ngoài Spring context.

**T.** Chuẩn bị canary/rollback plan khi JSON contract bắt buộc phải version.

## 20. Checklist kiểm thử serialization upgrade

- [ ] Biết Spring Boot version, Jackson major, JDK và Gradle Wrapper thực dùng?
- [ ] Đã đối chiếu vendor release/migration notes của đúng nhánh?
- [ ] Jackson core/databind/datatype modules được quản lý đồng bộ?
- [ ] Không pin một Jackson module ngoài BOM vô tình?
- [ ] Có audit libraries chưa hỗ trợ Jackson3?
- [ ] Có golden JSON fixtures của released contract?
- [ ] @JsonTest dùng đúng mapper/tester cho Boot version?
- [ ] Không dùng new ObjectMapper làm thay thế mapper Spring-managed không có lý do?
- [ ] Custom @JsonComponent hoặc @JacksonComponent thực sự được đăng ký?
- [ ] Null/absent, enum, dates, numbers và field names được assert?
- [ ] Data types của money được kiểm là number integer, không string/nested object?
- [ ] Có semantic assertions về cents/currency/timezone?
- [ ] Có tolerant và strict legacy consumer tests khi cần?
- [ ] Có JacksonTester write/parse, không chỉ DTO round-trip?
- [ ] Có MockMvc/HTTP converter tests cho public API?
- [ ] Có full-context tests kiểm custom mapper/profiles/wiring?
- [ ] Có request v1 không chứa optional field mới và vẫn hoạt động?
- [ ] Malformed JSON không gọi business service?
- [ ] Error status/body/content type được bảo vệ?
- [ ] Boot4 candidate có JsonMapper/Jackson3 đúng imports/modules?
- [ ] Annotations exception package được xử lý đúng?
- [ ] Nếu dùng Jackson2 bridge, module deprecated và sunset plan rõ?
- [ ] Preferred JSON mapper cho MVC/WebFlux được cấu hình theo transport?
- [ ] Module discovery, coercion và property paths có tests?
- [ ] CI thực sự chạy tests và lưu JUnit report, không chỉ UP-TO-DATE?
- [ ] Không auto-regenerate golden fixtures từ candidate?
- [ ] Không dùng public JSON snapshots chứa PII/secrets?
- [ ] Có contract diff và release/rollback plan nếu breaking?
- [ ] Các negative fixtures không bị hiểu nhầm thành evidence provider compatible?

## 21. Tài liệu chính thức

- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): ObjectMapper, Jackson2, @JsonComponent, module auto-config.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @JsonTest/JacksonTester và test slices.
- [Spring Boot 3.3 — JacksonTester API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/json/JacksonTester.html).
- [Spring Boot 4.0 — JSON](https://docs.spring.io/spring-boot/4.0/reference/features/json.html): Jackson3 default, Jackson2 bridge, preferred mapper properties.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): group/package migrations, modules, @JacksonComponent, starters.
- [Spring Boot 4.0 — Testing](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): JSON test slice, Jackson3 and deprecated Jackson2 support.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html).
- [Jackson 3 Migration Guide](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0).
- [Gradle — Dependency Reports](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.10.2/user-guide/).
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259).
- [RFC 3339 — Timestamps](https://www.rfc-editor.org/rfc/rfc3339).

**Ghi nhớ:** Khi thay Jackson, JSON tester hoặc serialization dependencies, hãy kiểm **wire JSON mà clients thực nhận**, không chỉ biên dịch và deserialize DTO mới. Spring Boot 3.x dùng ObjectMapper/JacksonTester Jackson2; Spring Boot 4.0 ưu tiên JsonMapper/Jackson3, có bridge deprecated cho Jackson2. Kết hợp frozen fixtures, @JsonTest, MockMvc, full-context wiring và legacy consumer assertions để bảo vệ backward compatibility. Mọi thay đổi phá hợp đồng cần được versioned và có migration rõ ràng.
