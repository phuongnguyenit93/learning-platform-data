# Spring Boot testing — Deserialize JSON hợp lệ, thiếu trường, sai kiểu hoặc dư trường

## 1. Bài toán cần giải quyết

Khi client gửi HTTP POST/PUT/PATCH với `Content-Type: application/json`, Spring MVC cần chuyển **chuỗi JSON** thành **đối tượng Java** trước khi controller gọi nghiệp vụ. Bốn tình huống quan trọng nhất là:

1. **Hợp lệ:** JSON đúng cú pháp, đúng kiểu/shape và thỏa business input constraints.
2. **Thiếu trường:** JSON không chứa một property mà API yêu cầu; Jackson vẫn có thể tạo DTO với `null` hoặc default primitive.
3. **Sai kiểu:** JSON không thể chuyển thành Java type đích, ví dụ `"quantity": "many"` trong DTO có `Integer quantity`.
4. **Dư trường:** JSON gửi property không có trong DTO, ví dụ `"isAdmin": true`; ứng dụng phải chọn **bỏ qua có chủ đích** hoặc **từ chối**.

Điểm then chốt là phân biệt hai bước **deserialize** và **validate**:

- **Jackson deserialization** trả lời: “JSON có thể tạo một giá trị Java thuộc type được khai báo không?”
- **Jakarta Bean Validation** trả lời: “Đối tượng Java vừa tạo có đáp ứng các ràng buộc đầu vào không?”
- **Controller/service domain validation** trả lời: “Dữ liệu hợp lệ về cấu trúc có được phép thực hiện nghiệp vụ này không?”

Một JSON có thể đọc được **nhưng vẫn không hợp lệ**. Ví dụ `{"sku":"SKU-1"}` có thể được Jackson chuyển thành record với `quantity == null`; chỉ khi có `@Valid` và `@NotNull` thì MVC mới từ chối với HTTP 400. Ngược lại, JSON sai cú pháp có thể bị từ chối **trước** khi Jakarta Validator có cơ hội hoạt động.

### Mục tiêu học tập

- Giải thích luồng `@RequestBody` → `HttpMessageConverter`/Jackson → DTO → `@Valid` → controller.
- Viết Java 17 `record`/POJO phù hợp để làm request DTO.
- Test JSON đúng, property thiếu, explicit `null`, chuỗi trắng, số ngoài biên.
- Test sai cú pháp, sai shape, sai kiểu mà Jackson không thể convert.
- Hiểu **numeric/string coercion**: khác kiểu JSON **không luôn** có nghĩa Jackson sẽ fail.
- Hiểu `FAIL_ON_UNKNOWN_PROPERTIES` và sự khác biệt giữa **Jackson thuần** với **ObjectMapper do Spring Boot 3.5 cấu hình**.
- Dùng `@JsonIgnoreProperties(ignoreUnknown = true)` khi API thực sự cho phép field dư.
- Chuẩn hóa lỗi bằng `@RestControllerAdvice`, không leak exception text, raw payload hoặc bí mật.
- Viết `@WebMvcTest` + `MockMvc` kiểm tra status, JSON response và việc service không bị gọi khi input sai.
- Biết lúc nào cần thêm `@SpringBootTest(RANDOM_PORT)` để kiểm tra HTTP thật.

## 2. Request body được xử lý ra sao?

Với controller:

```java
@PostMapping("/api/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // Chỉ chạy khi HTTP message converter đọc được JSON
    // và Bean Validation không phát hiện lỗi.
}
```

Luồng rút gọn:

```mermaid
flowchart TD
    A[HTTP request + Content-Type] --> B{Handler và converter phù hợp?}
    B -->|Không| C[415 Unsupported Media Type hoặc lỗi routing]
    B -->|Có| D[Jackson đọc cú pháp và cấu trúc JSON]
    D -->|Không đọc được| E[HttpMessageNotReadableException]
    D -->|Đọc được| F[Tạo Java request DTO]
    F --> G{@Valid và Bean Validation hợp lệ?}
    G -->|Sai| H[MethodArgumentNotValidException]
    G -->|Đúng| I[Controller xử lý]
    E --> J[Advice: 400 INVALID_JSON]
    H --> K[Advice: 400 VALIDATION_ERROR]
    I --> L[HTTP 201/200 hoặc domain response]
```

Sơ đồ trên tập trung vào **MVC + một validated command object**. Một controller có direct method-level constraints có thể chạy `HandlerMethodValidationException`; controller có `BindingResult` ngay sau parameter có thể xử lý lỗi cục bộ. Đây là các trường hợp khác, không biến mọi input error thành `MethodArgumentNotValidException`.

### Hai lớp lỗi thường bị gộp nhầm

| Tình huống | Jackson tạo DTO? | Bean Validation chạy? | Exception điển hình |
| --- | --- | --- | --- |
| JSON hợp lệ và đủ giá trị | Có | Có nếu `@Valid` | Không lỗi |
| Thiếu `quantity` kiểu `Integer` | Thường có, field là `null` | Có nếu `@Valid` | `MethodArgumentNotValidException` do `@NotNull` |
| Có `"quantity":null` | Thường có, field là `null` | Có nếu `@Valid` | `MethodArgumentNotValidException` do `@NotNull` |
| `"quantity":0`, yêu cầu ≥1 | Có | Có | `MethodArgumentNotValidException` do `@Min` |
| `"quantity":"many"` | Không chuyển được kiểu số | Không đến validation DTO | `HttpMessageNotReadableException` |
| JSON `{not-json` | Không parse được | Không | `HttpMessageNotReadableException` |
| JSON là array thay vì object DTO | Thường không deserialize được | Không | `HttpMessageNotReadableException` |
| Trường không biết trong chế độ strict | Không | Không | `HttpMessageNotReadableException` (bọc lỗi Jackson unknown property) |
| Trường không biết trong chế độ lenient | Có, trường dư bị bỏ qua | Có nếu `@Valid` | Không lỗi chỉ vì trường dư |
| Body trống với `@RequestBody(required=true)` | Không | Không | Thường `HttpMessageNotReadableException` |
| `Content-Type: text/plain` cho endpoint chỉ nhận JSON | Chưa gọi JSON converter | Không | Thường HTTP 415 |

**Không phụ thuộc exception class ở tầng API:** exception Jackson như `MismatchedInputException`, `InvalidFormatException`, `UnrecognizedPropertyException` thường được bọc bên trong `HttpMessageNotReadableException` khi đi qua MVC. API nên trả một contract lỗi an toàn, trong khi test dùng status/code ổn định thay vì nội dung stack trace.

## 3. DTO hợp lệ và vai trò của Java records

Ví dụ request cho một đơn hàng:

```json
{
  "sku": "SKU-123",
  "quantity": 2,
  "address": {
    "city": "Da Nang"
  }
}
```

Java 17 record:

```java
public record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @NotNull @Valid Address address
) {
    public record Address(@NotBlank String city) {}
}
```

Đây là **trích đoạn** thiếu imports; bản đầy đủ trong mục 9.

- `record` định nghĩa components, canonical constructor và accessors như `sku()`, `quantity()`, `address()`.
- Jackson 2.x tương thích trong Spring Boot 3.5 có thể deserialize JSON object thành Java record khi tên JSON khớp record components.
- `@NotBlank` cấm `null`, `""`, chuỗi toàn khoảng trắng.
- `@NotNull @Min(1) Integer quantity` đồng thời đòi field có giá trị và ít nhất 1.
- `@NotNull @Valid Address address` vừa bắt buộc object không null, vừa đi sâu validate `address.city`.
- `@Valid` tự nó là **cascade instruction**, không làm một object nullable trở thành mandatory.
- Jackson không tự gọi Bean Validation chỉ vì annotations tồn tại trong class; integration MVC phải đặt `@Valid`/`@Validated` ở đúng controller argument, và có validation provider trong dependencies.

### Vì sao chọn Integer thay vì int cho field bắt buộc?

`Integer` biểu diễn được `null`, nhờ đó `@NotNull` phân biệt “client không gửi số lượng” với “client gửi 0”. Nếu dùng primitive `int`, với cấu hình Jackson 2 phổ biến, property thiếu hoặc JSON null có thể trở thành default `0` (trừ khi bật các chế độ fail thích hợp). Với quy tắc `@Min(0)`, số 0 đó còn có thể vượt validation dù input thực sự thiếu.

**Khuyến nghị:** với input bắt buộc cần xác định sự hiện diện, dùng wrapper `Integer`/`Long`/`Boolean` và thêm `@NotNull`; với text bắt buộc dùng `@NotBlank`; sau khi validation thành công mới chuyển qua domain types phù hợp.

### Không bind trực tiếp entity JPA

Đừng nhận `@RequestBody UserEntity` nếu entity có `role`, `balance`, `isAdmin`, `creditLimit` hoặc field nội bộ có setter. Dùng request DTO chỉ chứa các properties mà endpoint cho phép; DTO validation và domain authorization là hai lớp trách nhiệm khác nhau.

Nếu client gửi `"isAdmin":true`, trong DTO không có `isAdmin` thì strict mapper từ chối hoặc lenient mapper bỏ qua — **không bao giờ** tự gán quyền admin chỉ vì JSON có field đó.

## 4. Thiếu trường, explicit null và default: khác nhau như thế nào?

Xem ba JSON:

```json
{"sku":"SKU-123","address":{"city":"Da Nang"}}
```

```json
{"sku":"SKU-123","quantity":null,"address":{"city":"Da Nang"}}
```

```json
{"sku":"SKU-123","quantity":0,"address":{"city":"Da Nang"}}
```

Trong record có `Integer quantity`, Jackson thường cho `null` với **missing** hoặc **explicit null**. Bean Validation sau đó đánh dấu `@NotNull` cho hai trường hợp đầu, và `@Min(1)` cho trường hợp thứ ba.

| Dạng input | Java quantity sau Jackson | Constraint fail | Ý nghĩa |
| --- | --- | --- | --- |
| Thiếu property | `null` | `@NotNull` | Client không gửi trường |
| `"quantity":null` | `null` | `@NotNull` | Client gửi null |
| `"quantity":0` | `0` | `@Min(1)` | Giá trị số ngoài miền |
| `"quantity":1` | `1` | Không | Biên dưới hợp lệ |
| `"quantity":10` | `10` | Không nếu `@Max(10)` | Biên trên hợp lệ |
| `"quantity":11` | `11` | `@Max(10)` | Vượt biên |
| `"quantity":"many"` | Không tạo DTO thành công | Không | Jackson không convert được |

**Lưu ý:** đối tượng đích kiểu Java record không tự bảo đảm mọi property có mặt. Với Jackson 2.x, `DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES` thường **tắt theo mặc định**, trừ khi property/creator được khai báo required theo contract cụ thể. Chính sách đầy đủ cho missing creators khác Bean Validation; không dùng nó thay cho `@NotNull` trong mọi API.

### Khi ứng dụng thật phải phân biệt “không gửi” với “gửi null”

Ví dụ PATCH: thiếu `displayName` nghĩa là “giữ nguyên”, nhưng `"displayName":null` nghĩa là “xóa tên”. Record với `String displayName` không giữ được thông tin presence vì cả hai có thể thành null. Các lựa chọn:

- Đọc `JsonNode` và dùng `has("displayName")` (presence) và `isNull()` (explicit null).
- Dùng kiểu wrapper theo hệ thống có **ba trạng thái**: undefined, explicit null, value.
- Định nghĩa JSON Merge Patch (RFC 7396), JSON Patch (RFC 6902) hoặc một DTO PATCH chuyên biệt với semantics rõ ràng.

Không nhầm `Optional<String>` trong request DTO với giải pháp đầy đủ cho PATCH presence: tùy deserializer/config, Optional empty có thể biểu diễn cả missing và explicit null. Hãy **test bằng chứng** cho từng trạng thái nếu API cần phân biệt.

### Annotation @JsonProperty(required=true) có phải @NotNull?

Không. `@JsonProperty(required=true)` là metadata của Jackson, có thể được dùng để yêu cầu creator property tồn tại trong một số cơ chế deserialize. Nó không thay thế Jakarta Bean Validation và không đương nhiên bảo đảm mọi field/setter property không null. Ngược lại, `@NotNull` là constraint của validation provider và chỉ có tác dụng khi validation được kích hoạt.

Không kết hợp các annotation này tùy tiện rồi suy luận một loại lỗi duy nhất: **lỗi “missing creator property” xảy ra trong Jackson**, còn **lỗi `@NotNull` xảy ra sau khi DTO đã được tạo**. API có thể map cả hai thành 400 nhưng nên test mỗi cơ chế.

## 5. Sai kiểu: Jackson có thể từ chối hoặc tự chuyển đổi

Các request sau không có cùng kết quả:

```json
{"sku":"SKU-123","quantity":"many","address":{"city":"Hue"}}
```

```json
{"sku":"SKU-123","quantity":"2","address":{"city":"Hue"}}
```

```json
{"sku":"SKU-123","quantity":2.5,"address":{"city":"Hue"}}
```

```json
{"sku":"SKU-123","quantity":[],"address":{"city":"Hue"}}
```

- `"many"` → `Integer` thường **không parse được** và sẽ gây lỗi deserialization.
- `"2"` → `Integer` **có thể được Jackson 2.x chấp nhận qua coercion** nếu cấu hình cho phép.
- `2.5` → số nguyên có thể bị truncate/convert hoặc bị từ chối tùy `ACCEPT_FLOAT_AS_INT`/coercion settings.
- `[]` → `Integer` thường mismatch, nhưng các tính năng empty-array-as-null và custom deserializer có thể thay behavior.

**Quan trọng:** đừng viết test “mọi giá trị chuỗi cho Integer phải 400” khi chưa tắt coercion. Điều chính xác cần kiểm là **policy của API**. Bài mẫu kiểm tra `"many"` và một JSON array ở top-level, là hai trường hợp rõ ràng không phù hợp với DTO record.

### Các Jackson 2.x flags liên quan

| Cấu hình | Tác dụng | Hệ quả |
| --- | --- | --- |
| `FAIL_ON_UNKNOWN_PROPERTIES` | Từ chối property không thuộc DTO | Dư trường → Jackson error |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | Từ chối JSON null cho primitive | Tránh null biến thành 0/false |
| `FAIL_ON_MISSING_CREATOR_PROPERTIES` | Yêu cầu các creator properties hiện diện | Missing constructor input → Jackson error |
| `FAIL_ON_NULL_CREATOR_PROPERTIES` | Từ chối null creator property | JSON null creator input → Jackson error |
| `ACCEPT_FLOAT_AS_INT` | Cho phép convert float thành integer | Dễ gây mất phần thập phân nếu bật |
| `ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` | Đối xử chuỗi rỗng theo null cho một số object types | Cần xác định đúng phạm vi |
| `FAIL_ON_TRAILING_TOKENS` | Từ chối ký tự/token dư sau root JSON value | Ví dụ `{} {}` không bị đọc như một document hợp lệ |
| `JsonParser.Feature.STRICT_DUPLICATE_DETECTION` | Phát hiện JSON object field name lặp | Hữu ích cho API yêu cầu không có duplicate keys |

Tùy Jackson minor version và deserializer, có thêm API `CoercionConfig` để quản lý coercion theo input shape/target type. Không phải mọi cờ áp dụng giống nhau cho `int`, `Integer`, enum, date, collection hoặc custom class. Khi cấu hình stricter, hãy dùng **test nhỏ xác định behavior mong muốn**, tránh thay toàn bộ ObjectMapper rồi gây hồi quy ở các APIs khác.

### Dùng ObjectMapper nào trong Spring MVC?

Một lỗi thường gặp là test:

```java
ObjectMapper mapper = new ObjectMapper();
```

rồi kết luận Spring MVC cũng làm y hệt. Điều đó **không luôn đúng**: ObjectMapper do Spring Boot auto-configure có các defaults/customizers, Java time modules, naming strategy và feature flags từ `application.properties`. Bài mẫu kiểm tra cả Jackson thuần và `ObjectMapper` Spring Boot cung cấp để minh họa sự khác biệt.

## 6. Dư trường: điểm khác nhau giữa Jackson thuần và Spring Boot

Giả sử DTO chỉ có ba fields `sku`, `quantity`, `address`, nhưng client gửi:

```json
{
  "sku":"SKU-123",
  "quantity":2,
  "address":{"city":"Hue"},
  "isAdmin":true
}
```

Jackson 2.x `new ObjectMapper()` mặc định có `FAIL_ON_UNKNOWN_PROPERTIES=true`; property dư có thể khiến `UnrecognizedPropertyException`. Nhưng **Spring Boot 3.x mặc định cấu hình Jackson mapper với `FAIL_ON_UNKNOWN_PROPERTIES=false`**, vì vậy các trường dư thường được bỏ qua khi không có cấu hình strict khác.

Để một API **chủ động từ chối trường không khai báo**, bật:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Trong dự án mẫu, thuộc tính này nằm ở `src/test/resources/application-test.properties` và test kích hoạt `@ActiveProfiles("test")`. Không suy đoán về policy từ “default Jackson” mà không kiểm tra property của **Boot-configured ObjectMapper**. Khi áp dụng vào production, đặt strict policy nhất quán trong config production/contract nếu thật sự muốn client ngoài chịu ràng buộc này.

### Khi nào nên strict?

- Write APIs (create/update) yêu cầu contract rõ và muốn phát hiện client gõ nhầm `quantity` thành `quanity`.
- Các trường dư có thể biểu thị client hiểu sai domain hoặc payload attack/over-posting.
- Muốn tránh lỗi “request vẫn 200 nhưng thuộc tính người dùng tưởng đã lưu thực ra bị bỏ qua”.

**Nhược điểm:** thêm một trường hợp lệ ở client version mới có thể làm server cũ từ chối payload. Các API ưu tiên forward compatibility đôi khi chủ động cho phép field dư. Quyết định strict/lenient phải thuộc **API versioning policy**, không phải lựa chọn ngẫu nhiên của từng developer.

### Lenient một loại DTO, không mở lỏng cả API

Với loại payload cho phép mở rộng, có thể viết:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public record LenientPreviewRequest(String sku, Integer quantity) {
}
```

`@JsonIgnoreProperties(ignoreUnknown = true)` cho phép Jackson bỏ qua unknown properties **ở type đó**, kể cả khi mapper chung đang strict. Bài mẫu dùng endpoint `/api/orders/preview` để chứng minh khác biệt này một cách có chủ đích.

**Không nhầm với:**
- `@JsonIgnore`: bỏ qua một property đã biết trong mô hình JSON, không phải bỏ qua mọi unknown field.
- `@JsonProperty("snake_case_name")`: đặt tên mapping của một property, không mở thêm arbitrary properties.
- `@JsonAlias({"legacyName"})`: chấp nhận tên thay thế lúc deserialize, không giữ giá trị field dư tùy ý.
- `@JsonAnySetter`: tiếp nhận các unknown fields vào map/handler có chủ đích, không đồng nghĩa bỏ qua.
- `@JsonIgnoreProperties(value={"internalField"})`: khai báo property bị ignore, khác với `ignoreUnknown=true`.

Nếu cần thu thập metadata mở rộng, dùng `Map<String,Object>` hoặc `@JsonAnySetter` và kiểm tra giới hạn kích thước/định dạng/allowlist. Không để trường dư trực tiếp tác động permission, giá, trạng thái đơn hàng hoặc security-sensitive logic.

## 7. Chính sách HTTP error: 400 không đủ để kết luận

Bài mẫu chọn hai mã lỗi:

| API code | HTTP status | Tình huống | Giai đoạn |
| --- | --- | --- | --- |
| `INVALID_JSON` | 400 | JSON syntax sai, mismatch kiểu, unknown property bị cấm, body thiếu | Jackson/message converter |
| `VALIDATION_ERROR` | 400 | DTO tạo được nhưng có `@NotBlank`, `@NotNull`, `@Min`, `@Max` fail | Jakarta Validation |

Và một số lỗi khác **không** bị gộp thành hai mã trên:

| Trường hợp | HTTP status thường phù hợp | Vì sao |
| --- | --- | --- |
| `Content-Type: text/plain` cho JSON-only endpoint | 415 | Không có converter phù hợp với consumes |
| HTTP method không hỗ trợ | 405 | Sai route contract, không phải JSON |
| URL endpoint không tồn tại | 404 | Không có handler |
| Client chưa xác thực | 401 | Security, không phải validation |
| Client không đủ quyền | 403 | Authorization, không phải JSON |
| Resource conflict/đã tồn tại | 409 | Domain policy |
| Server bug, DB outage hoặc serialization lỗi response | 5xx phù hợp | Không tự biến thành lỗi input |
| `@Valid` với DTO hợp lệ nhưng nghiệp vụ cấm thao tác | Theo domain contract, ví dụ 409/422 | Bean Validation không thay business rules |

Trả error body ổn định và không lộ chi tiết như:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "quantity",
      "message": "quantity is required"
    }
  ]
}
```

Với Jackson parse exception:

```json
{
  "code": "INVALID_JSON",
  "errors": [
    {
      "field": "body",
      "message": "JSON body is invalid or missing"
    }
  ]
}
```

Không gửi `JsonMappingException.getPathReference()`, raw input, rejected password/token hay stack trace ra client. Nếu sản phẩm dùng RFC 9457 `ProblemDetail`, có thể dùng format chuẩn đó cùng stable error codes; quan trọng là test **một hợp đồng API đã thống nhất**.

## 8. Project chạy được: Java 17, Spring Boot 3.5, Maven

Project này cố ý dùng **Spring MVC + Mockito test**, không có database. Nó giúp phân biệt Jackson/validation/network error mà không nhiễu bởi SQL, transaction hay external services.

Các endpoint:

| Endpoint | Ý nghĩa | Kỳ vọng |
| --- | --- | --- |
| `POST /api/orders` | Strict JSON DTO, validate sku/quantity/address | 201 + `{"id":...}` khi đúng |
| `POST /api/orders` | Thiếu field, null hoặc value out-of-range | 400 + `VALIDATION_ERROR` |
| `POST /api/orders` | Syntax sai, type mismatch, unknown property | 400 + `INVALID_JSON` |
| `POST /api/orders/preview` | Lenient DTO bỏ qua unknown fields | 200 + echoed sku/quantity |
| JSON-only endpoint với `text/plain` | Media type không hợp lệ | 415 |

### 8.1. Cấu trúc tệp

```text
json-deserialize-demo/
├── pom.xml
└── src/
    ├── main/java/example/jsondemo/
    │   ├── JsonDemoApplication.java
    │   ├── CreateOrderRequest.java
    │   ├── LenientPreviewRequest.java
    │   ├── OrderService.java
    │   ├── OrderController.java
    │   ├── ApiError.java
    │   └── ApiExceptionAdvice.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/jsondemo/
            ├── OrderControllerTest.java
            ├── JacksonBasicsTest.java
            └── RealHttpJsonIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>json-deserialize-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-starter-validation` là dependency riêng: không giả định `spring-boot-starter-web` đã chứa provider. Validation annotations chỉ có ý nghĩa khi Jakarta Validation provider hoạt động và controller áp dụng `@Valid`. Parent Boot quản lý phiên bản Spring/Jackson/JUnit/Mockito.

### 8.3. application-test.properties

`src/test/resources/application-test.properties`:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.main.banner-mode=off
logging.level.org.springframework.web=WARN
```

**Policy của bài mẫu:** unknown JSON property bị từ chối theo mặc định trong test profile. Nếu production cũng phải strict, hãy cấu hình strict **ở production** theo contract; file test này không tự thay đổi behavior production.

### 8.4. Spring Boot application

`src/main/java/example/jsondemo/JsonDemoApplication.java`:

```java
package example.jsondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonDemoApplication.class, args);
    }
}
```

Đặt application và các classes dưới package `example.jsondemo` để component scan mặc định tìm được controller, advice và service.

### 8.5. Strict request DTO

`src/main/java/example/jsondemo/CreateOrderRequest.java`:

```java
package example.jsondemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank(message = "sku is required")
        @Size(min = 3, max = 20,
              message = "sku length must be between 3 and 20")
        String sku,

        @NotNull(message = "quantity is required")
        @Min(value = 1, message = "quantity must be at least 1")
        @Max(value = 10, message = "quantity must be at most 10")
        Integer quantity,

        @NotNull(message = "address is required")
        @Valid Address address
) {
    public record Address(
            @NotBlank(message = "city is required") String city) {
    }
}
```

Đây là DTO bất biến; bản demo không dùng constructor tùy biến hay business defaults. Vì thế Jackson có thể phân biệt shape/kiểu, Jakarta Validator kiểm tra ràng buộc, và test sẽ chỉ ra rõ chỗ lỗi.

### 8.6. DTO chỉ cho phép lenient

`src/main/java/example/jsondemo/LenientPreviewRequest.java`:

```java
package example.jsondemo;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LenientPreviewRequest(
        String sku, Integer quantity) {
}
```

Type này cố ý **không có các constraints**: endpoint preview chỉ minh họa Jackson có thể bỏ qua field dư với local annotation. Đây không phải mẫu DTO thích hợp cho một API ghi dữ liệu thật nếu chưa thêm validation/authorization rules.

### 8.7. Service không lưu DB để test tập trung JSON

`src/main/java/example/jsondemo/OrderService.java`:

```java
package example.jsondemo;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final AtomicLong ids = new AtomicLong(100);

    public long create(String sku, int quantity, String city) {
        // Demo: trả ID mới; không có database.
        return ids.incrementAndGet();
    }
}
```

Ở `@WebMvcTest`, `OrderService` sẽ được thay bằng `@MockitoBean`. Với real HTTP integration test, service thật chạy nhưng không có trạng thái business persistence để cleanup. Các trường `sku/quantity/city` chỉ được chuyển tới service sau khi request đã qua validation.

### 8.8. Controller: tạo đơn strict và preview lenient

`src/main/java/example/jsondemo/OrderController.java`:

```java
package example.jsondemo;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public record Created(long id) {
    }

    public record Preview(String sku, Integer quantity) {
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Created> create(
            @Valid @RequestBody CreateOrderRequest request) {
        long id = service.create(
                request.sku(),
                request.quantity(),
                request.address().city());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Created(id));
    }

    @PostMapping(
        path = "/preview",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public Preview preview(
            @RequestBody LenientPreviewRequest request) {
        return new Preview(request.sku(), request.quantity());
    }
}
```

Trong create method, `request.quantity()` được unbox thành `int` an toàn **chỉ khi** `@NotNull` đã được thực thi. Nếu xóa `@Valid`, client thiếu quantity có thể khiến code gặp `NullPointerException` hoặc gây side effect sai; test thiếu trường bên dưới nhằm phát hiện regression này.

### 8.9. Error DTO

`src/main/java/example/jsondemo/ApiError.java`:

```java
package example.jsondemo;

import java.util.List;

public record ApiError(
        String code,
        List<Violation> errors
) {
    public record Violation(String field, String message) {
    }
}
```

Mỗi response lỗi có code ổn định và field/message rõ ràng. Không có phần chứa raw JSON, rejected value hoặc exception stack trace.

### 8.10. @RestControllerAdvice

`src/main/java/example/jsondemo/ApiExceptionAdvice.java`:

```java
package example.jsondemo;

import java.util.Comparator;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> invalidJson(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_JSON",
                        List.of(new ApiError.Violation(
                                "body",
                                "JSON body is invalid or missing"))));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> validationFailure(
            MethodArgumentNotValidException exception) {

        List<ApiError.Violation> errors =
                exception.getBindingResult().getFieldErrors()
                        .stream()
                        .map(e -> new ApiError.Violation(
                                e.getField(), e.getDefaultMessage()))
                        .sorted(Comparator
                                .comparing(ApiError.Violation::field)
                                .thenComparing(ApiError.Violation::message))
                        .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_ERROR", errors));
    }
}
```

**Tại sao không trả `exception.getMessage()`?** Jackson error có thể chứa tên class, property path hoặc một phần giá trị trong payload. Production API nên trả một thông điệp hữu ích nhưng an toàn; logging phía server cũng cần che secrets khi nội dung nhạy cảm.

**Giới hạn có chủ đích:** handler chỉ gom `getFieldErrors()`. Khi bổ sung class-level/cross-field constraint, cần bổ sung `getGlobalErrors()` để client nhìn thấy những lỗi không gắn một property cụ thể. Mã bài mẫu chỉ dùng field constraints.

**Không** thêm một `@ExceptionHandler(Exception.class)` trả HTTP 400, vì 415/404/5xx và domain errors có semantics khác. Với Spring MVC built-in method validation trên parameter trực tiếp, thêm handler riêng cho `HandlerMethodValidationException` nếu API dùng mô hình đó.

## 9. MockMvc tests: chứng minh bốn tình huống input

Test quan trọng nhất dùng `@WebMvcTest(OrderController.class)`: khởi động MVC slice, có Jackson message converter và validator, nhưng **không** khởi động database hoặc service thực. `@MockitoBean` tạo mock service trong Spring test context; `verifyNoInteractions(service)` chứng minh dữ liệu sai bị chặn **trước business call**.

Tệp `src/test/java/example/jsondemo/OrderControllerTest.java`:

```java
package example.jsondemo;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@ActiveProfiles("test")
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    OrderService service;

    @Test
    void springBootMapperIsStrictBecauseTestProfileConfiguresIt() {
        assertTrue(mapper.isEnabled(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES));
    }

    @Test
    void validInputIsDeserializedAndPassedToService()
            throws Exception {
        when(service.create("SKU-123", 2, "Da Nang"))
                .thenReturn(101L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "address":{"city":"Da Nang"}}
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(101));

        verify(service).create("SKU-123", 2, "Da Nang");
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 10})
    void validBoundaryQuantitiesAreAccepted(int quantity)
            throws Exception {
        when(service.create("SKU-123", quantity, "Hue"))
                .thenReturn(102L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":%d,
                         "address":{"city":"Hue"}}
                        """.formatted(quantity)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(102));

        verify(service).create("SKU-123", quantity, "Hue");
    }

    @Test
    void missingQuantityBecomesValidationError()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123",
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("quantity is required"));

        verifyNoInteractions(service);
    }

    @Test
    void explicitNullQuantityAlsoFailsNotNull()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":null,
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 11})
    void outOfRangeQuantityFailsValidation(int quantity)
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":%d,
                         "address":{"city":"Hue"}}
                        """.formatted(quantity)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void missingSkuFailsNotBlank() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"quantity":2,"address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"));

        verifyNoInteractions(service);
    }

    @Test
    void blankSkuFailsNotBlank() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"   ","quantity":2,
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"));

        verifyNoInteractions(service);
    }

    @Test
    void missingAddressFailsNotNull() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address"));

        verifyNoInteractions(service);
    }

    @Test
    void missingCityIsFoundByNestedValidation()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,"address":{}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address.city"));

        verifyNoInteractions(service);
    }

    @Test
    void nonNumericQuantityFailsDuringDeserialization()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":"many",
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("body"));

        verifyNoInteractions(service);
    }

    @Test
    void topLevelArrayIsNotAnOrderRecord()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        [{"sku":"SKU-123","quantity":2,
                          "address":{"city":"Hue"}}]
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void malformedJsonFailsBeforeValidation()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{not-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void emptyRequiredBodyReturns400() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void extraTopLevelFieldIsRejectedByStrictMapper()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "address":{"city":"Hue"},
                         "isAdmin":true}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void extraNestedFieldIsAlsoRejected()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "address":{"city":"Hue","unknown":"x"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void lenientPreviewExplicitlyIgnoresExtraFields()
            throws Exception {
        mvc.perform(post("/api/orders/preview")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "extra":"ignored"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku")
                        .value("SKU-123"))
                .andExpect(jsonPath("$.quantity").value(2));

        verifyNoInteractions(service);
    }

    @Test
    void wrongContentTypeIs415NotValidation400()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("""
                        {"sku":"SKU-123","quantity":2}
                        """))
                .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(service);
    }
}
```

Đặc điểm của test:

- `@WebMvcTest` dùng Spring MVC argument resolution/message converters thật, chứ không gọi controller trực tiếp bằng `new`.
- `@ActiveProfiles("test")` kích hoạt strict Jackson property; test đầu tiên assert mapper thực sự nhận cờ này.
- Mỗi trường hợp invalid assert **HTTP 400 + mã lỗi thích hợp + service không có interactions**.
- `@MockitoBean` của Spring Framework 6.2 cho Boot 3.4+ thay thế `@MockBean` cũ; Spring test infrastructure reset mock theo lifecycle thông thường.
- Một lỗi ở một field có thể được assert bằng `$.errors[0]`; nếu nhiều fields fail cùng lúc, đừng giả định thứ tự trừ khi error contract chủ động sắp xếp.
- `@JsonIgnoreProperties(ignoreUnknown=true)` trong preview DTO chứng minh local lenient policy, trong khi strict endpoint vẫn từ chối unknown.
- `text/plain` đi vào media type handling và ra 415, không phải JSON parsing/validation 400.

## 10. Thử Jackson thuần: ObjectMapper không đồng nhất với Spring Boot

Thêm unit test để tránh hiểu lầm “đặt `new ObjectMapper()` là đã dùng đúng mapper của ứng dụng”.

Tệp `src/test/java/example/jsondemo/JacksonBasicsTest.java`:

```java
package example.jsondemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import org.junit.jupiter.api.Test;

class JacksonBasicsTest {

    record SimpleInput(String sku, Integer quantity) {
    }

    @Test
    void missingNullableRecordMemberDeserializesAsNull()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        SimpleInput input = mapper.readValue(
                "{\"sku\":\"SKU-123\"}", SimpleInput.class);

        assertEquals("SKU-123", input.sku());
        assertNull(input.quantity());
    }

    @Test
    void directJacksonMapperRejectsUnknownByDefault() {
        ObjectMapper mapper = new ObjectMapper();

        assertThrows(UnrecognizedPropertyException.class, () ->
                mapper.readValue(
                        "{\"sku\":\"SKU-123\",\"quantity\":2,"
                                + "\"extra\":true}",
                        SimpleInput.class));
    }

    @Test
    void explicitLenientJacksonMapperCanIgnoreUnknown()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper()
                .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        SimpleInput input = mapper.readValue(
                "{\"sku\":\"SKU-123\",\"quantity\":2,"
                        + "\"extra\":true}",
                SimpleInput.class);

        assertEquals("SKU-123", input.sku());
        assertEquals(2, input.quantity());
    }

    @Test
    void explicitNullIsAlsoNullWithoutBeanValidation()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        SimpleInput input = mapper.readValue(
                "{\"sku\":\"SKU-123\",\"quantity\":null}",
                SimpleInput.class);

        assertNull(input.quantity());
    }
}
```

**Đây là 4 pure Jackson tests** không tạo Spring context. Chúng kiểm tra trực tiếp cú pháp JSON, record deserialization và unknown-property handling theo config của chính mapper. Lưu ý rằng việc Jackson đọc một DTO với null không có nghĩa HTTP controller dùng `@Valid` cũng sẽ chấp nhận nó.

### Ba nơi cấu hình khác nhau

| Nơi | Cách có ObjectMapper | Policy unknown mặc định / mẫu |
| --- | --- | --- |
| Pure unit | `new ObjectMapper()` | Jackson 2.x mặc định `FAIL_ON_UNKNOWN_PROPERTIES=true` |
| Spring Boot 3.5 bình thường | Boot-configured `ObjectMapper` | Boot tắt `FAIL_ON_UNKNOWN_PROPERTIES` theo default |
| Spring Boot test profile của bài | Boot-configured `ObjectMapper` + property strict | `FAIL_ON_UNKNOWN_PROPERTIES=true` |
| Type lenient trong bài | `@JsonIgnoreProperties(ignoreUnknown=true)` trên DTO | Bỏ qua unknown fields của type đó ngay cả khi mapper strict |

Đừng khẳng định rằng **tất cả** `ObjectMapper` trong một ứng dụng đều dùng cờ giống nhau: project có thể tạo mapper riêng, dùng custom `HttpMessageConverter`, cấu hình JSON cho RestClient/WebClient khác hoặc tự instantiate object mapper ở một nơi khác. Để kiểm chứng endpoint thật, ưu tiên **MockMvc/HTTP integration test** hơn chỉ unit test Jackson.

## 11. Test HTTP thật: RANDOM_PORT và request JSON qua socket

`@WebMvcTest` xác nhận MVC deserialization và error mapping trong mock Servlet request. Nếu yêu cầu là “client gọi server thật với Content-Type/HTTP headers đúng”, thêm một nhóm nhỏ `@SpringBootTest(RANDOM_PORT)`.

Tệp `src/test/java/example/jsondemo/RealHttpJsonIntegrationTest.java`:

```java
package example.jsondemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class RealHttpJsonIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private HttpResponse<String> post(String body) throws Exception {
        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/orders");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void validPayloadReturns201OverRealHttp()
            throws Exception {
        assertTrue(port > 0);

        HttpResponse<String> response = post("""
            {"sku":"SKU-123","quantity":2,
             "address":{"city":"Hue"}}
            """);

        assertEquals(201, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertTrue(body.path("id").asLong() > 0);
    }

    @Test
    void strictUnknownPayloadReturns400OverRealHttp()
            throws Exception {
        HttpResponse<String> response = post("""
            {"sku":"SKU-123","quantity":2,
             "address":{"city":"Hue"},
             "isAdmin":true}
            """);

        assertEquals(400, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertEquals("INVALID_JSON",
                body.path("code").asText());
    }
}
```

JDK 17 `HttpClient` không cần thêm HTTP test client library. `@LocalServerPort` lấy cổng thực của embedded server; không hard-code `localhost:8080`. Test profile bật strict Jackson policy. Service thật dùng ID trong bộ nhớ, nên không cần database teardown ở demo. Với ứng dụng có persistence, HTTP client và server thường chạy transaction khác nhau; `@Transactional` trên client test **không tự rollback** thay đổi được server commit.

Hai phép thử trên xác nhận đầy đủ HTTP transport đến server vừa khởi động, nhưng chưa chứng minh HTTPS, gateway, schema migration hoặc DB production. Những tầng này cần integration test/hạ tầng riêng nếu thuộc contract.

## 12. Chạy mã và expected outcomes

Yêu cầu JDK 17+, Maven, kết nối tải Maven dependencies khi chạy lần đầu. Từ thư mục có `pom.xml`:

```bash
mvn test
```

Hoặc chạy từng nhóm:

```bash
mvn test -Dtest=OrderControllerTest
mvn test -Dtest=JacksonBasicsTest
mvn test -Dtest=RealHttpJsonIntegrationTest
```

**Kết quả kỳ vọng:**

| Nhóm | Method declarations | Test invocations | Bằng chứng |
| --- | ---: | ---: | --- |
| `OrderControllerTest` | 18 (gồm 2 parameterized) | 20 | MVC binding + validation + unknown policy + service interactions |
| `JacksonBasicsTest` | 4 | 4 | Jackson thuần missing/null/strict/lenient |
| `RealHttpJsonIntegrationTest` | 2 | 2 | Real server trả 201/400 cho JSON |
| **Tổng** | **24** | **26** | Không cần DB/Docker |

Các con số trên tính `@ParameterizedTest` cho min/max và out-of-range, mỗi method có hai inputs. Khi các dependency/version khớp, **dự kiến 26 test invocations PASS, 0 failures/errors/skips**. Đây là expected behavior từ mã ví dụ; để xác nhận thực tế cần chạy Maven, đọc `target/surefire-reports`. Không có `System.out.println` trong mã, nên không có stdout ứng dụng cố định ngoài log Maven/Spring.

Một số kịch bản tiêu biểu:

| Input | Expected HTTP | API code/response | Service có được gọi? |
| --- | --- | --- | --- |
| JSON hợp lệ | 201 | `{"id":101}` trong MVC mock, ID > 0 khi HTTP thật | Có |
| `quantity` thiếu | 400 | `VALIDATION_ERROR`, field `quantity` | Không |
| `quantity:null` | 400 | `VALIDATION_ERROR`, field `quantity` | Không |
| `quantity:0` / `11` | 400 | `VALIDATION_ERROR` | Không |
| `sku` thiếu/trắng | 400 | `VALIDATION_ERROR`, field `sku` | Không |
| `address` thiếu | 400 | `VALIDATION_ERROR`, field `address` | Không |
| `address.city` thiếu | 400 | `VALIDATION_ERROR`, field `address.city` | Không |
| `quantity:"many"` | 400 | `INVALID_JSON` | Không |
| JSON sai cú pháp | 400 | `INVALID_JSON` | Không |
| Root là JSON array | 400 | `INVALID_JSON` | Không |
| Body rỗng | 400 | `INVALID_JSON` | Không |
| Top-level unknown `isAdmin` | 400 | `INVALID_JSON` với strict test policy | Không |
| Nested unknown trong address | 400 | `INVALID_JSON` với strict policy | Không |
| Lenient preview với `extra` | 200 | Preview chỉ gồm known fields | Không |
| `Content-Type: text/plain` | 415 | Spring media type error | Không |

Khi policy strict bị xóa ở test profile, các case unknown property **phải fail** vì 400 không còn đúng. Khi `@Valid` bị xóa, các case missing/null/invalid constraints **phải fail** vì request có thể lọt vào controller; đó là những regression mà bộ test có khả năng phát hiện.

## 13. Phân tích sâu hơn: khi nào missing dẫn tới lỗi Jackson ngay?

Trong bài mẫu, missing `Integer quantity` sẽ cho `null` rồi `@NotNull` trả lỗi validation. Nhưng có những schema dùng Jackson creator properties bắt buộc:

- `@JsonCreator` chọn constructor/static factory được Jackson dùng.
- `@JsonProperty(value="id", required=true)` trên creator parameter yêu cầu property hiện diện theo semantics của Jackson creator.
- `FAIL_ON_MISSING_CREATOR_PROPERTIES` có thể buộc Jackson báo lỗi khi creator input không xuất hiện.
- `FAIL_ON_NULL_CREATOR_PROPERTIES` có thể buộc báo lỗi với creator properties null.
- `@JsonSetter(nulls=Nulls.FAIL)` có thể đặt null policy theo property/deserializer phù hợp.

Khi bật chúng, **cùng một JSON thiếu field** có thể chuyển từ `MethodArgumentNotValidException` sang `HttpMessageNotReadableException`. Đó không nhất thiết là bug; là khác biệt ở lớp cấu hình. API contract nên giữ HTTP 400 ổn định và test nguyên nhân/response code phù hợp.

Không áp dụng các flag creator này cho toàn hệ thống mà không xem tác động lên backward compatibility của DTOs và các legacy clients. Một DTO có default property trong business logic không hẳn cần fail khi JSON bỏ trống field.

### Missing optional fields

Đối với field optional thực sự, có thể dùng:

```java
public record SearchFilter(
        String keyword,
        Integer pageSize,
        Boolean includeInactive) {
}
```

Nếu property không có, Java wrapper có thể nhận null; service/controller **phải** đặt default/normalize có chủ đích trước khi dùng. Tránh `Boolean includeInactive` bị unbox khi null, và tránh “default 0” âm thầm khi request hợp đồng đòi ≥1. Mọi default có giá trị nghiệp vụ cần được document và test riêng cho missing, null và explicit value.

## 14. Field không biết nhưng hợp lệ về mặt JSON: strict ở đâu?

Ba tầng policy thường gặp:

1. **Global ObjectMapper strict**: config `spring.jackson.deserialization.fail-on-unknown-properties=true`. Tất cả DTOs dùng mapper tương ứng có thể bị ảnh hưởng.
2. **Per-type lenient**: `@JsonIgnoreProperties(ignoreUnknown=true)` cho type contract mở rộng. Chỉ DTO được annotate mới có ngoại lệ.
3. **Endpoint-specific mapper/deserializer**: custom `HttpMessageConverter`, `ObjectReader` hoặc custom deserializer khi cần format đặc biệt — phức tạp hơn, nên chỉ dùng khi có yêu cầu rõ.

Một hạn chế quan trọng: đặt `@JsonIgnoreProperties(ignoreUnknown = false)` trên type **không tự đảm bảo** strict nếu ObjectMapper global đang cho phép unknown, vì `false` chỉ thể hiện “annotation này không yêu cầu ignore unknown”; deserializer còn theo global feature flag và các handler khác. Muốn enforced strict, cấu hình mapper dùng thực tế hoặc thêm cơ chế kiểm tra known keys có chủ đích.

Nếu cần chấp nhận JSON extensibility nhưng **không được mất dữ liệu**, hãy dùng `@JsonAnySetter` để thu unknown keys vào một map được kiểm soát, rồi quyết định lưu hay từ chối. Chỉ bỏ qua unknown fields phù hợp khi việc bỏ qua đó nằm trong API contract.

### Tên property, naming strategy và alias

`@JsonProperty("order_id")` có thể ánh xạ JSON `order_id` vào Java `orderId`. `spring.jackson.property-naming-strategy=SNAKE_CASE` thay đổi naming strategy theo mapper. `@JsonAlias("oldName")` cho phép tên cũ ở đường **deserialization**, không có nghĩa response sẽ luôn serialize cả alias.

Nếu API đang bật strict unknown property mà client gửi `orderID` thay vì `orderId`, key sai tên có thể tạo đồng thời lỗi unknown **và** field đích thiếu. Cần test exact JSON property names và migration aliases khi đổi contract.

## 15. Những ngoại lệ, lỗ hổng thường gặp khi deserialize JSON

### Primitive mặc định và business rule

Nếu dùng:

```java
public record UnsafeInput(int quantity) {}
```

trong môi trường Jackson 2 mặc định `FAIL_ON_NULL_FOR_PRIMITIVES=false`, missing hoặc null có thể được hiểu thành 0. Nếu `quantity` là một trường bắt buộc, dùng wrapper và `@NotNull` hoặc bật strict null handling phù hợp. **Không** để 0 bị hiểu như người dùng tự chọn 0 khi request thực tế không có property.

### Chuyển đổi string thành số

`"quantity":"2"` có thể đi qua implicit coercion. Nếu API đòi số JSON **đúng native numeric type**, cần cấu hình Jackson coercion cho target type và test trực tiếp; `@Min` chỉ kiểm tra giá trị Java sau chuyển đổi, không kiểm tra JSON ban đầu là token String hay Number.

### Duplicate keys

JSON như:

```json
{"quantity":1,"quantity":100}
```

không phải input đáng tin cho nghiệp vụ; nhiều parser/mapper có thể chấp nhận và chọn giá trị cuối hoặc có behavior khác theo cấu hình. Nếu contract yêu cầu từ chối duplicate keys, bật kiểm tra duplicate ở parser tương ứng, ví dụ `JsonParser.Feature.STRICT_DUPLICATE_DETECTION` trên Jackson 2.x, và test với converter thật. `FAIL_ON_READING_DUP_TREE_KEY` chỉ dành cho đường đọc tree ở những trường hợp nhất định, **không** thay thế kiểm tra duplicate chung khi bind trực tiếp POJO.

### Trailing tokens

Một JSON object hợp lệ theo sau bởi dữ liệu thừa:

```text
{"sku":"SKU-123"} {"other":"payload"}
```

cần chính sách “một document duy nhất”. `FAIL_ON_TRAILING_TOKENS` của Jackson có thể giúp từ chối token ngoài root JSON; mặc định behavior có thể khác tùy cách reader/converter được gọi. Nếu API coi đây là threat model, test bằng HTTP request thật chứ không chỉ `ObjectMapper.readTree` một object.

### Polymorphic typing và unsafe deserialization

Không bật Jackson **default typing** cho dữ liệu không đáng tin nếu không hiểu rõ type validation/allowlist. Với JSON bên ngoài, tránh cho phép client tự chọn arbitrary Java class name trong type metadata. Chỉ dùng polymorphic JSON nếu thiết kế schema rõ, subtype allowlist và versioning; không deserialize untrusted input thành arbitrary internal object graph.

### Khả năng bị over-posting

Trong các API ghi dữ liệu, không deserialize trực tiếp JPA entity có role/admin fields hoặc lưu mọi unknown property không kiểm tra. Một DTO allowlist với các trường public được phép sửa, domain authorization và service-level invariant vẫn bắt buộc, kể cả khi Jackson strict.

### Giới hạn kích thước và độ sâu

Bean Validation không ngăn một JSON rất lớn/nghìn object lồng nhau tiêu tốn memory trước khi validation chạy. Thiết lập request body size limits ở server/gateway, Jackson stream read constraints phù hợp phiên bản, số item tối đa và schema constraints như `@Size(max=...)`. Tách test input validation khỏi load/security tests ở tầng body size/depth.

## 16. So sánh MockMvc, ObjectMapper unit test và HTTP integration

| Tiêu chí | Pure ObjectMapper | `@WebMvcTest` + MockMvc | `@SpringBootTest(RANDOM_PORT)` |
| --- | --- | --- | --- |
| Có Spring context? | Không | MVC slice | Full Boot context |
| Test Jackson configuration của Boot? | Không nếu tự `new ObjectMapper()` | Có, theo test slice context | Có, theo full app context |
| Đọc `@RequestBody` qua MVC converter? | Không | Có | Có |
| Chạy `@Valid` và exception advice? | Không, trừ khi tự setup validation | Có | Có |
| Có HTTP socket thật? | Không | Không | Có |
| Test cần port? | Không | Không | `@LocalServerPort` |
| Tốc độ | Nhanh nhất | Thường nhanh | Chậm hơn do full startup/server |
| Dùng khi | Cần kiểm chứng behavior mapper riêng | API input mapping + status/error contract | Smoke HTTP end-to-end cùng wiring thật |

Không gắn `@SpringBootTest` và `@WebMvcTest` trên cùng class vì chúng chọn bootstrap khác nhau. Nếu muốn full-context + mock HTTP requests, dùng `@SpringBootTest` + `@AutoConfigureMockMvc`. Chọn lớp nhỏ nhất vẫn chứng minh mục tiêu.

## 17. Chẩn đoán khi test deserialize thất bại

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| JSON sai kiểu nhưng server trả 500 | Advice không xử lý `HttpMessageNotReadableException` hoặc exception bị nuốt/đổi status | Kiểm tra resolved exception, để parse errors thành 400 |
| JSON thiếu quantity nhưng được 201 | Quên `@Valid` hoặc `@NotNull`, dùng primitive default | Kiểm tra controller annotation và DTO constraints |
| `@NotNull` không chạy | Thiếu validation provider hoặc test gọi trực tiếp controller | Thêm starter validation; dùng MockMvc |
| Unexpected field vẫn 201 | Boot-configured mapper đang ignore unknown | Bật strict property nếu API contract yêu cầu |
| Unexpected field fail trong unit nhưng HTTP chấp nhận | `new ObjectMapper()` và Boot mapper khác defaults | Test trực tiếp mapper inject trong Spring |
| Type `"2"` được chấp nhận dù muốn numeric token | Jackson coercion đang bật | Strict coercion config, test policy |
| DTO record không deserialize được | Jackson version/constructor annotations/creator config/naming mismatch | Đồng bộ Boot BOM, kiểm tra record mapping |
| Field JSON bị thiếu sau đổi tên | `@JsonProperty`/naming strategy/`@JsonAlias` không tương thích | Test tên key thực trên wire |
| Nested city không được validate | Quên `@Valid` trên nested field | Thêm `@Valid` + `@NotNull` nếu field mandatory |
| Client gửi null nhưng test chỉ cover missing | Hai case có thể khác khi creator/null policy strict | Tách assertions cho missing và null |
| `@WebMvcTest` báo thiếu OrderService | Slice cố ý không load service thường | `@MockitoBean` hoặc import bean test phù hợp |
| Request body JSON nhưng test bị 415 | Content-Type không phù hợp `consumes` | Gửi `application/json`, phân biệt với 400 |
| Multiple violations đổi thứ tự | Validator không hứa thứ tự tự nhiên | Assert field set hoặc sort trong API contract |
| Unknown nested fields không bị reject | Field type có `@JsonIgnoreProperties` hoặc custom deserializer | Kiểm tra DTO tree và mapper policy |
| Test chạy riêng PASS, cả suite FAIL | Context/profile khác nhau, shared mutable config/mock | Dùng test profile rõ và tránh global mapper mutation |
| API leak dữ liệu payload khi error | Trả raw exception, rejected value | Generic safe response; chi tiết ở server log đã redacted |
| Boot 4 fail với Jackson imports cũ | Jackson 3/test modules khác Boot 3 | Xem BOM và API docs đúng phiên bản |

### Debug theo trình tự

1. Xác nhận request có `Content-Type: application/json`, đúng method/path và body thật.
2. Kiểm tra exception root cause nếu MVC trả 400: parse/token mismatch hay validation?
3. Kiểm tra DTO type và naming; có `@JsonProperty`/alias/global naming strategy không?
4. Xác nhận mapper **thực tế** bằng `@Autowired ObjectMapper` và feature flags trong test.
5. Kiểm tra `@Valid`, starter validation, constraints và nested cascade.
6. Kiểm tra `@RestControllerAdvice` có được component scan/test slice phát hiện không.
7. Assert status + code + field + verifyNoInteractions để chắc input sai bị chặn.
8. Khi có sự khác biệt chỉ xảy ra qua HTTP thật, thêm một RANDOM_PORT test với body/headers giống client.
9. Không sửa lỗi bằng cách tắt validation hoặc broad `catch(Exception)` trả 200/default object.
10. Chạy cả suite và xem `target/surefire-reports` để phát hiện test bị lọc hoặc chưa thực chạy.

## 18. Kiến trúc và version: Spring Boot 3.5 sang 4

**Bộ mã hoàn chỉnh nhắm Spring Boot 3.5.0, Spring Framework 6.2 và Jackson 2.x.** Khi nâng lên Spring Boot 4:

- Spring Boot 4 sử dụng Spring Framework 7 và định hướng Jackson 3; package Jackson API, cấu hình mặc định và converter configuration cần đối chiếu theo tài liệu chính thức.
- Test infrastructure của Boot 4 được chia theo công nghệ; có focused test starters như `spring-boot-starter-webmvc-test` và annotation `@WebMvcTest` được chuyển package.
- `@MockitoBean` của Spring Framework tiếp tục là hướng dùng thay `@MockBean` cũ.
- Không copy nguyên `com.fasterxml.jackson.databind.ObjectMapper` của Jackson 2 sang Jackson 3 mà không kiểm tra migration.
- Các quy tắc **missing ≠ null ≠ invalid shape**, strict unknown policy và Bean Validation vẫn là các vấn đề hợp đồng API; hãy xác nhận behavior qua HTTP tests trên stack đích.

Nếu không bắt buộc nâng major trong bài thực hành, dùng đúng các dependencies/imports của mục 8–11. Đồng bộ phiên bản qua Spring Boot BOM/parent thay vì ghép bất kỳ Jackson, Hibernate Validator và JUnit versions nào.

## 19. Checklist nghiệm thu

- [ ] Đã phân biệt Jackson deserialization với Jakarta Bean Validation?
- [ ] DTO request chỉ chứa fields API cho phép, không bind trực tiếp entity nhạy cảm?
- [ ] `@RequestBody` và `@Valid` nằm ở controller argument phù hợp?
- [ ] Có `spring-boot-starter-validation` hoặc provider tương thích?
- [ ] Test hợp lệ xác nhận HTTP 201, đúng JSON response và service được gọi đúng đối số?
- [ ] Test missing property và explicit null là hai case độc lập?
- [ ] Required numeric field dùng wrapper `Integer`/`Long` + `@NotNull` khi cần?
- [ ] Test số ở cận dưới/trên và ngay ngoài biên?
- [ ] Test input không convert được như `"quantity":"many"`?
- [ ] Test JSON sai cú pháp, root shape sai, body trống?
- [ ] Hiểu coercion `"2"`/`2.5` có thể phụ thuộc config, không suy luận sai?
- [ ] Đã chọn strict/lenient unknown property policy công khai?
- [ ] Nếu strict, config ObjectMapper được xác minh trong Spring test context?
- [ ] Nếu lenient, chỉ annotate những DTO thực sự cho phép unknown?
- [ ] Test unknown top-level và nested properties?
- [ ] Error response có status/code/field ổn định, không chứa raw payload hoặc stack trace?
- [ ] Test `text/plain` nhận 415, không nhầm với validation 400?
- [ ] MockMvc invalid cases xác nhận service không được gọi?
- [ ] Không phụ thuộc thứ tự của nhiều FieldErrors khi contract không cam kết?
- [ ] Có ít nhất một real HTTP test nếu contract cần kiểm tra socket/server thật?
- [ ] Test không nhầm direct `new ObjectMapper()` với mapper Spring Boot cấu hình?
- [ ] CI báo số tests executed/failed/skipped thực tế, không chỉ build status?
- [ ] Khi nâng Boot/Jackson major, đã kiểm tra test starters, imports, defaults và contracts?

## 20. Tài liệu chính thức và nguồn tra cứu

1. [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): `HttpMessageConverter`, `@Valid`, `MethodArgumentNotValidException` và `BindingResult`.
2. [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): validation ở argument resolver và method-level.
3. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jackson.deserialization.*` và các Jackson settings.
4. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@MockitoBean`, `@SpringBootTest`.
5. [Jackson 2.19 DeserializationFeature API](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-databind/2.19.0/com/fasterxml/jackson/databind/DeserializationFeature.html): default flags, coercion và failure handling.
6. [Jackson — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features): `FAIL_ON_UNKNOWN_PROPERTIES`, null primitives, creator features.
7. [Jackson — @JsonIgnoreProperties](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations): ignored/unknown JSON fields.
8. [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/): `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Valid`.
9. [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html): DTO allowlist, tránh bind internal/security fields.
10. [Spring Boot Reference — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): đối chiếu ObjectMapper/Jackson integration theo phiên bản Boot.

**Kết luận:** deserialize thành công **không chứng minh request hợp lệ**. Thiếu trường có thể thành `null`; sai kiểu có thể thất bại ở Jackson hoặc được coercion; dư trường bị chấp nhận hay từ chối tùy ObjectMapper/DTO policy. Một API đáng tin phải định nghĩa rõ bốn tình huống này, kiểm thử response và bảo đảm input sai **không đi tới service nghiệp vụ**.
