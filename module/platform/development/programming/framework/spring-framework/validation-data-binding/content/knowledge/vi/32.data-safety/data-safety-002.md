# DTO theo tác vụ và danh sách trường được phép trong Spring MVC

## 1. Vì sao data binding là một ranh giới bảo mật?

Trong Spring MVC, `@ModelAttribute` giúp chuyển request parameters thành thuộc tính của Java object. Đây là tính năng rất tiện lợi khi xây form, nhưng cũng là nơi dữ liệu **không đáng tin** đi vào ứng dụng.

Giả sử ứng dụng có một domain object chứa:

```java
public class AccountEntity {
    private Long id;
    private String displayName;
    private String email;
    private String role;
    private boolean locked;
    private Long ownerId;

    // Các setter/getter khác được lược bỏ trong ví dụ minh họa.
}
```

Một endpoint viết vội:

```java
@PostMapping("/accounts/update")
public String update(@ModelAttribute AccountEntity account) {
    accountRepository.save(account);
    return "redirect:/accounts";
}
```

Hai đoạn trên là **minh họa anti-pattern**, chưa phải một chương trình chạy độc lập; `accountRepository` là dependency được giả định. Khi Spring bind trực tiếp từ request vào entity có nhiều writable properties, client có thể cố gửi thêm:

```text
displayName=Lan&email=lan@example.org&role=ADMIN&locked=false&ownerId=7
```

Nếu các property trên có thể được bind và code cập nhật entity một cách thiếu kiểm soát, một người dùng được phép đổi tên hiển thị có thể cố thay **quyền, trạng thái khóa hoặc chủ sở hữu**. Đây là dạng **mass assignment / over-posting / unsafe data binding**.

**Nguyên tắc thiết kế:** đừng lấy “entity có những field nào” làm tiêu chuẩn “client được phép gửi những field nào”. Quyền thay đổi field phụ thuộc **tác vụ**, **caller** và **resource**; DTO đầu vào phải mô tả điều đó.

Bài này giải thích hai biện pháp bổ trợ:

1. **DTO theo tác vụ (task-specific command/input DTO):** mỗi thao tác chỉ nhận những field thuộc hợp đồng của thao tác đó.
2. **Danh sách trường được phép (allowlist):** khi dùng Spring property/setter binding, cấu hình `WebDataBinder#setAllowedFields(...)` để hạn chế field được gắn, đồng thời xem `BindingResult#getSuppressedFields()` nếu client cố gửi field ngoài hợp đồng.

Ngoài ra còn phân biệt **constructor binding**, **property binding**, `setDeclarativeBinding(true)`, JSON `@RequestBody`, validation và authorization. Mục tiêu không chỉ ngăn một payload cụ thể mà là xây cách tổ chức để **một property nhạy cảm được thêm vào entity trong tương lai cũng không tự động mở ra cho client**.

**Phạm vi:** Java 17+, Spring Framework 6.x, Spring Boot 3.x, Spring MVC Servlet stack, Jakarta Validation. Các nguyên tắc bảo mật áp dụng rộng hơn, nhưng class/exception và binding pipeline của WebFlux hoặc các framework khác cần kiểm tra riêng.

## 2. DTO theo tác vụ là gì?

**DTO theo tác vụ** là Java type mô tả **dữ liệu mà một hành động cụ thể được phép tiếp nhận**, không phải hình chiếu đầy đủ của database entity.

Một tài khoản có thể hỗ trợ ba tác vụ:

| Tác vụ | Input DTO | Các field caller được gửi | Field phải do server quản lý |
| --- | --- | --- | --- |
| Đăng ký tài khoản | `CreateAccountForm` | `displayName`, `email`, `acceptedTerms` | `id`, `role`, `locked`, `ownerId` |
| Thay đổi thông tin liên hệ | `ChangeContactForm` | `email`, `phone`, `newsletter` | `id`, `role`, `locked`, `displayName` |
| Cấp quyền quản trị | `ChangeRoleCommand` | `role` theo quy trình quản trị đã được authorize | Các field liên hệ và quyền khác ngoài phạm vi |

Đây là ba hợp đồng khác nhau. **Không dùng một `AccountEntity` với mọi setter cho cả ba**, rồi dựa vào client “đừng gửi những field không có trên UI”.

### 2.1. DTO đầu vào và entity có vai trò khác nhau

- **Input DTO:** biên dữ liệu từ HTTP, định nghĩa field hợp lệ cho một use case, kèm constraint cú pháp/định dạng.
- **Domain entity:** trạng thái và invariant của nghiệp vụ; có thể chứa các property client không được phép kiểm soát.
- **Output DTO:** dữ liệu được phép trả cho người dùng, không nhất thiết bằng input hay entity.
- **Service command:** yêu cầu nghiệp vụ đã qua validation/authorization; có thể được xây riêng để tránh phụ thuộc HTTP API.

Một luồng an toàn hơn:

```text
Untrusted HTTP request
      |
      v
Request mapping + task-specific DTO
      |
      v
Data binding: allowlist / constructor / conversion
      |
      v
Jakarta/Spring validation
      |
      v
Authentication + authorization + business checks
      |
      v
Explicit mapping các field hợp lệ
      |
      v
Domain service / aggregate / database
      |
      v
Response DTO cho caller
```

**Quan trọng:** DTO và allowlist **không thay thế authorization**. Một field được phép xuất hiện trong DTO nhưng caller vẫn có thể **không có quyền sửa tài khoản cụ thể**. Ví dụ `email` hợp lệ về kiểu không đồng nghĩa bất kỳ ai cũng được đổi email của tài khoản 42.

### 2.2. Tại sao dùng một DTO có nhiều nullable fields thường khó an toàn?

Một DTO “đa năng”:

```java
public class AccountRequest {
    private String displayName;
    private String email;
    private String phone;
    private String role;
    private Boolean locked;
    private Long ownerId;
    // getters/setters...
}
```

Nếu tái sử dụng type này ở tất cả endpoints, mỗi endpoint phải liên tục xác định field nào được phép và field nào không. Khi thêm property mới, nhiều chỗ có thể vô tình cho phép sửa property đó hoặc quên validation groups. Một DTO theo tác vụ nhỏ hơn thường có:

- Trách nhiệm rõ ràng khi code review.
- Validation phù hợp với hành động.
- Cấu trúc input dễ tài liệu hóa trên OpenAPI.
- Ít nguy cơ over-posting nếu có thay đổi domain entity.
- Ít phụ thuộc logic “nếu operation là CREATE thì bỏ field X, nếu UPDATE thì bỏ field Y”.
- Dễ kiểm thử negative cases với một hợp đồng cụ thể.

**Không phải mỗi endpoint buộc phải có class duy nhất**. Hai endpoints thật sự có cùng input semantics có thể dùng chung DTO. Cần tách khi **tập field được phép hoặc cách diễn giải dữ liệu khác nhau**.

## 3. Allowlist là tầng bảo vệ bổ sung cho property binding

Với `@ModelAttribute`, Spring thường dùng `WebDataBinder` để gán request values vào writable properties. Có thể giới hạn bằng:

```java
@InitBinder("createAccount")
void initCreate(WebDataBinder binder) {
    binder.setAllowedFields(
            "displayName", "email", "acceptedTerms");
}
```

Tác động: khi binder thực hiện **property binding** cho objectName `createAccount`, chỉ các property paths khớp những pattern được phép mới được chuyển vào object. Những field khác có thể được **suppress** (bỏ khỏi danh sách gán) và ghi nhận qua `BindingResult#getSuppressedFields()`.

Trong Spring 6.x:

- `setAllowedFields("...")` là **positive allowlist**: kể tên những property được phép.
- `setDisallowedFields("...")` là **denylist**: liệt kê những field bị cấm. Cách này kém an toàn vì có thể bỏ sót field mới được thêm vào class.
- `getSuppressedFields()` trả các tên field bị loại trong quá trình binding; **không có nghĩa `hasErrors()` tự động trở thành true**.
- Các pattern cho allowlist có thể chứa wildcard `*` theo matching rules của Spring, nên một pattern quá rộng có thể vô tình cho phép nhiều nested properties.
- Matching của **allowed field patterns phân biệt hoa/thường** theo Javadoc của Spring 6.x; không nên tự suy mọi tên field cùng nghĩa sẽ được coi như nhau.
- `@InitBinder("createAccount")` giới hạn initializer theo **binder objectName**, không phải Java type, tên controller method hoặc path URL.

Đây là một lớp kiểm soát **giai đoạn binding**, không phải database permission và cũng không phải JSON deserialization firewall.

### 3.1. Đặt tên model attribute tường minh

```java
@PostMapping("/accounts")
public String create(
        @Valid @ModelAttribute("createAccount")
                CreateAccountForm form,
        BindingResult errors) {
    // ...
    return "done";
}
```

Chỉ khi binder được tạo cho tên `createAccount` thì method `@InitBinder("createAccount")` tương ứng mới được chọn theo cơ chế Spring. Tên biến Java `form` không thay thế objectName.

Đừng đổi `@ModelAttribute("createAccount")` thành `@ModelAttribute("account")` mà quên cập nhật initializer; allowlist dự kiến có thể không còn áp dụng.

### 3.2. Đặt BindingResult ngay sau đối số

`BindingResult` hoặc `Errors` phải nằm **ngay sau** command object mà nó mô tả:

```java
@PostMapping("/accounts")
public String create(
        @Valid @ModelAttribute("createAccount") CreateAccountForm form,
        BindingResult result,
        Model model) {
    if (result.hasErrors()) {
        return "form";
    }
    return "done";
}
```

Với chữ ký trên, controller có thể xem validation/binding errors và `getSuppressedFields()`. Nếu đặt `Model model` chen giữa form và `BindingResult`, Spring không thể ghép kết quả theo đúng quy ước.

**Ghi nhớ:** lỗi field bị suppress là một tín hiệu riêng với `getSuppressedFields()`. Kiểm tra `result.hasErrors()` **không đủ** để nhận biết client gửi property bị cấm.

## 4. Positive allowlist khác denylist và validation như thế nào?

| Cơ chế | Ví dụ | Trả lời câu hỏi gì? | Không giải quyết gì? |
| --- | --- | --- | --- |
| Task-specific DTO | `ChangeContactForm` không có `role` | Hành động chấp nhận kiểu dữ liệu nào? | Quyền caller trên resource |
| `setAllowedFields` | `"email","phone","newsletter"` | Field nào được property-bind? | JSON Jackson mapping, constructor args, quyền DB |
| `setDisallowedFields` | `"role","locked"` | Field nào bị deny trong property-bind? | Các field nhạy cảm chưa biết đến |
| `@Valid` + `@NotBlank` | Email phải có giá trị | Giá trị có thỏa constraint không? | Ai được phép đổi email? |
| `@Email` | Chuỗi có format email | Định dạng input có hợp lệ không? | Email đã được xác minh hoặc thuộc caller? |
| Authorization | Chủ tài khoản hay admin | Ai được thực hiện thao tác trên resource? | Định dạng email hoặc số điện thoại |
| Explicit mapping | `current.role()` được giữ nguyên khi đổi email | Property domain nào thực sự thay đổi? | Vi phạm quyền nếu service chọn resource sai |
| DB constraints | unique email, FK, optimistic lock | Dữ liệu cuối cùng có nhất quán không? | Quyền truy cập ở HTTP boundary |

Một API bảo mật cần các lớp phù hợp **cùng hoạt động**. Ví dụ `@NotNull` trên `role` không chặn client tự đổi sang `ADMIN`; cả `MEMBER` lẫn `ADMIN` đều có thể là giá trị hợp lệ về mặt constraint. Đây là vấn đề **authorization và field ownership**, không phải chỉ Bean Validation.

### 4.1. Vì sao positive allowlist tốt hơn “cấm field role”?

Giả sử bạn viết:

```java
binder.setDisallowedFields("role", "locked");
```

Sau đó entity thêm `billingLimit`, `organizationId` hoặc `verified`. Denylist cũ không biết những field mới. Một allowlist chỉ cho `email`/`phone` vẫn không mở các field mới. Vì thế trong property binding của dữ liệu không tin cậy, **prefer allowlist**.

Nếu vẫn dùng denylist vì lý do tương thích, nên có một positive DTO boundary và tests cho property mới. Không nên xem denylist là bảo vệ duy nhất.

### 4.2. Vì sao whitelist quá rộng cũng không an toàn?

Ví dụ:

```java
binder.setAllowedFields("*");
```

Khai báo này về mặt bảo mật gần như tự bỏ lợi ích của allowlist: tất cả property paths được hỗ trợ có thể khớp. Các pattern như `"settings*"` hoặc `"addresses*"` cũng cần xét kỹ nested properties.

Nếu cần cho sửa nested field:

```java
binder.setAllowedFields(
        "displayName",
        "address.city",
        "address.postcode"
);
```

Đây là **fragment** cho một DTO thật sự có property `address`; không thuộc project runnable bên dưới. Danh sách trên hẹp hơn `"address.*"` khi chỉ cho đúng hai thuộc tính.

**Không “whitelist một object parent” rồi suy rằng tất cả nested properties của nó đều được phép**. Xem property path semantics, pattern và generated setters; test cả những field nested cố tình gửi trái phép.

## 5. Constructor binding, property binding và declarativeBinding

Theo tài liệu Spring MVC 6.x, `@ModelAttribute` có thể sử dụng **constructor binding** và **setter/property binding**. Hai đường này cần được phân biệt khi đánh giá một allowlist.

### 5.1. Property binding

Với JavaBean:

```java
public class ContactForm {
    private String email;
    private String phone;

    public ContactForm() {}

    public void setEmail(String email) {
        this.email = email;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }

    // getters...
}
```

Spring có thể tạo object bằng constructor rỗng rồi gán qua setters. Với cấu hình `setAllowedFields("email")`, property `phone` trong request bị loại ở property-binding phase.

### 5.2. Constructor binding và immutable DTO

Với record:

```java
public record ChangeEmailRequest(
        @NotBlank @Email String email) {
}
```

Đây là fragment cần import các Jakarta constraints. Khi dùng record làm `@ModelAttribute` phù hợp, Spring có thể dùng constructor binding để tạo object từ input. Record **không có setter role/locked** vì những field này không nằm trong constructor và không có trong type.

Ưu điểm: surface of input dễ nhìn; immutable object giúp tránh gán thêm field sau khi khởi tạo. Tuy nhiên:

- **Constructor parameters vẫn là dữ liệu không tin cậy** và cần validation.
- **`setAllowedFields(...)` chủ yếu điều khiển property binding**, không phải danh sách filter cho mọi constructor parameter.
- Nếu constructor của bạn chứa `role` hoặc `ownerId`, việc dùng immutable record **không tự khiến các giá trị đó được an toàn**. DTO phải *chỉ khai báo những tham số mà request được phép cung cấp*.
- Khi record/constructor parameter cần tên HTTP khác tên Java, Spring có thể dùng `@BindParam` theo tài liệu và test mapping tương ứng.
- Một DTO có constructor nhận mọi field entity **không còn là DTO theo tác vụ chỉ vì nó là record**.

### 5.3. setDeclarativeBinding(true)

Spring cung cấp cơ chế declarative binding:

```java
@ControllerAdvice
public class BinderPolicy {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Đây là **fragment của global config**, không thuộc project runnable bên dưới. Khi bật `declarativeBinding`, Spring tiếp tục áp dụng constructor binding, còn setter/property binding **chỉ được áp dụng khi có `allowedFields` được khai báo**.

Điều này hữu ích nếu hệ thống muốn mặc định an toàn hơn cho property binding. Nhưng không nên hiểu là:

- “Vô hiệu hóa tất cả data binding” — constructor binding vẫn hoạt động.
- “Mọi input trong constructor tự an toàn” — bạn phải thiết kế constructor input chặt chẽ.
- “Tự động chặn JSON properties” — Jackson có pipeline riêng.
- “Không cần test” — một `@InitBinder` khác vẫn có thể cấu hình allowedFields cho binder của một form.

Khi áp dụng toàn cục, nên chạy regression tests cho những form cũ dựa trên setters, marker/default fields, nested collections và các handlers dùng constructor binding. Một thay đổi global có thể ảnh hưởng lớn đến hành vi form.

### 5.4. Khi nào chọn cách nào?

| Trường hợp | Lựa chọn khuyến nghị |
| --- | --- |
| API command mới, ít field, không cần mutate | Record/immutable task DTO, constructor binding hoặc Jackson DTO |
| HTML form đang dùng setters | Dedicated JavaBean input DTO + `setAllowedFields` rõ ràng |
| Hệ thống đang bind domain entity trực tiếp | Refactor sang DTO riêng; trong lúc chuyển đổi phải có allowlist chặt |
| Có nhiều form legacy khó sửa cùng lúc | Cân nhắc declarative binding và từng bước bổ sung allowlists/tests |
| JSON REST dùng `@RequestBody` | DTO/record riêng, Jackson mapping có kiểm soát, validation, authorization |
| Một field chỉ admin được sửa | Endpoint/command admin riêng + authorization; không chỉ hiện/ẩn UI |

## 6. Ví dụ Java 17: hai tác vụ, hai DTO, hai allowlist

### 6.1. Mục đích và hành vi cần quan sát

Dự án Spring Boot MVC tối giản có hai endpoint:

- **`POST /accounts`**: tạo tài khoản từ `CreateAccountForm` với `displayName`, `email` và `acceptedTerms`.
- **`POST /accounts/{accountId}/contact`**: thay đổi thông tin liên hệ bằng `ChangeContactForm` với `email`, `phone`, `newsletter`.

Trong domain, tài khoản còn có `id` và `role`. Hai field này **luôn do server quản lý**, không xuất hiện trên input DTO. Server gán `role="MEMBER"` lúc tạo tài khoản, rồi giữ nguyên role khi đổi liên hệ.

Đồng thời:

- `@InitBinder("createAccount")` chỉ cho property binding các field tạo tài khoản.
- `@InitBinder("contactChange")` chỉ cho property binding các field thay đổi liên hệ.
- `BindingResult#getSuppressedFields()` phát hiện request cố gửi `role`, `id`, `displayName` trên endpoint không cho phép.
- `@Valid` kiểm tra `@NotBlank`, `@Email`, `@AssertTrue`, `@Pattern` và `@NotNull`.
- MockMvc gửi form-urlencoded thật qua MVC infrastructure, kiểm chứng cả happy path lẫn malicious/invalid payloads.

Đây là **ví dụ in-memory nhằm quan sát binding và policy**, không phải hệ thống phân quyền, lưu trữ hoặc xác minh email. Trong production, thay in-memory map bằng repository, bổ sung authentication/authorization, transaction, unique constraint và audit.

### 6.2. Cấu trúc project

```text
task-dto-allowlist/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── TaskDtoApplication.java
    │   ├── CreateAccountForm.java
    │   ├── ChangeContactForm.java
    │   ├── AccountService.java
    │   └── AccountController.java
    └── test/java/demo/
        └── AccountBindingSecurityTest.java
```

### 6.3. pom.xml

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
    <artifactId>task-dto-allowlist</artifactId>
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

Spring Boot parent quản lý các phiên bản Spring Framework/Jackson/Hibernate Validator phù hợp với starter. `spring-boot-starter-validation` được khai báo rõ vì `@Valid` cần một Jakarta Validation provider thực sự khi thực thi constraints.

### 6.4. src/main/java/demo/TaskDtoApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskDtoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaskDtoApplication.class, args);
    }
}
```

Main class và các type khác cùng package `demo` để component scan thấy controller và service.

### 6.5. src/main/java/demo/CreateAccountForm.java

```java
package demo;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class CreateAccountForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @AssertTrue
    private Boolean acceptedTerms;

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

    public Boolean getAcceptedTerms() {
        return acceptedTerms;
    }

    public void setAcceptedTerms(Boolean acceptedTerms) {
        this.acceptedTerms = acceptedTerms;
    }
}
```

Ý nghĩa:

- `displayName` và `email` bắt buộc có nội dung. `@Email` kiểm tra format theo provider; không chứng minh email thực sự tồn tại hoặc đã xác minh.
- `acceptedTerms` dùng `Boolean` với `@NotNull` và `@AssertTrue` để phân biệt thiếu giá trị và giá trị `false`. Chấp thuận điều khoản thường còn có yêu cầu lưu **version và thời điểm đồng ý** trong service/DB; demo chưa triển khai.
- Không có setters cho `role`, `id`, `locked` hoặc `ownerId`. Đây là quyết định **cấu trúc DTO**, không phải chỉ xóa các ô khỏi form HTML.

Nếu sau này domain có thêm `creditLimit` hoặc `securityFlags`, `CreateAccountForm` sẽ không tự mở các field đó.

### 6.6. src/main/java/demo/ChangeContactForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public class ChangeContactForm {

    @NotBlank
    @Email
    private String email;

    // Có thể bỏ trống bằng cách không gửi phone;
    // nếu có giá trị thì phải khớp mẫu demo.
    @Pattern(regexp = "\\+?[0-9]{8,15}")
    private String phone;

    @NotNull
    private Boolean newsletter;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPhone() {
        return phone;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }

    public Boolean getNewsletter() {
        return newsletter;
    }

    public void setNewsletter(Boolean newsletter) {
        this.newsletter = newsletter;
    }
}
```

DTO này **không có `displayName`, `role` hoặc `id`** vì tác vụ chỉ thay đổi contact information và newsletter preference.

Để ví dụ có semantics rõ ràng, endpoint này là **một lệnh thay thế thông tin liên hệ**: `email` và `newsletter` bắt buộc, `phone` vắng mặt tương đương đặt thành `null` (xóa số điện thoại). Nó **không phải PATCH partial-update semantics**. Nếu muốn PATCH, cần giải quyết riêng “field vắng mặt”, “field gửi null” và “field gửi giá trị” để tránh ghi đè ngoài ý muốn.

`@Pattern` cho phép null theo quy tắc Bean Validation chuẩn; điều này hợp với thiết kế phone tùy chọn. Nếu muốn chuỗi rỗng cũng đại diện “không có phone”, cần thêm normalization/validator phù hợp thay vì giả định `@Pattern` coi mọi chuỗi rỗng như null.

### 6.7. src/main/java/demo/AccountService.java

```java
package demo;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class AccountService {

    public record Account(
            long id,
            String displayName,
            String email,
            String phone,
            boolean newsletter,
            String role) {
    }

    private final ConcurrentMap<Long, Account> accounts =
            new ConcurrentHashMap<>();

    private final AtomicLong nextId = new AtomicLong(100);

    public AccountService() {
        // Dữ liệu mẫu phục vụ kiểm thử lệnh đổi contact.
        accounts.put(42L, new Account(
                42L,
                "Lan",
                "lan@example.org",
                "+84911111111",
                false,
                "MEMBER"
        ));
    }

    public Account create(CreateAccountForm form) {
        long id = nextId.incrementAndGet();

        // id và role do server quyết định; không lấy từ request.
        Account account = new Account(
                id,
                form.getDisplayName(),
                form.getEmail(),
                null,
                false,
                "MEMBER"
        );

        accounts.put(id, account);
        return account;
    }

    public Optional<Account> changeContact(
            long accountId, ChangeContactForm form) {

        Account updated = accounts.computeIfPresent(
                accountId,
                (id, current) -> new Account(
                        current.id(),
                        current.displayName(),
                        form.getEmail(),
                        form.getPhone(),
                        Boolean.TRUE.equals(form.getNewsletter()),
                        current.role()
                )
        );

        return Optional.ofNullable(updated);
    }
}
```

**Điểm bảo mật trung tâm:**

- Tạo tài khoản: chỉ copy `displayName` và `email` từ `CreateAccountForm`. ID lấy từ server, role là `MEMBER`.
- Đổi contact: dùng `current.id()`, `current.displayName()` và `current.role()` giữ nguyên; chỉ copy các field có trong lệnh.
- Không gọi reflection/automatic mapper cấu hình lỏng để copy toàn bộ request object vào entity.
- Không dùng `Map<String,Object>` từ HTTP làm danh sách property sửa domain.
- Dữ liệu `42L` chỉ là fixture để test update độc lập; không phải ID bảo mật hay tài khoản thực tế.

**Giới hạn minh họa:** `AccountService` này **chưa có authentication, authorization, transaction, unique email checks hoặc persistence**. Production phải xác định principal có quyền tác động tới `accountId` rồi mới update. `ConcurrentHashMap` và `AtomicLong` chỉ tạo một ví dụ Java runnable, không thay thế database và concurrency control nghiệp vụ.

### 6.8. src/main/java/demo/AccountController.java

```java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    private final AccountService accounts;

    public AccountController(AccountService accounts) {
        this.accounts = accounts;
    }

    @InitBinder("createAccount")
    public void initCreateAccount(WebDataBinder binder) {
        binder.setAllowedFields(
                "displayName", "email", "acceptedTerms");
    }

    @InitBinder("contactChange")
    public void initContactChange(WebDataBinder binder) {
        binder.setAllowedFields(
                "email", "phone", "newsletter");
    }

    @PostMapping(
            path = "/accounts",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("createAccount")
                    CreateAccountForm form,
            BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            return rejectSuppressed(result);
        }
        if (result.hasErrors()) {
            return rejectInvalid(result);
        }

        AccountService.Account created = accounts.create(form);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }

    @PostMapping(
            path = "/accounts/{accountId}/contact",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> changeContact(
            @PathVariable long accountId,
            @Valid @ModelAttribute("contactChange")
                    ChangeContactForm form,
            BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            return rejectSuppressed(result);
        }
        if (result.hasErrors()) {
            return rejectInvalid(result);
        }

        // Production: authorization theo principal và accountId
        // phải được thực thi trước khi cập nhật resource.
        var changed = accounts.changeContact(accountId, form);
        if (changed.isEmpty()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(changed.get());
    }

    private static ResponseEntity<?> rejectSuppressed(
            BindingResult result) {

        List<String> fields = Arrays.stream(
                result.getSuppressedFields())
                .distinct()
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(Map.of(
                "code", "DISALLOWED_FIELDS",
                "fields", fields
        ));
    }

    private static ResponseEntity<?> rejectInvalid(
            BindingResult result) {

        List<String> fields = result.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        List<String> bindingFailures = result.getFieldErrors()
                .stream()
                .filter(FieldError::isBindingFailure)
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(Map.of(
                "code", "INPUT_INVALID",
                "fields", fields,
                "bindingFailures", bindingFailures
        ));
    }
}
```

Lý do cho cách triển khai:

1. **Hai `@InitBinder` có tên**: việc chọn allowlist không dựa vào cùng/khác Java class, mà theo `@ModelAttribute("createAccount")` và `@ModelAttribute("contactChange")`.
2. **Đầu vào giới hạn bằng DTO**: controller không nhận `AccountService.Account` và không nhận entity có setter cho role.
3. **Allowlist đóng vai trò phòng thủ bổ sung**: kể cả client gửi `role` hoặc `id` trong form/query parameters, binder phát hiện field bị suppress; controller trả 400 thay vì lặng lẽ tiếp tục.
4. **`BindingResult` đặt ngay sau form object**: lỗi binding/validation được nhận trong controller; không chuyển thành lỗi 500.
5. **Kiểm tra suppressed fields trước `hasErrors()`**: field bị cấm không nhất thiết là `FieldError`; nhánh `DISALLOWED_FIELDS` làm contract dễ phân loại.
6. **Phân biệt `isBindingFailure()`**: khi `newsletter=maybe` không thể chuyển thành `Boolean`, field lỗi được ghi nhận là type conversion error.
7. **Không có mass update**: service sử dụng explicit mapping và giữ nguyên role.
8. **Không nhầm input validation với authorization**: ví dụ chưa giải quyết quyền thực tế của caller; production cần thêm lớp đó.

**Lưu ý response:** demo trả domain record để người học quan sát role không đổi. Production nên có **output DTO** để kiểm soát trường nào được xuất theo quyền xem; không mặc nhiên serialize mọi field của entity, nhất là thông tin cá nhân hoặc bí mật.

### 6.9. src/test/java/demo/AccountBindingSecurityTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountBindingSecurityTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder createRequest(
            String displayName, String email, String acceptedTerms) {

        return post("/accounts")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", displayName)
                .param("email", email)
                .param("acceptedTerms", acceptedTerms);
    }

    private MockHttpServletRequestBuilder contactRequest(
            String email, String newsletter) {

        return post("/accounts/42/contact")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", email)
                .param("phone", "+84912345678")
                .param("newsletter", newsletter);
    }

    @Test
    void creationAssignsRoleOnServer() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "true"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.displayName").value("Mai"))
                .andExpect(jsonPath("$.role").value("MEMBER"));
    }

    @Test
    void creationRejectsInjectedRole() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "true")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void creationRejectsClientChosenId() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "true")
                        .param("id", "999"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("id")));
    }

    @Test
    void invalidEmailDoesNotReachService() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "not-an-email", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields", hasItem("email")));
    }

    @Test
    void falseAcceptedTermsFailsValidation() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "false"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("acceptedTerms")));
    }

    @Test
    void contactChangePreservesIdentityAndRole()
            throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.email")
                        .value("new@example.org"))
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.newsletter").value(true));
    }

    @Test
    void contactChangeRejectsInjectedRole() throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "true")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void contactChangeRejectsDisplayName() throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "true")
                        .param("displayName", "Attacker"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields",
                        hasItem("displayName")));
    }

    @Test
    void contactChangeRejectsInvalidPhone() throws Exception {
        mvc.perform(post("/accounts/42/contact")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("email", "new@example.org")
                        .param("newsletter", "true")
                        .param("phone", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields", hasItem("phone")));
    }

    @Test
    void wrongBooleanIsBindingFailure() throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "maybe"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.bindingFailures",
                        hasItem("newsletter")));
    }

    @Test
    void missingNewsletterIsNotNullViolation()
            throws Exception {
        mvc.perform(post("/accounts/42/contact")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("email", "new@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("newsletter")));
    }

    @Test
    void nonexistentResourceIsNotFound() throws Exception {
        mvc.perform(post("/accounts/999999/contact")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("email", "new@example.org")
                        .param("phone", "+84912345678")
                        .param("newsletter", "false"))
                .andExpect(status().isNotFound());
    }
}
```

**Bộ test 12 tình huống** gồm:

- Tạo thành công: server quyết định role.
- Gửi `role=ADMIN` khi tạo: bị suppress.
- Gửi `id=999` khi tạo: bị suppress.
- Email tạo tài khoản sai định dạng: không được chấp nhận.
- Chưa chấp thuận điều khoản: vi phạm `@AssertTrue`.
- Đổi contact hợp lệ: ID, displayName và role được giữ nguyên.
- Cố đổi role qua tác vụ contact: bị suppress.
- Cố đổi displayName qua tác vụ contact: bị suppress.
- Phone sai mẫu: vi phạm `@Pattern`.
- Boolean sai kiểu: type conversion failure.
- Thiếu `newsletter`: vi phạm `@NotNull`.
- Resource không có trong demo store: 404.

**Tính độc lập test:** fixture `id=42` có `displayName="Lan"` và `role="MEMBER"`. Các test đổi contact có thể cập nhật email/phone trên fixture trong cùng context, nhưng không test nào phụ thuộc thứ tự email từ một test khác; những assertion kiểm tra role/displayName được service giữ bất biến.

### 6.10. Chạy và kiểm tra đầu ra

Tại thư mục project, dùng JDK 17+ và Maven:

```bash
mvn -q clean test
```

**Kỳ vọng:** 12 test thành công, Maven trả exit code 0 khi dependencies đã có và môi trường phù hợp. Không cung cấp một stdout Maven giả định là đã quan sát vì mức log và bản Surefire/JUnit có thể khác nhau. Các assertion kiểm tra HTTP status, JSON response code, tên field và giá trị domain sau mapping.

Khởi chạy server:

```bash
mvn spring-boot:run
```

Request tạo tài khoản hợp lệ:

```bash
curl -i -X POST 'http://localhost:8080/accounts' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Mai' \
  --data-urlencode 'email=mai@example.org' \
  --data-urlencode 'acceptedTerms=true'
```

HTTP **201 Created** với body minh họa (ID mới do server sinh, ví dụ dưới giả sử sequence vừa khởi động và lần tạo đầu tiên):

```json
{
  "id": 101,
  "displayName": "Mai",
  "email": "mai@example.org",
  "phone": null,
  "newsletter": false,
  "role": "MEMBER"
}
```

Request cố chiếm role:

```bash
curl -i -X POST 'http://localhost:8080/accounts' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Mai' \
  --data-urlencode 'email=mai@example.org' \
  --data-urlencode 'acceptedTerms=true' \
  --data-urlencode 'role=ADMIN'
```

HTTP **400 Bad Request** với:

```json
{
  "code": "DISALLOWED_FIELDS",
  "fields": ["role"]
}
```

Request cập nhật contact cho fixture:

```bash
curl -i -X POST 'http://localhost:8080/accounts/42/contact' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=contact@example.org' \
  --data-urlencode 'phone=+84912345678' \
  --data-urlencode 'newsletter=true'
```

HTTP **200 OK**, body có `displayName="Lan"`, `role="MEMBER"`, `email="contact@example.org"` và `newsletter=true`. Nếu thêm `displayName=Attacker` hoặc `role=ADMIN`, controller trả mã `DISALLOWED_FIELDS`.

**Lưu ý:** vì ví dụ có mutable in-memory store và generated IDs, không nên assert một ID mới cụ thể trong mọi môi trường/test order. Chỉ cố định ID của fixture 42 cho các bài test cần account đã tồn tại.

## 7. Giới hạn của setAllowedFields: không phải bộ lọc JSON Jackson

Đây là khác biệt rất quan trọng.

### 7.1. Form / @ModelAttribute

Ví dụ runnable dùng:

```java
@Valid @ModelAttribute("createAccount") CreateAccountForm form
```

Với request `application/x-www-form-urlencoded` (hoặc request parameters từ các nguồn mà `@ModelAttribute` hỗ trợ), Spring dùng binder cho **property binding**. `setAllowedFields("displayName", "email", "acceptedTerms")` kiểm soát property names được gắn qua cơ chế này.

### 7.2. JSON / @RequestBody

Một endpoint khác:

```java
@PostMapping("/api/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateAccountJson request) {
    // ...
    return ResponseEntity.ok().build();
}
```

Đây là **fragment**, cần định nghĩa `CreateAccountJson`; không thuộc project Maven runnable bên trên. Jackson (hoặc HTTP message converter khác) deserialize JSON thành DTO **trước** bước validation. `WebDataBinder#setAllowedFields` **không lọc trực tiếp tất cả JSON properties của Jackson** như nó lọc setter/property binding cho `@ModelAttribute`.

Với JSON, thiết kế an toàn thường là:

- **Task-specific record/class** chỉ có những fields request cần.
- Định nghĩa Jackson property names và deserialization behavior có kiểm soát.
- Nếu API yêu cầu **từ chối unknown fields** thay vì lờ đi, cấu hình Jackson nghiêm ngặt một cách tường minh và test toàn bộ pipeline.
- Không dùng JPA entity làm `@RequestBody` nếu nó có fields nhạy cảm.
- Service chỉ copy các field của command được phép thay đổi.
- Có authentication/authorization độc lập với validation.

Ví dụ JSON input DTO:

```java
public record CreateAccountJson(
        @NotBlank String displayName,
        @NotBlank @Email String email,
        @NotNull @AssertTrue Boolean acceptedTerms) {
}
```

Đây là fragment cần imports Jakarta constraints. Nó không có `role` hay `id`. Nhưng **đừng cho rằng mọi JSON field lạ đều mặc định bị reject**: Jackson/Boot có những cấu hình liên quan unknown properties, và mặc định có thể bỏ qua. Điều quan trọng là **field lạ không được phép ảnh hưởng domain**; việc muốn báo lỗi 400 khi có unknown property là **một contract riêng** cần cấu hình và kiểm thử.

### 7.3. @JsonIgnore và @JsonProperty(access=...) có thay thế DTO không?

Jackson annotations có thể điều khiển serialization/deserialization của một property, ví dụ chỉ đọc hoặc bỏ qua một số fields. Chúng hữu ích, nhưng nếu bind **cả entity** với nhiều annotation phân tán, rủi ro vẫn tăng khi field mới xuất hiện hoặc serialization rules thay đổi.

Task-specific DTO dễ review hơn: field không thuộc input thì không hiện diện trong type. Jackson restrictions/strict mode có thể bổ sung bảo vệ, không nhất thiết thay thế ranh giới thiết kế DTO.

## 8. Scoped @InitBinder và một controller có nhiều tác vụ

Trong demo:

```java
@InitBinder("createAccount")
void createBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "displayName", "email", "acceptedTerms");
}

@InitBinder("contactChange")
void contactBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "email", "phone", "newsletter");
}
```

Hai hàm chỉ là **fragment rút gọn** của controller runnable. Nếu dùng `@InitBinder` không tên:

```java
@InitBinder
void all(WebDataBinder binder) {
    binder.setAllowedFields("email");
}
```

thì initializer có thể áp dụng rộng cho các binder trong controller; một cấu hình như vậy có thể làm form tạo tài khoản không bind được `displayName` hoặc `acceptedTerms`.

**Tránh nhiều initializer cùng set `allowedFields` cho một binder** mà không hiểu thứ tự và chính sách “ai sở hữu allowlist”. Nếu cả global `@ControllerAdvice` và local controller cùng gọi `setAllowedFields(...)`, lệnh setter cuối cùng có thể thay thế danh sách trước đó; không coi Spring tự hợp nhất hai allowlists theo phép giao.

### 8.1. Nhiều controller dùng một policy

Có thể đặt cấu hình chung ở `@ControllerAdvice`, nhưng phải xác định phạm vi:

```java
@ControllerAdvice(assignableTypes = AccountController.class)
public class AccountBinderAdvice {

    @InitBinder("contactChange")
    void restrict(WebDataBinder binder) {
        binder.setAllowedFields("email", "phone", "newsletter");
    }
}
```

Đây là **fragment cách tổ chức thay thế**, không thêm vào demo runnable vì sẽ trùng với `@InitBinder` local. `assignableTypes` giới hạn controller nhận advice; `@InitBinder("contactChange")` giới hạn binder có objectName phù hợp.

Khi di chuyển policy từ local sang global, phải điều chỉnh tests và tránh trùng lặp. Một advice không giới hạn controller có thể áp dụng cho nhiều endpoints dùng cùng model attribute name nhưng ý nghĩa nghiệp vụ khác, gây hiệu ứng ngoài dự kiến.

### 8.2. Nhiều DTO dùng cùng một Java class vẫn có thể khác policy

Khi hai tác vụ thực sự có chung DTO type nhưng cần allowlist khác nhau, có thể dùng hai tên model attributes:

```java
@ModelAttribute("publicProfile") ProfileForm publicProfile
@ModelAttribute("privateProfile") ProfileForm privateProfile
```

và scoped binders theo từng tên. Tuy nhiên, **nếu tập fields được phép thực sự khác nhau**, cân nhắc tạo **hai DTO theo tác vụ** sẽ dễ review hơn là giữ một type có quá nhiều writable properties rồi dựa hoàn toàn vào binder name.

## 9. Allowed field patterns, nested objects, List và Map

`DataBinder#setAllowedFields(...)` nhận **property paths hoặc patterns**, không chỉ tên field cấp đầu. Tài liệu Spring mô tả ví dụ như:

- `"address"`: khớp property address.
- `"person.address.city"`: property lồng nhau.
- `"addresses[0].city"`: field city của phần tử đầu danh sách/array.
- `"map[key]"`: entry cụ thể trong Map.
- `"map*"`: wildcard cho các entries bắt đầu với tiền tố map tương ứng.

Nhưng **khả năng biểu diễn không đồng nghĩa nên mở rộng allowlist thoải mái**. Với domain nhạy cảm, chỉ cho update property path thực sự thuộc tác vụ.

### 9.1. List of objects

Ví dụ fragment với DTO có `List<AddressForm> addresses`:

```java
binder.setAllowedFields(
        "addresses[*].city",
        "addresses[*].postcode"
);
```

Spring wildcard `*` có thể khớp index bên trong bracket. Phải test property names thực tế, limit số phần tử và không cho client chỉnh `addresses[0].id` hoặc `addresses[0].ownerId` nếu endpoint không có quyền đó.

Không dùng `"addresses*"` khi chỉ cần city/postcode, vì nó có thể khớp cả các property nested khác.

### 9.2. Map keys

Với Map keys động:

```java
binder.setAllowedFields(
        "preferences[news]",
        "preferences[offers]"
);
```

Đây là fragment. Nó chỉ diễn đạt một tập key hữu hạn. Nếu client được phép sửa bất kỳ key nào, cần thêm **key validation**, kích thước tối đa, kiểm tra tên key, value constraints và auth theo ngữ cảnh; pattern `"preferences*"` không thay thế những kiểm tra đó.

### 9.3. Constructor arguments là trường hợp khác

Khi dùng record/constructor binding, request có thể cung cấp các parameters tương ứng với constructor arguments. `setAllowedFields` **không phải cơ chế allowlist tổng quát cho constructor arguments**. Nếu record chứa `List<@Valid LineItem> items`, chính thiết kế record + constraints + constructor binding quyết định shape được chấp nhận. Tránh dùng một constructor gồm cả `ownerId`, `role` và `price` rồi kỳ vọng allowedFields của property binding vô hiệu hóa chúng.

### 9.4. Bảo vệ collection size và auto-grow

Một client có thể gửi quá nhiều indexed parameters như `items[999999].name` nhằm tạo áp lực lên binder hoặc các collection. Spring có `DataBinder#setAutoGrowCollectionLimit(...)`, nhưng cần cấu hình phù hợp và giới hạn số lượng request parameters, body size, depth, và business-level max item count.

Đừng chỉ tập trung vào field ownership mà bỏ qua **resource exhaustion** khi cho bind danh sách/Map lớn.

## 10. Khi nào chọn @ModelAttribute(binding=false)?

Nếu controller cần **đọc** một domain object để tham chiếu nhưng **không muốn bind request lên nó**, có thể sử dụng:

```java
@ModelAttribute(binding = false) AccountEntity existingAccount
```

Đây là fragment, `AccountEntity` cần tồn tại trong model trước đó và controller cần logic lấy account theo ID. `binding=false` ngăn data binding của attribute từ request tại vị trí đó.

Ví dụ kiến trúc:

```java
@PostMapping("/accounts/{id}/contact")
public String save(
        @Valid @ModelAttribute("contactChange") ChangeContactForm input,
        BindingResult errors,
        @ModelAttribute(binding = false) AccountEntity existing) {
    // Chỉ cập nhật existing thông qua service sau khi kiểm tra quyền.
    return "done";
}
```

Đây là **fragment**, không phải endpoint runnable trong demo. `binding=false` không tự tải entity hoặc kiểm tra quyền; cần có model population và service phù hợp. Nên tránh để client có khả năng thay thế entity được lấy từ DB bằng dữ liệu request qua một path binding khác.

## 11. Validation khác authorization, và mapping chỉ an toàn khi làm đúng chỗ

Một lỗi phổ biến là tin rằng `@Valid` đảm bảo update an toàn. Thực tế:

- `@NotBlank` kiểm tra chuỗi không trống.
- `@Email` kiểm tra kiểu định dạng email.
- `@Min` kiểm tra số dưới ngưỡng.
- `@AssertTrue` kiểm tra điều kiện Boolean.
- **Không annotation nào trong số này xác định user X có được đổi email của account Y không.**

Authorization cần kiểm tra ít nhất:

1. **Actor:** caller đã đăng nhập, vai trò/phạm vi quyền gì?
2. **Action:** tạo, đổi contact, đổi role, khóa account, xóa account?
3. **Resource:** account có thuộc caller hoặc phạm vi quản trị của caller?
4. **Allowed transition:** state hiện tại có cho thực hiện thao tác không?
5. **Business invariants:** email verified, unique email, lock status hoặc phê duyệt?

Một service thực tế có thể có chữ ký kiểu:

```java
public AccountView changeContact(
        AuthenticatedActor actor,
        long accountId,
        ChangeContactCommand command) {

    Account account = repository.findById(accountId)
            .orElseThrow(NotFoundException::new);

    authorization.requireCanEditContact(actor, account);

    account.setEmail(command.email());
    account.setPhone(command.phone());
    account.setNewsletter(command.newsletter());

    repository.save(account);
    return AccountView.from(account);
}
```

Đây là **fragment kiến trúc**, các class/service chưa được định nghĩa; không coi là code runnable trong Maven demo. Ý nghĩa là authorization đặt ở ranh giới service/resource, sau đó **chỉ cập nhật field được command cho phép**. Không gọi `BeanUtils.copyProperties(request, account)` không giới hạn khi account có fields nhạy cảm.

### Tránh IDOR/BOLA khi dùng accountId trên URL

Ngay cả endpoint có input DTO không chứa role cũng có thể bị lạm dụng nếu caller thay `/accounts/42/contact` thành `/accounts/43/contact` và server cập nhật tài khoản 43 mà không kiểm tra sở hữu. Đây là vấn đề **Broken Object Level Authorization (BOLA)**, không phải mass assignment. Hai loại lỗi thường cùng xuất hiện trong hệ thống CRUD và phải được xử lý độc lập.

### Kiểm tra concurrency

Nếu hai request cùng sửa contact, cần cơ chế giao dịch/optimistic locking hoặc quy tắc xử lý concurrent writes khi nghiệp vụ yêu cầu. Demo `ConcurrentHashMap.computeIfPresent` chỉ giúp tránh cập nhật map không đồng bộ cơ bản; nó **không thay** database transaction hoặc business version conflict handling.

## 12. “Field không tồn tại trên DTO” và “field bị suppress” khác nhau

Tác vụ có thể chọn:

- **Ignore unknown input:** nếu DTO không chứa `role` và framework có cấu hình lờ field không biết, request được xử lý mà không dùng role.
- **Reject unknown input:** nếu client gửi field ngoài hợp đồng, trả 400.
- **Audit unknown input:** chặn hoặc ghi event với thông tin đã redaction, không log giá trị nhạy cảm.

Trong demo, `setAllowedFields` làm một tên field không được phép (ví dụ `role`) bị suppress trong property-binding phase. Controller xem `getSuppressedFields()` và trả **`DISALLOWED_FIELDS`**.

Tuy nhiên, **chính sách này chỉ chứng minh ở pipeline `@ModelAttribute` + property binding được sử dụng**. Với `@RequestBody`, Jackson có rule khác về unknown properties; với constructor binding, allowedFields không chặn constructor arguments theo cùng cách.

### Vì sao không chỉ dựa vào getSuppressedFields()?

Một ứng dụng có thể bỏ qua `getSuppressedFields()` nhưng vẫn an toàn nếu DTO không có property nhạy cảm và service mapping chỉ chọn field được phép; tuy nhiên nó có thể vô tình **chấp nhận request không đúng contract** mà không báo lỗi, làm client hiểu nhầm.

Nếu API cần phản hồi chính xác “field không được phép”, hãy dùng contract rõ và tests chặn extra fields. Nếu API cho phép ignore unknown fields vì tương thích client, hãy công bố và vẫn bảo đảm chúng không thay đổi domain state.

**Đừng suy rằng không có suppressed fields là bằng chứng authorization đã pass.** Không có input extra fields không nói gì về actor có quyền sửa resource hay không.

### Có nên dùng raw map cho partial update?

Ví dụ:

```java
@PostMapping("/accounts/patch")
public void patch(@RequestBody Map<String, Object> values) {
    // ...
}
```

Đây là fragment anti-pattern. Nếu service loop qua `values.entrySet()` rồi dùng reflection để gọi setters trên entity, ranh giới các fields được phép bị mờ và dễ dẫn tới over-posting.

Nếu dùng JSON Merge Patch/JSON Patch, cần **schema, danh sách operations/paths được phép, validation, authorization**, kiểm soát nested paths và xử lý null semantics. Không giả định mọi property path mà patch body gửi lên đều được phép chỉ vì nó là JSON hợp lệ.

## 13. Cách kiểm thử mass assignment có hệ thống

Một bộ test tốt phải có **negative cases cố ý gửi field trái phép**. Chỉ test form hợp lệ với ba field được thiết kế không chứng minh allowlist thực sự chạy.

### Ma trận theo tác vụ

| Tác vụ | Payload bổ sung | Kết quả bảo mật mong muốn |
| --- | --- | --- |
| Create account | `role=ADMIN` | Bị từ chối hoặc bỏ qua theo contract; role server vẫn MEMBER |
| Create account | `id=999` | Client không quyết định ID |
| Create account | `locked=false` | Client không điều khiển trạng thái khóa |
| Change contact | `displayName=Attacker` | Không sửa tên hiển thị |
| Change contact | `role=ADMIN` | Không đổi role |
| Change contact | `ownerId=1` | Không chuyển chủ sở hữu |
| Change contact | `email=invalid` | Constraint email thất bại |
| Change contact | `newsletter=maybe` | Binding lỗi kiểu Boolean |
| Change contact | Không có `newsletter` | Validation xác định thiếu giá trị |
| Change contact | ID của người dùng khác | Authorization từ chối trước khi ghi |
| Change contact | Account không tồn tại | 404 hoặc xử lý theo contract |
| Admin change role | User không có quyền quản trị | 403 (hoặc response policy tương ứng) |
| Nested form | `addresses[0].ownerId=...` | Không được mutate nested owner field |
| JSON command | Extra property `role` | Không ảnh hưởng domain; reject/ignore theo contract |

**Phân biệt rõ:** trong demo, kiểm thử ID của account khác, quyền admin và nested collection là **kế hoạch kiểm thử production** chứ không phải test code đã được hiện thực. Demo runnable bao phủ 12 tình huống đầu vào/allowlist được liệt kê ở phần 6.

### Dạng assertion nên ưu tiên

- Assert HTTP status và error code máy đọc được.
- Assert field bị suppress theo tên, không xuất raw value.
- Assert **state sau service mapping**: role và ID không đổi.
- Assert command DTO không có setter/property ngoài hợp đồng (qua review/API schema).
- Assert validation lỗi đúng field và lỗi type conversion được phân loại.
- Assert unauthorized user không thể tác động resource khác (integration/security tests).
- Assert các thay đổi thêm property mới vào entity **không mở rộng input DTO**.

### Không test bằng cách gọi controller method trực tiếp

Nếu chỉ:

```java
AccountController controller = new AccountController(service);
// controller.create(new CreateAccountForm(), ...);
```

thì bạn phải tự dựng `BindingResult` và không có quá trình MVC argument resolution/binding từ HTTP request. Một unit test như vậy không chứng minh `@InitBinder` được chọn hay `allowedFields` đã lọc property. Dùng `MockMvc` với controller và MVC context thật cho các assertion về binder.

## 14. Các lỗi phổ biến khi thiết kế DTO theo tác vụ

### 14.1. Đặt tên DTO “AccountDto” nhưng chứa toàn bộ entity

DTO bảo mật bởi **tập field và semantics**, không bởi hậu tố `Dto`. Nếu `AccountDto` vẫn có role, ownerId, locked, accountBalance và tất cả setters, rủi ro over-posting vẫn tồn tại.

### 14.2. Dùng DTO hiển thị làm DTO cập nhật

Một API response có thể cần trả `role` và `createdAt` để UI hiển thị. Dùng chính response DTO đó làm request update là một sai lầm: việc thêm field đọc cho UI có thể trở thành field viết vào server nếu mapping thiếu kiểm soát.

### 14.3. Dùng một DTO cho cả người dùng thường và quản trị viên

Một admin có thể được cấp quyền đổi role, nhưng người dùng thường không được. Tách `ChangeRoleCommand` với `ChangeContactForm` rồi kiểm tra authorization từng action. Không dựa duy nhất vào UI ẩn nút role.

### 14.4. Gắn @NotNull cho role rồi nghĩ đã bảo vệ role

`@NotNull` chỉ yêu cầu giá trị không null. Nó không bảo đảm role do server đặt. Bảo vệ role bằng cách **không nhận role trong input task DTO** và không cập nhật role trong service, trừ workflow có quyền.

### 14.5. Dùng disallowedFields làm lớp bảo vệ duy nhất

Một denylist hiện tại có thể bỏ sót field nhạy cảm mới. Prefer task DTO + allowedFields khi dùng property binding. Nếu có lý do cần denylist, viết tests cho các trường mới và rà soát khi domain model thay đổi.

### 14.6. Để @InitBinder không đúng objectName

`@InitBinder("contactChange")` không tự áp dụng cho binder tên `contactForm`. Đặt tên `@ModelAttribute` tường minh và test một request có extra field để biết init-binder thực sự chạy.

### 14.7. Có allowedFields nhưng không kiểm tra suppressed fields

Binder có thể loại field lạ mà không tạo FieldError. Nếu hợp đồng yêu cầu reject extra fields, phải chủ động xem `BindingResult#getSuppressedFields()` thay vì chỉ `hasErrors()`.

### 14.8. Dùng @RequestBody JSON và trông chờ setAllowedFields

Jackson deserialize JSON trước khi Bean Validation; `allowedFields` của property binder không phải JSON key allowlist. Dùng input DTO riêng + Jackson strictness khi cần và test JSON pipeline tương ứng.

### 14.9. Dùng record có constructor chứa field nhạy cảm

Immutable object không tự động an toàn khi constructor lấy `role`, `locked`, `ownerId` từ untrusted input. Task DTO phải chỉ nhận field được cấp phép.

### 14.10. Cho toàn bộ nested object bằng wildcard

`setAllowedFields("profile*")` có thể match nhiều property ngoài ý định. Dùng pattern hẹp và test các nested fields xấu, đặc biệt khi domain model có object graphs sâu.

### 14.11. Map tự động mọi property từ request vào entity

Một helper kiểu `BeanUtils.copyProperties(input, entity)` không có exclusion/allowlist rõ ràng có thể mở quyền thay đổi field khi DTO/entity được mở rộng. Explicit mapping trong service là minh bạch nhất cho các mutation nhạy cảm.

### 14.12. Tin vào validation nhưng quên quyền theo resource

DTO có thể an toàn về field list nhưng một người dùng vẫn có thể sửa account khác nếu không kiểm tra ownership. Bảo vệ object-level authorization ở service, không dựa trên client-supplied ID.

### 14.13. Xem null/vắng mặt như nhau trong PATCH

Một lệnh update có thể có ngữ nghĩa “không gửi phone = giữ nguyên” hoặc “không gửi phone = xóa”. Khi hai semantics bị lẫn, data loss có thể xảy ra. Tách command cho full replacement/partial update; dùng API contract rõ cho absent/null/value.

### 14.14. Chỉ kiểm thử phần UI

Frontend ẩn field role không có nghĩa request không gửi được field đó. Cần HTTP tests gửi extra parameters bằng MockMvc/curl hoặc security tests. Kẻ tấn công không bị ràng buộc bởi biểu mẫu bạn render.

## 15. DTO riêng cho PATCH, command và hành động quản trị

### 15.1. Đổi email khác đổi vai trò

Một command sửa email có thể:

```java
public record ChangeEmailCommand(
        @NotBlank @Email String newEmail) {
}
```

Một command quản trị:

```java
public record ChangeRoleCommand(
        @NotNull AccountRole newRole) {
}
```

Đây là **fragment**; `AccountRole` là enum domain, cần khai báo ở ứng dụng thật. Chúng có semantics khác nhau: đổi role đòi quyền quản trị, audit và có thể xác minh lại danh tính; không nên gộp chỉ vì đều tác động vào `AccountEntity`.

### 15.2. Khi partial update thực sự cần phân biệt absent/null/value

Một JSON PATCH-like request có thể chứa:

```json
{"phone": null}
```

hoặc:

```json
{}
```

Hai payload này có thể mang ý nghĩa **xóa số điện thoại** và **không thay đổi số điện thoại**. Nếu deserialize cả hai vào DTO chỉ có `String phone`, chúng đều có thể trở thành `null`, làm mất thông tin “client có gửi field hay không”.

Giải pháp tùy contract:

- Dùng HTTP PUT/full replacement với tất cả field cần thiết bắt buộc.
- Dùng JSON Merge Patch (RFC 7396) và xử lý explicit null theo đúng semantics.
- Dùng JSON Patch (RFC 6902) với operations/path được kiểm tra authorization.
- Dùng một command có marker/presence wrapper được cấu hình rõ (thường cần serializer hỗ trợ).
- Dùng endpoint chuyên biệt `POST /accounts/{id}/clear-phone` thay cho một patch generic nếu nghiệp vụ phù hợp.

Không cố giải quyết partial-update semantics chỉ bằng `@NotNull` hoặc `setAllowedFields`; đó là vấn đề input representation và operation contract.

### 15.3. DTO có nested list/map

Nếu tác vụ cho sửa danh sách địa chỉ, DTO có thể chứa `List<UpdateAddressItem>`, nhưng:

- Mỗi item chỉ có fields cần update.
- ID item phải được xác thực thuộc account/caller.
- Constraints cascade bằng `@Valid` ở đúng vị trí.
- Giới hạn số phần tử và độ sâu.
- Không cho nested entity có field owner/admin trở thành writable.
- Nếu property binding dùng indexed paths, allowlist cần kiểm tra kỹ từng nested property.
- Duy trì hành vi rõ về thêm, xóa, sắp xếp và duplicate IDs.

Dùng `List<DomainAddressEntity>` trực tiếp chỉ vì có getter/setter nhanh là một dấu hiệu cần xem lại ranh giới input.

## 16. Các điểm kiểm thử bổ sung cho production

### 16.1. Kiểm thử policy ở service

Controller validation chỉ lọc dữ liệu từ HTTP. Service có thể được gọi từ job, message handler hoặc test nội bộ. Một domain service bảo mật nên đảm bảo **action và resource-level permissions** độc lập với controller hoặc thông qua một business authorization boundary thống nhất.

### 16.2. Kiểm thử concurrency và persistence

Nếu một lệnh đổi contact thực hiện nhiều cập nhật DB, dùng transaction phù hợp. Nếu dữ liệu có version, dùng optimistic locking hoặc quy tắc conflict có tài liệu hóa. Không giả định `ConcurrentHashMap.computeIfPresent` của demo đủ cho persistence thật.

### 16.3. Kiểm thử strict unknown fields cho JSON

Nếu công bố “server từ chối unknown JSON property”, test có thêm `"role":"ADMIN"`, `"id":999` hoặc typo key và xác nhận 400 theo handler JSON. Không lấy kết quả từ form-urlencoded test làm bằng chứng cho JSON.

### 16.4. Kiểm thử form field markers/defaults

Spring `WebDataBinder` xử lý HTML checkbox unchecked bằng field marker prefix, field default prefix. Nếu task DTO có Boolean/checkbox, test cả checked, unchecked và missing field. `acceptedTerms` trong demo được gửi tường minh để tránh phụ thuộc marker convention trong những test tập trung vào allowlist.

### 16.5. Kiểm thử thay đổi model

Khi thêm field mới vào entity hoặc DTO, cần review:

- Nó có thuộc request contract nào không?
- Có cần validation mới không?
- Có cần cập nhật allowlist không?
- Có được map vào domain khi nào và bởi ai?
- Có permission/consent/audit requirement không?
- Output DTO có vô tình expose dữ liệu mới không?

Một test có request extra field hoặc một schema snapshot bảo vệ việc mở rộng không chủ đích tốt hơn lời hứa “frontend sẽ không gửi”.

## 17. Checklist review khi tạo một endpoint có data binding

### Thiết kế request

- [ ] Mỗi action có **input DTO/command** đúng field và semantics.
- [ ] Không dùng JPA/domain entity có nhiều setters làm request model.
- [ ] Tách request DTO khỏi response DTO và persistence entity.
- [ ] Không lấy ID/role/owner/locked từ client khi server phải sở hữu chúng.
- [ ] Phân biệt full replacement, partial update, create, admin mutation.

### Binding và validation

- [ ] Dùng `@ModelAttribute("objectName")` rõ ràng với HTML/form request.
- [ ] Với property binding, cấu hình `setAllowedFields(...)` cụ thể theo tác vụ.
- [ ] Đặt `@InitBinder("objectName")` đúng phạm vi controller/advice.
- [ ] `BindingResult` đứng ngay sau argument được bind/validate.
- [ ] Xem `getSuppressedFields()` nếu hợp đồng cần từ chối extra fields.
- [ ] Dùng `@Valid`/`@Validated` và Bean Validation provider thật.
- [ ] Kiểm tra type conversion errors khác constraint errors.
- [ ] Không dùng allowlist làm tường bảo vệ constructor binding hoặc Jackson JSON.
- [ ] Nếu dùng `setDeclarativeBinding(true)`, kiểm thử các form cũ.
- [ ] Giới hạn nested collection/Map depth và số phần tử.

### Nghiệp vụ và phân quyền

- [ ] Xác thực actor và quyền thực hiện action trên resource.
- [ ] Service mapping **chỉ cập nhật field được phép**.
- [ ] Role, ownerId, status, lock flags và server-generated ID được quản lý riêng.
- [ ] Đảm bảo DB constraints/transactions/concurrency khi có persistence.
- [ ] Có audit trail nếu sửa field nhạy cảm.
- [ ] Response DTO chỉ xuất fields caller có quyền xem.

### Test và vận hành

- [ ] Test request hợp lệ và các giá trị constraint-invalid.
- [ ] Test extra `role`/`id`/`ownerId`/nested sensitive fields.
- [ ] Assert domain state không đổi ngoài phạm vi action.
- [ ] Test caller không có quyền với account khác.
- [ ] Test input JSON riêng nếu endpoint dùng `@RequestBody`.
- [ ] Test `@InitBinder` thực sự áp dụng trong Spring MVC, không chỉ gọi Java method.
- [ ] Không log rejected values nhạy cảm.
- [ ] Monitoring phân biệt `DISALLOWED_FIELDS` và `INPUT_INVALID`.
- [ ] Có regression tests khi thêm property mới vào entity/DTO.

## 18. Kết luận

**DTO theo tác vụ** giới hạn **những dữ liệu mà một hành động có lý do chính đáng để tiếp nhận**. **Danh sách trường được phép** của Spring giới hạn **những property paths có thể được gán qua property binding**. Hai biện pháp bổ sung cho nhau, không thay thế nhau.

Với Spring MVC:

- Ưu tiên dedicated/immutable input DTO, không bind trực tiếp JPA/domain entity.
- Với setter/property binding, dùng `@InitBinder` + `setAllowedFields(...)` theo objectName và kiểm tra `getSuppressedFields()` khi cần từ chối extra fields.
- Hiểu rằng constructor binding và `@RequestBody` JSON có cơ chế riêng, không được bảo vệ bởi `allowedFields` theo cùng cách.
- Thêm Bean Validation để kiểm tra giá trị, **service authorization** để kiểm tra actor/action/resource, và **explicit mapping** để bảo đảm chỉ thay đổi domain fields có chủ đích.
- Viết tests cố tình gửi field nhạy cảm và xác minh state sau update, thay vì chỉ test request “đúng như UI”.

Thiết kế này giảm nguy cơ mass assignment ngay cả khi domain model phát triển theo thời gian, đồng thời giúp contract của từng tác vụ rõ ràng, dễ kiểm thử và dễ review bảo mật.

## Tài liệu tham khảo

- [Spring Framework — MVC Data Binding và Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — MVC @ModelAttribute arguments và constructor binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — DataBinder API: setAllowedFields, getSuppressedFields, declarativeBinding](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — @RequestBody JSON](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Core Constructor Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP API Security — Broken Object Property Level Authorization (BOPLA)](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
