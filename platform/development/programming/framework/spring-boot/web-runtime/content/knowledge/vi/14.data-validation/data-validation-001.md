# Thiết lập Bean Validation và spring-boot-starter-validation trong Spring Boot

## Mục tiêu học tập

Khi viết API, dữ liệu JSON hợp lệ về cú pháp chưa chắc hợp lệ về nghiệp vụ: email có thể rỗng, tuổi âm, giá âm hoặc một đối tượng con thiếu thuộc tính. **Jakarta Bean Validation** cho phép biểu đạt những quy tắc cơ bản ngay trên kiểu dữ liệu bằng constraint annotations và kiểm tra chúng qua một validation provider. Trong Spring Boot, **spring-boot-starter-validation** là cách thông dụng để bổ sung hạ tầng này.

Sau bài học, bạn có thể:

- Phân biệt API Jakarta Validation, Hibernate Validator, Spring Validator, @Valid và @Validated.
- Cài spring-boot-starter-validation bằng Maven/Gradle và nhận diện khác biệt giữa javax.validation và jakarta.validation.
- Dùng @NotNull, @NotBlank, @NotEmpty, @Size, @Min, @Max, @Email, @Positive, @Past, @Future và các constraint thích hợp.
- Kích hoạt validation của @RequestBody trong Spring MVC và WebFlux; kiểm tra nested object bằng @Valid.
- Hiểu validation cho method parameter/service qua @Validated và những giới hạn khi dùng AOP proxy.
- Xử lý lỗi validation thành HTTP 400, không lộ dữ liệu nhạy cảm, đồng thời phân biệt validation error với JSON parse error.
- Dùng Validator để kiểm tra dữ liệu ngoài web layer, viết custom constraint và tùy chỉnh thông báo.
- Kiểm thử một REST API Java 17+ bằng MockMvc và các tình huống biên thường gặp.

## 1. Phân biệt các lớp trong hệ thống validation

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| Jakarta Validation | Định nghĩa chuẩn annotation/API để khai báo và đánh giá constraint | jakarta.validation.Valid, Validator, ConstraintViolation |
| Hibernate Validator | Một implementation phổ biến của Jakarta Validation | Thực thi logic @NotBlank, @Email, @Size |
| spring-boot-starter-validation | Starter Spring Boot cung cấp dependency validation cần thiết | Maven/Gradle dependency |
| Spring Validation | Tích hợp constraint validation với binding, controller và service | LocalValidatorFactoryBean, BindingResult |
| @Valid | Yêu cầu đánh giá constraint trên một object và đi vào các đối tượng con được đánh dấu cascade | jakarta.validation.Valid |
| @Validated | Annotation của Spring, dùng để kích hoạt method validation tại bean/class hoặc chọn validation groups | org.springframework.validation.annotation.Validated |
| Constraint annotation | Mô tả một điều kiện hợp lệ | @NotNull, @Size, @Min, @Email |
| ConstraintValidator | Implementation cho một constraint tự định nghĩa | Kiểm tra mã đơn hàng theo quy tắc riêng |

Hình dung luồng với REST API:

~~~text
HTTP request JSON
       |
       v
Spring MVC HttpMessageConverter / WebFlux codec
       |
       v
Deserialize thành DTO
       |
       +--- @Valid / @Validated được khai báo phù hợp?
       |             |
       |             v
       |       Jakarta Validation API
       |             |
       |             v
       |       Hibernate Validator (provider)
       |             |
       |      +------+------+
       |      |             |
       |     PASS          FAIL
       |      |             |
       v      v             v
   Controller          validation exception
       |                     |
       v                     v
   Business logic       HTTP 400 / error handler
       |
       v
   HTTP response
~~~

**Lưu ý:** Jackson chịu trách nhiệm đọc JSON thành đối tượng, không thay thế Bean Validation. @Valid không làm cho JSON sai cú pháp trở thành hợp lệ. Một constraint như @Min cũng không tự chứng minh mọi quy tắc kinh doanh; ví dụ “email đã đăng ký hay chưa” thường cần tra cứu service/database.

## 2. Thêm spring-boot-starter-validation

### 2.1. Maven

Với Spring Boot parent hoặc BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đối với dự án Spring Boot 3.5 Spring MVC, đồng thời dùng web starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

### 2.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 2.3. Spring Boot 4.x

Theo migration guide của Spring Boot 4, tên starter validation vẫn là **spring-boot-starter-validation**. Tuy nhiên starter MVC được tách/đặt tên chuyên biệt **spring-boot-starter-webmvc**; dùng dependency tương ứng với phiên bản thực tế. Boot 4 còn giới thiệu các test starter tương ứng, chẳng hạn spring-boot-starter-validation-test; không nên lấy nguyên bộ Maven dependencies của ví dụ Boot 3.5 áp vào Boot 4 mà không kiểm tra migration guide.

Tất cả ví dụ Java runnable chính trong bài này nhắm **Java 17+, Spring Boot 3.5.x, Jakarta Validation**. Để bảo đảm tính tương thích, để Spring Boot BOM chọn phiên bản Hibernate Validator và các thư viện Jakarta.

### 2.4. Vì sao starter validation cần được khai báo rõ?

Từ các thế hệ Spring Boot hiện đại, không nên mặc định rằng thêm starter web là có provider validation. Nếu API classes có mặt nhưng provider không có, constraint có thể không được đánh giá theo kỳ vọng.

Dấu hiệu có thể gặp:

- @Valid được thêm vào controller nhưng dữ liệu vi phạm constraint vẫn lọt qua.
- Dependency resolution thiếu class Hibernate Validator hoặc Jakarta Validation.
- Khởi động gặp lỗi liên quan ValidatorFactory/ValidationProvider.
- Service không bị chặn dù method có @NotBlank và @Validated.

Hãy kiểm tra dependency tree thay vì thêm ngẫu nhiên nhiều implementation validation:

~~~bash
./mvnw dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Thông thường, chỉ cần starter validation là đủ để Boot thiết lập provider và adapter hợp lý. Không cần tự thêm Hibernate Validator version hoặc tự cấu hình LocalValidatorFactoryBean nếu không có yêu cầu đặc biệt.

## 3. Jakarta Validation và khác biệt package javax → jakarta

Ở các ứng dụng Spring Boot 3.x và 4.x hiện đại, dùng:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

Trong dự án cũ Spring Boot 2.x, bạn thường gặp:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

Hai namespace này không thể thay thế một cách tùy tiện. Một ví dụ trên internet viết javax.validation có thể không compile hoặc không được tích hợp như mong muốn trong Spring Boot 3+.

| Ứng dụng | Namespace thông dụng |
|---|---|
| Spring Boot 2.x / Spring Framework 5 | javax.validation.* |
| Spring Boot 3.x / Spring Framework 6 | jakarta.validation.* |
| Spring Boot 4.x / Spring Framework 7 | jakarta.validation.* |

Đừng thêm cả hai bộ javax/jakarta để “giải quyết” lỗi import. Hãy chọn Jakarta phù hợp với stack của dự án và thay dependency cũ một cách có kiểm soát.

## 4. Các constraint thông dụng

| Constraint | Dùng cho | Ý nghĩa thường gặp |
|---|---|---|
| @NotNull | Reference type | Phải khác null; không bảo đảm String không rỗng |
| @NotEmpty | CharSequence, Collection, Map, Array... | Không null và không rỗng; chuỗi chỉ có dấu cách vẫn được coi là không rỗng |
| @NotBlank | CharSequence | Không null, phải có ký tự không phải whitespace |
| @Size(min, max) | String/Collection/Array/Map... | Giới hạn độ dài/số phần tử; không nhất thiết chặn null |
| @Min(n), @Max(n) | Kiểu số hỗ trợ | Tối thiểu/tối đa (bao gồm giới hạn) |
| @Positive, @PositiveOrZero | Kiểu số hỗ trợ | Lớn hơn 0 / không nhỏ hơn 0 |
| @Negative, @NegativeOrZero | Kiểu số hỗ trợ | Nhỏ hơn 0 / không lớn hơn 0 |
| @DecimalMin, @DecimalMax | Kiểu số hỗ trợ | Giới hạn thập phân với cấu hình inclusive/exclusive |
| @Digits(integer, fraction) | Số hoặc biểu diễn số phù hợp | Giới hạn chữ số phần nguyên/phần thập phân |
| @Email | CharSequence | Kiểm tra cấu trúc email theo provider, không xác minh hộp thư tồn tại |
| @Pattern(regexp) | CharSequence | Khớp biểu thức chính quy |
| @Past, @PastOrPresent | Date/time hỗ trợ | Thời điểm trong quá khứ hoặc không vượt hiện tại |
| @Future, @FutureOrPresent | Date/time hỗ trợ | Thời điểm trong tương lai hoặc không trước hiện tại |
| @AssertTrue, @AssertFalse | Boolean/boolean | Quy tắc boolean |
| @Valid | Object con/collection elements | Yêu cầu cascade validation; bản thân không phải constraint |

### Bẫy lớn: @NotNull, @NotEmpty và @NotBlank khác nhau

Giả sử giá trị là String:

| Giá trị | @NotNull | @NotEmpty | @NotBlank |
|---|---|---|---|
| null | FAIL | FAIL | FAIL |
| "" | PASS | FAIL | FAIL |
| "   " | PASS | PASS | FAIL |
| "abc" | PASS | PASS | PASS |

Vì vậy tên người dùng hay email bắt buộc thường nên dùng @NotBlank thay vì chỉ @NotNull.

### @Size khác @Min

@Size(min = 3) kiểm tra độ dài hoặc số phần tử theo loại được hỗ trợ. @Min(3) kiểm tra giá trị số ít nhất 3; **không** dùng @Min(3) để yêu cầu String có 3 ký tự.

Ví dụ:

~~~java
@NotBlank
@Size(min = 2, max = 50)
String name;

@NotNull
@Min(18)
Integer age;
~~~

Các đoạn này minh họa field trong DTO/class. Với Integer, @NotNull cần thiết vì nhiều numeric constraints chấp nhận null và chỉ kiểm tra khi có giá trị.

### @Email không thay việc xác minh email

@Email kiểm tra định dạng theo provider, không kiểm tra MX record, khả năng nhận email hoặc quyền sở hữu hộp thư. Nếu trường email bắt buộc:

~~~java
@NotBlank
@Email
String email;
~~~

Đừng chỉ dùng @Email và cho rằng nó cấm null, chuỗi rỗng hoặc whitespace trong mọi trường hợp. Kết hợp @NotBlank theo hợp đồng API.

## 5. Khi nào validation chạy?

Annotation không tự chạy theo kiểu “cứ tạo object là validate”. Validation phải được kích hoạt ở một điểm thực thi:

1. Spring MVC xử lý @Valid @RequestBody hoặc @Validated trên argument được hỗ trợ.
2. WebFlux xử lý @Valid @RequestBody theo hợp đồng reactive.
3. Spring method validation kiểm tra method parameter/return value theo @Validated và proxy/handler method integration.
4. Bạn gọi Validator.validate(object) trực tiếp.
5. Một hệ thống ngoài web tích hợp Jakarta Validation vào persistence/other lifecycle.

Ví dụ tự tạo DTO bằng new:

~~~java
SignupRequest request =
    new SignupRequest("", "not-email", null);
~~~

Object Java vẫn có thể được tạo; annotation trên record components không tự ném exception từ constructor. Muốn kiểm tra ngoài web layer, gọi Validator hoặc đưa qua service/method đã bật validation.

## 6. @Valid và @Validated khác nhau ở điểm nào?

### @Valid của Jakarta

~~~java
import jakarta.validation.Valid;
~~~

Đây là annotation chuẩn dùng đánh dấu object cần cascade validation hoặc yêu cầu validation ở những integration points mà framework hỗ trợ. Ví dụ:

~~~java
@PostMapping("/api/users")
public ResponseEntity<UserView> create(
        @Valid @RequestBody SignupRequest request) {
    // ...
}
~~~

Trong Spring MVC, nếu DTO vi phạm các constraint, framework thông thường trả 400 trước khi business method chạy (hoặc để exception handler xử lý).

### @Validated của Spring

~~~java
import org.springframework.validation.annotation.Validated;
~~~

@Validated hỗ trợ validation groups và thường được dùng trên service type khi muốn Spring method validation thông qua AOP proxy:

~~~java
@Service
@Validated
public class UserService {
    public void register(@NotBlank String email) {
        // ...
    }
}
~~~

Ví dụ chỉ hoạt động theo ý định nếu service được quản lý bởi Spring, method đi qua proxy và có validation provider/hạ tầng method validation phù hợp. Không phải mọi lời gọi trực tiếp new UserService() đều được Spring kiểm tra.

### Quy tắc trong controller Spring Framework 6.1+

Spring MVC có **built-in method validation** cho controller khi constraint đặt trực tiếp trên method parameter hoặc return value. Để sử dụng cơ chế này thay vì AOP proxy cho controller, tài liệu Spring Framework khuyên **không** đặt @Validated ở class-level controller một cách máy móc.

Ví dụ:

~~~java
@GetMapping("/api/users/{id}")
public UserView find(@PathVariable @Min(1) long id) {
    // ...
}
~~~

Với built-in handler method validation, constraint trên id có thể dẫn đến HandlerMethodValidationException khi giá trị không hợp lệ. Điều này khác với lỗi trên một @Valid @RequestBody DTO. Không giả định mọi lỗi validation ở controller đều là MethodArgumentNotValidException.

## 7. Cách kích hoạt validation cho @RequestBody trong Spring MVC

Một DTO đầy đủ sử dụng record:

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(message = "email bắt buộc")
        @Email(message = "email sai định dạng")
        String email,

        @NotBlank(message = "tên bắt buộc")
        @Size(min = 2, max = 50, message = "tên dài 2–50 ký tự")
        String name,

        @NotNull(message = "tuổi bắt buộc")
        @Min(value = 18, message = "phải từ 18 tuổi")
        Integer age
) {
}
~~~

Khi method controller khai báo @Valid @RequestBody SignupRequest, Spring sẽ:

1. Đọc JSON body.
2. Deserialize thành SignupRequest (Jackson).
3. Chạy constraints do provider triển khai.
4. Nếu PASS, truyền object vào controller.
5. Nếu FAIL, theo nhánh validation error; trong tình huống argument validation thông thường là MethodArgumentNotValidException và HTTP 400 theo default handler.

### Vì sao Integer thay cho int?

Nếu một JSON request không gửi trường age, Integer có thể là null để @NotNull nhận diện thiếu dữ liệu. Nếu dùng int, deserialize/binding có thể tạo giá trị mặc định hoặc sinh lỗi kiểu khác tùy mapper và input. Với trường bắt buộc cần phân biệt missing/null với số hợp lệ, wrapper thường rõ contract hơn.

### JSON hợp lệ không đồng nghĩa dữ liệu hợp lệ

Request:

~~~json
{
  "email": "not-an-email",
  "name": " ",
  "age": 16
}
~~~

Đây là JSON đúng cú pháp và có thể deserialize thành Java record, nhưng vi phạm @Email, @NotBlank/@Size, @Min.

Request lỗi cú pháp:

~~~json
{"email": "an@example.com", "name":
~~~

Ở đây decoder/parser có thể ném HttpMessageNotReadableException trước cả khi Bean Validation được áp dụng. Cần phân biệt message conversion error với constraint violation.

## 8. Ví dụ REST API Spring Boot hoàn chỉnh (Java 17+)

Ví dụ chạy được nhắm **Spring Boot 3.5.x**, Java 17+ với Maven Wrapper. Chọn **Spring Web**, **Validation** và, cho kiểm thử, **Spring Boot Test**. Nếu Maven không có wrapper, dùng lệnh mvn spring-boot:run tương ứng.

### 8.1. Dependencies

Trong pom.xml của dự án Spring Boot có parent/BOM:

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

### 8.2. ValidationApplication.java

File: src/main/java/com/example/validation/ValidationApplication.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
~~~

### 8.3. SignupRequest.java

Dùng toàn bộ nội dung record ở phần 7. Không cần tạo class getters/setters khi DTO là record Java 17 với Jackson/Bean Validation versions phù hợp.

### 8.4. UserView.java

File: src/main/java/com/example/validation/UserView.java

~~~java
package com.example.validation;

public record UserView(
        long id,
        String email,
        String name,
        int age
) {
}
~~~

### 8.5. UserController.java

File: src/main/java/com/example/validation/UserController.java

~~~java
package com.example.validation;

import java.net.URI;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private final AtomicLong sequence = new AtomicLong();

    @PostMapping
    public ResponseEntity<UserView> create(
            @Valid @RequestBody SignupRequest request) {

        long id = sequence.incrementAndGet();

        UserView result = new UserView(
            id,
            request.email().trim(),
            request.name().trim(),
            request.age()
        );

        return ResponseEntity
            .created(URI.create("/api/users/" + id))
            .body(result);
    }

    @GetMapping("/{id}")
    public ResponseEntity<UserView> find(@PathVariable long id) {
        return ResponseEntity.notFound().build();
    }
}
~~~

Chú ý: GET ở đây luôn trả 404 vì ví dụ **không lưu database/in-memory users**, chỉ minh họa validation của POST. Đây là hành vi có chủ đích, không phải lỗi của validation. Nếu muốn GET trả dữ liệu thật, cần thêm repository/service và persistence.

Điều đáng học là controller **không cần** kiểm tra lặp lại email/name/age bằng nhiều if; DTO cùng @Valid mô tả các ràng buộc trước khi tạo response.

### 8.6. ValidationErrorAdvice.java

Để trả lỗi 400 có cấu trúc, có thể xử lý MethodArgumentNotValidException ở Spring MVC:

~~~java
package com.example.validation;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalidBody(
            MethodArgumentNotValidException ex) {

        Map<String, String> errors = new LinkedHashMap<>();

        ex.getBindingResult().getFieldErrors().forEach(fieldError ->
            errors.putIfAbsent(
                fieldError.getField(),
                fieldError.getDefaultMessage()
            )
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "Dữ liệu không hợp lệ");
        body.put("errors", errors);

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Lý do dùng putIfAbsent: một field có thể vi phạm nhiều constraint; demo chỉ trả một thông báo đầu tiên cho mỗi field, không bảo đảm thứ tự validation errors. Nếu API cần trả **tất cả** lỗi trên mỗi field, dùng Map<String,List<String>> hoặc danh sách error objects thay vì gom một lỗi.

Trong sản phẩm thực tế, có thể dùng **ProblemDetail** (Spring Framework 6+) và hợp đồng lỗi thống nhất. Không echo raw password/token hoặc toàn bộ rejected value vào response. Thông báo validation có thể được localize theo Locale/MessageSource.

**Giới hạn xử lý của advice này:** Chỉ bắt lỗi @Valid @RequestBody thuộc nhánh MethodArgumentNotValidException của MVC. Nó không có nghĩa tự bắt HandlerMethodValidationException, lỗi JSON parse hoặc validation lỗi service. Những trường hợp đó phải được xử lý riêng khi API sử dụng.

### 8.7. Chạy và kiểm tra bằng curl

Từ project root:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Gửi request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"email":"an@example.com","name":"An Nguyen","age":20}'
~~~

Với ứng dụng mới khởi động, sequence bắt đầu từ 0. Response thành công đầu tiên có status **201 Created**, header **Location: /api/users/1** và JSON body tương đương:

~~~json
{"id":1,"email":"an@example.com","name":"An Nguyen","age":20}
~~~

Gửi dữ liệu sai:

~~~bash
curl -i -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"email":"wrong-format","name":" ","age":16}'
~~~

Response dự kiến là **400 Bad Request** với body có trường message và map errors. Giá trị cụ thể của thông báo cho name có thể đến từ @NotBlank hoặc @Size, vì cả hai có thể fail; thứ tự không nên dùng làm API contract.

Một body minh họa (không bảo đảm thứ tự keys):

~~~json
{
  "message": "Dữ liệu không hợp lệ",
  "errors": {
    "email": "email sai định dạng",
    "name": "tên bắt buộc",
    "age": "phải từ 18 tuổi"
  }
}
~~~

Nếu name trả thông báo "tên dài 2–50 ký tự" trong môi trường này, đó vẫn có thể là kết quả hợp lệ của constraint, không phải lỗi framework.

### 8.8. Vì sao ví dụ dùng @Valid ở controller?

Chỉ khai báo constraint trên DTO mà viết method thế này là chưa rõ validation point:

~~~java
@PostMapping
public ResponseEntity<UserView> create(
        @RequestBody SignupRequest request) {
    // ...
}
~~~

Để bảo đảm validation argument theo Spring MVC integration, nên dùng **@Valid @RequestBody**. Đừng mặc định tất cả nơi nhận SignupRequest đều tự động validate.

## 9. Kiểm thử HTTP với MockMvc

Test quan trọng không chỉ xem JSON parse được, mà còn xác nhận status 201 với input hợp lệ và 400 khi Bean Validation fail.

File: src/test/java/com/example/validation/UserControllerTest.java

~~~java
package com.example.validation;

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
class UserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void validPayloadCreatesUser() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"an@example.com",
                     "name":"An Nguyen",
                     "age":20}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.email")
                .value("an@example.com"))
            .andExpect(jsonPath("$.age").value(20));
    }

    @Test
    void invalidPayloadIsRejectedBeforeControllerLogic() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"wrong-format",
                     "name":" ",
                     "age":16}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message")
                .value("Dữ liệu không hợp lệ"))
            .andExpect(jsonPath("$.errors.email").exists())
            .andExpect(jsonPath("$.errors.name").exists())
            .andExpect(jsonPath("$.errors.age").exists());
    }
}
~~~

Các test không so sánh ID cụ thể vì một Spring context có thể chạy nhiều test và AtomicLong được chia sẻ. Test thứ hai xác nhận tất cả field invalid đều có lỗi, nhưng không ràng buộc thứ tự message khi một field vi phạm nhiều constraint.

Bạn cũng nên bổ sung các test: email null, name rỗng, age thiếu, name dài hơn 50 ký tự, JSON malformed, media type không đúng, chuỗi Unicode và giá trị biên 18/17.

### Test validator ngoài HTTP

Với Spring context đã có validation starter, có thể inject Jakarta Validator để kiểm tra DTO thuần:

~~~java
@Autowired
jakarta.validation.Validator validator;

@Test
void invalidDtoHasConstraints() {
    SignupRequest request =
        new SignupRequest("", " ", null);

    var violations = validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

Đây là method minh họa cho một class test có imports JUnit và Spring đúng, không phải file độc lập. Nếu kiểm tra set message, nên dựa vào propertyPath và constraint type hoặc message code được kiểm soát, không phụ thuộc thứ tự phần tử của Set.

## 10. Nested validation với @Valid

Giả sử request có Address:

~~~java
public record Address(
    @NotBlank String city,
    @NotBlank String postalCode
) {
}
~~~

Và DTO cha:

~~~java
public record CheckoutRequest(
    @NotNull @Valid Address address,
    @NotEmpty String reference
) {
}
~~~

Các đoạn này minh họa records, cần imports jakarta.validation.Valid và các constraints.

Tại sao cần cả **@NotNull @Valid**?

- @Valid đánh dấu cần validate các thuộc tính bên trong **khi Address tồn tại**.
- @NotNull chặn trường hợp address không có hoặc là null.
- Nếu chỉ có @Valid, một reference address null thường không tự tạo constraint violation.
- Nếu chỉ có @NotNull, các constraint @NotBlank bên trong Address có thể không được validate bằng cascade như mong muốn.

Với collection:

~~~java
public record BatchRequest(
    @NotEmpty
    java.util.List<@Valid Address> addresses
) {
}
~~~

Jakarta Validation hỗ trợ container element validation cho các vị trí type-use phù hợp. Trong thực tế nên kết hợp constraints với từng phần tử nếu cần cấm null element; @Valid bản thân nó không cấm một phần tử null.

Ví dụ danh sách tag:

~~~java
public record TagRequest(
    @NotEmpty
    java.util.List<@NotBlank String> tags
) {
}
~~~

Ở đây @NotEmpty kiểm tra danh sách có phần tử; @NotBlank kiểm tra từng String trong danh sách. Không nên nghĩ @NotEmpty trên List tự kiểm tra tính hợp lệ của tất cả element.

## 11. Method validation ở service với @Validated

Bean Validation không chỉ dùng ở HTTP DTO. Một service có thể đặt constraint trực tiếp trên method parameter hoặc return value.

Ví dụ:

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class EmailService {

    @NotNull
    public String normalize(
            @NotBlank @Email String address) {

        return address.trim().toLowerCase(
            java.util.Locale.ROOT
        );
    }
}
~~~

Khi method này được gọi **qua Spring-managed proxy**, method validation có thể kiểm tra address trước khi body method chạy và kiểm tra return value theo hợp đồng. Với tham số sai, exception ở tầng method validation thường là **jakarta.validation.ConstraintViolationException** trong cấu hình thường gặp, nhưng behavior có thể thay đổi theo cơ chế Spring/adapter đang dùng.

### Các điều kiện quan trọng

- Có starter validation và provider phù hợp trên classpath.
- Service là Spring-managed bean.
- @Validated ở type-level nếu dùng AOP method validation theo Spring Boot thông dụng.
- Method được gọi từ bean khác qua proxy; self-invocation như this.normalize("") có thể bypass proxy.
- Các method private/final hoặc method không được proxy intercept theo cấu hình AOP không tự có bảo đảm validation.
- Tùy JDK proxy/CGLIB và nơi khai báo annotation, behavior có thể khác; đừng coi annotation là một câu lệnh Java chạy độc lập.

Không dùng @Validated class-level trên controller để “bắt chắc mọi lỗi” nếu bạn muốn sử dụng built-in handler method validation của Spring Framework 6.1+. Xem phần 12 để phân biệt lỗi của controller.

### Validation ở service không thay nghiệp vụ

@Email không kiểm tra unique email trong database. @Min(18) không xác minh ngày sinh thật. Những quy tắc như user balance, inventory, permission, transaction invariants cần logic ở service và database constraints phù hợp. Validation là lớp đầu vào, không phải tấm khiên bảo mật duy nhất.

## 12. Hai con đường validation trong Spring MVC/WebFlux

Từ Spring Framework 6.1, annotation controller có hai đường validation chủ yếu.

### Đường A: Validation một object argument

Ví dụ:

~~~java
@PostMapping("/api/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody OrderRequest request) {
    // ...
}
~~~

Nếu dữ liệu object sai constraint và không có method-level constraints khác làm kích hoạt method validation, Spring MVC thường phát **MethodArgumentNotValidException**. WebFlux thường dùng **WebExchangeBindException**.

### Đường B: Built-in handler method validation

Ví dụ:

~~~java
@GetMapping("/api/orders/{id}")
public OrderView find(@PathVariable @Min(1) long id) {
    // ...
}
~~~

Constraint @Min đặt **trực tiếp** trên method parameter làm controller handler cần method validation. Cả Spring MVC và WebFlux có thể phát **HandlerMethodValidationException** trong cơ chế built-in tương ứng.

### Bảng đối chiếu

| Trường hợp | Spring MVC | Spring WebFlux |
|---|---|---|
| @Valid trên DTO @RequestBody, validation argument riêng | MethodArgumentNotValidException | WebExchangeBindException |
| Constraint trực tiếp @Min/@NotBlank trên method parameter | HandlerMethodValidationException khi built-in method validation áp dụng | HandlerMethodValidationException khi built-in method validation áp dụng |
| Service @Validated qua AOP | Thường ConstraintViolationException/biến thể cấu hình | Thường ConstraintViolationException/biến thể cấu hình |
| JSON sai cú pháp | HttpMessageNotReadableException | Thường lỗi đọc/codec request phù hợp, có thể ServerWebInputException |
| Constraint fail mặc định | Thường HTTP 400 ở input request | Thường HTTP 400 ở input request |

**Cần xử lý cả hai nhánh lỗi** nếu ứng dụng dùng đồng thời @Valid DTO và inline method constraints. Việc chỉ viết @ExceptionHandler(MethodArgumentNotValidException.class) sẽ không tự bao quát HandlerMethodValidationException.

Đừng giả định một lỗi method return-value validation cũng là lỗi request 400: khi ứng dụng vi phạm ràng buộc của chính dữ liệu đầu ra, đó có thể là lỗi phía server. Spring Framework có phân biệt status tùy trường hợp.

## 13. Validation trong Spring WebFlux

Spring WebFlux cũng hỗ trợ @Valid và @Validated, nhưng làm việc với HTTP body reactive. Ví dụ:

~~~java
@PostMapping("/api/users")
public Mono<ResponseEntity<UserView>> create(
        @Valid @RequestBody Mono<SignupRequest> request) {

    return request.map(valid -> {
        UserView view = new UserView(
            1L,
            valid.email(),
            valid.name(),
            valid.age()
        );

        return ResponseEntity
            .created(URI.create("/api/users/1"))
            .body(view);
    });
}
~~~

Đây là method minh họa, cần đặt trong WebFlux @RestController với các imports phù hợp, và cùng DTO từ ví dụ. WebFlux hỗ trợ validation khi decode request body reactive theo các điểm tích hợp được framework hỗ trợ. Không nên tự gọi block() chỉ để validation. Nếu muốn custom error handling trong WebFlux, xử lý WebExchangeBindException/HandlerMethodValidationException theo contract của stack thay vì copy nguyên advice MVC.

**Không đặt @Valid lên Mono một cách máy móc trong mọi signature mà không xem tài liệu của version đang dùng.** Framework có quy tắc cụ thể cho validation của Publisher-valued @RequestBody và các cách validate element trong pipeline. Khi cần service-level validation hoặc validate từng phần tử Flux, hãy thiết kế publisher và constraint validation rõ ràng, đồng thời bổ sung WebTestClient tests cho các trường hợp sai dữ liệu.

### WebTestClient kiểm tra reactive validation

Với một WebFlux endpoint đã thiết lập test fixture đúng:

~~~java
webTestClient.post()
    .uri("/api/users")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new SignupRequest(
        "wrong-format",
        " ",
        16
    ))
    .exchange()
    .expectStatus().isBadRequest();
~~~

Đây là đoạn trong test đã có WebTestClient và MediaType, không phải file độc lập. Điều cần xác minh là bad input bị từ chối theo HTTP 400, không phải thread nào gọi validator.

## 14. Thông báo validation và i18n

Một constraint có thể có message:

~~~java
@NotBlank(message = "tên bắt buộc")
String name;
~~~

Hoặc tham chiếu message key:

~~~java
@NotBlank(message = "{user.name.required}")
String name;
~~~

Khi có MessageSource được cấu hình phù hợp, có thể định nghĩa trong src/main/resources/messages.properties:

~~~properties
user.name.required=Tên là bắt buộc
~~~

Nếu cần nhiều ngôn ngữ, đặt các bundle messages_vi.properties và messages_en.properties theo chiến lược locale của ứng dụng. Spring Boot có auto-configuration MessageSource trong điều kiện phù hợp; quá trình message interpolation của Jakarta Validation cũng tham gia giải mã message templates.

**Không phụ thuộc vào thứ tự message** khi một field vi phạm nhiều constraints. Kết quả Validator.validate là Set<ConstraintViolation<T>>; test nên so field/property và mã loại constraint thay vì thứ tự thông báo.

Thay đổi message không phải thay đổi validation logic. Một String vẫn fail @NotBlank dù thông báo là tiếng Việt hay tiếng Anh.

## 15. Validation groups: khi tạo và cập nhật có quy tắc khác nhau

Jakarta Validation hỗ trợ **validation groups** để dùng các nhóm constraint khác nhau theo ngữ cảnh.

Ví dụ khai báo marker interfaces:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

Tách mỗi public interface vào file riêng theo quy tắc Java.

Một DTO minh họa:

~~~java
public record ProductForm(
    @NotNull(groups = OnUpdate.class)
    Long id,

    @NotBlank(groups = {
        OnCreate.class,
        OnUpdate.class
    })
    String title
) {
}
~~~

Trong controller có thể yêu cầu group:

~~~java
@PostMapping("/products")
public ResponseEntity<Void> create(
        @Validated(OnCreate.class)
        @RequestBody ProductForm form) {
    // ...
}
~~~

@Validated là extension của Spring hỗ trợ chọn groups trong binding/validation. Với @Valid thuần, default group được dùng trong các integration points thông thường.

**Bẫy về Default group:** Một constraint khai báo chỉ trong OnCreate/OnUpdate không tự thuộc group Default. Khi controller dùng @Valid đơn thuần, các constraint không thuộc Default có thể không chạy như bạn nghĩ. Dùng groups có chủ đích, nhất quán với các endpoint.

Nếu yêu cầu tạo/cập nhật khác biệt lớn về schema, hai DTO CreateProductRequest/UpdateProductRequest thường rõ và dễ bảo trì hơn một DTO có quá nhiều groups.

## 16. Custom constraint: khi annotation sẵn có không đủ

Giả sử một ứng dụng cần kiểm tra mã đơn theo định dạng "ORD-" theo sau là bốn chữ số. Có thể tạo custom constraint.

### 16.1. Annotation @OrderCode

File: src/main/java/com/example/validation/OrderCode.java

~~~java
package com.example.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = OrderCodeValidator.class)
public @interface OrderCode {

    String message() default "mã đơn phải có dạng ORD-1234";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

### 16.2. Validator implementation

File: src/main/java/com/example/validation/OrderCodeValidator.java

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class OrderCodeValidator
        implements ConstraintValidator<OrderCode, String> {

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        return value.matches("ORD-[0-9]{4}");
    }
}
~~~

Chúng ta trả true với null vì **sự bắt buộc** nên do @NotNull hoặc @NotBlank kiểm soát. Việc tách hai trách nhiệm cho phép constraint @OrderCode được dùng cho field tùy chọn và bắt buộc.

### 16.3. Gắn lên record

~~~java
public record OrderCodeRequest(
    @NotBlank
    @OrderCode
    String orderCode
) {
}
~~~

Để đoạn này compile, cần đặt trong file OrderCodeRequest.java đúng package và import NotBlank. Request "ORD-1234" hợp lệ; "ORD-12A4" hoặc "ABC-1234" fail. Mã đơn chỉ là định dạng minh họa; không có nghĩa kiểm tra tồn tại trong database.

Trong môi trường Spring, LocalValidatorFactoryBean có thể dùng SpringConstraintValidatorFactory để hỗ trợ dependency injection cho custom ConstraintValidator. Nếu custom validator phải đọc database, cân nhắc chi phí và transaction; đừng thực hiện HTTP/network blocking trong event loop WebFlux một cách thiếu kiểm soát.

### Vì sao không biến mọi business rule thành ConstraintValidator?

Custom constraint thích hợp cho một quy tắc thuần túy của dữ liệu. Nếu validation cần biết quyền của user, trạng thái tồn kho, version của đơn hàng hoặc tính nhất quán transaction, nên thực thi ở service/domain layer với hợp đồng lỗi phù hợp và transaction/locking khi cần.

## 17. Programmatic validation: kiểm tra khi không có HTTP controller

Bạn có thể inject Validator vào service để validate DTO/command object trong batch job, message listener hoặc luồng xử lý khác.

~~~java
package com.example.validation;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.stereotype.Service;

@Service
public class SignupValidationService {

    private final Validator validator;

    public SignupValidationService(Validator validator) {
        this.validator = validator;
    }

    public Set<ConstraintViolation<SignupRequest>> check(
            SignupRequest request) {
        return validator.validate(request);
    }
}
~~~

Đây là cách chủ động kiểm tra, không phụ thuộc vào @RequestBody. Kết quả có thể được ánh xạ thành lỗi nghiệp vụ của batch/message consumer hoặc HTTP response phù hợp. Không ép mọi vi phạm constraint ngoài HTTP thành 400; HTTP status chỉ có nghĩa khi đang tạo HTTP response.

### Không nhầm hai Validator interface

- **jakarta.validation.Validator**: API chuẩn, trả Set<ConstraintViolation<T>>.
- **org.springframework.validation.Validator**: API Spring nhận Errors để ghi field/global errors.
- **LocalValidatorFactoryBean**: adapter có thể tích hợp với hai thế giới validation trong Spring.

Khi viết code, import phải khớp cách bạn muốn dùng. Một biến org.springframework.validation.Validator sẽ không có chữ ký validate(T) trả Set như Jakarta Validator.

## 18. Cấu hình validation provider và messages

Spring Boot tự cấu hình validation khi provider phù hợp nằm trên classpath. Trong Spring Boot 3.5, có **ValidationConfigurationCustomizer** để chỉnh configuration của provider trước khi tạo ValidatorFactory.

Ví dụ chỉ biểu diễn điểm mở rộng:

~~~java
@Bean
ValidationConfigurationCustomizer validationCustomizer() {
    return configuration -> {
        // Thêm thiết lập của provider khi thật sự cần.
    };
}
~~~

Đây là snippet minh họa, không phải chương trình chạy độc lập. Trong Spring Boot 3.5, import thường là:

~~~java
import org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer;
~~~

Spring Boot 4 chuyển package theo module validation, ví dụ:

~~~java
import org.springframework.boot.validation.autoconfigure.ValidationConfigurationCustomizer;
~~~

Chỉ dùng khi cần tinh chỉnh provider-level behavior mà không thể giải quyết bằng message bundles, annotations hoặc một bean Validator đơn giản. Một customizer có thể được sắp xếp bằng Ordered/@Order nếu nhiều bean cùng cấu hình.

Không tự viết một @Bean LocalValidatorFactoryBean trừ khi bạn cần thay đổi chủ động và hiểu ảnh hưởng đến MVC/WebFlux/service method validation. Việc thay global validator có thể làm các endpoint có behavior khác nếu bean không hỗ trợ Jakarta constraints phù hợp.

## 19. Lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| @Valid không báo lỗi | Thiếu provider, thiếu @Valid tại integration point, hoặc controller chưa dùng đúng argument validation | Kiểm tra starter validation và test bằng invalid input |
| Không import được @NotBlank | Dùng javax thay vì jakarta, thiếu starter/API | Kiểm tra namespace và dependency tree |
| @NotNull không chặn "" | @NotNull chỉ kiểm tra null | Dùng @NotBlank nếu String bắt buộc có chữ |
| @Email vẫn chấp nhận null | Constraint định dạng thường coi null là hợp lệ | Kết hợp @NotBlank |
| @Min đặt trên String để kiểm tra độ dài | Hiểu sai type constraint | Dùng @Size hoặc @Pattern |
| DTO nested có lỗi nhưng không bị phát hiện | Thiếu @Valid cascade ở field con | Đặt @Valid và @NotNull khi cần |
| POST JSON lỗi cú pháp bị xem là validation error | Parse error xảy ra trước validation | Xử lý HttpMessageNotReadableException riêng |
| HandlerMethodValidationException không bị advice bắt | Chỉ bắt MethodArgumentNotValidException | Bổ sung handling cho method validation |
| @Validated service không chạy | Gọi self-invocation, tạo bean bằng new, final/private method, hoặc thiếu proxy | Gọi qua Spring-managed proxy, kiểm tra AOP |
| Validation group không chạy | Constraint chỉ gắn group khác Default | Dùng @Validated(group) hoặc chỉnh DTO/group |
| Một field có nhiều message | Vi phạm nhiều constraint | Trả danh sách hoặc chọn một thông báo với chính sách rõ |
| Trả toàn bộ rejectedValue trong lỗi HTTP | Rò rỉ dữ liệu người dùng | Trả mã lỗi/field an toàn, không echo dữ liệu nhạy cảm |
| 400 cho mọi lỗi service | Nhầm validation input với lỗi server/business | Chọn status theo bản chất lỗi; 500/409/422 khi phù hợp |
| @Valid ở DTO nhưng không validate trong batch process | Không có integration point | Gọi Validator.validate hoặc method validation |
| Custom ConstraintValidator chặn WebFlux event loop | Gọi JDBC/HTTP blocking trong validation | Đưa business check vào reactive service phù hợp |

Một cách kiểm tra nhanh cho controller MVC:

1. Xác nhận starter validation có trong runtime dependencies.
2. Xác nhận import jakarta.validation.* trên Spring Boot 3+/4+.
3. Xác nhận DTO có constraint thích hợp.
4. Xác nhận method argument có @Valid hoặc @Validated phù hợp.
5. Gửi request sai dữ liệu nhưng JSON đúng cú pháp.
6. Quan sát status và type exception.
7. Kiểm tra @RestControllerAdvice có xử lý đúng loại lỗi không.
8. Chạy MockMvc/WebTestClient trên các nhánh invalid, missing và boundary.

## 20. Checklist thiết kế validation production

- **Đầu vào:** Có DTO riêng cho input thay vì dùng trực tiếp JPA entity không?
- **Bắt buộc:** Có phân biệt missing, null, empty, blank và whitespace?
- **Kiểu dữ liệu:** Dùng wrapper hay primitive để nhận diện thiếu trường?
- **Giới hạn:** Có ràng buộc độ dài, phạm vi số, định dạng email/ID và collection size?
- **Nested:** Có @Valid cascade và @NotNull nếu object con bắt buộc?
- **HTTP:** Có dùng @Valid @RequestBody, kiểm tra 400 và tránh lộ thông tin nhạy cảm?
- **Method:** Có phân biệt validation trên controller và service @Validated?
- **Groups:** Có tài liệu rõ về Default vs custom groups?
- **Security:** Có business checks cho permission, authorization, rate limit và ownership?
- **Database:** Có unique/check/foreign key constraints phù hợp và xử lý conflict/transaction?
- **Internationalization:** Có messages/locale nhất quán với API contract?
- **Tests:** Có test invalid, valid, boundary, malformed JSON, nested và error response?
- **Version:** Có dùng Jakarta API và import đúng Spring Boot version?
- **Operations:** Có metric/log không chứa password, email/raw payload ngoài chính sách dữ liệu?
- **Bảo trì:** Không copy constraints khác nhau giữa HTTP, service và persistence nếu cùng một quy tắc bất biến.

## 21. Câu hỏi tự kiểm tra

1. Jakarta Validation và Hibernate Validator có vai trò khác nhau thế nào?
2. spring-boot-starter-validation cung cấp những gì và vì sao không nên tự ấn định Hibernate Validator version?
3. @NotNull, @NotEmpty và @NotBlank xử lý chuỗi "   " ra sao?
4. Vì sao @Email phải kết hợp @NotBlank nếu email bắt buộc?
5. Dùng @Size(min=3) hay @Min(3) để giới hạn độ dài String?
6. Khi nào constraint trên DTO được thực thi trong Spring MVC?
7. @Valid và @Validated khác nhau thế nào?
8. Tại sao @Valid Address không chặn address=null?
9. Với Spring Framework 6.1+, controller inline @Min trên @PathVariable có thể gây exception nào?
10. Vì sao @Validated service có thể không chạy nếu gọi this.someMethod()?
11. Một request JSON sai cú pháp có phải luôn phát MethodArgumentNotValidException không?
12. Một service có nên trả HTTP 400 khi vi phạm database unique constraint không?
13. Validator.validate trả loại kết quả nào?
14. Vì sao constraint thuộc group OnCreate có thể không chạy khi dùng @Valid đơn thuần?
15. Spring Boot 3+ dùng javax.validation hay jakarta.validation?

### Đáp án gợi ý

1. Jakarta là chuẩn API/annotation; Hibernate Validator là implementation thực thi constraints.
2. Starter cung cấp dependency/hạ tầng provider phù hợp; để Boot BOM quản lý version đảm bảo tương thích.
3. @NotNull PASS, @NotEmpty PASS, @NotBlank FAIL.
4. @Email chủ yếu kiểm tra format; không tự bảo đảm field được cung cấp và không rỗng.
5. @Size(min=3), không dùng @Min cho độ dài String.
6. Khi framework nhận DTO ở một integration point hỗ trợ, chẳng hạn @Valid @RequestBody, hoặc khi gọi Validator trực tiếp.
7. @Valid là Jakarta cascade/validation marker; @Validated là Spring extension hỗ trợ groups/method validation.
8. @Valid chỉ cascade khi object con tồn tại; dùng @NotNull nếu bắt buộc.
9. HandlerMethodValidationException với built-in method validation.
10. Self-invocation không đi qua Spring proxy thông thường.
11. Không. JSON parse error xảy ra trước Bean Validation và được báo bằng exception khác.
12. Phải diễn đạt lỗi theo hợp đồng: duplicate có thể là 409 Conflict; không tự coi mọi database error là 400.
13. Set<ConstraintViolation<T>> của Jakarta Validator.
14. Vì OnCreate không tự thuộc group Default; cần chọn group phù hợp.
15. jakarta.validation.

## 22. Tài liệu tham khảo chính thức

- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): bật method validation khi có implementation, @Validated tại bean và ValidationConfigurationCustomizer.
- [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): starter validation và thay đổi modules/test starters.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): LocalValidatorFactoryBean, tích hợp Jakarta Validation và custom constraints.
- [Spring Framework — MVC Controller Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): @Valid DTO, built-in method validation, MethodArgumentNotValidException và HandlerMethodValidationException.
- [Spring Framework — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): WebExchangeBindException và method validation trong WebFlux.
- [Spring Framework — @RequestBody MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialization và validation của request body.
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/): ràng buộc, groups, cascade, validator và constraint metadata.
- [Hibernate Validator Reference](https://docs.jboss.org/hibernate/stable/validator/reference/en-US/html_single/): built-in constraints, custom constraints, method validation và interpolation.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử validation qua HTTP với MVC.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP trên reactive stack.
