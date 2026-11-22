# Bảo vệ HTTP theo READ, WRITE, ADMIN và kiểm thử từng phương thức

## 1. Mục tiêu của bài thực hành

Khi triển khai API với Spring Boot và Spring Security, yêu cầu “người dùng được đọc, người dùng khác được ghi, quản trị viên được quản lý” không thể giải quyết chỉ bằng `authenticated()`. Cần xác định rõ **phương thức HTTP**, **đường dẫn tài nguyên**, **authority của người gọi** và **quyền trên đối tượng cụ thể**. Sau đó kiểm thử cả các yêu cầu được phép và bị từ chối.

Bài thực hành sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x**, `SecurityFilterChain`, `authorizeHttpRequests` và `MockMvc`. Chính sách minh họa:

- `READ`: được đọc tài liệu bằng `GET`/`HEAD`; không được tạo, sửa, xóa hay vào khu vực quản trị.
- `WRITE`: được đọc **và** tạo/sửa/xóa tài liệu, nhưng không được vào khu vực quản trị.
- `ADMIN`: được đọc/ghi tài liệu và xem API quản trị.
- Không có authority phù hợp: bị từ chối; request chưa xác thực nhận challenge theo cơ chế authentication được cấu hình.
- Đường dẫn hoặc phương thức không được liệt kê: **deny by default**.

Ở đây `READ`, `WRITE`, `ADMIN` là **chuỗi `GrantedAuthority` thực**, không tự thêm tiền tố `ROLE_`. Chúng ta chủ động quy định rằng WRITE và ADMIN cũng được READ bằng `hasAnyAuthority`, chứ Spring Security không tự suy ra thứ bậc này. Trong hệ thống thật, quyền đọc, ghi và admin thường có tên chi tiết hơn như `DOCUMENT_READ`, `DOCUMENT_WRITE`, `TENANT_ADMIN`.

**Giới hạn phạm vi:** ví dụ tập trung bảo vệ ở tầng HTTP. Một request được WRITE chưa chắc được sửa **bất kỳ** tài liệu nào: quyền theo owner, tenant, ACL, trạng thái và nghiệp vụ vẫn phải kiểm tra ở service/repository. HTTP authorization là lớp đầu, không phải toàn bộ chính sách.

## 2. Thiết kế ma trận quyền trước khi viết mã

Đặt API giả định như sau:

| HTTP method | Đường dẫn | Hành động | Authority được phép | Kết quả thành công |
| --- | --- | --- | --- | --- |
| `GET` | `/api/documents/{id}` | Đọc nội dung | READ, WRITE, ADMIN | 200 |
| `HEAD` | `/api/documents/{id}` | Đọc metadata HTTP, không trả body | READ, WRITE, ADMIN | 200 |
| `POST` | `/api/documents` | Tạo tài liệu | WRITE, ADMIN | 201 |
| `PUT` | `/api/documents/{id}` | Thay thế nội dung | WRITE, ADMIN | 200 |
| `PATCH` | `/api/documents/{id}` | Sửa một phần | WRITE, ADMIN | 200 |
| `DELETE` | `/api/documents/{id}` | Xóa tài liệu | WRITE, ADMIN | 204 |
| `GET` | `/api/admin/reports` | Đọc báo cáo quản trị | ADMIN | 200 |
| Khác | Bất kỳ đường dẫn/method không có chính sách | Không hỗ trợ hoặc không được phép | Không ai theo cấu hình minh họa | Từ chối |

Một số chi tiết cần hiểu trước:

1. **HTTP method có ngữ nghĩa.** GET và HEAD được thiết kế an toàn (không tạo side effect nghiệp vụ); PUT thường idempotent, PATCH tùy ngữ nghĩa; DELETE thường idempotent về trạng thái tài nguyên. Tính idempotent không nói lên quyền. Không thực hiện thay đổi dữ liệu trong GET/HEAD.
2. **HEAD là phương thức riêng ở tầng HTTP.** Spring MVC có thể phục vụ HEAD thông qua `@GetMapping`, nhưng request matcher có `HttpMethod.GET` không nên được coi là tự bao phủ HEAD. Chúng ta liệt kê HEAD tường minh.
3. **OPTIONS thường dùng cho CORS preflight.** Preflight không phải lệnh ghi; CORS quyết định trình duyệt có thể gửi cross-origin request, không thay thế authorization của request thực. Cần cấu hình `http.cors(...)` và nguồn gốc/phương thức/header được phép nếu frontend ở origin khác. Không mở mọi OPTIONS hoặc mọi endpoint để “sửa lỗi CORS”.
4. **TRACE/CONNECT và method không dự kiến** không được tự động cấp quyền; ví dụ kết thúc bằng `anyRequest().denyAll()`. Trong cấu hình thực, hãy xử lý endpoint health, error, static assets và preflight có chủ đích, không để một wildcard permissive nuốt mất chúng.
5. **Ưu tiên rule cụ thể trước rule rộng.** Spring Security đánh giá các quy tắc `requestMatchers` trong thứ tự khai báo và áp dụng quy tắc đầu tiên khớp. Nếu đặt `requestMatchers("/api/**").authenticated()` trước các rule WRITE/ADMIN, một user chỉ đăng nhập có thể được đi qua lớp HTTP cho các endpoint đáng lẽ cần WRITE.

Ví dụ rule **sai thứ tự**:

```java
// Không sử dụng: rule rộng ăn mất các rule chi tiết sau.
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
        .hasAuthority("WRITE")
    .anyRequest().denyAll()
)
```

Rule `DELETE` ở dưới không còn cơ hội quyết định cho URL đã khớp `/api/**`. Cần khai báo phạm vi cụ thể, test request thật và giữ default deny.

## 3. Cấu trúc dự án Spring Boot

Các file dưới đây tạo một ví dụ **có thể chạy trong dự án Maven Spring Boot 3.x với JDK 17+**. Chọn một bản Spring Boot 3.x còn được hỗ trợ/vá lỗi trong tổ chức; đoạn phụ thuộc dưới đây giả định project đã có Spring Boot parent/BOM, tránh ghim version không phù hợp với vòng đời ứng dụng.

Các dependency Maven trong `pom.xml`:

```xml
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
```

Ứng dụng dùng package `com.example.httpauth`, gồm các file:

```text
src/main/java/com/example/httpauth/
  HttpAuthorizationApplication.java
  SecurityConfig.java
  DocumentController.java
  AdminController.java
src/test/java/com/example/httpauth/
  HttpAuthorizationIntegrationTest.java
```

Đây là một **API demo không lưu cơ sở dữ liệu** để tập trung vào phép kiểm tra HTTP. Các endpoint trả chuỗi cố định; khi đưa vào sản phẩm, controller phải gọi service có quyền theo tài nguyên, validation, transaction và persistence đúng yêu cầu.

### 3.1. Lớp khởi động

`HttpAuthorizationApplication.java`:

```java
package com.example.httpauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpAuthorizationApplication.class, args);
    }
}
```

Spring Boot sẽ quét các bean trong package này. `SecurityConfig` và controllers nằm cùng package để được phát hiện tự động.

### 3.2. SecurityFilterChain: kiểm soát theo method và authority

`SecurityConfig.java`:

```java
package com.example.httpauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .hasAnyAuthority("READ", "WRITE", "ADMIN")
                .requestMatchers(HttpMethod.HEAD, "/api/documents/*")
                    .hasAnyAuthority("READ", "WRITE", "ADMIN")

                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAnyAuthority("WRITE", "ADMIN")
                .requestMatchers(HttpMethod.PUT, "/api/documents/*")
                    .hasAnyAuthority("WRITE", "ADMIN")
                .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                    .hasAnyAuthority("WRITE", "ADMIN")
                .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
                    .hasAnyAuthority("WRITE", "ADMIN")

                .requestMatchers("/api/admin/**")
                    .hasAuthority("ADMIN")

                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Điểm cần chú ý:

- `authorizeHttpRequests` định nghĩa authorization dựa trên request. Với Spring Security 6, API này dùng cơ chế hiện đại dựa trên `AuthorizationManager`.
- `requestMatchers(HttpMethod, path)` yêu cầu **đồng thời khớp method và đường dẫn**. Mẫu `/api/documents/*` ở đây áp dụng cho tài nguyên ở một segment sau `documents/`; subresource như `/api/documents/1/comments` không được tự cấp quyền. Phải khai báo route và chính sách mới nếu phát triển tính năng đó.
- `hasAnyAuthority("READ", "WRITE", "ADMIN")` là logic OR: chỉ cần có **ít nhất một** authority trong tập. Không tự suy luận quan hệ kế thừa role.
- `/api/admin/**` có quy tắc tách biệt; người có WRITE nhưng không có ADMIN vẫn không được xem báo cáo quản trị. Không đặt `authenticated()` rộng trước nó.
- `anyRequest().denyAll()` đảm bảo route chưa phân loại không được truy cập qua lớp authorization. Một route không tồn tại có thể được trả 403 (nếu bị filter từ chối trước khi đến MVC) thay vì 404; thiết kế hợp đồng lỗi rõ ràng theo sản phẩm.
- `httpBasic(...)` minh họa cơ chế xác thực dễ dùng trong test/lab. `formLogin` bị tắt. Đối với production có JWT/OAuth2, dùng resource-server configuration tương ứng; **chính sách authorization vẫn cần được giữ**.
- Chúng ta **không tắt CSRF**. Với HTTP Basic/cookie/session mà trình duyệt có thể tự gửi credential, CSRF cần được xem xét nghiêm túc. Mặc định Spring Security kiểm tra token với các request thay đổi trạng thái như POST/PUT/PATCH/DELETE. Trong test, dùng `.with(csrf())` để kiểm tra đúng rule quyền thay vì bị CSRF chặn trước. Với API dùng Bearer token thuần không được trình duyệt tự gửi và không dùng cookie auth, có thể cân nhắc chính sách CSRF khác sau khi phân tích threat model — không sao chép `csrf.disable()` theo thói quen.

Để có tài khoản cho HTTP Basic khi chạy ứng dụng thật, cần một `UserDetailsService`/IdP cấu hình đúng và phân quyền đáng tin. Các test ở phần sau dùng Spring Security test tạo principal trong request nên **không** là test của password/JWT authentication thực tế.

### 3.3. Controller cho đủ các phương thức HTTP

`DocumentController.java`:

```java
package com.example.httpauth;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    @GetMapping("/{id}")
    public String read(@PathVariable String id) {
        return "read:" + id;
    }

    // Spring MVC có hỗ trợ HEAD cho mapping GET.
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public String create() {
        return "created";
    }

    @PutMapping("/{id}")
    public String replace(@PathVariable String id) {
        return "replaced:" + id;
    }

    @PatchMapping("/{id}")
    public String edit(@PathVariable String id) {
        return "patched:" + id;
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        // Demo không lưu dữ liệu.
    }
}
```

`AdminController.java`:

```java
package com.example.httpauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    @GetMapping("/reports")
    public String reports() {
        return "admin-report";
    }
}
```

API ví dụ **không có** endpoint cho `OPTIONS`, `TRACE` hay một đường subresource khác. Chúng cũng không được `permitAll`. Khi thêm CORS preflight cho ứng dụng frontend, cấu hình CORS phải chọn origin, method và header cụ thể; một preflight được xử lý thành công không phải là quyền thực hiện GET/WRITE sau đó.

### 3.4. Vì sao không chỉ viết @PreAuthorize cho controller?

Với HTTP layer, `SecurityFilterChain` cho thấy rõ **quy tắc theo HTTP verb**. `@PreAuthorize` hữu ích ở service/controller method để kiểm tra logic sâu hơn, ví dụ:

```java
@PreAuthorize("@documentPolicy.canEdit(authentication, #tenantId, #id)")
public void editDocument(UUID tenantId, UUID id, EditRequest request) {
    // Service thực hiện cập nhật có điều kiện owner/tenant/version.
}
```

Đoạn trên chỉ là **mảnh ví dụ**, yêu cầu bean `documentPolicy`, DTO và service được định nghĩa riêng. Nó không thay thế mapping GET/POST/PUT/PATCH/DELETE hay ràng buộc database. Trong hệ thống multi-tenant, `documentPolicy` phải xác minh tenant/resource/owner/ACL hiện hành ở server. Không dùng ownerId, role, tenantId do client tự khai làm bằng chứng quyền.

## 4. Kiểm thử tích hợp từng HTTP method bằng MockMvc

Một bài kiểm thử có ích phải đi qua **Spring Security filter chain**; không chỉ gọi trực tiếp controller bằng `new DocumentController()`, cũng không mock `SecurityFilterChain`. Chúng ta dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để nạp cấu hình thật, nhưng thay principal bằng Spring Security Test.

Trong source set test cần có dependency `spring-security-test`, đặc biệt cho `user(...)` và `csrf()`.

`HttpAuthorizationIntegrationTest.java`:

```java
package com.example.httpauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    private void expect(HttpMethod method, String path,
                        String authority, int httpStatus) throws Exception {
        MockHttpServletRequestBuilder builder = request(method, path)
                .with(user("test-user")
                    .authorities(new SimpleGrantedAuthority(authority)));

        if (method == HttpMethod.POST
                || method == HttpMethod.PUT
                || method == HttpMethod.PATCH
                || method == HttpMethod.DELETE) {
            builder.with(csrf());
        }

        mvc.perform(builder).andExpect(status().is(httpStatus));
    }

    @Test
    void readAndHeadMatrix() throws Exception {
        expect(HttpMethod.GET, "/api/documents/d1", "READ", 200);
        expect(HttpMethod.GET, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.GET, "/api/documents/d1", "ADMIN", 200);
        expect(HttpMethod.GET, "/api/documents/d1", "NONE", 403);

        expect(HttpMethod.HEAD, "/api/documents/d1", "READ", 200);
        expect(HttpMethod.HEAD, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.HEAD, "/api/documents/d1", "NONE", 403);
    }

    @Test
    void postMatrix() throws Exception {
        expect(HttpMethod.POST, "/api/documents", "WRITE", 201);
        expect(HttpMethod.POST, "/api/documents", "ADMIN", 201);
        expect(HttpMethod.POST, "/api/documents", "READ", 403);
    }

    @Test
    void putMatrix() throws Exception {
        expect(HttpMethod.PUT, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.PUT, "/api/documents/d1", "ADMIN", 200);
        expect(HttpMethod.PUT, "/api/documents/d1", "READ", 403);
    }

    @Test
    void patchMatrix() throws Exception {
        expect(HttpMethod.PATCH, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.PATCH, "/api/documents/d1", "ADMIN", 200);
        expect(HttpMethod.PATCH, "/api/documents/d1", "READ", 403);
    }

    @Test
    void deleteMatrix() throws Exception {
        expect(HttpMethod.DELETE, "/api/documents/d1", "WRITE", 204);
        expect(HttpMethod.DELETE, "/api/documents/d1", "ADMIN", 204);
        expect(HttpMethod.DELETE, "/api/documents/d1", "READ", 403);
    }

    @Test
    void adminIsSeparateFromWrite() throws Exception {
        expect(HttpMethod.GET, "/api/admin/reports", "ADMIN", 200);
        expect(HttpMethod.GET, "/api/admin/reports", "WRITE", 403);
        expect(HttpMethod.GET, "/api/admin/reports", "READ", 403);
    }

    @Test
    void unmatchedRouteIsDeniedEvenToAdmin() throws Exception {
        expect(HttpMethod.GET, "/api/documents/d1/comments", "ADMIN", 403);
    }

    @Test
    void unauthenticatedReadGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/documents/d1"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfFailsEvenForAuthorizedWriter() throws Exception {
        mvc.perform(post("/api/documents")
                .with(user("writer").authorities(
                        new SimpleGrantedAuthority("WRITE"))))
           .andExpect(status().isForbidden());
    }
}
```

**Giải thích test:**

- Phương thức helper tạo request theo `HttpMethod` và **một authority có thật trong SecurityContext thử nghiệm**. Dùng `SimpleGrantedAuthority("READ")` khác với `roles("READ")`, vì `roles` mặc định thêm `ROLE_`.
- `GET`/`HEAD` không cần CSRF token; `POST`/`PUT`/`PATCH`/`DELETE` được thêm `.with(csrf())`. Khi `POST` bị 403 với READ, bài test đang kiểm tra **thiếu quyền WRITE**, không phải vô tình thiếu CSRF.
- `status().is(201)`, `is(204)` hoặc `is(403)` là assert của MockMvc. `@SpringBootTest` không bắt buộc khởi động HTTP server ngoài, nhưng filter chain và MVC vẫn tham gia.
- Test anonymous GET kỳ vọng 401 do `httpBasic()` đã bật; đừng áp dụng 401 cứng nhắc cho mọi mô hình authentication, đặc biệt form login hoặc custom entry point.
- Kiểm thử thiếu CSRF với user có WRITE minh họa **authorization thành công không tự bỏ qua bảo vệ request giả mạo**.
- Test unmatched route chứng minh rule mặc định không “lộ” endpoint chưa khai báo. Với cấu hình khác, việc áp dụng error dispatch hoặc 404 có thể cần điều chỉnh theo hợp đồng API.

Chạy bằng Maven wrapper trong dự án đã có các tệp phía trên:

```bash
./mvnw test -Dtest=HttpAuthorizationIntegrationTest
```

Hoặc nếu Maven được cài đặt sẵn:

```bash
mvn test -Dtest=HttpAuthorizationIntegrationTest
```

Trên Windows dùng `mvnw.cmd` tương ứng. **Kết quả mong đợi:** 9 phương thức test được thực thi và đều pass trong môi trường Spring Boot 3.x/Security 6.x với dependency tương thích. Maven/JUnit in log phụ thuộc phiên bản, nên không coi một đoạn stdout giả định là output cố định; chỉ yêu cầu mọi assert thành công. Các phép thử trong một method có nhiều HTTP request, vì thế **số request test lớn hơn số phương thức test**.

**Bẫy cần tránh:** gọi `@WithMockUser` hoặc `user(...)` sẽ dựng principal thử nghiệm; nó **không** kiểm tra HTTP Basic password, token signature, issuer, audience, authority converter hoặc cấu hình IdP thật. Cần test authentication riêng khi chuyển production.

### 4.1. Khi test 403 mà thực ra chỉ bị CSRF chặn

Một lỗi test rất phổ biến:

```java
// Test này không chứng minh role READ bị từ chối bởi rule WRITE:
mvc.perform(post("/api/documents")
        .with(user("reader").authorities(
                new SimpleGrantedAuthority("READ"))))
   .andExpect(status().isForbidden());
```

Request thiếu CSRF nên có thể bị chặn trước khi tới rule authorization. Dù cấu hình lỡ viết `.permitAll()` cho POST, test trên vẫn có thể xanh. Muốn kiểm tra policy, cần `.with(csrf())` và assert 403; sau đó tạo test độc lập xác nhận CSRF bảo vệ write endpoint theo threat model.

Tương tự, một test GET bằng anonymous trả 401 không chứng minh rule GET yêu cầu READ: chỉ một rule `authenticated()` rộng cũng khiến anonymous bị chặn. Phải kiểm thử **người đã xác thực nhưng thiếu quyền**.

### 4.2. Kiểm tra cả nội dung khi cần

Ví dụ controller demo trả `"read:d1"` cho GET; có thể bổ sung:

```java
mvc.perform(get("/api/documents/d1")
        .with(user("reader").authorities(
                new SimpleGrantedAuthority("READ"))))
   .andExpect(status().isOk())
   .andExpect(content().string("read:d1"));
```

Đoạn trên cần static import `org.springframework.test.web.servlet.result.MockMvcResultMatchers.content` trong lớp test. Với dữ liệu thật, ngoài status còn cần assert **không lộ dữ liệu của owner/tenant khác**, body đã filter đúng scope, mọi trường nhạy cảm không có trong response.

## 5. Bổ sung kiểm thử deny-by-default, HEAD và OPTIONS

### 5.1. HEAD không phải GET khi xét method matcher

Trong HTTP, HEAD tương đương GET về metadata nhưng không gửi response body. Nhiều server/MVC có thể map HEAD đến handler GET, nhưng Security matcher vẫn nhìn thấy phương thức HEAD. Nếu chỉ khai báo:

```java
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("READ")
.anyRequest().denyAll()
```

thì HEAD không có rule cho phép theo ví dụ này. Có thể chọn **cho phép HEAD với cùng quyền READ** bằng một matcher riêng, hoặc cố ý chặn HEAD và test hành vi đó. Đừng coi HEAD an toàn để cho anonymous đọc metadata tài nguyên riêng tư: headers như `Content-Length`, `ETag`, thời gian xử lý có thể tiết lộ thông tin.

### 5.2. OPTIONS và CORS preflight

Với browser cross-origin, preflight OPTIONS có thể gửi:

```http
OPTIONS /api/documents/d1 HTTP/1.1
Origin: https://frontend.example
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,authorization
```

CORS preflight thường không mang credentials theo cách request thực mang. Nếu application dùng cross-origin frontend, nên cấu hình Spring CORS cho origin/method/header cho phép và tích hợp với Spring Security, ví dụ một `CorsConfigurationSource` được cung cấp hợp lệ kết hợp `http.cors(Customizer.withDefaults())`. **Không** sửa lỗi 401 của preflight bằng cách mở `/api/**` cho mọi phương thức.

Preflight được chấp nhận chỉ nói rằng origin có thể thử thực hiện PATCH; request PATCH thật vẫn phải qua authentication, CSRF (nếu áp dụng), `WRITE` authorization và policy theo tài nguyên. Với CORS origin cụ thể, không tùy tiện dùng wildcard cùng credential.

API mẫu không kích hoạt CORS riêng; đó là quyết định phạm vi của demo, không phải lỗi thiếu quyền. Nếu sản phẩm có frontend trên origin khác, thêm cấu hình CORS và test OPTIONS preflight lẫn request thật. Khi xử lý OPTIONS, nên kiểm thử cả origin hợp lệ và origin không hợp lệ, các method/header không cho phép và header CORS phản hồi.

### 5.3. Method override và routing phụ

Một số framework/proxy hỗ trợ HTTP method override bằng header/form parameter. Khi đó method nhìn thấy ở tầng Security và MVC có thể khác tùy thứ tự filter. Chỉ bật cơ chế override khi thật sự cần, cấu hình nhất quán và có test rằng người dùng READ không thể dùng POST + override để thực hiện DELETE.

Nếu có các route như `/api/documents/{id}/download`, `/api/documents/{id}/share`, `/api/documents/{id}/attachments`, `/api/admin/users/{id}/roles`, hãy phân loại từng **action** thay vì dùng wildcard rộng cho toàn bộ API. Đặc biệt download/export có thể cần permission riêng, không nhất thiết ngang READ metadata.

## 6. Phân biệt HTTP authorization với object-level authorization

Một người có `WRITE` có thể thao tác loại chức năng “sửa tài liệu” nhưng **không mặc nhiên sở hữu mọi tài liệu**. Đề xuất chia chính sách thành các lớp:

1. **Authentication:** người gọi đã được xác thực; authority được ánh xạ từ nguồn tin cậy.
2. **HTTP authorization:** method và URL có nằm trong tập hành động READ/WRITE/ADMIN của actor hay không?
3. **Resource/tenant authorization:** tài liệu có thuộc tenant được chọn, actor có owner/ACL/membership và quyền thao tác thật sự không?
4. **Workflow authorization:** trạng thái hiện tại có cho phép hành động? Ví dụ tài liệu LOCKED có thể không còn cho EDIT dù actor có WRITE.
5. **Data write guard:** ngay trước ghi, phải chống race nếu owner/tenant/status/role thay đổi giữa lúc kiểm tra và cập nhật.
6. **Response/side-effect filtering:** không xuất dữ liệu chéo tenant, không phát event thành công khi transaction thất bại hoặc bị từ chối.

Một pattern ở repository khi cập nhật có thể như sau (mảnh minh họa Spring Data JPA, cần entity và repository tương ứng):

```java
@Modifying
@Query("""
    update Document d
       set d.title = :title,
           d.version = d.version + 1
     where d.id = :documentId
       and d.tenantId = :tenantId
       and d.ownerId = :actorId
       and d.status = :expectedStatus
       and d.version = :expectedVersion
""")
int updateOwnedDocument(
        UUID documentId,
        UUID tenantId,
        String actorId,
        String title,
        DocumentStatus expectedStatus,
        long expectedVersion);
```

Actor ID phải lấy từ principal đã xác thực trong backend; `tenantId` là selector đã kiểm tra membership và phải khớp bản ghi; `ownerId`/`status` hiện hành được kiểm tra trong database; `expectedVersion` giúp tránh ghi đè thay đổi đồng thời. Mã minh họa không định nghĩa toàn bộ transaction/policy. Với quan hệ membership có thể đổi ngay trong request, cần cơ chế nhất quán riêng nếu quy tắc yêu cầu revoke tức thời.

**Bài test HTTP READ/WRITE/ADMIN chỉ chứng minh tầng 2.** Phải có integration tests với DB thật cho tầng 3–6, gồm tài liệu của Bob, tenant khác, owner chuyển giữa request, status thay đổi, stale version và audit/side effect.

## 7. Test matrix mở rộng khi đưa vào sản phẩm

| Nhóm | Tình huống | Điều cần khẳng định |
| --- | --- | --- |
| Xác thực | Anonymous GET tài liệu | 401/challenge theo cấu hình |
| READ | READ gửi GET tài liệu | Thành công 200 khi resource policy cho phép |
| READ | READ gửi HEAD tài liệu | Thành công 200, không trả body |
| READ | User đã đăng nhập nhưng authority NONE gửi GET | 403, không trả dữ liệu |
| WRITE | READ gửi POST có CSRF | 403 do không đủ WRITE, không tạo dữ liệu |
| WRITE | READ gửi PUT có CSRF | 403, không thay dữ liệu |
| WRITE | READ gửi PATCH có CSRF | 403, không thay dữ liệu |
| WRITE | READ gửi DELETE có CSRF | 403, không xóa dữ liệu |
| WRITE | WRITE gửi POST/PUT/PATCH/DELETE hợp lệ | Từng method thành công theo contract |
| ADMIN | WRITE gửi GET /api/admin/reports | 403 dù WRITE đọc/sửa tài liệu được |
| ADMIN | ADMIN gửi GET /api/admin/reports | 200 |
| Default deny | ADMIN gọi GET /api/documents/d1/comments chưa khai báo | Từ chối thay vì mở wildcard |
| CSRF | WRITE gửi POST thiếu/CSRF token sai | 403 khi CSRF bảo vệ endpoint |
| Role prefix | Principal có ROLE_READ nhưng policy kiểm READ | Không mặc nhiên pass nếu chưa ánh xạ đúng |
| Tenant | WRITE của tenant A cập nhật tài liệu tenant B | HTTP có thể pass, resource policy/DB phải từ chối |
| Owner | WRITE cố sửa tài liệu của user khác | Không ghi dữ liệu |
| Status | WRITE cố sửa tài liệu LOCKED | Bị từ chối theo workflow |
| Concurrency | Owner đổi giữa precheck và ghi | Không ghi trái phép |
| CORS | OPTIONS preflight từ origin được phép/bị chặn | Chính sách CORS và actual request độc lập |
| Method override | READ tìm cách gọi DELETE qua override | Không có bypass |
| Cache | READ decision của Alice được cache, Bob gọi cùng ID | Không dùng lại ALLOW của Alice |

Đối với endpoint thực sự thay đổi DB, assert không chỉ HTTP status mà cả **số bản ghi bị cập nhật, nội dung trước/sau, owner/tenant/status, audit và outbox event**. Nếu test chỉ kiểm tra 403 do thiếu CSRF hoặc anonymous, một lỗi route matcher có thể vẫn bị bỏ sót.

Nên có test tích hợp chạy với đúng cấu hình production-like, sau đó các test đơn vị riêng cho policy service. Cũng phải kiểm tra:
- URL encoding, trailing slash, context path, path matching và route mới có làm đổi phạm vi matcher không.
- Thứ tự nhiều `SecurityFilterChain` nếu ứng dụng có hơn một chain. Một request được gắn vào chain đầu tiên có `securityMatcher` phù hợp; chain khác có thể có rule khác. Test request thực tế chứ không chỉ đọc mỗi cấu hình.
- Mặc định method security `@PreAuthorize` chỉ có hiệu lực khi được bật và lời gọi đi qua Spring proxy, nên không dựa duy nhất vào `this.securedMethod()` từ cùng bean.
- Việc authentication/authority mapping có bị sai do JWT converter, role prefix, cache quyền lỗi thời hoặc impersonation không.

## 8. Lỗi phổ biến và cách phát hiện

**Lỗi 1 — Dùng `authenticated()` thay cho policy READ/WRITE/ADMIN.** Mọi user đã đăng nhập có thể sửa/xóa nếu rule quá rộng. Khắc phục: xác định và test authority cho từng method.

**Lỗi 2 — Chỉ bảo vệ GET, quên HEAD.** HEAD có thể được Spring MVC phục vụ từ GET handler nhưng Security matcher theo method là một điều kiện khác. Khắc phục: rule và test HEAD riêng.

**Lỗi 3 — Dùng `hasRole("WRITE")` trong khi principal chỉ có authority `WRITE`.** `hasRole` thường kiểm `ROLE_WRITE`, còn `hasAuthority("WRITE")` kiểm đúng chuỗi `WRITE`. Khắc phục: thống nhất tên quyền và converter; không trộn hai quy ước tùy tiện.

**Lỗi 4 — Test write thiếu `csrf()`.** Bài test 403 xanh dù cấu hình thực ra cho phép READ thao tác WRITE. Khắc phục: test quyền có token CSRF hợp lệ, test CSRF riêng.

**Lỗi 5 — Wildcard hoặc rule rộng đứng trước rule cụ thể.** `/api/**` với authenticated/permitAll có thể làm rule phía sau vô hiệu. Khắc phục: kiểm tra thứ tự và default deny; test người đã xác thực nhưng thiếu authority.

**Lỗi 6 — ADMIN tự động được mọi quyền vì tên “admin”.** Nếu chỉ cấu hình `hasAuthority("WRITE")`, user chỉ có `ADMIN` sẽ không pass. Khắc phục: định nghĩa phân cấp có chủ đích (`hasAnyAuthority`, role hierarchy hoặc gán authority thực). Ví dụ hiện tại cho ADMIN read/write một cách **tường minh**.

**Lỗi 7 — Dựa vào frontend ẩn nút Delete.** HTTP request có thể gửi trực tiếp; client không kiểm soát được chính sách server. Khắc phục: authorize trong filter/service và test API thật.

**Lỗi 8 — Coi HTTP WRITE là sở hữu mọi document.** Cross-tenant/IDOR xảy ra khi chỉ kiểm tra role. Khắc phục: policy theo resource ở service và condition/transaction bảo vệ DB.

**Lỗi 9 — Bỏ qua preflight CORS hoặc mở quá rộng để chữa CORS.** OPTIONS không phải quyền thực sự cho PATCH; CORS origin không thay cho authentication. Khắc phục: cấu hình CORS chính xác và giữ rule authorization trên request thật.

**Lỗi 10 — Chỉ test positive case.** Nếu ai cũng được truy cập vì `permitAll()`, test 200 vẫn pass. Khắc phục: một positive và ít nhất một negative cho **mỗi HTTP method** và route nhạy cảm.

## 9. Bài tập nâng cao

Bắt đầu với mã mẫu, rồi bổ sung ba bước kiểm chứng:

1. Thử bỏ rule `DELETE` trong cấu hình. Với `anyRequest().denyAll()`, test `deleteMatrix` phải thất bại ở case kỳ vọng WRITE/ADMIN được 204. Điều đó chứng minh endpoint chưa khai báo không mặc định mở.
2. Thử đổi rule POST thành `.authenticated()`. Test `postMatrix` với READ và token CSRF hợp lệ phải thất bại, vì READ sẽ được 201 thay vì 403. Đây là bằng chứng negative test bắt đúng lỗi cấu hình, không chỉ CSRF.
3. Thêm endpoint `GET /api/documents/{id}/history` và authority `HISTORY_READ` riêng. Trước khi thêm matcher, test phải bị chặn bởi default deny; sau khi thêm, HISTORY_READ mới được xem và READ/WRITE không tự được phép nếu yêu cầu bảo mật không cho.

Nâng cao hơn, kết hợp `MockMvc` với database thử nghiệm, hai tenant, các document khác owner và một policy `canEdit`. Dùng hai transaction/latch kiểm tra rằng chuyển owner hoặc revoke membership trước thời điểm ghi không bị bypass bởi HTTP authorization đã chạy ở đầu request.

## 10. Checklist hoàn thành bài

- [ ] Đã ghi rõ READ, WRITE, ADMIN là **authority**, hay ánh xạ đúng nếu ứng dụng dùng role với tiền tố `ROLE_`.
- [ ] Có bảng method × path × action × allowed authorities, kể cả HEAD và route ADMIN.
- [ ] Các rule cụ thể đứng trước rule rộng; kết thúc với `anyRequest().denyAll()`.
- [ ] Có positive và negative tests cho GET, HEAD, POST, PUT, PATCH, DELETE và ADMIN.
- [ ] Test POST/PUT/PATCH/DELETE có token CSRF khi đang kiểm tra authorization; CSRF có test riêng.
- [ ] Test anonymous khác với test authenticated-but-forbidden.
- [ ] Test thật qua Spring Security filter chain, không chỉ gọi controller thuần.
- [ ] Nếu có cross-origin, cấu hình CORS/preflight với origin/method/header thích hợp và test actual request.
- [ ] Resource/tenant/owner/status được kiểm ở service/DB khi làm nghiệp vụ thật.
- [ ] Thao tác ghi bảo vệ concurrency, không chỉ dựa vào ALLOW ở đầu request.
- [ ] Không quên các chain khác, URL pattern mới, method override, cache quyền và response cache.

**Kết luận:** Hãy thiết kế quyền theo **HTTP method + đường dẫn + authority** rồi dùng `SecurityFilterChain` để chặn request từ đầu. Kiểm thử phải bao phủ **được phép và bị từ chối ở từng phương thức**, đồng thời xác nhận CSRF không che lấp lỗi ủy quyền. Sau cùng, luôn tách rõ quyền loại hành động ở HTTP với quyền trên tài nguyên thật ở service và database.