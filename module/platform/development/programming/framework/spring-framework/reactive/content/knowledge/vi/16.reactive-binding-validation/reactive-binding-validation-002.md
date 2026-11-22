# @ModelAttribute và gắn dữ liệu vào đối tượng đầu vào trong Spring WebFlux

## 1. @ModelAttribute dùng để làm gì?

Trong Spring WebFlux, annotation `@ModelAttribute` dùng để **lấy hoặc tạo một đối tượng model, sau đó bind dữ liệu của HTTP request vào các thuộc tính của đối tượng đó** thông qua `WebDataBinder`. Đối tượng này thường được gọi là *model attribute*, *command object* hoặc *form-backing object*.

Một method argument có thể khai báo:

~~~java
@PostMapping("/profiles")
public ProfileView update(@ModelAttribute ProfileForm form) {
    return new ProfileView(form.getDisplayName(), form.getEmail());
}
~~~

Đây là đoạn minh họa; `ProfileForm` và `ProfileView` cần được định nghĩa trong ứng dụng. Khi controller được gọi, Spring tìm một attribute phù hợp trong model hoặc tạo đối tượng mới, rồi bind dữ liệu request vào nó trước khi truyền cho method.

Trong WebFlux, `@ModelAttribute` thường bind các nguồn:

- **Query parameters**: ví dụ `?page=2&keyword=spring`.
- **Form data**: dữ liệu gửi bằng `application/x-www-form-urlencoded`.
- **URI path variables**: ví dụ `/accounts/42` có thể cung cấp giá trị cho thuộc tính cùng tên.
- **Request headers**: tên header được chuyển thành tên thuộc tính theo quy tắc của Spring.

Form data và query parameters được ưu tiên hơn path variables và headers khi cùng có tên thuộc tính. Dữ liệu được chuyển từ chuỗi sang kiểu Java phù hợp qua hệ thống conversion/formatting của Spring.

**Điểm cần nhớ:** `@ModelAttribute` là cơ chế bind request parameters vào object; nó không phải cách giải mã một JSON document trong request body. Nếu client gửi JSON như `{"name":"An"}`, hãy dùng `@RequestBody`. Với form/query/path input, dùng `@ModelAttribute` là lựa chọn phù hợp.

## 2. Spring tạo và gắn đối tượng như thế nào?

Quá trình thông thường:

~~~text
HTTP request
    |
    +-- query parameters
    +-- form fields
    +-- URI path variables
    +-- request headers
    |
    v
@ModelAttribute argument
    |
    v
Tìm object trong Model
    | nếu chưa có
    v
Tạo object
    | constructor binding và/hoặc property binding
    v
WebDataBinder
    | type conversion, formatting, validation
    v
Controller method nhận object đã bind
~~~

Đối tượng có thể được lấy từ:

1. Model đã được thêm trước đó bằng `Model.addAttribute(...)`.
2. Một method được đánh dấu `@ModelAttribute` trong controller hoặc `@ControllerAdvice`.
3. Session nếu được quản lý qua `@SessionAttributes`.
4. Một constructor mặc định hoặc constructor phù hợp với dữ liệu request.

Nếu không tìm thấy attribute, Spring có thể tạo nó bằng constructor mặc định hoặc constructor chính với các tham số tương ứng. Sau đó, theo cấu hình mặc định, Spring có thể áp dụng **constructor binding và property binding**.

Một ví dụ form object mutable:

~~~java
public class ProfileForm {
    private String displayName;
    private String email;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Khi request gửi `displayName=An&email=an@example.com`, Spring có thể tạo `ProfileForm` qua constructor rỗng rồi gọi setter tương ứng để gắn dữ liệu.

## 3. Constructor binding và property binding

Spring hỗ trợ hai cách gắn dữ liệu chính:

| Cách binding | Cơ chế | Khi phù hợp |
| --- | --- | --- |
| **Constructor binding** | Dùng dữ liệu request làm đối số cho constructor | DTO bất biến, record, input model có tập thuộc tính rõ |
| **Property binding** | Tạo object rồi gán qua setter hoặc property có thể ghi | Form object mutable cần cập nhật thuộc tính |
| **Kết hợp** | Mặc định có thể dùng cả constructor và property binding | DTO riêng được thiết kế an toàn cho cả hai |

### Constructor binding

Có thể dùng Java record làm input object:

~~~java
public record SearchForm(String keyword, int page) {
}
~~~

Controller:

~~~java
@GetMapping("/search")
public SearchResult search(@ModelAttribute SearchForm form) {
    return searchService.find(form.keyword(), form.page());
}
~~~

Constructor binding phù hợp vì record bất biến và constructor thể hiện rõ những dữ liệu mà ứng dụng chấp nhận. Nó cũng tránh việc một client gửi thêm field tùy ý rồi gọi setter lên các thuộc tính nhạy cảm.

Nếu tên field bên ngoài khác tên constructor parameter, có thể dùng `@BindParam` để ánh xạ:

~~~java
public record SearchForm(
    @BindParam("page-size") int pageSize,
    String keyword
) {
}
~~~

Request có thể gửi `page-size=20&keyword=reactor`. `@BindParam` có thể đặt trên constructor parameter hoặc field tương ứng; cần import `org.springframework.web.bind.annotation.BindParam`.

### Property binding

Property binding thuận tiện cho form có setter:

~~~java
public class AddressForm {
    private String city;
    private String postalCode;

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getPostalCode() { return postalCode; }
    public void setPostalCode(String postalCode) { this.postalCode = postalCode; }
}
~~~

Request có thể gửi `city=Da+Nang&postalCode=550000`. Spring chuyển đổi chuỗi và gán vào các property tương ứng.

Tuy nhiên, property binding mặc định có thể gán **mọi thuộc tính có thể ghi** nếu tên request khớp. Vì vậy, không nên bind trực tiếp JPA/Hibernate entity hoặc domain object lớn từ dữ liệu client. Một client có thể tự thêm tham số cho những property không dự định cho phép chỉnh sửa, chẳng hạn `role=ADMIN`, `accountEnabled=true`, `creditLimit=...`.

## 4. Thiết kế input object an toàn: tránh mass assignment

**Mass assignment** xảy ra khi ứng dụng bind request parameters quá rộng vào object có các thuộc tính nhạy cảm. Nếu entity có `role`, `ownerId`, `approved` hoặc `balance`, client có thể thử gửi các tham số đó dù giao diện bình thường không hiển thị.

Ví dụ không an toàn:

~~~java
// Không nên dùng domain entity làm form input trực tiếp.
@PostMapping("/users")
public Mono<UserEntity> update(@ModelAttribute UserEntity user) {
    return repository.save(user);
}
~~~

Đoạn code minh họa này có thể cho phép request bind vào nhiều thuộc tính mà endpoint không có ý định mở ra. Việc ẩn field ở giao diện không phải cơ chế bảo mật.

Các cách phòng tránh, theo thứ tự nên cân nhắc:

1. **Dùng DTO/form object riêng** chỉ chứa dữ liệu mà client được phép gửi.
2. Ưu tiên **constructor binding** cho input model bất biến khi phù hợp.
3. Nếu cần property binding, khai báo **allow-list** bằng `WebDataBinder.setAllowedFields(...)`.
4. Chỉ dùng object/domain entity sau khi đã kiểm soát rõ các property được phép bind và quyền nghiệp vụ.
5. Kiểm tra quyền sở hữu và authorization ở service; allow-list không thay thế kiểm tra quyền.

### Giới hạn property bằng @InitBinder

`@InitBinder` cho phép tùy chỉnh `WebDataBinder` trước khi bind. Có thể giới hạn field được phép:

~~~java
@InitBinder("profileForm")
void initProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

Tên `profileForm` phải khớp với tên model attribute được khai báo trong controller:

~~~java
@PostMapping("/profiles")
public ProfileView update(
        @ModelAttribute("profileForm") ProfileForm form) {
    return new ProfileView(form.getDisplayName(), form.getEmail());
}
~~~

Với cấu hình này, request có thêm `role=ADMIN` không được phép bind vào property `role`, kể cả khi class có setter cho property đó. `allowedFields` là allow-list; tên field có phân biệt chữ hoa/chữ thường và hỗ trợ pattern/property path theo quy tắc của Spring.

Nếu cần chỉ dùng constructor binding, có thể bật chế độ declarative binding:

~~~java
@InitBinder("searchForm")
void initSearchBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Chế độ này luôn cho phép constructor binding và chỉ cho phép property binding khi có `allowedFields` được khai báo. Đây là lựa chọn phù hợp khi muốn bảo đảm dữ liệu chỉ đi vào những constructor parameter được thiết kế rõ ràng.

`setDisallowedFields(...)` cũng tồn tại, nhưng allow-list thường an toàn và dễ bảo trì hơn: khi domain object được thêm property mới, allow-list không tự mở quyền bind cho field đó.

## 5. Tùy chỉnh data binding bằng @InitBinder

Ngoài giới hạn field, `@InitBinder` còn dùng để đăng ký formatter, editor, converter hoặc tùy chỉnh các đặc tính binding.

Ví dụ giới hạn field và áp dụng theo đúng model attribute:

~~~java
@Controller
public class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    // Các handler method...
}
~~~

Có thể bỏ tên trong `@InitBinder` để áp dụng cho nhiều model attribute trong controller. Nếu đặt trong `@ControllerAdvice`, cấu hình có thể dùng chung cho một nhóm controller theo phạm vi advice.

### Chuyển đổi dữ liệu

Các giá trị request thường đến dưới dạng chuỗi. Spring có thể chuyển đổi sang kiểu đích như `int`, `long`, `boolean`, enum, date/time hoặc các kiểu có converter phù hợp.

Ví dụ:

~~~java
public class SearchForm {
    private int page;
    private LocalDate fromDate;

    // getters/setters
}
~~~

Request:

~~~text
GET /search?page=2&fromDate=2026-05-01
~~~

Nếu định dạng ngày không theo mặc định hoặc cần định dạng riêng, có thể đăng ký `Formatter` hoặc `Converter` qua binder/configuration. Không nên tự parse mọi giá trị chuỗi trong controller khi Spring conversion service có thể quản lý thống nhất.

### Tên attribute và binder

Dùng tên tường minh giúp liên kết rõ giữa `@ModelAttribute` và `@InitBinder`:

~~~java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}

@PostMapping("/profiles")
public ProfileView save(
        @ModelAttribute("profileForm") ProfileForm form) {
    // ...
}
~~~

Nếu bỏ tên trong `@ModelAttribute`, Spring suy ra tên mặc định từ kiểu đối tượng theo convention. Đối với binder có allow-list theo tên, nên khai báo tên rõ ràng để tránh cấu hình không áp dụng đúng attribute mong muốn.

## 6. Validation sau khi bind

Data binding chuyển dữ liệu request thành object; **validation kiểm tra object đó có thỏa quy tắc nghiệp vụ/định dạng hay không**. Hai bước có liên quan nhưng khác nhau.

Có thể dùng Jakarta Bean Validation:

~~~java
public class ProfileForm {
    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    // getters/setters
}
~~~

Đánh dấu tham số bằng `@Valid` hoặc `@Validated`:

~~~java
@PostMapping("/profiles")
public ProfileView save(
        @Valid @ModelAttribute("profileForm") ProfileForm form) {
    return new ProfileView(form.getDisplayName(), form.getEmail());
}
~~~

Khi validation thất bại, WebFlux mặc định phát `WebExchangeBindException`; exception handler có thể ánh xạ nó thành HTTP 400 Bad Request. Trong Spring Boot cần có implementation Bean Validation, thường được đưa vào qua dependency `spring-boot-starter-validation`.

### Lấy lỗi bằng BindingResult

Nếu muốn xử lý lỗi ngay trong controller method, khai báo `BindingResult` **ngay sau** tham số `@ModelAttribute`:

~~~java
@PostMapping("/profiles")
public ResponseEntity<?> save(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        List<String> messages = errors.getFieldErrors().stream()
            .map(error -> error.getField() + ": " + error.getDefaultMessage())
            .toList();

        return ResponseEntity.badRequest()
            .body(Map.of("errors", messages));
    }

    return ResponseEntity.ok(
        new ProfileView(form.getDisplayName(), form.getEmail())
    );
}
~~~

`BindingResult` phải đứng ngay sau model attribute mà nó mô tả; nếu đặt một tham số khác xen giữa, Spring không thể gắn kết quả lỗi với đúng object như mong đợi.

### Validation với Mono<T>

WebFlux hỗ trợ reactive wrapper trong model attribute, ví dụ `Mono<ProfileForm>`:

~~~java
@PostMapping("/profiles/reactive")
public Mono<ProfileView> saveReactive(
        @Valid @ModelAttribute("profileForm") Mono<ProfileForm> form) {
    return form.map(value ->
        new ProfileView(value.getDisplayName(), value.getEmail())
    );
}
~~~

Trong trường hợp này, có thể xử lý lỗi validation qua reactive error operators hoặc để exception handler chung quản lý. Nếu muốn nhận `BindingResult` làm tham số kế tiếp, model attribute phải là object **không bọc reactive type**; không khai báo `Mono<ProfileForm>` cùng `BindingResult` theo cách đó.

Nếu validation được thực hiện theo method validation vì các tham số khác có constraint, loại exception có thể là `HandlerMethodValidationException`. Cần xem đúng vị trí validation để chọn exception handler tương ứng.

## 7. Phân biệt @ModelAttribute trên tham số và trên method

Annotation này có hai cách dùng phổ biến, mục đích khác nhau:

### Trên method argument

Dùng để lấy/tạo input object và bind request vào object đó:

~~~java
@PostMapping("/profiles")
public ProfileView save(@ModelAttribute("profileForm") ProfileForm form) {
    // Dùng dữ liệu đã bind.
}
~~~

### Trên method của controller hoặc ControllerAdvice

Dùng để **chuẩn bị model attribute trước khi handler method được gọi**:

~~~java
@ModelAttribute("supportedRegions")
public List<String> supportedRegions() {
    return List.of("VN", "SG", "JP");
}
~~~

Các method `@ModelAttribute` trong controller được gọi trước các request mapping method của controller đó. Giá trị trả về được thêm vào model với tên attribute; cách dùng này thường hữu ích cho HTML view, danh sách lựa chọn hoặc dữ liệu dùng chung cho form.

Có thể đặt method-level `@ModelAttribute` trong `@ControllerAdvice` để chia sẻ model data giữa nhiều controller. Nó không phải một handler endpoint độc lập và không thay thế `@RequestBody`.

## 8. @ModelAttribute, @RequestParam và @RequestBody khác nhau thế nào?

| Annotation | Dữ liệu nhận | Kiểu đích | Dùng điển hình |
| --- | --- | --- | --- |
| `@ModelAttribute` | Query, form data, URI path variables, headers | Object/command object, có thể là reactive wrapper trong WebFlux | Nhiều trường input được gom vào DTO |
| `@RequestParam` | Một request parameter cụ thể | Giá trị đơn hoặc collection | `page=2`, `keyword=spring` |
| `@RequestBody` | Nội dung HTTP request body qua message reader/codec | DTO, `Mono<T>`, `Flux<T>` tùy định dạng | JSON/XML hoặc body streaming |
| `@RequestPart` | Một phần trong multipart request | DTO, file/part hoặc reactive part | Upload file kèm metadata |

Ví dụ:

~~~java
@GetMapping("/search")
public SearchResult search(
        @RequestParam(defaultValue = "1") int page,
        @ModelAttribute SearchForm filter) {
    return searchService.search(page, filter);
}

@PostMapping(path = "/json", consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<ProfileView> createJson(
        @RequestBody Mono<ProfileForm> body) {
    return body.map(form ->
        new ProfileView(form.getDisplayName(), form.getEmail())
    );
}
~~~

Ví dụ đầu nhận một tham số riêng `page` và gom các trường filter thành `SearchForm`; ví dụ sau đọc JSON body qua codec. Chọn annotation theo **nguồn dữ liệu thực tế** của request, không chỉ theo kiểu Java của tham số.

## 9. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này nhận form URL-encoded, giới hạn field được phép bind, kiểm tra validation và trả lỗi cụ thể. Nó có hai endpoint:

- `POST /profiles`: dùng `ProfileForm` trực tiếp cùng `BindingResult`.
- `POST /profiles/reactive`: dùng `Mono<ProfileForm>` và để lỗi validation đi qua reactive pipeline.

Tạo cấu trúc:

~~~text
model-attribute-demo/
├── pom.xml
└── src/main/java/com/example/modelattribute/
    ├── ModelAttributeApplication.java
    └── ProfileController.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
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
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/modelattribute/ModelAttributeApplication.java`:

~~~java
package com.example.modelattribute;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ModelAttributeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModelAttributeApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/modelattribute/ProfileController.java`:

~~~java
package com.example.modelattribute;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    public static class ProfileForm {
        @NotBlank
        private String displayName;

        @NotBlank
        @Email
        private String email;

        // Field nhạy cảm: client không được phép bind.
        private String role;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public record ProfileView(
        String displayName,
        String email,
        String role
    ) {}

    @InitBinder("profileForm")
    void initProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> messages = errors.getFieldErrors().stream()
                .map(error ->
                    error.getField() + ": " + error.getDefaultMessage())
                .toList();

            return ResponseEntity.badRequest()
                .body(new ErrorView(messages));
        }

        return ResponseEntity.ok(
            new ProfileView(
                form.getDisplayName(),
                form.getEmail(),
                form.getRole()
            )
        );
    }

    @PostMapping(
        path = "/reactive",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProfileView> createReactive(
            @Valid @ModelAttribute("profileForm") Mono<ProfileForm> form) {

        return form.map(value ->
            new ProfileView(
                value.getDisplayName(),
                value.getEmail(),
                value.getRole()
            )
        );
    }

    public record ErrorView(List<String> errors) {}
}
~~~

Chạy từ thư mục `model-attribute-demo` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Thử gửi form hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/profiles   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "displayName=An"   --data-urlencode "email=an@example.com"   --data-urlencode "role=ADMIN"
~~~

Response JSON dự kiến:

~~~json
{
  "displayName": "An",
  "email": "an@example.com",
  "role": null
}
~~~

Client đã gửi `role=ADMIN`, nhưng `@InitBinder` chỉ cho phép `displayName` và `email`, nên `role` không được gán. Đây là minh họa cụ thể cho allow-list property binding.

### Thử dữ liệu không hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/profiles   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "displayName="   --data-urlencode "email=not-an-email"
~~~

Endpoint trực tiếp nhận `BindingResult`, nên method được gọi và trả HTTP 400 với danh sách lỗi validation. Nội dung thông báo cụ thể có thể khác tùy Bean Validation provider và locale; trạng thái và việc có lỗi là điều cần kiểm tra.

### Thử endpoint reactive

~~~bash
curl -i -X POST http://localhost:8080/profiles/reactive   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "displayName=Binh"   --data-urlencode "email=binh@example.com"
~~~

Response JSON dự kiến:

~~~json
{
  "displayName": "Binh",
  "email": "binh@example.com",
  "role": null
}
~~~

Endpoint reactive trả `Mono<ProfileView>`; WebFlux quản lý subscription. Nếu validation thất bại, lỗi được phát trong quá trình resolve publisher và được exception handling của WebFlux xử lý. Không cần gọi `subscribe()` hay `block()` trong controller.

Ví dụ là ứng dụng Boot hoàn chỉnh ở mức demo; chưa kết nối database và không lưu profile. Trong hệ thống thật, service cần thực hiện authorization và kiểm tra quyền cập nhật dữ liệu ngoài các giới hạn binding.

## 10. Những lỗi thường gặp

1. **Dùng `@ModelAttribute` để đọc JSON body:** sai nguồn dữ liệu. Dùng `@RequestBody` và codec JSON.
2. **Bind trực tiếp JPA entity:** có thể cho client sửa các field ngoài dự kiến. Dùng DTO/form object riêng và allow-list.
3. **Chỉ ẩn field nhạy cảm trên giao diện:** client có thể tự gửi tham số. Kiểm soát bằng server-side binding và authorization.
4. **Quên tên attribute trong `@InitBinder`:** binder có thể không áp dụng vào model attribute mong muốn. Dùng tên tường minh thống nhất ở cả hai annotation.
5. **Cho rằng `@InitBinder` là nơi kiểm tra quyền:** allowedFields chỉ giới hạn property binding; service vẫn phải kiểm tra user có quyền sửa object hay không.
6. **Đặt `BindingResult` xa tham số model attribute:** Spring không gắn lỗi đúng argument. Đặt nó ngay sau `@ModelAttribute`.
7. **Kết hợp `BindingResult` với `Mono<T>` model attribute:** không đúng cách hỗ trợ của WebFlux. Nếu dùng BindingResult, tham số model attribute phải không có reactive wrapper.
8. **Nhầm validation với binding:** binding chuyển đổi dữ liệu; validation kiểm tra constraint. Một chuỗi không chuyển được sang số có thể gây binding error trước khi validation nghiệp vụ chạy.
9. **Dùng `@Valid` nhưng thiếu Bean Validation provider:** annotation không tự cung cấp implementation. Thêm dependency phù hợp như `spring-boot-starter-validation`.
10. **Cho phép quá nhiều nested property:** property path có thể truy cập object con, list hoặc map. Chỉ mở các đường dẫn thật sự cần thiết trong allow-list.
11. **Dùng `disallowedFields` làm bảo vệ duy nhất:** danh sách cấm dễ thiếu khi domain thêm field mới. Ưu tiên `allowedFields`.
12. **Dùng form object mutable nhưng không kiểm soát setter:** property binding chỉ hoạt động với property có thể ghi và có thể mở rộng ngoài dự kiến. Thiết kế DTO rõ ràng.
13. **Cho rằng query parameter và path variable luôn ưu tiên ngang nhau:** request parameters/form có ưu tiên hơn path variables và headers khi trùng tên.
14. **Đọc body JSON bằng `@ModelAttribute`:** body document không phải tập form/query parameters; dùng `@RequestBody`.
15. **Gọi `subscribe()` hoặc `block()` trong controller reactive:** tách pipeline khỏi lifecycle request hoặc chặn event-loop. Compose publisher và trả kết quả cho WebFlux.
16. **Tin rằng allow-list thay thế authorization:** field được phép bind không có nghĩa người dùng được quyền sửa object đó. Kiểm tra ownership, tenant và permission ở service.

## 11. Checklist trước khi đưa @ModelAttribute vào production

- Model attribute chỉ chứa những input field mà endpoint thật sự chấp nhận.
- Đã chọn đúng nguồn dữ liệu: query, form, path/header hay JSON body.
- Tên model attribute rõ ràng nếu có cấu hình `@InitBinder` theo tên.
- Đã cân nhắc constructor binding/record cho input bất biến.
- Nếu dùng property binding, `allowedFields` chỉ mở các property cần thiết.
- Không bind domain entity có field nhạy cảm một cách trực tiếp.
- Đã khai báo `@Valid`/`@Validated` và xử lý lỗi binding/validation.
- Nếu dùng `BindingResult`, nó đứng ngay sau object không reactive.
- Nếu dùng `Mono<T>`, error được xử lý reactive hoặc qua exception handler.
- Có kiểm tra authorization và ownership độc lập với binding.
- Có giới hạn độ dài/giá trị input và xử lý nested collection hợp lý.
- Controller không tự subscribe/block.

## 12. Câu hỏi tự kiểm tra

**1.** `@ModelAttribute` làm gì? Tạo hoặc lấy một object model và bind dữ liệu request vào object đó qua `WebDataBinder`.

**2.** Trong WebFlux, các nguồn dữ liệu chính của `@ModelAttribute` là gì? Query parameters, form data, URI path variables và request headers.

**3.** `@ModelAttribute` có đọc JSON body thay cho `@RequestBody` không? Không. JSON body dùng message reader/codec qua `@RequestBody`.

**4.** Constructor binding khác property binding thế nào? Constructor binding truyền input vào constructor; property binding gán qua setter/property có thể ghi.

**5.** Vì sao không nên bind trực tiếp JPA entity? Request có thể gán các thuộc tính nhạy cảm mà endpoint không định cho phép thay đổi.

**6.** `@InitBinder` và `setAllowedFields` dùng để làm gì? Cấu hình binder và giới hạn danh sách property được phép bind.

**7.** Vì sao nên dùng DTO riêng? DTO chỉ chứa input được phép nhận, làm rõ hợp đồng API và giảm nguy cơ mass assignment.

**8.** `BindingResult` phải đứng ở đâu? Ngay sau tham số `@ModelAttribute` mà nó mô tả.

**9.** Có thể dùng `Mono<ProfileForm>` với `BindingResult` ngay sau không? Không theo cách hỗ trợ của WebFlux; dùng object không reactive nếu cần BindingResult, hoặc xử lý lỗi reactive khi dùng Mono.

**10.** `@Valid` có thay thế authorization không? Không. Validation kiểm tra dữ liệu; authorization kiểm tra quyền thực hiện hành động.

**11.** `@ModelAttribute` trên method có ý nghĩa gì? Đưa giá trị trả về vào model hoặc chuẩn bị model trước khi request mapping method chạy.

**12.** Nếu client gửi thêm `role=ADMIN` nhưng allow-list chỉ có `displayName,email`, điều gì xảy ra? Field `role` không được phép bind; service vẫn cần kiểm tra quyền riêng.

**Ghi nhớ:** `@ModelAttribute` gắn **query/form/path/header input** vào một object có kiểu. `WebDataBinder` thực hiện constructor/property binding, chuyển đổi và validation. Trong WebFlux có thể nhận object trực tiếp hoặc reactive wrapper như `Mono<T>`. Để an toàn, dùng DTO riêng hoặc constructor binding; nếu cần property binding, giới hạn bằng `@InitBinder` và `setAllowedFields`. Validation, authorization và lifecycle reactive vẫn phải được xử lý đúng ở các tầng tương ứng.

**Tài liệu chính thức:** [Spring Framework 6.2 — @ModelAttribute trong WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html); [Spring Framework 6.2 — Data Binding trong WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/data-binding.html); [Spring Framework 6.2 — @InitBinder trong WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html).