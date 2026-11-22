# @RequestBody, @ModelAttribute và cơ chế tạo đối tượng đầu vào trong Spring Boot

## 1. Mục tiêu và bối cảnh

Khi Spring Boot nhận một HTTP request, framework cần biến dữ liệu bên ngoài — JSON, form fields, query parameters, URI variables, headers hoặc multipart parts — thành các đối tượng Java để controller xử lý. Hai annotation rất dễ nhầm lẫn là **`@RequestBody`** và **`@ModelAttribute`**.

Bài này giải thích *đường đọc dữ liệu*, *cách đối tượng Java được tạo*, *cách dữ liệu được gán*, *cách validate* và *lỗi/bảo mật* đối với cả hai. Trọng tâm là Spring MVC trong `spring-boot-starter-web`; cuối bài so sánh phần tương ứng của Spring WebFlux để tránh áp dụng sai runtime.

Sau bài học, bạn có thể:
1. Chọn `@RequestBody` cho JSON/XML và `@ModelAttribute` cho form/query binding đúng ngữ cảnh.
2. Giải thích trình tự argument resolver → message converter/deserializer hoặc binder → Java object → validation → handler.
3. Hiểu constructor binding, JavaBean setter binding, record/immutable DTO, chuyển đổi kiểu và dữ liệu không khớp tên.
4. Phân biệt lỗi không đọc được body, không convert được tham số, lỗi validation và lỗi media type.
5. Đặt `BindingResult` đúng vị trí; sử dụng `@Valid`, `@InitBinder` và DTO chuyên dụng.
6. Phòng tránh **mass assignment/over-posting** khi dữ liệu client điều khiển thuộc tính object.
7. Kiểm thử bằng curl, MockMvc và integration tests có thể tái lập.

Ví dụ chính: **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. Với các phiên bản khác, đối chiếu tài liệu API của phiên bản đang chạy.

## 2. Phân biệt nguồn dữ liệu trước khi chọn annotation

| Kiểu request | Ví dụ | Công cụ thường chọn |
|---|---|---|
| JSON body, `application/json` | `{"name":"Lan","age":24}` | `@RequestBody SignupJson` |
| Form URL-encoded | `name=Lan&age=24` | `@ModelAttribute SignupForm` hoặc `@RequestParam` |
| Query string | `GET /search?q=java&page=2` | `@RequestParam` cho vài tham số; `@ModelAttribute SearchCriteria` cho nhóm thuộc tính |
| URL path | `GET /users/42` | `@PathVariable long id`; có thể tham gia model-attribute binding khi tên phù hợp |
| Multipart form | Text parts + file | `@ModelAttribute UploadForm`, `@RequestParam MultipartFile` hoặc `@RequestPart` |
| Multipart JSON part | Part `metadata` có `Content-Type: application/json` | `@RequestPart("metadata") Metadata` |
| Raw bytes hoặc text body | `text/plain`, octet-stream | `@RequestBody String`/`byte[]` khi có converter phù hợp |
| Header hoặc cookie độc lập | `X-Trace-Id`, `session` | `@RequestHeader`, `@CookieValue` |

Quy tắc nền tảng: `@RequestBody` biểu diễn **nội dung body được đọc và giải mã qua HTTP message conversion**, còn `@ModelAttribute` biểu diễn **một model object được lấy/tạo rồi bind tên–giá trị của request**. Hai cơ chế có thể cùng trả về một Java DTO nhưng khác hoàn toàn đường thực hiện.

Trong Servlet MVC, dữ liệu form URL-encoded được Servlet API đưa vào hệ tham số request; truy cập các tham số này có thể tiêu thụ body. Bởi vậy tài liệu Spring khuyến nghị dùng `@RequestParam` hoặc `@ModelAttribute` cho form, **không coi `@RequestBody` là lựa chọn mặc định cho form-urlencoded**.

## 3. Luồng tổng thể của Spring MVC

~~~text
HTTP request
  |
DispatcherServlet -> HandlerMapping -> HandlerAdapter
                                       |
                                       v
                              Resolver cho mỗi method argument
                                       |
                    +------------------+------------------+
                    |                                     |
             @RequestBody                             @ModelAttribute
                    |                                     |
          HttpMessageConverter                       Model / Session?
                    |                                     |
       (JSON -> Jackson ObjectMapper)              có object / tạo mới
                    |                                     |
              JSON DTO/record                 constructor binding và/hoặc
                    |                          property (setter) binding
                    |                                     |
                    +------------- Validation ------------+
                                       |
                         Handler method/controller
                                       |
                      Business service -> response
~~~

Controller chỉ được gọi khi framework giải quyết được các tham số bắt buộc, trừ khi bạn khai báo `BindingResult`/`Errors` để chủ động xử lý các lỗi binding/validation hỗ trợ. Cả hai cách đều **không tự lưu dữ liệu vào database** và đối tượng nhận được **không tự trở thành Spring-managed bean**.

### 3.1. Method argument resolver mới là bước chọn cơ chế

Spring MVC có các `HandlerMethodArgumentResolver` với nhiệm vụ đọc annotation/kiểu tham số, sau đó tạo giá trị đưa vào lời gọi Java. `@RequestBody` đi theo nhánh đọc body bằng `HttpMessageConverter`; `@ModelAttribute` đi theo model attribute/binder. `@RequestParam`, `@PathVariable` và `@RequestHeader` đi theo các resolver tương ứng.

Vì mỗi resolver có contract riêng, **không** suy luận rằng thay `@ModelAttribute` bằng `@RequestBody` vẫn đọc được form hoặc query string như cũ.

## 4. @RequestBody: body, message converter và deserialization

Ví dụ controller nhận JSON:

~~~java
@PostMapping(path = "/users", consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<UserView> create(@Valid @RequestBody CreateUserRequest request) {
    UserView created = service.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Đây là fragment, giả định đã có DTO, service và imports.

Quy trình thường gặp:
1. HandlerAdapter phát hiện đối số `@RequestBody`.
2. HTTP `Content-Type` và kiểu Java đích được dùng để chọn `HttpMessageConverter`.
3. Với JSON và Jackson trên classpath, `MappingJackson2HttpMessageConverter` đọc body, gọi Jackson để tạo DTO và gán field/property/constructor arguments.
4. Nếu có `@Valid` hoặc `@Validated` và validation provider tương ứng, framework kiểm các constraints của object.
5. DTO hợp lệ được truyền cho controller; nếu không, có thể phát sinh exception và trả HTTP 400 theo cấu hình mặc định của MVC.

**Điểm quan trọng:** `@RequestBody` không tự lấy dữ liệu từ query string để điền thiếu JSON. Nếu client gửi `POST /users?name=Lan` với body `{"age":24}`, tên `name` không được mặc nhiên bổ sung từ query vào DTO JSON. Nếu API cần dữ liệu ở cả hai nơi, khai báo các tham số riêng có chủ đích.

### 4.1. Jackson tạo object như thế nào?

Không có một yêu cầu tuyệt đối rằng mọi JSON DTO phải có public no-arg constructor. Tùy thiết kế đối tượng và cấu hình Jackson, các cách phổ biến là:

- JavaBean: constructor không tham số + setter/field-access phù hợp.
- Java `record`: Jackson nhận các record components và gọi canonical constructor.
- Constructor hoặc static factory được chọn bằng `@JsonCreator` cùng mapping `@JsonProperty` khi cần.
- Annotation Jackson để đổi tên field (`@JsonProperty`) hoặc điều chỉnh quy tắc deserialization.

Ví dụ Java 17 record:

~~~java
public record CreateUserRequest(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {
}
~~~

Body:

~~~json
{"name":"Lan","email":"lan@example.org","age":24}
~~~

Jackson có thể tạo record bằng constructor nhận các giá trị tương ứng. Không cần thêm setter chỉ để JSON bind được. `@NotBlank`, `@Email`, `@Min` là Bean Validation constraints; chúng chỉ được kiểm tra theo pipeline validation khi được kích hoạt, chẳng hạn bằng `@Valid` và starter validation.

### 4.2. `required`, body rỗng, null và field thiếu

`@RequestBody` có `required=true` mặc định: thiếu body bắt buộc thường tạo 400. `@RequestBody(required=false)` cho phép trường hợp body không có; controller phải xử lý tham số có thể null hoặc optional tương ứng.

Phân biệt:
- Body rỗng: không có dữ liệu để message converter tạo đối tượng.
- JSON `null`: ý nghĩa phụ thuộc converter và kiểm tra required.
- JSON object nhưng thiếu một field: Java record constructor được gọi với giá trị null/default nếu Jackson cho phép; **không mặc định** coi mọi field thiếu là lỗi.
- Với `int age`, thiếu `age` có thể dẫn tới `0` và bị `@Min(18)` bắt khi validation chạy; dùng `Integer` + `@NotNull` nếu cần phân biệt “thiếu” và “0”.
- JSON sai cú pháp hoặc kiểu không giải mã được: thường nhận 400 trước khi controller chạy.

### 4.3. Không nhầm status 400, 415 và 406

| Tình huống | Kết quả thường gặp |
|---|---|
| `@RequestBody` bắt buộc nhưng request không có body | 400 Bad Request |
| JSON sai cú pháp/không deserialize được | 400 Bad Request (`HttpMessageNotReadableException`) |
| Bean Validation của body không đạt | 400 mặc định (`MethodArgumentNotValidException`) |
| Endpoint chỉ tiêu thụ JSON, client gửi `Content-Type: text/plain` | 415 Unsupported Media Type |
| Client không chấp nhận định dạng response được cung cấp | Có thể 406 Not Acceptable |
| Controller xử lý xong nhưng business rule từ chối dữ liệu hợp lệ về cú pháp | Mã lỗi tùy hợp đồng ứng dụng, không tự động gán 400/422 |

Những mã trên là hành vi chuẩn thường gặp, không phải lời hứa rằng custom `@ControllerAdvice`, proxy hay thư viện chưa đổi error mapping.

## 5. @ModelAttribute: lấy hoặc tạo đối tượng rồi data binding

Ví dụ:

~~~java
@PostMapping(path = "/signup", consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<String> signup(
        @Valid @ModelAttribute("signupForm") SignupForm form) {
    return ResponseEntity.ok("Hello " + form.getName());
}
~~~

Controller nhận một `SignupForm` **không phải nhờ JSON deserializer**. Spring tìm model attribute tên `signupForm` rồi sử dụng `WebDataBinder` để bind các tham số request tương ứng.

Một model attribute có thể:
- Đã nằm trong `Model`, ví dụ được một method-level `@ModelAttribute` chuẩn bị trước.
- Đến từ `@SessionAttributes` nếu controller khai báo và request có đối tượng phiên tương ứng.
- Được tạo từ constructor mặc định hoặc primary constructor phù hợp khi chưa có đối tượng trong model.
- Được bind bằng constructor arguments và/hoặc mutable bean properties theo cấu hình binder.

Trong Spring MVC, dữ liệu từ **form và query parameters** có thể tham gia binding; URI template variables và headers cũng có thể tham gia khi tên phù hợp và không ghi đè request parameters có cùng tên. Cơ chế này mạnh nhưng cũng là lý do phải kiểm soát dữ liệu client được phép điền.

### 5.1. JavaBean property binding

DTO mutable điển hình:

~~~java
public class SignupForm {
    private String name;
    private int age;

    public SignupForm() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
~~~

Với `name=Lan&age=24`, Spring có thể tạo `SignupForm` qua no-arg constructor rồi gọi setters. Giá trị string `"24"` được chuyển sang `int 24` bởi conversion infrastructure. Không cần viết mã `Integer.parseInt` trong controller cho từng field.

Nếu client gửi `age=abc`, đó là **lỗi chuyển đổi/binding**: `int` không thể nhận `"abc"`, được phản ánh trong `BindingResult` hoặc exception tương ứng. Nó khác với trường hợp convert thành công nhưng `age=15` vi phạm `@Min(18)`.

### 5.2. Constructor binding và đối tượng bất biến

Spring Framework 6.x hỗ trợ constructor binding cho model attributes. DTO có primary constructor hoặc Java record có thể được tạo bằng cách map tên request parameters tới constructor arguments.

~~~java
public record SearchCriteria(String keyword, Integer page) {}
~~~

Với `GET /search?keyword=java&page=2`, một parameter `@ModelAttribute SearchCriteria criteria` có thể được xây từ constructor. Với Java record, tên record components được giữ; với class constructor thông thường cần metadata tên tham số Java (thường có nhờ `javac -parameters`), hoặc dùng annotation mapping tên như `@BindParam` nếu cần.

Constructor binding và property binding **không loại trừ lẫn nhau** theo mặc định. Nếu muốn một object chỉ được gán theo constructor vì lý do bảo mật, thiết kế DTO bất biến không có setters và cân nhắc cấu hình declarative binding phù hợp với phiên bản framework.

### 5.3. Nested objects, collections, indexes và converter

Binder có thể hỗ trợ tên property dạng `address.city`, `items[0].sku`, `tags[1]`, trong giới hạn cấu hình và kiểu đối tượng. Điều này hữu ích cho HTML form phức tạp, nhưng cũng có thể mở bề mặt dữ liệu vượt mong muốn.

Nếu cần kiểu `LocalDate`, enum, số có định dạng theo locale hoặc đối tượng domain, xem `ConversionService`, `Converter`, `Formatter`, `@DateTimeFormat` và `@NumberFormat`. Không đặt trách nhiệm chuyển đổi chuỗi tùy ý vào business service nếu binder có thể xử lý theo hợp đồng API.

## 6. Cấu trúc object: JSON record khác form bean ở điểm nào?

| Câu hỏi | `@RequestBody` | `@ModelAttribute` |
|---|---|---|
| Nguồn chính | Request body (JSON/XML/bytes...) | Request parameter values, model/session, form/query; có thể thêm path/header khi phù hợp |
| Thành phần đọc | `HttpMessageConverter` (MVC) | `WebDataBinder` và model attribute resolution |
| Cơ chế tạo | Deserializer: no-arg/setter, record, `@JsonCreator`... | Existing model object, constructor binding, default constructor + property binding |
| Cách đặt tên | JSON property names, Jackson annotations | Request parameter/property names, `@BindParam` và binder configuration |
| Chuyển kiểu | JSON parsing/deserialization + Jackson types | Spring type conversion/formatter |
| Validation | `@Valid`/`@Validated` trên DTO | `@Valid`/`@Validated` trên model attribute |
| Form URL-encoded | Không nên dùng làm lựa chọn mặc định trong MVC | Phù hợp |
| Nested fields | Theo JSON tree | Theo property paths như `address.city` |
| Dữ liệu không được phép bind | JSON deserializer/DTO/Jackson policy | Allowed fields, DTO, constructor-only strategy |
| Lỗi hay gặp | Missing/invalid body, unsupported media | Type mismatch, unknown/disallowed fields, binding errors |

Hai cách cùng dùng `@Valid` nhưng error detail có thể khác ở phần không đọc được body hoặc conversion. Không nên viết một error handler giả định mọi thất bại khi nhận dữ liệu đều là `MethodArgumentNotValidException`.

## 7. Validation: khi nào chạy và BindingResult đặt ở đâu?

`jakarta.validation.Valid` kích hoạt việc validate object nếu dependency validation có trên classpath và được tích hợp. Trong Spring Boot, thông thường thêm `spring-boot-starter-validation` để có Jakarta Bean Validation provider.

Ví dụ constraints:

~~~java
record SignupJson(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {}
~~~

- `@NotBlank`: không chấp nhận null/chuỗi rỗng/chỉ whitespace.
- `@Email`: kiểm tra định dạng email ở mức constraint, không chứng minh mailbox tồn tại.
- `@Min(18)`: yêu cầu tuổi ít nhất 18; kiểm tra input numeric sau conversion/deserialization.
- `@NotNull` hữu ích với wrapper như `Integer` khi cần phân biệt null và zero.

### 7.1. BindingResult xử lý tại controller

Với `@ModelAttribute` hoặc `@RequestBody`, trong các tình huống Spring MVC hỗ trợ local errors, tham số `BindingResult`/`Errors` phải nằm **ngay sau** đối số được validate:

~~~java
@PostMapping("/signup/check")
ResponseEntity<?> signup(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid signup form"));
    }
    return ResponseEntity.ok(Map.of("name", form.getName()));
}
~~~

Đây là fragment cần `Map` và các imports tương ứng. Đừng đặt `BindingResult` sau tham số khác rồi chờ nó tự gắn với form. Nếu không khai báo local error argument, các lỗi validation/binding thường được đưa ra exception để framework hoặc `@RestControllerAdvice` xử lý.

Khi có constraints đặt **trực tiếp trên method parameters** (không chỉ `@Valid` vào DTO), Spring Framework có thể kích hoạt method validation và ném `HandlerMethodValidationException` thay cho `MethodArgumentNotValidException`. Error handler chung nên xét cả hai nhánh, nhất là khi thay đổi chữ ký controller.

### 7.2. @Valid không tự bảo vệ mass assignment

Validation chỉ kiểm tính hợp lệ của các giá trị đã bind; nó không mặc nhiên giới hạn field nào client được quyền sửa. `@Valid` cũng không thay thế authorization, xác thực quyền sở hữu tài nguyên, kiểm tra mã nghiệp vụ hoặc xử lý trùng lặp.

## 8. Ví dụ Maven chạy được: cùng một nghiệp vụ, hai đường tạo object

Ví dụ dưới đây dùng `spring-boot-starter-web` (Spring MVC + Tomcat mặc định), Java 17 và Bean Validation. Cung cấp ba endpoint:
- `POST /api/signup/json`: nhận JSON qua `@RequestBody` vào record.
- `POST /api/signup/form`: nhận form URL-encoded qua `@ModelAttribute` vào JavaBean mutable.
- `POST /api/signup/immutable`: nhận form vào record bằng constructor binding.

### 8.1. Tạo pom.xml

~~~xml
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
    <groupId>example</groupId>
    <artifactId>input-binding-demo</artifactId>
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

Không thêm `spring-boot-starter-webflux` cho ví dụ này: mục tiêu là minh họa Servlet MVC.

### 8.2. File Java đầy đủ

Tạo `src/main/java/example/input/InputBindingApplication.java`:

~~~java
package example.input;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class InputBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputBindingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/signup")
class SignupController {

    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<SignupView> json(
            @Valid @RequestBody SignupJson input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupView(
                        "json", input.name(), input.email(), input.age()));
    }

    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<SignupView> form(
            @Valid @ModelAttribute("signupForm") SignupForm input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupView(
                        "form", input.getName(), input.getEmail(), input.getAge()));
    }

    @PostMapping(path = "/immutable",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<SignupView> immutable(
            @Valid @ModelAttribute SignupRecord input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupView(
                        "record", input.name(), input.email(), input.age()));
    }

    @InitBinder("signupForm")
    void limitSignupFields(WebDataBinder binder) {
        binder.setAllowedFields("name", "email", "age");
    }
}

record SignupJson(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {}

record SignupRecord(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {}

record SignupView(String source, String name, String email, int age) {}

class SignupForm {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @Min(18)
    private int age;

    public SignupForm() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
~~~

Đây là một Java source file hợp lệ với **một public class** trùng tên tệp, các type còn lại package-private. Spring Boot parent cấu hình biên dịch theo Java version nêu trên, phù hợp với record/constructor parameter names. Controller không lưu dữ liệu thực, chỉ echo các giá trị đã bind để dễ quan sát; production cần chuyển DTO sang domain/service theo nghiệp vụ.

`@InitBinder("signupForm")` chỉ định allowed fields cho model attribute có tên `signupForm`. Đây là minh họa kiểm soát **property binding** ở endpoint form mutable, không phải lý do để cho phép bind trực tiếp entity nhạy cảm; constructor binding được kiểm soát bằng các tham số constructor/DTO chuyên dụng.

### 8.3. Chạy và thử từng endpoint

Tại thư mục chứa `pom.xml`, với Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i -X POST http://localhost:8080/api/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.org","age":24}'
~~~

Kết quả quan trọng dự kiến: **HTTP 201** và JSON:

~~~json
{"source":"json","name":"Lan","email":"lan@example.org","age":24}
~~~

Gửi form URL-encoded:

~~~bash
curl -i -X POST http://localhost:8080/api/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Minh" \
  --data-urlencode "email=minh@example.org" \
  --data-urlencode "age=21"
~~~

Kết quả quan trọng: **HTTP 201**, JSON:

~~~json
{"source":"form","name":"Minh","email":"minh@example.org","age":21}
~~~

Gửi cùng kiểu form vào record immutable:

~~~bash
curl -i -X POST http://localhost:8080/api/signup/immutable \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=An" \
  --data-urlencode "email=an@example.org" \
  --data-urlencode "age=30"
~~~

Kết quả quan trọng: **HTTP 201** và JSON:

~~~json
{"source":"record","name":"An","email":"an@example.org","age":30}
~~~

Các header khác, port, charset và trình tự thuộc tính response có thể tùy cấu hình runtime. Những JSON trên biểu diễn dữ liệu dự kiến; client JSON không nên phụ thuộc thứ tự key.

### 8.4. Thử lỗi validation và content type

~~~bash
# Tuổi không đạt constraint
curl -i -X POST http://localhost:8080/api/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.org","age":15}'

# Tuổi sai định dạng: binder không chuyển "abc" thành int
curl -i -X POST http://localhost:8080/api/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Minh&email=minh@example.org&age=abc"

# Gửi sai media type vào endpoint JSON
curl -i -X POST http://localhost:8080/api/signup/json \
  -H "Content-Type: text/plain" \
  -d "name=Lan"
~~~

Ba kết quả status thường gặp tương ứng **400**, **400** và **415** trong MVC mặc định. Error body có thể thay đổi theo phiên bản, `server.error.*` và custom exception handlers, nên không đóng cứng format JSON lỗi nếu chưa thiết kế hợp đồng riêng.

## 9. Unit/integration tests cho cơ chế tạo đối tượng

Với `spring-boot-starter-test` từ ví dụ, tạo `src/test/java/example/input/InputBindingApplicationTests.java`:

~~~java
package example.input;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InputBindingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsJsonViaRequestBody() throws Exception {
        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Lan","email":"lan@example.org","age":24}
                    """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.source").value("json"))
                .andExpect(jsonPath("$.age").value(24));
    }

    @Test
    void bindsFormParametersViaModelAttribute() throws Exception {
        mvc.perform(post("/api/signup/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Minh")
                .param("email", "minh@example.org")
                .param("age", "21"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.source").value("form"))
                .andExpect(jsonPath("$.name").value("Minh"));
    }

    @Test
    void rejectsInvalidJson() throws Exception {
        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"","email":"invalid","age":15}
                    """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsFormTypeMismatch() throws Exception {
        mvc.perform(post("/api/signup/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Minh")
                .param("email", "minh@example.org")
                .param("age", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các kiểm thử dự kiến **PASS** trên project đã mô tả, vì JSON được đọc qua message converter, form thông qua binder, Bean Validation được bật và lỗi binding/validation được Spring MVC ánh xạ 400. Kiểm thử MockMvc không thay thế integration test với servlet container khi bạn cần kiểm chứng limits, multipart streaming hoặc hạ tầng proxy, nhưng phù hợp để chốt cơ chế argument binding.

## 10. @ModelAttribute còn có nghĩa ở cấp method

Annotation `@ModelAttribute` có nhiều vai trò:

1. **Trên method parameter:** nhận hoặc tạo model object rồi bind dữ liệu request.
2. **Trên method của controller hoặc `@ControllerAdvice`:** chuẩn bị dữ liệu đưa vào `Model` trước khi handler request chạy.
3. **Trên return value của handler:** có thể khai báo rõ dữ liệu được coi là model attribute trong controller trả view.

Ví dụ fragment:

~~~java
@ModelAttribute("countries")
List<String> countries() {
    return List.of("VN", "SG", "JP");
}

@GetMapping("/signup-page")
String page(Model model) {
    model.addAttribute("form", new SignupForm());
    return "signup-page";
}
~~~

Ví dụ trên cần các imports và một template engine/view tương ứng; không phải endpoint trong demo REST ở mục 8. Method `countries()` cung cấp dữ liệu cho model, **không** phải một request body decoder.

Việc dùng `@ModelAttribute(binding=false)` giúp truy cập model attribute có sẵn mà không thực hiện data binding cho nó. Đây là cơ chế thích hợp trong tình huống bạn đã tìm domain object an toàn và không muốn client ghi đè properties của object đó.

## 11. Multipart: không nhầm form field, file và JSON part

HTML form upload thường gửi `multipart/form-data`. Một DTO dành cho binding có thể gồm:
- `String title`;
- `MultipartFile file` (Servlet MVC);
- các field text khác có setter/constructor binding phù hợp.

Fragment minh họa controller:

~~~java
@PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<?> upload(@Valid @ModelAttribute UploadForm form) {
    if (form.getFile() == null || form.getFile().isEmpty()) {
        return ResponseEntity.badRequest().body("file is required");
    }
    return ResponseEntity.ok(Map.of(
            "title", form.getTitle(),
            "size", form.getFile().getSize()));
}
~~~

Cần một class `UploadForm` có trường `title`, `MultipartFile file` và getters/setters, cùng imports; đây **không** là phần chạy độc lập của demo chính. Khi part chứa JSON với Content-Type riêng, dùng `@RequestPart("metadata") @Valid Metadata metadata` và `@RequestPart("file") MultipartFile file` sẽ biểu diễn hợp đồng rõ hơn.

Không gọi `getBytes()` cho file khổng lồ chỉ để kiểm tra metadata; giới hạn kích thước upload, loại file, xử lý đường dẫn và xác thực quyền trước khi lưu. Với Servlet MVC, `spring.servlet.multipart.*` điều khiển các giới hạn upload của Spring Boot trong phạm vi cấu hình được hỗ trợ.

## 12. Bảo mật: mass assignment, DTO và allowed fields

Đây là rủi ro học thuật quan trọng nhất của model attribute binding. Giả sử domain entity có:
- `displayName` — người dùng được sửa.
- `email` — có thể sửa theo quy trình xác minh.
- `role` — chỉ admin thay.
- `balance` — được tính toán từ hệ thống.
- `ownerId` — phải lấy từ identity đã xác thực.

Nếu controller bind thẳng một domain entity mutable bằng `@ModelAttribute`, attacker có thể gửi thêm `role=ADMIN`, `balance=999999` hoặc `ownerId=...`. Nếu binder cho phép gán field ấy và service lưu entity, đây là **mass assignment/over-posting**. Không nên dựa vào UI ẩn field để cho rằng client không thể gửi nó.

Các biện pháp ưu tiên:
1. **Thiết kế request DTO riêng** chỉ chứa trường được phép chỉnh sửa.
2. Cân nhắc constructor binding với DTO bất biến/record khi phù hợp.
3. Với property binding, giới hạn `allowedFields` qua `@InitBinder` hoặc cấu hình binder phù hợp.
4. Không bind trực tiếp JPA entity nhạy cảm, nhất là object lấy từ DB theo ID rồi đưa vào model.
5. Thực thi authorization và business checks ở service. `allowedFields` không xác thực ai được phép sửa một tài nguyên.
6. Áp dụng chính sách tương tự cho JSON `@RequestBody`: request DTO, Jackson binding policy và mapping rõ ràng sang entity; JSON không mặc nhiên miễn nhiễm over-posting.

Fragment có chủ đích:

~~~java
@InitBinder("accountForm")
void accountBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

Điều này giới hạn **property binding** cho model attribute `accountForm`. Constructor binding cần được kiểm soát bằng chính thiết kế constructor/DTO, không xem `setAllowedFields` là danh sách chặn tuyệt đối mọi nguồn input trong mọi giai đoạn.

## 13. Chuyển kiểu, lỗi và lựa chọn response status

| Vấn đề | Nguyên nhân cần tìm | Kết quả thường gặp và cách xử lý |
|---|---|---|
| `@RequestBody` là null/không có | Body rỗng, sai required contract | 400 hoặc xử lý nullable/optional nếu chủ đích |
| `HttpMessageNotReadableException` | JSON sai cú pháp, type không deserialize được | 400; không gọi service nghiệp vụ |
| `HttpMediaTypeNotSupportedException` | Content-Type không thuộc `consumes`/converter hỗ trợ | 415; xác minh client gửi đúng media type |
| `MethodArgumentNotValidException` | Bean Validation hoặc binding errors với object | 400 mặc định; cung cấp error detail nhất quán |
| `HandlerMethodValidationException` | Method-level constraints trên tham số/return | Trạng thái phụ thuộc hướng validation; thường 400 cho input |
| `BindException`/field binding errors | Tham số form không convert được hoặc thiếu | Xem BindingResult, field errors, 400 thường gặp |
| Form `age=abc` | Converter không đổi string thành int | 400, chỉ rõ field `age` |
| JSON `age="abc"` | Jackson không deserialize được int từ chuỗi không hợp lệ | 400 trước khi DTO được tạo hợp lệ |
| Unknown JSON properties | Chính sách Jackson với unknown fields | Có thể bị bỏ qua hoặc từ chối; kiểm tra ObjectMapper config |
| Over-posting | DTO cho phép field nhạy cảm hoặc bind entity | Sửa model design/allowedFields/authorization |

**Không trả nguyên exception stack trace hoặc toàn bộ raw request body ra client.** Thống nhất error response bằng `@RestControllerAdvice` khi có nhu cầu, nhưng cần phân biệt field validation, parser error và media type. JSON Problem Details (`ProblemDetail`) là một lựa chọn nếu API đã chuẩn hóa định dạng lỗi, không phải mặc định duy nhất.

### 13.1. Nên trả lỗi nào cho API?

- Request không đúng cú pháp hoặc không thể bind: thường **400 Bad Request**.
- Media type không được hỗ trợ: **415 Unsupported Media Type**.
- Nội dung có cú pháp hợp lệ nhưng vi phạm quy tắc nghiệp vụ: tùy hợp đồng, có thể **400**, **409** hoặc **422**; đừng coi 422 là phản hồi tự động của `@Valid`.
- Thiếu quyền hoặc xác thực: **401/403**, xử lý ở tầng security thích hợp.

Việc API trả lỗi đẹp không thay thế kiểm thử rằng **service chưa ghi dữ liệu** khi binding hoặc validation thất bại.

## 14. @RequestBody và @ModelAttribute trong Spring WebFlux

WebFlux vẫn dùng hai annotation nhưng **hạ tầng khác MVC**:

| Thành phần | Spring MVC | Spring WebFlux |
|---|---|---|
| HTTP server | Servlet container | Reactive runtime, thường Reactor Netty |
| Đọc `@RequestBody` | `HttpMessageConverter` | `HttpMessageReader` / codecs |
| Đối số body reactive wrapper | Không dùng như WebFlux để đọc non-blocking | Hỗ trợ `Mono<T>` và các reactive types theo contract |
| `@ModelAttribute` | `WebDataBinder` cho form/query/model object | Binder reactive-aware; form/query và các nguồn được hỗ trợ |
| Validation `@RequestBody` | Thường `MethodArgumentNotValidException` | Thường `WebExchangeBindException` |
| Khả năng chờ đọc body | Theo Servlet/I/O runtime | Không dùng `block()` trong handler reactive |

Ví dụ **fragment trong ứng dụng WebFlux**, không được dán vào project Spring MVC ở mục 8 với kỳ vọng tự chạy:

~~~java
@PostMapping(path = "/users", consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ResponseEntity<UserView>> create(
        @Valid @RequestBody Mono<CreateUserRequest> requestMono) {

    return requestMono.map(input ->
            ResponseEntity.status(HttpStatus.CREATED)
                    .body(new UserView(input.name(), input.email())));
}
~~~

Ở đây `CreateUserRequest`, `UserView` là record/class thuộc dự án khác; method minh họa việc đọc/validate body qua reactive publisher. Không gọi `requestMono.block()`. Khi dùng `BindingResult` với WebFlux, cần lưu ý các argument bọc reactive type không sử dụng local `BindingResult` giống tham số object đồng bộ; thường xử lý lỗi qua `onErrorResume` hoặc error handler của WebFlux.

Với `@ModelAttribute`, WebFlux cũng có thể bind form/query/path/header sang object, nhưng cách đọc form data và lifecycle request non-blocking khác Servlet. Đừng sử dụng `HttpServletRequest.getParameterMap()` trong Netty WebFlux.

## 15. Những sai lầm thường gặp

1. **Dùng `@RequestBody` để nhận mọi form URL-encoded trong MVC:** dễ xung đột Servlet parameter parsing; nên dùng `@ModelAttribute`/`@RequestParam`.
2. **Nghĩ `@ModelAttribute` lấy toàn bộ JSON body:** sai cơ chế; JSON phải có body converter với `@RequestBody`.
3. **Nghĩ `@RequestBody` tự gộp query params vào JSON DTO:** không đúng.
4. **Cho rằng `@ModelAttribute` bắt buộc no-arg constructor:** Spring hỗ trợ constructor binding và record khi điều kiện version/metadata thỏa.
5. **Cho rằng Jackson bắt buộc public setters:** Java records và creators có thể deserialize mà không cần setters.
6. **Không bật validation provider nhưng tin rằng `@Valid` sẽ luôn kiểm dữ liệu:** thiếu starter/provider có thể dẫn tới không có Bean Validation như kỳ vọng.
7. **Đặt `BindingResult` cách xa đối số tương ứng:** Spring không liên kết đúng error argument.
8. **Dùng domain/JPA entity trực tiếp làm `@ModelAttribute`:** tạo nguy cơ over-posting, nested property injection và sai authorization.
9. **Cho rằng validation đồng nghĩa authorization:** hai trách nhiệm khác nhau.
10. **Mọi input sai đều là 400:** media type sai có thể là 415; lỗi nghiệp vụ có status riêng.
11. **Nhầm method-level `@ModelAttribute` với argument-level `@ModelAttribute`:** một cái chuẩn bị model, một cái bind tham số.
12. **Test JSON bằng `.param()` mà không gửi body JSON:** không kiểm chứng `@RequestBody` deserialization.
13. **Test form bằng JSON content và mong data binder dùng params:** cần đúng Content-Type/hình thức request.
14. **Gửi JSON và form trong cùng request rồi bắt cả hai argument readers:** dễ gặp body-consumption/contract không nhất quán.
15. **Lấy `@RequestBody(required=false)` nhưng không xử lý null:** khiến service ném NPE.
16. **Cho rằng `@Email` xác minh email tồn tại:** constraint chỉ kiểm định dạng.
17. **Dùng `int` cho field cần phân biệt missing/null:** default primitive có thể che mất ý nghĩa dữ liệu thiếu.
18. **Copy mẫu Servlet MVC sang WebFlux không điều chỉnh:** message codecs, lỗi validation và reactive wrappers khác nhau.

## 16. Checklist trước khi merge endpoint mới

- [ ] Đã xác định client gửi JSON, form URL-encoded, query string hay multipart.
- [ ] Đã dùng `@RequestBody` cho body được converter/codec hỗ trợ và `@ModelAttribute` cho dữ liệu form/query phù hợp.
- [ ] Đã phân biệt DTO input với entity và response DTO.
- [ ] Đã biết constructor/setter/record/creator nào thực sự tạo object.
- [ ] Đã kiểm tra tên JSON property và request parameter, đặc biệt case/kebab-case/indexed fields.
- [ ] Đã kiểm tra type conversion và handling của field sai định dạng.
- [ ] Đã bật `spring-boot-starter-validation` và đặt constraints/ `@Valid` ở đúng nơi.
- [ ] Nếu dùng `BindingResult`, đã đặt ngay sau đối số cần validate.
- [ ] Đã kiểm tra body rỗng, field thiếu, nullable và primitive default.
- [ ] Đã thiết kế error contract, không lộ exception details hoặc dữ liệu nhạy cảm.
- [ ] Đã giới hạn writable fields, dùng DTO riêng và có authorization phù hợp.
- [ ] Đã kiểm thử JSON/form/multipart theo đúng `Content-Type`, cả success lẫn failure.
- [ ] Nếu chạy WebFlux, đã kiểm tra reactive codec, error type và không dùng `block()`.
- [ ] Đã có MockMvc/WebTestClient hoặc integration tests bảo vệ trước hồi quy.

## 17. Kết luận

**`@RequestBody` và `@ModelAttribute` là hai con đường khác nhau để tạo dữ liệu đầu vào cho cùng một handler.** Với Spring MVC, `@RequestBody` đọc HTTP body qua message converter và dùng deserializer như Jackson để tạo DTO; `@ModelAttribute` tìm hoặc tạo model object rồi dùng data binder gán form/query/path/header values phù hợp. Cả hai có thể validate, nhưng lỗi parse/binding và khả năng giới hạn field khác nhau. Chọn annotation theo hợp đồng dữ liệu, thiết kế input DTO tách biệt, kiểm chứng creation/binding bằng test thực, và kiểm soát mass assignment trước khi đưa object đến service.

## Tài liệu chính thức tham khảo

- Spring Framework — MVC @RequestBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — MVC Data Binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — WebFlux @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
