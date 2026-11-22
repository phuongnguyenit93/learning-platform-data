# Ràng buộc trường dữ liệu và phòng tránh cập nhật thuộc tính ngoài ý muốn trong Spring Boot

## 1. Mục tiêu và vấn đề cần giải quyết

Một form hoặc JSON request có thể chỉ hiển thị hai trường **displayName** và **bio**, nhưng đối tượng Java hoặc entity trong database lại có những thuộc tính khác như **admin**, **role**, **ownerId**, **tenantId**, **approved**, **balance** hoặc **createdAt**. Nếu ứng dụng tự động bind tất cả trường client gửi vào entity rồi lưu lại, một người dùng có thể gửi thủ công thuộc tính không có trên giao diện và thay đổi dữ liệu nhạy cảm.

Đây là vấn đề **mass assignment**, còn gọi là **over-posting**, **unsafe property binding** hoặc **cập nhật thuộc tính ngoài ý muốn**.

Sau bài học, bạn có thể:

1. Giải thích chính xác vì sao client có thể thêm field vào request dù form HTML không có trường đó.
2. Phân biệt cơ chế **Spring WebDataBinder** của **@ModelAttribute** với Jackson deserialize JSON qua **@RequestBody**.
3. Tạo **input DTO** hẹp, dùng **allowedFields**, **declarativeBinding** hoặc constructor binding đúng chỗ.
4. Không nhầm **@Valid/Bean Validation** với field allowlist và authorization.
5. Ánh xạ dữ liệu cập nhật tường minh, giữ trường nhạy cảm do server quản lý.
6. Kiểm thử form, JSON, nested fields, unknown properties, ownership và nguy cơ PUT/PATCH.
7. Chạy ví dụ đầy đủ **Java 17 / Spring Boot 3.5 / Maven** và kiểm thử bằng MockMvc.

Bài thuộc nhóm **Dữ liệu yêu cầu** và tập trung vào **Spring MVC Servlet stack**. Nguyên tắc thiết kế tương tự được áp dụng cho **Spring WebFlux**, nhưng các reader của JSON và form có chi tiết triển khai khác.

## 2. Một request độc hại có thể làm gì?

Giả sử entity tài khoản có các trường:

~~~java
public class Account {
    private Long id;
    private Long ownerId;
    private String displayName;
    private String bio;
    private boolean admin;
    private String approvalStatus;

    // Các setter/getter khác của entity.
}
~~~

Đây là sơ đồ Java minh họa, chưa phải class chạy độc lập. Một controller sai về thiết kế có thể nhận ngay domain object:

~~~java
// Mẫu KHÔNG AN TOÀN: bind dữ liệu client vào entity có field nhạy cảm.
@PostMapping("/accounts/{id}")
public Account update(@PathVariable Long id,
                      @ModelAttribute Account account) {
    return accountRepository.save(account);
}
~~~

Client có thể gửi:

~~~http
POST /accounts/42
Content-Type: application/x-www-form-urlencoded

displayName=An&bio=Xin+chao&admin=true&ownerId=1&approvalStatus=APPROVED
~~~

Nếu data binder có thể thiết lập các property này và logic lưu chấp nhận, **admin** và **ownerId** có thể bị thay đổi. Giao diện không có input admin **không ngăn được** client gửi tên trường đó.

Với JSON cũng có rủi ro tương tự:

~~~json
{
  "displayName": "An",
  "bio": "Xin chào",
  "admin": true,
  "ownerId": 1,
  "approvalStatus": "APPROVED"
}
~~~

Nếu server dùng **@RequestBody Account** và cập nhật toàn bộ entity, Jackson có thể đưa những property JSON hợp lệ vào object. Có thêm **@Valid** không ngăn giá trị **admin=true** nếu giá trị Boolean đó hợp lệ về mặt kiểu dữ liệu.

### 2.1. Phân biệt bốn lớp bảo vệ

| Vấn đề | Câu hỏi | Giải pháp |
|---|---|---|
| **Field selection** | Client được phép đề xuất thay đổi trường nào? | Input DTO/allowlist |
| **Value validation** | Giá trị trường được phép có hợp lệ? | Bean Validation và nghiệp vụ |
| **Object authorization** | Người gọi có quyền sửa bản ghi này? | Principal, tenant, owner, ACL |
| **Persistence mapping** | Những field nào thật sự được cập nhật? | Explicit mapping, service layer |

Ví dụ một DTO chỉ có displayName/bio có thể ngăn việc đổi role, nhưng nếu user A được phép gửi ID của user B và service không kiểm tra owner thì vẫn tồn tại lỗi **BOLA/IDOR**. Ngược lại, đã đăng nhập không đồng nghĩa với quyền sửa trạng thái duyệt hay vai trò quản trị.

## 3. Hai cơ chế binding quan trọng của Spring

### 3.1. @ModelAttribute: bind form/query bằng WebDataBinder

Spring MVC có thể tạo model object và bind request parameter qua **WebDataBinder**:

~~~java
@PostMapping("/profiles/form")
public String update(@ModelAttribute ProfileForm form) {
    return form.getDisplayName();
}
~~~

Ở đây **@ModelAttribute** có thể nhận form fields, query parameter và một số giá trị liên quan từ path/header tùy cơ chế argument resolution. WebDataBinder hỗ trợ conversion, formatting, validation và cả **constructor binding** lẫn **property/setter binding**.

Với đối tượng có nhiều setter, cơ chế property binding có thể chấp nhận nhiều field hơn lập trình viên mong muốn. Spring Framework khuyên sử dụng **model object chuyên biệt**, **constructor binding**, hoặc khi vẫn cần property binding thì khai báo **allowedFields**.

### 3.2. @RequestBody: deserialize JSON qua Jackson

~~~java
@PostMapping("/profiles/json")
public void update(@RequestBody UpdateProfileJson request) {
    // ...
}
~~~

Trong Spring MVC, **@RequestBody** được đọc bởi **HttpMessageConverter**, thông thường dùng Jackson cho application/json. Jackson tạo DTO dựa vào constructor, properties và cấu hình JSON.

**Cảnh báo:** thiết lập **WebDataBinder.setAllowedFields("displayName","bio")** không trực tiếp lọc các JSON property mà Jackson deserialize từ **@RequestBody**. Với JSON, lớp bảo vệ quan trọng là **DTO hẹp + explicit mapping**, có thể kết hợp cấu hình Jackson từ chối unknown properties.

### 3.3. Chọn cách bảo vệ tương ứng

| Nguồn | Đường xử lý | Ràng buộc nên dùng |
|---|---|---|
| HTML form URL encoded | @ModelAttribute/WebDataBinder | DTO, allowedFields, declarativeBinding |
| Query form-like | @RequestParam hoặc @ModelAttribute | Khai báo tham số/DTO rõ, validate |
| Path ID | @PathVariable | Kiểm tra đúng resource và authorization |
| JSON object | @RequestBody/Jackson | DTO hẹp, strict unknown policy khi phù hợp, explicit mapping |
| Multipart fields | @ModelAttribute hoặc @RequestPart | DTO, field allowlist, giới hạn số part/file |
| WebFlux form | Reactive model binder | Dedicated DTO, @InitBinder |
| WebFlux JSON | Reactive HttpMessageReader/codecs | Dedicated DTO, explicit mapping |

Đừng dùng cùng một object làm **database entity, input command, response DTO và security principal**.

## 4. Biện pháp mặc định: Input DTO hẹp

Nếu domain model có:

~~~java
public record Profile(
        long id,
        long ownerId,
        boolean admin,
        String displayName,
        String bio) {
}
~~~

thì DTO cập nhật hồ sơ cá nhân chỉ nên có:

~~~java
public record UpdateProfileRequest(
        String displayName,
        String bio) {
}
~~~

Điều này có nghĩa client không thể gửi **ownerId** hoặc **admin** dưới dạng property mà DTO biết cách lưu. Trong service, cập nhật có chủ đích:

~~~java
Profile updated = new Profile(
        existing.id(),
        existing.ownerId(),
        existing.admin(),
        request.displayName(),
        request.bio());
~~~

Đây là đoạn mã minh họa; **existing** phải được truy xuất từ dữ liệu server và đã kiểm tra quyền, không phải object tạo từ request.

Với JPA entity, thường tốt hơn:

~~~java
existing.setDisplayName(request.displayName());
existing.setBio(request.bio());
~~~

Không sao chép mù quáng:

~~~java
// Không nên dùng khi source có thể chứa property ngoài hợp đồng.
BeanUtils.copyProperties(request, existing);
~~~

**BeanUtils.copyProperties** không mặc nhiên luôn là lỗ hổng, nhưng việc sao chép toàn bộ property trùng tên từ request sang entity dễ khiến field mới trở thành writable mà không qua code review. Nếu dùng mapper tự động, phải thiết lập cơ chế **allowlist field** rõ ràng và kiểm thử khi domain đổi schema.

### 4.1. DTO theo từng chức năng

Một tài khoản có thể có nhiều command tách biệt:

- **RegisterAccountRequest**: email, mật khẩu, tên ban đầu; không có role quản trị.
- **UpdateProfileRequest**: displayName, bio, avatar nếu có quy định.
- **ChangePasswordRequest**: currentPassword, newPassword.
- **AdminChangeRoleRequest**: targetId, role; chỉ endpoint quản trị được phép gọi.
- **AccountResponse**: các field được phép hiển thị; không serialize entity nguyên trạng.

Một DTO “AccountRequest” chứa mọi trường cho mọi nghiệp vụ rất khó kiểm soát quyền.

## 5. @InitBinder và allowedFields cho form

Với form model attribute tên **profileForm**:

~~~java
@InitBinder("profileForm")
public void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
~~~

Import:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
~~~

**setAllowedFields** chỉ cho phép property name nằm trong tập được khai báo. Danh sách này **phân biệt chữ hoa/chữ thường** và có thể áp dụng với property paths lồng nhau.

Ví dụ nếu form thực sự được phép thay địa chỉ:

~~~java
binder.setAllowedFields(
        "displayName",
        "shippingAddress.city",
        "shippingAddress.postalCode");
~~~

Không mở rộng thành **shippingAddress.\*** nếu object nested còn chứa trường bảo mật, và tránh **setAllowedFields("*")** vì nó gần như loại bỏ tác dụng của allowlist.

### 5.1. Vì sao allowedFields tốt hơn disallowedFields?

Blacklist:

~~~java
binder.setDisallowedFields("admin", "role", "ownerId");
~~~

yêu cầu nhớ tất cả field nhạy cảm, kể cả field sẽ được bổ sung trong tương lai. Nếu có trường mới **isVerified** hoặc **tenantId**, blacklist cũ có thể thiếu. Một số bản Spring Framework còn từng có lỗi bảo mật với cách kiểm tra tên **disallowedFields**, nên duy trì bản vá và ưu tiên whitelist là lựa chọn tốt hơn.

### 5.2. declarativeBinding trong Spring Framework 6.1+

Có thể dùng:

~~~java
@InitBinder("profileForm")
public void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "bio");
}
~~~

Khi **declarativeBinding=true**, framework vẫn thực hiện **constructor binding**, nhưng chỉ cho phép **property/setter binding** khi có cấu hình allowedFields. Nếu chỉ dùng declarativeBinding mà không có allowedFields, setter binding không được mở rộng.

**Chú ý:** constructor binding vẫn có thể nhận các tham số constructor. Nếu DTO record có cả **admin**, **role**, **ownerId**, việc đặt declarativeBinding không khiến những constructor argument đó biến mất. DTO phải được thiết kế đúng.

### 5.3. BindingResult và suppressed fields

Các property không nằm trong danh sách có thể được ghi vào **BindingResult.getSuppressedFields()**.

~~~java
@PostMapping("/profiles/form")
public ResponseEntity<Void> update(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {

    if (result.hasErrors()
            || result.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.noContent().build();
}
~~~

Đây là đoạn minh họa; class ProfileForm và import nằm ở phần demo hoàn chỉnh bên dưới.

Bắt suppressed fields và trả 400 có ích khi muốn **từ chối request có field ngoài hợp đồng**, thay vì âm thầm bỏ qua. Tuy nhiên, không có suppressed fields **không chứng minh** toàn request đã an toàn; cần DTO đúng, validation và authorization. Không log giá trị nhạy cảm của trường bị chặn.

### 5.4. Cấu hình global qua @ControllerAdvice

Nếu tổ chức thống nhất chỉ cho phép property binding khi khai báo tường minh, có thể đặt:

~~~java
@ControllerAdvice
public class BindingPolicy {
    @InitBinder
    public void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

Cấu hình này áp dụng rộng hơn và có thể làm hỏng các form cũ dựa vào setter binding. Hãy kiểm thử từng controller khi migration. Với endpoint cần setter, khai báo **allowedFields** tương ứng ở binder thuộc phạm vi đúng.

### 5.5. Nested và indexed properties

WebDataBinder hỗ trợ tên trường lồng nhau:

~~~text
address.city
roles[0].name
contacts[2].phone
preferences[marketing]
profile.admin
~~~

Với nested properties, phải ràng buộc cả **property path**, index/key và giới hạn kích thước collection. Việc nhận chỉ một property cấp cao như **address** hoặc **address.\*** có thể vô tình làm nhiều thuộc tính con trở nên writable.

Đừng tự cho rằng field HTML không được render thì nested property path không thể được gửi.

## 6. @Valid và Bean Validation không phải quyền ghi

Ví dụ DTO:

~~~java
public record UpdateProfileJson(
        @NotBlank @Size(max = 80) String displayName,
        @Size(max = 250) String bio) {
}
~~~

Với **jakarta.validation.Valid**, Spring MVC thường trả **HTTP 400** khi object không đạt validation. Validation phù hợp để kiểm tra:

- displayName không rỗng, không vượt 80 ký tự;
- bio không vượt 250 ký tự;
- email đúng định dạng;
- số tiền, ngày giờ và business constraints hợp lệ.

Nhưng **@Valid trên entity có trường admin vẫn cho phép admin=true** nếu Boolean hợp lệ. Validation **không quyết định client có quyền sửa trường admin hay không**.

Tương tự, chỉ kiểm tra **ownerId** request bằng @NotNull không khiến ownerId đáng tin. Owner/tenant phải được xác định hoặc kiểm tra dựa vào server-side identity.

## 7. JSON: unknown properties và strict deserialization

Spring Boot 3.x dùng Jackson trong Spring MVC. Jackson có thể được cấu hình để **bỏ qua JSON property không có trong DTO**, nên JSON lạ không nhất thiết bị lỗi.

Ví dụ client gửi:

~~~json
{
  "displayName": "Mai",
  "bio": "Giới thiệu",
  "admin": true,
  "ownerId": 3
}
~~~

Nếu target là record chỉ có **displayName** và **bio**, extra fields không thể trở thành domain admin/ownerId khi service chỉ map hai giá trị DTO. Nếu API muốn **từ chối field lạ**, trong **application.yml**:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Lúc này JSON thêm **admin** có thể dẫn tới lỗi parse/deserialize và HTTP 400. Đây là tính năng **optional** theo hợp đồng API, không thay thế bảo vệ nghiệp vụ. Cấu hình strict có thể ảnh hưởng backward compatibility khi client gửi extra field vốn trước đây bị bỏ qua.

**@JsonIgnore**, **@JsonProperty(access = READ_ONLY)**, Jackson views hay custom deserializers có tác dụng trong phạm vi serialize/deserialize, nhưng không nên dùng làm lớp phân quyền duy nhất. Quan trọng nhất vẫn là **DTO cho đúng thao tác và explicit mapping**.

## 8. Demo Spring Boot 3.5/Java 17 chạy được

Demo dùng **Spring Boot 3.5.16** trên Maven Central, Java 17 và **spring-boot-starter-web**. Boot 3.5 là nhánh cũ phục vụ mục đích học; đối với production hãy chọn phiên bản còn được hỗ trợ và được cập nhật bảo mật.

Yêu cầu nghiệp vụ: một hồ sơ có **id=1**, **ownerId=9001**, **admin=false**, tên **An** và bio ban đầu. Client chỉ được đề xuất sửa **displayName** và **bio**. Server phải không nhận việc sửa **ownerId** hoặc **admin** qua endpoint profile.

### 8.1. Cấu trúc

~~~text
safe-binding-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/safebinding/
    │   │   ├── SafeBindingApplication.java
    │   │   ├── ProfileService.java
    │   │   ├── ProfileForm.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/java/com/example/safebinding/
        └── ProfileSecurityTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-binding-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
~~~

**spring-boot-starter-validation** được khai báo riêng vì ví dụ dùng Jakarta Bean Validation.

### 8.3. SafeBindingApplication.java

~~~java
package com.example.safebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeBindingApplication.class, args);
    }
}
~~~

### 8.4. ProfileService.java

~~~java
package com.example.safebinding;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProfileService {

    private final Map<Long, Profile> profiles =
            new ConcurrentHashMap<>();

    public ProfileService() {
        profiles.put(1L,
                new Profile(1L, 9001L, false, "An", "Giới thiệu"));
    }

    public Profile find(long id) {
        Profile p = profiles.get(id);
        if (p == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found");
        }
        return p;
    }

    public Profile update(long id, String name, String bio) {
        Profile p = profiles.computeIfPresent(id, (key, old) ->
                new Profile(
                        old.id(),
                        old.ownerId(),
                        old.admin(),
                        name,
                        bio));
        if (p == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found");
        }
        return p;
    }

    public record Profile(
            long id,
            long ownerId,
            boolean admin,
            String displayName,
            String bio) {
    }
}
~~~

**Điểm an toàn:** method update chỉ nhận tên và bio. Trong nhánh update, **id/ownerId/admin** luôn lấy từ **old** (server-side state), không lấy từ input. Demo dùng ConcurrentHashMap để có thể chạy độc lập không cần database; không thay thế transaction, locking và authorization thực tế.

### 8.5. ProfileForm.java

~~~java
package com.example.safebinding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @Size(max = 250)
    private String bio;

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
}
~~~

DTO form chỉ có hai writable properties. **Không đưa entity có admin hoặc ownerId vào @ModelAttribute**. Dù chỉ có hai field, controller vẫn dùng allowedFields để làm rõ hợp đồng và phòng ngừa trường hợp DTO được mở rộng sau này.

### 8.6. ProfileController.java

~~~java
package com.example.safebinding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("profileForm")
    public void initForm(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "bio");
    }

    @GetMapping("/{id}")
    public ProfileView find(@PathVariable long id) {
        return view(service.find(id));
    }

    @PostMapping(
            path = "/{id}/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ProfileView updateForm(
            @PathVariable long id,
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid form");
        }

        return view(service.update(
                id, form.getDisplayName(), form.getBio()));
    }

    @PostMapping(
            path = "/{id}/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ProfileView updateJson(
            @PathVariable long id,
            @Valid @RequestBody UpdateProfileJson input) {
        return view(service.update(
                id, input.displayName(), input.bio()));
    }

    private ProfileView view(ProfileService.Profile profile) {
        return new ProfileView(
                profile.id(), profile.displayName(), profile.bio());
    }

    public record UpdateProfileJson(
            @NotBlank @Size(max = 80) String displayName,
            @Size(max = 250) String bio) {
    }

    public record ProfileView(
            long id,
            String displayName,
            String bio) {
    }
}
~~~

**Điểm cần đọc kỹ:**

- **@InitBinder("profileForm")** chỉ cấu hình cho model attribute tên profileForm.
- **setDeclarativeBinding(true)** và **setAllowedFields** ràng buộc setter binding của form.
- **BindingResult** nằm ngay sau tham số @Valid @ModelAttribute, nên controller kiểm tra validation và suppressed fields.
- JSON dùng record **UpdateProfileJson**, không có admin hoặc ownerId.
- **ProfileService.update** chỉ cập nhật hai thuộc tính editable.
- **ProfileView** không tự trả những field quản trị trong response.

### 8.7. application.yml

~~~yaml
server:
  port: 8080

spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Khi bật strict JSON, client gửi property chưa khai báo trong **UpdateProfileJson** thường bị từ chối với HTTP 400. Đây là cấu hình **Jackson**, không phải WebDataBinder.

### 8.8. Chạy và kiểm tra

Tại thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Đọc profile khởi tạo:

~~~bash
curl -i "http://localhost:8080/api/profiles/1"
~~~

Mong đợi HTTP 200 và JSON:

~~~json
{"id":1,"displayName":"An","bio":"Giới thiệu"}
~~~

**Form hợp lệ:**

~~~bash
curl -i \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Bình" \
  --data-urlencode "bio=Học Spring" \
  "http://localhost:8080/api/profiles/1/form"
~~~

Mong đợi HTTP 200:

~~~json
{"id":1,"displayName":"Bình","bio":"Học Spring"}
~~~

**Form gửi thêm trường không được phép:**

~~~bash
curl -i \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Mai" \
  --data-urlencode "bio=Thử nghiệm" \
  --data-urlencode "admin=true" \
  --data-urlencode "ownerId=1" \
  "http://localhost:8080/api/profiles/1/form"
~~~

Mong đợi **HTTP 400** vì các field ngoài allowedFields bị suppressed và controller từ chối request. Điều này **không thay đổi** admin hay ownerId trong ProfileService.

**JSON hợp lệ:**

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary '{"displayName":"Hà","bio":"JSON"}' \
  "http://localhost:8080/api/profiles/1/json"
~~~

Mong đợi HTTP 200:

~~~json
{"id":1,"displayName":"Hà","bio":"JSON"}
~~~

**JSON gửi thêm admin:**

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary '{"displayName":"Mai","bio":"JSON","admin":true}' \
  "http://localhost:8080/api/profiles/1/json"
~~~

Mong đợi **HTTP 400** vì strict unknown properties được bật. Nếu không bật strict, field ngoài DTO có thể bị Jackson bỏ qua; dù vậy service không map admin từ input.

Các lệnh trên dùng Bash. Trên PowerShell, dùng **curl.exe** và cân nhắc file JSON UTF-8 để tránh lỗi escaping.

## 9. Kiểm thử tự động bằng MockMvc

Tạo file **src/test/java/com/example/safebinding/ProfileSecurityTest.java**:

~~~java
package com.example.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileSecurityTest {

    @Autowired MockMvc mvc;
    @Autowired ProfileService service;

    @Test
    void formAllowsOnlyEditableFields() throws Exception {
        mvc.perform(post("/api/profiles/1/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Bình")
                .param("bio", "Học Spring"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Bình"));

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void extraFormFieldsAreRejected() throws Exception {
        mvc.perform(post("/api/profiles/1/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Mai")
                .param("bio", "Thử nghiệm")
                .param("admin", "true")
                .param("ownerId", "1"))
            .andExpect(status().isBadRequest());

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void jsonAllowsOnlyEditableFields() throws Exception {
        mvc.perform(post("/api/profiles/1/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Hà\",\"bio\":\"JSON\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Hà"));

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void extraJsonFieldsAreRejected() throws Exception {
        mvc.perform(post("/api/profiles/1/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Mai\",\"bio\":\"JSON\","
                        + "\"admin\":true,\"ownerId\":1}"))
            .andExpect(status().isBadRequest());

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void blankDisplayNameFailsValidation() throws Exception {
        mvc.perform(post("/api/profiles/1/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"  \",\"bio\":\"test\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingResourceIs404() throws Exception {
        mvc.perform(get("/api/profiles/999"))
            .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Khi các test thành công, Maven kết thúc với exit code **0**; log cụ thể phụ thuộc version Surefire.

Bộ test xác minh cả hai hợp đồng input và **server-side state**. Kiểm tra **admin=false** và **ownerId=9001** từ ProfileService quan trọng hơn việc chỉ thấy response không có các trường đó.

**Giới hạn demo:** chưa có authentication và kiểm tra quyền trên profile ID. Do vậy bộ test **không chứng minh** ngăn người dùng A cập nhật profile B; chức năng đó phải được bổ sung trong ứng dụng thực.

## 10. Phân quyền theo người gọi và resource

Ngăn mass assignment khác với ngăn IDOR/BOLA. Client có thể không sửa được admin nhưng vẫn gửi:

~~~http
POST /api/profiles/987/json
Content-Type: application/json

{"displayName":"Thay tên người khác","bio":"..."}
~~~

Nếu service chỉ tìm id=987 và cập nhật mà không kiểm tra principal thì vẫn thiếu authorization.

Thiết kế production đúng gồm:

1. Xác thực người gọi và lấy user/tenant identity từ **security context đáng tin cậy**.
2. Tải resource từ database theo id.
3. Kiểm tra principal có quyền **edit** resource này, hoặc có quyền quản trị hợp lệ.
4. Validate business invariants sau khi field input được giới hạn.
5. Chỉ cập nhật các thuộc tính được phép, trong transaction phù hợp.
6. Ghi audit cho thay đổi nhạy cảm mà không log mật khẩu hoặc raw token.

Ví dụ **đoạn mô tả mã**, không phải class biên dịch độc lập:

~~~java
Profile entity = repository.findById(id)
        .orElseThrow(() -> new ResourceNotFoundException());

authorization.requireCanEdit(currentPrincipal, entity);

entity.setDisplayName(request.displayName());
entity.setBio(request.bio());

repository.save(entity);
~~~

Owner/tenant/role của entity phải đến từ dữ liệu server. **Không** coi ownerId được gửi từ client là bằng chứng quyền sở hữu. Với chức năng đổi role hoặc approval status, tạo **command/endpoint riêng** với quyền admin, review và audit cụ thể. Ứng dụng browser dùng session cookie còn phải xem xét **CSRF protection** cho các request thay đổi trạng thái.

## 11. Constructor binding và record

Trong Spring MVC hiện đại, **@ModelAttribute** có thể dùng constructor binding. Một input record:

~~~java
public record ChangeAddressForm(
        String city,
        String postalCode) {
}
~~~

chỉ có hai constructor parameters, vì vậy không có tham số tên admin để bind. Khi kết hợp **setDeclarativeBinding(true)**, Spring có thể sử dụng constructor binding mà không mở setter binding mặc định.

Tuy nhiên, một record sau vẫn không an toàn nếu client không được cấp quyền đổi role:

~~~java
public record UnsafeAccountInput(
        String city,
        boolean admin) {
}
~~~

Constructor binding **không tự lọc** tham số constructor. Chính thiết kế DTO quyết định field được chấp nhận. Đối với legacy entity có nhiều setter/nested properties, dùng DTO trung gian hoặc allowedFields, không hy vọng constructor binding “tự bỏ” trường nhạy cảm.

## 12. PUT/PATCH và phân biệt absent – null

Mass assignment còn xảy ra ở endpoint update từng phần. Nếu API dùng JSON PATCH tùy ý và lặp qua mọi key trong Map<String,Object> để set vào entity, client có thể chọn **role**, **ownerId** hoặc nested property ngoài hợp đồng.

Với PATCH cần phân biệt:

- **Không gửi trường**: thường giữ nguyên giá trị.
- **Gửi trường với null**: có thể muốn xóa giá trị, tùy hợp đồng.
- **Gửi giá trị cụ thể**: cập nhật nếu field đó có quyền ghi.

Một DTO nullable thông thường đôi khi không phân biệt được hai trường hợp đầu. Hãy dùng patch command có field presence hoặc JSON Merge Patch/JSON Patch theo hợp đồng được kiểm soát, và kiểm tra allowlist đối với **mọi JSON path**. Không dùng generic reflection setter cho các key từ client.

Với PUT, nên quyết định rõ liệu thiếu field có xóa giá trị cũ không; không tự copy null từ DTO sang entity làm mất thông tin nhạy cảm hoặc dữ liệu khác.

## 13. Spring WebFlux: ranh giới tương tự

Trong Spring WebFlux:

- **@ModelAttribute** vẫn sử dụng data binder cho form/query/model object; có thể cấu hình **@InitBinder**, DTO, constructor binding và allowedFields.
- **@RequestBody Mono<Dto>** dùng reactive **HttpMessageReader/codec** cho JSON; không bị lọc JSON fields bởi setAllowedFields của WebDataBinder.
- **RouterFunction/ServerRequest** cần thiết kế bind/deserialize theo command rõ ràng và kiểm soát mapping.

Đoạn minh họa không độc lập biên dịch nếu chưa có reactive service:

~~~java
@PostMapping("/api/profiles/{id}")
public Mono<ProfileView> update(
        @PathVariable long id,
        @Valid @RequestBody Mono<UpdateProfileRequest> input) {

    return input.flatMap(dto ->
            service.updateEditableFields(
                    id, dto.displayName(), dto.bio()));
}
~~~

Trong WebFlux, việc dùng Mono không thay thế DTO allowlist hay authorization. Nếu nhận body quá lớn, còn cần giới hạn codec memory và HTTP payload size; đó là bài toán riêng ngoài mass assignment.

## 14. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân | Biện pháp |
|---|---|---|
| Client thêm admin=true vào form và đổi role | Bind entity trực tiếp | DTO, allowedFields, mapping tường minh |
| Đã dùng allowedFields nhưng JSON vẫn bind admin | Jackson @RequestBody, không theo WebDataBinder allowlist | DTO JSON riêng và strict policy |
| @Valid vẫn không chặn admin=true | Validation không bảo vệ field access | Field selection + authorization |
| JSON unknown field không trả 400 | Boot/Jackson mặc định bỏ qua field lạ | Bật strict khi hợp đồng cho phép |
| Nested field thay đổi state ẩn | Form bind nested property path | Allowlist property path hẹp |
| Input từ PUT làm mất field cũ | Sao chép null hoặc replace toàn entity | Quy định update semantics |
| User sửa hồ sơ người khác | Service thiếu quyền theo resource | Authorization theo principal + owner |
| Role đổi mà không audit | Dùng endpoint profile update chung | Endpoint quản trị riêng, audit |
| Global declarativeBinding làm form cũ rỗng | Setter binding trước đây ngầm hoạt động | Migration và allowedFields rõ ràng |
| DTO hẹp nhưng mapper vẫn đổi cột lạ | Mapper có convention ghi trường nhạy cảm | Explicit mapping + test data state |
| Input lớn gây tăng memory | Không giới hạn request hoặc collection | Limit size, nested depth, rate |
| Field suppressed không được báo | Binder bỏ qua field ngoài allowlist | Kiểm tra BindingResult.getSuppressedFields |

### 14.1. Logging và giám sát

- Ghi nhận request bị từ chối do unknown/suppressed fields ở mức đủ để điều tra, nhưng không log giá trị password/token.
- Ghi correlation ID, endpoint và loại vi phạm; không để lộ tên class nội bộ/stack trace cho client.
- Cảnh báo nếu nhiều request cố thêm property có tên quyền hạn hoặc nested path bất thường.
- Mỗi lần thêm field vào entity/DTO, bổ sung test không cho thay đổi property ngoài hợp đồng.

## 15. Checklist code review

- [ ] Không bind trực tiếp entity/domain object nhiều trường nhạy cảm từ request.
- [ ] Có input DTO riêng cho mỗi thao tác.
- [ ] @ModelAttribute có allowedFields khi cần setter/property binding.
- [ ] Có thể dùng setDeclarativeBinding(true) để hạn chế property binding ngầm định.
- [ ] Không dựa duy nhất vào disallowedFields/blacklist.
- [ ] JSON @RequestBody chỉ nhận DTO được phép; unknown-properties policy rõ ràng.
- [ ] @Valid dùng cho dữ liệu, không thay authorization.
- [ ] Service chỉ update explicit fields, không copy tất cả.
- [ ] Owner/tenant/role/status lấy từ server hoặc command được cấp quyền riêng.
- [ ] PATCH xử lý absent/null và property path có chủ đích.
- [ ] Kiểm soát nested paths, collection index, kích thước dữ liệu và upload.
- [ ] Test form thêm admin/ownerId; test JSON thêm field lạ.
- [ ] Test trạng thái entity thực tế sau update, không chỉ response.
- [ ] Test quyền sửa resource của user/tenant trong ứng dụng production.
- [ ] Duy trì bản vá Spring Framework, Jackson và dependencies.

## 16. Tài liệu chính thức

1. Spring Framework 6.2 – Spring MVC **@InitBinder** và model design: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
2. Spring Framework 6.2 – **@ModelAttribute** method arguments: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
3. Spring Framework – MVC Data Binding, property paths: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
4. Spring Framework – **@RequestBody** qua HttpMessageConverter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
5. Spring Framework 6.2 – WebFlux **@InitBinder**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
6. Spring Framework 6.2 – WebFlux **@RequestBody**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html
7. Spring Boot 3.5 – Common Application Properties, Jackson deserialization: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
8. Spring Security – Method Security/Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
9. Spring Framework security advisory **CVE-2025-22233** (liên quan disallowedFields): https://spring.io/security/cve-2025-22233/
10. Spring Boot 3.5.16 chính thức: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

## 17. Tổng kết

Phòng chống **mass assignment** đòi hỏi xác định chính xác **client được phép gửi và sửa thuộc tính nào**. Trong Spring MVC, **@ModelAttribute** cần DTO hẹp, allowedFields/declarativeBinding khi dùng setter binding; còn **@RequestBody** JSON phải được bảo vệ bằng DTO, Jackson policy phù hợp và explicit mapping ở service.

**@Valid chỉ kiểm tra dữ liệu, không cấp quyền.** Những field như **id, ownerId, tenantId, admin, role, balance, approvalStatus** phải do server quyết định hoặc chỉ thay đổi qua endpoint có authorization riêng. Khi kiểm thử, luôn gửi thêm property ngoài hợp đồng và kiểm tra **dữ liệu đang lưu ở server** để chắc chắn không có thay đổi ngoài ý muốn.
