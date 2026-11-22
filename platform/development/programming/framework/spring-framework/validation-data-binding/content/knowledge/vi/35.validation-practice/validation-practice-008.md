# Bảo vệ form cập nhật bằng allowedFields và kiểm tra trường bị loại

## 1. Bài toán: client cập nhật profile nhưng lén gửi thêm quyền quản trị

Một ứng dụng Spring MVC có trang cập nhật thông tin cá nhân. Người dùng được phép sửa **tên hiển thị** và **tiểu sử**, nhưng **không** được phép tự đổi vai trò (`role`), cờ quản trị (`admin`) hoặc chủ sở hữu (`ownerId`).

Request form hợp lệ:

```http
POST /api/profile/update
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java%20developer
```

Request có dấu hiệu **mass assignment / overposting**:

```http
POST /api/profile/update
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java%20developer&role=ADMIN&admin=true&ownerId=999
```

Nếu controller bind trực tiếp mọi property của một mutable JavaBean hoặc JPA entity có setters, Spring có thể gán các giá trị không được phép. Đây là nguy cơ **mass assignment**: một trường không được render trên giao diện không có nghĩa attacker không thể gửi tên trường đó trong HTTP request.

Trong Spring MVC, một lớp bảo vệ khi **property binding** là:

```java
@InitBinder("profileForm")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
```

Khi đó những tham số ngoài allowlist sẽ không được dùng để gán property. Nhưng có một chi tiết cực kỳ quan trọng:

**Trường bị loại không mặc nhiên trở thành `FieldError` hoặc HTTP 400.**

Bạn phải kiểm tra riêng:

```java
String[] suppressed = bindingResult.getSuppressedFields();
```

Chẳng hạn `role`, `admin` và `ownerId` có thể xuất hiện trong `suppressed`. Controller có thể quyết định từ chối toàn bộ request thay vì chỉ âm thầm bỏ qua. Bài thực hành này dùng chính sách **reject-on-suppression**: nếu phát hiện bất kỳ field không được cho phép, không áp dụng bất cứ cập nhật nào và trả lỗi HTTP 400 an toàn.

**Mục tiêu học tập:**

1. Hiểu nguy cơ mass assignment khi dùng `@ModelAttribute`/`WebDataBinder`.
2. Dùng `setAllowedFields` theo danh sách đóng (allowlist).
3. Đọc `BindingResult#getSuppressedFields` để phát hiện tham số bị bỏ qua.
4. Phân biệt suppressed field với binding error và Bean Validation error.
5. Quy định cách xử lý: bỏ qua có chủ đích, cảnh báo, hay từ chối toàn request.
6. Bảo đảm cập nhật chỉ thay đổi những trường được business cho phép, không gán trực tiếp vào JPA entity.
7. Viết bộ test `MockMvc` và `DataBinder` để chứng minh không xảy ra overposting.
8. Hiểu giới hạn: `allowedFields` áp dụng cho **property binding**, không phải một bộ lọc JSON của Jackson và không thay thế kiểm tra quyền.

**Môi trường tham chiếu:** Java 17+, Spring Boot 3.3.6, Spring Framework 6.1, Spring MVC Servlet, Jakarta Bean Validation. Demo chạy độc lập bằng Gradle, không cần database. Một kho dữ liệu in-memory chỉ dùng để giúp quan sát trước/sau cập nhật; khi triển khai thật nên thay bằng service/repository có transaction, identity và authorization đúng.

## 2. Vì sao việc “ẩn trường trên HTML” không phải bảo mật?

Một form HTML chỉ chứa:

```html
<form method="post" action="/api/profile/update">
  <input name="displayName" value="Lan">
  <textarea name="bio">Java developer</textarea>
  <button type="submit">Save</button>
</form>
```

Nhưng attacker có thể sử dụng curl, Postman hoặc công cụ sửa HTTP request để gửi:

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java developer' \
  --data-urlencode 'admin=true' \
  --data-urlencode 'role=ADMIN'
```

Spring không dựa vào những input từng xuất hiện trên trang HTML. Nó xử lý **request parameters thực tế**. Nếu model có setter phù hợp và controller không giới hạn property binding, các tên property có thể được bind.

Đoạn code nguy hiểm thường gặp:

```java
@PostMapping("/update")
public String update(@ModelAttribute AccountEntity account) {
    repository.save(account);
    return "redirect:/profile";
}
```

Đây là **đoạn phản ví dụ**, không thuộc project runnable. Nó đồng thời có nhiều vấn đề: bind trực tiếp vào entity, mất ranh giới các trường client được phép chỉnh, khả năng nhận ID/role ngoài ý muốn, thiếu kiểm tra ownership và có thể ghi đè dữ liệu hiện hữu.

**Không nên dùng việc frontend không hiển thị `role` làm cơ chế bảo mật.** Quyền cập nhật phải được kiểm soát tại server.

## 3. Cơ chế DataBinder và allowedFields

### 3.1. Property binding mặc định

Với một JavaBean có setter:

```java
public class LegacyForm {
    private String displayName;
    private String role;

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

Nếu tạo `DataBinder` rồi gọi `bind(...)` với `displayName=Lan` và `role=ADMIN`, mặc định binder có thể bind **cả hai** property. Phần này không có bảo vệ role trừ khi bạn thiết kế DTO hoặc binder policy riêng.

### 3.2. setAllowedFields

```java
binder.setAllowedFields("displayName", "bio");
```

Spring `DataBinder` so sánh từng property name với allowlist. Những property không phù hợp được **loại khỏi danh sách property values trước khi bind**.

Cơ chế có thể được hình dung:

```text
HTTP form parameters
  displayName=Lan
  bio=Java developer
  role=ADMIN
  admin=true
  ownerId=999
         |
         v
WebDataBinder
  allowedFields = [displayName, bio]
         |
         +--> displayName=Lan        -> cho gán setter
         +--> bio=Java developer     -> cho gán setter
         +--> role=ADMIN             -> suppressed
         +--> admin=true             -> suppressed
         +--> ownerId=999            -> suppressed
         |
         v
BindingResult
  getSuppressedFields(): [role, admin, ownerId]
         |
         v
Controller quyết định:
  - Nếu suppressed không rỗng -> từ chối toàn request.
  - Nếu có binding/validation errors -> báo lỗi tương ứng.
  - Nếu cả hai trống -> gọi service cập nhật.
```

**Thứ tự trong mảng `getSuppressedFields()` không nên được dùng làm hợp đồng API.** Nếu cần so sánh trong test hoặc ghi log tên trường, chuẩn hóa bằng `Set` hoặc sort danh sách.

### 3.3. Cách allowlist được so sánh

Javadoc Spring `DataBinder#setAllowedFields` nêu rõ:

- Mặc định, khi không cấu hình allowed fields, binder cho phép bind tất cả property names phù hợp.
- Các patterns hỗ trợ tên chính xác và wildcard `*`, ví dụ `"xxx*"`, `"*xxx"`, `"*xxx*"`.
- Matching của allowed field patterns về cơ bản **phân biệt chữ hoa/chữ thường**.
- Trước khi kiểm tra, binder có bước canonicalize property path. Với nested/indexed properties, phải hiểu đúng path biểu diễn và pattern tương ứng.
- `setAllowedFields` dùng cho **`bind(PropertyValues)`**, không áp dụng để lọc tham số constructor qua `construct(ValueResolver)`.

Ví dụ:

```java
binder.setAllowedFields(
        "displayName",
        "bio",
        "address.city"
);
```

Phạm vi cho phép có thể chỉ gồm tên, tiểu sử và một field con `address.city`.

Không dùng mẫu quá rộng:

```java
binder.setAllowedFields("*");
```

vì nó gần như vô hiệu hóa ý nghĩa allowlist. Mẫu `"address.*"` cũng cần được xem xét kỹ: nó có thể cho phép **nhiều field con** không intended. Với dữ liệu nhạy cảm, nên liệt kê các property paths chính xác.

### 3.4. allowedFields khác disallowedFields

`setDisallowedFields("role", "admin")` là cách blacklist: mọi field không có trong danh sách cấm vẫn có thể được bind. Khi entity/DTO có thêm property mới, blacklist dễ bỏ sót.

`setAllowedFields("displayName", "bio")` là allowlist: các property mới sẽ **không tự động được cho phép**. Đây là lựa chọn an toàn hơn khi buộc phải dùng mutable property binding.

Trong Spring Framework 6.1, `disallowedFields` có matching không phân biệt chữ hoa/chữ thường, còn `allowedFields` phân biệt chữ hoa/chữ thường. Không suy rằng cả hai có cùng semantics. Trong code security-sensitive, hãy dùng danh sách cho phép rõ ràng thay vì dựa vào kiểu chữ của blacklist.

## 4. BindingResult#getSuppressedFields: điểm kiểm tra thường bị bỏ sót

### 4.1. Suppressed không phải binding error

Một request gửi:

```text
displayName=Lan&bio=Hello&admin=true
```

Nếu `displayName` và `bio` bind đúng kiểu, còn `admin` bị lọc do không nằm trong allowlist, `BindingResult` có thể có:

```text
bindingResult.hasErrors() == false
bindingResult.getSuppressedFields().length == 1
bindingResult.getSuppressedFields()[0] == "admin"
```

Đây là **kết quả minh họa** cho đúng thiết lập binder, không phải bảo đảm thứ tự/mảng trong mọi tình huống. Điểm quan trọng là **`hasErrors()==false` không có nghĩa request không chứa field không được phép**.

Do đó, chỉ viết:

```java
if (bindingResult.hasErrors()) {
    return badRequest();
}
service.update(form);
```

là chưa đủ nếu security policy yêu cầu **reject mọi tham số thừa**.

### 4.2. Chính sách reject-on-suppression

```java
if (bindingResult.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest().body(
            new ApiError(
                    "DISALLOWED_FIELDS",
                    "Request contains fields that cannot be updated",
                    List.of()
            )
    );
}
```

Đây là snippet sẽ xuất hiện trong controller runnable. Nó bảo đảm phương thức cập nhật không được gọi khi request có field không thuộc allowlist.

**Thứ tự kiểm tra cũng quan trọng:**

1. Phát hiện suppressed fields.
2. Nếu suppressed không rỗng, trả lỗi và **không gọi service**.
3. Nếu không suppressed nhưng binding/validation errors tồn tại, trả lỗi dữ liệu.
4. Nếu cả hai đều không có, áp dụng thay đổi qua service.

Một request có thể đồng thời có trường bị loại và field hợp lệ bị lỗi. Bài này ưu tiên trả `DISALLOWED_FIELDS` để tránh cập nhật một phần khi payload đáng ngờ; ứng dụng khác có thể chọn tổng hợp lỗi, nhưng phải có policy nhất quán.

### 4.3. Có nên trả tên trường bị loại cho client?

Trong nhiều ứng dụng, nên trả thông điệp **chung**:

```json
{
  "code": "DISALLOWED_FIELDS",
  "message": "Request contains fields that cannot be updated",
  "errors": []
}
```

Không trả lại nguyên `role=ADMIN`, `ownerId=999`, raw rejected value hoặc stack trace. Tên trường bị loại có thể được ghi vào audit logs **nếu policy cho phép**, nhưng cần tránh log dữ liệu nhạy cảm. Việc có nên tiết lộ danh sách tên trường cho client phụ thuộc API contract và yêu cầu security của sản phẩm.

Nếu muốn audit:

```java
String[] suppressed = bindingResult.getSuppressedFields();
String[] ordered = suppressed.clone();
java.util.Arrays.sort(ordered);

// Chỉ ghi tên trường theo security logging policy;
// tuyệt đối không ghi raw values/password/token.
```

Đây là snippet minh họa. Không lạm dụng audit logs để ghi toàn bộ payload nhạy cảm.

### 4.4. Vì sao không chỉ dựa vào suppressedFields?

Mảng suppressed chỉ mô tả những **property values được binder nhận và đánh dấu là không được phép**. Nó không:

- Kiểm tra user có quyền sở hữu tài khoản đang sửa không.
- Kiểm tra một field **được phép bind** nhưng thay đổi trái business rule không.
- Bảo vệ phương thức service được gọi trực tiếp từ job/event listener.
- Bảo vệ JSON deserialization khi đi qua Jackson thay vì form property binder.
- Thay thế unique constraints, transactions hoặc concurrency controls.
- Bảo đảm một client gửi secret không xuất hiện trong access log của reverse proxy.

Vì vậy, **allowedFields là một lớp trong defense-in-depth**, không phải toàn bộ mô hình bảo mật.

## 5. Ba ranh giới khác nhau: bind, validate và authorize

### 5.1. Binding allowlist

Trả lời câu hỏi: **client được đưa dữ liệu vào những property nào của form object?**

Ví dụ: chỉ `displayName` và `bio`.

### 5.2. Input validation

Trả lời: **giá trị của những property được phép đó có hợp lệ không?**

Ví dụ:

```java
@NotBlank
@Size(max = 60)
private String displayName;

@Size(max = 280)
private String bio;
```

`@NotBlank`/`@Size` không quyết định client có được sửa `role` hay không. Ngược lại, `allowedFields` không tự kiểm tra độ dài hay business format.

### 5.3. Authorization và business mapping

Trả lời: **người dùng hiện tại có quyền cập nhật resource nào, và thay đổi nào được thực hiện?**

Trong production, danh tính đến từ authentication principal/session/JWT đã xác minh — **không tin `ownerId` trong form**. Service cần tải resource theo identity/scope và kiểm tra quyền. Khi cập nhật, chỉ ánh xạ từng field được phép:

```java
account.setDisplayName(form.getDisplayName());
account.setBio(form.getBio());
```

Đây là snippet minh họa; giả định `account` đã được tải và đã kiểm tra ownership. Không dùng `BeanUtils.copyProperties(form, entity)` vô điều kiện hoặc object mapping phản xạ mà vô tình copy `role`/`ownerId`.

## 6. Hành vi với constructor binding, record và declarativeBinding

Spring MVC 6.1 hỗ trợ constructor binding cho object bất biến và Java records. Cần ghi nhớ **`setAllowedFields` kiểm soát property binding, không phải constructor parameters**.

### 6.1. Property binding

```java
public class ProfileForm {
    private String displayName;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Với setter/property binding, allowlist chặn các property không được cho phép.

### 6.2. Constructor binding

```java
public record ImmutableProfileForm(
        String displayName,
        String bio
) {}
```

Spring có thể tạo object qua constructor dựa trên parameter names. Constructor chỉ yêu cầu hai giá trị này, không có setter `role`, nên thiết kế immutable input DTO là hướng nên ưu tiên.

**Giới hạn:** nếu chính record khai báo thêm `String role` hoặc `Long ownerId` trong constructor, allowlist property binding **không thể được giả định sẽ lọc các constructor parameters đó**. Thiết kế constructor input shape đúng từ đầu là thiết yếu.

### 6.3. setDeclarativeBinding(true)

Spring Framework 6.1+ cho phép:

```java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Ý nghĩa: constructor binding được áp dụng, còn property binding chỉ được dùng khi có allowedFields patterns. Nếu bạn muốn hỗ trợ một mutable form property binding, cần khai báo allowlist tương ứng:

```java
@InitBinder("profileForm")
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "bio");
}
```

Trong demo runnable phía sau, cấu hình chỉ dùng `setAllowedFields` để tập trung vào property binding và `getSuppressedFields`. Ở production, có thể cân nhắc `declarativeBinding` sau khi kiểm thử toàn bộ form flows và cấu trúc DTO.

**Không nhầm với `setRequiredFields`:** option required fields trên DataBinder áp dụng cho property binding, không tự biến constructor parameters thành bắt buộc. Việc required trên records nên được mô hình hóa bằng validation constraints/boundary phù hợp.

## 7. @ModelAttribute khác @RequestBody JSON

Chữ ký:

```java
public ResponseEntity<?> update(
        @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    ...
}
```

đọc các form/query parameters theo Spring MVC binding; `@InitBinder` có thể đặt `allowedFields` vào `WebDataBinder`.

Ngược lại:

```java
public ResponseEntity<?> updateJson(
        @RequestBody ProfileForm form) {
    ...
}
```

đọc JSON qua `HttpMessageConverter` (thường Jackson). Spring có thể dùng `WebDataBinder` **sau deserialization để validate**, nhưng `DataBinder#setAllowedFields` **không tự lọc JSON properties** khi Jackson tạo object. Do đó, không nên thêm một endpoint JSON như vậy rồi kỳ vọng allowlist form tự bảo vệ `role`.

Nếu API cần JSON:

1. Tạo **dedicated JSON input record** chỉ có `displayName` và `bio`.
2. Dùng `@Valid @RequestBody ProfileUpdateRequest` để validate.
3. Kiểm soát unknown JSON properties theo ObjectMapper policy/API contract nếu cần phát hiện gửi thêm field.
4. Quan trọng nhất: service mapping chỉ thay đổi các trường cho phép và kiểm tra authorization.
5. Nếu muốn chặn JSON có keys không thuộc schema, cấu hình Jackson strict unknown-property policy trên input DTO/ObjectMapper theo cách đã kiểm thử. Đây là trách nhiệm của JSON deserialization, không phải `setAllowedFields`.

**Đừng dùng “Jackson bỏ qua unknown fields” làm một security boundary duy nhất.** DTO có thể phát triển thêm properties; cần bảo đảm role/privileged setters không nằm trong đầu vào và mapping service không tự gán toàn bộ entity.

## 8. Dự án Spring Boot chạy được: update profile với allowlist

Demo dùng Java 17 và Spring Boot 3.3.6. Có hai endpoint:

- `GET /api/profile`: xem trạng thái hiện tại của một profile duy nhất trong demo.
- `POST /api/profile/update`: cập nhật tên và tiểu sử qua `application/x-www-form-urlencoded`, kiểm tra allowed fields, suppressed fields và Bean Validation.

**Quan trọng về security:** endpoint không có authentication vì đây là một ví dụ cô lập để học data binding, không phải API production. Profile demo luôn có ID=1 và role=USER; khi triển khai thật phải thêm Spring Security/principal và authorization trong service.

### 8.1. Cấu trúc thư mục

```text
profile-allowed-fields-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/profilebinding/
        ProfileBindingApplication.java
        ProfileForm.java
        ProfileView.java
        FieldIssue.java
        ApiError.java
        ProfileService.java
        ProfileController.java
      resources/
        application.properties
    test/
      java/com/example/profilebinding/
        ProfileAllowedFieldsTest.java
```

### 8.2. settings.gradle

```groovy
rootProject.name = 'profile-allowed-fields-demo'
```

### 8.3. build.gradle

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

`spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider trong cấu hình Spring Boot 3.x thường gặp. `spring-boot-starter-web` cung cấp Spring MVC, WebDataBinder và Jackson cho JSON response.

### 8.4. application.properties

`src/main/resources/application.properties`:

```properties
spring.application.name=profile-allowed-fields-demo
spring.mvc.problemdetails.enabled=false
```

Dòng Problem Details chỉ giữ demo error response đơn giản. Trong ứng dụng production, có thể dùng `ProblemDetail` theo RFC 9457, nhưng suppressed field policy vẫn phải do controller/service chủ động thực hiện.

### 8.5. Main application

`src/main/java/com/example/profilebinding/ProfileBindingApplication.java`:

```java
package com.example.profilebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ProfileBindingApplication.class, args
        );
    }
}
```

### 8.6. ProfileForm: minh họa một DTO legacy có nhiều setters

`src/main/java/com/example/profilebinding/ProfileForm.java`:

```java
package com.example.profilebinding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 60)
    private String displayName;

    @Size(max = 280)
    private String bio;

    // Cố ý giữ các property legacy để minh họa overposting.
    // Trong DTO production mới, HÃY XÓA các property này.
    private String role;
    private Boolean admin;
    private Long ownerId;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getBio() {
        return bio;
    }

    public void setBio(String bio) {
        this.bio = bio;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public Boolean getAdmin() {
        return admin;
    }

    public void setAdmin(Boolean admin) {
        this.admin = admin;
    }

    public Long getOwnerId() {
        return ownerId;
    }

    public void setOwnerId(Long ownerId) {
        this.ownerId = ownerId;
    }
}
```

**Vì sao demo có `role`/`admin`/`ownerId` trên form?** Để test thật sự chứng minh chúng **sẽ được bind nếu không có allowlist**, nhưng **bị suppressed nếu có allowlist**. Đây là tình huống legacy cần bảo vệ. Trong code sản phẩm mới, thiết kế đúng hơn là tạo một DTO chỉ gồm `displayName` và `bio`; allowlist sẽ là lớp bảo vệ bổ sung chứ không phải lý do để giữ setters nhạy cảm.

`@NotBlank` chặn null/chuỗi rỗng/khoảng trắng. `@Size(max=60)` chặn tên quá dài, `@Size(max=280)` chặn tiểu sử quá dài; `@Size` thường cho phép null nên `bio` là tùy chọn.

### 8.7. ProfileView: dữ liệu server đang giữ

`src/main/java/com/example/profilebinding/ProfileView.java`:

```java
package com.example.profilebinding;

public record ProfileView(
        long id,
        String displayName,
        String bio,
        String role,
        boolean admin
) {}
```

`role` và `admin` có thể được **hiển thị** qua read response trong demo nhưng không được **cập nhật** từ profile form. Được phép đọc không đồng nghĩa được phép ghi. Trong ứng dụng thực tế, việc hiển thị metadata nội bộ cũng cần quy tắc phân quyền/ẩn dữ liệu phù hợp.

### 8.8. FieldIssue và ApiError

`src/main/java/com/example/profilebinding/FieldIssue.java`:

```java
package com.example.profilebinding;

public record FieldIssue(
        String field,
        String code
) {}
```

`src/main/java/com/example/profilebinding/ApiError.java`:

```java
package com.example.profilebinding;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<FieldIssue> errors
) {}
```

`DISALLOWED_FIELDS` là mã khi request chứa input ngoài allowlist. `VALIDATION_ERROR` là mã cho những trường cho phép nhưng giá trị không đạt constraint. Public response không chứa raw rejectedValue hoặc danh sách internal property names.

### 8.9. ProfileService: chỉ áp dụng field đã cho phép

`src/main/java/com/example/profilebinding/ProfileService.java`:

```java
package com.example.profilebinding;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    private final AtomicReference<ProfileView> state =
            new AtomicReference<>(initial());

    public ProfileView current() {
        return state.get();
    }

    public ProfileView update(ProfileForm form) {
        return state.updateAndGet(old -> new ProfileView(
                old.id(),
                form.getDisplayName().trim(),
                form.getBio() == null ? old.bio() : form.getBio(),
                old.role(),
                old.admin()
        ));
    }

    // Chỉ dùng cho fixture kiểm thử của demo in-memory.
    void resetDemoState() {
        state.set(initial());
    }

    private static ProfileView initial() {
        return new ProfileView(
                1L,
                "An",
                "Tiểu sử cũ",
                "USER",
                false
        );
    }
}
```

Service **không** đọc `form.getRole()`, `form.getAdmin()` hay `form.getOwnerId()`. Dù một lỗi khác khiến các trường đó bị bind, implementation của update vẫn chỉ map `displayName` và `bio` — một lớp bảo vệ thứ hai.

`AtomicReference#updateAndGet` phù hợp cho demo một profile, không đại diện cho transaction/locking của database thật. Production thường cần tải entity theo authenticated identity, kiểm tra quyền, version/optimistic locking khi có concurrent updates, validate invariants và persist trong transaction.

`resetDemoState()` là phương thức package-private phục vụ test fixtures; không có endpoint HTTP cho nó. Trong ứng dụng thật, không nên cung cấp endpoint cho phép reset dữ liệu.

### 8.10. ProfileController: @InitBinder, suppressedFields và BindingResult

`src/main/java/com/example/profilebinding/ProfileController.java`:

```java
package com.example.profilebinding;

import jakarta.validation.Valid;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private final ProfileService profiles;

    public ProfileController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @InitBinder("profileForm")
    void restrictProfileForm(WebDataBinder binder) {
        // Chỉ hai property được phép set bằng form binding.
        binder.setAllowedFields("displayName", "bio");
    }

    @GetMapping
    public ProfileView current() {
        return profiles.current();
    }

    @PostMapping(
            path = "/update",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> update(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        // Bước bảo mật không được bỏ qua:
        // suppressed fields KHÔNG tự làm result.hasErrors() == true.
        if (result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "DISALLOWED_FIELDS",
                            "Request contains fields that cannot be updated",
                            List.of()
                    )
            );
        }

        if (result.hasErrors()) {
            List<FieldIssue> issues = result.getAllErrors()
                    .stream()
                    .map(ProfileController::toIssue)
                    .sorted(Comparator.comparing(FieldIssue::field)
                            .thenComparing(FieldIssue::code))
                    .toList();

            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "VALIDATION_ERROR",
                            "Profile form is invalid",
                            issues
                    )
            );
        }

        // Chỉ thực hiện sau khi không có suppressed/errors.
        return ResponseEntity.ok(profiles.update(form));
    }

    private static FieldIssue toIssue(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        return new FieldIssue(
                field,
                Objects.toString(error.getCode(), "invalid")
        );
    }
}
```

**Chú ý từng điều kiện:**

1. `@InitBinder("profileForm")` chỉ cấu hình binder của model attribute tên `profileForm`, tránh ảnh hưởng các form khác không cùng policy.
2. `setAllowedFields("displayName","bio")` lọc setter/property binding.
3. `@Valid` chạy Bean Validation sau bind khi object có thể được kiểm tra.
4. `BindingResult result` đứng **ngay sau** argument form; nếu không, controller không nhận được binding/validation errors như thiết kế.
5. `getSuppressedFields` được kiểm tra **trước** `hasErrors`. Nếu payload có field bị cấm, từ chối request trước khi update.
6. `getAllErrors` lấy cả `FieldError` và `ObjectError`; payload được sort theo field/code thay vì phụ thuộc thứ tự provider.
7. Service update chỉ nhận object sau khi qua các bước gate và vẫn map field tường minh.
8. Controller không trả suppressed field **values** hay schema internals cho client.
9. Không dùng `BeanUtils.copyProperties` trên entity; điều đó có thể làm mất security contract.

### 8.11. Tại sao không có @RestControllerAdvice cho suppressed fields?

Suppressed fields **không mặc nhiên ném exception**. Một `@ExceptionHandler(MethodArgumentNotValidException.class)` không thể tự bắt được chuyện client gửi `role=ADMIN` nếu các input được phép đều valid và binder chỉ suppress role.

Vì vậy, có `BindingResult` ngay trong controller để đọc `getSuppressedFields` và quyết định reject là cách minh bạch nhất trong demo. Với nhiều controllers, có thể tạo một helper/policy chung, nhưng phải bảo đảm nó được gọi ở **mọi update boundary** cần chặn overposting.

Đừng giả định rằng “dự án đã có global validation advice” là đủ để bảo vệ property binding.

## 9. Chạy ứng dụng và quan sát phản hồi

Trong project có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có Gradle wrapper, dùng Gradle phù hợp đã cài và chạy `gradle bootRun` hoặc tạo wrapper.

### 9.1. Xem profile ban đầu

```bash
curl -i http://localhost:8080/api/profile
```

Kỳ vọng HTTP 200, phần body:

```json
{
  "id": 1,
  "displayName": "An",
  "bio": "Tiểu sử cũ",
  "role": "USER",
  "admin": false
}
```

Dữ liệu in-memory sẽ reset khi ứng dụng khởi động lại.

### 9.2. Cập nhật hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java developer'
```

Kỳ vọng HTTP **200 OK**:

```json
{
  "id": 1,
  "displayName": "Lan",
  "bio": "Java developer",
  "role": "USER",
  "admin": false
}
```

Role và admin không thay đổi vì không thuộc các field được phép chỉnh và vì service không copy chúng từ form.

### 9.3. Gửi thêm trường bị cấm

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Hacker' \
  --data-urlencode 'bio=Overposted' \
  --data-urlencode 'role=ADMIN' \
  --data-urlencode 'admin=true' \
  --data-urlencode 'ownerId=999'
```

Kỳ vọng HTTP **400 Bad Request**:

```json
{
  "code": "DISALLOWED_FIELDS",
  "message": "Request contains fields that cannot be updated",
  "errors": []
}
```

Gọi lại GET profile sẽ thấy **không có thay đổi nào từ request này**, vì controller reject trước khi service chạy. Nếu trước đó đã thực hiện 9.2, tên vẫn là `Lan` và bio vẫn `Java developer`.

### 9.4. Tên rỗng là lỗi validation, không phải suppressed field

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=   ' \
  --data-urlencode 'bio=Hello'
```

Kỳ vọng HTTP 400, mã `VALIDATION_ERROR` và một lỗi field `displayName` có code `NotBlank`. Field `displayName` nằm trong allowlist, nên không bị suppressed; nó sai **giá trị**, không sai **quyền ghi field**.

## 10. Bộ kiểm thử MockMvc và DataBinder

Tệp `src/test/java/com/example/profilebinding/ProfileAllowedFieldsTest.java`:

```java
package com.example.profilebinding;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileAllowedFieldsTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProfileService profiles;

    @BeforeEach
    void resetState() {
        profiles.resetDemoState();
    }

    @Test
    void validFormChangesOnlyEditableProperties() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("bio", "Java developer"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.bio").value("Java developer"))
            .andExpect(jsonPath("$.role").value("USER"))
            .andExpect(jsonPath("$.admin").value(false));

        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void forbiddenAdminIsSuppressedAndRejected() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Eve")
                .param("bio", "Try privilege change")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
        assertFalse(profiles.current().admin());
    }

    @Test
    void forbiddenRoleIsSuppressedAndRejected() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Eve")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("USER", profiles.current().role());
    }

    @Test
    void forbiddenOwnerIdIsSuppressedAndRejected()
            throws Exception {

        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Eve")
                .param("ownerId", "999"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals(1L, profiles.current().id());
        assertEquals("An", profiles.current().displayName());
    }

    @Test
    void unknownFieldIsSuppressedAndRejected() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("newFeatureFlag", "enabled"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
    }

    @Test
    void rejectedRequestDoesNotApplyValidFieldsPartially()
            throws Exception {

        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Valid New Name")
                .param("bio", "Valid new bio")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
        assertEquals("Tiểu sử cũ", profiles.current().bio());
    }

    @Test
    void missingNameTriggersValidationError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("bio", "Hello"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("NotBlank"));
    }

    @Test
    void blankNameTriggersValidationError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "  "))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("NotBlank"));
    }

    @Test
    void tooLongNameTriggersSizeError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "x".repeat(61)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("Size"));
    }

    @Test
    void tooLongBioTriggersSizeError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("bio", "a".repeat(281)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field")
                    .value("bio"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("Size"));
    }

    @Test
    void missingOptionalBioPreservesOldBio() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.bio").value("Tiểu sử cũ"));
    }

    @Test
    void suppressedFieldTakesPrecedenceOverInvalidAllowedData()
            throws Exception {

        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "  ")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
    }

    @Test
    void wrongContentTypeIsNotFormBinding() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"displayName":"Lan","role":"ADMIN"}
                        """))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void directBinderSuppressesEveryDisallowedProperty() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName", "bio");

        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "bio", "Hello",
                "role", "ADMIN",
                "admin", "true",
                "ownerId", "999"
        )));

        assertEquals("Lan", form.getDisplayName());
        assertEquals("Hello", form.getBio());
        assertNull(form.getRole());
        assertNull(form.getAdmin());
        assertNull(form.getOwnerId());

        BindingResult result = binder.getBindingResult();

        Set<String> suppressed = new HashSet<>(
                Arrays.asList(result.getSuppressedFields())
        );

        assertEquals(
                Set.of("role", "admin", "ownerId"),
                suppressed
        );
        assertFalse(result.hasErrors());
    }

    @Test
    void directBinderWithoutAllowlistIsUnsafeForLegacyDto() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");

        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "role", "ADMIN",
                "admin", "true",
                "ownerId", "999"
        )));

        // Đối chứng: các setter nhạy cảm đã bị gán!
        assertEquals("ADMIN", form.getRole());
        assertEquals(Boolean.TRUE, form.getAdmin());
        assertEquals(999L, form.getOwnerId());
        assertEquals(0, binder.getBindingResult()
                .getSuppressedFields().length);
    }

    @Test
    void suppressedDoesNotAutomaticallyBecomeFieldError() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName", "bio");

        binder.bind(new MutablePropertyValues(
                Map.of("role", "ADMIN")
        ));

        BindingResult result = binder.getBindingResult();

        assertEquals(
                Set.of("role"),
                new HashSet<>(
                        Arrays.asList(result.getSuppressedFields())
                )
        );
        assertFalse(result.hasErrors());
        assertEquals(0, result.getFieldErrorCount());
    }

    @Test
    void allowedFieldPatternIsCaseSensitive() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName");

        binder.bind(new MutablePropertyValues(
                Map.of("DisplayName", "Lan")
        ));

        assertNull(form.getDisplayName());

        assertEquals(
                Set.of("DisplayName"),
                new HashSet<>(
                        Arrays.asList(
                                binder.getBindingResult()
                                        .getSuppressedFields()
                        )
                )
        );
    }

    @Test
    void rejectedFieldValueIsNotReflectedInErrorJson()
            throws Exception {

        String marker = "SENSITIVE_MARKER_414";

        MvcResult result = mvc.perform(
                post("/api/profile/update")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("role", marker)
        )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"))
            .andReturn();

        assertFalse(
                result.getResponse().getContentAsString()
                        .contains(marker)
        );
    }
}
```

Có **18 test methods**, thuộc các nhóm:

- Cập nhật được phép hoạt động và không thay đổi role/admin/ID.
- Gửi `admin`, `role`, `ownerId` và unknown property bị từ chối.
- Không áp dụng một phần update khi có ít nhất một field bị cấm.
- Bean Validation kiểm tra name thiếu, blank, quá dài và bio quá dài.
- Optional bio được giữ nguyên khi người dùng không gửi.
- Với cả invalid allowed value và suppressed field, security policy ưu tiên reject.
- Content-Type JSON không được định tuyến vào form handler.
- `DataBinder` trực tiếp xác minh những tên field bị suppressed và các setters không được gọi.
- Đối chứng `DataBinder` không có allowlist cho thấy legacy sensitive fields bị bind.
- Chứng minh `getSuppressedFields()` không tự tạo `FieldError`.
- Kiểm tra allowed field name matching có phân biệt hoa/thường.
- Xác minh value nhạy cảm của field bị loại không xuất hiện trong HTTP error JSON.

### 10.1. Cách chạy

Từ thư mục project có Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu project chưa có wrapper, dùng Gradle đã cài để tạo wrapper hoặc chạy `gradle test`. **Kỳ vọng 18 test PASS** với Java 17 và đúng Spring Boot 3.3.6 dependencies.

**Kiểm chứng thực tế:** mã và expected behavior đã được rà soát tĩnh; không tuyên bố Gradle/JUnit đã được chạy trong quá trình soạn bài. Khi tích hợp vào dự án thật, hãy chạy tests trên chính Spring/Security/database version của ứng dụng.

### 10.2. Vì sao phải test cả DataBinder và MockMvc?

`DataBinder` test kiểm tra **cơ chế lọc fields** độc lập HTTP:

```java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAllowedFields("displayName", "bio");
binder.bind(values);

String[] suppressed = binder.getBindingResult()
        .getSuppressedFields();
```

Còn `MockMvc` test kiểm tra **tích hợp**:

- `@InitBinder("profileForm")` có được chọn đúng không.
- `@ModelAttribute` có nhận request parameters và gọi binder không.
- `BindingResult` có đứng sát argument không.
- Controller có kiểm tra suppressed fields **trước** khi cập nhật không.
- Service có bảo toàn các trường server sở hữu không.
- API error response có lộ dữ liệu bị loại hay không.

Chỉ test `DataBinder` chưa chứng minh controller thật đã kết nối allowlist; chỉ test HTTP 400 mà không kiểm tra state cũng chưa chứng minh một cập nhật không mong muốn đã bị chặn.

## 11. Các trường hợp nâng cao cần hiểu

### 11.1. Indexed và nested property paths

Nếu form có `address.city` hoặc list `contacts[0].email`, `allowedFields` sử dụng property path patterns. Một số cấu hình ví dụ:

```java
binder.setAllowedFields(
        "displayName",
        "bio",
        "address.city",
        "contacts[0].email"
);
```

Mỗi đường path cần có ý nghĩa nghiệp vụ. `"contacts* "` có khoảng trắng là một pattern khác; đừng copy tùy tiện. `"contacts*"` có thể cho phép nhiều indexed/nested entries, bao gồm những property chưa dự định cho client thay đổi. Nếu cần cho phép nhiều item, kiểm tra giới hạn collection size, object graph growth và field-specific authorization.

**Không coi `setAllowedFields("address")` luôn tương đương cho phép tất cả nested fields `address.*`.** Cần hiểu cách canonical property paths và wildcard matching hoạt động trên Spring version hiện tại; viết tests cho từng nested path muốn hỗ trợ.

### 11.2. Field marker/default prefixes của WebDataBinder

Spring `WebDataBinder` hỗ trợ field marker/default prefixes cho các loại input như checkbox. Chẳng hạn các marker có thể dùng để biểu diễn checkbox không được gửi giá trị trực tiếp. Việc preprocessing các markers có thể làm tên property values được chuyển đổi trước khi lọc.

Trong security review, test thêm:

- Checkbox on/off với tên field được phép.
- Marker cho field không được phép.
- Repeated parameters và các tên có dạng đặc biệt.
- Canonicalized/nested property names.
- Empty/default values và các custom binders.

Không suy rằng chỉ cần test một chuỗi `admin=true` là đủ bảo vệ mọi đường overposting trong một form phức tạp.

### 11.3. Cần cho phép một tập con của nested object

Ví dụ một update form chứa address có `city`, `postalCode`, `verified`. Nếu client chỉ được sửa `city`, hãy cho phép chính xác `address.city` và map riêng. Nếu client gửi `address.verified=true`, policy nên phát hiện và từ chối.

Nếu một user được sửa profile của **người khác** qua user-supplied ID, allowedFields không giải quyết được vấn đề. Authorization/ownership check phải dựa vào identity đã xác minh và scope resource.

### 11.4. allowedFields có thể bị lệch khỏi DTO khi refactor

Một developer thêm setter `setPreferredCurrency(...)` vào DTO nhưng quên cập nhật allowlist. Kết quả field mới có thể bị suppressed và request bị từ chối, mặc dù UI vừa thêm input. Đây là **fail-closed behavior có ích**: thay đổi hợp đồng input cần được review và thêm tests. Không sửa bằng cách thay allowlist thành `"*"` cho tiện.

Ngược lại, nếu rename field từ `bio` thành `biography` mà không đổi `@InitBinder`, field mới cũng bị suppressed. Test cho legitimate update phải phát hiện regression này.

### 11.5. Silent ignore hay reject?

Có hai chính sách hợp lệ tùy product:

| Chính sách | Mô tả | Ưu/nhược |
| --- | --- | --- |
| Ignore | Bỏ qua fields bị cấm, tiếp tục cập nhật fields được phép | Tương thích client cũ hơn, nhưng dễ che payload bất thường |
| Reject | Nếu suppressed không rỗng, từ chối toàn request | Phát hiện overposting rõ, tránh partial update; có thể làm client cũ gửi extra fields bị lỗi |

Demo chọn **Reject** vì mục tiêu thực hành là phát hiện trường bị loại. Dù chọn policy nào, đừng âm thầm coi suppressed fields là proof rằng client không cố gửi dữ liệu nguy hiểm.

### 11.6. Idempotency và concurrency của cập nhật

AllowedFields không giải quyết vấn đề hai request cùng update tên/bio dựa trên bản đọc cũ. Với database thật, có thể cần:

- Entity version qua `@Version` (optimistic locking).
- Conditional requests như `If-Match` và ETag.
- Transaction và merge policy rõ ràng.
- Audit trail của những thay đổi được phép.
- Authorization check gần thời điểm ghi.
- Không cập nhật cả entity bằng dữ liệu client ngoài allowlist.

Đây là vấn đề song song với overposting. Một update chỉ chứa fields được phép vẫn có thể mất dữ liệu do concurrent writes nếu thiếu chiến lược phù hợp.

### 11.7. Multipart, JSON part và source input khác

`@ModelAttribute` có thể bind form data, bao gồm các multipart form fields phù hợp. Nhưng một `@RequestPart` chứa JSON có thể được đọc bằng message converter; `allowedFields` của form binder không tự lọc từng JSON property trước khi deserialization. File upload còn cần kiểm tra kích thước, media type, filename, storage path và authorization riêng.

Không áp dụng máy móc chính sách form-urlencoded sang mọi content type.

## 12. Các lỗi phổ biến

**1. Bind trực tiếp request vào JPA entity có setters nhạy cảm.** Dễ bị overposting; tạo dedicated input DTO và mapping tường minh.

**2. Chỉ ẩn admin/role trên HTML.** Client có thể gửi các tham số không xuất hiện trên trang.

**3. Không cấu hình `setAllowedFields` khi phải dùng property binding.** Mặc định binder có thể bind những property có setter.

**4. Dùng `setDisallowedFields` như lớp bảo vệ duy nhất.** Blacklist dễ sót property mới; allowlist rõ ràng hơn.

**5. Chỉ kiểm tra `bindingResult.hasErrors()`.** Trường bị suppressed có thể không sinh `FieldError`.

**6. Không gọi `getSuppressedFields()`.** Không phát hiện trường mà client đã gửi nhưng binder đã loại.

**7. Kiểm tra suppressed fields sau khi đã gọi service.update.** Quá muộn; phải reject trước khi thay đổi state.

**8. Cho phép cập nhật một phần khi có field bị cấm mà không có policy.** Có thể dẫn đến hành vi khó đoán và mất audit clarity.

**9. Dùng wildcard `"*"` hoặc `"address*"` quá rộng.** Có thể vô tình mở thêm đường bind cho field tương lai.

**10. Tin allowedFields áp dụng cho Jackson JSON `@RequestBody`.** Sai cơ chế: JSON deserialization có ranh giới riêng.

**11. Tin allowedFields lọc constructor parameters.** Javadoc giới hạn nó cho property binding; input constructor phải được thiết kế đúng.

**12. Nghĩ `setDeclarativeBinding(true)` tự chặn mọi constructor argument nguy hiểm.** Constructor binding vẫn nhận những parameter nằm trong constructor.

**13. Cấu hình @InitBinder sai tên attribute.** Policy không được áp lên form cần bảo vệ.

**14. Cấu hình @InitBinder quá rộng cho mọi forms.** Có thể suppress legitimate fields ở endpoint khác; scope hợp lý.

**15. Không để BindingResult sát @ModelAttribute argument.** Controller không có errors đúng như mong đợi.

**16. Trả raw rejectedValue hoặc suppressed field values trong JSON.** Có thể lộ email, token hoặc dữ liệu riêng tư.

**17. Không có server-side authorization.** AllowedFields chỉ hạn chế thuộc tính, không quyết định user có quyền sửa resource nào.

**18. Tin role không đổi vì service bỏ qua role là đủ.** Service mapping là quan trọng nhưng binder policy/test vẫn hữu ích để phát hiện payload bất thường.

**19. Chỉ test outcome response, không kiểm tra state.** Một request có thể trả 400 nhưng dữ liệu đã bị thay đổi trước đó.

**20. Chỉ test form hợp lệ.** Không phát hiện overposting của `admin`, `role`, `ownerId`.

**21. So sánh thứ tự mảng getSuppressedFields.** Thứ tự không phải hợp đồng API; nên so tên dưới dạng tập hoặc sort.

**22. Dùng DTO có privileged setters vì “dù sao có allowlist”.** DTO mới nên loại hẳn các trường đó; allowlist là defense-in-depth.

**23. Gộp suppressed fields vào business validation errors mà không phân biệt.** Dễ che security event; cần code/tracking riêng.

**24. Chỉ kiểm tra HTTP form, bỏ JSON/multipart/other writers.** Các đường input khác có thể không qua cùng binder.

**25. Mở rộng allowlist khi bị lỗi mà không review domain rule.** Field bị suppressed có thể là biểu hiện client gửi dữ liệu không được phép, không phải bug UI.

## 13. Checklist kiểm thử và code review

1. Controller đang dùng `@ModelAttribute` property binding hay `@RequestBody` JSON?
2. Nếu dùng mutable form, có dedicated DTO thay vì entity?
3. `@InitBinder` có scope đúng attribute name?
4. `setAllowedFields` có danh sách **chính xác** những fields được phép cập nhật?
5. Nếu có wildcard, nó có phạm vi hẹp và tests cho nested/indexed paths?
6. Có tránh dùng `setDisallowedFields` làm security policy duy nhất?
7. Controller có đọc `BindingResult#getSuppressedFields()` **trước khi gọi service**?
8. Có quyết định rõ reject hay ignore suppressed fields?
9. Nếu reject, response có code ổn định và không tiết lộ raw values?
10. Nếu ignore, có audit/security monitoring phù hợp và không coi payload là sạch?
11. Có kiểm tra Bean Validation/binding errors riêng với suppressed fields?
12. `BindingResult` có đứng ngay sau `@ModelAttribute`?
13. Có test allowed name/bio cập nhật được?
14. Có test `admin=true`, `role=ADMIN`, `ownerId=999` và unknown fields?
15. Có test **toàn request bị từ chối mà state không thay đổi**?
16. Có test DataBinder trực tiếp xác minh `getSuppressedFields` và setter không được gọi?
17. Có test đối chứng binder không allowlist để hiểu mass assignment risk?
18. Có test allowedField patterns phân biệt hoa/thường và nested inputs khi có?
19. Có test input hợp lệ về field name nhưng sai giá trị/format?
20. Service có map từng field được phép và giữ nguyên server-owned fields?
21. Có lấy identity/ownership từ authentication context thay vì request field?
22. Nếu cập nhật trong database, có transaction/concurrency/versioning đúng?
23. Có kiểm thử JSON endpoints riêng, không nhầm allowedFields thành Jackson filter?
24. Có giới hạn collection growth, upload size và binding complexity?
25. Có kiểm tra logs không chứa dữ liệu của trường bị loại?
26. Có chạy integration tests khi nâng Spring Boot/Spring Framework?
27. Có đảm bảo một đổi tên DTO field phải đi cùng review allowlist và tests?
28. Có nêu rõ behavior của HTTP 400/422 và error codes trong API contract?

**Kết luận:** với Spring MVC property binding, `WebDataBinder#setAllowedFields(...)` là một hàng rào ngăn HTTP form gán những property ngoài danh sách cho phép. Nhưng **lọc field không đồng nghĩa request tự bị coi là lỗi**: hãy đọc `BindingResult#getSuppressedFields()` và áp dụng chính sách reject hoặc ignore có chủ đích. Để bảo vệ cập nhật dữ liệu, cần kết hợp **dedicated input DTO, allowlist, validation, kiểm tra suppressed trước service call, mapping từng field và authorization**. Bộ test phải chứng minh cả hai phía: dữ liệu hợp lệ vẫn cập nhật được, còn những tham số `role`/`admin`/`ownerId` bị loại và không gây ra bất kỳ thay đổi trái phép nào.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): `setAllowedFields`, `setDeclarativeBinding`, property binding và constructor binding.
- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): input model design, allowlist, nested property paths và mass assignment risk.
- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): form binding, constructor/property binding, `BindingResult`.
- [Spring Framework 6.1 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html): `setAllowedFields`, `checkAllowedFields`, patterns, case sensitivity và constructor-binding limitation.
- [Spring Framework 6.1 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/validation/BindingResult.html): `recordSuppressedField`, `getSuppressedFields` và binding error metadata.
- [Spring Framework — Data Binding and Validation](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): DataBinder, BindingResult và type conversion.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, argument validation, method validation.
- [Spring Boot 3.3 — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): Jakarta Bean Validation auto-configuration.
