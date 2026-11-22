# Kiểm thử hồi quy theo ma trận quyền khi thêm endpoint hoặc hành động mới

> Bài Knowledge dành cho Spring Security (Servlet/MVC), Java 17+, Spring Boot 3.x và JUnit 5. Mục tiêu: khi thêm một API hoặc hành động, chứng minh **quyền mới đúng đặc tả** và **quyền của mọi hành động trước đó vẫn giữ nguyên**. Một test chỉ kiểm tra “ADMIN gọi thành công” là chưa đủ.

## 1. Ma trận quyền là gì và vì sao giúp tránh hồi quy?

Ma trận quyền (permission matrix) mô tả quyết định mong đợi cho mỗi tổ hợp **principal × role/authority × HTTP method + endpoint/action × tài nguyên × ngữ cảnh**. Nó là đặc tả đã thống nhất với chủ sở hữu nghiệp vụ/chính sách, cần được viết **độc lập** với hàm đang thực thi quyền.

Các lỗi có thể xuất hiện khi thêm endpoint `POST /archive`:

- **Privilege escalation:** role `APPROVER` vô tình được quyền archive do rule URL quá rộng hoặc chính sách role bị nới.
- **BOLA/IDOR:** `EDITOR` chỉ được archive tài liệu của mình, nhưng có thể sửa ID đường dẫn để archive tài liệu của người khác.
- **Hồi quy chức năng cũ:** sửa `SecurityFilterChain` khiến API `GET /documents/{id}` hoặc `POST /approve` bị khóa sai hay mở quyền không chủ ý.
- **Rò rỉ/tác dụng phụ:** request bị trả 403 nhưng lệnh ghi database hoặc phát event đã xảy ra trước khi bị chặn.

Ví dụ ta có hai tài liệu `doc-a` thuộc `alice`, `doc-b` thuộc `bob`. Ba hành động:

| Hành động | Endpoint | Thời điểm |
| --- | --- | --- |
| Read | `GET /api/documents/{id}` | Đã tồn tại |
| Approve | `POST /api/documents/{id}/approve` | Đã tồn tại |
| Archive | `POST /api/documents/{id}/archive` | **Mới thêm** |

Chính sách **giả định của ví dụ** (các request của bảng dưới có username `alice`; “own” = `doc-a`, “other” = `doc-b`):

| Role | Read own | Read other | Approve own | Approve other | Archive own | Archive other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `VIEWER` | 200 | 403 | 403 | 403 | 403 | 403 |
| `EDITOR` | 200 | 403 | 403 | 403 | 200 | 403 |
| `APPROVER` | 200 | 200 | 200 | 200 | 403 | 403 |
| `ADMIN` | 200 | 200 | 200 | 200 | 200 | 200 |

Các cột “archive” là yêu cầu mới; **bốn cột read/approve cũ phải tiếp tục được test** sau khi thêm action. Đừng suy ra rằng `APPROVER` được archive chỉ vì có quyền approve. Bảng này mô tả hợp đồng nghiệp vụ mẫu, không phải các role mặc định của Spring Security.

Thêm các trường hợp biên có expected riêng:

| Điều kiện | Kỳ vọng ví dụ |
| --- | --- |
| Anonymous GET read | 401 (HTTP Basic yêu cầu xác thực) |
| Anonymous POST archive có CSRF hợp lệ | 401 |
| Có đăng nhập nhưng role/owner không phù hợp | 403 |
| ADMIN đọc ID không tồn tại | 404 |
| ADMIN gọi DELETE chưa được hỗ trợ | 403 do default-deny |
| ADMIN POST archive thiếu CSRF token | 403 (ứng dụng mẫu giữ CSRF mặc định) |
| `bob` / EDITOR archive tài liệu `doc-b` | 200 |

**401, 403, 404 là các contract khác nhau:** 401 thường chỉ thiếu xác thực; 403 là không được cấp quyền; 404 là tài nguyên không tìm thấy. Một số hệ thống chủ ý trả 404 thay cho 403 để giảm khả năng dò ID tài nguyên. Hãy chốt chính sách của hệ thống thật trước khi ghi expected. Không coi trạng thái của ví dụ là quy tắc bắt buộc cho mọi API/JWT.

## 2. Cần kiểm tra ranh giới nào?

Luồng bảo vệ cho một request Servlet Spring:

```text
Client: method + path + identity + (CSRF nếu cần)
          |
          v
SecurityFilterChain
  - path/method không được khai báo -> deny
  - thiếu authentication -> 401 trong ví dụ HTTP Basic
          |
          v
Controller -> Spring bean/proxy -> @PreAuthorize
                                  - role/owner sai -> 403
                                  - đủ quyền -> gọi method
                                           |
                                           v
                                      Service/Repository
                                        - ID không tồn tại -> 404
                                        - thành công -> data/side effects
```

Cần tách ba lớp: **request authorization** (`authorizeHttpRequests`), **method/resource authorization** (`@PreAuthorize`, `@EnableMethodSecurity`) và **business effect** (thay đổi DB, event, audit). Route match `.authenticated()` không đồng nghĩa cho phép mọi role ở service. Ngược lại, test trực tiếp `new DocumentService()` bỏ qua proxy có thể khiến annotation không được áp dụng.

Ma trận phải kiểm tra cả allow và deny. Một negative test POST thiếu CSRF có thể trả 403 dù role-check hoàn toàn sai: khi đang kiểm tra phân quyền role, hãy cung cấp CSRF hợp lệ, rồi viết test CSRF riêng.

## 3. Ví dụ runnable: 24 ca ma trận + 6 ca biên

Ví dụ sử dụng **Spring Boot 3.x**, Java 17, Spring MVC, JUnit Jupiter và `spring-security-test`; tránh truy cập DB để tách riêng trọng tâm authorization. Đường dẫn/role được mô phỏng, còn filter chain và Spring method security chạy trong test context thực sự.

Phụ thuộc Gradle nếu dự án chưa có starter tương ứng; dùng BOM/plugin Spring Boot sẵn có để quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo tệp `src/test/java/com/example/security/AuthorizationMatrixTest.java` với nội dung đầy đủ:

```java
package com.example.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthorizationMatrixTest.DemoApp.class)
@AutoConfigureMockMvc
class AuthorizationMatrixTest {

    @Autowired MockMvc mvc;

    // Mỗi Case mang expected đã xác định từ đặc tả, không tính từ Policy.
    record Case(String name, String verb, String path, String username,
                String role, int expectedStatus, String expectedBody) {}
    record PermissionRow(String role, int[] statuses) {}

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("accessMatrix")
    void allOldAndNewActionsRespectPermissionMatrix(Case c)
            throws Exception {

        MockHttpServletRequestBuilder request = switch (c.verb()) {
            case "GET" -> get(c.path());
            case "POST" -> post(c.path()).with(csrf());
            default -> throw new IllegalArgumentException(c.verb());
        };

        var result = mvc.perform(
                request.with(user(c.username()).roles(c.role())))
            .andExpect(status().is(c.expectedStatus()));

        // Ca thành công phải trả đúng nội dung tài nguyên/hành động.
        if (c.expectedBody() != null) {
            result.andExpect(content().string(c.expectedBody()));
        }
    }

    static Stream<Case> accessMatrix() {
        // Thứ tự: read-own, read-other, approve-own, approve-other,
        // archive-own, archive-other. Đây là SPEC đã được review.
        List<PermissionRow> spec = List.of(
            new PermissionRow("VIEWER",
                new int[] {200, 403, 403, 403, 403, 403}),
            new PermissionRow("EDITOR",
                new int[] {200, 403, 403, 403, 200, 403}),
            new PermissionRow("APPROVER",
                new int[] {200, 200, 200, 200, 403, 403}),
            new PermissionRow("ADMIN",
                new int[] {200, 200, 200, 200, 200, 200})
        );

        List<Case> cases = new ArrayList<>();
        for (PermissionRow row : spec) {
            for (int i = 0; i < 6; i++) {
                String id = i % 2 == 0 ? "doc-a" : "doc-b";
                String verb = i < 2 ? "GET" : "POST";
                String suffix = i < 2 ? ""
                    : i < 4 ? "/approve" : "/archive";
                String path = "/api/documents/" + id + suffix;
                int expected = row.statuses()[i];

                String expectedBody = expected == 200
                    ? (i < 2 ? "doc:"
                        : i < 4 ? "approved:" : "archived:") + id
                    : null;

                cases.add(new Case(
                    row.role() + "/" + suffix + "/" + id,
                    verb, path, "alice", row.role(),
                    expected, expectedBody));
            }
        }
        return cases.stream(); // 4 roles × 2 owner relations × 3 actions
    }

    @Test
    void bobEditorCanArchiveHisOwnDocument() throws Exception {
        mvc.perform(post("/api/documents/doc-b/archive")
                .with(user("bob").roles("EDITOR")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("archived:doc-b"));
    }

    @Test
    void anonymousReadIsUnauthorized() throws Exception {
        mvc.perform(get("/api/documents/doc-a"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousArchiveIsUnauthorized() throws Exception {
        mvc.perform(post("/api/documents/doc-a/archive").with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanReachNotFoundForUnknownDocument() throws Exception {
        mvc.perform(get("/api/documents/missing")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isNotFound());
    }

    @Test
    void undeclaredDeleteIsDeniedEvenToAdmin() throws Exception {
        mvc.perform(delete("/api/documents/doc-a")
                .with(user("root").roles("ADMIN")).with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeWithoutCsrfIsForbiddenEvenToAdmin() throws Exception {
        mvc.perform(post("/api/documents/doc-a/archive")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({
        SecuritySetup.class, DocumentPolicy.class,
        DocumentService.class, DocumentController.class
    })
    static class DemoApp {}

    @Configuration(proxyBeanMethods = false)
    static class SecuritySetup {
        @Bean
        SecurityFilterChain chain(HttpSecurity http) throws Exception {
            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET,
                        "/api/documents/{id}").authenticated()
                    .requestMatchers(HttpMethod.POST,
                        "/api/documents/{id}/approve",
                        "/api/documents/{id}/archive").authenticated()
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
            // Dùng session/HTTP Basic; không disable CSRF.
        }
    }

    @Component("documentPolicy")
    public static class DocumentPolicy {
        static final Map<String, String> OWNERS =
            Map.of("doc-a", "alice", "doc-b", "bob");

        private boolean hasRole(Authentication a, String role) {
            return a.getAuthorities().stream().anyMatch(
                x -> x.getAuthority().equals("ROLE_" + role));
        }

        public boolean canRead(Authentication a, String id) {
            return hasRole(a, "ADMIN") || hasRole(a, "APPROVER")
                || ((hasRole(a, "VIEWER") || hasRole(a, "EDITOR"))
                    && Objects.equals(OWNERS.get(id), a.getName()));
        }

        public boolean canApprove(Authentication a) {
            return hasRole(a, "APPROVER") || hasRole(a, "ADMIN");
        }

        public boolean canArchive(Authentication a, String id) {
            return hasRole(a, "ADMIN")
                || (hasRole(a, "EDITOR")
                    && Objects.equals(OWNERS.get(id), a.getName()));
        }
    }

    @Service
    public static class DocumentService {

        @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
        public String read(String id) {
            checkExists(id);
            return "doc:" + id;
        }

        @PreAuthorize("@documentPolicy.canApprove(authentication)")
        public String approve(String id) {
            checkExists(id);
            return "approved:" + id;
        }

        @PreAuthorize("@documentPolicy.canArchive(authentication, #p0)")
        public String archive(String id) {
            checkExists(id);
            return "archived:" + id;
        }

        private void checkExists(String id) {
            if (!DocumentPolicy.OWNERS.containsKey(id)) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
        }
    }

    @RestController
    @RequestMapping("/api/documents")
    public static class DocumentController {
        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/{id}")
        public String read(@PathVariable String id) {
            return service.read(id);
        }

        @PostMapping("/{id}/approve")
        public String approve(@PathVariable String id) {
            return service.approve(id);
        }

        @PostMapping("/{id}/archive")
        public String archive(@PathVariable String id) {
            return service.archive(id);
        }
    }
}
```

Chạy từ root dự án có Gradle Wrapper:

```bash
./gradlew test --tests "com.example.security.AuthorizationMatrixTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.security.AuthorizationMatrixTest"
```

**Kỳ vọng theo mã:** 24 lần chạy của parameterized test và 6 ca biên = **30 ca thành công**, miễn project dùng đúng dependency, Java/Spring Boot tương thích và không có security config khác can thiệp. Đây là expected assertions; không phải log test đã chạy. Bài dùng API Spring Boot 3.x: trên Spring Boot 4.x cần điều chỉnh import/auto-configuration `@AutoConfigureMockMvc` theo phiên bản thật.

Điểm thiết kế quan trọng:

1. `@SpringBootTest` + `@AutoConfigureMockMvc` thực thi MVC và Security filter trong ApplicationContext test. `@EnableMethodSecurity` kích hoạt `@PreAuthorize` trên **Spring bean** `DocumentService`.
2. `@Import` đăng ký rõ service/controller/policy. Một lời gọi tạo thủ công bằng `new DocumentService()` sẽ không kiểm tra interceptor tương tự.
3. `@PreAuthorize("@documentPolicy...")` gọi policy bean; `#p0` là đối số thứ nhất theo vị trí, tránh phụ thuộc cờ biên dịch `-parameters`.
4. User fixture `user("alice").roles("EDITOR")` sinh authority `ROLE_EDITOR`; quyền owner còn phụ thuộc `authentication.name`, nên role giống nhau chưa đủ.
5. POST test chính sách dùng `.with(csrf())` hợp lệ. Ca kiểm tra CSRF cố ý bỏ token và phải nhận 403. Trong ứng dụng OAuth2 Bearer thuần stateless, policy CSRF có thể khác.
6. `requestMatchers` xét **HTTP method + endpoint**; `.anyRequest().denyAll()` chặn các route chưa được khai báo. `@PreAuthorize` mới quyết định business role/owner tại service.
7. `accessMatrix()` lưu **giá trị mong đợi độc lập** dưới dạng bảng `200/403`. Nếu ai đó nới `DocumentPolicy.canArchive()` cho `APPROVER`, các test âm tính archive sẽ đỏ.

## 4. Quy trình thêm endpoint/action mới và giữ hồi quy

**Trước khi code:**

1. Xác định verb, path, tên action, tài nguyên, role/authority, ownership/tenant, trạng thái tài nguyên và tác dụng phụ. Ghi rõ người được phép và người bị cấm.
2. Lấy ma trận version-controlled đang dùng làm cơ sở; thêm các cột/hàng cho action mới. **Giữ nguyên expected của action cũ** trừ khi nghiệp vụ phê duyệt thay đổi quyền.
3. Viết ca positive, negative, anonymous, foreign owner, resource missing và HTTP method chưa được hỗ trợ theo từng rủi ro. Một cột quyền mới không có test từ chối là lỗ hổng coverage.
4. Đưa các ca vào `@MethodSource` hoặc fixture dữ liệu tương đương. Không tính expected bằng chính policy đang được kiểm thử.

**Khi triển khai:**

5. Thêm đúng request matcher và `@PreAuthorize`/policy ở ranh giới thích hợp. Với resource ownership, cần kiểm tra ID thực tế của request **trong lớp service hoặc policy**, không chỉ role tĩnh tại URL.
6. Kiểm tra việc đổi matcher không tạo wildcard cho phép quá rộng hoặc đảo thứ tự luật. Với nhiều `SecurityFilterChain`, chắc chắn route thuộc chain dự kiến.
7. Khi permission kiểm soát side effect, xác nhận check diễn ra **trước** thao tác ghi hay gửi event. Nếu cập nhật transactional, kiểm tra rollback theo chính sách.

**Trước merge:**

8. Chạy toàn bộ suite hồi quy quyền cũ và mới; kiểm tra báo cáo JUnit, không chỉ số lượng “green”. Nếu một expected thay đổi, cần có yêu cầu nghiệp vụ được review.
9. Thêm integration test với repository/event thật cho action thay đổi dữ liệu. Chạy trong môi trường có fixture cách ly; database phải trở về trạng thái ban đầu giữa các test.
10. Đưa suite vào CI để fail PR khi bất kỳ ca role/resource/action trọng yếu nào bị sai.

Với action archive thay đổi trạng thái DB, bổ sung assertion vượt ngoài demo response-only:

| Ca | HTTP | DB `status` sau request | Event archive |
| --- | --- | --- | --- |
| EDITOR archive tài liệu mình | 200 | `ARCHIVED` | Đúng một event |
| EDITOR archive tài liệu người khác | 403 | Vẫn `ACTIVE` | Không có |
| VIEWER archive tài liệu mình | 403 | Vẫn `ACTIVE` | Không có |
| ADMIN archive tài liệu tồn tại | 200 | `ARCHIVED` | Đúng một event |
| ADMIN archive ID không tồn tại | 404 | Không tạo/thay đổi bản ghi | Không có |

Khi tài liệu đã `ARCHIVED`, phải thêm ca idempotency, xung đột trạng thái (`409`) hoặc quy định xử lý lặp tùy contract. Đừng giả định quyền chỉ phụ thuộc role: tenant, ownership transfer, trạng thái và thời điểm có thể làm thay đổi quyết định.

## 5. Đánh giá coverage của ma trận

Ma trận ví dụ bao phủ **4 role × 3 action × 2 quan hệ owner = 24** tổ hợp, rồi thêm 6 ca biên. Trong dự án thật, cân nhắc các chiều sau để xác định regression suite:

| Chiều | Dữ liệu test | Rủi ro phát hiện |
| --- | --- | --- |
| Principal/identity | Alice, Bob; tên/ID khác nhau | Hardcode username hoặc check sai owner |
| Authority | Role và permission cụ thể, đa role | Mapping role/authority sai, privilege escalation |
| Authentication | Anonymous, valid session, expired/invalid token | Chế độ xác thực hoặc 401/403 không đúng |
| Resource | Own, foreign, cross-tenant, missing, state khác | IDOR/BOLA, rò thông tin tenant |
| Hành động | Read, approve, archive; action mới/cũ | Quyền cũ hỏng khi thêm action mới |
| HTTP | Verb, path, route không khai báo, CSRF | Bypass filter hoặc sai matcher |
| Kết quả | Status, payload, ID, DB/event/audit | Trả nhầm tài liệu hoặc đã có side effect khi 403 |

Khi số chiều quá lớn, có thể nhóm theo equivalence classes và dùng pairwise cho các tổ hợp rủi ro thấp, nhưng cần phủ đầy đủ các đường có thể ghi dữ liệu, vượt tenant, đọc record nhạy cảm và điều chỉnh quyền. Một điểm coverage hữu ích là **bao nhiêu ô ma trận có assertion độc lập**, không chỉ số test.

Để kiểm tra sức phát hiện lỗi, trong nhánh thử nghiệm có thể cố tình nới `canArchive()` cho `APPROVER` hoặc tạm bỏ `@PreAuthorize` rồi chạy suite. Những ca âm tính tương ứng phải thất bại; sau đó hoàn tác thay đổi thử nghiệm. Không thử lỗi bảo mật kiểu này trên production.

## 6. OAuth2/JWT, CSRF và sự khác biệt của test identity

`user(...).roles(...)` của Spring Security Test đưa authentication giả lập vào request: nó phù hợp để kiểm tra **authorization với role đã có** nhưng **không xác minh** JWT signature, issuer, audience, converter claims thành authorities hoặc quyền theo tenant được cấp từ IdP.

Trong Resource Server, có thể viết test riêng cho JWT/claims bằng `jwt()`:

```java
// Snippet trong một test đã có MockMvc và Resource Server config.
// Cần static import jwt từ SecurityMockMvcRequestPostProcessors
// và import org.springframework.security.core.authority.SimpleGrantedAuthority.
mvc.perform(get("/api/documents/doc-a")
        .with(jwt().jwt(token -> token.subject("alice"))
                   .authorities(
                       new SimpleGrantedAuthority("ROLE_VIEWER"))))
    .andExpect(status().isOk());
```

`jwt().authorities(...)` **gán thẳng authority**, nên không tự kiểm thử claim-to-authority converter. Hãy thêm unit test cho converter hoặc integration test xác thực token qua cấu hình thật khi chính phần mapping là rủi ro. Với cookie/session, CSRF thường là boundary cần test; với Bearer stateless, contract CSRF phụ thuộc cấu hình và threat model. Không copy kỳ vọng 403 do thiếu CSRF từ ví dụ sang một API đã chủ đích cấu hình khác.

## 7. Các lỗi phổ biến và cách tránh

- **Chỉ test ADMIN:** thêm test role thấp hơn cho cả `own` và `other`, nhất là action mới.
- **Chỉ assert 200 hoặc `size()`:** kiểm tra ID, nội dung tài nguyên, response status chính xác và dữ liệu side effect.
- **Expected lấy từ policy đang test:** dùng ma trận được review độc lập với code.
- **Test trực tiếp đối tượng tạo bởi `new`:** `@PreAuthorize` qua Spring AOP proxy không được kích hoạt như khi lấy bean từ context.
- **MockMvc tắt filter:** không chứng minh `SecurityFilterChain`; cần cấu hình và test filter thực sự.
- **Ca deny POST thiếu CSRF:** bị 403 sớm vì CSRF, làm test quyền xanh giả; thêm token hợp lệ cho role tests.
- **Nhầm role và authority:** `roles("ADMIN")` tạo `ROLE_ADMIN`, `authorities("document:archive")` giữ nguyên chuỗi permission.
- **Bỏ cột/hàng quyền cũ:** matcher mới có thể làm hồi quy trên endpoint đã tồn tại.
- **Không kiểm tra thao tác ghi khi bị deny:** 403 không chứng minh DB/event chưa thay đổi.
- **Cho phép route mới theo wildcard rộng:** nếu `anyRequest().authenticated()` hoặc `permitAll()` vô tình bao cả path nhạy cảm, user đã đăng nhập có thể qua HTTP layer; cần policy service và fallback deny.
- **Quên phân biệt 403 và 404:** có thể lộ sự tồn tại tài nguyên hoặc kiểm thử không khớp contract.
- **Quên path/verb tương đương:** REST route version khác, query parameter, nested resource và nhiều filter chain có thể đi qua nhánh khác.

## 8. Checklist nghiệm thu

1. Có bảng policy trước thay đổi, được review và lưu cùng code hoặc tài liệu đặc tả.
2. Action mới được thêm cho đủ role và quan hệ tài nguyên; mọi action cũ vẫn chạy regression.
3. Mỗi ca xác định `username`, role/authority, method, URL, resource và expected status/payload.
4. Có ca từ chối anonymous, role thấp, foreign owner, route/method không cho phép, CSRF/token theo thực tế.
5. Tầng HTTP/security interceptor hoạt động trong test; `@EnableMethodSecurity` bật khi test `@PreAuthorize`.
6. Với action ghi dữ liệu, kiểm tra DB, event, audit không thay đổi khi bị deny.
7. CI chặn merge nếu một ca quyền sai. Khi sửa expected, phải có yêu cầu thay đổi quyền được phê duyệt.

## Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security — CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [JUnit 5 — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)
