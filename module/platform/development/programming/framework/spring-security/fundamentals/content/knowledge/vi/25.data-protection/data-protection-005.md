# DTO và giới hạn trường dữ liệu được nhận hoặc trả về

## 1. Vấn đề bảo mật mà DTO giải quyết

Khi một API nhận JSON từ client hoặc trả JSON cho client, **không phải mọi trường có trong entity/domain model đều được phép đi qua ranh giới HTTP**. Ví dụ, bảng tài khoản có thể có `id`, `email`, `displayName`, `role`, `admin`, `passwordHash`, `internalNote`, `locked` và `createdAt`. Người dùng được phép đổi tên hiển thị có thể chỉ nên gửi `displayName`; trang hồ sơ có thể chỉ nên nhận `id`, `email` và `displayName` khi đọc.

**DTO (Data Transfer Object)** là kiểu dữ liệu được tạo để biểu diễn hợp đồng trao đổi ở một ranh giới, chẳng hạn request hoặc response của một API. Việc dùng DTO riêng cho từng thao tác giúp khai báo rõ:

- **Đầu vào**: client được phép cung cấp **những trường nào**, kiểu dữ liệu nào, điều kiện hợp lệ nào.
- **Đầu ra**: client được phép **nhìn thấy những trường nào**, ở endpoint nào và trong ngữ cảnh quyền nào.
- **Ánh xạ**: service quyết định **trường nào thực sự được cập nhật**, dữ liệu nào phải lấy từ phiên xác thực hoặc máy chủ.
- **Độ ổn định API**: thay đổi bảng/entity nội bộ không tự biến thành thay đổi JSON công khai.

Đây là một cơ chế **giảm bề mặt tấn công và giảm lộ dữ liệu** trong chủ đề *Bảo vệ dữ liệu* của Spring Security. DTO **không thay thế** authentication, authorization, kiểm tra quyền sở hữu, validation, CSRF, mã hóa khi truyền hoặc lọc dữ liệu theo tenant; nó là một lớp kiểm soát cần phối hợp với các lớp đó.

Mục tiêu: nhận diện **mass assignment/overposting** và **excessive data exposure**; thiết kế input DTO và output DTO; giới hạn field được nhận/trả; áp dụng Bean Validation; mapping allowlist thay vì copy tất cả thuộc tính; và kiểm thử cả trường hợp tấn công.

## 2. Hai kiểu lỗi điển hình

### 2.1. Nhận quá nhiều trường: mass assignment / overposting

Giả sử endpoint thay hồ sơ nhận trực tiếp entity:

```java
@PutMapping("/api/me")
public Account update(@RequestBody Account body) {
    return repository.save(body); // Ví dụ dễ bị overposting: KHÔNG áp dụng
}
```

Entity `Account` có thuộc tính `admin` và `role`. Client có thể gửi:

```json
{
  "displayName": "Mai",
  "email": "mai@example.test",
  "admin": true,
  "role": "ADMIN"
}
```

Nếu code bind rồi lưu nguyên entity mà không kiểm soát, trường `admin`/`role` do client gửi có thể làm thay đổi quyền. Đây là **mass assignment (CWE-915)**: dữ liệu HTTP điều khiển các thuộc tính mà người gửi không được phép sửa. Không cần endpoint tài liệu hóa tên trường nguy hiểm; kẻ tấn công có thể đoán hoặc thử các tên thuộc tính.

Cách bảo vệ chính: định nghĩa request DTO chỉ chứa trường client được chỉnh và **cập nhật từng thuộc tính trong service bằng allowlist**. Kiểm tra quyền đối với đối tượng được sửa là lớp riêng, không được bỏ qua.

### 2.2. Trả quá nhiều trường: excessive data exposure

Một lỗi khác là trả nguyên entity:

```java
@GetMapping("/api/me")
public Account me() {
    return repository.findCurrentAccount(); // Ví dụ lộ dữ liệu: KHÔNG áp dụng
}
```

Nếu Jackson serialize toàn bộ thuộc tính có thể nhìn thấy, response có nguy cơ lộ `passwordHash`, `internalNote`, `mfaSecret`, trạng thái khóa, token nội bộ, hoặc dữ liệu của tenant khác. **Frontend có ẩn trường đi cũng không bảo vệ được**: người gọi vẫn nhìn thấy JSON trong Network tab hoặc dùng `curl`.

Cách bảo vệ chính: response DTO chỉ gồm trường được phép trả. Với trường nhạy cảm, cân nhắc projection ngay trong truy vấn DB để không đọc dữ liệu thừa; endpoint và service vẫn phải thực thi chính sách quyền.

### 2.3. So sánh ba mức phòng vệ

| Mức | Chức năng | Có giải quyết một mình mọi lỗi không? |
| --- | --- | --- |
| Request/Response DTO | Giới hạn **hình dạng dữ liệu** ở ranh giới API | Không: dữ liệu được phép gửi vẫn phải kiểm tra quyền |
| Bean Validation như `@NotBlank`, `@Email`, `@Size` | Giới hạn **giá trị và định dạng** | Không: `"ADMIN"` có thể đúng định dạng nhưng không đúng quyền |
| Spring Security, service authorization, tenant/object checks | Quyết định **ai được làm gì với đối tượng nào** | Không: vẫn cần tránh trả field bí mật và tránh bind ngoài ý muốn |

## 3. Phân biệt entity, input DTO, output DTO và domain command

Một luồng điển hình:

```text
Client JSON
   │
   ▼
@RequestBody → Jackson deserialization
   │
   ▼
UpdateProfileRequest (allowlist input)
   │
   ▼
@Valid + xác thực người gửi + authorization
   │
   ▼
ProfileService: cập nhật đúng trường đã cho phép
   │
   ▼
Account entity / database
   │
   ▼
ProfileResponse (allowlist output)
   │
   ▼
Jackson serialization → HTTP JSON
```

| Kiểu đối tượng | Mục đích | Có nên dùng trực tiếp tại HTTP? |
| --- | --- | --- |
| JPA entity / persistence model | Lưu trạng thái, quan hệ DB, metadata, các trường nội bộ | Tránh nhận/trả nguyên entity cho API công khai |
| `CreateAccountRequest` | Field được phép cung cấp khi tạo | Có, tại endpoint tạo |
| `UpdateProfileRequest` | Field được phép sửa hồ sơ | Có, tại endpoint sửa hồ sơ |
| `ProfileResponse` | Field được phép công khai cho chính chủ | Có, tại endpoint đọc/sửa |
| `PublicProfileResponse` | Tập nhỏ hơn cho người khác xem | Có, tại endpoint công khai |
| `AdminAccountResponse` | Field bổ sung chỉ được cấp cho quản trị viên | Có, **sau** khi kiểm tra quyền ADMIN |
| Domain command | Lệnh nghiệp vụ đã được xác thực/chuẩn hóa | Thường đi giữa controller và service |

**Không cần tạo một DTO cho mỗi class Java**. Cần DTO theo *hợp đồng* và *quyền truy cập*: hai endpoint có cùng shape, cùng semantics và cùng chính sách có thể dùng chung một DTO. Nhưng việc gộp tất cả create, patch, admin và public vào một `AccountDto` có vài chục trường nullable thường phá vỡ ranh giới rõ ràng.

**Một input DTO không phải dữ liệu đáng tin chỉ vì nó có kiểu Java**. Jackson đã chuyển JSON thành object, nhưng client vẫn có quyền kiểm soát toàn bộ các giá trị trong những field được khai báo. Service phải chuẩn hóa và xác minh chúng.

## 4. Thiết kế allowlist theo nghiệp vụ

Ví dụ API tài khoản với `PUT /api/profile`:

| Trường của account nội bộ | Client được gửi để sửa? | Client xem trong `ProfileResponse`? | Ai kiểm soát? |
| --- | --- | --- | --- |
| `id` | **Không** | Có | Máy chủ / database |
| `username` | Không ở thao tác đổi hồ sơ này | Có thể tùy hợp đồng | Identity hệ thống |
| `displayName` | **Có** | **Có** | Người dùng trong giới hạn policy |
| `email` | Có nếu nghiệp vụ cho phép, có thể cần verify riêng | Có với chính chủ | Người dùng + quy trình xác minh |
| `role` | **Không** | Không trong profile thông thường | Quy trình quản lý quyền |
| `admin` | **Không** | Không | Server / chính sách cấp quyền |
| `passwordHash` | **Không** | **Không bao giờ** | Authentication subsystem |
| `internalNote` | Không | Không | Hệ thống quản trị |
| `locked` | Không | Thường không | Hệ thống chống lạm dụng |
| `createdAt` | Không | Tùy hợp đồng | Database |

Việc chọn tập field phải dựa vào từng thao tác: endpoint đổi mật khẩu có thể nhận `currentPassword` và `newPassword` nhưng không bao giờ nhận `passwordHash`; endpoint upload avatar có thể nhận tệp nhưng không nhận URL tài nguyên nội bộ không được phê duyệt. Tách luồng tương ứng.

Trong ví dụ bên dưới, `email` được chỉnh trực tiếp **chỉ để minh họa kỹ thuật DTO**. Hệ thống thật thường cần xác minh địa chỉ mới qua email trước khi cập nhật trường `verifiedEmail` hoặc quyền dựa trên email. Không tự coi một email client vừa gửi là đã xác minh.

## 5. Ví dụ Java 17+ chạy được: input DTO và output DTO riêng

Ví dụ dùng **Spring Boot 3.5.7 / Spring Security 6.x, Spring MVC, Jackson và Jakarta Bean Validation**. Để dễ thử nghiệm, dữ liệu account được lưu in-memory; phần xác thực dùng HTTP Basic với một tài khoản demo. Cấu hình **giữ CSRF mặc định** để thấy rõ yêu cầu an toàn cho method thay đổi trạng thái.

Mục tiêu của demo:

- `GET /api/profile`: chỉ user đã xác thực đọc profile của **chính mình**, response có `id`, `displayName`, `email`.
- `PUT /api/profile`: chỉ chấp nhận `displayName` và `email`; không nhận `id`, `admin`, `role`, `passwordHash`.
- JSON có field lạ bị trả **400** nhờ cấu hình Jackson nghiêm ngặt; đây là lựa chọn minh bạch cho hợp đồng API.
- JSON thiếu giá trị bắt buộc hoặc sai định dạng bị trả **400** nhờ `@Valid`.
- HTTP Basic không được dùng như lý do để tắt CSRF bừa bãi. Test có CSRF token hợp lệ mới thực hiện PUT thành công.
- Mọi response được tạo từ DTO, không serialize account nội bộ.

### 5.1. Cấu trúc dự án

```text
dto-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/DtoBoundaryApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/DtoBoundaryApplicationTests.java
```

### 5.2. Maven: `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>dto-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-security</artifactId>
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
```

Starter validation được khai báo riêng vì Bean Validation không nên được giả định luôn có mặt chỉ nhờ starter web. Dependency security test cung cấp `csrf()` và `httpBasic()` cho MockMvc.

### 5.3. Cấu hình Jackson: `src/main/resources/application.yml`

```yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
```

Cấu hình này bật Jackson `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` cho mapper do Spring Boot 3.5 quản lý. Nếu JSON gửi trường lạ như `admin` vào DTO không có trường đó, HTTP message converter thường ném lỗi đọc JSON và Spring MVC trả **400 Bad Request**.

**Lưu ý rất quan trọng:** mặc định ignore hay reject unknown properties có thể khác theo cấu hình, phiên bản, custom `ObjectMapper` và annotation. **Đừng dựa vào cấu hình mặc định không kiểm chứng.** Việc dùng DTO allowlist và mapping tường minh mới là phòng vệ gốc: dù JSON field lạ bị bỏ qua thay vì báo 400, nó vẫn không được phép thay đổi entity. Chế độ reject-unknown ở đây giúp phát hiện client gửi sai hợp đồng, nhưng có thể ảnh hưởng tương thích API khi client gửi field mới; hãy lựa chọn theo chiến lược phiên bản và kiểm thử.

### 5.4. Ứng dụng: `src/main/java/demo/DtoBoundaryApplication.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class DtoBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DtoBoundaryApplication.class, args);
    }

    @Bean
    UserDetailsService demoUsers() {
        // Chỉ dành cho demo. Production phải hash password và quản lý secret.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo123")
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/profile").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Không tắt CSRF: PUT phải có token hợp lệ.
                .build();
    }

    // DTO đầu vào chỉ chứa những thuộc tính người dùng được phép sửa.
    public record UpdateProfileRequest(
            @NotBlank @Size(max = 80) String displayName,
            @NotBlank @Email @Size(max = 254) String email) {}

    // DTO đầu ra chỉ chứa những thuộc tính được phép tiết lộ.
    public record ProfileResponse(
            long id, String displayName, String email) {}

    @Service
    public static class ProfileService {
        private final Map<String, Account> accounts =
                new ConcurrentHashMap<>();

        public ProfileService() {
            accounts.put("alice", new Account(
                    101L,
                    "alice",
                    "Alice",
                    "alice@example.test",
                    "internal-password-hash-placeholder",
                    "USER",
                    false,
                    "Internal review only"));
        }

        public ProfileResponse getProfile(String username) {
            Account account = accounts.get(username);
            if (account == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return toResponse(account);
        }

        public ProfileResponse updateProfile(
                String username, UpdateProfileRequest input) {
            Account updated = accounts.computeIfPresent(
                    username,
                    (key, current) -> new Account(
                            current.id(),
                            current.username(),
                            input.displayName().strip(),
                            input.email().strip(),
                            current.passwordHash(),
                            current.role(),
                            current.admin(),
                            current.internalNote()));

            if (updated == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return toResponse(updated);
        }

        private static ProfileResponse toResponse(Account account) {
            return new ProfileResponse(
                    account.id(),
                    account.displayName(),
                    account.email());
        }

        // Entity minh họa chứa những trường TUYỆT ĐỐI
        // không đi trực tiếp qua ranh giới HTTP.
        private record Account(
                long id,
                String username,
                String displayName,
                String email,
                String passwordHash,
                String role,
                boolean admin,
                String internalNote) {}
    }

    @RestController
    @RequestMapping("/api/profile")
    public static class ProfileController {
        private final ProfileService profiles;

        public ProfileController(ProfileService profiles) {
            this.profiles = profiles;
        }

        @GetMapping
        public ProfileResponse me(Authentication authentication) {
            // Username lấy từ authentication đã được Spring Security xác minh.
            return profiles.getProfile(authentication.getName());
        }

        @PutMapping
        public ProfileResponse update(
                Authentication authentication,
                @Valid @RequestBody UpdateProfileRequest input) {
            return profiles.updateProfile(
                    authentication.getName(), input);
        }
    }
}
```

**Vì sao code này giữ được giới hạn trường?**

1. `UpdateProfileRequest` **không có** `admin`, `role`, `passwordHash` hoặc `id`. Jackson không thể biến một giá trị `admin` hợp lệ trong JSON thành thuộc tính của DTO đó; cấu hình nghiêm ngặt còn reject request có field lạ.
2. Service gọi `new Account(...)` bằng các trường lấy từ **account hiện tại** và chỉ thay `displayName`, `email`. Các trường `id`, `role`, `admin`, `passwordHash`, `internalNote` được giữ nguyên ở server. Không có `BeanUtils.copyProperties(input, entity)` hoặc `repository.save(requestBody)` sao chép đại trà.
3. `ProfileController` không nhận `username` cần sửa từ body hoặc header client. Nó lấy chủ thể từ `Authentication#getName()`. Với API làm việc trên ID trong path, cần kiểm tra quyền trên **đúng object** trước khi đọc/sửa.
4. `ProfileResponse` chỉ có `id`, `displayName`, `email`. Jackson chỉ serialize các thuộc tính của response record; không có đường nào tự đưa password hash hoặc internal note vào JSON.
5. `@Valid` kích hoạt Jakarta Bean Validation trên input DTO. `@NotBlank` từ chối blank/null, `@Email` kiểm tra cú pháp cơ bản, `@Size` giới hạn độ dài. Việc kiểm tra email tồn tại, domain tin cậy hoặc trạng thái đã xác minh là nghiệp vụ khác.
6. `SecurityFilterChain` bắt buộc xác thực trước khi cho vào controller. HTTP Basic của demo dùng `{noop}` **chỉ để dễ chạy**, không được dùng cho tài khoản production. Phải dùng HTTPS, password encoder phù hợp và secret store an toàn khi làm thật.
7. `ConcurrentHashMap#computeIfPresent` cho phép thay bản ghi nguyên khối an toàn trong demo nhiều request. Đây không phải persistence layer thật; database production cần transaction, khóa và kiểm soát race condition.
8. `CSRF` giữ mặc định trong ví dụ. HTTP Basic có thể được trình duyệt tự gửi credentials nên không nên coi nó mặc nhiên miễn nhiễm với CSRF.

### 5.5. Xem đầu ra bằng HTTP

Tại thư mục chứa `pom.xml`, dùng Java 17+ và Maven:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/dto-boundary-demo-0.0.1-SNAPSHOT.jar
```

Terminal khác:

```bash
curl -i http://localhost:8080/api/profile
curl -i -u alice:demo123 http://localhost:8080/api/profile
```

Kết quả mong đợi:

- Request không có credentials: **401 Unauthorized**, không nhận profile.
- Request có credentials đúng: **200 OK**, JSON ban đầu có dạng sau (bỏ qua khác biệt thứ tự field):

```json
{
  "id": 101,
  "displayName": "Alice",
  "email": "alice@example.test"
}
```

Response **không có** `passwordHash`, `role`, `admin` hoặc `internalNote`. Không trả entity rồi trông chờ frontend bỏ chúng đi.

Nếu gọi thử PUT như dưới đây **không cung cấp CSRF token**:

```bash
curl -i -u alice:demo123 -X PUT \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Alicia","email":"alicia@example.test"}' \
  http://localhost:8080/api/profile
```

kết quả dự kiến là **403 Forbidden vì CSRF**, kể cả khi credentials đúng và field hợp lệ. Đây là hành vi có chủ ý của bản demo. Phần kiểm thử dưới đây dùng `csrf()` của Spring Security Test để mô phỏng token hợp lệ và xác minh luồng PUT. Muốn thực hiện PUT bằng `curl` trong ứng dụng cookie/session thật, phải thiết kế phương thức cấp và gửi token CSRF tương ứng; không tắt CSRF chỉ để câu lệnh `curl` trả 200.

### 5.6. Kiểm thử MockMvc: kiểm tra luồng thực với validation và Spring Security

**`src/test/java/demo/DtoBoundaryApplicationTests.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DtoBoundaryApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void responseContainsOnlyPublicContractFields() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.displayName").exists())
                .andExpect(jsonPath("$.email").exists())
                .andExpect(jsonPath("$.passwordHash").doesNotExist())
                .andExpect(jsonPath("$.role").doesNotExist())
                .andExpect(jsonPath("$.admin").doesNotExist())
                .andExpect(jsonPath("$.internalNote").doesNotExist());
    }

    @Test
    void validDtoUpdatesOnlyAllowedFields() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "Alicia",
                                  "email": "alicia@example.test"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Alicia"))
                .andExpect(jsonPath("$.email")
                        .value("alicia@example.test"))
                .andExpect(jsonPath("$.admin").doesNotExist());
    }

    @Test
    void rejectsUnknownAdminField() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "Alicia",
                                  "email": "alicia@example.test",
                                  "admin": true
                                }
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidUserInput() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "   ",
                                  "email": "not-an-email"
                                }
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unsafeMethodWithoutCsrfTokenIsForbidden() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "Alicia",
                                  "email": "alicia@example.test"
                                }
                                """))
                .andExpect(status().isForbidden());
    }
}
```

Chạy `mvn test`. Các test mong đợi pass khi dùng đúng các file trên và không sửa hành vi Spring Security/Jackson. Bài test đảm bảo:

- Luồng HTTP không xác thực nhận 401.
- Response DTO không có các field bí mật.
- Request DTO hợp lệ được update khi có credentials và token CSRF.
- Client thêm `admin` vào JSON bị 400 theo strict Jackson config.
- Bean Validation từ chối dữ liệu bất hợp lệ với 400.
- Request PUT không có CSRF token nhận 403.

Tests có thể chạy theo thứ tự bất kỳ; phần test đọc profile chỉ kiểm tra shape chứ không giả định tên hiển thị còn là giá trị seed ban đầu. Đối với dự án production, thêm test khẳng định `admin`/`role` trong domain **thực sự không thay đổi**, test concurrent update, transaction và user khác truy cập dữ liệu của `alice`.

## 6. DTO đầu vào: xác định field client được phép sửa

### 6.1. Allowlist theo thao tác, đừng tái dùng entity “cho tiện”

Giả sử tài khoản có `id`, `username`, `email`, `passwordHash`, `role`, `locked`. Những hành động sau có hợp đồng khác nhau:

| API | Input DTO nên chứa | Không nên nhận |
| --- | --- | --- |
| `POST /accounts` tạo tài khoản | `email`, `displayName`, có thể `password` | `id`, `role`, `locked`, `passwordHash` |
| `PUT /api/profile` cập nhật hồ sơ | `displayName`, `email` | `role`, `admin`, `ownerId`, `createdAt` |
| `POST /api/password/change` | `currentPassword`, `newPassword` | `passwordHash`, `role` |
| `PUT /admin/accounts/{id}/status` | Một enum `status` có ràng buộc | Toàn bộ entity |
| `POST /orders` | Mã sản phẩm, số lượng, địa chỉ được phép | `unitPrice` do server tính, `paid`, `ownerId`, `discountApproved` |

Nếu client gửi giá hoặc `paid=true` trong request đặt hàng, service phải lấy bảng giá và trạng thái thanh toán từ nguồn có thẩm quyền. JSON có thể trông hoàn toàn hợp lệ về kiểu mà vẫn sai về quyền.

### 6.2. Bean Validation chỉ kiểm tra tính hợp lệ, không tự bảo đảm quyền

Ví dụ:

```java
public record CreateInvoiceRequest(
        @NotBlank String customerId,
        @NotNull @Positive BigDecimal amount) {}
```

Đoạn trên **chỉ là fragment minh họa**. Nó cần import `BigDecimal`, `NotBlank`, `NotNull`, `Positive`, và không thể chạy độc lập. Dù `customerId` không trống và `amount` dương, người dùng vẫn có thể không được phép tạo invoice cho khách hàng đó hoặc gửi số tiền tùy ý. Những kiểm tra đó phải ở service/domain.

Một số quy tắc hữu ích: `@NotNull` cho bắt buộc có giá trị, `@NotBlank` cho chuỗi khác blank, `@Size` giới hạn độ dài hoặc số phần tử, `@Pattern` cho định dạng, `@Email` cho cú pháp email, và validator custom cho điều kiện nghiệp vụ phức tạp. `@Valid` có thể kích hoạt validation lồng nhau, nhưng cần đặt constraints trên các DTO con. Giới hạn kích thước request body và độ sâu JSON riêng để chống tiêu thụ tài nguyên quá mức; Bean Validation không tự giới hạn dung lượng HTTP request.

Đừng gửi toàn bộ giá trị bị từ chối, token hoặc mật khẩu vào thông báo lỗi. Một response validation chuẩn chỉ nên có mã lỗi và tên field cần thiết; có thể sử dụng `ProblemDetail`/`@RestControllerAdvice` để tạo hợp đồng thống nhất, tránh lộ stack trace hoặc dữ liệu riêng tư.

### 6.3. Unknown fields: bỏ qua hay từ chối?

Có hai lựa chọn hợp lệ tùy hợp đồng:

- **Strict**: từ chối JSON có thuộc tính không biết, giúp bắt lỗi client và phát hiện overposting. Demo bật `fail-on-unknown-properties` và mong 400.
- **Lenient**: bỏ qua field lạ để tăng khả năng tương thích. Vẫn an toàn với vấn đề overposting **nếu** DTO chỉ chứa allowlist và service chỉ copy những field đó.

Không nghĩ rằng việc field lạ bị bỏ qua đồng nghĩa API có bảo vệ đầy đủ. Nếu chính request DTO chứa `role` hoặc service map một `Map<String,Object>` vào entity theo tên, lỗ hổng vẫn có thể tồn tại.

### 6.4. POST, PUT và PATCH không có cùng semantics

- **Create**: object mới; server tạo ID, ownership, timestamps và trạng thái mặc định.
- **PUT**: thông thường biểu diễn cập nhật/thay thế một tài nguyên theo hợp đồng; nếu trường bắt buộc vắng mặt, nên reject để tránh vô tình ghi `null`.
- **PATCH**: chỉ sửa các field được khai báo; cần phân biệt **không gửi field** với **gửi field có giá trị `null`**. Java record nullable đơn giản không phải lúc nào phân biệt được hai trạng thái này.
- **JSON Patch (RFC 6902)**: nếu hỗ trợ path động, kiểm tra allowlist đường dẫn, thao tác và quyền đối tượng trước khi áp dụng; không cho patch vào `/roles`, `/passwordHash`, `/ownerId`.

Đừng dùng `BeanUtils.copyProperties(patch, entity)` mà không kiểm soát allowed fields; việc copy `null` và các trường mới có thể tạo thay đổi không chủ ý. MapStruct hoặc mapper khác chỉ có ích nếu cấu hình cho phép rõ các field; tự động map theo tên từ DTO quá rộng vẫn rủi ro.

## 7. DTO đầu ra: ngăn lộ dữ liệu theo từng đối tượng và nhóm người dùng

### 7.1. Response DTO là một allowlist xuất dữ liệu

Ví dụ, domain account có `passwordHash`, `mfaSecret`, `lastLoginIp`, `riskScore` và `email`. Endpoint công khai thường chỉ cần:

```java
public record PublicProfileResponse(
        String displayName, String avatarUrl) {}
```

Endpoint của chính người dùng có thể trả thêm `email` và `id`. Endpoint dành cho ADMIN có thể có DTO khác, nhưng chỉ sau khi service/endpoint đã thực hiện authorization. Không thêm một biến `isAdmin` do client truyền vào để quyết định response có field riêng tư hay không.

**Chia DTO theo audience:**

| Audience | DTO | Ví dụ field |
| --- | --- | --- |
| Khách chưa đăng nhập | `PublicProfileResponse` | `displayName`, `avatarUrl` đã duyệt |
| Chủ tài khoản | `SelfProfileResponse` | Các field công khai + `email` đã được phép xem |
| Nhân viên hỗ trợ có quyền cụ thể | `SupportAccountResponse` | Một số trạng thái hỗ trợ cần thiết, có audit |
| Quản trị bảo mật | `SecurityAuditResponse` | Metadata theo quyền cụ thể, giới hạn thông tin bí mật |

Không cần trả `passwordHash` ngay cả cho administrator; hệ thống xác thực không cần xuất hash qua REST. Dữ liệu cần xử lý nội bộ vẫn có thể được bảo vệ bởi quyền truy cập DB, mã hóa khi lưu và chính sách ghi log.

### 7.2. Rò rỉ có thể xảy ra trong object lồng nhau

DTO cấp cao chỉ chứa ba field nhưng một field `customer` hoặc `address` lại giữ nguyên **entity có quan hệ hai chiều** thì vẫn có thể lộ dữ liệu sâu hơn. Hãy dùng DTO con rõ ràng và giới hạn độ sâu:

```java
public record OrderResponse(
        long id,
        String status,
        CustomerSummary customer) {}

public record CustomerSummary(
        long id,
        String displayName) {}
```

Đoạn này là mô hình minh họa, không phải file Java chạy độc lập. Đừng đưa `CustomerEntity` vào `OrderResponse` rồi nghĩ DTO cấp ngoài đã đủ bảo vệ. Entity JPA còn có thể gây lazy loading, truy vấn N+1 hoặc vòng lặp serialize khi trả trực tiếp.

### 7.3. Field-level authorization khác với DTO

Có trường chỉ được nhìn thấy khi đáp ứng điều kiện động: chẳng hạn số tiền hóa đơn chỉ chủ sở hữu hoặc kế toán được xem. DTO tĩnh cho từng audience có thể kết hợp mapping theo policy:

```text
Authentication đã xác minh
        │
        ▼
Service xác nhận quyền truy cập đối tượng + tenant
        │
        ▼
Chọn response DTO và field được phép
        │
        ▼
Serialize JSON
```

Không chỉ xóa field khỏi response nếu người dùng **không được quyền biết đối tượng tồn tại**; trường hợp đó có thể cần 403/404 theo chính sách chống lộ danh tính tài nguyên. DTO giúp tránh rò rỉ field, không tự giải quyết IDOR/BOLA (Broken Object Level Authorization).

### 7.4. Giảm dữ liệu cả ở truy vấn và luồng xử lý

Nếu endpoint danh sách chỉ cần `id` và `displayName`, một query projection chọn đúng hai cột giúp giảm dữ liệu đi qua DB/network/memory. Tuy nhiên, giới hạn query không thay cho response DTO và authorization. Khi có PII, cân nhắc `Cache-Control: no-store` phù hợp, HTTPS, không log body tùy tiện và tránh cache chung giữa người dùng.

## 8. Annotation Jackson: hỗ trợ nhưng không thay thế DTO rõ ràng

Một số annotation Jackson thường gặp:

| Annotation | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `@JsonIgnore` | Bỏ qua property khi xử lý JSON theo cấu hình | Có thể ảnh hưởng cả chiều đọc/ghi; không thay chính sách field |
| `@JsonProperty(access = READ_ONLY)` | Property chỉ xuất ra trong serialization, không nhận từ JSON | “Read” từ góc nhìn Java/Jackson, không phải “client được đọc” theo quyền |
| `@JsonProperty(access = WRITE_ONLY)` | Property có thể nhận khi deserialize, không serialize ra JSON | Hợp với password input trong DTO riêng; vẫn tránh lưu lẫn output |
| `@JsonView` | Chọn trường theo view khi serialize/deserialize | Dễ phức tạp khi nhiều endpoint/view, vẫn cần authorization |
| `@JsonIgnoreProperties` | Khai báo property bị bỏ qua/unknown policy | Không phải thay thế việc chỉ định field được phép cập nhật |
| `@JsonInclude` | Điều khiển có trả `null`/empty values | Không phải cơ chế phân quyền |

Ví dụ fragment minh họa Jackson:

```java
public record RegistrationRequest(
        String email,
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String password) {}
```

Khi serialize kiểu này, field `password` không được trả theo quy tắc access. Tuy nhiên DTO `RegistrationRequest` vốn là kiểu **đầu vào**, không nên dùng nó làm response chỉ vì đã có `WRITE_ONLY`. Tách `RegistrationResponse` dễ kiểm toán hơn.

Nếu dùng entity kèm `@JsonIgnore` cho `passwordHash`, một developer sau này thêm field `recoveryToken` mà quên annotation có thể làm lộ dữ liệu. Response DTO tường minh giúp field mới không tự xuất hiện trong hợp đồng API.

## 9. Phân biệt JSON `@RequestBody` với form/query `@ModelAttribute`

Trong Spring MVC, hai cơ chế bind dữ liệu liên quan nhưng **không tương đương**:

| Loại request | Cách bind phổ biến | Công cụ chính |
| --- | --- | --- |
| JSON request body | `@RequestBody`, Jackson qua `HttpMessageConverter` | Input DTO, ObjectMapper, Bean Validation |
| Form-urlencoded / query parameters | `@ModelAttribute`, `WebDataBinder` | Dedicated form object, `setAllowedFields` cho binder, Bean Validation |

Spring Framework có `WebDataBinder#setAllowedFields(...)` để allowlist các property được gán từ dữ liệu form/model binding. Ví dụ fragment dành cho controller xử lý `@ModelAttribute`:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
```

Đoạn trên yêu cầu import `InitBinder` và `WebDataBinder`. **Không xem `setAllowedFields` là biện pháp kiểm soát Jackson deserialize JSON `@RequestBody`**; với JSON hãy dùng input DTO riêng, cấu hình Jackson phù hợp và service mapping allowlist. Cố áp cùng quy tắc mà không hiểu cơ chế bind có thể tạo ảo giác bảo vệ.

Form binding còn cần chú ý nested paths như `account.roles[0]` hoặc `owner.id`. DTO theo hợp đồng hẹp giúp tránh binder có đường để chạm tới trạng thái nhạy cảm. Trong Spring Framework, constructor binding cũng có thể nhận dữ liệu, nên không chỉ kiểm tra setter; thiết kế input class/record rõ ràng vẫn quan trọng.

## 10. Phối hợp với Spring Security: quyền được quyết định ở server

### 10.1. Không nhận identity/ownership từ client nếu có thể lấy từ principal

Ví dụ đường dẫn `PUT /accounts/{accountId}` cần xác minh chủ thể có quyền sửa `accountId`. Đừng dùng:

```java
if (requestBody.ownerId().equals(accountId)) {
    // Sai: ownerId đều có thể do client kiểm soát
}
```

Đúng hơn là lấy danh tính đã xác minh từ `Authentication` hoặc `@AuthenticationPrincipal`, tìm tài nguyên ở DB, rồi kiểm tra chủ sở hữu/tenant tại service:

```text
authenticated user ──► subjectId
requested accountId ─► account trong DB
                             │
                             ▼
                 subjectId có quyền với accountId?
                        │             │
                       Có            Không
                        │             │
                     cập nhật         403/404
                        │
                     response DTO
```

Với OAuth2/JWT, subject và tenant claim chỉ đáng tin khi token đã được xác minh bởi Resource Server và mapped theo đúng issuer; ID token của OAuth2 client hoặc dữ liệu do caller gửi tùy ý không thay cho authorization.

### 10.2. Chặn hành vi ở URL và ở tầng nghiệp vụ

`authorizeHttpRequests` có thể kiểm tra request đã đăng nhập. Với các hành động nhạy cảm, `@EnableMethodSecurity` và `@PreAuthorize`/`AuthorizationManager` giúp đặt quy tắc gần service. Tuy vậy, biểu thức như `hasRole("ADMIN")` chỉ xét authority; các quyền theo ownership, tenant và trạng thái đối tượng vẫn cần kiểm tra dữ liệu thật.

Không sử dụng `@PreAuthorize` để bảo vệ một phương thức nếu đường gọi nội bộ cùng bean bỏ qua proxy mà thiết kế không lường trước. Test cả service authorization lẫn HTTP status.

### 10.3. DTO không giải quyết CSRF, CORS, injection hay mã hóa

- **CSRF**: trình duyệt có thể tự gửi cookie hoặc Basic credentials; thao tác không an toàn cần chính sách CSRF phù hợp. Demo giữ CSRF và kiểm bằng `csrf()`.
- **CORS**: hạn chế origin của trình duyệt, không phải cơ chế thay thế authorization. Tắt CORS không chặn `curl`; bật CORS cho origin không có nghĩa dữ liệu được phép xem.
- **SQL injection**: dùng prepared statements/ORM tham số hóa, dù input đã vào DTO.
- **XSS**: output DTO giảm dữ liệu trả về nhưng không thay escaping phù hợp khi frontend render HTML.
- **Mật khẩu/token**: không trả bí mật qua DTO; vẫn cần hashing/encryption, TLS, phân quyền lưu trữ và không log nhạy cảm.
- **File upload**: một DTO có metadata file không thay việc kiểm kích thước, định dạng, lưu trữ an toàn và quét nội dung.

## 11. Cách chọn DTO trong API thật

Khi triển khai một endpoint, trước khi viết code hãy tạo **bảng hợp đồng**:

1. **Đối tượng và hành động**: tạo, xem, cập nhật toàn phần, cập nhật một phần, xóa hay quản trị.
2. **Actor/audience**: anonymous, chủ tài khoản, người cùng tenant, người hỗ trợ, admin.
3. **Input allowlist**: tên trường, kiểu, bắt buộc hay optional, ràng buộc giá trị và nguồn dữ liệu đáng tin cho trường server-owned.
4. **Output allowlist**: tên trường được phép công bố, quy tắc field-level authorization, điều kiện privacy.
5. **Quyết định quyền**: xác thực, object ownership, role/permission, tenant, trạng thái nghiệp vụ.
6. **Mapping**: input DTO → command/update từng field → domain; domain/query projection → response DTO.
7. **Bản chất lỗi**: 400 malformed/invalid input, 401 chưa xác thực, 403 thiếu quyền, 404 không tìm thấy/không được lộ, 409 xung đột trạng thái nếu phù hợp.
8. **Kiểm thử âm**: overposting, field lạ, field bí mật trong JSON response, người dùng khác, tenant khác, thiếu CSRF, null/blank, nested object.
9. **Vận hành**: audit, log redaction, cache, giới hạn request size, versioning, thay đổi schema.

Ví dụ `POST /orders`: client gửi `productId` và `quantity`. Server lấy `unitPrice` từ catalog, tính `totalPrice`, gán `ownerId` từ principal và giữ `paid=false` đến khi nhận sự kiện thanh toán đáng tin. Response trả `orderId`, trạng thái và tổng giá theo hợp đồng; không trả số tài khoản nội bộ hoặc token xử lý thanh toán. Nếu DTO chứa `paid` dù service “hy vọng frontend không gửi”, một lần refactor mapper có thể mở ra lỗ hổng.

## 12. Những lỗi thường gặp và cách tránh

1. **Trả thẳng JPA entity**: vô tình lộ field bí mật, quan hệ lồng nhau, lazy loading hoặc vòng lặp JSON. Dùng response DTO/projection.
2. **Nhận entity từ `@RequestBody` rồi `save`**: client sửa field hệ thống. Dùng input DTO hẹp và cập nhật từng field.
3. **Dùng duy nhất một `AccountDto` cho mọi endpoint**: field cần cho admin vô tình chấp nhận ở public API. Tách contract theo thao tác/audience.
4. **Tin rằng `@Valid` thay authorization**: request hoàn toàn hợp lệ về định dạng vẫn có thể thay dữ liệu của người khác. Kiểm tra ownership và tenant.
5. **Dùng `BeanUtils.copyProperties` vô điều kiện**: mapping theo tên có thể thêm field mới ngoài ý muốn. Dùng mapper allowlist tường minh.
6. **Chỉ dùng `@JsonIgnore` trên entity để chống rò rỉ**: field mới có thể bị quên. Output DTO giới hạn field từ thiết kế.
7. **Chỉ ẩn field trên frontend**: JSON vẫn bị lộ. Kiểm soát tại backend.
8. **Tưởng `@InitBinder#setAllowedFields` điều khiển JSON `@RequestBody`**: JSON do Jackson deserialize, phải kiểm soát riêng.
9. **Không phân biệt omit với `null` trong PATCH**: ghi đè các field không chủ đích. Dùng PATCH DTO/operation model rõ ràng.
10. **Cho client chọn `ownerId`/`tenantId`**: dễ tạo BOLA/IDOR. Lấy thông tin từ xác thực và xác minh với record thật.
11. **Trả nguyên validation exception**: có thể lộ giá trị nhạy cảm hoặc stack trace. Trả mã lỗi an toàn, ghi log đã redact.
12. **Không kiểm soát dữ liệu lồng nhau**: một trường DTO kiểu entity vẫn có thể lộ quan hệ. Dùng DTO con và mapping giới hạn độ sâu.
13. **Bỏ qua CSRF vì đang demo Basic**: PUT/POST từ browser dùng cookie/Basic vẫn có rủi ro; kiểm tra CSRF theo loại client.
14. **Tin rằng strict unknown JSON bảo vệ mọi thứ**: nếu DTO chứa `role` hoặc mapper cho phép ghi `admin` thì dù JSON hoàn toàn hợp lệ vẫn nguy hiểm.
15. **Quên data exposure trong list/export/log**: DTO dùng cho `GET /me` không tự áp dụng ở search API, CSV export, event payload và application logs. Kiểm tra từng ranh giới.

## 13. Khi ứng dụng sử dụng Spring WebFlux

Nguyên tắc DTO giữ nguyên, nhưng request được đọc qua HTTP message reader/codec của WebFlux, controller có thể làm việc với `Mono`/`Flux` và security sử dụng `SecurityWebFilterChain` thay cho servlet chain.

Ví dụ **fragment trong một controller WebFlux có service reactive sẵn**, không phải file Java độc lập:

```java
@PutMapping("/api/profile")
public Mono<ProfileResponse> update(
        @Valid @RequestBody UpdateProfileRequest input,
        Authentication authentication) {
    return service.updateSelf(authentication.getName(), input);
}
```

DTO input/output vẫn phải là các kiểu allowlist; mapping server-owned fields vẫn nằm trong service. Với WebFlux, lỗi validation thường có thể xuất hiện dưới dạng `WebExchangeBindException`; trong Spring MVC, `@Valid @RequestBody` không có `BindingResult` kèm theo thường dẫn tới `MethodArgumentNotValidException` (400). Phải dùng cơ chế error handling đúng stack. Tránh blocking JDBC trong event-loop và tránh `block()`/`subscribe()` thủ công trong reactive handler.

Nếu nhận request body dưới dạng `Mono<UpdateProfileRequest>`, cách kích hoạt và xử lý validation có thể khác chữ ký synchronous; kiểm thử pipeline thật. Dù chạy reactive, không nên deserialize JSON thành entity có field nhạy cảm.

## 14. Checklist và bài tập thực hành

### Checklist trước khi merge một API

- [ ] Mỗi endpoint nhận input DTO chỉ có field caller được phép gửi.
- [ ] Entity không được bind trực tiếp từ untrusted JSON/form vào thao tác lưu.
- [ ] Service chỉ sửa field thuộc allowlist và lấy `ownerId`, `role`, `paid`, timestamps từ nguồn tin cậy.
- [ ] Input có validation cần thiết và không nhầm validation với authorization.
- [ ] Response DTO chỉ chứa field đúng audience; không lộ hash, token, bí mật, field nội bộ hay quan hệ lồng nhạy cảm.
- [ ] Có object/tenant authorization độc lập với hình dạng DTO.
- [ ] Unknown field, missing field, null, PATCH semantics và nested objects có quy tắc rõ.
- [ ] Kiểm thử 400/401/403, CSRF, overposting, output exposure và user thuộc tenant khác.
- [ ] Log/exception/caching/export không vô tình xuất dữ liệu mà response DTO đã cố che.
- [ ] API contract được duy trì qua refactor model và khi thêm field mới.

### Tự luyện

1. Một API đổi tên nhận `@RequestBody UserEntity` với `role` và `isAdmin`. Hãy thiết kế lại `UpdateDisplayNameRequest` và cách service cập nhật để chống mass assignment.
2. Vì sao `@Email` trên DTO không chứng minh người dùng sở hữu email mới? Cần bổ sung luồng nào?
3. Một endpoint trả `OrderResponse(CustomerEntity customer)`. Vì sao vẫn có nguy cơ excessive data exposure dù lớp ngoài là DTO?
4. Khác biệt giữa `@JsonProperty(access = WRITE_ONLY)` và dùng riêng `CreateAccountRequest`/`AccountResponse` là gì?
5. Vì sao một request `PUT` có credentials đúng và DTO hợp lệ vẫn có thể nhận 403 trong demo? Khi nào có thể thiết kế CSRF khác?
6. Khi chuyển `PUT` sang `PATCH`, cần phân biệt thiếu field và field `null` thế nào để tránh ghi đè?
7. Vì sao kiểm tra `request.ownerId() == pathId` không giải quyết BOLA/IDOR?
8. Nếu một entity thêm trường `mfaSecret` trong migration, API nào an toàn hơn trước thay đổi đó: trả entity trực tiếp hay trả DTO tường minh? Giải thích bằng ranh giới serializer.

## 15. Tài liệu chính thức và khuyến nghị

- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP — API Security Top 10: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP — API Security Top 10: Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
- [Spring Framework — `@RequestBody` (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Framework — `@RequestBody` (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Jackson — `JsonProperty.Access`](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.3/com/fasterxml/jackson/annotation/JsonProperty.Access.html)

**Điểm ghi nhớ:** một DTO tốt thể hiện rõ dữ liệu đi **vào** và **ra** API. Cơ chế an toàn là **input allowlist + mapping tường minh + authorization ở service + output allowlist + kiểm thử âm**. Nếu entity thay đổi, những trường mới phải tiếp tục ở phía server cho tới khi được đưa vào hợp đồng API một cách chủ đích.
