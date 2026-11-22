# Kích hoạt @EnableMethodSecurity và các nhóm annotation trong Spring Security

> **Phạm vi:** Spring Security 6.5, Spring Boot 3.5.x, Java 17+, Servlet/Spring MVC. Bài học trình bày cách bật **method-level authorization**, phân loại **@PreAuthorize / @PostAuthorize / @PreFilter / @PostFilter**, **@Secured**, **@RolesAllowed / @PermitAll / @DenyAll**, giải thích proxy/AOP, cấu hình cờ và viết test để chứng minh chính sách thực sự được thực thi.

## 1. Tại sao cần method security?

Một HTTP rule có thể chỉ yêu cầu người dùng đăng nhập:

~~~java
// Fragment nằm trong http.authorizeHttpRequests(...):
.requestMatchers("/api/**").authenticated()
~~~

Nhưng cùng một service có thể được gọi từ nhiều controller hoặc các Spring beans khác. Method security bảo vệ **hành động của service**, không chỉ một đường dẫn:

~~~java
@Service
class InvoiceService {
    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approve(String invoiceId) {
        return "approved " + invoiceId;
    }
}
~~~

Đây là **fragment Spring**, không phải chương trình Java độc lập. Khi bật method security và gọi qua Spring proxy, người thiếu `invoice:approve` không được thực thi method. Spring Security có thể ném `AccessDeniedException` hoặc ngoại lệ con như `AuthorizationDeniedException`. Trong HTTP với một user đã xác thực, chúng thường thành **403 Forbidden**.

| Điểm kiểm tra | Mục đích | Ví dụ |
| --- | --- | --- |
| HTTP security | Giới hạn URL/method HTTP | `/api/**` yêu cầu authentication |
| Method security | Giới hạn lời gọi chức năng | `@PreAuthorize("hasRole('ADMIN')")` |
| Domain security | Giới hạn tài nguyên cụ thể | User thuộc tenant của invoice 42? |

**HTTP ALLOW không hủy method security.** Ngược lại, `@PermitAll` trên một service không vượt qua HTTP `authenticated()` nếu HTTP filter đã chặn request trước.

## 2. Bật method security: không tự bật với Spring Boot Starter Security

Spring Boot Starter Security bảo vệ web theo cấu hình HTTP, nhưng **không tự kích hoạt method authorization**. Bạn cần khai báo:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class SecurityMethodConfig {
}
~~~

Hoặc đặt `@EnableMethodSecurity` trực tiếp trên main class `@SpringBootApplication`. Trong cấu hình proxy thông thường, Spring Security đăng ký các method interceptors/advisors để xem annotation của Spring-managed methods.

### Ba nhóm và cờ bật/tắt

| Cờ trong `@EnableMethodSecurity` | Giá trị mặc định | Nhóm annotation |
| --- | :---: | --- |
| `prePostEnabled` | **true** | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` |
| `securedEnabled` | **false** | `@Secured` |
| `jsr250Enabled` | **false** | `@RolesAllowed`, `@PermitAll`, `@DenyAll` |

Các ví dụ **thay thế nhau**, không đặt cả bốn trên một class:

~~~java
@EnableMethodSecurity
// Pre/post mặc định.

@EnableMethodSecurity(securedEnabled = true)
// Pre/post + @Secured.

@EnableMethodSecurity(jsr250Enabled = true)
// Pre/post + JSR-250.

@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
// Cả ba nhóm.
~~~

**Điểm dễ quên:** `@EnableMethodSecurity(securedEnabled = true)` **vẫn bật nhóm pre/post**. Muốn chỉ `@Secured` thì chủ động đặt `prePostEnabled = false`. Nếu đặt cờ này trong hệ thống đang dùng `@PreAuthorize`, những rule pre/post có thể bị vô hiệu hóa.

### Import đúng package

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.annotation.Secured;

import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Với Spring Boot 3 / Spring Security 6, dùng namespace **`jakarta.annotation.security`**; không mặc nhiên dùng `javax.annotation.security` của thế hệ Spring Boot 2.

## 3. Bốn annotation pre/post và vị trí kiểm tra

### `@PreAuthorize` — xét trước khi chạy nghiệp vụ

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readReport() {
    return "report";
}
~~~

Expression SpEL được đánh giá trước khi gọi target method. Nếu DENY, nghiệp vụ không chạy qua proxy. Bạn có thể dùng `hasRole('ADMIN')`, `hasAuthority('report:read')`, `authentication.name`, tham số method và custom bean.

Ví dụ phức tạp hơn:

~~~java
@PreAuthorize("hasAuthority('invoice:approve') and @invoicePolicy.canApprove(authentication, #invoiceId)")
public void approveInvoice(String invoiceId) {
    // Thực hiện cập nhật sau khi đã được phép.
}
~~~

Đây là fragment, cần bean `invoicePolicy` với API tương ứng. Với SpEL `#invoiceId`, cấu hình biên dịch lưu tên tham số (thường `-parameters`) hoặc dùng `@P` khi cần.

**Không được nhầm `hasRole('ADMIN')` với literal `ADMIN`**: theo mặc định `hasRole('ADMIN')` kiểm authority `ROLE_ADMIN`; còn `hasAuthority('report:read')` đòi đúng chuỗi `report:read`.

### `@PostAuthorize` — xét sau khi có kết quả

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document findDocument(String id) {
    return repository.load(id);
}
~~~

`returnObject` là giá trị target method đã trả. Nó cho phép kiểm người gọi có phải owner của dữ liệu tải được không. Đây là fragment cần model và repository.

**Rủi ro:** method đã chạy **trước khi** hậu kiểm. `@PostAuthorize` không phù hợp làm hàng rào duy nhất cho method **ghi/xóa**, vì database hoặc side effect đã có thể bị thay đổi trước khi denial. Ưu tiên `@PreAuthorize` và domain checks cho các thao tác ghi.

### `@PreFilter` — lọc collection đầu vào

~~~java
@PreFilter("filterObject.owner == authentication.name")
public int countMine(List<Document> documents) {
    return documents.size();
}
~~~

`filterObject` là từng phần tử collection. Spring lọc trước khi target method xử lý. Nếu có nhiều collection parameters, chỉ rõ `filterTarget`. Ví dụ cần **danh sách mutable**, như `new ArrayList<>(...)`; `List.of(...)` bất biến không phù hợp khi framework cần loại bỏ phần tử.

### `@PostFilter` — lọc collection đầu ra

~~~java
@PostFilter("filterObject.owner == authentication.name")
public List<Document> visibleDocuments() {
    return new ArrayList<>(repository.findSome());
}
~~~

`@PostFilter` không nhất thiết DENY cả lời gọi; nó lọc các phần tử trả về. Phù hợp với ví dụ hoặc collection nhỏ. Với bảng dữ liệu lớn/multi-tenant, **lọc tại database/query** trước khi nạp, tránh tải dữ liệu trái quyền và gây lỗi phân trang.

### Phân biệt AUTHORIZE và FILTER

| Annotation | Đầu vào hay đầu ra? | Cho/từ chối cả lời gọi? |
| --- | --- | --- |
| `@PreAuthorize` | Trước chạy | Có |
| `@PostAuthorize` | Sau chạy | Có, dựa trên kết quả |
| `@PreFilter` | Collection tham số | Lọc phần tử |
| `@PostFilter` | Collection trả về | Lọc phần tử |

## 4. Nhóm `@Secured` (legacy)

`@Secured` hoạt động khi `securedEnabled = true`:

~~~java
@Secured("ROLE_MANAGER")
public String approveReview() {
    return "manager review";
}
~~~

Không viết biểu thức SpEL vào `@Secured`:

~~~java
// Sai về ý định:
@Secured("hasRole('MANAGER')")

// Đúng nếu dùng role prefix mặc định:
@Secured("ROLE_MANAGER")
~~~

Với nhiều role liệt kê, ý định thông thường là thỏa **ít nhất một** role, không phải yêu cầu AND nhiều điều kiện. Nếu cần kiểm tenant, owner, action và role, dùng `@PreAuthorize` + policy bean hoặc AuthorizationManager phù hợp.

**Test âm tính bắt buộc:** Nếu quên `securedEnabled = true`, người thiếu role có thể vẫn đi qua method. Một test chỉ chứng minh manager vào được 200 sẽ không phát hiện được lỗi đó.

## 5. Nhóm JSR-250/Jakarta: `@RolesAllowed`, `@PermitAll`, `@DenyAll`

Để kích hoạt nhóm này:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

Các annotation trong Boot 3:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Ví dụ:

~~~java
@RolesAllowed("ADMIN")
public String auditSettings() { return "audit"; }

@PermitAll
public String help() { return "help"; }

@DenyAll
public String blocked() { return "blocked"; }
~~~

- `@RolesAllowed("ADMIN")` kiểm role ADMIN theo prefix mặc định, thường tương ứng `ROLE_ADMIN`.
- `@PermitAll` không thêm rào cản ở interceptor JSR-250; **không bỏ qua HTTP authentication, CSRF hoặc các interceptor khác**.
- `@DenyAll` từ chối theo chính sách JSR-250; **không có hiệu lực** nếu nhóm annotation này chưa được kích hoạt.

**So sánh ý định ADMIN**: `@PreAuthorize("hasRole('ADMIN')")`, `@Secured("ROLE_ADMIN")` và `@RolesAllowed("ADMIN")` có thể đưa ra kết quả tương ứng trong cấu hình prefix mặc định, nhưng cần các **cờ kích hoạt khác nhau**. Với custom role prefix/hierarchy, phải test từng consumer.

## 6. Spring AOP và self-invocation: tại sao annotation đôi khi không chạy?

Trong proxy mode thường gặp:

~~~text
Spring controller
       |
       v
Spring proxy của service
       |-- PreAuthorize, Secured, JSR-250 ... (nếu áp dụng)
       |-- DENY -> AccessDeniedException
       v
Target service method
       |-- PostAuthorize / PostFilter ... (nếu áp dụng)
       v
Caller nhận kết quả
~~~

Sơ đồ chỉ nêu luồng chính, không phải đầy đủ thứ tự mọi advisor. Những trường hợp cần kiểm tra:

- **self-invocation:** `this.securedMethod()` trong cùng instance thường **không đi qua proxy**, có thể bỏ qua guard.
- Đối tượng tự tạo bằng `new Service()` không thuộc Spring ApplicationContext, không được proxy như bean.
- `private`/`final` method, class final hoặc loại proxy không phù hợp có thể không được intercept; thiết kế method proxyable và test.
- Method **không có annotation** không tự bị deny chỉ vì có `@EnableMethodSecurity`.
- `@Async` và công việc ở thread khác không mặc nhiên có đúng `SecurityContext`, cần propagation theo thiết kế.
- Annotation ở class/interface có cơ chế kế thừa và override; nhiều interface mang policy mâu thuẫn có thể khiến cấu hình không hợp lệ.

Một annotation cùng loại ở method có thể **override** annotation class-level tương ứng. Với nhiều **loại annotation khác nhau** trên một lời gọi, interceptor có thể đánh giá nối tiếp; yêu cầu mọi điều kiện áp dụng phải đạt. Đừng dùng hai `@PreAuthorize` lặp trên một method; dùng một biểu thức:

~~~java
@PreAuthorize("hasRole('MANAGER') and hasAuthority('task:approve')")
public String approveTask() {
    return "approved";
}
~~~

## 7. Ứng dụng Spring Boot Java 17+ minh họa cả ba nhóm

### Phụ thuộc và dữ liệu mẫu

Dùng Spring Boot **3.5.x / Java 17+**, Maven, với `spring-boot-starter-web` và `spring-boot-starter-security`; thêm test dependencies ở phần 9.

| User | Authorities từ UserDetailsService |
| --- | --- |
| Alice | `ROLE_USER` |
| Bob | `ROLE_MANAGER` |
| Carol | `ROLE_ADMIN` |
| Dave | `report:read` |

**Không cấu hình role hierarchy** trong demo: ADMIN không tự bao hàm MANAGER và USER. Nhờ đó kết quả kiểm tra từng nhóm annotation rõ ràng.

### Mã chạy đầy đủ

Tạo tệp **`src/main/java/com/example/methodsecurity/MethodSecurityApplication.java`**:

~~~java
package com.example.methodsecurity;

import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("MANAGER")
            .build();
        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();
        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .authorities("report:read")
            .build();
        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    public static final class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }
        public String getId() { return id; }
        public String getOwner() { return owner; }
    }

    @Service
    static class DocumentService {

        @PreAuthorize("hasRole('USER')")
        public String userArea() { return "user area"; }

        @PreAuthorize("hasAuthority('report:read')")
        public String reportArea() { return "report area"; }

        @Secured("ROLE_MANAGER")
        public String managerArea() { return "manager area"; }

        @RolesAllowed("ADMIN")
        public String adminArea() { return "admin area"; }

        @PermitAll
        public String help() { return "help"; }

        @DenyAll
        public String blocked() { return "must not be returned"; }

        @PostAuthorize("returnObject.owner == authentication.name")
        public Document readDocument(String id) {
            return new Document(id, "alice");
        }

        @PreFilter("filterObject.owner == authentication.name")
        public int countInput(List<Document> input) {
            return input.size();
        }

        @PostFilter("filterObject.owner == authentication.name")
        public List<Document> visibleDocuments() {
            return new ArrayList<>(List.of(
                new Document("a1", "alice"),
                new Document("b1", "bob"),
                new Document("a2", "alice")
            ));
        }

        public String noAnnotation() {
            return "no method annotation";
        }
    }

    @RestController
    static class Api {

        private final DocumentService service;
        Api(DocumentService service) { this.service = service; }

        @GetMapping("/public/ping")
        String ping() { return "pong"; }

        @GetMapping("/api/pre/user")
        String preUser() { return service.userArea(); }

        @GetMapping("/api/pre/report")
        String preReport() { return service.reportArea(); }

        @GetMapping("/api/secured/manager")
        String securedManager() { return service.managerArea(); }

        @GetMapping("/api/jsr/admin")
        String jsrAdmin() { return service.adminArea(); }

        @GetMapping("/api/jsr/permit")
        String jsrPermit() { return service.help(); }

        @GetMapping("/api/jsr/deny")
        String jsrDeny() { return service.blocked(); }

        @GetMapping("/api/post/document/{id}")
        Document document(@PathVariable("id") String id) {
            return service.readDocument(id);
        }

        @GetMapping("/api/filter/input")
        int filterInput() {
            List<Document> docs = new ArrayList<>(List.of(
                new Document("a1", "alice"),
                new Document("b1", "bob"),
                new Document("a2", "alice")
            ));
            return service.countInput(docs);
        }

        @GetMapping("/api/filter/output")
        List<Document> filterOutput() {
            return service.visibleDocuments();
        }

        @GetMapping("/api/no-annotation")
        String unannotated() { return service.noAnnotation(); }
    }
}
~~~

**Những gì ví dụ chứng minh:**

1. `@EnableMethodSecurity` trên main app đăng ký cả ba nhóm (pre/post, Secured, JSR-250).
2. HTTP chỉ yêu cầu `authenticated()` cho API. User đã đăng nhập còn phải qua method guard.
3. `DocumentService` được Spring quản lý. Controller **inject bean** và gọi qua proxy, không tự `new` hoặc `this.securedMethod()`.
4. Alice `ROLE_USER` qua `@PreAuthorize("hasRole('USER')")`; Dave `report:read` qua `@PreAuthorize("hasAuthority('report:read')")`.
5. Bob `ROLE_MANAGER` qua `@Secured("ROLE_MANAGER")`; Carol `ROLE_ADMIN` qua `@RolesAllowed("ADMIN")`.
6. `@PermitAll` ở service chỉ cho phép tại JSR-250, HTTP vẫn yêu cầu credential cho `/api/jsr/permit`.
7. `@DenyAll` chặn tất cả user, kể cả Carol.
8. `@PostAuthorize` chỉ cho caller nhận tài liệu nếu owner là Alice, sau khi method đã tạo kết quả.
9. `@PreFilter`/`@PostFilter` minh họa lọc phần tử theo `authentication.name`.
10. Method không annotation vẫn được thực thi đối với user đã đăng nhập — cần bảo vệ riêng nếu nhạy cảm.

Tất cả endpoint là **GET** nhằm tránh lẫn kết quả method authorization với CSRF của POST. Khi làm endpoint ghi thật, phải kiểm cả CSRF (tùy mô hình credential) và domain policy trước side effect.

## 8. Ma trận kết quả HTTP cần đạt

| Chủ thể | Pre USER | Pre report | Secured MANAGER | JSR ADMIN | JSR Permit | JSR Deny |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 | 401 | 401 | 401 |
| Alice — USER | **200** | 403 | 403 | 403 | **200** | 403 |
| Bob — MANAGER | 403 | 403 | **200** | 403 | **200** | 403 |
| Carol — ADMIN | 403 | 403 | 403 | **200** | **200** | 403 |
| Dave — report:read | 403 | **200** | 403 | 403 | **200** | 403 |

Cột tương ứng các URL `/api/pre/user`, `/api/pre/report`, `/api/secured/manager`, `/api/jsr/admin`, `/api/jsr/permit`, `/api/jsr/deny`. HTTP Basic thường trả 401 cho anonymous trên endpoint bảo vệ, 403 cho user đã xác thực nhưng thiếu quyền. Cấu hình form login có thể chuyển hướng 302.

| Endpoint | Alice | Bob | Carol |
| --- | --- | --- | --- |
| `/api/post/document/a1` | 200 | 403 | 403 |
| `/api/filter/input` | `2` | `1` | `0` |
| `/api/filter/output` | JSON 2 tài liệu | JSON 1 tài liệu | JSON rỗng |
| `/api/no-annotation` | 200 | 200 | 200 |

Không có role hierarchy, do đó ADMIN **không tự thừa kế** MANAGER/USER. Không tự suy đoán “admin có mọi quyền” nếu chưa khai báo đúng quan hệ.

### Chạy thử bằng curl

~~~bash
# Khởi động Maven app ở root project:
./mvnw spring-boot:run

# Endpoint public:
curl -i http://localhost:8080/public/ping

# Anonymous không đi qua HTTP authenticated():
curl -i http://localhost:8080/api/jsr/permit

# Pre/post group:
curl -i -u alice:demo123 http://localhost:8080/api/pre/user
curl -i -u bob:demo456 http://localhost:8080/api/pre/user
curl -i -u dave:demo000 http://localhost:8080/api/pre/report

# Legacy @Secured và JSR-250:
curl -i -u bob:demo456 http://localhost:8080/api/secured/manager
curl -i -u carol:demo789 http://localhost:8080/api/jsr/admin
curl -i -u carol:demo789 http://localhost:8080/api/jsr/deny

# Hậu kiểm owner và lọc kết quả:
curl -i -u alice:demo123 http://localhost:8080/api/post/document/a1
curl -i -u bob:demo456 http://localhost:8080/api/post/document/a1
curl -i -u alice:demo123 http://localhost:8080/api/filter/input
curl -i -u bob:demo456 http://localhost:8080/api/filter/output
~~~

Khi dùng Windows, có thể chạy `mvnw.cmd spring-boot:run`. Với các GET ALLOW, controller trả body như `user area`, `report area`, `manager area`, `admin area`, số lượng filter hoặc JSON document. Mật khẩu mẫu chỉ để học; môi trường thật phải dùng HTTPS và quản lý secret.

## 9. MockMvc: viết test bắt lỗi quên bật annotation

### Test dependencies

Trong `pom.xml`, các phần tử con của `<dependencies>`:

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

Nếu project đã có starter-test, không thêm trùng. Dùng các version tương thích do Spring Boot BOM quản lý.

### Test class hoàn chỉnh

Tạo tệp **`src/test/java/com/example/methodsecurity/MethodSecurityApplicationTests.java`**:

~~~java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        // user,password,path,expected status
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/jsr/permit,401",
        "anonymous,none,/api/pre/user,401",

        "alice,demo123,/api/pre/user,200",
        "alice,demo123,/api/pre/report,403",
        "alice,demo123,/api/secured/manager,403",
        "alice,demo123,/api/jsr/admin,403",
        "alice,demo123,/api/jsr/permit,200",
        "alice,demo123,/api/jsr/deny,403",

        "bob,demo456,/api/pre/user,403",
        "bob,demo456,/api/pre/report,403",
        "bob,demo456,/api/secured/manager,200",
        "bob,demo456,/api/jsr/admin,403",
        "bob,demo456,/api/jsr/permit,200",
        "bob,demo456,/api/jsr/deny,403",

        "carol,demo789,/api/pre/user,403",
        "carol,demo789,/api/pre/report,403",
        "carol,demo789,/api/secured/manager,403",
        "carol,demo789,/api/jsr/admin,200",
        "carol,demo789,/api/jsr/permit,200",
        "carol,demo789,/api/jsr/deny,403",

        "dave,demo000,/api/pre/user,403",
        "dave,demo000,/api/pre/report,200",
        "dave,demo000,/api/secured/manager,403",
        "dave,demo000,/api/jsr/admin,403",
        "dave,demo000,/api/jsr/permit,200",
        "dave,demo000,/api/jsr/deny,403"
    })
    void authorizationMatrix(
        String username, String password, String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder req = get(path);
        if (!"anonymous".equals(username)) {
            req.with(httpBasic(username, password));
        }
        mvc.perform(req).andExpect(status().is(expected));
    }

    @Test
    void postAuthorizeChecksOwner() throws Exception {
        mvc.perform(get("/api/post/document/a1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.id").value("a1"));

        mvc.perform(get("/api/post/document/a1")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void preFilterChangesInput() throws Exception {
        mvc.perform(get("/api/filter/input")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("2"));
        mvc.perform(get("/api/filter/input")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string("1"));
    }

    @Test
    void postFilterChangesOutput() throws Exception {
        mvc.perform(get("/api/filter/output")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.length()").value(2))
            .andExpect(jsonPath("$[0].owner").value("alice"));

        mvc.perform(get("/api/filter/output")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.length()").value(1))
            .andExpect(jsonPath("$[0].id").value("b1"));
    }

    @Test
    void unannotatedDoesNotImplyDeny() throws Exception {
        mvc.perform(get("/api/no-annotation")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isOk())
            .andExpect(content().string("no method annotation"));
    }

    @Test
    void denyAllBlocksAdmin() throws Exception {
        mvc.perform(get("/api/jsr/deny")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectPasswordIs401() throws Exception {
        mvc.perform(get("/api/pre/user")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Những ca phát hiện sai cấu hình:**

- Nếu không bật `securedEnabled`, Alice có thể lọt vào `/api/secured/manager`: test 403 bắt lỗi.
- Nếu không bật `jsr250Enabled`, Bob có thể lọt vào `/api/jsr/admin` và Carol có thể vào `/api/jsr/deny`: test âm tính bắt lỗi.
- Nếu tắt `prePostEnabled`, các ca thiếu quyền trên `@PreAuthorize`/`@PostAuthorize` không còn bị chặn.
- Nếu `@PreFilter`/`@PostFilter` không chạy, số lượng và JSON trả về sai.
- Anonymous bị 401 dù method có `@PermitAll` vì HTTP guard vẫn yêu cầu xác thực.

Chạy:

~~~bash
# macOS/Linux
./mvnw test

# Windows
mvnw.cmd test
~~~

Đây là **kết quả mong đợi** của mã mẫu, không phải tuyên bố đã chạy test. Đánh giá bằng kết quả Maven/JUnit thực tế và exit code. Các endpoint đều là GET, nên trong demo không cần token CSRF để phân biệt nguồn 403.

### Thử trực tiếp service bằng `@WithMockUser`

Có thể inject service proxy trong một Spring test và dùng:

~~~java
// Fragment trong test có Spring context:
@Autowired
MethodSecurityApplication.DocumentService service;

@Test
@WithMockUser(roles = "USER")
void userCanCallService() {
    assertEquals("user area", service.userArea());
}
~~~

Cần import `@WithMockUser` và `assertEquals`. Đây là **fragment**, không phải lớp test độc lập. Không dùng `new DocumentService()` để test method security, vì object tự tạo không qua proxy. `@WithMockUser` giả lập Authentication cho test method, còn `httpBasic` kiểm cả UserDetailsService/password mapping.

## 10. Kết hợp annotation, di trú và kiến trúc nhiều tầng

### Nhiều annotation cùng hiệu lực

Với method chỉ đọc, có thể cần cả permission và owner:

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public Document readOne(String id) {
    return repository.load(id);
}
~~~

Đây là fragment yêu cầu repository và Document thật. `@PreAuthorize` kiểm trước, `@PostAuthorize` kiểm sau, và cả hai điều kiện đều phải qua. Không lặp **hai `@PreAuthorize`** trên cùng method: dùng một SpEL biểu thức với `and` hoặc delegate sang bean policy.

### Di trú `@EnableGlobalMethodSecurity`

Spring Security hiện đại thay `@EnableGlobalMethodSecurity` bằng `@EnableMethodSecurity`, sử dụng API `AuthorizationManager` và Spring AOP advisors trực tiếp hơn:

~~~java
// Cũ:
@EnableGlobalMethodSecurity(prePostEnabled = true)

// Mới:
@EnableMethodSecurity
~~~

Trường hợp cũ **chỉ bật @Secured**:

~~~java
// Cũ:
@EnableGlobalMethodSecurity(securedEnabled = true)

// Mới: giữ nguyên chủ ý chỉ @Secured:
@EnableMethodSecurity(
    securedEnabled = true,
    prePostEnabled = false
)
~~~

Đây là các **fragment cấu hình thay thế nhau**. Migration phải kiểm lại cờ, role prefix, method expression handler, các custom voter/manager, AOP proxy và các test DENY.

### Một số khả năng nâng cao

Spring Security 6.5 hỗ trợ thêm meta-annotation (ví dụ tự định nghĩa `@CanReadInvoice` dựa trên `@PreAuthorize`), custom authorization beans, `@AuthorizeReturnObject` để bảo vệ property của object được trả về và `@HandleAuthorizationDenied` để xử lý tình huống bị từ chối theo API hỗ trợ. Chúng hữu ích cho nghiệp vụ cụ thể nhưng **không thay** các nhóm cơ bản hoặc nguyên tắc least privilege.

## 11. Checklist triển khai và các lỗi phổ biến

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Chỉ thêm `@PreAuthorize` mà quên `@EnableMethodSecurity` | Method có thể không được kiểm | Bật method security, test 403 |
| Quên `securedEnabled=true` | `@Secured` bị bỏ qua | Bật opt-in |
| Quên `jsr250Enabled=true` | `@RolesAllowed`/`@DenyAll` bị bỏ qua | Bật opt-in |
| Bật `prePostEnabled=false` không chủ đích | `@PreAuthorize`/filters ngưng hoạt động | Rà lại cấu hình |
| Nhầm Jakarta và Javax trong Boot 3 | Lỗi migration/build/annotation | Sử dụng đúng package |
| Method tự gọi `this.secured()` | **self-invocation** bỏ proxy | Dùng Spring bean proxy |
| Object do `new` tạo | Không có interceptor | Inject bean |
| Dùng `private`/`final` không phù hợp | Proxy có thể không chặn | Bảo đảm method interceptable |
| Dùng `@PostAuthorize` trên thao tác ghi | Side effect có thể đã xảy ra | Preauthorize trước khi ghi |
| Dùng `@PostFilter` lọc dữ liệu lớn | Tốn bộ nhớ, lỗi phân trang | Lọc tại DB/query |
| `@PermitAll` nhưng HTTP yêu cầu auth | Anonymous vẫn bị 401 | Hiểu nhiều tầng |
| Chỉ test ALLOW | Không thấy lỗ hổng cấp quyền | Viết negative tests |
| Bỏ qua tenant/owner | Rủi ro IDOR/BOLA | Domain-level policy |
| Thấy 403 trên POST rồi đoán thiếu role | Có thể do CSRF | Phân biệt filter và method |
| Không có fallback HTTP | Endpoint mới có thể lộ | Thiết kế default deny phù hợp |

**Checklist ngắn:** Bật đúng ba nhóm? Service là bean? Có proxy? Guard có đặt ở operation nhạy cảm? Test đủ 200/401/403? Có kiểm tra owner/tenant và CSRF cho thao tác ghi? Các role có prefix phù hợp? Các tác vụ nền có SecurityContext hợp lệ? Có test lại sau khi đổi annotation/configuration?

## 12. Tự kiểm tra

**Câu 1.** `@EnableMethodSecurity` mặc định bật nhóm nào?  
**Đáp án:** `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.

**Câu 2.** Cần bật gì để `@Secured` được kiểm?  
**Đáp án:** `securedEnabled = true`.

**Câu 3.** Cần bật gì cho `@RolesAllowed`, `@PermitAll`, `@DenyAll`?  
**Đáp án:** `jsr250Enabled = true`; trong Boot 3 dùng Jakarta namespace.

**Câu 4.** `@PostAuthorize` có bảo đảm side effect không xảy ra khi thiếu quyền không?  
**Đáp án:** Không. Method đã chạy trước khi hậu kiểm.

**Câu 5.** `@Secured("hasRole('ADMIN')")` có phải SpEL hợp lệ không?  
**Đáp án:** Không theo ý định; dùng `@Secured("ROLE_ADMIN")`.

**Câu 6.** `@PermitAll` ở method có bỏ qua HTTP `authenticated()` không?  
**Đáp án:** Không.

**Câu 7.** Tại sao `this.securedMethod()` nguy hiểm?  
**Đáp án:** Self-invocation có thể bỏ qua proxy/interceptor method security.

**Câu 8.** Khi `@PreFilter` nhận `List.of(...)` bất biến, có nên mặc định framework sửa được danh sách không?  
**Đáp án:** Không. Dùng collection mutable khi filter cần loại phần tử.

**Câu 9.** Test nào phát hiện `jsr250Enabled` chưa bật?  
**Đáp án:** Test user không phải admin bị 403 ở `@RolesAllowed`, và ngay cả admin cũng 403 ở `@DenyAll`.

**Câu 10.** Bật method security có làm toàn bộ method không annotation tự DENY không?  
**Đáp án:** Không. Phải thiết kế coverage ở HTTP/method/domain.

**Câu 11.** Vì sao cần cả test ALLOW và DENY?  
**Đáp án:** Một annotation không chạy có thể vẫn cho user đúng role 200; chỉ test người thiếu role bị 403 mới phát hiện thiếu guard.

**Câu 12.** Chuyển từ `@EnableGlobalMethodSecurity(securedEnabled=true)` sang `@EnableMethodSecurity(securedEnabled=true)` có giữ nguyên cờ mặc định không?  
**Đáp án:** Không nhất thiết. Annotation mới mặc định bật pre/post; nếu muốn chỉ `@Secured` cần `prePostEnabled=false`.

**Kết luận:** `@EnableMethodSecurity` là bước **kích hoạt**, còn các annotation chỉ có giá trị khi interceptor đã được đăng ký và lời gọi đi qua Spring AOP đúng cách. Pre/post mặc định bật, `@Secured` và JSR-250 cần opt-in. Tất cả phải được kiểm chứng bằng ma trận quyền **cho phép đúng / từ chối đúng**.

## Tài liệu chính thức

- Spring Security 6.5 — Method Security (annotation, proxy, migration): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — EnableMethodSecurity API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html
- Spring Security 6.5 — MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/
- Spring Security 6.5 — HTTP Basic test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security 6.5 — HTTP authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
