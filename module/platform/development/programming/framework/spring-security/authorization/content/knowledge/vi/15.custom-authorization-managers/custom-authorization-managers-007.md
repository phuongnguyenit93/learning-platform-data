# Đăng ký manager qua access ở mức HTTP

> **Phạm vi:** Spring Security – authorization → **AuthorizationManager tùy chỉnh**. Trọng tâm là đưa một `AuthorizationManager<RequestAuthorizationContext>` vào cấu hình `SecurityFilterChain` bằng `authorizeHttpRequests(...).requestMatchers(...).access(manager)`, để quyết định quyền trên **HTTP servlet request**. Ví dụ Java 17+ dùng Spring Boot 3.x và Spring Security 6.x; những thay đổi API đáng lưu ý ở Spring Security 7.x được giải thích riêng.

## 1. Bài toán: quyền phụ thuộc cả người dùng và tài nguyên trong URL

Một API có các đường dẫn:

~~~text
GET /api/public/ping           → công khai
GET /api/documents/101         → phải có DOC_READ và là chủ sở hữu tài liệu 101
GET /api/documents/202         → phải có DOC_READ và là chủ sở hữu tài liệu 202
Mọi request khác              → từ chối theo mặc định
~~~

Giả sử `alice` sở hữu tài liệu `101` và `bob` sở hữu `202`. Chỉ dùng:

~~~java
.requestMatchers("/api/documents/**").hasAuthority("DOC_READ")
~~~

thì người có `DOC_READ` có thể đi qua bước kiểm tra HTTP cho **mọi** tài liệu, dù không sở hữu. Để xét cả `Authentication` lẫn trạng thái tài nguyên đã lưu ở server, ta đưa logic vào một authorization manager riêng và đăng ký bằng `.access(...)`.

Ví dụ khung:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .access(documentReadManager)
    .anyRequest().denyAll()
);
~~~

Ý nghĩa ở đây là **một request khớp HTTP method + path được đưa cho manager để ra quyết định**. `.access(...)` nhận một đối tượng thực thi `AuthorizationManager<RequestAuthorizationContext>`; đó không phải URL, không phải vai trò, cũng không phải tên bean viết dưới dạng chuỗi SpEL.

## 2. Các thành phần trong đường xử lý

~~~text
HTTP request
    |
    v
Spring Security FilterChainProxy
    |
    +-- các filter xác thực (Basic, Bearer, session, ...)
    |
    v
AuthorizationFilter
    |
    | Supplier<Authentication>, HttpServletRequest
    v
RequestMatcherDelegatingAuthorizationManager
    |
    | thử các requestMatchers theo thứ tự
    v
Rule khớp: .access(documentReadManager)
    |
    | RequestAuthorizationContext(request, path variables)
    v
documentReadManager
    |
    +-- lấy Authentication khi cần
    +-- lấy documentId từ URL đã match
    +-- kiểm tra quyền + dữ liệu từ nguồn tin cậy
    |
    +-- allow -> tiếp tục đến controller
    |
    +-- deny  -> AccessDeniedException
                   |
                   v
            ExceptionTranslationFilter
            -> HTTP 401/403 tùy trạng thái xác thực và entry point
~~~

Các khái niệm cần phân biệt:

| Thành phần | Chức năng |
| --- | --- |
| `SecurityFilterChain` | Xác định filter bảo vệ request; tạo bởi `HttpSecurity.build()` |
| `authorizeHttpRequests` | Khai báo các quy tắc ủy quyền ở HTTP layer |
| `requestMatchers` | **Chọn request** mà quy tắc sẽ áp dụng, theo path, HTTP method hoặc matcher tùy biến |
| `.access(manager)` | **Chọn cách ra quyết định** cho request đã khớp |
| `AuthorizationManager<RequestAuthorizationContext>` | Hàm quyết định được phép hay từ chối |
| `Supplier<Authentication>` | Cho phép trì hoãn lấy thông tin người dùng cho đến lúc cần |
| `RequestAuthorizationContext` | Chứa `HttpServletRequest` và các path variable mà matcher trích xuất |
| `AuthorizationDecision` | Đối tượng biểu diễn quyết định `granted = true/false` |
| `AuthorizationFilter` | Áp dụng kết quả để cho request đi tiếp hoặc bị chặn |

**Phân biệt “match” và “authorize”:** một request khớp `GET /api/documents/{documentId}` chỉ có nghĩa là đi vào manager dành cho tuyến đó. Khớp đường dẫn **không có nghĩa đã được quyền**.

## 3. Quy tắc quan trọng nhất khi khai báo `.access(...)`

### 3.1. Viết manager đúng kiểu ngữ cảnh

Trong Spring Security servlet:

~~~java
AuthorizationManager<RequestAuthorizationContext> documentReadManager = /* ... */;
~~~

`RequestAuthorizationContext` ở package:

~~~java
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
~~~

Có hai dữ liệu thường dùng:

~~~java
context.getRequest()               // HttpServletRequest
context.getVariables()             // Map<String, String> từ request matcher
context.getVariables().get("documentId")
~~~

Không nhầm với `MethodInvocation` của Method Security hoặc `ServerWebExchange` của WebFlux. API reactive dùng `ReactiveAuthorizationManager<AuthorizationContext>` và DSL khác; đoạn code servlet trong bài này không đem áp dụng trực tiếp cho ứng dụng WebFlux.

### 3.2. Các rule được xét theo thứ tự, rule khớp đầu tiên quyết định

Ví dụ sai:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .access(documentReadManager)
    .anyRequest().denyAll()
)
~~~

`/api/**` đứng trước sẽ cho phép `GET /api/documents/101`, nên custom manager **không được gọi**. Đây là một lỗi quyền nghiêm trọng, dù bản thân manager viết chính xác.

Đặt quy tắc hẹp ở trước quy tắc rộng. Nếu cho phép một path công khai, giữ đúng phạm vi:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .access(documentReadManager)
    .anyRequest().denyAll()
)
~~~

`anyRequest().denyAll()` là chốt dự phòng cho các endpoint không được khai báo. Đối với một service cố ý chỉ công bố một số API, đó là cách giảm nguy cơ mở nhầm endpoint sau khi thêm controller mới.

### 3.3. `securityMatcher` khác `requestMatchers`

`http.securityMatcher("/api/**")` quyết định **toàn bộ SecurityFilterChain này áp dụng cho request nào**. Trong khi đó `requestMatchers("/api/documents/**")` chỉ chọn **quy tắc bên trong chain đã được chọn**.

Với nhiều `SecurityFilterChain`, Spring Security chọn chain đầu tiên khớp `securityMatcher` dựa trên thứ tự chain. Nếu không chain nào khớp, request có thể nằm ngoài những chốt authorization đang xét. Vì vậy, không coi `anyRequest().denyAll()` bên trong một chain chỉ bảo vệ `/api/**` là chốt cho toàn bộ ứng dụng. Phải kiểm tra cả chain dự phòng và thứ tự `@Order`.

## 4. Xây một ví dụ Spring Boot hoàn chỉnh

Ví dụ này độc lập với database: một repository trong bộ nhớ chứa hai tài liệu để ta quan sát chính sách. Quy tắc: request phải được xác thực, người gọi có authority chính xác `DOC_READ`, và tài liệu thuộc về người gọi. Nếu ID không hợp lệ hoặc không tìm thấy tài liệu, manager **từ chối**.

Ví dụ sử dụng **Spring Boot 3.x + Spring Security 6.x**, Java 17+. Người học cần một dự án Gradle Spring Boot đã có plugin `org.springframework.boot` và dependency management phù hợp. Nếu đã dùng Spring Boot 4/Security 7, xem mục phiên bản trước khi đổi API/khóa dependency.

### 4.1. Khai báo dependency

Trong `build.gradle` của dự án Spring Boot hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không cần bật `@EnableMethodSecurity` để dùng authorization tại HTTP layer: chúng là hai ranh giới cấu hình khác nhau. `@EnableMethodSecurity` chỉ cần khi muốn dùng annotation như `@PreAuthorize` ở service.

Các file Java bên dưới có package `demo.httpauth`. Cùng package giúp `@SpringBootApplication` tìm thấy bean, controller và cấu hình.

### 4.2. Application

**`src/main/java/demo/httpauth/HttpAuthApplication.java`**

~~~java
package demo.httpauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpAuthApplication.class, args);
    }
}
~~~

### 4.3. Tài liệu và kho dữ liệu

**`src/main/java/demo/httpauth/Document.java`**

~~~java
package demo.httpauth;

public record Document(long id, String owner, String title) {
}
~~~

**`src/main/java/demo/httpauth/DocumentStore.java`**

~~~java
package demo.httpauth;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {
    private final Map<Long, Document> documents = Map.of(
        101L, new Document(101L, "alice", "Alice document"),
        202L, new Document(202L, "bob", "Bob document")
    );

    public Optional<Document> findById(long documentId) {
        return Optional.ofNullable(documents.get(documentId));
    }
}
~~~

Dữ liệu owner được lấy từ repository tin cậy, **không phải từ query parameter/header mà client tự gửi**. Trong dự án thật, nên kiểm tra theo user ID bất biến và tenant đã xác minh, không coi username là định danh vĩnh viễn.

### 4.4. Đưa quy tắc nghiệp vụ vào lớp riêng

**`src/main/java/demo/httpauth/DocumentHttpPolicy.java`**

~~~java
package demo.httpauth;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentHttpPolicy {
    private final DocumentStore store;

    public DocumentHttpPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, String rawId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        boolean hasReadAuthority = authentication.getAuthorities().stream()
                .anyMatch(authority -> "DOC_READ".equals(authority.getAuthority()));
        if (!hasReadAuthority || rawId == null) {
            return false;
        }

        final long documentId;
        try {
            documentId = Long.parseLong(rawId);
        } catch (NumberFormatException invalidId) {
            return false;
        }

        return store.findById(documentId)
                .map(document -> document.owner().equals(authentication.getName()))
                .orElse(false);
    }
}
~~~

Ở đây `DocumentHttpPolicy` là lớp Java bình thường, trả `boolean`. Nó nhận `Authentication` và ID do matcher trích từ URL. Những bước bảo vệ gồm:

1. Từ chối anonymous, người chưa xác thực và authentication thiếu.
2. Kiểm tra authority `DOC_READ` **đúng chuỗi**, không nhầm với role `ROLE_DOC_READ`.
3. Xử lý ID không phải số hoặc thiếu path variable bằng kết quả `false`, tránh làm phát sinh lỗi 500 từ phép parse.
4. Tìm tài liệu tại server; nếu không tồn tại, trả `false`.
5. Đối chiếu owner thực của tài liệu với danh tính đã xác thực.

Trong ứng dụng thật, phải cân nhắc tenant, trạng thái khóa, sự thay đổi quyền và giao dịch; ví dụ đơn giản này chỉ minh họa quyết định ở HTTP layer.

### 4.5. Đăng ký `AuthorizationManager` bằng `@Bean`

**`src/main/java/demo/httpauth/SecurityConfig.java`**

~~~java
package demo.httpauth;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfig {

    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentReadManager(
            DocumentHttpPolicy policy) {

        return (authenticationSupplier, context) -> {
            // Supplier lấy Authentication khi manager thực sự cần.
            var authentication = authenticationSupplier.get();
            String rawId = context.getVariables().get("documentId");

            return new AuthorizationDecision(policy.canRead(authentication, rawId));
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Qualifier("documentReadManager")
            AuthorizationManager<RequestAuthorizationContext> manager)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
                    .access(manager)
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Các chi tiết cần hiểu:

- `@Bean` trả về **một instance** có kiểu `AuthorizationManager<RequestAuthorizationContext>`. Cấu hình `SecurityFilterChain` nhận instance đó qua dependency injection. `@Qualifier("documentReadManager")` tránh nhập nhằng khi ứng dụng sau này có nhiều authorization manager.
- `.requestMatchers(HttpMethod.GET, ".../{documentId}")` chỉ áp dụng rule này cho method **GET** và đường dẫn hợp lệ. Biến `documentId` đến từ matcher, không phải từ việc tự tách `request.getRequestURI()` bằng chuỗi.
- `.access(manager)` nối manager đã đăng ký vào rule. Chỉ có rule đó gọi logic `DocumentHttpPolicy`.
- `.anyRequest().denyAll()` từ chối những request không được công bố; nếu muốn cho phép endpoint khác, khai báo quy tắc của nó một cách rõ ràng.
- `.httpBasic(...)` là cơ chế xác thực đơn giản để thử ví dụ. HTTP Basic phải được dùng trên HTTPS trong môi trường thực; với API sử dụng JWT/session có thể thay bằng cơ chế xác thực phù hợp mà vẫn tái sử dụng ý tưởng của manager.
- Ví dụ không tắt CSRF. Các request GET được dùng để minh họa; khi thêm POST/PUT/DELETE phải kiểm tra cả chính sách CSRF và kiểu authentication, không tự động tắt bảo vệ CSRF cho mọi ứng dụng.

**Vì sao ví dụ dùng lambda?** `AuthorizationManager` là functional interface, nhưng chữ ký phương thức trừu tượng thay đổi qua các dòng phiên bản. Lambda có target type rõ và trả về `AuthorizationDecision` giúp code gọn, tương thích dễ dàng hơn giữa Spring Security 6.5 và 7.x. Nếu cần inject nhiều service, cache có kiểm soát hay nhiều phương thức hỗ trợ, có thể triển khai thành một class riêng `@Component`; mục 7 giải thích hai phiên bản chữ ký.

### 4.6. Controller phục vụ HTTP request

**`src/main/java/demo/httpauth/DocumentController.java`**

~~~java
package demo.httpauth;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DocumentController {
    private final DocumentStore store;

    public DocumentController(DocumentStore store) {
        this.store = store;
    }

    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{documentId}")
    public Document read(@PathVariable long documentId) {
        return store.findById(documentId).orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Nếu manager từ chối, lời gọi **không đến** thân `read`. Nếu manager cho phép nhưng tài liệu bị xóa giữa khi kiểm tra và khi controller đọc, controller trả 404 theo nhánh xử lý của nó. Với hệ thống thực cần loại bỏ khoảng cách giữa kiểm tra và sử dụng cho tài nguyên nhạy cảm; hãy xem mục 9.

## 5. Kiểm thử HTTP thật qua `MockMvc`

Để bảo đảm rule đã đăng ký và manager thực sự chạy, test phải đi qua **filter chain**, không chỉ gọi `new DocumentHttpPolicy(...)`. Spring Security Test cung cấp `@WithMockUser` để mô phỏng người dùng xác thực cho các test.

**`src/test/java/demo/httpauth/DocumentHttpAuthorizationTest.java`**

~~~java
package demo.httpauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = HttpAuthApplication.class)
@AutoConfigureMockMvc
class DocumentHttpAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicPingIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());
    }

    @Test
    void privateDocumentRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerWithReadAuthorityCanAccessDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void otherOwnerIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void ownerWithoutReadAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void bobCanAccessHisDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(202));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingDocumentIsDeniedByTheManager() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void malformedDocumentIdIsDenied() throws Exception {
        mvc.perform(get("/api/documents/not-a-number"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Giải thích kết quả:** không có thông tin xác thực trên endpoint cần login, HTTP Basic trả `401 Unauthorized`; đã xác thực nhưng không đạt chính sách, filter trả `403 Forbidden`. Phân biệt chính xác còn tùy `AuthenticationEntryPoint`, `AccessDeniedHandler` và cấu hình xác thực thực tế; test trên kiểm tra hành vi của cấu hình mẫu.

Test ID không tồn tại mong `403` vì policy được thiết kế trả `false` trước controller. Một ứng dụng khác có thể chọn 404 cho tài nguyên ngoài quyền nhằm tránh lộ sự tồn tại, nhưng phải thực hiện nhất quán và không để controller mở đường vượt chính sách.

Chạy từ thư mục dự án Gradle đã cấu hình Spring Boot:

~~~text
./gradlew test --tests demo.httpauth.DocumentHttpAuthorizationTest
~~~

Trên Windows:

~~~text
gradlew.bat test --tests demo.httpauth.DocumentHttpAuthorizationTest
~~~

Các lớp mẫu không gọi `System.out.println` nên không có stdout nghiệp vụ cố định. Kết quả cần đạt là mọi assertion đều xanh và Gradle hoàn thành `test`. Nếu project khác dùng context path, filter chain bổ sung hoặc thay cơ chế xác thực, cập nhật test cho đúng cấu hình thực trước khi kết luận.

## 6. Kiểm thử riêng logic manager và cách kiểm tra fail-closed

Test HTTP cho biết filter chain thực thi chốt quyền; ngoài ra có thể viết unit test cho policy để thử nhanh mọi nhánh:

**`src/test/java/demo/httpauth/DocumentHttpPolicyTest.java`**

~~~java
package demo.httpauth;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentHttpPolicyTest {
    private final DocumentHttpPolicy policy =
            new DocumentHttpPolicy(new DocumentStore());

    private Authentication user(String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
                name, "unused",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void requiresOwnershipAndAuthority() {
        assertTrue(policy.canRead(user("alice", "DOC_READ"), "101"));
        assertFalse(policy.canRead(user("bob", "DOC_READ"), "101"));
        assertFalse(policy.canRead(user("alice", "OTHER"), "101"));
    }

    @Test
    void missingOrMalformedResourceIsDenied() {
        assertFalse(policy.canRead(user("alice", "DOC_READ"), "999"));
        assertFalse(policy.canRead(user("alice", "DOC_READ"), "xyz"));
        assertFalse(policy.canRead(user("alice", "DOC_READ"), null));
    }

    @Test
    void absentAuthenticationIsDenied() {
        assertFalse(policy.canRead(null, "101"));
    }
}
~~~

Unit test trên khởi tạo `DocumentHttpPolicy` trực tiếp, **không kiểm tra được** `SecurityFilterChain` có đăng ký manager hay không; do đó không được bỏ test `MockMvc`.

Có thể chạy cả hai test:

~~~text
./gradlew test --tests demo.httpauth.DocumentHttpPolicyTest --tests demo.httpauth.DocumentHttpAuthorizationTest
~~~

Một chính sách HTTP an toàn nên có cả tình huống **không tồn tại**, **sai kiểu ID**, **không xác thực**, **thiếu authority**, **không phải owner** và **được phép**. Nếu một nhánh bất thường không xác định được quyền, hãy từ chối rõ ràng. Không tự bắt mọi exception rồi trả `new AuthorizationDecision(true)` để “giữ hệ thống hoạt động”.

## 7. API `AuthorizationManager` theo phiên bản: `check` và `authorize`

Đây là chi tiết dễ gây lỗi khi sao chép một ví dụ Spring Security cũ sang bản mới.

| Dòng Spring Security | Contract đáng chú ý | Lưu ý |
| --- | --- | --- |
| **6.0–6.3** | `AuthorizationManager` dùng phương thức `check(Supplier<Authentication>, T)` trả `AuthorizationDecision` hoặc `null` | Các ví dụ triển khai class thường override `check` |
| **6.4–6.5** | Thêm `authorize(Supplier<Authentication>, T)` trả `AuthorizationResult`; `check` còn tồn tại nhưng được đánh dấu deprecated | Khi chuyển phiên bản, kiểm tra interface và ưu tiên hình thức được API khuyến nghị |
| **7.x** | Phương thức chính là `authorize(Supplier<? extends Authentication>, T)` trả `AuthorizationResult`; `check` cũ đã bị loại khỏi contract | Lớp tùy chỉnh override `check` theo mã 6.x không thể mặc nhiên dùng nguyên vẹn |

Một lớp custom viết cho **Spring Security 6.5** có thể có dạng:

~~~java
// Minh họa riêng cho 6.5; không cần thêm vào ví dụ mục 4.
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        RequestAuthorizationContext context) {
    // ... kiểm tra quyền và tài nguyên
    return new AuthorizationDecision(false);
}
~~~

Trong **Spring Security 7.x**, chữ ký được chuyển thành:

~~~java
// Minh họa riêng cho 7.x; import AuthorizationResult và kiểu Supplier tương ứng.
@Override
public AuthorizationResult authorize(
        Supplier<? extends Authentication> authentication,
        RequestAuthorizationContext context) {
    // ... kiểm tra quyền và tài nguyên
    return new AuthorizationDecision(false);
}
~~~

Hai đoạn trên chỉ minh họa phương thức cần đặt **bên trong** một implementation tương ứng, không phải hai method để copy cùng lúc vào một class.

Vì `AuthorizationDecision` thực thi `AuthorizationResult` ở dòng mới, một lambda được gán đúng kiểu:

~~~java
AuthorizationManager<RequestAuthorizationContext> manager =
        (authentication, context) -> new AuthorizationDecision(false);
~~~

là cách ngắn gọn cho phần quyết định đơn giản, tránh tự ghi chữ ký method khác nhau giữa hai dòng API. Dù vậy, phải **biên dịch và chạy test trên phiên bản Spring Security đã khóa**; không xem sự giống nhau của lambda là bảo đảm cho mọi thay đổi framework.

Nếu một custom manager trả `null` ở API cho phép abstain, đó không phải `true`. Ngữ nghĩa khi không có quyết định phụ thuộc thành phần gọi và composition; tại ranh giới yêu cầu nghiêm ngặt, nên trả kết quả **cho phép/từ chối tường minh**. Ví dụ mục 4 luôn trả `AuthorizationDecision(boolean)`.

## 8. Khi nào dùng `.access(manager)` thay cho quy tắc có sẵn?

| Yêu cầu | Cách thể hiện hợp lý |
| --- | --- |
| Endpoint công khai | `permitAll()` |
| Chỉ cần có người dùng đăng nhập | `authenticated()` |
| Một quyền cố định | `hasAuthority("DOC_READ")` |
| Role mặc định | `hasRole("ADMIN")` tương ứng authority `ROLE_ADMIN` theo prefix mặc định |
| Cần cả nhóm authority | Một manager tổ hợp kiểu `allOf(...)` hoặc quy tắc cấu hình phù hợp phiên bản |
| Cần người dùng + owner + trạng thái tài nguyên + tenant | `.access(customAuthorizationManager)` |
| Một tập URL cần gọi cùng policy engine | Đăng ký một manager dùng chung trên các matcher phù hợp |
| Quy tắc thuộc nội dung kết quả/hành động service | Kết hợp với `@PreAuthorize`/`@PostAuthorize` hoặc kiểm tra ở domain/service boundary |

Không phải điều kiện nào cũng cần một class custom. Với `hasAuthority("DOC_READ")` ngắn gọn, dùng built-in dễ đọc hơn. Chỉ đưa vào manager riêng khi cần **logic có trạng thái/tài nguyên**, truy vấn hoặc chính sách cần tái sử dụng nhiều nơi.

Ví dụ đặt manager ở một rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
    .access(documentReadManager)
~~~

Có thể dùng manager ở `anyRequest()` khi mọi request của chain thực sự cần cùng một chính sách:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .anyRequest().access(sharedPolicy)
)
~~~

Nhưng khi đó `RequestAuthorizationContext.getVariables()` có thể **không có biến `documentId`** vì matcher là `anyRequest()`. Nếu policy mong một path variable, nó phải biết xử lý ngữ cảnh thiếu biến; ví dụ `DocumentHttpPolicy` trả `false`. **Không tái sử dụng mù quáng một manager dựa vào path ID cho mọi URL.**

Với các endpoint cùng loại nhưng có nhiều method, có thể tạo manager riêng cho hành động đọc/ghi hoặc đưa operation có cấu trúc rõ vào policy; đừng cho phép mọi HTTP method chỉ vì cùng đường dẫn. Nếu dựa vào `GET`/`POST`/`DELETE`, cần test từng method và ràng buộc CSRF/transaction thích hợp.

## 9. Những vấn đề thực tế cần cân nhắc

### 9.1. Đừng tin dữ liệu chủ sở hữu do client tự khai

Ví dụ sai về ý tưởng:

~~~java
// Không được coi owner trong request là bằng chứng cấp quyền.
String ownerFromQuery = request.getParameter("owner");
boolean allowed = ownerFromQuery.equals(authentication.getName());
~~~

Người gọi tự chọn `owner`; nó không chứng minh tài liệu thuộc về họ. Chính sách đúng lấy `documentId` từ URL đã khớp, tra cứu tài liệu tại repository và so sánh owner của **dữ liệu tin cậy** với định danh đã xác thực. Khi có multi-tenant, tenant ID cũng phải lấy từ nguồn được xác minh, không chỉ từ header tùy ý.

### 9.2. Path variable của matcher và path variable ở controller

`context.getVariables().get("documentId")` được trích từ request matcher thuộc Spring Security. `@PathVariable("documentId")` trong controller do Spring MVC phân giải khi controller chạy. Chúng thường cùng dùng biểu mẫu URL, nhưng là **hai thời điểm xử lý riêng**.

Không giả định manager đã có sẵn `HandlerMethod` hoặc kết quả phân giải tham số của controller. Trong filter chain, MVC handler có thể chưa được gọi. Nếu matcher không hỗ trợ capture biến, `getVariables()` có thể trống. Có thể dùng `RequestMatcher` cụ thể có hỗ trợ trích xuất biến, hoặc thiết kế manager không lệ thuộc vào biến từ matcher.

`context.getRequest()` cung cấp `HttpServletRequest` để đọc HTTP method, đường dẫn, header hoặc remote address nếu thực sự cần. Cẩn thận với proxy/load balancer khi dùng IP; không tin thẳng `X-Forwarded-For` nếu hạ tầng chưa cấu hình forwarded headers và trusted proxy đúng cách.

### 9.3. Có thể phát sinh hai lần đọc dữ liệu

Trong ví dụ, manager gọi repository để xác minh owner; sau đó controller lại đọc tài liệu để trả kết quả. Với database thật:

~~~text
T1: manager đọc document 101, owner=alice -> allow
T2: giao dịch khác đổi owner hoặc tenant
T3: controller đọc lại document 101 đã đổi -> có thể trả dữ liệu ngoài quyền
~~~

Đây là **time-of-check/time-of-use**. Đối với tài nguyên nhạy cảm, cần kiểm soát bằng transaction, truy vấn ràng buộc owner/tenant trực tiếp ở tầng dữ liệu, khóa/optimistic locking hoặc một cơ chế kiểm tra hợp nhất vào truy vấn/cập nhật. Authorization ở filter không đảm bảo state database sẽ không đổi trong cả vòng xử lý request.

Bên cạnh đó, manager kiểm tra từng request có thể gây truy vấn lặp/N+1 khi mỗi request kiểm tra nhiều đối tượng. Dùng repository projection tối thiểu, cache có kiểm soát theo user/tenant và đo lường số query; không cache kết quả “allow” theo mỗi document ID mà quên ràng buộc danh tính và phiên bản chính sách.

### 9.4. Chính sách ở HTTP và ở method không thay thế lẫn nhau

`authorizeHttpRequests(...).access(manager)` bảo vệ request **đi qua web security filter chain**. Nhưng cùng service có thể được gọi từ job, message consumer, test, scheduler hoặc code nội bộ không đi qua HTTP. Nếu nghiệp vụ nhạy cảm, còn cần **điểm chặn ở service/domain/data layer** phù hợp.

`@PreAuthorize` dùng Spring Method Security và proxy; `AuthorizationManager<RequestAuthorizationContext>` dùng HTTP request context. Có thể tái sử dụng một **policy service thuần Java** cho cả hai điểm chặn, nhưng không nhầm hai generic context. Ví dụ `DocumentHttpPolicy` tách được dữ liệu nghiệp vụ nên có thể áp dụng ở lớp khác sau khi thiết kế lại tham số rõ ràng.

### 9.5. HTTP 401, 403, 404 và kiểm soát lộ thông tin

Thông thường:

- **401 Unauthorized**: request chưa xác thực phù hợp; `AuthenticationEntryPoint` bắt đầu quá trình xác thực (ví dụ Basic challenge).
- **403 Forbidden**: caller đã xác thực nhưng thiếu quyền; `AccessDeniedHandler` phản hồi.
- **404 Not Found**: đường dẫn/tài nguyên không tồn tại trong contract của application; một số hệ thống cố tình dùng 404 cho tài nguyên ngoài quyền để tránh tiết lộ sự tồn tại.

Không nên nhầm `AuthorizationDecision(false)` với một HTTP status được mã hóa sẵn. Filter và xử lý ngoại lệ quyết định status theo cơ chế xác thực. Test phải xác nhận toàn bộ đường đi. Log bảo mật nên lưu actor ID, resource ID và outcome an toàn, không ghi token hoặc payload nhạy cảm.

### 9.6. Dispatcher type, error dispatch và nhiều filter chain

`AuthorizationFilter` có thể chạy cho những dispatch như `REQUEST`, `FORWARD`, `ERROR`, `INCLUDE` tùy cấu hình và môi trường. Khi error handling làm một `ERROR` dispatch mới, rule `anyRequest().denyAll()` có thể từ chối dispatch đó; điều này khiến trang lỗi không hiện như dự kiến. Có thể khai báo có chủ đích:

~~~java
// Chỉ minh họa nếu ứng dụng thực sự cần forward/error dispatch.
.dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
    .permitAll()
~~~

Phải xem xét ý nghĩa của việc permit các dispatcher type này trong ứng dụng, thay vì chép máy móc. Trong ứng dụng có nhiều servlet hoặc servlet path khác mặc định, matcher cần cấu hình phù hợp; tài liệu Spring Security các dòng mới có hướng dẫn `PathPatternRequestMatcher`.

Nếu có nhiều `SecurityFilterChain`, phải bảo đảm mọi endpoint nhạy cảm khớp **một chain có chốt**. Có thể một chain có `securityMatcher("/internal/**")` và chain còn lại cho các URL khác; dùng `@Order` đúng, test endpoint cả trong và ngoài chain. `anyRequest().denyAll()` trong một chain không bảo vệ path mà chain đó không match.

### 9.7. CSRF và xác thực

Bài này dùng HTTP Basic và GET, không tắt CSRF. Khi thêm các HTTP method thay đổi state, kiểm tra `CsrfFilter`, CORS, cookie/session và nguồn credential. Với ứng dụng dùng bearer token thuần túy không dựa vào cookie, thiết kế CSRF có thể khác. Đừng thêm `csrf.disable()` chỉ để một test POST chạy xanh mà chưa hiểu mô hình đe dọa.

## 10. Những lỗi thường gặp khi đăng ký manager qua access

| Dấu hiệu | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Manager không bao giờ được gọi | Rule rộng `permitAll` đứng trước hoặc request không khớp chain | Kiểm tra thứ tự `requestMatchers` và `securityMatcher`; thêm test route thật |
| `getVariables().get("documentId")` là null | Matcher không capture biến, tên placeholder khác hoặc dùng `anyRequest()` | Khớp tên và kiểu matcher; mặc định từ chối khi thiếu biến |
| Mọi ID đều bị cho phép | Chỉ kiểm tra authority, không xác minh owner từ server | Đối chiếu ID → tài nguyên → owner/tenant thực |
| 500 khi URL có ID không phải số | `Long.parseLong` không được xử lý | Trả deny tường minh hoặc định nghĩa matcher phù hợp |
| 403 khi mong 401 hoặc ngược lại | Cấu hình authentication entry point, anonymous, filter chain khác | Chạy MockMvc không/đã đăng nhập, kiểm tra entry point |
| Thêm endpoint mới mặc nhiên mở quyền | Quy tắc `anyRequest().permitAll()` hoặc `/api/**` quá rộng | Dùng deny-by-default cho chain kiểm soát chặt |
| Spring Security 7 báo lỗi khi override `check` | API đã chuyển sang `authorize` | Chuyển chữ ký class custom hoặc dùng lambda có target type |
| Bean manager mơ hồ khi inject | Có nhiều `AuthorizationManager<RequestAuthorizationContext>` | Đặt tên rõ và dùng `@Qualifier` |
| Manager phụ thuộc controller state và không tìm được `@PathVariable` | Authorization chạy ở filter, trước MVC handler | Dùng `RequestAuthorizationContext.getVariables()` |
| Policy trả phép khi repository lỗi | Catch-all trả allow hoặc fallback rộng | Fail closed; phân biệt lỗi hạ tầng với quyết định quyền |
| Rule HTTP tốt nhưng job gọi service vẫn đọc được trái quyền | Job không đi qua web filter chain | Bảo vệ service/domain/data layer tương ứng |
| Test unit policy xanh nhưng URL vẫn mở | Sai registration trong `SecurityFilterChain` | Thêm MockMvc test xuyên toàn bộ filter chain |
| Request qua chain khác không chạy policy | Nhiều chain và `securityMatcher` chồng lấn/sai thứ tự | Kiểm tra chain selection và integration test các path |
| Dùng sai context trong lambda | Mang `MethodInvocation`/`AuthorizationContext` reactive vào servlet | Dùng `RequestAuthorizationContext` cho `authorizeHttpRequests` |

## 11. Bài tập củng cố

**Bài 1 – Chứng minh thứ tự rule.** Tạm đặt `.requestMatchers("/api/**").permitAll()` phía trên rule tài liệu. Chạy test `otherOwnerIsForbidden` và quan sát nó không còn xác minh được chốt; sửa lại thứ tự, xác nhận test xanh. Trả lời vì sao manager đúng nhưng route vẫn mở.

**Bài 2 – Quyền sửa tách theo HTTP method.** Bổ sung `PUT /api/documents/{documentId}` có yêu cầu `DOC_EDIT` và owner, cùng manager riêng hoặc policy method `canEdit`. Đảm bảo `GET` không vô tình cấp quyền `PUT`. Viết test người có `DOC_READ` nhưng thiếu `DOC_EDIT` không sửa được.

**Bài 3 – Nhiều tenant.** Thêm tenant ID vào `Document` và principal đáng tin cậy. Viết test `alice` tenant A không thể đọc tài liệu tenant B kể cả khi trùng username. Đừng nhận tenant chỉ từ query parameter chưa xác minh.

**Bài 4 – Thiếu path variable.** Đăng ký một manager dựa vào `documentId` cho `anyRequest()` trong môi trường thử nghiệm; kiểm tra `getVariables()` có gì và cách policy trả `false`. Thiết kế lại matcher cho đúng tập request.

**Bài 5 – Hồi quy khi nâng cấp.** Chạy toàn bộ test trên bản Spring Security đang khóa, kiểm tra `AuthorizationManager` dùng `check` hay `authorize` khi viết class implementation, và đảm bảo code dùng `.access(manager)` thực thi đúng chốt sau khi nâng cấp.

**Tiêu chí hoàn thành:** tự khai báo một bean `AuthorizationManager<RequestAuthorizationContext>`, gắn vào `requestMatchers(...).access(manager)`, hiểu first-match rule, đọc đúng path variables, trả quyết định deny-by-default, phân biệt HTTP 401/403, và viết test cả đường cho phép lẫn bị chặn qua `MockMvc`.

## Tài liệu tham khảo

- Spring Security 6.5 – **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 7.0 – **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html
- Spring Security – **Authorization Architecture**, `AuthorizationManager` và `AuthorizationDecision`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security 6.5 API – **AuthorizationManager**: https://docs.spring.io/spring-security/site/docs/6.5.4/api/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 7.0 API – **AuthorizationManager**: https://docs.spring.io/spring-security/site/docs/7.0.0/api/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security API – **RequestAuthorizationContext**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html
