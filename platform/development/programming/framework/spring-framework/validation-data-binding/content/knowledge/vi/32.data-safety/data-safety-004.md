# Ngăn sửa id, vai trò, chủ sở hữu và trạng thái do server quản lý

## Mục tiêu

Trong Spring MVC, data binding và JSON deserialization giúp chuyển HTTP request thành object Java. Nếu nhận trực tiếp entity có các thuộc tính như `id`, `role`, `ownerId` và `status`, client có thể tự thêm tham số ngoài giao diện để yêu cầu sửa những thuộc tính do server quản lý. Đây là **mass assignment / over-posting** (CWE-915). Một lỗ hổng liên quan là **IDOR/BOLA**: người gửi thay ID trên URL để tác động đến tài nguyên của người khác.

Bài thuộc nhóm **An toàn dữ liệu** và tập trung vào bốn nguyên tắc:

1. Chỉ nhận những **thuộc tính được phép sửa** vào input DTO.
2. Với Spring MVC `@ModelAttribute`, giới hạn binding bằng `WebDataBinder` khi cần; với JSON `@RequestBody`, phải kiểm soát riêng Jackson.
3. Xác định principal đã xác thực, kiểm tra ownership/tenant và quyền tại service, bất kể body gửi gì.
4. Giữ `id`, `role`, `owner`, `status` từ dữ liệu server hiện tại và chỉ thay đổi chúng qua workflow riêng có quyền, audit và transaction phù hợp.

Bạn sẽ làm một ví dụ Java 17+ / Spring Boot 3.5.7 có cả form và JSON, Spring Security, `@Valid`, `setAllowedFields`, `setDeclarativeBinding`, kiểm tra ID theo principal và bộ MockMvc tests xác minh dữ liệu không bị thay đổi.

## 1. Tấn công mass assignment diễn ra như thế nào?

Frontend chỉ hiển thị hai ô nhập:

~~~text
Tên hiển thị: [Alice]
Tiểu sử:      [Developer]
                  [Lưu]
~~~

Nhưng entity trên server có:

~~~java
public class AccountEntity {
    private Long id;
    private String ownerUsername;
    private String role;
    private String status;
    private String displayName;
    private String bio;

    // getters, setters, quan hệ và logic khác...
}
~~~

Nếu controller bind trực tiếp entity:

~~~java
@PostMapping("/accounts/edit")
String edit(@ModelAttribute AccountEntity account) {
    repository.save(account);
    return "redirect:/accounts";
}
~~~

thì client có thể tự gửi:

~~~http
POST /accounts/edit
Content-Type: application/x-www-form-urlencoded

id=202&ownerUsername=bob&role=ADMIN&status=ACTIVE&displayName=Alice&bio=Hello
~~~

`@ModelAttribute` với property binding có thể gán tên request parameter trùng JavaBean property, kể cả field không nằm trên HTML. Nếu sau đó lưu mà không có chính sách, server có thể vô tình cho phép đổi ID, chủ sở hữu, vai trò hoặc trạng thái.

Tương tự với JSON:

~~~http
PUT /api/accounts/101
Content-Type: application/json

{
  "displayName": "Alice",
  "bio": "Hello",
  "id": 202,
  "role": "ADMIN",
  "ownerUsername": "bob",
  "status": "ACTIVE"
}
~~~

Nếu `@RequestBody` deserialize vào entity rộng và service copy mọi field, đây là over-posting. **UI không phải security boundary:** hidden/disabled fields, frontend validation hoặc việc “không có nút sửa role” đều không ngăn được HTTP request tự tạo.

### Bốn thuộc tính do server quyết định

| Field | Ý nghĩa | Nguồn tin cậy | Nguy cơ khi client được tùy ý sửa |
| --- | --- | --- | --- |
| `id` | Danh tính bản ghi | Database hoặc ID trong URL được xác thực quyền | Đổi bản ghi, cập nhật nhầm, identity confusion |
| `role` | Quyền hoặc membership | Security store / admin workflow | Tự nâng quyền thành ADMIN |
| `ownerId` / `ownerUsername` | Chủ sở hữu/tenant | Authenticated principal và domain data | Chiếm quyền, chuyển tài nguyên sang user khác |
| `status` | Trạng thái vòng đời | Domain state machine | Tự phê duyệt, mở khóa, bỏ qua quy trình |

Một thuộc tính có thể được phép thay đổi trong endpoint khác, ví dụ role qua thao tác admin hoặc status qua quy trình phê duyệt. Điều cần ngăn là **việc thay đổi không đúng quyền hoặc ngoài command được phép**, không phải cấm tuyệt đối mọi thay đổi.

## 2. Phân biệt binding, validation và authorization

Ba câu hỏi không giống nhau:

- **Binding:** “Request có thể đặt giá trị vào property này không?”
- **Bean Validation:** “Giá trị có đúng quy tắc kiểu/độ dài/format hay không?”
- **Authorization:** “Người này có quyền thực hiện hành động đó trên bản ghi đó hay không?”

Ví dụ:

~~~java
class ProfileRequest {
    @NotBlank
    String displayName;

    @NotNull
    Role role;
}
~~~

JSON `{"displayName":"Alice","role":"ADMIN"}` có thể **đạt** `@NotBlank` và `@NotNull`, dù người gửi hoàn toàn không có quyền tự chọn role. Vì vậy **`@Valid` không phải là phân quyền**.

Chuỗi trách nhiệm logic:

~~~text
Client-controlled HTTP input
       |
       +-- @ModelAttribute → WebDataBinder
       |                    (form/query/path/header)
       |
       +-- @RequestBody    → Jackson
       |                    (JSON)
       v
DTO chỉ chứa editable fields
       |
       v
@Valid / @Validated: syntax, size, format
       |
       v
Authenticated Principal / SecurityContext
       |
       v
Service: kiểm tra resource owner / tenant / action
       |
       v
Domain: kiểm tra current status và transition
       |
       v
Chỉ sửa những field được chỉ định
       |
       v
Transaction / concurrency / audit
~~~

Trong thực tế security filters thường xác thực trước khi MVC đọc body. Sơ đồ này chỉ mô tả **các trách nhiệm**, không cố mô tả thứ tự middleware cố định.

## 3. Đầu vào riêng và đầu ra riêng

### 3.1. Dùng DTO chỉ có field được sửa

Thay vì nhận `AccountEntity`, định nghĩa:

~~~java
public record EditProfileRequest(
        @NotBlank String displayName,
        @Size(max = 200) String bio) {
}
~~~

Đây là snippet với `jakarta.validation.constraints.*`. DTO **không có** `id`, `role`, `ownerUsername` hoặc `status`.

Bạn có thể có nhiều command cho nhiều use case:

~~~text
RegisterAccountRequest:    email, password, displayName
EditOwnProfileRequest:     displayName, bio
ChangePasswordRequest:     oldPassword, newPassword
AdminChangeRoleRequest:    targetId, newRole, reason
ApproveApplicationCommand: applicationId, decision, justification
~~~

Chúng không nên được gộp chỉ để tránh tạo thêm một class. Input contract thể hiện **quyền ghi** của từng endpoint; response model thể hiện **những gì được phép đọc**.

### 3.2. Response có trường không có nghĩa input được sửa

Một response của chính người dùng có thể là:

~~~json
{
  "id": 101,
  "ownerUsername": "alice",
  "role": "USER",
  "status": "ACTIVE",
  "displayName": "Alice"
}
~~~

Server vẫn có thể chỉ cho input:

~~~json
{
  "displayName": "Alice Updated",
  "bio": "New bio"
}
~~~

Đừng dùng chung một class có tất cả getters/setters cho input và output chỉ vì JSON trông giống nhau.

### 3.3. Vì sao DTO mutable vẫn có thể an toàn?

Một mutable DTO chỉ có `setDisplayName` và `setBio` không cung cấp các property nhạy cảm để framework ghi. Khi API phát triển, review DTO mới là một phần của security review: **thêm setter mới cũng là mở rộng bề mặt input**.

Record/immutable constructor binding còn hữu ích hơn khi constructor chỉ nhận các trường được phép sửa. Nhưng **không** đặt `role` hoặc `owner` vào constructor của một request record rồi tin rằng constructor binding tự kiểm quyền.

## 4. Spring MVC: setAllowedFields và declarativeBinding

### 4.1. @ModelAttribute dùng WebDataBinder

Trong MVC, `@ModelAttribute` thường bind dữ liệu form/query vào object thông qua `WebDataBinder`. Nếu muốn giới hạn property binding:

~~~java
@InitBinder("editForm")
void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
~~~

`@InitBinder("editForm")` áp dụng cho model attribute có tên `editForm` trong controller. Đừng quên khớp tên với `@ModelAttribute("editForm")` ở handler.

`setAllowedFields` là **allowlist**: field không nằm trong danh sách không được setter/property binding nhận. Trái lại, `setDisallowedFields("id","role","owner","status")` là **blocklist**: sau này entity có thêm `isAdmin` hoặc `approvedAt`, list cũ dễ bỏ sót. Spring và OWASP đều khuyến nghị DTO hoặc allowlist rõ ràng thay vì chỉ disallowed fields.

### 4.2. setDeclarativeBinding(true) từ Spring 6.1

Spring Framework 6.1+ hỗ trợ:

~~~java
binder.setDeclarativeBinding(true);
~~~

Khi bật, constructor binding vẫn hoạt động theo các tham số constructor được công bố, còn setter/property binding chỉ hoạt động khi `allowedFields` được cấu hình. Với form mutable DTO:

~~~java
@InitBinder("editForm")
void configureBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "bio");
}
~~~

Điều này giúp giảm việc vô tình bind property không dự tính. Nhưng nếu DTO constructor khai báo `role` hay `ownerId`, các tham số constructor ấy **vẫn** có thể là đường nhận dữ liệu: thiết kế input object mới là phòng vệ cốt lõi.

Ở Spring 5.x/6.0, không có API `setDeclarativeBinding`: dùng DTO chuyên dụng và `setAllowedFields` theo phiên bản, hoặc nâng lên dòng có hỗ trợ.

### 4.3. Phát hiện field bị loại

`BindingResult.getSuppressedFields()` trả tên các field bị binder loại vì không phù hợp allowlist:

~~~java
@PostMapping("/me/form")
ResponseEntity<?> submit(
        @Valid @ModelAttribute("editForm") EditAccountInput form,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "UNEXPECTED_FIELD"));
    }

    // Kiểm tra errors.hasErrors() và quyền sở hữu ở service.
}
~~~

Đây là snippet rút gọn, code đầy đủ ở mục 8. Bạn có thể lựa chọn reject request có field extra để phát hiện thử over-posting. Đừng log giá trị nhạy cảm của field bị suppress; nếu cần audit, lưu tên field và request/correlation ID sau khi sanitization.

**Lưu ý:** `getSuppressedFields()` thuộc Spring data binder. Nó không kiểm tra những unknown JSON properties do Jackson đọc.

### 4.4. Nested paths và wildcards

Allowed fields hỗ trợ property paths:

~~~java
binder.setAllowedFields(
        "displayName",
        "contact.city",
        "contact.postalCode");
~~~

Với nested object, tránh wildcard rộng như `"members[*].*"` nếu object con có `role`, `ownerId` hoặc `approved`. Input có thể cố sử dụng:

~~~text
members[0].role=ADMIN
contact.ownerId=202
flags[approved]=true
~~~

Nested collections/maps cũng phải được thiết kế là DTO chỉ chứa writable fields. Nếu một map cho phép keys tự do, domain service cần ràng buộc tên và kiểu key/value theo nghiệp vụ.

## 5. JSON @RequestBody cần cơ chế riêng

`@RequestBody` thường dùng Jackson `HttpMessageConverter`, **không phải** WebDataBinder setter filtering của `@ModelAttribute`. Vì vậy thêm `@InitBinder` không tự ngăn JSON như `{"role":"ADMIN"}` nếu bạn vẫn nhận một object có field role.

Với DTO chỉ có `displayName`/`bio`, có thể yêu cầu Jackson từ chối unknown keys:

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

Trong ví dụ Spring Boot 3.5, Jackson sẽ báo lỗi khi client gửi thêm `id`, `role`, `ownerUsername` hoặc `status`, vì chúng không có property trên DTO. `HttpMessageNotReadableException` thường dẫn đến HTTP 400.

Cấu hình trên áp dụng cho Jackson mapper được Boot cấu hình, có thể ảnh hưởng các JSON endpoints khác; cân nhắc phạm vi và backward compatibility khi dùng production. Nếu chọn bỏ qua unknown keys thay vì từ chối, **vẫn phải bảo đảm không có đường copy unknown fields vào entity**.

`@JsonIgnore` hoặc `@JsonProperty(access = READ_ONLY)` có thể giúp kiểm soát JSON serialization/deserialization, nhưng không thay thế DTO, Spring MVC binder policy, authorization hoặc domain rules. Việc thêm một setter mới vào input DTO có thể khiến field không còn “unknown”.

## 6. IDOR và quyền sở hữu phải được kiểm tra tại service

### 6.1. ID trong URL không mang quyền

~~~http
PUT /api/accounts/202
Authorization: Bearer <verified-token>
Content-Type: application/json

{"displayName":"Changed","bio":"Text"}
~~~

Giả sử người gửi là `alice`, account `202` thuộc `bob`. DTO body hoàn toàn hợp lệ và không có field nhạy cảm, **nhưng request vẫn phải bị chặn**. Đó là lý do input DTO alone chưa đủ chống IDOR/BOLA.

Controller nên truyền user identity từ Spring Security:

~~~java
service.updateOwn(
        idFromPath,
        principal.getName(),
        input);
~~~

Service kiểm tra:

~~~java
Account account = repository.findById(id)
        .orElseThrow(AccountNotFoundException::new);

if (!account.getOwnerUsername()
        .equals(authenticatedUsername)) {
    throw new AccountNotFoundException();
}
~~~

Đây là snippet cần repository/domain classes, không chạy độc lập. Chọn HTTP 404 cho tài nguyên không thuộc người dùng có thể giảm khả năng dò ID; một số API chọn 403 theo contract. Điều quan trọng là **không cập nhật tài nguyên khi không có quyền**.

### 6.2. Principal phải đến từ nguồn tin cậy

Không tin `ownerUsername` trong request body, query, hidden form input hoặc header tự khai báo như `X-User-Id`. Principal phải là danh tính đã được security layer xác thực (session, HTTP Basic, JWT được kiểm chữ ký/issuer/audience/expiration, v.v.).

Để tránh lỗ hổng bỏ sót ở đường khác, ownership/tenant authorization nên được thực hiện tại service/domain boundary trước khi ghi, không chỉ trong controller. Nếu dùng method security `@PreAuthorize`, vẫn phải xác định scope đối tượng, không chỉ kiểm tra người dùng có một role bất kỳ.

### 6.3. Multi-tenant

Trong hệ thống có tenant, cần kiểm tra cả ID và tenant context đã xác thực:

~~~java
Optional<AccountEntity> findByIdAndTenantId(
        Long id, Long trustedTenantId);
~~~

Đây là chữ ký derived query Spring Data minh họa. Nếu tenantId nằm trên URL hoặc JSON, đó vẫn là input cần so với membership tin cậy từ server. Không dựa vào việc client tự chọn tenant mà cho truy vấn/ghi dữ liệu tenant đó.

## 7. Status và role là workflow riêng

### 7.1. Không cho profile edit sửa status

Một account `SUSPENDED` không thể tự gửi `{"status":"ACTIVE"}` để mở khóa. Với request hợp lệ chỉ có displayName, service vẫn phải kiểm tra trạng thái hiện tại và từ chối nếu tài khoản không được phép sửa.

### 7.2. State machine

Ví dụ:

~~~text
DRAFT --submit--> PENDING
PENDING --approve--> APPROVED
PENDING --reject--> REJECTED
APPROVED --archive--> ARCHIVED
~~~

Chuyển `PENDING → APPROVED` là một **domain action**, không phải property update ngẫu nhiên. Endpoint phê duyệt phải kiểm tra reviewer permissions, trạng thái ban đầu, lý do, transaction và audit.

### 7.3. Thay role qua admin workflow

Nếu admin được phép thay role, tạo endpoint/command riêng:

~~~java
record AdminChangeRoleRequest(
        String newRole,
        String reason) {
}
~~~

Sau đó xác minh authority admin từ security store, quyền trên tenant/target, chính sách không tự nâng quyền hoặc xóa admin cuối cùng nếu cần, ghi audit và cập nhật session/authority cache. Đừng thêm `role` vào `EditOwnProfileRequest` chỉ vì tái sử dụng code tiện hơn.

### 7.4. Tránh copyProperties toàn bộ

Không làm:

~~~java
BeanUtils.copyProperties(request, entity);
repository.save(entity);
~~~

khi request rộng hoặc property mapping không kiểm soát. Ưu tiên mapping tường minh:

~~~java
entity.setDisplayName(input.displayName());
entity.setBio(input.bio());
// Không setId, setRole, setOwner, setStatus.
~~~

Tương tự với MapStruct, một mapping có danh sách field được khai báo rõ và ignored-by-default sẽ dễ review hơn mapping mở. Không có mapper nào thay authorization.

## 8. Ví dụ chạy được: Spring Boot 3.5.7 / Java 17 / Spring MVC

Ứng dụng demo cung cấp hai cách sửa cùng một hồ sơ:

- `PUT /api/accounts/{id}` nhận JSON vào `EditAccountInput`.
- `POST /api/accounts/me/form` nhận form vào `@ModelAttribute("editForm")` có allowlist.
- `GET /api/accounts/{id}` chỉ đọc account của principal tương ứng.

Domain chứa bốn field server-managed `id`, `ownerUsername`, `role`, `status` và hai field editable `displayName`, `bio`. Account `charlie` ban đầu bị `SUSPENDED`. Dữ liệu nằm trong `ConcurrentHashMap` để ví dụ không yêu cầu database; production nên dùng repository/transaction.

### 8.1. Cấu trúc dự án

~~~text
safe-account-edit/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/safeedit/
    │   │   ├── Application.java
    │   │   ├── SecurityConfig.java
    │   │   ├── EditAccountInput.java
    │   │   ├── AccountView.java
    │   │   ├── AccountService.java
    │   │   ├── AccountNotFoundException.java
    │   │   ├── AccountLockedException.java
    │   │   ├── AccountController.java
    │   │   └── ApiErrors.java
    │   └── resources/application.properties
    └── test/java/com/example/safeedit/
        └── AccountSecurityTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>safe-account-edit</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

Spring Boot parent quản lý dependency versions; Spring Security test cung cấp `@WithMockUser` và `csrf()` cho MockMvc. Chọn Spring MVC/Servlet vì `WebDataBinder` với `@InitBinder` đang được minh họa.

### 8.3. Application.java

~~~java
package com.example.safeedit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

~~~java
package com.example.safeedit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());

        // Giữ CSRF bật theo mặc định.
        return http.build();
    }
}
~~~

Authentication là điều kiện cần; service vẫn phải kiểm tra owner và state của tài nguyên. HTTP Basic ở đây chỉ để minh họa cấu hình bảo vệ endpoint. Trong production cần identity provider/user store, HTTPS, token/session policy, security headers và audit đúng chuẩn. Không dùng user name từ request body để dựng `Principal`.

### 8.5. EditAccountInput.java

~~~java
package com.example.safeedit;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class EditAccountInput {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @Size(max = 200)
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

No-arg constructor mặc định đủ để Jackson và form binder tạo object. Đáng chú ý: **không có setter cho id, role, owner hoặc status**. `@NotBlank` và `@Size` chỉ kiểm tra dữ liệu được phép nhận, không phải quy tắc cấp quyền.

### 8.6. AccountView.java

~~~java
package com.example.safeedit;

public record AccountView(
        long id,
        String ownerUsername,
        String role,
        String status,
        String displayName,
        String bio) {
}
~~~

Đây là response DTO. Những field đọc được trong API response không đương nhiên xuất hiện trong input DTO.

### 8.7. AccountService.java

~~~java
package com.example.safeedit;

import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class AccountService {

    private record StoredAccount(
            long id,
            String ownerUsername,
            String role,
            String status,
            String displayName,
            String bio) {
    }

    private final Map<Long, StoredAccount> accounts =
            new ConcurrentHashMap<>();

    private final Map<String, Long> primaryIds = Map.of(
            "alice", 101L,
            "bob", 202L,
            "charlie", 303L);

    public AccountService() {
        accounts.put(101L, new StoredAccount(
                101L, "alice", "USER", "ACTIVE",
                "Alice", "Developer"));

        accounts.put(202L, new StoredAccount(
                202L, "bob", "USER", "ACTIVE",
                "Bob", "Designer"));

        accounts.put(303L, new StoredAccount(
                303L, "charlie", "USER", "SUSPENDED",
                "Charlie", "Editor"));
    }

    public AccountView getOwn(
            long id, String authenticatedUsername) {

        StoredAccount stored = accounts.get(id);

        if (stored == null
                || !stored.ownerUsername()
                        .equals(authenticatedUsername)) {
            throw new AccountNotFoundException();
        }

        return view(stored);
    }

    public AccountView updateOwn(
            long id,
            String authenticatedUsername,
            EditAccountInput input) {

        StoredAccount next = accounts.compute(
                id, (key, stored) -> {
                    if (stored == null
                            || !stored.ownerUsername()
                                    .equals(authenticatedUsername)) {
                        throw new AccountNotFoundException();
                    }

                    if (!stored.status().equals("ACTIVE")) {
                        throw new AccountLockedException();
                    }

                    return new StoredAccount(
                            stored.id(),
                            stored.ownerUsername(),
                            stored.role(),
                            stored.status(),
                            input.getDisplayName().trim(),
                            input.getBio());
                });

        return view(next);
    }

    public AccountView updateMyPrimary(
            String authenticatedUsername,
            EditAccountInput input) {

        Long id = primaryIds.get(authenticatedUsername);
        if (id == null) {
            throw new AccountNotFoundException();
        }

        return updateOwn(id, authenticatedUsername, input);
    }

    private static AccountView view(StoredAccount stored) {
        return new AccountView(
                stored.id(),
                stored.ownerUsername(),
                stored.role(),
                stored.status(),
                stored.displayName(),
                stored.bio());
    }
}
~~~

Bốn điểm bảo mật:

- `id` đến từ URL hoặc mapping nội bộ, không có trong input DTO.
- `authenticatedUsername` đến từ Spring Security principal, không từ body.
- Service so khớp owner trước khi cho sửa và từ chối account không `ACTIVE`.
- Khi dựng bản ghi mới, bốn field server-managed được **copy nguyên** từ state hiện có; chỉ hai field editable được cập nhật.

`ConcurrentHashMap.compute` cho phép atomic update theo key trong demo. Mapping `primaryIds` là dữ liệu ví dụ, không phải cơ chế tìm account trong sản phẩm thật: dùng database mapping đáng tin và kiểm tra tenant/permissions. Vai trò trong account là metadata server-managed; nguồn authority dùng để cấp quyền trong production phải được bảo vệ bởi security subsystem, không lấy từ DTO.

### 8.8. AccountNotFoundException.java

~~~java
package com.example.safeedit;

public final class AccountNotFoundException
        extends RuntimeException {
}
~~~

### 8.9. AccountLockedException.java

~~~java
package com.example.safeedit;

public final class AccountLockedException
        extends RuntimeException {
}
~~~

### 8.10. AccountController.java

~~~java
package com.example.safeedit;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.security.Principal;
import java.util.Map;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @InitBinder("editForm")
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "bio");
    }

    @GetMapping("/{id}")
    public AccountView get(
            @PathVariable long id,
            Principal principal) {

        return service.getOwn(id, principal.getName());
    }

    @PutMapping(
            path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public AccountView updateJson(
            @PathVariable long id,
            @Valid @RequestBody EditAccountInput input,
            Principal principal) {

        return service.updateOwn(
                id, principal.getName(), input);
    }

    @PostMapping(
            path = "/me/form",
            consumes =
                    MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updateForm(
            @Valid @ModelAttribute("editForm")
            EditAccountInput input,
            BindingResult errors,
            Principal principal) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    Map.of("code", "UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    Map.of("code", "VALIDATION_FAILED"));
        }

        return ResponseEntity.ok(
                service.updateMyPrimary(
                        principal.getName(), input));
    }
}
~~~

**Quan trọng:** `@InitBinder` chỉ kiểm soát đường `@ModelAttribute`. JSON `@RequestBody` dùng Jackson với DTO và strict unknown fields. Form handler dùng `BindingResult` đứng ngay sau `@ModelAttribute`, trả 400 nếu binder suppress input ngoài allowlist.

Đường form là `/me/form` nên **không có path variable** đưa vào tập request bind values. Server chọn account của principal. Với endpoint form có path variable `id`, kiểm tra kỹ cách MVC đưa URI variables vào binder và chính sách `getSuppressedFields()`, tránh từ chối nhầm request hợp lệ.

### 8.11. ApiErrors.java

~~~java
package com.example.safeedit;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(AccountNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Account not found");
        p.setProperty("code", "ACCOUNT_NOT_FOUND");
        return ResponseEntity.status(
                HttpStatus.NOT_FOUND).body(p);
    }

    @ExceptionHandler(AccountLockedException.class)
    ResponseEntity<ProblemDetail> locked() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Account cannot be edited in its current state");
        p.setProperty("code", "ACCOUNT_STATE_CONFLICT");
        return ResponseEntity.status(
                HttpStatus.CONFLICT).body(p);
    }
}
~~~

Lỗi không tìm được/không có quyền theo policy demo trả 404, trạng thái khóa trả 409. Handler không echo exception internals. Phản hồi cho JSON/form invalid có thể do MVC hoặc controller xử lý với HTTP 400.

### 8.12. application.properties

~~~properties
server.port=8080
spring.jackson.deserialization.fail-on-unknown-properties=true
server.error.include-message=never
~~~

Không dùng `spring.security.*` cố định mật khẩu trong project source. Để tái lập với principals `alice`/`bob`/`charlie`, dùng MockMvc test `@WithMockUser` ở mục tiếp theo; khi chạy server thủ công, cần cấu hình authentication provider và credentials thật cho môi trường tương ứng.

Chạy:

~~~bash
mvn test
mvn spring-boot:run
~~~

Dữ liệu phản hồi thành công sau khi đổi thông tin có dạng:

~~~json
{
  "id": 101,
  "ownerUsername": "alice",
  "role": "USER",
  "status": "ACTIVE",
  "displayName": "Alice Updated",
  "bio": "New bio"
}
~~~

Bốn trường server-managed giữ nguyên dù client chỉ được phép gửi hai editable fields.

## 9. MockMvc kiểm thử cả HTTP lẫn dữ liệu cuối

File `src/test/java/com/example/safeedit/AccountSecurityTest.java`:

~~~java
package com.example.safeedit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(username = "alice", roles = "USER")
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AccountSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerReadsOwnAccount() throws Exception {
        mvc.perform(get("/api/accounts/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value(
                        "alice"))
                .andExpect(jsonPath("$.role").value("USER"))
                .andExpect(jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    void validJsonChangesOnlyEditableFields()
            throws Exception {

        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"Alice Updated",
                                  "bio":"New bio"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.role").value("USER"))
                .andExpect(jsonPath("$.ownerUsername").value(
                        "alice"))
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andExpect(jsonPath("$.displayName").value(
                        "Alice Updated"));
    }

    @Test
    void forgedJsonRoleAndOwnerAreRejected()
            throws Exception {

        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"Changed",
                                  "bio":"Text",
                                  "role":"ADMIN",
                                  "ownerUsername":"bob"
                                }
                                """))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.role").value("USER"))
                .andExpect(jsonPath("$.ownerUsername").value(
                        "alice"))
                .andExpect(jsonPath("$.displayName").value("Alice"));
    }

    @Test
    void forgedJsonIdIsRejected() throws Exception {
        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "id":202,
                                  "displayName":"Changed",
                                  "bio":"Text"
                                }
                                """))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.displayName").value("Alice"));
    }

    @Test
    void validFormUpdatesOwnFields() throws Exception {
        mvc.perform(post("/api/accounts/me/form")
                        .with(csrf())
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Alice Form")
                        .param("bio", "Updated by form"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value(
                        "Alice Form"))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void forgedFormFieldsAreSuppressedAndRejected()
            throws Exception {

        mvc.perform(post("/api/accounts/me/form")
                        .with(csrf())
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Attacker")
                        .param("bio", "Text")
                        .param("id", "202")
                        .param("role", "ADMIN")
                        .param("ownerUsername", "bob")
                        .param("status", "ACTIVE"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(
                        "UNEXPECTED_FIELD"));

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.displayName").value("Alice"))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void pathIdCannotAccessOtherOwner()
            throws Exception {

        mvc.perform(put("/api/accounts/202")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"Not Bob",
                                  "bio":"No permission"
                                }
                                """))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/accounts/202"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "charlie", roles = "USER")
    void suspendedAccountCannotEdit() throws Exception {
        mvc.perform(put("/api/accounts/303")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"New Charlie",
                                  "bio":"Edit attempt"
                                }
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(
                        "ACCOUNT_STATE_CONFLICT"));

        mvc.perform(get("/api/accounts/303"))
                .andExpect(jsonPath("$.status").value("SUSPENDED"))
                .andExpect(jsonPath("$.displayName").value(
                        "Charlie"));
    }

    @Test
    void invalidDisplayNameDoesNotChangeAccount()
            throws Exception {

        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"",
                                  "bio":"Text"
                                }
                                """))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.displayName").value("Alice"));
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotAccessAccount() throws Exception {
        mvc.perform(get("/api/accounts/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/accounts/me/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "No CSRF")
                        .param("bio", "Text"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ **11 tests** kiểm tra: quyền đọc của chủ sở hữu; JSON hợp lệ chỉ đổi hai trường; JSON giả role/owner/id bị từ chối và giữ state; form hợp lệ; form có field ngoài allowlist bị suppress và từ chối; sửa ID URL sang tài khoản người khác bị chặn; trạng thái `SUSPENDED` không thể bỏ qua; Bean Validation; authentication 401; và CSRF 403.

`@DirtiesContext` khiến application context được tạo lại sau mỗi test để bản ghi trong map không bị test khác sửa. Trong hệ thống lớn có DB, nên cân nhắc rollback/reset fixture để tăng tốc, nhưng phải giữ tính độc lập của tests.

**Phạm vi QA:** mã và API trong demo được soạn cho Java 17 / Spring Boot 3.5.7; lệnh `mvn test` là cách chạy được cung cấp. Tài liệu này không khẳng định đã chạy Maven trong môi trường đang soạn.

## 10. JPA/transaction và trạng thái server

Trong production, thay in-memory map bằng entity/repository. Một cách cập nhật an toàn:

~~~java
@Transactional
public AccountView edit(
        long id,
        String authenticatedUsername,
        EditAccountRequest input) {

    AccountEntity entity =
            repository.findByIdAndOwnerUsername(
                    id, authenticatedUsername)
                .orElseThrow(AccountNotFoundException::new);

    if (entity.getStatus() != AccountStatus.ACTIVE) {
        throw new AccountLockedException();
    }

    entity.setDisplayName(input.displayName());
    entity.setBio(input.bio());

    return toView(entity);
}
~~~

Đây là **snippet kiến trúc** cần entity/repository/DTO thật, không nằm trong project chạy được ở trên. Không gọi setter cho id/role/owner/status. Trong JPA, entity managed sẽ được dirty checking khi transaction hoàn tất; tránh copy nguyên HTTP body vào entity.

Với optimistic locking:

~~~java
@Entity
class AccountEntity {
    @Id
    private Long id;

    @Version
    private long version;
}
~~~

Đây là snippet JPA chưa đủ imports/mapping. `@Version` giúp phát hiện một số lost updates khi hai requests cùng sửa; không tự chứng minh người dùng có quyền truy cập.

Khi cần atomic authorization và state check ngay ở database, có thể dùng câu lệnh có điều kiện:

~~~sql
UPDATE accounts
SET display_name = :displayName,
    bio = :bio
WHERE id = :accountId
  AND owner_username = :trustedUsername
  AND status = 'ACTIVE'
  AND version = :expectedVersion;
~~~

Phải kiểm tra affected row count và cập nhật version theo DB/ORM policy. Với multi-tenant thêm tenant predicate. Không dùng `userId` hay tenantId tùy ý từ request body làm trusted predicate.

## 11. PATCH, nested fields và những đường ghi khác

### 11.1. JSON Patch

Một payload như:

~~~json
[
  {"op":"replace","path":"/displayName","value":"Alice"},
  {"op":"replace","path":"/role","value":"ADMIN"}
]
~~~

không nên được áp dụng trực tiếp vào entity. Với JSON Patch/Merge Patch, cần **allowlist paths** (ví dụ `/displayName`, `/bio`), validate operation/type, phân biệt field vắng mặt với null và kiểm quyền trên resource.

### 11.2. Nested input

~~~json
{
  "displayName":"Alice",
  "team":{
    "ownerId":202,
    "members":[{"role":"ADMIN"}]
  }
}
~~~

Nếu DTO chứa nested team object rộng, client có thể thử sửa role/owner qua graph con. Tách nested DTO chỉ có trường được phép, đặt constraints và size limits phù hợp. Đừng dùng wildcard cho toàn bộ object graph khi trong đó có server-managed fields.

### 11.3. Số lượng lớn / batch updates

Khi API nhận danh sách IDs, kiểm quyền trên **từng** object hoặc dùng truy vấn bảo đảm cùng scope. Không xác thực một ID đầu tiên rồi áp dụng update cho toàn bộ danh sách mà chưa kiểm tra phần còn lại. Với batch có lỗi từng phần, xác định transaction/atomicity và error response contract rõ ràng.

### 11.4. Audit và observability

Nên lưu:

~~~text
principal=alice
action=EDIT_OWN_PROFILE
resourceType=Account
resourceId=101
changedFields=[displayName,bio]
result=SUCCESS
~~~

Đây là ví dụ nội dung log, không phải stdout của demo. Nếu bắt được thử gửi `role` hay `ownerUsername`, có thể log tên field và request ID sau khi sanitization, **không** log raw body, rejected value, token hoặc thông tin cá nhân nhạy cảm.

## 12. Lỗi phổ biến

| Hiện tượng | Lý do | Cách khắc phục |
| --- | --- | --- |
| User gửi `role=ADMIN` và server chấp nhận | Entity được bind trực tiếp | DTO nhỏ, allowedFields, authorization |
| Chỉ dùng `setDisallowedFields("role")` | Sau này có `isAdmin` hoặc alias khác | Ưu tiên allowlist/DTO |
| `@Valid` vẫn chấp nhận role ADMIN | Giá trị đúng enum nhưng không được phép | Phân quyền và không nhận role ở input |
| Client tự sửa `ownerId` trong body | Tin body thay cho principal | Dùng identity từ SecurityContext |
| DTO chỉ editable fields nhưng vẫn sửa được account khác | IDOR qua URL `/{id}` | Service kiểm quyền trên resource ID |
| Form bị từ chối khi thêm field extra | Binder suppress field ngoài allowlist | Policy 400 hoặc ignore có kiểm soát |
| JSON có field extra nhưng `@InitBinder` không chặn | JSON do Jackson xử lý | DTO + Jackson unknown-field policy |
| Bật declarative binding nhưng constructor nhận role | Constructor vẫn là nguồn binding | Constructor chỉ có editable params |
| `status=ACTIVE` tự mở khóa account | Copy input sang entity | Domain state check và workflow riêng |
| PATCH đổi `/members/0/role` | Không hạn chế paths | Patch allowlist/nested DTO |
| Form gửi hidden `ownerId` | Hidden input không đáng tin | Không đưa owner vào form input |
| Test chỉ khẳng định 400, không kiểm tra DB | Có thể state đã đổi trước khi throw | Assert state sau request, transaction/rollback |
| Thiếu CSRF test | Chỉ test controller bỏ security filters | Full MockMvc Security + csrf() |
| Ownership chỉ check tại controller | Đường service khác có thể bypass | Enforce tại service/domain boundary |
| Concurrent update ghi đè status mới | Race condition/lost update | Transaction, version/state predicate |
| Log nguyên rejected field value | Lộ token/PII | Log key/context tối thiểu, không log value |
| JSON response để lộ internal exception | Trả exception thô | Error code và thông điệp an toàn |
| Dòng Spring cũ không có `setDeclarativeBinding` | API từ Spring 6.1 | DTO + allowedFields, hoặc nâng version |

Một vấn đề bảo mật thực tế: advisory **CVE-2025-22233** của Spring ghi nhận các trường hợp có thể vượt qua kiểm tra `disallowedFields` ở một số phiên bản. Các bản sửa được liệt kê gồm 6.2.7 và 6.1.20. Cần dùng bản vá phù hợp nhưng vẫn ưu tiên thiết kế DTO/allowlist thay vì dựa vào denylist.

## 13. Checklist review một endpoint cập nhật

1. Controller có nhận entity trực tiếp từ body/form không?
2. Input DTO chỉ có những field được phép sửa hay không?
3. Từng nested DTO/collection/map có thể chứa owner/role/status không?
4. Với form, `@InitBinder` có đúng tên model attribute và `allowedFields` có chính xác không?
5. Với JSON, có kiểm thử extra fields bằng Jackson policy đang dùng không?
6. ID trong URL được kiểm quyền với principal/tenant thực sự chưa?
7. SecurityContext được tạo từ nguồn authentication tin cậy, không phải header/body tự khai báo chứ?
8. Role/status có workflow riêng và kiểm tra preconditions hiện tại không?
9. Service có mapping thủ công chỉ sửa đúng editable fields không?
10. Database transaction, version hoặc conditional update có bảo vệ race không?
11. Có test thử JSON role/owner/id, form role/owner/id, URL IDOR và suspended state không?
12. Test có xác minh dữ liệu cuối vẫn giữ id/role/owner/status không?
13. Có CSRF, method security và audit khi cần không?
14. Nếu đổi phiên bản Spring, đã kiểm tra API binder và security advisories chưa?
15. Nếu request bị từ chối, response/log có tránh tiết lộ secrets và dữ liệu người dùng không?

## 14. Bài tập vận dụng

**1.** Tạo controller anti-pattern nhận `AccountEntity` rồi thử gửi `role=ADMIN`. Giải thích chính xác layer nào cho phép ghi dữ liệu và tại sao không nên dùng code này.

**2.** Chuyển sang input DTO có `displayName` và `bio`; viết test cho JSON có extra `role` và `ownerUsername`. Quy định rõ 400 hay ignore.

**3.** Với form, thêm `@InitBinder("editForm")` và `setAllowedFields`, sau đó inspect `BindingResult.getSuppressedFields()`. Vì sao một field `ownerUsername` bị suppress không đồng nghĩa authorization đã hoàn tất?

**4.** Bật `setDeclarativeBinding(true)` trên Spring 6.1+ và thử DTO constructor chỉ có editable fields. Giải thích tại sao constructor rộng vẫn nguy hiểm.

**5.** Đăng nhập alice rồi cố `PUT /api/accounts/202` của bob. Vì sao payload không chứa role/owner vẫn phải bị từ chối?

**6.** Với account `charlie` trạng thái `SUSPENDED`, thử request cập nhật bio hợp lệ. Điều gì xảy ra và nên trả 403/409 theo policy nào?

**7.** Thiết kế command thay role dành riêng cho admin, có permission check, reason và audit. Hãy phân biệt role do body yêu cầu với authority của người gọi.

**8.** Thêm `tenantId` vào account. Hãy sửa repository query để kiểm tra ID, owner và tenant trong cùng điều kiện an toàn.

**9.** Thêm `@Version` vào JPA entity. Thiết kế test hai updates đồng thời và giải thích vì sao optimistic locking không thay được authorization.

**10.** Thêm một nested `ContactInput` có street/city. Chứng minh không thể gửi `contact.ownerId` hoặc `members[0].role` qua binder/JSON.

## Kết luận

~~~text
HTTP form / JSON / PATCH: KHÔNG ĐÁNG TIN
       |
       v
Input DTO chỉ có editable fields
       |
       +-- MVC form: allowedFields + declarativeBinding
       +-- JSON: Jackson DTO + unknown-field strategy
       +-- PATCH: allowlist operations/paths
       |
       v
Validation định dạng và giới hạn
       |
       v
Authenticated principal + resource-level authorization
       |
       v
Server-side state checks và workflow rules
       |
       v
Explicit updates CHỈ cho editable fields
       |
       v
Transaction / concurrency / audit
~~~

**Không bao giờ để id, role, owner hoặc status trở thành dữ liệu client có thể tùy tiện gán chỉ vì có setter hoặc JSON property.** Hãy tách input và domain, kiểm quyền trên đúng đối tượng, giữ server-owned fields từ state tin cậy và test cả kết quả HTTP lẫn dữ liệu sau cập nhật. `@Valid`, việc ẩn UI và các blacklist không thay thế được những ranh giới đó.

## Tài liệu tham khảo

- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [Spring Framework 6.2 — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Security — CVE-2025-22233 DataBinder advisory](https://spring.io/security/cve-2025-22233/)
- [Spring Boot 3.5 — Jackson application properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Security — MockMvc with @WithMockUser](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
