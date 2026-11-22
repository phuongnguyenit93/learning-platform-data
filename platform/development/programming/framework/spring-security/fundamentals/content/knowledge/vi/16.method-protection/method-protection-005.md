# @Secured, @RolesAllowed và lựa chọn theo cấu hình hỗ trợ

## 1. Câu hỏi cốt lõi: Annotation nào thực sự được Spring Security thực thi?

Trong Spring Security, **bảo vệ phương thức (method security)** kiểm tra quyền khi mã gọi một method của bean được Spring quản lý. Điều này bổ sung cho việc bảo vệ HTTP endpoint: service có thể được gọi từ controller, scheduler, consumer hoặc một luồng nghiệp vụ khác, nên chính sách ở tầng method giúp chặn lời gọi không hợp lệ ngay tại ranh giới xử lý.

Có ba cách viết quy tắc thường được gặp:

~~~java
@Secured("ROLE_ADMIN")                     // Spring Security, kiểu legacy
@RolesAllowed("ADMIN")                    // Jakarta/Jakarta Security (JSR-250)
@PreAuthorize("hasRole('ADMIN')")         // Spring Security, SpEL
~~~

**Điểm dễ nhầm nhất:** chỉ viết annotation trên method **chưa đủ**. Ứng dụng phải kích hoạt đúng nhóm method-security interceptor. Với cấu hình hiện đại `@EnableMethodSecurity`:

- `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` được hỗ trợ **theo mặc định** sau khi bật `@EnableMethodSecurity`, trừ khi tắt bằng `prePostEnabled = false`.
- `@Secured` **không được bật mặc định**. Cần `securedEnabled = true`.
- Nhóm JSR-250/Jakarta annotations `@RolesAllowed`, `@PermitAll` và `@DenyAll` **không được bật mặc định**. Cần `jsr250Enabled = true`.
- Dependency Spring Security hoặc Spring Boot Starter Security **không tự bật method security**. Phải kích hoạt `@EnableMethodSecurity` hoặc cấu hình tương đương.

Vì vậy, một method có `@Secured("ROLE_ADMIN")` có thể vẫn chạy **mà không có kiểm tra từ annotation này** nếu ứng dụng chỉ khai báo `@EnableMethodSecurity` mặc định. Những rule khác (chẳng hạn HTTP filter hoặc một annotation khác đã bật) vẫn có thể chặn request, nên cần kiểm thử qua đúng đường gọi để xác định cơ chế nào thực thi.

## 2. So sánh ba nhóm annotation

| Tiêu chí | `@Secured` | `@RolesAllowed` | `@PreAuthorize` |
| --- | --- | --- | --- |
| Nguồn API | Spring Security, `org.springframework.security.access.annotation.Secured` | Jakarta/JSR-250, `jakarta.annotation.security.RolesAllowed` với Spring Boot 3+/Spring Security 6+ | Spring Security, `org.springframework.security.access.prepost.PreAuthorize` |
| Bật bằng | `securedEnabled = true` | `jsr250Enabled = true` | `prePostEnabled = true` (mặc định khi dùng `@EnableMethodSecurity`) |
| Cú pháp điển hình | `@Secured("ROLE_ADMIN")` | `@RolesAllowed("ADMIN")` | `@PreAuthorize("hasRole('ADMIN')")` |
| Kiểu điều kiện | Danh sách authority được yêu cầu; chủ yếu dùng role | Danh sách role theo hợp đồng Jakarta/JSR-250 | Biểu thức SpEL, authority, role, tham số, bean policy |
| Nhiều giá trị | `@Secured({"ROLE_ADMIN", "ROLE_EDITOR"})`: có **ít nhất một** authority phù hợp | `@RolesAllowed({"ADMIN", "EDITOR"})`: có **ít nhất một** role phù hợp | `hasAnyRole`, `and`, `or`, bean/custom policy |
| Kiểm tra chủ sở hữu, tenant, trạng thái đối tượng | Không trực tiếp biểu đạt được trong annotation | Không trực tiếp biểu đạt được trong annotation | Có thể dùng tham số và policy bean, ví dụ `@policy.canRead(authentication, #p0)` |
| Nhóm hỗ trợ | Chỉ `@Secured` | `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` |
| Hướng chọn | Chủ yếu duy trì hệ thống cũ, policy đơn giản | Dùng khi dự án ưu tiên annotation chuẩn Jakarta/JSR-250 | Thường là lựa chọn ưu tiên cho code Spring Security mới |

**Không có phép biến đổi “tự động” giữa các kiểu annotation.** Chuyển từ `@Secured("ROLE_ADMIN")` sang `@RolesAllowed("ADMIN")` phải kèm kiểm tra tiền tố role và cờ cấu hình. Chuyển sang `@PreAuthorize` phải chú ý cú pháp SpEL, phạm vi method và các test truy cập.

Dù `@Secured` thường được gọi là *legacy*, nó vẫn được hỗ trợ nếu chủ động kích hoạt. “Legacy” ở đây nói về định hướng thiết kế: Spring Security hiện khuyến nghị `@PreAuthorize` vì diễn đạt được nhiều chính sách hơn.

## 3. Kích hoạt đúng nhóm annotation bằng @EnableMethodSecurity

Một class cấu hình Java dùng Spring Security hiện đại có thể bật cả ba nhóm:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

Đây là cấu hình **dùng trong dự án Spring/Spring Boot** đã có dependency phù hợp; không phải file Java thuần độc lập chạy trực tiếp bằng `javac`. Với Spring Boot 3+ và Spring Security 6+, JSR-250 annotation dùng package `jakarta.annotation.security`, không dùng import `javax.annotation.security` từ thế hệ Java EE cũ.

Các cấu hình phổ biến:

| Cấu hình | `@PreAuthorize` | `@Secured` | `@RolesAllowed` và JSR-250 |
| --- | --- | --- | --- |
| Chưa bật `@EnableMethodSecurity` | Không có interceptor method-security do annotation này cung cấp | Không | Không |
| `@EnableMethodSecurity` | **Bật** | Tắt | Tắt |
| `@EnableMethodSecurity(securedEnabled = true)` | **Bật** | **Bật** | Tắt |
| `@EnableMethodSecurity(jsr250Enabled = true)` | **Bật** | Tắt | **Bật** |
| `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` | **Bật** | **Bật** | **Bật** |
| `@EnableMethodSecurity(prePostEnabled = false, securedEnabled = true)` | Tắt | **Bật** | Tắt |
| `@EnableMethodSecurity(prePostEnabled = false, jsr250Enabled = true)` | Tắt | Tắt | **Bật** |

Lưu ý hai điều:

1. **Cờ bật annotation là quyết định của toàn application context**, không phải setting đặt riêng cho một service. Khi bật `securedEnabled` trong dự án lớn, những `@Secured` có sẵn trước đó có thể bắt đầu chặn lời gọi ngay lập tức. Hãy kiểm kê và test trước khi triển khai.
2. Không bật cả ba nhóm “cho chắc” nếu không có nhu cầu: mỗi nhóm bổ sung interceptor và semantics cần duy trì. Nên chọn tập annotation mà nhóm phát triển thực sự sử dụng, rồi kiểm soát bằng test.

### Ví dụ lựa chọn cấu hình theo mục đích

**Dự án mới chỉ dùng `@PreAuthorize`:**

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

**Dự án hiện hữu dùng `@Secured`, chưa muốn chuyển tất cả sang SpEL:**

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true, prePostEnabled = false)
class MethodSecurityConfig {
}
~~~

Ở ví dụ thứ hai, `prePostEnabled = false` là lựa chọn **có chủ đích** để chỉ giữ `@Secured`. Nếu vẫn có `@PreAuthorize` cần dùng, không được tắt cờ đó.

**Dự án dùng chuẩn JSR-250 và muốn giữ `@PreAuthorize` cho các ngoại lệ phức tạp:**

~~~java
@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
class MethodSecurityConfig {
}
~~~

`@PreAuthorize` vẫn bật theo mặc định; JSR-250 được bổ sung. Không có yêu cầu phải sử dụng đồng thời `@Secured`.

## 4. Cơ chế: annotation trở thành quyết định authorization bằng cách nào?

Spring Security hiện đại sử dụng các interceptor/`AuthorizationManager` tương ứng với từng nhóm annotation:

| Annotation | Thành phần ra quyết định |
| --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor#preAuthorize` và `PreAuthorizeAuthorizationManager` |
| `@Secured` | `AuthorizationManagerBeforeMethodInterceptor#secured` và `SecuredAuthorizationManager` |
| `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `AuthorizationManagerBeforeMethodInterceptor#jsr250` và `Jsr250AuthorizationManager` |
| `@PostAuthorize` | Interceptor sau khi method chạy, với `PostAuthorizeAuthorizationManager` |

Luồng điển hình của một method có `@Secured("ROLE_ADMIN")` và đã bật `securedEnabled`:

~~~text
Một bean Spring gọi method của bean được bảo vệ qua proxy
    |
    v
Method-security advisor/interceptor nhìn thấy @Secured
    |
    v
Lấy Authentication / GrantedAuthority từ SecurityContext
    |
    v
SecuredAuthorizationManager đánh giá policy ROLE_ADMIN
    |
    +-- Không đủ quyền --> từ chối (không gọi method body)
    |
    +-- Có quyền -------> cho phép chạy method body
~~~

JSR-250 và pre/post cũng được áp dụng qua các interceptor tương ứng. Khi người gọi không có quyền, lời gọi có thể phát sinh `AccessDeniedException`/`AuthorizationDeniedException` tùy phiên bản và đường xử lý. Trong HTTP request, Spring Security có thể chuyển tình huống thành 401/403 theo trạng thái xác thực và exception handling; trong scheduled task hoặc message handler, ứng dụng phải tự xử lý ngoại lệ thích hợp.

**Một method không gắn annotation và không khớp một policy khác thường không được bảo vệ tự động bởi method security.** Để giữ hệ thống fail-closed, hãy thiết kế boundary bảo vệ request, policy nghiệp vụ và test cho các method nhạy cảm, thay vì giả định bật `@EnableMethodSecurity` thì mọi service đều mặc định yêu cầu quyền.

## 5. Role và GrantedAuthority: nơi hay phát sinh lỗi nhất

Trong Spring Security, `Authentication#getAuthorities()` trả các `GrantedAuthority`, thường là chuỗi như `ROLE_ADMIN`, `ROLE_REVIEWER`, `invoice:read`. **Role là một quy ước biểu diễn authority**, thường có tiền tố `ROLE_`; việc có quyền nào phụ thuộc nơi ánh xạ tài khoản/JWT/session thành authorities.

Với **cấu hình tiền tố role mặc định**:

| Annotation/biểu thức | Authority cần có | Giải thích |
| --- | --- | --- |
| `@Secured("ROLE_ADMIN")` | `ROLE_ADMIN` | Khai báo authority theo chuỗi thông dụng của `@Secured` |
| `@Secured("ADMIN")` | `ADMIN` | Không tự suy từ `ADMIN` thành `ROLE_ADMIN` theo cách dùng `@Secured` mặc định |
| `@RolesAllowed("ADMIN")` | `ROLE_ADMIN` | JSR-250 áp dụng tiền tố role mặc định |
| `@RolesAllowed({"ADMIN", "REVIEWER"})` | Một trong `ROLE_ADMIN` hoặc `ROLE_REVIEWER` | Danh sách role có nghĩa OR |
| `@PreAuthorize("hasRole('ADMIN')")` | `ROLE_ADMIN` | `hasRole` dùng tiền tố role mặc định |
| `@PreAuthorize("hasAuthority('ROLE_ADMIN')")` | `ROLE_ADMIN` | So khớp authority chính xác |
| `@PreAuthorize("hasAuthority('invoice:read')")` | `invoice:read` | Permission dạng chuỗi, không tự thêm `ROLE_` |

Đừng hiểu `@RolesAllowed("ADMIN")` là kiểm tra một field `user.role == "ADMIN"` nào đó trong DB; nó kiểm tra `Authentication` đã được Spring Security chuẩn hóa thành granted authorities. Giá trị role của application có thể được lưu là `ADMIN`, nhưng việc ánh xạ thành `ROLE_ADMIN` phải được thiết kế nhất quán.

Tiền tố role **có thể cấu hình khác mặc định**. Nếu dự án đã tùy biến `GrantedAuthorityDefaults`, `RoleHierarchy`, `AuthorizationManager` hoặc mapping authorities, hãy kiểm tra ngữ nghĩa thực của phiên bản đang dùng. Đừng trộn tên role có và không có tiền tố mà không có quy tắc rõ ràng; các loại manager có thể có cơ chế xử lý prefix khác nhau.

### Nhiều role: OR hay AND?

~~~java
@Secured({"ROLE_EDITOR", "ROLE_ADMIN"})
public String edit() { return "ok"; }

@RolesAllowed({"EDITOR", "ADMIN"})
public String review() { return "ok"; }

@PreAuthorize("hasRole('EDITOR') and hasAuthority('document:publish')")
public String publish() { return "ok"; }
~~~

Đây là **ví dụ đoạn method dùng trong Spring**, không phải chương trình Java độc lập. Hai annotation đầu cho phép người dùng có **một trong hai** role/authority được liệt kê. Biểu thức `@PreAuthorize` thứ ba yêu cầu **cả hai điều kiện** vì dùng `and` trong SpEL.

Muốn điều kiện có nhiều quyền khác nhau, ví dụ vừa là manager vừa có `document:publish` và là chủ tài nguyên, dùng `@PreAuthorize` (hoặc policy bean) thay vì cố nhồi ngữ nghĩa AND vào mảng giá trị của `@Secured`/`@RolesAllowed`.

## 6. Ví dụ service áp dụng ba nhóm annotation

Đây là **class minh họa tích hợp trong một ứng dụng Spring** với `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)`. Ứng dụng phải có Spring Security và Jakarta Annotations tương ứng trong classpath. Không chạy ví dụ này riêng bằng `javac` khi chưa có thư viện.

~~~java
import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;

import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Secured("ROLE_ADMIN")
    public String adminSummary() {
        return "Admin summary";
    }

    @RolesAllowed({"ANALYST", "ADMIN"})
    public String analystSummary() {
        return "Analyst summary";
    }

    @PreAuthorize("hasAuthority('report:download')")
    public String downloadReport(String id) {
        return "Report " + id;
    }

    @PermitAll
    public String publicDescription() {
        return "Public report description";
    }

    @DenyAll
    public String retiredExport() {
        return "Should never be returned when JSR-250 is enforced";
    }
}
~~~

Ý nghĩa từng method:

1. `adminSummary` chỉ được gọi khi `@Secured` **đã bật** và principal có authority `ROLE_ADMIN`.
2. `analystSummary` cho principal có `ROLE_ANALYST` hoặc `ROLE_ADMIN`, theo quy ước JSR-250 mặc định, khi `jsr250Enabled` bật.
3. `downloadReport` đòi authority chính xác `report:download`; đoạn minh họa **chưa** kiểm tra quyền trên báo cáo `id` cụ thể. Với dữ liệu thực, phải thêm kiểm tra tenant/owner/ACL phù hợp ở service/policy.
4. `publicDescription` được JSR-250 `@PermitAll` cho phép ở **tầng method**; không đồng nghĩa đường dẫn HTTP gọi tới method này cũng được công khai. HTTP filter có thể yêu cầu đăng nhập trước đó.
5. `retiredExport` bị `@DenyAll` chặn khi JSR-250 được kích hoạt; logic trả chuỗi trong method body không chạy qua lời gọi được Spring proxy bảo vệ.

Nếu `jsr250Enabled = false`, nhóm `@RolesAllowed`, `@PermitAll` và `@DenyAll` không được kích hoạt qua interceptor JSR-250. Điều này đặc biệt nguy hiểm với `@DenyAll`: đoạn code nhìn như đã khóa method nhưng thực tế không được chính annotation đó bảo vệ.

### Kiểm tra ở lớp nào?

- HTTP filter có thể chặn sớm `/reports/admin` theo role; method security vẫn hữu ích khi service được gọi từ nhiều đường vào.
- `@Secured` và `@RolesAllowed` chủ yếu kiểm tra vai trò/quyền tổng quát tại method boundary.
- Quyền **theo bản ghi** như “chỉ chủ báo cáo hoặc thành viên được chia sẻ mới xem ID này” cần kiểm tra đối tượng thật. Dùng `@PreAuthorize` với policy bean hoặc kiểm tra có kiểm soát trong service, và scope repository theo tenant.
- Việc đặt một annotation trên controller không tự bảo vệ những lời gọi service từ scheduler, queue hoặc bean khác. Hãy đặt rule tại ranh giới nghiệp vụ cần bảo vệ.

## 7. Khi nào chọn @Secured, @RolesAllowed hay @PreAuthorize?

Thay vì hỏi annotation nào “mạnh hơn” một cách tuyệt đối, hãy xét **hợp đồng policy**, khả năng cấu hình và định hướng dự án.

| Bối cảnh | Cách chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Codebase Spring Security mới, có quyền chi tiết | `@PreAuthorize` | Hỗ trợ authority/role, SpEL, tham số và delegate policy bean |
| Hệ thống cũ đã dùng nhiều `@Secured` | Giữ `@Secured`, bật `securedEnabled` và lên kế hoạch chuyển đổi nếu cần | Tránh migration ồ ạt; kiểm chứng từng method |
| Codebase ưu tiên Jakarta/JSR-250 chuẩn | `@RolesAllowed` + `jsr250Enabled` | Cú pháp role rõ và quen thuộc với các dự án đa framework |
| Chỉ cần phân quyền đơn giản theo role | `@Secured` hoặc `@RolesAllowed` nếu đã thống nhất | Dễ đọc, ít biểu thức |
| Policy phụ thuộc tham số/owner/tenant/trạng thái | `@PreAuthorize` gọi bean hoặc service policy | Hai annotation role đơn giản không biểu diễn đủ điều kiện |
| Cần từ chối method ở mức Jakarta | `@DenyAll` + `jsr250Enabled` | Chặn rõ ràng khi JSR-250 bật; test xác minh |
| Muốn mở một method công khai | `@PermitAll` (JSR-250) hoặc thiết kế policy tương đương | Chỉ mở tại method boundary, vẫn phải kiểm tra HTTP |
| Cần loại bớt phần tử khỏi collection hoặc kiểm tra kết quả | `@PreFilter`/`@PostFilter`/`@PostAuthorize` theo nhu cầu | Nhóm pre/post hỗ trợ nhưng cần cân nhắc rò rỉ và hiệu năng |

**Khuyến nghị thiết kế:** chọn **một quy ước chính** cho dự án, ví dụ `@PreAuthorize` cho policy mới; giữ `@Secured`/`@RolesAllowed` ở những phần legacy đã được test. Có thể dùng song song, nhưng phải mô tả rõ vì sao và những flag nào được bật.

Không dùng `@PreAuthorize` biểu thức quá dài với nhiều truy vấn DB ngầm trong SpEL. Khi logic đã phức tạp, gọi một bean như `@invoicePolicy.canApprove(authentication, #p0)` giúp code rõ ràng và có thể unit test policy độc lập.

## 8. Trộn nhiều annotation trên một method: không được tự suy ra ưu tiên

Có thể thấy code như:

~~~java
@Secured("ROLE_MANAGER")
@PreAuthorize("hasAuthority('invoice:approve')")
public void approve(String invoiceId) {
    // ...
}
~~~

Nếu cả hai nhóm interceptor được bật, **cả hai quyết định phải cho phép** thì method mới chạy (ngữ nghĩa kết hợp AND đối với các annotation khác loại). Một người có `ROLE_MANAGER` nhưng thiếu `invoice:approve` vẫn bị chặn, và ngược lại.

Các lưu ý quan trọng:

- **Không nên trộn chỉ vì “phòng thủ hai lớp”** khi không giải thích policy: người bảo trì rất dễ quên một điều kiện đang áp dụng.
- **Không lặp cùng một `@PreAuthorize` trên cùng method**. Viết một biểu thức chứa `and`/`or` hoặc chuyển sang policy bean.
- `@PermitAll` trong nhóm JSR-250 **không phải lệnh “bỏ qua mọi annotation khác”**. Nếu `@PreAuthorize` khác cũng áp dụng, nó vẫn có thể từ chối.
- Các annotation có thể đặt trên method, class hoặc interface. Method annotation cùng loại thường có khả năng ghi đè cấu hình ở class; không suy đoán mọi annotation từ cha và con sẽ luôn AND. Với nhiều interface khai báo xung đột, framework có thể không xác định được policy và phải giải quyết tại method cụ thể.
- Những advisor khác nhau có thứ tự chạy khác nhau. Không dùng thứ tự exception/log làm định nghĩa quyền nghiệp vụ; kết quả cuối cùng phải được test.
- Nếu `prePostEnabled = false` mà method vừa có `@Secured` vừa có `@PreAuthorize`, chỉ nhóm thực sự được bật mới quyết định. Không thể khẳng định cả hai bảo vệ được dựa trên nội dung mã nguồn.

**Chọn rõ một policy duy nhất** thường tốt hơn xếp chồng annotation tùy tiện. Với rule phức tạp, policy bean có thể xử lý mọi điều kiện và trả một quyết định có thể giải thích, kiểm thử.

## 9. Các bẫy runtime liên quan đến Spring AOP/proxy

Method Security trong cấu hình thông thường hoạt động nhờ Spring AOP. Vì vậy annotation chỉ có hiệu lực khi lời gọi thực sự đi qua cơ chế advice áp dụng cho bean đó.

### 9.1. Self-invocation

~~~java
@Service
class InvoiceService {

    public void outer() {
        approveInvoice("inv-1"); // this.approveInvoice(...): gọi nội bộ
    }

    @Secured("ROLE_ADMIN")
    public void approveInvoice(String id) {
        // business logic
    }
}
~~~

Đây là **đoạn minh họa cơ chế**, không phải một chương trình chạy độc lập. Khi `outer()` gọi `approveInvoice()` từ cùng instance, lời gọi có thể **không đi qua proxy**, nên `@Secured` không được interceptor kiểm tra ở ranh giới này.

Cách xử lý phù hợp là để bean khác gọi public method qua Spring proxy, tách use case được bảo vệ sang bean riêng, hoặc kiểm tra domain policy rõ trong service. Đừng cố “sửa” bằng cách chỉ thêm `@EnableMethodSecurity(securedEnabled = true)` nếu đường gọi vẫn bypass proxy.

### 9.2. Không phải mọi object đều là Spring bean

- Object tạo bằng `new InvoiceService()` không được Spring quản lý → không có method-security proxy tương ứng.
- Private method/final method hoặc final class trong một số chiến lược proxy có thể không được advice như mong muốn. Kiểm tra proxy mode, kiểu bean, phương thức public và test tích hợp thay vì dựa vào cảm tính.
- Gọi trực tiếp các helper hoặc repository khác có thể bypass method được đánh dấu annotation. Xác định boundary nghiệp vụ mà **mọi entrypoint** đều đi qua.
- Lời gọi bất đồng bộ, background job hoặc consumer thường không có `SecurityContext` của HTTP request; phải xác định service principal và context truyền vào đáng tin cậy, hoặc xử lý theo policy hệ thống được thiết kế riêng.

### 9.3. Mức method và HTTP endpoint là hai lớp độc lập

Một method có `@RolesAllowed("ADMIN")` không có nghĩa controller bên ngoài đã có đúng request authorization hoặc CSRF. Một endpoint HTTP có `hasRole("ADMIN")` cũng không có nghĩa service được bảo vệ khi gọi ngoài HTTP. Thiết kế cả hai lớp theo nhu cầu nghiệp vụ, đặc biệt với dữ liệu theo tenant/ownership.

## 10. Java 17 chạy độc lập: tự kiểm chứng ngữ nghĩa tên authority và tiền tố role

Để quan sát khác biệt giữa **authority đúng chuỗi** của `@Secured` và **role có tiền tố** của `@RolesAllowed` với cấu hình mặc định, chương trình Java thuần sau mô phỏng quy tắc so khớp. Đây là **mô hình học tập**, không sử dụng thư viện Spring và không thay thế interceptor/`AuthorizationManager` thực tế. Nó minh họa riêng ý nghĩa của chuỗi quyền.

Tạo tệp **`MethodRolesDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Set;

public class MethodRolesDemo {
    static boolean secured(Set<String> granted, String... required) {
        return Arrays.stream(required).anyMatch(granted::contains);
    }

    static boolean rolesAllowed(Set<String> granted, String... roles) {
        return Arrays.stream(roles)
                .map(role -> role.startsWith("ROLE_") ? role : "ROLE_" + role)
                .anyMatch(granted::contains);
    }

    static boolean hasAuthority(Set<String> granted, String authority) {
        return granted.contains(authority);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of("ROLE_ADMIN", "invoice:read");
        System.out.println("@Secured ROLE_ADMIN: " + secured(granted, "ROLE_ADMIN"));
        System.out.println("@Secured ADMIN: " + secured(granted, "ADMIN"));
        System.out.println("@RolesAllowed ADMIN: " + rolesAllowed(granted, "ADMIN"));
        System.out.println("@RolesAllowed USER: " + rolesAllowed(granted, "USER"));
        System.out.println("hasAuthority invoice:read: "
                + hasAuthority(granted, "invoice:read"));
        System.out.println("hasAuthority invoice:write: "
                + hasAuthority(granted, "invoice:write"));
    }
}
~~~

Chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 MethodRolesDemo.java
java MethodRolesDemo
~~~

**Stdout chính xác:**

~~~text
@Secured ROLE_ADMIN: true
@Secured ADMIN: false
@RolesAllowed ADMIN: true
@RolesAllowed USER: false
hasAuthority invoice:read: true
hasAuthority invoice:write: false
~~~

Kết quả:

1. Principal có `ROLE_ADMIN` nên trường hợp `@Secured("ROLE_ADMIN")` được mô phỏng là `true`.
2. Chuỗi `ADMIN` không có trong tập authorities nên cách gọi `@Secured("ADMIN")` được mô phỏng là `false`; không tự suy ra tiền tố.
3. Mô hình `@RolesAllowed("ADMIN")` đổi role thành `ROLE_ADMIN` theo tiền tố mặc định nên trả `true`.
4. Principal không có `ROLE_USER` nên `@RolesAllowed("USER")` là `false`.
5. Permission `invoice:read` có chính xác trong tập nên `hasAuthority` tương ứng là `true`; `invoice:write` không có nên `false`.

**Giới hạn ví dụ:** chương trình không quyết định liệu `securedEnabled`, `jsr250Enabled` đang bật, không đọc Spring `Authentication`, không mô phỏng `RoleHierarchy`/prefix tùy biến và không thực thi Spring AOP. Muốn chứng minh một annotation thật hoạt động, cần **test tích hợp với ApplicationContext và Spring Security**.

## 11. Kiểm thử cấu hình hỗ trợ: đừng chỉ nhìn annotation trong source

Giả sử ứng dụng có bean `ReportService` ở phần 6. Để xác nhận cấu hình đúng, kiểm thử **qua bean Spring thực** với principal giả lập, thay vì gọi method trên object tạo thủ công.

Nếu dùng Spring Test, JUnit Jupiter và `spring-security-test`, có thể minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadSecuredReport() {
        assertEquals("Admin summary", service.adminSummary());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadSecuredReport() {
        assertThrows(AccessDeniedException.class, service::adminSummary);
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    void analystCanReadJsr250Report() {
        assertEquals("Analyst summary", service.analystSummary());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadJsr250Report() {
        assertThrows(AccessDeniedException.class, service::analystSummary);
    }
}
~~~

Đoạn test là **mã tích hợp trong project Spring Boot** có cấu hình `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` và service ở trên; cần dependency test thích hợp, không thể chạy chỉ bằng `javac`. `@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN` theo quy ước helper, nên test phù hợp với cách cấp quyền đã mô tả.

Một test có giá trị đặc biệt khi migration là: **trước khi bật cờ mới, annotation cũ không chặn; sau khi bật cờ, cùng lời gọi từ user thiếu quyền phải bị từ chối**. Tuy nhiên không nên cố ý giữ một ca “security vô hiệu” trong test chính của ứng dụng. Có thể xây dựng context thử nghiệm riêng cho việc đối chiếu cờ, và luôn giữ cấu hình sản xuất ở trạng thái an toàn.

### Ma trận kiểm thử đầy đủ

| Cấu hình bật | Method được gọi | Caller | Kết quả mong đợi |
| --- | --- | --- | --- |
| `securedEnabled = true` | `@Secured("ROLE_ADMIN")` | Có `ROLE_ADMIN` | Allow |
| `securedEnabled = true` | `@Secured("ROLE_ADMIN")` | Chỉ `ROLE_USER` | Deny |
| `jsr250Enabled = true` | `@RolesAllowed("ANALYST")` | Có `ROLE_ANALYST` | Allow |
| `jsr250Enabled = true` | `@RolesAllowed("ANALYST")` | Chỉ `ROLE_USER` | Deny |
| `prePostEnabled = true` | `@PreAuthorize("hasAuthority('report:download')")` | Có `report:download` | Allow |
| `prePostEnabled = true` | Method trên | Không có `report:download` | Deny |
| `jsr250Enabled = true` | `@DenyAll` | Admin hoặc user bất kỳ | Deny |
| `jsr250Enabled = true` | `@PermitAll` (không thêm rule khác) | Principal bất kỳ/anonymous phù hợp bối cảnh | Không bị JSR-250 annotation chặn |
| `prePostEnabled = true` và `securedEnabled = true` | Có cả `@PreAuthorize` và `@Secured` | Chỉ đạt một điều kiện | Deny |

Đối với một request đi qua web, mã HTTP có thể còn chịu filter authentication/CSRF và không nhất thiết thể hiện rõ annotation đã từ chối hay chưa. Test trực tiếp lời gọi tới bean bằng `spring-security-test` giúp kiểm chứng method authorization; test `MockMvc` giúp xác minh cả HTTP chain.

Một **regression test quan trọng** là cố tình gọi service từ một bean khác hoặc message handler, vì tình huống này dễ làm lộ phần bảo vệ chỉ tồn tại ở controller. Nếu method truy cập dữ liệu theo tenant, hãy thêm test tenant A vs tenant B, self-invocation và denied path không tạo side effect.

## 12. Migration từ @EnableGlobalMethodSecurity sang @EnableMethodSecurity

Trong ứng dụng đời cũ có thể thấy:

~~~java
@EnableGlobalMethodSecurity(securedEnabled = true)
class LegacySecurityConfig {
}
~~~

Spring Security hiện đại khuyến nghị chuyển sang `@EnableMethodSecurity`. Hai annotation không nhất thiết có **mặc định giống nhau**: `@EnableMethodSecurity` mặc định bật nhóm pre/post. Vì vậy nếu muốn giữ nguyên behavior chỉ bật `@Secured`, cấu hình chuyển đổi có thể là:

~~~java
@EnableMethodSecurity(
    securedEnabled = true,
    prePostEnabled = false
)
class MigratedSecurityConfig {
}
~~~

Nếu trước đây dùng `jsr250Enabled = true`, đặt lại cờ tương ứng trên `@EnableMethodSecurity`. Đừng bỏ sót thay đổi import `javax.annotation.security` → `jakarta.annotation.security` khi nâng cấp lên Spring Security 6+/Spring Boot 3+ và Jakarta EE. Việc di chuyển namespace cần đồng bộ dependencies, compiler và thư viện liên quan, không chỉ thay chuỗi import.

### Trình tự migration an toàn

1. **Kiểm kê annotation đang sử dụng** (`@Secured`, `@RolesAllowed`, `@PermitAll`, `@DenyAll`, `@PreAuthorize`...). Cố định expected decision bằng unit/integration tests.
2. **Ghi lại cấu hình hiện tại**: `securedEnabled`, `jsr250Enabled`, `prePostEnabled`, prefix role, nơi gán `GrantedAuthority`.
3. **Chọn configuration đích** và xác định có giữ nguyên semantics hay cố ý thay policy. Đừng âm thầm thay đổi từ role-or sang role-and.
4. **Nâng cấp API import** phù hợp, xác minh dependency Jakarta cần thiết và cách ánh xạ authority từ token/session/database.
5. **Test trên Spring bean thực**, gồm denied path, class/interface-level annotations, nhiều annotation, self-invocation, scheduler/consumer nếu có.
6. **Triển khai cùng kiểm chứng thời gian chạy**: xác nhận method không được bảo vệ không vô tình trở thành public, và các endpoint nhạy cảm không bị mở quyền do thay flag.

Cấu hình XML cũng có lựa chọn tương đương:

~~~xml
<sec:method-security secured-enabled="true" jsr250-enabled="true" />
~~~

Đoạn XML chỉ minh họa khi ứng dụng thực sự dùng Spring Security XML namespace; với Java configuration, dùng `@EnableMethodSecurity` là đơn giản hơn.

## 13. Lỗi phổ biến và chẩn đoán theo dấu hiệu

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `@Secured` không chặn user thường | Chưa bật `securedEnabled` | Rà `@EnableMethodSecurity` và test denied path |
| `@RolesAllowed` không có hiệu lực | Chưa bật `jsr250Enabled`, import/dependency không phù hợp | Kiểm tra config, package Jakarta và test qua bean |
| `@DenyAll` bị “bỏ qua” | JSR-250 interceptor chưa bật hoặc gọi bỏ qua proxy | Bật `jsr250Enabled`, test direct bean invocation |
| Admin bị từ chối dù tưởng có role | Principal có `ADMIN` thay vì `ROLE_ADMIN` hoặc role mapping sai | Log authorities ở môi trường test an toàn, kiểm tra prefix |
| `@Secured("ADMIN")` không chấp nhận admin | `@Secured` so khớp tên authority được khai báo | Dùng đúng chuỗi authority thực được cấp, thường `ROLE_ADMIN` |
| `@PreAuthorize` không chạy sau migration | `prePostEnabled = false` | Xác minh ý định migration và cờ mới |
| Nhiều annotation gây deny bất ngờ | Các interceptor khác nhau đều áp dụng; điều kiện AND | Viết policy thống nhất và test từng quyền |
| Gọi từ controller bị chặn, gọi nội bộ vẫn chạy | Self-invocation bypass proxy | Tách bean, gọi qua Spring proxy hoặc domain policy |
| HTTP route public dù method có annotation | Endpoint không đi qua protected method/bean hoặc method advice chưa bật | Test luồng HTTP → controller → service |
| Chỉ annotation ở interface, runtime không như mong đợi | Proxy, inheritance, conflict giữa các interface/class | Kiểm tra cách Spring tìm annotation và test implementation thực |
| Job/consumer báo không có `Authentication` | Không có SecurityContext của HTTP | Thiết kế principal/service identity và chính sách cho background |
| Thay đổi dependency làm lỗi import `javax`/`jakarta` | Nâng cấp Jakarta EE chưa đồng bộ | Đồng bộ dependencies, source imports và test |

### Quy trình debug ngắn gọn

1. Xác định **method nào** thực sự đang được gọi, bean và kiểu proxy.
2. Đọc **annotation** trên method/class/interface thực tế, kể cả annotation khác loại có thể cùng áp dụng.
3. Đọc đúng **cờ kích hoạt** trong `@EnableMethodSecurity`. Đừng dựa vào việc thấy Spring Security dependency trong Gradle/Maven.
4. Kiểm tra `Authentication#getAuthorities()` từ principal thử nghiệm và tiền tố role đang dùng.
5. Tạo test với user có quyền và user thiếu quyền; quan sát method body có chạy khi deny hay không.
6. Kiểm tra đường gọi ngoài HTTP, self-invocation, và liệu HTTP filter đã chặn sớm trước khi vào method hay chưa.
7. Sau khi sửa, chạy lại regression test cho nhóm annotation đã bật và các service nhạy cảm.

## 14. Bài tập tự kiểm

**Câu 1.** Ứng dụng chỉ khai báo `@EnableMethodSecurity`. Method có `@Secured("ROLE_ADMIN")`. Annotation này có tự chặn user thiếu role không?

**Đáp án:** Không có bảo đảm từ `@Secured` vì `securedEnabled` mặc định tắt. Những rule bảo vệ khác vẫn có thể từ chối. Bật `@EnableMethodSecurity(securedEnabled = true)` và kiểm thử.

**Câu 2.** Ứng dụng có `@EnableMethodSecurity(jsr250Enabled = true)` và principal có `ROLE_ANALYST`. Method `@RolesAllowed("ANALYST")` có được phép ở lớp JSR-250 không?

**Đáp án:** Có, với tiền tố role mặc định và không có annotation/rule khác chặn.

**Câu 3.** Principal có `ROLE_ADMIN`, method dùng `@Secured("ADMIN")`. Kết quả có tương đương `@RolesAllowed("ADMIN")` không?

**Đáp án:** Không nhất thiết. Với cách kiểm tra authority mặc định, `@Secured("ADMIN")` không tự biến thành `ROLE_ADMIN`; `@RolesAllowed("ADMIN")` dùng quy ước tiền tố role. Luôn đối chiếu authorities thực tế và cấu hình prefix.

**Câu 4.** Có `@Secured("ROLE_ADMIN")` và `@PreAuthorize("hasAuthority('invoice:approve')")` cùng trên method, cả hai interceptor đều bật. Người dùng chỉ có `ROLE_ADMIN` có đủ không?

**Đáp án:** Không. Cần cả role admin và authority `invoice:approve` vì nhiều annotation khác loại phải cùng được thỏa.

**Câu 5.** Một service method dùng `@PermitAll`, nhưng HTTP filter bắt `authenticated()`. Người dùng anonymous gọi endpoint có chắc thành công không?

**Đáp án:** Không. `@PermitAll` tại method không thay đổi rule HTTP; request có thể bị chặn trước khi gọi method.

**Câu 6.** Vì sao test có `@WithMockUser(roles = "ADMIN")` chạy nhưng production dùng JWT lại bị 403?

**Đáp án:** Test helper thường tạo authority `ROLE_ADMIN`, trong khi JWT converter của production có thể tạo `ADMIN`, `SCOPE_admin` hoặc một chuỗi khác. Phải kiểm tra mapping và prefix chính thức của cả hai môi trường; không sửa bằng cách mở quyền bừa bãi.

## 15. Checklist lựa chọn annotation

- [ ] Đã xác định policy là role đơn giản hay phụ thuộc resource/parameter/tenant.
- [ ] Đã chọn nhóm annotation chính của dự án theo yêu cầu thực tế.
- [ ] Đã bật **đúng** `securedEnabled`, `jsr250Enabled` và/hoặc `prePostEnabled`.
- [ ] Đã kiểm tra package `jakarta.annotation.security` và dependency khi dùng JSR-250.
- [ ] Đã thống nhất tiền tố `ROLE_`, tên `GrantedAuthority` và mapping từ token/user store.
- [ ] Không vô tình trộn annotation khiến chính sách AND không được mô tả rõ.
- [ ] Kiểm tra security advice qua Spring bean/proxy, không dùng object tạo thủ công.
- [ ] Đã có test cả **ALLOW** và **DENY**, gồm method bị khóa bằng `@DenyAll` nếu dùng.
- [ ] Đã xem xét HTTP filter, method security và policy trên tài nguyên theo từng đường gọi.
- [ ] Nếu migration, đã kiểm tra thay đổi mặc định của `prePostEnabled`.
- [ ] Không mở endpoint nhạy cảm chỉ vì annotation bị bỏ qua hay role prefix không khớp.

**Ghi nhớ:** `@Secured` là lựa chọn legacy của Spring Security; `@RolesAllowed` thuộc nhóm JSR-250/Jakarta; `@PreAuthorize` linh hoạt hơn với biểu thức quyền. **Spring Security chỉ thực thi annotation khi interceptor tương ứng đã được kích hoạt và lời gọi đi qua boundary được bảo vệ.** Lựa chọn đúng phải đi cùng cờ cấu hình, chuỗi authority/role chính xác và test denied path.

### Tham khảo chính thức

- Spring Security — Method Security (cấu hình, `@Secured`, JSR-250, `@PreAuthorize`, interceptors): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — `@EnableMethodSecurity` Java API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html
- Spring Security — Method Security namespace/flags: https://docs.spring.io/spring-security/reference/servlet/appendix/namespace/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
