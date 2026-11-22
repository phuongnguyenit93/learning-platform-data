# Constructor binding, property binding và thiết kế DTO đầu vào trong Spring MVC

## 1. Bài toán: biến dữ liệu HTTP thành đối tượng Java như thế nào?

Khi client gửi query string, HTML form hoặc một số giá trị từ đường dẫn/header, Spring MVC có thể gắn dữ liệu vào đối tượng Java thông qua **data binding**. Hai con đường chính là:

- **Constructor binding:** dùng các giá trị đầu vào để gọi constructor và tạo đối tượng mới. Tên và kiểu tham số constructor thể hiện rõ dữ liệu được phép cung cấp.
- **Property binding (setter binding):** tạo hoặc lấy một đối tượng có sẵn, sau đó dùng setter/JavaBeans property để gán giá trị. Nếu không kiểm soát trường cho phép, client có thể sửa những property mà lập trình viên không định mở cho request.

Bài này tập trung vào **`@ModelAttribute`, `WebDataBinder` và thiết kế request DTO của Spring Web MVC (Servlet stack)**. JSON `@RequestBody` sẽ được đối chiếu riêng vì cơ chế tạo đối tượng của nó khác. Ví dụ chạy với **Java 17, Spring Boot 3.3.5 (Spring Framework 6.1.x)**; các API `@BindParam` và `setDeclarativeBinding` có từ Spring Framework 6.1.

Một HTTP form request có thể có dạng:

```http
POST /api/registration HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=lan%40example.com&age=21
```

Spring nhận các giá trị ban đầu dưới dạng chuỗi, chẳng hạn `"21"`, sau đó dùng bộ chuyển đổi kiểu của `WebDataBinder` để tạo thuộc tính `int age = 21`. Nếu gửi `age=abc`, Spring không thể chuyển chuỗi đó thành `int` và ghi lỗi vào `BindingResult`.

> **Phân biệt quan trọng:** `@ModelAttribute` thường bind từ request parameters (query/form), và trong các trường hợp phù hợp còn từ URI variables/request headers; `@RequestBody` đọc body qua `HttpMessageConverter`, thường sử dụng Jackson khi body là JSON. Cả hai có thể nhận DTO, nhưng **không được giả định cơ chế binding và quy tắc whitelist của chúng là giống nhau**.

## 2. Luồng xử lý của @ModelAttribute

Dưới đây là đường đi khái quát trong Spring MVC:

```text
Client gửi form/query/path/header
      |
DispatcherServlet tìm handler method
      |
Argument resolver xử lý @ModelAttribute
      |
Tìm đối tượng trong model hoặc tạo đối tượng mới
      |-- Constructor binding: ánh xạ tham số -> constructor
      |-- Property binding: ánh xạ tên property -> setter
      |
WebDataBinder chuyển String sang kiểu Java
      |
Validation (nếu có @Valid/@Validated và Validator)
      |
BindingResult ghi lỗi binding/validation
      |
Controller nhận DTO đã bind
```

Tùy tình huống, `@ModelAttribute` còn có thể tham chiếu đối tượng đã tồn tại trong model hoặc session thay vì luôn tạo mới. Spring MVC mặc định cho phép **cả constructor binding lẫn property binding** khi phù hợp; việc dùng constructor không tự động vô hiệu hóa mọi setter.

Ví dụ:

```java
@PostMapping("/search")
public String search(@ModelAttribute SearchCriteria criteria) {
    return "search";
}
```

Đây là đoạn minh họa controller, không phải chương trình Java độc lập. Spring cố tạo hoặc lấy `SearchCriteria` rồi bind dữ liệu vào đối tượng. Đối với tham số kiểu phức tạp chưa được resolver khác xử lý, Spring MVC có thể suy luận `@ModelAttribute` ngầm; **nên ghi annotation rõ ràng** để người đọc và công cụ AOT dễ hiểu.

### Binding khác validation

| Bước | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| Constructor/property binding | Giá trị request đi vào field nào, theo cơ chế nào? | `age=21` gắn vào `int age` |
| Type conversion | Chuyển kiểu thành công không? | `"abc"` không chuyển được sang `int` |
| Bean Validation | Giá trị đã chuyển đổi có hợp lệ theo constraint không? | `@Min(18)` từ chối `age=16` |
| Business validation/authorization | Người dùng có quyền và nghiệp vụ có cho phép không? | Người dùng A không được đổi vai trò của B |

`@Valid` không giới hạn field nào được gán; `setAllowedFields` cũng không chứng minh dữ liệu đúng nghiệp vụ. Đây là các trách nhiệm riêng.

## 3. Constructor binding: DTO bất biến

Với Java 17+, `record` là lựa chọn tự nhiên cho DTO chỉ nhận giá trị một lần:

```java
public record RegistrationForm(
        @NotBlank @Email String email,
        @Min(18) int age
) {}
```

Đoạn khai báo này cần các imports `jakarta.validation.constraints.NotBlank`, `Email` và `Min`, cùng starter validation. Khi Spring bind `email=lan%40example.com&age=21`, nó lấy hai tham số, đổi `age` sang `int`, gọi canonical constructor của record và tạo ra đối tượng bất biến về cấu trúc.

Vì record không có setter, request gửi thêm `role=ADMIN` không có chỗ để property binding gán `role` vào DTO này. Constructor chỉ khai báo `email` và `age`. Tuy vậy, điều đó **không có nghĩa** mọi tham số dư mặc nhiên bị coi là lỗi; mặc định các giá trị không được bind có thể được bỏ qua.

Với một lớp thông thường cũng có thể dùng constructor binding:

```java
public final class SearchForm {
    private final String keyword;
    private final int page;

    public SearchForm(String keyword, int page) {
        this.keyword = keyword;
        this.page = page;
    }

    public String getKeyword() { return keyword; }
    public int getPage() { return page; }
}
```

Đây là đoạn mã minh họa. Khi dựa vào **tên tham số constructor** của lớp thường, cần đảm bảo compiler giữ metadata parameter names (ví dụ `javac -parameters` hoặc cấu hình tương đương). Record có tên component rõ ràng. Khi có nhiều constructor, quy tắc chọn constructor có thể thay đổi; nên thiết kế một constructor dữ liệu không gây nhập nhằng.

### Đổi tên tham số đầu vào bằng @BindParam

Tên request không nhất thiết trùng với tên Java. Trong Spring 6.1+, `@BindParam` hỗ trợ gắn tên request cho tham số constructor:

```java
public final class AddressForm {
    private final String postalCode;

    public AddressForm(@BindParam("postal-code") String postalCode) {
        this.postalCode = postalCode;
    }

    public String getPostalCode() { return postalCode; }
}
```

```http
GET /addresses?postal-code=700000
```

Với `@ModelAttribute AddressForm`, Spring lấy tham số `postal-code` để điền `postalCode`. Import annotation là `org.springframework.web.bind.annotation.BindParam`. Đây là minh họa cần đặt trong ứng dụng Spring MVC, không phải lớp độc lập có `main`. Đừng nhầm `@BindParam` dùng cho constructor `@ModelAttribute` với Jackson `@JsonProperty` dùng khi chuyển JSON thành object.

Constructor binding có thể xử lý đối tượng lồng nhau và `List`, `Map`, array bằng tên có cấu trúc như `addresses[0].city`; điều kiện là constructor/kiểu dữ liệu tương ứng có thể bind và các giới hạn tài nguyên thích hợp được áp dụng. Không để client tùy ý tạo đồ thị object quá sâu hoặc collection không giới hạn.

## 4. Property binding: bean mutable và setter

Property binding thường dùng lớp JavaBean với constructor không tham số và getter/setter:

```java
public class ProfileForm {
    private String displayName;
    private String timeZone;

    public ProfileForm() {}

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getTimeZone() { return timeZone; }
    public void setTimeZone(String timeZone) {
        this.timeZone = timeZone;
    }
}
```

Khi có form `displayName=Lan&timeZone=Asia%2FHo_Chi_Minh`, Spring tạo `ProfileForm` rồi gọi các setter tương ứng. Cách này hữu ích cho form mutable hoặc khi làm việc với thư viện yêu cầu JavaBean. Nó có một rủi ro: nếu sau này lớp xuất hiện setter nhạy cảm như `setRole`, việc bind một cách rộng rãi có thể khiến client sửa thêm trường ngoài ý định.

**Mass assignment / over-posting** xảy ra khi client cố gửi tên property nhạy cảm mà server vô tình cho bind, ví dụ `role=ADMIN`, `approved=true` hoặc `ownerId=...`. Nguyên tắc giảm thiểu:

1. Dùng **DTO đầu vào riêng** theo từng tác vụ, chỉ chứa trường client được phép cung cấp.
2. Ưu tiên constructor binding hoặc DTO bất biến khi phù hợp, tránh setter không cần thiết.
3. Nếu phải dùng property binding, cấu hình `WebDataBinder.setAllowedFields(...)` để whitelist tên property dự kiến.
4. Không bind trực tiếp request vào JPA entity/domain object có setter nghiệp vụ nhạy cảm.
5. Server tự quyết định `id`, `role`, `ownerId`, `createdAt`, `approved` từ quyền hiện tại và quy tắc nghiệp vụ.

**Lưu ý:** whitelist chỉ áp dụng cho **property binding**, không thay đổi các giá trị được chấp nhận bởi constructor đã khai báo. Vì thế không đưa tham số nguy hiểm vào constructor public của DTO chỉ để hy vọng `allowedFields` chặn lại.

## 5. Kiểm soát WebDataBinder bằng @InitBinder

`WebDataBinder` là binder cụ thể trong Spring MVC. Dùng `@InitBinder` để điều chỉnh cách bind cho một model attribute hoặc một controller:

```java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "timeZone");
}
```

- `setAllowedFields` thiết lập **danh sách cho phép** đối với property names; pattern là case-sensitive. Ví dụ mở rộng có thể dùng `address.*` nhưng phải kiểm tra cả những nested property được mở.
- `setDisallowedFields` có tồn tại ở các phiên bản Spring liên quan, song blacklist dễ bỏ sót các property được thêm về sau. Ưu tiên whitelist.
- `setDeclarativeBinding(true)` (Spring 6.1+) buộc property binding chỉ thực hiện khi có `allowedFields`, trong khi constructor binding vẫn được hỗ trợ:

```java
@InitBinder("registrationForm")
void configureRegistrationBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Nếu dùng **cả** `setDeclarativeBinding(true)` và `setAllowedFields("displayName", "timeZone")` thì hai property trong whitelist vẫn được setter binding; các property khác không được gán qua setter. Với model chỉ cần constructor, chỉ cần bật declarative binding mà không khai báo allowed fields.

`@InitBinder("profileForm")` áp dụng cho model attribute có tên `profileForm`; `@InitBinder` không truyền tên có thể tác động các binding trong controller đó. `@ControllerAdvice` có thể dùng để chia sẻ chính sách giữa controller, nhưng hãy kiểm tra phạm vi áp dụng để không vô ý vô hiệu hóa những form khác. Nếu có yêu cầu cụ thể, binder còn có thể đăng ký formatter, converter hoặc validator.

### @ModelAttribute(binding = false) giải quyết việc khác

`@ModelAttribute(binding = false)` dùng khi cần lấy object từ model mà không thực hiện property binding từ request, chẳng hạn object domain đã được server tra cứu. Đó không phải cơ chế thay thế mọi kiểm soát constructor binding. Cách an toàn hơn cho API nhận dữ liệu là dùng request DTO tách biệt rồi gán có kiểm soát vào domain object.

## 6. Chương trình hoàn chỉnh: so sánh hai cơ chế binding

Ví dụ có hai endpoint:
- `POST /api/registration`: record DTO bất biến, constructor binding và validation.
- `POST /api/profile`: JavaBean có setter, property binding qua whitelist. Lớp minh họa cố tình có property `role` để cho thấy whitelist loại bỏ một tham số không được phép. **Trong ứng dụng thật, nên bỏ hẳn property `role` khỏi DTO đầu vào.**

Cấu trúc Maven:

```text
binding-demo/
├── pom.xml
└── src/main/java/example/binding/
    ├── BindingDemoApplication.java
    └── BindingController.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>binding-demo</artifactId>
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

**`src/main/java/example/binding/BindingDemoApplication.java`**

```java
package example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
```

**`src/main/java/example/binding/BindingController.java`**

```java
package example.binding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class BindingController {

    public record RegistrationForm(
            @NotBlank @Email String email,
            @Min(18) int age) {}

    public record RegistrationResponse(String email, int age) {}

    @InitBinder("registrationForm")
    void registrationBinder(WebDataBinder binder) {
        // Không bật setter binding cho RegistrationForm.
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(path = "/registration",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(Map.of(
                "invalidFields",
                errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList()
            ));
        }
        return ResponseEntity.ok(
                new RegistrationResponse(form.email(), form.age()));
    }

    public static class ProfileForm {
        private String displayName;
        private String timeZone;
        private String role; // Giữ để minh họa field cần chặn.

        public ProfileForm() {}

        public String getDisplayName() { return displayName; }
        public void setDisplayName(String value) {
            this.displayName = value;
        }

        public String getTimeZone() { return timeZone; }
        public void setTimeZone(String value) {
            this.timeZone = value;
        }

        public String getRole() { return role; }
        public void setRole(String value) {
            this.role = value;
        }
    }

    public record ProfileResponse(
            String displayName, String timeZone, String role) {}

    @InitBinder("profileForm")
    void profileBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "timeZone");
    }

    @PostMapping(path = "/profile",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ProfileResponse update(
            @ModelAttribute("profileForm") ProfileForm form) {
        return new ProfileResponse(
                form.getDisplayName(), form.getTimeZone(), form.getRole());
    }
}
```

**Cơ chế của từng endpoint:**

- `/registration`: record có canonical constructor nhận `email` và `age`; Spring chuyển chuỗi theo kiểu đích, tạo record, chạy Bean Validation vì có `@Valid`. `BindingResult` đứng **ngay sau** tham số được validate để controller đọc lỗi.
- `/profile`: JavaBean được tạo bằng constructor rỗng; binder chỉ cho phép gọi setters ứng với `displayName` và `timeZone`. Tham số `role` bị chặn bởi whitelist dù lớp minh họa có setter.
- Đây là ví dụ phân biệt cơ chế, **không lưu vào database**, không có authentication và không đại diện cho workflow chỉnh sửa role thật.

Chạy từ thư mục `binding-demo`:

```bash
mvn spring-boot:run
```

Gửi form hợp lệ (Bash, macOS/Linux/Git Bash):

```bash
curl -s -X POST 'http://localhost:8080/api/registration' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=21'
```

HTTP status `200`; JSON có dữ liệu:

```json
{"email":"lan@example.com","age":21}
```

Thứ tự field JSON không nên được coi là hợp đồng API. Thử dữ liệu sai constraint:

```bash
curl -i -X POST 'http://localhost:8080/api/registration' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=invalid' \
  --data-urlencode 'age=16'
```

Kết quả mong đợi là HTTP `400`, body chứa tên field không hợp lệ (thứ tự đã được sort trong controller):

```json
{"invalidFields":["age","email"]}
```

Kiểm tra trường bị chặn:

```bash
curl -s -X POST 'http://localhost:8080/api/profile' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'timeZone=Asia/Ho_Chi_Minh' \
  --data-urlencode 'role=ADMIN'
```

Kết quả JSON:

```json
{"displayName":"Lan","timeZone":"Asia/Ho_Chi_Minh","role":null}
```

Mặc dù request có `role=ADMIN` và `ProfileForm` có setter, `setAllowedFields` chỉ chấp nhận hai field còn lại, nên `role` không được gán. Phần response chỉ giúp quan sát cơ chế; trên ứng dụng thật **không nên trả role nội bộ khi nó không cần thiết**. Nếu muốn phát hiện trường bị chặn trong xử lý form, có thể khai báo `BindingResult` ngay sau `@ModelAttribute` và kiểm tra `getSuppressedFields()`; hãy quyết định chính sách trả lỗi hay ghi nhận sự kiện dựa theo bảo mật API, không mặc nhiên coi việc bỏ qua là đủ an toàn.

> **Kiểm chứng runtime:** những body trên là kết quả logic của controller với request đã nêu; HTTP headers phụ thuộc môi trường. Code yêu cầu Maven và JDK 17+, cùng dependencies tải thành công. Nếu cổng `8080` đang được sử dụng, cấu hình `server.port` phù hợp trước khi gửi request.

## 7. Khi đầu vào là JSON @RequestBody

Gửi JSON:

```http
POST /api/registration-json HTTP/1.1
Content-Type: application/json

{"email":"lan@example.com","age":21}
```

Controller thường khai báo:

```java
@PostMapping(path = "/registration-json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> createJson(
        @Valid @RequestBody RegistrationForm form) {
    // ...
}
```

**Đoạn trên minh họa**, có thể thêm vào `BindingController` cùng imports `@RequestBody`; không nằm trong file chạy đầy đủ ở mục 6. Ở đây Spring MVC chọn `HttpMessageConverter` đọc JSON, và Jackson (nếu được cấu hình) tạo object Java. Validation vẫn có thể xảy ra sau khi đọc body, nhưng đây **không phải** quá trình `@ModelAttribute` gọi `WebDataBinder` để gán request parameters bằng property binding. Do đó `binder.setAllowedFields(...)` trong `@InitBinder` không phải cơ chế bảo vệ JSON khỏi mass assignment.

Với JSON, hãy dùng request DTO với đúng các trường cho phép, ánh xạ tường minh sang domain model và chỉ cho phép các JSON properties cần thiết. Nếu cần quy tắc chặt về trường JSON lạ, phải cấu hình Jackson phù hợp; mặc định chấp nhận hay từ chối field lạ phụ thuộc cấu hình ObjectMapper và môi trường. `@JsonProperty`/`@JsonCreator` phục vụ Jackson; `@BindParam` phục vụ constructor binding của Spring MVC cho `@ModelAttribute`.

| Đặc điểm | `@ModelAttribute` với form/query | `@RequestBody` với JSON |
| --- | --- | --- |
| Nguồn dữ liệu điển hình | Query/form parameters; cũng có thể lấy URI variables/headers theo quy tắc lookup | HTTP body theo `Content-Type` |
| Thành phần chính | `WebDataBinder`, conversion service | `HttpMessageConverter`, Jackson với JSON |
| Tạo object | Constructor binding hoặc bean/property binding | JSON deserialization theo cấu hình Jackson |
| Whitelist property qua `setAllowedFields` | Có tác dụng với **property binding** | Không phải biện pháp whitelist JSON |
| Bean Validation `@Valid` | Có, thường đi với `BindingResult` | Có, xử lý lỗi validation theo cơ chế request body |

## 8. Thiết kế DTO đầu vào an toàn, dễ bảo trì

Một endpoint cập nhật profile nên phân định rõ **client input**, **domain object** và **response DTO**:

```text
HTTP request
     |
CreateProfileRequest / UpdateProfileRequest
     |  validate + authorize + check business rules
     v
Application service
     |  chỉ ánh xạ các field được phép
     v
Domain entity (id, role, ownerId do server quản lý)
     |
     v
ProfileResponse (chỉ dữ liệu được phép hiển thị)
```

Một DTO input tốt thường có các đặc điểm:

1. **Theo hành động, không theo bảng database.** Ví dụ `CreateOrderRequest`, `UpdateProfileRequest`; hai thao tác có tập trường được phép khác nhau.
2. **Giới hạn dữ liệu ngay trong kiểu.** Dùng record/final fields cho DTO bất biến khi phù hợp, constraints như `@NotBlank`, `@Email`, `@Size`, `@Min`; không coi annotation là toàn bộ logic nghiệp vụ.
3. **Không nhận field do server sở hữu.** `id`, `createdAt`, `approved`, `role`, `tenantId`, `ownerId` thường phải lấy từ cơ sở dữ liệu hoặc security context sau khi xác thực/phân quyền.
4. **Chỉ map field hợp lệ.** Không sao chép tất cả thuộc tính request vào entity bằng reflection hoặc BeanUtils không kiểm soát. Có thể tự gán hoặc dùng mapper khai báo explicit mapping.
5. **Tách kiểu tạo và kiểu cập nhật.** Trong cập nhật từng phần, cần phân biệt **không gửi field**, **gửi null** và **gửi giá trị mới**; record có primitive `int` hay một nullable reference đơn giản có thể làm mất khác biệt này. Nếu semantics patch quan trọng, thiết kế command/patch representation phù hợp.
6. **Coi nested object/list là dữ liệu từ bên ngoài.** Giới hạn số phần tử, chiều sâu, và kiểm tra mọi ID tham chiếu thuộc phạm vi được phép.
7. **Chuẩn hóa lỗi.** Đặt `BindingResult` ngay sau tham số `@ModelAttribute` khi muốn phản hồi field errors ngay tại controller; nếu không, lỗi có thể được Spring xử lý qua exception handler. Đừng đưa giá trị nhạy cảm vào thông báo lỗi/log.

Ví dụ ánh xạ tường minh (**minh họa logic dịch vụ**, không phải lớp chạy độc lập):

```java
public void changeProfile(UpdateProfileRequest input,
                          Account account) {
    account.changeDisplayName(input.displayName());
    account.changeTimeZone(input.timeZone());
    // account.role, account.ownerId không đến từ input.
}
```

Đối tượng `account` phải được tải và kiểm tra quyền ở tầng service/security. Whitelist binder và DTO hẹp có thể giảm bề mặt tấn công, nhưng không thay được kiểm soát quyền sở hữu bản ghi.

## 9. Các lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| Form gửi đúng tên nhưng field vẫn `null` | Getter/setter thiếu hoặc sai, tên request không khớp, `allowedFields` chặn | Kiểm tra JavaBean convention, tên param và binder |
| `age=abc` gây binding error | Không chuyển `String` thành `int` | Kiểm tra `BindingResult` và thông báo có cấu trúc |
| `age=16` bind được nhưng validation lỗi | Type conversion thành công, `@Min(18)` thất bại | Phân biệt validation với conversion |
| DTO có setter nhạy cảm được client sửa | Property binding mở quá rộng | Dùng DTO riêng, `setAllowedFields`/`setDeclarativeBinding` |
| Bật `setDeclarativeBinding(true)` khiến mutable form không nhận giá trị | Property binding cần `allowedFields` tường minh | Bổ sung chính xác whitelist hoặc chuyển sang DTO constructor |
| Đặt `BindingResult` sai vị trí | Spring yêu cầu nó ngay sau argument tương ứng | Chuyển `BindingResult` liền sau `@Valid @ModelAttribute` |
| Nhầm `@BindParam` với `@JsonProperty` | Hai pipeline khác nhau | Phân biệt binder của model attribute và Jackson |
| Nghĩ rằng bỏ `role` khỏi JSON là đã phân quyền | Authorization là kiểm tra riêng | Kiểm tra principal, resource ownership và policy ở service |
| Dùng cùng một request DTO cho create/update/patch | Quy tắc field và null khác nhau | Tách contract hoặc xây representation thể hiện rõ ý định |

Một số điểm tinh tế cần nhớ:

- `@ModelAttribute` có thể sử dụng giá trị từ request parameters, URI variables và headers; Spring ưu tiên request parameters khi tên trùng. Không nên dựa vào headers để cấp trường nhạy cảm chỉ vì binder có thể đọc được.
- `setAllowedFields` giới hạn setter/property binding, **không loại bỏ quyền bind tham số đã khai báo ở constructor**.
- `BindingResult` giữ cả lỗi binding/conversion và validation; nếu controller nhận nó, phải kiểm tra và xử lý, không tiếp tục gọi service khi có lỗi.
- Spring MVC thường trả `400 Bad Request` cho binding/validation không được xử lý riêng, nhưng cấu trúc JSON của lỗi do ứng dụng, phiên bản và exception handler quyết định.
- Các mối nguy về request size, danh sách lớn, nested binding và dữ liệu nhạy cảm cần giải quyết bằng giới hạn phù hợp ở cả HTTP và tầng nghiệp vụ.

## 10. Bài tập tự kiểm tra

1. Vì sao constructor của request DTO chỉ nên nhận những field client thực sự được phép kiểm soát?
2. `setDeclarativeBinding(true)` tác động thế nào đến constructor binding và property binding?
3. Nếu lớp JavaBean có setters `setName` và `setRole`, còn allowed fields chỉ có `name`, điều gì xảy ra với request `role=ADMIN`?
4. Vì sao `@Valid` không thay thế `setAllowedFields`? Và vì sao `setAllowedFields` không thay thế authorization?
5. Chọn cơ chế nào cho form HTML gồm `email` và `age`? Chọn cơ chế nào cho request JSON cùng hai field?
6. Khi thiết kế PATCH, vì sao `int age` trong record không đủ để phân biệt field không gửi và gửi `0`?

**Định hướng trả lời:** (1) Tham số constructor là tập đầu vào khai báo rõ; không để server-owned fields lọt vào. (2) Constructor binding vẫn hoạt động; setter binding chỉ khi có whitelist. (3) `role` bị loại khỏi property binding. (4) Validation kiểm tra giá trị, whitelist kiểm soát field được gán, authorization kiểm tra quyền. (5) Form/query: `@ModelAttribute`; JSON: `@RequestBody` qua converter. (6) Primitive có mặc định, nên cần mô hình biểu diễn trạng thái hiện diện nếu hỗ trợ cập nhật từng phần.

## 11. Nguồn tham khảo

- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Data Binding (Web MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Data Binding (Core)](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Framework 6.1 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.1 — @BindParam API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)

Các ví dụ được giới hạn vào Spring MVC, binding đầu vào và thiết kế DTO; chúng minh họa xử lý request an toàn trong phạm vi bài học, không bao gồm persistence hoặc cơ chế đăng nhập.