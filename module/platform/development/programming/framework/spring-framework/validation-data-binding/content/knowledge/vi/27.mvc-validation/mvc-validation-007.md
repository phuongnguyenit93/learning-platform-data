# MethodArgumentNotValidException khi kiểm tra đối tượng tham số trong Spring MVC

## 1. Ý nghĩa: dữ liệu đã được bind/đọc nhưng không đạt validation

Khi một HTTP request gửi dữ liệu để tạo hoặc cập nhật đối tượng, Spring MVC phải thực hiện hai việc khác nhau:

1. **Đọc/chuyển dữ liệu** thành Java object: `@ModelAttribute` sử dụng model/data binding; `@RequestBody` và `@RequestPart` có thể sử dụng `HttpMessageConverter` để đọc message/part.
2. **Kiểm tra ràng buộc** nếu có `@Valid` hoặc `@Validated` và một validator phù hợp, ví dụ Jakarta Bean Validation với `@NotBlank`, `@Email`, `@Min`.

Khi Spring MVC kiểm tra **một đối tượng tham số của handler method** và thấy lỗi, trong các điều kiện được giải thích bên dưới, nó ném **`org.springframework.web.bind.MethodArgumentNotValidException`**. Đây không phải là exception của chính annotation `@NotBlank`; nó là exception ở **tầng Spring MVC argument resolution**, mang theo các lỗi của đối tượng tham số đó.

Ví dụ:

~~~java
@PostMapping("/users")
public String create(@Valid @RequestBody UserInput input) {
    return "created";
}
~~~

Đây là **snippet trong controller**, cần khai báo DTO `UserInput` và imports. Nếu JSON parse thành công nhưng `input.name` là chuỗi trống và DTO có `@NotBlank`, Spring có thể ném `MethodArgumentNotValidException` **trước khi thân phương thức `create` chạy**. Với setup MVC thông thường và không có handler lỗi tùy chỉnh, Spring trả **HTTP 400 Bad Request**.

**Điểm then chốt:** `MethodArgumentNotValidException` phản ánh **BindingResult của một method argument**, không có nghĩa "mọi lỗi request đều là lỗi Bean Validation". Chẳng hạn JSON sai cú pháp là lỗi đọc body, còn constraint trực tiếp trên method parameter có thể đi qua cơ chế method validation khác.

## 2. Chính xác khi nào Spring MVC ném exception này?

Trong Spring Framework 6.1+ (bao gồm các phiên bản Spring Boot 3.2+ tương ứng), tài liệu MVC phân biệt hai cơ chế:

- **Individual argument validation:** `@Valid` hoặc `@Validated` được đặt trên **một command object** của `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart`; không có `Errors`/`BindingResult` ngay sau argument và không có cấu hình constraint khác khiến **method validation** phải áp dụng. Khi có lỗi, Spring MVC ném `MethodArgumentNotValidException`.
- **Method validation:** constraint Jakarta Validation được đặt **trực tiếp** trên tham số hoặc return value của handler (ví dụ `@Min(1)` trên `@RequestParam int size`). Cơ chế này bao gồm kiểm tra các đối tượng lồng nhau qua `@Valid` và thường phát sinh **`HandlerMethodValidationException`**, thay vì `MethodArgumentNotValidException`.

| Handler signature (minh họa) | Nếu dữ liệu sai, kết quả điển hình |
| --- | --- |
| `save(@Valid @RequestBody UserInput input)` | `MethodArgumentNotValidException` nếu JSON deserialize thành công rồi Bean Validation thất bại. |
| `save(@Valid @ModelAttribute UserInput input)` | `MethodArgumentNotValidException` nếu binding/validation có lỗi mà không có `BindingResult` ngay sau. |
| `save(@Valid @RequestPart("metadata") UserInput input)` | `MethodArgumentNotValidException` khi part đọc thành object nhưng object vi phạm constraint. |
| `save(@Valid @RequestBody UserInput input, BindingResult result)` | Controller được gọi và nhận lỗi trong `result` khi chỉ có lỗi validation cho tham số đó. |
| `search(@RequestParam @Min(1) int size)` | `HandlerMethodValidationException` khi method validation được kích hoạt. |
| `save(@NotNull @Valid @RequestBody UserInput input)` | Có constraint trực tiếp `@NotNull` nên có thể chuyển sang method validation, không nên mặc định mong đợi `MethodArgumentNotValidException`. |
| `save(@RequestBody UserInput input)` không có `@Valid` | Đọc JSON thành object; Bean Validation **không** tự chạy chỉ vì DTO có constraint. |
| `save(@Valid @RequestBody List<UserInput> input)` | Là container, hành vi validation không thể mặc định suy ra giống một command object; cần kiểm thử theo cấu hình/constraint và phiên bản. |

**`@Valid` tự nó không phải constraint annotation**; nó chỉ báo cần duyệt các ràng buộc của object. Ngược lại, `@NotNull` là constraint và có thể làm method validation trở thành cơ chế xử lý chính. Với controller có class-level `@Validated`, method validation có thể chạy qua AOP proxy; Spring Framework khuyến nghị bỏ annotation cấp class khi muốn sử dụng MVC built-in method validation từ phiên bản 6.1.

### Ba điều kiện cần nhớ

1. Cần có **validator được cấu hình** và annotation kích hoạt việc kiểm tra. Trong Spring Boot, thường dùng `spring-boot-starter-validation`.
2. Lỗi phải xảy ra sau khi Spring **đã có đối tượng tham số hoặc BindingResult tương ứng**. Nếu không đọc được JSON vì sai cú pháp, đó là lỗi converter trước bước validation.
3. Khi đặt `BindingResult` hoặc `Errors` **ngay sau tham số được validate**, Spring có thể chuyển lỗi cho controller xử lý tại chỗ thay vì ném exception riêng cho object đó.

## 3. Bên trong `MethodArgumentNotValidException` có gì?

Trong Spring Framework 6.x, lớp `MethodArgumentNotValidException` kế thừa `BindException` và triển khai `ErrorResponse`. Nó chứa thông tin về tham số handler gặp lỗi và một **`BindingResult`**.

Những API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getParameter()` | `MethodParameter` mô tả tham số handler đã thất bại. |
| `getBindingResult()` | Trả `BindingResult` chứa errors của object được bind/validate. |
| `getFieldErrors()` | Danh sách `FieldError` (kế thừa qua `BindException`/`BindingResult`). |
| `getGlobalErrors()` | Danh sách lỗi ở cấp object (ví dụ constraint class-level). |
| `getAllErrors()` | Gồm cả field errors và object/global errors. |
| `getErrorCount()` | Tổng số object/field errors trong `BindingResult`. |
| `getStatusCode()` | HTTP status theo `ErrorResponse`, đối với exception này là **400 Bad Request**. |
| `getBody()` | `ProblemDetail` đại diện cho lỗi theo Spring `ErrorResponse`; response thực tế vẫn tùy cấu hình/handler. |

`FieldError` thường cho biết:

- `getField()`: tên property (ví dụ `name`, `age`, `address.city`).
- `getCode()`: một mã lỗi cụ thể được giải quyết theo thứ tự mã (`NotBlank`, `Min`, `typeMismatch`, v.v.).
- `getDefaultMessage()`: thông báo đã nội suy, có thể được quốc tế hóa.
- `getRejectedValue()`: giá trị gây lỗi nếu có; **không đưa thẳng giá trị này vào API response hoặc log**, vì có thể là password, token hay dữ liệu cá nhân.
- `getObjectName()`: tên object được bind, hữu ích khi cùng controller nhận nhiều object.

`ObjectError` (lỗi object-level) có thể không gắn với một property đơn. Ví dụ class-level validator kiểm tra hai trường ngày tháng sẽ tạo object error nếu không chủ động thêm property node.

### Ví dụ đọc lỗi một cách có cấu trúc

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<?> onInvalid(MethodArgumentNotValidException ex) {
    BindingResult result = ex.getBindingResult();

    for (FieldError field : result.getFieldErrors()) {
        System.out.println(field.getField() + ": "
                + field.getCode());
    }

    for (ObjectError error : result.getGlobalErrors()) {
        System.out.println("object: " + error.getCode());
    }

    return ResponseEntity.badRequest().build();
}
~~~

Đây là **snippet cho controller/advice**, không phải class hoàn chỉnh. Cần import `BindingResult`, `FieldError`, `ObjectError`, `ResponseEntity`, `ExceptionHandler`. Ví dụ chỉ nhằm mô tả API; trong production nên dùng logger có lọc thông tin nhạy cảm thay vì `System.out`.

**Không giả định** thứ tự của `getFieldErrors()` là thứ tự ổn định để làm contract API. Nếu cần JSON lỗi có thứ tự cố định, hãy sort theo field hoặc theo một tiêu chí đã định nghĩa.

## 4. Binding error và validation error cùng xuất hiện thế nào?

`MethodArgumentNotValidException` mang `BindingResult` nên có thể có hai loại lỗi:

1. **Binding/conversion error:** HTTP parameter `age=abc` không chuyển được sang `Integer` khi dùng `@ModelAttribute`, dẫn đến `FieldError` với mã liên quan `typeMismatch`. Nếu controller không có `BindingResult` liền kề, framework có thể ném `MethodArgumentNotValidException`.
2. **Constraint violation:** input đã thành Java object nhưng không đạt `@NotBlank`, `@Email`, `@Min`, v.v. Spring tích hợp kết quả của Jakarta Bean Validation vào `BindingResult`.

Ví dụ DTO:

~~~java
public class UserInput {
    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    // getters/setters...
}
~~~

Đây là **đoạn mô tả class chưa đủ getters/setters**; bản biên dịch đầy đủ ở phần 6.

Với form request `age=abc`, binder có thể tạo `typeMismatch`. Với JSON `{"age":"abc"}`, Jackson có thể thất bại ngay khi deserialize và Spring ném `HttpMessageNotReadableException` thay vì tạo một `FieldError` cùng loại. Cùng "sai kiểu" trong mắt người dùng nhưng **bước thất bại khác nhau**.

Một input có thể có nhiều errors trên cùng field (ví dụ nhiều constraint đồng thời vi phạm). Không tự giới hạn "một field chỉ có một lỗi" nếu API mong muốn hiển thị đầy đủ constraint messages. Nếu chỉ trả field name một lần, cần công khai đó là contract tóm lược.

## 5. Vai trò của `BindingResult` ngay sau method argument

So sánh hai handler sau.

**Không có `BindingResult`:**

~~~java
@PostMapping("/users")
public String create(@Valid @RequestBody UserInput input) {
    // Khi validation fail, thường không đi vào đây.
    return "ok";
}
~~~

**Có `BindingResult` ngay sau:**

~~~java
@PostMapping("/users/local")
public ResponseEntity<?> createLocally(
        @Valid @RequestBody UserInput input,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Dữ liệu không hợp lệ");
    }

    return ResponseEntity.ok("ok");
}
~~~

Hai snippet này thuộc những handler khác nhau, không phải cùng một mapping. Ở biến thể thứ hai, lỗi Bean Validation của `input` được đưa vào `result` và controller tự xử lý. Thứ tự tham số là thiết yếu:

~~~java
// Đúng: BindingResult ngay sau object được kiểm tra.
void save(@Valid @ModelAttribute UserInput form,
          BindingResult result) {}

// Sai về ý định: parameter không liên quan chen vào giữa.
void save(@Valid @ModelAttribute UserInput form,
          @RequestParam String source,
          BindingResult result) {}
~~~

Snippet thứ hai cần imports và có thể gây lỗi về cách Spring xác định BindingResult. **Luôn khai báo `BindingResult`/`Errors` liền kề đúng object tương ứng**.

Trường hợp `@RequestBody` **không parse được JSON** hoặc body bắt buộc bị thiếu không thể được "chuyển" thành một `BindingResult` cho object đã deserialize, vì object đó chưa được tạo. Ngoài ra, nếu method validation đang áp dụng và có lỗi ở tham số khác không có `Errors` liền kề, `HandlerMethodValidationException` vẫn có thể xảy ra.

### `@ModelAttribute` và dữ liệu form

Ví dụ:

~~~java
@PostMapping(path = "/users/form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<?> submit(
        @Valid @ModelAttribute UserInput input) {
    return ResponseEntity.ok().build();
}
~~~

Servlet request parameters từ form được Spring binding vào `UserInput`. Nếu `age=not-a-number`, `BindingResult` ghi field error và MVC có thể ném `MethodArgumentNotValidException`. Nếu thêm `BindingResult result` ngay sau `input`, controller có thể trả lại view/form hoặc trả 400 JSON theo thiết kế.

Không áp dụng logic này cho JSON như một quá trình `ServletRequestDataBinder`: `@RequestBody` dùng `HttpMessageConverter`.

## 6. Ví dụ chạy được: Spring Boot 3.2+, Java 17 và REST API lỗi rõ ràng

Ví dụ chọn Spring Boot **3.2+** với Spring Framework **6.1+**, dùng Java 17+, Maven và namespace `jakarta.validation.*`. Các phiên bản tương thích khác cũng có thể dùng, nhưng hãy giữ dependencies theo một bản Spring Boot BOM thống nhất.

### 6.1. Dependency Maven

Trong dự án Maven Spring Boot với `spring-boot-starter-parent` hoặc dependency management tương ứng, cần:

~~~xml
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
~~~

Web starter cung cấp Spring MVC và JSON converter; validation starter cung cấp Bean Validation provider; test starter cung cấp JUnit 5 và MockMvc test support.

Tạo bốn file chính dưới `src/main/java/com/example/mvcvalidation/` và một file kiểm thử ở `src/test/java/com/example/mvcvalidation/`.

### 6.2. `ValidationMvcApplication.java`

~~~java
package com.example.mvcvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationMvcApplication.class, args);
    }
}
~~~

### 6.3. `UserInput.java`: DTO có ba constraint

~~~java
package com.example.mvcvalidation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class UserInput {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public UserInput() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

- `@NotBlank` bảo đảm tên/email có nội dung sau khi trim theo logic của constraint.
- `@Email` kiểm tra định dạng email theo provider, không thay thế xác minh quyền sở hữu địa chỉ.
- `@NotNull` kiểm tra `age` không null, `@Min(18)` kiểm tra tuổi tối thiểu.
- DTO chỉ nhận ba thuộc tính cần thiết. Không dùng trực tiếp entity có `role`, `isAdmin`, `balance` để giảm rủi ro mass assignment.

### 6.4. `UserController.java`: JSON, form và xử lý lỗi tại chỗ

~~~java
package com.example.mvcvalidation;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createJson(
            @Valid @RequestBody UserInput input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "created"));
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, String>> createForm(
            @Valid @ModelAttribute UserInput input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "created"));
    }

    @PostMapping(
            path = "/local",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createLocally(
            @Valid @RequestBody UserInput input,
            BindingResult result) {

        if (result.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "handled-locally"));
        }

        return ResponseEntity.ok(
                Map.of("status", "accepted"));
    }
}
~~~

**Vì sao controller có hai đường lỗi?**

- `/json` và `/form` **không có `BindingResult`** trong signature. Lỗi individual object validation được ném dưới dạng `MethodArgumentNotValidException` và sẽ được xử lý bởi advice bên dưới.
- `/local` có `BindingResult` ngay sau `@Valid @RequestBody UserInput`. Nếu JSON deserialize thành công nhưng constraint thất bại, Spring truyền errors vào controller; advice **không** xử lý trường hợp này.
- Nếu request gửi JSON sai cú pháp tới `/local`, controller vẫn có thể không được gọi vì converter thất bại trước validation.

### 6.5. `ValidationErrorAdvice.java`: trả lỗi có cấu trúc

~~~java
package com.example.mvcvalidation;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;
import java.util.Map;

@RestControllerAdvice
public class ValidationErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> onInvalidArgument(
            MethodArgumentNotValidException ex) {

        // Ví dụ API tối giản: chỉ xuất tên field, không echo dữ liệu.
        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        Map<String, Object> body = Map.of(
                "error", "VALIDATION_FAILED",
                "fields", fields
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Chú ý đây là **response schema minh họa do ứng dụng chủ động chọn**, không phải JSON mặc định của Spring:

~~~json
{
  "error": "VALIDATION_FAILED",
  "fields": ["age", "email", "name"]
}
~~~

Với input vi phạm cả ba constraint, response này trả ba tên field đã được **loại trùng và sắp xếp** theo alphabet. Code cố ý không dùng `FieldError#getRejectedValue()` để tránh lộ dữ liệu nhạy cảm. Trong ứng dụng thực tế, có thể bổ sung mã lỗi có ý nghĩa và thông báo i18n với chính sách redaction phù hợp. Để xử lý class-level errors, nên thêm `getGlobalErrors()` vào response schema; ví dụ hiện tại chỉ có các constraint ở field.

### 6.6. `ValidationMvcApplicationTest.java`: 7 bài kiểm thử MockMvc

Tạo file `src/test/java/com/example/mvcvalidation/ValidationMvcApplicationTest.java`:

~~~java
package com.example.mvcvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationMvcApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validJsonReachesController() throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Lan","email":"lan@example.com","age":22}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"));
    }

    @Test
    void invalidJsonObjectIsHandledByAdvice() throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","email":"wrong","age":16}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0]").value("age"))
                .andExpect(jsonPath("$.fields[1]").value("email"))
                .andExpect(jsonPath("$.fields[2]").value("name"));
    }

    @Test
    void invalidFormObjectIsHandledByAdvice() throws Exception {
        mvc.perform(post("/api/users/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("email", "lan@example.com")
                    .param("age", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0]").value("age"));
    }

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/api/users/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("email", "lan@example.com")
                    .param("age", "22"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"));
    }

    @Test
    void localBindingResultSuppressesTheGlobalHandler()
            throws Exception {
        mvc.perform(post("/api/users/local")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","email":"wrong","age":16}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status")
                        .value("handled-locally"));
    }

    @Test
    void malformedJsonFailsBeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredBodyFailsBeforeController()
            throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy từ root của dự án đã cấu hình Maven wrapper:

~~~bash
./mvnw test -Dtest=ValidationMvcApplicationTest
~~~

Trên Windows dùng `mvnw.cmd test -Dtest=ValidationMvcApplicationTest`; nếu Maven được cài toàn cục, dùng `mvn test -Dtest=ValidationMvcApplicationTest`.

Với các starter và cấu hình mặc định như trên, **7 test dự kiến pass**. Các status/response do code kiểm soát:

| Trường hợp | HTTP status | Response body chính |
| --- | --- | --- |
| JSON hợp lệ | 201 | `{"status":"created"}` |
| JSON hợp cú pháp nhưng sai ba field | 400 | `{"error":"VALIDATION_FAILED","fields":["age","email","name"]}` |
| Form `age=abc` | 400 | `error=VALIDATION_FAILED`, `fields=["age"]` |
| Form hợp lệ | 201 | `{"status":"created"}` |
| JSON sai field và có `BindingResult` | 400 | `{"status":"handled-locally"}` |
| JSON sai cú pháp | 400 | Lỗi framework trước khi controller xử lý, schema mặc định tùy cấu hình. |
| Thiếu body bắt buộc | 400 | Lỗi framework trước khi controller xử lý, schema mặc định tùy cấu hình. |

**Giới hạn lời khẳng định:** bài kiểm thử được thiết kế theo Spring Boot 3.2+ và Spring MVC 6.1+; Maven test suite không phải bằng chứng cho mọi phiên bản hay mọi cấu hình của ứng dụng. Nếu thêm Spring Security, custom `@ControllerAdvice` hoặc thay MessageConverter/Validator, kết quả tích hợp có thể đổi và cần điều chỉnh test. Test so sánh field names do ứng dụng sort; không so sánh thông báo mặc định của provider vì có thể thay đổi theo locale.

### 6.7. Gửi request thật bằng curl

Khi ứng dụng đang chạy với `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/api/users/json" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"wrong","age":16}'

curl -i -X POST "http://localhost:8080/api/users/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan&email=lan@example.com&age=abc"

curl -i -X POST "http://localhost:8080/api/users/local" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"wrong","age":16}'
~~~

Đây là cú pháp shell Unix; PowerShell có thể sử dụng `curl.exe` với cách quoting/continuation thích hợp. Ba request lần lượt đi qua `@RequestBody`, `@ModelAttribute` và handler tự xử lý `BindingResult`. Trong ví dụ, cả ba trả HTTP 400, nhưng **cách phát sinh và xử lý lỗi khác nhau**.

## 7. Xử lý lỗi với `ResponseEntityExceptionHandler` hoặc `@RestControllerAdvice`

Có hai cách thông dụng để chuẩn hóa lỗi:

### Cách A — `@RestControllerAdvice` với `@ExceptionHandler`

Đó là cách đã chạy ở phần 6. Nó nhận `MethodArgumentNotValidException` và trả response cụ thể của ứng dụng. Ưu điểm: rõ ràng, ngắn, không cần override các handler mặc định khác.

### Cách B — Kế thừa `ResponseEntityExceptionHandler`

Nếu ứng dụng muốn xử lý thống nhất nhiều loại Spring MVC exception/`ProblemDetail`, có thể tạo một `@ControllerAdvice` kế thừa `ResponseEntityExceptionHandler`. Ví dụ sau là **class thay thế** cho `ValidationErrorAdvice` trong demo, **không đăng ký song song hai handler cho cùng exception**:

~~~java
package com.example.mvcvalidation;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

import java.util.Map;

@ControllerAdvice
public class CommonMvcErrorHandler
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Object body = Map.of(
                "error", "VALIDATION_FAILED",
                "errorCount", ex.getBindingResult().getErrorCount()
        );

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
~~~

Trong code thực tế, import `ResponseEntityExceptionHandler` nên được viết trên **một dòng duy nhất** (ở đây xuống dòng trong mẫu để trình bày); dạng đầy đủ:

~~~java
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
~~~

**Lưu ý:** trong ví dụ class ở trên, nếu tự thêm dòng import chuẩn, hãy **thay thế hai dòng import bị ngắt** bằng dòng import đầy đủ rồi compile. Mẫu này chỉ minh họa cách override handler. Dự án ở phần 6 đã có implementation chạy được nên không cần thêm handler thay thế này để chạy test.

Với Spring Framework 6.x, signature protected override bao gồm `MethodArgumentNotValidException`, `HttpHeaders`, `HttpStatusCode` và `WebRequest`. Những phiên bản khác có thể đổi API; đọc Javadoc của đúng Spring version trong dự án. Không đồng thời khai báo `@ExceptionHandler(MethodArgumentNotValidException.class)` trong một subclass mà base class đã xử lý cùng exception qua handler nội bộ, vì dễ gây mapping ambiguity.

### `ProblemDetail` và `ErrorResponse`

Từ Spring Framework 6, `MethodArgumentNotValidException` là một `ErrorResponse`, có `getStatusCode()` và `getBody()` kiểu `ProblemDetail`. Framework có khả năng hiển thị response lỗi theo dạng RFC 9457/problem details tùy configuration. Đừng khẳng định payload HTTP mặc định luôn là một JSON cố định: Spring Boot, `@ControllerAdvice`, content negotiation, các option problem details và version có thể ảnh hưởng body.

Nếu ứng dụng public REST API, hãy **chọn một contract lỗi có version/stability rõ ràng**. Ví dụ `{error, fields}` ở phần 6 cố ý là một schema tối giản, dễ test; production có thể bổ sung mã constraint, thông báo, trace ID, URI và global errors mà không đưa raw rejected input lên client.

## 8. Phân biệt những exception gần nhau

| Exception/kết quả | Xảy ra khi nào? | Hướng xử lý |
| --- | --- | --- |
| **`MethodArgumentNotValidException`** | Spring MVC individual argument binding/validation thất bại và không được `BindingResult` liền kề xử lý. | Lấy `BindingResult`, chuyển thành HTTP 400/field errors có cấu trúc. |
| **`HandlerMethodValidationException`** | Spring MVC built-in method validation kiểm tra constraints trực tiếp trên method parameters/return value và phát hiện lỗi. | Xử lý danh sách parameter validation results; errors đầu vào thường là 400, lỗi return value thường là 500. |
| **`HttpMessageNotReadableException`** | `@RequestBody`/`@RequestPart` không đọc/deserialze được HTTP message; ví dụ JSON sai cú pháp hoặc body cần thiết bị thiếu. | Trả 400 phù hợp, không nhầm thành lỗi @NotBlank đã chạy. |
| **`HttpMediaTypeNotSupportedException`** | Content-Type/`consumes` hoặc converter không hỗ trợ request body. | Phản hồi 415 Unsupported Media Type, hướng dẫn client gửi đúng format. |
| **`ConstraintViolationException`** | Một tầng tích hợp/executable validation có thể ném khi mang `Set<ConstraintViolation>`; không phải kết quả mặc định của `Validator#validate`. | Xác định layer, constraints và HTTP policy; không tự đồng nhất với MethodArgumentNotValidException. |
| **`BindException`** | Spring binding/validation exception tổng quát; `MethodArgumentNotValidException` kế thừa nó trong Spring 6.x. | Kiểm tra subclass và `BindingResult`, tránh handler quá rộng làm che lỗi. |
| **`ValidationException`** của Jakarta | Cấu hình provider/custom constraint/nhóm kiểm tra sai hoặc lỗi thực thi bất thường. | Điều tra code/hạ tầng, không mặc định đổ lỗi cho client. |

**Đặc biệt với `HandlerMethodValidationException`:** Spring MVC 6.1+ có cơ chế built-in. Ví dụ:

~~~java
@GetMapping("/page")
public String page(@RequestParam @Min(1) int size) {
    return "size=" + size;
}
~~~

Đây là snippet với import `@RequestParam`, `@Min`, `@GetMapping`; nếu `size=0`, method validation có thể phát sinh `HandlerMethodValidationException`. Nếu controller dùng class-level `@Validated` qua AOP thì exception pipeline có thể khác; nên cấu hình và test rõ ràng.

Khi muốn xử lý cả hai kiểu trong `@ControllerAdvice`, cần **hai nhánh phù hợp với cấu trúc dữ liệu từng exception**: `MethodArgumentNotValidException#getBindingResult()` mô tả một object; `HandlerMethodValidationException#getParameterValidationResults()` mô tả lỗi theo các method parameters.

## 9. Quốc tế hóa (i18n), lỗi object-level và tính an toàn của response

### 9.1. Mã lỗi và message

Jakarta Validation tạo `ConstraintViolation`; Spring chuyển chúng thành `FieldError` hoặc `ObjectError` trong `BindingResult`. `MessageCodesResolver` có thể cung cấp nhiều mã ưu tiên, ví dụ:

~~~text
NotBlank.userInput.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

Đây là **ví dụ minh họa** về ý tưởng mã theo object/field/type; tên object và danh sách mã cụ thể phụ thuộc binding context. Không hardcode vào API public nếu chưa thống nhất.

Với Bean Validation, có thể khai báo:

~~~java
@NotBlank(message = "{user.name.required}")
private String name;
~~~

Và `src/main/resources/ValidationMessages.properties`:

~~~properties
user.name.required=Name is required
~~~

`src/main/resources/ValidationMessages_vi.properties`:

~~~properties
user.name.required=Vui lòng nhập tên
~~~

Đây là **snippets tùy chọn**; khi áp dụng phải thay annotation field trong DTO ví dụ và cấu hình locale/message interpolation phù hợp. Đừng giả định lỗi luôn ra tiếng Việt chỉ vì máy chủ chạy ở Việt Nam. Có thể dùng Spring `MessageSource` và `Locale` từ request để nội suy/localize message theo cấu hình.

### 9.2. Lỗi class-level

Constraint đặt trên class (ví dụ yêu cầu `startDate <= endDate`) có thể tạo **object-level violation** và chuyển thành `ObjectError`. Một handler chỉ lấy `getFieldErrors()` sẽ **bỏ sót** lỗi này; nếu contract cần liệt kê mọi lỗi, hãy đọc cả `getGlobalErrors()` hoặc `getAllErrors()`.

Trường hợp custom constraint dùng `ConstraintValidatorContext#addPropertyNode("endDate")` có thể chuyển lỗi class-level sang field cụ thể. Cách bố trí path là quyết định của tác giả custom validator, không phải `MethodArgumentNotValidException` tự đoán.

### 9.3. Không phơi dữ liệu nhạy cảm

`FieldError#getRejectedValue()` rất tiện cho việc giữ lại form input, nhưng có thể chứa PII/secrets. Với REST API, **tránh đưa raw rejectedValue, target object hoặc full stack trace vào JSON lỗi**. Chỉ xuất field name, mã lỗi và message đã kiểm soát. Mọi endpoint nhận input từ client vẫn cần authorization, chống mass assignment, size limits và bảo vệ dữ liệu.

Nếu log:

~~~java
logger.warn("Invalid request: fields={}",
        ex.getBindingResult().getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .toList());
~~~

Đây là **snippet trong handler có logger phù hợp**, không phải chương trình độc lập. Cách này tránh log giá trị của field; muốn liên hệ lỗi với request thì có thể thêm request ID được quản lý an toàn.

## 10. Những lỗi thường gặp và cách sửa

1. **Chỉ thêm constraint trên DTO mà quên `@Valid`.** Spring đọc JSON được nhưng Bean Validation không chạy. Sửa bằng `@Valid` hoặc `@Validated` trên đúng parameter và cấu hình validator.
2. **Thiếu `spring-boot-starter-validation`.** Không có provider hoạt động thì những kỳ vọng về constraint có thể không được đáp ứng. Bảo đảm dependency Jakarta Validation và Hibernate Validator đồng bộ với Spring Boot BOM.
3. **Nghĩ JSON sai cú pháp là `MethodArgumentNotValidException`.** Converter chưa tạo được object, thường là `HttpMessageNotReadableException`.
4. **Đặt `BindingResult` không ngay sau object tương ứng.** Spring có thể không liên kết đúng errors, hoặc ném lỗi signature. Sửa thứ tự argument.
5. **Bắt mọi lỗi MVC bằng một handler `Exception.class` trả 400.** Có thể che lỗi server, làm mất phân biệt parser, Bean Validation, method validation và cấu hình.
6. **Dựa vào thứ tự của `FieldError`.** Không chọn ngẫu nhiên "lỗi đầu" làm API contract trừ khi chủ đích. Sort/gộp lỗi có quy tắc.
7. **Chỉ đọc `getFieldErrors()` nhưng cần báo lỗi cross-field.** Thêm `getGlobalErrors()`/`getAllErrors()`.
8. **Dùng `@Valid` trên container rồi giả định chắc chắn giống DTO command object.** Cần hiểu cơ chế method validation/element constraints và kiểm thử phiên bản thực tế.
9. **Trộn `@Validated` ở class controller với MVC built-in method validation mà không hiểu proxy.** Trên Spring Framework 6.1+, cân nhắc bỏ class-level `@Validated` khi muốn cơ chế mới, kiểm thử với trực tiếp `@Min`/`@NotBlank`.
10. **Echo rejected values vào response.** Có thể lộ password, token, dữ liệu cá nhân; không trả thẳng rejectedValue/exception trace.
11. **Nhầm `@ModelAttribute` với `@RequestBody`.** Form/query binding và JSON message conversion có lỗi chuyển kiểu khác nhau; chọn annotation theo input contract.
12. **Nhầm validation với authorization.** Dữ liệu hợp lệ về `@NotNull` vẫn có thể là cập nhật property người dùng không có quyền sửa.

## 11. Checklist trước khi release

- [ ] DTO chỉ gồm những input thực sự cho phép nhận, có constraint rõ ràng.
- [ ] Annotation `@Valid`/`@Validated` đặt trên argument cần validate; dependency validator hoạt động.
- [ ] Phân biệt `@ModelAttribute`, `@RequestBody`, `@RequestPart` và các bước đọc/chuyển dữ liệu.
- [ ] Nếu muốn lỗi được ném cho advice, **không đặt `BindingResult` liền kề**; nếu muốn xử lý trong controller, đặt đúng vị trí và kiểm tra `hasErrors()`.
- [ ] Có chính sách riêng cho `MethodArgumentNotValidException`, `HandlerMethodValidationException`, lỗi đọc JSON và media type.
- [ ] Handler có xử lý cả field-level và object-level errors nếu schema API cần.
- [ ] Response ổn định, không lộ rejected values, stack trace hay nội dung server-only.
- [ ] MockMvc test bao gồm JSON hợp lệ, constraint failure, form typeMismatch, local BindingResult, JSON malformed/missing body.
- [ ] Kiểm tra locale, mã lỗi, status HTTP và phiên bản Spring dùng trong dự án.
- [ ] Không hardcode wording của Hibernate Validator/Spring vào test contract nếu không kiểm soát message source.

**Ghi nhớ:** `MethodArgumentNotValidException` là cách Spring MVC báo rằng **một object argument được bind/deserialze rồi kiểm tra nhưng có lỗi mà không được xử lý cục bộ**. Từ exception này, lấy `BindingResult` để xây phản hồi HTTP 400 có cấu trúc. Nếu lỗi phát sinh ở bước đọc HTTP body hoặc ở method validation cấp method, cần xử lý **đúng cơ chế exception khác**, không gom tất cả vào một lớp.

## Tài liệu tham khảo

- Spring Framework Reference — **Spring MVC Validation** và phân biệt `MethodArgumentNotValidException`/`HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework Reference — **`@RequestBody` và validation**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework Reference — **`@ModelAttribute` argument**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Javadoc 6.2 — **`MethodArgumentNotValidException`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html
- Spring Framework Javadoc 6.2 — **`ResponseEntityExceptionHandler`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework Reference — **Error Responses và ProblemDetail**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
