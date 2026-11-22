# Phối hợp role, permission và điều kiện dữ liệu trong cùng chính sách

Trong hệ thống thực tế, một **vai trò (role)** hiếm khi trả lời đủ câu hỏi “người này có được xử lý bản ghi này ngay lúc này không?”. Người dùng có thể thuộc nhóm hỗ trợ, có quyền phê duyệt hoàn tiền, nhưng yêu cầu thuộc cửa hàng khác, chưa được phân công hoặc vượt hạn mức phê duyệt của họ. Một chính sách phân quyền chính xác cần kết hợp **role + permission + dữ liệu của tài nguyên + bối cảnh tin cậy**.

Bài này giải thích cách xây dựng một quyết định thống nhất, thể hiện rõ AND/OR, tránh vô tình tạo đường tắt quyền, và áp dụng quyết định ấy trong ứng dụng Spring Security trên servlet stack. Mục tiêu là mô hình kiểm soát truy cập ở cấp nghiệp vụ, không chỉ viết một biểu thức `hasRole`.

## 1. Từng lớp thông tin trả lời câu hỏi khác nhau

| Yếu tố | Ý nghĩa | Ví dụ trong hệ thống hoàn tiền |
| --- | --- | --- |
| **Role** | Người gọi thuộc nhóm/trách nhiệm nào? | `ROLE_SUPPORT`, `ROLE_FINANCE_MANAGER`. |
| **Permission** | Người gọi được thực hiện loại thao tác nào? | `REFUND_READ`, `REFUND_APPROVE`, `REFUND_EXPORT`. |
| **Thuộc tính người gọi** | Người gọi có giới hạn và ngữ cảnh gì? | `tenantId`, mã nhân viên, hạn mức phê duyệt. |
| **Thuộc tính tài nguyên** | Bản ghi cụ thể có dữ liệu gì? | Chủ yêu cầu, người được phân công, trạng thái, số tiền, tenant. |
| **Điều kiện/bối cảnh** | Những ràng buộc chung nào phải đúng? | Đã xác thực, không tự phê duyệt, yêu cầu còn chờ xử lý. |

**Role** thường là cách quản lý nhóm quyền ở cấp tổ chức. **Permission** là đặc quyền cho hành động cụ thể; có thể được cấp qua role hoặc cấp trực tiếp theo chính sách của hệ thống. **Điều kiện dữ liệu** quyết định xem đặc quyền đó áp dụng cho *đối tượng hiện tại* hay không.

Ví dụ, `ROLE_FINANCE_MANAGER` không tự động có nghĩa “được duyệt mọi yêu cầu ở mọi tenant”. Và `REFUND_APPROVE` không tự động có nghĩa “được duyệt yêu cầu bất kể số tiền và trạng thái”.

Trong Spring Security, `Authentication.getAuthorities()` trả về các `GrantedAuthority`; cả role và permission thường được biểu diễn dưới dạng authority chuỗi. Với cấu hình tiền tố mặc định:

- `hasRole("SUPPORT")` tìm authority `ROLE_SUPPORT`.
- `hasAuthority("REFUND_APPROVE")` tìm chính xác authority `REFUND_APPROVE`.
- `hasAnyRole("SUPPORT", "FINANCE_MANAGER")` chấp nhận một trong các role tương ứng.
- Role do ứng dụng ánh xạ thành permission là **quyết định thiết kế**; Spring Security không tự hiểu `ROLE_SUPPORT` phải chứa những permission nghiệp vụ nào.

Không nên xem tên role như bản thân chính sách dữ liệu. Role cho biết nhóm quyền; quyền cho biết thao tác; điều kiện cho biết **khi nào, trên bản ghi nào** thao tác hợp lệ.

## 2. Tình huống xuyên suốt: phê duyệt yêu cầu hoàn tiền

Giả sử có một hệ thống đa cửa hàng (multi-tenant). Nhân viên hỗ trợ và quản lý tài chính đều có thể được cấp `REFUND_APPROVE`, nhưng phạm vi thực thi khác nhau. Để một người phê duyệt yêu cầu, hệ thống đặt ra chính sách minh họa:

1. Người gọi phải **đã xác thực** và có permission `REFUND_APPROVE`.
2. Yêu cầu hoàn tiền phải **cùng tenant** với người gọi.
3. Trạng thái yêu cầu phải là **`PENDING`**.
4. Số tiền hoàn không được vượt quá **hạn mức phê duyệt** của người gọi; hạn mức đến từ cấu hình/dữ liệu máy chủ đáng tin cậy.
5. Người phê duyệt **không được đồng thời là người tạo yêu cầu** (phân tách nhiệm vụ, *separation of duties*).
6. Một trong hai con đường phải đúng: nhân viên có `ROLE_SUPPORT` **và được phân công xử lý yêu cầu**, hoặc có `ROLE_FINANCE_MANAGER` trong cùng tenant.

Có thể viết chính sách dưới dạng logic:

~~~text
ALLOW =
    authenticated
    AND hasPermission(REFUND_APPROVE)
    AND (actor.tenantId == refund.tenantId)
    AND (refund.status == PENDING)
    AND (refund.amount <= actor.approvalLimit)
    AND (actor.id != refund.requesterId)
    AND (
         (hasRole(SUPPORT) AND actor.id == refund.assignedTo)
         OR hasRole(FINANCE_MANAGER)
    )

DENY = mọi trường hợp còn lại
~~~

Dấu ngoặc rất quan trọng. Nếu viết sai thành:

~~~text
(sharedConditions AND assignedSupport) OR financeManager
~~~

thì nhánh `financeManager` có thể **bỏ qua tenant, trạng thái, hạn mức hoặc điều kiện cấm tự duyệt**. Nhánh cho phép quản lý bỏ qua một điều kiện chỉ được tồn tại khi nghiệp vụ quy định ngoại lệ đó *một cách tường minh*. Trong bài này, **mọi role đều phải tuân thủ điều kiện chung**.

Đây là sự kết hợp có chủ đích của ba cách suy nghĩ:

- **RBAC:** chỉ những nhóm role đủ điều kiện mới có đường vào thao tác.
- **Quyền theo thao tác:** `REFUND_APPROVE` khác với `REFUND_READ`; được đọc không suy ra được duyệt.
- **ABAC/ReBAC:** tenant, số tiền, trạng thái là thuộc tính; quan hệ “được phân công xử lý” và “không phải người tạo” gắn người gọi với tài nguyên cụ thể.

## 3. Bảng quyết định: mỗi điều kiện bị thiếu đều phải từ chối

Giả sử `sue` có `ROLE_SUPPORT`, `REFUND_APPROVE`, thuộc `tenant-a`, hạn mức 500; `mia` có `ROLE_FINANCE_MANAGER`, `REFUND_APPROVE`, thuộc `tenant-a`, hạn mức 1.000. Một yêu cầu 300 đang `PENDING`, do `customer-1` tạo và được giao cho `sue`.

| Người gọi và biến thể | Kết quả | Điều kiện quyết định |
| --- | --- | --- |
| Sue duyệt yêu cầu được giao, số tiền 300 | **ALLOW** | Đủ role, permission và mọi điều kiện chung. |
| Sue duyệt yêu cầu giao cho Bob | **DENY** | Role hỗ trợ phải trùng người được phân công. |
| Mia duyệt yêu cầu giao cho Bob, số tiền 300 | **ALLOW** | Nhánh quản lý được phép không cần được phân công; điều kiện chung vẫn đúng. |
| Sue có role hỗ trợ nhưng thiếu `REFUND_APPROVE` | **DENY** | Role đơn lẻ chưa đủ. |
| Người có permission nhưng chỉ mang `ROLE_CUSTOMER` | **DENY** | Không có role thuộc nhánh được phép. |
| Sue duyệt khoản 600 | **DENY** | Vượt hạn mức 500. |
| Sue duyệt yêu cầu của `tenant-b` | **DENY** | Khác tenant. |
| Sue duyệt yêu cầu đã `APPROVED` | **DENY** | Trạng thái không cho phép duyệt lại. |
| Sue duyệt yêu cầu do chính Sue tạo | **DENY** | Vi phạm quy tắc không tự phê duyệt. |
| Người chưa xác thực nhưng dữ liệu quyền mang tên đúng | **DENY** | Thiếu điều kiện xác thực. |

Bảng này cũng giúp chỉ ra **quyền không tự mở rộng phạm vi dữ liệu**. Khi có permission nhưng không có quan hệ/tính chất phù hợp với bản ghi, quyết định vẫn là DENY. Khi không có permission, một role hợp lệ vẫn bị từ chối.

## 4. Ánh xạ role thành permission: khi nào cần kiểm tra cả hai?

Có hai kiểu thiết kế hợp lệ, nhưng chúng thể hiện **hai chính sách khác nhau**.

**Kiểu A — role cấp permission, chính sách kiểm tra permission và dữ liệu.** Chẳng hạn, hệ thống cấp `REFUND_APPROVE` cho nhân viên được ủy quyền, có thể thông qua role hoặc một cơ chế cấp quyền được phê duyệt. Quy tắc còn lại là:

~~~text
authenticated AND REFUND_APPROVE AND dataConditions
~~~

Ở đây, permission là nguồn sự thật cho thao tác. Không bắt buộc kiểm tra `hasRole` lần nữa nếu nghiệp vụ cho phép mọi người đã được cấp permission dùng quyền đó trong phạm vi dữ liệu hợp lệ. Có thể dùng bảng role → permission hoặc `RoleHierarchy` để giảm số biểu thức role dài dòng; phải bảo đảm quyền thực tế được cấp/trình bày đúng trong `Authentication`.

**Kiểu B — nghiệp vụ bắt buộc vừa thuộc nhóm role hợp lệ, vừa có permission.** Ví dụ quy trình phê duyệt chỉ dành cho đội hỗ trợ hoặc quản lý tài chính, dù một tài khoản khác bị cấp nhầm `REFUND_APPROVE`. Khi đó cần giữ cả role và permission trong chính sách:

~~~text
authenticated
AND hasAnyRole(SUPPORT, FINANCE_MANAGER)
AND hasPermission(REFUND_APPROVE)
AND dataConditions
~~~

Bài này chọn **Kiểu B** để minh họa việc phối hợp cả ba lớp. Việc thêm `hasRole` vào quy tắc chỉ vì “cho chắc” có thể gây từ chối ngoài dự kiến khi quyền được cấp hợp lệ cho vai trò mới; ngược lại, lược bỏ role khỏi một chính sách thật sự yêu cầu giới hạn nhóm có thể tạo lỗ hổng. Quyết định phải dựa trên **quy tắc nghiệp vụ đã phê duyệt**.

**Không dùng phép OR tùy tiện:** `hasRole('ADMIN') || hasAuthority('REFUND_APPROVE')` sẽ làm role ADMIN có thể vượt qua yêu cầu permission. Nếu muốn role quản trị có quyền duyệt, hãy định nghĩa rõ role đó cấp `REFUND_APPROVE` trong hệ thống quyền, rồi áp dụng điều kiện dữ liệu bắt buộc. Trong chính sách có ngoại lệ hợp lệ, ghi rõ ngoại lệ ở một nhánh có tên và kiểm thử cả các điều kiện vẫn phải giữ.

## 5. Một hàm chính sách thuần Java 17+ có thể chạy

Ví dụ sau biểu diễn **quyết định cuối cùng**, không phụ thuộc Spring, giúp dễ kiểm tra logic trước khi đưa vào web/service. Các trường trong `Actor` được xem là thông tin **đã xác thực/kiểm chứng ở server**. Nếu tích hợp thật, không được lấy `tenantId`, `roles`, `permissions` hay `approvalLimit` trực tiếp từ body do client tùy ý gửi.

Lưu đúng tên tệp **RefundAuthorizationDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.Set;

public class RefundAuthorizationDemo {
    enum Status { PENDING, APPROVED }

    record Actor(String id, String tenantId, Set<String> roles,
                 Set<String> permissions, BigDecimal approvalLimit,
                 boolean authenticated) {}

    record Refund(String tenantId, String requesterId, String assignedTo,
                  BigDecimal amount, Status status) {}

    static boolean canApprove(Actor actor, Refund refund) {
        if (actor == null || refund == null || !actor.authenticated()) {
            return false;
        }
        if (!actor.tenantId().equals(refund.tenantId())
                || !actor.permissions().contains("REFUND_APPROVE")
                || refund.status() != Status.PENDING
                || refund.amount().compareTo(actor.approvalLimit()) > 0
                || actor.id().equals(refund.requesterId())) {
            return false;
        }
        boolean assignedSupport = actor.roles().contains("ROLE_SUPPORT")
                && actor.id().equals(refund.assignedTo());
        boolean financeManager = actor.roles().contains("ROLE_FINANCE_MANAGER");
        return assignedSupport || financeManager;
    }

    public static void main(String[] args) {
        Actor sue = new Actor("sue", "tenant-a",
                Set.of("ROLE_SUPPORT"), Set.of("REFUND_APPROVE"),
                new BigDecimal("500"), true);
        Actor mia = new Actor("mia", "tenant-a",
                Set.of("ROLE_FINANCE_MANAGER"), Set.of("REFUND_APPROVE"),
                new BigDecimal("1000"), true);
        Actor noPermission = new Actor("ned", "tenant-a",
                Set.of("ROLE_SUPPORT"), Set.of(),
                new BigDecimal("500"), true);
        Actor noEligibleRole = new Actor("lee", "tenant-a",
                Set.of("ROLE_CUSTOMER"), Set.of("REFUND_APPROVE"),
                new BigDecimal("500"), true);
        Actor anonymous = new Actor("guest", "tenant-a",
                Set.of("ROLE_SUPPORT"), Set.of("REFUND_APPROVE"),
                new BigDecimal("500"), false);

        Refund assigned = new Refund("tenant-a", "customer-1", "sue",
                new BigDecimal("300"), Status.PENDING);
        Refund unassigned = new Refund("tenant-a", "customer-1", "bob",
                new BigDecimal("300"), Status.PENDING);
        Refund expensive = new Refund("tenant-a", "customer-1", "sue",
                new BigDecimal("600"), Status.PENDING);
        Refund foreignTenant = new Refund("tenant-b", "customer-1", "sue",
                new BigDecimal("300"), Status.PENDING);
        Refund alreadyApproved = new Refund("tenant-a", "customer-1", "sue",
                new BigDecimal("300"), Status.APPROVED);
        Refund selfApproval = new Refund("tenant-a", "sue", "sue",
                new BigDecimal("300"), Status.PENDING);

        System.out.println("Support assigned: " + canApprove(sue, assigned));
        System.out.println("Support unassigned: " + canApprove(sue, unassigned));
        System.out.println("Manager unassigned: " + canApprove(mia, unassigned));
        System.out.println("Missing permission: " + canApprove(noPermission, assigned));
        System.out.println("Ineligible role: " + canApprove(noEligibleRole, assigned));
        System.out.println("Above limit: " + canApprove(sue, expensive));
        System.out.println("Cross tenant: " + canApprove(sue, foreignTenant));
        System.out.println("Already approved: " + canApprove(sue, alreadyApproved));
        System.out.println("Self approval: " + canApprove(sue, selfApproval));
        System.out.println("Anonymous: " + canApprove(anonymous, assigned));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac RefundAuthorizationDemo.java
java RefundAuthorizationDemo
~~~

Kết quả:

~~~text
Support assigned: true
Support unassigned: false
Manager unassigned: true
Missing permission: false
Ineligible role: false
Above limit: false
Cross tenant: false
Already approved: false
Self approval: false
Anonymous: false
~~~

Quan sát cách chính sách được cấu trúc: hàm loại các yêu cầu vi phạm **điều kiện chung** trước, rồi mới xét hai **nhánh role**. Phép `&&` xác định điều kiện cùng bắt buộc; phép `||` xác định hai con đường được phép **bên trong phạm vi chung**. Nếu thêm một role mới, hãy bổ sung có chủ đích một nhánh phù hợp và ca kiểm thử; đừng bỏ qua các điều kiện cũ.

Ví dụ dùng `BigDecimal.compareTo` thay vì so sánh `double` cho khoản tiền, để tránh lỗi so sánh số thực nhị phân. Mô hình `record` là dữ liệu bất biến theo ví dụ; trong hệ thống thật phải lấy trạng thái và số tiền **hiện hành** từ cơ sở dữ liệu, không dựa vào bản sao do client cung cấp.

## 6. Tích hợp chính sách vào Spring Security: tầng HTTP, method và resource

Một cách triển khai rõ ràng với Spring Boot 3 / Spring Security 6 trên servlet stack là chia trách nhiệm:

| Vị trí | Chặn điều gì? | Không nên kỳ vọng gì? |
| --- | --- | --- |
| **HTTP authorization** | Đường dẫn yêu cầu đăng nhập/quyền cơ bản. | Không biết trạng thái hay người được phân công trong bản ghi nếu chưa tải dữ liệu. |
| **Method security** | Quyền gọi hành động nghiệp vụ, ví dụ role hợp lệ và `REFUND_APPROVE`. | Một biểu thức authority đơn giản chưa đủ để quyết định đối tượng cụ thể. |
| **Domain policy trong service** | Tenant, số tiền, hạn mức, quan hệ phân công, trạng thái, chống tự duyệt. | Không thể tin những thuộc tính client tự khai; phải dùng dữ liệu đáng tin. |

**Cấu hình chặn ở tầng HTTP** — đoạn mã để đặt trong dự án Spring có dependency tương ứng; đây không phải chương trình Java độc lập:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/refunds/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Các import tương ứng gồm `@Configuration`, `@Bean` của Spring Framework; `@EnableMethodSecurity`, `HttpSecurity` và `SecurityFilterChain` của Spring Security. Trong cấu hình trên, `authenticated()` **chỉ là cổng chung**: chưa có điều kiện tenant, owner hay số tiền. Với API có endpoint công khai, cần khai báo riêng trước `anyRequest().denyAll()`. Cấu hình CSRF, xác thực phiên hoặc bearer token cần hoàn thiện theo kiểu ứng dụng; không được suy từ đoạn ví dụ ngắn này.

**Method security** cho phép gắn quy tắc role và permission lên phương thức service:

~~~java
@PreAuthorize("""
    hasAnyRole('SUPPORT', 'FINANCE_MANAGER')
    and hasAuthority('REFUND_APPROVE')
    """)
@Transactional
public void approveRefund(long requestId) {
    ActorContext actor = currentActor.requireAuthenticated();
    RefundEntity refund = repository
            .findByIdAndTenantId(requestId, actor.tenantId())
            .orElseThrow(() -> new EntityNotFoundException("Refund not found"));

    if (!refundPolicy.canApprove(actor, refund)) {
        throw new AccessDeniedException("Refund approval denied");
    }

    refund.approveBy(actor.userId());
}
~~~

Đây là **trích đoạn minh họa trong Spring-managed service**, không phải lớp Java độc lập: `ActorContext`, `currentActor`, `RefundEntity`, `repository` và `refundPolicy` do ứng dụng định nghĩa; các import `@PreAuthorize`, `@Transactional`, `AccessDeniedException` cần bổ sung trong lớp thật. `currentActor` phải tạo từ ngữ cảnh xác thực tin cậy và dữ liệu server; `repository.findByIdAndTenantId` phải lọc theo tenant trong truy vấn. `refundPolicy.canApprove` phải thực thi **toàn bộ chính sách**, kể cả role/permission, để lớp nghiệp vụ giữ được quy tắc nếu được gọi qua một đường khác.

`@EnableMethodSecurity` cần được bật rõ ràng; Spring Boot Starter Security không tự bật method security. `@PreAuthorize` được xử lý qua AOP của Spring: **lời gọi nội bộ giữa hai method trên cùng một instance** thường không đi qua proxy, vì thế đừng dựa duy nhất vào annotation để giữ bất biến quan trọng của nghiệp vụ. Kiểm tra lại trong service/policy giúp không bỏ sót khi đường gọi thay đổi.

**Vì sao tải đối tượng rồi mới quyết định?** Vì nếu chỉ có request ID trong `@PreAuthorize`, ta chưa có đủ dữ liệu đáng tin để xét `PENDING`, assignedTo, số tiền. Có thể gọi một policy bean từ `@PreAuthorize` nếu bean tự tải dữ liệu, nhưng phải xét chi phí truy vấn lặp và nguy cơ dữ liệu đổi giữa lúc kiểm tra với lúc cập nhật. Với thao tác cập nhật, kiểm tra trạng thái và thực hiện thay đổi trong cùng transaction thường dễ kiểm soát hơn.

Trong mẫu trên, người gọi không đủ role/permission bị từ chối trước khi service chạy. Người có quyền chung nhưng vi phạm điều kiện của bản ghi được policy từ chối sau khi tải dữ liệu. Nếu đối tượng ở tenant khác, truy vấn có giới hạn tenant cho kết quả “không tìm thấy”, tránh vô tình tiết lộ bản ghi thuộc tenant khác. Cách chọn phản hồi 403/404 cho trường hợp đó phải được áp dụng nhất quán trong thiết kế API.

## 7. Gộp chính sách mà không tạo lỗ hổng logic

Có thể xem mỗi điều kiện là một predicate `boolean`. Thay vì một biểu thức SpEL dài hàng chục phép toán, hãy gom các nhóm có nghĩa:

~~~text
sharedConditions(actor, refund):
  authenticated && permission && sameTenant && pending
  && withinLimit && noSelfApproval

roleScope(actor, refund):
  (supportRole && assignedToActor) || financeManagerRole

canApprove(actor, refund):
  sharedConditions(actor, refund) && roleScope(actor, refund)
~~~

Những điều cần để ý khi thay đổi chính sách:

- **Mọi đường ALLOW đều phải đi qua ràng buộc chung.** Dùng ngoặc rõ ràng cho `AND` và `OR`, không dựa vào trí nhớ về độ ưu tiên toán tử.
- **Vai trò không phải là quyền vô điều kiện.** Một role có nhiều permission vẫn cần giới hạn tenant, trạng thái và hạn mức.
- **Không cấp quyền bằng tên gọi của client.** Người dùng có thể gửi `role=ADMIN` hoặc `tenantId` giả. Server phải đọc quyền từ identity/session/token đã xác minh và tải đối tượng từ kho dữ liệu.
- **Tránh nhân bản chính sách.** Có thể dùng annotation để chặn sớm, nhưng lõi quyết định dữ liệu nên có một hàm policy tái sử dụng được. Nếu logic ở controller, service và job không đồng bộ, cùng bản ghi có thể nhận kết quả trái nhau.
- **Tránh tăng quyền ngầm qua role mới.** Nếu role mới được phép duyệt, phải xác định rõ permission, phạm vi tài nguyên và giới hạn. Cập nhật bảng quyết định và ca âm tương ứng.
- **Quyền tối thiểu và deny by default.** Không thấy đường ALLOW nào hợp lệ thì từ chối; không mặc định “người đã đăng nhập có thể thao tác”.
- **Không dùng dữ liệu đã cũ để quyết định thao tác cập nhật.** Role/permission có thể bị thu hồi; trạng thái và hạn mức có thể đổi sau khi mở màn hình. Tùy yêu cầu bảo mật, cần cơ chế làm mới quyền và đọc dữ liệu gần thời điểm ghi.

Một cách tiếp cận khác ở lớp framework là phối hợp các `AuthorizationManager` bằng cơ chế thành phần (như `allOf`/`anyOf`) cho các quyết định mà manager có đủ ngữ cảnh. Cơ chế đó hữu ích cho phân quyền chung, nhưng không tự giải quyết bài toán lấy đúng đối tượng và kiểm tra bất biến dữ liệu. Với luật nghiệp vụ phức tạp, một policy service có đầu vào và đầu ra rõ ràng thường dễ đọc, dễ kiểm thử hơn.

## 8. Transaction, thay đổi đồng thời và quyền bị thu hồi

Phân quyền không chỉ đúng ở lúc render nút bấm. Giả sử hai nhân viên gửi yêu cầu duyệt cùng lúc:

1. Cả hai cùng đọc trạng thái `PENDING`.
2. Cả hai cùng vượt qua policy.
3. Nếu không có kiểm soát cập nhật đồng thời, cả hai có thể tạo hiệu ứng phê duyệt/chi trả không mong muốn.

Để giữ bất biến “chỉ duyệt một lần”, kết hợp policy với **transaction**, **optimistic locking** (`@Version`) hoặc **câu lệnh cập nhật có điều kiện** kiểu `WHERE status = 'PENDING'`; kiểm tra số dòng thực sự được thay đổi trước khi phát sinh hiệu ứng tài chính. Việc kiểm tra và cập nhật cần nằm gần nhau về mặt giao dịch. Authorization đúng nhưng thao tác ghi không nguyên tử vẫn chưa đủ an toàn.

Với hệ thống đa tenant, nên giới hạn truy vấn ngay từ kho dữ liệu khi có thể, ví dụ theo `id` **và** `tenantId`, nhất là với truy vấn danh sách. Việc lọc từng bản ghi sau khi đã lấy toàn bộ dữ liệu có thể gây rò rỉ qua response, phân trang, thống kê hoặc cache.

Các authority trong JWT có thể phản ánh quyền tại thời điểm token được phát hành. Nếu hệ thống đòi hỏi **thu hồi quyền gần như tức thời**, token dài hạn chỉ chứa snapshot quyền có thể không đáp ứng; cần cân nhắc token ngắn hạn, tra quyền động hoặc cơ chế thu hồi phiên/token. Quy tắc này độc lập với cú pháp `hasRole` hay `hasAuthority`.

## 9. Kiểm thử đúng tổ hợp role × permission × dữ liệu

Bài kiểm thử tốt nhất không chỉ xác nhận role ADMIN hoặc SUPPORT thành công. Từ bảng chính sách, hãy xây dựng các biến thể kiểm tra từng điều kiện và các kết hợp quan trọng:

| Nhóm kiểm thử | Ca cần có |
| --- | --- |
| **Xác thực** | Chưa đăng nhập, tài khoản bị khóa/không hợp lệ, session hết hạn. |
| **Role** | Role phù hợp, role không phù hợp dù có permission, role mới chưa được chấp thuận. |
| **Permission** | Có quyền duyệt, chỉ có quyền đọc, bị thu hồi quyền. |
| **Tenant** | Đúng tenant, khác tenant, cố sửa tenant ID trong request. |
| **Quan hệ** | Support được giao, support không được giao, quản lý đúng tenant. |
| **Trạng thái** | PENDING, APPROVED, CANCELLED hoặc trạng thái cấm chuyển. |
| **Hạn mức** | Nhỏ hơn, bằng đúng, vượt quá hạn mức; không dùng `double` cho tiền. |
| **Phân tách nhiệm vụ** | Người phê duyệt cũng là người gửi yêu cầu. |
| **Đường gọi** | HTTP, lời gọi service nội bộ, job xử lý nền, endpoint khác dùng cùng nghiệp vụ. |
| **Đồng thời** | Hai yêu cầu duyệt cạnh tranh trên cùng bản ghi; chỉ một cập nhật hợp lệ. |

Có thể chia thành **unit test cho policy thuần** (nhanh, bao phủ mọi nhánh), **integration test service và repository** (kiểm tra tenant, transaction, locking), và **test HTTP/method security** (401/403 hoặc quy ước 404, annotation, mapping authorities). Với Spring Security Test, `@WithMockUser` hỗ trợ kiểm tra role/authority, nhưng vẫn cần fixture bản ghi ở các trạng thái khác nhau; chỉ mock role không chứng minh điều kiện dữ liệu đúng.

Hãy kiểm tra **trường hợp gần đúng nhưng thiếu đúng một điều kiện**: có role nhưng thiếu permission; có permission nhưng khác tenant; đúng tenant nhưng thiếu phân công; mọi thứ đúng nhưng vượt hạn mức. Những ca này phát hiện nhầm lẫn `OR` với `AND` và lỗi bỏ sót dữ liệu tốt hơn chỉ thử đường thành công.

## 10. Các lỗi phổ biến và cách diễn đạt chính sách rõ ràng

1. **Chỉ viết `hasRole('MANAGER')`** rồi cho phép sửa mọi đối tượng. → Bổ sung permission hành động và kiểm tra đối tượng tại tầng nghiệp vụ.
2. **Chỉ viết `hasAuthority('REFUND_APPROVE')`** khi đặc tả còn bắt buộc một nhóm role cụ thể. → Thêm ràng buộc nhóm role *nếu* nghiệp vụ thực sự cần.
3. **`roleA || permissionB && dataCondition` không có ngoặc.** → Viết biểu thức chính sách thành các predicate có tên và kiểm thử cả từng nhánh ALLOW.
4. **Xem `ROLE_ADMIN` là ngoại lệ ngầm cho tenant và trạng thái.** → Chỉ cho phép ngoại lệ được mô tả và kiểm thử rõ ràng.
5. **Tin `ownerId`/`tenantId`/`approvalLimit` gửi từ frontend.** → Lấy identity từ xác thực và dữ liệu quyền/tài nguyên từ máy chủ.
6. **Đặt policy chỉ ở controller.** → Gắn kiểm tra với thao tác nghiệp vụ và tái sử dụng cho các entry point khác.
7. **Chỉ chặn tại `@PreAuthorize`, sau đó cập nhật dữ liệu cũ.** → Đảm bảo kiểm tra điều kiện dữ liệu gần thao tác ghi, có transaction và bảo vệ cạnh tranh.
8. **Chỉ test case ALLOW.** → Mỗi thành phần bắt buộc cần ít nhất một case DENY; kiểm tra thêm ghép nhánh và đồng thời.

Một yêu cầu mơ hồ như “nhân viên tài chính được duyệt hoàn tiền” cần chuyển thành câu kiểm thử được: **“Người dùng đã xác thực, có `REFUND_APPROVE`, thuộc role SUPPORT được phân công hoặc FINANCE_MANAGER, chỉ được duyệt yêu cầu PENDING trong tenant của mình, không vượt hạn mức và không do chính mình tạo.”** Chính sách này cho phép viết bảng quyết định, hàm policy, cấu hình Spring và test mà không suy diễn thêm quyền ngoài đặc tả.

**Điểm ghi nhớ:** role xác định đường quyền theo trách nhiệm, permission xác định hành động, dữ liệu/quan hệ/bối cảnh thu hẹp đối tượng và thời điểm thực thi. Khi phối hợp, hãy đặt **điều kiện chung ở ngoài**, **các con đường role ở trong ngoặc**, bảo vệ quyết định ở server, và mặc định **DENY** khi không thỏa đầy đủ quy tắc.

### Tài liệu tham khảo

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
