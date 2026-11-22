# Phân biệt @ModelAttribute với @RequestBody và HttpMessageConverter trong Spring MVC

## 1. Cùng tạo Java object từ HTTP, nhưng **hai đường đi khác nhau**

Trong Spring MVC (Servlet stack), controller có thể nhận một đối tượng Java từ request bằng hai annotation quen thuộc:

~~~java
@PostMapping("/profiles/form")
String saveForm(@ModelAttribute ProfileForm form) {
    // form được tạo/lấy từ model rồi bind từ request values.
    return "ok";
}

@PostMapping("/profiles/json")
String saveJson(@RequestBody ProfileJson body) {
    // body được đọc bằng HttpMessageConverter.
    return "ok";
}
~~~

Hai đoạn trên là **snippet** cần đặt trong controller đã cấu hình, không phải file biên dịch độc lập. Tuy đều nhận object, **`@ModelAttribute` không phải alias của `@RequestBody`**:

- **`@ModelAttribute`**: tạo hoặc lấy **model attribute**, sau đó dùng **`WebDataBinder`/`ServletRequestDataBinder`** để bind request parameters (query, form), cùng URI variables/headers trong tích hợp MVC khi thích hợp; dữ liệu được ánh xạ vào các constructor arguments hoặc JavaBean properties.
- **`@RequestBody`**: đọc **nội dung HTTP message body** bằng một **`HttpMessageConverter`** phù hợp với Java type và HTTP `Content-Type`; ví dụ Jackson chuyển JSON object thành Java record/POJO.

Vì thế, request form và request JSON **không chỉ khác cú pháp**; chúng đi qua **hai cơ chế chuyển dữ liệu, báo lỗi và cấu hình bảo mật khác nhau**.

Ví dụ hai request đều diễn đạt hồ sơ của Lan:

~~~http
POST /profiles/form
Content-Type: application/x-www-form-urlencoded

name=Lan&age=26&newsletter=true
~~~

~~~http
POST /profiles/json
Content-Type: application/json

{"name":"Lan","age":26,"newsletter":true}
~~~

Request đầu thường đi với `@ModelAttribute` hoặc `@RequestParam`; request sau thường đi với `@RequestBody` và một JSON converter. Chọn annotation dựa trên **hợp đồng dữ liệu HTTP thực tế**, không chỉ dựa vào việc Java parameter có kiểu class hay record.

## 2. Bảng so sánh chi tiết

| Tiêu chí | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Mục tiêu | Tạo/lấy model attribute và **data bind** các giá trị request vào nó. | Đọc **message body** và deserialize thành một giá trị Java. |
| Nguồn dữ liệu điển hình | Query string, `application/x-www-form-urlencoded`, multipart form; tích hợp MVC có thể bổ sung URI template variables và headers. | Raw HTTP body: JSON, XML, plain text, bytes, v.v., tùy converter và Java type. |
| Thành phần thực thi | `ModelAttributeMethodProcessor`/`ServletModelAttributeMethodProcessor`, `WebDataBinder`, `ConversionService`, `PropertyEditor`, formatter. | `RequestResponseBodyMethodProcessor` và các `HttpMessageConverter` đã đăng ký. |
| Cách tạo target | Có thể lấy từ Model/Session, converter theo key hoặc qua constructor; tiếp theo constructor/property binding. | Converter tự tạo/deserialize object từ body (ví dụ Jackson đối với JSON). |
| Chuyển kiểu | Spring data binding/formatters; property paths như `address.city`, `items[0].name`. | Luật của converter và thư viện mapping (ví dụ Jackson JSON annotations, deserializer). |
| Phụ thuộc `Content-Type` | Với query/form thường dựa request parameter map, không cần JSON converter. | Converter được chọn theo HTTP media type và Java target type. |
| Kiểm tra `@Valid` | Có thể chạy **sau khi binding**, lỗi được chứa trong `BindingResult` hoặc ném exception nếu không có handler cục bộ. | Có thể chạy **sau khi deserialize thành công**; JSON sai cú pháp có thể thất bại trước validation. |
| Lỗi chuyển kiểu | Thường là `FieldError` mã `typeMismatch` trong `BindingResult`. | Thường là `HttpMessageNotReadableException` khi body không parse/deserialize được. |
| Không hỗ trợ media type | Request form/query không nhất thiết phụ thuộc message converter; `consumes` của mapping vẫn có thể áp dụng. | Không tìm thấy converter đọc đúng type/media type thường dẫn đến HTTP 415. |
| `BindingResult` | Có thể đặt **ngay sau** `@ModelAttribute`; phổ biến trong HTML forms. | Có thể đặt **ngay sau** `@RequestBody` để xử lý lỗi *validation* khi object deserialize được; không biến JSON lỗi cú pháp thành BindingResult. |
| Bảo mật input fields | Dùng form DTO, constructor binding, `@InitBinder`/`setAllowedFields` cho setter/property binding. | Dùng request DTO, cấu hình Jackson và kiểm tra quyền; `setAllowedFields` không phải whitelist cho JSON deserialization. |
| Phù hợp | HTML form, GET filter/query, multi-field request parameters, form upload. | REST API JSON/XML, raw text/bytes hoặc định dạng body được converter hỗ trợ. |

**Chính xác hơn:** `@RequestBody` **không có nghĩa "luôn là JSON"**. Nó dùng một `HttpMessageConverter`, có thể là JSON converter, `StringHttpMessageConverter`, `ByteArrayHttpMessageConverter` hoặc converter XML/form tùy cấu hình. Ngược lại, `@ModelAttribute` không phải cơ chế đọc JSON payload mặc định. 

## 3. Dòng xử lý bên trong Spring MVC

Sau khi `DispatcherServlet` chọn handler method, `RequestMappingHandlerAdapter` dùng hệ thống *argument resolvers* để cung cấp các tham số controller.

### 3.1. Với `@ModelAttribute`

~~~text
HTTP request
   |
   +-- ?name=Lan&age=26
   +-- form body: name=Lan&age=26
   +-- multipart form parts
   +-- URI variables/headers nếu tích hợp MVC cho phép
   |
   v
ServletModelAttributeMethodProcessor
   |
   +--> Tìm instance đã có trong Model / @SessionAttributes
   |    hoặc tạo bằng constructor / converter phù hợp
   |
   v
WebDataBinder / ServletRequestDataBinder
   |
   +--> constructor binding (nếu target được tạo từ arguments)
   +--> property binding, Spring ConversionService/formatters
   +--> @InitBinder: allowed fields, converters, validators
   +--> BindingResult: typeMismatch, required, suppressed fields
   |
   v
@Valid / @Validated nếu được yêu cầu
   |
   v
Controller nhận object (+ BindingResult nếu khai báo ngay sau)
~~~

Theo tài liệu MVC, request parameters bao gồm **query parameters và form parameters** theo Servlet API. Khi MVC bind `@ModelAttribute`, URI template variables và request headers có thể được thêm nếu **không ghi đè** request parameters cùng tên; tên header có thể được chuẩn hóa bỏ dấu gạch ngang. Đây là hành vi của tích hợp MVC, **không phải lời hứa rằng gọi thủ công `new ServletRequestDataBinder(...).bind(request)` sẽ tự đọc mọi header/cookie**.

Lưu ý `@ModelAttribute` có thể lấy đối tượng đã có trong model trước khi bind, bao gồm model attribute do method khác chuẩn bị hoặc session attribute đã khai báo. Vì thế không được mặc nhiên cho rằng mọi lần đều tạo object mới bằng no-arg constructor. Trong Spring MVC hiện đại, constructor binding cũng hỗ trợ immutable DTO/record khi thông tin tên parameter phù hợp.

### 3.2. Với `@RequestBody`

~~~text
HTTP request
   |
   +-- Content-Type: application/json
   +-- Body: {"name":"Lan","age":26}
   |
   v
RequestResponseBodyMethodProcessor
   |
   +--> Chọn HttpMessageConverter phù hợp:
   |      canRead(targetType, contentType)
   |
   +--> JSON converter / Jackson: deserialize body -> object
   |    (hoặc String/byte[]/XML converter tương ứng)
   |
   +--> @Valid / @Validated nếu có
   |
   v
Controller nhận object (+ Errors/BindingResult khi hợp lệ)
~~~

Nếu body thiếu khi `@RequestBody(required=true)` (mặc định) hoặc nội dung sai cú pháp/không thể deserialize, controller có thể chưa được gọi. Nếu không có converter cho media type/target type, request có thể bị HTTP 415. Đây là lỗi ở bước đọc message, không phải lỗi JavaBean field binding bằng `WebDataBinder`.

**Lưu ý về phản hồi:** `@ResponseBody` (và `@RestController`) sử dụng message conversion theo **chiều ghi response**, còn `@RequestBody` sử dụng theo **chiều đọc request**. Hai hướng dùng cùng trừu tượng `HttpMessageConverter` nhưng thực hiện nghiệp vụ khác nhau.

## 4. Chi tiết `@ModelAttribute`: object, property và nguồn tham số

### 4.1. Trường hợp GET/filter

~~~java
@GetMapping("/products")
String search(@ModelAttribute("filter") SearchFilter filter,
              Model model) {
    model.addAttribute("items", service.search(filter));
    return "product-list";
}
~~~

Đây là snippet với `SearchFilter`/`service` giả định. Với request:

~~~http
GET /products?keyword=java&minPrice=100
~~~

Spring có thể tạo/lấy `SearchFilter` và bind `keyword`, `minPrice` qua property setters hoặc constructor arguments. Không có JSON body cần đọc. Nếu dùng `int` hoặc `BigDecimal`, Spring áp dụng conversion/formatter đã cấu hình; parse sai có thể tạo lỗi binding.

### 4.2. Trường hợp HTML form

~~~html
<form method="post" action="/profiles/form">
  <input name="name" value="Lan">
  <input name="age" type="number" value="26">
  <input type="hidden" name="_newsletter" value="present">
  <input name="newsletter" type="checkbox" value="true">
  <button type="submit">Save</button>
</form>
~~~

HTTP `application/x-www-form-urlencoded` thường được Servlet container phân tích thành request parameters; Spring data binder nhận các tên như `name`, `age` và `newsletter`. Field marker `_newsletter` báo rằng checkbox tồn tại trong form nhưng có thể không được tick; `WebDataBinder` dùng marker để reset giá trị nếu field thật không được gửi.

Cũng có thể dùng tên nested `address.city` hoặc indexed `items[0].quantity`. Đó là **property paths** của Spring, khác schema JSON; kiểm soát bề mặt property binding để tránh client tự gửi `admin=true`, `ownerId=...` hay chỉ số collection rất lớn.

### 4.3. Constructor binding và model đã có

Nếu DTO bất biến, Spring MVC có thể bind các constructor parameters từ request values. Ví dụ:

~~~java
public record SearchFilter(String keyword, Integer minPrice) {}
~~~

Khi truy cập `GET /products?keyword=java&minPrice=100`, MVC có thể tạo record bằng constructor thay vì setter. Tên tham số cần được Spring xác định, thường qua metadata Java hoặc annotations; `@BindParam` cho phép ánh xạ tên request khác tên Java. Spring Framework 6.1+ có thêm `DataBinder#setDeclarativeBinding(true)` để ưu tiên constructor binding, chỉ cho setter/property binding khi có allowed fields.

Nếu một object đã nằm trong Model hoặc `@SessionAttributes`, Spring có thể bind vào instance đó thay vì tạo mới. Khi muốn lấy model attribute **mà không cho request ghi đè**, có thể dùng `@ModelAttribute(binding=false)`.

### 4.4. `@InitBinder` và bảo vệ property

Ví dụ controller thiết lập danh sách field được phép:

~~~java
@InitBinder("profile")
void configureBinding(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "newsletter");
}
~~~

Đoạn trên là **snippet bên trong controller**. `setAllowedFields` là whitelist cho **property binding**, không phải cơ chế kiểm soát quyền ở tầng nghiệp vụ. `BindingResult#getSuppressedFields()` có thể ghi lại field bị chặn để ứng dụng quyết định báo lỗi hay log.

**Nguyên tắc an toàn:** không bind trực tiếp entity JPA có field nội bộ nhạy cảm; dùng request/form DTO chỉ có các field được client phép thay đổi. Kể cả khi có `@Valid`, vẫn phải kiểm tra authorization cho hành động cập nhật.

## 5. Chi tiết `@RequestBody`: body, converter và Content-Type

### 5.1. `HttpMessageConverter` đọc cái gì?

`org.springframework.http.converter.HttpMessageConverter<T>` định nghĩa khả năng đọc/ghi HTTP message cho một kiểu Java và media type. Trong Spring MVC, converter được đăng ký theo cấu hình; những triển khai thường gặp:

| Converter | Media type thường gặp | Target điển hình |
| --- | --- | --- |
| Jackson JSON converter (ví dụ `MappingJackson2HttpMessageConverter` trong Spring Framework 6.x) | `application/json`, tương thích JSON | POJO, record, cấu trúc JSON có cấu hình phù hợp. |
| `StringHttpMessageConverter` | `text/*` và những text media types được hỗ trợ | `String`. |
| `ByteArrayHttpMessageConverter` | Nhiều media types | `byte[]`. |
| `FormHttpMessageConverter` | `application/x-www-form-urlencoded` | `MultiValueMap<String, String>` (không phải mọi JavaBean). |
| XML converter nếu được cấu hình | `application/xml`, `text/xml` | Bean/DTO theo thư viện mapping. |

Các converter có `canRead(...)`/`read(...)` và `canWrite(...)`/`write(...)` hoặc variants theo type. Spring chọn converter phù hợp dựa vào **kiểu argument**, `Content-Type` và cấu hình. JSON mapping chịu các luật của Jackson (field names, constructor/record support, custom serializer/deserializer, unknown fields...); **nó không dùng danh sách allowed fields của `ServletRequestDataBinder` để đọc JSON**.

**Điểm đặc biệt với form:** mặc dù có `FormHttpMessageConverter`, Spring MVC khuyến nghị dùng `@RequestParam` hoặc `@ModelAttribute` cho form-urlencoded. Servlet API có thể parse request body khi đọc parameters khiến việc đọc lại body bằng `@RequestBody` không luôn đáng tin; `FormHttpMessageConverter` chủ yếu đọc form thành `MultiValueMap` trong ngữ cảnh phù hợp. Đừng suy luận "converter hỗ trợ x-www-form-urlencoded" đồng nghĩa `@RequestBody MyForm` mặc định deserialize form thành POJO như Jackson đọc JSON.

### 5.2. Phân biệt `Content-Type`, `consumes`, `Accept` và `produces`

- Request header `Content-Type` mô tả **body đang gửi**, giúp Spring chọn converter đọc.
- `@PostMapping(consumes = "application/json")` là **điều kiện chọn handler**; gửi không đúng media type có thể bị HTTP **415 Unsupported Media Type** trước khi handler đọc body.
- Request header `Accept` nói client muốn **response type** nào.
- `@GetMapping(produces = "application/json")` là điều kiện trên **response representation**; nếu không chấp nhận được có thể gặp HTTP **406 Not Acceptable**.

Không nhầm `Content-Type` với `Accept`. Một API có thể **nhận JSON** nhưng **trả plain text** nếu method trả `String` với `@ResponseBody`.

### 5.3. Lỗi JSON xảy ra *trước* validation

Với `@Valid @RequestBody JsonProfile`:

~~~http
POST /profiles/json
Content-Type: application/json

{"name":"Lan","age":"not-a-number"}
~~~

Nếu cấu hình Jackson không thể chuyển giá trị đó thành `Integer`, Spring báo lỗi đọc message, thường là `HttpMessageNotReadableException` → HTTP 400 theo xử lý mặc định. Nếu body JSON parse thành công, nhưng `name=""` vi phạm `@NotBlank` hoặc `age=16` vi phạm `@Min(18)`, lúc ấy Bean Validation báo lỗi, thường là `MethodArgumentNotValidException` → HTTP 400 nếu controller không nhận `Errors/BindingResult` cục bộ.

Đừng dựa vào tên lỗi `typeMismatch` từ `WebDataBinder` cho JSON parse failure. Cũng không dùng try/catch trong controller để bắt JSON syntax sai: controller chưa chắc đã được gọi.

## 6. Ví dụ Spring Boot 3.x, Java 17+: cùng một dữ liệu qua hai pipeline

Tạo một dự án **Spring Boot 3.x**, **Java 17+**, Maven. Thêm các dependencies sau trong `pom.xml` (hoặc chọn Web/Validation khi tạo dự án):

~~~xml
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
~~~

Code dưới đây gồm **bốn file Java ở `src/main/java/com/example/binding/`** và một file kiểm thử ở `src/test/java/com/example/binding/`. Các file không có package placeholder, và mỗi `public` top-level class/record có đúng tên file.

### 6.1. `BindingComparisonApplication.java`

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingComparisonApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingComparisonApplication.class, args);
    }
}
~~~

### 6.2. `ProfileForm.java`: JavaBean dành cho form/query binding

~~~java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ProfileForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    private boolean newsletter;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public boolean isNewsletter() {
        return newsletter;
    }

    public void setNewsletter(boolean newsletter) {
        this.newsletter = newsletter;
    }
}
~~~

`ProfileForm` có constructor không tham số mặc định, getter/setter để binder ghi dữ liệu. `Integer` được dùng thay `int` để `@NotNull` có thể nhận diện trường hợp không gửi `age`; `@Min(18)` kiểm tra tuổi đủ lớn.

### 6.3. `ProfileJson.java`: record dành cho JSON body

~~~java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ProfileJson(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        boolean newsletter) {
}
~~~

Jackson đọc các JSON properties và tạo record; không có setter. `@Valid` trên controller sẽ kích hoạt validation sau khi deserialize thành công. Record không mặc nhiên chống mọi rủi ro overposting nếu chứa field server-only; vì thế chỉ khai báo đúng input được phép dùng.

### 6.4. `ProfileController.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    // Chỉ cho phép những property có trong hợp đồng form.
    @InitBinder("profile")
    void configureFormBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "newsletter");
    }

    // GET query string → @ModelAttribute (không chạy @Valid ở ví dụ GET).
    @GetMapping("/query")
    public String query(
            @ModelAttribute("profile") ProfileForm profile) {
        return "QUERY:" + profile.getName() + ":"
                + profile.getAge();
    }

    // Form-urlencoded → WebDataBinder/JavaBean properties.
    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("profile") ProfileForm profile,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body("FORM_INVALID");
        }

        return ResponseEntity.ok(
                "FORM:" + profile.getName() + ":"
                + profile.getAge() + ":"
                + profile.isNewsletter());
    }

    // JSON body → HttpMessageConverter (thường Jackson).
    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public String json(@Valid @RequestBody ProfileJson profile) {
        return "JSON:" + profile.name() + ":"
                + profile.age() + ":"
                + profile.newsletter();
    }

    // JSON hợp cú pháp nhưng vi phạm Bean Validation:
    // xử lý lỗi trực tiếp bằng BindingResult ngay sau @RequestBody.
    @PostMapping(path = "/json-checked",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> jsonChecked(
            @Valid @RequestBody ProfileJson profile,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("JSON_INVALID");
        }

        return ResponseEntity.ok("JSON_OK");
    }
}
~~~

**Điểm đáng chú ý trong controller:**

- `@RestController` khiến các `String` được gửi vào **HTTP response body**, không được coi là tên view. Đây là chiều **ghi** qua converter.
- `@InitBinder("profile")` cấu hình binder cho model attribute `profile`, đặt allowlist cho **property binding**. Nó **không** kiểm soát Jackson đang deserialize `ProfileJson`.
- `@Valid` là bước validation, khác với binding/deserialize. `BindingResult` xuất hiện **ngay sau** tham số được validate để Spring có thể trao lỗi cho controller.
- Nếu khách gửi `admin=true` vào form, binder chặn vì field không nằm trong allowed fields; controller chủ động từ chối request có suppressed fields.
- `/json` không có `BindingResult`, nên lỗi Bean Validation theo mặc định được framework chuyển thành HTTP 400. `/json-checked` xử lý cùng nhóm lỗi **bằng code controller** khi body đã chuyển thành object thành công.

### 6.5. `BindingComparisonApplicationTest.java`: MockMvc kiểm tra end-to-end MVC

Tạo file tại `src/test/java/com/example/binding/BindingComparisonApplicationTest.java`:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BindingComparisonApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryParametersUseModelAttribute() throws Exception {
        mvc.perform(get("/profiles/query")
                    .param("name", "Hoa")
                    .param("age", "30"))
                .andExpect(status().isOk())
                .andExpect(content().string("QUERY:Hoa:30"));
    }

    @Test
    void formFieldsUseWebDataBinder() throws Exception {
        mvc.perform(post("/profiles/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "26")
                    .param("newsletter", "true"))
                .andExpect(status().isOk())
                .andExpect(content().string("FORM:Lan:26:true"));
    }

    @Test
    void badFormNumberIsBindingError() throws Exception {
        mvc.perform(post("/profiles/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void extraFormPropertyIsSuppressedByAllowlist()
            throws Exception {
        mvc.perform(post("/profiles/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "26")
                    .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void jsonBodyUsesMessageConverter() throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Minh","age":25,"newsletter":true}
                            """))
                .andExpect(status().isOk())
                .andExpect(content().string("JSON:Minh:25:true"));
    }

    @Test
    void validJsonSyntaxButInvalidFieldsProduces400()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","age":16,"newsletter":false}
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void localBindingResultCanHandleJsonValidation()
            throws Exception {
        mvc.perform(post("/profiles/json-checked")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","age":16,"newsletter":false}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("JSON_INVALID"));
    }

    @Test
    void malformedJsonFailsBeforeControllerValidation()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongMediaTypeDoesNotMatchJsonMapping()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("name=Lan&age=26"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void missingRequiredRequestBodyProduces400()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy test từ root dự án Maven:

~~~bash
./mvnw test -Dtest=BindingComparisonApplicationTest
~~~

Trên Windows dùng `mvnw.cmd test -Dtest=BindingComparisonApplicationTest`, hoặc `mvn test -Dtest=BindingComparisonApplicationTest` nếu đã cài Maven.

**Kết quả mong đợi:** **10 test pass** trong một dự án Boot 3.x Web + Validation + Test mặc định. Dưới đây là các **HTTP response body/status dự kiến**, không phải toàn bộ log Maven:

| Request/test | HTTP status | Body quan trọng |
| --- | --- | --- |
| GET `/profiles/query?name=Hoa&age=30` | 200 | `QUERY:Hoa:30` |
| POST form `name=Lan&age=26&newsletter=true` | 200 | `FORM:Lan:26:true` |
| POST form `age=not-a-number` | 400 | `FORM_INVALID` |
| POST form kèm `admin=true` | 400 | `FORM_INVALID` |
| POST JSON hợp lệ `{"name":"Minh","age":25,...}` | 200 | `JSON:Minh:25:true` |
| POST JSON field sai `name=""`, `age=16` | 400 | Framework response lỗi (format có thể tùy Spring Boot). |
| POST JSON sai field tại `/json-checked` | 400 | `JSON_INVALID` |
| POST JSON sai cú pháp | 400 | Framework response lỗi. |
| POST body `text/plain` vào endpoint chỉ nhận JSON | 415 | Framework response lỗi. |
| POST JSON không có body khi `required=true` | 400 | Framework response lỗi. |

Lưu ý **response body mặc định khi lỗi** phụ thuộc cấu hình error handling, phiên bản Spring và `@ControllerAdvice`. Test do đó khẳng định status cho các trường hợp framework xử lý, chỉ assert body exact cho các response do controller tự tạo. Với Spring Security được bật thêm, CSRF/authentication có thể thay đổi kết quả request POST và cần cấu hình test phù hợp; demo này chỉ dùng các starter nêu ở trên.

### Chạy thử bằng curl

Khi ứng dụng đang chạy với `./mvnw spring-boot:run`:

~~~bash
curl -i "http://localhost:8080/profiles/query?name=Hoa&age=30"

curl -i -X POST "http://localhost:8080/profiles/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan&age=26&newsletter=true"

curl -i -X POST "http://localhost:8080/profiles/json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Minh","age":25,"newsletter":true}'
~~~

Ví dụ lệnh shell dạng Unix. Trên Windows PowerShell, dùng `curl.exe` nếu muốn cú pháp curl thật; quy tắc escape/line continuation có thể khác. Kết quả dự kiến lần lượt có body `QUERY:Hoa:30`, `FORM:Lan:26:true`, `JSON:Minh:25:true` và HTTP 200.

## 7. Validation và lỗi HTTP: hai đường đi cần phân biệt

### 7.1. Binding errors khác JSON parse errors

| Tình huống | Bước gặp lỗi | Exception/kết quả điển hình |
| --- | --- | --- |
| `@ModelAttribute` với `age=abc` | Spring conversion khi binding | `BindingResult` có `FieldError` mã `typeMismatch`; nếu không được xử lý, MVC có thể báo `MethodArgumentNotValidException`. |
| `@ModelAttribute` với `age=16` và `@Min(18)` | Bean Validation sau binding | Field error trong `BindingResult` hoặc MVC trả HTTP 400. |
| `@RequestBody` với JSON hỏng `{"name":` | Converter/Jackson chưa deserialize xong | `HttpMessageNotReadableException`, thường HTTP 400. |
| `@RequestBody` với JSON hợp lệ nhưng `name=""` | Bean Validation sau deserialize | `MethodArgumentNotValidException`, thường HTTP 400 nếu không có `BindingResult` ngay sau. |
| JSON endpoint nhận `Content-Type: text/plain` | Chọn mapping hoặc converter | Thường HTTP 415; `consumes` có thể loại handler trước bước converter. |
| `@RequestBody(required=true)` nhưng body rỗng | Đọc required body | Thường HTTP 400; đặt `required=false` thì cần tự xử lý null. |
| Method có constraint trực tiếp trên argument khác | Method validation của Spring MVC | Có thể là `HandlerMethodValidationException` tùy chữ ký và phiên bản. |

Để xem lỗi cục bộ:

~~~java
@PostMapping("/form")
String handle(@Valid @ModelAttribute("profile") ProfileForm form,
              BindingResult result) {
    if (result.hasErrors()) {
        for (var error : result.getFieldErrors()) {
            System.out.println(
                    error.getField() + ": " + error.getCode());
        }
        return "profile-form";
    }
    return "success";
}
~~~

Đây là snippet cho một **controller trả tên view**, không phải method thay thế trong `@RestController` của ví dụ phần 6. `BindingResult` phải ngay sau `@ModelAttribute` tương ứng. Với `@RequestBody`, có thể đặt `Errors/BindingResult` ngay sau nếu muốn xử lý **validation errors** khi body đã deserialize được; không kỳ vọng bắt được lỗi cú pháp JSON tại đây.

### 7.2. `@Valid`, `@Validated` và lỗi của method validation

- `@Valid` trên bean input yêu cầu Bean Validation kiểm tra các annotations ràng buộc bên trong DTO. `@Validated` có thể chọn validation groups.
- Với một argument được validate riêng biệt mà không có `BindingResult` phù hợp, lỗi thường trở thành `MethodArgumentNotValidException`.
- Nếu method có constraints trực tiếp trên arguments hoặc return value, Spring MVC (đặc biệt từ Spring Framework 6.1) có thể chuyển sang **method validation**, khi đó loại exception có thể là `HandlerMethodValidationException`.
- Trước khi trả thông báo lỗi cho client, hãy chuyển chúng thành response có cấu trúc ổn định tại tầng `@ControllerAdvice` hoặc handler được thiết kế; không phơi exception stack trace.

**Không** suy luận "có `@Valid` thì mọi lỗi đều tự động là HTTP 400" trong mọi ứng dụng: custom exception handler, security, method validation và cấu hình MVC có thể ảnh hưởng status. Các quy tắc trên là hành vi phổ biến với setup Spring Boot MVC mặc định.

## 8. Multipart, @RequestParam, @RequestPart và một hiểu nhầm phổ biến

Trường hợp form upload:

~~~http
POST /profiles/photo
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="name"

Lan
--...
Content-Disposition: form-data; name="avatar"; filename="a.png"
Content-Type: image/png

...file bytes...
--...--
~~~

Với dữ liệu form/multipart, `@ModelAttribute` trên form object có property `MultipartFile avatar` hoặc `@RequestParam("avatar") MultipartFile file` là lựa chọn thông dụng. Với một multipart request chứa **part JSON** được gắn `Content-Type: application/json`, có thể dùng `@RequestPart` để converter deserialize riêng part đó:

~~~java
@PostMapping(path = "/photos",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String upload(@Valid @RequestPart("metadata") PhotoMetadata meta,
                     @RequestPart("avatar") MultipartFile avatar) {
    // Các part có thể được xử lý khác nhau.
    return "ok";
}
~~~

Đây là **snippet riêng**; cần lớp `PhotoMetadata`, imports và xử lý upload an toàn phù hợp. `@RequestPart` có thể dùng `HttpMessageConverter` cho part metadata, trong khi `@ModelAttribute` bind form fields. **Không nhầm `@RequestBody JsonProfile` với việc tự động hợp nhất tất cả multipart parts thành một object JSON.**

Trong các API đơn giản, `@RequestParam String name` đọc **một giá trị** request parameter, còn `@ModelAttribute ProfileForm form` bind **nhiều giá trị** vào object. `@RequestHeader`/`@CookieValue` đọc header/cookie rõ ràng khi cần, thay vì gộp chúng không kiểm soát vào DTO.

## 9. Bảo mật: tránh overposting ở cả hai pipeline

Dù qua form binder hay JSON converter, dữ liệu từ client **không đáng tin cậy**. Cùng một kịch bản `admin=true` có thể rất nguy hiểm nếu controller bind trực tiếp vào entity có quyền cập nhật thuộc tính này.

### 9.1. Với `@ModelAttribute`

- Ưu tiên **form/request DTO** chỉ có những field cần nhận. Nếu dùng setter/property binding, cấu hình allowlist `setAllowedFields(...)`.
- Xem xét immutable constructor binding/`setDeclarativeBinding(true)` nếu phiên bản Spring phù hợp.
- Với nested properties, chỉ cho phép các đường dẫn có chủ đích; không dùng wildcard quá rộng cho entity graph.
- Kiểm tra `getSuppressedFields()` khi cần từ chối request cố gắng bind các field bị chặn.
- Không nhầm `@Valid` với authorization: validation kiểm tra **giá trị**, không kiểm tra **quyền sửa property**.

### 9.2. Với `@RequestBody`

- **Không áp dụng `WebDataBinder#setAllowedFields` như JSON field whitelist**; converter có quy tắc deserialization riêng.
- Dùng request DTO/record chỉ chứa các trường cho phép nhập. Cấu hình mapper/annotations như `@JsonProperty`, `@JsonIgnore` khi phù hợp, nhưng không coi một annotation là thay thế authorization.
- Không truyền trực tiếp toàn bộ JSON request vào JPA entity rồi gọi `save`. Khi cập nhật, ánh xạ thủ công các field được phép vào entity sau khi xác minh quyền và giá trị.
- Phân biệt thiếu field, null, unknown JSON property và rule validation. Jackson có thể cấu hình xử lý unknown fields theo nhiều cách; **không giả định mọi field lạ tự động bị từ chối** nếu không kiểm thử.
- Thiết lập giới hạn kích thước body, độ sâu payload và bảo vệ DoS ở tầng web/server/gateway phù hợp.

**Quy tắc nhất quán:** chọn input contract hẹp, thực hiện validation, rồi kiểm tra authorization tại tầng nghiệp vụ. Bất kể annotation, server-only fields (ví dụ `role`, `ownerId`, `balance`) phải do server quyết định.

## 10. Câu hỏi nhanh và lỗi thường gặp

### "Gửi JSON nhưng `@ModelAttribute` nhận object rỗng?"

Vì `@ModelAttribute` đọc request values thông qua cơ chế binder (query/form), **không tự dùng Jackson để parse raw JSON body**. Dùng `@RequestBody` với `Content-Type: application/json` nếu muốn deserialize JSON. Nếu API cần cả query và body, khai báo các argument riêng, ví dụ `@RequestParam String source` và `@RequestBody JsonProfile payload`.

### "Dùng `@RequestBody` cho form-urlencoded được không?"

Một số converter hỗ trợ `application/x-www-form-urlencoded` thành `MultiValueMap<String,String>`. Nhưng trong Servlet MVC, truy cập request parameters có thể làm form body bị parse và không đọc lại ổn định qua `@RequestBody`. Spring khuyến nghị **`@RequestParam`/`@ModelAttribute` cho form**; không mặc nhiên mong đợi `@RequestBody MyPojo` parse HTML form giống JSON.

### "Tại sao `@RequestBody` báo 400 nhưng `@ModelAttribute` trả `FieldError`?"

JSON body phải được converter deserialize thành object trước khi chạy `@Valid`. Nếu sai cú pháp, converter thất bại → `HttpMessageNotReadableException`. Với form, binder có thể ghi `typeMismatch` vào `BindingResult`. Nếu không có handler cục bộ, Spring MVC vẫn có thể chuyển binding/validation errors thành HTTP 400.

### "`@ModelAttribute` phải ghi rõ trên mọi tham số không?"

Trong Spring MVC, một tham số phức tạp không được resolver khác xử lý có thể được hiểu là **implicit `@ModelAttribute`**. Tuy nhiên, khai báo **tường minh** giúp đọc code, làm rõ hợp đồng API và hỗ trợ AOT/native image tốt hơn. Đừng xem việc bỏ annotation là một cách "không bind".

### "Có thể dùng `@ModelAttribute` ở cấp phương thức không?"

Có, nhưng **ý nghĩa khác**: method có `@ModelAttribute` trong `@Controller`/`@ControllerAdvice` thường **chuẩn bị giá trị Model** trước khi handler chạy; còn `@ModelAttribute` trên **parameter của handler** yêu cầu lấy/bind model object. Không nhầm hai vai trò.

### "Mọi lỗi JSON đều là lỗi `@Valid`?"

Không. JSON có thể sai cú pháp, thiếu body, sai kiểu dữ liệu và lỗi converter trước khi Bean Validation chạy. Cần quan sát **bước lỗi** và loại exception; đừng gom mọi lỗi đọc HTTP thành "constraint violation".

### "Tại sao `@ResponseBody` lại xuất hiện cùng chủ đề?"

Vì `HttpMessageConverter` có **hai chiều**: `@RequestBody` đọc body vào Java object; `@ResponseBody` ghi Java object/String ra HTTP response. `@RestController` bao gồm `@ResponseBody`. Đây là cặp khái niệm dễ nhớ, nhưng không làm `@ModelAttribute` trở thành converter.

## 11. Checklist lựa chọn nhanh

| Dữ liệu client gửi | Annotation nên cân nhắc | Ghi chú |
| --- | --- | --- |
| `GET /search?keyword=java&size=10` | `@RequestParam` cho vài field; `@ModelAttribute` cho filter DTO. | Không cần JSON parser. |
| HTML `application/x-www-form-urlencoded` | `@ModelAttribute` hoặc `@RequestParam`. | Dùng form DTO, `BindingResult` và allowlist. |
| REST `application/json` | `@RequestBody`. | JSON converter + `@Valid`, request DTO. |
| Plain text body | `@RequestBody String`. | `StringHttpMessageConverter` nếu media type phù hợp. |
| Raw bytes body | `@RequestBody byte[]`. | Kiểm soát kích thước. |
| Multipart form upload | `@ModelAttribute`/`@RequestParam MultipartFile`. | Bind form fields + file parts. |
| Multipart gồm JSON metadata riêng và file | `@RequestPart`. | Converter đọc JSON **part** theo `Content-Type` của part. |
| Cần cả query param và JSON body | `@RequestParam` + `@RequestBody` ở hai tham số. | Mỗi nguồn có hợp đồng riêng. |

**Tóm tắt một câu:** **`@ModelAttribute` = model + request parameter/property binding; `@RequestBody` = message body + `HttpMessageConverter`**. Sau bước chuyển dữ liệu, cả hai đều có thể được validate bằng `@Valid`, nhưng cách nhận nguồn, cơ chế ánh xạ, lỗi chuyển đổi và biện pháp kiểm soát field **khác nhau**.

## Tài liệu tham khảo

- Spring Framework — `@ModelAttribute` trong controller, request parameter/URI/header sources, constructor/property binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — `@RequestBody`, message conversion, validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — **HTTP Message Conversion** và các converter: https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html
- Spring Framework — **MVC Data Binding** và security/model design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — **MVC Validation** (MethodArgumentNotValidException/HandlerMethodValidationException): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — **Multipart Forms** (`@RequestPart`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
