# Ràng buộc giá trị trả về và lỗi hợp đồng phía server trong Spring MVC

## 1. Tại sao phải kiểm tra cả giá trị trả về?

Thông thường khi nhắc đến validation ở Spring MVC, ta nghĩ đến việc kiểm tra dữ liệu **client gửi vào**: một `@RequestBody` thiếu tên, một `@RequestParam` là số âm hoặc một form có email sai định dạng. Nhưng Jakarta Validation còn hỗ trợ kiểm tra **giá trị trả về của phương thức**. Đây là một hợp đồng khác về bản chất:

- **Input constraint:** yêu cầu caller/client gửi dữ liệu đáp ứng điều kiện. Client gửi sai thì phản hồi thường là **400 Bad Request**.
- **Return-value constraint:** phương thức **đã chạy** nhưng kết quả do phía server sản xuất không đáp ứng điều kiện đã công bố. Đây thường là **lỗi hợp đồng hoặc lỗi lập trình/vận hành phía server**, vì vậy phản hồi HTTP phù hợp thường là **500 Internal Server Error**, không phải 400.

Ví dụ một REST controller trả về dữ liệu hóa đơn:

```java
@GetMapping("/receipts/{id}")
@NotNull
@Valid
public ReceiptView getReceipt(@PathVariable @Min(1) long id) {
    return receiptService.load(id);
}
```

Đây là đoạn phương thức minh họa, giả sử `ReceiptView` có các constraint trên trường và `receiptService` tồn tại. Hai hướng kiểm tra có thể xảy ra trong cùng một method:

1. `@Min(1)` trên `id` kiểm tra **đầu vào**. Nếu URL chứa `/receipts/0`, request không đạt hợp đồng mà controller yêu cầu.
2. `@NotNull` trên **chính phương thức** yêu cầu return value không null.
3. `@Valid` trên **chính phương thức** yêu cầu kiểm tra các constraint bên trong object `ReceiptView` được trả về. Ví dụ DTO trả về có `@NotBlank reference` nhưng lại chứa `reference=""`.
4. Nếu đầu vào sai, server nên trả lỗi 400. Nếu object trả về sai, server không nên đổ lỗi cho client; đây là lỗi hợp đồng phía server, nên báo 500 và không trả đối tượng không hợp lệ như dữ liệu thành công.

**Phạm vi:** Spring Framework 6.1–6.2, Spring Boot 3.x, Java 17+, Jakarta Validation 3.x, Servlet Spring MVC. Bài cũng phân biệt built-in MVC method validation với method validation AOP ở tầng service. Trong Spring Framework trước 6.1, hành vi controller method validation và cấu hình cần thiết khác đáng kể; không áp toàn bộ ví dụ nguyên xi cho Spring 5/WebFlux.

## 2. “Hợp đồng phía server” thực chất là gì?

### 2.1. Precondition và postcondition

Một phương thức có thể định nghĩa:

- **Precondition / điều kiện đầu vào:** phải thỏa **trước** khi thân phương thức được gọi; ví dụ `quantity >= 1`.
- **Postcondition / điều kiện đầu ra:** phải thỏa **sau** khi thân phương thức trả về; ví dụ mã biên nhận không được rỗng và tổng số dòng phải dương.

Minh họa:

```java
public record ReceiptView(
        @NotBlank String reference,
        @Positive int lineCount
) {}
```

Khi server tạo `new ReceiptView("RCPT-17", 2)`, object đáp ứng các ràng buộc. Khi server tạo `new ReceiptView(" ", 0)`, object **không đáp ứng hợp đồng đầu ra**, dù request đầu vào có thể hoàn toàn hợp lệ.

Có ba nơi liên quan nhưng độc lập:

| Lớp | Dữ liệu được kiểm tra | Ai phải sửa khi lỗi? |
| --- | --- | --- |
| MVC input validation | Query/path/form/JSON sau chuyển đổi, ràng buộc tham số | Thông thường client |
| MVC return-value validation | Giá trị do handler method trả về | Server/nhà phát triển hệ thống |
| Service/domain invariant | Kết quả nghiệp vụ, trạng thái transaction và dữ liệu lưu trữ | Tùy nguyên nhân, thường trách nhiệm service/domain |

**Lỗi hợp đồng trả về không phải lỗi người dùng nhập liệu.** Client không thể biết hoặc sửa một `reference` rỗng do server ánh xạ sai dữ liệu. Đặt HTTP 400 cho lỗi này làm sai ý nghĩa API, gây lệch metric và khiến client thử sửa một request vốn đã hợp lệ.

### 2.2. Constraint trên method khác constraint trên DTO

```java
@NotNull
@Valid
public ReceiptView load() {
    // ...
}
```

- `@NotNull` ở đây là **constraint trực tiếp lên return value** của phương thức.
- `@Valid` ở đây là **cascading validation**: đi vào object trả về và kiểm tra các constraint bên trong.
- `@Valid` **không tự cấm null**. Trong Jakarta Validation, khi cascade gặp null, nó không có object con để kiểm tra; muốn cấm null phải dùng `@NotNull`.
- `@NotNull` **không tự kiểm tra sâu** các trường `reference`, `lineCount`. Muốn kiểm tra chúng cần cascade với `@Valid`.
- Các constraint trên `ReceiptView` vẫn có thể được kiểm tra khi DTO dùng ở nơi khác, nhưng việc DTO có annotation **không bảo đảm** mọi method trả về DTO đều tự được validation nếu không có điểm kích hoạt.

### 2.3. Validation không thể thay mọi invariant

Trả `@Positive int lineCount` giúp phát hiện một kết quả bằng 0 khi domain đòi hỏi số dương. Nhưng các điều kiện như “tổng tiền bằng tổng các dòng”, “chỉ người có quyền được xem hóa đơn” và “không được lộ thông tin thanh toán” có thể cần kiểm tra nghiệp vụ, phân quyền và thiết kế truy vấn cụ thể.

Tương tự, một return value hợp lệ theo `@NotNull`/`@NotBlank` chưa chứng minh dữ liệu đúng về **ý nghĩa nghiệp vụ**. Bean Validation là một hàng rào hợp đồng hữu ích, không thay thế toàn bộ thiết kế domain.

## 3. Jakarta Validation chuẩn hỗ trợ kiểm tra return value như thế nào?

### 3.1. Các annotation thường gặp

Có thể đặt các constraint trực tiếp trên method không phải `void`:

```java
@NotNull
public ReceiptView load() { /* ... */ }

@Positive
public long calculateCount() { /* ... */ }

@NotBlank
public String createReference() { /* ... */ }
```

Ba method ở trên **chỉ là snippet minh họa**. Thực tế phải có thân method trả về giá trị đúng kiểu và package/import tương ứng.

Đặt constraint trên method có nghĩa constraint áp dụng cho **kết quả**, không phải tham số. Annotation `@Min(1)` trên tham số `id` vẫn là kiểm tra input.

Với DTO:

```java
@NotNull
@Valid
public ReceiptView load() {
    return new ReceiptView(" ", 0);
}
```

Trong bối cảnh method validation đã được kích hoạt và nhóm Default được chọn, provider có thể phát hiện **hai lỗi lồng nhau**: `reference` không đạt `@NotBlank` và `lineCount` không đạt `@Positive`.

### 3.2. ExecutableValidator: API Jakarta thuần

Jakarta Validation định nghĩa `ExecutableValidator` để kiểm tra method/constructor:

```java
ExecutableValidator executable =
        validator.forExecutables();

executable.validateParameters(
        target, method, argumentValues);

executable.validateReturnValue(
        target, method, returnedValue);
```

Đây là đoạn **minh họa API**, giả sử `validator`, `target`, `method`, `argumentValues`, `returnedValue` đã được chuẩn bị. Những phương thức này thuộc package `jakarta.validation.executable`; chúng không phụ thuộc riêng Spring hay Hibernate Validator.

Về ý tưởng, sau khi method trả về kết quả, framework có thể gọi `validateReturnValue(...)` để lấy `Set<ConstraintViolation<T>>`. Provider báo vi phạm, còn **framework** quyết định nên ném exception gì và chuyển thành HTTP status nào.

### 3.3. Property path cho lỗi return value

Violation trên method return thường có đường dẫn chứa method node và node **`<return value>`**, sau đó có thể là property con trong trường hợp cascade. Ví dụ dạng khái niệm:

```text
getReceipt.<return value>.reference
getReceipt.<return value>.lineCount
```

Chuỗi thật có thể chứa thông tin method và tên node khác tùy provider/version. Hãy dùng metadata `ConstraintViolation#getPropertyPath()` để xác định vị trí lỗi, thay vì dùng message đã được dịch làm một mã phân loại lỗi ổn định.

Trong `jakarta.validation.Path.Node` có khái niệm **`RETURN_VALUE`**. Khi debug, việc phát hiện node này cho biết ràng buộc liên quan đến output, không phải cứ thấy bất kỳ path nào là lỗi từ request field.

## 4. Spring MVC 6.1+ kích hoạt return-value validation ở đâu?

Spring Framework 6.1 bổ sung **built-in method validation cho handler methods** của MVC. Nó hỗ trợ constraint đặt trực tiếp trên **method parameters** hoặc **return value** và có thể cascade bằng `@Valid`. Với controller không bị method validation AOP phủ lên, Spring kiểm tra:

```text
HTTP request
    |
    v
Routing / argument resolution / deserialization
    |
    v
Method validation trên tham số
    |  nếu sai -> HandlerMethodValidationException (input)
    v
Controller method được gọi
    |
    v
Return value của controller
    |
    v
Method validation trên return value
    |  nếu sai -> HandlerMethodValidationException (return)
    v
Return-value handler / HttpMessageConverter / response
```

Cụ thể:

- `@Min(1)` đặt trên `@PathVariable long id` có thể kích hoạt method validation cho input.
- `@NotNull` đặt trên method return cũng là **constraint trực tiếp** và là tín hiệu để MVC thực hiện method validation.
- `@Valid` trên method return yêu cầu cascade. Đối với object result, kết hợp `@NotNull @Valid` là rõ ràng: không null và kiểm tra các field lồng nhau.
- Khi một handler có direct method constraints, **method validation** có thể thay thế validation từng argument vì nó bao phủ cả parameter constraints và cascaded constraints.
- Chỉ có `@Valid` trên tham số command object mà không có constraint trực tiếp, Spring MVC có thể dùng argument-level validation, thường báo `MethodArgumentNotValidException`; không cần suy luận rằng mọi `@Valid` tạo `HandlerMethodValidationException`.

Theo Spring MVC, lỗi method validation thường được báo bằng:

```java
org.springframework.web.method.annotation
        .HandlerMethodValidationException
```

Exception này có method `isForReturnValue()` và status tương ứng:

| Vi phạm | `isForReturnValue()` | HTTP status mặc định |
| --- | --- | --- |
| Constraint trên đầu vào | `false` | **400 Bad Request** |
| Constraint trên kết quả phương thức | `true` | **500 Internal Server Error** |

Hành vi 400/500 này là **phân loại có chủ đích** của Spring. Đừng viết một handler `@ExceptionHandler(HandlerMethodValidationException.class)` trả 400 cho tất cả trường hợp, vì như vậy sẽ che khuất lỗi server.

### 4.1. Vai trò @Validated cấp lớp ở controller

Spring MVC 6.1+ có điểm cần chú ý: nếu đặt `@Validated` lên **controller class**, việc kiểm tra phương thức có thể được thực hiện thông qua **AOP proxy** thay vì cơ chế built-in của MVC. Tài liệu Spring khuyến nghị **bỏ `@Validated` cấp lớp khỏi controller** khi muốn dùng built-in method validation mới.

Do đó, các ví dụ runnable ở dưới **không** đặt `@Validated` trên controller type. Điều này giúp kiểm tra được `HandlerMethodValidationException` rõ ràng.

### 4.2. Với @RequestBody và @RequestPart thì sao?

Nếu controller có:

```java
@PostMapping("/receipts")
public void submit(
        @Valid @RequestBody ReceiptInput input) {
    // ...
}
```

và `ReceiptInput` là command object, Spring thông thường validate riêng argument sau khi deserialize, rồi ném `MethodArgumentNotValidException` nếu input sai. Nhưng nếu cùng handler bổ sung direct constraint trên tham số hoặc return, built-in method validation có thể được chọn, thay đổi exception path.

Bài hiện tại tập trung vào **giá trị trả về**, vì vậy không dùng `BindingResult` để “bắt” lỗi return. `BindingResult`/`Errors` ngay sau một tham số là cơ chế xử lý **argument binding/validation**, không phải cách gom các lỗi hợp đồng return value xảy ra **sau khi thân method chạy xong**.

## 5. Dự án thực hành: kiểm tra hợp đồng trước khi trả JSON

Ta tạo ứng dụng REST với một endpoint:

```text
GET /api/receipts/{id}
```

Các kịch bản cố ý:

- `id = 7` → đầu vào hợp lệ, trả DTO hợp lệ → HTTP 200.
- `id = 0` → `@Min(1)` trên path parameter không đạt → HTTP 400.
- `id = 8` → service/controller tạo DTO có `reference=" "` và `lineCount=0` → HTTP 500.
- `id = 9` → controller trả `null`, vi phạm return `@NotNull` → HTTP 500.

Những giá trị đặc biệt 8 và 9 chỉ để demo cách phát hiện **lỗi hợp đồng phía server**. Ứng dụng production phải sửa nguồn tạo kết quả sai, không cố tình trả dữ liệu hỏng.

### 5.1. Cấu trúc và dependency

Dự án dùng Spring Boot 3.3.6, Spring Framework 6.1.x và Java 17.

```text
return-contract-demo/
  settings.gradle
  build.gradle
  src/
    main/java/com/example/returncontract/
      ReturnContractApplication.java
      ReceiptView.java
      ReceiptController.java
      ApiExceptionAdvice.java
    test/java/com/example/returncontract/
      ReceiptControllerTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'return-contract-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
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
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` có Spring MVC, `spring-boot-starter-validation` có Jakarta Validation provider (thường là Hibernate Validator). Không cần `spring-boot-starter-aop` cho **built-in MVC method validation** trong ví dụ này. Nếu triển khai service-level validation bằng AOP ở phần sau, cơ chế proxy/config sẽ phải được kiểm tra riêng.

### 5.2. Application

Tệp `src/main/java/com/example/returncontract/ReturnContractApplication.java`:

```java
package com.example.returncontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReturnContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReturnContractApplication.class, args);
    }
}
```

### 5.3. DTO định nghĩa hợp đồng đầu ra

Tệp `src/main/java/com/example/returncontract/ReceiptView.java`:

```java
package com.example.returncontract;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record ReceiptView(
        @NotBlank String reference,
        @Positive int lineCount
) {}
```

Các ràng buộc:

- `@NotBlank` trên `reference`: không null, không rỗng, không chỉ có khoảng trắng.
- `@Positive` trên `lineCount`: số phải lớn hơn 0.
- Record immutable giúp kết quả được định nghĩa tại thời điểm construct, nhưng **không tự động chạy validation** trong constructor. Có thể tạo `new ReceiptView(" ", 0)` trong Java; nó chỉ bị báo lỗi khi có điểm kích hoạt Bean Validation.

Điều này rất quan trọng: `record` và constraint annotations là các công cụ khác nhau. Không nên tuyên bố một DTO “an toàn” chỉ vì có `@NotBlank`/`@Positive` trên record components.

### 5.4. Controller có constraint trên tham số và giá trị trả về

Tệp `src/main/java/com/example/returncontract/ReceiptController.java`:

```java
package com.example.returncontract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ReceiptController {

    // @Min kiểm tra input; @NotNull và @Valid kiểm tra return.
    @GetMapping("/receipts/{id}")
    @NotNull
    @Valid
    public ReceiptView getReceipt(
            @PathVariable("id") @Min(1) long id) {

        if (id == 8) {
            // Cố tình vi phạm hai constraint bên trong DTO.
            return new ReceiptView(" ", 0);
        }

        if (id == 9) {
            // Cố tình vi phạm constraint @NotNull trên method.
            return null;
        }

        return new ReceiptView("RCPT-" + id, 2);
    }
}
```

Ở đây **không có `@Validated` cấp class**, nên controller dùng built-in method validation của Spring MVC 6.1+. Với `id = 0`, input không đạt `@Min(1)`; thân method không nên được chạy như một lời gọi hợp lệ. Với `id = 8` hoặc 9, method chạy và trả object/null vi phạm ràng buộc; Spring có thể ngăn một kết quả không hợp lệ đi tiếp đến bước viết JSON.

Việc trả `null` từ handler `@RestController` không nên dùng để biểu diễn “không tìm thấy” trong API thực tế. Nếu không tìm thấy resource, hãy đưa ra kết quả/exception nghiệp vụ rõ ràng như HTTP 404; nhánh `id = 9` chỉ dùng làm ca kiểm thử return `@NotNull`.

### 5.5. Exception handler phân biệt input 400 và output 500

Tệp `src/main/java/com/example/returncontract/ApiExceptionAdvice.java`:

```java
package com.example.returncontract;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, String>> handleMethodValidation(
            HandlerMethodValidationException exception) {

        if (exception.isForReturnValue()) {
            // Return-value violation: lỗi hợp đồng phía server.
            // Production: log/metric/correlation-id ở nơi an toàn.
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of(
                            "code", "SERVER_CONTRACT_VIOLATION",
                            "message", "Không thể hoàn tất yêu cầu"
                    ));
        }

        // Input violation: dữ liệu request không thỏa điều kiện.
        return ResponseEntity
                .badRequest()
                .body(Map.of(
                        "code", "INVALID_REQUEST",
                        "message", "Tham số yêu cầu không hợp lệ"
                ));
    }
}
```

Điểm quan trọng nhất của handler là **`exception.isForReturnValue()`**. Spring đã phân biệt return/input trong chính exception và mặc định HTTP 500/400; ví dụ định nghĩa body JSON riêng nhưng **giữ nguyên tính chất lỗi**.

Trong production, nên ghi nhận lỗi return contract ở server bằng log/metric có request ID và thông tin điều tra phù hợp; không phản chiếu mọi property path/giá trị nội bộ hoặc stack trace cho client. Ngay cả khi lỗi ràng buộc có message có ích với lập trình viên, người dùng không có hành động gì để sửa một DTO đầu ra hỏng.

### 5.6. HTTP request và kết quả

Khởi chạy:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

**Đầu ra hợp lệ:**

```bash
curl -i http://localhost:8080/api/receipts/7
```

Kỳ vọng HTTP **200 OK** và JSON:

```json
{
  "reference": "RCPT-7",
  "lineCount": 2
}
```

**Tham số đầu vào sai:**

```bash
curl -i http://localhost:8080/api/receipts/0
```

Kỳ vọng HTTP **400 Bad Request**:

```json
{
  "code": "INVALID_REQUEST",
  "message": "Tham số yêu cầu không hợp lệ"
}
```

**Server tạo DTO không hợp lệ:**

```bash
curl -i http://localhost:8080/api/receipts/8
```

Kỳ vọng HTTP **500 Internal Server Error**:

```json
{
  "code": "SERVER_CONTRACT_VIOLATION",
  "message": "Không thể hoàn tất yêu cầu"
}
```

**Server trả null trái hợp đồng:**

```bash
curl -i http://localhost:8080/api/receipts/9
```

Kỳ vọng HTTP **500 Internal Server Error** với cùng mã `SERVER_CONTRACT_VIOLATION`.

Những JSON body này là **contract do `ApiExceptionAdvice` định nghĩa trong demo**, không phải hình dạng mặc định bắt buộc của mọi ứng dụng Spring. Nếu bỏ advice, Spring MVC có thể dùng error response mặc định hoặc handler khác tùy cấu hình. Quy tắc nền tảng cần ghi nhớ là lỗi **input** và **return** không có cùng bản chất.

## 6. Kiểm thử qua MockMvc: xác định phía chịu trách nhiệm

Tệp `src/test/java/com/example/returncontract/ReceiptControllerTest.java`:

```java
package com.example.returncontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReceiptControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validReturnValueProducesHttp200() throws Exception {
        mvc.perform(get("/api/receipts/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.reference").value("RCPT-7"))
            .andExpect(jsonPath("$.lineCount").value(2));
    }

    @Test
    void invalidInputProducesHttp400() throws Exception {
        mvc.perform(get("/api/receipts/0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void invalidNestedOutputProducesHttp500() throws Exception {
        mvc.perform(get("/api/receipts/8"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("SERVER_CONTRACT_VIOLATION"));
    }

    @Test
    void nullOutputProducesHttp500() throws Exception {
        mvc.perform(get("/api/receipts/9"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("SERVER_CONTRACT_VIOLATION"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Kỳ vọng cả **bốn test thành công** trong cấu hình ví dụ. Chúng phân biệt:

- Đường thành công với DTO đáp ứng hợp đồng.
- Lỗi đầu vào do caller gây ra → 400.
- Lỗi bean lồng nhau trong giá trị trả về → 500.
- Giá trị trả về null trái `@NotNull` → 500.

Test `MockMvc` kiểm tra **hành vi MVC thật**, không chỉ gọi `new ReceiptView(...)` rồi xét annotation. Một DTO được tạo thủ công mà không có `Validator#validate` hoặc method validation sẽ không tự báo vi phạm.

Nếu muốn kiểm tra chính xác exception thay vì chỉ HTTP body, trong test có thể kiểm tra `MvcResult#getResolvedException()` là `HandlerMethodValidationException` và `isForReturnValue()` có giá trị mong đợi. Đừng truy cập thông tin lỗi từ raw message đã được nội suy để đoán input hay output, vì ngôn ngữ/bundle có thể thay đổi.

## 7. Phân biệt validation của output với validation của input

### 7.1. Trường hợp giống nhau: dùng Jakarta constraints

Cả input và output có thể dùng:

```java
@NotNull
@NotBlank
@Size
@Positive
@Valid
```

Sự khác biệt **không nằm ở tên annotation** mà ở **vị trí đặt constraint** và **giai đoạn lifecycle**.

Ví dụ:

```java
@PostMapping("/calculate")
@Positive
public int calculate(
        @RequestParam @Min(1) int quantity) {
    return quantity - 5;
}
```

Đây là method minh họa. Với `quantity = 1`, input đạt `@Min(1)` nhưng method trả `-4` vi phạm `@Positive` trên return. Không thể gọi đây là “người dùng gửi sai quantity”. Trách nhiệm nằm ở logic `calculate` hoặc hợp đồng mà server công bố.

### 7.2. Return value được kiểm tra sau side effect

Ví dụ một service:

```java
@Transactional
@NotNull
public ReceiptView saveReceipt(ReceiptInput input) {
    repository.save(...);
    return null;
}
```

Đây là **pseudocode minh họa**, không biên dịch độc lập: `ReceiptInput`, `repository`, `@Transactional` được giả định có trong ứng dụng. Điều cần hiểu là return validation xảy ra **sau khi thân phương thức thực thi**. Lệnh ghi dữ liệu/đẩy message/gọi hệ thống khác có thể đã được thực hiện.

**Không kết luận rằng return-value constraint tự bảo đảm rollback.** Với Spring AOP, transaction advice và method-validation advice có thứ tự cụ thể; một lỗi xuất hiện sau khi transaction advice đã hoàn tất có thể không quay lui transaction đã commit. Các side effect ngoài database như email, Kafka, object storage cũng không tự thu hồi chỉ vì method return vi phạm Bean Validation.

Do đó hãy giữ invariant trọng yếu ngay trong service/domain trước khi ghi dữ liệu; coi return validation là **hàng rào phát hiện**, không phải giải pháp transaction integrity duy nhất.

### 7.3. Return validation không có nghĩa response đã an toàn tuyệt đối

Với handler trả DTO thường, Spring MVC có thể kiểm tra method return trước khi serialize và ghi body. Nhưng các kiểu output khác cần xét riêng:

- `ResponseEntity<Dto>` là wrapper phản hồi; constraint đặt trên method có thể áp dụng lên **wrapper** chứ không mặc nhiên áp vào `Dto` bên trong. Không giả định `@Valid` luôn đi qua mọi wrapper mà không có value extractor phù hợp.
- `StreamingResponseBody`, `ResponseBodyEmitter`, SSE và các response streaming có thể bắt đầu ghi dữ liệu theo luồng; việc phát hiện lỗi sau khi response **đã commit** không thể đơn giản đổi HTTP status thành 500.
- `Callable`, `CompletableFuture` và các kiểu bất đồng bộ có lifecycle/đường xử lý riêng; cần kiểm thử version và adapter thực tế trước khi nói method-return constraint bao phủ kết quả cuối cùng.
- Jackson serialization vẫn có thể thất bại sau khi return validation đã PASS. Một DTO hợp lệ theo Bean Validation không chứng minh chắc chắn converter serialize thành công.

Bài demo cố ý trả một **record DTO đồng bộ trực tiếp** để bảo đảm điểm kiểm tra được quan sát rõ.

## 8. Service method validation bằng AOP: một đường khác

Ở tầng Spring service thông thường, method validation qua **AOP proxy** khác built-in MVC method validation.

Ví dụ **minh họa** về service Spring-managed:

```java
package com.example.returncontract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ReceiptService {

    @NotNull
    @Valid
    public ReceiptView fetch(boolean breakContract) {
        if (breakContract) {
            return new ReceiptView(" ", 0);
        }
        return new ReceiptView("RCPT-SERVICE", 3);
    }
}
```

Để bật service method validation, ứng dụng phải có Jakarta Validation provider, `MethodValidationPostProcessor` và một AOP proxy phù hợp. Trong Spring Boot có validation starter, processor thường được tự cấu hình; các ứng dụng Java/Spring Framework thuần có thể phải đăng ký nó. Khi dùng AOP proxying, đảm bảo dependency AOP cần thiết hiện diện; có thể thêm `spring-boot-starter-aop` trong dự án service-level để biểu đạt rõ ý định.

Nếu gọi **Spring bean proxy** của `ReceiptService`:

```java
receiptService.fetch(true);
```

thì default AOP method validation thường ném:

```java
jakarta.validation.ConstraintViolationException
```

Với `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, một đường khác là:

```java
org.springframework.validation.method.MethodValidationException
```

Trong khi đó, controller built-in MVC 6.1+ của ví dụ chính dùng:

```java
org.springframework.web.method.annotation.HandlerMethodValidationException
```

Phân biệt:

| Điểm kích hoạt | Cơ chế | Exception thường gặp |
| --- | --- | --- |
| Spring MVC built-in method validation | Handler method (Framework 6.1+) | `HandlerMethodValidationException` |
| Spring service method validation mặc định | AOP proxy + `@Validated` ở type | `ConstraintViolationException` |
| Spring service method validation với adapter | AOP + `adaptConstraintViolations=true` | `MethodValidationException` |
| Jakarta API trực tiếp | `Validator#forExecutables()` | Trả violation set; caller quyết định hành động |
| `@Valid @RequestBody` command object riêng biệt | Argument validation | `MethodArgumentNotValidException` |

**Đừng viết một global handler bắt mọi `ConstraintViolationException` rồi mặc định trả 400.** Nếu exception đó là return contract violation của service, 400 là sai trách nhiệm. AOP exception có thể chứa nhiều `ConstraintViolation` gồm input và output; cần phân loại theo điểm phát sinh, property path, metadata và contract tại boundary.

### 8.1. Self-invocation và proxy caveats

Ví dụ:

```java
@Service
@Validated
public class InternalCallExample {

    public void outer() {
        inner();  // gọi nội bộ, không đi qua proxy
    }

    @NotNull
    public String inner() {
        return null;
    }
}
```

Đây là **phản ví dụ** nhằm chỉ rõ một hạn chế. Lời gọi `this.inner()` thông thường bỏ qua Spring AOP proxy nên return validation của `inner` không được interceptor áp dụng. Tương tự, đối tượng tạo bằng `new` ngoài Spring container không được AOP bảo vệ, và method `private`/`final` có giới hạn interception tùy cơ chế proxy.

Nếu hợp đồng đầu ra là bất biến nghiệp vụ bắt buộc, **đừng chỉ trông cậy vào annotation AOP** trên method có thể bị gọi qua đường nội bộ; cần thiết kế logic domain/test phù hợp.

### 8.2. Không trộn @Validated cấp class của service với controller

Đối với service, `@Validated` cấp type là cách thông dụng chọn bean cho `MethodValidationPostProcessor`. Đối với controller Spring MVC 6.1+, cùng annotation cấp class có thể chuyển validation sang **AOP proxy** và khác đường built-in MVC. Vì vậy lời khuyên “mọi class có constraint đều phải thêm `@Validated`” là sai.

## 9. Kiểm tra return value theo group

Tương tự input validation, Jakarta Validation có **validation groups** cho output. Ví dụ:

```java
public interface PublicApi {}

public record ReceiptView(
        @NotBlank(groups = PublicApi.class) String reference,
        @Positive(groups = PublicApi.class) int lineCount
) {}
```

Nếu một return validation chạy chỉ với `Default`, các constraints thuộc riêng `PublicApi` **không tự động được xét**. Có thể chọn group theo cách framework hỗ trợ hoặc dùng API Jakarta trực tiếp:

```java
ExecutableValidator executable = validator.forExecutables();

Set<ConstraintViolation<ReceiptService>> violations =
        executable.validateReturnValue(
                receiptService,
                method,
                returned,
                PublicApi.class
        );
```

Đoạn này là snippet sử dụng `jakarta.validation.executable.ExecutableValidator`, `jakarta.validation.ConstraintViolation` và `java.util.Set`; `validator`/`receiptService`/`method`/`returned` được giả định chuẩn bị sẵn. Trong ứng dụng thật, chọn group rõ ràng theo hợp đồng API và kiểm tra xem Spring version/đường validation có đọc `@Validated(Group.class)` tại vị trí mong muốn hay không.

**Group sequence** (`@GroupSequence`) xác định thứ tự các nhóm; nó không giống một mảng groups không có thứ tự kiểm tra bắt buộc. Tránh vô tình bỏ qua constraints thuộc Default khi chuyển sang group mới.

Cũng đừng lẫn `@Valid` với constraint nhóm riêng: `@Valid` là cascading marker; nó không có thuộc tính `groups`. Nếu cần chuyển group khi cascade vào nested object, Jakarta Validation có `@ConvertGroup` tại vị trí cascade được phép; chỉ dùng khi nghiệp vụ có yêu cầu rõ.

## 10. Xử lý lỗi server-side contract thế nào cho đúng?

### 10.1. Status code: không đổ lỗi cho client

| Kết quả | HTTP thường phù hợp | Lý do |
| --- | --- | --- |
| Client gửi `id=0` trái `@Min(1)` | 400 | Caller có thể sửa input |
| Client gửi JSON malformed | 400 | Parser không đọc được input |
| Controller tự trả DTO có trường rỗng trái `@NotBlank` | 500 | Server không giữ hợp đồng đầu ra |
| Service trả null trái `@NotNull` | 500 | Server không đáp ứng postcondition |
| Resource không tồn tại (business outcome hợp lệ) | 404 | Không nhất thiết là lỗi hợp đồng |
| Client không được phép xem resource | 403/404 tùy chính sách | Authorization khác Bean Validation |
| Serialization thất bại | Thường 500 nếu response chưa commit | Có thể xảy ra sau validation |
| Async/streaming lỗi sau response đã commit | Không luôn đổi được status | Cần protocol/observability riêng |

HTTP 500 không nói lên **nguyên nhân chi tiết** của bug. Nó báo rằng hệ thống không thể hoàn tất yêu cầu đúng hợp đồng. Nếu một return constraint phản ánh business invariant chưa được đáp ứng, cần điều tra tầng tạo dữ liệu, mapping DTO, service và transaction, không ép frontend “sửa field” vốn không đến từ frontend.

### 10.2. Error body ổn định nhưng không lộ dữ liệu

Một phản hồi phù hợp cho client:

```json
{
  "code": "SERVER_CONTRACT_VIOLATION",
  "message": "Không thể hoàn tất yêu cầu"
}
```

Có thể kèm `correlationId`/trace ID nếu cơ chế log được thiết kế đúng. Không nên trả:

- Nội dung object chưa được kiểm tra như token hoặc thông tin cá nhân.
- Stack trace, internal Java class, field path nội bộ, SQL hoặc service endpoint.
- Raw `ConstraintViolation#getInvalidValue()` của dữ liệu nhạy cảm.
- Message của EL/validator có thể chứa dữ liệu request hoặc internals.

Ở phía server, cần log **nguyên nhân đủ điều tra**, kèm request ID, method, loại vi phạm (return/input), thời điểm xảy ra, phiên bản triển khai và context cần thiết được lọc dữ liệu nhạy cảm.

### 10.3. Cảnh báo và số liệu

Lỗi return contract nên được coi là **lỗi cần phát hiện và sửa**:

1. Metric riêng như `server_return_contract_violations_total`, phân nhóm theo endpoint/service.
2. Log lỗi có correlation ID để truy vết giữa controller và service.
3. Alert theo tỷ lệ/lượng lỗi tăng, tránh spam log khi một bug xảy ra hàng loạt.
4. Test regression cho chính object/path/condition từng làm vi phạm.
5. Rà soát việc mapping DTO và thứ tự commit/serialize nếu có side effects.

Không dùng return validation như cơ chế âm thầm “biến lỗi server thành dữ liệu mặc định”. Tự thay `null` bằng một object placeholder để đạt `@NotNull` có thể che giấu lỗi nghiệp vụ nếu object đó không phản ánh sự thật.

## 11. Những giả định dễ sai

**Sai lầm 1 — Xem mọi validation error là lỗi nhập liệu.** Return constraint được server tự đặt trên giá trị do server sản xuất; thất bại thường là 500, không phải 400.

**Sai lầm 2 — Chỉ đặt @Valid trên return rồi nghĩ null bị cấm.** Cascade bỏ qua null. Dùng `@NotNull` nếu hợp đồng yêu cầu result không null.

**Sai lầm 3 — Chỉ đặt @NotNull trên return rồi nghĩ các field lồng nhau được kiểm tra.** `@NotNull` chỉ bảo đảm có object. Thêm `@Valid` nếu muốn cascade vào field constraint.

**Sai lầm 4 — Không có điểm kích hoạt method validation.** Annotation trên method có thể tồn tại trong source nhưng lời gọi ngoài Spring proxy/manual validator không chạy kiểm tra. Spring MVC 6.1+ có built-in path riêng; service AOP phải có bean/proxy thích hợp.

**Sai lầm 5 — Đặt @Validated trên mọi controller.** Controller class-level `@Validated` có thể chuyển sang AOP, thay đổi exception/lifecycle và làm test dựa trên `HandlerMethodValidationException` thất bại.

**Sai lầm 6 — Bắt HandlerMethodValidationException rồi luôn trả 400.** Phải phân biệt `isForReturnValue()`; lỗi output mặc định là 500.

**Sai lầm 7 — Bắt mọi ConstraintViolationException rồi trả 400.** Ở service AOP, exception có thể là postcondition violation. Cần phân loại đúng boundary và contract.

**Sai lầm 8 — Nhầm @Valid @RequestBody với return validation.** Một bên là Bean Validation trên object request sau deserialize; một bên là method validation trên giá trị do controller trả về.

**Sai lầm 9 — Dựa vào số lượng hoặc thứ tự violation để phân loại nguyên nhân.** Constraint order không được cam kết; dùng node kind/path và metadata, không đoán từ phần tử đầu tiên.

**Sai lầm 10 — Nghĩ return validation sẽ rollback mọi side effect.** Phương thức đã chạy; transaction advice/async/event có thể có lifecycle riêng. Bảo đảm invariant trước khi commit và hiểu thứ tự AOP advice.

**Sai lầm 11 — Coi @Valid chắc chắn kiểm tra sâu mọi ResponseEntity/async wrapper.** Hợp đồng của method return type và khả năng value extractor khác với payload bên trong wrapper. Test đúng kiểu trả về.

**Sai lầm 12 — Khẳng định mọi lỗi trả về chuyển thành 500 dù response đã commit.** Với streaming/async, status có thể đã gửi; cần thiết kế kiểm tra và báo lỗi trước/sau commit phù hợp.

**Sai lầm 13 — Gắn @NotNull vào primitive return và nghĩ có ý nghĩa kiểm tra null.** Kiểu primitive không thể là null; quy tắc như `@Positive`/`@Min` hữu ích hơn nếu cần kiểm tra giá trị số.

**Sai lầm 14 — Dùng validation thay 404 và authorization.** Resource vắng mặt, token hết hạn, quyền không đủ có semantics riêng; không biến mọi tình huống hợp lệ của business flow thành contract violation.

**Sai lầm 15 — Test bean bằng new mà tuyên bố đã kiểm tra MVC.** Test Spring MVC built-in phải gọi qua `MockMvc`/DispatcherServlet; test service AOP phải gọi qua Spring bean proxy. Việc gọi trực tiếp Java method không chứng minh interceptor đã hoạt động.

**Sai lầm 16 — Trả chi tiết constraint nội bộ cho client.** Chẩn đoán nên ở log/metric được bảo vệ; client nhận mã 500 và thông báo chung.

## 12. Checklist khi thiết kế endpoint có return contract

1. Định nghĩa rõ **precondition** và **postcondition**: client phải cung cấp gì, server cam kết trả gì.
2. Đặt constraint input trên DTO/parameters; đặt constraint return phù hợp lên **method** hoặc DTO output.
3. Nếu return là object phải tồn tại và có field hợp lệ, cân nhắc `@NotNull @Valid` trên method; constraint tương ứng nằm trên fields/record components.
4. Với Spring MVC 6.1+, chọn built-in method validation nếu phù hợp; tránh thêm `@Validated` cấp controller class chỉ theo thói quen.
5. Với service, xác minh `MethodValidationPostProcessor`, Spring AOP proxy, self-invocation và default exception type.
6. Phân loại exception/status: `HandlerMethodValidationException.isForReturnValue()` là điểm quan trọng để phân biệt HTTP 500 và 400 trong MVC.
7. Không trả thông báo lỗi chứa dữ liệu nội bộ; cung cấp API error code ổn định, request correlation ID và log an toàn.
8. Đừng dùng return validation thay logic domain/transaction; kiểm tra invariant cần thiết trước khi commit hoặc thực hiện side effect.
9. Nếu dùng `ResponseEntity`, async/streaming hoặc converter tùy chỉnh, test cụ thể thời điểm validation/serialization và khả năng status đã commit.
10. Viết test cho cả 200 (output hợp lệ), 400 (input sai), 500 (output sai), null result và nested result.
11. Khi thêm validation groups, kiểm tra group được chọn đúng ở method return và các nested constraints; Default không tự cộng vào group tùy chỉnh.
12. Theo dõi return contract failures như một loại lỗi phía server, có cảnh báo và quy trình sửa nguyên nhân.

**Kết luận:** Validation không chỉ bảo vệ server khỏi input sai; nó còn giúp server tự kiểm tra **hợp đồng đầu ra**. Trong Spring MVC 6.1+, constraint trên method return có thể dẫn tới `HandlerMethodValidationException` với **HTTP 500** (`isForReturnValue() = true`), khác với lỗi tham số gửi đến thường là **HTTP 400**. Kết hợp `@NotNull`, `@Valid`, DTO output và test qua `MockMvc` giúp phát hiện dữ liệu trả về trái hợp đồng trước khi coi request đã hoàn tất thành công. Nhưng return validation vẫn là một biện pháp phát hiện, không thay thế kiểm soát transaction, business invariants, serialization hoặc xử lý lỗi an toàn.

## Tài liệu tham khảo

- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): argument validation, method validation, return value và controller-level `@Validated`.
- [Spring Framework 6.2 — HandlerMethodValidationException](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html): `getStatusCode()` 400/500 và `isForReturnValue()`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): service AOP, `MethodValidationPostProcessor`, exceptions.
- [Spring Framework — MVC Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): các loại return value MVC, wrapper và async.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): executable validation, return value, cascading, constraints và groups.
