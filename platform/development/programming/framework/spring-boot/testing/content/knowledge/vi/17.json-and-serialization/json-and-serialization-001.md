# `@JsonTest` và phạm vi hỗ trợ serialization trong Spring Boot

Khi xây REST API, ứng dụng thường chuyển qua lại giữa **đối tượng Java** và **JSON**. Các lỗi có thể xảy ra ngay ở lớp chuyển đổi: đổi `productId` thành `product_id` sai, bỏ sót trường, xuất `null` ngoài hợp đồng, biến ngày tháng thành timestamp, serialize số tiền sai hoặc quên đăng ký custom serializer. Những lỗi này có thể được phát hiện **mà không cần khởi động HTTP server hay database**.

Spring Boot cung cấp **`@JsonTest`**, một **test slice** tập trung vào JSON serialization/deserialization. Nó nạp JSON mapper và các thành phần tùy biến JSON có liên quan, đồng thời hạn chế những bean ngoài phạm vi. Với **Jackson** trên Spring Boot 3.5, thường dùng `JacksonTester<T>` để kiểm `write` và `parseObject`; khi dùng thư viện khác có `GsonTester<T>`, `JsonbTester<T>`; `BasicJsonTester` hỗ trợ assertion trên JSON string.

Bài này hướng dẫn **cơ chế, phạm vi nạp bean, cách kiểm hợp đồng JSON nghiêm ngặt, ví dụ Java 17+ hoàn chỉnh với `@JsonComponent`, những gì `@JsonTest` không chứng minh** và các điểm khác biệt giữa Spring Boot 3.x và 4.x.

## 1. JSON serialization/deserialization chứng minh điều gì?

Có hai chiều dữ liệu:

```text
                        serialize / write
Java record / DTO --------------------------------> JSON text
        ^                                              |
        |                                              |
        +----------------------------------------------+
                       deserialize / read
```

**Serialization** là việc chuyển một Java value thành JSON. **Deserialization** là chuyển JSON thành Java type mong đợi. Một hợp đồng API có thể quy định tên trường, kiểu, độ chính xác của số, định dạng ngày giờ, điều kiện xuất hiện field, thứ tự phần tử **trong array**, error policy và khả năng đọc dữ liệu từ phiên bản cũ.

| Rủi ro | Bằng chứng phù hợp trong `@JsonTest` |
|---|---|
| Đổi tên trường theo wire contract | `@JsonProperty`, assert JSON key chính xác |
| `null` được bỏ hay được giữ? | `@JsonInclude`, assert trường **vắng mặt**, không chỉ có giá trị null |
| `LocalDate`, `Instant`, zone/offset | `@JsonFormat` và mapper/module phù hợp, assert chuỗi JSON và round-trip |
| Dữ liệu số `int`, `long`, `BigDecimal` | Assert JSON number/string, precision và giá trị parse trở lại |
| Custom serializer/deserializer | Test `@JsonComponent` hoặc Jackson `Module` thực sự được đăng ký trong slice |
| Array có đúng thứ tự | So sánh JSON array bằng chế độ so sánh phù hợp |
| JSON input đúng/sai cú pháp | `parseObject` thành công hoặc ném lỗi parse |
| Unknown field/required/default semantics | Test mapper config thực tế và behavior của DTO |
| HTTP status, `Content-Type`, routing, security | **Ngoài phạm vi `@JsonTest`**; cần `@WebMvcTest`/`@WebFluxTest` hoặc `@SpringBootTest` |
| Controller → service → repository hoặc DB | **Ngoài phạm vi `@JsonTest`**; cần kiểm thử nhiều tầng |

Một bài `@JsonTest` “xanh” chỉ khẳng định **mapping JSON** trong configuration đã nạp. Nó không bảo đảm controller đang trả đúng DTO, security filter cho phép request, hoặc API đang dùng đúng Jackson mapper khi hệ thống có nhiều mapper tự cấu hình.

## 2. `@JsonTest` thực sự tạo context như thế nào?

Import trong **Spring Boot 3.5**:

```java
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

@JsonTest
class ProductJsonTest {
    @Autowired
    JacksonTester<ProductPayload> json;
}
```

Đoạn này chỉ là khung test; `ProductPayload` và test methods sẽ được định nghĩa đầy đủ bên dưới.

**Cơ chế:**

1. Annotation có `SpringExtension`/bootstrapper của Spring Boot để JUnit Jupiter chạy test trong **Spring TestContext**.
2. `@OverrideAutoConfiguration(enabled = false)` giới hạn auto-configuration thông thường; `@ImportAutoConfiguration` và các cấu hình JSON cần thiết được chọn theo classpath.
3. Với Jackson 2 trong Boot 3.5, các bean như **`ObjectMapper`**, những `@JsonComponent` và Jackson **`Module`** phù hợp được cấu hình/đăng ký.
4. Spring Boot tạo các JSON tester fields để `@Autowired JacksonTester<ProductPayload>` hoạt động, nếu mapper liên quan hiện diện.
5. Bộ lọc component scan của slice thường **không nạp `@Service`, `@Repository`, `@Controller` thông thường** chỉ vì chúng ở cùng package.

**`@JsonTest` không khởi động embedded web server**. Nó cũng không nạp một application graph đầy đủ như `@SpringBootTest`. Vì vậy, nếu serializer phụ thuộc vào một service bình thường, nó có thể thiếu bean trong slice: hãy xem có thực sự cần dependency đó cho JSON mapping, hoặc cung cấp config nhỏ có chủ đích bằng `@Import`/`@TestConfiguration`. Đừng import toàn bộ hệ thống chỉ để test một JSON field.

### Mức hỗ trợ tùy thư viện JSON

| Thư viện | Thành phần được dùng | Tester |
|---|---|---|
| **Jackson 2**, Spring Boot 3.5 | `com.fasterxml.jackson.databind.ObjectMapper`; `@JsonComponent`; Jackson `Module` | `JacksonTester<T>` |
| **Gson** khi có dependency phù hợp | `com.google.gson.Gson` cùng cấu hình liên quan | `GsonTester<T>` |
| **JSON-B** khi có provider/dependency phù hợp | `jakarta.json.bind.Jsonb` | `JsonbTester<T>` |
| **JSON string bất kỳ** | Không buộc phải biết Java DTO hay mapper | `BasicJsonTester` |
| **Jackson 3 / Boot 4.x** | API, mapper và custom component mới của dòng Boot 4 | Xem tài liệu và dependency đúng version; không giả định ví dụ Jackson 2 chuyển nguyên xi |

Các tester là tiện ích **AssertJ-based**, không đồng nhất với Spring MVC `HttpMessageConverter`. Việc có `JacksonTester` không đồng nghĩa một HTTP endpoint đã được đăng ký.

### Lưu ý `@AutoConfigureJsonTesters`

`@JsonTest` đã bao gồm cấu hình JSON testers. Annotation `@AutoConfigureJsonTesters` cho phép điều chỉnh hành vi này, ví dụ `enabled = false` khi không muốn tạo tester fields. **Tắt testers không phải tắt toàn bộ JSON mapper**; phần cấu hình mapper phụ thuộc vào các auto-configuration được nạp. Thông thường không cần gắn annotation này nếu chỉ đang viết bài test serialization cơ bản.

## 3. Bộ API kiểm JSON phổ biến

Với Jackson trong Spring Boot 3.5:

```java
@Autowired
private JacksonTester<ProductPayload> json;

// Object -> JSON content
var actual = json.write(payload);

// JSON string -> Object
ProductPayload restored = json.parseObject(content);
```

Đây là đoạn minh họa đặt trong một `@JsonTest`; `payload` và `content` được khai báo bởi test method. `write`/`parseObject` có thể ném `IOException` khi mapping lỗi.

Các assertions thường dùng:

| Phép kiểm | Ví dụ | Ý nghĩa |
|---|---|---|
| Toàn bộ JSON theo hợp đồng | `assertThat(json.write(value)).isEqualToJson("expected.json")` | So với resource JSON; mặc định so sánh **lenient** |
| Không cho field dư | `isEqualToJson(expected, JSONCompareMode.STRICT)` | Chế độ nghiêm ngặt: không cho extra fields; array order quan trọng |
| JSONPath tồn tại và là string | `hasJsonPathStringValue("@.product_id")` | Kiểm type và sự hiện diện ở path |
| Đọc một giá trị cụ thể | `extractingJsonPathStringValue("@.product_id").isEqualTo("BOOK-1")` | Kiểm nội dung của field |
| Trường không xuất hiện | `doesNotHaveJsonPath("@.note")` | Phân biệt **absent** với `"note":null` |
| Parse object | `assertThat(json.parseObject(input)).isEqualTo(expectedDto)` | Kiểm deserialization theo object equality |
| Input sai JSON | `assertThrows(IOException.class, () -> json.parseObject("{"))` | Parser từ chối cú pháp JSON lỗi |

**`JSONCompareMode.STRICT` không bắt buộc các key trong một JSON object phải cùng thứ tự ký tự**, vì thứ tự object keys không phải contract chuẩn; nhưng thứ tự phần tử của JSON array là có ý nghĩa. Chế độ mặc định lenient trong JSONAssert có thể bỏ qua **field dư** và có thể không ràng buộc thứ tự array. Khi test API contract yêu cầu không thêm field ngoài dự kiến, dùng so sánh strict có chủ đích.

Khi so sánh JSON bằng raw string `assertEquals("{...}", output)`, test có thể fail chỉ vì **thứ tự object keys hoặc khoảng trắng** dù JSON hợp lệ tương đương. Đối với contract JSON thông thường, ưu tiên structural JSON assertion; raw string chỉ phù hợp khi **chính xác từng byte** là rủi ro cần kiểm (ví dụ payload ký số/canonical JSON theo chuẩn riêng).

## 4. Ví dụ Java 17+ hoàn chỉnh: DTO, ngày tháng, null và custom serializer

Ta có response DTO cho một sản phẩm và hóa đơn:

- `ProductPayload` có field Java `productId`, nhưng key trên JSON phải là **`product_id`**.
- `availableOn` là `LocalDate` được serialize dạng **`yyyy-MM-dd`**.
- `note = null` phải **không xuất hiện** trong JSON vì `@JsonInclude(NON_NULL)`.
- `InvoiceView` chứa `Money`; một **`@JsonComponent` serializer** cố tình đổi `Money(150000)` thành chuỗi JSON **`"150000 VND"`** để minh họa custom mapping.

Format money thành string là ví dụ kỹ thuật, **không phải khuyến nghị wire contract production**: API tài chính thường cần trường tiền và đơn vị tiền rõ ràng, quy định precision và rounding. Trong hệ thống thật, phải thiết kế contract trước rồi mới viết serializer.

### 4.1. Cấu trúc dự án

```text
json-slice-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/json/
    │   ├── JsonLearningApplication.java
    │   ├── ProductPayload.java
    │   ├── Money.java
    │   ├── InvoiceView.java
    │   └── MoneySerializer.java
    └── test/
        ├── java/com/example/json/
        │   ├── ProductPayloadJsonTest.java
        │   └── InvoiceJsonTest.java
        └── resources/com/example/json/
            └── product-expected.json
```

### 4.2. Maven POM với Jackson và JUnit Jupiter

File **`pom.xml`** — cố định ở **Spring Boot 3.5.0** để các tên import Jackson 2 và Spring Boot test API thống nhất:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>json-slice-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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
```

`spring-boot-starter-json` có Jackson 2 và module Java Time thích hợp trong dòng Boot 3.5. `spring-boot-starter-test` đưa JUnit Jupiter, AssertJ và các dependency kiểm JSON cần thiết vào test scope. Maven parent quản lý bộ phiên bản tương thích: **không** tự pin một bản Jackson lẻ làm lệch BOM.

Không cần `spring-boot-starter-web`, HTTP server hay `MockMvc`: mục tiêu chỉ là **serialization/deserialization**. File main application dưới đây giúp Spring Boot tìm cấu hình gốc của slice.

### 4.3. Spring Boot configuration gốc

File **`src/main/java/com/example/json/JsonLearningApplication.java`**:

```java
package com.example.json;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLearningApplication {
}
```

Không cần `main` để chạy JUnit tests; `@JsonTest` có thể tìm `@SpringBootApplication` từ package của test. Nếu muốn chạy như một ứng dụng thực bằng `spring-boot:run`, cần thêm `main` và một application entrypoint tương ứng, nhưng **điều đó không cần để kiểm JSON**.

### 4.4. DTO có key đặc biệt, ngày và null policy

File **`src/main/java/com/example/json/ProductPayload.java`**:

```java
package com.example.json;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProductPayload(
        @JsonProperty("product_id") String productId,
        long priceVnd,
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
        LocalDate availableOn,
        String note) {
}
```

`@JsonProperty("product_id")` đổi **wire key** nhưng không đổi tên Java accessor `productId()`. `@JsonInclude(NON_NULL)` chỉ bỏ các field có giá trị **Java null** khi serialize; nó không có nghĩa field `note` không bao giờ được deserializing, cũng không phải một quy tắc validation. `LocalDate` dùng định dạng ngày thuần, không có timezone như `Instant`.

Với dữ liệu `new ProductPayload("BOOK-1", 120_000L, LocalDate.of(2026,11,8), null)`, hợp đồng JSON là:

```json
{
  "product_id": "BOOK-1",
  "priceVnd": 120000,
  "availableOn": "2026-11-08"
}
```

Ở đây `"note"` **vắng mặt hẳn**, không phải `"note": null`.

### 4.5. Fixture JSON lưu như một file resource

File **`src/test/resources/com/example/json/product-expected.json`**:

```json
{
  "product_id": "BOOK-1",
  "priceVnd": 120000,
  "availableOn": "2026-11-08"
}
```

Với `JacksonTester`, `isEqualToJson("product-expected.json")` tìm resource tương ứng với **package của test class**. Đặt fixture đúng `src/test/resources/com/example/json/` tránh lỗi “resource not found”. Dùng file fixture khi JSON dài, có cấu trúc nested hoặc cần review thay đổi hợp đồng rõ trong Git. Với vài field đơn giản, inline JSON string vẫn có thể dễ đọc.

### 4.6. Test serialize, JSONPath, deserialize và lỗi cú pháp

File **`src/test/java/com/example/json/ProductPayloadJsonTest.java`**:

```java
package com.example.json;

import java.io.IOException;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.skyscreamer.jsonassert.JSONCompareMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@JsonTest
class ProductPayloadJsonTest {
    @Autowired
    private JacksonTester<ProductPayload> json;

    private ProductPayload fixture() {
        return new ProductPayload(
                "BOOK-1", 120_000L, LocalDate.of(2026, 11, 8), null);
    }

    @Test
    void serializesExactPublicJsonContract() throws IOException {
        assertThat(json.write(fixture()))
                .isEqualToJson("product-expected.json", JSONCompareMode.STRICT);
    }

    @Test
    void serializesNamesTypesAndOmitsNullNote() throws IOException {
        var result = json.write(fixture());

        assertThat(result)
                .hasJsonPathStringValue("@.product_id")
                .doesNotHaveJsonPath("@.note");

        assertThat(result)
                .extractingJsonPathStringValue("@.availableOn")
                .isEqualTo("2026-11-08");

        assertThat(result)
                .hasJsonPathNumberValue("@.priceVnd");
    }

    @Test
    void deserializesJsonToEquivalentJavaRecord() throws IOException {
        String input = """
                {
                  "product_id":"BOOK-1",
                  "priceVnd":120000,
                  "availableOn":"2026-11-08",
                  "note":null
                }
                """;

        assertThat(json.parseObject(input)).isEqualTo(fixture());
    }

    @Test
    void rejectsMalformedJsonSyntax() {
        assertThrows(IOException.class,
                () -> json.parseObject("{\"product_id\":"));
    }
}
```

**Vì sao test này có ý nghĩa:**

- Test **strict** kiểm fixture theo cấu trúc JSON, không chấp nhận field lạ hoặc field thiếu; **không yêu cầu object keys có cùng thứ tự ký tự**.
- Test JSONPath kiểm key đổi tên, type của `priceVnd`, format ngày và việc `note` **không có mặt**.
- Test parse đọc một JSON thực tế và so sánh **record equality**, chứng minh `@JsonProperty`, date module và nullable field.
- Test sai cú pháp chứng minh parser báo lỗi. **Nó không tự chứng minh API sẽ trả HTTP 400** khi client gửi JSON đó; bước biến parser exception thành HTTP status do web layer phụ trách.

Java 17 hỗ trợ **text blocks** (`"""`) và `record` dùng trong ví dụ. Các API `JacksonTester`, `JSONCompareMode` và `AssertJ` ở đây được chọn theo bộ thư viện Spring Boot 3.5.

### 4.7. Custom serializer bằng `@JsonComponent`

Để chứng minh `@JsonTest` có hỗ trợ **custom mapping được Spring Boot tìm qua component scan**, ta tạo hai record và một serializer.

File **`src/main/java/com/example/json/Money.java`**:

```java
package com.example.json;

public record Money(long amountVnd) {
}
```

File **`src/main/java/com/example/json/InvoiceView.java`**:

```java
package com.example.json;

public record InvoiceView(String invoiceId, Money total) {
}
```

File **`src/main/java/com/example/json/MoneySerializer.java`**:

```java
package com.example.json;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public final class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(Money value, JsonGenerator generator,
                          SerializerProvider provider) throws IOException {
        generator.writeString(value.amountVnd() + " VND");
    }
}
```

`@JsonComponent` trên `MoneySerializer` làm serializer này trở thành **thành phần JSON đặc biệt** được Spring Boot 3.5 đăng ký vào Jackson. Nếu chỉ có một class `@Service` thông thường, `@JsonTest` không mặc định scan nó; nhưng `@JsonComponent` được filter của JSON slice cho phép.

**Lưu ý:** Ví dụ mới tạo serializer **một chiều** cho `Money`, chưa tạo deserializer tương ứng. Vì thế test dưới đây chỉ assert **serialization của `InvoiceView`**, không hứa parse chuỗi `"150000 VND"` trở lại `Money`. Nếu API thật yêu cầu round-trip, phải tạo `JsonDeserializer<Money>` tương thích và thêm test parse; chỉ test `write` sẽ bỏ sót lỗi đối xứng.

File **`src/test/java/com/example/json/InvoiceJsonTest.java`**:

```java
package com.example.json;

import java.io.IOException;

import org.junit.jupiter.api.Test;
import org.skyscreamer.jsonassert.JSONCompareMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class InvoiceJsonTest {
    @Autowired
    private JacksonTester<InvoiceView> json;

    @Test
    void registeredJsonComponentSerializerChangesMoneyWireFormat()
            throws IOException {
        var invoice = new InvoiceView("INV-1", new Money(150_000L));

        assertThat(json.write(invoice))
                .isEqualToJson(
                        "{\"invoiceId\":\"INV-1\",\"total\":\"150000 VND\"}",
                        JSONCompareMode.STRICT);
    }
}
```

Nếu custom serializer không được nạp, `Money` thông thường sẽ serialize như một object có `amountVnd`, khiến test **FAIL** thay vì trả chuỗi đã định nghĩa. Như vậy test chứng minh đúng **cấu hình mapping tùy biến trong JSON slice**, không chỉ constructor hoặc getter Java.

### 4.8. Lệnh chạy và kết quả dự kiến

Ở thư mục có `pom.xml`:

```bash
mvn test
```

Nếu project có Maven Wrapper:

```bash
./mvnw test
```

Hoặc chỉ chạy đúng hai class:

```bash
mvn -Dtest=ProductPayloadJsonTest,InvoiceJsonTest test
```

Windows dùng `mvnw.cmd` khi có wrapper hoặc `mvn` nếu Maven đã cài. Với đúng code và fixtures trên, có **5 phương thức `@Test`**: 4 ở `ProductPayloadJsonTest`, 1 ở `InvoiceJsonTest`. Kết quả kỳ vọng **5 tests pass, 0 failures** trên Java 17 và bộ Spring Boot 3.5 được chọn. Đây là test JUnit, **không có stdout nghiệp vụ cố định**; output của Maven Surefire/IDE thay đổi theo version và cấu hình.

**Không chạy `javac` riêng rồi `java ProductPayloadJsonTest`**: nó phụ thuộc Spring TestContext, Jackson, AssertJ và JUnit test runner trên classpath. Lệnh Maven dùng BOM để lấy các dependency tương thích.

## 5. Phạm vi cấu hình JSON: module, customizer, mixin và dependency bị loại

Một ứng dụng Spring Boot có thể cấu hình JSON theo nhiều lớp:

| Thành phần | Hành vi trong `@JsonTest` |
|---|---|
| `@JsonComponent` của Boot 3.x | Thường được scan và đăng ký cho Jackson 2 mapper |
| Jackson `Module` bean | Là một dạng bean mà filter JSON slice cho phép, có thể góp serializer/deserializer |
| Annotation trên DTO như `@JsonProperty`, `@JsonFormat`, `@JsonInclude` | Áp dụng khi mapper xử lý type, ngay cả khi DTO không phải Spring bean |
| `@JsonMixin` và cấu hình tương ứng (khi version hỗ trợ) | Cần kiểm nó được nạp/đăng ký đúng theo dòng Boot đang dùng |
| `Jackson2ObjectMapperBuilderCustomizer` hoặc mapper customizer trong `@Configuration` thường | **Không giả định tự được scan** vào slice; có thể cần `@Import` hoặc test config riêng |
| `@Service`, `@Repository`, controller và database infrastructure | **Không nạp mặc định** chỉ vì có JSON test |
| `HttpMessageConverter`, request/response filters, `@ControllerAdvice` | Không được test chỉ bởi serialization slice; cần web/slice tương ứng |

Ví dụ khi JSON mapping phụ thuộc một Jackson Module tự viết:

```java
@JsonTest
@Import(MyJacksonConfiguration.class)
class CustomMappingTest {
    @Autowired
    JacksonTester<MyDto> json;
}
```

**Đây là snippet cấu trúc, không chạy độc lập** vì `MyJacksonConfiguration` và `MyDto` giả định. Dùng `@Import` khi cấu hình cần kiểm không nằm trong tập mặc định của slice; đừng tự cho rằng mọi `@Configuration` có `ObjectMapper` bean trong production được tự quét vào test.

Một rủi ro quan trọng: **mapper trong `@JsonTest` có thể khác mapper dùng ở một endpoint thật**, ví dụ ứng dụng có nhiều `ObjectMapper`, MVC/WebFlux có converter riêng, hoặc profile HTTP cấu hình khác. Nếu yêu cầu là “API `GET /orders` trả đúng JSON”, cần thêm **web test** để chứng minh endpoint thực sự sử dụng mapping mong muốn.

### `@JsonTest` và Java record

Record là Java type hợp lệ cho Jackson khi version tương thích; việc serialize/deserializing dựa trên property names/accessors và annotations trên record components. Nhưng **record không tự thực thi Bean Validation**. Để kiểm `@NotBlank`, `@Valid` hoặc cơ chế lỗi API, hãy viết unit test validator hoặc `@WebMvcTest`/`@WebFluxTest` có validation infrastructure.

Nếu có bất biến nghiệp vụ trong record constructor (ví dụ `priceVnd` không được âm), JSON parse có thể gọi constructor và ném exception được bọc bởi mapper; song `@JsonTest` **không quyết định** HTTP status của lỗi đó.

## 6. Strict vs lenient, absent vs null, object vs array order

Các lựa chọn assertion này ảnh hưởng trực tiếp đến chất lượng test contract:

### 6.1. Lenient comparison

```java
assertThat(json.write(value)).isEqualToJson(expected);
```

Ở API JSON tester của Spring Boot 3.5, mặc định so sánh JSON theo cách **lenient** (mức độ dung sai theo JSONAssert). Ví dụ một object thực có thêm field `debug` vẫn có thể được chấp nhận nếu expected không nhắc tới nó. Hợp lý khi test chỉ quan tâm một tập field; **không phù hợp** nếu API contract cấm field ngoài danh sách.

### 6.2. Strict comparison

```java
assertThat(json.write(value))
        .isEqualToJson(expected, JSONCompareMode.STRICT);
```

Đoạn trên là snippet dùng trong class có `JacksonTester` và import `org.skyscreamer.jsonassert.JSONCompareMode`. Strict không cho field dư và kiểm array order. Nhưng JSON object keys vẫn được so theo **thuộc tính/tên**, không theo thứ tự key trong text; đó là hành vi đúng của JSON structure.

Nếu contract yêu cầu thứ tự phần tử của `items`, hãy assert JSON array theo đúng thứ tự. Còn nếu contract cho phép phần tử không có thứ tự, không nên ép order chỉ vì test fixture đang sắp xếp theo một cách tình cờ.

### 6.3. Absent và explicit `null` không tương đương

Hai JSON này khác về hợp đồng:

```json
{"product_id":"BOOK-1"}
```

```json
{"product_id":"BOOK-1","note":null}
```

`doesNotHaveJsonPath("@.note")` kiểm **không tồn tại key**. `doesNotHaveJsonPathValue("@.note")` có thể diễn đạt điều khác tùy cách JSONPath hiểu `null`, nên khi mục tiêu thật là **field vắng mặt**, chọn `doesNotHaveJsonPath` rõ ràng hơn. Tương tự, `hasJsonPath` không giống `hasJsonPathValue`: key có mặt với giá trị `null` không có nghĩa nó có non-null value.

### 6.4. Number, BigDecimal và JSON representation

JSON có **number**, nhưng client/language khác nhau có giới hạn kiểu số riêng. Test `priceVnd` là JSON number không tự đảm bảo số rất lớn được JavaScript client biểu diễn chính xác. Với tiền, cân nhắc `BigDecimal`, quy ước đơn vị nhỏ nhất hoặc string với precision rules, rồi assert đúng contract phía consumer. Không “sửa” vấn đề tiền bằng cách dùng `double` vô điều kiện.

### 6.5. LocalDate, Instant và timezone

`LocalDate` biểu diễn **ngày không múi giờ**. `Instant` biểu diễn **mốc thời gian UTC**. Với `Instant`, format, precision, offset và timezone của mapper có thể ảnh hưởng wire format; đừng chỉ assert `contains("2026")`. Dùng fixture cụ thể, clock cố định và timezone policy rõ ràng. Khi test date/time, nên kiểm **cả chiều serialize và deserialize**, không chỉ output.

## 7. JSON mapping không đồng nghĩa HTTP request body hợp lệ

Một lỗi thường gặp là viết:

```java
@JsonTest
class OrderJsonTest {
    // parseObject("{...}") thành công
}
```

Rồi kết luận rằng `POST /orders` luôn trả 201. Điều đó **không có cơ sở**, vì HTTP còn trải qua:

```text
HTTP request
    |
    +--> router/controller mapping
    +--> security/authentication/authorization
    +--> Content-Type, accept negotiation, body decoding
    +--> JSON deserialization
    +--> Bean Validation (@Valid, constraints)
    +--> business service, transaction, repository
    +--> response serialization + HTTP status
```

`@JsonTest` chỉ tập trung vào **JSON mapping**. Muốn kiểm controller có nhận `@RequestBody`, validate hay trả 400/415/422 theo contract, dùng `@WebMvcTest` + MockMvc hoặc `@WebFluxTest` + WebTestClient, với collaborator được cung cấp đúng. Muốn chứng minh Spring DI nối nhiều tầng và database, dùng `@SpringBootTest` cùng test fixtures phù hợp. Nếu cần kiểm HTTP socket/embedded server, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

**Không nên dùng `@SpringBootTest` cho mọi DTO** nếu `@JsonTest` có đủ bằng chứng cần thu: tạo toàn bộ context là tốn chi phí và có thể làm test lỗi vì external dependencies không liên quan. Ngược lại, chỉ `@JsonTest` cho một API nhạy cảm có thể thiếu coverage ở biên HTTP.

## 8. Phương án dùng Gson, JSON-B hoặc không khởi tạo Spring

`@JsonTest` hỗ trợ các mapper đang có trên classpath phù hợp, không chỉ Jackson. Tuy nhiên **annotation và module của từng thư viện khác nhau**: `@JsonProperty`, `@JsonComponent` và Jackson `Module` **không tự có ý nghĩa với Gson hoặc JSON-B**.

### GsonTester

Đoạn minh họa nếu dự án thêm `com.google.code.gson:gson` theo BOM/compatibility:

```java
@JsonTest
class GsonMappingTest {
    @Autowired
    GsonTester<MyDto> json;
}
```

`MyDto` là type giả định; snippet chưa có test method. Khi app dùng Gson, hãy kiểm naming strategy và custom TypeAdapter của Gson **thật sự được nạp**; đừng copy Jackson annotations rồi mong Gson hiểu hết.

### JsonbTester

Nếu dùng Jakarta JSON-B và có **JSON-B provider**, có thể dùng:

```java
@JsonTest
class JsonbMappingTest {
    @Autowired
    JsonbTester<MyDto> json;
}
```

Đây cũng là snippet, không chạy độc lập nếu thiếu provider, DTO và imports. Cấu hình JSON-B có khác biệt với Jackson; test phải phản ánh đúng mapper mà app sử dụng.

### BasicJsonTester

Khi chỉ cần kiểm một JSON string, `BasicJsonTester` cung cấp các assertion JSON mà không cần một Java DTO/mapper cụ thể. Nó thích hợp với fixture hoặc JSON do một thư viện khác trả ra; không tự chứng minh **Java object ↔ JSON** theo Jackson.

### Test Jackson trực tiếp bằng unit test

Trong test thuần không dùng `@JsonTest`, có thể khởi tạo và cấu hình `ObjectMapper` riêng hoặc dùng `JacksonTester.initFields(...)` với mapper đã chuẩn bị. Ưu điểm là nhanh, độc lập Spring context; nhược điểm là **không tự chứng minh cấu hình auto-configuration Spring Boot** như `@JsonComponent` được đăng ký trong ứng dụng. Chọn theo phạm vi mục tiêu, không theo sở thích annotation.

## 9. Khác biệt Spring Boot 3.5 và 4.x, đặc biệt Jackson 3

**Ví dụ runnable trong bài cố định ở Spring Boot 3.5.0**, sử dụng Jackson **2**, `com.fasterxml.jackson.*`, `ObjectMapper` và `@JsonComponent` theo các package của dòng này.

Trong **Spring Boot 4.x**, Jackson **3** là mapper mặc định ở các dòng mới; thư viện và API đã thay đổi (ví dụ `JsonMapper`, Jackson `@JacksonComponent`/module mới), trong khi hỗ trợ Jackson 2 cũ có tính chuyển tiếp/deprecated ở một số bản. **Không thể kết luận chỉ cần nâng version parent là mọi `JsonSerializer`, custom module và import Jackson 2 đều giữ nguyên hành vi.** Cần xem tài liệu Boot 4 đúng patch, migration guide và BOM, đặc biệt nếu code dùng custom serializers.

Những việc phải xác nhận khi nâng cấp:

1. `spring-boot-starter-json` và JSON mapper thực sự được chọn là Jackson 3 hay Jackson 2; không pin cả hai vô ý.
2. Annotation serializer và API `JsonMapper`/`ObjectMapper` đang dùng đúng dòng.
3. `@JsonTest` và tester loại tương ứng có trong test module/classpath đã chọn; không giả định mọi import Boot 3.5 giống Boot 4.
4. `@JsonComponent`/Jackson `Module` cũ đã chuyển sang `@JacksonComponent`/module mới khi cần.
5. So sánh **JSON contract thực tế** trước/sau nâng cấp, nhất là date/time, null, enums, number, unknown fields và custom mapping.
6. Bổ sung một web-slice/integration test nếu cần xác nhận **HTTP controller thật** sử dụng đúng mapper mới.

Ví dụ một test `@JsonTest` chỉ có `JacksonTester<Dto>` mà không bao giờ kiểm custom `@JsonComponent` có thể vẫn xanh sau khi serializer bị bỏ quên trong quá trình chuyển version. Hãy giữ test **dạng output contract** như ví dụ `InvoiceJsonTest`.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `JacksonTester<T>` không inject được | Thiếu Jackson/spring-test-json phù hợp hoặc slice/test bootstrap sai | Kiểm `spring-boot-starter-json`, `spring-boot-starter-test`, annotation và version |
| JSON fixture báo không tìm thấy | Resource đặt sai package/path | `src/test/resources/<package-path>/expected.json` cùng package với test |
| Mapper tạo field `productId` thay vì `product_id` | Chưa có naming strategy/`@JsonProperty` đúng | Assert strict wire key, dùng annotation/config phù hợp |
| JSON thừa `"note": null` | Null inclusion policy khác mong đợi | `@JsonInclude(NON_NULL)`, `doesNotHaveJsonPath` |
| Date thành array/timestamp | Module Java Time hoặc format khác | Dùng dependency/module/config đúng, kiểm `@JsonFormat` và output |
| String JSON order khác làm test fail | So sánh raw text cứng nhắc | So JSON theo cấu trúc, strict khi cần |
| Test lenient pass dù có field nhạy cảm bị xuất ra | Extra fields được cho qua | `JSONCompareMode.STRICT`, test field absent rõ |
| `@JsonComponent` không có hiệu lực | Sai mapper, không scan/import được serializer hoặc version khác | Kiểm `@JsonTest` và mapper trong context, test output cụ thể |
| Deserialization thất bại nhưng serialization pass | Chỉ có serializer mà không có deserializer, thiếu constructor/property mapping | Kiểm cả chiều `write` và `parseObject` khi contract yêu cầu |
| Bean `@Service` không có trong JSON slice | Slice cố ý exclude service bình thường | `@Import` config nhỏ hoặc chuyển cấp test phù hợp |
| JSON slice pass nhưng HTTP trả 415/400 | Chưa test Content-Type, `@RequestBody`, validation hoặc exception mapping | `@WebMvcTest`/`@WebFluxTest` hoặc integration |
| Test parse malformed JSON nhưng expected HTTP status không xuất hiện | `@JsonTest` không tạo HTTP endpoint | Tách parser test và web-layer test |
| Boot 4 không nhận custom serializer kiểu Boot 3 | Jackson 2/3 API và annotation thay đổi | Xem migration theo version, điều chỉnh module và regression contract tests |
| Suite chậm dù chỉ test DTO | Dùng `@SpringBootTest` cho mọi JSON mapping | `@JsonTest` hoặc unit test mapper theo nhu cầu |
| Fixture có dữ liệu không ổn định | Thời gian, ID ngẫu nhiên, locale/default zone | Dùng giá trị cố định và cấu hình deterministic |

## 11. Checklist trước khi hoàn thành

- [ ] Tôi biết mục tiêu là **Java ↔ JSON mapping** hay **HTTP response/request behavior**.
- [ ] Test JSON mapping được tách khỏi web/database khi không cần những tầng đó.
- [ ] `@JsonTest` nạp mapper thư viện thực tế ứng dụng sử dụng.
- [ ] Bean `@JsonComponent`/Jackson `Module` hoặc custom config quan trọng đã được nạp đúng.
- [ ] Nếu mapping có thêm service dependency, tôi cân nhắc scope thay vì import cả application.
- [ ] Serialization test kiểm đúng field names, field types, date/time, null policy và nested values.
- [ ] Khi contract yêu cầu, tôi dùng **strict JSON comparison**, không chỉ match một JSONPath.
- [ ] Khi cần absent field, tôi dùng `doesNotHaveJsonPath` thay vì kiểm `null` không rõ nghĩa.
- [ ] Nếu cần round-trip, tôi có test **cả serialization và deserialization**.
- [ ] Input malformed/unknown fields, locale, timezone và numeric precision được kiểm theo yêu cầu.
- [ ] File fixture trong `src/test/resources` nằm đúng vị trí và được review như hợp đồng API.
- [ ] Test có assertion tiêu biểu với `@JsonComponent` để phát hiện mapping tùy biến bị bỏ.
- [ ] Tôi biết `@JsonTest` **không kiểm** controller mapping, HTTP status, security, repository.
- [ ] Với Spring Boot 4.x, tôi kiểm lại **Jackson 3 vs Jackson 2, module, imports và tester**.
- [ ] Đã chạy đúng build/test runner hoặc kiểm chính xác dependency/behavior của dự án.

**Kết luận:** `@JsonTest` là **test slice cho serialization/deserialization**, không phải công cụ kiểm thử toàn bộ REST API. Nó phù hợp để chứng minh mapper, DTO annotations, JSON contract, custom serializer và parse behavior với context gọn. Khi rủi ro thuộc HTTP hoặc business workflow, bổ sung `@WebMvcTest`, `@WebFluxTest` hoặc `@SpringBootTest` thay vì suy rộng kết quả `@JsonTest`.

### Tài liệu chính thức

- [Spring Boot 3.5 — Auto-configured JSON Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — `@JsonTest` Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html)
- [Spring Boot 3.5 — Test slices auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 3.5 — JSON mapper configuration](https://docs.spring.io/spring-boot/3.5/reference/features/json.html)
- [Spring Boot 4.x — JSON support và Jackson 3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Spring Boot — `JsonContentAssert` Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/json/JsonContentAssert.html)
