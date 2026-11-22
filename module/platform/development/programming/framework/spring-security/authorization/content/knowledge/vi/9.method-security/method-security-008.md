# Phối hợp nhiều annotation và xử lý khai báo xung đột trong Spring Security Method Security

## Mục tiêu học tập

Trong dự án Spring Security, một service method có thể đồng thời xuất hiện nhiều yêu cầu: người dùng phải có role nghiệp vụ, phải có authority phù hợp, được xem đúng bản ghi của mình, và kết quả trả về không được lộ tài nguyên ngoài phạm vi. Các yêu cầu có thể được biểu diễn bằng `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@RolesAllowed`, `@PreFilter`, `@PostFilter` hoặc annotation tự định nghĩa.

Vấn đề là: **nhiều annotation có tự động tạo OR, AND, override hay lỗi khai báo?** Câu trả lời phụ thuộc vào việc đó là **các loại annotation khác nhau**, **cùng một loại annotation**, hay **khai báo trên method/class/interface trong cây kế thừa**. Hiểu sai có thể làm quyền bị nới ngoài ý định hoặc khiến Spring application không khởi động.

Sau bài này, bạn có thể:

1. Giải thích cơ chế method-security interceptors và ý nghĩa **AND khi phối hợp những loại annotation khác nhau**.
2. Biết vì sao không được lặp `@PreAuthorize` trên cùng method; dùng một biểu thức SpEL hoặc policy bean để diễn đạt `and`/`or`.
3. Phân biệt annotation trên **class** và **method**: method-level của cùng loại **ghi đè** class-level, không tự cộng thêm.
4. Nhận diện khai báo kế thừa từ **nhiều interface** gây nhập nhằng, và giải quyết bằng policy tường minh trên concrete method.
5. Sử dụng `@Secured` và `@RolesAllowed` đúng khi bật opt-in; phân biệt `ROLE_`, roles và authorities.
6. Cân nhắc kết hợp trước/sau invocation hoặc lọc collection mà không kiểm tra quyền quá muộn so với side effects.
7. Viết tests Spring trực tiếp vào service bean để bảo đảm chính sách đạt hoặc bị từ chối đúng yêu cầu.

Bài học dùng **Spring Security 6.x/7.x, Java 17+**, chủ yếu trên Spring-managed service của Servlet application. Những đoạn Spring cần dependencies và context thật. Một chương trình Java 17 độc lập ở phần 12 minh họa logic composition, không giả vờ là implementation của Spring Security.

## 1. Nền tảng: annotation cần được Spring thực thi

`@PreAuthorize("hasRole('ADMIN')")` trong source **không tự động** là một câu lệnh Java được chạy. Spring Security cần được bật method security để đăng ký interceptors vào cơ chế Spring AOP.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Với Spring Security 6.x/7.x:

- `@EnableMethodSecurity` cho phép `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` theo mặc định.
- `@Secured` **không bật mặc định**; cần `securedEnabled = true`.
- JSR-250 annotations (`@RolesAllowed`, `@PermitAll`, `@DenyAll`) **không bật mặc định**; cần `jsr250Enabled = true`.
- Spring Boot Starter Security không tự kích hoạt method security chỉ vì bạn đã thêm dependency.
- Annotation chỉ có hiệu lực trên lời gọi được **Spring intercept**. `new Service()`, self-invocation qua `this`, method không đi qua AOP proxy hoặc test thay bean thật bằng mock có thể làm kiểm tra không được gọi.

Nếu ứng dụng cần cả ba nhóm:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

**Không bật tất cả chỉ vì chúng có sẵn.** Một codebase nên chọn bộ annotation tối thiểu, nhất quán để giảm xung đột và làm việc review dễ hơn.

## 2. Những loại annotation thường gặp và thời điểm chạy

| Annotation | Điểm kiểm tra | Ý nghĩa điển hình |
| --- | --- | --- |
| `@PreAuthorize` | Trước khi gọi thân method | Đánh giá SpEL về principal, authority, arguments hoặc policy bean |
| `@PostAuthorize` | Sau khi method trả kết quả | Đánh giá SpEL dựa vào `returnObject`; từ chối không trả kết quả nếu policy fail |
| `@PreFilter` | Lọc collection/array/map/stream đầu vào trong interceptor | Chỉ cho những phần tử hợp lệ tới thân method |
| `@PostFilter` | Lọc collection kết quả sau invocation | Chỉ cho các phần tử được phép được trả ra |
| `@Secured` | Trước method; cần bật riêng | Kiểm tra tập authority/role khai báo, ít biểu cảm hơn SpEL |
| `@RolesAllowed` | Trước method; JSR-250, bật riêng | Khai báo một hoặc nhiều role được phép |
| `@PermitAll` | JSR-250, bật riêng | Cho phép về phía JSR-250 rule, không bỏ qua những interceptor khác |
| `@DenyAll` | JSR-250, bật riêng | Không cho phép về phía JSR-250 rule |

**Chú ý:** `@PostAuthorize` chạy sau khi thân method đã thực hiện. Nó **không** là hàng rào an toàn duy nhất cho lệnh ghi/xóa/chuyển tiền/gửi email. `@PostFilter` không thay thế query scoping và phân trang ở database.

### Các interceptor độc lập

Spring Security dùng những method interceptors riêng cho các annotation types, ví dụ:

- `@PreAuthorize`: `AuthorizationManagerBeforeMethodInterceptor#preAuthorize` kết hợp `PreAuthorizeAuthorizationManager`.
- `@PostAuthorize`: `AuthorizationManagerAfterMethodInterceptor#postAuthorize` kết hợp `PostAuthorizeAuthorizationManager`.
- `@PreFilter` và `@PostFilter`: các interceptor dành riêng cho filtering.
- `@Secured` và JSR-250: các before-method interceptors tương ứng khi bật.

Chúng có thứ tự trong **Spring AOP advisor chain**, không được áp dụng theo thứ tự các dòng annotation bạn gõ trên file Java. Tài liệu Spring Security nêu ví dụ `@PreFilter` order 100 và `@PreAuthorize` order 200; có thể điều chỉnh nhóm advisor bằng `@EnableMethodSecurity(offset = ...)`. Trừ khi bạn đang tự thiết kế advisor, **không thay đổi thứ tự để cố “làm một annotation thắng annotation khác”**; hãy viết chính sách rõ.

## 3. Quy tắc 1: nhiều loại annotation được kiểm tra nối tiếp (hiểu như AND)

Với các method-security annotations **khác loại** cùng áp dụng cho một invocation, Spring Security xử lý các checks **nối tiếp**. Lời gọi được phép chỉ khi **tất cả các kiểm tra bắt buộc đều đạt**. Về mặt quyết định quyền, đó là **phép AND**, không phải OR.

Ví dụ:

```java
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceApprovalService {

    @Secured("ROLE_APPROVER")
    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approve(long invoiceId) {
        return "approved:" + invoiceId;
    }
}
```

Với `@EnableMethodSecurity(securedEnabled = true)`, method này yêu cầu:

```text
Can invoke approve(id) =
    có GrantedAuthority "ROLE_APPROVER"
    AND
    có GrantedAuthority "invoice:approve"
```

| Principal | Authorities | Kết quả |
| --- | --- | --- |
| Alice | `ROLE_APPROVER`, `invoice:approve` | ALLOW |
| Bob | `ROLE_APPROVER` | DENY, thiếu `invoice:approve` |
| Carol | `invoice:approve` | DENY, thiếu `ROLE_APPROVER` |
| Dave | `ROLE_USER` | DENY |

**Đừng nghĩ thứ tự dòng annotation làm rule “trên thắng dưới”.** `@Secured` và `@PreAuthorize` thuộc hai nhóm interceptor khác nhau. Nếu cả hai đang bật, mỗi nhóm đều có thể từ chối invocation.

### Khi nào cần dùng cả hai?

Phối hợp có thể hữu ích khi codebase đang chuyển từ role-based rules kiểu cũ sang fine-grained authorities. Nhưng với một thiết kế mới, có thể rõ ràng hơn nếu diễn đạt cùng policy bằng **một** `@PreAuthorize`:

```java
@PreAuthorize(
    "hasRole('APPROVER') and hasAuthority('invoice:approve')"
)
public String approve(long invoiceId) {
    return "approved:" + invoiceId;
}
```

`hasRole('APPROVER')` thông thường kiểm tra authority `ROLE_APPROVER` theo role prefix cấu hình. `hasAuthority('invoice:approve')` kiểm tra **đúng chuỗi**, không tự thêm `ROLE_`.

**Không tự tạo quyền:** code phải bảo đảm `Authentication.getAuthorities()` thực sự chứa các authority được dùng. Người có `ROLE_ADMIN` **không tự có** `invoice:approve` nếu không có mapping/hierarchy/policy cấp quyền đó.

## 4. Quy tắc 2: không lặp cùng một annotation như @PreAuthorize

Không thể viết hai `@PreAuthorize` trên cùng method rồi kỳ vọng framework tự hiểu AND hay OR:

```java
// SAI: @PreAuthorize không phải repeatable annotation.
@PreAuthorize("hasAuthority('invoice:read')")
@PreAuthorize("hasRole('AUDITOR')")
public Invoice readInvoice(long id) {
    // ...
}
```

Đây là **ví dụ cấu hình sai**, không phải code có thể compile. Java compiler có thể báo annotation không repeatable; Spring Security cũng **không hỗ trợ** sử dụng lặp cùng loại annotation trong một method.

**Nếu cần cả hai điều kiện (AND):**

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and hasRole('AUDITOR')"
)
public Invoice readInvoice(long id) {
    // ...
}
```

**Nếu chấp nhận một trong hai điều kiện (OR):**

```java
@PreAuthorize(
    "hasAuthority('invoice:read') or hasRole('AUDITOR')"
)
public Invoice readInvoice(long id) {
    // ...
}
```

Hoặc:

```java
@PreAuthorize(
    "hasAnyAuthority('invoice:read', 'invoice:export')"
)
public Invoice readInvoice(long id) {
    // ...
}
```

`hasAnyAuthority` là OR giữa các authority. Nó không tạo logic AND; `hasAnyRole('APPROVER', 'ADMIN')` là OR giữa roles theo prefix tương ứng. Phân biệt rõ OR bên **trong một biểu thức** với AND giữa **những annotation types khác nhau**.

### Nếu policy dài, tách sang bean thay vì SpEL lồng phức tạp

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.mayApprove(authentication, #invoiceId)"
)
public void approve(@P("invoiceId") long invoiceId) {
    // cập nhật sau khi đã qua policy
}
```

`@P` là `org.springframework.security.access.method.P`; nó đặt tên tham số cho SpEL rõ ràng nếu không muốn phụ thuộc vào metadata tên tham số khi biên dịch. `invoicePolicy` là Spring bean được ứng dụng hiện thực, kiểm tra dữ liệu owner/tenant/state từ server. Đây là **snippet tích hợp**, cần policy bean và thân method thực. Không suy ra tính bảo mật chỉ từ tên `mayApprove`; phải test policy.

## 5. Quy tắc 3: cùng một loại annotation ở method ghi đè class-level

Spring Security cho phép đặt method-security annotations ở **class level** để áp một chính sách chung. Nếu một method khai báo **cùng một loại annotation**, khai báo method-level **ghi đè** khai báo class-level; nó không tự **AND** với policy ở class.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("hasAuthority('ledger:read')")
public class LedgerService {

    // Kế thừa class-level ledger:read.
    public String list() {
        return "listed";
    }

    // Ghi đè class-level bằng ledger:write.
    @PreAuthorize("hasAuthority('ledger:write')")
    public String update() {
        return "updated";
    }
}
```

Kết quả:

| Authorities | `list()` | `update()` |
| --- | --- | --- |
| Chỉ `ledger:read` | ALLOW | DENY |
| Chỉ `ledger:write` | DENY | ALLOW |
| Cả hai | ALLOW | ALLOW |
| Không có | DENY | DENY |

**Bẫy quan trọng:** người chỉ có `ledger:write` **vẫn được gọi `update()`**, dù thiếu `ledger:read`, vì `@PreAuthorize` ở method **thay thế** `@PreAuthorize` ở class. Không dùng class-level như “điều kiện nền bắt buộc” nếu bạn nghĩ method-level sẽ tự cộng điều kiện đó.

**Nếu update phải cần cả đọc lẫn ghi:**

```java
@PreAuthorize(
    "hasAuthority('ledger:read') and hasAuthority('ledger:write')"
)
public String update() {
    return "updated";
}
```

Hoặc trích xuất một policy bean/meta-annotation duy nhất biểu diễn toàn bộ bất biến. Trong code review, luôn kiểm tra việc override này khi một class annotation được thêm vào service đã có nhiều method annotations riêng.

### Cùng annotation và annotation khác loại không phải cùng một tình huống

```java
@Secured("ROLE_EMPLOYEE")
public class LedgerService {

    @PreAuthorize("hasAuthority('ledger:write')")
    public String update() {
        return "updated";
    }
}
```

Khi `securedEnabled = true`, `@Secured` (class-level) và `@PreAuthorize` (method-level) là **hai loại khác nhau**, nên có thể **cùng áp dụng**. Chúng không tạo quan hệ ghi đè giống hai `@PreAuthorize` ở class/method. Điều kiện kết hợp là `ROLE_EMPLOYEE AND ledger:write`.

## 6. Quy tắc 4: interface inheritance có thể tạo khai báo mơ hồ

Method-security annotations còn có thể nằm trên **interface**. Khi một implementation nhận cùng method từ hai interfaces nhưng mỗi interface chỉ định **một khai báo bảo mật khác nhau**, Spring Security không thể tự biết policy nào là ý định đúng. Tài liệu Spring Security 6.5/7.x nói trường hợp ambiguous inheritance này có thể làm **startup thất bại**; cần giải quyết bằng annotation tường minh ở concrete method.

**Ví dụ dễ xảy ra:**

```java
public interface ReviewerApi {

    @PreAuthorize("hasAuthority('review:read')")
    String getReport(long reportId);
}

public interface AuditorApi {

    @PreAuthorize("hasAuthority('audit:read')")
    String getReport(long reportId);
}

// Khi là Spring-managed bean với method security đang bật,
// kế thừa hai policy cùng loại từ interfaces là nhập nhằng.
@Service
public class ReportQueryService implements ReviewerApi, AuditorApi {

    @Override
    public String getReport(long reportId) {
        return "report:" + reportId;
    }
}
```

Đây là **minh họa cấu hình sai** cho việc kế thừa policy: imports/beans cần dự án Spring. Không coi annotation nào “ở interface bên trái” sẽ thắng; thứ tự implements không phải hợp đồng bảo mật.

**Khắc phục: đưa chính sách mong muốn lên concrete method**:

```java
@Service
public class ReportQueryService implements ReviewerApi, AuditorApi {

    @Override
    @PreAuthorize(
        "hasAuthority('review:read') and hasAuthority('audit:read')"
    )
    public String getReport(long reportId) {
        return "report:" + reportId;
    }
}
```

Ví dụ chọn **AND** theo chính sách nghiệp vụ giả định. Nếu sản phẩm thật chỉ đòi một trong hai quyền, đổi sang `or` hoặc `hasAnyAuthority` **theo yêu cầu đã duyệt**. Không chữa lỗi khởi động bằng cách tự nới thành `permitAll` hay chọn ngẫu nhiên một interface.

**Lưu ý:** code trước và sau là **hai phương án thay thế**, không đưa cả hai lớp `ReportQueryService` vào cùng source. Khi dùng interface-based JDK proxy hoặc class-based proxy, tiếp tục test behavior với cấu hình AOP thực tế.

## 7. Quy tắc 5: Meta-annotation không phải cách lách việc lặp cùng annotation

Một codebase có thể tạo annotation mang ý nghĩa nghiệp vụ để tránh lặp biểu thức bảo mật dài. Spring Security hỗ trợ **meta-annotations** với `@PreAuthorize`/`@PostAuthorize` và những annotations phù hợp.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "hasRole('FINANCE')"
)
public @interface CanApproveInvoice {
}
```

Service có thể dùng:

```java
@Service
public class InvoiceService {

    @CanApproveInvoice
    public String approve(long invoiceId) {
        return "approved:" + invoiceId;
    }
}
```

Điều kiện đầy đủ nằm trong meta-annotation: `invoice:approve AND ROLE_FINANCE`. `@CanApproveInvoice` giúp đọc nhanh ý nghĩa nghiệp vụ và tái sử dụng policy trên nhiều methods.

### Vẫn phải tránh hai effective @PreAuthorize tại cùng điểm khai báo

Không xem cách sau là “thêm một điều kiện”:

```java
// Tránh: hai nguồn @PreAuthorize trên cùng method.
@CanApproveInvoice
@PreAuthorize("hasAuthority('invoice:override')")
public String approve(long invoiceId) {
    return "approved:" + invoiceId;
}
```

Mặc dù tên annotation khác nhau, `@CanApproveInvoice` **chứa `@PreAuthorize`**. Việc phối hợp như vậy có thể tạo **hai khai báo cùng loại**/policy ambiguities, không phải AND có bảo đảm. Hãy **gộp** điều kiện vào một policy duy nhất, hoặc dùng một method-security annotation thuộc **loại khác** với semantics đã được test.

Tránh tạo nhiều composed annotations đều mang `@PreAuthorize` trên cùng method và tin rằng các điều kiện sẽ tự AND. Khi meta-annotation được parameterize bằng template, phải dùng tính năng **annotation templates** của đúng Spring Security version và kiểm thử SpEL, không coi string template tự được thay trong mọi version.

### Quyền theo object và bean policy

Meta-annotation có thể gói một chính sách phức tạp hơn:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #invoiceId)"
)
public @interface CheckInvoiceApproval {
}
```

Dùng trên method có tham số đặt tên ổn định, ví dụ `@P("invoiceId") long id`. `invoicePolicy` phải lấy tenant/owner/trạng thái invoice từ dữ liệu server, không tin `tenantId` client tự khai. Đây là ví dụ **tích hợp**, không tự triển khai policy bean.

## 8. @Secured và @RolesAllowed: opt-in, OR bên trong nhóm roles

### @Secured

```java
@Secured({"ROLE_APPROVER", "ROLE_FINANCE"})
public String approve(long invoiceId) {
    return "approved:" + invoiceId;
}
```

Một `@Secured` nhận **nhiều authority**; cấu hình này chấp nhận **một trong các authority** được liệt kê, không phải yêu cầu cả hai. Để yêu cầu **cả hai**, dùng `@PreAuthorize("hasAuthority('ROLE_APPROVER') and hasAuthority('ROLE_FINANCE')")`.

Phải bật `@EnableMethodSecurity(securedEnabled = true)`. Nếu chưa bật, chỉ viết `@Secured` trên source không có nghĩa Spring đang chặn nó. Hãy test.

### @RolesAllowed (JSR-250)

```java
import jakarta.annotation.security.RolesAllowed;

@RolesAllowed({"OPERATIONS", "SUPPORT"})
public String export(long reportId) {
    return "exported:" + reportId;
}
```

Với `@EnableMethodSecurity(jsr250Enabled = true)`, role list thể hiện **một trong các roles** được chấp nhận. Trong môi trường mặc định, `"OPERATIONS"` tương ứng `ROLE_OPERATIONS` trong `GrantedAuthority` theo role prefix mặc định. Nếu ứng dụng thay role prefix hoặc tích hợp identity provider riêng, kiểm thử chính xác cách mapping.

Có thể đặt `@RolesAllowed("OPERATIONS")` và `@PreAuthorize("hasAuthority('report:export')")` trên cùng method. Đây là **hai loại annotation** nên cần đủ **cả role và authority** khi cả hai cơ chế được bật.

### @PermitAll và @DenyAll không “ghi đè” tùy tiện những kiểm tra khác

`@PermitAll` là policy cho JSR-250 interception, **không phải lệnh tắt toàn bộ Spring Security**. Nếu cùng invocation vẫn có `@PreAuthorize`/`@Secured` áp dụng, những checks đó không tự biến mất chỉ vì một annotation khác cho phép. `@DenyAll` là deny ở phía JSR-250 khi bật.

**Không đặt cả `@PermitAll` và `@DenyAll` trên một method**, hoặc dùng chúng lẫn với các meta-annotation trái nghĩa để “thử cái nào thắng”. Một method cần một chính sách thống nhất, có thể review và kiểm thử. Với tác vụ rất nhạy cảm, chọn `@PreAuthorize("denyAll()")` hoặc disable entrypoint theo policy và test, không dựa vào trật tự may rủi giữa annotation xung đột.

## 9. @PreAuthorize + @PostAuthorize: hai thời điểm, hai bất biến

Ví dụ bảo vệ **đọc dữ liệu** bằng quyền chức năng trước và ownership sau:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;

public record InvoiceView(
    long id,
    String owner,
    String summary
) {
}

@Service
public class InvoiceQueryService {

    @PreAuthorize("hasAuthority('invoice:read')")
    @PostAuthorize(
        "returnObject.owner().equals(authentication.name)"
    )
    public InvoiceView get(long id) {
        // Giả sử repository trả InvoiceView từ dữ liệu đáng tin.
        return new InvoiceView(id, "alice", "Invoice summary");
    }
}
```

Đây là **Spring snippet**, cần imports/framework, service bean và data layer thực khi tích hợp. Những điều kiện thực thi:

1. **Trước khi chạy thân method:** cần `invoice:read`.
2. **Sau khi thân method trả kết quả:** kiểm tra `returnObject.owner()` so với `authentication.name`.
3. Chỉ khi **cả hai** đạt thì caller nhận `InvoiceView`. Nếu post-check fail, caller bị từ chối **sau khi body đã chạy**.

Ví dụ diễn đạt tốt rủi ro lộ kết quả đọc, nhưng không giải quyết tự động truy vấn/tenant scoping; tải dữ liệu ngoài scope trước khi bị từ chối vẫn có thể tốn tài nguyên, cache hoặc log không cần thiết. Với ứng dụng nhiều tenant, nên **lọc tại repository/query** và dùng policy trước khi đọc khi có thể.

### Vì sao không dùng hậu kiểm làm hàng rào cho hành động ghi?

```java
// SAI VỀ THỜI ĐIỂM nếu muốn ngăn side effect.
@PostAuthorize("hasAuthority('payment:execute')")
public void transferMoney(...) {
    // Lệnh chuyển tiền có thể đã được gọi trước khi hậu kiểm.
}
```

Một `@PostAuthorize` đánh giá sau invocation, nên HTTP 403 không chứng minh transfer đã không diễn ra. Hãy dùng `@PreAuthorize` hoặc kiểm tra trước side effect, kết hợp transaction, locking/query condition và idempotency khi phù hợp. `@Transactional` không thể tự đảo ngược mọi side effect bên ngoài database.

## 10. @PreFilter và @PostFilter phối hợp với authorization

`@PreFilter` và `@PostFilter` không đơn thuần là “permission check true/false” cho cả lời gọi. Chúng lọc các phần tử collection/array/map/stream theo policy.

Ví dụ một method nhận list công việc:

```java
@PreFilter("filterObject.owner().equals(authentication.name)")
@PreAuthorize("hasAuthority('task:process')")
public List<Task> process(List<Task> tasks) {
    // Thân method nhìn thấy danh sách đã được pre-filter.
    return List.copyOf(tasks);
}
```

Ý nghĩa:

- `@PreAuthorize` bảo vệ **quyền gọi thao tác process**.
- `@PreFilter` bỏ những phần tử mà caller không sở hữu khỏi collection truyền vào, theo cơ chế filtering tương ứng.
- Để một collection input được lọc bằng cách xóa phần tử, hãy dùng **mutable collection** phù hợp và test tác động của filtering. Đừng mặc định truyền `List.of(...)` bất biến rồi kỳ vọng việc lọc luôn thành công.
- Nếu method có **nhiều tham số là collection**, chỉ rõ `filterTarget` khi cần để tránh mơ hồ mục tiêu.
- Nếu nghiệp vụ phải **từ chối cả batch khi có một phần tử không có quyền** (all-or-nothing), dùng `@PreFilter` không đủ: lọc bỏ item có thể khiến partial processing không mong muốn. Hãy xác minh mọi item trước khi ghi hoặc reject batch.

`@PostFilter` dùng sau method để lọc collection result, nhưng truy vấn tất cả rows rồi lọc tại Java thường không hiệu quả và có thể làm sai pagination/count. Đặt permission scoping ở query/database khi có thể.

**Cảnh báo thứ tự:** các annotations được thực thi bởi những interceptors có thứ tự riêng; lọc input có thể xảy ra trước authorization rule khác theo advisor ordering. Không thiết kế method dựa vào giả định các filter/check chạy đúng theo thứ tự dòng source.

## 11. Xung đột ở nhiều tầng: ma trận xử lý

| Tình huống | Điều xảy ra/cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Hai `@PreAuthorize` trên một method | Không hỗ trợ lặp, có thể lỗi compile | Gộp vào **một SpEL** với `and`/`or` |
| `@PreAuthorize` ở class và cùng loại ở method | Method-level **override**, không AND | Viết toàn bộ bất biến cần thiết ở method |
| Hai interfaces cùng khai `@PreAuthorize` khác nhau cho một method | Ambiguous inherited policy; có thể fail startup | Đặt một annotation tường minh lên concrete method |
| `@Secured` + `@PreAuthorize` | Hai types, kiểm tra nối tiếp khi đều bật → AND | Giữ cả hai khi có lý do hoặc hợp nhất policy |
| `@RolesAllowed` + `@PreAuthorize` | Hai types, check cả JSR-250 và SpEL nếu bật | Test role prefix và authority |
| `@PermitAll` cùng `@PreAuthorize` | Không thể giả định PermitAll bỏ qua pre-check | Tránh biểu đạt gây nhầm, test policy |
| `@DenyAll` cùng annotation cho phép | Xung đột mục đích; không dựa vào “thứ tự thắng” | Chọn một business policy rõ ràng |
| Hai custom annotations cùng chứa `@PreAuthorize` | Hiệu quả là nguồn khai báo cùng loại mơ hồ | Gộp SpEL thành **một** meta-annotation |
| `@Secured` hiện diện nhưng `securedEnabled=false` | Interceptor không bật, rule có thể không thực thi | Bật đúng opt-in hoặc chuyển sang PreAuthorize |
| `@RolesAllowed` hiện diện nhưng `jsr250Enabled=false` | JSR-250 rules có thể không hoạt động | Bật đúng opt-in, test trực tiếp service |
| `@PostAuthorize` trên method ghi dữ liệu | Check quá muộn đối với side effects | Chuyển bất biến chặn sang pre-check |
| Annotated method được gọi qua `this.method()` | Self-invocation có thể bỏ proxy | Bảo vệ public entrypoint hoặc tách bean |
| Cùng service bị mock trong test | Có thể không chạy interceptor của bean thật | Test bean thật, mock dependency repository |
| HTTP rule cho phép nhưng service thiếu role | Service vẫn có quyền từ chối | Test service exception và HTTP mapping |
| Anonymous hoặc background job không có context | Authn không có/không phù hợp | Thiết kế system identity/propagation, không cấp admin mặc định |

**Tư duy giải quyết:** xác định trước **business invariant** bằng văn xuôi, chọn một nơi khai policy chính, rồi test **cho phép + từ chối**. Không chọn cơ chế theo việc annotation nào dễ chèn nhất.

## 12. Java 17 chạy độc lập: mô phỏng AND, OR, override và ambiguous policy

Ví dụ này là chương trình **thuần Java 17**, chạy được không cần Spring. Nó mô phỏng logic kết hợp checks (AND), quyền thay thế ở method level, OR trong một biểu thức và một lựa chọn chủ động khi có hai interfaces đưa ra policy khác nhau. Đây không phải cách Spring AOP dò annotations; nó chỉ giúp học cách **suy luận về quyết định quyền**.

Lưu file **`AnnotationCompositionDemo.java`**:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class AnnotationCompositionDemo {

    record Actor(String name, Set<String> authorities) {
        boolean has(String authority) {
            return authorities.contains(authority);
        }
    }

    static boolean allPass(
        Actor actor, List<Predicate<Actor>> checks
    ) {
        return checks.stream().allMatch(check -> check.test(actor));
    }

    static String decision(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Actor approver = new Actor(
            "alice", Set.of("ROLE_APPROVER", "invoice:approve")
        );
        Actor roleOnly = new Actor(
            "bob", Set.of("ROLE_APPROVER")
        );
        Actor authorityOnly = new Actor(
            "carol", Set.of("invoice:approve")
        );

        List<Predicate<Actor>> combined = List.of(
            a -> a.has("ROLE_APPROVER"),
            a -> a.has("invoice:approve")
        );

        System.out.println(
            "Both checks, approver: " +
            decision(allPass(approver, combined))
        );
        System.out.println(
            "Both checks, role only: " +
            decision(allPass(roleOnly, combined))
        );
        System.out.println(
            "Both checks, authority only: " +
            decision(allPass(authorityOnly, combined))
        );

        Actor writer = new Actor(
            "writer", Set.of("ledger:write")
        );
        // Method-level policy thay thế class-level policy:
        Predicate<Actor> classRead =
            a -> a.has("ledger:read");
        Predicate<Actor> methodWrite =
            a -> a.has("ledger:write");

        System.out.println(
            "Class rule, writer: " +
            decision(classRead.test(writer))
        );
        System.out.println(
            "Method override, writer: " +
            decision(methodWrite.test(writer))
        );

        Actor auditor = new Actor(
            "auditor", Set.of("audit:read")
        );
        // Hai interface policy khác nhau phải chọn rõ:
        // bên dưới chủ động chọn OR theo yêu cầu giả định.
        Predicate<Actor> mergedRule =
            a -> a.has("review:read") || a.has("audit:read");

        System.out.println(
            "Explicit OR, auditor: " +
            decision(mergedRule.test(auditor))
        );
    }
}
```

Lệnh chạy bằng **JDK 17+**:

```bash
javac AnnotationCompositionDemo.java
java AnnotationCompositionDemo
```

**Stdout chính xác:**

```text
Both checks, approver: ALLOW
Both checks, role only: DENY
Both checks, authority only: DENY
Class rule, writer: DENY
Method override, writer: ALLOW
Explicit OR, auditor: ALLOW
```

Giải thích:

- Hai predicates được yêu cầu đồng thời → **AND**; thiếu một quyền thì DENY.
- Trong mô phỏng method override, writer thiếu `ledger:read` nhưng có `ledger:write`: class rule riêng DENY, method rule mới ALLOW. Đó là **thay thế**, không cộng.
- Hai nguồn yêu cầu review/audit không được tự hợp nhất theo ý thích: ví dụ **chủ động chọn OR** để minh họa cần có quyết định nghiệp vụ. Khi triển khai Spring phải ghi **một policy tường minh** ở concrete method.
- Chương trình không đọc annotation thật, không tạo SecurityContext, không kiểm thử Spring proxies. Để xác nhận hiệu lực framework, dùng tests ở phần 13.

## 13. Spring JUnit test: chứng minh annotation composition thực tế

Một test đúng phải lấy **service thật từ Spring ApplicationContext**, bật method security tương ứng, dùng `@WithMockUser` để tạo `Authentication`, rồi gọi method **qua Spring bean proxy**. Không chỉ nhìn HTTP status hoặc test thuần Java trên service được tạo bằng `new`.

Dưới đây là **một lớp JUnit 5 có thể đặt trong project test Spring** có dependencies `spring-context`, `spring-security-config`, `spring-security-test`, `spring-test`, `jakarta.annotation-api` và JUnit 5 phù hợp. Không thể biên dịch bằng JDK thuần; cần Maven/Gradle cùng version/BOM.

```java
import jakarta.annotation.security.RolesAllowed;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(AnnotationCompositionTest.Config.class)
class AnnotationCompositionTest {

    @Autowired ApprovalService approvals;
    @Autowired LedgerService ledgers;
    @Autowired ExportService exports;

    @Test
    @WithMockUser(authorities = {"ROLE_APPROVER", "invoice:approve"})
    void bothAnnotationsMustPass() {
        assertEquals("approved:42", approvals.approve(42L));
    }

    @Test
    @WithMockUser(authorities = "ROLE_APPROVER")
    void roleWithoutFineGrainedAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> approvals.approve(42L));
    }

    @Test
    @WithMockUser(authorities = "invoice:approve")
    void authorityWithoutRoleIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> approvals.approve(42L));
    }

    @Test
    @WithMockUser(authorities = "ledger:write")
    void methodLevelPreAuthorizeOverridesClassLevel() {
        assertEquals("updated", ledgers.update());
        assertThrows(AccessDeniedException.class, ledgers::list);
    }

    @Test
    @WithMockUser(authorities = {"ROLE_OPERATIONS", "report:export"})
    void jsr250AndPreAuthorizeBothPass() {
        assertEquals("exported", exports.export());
    }

    @Test
    @WithMockUser(authorities = "report:export")
    void jsr250RoleIsStillRequired() {
        assertThrows(AccessDeniedException.class, exports::export);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "invoice:read")
    void postCheckRejectsWrongOwnerAfterMethodRuns() {
        assertThrows(AccessDeniedException.class,
            () -> approvals.view(42L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:read")
    void postCheckAllowsOwner() {
        assertEquals("alice", approvals.view(42L).owner());
    }

    @Configuration
    @EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
    static class Config {
        @Bean ApprovalService approvals() {
            return new ApprovalService();
        }
        @Bean LedgerService ledgers() {
            return new LedgerService();
        }
        @Bean ExportService exports() {
            return new ExportService();
        }
    }

    public static class ApprovalService {
        @Secured("ROLE_APPROVER")
        @PreAuthorize("hasAuthority('invoice:approve')")
        public String approve(long id) {
            return "approved:" + id;
        }

        @PreAuthorize("hasAuthority('invoice:read')")
        @PostAuthorize("returnObject.owner() == authentication.name")
        public InvoiceView view(long id) {
            return new InvoiceView(id, "alice");
        }
    }

    public record InvoiceView(long id, String owner) {}

    @PreAuthorize("hasAuthority('ledger:read')")
    public static class LedgerService {
        public String list() {
            return "listed";
        }

        @PreAuthorize("hasAuthority('ledger:write')")
        public String update() {
            return "updated";
        }
    }

    public static class ExportService {
        @RolesAllowed("OPERATIONS")
        @PreAuthorize("hasAuthority('report:export')")
        public String export() {
            return "exported";
        }
    }
}
```

**Vì sao test này quan trọng:**

- Kiểm tra hai annotation types `@Secured` + `@PreAuthorize` đều thực sự hoạt động (không chỉ có mặt trong source).
- Kiểm tra override class/method **không phải AND** đối với cùng `@PreAuthorize`.
- Kiểm tra `@RolesAllowed` là interceptor JSR-250 có vai trò riêng khi đã bật.
- Kiểm tra `@PostAuthorize` có thể từ chối **sau khi method đã tạo result**.
- Không có controller hoặc URL trong tests: đây là **method-security tests** thuần ở boundary service.
- `@WithMockUser(authorities = {...})` khai đầy đủ authorities; **không** kết hợp `roles` và `authorities` trên cùng annotation nếu version test support không cho phép cách dùng đó.
- Test context dùng nested public static classes để Spring AOP có thể tạo proxy; service bean thật được inject. Tùy dự án và custom configuration, classpath/proxy strategy phải kiểm chứng trên môi trường thực.

**Không đưa ví dụ “hai interface xung đột” vào cùng context test này**, vì nó được thiết kế để minh họa một cấu hình **có thể làm context không khởi động**. Hãy viết **test khởi tạo context riêng** cho lớp mâu thuẫn và test context hoạt động sau khi thêm annotation cụ thể; tách khỏi bộ integration tests đang cần chạy xanh.

## 14. Kiểm thử conflict resolution, inheritance và meta-annotation

Một ma trận QA hữu ích:

| Ca kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Hai annotation types với AND | Chỉ có role, thiếu authority | DENY |
| Hai annotation types với AND | Có đủ role + authority | ALLOW |
| Một `@PreAuthorize` với OR | Chỉ có một trong hai authority | ALLOW theo policy |
| Class-level và method-level cùng loại | Chỉ có quyền method | ALLOW method, không tự cần quyền class |
| Interface conflict | Hai interfaces có `@PreAuthorize` khác nhau | Detect ambiguity, khắc phục bằng concrete method policy |
| Meta-annotation duy nhất | User đạt policy chứa trong meta | ALLOW |
| Meta-annotation policy | User thiếu một điều kiện | DENY |
| `@Secured` không được enable | Annotation có nhưng interceptor tắt | Không giả định bảo vệ; test xác nhận và sửa config |
| JSR-250 bật | User có role+permission | ALLOW |
| JSR-250 bật | User chỉ có permission | DENY vì thiếu role |
| Pre + Post | Đủ quyền nhưng sai owner | DENY sau invocation |
| Pre + Post | Đủ quyền và đúng owner | ALLOW |
| Anonymous | Không có quyền cần thiết | DENY |
| Self-invocation | `this.annotatedMethod()` | Test khả năng bypass proxy và sửa thiết kế |
| Production object policy | Đủ role nhưng document ngoài tenant | DENY ở service/query |
| Side-effecting operation | User bị từ chối trước khi ghi | Repository/external calls không được chạy |

### Cách kiểm tra startup ambiguity trong dự án

1. Định nghĩa hai interfaces có **chính sách cùng loại khác nhau** cho cùng một method signature.
2. Tạo concrete bean implements cả hai mà không khai policy cụ thể.
3. Khởi chạy application context với `@EnableMethodSecurity` để xác định lỗi mơ hồ theo version thực tế; không cho test này chạy chung với suite đang cần context thành công.
4. Thêm **một** annotation ở concrete method thể hiện policy đã review.
5. Chạy lại test context, tiếp theo dùng `@WithMockUser` để kiểm tra cả ALLOW và DENY. Không coi “đã startup được” là đủ bằng chứng quyền đúng.

### Quan sát side effects

Với operation có ghi DB hoặc phát event, test DENY cần assert:

- method body không chạy khi pre-check từ chối;
- repository update/delete không được gọi;
- không phát event, gửi email hoặc gọi external API;
- transaction không lưu mutation ngoài ý định.

Đừng chỉ assert một HTTP 403 rồi kết luận mọi thao tác nội bộ đã được chặn: 403 có thể do HTTP authorization, CSRF hoặc `@PostAuthorize` sau khi side effect đã xảy ra.

## 15. Lỗi thiết kế thường gặp

1. **Xem nhiều annotations là OR:** các loại method security checks cùng áp dụng thường cần **đều đạt**.
2. **Lặp `@PreAuthorize` hai lần trên method:** annotation không repeatable, không hỗ trợ. Dùng một expression.
3. **Tin class-level `@PreAuthorize` luôn cộng với method-level `@PreAuthorize`:** method-level **ghi đè** policy class-level.
4. **Kế thừa annotation khác nhau từ hai interfaces và nghĩ Spring chọn một:** cần policy cụ thể trên implementation.
5. **Gắn nhiều meta-annotations chứa `@PreAuthorize` lên cùng method:** tạo ambiguity không được bảo đảm AND.
6. **Dùng `hasRole('ADMIN')` và `hasAuthority('ADMIN')` như tương đương:** role thường có prefix `ROLE_`.
7. **Nhầm `@Secured({"ROLE_A","ROLE_B"})` là AND:** danh sách là **một trong các authority**.
8. **Đặt `@Secured` nhưng quên `securedEnabled=true`:** annotation có thể không hoạt động.
9. **Đặt `@RolesAllowed` nhưng quên `jsr250Enabled=true`:** JSR-250 policy có thể bị bỏ qua.
10. **Dùng `@PermitAll` để thử bypass `@PreAuthorize` khác:** annotation cho phép của nhóm này không tắt các interceptor khác.
11. **Đặt `@PostAuthorize` lên lệnh ghi/xóa:** hậu kiểm quá muộn để bảo đảm không có side effect.
12. **Dùng `@PostFilter` như thay thế query scoping:** có thể tốn bộ nhớ, sai pagination hoặc lộ dữ liệu nội bộ trước filter.
13. **Dùng `@PreFilter` cho batch phải all-or-nothing:** filtering có thể âm thầm bỏ items thay vì DENY cả yêu cầu.
14. **Giả định thứ tự dòng annotation là thứ tự thực thi:** AOP advisors có ordering riêng.
15. **Quên proxy/self-invocation:** annotation trên method được gọi qua `this` có thể không được intercept.
16. **Test bằng `new Service()` hoặc mock chính service:** không xác nhận Spring method security.
17. **Dựa vào HTTP 403 để kết luận mọi annotation đều chạy:** có thể bị chặn trước method bởi CSRF/HTTP policy.
18. **Không kiểm tra permission theo object/tenant:** role và authority chỉ là một lớp, không cho phép mọi ID.
19. **Trộn các phiên bản Spring Security 5.x/6.x/7.x mà không kiểm tra behavior:** framework cũ có semantics/annotations khác, cần migration tests.
20. **Chọn policy chỉ để làm context startup thành công:** ambiguity phải được giải quyết theo invariant nghiệp vụ, không theo thứ tự interface.

## 16. Checklist triển khai và code review

- [ ] Application bật `@EnableMethodSecurity` trong context chứa service được bảo vệ.
- [ ] Chỉ bật `securedEnabled`/`jsr250Enabled` khi ứng dụng thật sự dùng annotation tương ứng.
- [ ] Với nhiều annotations **khác loại**, đã xác định nghĩa AND/điểm chặn của từng loại.
- [ ] Với nhiều điều kiện trong **một annotation**, đã chọn `and`, `or` hoặc `hasAnyAuthority` đúng policy.
- [ ] Không có `@PreAuthorize` lặp hoặc nhiều composed annotations cùng nguồn `@PreAuthorize` trên một method.
- [ ] Method-level annotation cùng loại đã được review là **override** class-level, không phải bổ sung.
- [ ] Không có method kế thừa policy mơ hồ từ hai interfaces; concrete method có policy rõ.
- [ ] Role prefix được mapping đúng `ROLE_`/custom hierarchy/authorities thực tế.
- [ ] Policy bean dùng dữ liệu identity/owner/tenant đáng tin, không tin client tự khai.
- [ ] Với thao tác ghi, authorization chặn **trước** side effect; không chỉ dựa vào `@PostAuthorize`.
- [ ] Với filtering, đã quyết định partial-filter hay all-or-nothing theo nghiệp vụ.
- [ ] Gọi service qua **Spring-managed proxy**; tránh bypass do self-invocation hoặc manual instantiation.
- [ ] Có direct-service JUnit tests cho ALLOW, DENY, override, phối hợp `@Secured`/JSR250, post-check.
- [ ] Nếu có HTTP Controller, test riêng HTTP rules, CSRF và exception mapping; method test không bị thay thế bởi test URL.
- [ ] Đưa context startup và security regression tests vào CI trước khi nâng Spring Security.

### Câu hỏi tự kiểm tra

**Câu 1.** Một method có `@Secured("ROLE_APPROVER")` và `@PreAuthorize("hasAuthority('invoice:approve')")`. Principal chỉ có `ROLE_APPROVER` được phép không?

**Đáp án:** **Không**, nếu cả hai interceptor đang bật. Đây là hai loại annotation cùng áp dụng, nên cần cả role và authority.

**Câu 2.** Class có `@PreAuthorize("hasAuthority('ledger:read')")`, method update có `@PreAuthorize("hasAuthority('ledger:write')")`. User chỉ có quyền write có thể gọi update không?

**Đáp án:** **Có**, nếu lời gọi được intercept và không có kiểm tra độc lập khác: annotation method-level **ghi đè** cùng loại ở class-level. Nếu cần cả read và write, biểu diễn rõ cả hai điều kiện ở method.

**Câu 3.** Có thể đặt `@PreAuthorize("hasRole('ADMIN')")` và `@PreAuthorize("hasAuthority('invoice:delete')")` trên cùng method để được OR không?

**Đáp án:** **Không**. Dùng **một** `@PreAuthorize` với `or`, hoặc `and` nếu cả hai bắt buộc.

**Câu 4.** Một class implements hai interfaces, mỗi interface có `@PreAuthorize` khác nhau trên cùng method. Spring nên lấy interface nào?

**Đáp án:** **Không chọn ngẫu nhiên**; đây là kế thừa mơ hồ có thể khiến application context không khởi động. Đưa một policy được duyệt lên concrete method rồi test.

**Câu 5.** Phương thức chuyển tiền có `@PostAuthorize("hasAuthority('payment:send')")` và bị từ chối, điều đó chứng minh tiền chưa được chuyển chưa?

**Đáp án:** **Không**. Body chạy trước hậu kiểm; đặt điều kiện ở pre-check và bảo đảm transaction/side-effect safety.

## Tài liệu tham khảo chính thức

- Spring Security 6.5, *Method Security*: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0, *Method Security*: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security, *Testing Method Security*: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security, *Spring MVC Authorization / HTTP Rules*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Framework, *Proxying Mechanisms and Self Invocation*: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
