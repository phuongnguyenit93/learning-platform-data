# Spring MVC — @ModelAttribute và liên kết dữ liệu biểu mẫu (form data binding)

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích `@ModelAttribute` trên **tham số controller**: lấy/tạo đối tượng model rồi liên kết các giá trị của HTTP request vào thuộc tính Java.
- Nhận form HTML (`application/x-www-form-urlencoded`) và query parameters mà không phải đọc từng trường bằng `@RequestParam`.
- Hiểu JavaBean/property binding, constructor binding, nested property, danh sách và chuyển đổi kiểu.
- Kết hợp `@Valid` hoặc `@Validated` với `BindingResult` để xử lý lỗi đầu vào.
- Phân biệt `@ModelAttribute` trên **tham số** và trên **phương thức**; phân biệt `@ModelAttribute`, `@RequestParam`, `@RequestBody`.
- Hạn chế trường được phép bind để tránh client sửa thuộc tính ngoài ý muốn.

Bối cảnh: **Spring MVC (Servlet stack)**, Java 17+; ví dụ thực hành dùng Spring Boot 3.5.0 và Spring Framework 6.2.x. Không nhầm cơ chế MVC với Spring WebFlux.

## 2. Từ form HTML đến đối tượng Java

Một form gửi request như sau:

~~~http
POST /api/register HTTP/1.1
Content-Type: application/x-www-form-urlencoded

fullName=Lan%20Nguyen&email=lan%40example.com&age=22&address.city=Da%20Nang&interests=java&interests=spring
~~~

Đoạn body chứa các cặp `name=value`, có thể lặp key `interests`. Trong Spring MVC, request parameters theo Servlet bao gồm **query string** và **dữ liệu form** mà Servlet giải mã; vì vậy Spring có thể dùng chúng để điền một object:

~~~java
@PostMapping("/register")
public String register(@ModelAttribute("registration") RegistrationForm form) {
    // form.getFullName(), form.getAge(), form.getAddress()...
    return "success";
}
~~~

Đoạn này chỉ minh họa chữ ký handler; để chạy độc lập, xem dự án ở mục 8.

**Luồng xử lý** thường gặp:

1. Spring MVC chọn handler dựa trên URL, HTTP method và các điều kiện mapping.
2. Spring tìm model attribute tên `registration` (nếu đã có trong model/session theo cấu hình) hoặc tạo đối tượng mới.
3. `WebDataBinder` lấy dữ liệu request, liên kết với constructor hoặc các thuộc tính writable và chuyển đổi chuỗi sang kiểu Java.
4. Nếu có `@Valid`/`@Validated`, Spring chạy validation sau khi binding.
5. Spring truyền object và kết quả lỗi (nếu controller khai báo `BindingResult`) vào handler.
6. Handler quyết định trả về view, redirect hoặc response HTTP.

Theo cơ chế Spring MVC hiện đại, giá trị bind có thể đến từ request parameters, URI path variables và headers. Khi trùng tên, request parameter ưu tiên hơn path variable/header; tên header có dấu gạch ngang được chuẩn hóa theo quy tắc binder. Với form thông thường, hãy tập trung vào field name và request parameters, và tránh phụ thuộc ngầm vào nguồn khác.

## 3. Thiết kế form object theo quy tắc JavaBean

~~~java
public class ProfileForm {
    private String displayName;
    private Integer age;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Handler:

~~~java
@PostMapping("/profiles")
public String save(@ModelAttribute("profile") ProfileForm form) {
    // Trường displayName và age đã được bind.
    return "profile-success";
}
~~~

Form HTML:

~~~html
<form method="post" action="/profiles">
  <label>Tên <input type="text" name="displayName"></label>
  <label>Tuổi <input type="number" name="age"></label>
  <button type="submit">Lưu</button>
</form>
~~~

`name="displayName"` khớp tên property `displayName`; `name="age"` khớp `age`. Với property binding dựa trên JavaBean, setter cho Spring cách gán giá trị. Thông thường Spring tạo object bằng constructor không tham số rồi gọi các setter phù hợp; Spring còn hỗ trợ **constructor binding** dựa trên tên tham số constructor. Hai chiến lược có thể cùng tham gia vào quá trình binding theo cấu hình mặc định.

Không suy ra rằng annotation `@ModelAttribute` tự tạo bảng cơ sở dữ liệu hoặc lưu thông tin người dùng: nó chỉ chuẩn bị object trong request/model. Các thao tác business và lưu trữ nằm ở service/repository.

### 3.1. Tên model attribute có ý nghĩa gì?

`@ModelAttribute("profile")` đặt tên attribute là `profile`. Tên này dùng để tìm/đưa object vào model, xác định mục tiêu `@InitBinder("profile")`, và gắn BindingResult của đối tượng. **Tên property được bind** vẫn là `displayName`, `age`, v.v.; input HTML không cần tiền tố `profile.` khi bind đối tượng top-level này.

Nếu không chỉ rõ tên, Spring có thể suy ra theo kiểu đối tượng, ví dụ `ProfileForm` → `profileForm`. Dùng tên tường minh khi cấu trúc view và binder cần nhất quán. Với tham số phức tạp không được argument resolver khác xử lý, Spring MVC có thể ngầm coi đó là `@ModelAttribute`; khai báo tường minh giúp rõ ý và an toàn hơn cho ứng dụng native/AOT.

## 4. Nested fields, danh sách và chuyển đổi kiểu

Giả sử form class:

~~~java
public class OrderForm {
    private Customer customer = new Customer();
    private List<String> tags = new ArrayList<>();

    public Customer getCustomer() { return customer; }
    public void setCustomer(Customer customer) { this.customer = customer; }
    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }

    public static class Customer {
        private String name;
        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
    }
}
~~~

Cần import `java.util.ArrayList` và `java.util.List`. Form data tương ứng:

~~~text
customer.name=Lan
tags=java
tags=spring
~~~

- `customer.name`: nested property path, được điền vào `orderForm.getCustomer().getName()`.
- Hai trường `tags`: Spring có thể nhận nhiều giá trị của cùng key rồi chuyển sang `List<String>`.
- Với phần tử đối tượng trong list, cú pháp dạng `items[0].name` có thể được binder hỗ trợ nếu cấu trúc object, quyền ghi và cấu hình phù hợp; tránh tạo số chỉ mục quá lớn từ dữ liệu không tin cậy.

Một ví dụ gửi bằng curl:

~~~bash
curl --get 'http://localhost:8080/orders/preview' \
  --data-urlencode 'customer.name=Lan' \
  --data-urlencode 'tags=java' \
  --data-urlencode 'tags=spring'
~~~

Lệnh trên minh họa **cách gửi request parameters**; endpoint `/orders/preview` chưa được cài đặt trong ứng dụng mẫu ở mục 8.

### 4.1. Chuyển đổi kiểu

Data binding sử dụng cơ chế chuyển đổi dữ liệu của Spring:

| Request parameter | Property Java | Kết quả thường gặp |
| --- | --- | --- |
| `age=22` | `Integer age` | Số nguyên 22 |
| `active=true` | `Boolean active` | `true` |
| `birthDate=2026-05-01` | `LocalDate birthDate` với `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` | Ngày 2026-05-01 |
| `age=abc` | `Integer age` | Lỗi type mismatch, ghi trong binding errors |
| `address.city=Hue` | Nested property `address.city` | `address.getCity() == "Hue"` nếu object/binder phù hợp |

Ví dụ ngày:

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate birthDate;
~~~

Cần import `java.time.LocalDate` và `org.springframework.format.annotation.DateTimeFormat`. Với định dạng riêng hoặc kiểu nghiệp vụ, đăng ký `Converter`, `Formatter` hoặc cấu hình `ConversionService` phù hợp. Chuyển đổi kiểu và **validation** là hai bước khác nhau: `age=abc` là lỗi chuyển đổi; `age=17` có thể chuyển đổi thành công nhưng vi phạm quy tắc tuổi tối thiểu.

## 5. @ModelAttribute và validation bằng BindingResult

Khi DTO có constraint Bean Validation:

~~~java
public class SignUpForm {
    @NotBlank
    private String username;

    @Email
    @NotBlank
    private String email;

    // Constructor, getters, setters theo JavaBean...
}
~~~

Một controller có thể nhận object và lỗi ngay trong cùng handler:

~~~java
@PostMapping("/signup")
public String signup(
        @Valid @ModelAttribute("signUp") SignUpForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "signup-form";
    }
    return "signup-success";
}
~~~

Phần `SignUpForm` và các view ở đoạn này là minh họa; bản thực hành hoàn chỉnh nằm ở mục 8.

**Quy tắc bắt buộc:** `BindingResult` (hoặc `Errors`) phải **đứng ngay sau** đối số `@ModelAttribute` mà nó đại diện. Không đặt `Model`, `@RequestParam` hoặc tham số khác chen giữa. Ví dụ sau sai thứ tự:

~~~java
// Sai: Model chen giữa object đã validate và BindingResult.
public String signup(@Valid @ModelAttribute("signUp") SignUpForm form,
                     Model model,
                     BindingResult errors) { /* ... */ }
~~~

Khi khai báo liền kề, handler có thể đọc cả lỗi chuyển đổi và lỗi validation. Nếu không có `BindingResult` để xử lý, quá trình phân giải đối số có thể ném `MethodArgumentNotValidException`; khi validation cấp phương thức áp dụng, loại exception có thể khác (như `HandlerMethodValidationException`). Không coi mọi lỗi form mặc nhiên trả cùng một chuỗi hay cấu trúc JSON: cách trả response phụ thuộc xử lý exception của ứng dụng.

Các API hữu ích của `BindingResult`:

- `hasErrors()`: có lỗi nào không?
- `hasFieldErrors("email")`: riêng trường email có lỗi không?
- `getFieldErrors()`: danh sách lỗi theo trường.
- `getFieldValue("age")`: giá trị được binder ghi nhận cho trường (có thể là rejected value).
- `getSuppressedFields()`: các field bị binder loại ra khi cấu hình giới hạn trường.

### 5.1. Trong giao diện HTML

Ví dụ luồng sử dụng view template:

~~~java
@Controller
@RequestMapping("/signup")
class SignupPageController {
    @GetMapping
    String showForm(Model model) {
        model.addAttribute("signUp", new SignUpForm());
        return "signup-form";
    }

    @PostMapping
    String submit(@Valid @ModelAttribute("signUp") SignUpForm form,
                  BindingResult errors) {
        if (errors.hasErrors()) {
            return "signup-form";
        }
        return "redirect:/signup/success";
    }
}
~~~

Để chạy đoạn này cần lớp `SignUpForm` đầy đủ, engine/template view tương ứng, định nghĩa view `signup-form` và đường dẫn `/signup/success`. Đây là **sơ đồ luồng MVC có view**, không phải một chương trình Java độc lập.

Template engine (ví dụ Thymeleaf) có thể render lại dữ liệu người dùng nhập và thông báo lỗi từ model; trong Spring MVC, `BindingResult` cũng được cung cấp trong model theo tên quy ước. Lưu ý xử lý CSRF khi POST từ form trình duyệt nếu ứng dụng bật Spring Security.

## 6. @ModelAttribute trên method: chuẩn bị dữ liệu model

Annotation này có **hai vai trò** cần phân biệt:

| Vị trí | Ví dụ | Vai trò |
| --- | --- | --- |
| Tham số handler | `submit(@ModelAttribute("profile") ProfileForm form)` | Lấy/tạo model object, bind request values vào object |
| Phương thức controller hoặc `@ControllerAdvice` | `@ModelAttribute("countries") List<String> countries()` | Đưa dữ liệu sẵn vào model trước handler để view dùng |
| Trên request-handling method | `@ModelAttribute("profile") @GetMapping ...` | Diễn giải giá trị trả về như model attribute thay vì kiểu trả về mặc định |

Ví dụ model cho danh sách quốc gia:

~~~java
@Controller
class ProfilePageController {
    @ModelAttribute("countries")
    public List<String> countries() {
        return List.of("VN", "SG", "JP");
    }

    @GetMapping("/profiles/new")
    public String show(Model model) {
        model.addAttribute("profile", new ProfileForm());
        return "profile-form";
    }
}
~~~

`countries()` được Spring MVC gọi để chuẩn bị attribute cho các handler thích hợp trong controller; nếu cần áp dụng rộng hơn, có thể đặt method tương tự trong `@ControllerAdvice`. Đoạn này cần các class/view đã được khai báo ở ứng dụng thực, không phải code độc lập. Các method-level `@ModelAttribute` không có nghĩa là gửi dữ liệu trực tiếp trong HTTP response; object trong model được view hoặc handler sử dụng.

**Thứ tự quan trọng:** Model object có thể đã được tạo/sẵn trong model bởi `@ModelAttribute` method trước khi tham số handler được resolve; controller tiếp tục bind request values vào object đó nếu binding được bật.

### 6.1. Tắt property binding khi chỉ muốn lấy object đã chuẩn bị

~~~java
@ModelAttribute("account")
public Account findAccount(@PathVariable String accountId) {
    return accountService.getById(accountId);
}

@PostMapping("/accounts/{accountId}/action")
public String action(@ModelAttribute(value = "account", binding = false) Account account) {
    accountService.performAction(account);
    return "redirect:/accounts";
}
~~~

Ở đây `binding = false` thể hiện object `account` được cung cấp nhưng **không nhận property values từ request** qua annotation này; có ích khi object domain đã được tìm từ DB và không muốn client sửa field. Đoạn minh họa cần kiểu `Account`, service và endpoint tương ứng.

## 7. An toàn dữ liệu: tránh mass assignment/over-posting

Giả sử entity `User` có `name`, `email`, `role`, `isAdmin`. Nếu bind request trực tiếp vào một entity có setter cho tất cả field, client có thể gửi thêm `role=ADMIN` hoặc `isAdmin=true` dù form HTML không hiển thị trường đó.

**Khuyến nghị thực tế:**

1. Thiết kế **form DTO riêng** chỉ có các field client được phép cung cấp. Sau validation, ánh xạ sang entity trong service; role, id, owner, giá tiền hoặc trạng thái nhạy cảm lấy từ server.
2. Khi dùng **property binding**, cấu hình `WebDataBinder#setAllowedFields(...)` cho danh sách trường được phép gán, nhất là với object có thể sở hữu nhiều setter.
3. Với immutable DTO, có thể chọn constructor binding và chủ động thiết kế rõ những tham số được bind; Spring hỗ trợ tên constructor argument và `@BindParam` khi cần tên khác.
4. Luôn kiểm tra quyền nghiệp vụ ở tầng service; chỉ giới hạn binding không thay cho authorization.

Giới hạn property binding theo attribute name:

~~~java
@InitBinder("registration")
public void initRegistrationBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "fullName", "email", "age", "address.city", "interests");
}
~~~

`@InitBinder` áp dụng trong phạm vi controller (hoặc theo cấu hình advice) và có thể cấu hình binder. `setAllowedFields` hạn chế việc đặt **properties** bằng property binding; không nên cho rằng nó thay thế việc xem xét constructor arguments, kiểm tra quyền hoặc validation. Field không được cho phép có thể bị suppress, và bạn có thể đọc `BindingResult#getSuppressedFields()` nếu cần theo dõi.

## 8. Ví dụ hoàn chỉnh chạy với Spring Boot + Java 17

Ứng dụng REST nhỏ này thực hiện form binding, nested address, danh sách sở thích, chuyển kiểu số, validation và whitelist field. Nó trả JSON để thử nhanh bằng `curl`, không cần template engine.

Cấu trúc:

~~~text
model-attribute-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ModelAttributeDemoApplication.java
    ├── RegistrationForm.java
    └── RegistrationController.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>model-attribute-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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

### 8.2. ModelAttributeDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ModelAttributeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModelAttributeDemoApplication.class, args);
    }
}
~~~

### 8.3. RegistrationForm.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {
    @NotBlank
    private String fullName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    @Valid
    private Address address = new Address();

    private List<String> interests = new ArrayList<>();

    public RegistrationForm() {
    }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }

    public List<String> getInterests() { return interests; }
    public void setInterests(List<String> interests) { this.interests = interests; }

    public static class Address {
        @NotBlank
        private String city;

        public Address() {
        }

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }
}
~~~

Nhờ `@Valid` trên `address`, các ràng buộc ở object lồng nhau được kiểm tra. Với `Integer age`, `@NotNull` bắt trường vắng mặt, còn `@Min(18)` bắt tuổi dưới 18. Dùng `jakarta.validation` cho Spring Boot 3.x thay vì package `javax.validation` cũ.

### 8.4. RegistrationController.java

~~~java
package demo;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RegistrationController {
    @InitBinder("registration")
    public void initBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "fullName", "email", "age", "address.city", "interests");
    }

    @PostMapping(
            path = "/register",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            List<String> errors = result.getFieldErrors().stream()
                    .map(error -> error.getField() + ": " + error.getDefaultMessage())
                    .toList();
            return ResponseEntity.badRequest().body(Map.of("errors", errors));
        }

        return ResponseEntity.ok(Map.of(
                "fullName", form.getFullName(),
                "email", form.getEmail(),
                "age", form.getAge(),
                "city", form.getAddress().getCity(),
                "interests", form.getInterests()));
    }
}
~~~

**Vì sao ví dụ hoạt động?**

- Spring nhận request body `application/x-www-form-urlencoded` từ Servlet như request parameters.
- `@ModelAttribute("registration")` tạo/lấy `RegistrationForm`, binder điền `fullName`, `email`, `age`, `address.city`, `interests`.
- `@InitBinder("registration")` giới hạn các property được bind.
- `@Valid` kiểm tra các ràng buộc; `BindingResult` liền sau form cho controller biết field nào sai.
- Khi hợp lệ, `Map` được chuyển thành JSON nhờ `@RestController` và Jackson do Spring Boot starter web cung cấp.

### 8.5. Chạy và kiểm thử

Cần Java 17+ và Maven; trong thư mục `model-attribute-demo`:

~~~bash
mvn spring-boot:run
~~~

Gửi form hợp lệ:

~~~bash
curl -i -X POST 'http://localhost:8080/api/register' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=Lan Nguyen' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=22' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'interests=java' \
  --data-urlencode 'interests=spring'
~~~

Phần body trả về có giá trị tương đương JSON sau (thứ tự key object không được đảm bảo):

~~~json
{
  "fullName": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 22,
  "city": "Da Nang",
  "interests": ["java", "spring"]
}
~~~

Gửi form vi phạm validation:

~~~bash
curl -i -X POST 'http://localhost:8080/api/register' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=' \
  --data-urlencode 'email=wrong-format' \
  --data-urlencode 'age=17' \
  --data-urlencode 'address.city='
~~~

Kết quả dự kiến: HTTP **400 Bad Request** với JSON chứa `errors` (các trường như `fullName`, `email`, `age`, `address.city`). Thứ tự và ngôn ngữ thông điệp validation tùy cấu hình, vì vậy không cố định nguyên văn.

Gửi sai kiểu dữ liệu:

~~~bash
curl -i -X POST 'http://localhost:8080/api/register' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=Lan' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=abc' \
  --data-urlencode 'address.city=Hue'
~~~

`age=abc` không chuyển sang `Integer` được nên binder ghi lỗi `typeMismatch`; `BindingResult` giúp trả HTTP 400 thay vì tiếp tục dùng object không hợp lệ.

Với Windows PowerShell, có thể thay `curl` bằng `curl.exe` và đổi cách xuống dòng theo cú pháp PowerShell (ví dụ viết toàn bộ lệnh trên một dòng); dấu `\` nối dòng trong ví dụ trên dành cho shell Unix.

### 8.6. Không gửi JSON bằng cách gọi @ModelAttribute

Request sau **không phù hợp** với endpoint `/api/register` ở trên:

~~~http
POST /api/register HTTP/1.1
Content-Type: application/json

{"fullName":"Lan","age":22}
~~~

Endpoint đặt `consumes = application/x-www-form-urlencoded` nên request `application/json` thường nhận HTTP **415 Unsupported Media Type**. Nếu API cần JSON, hãy đổi handler sang `@RequestBody RegistrationRequest dto` cùng `consumes=application/json` và khai báo DTO phù hợp. Đừng đồng nhất form binding với JSON deserialization.

## 9. Constructor binding và @BindParam

Spring MVC hiện đại cũng hỗ trợ bind trực tiếp các giá trị request vào tham số của constructor, hữu ích với object immutable. Ví dụ minh họa (không thuộc dự án thực hành ở mục 8):

~~~java
import org.springframework.web.bind.annotation.BindParam;

public class SearchForm {
    private final String keyword;
    private final int page;

    public SearchForm(@BindParam("q") String keyword,
                      @BindParam("page") int page) {
        this.keyword = keyword;
        this.page = page;
    }

    public String getKeyword() { return keyword; }
    public int getPage() { return page; }
}
~~~

Request `?q=spring&page=2` có thể cung cấp `keyword="spring"` và `page=2` cho constructor. Cần giữ tên tham số constructor trong bytecode khi dựa vào tên suy luận; `@BindParam` cho phép đặt tên nguồn rõ ràng. Khi chọn immutable object, tránh thiết kế setter/property binding không cần thiết. Không giả định `@InitBinder#setAllowedFields` lọc được mọi constructor argument: hai hình thức binding có phạm vi kiểm soát khác nhau.

## 10. So sánh các annotation thường gặp

| Annotation | Phù hợp với | Ghi nhớ |
| --- | --- | --- |
| `@RequestParam("page") int page` | Một query/form parameter theo tên | Dễ đọc cho input đơn giản |
| `@ModelAttribute("form") FormDto form` | Nhiều trường request map vào object, kể cả nested/list | Có data binding, conversion, validation |
| `@RequestBody FormDto form` | JSON/XML body qua HTTP message converters | Phụ thuộc Content-Type, không phải form-property binding |
| `@PathVariable Long id` | Segment của URL như `/users/42` | Không thay thế cả form |
| `@RequestPart MultipartFile file` | Phần của multipart request, đặc biệt file | Có thể kết hợp với form fields theo cơ chế multipart |

Chọn theo **hình dạng HTTP request** và mục đích của controller. Ví dụ đăng ký từ HTML form thường hợp lý với `@ModelAttribute`; REST API nhận JSON thường hợp lý với `@RequestBody`.

## 11. Lỗi phổ biến và cách xử lý

1. **Tên input không khớp property:** `name="full_name"` không tự bind sang `fullName` của JavaBean. Đặt tên nhất quán hoặc dùng constructor mapping/`@BindParam` khi phù hợp.
2. **Thiếu constructor/setter phù hợp:** Với property binding, Spring cần object writable và property có thể truy cập; với constructor binding, Spring cần nhận diện đúng tham số và chuyển kiểu.
3. **Nested field bị null hoặc không thể tạo:** Đảm bảo nested object có cách tạo/khởi tạo phù hợp, ví dụ `private Address address = new Address()`.
4. **Ngộ nhận `@Valid` tự xử lý giao diện lỗi:** `BindingResult` giúp kiểm tra field lỗi nhưng controller/view phải quyết định cách hiển thị.
5. **Đặt `BindingResult` cách xa form argument:** Điều này có thể gây lỗi chữ ký method hoặc không gắn lỗi vào đúng object.
6. **Bỏ `spring-boot-starter-validation` trong ứng dụng Boot:** Nếu không có Bean Validation provider phù hợp, annotation constraint có thể không được chạy như mong đợi.
7. **Gửi JSON tới endpoint dành cho form:** Kiểm tra `Content-Type`, `consumes`; dùng `@RequestBody` cho JSON.
8. **Bind trực tiếp entity nghiệp vụ:** Client có thể over-post thêm field không hiển thị. Dùng DTO rõ ràng, allowed fields và authorization trong service.
9. **Đọc mã lỗi chuyển kiểu như lỗi nghiệp vụ:** `age=abc` là binding/type mismatch, khác với `age=17` đã chuyển số thành công nhưng không qua `@Min(18)`.
10. **Nhầm model với HTTP session:** Model attribute thường gắn với xử lý request; chỉ khi dùng cơ chế `@SessionAttributes` và quy tắc liên quan mới có lưu xuyên nhiều request theo session.

## 12. Bài tập tự kiểm tra

**Bài 1 — Form object:** Viết `ContactForm` gồm `name`, `email`, `message`; tạo handler POST nhận `@ModelAttribute("contact")`, chỉ ra tên ba input HTML cần gửi.

**Bài 2 — Nested + list:** Thiết kế `BookingForm` có `guest.name` và `preferences` (`List<String>`). Tạo dữ liệu HTTP request có hai preference, giải thích cách Spring điền từng trường.

**Bài 3 — Validate:** Thêm `@NotBlank` cho `name`, `@Email` cho `email`, khai báo `@Valid` và `BindingResult` đúng vị trí; phân biệt lỗi `age=abc` và `age=17` khi có `@Min(18)`.

**Bài 4 — Security:** Giả sử `AccountEntity` có `role` và `balance` bên cạnh `displayName`. Giải thích vì sao không bind trực tiếp entity, đề xuất `AccountUpdateForm` và tập allowed fields.

**Bài 5 — Annotation:** Với client gửi `Content-Type: application/json`, hãy chọn giữa `@ModelAttribute` và `@RequestBody`; khi nào bạn sẽ dùng `@ModelAttribute` ở mức phương thức thay vì tham số?

*Gợi ý:* Form name khớp JavaBean property; nested field có dấu chấm; repeated key có thể thành list; `BindingResult` đứng ngay sau form; DTO giới hạn field từ client; JSON phù hợp với `@RequestBody`.

## 13. Tài liệu chính thức

- [Spring Framework — MVC `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html) — lấy/tạo object, bind, validation, BindingResult, constructor binding.
- [Spring Framework — MVC model methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-modelattrib-methods.html) — `@ModelAttribute` trên phương thức chuẩn bị model.
- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html) — WebDataBinder và conversion.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html) — các quy tắc validation/exception.
- [Spring Framework — MVC `@InitBinder`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html) — cấu hình binder theo controller/advice.
