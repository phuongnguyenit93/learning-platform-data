# Kiểm thử dữ liệu sai, Problem Details và phản hồi lỗi mặc định

## 1. Mục tiêu: một API không chỉ đúng khi dữ liệu hợp lệ

Trong **Kiểm thử web runtime** của **Spring Boot - web-runtime**, một endpoint có thể hoạt động đúng ở happy path nhưng vẫn tạo trải nghiệm khó dùng hoặc nguy hiểm khi khách hàng gửi dữ liệu sai: JSON bị hỏng, sai kiểu dữ liệu, body thiếu, field trống, query vượt giới hạn, HTTP method sai, Content-Type/Accept không phù hợp hoặc một lỗi nội bộ xảy ra.

Bài học giải quyết ba câu hỏi khác nhau:

1. **Dữ liệu nào phải bị từ chối?** Phân biệt lỗi cú pháp JSON, lỗi chuyển kiểu, thiếu field/query, lỗi ràng buộc Jakarta Bean Validation, lỗi nghiệp vụ và lỗi bất ngờ phía server.
2. **HTTP response có contract gì?** Status 400/404/405/406/409/415/422/500; media type **application/problem+json**, các trường của RFC 9457; sự khác biệt so với JSON lỗi mặc định của Spring Boot.
3. **Kiểm thử tầng nào để tin kết quả?** Dùng **MockMvc/@WebMvcTest** cho MVC validation và exception advice, **@SpringBootTest(RANDOM_PORT)** cho cơ chế container error dispatch và **BasicErrorController /error**. Không suy luận default error body từ MockMvc nếu servlet container thực không chạy.

Mục tiêu đầu ra: viết được bộ negative tests có thể lặp lại, tránh assert thông điệp nội bộ dễ thay đổi, biết vì sao Problem Details không bao phủ mọi loại lỗi và không làm rò stack trace, credentials hoặc dữ liệu người dùng.

Các ví dụ dùng **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1, Spring MVC/Servlet, Jakarta Validation, JUnit Jupiter và MockMvc**. Spring WebFlux dùng mô hình WebTestClient/reactive exceptions khác; không sao chép nguyên cấu hình spring.mvc sang WebFlux.

## 2. Request lỗi đi qua các tầng nào?

~~~text
HTTP client
    |
    v
TCP / Reverse Proxy / Servlet Filters / Spring Security
    |
    v
DispatcherServlet
    |
    +--- Handler mapping: path, method, consumes, produces
    |
    +--- Parameter binding & type conversion
    |
    +--- HttpMessageConverter: đọc JSON body
    |
    +--- Jakarta Bean Validation: @Valid, @Min, @NotBlank...
    |
    +--- Controller -> service -> domain rule
    |
    v
Response / Exception
    |
    +--- @ExceptionHandler trong @RestControllerAdvice
    |
    +--- MVC HandlerExceptionResolver / Boot Problem Details advice
    |
    +--- Servlet error dispatch -> Boot /error (BasicErrorController)
    |
    v
HTTP status + Content-Type + JSON/HTML body
~~~

Đường đi **phụ thuộc loại lỗi và cấu hình**. Ví dụ một lỗi body thiếu có thể bị từ chối **trước khi Controller được gọi**. Một exception nghiệp vụ có thể được @RestControllerAdvice biến thành ProblemDetail. Một lỗi runtime bất ngờ không được xử lý có thể được chuyển qua cơ chế **/error** của Servlet container.

**Không có một quy tắc “mọi lỗi 4xx/5xx đều có cùng JSON schema” theo mặc định.** Muốn contract thống nhất, team phải chủ động thiết kế, kiểm thử và cấu hình cả những boundary nằm ngoài Controller.

## 3. Ma trận dữ liệu sai và HTTP status nên kiểm thử

| Trường hợp | Nơi phát hiện thường gặp | Status thường phù hợp |
| --- | --- | --- |
| Body là JSON hỏng cú pháp | Jackson/HttpMessageConverter | 400 Bad Request |
| JSON đúng cú pháp nhưng age là chuỗi không chuyển thành Integer | Jackson deserialization/type mismatch | 400 |
| Thiếu body bắt buộc với @RequestBody | Request body resolver | 400 |
| @NotBlank, @Email, @Min không đạt trên @Valid DTO | Bean Validation | 400 trong Spring MVC mặc định |
| Query @RequestParam bắt buộc bị thiếu | Argument resolver | 400 |
| @RequestParam/@PathVariable không chuyển được kiểu | Type conversion/binding | 400 |
| Constraint trực tiếp @Min/@Max trên method parameter | Method validation | 400 cho input |
| Route không tồn tại | Handler mapping/static resource | 404 Not Found |
| Tài nguyên ID hợp lệ nhưng không tìm thấy | Domain/service | 404 theo API contract |
| HTTP method không được hỗ trợ | Handler mapping | 405 Method Not Allowed |
| Client yêu cầu Accept media type không thể đáp ứng | Content negotiation | 406 Not Acceptable |
| Request Content-Type không được hỗ trợ | Consumes condition/converter | 415 Unsupported Media Type |
| Email đã dùng hoặc xung đột trạng thái | Domain rule | 409 Conflict |
| Payload đúng cú pháp nhưng không xử lý được theo quy tắc domain | Thiết kế API riêng | Có thể 422 Unprocessable Content |
| Thiếu/không hợp lệ thông tin xác thực | Spring Security filter/entry point | 401 Unauthorized |
| Đã xác thực nhưng không được phép | AccessDeniedHandler/method security | 403 Forbidden |
| Exception bất ngờ, bug, database unavailable không được map | Server error | 500 hoặc mã 5xx phù hợp |
| Gateway timeout khi gọi service | Reverse proxy | 504 Gateway Timeout |

**Không tự mặc định mọi Bean Validation failure là 422.** Với Spring MVC, @Valid request DTO lỗi thông thường trả **400**. Chỉ chọn 422 nếu API contract thực sự phân biệt lỗi “nội dung đúng cú pháp nhưng không thể xử lý” và có exception mapping riêng.

**Không tự biến mọi lỗi runtime thành HTTP 400.** Lỗi do server phải là 5xx và không để client tin có thể sửa payload để khắc phục. Ngược lại lỗi input người dùng không nên bị ghi thành 500 chỉ vì exception handler thiếu.

### 3.1. HTTP status và body là hai khía cạnh độc lập

Một response có thể trả **HTTP 400** nhưng body là JSON mặc định của Boot, ProblemDetail JSON, HTML hoặc body rỗng, tùy stack và negotiation. Kiểm thử phải assert:
- Status đúng.
- Content-Type đúng cho API contract.
- Các field ổn định, đặc biệt **status, type, code** khi có.
- Dữ liệu nhạy cảm không xuất hiện.
- Client phân biệt được lỗi có thể sửa/retry và lỗi không nên retry.

Không chỉ viết **andExpect(status().isBadRequest())** rồi cho rằng error payload cũng đã đúng.

## 4. Jakarta Bean Validation: những annotation cần dùng đúng

Để dùng Jakarta Bean Validation trong Spring Boot 3.3, thêm dependency **spring-boot-starter-validation**. Đừng nghĩ starter-web luôn cung cấp Hibernate Validator đầy đủ cho mọi phiên bản.

Các annotation thường gặp:
- **@NotNull:** giá trị không được null; không cấm chuỗi rỗng.
- **@NotBlank:** CharSequence không null và có ít nhất một ký tự không phải khoảng trắng; hợp tên/email.
- **@NotEmpty:** không null/rỗng đối với String/Collection/Map/Array; khác NotBlank.
- **@Email:** kiểm định dạng email theo validator; có thể cho null, nên kết hợp @NotBlank khi bắt buộc.
- **@Size(min,max):** độ dài String/kích thước Collection, không phải giới hạn số nguyên.
- **@Min/@Max:** giới hạn giá trị số, không áp lên String như thay thế @Size.
- **@Positive/@PositiveOrZero:** giá trị số theo điều kiện dấu.
- **@Pattern:** regex cho String; cần kiểm chính sách, không dùng regex phức tạp gây ReDoS.
- **@Valid:** yêu cầu validate đối tượng/nested fields; bản thân @Valid không phải constraint.
- **@Validated:** hỗ trợ validation groups và một số mô hình method validation; không luôn cần đặt trên MVC Controller.

Trong Spring Framework 6.1, có hai đường validation quan trọng:
1. **MethodArgumentNotValidException:** thường gặp khi **@Valid @RequestBody DTO** hoặc @ModelAttribute/@RequestPart sai constraints và không có BindingResult/Errors ngay sau parameter.
2. **HandlerMethodValidationException:** thường gặp khi có constraint **đặt trực tiếp trên method parameters** như @Min @RequestParam hoặc @Min @PathVariable; Spring MVC built-in method validation kiểm cả method signature.

**Lưu ý dễ sai:** nếu đặt **@Validated trên class Controller**, validation có thể đi qua AOP method-validation proxy thay vì cơ chế built-in của MVC 6.1. Theo tài liệu Spring Framework, muốn dùng MVC 6.1 built-in method validation thì **bỏ class-level @Validated** khi không cần. Exception thực tế có thể khác theo cách cấu hình; kiểm thử đúng dự án thật.

### 4.1. Mất dữ liệu ngay ở bước deserialize

JSON như:

~~~json
{"fullName":"Ada","email":"ada@example.test","age":"not-a-number"}
~~~

có thể lỗi trước Bean Validation, vì Jackson không chuyển **not-a-number** sang Integer. Không kỳ vọng luôn có FieldError từ @Min cho trường hợp này. HTTP message conversion có thể ném **HttpMessageNotReadableException**, cần test riêng.

Nếu JSON body thiếu hẳn, @RequestBody mặc định **required=true** cũng có thể làm HTTP 400 trước Controller. Nếu DTO field age bị null nhưng JSON vẫn hợp lệ, khi có **@NotNull** nó sẽ bị Bean Validation bắt.

### 4.2. BindingResult có thể thay đường xử lý lỗi

Một Controller nhận **@Valid @RequestBody DTO dto, BindingResult errors** ngay sau DTO có thể tự xử lý errors, không mặc định ném MethodArgumentNotValidException theo mô hình trên. Nếu dùng, phải kiểm tra errors.hasErrors() và tự trả HTTP status/body đúng. Đừng thêm BindingResult rồi bỏ qua errors, khiến payload sai tiếp tục vào business logic.

## 5. RFC 9457 Problem Details là gì?

**Problem Details for HTTP APIs (RFC 9457)** cung cấp một representation chuẩn cho lỗi HTTP. Spring Framework có **org.springframework.http.ProblemDetail** và **org.springframework.web.ErrorResponse**.

Một ví dụ **application/problem+json**:

~~~json
{
  "type": "https://errors.example.test/problems/invalid-input",
  "title": "Invalid input",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/accounts",
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field":"age","constraint":"Min"},
    {"field":"email","constraint":"Email"}
  ]
}
~~~

Năm trường chuẩn:
- **type:** URI định danh loại lỗi; mặc định thường là **about:blank**. Nếu dùng custom type URI nên ổn định, tốt nhất có tài liệu giải thích contract.
- **title:** tên ngắn mô tả *loại lỗi*, không phải stack trace.
- **status:** HTTP status code liên quan đến occurrence.
- **detail:** mô tả dành cho client, không chứa SQL, secrets hay nội dung exception nội bộ.
- **instance:** URI xác định occurrence/path; Spring MVC có thể suy ra từ request path khi không set.

**code** và **violations** là **extension fields**, không phải năm trường bắt buộc của RFC. Spring hỗ trợ **ProblemDetail.setProperty(...)** và Jackson có mixin để đưa các properties này lên top-level JSON. Client nên dùng **type hoặc code ổn định**, không parse câu chữ của detail.

**application/problem+json** khác **application/json** về media type và ý nghĩa. Khi test ProblemDetail, có thể dùng **contentTypeCompatibleWith(application/problem+json)** thay vì giả định thêm charset/thứ tự params cố định.

### 5.1. HTTP status phải khớp ProblemDetail.status

**ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ...)** tạo body có status 400. Khi Spring MVC trả ProblemDetail từ @ExceptionHandler, framework dùng status đó cho response theo support. Tránh tạo body có status 400 trong khi response thực là 500, khiến clients, metrics và caches diễn giải sai.

### 5.2. Không lạm dụng extension fields

Một số field mở rộng hữu ích:
- **code:** machine-readable, ví dụ EMAIL_CONFLICT hoặc INVALID_JSON.
- **violations:** danh sách field/constraint names được lọc và chuẩn hóa, giới hạn số lượng.
- **traceId:** correlation ID không phải credential, có thể dùng khi chính sách cho phép.

Không phản chiếu **rejectedValue** của người dùng trong response một cách mặc định: password, refresh token, địa chỉ, số tài khoản hoặc HTML/JSON lớn có thể bị leak qua lỗi. Không trả raw exception message, class name, stack trace hoặc database diagnostics.

### 5.3. Không mặc định 404/500 luôn là Problem Details

**ProblemDetail** là một cách biểu diễn lỗi, không phải cam kết mọi nguồn lỗi của ứng dụng đều dùng nó. Một response do MVC exception resolver tạo có thể là ProblemDetail, trong khi một lỗi không được bắt có thể đi qua **BasicErrorController /error** và nhận JSON mặc định. Hệ thống cũng có thể trả HTML khi client gửi Accept: text/html.

Muốn API có schema duy nhất trên tất cả boundary (bao gồm security filters, proxy errors), cần kiến trúc/error handlers riêng và kiểm thử ở HTTP level.

## 6. Spring Boot 3.3: bật Problem Details và phân biệt /error

Trong Spring Boot 3.3, property:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

bật auto-configuration hỗ trợ RFC 9457 cho nhiều **Spring MVC ErrorResponse exceptions**. **Giá trị mặc định của spring.mvc.problemdetails.enabled trong Spring Boot 3.3.13 là false.** Không được giả định dự án mới có Problem Details theo mặc định.

Spring Boot cung cấp cơ chế lỗi Servlet mặc định:
- **/error** là mapping được dùng khi container dispatch lỗi.
- **BasicErrorController** thường trả JSON cho machine clients và error HTML/whitelabel cho browser clients.
- **ErrorAttributes** xác định những dữ liệu được đưa ra body.
- Các cấu hình **server.error.*** giới hạn trường message, binding errors, exception và stack trace.

### 6.1. Ví dụ phản hồi /error mặc định

Khi request dẫn tới BasicErrorController với HTTP 404/500, JSON có thể có dạng:

~~~json
{
  "timestamp": "2026-01-01T00:00:00.000+00:00",
  "status": 404,
  "error": "Not Found",
  "path": "/does-not-exist"
}
~~~

Đây là **mẫu minh họa**, không phải JSON exact output của mọi request. Timestamp thay đổi; content negotiation, các error properties và phiên bản Spring Boot có thể làm field set khác.

### 6.2. Kiểm soát dữ liệu nhạy cảm trong default error

Với Spring Boot 3.3:

~~~yaml
server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
    include-path: always
~~~

Các defaults của phiên bản 3.3 tương ứng **include-message=never**, **include-binding-errors=never**, **include-stacktrace=never**, **include-exception=false**, **include-path=always**; lab khai báo lại để mục đích rõ ràng. **Không bật always cho message/stacktrace chỉ để test tiện**, nhất là production. Nếu một môi trường phát raw exception ra JSON, đó là vấn đề bảo mật.

**server.error.path** mặc định là **/error**. Không gọi endpoint đó trực tiếp rồi kết luận sẽ tái hiện một Servlet error dispatch với đầy đủ request attributes; cần một lỗi thật phát sinh qua container.

### 6.3. Không xem /error và @RestControllerAdvice là cùng tầng

**@RestControllerAdvice** xử lý exceptions đi qua MVC exception resolution. **BasicErrorController** được dùng bởi Servlet error dispatch hoặc lỗi chưa được xử lý ở MVC level. Một **@ExceptionHandler(Exception.class)** quá rộng có thể che /error và biến toàn bộ errors thành một JSON chung, kể cả lỗi bất ngờ; nếu viết sai sẽ làm 500 bị biến thành 400.

**Spring Security** có exception handlers trong filter chain (AuthenticationEntryPoint, AccessDeniedHandler). @RestControllerAdvice không tự bắt mọi 401/403 từ filter vì nhiều lỗi xảy ra **trước DispatcherServlet**.

## 7. Quy tắc 404 và static resources trong Spring Boot 3.3

Một khác biệt quan trọng khi test 404: **Spring Boot thường map static resources tới /**. Với request route không tồn tại, HandlerMapping có thể chọn **ResourceHttpRequestHandler**, sau đó ném **NoResourceFoundException** thay vì **NoHandlerFoundException**.

Theo tài liệu Boot 3.3, nếu muốn 404 từ route không tìm thấy đi qua **NoHandlerFoundException**, có thể:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

Cấu hình này **tắt phục vụ static resources tự động**. Chỉ dùng nếu ứng dụng là API thuần không phục vụ static files, như lab. Nếu app còn frontend assets, swagger UI hay static content, đừng bật tùy tiện chỉ để thay đổi exception class.

Cần test **HTTP 404 status và error contract**, không khóa mọi test vào một exception type, vì static mapping/configuration có thể thay đổi. Đặc biệt, **MockMvc không thực thi servlet container error page dispatch như server thật**.

## 8. Chiến lược kiểm thử: các tầng cần bao phủ

| Loại kiểm thử | Công cụ | Cái kiểm tốt | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Unit validator/service | JUnit, Validator | Business rule, constraints | Không có HTTP status/body/mapping |
| MVC slice | @WebMvcTest + MockMvc | Routing, JSON parse, validation, exception advice | Không mở embedded HTTP server |
| MVC full context mocked | @SpringBootTest + @AutoConfigureMockMvc | MVC pipeline với nhiều beans thật | Vẫn không có servlet container network/error-page thật |
| HTTP integration | @SpringBootTest(RANDOM_PORT) + TestRestTemplate | Tomcat, serialization, /error, actual status/headers | Chậm hơn slice, dùng random port |
| End-to-end | Real client qua gateway | CORS, Security, ingress, proxy mapping | Phụ thuộc môi trường, cần isolate test data |
| Contract testing | Consumer/provider contract | Type/status/schema ổn định giữa services | Cần agreement và versioning |

**Khuyến nghị:** dùng nhiều MVC slice tests cho các input permutations; thêm một số integration tests kiểm hành vi mặc định của **/error** và container; thêm security tests nếu dự án có AuthenticationEntryPoint/AccessDeniedHandler; chỉ dùng full E2E cho những ranh giới quan trọng.

### 8.1. Test những gì, không test những gì?

Tốt:
- HTTP status, media type và machine-readable code/type.
- Có field violation cho input invalid, không leak raw input.
- Invalid input không gọi service/save (với mocked collaborator).
- HTTP 500 không lộ message/stack trace.
- Missing route, wrong method, unsupported Content-Type và Accept.
- 401/403 được xử lý ở đúng security boundary.
- Errors giống nhau giữa các môi trường/configurations quan trọng.

Tránh:
- Assert cả timestamp cố định.
- Assert thứ tự JSON fields hoặc thứ tự các field errors không có hợp đồng.
- Assert raw text của default exception detail vốn phụ thuộc locale/phiên bản.
- Dùng @WebMvcTest để tuyên bố đã test đủ embedded servlet container /error.
- Cấu hình server.error.include-stacktrace=always để snapshot test “dễ hơn”.

## 9. Demo Maven Java 17 chạy được: một API và hai đường trả lỗi

Demo cố tình có:
- **POST /api/accounts** nhận **@Valid @RequestBody**.
- **GET /api/accounts/{id}** dùng **@Min** trên path parameter, minh họa HandlerMethodValidationException.
- **GET /api/accounts/search?q=...&limit=...** dùng required query và @Min/@Max.
- Custom domain 404 và 409, trả **ProblemDetail** có code ổn định.
- @RestControllerAdvice xử lý **MethodArgumentNotValidException** và **HttpMessageNotReadableException** thành ProblemDetail không lộ input.
- **GET /api/boom** ném exception bất ngờ không có custom handler; test real HTTP để quan sát cơ chế **/error** của Spring Boot.

Không dùng database để bài tập trung vào web runtime. Không tạo tài khoản thực; id 42 và dữ liệu sample chỉ để kiểm HTTP contract.

### 9.1. Cấu trúc thư mục

~~~text
invalid-input-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/errorlab/
    │   │   └── ErrorLabApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/errorlab/
            ├── AccountMvcTest.java
            ├── DefaultErrorHttpTest.java
            └── LegacyDefaultErrorHttpTest.java
~~~

### 9.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>invalid-input-lab</artifactId>
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
~~~

**spring-boot-starter-validation** là điểm bắt buộc để ràng buộc @NotBlank/@Email/@Min hoạt động như dự kiến. **spring-boot-starter-test** đưa JUnit Jupiter, MockMvc/Spring Test, AssertJ, Hamcrest theo dependency management của Boot.

### 9.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
    include-path: always

spring:
  mvc:
    problemdetails:
      enabled: true
  web:
    resources:
      add-mappings: false
~~~

Cấu hình chọn **Problem Details cho MVC framework exceptions** trong mode chính của lab, giữ **/error** an toàn, và tắt static mappings để route missing có một đường xử lý dễ suy luận. Đây là lab API thuần, không dùng static assets.

**Để quan sát mode mặc định khi chưa bật Problem Details**, test cuối đặt property override **spring.mvc.problemdetails.enabled=false** trên context thử riêng. Không chỉnh application.yml của test khác.

### 9.4. Một Java file chứa app, DTOs, controllers và advice

**src/main/java/com/example/errorlab/ErrorLabApplication.java:**

~~~java
package com.example.errorlab;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class ErrorLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorLabApplication.class, args);
    }
}

record CreateAccountRequest(
        @NotBlank @Size(max = 40) String fullName,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {}

record AccountResponse(long id, String fullName, String email, int age) {}

class DuplicateEmailException extends RuntimeException {}

class AccountNotFoundException extends RuntimeException {}

@RestController
@RequestMapping("/api/accounts")
class AccountController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<AccountResponse> create(
            @Valid @RequestBody CreateAccountRequest request
    ) {
        if ("taken@example.test".equalsIgnoreCase(request.email())) {
            throw new DuplicateEmailException();
        }

        AccountResponse response = new AccountResponse(
                42L, request.fullName(), request.email(), request.age()
        );
        return ResponseEntity
                .created(URI.create("/api/accounts/42"))
                .body(response);
    }

    @GetMapping(
        path = "/search",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Map<String, Object> search(
            @RequestParam("q") String q,
            @RequestParam("limit") @Min(1) @Max(50) int limit
    ) {
        return Map.of("q", q, "limit", limit);
    }

    // Không dùng class-level @Validated: MVC 6.1 có method validation.
    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    AccountResponse get(@PathVariable("id") @Min(1) long id) {
        if (id != 42L) {
            throw new AccountNotFoundException();
        }
        return new AccountResponse(
                42L, "Ada", "ada@example.test", 23
        );
    }
}

@RestController
class UnhandledFailureController {
    @GetMapping("/api/boom")
    String boom() {
        throw new IllegalStateException("internal diagnostic - do not expose");
    }
}

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class ApiProblemAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail onBodyValidation(MethodArgumentNotValidException ex) {
        ProblemDetail p = problem(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                "Invalid input",
                "One or more request fields are invalid.",
                "invalid-input"
        );

        List<Map<String, String>> issues =
                ex.getBindingResult().getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "constraint",
                            error.getCode() == null
                                ? "INVALID" : error.getCode()
                    ))
                    .sorted(Comparator.comparing(m -> m.get("field")))
                    .toList();

        // Chỉ cho biết field và constraint; không echo rejectedValue.
        p.setProperty("violations", issues);
        return p;
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail onUnreadableJson(
            HttpMessageNotReadableException ex
    ) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "INVALID_JSON",
                "Invalid JSON",
                "Request body is missing or cannot be read as JSON.",
                "invalid-json"
        );
    }

    @ExceptionHandler(DuplicateEmailException.class)
    ProblemDetail onDuplicate(DuplicateEmailException ex) {
        return problem(
                HttpStatus.CONFLICT,
                "EMAIL_CONFLICT",
                "Email conflict",
                "An account with this email already exists.",
                "email-conflict"
        );
    }

    @ExceptionHandler(AccountNotFoundException.class)
    ProblemDetail onMissing(AccountNotFoundException ex) {
        return problem(
                HttpStatus.NOT_FOUND,
                "ACCOUNT_NOT_FOUND",
                "Account not found",
                "The requested account is not available.",
                "account-not-found"
        );
    }

    private static ProblemDetail problem(
            HttpStatus status,
            String code,
            String title,
            String detail,
            String typeSlug
    ) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(status, detail);
        p.setTitle(title);
        p.setType(URI.create(
                "https://errors.example.test/problems/" + typeSlug
        ));
        p.setProperty("code", code);
        return p;
    }
}
~~~

### 9.5. Giải thích điểm cốt lõi của code

1. **CreateAccountRequest** là Java record, ba field fullName/email/age có Jakarta Validation constraints. **@Valid @RequestBody** làm MVC validate sau khi JSON deserialize thành DTO.
2. **age là Integer + @NotNull @Min(18)**: null/missing field bị validation; chuỗi không thể chuyển Integer bị Jackson xử lý trước và đi theo lỗi JSON.
3. **@Email** không bảo đảm địa chỉ tồn tại, có thể chấp nhận null theo validator; @NotBlank làm email bắt buộc.
4. **@Min/@Max** trực tiếp trên search limit và path id kích hoạt **MVC 6.1 method validation**; khi input không hợp lệ có thể ném **HandlerMethodValidationException** được Boot Problem Details resolver xử lý nếu bật.
5. **POST /api/accounts** trả 201 và Location /api/accounts/42 khi hợp lệ; đây là lab, không có database và không tạo record lâu dài.
6. **Email taken@example.test** tạo lỗi nghiệp vụ 409. Một email khác hợp lệ trả 201 trong lab.
7. **GET /api/accounts/42** thành công; GET một ID dương khác 42 trả ProblemDetail domain 404; GET /api/accounts/abc lỗi chuyển kiểu 400.
8. **GET /api/accounts/search** phải có q và limit; limit=0 hoặc 51 kích hoạt method constraint.
9. **@RestControllerAdvice @Order(HIGHEST_PRECEDENCE)** ưu tiên các exception handlers được định nghĩa rõ trước Boot Problem Details advice cho MVC built-in exceptions. Không catch Exception.class, nên lỗi runtime bất ngờ vẫn có thể đi qua /error.
10. **onBodyValidation** chỉ trả field/constraint code, **không echo rejectedValue**. Danh sách được sort theo tên field để dễ kiểm contract; tùy annotations và Hibernate Validator có thể có nhiều violations trên một field.
11. **onUnreadableJson** không trả raw Jackson exception, vị trí byte lỗi hoặc field chứa secret.
12. **ProblemDetail.setProperty("code", ...)** tạo extension machine-readable. Type URIs dùng domain **example.test** chỉ để minh họa, không phải địa chỉ production thực.
13. **UnhandledFailureController** cố tình ném IllegalStateException để test cơ chế lỗi mặc định và bảo mật của /error. Không copy endpoint /api/boom vào ứng dụng thật.
14. Không có Spring Security trong pom.xml để tránh thay đổi ý nghĩa negative tests; sau này nếu bổ sung security, phải kiểm riêng filter 401/403.

**Bảo mật:** không nên đưa fullName/email trong default exception message hoặc log công khai; các giá trị được dùng trong response happy path chỉ nhằm minh họa. Production cần input size limits, redaction, audit, masking và data protection.

## 10. MockMvc slice test: kiểm dữ liệu sai và Problem Details

**src/test/java/com/example/errorlab/AccountMvcTest.java:**

~~~java
package com.example.errorlab;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(
        controllers = AccountController.class,
        properties = "spring.mvc.problemdetails.enabled=true"
)
class AccountMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validPostCreatesResource() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"fullName":"Ada",
                     "email":"ada@example.test",
                     "age":23}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "Location", "/api/accounts/42"
            ))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.fullName").value("Ada"));
    }

    @Test
    void invalidFieldsUseSafeProblemDetail() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("""
                    {"fullName":" ",
                     "email":"not-an-email",
                     "age":16}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")
            ))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[*].field",
                    hasItems("fullName", "email", "age")));
    }

    @Test
    void malformedJsonIsNotBeanValidation() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("{broken"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void missingRequiredBodyIsAlsoAClientError() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void jsonTypeMismatchIsNotAFieldConstraintError()
            throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("""
                    {"fullName":"Ada",
                     "email":"ada@example.test",
                     "age":"not-a-number"}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void duplicateEmailHasBusinessConflictCode() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("""
                    {"fullName":"Ada",
                     "email":"taken@example.test",
                     "age":23}
                    """))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")
            ))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code").value("EMAIL_CONFLICT"));
    }

    @Test
    void unknownAccountReturnsDomainNotFound() throws Exception {
        mvc.perform(get("/api/accounts/99")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code")
                    .value("ACCOUNT_NOT_FOUND"));
    }

    @Test
    void pathVariableTypeMismatchReturns400() throws Exception {
        mvc.perform(get("/api/accounts/not-a-number")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void pathConstraintReturns400() throws Exception {
        mvc.perform(get("/api/accounts/0")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredQueryReturns400() throws Exception {
        mvc.perform(get("/api/accounts/search")
                .param("limit", "10")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void queryConstraintReturns400() throws Exception {
        mvc.perform(get("/api/accounts/search")
                .param("q", "ada")
                .param("limit", "0")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.TEXT_PLAIN)
                .content("not JSON"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void wrongHttpMethodReturns405() throws Exception {
        mvc.perform(put("/api/accounts/42"))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void unrepresentableAcceptReturns406() throws Exception {
        mvc.perform(get("/api/accounts/42")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }
}
~~~

### 10.1. Test đang xác minh điều gì?

- **201 validPost**: baseline cho thấy Controller, Jackson và DTO chạy đúng. Nếu happy path hỏng, negative tests khó được tin.
- **400 invalidFields**: MethodArgumentNotValidException được advice chuyển thành ProblemDetail với **VALIDATION_FAILED**, top-level field violations không lộ rejected values.
- **400 malformed/missing/type mismatch**: lỗi HTTP message conversion được xử lý khác Bean Validation; client biết cần sửa JSON/body chứ không phải business rule.
- **409 conflict**: lỗi nghiệp vụ có code khác 400 và không phải 500.
- **404 domain not found**: ID hợp lệ nhưng tài nguyên không có; khác route không tồn tại.
- **400 path type/constraint**: type conversion khác validation trực tiếp trên method signature.
- **400 missing query/limit=0**: kiểm @RequestParam required và @Min.
- **415**: Content-Type request không khớp consumes.
- **405**: path có route nhưng HTTP method không được cho phép.
- **406**: Accept không có representation được endpoint hỗ trợ.

**Không assert nguyên câu default detail của Spring** ở 405/406/param errors. Bản dịch, message source, Java runtime và Spring minor version có thể khác; các tests trên ưu tiên status ổn định. Với lỗi do ứng dụng tự định nghĩa, code là API contract và được assert tường minh.

### 10.2. Vì sao dùng contentTypeCompatibleWith?

Media type của ProblemDetail là **application/problem+json**; có thể đi kèm các parameters và do content negotiation quyết định. **contentTypeCompatibleWith** kiểm loại media tương thích mà không khóa chi tiết serialization không cần thiết. Không so sánh raw JSON string vì thứ tự properties, whitespace và URI instance có thể thay đổi.

### 10.3. @WebMvcTest tự mang những gì?

Spring Boot 3.3 **@WebMvcTest(AccountController.class)** chỉ dựng MVC slice, bao gồm MVC infrastructure, Jackson/validation hỗ trợ và các **@ControllerAdvice** phù hợp; không tự dựng toàn bộ repositories, external clients hay dịch vụ ngoài slice. Vì Controller của lab không có dependency service, không cần @MockBean.

Trong dự án thật, nếu AccountController inject AccountService, dùng **@MockBean AccountService** theo Boot 3.3 hoặc cấu hình collaborator tương thích. Nếu security starter tồn tại, @WebMvcTest thường đưa các security filters vào context; tests có thể nhận 401/403 trước khi tới Controller. Hãy dùng Spring Security Test @WithMockUser/csrf() khi policy yêu cầu thay vì tắt filters tùy tiện.

### 10.4. Một test invalid body nên bảo đảm service không bị gọi

Với Controller có service mock, assert sau request invalid:

~~~java
// Fragment trong @WebMvcTest đã @MockBean AccountService service.
// Cần Mockito.verifyNoInteractions và mock được inject.
mvc.perform(post("/api/accounts")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{broken"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(service);
~~~

Đây là **fragment**, không phải chương trình độc lập. Nó chứng minh Controller không gửi payload sai xuống service. Nếu đã có authentication filters, cần account/CSRF đúng để negative test thật sự chạm validation layer.

## 11. Real HTTP integration test: đường /error khi exception không được xử lý

Theo tài liệu Spring Boot, **MockMvc không khởi chạy embedded Servlet container**, vì vậy không trực tiếp tái hiện mọi hành vi error page dispatch. Khi muốn xác minh body do **BasicErrorController /error** tạo, dùng HTTP server thật với **@SpringBootTest(webEnvironment=RANDOM_PORT)**.

**src/test/java/com/example/errorlab/DefaultErrorHttpTest.java:**

~~~java
package com.example.errorlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DefaultErrorHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void unexpectedFailureUsesSafeDefaultError() {
        ResponseEntity<Map> response =
                http.getForEntity("/api/boom", Map.class);

        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR,
                response.getStatusCode());

        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(500, ((Number) body.get("status")).intValue());
        assertEquals("/api/boom", body.get("path"));

        // Không leak error detail của IllegalStateException.
        assertFalse(body.containsKey("trace"));
        assertFalse(body.containsKey("exception"));
        assertFalse(body.containsKey("message"));
        assertFalse(body.toString().contains(
                "internal diagnostic - do not expose"
        ));
    }
}
~~~

### 11.1. Vì sao HTTP 500 vẫn có JSON mặc định dù bật Problem Details?

Trong mode demo, custom advice **không có handler cho IllegalStateException**, còn Spring Boot Problem Details auto-handler chủ yếu xử lý các **MVC ErrorResponse exceptions**. Exception runtime bất ngờ không được catch có thể đi qua container /error và được BasicErrorController biểu diễn thành JSON có **timestamp/status/error/path**.

Điều đó chứng minh **bật spring.mvc.problemdetails.enabled=true không phải “công tắc biến tất cả lỗi 500 thành problem+json”**.

Test không assert timestamp hay class name. Nó kiểm **HTTP 500**, **status 500**, **path** và **không rò** trace/exception/message. Cần chạy trên real server để tin kết quả /error.

### 11.2. Real server không đồng nghĩa cả môi trường production

RANDOM_PORT mở embedded HTTP server cục bộ, nhưng chưa đi qua reverse proxy, gateway, authentication provider hay WAF của production. Đây là **integration test**, không phải E2E. Khi triển khai cần test thêm proxy rewrites, error page mapping và security-specific failures.

## 12. Test chế độ Boot mặc định khi tắt Problem Details

Để so sánh **default /error** với **ProblemDetail**, tạo test có context riêng tắt property.

**src/test/java/com/example/errorlab/LegacyDefaultErrorHttpTest.java:**

~~~java
package com.example.errorlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.mvc.problemdetails.enabled=false"
)
class LegacyDefaultErrorHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void unmatchedRouteUsesBootDefaultErrorJson() {
        ResponseEntity<Map> response =
                http.getForEntity("/does-not-exist", Map.class);

        assertEquals(HttpStatus.NOT_FOUND,
                response.getStatusCode());
        assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(
                response.getHeaders().getContentType()
        ));

        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(404, ((Number) body.get("status")).intValue());
        assertEquals("/does-not-exist", body.get("path"));
    }
}
~~~

**Điểm khác nhau:**
- Test này tắt **spring.mvc.problemdetails.enabled**; **spring.web.resources.add-mappings=false** vẫn được đọc từ application.yml.
- Khi GET route không tồn tại, MVC/container có thể dispatch error tới **/error**, nhận JSON cơ bản với **status/path** thay vì mặc định problem+json.
- **AccountMvcTest** trong mode Problem Details kiểm những errors được advice và Boot MVC xử lý.
- **DefaultErrorHttpTest** trong mode enabled=true chứng minh một unhandled 500 vẫn có thể rơi vào /error.

Không dựa vào việc gọi **GET /error** trực tiếp, vì Servlet error attributes khi đó không giống một dispatch lỗi thật.

### 12.1. Tại sao không assert JSON default có trường message?

Spring Boot 3.3 property **server.error.include-message=never** làm trường message **không được mặc định đưa ra**. Một vài nguồn ngoài có thể mô tả /error trả exception message, nhưng cấu hình và version mới quyết định field set thực. Kiểm status/path là chắc hơn và bảo vệ thông tin nhạy cảm.

### 12.2. Điều gì xảy ra khi test chạy dưới môi trường khác?

Profile local/test có thể override:
- spring.mvc.problemdetails.enabled.
- server.error.include-*.
- spring.web.resources.add-mappings.
- security filters hoặc custom ControllerAdvice.
- custom ErrorController và error page resolver.

Trong CI nên chạy tests với config cố định hoặc property override để bảo đảm contract được kiểm đúng mode. Nếu test cần so sánh hai mode, tách context/classes như demo; không đổi một System property toàn JVM giữa các tests để tránh thứ tự phụ thuộc.

## 13. Chạy ứng dụng và thực hiện curl negative tests

Tại root **invalid-input-lab**, cần JDK 17+, Maven và port 8080 còn trống:

~~~bash
mvn test
mvn package
java -jar target/invalid-input-lab-1.0.0.jar
~~~

JUnit tests phải bao phủ một MVC slice và hai real server contexts. Nếu một test thất bại vì context/security/profile khác, đọc stack trace/test report để sửa đúng nguyên nhân, không chuyển sang @AutoConfigureMockMvc(addFilters=false) chỉ để xanh test.

Trong terminal khác:

**Valid request:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"fullName":"Ada","email":"ada@example.test","age":23}'
~~~

Kỳ vọng status **201 Created**, Location **/api/accounts/42**, body có id=42.

**Vi phạm @Valid DTO:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"fullName":" ","email":"not-an-email","age":16}'
~~~

Kỳ vọng status **400**, content type **application/problem+json**, code **VALIDATION_FAILED** và violations chứa các field **fullName, email, age**. Thứ tự violations đã được sort theo field trong advice, nhưng thứ tự các JSON keys vẫn không cần cố định.

**JSON hỏng:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{broken'
~~~

Kỳ vọng status **400**, code **INVALID_JSON**.

**Lỗi nghiệp vụ email trùng:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"fullName":"Ada","email":"taken@example.test","age":23}'
~~~

Kỳ vọng **409 Conflict**, code **EMAIL_CONFLICT**.

**Method/Media Type:**

~~~bash
curl -i -X PUT http://localhost:8080/api/accounts/42
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: text/plain" -d "wrong"
curl -i -H "Accept: application/xml" \
  http://localhost:8080/api/accounts/42
~~~

Kỳ vọng lần lượt **405**, **415**, **406**. Body có thể rỗng hoặc ProblemDetail tùy content negotiation/exception resolver; không hứa cả ba đều chứa một JSON giống nhau.

**500 bất ngờ:**

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/boom
~~~

Kỳ vọng status **500**. Trong demo cấu hình an toàn, response không chứa **internal diagnostic - do not expose** hoặc Java stack trace; hình thức có thể là JSON mặc định từ /error.

### 13.1. Các lệnh trên phù hợp Bash/Linux/macOS

Trong PowerShell Windows, dùng **curl.exe** thay cho alias curl để tránh nhầm cú pháp. JSON quoting giữa PowerShell và Bash khác nhau; kiểm HTTP status và content-type thay vì copy nguyên một command Bash có single-quote vào shell khác rồi coi lỗi quoting là lỗi Spring.

Một cách đơn giản trong PowerShell:

~~~powershell
$payload = @{ fullName = "Ada"; email = "ada@example.test"; age = 23 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/accounts" -ContentType "application/json" -Body $payload
~~~

Command trên minh họa happy path; với 4xx/5xx, PowerShell Invoke-RestMethod có thể phát exception, cần đọc HTTP response của exception thay vì kỳ vọng in body tự động.

## 14. Ma trận kiểm thử dữ liệu sai đầy đủ cho dự án thật

Bộ test từ ví dụ là nền tảng; API production còn cần xét các chiều sau:

| Nhóm test | Input tiêu biểu | Điều nên assert |
| --- | --- | --- |
| Missing body | Body trống với @RequestBody required | 400 + code phù hợp |
| Malformed JSON | Thiếu dấu ngoặc, JSON không hợp lệ | 400, không leak parser details |
| Wrong JSON type | Age="abc", object thay scalar | 400, không gọi service |
| Missing fields | age=null hoặc không có | 400, field violations |
| Blank strings | fullName="   " | 400 @NotBlank |
| Boundary numeric | age=17 / age=18 | 400 vs 201 |
| Upper bound | @Size(max=40) với 40/41 ký tự | Phân biệt biên đúng |
| Nested DTO | @Valid trên child object | Nested violations |
| Collection size | Danh sách hàng trăm/ngàn phần tử | Không OOM, policy rõ |
| Unknown JSON fields | Trường không được định nghĩa | Phụ thuộc Jackson config/API contract |
| Duplicate/conflict | Dữ liệu đã tồn tại | 409 domain code |
| Missing query | q không có | 400 |
| Empty query | q= | Có cần @NotBlank trực tiếp không? |
| Invalid path variable | /accounts/abc, /accounts/0 | 400 theo conversion/constraint |
| Method not allowed | PUT vào GET-only path | 405 |
| Unsupported content type | text/plain vào endpoint JSON | 415 |
| Unacceptable response | Accept: application/xml khi chỉ JSON | 406 |
| Missing route | /does-not-exist | 404, default vs custom schema |
| Not found resource | /accounts/999 | 404 domain code |
| Unexpected server exception | Throw IllegalStateException | 500, no stack trace/message |
| Unauthorized | Không credentials/expired token | 401 tại security filter |
| Forbidden | User thiếu quyền | 403 tại security boundary |
| Oversized payload | JSON body vượt giới hạn server/proxy | 413 hoặc connection-level failure tùy stack |
| Unicode | Vietnamese, emoji, combining marks | UTF-8 không hỏng dữ liệu |
| Injection strings | HTML/SQL fragments trong fields | Không execute, không echo nguy hiểm |
| Locale | Accept-Language: vi/en | Status/code ổn định, detail có thể đổi |
| Negotiation | Accept */*, problem+json, text/html | Media type/body đúng contract |
| HEAD/OPTIONS | Các method đặc biệt | Kiểm response theo framework/security |
| CORS preflight | Origin + Access-Control-Request-Method | Kiểm CORS config/filter behavior |

Đặc biệt, **JSON unknown fields** có thể bị Jackson bỏ qua hoặc lỗi tùy cấu hình deserializer; không suy luận mặc định chung khi API contract muốn strict. **@NotBlank trên String q** cần được khai báo nếu muốn query present nhưng chỉ có khoảng trắng cũng là invalid; **@RequestParam(required=true)** chỉ bảo đảm param hiện diện theo resolver, không thay kiểm tra blank.

### 14.1. Test boundary tốt hơn chỉ test giá trị sai xa ngưỡng

Với @Min(18), bộ dữ liệu **17, 18, 19** giúp bắt lỗi nhầm so sánh; với @Size(max=40) test **40 và 41** ký tự theo quy tắc độ dài thực; với @Max(50) test **50 và 51**. Với Unicode có ký tự surrogate, cách tính độ dài String trong Java có thể khác số grapheme người dùng nhìn thấy; cần đặt contract rõ.

### 14.2. Tập dữ liệu sai phải an toàn

Không đưa production passwords/tokens hay thông tin thật vào fixture. Với invalid input chứa HTML injection hoặc bí mật, assert response đã được sanitize/không echo. Nếu test dùng snapshots trong CI logs, chúng cũng phải tránh PII. Dữ liệu giả như **example.test** là domain dành cho minh họa, không phải endpoint thật.

## 15. Khi nào dùng custom ResponseEntityExceptionHandler?

Spring Framework cung cấp **ResponseEntityExceptionHandler** làm base class để centralize MVC exceptions thành ErrorResponse/ProblemDetail. Có hai hướng:

**Hướng A — Spring Boot tự bật Problem Details:** đặt **spring.mvc.problemdetails.enabled=true**, rồi tạo **@RestControllerAdvice** chỉ để xử lý custom exceptions và những built-in exceptions cần override. Như demo, cần đặt **@Order** ưu tiên trước Boot advice auto-configured (order 0) để bắt những built-ins được tùy biến.

**Hướng B — Tự sở hữu toàn bộ MVC exception mapping:** tạo **@ControllerAdvice extends ResponseEntityExceptionHandler**, override các protected methods có signature đúng phiên bản như **handleMethodArgumentNotValid**, **handleHttpMessageNotReadable** và **handleHandlerMethodValidationException**. Cần duy trì behavior cho 405/415/406, headers và status, đồng thời test khi Spring nâng cấp.

Không vừa bật Boot auto advice, vừa viết custom advice có cùng mức ưu tiên và cùng loại exceptions rồi hy vọng thứ tự ngẫu nhiên. Nếu nhiều @ControllerAdvice, cấu hình order rõ và test route chạy thật.

### 15.1. Ví dụ cách override — chỉ là fragment

~~~java
// Fragment bên trong lớp extends ResponseEntityExceptionHandler.
// Cần @Override với signature phù hợp Spring Framework 6.1.
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request
) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Request validation failed."
    );
    body.setProperty("code", "VALIDATION_FAILED");
    return handleExceptionInternal(
            ex, body, headers, status, request
    );
}
~~~

Đoạn này không phải Java file chạy độc lập; thiếu surrounding class/imports. Với tình huống cần **nhất quán toàn bộ built-in errors**, override có thể hiệu quả, nhưng phải tự chịu trách nhiệm về status/headers và body. Không copy nguyên đoạn mà không đối chiếu API Spring Framework 6.1 đang dùng.

## 16. Những hiểu lầm về HTTP error handling

### 16.1. “Chỉ cần @RestControllerAdvice là bắt được mọi 401/403”

Sai. Spring Security filters có thể chặn request trước DispatcherServlet. **AuthenticationEntryPoint** xử lý yêu cầu chưa authenticated; **AccessDeniedHandler** xử lý truy cập bị từ chối tùy authentication state. Form login có thể redirect, API stateless có thể trả 401/403 không có body hoặc theo entry point được cấu hình. Kiểm thử Spring Security nên dùng **spring-security-test, @WithMockUser, csrf()** và integration với filter chain thật.

**Đừng tắt security filters trong test validation rồi coi đó là kiểm thử security.** Nếu cần isolate validation, tách tests; nếu cần kiểm behavior production, giữ filters.

### 16.2. “HTTP 400 nghĩa là @Valid đã chạy”

Không. Jackson có thể thất bại trước Bean Validation; missing required query, type conversion hoặc Content-Type lỗi cũng tạo 4xx. Kiểm stable code và lỗi theo class/cơ chế, không suy luận từ status duy nhất.

### 16.3. “Bật Problem Details là mọi lỗi đều application/problem+json”

Không. Unhandled exceptions có thể qua /error, security filters có handler riêng, proxy có error page riêng, và content negotiation còn ảnh hưởng. Muốn một public API contract thống nhất, cần thiết kế và test trên các boundaries này.

### 16.4. “MockMvc test lỗi mặc định của container đầy đủ”

Không. **MockMvc** không mở embedded server. Error page registration và dispatch tới /error là hành vi của Servlet container; Spring Boot khuyên dùng real server test cho những phần đó. MockMvc giỏi kiểm exception resolution, content negotiation và validation trong MVC pipeline.

### 16.5. “Dùng assert toàn bộ message giúp test chặt hơn”

Thường tạo test giòn. Default detail và validation messages thay đổi theo locale, message source hoặc nâng cấp thư viện. Hãy assert machine-readable code, status, field/path hoặc một message do chính API contract bảo đảm. Với dữ liệu do app tự định nghĩa, giữ các mã lỗi ổn định và có versioning.

### 16.6. “Trả chi tiết exception cho client giúp debug nhanh”

Có thể vô tình lộ SQL queries, stack traces, internal service names, tokens hoặc account enumeration. Trả một mã lỗi an toàn và correlation ID; ghi thông tin chẩn đoán đã được redacted vào logs/traces bảo vệ, không copy raw stacktrace vào body.

## 17. Troubleshooting khi negative test thất bại

| Hiện tượng | Nguyên nhân thường gặp | Hướng xác minh |
| --- | --- | --- |
| @NotBlank không chạy | Thiếu starter-validation hoặc @Valid | Dependency và method signature |
| JSON age="abc" không có violations | Jackson lỗi trước validation | Test HttpMessageNotReadableException |
| Query @Min không chạy đúng | Method validation setup/class @Validated khác kỳ vọng | Spring MVC 6.1 built-in, annotation placement |
| @WebMvcTest không start context | Service/repository dependency không được slice scan | @MockBean hoặc @Import đúng bean |
| Test nhận 401 thay vì 400 | Spring Security filter chặn trước Controller | Authentication/CSRF trong test |
| Test POST nhận 403 | CSRF filter trong app cookie auth | csrf() và policy đúng |
| Expected ProblemDetail nhưng ra JSON /error | Sai property, exception không qua advice | Kiểm spring.mvc.problemdetails.enabled và path |
| Custom @ExceptionHandler không được gọi | Boot advice ưu tiên hoặc exception type khác | @Order, HandlerMethodValidationException vs MethodArgumentNotValidException |
| 404 là NoResourceFoundException | Default static /** mapping | spring.web.resources.add-mappings |
| MockMvc 404 body khác real Tomcat | Thiếu Servlet error dispatch | RANDOM_PORT integration test |
| 406 không trả body problem+json | Accept yêu cầu representation khác | Assert status, không ép media type không hợp lệ |
| Wrong Content-Type thành 415 | Mapping consumes không khớp | Kiểm consumes và message converters |
| 500 trả raw exception message | server.error.include-message hoặc custom error handler sai | Khóa defaults an toàn, redaction test |
| JSON fields thay thứ tự giữa lần chạy | Serialization Map/Json writer không cam kết order | jsonPath thay raw string |
| Validation error list thay thứ tự | Nhiều constraints, group/validator order | Sort theo field nếu là contract |
| Test error message đổi sang tiếng Việt | Locale/MessageSource | Assert stable code/status |
| Real server test trùng port 8080 | Dùng DEFINED_PORT | RANDOM_PORT và TestRestTemplate |
| RestTemplate parse fail body | Server trả HTML do Accept | Đặt Accept phù hợp, inspect Content-Type |
| CI đỏ nhưng local xanh | Profile, JDK hoặc dependency khác | Lock Boot version và test properties |

### 17.1. Các bước debug không lan man

1. Xác nhận HTTP request **method, path, query, Content-Type, Accept** và body thực tế.
2. Phân biệt request bị chặn ở filter, handler mapping, converter, validation, Controller hay /error.
3. Xem **status và Content-Type** trước body.
4. Kiểm framework exception type bằng logs an toàn; không trả type ra client.
5. Kiểm @ControllerAdvice order và property Problem Details đang active.
6. Nếu liên quan default /error, dùng real embedded server test.
7. So sánh response với stable API contract thay vì một snapshot quá chi tiết.
8. Bổ sung regression test cho đúng lỗi đã tìm thấy.

## 18. Gợi ý thiết kế error contract dài hạn

Một API đáng tin có thể quy định:
- **type** URI ổn định cho lỗi nghiệp vụ và nhóm validation.
- **code** machine-readable không thay đổi theo locale.
- **title/detail** an toàn, dễ hiểu, có thể bản địa hóa.
- **status** khớp HTTP status và nghĩa lỗi.
- **instance** là đường dẫn hoặc URI occurrence, không kèm token/secret.
- **violations** chỉ liệt kê field/constraint code ở mức cần thiết.
- **traceId** tương quan từ tracing infrastructure nếu được cho phép.
- **Retry-After** cho overload/maintenance khi phù hợp, không dùng cho lỗi validation.

Tránh coi toàn bộ một JSON object bất kỳ là contract: nhiều field có thể là thông tin vận hành tự động. Chọn một bộ **field ổn định** và kiểm qua consumer/provider tests. Khi thay đổi error schema, phải có kế hoạch tương thích hoặc versioning.

### 18.1. Kịch bản kiểm thử contract giữa frontend/backend

Frontend gửi sai field; backend trả 400 + VALIDATION_FAILED + violations. Frontend có thể gắn lỗi đúng input field mà không dựa vào câu tiếng Anh. Khi backend thay wording hoặc locale, frontend vẫn hoạt động. Một request duplicate trả 409 + EMAIL_CONFLICT; frontend gợi ý đăng nhập hoặc đổi email. Một unhandled 500 trả generic error + correlation ID và không lộ exception; frontend báo “Thử lại sau” thay vì hiển thị stack trace.

Đây là lý do cần **negative tests có chủ đích**, không chỉ đảm bảo một method Java ném đúng exception.

## 19. Bài tập tự kiểm tra

**1.** Với Spring Boot 3.3, spring.mvc.problemdetails.enabled có mặc định là true không?  
**Đáp án:** Không, mặc định false; đặt true để bật auto hỗ trợ RFC 9457 cho MVC errors.

**2.** JSON sai cú pháp và JSON hợp lệ vi phạm @NotBlank có cùng exception không?  
**Đáp án:** Không. JSON parsing thường là HttpMessageNotReadableException; @Valid DTO thường là MethodArgumentNotValidException.

**3.** @Min trực tiếp trên @RequestParam trong Spring MVC 6.1 thường đi qua exception nào?  
**Đáp án:** HandlerMethodValidationException của built-in method validation nếu cấu hình theo mô hình mới.

**4.** Vì sao không đặt class-level @Validated tùy tiện trên Controller?  
**Đáp án:** Có thể kích hoạt AOP method validation và thay exception/đường xử lý; MVC 6.1 built-in không cần class-level annotation này.

**5.** HTTP 400 luôn có body application/problem+json không?  
**Đáp án:** Không. Phụ thuộc Problem Details config, exception handler, content negotiation và boundary.

**6.** @WebMvcTest có khởi động Tomcat thật và error page dispatch /error không?  
**Đáp án:** Không. Dùng @SpringBootTest(RANDOM_PORT) cho cơ chế Servlet container error page.

**7.** JSON lỗi mặc định của BasicErrorController có nhất thiết có message/trace không?  
**Đáp án:** Không. Spring Boot 3.3 mặc định không include các trường đó; tránh bật always ở production.

**8.** ProblemDetail có năm trường cơ bản nào?  
**Đáp án:** type, title, status, detail, instance; code/violations là extensions.

**9.** Vì sao không test so sánh raw JSON string nguyên văn?  
**Đáp án:** Thứ tự fields, timestamp, locale và các giá trị động có thể thay đổi; nên assert JSONPath/status/media type.

**10.** Test HTTP 415 và 406 khác nhau chỗ nào?  
**Đáp án:** 415 liên quan Content-Type của request; 406 liên quan Accept/representation response.

**11.** User nhập email đã tồn tại, nên luôn trả 400 hay có thể 409?  
**Đáp án:** 409 phù hợp khi API contract xem đó là conflict với trạng thái hiện tại; không tự mặc định tất cả business errors là 400.

**12.** Khi thêm Spring Security, vì sao bài test @WebMvcTest có thể bỗng nhận 401/403?  
**Đáp án:** Security filters hoạt động trước Controller, cần authentication/CSRF test đúng.

**13.** Vì sao URI /does-not-exist có thể liên quan NoResourceFoundException thay vì NoHandlerFoundException?  
**Đáp án:** Mặc định static mapping /** có thể bắt route rồi báo resource không có.

**14.** Khi @ExceptionHandler bắt Exception.class và luôn tạo HTTP 400, chuyện gì sai?  
**Đáp án:** Lỗi server/bảo mật/logic có thể bị báo sai thành client error, làm metrics và retry behavior sai.

**15.** Vì sao không echo rejectedValue trong violations?  
**Đáp án:** Có thể tiết lộ password, tokens, dữ liệu cá nhân, hoặc input cực lớn và gây XSS/log leak.

**16.** Test nào xác minh server.error.include-stacktrace=never hoạt động trên real HTTP 500?  
**Đáp án:** Real server integration GET /api/boom, assert 500 và body không có trace/exception/message.

**17.** Điều kiện nào để lỗi dữ liệu hợp lệ cú pháp dùng 422?  
**Đáp án:** API phải định nghĩa rõ tình huống nội dung không thể xử lý và custom mapping, không phải @Valid tự trả 422.

**18.** Có thể chỉ đọc status là đủ để bảo đảm frontend hiển thị field errors đúng không?  
**Đáp án:** Không. Cần assert code, violations schema, field names, content type và contract ổn định.

## 20. Checklist QA cho mỗi API

- [ ] Có tests happy path để làm baseline.
- [ ] Có tests JSON malformed, missing body, wrong type và @Valid DTO.
- [ ] Có tests null/blank/boundary constraints, @Min/@Max/@Size.
- [ ] Có tests required/malformed query và path variable.
- [ ] Có tests method/content negotiation 404/405/406/415.
- [ ] Có tests domain 404/409 và phân biệt chúng với built-in errors.
- [ ] Có tests 401/403 ở security filter nếu app dùng Spring Security.
- [ ] Problem Details được bật đúng property của stack MVC, không nhầm WebFlux.
- [ ] Tests ProblemDetail kiểm HTTP status, application/problem+json, stable code/type.
- [ ] Các violations được lọc, không echo rejectedValue hoặc bí mật.
- [ ] server.error.include-message/stacktrace/binding-errors bảo mật.
- [ ] Real HTTP integration test xác minh /error và các default responses.
- [ ] Không dùng MockMvc để khẳng định đã test container error-page behavior.
- [ ] Assertions không phụ thuộc timestamp, locale hoặc order JSON không cam kết.
- [ ] @WebMvcTest không vô hiệu hóa security filters để che lỗi thật.
- [ ] Có test không gọi service khi request lỗi trước Controller.
- [ ] Có negative tests chống lộ SQL, stack trace, tokens, internal class names.
- [ ] Tất cả tests chạy qua Maven CI, có quyền chỉnh behavior khi nâng Spring Boot.

## 21. Kết luận

**Kiểm thử web runtime phải kiểm đường dữ liệu sai cũng nghiêm túc như happy path.** Trong Spring Boot MVC, lỗi có thể xuất hiện ở **routing, JSON conversion, Bean Validation, method validation, domain service, Spring Security filter hoặc Servlet /error**. Mỗi tầng có exception/status/error body riêng.

**Problem Details RFC 9457** tạo ngôn ngữ lỗi chuẩn qua **ProblemDetail** và **application/problem+json**, nhưng với Spring Boot 3.3 phải bật **spring.mvc.problemdetails.enabled=true** và không được mặc định mọi 500/security/proxy error đều chuyển sang cùng schema. **MockMvc/@WebMvcTest** thích hợp test validation và ControllerAdvice; **real-port @SpringBootTest** cần thiết để xác minh default /error. Error contract bền vững cần status đúng, code/type ổn định và không rò thông tin nhạy cảm.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Servlet Web Applications, Error Handling và RFC 9457: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties, spring.mvc.problemdetails.enabled và server.error.*: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot 3.3 — Testing Spring Boot Applications, @WebMvcTest, MockMvc và servlet container caveat: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Error Responses, ProblemDetail và ResponseEntityExceptionHandler: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MockMvc integration tests: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Security — Servlet ExceptionTranslationFilter, AuthenticationEntryPoint và AccessDeniedHandler: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP status semantics (400/404/405/406/409/415/422/500): https://www.rfc-editor.org/rfc/rfc9110.html
