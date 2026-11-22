# Thay đổi chính sách phân quyền và kiểm tra tính nhất quán giữa các lớp

## 1. Vì sao thay đổi chính sách phải được kiểm tra xuyên lớp?

Trong ứng dụng dùng Spring Security, một quyết định “cho phép hay từ chối” có thể đi qua nhiều nơi: gateway hoặc HTTP security filter, controller, method security, service nghiệp vụ, repository, API danh sách, tác vụ nền và thậm chí cache. Khi một quy tắc phân quyền thay đổi, hệ thống phải bảo đảm **mọi đường thực thi liên quan vẫn tuân theo cùng một chính sách nghiệp vụ**. Nếu chỉ sửa một annotation hoặc một URL matcher, một đường khác có thể tiếp tục áp dụng quy tắc cũ.

Ví dụ: chức năng **phê duyệt hóa đơn** trước đây cho phép bất kỳ ai có authority `invoice:approve` phê duyệt. Chính sách mới yêu cầu đồng thời:

- Có quyền `invoice:approve` được cấp từ nguồn tin cậy.
- Người phê duyệt và hóa đơn thuộc cùng tenant.
- Người phê duyệt **không phải người tạo** hóa đơn (*separation of duties*).
- Hóa đơn có trạng thái `PENDING`.
- Giá trị hóa đơn không vượt hạn mức phê duyệt của người đó.

Nếu HTTP filter chỉ kiểm tra authority, điều này vẫn có thể **đúng ở tầng lọc thô**; nhưng service phải thực thi đầy đủ quy tắc mới. Nếu endpoint HTTP đã sửa mà message consumer, batch job hay API nội bộ vẫn duyệt theo quy tắc cũ, hệ thống không nhất quán và có lỗ hổng nghiệp vụ.

**Mục tiêu kiểm tra tính nhất quán** là: với cùng chủ thể, hành động, tài nguyên và ngữ cảnh tin cậy, **mọi đường thực thi có khả năng tạo kết quả nghiệp vụ phải đi tới cùng quyết định cho phép/từ chối**. Không bắt buộc mọi lớp có điều kiện giống hệt nhau: filter có thể chặn sớm theo authority, còn service và dữ liệu chịu trách nhiệm cho điều kiện chi tiết.

## 2. Xác định chính xác “chính sách thay đổi” là gì

Trước khi chạm vào code, định nghĩa chính sách thành một hợp đồng có thể kiểm chứng:

~~~text
decision = authorize(subject, action, resource, context, policyVersion)

subject:     principal đã xác thực, authorities, tenant, thuộc tính tin cậy
action:      hành động nghiệp vụ, ví dụ invoice:approve
resource:    hóa đơn cụ thể với id, tenant, creator, amount, status
context:     hạn mức, quan hệ chủ thể-tài nguyên, thời điểm, workflow
policyVersion: phiên bản quy tắc đang có hiệu lực
decision:    ALLOW hoặc DENY, kèm reason code nội bộ nếu cần
~~~

Dùng **một bảng quyết định** cho thay đổi từ `v1` sang `v2`:

| Tình huống | v1: chỉ có `invoice:approve` | v2: chính sách mới |
| --- | --- | --- |
| Có authority; cùng tenant; người khác tạo; `PENDING`; trong hạn mức | Cho phép | Cho phép |
| Có authority nhưng hóa đơn thuộc tenant khác | Có thể được phép theo v1 (lỗ hổng nếu thiếu kiểm tra tenant) | Từ chối |
| Có authority nhưng tự phê duyệt | Cho phép | Từ chối |
| Có authority nhưng vượt hạn mức | Cho phép | Từ chối |
| Có authority nhưng hóa đơn đã `PAID` | Cho phép nếu v1 không kiểm tra trạng thái | Từ chối |
| Không có authority | Từ chối | Từ chối |

Bảng này là **đặc tả mong đợi** cho toàn bộ thay đổi. Nếu chính sách cũ đã có tenant/status guard thì ghi đúng các điều kiện đó trong tài liệu thay đổi thực tế; ví dụ v1 ở đây được chủ ý đơn giản hóa để làm rõ cách tìm chênh lệch.

Khi rà soát, phải trả lời rõ:

1. **Đối tượng chịu ảnh hưởng**: endpoint, method, sự kiện, export, list/search, admin tool hay tác vụ nền nào có thể thực hiện action?
2. **Dữ liệu quyết định**: authority và tenant lấy ở đâu; creator, status, amount lấy từ bản ghi nào; hạn mức có được xác nhận ở server không?
3. **Quy tắc mới thay gì**: thêm điều kiện, bỏ quyền, mở rộng ngoại lệ, đổi thẩm quyền, đổi phạm vi tenant?
4. **Điều kiện thất bại**: thiếu authentication, thiếu bản ghi, thiếu metadata, cache cũ, lỗi dịch vụ chính sách xử lý thế nào?
5. **Hiệu lực và chuyển tiếp**: chính sách mới có hiệu lực ngay, theo phiên bản cấu hình, hay theo thời điểm nghiệp vụ? Phiên bản cũ được thu hồi ra sao?

Đối với dữ liệu thiếu hoặc không đáng tin, áp dụng nguyên tắc **fail closed**: không suy ra quyền từ một giá trị `null`, từ tham số do client gửi hoặc từ ngoại lệ xử lý chính sách.

## 3. Bản đồ các lớp cần đối chiếu

| Lớp/đường vào | Có thể thực thi điều gì? | Kiểm tra khi đổi policy |
| --- | --- | --- |
| **Gateway / proxy** | Điều hướng, xác thực một phần, giới hạn truy cập | Đường nội bộ/đi thẳng tới service có thể bỏ qua gateway không? Gateway không thay kiểm tra tài nguyên của service |
| **HTTP `SecurityFilterChain`** | Chặn sớm theo route, method, authority qua `authorizeHttpRequests` | Matcher, thứ tự, các HTTP method, các route alias, `denyAll` với route chưa khai báo |
| **Controller** | Nhận ID, gọi use case, trả phản hồi | Không tin `tenantId`/`role`/`userId` do client cung cấp; không có endpoint phụ bỏ qua service |
| **Method security** | `@PreAuthorize`/`@PostAuthorize` trên lời gọi qua Spring proxy | `@EnableMethodSecurity`, đúng method và authority, không phụ thuộc self-invocation |
| **Application/service** | Quyết định nghiệp vụ và side effect | Quy tắc v2 phải được kiểm tra trước khi duyệt/xoá/chuyển tiền/phát sự kiện |
| **Repository / DB** | Tìm, lọc, cập nhật bản ghi, phân trang | Truy vấn list/get/update giới hạn tenant và phạm vi quyền; giao dịch tránh TOCTOU |
| **Queue / scheduler / consumer** | Thực hiện use case mà không đi qua HTTP filter | Xác định principal dịch vụ và gọi cùng domain policy, không mặc định đặc quyền vô hạn |
| **Cache / token / session** | Giữ thông tin quyền, quyết định hoặc dữ liệu | Khi thu hồi/đổi quyền, TTL, invalidation và phiên bản chính sách có làm quyết định cũ sống lâu? |
| **Frontend / BFF** | Ẩn/hiện thao tác, gửi yêu cầu | UI phản ánh rule mới để có UX đúng; backend vẫn là nơi cưỡng chế |
| **Audit / monitoring** | Ghi lại thay đổi và quyết định | Có policy version, action, reason code, correlation ID; không log bí mật/token |

**Không nên đặt cùng một bộ điều kiện dài ở mọi tầng rồi sửa thủ công từng bản.** Một kiến trúc bền vững thường để filter kiểm tra tiền điều kiện thô, còn **domain policy service** là nguồn quyết định có trách nhiệm với resource. Repository bổ sung ràng buộc dữ liệu và tính nguyên tử. Tất cả đường thực thi tạo side effect phải đi qua enforcement tương đương.

## 4. Quy ước một nguồn chính sách có thể tái sử dụng

Giả sử quy tắc mới là:

~~~text
canApprove(actor, invoice) =
    actor authenticated
    AND actor.hasAuthority("invoice:approve")
    AND actor.tenant == invoice.tenant
    AND actor.id != invoice.creator
    AND invoice.status == PENDING
    AND invoice.amount <= actor.approvalLimit
~~~

Phân biệt rõ **nơi chứa chính sách** và **nơi thực thi**:

- **Policy definition**: tiêu chí quyết định của use case `approveInvoice`, có tên, input, outcome, version và test matrix.
- **Policy decision point**: service hoặc bean policy tính `ALLOW/DENY` từ dữ liệu tin cậy. Có thể là component Spring, policy engine hoặc thư viện chung tùy kiến trúc.
- **Policy enforcement point**: filter, service, repository operation, message handler chặn thao tác khi quyết định `DENY`. Những điểm này **phải gọi policy** hoặc áp dụng guard được chứng minh tương đương.
- **Policy information point**: nơi tải actor, role/authorities, quan hệ tài nguyên, tenant, trạng thái; không lấy thuộc tính nhạy cảm từ dữ liệu client tự khai.

Một API chỉ kiểm tra `hasAuthority("invoice:approve")` ở HTTP không nhất thiết sai: đó là **điều kiện cần**. Sai là khi tầng xử lý bên dưới không kiểm tra tenant, separation of duties, state và limit. Ngược lại, nếu service đã chặn hợp lệ thì frontend hiển thị sai nút Approve chỉ là vấn đề UX, nhưng vẫn cần sửa để hành vi dễ hiểu.

### Hợp đồng trách nhiệm khuyến nghị

~~~text
POST /api/invoices/{id}/approve
    |
    v
HTTP SecurityFilterChain
    |-- thiếu invoice:approve ----------> DENY
    |
    v
InvoiceApplicationService.approve(id)
    |-- tải actor tin cậy và invoice --> policy.canApprove(...)
    |-- DENY ---------------------------> không thay đổi DB / không phát event
    |
    v
Transaction + atomic update/row lock
    |-- cập nhật 0 dòng / state đổi ----> từ chối hoặc conflict theo contract
    |
    v
Commit -> publish event theo cơ chế bảo đảm sau commit
~~~

Luồng message consumer dùng cùng `InvoiceApplicationService`, với danh tính service hoặc actor ủy quyền được định nghĩa rõ. Nó không thể dựa vào `SecurityFilterChain` vì không có HTTP request. Khi system principal thực sự được phép bỏ qua một số điều kiện, phải có **chính sách ngoại lệ có tên, phạm vi, audit và test riêng**; không âm thầm dùng `isAdmin` để bỏ qua tenant.

## 5. Ví dụ Java 17 chạy độc lập: cùng một chính sách cho hai đường vào

Đoạn sau là mô hình đơn giản để thấy sự nhất quán giữa đường HTTP và consumer. Đây **không phải** server Spring chạy thực tế: hai hàm `http` và `message` chỉ mô phỏng hai entrypoint, cùng gọi một `ApprovalPolicy` thuần Java. `amount`/`limit` sử dụng số nguyên theo cùng đơn vị giả định để tập trung vào authorization.

Tạo tệp **`PolicyChangeDemo.java`**:

~~~java
import java.util.Set;

record Reviewer(String id, String tenant, Set<String> authorities, int limit) {}
record Invoice(String id, String tenant, String creator, int amount, String status) {}

final class ApprovalPolicy {
    static boolean allow(Reviewer user, Invoice invoice) {
        return user != null && invoice != null
                && user.authorities().contains("invoice:approve")
                && user.tenant().equals(invoice.tenant())
                && !user.id().equals(invoice.creator())
                && invoice.amount() <= user.limit()
                && "PENDING".equals(invoice.status());
    }
}

public class PolicyChangeDemo {
    static boolean http(Reviewer user, Invoice invoice) {
        return ApprovalPolicy.allow(user, invoice);
    }

    static boolean message(Reviewer user, Invoice invoice) {
        return ApprovalPolicy.allow(user, invoice);
    }

    public static void main(String[] args) {
        Reviewer reviewer = new Reviewer("bob", "t1", Set.of("invoice:approve"), 1000);
        Reviewer noPermission = new Reviewer("bob", "t1", Set.of(), 1000);
        Invoice eligible = new Invoice("i1", "t1", "alice", 700, "PENDING");
        Invoice own = new Invoice("i2", "t1", "bob", 700, "PENDING");
        Invoice expensive = new Invoice("i3", "t1", "alice", 1500, "PENDING");
        Invoice otherTenant = new Invoice("i4", "t2", "alice", 700, "PENDING");
        Invoice paid = new Invoice("i5", "t1", "alice", 700, "PAID");

        System.out.println("HTTP eligible: " + http(reviewer, eligible));
        System.out.println("Message eligible: " + message(reviewer, eligible));
        System.out.println("Own invoice: " + http(reviewer, own));
        System.out.println("Over limit: " + http(reviewer, expensive));
        System.out.println("Other tenant: " + message(reviewer, otherTenant));
        System.out.println("Already paid: " + http(reviewer, paid));
        System.out.println("No authority: " + http(noPermission, eligible));
    }
}
~~~

Chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 PolicyChangeDemo.java
java PolicyChangeDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
HTTP eligible: true
Message eligible: true
Own invoice: false
Over limit: false
Other tenant: false
Already paid: false
No authority: false
~~~

Dòng đầu và dòng thứ hai cùng là `true` vì cả hai entrypoint gọi **chính xác cùng logic**. Năm ca còn lại phủ các điều kiện deny: tự duyệt, vượt hạn mức, khác tenant, sai trạng thái và thiếu authority. Nếu ai đó sửa hàm `http` để chỉ kiểm tra authority mà không sửa `message`, test đối chiếu hai đường vào với cùng fixture sẽ phát hiện sai lệch.

Trong ứng dụng thực tế, thông tin `Reviewer` phải được giải ra từ `Authentication` và hệ thống phân quyền đáng tin; `Invoice` phải tải từ repository. Không cho client quyết định `limit`, `tenant`, `creator` hoặc `status`. Nếu policy phụ thuộc thời gian, tổ chức, đơn vị tiền, trạng thái khóa hay quyền được ủy quyền, những thuộc tính đó phải được nạp và kiểm tra đầy đủ.

## 6. Áp dụng vào Spring Security: request rule, method rule và service

### 6.1. HTTP rule chặn thao tác thô

Ví dụ cấu hình **minh hoạ** cho Spring Security Servlet, đặt trong ứng dụng đã cài Spring Web và Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                    .hasAuthority("invoice:approve")
                .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Ý nghĩa: POST phê duyệt phải có authority chính xác `invoice:approve`; mọi request khác bị chặn trong **security chain minh hoạ** này. Ứng dụng thật cần khai báo thêm các endpoint hợp lệ, xác thực/session hoặc Bearer JWT và cấu hình theo stack đã chọn. `@EnableMethodSecurity` cho phép sử dụng method-level annotations. Với ứng dụng dựa vào cookie/session, `POST` vẫn chịu CSRF protection theo cấu hình; đừng tắt CSRF chỉ để thử API.

**Quy tắc thứ tự:** `requestMatchers` cụ thể phải được xét trước `anyRequest`; matcher sai method/path hoặc security chain có thứ tự sai có thể tạo lỗ hổng hay từ chối nhầm. Cần rà cả đường dẫn alias, mapping có version, path variable và controller cho API admin.

### 6.2. Service policy là điểm ra quyết định theo resource

Đoạn sau là **phác thảo tích hợp trong một ứng dụng Spring**, dùng các type do ứng dụng tự định nghĩa (`InvoiceRepository`, `ActorResolver`, `InvoicePolicy`); **không phải chương trình độc lập có thể biên dịch**:

~~~java
@Service
class InvoiceApprovalService {
    private final InvoiceRepository repository;
    private final ActorResolver actorResolver;
    private final InvoicePolicy policy;

    // Constructor injection được lược trong đoạn minh hoạ.
    @Transactional
    @PreAuthorize("hasAuthority('invoice:approve')")
    public void approve(String invoiceId) {
        var actor = actorResolver.currentActor();
        var invoice = repository.findForUpdate(invoiceId)
                .orElseThrow(() -> new InvoiceNotFoundException(invoiceId));

        if (!policy.canApprove(actor, invoice)) {
            throw new AccessDeniedException("Invoice approval denied");
        }

        invoice.approve();
        // Persist trong transaction; publish nghiệp vụ sau commit nếu cần.
    }
}
~~~

Đoạn code chỉ minh hoạ cách đặt kiểm tra: trước thay đổi trạng thái, trong ranh giới transaction có khóa hoặc cơ chế update tương đương. Trong code production cần constructor, imports, implementation repository/policy và cách lấy actor tin cậy. Một lựa chọn khác là `@PreAuthorize("@invoicePolicy.canApprove(authentication, #p0)")` để gọi bean policy theo ID; khi đó policy phải tải dữ liệu tài nguyên. Tuy nhiên **không được cho rằng kiểm tra annotation và ghi DB tự động nguyên tử**: thứ tự AOP advisor/transaction và cập nhật đồng thời vẫn cần được thiết kế rõ.

Những điểm dễ bỏ sót:

- `@PreAuthorize` trên Spring bean thường được thực thi qua proxy. Gọi method cùng bean qua `this.someMethod()` có thể **bỏ qua** security advice của proxy.
- `@EnableMethodSecurity` phải được bật cho method security; annotation đặt trên object tự tạo bằng `new` không được Spring quản lý sẽ không cho hiệu lực mong muốn.
- `hasRole("APPROVER")` theo quy ước mặc định kiểm tra authority `ROLE_APPROVER`; `hasAuthority("invoice:approve")` so khớp đúng chuỗi. Khi thay đổi mapping role → permission, xem xét cả nơi cấp `GrantedAuthority`.
- `@PostAuthorize` hoặc lọc dữ liệu sau truy vấn không thích hợp để bảo vệ thao tác đã ghi dữ liệu/phát event; dùng kiểm tra **trước** side effect.
- Nếu consumer hoặc scheduler gọi service mà không có `SecurityContext` của HTTP, cần định nghĩa actor của tác vụ đó, quyền được cấp và cách gọi policy. Không “giả mạo” actor người dùng theo event field chưa xác minh.

Một HTTP request bị chặn ở filter có thể trả 403 sớm; request qua filter nhưng bị policy nghiệp vụ từ chối cũng phải dừng thao tác. **Hai điểm từ chối không cần chung exception class**, miễn quyết định nghiệp vụ và side effect nhất quán, đồng thời API contract được chuẩn hóa.

## 7. Repository và transaction: nhất quán nghĩa là dữ liệu cũng được bảo vệ

### 7.1. Đọc một bản ghi và đọc danh sách

Đổi policy từ “có authority là đọc” sang “chỉ đọc hóa đơn cùng tenant” đòi hỏi cả hai hình thức:

~~~sql
-- Truy vấn một hóa đơn (minh họa).
SELECT id, tenant_id, created_by, amount, status
FROM invoices
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId;
~~~

~~~sql
-- Truy vấn danh sách: scope phải áp dụng trước LIMIT/OFFSET.
SELECT id, tenant_id, created_by, amount, status
FROM invoices
WHERE tenant_id = :trustedTenantId
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

`:trustedTenantId` phải xuất phát từ danh tính được xác thực hoặc dịch vụ xác định tenant đáng tin, **không phải** giá trị client có thể tùy ý đặt. Nếu quyền xem còn phụ thuộc membership/ownership, thêm điều kiện đó vào truy vấn theo mô hình domain thực tế; không lấy mọi bản ghi rồi lọc trên UI hay lọc sau pagination. Các endpoint `count`, search, export, báo cáo tổng hợp và quan hệ join cũng phải tôn trọng cùng phạm vi dữ liệu; nếu không, người dùng có thể thấy số lượng, metadata hoặc trang dữ liệu ngoài quyền.

### 7.2. Ghi dữ liệu và race condition

Một kiểm tra `invoice.status == PENDING` trước khi ghi chưa đủ nếu transaction khác đã duyệt hóa đơn sau thời điểm kiểm tra. Để giữ invariant, có thể khóa bản ghi phù hợp, hoặc dùng **conditional update nguyên tử**:

~~~sql
-- Phác thảo SQL; tham số nhận từ policy context đáng tin.
UPDATE invoices
SET status = 'APPROVED'
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId
  AND created_by <> :trustedActorId
  AND status = 'PENDING'
  AND amount <= :trustedApprovalLimit;
~~~

Trước lệnh này, tầng service vẫn phải xác thực authority `invoice:approve`, xác định actor hợp lệ và bảo đảm policy áp dụng đúng trên hóa đơn. Sau lệnh, kiểm tra **số hàng bị ảnh hưởng**: bằng `1` mới là cập nhật thành công; bằng `0` cần xử lý theo API contract (không tồn tại, hết quyền, conflict trạng thái...) và **không phát sự kiện phê duyệt thành công**. Hệ thống dùng event/outbox cần bảo đảm side effect chỉ diễn ra khi transaction commit.

**Có thể có nhiều hiện thân kỹ thuật của cùng invariant** (domain policy và điều kiện SQL bắt buộc để chống đua trạng thái). Đây không phải lý do bỏ một trong hai; thay vào đó, đặt tên cùng quy tắc trong đặc tả và kiểm thử chúng đồng bộ. Khi thay điều kiện như `amount <= limit` thành approval-tier phức tạp hơn, cập nhật cả domain policy lẫn guard cập nhật dữ liệu hoặc dùng một cơ chế transaction khác bảo đảm cùng ngữ nghĩa.

### 7.3. Phân biệt DENY với NOT_FOUND và CONFLICT

Việc trả về `403 Forbidden`, `404 Not Found` hay `409 Conflict` phụ thuộc API contract, chiến lược hạn chế lộ tồn tại tài nguyên và nguyên nhân thất bại. Hệ thống có thể cố ý trả 404 khi người dùng không được biết tài nguyên tồn tại. Dù mã HTTP khác nhau, kết quả bắt buộc là **không lộ nội dung/không ghi thay đổi khi policy từ chối**. Nếu chưa đăng nhập, một API Bearer thường dùng 401; 403 phù hợp khi đã xác thực nhưng không đủ quyền. Đừng viết test chỉ dựa trên status mà bỏ qua dữ liệu/side effect.

## 8. Các đường thực thi ngoài HTTP và hệ quả khi thay policy

Không phải mọi action đều khởi đầu từ controller:

- **Message consumer**: nhận `invoiceId` từ queue. ID chỉ định tài nguyên; không phải bằng chứng người phát event được phép duyệt. Consumer phải kiểm tra service actor/ủy quyền, policy và trạng thái tài nguyên hiện tại.
- **Scheduled job**: chạy theo lịch có thể thao tác nhiều tenant. Cần định nghĩa account dịch vụ, scope tenant, loại action và policy ngoại lệ nếu có; không gán mặc định đặc quyền toàn cục chỉ vì “chạy nội bộ”.
- **GraphQL/gRPC/internal REST**: cùng nghiệp vụ có thể được gọi bằng giao thức khác. Đừng dựa vào matcher HTTP duy nhất nếu service có nhiều entrypoint.
- **Import/bulk operation**: mỗi dòng có thể có chủ sở hữu/tenant khác nhau. Một lần kiểm tra quyền tổng quát trước batch không thay việc kiểm tra scope của từng resource.
- **UI/BFF**: disable hoặc ẩn nút Approve theo policy mới để tránh thao tác thất bại khó hiểu, nhưng người dùng vẫn có thể gọi API trực tiếp. UI luôn chỉ là tiện ích trình bày.
- **Dữ liệu được cache hoặc search index**: một bản sao cũ có thể trả dữ liệu bị thu hồi quyền; cần kiểm tra authorization tại điểm trả kết quả hoặc giới hạn cache theo quyền/tenant có thể được chứng minh.

Một bài kiểm thử quan trọng là **cùng actor và invoice, gọi use case bằng ít nhất hai entrypoint**. Kết quả nghiệp vụ phải giống nhau, kể cả khi HTTP có chặn sớm bằng 403 còn tác vụ nền báo một lỗi nghiệp vụ khác. Đặc biệt kiểm tra rằng đường bị deny **không cập nhật DB, không phát domain event, không gửi thông báo duyệt thành công**.

## 9. Thay đổi role/authority, token và cache: “quyền cũ” còn sống bao lâu?

Nhiều thay đổi chính sách không chỉ là sửa `@PreAuthorize`. Ví dụ admin bỏ authority `invoice:approve` của Bob nhưng Bob đang có JWT sống thêm 30 phút. Nếu app dùng claims trong JWT làm nguồn authority cho đến khi token hết hạn, Bob có thể tiếp tục sở hữu authority cũ cho tới thời điểm hết hạn, **trừ khi** hệ thống có cơ chế thu hồi hoặc kiểm tra quyền thời gian thực phù hợp.

Phải nhận diện các lớp giữ trạng thái:

| Nguồn trạng thái | Rủi ro khi policy đổi | Cách kiểm soát |
| --- | --- | --- |
| JWT chứa role/authority | Token còn hạn mang quyền đã thu hồi | Cân nhắc TTL, revocation/version check hoặc authority lookup tùy yêu cầu thu hồi |
| Session / `Authentication` | Quyền được nạp từ phiên trước | Refresh/re-authentication/invalidation khi thay đổi quyền trọng yếu |
| Cache quyết định authorization | `ALLOW` cũ được tái sử dụng sau đổi policy | Key có subject/action/resource/context/version; TTL hợp lý và invalidation |
| Cache entity, list, search | Dữ liệu thuộc tenant khác/lệch trạng thái | Key theo scope, kiểm tra quyền khi trả response, invalidation khi ownership thay đổi |
| Bản sao ứng dụng triển khai khác version | Replica A cho phép, replica B từ chối | Triển khai version đồng bộ, compatibility window có chủ đích, theo dõi policy version |
| Database replica / eventual consistency | Quyết định dựa trên trạng thái chưa cập nhật | Với action nhạy cảm, kiểm tra trên nguồn nhất quán với transaction; không tin bản sao trễ |

**Policy version** (ví dụ `invoice-approval-v2`) là nhãn dùng để truy vết và đồng bộ, không tự làm token hoặc cache an toàn hơn. Mỗi lần thay rule phải biết nơi nào quyết định vẫn có thể đang dùng version cũ. Khi yêu cầu thu hồi quyền ngay lập tức, thiết kế cơ chế kiểm tra cập nhật trước khi chạy action; dựa vào token cũ còn hạn có thể không đáp ứng.

Các bản ghi audit nên nêu policy ID/version, actor ID, action, resource ID, tenant, kết quả và reason code nội bộ theo chính sách bảo vệ dữ liệu. Tránh lưu raw token, mật khẩu, thông tin tài chính chi tiết hoặc nội dung nhạy cảm không cần thiết trong log.

## 10. Kiểm tra tính nhất quán theo ba cấp

### 10.1. Unit test của chính sách

Unit test phải khẳng định cả case được phép và các điều kiện bị từ chối. Mỗi thay đổi điều kiện cần ít nhất một ca “chỉ một điều kiện sai” để biết đúng guard chịu trách nhiệm:

| Test case | Authority | Tenant | Creator | Status | Amount/limit | Kỳ vọng |
| --- | --- | --- | --- | --- | --- | --- |
| Eligible | Có | Trùng | Khác actor | PENDING | 700/1000 | ALLOW |
| Permission revoked | Không | Trùng | Khác actor | PENDING | 700/1000 | DENY |
| Cross-tenant | Có | Khác | Khác actor | PENDING | 700/1000 | DENY |
| Self approval | Có | Trùng | Cùng actor | PENDING | 700/1000 | DENY |
| Over limit | Có | Trùng | Khác actor | PENDING | 1500/1000 | DENY |
| Already finalized | Có | Trùng | Khác actor | PAID | 700/1000 | DENY |
| Missing actor/resource | Không xác định | — | — | — | — | DENY |

Kiểm tra thêm biên đúng hạn mức (`1000/1000` cho phép nếu dùng toán tử `<=`), thiếu thuộc tính, mapping role, ký tự Unicode trong ID nếu có, và trường hợp tenant khác nhưng trùng resource ID. Test nên biểu diễn policy **v2** rõ ràng, không copy-paste trực tiếp implementation vào expected result.

### 10.2. Integration test theo entrypoint và dữ liệu

Với Spring MVC + `spring-security-test`, mô phỏng principal có authorities phù hợp, gọi từng HTTP method/path bằng `MockMvc` (với CSRF token nếu request cần), đồng thời test service qua public bean và consumer/job handler. Kiểm tra:

1. Không có authentication / không có authority bị chặn ở HTTP.
2. Có authority nhưng khác tenant, tự duyệt, sai trạng thái hoặc vượt hạn mức bị chặn ở service.
3. User hợp lệ thực hiện thành công đúng **một** lần; request lặp lại không duyệt lần thứ hai.
4. Bị deny thì dữ liệu DB, outbox và các side effect liên quan **không thay đổi**.
5. List, search, count, export cùng scope; đổi ID trong URL không đọc/ghi bản ghi của người khác.
6. Method security còn hiệu lực qua Spring proxy; test đường self-invocation nếu kiến trúc có.
7. Hai đường HTTP và message cùng input tin cậy dẫn tới cùng quyết định.
8. Thay role/permission hoặc kích hoạt policy version mới không để dữ liệu/decision cache cấp quyền đã thu hồi.

**Status không đủ để chứng minh đúng.** Một API trả 200 nhưng phản hồi chứa bản ghi tenant khác vẫn lỗi; một API trả 403 sau khi đã ghi DB cũng sai. Khi review test cần quan sát cả response, DB state, event/outbox và hành vi sau rollback.

### 10.3. Contract/consistency test giữa các lớp

Nên có một tập **scenario chung** (bảng quyết định v2) mà các lớp liên quan dùng làm fixture. Test không cần bắt HTTP filter và service luôn trả cùng một loại lỗi; chỉ cần xác minh kết quả cuối cùng tuân thủ contract.

~~~text
Scenario: reviewer=bob, tenant=t1, authority=invoice:approve
Resource: creator=alice, tenant=t2, status=PENDING, amount=700

HTTP route permission check: PASS (authority hợp lệ)
Domain policy: DENY (cross-tenant)
Persistence mutation: 0 row
API observable outcome: không phê duyệt và không lộ dữ liệu
Async consumer outcome: không phê duyệt cùng resource
Cache/audit: không ghi nhận ALLOW cho policy mới
~~~

Trên bảng CI có thể xây dựng matrix actor × action × resource × entrypoint, so sánh với **expected quyết định chung**, đồng thời chạy qua nhiều security chain/route alias. Cần xác định các rule thay đổi ảnh hưởng endpoint nào; test theo từng điểm kiểm tra có ý nghĩa, không phải tạo hàng nghìn test chỉ lặp lại cùng mock implementation.

## 11. Quy trình triển khai một thay đổi policy an toàn

### Giai đoạn A — Thiết kế và review

1. Ghi rõ yêu cầu nghiệp vụ, actor, action, resource, context, phiên bản và thời điểm hiệu lực. Phân biệt **thu hồi quyền**, **bổ sung điều kiện**, và **mở rộng quyền** vì tác động khác nhau.
2. Lập decision matrix trước/sau và thống nhất hành vi `ALLOW/DENY`, 401/403/404/409, ngoại lệ, việc trả dữ liệu và side effect.
3. Liệt kê toàn bộ entrypoint và luồng xử lý; xác định nơi ra quyết định chính và cơ chế bảo vệ transaction/data.
4. Rà nguy cơ vi phạm tenant, quyền ngang/dọc, stale token/cache, đặc quyền tài khoản dịch vụ và cả các consumer chưa theo version mới.
5. Xác định ai có quyền thay policy, cơ chế phê duyệt/versioning và cách audit thay đổi cấu hình; bản thân thao tác sửa policy cũng là hành động được bảo vệ.

### Giai đoạn B — Sửa code và kiểm thử

1. Cập nhật **domain policy** trước như nguồn logic; nếu đổi permission name thì cập nhật mapping authorities có chủ đích.
2. Rà filter matcher, method annotations và các entrypoint. Bảo đảm deny-by-default ở nơi phù hợp và không có đường tắt service.
3. Cập nhật repository scope, conditional update/locking, cache invalidation và consumer. Chính sách mới phải nhất quán với điều kiện dữ liệu hiện hành.
4. Chạy unit matrix, integration tests và negative tests. Đo trạng thái DB/event sau các request bị deny.
5. Rà code path có `permitAll`, `hasRole`, `hasAuthority`, `@PreAuthorize`, `@PostAuthorize`, direct repository access, service account override và nơi tin `tenantId` phía client.

### Giai đoạn C — Triển khai và quan sát

1. Lập kế hoạch chuyển tiếp nếu nhiều replica, token cũ hoặc schema cũ còn hoạt động. Không mở rộng quyền ngoài ý muốn trong compatibility window.
2. Triển khai policy version cùng metric/log phù hợp; theo dõi tỷ lệ deny, route, reason code, tenant, bản phân phối instance và consumer.
3. Dùng feature flag hay shadow evaluation nếu rủi ro cao: **shadow decision chỉ ghi nhận**, tuyệt đối không tự cho phép action khi bản chính từ chối. Tránh gửi dữ liệu nhạy cảm qua shadow log.
4. Xác minh sau deploy các ca chủ chốt, đặc biệt token cũ, cache, role bị thu hồi, queue message tồn và bản ghi chuyển trạng thái cùng lúc.
5. Chuẩn bị rollback theo business contract: rollback code có thể khôi phục quyền vừa bị thu hồi, vì vậy phải đánh giá rủi ro trước khi quay lại phiên bản trước. Đối với thu hồi quyền khẩn cấp, ưu tiên chế độ an toàn từ chối, không tự ý mở lại quyền.

## 12. Những lỗi hay gặp khi chỉ sửa một lớp

| Lỗi | Dấu hiệu | Cách phát hiện và sửa |
| --- | --- | --- |
| Sửa URL rule, quên service | API A chặn nhưng job/API B vẫn duyệt | Test cùng policy scenario qua mọi entrypoint; đưa quyết định chi tiết vào service |
| Sửa `@PreAuthorize`, quên self-invocation | Gọi qua controller bị chặn, gọi trong cùng bean bỏ qua proxy | Test public bean path; chuyển boundary hoặc cưỡng chế policy trong use case |
| Chỉ kiểm tra authority mà không kiểm tra resource | Đổi ID là đọc/duyệt của tenant khác | Negative test cross-tenant/ownership; scope repository |
| Sửa get-by-id nhưng quên list/export/count | Không đọc được hóa đơn ID cụ thể nhưng thấy danh sách/metadata | Test mọi hình thức truy vấn và pagination |
| Dựa vào UI để ẩn nút | Gọi API thủ công vẫn thành công | Backend phải kiểm tra mọi lần |
| Bỏ qua consumer vì “internal” | Queue message cũ thực thi quyền cũ | Quy định service actor và gọi cùng domain policy |
| Cache hoặc JWT giữ quyền cũ | Vừa thu hồi role vẫn phê duyệt được | Kiểm tra TTL, revoke/version, invalidation |
| Kiểm tra policy trước transaction rồi ghi sau | Hai worker duyệt cùng invoice; trạng thái thay đổi giữa check và update | Transaction lock hoặc conditional update nguyên tử |
| Nhầm `hasRole` và `hasAuthority` | User có quyền nhưng 403 bất ngờ, hoặc mapping cấp thừa | Soát `GrantedAuthority` thực tế và prefix `ROLE_` |
| Policy đổi nhưng thiếu test deny | Chỉ happy-path pass trong CI | Decision matrix cho từng điều kiện mới và entrypoint |
| Mở rộng fallback khi policy service lỗi | Mất kết nối tới quyền thì tất cả được phép | Fail closed, trả lỗi phù hợp, giám sát và retry có kiểm soát |
| Rollback về policy cũ không đánh giá | Quyền đã thu hồi được mở lại | Review rollback như một thay đổi phân quyền độc lập |

## 13. Danh sách kiểm tra khi review Pull Request thay đổi authorization

Trả lời **Có/Không**, kèm đường dẫn test hoặc bằng chứng cụ thể:

- [ ] Có đặc tả `actor + action + resource + context` và bảng so sánh v1/v2.
- [ ] Các role/authorities được cấp từ nguồn tin cậy và mapping nhất quán.
- [ ] Route matcher, method annotations và mọi entrypoint liên quan được rà soát.
- [ ] Quy tắc per-resource ở service/domain policy, được gọi trước side effect.
- [ ] Repository query/list/count/export và update được giới hạn đúng quyền và tenant.
- [ ] Transaction hoặc atomic update bảo vệ trạng thái khỏi race.
- [ ] Consumer/job/admin endpoint có actor và chính sách riêng rõ ràng.
- [ ] Token/session/cache/policy version được xử lý theo yêu cầu thời điểm hiệu lực.
- [ ] Có test cho ALLOW và DENY, gồm cross-tenant, ownership, thiếu quyền, sai trạng thái, race.
- [ ] Có test chứng minh deny không làm thay đổi DB/outbox/event.
- [ ] API phản hồi và audit ghi nhận kết quả đúng mà không làm lộ dữ liệu nhạy cảm.
- [ ] Có kế hoạch rollout/rollback không mở lại quyền ngoài ý muốn.

**Kết luận học tập:** “Nhất quán giữa các lớp” không có nghĩa copy y nguyên một câu `hasAuthority` khắp nơi. Đó là khả năng chứng minh **mọi đường thực thi đưa ra hoặc tôn trọng một quyết định chính sách duy nhất**, từ quyền tổng quát ở HTTP, điều kiện tài nguyên tại service, tới ràng buộc dữ liệu và side effect trong transaction. Khi policy thay đổi, chính **bảng quyết định và tập test xuyên lớp** là công cụ phát hiện nơi còn áp dụng quy tắc cũ.

### Tài liệu tham khảo chính thức

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
