# Quyền theo đối tượng, chủ sở hữu và cách ly tenant trong kiểm thử Spring Boot Security

## 1. Tại sao chỉ kiểm role là chưa đủ?

Trong ứng dụng nhiều khách hàng tổ chức (multi-tenant SaaS), một người dùng có thể có quyền gọi endpoint `GET /api/orders/{id}` nhưng **không được xem mọi đơn hàng có ID hợp lệ**. Người dùng Alice của tenant A có thể đọc đơn hàng do Alice sở hữu; Bob cùng tenant A có thể không được xem đơn hàng riêng của Alice; Mallory thuộc tenant B chắc chắn không được xem đơn hàng của tenant A; còn một quản trị viên **tenant A** có thể được xem đơn hàng của Alice và Bob nhưng **không được vượt sang tenant B**.

Nếu ứng dụng chỉ viết:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public OrderView get(long orderId) {
    return repository.findById(orderId).orElseThrow();
}
~~~

thì một người có quyền ORDER_READ có thể thử thay `{id}` trong URL để xem tài nguyên của người khác. Đó là lỗi **Broken Object Level Authorization (BOLA)**, còn được gọi trong nhiều tình huống là **IDOR (Insecure Direct Object Reference)**. API id có thể là số tăng dần, UUID hoặc chuỗi khó đoán: **ID khó đoán không thay thế authorization**.

**Đề bài chính:** “Quyền theo đối tượng, chủ sở hữu và cách ly tenant”, thuộc nhóm **Bảo mật** trong Spring Boot testing. Trọng tâm không chỉ là role-based access control (RBAC), mà còn là **quyết định truy cập dựa trên bản ghi cụ thể và identity đã xác thực**, được kiểm chứng bằng những trường hợp dương tính và âm tính.

**Kết quả bạn cần đạt:**

1. Phân biệt **authentication**, **function-level authorization**, **object-level authorization**, **ownership** và **tenant isolation**.
2. Viết rõ ma trận quyền theo **tenant + owner + authority + thao tác** trước khi viết code.
3. Hiểu vì sao ID, `X-Tenant-Id`, `ownerId` trong request body và query params đều là **untrusted input** nếu không được đối chiếu với trusted identity/claims.
4. Sử dụng **`SecurityFilterChain`, `@EnableMethodSecurity` và `@PreAuthorize`** trong Spring Boot 3.3.5.
5. Giữ quyền theo đối tượng trong **service policy** và giới hạn truy vấn bằng **tenant-aware repository**, không chỉ ở controller.
6. Kiểm trường hợp **cùng tenant khác owner**, **khác tenant**, **tenant admin trong tenant của mình** và **tenant admin khác tenant**.
7. Kiểm `GET` một object, `GET` danh sách, `PATCH` thay đổi dữ liệu, missing permission, unauthenticated request và CSRF.
8. Dùng **`MockMvc` + `spring-security-test`** với custom `UserDetails` chứa trusted `tenantId`, thay vì tự nhận tenant từ HTTP header.
9. Phân biệt `401`, `403`, `404` theo policy và tránh rò rỉ sự tồn tại của object giữa tenants.
10. Kiểm **mass assignment**: JSON client cung cấp `ownerId` hoặc `tenantId` không được phép đổi quyền sở hữu.
11. Viết ví dụ **Java 17 / Spring Boot 3.3.5 / Gradle**, chạy được bằng `@SpringBootTest` + `@AutoConfigureMockMvc`, với **21 phương thức JUnit Jupiter `@Test`**.
12. Hiểu những giới hạn của in-memory repository và nâng lên **JDBC/JPA tenant predicates, PostgreSQL RLS, database integration tests, transaction/TOCTOU controls**.
13. Biết tại sao cần kiểm quyền ở **mọi đường truy cập object**: detail, list, update, delete, export, batch, async job, file download và subresource.

**Phiên bản cố định:** Java 17, Spring Boot **3.3.5**, Spring Security **6.3.x** thuộc dependency management của Boot 3.3, JUnit Jupiter và Spring MVC MockMvc. Mẫu dùng dữ liệu trong bộ nhớ để làm rõ chính sách, **không phải bằng chứng rằng database production đã được cách ly**. Phần SQL/RLS sau đó ghi rõ lớp kiểm chứng bổ sung.

## 2. Định nghĩa: Authentication khác authorization thế nào?

| Khái niệm | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| **Authentication** | Ai đang gửi request? Identity có được xác minh không? | Principal là Alice, userId=alice, tenantId=tenant-a |
| **Function-level authorization** | Principal có được thực hiện thao tác này không? | Có `ORDER_READ` mới gọi được read/list |
| **Object-level authorization** | Với **bản ghi cụ thể**, principal có được truy cập không? | Alice không được mở order của Bob |
| **Ownership** | Bản ghi thuộc người dùng/nhóm nào? | ownerId=alice |
| **Tenant isolation** | Bản ghi thuộc tổ chức nào? | tenantId=tenant-a, luôn giới hạn theo tenant |
| **Tenant admin scope** | Admin được vượt quyền owner trong phạm vi nào? | Admin A xem đơn hàng trong tenant A, không xem tenant B |
| **Field-level authorization** | Trong object hợp lệ, field nào được đọc/sửa? | title được sửa; ownerId/tenantId không được client đổi |
| **Audit/monitoring** | Ai thử truy cập dữ liệu nào và kết quả ra sao? | Ghi request ID, principal ID, outcome; tránh PII |

**Nhận biết lỗi:** Nếu một API từ chối người không có `ORDER_READ` nhưng người có `ORDER_READ` lại truy cập được ID của mọi người, bạn đã kiểm **chức năng** mà chưa kiểm **object**. OWASP API Security Top 10 2023 đặt Broken Object Level Authorization tại **API1:2023**; thao tác trái phép do quyền theo chức năng lại thuộc nhóm Broken Function Level Authorization (API5:2023).

Một API an toàn không chỉ hỏi “người dùng có role USER không?” mà phải kết hợp:

~~~text
allow(action, principal, object) =
    authenticated(principal)
    AND hasAuthority(principal, action)
    AND principal.tenantId == object.tenantId
    AND (
          principal.userId == object.ownerId
          OR hasRoleWithinThisTenant(principal, TENANT_ADMIN)
        )
    AND passesBusinessRestrictions(action, object)
~~~

Bài chọn chính sách đơn giản: owner hoặc tenant admin được đọc/sửa trong **chính tenant của mình**; người khác cùng tenant bị từ chối; mọi người ở tenant khác đều không nhìn thấy object. Hệ thật có thể thêm team membership, data classification, share grants, trạng thái khóa, delegated access hay time-limited permissions. Khi policy phức tạp, đưa vào một **authorization service/Policy Decision Point** có test riêng; đừng rải những điều kiện không nhất quán giữa nhiều controllers.

## 3. Ma trận quyền làm nguồn sự thật cho tests

Dữ liệu fixture:

| ID order | Tenant | Owner | Title |
|---|---|---|---|
| **100** | `tenant-a` | `alice` | `Alice draft` |
| **101** | `tenant-a` | `bob` | `Bob draft` |
| **200** | `tenant-b` | `mallory` | `Mallory draft` |

Principal giả lập trong test:

- Alice: `userId=alice`, `tenantId=tenant-a`, `ORDER_READ`, `ORDER_WRITE`.
- Bob: `userId=bob`, `tenantId=tenant-a`, `ORDER_READ`, `ORDER_WRITE`.
- Mallory: `userId=mallory`, `tenantId=tenant-b`, `ORDER_READ`, `ORDER_WRITE`.
- Admin A: `tenant-a`, `ROLE_TENANT_ADMIN`, `ORDER_READ`, `ORDER_WRITE`.
- Admin B: `tenant-b`, `ROLE_TENANT_ADMIN`, `ORDER_READ`, `ORDER_WRITE`.
- Read-only Alice: `tenant-a`, `ORDER_READ`, **không có ORDER_WRITE**.
- Write-only Alice: `tenant-a`, `ORDER_WRITE`, **không có ORDER_READ**.
- Anonymous: không có identity xác thực.

Ma trận đối với **order 100 (tenant-a, Alice)**:

| Caller | GET 100 | PATCH 100 | Lý do |
|---|---|---|---|
| Anonymous | **401** | **401** khi request có CSRF hợp lệ; nếu không, CSRF có thể chặn 403 sớm hơn | Chưa authentication |
| Alice | **200** | **200** khi có CSRF | Owner trong đúng tenant |
| Bob | **403** | **403** | Cùng tenant, không phải owner/admin |
| Mallory | **404** | **404** | Khác tenant; không tiết lộ sự tồn tại của ID |
| Admin A | **200** | **200** | Tenant admin trong tenant A |
| Admin B | **404** | **404** | Tenant admin không được vượt sang tenant A |
| Write-only Alice | **403** | Theo ORDER_WRITE + ownership | Thiếu ORDER_READ |
| Read-only Alice | **200** | **403** | Thiếu ORDER_WRITE |

**Về 403 và 404:** Cả hai cần được xác định trong contract. Ví dụ chọn **404** nếu ID không tồn tại trong tenant của principal, để không tiết lộ rằng tài nguyên ở tenant khác có tồn tại; chọn **403** khi object ở cùng tenant nhưng principal không có quyền owner/admin. Một hệ thống có thể chọn 404 cho cả hai để giảm enumeration; hãy giữ policy nhất quán, đặc biệt về response body và latency. Không trả 200 cùng dữ liệu rỗng để che một lỗi authorization nếu contract không quy định.

**Không dùng tenant lấy từ URL/header làm nguồn sự thật.** Với các URL dạng `/tenants/{tenantId}/orders/{id}`, `tenantId` trong path là **scope được yêu cầu**, phải đối chiếu với identity đã xác thực và membership được cấp; nó không tự là quyền truy cập.

## 4. Các lớp phòng vệ trong một request

~~~text
Client
  |
  | GET /api/orders/100
  | Header X-Tenant-Id: tenant-b    <-- untrusted input
  v
Spring Security filter chain
  |  Authentication được kiểm qua cơ chế đáng tin
  |  Principal được gắn userId + tenantId + authorities
  v
Controller
  |  Nhận objectId và trường được phép cập nhật
  |  KHÔNG dùng client tenant/owner để cấp quyền
  v
Service (@PreAuthorize: ORDER_READ / ORDER_WRITE)
  |  Kiểm function-level authority
  |  Lấy tenant từ authenticated principal
  |  Load object trong đúng tenant
  |  Kiểm owner hoặc ROLE_TENANT_ADMIN của tenant đó
  v
Repository
  |  SELECT ... WHERE tenant_id = :trustedTenantId AND id = :id
  |  UPDATE ... WHERE tenant_id = :trustedTenantId ...
  v
Database
  |
  | (production) RLS/constraints/tenant-scoped joins
  v
DTO trả về đúng fields được phép
~~~

**Defense in depth:** URL-level authentication chặn người chưa đăng nhập; method-level authority chặn một số chức năng; service/repository bảo vệ object; database tenant predicates/RLS giảm hậu quả nếu một đường code khác quên scope. Không lớp đơn lẻ nào thay thế tất cả.

### 4.1. Những phản mẫu cần tránh

**Phản mẫu A: chỉ kiểm role rồi query theo ID toàn cục**

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public OrderView read(long id) {
    return repository.findById(id) // Có thể lấy object tenant khác.
            .map(this::view)
            .orElseThrow();
}
~~~

**Phản mẫu B: tin `X-Tenant-Id` do client gửi**

~~~java
@GetMapping("/{id}")
OrderView read(
        @PathVariable long id,
        @RequestHeader("X-Tenant-Id") String tenantId) {
    return service.read(id, tenantId); // Có thể bị spoof.
}
~~~

**Phản mẫu C: tin ownerId từ JSON của client**

~~~java
// JSON client gửi:
// {"title":"Changed", "ownerId":"alice", "tenantId":"tenant-a"}

// Sai nếu service sử dụng ownerId/tenantId trong body
// để quyết định người dùng có quyền với object không.
~~~

**Phản mẫu D: list API lọc sau khi đọc toàn bộ**

~~~java
List<Order> all = repository.findAll();
return all.stream()
        .filter(order -> order.tenantId().equals(tenant))
        .toList();
~~~

Lọc trong Java *có thể* tạo output đúng, nhưng toàn bộ cross-tenant records đã được tải vào memory/cache và có thể xuất hiện trong log, metrics hoặc object mapping trung gian. Ưu tiên **tenant-scoped DB query** ngay từ tầng truy cập dữ liệu và kết hợp các kiểm tra domain cần thiết.

**Phản mẫu E: tenant admin tương đương global admin**

~~~java
boolean allowed = hasRole("TENANT_ADMIN")
        || order.ownerId().equals(userId);
~~~

Nếu quên ràng buộc `order.tenantId == principal.tenantId`, một admin của tenant B có thể truy cập dữ liệu tenant A. **Ràng buộc tenant phải đứng ngoài và bắt buộc trước nhánh admin**.

## 5. Chọn kiểu test: unit, method security, MVC hay database

| Loại | Có Spring Security filters? | Có DB thật? | Kiểm được gì? |
|---|---|---|---|
| Unit test `OrderPolicy` thuần Java | Không | Không | Ma trận principal/object/action, branch logic |
| `@WithMockUser` gọi service bean có `@EnableMethodSecurity` | Method proxy | Không bắt buộc | `@PreAuthorize`, role/authority |
| **`@SpringBootTest` + `@AutoConfigureMockMvc`** | **Có (nếu addFilters=true mặc định)** | Không bắt buộc | 401/403/404, CSRF, controller + method policy + repository |
| `@WebMvcTest` | Có nhưng chỉ MVC slice | Không | Endpoint/security filter; cần `@MockBean/@Import` cho policy |
| `@JdbcTest` / `@DataJpaTest` + DB | Tuỳ context | **Có** | Tenant predicates, query joins, UPDATE counts |
| `@SpringBootTest` + Testcontainers PostgreSQL | Có thể có | **Có, đúng vendor** | RLS, roles, connection/session context, isolation |
| HTTP server thật + OAuth2 test IdP | Có | Có thể | Xác minh JWT/issuer/audience, toàn chuỗi xác thực |

Vì mục tiêu bài là kiểm quyền qua HTTP và service, ví dụ chạy được sử dụng **MockMvc với full Spring Boot context**, in-memory repository để mỗi test nhanh và độc lập. Phải bổ sung DB integration tests trên hệ thống thật khi có repository SQL/JPA, vì một fake có thể đúng policy trong khi production query thiếu `tenant_id`.

### 5.1. @WithMockUser hay custom principal?

`@WithMockUser` tạo một Spring Security principal kiểu `User` với username/roles/authorities. Nó rất tốt cho các test role đơn giản, nhưng **không tự có trường tenantId được xác minh**. Nếu code production dựa vào `TenantUser.tenantId`, một `@WithMockUser(username="alice")` đơn thuần không đủ để kiểm tenant scoping.

Trong ví dụ ta dùng Spring Security Test **`SecurityMockMvcRequestPostProcessors.user(customUserDetails)`**, tạo một identity test có `userId`, `tenantId` và authorities theo từng request. Đây là **test shortcut để mô phỏng kết quả authentication**, không phải bằng chứng token/chứng thực thật đã hợp lệ.

**Không tạo tenant principal dựa trên header X-Tenant-Id do caller tự chọn.** Trong production, tenant phải đến từ login session/JWT claims đã **được kiểm chữ ký, issuer, audience, expiry, membership** hoặc từ identity/authorization directory tin cậy. Khi user thuộc nhiều tenants, active tenant do client chọn cũng phải được đối chiếu danh sách membership; không tin raw header.

## 6. Project chạy được: Java 17 + Spring Boot 3.3.5 + MockMvc

Project này có 3 orders và 5 loại principal test, một REST controller, một service có `@PreAuthorize`, một in-memory repository tự scope tenant, và lớp JUnit kiểm đủ các nhánh. Mẫu **không có login account/password production**; test dùng `user(customUserDetails)` để đưa principal đã được mô phỏng vào `MockMvc`. Muốn chạy thành hệ SaaS thật, phải thay bằng cơ chế xác thực JWT/OIDC/session và database có tenant scoping.

### 6.1. Cây thư mục

~~~text
settings.gradle
build.gradle
src/main/java/demo/tenant/TenantSecurityApplication.java
src/main/java/demo/tenant/SecurityConfiguration.java
src/main/java/demo/tenant/TenantUser.java
src/main/java/demo/tenant/OrderData.java
src/main/java/demo/tenant/OrderView.java
src/main/java/demo/tenant/RenameOrderRequest.java
src/main/java/demo/tenant/InMemoryOrderStore.java
src/main/java/demo/tenant/OrderService.java
src/main/java/demo/tenant/OrderController.java
src/test/java/demo/tenant/TenantAuthorizationIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tenant-authorization-test'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích:** starter-web mang Spring MVC, Jackson JSON và MockMvc support cùng starter-test. starter-security mang `SecurityFilterChain`, `@PreAuthorize` và authentication context. `spring-security-test` mang `user(...)`, `csrf()` và `@WithMockUser`. Đặc biệt, **không mặc định rằng starter-test đã bao gồm spring-security-test** — dependency này được khai báo riêng. Spring Boot BOM quản lý version Spring Security và không cần tự pin Spring Security 6.3.x.

### 6.2. Application và HTTP security

**src/main/java/demo/tenant/TenantSecurityApplication.java**

~~~java
package demo.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantSecurityApplication.class, args);
    }
}
~~~

**src/main/java/demo/tenant/SecurityConfiguration.java**

~~~java
package demo.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Điểm cần hiểu:**
1. `.anyRequest().authenticated()` chặn người chưa xác thực từ filter chain.
2. `.httpBasic(...)` cung cấp HTTP 401 challenge cho request không đăng nhập trong ví dụ. Basic Auth chỉ là một cơ chế thử HTTP auth status ở bài này, **không có nghĩa kiến trúc SaaS production nên dùng password Basic Auth**.
3. **`@EnableMethodSecurity` là bắt buộc** để `@PreAuthorize` trên service có tác dụng; Spring Boot Starter Security không tự bật method security cho mọi bean.
4. Không tắt CSRF trong mẫu: `PATCH` phải có token hợp lệ với cơ chế session/CSRF của Spring Security. Test sẽ dùng `.with(csrf())`.
5. Endpoint bất kỳ vẫn cần authenticated user; **authentication không đồng nghĩa có quyền đọc mọi object**.
6. Method security dùng Spring AOP proxy: tránh tự gọi một method `@PreAuthorize` từ method khác trên cùng instance rồi nghĩ proxy sẽ can thiệp. Các controller trong bài gọi Spring-managed service bean qua proxy.

**Lưu ý thực tế:** Khi deploy API stateless JWT Bearer với Authorization header, bạn cần `oauth2ResourceServer(...).jwt(...)` hoặc cơ chế xác thực tương đương; CSRF policy có thể khác tuỳ cách lưu credentials. **Không tắt CSRF theo công thức** chỉ vì project dùng REST: nếu browser tự gửi cookie/session credentials thì CSRF vẫn là mối nguy. Bài cố định CSRF bật để test một lớp bảo vệ bổ sung, độc lập với ownership/tenant authorization.

### 6.3. Principal có tenant và authorities

**src/main/java/demo/tenant/TenantUser.java**

~~~java
package demo.tenant;

import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public record TenantUser(
        String userId,
        String tenantId,
        List<GrantedAuthority> authorities) implements UserDetails {

    public TenantUser {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(tenantId);
        authorities = List.copyOf(authorities);
    }

    public static TenantUser regular(String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(
                        new SimpleGrantedAuthority("ORDER_READ"),
                        new SimpleGrantedAuthority("ORDER_WRITE")));
    }

    public static TenantUser tenantAdmin(
            String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(
                        new SimpleGrantedAuthority("ORDER_READ"),
                        new SimpleGrantedAuthority("ORDER_WRITE"),
                        new SimpleGrantedAuthority(
                                "ROLE_TENANT_ADMIN")));
    }

    public static TenantUser readOnly(
            String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(new SimpleGrantedAuthority("ORDER_READ")));
    }

    public static TenantUser writeOnly(
            String userId, String tenantId) {
        return new TenantUser(
                userId, tenantId,
                List.of(new SimpleGrantedAuthority("ORDER_WRITE")));
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return "NOT_USED_FOR_LOGIN";
    }

    @Override
    public String getUsername() {
        return userId;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

`TenantUser` là **một record Java 17 có thể được Spring Security test tạo thành principal thông qua UserDetails**. `getPassword()` ở đây cố ý là dummy: class này không có `UserDetailsService` dùng để authenticate request thật và test không đi qua password verification. Trong production nên dùng một validated JWT principal/Authentication token hoặc một directory-backed UserDetailsService an toàn. **Không tự gán tenantId từ request header**, không serialize dummy password ra response/logs.

**Quy tắc role:** `hasRole('TENANT_ADMIN')` kiểm authority `ROLE_TENANT_ADMIN`; `hasAuthority('ORDER_READ')` kiểm đúng string `ORDER_READ`. Bài cấp cả role và action authorities rõ ràng; admin thuộc **tenant của chính mình**, không tự trở thành cross-tenant superuser.

### 6.4. Domain data, response DTO và request DTO

**src/main/java/demo/tenant/OrderData.java**

~~~java
package demo.tenant;

public record OrderData(
        long id,
        String tenantId,
        String ownerId,
        String title) {
}
~~~

**src/main/java/demo/tenant/OrderView.java**

~~~java
package demo.tenant;

public record OrderView(long id, String title) {
    public static OrderView from(OrderData value) {
        return new OrderView(value.id(), value.title());
    }
}
~~~

**src/main/java/demo/tenant/RenameOrderRequest.java**

~~~java
package demo.tenant;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record RenameOrderRequest(String title) {
}
~~~

**Tại sao có ba kiểu?**
- **OrderData** là dữ liệu nội bộ: chứa `tenantId`/`ownerId` để enforce access.
- **OrderView** là response public: chỉ gồm `id` và `title`; không tự trả trường phân quyền hoặc internal notes khi không cần.
- **RenameOrderRequest** chỉ nhận `title`; không có setters cho tenant/owner. Annotation `@JsonIgnoreProperties(ignoreUnknown=true)` cố ý cho phép thêm JSON keys mà **không sử dụng** chúng. Test mass-assignment sau đây chứng minh các key `tenantId`/`ownerId` gửi thêm không thể đổi quyền sở hữu. Trong production có thể cấu hình **fail on unknown properties** để báo input bất thường rõ ràng; việc bỏ qua keys ngoài DTO không phải chính sách input validation bắt buộc cho mọi API.

Nếu dùng JPA entity trực tiếp làm `@RequestBody` rồi gọi `repository.save(entity)`, client có thể sửa các trường không intended như tenantId/ownerId/isAdmin/status; đó là **mass assignment**, một rủi ro khác với BOLA nhưng thường xuất hiện cùng đường update. Nên tách request DTO allowlist như bài mẫu.

### 6.5. Repository: mọi read/list/update đều có tenant scope

**src/main/java/demo/tenant/InMemoryOrderStore.java**

~~~java
package demo.tenant;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

@Repository
public class InMemoryOrderStore {

    private final ConcurrentMap<Long, OrderData> rows =
            new ConcurrentHashMap<>();

    public InMemoryOrderStore() {
        reset();
    }

    public void reset() {
        rows.clear();
        rows.put(100L,
                new OrderData(100L,
                        "tenant-a", "alice", "Alice draft"));
        rows.put(101L,
                new OrderData(101L,
                        "tenant-a", "bob", "Bob draft"));
        rows.put(200L,
                new OrderData(200L,
                        "tenant-b", "mallory", "Mallory draft"));
    }

    public Optional<OrderData> findInTenant(
            long id, String tenantId) {
        return Optional.ofNullable(rows.get(id))
                .filter(row -> row.tenantId().equals(tenantId));
    }

    public List<OrderData> listInTenant(String tenantId) {
        return rows.values().stream()
                .filter(row -> row.tenantId().equals(tenantId))
                .sorted(Comparator.comparingLong(OrderData::id))
                .toList();
    }

    public OrderData renameInTenant(
            long id, String tenantId, String title) {

        OrderData updated = rows.computeIfPresent(
                id,
                (key, row) -> row.tenantId().equals(tenantId)
                        ? new OrderData(
                                row.id(), row.tenantId(),
                                row.ownerId(), title)
                        : row);

        if (updated == null
                || !updated.tenantId().equals(tenantId)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }

        return updated;
    }
}
~~~

Mỗi phương thức read/list/update đều nhận tenant scope **do service lấy từ authenticated principal**, không nhận tenant tùy tiện từ header. `findInTenant` trả empty nếu ID không tồn tại hoặc tồn tại trong tenant khác, làm HTTP policy 404 đồng nhất.

**Đây là fake repository phục vụ bài học.** `reset()` chạy trước mỗi test; test dùng cùng một ApplicationContext nên không chạy parallel trong class. `ConcurrentHashMap` giúp các thao tác cụ thể có atomic map updates, nhưng reset bằng clear/put không phải transaction database và có thể race nếu suite toàn hệ thống chia sẻ store với test khác. Trong production dùng PostgreSQL/JPA tenant-aware predicates, row-level permissions, transaction và constraints thay vì một singleton map.

**Defense in depth:** `renameInTenant` lại kiểm tenant một lần nữa trong chính update operation. Dù service đã xác minh object, tầng lưu trữ không chấp nhận ghi vào một record của tenant khác. Với database thật, làm điều này bằng **một câu UPDATE có tenant predicate và kiểm affected row count** để tránh time-of-check/time-of-use race.

### 6.6. Service: quyền theo action + owner + tenant

**src/main/java/demo/tenant/OrderService.java**

~~~java
package demo.tenant;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final InMemoryOrderStore store;

    public OrderService(InMemoryOrderStore store) {
        this.store = store;
    }

    private TenantUser trustedPrincipal() {
        Authentication authentication =
                SecurityContextHolder.getContext()
                        .getAuthentication();

        if (authentication == null
                || !(authentication.getPrincipal()
                        instanceof TenantUser user)) {
            throw new AccessDeniedException(
                    "Trusted tenant principal required");
        }

        return user;
    }

    private boolean isTenantAdmin(TenantUser user) {
        return user.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_TENANT_ADMIN"::equals);
    }

    private OrderData authorizedOrder(
            long id, TenantUser principal) {

        // Tenant scope ĐƯỢC KIỂM TRƯỚC owner/admin.
        OrderData row = store
                .findInTenant(id, principal.tenantId())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Order not found"));

        if (!row.ownerId().equals(principal.userId())
                && !isTenantAdmin(principal)) {
            throw new AccessDeniedException(
                    "Object ownership permission required");
        }

        return row;
    }

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public OrderView read(long id) {
        TenantUser principal = trustedPrincipal();
        return OrderView.from(authorizedOrder(id, principal));
    }

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public List<OrderView> listMineOrTenantAdmin() {
        TenantUser principal = trustedPrincipal();

        return store.listInTenant(principal.tenantId())
                .stream()
                .filter(row -> isTenantAdmin(principal)
                        || row.ownerId().equals(principal.userId()))
                .map(OrderView::from)
                .toList();
    }

    @PreAuthorize("hasAuthority('ORDER_WRITE')")
    public OrderView rename(long id, String newTitle) {
        TenantUser principal = trustedPrincipal();

        OrderData current = authorizedOrder(id, principal);

        if (newTitle == null || newTitle.isBlank()
                || newTitle.strip().length() > 80) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Title must contain 1 to 80 characters");
        }

        // Tầng storage vẫn giới hạn theo tenant.
        OrderData updated = store.renameInTenant(
                current.id(),
                principal.tenantId(),
                newTitle.strip());

        return OrderView.from(updated);
    }
}
~~~

**Phân tích trình tự:**

1. `@PreAuthorize("hasAuthority('ORDER_READ')")` hoặc `ORDER_WRITE` là **function-level guard** trước khi vào method (khi `@EnableMethodSecurity` bật và invocation qua Spring proxy).
2. `trustedPrincipal()` lấy identity từ **SecurityContextHolder của request đã được xác thực**, không nhận tenant qua method argument do controller/client nhập.
3. `authorizedOrder` yêu cầu truy vấn đúng tenant **trước khi** xét owner hoặc tenant admin. Với ID của tenant khác, nó không thấy object và trả **404**.
4. Với object cùng tenant, nếu người dùng không phải owner và không có `ROLE_TENANT_ADMIN`, ném `AccessDeniedException` để Spring Security xử lý **403**.
5. Tenant admin cũng chỉ đọc những rows `store.listInTenant(principal.tenantId())`, nên role này không biến thành global admin.
6. Khi rename, chỉ cho phép `title` hợp lệ và gọi storage method đã tenant-scoped. Code không hề nhận `ownerId`/`tenantId` từ body.
7. `@PreAuthorize` bảo vệ cả service gọi từ đường khác, ví dụ controller khác hoặc scheduled job đi qua Spring proxy. Tuy nhiên **self-invocation có thể bypass method-security proxy**, nên không chỉ dựa một annotation khi viết code nội bộ.
8. `SecurityContextHolder` thường dựa vào thread-local. Với `@Async`, `CompletableFuture`, thread pool, cần thiết kế context propagation và kiểm lại authorization; không được gán default tenant hoặc tự sao chép user ID từ header.

**Về order check và 403/404:** Bài thực hành cố tình trả 404 cho cross-tenant ID và 403 cho non-owner trong tenant. Nếu yêu cầu an ninh cấm tiết lộ cả owner existence trong tenant, trả 404 đồng nhất cũng hợp lệ. Policy này cần được test ở **tất cả các thao tác**. Đừng trả khác biệt lỗi giữa GET và PATCH khiến client suy đoán được sự tồn tại tài nguyên.

**Về direct DB SQL:** Fake `authorizedOrder` + `renameInTenant` minh họa hai lớp kiểm, chưa bảo đảm serializable isolation với DB thật. Khi object có thể đổi owner/tenant đồng thời, cần một câu UPDATE có `WHERE tenant_id AND owner_id/permission predicate` hoặc transaction locking với recheck. Xem mục 10.

### 6.7. Controller không nhận tenant/owner do client tự xác nhận

**src/main/java/demo/tenant/OrderController.java**

~~~java
package demo.tenant;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping
    public List<OrderView> list() {
        return service.listMineOrTenantAdmin();
    }

    @GetMapping("/{id}")
    public OrderView read(@PathVariable long id) {
        return service.read(id);
    }

    @PatchMapping("/{id}")
    public OrderView rename(
            @PathVariable long id,
            @RequestBody RenameOrderRequest request) {
        return service.rename(id, request.title());
    }
}
~~~

Controller nhận ID tài nguyên và trường `title`, nhưng **không có tham số `tenantId`/`ownerId`** để khách hàng tự khai báo. Nếu cần API với URL có tenant segment, phải validate segment với tenant được phép từ identity. Không dùng request parameter như `?tenantId=tenant-b` thay `trustedPrincipal()`.

Trả `OrderView` thay `OrderData` cũng giảm nguy cơ lộ fields nội bộ. Tuy nhiên DTO có thể cần field-level authorization thêm khi object chứa thông tin nhạy cảm; **được phép đọc object không đồng nghĩa được xem mọi field**.

## 7. Lớp integration test hoàn chỉnh: 21 JUnit Jupiter tests

**src/test/java/demo/tenant/TenantAuthorizationIntegrationTest.java**

~~~java
package demo.tenant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Execution(ExecutionMode.SAME_THREAD)
class TenantAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryOrderStore store;

    @BeforeEach
    void resetFixture() {
        store.reset();
    }

    @Test
    void anonymousCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/100"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(100))
                .andExpect(jsonPath("$.title").value("Alice draft"))
                .andExpect(jsonPath("$.tenantId").doesNotExist())
                .andExpect(jsonPath("$.ownerId").doesNotExist());
    }

    @Test
    void sameTenantOtherOwnerIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "bob", "tenant-a"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void crossTenantOrderLooksNotFound() throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isNotFound());
    }

    @Test
    void tenantAdminCanReadAnotherOwnerInSameTenant()
            throws Exception {
        mvc.perform(get("/api/orders/101")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.title").value("Bob draft"));
    }

    @Test
    void tenantAdminCannotCrossTenantBoundary()
            throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-b", "tenant-b"))))
                .andExpect(status().isNotFound());
    }

    @Test
    void ownerListContainsOnlyOwnOrders()
            throws Exception {
        mvc.perform(get("/api/orders")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value(100));
    }

    @Test
    void tenantAdminListContainsOnlyItsTenant()
            throws Exception {
        mvc.perform(get("/api/orders")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].id").value(100))
                .andExpect(jsonPath("$[1].id").value(101));
    }

    @Test
    void secondTenantListDoesNotContainFirstTenant()
            throws Exception {
        mvc.perform(get("/api/orders")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value(200));
    }

    @Test
    void forgedTenantHeaderDoesNotGrantAccess()
            throws Exception {
        mvc.perform(get("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .header("X-Tenant-Id", "tenant-b"))
                .andExpect(status().isNotFound());
    }

    @Test
    void writeOnlyPrincipalCannotRead()
            throws Exception {
        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.writeOnly(
                                "alice", "tenant-a"))))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ORDER_READ")
    void genericMockUserLacksTrustedTenantPrincipal()
            throws Exception {
        mvc.perform(get("/api/orders/100"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanPatchTitleWithCsrf()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Updated title\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated title"));

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated title"));
    }

    @Test
    void sameTenantOtherOwnerCannotPatch()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "bob", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Hijacked\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Alice draft"));
    }

    @Test
    void crossTenantPatchIsNotFoundAndUnchanged()
            throws Exception {
        mvc.perform(patch("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Cross-tenant rewrite\"}"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Mallory draft"));
    }

    @Test
    void patchWithoutCsrfIsRejected()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .contentType("application/json")
                        .content("{\"title\":\"No csrf\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(jsonPath("$.title").value("Alice draft"));
    }

    @Test
    void readOnlyPrincipalCannotPatch()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.readOnly(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Write forbidden\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void tenantAdminCanPatchWithinSameTenant()
            throws Exception {
        mvc.perform(patch("/api/orders/101")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Admin reviewed\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Admin reviewed"));

        mvc.perform(get("/api/orders/101")
                        .with(user(TenantUser.regular(
                                "bob", "tenant-a"))))
                .andExpect(jsonPath("$.title").value("Admin reviewed"));
    }

    @Test
    void tenantAdminCannotPatchAnotherTenant()
            throws Exception {
        mvc.perform(patch("/api/orders/200")
                        .with(user(TenantUser.tenantAdmin(
                                "admin-a", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Global admin mistake\"}"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/200")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(jsonPath("$.title").value("Mallory draft"));
    }

    @Test
    void jsonOwnerAndTenantFieldsCannotReassignOrder()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("""
                                {
                                  "title":"Safe title",
                                  "ownerId":"mallory",
                                  "tenantId":"tenant-b"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Safe title"));

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "mallory", "tenant-b"))))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Safe title"));
    }

    @Test
    void blankTitleIsRejectedWithoutMutation()
            throws Exception {
        mvc.perform(patch("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a")))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/orders/100")
                        .with(user(TenantUser.regular(
                                "alice", "tenant-a"))))
                .andExpect(jsonPath("$.title").value("Alice draft"));
    }
}
~~~

**Đếm chính xác: 21 phương thức `@Test`**; `@BeforeEach` reset fixture không tính là một test. Các phương thức sau đổi dữ liệu đều chạy trên fixture mới ở method tiếp theo. `@Execution(SAME_THREAD)` giúp tránh việc chính lớp test này chạy methods song song với nhau; một suite lớn vẫn cần cô lập ApplicationContext/DB nếu nhiều lớp chia sẻ store hoặc thiết lập global parallelism.

**Tại sao các assertions quan trọng:**
- `401`: anonymous chưa qua authentication. Điều này không phải bằng chứng object-level authorization.
- `403`: đã xác thực nhưng thiếu action authority hoặc không phải owner/admin trong tenant.
- `404`: object không có trong tenant của principal; dù có ID ở tenant khác cũng không được tiết lộ.
- `200`: chỉ người được phép mới nhận DTO; DTO không chứa `ownerId`/`tenantId`.
- `GET /api/orders`: kiểm **list scoping**, vì chỉ bảo vệ detail endpoint sẽ để lộ dữ liệu qua list/search.
- `PATCH`: kiểm quyền **ghi** tách khỏi quyền **đọc**, không cho cùng-tenant Bob hoặc cross-tenant admin sửa trái phép.
- `X-Tenant-Id` giả: header không thay được tenant từ trusted principal.
- JSON `ownerId`/`tenantId` giả: request DTO không có các writable fields tương ứng; owner và tenant của persisted record không bị chuyển.
- CSRF: request ghi mà thiếu token bị chặn. Đây là **lớp bảo vệ khác**, không chứng minh policy ownership; những tests muốn kiểm owner phải dùng `.with(csrf())` để tránh bị chặn quá sớm.
- `@WithMockUser`: minh họa test role đơn giản không tự tạo `TenantUser` có tenant; method-level read authority có thể hợp lệ nhưng service vẫn từ chối principal thiếu trusted tenant.

**Không tuyên bố đây là test JWT thật.** `.with(user(...))` đưa một principal tin cậy *giả lập* trực tiếp vào mock request. Nó không test verification của token, issuer/audience, role mapping từ IdP hay tenant membership refresh. Các yêu cầu đó cần test lớp authentication riêng.

### 7.1. Tại sao phải reset fixture trước từng test?

InMemoryOrderStore là Spring singleton được `@SpringBootTest` giữ trong ApplicationContext. Nếu một test PATCH đổi title từ `Alice draft` thành `Updated title`, test sau kiểm title gốc có thể fail hoặc pass tùy thứ tự nếu không reset. Vì vậy:

~~~java
@Autowired
InMemoryOrderStore store;

@BeforeEach
void resetFixture() {
    store.reset();
}
~~~

Khi chuyển sang JPA/JDBC, ưu tiên **test-managed transaction + rollback**, `@Sql` setup/cleanup, disposable database hoặc Testcontainers fixture riêng. Đừng dùng in-memory reset làm bằng chứng database transaction isolation; và đừng dựa vào `@DirtiesContext` cho mọi test nếu có cách reset data nhẹ hơn.

### 7.2. Vì sao cần negative tests *cùng tenant khác chủ*?

Nhiều dự án chỉ test Alice và Mallory tenant khác nhau, rồi tưởng đã có ownership enforcement. Một implementation bị lỗi:

~~~java
if (record.tenantId().equals(principal.tenantId())) {
    return record; // Lộ mọi object trong cùng tenant!
}
~~~

sẽ **pass** test cross-tenant, nhưng **fail** test Bob đọc order Alice khi policy chỉ cho owner/tenant admin. Nếu hệ nghiệp vụ cho mọi user trong cùng tenant đọc chung, phải thay ma trận quyền và assertions có chủ đích. Không tự mặc định owner check là bắt buộc trong mọi B2B ứng dụng; nó phải xuất phát từ hợp đồng quyền thật.

### 7.3. Vì sao tenant admin phải kiểm cross-tenant riêng?

Một phép kiểm sai:

~~~java
if (principal.hasAuthority("ROLE_TENANT_ADMIN")) {
    return repository.findById(id).orElseThrow();
}
~~~

sẽ cho tenant admin A truy cập cả tenant B. Test **tenantAdminCannotCrossTenantBoundary** và **tenantAdminCannotPatchAnotherTenant** bắt được. Cách viết đúng là **lọc đúng tenant trước**, sau đó xem role có cho vượt owner *trong tenant đó* không.

### 7.4. Vì sao response DTO không cần chủ/tenant nếu chưa có contract?

Một client hợp lệ đôi khi cần tenantId/ownerId để hiển thị; nếu vậy có thể cho phép những fields phù hợp với field-level access. Trong bài, OrderView chỉ gồm id/title, nhằm tránh vô tình trả full domain entity. Nếu response có `isAdmin`, internal cost, mật khẩu, recovery key hoặc thông tin riêng tư, object-level authorization pass vẫn chưa bảo đảm field-level authorization.

## 8. Lệnh chạy, điều kiện và expected results

Dự án có Java 17, Gradle, các files theo phần 6 và các test theo phần 7. Nếu đã tạo Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu chỉ sao chép build.gradle/settings.gradle nhưng **chưa tạo Gradle Wrapper scripts/JAR**, lệnh `./gradlew` chưa tồn tại. Dùng Gradle phiên bản tương thích để tạo wrapper hoặc chạy `gradle test`.

Chạy riêng lớp:

~~~bash
./gradlew test --tests demo.tenant.TenantAuthorizationIntegrationTest
~~~

Kỳ vọng Spring Boot tìm `@SpringBootApplication` trong package demo.tenant, khởi tạo Spring Security filter chain, method-security proxy, controller/service/repository và MockMvc. `spring-security-test` cung cấp `.with(user(...))` và `.with(csrf())`. **21 test methods được thiết kế PASS** khi source được tạo đúng và không có cấu hình ngoài thay đổi authorization policy. Đây là **kết quả dự kiến từ source**, không phải xác nhận đã thực thi Gradle trong môi trường của người đọc.

Báo cáo Gradle thường nằm tại:

~~~text
build/reports/tests/test/index.html
~~~

| Nhóm test | Số @Test | Mục tiêu |
|---|---:|---|
| Authentication / GET detail / owner & tenant | 6 | 401, owner 200, cùng tenant 403, khác tenant 404, admin same tenant 200, admin cross tenant 404 |
| GET list / forged header / missing authority / principal type | 6 | List scope 3 trường hợp, giả header, thiếu ORDER_READ, generic @WithMockUser |
| PATCH update / CSRF / authority / admin / mass assignment / validation | 9 | Owner write, same-tenant denied, cross-tenant denied, no CSRF, readOnly, admin allow/deny, JSON spoof, blank title |
| **Tổng** | **21** | Không có @Disabled hoặc test cố ý fail |

**Phân loại group chính xác:** 6 + 6 + 9 = 21. Các method có nhiều `mvc.perform` vẫn chỉ là **một JUnit test**; mỗi request trong một test được thực hiện theo thứ tự assertions rõ ràng.

**Tình huống có thể gây khác biệt ngoài code mẫu:** Nếu cấu hình `spring-security-test` bị thiếu, các static imports không compile. Nếu tự disable Spring Security filters trong `@AutoConfigureMockMvc(addFilters=false)`, tests 401/CSRF có thể sai. Nếu không bật `@EnableMethodSecurity`, thiếu ORDER_READ/ORDER_WRITE có thể không được chặn. Nếu đổi DTO thành entity nhận trực tiếp, test JSON owner/tenant sẽ giúp bắt mass-assignment. Nếu server xác thực token thật, cần test token validation riêng và không dùng dummy `TenantUser` như authentication production.

## 9. Ma trận mutation: chủ động đưa lỗi vào code để kiểm test có sức phát hiện

| Mutation giả định | Kỳ vọng test nào fail |
|---|---|
| Xóa `@EnableMethodSecurity` | MissingReadAuthority và ReadOnlyCannotPatch có thể fail vì thiếu function guard |
| Đổi `@PreAuthorize("ORDER_READ")` thành `permitAll()` | WriteOnlyPrincipalCannotRead |
| Repository dùng `findById` không scope tenant | CrossTenantOrderLooksNotFound và AdminCannotCrossTenantBoundary |
| Bỏ kiểm owner trong authorizedOrder | SameTenantOtherOwnerIsForbidden, BobCannotPatch |
| Cho admin bỏ qua tenant | AdminCannotCrossTenantBoundary, AdminCannotPatchAnotherTenant |
| Tin header `X-Tenant-Id` | ForgedTenantHeaderDoesNotGrantAccess |
| Trả `OrderData` raw thay `OrderView` | OwnerCanReadOwnOrder phát hiện ownerId/tenantId lộ |
| PATCH nhận `OrderData` toàn bộ rồi save | JsonOwnerAndTenantFieldsCannotReassignOrder |
| Bỏ `@PreAuthorize("ORDER_WRITE")` | ReadOnlyPrincipalCannotPatch |
| Tắt CSRF trong security config | PatchWithoutCsrfIsRejected |
| Dùng global `findAll()` rồi trả DTO mà không lọc | List scoping tests fail |
| Cho bob cùng tenant rename owner Alice | SameTenantOtherOwnerCannotPatch |
| Đổi 404 cross tenant thành 403 | Tests cross tenant fail, tiết lộ policy đã đổi |
| Không reset fixture trước từng test | Các PATCH tests có thể tạo sự phụ thuộc thứ tự |
| Không xác định trusted tenant principal | GenericMockUser test có thể phát hiện principal bị coi là đủ |
| Bỏ validate title rỗng | BlankTitleIsRejectedWithoutMutation |

**Mục tiêu của mutation testing:** Kiểm rằng test suite có khả năng phát hiện **đúng loại lỗi quyền**. Không chỉ kiểm mỗi happy path hoặc các request không xác thực; BOLA thường xuất hiện ở người dùng **đã đăng nhập, có quyền chức năng**, nhưng thao tác object không được phép.

## 10. Khi thay fake bằng database thật: tenant scope phải có ở SQL

### 10.1. Truy vấn đơn

**Phản mẫu:**

~~~sql
SELECT id, tenant_id, owner_id, title
FROM orders
WHERE id = :id;
~~~

Nếu ID toàn cục, truy vấn này có thể tải record của tenant khác lên application layer. Application service vẫn có thể chặn, nhưng nếu code trả response/log trước check, dữ liệu đã bị lộ. Với hệ nhiều tenant, tốt hơn:

~~~sql
SELECT id, tenant_id, owner_id, title
FROM orders
WHERE id = :id
  AND tenant_id = :trusted_tenant_id;
~~~

`trusted_tenant_id` phải đến từ **validated principal/tenant membership**, không lấy trực tiếp từ `X-Tenant-Id` hoặc JSON body. Với Spring JDBC, dùng **NamedParameterJdbcTemplate** cùng bound parameters; đừng nối string thô vào SQL. Với Spring Data JPA, các methods dạng `findByIdAndTenantId` hoặc Criteria/Specification có điều kiện tenant giúp tạo rõ contract, nhưng cần test **SQL thật** và tránh các đường repository khác không có filter.

### 10.2. UPDATE/DELETE phải scope nguyên tử

Chỉ kiểm owner trong Java rồi update bằng `WHERE id=:id` có thể tạo **time-of-check/time-of-use (TOCTOU)** race: owner/tenant của record thay đổi giữa hai bước. Một câu update atomic có điều kiện:

~~~sql
UPDATE orders
SET title = :new_title
WHERE id = :id
  AND tenant_id = :trusted_tenant_id
  AND (
        owner_id = :trusted_user_id
        OR :trusted_is_tenant_admin = TRUE
      );
~~~

Với PostgreSQL boolean parameter, điều kiện trên là ví dụ hợp lệ về ý tưởng; các placeholders có tên thuộc **NamedParameterJdbcTemplate**, không phải syntax PostgreSQL thuần khi chạy bằng psql. `trusted_is_tenant_admin` **chỉ được backend tính từ quyền đã xác thực trong tenant đang xét**. Kiểm affected row count:
- 1: update thành công.
- 0: không tồn tại hoặc không có quyền; chọn 404/403 theo policy và không reveal tenant khác.

Nếu cần phân biệt 403 và 404, nên truy vấn tồn tại **trong tenant** để xác định object mà không lộ cross-tenant, rồi recheck/lock phù hợp trong cùng transaction. Không tách read and update mà bỏ qua concurrency. DELETE và batch updates tương tự: mọi câu lệnh phải có tenant predicate hoặc RLS đúng.

### 10.3. LIST và pagination phải scope ngay tại DB

~~~sql
SELECT id, title
FROM orders
WHERE tenant_id = :trusted_tenant_id
  AND (
       owner_id = :trusted_user_id
       OR :trusted_is_tenant_admin = TRUE
  )
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

Cả **COUNT query** phục vụ pagination cũng phải có cùng tenant/ownership predicate, nếu không JSON metadata `totalElements` có thể rò số lượng object của tenant khác dù list items đã lọc. Tương tự với search index, cache, exports và aggregates: tenant scope phải có trong **key/query/cache namespace**, không chỉ HTTP list endpoint.

### 10.4. Composite keys và foreign keys

Trong mô hình dùng id có thể lặp giữa tenants, nên xem xét:

~~~sql
CREATE TABLE orders (
    tenant_id VARCHAR(80) NOT NULL,
    id BIGINT NOT NULL,
    owner_id VARCHAR(80) NOT NULL,
    title VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
~~~

Với bảng con, foreign key cũng nên có tenant dimension để không gắn row của tenant A vào parent của tenant B:

~~~sql
CREATE TABLE order_lines (
    tenant_id VARCHAR(80) NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, id)
);
~~~

Đây là **SQL kiến trúc tham khảo**, không nằm trong Gradle project in-memory. Nó mô tả cách dùng composite PK/FK để chống cross-tenant references ở tầng dữ liệu. Chọn UUID toàn cục cũng có thể dùng, nhưng cần tenant predicate và ràng buộc tương ứng. Unique indexes trên email/external ID cũng phải được cân nhắc scope `(tenant_id, external_id)` nếu tính duy nhất chỉ trong tenant.

## 11. PostgreSQL Row-Level Security (RLS) là lớp phòng vệ bổ sung

Nếu dùng **shared database/shared schema** trên PostgreSQL, RLS có thể giảm tác động của một truy vấn ứng dụng quên `WHERE tenant_id = ?`. Tuy nhiên bật RLS không có nghĩa tự động an toàn; cần chính sách, DB role và transaction context chuẩn.

Ví dụ khái niệm trên bảng PostgreSQL `orders` với tenant_id kiểu VARCHAR:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON orders
    FOR ALL
    USING (
        tenant_id = current_setting(
            'app.current_tenant', true)
    )
    WITH CHECK (
        tenant_id = current_setting(
            'app.current_tenant', true)
    );

ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

**Ý nghĩa:**
- `USING` giới hạn những rows có thể thấy/update/delete.
- `WITH CHECK` kiểm rows mới/được cập nhật thuộc tenant được phép.
- `current_setting(..., true)` trả NULL nếu biến chưa được set; phép so sánh với NULL không true, nên RLS không trả row theo policy đó.
- `FORCE ROW LEVEL SECURITY` bắt table owner tuân theo policy; nhưng **superuser hoặc DB role có BYPASSRLS vẫn có thể bỏ qua RLS**, nên ứng dụng bình thường phải dùng role ít đặc quyền.
- Bảng thật phải có indexes thích hợp, migrations, policy cho từng operation và kiểm kỹ owner/admin exceptions.

**Giới hạn quan trọng:** RLS không thay object ownership logic trong cùng tenant nếu policy mới chỉ so tenant. Khi cần chủ sở hữu, phải bổ sung owner checks ở policy hoặc tại service/SQL predicates. Cũng phải kiểm bảo vệ dữ liệu ở **views, SECURITY DEFINER functions, background jobs và migrations**, nơi đặc quyền có thể khác application role.

**Cách set tenant context:** Với connection pooling, không nên dùng session-level `SET app.current_tenant` rồi thả connection vào pool; tenant cũ có thể rò sang request sau. Trong transaction chứa các truy vấn, dùng **`SET LOCAL`** hoặc `set_config(..., true)` với giá trị từ identity đã xác thực và bảo đảm transaction boundary. Ví dụ:

~~~sql
BEGIN;
SET LOCAL app.current_tenant = 'tenant-a';
SELECT id, title FROM orders;
COMMIT;
~~~

Đây là ví dụ SQL trong **một transaction PostgreSQL**, không phải lệnh mặc định của H2 hoặc một cấu hình tự động của Spring Boot. Khi dùng JDBC driver, bind tenant an toàn hoặc gọi `SELECT set_config('app.current_tenant', :tenant, true)` qua prepared statement trong đúng transaction/connection; không nội suy chuỗi user vào `SET LOCAL`.

**RLS test bắt buộc:** Test với **database role production thực tế**, không dùng superuser hoặc owner chưa FORCE rồi tưởng policy đang hoạt động. Kiểm tenant A→B→A trên connections được tái sử dụng, concurrent requests và thread pool; nếu `tenantId` thiếu hoặc không hợp lệ thì fail closed. PostgreSQL RLS là defense-in-depth, không phải một công tắc tự bảo đảm application-level policy.

## 12. Cách viết kiểm thử database và JWT thực tế

### 12.1. Tests với @JdbcTest / @DataJpaTest

Khi đổi in-memory store sang database:
1. Seed ít nhất **2 tenants, mỗi tenant có 2 owners**, có các IDs trùng dạng đoán được nếu schema cho phép.
2. Test repository `findByIdAndTenantId` với cùng ID/khác tenant, trả empty; test join và pagination count.
3. Test UPDATE/DELETE dùng điều kiện tenant/owner, xác minh affected rows và **không thay đổi dữ liệu của tenant khác**.
4. Test business side effects như audit records, file references, payments, notifications có tenant scope riêng.
5. Test `@Sql` scripts đúng transaction/cleanup, không để dữ liệu của một tenant test chảy sang test tiếp.
6. Nếu dùng Testcontainers PostgreSQL, chạy với DB role/connection pool/RLS giống production. H2 không mô phỏng PostgreSQL RLS đầy đủ.
7. Test concurrency: hai transactions cùng thử chuyển quyền/sửa order; kiểm không có cửa TOCTOU.
8. Test cache keys/search indexes: lookup có `(tenantId,id)` hoặc partition tương ứng.
9. Test migrations đảm bảo các foreign keys/indexes/policies trên bảng mới tiếp tục có tenant scope.
10. Khi có async job hoặc scheduled worker, kiểm nó nhận identity/context authorization rõ, không lấy một default tenant toàn cục.

Ví dụ dùng NamedParameterJdbcTemplate ở tầng repository:

~~~java
// Snippet trong repository có NamedParameterJdbcTemplate jdbc.
var params = new MapSqlParameterSource()
        .addValue("id", requestedId)
        .addValue("tenant", authenticatedTenantId);

List<OrderData> rows = jdbc.query(
        """
        SELECT id, tenant_id, owner_id, title
        FROM orders
        WHERE id = :id AND tenant_id = :tenant
        """,
        params,
        (rs, n) -> new OrderData(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getString("owner_id"),
                rs.getString("title")));
~~~

Đây là **snippet**, không thuộc project in-memory chạy được. Nó có placeholders dạng named parameters, không concat input vào SQL; cần imports `NamedParameterJdbcTemplate`, `MapSqlParameterSource`, `List` và `OrderData` theo package.

### 12.2. JWT và token validation phải kiểm riêng

Một token có `tenant_id=tenant-a` chỉ đáng tin khi authentication layer đã:
- Xác minh signature bằng keys/JWKS đáng tin.
- Xác minh issuer (`iss`), audience (`aud`), expiry (`exp`), not-before nếu dùng, và token type/scope.
- Ràng buộc subject (`sub`) với user/tenant membership được phép.
- Chuyển roles/scopes thành authorities đúng prefix (ví dụ ORDER_READ, ROLE_TENANT_ADMIN).
- Giải quyết user có nhiều tenants: active tenant chỉ hợp lệ khi đã được phép cho membership đó.
- Không cho client tự đổi `X-Tenant-Id` rồi dùng như đã được IdP xác nhận.

Với Spring Security OAuth2 Resource Server, có thể dùng `jwt()` của `spring-security-test` để test claims mapping ở controller, nhưng nó **không thực hiện xác minh chữ ký JWT** vì đây là mock authentication; cần test riêng cho JwtDecoder/issuer/JWKS khi chính authentication là mục tiêu. Test trong bài dùng `user(TenantUser...)` để tránh giả vờ đã kiểm security token.

### 12.3. Method security và self-invocation

`@PreAuthorize` dùng proxy ở Spring-managed beans. Nếu một method trong cùng class gọi `this.read(id)`, lời gọi đó có thể **không đi qua method-security interceptor**, làm `@PreAuthorize` không được chạy. Vì vậy:
- Đặt authorization ở boundary service rõ ràng.
- Đảm bảo controller/invoker đi qua Spring-managed proxy.
- Kiểm cả entrypoints không phải HTTP (message listener, scheduled job, batch).
- Không dựa duy nhất vào annotations nếu repository cho phép truy vấn toàn cục mà không có tenant predicate.

Một số project dùng `@PostAuthorize` để kiểm `returnObject.ownerId == authentication.name` **sau khi** lấy object. Nó hữu ích trong trường hợp phù hợp nhưng không bảo vệ side effect đã xảy ra, và object có thể đã được load/log trước khi bị từ chối. Với thao tác ghi, kiểm **trước side effect** và scope truy vấn/UPDATE càng sớm càng tốt.

## 13. Các lỗi thiết kế và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách kiểm thử/sửa |
|---|---|---|
| Alice đọc được order của Bob | Chỉ check tenant, không check owner | Cùng-tenant non-owner negative test |
| Tenant B xem order tenant A | Repository findById toàn cục hoặc role bypass | Cross-tenant GET/PATCH/list assertions |
| Tenant admin A đọc mọi tenant | Admin OR owner check trước tenant check | Tenant scope bắt buộc bên ngoài nhánh admin |
| Query list đúng nhưng totalCount lộ | COUNT query không tenant-scoped | Test pagination metadata |
| `@WithMockUser` test không có tenantId | Principal mặc định kiểu User | Custom test UserDetails/Authentication |
| Header X-Tenant-Id đổi dữ liệu trả về | Dùng client-supplied tenant làm authority | Fake header test; derive tenant từ auth |
| PATCH cho sửa ownerId/tenantId | Bind trực tiếp JPA entity/DTO quá rộng | Allowlist request DTO + mass-assignment test |
| Missing ID trả 500 thay 404 | Missing repository row không xử lý | `ResponseStatusException(NOT_FOUND)` hoặc exception mapper |
| `@PreAuthorize` không hoạt động | Quên `@EnableMethodSecurity` | Missing authority tests |
| HTTP anonymous vẫn vào controller | SecurityFilterChain không apply URL | MockMvc 401 test, filter integration |
| CSRF 403 che mất owner test | PATCH không có `.with(csrf())` | Cấp CSRF để kiểm policy; test CSRF riêng |
| Test PATCH qua nhưng DB ghi sai tenant | Service check xong update WHERE id | SQL affected row + cross-tenant DB test |
| Test pass riêng nhưng fail cả suite | Shared singleton fixture/state | Reset @BeforeEach, isolation, no parallel writes |
| Tất cả test dùng admin nên pass | Thiếu user/owner/other-tenant cases | Permission matrix positive và negative |
| 404 khác biệt giữa tenants | Policy trả response khác | Đồng nhất not-found policy và không leak body |
| Cache trả object tenant khác | Cache key chỉ có id | Tenant-aware cache key và tests |
| SQL JOIN kéo cross-tenant child | FK/join không gắn tenant | Composite foreign keys, scoped join |
| RLS không tác dụng | Dùng superuser/owner bypass | Role thường + FORCE RLS + kiểm policy |
| Tenant context của PgBouncer bị lẫn | Session SET trong pooled connection | SET LOCAL trong transaction |
| Async worker có tenant rỗng/cũ | SecurityContext ThreadLocal không propagation đúng | Explicit trusted context/tenant scope, fail closed |
| Direct service invocation bypass guard | Self-invocation không qua proxy | Test direct/indirect paths, service policy |

### 13.1. Quy trình debug thực tế

1. Xác nhận request **đã authenticated** với principal đúng, không nhầm role với userId.
2. Xác nhận action authority có quyền READ/WRITE tương ứng.
3. Xác nhận `tenantId` đến từ nguồn **đã được verify**, không phải path/header/body tùy ý.
4. Kiểm object row đang thuộc tenant nào, owner nào và admin role có scope nào.
5. Xem query repository có `WHERE tenant_id=?` hoặc RLS đang hoạt động không.
6. Kiểm GET detail, list/search/pagination, PATCH/DELETE, export và batch API có dùng cùng policy không.
7. Nếu 403, kiểm missing authority/owner; nếu 404, kiểm tenant-scoped lookup và tồn tại trong đúng tenant.
8. Nếu dùng `@PreAuthorize`, xác minh `@EnableMethodSecurity`, Spring proxy và absence of self-invocation bypass.
9. Nếu dùng `MockMvc`, xác minh security filters được bật và request có `.with(user(customPrincipal))`.
10. Nếu dùng CSRF cho state-changing requests, dùng `.with(csrf())` ở test đang kiểm ownership.
11. Kiểm update **không xảy ra** sau 403/404, bằng lần GET hợp lệ hoặc DB query.
12. Với DB thật, test transaction/concurrency và cache isolation thay vì chỉ xem HTTP status.
13. Ghi security audit records không tiết lộ body, JWT, secrets và dữ liệu của tenant khác.
14. Khi policy thay đổi, cập nhật permission matrix trước khi điều chỉnh assertions.

## 14. Bài tập thực hành

**Bài 1 — BOLA:** Xóa `.filter(row -> row.tenantId().equals(tenantId))` ở `findInTenant`, rồi thử Mallory GET order 100. Test nào fail? Hãy chỉ ra chỗ tenant scope bị mất.

**Bài 2 — Ownership:** Bỏ kiểm `row.ownerId()` và chỉ giữ tenant. Test của Bob khi GET/PATCH order Alice còn an toàn không?

**Bài 3 — Tenant admin:** Cho admin role bypass tenant; chạy hai tests admin cross-tenant. Vì sao role “admin” không mặc định là global?

**Bài 4 — List:** Đổi `listMineOrTenantAdmin` thành trả mọi orders trong tenant. Với Alice thường, response có bao nhiêu records? Khi nào policy thực sự cho phép shared orders?

**Bài 5 — 401/403/404:** Tạo tình huống anonymous, user thiếu ORDER_READ, Bob cùng tenant không là owner, Mallory tenant khác, và ID 999 không tồn tại. Chọn status/body nhất quán theo contract.

**Bài 6 — Header spoof:** Gửi `X-Tenant-Id: tenant-b` với principal Alice tenant-a. Vì sao header này chỉ là untrusted input? Thiết kế cách chọn active tenant khi user hợp pháp thuộc nhiều tenants.

**Bài 7 — Mass assignment:** Cho JSON gửi `ownerId`, `tenantId`, `isAdmin`, `title` và kiểm chỉ trường title được thay theo chính sách. Nếu bật Jackson fail-on-unknown, status nào phù hợp?

**Bài 8 — PATCH:** Thử một request của Bob có CSRF hợp lệ, một request của Alice thiếu CSRF và một request của read-only Alice có CSRF. Vì sao cả ba có thể bị 403 nhưng nguyên nhân khác nhau?

**Bài 9 — JDBC:** Viết `UPDATE ... WHERE id=:id AND tenant_id=:tenantId AND (owner_id=:user OR :isAdmin=true)`, kiểm affected row count cho các actor.

**Bài 10 — JPA:** Viết Spring Data repository method tenant-scoped cho findOne và list. Kiểm generated SQL và COUNT query dùng cùng filter.

**Bài 11 — PostgreSQL RLS:** Enable + FORCE RLS, chạy tests bằng role không BYPASSRLS; `SET LOCAL` tenant A rồi B trong các transactions khác nhau. Dữ liệu có bị rò khi connection được reuse không?

**Bài 12 — Cache:** Thêm `@Cacheable`. Nếu cache key chỉ là `id`, vì sao có nguy cơ user tenant B nhận kết quả tenant A? Thiết kế key `(tenantId,id)`.

**Bài 13 — Background jobs:** Một scheduled task không có HTTP SecurityContext. Thiết kế service account được ủy quyền rõ tenant scope, không lấy default tenant toàn cục.

**Bài 14 — Export & batch:** Với request chứa nhiều order IDs, xử lý mỗi id bằng tenant-aware query hoặc kiểm toàn bộ tập quyền trước khi export. Không trả partial unauthorized data do chỉ lọc client-side.

**Bài 15 — Token verification:** Viết JWT converter lấy tenantId/permissions từ claims đã validate; thử token sai issuer, hết hạn, missing tenant membership. Phân biệt unit test claim mapping với integration test chữ ký thật.

**Bài 16 — Property-based authorization:** Sinh cặp principals/tenants/owners ngẫu nhiên, assert `crossTenantAccessAlwaysDenied`; phải giữ một tập role ngoại lệ có scope rõ.

**Bài 17 — Concurrency:** Giả lập hai transactions đổi owner/update title giữa check và write; bảo đảm điều kiện ownership/tenant được đánh giá khi UPDATE commit.

**Bài 18 — Security review:** Duyệt toàn bộ routes có id/path/query/body, tạo permission matrix và negative test trước khi release; không chỉ test route được gọi mà test đối tượng thực bị từ chối.

## 15. Tham khảo chính thức

- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): IDOR/BOLA, kiểm quyền trên mọi object access.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege và authorization checks.
- [OWASP Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): tenant-scoped queries, isolation, cache keys và RLS.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và proxy behavior.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): SecurityFilterChain, authenticated request rules.
- [Spring Security — MockMvc test authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user(UserDetails)` và `@WithMockUser`.
- [Spring Security — MockMvc CSRF testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `.with(csrf())`, CSRF failure tests.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, Spring Security test integration.
- [Spring Data JPA — Repository Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): tenant-aware query patterns.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, policies, owner/superuser bypass, USING/WITH CHECK.
- [PostgreSQL — SET](https://www.postgresql.org/docs/current/sql-set.html): session/transaction configuration và SET LOCAL.

**Ghi nhớ:** **Được phép gọi endpoint không có nghĩa được phép mở mọi ID.** Luôn kiểm **action authority + đúng tenant + owner hoặc tenant-scoped admin**; tenant scope phải bắt buộc trước mọi nhánh admin. Lấy identity từ nguồn authentication đáng tin, không cấp quyền theo raw header/body. Viết tests gồm **cùng tenant khác owner, khác tenant, tenant admin khác tenant, GET list, PATCH, mass-assignment và negative cases**; sau 403/404 còn phải kiểm dữ liệu không bị thay. Để an toàn production, nâng phép kiểm lên **tenant-scoped SQL UPDATE/SELECT, database constraints, RLS đúng role, JWT validation và cross-tenant isolation tests**.
