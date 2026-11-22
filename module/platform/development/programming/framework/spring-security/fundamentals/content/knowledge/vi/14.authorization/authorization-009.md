# Phân quyền tại HTTP, phương thức và dữ liệu bổ sung cho nhau

> **Phạm vi:** Spring Security fundamentals → Phân quyền. Bài này giải thích cách kết hợp ba cấp kiểm soát: **HTTP/request → phương thức nghiệp vụ → quyền trên dữ liệu cụ thể**. Các cấp giải quyết những rủi ro khác nhau và phải nhất quán với một chính sách nghiệp vụ.

## 1. Vì sao một lớp phân quyền chưa đủ?

Một API quản lý tài liệu có endpoint `GET /api/documents/42`. Giả sử hệ thống xác thực được Alice và Alice có quyền `DOC_READ`. Điều đó **chưa đủ** để khẳng định Alice được đọc tài liệu 42: tài liệu có thể thuộc Bob hoặc một tenant khác.

Ba câu hỏi cần trả lời riêng:

1. **HTTP:** Người gọi có được đi vào nhóm endpoint này không? Ví dụ đường `/api/**` yêu cầu đăng nhập, đường quản trị yêu cầu quyền quản trị.
2. **Phương thức nghiệp vụ:** Danh tính này có được thực hiện *hành động* “đọc tài liệu”, “duyệt đơn”, “hoàn tiền” không, kể cả khi hành động được gọi từ controller khác, job hoặc message listener?
3. **Dữ liệu:** Trong các bản ghi cùng loại, người này được thao tác **bản ghi nào, thuộc tenant nào, trong trạng thái nào**, và được xem/sửa những trường nào?

Một người có quyền đọc tài liệu nói chung vẫn không có quyền đọc **mọi tài liệu**. Tương tự, một repository lọc bản ghi theo owner không thay thế cho quy tắc “chỉ người có quyền duyệt mới được phê duyệt”. Các lớp phải bổ sung, thống nhất và kiểm thử cùng nhau.

### Ví dụ ma trận quyết định

| Yêu cầu | HTTP | Method | Data | Kết quả mong muốn |
|---|---|---|---|---|
| Anonymous GET tài liệu riêng | Chặn vì chưa đăng nhập | Không vào nghiệp vụ | Không truy vấn | 401 với cấu hình HTTP Basic trong ví dụ |
| Alice, có `DOC_READ`, đọc tài liệu Alice | Cho qua | Cho phép hành động đọc | Bản ghi thuộc tenant và Alice | 200 |
| Alice, có `DOC_READ`, đọc tài liệu Bob | Cho qua | Cho phép hành động đọc | Không nằm trong phạm vi | 404 theo chính sách ví dụ |
| Người đã đăng nhập nhưng không có `DOC_READ` | Cho qua | Từ chối | Không chạy truy vấn | 403 |
| Người có `DOC_READ` nhưng cố POST sửa dữ liệu | Chặn theo HTTP rule hoặc method rule tương ứng | Không cấp quyền sửa | Không thực hiện update | 403 hoặc 405 tùy endpoint được khai báo |

**Lưu ý:** 401, 403, 404 phụ thuộc cơ chế authentication/entry point, mapping route và chính sách không tiết lộ sự tồn tại tài nguyên. Với form login, người chưa đăng nhập có thể được redirect thay vì nhận 401. Không hứa một status code cho mọi cấu hình Spring Security.

## 2. Đường xử lý và trách nhiệm từng tầng

```text
Client / token / session
        |
        v
[HTTP security filter chain]
  - Xác thực credential
  - Request matcher, method, path, dispatcher type
  - Chính sách truy cập theo nhóm URL
        |
        v
[Controller / handler]
  - Kiểm tra định dạng input
  - Chuyển sang use case/service
        |
        v
[Method security ở service]
  - Quyền thực hiện hành động nghiệp vụ
  - Quy tắc trạng thái hoặc chính sách tùy ngữ cảnh
        |
        v
[Data authorization trong query / domain]
  - tenant_id, owner, membership, ACL, status
  - Trường dữ liệu nào được đọc/sửa
        |
        v
[Repository/DB] → DTO được phép → HTTP response
```

Không phải mọi ứng dụng cần 100% biểu thức tại mỗi tầng. Với endpoint công khai, HTTP có thể `permitAll`; với một operation bảo mật, thường cần đủ kiểm tra tại nơi phù hợp. Điều quan trọng là **mỗi quy tắc có chủ sở hữu rõ ràng** và không có đường gọi nào vô tình bỏ qua nó.

| Tầng | Công cụ quen thuộc trong Servlet Spring Security | Giới hạn cần hiểu |
|---|---|---|
| HTTP | `SecurityFilterChain`, `HttpSecurity`, `authorizeHttpRequests`, `requestMatchers`, `AuthorizationManager` | Thấy request/path/method, không tự biết bản ghi 42 thuộc ai |
| Method | `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, hoặc authorization service | Chỉ được áp dụng khi invocation thực sự đi qua interceptor/proxy |
| Data/object | Query có predicate scope; permission service; ACL; RLS của DB; projection DTO | Phải được áp dụng trên **mọi** read/list/update/delete/export/stream, không chỉ get-by-id |

**Quy tắc tổng hợp:** Một operation chỉ được thực thi nếu các kiểm tra liên quan đều cho phép. Thông thường cần **authenticate → authorize action → authorize resource → thực thi → trả dữ liệu đã giới hạn**. Không dùng một lần kiểm tra quyền trên UI hoặc kiểm tra role ở HTTP rồi bỏ qua ownership.

## 3. Phân quyền ở HTTP: bảo vệ cửa vào

### 3.1. Khai báo chính sách tuyến đường rõ ràng

Với Spring MVC/Servlet, Spring Security tích hợp vào Servlet filter chain qua `FilterChainProxy` và các `SecurityFilterChain`. Có thể dùng `requestMatchers` cùng HTTP method/path để mô tả nhóm request.

Ví dụ phần cấu hình độc lập về ý tưởng, **chưa phải toàn bộ ứng dụng**:

```java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .authenticated()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Imports trọng tâm: `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `HttpMethod`. Không phải Java class hoàn chỉnh. `GET /api/documents/42` đòi hỏi danh tính đã xác thực, sau đó **service vẫn phải kiểm tra `DOC_READ`** và dữ liệu vẫn phải thuộc scope của người gọi. `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo tiền tố mặc định; `hasAuthority("DOC_READ")` kiểm tra chính xác authority `DOC_READ`. Đừng lẫn role với permission.

### 3.2. Sai lầm matcher và filter chain

- Matcher được đánh giá theo thứ tự trong registry: quy tắc rộng đặt trước có thể bắt mất quy tắc hẹp. Ví dụ `/api/**` = `permitAll` trước `/api/admin/**` là lỗi nghiêm trọng.
- `anyRequest().authenticated()` chỉ kiểm tra đăng nhập; không đồng nghĩa với quyền truy cập toàn bộ tài nguyên. `anyRequest().denyAll()` giúp từ chối đường chưa có chính sách chủ động.
- Với nhiều `SecurityFilterChain`, `securityMatcher` quyết định chain nào xử lý request; chỉ **chain khớp đầu tiên** được dùng. Nếu không có chain nào khớp, request có thể không được Spring Security bảo vệ. Kiểm tra thứ tự `@Order`, matcher và fallback.
- Phân biệt URL-level protection với method-level protection. Nếu có đường khác gọi cùng service, matcher HTTP ở controller đầu tiên không bảo vệ đường đó.
- Dispatcher `ERROR`/`FORWARD` có thể làm status lỗi bị thay đổi nếu chặn mọi loại dispatch. Cấu hình phù hợp với ứng dụng; không cấp quyền rộng bừa bãi cho business endpoint.
- Không dựa vào việc ẩn nút ở frontend, CORS hay chỉ xác thực API gateway thay cho authorization trên service.

### 3.3. Authentication, 401/403, CSRF

Authentication trả lời “ai đang gọi?”. Authorization trả lời “người đó được làm gì với tài nguyên này?”. Với Basic hoặc bearer resource server, anonymous thường nhận 401; đã đăng nhập nhưng thiếu quyền thường 403. Một số chính sách dữ liệu trả 404 cho bản ghi ngoài scope để tránh lộ metadata, song cần nhất quán và không dùng việc đổi status như biện pháp bảo mật duy nhất.

CSRF là rủi ro khác authorization: khi browser **tự đính kèm** cookie/session (hoặc cơ chế credential tự động), một trang độc hại có thể khiến browser gửi request thay đổi trạng thái. Với REST API chỉ dùng bearer header do ứng dụng chủ động gửi, phân tích CSRF có thể khác. **Không tắt CSRF chỉ vì “API có token”**; xét thực tế credential được gửi thế nào. Dùng `GET` cho thao tác an toàn không thay đổi trạng thái.

## 4. Phân quyền tại phương thức: bảo vệ use case

HTTP guard bảo vệ điểm vào; method security bảo vệ **khả năng nghiệp vụ** bất kể controller nào gọi service. Trên Spring Security 6 cho mô hình imperative:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Trên một bean `@Service`:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public DocumentDto readDocument(long id) {
    return repository.load(id);
}

@PreAuthorize("hasAuthority('DOC_APPROVE')")
public void approveDocument(long id) {
    // Kiểm tra trạng thái + phạm vi tài nguyên trước khi thay đổi
}
```

Các đoạn ở trên minh họa vị trí đặt annotation; `DocumentDto`, `repository` và thân hàm là thành phần của project, **không phải class runnable độc lập**. Cần bật `@EnableMethodSecurity`. Mặc định hỗ trợ `@PreAuthorize`/`@PostAuthorize`; các annotation khác có tùy chọn kích hoạt riêng tùy loại.

**Nên đặt ở service có ý nghĩa nghiệp vụ**, chẳng hạn `approveInvoice`, `refundPayment`, `inviteMember`. Controller có thể thay đổi, còn quy tắc “ai được phép approve” nên gắn với use case và được dùng lại cho web, message consumer và tác vụ có principal phù hợp. Không nhân bản nguyên một biểu thức không cần thiết ở 20 controller rồi quên sửa một chỗ.

### 4.1. Khi nào dùng `@PreAuthorize`, `@PostAuthorize`?

- `@PreAuthorize` kiểm tra **trước** khi gọi method. Dùng cho quyền hành động, điều kiện input đáng tin và gọi bean policy như `@documentPolicy.canEdit(#id, authentication)`.
- `@PostAuthorize` đánh giá giá trị trả về **sau** khi method đã chạy. Nó hữu ích cho một số thao tác đọc nhưng không cứu được side effect đã phát sinh, không hoàn nguyên giao dịch một cách tự động theo mọi tình huống, và có thể đã tải thông tin ngoài phạm vi lên bộ nhớ.
- `@PreFilter` / `@PostFilter` có thể lọc collection, nhưng không phải lựa chọn mặc định cho hàng triệu bản ghi: lọc sau khi tải có thể làm rò rỉ qua count, gây lỗi phân trang, hiệu năng và cache. Với danh sách lớn hãy ràng buộc scope ngay trong truy vấn DB.

Ví dụ policy bean, đoạn minh họa:

```java
@PreAuthorize("@documentPolicy.canEdit(#documentId, authentication)")
public void renameDocument(long documentId, String newTitle) {
    repository.rename(documentId, newTitle);
}
```

`documentPolicy` là một Spring bean có method kiểm tra quyền thực tế; tham số trong biểu thức phải được Spring Security nhận diện đúng tên, có thể dùng `@P("documentId")` hoặc cấu hình biên dịch giữ parameter names khi cần. Dù pre-check đúng, thao tác update vẫn nên có điều kiện scope trong SQL để giảm nguy cơ thay đổi quyền giữa lúc kiểm tra và ghi.

### 4.2. Cạm bẫy method security

Method security kiểu proxy thường áp dụng khi **lời gọi đi qua Spring-managed proxy**. Một method trong cùng class tự gọi method được đánh dấu `@PreAuthorize` qua `this.method()` có thể bỏ qua interceptor. Bean tự tạo với `new`, private/non-proxyable method hoặc cấu hình proxy không phù hợp cũng có thể bỏ qua advice. Đừng tin annotation chỉ vì code compile; dùng integration test gọi qua bean thực.

Ngoài ra, bảo vệ method cho job/consumer cần xác định **service identity** và quyền rõ ràng. Không tự giả định HTTP authentication vẫn có trong thread của worker, scheduler hoặc message listener.

## 5. Phân quyền dữ liệu: chống IDOR/BOLA và vượt tenant

IDOR (Insecure Direct Object Reference) hoặc Broken Object Level Authorization xảy ra khi caller thay ID tài nguyên trong URL/body và nhận bản ghi không thuộc quyền. Ví dụ Alice được đọc tài liệu 1, nhưng thay `/api/documents/1` thành `/api/documents/2` để đọc tài liệu Bob. Cả hai request đều đã authenticated và Alice có thể có `DOC_READ`; lỗ hổng nằm ở **object-level authorization**.

### 5.1. Ràng buộc scope ngay trong query

**Không an toàn:**

```sql
SELECT id, title
FROM documents
WHERE id = ?;
```

Sau đó chỉ kiểm tra `hasAuthority("DOC_READ")` là chưa đủ. Khi hệ thống yêu cầu tenant + owner, điều kiện phải bao gồm cả hai:

```sql
SELECT id, title
FROM documents
WHERE id = ?
  AND tenant_id = ?
  AND owner_username = ?;
```

Các dấu `?` phải được binding qua prepared statement/JDBC template, không nối trực tiếp chuỗi SQL. `tenant_id` và `owner_username` lấy từ **identity/membership được hệ thống xác thực**, không đơn thuần tin vào header `X-Tenant-Id`, query parameter `?tenant=T2` hoặc owner do client gửi. Nếu cho người dùng chọn tenant, backend phải kiểm tra họ thực sự thuộc tenant đó trước khi dùng.

Khi truy vấn không tìm thấy tài liệu trong scope, có thể trả 404 (kể cả bản ghi tồn tại ngoài scope), tránh xác nhận sự tồn tại ID của người khác. Đổi 403 sang 404 không thay cho điều kiện DB và cũng phải xem yêu cầu audit/UX.

### 5.2. Danh sách, đếm, tìm kiếm, xuất và cập nhật

Scope phải áp dụng **nhất quán ở mọi đường dữ liệu**:

- `GET /documents/{id}`: tìm bản ghi có `id + tenant + owner/ACL`.
- `GET /documents`: lọc scope trong SQL **trước khi** `ORDER BY`, `LIMIT/OFFSET`; `count` cũng chỉ đếm bản ghi nhìn thấy.
- Search, export CSV, batch read và cache: dùng cùng phạm vi; tránh để file export hoặc cache key bỏ qua `tenant_id`/caller.
- `PATCH/DELETE`: ngoài quyền hành động, ràng buộc phạm vi **trong chính câu lệnh ghi** và kiểm tra affected rows, tránh cửa sổ race giữa check và update.
- Trả DTO chỉ có trường được phép xem; owner có quyền đọc một tài liệu không mặc nhiên được xem secret, internal flags, dữ liệu định danh của người khác.

Ví dụ SQL cập nhật có điều kiện:

```sql
UPDATE documents
SET title = ?
WHERE id = ?
  AND tenant_id = ?
  AND owner_username = ?;
```

Nếu 0 dòng được cập nhật, có thể là ID không tồn tại hoặc không thuộc scope; quyết định response và audit theo hợp đồng nghiệp vụ. Nếu cần thêm điều kiện “chỉ sửa tài liệu ở trạng thái DRAFT”, thêm `AND status = 'DRAFT'` hoặc kiểm soát concurrency/lock phù hợp trong cùng transaction. **Kiểm tra rồi ghi ở hai câu lệnh độc lập không luôn bảo đảm tính nguyên tử.**

### 5.3. Nhiều quan hệ quyền hơn owner

Ownership chỉ là một mô hình. Ứng dụng có thể cần membership nhóm, tenant role, relationship-based access (ReBAC), attribute-based access (ABAC), access control list (ACL), trạng thái tài liệu, quyền được ủy nhiệm và policy theo thời gian. Đặt logic có thể tái sử dụng trong domain authorization service và chiếu predicate phù hợp xuống query. Cần cân bằng tính dễ đọc, hiệu năng, khả năng giải thích lý do từ chối và audit.

Với PostgreSQL có thể cân nhắc Row-Level Security (RLS) như lớp bổ sung tại DB. RLS phải được cấu hình với session/transaction identity đáng tin, policy đúng và kết nối pool không làm rò context. RLS không miễn trừ kiểm tra action-level tại service hay việc ẩn trường dữ liệu nhạy cảm.

## 6. Ví dụ end-to-end: HTTP + method + data cùng bảo vệ một API

Ví dụ này tạo **một ứng dụng Spring Boot 3.x, Java 17+**, dùng Servlet MVC, Spring Security 6, JDBC và H2 in-memory. Mục tiêu không phải thiết kế hệ thống production mà là chạy một tình huống minh bạch, kiểm chứng được cả ba tầng. Tài khoản demo dùng password `{noop}` để học **chỉ trong môi trường cục bộ**, không dùng cho hệ thống thật.

Dữ liệu và quyền:

| User | Tenant do server xác định | Authorities | Bản ghi sở hữu |
|---|---|---|---|
| `alice` | `T1` | `DOC_READ` | 1, 3 |
| `bob` | `T2` | `DOC_READ` | 2 |
| `visitor` | Không có tenant | `DASHBOARD_READ` | Không có |

### 6.1. Dependencies

Từ Spring Initializr tạo **Gradle Spring Boot 3.x, Java 17+**, sau đó đảm bảo `build.gradle` có các dependencies (đoạn này chỉ là **khối dependencies** của project Boot, không phải toàn bộ build file):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Chỉ dùng starter Web MVC trong ví dụ; không thêm `spring-boot-starter-webflux`. Mặc định Spring Boot tự chạy script `schema.sql`/`data.sql` với H2 embedded.

### 6.2. Tạo bảng mẫu

Tệp `src/main/resources/schema.sql`:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    owner_username VARCHAR(80) NOT NULL,
    title VARCHAR(200) NOT NULL
);

CREATE INDEX idx_documents_scope
    ON documents (tenant_id, owner_username, id);
```

Tệp `src/main/resources/data.sql`:

```sql
INSERT INTO documents (id, tenant_id, owner_username, title)
VALUES
    (1, 'T1', 'alice', 'Alice private'),
    (2, 'T2', 'bob',   'Bob private'),
    (3, 'T1', 'alice', 'Alice notes');
```

### 6.3. Mã Java đầy đủ

Đặt **một tệp** `src/main/java/example/authz/AuthorizationApplication.java`. Trong thực tế nên tách configuration, controller, service, repository và policy ra các tệp/package riêng; gom chung ở đây để chạy mẫu dễ dàng.

```java
package example.authz;

import jakarta.servlet.DispatcherType;
import java.util.List;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // ERROR dispatch không vô tình đổi lỗi ứng dụng thành 403.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .authorities("DOC_READ")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}demo123")
            .authorities("DOC_READ")
            .build();
        UserDetails visitor = User.withUsername("visitor")
            .password("{noop}demo123")
            .authorities("DASHBOARD_READ")
            .build();
        return new InMemoryUserDetailsManager(alice, bob, visitor);
    }
}

record DocumentView(long id, String title) {}

@RestController
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping("/api/documents/{id}")
    ResponseEntity<DocumentView> getDocument(
            @PathVariable long id, Authentication authentication) {
        return service.findOneForCaller(id, authentication)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}

@Service
class DocumentService {
    private final DocumentRepository repository;
    private final TenantDirectory tenantDirectory;

    DocumentService(DocumentRepository repository,
                    TenantDirectory tenantDirectory) {
        this.repository = repository;
        this.tenantDirectory = tenantDirectory;
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Optional<DocumentView> findOneForCaller(
            long id, Authentication authentication) {
        String caller = authentication.getName();
        String tenant = tenantDirectory.requiredTenant(caller);
        return repository.findVisible(id, tenant, caller);
    }
}

@Component
class TenantDirectory {
    String requiredTenant(String username) {
        // Mô phỏng membership đã được server quản lý.
        return switch (username) {
            case "alice" -> "T1";
            case "bob" -> "T2";
            default -> throw new AccessDeniedException(
                "Caller has no tenant membership");
        };
    }
}

@Repository
class DocumentRepository {
    private final JdbcTemplate jdbc;

    DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    Optional<DocumentView> findVisible(long id, String tenant,
                                       String caller) {
        List<DocumentView> rows = jdbc.query(
            """
            SELECT id, title
            FROM documents
            WHERE id = ? AND tenant_id = ? AND owner_username = ?
            """,
            (rs, rowNum) -> new DocumentView(
                rs.getLong("id"), rs.getString("title")),
            id, tenant, caller);
        return rows.stream().findFirst();
    }
}
```

Giải thích từng tuyến bảo vệ:

1. **HTTP:** chỉ `/public/ping` public; `GET /api/documents/*` yêu cầu đã xác thực; các tuyến còn lại không được khai báo chủ động sẽ bị `denyAll`.
2. **Method:** `DocumentService.findOneForCaller` yêu cầu authority `DOC_READ`. `visitor` đăng nhập thành công nhưng bị từ chối trước khi chạm DB.
3. **Data:** `TenantDirectory` xác định tenant từ danh tính đã xác thực ở phía server; SQL giới hạn `id + tenant + owner`. Alice có `DOC_READ` vẫn không được xem dữ liệu Bob.
4. **Output:** DTO `DocumentView` chỉ trả `id` và `title`; tenant/owner không bị lộ vô tình. DTO là lớp lọc trường, không thay thế scope ở query.

Ở sản phẩm thật, thay `TenantDirectory` hardcode bằng dữ liệu membership/claims đã xác minh và xử lý nhiều tenant/quyền phân cấp; thay user/password demo bằng authentication thực tế, password hash phù hợp, TLS và quy trình quản trị credential. Không lấy tenant từ header không được xác nhận.

### 6.4. Chạy và kiểm tra kết quả

Chạy trong thư mục project đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows dùng `gradlew.bat bootRun`. Mặc định service ở `http://localhost:8080` nếu chưa cấu hình khác. Kiểm tra bằng:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/1
curl -i -u visitor:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/2
curl -i -u bob:demo123 http://localhost:8080/api/documents/2
```

| Request | HTTP dự kiến | Vì sao |
|---|---:|---|
| Public ping | 200, body `ok` | HTTP `permitAll` |
| Anonymous GET tài liệu 1 | 401 | HTTP yêu cầu login, Basic entry point |
| Visitor GET tài liệu 1 | 403 | HTTP qua được nhưng `@PreAuthorize` từ chối |
| Alice GET tài liệu 1 | 200, JSON `{"id":1,"title":"Alice private"}` | Đủ quyền + đúng tenant + owner |
| Alice GET tài liệu 2 | 404 | Có `DOC_READ` nhưng SQL scope không thấy tài liệu Bob |
| Bob GET tài liệu 2 | 200, JSON `{"id":2,"title":"Bob private"}` | Đủ quyền + đúng scope |

Một kịch bản giá trị cao là **thay ID** của tài liệu thuộc người khác bằng request đã xác thực. Nếu chỉ kiểm tra HTTP+method, request Alice→ID2 sẽ lọt. Nếu query được scope đúng, nó trả kết quả rỗng.

### 6.5. Integration test kiểm chứng đủ ba tầng

Tạo `src/test/java/example/authz/AuthorizationLayersTest.java`:

```java
package example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationLayersTest {
    @Autowired
    MockMvc mvc;

    @Test
    void httpMethodAndDataScopeWorkTogether() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/documents/1")
                .with(httpBasic("visitor", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice private"));

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("bob", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Bob private"));
    }
}
```

Chạy `./gradlew test` (Windows: `gradlew.bat test`). Test là **integration test dùng Spring context và security filter thực**, khác với unit test chỉ mock service rồi khẳng định controller trả đúng data. Các giả định cần giữ: Spring Boot 3.x đúng dependency versions và H2 nạp `schema.sql`/`data.sql` tại startup. Nếu ứng dụng thật có nhiều datasource, migration tool hoặc cấu hình SQL initialization riêng, cần sửa fixture tương ứng.

## 7. Không tạo “lỗ hổng” giữa ba tầng

### 7.1. Truy cập theo đối tượng và đa tenant

Giả sử tenant T1 và T2 dùng chung bảng. Role `ROLE_MANAGER` chỉ cho biết “quản lý”, **không nói** đó là manager của tenant nào. Phải xác định tenant membership/permission trong service và gắn tenant vào read/write query. Header chọn tenant là **dữ liệu chưa tin cậy** cho đến khi xác thực mối quan hệ user↔tenant.

Một thiết kế phổ biến:

```text
Authenticated principal
  -> validated tenant membership (server-side)
  -> action permission for that tenant
  -> object relationship/status constraints
  -> scoped SELECT / UPDATE / DELETE
  -> field-filtered DTO
```

Có thể có admin quyền xuyên tenant, nhưng phải khai báo rõ policy, audit và test. **Không biến mọi admin thành bypass mọi điều kiện nghiệp vụ** ngoài ý muốn.

### 7.2. Xác thực tại đâu, authorize tại đâu?

Trong bearer JWT resource server, Security xác minh token theo chính sách issuer, chữ ký, thời hạn, audience khi phù hợp; sau đó chuyển scopes/roles thành authorities. Không dùng trực tiếp username hoặc tenant do client nhập thay cho claims/membership đã kiểm tra. Token hợp lệ chỉ chứng minh các claims tin cậy theo thiết lập; không có nghĩa tài nguyên ID bất kỳ tự động hợp lệ.

Ở service, dùng một authorizer có cấu trúc cho quy tắc phức tạp thay vì biểu thức SpEL quá dài. Ví dụ `canApprove(user, invoice)` có thể kiểm tra role, tenant, người tạo không tự duyệt và trạng thái đang chờ. Repo phải dùng update có điều kiện hoặc transaction/locking để bảo đảm trạng thái không đổi giữa check và commit.

### 7.3. Field-level authorization

Một user được xem đơn hàng có thể được thấy `id, status, total` nhưng không được thấy `cardToken, internalNotes`. Truy vấn scoped là điều kiện cần nhưng chưa đủ: thêm projection/DTO/serializer policy đúng mức độ nhạy cảm. Tránh trả cả JPA entity rồi kỳ vọng frontend tự giấu trường.

Với mutation, không bind toàn bộ request JSON vào entity có `ownerId`, `tenantId`, `approved` mà client có thể sửa. Tạo allowlist trường cập nhật, lấy owner/tenant từ security context phía server và kiểm soát transition bằng business rule.

### 7.4. Cache, background job và message consumers

Cache key cho dữ liệu scoped nên gồm định danh scope cần thiết (tenant, user hoặc permission scope) và version khi quyền đổi; dữ liệu đã được cache bởi Alice không được phát cho Bob vì cùng `documentId`. Background job và consumer phải có service principal, permission explicit hoặc business context đã kiểm chứng; không giả định `SecurityContextHolder` tự lan sang thread/tác vụ bất đồng bộ.

### 7.5. 403, 404 và việc tiết lộ dữ liệu

Một số hệ thống muốn 403 khi user không được quyền với object biết trước; hệ thống khác muốn 404 để hạn chế object enumeration. Cả hai là lựa chọn sản phẩm/bảo mật tùy hợp đồng. Điều bắt buộc là không trả content ngoài scope, không lộ qua list/count/export, latency/error detail hoặc audit log gửi sai đối tượng. Ghi audit nội bộ đầy đủ nhưng response ra client chỉ gồm chi tiết phù hợp.

## 8. Servlet và WebFlux khác nhau ở công cụ, không khác nguyên tắc

Bài này dùng Spring MVC để minh họa. Với WebFlux, mô hình ba tầng vẫn áp dụng nhưng security integration khác:

| Vấn đề | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| HTTP | `SecurityFilterChain`, `HttpSecurity`, `authorizeHttpRequests` | `SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange` |
| Method | `@EnableMethodSecurity` với method imperative | `@EnableReactiveMethodSecurity` với method reactive phù hợp |
| Context | `SecurityContextHolder` thường theo luồng | `ReactiveSecurityContextHolder` trên Reactor Context |
| Data | JDBC/JPA query theo scope/transaction imperative | R2DBC/reactive repository với scope và transaction reactive |
| Test | `MockMvc`, `spring-security-test` | `WebTestClient`, reactive security test helpers |

Đoạn WebFlux minh họa (**chưa phải class runnable**):

```java
@Bean
SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/api/documents/**").authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Trong service reactive, nhận context đúng qua Reactor Context, kiểm tra action bằng reactive method security/policy và truy vấn non-blocking có predicate tenant/owner, ví dụ ý tưởng `repository.findByIdAndTenantIdAndOwnerUsername(id, tenant, username)` trả `Mono`. Không gọi blocking JPA trên event-loop, không lấy identity từ `ThreadLocal` tùy ý, không `block()` để né cấu trúc reactive.

## 9. Những hiểu nhầm và lỗ hổng thường gặp

| Cách làm / nhận định | Vấn đề | Cách xử lý |
|---|---|---|
| “`authenticated()` ở HTTP là đủ.” | Người đăng nhập có thể thử ID của bất cứ ai. | Thêm action authorization và object/tenant scope. |
| “Có `ROLE_ADMIN` thì tất cả tenant tự mở.” | Vai trò không mô tả phạm vi tenant. | Chính sách cross-tenant tường minh, test/audit. |
| “`@PreAuthorize` ở controller là đủ.” | Job, listener hoặc controller khác vẫn gọi service. | Đặt rule ở service/use case, test các đường gọi. |
| “Có annotation là chắc chắn chạy.” | Self-invocation hoặc non-proxied method có thể bỏ qua interceptor. | Spring-managed bean, external invocation, integration test. |
| “`@PostFilter` xử lý mọi danh sách.” | Tải toàn DB vào RAM, sai pagination/count, nguy cơ leak. | Scope ở SQL/query. |
| “Query theo ID là đủ vì ID khó đoán.” | ID có thể lộ hoặc bị đoán; thiếu object authorization. | Luôn query trong scope hoặc check ACL đáng tin. |
| “Lấy tenant từ request header.” | User tự đổi header để truy cập tenant khác. | Xác thực membership và bind tenant đã được duyệt. |
| “Check role rồi UPDATE theo ID.” | Row-level update có thể vượt scope hoặc gặp race. | UPDATE có predicate scope/status, kiểm tra row count. |
| “API trả DTO thì bảo vệ được object.” | DTO chỉ giới hạn field, không bảo vệ ai được nhận record. | Data scope trước, DTO sau. |
| “Ẩn menu là khóa chức năng.” | HTTP request tự tạo vẫn gọi được API. | Bảo vệ server ở HTTP + service + data. |
| “Test HTTP 200 là đủ.” | Không kiểm tra unauthorized, cross-tenant hay thiếu quyền. | Test âm tính cho cả ba tầng. |
| “Auth cache theo ID tài liệu.” | Có thể trả dữ liệu Alice cho Bob. | Cache theo scope, invalidate khi membership thay đổi. |

## 10. Thiết kế bộ test phân quyền trước khi triển khai

Với mỗi use case, lập ma trận gồm **actor × action × resource scope × trạng thái × đường vào**. Ví dụ “xem tài liệu” có các actor anonymous, visitor, alice, bob; resource own, same tenant but not own, other tenant, deleted; đường vào HTTP, service direct, export/list.

Các kiểm thử thiết yếu:

1. **Authentication:** anonymous và credential sai không được vào tài nguyên riêng; kiểm tra entry point đúng với Basic/form/bearer.
2. **HTTP:** route ngoài policy bị từ chối; matcher rộng/hẹp và nhiều filter chain không mở nhầm URL; verb không được cho phép không thể vượt rule.
3. **Method:** user authenticated thiếu `DOC_READ` nhận 403; gọi method qua Spring bean thực, test self-invocation nếu thiết kế có rủi ro; business role/state rule hoạt động.
4. **Object & tenant:** Alice không đọc/sửa tài liệu Bob dù biết ID; user có role tương tự ở tenant khác không truy cập được; query list/count/export cùng scope.
5. **Write:** cập nhật chỉ tác động row hợp lệ; 0 affected rows được xử lý đúng; không cho client sửa owner/tenant/approved; kiểm tra race/transaction nếu nghiệp vụ nhạy cảm.
6. **Field:** response không lộ secret/private field; logs/error payload không tiết lộ bản ghi ngoài quyền.
7. **Async/caching:** không rò principal/tenant qua thread, scheduler, reactor context hoặc cache; thay đổi role/membership có hiệu lực đúng.
8. **Browser:** POST/PUT/PATCH/DELETE với cookie/session có CSRF protection phù hợp; test authorized request thành công với token CSRF hợp lệ và request trái phép bị từ chối.
9. **Failure modes:** DB timeout, retry, exception, concurrency không bỏ qua authorization hoặc thay response thành leak.

Đối với hệ thống có nhiều policy, nên tập trung logic trong **permission service/authorization manager có test độc lập**, thêm integration test cho đường HTTP→service→DB và các negative case. Unit test của controller mock service chỉ xác minh mapping/response; nó **không chứng minh** method interceptor hay SQL scope chạy thật.

## 11. Checklist review một endpoint trước khi release

- [ ] Liệt kê actor, quyền hành động, phạm vi tenant/owner/ACL, trạng thái và field được nhìn thấy.
- [ ] HTTP matcher đúng URL/verb, thứ tự và filter chain; endpoint không mong muốn bị từ chối.
- [ ] Controller không coi dữ liệu client tự khai là identity hoặc tenant đã được kiểm chứng.
- [ ] Service/use case được bảo vệ bằng method security hoặc policy phù hợp; không bị self-invocation bỏ qua.
- [ ] Query read/list/count/export đã scope đúng **trước** phân trang và trước khi build response.
- [ ] UPDATE/DELETE có predicate scope + điều kiện business state; xử lý affected rows/transaction nhất quán.
- [ ] DTO/serialization chỉ phát ra trường được phép; cache key có scope.
- [ ] Đã có test negative: anonymous, thiếu quyền, owner khác, tenant khác, verb không hợp lệ.
- [ ] Đã xét CSRF/session/token, 401/403/404, audit và context propagation ở các đường async.
- [ ] Những quyền admin/cross-tenant hoặc service account vượt scope được ghi rõ, không mặc định bypass.
- [ ] Có người sở hữu chính sách khi xuất hiện endpoint/service/consumer mới.

**Kết luận:** Phân quyền tại HTTP quyết định **ai có thể vào tuyến**, phân quyền tại method quyết định **ai được thực hiện hành động nghiệp vụ**, còn phân quyền dữ liệu quyết định **hành động đó được áp dụng lên bản ghi/trường nào**. Dùng cả ba đúng phạm vi, chia sẻ policy tin cậy, truy vấn có scope và kiểm thử trường hợp bị từ chối là cách giảm đáng kể lỗi IDOR/BOLA, vượt tenant và bypass use case.

## 12. Tham khảo chính thức

- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher, thứ tự rule, `AuthorizationManager`, filter chain.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`, proxy/interceptors.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): session/cookie, các thao tác thay đổi trạng thái, lựa chọn protection.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context và reactive method authorization.
- [Spring Security — Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain` và `ServerHttpSecurity`.
- [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): ngữ cảnh giao dịch và điều kiện kiểm soát thao tác dữ liệu.

**Khi áp dụng:** Đối chiếu tài liệu đúng phiên bản Spring Boot/Spring Security của ứng dụng thực tế; mẫu cố định dùng Boot 3.x / Security 6 và tài khoản cục bộ, không mặc định là cấu hình production.
