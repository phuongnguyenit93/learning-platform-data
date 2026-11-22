# Phạm vi bảo vệ ứng dụng và những trách nhiệm vẫn thuộc về lập trình viên

> **Bối cảnh:** Spring Security là framework bảo mật cho ứng dụng Spring, tập trung vào **xác thực**, **phân quyền** và một số cơ chế giảm thiểu tấn công ở lớp HTTP. Sự hiện diện của dependency `spring-boot-starter-security` không đồng nghĩa ứng dụng đã an toàn trước mọi kiểu tấn công. Bài học tập trung vào ứng dụng web Spring MVC/Servlet; với WebFlux, nguyên tắc tương tự nhưng API và chuỗi xử lý khác.

## 1. Mục tiêu học tập

Sau bài này, bạn cần trả lời được:

1. Spring Security xử lý những câu hỏi nào tại ranh giới HTTP và tại phương thức?
2. Phần nào được framework cung cấp sẵn, phần nào **chỉ có hiệu lực khi cấu hình**, và phần nào luôn phải do nghiệp vụ hoặc hạ tầng đảm nhận?
3. Vì sao endpoint đã yêu cầu đăng nhập vẫn có thể rò rỉ tài liệu của người dùng khác?
4. Phải kiểm thử theo những lớp nào để không nhầm “đã bật Spring Security” với “đã bảo vệ ứng dụng”?

## 2. Security là nhiều lớp, không phải một bộ lọc duy nhất

Một request thực tế có thể đi qua luồng sau:

```text
Client / Browser
    |
    v
TLS, reverse proxy, WAF/rate limiter (hạ tầng, nếu được triển khai)
    |
    v
Servlet Filter Chain
    |
    v
Spring Security FilterChainProxy -> SecurityFilterChain phù hợp
    |  Authentication: ai đang gọi?
    |  CSRF/headers/session: các bảo vệ HTTP đã cấu hình
    |  Authorization: request này có được đi tiếp?
    v
Spring MVC Controller
    |
    v
Service -> kiểm tra quyền trên đối tượng/tenant, quy tắc nghiệp vụ
    |
    v
Repository / SQL / external API / file storage
    |
    v
Dữ liệu được lọc và trả về (output encoding, privacy, logging...)
```

Với Servlet, Spring Security tích hợp vào filter chain trước khi request đến controller; `SecurityFilterChain` xác định các filter bảo mật được áp dụng. `Authentication` mô tả principal và các `GrantedAuthority`; `SecurityContext` cung cấp bối cảnh bảo mật cho xử lý hiện tại. Bộ phận phân quyền có thể ra quyết định cho URL/method/HTTP method, nhưng **không tự biết** “đơn hàng 42 thuộc ai”, “khách hàng này có được xem tenant khác không” hoặc “trường dữ liệu này có được xuất ra không”.

Phân biệt bốn câu hỏi:

| Câu hỏi | Ví dụ | Nơi thường quyết định |
| --- | --- | --- |
| **Authentication**: Ai? | Token hợp lệ? Tài khoản nào? | Spring Security và hệ thống danh tính được cấu hình |
| **Authorization ở đường vào**: Có được gọi thao tác? | `/admin/**` yêu cầu `ADMIN` | `SecurityFilterChain`, method security |
| **Authorization ở dữ liệu/nghiệp vụ**: Có được thao tác **đối tượng này**? | Alice có quyền đọc hóa đơn số 42 không? | Service/repository với policy của ứng dụng |
| **An toàn toàn hệ thống**: Cách xử lý có an toàn? | SQL Injection, XSS, SSRF, lộ bí mật, DoS? | Lập trình viên, framework liên quan, vận hành/hạ tầng |

**Nguyên tắc cốt lõi:** “Đã xác thực” chỉ chứng minh danh tính theo cơ chế đang dùng; nó không tự cấp quyền đối với mọi tài nguyên.

## 3. Spring Security cung cấp những gì?

### 3.1. Xác thực và duy trì bối cảnh danh tính

- Có cơ chế tích hợp xác thực: form login, HTTP Basic, `AuthenticationProvider`/`AuthenticationManager`, xác thực bằng tài khoản/mật khẩu; có thể mở rộng với nhà cung cấp danh tính.
- Có hạ tầng `PasswordEncoder` cho lưu và kiểm tra **mật khẩu đã băm**, chẳng hạn BCrypt/Argon2 theo cấu hình thích hợp. Framework không tạo chính sách đặt lại mật khẩu, chống chiếm đoạt tài khoản hoặc kiểm soát vòng đời danh tính thay ứng dụng.
- Có hỗ trợ quản lý bối cảnh bảo mật, session và những biện pháp như chống session fixation trong cấu hình phù hợp. Ứng dụng phải chọn đúng chiến lược session/stateless, thời hạn, logout/revocation và cách lưu session.
- Có tích hợp OAuth2 Login/OIDC Client và OAuth2 Resource Server nếu đưa đúng dependency/cấu hình. Với JWT, **xác minh chữ ký, issuer, audience, scope, thời hạn** phải được cấu hình và kiểm chứng phù hợp; việc có `spring-security` không tự biến API thành Resource Server an toàn.

Điểm dễ nhầm: `SecurityContextHolder.getContext().getAuthentication()` có đối tượng `Authentication` không có nghĩa tất cả yêu cầu truy cập đều hợp lệ; trạng thái anonymous và cơ chế lưu `SecurityContext` phải được hiểu trong ngữ cảnh request hiện tại. Không tin username hoặc role được client tự gửi qua JSON/header tùy ý.

### 3.2. Phân quyền ở request và method

- `authorizeHttpRequests` có thể đặt quy tắc theo đường dẫn, HTTP method, authority/role, hoặc `AuthorizationManager` tùy chỉnh.
- `@EnableMethodSecurity` bật hỗ trợ kiểm soát phương thức; `@PreAuthorize`/`@PostAuthorize` chỉ có hiệu lực khi method security được bật và lời gọi đi qua proxy/điểm chặn phù hợp. **Method không được gắn policy không tự động được bảo vệ.**
- `hasRole("ADMIN")` thường so sánh authority `ROLE_ADMIN`; `hasAuthority("ADMIN")` so sánh đúng chuỗi `ADMIN`. Cần thống nhất quy ước cấp quyền.
- `requestMatchers(...)` chỉ kiểm tra những request khớp quy tắc; `securityMatcher(...)` lựa chọn filter chain nào áp dụng. Nếu tự tạo nhiều chain, phải bảo đảm không để lộ endpoint ngoài phạm vi các chain.
- Nên có quy tắc kết thúc rõ ràng, ví dụ `anyRequest().denyAll()` nếu chỉ muốn công khai một tập endpoint xác định, hoặc `authenticated()` khi mọi đường còn lại đều cần đăng nhập.

Phân quyền URL giúp chặn thao tác thô như “người thường gọi trang quản trị”. Nó **chưa đủ** cho BOLA/IDOR (Broken Object Level Authorization / Insecure Direct Object Reference): người dùng đăng nhập thay `/documents/1` thành `/documents/2` để lấy tài liệu người khác. Policy phải đối chiếu **principal + hành động + resource + tenant + trạng thái nghiệp vụ** với dữ liệu đáng tin cậy.

### 3.3. Cơ chế bảo vệ ở HTTP có điều kiện

- **CSRF:** Trong ứng dụng Servlet, cơ chế chống CSRF được bật theo cấu hình mặc định thông dụng; các request làm thay đổi trạng thái được kiểm tra token khi nằm trong phạm vi bảo vệ. Token phải thực sự được gửi từ form/client. Không tắt `csrf` chỉ vì API trả JSON: nếu trình duyệt tự đính kèm cookie/session hoặc Basic credentials, CSRF vẫn cần đánh giá.
- **Security headers:** Spring Security có thể viết những header bảo vệ phổ biến (như chống nhúng iframe, cache control, HSTS khi đủ điều kiện). **Content-Security-Policy không được framework tự suy ra và thêm sẵn**; tác giả ứng dụng phải thiết kế policy phù hợp. Header giảm một số rủi ro, không thay cho escaping/validation.
- **CORS:** Spring Security có thể tích hợp chính sách CORS với Spring MVC/`CorsConfigurationSource`. Origin được phép, credential, method, header là **quyết định của ứng dụng**. CORS là chính sách trình duyệt, không phải cơ chế xác thực hay cấp quyền, và không chống truy cập bằng curl/server-to-server.
- **Session/login/logout:** có các hook hỗ trợ, nhưng ứng dụng vẫn phải định nghĩa cách thu hồi token, khóa tài khoản, giới hạn đăng nhập, quản trị thiết bị và phản ứng sự cố theo yêu cầu riêng.
- **Test integration:** hỗ trợ mô phỏng người dùng, role, CSRF trong Spring Security Test; kiểm thử vẫn phải do nhóm phát triển viết dựa trên policy thực tế.

**Cẩn thận với mặc định:** Mặc định có thể thay đổi theo phiên bản, dependency, loại ứng dụng (Servlet/WebFlux) và việc bạn tự định nghĩa `SecurityFilterChain`. Cần đọc cấu hình đang chạy và kiểm chứng bằng integration test.

## 4. Trách nhiệm còn thuộc về lập trình viên và hạ tầng

| Rủi ro/trách nhiệm | Spring Security giúp gì? | Việc bắt buộc phải làm ngoài framework |
| --- | --- | --- |
| Người lạ vào API riêng | Authentication và rule HTTP/method | Chọn cơ chế đăng nhập, bảo vệ mọi entrypoint và thiết kế policy đúng |
| Người dùng xem dữ liệu người khác (IDOR/BOLA) | Cung cấp principal/authority, hook phân quyền | Kiểm tra owner, tenant, trạng thái và quyền trên **từng resource**; đưa policy vào service/query |
| Nâng quyền qua cập nhật trường | Chặn thao tác nếu rule khớp | Không cho client ghi `role`, `ownerId`, `tenantId` tùy ý; whitelist DTO và kiểm soát state transition |
| SQL/NoSQL injection | Không tự sửa query | Dùng parameter binding/ORM đúng cách; tránh nối chuỗi câu truy vấn |
| XSS/content injection | Hỗ trợ header, cho phép cấu hình CSP | Escape đầu ra **theo ngữ cảnh**, sanitize HTML được phép, tránh đưa dữ liệu thô vào DOM |
| CSRF | Hỗ trợ token/filter | Chọn chiến lược credential, client gửi token đúng; kiểm thử endpoint thay đổi dữ liệu |
| SSRF | Không tự kiểm duyệt mọi URL outbound | Kiểm tra đích gọi ra, hạn chế DNS/IP nội bộ, network egress, timeout và redirect |
| Upload/path traversal | Không tự xét file người dùng | Giới hạn kích thước/kiểu, kiểm tra nội dung, tạo tên lưu an toàn, cách ly file, kiểm soát quyền tải |
| Broken authentication/session | Có cơ chế auth/session | MFA khi cần, lockout/rate limit, reset flow, token revocation, cookie flags, HTTPS, rotation |
| Tiết lộ dữ liệu nhạy cảm | Không biết field nào là bí mật | Data minimization, DTO, masking, access review, mã hóa dữ liệu và backup |
| Giao tiếp an toàn | Một số header và tích hợp | TLS ở proxy/ingress, trust proxy headers, cấu hình HTTPS/HSTS phù hợp và bảo vệ internal traffic |
| Tấn công cạn tài nguyên | Không phải giải pháp DoS toàn diện | Rate limiting, quotas, giới hạn payload, timeout, queue, circuit breaker, capacity |
| Phụ thuộc dễ tổn thương | Không tự loại hết thư viện lỗi thời | Theo dõi CVE, update dependency/base image, kiểm tra SBOM và cấu hình |
| Giám sát/tuân thủ | Có event/hook xác thực, phân quyền | Audit đủ ngữ cảnh, tránh log mật khẩu/token/PII, phân quyền người đọc log, cảnh báo và ứng cứu |
| Multi-tenancy | Có thể truyền identity/claim | Ràng buộc tenant ở mọi query/cache/job/event, phân tách dữ liệu, chống truy cập tenant khác |

Một điểm dễ bị bỏ sót: request không đi qua HTTP (scheduled job, message consumer, batch, internal method call) có thể **không chịu** URL authorization. Đừng dựa riêng vào filter để bảo vệ logic chia sẻ giữa nhiều entrypoint. Ranh giới domain phải được thực thi ở nơi dùng dữ liệu.

## 5. Ví dụ end-to-end: khóa đường dẫn vẫn chưa bảo vệ tài liệu

Ví dụ nhỏ dưới đây dùng **Java 17+, Spring Boot 3.3.13/Spring Security 6.x** để tái hiện hành vi; phiên bản được cố định để có thể chạy lại bài học. Khi tạo dự án sản xuất mới, chọn nhánh Spring Boot đang được hỗ trợ và cập nhật bản vá. Sử dụng tài khoản in-memory và mật khẩu mẫu **chỉ dành cho môi trường học tập**.

### 5.1. Cấu trúc và dependencies

```text
security-scope-demo/
├── pom.xml
└── src/main/java/demo/security/SecurityScopeApplication.java
```

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-scope-demo</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

### 5.2. Mã Java hoàn chỉnh

```java
// src/main/java/demo/security/SecurityScopeApplication.java
package demo.security;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityScopeApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityScopeApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/documents/**").authenticated()
                .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo123")).roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("demo123")).roles("USER").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo123")).roles("ADMIN").build()
        );
    }
}

@RestController
class DemoController {
    private final DocumentService documents;

    DemoController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }

    @GetMapping("/documents/{id}")
    String document(@PathVariable long id, Authentication authentication) {
        return documents.read(id, authentication.getName());
    }
}

@Service
class DocumentService {
    private final Map<Long, String> ownerById =
        Map.of(1L, "alice", 2L, "bob");

    @PreAuthorize("hasRole('USER')")
    String read(long id, String requester) {
        String owner = ownerById.get(id);

        // Chính sách trên resource: vai trò USER là chưa đủ.
        if (owner == null || !owner.equals(requester)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return "document-" + id;
    }
}
```

Có **ba lớp quyết định**:

1. `/admin` yêu cầu `ROLE_ADMIN`; đây là phân quyền theo URL ở `SecurityFilterChain`.
2. `DocumentService.read` yêu cầu `ROLE_USER` bằng `@PreAuthorize`. Vì đã có `@EnableMethodSecurity` và lời gọi từ controller sang bean service, check tại method được áp dụng. `@PreAuthorize` không tự áp dụng nếu gọi nội bộ một phương thức cùng bean qua `this`.
3. Dòng so sánh `owner.equals(requester)` kiểm tra **quyền với dữ liệu cụ thể**. Nếu chỉ dùng `authenticated()` cho `/documents/**` hoặc chỉ `hasRole('USER')`, Alice có thể xem tài liệu của Bob khi biết ID.

Ví dụ trả `404` khi tài liệu không tồn tại **hoặc** không thuộc người yêu cầu để hạn chế suy đoán sự tồn tại; trong hệ thống thật, cần định nghĩa rõ khi nào trả `403`/`404` theo hợp đồng API. Với hệ thống nhiều tenant, kiểm tra phải dựa trên tenant lấy từ danh tính đáng tin cậy, không chỉ `tenantId` do client gửi. Trong thực tế, thực hiện policy trong service/repository với truy vấn kiểu `findByIdAndOwnerId`/`findByIdAndTenantId` giúp tránh nạp nhầm dữ liệu.

### 5.3. Chạy và kiểm tra

Yêu cầu JDK 17+ và Maven 3.9+ trong thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Ở terminal khác, thử:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u alice:demo123 http://localhost:8080/documents/1
curl -i -u alice:demo123 http://localhost:8080/documents/2
curl -i -u alice:demo123 http://localhost:8080/admin
curl -i -u admin:demo123 http://localhost:8080/admin
curl -i -u admin:demo123 http://localhost:8080/documents/1
```

| Request | HTTP status dự kiến | Body thành công / lý do |
| --- | --- | --- |
| `GET /public`, anonymous | `200` | `public` |
| `GET /admin`, anonymous | `401` | Cần xác thực bằng Basic |
| `GET /documents/1`, Alice | `200` | `document-1` |
| `GET /documents/2`, Alice | `404` | Bị từ chối bởi kiểm tra owner |
| `GET /admin`, Alice | `403` | Không có role ADMIN |
| `GET /admin`, Admin | `200` | `admin` |
| `GET /documents/1`, Admin | `403` | Method yêu cầu role USER |

Mã trả về là hành vi cần đối chiếu; header/body lỗi chi tiết phụ thuộc cấu hình server. Sample chỉ có GET nên không cần gửi CSRF token trong các lệnh trên. Nếu bổ sung POST/PUT/DELETE có session/cookie, cần thiết kế và kiểm tra token CSRF. `httpBasic` phải đi qua HTTPS ở môi trường thật vì Basic chỉ mã hóa Base64 credential, không mã hóa đường truyền.

## 6. Tình huống sai thường gặp và cách sửa

### Tình huống A — “Đã đăng nhập nên đọc tài liệu nào cũng được”

```java
// SAI trong hệ thống có tài liệu riêng tư:
@GetMapping("/documents/{id}")
Document get(@PathVariable Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

Bộ lọc HTTP có thể buộc đăng nhập, nhưng query này không ràng buộc người sở hữu. Hướng sửa: xác định principal/tenant từ server, kiểm tra quyền trước thao tác, và truy vấn bằng điều kiện tài liệu **cùng** owner/tenant. Không dùng `ownerId` nhận từ request body làm bằng chứng người sở hữu.

### Tình huống B — “Bật bảo mật rồi nên không bị XSS/SQLi”

```java
// SAI: nối dữ liệu không tin cậy vào truy vấn:
String sql = "SELECT * FROM orders WHERE code = '" + input + "'";
```

Spring Security không tự biến câu SQL đó thành truy vấn an toàn. Hướng sửa: `PreparedStatement`/parameterized query hoặc ORM với parameter binding; escape output theo HTML/attribute/URL/JavaScript context và sanitize HTML nếu ứng dụng cho nhập rich text. CSP là lớp bổ sung, **không** thay escaping.

### Tình huống C — “API stateless thì luôn có thể tắt CSRF”

“Stateless” về mặt server **không đủ** để kết luận. Câu hỏi quyết định là trình duyệt có tự đính kèm credential vào cross-site request không. API chỉ nhận Bearer token qua header `Authorization` do client tự đặt thường có mô hình rủi ro khác so với cookie auth; cần xem threat model cụ thể. CORS cấu hình chặt không thay thế CSRF token khi CSRF vẫn có thể xảy ra.

### Tình huống D — “`permitAll()` làm endpoint hoàn toàn không được bảo vệ”

`permitAll` bỏ yêu cầu phân quyền đối với request khớp, nhưng nếu request vẫn đi qua security filter chain, các cơ chế như ghi security headers có thể tiếp tục hoạt động. `web.ignoring()` loại đường dẫn khỏi Spring Security filter chain và có tác động rộng hơn; tránh dùng như cách mặc định cho static resources.

### Tình huống E — “Role đã đủ cho hệ thống nhiều tenant”

Role chỉ trả lời loại hành động được phép, ví dụ `REPORT_VIEWER`; **scope dữ liệu** còn cần tenant và quyền thực tế. Phải kiểm soát ở list/detail/export, background job, cache key và truy vấn. Khi chuyển từ `GET` sang `POST` hay thêm endpoint mới, kiểm tra lại toàn bộ lớp policy.

## 7. Quy trình thiết kế, vận hành và kiểm thử

### 7.1. Thiết kế từ tài sản cần bảo vệ

1. Liệt kê dữ liệu/hành động: profile, hóa đơn, tài liệu, xuất file, admin, webhook, health endpoint.
2. Xác định chủ thể: anonymous, user, admin, service account, tenant; phân biệt identity claim và role/permission do máy chủ tin cậy.
3. Viết ma trận **principal × action × resource × điều kiện**. Ví dụ: chỉ owner được xem tài liệu; admin có quyền cấp quản lý theo tenant; nhân viên chỉ export trường được cho phép.
4. Đặt kiểm tra ở cả **entrypoint** (HTTP/method) và **domain/data**. Quy tắc domain không được phụ thuộc mỗi controller.
5. Chọn session cookie, JWT bearer hoặc OAuth2/OIDC theo trust boundary; cấu hình TLS, CSRF, CORS, lưu/thu hồi token tương ứng. Tránh tắt filter không hiểu nguyên nhân.
6. Thực hiện kiểm soát bổ trợ: validation, parameter binding, output escaping, secret management, rate limit, quota, patching, audit log, backup.

### 7.2. Ma trận test tối thiểu

| Kiểm tra | Dự kiến |
| --- | --- |
| Anonymous gọi endpoint private | `401` hoặc chuyển hướng tới login tùy cơ chế |
| User thường gọi admin | `403` |
| Alice đọc/sửa/xóa tài nguyên Bob | Bị từ chối hoặc không thấy, không lộ dữ liệu |
| User gửi `tenantId`/`ownerId` giả | Không vượt qua policy kiểm tra ở server |
| Quyền bị thu hồi, session/token hết hạn | Không tiếp tục được dùng theo thiết kế revocation/expiry |
| POST bằng cookie auth nhưng thiếu/sai CSRF token | Bị chặn khi CSRF protection áp dụng |
| URL mới chưa có trong allowlist | Bị chặn theo `denyAll`; test cả HTTP method |
| Input chứa ký tự SQL/HTML đặc biệt | Query vẫn tham số hóa, output không thực thi mã |
| Request quá lớn/quá nhanh | Chịu giới hạn payload/rate/quota đã thiết kế |
| Log lỗi có mật khẩu/token/PII | Không ghi lộ dữ liệu nhạy cảm |

Trong Spring Boot, dùng `MockMvc`/`spring-security-test` để kiểm tra `@WithMockUser`, `user()`, `csrf()`, đồng thời dùng integration test với repository thật hoặc dữ liệu mô phỏng nhiều chủ sở hữu để bắt lỗi IDOR. Test cấu hình chuỗi filter và method security, không chỉ test service logic. Nếu có nhiều security chain, viết test cho endpoint khớp và **không khớp** từng chain.

### 7.3. Các câu hỏi tự đánh giá trước khi phát hành

- Endpoint nào `permitAll`? Tại sao được công khai, và liệu dữ liệu trả về có nhạy cảm?
- Người dùng có thể thay ID, tenant, role, query/filter, filename hoặc URL trong request để mở rộng quyền không?
- Tại chỗ đọc/ghi dữ liệu, policy có dùng identity thực từ phía server và xác minh chủ sở hữu không?
- Các lời gọi từ event/job/service hoặc nội bộ có đi vòng qua policy HTTP không?
- Có cơ chế chống SQLi, XSS, SSRF, upload độc hại, lộ secrets và DoS phù hợp với attack surface chưa?
- Có test âm tính cho anonymous, role sai, object khác owner và cấu hình lỗi không?
- Ai chịu trách nhiệm nâng cấp thư viện, kiểm tra bảo mật định kỳ, theo dõi sự kiện và xử lý sự cố?

## 8. Những điều cần ghi nhớ

1. **Spring Security là nền tảng thực thi chính sách xác thực/phân quyền**, cùng các cơ chế HTTP được bật và cấu hình đúng; framework không thể tự đoán chính sách nghiệp vụ.
2. **Authentication ≠ authorization ≠ data ownership.** Đăng nhập hợp lệ và có role hợp lệ vẫn có thể không được đụng vào một document cụ thể.
3. **Default không thay thế threat model.** Cấu hình, dependency, session/token, frontend, reverse proxy và phiên bản quyết định hành vi thực tế.
4. **Defense in depth:** filter + service/repository policy + code an toàn + hạ tầng + kiểm thử + vận hành.
5. Định nghĩa hệ thống an toàn bằng **quy tắc có thể kiểm chứng và test trường hợp bị từ chối**, không bằng việc đã khai báo một dependency.

## Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
