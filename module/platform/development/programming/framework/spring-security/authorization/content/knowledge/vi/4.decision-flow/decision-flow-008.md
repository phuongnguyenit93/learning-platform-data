# Interceptor trước, sau phương thức và điểm thực thi chính sách

> **Module:** Spring Security - authorization  
> **Nhóm:** Luồng quyết định  
> **Mục tiêu:** Hiểu chính xác khi nào một lời gọi phương thức bị chặn **trước khi chạy**, khi nào kết quả được kiểm tra **sau khi method chạy**, cơ chế interceptor/`AuthorizationManager` đứng ở đâu, cách kết hợp policy theo dữ liệu nghiệp vụ và cách kiểm thử để không vô tình để side effect xảy ra trước khi từ chối.

## 1. Tại sao một method cần nhiều thời điểm kiểm tra quyền?

Giả sử một hệ thống có method `readReport(42)` và `approvePayment(42)`. Người dùng Alice có authority `report:read` nhưng không được đọc báo cáo thuộc tenant khác. Người dùng Bob có quyền `payment:approve` nhưng không được phê duyệt khoản thanh toán do chính mình lập.

Có ít nhất ba chỗ ứng dụng có thể kiểm tra:

1. **Trước method (pre-invocation):** Alice có `report:read`? Bob có `payment:approve`? Từ đối số ID, tenant và thông tin đáng tin có thể xác định người gọi có quyền vào method không?
2. **Sau method (post-invocation):** Method đọc báo cáo trả về `Report` có `owner` đúng người gọi không? Thông tin này đôi khi chỉ có **sau khi tải bản ghi**.
3. **Bên trong use case/domain (policy enforcement):** Sau khi tải bản ghi trong transaction, kiểm tra tenant, owner, người tạo, trạng thái, hạn mức, khóa nghiệp vụ và các quy tắc cần thiết **trước khi sửa dữ liệu**.

Một kết quả ALLOW tại tầng HTTP hoặc ở pre-interceptor chỉ cho phép đi tiếp đến chặng sau. Nó **không tự động cấp mọi quyền trên đối tượng**. Với các thao tác thay đổi trạng thái, nguyên tắc trọng yếu là:

> Quy tắc phải được kiểm tra **trước side effect mà quy tắc có trách nhiệm bảo vệ**, trong phạm vi dữ liệu nhất quán phù hợp. Một kiểm tra sau khi method hoàn tất không thể đảm bảo rằng mọi side effect được hoàn tác.

## 2. Interceptor trong Spring Security là gì?

Trong Spring Security Servlet, hai nhóm interceptor dễ bị lẫn:

| Lớp | Điểm chặn | Đơn vị cần bảo vệ |
| --- | --- | --- |
| **Servlet filter / `AuthorizationFilter`** | Trước khi HTTP request được xử lý bởi application endpoint | `HttpServletRequest`, path, method, authority |
| **Method-security interceptor** | Bao quanh lời gọi method của Spring-managed bean | Method, đối số, `Authentication`, giá trị trả về |
| **Domain/application policy** | Tại use case/điểm thay đổi trạng thái do ứng dụng thiết kế | Actor, resource, tenant, trạng thái, giao dịch |

`AuthorizationFilter` không phải là “interceptor trước method”: nó tham gia **filter chain của HTTP**. Method-security interceptor hoạt động qua **Spring AOP advisor/proxy** theo cấu hình; cùng một method có thể được gọi từ controller, message consumer hoặc một bean khác.

Method interceptor là một dạng *advice* bao quanh invocation:

```text
Caller
  |
  v
Spring AOP proxy
  |
  +-- BEFORE advice: kiểm tra quyền trước
  |       | DENY -> dừng, không gọi target
  |       v ALLOW
  |
  +-- TARGET METHOD: thực thi thân method
  |       | ném lỗi -> luồng exception
  |       v return value
  |
  +-- AFTER advice: kiểm tra dựa trên return value
          | DENY -> không trả value cho caller như bình thường
          v ALLOW
Caller nhận kết quả
```

Đây là mô hình khái niệm của một method có cả `@PreAuthorize` và `@PostAuthorize`, không phải cam kết rằng mọi advisor khác (`@Transactional`, caching, retry, logging...) đều được chạy đúng vị trí minh họa. Thứ tự advisor thực tế có thể được cấu hình, vì thế không đoán hành vi transaction từ vị trí annotation trong source.

## 3. Bật method security: dependency không đồng nghĩa tự có interception

Trong Spring Security 6.x, `@EnableMethodSecurity` bật hạ tầng method authorization và theo mặc định cung cấp các advisor cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Chỉ thêm Spring Security starter **không tự bật toàn bộ** method-level authorization.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Đây là snippet cấu hình Spring, không phải Java `main` chạy bằng `javac` đơn độc.

Với code cũ có thể thấy `@EnableGlobalMethodSecurity(prePostEnabled = true)`; cấu hình hiện đại ưu tiên `@EnableMethodSecurity` và `AuthorizationManager`. Nếu cần `@Secured` hoặc annotation JSR-250 như `@RolesAllowed`, chúng có lựa chọn bật riêng, ví dụ:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

Không nên thêm mọi loại annotation chỉ vì framework hỗ trợ; chọn một phong cách dễ audit, thường ưu tiên `@PreAuthorize` cho các điều kiện biểu thức và policy tùy biến.

**Điều kiện quan trọng:** advisor phải được áp dụng cho method thật sự qua proxy/AspectJ tương ứng. Một object tự tạo bằng `new` thay vì lấy Spring bean, một lời gọi nội bộ bằng `this`, hoặc method không thể intercept theo cấu hình có thể không được bảo vệ như mong đợi.

## 4. Điểm chặn trước phương thức: @PreAuthorize

Ví dụ:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readSummary(long reportId) {
        return "Summary " + reportId;
    }
}
```

Khi client Spring gọi `reportService.readSummary(42)` **thông qua proxy**:

1. Proxy nhận `MethodInvocation` (method, target, arguments).
2. `AuthorizationManagerBeforeMethodInterceptor` có pointcut phù hợp với `@PreAuthorize`.
3. `PreAuthorizeAuthorizationManager` xử lý biểu thức.
4. `MethodSecurityExpressionHandler` xây evaluation context có `Authentication` và thông tin lời gọi.
5. `hasAuthority('report:read')` kiểm tra tập `GrantedAuthority` của người gọi.
6. **ALLOW:** method thật được chạy.
7. **DENY:** interceptor ném exception từ chối quyền (thường thuộc họ `AccessDeniedException`); thân method không chạy.

Với biểu thức pre-authorization, tham số đã có sẵn:

```java
@PreAuthorize(
    "hasAuthority('report:read') and @reportPolicy.canRead(authentication, #reportId)"
)
public ReportDto readReport(long reportId) {
    return reportRepository.loadDto(reportId);
}
```

`@reportPolicy` là Spring bean ứng dụng phải định nghĩa, còn `#reportId` yêu cầu Spring Security có khả năng phát hiện tên parameter (cấu hình compiler/metadata/annotation phù hợp). Nếu việc bind tên tham số không đáng tin, cần cấu hình build hoặc tên tham số rõ ràng thay vì cho rằng biểu thức chắc chắn lấy được ID.

**Trước method không có return value**. Có thể quyết định từ Authentication, method, arguments và dịch vụ policy, nhưng không thể dựa vào `returnObject` mà method chưa sinh ra. Nếu policy cần tải resource từ database, có thể query từ helper tại đây; tuy nhiên cần cân nhắc tải trùng, thời điểm transaction và race giữa pre-check và update.

## 5. Sau phương thức: @PostAuthorize

`@PostAuthorize` đánh giá **sau khi method trả về thành công**. Nó phù hợp với một số tình huống đọc dữ liệu khi điều kiện quyền phụ thuộc giá trị trả về:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;

    public DocumentQueryService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostAuthorize("returnObject.ownerId == authentication.name")
    public DocumentView read(long id) {
        return repository.getView(id);
    }
}
```

Đoạn trên là **snippet tích hợp**, không phải chương trình standalone: `DocumentRepository`, `DocumentView` và `getView` do ứng dụng định nghĩa. Cần bảo đảm SpEL có thuộc tính `ownerId` thích hợp trên `DocumentView` và principal name được chuẩn hóa cùng loại với owner ID. Với record, getter/custom object, syntax property có thể khác; phải test trên type thật.

Luồng:

1. Proxy nhận lời gọi `read(id)`.
2. Target method **chạy trước**, có thể truy vấn DB và tạo `DocumentView`.
3. `AuthorizationManagerAfterMethodInterceptor` áp dụng pointcut `@PostAuthorize`.
4. `PostAuthorizeAuthorizationManager` đánh giá biểu thức với biến `returnObject`.
5. Nếu owner không khớp, exception được ném; caller không nhận return value như một lời gọi thành công.
6. Nếu khớp, proxy chuyển tiếp kết quả cho caller.

Điều quan trọng: “không trả kết quả cho caller” **không đồng nghĩa** “method chưa chạy”. Truy vấn đã được gửi đi. Log, metric hoặc side effect phát sinh trong thân method có thể đã xuất hiện.

Nếu method ném exception trước khi return, đừng kỳ vọng biểu thức dựa trên `returnObject` sẽ được gọi để hợp thức hóa kết quả. Đối với thao tác ghi, quy tắc bắt buộc cần được thực thi **trước thay đổi**, không dùng post-check như điểm ngăn quyền đầu tiên.

## 6. So sánh thời điểm trước/sau bằng bảng

| Thuộc tính | `@PreAuthorize` | `@PostAuthorize` |
| --- | --- | --- |
| Thời điểm | Trước khi thân method chạy | Sau khi method trả kết quả |
| Dữ liệu có sẵn | Authentication, method, arguments, bean/policy | Authentication, method và `returnObject` |
| Nếu DENY | Target chưa chạy qua invocation này | Target **đã chạy** |
| Dùng để | Chặn thiếu quyền trước thao tác; xét điều kiện từ arguments | Kiểm tra quyền trên result của method đọc |
| Hợp với thao tác ghi? | Có, nếu policy đủ dữ kiện và nhất quán | Không nên làm guard chính |
| Dùng được cho quyền owner? | Có, nếu tải/đưa resource hoặc ID đúng cho policy | Có, khi owner chỉ biết sau read |
| Rủi ro chính | TOCTOU, tải resource lặp, SpEL/parameter binding | Side effect đã xảy ra, data loaded, transaction order |
| Caller nhìn thấy khi deny | Exception/handler tùy ngữ cảnh | Exception/handler tùy ngữ cảnh |

**Quy tắc thiết kế:** với query có hiệu ứng thuần đọc và giá trị trả về cần xét ownership, `@PostAuthorize` có thể hữu ích. Với command như `approvePayment`, `changeOwner`, `deleteDocument` hoặc `sendEmail`, dùng pre-authorization hoặc guard trong use case trước side effect.

## 7. Những class tham gia lúc Spring AOP quyết định

Khi bật `@EnableMethodSecurity`, Spring Security có các interceptor/advisor chuyên trách, thường gặp:

| Annotation | Interceptor / manager tiêu biểu | Thời điểm |
| --- | --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor` → `PreAuthorizeAuthorizationManager` | Trước method |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor` → `PostAuthorizeAuthorizationManager` | Sau method |
| `@PreFilter` | `PreFilterAuthorizationMethodInterceptor` | Lọc đầu vào trước method |
| `@PostFilter` | `PostFilterAuthorizationMethodInterceptor` | Lọc collection trả về sau method |
| `@Secured` (nếu bật) | Before-method interceptor → `SecuredAuthorizationManager` | Trước method |
| JSR-250 (nếu bật) | Before-method interceptor → `Jsr250AuthorizationManager` | Trước method |

Mỗi loại annotation có **pointcut riêng** và interceptor riêng. Từ góc nhìn AOP, lời gọi có nhiều advisor phù hợp sẽ đi qua chúng theo thứ tự tương ứng. Không tự kết luận rằng một annotation trên controller sẽ bảo vệ mọi method cùng tên ở nơi khác; pointcut áp dụng theo bean và type thực tế.

Các loại `AuthorizationManager` có thể nhận `Supplier<Authentication>` để trì hoãn lấy danh tính đến lúc cần. Với pre-method, kiểu đối tượng được bảo vệ thường là `MethodInvocation`; với post-method, Spring Security dùng ngữ cảnh invocation có kết quả (ví dụ `MethodInvocationResult` trong API liên quan). Những chi tiết chữ ký của `authorize`/`check` có thể thay đổi giữa phiên bản; nếu viết manager custom cần dựa vào API đúng bản dependency chứ không sao chép mù quáng snippet cũ.

### Tại sao phân tách interceptor và manager?

**Interceptor** là thành phần thực thi enforcement: bao quanh invocation, gọi manager, tiếp tục hoặc từ chối. **AuthorizationManager** quyết định: dùng Authentication và đối tượng cần bảo vệ để đánh giá. **Policy service** là nơi doanh nghiệp có thể tập trung luật như `canApprove(actor, payment)`.

Phân tách trách nhiệm này giúp thay policy mà không cần tự viết AOP advice, hoặc thay điểm chặn mà không đưa quyền vào từng controller.

## 8. Nhiều annotation trên một method: tổng hợp như thế nào?

Ví dụ một method đọc tài liệu:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView readDocument(long id) {
    return repository.getView(id);
}
```

Cần **cả hai** điều kiện đúng:
- Thiếu `document:read` → bị chặn trước khi load.
- Có `document:read`, nhưng tài liệu thuộc user khác → method load xong, rồi bị từ chối ở post-check.
- Có authority và owner hợp lệ → kết quả được trả bình thường.

Các annotation method-security khác nhau được đánh giá theo chuỗi; về mặt logic cần vượt qua toàn bộ kiểm tra có liên quan. **Không lặp cùng một `@PreAuthorize` hai lần trên cùng method.** Khi cần điều kiện phức tạp, dùng toán tử SpEL `and`/`or` hoặc delegate tới policy bean có method rõ nghĩa và test riêng.

Ví dụ chỉ chấp nhận người có role AUDITOR **và** permission đọc:

```java
@PreAuthorize(
    "hasRole('AUDITOR') and hasAuthority('report:read')"
)
public ReportView exportReport(long id) {
    return repository.getReport(id);
}
```

`hasRole('AUDITOR')` theo mặc định tìm authority `ROLE_AUDITOR`. Còn `hasAuthority('report:read')` so khớp chuỗi đó, không tự suy ra từ role AUDITOR. Nếu đổi prefix mặc định, phải kiểm tra cấu hình thật.

### Cẩn trọng với biểu thức or

```java
// Có thể vô tình bypass check tenant nếu nghĩ ADMIN được đi mọi nơi:
@PreAuthorize(
    "hasRole('ADMIN') or (@tenantPolicy.inTenant(authentication, #id) and hasAuthority('report:read'))"
)
```

Nếu admin cũng phải tuân theo tenant isolation, cần nhóm điều kiện theo cách khác. Mọi nhánh bypass đều là quyết định policy quan trọng, không phải đơn thuần vấn đề viết SpEL.

## 9. Lọc collection: @PreFilter và @PostFilter

Hai annotation này **khác** authorize/deny toàn bộ lời gọi:

- `@PreFilter`: đánh giá từng phần tử của tham số collection được hỗ trợ, giữ phần tử hợp lệ trước khi gọi method.
- `@PostFilter`: đánh giá từng phần tử của collection/kết quả được hỗ trợ sau khi method chạy, chỉ trả phần tử được chấp nhận.
- Trong biểu thức lọc, `filterObject` là phần tử đang được xét; với nhiều tham số filter, có thể cần chỉ rõ tham số mục tiêu.
- Các loại collection/stream/map được hỗ trợ và hành vi biến đổi phụ thuộc API/phiên bản; phải kiểm thử type thực tế. Không mặc nhiên cho rằng mọi `Iterable`, database stream hoặc immutable collection đều được sửa/lọc an toàn.

Ví dụ minh họa trên method query:

```java
@PostFilter("filterObject.ownerId == authentication.name")
public List<DocumentView> findRecentDocuments() {
    return repository.findRecentDocuments();
}
```

Đoạn này chỉ minh họa cú pháp; `DocumentView` và repository là type của ứng dụng. Nó có ba rủi ro:
1. Repository có thể đã tải **cả tài liệu không được phép** vào bộ nhớ ứng dụng trước khi filter.
2. Phân trang thực hiện trước lọc làm số lượng trang và tổng bản ghi bị lệch.
3. Một path khác (export, API download) có thể quên filter, dẫn đến lộ dữ liệu.

Do đó, với danh sách lớn hoặc dữ liệu nhiều tenant, **đưa scope vào database query** (`WHERE tenant_id = ?`, ACL/join visibility) trước khi fetch; dùng `@PostFilter` bổ trợ nếu thực sự phù hợp, không thay thế hàng rào dữ liệu chính.

Với command nhận nhiều ID để xóa, đừng dùng `@PreFilter` rồi coi các phần tử bị lọc im lặng là “xóa thành công một phần” nếu API yêu cầu all-or-nothing. Quy tắc giao dịch và UX cần nêu rõ có cho phép partial success hay phải từ chối toàn bộ batch.

## 10. Điểm thực thi chính sách: trước method, bên trong method hay sau method?

Một hệ thống thực tế thường có ba loại thông tin:

| Thông tin | Có trước lời gọi không? | Điểm kiểm tra hợp lý |
| --- | --- | --- |
| Authority `invoice:approve` của actor | Có nếu Authentication đáng tin | `@PreAuthorize` hoặc HTTP guard |
| ID invoice trong đối số | Có | Pre-check có thể dùng ID, nhưng cần xác thực và query đúng scope |
| Owner/tenant thực của invoice | Có thể phải query DB | Domain policy sau khi nạp tài nguyên; hoặc pre-policy query chuyên biệt |
| Trạng thái `PENDING`/`PAID` hiện tại | Phải đọc dữ liệu nhất quán | Bên trong use case/transaction trước update |
| Kết quả DTO vừa được đọc | Chỉ có sau method | `@PostAuthorize` nếu method không gây side effect |
| Quyền thay đổi ACL hoặc chia sẻ object | Cần kiểm tra tài nguyên/actor | Policy riêng tại use case thay đổi quyền |

Đặt policy dựa trên **phạm vi dữ liệu và thời điểm dữ liệu sẵn có**. Không cần nhồi toàn bộ business policy vào một chuỗi SpEL khó audit. Một thành phần có interface rõ ràng như `InvoiceAuthorizationPolicy.canApprove(actor, invoice)` giúp tập trung và unit-test logic.

Cũng đừng coi `@PreAuthorize` luôn đi trước mở transaction, hoặc `@PostAuthorize` luôn ở trong transaction. `@Transactional` là một AOP advisor khác; cấu hình `@Order` và cơ chế proxy ảnh hưởng quan hệ bao ngoài/bên trong. Khi policy phụ thuộc dữ liệu có thể đổi đồng thời, đặt kiểm tra bắt buộc trong use case có transaction/lock phù hợp.

## 11. Ví dụ ứng dụng: method có quyền tổng quát và luật nghiệp vụ

Giả sử chỉ người có authority `payment:approve` mới có thể tham gia phê duyệt, nhưng để duyệt một payment còn cần:
- Payment thuộc tenant mà actor đang hoạt động.
- Payment ở trạng thái `PENDING`.
- Actor khác người tạo payment (*separation of duties*).
- Số tiền trong hạn mức của actor.
- Chưa có phê duyệt trùng và có version phù hợp.

Một thiết kế service có thể như sau:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApprovalService {
    private final ActorResolver actorResolver;
    private final PaymentRepository payments;
    private final PaymentPolicy policy;

    public PaymentApprovalService(
            ActorResolver actorResolver,
            PaymentRepository payments,
            PaymentPolicy policy) {
        this.actorResolver = actorResolver;
        this.payments = payments;
        this.policy = policy;
    }

    @PreAuthorize("hasAuthority('payment:approve')")
    @Transactional
    public void approve(long paymentId) {
        Actor actor = actorResolver.requireActor();
        Payment payment = payments
            .findPendingForUpdate(paymentId, actor.tenantId())
            .orElseThrow(PaymentNotFoundException::new);

        if (!policy.mayApprove(actor, payment)) {
            throw new AccessDeniedException("Payment approval denied");
        }

        payment.approveBy(actor.id());
    }
}
```

**Lưu ý:** đây là snippet *tích hợp*, không phải file standalone. `Actor`, `ActorResolver`, `PaymentRepository`, `PaymentPolicy`, `Payment`, phương thức `findPendingForUpdate` và exception là type/contract **do ứng dụng định nghĩa**. Tên `findPendingForUpdate` gợi ý truy vấn khóa hoặc version, nhưng cần triển khai đúng với JPA/database thật, không có locking tự phát sinh vì tên method.

Giải thích:
1. Pre-interceptor chặn người không có authority tổng quát; thân method chưa chạy.
2. Trong transaction, actor được nạp từ `Authentication` tin cậy; không nhận `actorId` và `tenantId` do client tự khai như bằng chứng quyền.
3. Repository nạp payment đúng tenant và trạng thái trong transaction theo chiến lược nhất quán.
4. `PaymentPolicy` từ chối trường hợp tự duyệt, quá hạn mức, không có quyền trên object.
5. Chỉ sau đó mới gọi `payment.approveBy` tạo thay đổi.

**Không thay đoạn trên bằng**:

```java
@PostAuthorize("returnObject.approvedBy == authentication.name")
public Payment approve(long paymentId) {
    // Thực thi cập nhật payment và/hoặc gọi external gateway.
    // Chặn sau return là quá muộn để bảo vệ thay đổi.
}
```

Nếu domain đã ghi DB, gửi email hoặc gọi hệ thống thanh toán, deny sau đó không đảm bảo hoàn tác. Transaction rollback có thể xảy ra ở vài cấu hình nhưng không bảo đảm hoàn tác message, network call, file write hoặc side effect ngoài transaction; thứ tự advisor/commit cũng cần xác minh. Vì vậy **write authorization thuộc trước side effect**, không thuộc post-return check.

## 12. Ví dụ Java 17+ chạy độc lập: thấy rõ before và after

Ví dụ thuần Java sau mô phỏng thứ tự interceptor. Không có Spring, AOP, token hay database; đối tượng `Actor` là giả lập **đã do hệ thống xác thực**. Mục đích là quan sát khác biệt giữa “target chưa chạy” và “target đã chạy nhưng không được trả kết quả”.

Lưu dưới tên `MethodBoundaryDemo.java`:

```java
import java.util.Set;

public class MethodBoundaryDemo {
    record Actor(String id, Set<String> authorities) {}
    record Document(String ownerId, String content) {}

    private static int readCalls = 0;
    private static int writeCalls = 0;

    static boolean has(Actor actor, String authority) {
        return actor != null && actor.authorities().contains(authority);
    }

    static String read(Actor actor, Document document) {
        // Giả lập @PreAuthorize("hasAuthority('document:read')")
        if (!has(actor, "document:read")) {
            return "DENY @BEFORE";
        }

        // Target method ĐÃ THỰC THI ở đây.
        readCalls++;
        String loaded = document.content();

        // Giả lập @PostAuthorize: kiểm tra return object.
        if (!document.ownerId().equals(actor.id())) {
            return "DENY @AFTER";
        }
        return "ALLOW " + loaded;
    }

    static String write(Actor actor, Document document) {
        // Quyền chung và policy resource phải được xét TRƯỚC ghi.
        if (!has(actor, "document:write")) {
            return "DENY @BEFORE";
        }
        if (!document.ownerId().equals(actor.id())) {
            return "DENY @POLICY";
        }

        writeCalls++;
        return "ALLOW updated";
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice",
            Set.of("document:read", "document:write"));
        Actor bob = new Actor("bob",
            Set.of("document:read", "document:write"));
        Actor guest = new Actor("guest", Set.of());
        Document doc = new Document("alice", "draft-42");

        System.out.println("Guest read: " + read(guest, doc));
        System.out.println("Bob read: " + read(bob, doc));
        System.out.println("Alice read: " + read(alice, doc));
        System.out.println("Bob write: " + write(bob, doc));
        System.out.println("Alice write: " + write(alice, doc));
        System.out.println("Target reads: " + readCalls);
        System.out.println("Target writes: " + writeCalls);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac MethodBoundaryDemo.java
java MethodBoundaryDemo
```

Kết quả **chính xác**:

```text
Guest read: DENY @BEFORE
Bob read: DENY @AFTER
Alice read: ALLOW draft-42
Bob write: DENY @POLICY
Alice write: ALLOW updated
Target reads: 2
Target writes: 1
```

Diễn giải:
- Guest không có authority đọc: pre-check từ chối **trước** khi tăng `readCalls`.
- Bob có authority đọc nhưng không phải owner: target đã chạy và tăng `readCalls`, rồi post-check từ chối.
- Alice vừa có quyền vừa là owner: trả kết quả thành công.
- Bob có authority ghi nhưng không phải owner: domain policy từ chối **trước** khi tăng `writeCalls`.
- Alice có cả quyền và ownership: được ghi, `writeCalls` tăng.

Đây là **mô phỏng dễ kiểm chứng**, không phải bản thực thi của `PreAuthorizeAuthorizationManager` hoặc `PostAuthorizeAuthorizationManager`. Spring Security sử dụng AOP interceptor, SpEL, authentication và exceptions; trong demo, kết quả biểu diễn bằng chuỗi để thấy thời điểm chặn.

## 13. Điểm chặn còn phụ thuộc người nào đang gọi

Method security không chỉ dùng cho HTTP controller. Các đường gọi có thể gồm:

```text
REST controller --------------+
GraphQL resolver -------------+--> Spring proxy --> Method interceptor --> use case
Message consumer -------------+
Scheduled job ----------------+
Other Spring service bean ----+
```

Lợi ích là có thể tái sử dụng bảo vệ method trên nhiều entry point. Tuy nhiên:

- HTTP controller được bảo vệ bằng `authorizeHttpRequests` không có nghĩa message consumer được bảo vệ.
- Method interceptor chỉ hoạt động với invocation **đúng cơ chế proxy/advisor**.
- Background task có thể không có `SecurityContext` của user tương tác; phải thiết kế service identity hoặc actor theo ủy quyền đáng tin.
- Nếu caller là job hệ thống, phải quyết định cách cấp quyền có giới hạn và audit, không mặc định dùng toàn quyền admin.
- Nếu business policy cần actor cụ thể, giữ ngữ cảnh rõ ràng; tránh fallback “không có user → bỏ qua authorization”.

Trong Servlet, `SecurityContextHolder` mặc định gắn với thread hiện tại. `@Async` hoặc executor khác không tự đảm bảo context đúng; các wrapper `DelegatingSecurityContext...` có thể hỗ trợ truyền context khi phù hợp, đồng thời phải tránh giữ identity quá lâu. Trong WebFlux, dùng cơ chế Reactor `ReactiveSecurityContextHolder` thay vì giả định ThreadLocal từ Servlet.

## 14. Bẫy self-invocation: annotation có nhưng interceptor không chạy

Xem ví dụ:

```java
@Service
class TransferService {
    public void runBatch() {
        // Gọi trên 'this' trong cùng object, có thể bypass proxy.
        transferOne();
    }

    @PreAuthorize("hasAuthority('transfer:execute')")
    public void transferOne() {
        // Thực hiện chuyển tiền.
    }
}
```

Khi Spring AOP dùng proxy, lời gọi từ `runBatch()` tới `this.transferOne()` **không đi qua proxy** theo cách thông dụng. Do đó, không nên coi `@PreAuthorize` trên `transferOne` là chắc chắn đã chạy ở đường này.

Những cách giải quyết tùy thiết kế:

1. Đặt annotation trên **entry point** `runBatch` nếu toàn bộ batch có cùng yêu cầu quyền.
2. Tách `transferOne` sang một Spring bean chuyên trách, inject bean đó vào `runBatch` để lời gọi đi qua proxy.
3. Đặt chính sách bắt buộc trong use case/domain service và gọi tường minh trước mọi side effect.
4. Cân nhắc AspectJ weaving nếu tổ chức thực sự cần interception ở lời gọi nội bộ, với chi phí cấu hình và thử nghiệm tương ứng.

**Đừng chữa bằng cách** gọi `AopContext.currentProxy()` tùy tiện hoặc tự cài proxy lồng nhau mà không đánh giá tính phức tạp; chỉ dùng khi thật sự có yêu cầu và team nắm rõ giới hạn.

Các trường hợp khác phải xác minh: method/private/final, class final, JDK dynamic proxy theo interface, proxy CGLIB, bean tạo thủ công bằng `new`, annotation ở interface/implementation và các biến thể Kotlin (class final mặc định khi chưa mở). Kiểm thử trên cấu hình build thật là bằng chứng tốt hơn suy đoán từ annotation.

## 15. Điều gì xảy ra khi DENY?

Method-security interceptor thông thường ném `AccessDeniedException` hoặc một subclass liên quan khi từ chối. Điều này khác với việc method tự trả `Optional.empty()`, `null` hay một status lỗi nghiệp vụ. Nếu được gọi từ HTTP:

1. Exception đi ngược call stack từ service/controller.
2. Hạ tầng xử lý exception của MVC hoặc filter có thể tham gia tùy cách ứng dụng cấu hình.
3. `ExceptionTranslationFilter` có thể dịch `AccessDeniedException` (hoặc các exception bảo mật liên quan) theo trạng thái authentication.
4. Người đã đăng nhập nhưng thiếu quyền thường nhận `403 Forbidden` qua `AccessDeniedHandler`.
5. Với anonymous/không đủ authentication, `AuthenticationEntryPoint` có thể trả `401 Unauthorized` cho API hoặc redirect tới form login.

Nếu method được gọi từ scheduler, batch job hoặc message consumer **không có HTTP request**, không có `ExceptionTranslationFilter` của servlet đứng ngoài. Caller phải xử lý exception rõ ràng, ví dụ đánh dấu nhiệm vụ thất bại, ghi audit, không retry vô hạn đối với deny cố định.

Một số phiên bản Spring Security hỗ trợ `@HandleAuthorizationDenied`/`MethodAuthorizationDeniedHandler` để cung cấp giá trị dự phòng hoặc mask kết quả khi bị từ chối ở method security. Đó là **chính sách riêng** và không nên dùng để che chặn của command nhạy cảm. Cần kiểm tra API đúng version và xác định rõ fallback có làm rò resource hay không.

**Không đánh đồng mọi lỗi 403 với method security.** CSRF filter, URL authorization, authentication, domain policy hoặc custom exception handler cũng có thể tạo phản hồi tương tự. Luôn tìm **điểm deny đầu tiên**.

## 16. Tương tác với @Transactional và thời điểm commit

`@Transactional` và method-security interceptor đều có thể dùng Spring AOP advisors. Thứ tự các advice và vị trí transaction có thể ảnh hưởng điều gì xảy ra khi post-check ném exception.

Hai minh họa khái niệm:

```text
Trường hợp A: Transaction advice bao bên ngoài post advice
Transaction BEGIN
  -> Method target ghi DB
  -> Post-authorize DENY
Transaction ROLLBACK (khi exception vượt ra và rollback rule áp dụng)
```

```text
Trường hợp B: Post advice bao bên ngoài transaction advice
Transaction BEGIN
  -> Method target ghi DB
Transaction COMMIT
  -> Post-authorize DENY
# DB đã commit, từ chối sau không tự hoàn tác
```

Cả hai chỉ minh họa **tại sao phải kiểm chứng thứ tự**; đừng suy ra hệ thống của bạn thuộc A hay B nếu chưa xác nhận advisor order và transaction semantics. Ngoài ra, ngay cả khi DB rollback, những việc như gửi email, gọi payment gateway, đẩy message hoặc ghi file **không đương nhiên rollback**.

Với transaction-sensitive authorization, các lựa chọn vững hơn:

- Pre-authorize quyền tổng quát trước method.
- Trong transaction, nạp entity theo tenant từ DB.
- Kiểm tra policy resource/điều kiện nghiệp vụ ngay trước lệnh cập nhật.
- Dùng optimistic versioning, pessimistic lock hoặc conditional update khi có race.
- Quản lý outbox/side effect để không phát tín hiệu “đã thành công” trước khi giao dịch hợp lệ hoàn tất.
- Test cạnh tranh concurrent revoke/owner change/status change nếu luật cần hiệu lực ngay.

**Không đặt `@PostAuthorize` trên method chuyển tiền** rồi coi exception sau return là cơ chế bảo vệ thay đổi trạng thái đáng tin.

## 17. Thay đổi dữ liệu giữa kiểm tra và thực thi: TOCTOU

**Time-of-check / time-of-use (TOCTOU)** là khoảng cách giữa việc kiểm tra quyền và sử dụng tài nguyên.

Ví dụ:

```text
T1: PreAuthorize đọc Document 42 và thấy status=DRAFT
T2: Request khác chuyển Document 42 sang LOCKED
T3: Thân method T1 thực hiện update mà không kiểm tra lại
=> Quy tắc "LOCKED không được sửa" có thể bị vi phạm
```

Một pre-check thực hiện ở ngoài transaction của write có thể nhận dữ liệu cũ. Tương tự, owner hoặc membership có thể được thu hồi giữa pre-check và thao tác. Cách xử lý tùy chính sách:
- Sử dụng `UPDATE documents SET ... WHERE id=? AND tenant_id=? AND version=? AND status='DRAFT'`, sau đó kiểm tra số bản ghi bị thay đổi.
- Sử dụng optimistic locking với `@Version` trong JPA.
- Khóa hàng phù hợp và kiểm tra dưới cùng transaction khi cần tính nhất quán cao.
- Thống nhất hợp đồng về thời điểm thu hồi quyền và cache/token: không phải mọi hệ thống đòi hỏi quyền cũ mất hiệu lực tức thì, nhưng yêu cầu phải rõ.

**Transaction không phải một công tắc tự động xóa mọi race condition.** Isolation level, các khóa, thao tác side effect và cách query ảnh hưởng tính đúng. Policy phải dựa trên bản ghi thật, không dùng ID hoặc trạng thái do client tự khẳng định.

## 18. Khi nào dùng policy bean trong @PreAuthorize?

Với rule đơn giản, biểu thức như `hasAuthority('document:read')` rất dễ hiểu. Với rule phức tạp, có thể delegate:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and @invoiceAccess.canApprove(authentication, #invoiceId)"
)
public void approve(long invoiceId) {
    // ...
}
```

Một policy bean như `invoiceAccess` có thể nhận `Authentication`, xác định actor thực, truy vấn dữ liệu và trả boolean. Các lưu ý:

1. **Không nhận quyền từ client:** chỉ dùng authentication đã xác thực và nguồn DB tin cậy.
2. **Không tạo vòng gọi:** nếu policy bean gọi lại method có `@PreAuthorize` trên chính use case, có thể gây vòng lặp/cấu trúc khó lý giải.
3. **Kiểm soát dữ liệu tải:** query theo tenant/ownership để tránh đọc chéo; không tải bí mật rồi vô tình ghi log.
4. **Không phụ thuộc vào mutable global state:** chính sách phải quyết định theo actor/resource/context cụ thể.
5. **Đo chi phí:** một phép authorize có thể kích hoạt SQL, đôi khi nhiều lần nếu có nhiều advisor; xem xét caching đúng phạm vi và cơ chế invalidation.
6. **Quy tắc phải chạy ở đúng thời điểm:** kiểm tra pre giúp chặn sớm nhưng nếu policy phụ thuộc trạng thái có thể đổi nhanh, vẫn cần bảo vệ trong transaction ngay trước write.

Một lựa chọn khác cho hệ thống lớn là implement `AuthorizationManager<MethodInvocation>` riêng hoặc khai báo advisor/pointcut cho nhóm method. Điều này phù hợp khi muốn tách policy khỏi SpEL, nhưng tăng công sức cấu hình và cần test cả điểm chặn lẫn logic decision.

## 19. Tùy biến AuthorizationManager trước và sau method

Spring Security cho phép viết `AuthorizationManager` tùy biến, sau đó gắn qua method interceptor. Lợi ích:
- Dùng Java với cấu trúc rõ ràng thay vì chuỗi SpEL dài.
- Tách rule và logging/audit.
- Tái sử dụng ở một nhóm method hoặc một annotation meta.
- Unit-test policy bằng đầu vào có cấu trúc.

Ở Spring Security 6.5, cấu hình nâng cao có thể tắt pre/post mặc định bằng `@EnableMethodSecurity(prePostEnabled = false)` rồi xuất bản advisor cần thiết, sử dụng factory như `AuthorizationManagerBeforeMethodInterceptor.preAuthorize(manager)` và `AuthorizationManagerAfterMethodInterceptor.postAuthorize(manager)`. Khi tự cấu hình, phải đảm bảo **không vô ý bỏ toàn bộ bảo vệ** của các method đang dựa vào annotation trước đây.

Chỉ minh họa dạng class/contract chứ không cố nhét đầy đủ import vào chương trình standalone:

```java
// Pseudocode Java gần với Spring Security 6.5;
// cần chọn đúng AuthorizationManager<T> và API phiên bản cụ thể.
AuthorizationManager<MethodInvocation> beforeManager = (auth, invocation) -> {
    // Tìm method/arguments, gọi policy và tạo AuthorizationResult.
    // Không lấy quyền từ dữ liệu do client tự khai.
    // MethodInvocation cung cấp tên method, đối số, target.
    return new AuthorizationDecision(/* allowed */ true);
};

// Tạo advisor pre-authorize phù hợp từ manager.
// Cần cấu hình bean và pointcut thực sự trong Spring context.
```

**Đây không phải Java runnable**: `/* allowed */` là vị trí biểu diễn tham số của constructor và phần wiring cần triển khai theo đúng dependency. Đối với hướng dẫn thực hành cơ bản, dùng `@PreAuthorize` và policy bean sẽ an toàn, dễ đọc hơn; custom manager chỉ nên chọn khi có yêu cầu cụ thể về interception/logic.

Ngoài authorization bằng annotation, có thể cấu hình advisor với pointcut AOP bảo vệ nhóm service method. Khi đó, cần kiểm tra phạm vi match tránh chặn nhầm helper hoặc bỏ sót method public nhạy cảm.

## 20. Thứ tự interceptor, @Order và các annotation khác

Mỗi annotation có pointcut/interceptor riêng. Trong Spring Security 6.5, các method-security interceptor có giá trị order riêng (ví dụ `@PreFilter` đứng trước `@PreAuthorize` theo mặc định; tài liệu nêu các thứ tự như 100 và 200). Thứ tự còn tương tác với `@Transactional` và các advisor của framework/ứng dụng.

Các tình huống cần phân biệt:

- **Pre-filter rồi pre-authorize:** dữ liệu đầu vào có thể đã được lọc trước khi biểu thức pre kiểm tra.
- **Pre-authorize rồi thân method:** body không chạy khi pre deny.
- **Post-authorize sau thân method:** có thể bị deny sau một hoạt động đọc/ghi.
- **Post-filter sau khi tạo collection:** list có thể bị lọc trước khi trả về.
- **Transaction/caching/retry:** thứ tự bao trong/bao ngoài của advisor có thể làm thay đổi thời điểm kiểm tra và side effect.

Với yêu cầu thật sự phải điều chỉnh thứ tự, Spring Security cung cấp các điểm cấu hình order (ví dụ `AuthorizationInterceptorsOrder`, thuộc tính `offset` của `@EnableMethodSecurity` ở những phiên bản hỗ trợ). Cần tài liệu đúng version, test thực tế và đánh giá tác động của mọi advisor. **Đừng sửa order chỉ để một test hiện tại pass** nếu chưa hiểu hậu quả bảo mật.

## 21. Interceptor trước/sau và kiểm soát object: tình huống owner

Giả sử Alice và Bob cùng có authority `file:read`, nhưng chỉ Alice sở hữu file số 42.

### Cách A: chỉ @PreAuthorize chung

```java
@PreAuthorize("hasAuthority('file:read')")
public FileContent readFile(long id) {
    return store.load(id);
}
```

**Chưa đủ.** Bob có `file:read` nên cũng qua; nếu service không kiểm tra owner/tenant, Bob có thể đọc file của Alice (IDOR/BOLA).

### Cách B: @PreAuthorize + @PostAuthorize trên read

```java
@PreAuthorize("hasAuthority('file:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public FileDto readFile(long id) {
    return store.loadDto(id);
}
```

Cách này có thể chặn **trả về object** không thuộc quyền. Nhưng `loadDto` đã chạy. Nếu trả file quá lớn, query nhiều resource, hoặc có side effect, hãy cân nhắc lại.

### Cách C: use case chủ động query có scope + policy

```java
@PreAuthorize("hasAuthority('file:read')")
public FileDto readFile(long id) {
    Actor actor = actorResolver.requireActor();
    FileEntity file = store
        .findByIdAndTenantId(id, actor.tenantId())
        .orElseThrow(FileNotFoundException::new);
    policy.assertCanRead(actor, file);
    return mapper.toDto(file);
}
```

Cách C thích hợp hơn nếu muốn **không dựng nội dung nhạy cảm trước khi kiểm tra quyền** và mở rộng sang list/download/export. Có thể dùng cả pre-authorize và policy tại use case; post-authorize vẫn có thể là defense-in-depth cho pure read nhưng không nên dùng để che lỗ hổng query scope.

Trong hệ thống nhiều tenant, `authentication.name` có thể là email hoặc OIDC subject và **không phải** ID owner ở DB. Phải có adapter ánh xạ principal sang actor ID ổn định trước khi so owner.

## 22. Nhiều entry point và đường bypass ít ai để ý

Dùng interceptor ở service có giá trị khi cùng use case được gọi từ nhiều nơi. Nhưng ngoài self-invocation, còn có:

| Đường gọi | Nguy cơ | Biện pháp |
| --- | --- | --- |
| REST controller | HTTP matcher cho phép quá rộng | Method guard và domain policy |
| GraphQL resolver | Không dùng REST matcher | Policy ở application service |
| Message listener | Không có `SecurityContext` của request | Service actor hợp lệ, domain guard |
| Scheduler | Chạy bằng quyền hệ thống không giới hạn | Scope service account và audit |
| Cùng bean gọi `this.securedMethod()` | Bỏ qua proxy | Refactor bean boundary hoặc guard nội bộ |
| Test tạo service bằng `new` | Không có AOP proxy | Integration test Spring bean thật |
| Cache trả giá trị trước advisor bảo vệ | Thứ tự AOP/cache có thể tạo bất ngờ | Kiểm tra order và cache key theo identity |
| Retry bao ngoài command | Có thể lặp side effect/exception | Idempotency và transaction đúng |
| Gọi external API trước khi xét quyền | Side effect đã xảy ra | Policy pre-check trước external call |
| Batch job không phân biệt tenant | Lộ dữ liệu chéo tổ chức | Query scope và per-resource policy |

Tất cả entry point phải đi về một policy hoặc một use case có chốt bảo vệ đáng tin. Nếu một đường gọi yêu cầu bypass (ví dụ migration nội bộ), thiết kế bypass rõ ràng, có authorization/audit riêng, không tự động bypass do thiếu Authentication.

## 23. Kiểm thử interceptor: chứng minh thời điểm thật

**Không chỉ assert một status 403.** Một test có thể pass vì CSRF, URL matcher hoặc ngoại lệ khác, dù `@PreAuthorize` không được chạy. Hãy kiểm chứng **thân method có được gọi không**, **state có thay đổi không**, và **điểm deny nào đúng**.

### Test 1 — PreAuthorize phải chặn trước target

Ở integration test Spring Security Test, tạo principal không có authority, gọi Spring-managed proxy của service:

```java
// Snippet JUnit 5 + Spring Test, cần bean thật và fixtures phù hợp.
@Test
@WithMockUser(authorities = {"report:read"})
void paymentApprovalWithoutAuthorityNeverRunsTarget() {
    assertThatThrownBy(() -> paymentService.approve(42L))
        .isInstanceOf(AccessDeniedException.class);

    verify(paymentRepository, never()).findPendingForUpdate(anyLong(), anyString());
}
```

Nếu method thực sự được gọi qua proxy, pre authorization deny trước khi thân method truy vấn repository. Các import AssertJ/Mockito/JUnit/Test annotations và bean fixtures tùy project; snippet này **không phải standalone**. Nếu service là mock thay vì target bean qua AOP, test có thể không kiểm tra đúng cơ chế.

### Test 2 — PostAuthorize deny sau khi body chạy

Dùng method đọc trả object không thuộc owner, với mock principal có authority đọc hợp lệ:

```java
@Test
@WithMockUser(username = "alice", authorities = {"document:read"})
void postAuthorizeDeniesForeignDocumentAfterRead() {
    when(repository.getView(42L))
        .thenReturn(new DocumentView("bob", "sample"));

    assertThatThrownBy(() -> queryService.read(42L))
        .isInstanceOf(AccessDeniedException.class);

    verify(repository).getView(42L);
}
```

Test này khẳng định target đọc **đã chạy**, nhưng caller bị từ chối. DTO/constructor là fixture ứng dụng định nghĩa.

### Test 3 — Domain policy từ chối trước write

Cố định authority `payment:approve` cho actor, thay creator/tenant/status/limit. Chứng minh:
- Người thiếu quyền object bị deny.
- Payment không chuyển trạng thái khi deny.
- Gateway/email/outbox không được gọi.
- Có quyền hợp lệ thì thay đổi được thực thi đúng một lần.
- Nếu actor bị thu hồi quyền, request mới phản ánh thời điểm thu hồi theo contract.

### Test 4 — Nguy cơ AOP bypass

Tạo bean qua Spring và thử cả gọi trực tiếp từ bean khác lẫn `this.secured()` trong cùng bean. Không giả định behavior từ annotation; xác nhận bằng behavior/test. Nếu test bộc lộ bypass, khắc phục kiến trúc trước khi phát hành.

### Test 5 — Tương tác HTTP, CSRF và transaction

Với MockMvc, cung cấp authentication và CSRF token hợp lệ cho write request có CSRF protection, sau đó kiểm tra sự khác biệt của authority/policy. Xác minh user ẩn danh, thiếu authority, khác tenant, resource không tồn tại và domain conflict trả đúng contract. Nếu cần post-check trên read, test cả response không lộ DTO sau deny.

## 24. Thực hành debug: tìm interceptor đầu tiên từ chối

Khi thấy “đáng lẽ có quyền mà vẫn 403” hoặc “annotation có mà vẫn vào được”, làm lần lượt:

1. **Lời gọi qua HTTP hay ngoài HTTP?** Nếu HTTP, xác định SecurityFilterChain và request authorization có chặn trước không.
2. **Method được gọi qua Spring-managed bean/proxy không?** Kiểm tra self-invocation, method visibility, interface/proxy.
3. **`@EnableMethodSecurity` có bật không?** Phạm vi application context và cấu hình pre/post có như mong đợi không.
4. **Authority thực trong Authentication là gì?** `ROLE_*`, `SCOPE_*` và permission raw string phải khớp chính xác; không log credential/token.
5. **Biểu thức SpEL dùng dữ liệu gì?** `#id` có resolve đúng, `returnObject` có property đúng, bean policy được gọi với actor nào?
6. **Điểm deny ở trước hay sau target?** Bật logging/metrics an toàn hoặc verify mock để xác nhận body đã chạy chưa.
7. **Tương tác AOP khác?** Kiểm tra `@Transactional`, cache, retry và thứ tự advisor thực tế.
8. **Policy dữ liệu?** Owner, tenant, trạng thái, delegation và query scope có đúng database không.
9. **Exception được chuyển thành response ở đâu?** Trong request có handler/controller advice/filter; ngoài request caller tự xử lý.
10. **Test có loại bỏ nhiễu không?** Lỗi do CSRF, validation, token expired hoặc route mismatch không chứng minh method guard.

Có thể bật log Spring Security mức phù hợp trong môi trường phát triển và quan sát sự kiện denial, nhưng không ghi raw access token, password, thông tin principal nhạy cảm hoặc toàn bộ nội dung tài liệu vào log. Audit nên chứa actor ID chuẩn hóa, action, resource ID, điểm từ chối, reason code an toàn và correlation ID theo chính sách hệ thống.

## 25. Các hiểu lầm thường gặp và cách sửa

| Hiểu lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| “Annotation `@PreAuthorize` là Java guard trong thân method” | Gọi bypass proxy có thể không kiểm tra | Hiểu interception và test qua Spring-managed proxy |
| “`@PostAuthorize` kiểm tra trước khi ghi DB” | Có thể ghi/commit rồi mới deny | Guard write trước side effect, trong transaction phù hợp |
| “Có `@EnableMethodSecurity` thì tất cả method đều được bảo vệ” | Method không được match vẫn chạy | Khai báo chính sách ở entry point/use case rõ ràng |
| “Một class có nhiều annotations nghĩa là chọn một trong số đó” | Bỏ sót kiểm tra | Các annotation khác nhau có thể cùng phải pass |
| “Có thể lặp `@PreAuthorize` nhiều lần” | Cấu hình không được hỗ trợ | Kết hợp biểu thức hoặc gọi policy bean |
| “`@PostFilter` giải quyết mọi list security” | Dữ liệu đã load, phân trang sai | Scope query từ DB, filter bổ trợ nếu hợp lý |
| “`@PreFilter` là kiểm tra tất cả phần tử và reject cả batch” | Có thể lọc im lặng, partial processing | Thiết kế all-or-nothing hoặc partial success rõ |
| “Có role ADMIN thì luôn bypass tenant” | Lộ dữ liệu cross-tenant | Chính sách bypass phải được định nghĩa và test |
| “Dùng `#id` sẽ luôn lấy đúng argument” | SpEL có thể không resolve parameter | Cấu hình compiler/metadata, test method thật |
| “Method private/final sẽ được AOP can thiệp như public method” | Annotation có thể không chạy | Xác nhận khả năng proxy/AspectJ và bảo vệ ở boundary |
| “HTTP 403 nghĩa là `@PreAuthorize` hoạt động” | Có thể do CSRF/URL guard | Kiểm tra target không chạy, đối chứng với quyền hợp lệ |
| “Transaction rollback sẽ thu hồi được email đã gửi” | External side effect tồn tại | Kiểm tra quyền trước external call; dùng outbox |
| “Cứ ném 403 là xong” | Job ngoài HTTP xử lý sai retry | Thiết kế handler theo entry point |
| “Thiếu Authentication thì chạy như hệ thống” | Dễ bypass quyền qua job | Dùng service actor có quyền giới hạn và audit |

## 26. Checklist khi đặt điểm thực thi chính sách

Trước khi đưa một method vào production, xác nhận:

1. **Mục đích:** method đọc dữ liệu hay thay đổi trạng thái? Có side effect nào ngoài DB không?
2. **Entrypoint:** REST, GraphQL, job, event, service khác đều đi qua guard nào?
3. **Proxy:** method được gọi qua Spring-managed proxy/AspectJ phù hợp chưa?
4. **Authentication:** actor được xác thực qua nguồn tin cậy, `SecurityContext` có đúng ở thread/task chưa?
5. **Pre-rule:** cần role/authority nào để chặn trước target? SpEL và parameter name có hoạt động thực sự không?
6. **Resource-rule:** owner, tenant, ACL, group, trạng thái và hạn mức nằm ở đâu?
7. **Policy timing:** tất cả luật ảnh hưởng quyền ghi đã được kiểm tra **trước** thay đổi chưa?
8. **Concurrency:** có cần transaction, lock, version hoặc conditional update bảo đảm trạng thái không đổi giữa check/use?
9. **Post-rule:** nếu dùng `@PostAuthorize`, thân method có thuần đọc không? Return object có đúng type/property?
10. **List filtering:** quyền được áp dụng ngay trong DB query hay chỉ sau khi tải dữ liệu?
11. **Advisor order:** transaction, cache, retry, method security có quan hệ thứ tự đã được kiểm chứng không?
12. **Exceptions:** HTTP entry point/denied handler, non-HTTP caller xử lý denial nhất quán chưa?
13. **Test:** có kiểm tra body không chạy khi pre-deny, body chạy khi post-deny, state không đổi sau domain deny?
14. **Observability:** audit ghi nhận actor/action/resource/decision mà không tiết lộ secret không?
15. **Fallback:** anonymous, người mất quyền, token/session cũ và backend ACL/database lỗi được xử lý fail-closed thế nào?

### Tự kiểm tra

**1.** Một method `@PostAuthorize("returnObject.ownerId == authentication.name")` trả về object thuộc Bob khi Alice gọi. Cơ sở dữ liệu đã bị query chưa?  
→ **Có, target đã chạy** để sinh return value. Post-interceptor chỉ quyết định có chuyển tiếp kết quả thành công cho caller hay không.

**2.** Method `approvePayment` có `@PostAuthorize` nhưng không có kiểm tra quyền trước khi gửi email xác nhận. Một request bị deny có đảm bảo email chưa gửi không?  
→ **Không**. Email có thể đã gửi trước post-check; phải kiểm tra quyền trước side effect.

**3.** Một bean gọi `this.secured()`, method `secured` được gắn `@PreAuthorize`. Proxy thông dụng có bảo đảm chặn không?  
→ **Không**. Self-invocation có thể bypass proxy; refactor điểm gọi hoặc đặt guard nội bộ.

**4.** Controller có `hasRole('EDITOR')` và service có `@PreAuthorize("hasAuthority('document:edit')")`. Chỉ có `ROLE_EDITOR` có đủ không?  
→ **Không**, nếu chưa được map thành `document:edit`. Hai điều kiện độc lập theo chuỗi authority.

**5.** Bob có `document:edit` nhưng file ở tenant khác. Nên chặn ở đâu?  
→ Dùng pre-rule chặn thiếu quyền chung, đồng thời kiểm tra tenant/object trong use case/policy từ dữ liệu tin cậy trước thao tác.

**6.** Một batch job không đi qua `AuthorizationFilter` nhưng gọi service qua proxy. Method security có thể chạy không?  
→ **Có**, nếu method được intercept và có security context/actor phù hợp. HTTP filter không tham gia vào đường job.

**7.** Một list trả 50.000 tài liệu rồi `@PostFilter` chỉ còn 15 tài liệu. Đây có phải chiến lược truy vấn an toàn/hiệu quả mặc định không?  
→ **Không**. Dữ liệu bị tải quá rộng, tốn tài nguyên và có thể làm sai phân trang; cần query có scope và kiểm thử.

**8.** `@Transactional` cùng `@PostAuthorize` trên method ghi có bảo đảm rollback khi post-deny không?  
→ **Không nên mặc định**. Advisor order, commit, rollback rule và external side effects ảnh hưởng kết quả. Guard write phải đặt trước side effect.

**Kết luận:** *Before-method interceptor* kiểm tra quyền **trước khi target chạy**; *after-method interceptor* có thể kiểm tra **giá trị trả về sau khi target đã chạy**. `AuthorizationManager` đưa ra quyết định, interceptor cưỡng chế quyết định tại điểm gọi, còn policy nghiệp vụ phải đặt đúng chỗ có actor, object và trạng thái đáng tin. Với command có side effect, hãy kiểm tra quyền trước khi thay đổi dữ liệu; dùng post-authorize chủ yếu cho các tình huống đọc mà kết quả vừa tải mới cung cấp thông tin cần thiết.

## Tài liệu tham khảo

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Spring Security Test: Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html)
