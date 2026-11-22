# Xây ma trận kiểm thử theo tài nguyên, thao tác và nhóm người dùng

> **Ngữ cảnh:** Spring Security — fundamentals / Kiểm thử. Bài này hướng dẫn chuyển chính sách truy cập thành **ma trận kiểm thử authorization** theo ba trục **tài nguyên × thao tác × nhóm người dùng**, rồi dùng Spring Security Test và MockMvc chứng minh cả trường hợp được phép lẫn bị từ chối. Ví dụ sử dụng Java 17+, Spring Boot 3.5.0, Spring Security 6.x và Servlet stack.

## 1. Vấn đề: một bài test "đăng nhập thành công" là chưa đủ

Giả sử ứng dụng có tài liệu riêng tư và báo cáo quản trị. Hai người dùng đã đăng nhập đều có thể mở `/api/documents/101`, nhưng liệu người thứ hai được xem tài liệu 101, được sửa tên nó hay được xóa nó? Người có quyền quản trị của **tenant khác** có vượt qua giới hạn tenant hay không? Nếu API trả `403` sau khi dữ liệu đã bị sửa, bài kiểm thử chỉ kiểm tra status có thể **bỏ sót lỗi bảo mật**.

Ba câu hỏi cốt lõi:

1. **Tài nguyên (resource):** đối tượng nào được bảo vệ — tài liệu, báo cáo, bản ghi, file đính kèm, đơn hàng, dự án, danh sách, export?
2. **Thao tác (action):** đang đọc, tạo, sửa, xóa, chia sẻ, phê duyệt, download, export, hay quản trị?
3. **Nhóm người dùng (subject group):** anonymous, owner, đồng nghiệp cùng tenant, editor, auditor, admin, service account, người thuộc tenant khác? Những nhóm này phải phản ánh **danh tính + thuộc tính + quan hệ tới đối tượng**, không chỉ tên role.

Một *authorization test matrix* cho biết **đầu vào, chính sách kỳ vọng và bằng chứng cần xác nhận** ở từng giao điểm. Nó phát hiện BOLA/IDOR (đọc hoặc sửa object người khác), lỗi role/scope, truy cập xuyên tenant và các đường dẫn bị bỏ sót.

**Authentication ≠ authorization.** Spring Security xác minh người dùng là ai; chính sách của ứng dụng còn phải quyết định họ được làm gì với tài nguyên cụ thể. `.authenticated()` bảo vệ route nhưng không tự hiểu ai là chủ sở hữu document 101.

## 2. Biến yêu cầu nghiệp vụ thành quy tắc có thể kiểm thử

Xét một API demo quản lý tài liệu và báo cáo với ba tài liệu ban đầu:

| Tài nguyên | Tenant | Chủ sở hữu | Nội dung minh họa |
|---|---|---|---|
| Document `101` | `east` | `alice` | `Alice plan` |
| Document `202` | `east` | `bob` | `Bob budget` |
| Document `303` | `west` | `mallory` | `West plan` |

Các chủ thể đã được server xác thực và gán tenant/role đáng tin:

| Người gọi | Tenant | Vai trò | Quan hệ cần kiểm thử |
|---|---|---|---|
| Anonymous | — | — | Chưa có danh tính hợp lệ |
| `alice` | `east` | `USER` | Owner của 101 |
| `bob` | `east` | `USER` | Owner của 202; không sở hữu 101 |
| `carol` | `east` | `EDITOR` | Được sửa tài liệu trong tenant, không được xóa tài liệu người khác |
| `audrey` | `east` | `AUDITOR` | Được đọc tài liệu/báo cáo trong tenant; không được sửa/xóa |
| `admin` | `east` | `ADMIN` | Quản trị trong tenant east |
| `mallory` | `west` | `ADMIN` | Quản trị tenant west, **không** có quyền với east |

**Các quy tắc của bài tập** (một chính sách minh họa, không phải chính sách mặc định do Spring Security tự sinh):

- **Document READ:** cùng tenant **và** (là owner **hoặc** có role `EDITOR`, `AUDITOR`, `ADMIN`).
- **Document UPDATE:** cùng tenant **và** (là owner **hoặc** có role `EDITOR`, `ADMIN`).
- **Document DELETE:** cùng tenant **và** (là owner **hoặc** có role `ADMIN`).
- **Report READ:** có role `AUDITOR` hoặc `ADMIN`; dữ liệu thống kê chỉ thuộc tenant mà server xác minh cho người gọi.
- **Anonymous:** không được gọi API bảo vệ.
- **Không tìm thấy document / document thuộc tenant khác:** trả `404` trong demo; caller cùng tenant nhưng không đủ quyền READ cũng nhận `404` để giảm việc dò object. Với UPDATE/DELETE cùng tenant nhưng thiếu quyền, demo trả `403`; lựa chọn này có thể bộc lộ sự tồn tại trong tenant và cần thay đổi nếu chính sách che giấu yêu cầu 404 cho mọi hành động.

Có thể diễn đạt chính sách dạng giả mã:

~~~text
canReadDocument(user, doc) =
    sameTenant(user, doc) AND
    (isOwner(user, doc) OR hasAnyRole(user, EDITOR, AUDITOR, ADMIN))

canUpdateDocument(user, doc) =
    sameTenant(user, doc) AND
    (isOwner(user, doc) OR hasAnyRole(user, EDITOR, ADMIN))

canDeleteDocument(user, doc) =
    sameTenant(user, doc) AND
    (isOwner(user, doc) OR hasRole(user, ADMIN))

canReadReport(user) =
    hasAnyRole(user, AUDITOR, ADMIN)
    // Báo cáo chỉ chứa dữ liệu tenant được server xác minh.
~~~

Điều kiện `sameTenant` áp dụng **ngay cả cho ADMIN**. Quyền admin không tự nhiên vượt mọi tenant. Phân biệt cụ thể giữa role và ownership tránh trường hợp test “ADMIN được mọi thứ” dẫn đến hợp thức hóa một lỗi phân quyền.

## 3. Thiết kế ma trận theo ba trục

Ma trận không phải một bảng role đơn giản. Một bộ test đầy đủ có thể mô hình hóa:

~~~text
Case = {
  resourceType, resourceIdOrScope,
  action, httpMethod, route,
  actor, role, tenant, relationToResource,
  input, expectedStatus, expectedBody, expectedSideEffects
}
~~~

Ma trận mẫu quan trọng nhất đối với document 101:

| Người gọi / quan hệ | GET 101 (READ) | PATCH 101 (UPDATE) | DELETE 101 (DELETE) |
|---|---|---|---|
| Anonymous | 401 | 401* | 401* |
| Alice — owner, east | 200 | 200 | 204 |
| Bob — USER khác owner, east | 404 | 403 | 403 |
| Carol — EDITOR, east | 200 | 200 | 403 |
| Audrey — AUDITOR, east | 200 | 403 | 403 |
| Admin — ADMIN, east | 200 | 200 | 204 |
| Mallory — ADMIN, west | 404 | 404 | 404 |

`* `Với PATCH/DELETE, test phải cung cấp CSRF token hợp lệ khi muốn cô lập kết quả **authentication/authorization**. Nếu thiếu CSRF token, Spring Security có thể trả `403` trước khi đánh giá người gọi. Bài demo giữ CSRF protection mặc định và dùng `with(csrf())` trong MockMvc để không đánh đồng CSRF với authorization.

Bổ sung trục tài nguyên thứ hai, `GET /api/reports/summary`:

| Nhóm người dùng | Dự kiến | Dữ liệu bắt buộc |
|---|---|---|
| Anonymous | 401 | Không trả thống kê |
| Alice / Bob (`USER`) | 403 | Không trả thống kê |
| Carol (`EDITOR`) | 403 | Không trả thống kê |
| Audrey (`AUDITOR`, east) | 200 | Đếm **chỉ** tài liệu east |
| Admin (`ADMIN`, east) | 200 | Đếm **chỉ** tài liệu east |
| Mallory (`ADMIN`, west) | 200 | Đếm **chỉ** tài liệu west |

Các trường hợp biên cần đi kèm:

- Document ID không tồn tại, ví dụ 999: phải là `404`, không tự đổi thành `403` hoặc 500.
- Cross-tenant admin: `GET/PATCH/DELETE /api/documents/101` bằng Mallory luôn bị chặn, dù Mallory có `ROLE_ADMIN`.
- POST/PATCH/DELETE không có CSRF token: phải từ chối trong mô hình demo ngay cả khi người gọi là owner.
- UPDATE bị từ chối: **title không đổi** trong kho dữ liệu sau request.
- DELETE bị từ chối: tài liệu vẫn tồn tại.
- Report không được chứa bản ghi tenant khác dù HTTP status là 200.
- Hai principal có cùng role USER nhưng sở hữu document khác nhau phải cho kết quả trái ngược. Nếu chỉ test một account `USER`, nguy cơ bỏ sót object-level authorization rất lớn.

Để vận hành, mỗi case nên có **ID ổn định** (ví dụ AUTH-DOC-READ-007), liên kết đến điều khoản chính sách, và khả năng truy vết đến test tự động.

## 4. Tách expected outcome khỏi implementation

Khi viết ma trận, xác định expected từ **quy tắc đã duyệt** trước khi chạy code. Không lấy status trả về hiện tại làm expected: một lỗ hổng `200` có thể bị đóng dấu “test passed” nếu expected được sinh từ hệ thống đang sai.

Một case cần bốn lớp assertion:

1. **HTTP status:** 200/204 khi được phép; 401/403/404 theo hợp đồng khi bị từ chối.
2. **Response data:** dữ liệu đúng chủ thể/tenant; không lộ title, owner, secret của đối tượng không được phép; hạn chế field nhạy cảm.
3. **State change:** thao tác được phép thực sự đổi dữ liệu; thao tác bị từ chối không đổi database, storage, cache hoặc thông điệp phát đi.
4. **Boundary behavior:** route, method, tenant, ID, nested ID, role/scope và các biến thể của request phải được phân quyền cùng chính sách.

Ví dụ:

~~~text
Test ID: AUTH-DOC-UPDATE-BOB-101
Actor: bob (tenant=east, role=USER)
Resource: document/101 (owner=alice, tenant=east)
Action: UPDATE; PATCH /api/documents/101
Request: {"title":"Unauthorized overwrite"}
Expected: HTTP 403
Invariant: title của document 101 vẫn là "Alice plan"
Rationale: Bob không sở hữu 101, không có EDITOR/ADMIN
~~~

**Một response 403 không đủ chứng minh không có lỗi bảo mật.** Nếu service đã ghi DB rồi mới ném exception, status có thể đúng nhưng dữ liệu đã thay đổi. Đặc biệt kiểm tra side effect với DELETE, chuyển ownership, thanh toán, phê duyệt, grant quyền, gửi email và phát event.

## 5. Ví dụ ứng dụng có thể chạy: chính sách và tài nguyên

Ví dụ sau cho phép chạy trực tiếp các test ma trận bằng `mvn test`. Kho dữ liệu là `ConcurrentHashMap` cố ý đơn giản để tập trung vào **test design** và chính sách; không giả làm cơ chế isolation/transaction của database production.

**Yêu cầu:** JDK 17+, Maven 3.9+, Spring Boot 3.5.0 (kéo Spring Security 6.5.x qua BOM). Dùng mật khẩu mẫu `pw` chỉ để test.

Cấu trúc:

~~~text
authorization-matrix-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/matrix/
    │   ├── AuthorizationMatrixApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentService.java
    │   ├── DocumentController.java
    │   └── ReportController.java
    └── test/java/com/example/matrix/
        └── AuthorizationMatrixTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>authorization-matrix-demo</artifactId>
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

### 5.2. AuthorizationMatrixApplication.java

~~~java
package com.example.matrix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationMatrixApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.matrix;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Giữ CSRF protection mặc định cho PATCH/DELETE.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            user("alice", "USER"),
            user("bob", "USER"),
            user("carol", "EDITOR"),
            user("audrey", "AUDITOR"),
            user("admin", "ADMIN"),
            user("mallory", "ADMIN")
        );
    }

    private static org.springframework.security.core.userdetails.UserDetails
            user(String name, String role) {
        return User.withUsername(name)
            .password("{noop}pw")
            .roles(role)
            .build();
    }
}
~~~

**Cấu hình chỉ giải quyết authentication tại route.** `/api/**` yêu cầu đăng nhập, nhưng chưa hề nói người dùng nào được đọc document 101. Dữ liệu role từ `InMemoryUserDetailsManager` là server-owned; role `ADMIN` được hiểu trong **phạm vi tenant** do policy service kiểm soát.

CSRF vẫn bật theo mặc định. Với các request thay đổi trạng thái, test hợp lệ dùng `with(csrf())`. Nếu một test PATCH thiếu CSRF trả `403`, không thể kết luận chính sách UPDATE đã được kiểm tra: `CsrfFilter` có thể từ chối request trước.

### 5.4. DocumentService.java

Service demo định nghĩa chính sách ở một nơi có thể kiểm tra và trả dữ liệu sau khi quyền được quyết định. `tenant` được server gán từ bảng danh tính mẫu, không lấy từ `X-Tenant` hay JSON do client tự khai.

~~~java
package com.example.matrix;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private static final Map<String, String> USER_TENANTS = Map.of(
        "alice", "east",
        "bob", "east",
        "carol", "east",
        "audrey", "east",
        "admin", "east",
        "mallory", "west"
    );

    private final Map<Long, Document> documents = new ConcurrentHashMap<>();

    public DocumentService() {
        resetDemo();
    }

    // Dữ liệu fixture; test mặc định chạy tuần tự.
    public void resetDemo() {
        documents.clear();
        documents.put(101L,
            new Document(101L, "east", "alice", "Alice plan"));
        documents.put(202L,
            new Document(202L, "east", "bob", "Bob budget"));
        documents.put(303L,
            new Document(303L, "west", "mallory", "West plan"));
    }

    public DocumentView read(long id, Authentication auth) {
        Document doc = withinTenant(id, auth);
        boolean owner = doc.owner().equals(auth.getName());

        if (!owner && !has(auth, "EDITOR")
                && !has(auth, "AUDITOR") && !has(auth, "ADMIN")) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return view(doc);
    }

    public DocumentView rename(
            long id, String newTitle, Authentication auth) {
        Document doc = withinTenant(id, auth);
        boolean owner = doc.owner().equals(auth.getName());

        if (!owner && !has(auth, "EDITOR") && !has(auth, "ADMIN")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        if (newTitle == null || newTitle.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Document updated = new Document(
            doc.id(), doc.tenant(), doc.owner(), newTitle);
        documents.put(id, updated);
        return view(updated);
    }

    public void delete(long id, Authentication auth) {
        Document doc = withinTenant(id, auth);
        boolean owner = doc.owner().equals(auth.getName());

        if (!owner && !has(auth, "ADMIN")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        documents.remove(id);
    }

    public ReportView report(Authentication auth) {
        if (!has(auth, "AUDITOR") && !has(auth, "ADMIN")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        String tenant = tenantOf(auth);
        long count = documents.values().stream()
            .filter(doc -> doc.tenant().equals(tenant))
            .count();

        return new ReportView(tenant, count);
    }

    private Document withinTenant(long id, Authentication auth) {
        String trustedTenant = tenantOf(auth);
        Document doc = documents.get(id);
        if (doc == null || !doc.tenant().equals(trustedTenant)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return doc;
    }

    private static String tenantOf(Authentication auth) {
        if (auth == null || auth instanceof AnonymousAuthenticationToken
                || !auth.isAuthenticated()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String tenant = USER_TENANTS.get(auth.getName());
        if (tenant == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return tenant;
    }

    private static boolean has(Authentication auth, String role) {
        return auth != null && auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_" + role));
    }

    private static DocumentView view(Document doc) {
        return new DocumentView(doc.id(), doc.title());
    }

    private record Document(long id, String tenant,
                            String owner, String title) {}

    public record DocumentView(long id, String title) {}

    public record ReportView(String tenant, long documentCount) {}
}
~~~

**Các ranh giới bảo mật được thể hiện:**

- `withinTenant(...)` chạy trước mọi READ/UPDATE/DELETE; role ADMIN không bypass tenant.
- `read(...)` chỉ trả document nếu owner hoặc role được phép đọc; user khác chủ và thiếu quyền nhận 404.
- `rename(...)` và `delete(...)` kiểm tra quyền **trước khi ghi**. Cùng tenant mà thiếu UPDATE/DELETE nhận 403.
- `report(...)` vừa kiểm tra role vừa giới hạn dữ liệu thống kê theo tenant. Kiểm tra role mà quên lọc tenant vẫn là lỗi.
- Controller sẽ trả `DocumentView` gồm ID/title, không serialize toàn bộ đối tượng nội bộ. Production cần DTO giới hạn trường theo chính sách và tránh rò qua serialization.
- `resetDemo()` chỉ hỗ trợ fixture cho bài học; không tạo endpoint HTTP để user reset dữ liệu.

**Giới hạn có chủ đích:** Map in-memory không có tính chất giao dịch, khóa, phân tách dữ liệu hay độ bền như DB. Trong hệ thống thật, dùng query/mutation ràng buộc `tenant_id`, owner, quyền chia sẻ và action; kiểm tra concurrency, TOCTOU và transaction. Ví dụ dùng Map để làm rõ từng nhánh của ma trận thay vì phụ thuộc một DB ngoài.

### 5.5. DocumentController.java

~~~java
package com.example.matrix;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentService.DocumentView read(
            @PathVariable long id, Authentication authentication) {
        return service.read(id, authentication);
    }

    @PatchMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public DocumentService.DocumentView rename(
            @PathVariable long id,
            @RequestBody RenameRequest request,
            Authentication authentication) {
        return service.rename(id, request.title(), authentication);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable long id, Authentication authentication) {
        service.delete(id, authentication);
    }

    public record RenameRequest(String title) {}
}
~~~

**Không truyền `tenant`, `owner` hoặc `role` từ request vào service để quyết định quyền.** Controller nhận `Authentication` do Spring Security đã xác minh. `PATCH` chỉ cho phép sửa title; client không có đường tự thay owner hoặc tenant trong DTO.

### 5.6. ReportController.java

~~~java
package com.example.matrix;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final DocumentService service;

    public ReportController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/api/reports/summary")
    public DocumentService.ReportView summary(
            Authentication authentication) {
        return service.report(authentication);
    }
}
~~~

Báo cáo tách thành **một resource type khác** để ma trận kiểm thử không chỉ phủ document. `tenant` của báo cáo được xác minh phía server. Không có tham số `?tenant=west` cho caller tự chọn để xem dữ liệu người khác.

## 6. Tự động hóa toàn bộ ma trận bằng MockMvc và JUnit 5

Đặt file `src/test/java/com/example/matrix/AuthorizationMatrixTest.java`:

~~~java
package com.example.matrix;

import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMatrixTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService documents;

    @BeforeEach
    void freshFixture() {
        documents.resetDemo();
    }

    static Stream<Arguments> cases() {
        return Stream.of(
            // Document READ: anonymous / owner / same-tenant / role / cross-tenant
            Arguments.of("R01 anonymous GET 101",
                null, "GET", "/api/documents/101", 401),
            Arguments.of("R02 Alice owner GET 101",
                "alice", "GET", "/api/documents/101", 200),
            Arguments.of("R03 Bob non-owner GET 101",
                "bob", "GET", "/api/documents/101", 404),
            Arguments.of("R04 Carol editor GET 101",
                "carol", "GET", "/api/documents/101", 200),
            Arguments.of("R05 Audrey auditor GET 101",
                "audrey", "GET", "/api/documents/101", 200),
            Arguments.of("R06 East admin GET 101",
                "admin", "GET", "/api/documents/101", 200),
            Arguments.of("R07 West admin GET 101",
                "mallory", "GET", "/api/documents/101", 404),
            Arguments.of("R08 Bob owner GET 202",
                "bob", "GET", "/api/documents/202", 200),
            Arguments.of("R09 Alice GET missing ID",
                "alice", "GET", "/api/documents/999", 404),

            // Document UPDATE: valid csrf() isolates authorization.
            Arguments.of("U01 anonymous PATCH 101",
                null, "PATCH", "/api/documents/101", 401),
            Arguments.of("U02 Alice owner PATCH 101",
                "alice", "PATCH", "/api/documents/101", 200),
            Arguments.of("U03 Bob non-owner PATCH 101",
                "bob", "PATCH", "/api/documents/101", 403),
            Arguments.of("U04 Carol editor PATCH 101",
                "carol", "PATCH", "/api/documents/101", 200),
            Arguments.of("U05 Audrey auditor PATCH 101",
                "audrey", "PATCH", "/api/documents/101", 403),
            Arguments.of("U06 East admin PATCH 101",
                "admin", "PATCH", "/api/documents/101", 200),
            Arguments.of("U07 West admin PATCH 101",
                "mallory", "PATCH", "/api/documents/101", 404),

            // Document DELETE: same resource, different policy.
            Arguments.of("D01 anonymous DELETE 101",
                null, "DELETE", "/api/documents/101", 401),
            Arguments.of("D02 Alice owner DELETE 101",
                "alice", "DELETE", "/api/documents/101", 204),
            Arguments.of("D03 Bob non-owner DELETE 101",
                "bob", "DELETE", "/api/documents/101", 403),
            Arguments.of("D04 Carol editor DELETE 101",
                "carol", "DELETE", "/api/documents/101", 403),
            Arguments.of("D05 Audrey auditor DELETE 101",
                "audrey", "DELETE", "/api/documents/101", 403),
            Arguments.of("D06 East admin DELETE 101",
                "admin", "DELETE", "/api/documents/101", 204),
            Arguments.of("D07 West admin DELETE 101",
                "mallory", "DELETE", "/api/documents/101", 404),

            // Report READ: second resource type.
            Arguments.of("P01 anonymous REPORT",
                null, "GET", "/api/reports/summary", 401),
            Arguments.of("P02 Alice user REPORT",
                "alice", "GET", "/api/reports/summary", 403),
            Arguments.of("P03 Carol editor REPORT",
                "carol", "GET", "/api/reports/summary", 403),
            Arguments.of("P04 Audrey auditor REPORT",
                "audrey", "GET", "/api/reports/summary", 200),
            Arguments.of("P05 East admin REPORT",
                "admin", "GET", "/api/reports/summary", 200),
            Arguments.of("P06 West admin REPORT",
                "mallory", "GET", "/api/reports/summary", 200)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("cases")
    void authorizationMatrix(
            String caseName, String username, String method,
            String path, int expectedStatus) throws Exception {

        MockHttpServletRequestBuilder request = switch (method) {
            case "GET" -> get(path);
            case "PATCH" -> patch(path)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Revised\"}")
                .with(csrf());
            case "DELETE" -> delete(path).with(csrf());
            default -> throw new IllegalArgumentException(
                "Unsupported method: " + method);
        };

        if (username != null) {
            request.with(httpBasic(username, "pw"));
        }
        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void rejectedPatchMustNotChangeData() throws Exception {
        mvc.perform(patch("/api/documents/101")
                .with(httpBasic("bob", "pw"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Overwritten by Bob\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice plan"));
    }

    @Test
    void crossTenantAdminCannotDeleteOrReadDocument() throws Exception {
        mvc.perform(delete("/api/documents/101")
                .with(httpBasic("mallory", "pw"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice plan"));
    }

    @Test
    void allowedEditorPatchChangesState() throws Exception {
        mvc.perform(patch("/api/documents/101")
                .with(httpBasic("carol", "pw"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Approved edit\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Approved edit"));

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Approved edit"));
    }

    @Test
    void reportIsLimitedToAuthenticatedTenant() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("audrey", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenant").value("east"))
            .andExpect(jsonPath("$.documentCount").value(2));

        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("mallory", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenant").value("west"))
            .andExpect(jsonPath("$.documentCount").value(1));
    }

    @Test
    void missingCsrfCannotMutateEvenOwnersDocument() throws Exception {
        mvc.perform(patch("/api/documents/101")
                .with(httpBasic("alice", "pw"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No CSRF token\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice plan"));
    }
}
~~~

### Vì sao cách tổ chức test này có ích?

- `@SpringBootTest` và `@AutoConfigureMockMvc` chạy **Spring Security filter chain thật** trong Spring test context (không cần mở cổng TCP). Test đi qua HTTP mapping, authentication, CSRF, chính sách service và serialization.
- `httpBasic(username, "pw")` tạo credentials cho principal thật của fixture; không giả định rằng thay role trong unit test luôn mô phỏng đúng HTTP Basic.
- `@ParameterizedTest` biến 29 dòng trường hợp thành một test có tên và expected status độc lập. Mỗi dòng là một giao điểm **resource + action + subject**.
- `@BeforeEach` tạo fixture trước từng lần chạy, tránh DELETE trong một case làm thay đổi kết quả của case khác. Không bật parallel test cho fixture singleton này; hệ thống thật nên dùng database isolation/transaction hoặc fixture độc lập để chạy song song.
- `with(csrf())` ở PATCH/DELETE **không tắt** CSRF protection; nó mô phỏng client đã gửi token hợp lệ để kiểm tra authorization. Có một test riêng cố tình bỏ token.
- Ba test về mutation còn xác nhận **state invariant**: request bị từ chối không sửa/xóa dữ liệu; request hợp lệ cập nhật đúng dữ liệu.
- Test báo cáo xác minh dữ liệu `east=2` và `west=1`. Nếu logic trả tổng `3` cho mọi admin, test phát hiện rò rỉ phạm vi tenant dù status đều 200.

Trong code, `403` ở `PATCH` cho Bob và `404` ở `GET` cho Bob là policy đã quy định, không phải sự khác biệt tự sinh từ HTTP method. Nếu hợp đồng cần giấu sự tồn tại tài liệu cả khi UPDATE/DELETE, đổi policy sang 404 cho thiếu quyền cùng tenant và cập nhật cả expected matrix.

## 7. Chạy và đọc kết quả kiểm thử

Chạy trong thư mục `authorization-matrix-demo`:

~~~bash
mvn test
~~~

Nếu test thành công, Maven Surefire hiển thị BUILD SUCCESS và các bài test pass (chi tiết số lượng/format phụ thuộc phiên bản plugin). Nếu một case sai, JUnit chỉ rõ case index/tên, expected status và actual status. Đây là **kết quả mong đợi**, không khẳng định đã thực sự chạy trong tài liệu Markdown.

Có thể chạy ứng dụng để kiểm tra một số dòng **GET** bằng curl:

~~~bash
mvn spring-boot:run
~~~

~~~bash
curl -i -u alice:pw http://localhost:8080/api/documents/101
curl -i -u bob:pw http://localhost:8080/api/documents/101
curl -i -u carol:pw http://localhost:8080/api/documents/101
curl -i -u audrey:pw http://localhost:8080/api/reports/summary
curl -i -u mallory:pw http://localhost:8080/api/reports/summary
~~~

Kết quả rút gọn:

| Lệnh | Status dự kiến | Nội dung chính |
|---|---|---|
| Alice đọc doc101 | 200 | `{"id":101,"title":"Alice plan"}` |
| Bob đọc doc101 | 404 | Không lộ title/doc101 |
| Carol đọc doc101 | 200 | `{"id":101,"title":"Alice plan"}` |
| Audrey xem report | 200 | `{"tenant":"east","documentCount":2}` |
| Mallory xem report | 200 | `{"tenant":"west","documentCount":1}` |

Ví dụ này **không đưa workflow cấp CSRF token cho curl**; kiểm tra PATCH/DELETE bằng MockMvc với `with(csrf())` như mục 6. Gửi PATCH/DELETE thủ công mà thiếu token sẽ bị chặn, nên không thể dùng status 403 từ request đó để kết luận policy UPDATE/DELETE hoạt động.

Trên PowerShell, dùng `curl.exe` nếu lệnh `curl` bị ánh xạ thành `Invoke-WebRequest`. Bản demo dùng mật khẩu `{noop}` chỉ để học; không triển khai cấu hình này ra Internet.

## 8. Phủ kiểm thử đủ rộng nhưng không bùng nổ tổ hợp

Nếu có 20 resource types, 6 actions, 10 subject groups, 3 tenant relations và 4 trạng thái tài nguyên, tích Descartes sẽ có hàng nghìn trường hợp. Không phải mọi tổ hợp đều mang ý nghĩa hoặc cần một HTTP integration test riêng.

Thiết kế theo **rủi ro và ranh giới chính sách**:

1. **Bắt buộc có mỗi resource/action nhạy cảm:** READ, UPDATE, DELETE, EXPORT, SHARE, APPROVE, download file; ưu tiên dữ liệu riêng tư, tài chính, quyền quản trị.
2. **Mỗi nhánh policy phải có một case được phép và một case bị cấm.** Ví dụ nhánh owner, editor, auditor, admin, cross-tenant.
3. **Cross-user và cross-tenant phải có case đối nghịch:** Alice được đọc doc101 nhưng Bob không; Admin east được đọc doc101 nhưng Admin west không.
4. **Xác thực thất bại, anonymous, credentials sai:** dùng 401 theo cơ chế của API; phân biệt với 403 do thiếu quyền khi đã xác thực.
5. **Tài nguyên không tồn tại, trạng thái khóa/lưu trữ, soft-deleted:** bảo đảm không lộ dữ liệu hoặc vô tình cho phép thao tác.
6. **Với mutation, kiểm state sau request:** quyền bị từ chối phải đồng thời không ghi DB, phát event, gửi thông báo hoặc lưu file.
7. **Thử đường vào thay thế:** API list, search, export, query GraphQL, endpoint nested, file download, background job/service account; đừng chỉ test endpoint chính.

Có thể chia lớp kiểm thử:

| Lớp | Nên kiểm gì? | Điểm mạnh / giới hạn |
|---|---|---|
| Unit test policy | Truth table `canRead/canWrite`, tổ hợp role-owner-tenant, phủ nhánh | Rất nhanh; không chứng minh security filter hoặc HTTP mapping đã được bật |
| MVC/security integration | HTTP status, authentication, CSRF, route, service policy | Bắt sai filter config, rule order, mapping, response |
| DB integration | Query có tenant/owner predicate, số dòng UPDATE/DELETE, side effects thực | Bắt bypass trong repository/transaction; tốn setup hơn |
| E2E | Browser/client, cookie/session, headers, reverse proxy, nhiều account | Kiểm hành trình thực; chậm, dễ biến động |
| Security review/manual | IDOR/BOLA, token replay, endpoint ngoài ma trận, privilege escalation | Giúp tìm đường đi/thuộc tính chưa nằm trong test plan |

**Coverage nên đo theo policy branch và API surface**, không chỉ tỷ lệ dòng code chạy. 100% line coverage của `DocumentController` vẫn có thể bỏ sót hành vi Bob đọc tài liệu Alice. Test tốt nhất là test có **đối tượng, người gọi và expected behavior cụ thể**.

## 9. Xây ma trận từ yêu cầu theo một quy trình lặp được

### Bước 1 — Lập danh mục tài nguyên và thao tác

Từ OpenAPI, controllers, use cases và mô hình dữ liệu, xác định tất cả điểm truy cập. Ví dụ:

~~~text
Document:
  READ    GET    /api/documents/{id}
  UPDATE  PATCH  /api/documents/{id}
  DELETE  DELETE /api/documents/{id}

Report:
  READ    GET    /api/reports/summary
~~~

Sau này cần bổ sung CREATE, list/search, bulk, export, file, share/transfer owner và mọi đường dẫn admin nếu sản phẩm có. Đừng tự giới hạn test chỉ dựa trên ba route phổ biến khi API thật còn endpoint khác.

### Bước 2 — Chốt subject groups và quan hệ đối tượng

Với role-based và ownership-based authorization, chỉ ghi `USER/ADMIN` là chưa đủ. Ghi thêm các thuộc tính:

~~~text
actor = alice
authn = authenticated
role = USER
tenant = east
relationship(document 101) = OWNER
relationship(document 202) = SAME_TENANT_NON_OWNER
relationship(document 303) = OTHER_TENANT
~~~

Một actor có thể là owner của một đối tượng, non-owner của đối tượng khác. Nhóm "owner" là **quan hệ** cần xây từ fixture, không phải role cố định gắn sẵn cho người dùng.

### Bước 3 — Viết bảng quyết định policy trước test code

Đặt `ALLOW` / `DENY` theo yêu cầu nghiệp vụ; tiếp đó ánh xạ thành HTTP status và body/state invariant. Ví dụ:

~~~text
sameTenant? no  -> deny, 404
sameTenant? yes
    READ:   owner || EDITOR || AUDITOR || ADMIN
    UPDATE: owner || EDITOR || ADMIN
    DELETE: owner || ADMIN
Report READ: AUDITOR || ADMIN (tenant-scoped)
~~~

Lựa chọn `401`, `403`, `404` phải nhất quán với scheme xác thực, chính sách ẩn hiện tài nguyên và hợp đồng API. Không mặc nhiên mọi DENY đều là `403`.

### Bước 4 — Chuẩn hóa fixture và cách xác thực

Mỗi test cần biết document nào thuộc user/tenant nào, account nào có role nào. Tránh test dựa trên bản ghi ngẫu nhiên hoặc dữ liệu production. Fixture phải có **ít nhất hai principal cùng role nhưng khác ownership**, cộng với một principal quyền cao từ tenant khác.

Với JWT/OIDC, kiểm cả issuer, audience, expiry, scope và tenant mapping đã xác minh; không tự tạo token giả rồi suy ra production chấp nhận giống vậy. Với Basic demo, `httpBasic` là cách gửi credential vào filter chain thật.

### Bước 5 — Sinh test từ dữ liệu ma trận

Dùng `@MethodSource`, `@CsvSource` hoặc test factory phù hợp. Khi case rất nhiều, bảng dữ liệu có thể nằm trong fixture YAML/JSON đã được code review hoặc một DSL test, nhưng **nguồn quyết định policy** phải độc lập với code sản phẩm.

Cẩn thận: sinh expected từ chính `canRead(...)` của code đang test tạo **oracle vòng tròn**; nếu policy có bug, test cũng đồng ý với bug. Expected nên xuất phát từ decision table đã duyệt.

### Bước 6 — Thực thi, quan sát và cập nhật ma trận có kiểm soát

Gắn test ID với quy tắc hoặc yêu cầu; khi policy thay đổi, cập nhật tài liệu policy trước, đánh giá case bị ảnh hưởng, rồi đổi implementation/test. Nếu một test bị từ chối sai do CSRF, xác định đúng root cause thay vì nới quyền một cách tùy tiện.

## 10. Lỗi phổ biến khi kiểm thử phân quyền

1. **Chỉ dùng `@WithMockUser(roles="ADMIN")` cho mọi test.** Nó bỏ qua việc xác thực credentials và dễ che lỗi mapping group/tenant. Kết hợp test policy bằng mock principal với integration test dùng scheme thực.
2. **Test `200` cho owner mà không test non-owner.** BOLA chỉ lộ ra khi đổi **object ID** nhưng giữ nguyên principal.
3. **Chỉ kiểm `status().isForbidden()`.** Với mutation phải kiểm DB/cache/event không đổi. Trong demo, test đọc lại title sau PATCH bị từ chối.
4. **Không cấp CSRF cho unsafe method trong test.** Kết quả 403 có thể do `CsrfFilter`, không phải `AuthorizationManager`. Dùng `with(csrf())` để kiểm quyền và test thiếu/CSRF sai riêng.
5. **Gắn nghĩa "admin global" không có trong chính sách.** Nếu admin chỉ quản lý tenant, cross-tenant ADMIN phải bị từ chối.
6. **Tin `tenantId`, `ownerId` hoặc `role` do client gửi.** Test header/body giả mạo; server phải lấy từ identity/claims đã kiểm tra và policy server.
7. **Thiếu fixture của hai user cùng role.** Test role đơn thuần không bắt được lỗi owner.
8. **Kiểm detail an toàn nhưng quên list/search/export.** Query không lọc dữ liệu có thể lộ cả tenant qua danh sách, count, pagination hoặc cache.
9. **Chỉ test route đúng phương thức.** HTTP method khác, nested object, bulk ID hoặc endpoint legacy cũng có thể mở đường bypass.
10. **Test state dùng chung mà vẫn chạy song song.** Case DELETE ảnh hưởng case READ; test trở nên không quyết định. Dùng fixture cách ly hoặc transaction rollback cho DB test.
11. **Chỉ kiểm 404 cho cross-tenant mà không kiểm response body.** Error message chứa title/owner hoặc metadata có thể lộ dữ liệu.
12. **Nhầm method security với HTTP request security.** `@PreAuthorize` thường cần `@EnableMethodSecurity`; test `MockMvc` không tự chứng minh mọi service invocation qua job/event cũng an toàn.
13. **Tự động dùng `hasRole("USER")` thay ownership check.** Người dùng cùng role vẫn phải được phân biệt theo object và action.
14. **Coi `401 Unauthorized` là "thiếu role".** 401 nói về authentication/challenge; thiếu quyền của người đã xác thực thường 403 hoặc 404 theo chính sách.

## 11. Tiêu chí hoàn thành một ma trận kiểm thử có giá trị

Một ma trận đủ dùng cần trả lời được:

- Có danh mục tài nguyên/hành động nhạy cảm, kể cả bulk/export/file và đường thay thế hay chưa?
- Mỗi nhánh policy có **ít nhất một allowed và một denied case** chưa?
- Có thử cùng role khác owner, cùng owner khác action, admin khác tenant, anonymous và resource không tồn tại?
- Mỗi case có expected status, dữ liệu/không dữ liệu được phép trả và state invariant không?
- Có tách kiểm thử CSRF, authentication, role, object ownership, tenant và business state không?
- Fixture có xác định và cách ly được không? Dữ liệu đầu vào/expected có xuất phát từ policy độc lập không?
- Với request bị từ chối, có bằng chứng không ghi dữ liệu và không gửi side effect không?
- Với request được phép, có xác minh kết quả đúng và **chỉ** trong phạm vi được phép không?
- Khi chính sách thay đổi, có thể nhận ra hàng ma trận nào phải cập nhật không?

**Năng lực cần đạt:** bạn có thể lấy một endpoint Spring Security bất kỳ, xác định tài nguyên, thao tác, nhóm người dùng và quan hệ đối tượng; viết ma trận allow/deny trước khi chạy code; tự động hóa bằng MockMvc/parameterized tests; và phát hiện lỗi BOLA, role escalation, cross-tenant access, CSRF confusion và mutation bất hợp lệ.

## Tài liệu chính thức để đọc thêm

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — MockMvc integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [JUnit 5 — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
