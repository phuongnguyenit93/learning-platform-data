# Kiểm thử JSON với JacksonTester, JsonbTester, GsonTester và BasicJsonTester

> **Module:** Spring Boot – testing  
> **Nhóm:** JSON và serialization  
> **Chủ đề:** JacksonTester, JsonbTester, GsonTester hoặc BasicJsonTester theo thư viện  
> **Mục tiêu:** Chọn đúng JSON tester theo mapper đang dùng, kiểm tra serialize/deserialize và JSON contract bằng những assertion có giá trị, phân biệt `@JsonTest` với unit test tự khởi tạo tester, biết giới hạn và khác biệt giữa Jackson, Gson, Jakarta JSON-B và chuỗi JSON thuần.

## 1. Vấn đề thật sự cần kiểm thử

Trong một ứng dụng Spring Boot, chuyển một Java object thành JSON không chỉ là gọi `toString()`. Dữ liệu qua ranh giới API hoặc message broker phải tuân theo một hợp đồng, ví dụ:

```json
{
  "order_id": 502,
  "recipient": "buyer@example.test",
  "quantity": 3,
  "shipOn": "2026-06-17"
}
```

Một DTO có thể bị serialize sai theo rất nhiều cách:

- `order_id` biến thành `orderId` vì annotation bị bỏ hoặc mapper khác được dùng.
- `shipOn` trở thành timestamp/array thay vì chuỗi ngày `yyyy-MM-dd`.
- Trường `recipient` bị null hoặc nhầm với địa chỉ khác.
- `quantity` bị serialize thành chuỗi `"3"` thay vì số `3`.
- Một trường nội bộ, mật khẩu hoặc token vô tình lộ ra trong JSON.
- Bỏ thiếu required field khi deserialize, dùng giá trị mặc định không mong muốn.
- JSON hợp lệ về cú pháp nhưng sai ngữ nghĩa: currency, đơn vị, precision, timezone, enum naming.
- Test chỉ so sánh Java object với chính nó, không kiểm tra output JSON thực tế.

Một test chất lượng nên xác minh **cả hai chiều** nếu hệ thống có nhu cầu:

1. **Serialization:** Java object → JSON có đúng tên trường, kiểu dữ liệu, giá trị, cấu trúc và các trường bị loại trừ?
2. **Deserialization:** JSON từ client/provider → Java object có đọc đúng required/optional fields, enum, ngày giờ và kiểu số?
3. **Negative contract:** JSON sai cấu trúc, thiếu trường bắt buộc hoặc có giá trị không hợp lệ được xử lý theo policy nào?
4. **Mapper configuration:** Có dùng cùng ObjectMapper/Gson/Jsonb và module/naming rules như ứng dụng thực tế không?

Spring Boot cung cấp bốn trợ thủ chính dưới package `org.springframework.boot.test.json` để viết assertion theo cách gần với hợp đồng JSON hơn là so sánh chuỗi thủ công.

## 2. Chọn tester theo thư viện, không theo tên tùy thích

| Tester | Engine dùng để serialize/parse object | Input phù hợp | Cách dùng điển hình |
| --- | --- | --- | --- |
| **`JacksonTester<T>`** | Jackson `ObjectMapper` | Java DTO/record dùng Jackson, `@JsonProperty`, `@JsonFormat`, Jackson modules | `@JsonTest` + `@Autowired JacksonTester<Dto>` |
| **`GsonTester<T>`** | Google `Gson` | DTO do Gson serialize, `@SerializedName`, `TypeAdapter` | `@JsonTest` khi có Gson hoặc unit test `GsonTester.initFields` |
| **`JsonbTester<T>`** | Jakarta JSON Binding `Jsonb` | DTO dùng `@JsonbProperty`, adapter/visibility theo JSON-B | `@JsonTest` khi có provider hoặc unit test `JsonbTester.initFields` |
| **`BasicJsonTester`** | Không tự chuyển Java object qua mapper; nhận JSON bytes/text/file | JSON đã được tạo bởi bất kỳ nguồn nào, raw HTTP response, message text | `new BasicJsonTester(getClass())` + `json.from(payload)` |

Chúng có chung một nhóm tính năng assertion JSON vì Spring Boot tích hợp AssertJ, JSONAssert và JsonPath. Nhưng **tester không tự thay đổi JSON engine mà production đang dùng**. Nếu API thực chạy bằng Jackson mà test dùng GsonTester, bạn có thể bỏ sót cấu hình Jackson-specific của chính API đó.

### 2.1. Câu hỏi quyết định

- Ứng dụng Spring MVC/WebFlux chuẩn có Jackson ở classpath và DTO dùng `com.fasterxml.jackson.annotation.*`? Thường chọn **JacksonTester**.
- Hệ thống thật chủ động dùng Gson (`com.google.gson.Gson`)? Chọn **GsonTester**, cấp đúng `Gson` hoặc Boot auto-configuration tương ứng.
- Hệ thống dựa trên Jakarta JSON-B (`jakarta.json.bind.Jsonb`)? Chọn **JsonbTester**, có JSON-B API **và implementation** như Eclipse Yasson.
- Bạn chỉ có payload JSON từ webhook, file fixture, response hoặc producer mà chưa cần tạo object? Chọn **BasicJsonTester**.
- Muốn kiểm tra request/response HTTP thực qua controller? Tester JSON chỉ là **một phần**; cần thêm `MockMvc`, `WebTestClient` hoặc HTTP client integration test tùy ranh giới.

**Không có “tester mạnh nhất cho mọi tình huống”.** Cách chọn đúng là theo contract và engine. Ví dụ Java record được Jackson serialize tốt trong Spring Boot 3.5; nếu dùng Gson version hoặc JSON-B provider không hỗ trợ cùng kiểu record/annotation semantics, phải kiểm tra khả năng của engine ấy thay vì giả định tương đương.

## 3. `@JsonTest` thực sự auto-configure cái gì?

`@JsonTest` là một **test slice** thuộc `spring-boot-test-autoconfigure`. Nó thiết lập phần cấu hình JSON cần kiểm tra, không nạp toàn bộ business application.

Với các thư viện tương ứng có mặt và điều kiện auto-configuration thỏa mãn, nó có thể nạp:

- Jackson `ObjectMapper`, những Jackson `Module` và `@JsonComponent` phù hợp.
- Gson `Gson` và customizations khi classpath/config hỗ trợ.
- JSON-B `Jsonb` với provider tương thích khi dependencies thích hợp.
- Các JSON testers có thể được inject vào fields.
- Cơ chế assertion JSON/JSONPath từ test dependencies.

Nó **không** tự dựng HTTP listener, chạy toàn bộ controllers/services/repositories, gọi network hay khởi động một full Spring Boot application context như `@SpringBootTest`.

Ví dụ:

```java
@JsonTest
class ShippingNoticeJsonTest {
    @Autowired
    JacksonTester<ShippingNotice> json;
}
```

Đây là **đoạn cấu hình rút gọn**; project runnable ở phần 5 sẽ có đầy đủ imports và test methods. Annotation `@JsonTest` cùng phần hỗ trợ tester của Spring Boot tự khởi tạo field `JacksonTester<ShippingNotice>` đúng generic type, vì vậy không cần tự viết `new JacksonTester(...)`.

### 3.1. Vai trò của `@AutoConfigureJsonTesters`

`@AutoConfigureJsonTesters` cho phép tùy chỉnh việc đăng ký JSON testers; attribute `enabled` mặc định là true. Khi `@JsonTest` hoạt động bình thường, thường **không cần thêm** annotation này.

```java
@JsonTest
@AutoConfigureJsonTesters(enabled = true)
class ExampleJsonTest {
    // Tester fields được khởi tạo khi có mapper thích hợp.
}
```

Đây chỉ là mẫu annotation, không phải test độc lập. Đừng nhầm `@AutoConfigureJsonTesters` với việc thêm engine dependency: nếu project không có Gson hoặc provider JSON-B thì annotation không tự tải thư viện từ Maven.

### 3.2. `@JsonTest` dùng cấu hình mapper thật hay mapper mới?

Điểm mạnh của `@JsonTest` là nó thường sử dụng **bean mapper có cấu hình Spring Boot** trong JSON slice: thuộc tính `spring.jackson.*`, `@JsonComponent`, các Module/Customizer phù hợp với test context. Điều này khác:

```java
ObjectMapper mapper = new ObjectMapper();
```

Một `ObjectMapper` tự tạo chưa chắc có `JavaTimeModule`, naming strategy, serializers, visibility rules, mix-ins hoặc quy tắc null như app. Test với mapper mặc định có thể pass trong khi HTTP JSON của app khác, hoặc ngược lại.

Tuy nhiên, slice không nhất thiết scan/import **mọi custom `@Configuration`** trong ứng dụng. Nếu Jackson Module được khai báo trong một configuration bị loại khỏi slice, hãy `@Import` đúng module/config nhỏ đó, hoặc dùng full-context/integration test để xác minh bean wiring. Không vì thiếu module mà vội chuyển tất cả JSON tests thành `@SpringBootTest`.

### 3.3. Có nhiều JSON engine trên classpath thì sao?

`@JsonTest` có thể có support cho nhiều engine nếu chúng có mặt, nhưng JSON engine được HTTP converter của ứng dụng lựa chọn theo dependencies, auto-configuration và custom settings. Một test `GsonTester` pass không tự chứng minh MVC dùng Gson; tương tự test `JsonbTester` không chứng minh message producer thực dùng JSON-B.

Muốn kiểm tra **serialization thực sự ở HTTP boundary**, phải kiểm tra MVC/WebFlux converter và response body trong một test HTTP phù hợp. Muốn tránh phức tạp trong bài học, dự án chạy được bên dưới dùng Jackson + Basic, còn Gson/JSON-B được trình bày thành **hai extension opt-in** với dependencies rõ ràng.

## 4. Những assertion JSON có giá trị

Giả sử một tester trả về `JsonContent<T>`:

```java
assertThat(json.write(dto))
        .isEqualToJson("expected-shipping-notice.json");
```

`isEqualToJson` so sánh **JSON có cấu trúc**, không phải so sánh hai chuỗi từng ký tự với `String#equals`. Cách này thường không khóa test vào whitespace hoặc thứ tự trường object. Tên `.json` là fixture resource (xem layout phần 5).

```java
assertThat(json.write(dto))
        .extractingJsonPathStringValue("@.recipient")
        .isEqualTo("buyer@example.test");
```

Đoạn trên kiểm tra trực tiếp một trường consumer cần dùng. Cú pháp `@.recipient` tương ứng root JSON trong API này (có thể thấy các ví dụ JSONPath dùng ký hiệu `$` ở nơi khác; hãy dùng cùng cách mà Spring Boot test API hỗ trợ).

Một số dạng assertion hữu ích:

| Điều muốn chứng minh | Lựa chọn assertion |
| --- | --- |
| JSON tương đương fixture | `assertThat(json.write(dto)).isEqualToJson("expected.json")` |
| Có field string và đúng giá trị | `extractingJsonPathStringValue("@.field").isEqualTo(...)` |
| Có số và đúng giá trị | `extractingJsonPathNumberValue("@.quantity")` + assert với `Number` |
| Round-trip Java object | `assertThat(json.parseObject(payload)).isEqualTo(expected)` |
| Không leak trường bí mật | Parse thành JSON tree/map rồi assert field không tồn tại |
| Array đúng thứ tự khi thứ tự là contract | So sánh list/array JSONPath hoặc JSON tree theo thứ tự |
| JSON lỗi cú pháp | Kiểm tra exception của mapper/tester, không chấp nhận parse âm thầm |
| Request/response HTTP trả đúng status/header | `MockMvc`/`WebTestClient` bổ sung cho tester |

**Đừng chỉ kiểm tra “JSON hợp lệ”.** Một JSON hợp lệ vẫn có thể chứa field sai hoặc bỏ sót field bắt buộc.

### 4.1. JSON numbers: tránh nhầm `Integer`, `Long`, `Double` và `BigDecimal`

JSON có kiểu `number` nhưng không định nghĩa riêng `int`/`long`/`double`. Sau JsonPath extraction, một value có thể là một đối tượng `Number` cụ thể tùy parser và kích thước của số. Vì vậy so sánh máy móc:

```java
assertThat(json.write(dto))
        .extractingJsonPathNumberValue("@.quantity")
        .isEqualTo(3L);
```

có thể giòn nếu giá trị được trả dưới dạng `Integer(3)` chứ không phải `Long(3)`. Khi contract chỉ yêu cầu trị số nguyên:

```java
assertThat(json.write(dto))
        .extractingJsonPathNumberValue("@.quantity")
        .satisfies(number ->
                assertThat(number.intValue()).isEqualTo(3));
```

Hai đoạn trên là **mẫu assertion nhúng vào test**; cần `assertThat` static import và biến `json`/`dto`. Với số tiền, **không** đổi sang `intValue()` vì mất thập phân. Dùng `BigDecimal`/decimal semantics trong domain, kiểm tra scale/precision theo hợp đồng và JSON tree khi cần. Kiểm tra giá trị JSON là `3`, không phải chuỗi `"3"`, cũng là một assertion độc lập khi type là contract.

### 4.2. Missing khác null, null khác chuỗi rỗng

Ba JSON sau là **ba contract khác nhau**:

```json
{"order_id":502}
```

```json
{"order_id":502,"note":null}
```

```json
{"order_id":502,"note":""}
```

Nếu client phân biệt “không cập nhật” với “xóa dữ liệu”, missing và explicit null có thể ảnh hưởng lớn. Đừng chỉ viết `contains("note")` trên chuỗi; parse JSON rồi kiểm tra `node.has("note")`, `node.hasNonNull("note")` hoặc thuộc tính cụ thể. Với Gson/JSON-B, hãy dùng JSON tree/parser tương ứng hoặc AssertJ JSONPath; không phụ thuộc Jackson nếu app cố tình không dùng nó.

### 4.3. JSON object field order và array order

`{"a":1,"b":2}` và `{"b":2,"a":1}` thường tương đương theo ngữ nghĩa JSON object. Nhưng array `[1,2]` và `[2,1]` là hai thứ tự khác nhau.

Nếu test cần bảo vệ thứ tự item, đừng dùng phép so sánh không phân biệt order của collection. Có thể parse JSON thành tree và dùng `assertThat(node.get("items").get(0)...).isEqualTo(...)`, hoặc JSONPath array/list assertion. Nếu bên nhận yêu cầu canonical JSON bytes cho chữ ký, thứ tự/whitespace/encoding thật sự là contract và phải test **serialized bytes** theo quy chuẩn đó.

### 4.4. Các kiểm tra chỉ dựa trên `toString()` thường vô nghĩa

Đoạn này không kiểm thử Jackson:

```java
ShippingNotice notice = ...;
assertThat(notice.toString()).contains("buyer@example.test");
```

Nó kiểm tra `record.toString()`, hoàn toàn độc lập với `ObjectMapper`. Test tốt phải đi qua `json.write(notice)` hoặc mapper thật để quan sát JSON output. Tương tự, `assertThat(json.parseObject(json.write(dto).getJson())).isEqualTo(dto)` **chỉ** là round-trip: hai chiều cùng mắc một lỗi mapping có thể vẫn pass. Kết hợp expected fixture hoặc field-level contract **độc lập**.

## 5. Dự án Spring Boot/Java 17 chạy được: JacksonTester + BasicJsonTester

Dự án chính dùng **Java 17, Spring Boot 3.5.16, Maven, Jackson và AssertJ**. Các test JSON không khởi động HTTP server hoặc kết nối database/Internet, ngoại trừ việc Maven có thể cần tải dependencies trong lần đầu.

### 5.1. Cấu trúc tệp

```text
json-tester-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jsonlab/
    │   │   ├── JsonTesterLabApplication.java
    │   │   └── ShippingNotice.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/com/example/jsonlab/
        │   ├── ShippingNoticeJsonTest.java
        │   ├── RawJsonContractTest.java
        │   └── ManualJacksonTesterTest.java
        └── resources/com/example/jsonlab/
            └── expected-shipping-notice.json
```

Mọi Java type public trong file trùng tên; tất cả class cùng package `com.example.jsonlab`. File fixture trong `src/test/resources/com/example/jsonlab/` để được tìm theo package của test class. Dự án không cần controller/repository vì bài toán là **JSON contract**, không phải HTTP mapping.

### 5.2. `pom.xml`

```xml
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
    <artifactId>json-tester-lab</artifactId>
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

- `spring-boot-starter-json` có Jackson 2.x và những modules thông dụng như Java Time (theo dependency management của Boot).
- `spring-boot-starter-test` có JUnit Jupiter, AssertJ, JSONAssert, JsonPath và Spring Boot test support.
- **Không cần** `spring-boot-starter-web` để test serialization: không dùng controller/server.
- Khi chuyển ví dụ sang ứng dụng web thật, `spring-boot-starter-web` thường đã kéo theo Jackson. Tránh thêm trùng dependencies không cần thiết.

### 5.3. Application root và DTO

```java
// src/main/java/com/example/jsonlab/JsonTesterLabApplication.java
package com.example.jsonlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonTesterLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonTesterLabApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/jsonlab/ShippingNotice.java
package com.example.jsonlab;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

public record ShippingNotice(
        @JsonProperty("order_id") long orderId,
        String recipient,
        int quantity,
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate shipOn,
        @JsonInclude(JsonInclude.Include.NON_NULL) String note) {
}
```

**JSON contract của `ShippingNotice`:**

| Java component | JSON field | Semantics |
| --- | --- | --- |
| `orderId` | `order_id` | Annotation Jackson đổi tên field |
| `recipient` | `recipient` | Chuỗi email giả |
| `quantity` | `quantity` | JSON number, không phải string |
| `shipOn` | `shipOn` | Chuỗi ngày ISO-like theo pattern đã chỉ định |
| `note` null | Field `note` **bị bỏ** | `@JsonInclude(NON_NULL)` trên component |

`@JsonProperty`, `@JsonFormat` và `@JsonInclude` đều là **Jackson annotations**. Chúng không bắt buộc được Gson/JSON-B hiểu theo cùng cách. Phần 9/10 sẽ dùng một POJO trung tính, không giả định engine nào diễn giải các Jackson annotations.

### 5.4. `application.yml`

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: json-tester-lab
```

Không cần `server.port`, database hoặc production secret. `@JsonTest` chỉ nạp JSON slice; ứng dụng chính cũng có thể khởi động như một application không-web nếu chạy `main`, nhưng điều đó không cần cho test.

### 5.5. Fixture JSON độc lập

Tệp `src/test/resources/com/example/jsonlab/expected-shipping-notice.json`:

```json
{
  "order_id": 502,
  "recipient": "buyer@example.test",
  "quantity": 3,
  "shipOn": "2026-06-17"
}
```

Fixture do người viết test định nghĩa theo hợp đồng, **không phải** được tạo bằng cách gọi chính `json.write(actual)` rồi lưu lại mà không review. Nếu một bug serializer đổi `order_id` thành `orderId`, test phải fail.

### 5.6. `ShippingNoticeJsonTest.java` — `@JsonTest` dùng Jackson thật

```java
// src/test/java/com/example/jsonlab/ShippingNoticeJsonTest.java
package com.example.jsonlab;

import java.time.LocalDate;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class ShippingNoticeJsonTest {

    @Autowired
    private JacksonTester<ShippingNotice> json;

    @Autowired
    private ObjectMapper mapper;

    private ShippingNotice sample() {
        return new ShippingNotice(
                502L,
                "buyer@example.test",
                3,
                LocalDate.of(2026, 6, 17),
                null);
    }

    @Test
    void writesJsonContractFromRealJacksonConfiguration()
            throws Exception {
        assertThat(json.write(sample()))
                .isEqualToJson("expected-shipping-notice.json");

        assertThat(json.write(sample()))
                .extractingJsonPathStringValue("@.recipient")
                .isEqualTo("buyer@example.test");
    }

    @Test
    void keepsNumbersNumericAndDoesNotLeakNullNote()
            throws Exception {
        JsonNode actual = mapper.readTree(
                json.write(sample()).getJson());

        assertThat(actual.path("order_id").asLong())
                .isEqualTo(502L);
        assertThat(actual.path("quantity").isIntegralNumber())
                .isTrue();
        assertThat(actual.path("quantity").asInt())
                .isEqualTo(3);
        assertThat(actual.has("note")).isFalse();
        assertThat(actual.has("orderId")).isFalse();
    }

    @Test
    void deserializesKnownJsonIntoIndependentExpectedRecord()
            throws Exception {
        String payload = """
                {
                  "order_id": 502,
                  "recipient": "buyer@example.test",
                  "quantity": 3,
                  "shipOn": "2026-06-17"
                }
                """;

        ShippingNotice actual = json.parseObject(payload);

        assertThat(actual).isEqualTo(sample());
    }

    @Test
    void preservesUnicodeAndEscaping() throws Exception {
        ShippingNotice notice = new ShippingNotice(
                503L,
                "người.dùng@example.test",
                1,
                LocalDate.of(2026, 6, 18),
                "Chào \"bạn\"!");

        String jsonText = json.write(notice).getJson();
        ShippingNotice roundTrip = json.parseObject(jsonText);

        assertThat(roundTrip).isEqualTo(notice);
        assertThat(mapper.readTree(jsonText)
                .path("note").asText())
                .isEqualTo("Chào \"bạn\"!");
    }
}
```

**Giải thích từng assertion:**

1. Fixture so sánh cả cấu trúc JSON với giá trị expected độc lập.
2. JSONPath kiểm tra trực tiếp recipient mà consumer sẽ đọc.
3. `mapper.readTree` xác định `quantity` có dạng numeric, field `note` null không được serialize và `orderId` không bị lộ dưới tên Java.
4. `parseObject` kiểm tra JSON → record theo chính giá trị expected, gồm `LocalDate`.
5. Round-trip Unicode/escaping là test **bổ sung**, không thay thế fixture độc lập. Bởi hai chiều có thể cùng sai nhưng vẫn tạo object giống ban đầu.

**Lưu ý về đoạn code Java:** Trong actual Java source, literal `"Chào \"bạn\"!"` biểu thị chuỗi chứa dấu nháy kép trong nội dung. Với file Markdown, dấu backslash trong code fence phải được giữ nguyên như bên trên khi dán sang `.java`.

### 5.7. `RawJsonContractTest.java` — `BasicJsonTester` không cần mapper

```java
// src/test/java/com/example/jsonlab/RawJsonContractTest.java
package com.example.jsonlab;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.BasicJsonTester;

import static org.assertj.core.api.Assertions.assertThat;

class RawJsonContractTest {

    private final BasicJsonTester json =
            new BasicJsonTester(getClass());

    @Test
    void validatesRawPayloadWithoutDeserializingJavaDto() {
        String raw = """
                {
                  "status": "ACCEPTED",
                  "count": 2,
                  "items": [
                    {"sku":"SKU-1"},
                    {"sku":"SKU-2"}
                  ]
                }
                """;

        assertThat(json.from(raw))
                .extractingJsonPathStringValue("@.status")
                .isEqualTo("ACCEPTED");

        assertThat(json.from(raw))
                .extractingJsonPathNumberValue("@.count")
                .satisfies(number ->
                        assertThat(number.intValue()).isEqualTo(2));

        assertThat(json.from(raw))
                .extractingJsonPathStringValue("@.items[1].sku")
                .isEqualTo("SKU-2");
    }

    @Test
    void comparesSemanticJsonRatherThanWhitespace() {
        String raw = """
                {"status":"ACCEPTED","count":2}
                """;

        assertThat(json.from(raw))
                .isEqualToJson("""
                        {
                          "count": 2,
                          "status": "ACCEPTED"
                        }
                        """);
    }
}
```

`BasicJsonTester#from(CharSequence)` nhận **JSON đã tồn tại**. Nó có thể đọc JSON từ String, byte array, file, stream hoặc resource, nhưng không có `write(SomeDto)` hoặc `parseObject(...)` giống các typed marshal testers. Vì vậy nó rất phù hợp cho test webhook JSON/raw payload. Cùng lúc, nó **không chứng minh Jackson/Gson/JSON-B mapper đã xây JSON chính xác**, trừ khi JSON đầu vào thực sự được tạo bởi mapper đó ở code bạn đang test.

### 5.8. `ManualJacksonTesterTest.java` — dùng không có `@JsonTest`

```java
// src/test/java/com/example/jsonlab/ManualJacksonTesterTest.java
package com.example.jsonlab;

import java.time.LocalDate;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

class ManualJacksonTesterTest {

    private JacksonTester<ShippingNotice> json;

    @BeforeEach
    void setup() {
        ObjectMapper mapper = new ObjectMapper()
                .findAndRegisterModules();
        JacksonTester.initFields(this, mapper);
    }

    @Test
    void serializesWithExplicitMapperOutsideSpringContext()
            throws Exception {
        ShippingNotice notice = new ShippingNotice(
                502L, "buyer@example.test", 3,
                LocalDate.of(2026, 6, 17), null);

        assertThat(json.write(notice))
                .isEqualToJson("expected-shipping-notice.json");
    }
}
```

`JacksonTester.initFields(this, mapper)` đi qua những field typed tester trên test instance và khởi tạo chúng dựa trên mapper truyền vào. `findAndRegisterModules()` giúp mapper tự phát hiện những Jackson modules ở classpath (bao gồm JavaTime module khi có) trong ví dụ này.

**Khác biệt quan trọng:** manual mapper không tự bảo đảm dùng **mọi** Spring Boot customization của production `ObjectMapper`. Nếu contract phụ thuộc property naming/visibility/module do context tạo, dùng `@JsonTest` hoặc inject **mapper bean thực**; manual example tốt cho phép test riêng không cần Spring.

### 5.9. Cách chạy và số test của dự án chính

Từ thư mục `json-tester-lab` (có `pom.xml`):

```bash
java -version
mvn -version

mvn test
mvn -Dtest=ShippingNoticeJsonTest test
mvn -Dtest=RawJsonContractTest test
mvn -Dtest=ManualJacksonTesterTest test
```

Dự án chính có **7 phương thức JUnit `@Test`**: `ShippingNoticeJsonTest` có **4**, `RawJsonContractTest` có **2**, và `ManualJacksonTesterTest` có **1**: **4 + 2 + 1 = 7**.

Kết quả mong đợi: các assertions pass khi file và dependencies được khai báo đúng. Maven/Surefire/Spring Boot có thể in thứ tự tests, thời gian chạy hoặc log khác nhau; không có stdout cố định để hard-code. Không cần `curl` vì không có HTTP endpoint trong ví dụ.

## 6. `JacksonTester`: mapper-aware contract, có thể dùng JSON view

### 6.1. Khi nào nên chọn?

Chọn `JacksonTester<T>` khi production dùng Jackson và DTO có một trong các yếu tố:

- `@JsonProperty` đổi tên field.
- `@JsonIgnore`/`@JsonInclude` quyết định field nào xuất hiện.
- `@JsonFormat`, `JavaTimeModule`, enum format hoặc timezone.
- Custom `JsonSerializer`/`JsonDeserializer`, mix-in hoặc Jackson `Module`.
- `@JsonView` nếu API có các view công khai/nội bộ.
- Cấu hình từ `spring.jackson.*` hoặc `Jackson2ObjectMapperBuilderCustomizer` của ứng dụng Boot 3.x.

Với Jackson, engine và annotation phải khớp. Một test dùng Gson trên cùng DTO có thể **bỏ qua** `@JsonProperty("order_id")` và phát `orderId`, đó không phải “GsonTester hỏng” mà là khác biệt thực sự của mapper.

### 6.2. `JacksonTester#forView`

Nếu ứng dụng sử dụng `@JsonView`, `JacksonTester` có `forView(ViewClass.class)` để kiểm tra đúng view. Ví dụ **minh họa**, không thuộc dự án chạy được vì cần thêm DTO và view annotations:

```java
class Views {
    interface Public {}
    interface Internal extends Public {}
}

record Profile(
        @JsonView(Views.Public.class) String displayName,
        @JsonView(Views.Internal.class) String internalNote) {
}

// Trong test có JacksonTester<Profile> json:
assertThat(json.forView(Views.Public.class)
        .write(new Profile("Lan", "review-only")))
        .isEqualToJson("""
                {"displayName":"Lan"}
                """);
```

Snippet cần imports `com.fasterxml.jackson.annotation.JsonView` và AssertJ `assertThat`. Hành vi inclusion của field không đánh dấu view còn tùy cấu hình `DEFAULT_VIEW_INCLUSION`. Với dữ liệu nhạy cảm, kiểm tra schema xuất theo đúng security contract, không dựa vào ví dụ giản lược để coi view là biện pháp auth.

### 6.3. Typed marshal tester và resources

`JacksonTester<T>` kế thừa `AbstractJsonMarshalTester<T>`, cung cấp `write(T)`, `parse(String)`, `parseObject(String)`, `read(String)` và các overload. Phân biệt:

- `write(dto)`: serialize Java DTO, trả `JsonContent<T>` để AssertJ kiểm tra JSON.
- `parse(jsonString)`: deserialize và trả `ObjectContent<T>` để assert object.
- `parseObject(jsonString)`: deserialize và trả trực tiếp `T`.
- `read("resource.json")` / các overload đọc resource: hữu ích khi input JSON lớn nằm trong fixture.
- `JsonContent#getJson()`: lấy raw serialized text khi cần kiểm tra byte/text syntax hoặc parse JSON tree.

Tên file fixture thường resolve tương đối với test class/package; nên đặt resources đúng package, đặc biệt khi chuyển package test hoặc tạo module mới.

## 7. `BasicJsonTester`: đúng cho JSON từ nguồn bất kỳ

`BasicJsonTester` phù hợp khi không có Java DTO để serialize, chẳng hạn:

- Một callback/webhook gửi nguyên chuỗi JSON.
- Một API client trả response `String` hoặc `byte[]`.
- Một producer viết JSON qua library custom hoặc template engine.
- Một file snapshot/fixture được đọc bởi hệ thống khác.
- Kiểm tra JSONPath/JSONAssert mà không quyết định engine Jackson/Gson/JSON-B.

Sử dụng trực tiếp:

```java
BasicJsonTester json = new BasicJsonTester(getClass());

assertThat(json.from("""
        {"event":"order.created","orderId":502}
        """))
        .extractingJsonPathStringValue("@.event")
        .isEqualTo("order.created");
```

Đây là mẫu nhúng trong test method, cần `assertThat` static import. Nếu data đã tồn tại dưới dạng bytes, có thể dùng `json.from(byte[])`. Khi truyền một `String` **kết thúc bằng `.json`**, API có thể coi đó là resource name thay vì raw JSON; để tránh nhầm, dùng nội dung JSON rõ dạng `{...}`/`[...]` hoặc overload resource tường minh.

### 7.1. Không biến BasicJsonTester thành “parser Java object”

Điểm khác biệt cơ bản:

```text
JacksonTester<ShippingNotice> / GsonTester<T> / JsonbTester<T>
              Java object ↔ JSON text

BasicJsonTester
              JSON text/bytes/file → JsonContent<Object> → assertions
```

`BasicJsonTester` không mang generic DTO type, không biết annotation serialization của DTO và không tự tạo entity từ JSON. Nếu test yêu cầu deserialize JSON thành domain object, hãy chọn typed tester theo engine hoặc dùng mapper thật.

### 7.2. Chọn JSONPath hay structural equality?

- JSONPath tốt khi chỉ một số fields là contract, hoặc JSON chứa metadata động.
- Structural equality tốt khi toàn bộ payload/schema là contract ổn định và fixture được review.
- Đối với JSON chứa timestamp/UUID động, hãy assert format, presence, correlation và relationship thay vì snapshot cố định.
- Đối với JSON có trường bí mật, assert **sự vắng mặt** bằng parser/tree thay vì chỉ kiểm tra một field public.
- Với arrays, phải xác định order có thuộc contract hay không.

## 8. GsonTester: khi ứng dụng thực sự dùng Gson

Gson do Google cung cấp, import `com.google.gson.Gson` và các annotations như `@SerializedName`. `GsonTester<T>` dùng `Gson` để marshal/unmarshal Java object, còn phần assertion JSON hoạt động tương tự các typed testers.

**Không cần thêm Gson vào dự án Jackson nếu production không dùng nó.** Để chạy đoạn mở rộng dưới đây trên cùng Maven project phần 5, thêm dependency ở **test scope**:

```xml
<dependency>
    <groupId>com.google.code.gson</groupId>
    <artifactId>gson</artifactId>
    <scope>test</scope>
</dependency>
```

Phiên bản thường do Spring Boot BOM quản lý. Gson ở test scope đủ cho ví dụ unit test; trong ứng dụng production thật dùng Gson cần khai báo dependency ở scope thích hợp và cấu hình HTTP converter/mapper tương ứng.

### 8.1. POJO trung tính làm fixture chung cho Gson và JSON-B

Tạo file `src/test/java/com/example/jsonlab/GatewayReceipt.java`:

```java
// GatewayReceipt.java
package com.example.jsonlab;

public class GatewayReceipt {
    private String code;
    private int attempts;

    public GatewayReceipt() {
    }

    public GatewayReceipt(String code, int attempts) {
        this.code = code;
        this.attempts = attempts;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public int getAttempts() {
        return attempts;
    }

    public void setAttempts(int attempts) {
        this.attempts = attempts;
    }
}
```

POJO có no-arg constructor, getters/setters và fields đơn giản để Gson/JSON-B đều dễ xử lý. Không dùng Jackson record `ShippingNotice` làm “bằng chứng” rằng mọi engine đều có cùng support record/annotations.

### 8.2. `GsonTesterTest.java` — manual initFields, không Spring

```java
// src/test/java/com/example/jsonlab/GsonTesterTest.java
package com.example.jsonlab;

import com.google.gson.Gson;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.GsonTester;

import static org.assertj.core.api.Assertions.assertThat;

class GsonTesterTest {

    private GsonTester<GatewayReceipt> json;

    @BeforeEach
    void setup() {
        Gson gson = new Gson();
        GsonTester.initFields(this, gson);
    }

    @Test
    void serializesUsingGson() throws Exception {
        GatewayReceipt receipt =
                new GatewayReceipt("OK", 2);

        assertThat(json.write(receipt))
                .isEqualToJson("""
                        {"code":"OK","attempts":2}
                        """);
    }

    @Test
    void deserializesUsingGson() throws Exception {
        GatewayReceipt actual = json.parseObject("""
                {"code":"DONE","attempts":3}
                """);

        assertThat(actual.getCode()).isEqualTo("DONE");
        assertThat(actual.getAttempts()).isEqualTo(3);
    }
}
```

Vì đây là pure JUnit test, `GsonTester.initFields(this, gson)` chủ động cấp engine vào tester, không cần `@JsonTest`. Test xác nhận JSON đúng theo Gson defaults của ví dụ, nhưng **không** tự kiểm tra `GsonBuilderCustomizer`/`spring.gson.*` trong ứng dụng thật.

### 8.3. Khi dùng `@JsonTest` cho Gson

Trong application thực sự dùng Gson, khi dependencies và auto-configuration Gson sẵn sàng, có thể:

```java
@JsonTest
class GsonContractSliceTest {
    @Autowired
    GsonTester<GatewayReceipt> json;

    // @Test kiểm tra json.write và json.parseObject...
}
```

Đây là mẫu annotation, không phải tệp runnable trong dự án chính. Một `@JsonTest` sẽ có ích khi cần xác nhận mapper do Boot tạo. Không giả định thêm Gson dependency làm MVC/WebFlux **bắt buộc** chuyển sang Gson; HTTP converter có lựa chọn/cấu hình riêng.

### 8.4. Gson khác Jackson ở điểm nào?

- Annotation đổi tên field: Gson dùng `@SerializedName("order_id")`; Jackson dùng `@JsonProperty("order_id")`.
- Naming/exclusion/field visibility có thể khác.
- Java Time, polymorphic mapping, null inclusion và adapter behavior có thể khác.
- Gson serializes fields theo engine mặc định, còn Jackson thường dựa properties/annotations.
- Một DTO pass GsonTester chưa chứng minh tương thích với `ObjectMapper`.

**Ví dụ khác biệt annotation (chỉ minh họa):**

```java
class Example {
    @SerializedName("order_id")
    long orderId;
}
```

Đoạn này cần import `com.google.gson.annotations.SerializedName`; không đặt thêm vào source chính nếu không dùng Gson. Nó biểu thị contract riêng của Gson. Với JSON-B, annotation tương ứng thuộc namespace `jakarta.json.bind.annotation`.

## 9. JsonbTester: với Jakarta JSON Binding (JSON-B)

JSON-B là API cho Java object ↔ JSON. Spring Boot có hỗ trợ auto-configuration khi **JSON-B API và implementation tương thích** nằm trên classpath. Một implementation thông dụng là Eclipse Yasson.

Để chạy phần mở rộng trong project, thêm vào `pom.xml`:

```xml
<dependency>
    <groupId>jakarta.json.bind</groupId>
    <artifactId>jakarta.json.bind-api</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.eclipse</groupId>
    <artifactId>yasson</artifactId>
    <scope>test</scope>
</dependency>
```

`Yasson` cần một Jakarta JSON-P provider tương thích ở runtime (thường được kéo qua dependency graph của provider). Nếu gặp lỗi kiểu “provider not found”, kiểm tra dependency tree/phiên bản và bổ sung provider JSON-P phù hợp theo tài liệu Yasson; không nhầm JSON-B API với implementation.

### 9.1. `JsonbTesterTest.java` — tạo/đóng Jsonb rõ ràng

```java
// src/test/java/com/example/jsonlab/JsonbTesterTest.java
package com.example.jsonlab;

import jakarta.json.bind.Jsonb;
import jakarta.json.bind.JsonbBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.JsonbTester;

import static org.assertj.core.api.Assertions.assertThat;

class JsonbTesterTest {

    private Jsonb jsonb;
    private JsonbTester<GatewayReceipt> json;

    @BeforeEach
    void setup() {
        jsonb = JsonbBuilder.create();
        JsonbTester.initFields(this, jsonb);
    }

    @AfterEach
    void cleanup() throws Exception {
        if (jsonb != null) {
            jsonb.close();
        }
    }

    @Test
    void serializesUsingJsonb() throws Exception {
        GatewayReceipt receipt =
                new GatewayReceipt("OK", 2);

        assertThat(json.write(receipt))
                .isEqualToJson("""
                        {"code":"OK","attempts":2}
                        """);
    }

    @Test
    void deserializesUsingJsonb() throws Exception {
        GatewayReceipt actual = json.parseObject("""
                {"code":"DONE","attempts":3}
                """);

        assertThat(actual.getCode()).isEqualTo("DONE");
        assertThat(actual.getAttempts()).isEqualTo(3);
    }
}
```

`JsonbTester.initFields(this, jsonb)` khởi tạo tester dùng đúng `Jsonb` instance đã tạo. Khác với code sử dụng Spring injection, unit test chịu trách nhiệm khởi tạo và đóng tài nguyên JSON-B.

**Chú ý:** `JsonbTester` sử dụng Jakarta namespace `jakarta.json.bind.*` với Spring Boot 3.x. Không copy imports `javax.json.bind.*` từ một dự án Java EE cũ mà không kiểm tra phiên bản.

### 9.2. JSON-B annotation không tự động tương đương Jackson annotation

```java
class Example {
    @JsonbProperty("order_id")
    public long orderId;
}
```

Đây là snippet minh họa cần `jakarta.json.bind.annotation.JsonbProperty`, không thuộc code runnable chính. `@JsonbProperty` được JSON-B hiểu; Jackson `@JsonProperty` và Gson `@SerializedName` là ba hệ annotation khác nhau.

Nếu một service sử dụng JSON-B thật, hãy kiểm tra đúng `JsonbConfig`, visibility, adapters, date/time formatting và runtime provider. Đừng dùng tester của mapper khác để “đạt” schema chỉ trên giấy.

### 9.3. Khi dùng `@JsonTest` cho JSON-B

Khi provider/API ở classpath và Spring Boot auto-configures `Jsonb`, có thể inject:

```java
@JsonTest
class JsonbContractSliceTest {
    @Autowired
    JsonbTester<GatewayReceipt> json;
}
```

Đây là mẫu annotation, không phải test class đầy đủ. Dự án phần 5 không nạp Gson/Jsonb trong base POM; chúng chỉ trở thành runnable sau khi bạn thêm dependencies mở rộng. Với project cần nhiều engine, nên tách test classes và lựa chọn mapper đang kiểm tra rõ ràng thay vì suy đoán HTTP converter tự thay đổi.

## 10. Chạy toàn bộ ví dụ, tách base và mở rộng

### 10.1. Dự án gốc

Chỉ dùng POM phần 5 và ba test classes gốc:

- `ShippingNoticeJsonTest`: 4 tests.
- `RawJsonContractTest`: 2 tests.
- `ManualJacksonTesterTest`: 1 test.

Kết quả: **7 tests** nếu chỉ có những class này. Không có Gson hoặc JSON-B dependency trong base POM, nên không copy hai class extension vào source mà không thêm dependencies.

### 10.2. Khi muốn thực hành cả ba engines

Thêm ba dependencies test-scope ở phần 8–9 (Gson, JSON-B API, Yasson), thêm `GatewayReceipt.java` và hai test classes `GsonTesterTest`, `JsonbTesterTest` vào đúng package.

```bash
# Đảm bảo Maven tải đủ dependencies và compile test source:
mvn -B test

# Chạy riêng từng engine:
mvn -Dtest=ShippingNoticeJsonTest test
mvn -Dtest=GsonTesterTest test
mvn -Dtest=JsonbTesterTest test
mvn -Dtest=RawJsonContractTest test
```

Khi thêm hai test classes mở rộng, tổng số `@Test` là **11**: 7 gốc + 2 Gson + 2 JSON-B. Tuy nhiên số test pass phụ thuộc dependencies tương thích/JSON-B provider setup; nếu Maven báo lỗi provider hoặc module, hãy sửa dependency graph chứ không thay `JsonbTester` bằng JacksonTester để “lách” test.

### 10.3. Những điều test đã và chưa chứng minh

| Test | Đã kiểm tra | Chưa kiểm tra |
| --- | --- | --- |
| `ShippingNoticeJsonTest` | Spring JSON slice với mapper Jackson và contract DTO | HTTP route/status, network serialization khác context |
| `RawJsonContractTest` | JSON payload raw và JSONPath | Cách payload được sinh từ Java object |
| `ManualJacksonTesterTest` | Jackson serialization với mapper tự tạo | Mọi Boot-specific mapper customizer |
| `GsonTesterTest` | JSON theo Gson default của test | App production có dùng Gson converter hay không |
| `JsonbTesterTest` | JSON theo Jsonb/Yasson của test | Runtime provider/config production nếu khác |
| MVC/WebFlux integration test riêng | Endpoint trả JSON qua converter thực trong web context | Gateway/proxy/consumer ngoài hệ nếu chưa dựng |

**Phạm vi phải minh bạch:** `@JsonTest` là slice dành cho JSON mapper; kiểm thử toàn bộ HTTP boundary là một tầng bổ sung. Việc JSON fixture pass không tự khẳng định endpoint routing, validation, exception handling hay content negotiation hoạt động đúng.

## 11. Định nghĩa expected sao cho test không “xanh giả”

### 11.1. Expected phải độc lập với actual

Một anti-pattern:

```java
String actualJson = json.write(dto).getJson();
assertThat(json.write(dto)).isEqualToJson(actualJson);
```

Đoạn này chỉ so output với chính output vừa sinh, không đặt ra tiêu chuẩn cần đúng. Nếu mapper lỡ đổi `order_id` thành `orderId`, nó vẫn có thể pass.

Đúng hơn:

```java
assertThat(json.write(dto))
        .isEqualToJson("""
                {
                  "order_id": 502,
                  "recipient": "buyer@example.test",
                  "quantity": 3,
                  "shipOn": "2026-06-17"
                }
                """);
```

Đoạn trên là snippet dùng trong test có `json` và `dto` đã chuẩn bị; value expected được người viết quy định độc lập từ contract.

### 11.2. Không ép output phải giống từng khoảng trắng

Nếu bên nhận chỉ đọc JSON object, các bản:

```json
{"a":1,"b":2}
```

và

```json
{
  "b": 2,
  "a": 1
}
```

thường tương đương về cấu trúc. Dùng `isEqualToJson` hoặc JSON tree thay vì `assertThat(raw).isEqualTo(...)` khi whitespace/key order không thuộc contract.

**Ngoại lệ:** khi ký message bằng HMAC trên serialized bytes, content hashing/canonicalization hoặc protocol yêu cầu thứ tự chính xác, so sánh bytes và encoding một cách rõ ràng. `isEqualToJson` không đủ để chứng minh chữ ký byte-for-byte.

### 11.3. Đừng chỉ assert round-trip

`json.parseObject(json.write(dto).getJson()).equals(dto)` có thể pass ngay cả khi cả serializer và deserializer đều đổi tên trường theo cùng cách sai. Phải có một **golden fixture** hoặc field-level assertions dựa trên schema public.

### 11.4. Không kiểm tra trường nội bộ chỉ qua `contains`

Một JSON có `"password":"***"` và JSON khác có `"password":"secret"` đều chứa chuỗi `password`. Để đảm bảo không leak, assert field **vắng mặt hoặc đã mask** theo exact policy, và kiểm tra nested objects nếu schema cho phép.

Trong JSON parser Jackson ví dụ:

```java
JsonNode root = mapper.readTree(json.write(dto).getJson());
assertThat(root.has("password")).isFalse();
```

Đây là mẫu nhúng trong test; cần actual DTO có field password nếu muốn thật sự bảo vệ use case ấy. Với JSON-B/Gson, dùng parser tương ứng hoặc `BasicJsonTester`/JSONPath để quan sát payload. Không dùng secrets thật trong fixture.

## 12. Các góc khó của JSON serialization

### 12.1. Ngày giờ và timezone

Trong `ShippingNotice`, `shipOn` là `LocalDate`, không mang timezone. Nó được đặt format rõ `yyyy-MM-dd`.

Với `Instant`, `OffsetDateTime` hay `ZonedDateTime`, phải quyết định hợp đồng:

- UTC ISO-8601?
- Epoch milliseconds hay seconds?
- Có fractional seconds không?
- Có giữ offset gốc hay normalize?
- Có convert timezone theo locale của user không?

Test cần **mốc cố định** và fixture đúng expected; đừng dùng `Instant.now()` rồi mong serializing và assertions cùng đúng đến nanosecond. Một mapper tự tạo không có Java Time support có thể báo `InvalidDefinitionException`; hãy dùng Boot-configured mapper/appropriate module.

### 12.2. Enum naming

Một API có enum `PENDING_APPROVAL` nhưng consumer mong `"pendingApproval"`. Jackson `@JsonValue`, Gson adapters và JSON-B adapters có cơ chế riêng. Viết test serialize **và** deserialize với mẫu string đúng, không coi `enum.name()` mặc định là hợp đồng cuối cùng.

### 12.3. Null/missing/default values

- Missing object property và explicit null khác nhau.
- Primitive Java `int` không đại diện được null như `Integer`.
- Java record với constructor strict validation có thể throw khi Jackson deserialize.
- Gson/JSON-B có chiến lược default/unknown fields riêng.
- JSON schema validation và Bean Validation không mặc nhiên chạy chỉ vì gọi `json.parseObject`; `@Valid` trong controller là một tầng khác.

Để kiểm tra missing required field, có thể test `assertThatThrownBy(() -> json.parseObject(payload))` **nếu mapper/DTO đã được cấu hình để reject**. Đừng viết test mong Jackson luôn fail với mọi field thiếu; mặc định nhiều loại field có thể nhận null/zero.

### 12.4. Numeric precision

JSON number `12.50` và `12.5` có thể cùng trị toán học nhưng scale khác nhau ở Java `BigDecimal`. Khi unit tests về tiền cần làm rõ: contract yêu cầu numeric equivalence, fixed two-decimal formatting hay string amount? Nếu JSON signature hoặc downstream schema yêu cầu 2 decimal places, test raw representation/JsonNode decimal node theo cách bảo toàn scale. Không convert currency amount sang `double` rồi assert xấp xỉ nếu tiền có quy tắc thập phân chính xác.

### 12.5. Collections và thứ tự

Nếu JSON output chứa list thứ tự thời gian, assert phần tử theo thứ tự. Nếu object field order không thuộc contract, không ép thứ tự. Nếu `Map` được serialize và consumer chỉ tra key, test dựa trên structural equality chứ không dựa vào iteration order ngẫu nhiên.

### 12.6. Polymorphism và type information

Jackson `@JsonTypeInfo`, custom subtypes, Gson `TypeAdapter` và JSON-B adapters quyết định cách một field interface/abstract type được encode/decode. Test một DTO đơn giản không bảo vệ các trường hợp polymorphic. Khi object graph có subtype, cần fixture chứa type discriminator, kiểm tra whitelist type hợp lệ, và tránh bật deserialization mặc định không an toàn chỉ để test pass.

### 12.7. Generics như `List<Dto>`

`JacksonTester<List<MyDto>>` có thể được khởi tạo với full generic type information từ field thông qua test infrastructure. Nếu tạo mapper tay, `TypeReference<List<MyDto>>`/`ResolvableType` cần được xử lý đúng. Đừng serialize `List<Dto>` bằng cách cast qua raw `List` rồi tuyên bố đã kiểm tra type của từng phần tử sau deserialize.

### 12.8. Escaping và Unicode

JSON string phải encode dấu ngoặc kép, backslash và control characters hợp lệ. Test Java record ở phần 5 đưa tiếng Việt và dấu nháy vào `note`, xác nhận round-trip. Nếu hệ thống tiêu thụ JSON theo charset cụ thể hoặc ký raw bytes, phải kiểm tra encoding thật ở HTTP/message boundary.

### 12.9. Unknown fields, backward compatibility

Một provider mới có thể thêm field. Mapper có thể ignore unknown fields hoặc fail, tùy configuration. Chọn policy rõ:

- Public API nên forward-compatible với field bổ sung? Test decode input có extra field.
- Command nhận đầu vào nhạy cảm cần strict validation? Test unknown/missing/duplicate fields theo policy.
- Versioned event dùng schema evolution? Test v1/v2 fixtures và defaults của consumer.

Đừng suy luận mọi JSON tester luôn bỏ qua unknown fields: Jackson/Gson/JSON-B có defaults và custom settings khác nhau.

## 13. JSON fixture và snapshot: cách quản lý đáng tin

### 13.1. Khi nào lưu `expected.json`?

Fixture hữu ích với payload lớn, nested arrays, các required fields và schema có ổn định. Nó dễ review trong pull request hơn một chuỗi escaped dài.

Quy tắc:

1. Đặt trong `src/test/resources` cùng package nếu muốn resource-relative lookup.
2. Dùng giá trị giả, không chứa dữ liệu khách hàng/token thật.
3. Giữ fixture **độc lập** với serializer actual; nếu update snapshot, phải review lý do thay đổi.
4. Đặt tên thể hiện contract: `order-created-v1.json`, `payment-captured-v2.json`.
5. Với schema evolution, giữ vài fixtures của version cũ khi backward compatibility là yêu cầu.
6. Không biến việc update fixture thành hành động tự động mỗi khi test đỏ; đó có thể là regression.

### 13.2. `isEqualToJson` không tự thay thế JSON Schema

So sánh với một fixture chứng minh đúng **một ví dụ**. Nó không tự chứng minh mọi giá trị, mọi required/optional field hay valid ranges. Nếu contract yêu cầu JSON Schema/OpenAPI, thêm schema validation hoặc contract testing ở tầng phù hợp; tester vẫn có ích cho các case điển hình/biên.

### 13.3. Cách review diff

Khi test fail, phân loại:

- **Tên field sai:** mapper annotation/naming strategy đổi.
- **Value sai:** domain mapping/rounding/timezone sai.
- **Field dư/thiếu:** include/exclude/visibility/optional semantics đổi.
- **Array khác thứ tự:** collection sorting/contract order thay đổi.
- **Type sai:** number vs string, object vs array, null vs omitted.
- **Fixture sai hoặc không còn cập nhật:** requirements đã thay, cần quyết định version/compatibility.

Chỉ sửa expected khi contract thực sự thay đổi; không auto-accept output mới để làm test xanh.

## 14. `@JsonTest`, `@WebMvcTest` và `@SpringBootTest` khác nhau thế nào?

| Mục đích | Annotation/công cụ | Những gì được kiểm tra | Điều chưa được kiểm tra |
| --- | --- | --- | --- |
| Kiểm tra serializer/mapper DTO | `@JsonTest` + `JacksonTester`/Gson/Jsonb | Mapper, modules, JSON fields | HTTP routing, status/headers |
| Kiểm tra JSON raw từ bên ngoài | `BasicJsonTester` | JSONPath/structural JSON contract | Mapper nào đã sản sinh payload |
| Controller trả status/body theo service mock | `@WebMvcTest` + `MockMvc` | MVC mapping, HTTP response serialization trong slice | Logic service thật nếu mock |
| Service + controller thật với HTTP giả lập | `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` | Integration bean graph/mapping/response | Embedded HTTP listener/network |
| HTTP server thật | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Servlet/reactive server và JSON response qua socket | Production ingress/CDN nếu không có |
| Provider schema/contract ngoài hệ | HTTP stub, Pact/OpenAPI/schema tests | Consumer/provider compatibility | Toàn bộ E2E production flow |

Điểm hay bị nhầm: `@JsonTest` dùng ObjectMapper thật nhưng **không tự bảo đảm** cấu hình controller HTTP có cùng converter/visibility/profile như ứng dụng chạy đầy đủ. Một số customizations được slice chọn; một số app-specific `@Configuration` cần import. Khi serialization là contract công khai quan trọng, nên có **một số** HTTP boundary tests để bảo vệ wiring thật.

## 15. Troubleshooting: lỗi hay gặp khi dùng JSON testers

### Lỗi A. `@Autowired JacksonTester<Dto>` không được tạo

**Khả năng:** thiếu `@JsonTest`/test auto-configuration, thiếu Jackson dependency, generic field không được khởi tạo hoặc test không chạy bằng Spring TestContext.

**Sửa:** kiểm tra `spring-boot-starter-test`, `@JsonTest` và `spring-boot-starter-json`; nếu không muốn Spring context, gọi `JacksonTester.initFields(this, mapper)` trong `@BeforeEach`.

### Lỗi B. `ObjectMapper` không xử lý được `LocalDate`

**Khả năng:** bạn dùng `new ObjectMapper()` không đăng ký JavaTime module.

**Sửa:** dùng `@JsonTest` mapper, hoặc `new ObjectMapper().findAndRegisterModules()` khi module có trên classpath; không tùy tiện stringify date chỉ để test pass.

### Lỗi C. Thêm `@JsonProperty` nhưng Gson output vẫn tên cũ

**Nguyên nhân:** `@JsonProperty` thuộc Jackson; Gson dùng `@SerializedName`/Gson configuration.

**Sửa:** chọn đúng tester theo engine hoặc thay mapping annotation phù hợp. Nếu app đáng lẽ dùng Jackson, lỗi là **engine selection/config**, không phải “test dữ liệu sai”.

### Lỗi D. JSON-B báo “provider not found”

**Nguyên nhân:** có JSON-B API mà thiếu implementation/JSON-P provider tương thích.

**Sửa:** thêm Eclipse Yasson và dependency provider Jakarta JSON-P cần thiết, đồng bộ version theo BOM và kiểm tra dependency tree. Không dùng `javax.json.bind` cũ trong Boot 3.x.

### Lỗi E. `isEqualToJson("fixture.json")` không tìm file

**Nguyên nhân:** fixture không nằm đúng classpath/package relative với test, tên file/path sai hoặc resources chưa được build copy.

**Sửa:** đặt dưới `src/test/resources/com/example/jsonlab/` tương ứng package, tên file đúng; nếu cần dùng overload resource path tường minh.

### Lỗi F. Numeric JSONPath assertion fail dù `3 == 3` về trị số

**Nguyên nhân:** `Number` được trả là `Integer`/`Long`/`BigDecimal` khác type với expected.

**Sửa:** dùng `satisfies(n -> assertThat(n.intValue()).isEqualTo(3))` nếu integer semantics, hoặc kiểm tra decimal đúng policy. Không ép numeric thành string để né type.

### Lỗi G. Test pass chỉ vì round-trip

**Nguyên nhân:** expected lấy từ actual, hoặc cả serialize và deserialize đều cùng một sai mapping.

**Sửa:** thêm expected fixture/schema độc lập, field-level assertions quan trọng và negative cases.

### Lỗi H. Test Jackson pass nhưng response HTTP khác

**Nguyên nhân:** MVC converter dùng mapper/config khác, custom configuration không có trong `@JsonTest`, hoặc content negotiation thay format.

**Sửa:** xác minh mapper bean và custom modules trong context tương ứng; thêm `@WebMvcTest`/`MockMvc` hoặc HTTP integration test cho endpoint.

### Lỗi I. Cùng một DTO dùng cả Gson, JSON-B và Jackson nhưng JSON output khác

**Nguyên nhân:** engine có naming/visibility/annotation support khác nhau.

**Sửa:** định nghĩa contract theo engine thực, test mỗi engine riêng nếu có lý do; không áp một expected duy nhất khi schema intentionally khác.

### Lỗi J. Null field xuất hiện bất ngờ

**Nguyên nhân:** default include policy hoặc annotation/configuration không áp dụng ở mapper đang dùng.

**Sửa:** viết test missing-vs-null cụ thể, kiểm tra `JsonInclude`, Gson `serializeNulls`, JSON-B config theo engine.

### Lỗi K. Test nạp toàn bộ application và đòi database

**Nguyên nhân:** dùng `@SpringBootTest` thay vì `@JsonTest` khi chỉ cần mapper.

**Sửa:** chọn JSON slice, import custom module cần thiết thay vì cả application. Nếu mục tiêu yêu cầu mapper wiring trong full context, dùng test database/fake outbound ports, không lấy production credentials.

### Lỗi L. JSON payload chứa secret trong failure logs

**Nguyên nhân:** assertion in toàn payload chứa token/password/PII thật.

**Sửa:** dùng fixtures giả, redact fields nhạy cảm và giới hạn test artifacts; không đưa production data vào tests để debug.

## 16. Checklist khi code review JSON tests

- [ ] Đã xác định engine thực: Jackson, Gson, JSON-B hay raw JSON text.
- [ ] Đã chọn đúng `JacksonTester`/`GsonTester`/`JsonbTester`/`BasicJsonTester`.
- [ ] Với `@JsonTest`, đã bảo đảm mapper modules/customizations cần thiết thực sự có trong slice.
- [ ] Với manual tester, đã gọi `initFields` bằng mapper tương thích.
- [ ] Có assertions **Java → JSON** về tên trường, loại dữ liệu, giá trị và fields bỏ qua.
- [ ] Có assertions **JSON → Java** khi ứng dụng nhận input JSON.
- [ ] Expected là fixture/hợp đồng độc lập, không so output với chính output.
- [ ] JSON structural equality được dùng khi whitespace/object key order không thuộc contract.
- [ ] Array order được kiểm tra khi thứ tự là quan trọng.
- [ ] Missing, null, empty string và unknown fields có policy/test phù hợp.
- [ ] Ngày giờ/timezone, enum, BigDecimal, Unicode/escaping có case khi liên quan.
- [ ] Dữ liệu nhạy cảm được **loại trừ** và không lọt vào logs/fixtures.
- [ ] Test không nhầm việc mapper pass với endpoint HTTP pass.
- [ ] Không khởi động DB/broker/network thật nếu chỉ test JSON conversion.
- [ ] Nếu production dùng converter khác, có HTTP boundary test để xác nhận engine thực.
- [ ] Fixture được version/review cùng public contract.

## 17. Bài tập vận dụng

### Bài 1: Phát hiện đổi tên field sai

Thay thử `@JsonProperty("order_id")` thành `@JsonProperty("orderId")` trên nhánh tạm. Chạy `ShippingNoticeJsonTest`. Bạn mong test nào fail?

**Gợi ý đáp án:** `isEqualToJson("expected-shipping-notice.json")` không khớp schema, và assertion kiểm tra JSON tree không có `orderId` cũng fail.

### Bài 2: Missing khác null

Thử bỏ `@JsonInclude(NON_NULL)` khỏi `note`, rồi kiểm tra JSON tạo ra có field `note` hay không. Viết assertion xác nhận contract “không gửi field nếu null” bằng `mapper.readTree`/`has("note")`. Nếu mapper có global NON_NULL policy, hãy hiểu config đó trước khi kết luận annotation là phần duy nhất điều khiển.

### Bài 3: Gson annotation

Tạo DTO riêng có `@SerializedName("order_id")`, viết `GsonTester` xác nhận key `order_id` và không có key `orderId`. **Không** dùng `@JsonProperty` rồi mong Gson thay tên.

### Bài 4: JSON-B field naming

Tạo POJO JSON-B với `@JsonbProperty("order_id")`, viết `JsonbTester` assert output. Kiểm tra differences nếu thay DTO bằng Java record, nhất là trên provider/phiên bản JSON-B thực đang dùng.

### Bài 5: Payload JSON từ webhook

Nhận một chuỗi JSON có `eventType`, `aggregateId`, `items[]`. Dùng `BasicJsonTester#from(payload)` assert kiểu/string và một item theo JSONPath. Thêm case payload thiếu `aggregateId`; quyết định đây là case test invalid schema hay chỉ assertion vắng trường.

### Bài 6: JSON API response

Bổ sung một controller trả `ShippingNotice`. Dùng `@WebMvcTest` + `MockMvc` assert response JSON có `order_id`, `shipOn` và không có `note`. Qua đó chứng minh rằng JSON engine/wiring trong MVC slice tạo đúng HTTP response, không chỉ `JacksonTester`.

## 18. Câu hỏi tự kiểm tra

**1.** Khi nào chọn `BasicJsonTester` thay vì `JacksonTester`?

**Trả lời:** Khi dữ liệu cần kiểm tra là JSON text/bytes/file đã được tạo từ nguồn bất kỳ, không cần serialize/deserialize Java DTO bằng Jackson.

**2.** `@JsonTest` có tự tải Gson dependency từ Maven không?

**Trả lời:** Không. Nó auto-configures support cho những JSON libraries có sẵn theo classpath/conditions. Dependencies do dự án khai báo.

**3.** Dùng `GsonTester` để test một DTO chứa `@JsonProperty("order_id")` có chắc output `order_id` không?

**Trả lời:** Không. `@JsonProperty` thuộc Jackson; Gson có annotation/configuration riêng như `@SerializedName`.

**4.** Tại sao `JacksonTester.initFields(this, new ObjectMapper())` có thể khác `@JsonTest`?

**Trả lời:** Mapper tự tạo thiếu Boot customizations, Java Time modules, naming/visibility rules hoặc serializers được Spring context đăng ký. Nếu cần config ứng dụng, dùng mapper bean hoặc auto-configured JSON slice.

**5.** Có nên viết `assertThat(json.write(dto).getJson()).isEqualTo(expectedRawString)` không?

**Trả lời:** Chỉ khi whitespace/key order/raw bytes thật sự thuộc contract. Nếu không, nên so JSON structure hoặc JSONPath.

**6.** `JsonbTester` cần gì ngoài `jakarta.json.bind-api`?

**Trả lời:** Cần một JSON-B implementation/provider tương thích như Eclipse Yasson cùng dependency JSON-P tương ứng. API chỉ là interface.

**7.** `@JsonTest` pass đã chứng minh `GET /api/orders` trả status 200 chưa?

**Trả lời:** Chưa. Nó bảo vệ mapper; HTTP routing/status phải được kiểm tra bằng MVC/WebFlux/server integration test.

**8.** Round-trip `parseObject(write(dto))` pass có đủ không?

**Trả lời:** Chưa đủ: cả serialize và deserialize có thể cùng sai về field naming. Cần expected schema/fixture độc lập.

**9.** JSONPath trả `Number`; nên ép `Long` mọi trường hợp không?

**Trả lời:** Không. Chọn so sánh theo numeric semantics cần thiết hoặc kiểm tra type cụ thể theo contract, tránh matcher giòn chỉ do numeric wrapper.

**10.** Có nên test không lộ `password` bằng cách assert JSON chứa `"password":null`?

**Trả lời:** Chỉ nếu contract thật sự cho phép field đó xuất hiện null. Thường dữ liệu bí mật không được xuất hiện cả dưới dạng null; kiểm tra vắng field bằng JSON tree/schema.

## 19. Tài liệu chính thức

- [Spring Boot 3.5 – Auto-configured JSON Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-json-tests): `@JsonTest`, Jackson/Gson/Jsonb/Basic testers, `initFields` và JSONPath.
- [Spring Boot 3.5 – Test JSON package](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/package-summary.html): `JacksonTester`, `GsonTester`, `JsonbTester`, `BasicJsonTester`.
- [Spring Boot 3.5 – JacksonTester Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/JacksonTester.html): `write`, `parseObject`, `initFields`, `forView`.
- [Spring Boot 3.5 – JsonbTester Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/JsonbTester.html): `JsonbTester.initFields` và JSON-B support.
- [Spring Boot 3.5 – AutoConfigureJsonTesters Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/json/AutoConfigureJsonTesters.html): điều khiển registration.
- [Spring Boot 3.5 – Test Auto-configuration Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): các bean/auto-configurations của JSON slice.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): `@JsonProperty`, `@JsonFormat`, `@JsonInclude`.
- [Gson User Guide](https://github.com/google/gson/blob/main/UserGuide.md): Gson engine và annotations/adapters.
- [Jakarta JSON Binding Specification](https://jakarta.ee/specifications/jsonb/): API `Jsonb`, naming/serialization và providers.

**Kết luận:** Để kiểm tra JSON hiệu quả, **chọn tester đúng engine và đúng boundary**. `JacksonTester`, `GsonTester`, `JsonbTester` bảo vệ chuyển đổi Java object ↔ JSON của một mapper; `BasicJsonTester` bảo vệ JSON đã có sẵn như một chuỗi/bytes. `@JsonTest` giúp kiểm tra JSON mapper trong Spring slice, còn HTTP test kiểm tra converter và response của ứng dụng. Luôn dùng expected độc lập, kiểm tra tên trường/kiểu/giá trị/field vắng mặt, và đừng nhầm round-trip pass với contract pass.