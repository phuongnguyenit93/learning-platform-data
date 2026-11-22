# Constructor binding và property binding trong controller của Spring MVC

## 1. Cùng một request, hai cách đưa dữ liệu vào đối tượng

Khi viết Spring MVC controller, chúng ta thường nhận dữ liệu biểu mẫu bằng `@ModelAttribute`:

```java
@PostMapping("/register")
public String register(@ModelAttribute RegistrationForm form) {
    // form đã được bind từ dữ liệu HTTP.
    return "ok";
}
```

“Binding” là quá trình chuyển các giá trị HTTP thường ở dạng chuỗi thành thuộc tính Java có kiểu dữ liệu phù hợp. Với một model object, Spring hỗ trợ hai cơ chế chính:

1. **Constructor binding:** lấy các giá trị đầu vào tương ứng với tham số constructor, chuyển kiểu rồi **tạo object qua constructor**. Rất phù hợp với Java record và immutable DTO.
2. **Property binding (setter binding):** lấy object đã có hoặc khởi tạo object rồi **ghi giá trị vào các JavaBeans property** thông qua setter (và các cơ chế truy cập property được cấu hình).

Ví dụ request:

```http
POST /registrations
Content-Type: application/x-www-form-urlencoded

username=lan&age=21
```

Có thể tạo record:

```java
public record RegistrationForm(String username, Integer age) {}
```

hoặc ghi vào bean có setter:

```java
public class RegistrationForm {
    private String username;
    private Integer age;

    public RegistrationForm() {}

    public void setUsername(String username) {
        this.username = username;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Hai kiểu trên đều có thể nhận `username=lan` và `age=21`, nhưng **cách được tạo và cập nhật, khả năng chống mass assignment, sự bất biến và cách xử lý dữ liệu dư** khác nhau.

**Phạm vi và phiên bản:** bài học tập trung vào Spring Framework 6.1–6.2, Spring MVC Servlet stack, Spring Boot 3.x và Java 17+. Spring MVC có những bổ sung theo từng phiên bản: `@BindParam` và `setDeclarativeBinding` có từ Spring Framework 6.1; hỗ trợ constructor binding cho collection/array dạng phần tử có chỉ số được nâng cao ở 6.2. Không nên áp nguyên mọi chi tiết này cho Spring 5 hoặc WebFlux mà không kiểm tra tài liệu đúng phiên bản.

## 2. Data binding nằm ở đâu trong pipeline Spring MVC?

Một luồng điển hình với `@ModelAttribute`:

```text
HTTP request
  |  query parameters, form fields, path variables
  v
DispatcherServlet
  |
  v
HandlerMethodArgumentResolver
  |  xác định tham số @ModelAttribute
  v
Model attribute / WebDataBinder
  |  1. lấy object đã có hoặc construct object mới
  |  2. chọn constructor parameters và/hoặc writable properties
  |  3. chuyển String sang Integer, LocalDate, Enum...
  |  4. ghi binding/type mismatch errors
  |  5. nếu có @Valid/@Validated, chạy Bean Validation
  v
Controller argument + BindingResult
  |  tự xử lý lỗi nếu khai báo BindingResult ngay sau attribute
  v
Controller method / response
```

**Không nhầm ba khái niệm:**

- **Binding:** `"21"` → `Integer.valueOf(21)` rồi đưa vào constructor/setter.
- **Validation:** `@Min(18)` kiểm tra giá trị đã chuyển được có đáp ứng quy tắc hay không.
- **Business checks:** kiểm tra tài khoản trùng, quyền truy cập, phiên giao dịch hoặc trạng thái cơ sở dữ liệu; những kiểm tra này không tự động được bảo đảm chỉ bằng binding/annotation.

Trong Spring MVC, `@ModelAttribute` được dùng với query parameters và form body. URI template variables cũng có thể được đưa vào nguồn binding theo quy tắc ưu tiên của Spring. Spring Framework 6.2 còn bổ sung binding từ HTTP headers; không nên mặc nhiên nhận định phiên bản 6.1 có đầy đủ hành vi header của 6.2. Request parameters có độ ưu tiên cao hơn path/header values trùng tên trong mô hình MVC hiện đại.

Một request JSON xử lý bởi `@RequestBody` đi qua **HttpMessageConverter/Jackson** để deserialize; mặc dù Jackson cũng có constructor/property semantics riêng, đó **không phải** `WebDataBinder` đang được mô tả ở đây.

## 3. Constructor binding: xác định dữ liệu ngay trong constructor

### 3.1. Khái niệm và ưu điểm

Constructor binding dùng tham số của một data constructor như “danh sách đầu vào được chấp nhận”:

```java
public record RegistrationForm(
        String username,
        Integer age
) {}
```

Với cặp giá trị `username=lan` và `age=21`, Spring MVC tìm tên tham số, chuyển kiểu và gọi constructor tương ứng:

```java
new RegistrationForm("lan", 21);
```

Các thuộc tính của record là final; không có setter để sửa `username` hoặc `age` sau khi tạo. Nếu request gửi thêm `role=ADMIN` mà record không khai báo `role`, bản thân record này không có chỗ để lưu trường đó.

Constructor binding **không đồng nghĩa “mọi request đều an toàn”**. Nếu constructor input DTO nhận một tham số nhạy cảm như `isAdmin`, nó vẫn có thể được bind từ request. An toàn đến từ **thiết kế tập input được phép**, không phải chỉ từ khóa `record`.

Ưu điểm thường thấy:

- Dữ liệu kỳ vọng được liệt kê rõ tại constructor.
- Object có thể immutable; dễ suy luận và test.
- Không cần public setter cho mọi thuộc tính.
- Tách DTO nhận input khỏi JPA entity/domain object, giảm nguy cơ cập nhật nhầm cột nội bộ.
- Các giá trị bắt buộc có thể được diễn đạt qua kiểu và validation; constructor tự kiểm tra bất biến khi thật sự cần.

### 3.2. Chọn constructor nào?

Spring `DataBinder` hỗ trợ object có một data constructor; khi lớp có nhiều constructor, hành vi lựa chọn phụ thuộc cấu trúc lớp. **Constructor mặc định không tham số, nếu hiện diện, thường là lựa chọn để construct object**, rồi property binding cập nhật giá trị nếu được phép.

Với Java record, canonical constructor thể hiện danh sách record component rất rõ. Với class immutable, nên có một constructor phù hợp và **tên tham số được giữ trong bytecode**. Với class thường, biên dịch bằng `-parameters` giúp Spring đọc tên constructor arguments. Nếu tên không có sẵn, Spring có thể không ánh xạ đúng `username`/`age`.

Ví dụ Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Không coi `-parameters` là một cách “bật validation”: nó chủ yếu cung cấp metadata tên tham số cho reflection/binding. Java record có metadata record components; vẫn nên giữ cấu hình build nhất quán cho DTO dạng class.

### 3.3. Đổi tên input bằng @BindParam

Kể từ Spring Framework 6.1, `@BindParam` cho phép tên request khác tên tham số constructor. Đoạn sau là **class minh họa**:

```java
import org.springframework.web.bind.annotation.BindParam;

public class CustomerInput {
    private final String firstName;

    public CustomerInput(
            @BindParam("first-name") String firstName) {
        this.firstName = firstName;
    }

    public String getFirstName() {
        return firstName;
    }
}
```

Đầu vào `first-name=Lan` có thể được ánh xạ vào tham số `firstName`. `@BindParam` thuộc **Spring**, không phải Jakarta Validation, không phải Jackson `@JsonProperty` và không phải `@RequestParam`. Nó cũng có thể xuất hiện ở field tương ứng constructor parameter; ngoài ra `DataBinder.NameResolver` hỗ trợ chiến lược ánh xạ tên riêng.

**Phân biệt:** `@JsonProperty("first_name")` thường điều khiển Jackson JSON serialization/deserialization, trong khi `@BindParam("first-name")` phục vụ constructor binding của Spring `@ModelAttribute`. Đừng giả định một annotation tự thay thế annotation còn lại.

### 3.4. Giá trị không chuyển đổi được

Nếu request truyền:

```text
username=lan&age=abc
```

`"abc"` không thể chuyển hợp lệ thành `Integer`. Spring đưa **type mismatch/conversion error** vào `BindingResult` hoặc kích hoạt đường xử lý exception khi controller không nhận lỗi trực tiếp. Nó không biến `abc` thành 0 để vượt kiểm tra một cách bí mật.

Ràng buộc `@Min(18)` được dùng **sau khi bind và chuyển kiểu** thành công. Một lỗi conversion không phải là lỗi `@Min`; frontend cần phân biệt “phải nhập số” với “số phải đủ lớn”.

## 4. Property binding: khởi tạo rồi gán qua property

### 4.1. JavaBeans property

Một object mutable thường có constructor rỗng và các setter:

```java
public class ProfileForm {
    private String displayName;
    private Integer age;

    public ProfileForm() {}

    public void setDisplayName(String value) {
        this.displayName = value;
    }

    public void setAge(Integer value) {
        this.age = value;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Integer getAge() {
        return age;
    }
}
```

Với request `displayName=Lan&age=23`, property binding gọi logic tương đương:

```java
ProfileForm input = new ProfileForm();
input.setDisplayName("Lan");
input.setAge(23);
```

Lợi ích:

- Phù hợp form mutable và các dự án JavaBeans truyền thống.
- Có thể áp dụng lên đối tượng **đã tồn tại** trong model hoặc session.
- Hỗ trợ cấu trúc nested, collection hoặc indexed path trong giới hạn dữ liệu và binder configuration.
- Dễ tích hợp form editing, khi object cần được cập nhật có chủ đích.

Hạn chế lớn: nếu object có thêm setter public cho trường nhạy cảm, một request có thể cố tình gửi tên property tương ứng.

### 4.2. Mass assignment: rủi ro khi bind “mọi setter”

Xét một entity chứa:

```java
public class Account {
    private String displayName;
    private boolean admin;

    public void setDisplayName(String name) {
        this.displayName = name;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

Nếu bind request trực tiếp vào `Account` và không giới hạn property nào được sửa, input:

```text
displayName=Lan&admin=true
```

có thể làm thuộc tính `admin` thay đổi ngoài ý muốn. Đây là **mass assignment/over-posting**, một vấn đề bảo mật, không phải lỗi Bean Validation. Việc đặt `@NotNull` hay `@Valid` **không tự ngăn** cập nhật thuộc tính nhạy cảm.

Thứ tự ưu tiên thường nên là:

1. **Dùng DTO chuyên biệt cho từng endpoint**, chỉ chứa dữ liệu client được phép cung cấp.
2. Ưu tiên **constructor binding + immutable input** khi phù hợp.
3. Nếu cần property binding, đặt **allowlist `allowedFields`** cụ thể.
4. Chuyển DTO sang domain/entity trong service, áp dụng authorization và business rules trước khi ghi cơ sở dữ liệu.

## 5. Hai cơ chế có thể cùng hoạt động trong một @ModelAttribute

Đây là điểm dễ bỏ sót: Spring MVC **mặc định có thể thực hiện cả constructor binding và property binding** trong quá trình tạo/điền model attribute.

Điều này có nghĩa:

- Khi cần object mới, Spring có thể construct object qua constructor hoặc constructor rỗng.
- Sau đó, nếu có writable properties và không bị giới hạn, binder vẫn có thể gán các property từ request.
- Trên một immutable record, các component không có setter nên property binding không cập nhật các component đó.
- Trên mutable bean, property binding có thể cập nhật nhiều trường hơn danh sách business thực sự muốn nhận.
- Nếu model attribute được lấy từ `Model`/`@SessionAttributes` hoặc được tạo sẵn bằng `@ModelAttribute` method, object có thể đã tồn tại; lúc này property binding lên object hiện có cần được xem xét kỹ.

Spring Framework 6.1 cung cấp:

```java
binder.setDeclarativeBinding(true);
```

Ở chế độ này, **constructor binding vẫn được thực hiện**, còn **property binding chỉ được thực hiện khi cấu hình `allowedFields`**. Đây là cách bảo vệ chung để việc bind dữ liệu theo cấu trúc đầu vào rõ ràng hơn.

Ví dụ:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Đoạn method trên là minh họa bên trong controller hoặc `@ControllerAdvice`, cần import `org.springframework.web.bind.WebDataBinder` và `org.springframework.web.bind.annotation.InitBinder`. Khi cấu hình toàn controller, cần chắc chắn các endpoint dùng mutable form không bị ngưng nhận property ngoài dự kiến; giải pháp là định nghĩa allowlist cụ thể hoặc chuyển sang DTO immutable.

**Chú ý cực kỳ quan trọng:** `setAllowedFields(...)` điều khiển **property binding**, không phải bộ lọc làm vô hiệu tham số của constructor. Nếu constructor input có `admin`, bật allowlist property chỉ gồm `displayName` vẫn không thể tự giả định sẽ chặn `admin` ở constructor binding. Hãy thiết kế constructor DTO không nhận dữ liệu nhạy cảm ngay từ đầu.

## 6. Bảng so sánh tổng quan

| Tiêu chí | Constructor binding | Property binding |
| --- | --- | --- |
| Điểm gán dữ liệu | Tham số constructor | JavaBeans setters/writable properties |
| Object mới | Tạo object với các giá trị đã chuyển kiểu | Có thể tạo object rỗng rồi cập nhật property |
| Kiểu phù hợp | Record, immutable DTO, class có data constructor | Mutable form/JavaBeans |
| Field được xét | Tên/tham số constructor | Property path có thể ghi |
| Extra field | Không có constructor param tương ứng thì không thành constructor argument | Có thể gán nếu property writable và không bị chặn |
| Đổi tên input | `@BindParam` | Tên JavaBeans property / custom binder config |
| Đối tượng sẵn trong model | Không phải đường “tạo mới” phổ biến | Có thể cập nhật object có sẵn |
| Cấu hình an toàn | Chỉ khai báo input được phép trong constructor; `declarativeBinding` | DTO chuyên biệt, `allowedFields`, tránh bind entity |
| Nested structures | Hỗ trợ qua constructor, với những cải tiến theo phiên bản | Qua nested/indexed property paths |
| Conversion errors | Ghi nhận trong `BindingResult` | Ghi nhận trong `BindingResult` |
| Jakarta Bean Validation | Kiểm tra sau binding với `@Valid`/`@Validated` | Tương tự |
| Tình huống tránh | Constructor chứa thuộc tính bảo mật không nên cho client cung cấp | Setter nhạy cảm không được giới hạn |

Cả hai hình thức đều dùng `WebDataBinder` để quản lý conversion, errors và có thể kích hoạt validation. Không nên suy ra rằng “cứ là `@ModelAttribute` thì chắc chắn property binding” hoặc “cứ có constructor thì Spring không động vào setter nữa”.

## 7. Ví dụ Spring Boot runnable: hai endpoint, hai kiểu input

Dự án nhỏ bên dưới có:

- `POST /binding/registrations`: record immutable và constructor binding.
- `POST /binding/profiles`: mutable bean và property binding với allowlist.
- Validation bằng Jakarta `@NotBlank`, `@NotNull` và `@Min`.
- `BindingResult` ngay sau `@ModelAttribute` để controller trả HTTP 400 có cấu trúc.
- Kiểm thử HTTP qua `MockMvc`, bao gồm thử gửi property `privileged=true` không được phép.

### 7.1. Dependency và cấu trúc thư mục

Tệp `settings.gradle`:

```groovy
rootProject.name = 'mvc-binding-demo'
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

`spring-boot-starter-web` cung cấp Spring MVC và Jackson; `spring-boot-starter-validation` cung cấp cơ chế Jakarta Bean Validation với provider được quản lý theo dependency của Spring Boot. Bài sử dụng Spring Boot 3.3.x (Spring Framework 6.1.x).

Cấu trúc:

```text
src/
  main/java/com/example/mvcbinding/
    MvcBindingApplication.java
    RegistrationForm.java
    ProfileForm.java
    BindingController.java
  test/java/com/example/mvcbinding/
    BindingControllerTest.java
```

### 7.2. Application

`src/main/java/com/example/mvcbinding/MvcBindingApplication.java`:

```java
package com.example.mvcbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcBindingApplication.class, args);
    }
}
```

### 7.3. Record cho constructor binding

`src/main/java/com/example/mvcbinding/RegistrationForm.java`:

```java
package com.example.mvcbinding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationForm(
        @NotBlank String username,
        @NotNull @Min(18) Integer age
) {}
```

Record có hai component, tương ứng với hai tham số của canonical constructor. Các annotation Jakarta được dùng để kiểm tra sau binding; không cần setter.

`@Min(18)` không tự cấm `null` theo contract Bean Validation. Vì vậy `@NotNull` được dùng song song trên `age`. Còn `@NotBlank` không chấp nhận chuỗi null, rỗng hay chỉ khoảng trắng.

### 7.4. JavaBean cho property binding

`src/main/java/com/example/mvcbinding/ProfileForm.java`:

```java
package com.example.mvcbinding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ProfileForm {

    @NotBlank
    private String displayName;

    @NotNull
    @Min(18)
    private Integer age;

    // Cố tình có setter nhạy cảm để thử allowlist.
    private boolean privileged;

    public ProfileForm() {}

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

    public boolean isPrivileged() {
        return privileged;
    }

    public void setPrivileged(boolean privileged) {
        this.privileged = privileged;
    }
}
```

Trong một hệ thống thật, nên **loại hẳn `privileged` khỏi input DTO** và không trả nó trong response. Ví dụ cố ý đặt setter này để chứng minh `allowedFields` chặn một request field mà JavaBeans property binding có thể gán nếu không được giới hạn.

### 7.5. Controller: cấu hình binder theo tên attribute

`src/main/java/com/example/mvcbinding/BindingController.java`:

```java
package com.example.mvcbinding;

import jakarta.validation.Valid;
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
@RequestMapping("/binding")
public class BindingController {

    @InitBinder("registration")
    void registrationBinder(WebDataBinder binder) {
        // Bật constructor binding; không cho property binding
        // nếu không khai báo allowedFields.
        binder.setDeclarativeBinding(true);
    }

    @InitBinder("profile")
    void profileBinder(WebDataBinder binder) {
        // Mutable bean: chỉ cho phép hai property này.
        binder.setAllowedFields("displayName", "age");
    }

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> register(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("username", form.username());
        response.put("age", form.age());

        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping(
        path = "/profiles",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> updateProfile(
            @Valid @ModelAttribute("profile") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("displayName", form.getDisplayName());
        response.put("age", form.getAge());
        response.put("privileged", form.isPrivileged());

        return ResponseEntity.ok(response);
    }

    private ResponseEntity<Map<String, Object>> invalid(
            BindingResult result) {

        List<Map<String, String>> fields = result.getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "code", Objects.toString(
                                error.getCode(), "invalid")
                ))
                .toList();

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("errors", fields);
        return ResponseEntity.badRequest().body(response);
    }
}
```

Điểm quan trọng trong controller:

- `@ModelAttribute("registration")` làm rõ tên model attribute để `@InitBinder("registration")` áp dụng đúng đối tượng.
- `setDeclarativeBinding(true)` chỉ áp dụng cho registration; record của ta có constructor nhận chính xác `username` và `age`.
- `@ModelAttribute("profile")` đi với `@InitBinder("profile")`, cho phép property binding **chỉ** với `displayName` và `age`.
- `BindingResult errors` đứng **ngay sau tham số** `@Valid @ModelAttribute`. Nếu có binding/validation error, controller có thể xử lý thay vì để exception đi theo cơ chế mặc định.
- Response demo chứa `privileged` để có thể quan sát khóa an toàn hoạt động. Trong API production, không nên trả internal privilege field chỉ để debug; quyền thực tế còn phải được service kiểm tra.
- Map lỗi trả `field` và `code` để test không phụ thuộc ngôn ngữ của default message. Trong API production có thể chuẩn hóa mã lỗi riêng ổn định hơn `FieldError#getCode()`.

### 7.6. Gửi form request

Khởi chạy:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

**Constructor binding thành công:**

```bash
curl -i -X POST "http://localhost:8080/binding/registrations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=lan" \
  --data-urlencode "age=21"
```

Kỳ vọng HTTP `201 Created`, JSON body (trình tự keys không phải hợp đồng API):

```json
{
  "username": "lan",
  "age": 21
}
```

**Property binding với request cố gắng gán quyền:**

```bash
curl -i -X POST "http://localhost:8080/binding/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "age=23" \
  --data-urlencode "privileged=true"
```

Kỳ vọng HTTP `200 OK` và JSON:

```json
{
  "displayName": "Lan",
  "age": 23,
  "privileged": false
}
```

`privileged=true` có trong request nhưng không thuộc `allowedFields`, nên setter `setPrivileged(true)` không được gọi qua property binding. Trong ví dụ, giá trị boolean giữ mặc định `false`.

**Conversion error:** gửi `age=abc`:

```bash
curl -i -X POST "http://localhost:8080/binding/registrations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=lan" \
  --data-urlencode "age=abc"
```

Kỳ vọng HTTP `400 Bad Request` với lỗi liên quan field `age`; `code` có thể là `typeMismatch` hoặc một mã lỗi được binder/exception adapter xác định. Không ép test dựa vào message quốc tế hóa cụ thể trong trường hợp này.

## 8. Integration tests: xác minh constructor, setter và allowlist

`src/test/java/com/example/mvcbinding/BindingControllerTest.java`:

```java
package com.example.mvcbinding;

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
class BindingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void recordIsConstructedFromRequestParameters() throws Exception {
        mvc.perform(post("/binding/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "lan")
                .param("age", "21")
                .param("privileged", "true"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.username").value("lan"))
            .andExpect(jsonPath("$.age").value(21))
            .andExpect(jsonPath("$.privileged").doesNotExist());
    }

    @Test
    void recordValidationDetectsUnderage() throws Exception {
        mvc.perform(post("/binding/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "lan")
                .param("age", "16"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("age"));
    }

    @Test
    void propertyBindingAllowsOnlyExplicitFields() throws Exception {
        mvc.perform(post("/binding/profiles")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("age", "23")
                .param("privileged", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(23))
            .andExpect(jsonPath("$.privileged").value(false));
    }

    @Test
    void invalidNumberProducesBindingError() throws Exception {
        mvc.perform(post("/binding/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "lan")
                .param("age", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors").isArray());
    }
}
```

Chạy test:

```bash
./gradlew test
```

Các test bao phủ khác biệt chính: record không có thành phần `privileged`, bean mutable vẫn có setter nhạy cảm nhưng đã được allowlist bảo vệ, `@Min(18)` được chạy sau binding và lỗi chuyển kiểu sinh phản hồi `400`.

**Giới hạn của việc assert:** mẫu chỉ có một constraint không hợp lệ trong test `age=16` nên kiểm tra `errors[0]` hợp lý. Trong dự án nhiều lỗi, `BindingResult#getFieldErrors()` hoặc tập vi phạm từ provider có thể không có thứ tự ổn định; nên tìm lỗi theo field/code thay vì giả định vị trí đầu tiên.

### 8.1. Test trường bị chặn sâu hơn qua BindingResult

Spring `BindingResult` có `getSuppressedFields()`, giúp quan sát các tên field bị chặn do `allowedFields`/`disallowedFields`. Trong integration test có thể dùng một logger/test hook riêng hoặc unit test trực tiếp `DataBinder`; **không đưa danh sách tên thuộc tính nội bộ vào response production** chỉ để chứng minh field bị chặn.

Ví dụ ý tưởng về API (đoạn minh họa bên trong một handler có `BindingResult result`):

```java
String[] suppressed = result.getSuppressedFields();
```

Với input có `privileged=true` và allowlist chỉ gồm `displayName`, `age`, tên `privileged` có thể xuất hiện trong danh sách suppressed. Việc bị chặn **không tự tạo Bean Validation error** như `@NotBlank`; nếu muốn coi một attempt over-posting là security event, xử lý/log ở tầng phù hợp.

## 9. @InitBinder và WebDataBinder: giới hạn phạm vi đúng cách

### 9.1. Binder của controller

`@InitBinder` nhận `WebDataBinder` và cho phép cấu hình chuyển kiểu, field allowlist, declarative binding, formatter, validators theo request:

```java
@InitBinder("profile")
void initProfile(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "age");
}
```

Đây là một method minh họa trong controller; `"profile"` phải khớp tên model attribute cần bind. Nếu model attribute có tên khác, cấu hình scope có thể không chạy như dự định.

Không đưa tên property không tin cậy từ request làm allowlist động. Danh sách allowed fields nên được xác định theo contract của endpoint.

### 9.2. Binder dùng chung cho các controller

Một cấu hình có thể dùng `@ControllerAdvice`:

```java
@ControllerAdvice
public class GlobalBindingPolicy {

    @InitBinder
    public void restrictBinding(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Đây là đoạn **cấu hình thay thế**, không thêm nguyên xi vào dự án demo nếu chưa kiểm tra ảnh hưởng lên `ProfileForm`. Khi bật declarative binding toàn ứng dụng, các form truyền thống dựa hoàn toàn vào setter mà không có `allowedFields` có thể không còn bind được như trước.

Mục tiêu của `setDeclarativeBinding(true)` không phải là “tắt mọi binding”, mà là **chỉ constructor binding mặc định**, với property binding chỉ khi đã tuyên bố `allowedFields`. Nếu cần các endpoint mutable, áp dụng allowlist tường minh và viết test regression.

### 9.3. Allowed fields và disallowed fields

Spring hỗ trợ:

```java
binder.setAllowedFields("displayName", "age");
```

và:

```java
binder.setDisallowedFields("admin", "role");
```

Nhưng **allowlist được ưu tiên** vì rõ ràng hơn: thêm setter mới `approved` hoặc `creditLimit` vào domain object sẽ không tự được cho phép. Blacklist cần theo dõi mọi trường nhạy cảm, dễ bỏ sót trong các lần mở rộng schema.

Allowlist còn có thể mô tả property path như `address.city`, `items[0].sku` hoặc wildcard khi thật sự cần. Cẩn thận wildcard quá rộng, đặc biệt ở nested object vì có thể cho phép các đường dẫn chưa lường trước.

### 9.4. @ModelAttribute(binding=false)

Nếu controller nhận một object đã được thêm vào Model, đôi khi chỉ muốn đọc object đó mà **không áp request parameters lên nó**:

```java
@GetMapping("/preview")
public String preview(
        @ModelAttribute(binding = false) Account account) {
    // Dùng model attribute đã được chuẩn bị từ nguồn tin cậy.
    return "preview";
}
```

Đây là method controller minh họa, không phải toàn bộ flow lấy object. `binding = false` ngăn data binding cho model attribute tương ứng; cần chắc chắn object đã được tạo/cấp cho controller theo logic phù hợp. Nó không thay thế authorization khi lấy entity từ database.

## 10. Nested object, collection và property path

### 10.1. Property binding theo đường dẫn

Với bean chứa `Address address` có setter/getter, form có thể dùng tên:

```text
address.city=Hanoi
address.zipCode=100000
```

Spring có thể đi theo property path và tạo/gán object lồng nhau theo cấu hình binder, converter và khả năng auto-grow của object graph. Với collection có thể xuất hiện:

```text
items[0].sku=SKU-1
items[1].sku=SKU-2
```

Đây là cách đặt tên property path phổ biến; để code chạy thật còn cần các class, constructor, setters và collection declarations tương ứng. Không khẳng định mọi cấu trúc nested/list được tạo thành công với mọi DTO.

**Bảo mật:** allowlist phải xét cả đường dẫn lồng nhau. Chặn `admin` ở top-level nhưng cho phép wildcard quá rộng ở `account.*` có thể để lộ setter nhạy cảm trong child object. Giới hạn kích thước collection/auto-grow và số lượng phần tử theo chính sách ứng dụng để tránh request cực lớn tiêu hao tài nguyên.

### 10.2. Constructor binding cho nested và collection

Constructor binding hỗ trợ đối tượng nested thông qua constructor của các type con. Spring Framework 6.2 mở rộng đáng kể hỗ trợ constructor binding cho `List`, `Map` và array theo indexed request keys, ví dụ `accounts[0].name`. Nếu đang dùng Spring Boot 3.3 (Spring 6.1) như demo, **không suy ra mọi tính năng 6.2 về collection constructor binding đã có**.

Đối với một endpoint cần danh sách lồng nhau phức tạp, hãy kiểm tra phiên bản Spring và viết test bằng request thực tế. Một số mô hình dữ liệu sẽ phù hợp hơn với JSON body qua `@RequestBody`, miễn là cấu trúc API và chính sách bảo mật cho phép.

## 11. Chuyển kiểu, validation và lỗi: ba tầng kiểm tra

| Đầu vào | Bước lỗi | Thực tế |
| --- | --- | --- |
| `age=21` với kiểu `Integer` | Không | Chuỗi đổi thành số 21 |
| `age=abc` với kiểu `Integer` | Binding/conversion | `typeMismatch` hoặc binding error |
| `age=16` với `@Min(18)` | Bean Validation | Giá trị đã convert nhưng dưới ngưỡng |
| `username=` với `@NotBlank` | Bean Validation | Chuỗi rỗng không hợp lệ |
| `privileged=true` bị `allowedFields` chặn | Property binding policy | Field bị suppressed, không phải vi phạm `@NotBlank` |
| Input cho property không tồn tại | Binding policy | Tùy binder `ignoreUnknownFields` và xử lý riêng |
| Input gán biến chỉ dùng nội bộ vào constructor DTO | Thiết kế DTO sai | Allowlist setter không giải quyết được |

### 11.1. Đăng ký Formatter/Converter

Nếu request chứa `birthday=2026-01-02` và DTO có `LocalDate`, Spring cần một formatter/converter phù hợp. Ví dụ annotation:

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate birthday;
```

Đây là snippet trong bean, cần import `java.time.LocalDate` và `org.springframework.format.annotation.DateTimeFormat`; nó không phải ứng dụng hoàn chỉnh. Với constructor parameter, cũng có thể cần khai báo/đăng ký conversion metadata phù hợp ở vị trí mà Spring đọc được. Không tự parse date string trong setter nếu có thể dùng `FormattingConversionService` được cấu hình thống nhất.

`@InitBinder` còn có thể đăng ký `PropertyEditor` hoặc `Formatter`, nhưng formatter/converter chung thường tốt hơn nếu nhiều endpoint dùng cùng kiểu. Khi conversion thất bại, lỗi là binding error, không phải mặc nhiên là validation constraint error.

### 11.2. BindingResult phải đứng ngay sau đúng attribute

Đúng:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "success";
}
```

Sai hoặc dễ gây hiểu nhầm:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm form,
        @RequestParam String source,
        BindingResult errors) {
    return "success";
}
```

Đây là hai snippet method controller, không phải chương trình độc lập. `BindingResult` phải đi **ngay sau** tham số model attribute tương ứng; chèn tham số khác ở giữa sẽ khiến Spring không xác định được một kết quả binding hợp lệ cho attribute đó.

Nếu không khai báo `BindingResult`, Spring MVC có thể ném `MethodArgumentNotValidException` khi validation riêng của `@ModelAttribute` thất bại; khi endpoint còn có direct method constraints, Spring MVC 6.1+ có đường method validation khác và có thể dùng `HandlerMethodValidationException`. Không đánh đồng mọi binding/conversion error với duy nhất một exception trong mọi cấu hình.

### 11.3. @Valid không tự kích hoạt từ constructor

Constructor binding chỉ tạo một object. `@NotBlank`, `@Min` không tự chạy chỉ vì constructor được gọi bằng reflection. Trong annotated controller, `@Valid` hoặc `@Validated` (với groups khi cần) yêu cầu framework kiểm tra object sau binding.

Tương tự, `@Valid` không cấm request field `privileged=true` nếu property writable: đó là phạm vi của data binding policy. Đặt chính sách bảo mật input và business authorization **trước khi** tin tưởng dữ liệu đã bind thành công.

## 12. @RequestBody và @ModelAttribute: không trộn hai mô hình

Ví dụ hai endpoint:

```java
@PostMapping("/form")
public void form(@Valid @ModelAttribute RegistrationForm form) {
    // MVC DataBinder: request parameters, form/query.
}

@PostMapping("/json")
public void json(@Valid @RequestBody RegistrationForm form) {
    // HttpMessageConverter / Jackson: JSON body.
}
```

Đây là các snippet method trong controller, chưa phải một class hoàn chỉnh. Cả hai cùng tạo `RegistrationForm` và có thể kiểm tra bằng Bean Validation, nhưng **đường đọc dữ liệu khác**.

| Vấn đề | @ModelAttribute | @RequestBody |
| --- | --- | --- |
| Đầu vào phổ biến | Query string, HTML form-urlencoded, multipart form | JSON/XML và body media type converter hỗ trợ |
| Cơ chế chính | Spring MVC `WebDataBinder` | `HttpMessageConverter`, thường Jackson cho JSON |
| Constructor/property trong bài này | Spring `DataBinder` | Jackson có cơ chế tạo/gán object riêng |
| `@InitBinder#setAllowedFields` | Có ý nghĩa với property binding | Không phải giải pháp bảo vệ JSON Jackson |
| `@BindParam` | Tên cho constructor parameter Spring | Không thay cho `@JsonProperty` |
| Validation | `@Valid`/`@Validated` sau bind | `@Valid`/`@Validated` sau deserialize |
| Lỗi chuyển kiểu đầu vào | Binding error/`BindingResult` | Thường là `HttpMessageNotReadableException` cho JSON không parse được |

Nếu một API nhận JSON, bảo vệ input bằng DTO JSON chuyên biệt, annotation Jackson thích hợp và service authorization; đừng chỉ cấu hình `allowedFields` của `WebDataBinder` rồi nghĩ đã chặn mọi trường JSON.

## 13. Những lỗi hay gặp khi triển khai

**1. Nghĩ record luôn chỉ có constructor binding và không cần thiết kế input.** Nếu record khai báo `boolean admin`, client vẫn có thể gửi giá trị tương ứng để Spring construct. Không đưa trường nhạy cảm vào DTO.

**2. Dùng trực tiếp JPA entity làm `@ModelAttribute`.** Entity thường có nhiều setter cho trạng thái nội bộ. Nếu bắt buộc bind, dùng allowlist chặt hoặc chuyển qua DTO. Hãy kiểm soát ID, owner, role, status ở service.

**3. Tưởng `setAllowedFields` giới hạn cả constructor parameters.** Nó chủ yếu hạn chế property binding; constructor vẫn lấy các tham số được khai báo. Dùng DTO đầu vào chỉ bao gồm dữ liệu được phép nhận.

**4. Gắn `@Valid` và nghĩ mass assignment sẽ bị chặn.** Validation kiểm tra constraint trên object; nó không bảo vệ mọi writable property khỏi input không mong đợi.

**5. Không có tên constructor parameter trong bytecode.** Với class non-record, cần metadata tên tham số hoặc cơ chế `@BindParam` phù hợp; nếu không, binding có thể thất bại hay không ánh xạ như mong đợi.

**6. Thêm setter để sửa một lỗi constructor binding mà không suy xét bảo mật.** Việc thêm setter có thể mở ra property binding đối với tên request tương ứng. Trước tiên kiểm tra constructor và metadata names.

**7. Gọi type mismatch là lỗi `@Min`.** `age=abc` không phải số dưới ngưỡng. Phân biệt conversion error và Bean Validation violation để trả thông báo dễ hiểu.

**8. Đặt `BindingResult` không liền kề `@ModelAttribute`.** Spring yêu cầu nó ngay sau argument đang được validate khi muốn xử lý lỗi trực tiếp.

**9. Bật `setDeclarativeBinding(true)` toàn app nhưng không cập nhật endpoint form mutable.** Property binding sẽ không còn áp dụng trừ khi có allowlist; phải test regression.

**10. Dùng blacklist rồi quên thêm thuộc tính nhạy cảm mới.** Danh sách `disallowedFields` không mở rộng an toàn theo model; ưu tiên `allowedFields`.

**11. Đọc nhầm @ModelAttribute với @RequestBody.** Một bên là MVC DataBinder và request parameters; bên kia thường là Jackson deserialization của JSON.

**12. Áp tài liệu Spring 6.2 cho runtime Spring 6.1.** Tính năng thêm trong 6.2 (ví dụ hỗ trợ cấu trúc collection constructor phức tạp) không tự có trong Spring Boot 3.3. Luôn đối chiếu BOM/runtime dependency.

**13. Tin một field bị suppressed nghĩa là có HTTP 400 mặc định.** Binder có thể bỏ qua field không cho phép và tiếp tục xử lý. Nếu chính sách yêu cầu báo lỗi/lưu sự kiện bảo mật, phải viết xử lý rõ ràng.

**14. Dựa vào binding để bảo đảm bất biến database.** Các điều kiện phụ thuộc dữ liệu hiện tại, authorization và transaction phải được kiểm tra ở tầng service/domain, không dựa vào object creation.

## 14. Checklist thiết kế controller an toàn

1. Xác định endpoint thực sự nhận **form/query** (`@ModelAttribute`) hay **JSON** (`@RequestBody`).
2. Định nghĩa **input DTO chuyên biệt**, không bind trực tiếp domain/JPA entity.
3. Ưu tiên Java record/immutable constructor DTO khi input là tập giá trị cố định.
4. Nếu dùng constructor với class, cung cấp tên tham số runtime (`-parameters` hoặc `@BindParam`).
5. Nếu dùng mutable form, cấu hình `@InitBinder#setAllowedFields(...)` với danh sách property cụ thể.
6. Nếu muốn tắt setter binding mặc định, dùng `setDeclarativeBinding(true)` (Spring 6.1+) và rà soát các endpoint hiện hữu.
7. Không đưa role/admin/owner/internal status vào constructor DTO hay writable setter công khai của input.
8. Đăng ký converter/formatter có kiểm thử; phân biệt lỗi chuyển kiểu với lỗi validation.
9. Đặt `@Valid`/`@Validated` và `BindingResult` đúng vị trí để xử lý dữ liệu không hợp lệ.
10. Kiểm thử request hợp lệ, thiếu trường bắt buộc, sai kiểu, trường dư, field nhạy cảm và nested/collection nếu có.
11. Thử request thật qua `MockMvc`, không chỉ gọi trực tiếp constructor/JavaBean setter bằng unit test.
12. Ánh xạ DTO → domain trong service, tiếp tục kiểm tra quyền, consistency và business invariants tại nơi cập nhật.

### Kết luận

**Constructor binding** biểu đạt dữ liệu được chấp nhận ngay ở tham số constructor và phù hợp với immutable DTO. **Property binding** đi qua JavaBeans writable properties, linh hoạt nhưng cần allowlist để hạn chế over-posting. Trong Spring MVC, **cả hai có thể cùng được áp dụng cho `@ModelAttribute`**, trừ khi cấu hình kiểu declarative hoặc thiết kế object hạn chế setter. Hãy phân biệt dữ liệu HTTP, chuyển kiểu, validation và business authorization; một object được bind thành công chưa có nghĩa mọi giá trị của nó đều được phép sử dụng.

## Tài liệu tham khảo

- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): các kiểu binding, object design và bảo mật.
- [Spring Framework — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): cách MVC tạo model attribute, constructor/property binding và BindingResult.
- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html): `DataBinder`, conversion và property/constructor behavior.
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): `allowedFields` và `declarativeBinding`.
- [Spring Framework — @BindParam Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/annotation/BindParam.html): tên constructor parameter trong MVC.
