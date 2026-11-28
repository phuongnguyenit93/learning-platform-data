# Tenant-scoped role

## 1. Vai trò phải đi cùng phạm vi tenant

**Tenant-scoped role** là cách tổ chức vai trò và phép gán vai trò sao cho quyền chỉ có hiệu lực trong một tenant xác định. Trong ứng dụng SaaS, tenant thường đại diện cho một khách hàng, tổ chức hoặc workspace có ranh giới dữ liệu và quản trị riêng.

Ví dụ, Lan tham gia hai tổ chức trên cùng một nền tảng quản lý dự án:

| Người dùng | Tenant | Vai trò | Quyền có hiệu lực |
|---|---|---|---|
| Lan | Minh An | Project Administrator | Quản trị dự án trong Minh An theo phạm vi được cấp |
| Lan | Bắc Hải | Project Reader | Đọc dự án trong Bắc Hải theo phạm vi được cấp |

Lan đăng nhập một lần nhưng không mang quyền quản trị Minh An sang Bắc Hải. Khi Lan chuyển workspace trên giao diện, hệ thống phải xác định lại quyền trong workspace đích.

Một phép kiểm tra như `user.hasRole("ADMIN")` thiếu thông tin quan trọng: admin của tenant nào, đối với loại tài nguyên nào và trong điều kiện nào? Nếu câu trả lời chỉ dựa vào tên vai trò, quyền của một khách hàng có thể bị sử dụng để tác động dữ liệu khách hàng khác.

Tenant-scoped role giúp mô hình RBAC thể hiện đúng ranh giới này. Nó không thay thế việc xác minh danh tính, kiểm tra quyền trên đối tượng hoặc cách ly dữ liệu; các cơ chế đó cần hoạt động cùng nhau.

## 2. Phân biệt định nghĩa vai trò và phép gán vai trò

Một **role definition** mô tả tập quyền. Một **role assignment** gắn định nghĩa đó với một chủ thể tại phạm vi cụ thể.

Ví dụ:

```text
Role definition:
  Project Reader -> project:read, document:read

Role assignment:
  principal=lan
  tenant=minh-an
  role=Project Reader
  scope=project/audit-2027
```

Tên `Project Reader` chưa tự cấp quyền cho Lan. Assignment mới là bằng chứng cho biết Lan có vai trò đó trong tenant Minh An và trong dự án `audit-2027`.

Mô hình có thể diễn đạt bằng bộ giá trị:

```text
assignment = (
  principal,
  tenant,
  roleDefinition,
  resourceScope,
  validity,
  conditions
)
```

Azure RBAC cũng phân biệt ba thành phần cốt lõi của phép gán vai trò: security principal, role definition và scope. Đây là ví dụ cho tư duy gắn quyền với phạm vi; cây scope của Azure không phải quy tắc mặc định cho tenant của mọi ứng dụng SaaS. [Microsoft Learn: Azure RBAC overview](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview).

Trong thực tế có hai cách sử dụng cụm từ tenant-scoped role:

- **Định nghĩa vai trò thuộc tenant:** tenant tự sở hữu role definition, chẳng hạn `custom-auditor` của Minh An.
- **Phép gán vai trò có phạm vi tenant:** cùng một mẫu vai trò được gán độc lập trong nhiều tenant.

Một hệ thống có thể sử dụng cả hai. Điều bắt buộc là quyết định truy cập luôn tìm được phạm vi tenant của quyền, kể cả khi định nghĩa vai trò xuất phát từ một catalog dùng chung.

## 3. Dùng chung mẫu vai trò nhưng không dùng chung quyền được cấp

Nền tảng có thể cung cấp các mẫu `Reader`, `Editor`, `Tenant Administrator` cho mọi khách hàng. Việc dùng chung mẫu giúp định nghĩa nhất quán, nhưng không có nghĩa assignment trở thành toàn nền tảng.

```text
Catalog dùng chung: Project Reader
          |
          +-- Assignment của Lan tại Minh An
          |
          +-- Assignment của Huy tại Bắc Hải
```

Một thiết kế khác là khởi tạo role definition riêng trong từng tenant từ mẫu chung. Khi đó, `role_id` của Minh An và Bắc Hải khác nhau dù cùng tên hiển thị.

| Thành phần | Có thể dùng chung? | Ràng buộc cần giữ |
|---|---|---|
| Mã permission như `document:read` | Có, nếu ngữ nghĩa được nền tảng định nghĩa thống nhất | Permission không tự mang tenant scope |
| Mẫu vai trò chuẩn | Có | Sửa mẫu cần có chính sách phiên bản và tác động rõ ràng |
| Role definition tùy chỉnh | Thường thuộc từng tenant | Tenant A không sửa role definition của B |
| Assignment của người dùng hoặc workload | Cần ràng buộc tenant cụ thể | Không suy từ assignment ở tenant khác |
| Vai trò quản trị nền tảng | Là phạm vi riêng | Không đồng nhất với tenant administrator |

Không dùng tên hiển thị làm khóa bảo mật. Hai khách hàng có thể cùng tạo vai trò `Auditor`, nhưng quyền và phạm vi khác nhau. Tra cứu theo `tenant_id` cùng định danh vai trò ổn định; nếu định nghĩa là toàn cục, phải có cách nhận diện rõ namespace toàn cục và quy tắc được phép gán.

Đối với custom role, tenant chỉ được chọn những permission mà nền tảng cho phép họ quản lý. Tạo một role mới không được trở thành cách cấp quyền nội bộ như vận hành toàn hệ thống, đọc bí mật nền tảng hoặc vượt ranh giới khách hàng.

## 4. Membership, role và resource scope là ba thông tin khác nhau

Membership trả lời “chủ thể có quan hệ hợp lệ với tenant không?”. Role trả lời “chủ thể được thực hiện những hành động nào?”. Resource scope trả lời “những hành động đó áp dụng trên tập tài nguyên nào?”.

Trong một mô hình yêu cầu membership, việc một người dùng thuộc tenant chưa tự cho phép họ đọc mọi dữ liệu. Ngược lại, assignment cũ không nên tiếp tục có hiệu lực khi membership đã bị đình chỉ hoặc chấm dứt.

```text
Tenant Minh An
  Membership của Lan: ACTIVE
  Assignment 1: Project Reader, scope=project-10
  Assignment 2: Project Editor, scope=project-20

Tenant Bắc Hải
  Membership của Lan: ACTIVE
  Assignment 3: Project Reader, scope=project-30
```

Lan được chỉnh sửa dự án 20 tại Minh An, nhưng không vì vậy được chỉnh sửa dự án 10 hoặc dự án 30.

Nếu ứng dụng hỗ trợ quyền được kế thừa từ tenant xuống project rồi document, quan hệ kế thừa phải được định nghĩa trong mô hình tài nguyên. Không áp dụng quy tắc chuỗi ký tự kiểu “scope bắt đầu bằng cùng tiền tố thì được phép”. ID hoặc đường dẫn có hình thức tương tự không chứng minh hai tài nguyên nằm trong cùng cây quyền.

Không kế thừa sang tenant anh em. Quyền tại tenant Minh An không bao phủ tenant Bắc Hải chỉ vì cả hai thuộc cùng một tập đoàn trên giao diện. Nếu tổ chức mẹ có quyền điều hành nhiều tenant, đó phải là quan hệ quản trị được mô hình hóa và phê duyệt riêng.

Trong mô hình chia sẻ với người ngoài, ứng dụng có thể dùng external principal hoặc grant thay vì membership thông thường. Dù chọn mô hình nào, role assignment vẫn phải ràng buộc với tenant tài nguyên và không được nhận quyền quản trị từ tổ chức nguồn một cách tự động.

## 5. Quyết định cho phép phải sử dụng cùng một assignment phù hợp

Với yêu cầu đọc tài liệu `doc-41` thuộc dự án `project-10` của Minh An, hệ thống cần kiểm tra:

1. Danh tính người gọi đã được xác minh và ánh xạ tới principal ổn định.
2. Tenant đích đang hoạt động và quan hệ của principal với tenant đáp ứng chính sách.
3. Tài liệu thực sự thuộc Minh An và dự án được xét.
4. Có ít nhất một assignment còn hiệu lực của principal tại Minh An mà role chứa `document:read` và scope bao phủ tài liệu đó.
5. Các điều kiện bổ sung và quy tắc từ chối bắt buộc đã được đáp ứng.

Có thể biểu diễn phần kiểm tra assignment như sau:

```text
exists assignment a:
    a.principal == verifiedPrincipal
    AND a.tenant == resource.tenant
    AND a.isActive(now)
    AND a.role.allows(requestedAction)
    AND a.scope.covers(resource)
    AND a.conditions.areSatisfied(context)
```

Các phép kiểm tra phải gắn với cùng assignment có liên quan. Một lỗi dễ gặp là lấy hợp tất cả permission ở mọi assignment, lấy hợp tất cả scope, rồi ghép chéo hai tập đó.

Ví dụ, Lan có `document:read` ở project 10 và `document:write` ở project 20. Không được lấy `document:write` từ assignment project 20 rồi ghép với scope project 10 để cho phép sửa tài liệu project 10.

Việc cộng gộp quyền từ nhiều vai trò có thể hợp lệ khi chính sách quy định, nhưng mỗi quyền hiệu lực vẫn phải có căn cứ về tenant, scope và điều kiện tương ứng. Nếu có explicit deny, giới hạn giấy phép hoặc chính sách ABAC, cách kết hợp phải được định nghĩa rõ; một vai trò cho phép không tự vô hiệu hóa mọi ràng buộc khác.

## 6. Mô hình dữ liệu giữ tenant trong các quan hệ

Một mô hình quan hệ đơn giản có thể tổ chức như sau. Đây là thiết kế minh họa, không phải schema bắt buộc của một sản phẩm IAM:

| Bảng | Trường chính có ý nghĩa | Ràng buộc cần có |
|---|---|---|
| `tenant_membership` | `tenant_id`, `principal_id`, `status` | Duy nhất cặp tenant và principal |
| `role_definition` | `tenant_id`, `role_id`, `role_key`, `status` | Role tùy chỉnh thuộc đúng tenant |
| `role_permission` | `tenant_id`, `role_id`, `permission` | Tham chiếu role bằng tenant và role ID |
| `role_assignment` | `assignment_id`, `tenant_id`, `principal_id`, `role_id`, `scope_type`, `scope_id`, trạng thái và thời hạn | Membership, role và scope phải thuộc đúng tenant |
| `project` | `tenant_id`, `project_id` | Duy nhất cặp tenant và project |
| `document` | `tenant_id`, `document_id`, `project_id` | Tham chiếu project bằng tenant và project ID |

Nếu chỉ dùng foreign key `role_id`, dữ liệu có thể vô tình liên kết assignment của A tới role definition của B. Khóa và foreign key có thành phần `tenant_id` giúp chặn kiểu liên kết sai này tại tầng dữ liệu.

Với `scope_type` và `scope_id` đa hình, một foreign key thông thường không tự xác minh được mọi loại scope. Có thể dùng bảng scope chuẩn hóa có tenant owner, bảng assignment riêng theo loại tài nguyên hoặc kiểm tra nghiệp vụ trong transaction. Không cho rằng việc thêm cột `tenant_id` đã tự bảo đảm toàn bộ tính nhất quán.

Trạng thái `ACTIVE`, thời hạn assignment, trạng thái role và trạng thái membership vẫn cần được kiểm tra khi đánh giá quyền. Foreign key bảo đảm liên kết tồn tại; nó không chứng minh liên kết đang được phép sử dụng.

Ví dụ truy vấn quyết định quyền dưới đây giả định role definition được khởi tạo riêng trong từng tenant, chỉ hỗ trợ scope TENANT và PROJECT, không có group hay kế thừa bổ sung:

```sql
SELECT EXISTS (
    SELECT 1
    FROM role_assignment a
    JOIN tenant_membership m
      ON m.tenant_id = a.tenant_id
     AND m.principal_id = a.principal_id
    JOIN role_definition r
      ON r.tenant_id = a.tenant_id
     AND r.role_id = a.role_id
    JOIN role_permission p
      ON p.tenant_id = r.tenant_id
     AND p.role_id = r.role_id
    JOIN document d
      ON d.tenant_id = a.tenant_id
    WHERE a.tenant_id = :verified_target_tenant
      AND a.principal_id = :verified_principal
      AND d.document_id = :document_id
      AND p.permission = :required_permission
      AND m.status = 'ACTIVE'
      AND r.status = 'ACTIVE'
      AND a.status = 'ACTIVE'
      AND (a.not_before IS NULL OR a.not_before <= :now)
      AND (a.expires_at IS NULL OR :now < a.expires_at)
      AND (
          (a.scope_type = 'TENANT' AND a.scope_id = a.tenant_id)
          OR
          (a.scope_type = 'PROJECT' AND a.scope_id = d.project_id)
      )
);
```

Các tham số phải được bind, không nối chuỗi SQL. `required_permission` do endpoint hoặc nghiệp vụ phía server xác định; client không được chọn một permission dễ hơn để vượt kiểm tra.

Truy vấn này chỉ minh họa phần RBAC theo các giả định đã nêu. Khi triển khai, phải kết hợp trạng thái tenant, điều kiện truy cập, deny policy và các quy tắc nghiệp vụ có liên quan. Tác vụ ghi dữ liệu cũng cần ràng buộc tenant trong chính câu lệnh ghi và xử lý thay đổi đồng thời phù hợp.

## 7. Backend cần mang tenant context xuyên suốt

Một đường xử lý có thể được mô tả bằng mã giả Java:

```java
DocumentView readDocument(
        VerifiedPrincipal principal,
        TenantId requestedTenant,
        DocumentId documentId) {

    // principal chỉ được tạo sau bước xác minh danh tính/token hợp lệ.
    Tenant tenant = tenants.requireActive(requestedTenant);
    Membership membership = memberships.requireActive(
            tenant.id(), principal.id());

    Document document = documents.findByTenantAndId(tenant.id(), documentId)
            .orElseThrow(NotFound::new);

    authorization.requireAllowed(
            principal,
            membership,
            tenant.id(),
            "document:read",
            document.resourceDescriptor());

    return document.toView();
}
```

Các kiểu và phương thức ở trên là thành phần minh họa. Điều quan trọng là `authorization` đánh giá assignment trong đúng tenant, trên đúng tài nguyên đã phân giải, chứ không chỉ kiểm tra tên vai trò ở principal.

Tenant từ URL, header hoặc lựa chọn trên giao diện chỉ thể hiện tenant mà client muốn truy cập. Backend phải kiểm tra quyền trong tenant đó. Nếu ứng dụng sử dụng tenant context do token hoặc phiên đã ràng buộc cung cấp, request phải nhất quán với ngữ cảnh đó theo hợp đồng của hệ thống; không âm thầm đổi tenant bằng header.

Các tầng sau cũng phải nhận cùng tenant context: repository, dịch vụ nội bộ, search index, object storage, export và audit. Không tìm tài liệu toàn cục bằng ID rồi quên đối chiếu tenant sở hữu.

Tài liệu AWS về tenant isolation nhấn mạnh rằng xác thực và quyền sử dụng chức năng chưa tự bảo đảm cách ly tenant; cần áp dụng tenant context để giới hạn tài nguyên được truy cập. Điều này giải thích vì sao role đúng vẫn cần truy vấn dữ liệu đúng tenant. [AWS: Tenant isolation](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html).

Nếu sử dụng row-level security hoặc tenant session ở database, phải quản lý cách thiết lập và dọn ngữ cảnh trên connection pool. Nếu dùng schema hoặc database riêng, bộ định tuyến dữ liệu cũng phải dựa trên tenant đã được xác minh quyền truy cập.

## 8. Token và cache không được làm mất phạm vi

Một claim như sau quá mơ hồ nếu ứng dụng phục vụ nhiều tenant:

```json
{
  "sub": "principal-93",
  "roles": ["ADMIN"]
}
```

Claim có thể có ý nghĩa trong một hợp đồng token cụ thể, nhưng ứng dụng không được tự suy rằng `ADMIN` có hiệu lực trên mọi tenant. Cần biết issuer đã được chấp nhận, audience, tenant hoặc ngữ cảnh mà role áp dụng và cách ánh xạ role sang quyền nội bộ.

Một payload minh họa có ràng buộc tenant có thể như sau:

```json
{
  "sub": "principal-93",
  "aud": "project-api",
  "app_tenant": "minh-an",
  "role_refs": ["role-reader-17"],
  "authorization_version": 12
}
```

`app_tenant`, `role_refs` và `authorization_version` là claim tùy chỉnh trong ví dụ, không phải chuẩn chung. Giải mã payload không chứng minh claim đáng tin; phải xác minh token theo cấu hình của API trước khi sử dụng. Version chỉ hỗ trợ phát hiện quyền cũ nếu backend thực sự so sánh với trạng thái hiện hành hoặc một cơ chế invalidation đáng tin cậy.

Không nhất thiết đưa toàn bộ vai trò của mọi tenant vào một token. Có thể cấp token theo tenant đang hoạt động hoặc dùng định danh chủ thể để backend tra cứu quyền. Lựa chọn cần phù hợp với kích thước token, hiệu năng, thời gian thu hồi và ranh giới tin cậy.

Một khóa cache quyết định quyền chỉ gồm `principalId + action` có thể tái sử dụng kết quả Minh An khi gọi Bắc Hải. Khóa cần phản ánh tenant đích, chủ thể, hành động, tài nguyên hoặc phạm vi và những phiên bản chính sách ảnh hưởng tới kết quả. Điều kiện theo thời gian, trạng thái hay ngữ cảnh cũng phải được xử lý; TTL dài không được kéo dài quyền quá thời hạn assignment.

Khi chuyển tenant, frontend cần làm mới trạng thái quyền và dữ liệu hiển thị. Backend vẫn phải kiểm tra độc lập. Ẩn nút Delete ở frontend không ngăn được lời gọi trực tiếp tới API Delete.

## 9. Quyền gán vai trò cũng phải có phạm vi

Quyền đọc tài liệu và quyền cấp vai trò là hai loại quyền khác nhau. Một `Tenant Administrator` chỉ nên quản trị những đối tượng và assignment trong tenant của mình theo chính sách nền tảng.

Đường gán vai trò cần kiểm tra tối thiểu:

1. Người thực hiện có quyền quản lý assignment tại tenant đích hay không.
2. Role được yêu cầu có thuộc tenant hoặc catalog được phép sử dụng tại tenant đó không.
3. Chủ thể nhận quyền có đủ điều kiện tham gia tenant theo mô hình đã chọn không.
4. Scope tồn tại, thuộc đúng tenant và nằm trong phạm vi được người thực hiện quản lý không.
5. Role có nằm trong tập được phép cấp hay đòi hỏi phê duyệt bổ sung không.

Không mặc định rằng ai có quyền `roles:assign` đều được cấp mọi role. Cần kiểm soát **tập vai trò được phép cấp**, đặc biệt với role quản trị bảo mật, quản lý credential, xuất dữ liệu hoặc ủy quyền tiếp.

Một nguyên tắc thường dùng là không cho người quản trị cấp quyền vượt phạm vi hoặc mức ủy quyền mà họ được phép phân phối. Tuy nhiên, quy tắc cụ thể có thể là allowlist role, quan hệ ủy quyền rõ ràng hoặc quy trình phê duyệt; không nên chỉ so sánh tên vai trò hay số thứ bậc tự đặt.

Quyền sửa nội dung role definition cũng nhạy cảm như quyền gán role. Nếu một người có thể thêm `tenant:admin` vào role mà chính họ đang giữ, họ có thể tự nâng quyền mà không tạo assignment mới. Vì thế, phải kiểm soát cả đường chỉnh role, ánh xạ permission và quản lý nhóm có assignment đặc quyền.

Phân biệt tài khoản quản trị khách hàng với quản trị nền tảng. Những thao tác hỗ trợ toàn hệ thống, nếu cần, nên có đường đặc quyền riêng, tenant đích rõ ràng, lý do, thời hạn và audit; không đặt một điều kiện `if admin then skip tenant checks` dùng chung cho mọi loại admin.

## 10. Nhóm, danh tính workload và vòng đời quyền

**Gán qua nhóm.** Assignment cho nhóm giảm số thao tác gán trực tiếp, nhưng quyền thay đổi thành viên nhóm cũng trở thành một đường cấp quyền. Nhóm phải có ngữ cảnh tenant hoặc ánh xạ tin cậy rõ ràng. Không sử dụng tên nhóm `Admins` từ mọi nhà cung cấp SSO như cùng một nhóm đặc quyền.

**Ánh xạ từ SSO.** Các claim nhóm hoặc role bên ngoài chỉ được ánh xạ qua cấu hình do bên có thẩm quyền quản lý. Nếu cho phép tenant tự cấu hình mapping, phạm vi tác động phải dừng trong tenant đó; không cho tenant A sửa mapping dùng để cấp quyền ở B.

**Danh tính workload.** Service account, service principal hoặc workload identity cũng cần assignment có tenant scope. Ứng dụng chạy nền cho nhiều khách hàng không được có quyền truy cập mọi tenant chỉ vì là một dịch vụ nội bộ. Cần có quyền tenant cụ thể hoặc một mô hình đặc quyền nền tảng được thiết kế rõ ràng.

**Thu hồi.** Khi membership bị đình chỉ, người dùng rời tổ chức, assignment hết hạn hoặc role bị vô hiệu hóa, quyền hiệu lực cần thay đổi theo chính sách đã định nghĩa. Phải xét cache, phiên, token cũ, job đang chờ và quyền gán qua nhóm; xóa một assignment trực tiếp chưa chắc đã thu hồi quyền nếu còn assignment tương đương từ nguồn khác.

**Thay đổi role.** Sửa role dùng bởi hàng nghìn thành viên có thể cấp thêm quyền hàng loạt. Cần xem trước ảnh hưởng, phân biệt thay đổi tăng và giảm quyền, lưu phiên bản, ghi người thay đổi và hỗ trợ khôi phục có kiểm soát. Nếu catalog vai trò dùng chung được cập nhật, phải biết tenant nhận thay đổi ngay hay theo cơ chế nâng phiên bản.

**Tác vụ nền.** Job cần mang tenant đích và căn cứ ủy quyền được thiết lập từ yêu cầu hợp lệ. Nếu nghiệp vụ yêu cầu quyền còn hiệu lực khi thực thi, worker phải kiểm tra lại membership và assignment khi chạy; không chỉ dùng kết quả kiểm tra lúc enqueue.

## 11. Kiểm toán và tình huống cần kiểm chứng

Sự kiện quản trị vai trò nên có tenant đích, actor, chủ thể nhận quyền, role ID, scope, thay đổi trước/sau, thời gian, lý do và request ID. Sự kiện quyết định quyền nên cho biết hành động, tài nguyên, kết quả cùng assignment hoặc policy làm căn cứ.

Không ghi raw token, mật khẩu hay khóa bí mật vào log. Quyền đọc log cũng cần phạm vi phù hợp, vì danh sách thành viên và role assignment có thể là dữ liệu nhạy cảm của khách hàng.

| Tình huống | Kết quả mong đợi |
|---|---|
| Lan là admin ở Minh An, reader ở Bắc Hải và xóa dữ liệu Bắc Hải | Từ chối nếu reader không có quyền xóa |
| Lan có role đúng nhưng membership Minh An đã bị đình chỉ | Từ chối theo chính sách membership |
| Assignment Minh An tham chiếu role tùy chỉnh Bắc Hải | Chặn dữ liệu không hợp lệ hoặc từ chối sử dụng |
| Hai tenant cùng có role tên `Auditor` | Tra cứu bằng định danh và tenant, không nhầm theo tên |
| Có quyền đọc ở project 10 và ghi ở project 20 | Không ghép thành quyền ghi project 10 |
| Client sửa tenant ID trên URL hoặc header | Đánh giá tenant đích và từ chối nếu không được phép |
| Tài liệu có ID trùng trong hai tenant | Chỉ lấy tài liệu thuộc tenant đã kiểm tra |
| Cache còn kết quả allow của tenant trước | Không dùng cho tenant mới |
| Người quản trị A gán role cho chủ thể tại B | Từ chối nếu không có thẩm quyền riêng tại B |
| Người giữ role sửa role đó để thêm quyền đặc biệt | Chặn hoặc yêu cầu quy trình phê duyệt phù hợp |
| Thu hồi assignment trực tiếp nhưng còn role qua nhóm | Quyền còn lại phải được nhận diện đúng, không báo thu hồi hoàn toàn sai |
| Assignment hết hạn trong lúc job chờ | Áp dụng chính sách kiểm tra lại khi thực thi |

Ngoài endpoint đọc danh sách, cần kiểm chứng lấy chi tiết, cập nhật, tìm kiếm, export, file download và các API quản trị role. Chỉ cần một đường thực thi bỏ tenant scope thì ranh giới vai trò có thể bị phá vỡ.

## 12. Điểm cần ghi nhớ

Một role name không đủ để quyết định quyền trong hệ thống multi-tenant. Cần biết chủ thể, tenant, role definition, resource scope, trạng thái và điều kiện của phép gán.

Mẫu vai trò có thể dùng chung, nhưng quyền hiệu lực phải gắn với tenant và tài nguyên tương ứng. Giữ sự ràng buộc đó trong dữ liệu, kiểm tra backend, token, cache, nhóm và tác vụ nền giúp một danh tính làm việc ở nhiều tổ chức mà quyền của tổ chức này không tràn sang tổ chức khác.
