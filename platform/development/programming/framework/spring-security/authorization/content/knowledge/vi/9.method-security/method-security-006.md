# @RolesAllowed, @PermitAll, @DenyAll và ngữ nghĩa JSR-250 trong Spring Security

## 1. Mục tiêu: ba annotation ngắn nhưng có ranh giới bảo mật riêng

Một ứng dụng Java dùng Spring Security muốn mô tả quyền trên service theo cách không phụ thuộc vào cú pháp SpEL. Nhóm phát triển có các thao tác:

- `listPublicNews()`: công khai nội dung đã xuất bản.
- `viewDashboard()`: chỉ role USER.
- `reviewSubmission()`: role REVIEWER **hoặc** ADMIN.
- `deleteUser()`: chỉ role ADMIN, còn phải kiểm tra tenant và phạm vi quản lý.
- `obsoleteDangerousOperation()`: bị khóa tuyệt đối trong lúc chuyển đổi nghiệp vụ.

Java/Jakarta cung cấp bộ annotation JSR-250/Jakarta Common Annotations cho các tình huống kiểu này:

```java
@RolesAllowed("ADMIN")                 // yêu cầu role cho phép
@RolesAllowed({"REVIEWER", "ADMIN"})   // một trong các role
@PermitAll                              // không đòi role tại lớp JSR-250
@DenyAll                                // từ chối mọi role tại lớp JSR-250
```

Spring Security có thể thực thi chúng trên Spring-managed beans **khi method security JSR-250 được bật**. Nhưng việc đặt annotation không tự động bảo vệ mọi request: bộ lọc HTTP, security context, AOP proxy, role prefix và quyền trên từng tài nguyên vẫn là các phần độc lập của thiết kế.

Bài học này giúp bạn:

1. Hiểu `@RolesAllowed`, `@PermitAll` và `@DenyAll` đúng theo ngữ nghĩa Jakarta/JSR-250.
2. Bật `@EnableMethodSecurity(jsr250Enabled = true)` và dùng package `jakarta.annotation.security` trong Spring Boot 3+/Spring Security 6+/7.
3. Phân biệt role name với `GrantedAuthority` thật và prefix `ROLE_`.
4. Xác định annotation ở **class** và **method** tương tác như thế nào.
5. Không nhầm `@PermitAll` với `permitAll()` của HTTP, không dùng nó để bỏ qua CSRF, authentication hoặc các advisor khác.
6. Kiểm thử với `@WithMockUser`, `@WithAnonymousUser`, `MockMvc` và negative cases.
7. Nhận diện giới hạn: không có SpEL cho object-level authorization, self-invocation, asynchronous calls, conflicting annotations, stale authorities, và nhiều filter chains.
8. Chọn giữa JSR-250, `@Secured` và `@PreAuthorize` theo độ phức tạp của policy.

**Phạm vi:** Spring Security Servlet/Spring MVC, Java 17+, JUnit 5, Spring Security Test. Các snippet có tên type nghiệp vụ là **fragment tích hợp**; ví dụ Java 17 độc lập ở mục 13 mô phỏng chính sách và được ghi rõ không phải implementation Spring.

## 2. JSR-250 là gì? Jakarta và javax có liên quan ra sao?

### 2.1. Nguồn gốc và package

JSR-250 là bộ *Common Annotations for the Java Platform*. Trong các hệ sinh thái Java EE cũ, annotation bảo mật thường được import từ:

```java
// Dùng trong một số dự án Java EE/Spring cũ:
import javax.annotation.security.RolesAllowed;
import javax.annotation.security.PermitAll;
import javax.annotation.security.DenyAll;
```

Sau khi Jakarta EE đổi namespace, ứng dụng Spring Framework 6+/Spring Boot 3+/Spring Security 6+ dùng package:

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
```

Đừng nhầm chúng với `jakarta.ws.rs` hoặc `org.springframework.security.access.annotation.Secured`. Các tên annotation gần giống nhưng được định nghĩa bởi những API khác nhau.

**Java 17 không tự cung cấp toàn bộ Jakarta Annotations API chỉ vì JDK đã cài.** Trong một dự án Spring Boot, dependency có thể đã được transitively quản lý; nếu compiler báo `package jakarta.annotation.security does not exist`, kiểm tra dependency graph và thêm `jakarta.annotation-api` tương thích với BOM. Không tự chuyển về `javax.annotation.security` để chữa lỗi trong project Spring 6/7.

### 2.2. Chúng là metadata, Spring Security mới quyết định thực thi

Annotation:

```java
@RolesAllowed("ADMIN")
public void deleteUser(String id) { ... }
```

chỉ đánh dấu metadata trên code. Nếu method security chưa được kích hoạt hoặc lời gọi không đi qua interceptor tương ứng, annotation **không tự kiểm tra** `Authentication`. Không thể dựa vào việc IDE hiển thị annotation để kết luận method đã được bảo vệ.

Spring Security hiện đại dùng `Jsr250AuthorizationManager` cùng method interceptor để đánh giá `@RolesAllowed`/`@PermitAll`/`@DenyAll` khi cấu hình JSR-250 được bật. Cơ chế này thuộc **method security**, khác với `SecurityFilterChain` bảo vệ request ở cấp HTTP.

### 2.3. Vị trí khai báo

Các Jakarta annotation này có `@Target({TYPE, METHOD})` và `@Retention(RUNTIME)`:

- Đặt trên **class**: tạo chính sách mặc định cho các method thuộc class.
- Đặt trên **method**: áp dụng cho method cụ thể, có thể ghi đè chính sách JSR-250 của class theo quy tắc đặc tả.
- Đặt trên **interface/service method**: Spring Security có hỗ trợ annotation ở interface trong cấu hình method proxy phù hợp, nhưng cần test proxy thực tế, nhất là khi nhiều interface có policy xung đột.

Đây không phải annotation dành cho *field* hoặc *tham số method*. Với rule kiểm tra tham số/giá trị trả về, dùng `@PreAuthorize`, `@PostAuthorize`, custom bean/policy hoặc cách khác phù hợp.

## 3. Ngữ nghĩa của @RolesAllowed

### 3.1. Một role

```java
@RolesAllowed("ADMIN")
public String readAdminDashboard() {
    return "admin";
}
```

Trong Spring Security với prefix mặc định, `@RolesAllowed("ADMIN")` thường yêu cầu một `GrantedAuthority` mang chuỗi `ROLE_ADMIN`. User có `ROLE_USER` không qua; user có `ROLE_ADMIN` có thể qua **kiểm tra JSR-250**, miễn không bị rule khác từ chối.

`@RolesAllowed("ADMIN")` không tự kiểm tra ID của người dùng, tenant, trạng thái tài khoản đích hoặc điều kiện như “chỉ xem tài liệu mình sở hữu”. Nó chỉ thể hiện một điều kiện role tại thời điểm method invocation.

### 3.2. Nhiều role dùng OR, không phải AND

```java
@RolesAllowed({"REVIEWER", "ADMIN"})
public String reviewSubmission(String id) {
    return "review-" + id;
}
```

Danh sách role nghĩa là **được một trong các role cho phép**:

```text
ROLE_REVIEWER -> được qua điều kiện role
ROLE_ADMIN    -> được qua điều kiện role
ROLE_USER     -> không đạt điều kiện role
```

Không cần đồng thời REVIEWER và ADMIN. Nếu nghiệp vụ yêu cầu **hai permission cùng lúc**, ví dụ `report:review` **và** `report:export`, `@RolesAllowed({"REVIEWER", "EXPORTER"})` **không phải** một phép AND. Dùng `@PreAuthorize` với biểu thức AND hoặc một domain authorization manager/policy bean.

### 3.3. Role name và chuỗi authority thật

Phân biệt rõ:

| Annotation | Authority mặc định ứng dụng cần cấp | Ghi chú |
| --- | --- | --- |
| `@RolesAllowed("USER")` | `ROLE_USER` | Role USER |
| `@RolesAllowed("ADMIN")` | `ROLE_ADMIN` | Role ADMIN |
| `@RolesAllowed({"ADMIN", "AUDITOR"})` | `ROLE_ADMIN` **hoặc** `ROLE_AUDITOR` | Một trong hai |
| `@PreAuthorize("hasAuthority('report:read')")` | `report:read` | Permission chính xác, không tự prefix |
| `@PreAuthorize("hasRole('ADMIN')")` | `ROLE_ADMIN` theo convention | Spring expression, khác annotation JSR-250 |

`@RolesAllowed("ADMIN")` là cách đọc dễ hiểu khi ứng dụng theo chuẩn role prefix `ROLE_`. Đừng trộn `ADMIN`, `ROLE_ADMIN`, `SCOPE_admin` và `admin:read` rồi coi chúng đồng nghĩa; chúng là các chuỗi khác nhau nếu không có ánh xạ rõ.

### 3.4. Prefix ROLE_ có thể được tùy chỉnh

`Jsr250AuthorizationManager` cung cấp `setRolePrefix(String)`, mặc định `ROLE_`. Một dự án legacy có thể đổi prefix hoặc dùng role được cấp theo convention khác. Khi làm vậy, phải nhất quán giữa:

- Nguồn `Authentication.getAuthorities()`.
- Quy tắc JSR-250 cho method.
- HTTP `hasRole`/`hasAuthority`.
- `@Secured`/`@PreAuthorize` và role hierarchy nếu cùng được dùng.
- JWT/OAuth converter, user directory và test fixtures.

Không suy rằng đổi một `GrantedAuthorityDefaults` hay một bean tự động cập nhật **mọi** custom authorization manager ở mọi Spring Security version. Đọc Javadoc theo resolved dependency và test cả HTTP/method paths.

## 4. Ngữ nghĩa của @PermitAll

### 4.1. Không yêu cầu role tại điểm JSR-250

```java
@PermitAll
public String publicCatalog() {
    return "public catalog";
}
```

`@PermitAll` mô tả method không yêu cầu một role cụ thể **trong chính sách JSR-250**. Trong cấu hình method security đúng, cả principal không có role đặc biệt cũng có thể đi qua JSR-250 interceptor cho method này.

Nhưng nó **không phải** “bỏ qua mọi lớp bảo mật của ứng dụng”. Nếu HTTP filter đang yêu cầu role ADMIN cho `GET /api/catalog`, request của guest vẫn bị chặn trước khi controller gọi service, dù method service có `@PermitAll`.

### 4.2. @PermitAll không phải HTTP permitAll()

So sánh:

```java
// Rule của SecurityFilterChain (HTTP)
.requestMatchers(HttpMethod.GET, "/api/catalog").permitAll()
```

và:

```java
// Rule của method security (service)
@PermitAll
public List<CatalogItem> publicCatalog() { ... }
```

Rule thứ nhất áp dụng cho **HTTP request**. Annotation thứ hai áp dụng cho **method invocation** qua interceptor. Chúng thường phối hợp khi muốn xuất bản một API công khai, nhưng không thay thế nhau.

Ví dụ:

| HTTP rule | Method annotation | Guest GET tới endpoint | Kết luận |
| --- | --- | --- | --- |
| `permitAll()` | `@PermitAll` | Có thể vào controller/service | Các lớp khác vẫn có thể xử lý/từ chối |
| `authenticated()` | `@PermitAll` | Bị chặn nếu chưa xác thực | Method-level public không bỏ HTTP rule |
| `hasRole("ADMIN")` | `@PermitAll` | Bị chặn nếu không phải admin | HTTP mạnh hơn ở đường request đó |
| `permitAll()` | `@RolesAllowed("ADMIN")` | Có thể qua HTTP nhưng bị từ chối ở service | Method rule vẫn hiệu lực |
| `permitAll()` | `@DenyAll` | Có thể qua HTTP nhưng bị từ chối ở service | @DenyAll chặn invocation |

“Có thể” là từ khóa quan trọng: ứng dụng còn `CsrfFilter`, các security advisors khác, validation và policy domain.

### 4.3. @PermitAll không tắt CSRF

Với một method cập nhật tài nguyên:

```java
@PermitAll
public String submitFeedback(String text) { ... }
```

nếu nó được gọi từ `POST /api/feedback` trong ứng dụng session/cookie có CSRF protection, request có thể bị từ chối vì thiếu CSRF token dù JSR-250 cho phép method. `@PermitAll` không vô hiệu hóa `CsrfFilter`, không bỏ qua rate limits và không xác nhận input đáng tin.

### 4.4. @PermitAll không bỏ qua những advisor khác

Nếu một method đồng thời có:

```java
@PermitAll
@PreAuthorize("hasAuthority('report:read')")
public String readReport() { ... }
```

và cả JSR-250 lẫn pre/post method security được bật, các method-security checks được thực thi độc lập theo cơ chế interceptor; một `@PermitAll` **không biến `@PreAuthorize` thành allow**. Cách dễ hiểu là các điều kiện đang hoạt động đều phải cho phép method thực thi.

Tránh đặt nhiều annotation chính sách khác loại trên một method trừ khi **đó là AND có chủ đích** và đã được test; code review sẽ dễ bỏ sót vì thấy `@PermitAll` tưởng rằng method đã public.

## 5. Ngữ nghĩa của @DenyAll

### 5.1. Từ chối tại điểm method-security JSR-250

```java
@DenyAll
public String deprecatedAdministrationOperation() {
    return "should not execute";
}
```

Nếu JSR-250 method security đang hoạt động và invocation đi qua interceptor, `@DenyAll` từ chối ngay cả với principal có `ROLE_ADMIN` hoặc quyền rộng. Đó là một **hàng rào theo method** hữu ích khi loại bỏ chức năng nguy hiểm, khóa tạm một use case hoặc phòng thủ cho method chưa được phép sử dụng.

Nó không tự động xóa endpoint, không xóa method implementation và không bảo đảm một lời gọi **bỏ qua proxy** không thể thực thi. Với hành động thật sự cấm, nên **gỡ đường gọi** khỏi API, tắt feature flag, hoặc loại bỏ code không cần thiết thay vì dựa duy nhất vào một annotation.

### 5.2. @DenyAll không đồng nghĩa HTTP denyAll

```java
.requestMatchers("/api/internal/**").denyAll()
```

cấm HTTP requests khớp rule. `@DenyAll` cấm method invocation được JSR-250 interceptor nhìn thấy. Một background job có thể gọi service mà không đi qua HTTP filter, nên method-level protection rất hữu ích; nhưng nếu job gọi trực tiếp object/this method mà bỏ AOP proxy, annotation cũng có thể bị vô hiệu hóa.

### 5.3. Không xem @DenyAll là cơ chế phân quyền theo trạng thái

“Chức năng đang bảo trì” hoặc “tài khoản bị khóa” có thể đòi policy động. `@DenyAll` là một quyết định tĩnh tại annotation, không kiểm tra maintenance state theo thời gian. Muốn cho phép sau khi được phê duyệt/feature flag thay đổi, dùng rule có ngữ nghĩa nghiệp vụ rõ ràng thay vì thay annotation trực tiếp ngoài chu kỳ deploy.

### 5.4. Test side effects, không chỉ exception

Test nên xác minh method bị chặn **trước khi** ghi dữ liệu hay phát sự kiện. Nếu gọi method có `@DenyAll` và nhận `AccessDeniedException`, đồng thời cần bảo đảm database row, message queue, audit action nghiệp vụ hoặc counter không đổi.

Lưu ý các bộ xử lý denied method tùy chỉnh trong một số dòng Spring Security mới có thể biến exception thành response/value thay thế; nếu dự án bật chúng, test đúng contract. Mặc định thường bị từ chối bằng exception trước khi chạy body.

## 6. Bật JSR-250 method security một cách tường minh

### 6.1. Cấu hình với Spring Security hiện đại

Tạo một class Spring `@Configuration`:

```java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
public class MethodSecurityConfig {
}
```

Từ `@EnableMethodSecurity`, Spring Security tạo method-security advisors. `jsr250Enabled = true` yêu cầu bật riêng support cho `@RolesAllowed`, `@PermitAll` và `@DenyAll`; trong các cấu hình Spring Security hiện đại, JSR-250 **không tự được bật chỉ vì có spring-boot-starter-security**. Support `@PreAuthorize`/`@PostAuthorize` thường được bật mặc định khi `@EnableMethodSecurity` hoạt động, nhưng `@Secured` cần `securedEnabled = true` nếu muốn dùng.

Đừng dùng lời gọi mới `@EnableMethodSecurity` và tài liệu `@EnableGlobalMethodSecurity` cổ trong cùng một module mà không hiểu migration: API `@EnableGlobalMethodSecurity` là đường cấu hình cũ/deprecated.

### 6.2. Dependency và import cần có

Trong dự án Spring Boot 3+/Spring 6+/Security 6+, dùng:

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
```

Nếu build thiếu Jakarta annotations dependency, dự án cần `jakarta.annotation:jakarta.annotation-api` ở version tương thích. Ví dụ dạng Maven **fragment**, thường để Spring Boot BOM quản lý phiên bản:

```xml
<dependency>
    <groupId>jakarta.annotation</groupId>
    <artifactId>jakarta.annotation-api</artifactId>
</dependency>
```

Chỉ thêm nếu dependency chưa có. Đừng pin version tùy ý chống lại dependency management của ứng dụng. Với Spring Boot 2/Spring Security đời cũ, package và annotation migration cần kế hoạch riêng; không thay `javax` bằng `jakarta` trong toàn project mà chưa nâng Spring Framework tương ứng.

### 6.3. Method security chỉ áp dụng với bean/proxy được quản lý

`@EnableMethodSecurity` dùng Spring AOP interceptor theo mặc định. Vì vậy:

- Class/method phải được Spring quản lý và advice phải nhìn thấy invocation.
- Lời gọi qua bean proxy từ một bean khác thường được kiểm tra.
- `this.someSecuredMethod()` tự gọi trong cùng object thường **bỏ qua proxy**.
- Private/final/non-proxyable methods không phải ranh giới method security đáng tin.
- Method không có annotation security không tự bị từ chối bởi method security; cần quy tắc HTTP/service fallback rõ.
- Nếu dùng AspectJ mode, đặc tính weaving khác và phải cấu hình/test riêng.

**Nguyên tắc triển khai:** đặt method authorization tại **public service boundary** và kiểm thử bằng Spring-managed bean thật. Controller authentication không thay thế bảo vệ service khi use case còn được gọi từ scheduled job, message listener hoặc API khác.

## 7. Ví dụ cấu hình và service hoàn chỉnh ở lớp Spring

### 7.1. Service demo với chính sách ở class và method

Tạo `PolicyService.java` trong package `com.example.security`. Đây là **class biên dịch được khi project có Jakarta Annotations + Spring Context + Spring Security method configuration**:

```java
package com.example.security;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.stereotype.Service;

@Service
@RolesAllowed("USER")
public class PolicyService {

    private final AtomicInteger deniedBodyCalls = new AtomicInteger();

    // Phương thức ghi đè rule class USER bằng PermitAll.
    @PermitAll
    public String publicNotice() {
        return "public";
    }

    // Kế thừa rule class: cần role USER.
    public String privateDashboard() {
        return "dashboard";
    }

    // Ghi đè rule class USER: EDITOR hoặc ADMIN.
    @RolesAllowed({"EDITOR", "ADMIN"})
    public String editDraft() {
        return "edited";
    }

    // Tuyệt đối không gọi body qua JSR-250 interceptor.
    @DenyAll
    public String disabledOperation() {
        deniedBodyCalls.incrementAndGet();
        return "disabled-body-ran";
    }

    // Chỉ để test: đọc counter không cần role.
    @PermitAll
    public int disabledBodyCallCount() {
        return deniedBodyCalls.get();
    }
}
```

Ý nghĩa:

1. Ở class level, `@RolesAllowed("USER")` là policy mặc định cho method chưa có annotation JSR-250 riêng.
2. `publicNotice` gắn `@PermitAll`: trong JSR-250, method-level declaration thay rule class cho method này.
3. `privateDashboard` không có annotation riêng: yêu cầu `ROLE_USER`.
4. `editDraft` gắn `@RolesAllowed({"EDITOR","ADMIN"})`: role EDITOR **hoặc** ADMIN, **không mặc nhiên bắt thêm USER** theo chính sách JSR-250 được ghi đè. Nếu business cần ADMIN vừa có USER vừa có EDITOR, phải mô tả bằng policy riêng chứ không suy từ class.
5. `disabledOperation` gắn `@DenyAll`: body không được chạy nếu method interceptor hoạt động.
6. `disabledBodyCallCount` giúp test xác nhận không có side effect khi deny.

**Cẩn thận:** nếu ứng dụng có các advisors khác, annotation từ interface, AOP custom hoặc hierarchy, chúng cũng có thể ảnh hưởng kết quả. Khi có xung đột hoặc ghi đè, không suy bằng cách đọc một annotation đơn lẻ; test với proxy/context thực.

### 7.2. Cấu hình HTTP cho service đó

Giả sử có REST controller gọi `PolicyService`. Cấu hình HTTP fragment:

```java
http.authorizeHttpRequests(auth -> auth
        // Public route rõ ràng, không mở mọi API bằng wildcard.
        .requestMatchers(HttpMethod.GET, "/api/notices").permitAll()
        .requestMatchers("/api/dashboard/**").authenticated()
        .requestMatchers("/api/drafts/**").authenticated()
        .requestMatchers("/api/internal/**").denyAll()
        .anyRequest().denyAll()
);
```

Đây là **fragment Spring Security Servlet**, không phải class standalone. Nó minh họa defense in depth: HTTP route đã được phân loại, trong service còn có role policy theo JSR-250. Nếu một route là public nhưng service `@RolesAllowed("ADMIN")`, người không có role vẫn bị từ chối tại service; nếu service `@PermitAll` nhưng HTTP route đòi auth, guest vẫn không qua HTTP rule.

Một route POST/PATCH phải xử lý CSRF phù hợp trong ứng dụng session/cookie. Permission đối với tài nguyên cụ thể (tenant, owner, draft status) không thể suy ra chỉ từ URL hoặc JSR-250 roles.

## 8. Class-level và method-level: quy tắc ghi đè và mâu thuẫn

### 8.1. Mặc định ở class

```java
@RolesAllowed("USER")
public class AccountService {

    public String profile() {
        return "profile";
    }

    @RolesAllowed("ADMIN")
    public String lockAccount() {
        return "locked";
    }

    @PermitAll
    public String systemStatus() {
        return "up";
    }

    @DenyAll
    public String legacyDanger() {
        return "forbidden";
    }
}
```

Theo ngữ nghĩa Jakarta annotations, policy trên method **ghi đè** policy role của class cùng nhóm JSR-250:

| Method | Rule JSR-250 có hiệu lực | Không được suy ra |
| --- | --- | --- |
| `profile` | USER | ADMIN không tự thay USER nếu không có hierarchy/direct role |
| `lockAccount` | ADMIN | Không tự cần cả USER và ADMIN |
| `systemStatus` | PermitAll | Không cần USER ở tầng JSR-250 |
| `legacyDanger` | DenyAll | Không ai qua JSR-250 interceptor |

**Tuy nhiên:** không áp dụng cách “ghi đè class” này như một quy tắc tổng quát cho **mọi annotation method security khác loại**. Ví dụ class có `@PreAuthorize(...)` và method có `@PermitAll` có thể làm cả pre/post advisor và JSR-250 advisor tham gia; khi đó `@PermitAll` không hủy điều kiện của `@PreAuthorize`.

### 8.2. Không đặt annotation JSR-250 mâu thuẫn trên cùng method

Tránh:

```java
// Anti-pattern: hai phát biểu chính sách xung đột.
@PermitAll
@DenyAll
public String ambiguousMethod() {
    return "ambiguous";
}
```

Cách dễ audit là **mỗi method có một JSR-250 access policy rõ ràng**. Nếu muốn kết hợp những điều kiện phức tạp, chuyển sang `@PreAuthorize`/policy bean, thay vì kỳ vọng một precedence không được document/test đủ rõ trong dự án.

Với annotation kế thừa từ nhiều interface, Spring Security có thể từ chối cấu hình xung đột. Đặt rule ở concrete method để loại mơ hồ, và test application startup/invocation.

### 8.3. Một @PermitAll cấp class rất rộng

```java
@PermitAll
public class SharedService {
    public String publicRead() { return "public"; }
    public String privateRead() { return "sensitive"; }
}
```

Nếu không có policy method riêng và JSR-250 bật, cả hai method được xem như public **tại lớp JSR-250**. Đây là một bẫy khi thêm method mới vào một class được đánh dấu public từ trước. Ưu tiên đặt `@PermitAll` tại **method thực sự công khai**, hoặc quản lý class như một public-only service với boundary rõ.

### 8.4. Interface annotations và xung đột inheritance

Có thể đặt annotation ở interface service, nhưng khi một implementation kế thừa **hai interface** có những annotation security khác nhau cho cùng method, Spring Security không có quyết định rõ để ưu tiên. Tài liệu khuyến nghị thêm annotation tường minh vào **concrete method** để giải quyết.

Khi triển khai:

- Tránh lập lại nhiều định nghĩa quyền xung đột tại interface/class/method.
- Kiểm thử public method thông qua interface proxy và class proxy theo setup thực.
- Nếu controller/service phụ thuộc interface, bảo đảm AOP intercept đúng method được gọi.
- Không tưởng rằng annotation trên interface được Java reflection kế thừa y hệt class; Spring có lookup riêng, và test là bằng chứng tốt nhất.

## 9. JSR-250, @Secured và @PreAuthorize: chọn API đúng

| Khả năng | `@RolesAllowed` | `@Secured` | `@PreAuthorize` |
| --- | --- | --- | --- |
| Nguồn annotation | Jakarta Common Annotations/JSR-250 | Spring Security | Spring Security |
| Bật support | `jsr250Enabled = true` | `securedEnabled = true` | Bật mặc định cùng `@EnableMethodSecurity` |
| Mô tả role | Có | Có | Có qua SpEL |
| Danh sách role OR | Có | Có | Có qua `hasAnyRole` |
| Check permission literal | Qua config tên quyền/phần prefix phù hợp, nhưng JSR-250 hướng tới role | Gắn authority strings theo API | `hasAuthority` rõ ràng |
| AND nhiều điều kiện | Không biểu diễn trực tiếp bằng danh sách | Không biểu diễn trực tiếp bằng danh sách | Có, dùng `and`/`&&` trong SpEL |
| Kiểm tra owner/tenant theo tham số | Không trực tiếp | Không trực tiếp | Có thể gọi policy bean theo parameter |
| Kiểm tra giá trị trả về | Không | Không | Thường dùng `@PostAuthorize` |
| Portability annotation | Được chuẩn hóa qua Jakarta | Spring-specific | Spring-specific |
| Mức linh hoạt | Đơn giản | Đơn giản | Cao |

**Gợi ý lựa chọn:**

- Role-only rule ổn định, dùng Jakarta annotations trong module: `@RolesAllowed`.
- Method public/disabled rõ ý nghĩa: `@PermitAll`/`@DenyAll` khi JSR-250 đã bật.
- Rule cần permission cụ thể, nhiều điều kiện, tenant/owner hoặc param: `@PreAuthorize` gọi policy bean thường dễ diễn đạt và kiểm thử hơn.
- `@Secured` thường xuất hiện ở codebase cũ; không cần đổi sang JSR-250 chỉ vì tên annotation tương đồng.

Spring Security docs mô tả `@PreAuthorize` có khả năng diễn đạt mạnh hơn JSR-250 và thường khuyến nghị cho logic phức tạp.

### 9.1. @RolesAllowed không hỗ trợ SpEL

Sai:

```java
@RolesAllowed("hasAuthority('report:approve')")
public String approve() { return "approved"; }
```

Với JSR-250, chuỗi trên được hiểu là **tên role**, không phải SpEL expression. Nếu cần phép kiểm tra dựa trên permission:

```java
@PreAuthorize("hasAuthority('report:approve')")
public String approve() { return "approved"; }
```

Hoặc nếu cần thêm owner:

```java
@PreAuthorize(
        "hasAuthority('report:approve') and " +
        "@reportPolicy.mayApprove(authentication, #reportId)"
)
public void approve(String reportId) {
    reportService.approve(reportId);
}
```

`reportPolicy` là bean **ứng dụng tự viết** và tên tham số `#reportId` cần được Spring Security nhận diện (ví dụ project compile với `-parameters`). Ví dụ là fragment, không phải chương trình runnable độc lập. Các method/domain checks cần làm việc ở boundary có dữ liệu resource đáng tin.

## 10. RoleHierarchy, quyền suy ra và JSR-250

### 10.1. Direct authorities không tự chứa mọi quyền suy ra

Giả sử:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
```

User chỉ có direct `ROLE_ADMIN`. Khi một JSR-250 authorization manager **được cấu hình sử dụng RoleHierarchy**, nó có thể xem ADMIN là có quyền tương ứng USER thông qua graph. Nhưng `Authentication.getAuthorities()` có thể vẫn chỉ chứa `ROLE_ADMIN`.

### 10.2. Cần kiểm tra cấu hình ở đúng authorization consumer

Spring Security hỗ trợ role hierarchy cho method JSR-250 qua `Jsr250AuthorizationManager` và cơ chế cấu hình liên quan, nhưng mức auto-wiring và API theo version cần được kiểm chứng. **Đừng xem việc tạo một bean `RoleHierarchy` là bằng chứng rằng mọi custom manager của project đều dùng graph**.

Một ví dụ hierarchy:

```java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_USER
            """);
}
```

Đây là fragment cấu hình; cần imports `@Bean`, `RoleHierarchy` và `RoleHierarchyImpl`. Kiểm thử:

- `@RolesAllowed("USER")`: direct USER được phép.
- `@RolesAllowed("USER")`: ADMIN **chỉ có direct ROLE_ADMIN** được phép **nếu** JSR-250 manager đã tích hợp hierarchy.
- Không có hierarchy/manager chưa dùng hierarchy: ADMIN có thể bị từ chối ở method đòi USER.
- USER không suy ngược ADMIN.
- Một thay đổi graph phải được test ở **manager thực sự dùng** chứ không chỉ unit test closure.

### 10.3. Không cấp hierarchy để che lỗi naming convention

Nếu role `ROLE_MANAGER` và permission `report:read` là hai loại authority khác nhau, đừng tự cho rằng mọi manager cũng có permission `report:read`. Chỉ suy ra khi graph có quan hệ rõ và điểm authorization thật sự xét graph. Việc tạo cạnh sai có thể mở quyền cho cả role cao qua transitive closure.

### 10.4. RoleHierarchy không thay kiểm tra object scope

`@RolesAllowed("MANAGER")` không tự bảo đảm người quản lý tenant A chỉ sửa user tenant A. Dù có hierarchy, service cần kiểm tra:

```text
role allows entering function
AND target.tenantId == principal.tenantId
AND target.status permits action
AND separation-of-duties policy is satisfied
```

Đó là **pseudo-policy**; triển khai bằng service query/policy bean có nguồn dữ liệu đáng tin, không tin tenant ID do client khai báo nếu chưa xác minh.

## 11. JSR-250 và lớp HTTP: đừng dùng annotation để mở API

### 11.1. Defense in depth

Với endpoint:

```text
GET /api/public/catalog        -> public
GET /api/admin/users           -> ADMIN
POST /api/admin/users          -> ADMIN + nghiệp vụ tạo user
POST /api/accounts/u7/disable  -> ADMIN + policy cùng tenant
```

HTTP `authorizeHttpRequests` và method security có thể cùng tham gia:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public/catalog")
            .permitAll()
        .requestMatchers("/api/admin/**")
            .hasRole("ADMIN")
        .requestMatchers(HttpMethod.POST, "/api/accounts/*/disable")
            .authenticated()
        .anyRequest().denyAll()
);
```

Trong service:

```java
@RolesAllowed("ADMIN")
public void disableAccount(String accountId) {
    accountPolicy.requireCanDisableCurrentUserTarget(accountId);
    repository.disable(accountId);
}
```

Hai đoạn trên là **fragments** trong project. Với method service có rule ADMIN và object policy, user phải qua HTTP matcher (nếu đi qua HTTP), qua JSR-250 role rule, rồi còn phải được phép trên account đích.

### 11.2. @PermitAll có thể public trong Java nhưng không public từ browser

Một message consumer/service bean có thể gọi `@PermitAll` vì không yêu cầu principal; nhưng API gọi tới đó qua HTTP vẫn phụ thuộc filter chain. Tương tự, `@RolesAllowed` có thể chặn service invocation từ scheduler dù scheduler không đi qua HTTP. Tầng method giúp bảo vệ logic ở **nơi dùng**, không thay cho bảo vệ request ingress.

### 11.3. Anonymous, 401, 403 và redirect

- Guest gọi HTTP route cần xác thực thường được chuyển tới authentication entry point (ví dụ 401 JSON hoặc redirect login).
- User đã xác thực thiếu role thường bị từ chối (ví dụ 403).
- Gọi trực tiếp một method bị JSR-250 deny qua Spring proxy thường gây `AccessDeniedException`, không phải tự trả một HTTP status.
- HTTP `ExceptionTranslationFilter` và web exception handling có thể chuyển exception thành response phù hợp.
- `@PermitAll` trong service không tự tạo `200 OK`; method vẫn có thể ném lỗi domain hoặc controller trả status khác.

Đừng viết test chỉ nhìn `403` rồi kết luận JSR-250 chính là lớp chặn: 403 có thể do CSRF, HTTP authorization hoặc domain policy.

## 12. Spring Security Test: kiểm chứng đúng annotations trên proxy

### 12.1. @WithMockUser cung cấp role và authority khác nhau

Ví dụ:

```java
@WithMockUser(roles = "ADMIN")
```

thường tạo một test principal có authority `ROLE_ADMIN`. Nó khác với:

```java
@WithMockUser(authorities = "ADMIN")
```

vì trường hợp thứ hai cấp chính xác chuỗi `ADMIN`, không tự thêm prefix. Với `Jsr250AuthorizationManager` prefix mặc định, `@RolesAllowed("ADMIN")` không được phép chỉ bởi authority `ADMIN` chưa mapping.

Thử cả **đúng prefix** và **sai prefix** để bắt lỗi khác nhau giữa authentication provider và method-security config.

### 12.2. Test service trong application context

Đây là fragment JUnit 5 + AssertJ + Spring Security Test; cần `@SpringBootTest` hoặc `@SpringJUnitConfig` và inject bean `PolicyService` đã qua proxy:

```java
@Autowired
PolicyService service;

@Test
@WithAnonymousUser
void anonymousCanCallPermitAllMethod() {
    assertThat(service.publicNotice()).isEqualTo("public");
}

@Test
@WithMockUser(roles = "USER")
void userCanCallClassLevelMethod() {
    assertThat(service.privateDashboard()).isEqualTo("dashboard");
}

@Test
@WithMockUser(roles = "ADMIN")
void adminCanCallMethodLevelOverride() {
    assertThat(service.editDraft()).isEqualTo("edited");
}

@Test
@WithMockUser(roles = "USER")
void userCannotEditDraft() {
    assertThatThrownBy(() -> service.editDraft())
        .isInstanceOf(AccessDeniedException.class);
}

@Test
@WithMockUser(roles = "ADMIN")
void adminIsDeniedWhenDenyAll() {
    int before = service.disabledBodyCallCount();

    assertThatThrownBy(() -> service.disabledOperation())
        .isInstanceOf(AccessDeniedException.class);

    assertThat(service.disabledBodyCallCount()).isEqualTo(before);
}
```

Mục đích từng test:

1. `@PermitAll` method ghi đè role USER ở class tại tầng JSR-250.
2. Method không annotate riêng kế thừa class-level USER.
3. ADMIN vào được method-level `@RolesAllowed({"EDITOR","ADMIN"})`.
4. USER không được mở quyền EDITOR/ADMIN chỉ vì class mang USER.
5. `@DenyAll` không chạy body, ngay cả với ADMIN.

### 12.3. Test cả lỗi cấu hình JSR-250 bị tắt

Một test chỉ kiểm `publicNotice` chạy thành công **không** chứng minh interceptor hoạt động, vì method public sẽ chạy cả khi JSR-250 tắt. Bài test quan trọng phải assert **negative case**:

```java
@Test
@WithMockUser(roles = "USER")
void denyAllReallyBlocksExecution() {
    assertThatThrownBy(() -> service.disabledOperation())
        .isInstanceOf(AccessDeniedException.class);
}
```

Nếu `jsr250Enabled = false` hoặc lời gọi không qua proxy, body có thể chạy và test sẽ fail. Đây là bài test “canary” hữu ích cho setup method security.

### 12.4. Test role OR

Với:

```java
@RolesAllowed({"EDITOR", "ADMIN"})
public String editDraft() { return "edited"; }
```

ma trận:

| Test direct authorities | Kỳ vọng |
| --- | --- |
| `ROLE_EDITOR` | ALLOW |
| `ROLE_ADMIN` | ALLOW |
| `ROLE_USER` | DENY |
| `ROLE_REVIEWER` | DENY |
| `ROLE_EDITOR` + `ROLE_ADMIN` | ALLOW (nhưng không bắt buộc có cả hai) |
| `EDITOR` không prefix | DENY theo convention mặc định |
| Anonymous | Không được dựa vào role không tồn tại |

### 12.5. @WithAnonymousUser không thay end-to-end HTTP authentication

Một test service gọi qua proxy dưới `@WithAnonymousUser` có thể xác minh JSR-250 `@PermitAll`, nhưng không chứng minh `GET /api/public/catalog` mở từ internet nếu `SecurityFilterChain` đã cấu hình sai. Cần thêm MockMvc hoặc integration HTTP test và kiểm tra chain đúng.

## 13. Java 17 chạy độc lập: mô phỏng đúng ý nghĩa class và method annotations

Để hiểu precedence mà không cần dependency Spring, chương trình dưới đây dùng **các annotation demo tự định nghĩa**. Nó không dùng các class `jakarta.annotation.security` thật; mục đích là mô phỏng ba rule và cách ghi đè class-level tại method-level. Khi triển khai thật, phải dùng `jakarta.annotation.security` và Spring interceptor.

Tạo tệp `Jsr250PolicyConceptDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Set;

public class Jsr250PolicyConceptDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface DemoRolesAllowed {
        String[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface DemoPermitAll {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface DemoDenyAll {}

    @DemoRolesAllowed({"USER"})
    static class ExampleService {

        String dashboard() {
            return "dashboard";
        }

        @DemoPermitAll
        String publicNews() {
            return "news";
        }

        @DemoRolesAllowed({"EDITOR", "ADMIN"})
        String edit() {
            return "edit";
        }

        @DemoDenyAll
        String disabled() {
            return "disabled";
        }
    }

    static boolean allowed(
            Class<?> serviceType,
            String methodName,
            Set<String> granted) throws ReflectiveOperationException {

        Method method = serviceType.getDeclaredMethod(methodName);

        // Dùng annotation METHOD nếu method có rule; nếu không
        // mới tra chính sách CLASS, mô phỏng ghi đè JSR-250.
        if (method.isAnnotationPresent(DemoDenyAll.class)) {
            return false;
        }
        if (method.isAnnotationPresent(DemoPermitAll.class)) {
            return true;
        }
        DemoRolesAllowed roles =
                method.getAnnotation(DemoRolesAllowed.class);

        if (roles == null) {
            if (serviceType.isAnnotationPresent(DemoDenyAll.class)) {
                return false;
            }
            if (serviceType.isAnnotationPresent(DemoPermitAll.class)) {
                return true;
            }
            roles = serviceType.getAnnotation(DemoRolesAllowed.class);
        }

        // Demo dùng deny-by-default nếu hoàn toàn không annotate;
        // Spring thực KHÔNG tự deny mọi method không annotate.
        if (roles == null || granted == null) {
            return false;
        }

        for (String role : roles.value()) {
            if (granted.contains("ROLE_" + role)) {
                return true;  // ANY role là đủ.
            }
        }
        return false;
    }

    static void print(
            String label,
            String method,
            Set<String> granted) throws ReflectiveOperationException {
        System.out.println(label + "="
                + (allowed(ExampleService.class, method, granted)
                    ? "ALLOW" : "DENY"));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Set<String> guest = Set.of();
        Set<String> user = Set.of("ROLE_USER");
        Set<String> editor = Set.of("ROLE_EDITOR");
        Set<String> admin = Set.of("ROLE_ADMIN");
        Set<String> unprefixed = Set.of("ADMIN");

        print("guest-news", "publicNews", guest);
        print("guest-dashboard", "dashboard", guest);
        print("user-dashboard", "dashboard", user);
        print("admin-dashboard", "dashboard", admin);
        print("user-edit", "edit", user);
        print("editor-edit", "edit", editor);
        print("admin-edit", "edit", admin);
        print("unprefixed-edit", "edit", unprefixed);
        print("user-disabled", "disabled", user);
        print("admin-disabled", "disabled", admin);
    }
}
```

Lệnh JDK 17+:

```bash
javac Jsr250PolicyConceptDemo.java
java Jsr250PolicyConceptDemo
```

Stdout theo logic của demo:

```text
guest-news=ALLOW
guest-dashboard=DENY
user-dashboard=ALLOW
admin-dashboard=DENY
user-edit=DENY
editor-edit=ALLOW
admin-edit=ALLOW
unprefixed-edit=DENY
user-disabled=DENY
admin-disabled=DENY
```

**Diễn giải kết quả:**

- Guest vào method `publicNews` vì rule ở method là PermitAll, dù class có USER.
- `dashboard` không có annotation riêng nên lấy rule USER từ class.
- ADMIN **không tự** được coi là USER trong demo: không có role hierarchy, và ADMIN chỉ có `ROLE_ADMIN` trực tiếp.
- `edit` ghi đè class USER và chấp nhận EDITOR **hoặc** ADMIN; user chỉ có USER bị từ chối.
- Authority `ADMIN` không có prefix không đáp ứng quy ước `ROLE_ADMIN` được minh họa.
- `disabled` từ chối ngay cả với admin.

**Giới hạn bắt buộc phải nhớ:** demo không có Spring proxies, HTTP filters, MethodSecurityInterceptor, Jsr250AuthorizationManager, token, CSRF hoặc object policy. Ngoài ra demo tự chọn deny-by-default khi không tìm thấy annotation; Spring method security **không tự khóa mọi method không annotate**. Dùng ví dụ này để hiểu logic JSR-250 rồi xác minh bằng tests trong Spring context ở mục 12.

## 14. MockMvc: kết hợp HTTP và JSR-250 đúng chỗ

Giả sử một controller có:

```java
@RestController
@RequestMapping("/api")
public class NoticeController {

    private final PolicyService policy;

    public NoticeController(PolicyService policy) {
        this.policy = policy;
    }

    @GetMapping("/notices")
    public String publicNotice() {
        return policy.publicNotice();
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return policy.privateDashboard();
    }
}
```

Đây là fragment Spring Web có controller/bean trong context. Đường dẫn `GET /api/notices` phải được HTTP `permitAll`, còn `GET /api/dashboard` phải có HTTP policy thích hợp. Nếu controller thiếu handler, `@PermitAll` không tạo handler thay.

### 14.1. Test public service nhưng HTTP yêu cầu role

Nếu security config vô tình có:

```java
.requestMatchers("/api/notices").hasRole("ADMIN")
```

thì một `GET /api/notices` từ guest vẫn bị chặn ở HTTP. Đây không phải lỗi `@PermitAll`. Để API thật sự công khai, các tầng cần có contract phù hợp.

### 14.2. Test HTTP status đúng nguyên nhân

MockMvc fragment:

```java
@Test
void guestCanGetPublishedNotices() throws Exception {
    mockMvc.perform(get("/api/notices"))
        .andExpect(status().isOk())
        .andExpect(content().string("public"));
}

@Test
@WithMockUser(roles = "USER")
void userCanGetDashboard() throws Exception {
    mockMvc.perform(get("/api/dashboard"))
        .andExpect(status().isOk())
        .andExpect(content().string("dashboard"));
}
```

Hai test chỉ hợp lệ nếu `SecurityFilterChain` đã cho guest qua `/api/notices`, cho USER qua `/api/dashboard`, controller/service return đúng nội dung và không có policy bổ sung. Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc test slice với security config được import đầy đủ.

Không chỉ test 200. Thêm guest bị từ chối dashboard và USER bị từ chối admin. Nếu dùng form login, guest có thể bị redirect thay vì 401; nếu dùng REST entry point, có thể là 401. Test theo **authentication entry point** của project.

### 14.3. Kiểm tra POST và CSRF tách riêng

`@RolesAllowed("ADMIN")` trên service xóa tài khoản không thay CSRF protection cho HTTP POST/DELETE. Với MockMvc:

```java
mockMvc.perform(post("/api/admin/users/u7/disable")
        .with(user("alice").roles("ADMIN"))
        .with(csrf()))
    .andExpect(/* response theo contract controller */);
```

Đây là **pseudocode fragment**, vì response còn phụ thuộc controller, resource, trạng thái, policy tenant. Trong test thật hãy dùng một `ResultMatcher` cụ thể phù hợp (ví dụ `status().isNoContent()` nếu handler trả 204). Đừng để thiếu CSRF gây 403 rồi kết luận `@RolesAllowed` đã ngăn user.

### 14.4. Thử đường ngoài HTTP

Nếu `PolicyService` được gọi từ message consumer hay scheduled task, HTTP filters không chạy. JSR-250 method security sẽ xử lý nếu lời gọi qua proxy và có Authentication phù hợp. Không tự tạo `ROLE_ADMIN` cho job chỉ để mọi method chạy; cần thiết kế service identity, authority và audit.

## 15. Giới hạn bảo mật cần tính trước

### 15.1. Self-invocation bỏ qua proxy

```java
@Service
public class UnsafeExample {

    public void outer() {
        inner();  // this.inner(), có thể bypass AOP proxy.
    }

    @RolesAllowed("ADMIN")
    public void inner() {
        // Side effect nhạy cảm.
    }
}
```

Đây là anti-pattern minh họa. Nếu gọi `outer()` từ bên ngoài, việc tự gọi `inner()` trên cùng object có thể **không đi qua JSR-250 interceptor**, nên rule ở `inner()` không được áp dụng. Tránh coi method annotation như rào chắn tuyệt đối nếu kiến trúc còn cho code gọi trực tiếp nội bộ.

Cách thường dùng: chuyển use case nhạy cảm sang một Spring-managed service khác, inject bean và gọi qua proxy; hoặc tổ chức domain policy được service bắt buộc gọi từ mọi đường.

### 15.2. Private, final và non-Spring objects

Spring AOP có các giới hạn về proxy. Không nên đặt `@RolesAllowed` trên private method rồi kỳ vọng một external caller bị chặn; cũng không nên tự khởi tạo `new PolicyService()` và mong Spring Security advice chạy. Trong Java/Kotlin có final classes/methods cần kiểm tra proxy strategy/AspectJ. Cấu hình class-level chỉ là metadata nếu runtime không intercept.

### 15.3. Async, @Async và scheduler

`SecurityContextHolder` mặc định thường dựa trên ThreadLocal. Task chạy qua raw `Executor` hoặc `CompletableFuture.supplyAsync` không tự có principal request. Với `@Async`, `DeferredResult` hoặc job queue, cần cơ chế context propagation hoặc service identity phù hợp, đồng thời đánh giá quyền lại nếu action nhạy cảm chạy trễ.

`@RolesAllowed` ở service có thể bị từ chối vì worker không có `Authentication`; **không** nên sửa bằng cách bỏ annotation hoặc tạo ADMIN context chung cho mọi task.

### 15.4. Multi-tenant/owner/ACL

Một user được `ROLE_ADMIN` tại tenant A không mặc nhiên được xóa user ở tenant B. `@RolesAllowed("ADMIN")` chỉ là điều kiện role. Với ID được client cung cấp, service phải nạp resource tin cậy, kiểm tenant/owner/membership/status và xác minh các điều kiện separation of duties.

### 15.5. Stale JWT/session/role hierarchy

Khi một user bị thu hồi role trong database, JWT hoặc session đang hoạt động có thể vẫn chứa authorities cũ. Annotation không tự gọi DB để refresh role. Tùy threat model, dùng token TTL, revocation/introspection, session invalidation hoặc kiểm tra quyền hiện tại ở thời điểm hành động.

Nếu RoleHierarchy thay đổi, test manager/handler có dùng graph mới chưa. Đừng suy rằng update text config đồng nghĩa mọi JVM instance lập tức reload policy.

### 15.6. Unannotated methods không tự bị deny

Đây là giới hạn lớn nhất của method security. Nếu một service có 20 method nhưng chỉ 10 method có `@RolesAllowed`, Spring Security không mặc nhiên từ chối 10 method còn lại. Cần **deny-by-default ở HTTP**, code review service boundary, tổ chức lớp với policy mặc định phù hợp và test các đường gọi ngoài HTTP.

Một `@PermitAll` đặt rộng ở class còn nguy hiểm hơn: các method mới có thể được thừa hưởng public policy. Duy trì allowlist rõ ràng và kiểm thử negative cases.

## 16. Ma trận kiểm thử đầy đủ

| Kịch bản | Principal | Method/policy | Kết quả mong đợi |
| --- | --- | --- | --- |
| Public notice | Anonymous | `@PermitAll` | ALLOW tại JSR-250 |
| Public notice | ROLE_USER | `@PermitAll` | ALLOW |
| Dashboard | ROLE_USER | Class `@RolesAllowed("USER")` | ALLOW |
| Dashboard | ROLE_ADMIN đơn lẻ | Class `@RolesAllowed("USER")` | DENY nếu không có hierarchy/direct USER |
| Edit draft | ROLE_EDITOR | Method `@RolesAllowed({"EDITOR","ADMIN"})` | ALLOW |
| Edit draft | ROLE_ADMIN | Method `@RolesAllowed({"EDITOR","ADMIN"})` | ALLOW |
| Edit draft | ROLE_USER | Method `@RolesAllowed({"EDITOR","ADMIN"})` | DENY |
| Edit draft | Authority `EDITOR` không có prefix | Method rolesAllowed | DENY theo default prefix |
| Disabled operation | Anonymous | `@DenyAll` | DENY |
| Disabled operation | ROLE_ADMIN | `@DenyAll` | DENY, body không chạy |
| Method @PermitAll + @PreAuthorize(USER) | Anonymous | Hai advisors cùng hoạt động | DENY do @PreAuthorize |
| HTTP admin route + method PermitAll | Guest | HTTP hasRole ADMIN | DENY ở HTTP |
| HTTP public route + method RolesAllowed ADMIN | Guest | Method requires ADMIN | DENY ở method |
| Method không annotate | Bất kỳ | Không có method-security rule | Không tự bị deny bởi JSR-250 |
| Class USER, method PermitAll | Anonymous | Method-level override | ALLOW ở JSR-250 |
| Class USER, method ADMIN | ROLE_ADMIN | Method-level override | ALLOW ở JSR-250 |
| Class USER, method ADMIN | ROLE_USER | Method-level override | DENY |
| Class USER, method DenyAll | ROLE_ADMIN | Method-level override | DENY |
| Manager có RoleHierarchy ADMIN→USER | ROLE_ADMIN | Method requires USER | Có thể ALLOW nếu JSR-250 manager dùng hierarchy |
| POST qua session, thiếu CSRF | ROLE_ADMIN | Method có rolesAllowed ADMIN | Có thể bị chặn trước method do CSRF |
| Service private resource khác tenant | ROLE_ADMIN | JSR-250 ADMIN + domain policy | DENY theo object scope |
| Gọi nội bộ `this.method()` | ROLE_USER | Method RolesAllowed ADMIN | Có nguy cơ bypass proxy; phải sửa thiết kế |
| JSR-250 tắt | ROLE_USER | Method DenyAll | Không được tin là bị chặn; test config |
| Async worker không có SecurityContext | Caller trước đó là ADMIN | Method RolesAllowed ADMIN | Không tự có role, cần propagation/policy |

**Tư duy kiểm thử:** mỗi security rule phải có ít nhất một ca **được cho phép đúng**, một ca **bị từ chối đúng**, và với chức năng ghi dữ liệu một ca xác minh **side effect không xảy ra** khi deny.

### 16.1. Những test bắt buộc trước deploy

- [ ] `@EnableMethodSecurity(jsr250Enabled=true)` có hiệu lực trên Spring context thật.
- [ ] Import `jakarta.annotation.security.*` tương thích dependency.
- [ ] Role prefix/tên authority từ nguồn xác thực trùng contract.
- [ ] `@RolesAllowed` đa role là OR.
- [ ] Method annotation ghi đè class JSR-250 policy ở những nơi chủ đích.
- [ ] `@PermitAll` chỉ công khai tại lớp JSR-250, HTTP vẫn có rule riêng.
- [ ] `@DenyAll` deny cả ADMIN và body không chạy.
- [ ] Không có policy “bỏ sót” cho service method mới.
- [ ] Test AOP proxy/self-invocation và đường ngoài HTTP.
- [ ] Test RoleHierarchy nếu dùng: direct role và inherited role khác nhau.
- [ ] Test CSRF với POST/PATCH/DELETE khi được áp dụng.
- [ ] Test tenant/owner/state trên resource ID thật.
- [ ] Test bearer/session claims cũ và user role revocation theo threat model.

## 17. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| @RolesAllowed không chặn ai | Chưa bật `jsr250Enabled=true` | Kiểm tra @EnableMethodSecurity và canary @DenyAll test |
| Annotation có nhưng method chạy qua `new` | Không phải Spring-managed bean | Inject bean từ application context |
| Gọi method ADMIN từ method public vẫn chạy | Self-invocation bỏ proxy | Chuyển sang bean khác hoặc boundary có policy |
| ADMIN có ROLE_ADMIN nhưng bị 403 | HTTP rule khác, @PreAuthorize khác, tenant/CSRF hoặc prefix mismatch | Tách từng lớp, kiểm tra authorities |
| @RolesAllowed("ADMIN") không nhận `ADMIN` | Default prefix `ROLE_` | Gán ROLE_ADMIN hoặc cấu hình prefix nhất quán |
| @RolesAllowed({"A","B"}) cho phép role A đơn lẻ | Đây là OR, không phải AND | Dùng @PreAuthorize cho AND |
| @PermitAll nhưng HTTP vẫn trả 401 | HTTP chain yêu cầu authentication | Chỉnh HTTP policy nếu endpoint thật sự public |
| @PermitAll + @PreAuthorize nhưng vẫn 403 | Hai method-security advisors độc lập | Review policy kép, không kỳ vọng PermitAll bypass |
| @DenyAll không cấm bypass proxy | Internal invocation/non-Spring object | Củng cố service boundary |
| @RolesAllowed SpEL không hoạt động | JSR-250 value là role name | Dùng @PreAuthorize |
| @WithMockUser(roles="ADMIN") pass nhưng JWT production fail | Converter không cấp ROLE_ADMIN | Test JwtAuthenticationConverter/IDP mapping |
| Method level ADMIN lại không cần USER | Method policy ghi đè class role | Bổ sung AND rule nếu nghiệp vụ cần cả hai |
| Class @PermitAll mở method mới | Kế thừa policy class public | Đặt PermitAll ở method hoặc phân tách public service |
| 403 ở POST dù role đúng | CSRF token thiếu hoặc filter khác | Kiểm tra CsrfFilter và .with(csrf()) trong test |
| Một interface có hai annotation khác nhau | Spring không rõ annotation kế thừa nào | Đặt annotation trên concrete method |
| Task background thiếu Authentication | ThreadLocal không tự truyền | Context-aware executor/service identity |
| Test chỉ gọi method trực tiếp trong unit test | Không có Spring AOP | Test qua Spring-managed proxy |
| RoleHierarchy bean tồn tại nhưng không có tác dụng | Manager chưa sử dụng graph | Cấu hình/kiểm tra JSR250 manager theo version |

### Quy trình gỡ lỗi nhanh

1. **Kiểm tra method security đã bật:** `@EnableMethodSecurity(jsr250Enabled=true)`.
2. **Kiểm tra proxy:** invocation đi qua Spring bean hay lời gọi `this.method`/`new`?
3. **Kiểm tra annotation thực được resolve:** method/class/interface nào có rule; có xung đột?
4. **Kiểm tra Authentication:** principal và `GrantedAuthority` đúng tên/prefix chưa (không log credentials/token)?
5. **Kiểm tra những lớp khác:** HTTP matcher, CSRF, @PreAuthorize advisor, object policy, transaction và error handler.
6. **Kiểm tra hành vi bằng test cả pass/deny:** phân biệt HTTP status với method exception/side effect.

## 18. Quy trình chọn cách dùng trong dự án

**Bước 1 — Phân loại service use cases.** Mỗi method ghi rõ public, role-only, permission-based, object-level hoặc tạm vô hiệu hóa. Không để method nhạy cảm mặc định unannotated chỉ vì thiếu thời gian.

**Bước 2 — Chốt convention role.** Ví dụ USER/EDITOR/ADMIN trong `@RolesAllowed`, authorities `ROLE_USER`/`ROLE_EDITOR`/`ROLE_ADMIN`; ghi rõ mapper từ JWT/DB và role hierarchy nếu có.

**Bước 3 — Bật JSR-250 đúng config.** Thêm `@EnableMethodSecurity(jsr250Enabled = true)`; xác nhận Jakarta annotations được resolve đúng trong build.

**Bước 4 — Đặt rule tại service boundary.** Dùng `@RolesAllowed` cho role đơn giản, `@PermitAll` chỉ cho method thật công khai, `@DenyAll` cho method đã khóa. Hạn chế class-wide PermitAll.

**Bước 5 — Dùng policy khác cho điều kiện sâu.** Owner/tenant/permission AND, trạng thái resource hay action nhiều bước nên dùng `@PreAuthorize`/domain service, không ép vào chuỗi @RolesAllowed.

**Bước 6 — Phân quyền HTTP riêng.** Public URL và admin URL cần SecurityFilterChain matching rõ; fallback deny. Không dựa vào JSR-250 để thay authentication entry point, CSRF hay CORS.

**Bước 7 — Kiểm thử proxy và negative cases.** Có @DenyAll canary, @RolesAllowed sai role, class/method override, anonymous PermitAll; không chỉ kiểm annotation tồn tại trong source.

**Bước 8 — Kiểm thử object-level và side effects.** Thiếu quyền hoặc khác tenant không được tạo/xóa tài nguyên; nếu deny, transaction/queue không phát sinh side effect.

**Bước 9 — Đánh giá concurrency/version.** Role revoke, JWT/session cũ, hierarchy thay đổi, executor không có context; test với dependency resolved và request thực.

**Bước 10 — Review định kỳ.** Khi thêm method mới hoặc đổi business role, cập nhật access matrix, integration tests và tài liệu policy. Không tự nới quyền chỉ vì một test 403.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@RolesAllowed("ADMIN")` không tự chặn method nếu thiếu `jsr250Enabled=true`?

**Đáp án:** Annotation là metadata Jakarta; Spring Security chỉ thực thi nó khi JSR-250 method interceptor được kích hoạt và invocation đi qua proxy/điểm interception phù hợp.

**Câu 2.** `@RolesAllowed({"ADMIN","EDITOR"})` yêu cầu một hay hai role?

**Đáp án:** **Một trong hai** (OR). Nếu cần cả hai, dùng chính sách AND tường minh như `@PreAuthorize`.

**Câu 3.** `@PermitAll` trên service có làm HTTP endpoint tương ứng tự public không?

**Đáp án:** Không. HTTP `SecurityFilterChain` vẫn có thể yêu cầu authentication/role và có filter CSRF/CORS. PermitAll chỉ bỏ role check tại JSR-250 method advisor.

**Câu 4.** Một class `@RolesAllowed("USER")` có method `@RolesAllowed("ADMIN")`. Method đó phải có USER và ADMIN đồng thời không?

**Đáp án:** Không theo ngữ nghĩa JSR-250 class/method override; method-level ADMIN thay class-level USER cho method đó. Những advisor khác hoặc domain policy vẫn có thể yêu cầu thêm điều kiện.

**Câu 5.** `@DenyAll` có chặn được ADMIN không?

**Đáp án:** Có, nếu JSR-250 interceptor hoạt động và invocation đi qua nó. Test nên xác minh method body không chạy. Không xem nó là rào chắn tuyệt đối trước self-invocation không qua proxy.

**Câu 6.** Dùng `@RolesAllowed("hasAuthority('report:read')")` có đánh giá SpEL không?

**Đáp án:** Không. Đó là string role name. Dùng `@PreAuthorize("hasAuthority('report:read')")` cho biểu thức đó.

**Câu 7.** `@WithMockUser(roles="ADMIN")` và `@WithMockUser(authorities="ADMIN")` khác nhau như thế nào?

**Đáp án:** Dạng `roles` thường cấp `ROLE_ADMIN`; dạng `authorities` cấp chính xác `ADMIN`. Với role prefix mặc định, kết quả JSR-250 có thể khác.

**Câu 8.** Vì sao test một method PermitAll chạy thành công không chứng minh JSR-250 đã bật?

**Đáp án:** Một method công khai vẫn có thể chạy khi method-security JSR-250 bị tắt. Cần negative test với `@DenyAll` hoặc thiếu role để xác minh interceptor thực sự hoạt động.

**Câu 9.** `@RolesAllowed("ADMIN")` có tự đảm bảo ADMIN tenant A chỉ xóa user tenant A không?

**Đáp án:** Không. Đây chỉ là functional role check. Service phải kiểm tra tenant/ownership/ACL/trạng thái account.

**Câu 10.** @PreAuthorize và @PermitAll cùng hiện diện trên một method, annotation nào “thắng”?

**Đáp án:** Không nên nghĩ một annotation luôn thắng và vô hiệu hóa cái còn lại. Khi hai loại method-security advisors đều hoạt động, các checks tương ứng cùng được áp dụng; @PermitAll không biến @PreAuthorize thành allow.

**Câu 11.** Vì sao class-level @PermitAll có thể nguy hiểm?

**Đáp án:** Các method mới trong class có thể kế thừa chính sách public tại JSR-250. Nên giới hạn PermitAll ở các method thực sự công khai hoặc tách service rõ ràng.

**Câu 12.** Khi đổi từ Spring Boot 2 sang Boot 3, lỗi import JSR-250 thường nằm ở đâu?

**Đáp án:** Namespace chuyển từ `javax.annotation.security` cũ sang `jakarta.annotation.security`. Kiểm tra `jakarta.annotation-api` và các thư viện tương thích, không trộn hai hệ annotation một cách vô ý thức.

**Câu 13.** Role ADMIN được @RolesAllowed chấp nhận ở method, nhưng POST trả 403 trước controller. Nguyên nhân?

**Đáp án:** Có thể do CSRF, HTTP rule hoặc filter khác, không nhất thiết do JSR-250. Test POST với CSRF phù hợp, kiểm matcher/filter chain và method policy riêng.

**Câu 14.** Service method có JSR-250 được gọi qua `this.method()` trong cùng bean. Có chắc bảo vệ hoạt động?

**Đáp án:** Không trong mô hình Spring AOP proxy thông thường. Self-invocation có thể bypass interceptor. Thiết kế lời gọi qua bean boundary và test proxy thật.

**Câu 15.** Có nên dùng JSR-250 cho policy “report:approve và cùng tenant và không tự phê duyệt” không?

**Đáp án:** Không đủ biểu đạt trực tiếp. Dùng `@PreAuthorize`/policy bean hoặc kiểm tra tại domain service, với nguồn dữ liệu đáng tin và integration tests.

**Kết luận:** `@RolesAllowed` trả lời “role nào được phép”, `@PermitAll` nói “không cần role ở tầng JSR-250”, và `@DenyAll` nói “không role nào được vào”. Để chúng thực sự bảo vệ ứng dụng, phải bật `jsr250Enabled`, dùng import Jakarta đúng version, bảo đảm Spring AOP intercept lời gọi, giữ HTTP security và quyền theo đối tượng độc lập, kiểm thử **allow, deny, override, role prefix và side effects**. Một annotation ngắn chỉ an toàn khi được triển khai trong một ranh giới thực thi có thể kiểm chứng.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security, JSR-250, multiple advisors và class/method annotations: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 — Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security 6.5 — Jsr250AuthorizationManager API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html
- Spring Security 7.0 — Jsr250AuthorizationManager API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html
- Jakarta Annotations — @RolesAllowed Javadoc: https://jakarta.ee/specifications/webprofile/11/apidocs/jakarta/annotation/security/rolesallowed
- Jakarta Annotations — @PermitAll Javadoc: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/annotation/security/permitall
- Jakarta Annotations — @DenyAll Javadoc: https://jakarta.ee/specifications/annotations/2.1/apidocs/jakarta.annotation/jakarta/annotation/security/denyall
- Spring Security — Authorization Architecture và role naming: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — MockMvc security tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Method security tests và @WithMockUser: https://docs.spring.io/spring-security/reference/servlet/test/method.html
