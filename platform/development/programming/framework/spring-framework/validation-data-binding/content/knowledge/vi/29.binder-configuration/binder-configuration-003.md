# @ControllerAdvice và cấu hình binder dùng chung trong Spring MVC

## 1. Vấn đề: nhiều controller cùng cần một chính sách data binding

Trong Spring MVC, mỗi khi framework chuyển các tham số từ HTTP request thành một **model attribute**, cơ chế `WebDataBinder` có thể tham gia vào việc khởi tạo object, chuyển đổi kiểu, ghi nhận lỗi binding và gọi validator. Một ứng dụng có nhiều controller thường gặp các yêu cầu dùng chung:

- Hạn chế cách request được phép ghi dữ liệu vào object.
- Áp dụng chính sách an toàn đối với **property binding** để giảm nguy cơ mass assignment.
- Đăng ký formatter, converter hoặc validator theo một quy ước chung.
- Cho phép từng controller đưa ra ngoại lệ có kiểm soát cho form đặc thù.
- Không phải chép cùng một `@InitBinder` vào hàng chục controller.

Spring hỗ trợ khai báo phương thức `@InitBinder` trong **`@ControllerAdvice`** để tạo chính sách binder cho nhiều controller. Đây là chức năng dành cho **khởi tạo/cấu hình binder**, khác với `@ExceptionHandler` vốn xử lý exception và `@ModelAttribute` cấp method vốn có thể chuẩn bị dữ liệu model.

Ví dụ định hướng:

```java
@ControllerAdvice
public class SharedBindingPolicy {

    @InitBinder
    void initialize(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Ý tưởng: bật **constructor binding** theo mặc định, còn **property binding** không chạy nếu không có `allowedFields` được cấu hình. Một controller xử lý form mutable có thể bổ sung:

```java
@InitBinder("profile")
void profileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "city");
}
```

Hai đoạn trên chỉ là các trích đoạn minh họa; phần thực hành sau cung cấp mã nguồn đầy đủ, build Gradle, Spring Boot và test qua `MockMvc`.

**Phiên bản tham chiếu:** Java 17+, Spring Boot 3.3.x, Spring Framework 6.1–6.2, Servlet Spring MVC. `setDeclarativeBinding(true)` được bổ sung từ Spring Framework 6.1, vì thế không sao chép nguyên đoạn mã vào Spring Framework 5.x. Những lời khuyên về security là nguyên tắc chung, còn API cụ thể phải kiểm tra theo version.

## 2. Các thành phần và ranh giới trách nhiệm

### 2.1. WebDataBinder là gì?

`org.springframework.web.bind.WebDataBinder` là binder dành cho môi trường web. Nó kế thừa các khả năng từ `DataBinder` để:

- Gắn request parameters/giá trị web vào model object.
- Chuyển từ chuỗi sang kiểu Java như `Integer`, `LocalDate`, enum hoặc kiểu custom nhờ `ConversionService`, `PropertyEditor`, `Formatter`.
- Chọn hoặc giới hạn writable properties.
- Ghi nhận lỗi kiểu dữ liệu vào `BindingResult`.
- Kích hoạt các validator đã được cấu hình khi Spring yêu cầu validation.

Một object được bind không có nghĩa chắc chắn được validate: `@Valid`/`@Validated` tại boundary và validator phù hợp vẫn là những phần riêng. Cũng không có nghĩa dữ liệu được phép về mặt phân quyền hay business domain.

### 2.2. @InitBinder là hook cấu hình

`@InitBinder` đánh dấu một **method khởi tạo binder**, thường nhận tham số `WebDataBinder` và trả `void`. Annotation có thể đặt:

- Trong `@Controller` hoặc `@RestController`: tác động **cục bộ** đến controller đó.
- Trong `@ControllerAdvice`: có thể tác động đến nhiều controller, theo phạm vi được chọn.
- Trong `@RestControllerAdvice`: cũng hỗ trợ `@InitBinder` vì annotation này kết hợp `@ControllerAdvice` với `@ResponseBody`; phần `@ResponseBody` chủ yếu liên quan đến các exception handler trả body.

Ví dụ controller local:

```java
@RestController
class ChangeEmailController {

    @InitBinder("changeEmail")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("newEmail");
    }
}
```

Đây là class minh họa chưa có endpoint. Tên `"changeEmail"` là **tên model attribute**, không phải tên request mapping, không phải tên class Java và cũng không phải một validation group.

### 2.3. @ControllerAdvice là cơ chế chia sẻ

`@ControllerAdvice` là một stereotype component được Spring phát hiện thông qua component scanning hoặc khai báo bean. Nó có thể chứa:

| Annotation trong advice | Chức năng |
| --- | --- |
| `@InitBinder` | Cấu hình binder cho các controller thuộc phạm vi áp dụng |
| `@ModelAttribute` trên method | Chuẩn bị model attributes dùng chung |
| `@ExceptionHandler` | Xử lý exception của handler/controller theo phạm vi advice |

Việc đặt `@ControllerAdvice` trên class **không tự động biến nó thành validator**. Các phương thức bên trong vẫn phải được đánh dấu và khai báo đúng mục đích. Một class advice chỉ có `@InitBinder` không bắt buộc phải có `@ExceptionHandler`.

### 2.4. Phân biệt ba cơ chế “global” thường bị nhầm

| Nơi cấu hình | Phạm vi / thời điểm | Dùng khi |
| --- | --- | --- |
| `@InitBinder` trong controller | Binder của controller đó hoặc tên attribute được chỉ định | Form/endpoint cần chính sách riêng |
| `@InitBinder` trong `@ControllerAdvice` | Binder của các controller được advice áp dụng | Chính sách binder dùng chung theo nhóm controller |
| `WebMvcConfigurer#addFormatters` | `FormattingConversionService` dùng chung của MVC | Converter/formatter thực sự dùng rộng toàn ứng dụng |
| `WebBindingInitializer`/`ConfigurableWebBindingInitializer` | Khởi tạo binder ở tầng hạ tầng MVC | Cần điểm mở rộng thấp hơn, cấu hình framework chuyên sâu |
| `@ExceptionHandler` / `ResponseEntityExceptionHandler` | Sau khi exception xảy ra | Chuẩn hóa error response, không giới hạn field được bind |
| `Validator` / Jakarta Validation provider | Khi thực thi ràng buộc | Kiểm tra giá trị hợp lệ, không thay chính sách writable properties |

Chọn công cụ phù hợp với ranh giới: **conversion**, **binding policy**, **validation** và **exception response** là các bước có thể liên kết nhưng không phải cùng một thao tác.

## 3. Vòng đời: global @InitBinder trước local @InitBinder

Với Spring MVC annotated controller, cơ chế có thể hình dung:

```text
HTTP request
      |
      v
DispatcherServlet xác định handler
      |
      v
Argument resolver cần bind model attribute
      |
      v
Tạo WebDataBinder cho object/attribute
      |
      +--> @InitBinder từ @ControllerAdvice phù hợp
      |      - declarative binding
      |      - formatter/validator dùng chung
      |
      +--> @InitBinder cục bộ trong controller
      |      - cấu hình riêng theo attribute name
      |      - allowedFields cho form mutable
      |
      v
Constructor binding / property binding (theo policy)
      |
      v
Chuyển kiểu -> BindingResult (nếu có lỗi)
      |
      v
@Valid/@Validated khi được yêu cầu
      |
      v
Controller nhận object và BindingResult
```

**Thứ tự quan trọng:** Theo tài liệu Spring MVC, các method `@InitBinder` ở `@ControllerAdvice` được áp dụng **trước** `@InitBinder` cục bộ của controller. Ngược lại, thứ tự tìm kiếm `@ExceptionHandler` là local trước global. Vì vậy không được suy từ một loại method trong advice sang loại khác.

Điều này cho phép cấu hình chính sách nền trước, sau đó một controller **bổ sung** cấu hình riêng. Tuy nhiên, nếu global và local gọi những setter cấu hình **cùng một thuộc tính binder**, cấu hình sau có thể thay cấu hình trước theo semantics của setter. Không coi advice là một security firewall bất biến mà local controller không thể thay đổi.

Ví dụ hợp lý:

```java
// Global:
binder.setDeclarativeBinding(true);

// Local:
binder.setAllowedFields("displayName", "city");
```

Kết quả mong muốn: các controller đều không mở property binding bừa bãi; controller xử lý `profile` cho phép property binding **chỉ hai trường đã khai báo**. Ngược lại, một local binder gọi `setDeclarativeBinding(false)` có thể vô hiệu hóa chính sách chung — đó phải là quyết định được review/test nghiêm ngặt.

### 3.1. Cấu hình không “bind request” ngay khi @InitBinder chạy

`@InitBinder` có nhiệm vụ **thiết lập** cách binder hoạt động, không tự gọi business service hoặc tự gán toàn bộ request. Binder sẽ được sử dụng bởi argument resolver trong bước tiếp theo. Cũng không có cơ sở để giả định mọi HTTP request đều luôn tạo cùng số lượng binder: số binder và đối tượng mục tiêu phụ thuộc signature, attribute và đường validation của framework.

### 3.2. @InitBinder("name") có tác dụng giới hạn gì?

`@InitBinder("profile")` chỉ định tên attribute mà customizer muốn áp dụng. Nếu controller khai báo:

```java
@ModelAttribute("profile") ProfileForm form
```

thì hai tên khớp nhau. Nếu đổi thành `@ModelAttribute("userProfile")` nhưng quên đổi tên trong `@InitBinder`, allowlist có thể không được đăng ký cho attribute mới.

Hãy dùng tên tường minh trên cả hai annotation khi có chính sách bảo mật cụ thể. Đừng dựa vào tên suy diễn từ convention, nhất là khi đổi kiểu DTO hoặc refactor tham số.

## 4. Khi nào nên dùng @ControllerAdvice toàn cục?

### 4.1. Mặc định là toàn bộ controllers

```java
@ControllerAdvice
public class GlobalBinderAdvice {
    @InitBinder
    void customize(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Khi class được Spring scan, advice này có thể tác động tới các `@Controller` và `@RestController` trên ứng dụng MVC mà không cần tham chiếu trực tiếp từ từng controller.

Lợi ích:

- Chính sách nhập liệu mặc định được áp dụng thống nhất.
- Ít code trùng lặp.
- Các controller mới được hưởng chính sách nền, giảm khả năng vô tình quên cấu hình.
- Có thể bảo vệ việc mở property binding bằng cách yêu cầu whitelist cục bộ.

Mặt trái: việc thêm một cấu hình “global” có thể làm thay đổi hành vi các form hiện hữu. Các form mutable đang dựa vào setter binding không có allowlist có thể không còn được bind sau khi bật `declarativeBinding`.

### 4.2. Chỉ áp dụng cho một nhóm controller

`@ControllerAdvice` hỗ trợ các selector:

```java
@ControllerAdvice(basePackages = "com.example.app.web.forms")
public class FormsOnlyAdvice { /* ... */ }
```

```java
@ControllerAdvice(basePackageClasses = FormController.class)
public class PackageAdvice { /* ... */ }
```

```java
@ControllerAdvice(assignableTypes = FormController.class)
public class OneControllerAdvice { /* ... */ }
```

```java
@ControllerAdvice(annotations = RestController.class)
public class RestControllersAdvice { /* ... */ }
```

Đây là **bốn phương án minh họa độc lập**, không phải bốn class cần thêm cùng lúc vào dự án thực hành. `basePackageClasses` an toàn hơn tên package hard-coded khi refactor, nhưng nó chọn **package chứa type được cung cấp** chứ không chỉ duy nhất type đó. `assignableTypes` dùng khi mục tiêu là một controller class hoặc lớp/interface cha được chỉ định.

**Lưu ý rất dễ sai:** Nếu đặt nhiều loại selector trong cùng `@ControllerAdvice`, Spring áp dụng logic **OR**: controller khớp **bất kỳ** selector nào là đủ. Vì thế:

```java
@ControllerAdvice(
    basePackages = "com.example.app.web.forms",
    annotations = RestController.class
)
```

không có nghĩa “chỉ `@RestController` trong package forms”; nó có thể chọn cả controller thuộc package **hoặc** annotated `@RestController` ở package khác. Nếu cần logic AND phức tạp, đừng suy nó từ các selector; hãy tách policy phù hợp hoặc dùng marker annotation/controller hierarchy rõ ràng.

Các selector được kiểm tra lúc runtime. Tránh thêm quá nhiều selector phức tạp nếu không cần; chúng làm maintenance và mức độ dự đoán phạm vi áp dụng khó hơn.

### 4.3. @RestControllerAdvice có dùng để cấu hình binder được không?

Có:

```java
@RestControllerAdvice
public class RestBindingAdvice {

    @InitBinder
    void init(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

`@RestControllerAdvice` không có nghĩa chỉ áp dụng cho `@RestController` theo tên annotation; mặc định nó cũng có phạm vi chung như `@ControllerAdvice`. Từ “Rest” chủ yếu nói rằng exception-handler methods được xử lý theo `@ResponseBody` semantics. Nếu muốn chỉ nhắm `@RestController`, khai báo `annotations = RestController.class` cụ thể.

## 5. Bảo mật property binding: allowedFields là trọng tâm

### 5.1. Mass assignment / over-posting

Giả sử web application nhận một object có setters:

```java
public class Account {
    private String displayName;
    private boolean admin;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

Nếu Spring property binding có quyền gán mọi writable property, một client độc hại có thể gửi:

```text
displayName=Lan&admin=true
```

Dù UI chỉ hiển thị input `displayName`, request thực tế vẫn có thể chứa `admin`. Đó là **mass assignment**. `@Valid` không tự bảo vệ: nó kiểm tra constraint, không xác định thuộc tính nào client được phép điều khiển.

Phòng vệ ưu tiên:

1. DTO riêng cho endpoint, chỉ có những field client được phép gửi.
2. Constructor binding với danh sách tham số rõ ràng, thích hợp với immutable record.
3. Nếu cần mutable JavaBean/property binding, `setAllowedFields` với danh sách cụ thể, đủ hẹp.
4. Business authorization và mapping DTO → domain ở service trước khi lưu dữ liệu.
5. Regression tests cố tình gửi thêm field nhạy cảm.

### 5.2. setAllowedFields và setDisallowedFields

Cho phép đúng hai field:

```java
binder.setAllowedFields("displayName", "city");
```

Chặn theo blacklist:

```java
binder.setDisallowedFields("admin", "role");
```

Spring khuyến nghị **allowlist** vì explicit hơn và ít dễ quên khi schema phát triển. `allowedFields` patterns có matching **phân biệt chữ hoa/chữ thường**, trong khi `disallowedFields` được xử lý theo matching **không phân biệt chữ hoa/chữ thường**. Khi dùng wildcard, phải hiểu chính xác đường dẫn property được phép.

Ví dụ `"address.*"` có thể cho phép thêm nhiều field lồng nhau hơn dự định. Hãy dùng `"address.city"` và `"address.postalCode"` nếu chỉ cần hai field đó. Tránh `"*"` trong DTO có setter nhạy cảm.

**Không coi blacklist là giải pháp fallback an toàn** nếu không có policy rà soát schema; chỉ một setter mới như `setCanApprove` cũng có thể mở một đường gán không lường trước.

### 5.3. getSuppressedFields giúp quan sát input bị chặn

`BindingResult#getSuppressedFields()` trả những field names bị loại khỏi property binding do policy hạn chế. Ví dụ:

```java
String[] suppressed = bindingResult.getSuppressedFields();
```

Nếu request cố gửi `admin=true` nhưng `allowedFields` chỉ có `displayName` và `city`, `admin` có thể xuất hiện trong `suppressed`. Điều đó **không mặc định tạo Bean Validation violation**; một field bị bỏ qua có thể không làm `hasErrors()` trả true.

Nếu hệ thống muốn từ chối toàn bộ request khi có over-posting, cần thiết kế bước xử lý `suppressedFields` riêng, ví dụ trả HTTP 400 hoặc ghi security event theo chính sách. Không tự tin rằng `@NotBlank` sẽ phát hiện và từ chối một trường bị chặn.

### 5.4. Constructor binding và allowedFields không tương đương

Một record:

```java
public record AccountInput(
        String displayName,
        boolean admin
) {}
```

vẫn có thể được tạo qua constructor với `admin=true` từ request nếu model attribute constructor binding nhận tham số đó. `setAllowedFields("displayName")` áp dụng cho **property binding**, không phải “xóa” tham số `admin` ra khỏi constructor đã khai báo.

Vì vậy đầu tiên phải **thiết kế input DTO hợp lý**: không đưa trường quyền, trạng thái phê duyệt, ownerId nội bộ vào constructor của object mà client được phép điền. `setDeclarativeBinding` là hàng rào bổ sung, không hợp thức hóa một DTO chứa các trường nhạy cảm.

## 6. setDeclarativeBinding(true): chính sách nền an toàn

Theo Spring MVC 6.1+, `WebDataBinder` có thể được cấu hình:

```java
binder.setDeclarativeBinding(true);
```

Hiệu ứng:

- Constructor binding vẫn khả dụng.
- Property binding **chỉ thực hiện** nếu cấu hình `allowedFields`.
- Các controller nhận immutable DTO dễ được bảo vệ khỏi việc gán các writable properties ngoài ý muốn.
- Những form mutable cũ không có allowed fields có thể không còn được điền như trước.

Trong một ứng dụng lớn, cách tổ chức hữu ích:

```text
@ControllerAdvice
    |
    +--> global @InitBinder
           binder.setDeclarativeBinding(true)
                     |
                     v
          Constructor DTO (record) ------> Bind constructor arguments
                     |
                     +--> Mutable form
                              |
                              +--> Local @InitBinder("profile")
                                     setAllowedFields("displayName", "city")
                              |
                              v
                         Bind two setter properties only
```

Đây là mô hình **default-deny đối với property binding**, không phải chính sách bảo mật đầy đủ cho mọi dạng input. Với `@RequestBody` JSON, Jackson thực hiện deserialization qua `HttpMessageConverter`, nên `setAllowedFields` của `WebDataBinder` **không chặn các JSON properties** mà Jackson đọc. Xem phần 12 để tránh hiểu nhầm quan trọng này.

## 7. Dự án hoàn chỉnh: chính sách chung và ngoại lệ cục bộ

Chúng ta tạo một ứng dụng Spring Boot 3.3.x:

- `POST /forms/register` nhận một **record immutable** qua `@ModelAttribute`. Global advice bật declarative binding; record được tạo qua canonical constructor.
- `POST /forms/profile` nhận một **mutable JavaBean**. Local `@InitBinder("profile")` cho phép setter binding chỉ với `displayName` và `city`.
- `admin` có setter trong bean minh họa để chứng minh allowlist hoạt động: client thử gửi `admin=true` nhưng object vẫn có `admin=false`.
- `BindingResult` đặt ngay sau model attribute để controller chủ động trả HTTP 400 khi conversion/validation thất bại.
- `MockMvc` test hợp đồng chung, ngoại lệ cục bộ, trường bị chặn và Bean Validation.

> Lưu ý: việc đưa `admin` vào form DTO và phản hồi HTTP chỉ phục vụ bài thử bảo mật. Trong production, **không đưa trường quyền vào DTO input hoặc response demo**, không tin client để xác lập quyền.

### 7.1. Gradle và cấu trúc

Tệp `settings.gradle`:

```groovy
rootProject.name = 'shared-binder-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Thư mục:

```text
src/
  main/
    java/com/example/sharedbinder/
      SharedBinderApplication.java
      RegistrationForm.java
      ProfileForm.java
      SharedBindingAdvice.java
      FormsController.java
  test/
    java/com/example/sharedbinder/
      FormsControllerTest.java
```

`spring-boot-starter-web` chứa Spring MVC, `spring-boot-starter-validation` đưa provider Jakarta Bean Validation vào classpath. Dòng `-parameters` hỗ trợ tên tham số khi constructor binding cần reflection metadata. Java record có metadata riêng nhưng config này vẫn hữu ích cho class có data constructor.

### 7.2. Application

Tệp `src/main/java/com/example/sharedbinder/SharedBinderApplication.java`:

```java
package com.example.sharedbinder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SharedBinderApplication {

    public static void main(String[] args) {
        SpringApplication.run(SharedBinderApplication.class, args);
    }
}
```

### 7.3. RegistrationForm: record và constructor binding

Tệp `src/main/java/com/example/sharedbinder/RegistrationForm.java`:

```java
package com.example.sharedbinder;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationForm(
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {}
```

Record chỉ nhận `email` và `age`. Khi request gửi thêm `admin=true`, record không có constructor argument hoặc setter tương ứng. `@NotBlank`, `@Email`, `@NotNull`, `@Min` là ràng buộc Jakarta Validation; chúng chạy khi controller yêu cầu `@Valid` sau binding.

### 7.4. ProfileForm: mutable bean để minh họa property binding

Tệp `src/main/java/com/example/sharedbinder/ProfileForm.java`:

```java
package com.example.sharedbinder;

import jakarta.validation.constraints.NotBlank;

public class ProfileForm {

    @NotBlank
    private String displayName;

    @NotBlank
    private String city;

    // Chỉ có để mô phỏng nguy cơ mass assignment.
    private boolean admin;

    public ProfileForm() {}

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

Đây là kiểu JavaBean với no-arg constructor và public setters. Nếu không kiểm soát property binding, `admin=true` có thể đi vào `setAdmin`. Trong ví dụ global binder policy và local allowlist sẽ ngăn điều đó. Không dùng entity thật cho input form.

### 7.5. SharedBindingAdvice: nơi cấu hình dùng chung

Tệp `src/main/java/com/example/sharedbinder/SharedBindingAdvice.java`:

```java
package com.example.sharedbinder;

import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
public class SharedBindingAdvice {

    @InitBinder
    public void initialize(WebDataBinder binder) {
        // Từ Spring Framework 6.1:
        // Constructor binding được phép.
        // Property binding chỉ khi allowedFields đã được khai báo.
        binder.setDeclarativeBinding(true);
    }
}
```

Không cần gọi `initialize(...)` từ controller. Spring tìm `@ControllerAdvice` qua component scan và thực thi method khởi tạo cho các binder phù hợp. Class advice là Spring singleton mặc định, nhưng **WebDataBinder của từng request/attribute được tạo riêng**; method không nên lưu request-specific binder vào field mutable của singleton.

### 7.6. FormsController: local @InitBinder chỉ cho profile

Tệp `src/main/java/com/example/sharedbinder/FormsController.java`:

```java
package com.example.sharedbinder;

import jakarta.validation.Valid;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpStatus;
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
@RequestMapping("/forms")
public class FormsController {

    // Được chạy sau @InitBinder global cho attribute tên "profile".
    @InitBinder("profile")
    void configureProfile(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "city");
    }

    @PostMapping(
        path = "/register",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> register(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("email", form.email());
        body.put("age", form.age());

        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    @PostMapping(
        path = "/profile",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> profile(
            @Valid @ModelAttribute("profile") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("displayName", form.getDisplayName());
        body.put("city", form.getCity());

        // Chỉ để demo rằng request admin=true đã bị chặn.
        body.put("admin", form.isAdmin());

        // Chỉ để demo số field bị binder loại khỏi setter binding.
        body.put("suppressedCount", errors.getSuppressedFields().length);

        return ResponseEntity.ok(body);
    }

    private ResponseEntity<Map<String, Object>> invalid(
            BindingResult errors) {

        List<Map<String, String>> fields =
                errors.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", Objects.toString(
                                    error.getCode(), "invalid")))
                    .sorted(Comparator.comparing(
                            field -> field.get("field")))
                    .toList();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", "INVALID_FORM");
        body.put("fields", fields);

        return ResponseEntity.badRequest().body(body);
    }
}
```

Các chi tiết cần hiểu:

- Advice chung bật `setDeclarativeBinding(true)` cho binder.
- Với `"registration"`, không có allowed fields cục bộ. Record có canonical constructor, nên binder có thể tạo `RegistrationForm` qua **constructor binding**. Không cần public setters.
- Với `"profile"`, local binder chỉ khai báo writable properties `displayName` và `city`. Khi `allowedFields` đã được khai báo, declarative binding cho phép property binding trên các field đó.
- `@InitBinder("profile")` không có hiệu lực cho `"registration"` vì tên attribute khác.
- `@Valid` kích hoạt Jakarta Bean Validation. `BindingResult` ngay sau attribute chứa lỗi binding/validation nếu xảy ra.
- `admin` và `suppressedCount` chỉ xuất hiện trong response **của bài học** để quan sát chính sách. Một API production không nên công khai internal privileges/suppression detail.
- Không đặt `@Validated` cấp class vào controller chỉ để bind form; đó là khái niệm khác (method validation) và có thể thay đổi validation path trên Spring MVC 6.1+.

### 7.7. Thử bằng curl

Khởi chạy sau khi dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

**Form dùng record:**

```bash
curl -i -X POST "http://localhost:8080/forms/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=lan@example.org" \
  --data-urlencode "age=22" \
  --data-urlencode "admin=true"
```

HTTP dự kiến: **201 Created**. Body:

```json
{
  "email": "lan@example.org",
  "age": 22
}
```

Input có `admin` nhưng `RegistrationForm` không khai báo nó. Dù vậy, không nên dùng một DTO record có tham số `admin` và hy vọng cùng policy tự bỏ qua giá trị nhạy cảm.

**Form mutable với setter nhạy cảm:**

```bash
curl -i -X POST "http://localhost:8080/forms/profile" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "city=Hanoi" \
  --data-urlencode "admin=true"
```

HTTP dự kiến: **200 OK**. Body minh họa:

```json
{
  "displayName": "Lan",
  "city": "Hanoi",
  "admin": false,
  "suppressedCount": 1
}
```

Local allowed fields chỉ có `displayName` và `city`; binder không gọi `setAdmin(true)` từ property input. `getSuppressedFields()` cho thấy một field đã bị chặn trong ví dụ. **Điểm cần nhớ:** field bị chặn có thể bị bỏ qua mà không tự tạo lỗi validation; endpoint demo vẫn trả 200. Nếu policy yêu cầu từ chối over-posting, phải thêm xử lý riêng.

**Bean Validation thất bại:**

```bash
curl -i -X POST "http://localhost:8080/forms/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=invalid" \
  --data-urlencode "age=22"
```

Kết quả dự kiến: **400 Bad Request**, response chứa `code = INVALID_FORM` và một `field = email` với code `Email`.

**Chuyển đổi số thất bại:**

```bash
curl -i -X POST "http://localhost:8080/forms/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=lan@example.org" \
  --data-urlencode "age=abc"
```

Trong cấu hình binder/record thông thường, yêu cầu này tạo binding error cho `age` và HTTP 400 theo controller xử lý `BindingResult`. Đây là lỗi chuyển kiểu, **không phải** kết quả của `@Min(18)`.

## 8. Integration tests: xác minh global và local cùng có hiệu lực

Tệp `src/test/java/com/example/sharedbinder/FormsControllerTest.java`:

```java
package com.example.sharedbinder;

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
class FormsControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void immutableRecordUsesConstructorBinding() throws Exception {
        mvc.perform(post("/forms/register")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.org")
                .param("age", "22")
                .param("admin", "true"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.email").value("lan@example.org"))
            .andExpect(jsonPath("$.age").value(22))
            .andExpect(jsonPath("$.admin").doesNotExist());
    }

    @Test
    void mutableFormAllowsOnlyNamedProperties() throws Exception {
        mvc.perform(post("/forms/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("city", "Hanoi")
                .param("admin", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.city").value("Hanoi"))
            .andExpect(jsonPath("$.admin").value(false))
            .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void beanValidationStillRunsAfterBinding() throws Exception {
        mvc.perform(post("/forms/register")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "invalid")
                .param("age", "22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_FORM"))
            .andExpect(jsonPath("$.fields[0].field").value("email"))
            .andExpect(jsonPath("$.fields[0].code").value("Email"));
    }

    @Test
    void invalidProfileFieldProducesValidationError()
            throws Exception {
        mvc.perform(post("/forms/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", " ")
                .param("city", "Hanoi"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_FORM"))
            .andExpect(jsonPath("$.fields[0].field")
                    .value("displayName"));
    }

    @Test
    void validProfileWithoutExtraFieldStillWorks()
            throws Exception {
        mvc.perform(post("/forms/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Mai")
                .param("city", "Hue"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.suppressedCount").value(0))
            .andExpect(jsonPath("$.admin").value(false));
    }
}
```

Chạy:

```bash
./gradlew test
```

**Kỳ vọng:** năm test PASS khi môi trường dùng đúng cấu hình Spring Boot 3.3.x, Java 17 và dependencies nêu ở trên. Những bài test này xác minh behavior **qua DispatcherServlet/MockMvc**, không chỉ tự tạo `new ProfileForm()` rồi gọi setter.

Ý nghĩa của từng nhóm test:

1. Record nhận giá trị qua constructor, không có property `admin` để trả ra.
2. Shared declarative binding không cấm toàn bộ form mutable khi controller có allowlist.
3. `@Valid` vẫn chạy và trả field errors sau binding.
4. Property input blank bị `@NotBlank` bắt ngay cả khi nằm trong allowed fields.
5. Không có field dư thì không có suppressed property nào.

Không nên assert thứ tự error list khi có nhiều lỗi. Trong demo `beanValidationStillRunsAfterBinding` và `invalidProfileFieldProducesValidationError` chỉ cố ý tạo một field lỗi, nên `fields[0]` là đủ. Nếu form có nhiều lỗi hoặc locale thay đổi, hãy tìm field/code thay vì dựa vào vị trí hay message text.

### 8.1. Thêm test cho chính policy, không chỉ status

Một test **đủ tốt** không chỉ khẳng định HTTP 200 cho form hợp lệ. Cần cố gửi tên property nhạy cảm và xác nhận:

- Object không nhận giá trị `admin=true`.
- Các trường nằm trong `allowedFields` vẫn bind đúng.
- `BindingResult#getSuppressedFields()` phản ánh field bị ngăn khi phù hợp.
- Nếu app chọn chính sách từ chối over-posting, status phải là 400 và side effects không xảy ra.

Ngược lại, nếu chỉ test input hợp lệ và bỏ qua negative test, một thay đổi như xóa `@InitBinder("profile")` có thể lọt qua review mà không được phát hiện rõ.

## 9. Shared binder policy có thể tùy chỉnh những gì?

### 9.1. Formatter hoặc PropertyEditor

`@InitBinder` cho phép đăng ký formatter cục bộ hay trong advice. Ví dụ minh họa:

```java
@ControllerAdvice
public class DateBindingAdvice {

    @InitBinder
    void customize(WebDataBinder binder) {
        binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
    }
}
```

Đây là **một phương án thay thế độc lập**, không phải class cần copy thêm vào bài demo nếu không có nhu cầu xử lý date. `DateFormatter` ở package `org.springframework.format.datetime.DateFormatter`. Nó hỗ trợ parse/format `java.util.Date` theo pattern; với `java.time.LocalDate` có thể dùng `@DateTimeFormat`/`DateTimeFormatterRegistrar` hoặc formatter phù hợp trong ConversionService.

Nếu toàn ứng dụng dùng cùng quy ước `LocalDate`, đăng ký formatter qua `WebMvcConfigurer#addFormatters(FormatterRegistry)` hoặc một `FormattingConversionService` dùng chung thường rõ ràng hơn so với thêm nhiều advice không cần thiết. Nếu chỉ một form có quy tắc riêng, local `@InitBinder` hợp lý hơn.

Đối với `PropertyEditor`, tránh dùng instance mutable dùng chung giữa các request. `PropertyEditor` thường **không thread-safe**; tạo instance phù hợp cho mỗi binder. Advice bean có thể là singleton, không nên lưu formatter/editor phụ thuộc request vào mutable field.

### 9.2. Thêm Spring Validator chuyên biệt

Một custom validator của Spring sử dụng:

```java
org.springframework.validation.Validator
```

Nó khác `jakarta.validation.Validator` về interface và cách trả lỗi. Validator của Spring có `supports(Class<?>)` và `validate(Object, Errors)`.

Ví dụ mẫu:

```java
public class ProfileFormValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;
        if ("root".equalsIgnoreCase(form.getDisplayName())) {
            errors.rejectValue("displayName", "reservedName");
        }
    }
}
```

Đây là class minh họa; trong project thực tế cần import `org.springframework.validation.Errors` và type `ProfileForm`. Khi đăng ký:

```java
@InitBinder("profile")
void init(WebDataBinder binder) {
    binder.addValidators(new ProfileFormValidator());
}
```

Phải bảo đảm validator **hỗ trợ target type** trước khi thêm; nếu dùng global advice cho mọi form mà không kiểm tra `supports`, một validator chuyên biệt có thể không phù hợp với object khác. Ngoài ra, `addValidators` **bổ sung** validator còn `setValidator`/`setValidators` có thể thay đổi tập đã cấu hình; tránh vô tình thay validator Jakarta mặc định nếu còn cần `@NotBlank`, `@Min`.

Thực tế, nếu rule là constraint thuần dữ liệu, một Jakarta custom `@Constraint` và `ConstraintValidator` có thể tái sử dụng tốt hơn trong nhiều entrypoints. Nếu rule chỉ phục vụ form MVC và phụ thuộc `Errors`/field paths của Spring, Spring Validator có thể phù hợp.

### 9.3. Giới hạn nested/collection binding

`WebDataBinder`/`DataBinder` có các cấu hình như `setAutoGrowNestedPaths(...)` và `setAutoGrowCollectionLimit(...)` liên quan việc tự mở rộng cấu trúc khi bind indexed properties. Ví dụ:

```java
binder.setAutoGrowCollectionLimit(64);
```

Đây là đoạn minh họa của `@InitBinder`, không phải policy hoàn chỉnh chống denial-of-service. Khi cho phép request field `items[1000000].name` hoặc object graph sâu, cần giới hạn collection/size request, validate số phần tử và tránh allowlist wildcard quá rộng.

### 9.4. Điều gì không thuộc @InitBinder?

`@InitBinder` không phải:

- Một bộ lọc authentication/authorization.
- Một cơ chế chặn tất cả JSON properties trước khi Jackson deserialize.
- Một handler cho mọi exception của server.
- Một transaction interceptor.
- Một global validation pipeline chạy với mọi object do code Java tạo thủ công.
- Một điểm cấu hình dữ liệu dùng chung an toàn nếu chứa mutable per-request state trong advice singleton.

Nó là **hook cấu hình binder cho các entrypoints và controller phù hợp**, không phải giải pháp thay thế cho input DTO, service authorization hoặc database invariants.

## 10. @ControllerAdvice và @ExceptionHandler: phối hợp nhưng khác nhiệm vụ

Rất nhiều dự án có một `@RestControllerAdvice` dành cho lỗi API. Có thể giữ chung hoặc tách class cấu hình binder, tùy độ lớn ứng dụng:

```java
@RestControllerAdvice
public class ApiAdvice {

    @InitBinder
    void bind(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> invalid(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "VALIDATION_ERROR"));
    }
}
```

Đây là class minh họa, không thuộc dự án runnable ở mục 7; cần import các annotation, kiểu HTTP và `MethodArgumentNotValidException`. Các method thực hiện **hai việc khác nhau**:

- `@InitBinder` chạy khi khởi tạo binder, **trước binding/validation**.
- `@ExceptionHandler` chạy khi exception phù hợp đã xảy ra, để tạo response.

Trong bài demo, controller có `BindingResult` ngay sau `@ModelAttribute` nên nó **tự xử lý lỗi** và trả 400. Vì vậy một global exception handler cho `MethodArgumentNotValidException` có thể không nhận lỗi của các endpoint ấy; đây không phải chứng cứ advice không hoạt động.

Nếu bỏ `BindingResult`, trong đường MVC argument validation phổ biến, Spring có thể ném `MethodArgumentNotValidException`. Khi handler method có direct method constraints và MVC 6.1+ method validation, exception có thể là `HandlerMethodValidationException`. Đừng nhầm hai exception với lỗi cấu hình binder.

**Thứ tự áp dụng đáng nhớ:**

- Global `@InitBinder` **trước** local `@InitBinder`.
- Local `@ExceptionHandler` **trước** global `@ExceptionHandler` khi cùng phù hợp, theo quy tắc Spring exception resolution.
- Các `@ControllerAdvice` khác nhau có thể được sắp theo `@Order`/`Ordered`; nếu nhiều advice cùng sửa một binder field, cần kiểm thử rõ cấu hình cuối cùng. Đừng dùng thứ tự mơ hồ để tạo policy bảo mật.

## 11. Sự khác biệt với @RequestBody JSON và multipart

### 11.1. @ModelAttribute sử dụng binder để gán properties

Đối với:

```java
@PostMapping("/profile")
public void profile(@ModelAttribute ProfileForm form) { }
```

Spring MVC đọc request parameters/form fields, tạo model object, chạy constructor/property binding và có thể validate sau đó. `setAllowedFields` tác động tới **property binding** trong quá trình này.

### 11.2. @RequestBody JSON thường do Jackson xử lý

Đối với:

```java
@PostMapping("/profile-json")
public void profileJson(@RequestBody ProfileForm form) { }
```

Spring dùng `HttpMessageConverter`, thường là Jackson, để deserialize JSON. Jackson có cơ chế constructor/setter/property riêng. `WebDataBinder` có thể được tạo để phục vụ validation/error handling của argument, nhưng `setAllowedFields` không tự hoạt động như **JSON property allowlist** đối với Jackson.

Vì thế nếu endpoint JSON nhận:

```json
{
  "displayName": "Lan",
  "admin": true
}
```

mà DTO JSON vẫn có writable `admin`, không được coi global `@InitBinder#setAllowedFields` là biện pháp ngăn Jackson điền `admin`. Dùng **JSON input DTO chuyên biệt**, cấu hình Jackson phù hợp, mapping sang domain và authorization server-side.

### 11.3. @RequestPart metadata JSON

`@RequestPart("metadata") SomeDto dto` trong multipart thường đi qua message converter đối với part JSON, giống `@RequestBody` ở khía cạnh deserialize, chứ không biến `setAllowedFields` thành filter JSON. Ngược lại, các form fields thông thường trong multipart có thể tham gia binding qua `@ModelAttribute` theo controller signature.

Tóm lại:

| Đầu vào | Cơ chế chính | Có nên dựa vào allowedFields để ngăn field dư? |
| --- | --- | --- |
| Form/query `@ModelAttribute` mutable bean | WebDataBinder property binding | **Có**, nhưng vẫn ưu tiên DTO riêng |
| Form/query `@ModelAttribute` record | Constructor binding | Không thay danh sách constructor inputs |
| JSON `@RequestBody` | HttpMessageConverter/Jackson | **Không**, dùng JSON DTO/mapper |
| JSON part `@RequestPart` | Converter cho part | **Không** như JSON body |
| File upload `MultipartFile` | Multipart resolver | Cần kiểm tra file size/type/name/content riêng |

Đây là một trong những ranh giới bảo mật quan trọng nhất khi cấu hình binder dùng chung.

## 12. WebFlux có @ControllerAdvice và @InitBinder không?

Có, Spring WebFlux annotated controllers cũng có `@ControllerAdvice` và `@InitBinder`, nhưng runtime là **reactive stack** và các loại binder/argument resolution có khác biệt. Không sao chép toàn bộ code Servlet MVC rồi mặc định mọi formatter, converter, exception và thread behavior sẽ giống nhau.

- Trong MVC, `DispatcherServlet` và `WebDataBinder` phục vụ binding tại Servlet stack.
- Trong WebFlux, `DispatcherHandler`, codecs và cơ chế binding phản ứng xử lý request; `WebExchangeBindException` là lỗi command-object binding/validation điển hình, khác `MethodArgumentNotValidException` ở MVC.
- Một WebFlux functional route (`RouterFunction`) không tự dùng annotated controller `@InitBinder` như `@ModelAttribute` argument của controller.
- `@ControllerAdvice` có thể cấu hình binder/exception handling cho WebFlux annotated controllers, nhưng test nên dùng `WebTestClient`, không copy `MockMvc` nếu app không chạy Servlet.

Bài học tập trung vào Spring MVC vì ví dụ runnable dùng `spring-boot-starter-web`. Khi dự án triển khai WebFlux, hãy tham khảo tài liệu WebFlux cụ thể và điều chỉnh dependency/các test cho phù hợp.

## 13. Cách rollout global binder policy trong hệ thống đã chạy

Đặt `setDeclarativeBinding(true)` toàn bộ controller là thay đổi có **tác động hành vi**, dù chỉ vài dòng Java. Kế hoạch triển khai an toàn:

1. **Lập danh sách entrypoints** dùng `@ModelAttribute`, form-urlencoded, multipart form fields hoặc model attributes đã chuẩn bị sẵn.
2. **Phân loại input**: record/immutable DTO, mutable form DTO, JPA entity bị bind trực tiếp, session/model object đã tồn tại.
3. **Tách khỏi entity** nếu DTO chứa trường nhạy cảm như role, owner, creditLimit, approved, internalStatus.
4. **Gắn allowlist cụ thể** tại controller có mutable form thực sự cần setter binding.
5. **Đặt global advice theo scope phù hợp** (toàn app hoặc package/annotation marker) thay vì bật vô điều kiện trên codebase chưa được test.
6. **Chạy regression tests** với input hợp lệ, thiếu trường, sai kiểu, field dư, nested field và multipart.
7. **Quan sát suppressed fields** ở nơi bảo mật, có thể ghi security event không chứa giá trị nhạy cảm.
8. **Kiểm tra JSON endpoints riêng** vì Jackson không dùng `allowedFields` như property binder.
9. **Rà soát global/local overrides** để tránh `setDeclarativeBinding(false)` hoặc `setAllowedFields("*")` vô ý mở lại binding.
10. **Deploy với khả năng rollback**, quan sát tỷ lệ HTTP 4xx mới tăng do form bị chặn và business errors phát sinh từ input thiếu dữ liệu.
11. **Viết contract tests** cho các trường dữ liệu cần được chấp nhận, không chỉ test trường bị chặn.
12. **Ghi rõ version baseline** vì Spring MVC 6.1+ có `declarativeBinding`; dự án cũ phải có chiến lược khác.

Đối với một API chỉ nhận JSON, trước tiên nên xử lý DTO/Jackson policies; việc thêm một global binder policy có thể không đạt mục tiêu như mong muốn.

## 14. Lỗi phổ biến và cách sửa

**Lỗi 1 — Nghĩ @ControllerAdvice chỉ để bắt exception.** Nó còn chia sẻ `@InitBinder` và `@ModelAttribute`. Một advice không có `@ExceptionHandler` vẫn có giá trị.

**Lỗi 2 — Nghĩ @RestControllerAdvice chỉ chạy cho @RestController.** Nó mặc định có phạm vi chung như `@ControllerAdvice`; muốn giới hạn thì dùng selector.

**Lỗi 3 — Nhầm thứ tự init binder với exception handler.** Global `@InitBinder` trước local; ngược lại local `@ExceptionHandler` có ưu tiên với exception phù hợp.

**Lỗi 4 — Cho rằng global policy tự động không thể bị local override.** Các lời gọi setter lên cùng binder có thể tác động tới cấu hình cuối cùng; xem review và tests như một phần của security.

**Lỗi 5 — Bật declarativeBinding nhưng không chuẩn bị mutable forms.** Nếu không có allowlist, setter binding sẽ không chạy. Đây là hành vi có chủ đích nhưng có thể khiến form hiện có mất dữ liệu.

**Lỗi 6 — Dùng setAllowedFields để chặn constructor argument nhạy cảm.** Allowlist property binding không xóa constructor parameter khỏi DTO. Hãy bỏ field đó khỏi input contract.

**Lỗi 7 — Dùng blacklist và tin rằng sẽ luôn an toàn.** Setter mới có thể bị bỏ sót; allowlist cụ thể là mặc định tốt hơn.

**Lỗi 8 — Dùng @InitBinder("ProfileForm") khi @ModelAttribute("profile") được đặt ở method.** Tên phải khớp model attribute, không phải tên class.

**Lỗi 9 — Tin @InitBinder áp vào mọi JSON field.** Jackson xử lý `@RequestBody`/JSON parts; WebDataBinder allowedFields không phải Jackson allowlist.

**Lỗi 10 — Chỉ test HTTP status 200.** Cần test giá trị field được bind, field bị chặn, sai kiểu, constraint error, nested properties và side effects.

**Lỗi 11 — Nghĩ suppressed field tự động thành 400.** Spring có thể bỏ qua input bị cấm và vẫn xử lý request; nếu cần từ chối thì có policy riêng.

**Lỗi 12 — Đăng ký custom validator toàn cục cho một type duy nhất.** Kiểm tra `supports(Class<?>)` và target type; tránh phá các binder cho model khác.

**Lỗi 13 — Đặt PropertyEditor mutable vào static/singleton dùng chung.** Cẩn trọng thread safety; tạo editor riêng cho binder hoặc dùng formatter/converter phù hợp.

**Lỗi 14 — Trộn Spring MVC với WebFlux.** MVC dùng Servlet; WebFlux có handler/error APIs riêng và nên test bằng `WebTestClient`.

**Lỗi 15 — Dùng @Valid để giải quyết over-posting.** Validation đánh giá constraint sau binding; không quyết định field nào client được phép kiểm soát.

**Lỗi 16 — Dùng nhiều selectors và tưởng là AND.** `@ControllerAdvice` selectors kết hợp bằng **OR**, dễ mở rộng scope ngoài dự tính.

**Lỗi 17 — Dùng @ControllerAdvice lưu trạng thái request vào instance field.** Advice thường là singleton; mutable request-specific state sẽ gây race/leak. Dùng đối tượng binder/method arguments tại từng request.

**Lỗi 18 — Bỏ qua dữ liệu đã tồn tại trong Model/Session.** `@ModelAttribute` có thể bind lên object có sẵn chứ không chỉ object mới; allowlist càng quan trọng để không vô ý thay đổi state server.

## 15. Checklist quyết định và thiết kế

| Câu hỏi | Cách làm phù hợp |
| --- | --- |
| Cần cùng policy cho nhiều controller? | `@ControllerAdvice` có `@InitBinder` |
| Chỉ một controller cần ngoại lệ? | Local `@InitBinder`, có thể giới hạn theo attribute name |
| Muốn constructor binding là mặc định? | `setDeclarativeBinding(true)` trên Spring 6.1+ |
| Mutable form thật sự cần setters? | `setAllowedFields("fieldA", "fieldB")` cụ thể |
| Muốn field bị chặn trở thành lỗi? | Đọc `getSuppressedFields()` và áp policy từ chối/log riêng |
| Muốn dùng cùng format date cho toàn app? | `WebMvcConfigurer#addFormatters` hoặc ConversionService chung |
| Muốn chỉ áp policy cho package controller? | `@ControllerAdvice(basePackageClasses=...)` |
| Muốn handler cho lỗi binding? | `BindingResult` cạnh attribute, hoặc `@ExceptionHandler` |
| Muốn an toàn cho JSON @RequestBody? | Input DTO/Jackson/authorization, không chỉ `allowedFields` |
| Muốn validation cho field hợp lệ? | `@Valid`/`@Validated` và Jakarta Validation provider |
| Muốn bảo vệ quyền admin/owner? | Domain/service authorization và DTO không chứa field đặc quyền |
| Muốn tránh ảnh hưởng form cũ khi rollout? | Scoped advice, allowlists, MockMvc regression tests |

### Checklist review code

- `@ControllerAdvice` có được Spring scan và có scope đúng không?
- Cấu hình global có áp dụng được cho cả `@Controller` và `@RestController` mong muốn không?
- Cấu hình cục bộ có đúng tên `@ModelAttribute` không?
- Global `@InitBinder` được gọi trước local như dự kiến không?
- Có controller nào vô tình gọi `setDeclarativeBinding(false)` hoặc wildcard allowed fields không?
- Input DTO có field nhạy cảm ở constructor hoặc writable properties không?
- Các field cần nhập liệu có đầy đủ trong local allowlist không?
- Có cần `@Valid` hoặc `@Validated(Group.class)` để chạy rule sau binding không?
- `BindingResult` có đặt ngay sau đúng argument không?
- Có test positive/negative cho mỗi dạng input và error response không?
- JSON endpoints có được đánh giá riêng khỏi `WebDataBinder` không?
- Code có lưu editor/binder mutable vào singleton advice state không?

**Kết luận:** `@ControllerAdvice` cho phép đưa `@InitBinder` thành **chính sách cấu hình binder dùng chung**, được thực thi trước các `@InitBinder` cục bộ. Một chiến lược hữu ích ở Spring MVC 6.1+ là bật `setDeclarativeBinding(true)` làm mặc định và cho phép setter binding ở những form thực sự cần bằng `setAllowedFields(...)` hẹp. Tuy nhiên, tính an toàn phải đến từ DTO đầu vào, kiểm soát quyền, test request thật và ranh giới rõ ràng giữa `@ModelAttribute` binding với Jackson `@RequestBody`. Không biến một cấu hình global thành giả định rằng mọi input đều đã được bảo vệ.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): phạm vi của advice, thứ tự global/local, selectors.
- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): cấu hình binder, formatters, allowedFields và declarative binding.
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): constructor/property binding, BindingResult và validation.
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html): DataBinder, property paths, conversions, restrictions.
- [Spring Framework 6.2 — Web MVC Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html): shared conversion/formatting hooks.
- [Spring Framework — ControllerAdvice Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html): selectors kết hợp OR, `Ordered` và phạm vi áp dụng.
