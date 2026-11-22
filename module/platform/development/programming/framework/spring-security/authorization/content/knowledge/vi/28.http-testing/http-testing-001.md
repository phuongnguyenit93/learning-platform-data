# Chuyển ma trận quyền thành bộ ca cho phép và từ chối trong kiểm thử HTTP

Một ứng dụng Spring Security có thể có nhiều loại người dùng và nhiều endpoint: người xem được đọc, người biên tập được tạo, quản trị viên được xóa. Nếu chỉ kiểm thử một request thành công cho mỗi API, ta dễ bỏ sót tình huống **người không có quyền vẫn truy cập được**. Ngược lại, chỉ kiểm thử `403 Forbidden` cũng không chứng minh rằng người có quyền thật sự dùng được tính năng.

Cách làm có hệ thống là chuyển **ma trận quyền (authorization matrix)** thành bộ ca HTTP có kỳ vọng độc lập: request nào **được cho phép**, request nào **bị từ chối**, nhận **status nào**, và có phát sinh **thay đổi dữ liệu hay không**.

Bài học tập trung vào **Spring Security authorization ở tầng Servlet/MVC**, dùng Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5 và MockMvc. Các ví dụ tạo ứng dụng nhỏ có thể chạy và kiểm thử tích hợp; sau đó trình bày cách mở rộng cho quyền theo tài nguyên, tenant và endpoint thực tế.

## 1. Hiểu ma trận quyền trước khi viết test

Một hàng trong ma trận quyền không chỉ là “role A gọi endpoint B”. Kỳ vọng chịu ảnh hưởng bởi các chiều sau:

| Chiều của test | Câu hỏi cần chốt |
| --- | --- |
| Actor | Request anonymous, `READER`, `EDITOR`, `ADMIN`, service account hay token hết hạn? |
| HTTP method | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` có quy tắc riêng không? |
| Path/resource | `/api/docs/{id}` trỏ đến bản ghi nào; owner/tenant là ai? |
| Authentication | Credential hợp lệ, không có credential, sai hoặc hết hạn? |
| Authority và role | Dùng `DOC_READ`, `DOC_WRITE`, `DOC_ADMIN` hay `ROLE_ADMIN`? |
| Context | Resource đang ở trạng thái nào; chủ thể có sở hữu không; cùng tenant không? |
| Expected decision | Cho phép hay từ chối theo **yêu cầu nghiệp vụ**? |
| HTTP status/contract | Khi được phép: 200/201/204; khi từ chối: 401/403 hoặc chính sách 404 che giấu sự tồn tại? |
| Side effects | Request bị từ chối có tạo, sửa, xóa dữ liệu hoặc phát event không? |

**Ma trận phải xuất phát từ yêu cầu quyền được phê duyệt**, không được lấy nguyên logic `SecurityFilterChain` hiện tại rồi coi kết quả đó là chân lý. Nếu test tự suy ra expected từ chính rule đang kiểm tra, đổi rule sai có thể làm cả logic và test sai cùng lúc mà vẫn xanh.

Trong Spring Security:

- `hasAuthority("DOC_WRITE")` kiểm tra đúng authority tên `DOC_WRITE`.
- `hasRole("ADMIN")` thông thường kiểm tra authority `ROLE_ADMIN`, không phải authority `ADMIN`.
- `ROLE_ADMIN` **không tự động bao hàm** `DOC_READ` hoặc `DOC_WRITE` nếu ứng dụng chưa cấp các authority đó hay thiết lập cơ chế kế thừa rõ ràng.
- Request chưa xác thực vào tài nguyên yêu cầu đăng nhập thường được **401** ở REST API HTTP Basic/Bearer (hoặc redirect khi dùng form login); request đã xác thực nhưng thiếu quyền thường **403**.
- `AccessDeniedException` không luôn đồng nghĩa HTTP 403: Spring Security còn xét trạng thái anonymous/đã xác thực khi chuyển thành response.
- CSRF có thể chặn `POST`/`PUT`/`PATCH`/`DELETE` bằng 403 **trước khi** đi đến nhánh kiểm tra quyền; test authorization cần cung cấp CSRF hợp lệ nếu cấu hình bật CSRF.

## 2. Ví dụ chính sách quyền: tài liệu và trang audit

Giả sử API có ba tài khoản thử nghiệm:

| Actor | Authorities được cấp |
| --- | --- |
| Anonymous | Không có Authentication đã đăng nhập |
| `reader` | `ROLE_READER`, `DOC_READ` |
| `editor` | `ROLE_EDITOR`, `DOC_READ`, `DOC_WRITE` |
| `admin` | `ROLE_ADMIN`, `DOC_READ`, `DOC_WRITE`, `DOC_ADMIN` |

Danh sách endpoint và kỳ vọng:

- `GET /api/public`: public, không cần đăng nhập, trả 200.
- `GET /api/docs/42`: cần `DOC_READ`, trả 200 nếu được phép.
- `POST /api/docs`: cần `DOC_WRITE`, trả 201 nếu tạo được tài liệu.
- `DELETE /api/docs/42`: cần `DOC_ADMIN`, trả 204 nếu xóa thành công.
- `GET /api/admin/audit`: cần `ROLE_ADMIN`, trả 200 nếu được phép.

Từ năm endpoint × bốn actor, tạo bảng 20 ô kiểm thử:

| Request | Anonymous | `reader` | `editor` | `admin` |
| --- | ---: | ---: | ---: | ---: |
| `GET /api/public` | **200** | **200** | **200** | **200** |
| `GET /api/docs/42` | **401** | **200** | **200** | **200** |
| `POST /api/docs` | **401** | **403** | **201** | **201** |
| `DELETE /api/docs/42` | **401** | **403** | **403** | **204** |
| `GET /api/admin/audit` | **401** | **403** | **403** | **200** |

Đây là **đặc tả của ví dụ**, không phải bảng HTTP mặc định áp dụng cho mọi ứng dụng. Ví dụ dùng HTTP Basic nên request anonymous đến endpoint bảo vệ được kỳ vọng 401. Với form login, status của cùng tình huống có thể là redirect 302; với thiết kế che giấu tài nguyên, một số từ chối có thể được ánh xạ 404 theo yêu cầu sản phẩm.

Quy tắc diễn giải từng ô:

- **Allow case**: status đúng với hành động được phép (`200`, `201`, `204`), và nếu có side effect thì side effect đúng.
- **Deny case vì chưa xác thực**: HTTP 401; nếu dùng Basic, kiểm tra `WWW-Authenticate` challenge.
- **Deny case vì thiếu quyền**: HTTP 403; không được tạo/xóa tài liệu dù request có payload hợp lệ.
- **Public case**: anonymous phải vào được; authenticated cũng không được chặn vô cớ.
- **Default deny**: path/method chưa khai báo không tự nhiên được phép. Dành test riêng cho matcher tổng quát.

Tổng cộng ma trận trên có 11 allow case và 9 deny case. Con số chỉ dùng để đối chiếu số dòng test trong **chính ví dụ này**; với hệ thống thật số ca tăng theo actor, HTTP method, resource context và policy nghiệp vụ.

## 3. Quy trình chuyển ma trận thành test case

### Bước 1 — Cố định nguồn đặc tả

Ghi rõ actor, method, path pattern, quyền yêu cầu, hành vi dự kiến và chính sách ngoại lệ. Đặc biệt phân biệt quyền trên **endpoint** với quyền trên **từng bản ghi**:

- `GET /api/docs/{id}` được phép bởi `DOC_READ` ở tầng URL chưa chắc đủ; có thể còn cần điều kiện `doc.tenantId == principal.tenantId` hoặc `doc.ownerId == principal.id`.
- Một actor vừa có `DOC_READ` vừa có `ROLE_ADMIN` cũng không tự được miễn kiểm tra tenant nếu nghiệp vụ không cho phép.
- Có thể yêu cầu chặn đối tượng khác tenant bằng 403 hoặc trả 404 để hạn chế lộ sự tồn tại; kỳ vọng phải lấy từ chính sách, không đoán.

### Bước 2 — Mỗi ô tạo ít nhất một request độc lập

Một ca gồm `caseId`, `method`, `path`, `actor`, điều kiện fixture, expected status và side effect. Ví dụ:

```text
DOC_READ_ANON       GET     /api/docs/42    anonymous  -> 401
DOC_READ_READER     GET     /api/docs/42    reader     -> 200
DOC_CREATE_READER   POST    /api/docs       reader     -> 403
DOC_CREATE_EDITOR   POST    /api/docs       editor     -> 201
DOC_DELETE_EDITOR   DELETE  /api/docs/42    editor     -> 403
DOC_DELETE_ADMIN    DELETE  /api/docs/42    admin      -> 204
```

Không gom “reader được đọc” và “reader không được xóa” thành một assertion; đó là **hai kỳ vọng khác nhau**. Dùng tên test có ý nghĩa để khi một ô thất bại, report chỉ đúng actor × action đang sai.

### Bước 3 — Dữ liệu fixture phải xác định

Tạo tài khoản, authorities, owner/tenant, bản ghi và trạng thái sao cho mỗi lần chạy có cùng điều kiện. Với HTTP Basic, `reader`/`editor`/`admin` có thể là tài khoản in-memory ở test. Với JWT, test có thể dùng `jwt()` request post-processor để mô phỏng claims, nhưng vẫn cần test riêng cho decoder/chữ ký/expiry nếu muốn kiểm chứng **xác thực thật**.

Đối với method làm thay đổi trạng thái, cung cấp CSRF token hợp lệ trong ca kiểm thử quyền **khi CSRF được bật**, rồi thêm một test riêng chứng minh request không có CSRF bị từ chối. Không kết luận “reader thiếu quyền” từ một 403 do thiếu CSRF.

### Bước 4 — So sánh kết quả đầy đủ

Bên cạnh status, cân nhắc `WWW-Authenticate`, `Location`, `Content-Type`, body/schema lỗi, đối tượng trả về, kiểm toán, log và **absence of side effects**. Một test deny chỉ kiểm tra status vẫn có thể bỏ sót lỗi “ghi DB trước khi trả 403”.

### Bước 5 — Chống lỗ hổng phủ sóng

Kiểm tra riêng: không có credential; credential sai; credential hợp lệ nhưng thiếu quyền; role/authority ngoài danh sách; method khác cùng path; path lồng nhau; resource owner/tenant khác; matcher theo thứ tự; nhiều `SecurityFilterChain`; anonymous vs remember-me nếu hệ thống dùng; CSRF và các luồng async/error dispatch có liên quan.

## 4. Ví dụ Java 17+ có thể chạy

Tạo một ứng dụng Spring Boot 3.x package `com.example.authorization`. Dùng các dependency **Spring Web**, **Spring Security**, **Spring Boot Test**, **Spring Security Test**. Với Gradle, ví dụ `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Thêm `settings.gradle`:

```groovy
rootProject.name = 'authorization-matrix-demo'
```

### 4.1. Cấu hình quyền bám sát ma trận

File `src/main/java/com/example/authorization/AuthorizationMatrixApplication.java`:

```java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationMatrixApplication.class, args);
    }
}
```

File `src/main/java/com/example/authorization/SecurityConfig.java`:

```java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/docs/*")
                    .hasAuthority("DOC_READ")
                .requestMatchers(HttpMethod.POST, "/api/docs")
                    .hasAuthority("DOC_WRITE")
                .requestMatchers(HttpMethod.DELETE, "/api/docs/*")
                    .hasAuthority("DOC_ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_READER", "DOC_READ")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_EDITOR", "DOC_READ", "DOC_WRITE")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_ADMIN", "DOC_READ",
                             "DOC_WRITE", "DOC_ADMIN")
                .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
```

Giải thích:

- `requestMatchers(HttpMethod.GET, "/api/docs/*")` và `requestMatchers(HttpMethod.DELETE, "/api/docs/*")` có **chính sách khác nhau trên cùng path**. Vì vậy không được chỉ test GET rồi coi DELETE đã được bảo vệ.
- `.hasAuthority("DOC_ADMIN")` yêu cầu đúng `DOC_ADMIN`. `.hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` theo convention. `admin` trong ví dụ được cấp cả hai nhưng đó là quyết định fixture, không phải quyền tự động kế thừa.
- `.anyRequest().denyAll()` mặc định từ chối request không được khai báo. Matcher được xét theo thứ tự và **chỉ rule khớp đầu tiên** được áp dụng; hãy đặt rule cụ thể trước rule tổng quát.
- `.httpBasic(...)` tạo một đường xác thực thực tế để test cả trường hợp anonymous, Basic credential hợp lệ và sai. `InMemoryUserDetailsManager` cùng mật khẩu cố định chỉ dành cho ví dụ học tập.
- CSRF mặc định vẫn được bật; test `POST`/`DELETE` sẽ dùng `.with(csrf())` để không vô tình biến ca phân quyền thành ca CSRF.
- Mặc định của Spring Security thường trả **401 Basic challenge** khi chưa xác thực; các ca đã xác thực thiếu quyền là **403**.

### 4.2. Một service để quan sát side effect

File `src/main/java/com/example/authorization/MutationCounter.java`:

```java
package com.example.authorization;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class MutationCounter {
    private final AtomicInteger mutations = new AtomicInteger();

    public void recordMutation() {
        mutations.incrementAndGet();
    }

    public int count() {
        return mutations.get();
    }
}
```

`MutationCounter` chỉ để chứng minh kiểm thử **không có thay đổi dữ liệu** khi request bị chặn. Trong dự án thật, thay thế bằng truy vấn repository, outbox, audit event hoặc trạng thái nghiệp vụ phù hợp.

File `src/main/java/com/example/authorization/DocumentController.java`:

```java
package com.example.authorization;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final MutationCounter counter;

    public DocumentController(MutationCounter counter) {
        this.counter = counter;
    }

    @GetMapping("/api/public")
    public Map<String, String> publicPage() {
        return Map.of("result", "public");
    }

    @GetMapping("/api/docs/{id}")
    public Map<String, String> read(@PathVariable String id) {
        return Map.of("id", id);
    }

    @PostMapping("/api/docs")
    public ResponseEntity<Map<String, String>> create() {
        counter.recordMutation();
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", "new"));
    }

    @DeleteMapping("/api/docs/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        counter.recordMutation();
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/admin/audit")
    public Map<String, String> audit() {
        return Map.of("result", "audit");
    }
}
```

Controller không tự kiểm tra role; security rules chặn request trước khi gọi controller. Side effects được đặt trong controller cho bài học; ứng dụng thực tế có thể có validation, service authorization, transaction hoặc kiểm tra từng record.

### 4.3. Chuyển toàn bộ 20 ô thành parameterized HTTP tests

File `src/test/java/com/example/authorization/AuthorizationMatrixTest.java`:

```java
package com.example.authorization;

import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMatrixTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MutationCounter counter;

    record AccessCase(
            String caseId,
            String method,
            String path,
            String actor,
            int expectedStatus) {
    }

    // Kỳ vọng được chép từ ma trận nghiệp vụ, không suy ra từ SecurityConfig.
    static Stream<AccessCase> permissionMatrix() {
        return Stream.of(
            new AccessCase("PUBLIC_ANON", "GET", "/api/public", null, 200),
            new AccessCase("PUBLIC_READER", "GET", "/api/public", "reader", 200),
            new AccessCase("PUBLIC_EDITOR", "GET", "/api/public", "editor", 200),
            new AccessCase("PUBLIC_ADMIN", "GET", "/api/public", "admin", 200),

            new AccessCase("READ_ANON", "GET", "/api/docs/42", null, 401),
            new AccessCase("READ_READER", "GET", "/api/docs/42", "reader", 200),
            new AccessCase("READ_EDITOR", "GET", "/api/docs/42", "editor", 200),
            new AccessCase("READ_ADMIN", "GET", "/api/docs/42", "admin", 200),

            new AccessCase("CREATE_ANON", "POST", "/api/docs", null, 401),
            new AccessCase("CREATE_READER", "POST", "/api/docs", "reader", 403),
            new AccessCase("CREATE_EDITOR", "POST", "/api/docs", "editor", 201),
            new AccessCase("CREATE_ADMIN", "POST", "/api/docs", "admin", 201),

            new AccessCase("DELETE_ANON", "DELETE", "/api/docs/42", null, 401),
            new AccessCase("DELETE_READER", "DELETE", "/api/docs/42", "reader", 403),
            new AccessCase("DELETE_EDITOR", "DELETE", "/api/docs/42", "editor", 403),
            new AccessCase("DELETE_ADMIN", "DELETE", "/api/docs/42", "admin", 204),

            new AccessCase("AUDIT_ANON", "GET", "/api/admin/audit", null, 401),
            new AccessCase("AUDIT_READER", "GET", "/api/admin/audit", "reader", 403),
            new AccessCase("AUDIT_EDITOR", "GET", "/api/admin/audit", "editor", 403),
            new AccessCase("AUDIT_ADMIN", "GET", "/api/admin/audit", "admin", 200)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("permissionMatrix")
    void enforcesEachExpectedDecision(AccessCase c) throws Exception {
        MockHttpServletRequestBuilder request = switch (c.method()) {
            case "GET" -> get(c.path());
            case "POST" -> post(c.path());
            case "DELETE" -> delete(c.path());
            default -> throw new IllegalArgumentException(c.method());
        };

        if (c.actor() != null) {
            request.with(httpBasic(c.actor(), "demo-pass"));
        }

        // Ca này kiểm thử authorization; CSRF luôn hợp lệ cho write.
        if (!"GET".equals(c.method())) {
            request.with(csrf());
        }

        int before = counter.count();

        mvc.perform(request)
            .andExpect(status().is(c.expectedStatus()));

        // 201/204 là hai hành động ghi thành công trong demo.
        int expectedMutations = c.expectedStatus() == 201
                || c.expectedStatus() == 204 ? 1 : 0;
        assertEquals(before + expectedMutations, counter.count(),
                c.caseId() + " changed state unexpectedly");
    }

    @Test
    void anonymousProtectedRequestReceivesBasicChallenge()
            throws Exception {
        mvc.perform(get("/api/docs/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void wrongBasicPasswordDoesNotBecomeAuthorized() throws Exception {
        mvc.perform(get("/api/docs/42")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedWriterStillNeedsCsrfForPost() throws Exception {
        int before = counter.count();

        mvc.perform(post("/api/docs")
                .with(httpBasic("editor", "demo-pass")))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.count());
    }

    @Test
    void unlistedRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedMethodIsNotAccidentallyAuthorized() throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("editor", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Điều kiện cho các test hoạt động:

1. `@SpringBootTest` khởi tạo cấu hình security và controller thật của ứng dụng học tập; `@AutoConfigureMockMvc` cung cấp `MockMvc` với filter chain được đăng ký.
2. `.with(httpBasic(...))` gửi Basic credentials vào security filter, kiểm thử đường xác thực thật hơn việc chỉ gắn `@WithMockUser`. Tài khoản chỉ tồn tại trong bộ user in-memory ví dụ.
3. `.with(csrf())` thêm CSRF token hợp lệ cho `POST`/`DELETE`, để kết quả phản ánh **quyết định quyền**; test `authorizedWriterStillNeedsCsrfForPost` tách riêng hành vi CSRF.
4. `status().is(c.expectedStatus())` so sánh giá trị từ ma trận với status HTTP thực tế.
5. `counter.count()` trước/sau bảo đảm 401/403 không làm thay đổi dữ liệu trong mô hình đơn giản; với giao dịch thật cần kiểm tra DB và event/audit log.
6. `permissionMatrix()` có đúng 20 test case theo thứ tự bảng quyền. Một quyền bị nới hoặc thắt sai sẽ khiến ít nhất một case fail nếu ma trận là đặc tả độc lập.
7. Mẫu đã đặt cả **allow** và **deny** cho từng hành động bảo vệ. Nó còn kiểm tra Basic credential sai, CSRF bị thiếu, path chưa khai báo và method chưa khai báo.

Không dùng `.standaloneSetup(controller)` đơn lẻ rồi kết luận đã kiểm thử authorization: cấu hình đó có thể bỏ qua Spring Security filters. Nếu tự xây MockMvc thay vì để Boot auto-configure, phải tích hợp Spring Security, ví dụ `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build()`.

### 4.4. Lệnh chạy và kết quả kỳ vọng

Chạy:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

`@ParameterizedTest` triển khai 20 lượt chạy từ `Stream<AccessCase>` và có 5 phương thức `@Test` bổ sung. Theo cấu hình được nêu, kỳ vọng là **25 lượt test thành công**; không nên tuyên bố đã PASS nếu chưa thực sự chạy lệnh trong một dự án có dependencies.

Chạy ứng dụng và thử bằng cURL:

```bash
./gradlew bootRun
curl -i http://localhost:8080/api/docs/42
curl -i -u reader:demo-pass http://localhost:8080/api/docs/42
curl -i -u reader:demo-pass -X DELETE http://localhost:8080/api/docs/42
curl -i -u admin:demo-pass http://localhost:8080/api/admin/audit
```

Với các request GET ở trên, kết quả mong đợi theo thứ tự là **401, 200, 403, 200**. Riêng lệnh `DELETE` không có CSRF token phù hợp cũng có thể bị **403 do CSRF**, vì vậy các lệnh cURL không chứng minh được lý do cụ thể khiến DELETE bị từ chối. Để cô lập authorization cho hành động ghi, dùng MockMvc `.with(csrf())` như ở test. Nếu muốn chạy thành công POST/DELETE từ client thật, cần thiết kế và cung cấp CSRF token hợp lệ theo session/cookie và mô hình xác thực của ứng dụng. Không tắt CSRF chỉ để làm cho ví dụ cURL ngắn hơn.

## 5. Tránh test xanh giả vì thiết lập môi trường

**Một request 200 chưa chắc chứng minh quyền chính xác.** Cần xác minh test đang chạy toàn bộ security chain và actor thực sự mang authority dự kiến. Những lỗi sau rất phổ biến:

- `@WithMockUser(roles = "ADMIN")` chỉ gán `ROLE_ADMIN`; nó không mặc nhiên gán `DOC_ADMIN`. Nếu endpoint đòi `hasAuthority("DOC_ADMIN")`, phải đưa đúng authority.
- `@WithMockUser` và `.with(user(...))` có ích cho test authorization nhanh, nhưng **không chứng minh** password/JWT được kiểm tra đúng. Khi muốn kiểm thử cả xác thực HTTP, phải dùng Basic credential hoặc cơ chế token phù hợp.
- Test 403 của POST mà quên CSRF token hợp lệ không chứng minh rằng rule `DOC_WRITE` hoạt động.
- Test chỉ dùng account có mọi authority sẽ không tìm ra lỗi cấp quyền quá rộng. Cần ít nhất một actor nằm **ngoài** policy cho mỗi action.
- MockMvc test dùng `standaloneSetup` mà không gắn `FilterChainProxy` có thể trả 200 dù production chặn 403.
- Dùng `.anyRequest().authenticated()` cho mọi URL có thể cho phép người `reader` truy cập hành động chưa được quy định. Nếu chính sách là *deny by default*, test cho các path/method chưa khai báo.
- Test sao chép hệt logic của implementation để tính expected status dẫn đến kiểm thử vòng tròn. Hãy coi ma trận đã duyệt là dữ liệu riêng của test.
- Chỉ assert status mà không assert side effect có thể bỏ sót lỗi tạo/xóa trước khi bị chặn.
- Đảo thứ tự matcher cụ thể và matcher rộng có thể làm quy tắc cụ thể vô hiệu. Spring Security xét rule theo thứ tự, áp dụng rule khớp đầu tiên.
- Không phân biệt 401/403 có thể che lỗi điều hướng đăng nhập hoặc rò rỉ quyền. Với form login hoặc chính sách 404, cập nhật expected theo contract thực tế.

## 6. Mở rộng ma trận sang quyền theo bản ghi, owner và tenant

Ma trận HTTP đơn giản là nền tảng. Trong ứng dụng thật, **cùng actor và endpoint** có thể cho kết quả khác nhau tùy tài nguyên:

| Ca theo ngữ cảnh | Fixture và chính sách | Kỳ vọng minh họa |
| --- | --- | --- |
| Chủ sở hữu đọc tài liệu | `readerA` có `DOC_READ`, `ownerId=readerA`, cùng tenant | 200 |
| Người khác đọc tài liệu riêng tư | `readerB` có `DOC_READ`, nhưng owner khác, không có quyền chia sẻ | 403 hoặc 404 theo đặc tả |
| Truy cập khác tenant | Actor có `DOC_READ`, `tenantId` không trùng | Từ chối; status theo chính sách chống enumeration |
| Admin vượt quyền owner | Chỉ khi nghiệp vụ cho phép và tenant boundary vẫn hợp lệ | 200 |
| Tài liệu không tồn tại | ID không có trong repository | 404 |
| Token sai/không có | Chưa xác thực | Thường 401 đối với REST Basic/Bearer |

Với bài toán này cần bổ sung policy phía service hoặc method authorization, ví dụ một `AuthorizationManager`/`@PreAuthorize` dùng dữ liệu owner/tenant được load từ nguồn đáng tin. **Không tin `ownerId`/`tenantId` do client tự gửi** rồi dùng trực tiếp để cho phép. Một test độc lập phải seed ít nhất hai owner và hai tenant, sau đó đối chiếu từng trường hợp.

Ví dụ ý tưởng dùng method authorization (đoạn minh họa, cần triển khai `documentPolicy` và bật `@EnableMethodSecurity` trong ứng dụng thực):

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentDto readDocument(@P("documentId") long documentId) {
    return documentService.get(documentId);
}
```

Đây **không phải tệp Java độc lập**; `@PreAuthorize` đến từ `org.springframework.security.access.prepost.PreAuthorize`, `@P` đến từ `org.springframework.security.core.parameters.P`. Trong test tích hợp, kiểm tra `readDocument` với cùng actor nhưng `documentId` của owner khác, tenant khác và cùng owner. Chỉ kiểm tra quyền URL `DOC_READ` là chưa đủ để chứng minh không có lỗi IDOR/BOLA (*Broken Object Level Authorization*).

Ngoài ra cần xét trạng thái tài nguyên (`DRAFT`, `PUBLISHED`, `LOCKED`), phương thức (read/update/delete), scope OAuth2, và thứ tự cấp quyền/deny override nếu nghiệp vụ quy định. Không nhân mọi chiều một cách máy móc dẫn đến số test khổng lồ: trước hết bảo đảm **mọi quyết định bảo mật khác nhau** đều có ca positive/negative, rồi thêm các cặp biên đại diện.

## 7. Cách quản lý độ phủ và chất lượng test

Có thể dùng bảng theo dõi quyền riêng của sản phẩm:

| Case ID | Method/path | Actor/fixture | Expected | Actual | Evidence |
| --- | --- | --- | --- | --- | --- |
| `DOC_CREATE_READER` | `POST /api/docs` | `reader` + CSRF hợp lệ | 403, không ghi DB | Từ CI | MockMvc + repository assertion |
| `DOC_CREATE_EDITOR` | `POST /api/docs` | `editor` + CSRF hợp lệ | 201, một bản ghi mới | Từ CI | MockMvc + repository assertion |
| `DOC_READ_OTHER_TENANT` | `GET /api/docs/42` | `readerB` tenant khác | 403/404 theo contract | Từ CI | Test fixture hai tenant |
| `UNLISTED_DELETE` | `DELETE /api/unknown` | `admin` + CSRF hợp lệ | Deny by default | Từ CI | Matcher coverage |

Ba chỉ báo nên theo dõi:

1. **Matrix coverage**: số quyết định có test chia cho tổng số quyết định đã duyệt trong phạm vi. Ví dụ phần 2 có 20/20 ô cụ thể.
2. **Negative coverage**: mọi hành động yêu cầu quyền đều có ca anonymous và ít nhất một actor đã xác thực nhưng **thiếu quyền**. Nếu chỉ test anonymous, có thể bỏ qua lỗi cấp quyền quá rộng cho người dùng nội bộ.
3. **Behavior coverage**: các ca cho phép xác nhận response và tác động mong đợi; các ca bị từ chối xác nhận **không có side effect**, không tiết lộ dữ liệu và đúng status/header.

Khi thêm role, authority, endpoint, HTTP method hoặc trạng thái tài nguyên, cập nhật **ma trận trước**, rồi cập nhật test. Nếu test fail do chính sách mới, review yêu cầu quyền với người chịu trách nhiệm; đừng sửa expected chỉ để CI xanh.

## 8. Câu hỏi tự kiểm tra

1. Vì sao cần cả test 200 và 403 cho `GET /api/docs/42`? Vì test 200 xác nhận người đủ quyền vào được; test 403 xác nhận người thiếu `DOC_READ` không được đọc.
2. Vì sao anonymous và `reader` có thể nhận hai status khác nhau khi gọi `DELETE /api/docs/42`? Anonymous cần xác thực (thường 401); `reader` đã xác thực nhưng thiếu `DOC_ADMIN` (403), miễn CSRF test đã hợp lệ.
3. Vì sao phải thêm `.with(csrf())` vào test `POST`/`DELETE`? Để khi CSRF protection bật, test phân quyền không bị đánh lạc hướng bởi 403 do CSRF.
4. `hasRole("ADMIN")` khác `hasAuthority("DOC_ADMIN")` ở đâu? Điều kiện thứ nhất yêu cầu `ROLE_ADMIN` theo mặc định, điều kiện thứ hai yêu cầu chính xác `DOC_ADMIN`.
5. Vì sao test status 403 không đủ để chứng minh an toàn? Vì request có thể đã thực hiện thay đổi trạng thái trước khi lỗi bị xử lý; cần kiểm tra DB/event/counter.
6. Vì sao hai người cùng có `DOC_READ` vẫn có thể được phép/không được phép đọc cùng một ID? Vì policy owner/tenant/trạng thái tài nguyên có thể bổ sung điều kiện ngoài quyền đường dẫn.
7. Vì sao một bộ test lấy expected từ `SecurityConfig` dễ bỏ sót bug? Vì khi cấu hình sai, logic tạo expected có thể sao chép cùng lỗi; đặc tả nghiệp vụ phải độc lập với implementation.

## Tài liệu chính thức

- [Authorize HTTP Requests — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring MVC Test Integration — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [MockMvc Test Setup — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Running as a User in MockMvc — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [CSRF Testing — Spring Security](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Testing Method Security — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)