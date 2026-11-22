# Phân biệt dữ liệu JSON sai cú pháp với dữ liệu vi phạm constraint trong Spring MVC

## 1. Hai loại lỗi “400 Bad Request” nhưng xảy ra ở hai tầng khác nhau

Khi một REST controller nhận JSON qua `@RequestBody`, có ít nhất **hai câu hỏi độc lập**:

1. **Có đọc được request body và tạo được Java object không?** Đây là công việc của HTTP message converter (thường dùng Jackson). Một dấu phẩy sai chỗ, JSON bị cắt ngang hoặc kiểu dữ liệu không chuyển đổi được có thể khiến bước này thất bại.
2. **Object đã tạo có hợp lệ theo quy tắc nghiệp vụ/constraint không?** Đây là công việc của Jakarta Bean Validation qua `@Valid`/`@Validated`, chẳng hạn `@NotBlank`, `@NotNull`, `@Size`, `@Email`, `@Min`.

Hai loại lỗi thường cùng trả HTTP **400**, nhưng **không phải cùng exception** và **không nên trả cùng error code mơ hồ**. Với Spring MVC 6.x:

- Đọc/chuyển JSON thất bại: thường là `HttpMessageNotReadableException`. Nguyên nhân bên dưới có thể là `JsonParseException` (sai cú pháp), `InvalidFormatException` / `MismatchedInputException` (không ánh xạ được vào kiểu Java).
- Object đọc được nhưng vi phạm constraint của một `@Valid @RequestBody` command object: thông thường là `MethodArgumentNotValidException`.
- Nếu Spring MVC áp dụng **method validation** (ví dụ một controller method có constraint trực tiếp trên tham số khác), từ Spring Framework 6.1 có thể là `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException`.

Bài này tập trung vào REST JSON trên **Spring MVC / Servlet stack**, không mặc nhiên áp dụng exception class y hệt cho Spring WebFlux. Ví dụ dùng Java 17, Spring Boot 3.x, Spring Framework 6.x và package `jakarta.validation.*`.

## 2. Pipeline xử lý `@RequestBody`

Đường đi điển hình của một request POST:

```text
HTTP POST /users
Content-Type: application/json
        |
        v
DispatcherServlet + HandlerMapping
        |
        v
Chọn controller method / argument resolver
        |
        v
HttpMessageConverter (thường MappingJackson2HttpMessageConverter)
        |
        +---- JSON không parse được?
        |         |
        |         +--> HttpMessageNotReadableException
        |                    |
        |                    +--> HTTP 400; controller chưa chạy
        |
        +---- JSON parse được nhưng không map được thành DTO?
        |         |
        |         +--> HttpMessageNotReadableException
        |                    |
        |                    +--> HTTP 400; controller chưa chạy
        |
        v
Java DTO đã được tạo
        |
        +---- @Valid / @Validated và Validator phù hợp?
        |         |
        |         +--> Kiểm tra Jakarta Validation constraints
        |                    |
        |                    +--> Lỗi? MethodArgumentNotValidException
        |                               hoặc HandlerMethodValidationException
        |                               tùy chữ ký method
        |
        v
Controller method được gọi
        |
        v
Nghiệp vụ / persistence / response
```

**Quy tắc cốt lõi:** nếu Jackson không tạo được đối số method, Spring chưa có object để chạy Bean Validation cho đối số đó. Vì vậy payload `{"age":"abc"}` với field Java kiểu `Integer` **không phải vi phạm `@Min`**; nó là lỗi chuyển đổi JSON→Java trước khi `@Min` có cơ hội kiểm tra.

Ngược lại, `{"age":15}` là JSON hợp lệ và chuyển được thành `Integer(15)`. Khi field có `@Min(18)`, đây mới là **constraint violation**.

## 3. Bốn khái niệm phải tách riêng

| Nhóm | Ví dụ | Thời điểm phát hiện | Exception điển hình | HTTP mặc định |
| --- | --- | --- | --- | --- |
| **Lỗi cú pháp JSON** | `{"name":, "age":20}`, dấu ngoặc thiếu | JSON parser | `HttpMessageNotReadableException`, cause có thể là Jackson `JsonParseException` | 400 |
| **Lỗi ánh xạ / deserialization** | `{"age":"abc"}` với `Integer age`; array thay vì object | Jackson mapping / converter | `HttpMessageNotReadableException`, cause có thể là `InvalidFormatException`, `MismatchedInputException` | 400 |
| **Constraint violation** | `{"name":"","age":15}` với `@NotBlank` và `@Min(18)` | Jakarta Bean Validation sau khi DTO được tạo | `MethodArgumentNotValidException` với DTO `@Valid @RequestBody` thông thường | 400 |
| **Method validation** | `@Min(1) @RequestParam int page` ở controller | Spring MVC built-in method validation (6.1+) | `HandlerMethodValidationException` | 400 |

Một lỗi “JSON hợp lệ” **không đồng nghĩa** với “payload hợp lệ theo mọi nghĩa”. JSON parser chỉ xét cấu trúc ngôn ngữ JSON; Jackson còn xét kiểu Java và cấu hình deserialization; Bean Validation xét constraint trên dữ liệu đã được gắn.

### 3.1. Lỗi cú pháp JSON

JSON phải có đúng dấu ngoặc, dấu hai chấm, dấu phẩy và ký tự escape. Ví dụ sai:

```json
{"name": "Lan", "age": }
```

Không có giá trị sau `age:`. Jackson không thể đọc JSON token hợp lệ, thường ném một exception phân tích cú pháp được Spring bọc trong `HttpMessageNotReadableException`. Không có `CreateUserRequest` hoàn chỉnh để validate và controller method không chạy.

Một ví dụ khác:

```text
{"name": "Lan", "age": 20
```

Đây là **chuỗi request body không hợp lệ**, nên trình bày dưới dạng `text` chứ không gắn nhãn `json` cho code fence trong tài liệu. Nó thiếu dấu `}` kết thúc object.

### 3.2. JSON đúng cú pháp nhưng không đọc được theo DTO

```json
{"name": "Lan", "age": "không-phải-số"}
```

Đây là JSON hợp lệ. Nhưng nếu `age` là `Integer`, Jackson mặc định không chuyển chuỗi trên thành số nguyên được. Lỗi thường là `HttpMessageNotReadableException`, với cause phù hợp như `InvalidFormatException`.

Một số kiểu khác cũng có thể phát sinh lỗi deserialization, tùy cấu hình Jackson: enum có giá trị không hỗ trợ, kiểu ngày giờ không hợp lệ, cấu trúc object/array sai, constructor không thể tạo instance, polymorphic type không hợp lệ...

**Không khẳng định mọi mismatch đều ném lỗi**. Jackson có tính năng coercion; ví dụ một số chuỗi số có thể được chấp nhận để chuyển sang số nguyên, hoặc unknown property có thể bị bỏ qua theo cấu hình. Khi cần kiểu đầu vào nghiêm ngặt, phải cấu hình Jackson cụ thể và test payload thực tế.

### 3.3. JSON đọc được nhưng vi phạm constraint

```json
{"name": "", "age": 15}
```

Nếu DTO quy định `name` không trống và `age >= 18`, Jackson tạo object thành công, rồi Bean Validation phát hiện hai vi phạm. Với `@Valid @RequestBody` đơn giản, Spring MVC thường phát ra `MethodArgumentNotValidException` và HTTP 400. **Controller method không chạy** nếu exception không được xử lý theo nhánh khác.

### 3.4. Dữ liệu hợp lệ

```json
{"name": "Lan", "age": 22}
```

Đây là JSON đúng cú pháp, ánh xạ đúng kiểu, thỏa mãn các constraint của DTO minh họa; controller method được gọi.

## 4. Ví dụ Java 17 chạy được: Spring Boot MVC + Jackson + Jakarta Validation

Ta tạo một endpoint `POST /users` với một DTO hai field:

- `name`: bắt buộc là chuỗi không blank.
- `age`: bắt buộc có giá trị và phải lớn hơn hoặc bằng 18.

Bài sẽ dùng một `@RestControllerAdvice` để trả **hai mã lỗi khác nhau**:

- `REQUEST_BODY_UNREADABLE` cho bước đọc request body thất bại.
- `CONSTRAINT_VIOLATION` cho dữ liệu đã deserialize nhưng vi phạm constraint.

Các lỗi syntax và lỗi chuyển kiểu cùng thuộc nhóm unreadable, **nhưng vẫn có thể phân loại sâu hơn theo cause nếu API thực sự cần**, với điều kiện không lộ chi tiết hệ thống.

### 4.1. Cấu trúc thư mục

```text
json-vs-validation/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── JsonVsValidationApplication.java
    │   ├── CreateUserRequest.java
    │   ├── UsersController.java
    │   └── ApiErrorHandler.java
    └── test/java/demo/
        └── UsersControllerTest.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>json-vs-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

`spring-boot-starter-web` mang Spring MVC và Jackson, `spring-boot-starter-validation` cung cấp Jakarta Validation API và một provider như Hibernate Validator. Không có provider phù hợp thì `@Valid` có thể không kích hoạt được validation như ví dụ kỳ vọng; cần kiểm tra dependency thực tế.

### 4.3. `src/main/java/demo/JsonVsValidationApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonVsValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonVsValidationApplication.class, args);
    }
}
```

### 4.4. `src/main/java/demo/CreateUserRequest.java`

```java
package demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateUserRequest(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

Tại sao dùng `Integer` thay vì `int`? Nếu không gửi `age`, field `Integer` có thể là `null` để `@NotNull` phát hiện chính xác lỗi thiếu giá trị. Nếu dùng primitive `int`, một số con đường deserialization có thể tạo mặc định 0; test lúc đó dễ nhầm “missing” với “age dưới 18”.

Với `name`, `@NotBlank` kiểm tra cả `null`, chuỗi rỗng và chuỗi toàn khoảng trắng. `@Min(18)` kiểm tra giá trị số đã đọc được, **không kiểm tra cú pháp hay ép kiểu JSON**.

### 4.5. `src/main/java/demo/UsersController.java`

```java
package demo;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/users")
public class UsersController {
    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody CreateUserRequest request) {

        // Chỉ thực thi khi JSON đã được deserialize
        // và DTO không vi phạm constraint.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "status", "created",
                        "name", request.name()
                ));
    }
}
```

`@RequestBody` yêu cầu Spring đọc body bằng HTTP message converter; `@Valid` kích hoạt Bean Validation trên DTO sau bước deserialization. Nếu không có `@Valid`/`@Validated` hoặc cơ chế kích hoạt tương đương, annotation trên DTO **không tự ném `MethodArgumentNotValidException`** khi controller được gọi.

### 4.6. `src/main/java/demo/ApiErrorHandler.java`

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Không trả thẳng ex.getMessage() hoặc stack trace cho client.
        Map<String, Object> body = Map.of(
                "code", "REQUEST_BODY_UNREADABLE",
                "message", "JSON body is missing, malformed, or incompatible"
        );

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors().stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .map(field -> Map.of(
                        "field", field.getField(),
                        "message", Objects.toString(
                                field.getDefaultMessage(), "Invalid value")
                ))
                .toList();

        Map<String, Object> body = Map.of(
                "code", "CONSTRAINT_VIOLATION",
                "message", "Request fields violate validation rules",
                "errors", errors
        );

        return new ResponseEntity<>(body, headers, status);
    }
}
```

**Tại sao dùng `ResponseEntityExceptionHandler`?** Trong Spring MVC, framework đã định nghĩa handler cho nhiều exception chuẩn. Kế thừa class này và **override các hook protected** là cách tập trung định dạng lỗi mà không tạo `@ExceptionHandler` trùng lặp cho `HttpMessageNotReadableException` và `MethodArgumentNotValidException`. Không gắn thêm `@ExceptionHandler` lên hai method override trong ví dụ.

`HttpStatusCode status` và `HttpHeaders headers` do Spring truyền vào; ví dụ giữ nguyên mã status (thông thường là 400). Việc đặt mã `REQUEST_BODY_UNREADABLE` giúp client nhận diện lỗi đọc body, còn `CONSTRAINT_VIOLATION` đi kèm danh sách field vi phạm khi có dữ liệu hợp lệ về mặt parse.

**Giới hạn chủ đích của ví dụ:** chỉ xử lý hai exception này. Một controller có constraint trực tiếp trên method parameter có thể cần override thêm `handleHandlerMethodValidationException(...)`; phần 7 trình bày khi nào điều đó xảy ra.

### 4.7. `src/test/java/demo/UsersControllerTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UsersControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void malformedJsonIsNotReadable() throws Exception {
        MvcResult result = mvc.perform(
                        post("/users")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"name\":,\"age\":20}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("REQUEST_BODY_UNREADABLE"))
                .andReturn();

        assertInstanceOf(HttpMessageNotReadableException.class,
                result.getResolvedException());
    }

    @Test
    void wrongTypeIsNotReadable() throws Exception {
        MvcResult result = mvc.perform(
                        post("/users")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"name\":\"Lan\",\"age\":\"abc\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("REQUEST_BODY_UNREADABLE"))
                .andReturn();

        assertInstanceOf(HttpMessageNotReadableException.class,
                result.getResolvedException());
    }

    @Test
    void validJsonButBadFieldsIsConstraintViolation() throws Exception {
        MvcResult result = mvc.perform(
                        post("/users")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"name\":\"\",\"age\":15}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.errors.length()").value(2))
                .andExpect(jsonPath("$.errors[0].field").value("age"))
                .andExpect(jsonPath("$.errors[1].field").value("name"))
                .andReturn();

        assertInstanceOf(MethodArgumentNotValidException.class,
                result.getResolvedException());
    }

    @Test
    void missingAgeIsNotNullViolation() throws Exception {
        mvc.perform(post("/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.errors[0].field").value("age"));
    }

    @Test
    void validRequestReachesController() throws Exception {
        mvc.perform(post("/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\",\"age\":22}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"))
                .andExpect(jsonPath("$.name").value("Lan"));
    }
}
```

Chạy test:

```bash
mvn -q test
```

Với cấu hình trên, **năm test dự kiến đều pass**, lệnh kết thúc exit code 0. Không khẳng định có một mẫu stdout Maven cố định vì định dạng log, bản plugin Surefire và mức log của Spring có thể khác nhau. Test kiểm tra **HTTP status**, **API error code** và **exception class được Spring resolve** thay vì dựa vào stack trace hoặc message Jackson vốn có thể thay đổi theo phiên bản.

Chạy server:

```bash
mvn spring-boot:run
```

Thử bằng `curl` (trên shell POSIX hoặc dùng cú pháp quoting phù hợp với shell của bạn):

```bash
curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  --data '{"name":"Lan","age":22}'

curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  --data '{"name":"","age":15}'

curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  --data '{"name":,"age":20}'
```

HTTP status dự kiến lần lượt là **201**, **400** do constraint, **400** do body unreadable. Ví dụ về ý nghĩa response (trình tự key trong JSON object không được đảm bảo):

```json
{
  "code": "CONSTRAINT_VIOLATION",
  "message": "Request fields violate validation rules",
  "errors": [
    {"field": "age", "message": "must be greater than or equal to 18"},
    {"field": "name", "message": "must not be blank"}
  ]
}
```

Thông điệp field ở trên là **ví dụ theo locale tiếng Anh thông dụng**, không phải một hợp đồng byte-for-byte: resource bundle, cấu hình provider và ngôn ngữ có thể thay đổi wording. Với body unreadable, response có dạng:

```json
{
  "code": "REQUEST_BODY_UNREADABLE",
  "message": "JSON body is missing, malformed, or incompatible"
}
```

Không có `errors` cho các field trong trường hợp Jackson không tạo được DTO. Nếu ứng dụng cần báo rõ vị trí JSON sai, có thể xây API error detail riêng dựa trên cause một cách có kiểm soát, nhưng **không hiển thị raw stack trace hoặc mô tả class nội bộ** cho client.

## 5. Đi sâu vào exception và nguyên nhân gốc

### 5.1. `HttpMessageNotReadableException` không có nghĩa “chỉ sai cú pháp”

Spring ném `HttpMessageNotReadableException` khi không đọc được request body bằng converter phù hợp. Có thể chia thành các nhóm nguyên nhân phổ biến:

| JSON / request | Nguyên nhân thường gặp | Có thể là nested cause |
| --- | --- | --- |
| `{"name":,}` | Token sai cú pháp | `JsonParseException` |
| `{"age":"abc"}` với `Integer age` | Giá trị không chuyển được sang số | `InvalidFormatException` |
| `[]` khi đòi DTO object | JSON shape không tương thích | `MismatchedInputException` |
| JSON string escape bị hỏng | Lỗi parser | `JsonParseException` |
| Body rỗng khi `@RequestBody(required=true)` | Thiếu body bắt buộc | `HttpMessageNotReadableException`, không nhất thiết có Jackson parse cause |
| Custom deserializer từ chối dữ liệu | Lỗi chuyển đổi tùy implementation | Có thể là `JsonMappingException` hoặc exception khác |

Do vậy, tên **`REQUEST_BODY_UNREADABLE`** an toàn hơn `JSON_SYNTAX_ERROR` cho handler chung. Nếu muốn hai code riêng, kiểm tra cause có thuộc `com.fasterxml.jackson.core.JsonParseException` hay không, đồng thời dự phòng cho các lỗi không có cause hoặc cause thay đổi qua converter/version. **Không ép mọi `HttpMessageNotReadableException` thành `JsonParseException`.**

Cũng cần nhớ: không phải mọi request body được đọc bởi Jackson. Spring MVC chọn converter dựa vào kiểu Java, `Content-Type` và danh sách converter có sẵn. Với endpoint JSON được cấu hình thông thường, Jackson là converter tiêu biểu.

### 5.2. `MethodArgumentNotValidException` có gì hữu ích?

Exception này bao gồm `BindingResult`. Với lỗi field của DTO:

- `getFieldErrors()`: danh sách `FieldError` có property path, message, rejected value và metadata constraint/binding liên quan.
- `getGlobalErrors()`: lỗi cấp object/class, ví dụ class-level constraint hoặc validator tạo object error.
- `getAllErrors()`: cả lỗi field lẫn lỗi object.
- Có thể dùng `getFieldError("name")` nếu cần kiểm tra một trường cụ thể.

Không nên giả định **mọi validation error đều gắn một field**. Ví dụ password confirmation hoặc một constraint liên trường có thể tạo **global error**. Handler mẫu chỉ xuất `getFieldErrors()` để giữ ví dụ ngắn; trong ứng dụng thật cần xem xét cả `getGlobalErrors()`. Với dữ liệu lỗi phức tạp, xuất một schema ổn định gồm field error, object error, error code và correlation id phù hợp.

**Rejected value** có thể chứa email, mật khẩu, số giấy tờ hoặc dữ liệu nhạy cảm. Không đưa nguyên xi `FieldError#getRejectedValue()` vào response hoặc log phổ thông.

### 5.3. Constraint không bảo đảm field có mặt

Một số constraint mặc định xem `null` là hợp lệ, ví dụ `@Min` và `@Email`. Vì vậy, khi muốn yêu cầu giá trị, dùng `@NotNull`; khi muốn yêu cầu string có ký tự không whitespace, dùng `@NotBlank`. Trong demo:

```java
public record CreateUserRequest(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

`{"name":"Lan"}` parse thành DTO với `age=null`, sau đó `@NotNull` thất bại. Nó khác hẳn `{"name":"Lan","age":"abc"}`: lỗi deserialization xảy ra trước khi Bean Validation được thực thi.

### 5.4. Sai kiểu dữ liệu không phải luôn sai cú pháp JSON

Các payload này đều là JSON có cú pháp đúng:

```json
{"age": "abc"}
```

```json
{"age": null}
```

```json
{"age": 17}
```

Nhưng với DTO demo:

- `"abc"`: không chuyển thành `Integer` → unreadable.
- `null`: có thể tạo DTO thành công → `@NotNull` vi phạm.
- `17`: tạo DTO thành công → `@Min(18)` vi phạm.

Phân loại theo **giai đoạn thất bại**, không chỉ theo “nhìn payload có vẻ sai”.

## 6. HTTP status và định dạng API error

### 6.1. Vì sao cả hai đều thường là 400?

HTTP `400 Bad Request` phù hợp khi client gửi body không đọc được **hoặc** dữ liệu đầu vào không đáp ứng quy tắc của endpoint. Cùng status không có nghĩa cùng cách sửa:

- Với `REQUEST_BODY_UNREADABLE`, client phải sửa JSON syntax, shape, kiểu hoặc yêu cầu có body.
- Với `CONSTRAINT_VIOLATION`, client phải sửa giá trị field theo quy tắc nhận được.

Một API cũng có thể chọn `422 Unprocessable Content` cho một số trường hợp dữ liệu đã parse được nhưng không hợp lệ theo nghiệp vụ, nếu **đó là contract đã thống nhất**. Tuy nhiên, trong Spring MVC với `@Valid @RequestBody` mặc định, validation errors thường được ánh xạ sang **400**. Không tự đổi thành 422 mà không xét client contract và exception handling.

### 6.2. Một mẫu hợp đồng nhất quán

Ví dụ cấu trúc response có thể chuẩn hóa:

```json
{
  "code": "CONSTRAINT_VIOLATION",
  "message": "Request fields violate validation rules",
  "errors": [
    {"field": "age", "message": "must be greater than or equal to 18"}
  ],
  "traceId": "example-correlation-id"
}
```

Đây là **gợi ý thiết kế schema mở rộng**, khác với handler runnable ở mục 4 vì handler demo **chưa thêm `traceId`**. Có thể gắn correlation ID từ request tracing để hỗ trợ support và log đối chiếu, nhưng không đưa địa chỉ file, tên class implementation hoặc stack trace vào payload client.

Spring hỗ trợ **`ProblemDetail` / RFC 9457** qua cơ chế `ErrorResponse`, và `ResponseEntityExceptionHandler` có mặc định hỗ trợ xây response lỗi. Nếu API đã dùng Problem Details, nên giữ chuẩn `type`, `title`, `status`, `detail`, `instance` và thêm extension properties có kiểm soát thay vì tạo nhiều shape JSON không nhất quán. Ví dụ chạy ở mục 4 chọn `Map` tối giản để làm nổi bật sự khác nhau giữa hai loại lỗi.

### 6.3. Các lỗi khác không nên gom chung

| Hiện tượng | Exception/status tiêu biểu | Có phải JSON syntax hay Bean Validation? |
| --- | --- | --- |
| `Content-Type: text/plain` cho endpoint chỉ nhận JSON | `HttpMediaTypeNotSupportedException` (415) | Không |
| Phương thức HTTP không hỗ trợ, ví dụ GET vào endpoint chỉ POST | `HttpRequestMethodNotSupportedException` (405) | Không |
| Không có `@Valid` nhưng DTO vi phạm annotation | Có thể vẫn gọi controller, nếu không có cơ chế validation khác | Không tự phát sinh constraint exception |
| Lỗi kết nối database khi xử lý body hợp lệ | Exception infrastructure, thường nhóm 5xx | Không |
| Vi phạm unique constraint DB sau khi xử lý DTO hợp lệ | Exception tầng persistence; mapping status theo API | Không đồng nhất với Jakarta Bean Validation |
| `@RequestParam int page` nhận chữ `abc` | Có thể `MethodArgumentTypeMismatchException` / 400 | Không phải lỗi JSON deserialization của `@RequestBody` |

Tên đúng của lỗi media type trong Spring MVC là `HttpMediaTypeNotSupportedException`, không phải `HttpMessageNotReadableException`; cả hai có thể xuất hiện trong quá trình xử lý request nhưng có ý nghĩa khác nhau.

## 7. Trường hợp Spring MVC 6.1+: method validation có thể đổi exception

Trong Spring MVC 6.1+, nếu constraint được đặt **trực tiếp** trên method parameter hoặc return value, built-in method validation có thể kiểm tra cả các constraint đó và nested `@Valid` của DTO.

Ví dụ controller method có hai loại constraint:

```java
@PostMapping("/users")
public String create(
        @RequestParam @Min(1) int tenant,
        @Valid @RequestBody CreateUserRequest body) {
    return "ok";
}
```

Đây là **fragment minh họa**, không phải method được dùng trong project runnable. Nếu body JSON vẫn không đọc được, Jackson/converter tiếp tục có thể gây `HttpMessageNotReadableException` trước khi có đủ args để validate method. Nếu JSON đọc được nhưng giá trị method/DTO không hợp lệ, Spring MVC built-in method validation có thể phát **`HandlerMethodValidationException`** thay vì `MethodArgumentNotValidException`.

Các điều kiện cần ghi nhớ:

- `@Valid` **không phải một constraint trực tiếp**; một mình nó thường kích hoạt validation của DTO ở argument level.
- Constraint trực tiếp như `@Min` hoặc `@NotNull` trên method parameter có thể khiến built-in **method validation** áp dụng.
- Controller có class-level `@Validated` có thể dùng **AOP-based method validation** thay cho built-in MVC method validation. Theo hướng dẫn Spring 6.1+, khi muốn cơ chế built-in, nên bỏ `@Validated` class-level khỏi controller.
- `BindingResult`/`Errors` đặt ngay sau một đối số hợp lệ có thể cho phép xử lý lỗi bên trong controller theo contract riêng, khiến exception mặc định không xuất hiện theo cách thường gặp.

Vì vậy, một error handler hoàn chỉnh cho MVC 6.1+ thường cần hỗ trợ cả **`MethodArgumentNotValidException` lẫn `HandlerMethodValidationException`**. API về danh sách parameter validation results khác danh sách field errors của một `BindingResult`; không ép kiểu hai exception sang nhau.

Trong project demo, controller **không đặt constraint trực tiếp lên tham số method ngoài `@Valid`**, vì mục tiêu là minh họa đúng hai nhánh “unreadable body” và “DTO constraint violation” một cách dễ kiểm chứng.

## 8. Những lưu ý bảo mật và vận hành

1. **Không lộ raw Jackson exception message** cho người dùng ngoài. Message có thể chứa tên class, property path nội bộ, chuỗi gây lỗi hoặc chi tiết định dạng.
2. **Không đưa rejected value nhạy cảm** từ `FieldError` ra client: mật khẩu, token, dữ liệu cá nhân và thông tin tài chính không cần xuất hiện.
3. **Log đúng tầng**: lỗi client đầu vào thường là thông tin ở mức debug/monitoring phù hợp, không phải mọi lần nhập sai đều cần stack trace ở mức ERROR. Kèm request ID thay vì ghi toàn bộ payload.
4. **Giới hạn kích thước request body** và cấu hình các giới hạn deserialize phù hợp để tránh các payload quá lớn, mảng quá sâu hoặc dữ liệu tiêu tốn tài nguyên.
5. **Đừng đổi mọi exception thành 400** qua một `@ExceptionHandler(Exception.class)` chung. Lỗi server, cấu hình, database hoặc code bug cần được phân biệt.
6. **Không dùng lời nhắn lỗi làm API contract duy nhất**. Giữ các error code ổn định, field path hợp lý và localization riêng.
7. **Không tin vào annotation chỉ vì nó tồn tại**. Phải có Jakarta Validation provider và điểm kích hoạt như `@Valid`, `@Validated` hoặc method-validation integration.
8. **Không xử lý lỗi parse bằng Bean Validation**. ConstraintValidator chỉ nhận object/giá trị sau deserialization, không phải raw token stream.
9. **Không lưu thông tin partial state** vào database nếu deserialize hoặc validation thất bại. Controller thông thường chưa được gọi trong hai nhánh này; nếu có custom deserializer hay interceptor gây side effect, cần đánh giá riêng.
10. **Theo dõi tỷ lệ lỗi riêng**: `REQUEST_BODY_UNREADABLE` tăng có thể chỉ ra client version/schema mismatch, còn `CONSTRAINT_VIOLATION` tăng có thể do UI không giải thích đúng quy tắc hoặc data contract thiếu đồng bộ.

## 9. Cách debug theo từng câu hỏi

Khi nhận HTTP 400 từ một endpoint JSON:

1. **Kiểm tra Content-Type**. Nó có thật sự là `application/json` và được converter hỗ trợ không? Nếu là 415, đây là vấn đề media type.
2. **Kiểm tra body nguyên bản** (trong môi trường an toàn, tránh dữ liệu nhạy cảm). JSON có đúng dấu ngoặc, string escape và token không?
3. **Kiểm tra mapping vào DTO**. Tên field, enum, kiểu số, ngày giờ, collection, custom deserializer và constructor có tương thích?
4. **Đọc exception class ở server log/test**. `HttpMessageNotReadableException` nghĩa là chưa đọc được body thành đối số; xem cause để biết lỗi parse hay type mismatch.
5. **Nếu đã deserialize**, kiểm tra `@Valid`/`@Validated` và Jakarta Validation provider, constraint trên DTO, validation groups, logic cascade `@Valid`.
6. **Nếu có `MethodArgumentNotValidException`**, xem `BindingResult#getFieldErrors()` và `getGlobalErrors()`. Đừng chỉ in `ex.getMessage()`.
7. **Nếu có `HandlerMethodValidationException`**, xem method parameters có direct constraint hoặc return constraint không; áp dụng built-in MVC validation theo tài liệu phiên bản đang dùng.
8. **Nếu controller đã chạy**, lỗi có thể thuộc business logic/DB chứ không còn là hai nhóm tiền xử lý mặc định.
9. **Đối chiếu với test** mô phỏng malformed JSON, wrong type, valid JSON/invalid constraint, missing required field và valid request.
10. **Kiểm tra API response** được client nhận: status, code, field details và tính nhất quán giữa các endpoint.

### Một checklist kiểm thử ngắn

| Test case | Dữ liệu | Nhánh kỳ vọng |
| --- | --- | --- |
| Sai dấu phẩy | `{"name":,"age":20}` | Unreadable / parse error |
| Sai kiểu số | `{"name":"Lan","age":"abc"}` | Unreadable / mapping error |
| Field rỗng + dưới tuổi | `{"name":"","age":15}` | Constraint violation |
| Thiếu `age` | `{"name":"Lan"}` | Constraint violation do `@NotNull` |
| Thành công | `{"name":"Lan","age":22}` | Controller trả 201 |
| Body thiếu khi required | Không gửi body | Unreadable request body |
| HTTP media type sai | `text/plain` | 415, không phải hai nhóm trên |
| Thêm direct method constraint | `@Min(1) @RequestParam int tenant` | Có thể dùng `HandlerMethodValidationException` |

Các test quan trọng nhất nên xác nhận **exception type thực tế và response code**. Không dựa trên việc cả hai nhóm đều tình cờ có status 400.

## 10. Kết luận và nguyên tắc áp dụng

**JSON sai cú pháp**: JSON parser không đọc được token → `HttpMessageNotReadableException`.

**JSON đúng cú pháp nhưng sai kiểu DTO**: converter không tạo được object → cũng thường là `HttpMessageNotReadableException`, nhưng nguyên nhân không phải parser syntax.

**JSON parse/mapping thành công nhưng vi phạm constraint**: Bean Validation đánh giá object sau deserialization → thông thường là `MethodArgumentNotValidException` với `@Valid @RequestBody` command object; Spring MVC 6.1+ method validation có thể tạo `HandlerMethodValidationException` trong chữ ký controller thích hợp.

Ba kết quả có thể đều được client nhìn thấy dưới HTTP 400, nên cần **error code riêng, response schema nhất quán, kiểm thử bằng MockMvc và không làm lộ thông tin nhạy cảm**. Phân loại chính xác theo giai đoạn lỗi sẽ giúp client biết phải sửa **cú pháp/kiểu JSON** hay **giá trị theo quy tắc**.

## Tài liệu tham khảo

- [Spring Framework — `@RequestBody` and validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MVC validation and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — DefaultHandlerExceptionResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/support/DefaultHandlerExceptionResolver.html)
- [Jakarta Validation — Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jackson — JsonParseException Javadoc](https://fasterxml.github.io/jackson-core/javadoc/2.17/com/fasterxml/jackson/core/JsonParseException.html)
