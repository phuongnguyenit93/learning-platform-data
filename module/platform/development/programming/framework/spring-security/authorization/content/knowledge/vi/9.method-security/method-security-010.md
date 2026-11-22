# Meta-annotation để đặt tên chính sách dễ đọc, tái sử dụng

## 1. Bài toán: biểu thức đúng nhưng mã nghiệp vụ khó hiểu và khó bảo trì

Trong Spring Security, method security cho phép khai báo:

```java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView getInvoice(long invoiceId) { ... }

@PreAuthorize("hasAuthority('invoice:approve') and @invoicePolicy.canApprove(authentication, #invoiceId)")
public void approveInvoice(long invoiceId) { ... }
```

Các biểu thức trên có thể hợp lệ, nhưng khi hệ thống có hàng trăm service method, việc lặp lại chúng khiến mã vừa khó đọc vừa dễ lệch chính sách: chỗ này kiểm tra tenant, chỗ khác bỏ sót; chỗ này dùng `ROLE_MANAGER`, chỗ khác dùng `invoice:approve`; khi quy tắc đổi phải tìm nhiều vị trí.

**Meta-annotation bảo mật** giúp đặt một tên Java có ý nghĩa nghiệp vụ cho biểu thức authorization. Thay vì đọc SpEL dài ở mọi service, người đọc nhìn thấy:

```java
@RequiresInvoiceReadPermission
public InvoiceView listSummary() { ... }

@CanReadInvoice
public InvoiceView getInvoice(long invoiceId) { ... }

@CanApproveInvoice
public void approveInvoice(long invoiceId) { ... }
```

Tất cả tên trên là **tên minh họa do dự án định nghĩa**; Spring Security không cung cấp sẵn các annotation nghiệp vụ ấy. Bên trong annotation phải gắn một annotation bảo mật mà method security hiểu, ví dụ `@PreAuthorize` hoặc `@PostAuthorize`.

Điểm cần nhớ: **đặt tên lại không tự tạo chính sách an toàn**. Nếu `@CanReadInvoice` bên trong chỉ kiểm tra `invoice:read` mà không xét tenant/owner, tên của nó đang **hứa quá nhiều** so với hành vi. Meta-annotation tốt giúp chính sách dễ hiểu, tái sử dụng và kiểm thử; meta-annotation sai có thể che giấu lỗ hổng sau một tên tưởng như chắc chắn.

### Trước và sau

```text
TRƯỚC:
@PreAuthorize("hasAuthority('invoice:read') and " +
  "@invoicePolicy.canRead(authentication, #invoiceId)")
InvoiceView find(long invoiceId);

SAU:
@CanReadInvoice
InvoiceView find(long invoiceId);

ĐỊNH NGHĨA TẬP TRUNG:
@CanReadInvoice
  => @PreAuthorize(
       "hasAuthority('invoice:read') and " +
       "@invoicePolicy.canRead(authentication, #invoiceId)"
     )
```

Kết quả mong muốn là **một nguồn định nghĩa chính sách rõ ràng**, không phải biến mọi biểu thức tùy ý thành những tên annotation trừu tượng khó truy vết.

## 2. Meta-annotation hoạt động như thế nào?

Java cho phép đặt một annotation lên định nghĩa của annotation khác. Một annotation được dùng để chú thích annotation khác được gọi là **meta-annotation**. Spring Security có thể tìm các annotation method security qua cấu trúc này.

Một ví dụ tối thiểu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('ADMIN')")
public @interface IsAdmin {
}
```

Khi viết:

```java
@IsAdmin
public void viewAudit() {
    // Business logic
}
```

Spring Security method security có thể phát hiện `@PreAuthorize` **thông qua** `@IsAdmin` và đánh giá `hasRole('ADMIN')` trước khi chạy phương thức.

Mô hình:

```text
Phương thức dịch vụ
     |
     | @IsAdmin
     v
Định nghĩa @IsAdmin
     |
     | @PreAuthorize("hasRole('ADMIN')")
     v
Method-security pointcut + interceptor
     |
     | Authentication / authorities
     v
Permit hoặc Deny
     |
     v
Thực thi method nếu được phép
```

Đây là cơ chế **phát hiện annotation bảo mật**, không phải sự thay thế `@PreAuthorize` bằng một hệ thống mới. Điểm thực thi vẫn là authorization manager/interceptor của Spring Security và chịu các giới hạn Spring AOP tương tự.

### 2.1. Các thành phần Java quan trọng

| Thành phần | Vai trò | Nếu thiếu/sai |
| --- | --- | --- |
| `public @interface X` | Khai báo loại annotation riêng | Không có kiểu để tái sử dụng |
| `@Target(METHOD)` | Cho phép gắn trên phương thức | Không sử dụng được tại method |
| `@Target(TYPE)` | Cho phép gắn trên lớp/interface | Không gắn được trên class |
| `@Retention(RUNTIME)` | Giữ annotation để framework phát hiện lúc chạy | Retention khác có thể khiến interceptor không thấy |
| `@PreAuthorize(...)` | Quy tắc bảo mật được chứa trong meta-annotation | Tên đẹp nhưng không có kiểm tra từ nhóm pre/post |
| `@Documented` (tùy chọn) | Hiện annotation trong JavaDoc | Không ảnh hưởng phép cấp quyền |
| `@Inherited` (tùy trường hợp) | Quy tắc kế thừa Java của annotation trên class | Không thay thế thuật toán tìm annotation của Spring |
| `@EnableMethodSecurity` | Bật method authorization | Meta-annotation không tự kích hoạt method security |

Trong Java, mỗi `public @interface` thường được đặt trong **một file .java riêng cùng tên**. Các đoạn code dưới đây là mảnh ghép của một dự án Spring, không được nối tất cả các public type vào một file Java duy nhất rồi chạy `javac` như chương trình độc lập.

### 2.2. Điều kiện tối thiểu để annotation có hiệu lực

- Có dependency Spring Security method authorization phù hợp.
- Có `@EnableMethodSecurity` trong cấu hình Spring; Spring Boot Starter Security **không tự bật method security**.
- Nhóm annotation tương ứng được bật: `@PreAuthorize` và `@PostAuthorize` mặc định thuộc `prePostEnabled=true`; `@Secured` cần `securedEnabled=true`; nhóm `@RolesAllowed`/`@PermitAll`/`@DenyAll` cần `jsr250Enabled=true`.
- Phương thức thuộc Spring-managed bean và lời gọi thực sự đi qua proxy/advice phù hợp.
- `Authentication` và bean chính sách liên quan tồn tại, có dữ liệu đáng tin.
- Có test chứng minh lời gọi thiếu quyền bị từ chối **trước khi thực hiện side effect**.

Tạo `@CanReadInvoice` nhưng quên `@EnableMethodSecurity` không có nghĩa “tự động deny”. Nó có thể chỉ trở thành một annotation Java thuần không được method-security interceptor xử lý.

## 3. Thiết kế tên chính sách trước khi viết mã

Một tên annotation tốt phải nói đúng **điều kiện mà nó thực sự bảo đảm**.

| Tên minh họa | Ý nghĩa phù hợp | Nguy cơ đặt tên sai |
| --- | --- | --- |
| `@RequiresInvoiceReadPermission` | Caller có authority `invoice:read` | Không hứa đã kiểm tra tenant/owner |
| `@CanReadInvoice` | Caller được đọc **invoice theo ID cụ thể** với quyền chức năng và object policy | Không nên chỉ kiểm tra role |
| `@CanApproveInvoice` | Đủ permission và điều kiện approval theo tài nguyên | Có thể cần kiểm tra lại trạng thái lúc ghi |
| `@IsFinanceAdmin` | Có role admin ngành tài chính đã ánh xạ đúng | Không mặc định là admin mọi tenant |
| `@MayViewAuditTrail` | Được phép xem audit trail theo phạm vi | Không dùng `authenticated()` đơn thuần |
| `@PublicCatalogRead` | Chỉ thao tác đọc catalog thật sự công khai | Không được mở rộng tới mọi API của service |

Tên tốt thường có một trong các dạng:

- **RequiresXPermission:** chốt về authority chức năng, không cam kết object.
- **CanXResource:** chốt gắn với tham số/tài nguyên thật và policy tương ứng.
- **RequiresSpecificRole:** chốt role, cần chú ý tiền tố `ROLE_` và phạm vi role.
- **MayXUnderCondition:** chốt phức hợp có điều kiện nghiệp vụ; cần test cụ thể.

Hãy tránh những tên chung chung như `@Secure`, `@Trusted`, `@Internal` hoặc `@Authorized` nếu không có hợp đồng rõ. Chúng khó cho reviewer biết chính sách **nào** đang được thực thi và có thể khiến người khác giả định quá mức.

### 3.1. Có nên đặt annotation cho mọi biểu thức?

Không. Một biểu thức chỉ dùng một lần, đơn giản và dễ đọc có thể giữ nguyên:

```java
@PreAuthorize("hasAuthority('audit:read')")
public List<AuditView> list() { ... }
```

Meta-annotation đem lại giá trị lớn nhất khi:

1. Quy tắc được **lặp** ở nhiều service;
2. Quy tắc là một **khái niệm nghiệp vụ ổn định**;
3. Nhiều developer cần sử dụng **chính xác cùng một định nghĩa**;
4. Chính sách có nhiều điều kiện và dễ viết sai khi copy;
5. Cần gom kiểm thử, review và kiểm toán chính sách vào một nơi.

Đừng tạo hàng trăm annotation chỉ để biến một chuỗi một dòng thành một tên một dòng. Mục tiêu là giảm **độ lệch chính sách** và tăng tính diễn đạt.

## 4. Meta-annotation cố định bằng @PreAuthorize

### 4.1. Quyền chức năng: ví dụ hoàn chỉnh một file annotation

File `RequiresInvoiceReadPermission.java`:

```java
package example.security.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('invoice:read')")
public @interface RequiresInvoiceReadPermission {
}
```

Dùng trong một service được Spring quản lý:

```java
@Service
public class InvoiceQueryService {

    @RequiresInvoiceReadPermission
    public List<InvoiceSummary> listOwnInvoices() {
        // Repository còn phải lọc theo tenant và owner.
        return repository.findVisibleForCurrentActor();
    }
}
```

Với `@EnableMethodSecurity`, phương thức này cần authority `invoice:read` để được gọi. Nhưng annotation chỉ xác minh **quyền chức năng**. Lọc dữ liệu trong `repository.findVisibleForCurrentActor()` phải diễn ra dựa trên principal/tenant đã được kiểm chứng, không dựa vào parameter client tùy ý.

Nếu tên là `@CanReadAnyInvoice`, logic bên trong sẽ không đúng với lời hứa: user có quyền đọc hóa đơn không có nghĩa được đọc mọi hóa đơn. Đổi tên hoặc thêm policy object cho khớp.

### 4.2. Chốt role: ví dụ IsFinanceAdmin

File `IsFinanceAdmin.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('FINANCE_ADMIN')")
public @interface IsFinanceAdmin {
}
```

Theo role prefix mặc định, `hasRole('FINANCE_ADMIN')` kiểm tra authority `ROLE_FINANCE_ADMIN`. Nếu ứng dụng nhận nhóm/role từ IdP, cần một mapping đáng tin tới authority của ứng dụng; không tự cho role admin từ raw header hoặc một claim chưa được kiểm chứng.

Nếu finance admin chỉ quản lý một tenant, annotation này chưa xử lý giới hạn tenant. Đừng đặt lên mọi hàm đọc dữ liệu toàn cục rồi xem đó là một “superuser pass”.

### 4.3. Định nghĩa một lần, dùng nhiều lần

Ví dụ một policy phục vụ cả REST, batch và admin workflow:

```java
@RequiresInvoiceReadPermission
public InvoiceSummary fetchSummary(long id) { ... }

@RequiresInvoiceReadPermission
public InputStream exportVisibleInvoices() { ... }

@RequiresInvoiceReadPermission
public InvoiceStats calculateStats() { ... }
```

Cả ba đều dùng cùng authority chức năng, nhưng **khác rủi ro dữ liệu**. Với export, có thể cần quyền `invoice:export` riêng; với thống kê toàn công ty, có thể cần `invoice:aggregate`. Đừng lạm dụng tính tái sử dụng để áp một policy yếu lên những hành động mạnh hơn.

Quy tắc thực hành: **reuse tên chính sách khi các hành động thực sự có cùng yêu cầu**, không reuse chỉ vì chúng nằm cùng module.

## 5. Chính sách theo đối tượng: kết hợp quyền và bean nghiệp vụ

Meta-annotation đặc biệt hữu ích khi biểu thức gồm permission, tham số và một policy bean. Nhưng mẫu code phải bảo đảm tham số được lấy đúng và bean thực hiện kiểm tra đáng tin.

### 5.1. Định nghĩa @CanReadInvoice

File `CanReadInvoice.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public @interface CanReadInvoice {
}
```

Tại sao `@Target(METHOD)` mà không phải `TYPE`? Biểu thức cần tham số `#invoiceId`. Nếu đặt annotation trên cả lớp có nhiều method với chữ ký khác, một số method có thể không có biến ấy và chính sách trở nên khó bảo đảm. Giới hạn mục tiêu giúp tránh áp nhầm.

Dùng trong service:

```java
@Service
public class InvoiceService {

    @CanReadInvoice
    public InvoiceView readInvoice(long invoiceId) {
        return repository.findVisibleInvoice(invoiceId);
    }
}
```

Code trên **là fragment tích hợp**, cần khai báo repository và các kiểu miền trong dự án. Một thiết kế tốt còn yêu cầu repository truy vấn theo đúng tenant và điều kiện quyền, thay vì dựa hoàn toàn vào việc policy đã kiểm tra trước.

### 5.2. Policy bean với danh tính đáng tin

Ví dụ ý định của `invoicePolicy`:

```java
@Component("invoicePolicy")
public class InvoicePolicy {

    private final InvoiceRepository repository;

    public InvoicePolicy(InvoiceRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
            Authentication authentication, long invoiceId) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        // Identity/tenant phải đến từ principal đã được xác minh.
        VerifiedActor actor = VerifiedActor.from(authentication);
        if (actor == null || !actor.active()) {
            return false;
        }

        return repository.existsReadableInvoice(
            invoiceId, actor.tenantId(), actor.userId()
        );
    }
}
```

Mã minh họa dùng các class ứng dụng như `InvoiceRepository` và `VerifiedActor`; chúng phải được triển khai và có hợp đồng an toàn trong dự án. `AnonymousAuthenticationToken` cần import từ `org.springframework.security.authentication.AnonymousAuthenticationToken`, còn `Authentication` từ `org.springframework.security.core.Authentication`.

**Quan trọng:** `authentication.isAuthenticated()` không đủ để loại anonymous authentication trong mọi cấu hình; cần kiểm tra trạng thái principal theo chính sách. Không dùng `(String) authentication.getPrincipal()` hoặc `request.getHeader("X-Tenant-Id")` để tự chế tenant đã xác minh.

Nếu repository check rồi service ghi sau đó, có thể có race condition; với thao tác thay đổi trạng thái cần **câu lệnh ghi có điều kiện/version/transaction** ở tầng dữ liệu.

### 5.3. Tên tham số SpEL và -parameters

Trong biểu thức `#invoiceId`, Spring cần biết tên tham số Java tại runtime. Với Spring Framework 6.1+ và đường phát hiện tên phổ biến, biên dịch có `-parameters` là lựa chọn cần thiết để giữ tên tham số:

```bash
javac -parameters ...
```

Trong Maven/Gradle, cấu hình compiler plugin hoặc toolchain để giữ tên tham số cho source code được method security sử dụng. Nếu không muốn phụ thuộc vào tên Java do compiler cung cấp, cân nhắc `@P("invoiceId")` theo Spring Security hoặc dùng hợp đồng tham số được hỗ trợ đúng phiên bản. Test bằng Java bytecode biên dịch thực tế của dự án, không chỉ bằng mocks trong IDE.

Đổi tên tham số `invoiceId` thành `id` trong method mà quên sửa expression có thể dẫn tới lỗi hoặc deny bất ngờ. **Meta-annotation phụ thuộc tên tham số là hợp đồng API nội bộ**, phải được version hóa và có integration tests.

### 5.4. Đặt tên theo ngữ cảnh không đủ khi cùng ID tồn tại ở nhiều tenant

Nếu `invoiceId=42` có thể trùng giữa hai tenant, policy cần tenant đã xác minh. Một biểu thức như:

```java
@PreAuthorize("@invoicePolicy.canRead(#invoiceId)")
```

không đủ rõ nếu `canRead` lấy tenant từ payload do client tự gửi. Tốt hơn là policy dùng `Authentication` được xác thực và truy vấn kết hợp `invoiceId`, tenant, owner/share/roles; không đặt niềm tin ở tên meta-annotation mà bỏ qua dữ liệu server.

Một khoản invoice có thể được “đọc” trong nhiều tình huống: owner, thành viên chia sẻ, người phê duyệt, admin tenant. Hãy viết các nhánh OR bên trong policy với điều kiện AND tenant/trạng thái bất biến, ví dụ:

```text
canReadInvoice =
  has(invoice:read)
  AND sameTenant
  AND (isOwner OR isValidShareRecipient OR isAssignedReviewer)
```

Không viết nhầm thành:

```text
(has(invoice:read) AND sameTenant AND isOwner)
OR isAssignedReviewer
```

trừ khi người reviewer được chủ đích cho vượt qua permission và tenant, điều cần review đặc biệt.

## 6. Meta-annotation tham số hóa: dùng template có kiểm soát

Meta-annotation cố định thuận tiện nhưng có thể sinh quá nhiều loại như `@IsAdmin`, `@IsManager`, `@IsAuditor`. Spring Security hỗ trợ **template cho biểu thức bên trong meta-annotation**, cho phép tạo một annotation có tham số.

**Phân biệt phiên bản:** `AnnotationTemplateExpressionDefaults` thuộc `org.springframework.security.core.annotation`, được ghi nhận **từ Spring Security 6.4**. Trong Spring Security 6.4/6.5, đăng ký bean để bật xử lý template như tài liệu; từ Spring Security 7.x, kiểm tra hành vi mặc định và cấu hình của bản đã khóa vì cơ chế template được tích hợp hơn. Không copy API này vào project Spring Security 6.3 hoặc cũ hơn rồi coi chắc chắn có class.

### 6.1. Đăng ký bean cấu hình template

Trong project Spring Security 6.4/6.5:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }
}
```

`@Bean static` đặt ở cấu hình giúp bean cấu hình được đăng ký sớm cho method-security infrastructure. Với các custom advisors/interceptors tự xuất bản, phải kiểm tra xem chúng có nhận template defaults hay không. Tạo bean chưa bảo đảm mọi interceptor tùy biến do ứng dụng tự viết có hỗ trợ cùng cơ chế.

### 6.2. Định nghĩa @RequiresRole(String)

File `RequiresRole.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface RequiresRole {
    String value();
}
```

Khi sử dụng:

```java
@RequiresRole("ADMIN")
public void viewAudit() { ... }

@RequiresRole("MANAGER")
public void approveRoutineRequest() { ... }
```

Template giải `{value}` từ annotation attribute thành biểu thức `hasRole('ADMIN')` hoặc `hasRole('MANAGER')` trước khi được đánh giá bởi Spring Security.

Ở đây:

- Trong template, `'{value}'` đã có **dấu nháy** vì đối số mong đợi là string role.
- Tại nơi gọi, dùng `@RequiresRole("ADMIN")`, không viết thêm dấu nháy trong giá trị.
- Đây là giá trị trong **source Java được review**, không phải giá trị từ request user.
- `hasRole("ADMIN")` trong convention mặc định đánh giá `ROLE_ADMIN`; không dùng `"ROLE_ADMIN"` nếu cơ chế đang tự thêm tiền tố.
- Nếu có namespace hoặc tenant role, vẫn cần mapping đã xác minh và object policy.

**Không được tự tin rằng một meta-annotation tham số hóa hoạt động chỉ vì class compile được.** Nếu thiếu template defaults ở bản cần opt-in, placeholder có thể không được thay đúng; test Spring context thực là bắt buộc.

### 6.3. @RequiresAuthority(String)

Một dạng tương tự:

```java
@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresAuthority {
    String value();
}
```

Ví dụ:

```java
@RequiresAuthority("invoice:read")
public InvoiceSummary getSummary() { ... }

@RequiresAuthority("invoice:export")
public byte[] exportInvoices() { ... }
```

Annotation tham số hóa giảm việc tạo nhiều wrapper giống nhau, nhưng **yếu về diễn đạt nghiệp vụ hơn** một annotation cụ thể `@CanApproveInvoice`. Với những policy có owner/tenant/SoD, ưu tiên tên chính sách cụ thể hoặc policy bean thay vì chèn mọi điều kiện vào một string template.

### 6.4. Template có nhiều role và dấu nháy

Tài liệu Spring Security 6.5 mô tả dạng:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAnyRole({roles})")
public @interface HasAnyRole {
    String[] roles();
}
```

Sử dụng:

```java
@HasAnyRole(roles = { "'USER'", "'ADMIN'" })
public String overview() { ... }
```

Ở ví dụ này, **mỗi phần tử đã chứa dấu nháy** để khi template mở rộng, biểu thức trở thành:

```text
hasAnyRole('USER', 'ADMIN')
```

Nếu viết template `hasAnyRole('{roles}')` cho mảng, toàn bộ danh sách có thể biến thành một chuỗi không đúng ý định. Ngược lại, nếu truyền `"USER"` và `"ADMIN"` trong ví dụ không thêm dấu nháy, biểu thức sau khi mở rộng có thể không parse đúng.

Đừng tự phát minh cú pháp template từ cảm giác; đối chiếu JavaDoc/reference của **đúng version** và kiểm thử annotation thật. Trong nhiều dự án, một enum permission hoặc các annotation policy cố định dễ bảo trì hơn việc cho mọi nơi nhập SpEL gián tiếp.

### 6.5. Rủi ro chèn SpEL khi template nhận giá trị không kiểm soát

Placeholder được thay vào một biểu thức SpEL, nên mọi giá trị được đưa vào template phải được xem là **một phần cấu hình chính sách**, không phải dữ liệu nghiệp vụ nhận từ user. Annotation attribute là hằng số compile-time trong Java, nhưng module bên thứ ba, codegen hoặc cấu hình động không được review vẫn có thể tạo biểu thức ngoài ý muốn.

Không tạo cơ chế tự đọc query/header như:

```text
client parameter "role" -> value của biểu thức @PreAuthorize
```

Quyền thực phải dựa vào `Authentication` được xác thực và policy server. Với template string có dấu nháy, không được dùng input chứa dấu nháy/biểu thức tùy ý làm role name; hãy giới hạn vào các role/authority do developer kiểm soát. Nếu muốn điều kiện nghiệp vụ động, truyền **dữ liệu** vào một policy bean với API typed và kiểm tra validation, thay vì tạo SpEL string mới theo request.

### 6.6. Version và cấu hình migraton

| Phiên bản | Khả năng cần nhớ |
| --- | --- |
| Spring Security 6.0–6.3 | Meta-annotation cố định như `@IsAdmin` hoạt động với method security; không giả định `AnnotationTemplateExpressionDefaults` đã có |
| Spring Security 6.4–6.5 | Có `AnnotationTemplateExpressionDefaults`; dùng bean opt-in cho expression template theo tài liệu |
| Spring Security 7.x | Template support được tích hợp làm mặc định theo hướng dẫn migration 7; vẫn cần kiểm tra API/cấu hình chính xác ở version đang dùng |
| Legacy `@EnableGlobalMethodSecurity` | Xem lộ trình chuyển sang `@EnableMethodSecurity`, tránh giả định template/manager giống bản mới |

Khi nâng cấp, cần test lại toàn bộ meta-annotations tham số hóa vì biểu thức sau khi expand là phần **nhạy cảm của chính sách**.

## 7. Meta-annotation cho @PostAuthorize: dùng đúng thời điểm

Spring Security cũng hỗ trợ meta-annotation trên `@PostAuthorize`, đặc biệt hữu ích khi quyền phụ thuộc object trả về.

### 7.1. Chính sách đọc kết quả theo owner

File `ReturnedObjectMustBeOwned.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PostAuthorize;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@PostAuthorize("returnObject.owner == authentication.name")
public @interface ReturnedObjectMustBeOwned {
}
```

Sử dụng:

```java
@ReturnedObjectMustBeOwned
public InvoiceView loadOwnedInvoice(long invoiceId) {
    return repository.loadView(invoiceId);
}
```

Nếu `InvoiceView` có thuộc tính `owner` phù hợp và đối chiếu `authentication.name` chính xác, người gọi không phải owner sẽ không nhận được kết quả trả về khi interceptor đánh giá. Đây là **mã tích hợp minh họa**. Cần xử lý return null, dữ liệu thiếu owner, tenant, resource ID và cách mã hóa actor, không tin trường owner do client tự gửi.

### 7.2. Không dùng after-check để bảo vệ tác vụ ghi

Đặc tính của `@PostAuthorize` là **thân method đã thực thi** trước khi biểu thức được đánh giá. Với:

```java
@ReturnedObjectMustBeOwned
public InvoiceView approveInvoice(long invoiceId) {
    repository.markApproved(invoiceId);
    return repository.loadView(invoiceId);
}
```

chốt sau có thể từ chối kết quả nhưng **hành động đã ghi DB hoặc gọi API bên ngoài**. Không dùng như cơ chế duy nhất để bảo vệ việc duyệt, thanh toán, xóa, email hoặc export bắt đầu chạy.

Một mẫu an toàn hơn:

- Dùng `@PreAuthorize` hoặc meta-annotation `@CanApproveInvoice` trước method.
- Kiểm tra trạng thái/owner/tenant **ở thời điểm ghi**, transaction/lock/version tương ứng.
- `@PostAuthorize` nếu có chỉ thêm điều kiện với kết quả đọc phù hợp.
- Test rằng request bị deny **không có side effect**, không chỉ kiểm tra mã 403.

### 7.3. Kết hợp @PreAuthorize và @PostAuthorize

Nếu một method có **hai nhóm khác nhau**:

```java
@RequiresInvoiceReadPermission
@ReturnedObjectMustBeOwned
public InvoiceView load(long invoiceId) { ... }
```

một chốt pre cho permission và một chốt post cho owner có thể cùng áp dụng: cả hai phải thỏa để lời gọi thành công. Nhưng policy trước khi tải dữ liệu vẫn nên kiểm tra tenant trong query; không vì đã có chốt post mà đọc hàng nghìn record ngoài phạm vi rồi mới lọc.

Điểm quan trọng: **không suy rộng điều này thành việc gắn nhiều meta-annotation cùng mang `@PreAuthorize` để tạo AND**. Spring Security không hỗ trợ lặp cùng loại annotation bảo mật trên một method theo cách tùy ý. Khi có hai điều kiện pre bắt buộc, hãy viết **một biểu thức pre** dùng `and`, hoặc gom vào một policy bean.

## 8. Tổ chức một thư viện annotation chính sách nhỏ, rõ ràng

### 8.1. Đề xuất cấu trúc

Một thư viện chính sách trong dự án Java có thể có:

```text
example/
  security/
    MethodSecurityConfig.java
    policy/
      RequiresInvoiceReadPermission.java
      CanReadInvoice.java
      CanApproveInvoice.java
      RequiresRole.java
      RequiresAuthority.java
    service/
      InvoicePolicy.java
      InvoiceService.java
    test/
      InvoicePolicyTest.java
      InvoiceMethodSecurityTest.java
```

Đây là **gợi ý tổ chức**, không yêu cầu phải tạo package/file theo đúng tên trên. Các annotation có thể nằm trong module shared nếu nhiều service dùng chung, nhưng chính sách cần version và có chủ sở hữu nghiệp vụ rõ.

### 8.2. Một định nghĩa policy cho nhiều entrypoint

Giả sử REST controller, scheduled job và message consumer cùng gọi `InvoiceService.approveInvoice(...)`. Nếu dùng meta-annotation trên service:

```text
REST HTTP chain ----+
                    |
Message consumer ---+--> InvoiceService.approveInvoice
                    |         |
Scheduled job ------+         +-- @CanApproveInvoice
                              +-- transaction/data conditions
```

Điều này **có thể** làm giảm khả năng bỏ sót khi có entrypoint mới. Nhưng method security qua proxy cần `Authentication` hoặc một danh tính dịch vụ phù hợp cho những lời gọi non-HTTP; scheduled job không tự mang principal từ request cũ. Thiết kế một service account/ủy quyền tối thiểu và test. Nếu một job gọi thẳng repository hoặc sử dụng self-invocation, annotation trên service có thể bị bỏ qua.

### 8.3. Nên gắn annotation vào đâu?

Một lựa chọn hợp lý:

- **Lớp service public entrypoint:** bảo vệ hành động nghiệp vụ được gọi từ nhiều kênh.
- **Controller:** có thể thêm chốt HTTP/method cho chức năng, nhưng đừng xem đó là ranh giới duy nhất nếu service tái sử dụng.
- **Class-level:** phù hợp chính sách **chung cho mọi public method** của class.
- **Method-level:** phù hợp khi mỗi hành động khác nhau; cần chú ý annotation method có thể override annotation class cùng loại.
- **Interface:** hữu ích khi service có hợp đồng công khai dùng lại, nhưng cần tránh annotation kế thừa mâu thuẫn từ nhiều interface.
- **Repository:** có thể áp annotation trong một số trường hợp, nhưng không thay query scope hoặc các ràng buộc dữ liệu.

Đặt annotation vào private method chỉ được gọi nội bộ **không tạo ranh giới Spring AOP proxy đáng tin**.

### 8.4. Một thay đổi annotation có thể mở quyền cho nhiều nơi

Nếu `@CanReadInvoice` được dùng trên 50 phương thức, sửa biểu thức bên trong:

```text
TRƯỚC: has(invoice:read) AND sameTenant AND owner
SAU:   has(invoice:read) AND (sameTenant OR admin)
```

là một thay đổi **quyền truy cập tập trung**, ảnh hưởng tất cả 50 phương thức. Đây vừa là lợi ích tái sử dụng vừa là rủi ro blast radius. Cần code review, test regression cho mọi trường hợp deny, audit thay đổi policy và kiểm tra lộ dữ liệu cross-tenant.

Không coi thay đổi chuỗi annotation là “refactor tên” khi nó làm rộng predicate.

## 9. Thứ tự, kế thừa và xung đột annotation

### 9.1. Method-level và class-level

Tài liệu Spring Security mô tả có thể gắn `@PreAuthorize` trên lớp và method. Khi method định nghĩa cùng loại annotation, chính sách method **override** chính sách cùng loại ở class level.

Ví dụ:

```java
@RequiresInvoiceReadPermission
@Service
public class InvoiceOperations {

    public List<InvoiceSummary> list() { ... }

    @IsFinanceAdmin
    public void rebuildIndex() { ... }
}
```

Cả `@RequiresInvoiceReadPermission` và `@IsFinanceAdmin` đều là meta-annotation của `@PreAuthorize`. **Đừng mặc định chúng được AND với nhau** ở `rebuildIndex()`. Trong đường tìm metadata, annotation method có thể thay thế chính sách class-level cùng loại; cần review và test quy tắc cụ thể theo version.

Nếu `rebuildIndex()` phải có **cả quyền đọc invoice lẫn finance admin**, định nghĩa rõ một annotation riêng với một SpEL duy nhất:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and hasRole('FINANCE_ADMIN')"
)
public @interface FinanceAdminWithInvoiceReadPermission {
}
```

Đây là **fragment**, khi triển khai cần bổ sung `@Target`, `@Retention(RUNTIME)` và import phù hợp như các ví dụ hoàn chỉnh. Dù vậy cần tự hỏi hai điều kiện có thực sự bắt buộc hay không, tránh ghép quyền tùy tiện.

### 9.2. Nhiều interface với policy khác nhau

Ví dụ:

```java
interface ReadInterface {
    @PreAuthorize("hasAuthority('invoice:read')")
    String fetch();
}

interface AuditInterface {
    @PreAuthorize("hasAuthority('audit:read')")
    String fetch();
}
```

Nếu một class implement cả hai và cùng method kế thừa metadata bảo mật từ nhiều interface, Spring Security có thể không xác định được chính sách nào phải áp, dẫn tới lỗi khởi động. Cách giải quyết là **định nghĩa chính sách rõ trên concrete method**, hoặc thiết kế interface không có xung đột.

Với meta-annotations cũng vậy: tên mới không xóa được sự nhập nhằng của underlying `@PreAuthorize`.

### 9.3. Lặp cùng nhóm và nhiều nhóm khác nhau

Spring Security ghi rõ không hỗ trợ **lặp cùng annotation method security** trên một method, ví dụ hai `@PreAuthorize`. Cũng không nên stack hai wrapper khác tên nhưng cùng chứa `@PreAuthorize` rồi mong framework tự AND chúng.

Nếu có một `@PreAuthorize` và một `@PostAuthorize`, hai interceptor khác nhau có thể được đánh giá nối tiếp, như mục 7. Nếu có `@Secured` hoặc JSR-250 cùng với `@PreAuthorize`, phải bật nhóm tương ứng và kiểm thử sự phối hợp. Đừng dùng `@PermitAll` để “vượt” các chốt khác.

### 9.4. Có nên meta-annotate @Secured và JSR-250?

Spring Security hỗ trợ phát hiện các nhóm annotation method security được bật, nhưng không nên cho rằng mọi dạng meta-annotation kết hợp/templating có cùng cú pháp và hành vi ở mọi phiên bản. Nếu dự án dùng `@Secured` hoặc `@RolesAllowed`, phải bật `securedEnabled=true`/`jsr250Enabled=true` và đọc đúng JavaDoc. Với mã mới, `@PreAuthorize` thường linh hoạt và dễ thống nhất hơn khi cần biểu thức theo tham số hoặc policy bean.

Không chuyển một chuỗi role trong `@Secured` thành expression SpEL rồi tin nó được parse như `@PreAuthorize`; chúng là cơ chế khác nhau.

## 10. Proxy, self-invocation và phạm vi thực thi

### 10.1. Proxy là ranh giới quan trọng

Trong chế độ `@EnableMethodSecurity` mặc định, Spring method security thường dựa trên Spring AOP proxy. Một lời gọi từ bean khác qua proxy sẽ có cơ hội chạy interceptor; lời gọi `this.method()` trong cùng instance thường **bỏ qua proxy**.

Ví dụ nguy hiểm:

```java
@Service
class InvoiceApprovalService {

    public void runBatch(long invoiceId) {
        approveInvoice(invoiceId);
    }

    @CanApproveInvoice
    public void approveInvoice(long invoiceId) {
        // Cập nhật trạng thái nghiệp vụ.
    }
}
```

Nếu `runBatch` tự gọi `approveInvoice` trên chính instance, annotation có thể không được thực thi. Chuyển logic nhạy cảm sang một Spring bean khác được gọi qua proxy, hoặc dùng ranh giới chính sách trực tiếp tại service/data/transaction. Đừng giải quyết bằng cách thêm annotation vào cả hai method mà không phân tích entrypoints.

### 10.2. Những tình huống khác cần test

- Đối tượng tạo bằng `new` ngoài Spring container không tự có AOP advice.
- Private/final method hoặc final class có hạn chế theo loại proxy; đặc biệt Kotlin có final mặc định nếu không cấu hình open/plugin phù hợp.
- Bean đa giao diện có thể sử dụng JDK proxy, nên lời gọi qua interface và concrete type có khác biệt; kiểm tra cấu hình ứng dụng thật.
- Async/background thread có thể không có `SecurityContextHolder` của HTTP request; dùng cơ chế propagation/ủy quyền có kiểm soát.
- AspectJ weaving có thể xử lý một số giới hạn proxy, nhưng cần dependency/weaving cấu hình đúng; chỉ đổi `mode=ASPECTJ` không tự có weaving.
- Meta-annotation đặt ở một method không tự bảo vệ những lời gọi trực tiếp vào repository hoặc endpoint không đi qua method ấy.

**Chính sách trên annotation là một lớp bảo vệ, không phải bằng chứng mọi đường tới dữ liệu đều đã bị khóa.**

## 11. Tính an toàn của policy bean và các điều kiện nghiệp vụ

### 11.1. Bean name là hợp đồng

Trong SpEL:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #invoiceId)"
)
```

`@invoicePolicy` trỏ tới bean Spring có tên tương ứng. Nếu đổi tên bean hoặc method, expression có thể lỗi runtime. Nên:

- Đặt tên bean tường minh khi cần ổn định hợp đồng, ví dụ `@Component("invoicePolicy")`.
- Test chính sách ở unit level và integration method-security.
- Tránh logic truy vấn tốn kém không có cache/giới hạn hợp lý khi interceptor chạy nhiều lần.
- Không gọi API không idempotent hoặc tạo side effect trong phương thức `canApprove(...)`; nó phải là phép **kiểm tra**.
- Fail closed nếu không xác minh được quyền; không chuyển exception phụ thuộc thành ALLOW.

### 11.2. Authentication và principal

Một meta-annotation:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
```

kiểm tra authority đang được gắn vào `Authentication`. Nó **không xác minh lại nguồn gốc của role**; nhiệm vụ đó thuộc authentication/claim mapper tin cậy. Nếu một gateway chuyển header `X-Role: ADMIN` chưa được xác thực thành `ROLE_ADMIN`, annotation không sửa được sai lầm này.

Tương tự, `@CanApproveInvoice` cần biết tenant và người tạo từ nguồn server, không dựa vào `?tenantId=...` hoặc JSON client tự gửi để quyết định đối tượng.

### 11.3. SoD và ràng buộc trạng thái

Chính sách duyệt invoice có thể bao gồm:

```text
canApprove(invoice, actor) =
  authenticated
  AND hasAuthority(invoice:approve)
  AND sameTenant
  AND assignedApprover
  AND actor != invoice.creator
  AND invoice.status == PENDING
```

Nên gom logic đối tượng vào `InvoicePolicy.canApprove(...)` để thống nhất giữa các endpoint. Khi thực sự cập nhật, dùng transaction, optimistic locking hoặc UPDATE có điều kiện trạng thái/version; một phép `canApprove` trước method không loại bỏ mọi race condition (TOCTOU).

### 11.4. Định nghĩa policy và thực thi data scope phải song hành

Với API list/export, `@RequiresInvoiceReadPermission` có thể cho vào service nhưng truy vấn vẫn phải lọc tập dữ liệu:

```sql
SELECT id, total, owner_id, tenant_id
FROM invoices
WHERE tenant_id = :verifiedTenant
  AND (
       owner_id = :verifiedUser
       OR :hasApprovedTeamAccess = true
  );
```

Đây là SQL mô tả ý định; quyền team access phải được xác định từ nguồn tin cậy, không lấy Boolean trực tiếp từ client. Với multi-tenant, phải cân nhắc mô hình quyền thật, chỉ định rõ dữ liệu có thể xem và không cho query/export khác vượt qua scope.

## 12. Java 17 độc lập: học chính sách được đặt tên và tái sử dụng

Chương trình sau không có Spring dependency. Nó mô phỏng **các chính sách có tên ổn định**, được gọi từ nhiều entrypoint, để cho thấy khác biệt giữa quyền chức năng và quyền tài nguyên. Một bộ policy không biết tên sẽ mặc định từ chối, thay vì cho phép.

Lưu file `NamedMethodPolicyDemo.java`:

```java
import java.util.Set;

public class NamedMethodPolicyDemo {
    enum Status { DRAFT, PENDING, APPROVED }

    record Actor(
        long id, String tenantId, Set<String> authorities,
        boolean active
    ) {}

    record Invoice(
        long id, String tenantId, long ownerId,
        long creatorId, long assignedApproverId,
        Status status, Set<Long> sharedReaders
    ) {}

    static boolean has(Actor actor, String authority) {
        return actor != null
            && actor.active()
            && actor.authorities() != null
            && actor.authorities().contains(authority);
    }

    static boolean sameTenant(Actor actor, Invoice invoice) {
        return actor != null && invoice != null
            && actor.tenantId() != null
            && actor.tenantId().equals(invoice.tenantId());
    }

    static boolean requiresInvoiceReadPermission(Actor actor) {
        return has(actor, "invoice:read");
    }

    static boolean canReadInvoice(Actor actor, Invoice invoice) {
        return requiresInvoiceReadPermission(actor)
            && sameTenant(actor, invoice)
            && (
                actor.id() == invoice.ownerId()
                || (
                    invoice.sharedReaders() != null
                    && invoice.sharedReaders().contains(actor.id())
                )
            );
    }

    static boolean canApproveInvoice(
            Actor actor, Invoice invoice) {
        return has(actor, "invoice:approve")
            && sameTenant(actor, invoice)
            && invoice.status() == Status.PENDING
            && actor.id() == invoice.assignedApproverId()
            && actor.id() != invoice.creatorId();
    }

    static boolean namedPolicy(
            String name, Actor actor, Invoice invoice) {
        if (name == null) {
            return false;
        }
        return switch (name) {
            case "RequiresInvoiceReadPermission" ->
                requiresInvoiceReadPermission(actor);
            case "CanReadInvoice" ->
                canReadInvoice(actor, invoice);
            case "CanApproveInvoice" ->
                canApproveInvoice(actor, invoice);
            default -> false;
        };
    }

    static void show(String label, boolean result) {
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            10, "A", Set.of("invoice:read"), true
        );
        Actor bob = new Actor(
            20, "A", Set.of("invoice:read"), true
        );
        Actor approver = new Actor(
            30, "A", Set.of("invoice:approve"), true
        );
        Actor outsider = new Actor(
            99, "B", Set.of("invoice:read", "invoice:approve"),
            true
        );
        Actor inactive = new Actor(
            10, "A", Set.of("invoice:read"), false
        );

        Invoice pending = new Invoice(
            101, "A", 10, 10, 30,
            Status.PENDING, Set.of(20L)
        );
        Invoice approved = new Invoice(
            102, "A", 10, 10, 30,
            Status.APPROVED, Set.of()
        );
        Invoice selfApproval = new Invoice(
            103, "A", 10, 30, 30,
            Status.PENDING, Set.of()
        );

        show("alice has read permission",
            namedPolicy(
                "RequiresInvoiceReadPermission", alice, pending
            ));
        show("alice reads own",
            namedPolicy("CanReadInvoice", alice, pending));
        show("bob reads shared",
            namedPolicy("CanReadInvoice", bob, pending));
        show("bob reads unshared",
            namedPolicy("CanReadInvoice", bob, approved));
        show("outsider reads cross tenant",
            namedPolicy("CanReadInvoice", outsider, pending));
        show("inactive reads own",
            namedPolicy("CanReadInvoice", inactive, pending));
        show("approver approves pending",
            namedPolicy("CanApproveInvoice", approver, pending));
        show("approver approves approved",
            namedPolicy("CanApproveInvoice", approver, approved));
        show("approver self approves",
            namedPolicy(
                "CanApproveInvoice", approver, selfApproval
            ));
        show("alice without approve permission",
            namedPolicy("CanApproveInvoice", alice, pending));
        show("unknown policy denied",
            namedPolicy("UnknownPolicy", alice, pending));
        show("null actor denied",
            namedPolicy("CanReadInvoice", null, pending));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac NamedMethodPolicyDemo.java
java NamedMethodPolicyDemo
```

Kết quả stdout theo thứ tự:

```text
alice has read permission: true
alice reads own: true
bob reads shared: true
bob reads unshared: false
outsider reads cross tenant: false
inactive reads own: false
approver approves pending: true
approver approves approved: false
approver self approves: false
alice without approve permission: false
unknown policy denied: false
null actor denied: false
```

**Giải thích kết quả:**

1. Alice có permission chức năng `invoice:read` và là owner nên đọc được invoice 101.
2. Bob có quyền đọc và nằm trong danh sách share hợp lệ của invoice 101 nên được đọc nó; với invoice 102 không được share, kết quả false dù permission vẫn có.
3. Outsider thuộc tenant B không thể đọc invoice tenant A, dù có `invoice:read` và `invoice:approve`.
4. Account inactive không được đọc dù quyền vẫn còn trong Set.
5. Approver được duyệt invoice `PENDING` khi được giao duyệt và không phải người tạo; invoice `APPROVED` và trường hợp tự duyệt đều bị từ chối.
6. Policy không xác định và actor null mặc định bị deny. Không có cơ chế “không biết policy thì cho qua”.
7. `namedPolicy` dùng string name chỉ để mô phỏng tư duy; trong ứng dụng Spring, annotation được xử lý bởi method-security advisor, **không** chạy một switch này.

**Giới hạn chương trình:** không có `Authentication`, Spring AOP, proxy, token, Hibernate hay transaction. Logic danh sách share/tenant trong dữ liệu thật phải được xác minh tại server và không tự tin Set do client cung cấp. Lệnh stdout được thiết kế để kiểm chứng ý nghĩa chính sách, không thay thế integration test của meta-annotation.

## 13. Kiểm thử meta-annotation trên Spring bean thật

### 13.1. Test tối thiểu với annotation cố định

Ví dụ một bean đơn giản:

```java
import org.springframework.stereotype.Service;

@Service
public class ReportGateService {

    @RequiresInvoiceReadPermission
    public String read() {
        return "allowed";
    }

    @IsFinanceAdmin
    public String admin() {
        return "admin-allowed";
    }
}
```

Giả định project có các annotation ở mục 4 và cấu hình `@EnableMethodSecurity`. Test JUnit 5:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MetaAnnotationMethodSecurityTest {

    @Autowired
    ReportGateService service;

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanRead() {
        assertEquals("allowed", service.read());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotRead() {
        assertThrows(
            AccessDeniedException.class, service::read
        );
    }

    @Test
    @WithMockUser(roles = "FINANCE_ADMIN")
    void financeAdminCanRunAdminMethod() {
        assertEquals("admin-allowed", service.admin());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotRunAdminMethod() {
        assertThrows(
            AccessDeniedException.class, service::admin
        );
    }
}
```

Đây là **mã test tích hợp**, cần một Spring Boot test context thật, dependency `spring-security-test` và annotation definitions đã được biên dịch. Lời gọi cần đi qua **Spring bean đã proxy**, không dùng `new ReportGateService()`; nếu test tự tạo object, annotation không được interceptor xử lý và kết quả có thể sai.

### 13.2. Test template annotation ở bản 6.4/6.5

Bean thử:

```java
@Service
public class TemplateGate {

    @RequiresRole("MANAGER")
    public String managersOnly() {
        return "manager-zone";
    }

    @RequiresAuthority("invoice:export")
    public String export() {
        return "exported";
    }
}
```

Test nên có:

- Người `@WithMockUser(roles="MANAGER")` qua `managersOnly()`.
- Người `@WithMockUser(roles="USER")` bị từ chối `managersOnly()`.
- Người `@WithMockUser(authorities="invoice:export")` qua `export()`.
- Người chỉ có `invoice:read` bị từ chối `export()`.
- Test khởi động context không lỗi parse placeholder.
- Test không có `AnnotationTemplateExpressionDefaults` chỉ đặt trong **context tách biệt** để minh họa khác biệt, không trộn config trái ngược vào cùng context.

Test ứng dụng thật quan trọng hơn việc chỉ kiểm tra annotation bằng reflection: reflection chỉ chứng minh `@RequiresRole` mang `@PreAuthorize`, không chứng minh Spring interceptor đã kích hoạt và parser đã thay `{value}`.

### 13.3. Test @CanReadInvoice có parameter

Với meta-annotation dựa trên `#invoiceId`:

- Mock/fixture repository có invoice 101 tenant A owner Alice.
- Alice có `invoice:read` và tenant A: được đọc.
- Bob có `invoice:read` nhưng không phải owner/share: từ chối.
- Carol khác tenant nhưng có role cao: từ chối.
- Người thiếu `invoice:read` nhưng là owner: từ chối.
- User anonymous hoặc account inactive: từ chối.
- ID không tồn tại: không đọc được.
- Request bị deny: không trả dữ liệu hoặc phát sinh side effect.
- Biên dịch release thực tế có `-parameters`, để `#invoiceId` được bind đúng.

Mỗi test cần biết **lớp nào đã chặn**. Một `MockMvc` test trả 403 vì CSRF không chứng minh `@CanReadInvoice` được interceptor gọi. Hãy test service trực tiếp qua bean và tạo test HTTP riêng.

### 13.4. Test cấu hình mất/chồng annotation

Những negative test giúp phát hiện lỗi an ninh:

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Chưa bật `@EnableMethodSecurity` | Annotation không tự bảo vệ; test phải phát hiện thiếu config |
| `prePostEnabled=false` | Meta-annotation bọc `@PreAuthorize` không tự hoạt động |
| Self-invocation | Annotation có thể bị bỏ qua khi không qua proxy |
| Annotation trên private/final method | Không dựa vào chốt proxy không áp dụng |
| Class-level và method-level cùng underlying `@PreAuthorize` | Chính sách method có thể override class; không tự AND |
| Hai interface mâu thuẫn | Policy phải được khai báo rõ trên method concrete |
| Hai wrapper cùng mang underlying `@PreAuthorize` | Không trông chờ tự kết hợp, cần một expression thống nhất |
| Template thiếu bean trên bản yêu cầu opt-in | Không coi placeholder đã được thay |
| Template chứa dấu nháy hoặc role lạ | Đã validate và không mở rộng quyền |
| Policy bean lỗi/DB timeout | Hành động nhạy cảm fail closed |
| Người đổi tenant/role trong session | Object policy và thu hồi quyền có hiệu lực theo thiết kế |

Với custom meta-annotation trên `@PostAuthorize`, test rằng method **đọc** trả về object owner đúng thì được phép; không owner thì bị từ chối. Không dùng test pass ở chốt post để chứng minh một thao tác ghi không phát sinh side effect.

### 13.5. MockMvc và HTTP authorization

Có thể có:

```text
HTTP: GET /api/invoices/101 -> authenticated
Service: @CanReadInvoice
DB: query scoped by verified tenant
```

Trong cấu hình ấy, HTTP có thể cho một user đã đăng nhập đi tới service, còn method chặn do thiếu authority/tenant. Điều đó là **phối hợp nhiều lớp đúng**, không nhất thiết mâu thuẫn. Nếu controller khác, export job hoặc event consumer gọi service, method vẫn cần nhận context hợp lệ và object policy đúng.

Đừng dùng meta-annotation làm lý do để mở `anyRequest().permitAll()` trên HTTP. Phải giữ fallback deny, route-level checks và bảo vệ CSRF theo mô hình cookie/session.

## 14. Vận hành và governance cho thư viện policy annotations

### 14.1. Quy ước đặt tên và tài liệu

Mỗi annotation nên có JavaDoc tối thiểu trả lời:

1. Nó bảo vệ **hành động** gì?
2. Cần permission/role nào?
3. Có phụ thuộc tham số method nào (ví dụ `invoiceId`) không?
4. Có kiểm tra tenant/owner/sharing/status không?
5. Có bảo đảm không phát sinh side effect trước khi deny không?
6. Nó được dùng ở method hay class, trên interface nào?
7. Cần phiên bản Spring Security tối thiểu nào?
8. Có test chứng minh cả phép cho phép lẫn phép từ chối không?

Ví dụ hợp đồng rõ ràng:

```java
/**
 * Chỉ gọi method khi actor có invoice:read và được đọc
 * invoiceId trong tenant đã xác minh.
 *
 * Yêu cầu parameter method tên invoiceId (compile -parameters).
 * Không thay thế query scope và transaction invariants.
 */
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public @interface CanReadInvoice {}
```

Đây chỉ là fragment JavaDoc/annotation, cần thêm `@Retention`, `@Target` và import như mục 5 khi tạo file thật.

### 14.2. Đổi tên hay đổi semantics?

- **Đổi tên** `@CanReadInvoice` thành `@MayReadInvoice` nhưng giữ expression: refactor API code, vẫn phải cập nhật nơi dùng/test.
- **Đổi expression** từ owner-only sang owner-or-team: thay đổi chính sách truy cập, phải review bảo mật và kiểm thử phạm vi.
- **Thêm permission** export vào role manager: có thể làm rộng quyền, dù không sửa annotation.
- **Đổi policy bean** từ truy vấn scoped sang `findById`: có nguy cơ IDOR dù annotation không đổi.
- **Tắt method security** hoặc đổi cấu hình AOP: có thể khiến toàn bộ thư viện annotation không còn tác dụng.

Xem annotation policy như **security API**: thay đổi cần migration note, version, người phê duyệt và regression tests.

### 14.3. Kiểm toán và quan sát

Khi một lời gọi bị deny, log phù hợp có thể cho biết:

- Correlation ID;
- Tên chính sách (ví dụ `CanApproveInvoice`);
- Hành động và object type;
- Principal/tenant **đã xác minh**, ở mức tối thiểu;
- Kết quả ALLOW/DENY và mã lý do;
- Thời điểm thay đổi role/policy version.

Không log raw JWT, mật khẩu, session cookie, hồ sơ khách hàng hoặc mọi chi tiết tài nguyên nhạy cảm. Không tự động cho người dùng xem toàn bộ biểu thức SpEL vì có thể lộ cấu trúc nội bộ; với client, dùng mã lỗi và thông điệp thích hợp (401, 403, 404, 409 tùy thiết kế).

Một biểu thức phức tạp gọi nhiều DB queries trong policy bean có thể gây overhead; tối ưu theo cache có khóa tenant/actor/object chính xác, TTL phù hợp, thu hồi quyền và không tái sử dụng kết quả giữa user khác.

## 15. Những lỗi phổ biến

| Lỗi | Vì sao sai/nguy hiểm? | Cách phòng |
| --- | --- | --- |
| Đặt tên `@CanReadInvoice` nhưng chỉ check `ROLE_USER` | Tên hứa kiểm tra object nhưng policy không có | Tách permission và object policy |
| Quên `@EnableMethodSecurity` | Annotation không có interceptor | Bật và integration test Spring bean |
| Thiếu `@Retention(RUNTIME)` | Runtime có thể không thấy annotation | Đặt retention đúng |
| `@Target(TYPE)` cho policy phụ thuộc `#invoiceId` | Class có method không có tham số | Dùng `METHOD` hoặc hợp đồng rõ |
| Đọc `#invoiceId` mà không giữ tên tham số | SpEL không tìm đúng argument | Biên dịch `-parameters`/cấu hình phù hợp |
| Tạo object bằng `new` | Không qua AOP proxy | Gọi Spring bean |
| Self-invocation | Bỏ qua method-security proxy | Refactor ranh giới bean |
| Dùng hai wrapper mang `@PreAuthorize` như AND | Có thể xung đột/không hỗ trợ lặp | Một biểu thức/bean policy |
| Nhầm class-level + method-level thành AND | Method override policy cùng loại | Viết điều kiện tổng hợp rõ |
| Dùng `@PostAuthorize` cho write | Deny sau side effect | Pre-check và transaction/data invariants |
| Dùng template 6.4 trong bản 6.3 | API không tồn tại | Khóa version và kiểm tra JavaDoc |
| Quên bean template trong 6.4/6.5 | Placeholder chưa expand như mong đợi | Bean static + test context |
| Quote array template sai | SpEL parse hoặc semantics sai | Kiểm tra expansion có test |
| Để người dùng kiểm soát giá trị SpEL template | Rủi ro injection và mở quyền | Chỉ giá trị compile-time có review |
| Dùng tên role không thống nhất `ROLE_` | Deny sai hoặc workaround nguy hiểm | Catalog authority/prefix |
| Có permission nhưng bỏ tenant/owner | IDOR/BOLA | Policy bean và query scope |
| Check trước, ghi sau không ràng buộc state | TOCTOU | Conditional update/version/transaction |
| Tắt nhóm pre/post vì lỗi cấu hình | Annotation custom mất chốt | Debug thay vì disable |
| Chỉ test reflection annotation | Không chứng minh interceptor hoạt động | Test qua Spring-managed bean |
| Sửa policy tập trung mà không test toàn bộ nơi dùng | Mở rộng quyền diện rộng | Review, CI regression, audit |
| Quên non-HTTP entrypoint | Job/consumer bypass | Service method + task identity |

## 16. Bài tập thực hành

### Bài 1 — Tên và nội dung chính sách

Tạo `@RequiresInvoiceReadPermission` chỉ kiểm tra `invoice:read` và `@CanReadInvoice` kiểm tra thêm tenant, owner/share. Tìm tình huống user có quyền đọc chức năng nhưng không được xem object cụ thể; giải thích vì sao hai tên không đồng nghĩa.

### Bài 2 — Static meta-annotation chạy trong Spring

Tạo `@IsFinanceAdmin` với `@PreAuthorize("hasRole('FINANCE_ADMIN')")`; gắn lên Spring service public method; bật `@EnableMethodSecurity`. Test với `@WithMockUser(roles="FINANCE_ADMIN")` và `roles="USER"`. Đảm bảo test gọi qua injected bean.

### Bài 3 — Meta-annotation template 6.4+

Đăng ký `AnnotationTemplateExpressionDefaults`. Tạo `@RequiresAuthority("{value}")` đúng cú pháp như mục 6.3; test `invoice:read` và `invoice:export`. Tạo một trường hợp quote sai ở context test riêng để hiểu lỗi. Đừng đưa mã lỗi đó vào production.

### Bài 4 — Parameter binding

Dùng `@CanReadInvoice` phụ thuộc `#invoiceId`. Biên dịch với và không có `-parameters` trong môi trường kiểm thử được kiểm soát; xác minh cách binding của phiên bản đang dùng. Thử đổi tên tham số từ `invoiceId` sang `id` và chứng minh test hồi quy phát hiện vấn đề.

### Bài 5 — Class và method precedence

Đặt `@RequiresInvoiceReadPermission` ở class, `@IsFinanceAdmin` ở một method. Test xem rule method được áp dụng như thế nào. Nếu nghiệp vụ muốn cả hai, viết một biểu thức AND trong một annotation mới thay vì đoán framework tự hợp.

### Bài 6 — Từ chối ở đúng thời điểm

Tạo `@ReturnedObjectMustBeOwned` với `@PostAuthorize`, dùng cho read-only query. Sau đó thử đặt nó lên method ghi và giải thích tại sao deny quá muộn. Thiết kế `@CanApproveInvoice` với pre-check và cập nhật có version/condition.

### Bài 7 — Chạy Java 17

Chạy `NamedMethodPolicyDemo.java` và đối chiếu 12 dòng stdout. Thêm actor auditor, một invoice khác tenant và một policy `CanExportInvoice`; giữ default deny cho tên policy lạ và chỉ cho phép xuất đúng phạm vi.

### Bài 8 — Kiểm thử thay đổi chính sách tập trung

Giả sử `@CanReadInvoice` được dùng trên 20 service method. Nghiệp vụ thêm quyền team read. Liệt kê những case permit/deny phải thêm, nguy cơ tenant crossover, giới hạn dữ liệu export, đường gọi từ message consumer và cách rollback nếu policy mới mở quyền quá rộng.

## 17. Checklist trước khi đưa vào hệ thống

- [ ] Chọn tên phản ánh **đúng điều kiện** mà annotation thật sự kiểm tra.
- [ ] Có `@Retention(RUNTIME)` và `@Target` phù hợp với nơi dùng.
- [ ] Có `@EnableMethodSecurity`, nhóm pre/post hoạt động.
- [ ] Static meta-annotation có một biểu thức rõ, không chứa quyền quá rộng.
- [ ] Với template, kiểm tra Spring Security 6.4+/7.x và bean/mặc định của version đang dùng.
- [ ] Giá trị template là cấu hình compile-time được review, không lấy từ client.
- [ ] Quote, array expansion và role prefix được integration test.
- [ ] Biểu thức dùng `#param` có tên parameter được compiler giữ đúng.
- [ ] Không stack cùng underlying `@PreAuthorize` như một phép AND ngầm.
- [ ] Class/interface/method inheritance không tạo policy mâu thuẫn.
- [ ] Service được gọi qua Spring proxy hoặc weaving đã cấu hình.
- [ ] Policy bean có logic kiểm tra đáng tin, không gây side effect.
- [ ] Query/transaction tiếp tục bảo vệ tenant, owner, trạng thái và version.
- [ ] `@PostAuthorize` chỉ dùng khi after-check phù hợp và không gây side effect bị bỏ sót.
- [ ] Test permit/deny trên Spring bean thật, thêm HTTP integration test khi cần.
- [ ] Có regression test khi thay đổi biểu thức, mapper, prefix hoặc version Spring Security.
- [ ] Có owner/reviewer của policy và ghi nhận thay đổi bảo mật.

## 18. Tự kiểm tra

1. **Meta-annotation là gì?** Một annotation được dùng để chú thích annotation khác; Spring Security có thể phát hiện các annotation method security nằm bên trong.
2. **Tạo `@IsAdmin` có tự bật method security không?** Không; cần cấu hình `@EnableMethodSecurity` và interception phù hợp.
3. **Vì sao phải có `@Retention(RUNTIME)`?** Để runtime scanner của framework nhìn thấy annotation.
4. **Khi nào dùng `@Target(METHOD)` thay vì cả TYPE?** Khi policy phụ thuộc tham số chỉ có trên method, hoặc không phù hợp áp lên cả class.
5. **Tên `@CanReadInvoice` mà chỉ kiểm tra `invoice:read` có đủ không?** Không nếu tên cam kết quyền với invoice cụ thể; còn cần tenant/owner/share.
6. **`@RequiresRole("ADMIN")` khác `@RequiresAuthority("ROLE_ADMIN")` thế nào?** Role matcher mặc định áp prefix, còn authority matcher so tên chính xác; cần mapper thống nhất.
7. **Trong 6.4/6.5 cần gì cho templated annotation?** Bean `AnnotationTemplateExpressionDefaults` được đăng ký theo tài liệu.
8. **Giá trị template có thể lấy từ query user không?** Không nên; đó là một phần biểu thức authorization, phải được kiểm soát và review.
9. **Vì sao `hasAnyRole({roles})` phải chú ý dấu nháy?** Template mở rộng một mảng thành các đối số SpEL; từng phần tử cần cú pháp string đúng.
10. **Nếu Java method đổi tên `invoiceId` thành `id` thì cần làm gì?** Cập nhật policy/annotation hoặc giữ binding rõ và chạy test.
11. **Đặt hai meta-annotation có `@PreAuthorize` để có AND có được bảo đảm không?** Không; không dựa vào stacking cùng underlying annotation, hãy viết một biểu thức thống nhất.
12. **`@PostAuthorize` có thể thay pre-check cho chuyển tiền không?** Không; phép từ chối sau method có thể quá muộn.
13. **Một lời gọi nội bộ `this.approve()` có chắc chạy interceptor không?** Không với proxy Spring AOP thông dụng.
14. **Thêm meta-annotation vào service có thay HTTP security không?** Không; cần kiểm tra cả route/filter chain, method và tài nguyên.
15. **Một annotation dùng ở 50 nơi thì sửa expression có thể ảnh hưởng gì?** Cùng lúc thay đổi quyền ở toàn bộ nơi dùng; cần regression và review.
16. **Bật role hierarchy có giải quyết tenant authorization không?** Không; hierarchy xử lý quan hệ authority, không tự xét dữ liệu.
17. **Nếu một request trả 403, điều đó chứng minh annotation đã chạy?** Không; có thể bị chặn bởi HTTP matcher, CSRF hoặc lớp khác.
18. **Vì sao ưu tiên policy bean cho điều kiện phức tạp?** Dễ unit test với kiểu dữ liệu thật, hạn chế SpEL dài và tránh lặp logic ở nhiều annotation.
19. **Khi nâng Spring Security, cần xem gì?** API template, annotation scanner/interceptor, biểu thức, role prefix, cấu hình AOP và test quyền.
20. **Một principal đủ permission nhưng invoice khác tenant phải thế nào?** Bị từ chối theo object policy; meta-annotation không được mở đường vòng.

**Ghi nhớ:** meta-annotation trong Spring Security là cách đặt **tên nghiệp vụ có ý nghĩa** cho chính sách method authorization, giúp code dễ đọc và thống nhất. Hãy chọn tên phản ánh đúng phạm vi quyền, dùng static wrapper cho chính sách ổn định, template có kiểm soát khi thật sự cần tham số, và giữ các phép kiểm tra tenant/owner/trạng thái tại nơi có dữ liệu tin cậy. Quyết định cuối không đến từ tên annotation mà từ **interceptor đã bật, biểu thức được áp dụng, chính sách nghiệp vụ đúng và kiểm thử chứng minh cả các trường hợp bị từ chối**.

### Tài liệu chính thức

- [Spring Security 6.5 – Method Security / Using Meta Annotations](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 – AnnotationTemplateExpressionDefaults JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/annotation/AnnotationTemplateExpressionDefaults.html)
- [Spring Security – Migration to 7 / Authorization Changes](https://docs.spring.io/spring-security/reference/6.5/migration-7/authorization.html)
- [Spring Security – Method Security (current)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – HTTP authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)