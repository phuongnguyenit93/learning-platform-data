# Tách quy tắc endpoint, chính sách nghiệp vụ và quyền đối với dữ liệu

## 1. Vấn đề cốt lõi: ba câu hỏi phân quyền khác nhau

Trong Spring Security, việc bảo vệ một URL bằng `authenticated()` hoặc `hasRole("USER")` **không tự ngăn** người đã đăng nhập thay ID trên URL để đọc dữ liệu người khác. Một bộ lọc bảo vệ endpoint cũng không thể quyết định tất cả điều kiện nghiệp vụ như “chỉ phê duyệt hóa đơn DRAFT”, “không tự duyệt yêu cầu do mình tạo” hoặc “chỉ truy cập dữ liệu cùng tenant”.

Thiết kế ứng dụng nên tách ba lớp:

1. **Quy tắc endpoint (HTTP/request authorization)**: ai được gọi HTTP method và URL nào? Dùng `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `hasRole`/`hasAuthority`, xác thực và CSRF.
2. **Chính sách nghiệp vụ (application/domain authorization)**: ai được thực hiện hành động nào trong trạng thái nghiệp vụ hiện tại? Dùng application service, policy object, `@PreAuthorize` hoặc `AuthorizationManager`; kết hợp quy tắc role, hạn mức, thời điểm, trạng thái và phân nhiệm.
3. **Quyền đối với dữ liệu (object/tenant authorization)**: người gọi được chạm tới **bản ghi cụ thể nào**? Dùng tenant/owner-scoped repository queries, kiểm quyền sở hữu/quan hệ trên resource, field-level output control và transaction/condition khi cập nhật.

Ví dụ:

- Alice đã đăng nhập gọi `GET /api/invoices/101`. Endpoint cho phép request authenticated nhưng service còn phải kiểm invoice 101 thuộc tenant Alice và Alice là owner hoặc có quyền đọc đặc biệt.
- Manager có role APPROVER gọi `POST /api/invoices/101/approve`. Endpoint đòi role và CSRF hợp lệ; service còn kiểm invoice cùng tenant, đang DRAFT và không vi phạm quy trình duyệt.
- Manager thuộc tenant A không được dùng role APPROVER để phê duyệt invoice tenant B.

**Đây là ba loại phép kiểm khác nhau, không chỉ là ba nơi để lặp cùng một câu `hasRole`.** Người học cần biết lớp nào sở hữu invariant nào, để giữ security policy nhất quán khi xuất hiện thêm REST endpoint, scheduler, message consumer hoặc batch job.

## 2. Bảng trách nhiệm theo ranh giới

| Tầng | Câu hỏi cần trả lời | Công cụ điển hình | Không nên chịu trách nhiệm |
| --- | --- | --- | --- |
| **HTTP security** | Request public hay protected? Method/path/role tối thiểu? | `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `anyRequest().denyAll()` | Tải nhiều bảng và tự quyết định workflow nghiệp vụ |
| **Controller** | Chuyển HTTP input đã parse cho application service như thế nào? | `@RestController`, `@PathVariable`, request DTO, `Authentication` | Lưu entity và lặp toàn bộ kiểm quyền ở mỗi endpoint |
| **Application service** | Actor có thể thực hiện action trong trạng thái hiện tại không? | `@PreAuthorize`, `@EnableMethodSecurity`, service/policy, transaction | Tin `ownerId`/`tenantId`/`isAdmin` do client tự khai |
| **Domain policy** | Owner/tenant/action/state thỏa bất biến gì? | Pure Java policy, rule methods, unit test | Phụ thuộc HTTP/cookie và status code |
| **Repository/data** | Truy vấn/sửa đúng tập record thuộc scope nào? | `findByIdAndTenantId`, `UPDATE ... WHERE tenant_id = ?`, database RLS nếu phù hợp | Suy tenant tin cậy từ header không được xác minh |
| **Response boundary** | Field nào được công bố cho audience này? | Response DTO, projection, field-level policy | Trả nguyên entity chứa secrets hoặc metadata nội bộ |

### Ví dụ nhận diện đúng loại lỗi

- Không login vẫn gọi được một API đáng ra protected: lỗi **endpoint policy**.
- User có APPROVER nhưng duyệt hóa đơn đã đóng hoặc vượt hạn mức: lỗi **business policy**.
- Alice đổi invoice ID để xem hóa đơn Bob: lỗi **object-level authorization (BOLA/IDOR)**.
- API đã kiểm object nhưng trả cả `internalNote` hoặc `paymentToken`: lỗi **property/data exposure**, cần response DTO và field authorization.

Một team dễ bỏ sót kiểm thử nếu dùng nhãn chung “đã làm authorization” mà không chỉ rõ loại đối tượng và hành động được bảo vệ.

## 3. Luồng xử lý từ request đến dữ liệu

```text
HTTP request
    │
    ▼
Spring Security FilterChainProxy
    ├─ authentication (Basic / session / Bearer ...)
    ├─ CSRF nếu policy yêu cầu
    └─ authorizeHttpRequests
           │ Không đạt -> 401 / 403 / redirect
           ▼
Controller
    └─ nhận id/DTO, truyền Authentication đến service
           ▼
Method security + application service
    ├─ @PreAuthorize cho action/authority
    ├─ giải quyết actor và tenant từ nguồn đã xác minh
    ├─ repository: truy vấn theo id + tenant
    ├─ owner/object policy, status, limit, separation of duties
    └─ ghi có điều kiện trong transaction
           │ Không đạt -> 403 / 404 / 409 (theo hợp đồng)
           ▼
Response DTO đã loại bỏ field nhạy cảm
           ▼
HTTP response
```

Thứ tự có chủ ý: **HTTP rule chặn sớm**, service kiểm các invariant có giá trị dù không có HTTP, repository giảm phạm vi dữ liệu từ đầu, còn response DTO giới hạn những gì rời khỏi hệ thống. Không dùng độ khó đoán của ID/UUID để thay phân quyền.

## 4. Lớp HTTP: cấu hình cơ chế chuẩn, không nhồi logic dữ liệu vào filter

Một mẫu `HttpSecurity`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/invoices/*")
        .authenticated()
    .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
        .hasRole("APPROVER")
    .anyRequest().denyAll())
```

Đây là **fragment trong `SecurityFilterChain`**, không chạy độc lập. Nó quyết định:

- Public GET `/public` được cho phép.
- GET hóa đơn yêu cầu người dùng đã xác thực.
- POST approve yêu cầu authority `ROLE_APPROVER` (vì `hasRole("APPROVER")`).
- Những URL khác bị từ chối theo fallback `denyAll()`.

Nó **không biết** invoice ID có tồn tại không, thuộc tenant nào, owner là ai hay đã được APPROVED. Vì vậy dùng `hasRole("APPROVER")` ở đây là **coarse-grained permission**, không phải kết luận cuối cùng để sửa bất kỳ record nào.

Khi dùng Spring MVC, matcher có thể xét HTTP method, pattern và rule theo thứ tự. Trong ứng dụng dùng nhiều `SecurityFilterChain`, `securityMatcher` chọn chain áp dụng còn `requestMatchers` chọn rule trong chain. Tránh cấu hình các chain không có fallback khiến request không được bảo vệ.

**Nhầm lẫn quan trọng:** `permitAll()` bỏ điều kiện authorization cho matcher, **không** nói rằng mọi CSRF, security header hay authentication filter trong chain đều bị bỏ. Còn `web.ignoring()` có thể khiến request bỏ qua cả chuỗi security; không dùng ignoring để chữa 401/403 bừa bãi.

## 5. Lớp nghiệp vụ: kiểm quyền thực hiện hành động, không chỉ quyền gọi URL

Ví dụ yêu cầu: “Người có quyền APPROVER được duyệt hóa đơn cùng tenant nếu trạng thái DRAFT”. Điều kiện có thể biểu diễn:

```text
canApprove =
    actor được xác thực
    AND actor có role/permission APPROVER
    AND invoice thuộc tenant actor được phép
    AND invoice.status == DRAFT
    AND không vi phạm quy tắc phân nhiệm/hạn mức
```

Dùng `@EnableMethodSecurity` và annotation tại service là một lựa chọn:

```java
@PreAuthorize("hasRole('APPROVER')")
public InvoiceView approve(long invoiceId, Authentication actor) {
    // Phần thân vẫn phải kiểm tenant, trạng thái và update có điều kiện.
}
```

Đoạn này là **fragment**, không phải file chạy độc lập. `@PreAuthorize` yêu cầu quyền trước khi method được chạy qua Spring AOP proxy; nó không tự biết invoice DRAFT hoặc tenant. Nếu service được gọi từ controller khác, `@PreAuthorize` vẫn có ích; nhưng **self-invocation** (method trong cùng bean gọi `this.approve(...)`) có thể bỏ qua proxy. Không lấy annotation làm biện pháp duy nhất bảo vệ invariant khi các lời gọi không qua proxy.

Các chính sách nghiệp vụ khác gồm: hạn mức tiền, hạn mức số lần, người tạo không được duyệt chính mình, hành động chỉ cho người đã xác minh email, action hợp lệ theo state machine, kiểm quyền tại thời điểm ghi và quy tắc “hai người phê duyệt”. Với trường hợp phức tạp, tách policy thành đối tượng Java có unit tests; tránh biểu thức SpEL dài chứa nhiều truy vấn DB trong HTTP filter.

## 6. Lớp dữ liệu: BOLA/IDOR, tenant, owner và phạm vi truy vấn

**Broken Object Level Authorization (BOLA)** xảy ra khi API cho phép nhận ID đối tượng do client kiểm soát nhưng không xác minh actor có quyền với **ID cụ thể đó**. Alice có thể gọi một endpoint hợp lệ, thay `/101` thành `/102` và nhận dữ liệu của Bob.

Cách phòng thủ quan trọng là giới hạn repository bằng **tenant scope đã được xác minh**:

```java
// Chữ ký minh họa cho Spring Data JPA repository.
Optional<InvoiceEntity> findByIdAndTenantId(
        Long id, String tenantId);
```

Đây chỉ là fragment: `InvoiceEntity` phải là entity thật trong ứng dụng JPA. Với user cùng tenant, vẫn cần **owner hoặc quyền tương đương**. Tenant scope giúp cách ly tổ chức, còn owner/access policy cách ly tài nguyên của các user trong cùng tổ chức.

**Nguồn tenant không được do client tự cấp quyền:** header `X-Tenant-Id` hoặc field JSON `tenantId` có thể mô tả tenant đang yêu cầu, nhưng server phải đối chiếu user với membership và role tại tenant ấy. Với JWT, claims phải đến từ issuer đáng tin và được xác minh chữ ký/issuer/audience theo policy; đừng decode Base64 rồi tin giá trị.

**404 và 403:** có thể chọn 404 cho record ngoài tenant để không xác nhận sự tồn tại; 403 cho record cùng tenant nhưng thiếu owner/role. Đây là quyết định contract, cần nhất quán cả error body và timing. ID khó đoán không thay kiểm quyền.

## 7. Ví dụ Java 17+ runnable: tách ba lớp bằng một API hóa đơn

Dự án dùng **Spring Boot 3.5.7, Spring Security 6.x, Spring MVC, Java 17+**. In-memory repository thay database để tập trung vào phân lớp. HTTP Basic hỗ trợ thử nhanh; giữ CSRF cho `POST`. Không dùng tài khoản demo hoặc HTTP plain-text trong production.

### 7.1. Actor và dữ liệu mẫu

| Principal / mật khẩu demo | Authority | Tenant |
| --- | --- | --- |
| `alice / alice-pass` | `ROLE_USER` | tenant-a |
| `clara / clara-pass` | `ROLE_USER` | tenant-a |
| `bob / bob-pass` | `ROLE_USER` | tenant-b |
| `manager / manager-pass` | `ROLE_APPROVER` | tenant-a |

| Invoice ID | Owner | Tenant | Status |
| --- | --- | --- | --- |
| 101 | alice | tenant-a | DRAFT |
| 102 | bob | tenant-b | DRAFT |
| 103 | clara | tenant-a | DRAFT |
| 104 | clara | tenant-a | APPROVED |

Chính sách demo:

- `GET /public` không cần đăng nhập.
- `GET /api/invoices/{id}` cần đăng nhập. Owner được đọc invoice trong tenant của mình; APPROVER được đọc invoice cùng tenant.
- `POST /api/invoices/{id}/approve` cần APPROVER, cùng tenant, invoice DRAFT và CSRF token hợp lệ.
- `anyRequest().denyAll()` làm fallback.

Alice có thể đọc 101, **không** đọc 103 dù cùng tenant, càng không đọc 102 của tenant-b. Manager có quyền đọc/approve invoice cùng tenant-a nhưng không xuyên tenant-b.

### 7.2. Cấu trúc tệp

```text
security-layers/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── SecurityLayersApplication.java
    │   └── InvoiceAccessPolicy.java
    └── test/java/demo/
        ├── InvoiceAccessPolicyTest.java
        └── SecurityLayersIntegrationTest.java
```

### 7.3. `pom.xml` — có đầy đủ plugin wrapper

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-layers</artifactId>
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
```

### 7.4. Policy thuần Java: `InvoiceAccessPolicy.java`

```java
package demo;

public final class InvoiceAccessPolicy {

    private InvoiceAccessPolicy() {}

    public static boolean canRead(
            String actorTenant,
            String invoiceTenant,
            String actorUsername,
            String invoiceOwner,
            boolean approverRole) {

        if (actorTenant == null || invoiceTenant == null
                || actorUsername == null || invoiceOwner == null) {
            return false;
        }

        return actorTenant.equals(invoiceTenant)
                && (actorUsername.equals(invoiceOwner) || approverRole);
    }
}
```

Policy **không phụ thuộc Spring hay HTTP** nên có thể unit test dễ dàng. `approverRole` phải được service tính từ `Authentication` đã được Spring Security xác minh, không nhận từ JSON của client.

### 7.5. Ứng dụng chính: `SecurityLayersApplication.java`

```java
package demo;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
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
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityLayersApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLayersApplication.class, args);
    }

    // Endpoint policy: không truy vấn invoice/tenant ở đây.
    @Bean
    SecurityFilterChain httpRules(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/invoices/*")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/invoices/*/approve")
                            .hasRole("APPROVER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER").build(),
                User.withUsername("clara")
                        .password(encoder.encode("clara-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER").build(),
                User.withUsername("manager")
                        .password(encoder.encode("manager-pass"))
                        .roles("APPROVER").build());
    }

    public record Actor(String username, String tenantId) {}
    public enum InvoiceStatus { DRAFT, APPROVED }
    public record Invoice(
            long id, String tenantId, String ownerUsername,
            long amountCents, InvoiceStatus status) {}
    public record InvoiceView(
            long id, long amountCents, String status) {}

    @Service
    public static class ActorDirectory {
        // Demo: tenant map do server quản lý.
        public Actor require(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()) {
                throw new AccessDeniedException("Not authenticated");
            }
            String name = auth.getName();
            String tenant = switch (name) {
                case "alice", "clara", "manager" -> "tenant-a";
                case "bob" -> "tenant-b";
                default -> throw new AccessDeniedException(
                        "Unknown tenant membership");
            };
            return new Actor(name, tenant);
        }
    }

    @Repository
    public static class InvoiceRepository {
        private final ConcurrentHashMap<Long, Invoice> rows =
                new ConcurrentHashMap<>();

        public InvoiceRepository() {
            rows.put(101L, new Invoice(
                    101L, "tenant-a", "alice", 10000L,
                    InvoiceStatus.DRAFT));
            rows.put(102L, new Invoice(
                    102L, "tenant-b", "bob", 20000L,
                    InvoiceStatus.DRAFT));
            rows.put(103L, new Invoice(
                    103L, "tenant-a", "clara", 30000L,
                    InvoiceStatus.DRAFT));
            rows.put(104L, new Invoice(
                    104L, "tenant-a", "clara", 40000L,
                    InvoiceStatus.APPROVED));
        }

        public Optional<Invoice> findByIdInTenant(
                long id, String tenant) {
            return Optional.ofNullable(rows.get(id))
                    .filter(inv -> inv.tenantId().equals(tenant));
        }

        public boolean approveDraftInTenant(
                long id, String tenant) {
            AtomicBoolean changed = new AtomicBoolean(false);
            rows.computeIfPresent(id, (key, previous) -> {
                if (!previous.tenantId().equals(tenant)
                        || previous.status() != InvoiceStatus.DRAFT) {
                    return previous;
                }
                changed.set(true);
                return new Invoice(
                        previous.id(),
                        previous.tenantId(),
                        previous.ownerUsername(),
                        previous.amountCents(),
                        InvoiceStatus.APPROVED);
            });
            return changed.get();
        }
    }

    @Service
    public static class InvoiceService {
        private final InvoiceRepository repo;
        private final ActorDirectory directory;

        public InvoiceService(
                InvoiceRepository repo, ActorDirectory directory) {
            this.repo = repo;
            this.directory = directory;
        }

        @PreAuthorize("isAuthenticated()")
        public InvoiceView read(
                long id, Authentication auth) {
            Actor actor = directory.require(auth);
            Invoice invoice = repo.findByIdInTenant(
                    id, actor.tenantId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND));

            boolean approver = auth.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_APPROVER".equals(
                            a.getAuthority()));

            if (!InvoiceAccessPolicy.canRead(
                    actor.tenantId(), invoice.tenantId(),
                    actor.username(), invoice.ownerUsername(),
                    approver)) {
                throw new AccessDeniedException(
                        "Access denied to invoice");
            }
            return toView(invoice);
        }

        @PreAuthorize("hasRole('APPROVER')")
        public InvoiceView approve(
                long id, Authentication auth) {
            Actor actor = directory.require(auth);
            Invoice current = repo.findByIdInTenant(
                    id, actor.tenantId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND));

            if (current.status() != InvoiceStatus.DRAFT) {
                throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Invoice is not in DRAFT state");
            }

            if (!repo.approveDraftInTenant(
                    id, actor.tenantId())) {
                throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Invoice changed concurrently");
            }

            Invoice updated = repo.findByIdInTenant(
                    id, actor.tenantId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND));
            return toView(updated);
        }

        private static InvoiceView toView(Invoice invoice) {
            return new InvoiceView(
                    invoice.id(),
                    invoice.amountCents(),
                    invoice.status().name());
        }
    }

    @RestController
    public static class InvoiceController {
        private final InvoiceService service;

        public InvoiceController(InvoiceService service) {
            this.service = service;
        }

        @GetMapping("/public")
        public String publicPage() {
            return "public";
        }

        @GetMapping("/api/invoices/{id}")
        public InvoiceView read(
                @PathVariable long id,
                Authentication auth) {
            return service.read(id, auth);
        }

        @PostMapping("/api/invoices/{id}/approve")
        public InvoiceView approve(
                @PathVariable long id,
                Authentication auth) {
            return service.approve(id, auth);
        }
    }
}
```

### 7.6. Giải thích theo từng tầng

**HTTP filter:** `httpRules` áp method/path/role chung, chưa hề đọc tenant hoặc invoice. `httpBasic` dùng provider và encoder chuẩn; user demo được encode trong `UserDetailsService`. `formLogin` tắt riêng để response API thử bằng curl có challenge Basic; CSRF vẫn bật.

**Business service:** `@EnableMethodSecurity` kích hoạt `@PreAuthorize` trên Spring-managed `InvoiceService`. `approve` yêu cầu APPROVER, kiểm trạng thái DRAFT và chỉ cập nhật khi repository còn giữ trạng thái đó; trả 409 nếu trạng thái đã thay đổi. Service policy không phụ thuộc một controller duy nhất.

**Data scope:** `ActorDirectory` giải quyết tenant từ principal đã xác thực và mapping phía server. Repository lọc theo `id + tenant`. `InvoiceAccessPolicy` tiếp tục yêu cầu cùng tenant và (owner hoặc APPROVER). Approver tenant A không vượt phạm vi tenant B.

**Cập nhật đồng thời:** `ConcurrentHashMap.computeIfPresent` có logic kiểm tenant/status trong cùng phép cập nhật atomic của map. Đây là mô phỏng để thấy tinh thần *check and write atomically*; database thực cần transaction, conditional SQL hoặc optimistic locking, không dùng map làm persistence production.

**DTO đầu ra:** `InvoiceView` chỉ có ID, số tiền và trạng thái. Không trả entity nội bộ hay tenant/owner một cách tự động.

**Mật khẩu và CSRF:** password demo chỉ để học, production phải dùng TLS và store bí mật phù hợp. Khi dùng trình duyệt với Basic hoặc cookie session, CSRF không thể bỏ qua theo cảm tính; bài giữ CSRF và kiểm POST bằng Spring Security Test.

## 8. Unit test: policy trước khi viết controller

`src/test/java/demo/InvoiceAccessPolicyTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class InvoiceAccessPolicyTest {

    @Test
    void ownerMayReadSameTenant() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                "alice", "alice", false)).isTrue();
    }

    @Test
    void sameTenantDoesNotGrantAllObjects() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                "alice", "clara", false)).isFalse();
    }

    @Test
    void approverCanReadWithinTenant() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                "manager", "clara", true)).isTrue();
    }

    @Test
    void approverCannotCrossTenantBoundary() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-b",
                "manager", "bob", true)).isFalse();
    }

    @Test
    void missingPrincipalFailsClosed() {
        assertThat(InvoiceAccessPolicy.canRead(
                "tenant-a", "tenant-a",
                null, "alice", true)).isFalse();
    }
}
```

Với `InvoiceAccessPolicy` thuần Java, unit tests phát hiện ngay việc nhầm `sameTenant || approver` thành quyền vượt tenant. Nhưng chúng **chưa** chứng minh controller/service thực sự gọi policy hoặc security filters đã được gắn; cần integration tests.

## 9. Integration test: kiểm HTTP, service method và object scope

`src/test/java/demo/SecurityLayersIntegrationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityLayersIntegrationTest {

    @Autowired MockMvc mvc;

    @Autowired
    SecurityLayersApplication.InvoiceService service;

    @Test
    void publicEndpointAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadInvoice() throws Exception {
        mvc.perform(get("/api/invoices/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordRejected() throws Exception {
        mvc.perform(get("/api/invoices/101")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerInvoice() throws Exception {
        mvc.perform(get("/api/invoices/101")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101));
    }

    @Test
    void aliceCannotReadClarasInvoiceInSameTenant()
            throws Exception {
        mvc.perform(get("/api/invoices/103")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotAccessAnotherTenant() throws Exception {
        mvc.perform(get("/api/invoices/102")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void managerCanReadWithinTenant() throws Exception {
        mvc.perform(get("/api/invoices/103")
                        .with(httpBasic("manager", "manager-pass")))
                .andExpect(status().isOk());
    }

    @Test
    void managerCannotCrossTenant() throws Exception {
        mvc.perform(get("/api/invoices/102")
                        .with(httpBasic("manager", "manager-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void ordinaryUserCannotApprove() throws Exception {
        mvc.perform(post("/api/invoices/103/approve")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void csrfStillProtectsStateChange() throws Exception {
        mvc.perform(post("/api/invoices/103/approve")
                        .with(httpBasic("manager", "manager-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void managerCannotApproveOtherTenant() throws Exception {
        mvc.perform(post("/api/invoices/102/approve")
                        .with(httpBasic("manager", "manager-pass"))
                        .with(csrf()))
                .andExpect(status().isNotFound());
    }

    @Test
    void alreadyApprovedInvoiceReturnsConflict() throws Exception {
        mvc.perform(post("/api/invoices/104/approve")
                        .with(httpBasic("manager", "manager-pass"))
                        .with(csrf()))
                .andExpect(status().isConflict());
    }

    @Test
    void managerMayApproveDraftWithinTenant() throws Exception {
        mvc.perform(post("/api/invoices/101/approve")
                        .with(httpBasic("manager", "manager-pass"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directServiceInvocationAlsoNeedsApproverRole() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

        assertThatThrownBy(() -> service.approve(103L, auth))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Ý nghĩa các kết quả:**

- 401 ở anonymous hoặc password sai: HTTP Basic authentication filter/provider xử lý.
- 403 cho Alice đọc invoice 103: cùng tenant nhưng không phải owner/approver; **data object policy** từ chối.
- 404 cho invoice 102 khi caller tenant-a: repository không làm lộ dữ liệu tenant-b.
- 403 cho Alice POST approve: coarse endpoint role check ngăn từ đầu.
- 403 cho Manager POST thiếu CSRF: `CsrfFilter` bảo vệ unsafe method.
- 409 cho invoice 104: business workflow không cho approve lại.
- 200 cho manager approve invoice 101: role + tenant + DRAFT + CSRF đều đạt.
- Test gọi trực tiếp `service.approve` với `@WithMockUser` USER trả `AccessDeniedException`: method security trên Spring bean được áp dụng kể cả khi không đi qua controller.

`@WithMockUser` không xác minh password; các request dùng `httpBasic()` là nhóm test authentication qua filters. Test `MockMvc` không mở port, nhưng vì Spring context và filter chain được nạp nên vẫn là integration test. Nếu cần kiểm socket thật, có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` với HTTP client — đó không phải browser test nếu không chạy browser engine.

Chỉ test approve invoice 101 làm thay đổi state; các test còn lại không giả định 101 vẫn DRAFT. Khi dùng DB thật hoặc chạy test song song, cần fixture/reset data, transaction và concurrency tests.

## 10. Chạy và đối chiếu status

Cần Java 17+ và Maven, thực hiện ở thư mục chứa `pom.xml`:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/security-layers-0.0.1-SNAPSHOT.jar
```

Trong terminal thứ hai:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/invoices/101
curl -i -u alice:alice-pass http://localhost:8080/api/invoices/101
curl -i -u alice:alice-pass http://localhost:8080/api/invoices/103
curl -i -u alice:alice-pass http://localhost:8080/api/invoices/102
curl -i -u manager:manager-pass http://localhost:8080/api/invoices/103
curl -i -u manager:manager-pass http://localhost:8080/api/invoices/102
```

Status mong đợi: **200, 401, 200, 403, 404, 200, 404**. JSON đọc invoice 101 trước khi duyệt có dạng:

```json
{
  "id": 101,
  "amountCents": 10000,
  "status": "DRAFT"
}
```

Nếu chạy POST approve bằng `curl` chỉ với Basic credentials **không có CSRF token**, kết quả là 403. Không tắt CSRF chỉ vì command demo không cung cấp token; test `.with(csrf())` trong Spring Security Test mô phỏng token hợp lệ. Ứng dụng thật cần chiến lược CSRF tùy cơ chế xác thực, client sử dụng cookie hay Bearer-only, và nguy cơ browser tự gửi credentials.

**Giới hạn chạy:** ví dụ lưu state trong `ConcurrentHashMap`, mất khi restart, không có DB migration, lockout hay audit. Đây là minh họa kiến trúc, không phải ứng dụng có thể triển khai production trực tiếp.

## 11. Chuyển sang database thật: truy vấn và cập nhật có điều kiện

Truy vấn phải lọc tenant ngay từ đầu:

```sql
SELECT id, tenant_id, owner_username, amount_cents, status
FROM invoice
WHERE id = :invoice_id
  AND tenant_id = :tenant_id;
```

Với workflow DRAFT → APPROVED, cập nhật nên ràng buộc điều kiện trong database:

```sql
UPDATE invoice
SET status = 'APPROVED'
WHERE id = :invoice_id
  AND tenant_id = :tenant_id
  AND status = 'DRAFT';
```

Các đoạn SQL là **mẫu khái niệm**, không phải code kết nối DB của demo trên. Giá trị `tenant_id` phải được resolve từ actor/issuer đã xác minh. Kiểm số hàng cập nhật: 0 có thể do ID không tồn tại, tenant sai hoặc state đã thay đổi; service chọn response 404/409 phù hợp.

Tại sao cần điều kiện ngay trong UPDATE? Vì một request có thể đọc DRAFT, sau đó request khác đã duyệt trước khi request thứ nhất ghi. **TOCTOU/race** sẽ làm sai bất biến nếu chỉ kiểm ở bộ nhớ. Dùng transaction, optimistic lock `@Version` hoặc conditional update tùy yêu cầu, và kiểm concurrency.

Đối với Spring Data JPA, repository có thể có `findByIdAndTenantId(...)`, projection và method update với `@Modifying`/`@Query`. Kiểm cả list, search, export, delete, batch update và nested sub-resources: **filter đúng ở GET by ID không đủ** nếu export trả dữ liệu toàn tenant khác. Với hệ thống đa tenant, database Row-Level Security là lớp bổ sung có giá trị nhưng đòi session/database context được thiết lập an toàn và không rò giữa pooled connections.

## 12. Actor, tenant, role: lấy nguồn quyền từ đâu?

- **Form/HTTP Basic:** provider xác minh password rồi tạo `Authentication`. Service có thể tra user ID và tenant memberships từ database server-side.
- **JWT Resource Server:** `JwtDecoder` phải xác minh signature, issuer, thời gian và audience khi policy yêu cầu; converter ánh xạ `scope`, `roles` hoặc claims được cho phép thành `GrantedAuthority`. Đừng base64-decode rồi tự tin token hợp lệ.
- **OIDC Login:** thông tin `issuer + sub` và user details/permissions cần liên kết với app account. Email hiển thị không luôn là khóa duy nhất ổn định.
- **Nhiều tenant:** nếu client chọn tenant mục tiêu qua URL/header, backend vẫn phải kiểm membership và quyền actor trong tenant đó. Header không phải bằng chứng quyền.
- **Service accounts/jobs:** cần principal và scope riêng, không tự gán ADMIN toàn hệ thống khi request không đến từ HTTP.

**Role không tự mang mọi quyền:** `ROLE_APPROVER` chỉ có ý nghĩa theo chính sách ứng dụng, không tự bao hàm `ROLE_USER` hoặc quyền mọi tenant. Nếu hệ thống muốn hierarchy hoặc kết hợp scopes, phải khai báo/test rõ. Đừng tự động union tất cả roles từ database và claims của IdP mà không xác định nguồn có thẩm quyền.

## 13. Method security: điểm mạnh và giới hạn

Spring Security cung cấp `@EnableMethodSecurity` để bật `@PreAuthorize`, `@PostAuthorize` và các cơ chế method authorization. Khi gọi method của một Spring-managed bean qua proxy, rule được đánh giá độc lập với route HTTP.

**Ưu điểm:** một service được gọi từ nhiều controller/adapter vẫn có security boundary; unit tests của policy và Spring method tests dễ kết hợp; có thể tạo annotation hoặc authorization manager riêng nếu cần.

**Giới hạn:**

- `@PreAuthorize("hasRole('APPROVER')")` chỉ biết authority, chưa biết invoice DRAFT/tenant nếu không cung cấp policy logic.
- Self-invocation cùng bean có thể bỏ qua proxy; các method private hoặc object tạo bằng `new` không tự nhận method security từ Spring.
- Khi logic gọi database hoặc external service trong expression quá phức tạp, khó quản lý performance và exception handling; cân nhắc tách policy/service chuyên trách.
- Method security không quyết định CSRF/CORS/security headers hoặc HTTP challenge; vẫn cần filter chain.
- Một exception từ service có thể được map thành 403 khi qua security filters, nhưng trong unit test thuần bạn cần assert exception/decision tương ứng.

Chọn **policy service thuần Java** khi có nhiều điều kiện business và cần test độc lập; chọn **AuthorizationManager** khi muốn tích hợp sâu hơn với cơ chế authorization chung. Không viết custom HTTP filter chỉ để truy vấn owner từ DB: việc này làm filter mang state/transaction của domain, tăng rủi ro và khó tái sử dụng.

## 14. Ma trận status và cách debug

| Trường hợp | Kết quả thường dùng | Tầng quyết định |
| --- | --- | --- |
| Anonymous GET invoice (HTTP Basic) | **401** | Authentication entry point |
| User hợp lệ thiếu APPROVER khi POST | **403** | Request/method authorization |
| Manager POST thiếu CSRF | **403** | CSRF filter |
| Invoice không tồn tại trong tenant hoặc nằm ở tenant khác | **404** | Tenant-scoped lookup |
| Cùng tenant nhưng user không có quyền đọc invoice ấy | **403** | Object policy |
| Approve invoice đã APPROVED | **409** | Business state |
| Đủ quyền, tenant, trạng thái và CSRF | **200** | Tất cả tầng đều cho phép |

Ở app dùng form login, anonymous có thể được **302 redirect** thay vì 401; API Bearer token có `WWW-Authenticate` và semantics riêng. Không đoán “403 chắc do role”: CSRF hoặc object permission cũng có thể gây 403. Khi debug, xác định tầng nào từ chối đầu tiên và test tái hiện nguyên nhân.

## 15. Những lỗi kiến trúc thường gặp

1. Chỉ dùng `authenticated()` rồi `findById(id)` → BOLA.
2. Chỉ dùng `hasRole("ADMIN")` rồi trả mọi record mọi tenant → vượt scope.
3. Tin `role`, `ownerId` hoặc `tenantId` từ request → caller có thể tự cấp quyền.
4. Dồn permission, domain state và SQL vào servlet filter → khó test, khó transaction.
5. Đưa policy vào mỗi controller bằng cách copy/paste → endpoint mới có thể quên.
6. Không bật `@EnableMethodSecurity` nhưng tưởng annotation luôn có hiệu lực.
7. Self-invocation bypass proxy → `@PreAuthorize` không được chạy.
8. Dùng `sameTenant || approver` thay vì `sameTenant && (owner || approver)`.
9. Kiểm status DRAFT trước nhưng UPDATE không có WHERE status → race/TOCTOU.
10. Chỉ lọc tenant ở GET, bỏ quên list/export/batch/delete.
11. Dùng ID khó đoán thay cho object authorization.
12. Trả trực tiếp JPA entity chứa PII, internal note hoặc secrets.
13. Dùng `permitAll` quá rộng làm fallback cho API mới.
14. Nhầm `hasRole("APPROVER")` với `hasAuthority("SCOPE_invoice.approve")`.
15. Chỉ test request success 200 mà thiếu owner khác/tenant khác/missing CSRF.
16. Sửa lỗi 403 bằng cách tắt CSRF hoặc xóa security chain.
17. Dùng mock principal rồi báo đã test password/JWT cryptography.
18. Log toàn bộ bearer tokens, password và session cookies để debug phân quyền.

## 16. Checklist code review và bài tập

Trước khi merge, tự kiểm:

- [ ] Endpoint có rule theo method/path và fallback deny-by-default phù hợp.
- [ ] Danh tính/role/tenant bắt nguồn từ authentication đáng tin hoặc server-side directory.
- [ ] Business action có invariant tại service, không chỉ UI/controller.
- [ ] Method security được bật đúng, gọi qua proxy và được test trực tiếp.
- [ ] Query có tenant/object scope; owner/permission được kiểm trên đúng record.
- [ ] List, export, update, delete, batch và nested object cũng được lọc.
- [ ] POST/PUT/DELETE có CSRF đúng kiểu client và không lộ dữ liệu nhạy cảm.
- [ ] State-changing operation có transaction và update điều kiện, xử lý race.
- [ ] Response DTO công bố đúng field, không trả entity/bí mật tự động.
- [ ] Có test 401, 403, 404, 409, token/password sai, tenant và owner khác.
- [ ] Audit có actor/action/object/result nhưng không lộ credentials.
- [ ] Khi role/tenant membership bị thu hồi, session/cache/token được refresh hoặc revoke theo thiết kế.

**Câu hỏi tự luyện:**

1. Vì sao `GET /api/invoices/102` có thể tạo BOLA dù endpoint đã dùng `authenticated()`?
2. Vì sao tenant-scoped query vẫn chưa đủ khi Alice và Clara cùng tenant nhưng không cùng owner?
3. Role APPROVER tenant-a có nên cho phép đọc tenant-b không? Viết biểu thức AND/OR đúng.
4. Khi nào `@PreAuthorize` bổ sung giá trị so với `requestMatchers`?
5. Nêu một lỗ hổng do self-invocation qua Spring AOP proxy và cách tổ chức service để tránh.
6. Vì sao kiểm DRAFT trong Java nhưng SQL UPDATE không ràng buộc trạng thái có thể sai khi có hai request đồng thời?
7. Header `X-Tenant-Id` có được coi là bằng chứng membership không?
8. Vì sao cần kiểm export/list API chứ không chỉ GET by ID?
9. Nêu test nào chứng minh 403 vì thiếu role và test nào chứng minh 403 vì object khác owner.
10. Chọn khi nào trả 404 thay vì 403 và rủi ro object existence enumeration là gì?
11. Tại sao service cần giữ invariant dù controller đã kiểm cùng rule?
12. Nếu thay HTTP Basic bằng OAuth2 JWT, cần kiểm điểm nào trước khi tin tenant/roles claims?

## 17. Tài liệu chính thức

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security — MockMvc HTTP Basic Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API5:2023 — Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

**Ghi nhớ:** endpoint policy quyết định **request nào được đi vào chức năng**; business policy quyết định **hành động có hợp lệ trong tình trạng nghiệp vụ**; object/data policy quyết định **actor được xem hoặc sửa bản ghi/tenant nào**. Phải thiết kế và kiểm thử cả ba, chứ không gộp chúng thành một role check trên URL.
