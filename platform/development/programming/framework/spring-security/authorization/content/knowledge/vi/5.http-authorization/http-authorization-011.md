# Kiểm chứng một cấu hình HTTP tối thiểu bằng ma trận quyền — Spring Security

> **Mục tiêu:** Từ một cấu hình phân quyền HTTP ngắn, lập **ma trận người dùng × request × kết quả mong đợi**, chạy thử các trường hợp cho phép và từ chối, rồi tự động hóa bằng **Spring Security Test + MockMvc**. Bài dùng Java 17+, Spring Boot 3.x và Spring Security 6.x theo cấu hình Servlet; các ví dụ là ứng dụng học tập, không chứa cơ sở dữ liệu hoặc nghiệp vụ production.

## 1. Vì sao cần ma trận quyền thay vì chỉ đọc cấu hình?

Một đoạn `authorizeHttpRequests` có thể trông rất hợp lý nhưng vẫn chứa lỗi nghiêm trọng:

- Rule tổng quát `/api/**.authenticated()` được đặt trước rule `/api/admin/**.hasRole("ADMIN")`, vô tình cho user thường đi vào API quản trị.
- Chỉ test admin gọi endpoint admin trả 200 mà **không** test user thiếu quyền phải trả 403.
- Dùng `hasRole("ADMIN")` nhưng tài khoản thực chỉ có authority `ADMIN` thay vì `ROLE_ADMIN`.
- Bảo vệ `GET` nhưng để `POST`/`DELETE` đi qua một rule quá rộng.
- Đặt `anyRequest().permitAll()` làm fallback, khiến endpoint mới tự động được công khai.
- Test `POST` thiếu CSRF rồi kết luận nhầm 403 là do authorization; hoặc ngược lại, tắt CSRF chỉ để test đạt.

**Ma trận quyền** là một đặc tả kiểm thử độc lập với code cấu hình:

`expected(subject, httpMethod, path, context) → ALLOW / DENY`.

Khi đưa qua HTTP, ta còn phải dự đoán **status** và **phản hồi** theo cách xác thực. Ví dụ HTTP Basic thường cho **401** khi không có credential trên endpoint được bảo vệ, **403** với danh tính hợp lệ nhưng thiếu quyền, và **2xx** khi được phép. Với form login, yêu cầu chưa đăng nhập có thể **302 redirect**. Đừng coi 401/403 là hai loại role; chúng là kết quả xử lý HTTP sau các bộ lọc xác thực/phân quyền.

**Một bài kiểm chứng đạt chất lượng phải trả lời đủ bốn câu hỏi:**

1. Rule **nào được chọn** cho request cụ thể?
2. User thực sự có authority **nào**?
3. Kết quả mong đợi là **cho phép hay từ chối**, kể cả trường hợp thiếu đăng nhập?
4. Test có phát hiện được trường hợp **mở quyền ngoài ý muốn** hay không?

## 2. Đề bài minh họa: API báo cáo có 4 nhóm quyền

Giả sử ứng dụng có các endpoint sau:

| Request | Ý nghĩa | Quy tắc HTTP |
| --- | --- | --- |
| `GET /public/ping` | Kiểm tra sức khỏe công khai | `permitAll()` |
| `GET /api/me` | Xem danh tính của chính người gọi | `authenticated()` |
| `GET /api/reports/summary` | Xem báo cáo tổng hợp | `hasAuthority("report:read")` |
| `POST /api/reports` | Tạo bản nháp báo cáo | `hasAuthority("report:write")` |
| `GET /api/admin/audit` | Xem khu vực quản trị | `hasRole("ADMIN")` |
| `GET /api/unknown` | Endpoint chưa được phê duyệt chính sách | `anyRequest().denyAll()` |

Để cô lập chủ đề, ta **không sử dụng OAuth2/JWT, database hay nhiều SecurityFilterChain**. Người dùng mẫu có authority cụ thể:

| Chủ thể | Danh sách authority thực tế | Vai trò trong bài |
| --- | --- | --- |
| **Anonymous** | Chưa xác thực, không có quyền được cấp | Kiểm tra 401/public access |
| **Alice** | `report:read` | Chỉ đọc báo cáo |
| **Bob** | `report:read`, `report:write` | Đọc và tạo báo cáo |
| **Carol** | `ROLE_ADMIN` | Chỉ quản trị, **không tự được** đọc/ghi báo cáo |
| **Dave** | `ROLE_USER` | Chỉ là user đã đăng nhập |

Cố ý giữ **Carol chỉ có `ROLE_ADMIN`**. Trong Spring Security, `hasRole("ADMIN")` theo prefix mặc định là kiểm tra `ROLE_ADMIN`, chứ `ROLE_ADMIN` không tự cấp `report:read` hoặc `report:write`. Nếu muốn admin có thêm quyền nghiệp vụ, phải cấp các authorities đó hoặc cấu hình kế thừa/quy tắc phù hợp.

**Giả định chung của bài:** HTTP Basic đang được bật, endpoint `POST` dùng CSRF protection mặc định. Khi ma trận nói `POST` “đủ điều kiện CSRF”, tức request chứa token CSRF **hợp lệ**. Trường hợp thiếu token được kiểm tra riêng, không trộn với chính sách role/permission.

## 3. Xây ma trận quyền trước khi viết test

### 3.1. Ma trận ALLOW / DENY theo nghiệp vụ

Với các danh tính ở mục 2:

| Chủ thể | Public GET | Me GET | Summary GET | Reports POST* | Admin GET | Unknown GET |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Anonymous** | ALLOW | DENY | DENY | DENY | DENY | DENY |
| **Alice** | ALLOW | ALLOW | ALLOW | DENY | DENY | DENY |
| **Bob** | ALLOW | ALLOW | ALLOW | ALLOW | DENY | DENY |
| **Carol** | ALLOW | ALLOW | DENY | DENY | ALLOW | DENY |
| **Dave** | ALLOW | ALLOW | DENY | DENY | DENY | DENY |

`*` Cột `Reports POST` giả định request có CSRF token hợp lệ, vì kiểm thử đang **cách ly authorization khỏi CSRF**. Nếu thiếu CSRF token, Spring Security có thể chặn `POST` **trước** khi kiểm tra authority. Không dùng status 403 từ CSRF để kết luận rule `report:write` đã hoạt động.

Từ bảng có thể rút ra những test bảo mật quan trọng:

- Bob phải **được** `POST /api/reports` khi có CSRF hợp lệ; Alice phải **bị chặn** dù đã đăng nhập.
- Carol phải **được** xem admin, nhưng phải **bị chặn** ở summary vì không có `report:read`.
- Dave phải **được** xem `/api/me` nhưng **không** được xem report/admin.
- Bất kỳ user đã đăng nhập nào gọi `/api/unknown` đều bị từ chối, chứng minh fallback `denyAll()` hoạt động.
- Anonymous vẫn được gọi `/public/ping`; mọi endpoint còn lại yêu cầu bảo vệ phải từ chối.

### 3.2. Chuyển ma trận thành HTTP status trong cấu hình ví dụ

| Kết quả nghiệp vụ | Trạng thái HTTP kỳ vọng trong ví dụ |
| --- | --- |
| Cho phép `GET` | `200 OK` |
| Cho phép tạo báo cáo `POST` | `201 Created` — do controller demo trả |
| Chưa xác thực trên API bảo vệ | `401 Unauthorized` — vì dùng HTTP Basic |
| Đã xác thực nhưng thiếu authority | `403 Forbidden` |
| Đã xác thực nhưng vào rule `denyAll()` | `403 Forbidden` |
| Gửi `POST` không có CSRF token hợp lệ | `403 Forbidden` — **lỗi CSRF**, không chứng minh đã check authority |

Đây là **bảng kết quả dự kiến cho chính ứng dụng minh họa**, không phải khẳng định mọi cấu hình Spring Security đều có các status này. Với endpoint không có controller, URL đã bị deny có thể trả 403 **trước khi** Spring MVC trả 404. Để kiểm chứng fallback chắc chắn, ta tạo một controller `/api/unknown` nhưng vẫn yêu cầu security chặn.

### 3.3. Ma trận nên là “hợp đồng” với nhóm phát triển

Ma trận cần được thống nhất **trước** khi sửa cấu hình; nếu viết test dựa trên hành vi đang có, lỗi cấp quyền dễ bị coi nhầm là “kết quả mong muốn”. Đặc biệt, **test âm tính** quan trọng ngang test thành công. Ví dụ đặt `authenticated()` quá rộng lên đầu có thể làm nhiều test 200 vẫn đỗ, còn các test 403 sẽ bắt được lỗi.

Khi thiết kế API thật, có thể thêm cột `tenantId`, `ownerId`, trạng thái dữ liệu, HTTP method, loại token, thời hạn quyền và điều kiện ngữ cảnh. Ma trận HTTP trong bài chỉ kiểm **cấp quyền trên loại endpoint**; không thay thế kiểm tra quyền theo từng bản ghi.

## 4. Cấu hình `authorizeHttpRequests` tối thiểu

Định nghĩa theo thứ tự: công khai → endpoint nhạy cảm theo permission → khu vực admin → endpoint yêu cầu đăng nhập → fallback từ chối.

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/reports/summary")
        .hasAuthority("report:read")
    .requestMatchers(HttpMethod.POST, "/api/reports")
        .hasAuthority("report:write")
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/me").authenticated()
    .anyRequest().denyAll()
);
~~~

Đây là **fragment** cấu hình nằm bên trong một `SecurityFilterChain`; code đầy đủ nằm ở mục sau.

**Giải thích đúng thứ tự:**

1. `/public/ping` có một ALLOW rõ ràng và không cần credential.
2. `GET /api/reports/summary` yêu cầu authority chính xác `report:read`.
3. `POST /api/reports` yêu cầu authority chính xác `report:write`.
4. `/api/admin/**` theo `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` trong ví dụ.
5. `/api/me` yêu cầu danh tính được xác thực.
6. `anyRequest().denyAll()` chặn các URL chưa có chính sách.

Spring Security xét các cặp `RequestMatcher → AuthorizationManager` theo **thứ tự đã khai báo** và áp dụng **rule khớp đầu tiên**. Không có cơ chế “thử rule kế tiếp nếu rule đầu từ chối” ở danh sách này. Vì thế **không được** đặt `requestMatchers("/api/**").authenticated()` trước các rule permission/admin: nó có thể mở quá rộng mọi API cho bất kỳ user nào đã đăng nhập.

### Không nhầm các API nhìn giống nhau

- `hasRole("ADMIN")`: so khớp role theo quy ước tiền tố mặc định `ROLE_`.
- `hasAuthority("ROLE_ADMIN")`: so khớp authority **literal** `ROLE_ADMIN`.
- `hasAuthority("report:read")`: so khớp **literal** `report:read`.
- `authenticated()`: đã được xác thực, **không** đồng nghĩa có quyền đọc/ghi.
- `permitAll()`: chủ động công khai một route; không có nghĩa bỏ cả security filter chain.
- `denyAll()`: từ chối tường minh.
- `anyRequest()`: fallback ở **SecurityFilterChain đang được chọn**, không phải chính sách tự động cho mọi chain khác.

## 5. Ứng dụng Spring Boot Java 17+ chạy được

**Tạo project:** sử dụng Spring Initializr hoặc dự án Maven Spring Boot 3.x tương thích Java 17+, với dependencies:

- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-test` ở scope test;
- `spring-security-test` ở scope test để viết test `MockMvc` với helpers `httpBasic()` và `csrf()`.

Không cần bật `@EnableMethodSecurity` vì ví dụ này **chỉ kiểm chứng HTTP authorization**. Khi dùng policy ở service, phải thiết kế method/domain security riêng.

Tạo tệp **`src/main/java/com/example/matrix/MatrixApplication.java`**:

~~~java
package com.example.matrix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatrixApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/summary")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("report:write")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF: POST trong MockMvc test sẽ dùng csrf().
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("report:read", "report:write")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();

        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    @RestController
    static class DemoController {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/me")
        String me(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/api/reports/summary")
        String summary() {
            return "report summary";
        }

        @PostMapping("/api/reports")
        ResponseEntity<String> createReport() {
            // Minh họa kiểm tra quyền, chưa tạo bản ghi trong database.
            return ResponseEntity.status(HttpStatus.CREATED)
                .body("report created");
        }

        @GetMapping("/api/admin/audit")
        String audit() {
            return "audit log";
        }

        @GetMapping("/api/unknown")
        String unknown() {
            // Có controller thật nhưng phải bị denyAll() chặn ở security.
            return "must not be reached";
        }
    }
}
~~~

**Đọc kết quả cấp quyền:**

- Alice được tạo với `authorities("report:read")` nên không có `report:write` hay `ROLE_ADMIN`.
- Bob có đúng hai permission `report:read` và `report:write`.
- Carol dùng builder `roles("ADMIN")`, nên được gán `ROLE_ADMIN` theo prefix mặc định, **không tự có** các permission report.
- Dave dùng `roles("USER")`, chỉ có `ROLE_USER`.
- `httpBasic()` cho phép gửi credential qua header Basic để demo. Trong ứng dụng thật phải dùng HTTPS, không hardcode password.
- `PasswordEncoder` là BCrypt để lưu và đối chiếu mật khẩu demo phù hợp.
- `anyRequest().denyAll()` chặn `/api/unknown` dù controller tồn tại.
- Spring Security có CSRF protection mặc định ở cấu hình Servlet này. Vì vậy một `POST` từ `curl` không có CSRF token có thể trả 403 ngay cả khi Bob có `report:write`. Ta sẽ dùng `MockMvc` với `csrf()` để kiểm chứng permission theo cách có kiểm soát.

### Kết quả nào là của authorization, kết quả nào của controller?

Một rule `hasAuthority` đưa ra **ALLOW** cho Bob trên `POST /api/reports`, nhưng bản thân rule không tạo status 201. Controller `createReport()` mới là nơi **chọn `201 Created`**. Nếu controller ném ngoại lệ hoặc validation fail, response có thể không phải 201 dù authorization đã ALLOW. Vì vậy test quyền cần kết hợp assertion **status + body/side effect**, nhưng không nhầm ràng buộc nghiệp vụ với chính sách HTTP.

## 6. Chạy thủ công: các GET trước

Từ thư mục root của project Maven:

~~~bash
# macOS / Linux:
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt:
mvnw.cmd spring-boot:run
~~~

Khi ứng dụng chạy ở `http://localhost:8080`:

~~~bash
# Public
curl -i http://localhost:8080/public/ping

# Anonymous => 401 trên endpoint yêu cầu đăng nhập
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/reports/summary

# User có quyền đọc và user không có quyền đọc
curl -i -u alice:demo123 http://localhost:8080/api/reports/summary
curl -i -u dave:demo000 http://localhost:8080/api/reports/summary

# Admin thành công, user thường bị từ chối
curl -i -u carol:demo789 http://localhost:8080/api/admin/audit
curl -i -u bob:demo456 http://localhost:8080/api/admin/audit

# Fallback denyAll
curl -i -u carol:demo789 http://localhost:8080/api/unknown
~~~

Kỳ vọng:

| Lệnh tương ứng | Status / body |
| --- | --- |
| Public anonymous | `200` / `pong` |
| `/api/me` anonymous | `401` |
| Summary anonymous | `401` |
| Summary Alice | `200` / `report summary` |
| Summary Dave | `403` |
| Admin Carol | `200` / `audit log` |
| Admin Bob | `403` |
| Unknown Carol | `403` |

### Tại sao không lấy `curl -u bob:... -X POST` làm bằng chứng duy nhất?

Vì CSRF protection đang bật. Với một request POST không mang CSRF token hợp lệ, Spring Security có thể trả **403 trước khi đến `AuthorizationFilter`**. Kết quả đó **không chứng minh Bob thiếu `report:write`**. Một cách đúng trong kiểm thử là dùng `MockMvc` + `with(csrf())` để loại bỏ biến gây nhiễu, sau đó kiểm tra 201 đối với Bob và 403 đối với user thiếu quyền.

**Trong production**, cách cung cấp CSRF token phụ thuộc ứng dụng (session/cookie/token repository và client). Không nên tắt CSRF chung chỉ để request `curl` dễ thành công. Với API token-based stateless, quyết định bật/tắt CSRF cần dựa trên threat model và cách browser tự gửi credential, không dựa vào khẩu quyết “REST thì không có CSRF”.

## 7. Tự động hóa ma trận bằng MockMvc và HTTP Basic

### 7.1. Thêm dependencies kiểm thử

Kiểm tra `pom.xml` đã có dependency `spring-boot-starter-test` (thường được Initializr thêm khi chọn phần test). Thêm `spring-security-test` cùng phiên bản tương thích với Spring Security do Boot quản lý:

~~~xml
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
~~~

Các đoạn dependency là **phần tử con của `<dependencies>` trong `pom.xml`**, không phải một file XML hoàn chỉnh. Nếu project đã có starter-test, không thêm trùng.

### 7.2. Test class hoàn chỉnh chạy cùng ứng dụng

Tạo tệp **`src/test/java/com/example/matrix/HttpAuthorizationMatrixTest.java`**:

~~~java
package com.example.matrix;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationMatrixTest {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest(name = "{index}: {0} {2} {3} -> {4}")
    @CsvSource({
        // username, password, method, path, expected HTTP status
        "anonymous,none,GET,/public/ping,200",
        "anonymous,none,GET,/api/me,401",
        "anonymous,none,GET,/api/reports/summary,401",
        "anonymous,none,POST,/api/reports,401",
        "anonymous,none,GET,/api/admin/audit,401",
        "anonymous,none,GET,/api/unknown,401",

        "alice,demo123,GET,/public/ping,200",
        "alice,demo123,GET,/api/me,200",
        "alice,demo123,GET,/api/reports/summary,200",
        "alice,demo123,POST,/api/reports,403",
        "alice,demo123,GET,/api/admin/audit,403",
        "alice,demo123,GET,/api/unknown,403",

        "bob,demo456,GET,/public/ping,200",
        "bob,demo456,GET,/api/me,200",
        "bob,demo456,GET,/api/reports/summary,200",
        "bob,demo456,POST,/api/reports,201",
        "bob,demo456,GET,/api/admin/audit,403",
        "bob,demo456,GET,/api/unknown,403",

        "carol,demo789,GET,/public/ping,200",
        "carol,demo789,GET,/api/me,200",
        "carol,demo789,GET,/api/reports/summary,403",
        "carol,demo789,POST,/api/reports,403",
        "carol,demo789,GET,/api/admin/audit,200",
        "carol,demo789,GET,/api/unknown,403",

        "dave,demo000,GET,/public/ping,200",
        "dave,demo000,GET,/api/me,200",
        "dave,demo000,GET,/api/reports/summary,403",
        "dave,demo000,POST,/api/reports,403",
        "dave,demo000,GET,/api/admin/audit,403",
        "dave,demo000,GET,/api/unknown,403"
    })
    void fullMatrix(
            String username,
            String password,
            String httpMethod,
            String path,
            int expectedStatus
    ) throws Exception {
        MockHttpServletRequestBuilder request =
            "POST".equals(httpMethod) ? post(path) : get(path);

        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }

        // Token hợp lệ để đo quyền POST, không nhầm 403 do CSRF.
        if ("POST".equals(httpMethod)) {
            request.with(csrf());
        }

        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void bobCanCreateWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("bob", "demo456"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("report created"));
    }

    @Test
    void bobPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("bob", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminDoesNotAutomaticallyHaveReportPermission() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void fallbackDeniesEvenAnAdmin() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedEndpointReturnsPrincipal() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isOk())
            .andExpect(content().string("dave"));
    }

    @Test
    void unexpectedMethodOnReportCollectionIsDenied() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Tại sao chọn `httpBasic()` thay vì chỉ `@WithMockUser`?** `httpBasic()` gửi header Basic trong request MockMvc, để cấu hình xác thực với user demo thực sự tham gia cấp `GrantedAuthority`. `@WithMockUser` rất hữu ích để kiểm tra rule riêng, nhưng không chứng minh đúng password encoder hoặc ánh xạ authority của `UserDetailsService`. Cả hai kỹ thuật đều có chỗ dùng; với bài này, test đi qua credential mẫu tạo độ tin cậy cao hơn.

**Lưu ý phần test:** `MockMvc` đi qua Spring Security filter chain nhưng không mở server TCP như `curl`. `csrf()` tạo request token hợp lệ cho kiểm thử; nó **không** có nghĩa client production có thể tự chế token. Các assertion 401/403 giả định cấu hình HTTP Basic và Spring Security filter chain của **ứng dụng mẫu**.

### 7.3. Chạy test

~~~bash
# macOS / Linux
./mvnw test

# Windows PowerShell / Command Prompt
mvnw.cmd test
~~~

Khi có dependency/test class đúng và không có thay đổi khác, toàn bộ các trường hợp của ma trận **được kỳ vọng vượt qua**. Để xác nhận số trường hợp, `@CsvSource` gồm **30 hàng** (5 chủ thể × 6 request), và còn 7 phương thức `@Test` bổ sung. Không cần tin vào tổng số test hiển thị cố định nếu Maven Surefire/JUnit phiên bản khác xuất báo cáo theo cách khác; kiểm tra kết quả từng ca và exit code.

**Không bịa output test:** phần demo không cố định timestamp, thời gian thực thi, phiên bản dependency hoặc số lượng dòng log. Sau khi chạy thực tế, **exit code 0** và báo cáo không có failed/error tests mới là bằng chứng chính.

## 8. Đọc từng hàng ma trận như một bằng chứng

Một bảng test pass toàn bộ vẫn cần biết **vì sao** từng kết quả có ý nghĩa.

### 8.1. Anonymous trên route công khai và bảo vệ

- Anonymous gọi `GET /public/ping` → **200** do `permitAll()`.
- Anonymous gọi `GET /api/me` → **401** do `authenticated()` với HTTP Basic.
- Anonymous gọi `GET /api/reports/summary` → **401** vì chưa có danh tính hợp lệ để xét `report:read`.
- Anonymous gọi `POST /api/reports` trong test có `csrf()` → **401**, để quan sát authentication/authorization thay vì CSRF.
- Anonymous gọi `/api/unknown` → bị `denyAll()`. Với HTTP Basic, `ExceptionTranslationFilter` có thể dùng entry point cho anonymous, tạo **401**; trên tài khoản đã xác thực, trường hợp này được kiểm riêng và cho **403**.

### 8.2. Alice và Bob: test permission chuyên biệt

- Alice có `report:read` → Summary GET **200**.
- Alice không có `report:write` → Reports POST **403** (dù có CSRF token hợp lệ).
- Bob có cả hai → Summary GET **200** và Reports POST **201**.
- Bob gọi Reports POST **không** có CSRF token → **403**; đây là lý do một test chỉ quan sát 403 có thể đưa ra kết luận sai. Cần có test **Bob + valid CSRF = 201** để chứng minh rule write hoạt động.

### 8.3. Carol: admin không tự có mọi permission

- Carol `ROLE_ADMIN` → Admin GET **200**.
- Carol không có `report:read` → Summary GET **403**.
- Carol không có `report:write` → Reports POST **403**.

Điểm này bảo vệ hệ thống khỏi giả định “admin luôn có tất cả quyền” khi chính sách chưa định nghĩa như vậy. Nếu nghiệp vụ cần admin xem báo cáo, hãy **cấp authority tường minh** hoặc thiết kế một rule kết hợp được kiểm thử, không chèn thêm `permitAll()`.

### 8.4. Dave: đăng nhập không đồng nghĩa với quyền nghiệp vụ

- Dave có `ROLE_USER` → `GET /api/me` **200**.
- Dave thiếu `report:read`, `report:write`, `ROLE_ADMIN` → cả ba nhóm API nhạy cảm đều **403**.

Nếu Dave bất ngờ được 200 ở Summary, có khả năng matcher chung `/api/**.authenticated()` đã che mất rule report hoặc có cấu hình khác cấp sai quyền.

### 8.5. Fallback

`GET /api/unknown` có controller nhưng **không có rule permit**: mọi user đã xác thực phải bị **403** nhờ `anyRequest().denyAll()`. Nó là bài test đặc biệt quan trọng để bảo vệ khi nhóm phát triển thêm route mới trong tương lai.

## 9. Kiểm tra thứ tự rule và nguy cơ che khuất

Một cấu hình dễ mắc lỗi:

~~~java
// KHÔNG DÙNG — chỉ để nhận diện lỗi.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/reports/summary")
        .hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

Dòng `/api/**.authenticated()` đứng trước khiến:

- Dave đã đăng nhập có thể qua HTTP check của `/api/admin/audit`.
- Dave đã đăng nhập có thể qua HTTP check của Summary GET.
- Các rule admin/report phía sau trở thành **không tới được** cho những request đó.

**Test âm tính** `Dave Summary GET = 403` và `Dave Admin GET = 403` lập tức phát hiện sự suy yếu này. Test “Bob Summary = 200” hoặc “Carol Admin = 200” **không đủ** để phát hiện lỗi.

Một biến thể sai khác:

~~~java
// KHÔNG DÙNG: fallback cho phép tất cả.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/ping").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().permitAll()
);
~~~

Nếu dùng như vậy, `/api/unknown` và cả route chưa khai báo đều được **ALLOW**. Test fallback cho user và anonymous sẽ phát hiện lỗi.

**Quy tắc review:** khi một matcher rộng hơn có thể khớp cùng request với matcher cụ thể, phải đặt rule cụ thể trước hoặc làm rõ design. Spring Security không tự chọn matcher “đẹp nhất”; nó **áp dụng match đầu tiên**.

## 10. Kiểm thử theo phương thức HTTP: GET và POST không tương đương

Hai request cùng prefix có thể cần quyền hoàn toàn khác nhau:

| HTTP request | Action nghiệp vụ | Authority cần |
| --- | --- | --- |
| `GET /api/reports/summary` | Đọc tổng hợp | `report:read` |
| `POST /api/reports` | Tạo báo cáo | `report:write` |
| `GET /api/reports` | Không được khai báo trong bài | Fallback DENY |
| `DELETE /api/reports/42` | Chưa được cho phép | Fallback DENY |

**Không thay rule method-specific bằng `requestMatchers("/api/reports/**").authenticated()` ở phía trên.** Vì sự khớp đầu tiên của pattern rộng này có thể cho user chỉ đăng nhập đi qua toàn bộ luồng HTTP authorization.

Với thao tác ghi thật, thường cần thêm:

- Kiểm tra user có quyền trên **resource instance** hay không (tenant, owner, trạng thái).
- CSRF nếu xác thực bằng session/cookie và browser tự gửi credential.
- Validation input, idempotency/transaction, audit, chống race condition, không để lộ dữ liệu qua lỗi.
- Kiểm thử mọi method liên quan: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, kể cả method chưa hỗ trợ.

Ở demo, `POST` trả 201 nhưng **không lưu dữ liệu**. Không diễn giải ví dụ như dịch vụ báo cáo production.

## 11. Test 403 do CSRF khác 403 do thiếu quyền

Trong Spring Security Servlet, CSRF filter thường xử lý các HTTP method không được xem là “safe”. Một request như:

~~~bash
curl -i -u bob:demo456 -X POST http://localhost:8080/api/reports
~~~

có thể trả **403** vì không có CSRF token hợp lệ, **dù** Bob có `report:write`. Nếu chỉ nhìn status và kết luận “Bob không có quyền”, bài test đã nhầm **bộ lọc bảo vệ request** với **authorization rule**.

Hai phép thử có ý nghĩa khác nhau:

~~~java
// Test permission: cung cấp token CSRF hợp lệ.
mvc.perform(post("/api/reports")
        .with(httpBasic("bob", "demo456"))
        .with(csrf()))
    .andExpect(status().isCreated());

// Test CSRF: cố ý thiếu token.
mvc.perform(post("/api/reports")
        .with(httpBasic("bob", "demo456")))
    .andExpect(status().isForbidden());
~~~

Bộ test tốt cần cả **Bob có token và được tạo** lẫn **Alice có token nhưng thiếu authority nên bị chặn**. Test thiếu token chỉ chứng minh chính sách CSRF đang hoạt động.

Đối với các API không dùng cookie/session và có bearer token được client chủ động thêm vào header, threat model có thể khác. Không tự tắt CSRF ở toàn ứng dụng chỉ vì đang dùng REST; hãy đánh giá nguồn credential và sự hỗ trợ của browser.

## 12. Ma trận thực tế: tách HTTP, method và dữ liệu

Ví dụ một user có `report:read` được gọi `GET /api/reports/{id}`. HTTP có thể **ALLOW** trên loại endpoint, nhưng user không nhất thiết được xem **mọi báo cáo**. Mô hình bảo vệ nhiều tầng:

~~~text
Request GET /api/reports/42
    |
    v
HTTP authorization: authenticated + report:read?
    |  DENY -> chặn
    v  ALLOW
Method/domain authorization: report 42 thuộc tenant/owner hợp lệ?
    |  DENY -> chặn
    v  ALLOW
Nạp/đọc dữ liệu được phép -> Response
~~~

Nếu ứng dụng có multi-tenant hoặc dữ liệu nhạy cảm, test matrix cần bổ sung:

| User | Permission | Report | Tenant/owner | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Alice | `report:read` | Report 42 | Cùng tenant và được chia sẻ | ALLOW |
| Alice | `report:read` | Report 99 | Tenant khác | DENY |
| Dave | Không có `report:read` | Report 42 | Dù cùng tenant | DENY |
| Bob | `report:write` | Report 42 | Trạng thái khóa | DENY cho thao tác sửa nếu policy cấm |

Cấu hình mẫu **không tự thực hiện** các kiểm tra tenant/owner/state. Đây là **hướng mở rộng**, không nên suy diễn rằng ma trận HTTP đã kiểm chứng được toàn bộ authorization trên từng bản ghi.

Với `LIST/SEARCH`, phải lọc phạm vi dữ liệu trong truy vấn; chỉ chặn một ID sau khi đã tải cả danh sách có thể làm lộ dữ liệu qua kết quả, phân trang hoặc số lượng bản ghi.

## 13. Khi có nhiều SecurityFilterChain

Bài mẫu dùng **một chain** để đơn giản hóa bằng chứng. Với nhiều chain, có **hai tầng chọn đầu tiên**:

1. `FilterChainProxy` chọn **SecurityFilterChain đầu tiên** có matcher khớp request, xét theo thứ tự ưu tiên như `@Order`.
2. Bên trong chain được chọn, `AuthorizationFilter` áp dụng **rule đầu tiên khớp** của `authorizeHttpRequests`.

`http.securityMatcher("/api/**")` giới hạn phạm vi **cả chain**; còn `authorizeHttpRequests().requestMatchers("/api/admin/**")` chỉ phân loại request **bên trong chain đã được chọn**.

Nếu chỉ có chain `securityMatcher("/api/**")`, các URL khác có thể không được Spring Security bảo vệ nếu không có fallback chain. `anyRequest().denyAll()` bên trong API chain **không tự phủ** URL nằm ngoài `/api/**`.

Khi chuyển ứng dụng thực sang nhiều chain, mở rộng ma trận thêm cột **Chain được chọn** và viết integration test cho URL khớp cả hai chain, chỉ khớp một chain, hoặc không khớp chain nào. Không mặc định các chain “cộng thêm quyền” cho cùng request.

## 14. Một quy trình review có thể lặp lại

Để kiểm chứng một cấu hình HTTP mới hay sau mỗi lần thay đổi:

1. **Liệt kê endpoint và method**: public, login, resource read/write, admin, fallback.
2. **Liệt kê danh tính mẫu**: anonymous, user thường, read-only, writer, admin; ghi rõ authority literal.
3. **Chốt ma trận ALLOW/DENY** cùng người phụ trách nghiệp vụ và bảo mật **trước khi viết test**.
4. **Chuyển thành status kỳ vọng** cho cơ chế xác thực đang dùng; tách CSRF, validation, controller response.
5. **Viết rule cụ thể trước, fallback từ chối cuối**; tránh matcher trùng hoặc quá rộng.
6. **Viết test dương tính và âm tính** cho mọi đường giao nhau giữa các matcher.
7. **Thử sai thứ tự có chủ đích** trên nhánh thử nghiệm hoặc test cục bộ để xác minh test âm tính có thể phát hiện lỗi (*mutation thought experiment*); không triển khai cấu hình sai.
8. **Chạy lại suite** mỗi khi thêm endpoint, role, permission, filter chain hoặc đổi authentication mechanism.
9. **Đọc log kết quả** để phân biệt failure của HTTP authorization, authentication, CSRF, controller và domain policy.
10. **Không đổi kỳ vọng chỉ để làm test xanh**: mọi thay đổi ma trận phải được duyệt theo chính sách nghiệp vụ.

### Checklist kiểm tra nhanh

- Mỗi endpoint quan trọng có matcher phù hợp và thứ tự không bị che khuất?
- `ROLE_ADMIN` và `report:read`/`report:write` được cấp chính xác như bảng?
- Public route có `permitAll()` chủ đích, không bị `denyAll()` phía trước?
- Endpoint mới/chưa khai báo bị deny theo fallback?
- Test anonymous, 401, wrong password, 403 thiếu role/authority, 200/201 hợp lệ?
- Với POST, có cả test **CSRF hợp lệ** và **thiếu CSRF**?
- Test role admin **không** mặc nhiên có mọi permission?
- Có bảo vệ bổ sung theo tenant/owner cho dữ liệu nhạy cảm?
- Nếu nhiều filter chain, biết chain nào được chọn?
- Dữ liệu mẫu và mật khẩu có được tách khỏi cấu hình production?

## 15. Tự đánh giá

**Câu 1.** Dave đã đăng nhập và chỉ có `ROLE_USER`. `GET /api/me` kỳ vọng gì?  
**Đáp án:** **200**, vì rule `authenticated()` không yêu cầu permission nghiệp vụ khác.

**Câu 2.** Dave gọi `GET /api/reports/summary`?  
**Đáp án:** **403**, vì thiếu `report:read`, dù đã đăng nhập.

**Câu 3.** Carol có `ROLE_ADMIN`. Carol có tự được gọi `POST /api/reports` không?  
**Đáp án:** **Không** theo chính sách mẫu; `report:write` là authority khác và chưa được cấp.

**Câu 4.** Bob gửi POST có đúng `report:write` nhưng thiếu CSRF token?  
**Đáp án:** **403** có thể đến từ CSRF filter; không thể kết luận quyền write sai. Cung cấp CSRF token hợp lệ khi kiểm chứng authorization.

**Câu 5.** Anonymous gọi `/api/reports/summary` dưới HTTP Basic?  
**Đáp án:** **401**, vì route bảo vệ cần authentication để xét authority.

**Câu 6.** Một controller `/api/unknown` tồn tại nhưng không có allow rule. Có thể truy cập không?  
**Đáp án:** Không. `anyRequest().denyAll()` chặn; với người dùng đã xác thực, ví dụ trả **403**.

**Câu 7.** Đặt `requestMatchers("/api/**").authenticated()` trước `/api/admin/**.hasRole("ADMIN")` gây hậu quả gì?  
**Đáp án:** Admin rule bị che khuất; user thường đã đăng nhập có thể qua tầng HTTP authorization cho khu vực admin.

**Câu 8.** Tại sao test “Carol vào admin = 200” chưa đủ?  
**Đáp án:** Vì một rule quá rộng cũng có thể làm Carol được 200; cần test “Bob/Dave vào admin = 403” mới chứng minh chỉ admin được phép.

**Câu 9.** `@WithMockUser(authorities = "report:read")` và `httpBasic("alice","demo123")` chứng minh giống nhau không?  
**Đáp án:** Không hoàn toàn. Mock user dựng sẵn Authentication; HTTP Basic đi qua việc xử lý credential và nguồn cấp user/authorities. Kết hợp hợp lý hai cách test.

**Câu 10.** Ma trận HTTP chứng minh Alice chỉ được đọc báo cáo thuộc tenant của mình chưa?  
**Đáp án:** Chưa. Quy tắc HTTP kiểm soát endpoint/permission. Cần thêm kiểm tra và test dữ liệu theo tenant/ownership cho resource instance.

**Ghi nhớ:** **Ma trận quyền là hợp đồng kiểm thử của phân quyền HTTP**. Cấu hình đúng cần matcher đúng thứ tự, authority rõ ràng, default deny và các test cho cả **ALLOW đúng** lẫn **DENY đúng**. Với `POST`, kiểm chứng quyền phải **tách khỏi CSRF** để tránh kết luận sai.

## Tài liệu chính thức

- Spring Security — Authorize HTTP Requests (first-match, authorization methods và default deny): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Test with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Java Configuration (SecurityFilterChain và `securityMatcher`): https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Method Security (bảo vệ nghiệp vụ bên dưới HTTP): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
