# Phối hợp constructor binding và property binding một cách có chủ đích trong Spring Framework

> **Chủ đề:** Spring Framework – Validation & Data Binding  
> **Nhóm kiến thức:** Gắn qua constructor  
> **Bối cảnh:** Spring Framework 6.1+/6.2, Spring MVC, Java 17 trở lên. Bài giải thích cách Spring có thể tạo đối tượng bằng constructor rồi tiếp tục gán những thuộc tính được cho phép, cách cấu hình ranh giới giữa hai pha và cách tránh ghi đè dữ liệu ngoài ý muốn.

## 1. Bài toán: một đối tượng có phần bất biến và phần có thể chỉnh sửa

Giả sử một form tạo hồ sơ gồm:

- `email`: phải được cung cấp khi tạo; không được tự ý thay đổi qua setter.
- `age`: nhận lúc tạo, chuyển từ chuỗi request sang số nguyên và kiểm tra giới hạn.
- `displayName`: thuộc tính được phép nhập hoặc thay đổi qua setter.
- `role`: thông tin nội bộ, client không được tự nâng quyền.

Có hai cơ chế binding khác nhau:

1. **Constructor binding**: Spring tra giá trị theo tên tham số constructor, chuyển kiểu rồi dùng các tham số để **tạo instance**.
2. **Property binding**: Spring tra giá trị theo tên JavaBeans property và dùng setter/field-access đã cấu hình để **gán vào instance hiện có**.

Spring MVC khi xử lý `@ModelAttribute` có thể dùng cả hai. Việc dùng cùng lúc chỉ an toàn khi bạn đã quyết định rõ **dữ liệu nào được nhận ở constructor**, **dữ liệu nào có thể được ghi tiếp**, và **điều gì xảy ra nếu client gửi các tên không mong đợi**.

**Mục tiêu thiết kế:** tham số constructor xác định những dữ liệu cần thiết để tạo một đối tượng hợp lệ; property binding chỉ bổ sung các field được phép thay đổi. Hãy kiểm soát rõ ràng cả hai tập tên đầu vào, nhất là khi request đến từ người dùng bên ngoài.

## 2. Hai cơ chế khác nhau ở điều gì?

| Tiêu chí | Constructor binding | Property binding |
| --- | --- | --- |
| Mục đích | Tạo đối tượng từ các tham số đầu vào | Cập nhật thuộc tính của đối tượng đã tồn tại |
| Đích nhận dữ liệu | Tham số của constructor được chọn | Property có setter hoặc cơ chế field access phù hợp |
| Khóa đầu vào | Tên tham số constructor, có thể ánh xạ bằng `@BindParam` | Tên property/path như `displayName` hoặc `address.city` |
| Kiểu đối tượng phù hợp | Record, immutable DTO, class có data constructor | JavaBean mutable, đối tượng có setter |
| Khả năng thay đổi sau tạo | Bản thân bước construct không yêu cầu setter | Có thể thay đổi trạng thái sau constructor |
| Giới hạn field | Hình dạng constructor định nghĩa danh sách tham số có thể đưa vào | Cần giới hạn bằng `allowedFields`/DTO hoặc tắt pha này |
| Lỗi | Chuyển kiểu/khởi tạo constructor, thể hiện qua binding result hoặc exception tùy tình huống | Lỗi chuyển kiểu, field path, setter... được binder thu thập hoặc báo |
| Rủi ro | Constructor có quá nhiều tham số nhạy cảm; chọn sai constructor; thiếu metadata tên | Mass assignment, ghi đè field, cập nhật nested path ngoài dự định |

**Constructor binding không đồng nghĩa Bean Validation**: constructor có thể tạo thành công một đối tượng với `age=0`; quy tắc `@Min(18)` vẫn phải được kích hoạt và kiểm tra sau binding. Tương tự, property binding có thể chuyển chuỗi thành số hợp lệ về kiểu mà chưa đúng chính sách nghiệp vụ.

## 3. Trình tự điển hình của `@ModelAttribute` trong Spring MVC

```text
HTTP request: email=linh@example.com&age=21&displayName=Linh&role=ADMIN
            |
            v
Spring tìm model attribute đã tồn tại?
      | Có                            | Chưa có
      v                                v
Dùng instance từ model/session      Tạo instance bằng default constructor
hoặc nguồn phù hợp                  hoặc primary/data constructor
      |                                | (constructor binding)
      +----------------+---------------+
                       |
                       v
         WebDataBinder và cấu hình @InitBinder
                       |
                       v
     Property binding lên target hiện có
       - Mặc định có thể áp dụng
       - Với declarativeBinding + allowedFields:
         chỉ những setter fields được cho phép
                       |
                       v
         Validation khi được kích hoạt
                       |
                       v
      BindingResult / Controller / Service
```

Sơ đồ là mô hình tư duy cho đường đi `@ModelAttribute`, không phải mọi request luôn gọi constructor: Spring MVC có thể lấy sẵn attribute từ model, session hoặc một nguồn/`Converter` thích hợp. Trong trường hợp đó, không có một lần constructor binding mới cho instance đã được chuẩn bị.

Với một attribute mới được tạo qua constructor, **constructor binding xảy ra trước việc gán các property của đối tượng đã tạo**. Spring MVC mặc định có thể tiếp tục property binding sau bước tạo, nên nếu cùng một dữ liệu có cả constructor parameter và setter, phải xem xét khả năng gán lặp hoặc ghi đè.

Lưu ý nguồn dữ liệu: `@ModelAttribute` trong Spring MVC có thể bind request parameters (bao gồm query và form data), cùng các nguồn bổ sung như URI variables/header theo quy tắc framework. **`@RequestBody` JSON đi qua HTTP message converter/Jackson**, có cơ chế deserialization riêng; không nên coi cấu hình `WebDataBinder.setDeclarativeBinding` là hàng rào mặc định cho mọi JSON field.

## 4. Điều kiện để Spring chọn constructor đúng

Với một class chỉ có một data constructor:

```java
public final class RegistrationForm {
    private final String email;
    private final int age;

    public RegistrationForm(String email, int age) {
        this.email = email;
        this.age = age;
    }

    public String getEmail() { return email; }
    public int getAge() { return age; }
}
```

Khi nhận request có các tham số `email` và `age`, Spring MVC có thể dùng tên tham số constructor để tra giá trị, convert `"21"` thành `int 21` rồi tạo instance. Để đọc được tên tham số runtime, nên biên dịch Java có tùy chọn `-parameters` (Spring Boot Maven parent thường cấu hình việc này; có thể đặt tường minh trong Maven compiler settings).

Những điều cần xác định:

- **Constructor được chọn:** với một data constructor duy nhất, ánh xạ khá rõ. Nếu class có nhiều constructor, hãy kiểm tra quy tắc chọn constructor của phiên bản Spring, đặc biệt khi có no-argument constructor; đừng giả định Spring sẽ luôn chọn constructor nhiều tham số nhất.
- **Tên tham số phải khớp nguồn:** `email`, `age` là những tên Spring tìm mặc định. Nếu cần tên request khác tên biến Java, có thể dùng `@BindParam`.
- **Type conversion:** chuỗi không chuyển được sang `int` làm phát sinh lỗi. Không nên dùng giá trị Java mặc định của primitive để che lỗi chuyển kiểu.
- **Nested constructor arguments:** Spring 6.1+ có thể dựng object lồng nhau theo property path từ dữ liệu được cung cấp, và hỗ trợ collection/map/indexed inputs theo những quy tắc riêng.
- **Record/immutable DTO:** dùng rất tốt với constructor binding; không cần setter. `record` có canonical constructor; không thể kỳ vọng property binding sửa final components sau đó.

Nếu constructor có tham số `role` do client kiểm soát, **bật `setAllowedFields` không chặn được riêng tham số constructor đó**: allowlist này bảo vệ *property binding*, còn constructor binding nhận theo chữ ký constructor. Hãy thiết kế constructor input không chứa trường đặc quyền, thay vì trông đợi allowlist setter bảo vệ constructor.

### Ánh xạ tên bằng `@BindParam`

Khi tên request là `first-name` nhưng tên tham số Java là `firstName`:

```java
import org.springframework.web.bind.annotation.BindParam;

public PersonForm(@BindParam("first-name") String firstName) {
    this.firstName = firstName;
}
```

Đây là **một constructor minh họa bên trong class `PersonForm`**, không phải source file Java độc lập. `@BindParam` có thể ánh xạ tên trong constructor binding ở MVC/WebFlux, và cũng có thể được đặt trên field tương ứng theo hỗ trợ của Spring. Nó không tự tạo setter hay cho phép property binding vào tên ngoài allowlist.

## 5. Property binding là bước kế tiếp, cần quyết định có cho phép hay không

Hãy phân biệt ba cấu hình:

| Cấu hình | Hành vi chủ đích |
| --- | --- |
| Mặc định, không giới hạn | Constructor binding có thể tạo object; sau đó property binding có thể gán mọi property khớp tên và writable. Với đối tượng chứa field nội bộ, đây là rủi ro. |
| `binder.setDeclarativeBinding(true)` và **không** thiết lập `allowedFields` | Chỉ dùng constructor binding khi tạo object; property binding được tắt theo chế độ declarative. |
| `binder.setDeclarativeBinding(true)` cùng `binder.setAllowedFields("displayName")` | Constructor binding vẫn chạy; property binding chỉ áp dụng cho những property patterns đã cho phép. |

`setDeclarativeBinding(true)` được hỗ trợ từ Spring Framework 6.1. Đây là cờ yêu cầu ràng buộc mang tính khai báo: constructor arguments vẫn được bind; setter/property chỉ được bind nếu `allowedFields` đã được cấu hình.

Trong Spring MVC:

```java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName");
}
```

Đoạn trên là một method trong controller hoặc advice, cần import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`. `"profileForm"` phải khớp tên model attribute tương ứng. Constructor có thể nhận `email`/`age`, còn setter phase chỉ nhận `displayName`.

Cần nhớ:

- `setAllowedFields(...)` áp dụng cho **property binding**, không phải cơ chế nhận tham số constructor.
- Các patterns có hỗ trợ wildcard; ưu tiên tên tường minh khi có thể. Pattern quá rộng có thể vô tình cho phép thêm field mới về sau.
- `setDisallowedFields(...)` là cách cấm theo danh sách nhưng dễ bỏ sót field mới; allowlist thường dễ kiểm soát hơn.
- Khi binder loại field khỏi property phase, `BindingResult.getSuppressedFields()` có thể cho biết các tên bị chặn. **Đừng mặc định mọi suppressed field đều là tấn công**: các tên đã được dùng hợp lệ ở constructor phase cũng có thể xuất hiện trong tập request mà property phase lọc ra.
- Bật declarative binding **không có nghĩa** tất cả field của DTO tự được xác minh theo quyền truy cập hoặc yêu cầu nghiệp vụ; bạn vẫn cần validation và kiểm tra quyền ở tầng phù hợp.

## 6. Thiết kế một hybrid form: immutable core + một phần mutable

Một mô hình phù hợp khi thật sự cần phối hợp hai bước:

```java
package demo.hybrid;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public final class ProfileForm {

    @NotBlank
    @Email
    private final String email;

    @Min(18)
    private final int age;

    @NotBlank
    private String displayName;

    // Có setter chỉ để minh họa nguy cơ mass assignment.
    // Trong thiết kế production nên bỏ role khỏi input DTO.
    private String role = "USER";

    public ProfileForm(String email, int age) {
        this.email = email;
        this.age = age;
    }

    public String getEmail() {
        return email;
    }

    public int getAge() {
        return age;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

Các ý định được thể hiện trong class:

1. `email` và `age` là dữ liệu tạo instance, **không có setter** và được khai báo `final`.
2. `displayName` có setter để nhận property binding sau khi instance được tạo.
3. `role` có setter nhưng **không nằm trong allowedFields**, cho thấy binder cần được cấu hình có chủ đích nếu class còn property khác.
4. `@NotBlank`, `@Email` và `@Min` là những điều kiện kiểm tra dữ liệu; chúng **không tự chạy chỉ vì constructor hoặc setter được gọi**. Trong controller dùng `@Valid` để kích hoạt Bean Validation.

Class này là ví dụ minh họa về ranh giới binding. Khi làm sản phẩm thực tế, nên thiết kế input DTO **không có field `role`** ngay từ đầu, lấy vai trò từ quyền và chính sách ở tầng ứng dụng/domain.

## 7. Ví dụ Spring Boot 3.5.7 chạy được bằng Java 17

Dưới đây là project web nhỏ cho thấy **một request dùng cả constructor và property binding theo allowedFields**. Phiên bản Spring Boot 3.5.7 dùng trong ví dụ đã được phát hành trên Maven Central; nó tương thích Java 17 và nhóm API của Spring Framework 6.2.x.

Cấu trúc:

```text
hybrid-binding-demo/
  pom.xml
  src/main/java/demo/hybrid/HybridBindingApplication.java
  src/main/java/demo/hybrid/ProfileForm.java
  src/main/java/demo/hybrid/ProfileController.java
  src/test/java/demo/hybrid/ProfileControllerTest.java
```

### 7.1. `pom.xml`

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
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>hybrid-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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

### 7.2. `HybridBindingApplication.java`

```java
package demo.hybrid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HybridBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(HybridBindingApplication.class, args);
    }
}
```

### 7.3. `ProfileForm.java`

Dùng nguyên nội dung `ProfileForm` từ phần 6, lưu tại đường dẫn file trên. `-parameters` trong cấu hình Maven giúp Spring nhận được tên `email`/`age` của constructor khi bind.

### 7.4. `ProfileController.java`

```java
package demo.hybrid;

import java.util.LinkedHashMap;
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
@RequestMapping("/profiles")
public class ProfileController {

    @InitBinder("profileForm")
    void initBinder(WebDataBinder binder) {
        // Constructor arguments vẫn được sử dụng để tạo ProfileForm.
        binder.setDeclarativeBinding(true);

        // Setter phase chỉ được phép gán displayName.
        binder.setAllowedFields("displayName");
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> create(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.<String, Object>of(
                            "error", "INVALID_FORM"));
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("email", form.getEmail());
        response.put("age", form.getAge());
        response.put("displayName", form.getDisplayName());
        response.put("role", form.getRole());
        return ResponseEntity.ok(response);
    }
}
```

Tại sao controller được viết như vậy?

- `@ModelAttribute("profileForm")` khai báo tên attribute mà Spring MVC xử lý; `@InitBinder("profileForm")` cấu hình đúng binder của attribute ấy.
- `ProfileForm` có một public constructor hai tham số và không có constructor rỗng; khi cần tạo instance mới, Spring dùng dữ liệu `email` và `age` cho constructor binding.
- Sau khi có instance, cấu hình `setAllowedFields("displayName")` chỉ cho setter phase nhận `displayName`. Một request cố gửi `role=ADMIN` **không được gán** qua property binding.
- `@Valid` kích hoạt validation; `BindingResult` phải nằm **ngay sau tham số model attribute** để xử lý lỗi của chính đối tượng đó.
- `BindingResult.hasErrors()` kiểm tra lỗi binding/validation; không thay việc kiểm tra quyền tạo hồ sơ trong một service thật.
- Endpoint chỉ trả dữ liệu minh họa, chưa truy cập DB. Trong ứng dụng thật, controller sẽ gọi service để kiểm tra nghiệp vụ và lưu một domain entity an toàn.

### 7.5. Gửi request và quan sát kết quả

Khởi động từ thư mục `hybrid-binding-demo`:

```bash
mvn spring-boot:run
```

Ở Windows, nếu có Maven Wrapper thì dùng `mvnw.cmd spring-boot:run`; nếu dùng lệnh trên, Maven phải có trong PATH.

Gửi form-encoded request:

```bash
curl -X POST "http://localhost:8080/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=linh@example.com" \
  --data-urlencode "age=21" \
  --data-urlencode "displayName=Linh"
```

Kết quả HTTP thành công về **giá trị** (thứ tự key JSON có thể thay đổi theo serializer):

```json
{
  "email": "linh@example.com",
  "age": 21,
  "displayName": "Linh",
  "role": "USER"
}
```

Gửi thêm trường không được phép gán qua setter:

```bash
curl -X POST "http://localhost:8080/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=linh@example.com" \
  --data-urlencode "age=21" \
  --data-urlencode "displayName=Linh" \
  --data-urlencode "role=ADMIN"
```

Với cấu hình ở trên, giá trị `role` của đối tượng vẫn là `"USER"`. Đây chỉ là chứng minh cơ chế field allowlist; trong API thật còn nên quyết định chính sách báo lỗi với key thừa, và không để DTO chứa quyền nếu không cần thiết.

Nếu gửi `age=abc`, giá trị không chuyển thành `int`; request cần được xem như lỗi binding, không tự đổi thành `0` hay tiếp tục tạo hồ sơ. Nếu gửi `displayName=`, `@NotBlank` sẽ báo lỗi khi validation chạy.

Đường đi trình diễn là **form data của `@ModelAttribute`**. Nếu đổi endpoint sang `@RequestBody` JSON, các chú thích về constructor/setter ở đây cần được xét lại theo Jackson; riêng `@InitBinder.setAllowedFields` không phải chính sách chặn JSON field của Jackson.

## 8. Kiểm thử cơ chế kết hợp bằng `MockMvc`

Lưu `src/test/java/demo/hybrid/ProfileControllerTest.java`:

```java
package demo.hybrid;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void combinesConstructorAndPropertyBinding() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "linh@example.com")
                    .param("age", "21")
                    .param("displayName", "Linh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email")
                        .value("linh@example.com"))
                .andExpect(jsonPath("$.age").value(21))
                .andExpect(jsonPath("$.displayName").value("Linh"))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void cannotChangeRoleViaPropertyBinding() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "linh@example.com")
                    .param("age", "21")
                    .param("displayName", "Linh")
                    .param("role", "ADMIN"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void rejectsBlankDisplayName() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "linh@example.com")
                    .param("age", "21")
                    .param("displayName", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("INVALID_FORM"));
    }
}
```

Chạy:

```bash
mvn test
```

Ba bài test có ý nghĩa khác nhau:

1. `email` và `age` đi qua constructor binding; `displayName` đi qua property binding.
2. `role` không nằm trong allowedFields, nên không thể bị sửa qua setter phase dù setter tồn tại.
3. Giá trị rỗng của `displayName` được gán rồi bị Bean Validation từ chối; đây là validation sau data binding, không phải điều kiện được constructor tự giải quyết.

**Lưu ý kiểm thử:** đoạn ví dụ cho một project Spring Boot đầy đủ về cấu trúc nhưng còn phụ thuộc vào runtime và các dependency được tải bằng Maven. Bài mô tả kết quả mong đợi theo API; trong dự án thực tế hãy chạy `mvn test` với phiên bản đang triển khai và xem báo cáo thực tế, nhất là khi có custom converter, `@ControllerAdvice` hoặc binder config toàn cục.

## 9. Chọn thứ tự và tránh xung đột giữa constructor field với setter field

Một trường vừa có trong constructor vừa có setter có thể khiến hai pha cùng nhận dữ liệu:

```java
public class AmbiguousForm {
    private String name;

    public AmbiguousForm(String name) {
        this.name = name;
    }

    public String getName() { return name; }

    public void setName(String name) {
        // Có thể khác logic chuẩn hóa ở constructor.
        this.name = name;
    }
}
```

Nếu tiếp tục property binding cho `name`, setter có thể được gọi sau khi constructor đã xử lý `name`. Kể cả giá trị đầu vào giống nhau, việc chạy logic hai lần có thể ảnh hưởng chuẩn hóa, side effects hoặc kiểm tra bất biến.

Thiết kế rõ hơn:

- **Dữ liệu tạo bản sắc/bất biến:** dùng constructor, `final` fields, không mở setter; ví dụ `email` ở thời điểm tạo DTO.
- **Dữ liệu được phép bổ sung/sửa:** dùng setter riêng với tên property được cho phép; ví dụ `displayName`.
- **Thuộc tính nội bộ:** không đưa vào constructor mà client điều khiển; không cho setter binding; tốt nhất không có trong input DTO.
- **Một nguồn chân lý cho validation:** kiểm tra trên trạng thái cuối cùng; nếu có rule trong constructor, rule đó cần đồng bộ với Bean Validation/business policy và không làm mất khả năng trả lỗi dễ hiểu.

Không nên viết constructor có side effects như ghi database, gửi email hoặc publish message. Binding có thể thất bại sau khi constructor đã chạy, khiến side effect xảy ra dù request bị từ chối. Giữ constructor thuần (thiết lập và bảo vệ bất biến nội bộ), còn hành động nghiệp vụ thực hiện ở service sau khi kiểm tra.

## 10. Tình huống không có constructor binding vì object đã tồn tại

Spring MVC có thể nhận model attribute từ:

- Model do `@ModelAttribute` method chuẩn bị.
- `@SessionAttributes` và session liên quan.
- Converter phù hợp với tham số/path variable.
- Một cơ chế tạo attribute khác được framework chọn.

Khi instance đã có sẵn, Spring có thể **không tạo mới qua data constructor**. Property binding trên instance đó (nếu được phép) có thể sửa dữ liệu đang tồn tại.

Ví dụ một controller lấy domain entity theo id rồi bind trực tiếp cả request là đặc biệt rủi ro: một property setter không được bảo vệ có thể thay giá trị ngoài ý muốn. Hãy tách **input form DTO** ra khỏi **domain entity**, validate DTO rồi gọi method nghiệp vụ kiểm soát để cập nhật entity.

Nếu chỉ muốn đưa một attribute vào handler **mà không bind request lên attribute đó**, có thể dùng `@ModelAttribute(binding = false)` theo contract MVC. Tùy use case, đây là lựa chọn phù hợp hơn là mở property binding cho một entity đã tải từ DB.

## 11. Phân biệt `@ModelAttribute` với `@RequestBody`

| Câu hỏi | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Đầu vào thông dụng | Query/form parameters, URI variables, header theo luật MVC | Nội dung HTTP body như JSON |
| Hệ thống chính | WebDataBinder, constructor/property binding | HttpMessageConverter, thường Jackson khi là JSON |
| Dùng `@InitBinder.setAllowedFields` cho setter? | Có ý nghĩa với property binding qua WebDataBinder | Không phải cơ chế giới hạn field khi Jackson deserialize JSON |
| Object bất biến | Data constructor/record có thể phù hợp | Jackson có thể dùng canonical constructor/creator theo cấu hình riêng |
| Validation | `@Valid`/`@Validated` khi kích hoạt | `@Valid`/`@Validated` khi kích hoạt |
| Vấn đề bảo mật | Bind field ngoài dự định nếu DTO/setter mở rộng | JSON có thể map vào field/setter/creator ngoài dự định theo Jackson config |

Hai con đường có thể cùng nhận DTO Java nhưng không dùng chính xác cùng một pipeline binding. Nếu ứng dụng có cả endpoint HTML form và JSON, hãy test mỗi endpoint riêng; không suy luận rằng một `@InitBinder` đã bảo vệ mọi đường đi dữ liệu.

## 12. Tương tác với `DataBinder` khi dùng thủ công

Ngoài Spring MVC, có thể dùng `DataBinder` ở mức chương trình để thấy ranh giới hai pha. Với Spring Framework 6.1+:

```java
import java.util.Map;
import java.util.Set;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

// ProfileForm có data constructor và setter như ví dụ trên.
Map<String, String> input = Map.of(
        "email", "linh@example.com",
        "age", "21",
        "displayName", "Linh",
        "role", "ADMIN");

DataBinder binder = new DataBinder(null, "profileForm");
binder.setTargetType(ResolvableType.forClass(ProfileForm.class));
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");

DataBinder.ValueResolver resolver = new DataBinder.ValueResolver() {
    @Override
    public Object resolveValue(String name, Class<?> type) {
        return input.get(name);
    }

    @Override
    public Set<String> getNames() {
        return input.keySet();
    }
};

// Pha 1: tạo object thông qua constructor.
binder.construct(resolver);

// Pha 2: chỉ bind các property cho phép lên object đã có.
if (binder.getTarget() != null) {
    binder.bind(new MutablePropertyValues(input));
}

BindingResult result = binder.getBindingResult();
// Kiểm tra result.hasErrors() và chỉ dùng target khi hợp lệ.
```

Đây là **đoạn minh họa API** dành cho một class/method đã có `ProfileForm`, không phải file Java độc lập có `main`. Khi triển khai, cần biên dịch với `-parameters` hoặc có cơ chế ánh xạ tên tham số phù hợp.

Ý nghĩa của các bước:

1. `new DataBinder(null, "profileForm")` bắt đầu khi chưa có target.
2. `setTargetType(ResolvableType.forClass(ProfileForm.class))` chỉ định kiểu cần dựng.
3. `construct(ValueResolver)` tra giá trị theo tham số constructor và thực hiện tạo đối tượng nếu thành công.
4. `bind(MutablePropertyValues)` đi vào property phase theo `allowedFields`.
5. `BindingResult` ghi nhận lỗi từ các bước thích hợp; `getTarget()` có thể vẫn chưa có instance nếu construction thất bại.

**Quan trọng:** gọi `construct` và `bind` không tự động kích hoạt Bean Validation nếu bạn chỉ dùng `DataBinder` thủ công mà chưa cấu hình/gọi validator. Trong Spring MVC, `@Valid` trên `@ModelAttribute` tham gia lifecycle validation do framework quản lý.

## 13. Xử lý lỗi và validation trong hai pha

Có ít nhất ba nguồn lỗi cần phân biệt:

1. **Constructor/type conversion:** tham số `age=abc` không chuyển được thành `int`; hoặc constructor từ chối dữ liệu. Kết quả phụ thuộc loại lỗi, cấu hình và phiên bản framework; không tự kết luận rằng đối tượng đã tạo thành công.
2. **Property binding:** setter `displayName` có thể nhận giá trị sai kiểu, hoặc nested path không hợp lệ; binder tạo field errors hoặc báo exception theo contract.
3. **Bean Validation và nghiệp vụ:** `@NotBlank`/`@Min` được kiểm tra trên đối tượng theo `@Valid`/validator; chính sách “được phép tạo hồ sơ” cần xử lý ở service/domain.

Trong MVC:

```java
@PostMapping("/sample")
public String example(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "profile-success";
}
```

Đây là snippet trong một MVC controller có view `profile-form`/`profile-success`; không phải method được thêm nguyên xi vào `ProfileController` REST ở phần 7.

`BindingResult` nên đứng **ngay sau** model attribute tương ứng. Không đặt một tham số không liên quan chen vào giữa rồi kỳ vọng BindingResult vẫn nhận đúng lỗi của attribute đó.

`BindingResult.getSuppressedFields()` có ích khi cần quan sát field bị bộ lọc property chặn. Nhưng khi constructor arguments vẫn xuất hiện trong tập request cho property phase, chúng cũng có thể bị suppressed bởi allowlist setter. Do đó muốn **từ chối mọi tham số không thuộc hợp đồng request**, cần kiểm tra danh sách key cho phép ở biên API với hiểu biết về cả **constructor keys** lẫn **setter keys**; không thể đơn giản coi mọi suppressed key đều độc hại.

Nếu không có `BindingResult` argument, Spring MVC thông thường dùng exception cho lỗi binding/validation (ví dụ `MethodArgumentNotValidException`); một số cấu hình method validation có loại exception khác. Hãy thiết kế `@ControllerAdvice` và test HTTP contract theo phiên bản Spring dùng trong dự án.

## 14. Giá trị thiếu, null, mặc định và conversion

| Input | Điểm cần xác định |
| --- | --- |
| Không gửi `email` | Constructor có thể nhận `null` cho tham số reference; validation `@NotBlank` sẽ từ chối nếu được kích hoạt và object được tạo thành công. |
| Không gửi `age` kiểu primitive | Giá trị mặc định primitive và constraint có thể ảnh hưởng; không coi `0` là bằng chứng client đã gửi `0`. |
| Gửi `age=xyz` | Conversion error; không tự fallback thành một số tùy ý. |
| Không gửi `displayName` | Setter phase không gán; field giữ giá trị khởi tạo (nếu có); `@NotBlank` từ chối nếu còn null/rỗng. |
| Gửi `displayName=` | Một chuỗi rỗng có thể được gán, sau đó `@NotBlank` từ chối. |
| Gửi `role=ADMIN` | Với allowedFields chỉ chứa `displayName`, setter `role` không nhận giá trị. |
| Gửi JSON `{"role":"ADMIN"}` tới `@RequestBody` | Cần kiểm soát bằng DTO/Jackson và chính sách API riêng; `WebDataBinder` không bảo vệ đường đi JSON này. |

Không tự “sửa” giá trị sai thành mặc định chỉ vì việc bind tiện hơn. Nếu cần default động dựa trên user, tenant hoặc thời điểm, nên quyết định ở application service và kiểm tra lại bất biến sau khi xác định giá trị cuối.

## 15. Với nested object và collection, cần chọn một pha sở hữu đường dẫn

Spring constructor binding có thể dựng nested object bằng tên tham số lồng nhau; property binding cũng có thể ghi đường dẫn `address.city` hoặc `items[0].quantity` khi target và converter phù hợp.

Nếu vừa construct `address` từ `address.city` vừa cho setter phase quyền ghi `address.city`, dữ liệu đó có thể được xử lý hai lần. Với object graph phức tạp:

- Quyết định nested object nào **bất biến và thuộc constructor phase**.
- Chỉ mở setter paths cho những field bổ sung thực sự cần thay đổi.
- Kiểm soát allowedFields bằng những patterns cụ thể, tránh wildcard quá rộng như `"*"`.
- Nếu dùng collections/indexed fields, giới hạn kích thước, index và auto-grow phù hợp để tránh object graph lớn ngoài ý muốn.
- Validation nested thường cần `@Valid` để cascade vào child object và các constraint trên child fields.
- Đừng coi nested path mở cho binding là bằng chứng người dùng có quyền cập nhật toàn bộ child object.

Tách constructor keys khỏi property keys trong thiết kế giúp tránh sự nhập nhằng khi nhiều thành phần cùng xử lý một đường dẫn.

## 16. Ba kiểu DTO và lựa chọn phù hợp

| Kiểu | Ví dụ | Khuyến nghị |
| --- | --- | --- |
| **Chỉ constructor** | `record SearchRequest(String query, int limit)` | Đơn giản, rõ field nào được tạo; phù hợp với API input bất biến. Dùng declarative binding nếu cần ngăn setter binding ở context MVC có object khác. |
| **Chỉ property** | JavaBean có constructor rỗng, setter cho các field có thể sửa | Phù hợp form cũ hoặc công cụ binding mutable; dùng DTO riêng và allowedFields khi nhận dữ liệu không tin cậy. |
| **Phối hợp có kiểm soát** | `ProfileForm(String email, int age)` + `setDisplayName` | Chỉ dùng nếu thực sự có cả tập tham số tạo đối tượng và tập thuộc tính bổ sung; bật declarativeBinding và allowlist setter rõ ràng. |

Không nên chọn hybrid chỉ vì framework hỗ trợ. Nếu không có lý do cần setter phase, immutable DTO với constructor/record thường đơn giản hơn. Nếu cần một form mutable hoàn toàn, một input DTO chuyên biệt có thể dễ hiểu hơn. Quyết định dựa trên ngữ nghĩa dữ liệu và vòng đời đối tượng, không dựa vào số lượng annotation.

## 17. Các lỗi thiết kế thường gặp

**Lỗi 1: Cho rằng `@ModelAttribute` luôn chỉ gọi setter.** Với data constructor hoặc record, Spring có thể dùng constructor binding để tạo đối tượng, rồi property binding nếu được phép.

**Lỗi 2: Có no-arg constructor và data constructor nhưng nghĩ Spring chắc chắn chọn data constructor.** Quy tắc constructor selection phụ thuộc cấu trúc class; một default constructor có thể được ưu tiên khi nhiều constructor tồn tại. Cần thiết kế class rõ ràng và có test.

**Lỗi 3: Đặt field đặc quyền ở constructor rồi tin `allowedFields` chặn được.** `allowedFields` dùng cho property binding; không thay thế việc chọn constructor inputs an toàn.

**Lỗi 4: Bật `setDeclarativeBinding(true)` rồi quên khai báo `allowedFields` cho setter field cần dùng.** Property phase sẽ không tự bind những field đó; `displayName` có thể vẫn null và validation thất bại.

**Lỗi 5: Dùng setter cho chính giá trị đã khởi tạo bằng constructor.** Có thể gây gán lặp, ghi đè, chuẩn hóa hai lần hoặc side effect. Chia rõ quyền sở hữu field giữa hai pha.

**Lỗi 6: Dùng JPA entity làm input model.** Entity có thể chứa nhiều setters ngoài hợp đồng request, hoặc đang có trạng thái từ DB. Hãy nhận DTO và cập nhật entity qua service.

**Lỗi 7: Cho rằng `@RequestBody` JSON dùng chính sách allowedFields của `@InitBinder`.** JSON deserialization có pipeline riêng.

**Lỗi 8: Coi conversion là validation.** Chuyển `"0"` sang `int 0` thành công không nghĩa dữ liệu đã đúng `@Min` hay nghiệp vụ.

**Lỗi 9: Bỏ `BindingResult` hoặc đặt sai vị trí.** Dễ không nhận được lỗi binding/validation tại controller như mong muốn.

**Lỗi 10: Coi mọi suppressed field là tấn công.** Trong hybrid binding, tên constructor đã hợp lệ vẫn có thể bị liệt kê trong property phase; hãy kiểm tra hợp đồng toàn bộ request.

**Lỗi 11: Đưa side effect vào constructor/setter.** Một request bị từ chối vẫn có thể đã chạy constructor/setter. Side effects và transactional domain changes thuộc service sau khi dữ liệu được kiểm tra.

**Lỗi 12: Không kiểm thử riêng thứ tự và ranh giới giữa hai pha.** Một testcase chỉ có request hợp lệ có thể bỏ sót trường đặc quyền, name collision, lỗi chuyển kiểu và path lồng nhau.

## 18. Bảng kiểm thử khuyến nghị

| Trường hợp | Kỳ vọng |
| --- | --- |
| Gửi `email`/`age`/`displayName` hợp lệ | Tạo form qua constructor, bổ sung displayName qua setter, validation thành công. |
| Chỉ gửi constructor fields, thiếu displayName | Bị `@NotBlank` từ chối theo contract. |
| `age=abc` | Lỗi conversion ở constructor binding, không âm thầm lấy default. |
| `age=17` | Có thể construct, nhưng `@Min(18)` từ chối. |
| Gửi `role=ADMIN` | Không đổi role qua setter khi allowlist chỉ có displayName. |
| Bật declarative binding nhưng không có allowedFields | Chỉ constructor binding; setter field không tự nhận dữ liệu. |
| Dùng input DTO có nhiều constructor | Xác nhận chính xác constructor được chọn. |
| Dùng `@BindParam` cho tên chứa dấu gạch nối | Tên ngoài ánh xạ đúng về constructor argument. |
| Đối tượng đã có sẵn trong model | Không giả định constructor binding chạy lại; kiểm tra property update. |
| JSON `@RequestBody` với field ngoài hợp đồng | Từ chối/giới hạn bằng cơ chế JSON DTO phù hợp; không tin @InitBinder. |
| Nested field trùng tên qua hai pha | Kiểm tra không bị gán lặp hoặc override ngoài dự định. |
| Quan sát suppressed fields | Không đánh đồng constructor keys hợp lệ với malicious fields. |

Khi test integration, nên dùng `MockMvc` cho binder behavior và HTTP status, unit test cho quy tắc tạo DTO/normalization, và test service/domain riêng cho quyền và nghiệp vụ. Với ứng dụng thực, việc test security nên gồm cả form, JSON và các adapter khác nếu chúng sử dụng cùng DTO.

## 19. Quy trình thiết kế chủ đích cho một form mới

1. **Liệt kê các field trong hợp đồng đầu vào** và phân biệt nguồn client với thông tin phải suy ra từ phiên đăng nhập hay server.
2. **Chọn những field cần để tạo đối tượng**: đặt vào một data constructor rõ ràng hoặc record, không thêm field đặc quyền do client điều khiển.
3. **Xem có thực sự cần property binding không**: nếu không, dùng immutable input và tắt setter phase bằng declarative binding.
4. Nếu có setter phase, **liệt kê tên property được phép** bằng `setAllowedFields(...)` và bật `setDeclarativeBinding(true)`.
5. **Tránh chồng tên** giữa constructor arguments và writable setter paths; khi không tránh được, test cụ thể thứ tự và kết quả cuối.
6. **Khóa kiểu, tên và conversion**: bảo đảm runtime có metadata tên constructor parameters; dùng `@BindParam` khi hợp đồng bên ngoài dùng tên khác.
7. **Validation sau binding**: `@Valid`/`@Validated` và `BindingResult` đúng vị trí; kiểm tra quyền/chính sách trong service trước lưu.
8. **Kiểm thử tình huống đối kháng**: field lạ, field đặc quyền, nested path, type mismatch, null/thiếu, object đã có trong model, JSON endpoint khác pipeline.
9. **Đánh giá object cuối cùng** trước khi dùng: không cho một target bị bind lỗi đi tiếp vào hoạt động ghi dữ liệu.

Thiết kế tốt chỉ cần trả lời ba câu hỏi: **constructor chịu trách nhiệm tạo những giá trị nào; setter được quyền thay đổi những property nào; sau cả hai bước, ai kiểm tra đối tượng trước khi thực hiện nghiệp vụ?**

## Tham khảo chính thức

- [Spring Framework 6.2 – Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html): constructor binding, property binding, cách dùng cả hai và cơ chế dựng target.
- [Spring Framework 6.2 – @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): nguồn tạo attribute, cả constructor/property binding, BindParam và BindingResult.
- [Spring Framework 6.2 – Web MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): model design, allowedFields, declarative binding và bảo vệ khỏi mass assignment.
- [Spring Framework 6.2 – @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): cấu hình WebDataBinder trong controller.
- [Spring Framework 6.2 – DataBinder JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html): `setDeclarativeBinding`, `setAllowedFields`, `setTargetType`, `construct`, `bind` và `getBindingResult`.
