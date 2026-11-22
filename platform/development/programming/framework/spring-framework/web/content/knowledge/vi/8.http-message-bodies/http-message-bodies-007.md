# Phân biệt lỗi JSON sai cú pháp, JSON sai kiểu và dữ liệu không hợp lệ trong Spring MVC

## 1. Mục tiêu

Ba HTTP request sau đều có thể nhận phản hồi **400 Bad Request**, nhưng **nguyên nhân, thời điểm lỗi và cách sửa hoàn toàn khác nhau**:

```json
{"sku":"A-100", "quantity": 2,
```

```json
{"sku":"A-100", "quantity": "nhiều", "shipping":{"city":"Hà Nội"}}
```

```json
{"sku":"", "quantity": 0, "shipping":{"city":""}}
```

- **JSON sai cú pháp:** văn bản không tuân theo ngữ pháp JSON. Ví dụ đầu tiên thiếu dấu `}` kết thúc object. JSON parser không tạo được cấu trúc dữ liệu hoàn chỉnh.
- **JSON sai kiểu hoặc không thể giải mã sang kiểu Java:** văn bản là JSON hợp lệ, nhưng mapper không tạo được kiểu Java đích. Ví dụ `"quantity": "nhiều"` không chuyển được thành `Integer` với cấu hình Jackson thông thường.
- **Dữ liệu không hợp lệ:** JSON đúng cú pháp và chuyển thành object Java được, nhưng **vi phạm quy tắc của API**, ví dụ số lượng phải ≥ 1, SKU không rỗng, thành phố giao hàng bắt buộc.

Sau bài này bạn sẽ phân biệt chính xác ba lớp lỗi, hiểu luồng `@RequestBody` của Spring MVC, biết khi nào gặp `HttpMessageNotReadableException` hoặc `MethodArgumentNotValidException`, xử lý lỗi có cấu trúc, không tiết lộ thông tin nội bộ và viết kiểm thử tái hiện từng trường hợp.

**Phạm vi:** Spring MVC (Servlet stack), Spring Framework 6.x, Spring Boot 3.x, Jackson làm JSON mapper, Java 17+. Với WebFlux, Moshi/Gson hoặc cấu hình Jackson thay đổi, tên exception và hành vi chuyển kiểu có thể khác.

## 2. Ba tầng kiểm tra trong đường đi của request

Một request đến controller dạng:

```java
@PostMapping("/api/orders")
OrderCreated create(@Valid @RequestBody CreateOrderRequest request) {
    // Được gọi khi body đọc được, object tạo được và validation qua.
}
```

*Đoạn này chỉ minh họa chữ ký; ứng dụng Java đầy đủ ở mục 8.*

Luồng xử lý cơ bản:

```text
Client
   │
   │ POST /api/orders
   │ Content-Type: application/json
   ▼
DispatcherServlet / RequestMappingHandlerAdapter
   │
   ├─ (A) Chọn HTTP message converter phù hợp với media type
   │      Content-Type sai → có thể 415 Unsupported Media Type
   │
   ├─ (B) JSON parser (Jackson)
   │      Văn bản không đúng ngữ pháp JSON → JsonParseException
   │      Spring bọc thành HttpMessageNotReadableException → 400
   │
   ├─ (C) JSON deserialization / mapping
   │      JSON hợp lệ, nhưng không tạo được CreateOrderRequest:
   │      ví dụ String "nhiều" → Integer quantity
   │      → MismatchedInputException / InvalidFormatException
   │      Spring bọc thành HttpMessageNotReadableException → 400
   │
   ├─ (D) Validation trên object Java đã tạo (`@Valid`)
   │      @NotBlank, @Min, @NotNull, nested @Valid, ...
   │      → MethodArgumentNotValidException → thường 400
   │
   └─ (E) Controller method
          → xử lý nghiệp vụ nếu input hợp lệ
          → có thể tự trả lỗi nghiệp vụ như 409/422/400 tùy hợp đồng
```

**Điểm phân biệt lớn nhất:** một JSON có thể **đúng cú pháp** nhưng **sai kiểu Java**; một Java object có thể **tạo thành công** nhưng **vi phạm validation**. Không gom cả ba thành câu “JSON invalid” trong tài liệu API hoặc metric vận hành.

**Lưu ý về thứ tự:** các bước trên là mô hình dễ hiểu, không hứa hẹn rằng mọi request đều đi qua tất cả bước. Ví dụ `Content-Type: text/plain` có thể bị từ chối ở bước chọn converter, trước khi parser JSON chạy. Một converter tùy biến có thể gộp hai bước parse và mapping trong cùng lời gọi. Phần routing, filter bảo mật, giới hạn body hoặc đọc network cũng có thể dừng request sớm hơn.

## 3. Lỗi JSON sai cú pháp (syntax error)

JSON phải tuân theo cú pháp riêng: object đặt trong `{}`, key là chuỗi trong dấu nháy kép, mỗi cặp phân tách bằng dấu phẩy, string phải có escape hợp lệ, số không được viết theo mọi kiểu JavaScript.

### 3.1. Các ví dụ sai

| Request body | Lỗi cú pháp | Dạng đúng |
| --- | --- | --- |
| `{"id": 1,` | Thiếu trường hoặc phần kết thúc sau dấu phẩy | `{"id": 1}` |
| `{'id': 1}` | JSON chuẩn yêu cầu dấu nháy kép cho key | `{"id": 1}` |
| `{id: 1}` | Tên thuộc tính không được bỏ nháy trong JSON chuẩn | `{"id": 1}` |
| `{"id": 1,}` | Trailing comma không hợp lệ theo JSON chuẩn | `{"id": 1}` |
| `{"active": True}` | Boolean JSON là `true` hoặc `false`, chữ thường | `{"active": true}` |
| `{"name": "A" "age": 3}` | Thiếu dấu phẩy giữa hai cặp | `{"name":"A","age":3}` |
| `{"x":"dòng xuống↵trực tiếp"}` | Ký tự newline thô bên trong JSON string | `{"x":"dòng xuống\nhợp lệ"}` |

Các trường hợp trên có thể bị Jackson báo `com.fasterxml.jackson.core.JsonParseException` hoặc subtype (ví dụ EOF bất ngờ). Khi đọc `@RequestBody`, Spring MVC thường bọc lỗi thành `org.springframework.http.converter.HttpMessageNotReadableException`. Controller method **thường chưa được gọi**, vì không có object đích để xử lý.

Nếu ứng dụng bật một số tính năng parser mở rộng (ví dụ cho phép single quotes hoặc trailing comma), dữ liệu sai theo JSON chuẩn có thể được chấp nhận. Các ví dụ trong bài giả định cấu hình JSON mặc định của Spring Boot 3. Đừng nhầm “parser có chế độ dễ dãi” với “JSON chuẩn cho phép cú pháp đó”.

### 3.2. Cách đọc lỗi parser

Thông tin root cause trong server log có thể chứa vị trí line/column, token không hợp lệ và lời giải thích từ Jackson. Điều này hữu ích khi debug; khi trả API public, tránh sao chép toàn bộ exception message hoặc nội dung body vào phản hồi vì có thể rò rỉ dữ liệu, phụ thuộc version và cấu trúc nội bộ.

Khuyến nghị response ổn định:

```json
{
  "code": "JSON_SYNTAX",
  "fields": []
}
```

Đây là **hợp đồng lỗi do ví dụ bài học chủ động xây dựng**, không phải định dạng lỗi mặc định của Spring Boot. Nếu API cần chỉ rõ line/column, hãy quyết định trong hợp đồng riêng và kiểm tra tác động bảo mật. Không cần trả “field” khi parser chưa phân tích được một JSON document hợp lệ.

### 3.3. JSON thiếu body khác gì JSON sai cú pháp?

Request `POST` không gửi body dù `@RequestBody(required = true)` (mặc định) có thể tạo `HttpMessageNotReadableException` kiểu “Required request body is missing”. Đây **không hẳn là lỗi cú pháp của một tài liệu JSON**, vì không có JSON document để parse. Nên dùng mã tổng quát `BODY_NOT_READABLE` hoặc `BODY_REQUIRED` nếu phân loại riêng.

Một body chứa chữ `null` là **JSON hợp lệ** (literal null); tác động tiếp theo phụ thuộc kiểu đích và việc `@RequestBody` có yêu cầu object khác null hay không. Đừng gọi nó là JSON sai cú pháp.

## 4. JSON đúng cú pháp nhưng sai kiểu/không deserialization được

JSON chỉ có các loại giá trị cơ bản: object, array, string, number, boolean và null. Java có kiểu phong phú hơn (`Integer`, `LocalDate`, `UUID`, enum, record, collections, các lớp do ứng dụng định nghĩa). Jackson phải áp dụng quy tắc ánh xạ giữa hai phía.

### 4.1. Ví dụ dữ liệu JSON hợp lệ nhưng không khớp Java

Giả sử DTO có `Integer quantity`, `LocalDate deliveryDate` và `List<String> labels`.

| JSON đầu vào | Kiểu Java đích | Nguyên nhân có thể thất bại |
| --- | --- | --- |
| `{"quantity":"nhiều"}` | `Integer` | Không parse được chuỗi thành số |
| `{"quantity":999999999999}` | `Integer` | Số vượt phạm vi integer |
| `{"deliveryDate":"ngày mai"}` | `LocalDate` | Không đúng định dạng được parser ngày chấp nhận |
| `{"labels":{"key":"x"}}` | `List<String>` | Object thay vì array, khi không có cấu hình coercion riêng |
| `{"shipping":[] }` | Object `ShippingAddress` | Array không phải dạng object dự kiến |
| `{"status":"UNKNOWN"}` | Enum `OrderStatus` | Không có constant tương ứng với chuỗi |
| `{"id":"không-phải-uuid"}` | `UUID` | Chuỗi không tạo được UUID theo quy tắc mapper |

Jackson thường ném `com.fasterxml.jackson.databind.exc.MismatchedInputException` hoặc subtype `InvalidFormatException`. Các exception này là lỗi **đọc/ánh xạ request**, và Spring MVC thường chuyển thành `HttpMessageNotReadableException`, nên HTTP status mặc định hay là **400**.

**Lưu ý quan trọng về coercion:** không phải cứ JSON string gặp trường Java kiểu số là lỗi. Tùy Jackson và cấu hình, `"quantity":"2"` **có thể** được chấp nhận và đổi thành `Integer(2)`. `2.0`, chuỗi trống, boolean hoặc singleton thay cho array cũng có hành vi phụ thuộc các tùy chọn coercion. Vì thế dùng `"quantity":"nhiều"` trong test để có case sai kiểu chắc chắn hơn trong cấu hình demo. Nếu hợp đồng API yêu cầu **bắt buộc JSON number**, hãy cấu hình deserialization/coercion nghiêm ngặt và thêm test; chỉ annotation `Integer` chưa bảo đảm cấm tất cả string chứa số.

### 4.2. Sai hình dạng và lỗi không đọc được

Các trường hợp khác:

- Object chứa cấu trúc lồng nhau không phù hợp với record/class constructor.
- JSON hợp lệ nhưng Jackson không có cách tạo object (không có creator thích hợp, constructor không thể dùng hoặc cấu hình polymorphic type không phù hợp).
- Một constructor/creator của DTO tự ném lỗi; đây cũng có thể trở thành lỗi ánh xạ.
- Với cấu hình chặt chẽ, thuộc tính JSON **không khai báo** có thể gây `UnrecognizedPropertyException`. Nhưng Spring Boot thường cấu hình Jackson bỏ qua unknown properties; không mặc nhiên khẳng định mọi thuộc tính lạ đều bị từ chối.
- JSON có duplicate keys đôi khi được parser/mapper chấp nhận; muốn từ chối bắt buộc cần bật kiểm tra duplicate tương ứng, không suy ra đó luôn là syntax error.

**Nguyên tắc:** nếu parser hiểu được tài liệu JSON nhưng mapper không thể tạo ra object Java mong đợi, đây là lỗi **deserialization/mapping**, không phải lỗi Bean Validation. `@NotNull`, `@Min` không chạy có ý nghĩa trên một DTO **chưa thể được tạo hoàn chỉnh**.

Một mã API phù hợp:

```json
{
  "code": "JSON_TYPE",
  "fields": []
}
```

Trong hệ thống thực, có thể phân loại chi tiết `JSON_SHAPE`/`JSON_VALUE_FORMAT`/`JSON_TYPE`. Đừng phụ thuộc vào việc mọi `JsonMappingException` đều là “sai kiểu do client”: custom deserializer, bug trong setter hoặc cấu hình server cũng có thể gây exception. Ví dụ ở mục 8 chỉ xếp `MismatchedInputException` vào `JSON_TYPE`; các lỗi khác dùng mã fallback.

### 4.3. Các giá trị null và thiếu trường

`null` là một JSON value hợp lệ và thiếu field cũng không phải syntax error. Ví dụ:

```json
{"sku":"A-100","quantity":null,"shipping":{"city":"Hà Nội"}}
```

Khi `quantity` dùng **`Integer`** (wrapper), Jackson có thể tạo object với `quantity == null`. `@NotNull` trên quantity sau đó báo **validation error**. Ngược lại, primitive `int` không lưu được null, nên mapper có thể tạo giá trị mặc định `0` hoặc báo lỗi tùy cấu hình `FAIL_ON_NULL_FOR_PRIMITIVES`; đây là lý do DTO request thường nên dùng wrapper + constraint rõ ràng cho field bắt buộc.

`null` cho một nested object cũng có thể được deserialize thành null; chỉ `@Valid` trên field đó **không buộc field phải tồn tại**. Thêm `@NotNull` nếu shipping bắt buộc, và `@Valid` để kiểm tra các constraint bên trong khi shipping khác null.

## 5. JSON hợp lệ về cấu trúc và kiểu nhưng vi phạm quy tắc dữ liệu

Sau khi parser và mapper thành công, Java object có thể vẫn sai với hợp đồng của API:

```java
public record CreateOrderRequest(
    @NotBlank String sku,
    @NotNull @Min(1) Integer quantity,
    @NotNull @Valid ShippingAddress shipping
) {}

public record ShippingAddress(@NotBlank String city) {}
```

*Đây là định nghĩa minh họa; cần import Jakarta Validation và đặt vào project phù hợp. Phiên bản đầy đủ ở mục 8.*

Body:

```json
{"sku":"","quantity":0,"shipping":{"city":""}}
```

JSON hoàn toàn đúng cú pháp, các kiểu Java đều tạo được (`String`, `Integer`, record lồng nhau), nhưng:

- `sku=""` vi phạm `@NotBlank`.
- `quantity=0` vi phạm `@Min(1)`; không phải lỗi parse số.
- `shipping.city=""` vi phạm `@NotBlank` ở object lồng nhau; `@Valid` trên `shipping` cho phép đi sâu.
- `@NotNull` làm rõ việc thiếu trường hoặc truyền null là không hợp lệ.

Nếu controller khai báo `@Valid @RequestBody CreateOrderRequest request` và **không** có `Errors`/`BindingResult` liền sau, Spring MVC thường ném `org.springframework.web.bind.MethodArgumentNotValidException`. Exception chứa `BindingResult`, trong đó có `FieldError` cho các trường như `sku`, `quantity` và `shipping.city`. HTTP status mặc định là **400 Bad Request** trong Spring MVC.

Phản hồi do ví dụ xây dựng:

```json
{
  "code": "VALIDATION_FAILED",
  "fields": ["quantity", "shipping.city", "sku"]
}
```

Lỗi có thể thuộc toàn object (cross-field constraint), không chỉ field. Nếu cần, ghi `ObjectError`/`global` riêng. Khi thiết kế JSON API, dùng mã lỗi ổn định và bản địa hóa thông điệp; không trả nguyên `getRejectedValue()` khi dữ liệu có thể chứa bí mật.

### 5.1. @Valid và @Validated có gì khác trong phạm vi này?

- `@Valid` là cách thông dụng để yêu cầu Jakarta Bean Validation chạy trên object đã được tạo. Thêm `@Valid` tại property lồng nhau để cascade validation.
- `@Validated` hỗ trợ validation groups và các cơ chế tích hợp của Spring khi cần.
- Muốn các constraint `@NotBlank`, `@Min` hoạt động, dự án phải có Jakarta Validation implementation, ví dụ `spring-boot-starter-validation`.
- Chỉ thêm annotation mà không có provider validation hoặc không kích hoạt validation đúng vị trí có thể khiến request vi phạm constraint vẫn tới service.
- **Semantic validation không đồng nghĩa kiểm tra nghiệp vụ trong database:** ví dụ trùng SKU, hết hàng, trạng thái đơn đã khóa hay không có quyền sửa đơn. Các lỗi đó có thể phát sinh **sau** Bean Validation khi controller gọi service; chọn HTTP 400/409/422 theo hợp đồng và ngữ nghĩa, không ép tất cả thành `MethodArgumentNotValidException`.

### 5.2. Khi nào không còn là MethodArgumentNotValidException?

Từ Spring MVC 6.1, method validation có thể được áp dụng khi constraint đặt trực tiếp trên parameter/return value của handler, ví dụ `@Min(1) @RequestParam int page`. Trong trường hợp này, `HandlerMethodValidationException` có thể xuất hiện thay vì `MethodArgumentNotValidException`. Điều đó không thay đổi bản chất rằng lỗi xuất hiện ở giai đoạn validation, nhưng bạn cần xử lý đúng exception theo chữ ký method.

Nếu controller khai báo `@Valid @RequestBody Dto dto, Errors errors` **liền nhau**, các lỗi Bean Validation của object đã deserialize có thể được trao cho controller thay vì ném `MethodArgumentNotValidException`. Vẫn không thể dùng `Errors` đó bắt lỗi syntax hoặc deserialize thất bại, vì method chưa nhận được DTO hợp lệ.

## 6. Bảng đối chiếu nhanh: nguyên nhân, exception, HTTP

| Tình huống | Giai đoạn | Exception thường thấy | HTTP mặc định/phổ biến |
| --- | --- | --- | --- |
| `{"quantity":1,}` | JSON syntax | `JsonParseException` bên trong `HttpMessageNotReadableException` | 400 |
| `{"quantity":"nhiều"}` khi cần `Integer` | Deserialization | `InvalidFormatException`/`MismatchedInputException` bên trong `HttpMessageNotReadableException` | 400 |
| `{"quantity":0}` với `@Min(1)` | Bean Validation sau khi deserialize | `MethodArgumentNotValidException` | 400 |
| `{"quantity":null}` với `@NotNull` và `Integer` | Bean Validation | `MethodArgumentNotValidException` | 400 |
| Không gửi body nhưng `@RequestBody` yêu cầu body | HTTP body missing | `HttpMessageNotReadableException` | 400 |
| `Content-Type: text/plain` gửi tới endpoint chỉ nhận JSON | Chọn converter/media type | `HttpMediaTypeNotSupportedException` | 415 |
| `Accept: text/plain` khi endpoint chỉ tạo `application/json` | Content negotiation | `HttpMediaTypeNotAcceptableException` | 406 |
| `@RequestParam int page` nhận `page=abc` | Chuyển kiểu request parameter ngoài JSON body | `MethodArgumentTypeMismatchException` | 400 |
| Constraint trực tiếp trên handler parameter | Method validation | `HandlerMethodValidationException` (MVC 6.1+) | 400 cho input vi phạm |
| Object hợp lệ nhưng vi phạm business rule | Service/domain | Exception/response do ứng dụng định nghĩa | 400, 409 hoặc 422 tùy hợp đồng |

**Không suy đoán nguyên nhân từ mỗi HTTP 400.** Trên wire, ba lỗi chính đều có thể cùng status 400; để phân biệt cần mã lỗi response, log/metric server hoặc exception chain.

**Đừng phụ thuộc 100% vào một tên exception:** behavior thay đổi theo Spring Framework/Jackson, converter, cấu hình exception handlers và kiểu controller. Khi ghi log phục vụ debugging, dùng `exception.getCause()`, phân loại có kiểm soát; không đưa raw exception class của bên thứ ba thành hợp đồng public API dài hạn.

## 7. Thiết kế hợp đồng lỗi JSON có ích cho client

Các client frontend/mobile cần biết có nên **sửa cấu trúc request** hay **hiển thị lỗi form**. Một API minh bạch có thể chuẩn hóa:

| `code` | Ý nghĩa cho client | Gợi ý phản ứng |
| --- | --- | --- |
| `JSON_SYNTAX` | Body không phải JSON đúng cú pháp | Sửa cách serialize, báo lỗi phía client/integration |
| `JSON_TYPE` | JSON có cấu trúc/giá trị không ánh xạ được sang DTO | Sửa kiểu dữ liệu hoặc shape theo API contract |
| `BODY_NOT_READABLE` | Body bị thiếu hoặc không đọc được vì nguyên nhân khác | Kiểm tra request body và content negotiation |
| `VALIDATION_FAILED` | DTO đã parse/deserialize được nhưng vi phạm constraint | Hiển thị field errors để người dùng sửa |
| `BUSINESS_RULE_VIOLATION` | Đầu vào qua validation kỹ thuật nhưng vi phạm nghiệp vụ | Thông báo trạng thái và hướng xử lý tương ứng |

Bài mẫu trả kiểu đơn giản `{"code":"...","fields":[...]}` để thấy rõ khác biệt. Trong dự án lớn có thể dùng `ProblemDetail` (RFC 9457), ví dụ `type`, `title`, `status`, `detail` và extension `code`/`errors`. Đó là **lựa chọn định dạng**, không làm thay đổi nơi exception xuất hiện.

Lời khuyên cho server:

1. Thống nhất schema phản hồi lỗi trong toàn API, gồm error code ổn định và field path nếu an toàn.
2. Không trả thẳng stack trace, raw JSON body, đường dẫn file máy chủ hoặc thông điệp Jackson chứa nội dung bí mật.
3. Với validation, trả mã phù hợp cho từng field; khi i18n, render message từ `MessageSource`. Cân nhắc giới hạn số lỗi/phần tử để tránh response quá lớn.
4. Đặt log/metric tách riêng `JSON_SYNTAX`, `JSON_TYPE`, `VALIDATION_FAILED`; đó là tín hiệu khác nhau về bug client và UX.
5. Đảm bảo custom `@RestControllerAdvice` không nuốt mọi exception thành HTTP 400. Lỗi server không liên quan tới input nên được phát hiện đúng (thường HTTP 500), không trá hình thành lỗi người dùng.
6. Kiểm thử cả lỗi thiếu body, JSON null, unknown fields, coercion string-to-number, nested validation, field thuộc enum và giới hạn payload trên cấu hình deploy thực tế.

## 8. Ứng dụng Spring Boot 3 + Java 17 chạy được

Ví dụ dùng **Spring Boot 3.3.13**, Spring MVC, Jackson và Jakarta Validation. Demo có ba error code tách biệt; đồng thời có fallback cho `HttpMessageNotReadableException` không xác định chính xác là cú pháp hay sai kiểu.

### 8.1. Cấu trúc

```text
json-errors-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── JsonErrorsDemoApplication.java
    │   ├── OrderController.java
    │   └── JsonErrorAdvice.java
    └── test/java/example/
        └── OrderControllerTest.java
```

### 8.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>json-errors-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

`spring-boot-starter-web` cung cấp Spring MVC và JSON conversion thông thường qua Jackson. `spring-boot-starter-validation` kích hoạt các Jakarta constraints trong demo; `spring-boot-starter-test` chứa JUnit Jupiter, MockMvc và bộ assertion test.

### 8.3. File JsonErrorsDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonErrorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonErrorsDemoApplication.class, args);
    }
}
```

### 8.4. File OrderController.java

```java
package example;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Các record package-private được đặt trong cùng file theo cú pháp Java 17.
record ShippingAddress(@NotBlank String city) {}

record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @NotNull @Valid ShippingAddress shipping
) {}

record OrderCreated(
        String status, String sku, Integer quantity, String city
) {}

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderCreated create(@Valid @RequestBody CreateOrderRequest request) {
        return new OrderCreated(
                "accepted",
                request.sku(),
                request.quantity(),
                request.shipping().city());
    }
}
```

Các record vừa là Java DTO, vừa khai báo rõ quy tắc validation. `@NotNull @Valid ShippingAddress shipping` đảm bảo nested object không null và validate được `city`. `@NotBlank String sku` kiểm tra chuỗi; `@Min(1) Integer quantity` kiểm tra số dương sau khi deserialize. Method không khai báo `Errors` liền sau request DTO, nên lỗi validation được Spring chuyển tới global exception handler.

### 8.5. File JsonErrorAdvice.java

Đây là phần cốt lõi để **phân loại** thay vì trả chung mọi trường hợp là “invalid JSON”.

```java
package example;

import java.util.List;

import com.fasterxml.jackson.core.JsonParseException;
import com.fasterxml.jackson.databind.exc.MismatchedInputException;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

// Cấu trúc phản hồi của demo, dùng chung cho các nhóm lỗi.
record ApiError(String code, List<String> fields) {}

@RestControllerAdvice
public class JsonErrorAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        String code = classifyUnreadable(ex);
        return new ResponseEntity<>(
                new ApiError(code, List.of()),
                headers,
                status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new ResponseEntity<>(
                new ApiError("VALIDATION_FAILED", fields),
                headers,
                status);
    }

    private static String classifyUnreadable(Throwable error) {
        // Spring có thể bọc lỗi Jackson trong một hoặc nhiều cause.
        boolean typeMismatch = false;
        Throwable cursor = error;

        while (cursor != null) {
            if (cursor instanceof JsonParseException) {
                return "JSON_SYNTAX";
            }
            if (cursor instanceof MismatchedInputException) {
                typeMismatch = true;
            }
            cursor = cursor.getCause();
        }

        // Không đoán tất cả lỗi unreadable đều do cú pháp hoặc kiểu.
        return typeMismatch ? "JSON_TYPE" : "BODY_NOT_READABLE";
    }
}
```

**Vì sao phân loại như vậy?**

- `JsonParseException` cho biết lỗi ở lớp parser, nên `JSON_SYNTAX`.
- `MismatchedInputException` (bao gồm nhiều `InvalidFormatException`) đại diện một số lỗi ánh xạ giá trị/hình dạng đầu vào, nên `JSON_TYPE`.
- Thiếu body hoặc lỗi đọc khác có thể chỉ là `HttpMessageNotReadableException` không có cause thuộc hai loại trên, nên dùng fallback `BODY_NOT_READABLE`.

Điều này chỉ là **phân loại thực dụng cho demo**. Không có bảo đảm mọi lỗi deserialization từ Jackson đều nằm trong `MismatchedInputException`; `JsonMappingException` còn có những subtype liên quan tới bug trong creator, setter, custom deserializer hoặc cấu hình. Trong production, cân nhắc xử lý rõ từng trường hợp, ghi log đầy đủ ở server, phản hồi gọn và an toàn ở client.

`ResponseEntityExceptionHandler` vốn có handler trung tâm cho nhiều exception Spring MVC. Ở đây **override** hai phương thức `handleHttpMessageNotReadable`/`handleMethodArgumentNotValid` để thống nhất body, tránh viết `@ExceptionHandler` trùng với handler kế thừa gây lỗi ánh xạ exception handler.

### 8.6. Chạy và gửi bốn loại request

Cài JDK 17+ và Maven. Từ thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Request hợp lệ:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-100","quantity":2,"shipping":{"city":"Ha Noi"}}'
```

Kỳ vọng HTTP **200**, body JSON:

```json
{"status":"accepted","sku":"A-100","quantity":2,"city":"Ha Noi"}
```

Request **sai cú pháp** (cố ý thiếu `}`):

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-100","quantity":2,'
```

Kỳ vọng HTTP **400**, body:

```json
{"code":"JSON_SYNTAX","fields":[]}
```

Request **sai kiểu** (chuỗi không chuyển được sang số nguyên):

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-100","quantity":"many","shipping":{"city":"Ha Noi"}}'
```

Kỳ vọng HTTP **400**, body:

```json
{"code":"JSON_TYPE","fields":[]}
```

Request **vi phạm Bean Validation**:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":0,"shipping":{"city":""}}'
```

Kỳ vọng HTTP **400**, body:

```json
{"code":"VALIDATION_FAILED","fields":["quantity","shipping.city","sku"]}
```

Với ví dụ này, ba status lỗi đều là 400; **`code` khác nhau**, vì nguyên nhân xảy ra ở tầng khác nhau. Danh sách lỗi validation được sắp xếp theo field để tránh phụ thuộc thứ tự provider. Còn status/body lỗi 415 hoặc 406 không được custom theo schema ở trên: handler kế thừa có thể tạo `ProblemDetail`, nên đừng mong `ApiError` cho mọi loại lỗi HTTP chưa override.

Lệnh `curl` có dấu `\` để nối dòng cho shell POSIX. Trên PowerShell, dùng `curl.exe` và nhập câu lệnh một dòng hoặc áp dụng cú pháp multiline của PowerShell; tránh alias `curl` trỏ tới `Invoke-WebRequest`.

### 8.7. MockMvc kiểm chứng đầy đủ ba tầng lỗi

File `src/test/java/example/OrderControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validJsonReachesController() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"A-100","quantity":2,
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void malformedJsonIsSyntaxFailure() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"A-100\",\"quantity\":2,"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("JSON_SYNTAX"));
    }

    @Test
    void invalidIntegerIsDeserializationFailure() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"A-100","quantity":"many",
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("JSON_TYPE"));
    }

    @Test
    void validJsonObjectCanFailBeanValidation() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"","quantity":0,
                             "shipping":{"city":""}}
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().json("""
                    {"code":"VALIDATION_FAILED",
                     "fields":["quantity","shipping.city","sku"]}
                    """));
    }

    @Test
    void missingBodyIsNeitherSyntaxNorDtoValidation() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("BODY_NOT_READABLE"));
    }

    @Test
    void nullQuantityDeserializesThenFailsNotNull() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"A-100","quantity":null,
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.fields[0]").value("quantity"));
    }

    @Test
    void wrongMediaTypeIs415NotJsonSyntaxError() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void unacceptableResponseTypeIs406NotJsonError() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.TEXT_PLAIN)
                    .content("""
                            {"sku":"A-100","quantity":2,
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isNotAcceptable());
    }
}
```

Chạy:

```bash
mvn test
```

Các test giúp khóa hành vi mong muốn: JSON parser lỗi, mapper lỗi, constraint lỗi, body thiếu, null hợp lệ cú pháp nhưng không hợp lệ theo constraint, và 415/406 liên quan tới media type. Tất cả test chạy qua Spring MVC test context với `MockMvc`; không cần bật HTTP server riêng.

**Giới hạn kiểm thử:** những assertion nêu trên là kỳ vọng theo cấu hình demo. Khi thay đổi Jackson features, đối tượng DTO, constraint groups, error handler hoặc Spring Framework version, chạy lại test và cập nhật hợp đồng một cách có chủ ý.

## 9. Các trường hợp biên thường gây hiểu nhầm

### 9.1. JSON số được đặt trong chuỗi

```json
{"quantity":"2"}
```

Nhiều cấu hình Jackson chuyển được `"2"` thành `Integer(2)`, vậy request có thể **thành công** nếu các field khác hợp lệ. Nếu yêu cầu JSON number tuyệt đối, cần áp dụng chính sách coercion chặt chẽ và viết test `"quantity":"2"` phải bị từ chối. Không có một “bản chất JSON sai kiểu” cố định tách khỏi **hợp đồng deserialization** đã cấu hình.

### 9.2. Trường vắng mặt, null và chuỗi rỗng

| JSON | Đích | Kết quả thường gặp |
| --- | --- | --- |
| Không có `quantity` | `Integer quantity` | `null`, sau đó `@NotNull` báo validation error |
| `"quantity":null` | `Integer quantity` | `null`, `@NotNull` báo validation error |
| `"quantity":""` | `Integer quantity` | Có thể thành `null` hoặc mapping error tùy coercion; cần test |
| `"quantity":"abc"` | `Integer quantity` | Mapping error, không tạo được số |
| `"sku":""` | `String sku` + `@NotBlank` | String hợp lệ về kiểu, validation error |
| `"sku":null` | `String sku` + `@NotBlank` | Null vẫn deserialize được, validation error |
| `"shipping":null` | `@NotNull @Valid ShippingAddress` | Null hợp lệ cú pháp; `@NotNull` báo validation error |
| Không có `shipping.city` | `@Valid ShippingAddress` + `@NotBlank city` | Nếu object shipping được tạo, nested validation báo city |

### 9.3. Date/time, enum và định dạng tùy chỉnh

Giả sử DTO có:

```java
record Appointment(java.time.LocalDate date, Priority priority) {}
enum Priority { LOW, HIGH }
```

JSON `{"date":"tomorrow","priority":"URGENT"}` là JSON đúng cú pháp nhưng Jackson không thể parse ngày hoặc enum theo cấu hình thông thường. Nếu bạn cần ngày theo định dạng khác, dùng cấu hình Jackson như `@JsonFormat` hoặc custom deserializer; `@DateTimeFormat` chủ yếu dành cho Spring type conversion (ví dụ form/query) và không phải giải pháp chung cho JSON `@RequestBody`. Với enum có unknown value, hãy quyết định chính sách thay vì âm thầm map mọi giá trị lạ.

### 9.4. Unknown fields và duplicate keys

JSON `{"sku":"A-100","quantity":1,"shipping":{"city":"HN"},"admin":true}` là đúng cú pháp. `admin` là field **ngoài hợp đồng DTO**, nhưng không nhất thiết gây lỗi với cấu hình Jackson của Spring Boot: unknown property có thể bị bỏ qua. Muốn API từ chối, đặt chính sách strict/deserialize thích hợp và có test. Dữ liệu nhạy cảm trong entity tuyệt đối không nên được expose tự do dưới dạng request DTO có setter tương ứng.

Với duplicate key như `{"quantity":1,"quantity":2}`, JSON parser thường có thể nhận nếu không bật tính năng kiểm tra duplicate. Đừng khẳng định luôn là syntax error. Quyết định chính sách trong API contract, parser settings và kiểm thử.

### 9.5. Validation sau khi controller được gọi

Nếu bạn dùng `Errors` hoặc `BindingResult` ngay sau `@Valid @RequestBody`, các Bean Validation error có thể đi vào method để bạn xử lý thủ công. Nhưng mapper chưa tạo được object thì controller vẫn không thể chạy. Tương tự, tự kiểm tra nghiệp vụ sau khi parse/validation (ví dụ tồn kho) là lỗi ở giai đoạn riêng: một input có thể hợp lệ về JSON, Java type và Bean Validation nhưng vẫn bị service từ chối.

## 10. Quy trình xử lý khi API báo HTTP 400

1. **Ghi lại HTTP method, URL, Content-Type và Accept** trước. Nếu status 415/406, xử lý header/media-type thay vì parser/DTO.
2. **Xác nhận body JSON chuẩn** bằng parser; kiểm tra dấu nháy, dấu phẩy, bracket, escape và encoding. Nếu parser lỗi, sửa producer JSON.
3. **Đối chiếu schema Java và payload**: object/array, number/string/boolean/null, ngày, enum, khóa thuộc tính, generic collection, nested structure; xem cấu hình coercion.
4. **Đọc constraint validation**: `@NotNull`, `@NotBlank`, `@Min`, nested `@Valid`, custom validators và validation groups.
5. **Xem exception chain tại server** để phân biệt parser và mapper, sau đó xử lý qua advice. Không công khai thông tin nhạy cảm của chain.
6. **Kiểm tra API error code**: `JSON_SYNTAX`, `JSON_TYPE`, `VALIDATION_FAILED`; cùng HTTP 400 nhưng hướng xử lý của client khác nhau.
7. **Viết regression test** với một case tối thiểu cho từng tầng, thêm các ranh giới như null, missing body, date/enum không đúng, Content-Type không phù hợp.

Đối với người mới, hãy đặt breakpoint vào `JsonErrorAdvice.handleHttpMessageNotReadable` và `handleMethodArgumentNotValid`. Hai đường đi này đủ để thấy sự khác biệt giữa **“object chưa được tạo”** và **“object đã được tạo nhưng vi phạm constraint”**.

## 11. Bài tự kiểm tra

1. JSON `{"age": 21,}` là loại lỗi gì? **Sai cú pháp** nếu parser tuân JSON chuẩn vì trailing comma.
2. JSON `{"age":"twenty"}` vào `Integer age` là lỗi gì? **Deserialization/type mismatch** theo Jackson thông thường; JSON vẫn đúng cú pháp.
3. JSON `{"age":17}` vào `Integer age` với `@Min(18)` là lỗi gì? **Validation**; không phải lỗi chuyển kiểu.
4. JSON `{"age":null}` vào `Integer age` với `@NotNull` có phải sai cú pháp không? **Không.** Null là literal JSON hợp lệ; `@NotNull` báo vi phạm constraint.
5. JSON `{"age":"21"}` chắc chắn sai kiểu không? **Không chắc.** Jackson có thể chuyển chuỗi số thành integer tùy chính sách coercion.
6. Vì sao `BindingResult` sau `@RequestBody` không bắt mọi lỗi JSON sai cú pháp? **Không có DTO đã deserialize thành công**, nên controller chưa có argument để tiếp nhận kết quả validation.
7. Ngoại lệ Spring bao ngoài JSON parser lỗi là gì? **`HttpMessageNotReadableException`**; cause có thể là `JsonParseException`.
8. Lỗi `@NotBlank` ở DTO `@Valid @RequestBody` không có `Errors` ngay sau thường được báo bằng gì? **`MethodArgumentNotValidException`**.
9. HTTP 415 có nói gì về syntax JSON? **Không nhất thiết.** Nó thường báo media type request không phù hợp với endpoint.
10. Khi enum có giá trị không tồn tại, tại sao không nên mặc định quy về validation? **Jackson có thể thất bại trước khi DTO được tạo**, đó là lỗi deserialization.
11. Vì sao API nên có `code` bên cạnh HTTP status? **Vì cùng HTTP 400 có nhiều giai đoạn lỗi và hướng xử lý khác nhau**.
12. Nếu DTO parse và validate thành công nhưng inventory service báo hết hàng, có phải lỗi JSON không? **Không.** Đó là quy tắc nghiệp vụ, cần hợp đồng lỗi và HTTP status riêng.

## 12. Nguồn tài liệu và điểm cần nhớ

- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): giải mã body qua `HttpMessageConverter` và xử lý `@Valid`/`Errors`.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [Spring MVC — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): cơ chế chọn converter từ media type.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): override các nhánh xử lý `HttpMessageNotReadableException` và `MethodArgumentNotValidException`.
- [Jackson Databind — MismatchedInputException](https://www.javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/exc/MismatchedInputException.html): lỗi mapping/deserialize đầu vào.
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/3.0/): constraint validation trên Java object.

**Quy tắc để nhớ:** *Syntax* trả lời “JSON có đọc thành tài liệu được không?”; *type/deserialization* trả lời “tài liệu có biến thành object Java đích được không?”; *validation* trả lời “object đã tạo có thỏa hợp đồng dữ liệu không?”. Ba câu hỏi khác nhau có thể cùng dẫn tới HTTP 400, nên phải phân loại theo tầng xử lý và cung cấp phản hồi rõ ràng.
