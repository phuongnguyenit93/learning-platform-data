# Tài liệu hóa những cơ chế được tắt cùng lý do và kiểm thử bù đắp

> **Phạm vi:** Spring Security fundamentals, nhóm **Thiết kế ứng dụng**. Hướng dẫn ghi nhận mọi quyết định tắt hoặc nới lỏng cơ chế bảo mật, nêu rõ **baseline, thay đổi, lý do, ranh giới, rủi ro, kiểm soát bù đắp, bằng chứng kiểm thử, người chịu trách nhiệm, hạn xem xét và cách hoàn nguyên**. Ví dụ thực hành sử dụng Java 17, Spring Boot 3.3.5, Spring Security 6.x, JUnit 5 và MockMvc cho Servlet/Spring MVC.

## 1. Một cơ chế bị tắt là một quyết định thiết kế, không phải cách “sửa” 401/403

Ứng dụng thật có nhiều loại client và trust boundary. Browser sử dụng cookie/session có nguy cơ CSRF; service-to-service có thể dùng Bearer token, mTLS hoặc chữ ký; API công khai cần `permitAll», trong khi chức năng quản trị vẫn cần role. Một ứng dụng API-only có thể tắt HTML form login nếu dùng một cơ chế xác thực thay thế. Một trang cần iframe có thể điều chỉnh framing nhưng không được bỏ luôn tất cả security response headers.

Chỉ có test “endpoint trả 200” không đủ để chứng minh an toàn. Cần có test **âm**: request không credential, credential sai, role sai, CSRF token thiếu, endpoint ngoài scope và policy header bị mở quá rộng phải bị chặn. Đồng thời phải chứng minh cơ chế thay thế hoạt động và không làm mất các kiểm soát độc lập.

**Quy tắc thực hành:** nếu một security setting bị tắt, nới lỏng hoặc bỏ qua, hãy có hồ sơ ngoại lệ trước khi merge; code chỉ thay đổi đúng phạm vi; test bảo vệ baseline bên ngoài; owner và reviewer có cơ chế xác định khi nào phải khôi phục.

### Những thay đổi thường bị nhầm lẫn

| Thay đổi | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `formLogin(AbstractHttpConfigurer::disable)» | Tắt endpoint/form login tạo bởi Spring Security | Phải có authentication thay thế thật sự |
| `httpBasic(AbstractHttpConfigurer::disable)» | Tắt HTTP Basic | Client đang dùng Basic có thể không đăng nhập được |
| `csrf(AbstractHttpConfigurer::disable)» | Bỏ bảo vệ CSRF trong chain | Nguy hiểm nếu browser còn ambient credentials |
| `csrf(...ignoringRequestMatchers(...))» | Chỉ ngoại lệ các request được match | Matcher mở rộng ngoài ý muốn có thể tạo lỗ hổng |
| `authorizeHttpRequests(...permitAll())» | Một route không cần authorization check | Không tự tắt CSRF, headers, các filter còn lại |
| `web.ignoring()» | Bỏ request khỏi Spring Security filter chain | Có thể mất luôn những lớp bảo vệ/security headers |
| `headers(...disable)» | Bỏ security response headers | Browser mất các chính sách chống framing, MIME sniffing... |
| CORS quá rộng | Cho JS từ origin khác đọc response | Không thay thế xác thực hay CSRF |
| `SessionCreationPolicy.STATELESS» | Không tạo/dùng session cho SecurityContext theo policy | Không tự bảo đảm token đúng hay không có CSRF risk |
| Bỏ `@EnableMethodSecurity» | Method security annotation có thể không có hiệu lực | Service logic bị gọi ngoài HTTP route có thể bypass |

**Khác biệt quan trọng:** một public URL nên được `permitAll» nếu đó thực sự là public, nhưng không nên tự ý dùng `web.ignoring» chỉ vì muốn người dùng anonymous có thể gọi URL. Với endpoint machine-to-machine, có thể thiết kế security chain riêng, nhưng kiểm tra cả nơi filter bắt đầu và nơi quyết định được đưa ra.

## 2. Cách quyết định ngoại lệ theo mô hình đe dọa

Trước khi thay đổi, trả lời bằng văn bản:

1. Ai là caller: browser, service account, mobile app, partner, scheduler?
2. Credential được gửi ra sao: cookie/session, HTTP Basic, Authorization Bearer, client certificate, HMAC?
3. Browser có tự gắn credential vào request không? Đây là câu hỏi đặc biệt quan trọng với CSRF.
4. Resource có thay đổi dữ liệu, cấp quyền, tải thông tin nhạy cảm hay chỉ là GET công khai?
5. Quyền được quyết định ở filter, method security, gateway hay ứng dụng nội bộ?
6. Có TLS ở đường từ client tới gateway và gateway tới backend không? Proxy nào được tin?
7. Kiểm soát bù đắp chạy phía server hay chỉ dựa vào client “sẽ gửi đúng”?
8. Khi identity service, secret manager hoặc policy service không phản hồi, request có **fail closed** không?
9. Có thể audit, metric, giới hạn tải và rollback khi điều kiện giả định thay đổi không?
10. Có bằng chứng test trực tiếp của flow thật thay vì chỉ mock Authentication không?

Không coi “REST API”, “stateless”, “chỉ chạy nội bộ”, “đã có WAF”, “đã bật CORS” hoặc “đã có HTTPS” là lý do tự đủ để bỏ một kiểm soát độc lập. Chẳng hạn HTTPS mã hóa kết nối nhưng không chứng minh người gửi webhook; CORS là chính sách browser về cross-origin reading chứ không ngăn mọi request thay đổi trạng thái.

## 3. Hồ sơ ngoại lệ bảo mật (Security Exception Register)

Một hồ sơ nên ở repository có version control hoặc hệ thống quản trị thay đổi có lịch sử và quyền phê duyệt. Không cần văn bản dài lê thê nhưng phải trả lời được **tại sao quyết định tồn tại và còn an toàn đến hôm nay hay không**.

| Trường | Nội dung cần ghi |
| --- | --- |
| `exception_id» | Mã ID, liên kết code/comment/PR/test |
| `system/component» | Service, security chain, environment và dependency version |
| `control_baseline» | Cơ chế bảo vệ mặc định hoặc yêu cầu trong chuẩn nội bộ |
| `deviation» | Cấu hình/đoạn code tắt hoặc nới lỏng chính xác |
| `scope» | HTTP method, path, audience/client/tenant, môi trường |
| `business_reason» | Yêu cầu và phương án đã cân nhắc |
| `threats» | Tấn công khả thi sau khi bỏ cơ chế |
| `assumptions» | Điều kiện phải luôn đúng về client, credential, proxy |
| `compensating_controls» | Các kiểm soát khác thực sự được **server xác minh** |
| `positive_tests» | Trường hợp hợp lệ vẫn hoạt động |
| `negative_tests» | Trường hợp không hợp lệ hoặc ngoài phạm vi bị chặn |
| `evidence» | CI run, git commit, config version và môi trường đã thử |
| `owner/approver» | Người chịu trách nhiệm và người chấp nhận rủi ro |
| `effective/review/expiry» | Thời điểm áp dụng, hạn xét lại và trigger thu hồi |
| `monitoring» | Logs, audit events, counters, alerts phù hợp |
| `rollback» | Điều kiện và thao tác khôi phục baseline |
| `residual_risk» | Rủi ro vẫn còn và được chấp nhận ở mức nào |

### Mẫu hồ sơ cho một ứng dụng chỉ cung cấp API

Ở đây ta lựa chọn một thay đổi có phạm vi dễ chứng minh: **tắt HTML form login**, nhưng giữ HTTP Basic cho demo API, giữ CSRF và security headers. HTTP Basic ở môi trường thật phải dùng **TLS**, kiểm soát mật khẩu, throttling và xác thực phù hợp. Trong hệ thống production, OAuth2/OIDC Bearer hoặc mTLS có thể là lựa chọn phù hợp hơn tùy client.

```markdown
# SEC-EXC-API-001 — No generated HTML form login

- Status: PROPOSED (mẫu minh họa, chưa phải phê duyệt sản xuất)
- Baseline: Spring Security form login may be available when configured
- Deviation: explicitly disable formLogin; API accepts HTTP Basic in demo
- Client: non-browser API client controlled by application owner
- Reason: no interactive HTML login page is provided
- In-scope: generated form-login mechanism only
- Not disabled: authentication, authorization, CSRF, security headers
- Threat introduced: losing authentication if replacement is misconfigured
- Compensating controls: authenticated HTTP Basic with BCrypt user store;
  HTTPS requirement in deployment; explicit route policy and deny-all fallback
- Positive evidence:
  - valid API user GET /api/me -> 200
  - authorized report reader GET /api/reports -> 200
- Negative evidence:
  - anonymous protected GET -> 401
  - wrong Basic password -> 401
  - insufficient authority -> 403
  - unsafe POST missing/invalid CSRF -> 403
  - generated /login is not usable as an authentication entry
  - default security headers remain present
- Owner role: API platform owner
- Reviewer role: application security reviewer
- Review trigger: browser clients, credential model, gateway or route changes
- Deployment precondition: HTTPS, secret storage, audit and rate controls
- Rollback: restore form login only after reviewing intended login UX
```

Đây là **mẫu**, không phải phê duyệt thực tế. Trong dự án, gán người cụ thể cho owner/approver, link PR và test evidence đúng commit/deployment. Nếu hệ thống đưa browser client có cookie vào API, cần đánh giá lại CSRF, authentication method và threat model thay vì tiếp tục dùng lý do “API-only” từ một phiên bản cũ.

## 4. Từ hồ sơ sang kiểm thử: có “cho phép” và “từ chối”

Ma trận test phải minh họa đúng ranh giới của quyết định.

| Endpoint | User và credential | CSRF | Quyết định cần chứng minh |
| --- | --- | --- | --- |
| GET /public | Anonymous | Không cần | 200, chỉ resource được định danh là public |
| GET /api/me | Anonymous | Không cần | 401, API không mở vì tắt form |
| GET /api/me | Sai Basic password | Không cần | 401, provider xác thực thật |
| GET /api/me | Basic user hợp lệ | Không cần | 200, trả đúng identity |
| GET /api/reports | Không có `SCOPE_reports.read» | Không cần | 403 |
| GET /api/reports | Có `SCOPE_reports.read» | Không cần | 200 |
| POST /api/notes | Có ROLE_EDITOR | Thiếu | 403, CSRF không bị tắt |
| POST /api/notes | Có ROLE_EDITOR | Sai | 403 |
| POST /api/notes | Có ROLE_EDITOR | Đúng | 200 |
| POST /api/notes | Chỉ có reports scope | Đúng | 403, CSRF đúng chưa đủ quyền |
| GET /login | Có Basic user | Không cần | Không được cung cấp generated login page |
| GET /unknown | Có Basic user | Không cần | Không tự động thành route public |
| GET /public | Anonymous | Không cần | `nosniff», `X-Frame-Options» vẫn hiện diện |

**Phân biệt authentication và authorization:** test `@WithMockUser» có thể hữu ích khi chỉ kiểm tra role, nhưng **không xác minh password, JWT decoder hoặc HTTP Basic provider**. Khi mục tiêu chứng minh cơ chế xác thực thay thế thật sự hoạt động, phải gửi credential qua filter bằng HTTP test. Trong demo này dùng `httpBasic(...)» để làm việc đó.

## 5. Maven demo chạy được trên Java 17

Ví dụ chỉ bỏ **form login** của Spring Security. Không tắt CSRF, CORS, headers hay authorization. Browser POST vẫn cần CSRF token. HTTP Basic dùng password đã băm BCrypt trong user store giả lập.

```text
documented-security-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/documentedsecurity/
    │   └── DocumentedSecurityApplication.java
    └── test/java/com/example/documentedsecurity/
        └── DocumentedSecurityApplicationTest.java
```

### 5.1 pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>documented-security-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
```

### 5.2 Java configuration và API

Tạo `src/main/java/com/example/documentedsecurity/DocumentedSecurityApplication.java»:

```java
package com.example.documentedsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
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
public class DocumentedSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentedSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-password"))
            .authorities("ROLE_EDITOR")
            .build();
        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode("analyst-demo-password"))
            .authorities("SCOPE_reports.read")
            .build();
        return new InMemoryUserDetailsManager(editor, analyst);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll())
            // SEC-EXC-API-001: no generated HTML form login.
            .formLogin(AbstractHttpConfigurer::disable)
            // Compensating authentication path for this learning demo.
            .httpBasic(Customizer.withDefaults())
            // Keep CSRF, security response headers and other defaults.
            .csrf(Customizer.withDefaults())
            .build();
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/api/me")
        String me(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/api/reports")
        String reports() {
            return "report allowed";
        }

        @PostMapping("/api/notes")
        String addNote() {
            return "note saved";
        }
    }
}
```

**Điểm quan trọng:**

- `.formLogin(AbstractHttpConfigurer::disable)» không xóa toàn bộ authentication. `httpBasic» vẫn tiếp nhận credential, `UserDetailsService» và `PasswordEncoder» vẫn phải xác minh username/password.
- `httpBasic» ở đây là cơ chế để học và test. Production sử dụng **HTTPS**, secret management và chống brute-force; có thể chọn OIDC/OAuth2 JWT hoặc mTLS phù hợp hơn. Tắt form login không tự biến Basic thành phương án tối ưu cho mọi hệ thống.
- `requestMatchers» có phạm vi method/path cụ thể và `anyRequest().denyAll()». Endpoint chưa được khai báo không tự mở quyền.
- `hasRole("EDITOR")» kiểm authority `ROLE_EDITOR» theo role prefix mặc định. `hasAuthority("SCOPE_reports.read")» kiểm chuỗi chính xác.
- CSRF vẫn bật; user có password đúng nhưng POST thiếu CSRF vẫn 403. Đừng tắt CSRF chỉ để dùng `curl -X POST» nhanh.
- Cấu hình response headers của Spring Security vẫn còn vì không dùng `headers().disable()».

## 6. Test hoàn chỉnh: kiểm soát bù đắp và baseline

Tạo `src/test/java/com/example/documentedsecurity/DocumentedSecurityApplicationTest.java»:

```java
package com.example.documentedsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentedSecurityApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void anonymousCannotReadProtectedApi() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejectedByRealBasicAuth() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("editor", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello editor"));
    }

    @Test
    void editorLacksReportScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystHasReportScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "analyst-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("report allowed"));
    }

    @Test
    void browserStylePostWithoutCsrfIsStillBlocked() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongCsrfTokenIsBlocked() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-password"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndRoleAllowPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-password"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note saved"));
    }

    @Test
    void correctCsrfCannotReplaceMissingRole() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("analyst", "analyst-demo-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginPageIsNotExposedAsApi() throws Exception {
        mvc.perform(get("/login")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRouteIsDenied() throws Exception {
        mvc.perform(get("/unknown")
                .with(httpBasic("editor", "editor-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securityHeadersRemainEnabled() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"));
    }
}
```

Đây là **13 ca** với cả positive và negative paths: public 200, anonymous 401, sai password 401, credential đúng 200, thiếu scope 403, đủ scope 200, CSRF thiếu/sai 403, CSRF đúng và đủ role 200, CSRF không thay quyền 403, route login không được cấp, route lạ bị từ chối, header mặc định vẫn có.

### Chạy và kết quả mong đợi

```bash
mvn test
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u editor:editor-demo-password http://localhost:8080/api/me
curl -i -u editor:editor-demo-password http://localhost:8080/api/reports
curl -i -u analyst:analyst-demo-password http://localhost:8080/api/reports
```

| Request | Status kỳ vọng | Body chính |
| --- | --- | --- |
| GET /public | 200 | `public ok» |
| GET /api/me anonymous | 401 | Basic challenge |
| GET /api/me editor | 200 | `hello editor» |
| GET /api/reports editor | 403 | Bị từ chối |
| GET /api/reports analyst | 200 | `report allowed» |

Các trạng thái là **kỳ vọng theo code**, không phải lời khẳng định test đã thực thi. `MockMvc» kiểm tra Servlet request trong JVM, không tự chứng minh TLS/ingress, security gateway, proxy headers hoặc browser behavior.

## 7. Với ngoại lệ CSRF: điều kiện để có kiểm thử bù đắp đúng nghĩa

Nếu một API thực sự chỉ phục vụ webhook đã ký và không dùng cookie/session, có thể cần ngoại lệ CSRF **hẹp**. Hồ sơ phải ghi rõ exact HTTP method/path, loại client và credential, bộ lọc xác thực thay thế, cách chống giả mạo, replay, giới hạn tải và cơ chế lỗi.

**Test bổ sung bắt buộc:**

- Browser POST ngoài ngoại lệ thiếu/sai CSRF vẫn 403, đúng CSRF và có user mới 2xx.
- Webhook thiếu credential/chữ ký bị từ chối, dù caller đưa `Origin» được phép.
- Chữ ký đúng cho body A không hợp lệ khi body bị sửa thành B.
- Timestamp không hợp lệ hoặc quá cũ bị từ chối; ID lặp phải được kiểm tra chống replay.
- Method ngoài ngoại lệ và path gần giống không được tự mở quyền.
- Khi secret manager hoặc replay store không khả dụng, xử lý fail closed/queue đúng hợp đồng.
- Kiểm soát bù đắp phải hoạt động qua gateway, nhiều replica và những lần restart, không chỉ trong một unit test.

**Cảnh báo:** HMAC chỉ tạo tính xác thực/toàn vẹn nếu bí mật được quản lý an toàn và producer/consumer thống nhất canonical bytes. Timestamp không tự ngăn replay trong cửa sổ hợp lệ; phải có event ID + atomic distributed idempotency khi yêu cầu. Đừng mở public route trước rồi chỉ đặt một kiểm tra “có header X” dễ giả mạo.

## 8. Khi tắt hoặc nới response headers, CORS và HSTS

### Framing và CSP

Nếu trang cần được nhúng iframe, tắt toàn bộ security headers sẽ mất cả `X-Content-Type-Options», cache directives và các bảo vệ khác. Nên điều chỉnh riêng framing policy hoặc cấu hình CSP `frame-ancestors» theo origin cho phép, đồng thời test tài nguyên nhạy cảm khác vẫn bị chặn iframe. MockMvc chứng minh server phát header đúng; **browser E2E** mới kiểm tra browser thực sự tuân thủ CSP và không làm vỡ UI.

### CORS

CORS là cơ chế để browser đánh giá quyền đọc response cross-origin. CORS không là authentication hoặc authorization, và không thay CSRF. Hồ sơ nới CORS cần scheme/host/port của origin, allowCredentials, allowedMethods/Headers, cấu hình proxy và lý do. Test preflight hợp lệ, origin sai, method sai, header sai và actual request vẫn chịu auth/CSRF. Không dùng wildcard cho credentialed browser response rồi coi đó là giải pháp sạch.

### HSTS và HTTPS

HSTS phải được xem xét ở ranh giới HTTPS thật. Nếu TLS terminate ở reverse proxy, Spring Boot có thể thấy HTTP nội bộ; giải pháp thường là cấu hình proxy/trusted forwarded headers đúng chỗ, không tắt HSTS cho nhanh. Kiểm thử TLS certificate, HTTPS redirect, HSTS header, subdomain coverage và việc client giả `X-Forwarded-Proto» không được tin.

### Session và token

Với API stateless chỉ dùng Bearer token, hồ sơ cần nêu rõ lý do bỏ form/session, mọi request phải mang token và kiểm tra chữ ký/issuer/audience/expiry/role. `@WithMockUser» **không** chứng minh JWT decoder hoặc PasswordEncoder hoạt động; dùng request token thật qua filter/provider trong test tích hợp.

## 9. Quy trình review/CI có thể lặp lại

```text
Security config change
    |
    v
Exception ID + threat model + scope + owner
    |
    v
Reviewer approves residual risk
    |
    v
Code narrow change + compensating controls
    |
    v
JUnit/MockMvc positive and negative tests
    |
    v
CI gate + integration/browser/proxy tests where relevant
    |
    v
Deploy, audit, monitor
    |
    v
Review on expiry/change; rollback if assumptions break
```

Nên gắn code review đặc biệt với diff có `disable()», `permitAll()», `ignoringRequestMatchers», `web.ignoring()», CORS wildcard, encoder `{noop}», JWT validator bị bỏ hoặc annotation method-security bị xóa. Không tự kết luận mọi biểu thức đều sai; **đối chiếu với hồ sơ ngoại lệ và bằng chứng**.

CI cần kiểm tra test âm không bị `@Disabled»/skip, security filter chain đang bật, test chạy đúng version và không dùng mock identity để che lỗi xác thực thật. Lưu kết quả test gắn với commit, config profile và môi trường. Sau deploy, định kỳ so sánh effective configuration với hồ sơ ngoại lệ: code review chỉ chứng minh cấu hình ở repository, không bảo đảm gateway/proxy không ghi đè.

## 10. Vòng đời ngoại lệ: quan sát và hoàn nguyên

Một ngoại lệ nên được xem xét lại ngay khi:

- Có client browser/cookie mới, hoặc một machine endpoint bắt đầu nhận session.
- Matcher, method, URL, tenant hoặc `SecurityFilterChain» bị thay đổi.
- Auth provider/token format/JWT issuer/audience hoặc key rotation đổi.
- Proxy/TLS/CORS policy hoặc load balancer có thay đổi.
- Dữ liệu trở nên nhạy cảm hơn, role thay đổi, thêm quyền quản trị.
- Thay đổi số lượng replica làm giả định cache/replay store không còn đúng.
- Các bài test bảo vệ bị skip, fail, hoặc monitoring cho thấy denial bất thường.
- Đến hạn review mà owner không cung cấp được evidence.

Trường hợp không còn đáp ứng điều kiện, phải rollback: khôi phục cơ chế bảo vệ, thu hồi quyền/key không còn cần, di chuyển client theo kế hoạch, thông báo bộ phận vận hành. Không giữ ngoại lệ “tạm thời” vô thời hạn chỉ vì test cũ từng pass.

### Audit và bảo vệ dữ liệu

Event và log hữu ích khi cần điều tra ngoại lệ, nhưng không ghi password, Authorization header, session cookie, CSRF token, raw JWT, API secret hoặc toàn bộ principal/request. Dùng request ID, event type, outcome, reason code và metadata tối thiểu; bảo vệ quyền xem log, retention và khả năng phát hiện mất event. Logging DEBUG/TRACE không thay thế audit trail bền vững.

## 11. Lỗi phổ biến cần tránh

1. **“REST API nên tắt CSRF”.** Không đủ nếu có browser credentials. Kiểm tra cookie, session, Basic, Bearer, và route thật.
2. **“Nội bộ nên bỏ auth”.** Mạng nội bộ không chặn compromised service, SSRF hoặc lateral movement.
3. **Chỉ comment trong code.** Không có owner, review, test và rollback thì ngoại lệ không thể kiểm soát.
4. **Dùng `permitAll» rộng.** Route quản trị/public bị lẫn; dùng exact matcher và deny-all fallback.
5. **Dùng `web.ignoring» khi chỉ muốn public.** Có thể bỏ security headers và filter; nên cân nhắc `permitAll».
6. **Tắt toàn bộ headers vì iframe.** Chỉ nới framing; test các headers còn lại.
7. **Coi CORS là chống CSRF.** Hai cơ chế giải quyết rủi ro khác nhau.
8. **Chỉ test thành công.** Cần test sai credential/role/token, outside scope và lỗi dependency.
9. **Test bằng `@WithMockUser» rồi tin đã xác thực password/JWT.** Annotation đặt security context giả, không đi qua provider.
10. **Bỏ qua failure mode của kiểm soát bù đắp.** Nếu IdP/key store down mà cho qua request là fail-open.
11. **Không xem proxy/gateway.** Cấu hình thực có thể khác source Spring Boot; cần deployment test.
12. **“Có test” nhưng bị skip.** Evidence phải là test run thật trên commit/version tương ứng.
13. **Bỏ qua expiry/review.** Mô hình client và credential thay đổi, cần trigger review rõ.
14. **Audit có cả token/secrets.** Ghi thông tin đủ điều tra, không tự tạo kho dữ liệu nhạy cảm.
15. **Rollback không khả thi.** Phải có cách đưa client sang giao thức an toàn và ngắt ngoại lệ khi rủi ro tăng.

## 12. Checklist trước khi merge hoặc deploy

| Câu hỏi | Khi nào đạt? |
| --- | --- |
| Baseline và deviation rõ? | Biết setting nào đổi, trên chain/route/method nào |
| Đã mô tả threat model? | Biết client, credentials, dữ liệu, ranh giới tin cậy |
| Phạm vi nhỏ nhất? | Không nới ngoài yêu cầu nghiệp vụ |
| Có kiểm soát bù đắp server-side? | Không chỉ tin UI hoặc browser tự giác |
| Positive tests PASS? | Request hợp lệ đạt kết quả nghiệp vụ |
| Negative tests PASS? | Sai token/role/CSRF/route bị từ chối |
| Baseline khác còn được bảo vệ? | CSRF/headers/authorization không mất ngoài ngoại lệ |
| Test xác thực thật phù hợp? | HTTP Basic/JWT/mTLS qua đúng filter/provider |
| Có evidence theo commit/deploy? | Gắn CI run, version và environment |
| Có owner, approver, hạn review? | Người chịu trách nhiệm chấp nhận rủi ro |
| Có audit/monitor? | Phát hiện hành vi vượt phạm vi và các control failure |
| Có rollback? | Có thể khôi phục baseline khi yêu cầu thay đổi |
| Không tiết lộ secrets? | Credential/log/test artifacts được bảo vệ |

## 13. Kết luận

- Tắt hoặc nới một cơ chế Spring Security là quyết định kỹ thuật có rủi ro, **không phải cách sửa 401/403**.
- Hồ sơ ngoại lệ tốt nối được **baseline → thay đổi → lý do → ranh giới → kiểm soát bù đắp → test → owner/approval → review/rollback**.
- Ưu tiên **thay đổi phạm vi hẹp**, giữ các lớp bảo vệ độc lập hoạt động; tắt form login không được tắt auth/CSRF/headers.
- Test âm chứng minh người không đủ quyền, sai credential hoặc request ngoài phạm vi vẫn bị chặn.
- Các test trong JVM không thay thế kiểm tra browser, TLS, proxy và các phụ thuộc production.
- Khi giả định thay đổi hoặc ngoại lệ hết giá trị, phải xem xét và **hoàn nguyên** thay vì để cấu hình yếu tồn tại vĩnh viễn.

## Tài liệu tham khảo

- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — HTTP Security Response Headers: https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — ASVS: https://owasp.org/www-project-application-security-verification-standard/