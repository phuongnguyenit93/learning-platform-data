# Kiểm tra JSON đầu ra theo cấu trúc và thuộc tính quan trọng trong Spring Boot

## 1. Tại sao phải kiểm thử JSON theo cấu trúc?

Khi viết Spring Boot REST API, một response trông như sau:

```json
{
  "sku": "SKU-001",
  "title": "Spring Testing",
  "price": {
    "amount": 19.90,
    "currency": "USD"
  },
  "available": true
}
```

Nội dung mà client thật sự phụ thuộc vào là **cấu trúc** và **giá trị/ngữ nghĩa của các thuộc tính quan trọng**: `sku` là chuỗi định danh, `price` là object có `amount` dạng số và `currency`, `available` là boolean. Thứ tự các key trong object hoặc số lượng khoảng trắng thường **không** thuộc hợp đồng API.

Kiểm response bằng phép so sánh chuỗi thô là mong manh:

```java
assertEquals(
    "{\"sku\":\"SKU-001\",\"title\":\"Spring Testing\",...}",
    responseBody);
```

Nếu Jackson chỉ đổi thứ tự field hoặc format whitespace, chuỗi này có thể fail dù client vẫn đọc được JSON đúng. Ngược lại, chỉ kiểm HTTP 200 có thể **bỏ sót** field sai kiểu, thiếu dữ liệu, giá tiền sai, danh sách trả về không đúng hoặc vô tình lộ thông tin nhạy cảm.

Bài này hướng dẫn **chọn đúng mức assertion**:

1. Kiểm **response contract**: HTTP status, Content-Type, JSON object/array root.
2. Kiểm **thuộc tính bắt buộc**: path tồn tại, đúng kiểu và giá trị/ngữ nghĩa.
3. Kiểm **cấu trúc lồng nhau**: object, array, quan hệ giữa fields, cardinality.
4. Kiểm **negative contract**: field phải vắng mặt, không lộ `passwordHash`/`internalCost`/`secretToken`.
5. Chọn **strict/lenient** cho so sánh cả JSON khi hợp đồng yêu cầu.
6. Chỉ dùng JSON Schema hay snapshot/golden file khi chúng giải quyết một rủi ro thật.
7. Viết test đáng tin bằng Spring Boot 3.5, JUnit Jupiter, `MockMvc`, `MockMvcTester`, `@JsonTest`/`JacksonTester`, `ObjectMapper`/`JsonNode` và `WebTestClient` khi dùng WebFlux.

**Nguyên tắc:** Test nên **nghiêm với hợp đồng công khai, linh hoạt với chi tiết không thuộc hợp đồng**. “So ít field cho đỡ fail” không đủ nếu bỏ qua những field bắt buộc hoặc rò rỉ dữ liệu nhạy cảm.

## 2. JSON là cây giá trị, không phải một chuỗi định dạng

### 2.1. Những loại node trong JSON

JSON có sáu loại giá trị: **object**, **array**, **string**, **number**, **boolean**, **null**. Không có kiểu JSON chính thức tên `BigDecimal`, `LocalDateTime` hoặc `UUID`; những ý nghĩa đó do API contract quy định trên một JSON number/string và quy tắc serialization.

```json
{
  "id": "p-17",
  "total": 19.9,
  "active": true,
  "tags": ["spring", "testing"],
  "shipping": {
    "city": "Hà Nội",
    "fee": 0
  },
  "discount": null
}
```

Đường dẫn JSON:

| JSONPath | Loại kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| `$.id` | string | Định danh sản phẩm |
| `$.total` | number | Giá trị số, không phải chuỗi `"19.9"` |
| `$.active` | boolean | `true` không phải `"true"` |
| `$.tags` | array | Danh sách tags |
| `$.tags[0]` | string | Phần tử đầu nếu thứ tự là contract |
| `$.shipping` | object | Object lồng |
| `$.shipping.city` | string | Địa điểm |
| `$.discount` | null | Field tồn tại nhưng giá trị null |

### 2.2. Hai chuỗi JSON khác nhau có thể tương đương

Hai object sau thường mang cùng ý nghĩa:

```json
{"sku":"SKU-001","available":true,"price":{"amount":19.90,"currency":"USD"}}
```

```json
{
  "price": {"currency": "USD", "amount": 19.90},
  "available": true,
  "sku": "SKU-001"
}
```

Theo JSON, thứ tự các **member của object** không nên được client phụ thuộc nếu contract không nói khác. Nhưng **thứ tự phần tử trong array** có ý nghĩa và có thể là phần contract, chẳng hạn `items` đã được sort theo thời gian.

Đừng gộp hai câu:
- “Chúng tôi không quan tâm thứ tự **key trong object**.”
- “Chúng tôi không quan tâm thứ tự **phần tử trong array**.”

Thứ hai chỉ đúng khi danh sách là một tập không có thứ tự đã cam kết.

### 2.3. Missing, null, empty và false là bốn ý nghĩa khác nhau

So sánh:

```json
{}
```

```json
{"discount":null}
```

```json
{"discount":0}
```

```json
{"discount":false}
```

```json
{"discount":[]}
```

Trong API, `discount` vắng mặt có thể mang nghĩa “không hỗ trợ thuộc tính”, `null` là “chưa biết/không áp dụng”, `0` là miễn giảm bằng 0; và `false`/`[]` thuộc các kiểu khác. Không thể thay thế lẫn nhau chỉ vì UI vẫn hiển thị một giá trị mặc định.

Phân biệt trong Spring MVC:

```java
jsonPath("$.discount").exists();            // chỉ khi có giá trị non-null
jsonPath("$.discount").hasJsonPath();       // cả khi field tồn tại với null
jsonPath("$.discount").doesNotExist();      // không có giá trị non-null
jsonPath("$.discount").doesNotHaveJsonPath();// field hoàn toàn không có, kể cả null
```

Đây là **các biểu thức matcher minh họa**, dùng từ `MockMvcResultMatchers.jsonPath` trong một `andExpect(...)`. Phần thực hành sẽ dùng `doesNotHaveJsonPath()` để bảo vệ **sự vắng mặt tuyệt đối** của trường nhạy cảm. Nếu dùng `doesNotExist()` cho trường nhạy cảm, một response chứa `"passwordHash":null` vẫn có thể khiến test pass, dù chính sách yêu cầu không bao giờ xuất hiện key đó.

## 3. Chọn chiến lược assertion theo rủi ro

| Cần chứng minh | Cách kiểm phù hợp | Không nên chỉ dùng |
| --- | --- | --- |
| API phản hồi thành công | `status().isOk()` và Content-Type | Chỉ kiểm body text |
| Root là object | Parse bằng `JsonNode.isObject()` hoặc JSONPath type | Tìm ký tự `{` đầu tiên |
| Một field bắt buộc có giá trị | `jsonPath("$.sku").value(...)` | `contains("SKU-001")` trong raw text |
| Field đúng kiểu number | `jsonPath("$.price.amount").isNumber()` | So `String` `"19.90"` |
| Field boolean đúng kiểu | `jsonPath("$.available").isBoolean()` | So text `"true"` |
| Field nhạy cảm vắng hoàn toàn | `doesNotHaveJsonPath()` hoặc `JsonNode.has()==false` | `doesNotExist()` (null vẫn có thể pass) |
| Mảng có đúng số phần tử | `jsonPath("$.items", hasSize(2))` | Chỉ kiểm `items[0]` |
| Danh sách không có thứ tự cam kết | `containsInAnyOrder` + cardinality | `items[0]` phải là sản phẩm A |
| Danh sách có thứ tự cam kết | `containsExactly`/JSON compare STRICT | LENIENT bỏ qua order |
| JSON cả object phải khớp | `content().json(expected, JsonCompareMode.STRICT)` | Raw string equality |
| Chỉ subset fields là contract | JSONPath/selective `JsonNode` assertions | Strict snapshot toàn response |
| Serialization của DTO | `@JsonTest` + `JacksonTester` | Full server test để kiểm annotation Jackson nhỏ |
| Full MVC wiring | `@SpringBootTest + @AutoConfigureMockMvc` | Unit test object Java đơn thuần |
| WebFlux response | `@WebFluxTest` + `WebTestClient` | `MockMvc` (servlet stack khác) |
| Hợp đồng chính thức của payload lớn | JSON Schema và contract tests | Snapshot không xem kỹ |

**Chọn kết hợp**: một test có thể kiểm status + media type + các trường quan trọng + không lộ field nhạy cảm; một test riêng kiểm **strict full response** khi endpoint có hợp đồng cứng. Không ép tất cả assertions vào một method quá dài.

## 4. Spring MVC: kiểm JSON qua MockMvc và jsonPath

### 4.1. MockMvc không chạy HTTP server thật

`MockMvc` gửi mock servlet request tới `DispatcherServlet`, controller, message converters và filters hiện diện trong test context. Nó phù hợp để kiểm routing, JSON serialization, status và controller behavior mà không mở cổng TCP.

Với Spring Boot 3.5 và JUnit Jupiter:

```java
@WebMvcTest(ProductController.class)
class ProductControllerJsonContractTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;
}
```

`@WebMvcTest` là MVC slice. Nó không scan mọi `@Service`/repository của app; `@MockitoBean` cấp đúng collaborator của controller, đồng thời test vẫn kiểm **controller và Jackson HTTP layer thật**.

### 4.2. Assertions có giá trị cao

```java
mvc.perform(get("/api/products/{sku}", "SKU-001")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.sku").value("SKU-001"))
    .andExpect(jsonPath("$.price").isMap())
    .andExpect(jsonPath("$.price.amount").isNumber())
    .andExpect(jsonPath("$.price.currency").value("USD"))
    .andExpect(jsonPath("$.available").isBoolean())
    .andExpect(jsonPath("$.internalCost").doesNotHaveJsonPath());
```

Đoạn trên là ví dụ bên trong JUnit test có `mvc`, service đã được stub và các static imports tương ứng. `isMap` kiểm object tại path, `isNumber` kiểm kiểu JSON number, không phụ thuộc object field order. Assert `internalCost` hoàn toàn vắng mặt giúp chống lộ trường nội bộ.

**Không coi `jsonPath("$.price.amount").isNumber()` là phép kiểm giá trị tiền**. Nó chỉ chứng minh kiểu; cần thêm assertion giá trị/ngữ nghĩa riêng khi giá là business contract.

### 4.3. JSONPath definite và indefinite

Các path như `$.items[0].sku` xác định một phần tử cụ thể. Path `$.items[*].sku` có wildcard và trả collection. Có thể dùng Hamcrest:

```java
.andExpect(jsonPath("$.items[*].sku",
        containsInAnyOrder("SKU-001", "SKU-002")))
```

Với wildcard, hãy kiểm **kích thước list** ở path cha để tránh bỏ sót phần tử trùng hoặc phần tử ngoài dự kiến. `containsInAnyOrder` khẳng định tập giá trị trả về theo matcher, không bảo đảm thứ tự; dùng khi API không cam kết sort.

### 4.4. Array: nội dung, size và order

Nếu `items` có hai phần tử, kiểm:

```java
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items", hasSize(2)))
.andExpect(jsonPath("$.items[*].sku",
        containsInAnyOrder("SKU-001", "SKU-002")))
```

Nếu API có query `sort=price,asc` và contract cam kết thứ tự, nên kiểm:

```java
.andExpect(jsonPath("$.items[*].sku",
        contains("SKU-002", "SKU-001")))
```

Đoạn `contains(...)` là **minh họa** cho endpoint đã sort theo giá tăng. Không áp dụng matcher order đó cho project mẫu không có sort parameter. Khi sắp xếp chính xác quan trọng, xác định tie-breaker như `sku` để tránh flaky tests khi có hai giá bằng nhau.

### 4.5. Kiểm optional và field nhạy cảm

```java
.andExpect(jsonPath("$.internalCost").doesNotHaveJsonPath())
.andExpect(jsonPath("$.secretToken").doesNotHaveJsonPath())
.andExpect(jsonPath("$.passwordHash").doesNotHaveJsonPath())
```

Nếu DTO đã loại các field nhạy cảm khỏi serialization, những assertions này bảo vệ việc refactor vô tình thêm getter/field mới. Cần kiểm ở path lồng khi có:

```java
.andExpect(jsonPath("$.customer.passwordHash").doesNotHaveJsonPath())
```

Nhưng nếu property `customer` vốn không có, matcher path lồng cũng pass. Khi contract yêu cầu object customer tồn tại, thêm `jsonPath("$.customer").isMap()` và `jsonPath("$.customer.id").isString()` để tránh “pass vì bỏ luôn cả object cần thiết”.

### 4.6. Status và Content-Type là một phần hợp đồng

API trả 200 với body HTML lỗi của proxy không phải JSON contract đúng. Chỉ assert `contains("SKU")` có thể bỏ qua điều này. Kết hợp:

```java
.andExpect(status().isOk())
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
```

`contentTypeCompatibleWith` cho phép media type tương thích, ví dụ application/json với charset variation. Nếu hợp đồng yêu cầu `application/problem+json` cho lỗi, kiểm đúng media type đó ở test lỗi; không ép tất cả endpoints trả `application/json`.

## 5. So sánh toàn bộ JSON bằng JSONAssert: STRICT và LENIENT

Spring Framework 6.2 cung cấp `org.springframework.test.json.JsonCompareMode`; `MockMvcResultMatchers.content().json(expected, mode)` sử dụng JSON comparator, thông thường JSONAssert khi có dependency tương ứng.

### 5.1. STRICT

```java
import org.springframework.test.json.JsonCompareMode;

mvc.perform(get("/api/products/SKU-001"))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """, JsonCompareMode.STRICT));
```

**STRICT** so sánh JSON theo cấu trúc, không phụ thuộc thứ tự key của object hay whitespace, nhưng yêu cầu không có member thừa và giữ thứ tự phần tử array. Đây là lựa chọn tốt khi DTO chính là hợp đồng cần kiểm và mọi field đều có ý nghĩa.

### 5.2. LENIENT

```java
mvc.perform(get("/api/products/SKU-001"))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {"sku":"SKU-001","available":true}
                """, JsonCompareMode.LENIENT));
```

**LENIENT** cho phép object có field bổ sung và có so sánh array không yêu cầu cùng thứ tự theo semantics JSONAssert. Nó phù hợp khi chỉ một phần object là contract và không muốn mỗi lần thêm field vô hại đều làm test fail.

Tuy nhiên, **không dùng LENIENT thay thế các phép kiểm bảo mật**. Vì cho phép thuộc tính dư, một response vô tình chứa `"secretToken":"..."` vẫn có thể khớp expected lenient chỉ gồm `sku` và `available`. Phải có negative assertions `doesNotHaveJsonPath()` hoặc kiểm whitelist/schema phù hợp.

### 5.3. Bảng khác biệt

| Thay đổi của actual so với expected | STRICT | LENIENT | Có phải bug? |
| --- | --- | --- | --- |
| Đổi thứ tự key trong object | Thường PASS | PASS | Không nếu contract không quy định order |
| Thêm field mới vào object | FAIL | Có thể PASS | Tùy chính sách tương thích/bảo mật |
| Thiếu field expected | FAIL | FAIL | Thường là bug contract |
| Value của field expected khác | FAIL | FAIL | Bug nếu expected đúng |
| Đảo thứ tự phần tử array | FAIL | Có thể PASS | Tùy API có cam kết order |
| Thêm element mới vào array | FAIL | FAIL hoặc khác theo comparator | Phải xác định pagination/cardinality |
| String `"19.90"` thay number `19.90` | Không tương đương theo contract kiểu | Không nên cho qua | Sai schema/kiểu |
| Field null thay vì absent | Có thể FAIL | Phụ thuộc expected/compare mode | Cần assertion về presence cụ thể |

Không nên chọn chế độ chỉ vì “STRICT làm đỏ nhiều test” hoặc “LENIENT dễ PASS”. Chọn từ **OpenAPI/JSON Schema và consumer expectations**; khi cần khác nhau ở từng path, phối hợp JSONPath/JsonNode/custom comparator thay vì áp một chế độ toàn cục.

### 5.4. Vì sao không so raw JSON string?

```java
assertThat(body).isEqualTo("""
        {"sku":"SKU-001","available":true}
        """);
```

Đoạn này kiểm cả whitespace và thứ tự JSON object properties. Nó có thể phù hợp với định dạng wire-format được quy định byte-for-byte hoặc signed payload, nhưng **không phù hợp mặc định** cho HTTP JSON business API. Hãy parse JSON hoặc dùng JSON-aware matcher.

### 5.5. Chú ý phiên bản

Spring Framework 6.2 đã bổ sung overload nhận `JsonCompareMode`. Overload cũ `content().json(expected, booleanStrict)` vẫn có trong một số phiên bản 6.2 nhưng đã deprecated; khi bài mẫu dùng 6.2 thì ưu tiên enum. Với Boot 3.3 / Framework 6.1, cần dùng API có trong version đó hoặc nâng dependency BOM nhất quán.

## 6. Jackson JsonNode: kiểm cấu trúc với quyền kiểm soát chi tiết

JSONPath rất thuận tiện trong MVC tests. Nhưng có lúc cần kiểm **nhiều path có điều kiện, tính toán số chính xác, hoặc phân biệt thiếu/null rõ ràng**. Khi đó parse một lần bằng Jackson:

```java
JsonNode root = objectMapper.readTree(responseBody);
```

`ObjectMapper` từ Spring Boot có thể được `@Autowired` trong full-context test, hoặc tạo mapper theo config cần kiểm. Không bắt buộc dùng ObjectMapper để test mọi response.

### 6.1. isObject, isArray, isTextual, isNumber, isBoolean

```java
assertThat(root.isObject()).isTrue();
assertThat(root.path("sku").isTextual()).isTrue();
assertThat(root.path("price").isObject()).isTrue();
assertThat(root.path("price").path("amount").isNumber()).isTrue();
assertThat(root.path("available").isBoolean()).isTrue();
```

`path(...)` trả **MissingNode** thay vì ném exception khi không thấy field; điều đó tiện cho nested checks nhưng có thể che thiếu field nếu chỉ gọi `asText()` mà không assert presence/type.

### 6.2. get, path, has, hasNonNull

| Jackson API | Khi field vắng mặt | Khi field là JSON null |
| --- | --- | --- |
| `root.get("field")` | Trả Java `null` | Trả `NullNode` |
| `root.path("field")` | Trả `MissingNode` | Trả `NullNode` |
| `root.has("field")` | `false` | `true` |
| `root.hasNonNull("field")` | `false` | `false` |
| `root.path("field").isMissingNode()` | `true` | `false` |
| `root.path("field").isNull()` | `false` | `true` |

Nếu yêu cầu “field này không được xuất hiện”, dùng `assertThat(root.has("secretToken")).isFalse()`, không dùng `hasNonNull` vì key có thể xuất hiện với `null` và vẫn pass.

### 6.3. JSON Pointer

Jackson `JsonNode.at(...)` sử dụng JSON Pointer (RFC 6901), khác với JSONPath:

```java
JsonNode amount = root.at("/price/amount");
JsonNode firstSku = root.at("/items/0/sku");
```

`/items/0/sku` chọn phần tử mảng đầu; nếu API không cam kết order, nên duyệt/lookup theo `sku` thay vì giả định index 0. Dấu `~` và `/` trong field name phải escape theo JSON Pointer (`~0` và `~1`).

### 6.4. Tiền tệ: kiểm giá trị bằng BigDecimal

`BigDecimal("19.90").equals(new BigDecimal("19.9"))` trả false vì scale khác; `compareTo` trả 0 nếu cùng giá trị số. Trong JSON, `19.90` và `19.9` đều là JSON numbers; quyết định **scale có thuộc contract** hay không.

```java
JsonNode amountNode = root.at("/price/amount");

assertThat(amountNode.isNumber()).isTrue();

BigDecimal actual = amountNode.decimalValue();
assertThat(actual.compareTo(new BigDecimal("19.90"))).isZero();
```

Nếu API yêu cầu hiển thị đúng hai chữ số thập phân, có thể dùng **string** `"19.90"` theo định nghĩa hợp đồng, hoặc custom serialization/formatting và kiểm riêng. Đừng assert `BigDecimal.equals` khi scale không được cam kết, nhưng cũng đừng bỏ qua precision/rounding khi nghiệp vụ tài chính cần chúng.

### 6.5. Số lớn và floating point

JSON có type number nhưng không quy định precision nội bộ. Một số parser chuyển thành `Integer`, `Long`, `Double`, `BigDecimal` tùy input/configuration. Khi so tiền hoặc định danh lớn:
- Không ép ID 64-bit thành JavaScript Number nếu có thể mất precision.
- Dùng `isNumber` để kiểm type rồi `decimalValue()/bigIntegerValue()` hoặc typed conversion để kiểm value.
- Với số đo floating point, dùng tolerance rõ, không so equality tuyệt đối tùy tiện.
- Với tiền, ưu tiên decimal/exact type và quy tắc rounding của domain.

## 7. Project thực hành chạy được: Spring Boot 3.5, Java 17

Demo minh họa cả **HTTP JSON contract** và **serialization contract** với Java records, JSON lồng, array, boolean và giá BigDecimal. Không dùng DB, Kafka, Docker hay external HTTP.

### 7.1. Cấu trúc

```text
json-structure-lab/
├── pom.xml
├── src/main/java/com/example/jsoncontract/
│   ├── JsonContractApplication.java
│   ├── PriceView.java
│   ├── ProductView.java
│   ├── CatalogPage.java
│   ├── ProductService.java
│   └── ProductController.java
└── src/test/java/com/example/jsoncontract/
    ├── ProductFixtures.java
    ├── ProductControllerJsonContractTest.java
    ├── ProductViewJsonTest.java
    └── ProductJsonTreeIntegrationTest.java
```

Mỗi file Java có package `com.example.jsoncontract`. Toàn bộ test classes được phát hiện bởi Maven Surefire do kết thúc bằng `Test`.

### 7.2. pom.xml

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
  <artifactId>json-structure-lab</artifactId>
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
```

`spring-boot-starter-web` có Spring MVC/Jackson; `spring-boot-starter-test` có JUnit Jupiter, Mockito, AssertJ và các test helper cần dùng. Spring Boot parent quản lý versions, không pin một mình `spring-test` hoặc Jackson module khác phiên bản. `@MockitoBean` thuộc Spring Framework 6.2, có sẵn theo BOM của Boot 3.5.

### 7.3. Main application

`src/main/java/com/example/jsoncontract/JsonContractApplication.java`:

```java
package com.example.jsoncontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonContractApplication.class, args);
    }
}
```

### 7.4. Nested DTO: PriceView

`src/main/java/com/example/jsoncontract/PriceView.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;

public record PriceView(BigDecimal amount, String currency) {}
```

Jackson serialize `BigDecimal` dưới JSON number, không phải text, khi dùng cấu hình mặc định của Boot. API contract ở ví dụ là `price.amount` là number và `price.currency` là string mã tiền tệ.

### 7.5. ProductView

`src/main/java/com/example/jsoncontract/ProductView.java`:

```java
package com.example.jsoncontract;

public record ProductView(
        String sku,
        String title,
        PriceView price,
        boolean available) {}
```

DTO công khai **chỉ** chứa bốn thành phần. Nó không chứa `internalCost`, `supplierPassword` hay `secretToken`. Test sẽ kiểm sự vắng mặt của các field nhạy cảm để chặn thay đổi ngoài ý muốn ở serialization layer.

### 7.6. CatalogPage

`src/main/java/com/example/jsoncontract/CatalogPage.java`:

```java
package com.example.jsoncontract;

import java.util.List;

public record CatalogPage(
        List<ProductView> items,
        int total,
        String requestId) {}
```

`total` là tổng số item trong trang minh họa (2). Trong API pagination thật, phải phân biệt `totalElements` trên toàn dataset với `items.size()` trên trang hiện tại, `pageSize` và `hasNext`; test không nên đánh đồng các ý nghĩa đó.

### 7.7. ProductService

`src/main/java/com/example/jsoncontract/ProductService.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    public Optional<ProductView> find(String sku) {
        return "SKU-001".equals(sku)
                ? Optional.of(first())
                : Optional.empty();
    }

    public CatalogPage page() {
        return new CatalogPage(
                List.of(first(), second()),
                2,
                "req-123");
    }

    private ProductView first() {
        return new ProductView(
                "SKU-001",
                "Spring Testing",
                new PriceView(new BigDecimal("19.90"), "USD"),
                true);
    }

    private ProductView second() {
        return new ProductView(
                "SKU-002",
                "JUnit Patterns",
                new PriceView(new BigDecimal("8.00"), "USD"),
                false);
    }
}
```

Dữ liệu cố định để test có kết quả dự đoán được. Production code sẽ lấy dữ liệu từ repository hoặc external API, có phân quyền và xử lý lỗi; không kéo những phụ thuộc đó vào ví dụ đang tập trung JSON structure.

### 7.8. ProductController

`src/main/java/com/example/jsoncontract/ProductController.java`:

```java
package com.example.jsoncontract;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ResponseEntity<ProductView> bySku(
            @PathVariable String sku) {
        return service.find(sku)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping
    public CatalogPage page() {
        return service.page();
    }
}
```

Hai endpoints:
- `GET /api/products/SKU-001`: HTTP 200, JSON object ProductView.
- `GET /api/products/NOT-FOUND`: HTTP 404, body có thể trống.
- `GET /api/products`: HTTP 200, JSON object CatalogPage với `items` array, `total` number và `requestId` string.

Không thêm status 201 cho GET, không mong response 404 có JSON body nếu controller không xây error DTO.

### 7.9. Fixtures dùng chung trong test

`src/test/java/com/example/jsoncontract/ProductFixtures.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;
import java.util.List;

final class ProductFixtures {

    private ProductFixtures() {}

    static ProductView first() {
        return new ProductView(
                "SKU-001",
                "Spring Testing",
                new PriceView(new BigDecimal("19.90"), "USD"),
                true);
    }

    static ProductView second() {
        return new ProductView(
                "SKU-002",
                "JUnit Patterns",
                new PriceView(new BigDecimal("8.00"), "USD"),
                false);
    }

    static CatalogPage page() {
        return new CatalogPage(
                List.of(first(), second()),
                2,
                "req-123");
    }
}
```

`ProductFixtures` chỉ nằm ở test source set, không phải production bean. Test slice sử dụng fixture để stub `ProductService`; full integration test sử dụng service thật có kết quả tương ứng.

### 7.10. ProductControllerJsonContractTest: MVC slice kiểm cấu trúc quan trọng

`src/test/java/com/example/jsoncontract/ProductControllerJsonContractTest.java`:

```java
package com.example.jsoncontract;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerJsonContractTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;

    @Test
    void checksRequiredPropertiesAndTypes() throws Exception {
        when(service.find("SKU-001"))
                .thenReturn(Optional.of(ProductFixtures.first()));

        mvc.perform(get("/api/products/{sku}", "SKU-001")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$").isMap())
                .andExpect(jsonPath("$.sku").value("SKU-001"))
                .andExpect(jsonPath("$.title").value("Spring Testing"))
                .andExpect(jsonPath("$.price").isMap())
                .andExpect(jsonPath("$.price.amount").isNumber())
                .andExpect(jsonPath("$.price.currency").value("USD"))
                .andExpect(jsonPath("$.available").isBoolean())
                .andExpect(jsonPath("$.available").value(true))
                .andExpect(jsonPath("$.internalCost")
                        .doesNotHaveJsonPath())
                .andExpect(jsonPath("$.secretToken")
                        .doesNotHaveJsonPath());

        verify(service).find("SKU-001");
    }

    @Test
    void checksCollectionShapeWithoutAssumingOrder() throws Exception {
        when(service.page()).thenReturn(ProductFixtures.page());

        mvc.perform(get("/api/products")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$").isMap())
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.items", hasSize(2)))
                .andExpect(jsonPath("$.items[*].sku",
                        containsInAnyOrder("SKU-001", "SKU-002")))
                .andExpect(jsonPath("$.total").isNumber())
                .andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.requestId").isString())
                .andExpect(jsonPath("$.requestId").value("req-123"));

        verify(service).page();
    }

    @Test
    void strictComparisonProtectsCompletePublicDto() throws Exception {
        when(service.find("SKU-001"))
                .thenReturn(Optional.of(ProductFixtures.first()));

        mvc.perform(get("/api/products/SKU-001"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "sku": "SKU-001",
                          "title": "Spring Testing",
                          "price": {
                            "amount": 19.90,
                            "currency": "USD"
                          },
                          "available": true
                        }
                        """, JsonCompareMode.STRICT));
    }

    @Test
    void lenientComparisonCanCheckStableSubset() throws Exception {
        when(service.find("SKU-001"))
                .thenReturn(Optional.of(ProductFixtures.first()));

        mvc.perform(get("/api/products/SKU-001"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "sku": "SKU-001",
                          "available": true
                        }
                        """, JsonCompareMode.LENIENT))
                .andExpect(jsonPath("$.secretToken")
                        .doesNotHaveJsonPath());
    }

    @Test
    void missingProductHas404WithoutExpectingJsonBody()
            throws Exception {
        when(service.find("UNKNOWN"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/products/UNKNOWN"))
                .andExpect(status().isNotFound());

        verify(service).find("UNKNOWN");
    }
}
```

**Những rủi ro được bảo vệ:**

1. `checksRequiredPropertiesAndTypes` kiểm value, JSON types, object nesting, MediaType và sự vắng mặt của hai field nhạy cảm.
2. `checksCollectionShapeWithoutAssumingOrder` kiểm mảng có đúng hai phần tử, hai SKU mong đợi, số `total` và `requestId`; không lệ thuộc thứ tự phần tử khi contract chưa quy định.
3. `strictComparisonProtectsCompletePublicDto` kiểm toàn bộ public DTO một cách strict theo cấu trúc JSON, không phải raw string.
4. `lenientComparisonCanCheckStableSubset` kiểm subset ổn định; thêm negative assertion vì LENIENT cho phép thêm fields.
5. `missingProductHas404WithoutExpectingJsonBody` phân biệt status lỗi và body: test không giả định controller luôn trả JSON error object.

Tất cả test dùng `@MockitoBean` vì `@WebMvcTest` không scan service như full context. Đây là **HTTP serialization contract test của controller**, không chứng minh logic truy vấn repository của service thật.

### 7.11. ProductViewJsonTest: @JsonTest kiểm Jackson độc lập HTTP

`src/test/java/com/example/jsoncontract/ProductViewJsonTest.java`:

```java
package com.example.jsoncontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class ProductViewJsonTest {

    @Autowired
    JacksonTester<ProductView> json;

    @Test
    void writesPublicProductStructure() throws Exception {
        ProductView product = ProductFixtures.first();

        assertThat(json.write(product)).isEqualToJson("""
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """);

        assertThat(json.write(product))
                .extractingJsonPathStringValue("@.sku")
                .isEqualTo("SKU-001");

        assertThat(json.write(product))
                .extractingJsonPathNumberValue("@.price.amount")
                .satisfies(value -> assertThat(
                        value.doubleValue()).isEqualTo(19.9));
    }

    @Test
    void readsDtoFromJson() throws Exception {
        String body = """
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """;

        ProductView parsed = json.parseObject(body);

        assertThat(parsed.sku()).isEqualTo("SKU-001");
        assertThat(parsed.title()).isEqualTo("Spring Testing");
        assertThat(parsed.price().amount())
                .isEqualByComparingTo("19.90");
        assertThat(parsed.price().currency()).isEqualTo("USD");
        assertThat(parsed.available()).isTrue();
    }
}
```

`@JsonTest` chỉ nạp JSON serialization support và JSON helper, không chạy servlet/HTTP. Với `JacksonTester`, `assertThat(json.write(...)).isEqualToJson(...)` dùng JSON-aware comparison; `extractingJsonPathStringValue`/`NumberValue` kiểm property cụ thể. `json.parseObject(...)` kiểm deserialization.

**Lưu ý số:** ví dụ test số dùng `19.9` có biểu diễn chính xác tới mức cần thiết cho fixture này, nhưng đây không phải mẫu đo tiền trong production. Với `BigDecimal`, phép kiểm `isEqualByComparingTo` thích hợp hơn, tránh phụ thuộc scale. Với số floating-point tính toán qua nhiều phép toán, dùng tolerance rõ thay vì equality.

### 7.12. ProductJsonTreeIntegrationTest: context thật và JsonNode

`src/test/java/com/example/jsoncontract/ProductJsonTreeIntegrationTest.java`:

```java
package com.example.jsoncontract;

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductJsonTreeIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void checksNestedAmountSemantically() throws Exception {
        String body = mvc.perform(get("/api/products/SKU-001")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);

        assertThat(root.isObject()).isTrue();
        assertThat(root.path("sku").asText()).isEqualTo("SKU-001");
        assertThat(root.path("price").isObject()).isTrue();

        JsonNode amount = root.at("/price/amount");
        assertThat(amount.isNumber()).isTrue();

        BigDecimal money = amount.decimalValue();
        assertThat(money.compareTo(new BigDecimal("19.90")))
                .isZero();

        assertThat(root.path("available").isBoolean()).isTrue();
        assertThat(root.path("available").booleanValue()).isTrue();

        assertThat(root.has("internalCost")).isFalse();
        assertThat(root.has("secretToken")).isFalse();
    }

    @Test
    void checksPageMembersAndItemBusinessInvariant()
            throws Exception {
        String body = mvc.perform(get("/api/products"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);
        JsonNode items = root.path("items");

        assertThat(root.isObject()).isTrue();
        assertThat(items.isArray()).isTrue();
        assertThat(items.size()).isEqualTo(2);
        assertThat(root.path("total").isInt()).isTrue();
        assertThat(root.path("total").intValue()).isEqualTo(2);
        assertThat(root.path("requestId").asText())
                .matches("req-[0-9]+");

        int availableItems = 0;
        for (JsonNode item : items) {
            assertThat(item.path("sku").isTextual()).isTrue();
            assertThat(item.path("price").path("amount").isNumber())
                    .isTrue();
            assertThat(item.path("price").path("currency").asText())
                    .isEqualTo("USD");
            if (item.path("available").asBoolean()) {
                availableItems++;
            }
        }
        assertThat(availableItems).isEqualTo(1);
    }
}
```

Khác với MVC slice, test này dùng `ProductService` thật và Boot/Jackson HTTP components thật, nhưng vẫn mock servlet requests, **không** mở HTTP socket. Nó kiểm nested numeric semantics, regex `requestId` và invariant của danh sách, đồng thời bảo vệ sự vắng mặt của internal fields.

`JsonNode.path(...).asText()` có thể trả chuỗi rỗng cho missing node, vì vậy khi field là critical nên check thêm `isTextual()`/`has(...)` trước khi kiểm giá trị. Với field `requestId` ở đây, regex không cho chuỗi rỗng; khi contract yêu cầu type string, nên bổ sung `isTextual()` nữa.

### 7.13. Chạy thử

Trong thư mục `json-structure-lab`, có JDK 17+, Maven và dependency repository truy cập được:

```bash
mvn -q clean test

mvn -q -Dtest=ProductControllerJsonContractTest test
mvn -q -Dtest=ProductViewJsonTest test
mvn -q -Dtest=ProductJsonTreeIntegrationTest test
```

Ba lớp được thiết kế PASS trên Spring Boot 3.5.16. Lệnh Maven thành công trả exit code **0**; số lượng log và thời gian chạy phụ thuộc môi trường. File reports ở `target/surefire-reports`. Test Maven đã được thiết kế với imports và paths tương ứng nhưng kết quả runtime thực tế phải được xác minh bằng chạy build trong môi trường dự án của bạn.

Chạy ứng dụng thật:

```bash
mvn spring-boot:run
```

Rồi mở terminal khác:

```bash
curl "http://localhost:8080/api/products/SKU-001"
curl "http://localhost:8080/api/products"
```

Response đầu tiên có `sku="SKU-001"`, `title="Spring Testing"`, `price.amount=19.90`, `available=true`. Response thứ hai chứa hai items, `total=2` và `requestId="req-123"`. Thứ tự các JSON object keys/format whitespace không phải phần được cam kết.

## 8. MockMvcTester (Spring Framework 6.2+) như lựa chọn AssertJ-friendly

Với Spring Boot 3.4+/Framework 6.2+, `MockMvcTester` cung cấp API AssertJ thuận tiện:

```java
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import static org.assertj.core.api.Assertions.assertThat;

// Bên trong @WebMvcTest và đã @Autowired MockMvcTester tester
assertThat(tester.get().uri("/api/products/SKU-001"))
        .hasStatusOk()
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .bodyJson()
        .extractingPath("$.sku")
        .asString()
        .isEqualTo("SKU-001");
```

Đây là **snippet**, không phải file test độc lập: cần service được stub trong `@WebMvcTest`. Trong Spring Boot 3.5, khi AssertJ có mặt, `@WebMvcTest` auto-configure tester; `@SpringBootTest` cần `@AutoConfigureMockMvc`.

### 8.1. So cả JSON

```java
assertThat(tester.get().uri("/api/products/SKU-001"))
        .hasStatusOk()
        .bodyJson()
        .isStrictlyEqualTo("""
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """);
```

`bodyJson().isStrictlyEqualTo` so JSON theo cấu trúc; không so raw string. Khi chỉ kiểm subset, dùng `isLenientlyEqualTo` hoặc `extractingPath`. Đừng dùng strict golden file cho fields biến động như timestamp, UUID nếu business contract chỉ yêu cầu format/độ duy nhất.

### 8.2. Một request, nhiều assertions

```java
MvcTestResult result = tester.get()
        .uri("/api/products/SKU-001")
        .exchange();

assertThat(result).hasStatusOk();

assertThat(result).bodyJson()
        .extractingPath("$.price.currency")
        .asString()
        .isEqualTo("USD");
```

Với một request có side effects, lưu `MvcTestResult` rồi dùng nhiều assertion giúp tránh vô tình thực thi request nhiều lần.

## 9. WebFlux: cùng tư duy, khác client API

Ứng dụng Spring WebFlux dùng `WebTestClient` (không phải `MockMvc`). Ví dụ **minh họa** dưới đây giả định đã có WebFlux controller/`@WebFluxTest` với `WebTestClient client` và endpoint `/api/products`:

```java
client.get()
        .uri("/api/products")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.items").isArray()
        .jsonPath("$.items[0].sku").isEqualTo("SKU-001")
        .jsonPath("$.total").isNumber();
```

Nếu endpoint thực không bảo đảm order, đừng dùng index 0. Bạn có thể lấy body thành `byte[]` rồi parse bằng Jackson `JsonNode` và kiểm membership bất kể thứ tự, hoặc dùng matchers cho JSONPath array:

```java
client.get().uri("/api/products")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {"total":2}
                """, JsonCompareMode.LENIENT);
```

Spring Framework 6.2 có `WebTestClient.BodyContentSpec.json(expected, JsonCompareMode)`. Với WebFlux slice, collaborator service cần mock nếu slice không scan service, tương tự MVC slice nhưng dùng reactive types của service.

**Không** thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` vào project Maven ở phần 7 chỉ để chạy hai ví dụ trong cùng context; Boot thường chọn MVC khi cả hai stacks có mặt. Hãy chọn đúng web application type và test client cho module của bạn.

## 10. Kiểm định schema: khi cấu trúc lớn và có hợp đồng chính thức

### 10.1. JSON Schema giải quyết gì?

JSONPath assertions phù hợp vài field trọng yếu. Với payload lớn/được nhiều consumers sử dụng, **JSON Schema** có thể ràng buộc:

- Root object/array type.
- Các properties bắt buộc.
- Type, pattern, min/max, minimum/maximum.
- Array item type và cardinality.
- Nested object properties.
- Không cho properties không khai báo qua `additionalProperties: false`.
- Conditional fields qua `oneOf`/`anyOf`/`if/then/else` nếu thật cần.

Một JSON Schema **Draft 2020-12** tối giản cho `ProductView` (đây là tài liệu schema, không phải code phải thêm vào project mẫu):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["sku", "title", "price", "available"],
  "properties": {
    "sku": {
      "type": "string",
      "pattern": "^SKU-[0-9]{3}$"
    },
    "title": {
      "type": "string",
      "minLength": 1
    },
    "price": {
      "type": "object",
      "required": ["amount", "currency"],
      "properties": {
        "amount": {"type": "number", "minimum": 0},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}
      },
      "additionalProperties": false
    },
    "available": {"type": "boolean"}
  },
  "additionalProperties": false
}
```

Schema này bảo vệ cấu trúc, type, điều kiện bắt buộc, và loại field dư. Nhưng nó **không** chứng minh business rule “SKU-001 giá 19.90” vì schema cho phép mọi amount không âm. Cần thêm example assertions/contract tests theo business.

### 10.2. JSON Schema validator không tự đến từ Spring Boot test

`spring-boot-starter-test` mặc định **không phải** một validator JSON Schema Draft 2020-12 đầy đủ. Muốn test schema, hãy thêm một thư viện JSON Schema validator tương thích với draft và phiên bản JDK (ví dụ một implementation hiện hành được dự án chọn), rồi viết test assert schema-validation result. Đừng copy một import thư viện không có trong POM và coi file chạy được.

Nếu API được mô tả bằng OpenAPI, có thể dùng OpenAPI schema validators/contract tests ở boundary phù hợp, song vẫn cần định nghĩa **cụ thể những properties nào bắt buộc, nullable, readOnly, additionalProperties và versioning**. Các công cụ sinh schema khác nhau có thể xử lý null/optional/default khác nhau, phải kiểm theo version.

### 10.3. Closed schema vs backward compatibility

`additionalProperties: false` bảo đảm không có field ngoài whitelist, tốt với một số payload bảo mật. Nhưng nó cũng khiến consumer/test fail khi server bổ sung field mới mặc dù client không dùng field đó. Cân nhắc:
- Các response nhạy cảm: whitelist/closed schema có giá trị cao.
- Public API cần additive evolution: có thể chấp nhận extra fields cho backwards compatibility, đồng thời có **negative assertions** cho field nhạy cảm.
- Request input: đôi khi cần reject unknown fields để tránh mass assignment; đó là chính sách API riêng, không nên suy từ response tests.

Một schema quá chặt hoặc quá lỏng đều có rủi ro. Đưa ra quyết định bằng contract giữa producer và consumer.

## 11. JSON output có field biến động: kiểm định dạng, không hard-code giá trị

### 11.1. UUID, requestId và correlationId

Nếu API phát `requestId` mới cho mỗi request, đừng assert đúng một UUID cố định trừ khi test đã inject ID generator. Có thể dùng:

```java
JsonNode root = mapper.readTree(body);
String requestId = root.path("requestId").asText();

assertThat(root.path("requestId").isTextual()).isTrue();
assertThat(requestId).matches("[a-f0-9-]{36}");
```

Mẫu regex ở đây là **kiểm hình dạng tương đối lỏng**, không chứng minh UUID hợp lệ; khi contract thật đòi UUID, dùng `UUID.fromString(requestId)` và kiểm version/variant hoặc regex UUID đủ chặt. Nếu muốn deterministic assertions, inject một `IdGenerator`/`Clock` có thể thay thế trong test.

### 11.2. Timestamp và timezone

Dữ liệu ISO-8601 string có thể có offset/timezone khác nhưng cùng instant. Thay vì so raw text:

```java
String text = root.path("createdAt").asText();

Instant actualInstant = Instant.parse(text);
assertThat(actualInstant).isEqualTo(expectedInstant);
```

Đây là snippet **minh họa** khi endpoint có `createdAt` dạng UTC `Z` và test có `expectedInstant`. Nếu API cho phép offsets khác, dùng `OffsetDateTime.parse(text).toInstant()`. Khi test cần cùng một giờ cố định, inject `Clock.fixed(...)` để không phụ thuộc thời gian chạy. Cũng kiểm format/precision nếu contract có yêu cầu về milliseconds hoặc timezone cụ thể.

### 11.3. Giá trị enum

Java enum có thể serialize thành chuỗi `"ACTIVE"`, `"active"`, object hoặc alias tùy `@JsonValue`/`@JsonFormat`/custom serializer. Không assert chỉ “là string” nếu consumer cần chính xác `ACTIVE`:

```java
.andExpect(jsonPath("$.status").isString())
.andExpect(jsonPath("$.status").value("ACTIVE"))
```

Đây là snippet minh họa endpoint có `status`, không phải file trong project mẫu (Project ProductView có `available` boolean). Nếu API đổi tên enum, test phải fail hoặc hợp đồng versioning phải được cập nhật.

### 11.4. Optional và null policy

Jackson có thể bỏ qua null fields khi cấu hình `@JsonInclude(JsonInclude.Include.NON_NULL)` hoặc Boot ObjectMapper setting. Khi test yêu cầu một property không bao giờ xuất hiện nếu null, assert `doesNotHaveJsonPath()`; khi yêu cầu property tồn tại với JSON null, assert `hasJsonPath()` và kiểm null qua JsonNode. Không sử dụng `exists()` để kiểm một property mà contract cho phép JSON null — matcher đó yêu cầu non-null value.

## 12. Kiểm quan hệ giữa các fields và invariant

Một payload có thể có đúng kiểu từng field nhưng **sai quan hệ**.

### 12.1. total và items

```json
{
  "items": [
    {"sku":"SKU-001"},
    {"sku":"SKU-002"}
  ],
  "total": 5000
}
```

Đây không nhất thiết là bug: trong phân trang, `total` có thể nghĩa “tổng số toàn bộ dataset”, không phải `items.size()`. Phải đọc contract:
- `count` của current page → có thể bằng `items.size()`.
- `totalElements` toàn hệ thống → có thể lớn hơn `items.size()`.
- `pageSize` là giới hạn mong muốn, khác actual size ở trang cuối.
- `hasNext`/`nextCursor` có thể liên quan pagination window/cursor.

Đừng viết invariant sai chỉ vì hai số tên gần giống nhau. Trong project mẫu, `total=2` cố ý đại diện đúng hai items nhưng API thật có thể khác.

### 12.2. available và stock

Nếu API cam kết `available == (stock > 0)`, test nên assert cả quan hệ, không chỉ presence. Với JsonNode:

```java
int stock = root.path("stock").intValue();
boolean available = root.path("available").booleanValue();

assertThat(available).isEqualTo(stock > 0);
```

Đây là snippet khi endpoint thật có `stock` number, khác project mẫu. Check `isIntegralNumber()`/`isBoolean()` trước các phép `intValue`/`booleanValue` để tránh biến missing field thành default số/boolean gây false positive.

### 12.3. Nhận diện bản ghi trong array

Nếu API không bảo đảm order, dùng thuộc tính định danh:

```java
Map<String, JsonNode> bySku = new HashMap<>();
for (JsonNode item : root.path("items")) {
    String sku = item.path("sku").asText();
    assertThat(bySku.put(sku, item)).isNull();
}

assertThat(bySku.keySet())
        .containsExactlyInAnyOrder("SKU-001", "SKU-002");
assertThat(bySku.get("SKU-001")
        .path("price").path("currency").asText())
        .isEqualTo("USD");
```

Đoạn này cần imports `Map`, `HashMap`, `JsonNode` và AssertJ trong một test có `root` hợp lệ. Việc assert kết quả `put(...)` là null giúp phát hiện SKU trùng. Kiểm mảng bằng index0 dễ fail khi thứ tự thay đổi ngoài contract hoặc che duplicate data.

## 13. Những anti-pattern thường gặp

### 13.1. Chỉ assert HTTP status

`status().isOk()` không chứng minh JSON body đúng. Một endpoint có thể trả 200 với `{}` hoặc cấu trúc thay đổi nguy hiểm. Tối thiểu kiểm field định danh và thuộc tính chính.

### 13.2. So raw JSON string

JSON object key order và whitespace không có ý nghĩa nghiệp vụ trong đa số REST contracts. Dùng JSON compare/JSONPath/JsonNode thay vì `String.equals`, trừ khi byte-level representation là contract.

### 13.3. Dùng lenient để luôn có test xanh

LENIENT cho phép extra fields và non-strict array order. Nếu consumer cần sort hoặc security cần field vắng mặt, phải bổ sung explicit assertions hoặc STRICT/schema ở đúng chỗ.

### 13.4. Kiểm field sensitive bằng doesNotExist()

`doesNotExist()` chỉ đảm bảo không có non-null value ở path, nên field hiện hữu với null vẫn có thể pass. Khi field **không bao giờ được phép xuất hiện**, dùng `doesNotHaveJsonPath()`.

### 13.5. Dùng asText() khi chưa kiểm type/presence

`JsonNode.path("missing").asText()` có thể trả string rỗng. Đừng coi vậy là một string hợp lệ nếu contract yêu cầu field. Assert `has`/`isTextual` trước.

### 13.6. Assert array theo thứ tự ngẫu nhiên

Nếu DB không có ORDER BY hoặc collection là set, thứ tự JSON array có thể không ổn định. Assert membership/cardinality hoặc yêu cầu API thực sự cung cấp sort ổn định. Chỉ assert index khi thứ tự là contract.

### 13.7. So tiền bằng double hoặc BigDecimal.equals một cách vô thức

Đối với số tiền, `19.90` và `19.9` có thể cùng giá trị, nhưng `BigDecimal.equals` phân biệt scale. Dùng `compareTo` cho numeric value; thêm assertion scale/format nếu contract có yêu cầu. Tránh phép tính float/double cho số tiền.

### 13.8. Mock chính object đang cần serialize

Nếu bạn mock `ObjectMapper` trong `@WebMvcTest` khi đang kiểm JSON serialization, test không còn chứng minh mapping thực tế. Giữ Jackson HTTP infrastructure thật; chỉ mock service/repository collaborator theo boundary.

### 13.9. Đặt toàn bộ expected JSON trong một test khó đọc

Một golden JSON vài nghìn dòng có thể rất brittle. Chia test:
- Critical fields/cấu trúc.
- Security-negative fields.
- Schema compatibility.
- Snapshot/strict complete payload khi cần.

Golden file vẫn hữu ích cho representation lớn ổn định, nhưng phải review diff thật; không tự động “update snapshots” khi mọi test fail.

### 13.10. Bỏ qua Content-Type và status của lỗi

Một body giống JSON có thể được gửi với `text/plain`, làm client parse khác kỳ vọng; error payload có thể cần `application/problem+json`. Hãy kiểm status + media type ở boundary, không chỉ nội dung.

### 13.11. Tin DTO equality chứng minh wire contract

`assertEquals(expectedDto, actualDto)` trong Java có thể PASS dù Jackson đổi `@JsonProperty` từ `sku` sang `productCode`. Test serialization phải nhìn **JSON đã được tạo/response**. `@JsonTest` là lựa chọn tốt cho cấu hình Jackson; MVC test cho HTTP contract.

### 13.12. Dùng full @SpringBootTest cho mọi JSON assertion

Full context có thể tải DB, messaging, external clients không liên quan. Với controller response, `@WebMvcTest` nhanh/cô lập hơn; với DTO serialization `@JsonTest` nhẹ hơn. Dùng full context khi integration giữa các tầng là rủi ro cần kiểm.

### 13.13. Chỉ test happy path

Cần negative scenarios phù hợp:
- ID không tồn tại → status 404, không giả định JSON có body.
- Quyền truy cập không đủ → status 403 và không lộ data.
- Dữ liệu null/empty/optional → serialization đúng contract.
- Mảng rỗng → `[]` vs null vs absent.
- Number quá lớn, Unicode, timestamps, enum và nested objects.

Không nên biến mọi edge case thành một full integration test nếu vấn đề nằm ở một serializer cụ thể.

## 14. HTTP response lỗi, ProblemDetail và bảo mật

### 14.1. 4xx/5xx cũng có JSON contract

Một API có thể trả:

```json
{
  "type": "https://example.test/problems/invalid-input",
  "title": "Invalid input",
  "status": 400,
  "detail": "sku is required"
}
```

Nếu dùng Spring `ProblemDetail` hoặc error DTO, test nên kiểm status và các thuộc tính bắt buộc, không hard-code toàn bộ stack trace/time/machine hostname. Media type có thể là `application/problem+json`; check đúng contract của endpoint.

**Snippet minh họa** cho endpoint có error handler phù hợp:

```java
mvc.perform(get("/api/products/").accept(MediaType.APPLICATION_JSON))
        .andExpect(status().is4xxClientError())
        .andExpect(jsonPath("$.status").isNumber())
        .andExpect(jsonPath("$.title").isString());
```

Đây không phải assertion chạy được trên mọi ứng dụng: status của path thiếu segment có thể là 404, và Boot có thể không tự trả ProblemDetail trong mọi cấu hình. Dùng endpoint error cụ thể của project và kiểm actual handler response.

### 14.2. Không lộ secrets dù đang lỗi

Với exception unhandled, response không nên serialize stack trace, SQL query có secrets hoặc JWT/token. Test với contract thực:

```java
.andExpect(jsonPath("$.stackTrace").doesNotHaveJsonPath())
.andExpect(jsonPath("$.password").doesNotHaveJsonPath())
.andExpect(jsonPath("$.accessToken").doesNotHaveJsonPath())
```

Tuy nhiên những assertions ở root không chứng minh không có secrets trong nested `debug` object hoặc string `detail`. Với dữ liệu nhạy cảm, cân nhắc schema whitelist và scanning có chủ đích, không log toàn response thật từ CI lên nơi công khai.

### 14.3. 401/403 và security test setup

Nếu `@WebMvcTest` có Spring Security, unauthenticated request có thể bị 401, 403 hoặc redirect, không tới controller. Test JSON body khác khi security filter chặn. Dùng `spring-security-test` và principal/CSRF theo policy. Không tắt filter chain chỉ để status 200 khi mục tiêu bao gồm kiểm bảo mật.

## 15. Spring @JsonTest so với MVC và full-context

| Setup | Nạp gì? | Kiểm chứng chính | Không chứng minh |
| --- | --- | --- | --- |
| Plain JUnit + ObjectMapper | Jackson do test tự tạo | Serialization theo mapper đó | Boot mapper config nếu khác |
| `@JsonTest` + JacksonTester | JSON mapper/modules/components phù hợp | DTO serialize/deserialize | Controller route/status/security |
| `@WebMvcTest` + MockMvc | MVC slice, Jackson HTTP layer, controller, mocked collaborators | HTTP status/body/contract của controller | Business/persistence của mocked service |
| `@SpringBootTest + @AutoConfigureMockMvc` | Full Spring app context, MVC mock request | Real bean graph và HTTP serialization | Network/embedded server socket |
| `@SpringBootTest(RANDOM_PORT)` + client | Embedded server HTTP thật | HTTP transport và app wiring trong môi trường test | Gateway/TLS/deployment thật nếu không cấu hình |
| `@WebFluxTest + WebTestClient` | Reactive web slice | WebFlux request/response contract | Service/DB nếu collaborator mock |

Nếu mục tiêu là “Jackson đặt tên field có đúng không?”, `@JsonTest` là gần nhất. Nếu mục tiêu là “client GET endpoint nhận đúng JSON fields?”, `@WebMvcTest`. Nếu mục tiêu là “service thật tạo ra đúng dữ liệu và đưa qua controller?”, full context hoặc phối hợp unit/integration tests. Đừng suy luận test pass ở một boundary chứng minh boundary khác.

## 16. Các lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| `jsonPath("$.sku")` fail | Field thiếu, đổi tên, nằm ở path khác, body không JSON | In response test, parse JsonNode, xem DTO/mapper |
| `$.price.amount` bị xem string | Serializer biến BigDecimal thành text; custom converter | Kiểm config Jackson, `@JsonFormat` và schema |
| `$.available` fail `isBoolean` | API trả `"true"` string thay boolean | Kiểm DTO type và serializer |
| `$.items[0]` flaky | Thứ tự không được contract bảo đảm | `containsInAnyOrder` + size, hoặc thêm sort |
| `doesNotExist` PASS dù key có null | Matcher chỉ xét non-null | `doesNotHaveJsonPath` |
| JSON STRICT fail do field mới | Strict không cho extra property | Xác định extra field là breaking/security hay additive |
| JSON LENIENT PASS dù field nhạy cảm mới | Lenient cho extra properties | Negative assertions / schema whitelist |
| `@JsonTest` PASS nhưng MVC fail | MVC context dùng configuration khác, response wrapping/advice | Chạy MVC contract test và kiểm bean Jackson |
| Context fail trong `@WebMvcTest` | Controller collaborator thiếu trong slice | `@MockitoBean`/`@Import` đúng boundary |
| HTTP 401/403 thay 200 | Security/filter/CSRF | Setup authentication và policy |
| `JsonNode.asText()` rỗng | Field missing/null/type sai | Check `has/isTextual` trước |
| So BigDecimal fail dù 19.90 và 19.9 | Scale khác trong equals | `compareTo` hoặc `isEqualByComparingTo` |
| JSON date format khác giữa máy | Timezone/locale/Clock thiếu kiểm soát | Fix Clock/zone, parse ISO-8601 |
| Snapshot fail sau khi đổi UUID | Expected cố định trên field động | Regex/parser, inject deterministic generator |
| JSON Schema validator không compile | Chưa khai báo validator dependency | Chọn library + version/draft phù hợp |
| MockMvc test pass nhưng production trả HTML | Proxy/ingress/real server khác mock context | Bổ sung running-server/deployment test |

Khi debug, ghi lại **test boundary**, status, content type, actual JSON, path khác biệt và expected contract. Phân biệt:
- **Failed to load ApplicationContext**: dependency/config/slice fail trước body test.
- **AssertionFailedError**: test đã đến assertion nhưng output không khớp.
- **Controller exception**: business/runtime lỗi được map thành status hoặc truyền ra MockMvc.
- **JSON parse error**: response không phải JSON hợp lệ hoặc input/test data bị sai.

Không đọc stack trace rồi tự sửa expected theo actual để “xanh”; xác định contract trước.

## 17. Checklist cho người review JSON output tests

- [ ] Root của response là object hay array? Có được kiểm?
- [ ] Status và Content-Type được assert, đặc biệt trên 4xx/5xx?
- [ ] Các field bắt buộc đều tồn tại và đúng **JSON type**?
- [ ] Các field quan trọng được kiểm giá trị/ngữ nghĩa, không chỉ presence?
- [ ] Với nested object, đã kiểm parent object có mặt và path con đúng?
- [ ] Với array, đã kiểm cardinality và membership; order có phải contract?
- [ ] Missing và null có được phân biệt? Có dùng `doesNotHaveJsonPath` khi field phải vắng hoàn toàn?
- [ ] Các trường nhạy cảm `passwordHash`/`internalCost`/`secretToken` được bảo vệ?
- [ ] Chế độ STRICT/LENIENT được chọn có chủ đích?
- [ ] Tiền tệ, decimal precision, timezone, enum casing được kiểm đúng business?
- [ ] Generated timestamp/UUID có deterministic fixture hoặc format assertion phù hợp?
- [ ] Có kiểm relationship/invariant giữa các field khi contract yêu cầu?
- [ ] `@JsonTest`/`@WebMvcTest`/`@SpringBootTest` được chọn đúng phạm vi?
- [ ] Mock collaborator là bean Spring qua `@MockitoBean` khi cần?
- [ ] Có tách JSON serializer test khỏi service business test nếu cần?
- [ ] Có test negative/error/empty/null cases phù hợp, không chỉ happy path?
- [ ] Có tránh raw string equality và cập nhật snapshot tự động mà không review?
- [ ] JSON Schema nếu dùng có validator dependency tương thích draft?
- [ ] Test chạy trên Maven/Gradle cùng dependency management với CI?
- [ ] Khi test fail, có đối chiếu với OpenAPI/consumer contract trước khi sửa?

**Kết luận:** Kiểm JSON đầu ra chất lượng không phải chụp lại một chuỗi JSON dài, mà là **xác minh hợp đồng cấu trúc, type, dữ liệu quan trọng, quan hệ giữa fields và sự vắng mặt của dữ liệu không được phép**. Dùng JSONPath cho những path trọng tâm, JSON-aware STRICT/LENIENT khi so toàn object, `JsonNode` cho kiểm tra ngữ nghĩa linh hoạt, `@JsonTest` cho Jackson và MVC/WebFlux tests cho HTTP boundary. Luôn nghiêm ở field mà consumer phụ thuộc, và tránh brittle assertions với thứ tự key, whitespace, giá trị sinh ngẫu nhiên.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Auto-configured JSON Tests / JacksonTester: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — MockMvc Hamcrest expectations: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/expectations.html
- Spring Framework 6.2 — MockMvc AssertJ / MockMvcTester JSON support: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/assertions.html
- Spring Framework 6.2 — JsonCompareMode API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/json/JsonCompareMode.html
- Spring Framework 6.2 — ContentResultMatchers.json API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html
- Spring Framework 6.2 — JsonPathResultMatchers API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html
- Spring Framework 6.2 — WebTestClient JSON assertions: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- Jackson Databind — JsonNode / ObjectMapper documentation: https://github.com/FasterXML/jackson-databind
- JSON Schema — Draft 2020-12: https://json-schema.org/draft/2020-12
- JSON Specification — RFC 8259: https://www.rfc-editor.org/rfc/rfc8259
