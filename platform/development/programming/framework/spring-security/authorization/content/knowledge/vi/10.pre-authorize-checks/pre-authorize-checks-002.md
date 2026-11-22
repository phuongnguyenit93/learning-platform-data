# Kiểm tra role, authority và trạng thái xác thực bằng SpEL trong Spring Security

## 1. Mục tiêu và tình huống thực tế

Một service nghiệp vụ có nhiều mức quyền khác nhau: khách chưa đăng nhập được đọc tin công khai; người dùng đăng nhập được xem trang cá nhân; người có role REVIEWER được rà soát tài liệu; người có permission `report:export` mới được xuất báo cáo; và tác vụ chuyển tiền phải đòi xác thực đầy đủ, không chấp nhận chỉ đăng nhập trở lại qua remember-me.

Spring Security cung cấp `@PreAuthorize` để kiểm tra **trước khi method được thực thi** bằng biểu thức **SpEL** (*Spring Expression Language*). Biểu thức có thể tham chiếu role, authority, trạng thái authentication, tham số method, principal hoặc gọi bean chính sách.

Ví dụ:

```java
@PreAuthorize("hasRole('REVIEWER')")
public ReviewResult review(String documentId) { /* ... */ }

@PreAuthorize("isAuthenticated() and hasAuthority('report:read')")
public ReportView read(String reportId) { /* ... */ }

@PreAuthorize("isFullyAuthenticated() and hasAuthority('payment:approve')")
public void approvePayment(String paymentId) { /* ... */ }
```

Đây là **fragment Spring service**: các class `ReviewResult`, `ReportView` và implementation là tùy ứng dụng. Giá trị `@PreAuthorize` là **một SpEL expression**, không phải Java boolean expression thuần; Spring Security đánh giá nó bằng context của method invocation.

Bài này giúp bạn:

1. Phân biệt `hasRole` với `hasAuthority`, quy tắc prefix `ROLE_` và các biến thể “any”.
2. Hiểu rõ `isAuthenticated()`, `isFullyAuthenticated()`, `isRememberMe()`, `isAnonymous()`, `permitAll` và `denyAll`.
3. Biết cách viết biểu thức `and`, `or`, `!`, dấu ngoặc và điều kiện theo tham số.
4. Dùng `authentication`, `principal`, `#parameter` và bean policy với ngữ nghĩa tin cậy.
5. Bật `@EnableMethodSecurity`, quản lý AOP proxy và tránh self-invocation.
6. Tránh nhầm method authorization với HTTP authorization, CSRF, MFA hoặc quyền trên từng tài nguyên.
7. Kiểm thử cả tài khoản có role, có permission, thiếu quyền, anonymous và remember-me.
8. Thiết kế quy tắc rõ ràng, dễ kiểm toán, tránh cấp thừa quyền trong Java/Spring Boot hiện đại.

**Phạm vi:** Spring Security Servlet/Spring MVC, Java 17+, các API Spring Security 6.x/7.x phổ biến. `@PreAuthorize` cũng dùng trong một số môi trường khác nhưng ví dụ filter/HTTP ở đây thuộc Servlet. Khi áp dụng, đối chiếu API và version thực được Maven/Gradle giải quyết bằng BOM.

## 2. @PreAuthorize hoạt động ở đâu và lúc nào?

### 2.1. Chu trình method invocation

```text
HTTP request hoặc lời gọi từ bean khác
           │
           ▼
Spring-managed service proxy
           │
           ▼
AuthorizationManagerBeforeMethodInterceptor
           │
           ▼
PreAuthorizeAuthorizationManager
           │
           ▼
MethodSecurityExpressionHandler
    ├─ SecurityContext / Authentication
    ├─ GrantedAuthorities / RoleHierarchy (nếu cấu hình)
    ├─ tham số method (#id, #request, ...)
    ├─ principal, authentication, expression root
    └─ bean chính sách (@policyBean)
           │
           ▼
SpEL trả kết quả authorization
    ├─ GRANT ──> gọi method body
    └─ DENY  ──> ngăn method body / access denied
```

Ở đây “trước method” thực sự là **trước thân method được advice**. Method security được thực thi bởi Spring AOP interceptor khi invocation đi qua proxy hoặc phương thức weaving phù hợp. Một method có annotation nhưng được gọi trực tiếp trên đối tượng tạo bằng `new` hoặc qua `this.method()` có thể **không** được intercept.

Thông thường, `@PreAuthorize` được đánh giá ở service boundary và có thể bảo vệ cả use case được gọi từ HTTP controller, scheduled task hoặc message consumer — nếu mọi đường gọi đều đi qua cơ chế method-security và có identity phù hợp.

### 2.2. Bật method security

Trong Spring Security hiện đại:

```java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` bật hỗ trợ pre/post method annotations như `@PreAuthorize` theo mặc định. Chỉ thêm `spring-boot-starter-security` **không tự bật** method-level authorization. Với code Spring Security cũ dùng `@EnableGlobalMethodSecurity(prePostEnabled = true)`, hãy xem đây là đường cấu hình legacy cần migration theo phiên bản, không đưa hai cách vào một project mà thiếu review.

### 2.3. Không có annotation không tự đồng nghĩa DENY

Nếu bean có một số method `@PreAuthorize` và một số method không annotate, method-security framework **không mặc nhiên từ chối mọi method không annotate**. Hãy tổ chức service boundary rõ, dùng HTTP fallback `denyAll()` cho URL chưa khai báo và kiểm thử đường gọi nghiệp vụ khác nhau. Không lấy việc một method đã được bảo vệ làm bằng chứng cả class đều được bảo vệ.

## 3. Authority: chuỗi quyền mà AuthorizationManager có thể kiểm tra

### 3.1. GrantedAuthority là gì?

`Authentication` đại diện cho principal được xác thực và chứa tập `GrantedAuthority`. Một user có thể có:

```text
Authentication:
  principal: linh
  authenticated: true
  authorities:
    - ROLE_USER
    - ROLE_REVIEWER
    - report:read
    - report:export
```

Mỗi authority thông dụng có thể biểu diễn bằng `SimpleGrantedAuthority` chứa một chuỗi. `hasAuthority('report:read')` so với authority có tên đó, có phân biệt chính xác chuỗi. Spring Security **không tự coi** `report:read` và `REPORT:READ` hay `SCOPE_report.read` là một.

Ví dụ SpEL:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView view(String reportId) {
    return reportService.loadVisibleReport(reportId);
}
```

Đây là fragment, không tự tồn tại `reportService` hay `ReportView`. Trong project thật, đọc report còn cần policy về tenant/owner, không chỉ permission chức năng `report:read`.

### 3.2. hasAuthority là phép so khớp quyền cụ thể

| Authority thực tế | `hasAuthority('report:read')` | Vì sao |
| --- | --- | --- |
| `report:read` | True | Trùng chuỗi |
| `report:write` | False | Khác thao tác |
| `ROLE_ADMIN` | False nếu không có mapping/hierarchy liên quan | Role không tự là permission |
| `SCOPE_reports.read` | False | Tên scope khác permission |
| `REPORT:READ` | False | Khác chữ hoa |
| `report:read` + `ROLE_USER` | True | Một authority đúng là đủ |

Khi cấu hình `RoleHierarchy` trong expression handler, `hasAuthority` có thể đánh giá reachable authorities thay cho tập direct thuần; vì vậy trường hợp chỉ có `ROLE_ADMIN` có thể thỏa permission do **cạnh hierarchy được cấu hình**. Không mặc nhiên có cơ chế suy quyền nếu chưa tạo graph và kiểm tra handler thật.

### 3.3. hasAnyAuthority là OR

```java
@PreAuthorize("hasAnyAuthority('report:read', 'report:manage')")
public ReportView preview(String reportId) { /* ... */ }
```

Ý nghĩa: chỉ cần **một trong hai** authority tương ứng. Đây không phải AND.

Nếu nghiệp vụ cần cả hai:

```java
@PreAuthorize(
    "hasAuthority('report:read') and hasAuthority('report:export')"
)
public byte[] export(String reportId) { /* ... */ }
```

Chính sách AND kiểm tra đồng thời hai quyền. Với biểu thức dài, hãy gom vào tên permission/policy bean rõ ý nghĩa thay vì nhân đôi quyền trong nhiều nơi.

## 4. Role: hasRole khác hasAuthority ở quy ước prefix

### 4.1. hasRole('ADMIN') theo mặc định là ROLE_ADMIN

Theo convention mặc định của Spring Security, các rule role dùng prefix `ROLE_`. Vì vậy:

```java
@PreAuthorize("hasRole('ADMIN')")
public void approveConfiguration() { /* ... */ }
```

thường kiểm tra `GrantedAuthority` là `ROLE_ADMIN`, tương tự ý nghĩa:

```java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
public void approveConfiguration() { /* ... */ }
```

**Không** mặc định kiểm tra authority trần `ADMIN`. Khi gặp “user đã có ADMIN mà vẫn bị từ chối”, hãy in/log danh sách authority **đã được làm sạch thông tin nhạy cảm** trong môi trường test, đối chiếu `ROLE_ADMIN` với `ADMIN` và mapper của authentication provider.

Nên viết `hasRole('ADMIN')` thay vì `hasRole('ROLE_ADMIN')` để nhất quán contract role-prefix; một số manager/API có cơ chế xử lý hoặc ràng buộc khác nhau khi được truyền role name đã chứa prefix.

### 4.2. hasAnyRole là OR

```java
@PreAuthorize("hasAnyRole('EDITOR', 'ADMIN')")
public void publishDraft(String id) { /* ... */ }
```

Nó chấp nhận người có `ROLE_EDITOR` **hoặc** `ROLE_ADMIN`, không cần hai role cùng lúc. Nếu cần cả hai, viết:

```java
@PreAuthorize("hasRole('EDITOR') and hasRole('ADMIN')")
public void highlyRestrictedAction() { /* ... */ }
```

Nhưng hãy tự hỏi business policy có thật sự đòi hai chức danh cùng lúc hay nên dùng một **permission nghiệp vụ** như `document:publish:restricted`? Đòi đồng thời hai role thường ít linh hoạt hơn RBAC/permission modeling.

### 4.3. Tên role và tên permission

| Biểu thức | Ý nghĩa thông thường |
| --- | --- |
| `hasRole('ADMIN')` | Có `ROLE_ADMIN` theo prefix mặc định |
| `hasAuthority('ROLE_ADMIN')` | Chính xác authority `ROLE_ADMIN` |
| `hasAuthority('admin:manage')` | Chính xác permission `admin:manage` |
| `hasAnyRole('USER','ADMIN')` | Có một trong `ROLE_USER`, `ROLE_ADMIN` |
| `hasAnyAuthority('invoice:read','invoice:manage')` | Có một trong hai permissions |
| `hasRole('read')` | Đòi role `ROLE_read` theo default; **không** phải `read` |

Đừng chuyển toàn bộ permission thành role chỉ vì project đang dùng `hasRole`. Role là cách nhóm users theo chức trách; permission thường mô tả hành động trên tài nguyên. Một user có `ROLE_ADMIN` không tự có permission `report:export` nếu không có ánh xạ cụ thể (lúc xác thực hoặc qua `RoleHierarchy`).

### 4.4. Prefix có thể tùy chỉnh

Một project có thể thay role prefix bằng `GrantedAuthorityDefaults`/cấu hình expression handler hoặc factory phù hợp với version. Khi đó câu “`hasRole('ADMIN')` đòi `ROLE_ADMIN`” chỉ đúng theo **default**.

Nếu đang dùng Spring Security 7, các authorization-manager factories giúp tùy chỉnh role prefix/hierarchy tập trung; ở cấu hình cũ hơn, expression handler có các setter khác. **Luôn test bằng principal có authority thật**, không dựa vào tên biến “role” trong code.

## 5. Trạng thái xác thực: bốn biểu thức quan trọng

### 5.1. Không đủ chỉ kiểm Authentication.isAuthenticated()

Một `AnonymousAuthenticationToken` trong Spring Security thường có `isAuthenticated() == true` về mặt thuộc tính token, nhưng vẫn được phân loại là anonymous bởi `AuthenticationTrustResolver`. Vì thế, trong SpEL hãy dùng các biểu thức chuyên biệt:

```java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("isFullyAuthenticated()")
@PreAuthorize("isRememberMe()")
@PreAuthorize("isAnonymous()")
```

Chúng được Spring Security cung cấp qua `SecurityExpressionRoot`/`SecurityExpressionOperations` dựa trên authentication trust resolution, không nên tự thay toàn bộ bằng kiểm tra property `authentication.authenticated`.

### 5.2. Ma trận ngữ nghĩa

| Trạng thái user | `isAnonymous()` | `isAuthenticated()` | `isRememberMe()` | `isFullyAuthenticated()` |
| --- | --- | --- | --- | --- |
| Anonymous do Spring Security tạo | True | False | False | False |
| User đăng nhập bằng remember-me token | False | True | True | False |
| User đăng nhập đầy đủ (form/session, Basic, Bearer…) | False | True | False | True |
| Không có Authentication hợp lệ | Không nên mặc định coi là anonymous | Không được cấp quyền | Không | Không |

**Hàng cuối** là phân loại an toàn khái niệm: request không có Authentication được cung cấp cho interceptor có thể bị từ chối/được xử lý bởi framework trước khi biểu thức chạy; không được coi null context giống hệt một `AnonymousAuthenticationToken` hợp lệ. Mục tiêu là **không cấp quyền nhờ context vắng**.

#### isAuthenticated()

`isAuthenticated()` cho phép một user đã xác thực (bao gồm cơ chế remember-me khi được bật), loại trừ anonymous. Dùng cho hành động không đòi xác thực mới:

```java
@PreAuthorize("isAuthenticated()")
public UserView currentProfile() { /* ... */ }
```

**Lưu ý:** việc “đã xác thực” không nói user có permission trên tất cả tài nguyên. Nếu method nhận `userId` bất kỳ, vẫn cần owner/tenant check.

#### isFullyAuthenticated()

`isFullyAuthenticated()` yêu cầu user không phải anonymous **và không chỉ được xác thực qua remember-me**. Hữu ích cho nghiệp vụ đòi user đã đăng nhập đầy đủ thay vì được khôi phục tự động:

```java
@PreAuthorize("isFullyAuthenticated() and hasAuthority('payment:approve')")
public void approvePayment(String id) { /* ... */ }
```

**Không đồng nghĩa MFA hoặc re-authentication gần đây.** Một Bearer token hoặc session có thể được xem là fully authenticated nhưng không chứng minh user đã hoàn thành MFA/step-up theo chính sách của sản phẩm. Những yêu cầu đó cần cơ chế yếu tố bổ sung/session freshness và test riêng theo version.

#### isRememberMe()

`isRememberMe()` chỉ True với authentication được `AuthenticationTrustResolver` nhận diện là **remember-me**; không phải “trong trình duyệt có cookie”. Cần phân biệt:

- Cookie session thông thường có thể đại diện cho một login đầy đủ.
- Một `RememberMeAuthenticationToken` được tạo từ cơ chế remember-me có mức tin cậy riêng.
- JWT không tự được xếp remember-me chỉ vì token có hạn dài.

Ví dụ fragment chỉ cho remember-me xem trang nhắc đăng nhập lại:

```java
@PreAuthorize("isRememberMe()")
public ReauthenticationPrompt promptForFullLogin() { /* ... */ }
```

Đây là chính sách chuyên biệt; thông thường một trang thông báo có thể nên mở cho nhiều loại user hơn. Không dùng `isRememberMe()` như alias của `isAuthenticated()`.

#### isAnonymous()

`isAnonymous()` chỉ người dùng được Spring Security coi là anonymous:

```java
@PreAuthorize("isAnonymous()")
public String anonymousLanding() {
    return "Welcome, guest";
}
```

**Không đồng nghĩa public cho tất cả:** người đã đăng nhập đầy đủ/remember-me có thể bị từ chối tại method này. Nếu mọi user đều được vào, xem `permitAll` dưới đây.

### 5.3. permitAll và denyAll trong SpEL

```java
@PreAuthorize("permitAll")
public String publicAnnouncement() { return "public"; }

@PreAuthorize("denyAll")
public String removedOperation() { return "disabled"; }
```

`permitAll` và `denyAll` là expressions có nghĩa allow luôn/deny luôn **ở tầng @PreAuthorize** (với method-security interceptor đang hoạt động). Trong API mới cũng có thao tác tương ứng dạng `permitAll()`/`denyAll()`; ngữ nghĩa cơ bản không thay đổi.

`permitAll` **không**:
- Bỏ security filters của HTTP endpoint.
- Bỏ CSRF cho POST/PUT/PATCH/DELETE.
- Bỏ `@PostAuthorize`, `@Secured`, JSR-250 hoặc custom advisors khác nếu đang hoạt động.
- Bảo đảm controller tồn tại hoặc service không ném lỗi domain.

`denyAll` ở method **không** đồng nghĩa xóa đường code; self-invocation có thể bỏ proxy. Khi một tác vụ phải ngừng hoàn toàn, cần chặn mọi entrypoint và test không phát sinh side effect.

## 6. Cách kết hợp SpEL: AND, OR, NOT và dấu ngoặc

SpEL hỗ trợ các toán tử logic bằng chữ `and`, `or`, `not` hoặc ký hiệu tương đương `&&`, `||`, `!`. Trong annotation Java string, dạng chữ thường dễ đọc hơn và tránh nhầm với cú pháp hệ thống khác.

### 6.1. Một quyền là điều kiện đơn

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView view(String reportId) { /* ... */ }
```

Ý nghĩa: phải có `report:read` trong effective authorities.

### 6.2. Hai quyền cùng lúc

```java
@PreAuthorize(
    "hasAuthority('report:read') and hasAuthority('report:export')"
)
public byte[] export(String reportId) { /* ... */ }
```

Chỉ có `report:export` mà không có `report:read` là không đủ. Với business thật, có thể cấp một permission riêng `report:export` vốn đã bao hàm đọc báo cáo, nhưng đó là quyết định mô hình quyền, không phải sự thật framework tự suy ra.

### 6.3. Role hoặc permission

```java
@PreAuthorize(
    "hasRole('ADMIN') or hasAuthority('report:read')"
)
public ReportView inspect(String reportId) { /* ... */ }
```

Chỉ cần **một** điều kiện đúng. Nếu ADMIN cần bắt buộc có tenant scope hoặc audit riêng, đừng cho phép OR quá rộng tạo “superuser bypass” không được nghiệp vụ phê duyệt.

### 6.4. Thứ tự biểu thức và dấu ngoặc

Giả sử policy: **đã xác thực**, đồng thời **có ROLE_REVIEWER hoặc ROLE_ADMIN**.

Đúng:

```java
@PreAuthorize(
    "isAuthenticated() and (hasRole('REVIEWER') or hasRole('ADMIN'))"
)
public void review(String id) { /* ... */ }
```

Biểu thức sau:

```java
@PreAuthorize(
    "isAuthenticated() and hasRole('REVIEWER') or hasRole('ADMIN')"
)
```

có thể làm `hasRole('ADMIN')` trở thành nhánh OR riêng theo độ ưu tiên toán tử. Nếu mọi principal có ROLE_ADMIN đều được xác thực đầy đủ trong model, khác biệt đôi khi không lộ trong test; về logic policy vẫn không giống lời yêu cầu “mọi đường đều phải authenticated”. **Dùng dấu ngoặc diễn đạt ý định**, đặc biệt khi có AND/OR nhiều điều kiện.

### 6.5. NOT và ngoại lệ

```java
@PreAuthorize(
    "isAuthenticated() and !hasAuthority('account:suspended')"
)
public void uploadDocument(String id) { /* ... */ }
```

Ví dụ minh họa chặn user có authority `account:suspended`. Nhưng nếu hệ thống không gán authority đó đúng hoặc session/JWT cũ, biểu thức sẽ cho phép người đang bị khóa. Trạng thái tài khoản/khóa trong database thường nên được xác thực/kiểm tra bằng nguồn tin cậy, không chỉ “không thấy cờ trong token”.

### 6.6. Đừng nhét policy quá dài vào một annotation

Khi biểu thức trở thành:

```java
@PreAuthorize(
    "isFullyAuthenticated() and " +
    "(hasRole('REVIEWER') or hasRole('ADMIN')) and " +
    "hasAuthority('document:approve') and " +
    "@approvalPolicy.canApprove(authentication, #documentId)"
)
```

thì hãy cân nhắc tách business logic sang một bean có tên rõ, còn annotation chỉ giữ điều kiện chức năng cốt lõi. Một bean policy có thể được unit-test đầy đủ theo dữ liệu/tình trạng resource, thay vì một biểu thức dài khó audit.

## 7. authentication và principal: hai đối tượng khác nhau trong SpEL

### 7.1. authentication tham chiếu Authentication hiện hành

```java
@PreAuthorize("authentication.name == #username")
public String getOwnProfile(String username) { /* ... */ }
```

`authentication` là `Authentication`, thuộc tính `name` thường tương ứng `getName()`. Biểu thức chỉ cho phép user gọi với `username` trùng tên trong authentication. Đây là ví dụ owner-check đơn giản **nếu username là định danh tin cậy/duy nhất**; với dữ liệu nhạy cảm, nên kiểm tra owner ID/tenant theo nguồn đáng tin thay vì trông vào tên có thể đổi.

### 7.2. principal là Authentication.getPrincipal()

```java
@PreAuthorize("principal.username == #username")
public String getProfile(String username) { /* ... */ }
```

Biểu thức này chỉ phù hợp khi principal thực sự có thuộc tính `username` (ví dụ một số `UserDetails`). Với JWT, principal có thể là `Jwt` hoặc một kiểu khác, không có `username`; còn anonymous principal thường là một chuỗi như `anonymousUser`. **Không mặc định principal luôn là một UserDetails**.

Cách ít phụ thuộc kiểu principal hơn là:

```java
@PreAuthorize("authentication.name == #username")
```

Nhưng vẫn phải xác minh authentication name là khóa đối tượng mà hệ thống dùng để kiểm quyền.

### 7.3. Tránh in principal, credentials hoặc raw token

Không viết log:

```java
logger.info("Auth object: {}", authentication);
```

một cách vô điều kiện trong production; Authentication/details có thể chứa dữ liệu nội bộ, claims hoặc thông tin không dành cho log. Khi cần chẩn đoán authorization, chỉ log ID người dùng đã được phép, permission name và correlation ID ở mức an toàn, không xuất access token hay mật khẩu.

### 7.4. Principal từ JWT và OAuth2

Khi Spring Resource Server xác thực JWT, converter thường gán scopes thành authorities dạng `SCOPE_xxx`. Ví dụ:

```text
scope claim: reports.read
authority:   SCOPE_reports.read
```

Khi đó:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportView getReport(String id) { /* ... */ }
```

mới khớp authority mặc định tương ứng, **không phải** `hasRole('reports.read')` hoặc `hasAuthority('report:read')` trừ khi converter đã đổi tên. Đừng đoán: hãy test `JwtAuthenticationConverter` và actual authorities của application version.

## 8. Dùng tham số method trong biểu thức SpEL

### 8.1. Ký hiệu #parameterName

`@PreAuthorize` nhận được method invocation và có thể truy cập method arguments:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public InvoiceView readInvoice(String invoiceId) {
    return invoiceService.read(invoiceId);
}
```

`#invoiceId` là giá trị argument. `@invoicePolicy` tham chiếu bean trong Spring context; `canRead` là method **ứng dụng tự triển khai**, không phải API có sẵn của Spring Security. Tên type `InvoiceView` và service cũng là code nghiệp vụ.

### 8.2. Phát hiện tên tham số

Spring Security dùng cơ chế khám phá tên tham số; tùy project/compiler, tên thật có thể được giữ bằng cờ Java `-parameters`, hoặc qua annotation `@P`:

```java
import org.springframework.security.access.method.P;

@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #targetId)"
)
public InvoiceView readInvoice(@P("targetId") String invoiceId) {
    return invoiceService.read(invoiceId);
}
```

Dạng này cho phép SpEL dùng `#targetId` dù tên tham số Java là `invoiceId`. Trong một số ngữ cảnh cũng có thể truy cập tham số theo vị trí (`#p0` hoặc `#a0`), nhưng đặt tên rõ sẽ dễ đọc/test hơn. Với interface method, kiểm tra annotation nằm đúng vị trí và được proxy nhìn thấy.

### 8.3. Tham số không đáng tin chỉ vì xuất hiện trong SpEL

Client có thể gửi `invoiceId` hay `tenantId` tùy ý. Nếu policy dùng:

```java
@PreAuthorize("#requestedTenantId == authentication.name")
```

nó không kiểm tra được liệu invoice thật có thuộc tenant ấy không. Một người tấn công có thể tự điền cả ID lẫn tenant ID để thỏa điều kiện.

Trong bean policy, cần nạp resource từ nguồn tin cậy, kiểm tenant/owner/membership/state rồi mới quyết định:

```text
ALLOW =
  hasAuthority("invoice:read")
  AND invoice.tenantId == user.tenantId
  AND invoice is visible under business policy
```

Đây là pseudo-policy; tùy use case nên thực hiện dưới transaction phù hợp để tránh dữ liệu thay đổi giữa check và action (*TOCTOU*). Nếu không có object-level checks, user có role phù hợp vẫn có thể đọc dữ liệu tenant khác.

### 8.4. Null safety và expression errors

Một SpEL truy cập `#request.ownerId` trong khi `request == null` có thể ném lỗi evaluation. Không dựa vào exception ấy như một chính sách deny được thiết kế rõ.

Với input có thể null:

```java
@PreAuthorize(
    "#request != null and " +
    "hasAuthority('document:create') and " +
    "@documentPolicy.canCreate(authentication, #request)"
)
```

Đây là fragment với bean `documentPolicy` do ứng dụng cung cấp. Service vẫn cần Bean Validation, data validation và tránh lộ chi tiết exception trong HTTP response. Sử dụng operator null-safe của SpEL khi appropriate và version hỗ trợ, nhưng **không** lấy null-safe navigation thay cho policy kiểm tra dữ liệu.

## 9. Gọi bean chính sách thay vì nhúng toàn bộ logic nghiệp vụ vào SpEL

### 9.1. Bean policy có một nhiệm vụ rõ ràng

Ví dụ:

```java
package com.example.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentAccessRepository accessRepository;

    public DocumentPolicy(DocumentAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(Authentication actor, String documentId) {
        if (actor == null || documentId == null || documentId.isBlank()) {
            return false;
        }
        if (!actor.isAuthenticated()) {
            return false;
        }
        // Repository phải lấy membership/owner/tenant đã xác minh từ DB.
        return accessRepository.userCanRead(actor.getName(), documentId);
    }
}
```

Đây là **fragment kiến trúc**, cần `DocumentAccessRepository` do dự án định nghĩa; `actor.isAuthenticated()` **không đủ** để phân biệt anonymous theo Spring Security trust resolver. Trong production hãy bảo đảm request/method invocation đã qua `isAuthenticated()` ở expression hoặc dùng `AuthenticationTrustResolver` trong policy bean nếu nó có thể được gọi từ đường khác. Policy vẫn cần exception handling, caching và transactional consistency khi thích hợp.

Cách đặt annotation:

```java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(String documentId) {
    return documentService.read(documentId);
}
```

`DocumentView` và `documentService` là domain code chưa khai báo ở fragment. Spring Security sẽ gọi bean `documentPolicy` trong expression context. Khi policy trở nên phức tạp, không nên đặt logic SQL/HTTP call trực tiếp bên trong chuỗi SpEL.

### 9.2. Dùng @PreAuthorize như cổng trước hành động ghi

```java
@PreAuthorize(
    "isFullyAuthenticated() and " +
    "hasAuthority('document:approve') and " +
    "@documentPolicy.canApprove(authentication, #documentId)"
)
public void approve(String documentId) {
    documentService.approve(documentId);
}
```

Đảm bảo `canApprove` kiểm tra **đúng đối tượng**: report/document thuộc tenant, đang ở trạng thái chờ duyệt, người phê duyệt không phải người tạo nếu business cấm, và các quy tắc ủy quyền cần thiết. Với dữ liệu thay đổi đồng thời, cần transaction/optimistic locking hoặc kiểm tra lúc cập nhật để tránh trạng thái policy khác lúc check.

### 9.3. Khi nào không nên dùng SpEL cho mọi thứ?

- Quy tắc cần truy cập nhiều bảng, transaction hoặc locks.
- Policy phải được tái sử dụng qua HTTP, queue và batch jobs.
- Quy tắc thay đổi theo thời gian, version, tenant policy.
- Có nhiều nhánh exception/approval workflow.
- Việc gọi bean từ expression tạo n+1 queries hoặc hiệu năng không ổn định.

Khi đó có thể dùng permission-oriented service/domain policy và method annotation làm lớp entry gate. Không đòi mọi policy phải là một chuỗi SpEL dài.

## 10. Role hierarchy và SpEL

### 10.1. Role cao không tự chứa role thấp

Giả sử một user chỉ có:

```text
ROLE_ADMIN
```

và method yêu cầu:

```java
@PreAuthorize("hasRole('USER')")
public String readDashboard() { return "dashboard"; }
```

Mặc định, **chỉ có ROLE_ADMIN không làm user tự có ROLE_USER**. Nếu muốn ADMIN bao hàm USER, hoặc gán thêm direct `ROLE_USER` ở nguồn xác thực, hoặc cấu hình `RoleHierarchy`:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
```

Dấu `>` biểu diễn inclusion một chiều và có tính bắc cầu.

### 10.2. Cấu hình method-security expression handler có hierarchy

Theo hướng dẫn Spring Security, dùng bean `RoleHierarchy` và `MethodSecurityExpressionHandler` phù hợp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
public class RoleHierarchyConfig {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_MANAGER
                ROLE_MANAGER > ROLE_USER
                ROLE_MANAGER > report:read
                """);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
```

Đây là class Spring configuration, yêu cầu method security đã bật ở mục 2; cách dùng expression handler như ví dụ được tài liệu 6.x mô tả. Đối với Spring Security 7.x, API factory có thể được ưu tiên/tùy chỉnh khác; đối chiếu Javadoc version thực. `static @Bean` giúp hạ tầng method security nhìn thấy handler trước khi được khởi tạo.

### 10.3. Test direct và inferred authorities riêng

Với graph trên:

- Direct `ROLE_ADMIN` có thể đạt tới `ROLE_MANAGER`, `ROLE_USER` và `report:read`.
- Direct `ROLE_USER` **không** suy ngược `ROLE_MANAGER`.
- Direct `ROLE_MANAGER` đạt `report:read` nếu handler dùng hierarchy.
- Direct permission `report:read` không tự khiến user có role MANAGER.

`Authentication.getAuthorities()` có thể vẫn chỉ có direct authorities. Test `getReachableGrantedAuthorities` kiểm tra graph; test `@PreAuthorize("hasRole('USER')")` trên Spring bean kiểm tra manager **đã thực sự dùng** graph. Hai loại test không thay thế nhau.

### 10.4. Cẩn thận khi cấp quyền quản trị theo OR

```java
@PreAuthorize(
    "hasRole('ADMIN') or hasAuthority('document:delete')"
)
```

cho phép hai con đường độc lập. Khi dùng hierarchy, một role có thể suy ra permission `document:delete` theo graph. Nếu một cạnh bị thêm nhầm, cả role thấp có thể được xóa tài liệu. Hãy test không chỉ role cao được phép, mà cả **role thấp chắc chắn bị từ chối**.

## 11. So sánh SpEL với HTTP authorization

### 11.1. Hai ranh giới bảo vệ

Ví dụ Servlet SecurityFilterChain:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/news").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/**").authenticated()
    .anyRequest().denyAll()
);
```

Ở service:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView loadVisibleReport(String id) { /* ... */ }

@PreAuthorize("isFullyAuthenticated() and hasRole('ADMIN')")
public void disableAccount(String accountId) { /* ... */ }
```

Cả hai loại rule có vai trò riêng:

1. HTTP route filter quyết định request được vào endpoint theo method/path.
2. Service method security kiểm tra ngay trước invocation.
3. Domain policy còn kiểm tra tenant/owner/record state.
4. Các filter CSRF/CORS/authentication cũng có thể chặn trước khi method chạy.

Vì vậy `@PreAuthorize("permitAll")` không làm `GET /api/admin/...` mở cho guest nếu HTTP rule còn `hasRole("ADMIN")`. Ngược lại, HTTP `permitAll()` không bỏ `@PreAuthorize` yêu cầu permission trong service.

### 11.2. Không ép mọi method vào một controller

Nếu policy ở controller duy nhất, cùng use case có thể được gọi từ queue, scheduler hoặc GraphQL/gRPC endpoint mới mà quên rule. Đặt policy ở service boundary có giá trị phòng thủ sâu hơn, nhưng phải chắc chắn mọi đường gọi đi qua Spring proxy và actor identity chính xác.

### 11.3. Không thể dùng SpEL bù cho authentication provider yếu

Một biểu thức `isAuthenticated()` chỉ biết context đã được authentication mechanism thiết lập. Nếu identity provider, JWT converter hoặc session handling sai, SpEL không tự sửa được. Cần test với token/cookie thật ở integration level, không chỉ principal giả lập bằng `@WithMockUser`.

## 12. Những hạn chế của @PreAuthorize và Spring AOP

### 12.1. Self-invocation bỏ qua method-security proxy

```java
@Service
public class UnsafeService {

    public void outer(String id) {
        deleteSensitive(id); // this.deleteSensitive(id)
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void deleteSensitive(String id) {
        // Hành động nhạy cảm
    }
}
```

Đây là **anti-pattern**. `outer` gọi nội bộ `deleteSensitive` trên cùng instance, thường bỏ qua Spring AOP proxy, khiến `@PreAuthorize` không được thực thi ở ranh giới đó.

Cách khắc phục thường là tách method nhạy cảm sang Spring-managed bean khác, gọi qua injected bean proxy và để domain policy bắt buộc chạy ở service. Không dùng `self-injection` như một mẹo không được review kỹ.

### 12.2. Final/private/non-Spring objects

Một private method hoặc object tạo với `new` không phải điểm bảo vệ AOP proxy đáng tin. Với Kotlin (classes/methods thường final) hoặc Java method final, xác minh proxying strategy và configuration; nếu dùng AspectJ weaving thay proxy, đặc tính có thể khác và phải được kiểm thử riêng.

### 12.3. SpEL không tự đi theo mọi thread

`SecurityContextHolder` ở Servlet thường dựa trên `ThreadLocal`. Trong raw `Executor`, `CompletableFuture.supplyAsync` hoặc `@Async` không có context-aware executor, method security có thể không thấy user request. Với Spring MVC `Callable` có tích hợp riêng, nhưng các nested tasks không tự truyền. Dùng `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế được Spring Security hỗ trợ theo đúng version, và kiểm tra cleanup.

**Không** tự cấp ADMIN cho worker để chữa lỗi thiếu context. Worker cần identity tương ứng hoặc service account có scope tối thiểu, và authorization lại nếu tác vụ chờ lâu.

### 12.4. Class-level và method-level annotations

```java
@PreAuthorize("hasRole('USER')")
public class ProfileService {

    public String view() { return "view"; }

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(String id) { return "deleted"; }
}
```

Theo Spring method security, annotation ở **method có thể ghi đè annotation cùng loại ở class**. Ở ví dụ trên, `delete` dùng rule ADMIN của method, **không tự AND** với role USER ở class. Các annotation **khác loại** như `@PreAuthorize` cùng `@PostAuthorize` được thực thi như những kiểm tra riêng và có thể tạo AND ở mức tổng thể.

Với annotation trùng nhau trên nhiều interface gây mơ hồ, Spring Security có thể fail startup; nên đặt annotation rõ ở concrete method và test.

### 12.5. Đừng lặp hai @PreAuthorize trên cùng method

`@PreAuthorize` không được repeat hai lần cho cùng method để kỳ vọng kiểm AND. Dùng một expression kết hợp:

```java
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public void rotateCredential() { /* ... */ }
```

hoặc gọi bean policy.

## 13. Kiểm thử bằng Spring Security Test và JUnit 5

### 13.1. @WithMockUser(roles=...) và authorities=...

```java
@WithMockUser(roles = "ADMIN")
```

thường tạo user có authority `ROLE_ADMIN`. Còn:

```java
@WithMockUser(authorities = "ADMIN")
```

cấp **chuỗi chính xác `ADMIN`**, không tự thêm `ROLE_`.

Khi cần permission:

```java
@WithMockUser(authorities = {"ROLE_USER", "report:read"})
```

Đừng cấp cả authority cần suy ra trong fixture nếu mục tiêu test role hierarchy: test đó vẫn pass khi hierarchy không hoạt động.

`@WithMockUser` tạo authentication cho test, không kiểm tra password provider/JWT converter thật. Muốn test nguồn authorities production, dùng integration test với authentication mechanism thích hợp.

### 13.2. @WithAnonymousUser và tình huống thiếu auth

`@WithAnonymousUser` mô phỏng anonymous principal mà Spring Security xử lý. Dùng để xác minh:

- `isAnonymous()` có thể cho qua.
- `isAuthenticated()` từ chối.
- `isFullyAuthenticated()` từ chối.
- Role/permission business không tự được cấp.
- `permitAll` vẫn cho qua ở method layer.

Với method invocation bị từ chối, Spring Test/Spring Security hiện đại thường ném `AccessDeniedException`, còn xử lý qua HTTP có thể dẫn đến 401, 403 hoặc redirect tùy entry point.

### 13.3. Test service bean đã được proxy

Giả sử có service test:

```java
package com.example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ExpressionProbe {

    @PreAuthorize("permitAll")
    public String publicData() {
        return "public-ok";
    }

    @PreAuthorize("isAuthenticated()")
    public String profile() {
        return "profile-ok";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String admin() {
        return "admin-ok";
    }

    @PreAuthorize("hasAuthority('report:read')")
    public String report() {
        return "report-ok";
    }

    @PreAuthorize(
        "isFullyAuthenticated() and hasAuthority('payment:approve')")
    public String sensitive() {
        return "sensitive-ok";
    }

    @PreAuthorize("isAnonymous()")
    public String anonymousOnly() {
        return "anonymous-ok";
    }
}
```

Class này có thể biên dịch trong project Spring Security/Spring Context có `@EnableMethodSecurity`, và là một probe đơn giản **không phụ thuộc database**.

Mẫu JUnit 5/AssertJ fragments trong test Spring context:

```java
@Autowired
ExpressionProbe probe;

@Test
@WithAnonymousUser
void anonymousCannotAccessProfile() {
    assertThatThrownBy(() -> probe.profile())
        .isInstanceOf(AccessDeniedException.class);
}

@Test
@WithAnonymousUser
void anonymousCanCallAnonymousAndPublic() {
    assertThat(probe.anonymousOnly()).isEqualTo("anonymous-ok");
    assertThat(probe.publicData()).isEqualTo("public-ok");
}

@Test
@WithMockUser(roles = "USER")
void ordinaryUserCannotCallAdmin() {
    assertThatThrownBy(() -> probe.admin())
        .isInstanceOf(AccessDeniedException.class);
}

@Test
@WithMockUser(roles = "ADMIN")
void adminRoleMatchesDefaultPrefix() {
    assertThat(probe.admin()).isEqualTo("admin-ok");
}

@Test
@WithMockUser(authorities = {"ROLE_USER", "report:read"})
void permissionWorksIndependentlyOfRole() {
    assertThat(probe.report()).isEqualTo("report-ok");
}

@Test
@WithMockUser(authorities = "payment:approve")
void fullyAuthenticatedMockUserCanPerformSensitiveTask() {
    assertThat(probe.sensitive()).isEqualTo("sensitive-ok");
}
```

Các snippet yêu cầu `@SpringBootTest` hoặc `@SpringJUnitConfig` có method security, JUnit/AssertJ/Spring Security Test dependencies, bean injection và imports. Một test `@WithMockUser` biểu diễn fully authenticated token thường gặp, nhưng **không** test remember-me behavior thật.

### 13.4. Test role prefix sai

```java
@Test
@WithMockUser(authorities = "ADMIN")
void unprefixedAuthorityIsNotAdminRole() {
    assertThatThrownBy(() -> probe.admin())
        .isInstanceOf(AccessDeniedException.class);
}
```

Khi default prefix là `ROLE_`, chuỗi `ADMIN` không thỏa `hasRole('ADMIN')`. Nếu project có custom prefix, phải cập nhật expected test theo chính sách thực.

### 13.5. Test remember-me không giống @WithMockUser

Một test chỉ dùng `@WithMockUser` không thể chứng minh `isFullyAuthenticated()` phân biệt được remember-me. Cần tạo `RememberMeAuthenticationToken` phù hợp và đặt vào `SecurityContext` trong test, ví dụ dùng `@WithSecurityContext` với custom factory.

Đây là **fragment của Spring Security Test**, cho thấy cấu trúc factory:

```java
import java.util.List;

import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

final class RememberedUserFactory
        implements WithSecurityContextFactory<WithRememberedUser> {

    @Override
    public SecurityContext createSecurityContext(WithRememberedUser ann) {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();

        var authentication = new RememberMeAuthenticationToken(
                "test-remember-me-key",
                ann.username(),
                List.of(new SimpleGrantedAuthority("payment:approve"))
        );
        context.setAuthentication(authentication);
        return context;
    }
}
```

Annotation `WithRememberedUser` có thể được định nghĩa trong test suite:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = RememberedUserFactory.class)
public @interface WithRememberedUser {
    String username() default "remembered-user";
}
```

Đây là **hai fragments** cho test suite, không phải Java độc lập; imports, package visibility và Spring test configuration phải được tổ chức đúng trong project. `RememberMeAuthenticationToken` sử dụng key cho integrity check trong một số cơ chế, còn example factory không thực hiện login cookie thật.

Test:

```java
@Test
@WithRememberedUser
void rememberMeCanBeAuthenticatedButNotFullyAuthenticated() {
    assertThat(probe.profile()).isEqualTo("profile-ok");

    assertThatThrownBy(() -> probe.sensitive())
        .isInstanceOf(AccessDeniedException.class);
}
```

Dù remember-me principal có `payment:approve`, method `sensitive` vẫn từ chối do `isFullyAuthenticated() == false`. Đây là kết quả chính cần chứng minh.

### 13.6. Test ma trận tổng hợp

| Principal test | isAnonymous | isAuthenticated | isFullyAuthenticated | hasRole('ADMIN') | hasAuthority('report:read') |
| --- | --- | --- | --- | --- | --- |
| Anonymous | True | False | False | False | False |
| @WithMockUser(roles="USER") | False | True | True | False | False |
| @WithMockUser(roles="ADMIN") | False | True | True | True | False nếu không mapping |
| @WithMockUser(authorities="report:read") | False | True | True | False | True |
| Custom remember-me với report:read | False | True | False | Theo role được cấp | True |
| @WithMockUser(authorities="ADMIN") | False | True | True | False theo default prefix | False |

Test chính sách nên có **deny cases** cho mỗi action nhạy cảm, và một ca chưa đăng nhập với method public, tránh “hầu hết test đều chạy với ADMIN nên không biết user thường bị mở quyền”.

## 14. Kiểm thử HTTP và method security cùng lúc

### 14.1. Một method đúng không có nghĩa HTTP route đúng

Giả sử:

```java
// Trong SecurityFilterChain của Servlet:
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .authenticated()
.anyRequest().denyAll()
```

trong controller/service lại gọi:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView read(String reportId) { /* ... */ }
```

Client thiếu permission có thể qua HTTP `authenticated` nhưng bị từ chối ở service. Ngược lại, một method `@PreAuthorize("permitAll")` không mở HTTP URL đã bị `denyAll`. Đây là defense-in-depth có chủ đích.

### 14.2. MockMvc negative test

```java
@Test
@WithMockUser(authorities = "report:write")
void writerWithoutReadPermissionCannotRead() throws Exception {
    mockMvc.perform(get("/api/reports/r1"))
        .andExpect(status().isForbidden());
}
```

**Fragment** này chỉ đúng khi HTTP cho người dùng authenticated vào, controller thật gọi Spring-managed service annotated `hasAuthority('report:read')` và không có exception handler tùy chỉnh chuyển status. Nếu test dùng user thiếu CSRF trên POST, một status 403 không chứng minh method-security từ chối; phải đưa CSRF token hợp lệ khi appropriate.

### 14.3. HTTP test không thay thế service test

Một controller chưa được map có thể trả 404 trước khi test tới service. Một HTTP matcher sai có thể chặn ở filter mà service method vốn chưa được kiểm tra. Do đó hãy có:

1. **Service-level test** gọi proxied bean với `@WithMockUser`/`@WithAnonymousUser`.
2. **MockMvc/integration test** qua `SecurityFilterChain`.
3. **Domain test** kiểm tra tenant/owner/row state.
4. **Token/session test** cho authorities thực trong production.

### 14.4. Authentication entry point và status

Guest gọi HTTP endpoint cần auth có thể bị trả **401 Unauthorized**, redirect sang login hoặc một response khác do `AuthenticationEntryPoint` cấu hình. User đã authenticated nhưng thiếu authority thường bị trả **403 Forbidden**. Một method invocation bị từ chối bên ngoài HTTP chủ yếu là **exception hoặc method-denial handling**, không tự “trả HTTP status”.

Không assert cứng một status duy nhất cho mọi project; kiểm tra nơi thực sự xảy ra lỗi.

## 15. Ví dụ Java 17 chạy độc lập: role, authority và trust level

Chương trình sau mô phỏng **ý nghĩa** của các biểu thức phổ biến mà không cần tải Spring. Nó cố ý tách:

- `Trust.ANONYMOUS`: anonymous.
- `Trust.REMEMBER_ME`: user được ghi nhớ, không fully authenticated.
- `Trust.FULL`: user đã xác thực đầy đủ trong mô hình demo.
- Tập authority: các chuỗi `ROLE_*` hoặc permission cụ thể.
- Policy cho public, profile, review, export, approve.

Đây là **mô phỏng giáo dục**, không phải parser SpEL, `AuthenticationTrustResolver` hay `AuthorizationManager` của Spring. Nó không xử lý JWT, session, CSRF, MFA, token freshness hay object-level authorization.

Tạo `SpelAuthConceptDemo.java`:

```java
import java.util.Set;

public class SpelAuthConceptDemo {

    enum Trust {
        ANONYMOUS,
        REMEMBER_ME,
        FULL
    }

    record Caller(
            String name,
            Trust trust,
            Set<String> authorities) {

        Caller {
            authorities = authorities == null
                    ? Set.of() : Set.copyOf(authorities);
        }
    }

    static boolean isAnonymous(Caller c) {
        return c != null && c.trust() == Trust.ANONYMOUS;
    }

    static boolean isAuthenticated(Caller c) {
        return c != null && c.trust() != Trust.ANONYMOUS;
    }

    static boolean isRememberMe(Caller c) {
        return c != null && c.trust() == Trust.REMEMBER_ME;
    }

    static boolean isFullyAuthenticated(Caller c) {
        return c != null && c.trust() == Trust.FULL;
    }

    static boolean hasAuthority(Caller c, String authority) {
        return c != null && c.authorities().contains(authority);
    }

    static boolean hasRole(Caller c, String role) {
        return hasAuthority(c, "ROLE_" + role);
    }

    static boolean hasAnyAuthority(Caller c, String a, String b) {
        return hasAuthority(c, a) || hasAuthority(c, b);
    }

    static String decision(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    static void print(String label, boolean allowed) {
        System.out.println(label + "=" + decision(allowed));
    }

    public static void main(String[] args) {
        Caller guest = new Caller(
                "anonymousUser",
                Trust.ANONYMOUS,
                Set.of("ROLE_ANONYMOUS"));

        Caller remembered = new Caller(
                "mai",
                Trust.REMEMBER_ME,
                Set.of("ROLE_REVIEWER", "report:read"));

        Caller manager = new Caller(
                "linh",
                Trust.FULL,
                Set.of("ROLE_MANAGER", "report:approve", "report:export"));

        Caller admin = new Caller(
                "an",
                Trust.FULL,
                Set.of("ROLE_ADMIN", "report:read"));

        Caller wrongPrefix = new Caller(
                "unprefixed-admin",
                Trust.FULL,
                Set.of("ADMIN"));

        print("guest-public", true);
        print("manager-public", true);

        print("guest-profile", isAuthenticated(guest));
        print("remember-profile", isAuthenticated(remembered));
        print("manager-profile", isAuthenticated(manager));

        print("guest-anonymous-only", isAnonymous(guest));
        print("manager-anonymous-only", isAnonymous(manager));
        print("remember-is-remember-me", isRememberMe(remembered));

        print("remember-full", isFullyAuthenticated(remembered));
        print("manager-full", isFullyAuthenticated(manager));

        print("remember-review",
                isAuthenticated(remembered)
                    && (hasRole(remembered, "REVIEWER")
                        || hasRole(remembered, "ADMIN")));
        print("admin-review",
                isAuthenticated(admin)
                    && (hasRole(admin, "REVIEWER")
                        || hasRole(admin, "ADMIN")));

        print("remember-read",
                hasAnyAuthority(remembered, "report:read", "report:manage"));
        print("guest-read",
                hasAnyAuthority(guest, "report:read", "report:manage"));

        print("remember-export",
                isFullyAuthenticated(remembered)
                    && hasAuthority(remembered, "report:export"));
        print("manager-export",
                isFullyAuthenticated(manager)
                    && hasAuthority(manager, "report:export"));
        print("admin-export",
                isFullyAuthenticated(admin)
                    && hasAuthority(admin, "report:export"));

        print("manager-approve",
                isFullyAuthenticated(manager)
                    && hasRole(manager, "MANAGER")
                    && hasAuthority(manager, "report:approve"));
        print("admin-approve",
                isFullyAuthenticated(admin)
                    && hasRole(admin, "MANAGER")
                    && hasAuthority(admin, "report:approve"));

        print("unprefixed-admin-role",
                hasRole(wrongPrefix, "ADMIN"));
    }
}
```

Biên dịch với JDK 17 trở lên:

```bash
javac SpelAuthConceptDemo.java
java SpelAuthConceptDemo
```

Stdout mong đợi:

```text
guest-public=ALLOW
manager-public=ALLOW
guest-profile=DENY
remember-profile=ALLOW
manager-profile=ALLOW
guest-anonymous-only=ALLOW
manager-anonymous-only=DENY
remember-is-remember-me=ALLOW
remember-full=DENY
manager-full=ALLOW
remember-review=ALLOW
admin-review=ALLOW
remember-read=ALLOW
guest-read=DENY
remember-export=DENY
manager-export=ALLOW
admin-export=DENY
manager-approve=ALLOW
admin-approve=DENY
unprefixed-admin-role=DENY
```

### 15.1. Đọc kết quả theo từng khái niệm

- Public method mở cho guest lẫn manager; đây chỉ là policy mock của demo.
- Remember-me **được coi authenticated** nhưng **không được coi fully authenticated**.
- User có role REVIEWER hoặc ADMIN đều được phép vào review; danh sách role được kết hợp bằng OR.
- Có `report:read` thì read được, nhưng không tự có `report:export`.
- Manager FULL đủ `ROLE_MANAGER`, `report:approve` và `report:export` để thực hiện hai chức năng minh họa.
- Admin FULL chỉ có `ROLE_ADMIN` và `report:read`, nên **không tự** được export/approve; đây là khác biệt giữa role và permission nếu không có mapping/hierarchy.
- Authority `ADMIN` không có tiền tố không thỏa `hasRole('ADMIN')` trong quy ước demo mặc định.

### 15.2. Giới hạn của ví dụ

- Demo dùng `Trust` enum tự tạo, không nhận biết Spring `AnonymousAuthenticationToken`, `RememberMeAuthenticationToken` hoặc `JwtAuthenticationToken`.
- Demo không xử lý SpEL string, method parameter hoặc AOP intercept.
- `hasAuthority` trong demo chỉ kiểm tập quyền trực tiếp, không có `RoleHierarchy`.
- Không có đối tượng/tenant, MFA, session state hay JWT revocation.
- Trường hợp hoàn toàn không có Authentication cần policy fail-closed; demo mô phỏng bằng `c == null`.

**Bước tiếp theo để vận dụng:** viết Spring service probe mục 13 và test Spring context thật, không chuyển các hàm demo thành một authorization framework tự chế trong production.

## 16. Sai lầm phổ biến và cách xử lý

| Triệu chứng hoặc sai lầm | Vì sao xảy ra | Hướng sửa |
| --- | --- | --- |
| `@PreAuthorize` không chặn ai | Chưa bật `@EnableMethodSecurity` hoặc không qua proxy | Bật method security, test proxied bean |
| `hasRole('ADMIN')` bị 403 dù principal có `ADMIN` | Default prefix đòi `ROLE_ADMIN` | Kiểm nguồn authorities/mapping |
| `hasAuthority('report:read')` bị 403 khi chỉ có `ROLE_ADMIN` | Chưa cấp permission hoặc chưa có hierarchy | Cấp/ánh xạ permission theo policy |
| `hasAnyRole('ADMIN','EDITOR')` bị tưởng là AND | “Any” là OR | Dùng `and` hoặc permission riêng nếu cần cả hai |
| `isAuthenticated()` được viết thành `authentication.authenticated` | Token anonymous có thể mang flag authenticated | Dùng trust-resolver-backed expression |
| User remember-me vào được action nhạy cảm | Policy chỉ đòi `isAuthenticated()` | Dùng `isFullyAuthenticated()` khi phù hợp, thêm MFA nếu cần |
| `isFullyAuthenticated()` bị xem là MFA | Nó chỉ loại anonymous/remember-me | Thiết kế MFA/step-up riêng |
| `@PreAuthorize("permitAll")` nhưng HTTP trả 401 | HTTP rule yêu cầu login | Cấu hình HTTP public nếu nghiệp vụ cần |
| Method annotated chạy từ `this.method()` | Self-invocation bypass Spring AOP | Tách bean boundary và test |
| @WithMockUser test pass, JWT production fail | Converter cấp authority khác mock | Test JWT/IDP mapping thật |
| Một user có `ROLE_MANAGER` xóa file tenant khác | Thiếu object authorization | Bean policy tra DB tenant/owner/ACL |
| SpEL báo không tìm thấy `#id` | Java không giữ tên parameter hoặc thiếu @P | Bật -parameters hoặc @P |
| SpEL ném lỗi khi principal là chuỗi/JWT | Giả định principal là UserDetails | Dùng authentication.name hoặc handler theo type |
| Expression có AND/OR sai | Thiếu ngoặc/ưu tiên toán tử | Viết policy rõ và test truth table |
| Task async thiếu authentication | ThreadLocal không đi theo executor tùy ý | Context-aware executor/actor policy |
| RoleHierarchy test đúng nhưng method không áp dụng | Handler không dùng graph | Cấu hình MethodSecurityExpressionHandler và test proxy |
| POST 403 dù role đúng | CSRF hoặc HTTP filter chặn trước method | Thử với CSRF đúng, xem filter chain |
| Rule class và method được tưởng là AND | Method có thể override class @PreAuthorize | Test annotation resolution |
| Không annotation nhưng method vẫn chạy | Method security không tự deny mọi method | Service boundary/HTTP deny-by-default |
| HTTP 200 mà dữ liệu bị lộ | Chỉ test chức năng, không test owner/tenant | Negative data access tests |

### Quy trình gỡ lỗi

1. **Xác định tầng deny:** HTTP, CSRF, authentication, method-security hay domain policy? Đừng đoán từ status 403 đơn lẻ.
2. **Xem authorities đã xác minh:** `Authentication.getAuthorities()` trong test và cách mapper tạo `ROLE_*`/`SCOPE_*`.
3. **Xem trust level:** anonymous, remember-me, fully authenticated và custom tokens có được resolver nhận diện đúng?
4. **Xem SpEL expression thật:** toán tử, ngoặc, tên tham số, bean reference và lỗi evaluation.
5. **Kiểm tra proxy/async:** method được gọi từ bean khác qua AOP? Worker có security context đúng?
6. **Kiểm tra resource policy:** tenant/owner/row state/SoD có được kiểm ở dữ liệu tin cậy?
7. **Test case đối chứng:** user đủ quyền, thiếu quyền, anonymous, remember-me, role prefix sai, JWT converter thực.

Không sửa sự cố bằng cách cấp `ROLE_ADMIN` chung cho mọi user, thay mọi annotation thành `permitAll` hay tắt CSRF.

## 17. Checklist triển khai an toàn

**Cấu hình:**

- [ ] `@EnableMethodSecurity` đã có hiệu lực và bean annotations đi qua proxy.
- [ ] Dự án xác định version Spring Security, authentication mechanism và role prefix.
- [ ] HTTP authorization là lớp riêng; có fallback deny hợp lý.
- [ ] Quy ước `ROLE_*`, `SCOPE_*` và permission nghiệp vụ nhất quán.
- [ ] Nếu có RoleHierarchy, handler SpEL thật sự dùng graph.

**Biểu thức:**

- [ ] `hasRole` dành cho role, `hasAuthority` dành cho chuỗi quyền chính xác.
- [ ] `hasAnyRole`/`hasAnyAuthority` được hiểu là OR; AND được viết tường minh.
- [ ] `isAuthenticated` không được hiểu là “fully authenticated”.
- [ ] `isFullyAuthenticated` chỉ bảo đảm không phải anonymous/remember-me, **không** tự bảo đảm MFA/fresh login.
- [ ] Dấu ngoặc được dùng rõ khi AND/OR cùng biểu thức.
- [ ] Không giả định principal luôn là UserDetails.
- [ ] Tên `#parameter` được discover chính xác; dùng `@P` hoặc `-parameters` khi cần.
- [ ] Logic phức tạp được đưa vào bean policy có nguồn dữ liệu tin cậy.

**Kiểm thử:**

- [ ] Dùng `@WithAnonymousUser` cho tình huống anonymous.
- [ ] Dùng `@WithMockUser(roles=...)` để test role prefix và `authorities=...` cho permission.
- [ ] Tạo remember-me Authentication thật ở test để kiểm `isFullyAuthenticated`.
- [ ] Có negative tests cho role/authority không khớp và data ngoài tenant.
- [ ] Có MockMvc hoặc integration HTTP tests với chain/csrf/entrypoint.
- [ ] Test self-invocation, nested/async tasks khi liên quan.
- [ ] Test JWT/session stale authorities và role revocation theo mức độ nhạy cảm.
- [ ] Với action ghi dữ liệu, khẳng định **không có side effect** khi deny.

**Vận hành:**

- [ ] Không đưa raw tokens/credentials vào logs.
- [ ] Đảm bảo permission/tokens có TTL/revocation strategy.
- [ ] Review mỗi lần thêm method mới hoặc mở role mới.
- [ ] Có audit cho action nhạy cảm, kèm actor và resource scope phù hợp.
- [ ] Có kế hoạch kiểm thử lại khi nâng cấp Spring Security/method expression handler.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `@PreAuthorize("hasRole('ADMIN')")` yêu cầu authority nào theo default?

**Đáp án:** `ROLE_ADMIN`. `ADMIN` trần hoặc `SCOPE_ADMIN` không tự tương đương.

**Câu 2.** `hasAnyAuthority('a','b')` cần cả hai quyền không?

**Đáp án:** Không, đó là OR. Dùng `hasAuthority('a') and hasAuthority('b')` nếu cần đồng thời.

**Câu 3.** Với principal anonymous, `Authentication.isAuthenticated()` có thể true. Có nên dùng nó thay `isAuthenticated()` trong SpEL?

**Đáp án:** Không. Dùng `isAuthenticated()` của Spring Security expression root/trust resolver để phân biệt anonymous đúng cách.

**Câu 4.** Remember-me user có `isAuthenticated()` và `isFullyAuthenticated()` lần lượt là gì?

**Đáp án:** Thông thường true và false, vì remember-me không đạt fully authenticated theo mô hình trust của Spring Security.

**Câu 5.** `isFullyAuthenticated()` có chứng minh user vừa hoàn thành MFA trong 5 phút không?

**Đáp án:** Không. Nó chỉ phân biệt với anonymous/remember-me; MFA và freshness cần cơ chế khác.

**Câu 6.** `@PreAuthorize("permitAll")` có mở HTTP route đang `hasRole('ADMIN')` không?

**Đáp án:** Không. HTTP filter có thể chặn request trước khi method chạy.

**Câu 7.** `@PreAuthorize("isAnonymous()")` có cho user đã đăng nhập qua không?

**Đáp án:** Không trong trust model bình thường; expression dành riêng cho anonymous.

**Câu 8.** User có `ROLE_ADMIN` có mặc nhiên `report:export` không?

**Đáp án:** Không. Cần cấp permission trực tiếp, ánh xạ role→permission ở nguồn xác thực hoặc một graph hierarchy đã được handler sử dụng.

**Câu 9.** Biểu thức `authentication.name == #username` có luôn chứng minh quyền đọc đối tượng không?

**Đáp án:** Không. Chỉ hợp lý nếu username thật sự là định danh owner đáng tin; với resource ID khác, còn cần database/tenant/ACL policy.

**Câu 10.** Khi Java compiler bỏ tên tham số, `#invoiceId` có thể thất bại. Sửa thế nào?

**Đáp án:** Bật `-parameters` hoặc annotate `@P("invoiceId")` theo cơ chế Spring Security; kiểm thử expression resolution trong application context.

**Câu 11.** `@PreAuthorize("hasRole('ADMIN')")` ở method private hoặc được gọi bằng `this.method()` có chắc bảo vệ không?

**Đáp án:** Không trong Spring AOP proxy model thông thường; lời gọi có thể không đi qua interceptor. Đặt security ở Spring-managed service boundary có thể kiểm thử.

**Câu 12.** Hai annotation `@PreAuthorize` trên cùng method có hợp lệ để tạo AND không?

**Đáp án:** Không phải cách được hỗ trợ. Viết một expression với `and`/`or` hoặc gọi policy bean.

**Câu 13.** Test `@WithMockUser(roles="ADMIN")` pass nhưng JWT production bị 403 dù token chứa scope admin. Vì sao?

**Đáp án:** Mock user có `ROLE_ADMIN`, còn JWT có thể được converter đưa về `SCOPE_admin`. Kiểm tra naming/mapping thực.

**Câu 14.** Nếu service `@PreAuthorize("hasAuthority('file:read')")`, user có thể đọc mọi file không?

**Đáp án:** Không. Còn phải kiểm tra quyền trên object, tenant và owner.

**Câu 15.** Ở lớp method, người có `@PreAuthorize("denyAll")` có thể thực thi body qua lời gọi trong cùng bean không?

**Đáp án:** Nếu self-invocation bỏ proxy thì có nguy cơ, vì interceptor không chạy. Không coi annotation là rào chắn duy nhất nếu kiến trúc không đảm bảo enforcement.

**Câu 16.** Khi nào dùng bean policy trong SpEL?

**Đáp án:** Khi cần điều kiện theo tham số, resource, tenant, trạng thái hoặc logic lặp lại; đừng nhồi quá nhiều SQL/logic vào annotation.

**Kết luận:** `@PreAuthorize` kết hợp SpEL giúp trình bày chính sách trước method rõ ràng: **role**, **authority**, **trạng thái xác thực** và **điều kiện domain**. Muốn dùng an toàn, phải hiểu prefix `ROLE_`, khác biệt giữa authenticated và fully authenticated, nguồn authority thật, cơ chế AOP proxy, tham số method, các lớp HTTP/CSRF độc lập và quyền trên từng tài nguyên. Luôn test cả **được phép** lẫn **bị từ chối** với principal phù hợp, không chỉ trường hợp admin thành công.

## Tài liệu tham khảo chính thức

- Spring Security — Method Security, @PreAuthorize, SpEL, expression root, method parameters, RoleHierarchy, proxies: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 — Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture, GrantedAuthority and role prefix: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Servlet Authentication Architecture, SecurityContextHolder and Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Anonymous Authentication and AuthenticationTrustResolver: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — SecurityExpressionRoot Javadoc (authentication states, hasRole, permitAll): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/SecurityExpressionRoot.html
- Spring Security — AuthenticationTrustResolver Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — Role hierarchy and expression handler: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html#authz-hierarchical-roles
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Spring MVC/MockMvc test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Method security test annotations: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework — Spring Expression Language reference: https://docs.spring.io/spring-framework/reference/core/expressions.html
