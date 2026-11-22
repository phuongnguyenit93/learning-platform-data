# Leo thang đặc quyền theo chiều dọc và truy cập trái phép theo chiều ngang

> **Module:** Spring Security – authorization  
> **Nhóm kiến thức:** Mô hình kiểm soát truy cập

## 1. Bối cảnh: đã đăng nhập vẫn có thể truy cập sai quyền

Một ứng dụng quản lý hóa đơn có ba tài khoản:

- **An** là nhân viên thông thường, được xem hóa đơn do An phụ trách.
- **Bình** cũng là nhân viên, được xem hóa đơn của Bình.
- **Chi** có quyền phê duyệt hóa đơn trong tổ chức T1.

Hai yêu cầu có vẻ giống nhau nhưng sai ở **hai chiều khác nhau**:

1. An gửi yêu cầu vào chức năng **phê duyệt** chỉ dành cho người có quyền phê duyệt: người dùng có mức đặc quyền thấp cố thực hiện hành động ở mức cao hơn.
2. An gọi chức năng **xem hóa đơn** vốn được phép dùng, nhưng thay ID để xem hóa đơn riêng của Bình: người dùng đi ngang sang tài nguyên của người khác trong cùng mức quyền.

Cả hai là **Broken Access Control** – thiếu hoặc thực thi sai kiểm soát truy cập. Chỉ kiểm tra `isAuthenticated()`, kiểm tra token hợp lệ, giấu nút trong giao diện, hay dùng ID khó đoán đều **không đủ**.

Bài này tập trung trả lời:

- Leo thang đặc quyền theo chiều dọc (*vertical privilege escalation*) khác truy cập trái phép theo chiều ngang (*horizontal unauthorized access / horizontal privilege escalation*) ở đâu?
- Lỗi kiểm tra chức năng và lỗi kiểm tra từng đối tượng dữ liệu hình thành như thế nào?
- Áp dụng Spring Security ở HTTP, method và tầng dữ liệu ra sao để chặn cả hai?
- Phải thiết kế bộ test âm tính nào để phát hiện lỗi trước khi triển khai?

## 2. Mô hình quyết định truy cập

Một yêu cầu phân quyền đầy đủ cần ít nhất bốn thông tin:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **Subject (chủ thể)** | Ai đang yêu cầu? Thuộc tenant nào, có role/permission gì? | An, `tenant=T1`, `invoice:read` |
| **Action (hành động)** | Muốn làm gì? | `read`, `update`, `approve`, `delete` |
| **Resource (tài nguyên)** | Tác động lên bản ghi hoặc đối tượng nào? | Hóa đơn `INV-102`, chủ sở hữu Bình |
| **Context (ngữ cảnh)** | Điều kiện hiện tại có cho phép không? | `status=PENDING`, tenant, phòng ban, chính sách chia sẻ |

Diễn đạt chính sách một cách tường minh:

~~~text
ALLOW(subject, action, resource, context)
  = subject đã được xác thực
    AND subject được phép thực hiện action
    AND subject được phép thao tác trên resource cụ thể
    AND các điều kiện context đều thỏa mãn
~~~

**Authentication (xác thực)** trả lời “ai?”. **Authorization (phân quyền)** trả lời “được làm gì với đối tượng nào?”. Role, authority và token scope có thể hỗ trợ **kiểm tra hành động**, nhưng **không tự chứng minh** quyền trên một tài nguyên cụ thể.

Trong Spring Security, `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`; `hasAuthority("invoice:read")` so sánh chuỗi quyền chính xác. Khi dùng JWT Resource Server, OAuth scope như `invoices.read` thường được ánh xạ thành `SCOPE_invoices.read`. Việc role được cấp permission nào và quyền nào áp dụng cho hóa đơn nào **là chính sách do ứng dụng xác định**.

## 3. Leo thang đặc quyền theo chiều dọc (vertical privilege escalation)

### 3.1. Định nghĩa

**Vertical privilege escalation** xảy ra khi một chủ thể có **mức đặc quyền thấp** thực hiện được hành động hoặc chức năng chỉ dành cho **mức đặc quyền cao hơn**, do hệ thống kiểm tra quyền không đầy đủ.

Ví dụ chức năng:

| Tài khoản | Quyền hợp lệ | Hành động vượt quyền |
|---|---|---|
| Nhân viên | `invoice:read` | `invoice:approve` |
| Người duyệt | `invoice:approve` | `user:manage` |
| Người dùng thông thường | Xem hồ sơ cá nhân | Sửa role hoặc trạng thái khóa của tài khoản khác |
| Nhân viên vận hành | Xem báo cáo tổng hợp | Truy cập cấu hình hệ thống chỉ dành cho admin |

Không bắt buộc phải “đổi role thành ADMIN” mới gọi là leo thang theo chiều dọc. **Thực thi thành công một thao tác đặc quyền cao hơn** cũng đủ để cho thấy kiểm soát truy cập bị sai.

### 3.2. Ví dụ: API cho người duyệt bị mở sai

Giả sử hệ thống có các endpoint:

~~~http
GET /api/invoices/101
POST /api/invoices/101/approve
~~~

Chính sách dự kiến:

- `GET`: yêu cầu `invoice:read` và quyền truy cập hóa đơn cụ thể.
- `POST .../approve`: yêu cầu `invoice:approve`, hóa đơn cùng tenant và đang ở trạng thái có thể duyệt.

Nếu endpoint phê duyệt chỉ yêu cầu “người gọi đã đăng nhập” mà không kiểm tra permission `invoice:approve`, nhân viên thông thường có thể thực hiện thao tác vốn dành cho người duyệt. Đây là **lỗi phân quyền chức năng**, thường được gọi là *Broken Function Level Authorization* (BFLA).

Lỗi có thể nằm ở nhiều lớp:

- HTTP URL rule quá rộng hoặc không bao phủ endpoint mới.
- Service method thiếu kiểm tra permission, hoặc được gọi qua một luồng không đi qua controller.
- Chỉ ẩn nút “Duyệt” trên giao diện mà backend không kiểm tra.
- Dựa vào trường `role` hoặc `isAdmin` do client tự truyền.
- Gọi trực tiếp một bước trong workflow mà server không kiểm tra quyền và trạng thái chuyển tiếp.

### 3.3. Một biến thể: tự nâng quyền qua mass assignment

Hãy xét API cho phép người dùng cập nhật thông tin cá nhân. Ứng dụng cần cho sửa `displayName` nhưng lại dùng trực tiếp mọi trường từ request để ghi vào entity chứa cả `role`, `enabled`, `tenantId`.

~~~json
{
  "displayName": "An",
  "role": "ADMIN"
}
~~~

Nếu server nhận và lưu cả `role` từ nguồn không đáng tin, người dùng có thể tự cấp quyền cao hơn. Đây là lỗi **gán thuộc tính hàng loạt thiếu kiểm soát (mass assignment)** có thể dẫn đến leo thang đặc quyền. Phòng tránh bằng DTO/allowlist trường được phép sửa, mapping tường minh và kiểm tra quyền riêng cho trường nhạy cảm. Việc chỉ bỏ trường khỏi giao diện **không phải biện pháp bảo vệ**.

### 3.4. Nguyên nhân cốt lõi

Hệ thống thiếu kiểm tra **“chủ thể này có quyền gọi hành động đặc quyền không?”** tại nơi thực hiện hành động. Chỉ có quyền xem tài nguyên không đồng nghĩa có quyền phê duyệt, xóa, phân quyền hay truy cập quản trị.

## 4. Truy cập trái phép theo chiều ngang (horizontal unauthorized access)

### 4.1. Định nghĩa

**Horizontal unauthorized access** xảy ra khi một chủ thể truy cập hoặc thay đổi tài nguyên của **chủ thể khác có cùng mức đặc quyền**, dù chức năng đang gọi là chức năng chính họ cũng được phép sử dụng.

Ví dụ hai nhân viên có cùng role `EMPLOYEE`:

- An được đọc hóa đơn `101` do An sở hữu.
- Bình được đọc hóa đơn `102` do Bình sở hữu.
- An yêu cầu đọc `102` và hệ thống trả dữ liệu của Bình.

An không nhất thiết sử dụng chức năng “admin”; **hành động đọc là hợp lệ**, nhưng **đối tượng bị đọc là sai**. Đây là lỗi phân quyền trên từng đối tượng, gọi là *Broken Object Level Authorization* (BOLA). Kiểu lộ dữ liệu qua tham chiếu đối tượng mà không kiểm tra quyền phù hợp thường được gọi là *Insecure Direct Object Reference* (IDOR).

### 4.2. Ví dụ: kiểm tra role nhưng bỏ qua owner

Một đoạn xử lý minh họa bị lỗi:

~~~java
// Minh họa lỗi; không sao chép vào ứng dụng thật.
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceDto getInvoice(long id) {
    Invoice invoice = repository.findById(id)
            .orElseThrow();
    return mapper.toDto(invoice);
}
~~~

Giả sử `invoice:read` được gán cho mọi nhân viên. Annotation chỉ trả lời **“có permission đọc hóa đơn nói chung không?”**, còn `findById(id)` không kiểm tra hóa đơn có thuộc owner hoặc tenant được phép không. Một nhân viên có thể truy cập hóa đơn khác nếu biết hoặc đoán được ID.

Sửa bằng cách định nghĩa policy cho **đối tượng cụ thể** và ràng buộc truy vấn theo tenant/owner hoặc quan hệ được cấp quyền. Cần bao phủ cả đọc, cập nhật, xóa, tải tệp đính kèm, xuất dữ liệu, lịch sử và các chức năng liên quan; không chỉ một endpoint.

### 4.3. Tenant và quan hệ chia sẻ

Horizontal access không chỉ xuất hiện giữa hai cá nhân. Trong SaaS đa tenant, hai quản trị viên tổ chức có thể cùng role `TENANT_ADMIN` nhưng mỗi người chỉ được quản trị tài nguyên thuộc tenant mình. Nếu quản trị viên T1 đọc được dữ liệu T2, đó cũng là vi phạm ranh giới dữ liệu.

Ngược lại, việc người A truy cập dữ liệu của B **không luôn là sai**. Có trường hợp B đã chia sẻ bản ghi cho A hoặc A được giao nhiệm vụ xử lý. Khi đó hệ thống cần **quy tắc quan hệ được xác minh từ server**: người sở hữu, người được chia sẻ, nhóm được ủy quyền, người giám sát, quyền trên tổ chức, v.v.

Không nên định nghĩa policy quá cứng như “owner ID phải luôn bằng user ID” nếu nghiệp vụ thực sự có chia sẻ; cũng không được bỏ luôn điều kiện object-level chỉ vì một số role cần xem hộ.

### 4.4. ID khó đoán không thay thế kiểm tra quyền

Thay số `101` bằng UUID hoặc ID ngẫu nhiên giúp giảm khả năng đoán ID, nhưng **không tạo ra quyền truy cập**. ID có thể xuất hiện trong URL, log, email, trang chia sẻ hoặc dữ liệu khác. Nếu API cứ nhận ID đúng là trả dữ liệu, hệ thống vẫn bị BOLA.

Điểm cốt lõi cần thực hiện là **kiểm tra đối tượng trên mọi yêu cầu**, bất kể định dạng khóa chính.

## 5. So sánh nhanh hai chiều vượt quyền

| Tiêu chí | Theo chiều dọc | Theo chiều ngang |
|---|---|---|
| Chủ thể thực hiện | Người có ít quyền hơn chức năng cần gọi | Người có quyền dùng chức năng nhưng không có quyền trên đối tượng đích |
| Ranh giới bị vượt | **Cấp chức năng / đặc quyền** | **Sở hữu / tenant / quan hệ tài nguyên** |
| Câu hỏi kiểm tra bị thiếu | “Có được thực hiện hành động này không?” | “Có được thực hiện hành động này trên **đối tượng cụ thể này** không?” |
| Ví dụ | `EMPLOYEE` gọi `approveInvoice` | An xem hóa đơn riêng của Bình |
| Kiểm soát điển hình | Permission, role, method/URL authorization, workflow guards | Resource policy, owner/tenant constraint, relationship checks |
| Nhãn thường gặp | BFLA, vertical privilege escalation | BOLA, IDOR, horizontal privilege escalation |

**Lưu ý:** Hai chiều có thể xuất hiện **đồng thời**. Ví dụ người dùng thông thường vừa gọi endpoint duyệt trái phép (dọc), vừa duyệt hóa đơn của tenant khác (ngang). Cũng có trường hợp một admin có đặc quyền rộng trong tenant mình nhưng vẫn bị cấm thao tác vượt tenant. Vì vậy không thể chỉ so sánh tên role; phải xem **chính sách trên hành động và đối tượng**.

## 6. Mô hình bảo vệ nhiều lớp trong Spring Security

~~~text
HTTP request: principal + action + resource id
                     |
                     v
          Authentication hợp lệ?
                     |
                không | có
                     v
             401    URL/API rule
                    (scope/role/permission)
                        |
                    không | có
                        v
                       403
                         v
             Service / use-case policy
             - permission nghiệp vụ?
             - đúng tenant?
             - owner / shared / delegated?
             - trạng thái hợp lệ?
                         |
                    không | có
                         v
                 403/404  thao tác dữ liệu
                              |
                              v
                     200/201/204...
~~~

Sơ đồ mang tính khái niệm: ứng dụng có thể dùng `404 Not Found` để không tiết lộ sự tồn tại của tài nguyên, miễn là chính sách xử lý nhất quán. `401` thường dành cho yêu cầu chưa xác thực/token không hợp lệ; `403` thường dành cho chủ thể đã xác thực nhưng không đủ quyền. Phản hồi thực tế phụ thuộc entry point, filter chain và access-denied handler.

Cần **hai lớp kiểm tra độc lập nhưng phối hợp**:

1. **Function-level authorization:** kiểm tra người gọi có được thực hiện hành động không. Ví dụ chỉ role/permission phù hợp mới được phê duyệt.
2. **Object-level authorization:** kiểm tra đối tượng cụ thể có thuộc phạm vi được phép không. Ví dụ đúng tenant, đúng owner, được chia sẻ hợp lệ, trạng thái phù hợp.

Kiểm tra ở HTTP giúp từ chối sớm. Kiểm tra tại service/use case giúp bảo vệ nghiệp vụ khi có nhiều controller, job, event consumer hoặc luồng nội bộ cùng gọi vào một chức năng. Bộ lọc dữ liệu ở repository tăng thêm lớp phòng thủ, đặc biệt trong hệ thống đa tenant.

## 7. Ví dụ Spring Security 6.x / Spring Boot 3.x

### 7.1. Chặn thao tác đặc quyền ở HTTP layer

Ví dụ dưới đây là **lớp cấu hình trong một dự án Spring Boot Servlet có Spring Security và OAuth 2.0 Resource Server JWT đã được cấu hình hợp lệ**. Đây không phải chương trình Java chạy độc lập. Giả sử Authorization Server cấp scope `invoices.read` và `invoices.approve`; converter JWT mặc định ánh xạ thành các authority `SCOPE_*`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                    .hasAuthority("SCOPE_invoices.approve")
                .requestMatchers(HttpMethod.GET, "/api/invoices/*")
                    .hasAuthority("SCOPE_invoices.read")
                .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Ý nghĩa và giới hạn:**

- Người có token chỉ chứa `invoices.read` không thể gọi endpoint duyệt nếu không có `SCOPE_invoices.approve`. Điều này giúp ngăn một phần **vượt quyền theo chiều dọc**.
- `SCOPE_invoices.approve` là **scope token**, chưa chắc là quyền duyệt nghiệp vụ của user. Nếu nghiệp vụ còn yêu cầu role/permission `invoice:approve`, phải có policy/authority tương ứng được kiểm tra bổ sung.
- `GET .../{id}` chỉ kiểm tra phạm vi đọc của token; vẫn phải chặn **truy cập ngang** bằng kiểm tra hóa đơn cụ thể.
- Converter mặc định cho JWT **không tự chuyển claim role tùy biến thành `ROLE_ADMIN`**. Muốn kiểm tra role/permission khác scope phải cấu hình ánh xạ từ nguồn đáng tin hoặc thực thi logic qua policy.
- `anyRequest().denyAll()` từ chối các URL khác chưa cấu hình. Một ứng dụng hoàn chỉnh cần khai báo rõ các API khác, endpoint public/health nếu cần và quy tắc kiểm soát access token (issuer, audience theo thiết kế).
- Đừng coi việc một rule URL hiện tại khớp là lý do bỏ kiểm tra tại service; các tuyến gọi sau này có thể khác.

Với ứng dụng dùng session/cookie thay vì Bearer token, cần thiết kế xác thực và CSRF protection phù hợp; đoạn mã JWT phía trên không phải hướng dẫn tắt CSRF cho mọi ứng dụng.

### 7.2. Chặn cả quyền chức năng và quyền đối tượng tại service

Với Spring-managed service và `@EnableMethodSecurity`, có thể đặt policy ngay ở use case:

~~~java
// Minh họa hai method của một Spring-managed service.
// invoicePolicy là bean do ứng dụng tự cài đặt.
@PreAuthorize(
    "hasAuthority('SCOPE_invoices.read') " +
    "and @invoicePolicy.canRead(authentication, #id)"
)
public InvoiceDto readInvoice(long id) {
    return invoiceQueryService.read(id);
}

@PreAuthorize(
    "hasAuthority('SCOPE_invoices.approve') " +
    "and @invoicePolicy.canApprove(authentication, #id)"
)
public void approveInvoice(long id) {
    invoiceCommandService.approve(id);
}
~~~

Đoạn trên **không độc lập**: `InvoiceDto`, hai service và bean `invoicePolicy` là thành phần của ứng dụng. Policy phải tự xác minh **role/permission nghiệp vụ**, tenant, ownership/delegation và trạng thái tài nguyên bằng dữ liệu server. Không dùng `#id` như bằng chứng về quyền chỉ vì client biết ID.

Một policy đọc có thể diễn giải:

~~~text
canRead(authentication, invoiceId):
  actor = identity được xác minh từ authentication
  invoice = tìm bằng invoiceId trong tenant hợp lệ
  deny nếu invoice không tồn tại
  deny nếu actor không có permission invoice:read
  allow nếu actor là owner hoặc được chia sẻ hợp lệ
  allow nếu actor có quyền read-all-in-tenant
  deny trong các trường hợp còn lại
~~~

Policy duyệt có thể yêu cầu `invoice:approve`, cùng tenant, `status=PENDING` và không vi phạm quy tắc tách biệt người tạo/người duyệt (nếu nghiệp vụ yêu cầu). **Quy tắc này không mặc định có sẵn trong Spring Security**; phải do ứng dụng quyết định và kiểm thử.

**Hai chi tiết kỹ thuật dễ bỏ sót:** tham số `#id` cần được method security nhận diện đúng (ví dụ biên dịch với `-parameters` hoặc cung cấp tên tham số tường minh); lời gọi nội bộ trực tiếp tới method khác trên cùng instance có thể không đi qua Spring AOP proxy nên annotation không được áp dụng. Đặt ràng buộc thiết yếu tại service/repository để không phụ thuộc hoàn toàn vào một điểm chặn.

### 7.3. Ràng buộc truy vấn dữ liệu theo tenant

Một cách phòng vệ bổ sung là đưa tenant đáng tin cậy vào truy vấn thay vì tải bản ghi toàn hệ thống bằng ID rồi quên kiểm tra:

~~~sql
SELECT id, tenant_id, owner_id, status
FROM invoice
WHERE id = :invoiceId
  AND tenant_id = :authenticatedTenantId;
~~~

Nếu chính sách chỉ cho owner đọc, có thể ràng buộc thêm:

~~~sql
SELECT id, tenant_id, owner_id, status
FROM invoice
WHERE id = :invoiceId
  AND tenant_id = :authenticatedTenantId
  AND (
      owner_id = :authenticatedUserId
      OR :mayReadAnyInTenant = TRUE
  );
~~~

Các biến `authenticatedTenantId`, `authenticatedUserId` và `mayReadAnyInTenant` **phải được tính ở server từ danh tính và quyền tin cậy**; không dùng giá trị client tự điền để tạo điều kiện vượt quyền. Câu lệnh SQL trên minh họa ý tưởng, chi tiết schema/binding phụ thuộc hệ thống thực tế.

Đối với thao tác đổi trạng thái, nên kiểm tra và cập nhật có tính nguyên tử trong transaction khi có cạnh tranh đồng thời, ví dụ chỉ đổi hóa đơn cùng tenant và vẫn ở trạng thái `PENDING`. Tránh lỗi “kiểm tra xong – trạng thái thay đổi – vẫn ghi” (*time-of-check/time-of-use*).

## 8. Bài thực hành Java 17: cùng một policy chặn hai hướng tấn công

Ví dụ dưới đây là **chương trình Java thuần, có thể biên dịch độc lập**, mô phỏng policy cho tài liệu. Nó cố ý tách permission hành động khỏi owner/tenant. Chuỗi quyền chỉ là dữ liệu mô phỏng, không phải `GrantedAuthority` thực sự của Spring Security.

Tạo tệp `AccessControlDemo.java`:

~~~java
import java.util.Set;

public class AccessControlDemo {

    record Actor(String id, String tenant, Set<String> permissions) {
    }

    record Document(
            String id, String tenant, String owner, String status) {
    }

    static boolean allows(Actor actor, String action, Document document) {
        // Ranh giới dữ liệu: không cho vượt tenant.
        if (!actor.tenant().equals(document.tenant())) {
            return false;
        }

        return switch (action) {
            case "read" -> actor.permissions().contains("document:read")
                    && (actor.id().equals(document.owner())
                    || actor.permissions().contains(
                            "document:read:any-in-tenant"));

            case "approve" -> actor.permissions().contains("document:approve")
                    && document.status().equals("PENDING");

            default -> false; // Mặc định từ chối hành động lạ.
        };
    }

    static void show(String label, boolean decision) {
        System.out.println(label + ": " + decision);
    }

    public static void main(String[] args) {
        Document target = new Document("D-100", "T1", "alice", "PENDING");

        Actor alice = new Actor(
                "alice", "T1", Set.of("document:read"));

        Actor bob = new Actor(
                "bob", "T1", Set.of("document:read"));

        Actor approver = new Actor(
                "carol", "T1",
                Set.of("document:read", "document:read:any-in-tenant",
                        "document:approve"));

        Actor anotherTenant = new Actor(
                "dave", "T2",
                Set.of("document:read", "document:read:any-in-tenant",
                        "document:approve"));

        show("Alice reads own", allows(alice, "read", target));
        show("Bob reads Alice", allows(bob, "read", target));
        show("Alice approves", allows(alice, "approve", target));
        show("Carol approves", allows(approver, "approve", target));
        show("Dave approves T1", allows(anotherTenant, "approve", target));
        show("Unknown action", allows(approver, "delete", target));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac AccessControlDemo.java
java AccessControlDemo
~~~

Kết quả chuẩn:

~~~text
Alice reads own: true
Bob reads Alice: false
Alice approves: false
Carol approves: true
Dave approves T1: false
Unknown action: false
~~~

**Phân tích từng nhánh:**

- **Alice đọc tài liệu mình sở hữu:** có `document:read`, đúng owner, đúng tenant → cho phép.
- **Bob đọc tài liệu của Alice:** cùng cấp permission đọc nhưng sai owner → từ chối **truy cập ngang**.
- **Alice duyệt tài liệu:** không có `document:approve` → từ chối **leo thang dọc**.
- **Carol duyệt:** có permission duyệt, đúng tenant và trạng thái `PENDING` → cho phép.
- **Dave duyệt tài liệu của T1:** dù có permission duyệt nhưng thuộc T2 → từ chối **vượt tenant**.
- **Hành động không khai báo:** nhánh `default` trả false, thể hiện **deny by default**.

Chương trình này chỉ minh họa **logic quyết định**, chưa có authentication, JWT, transaction, database hay kiểm soát đồng thời. Trong ứng dụng thật, permissions và tenant phải được dựng từ nguồn đáng tin; chính sách có thể cần thêm điều kiện chia sẻ, tách biệt nhiệm vụ hoặc người có quyền duyệt trong đúng đơn vị.

## 9. Quy tắc thiết kế tránh lỗi lặp lại

### 9.1. Không tin dữ liệu đặc quyền do client tự khai

Không lấy `role`, `tenantId`, `userId` hay `isAdmin` từ query parameter/body/header làm nguồn duy nhất xác định quyền. Client có thể thay những giá trị đó. Hãy sử dụng authentication đã được xác minh, membership/role do server quản lý, và dữ liệu gốc của resource.

Tương tự, một access token hợp lệ có scope `read` chưa chắc là bằng chứng được đọc **mọi** đối tượng; scope và quyền trên bản ghi phải được đánh giá riêng. Nếu một service nhận token từ service khác, cần kiểm tra token cho đúng audience/issuer và hiểu chủ thể cuối cùng, tránh nhầm quyền của service với quyền của người dùng.

### 9.2. Kiểm tra mọi entry point và mọi đối tượng

Bản ghi có thể xuất hiện qua nhiều bề mặt:

- Xem chi tiết, danh sách, tìm kiếm và export.
- Cập nhật, duyệt, hủy, xóa và thay đổi trạng thái.
- Tải file đính kèm, xem lịch sử và các tài nguyên con.
- Batch endpoint, GraphQL resolver, WebSocket, job và event consumer.
- Admin UI và API dùng chung service.

Nếu một đường đi áp dụng policy còn đường khác bỏ qua, kẻ gọi có thể chạm được dữ liệu qua đường còn thiếu kiểm tra. Đặt policy gần use case và tạo cách dùng chung cho những đường vào tương đương; không đẩy toàn bộ trách nhiệm vào UI hay gateway.

### 9.3. Giới hạn quyền và fail closed

- Chọn permission cụ thể, không cấp `ADMIN` cho tác vụ chỉ cần đọc.
- Khi thiếu thông tin chủ thể/tài nguyên/chính sách: từ chối, không mặc định cho phép.
- Không coi ID có định dạng bí mật là access-control mechanism.
- Không lạm dụng wildcard/pattern mở rộng quá nhiều endpoint và không đặt `permitAll()` cho nghiệp vụ nhạy cảm.
- Không tin rằng role cấp cao ở tenant A có quyền với tenant B.
- Khi cố ý cho admin toàn hệ thống vượt tenant, phải có **policy riêng**, kiểm toán và test rõ ràng.

### 9.4. Không lộ dữ liệu trước khi quyết định quyền

Việc chỉ kiểm tra quyền sau khi đã tạo DTO hoặc trước khi render frontend có thể làm rò rỉ dữ liệu qua log, cache hoặc serialization. Nên kiểm tra tại điểm truy vấn/trước khi trả kết quả. Với danh sách dữ liệu, bộ lọc theo tenant/owner phải áp dụng ở câu truy vấn, không chỉ lọc phần tử bằng Java sau khi đã lấy toàn bộ bảng.

Cache cũng cần khóa theo phạm vi thích hợp; cache trả chi tiết hóa đơn chỉ theo ID mà bỏ tenant/user có thể gây lộ dữ liệu giữa người gọi dù endpoint có kiểm tra một phần.

## 10. Thiết kế test âm tính: kiểm tra thứ hệ thống **phải từ chối**

Dựng dữ liệu test với các tài khoản và bản ghi **khác nhau thật sự**:

~~~text
Alice: USER, tenant T1, có document:read
Bob:   USER, tenant T1, có document:read
Carol: APPROVER, tenant T1, có document:approve
Dave:  APPROVER, tenant T2, có document:approve

D-100: owner=Alice, tenant=T1, status=PENDING
D-200: owner=Bob,   tenant=T1, status=PENDING
D-300: owner=Dave,  tenant=T2, status=PENDING
~~~

| Kịch bản | Mong đợi | Lỗi phát hiện nếu cho qua |
|---|---|---|
| Alice đọc D-100 | Cho phép | Kiểm tra chức năng quá chặt nếu bị chặn |
| Alice đọc D-200 | **Từ chối** | Horizontal / BOLA |
| Alice đọc D-300 | **Từ chối** | Cross-tenant / BOLA |
| Alice gọi API duyệt D-100 | **Từ chối** | Vertical / BFLA |
| Carol duyệt D-100 ở T1 | Cho phép nếu các điều kiện khác hợp lệ | Kiểm tra đúng quyền |
| Carol duyệt D-300 của T2 | **Từ chối** | Cross-tenant |
| Client gửi `role=ADMIN` trong request | Không làm thay đổi quyền | Trusting client / mass assignment |
| Token thiếu scope bắt buộc | **Từ chối** | Thiếu kiểm tra phạm vi token |
| Bản ghi đã `APPROVED` bị duyệt lại | **Từ chối** theo workflow | Thiếu ràng buộc trạng thái |
| Tham số id thay đổi giữa hai người dùng | Mỗi request kiểm tra lại đối tượng | BOLA nếu reuse kết quả quyền của ID cũ |

Chú ý test **cả phương thức HTTP, cả use case và cả kết quả truy vấn**. Kiểm thử chỉ với một tài khoản admin sẽ không phát hiện được truy cập ngang. Test thành công đơn thuần cũng không chứng minh rằng các trường hợp sai đều bị chặn.

Trong dự án Spring Security, có thể sử dụng Spring Security Test/MockMvc để kiểm tra đường HTTP và method security. `@WithMockUser` giúp mô phỏng người dùng/authority; khi xác minh JWT Resource Server cần test riêng mapping token/scope thực tế, vì mock user không chứng minh converter và validator JWT hoạt động. Với test ở service hoặc repository, dùng bản ghi khác owner/tenant để kiểm tra policy cho đúng từng resource.

Cần chú ý **403 so với 404**: một số ứng dụng cố ý trả 404 cho bản ghi không thuộc phạm vi để tránh lộ sự tồn tại; viết assertion theo chính sách hệ thống, nhưng luôn bảo đảm dữ liệu bí mật **không được trả**. Không dùng một lỗi HTTP bất kỳ làm bằng chứng đủ nếu response body đã rò rỉ dữ liệu.

## 11. Các sai lầm khó phát hiện trong hệ thống lớn

| Sai lầm | Hệ quả |
|---|---|
| Coi kiểm tra `authenticated` là đủ | Người dùng thường gọi được chức năng đặc quyền cao |
| Chỉ có `hasRole` ở controller | Service, job hoặc entry point khác bỏ qua rule |
| Chỉ có `hasAuthority("invoice:read")` khi đọc theo ID | Người cùng role đọc bản ghi không thuộc mình |
| Bỏ filter tenant trong repository | Truy cập chéo tổ chức dù UI đang chọn tenant đúng |
| Tin `tenantId` do client chọn | Người dùng có thể tự chọn tenant khác |
| Không kiểm soát trường nhạy cảm khi update entity | Mass assignment nâng role/đổi owner |
| Kiểm tra quyền trước, cập nhật sau mà không quản lý cạnh tranh | Bản ghi đổi trạng thái trong khoảng giữa hai bước |
| Cache response chỉ theo resource ID | Trả dữ liệu của user/tenant khác |
| Phụ thuộc vào `@PreAuthorize` khi method được tự gọi trên cùng bean | Advice của proxy có thể không chạy |
| Chỉ test 200 với admin | Không phát hiện vertical/horizontal denial bị thiếu |
| Dùng UUID rồi bỏ authorization | ID khó đoán không tương đương quyền truy cập |
| Log toàn bộ token và dữ liệu nhạy cảm khi từ chối | Gây rò rỉ thông tin ngoài đường API |

Một điểm thực tế: **vấn đề hiển thị nút** và **vấn đề thực thi quyền** là hai trách nhiệm khác nhau. UI nên ẩn hoặc vô hiệu hóa thao tác để người dùng không gặp lỗi ngoài ý muốn, nhưng server luôn là nơi quyết định cuối cùng.

## 12. Checklist khi review một endpoint mới

Ví dụ PR bổ sung `POST /api/invoices/{id}/approve`:

1. **Xác thực:** ai đang gọi? Token/phiên có hợp lệ không?
2. **Hành động:** permission/role/scope nào bắt buộc cho “approve”? Kiểm tra ở đâu?
3. **Dữ liệu:** invoice nào, tenant nào, có phải đối tượng mà chủ thể được phép duyệt không?
4. **Workflow:** trạng thái nào có thể chuyển sang APPROVED? Có yêu cầu người duyệt khác người tạo không?
5. **Nguồn tin cậy:** user ID, role, tenant và permission đến từ server hay dữ liệu client tự nhập?
6. **Đường gọi khác:** method này có được gọi từ controller/job/event nào không? Policy có được thực thi nhất quán không?
7. **Phòng thủ dữ liệu:** truy vấn đã giới hạn tenant? Cập nhật có xử lý transaction/điều kiện trạng thái không?
8. **Kiểm thử:** đã có case user thường cố duyệt, user cùng cấp xem bản ghi khác, admin khác tenant, thiếu scope và trạng thái không hợp lệ chưa?
9. **Quan sát:** audit log ghi subject, action, resource, tenant, kết quả và lý do ở mức phù hợp; không ghi token/secret?

Nếu câu trả lời cho việc **“được phép làm hành động này?”** hoặc **“được phép làm trên đúng bản ghi này?”** chưa rõ, policy chưa sẵn sàng.

## 13. Tổng kết và tự kiểm tra

**Ghi nhớ:**

- **Vertical privilege escalation:** vượt qua **cấp đặc quyền/chức năng**; ví dụ nhân viên thường duyệt hóa đơn.
- **Horizontal unauthorized access:** vượt qua **ranh giới đối tượng** trong cùng cấp quyền; ví dụ nhân viên đọc hóa đơn của đồng nghiệp.
- **BFLA** gắn với kiểm tra sai chức năng; **BOLA/IDOR** gắn với kiểm tra sai đối tượng. Hai nhóm có thể xảy ra đồng thời.
- **Spring Security URL/method authorization** là điểm chặn quan trọng; **service policy và giới hạn truy vấn dữ liệu** mới làm rõ quyền trên từng tài nguyên.
- **Deny by default, least privilege, server-side enforcement, negative tests** là các nguyên tắc xuyên suốt.

**Câu hỏi luyện tập:**

1. An có `invoice:read` và đọc được hóa đơn của Bình qua một ID khác. Đây là lỗi gì? **Horizontal/BOLA**: hành động đọc được phép nhưng bản ghi không thuộc phạm vi.
2. An không có `invoice:approve` nhưng gọi API duyệt thành công. Đây là lỗi gì? **Vertical/BFLA**: thực thi thao tác đặc quyền cao hơn.
3. Quản trị viên tenant T1 có được mặc nhiên xem bản ghi tenant T2? **Không**: chức danh cao trong T1 không tự cấp quyền vượt tenant.
4. Đổi ID số thành UUID đã xử lý BOLA chưa? **Chưa**: vẫn phải kiểm tra quyền từng đối tượng.
5. `hasAuthority("SCOPE_invoices.read")` đã đủ để trả hóa đơn theo ID chưa? **Chưa**: token scope không thay thế quyền theo owner/tenant và policy nghiệp vụ.
6. Nếu chỉ test API bằng tài khoản admin, bạn bỏ sót nhóm test nào? **Các test từ chối**: user thường gọi chức năng admin, hai user cùng role truy cập chéo tài nguyên, hai tenant truy cập chéo.

### Nguồn tham khảo

- Spring Security – Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP API Security Top 10 (2023): https://owasp.org/API-Security/editions/2023/en/0x11-t10/