# Chọn mô hình phân quyền phù hợp và tránh tạo quá nhiều role

## 1. Tình huống: vì sao số lượng role tăng mất kiểm soát?

Một hệ thống quản lý tài liệu bắt đầu với ba vai trò: **VIEWER**, **EDITOR**, **ADMIN**. Sau vài tháng, nghiệp vụ bổ sung “chỉ sửa tài liệu trong phòng ban của mình”, “không tự duyệt tài liệu đã tạo”, “chỉ được xuất dữ liệu thuộc khu vực được giao”, “quyền duyệt hết hạn sau 7 ngày”, và “quản trị viên chỉ quản lý tenant của họ”.

Một cách tiếp cận thiếu bền vững là tạo role mới cho mọi trường hợp:

- `EDITOR_SALES`, `EDITOR_HR`, `EDITOR_FINANCE`.
- `EDITOR_SALES_NORTH`, `EDITOR_SALES_SOUTH`.
- `APPROVER_SALES_PENDING`, `APPROVER_SALES_TEMP_7D`.
- `TENANT_A_ADMIN`, `TENANT_B_ADMIN`, v.v.

Danh sách role nhanh chóng khó hiểu: người dùng được gán nhiều role chồng lấn; tính năng mới đòi hỏi thêm role; một role cũ có thể vô tình cấp quá nhiều quyền; không ai chắc role nào đang thực sự cần thiết.

**Vấn đề gốc:** role vốn dùng để mô tả **trách nhiệm tương đối ổn định** lại bị biến thành nơi chứa mọi điều kiện biến động của tài nguyên, tổ chức, quan hệ và thời gian. Khi những điều kiện đó kết hợp, số biến thể role có thể tăng theo cấp số nhân.

Bài này hướng dẫn chọn **RBAC**, **ABAC**, **ReBAC** hoặc cách kết hợp hợp lý theo nhu cầu thật, giữ danh mục role gọn mà vẫn áp dụng nguyên tắc *least privilege*, kiểm tra quyền trên đối tượng và *deny by default*.

### Sau bài học, bạn cần làm được

1. Nhận ra lúc nào RBAC đủ tốt và lúc nào cần thuộc tính hoặc quan hệ.
2. Phân biệt role, permission, scope, resource relationship và policy condition.
3. Thiết kế role quanh trách nhiệm nghiệp vụ, không quanh từng bản ghi hoặc trạng thái tạm thời.
4. Ánh xạ mô hình vào Spring Security bằng `GrantedAuthority`, request/method security và policy theo đối tượng.
5. Có một quy trình giảm role dư thừa, kiểm thử quyền và kiểm soát thay đổi chính sách.

## 2. Tách đúng các khái niệm trước khi chọn mô hình

| Khái niệm | Ý nghĩa | Ví dụ | Không nên nhầm với |
| --- | --- | --- | --- |
| **Subject** | Người dùng, dịch vụ hoặc tác nhân yêu cầu | User `u42`, service `billing-worker` | Role |
| **Role** | Nhóm trách nhiệm hoặc chức danh truy cập tương đối ổn định | `DOCUMENT_EDITOR`, `PAYMENT_REVIEWER` | Từng điều kiện owner, thời gian hoặc một tài liệu cụ thể |
| **Permission/authority** | Hành động nghiệp vụ được hệ thống cho phép thử thực hiện | `document:read`, `document:edit`, `invoice:approve` | Quyền mặc nhiên trên mọi resource |
| **Resource** | Bản ghi hay đối tượng đích | Document `d72`, invoice `i05` | Endpoint hoặc action chung |
| **Scope** | Giới hạn nơi một quyền có hiệu lực | Tenant `alpha`, dự án `p9`, phòng ban `sales` | Một phần vĩnh viễn của tên role |
| **Relationship** | Quan hệ giữa chủ thể và tài nguyên | Owner, assigned reviewer, project member | Role toàn hệ thống |
| **Attribute** | Thuộc tính của subject/resource/environment | `status=DRAFT`, `region=APAC`, MFA đã xác nhận | Một role mới mỗi khi giá trị thay đổi |
| **Policy** | Quy tắc xét và kết hợp các đầu vào | Editor + cùng tenant + owner + tài liệu nháp | Danh sách role đơn thuần |

Ví dụ câu: “Alice được sửa tài liệu `d72` vì Alice có chức năng chỉnh sửa, là chủ sở hữu, cùng tenant, tài liệu chưa khóa và hệ thống không ở chế độ chỉ đọc” chứa nhiều chiều:

```text
Subject: Alice
Permission: document:edit
Role (nguồn cấp permission): DOCUMENT_EDITOR
Resource: document d72
Scope: tenant alpha
Relationship: Alice là owner của d72
Resource attribute: d72.status == DRAFT
Environment attribute: system.readOnly == false

ALLOW = đủ permission
        AND scope hợp lệ
        AND quan hệ phù hợp
        AND thuộc tính/ngữ cảnh phù hợp
```

Role hữu ích để nhóm các **permission** ổn định. Chính sách theo resource và context giải quyết các câu hỏi phụ thuộc dữ liệu cụ thể. Đây là lý do một người có thể có `document:edit` nhưng vẫn bị từ chối sửa tài liệu `d73`.

**Không suy quyền từ input do client tự khai.** `tenantId`, `ownerId`, `roles`, `isAdmin` trong request body/header không phải bằng chứng quyền truy cập. Chủ thể cần đến từ nguồn xác thực/ủy quyền đáng tin; thông tin tài nguyên cần đến từ persistence hoặc nguồn có thẩm quyền.

## 3. Các mô hình kiểm soát truy cập và trường hợp phù hợp

### 3.1. RBAC — Role-Based Access Control

**Ý tưởng:** cấp permission cho role, sau đó gán role cho chủ thể. Người dùng được phép dùng chức năng nhờ role của mình.

```text
Alice --has role--> DOCUMENT_EDITOR
DOCUMENT_EDITOR --grants--> document:read
DOCUMENT_EDITOR --grants--> document:edit
```

**Phù hợp khi:** nhóm trách nhiệm ổn định, quyền nghiệp vụ tương đối giống nhau giữa các thành viên cùng vai trò, ví dụ nhóm hỗ trợ có quyền xem ticket, bộ phận kế toán có quyền lập phiếu.

**Ưu điểm:** giải thích dễ, dễ review quyền theo chức năng, cấp/thu hồi quyền theo nhóm, ít điều kiện chạy thời gian thực.

**Giới hạn:** role `DOCUMENT_EDITOR` tự nó chưa biết tài liệu nào thuộc Alice, tenant nào, tài liệu đang `DRAFT` hay đã `APPROVED`. Nếu cố encode những chiều này thành tên role, xuất hiện *role explosion*. RBAC phù hợp để làm lớp quyền chức năng nhưng không đủ cho nhiều quyết định theo đối tượng.

**Khi dùng:** giữ role ít, tên nói lên công việc; mapping `role → permission` rõ ràng; dùng thêm policy khác cho tenant, owner, trạng thái.

### 3.2. ABAC — Attribute-Based Access Control

**Ý tưởng:** quyết định dựa trên thuộc tính của subject, resource, action và environment/context, ví dụ:

```text
ALLOW edit(document) WHEN
    user.enabled == true
    AND user.department == document.department
    AND document.status == DRAFT
    AND environment.readOnly == false
```

**Phù hợp khi:** quyền phụ thuộc trạng thái tài liệu, phân loại dữ liệu, ca trực, mức độ tin cậy phiên, khu vực, hạn xử lý hoặc điều kiện biến động thường xuyên.

**Ưu điểm:** giảm nhu cầu tạo role cho mọi tổ hợp; chính sách phản ánh quy tắc nghiệp vụ.

**Đổi lại:** chính sách có thể khó lý giải nếu quá nhiều thuộc tính; cần chuẩn hóa tên, nguồn dữ liệu, thời điểm cập nhật, thứ tự/ưu tiên quyết định và kiểm thử ma trận điều kiện. ABAC không có nghĩa là “nhét một biểu thức khổng lồ vào mỗi controller”.

### 3.3. ReBAC — Relationship-Based Access Control

**Ý tưởng:** dựa trên **quan hệ** giữa subject và resource, có thể trực tiếp hoặc qua nhóm/dự án.

```text
Alice --ownerOf--> document d72
Bob   --reviewerOf--> document d72
Carol --memberOf--> project p9
document d72 --belongsTo--> project p9
```

**Phù hợp khi:** chia sẻ tài liệu, cộng tác nhóm, quản lý dự án, cây thư mục, owner, người được giao duyệt, quyền kế thừa từ nhóm hoặc quan hệ nhiều tầng.

**Ưu điểm:** diễn đạt “ai được làm việc gì trên tài nguyên nào” tự nhiên hơn việc cấp thêm role cho từng tài liệu.

**Đổi lại:** cần lưu và truy vấn quan hệ, hiểu độ sâu/kế thừa và quy tắc thu hồi; tránh query nhiều vòng hoặc dữ liệu quan hệ stale. Với dữ liệu đa tenant, quan hệ không được vượt ranh giới tenant ngoài ý định của chính sách.

### 3.4. ACL — Access Control List trên từng đối tượng

**Ý tưởng:** đối tượng lưu/có bảng riêng thể hiện ai hoặc nhóm nào được quyền gì. Ví dụ `d72` có ACL `(alice, EDIT)`, `(team-review, READ)`.

**Phù hợp khi:** ứng dụng chia sẻ trực tiếp từng file/tài liệu với người dùng hoặc nhóm, số quyền ngoại lệ hữu hạn và cần hiển thị “shared with”.

**Đổi lại:** ACL lớn khó bảo trì, các bản ghi kế thừa/nhóm làm quyết định phức tạp, truy vấn danh sách phải lọc theo ACL. Không biến ACL thành role toàn hệ thống cho mỗi tài liệu.

ACL là **cách biểu diễn quyền theo đối tượng**; có thể kết hợp với ReBAC (quan hệ thành viên nhóm) và RBAC (permission chức năng).

### 3.5. Kết hợp nhiều mô hình — thường là lựa chọn thực dụng

Không có yêu cầu “chọn đúng một mô hình cho toàn ứng dụng”. Ví dụ:

- **RBAC:** `DOCUMENT_EDITOR` cấp `document:edit`.
- **Scope:** quyền chỉ áp dụng trong tenant mà người dùng là thành viên.
- **ReBAC:** người dùng phải là owner hoặc thành viên được giao.
- **ABAC:** tài liệu phải `DRAFT`, hệ thống không `readOnly`.
- **ACL (khi cần):** người dùng cụ thể được chia sẻ quyền đọc tài liệu.

```text
                    ┌────────────────────────┐
Yêu cầu ------------>│ Có quyền chức năng?     │
                    └───────────┬────────────┘
                                │ có
                    ┌───────────▼────────────┐
                    │ Đúng tenant/scope?      │
                    └───────────┬────────────┘
                                │ có
                    ┌───────────▼────────────┐
                    │ Đúng quan hệ với object?│
                    └───────────┬────────────┘
                                │ có
                    ┌───────────▼────────────┐
                    │ Thuộc tính/context OK? │
                    └───────────┬────────────┘
                                │ có
                              ALLOW

Tại bất kỳ bước nào không đạt/không xác minh được → DENY.
```

RBAC hỗ trợ câu hỏi “được dùng chức năng gì?”, ReBAC/ACL hỗ trợ “được dùng với object nào?”, ABAC hỗ trợ “trong điều kiện nào?”. Đây là cách tổ chức thường dễ duy trì hơn khi cố dùng role cho mọi biến thể.

## 4. Quyết định chọn mô hình bằng tiêu chí cụ thể

Đầu tiên viết **ma trận hành động và tài nguyên** của sản phẩm. Đừng chọn công nghệ policy trước khi mô tả quyền thực tế.

| Đặc điểm yêu cầu | Hướng tiếp cận | Lý do |
| --- | --- | --- |
| Ít nhóm người dùng, chức năng rõ ràng, ít ngoại lệ | RBAC đơn giản | Dễ quản trị và giải thích |
| Nhiều tenant/chi nhánh và cùng role ở nhiều nơi | RBAC **theo phạm vi** + điều kiện tenant | Tránh nhân role theo tenant |
| Quyền theo chủ sở hữu, assignee, nhóm cộng tác, cha/con | ReBAC hoặc ACL + RBAC cho chức năng | Quan hệ thuộc dữ liệu thay vì tên role |
| Quyền đổi theo trạng thái hồ sơ, phân loại, thời điểm, MFA | ABAC kết hợp quyền chức năng | Các điều kiện thường biến động |
| Chia sẻ người/nhóm cụ thể trên tài liệu | ACL hoặc mô hình ReBAC | Quyền cấp cho đối tượng cụ thể |
| Tổ chức có nhiều chức năng và nhiều ràng buộc nguồn dữ liệu | Hybrid RBAC + scope + ReBAC/ABAC | Tách quyền ổn định và quy tắc động |
| Chính sách phức tạp, nhiều sản phẩm/dịch vụ cùng dùng | Dịch vụ/engine policy dùng chung **khi thực sự cần** | Tăng nhất quán, nhưng có chi phí vận hành, độ trễ và phiên bản policy |

Không nên chuyển sang engine policy phức tạp chỉ vì số role bắt đầu tăng: trước hết xem nguyên nhân có phải đang đưa tenant, trạng thái, owner vào tên role hay không. Ngược lại, cũng không giữ RBAC thuần chỉ để đơn giản hóa khi nghiệp vụ bắt buộc kiểm tra từng đối tượng.

### Sáu câu hỏi chốt phương án

1. **Cái gì ổn định?** Trách nhiệm nghề nghiệp ổn định → role; trạng thái/quan hệ biến động → policy.
2. **Quyền áp dụng lên toàn hệ thống hay một phạm vi?** Role `ADMIN` có thể chỉ là `tenant admin`, không phải `global admin`.
3. **Ai là chủ sở hữu dữ liệu quyết định?** Identity service quản lý user/role; service nghiệp vụ biết owner, state, tenant của đối tượng.
4. **Thu hồi quyền cần nhanh đến đâu?** Role/ACL/quan hệ có thể nằm trong cache/JWT; độ trễ cập nhật ảnh hưởng bảo mật.
5. **Ai sẽ giải thích được kết quả?** Cần reason code và test cho từng policy; quá nhiều điều kiện ẩn tạo khó khăn audit.
6. **Quy mô truy vấn là bao nhiêu?** ReBAC/ACL trên hàng triệu đối tượng cần chiến lược truy vấn/bộ lọc có chỉ mục phù hợp.

## 5. Role explosion: nhận biết và xử lý đúng nguyên nhân

### 5.1. Role explosion xuất hiện như thế nào?

Giả sử tổ chức có:

- 4 phòng ban.
- 3 vùng hoạt động.
- 3 mức dữ liệu.
- 3 nhóm thao tác.

Nếu tạo một role cho **mỗi tổ hợp**, số biến thể có thể là `4 × 3 × 3 × 3 = 108` role, trước cả khi thêm trạng thái hồ sơ, owner, thời gian hoặc tenant. Khi thêm một chiều giá trị, số kết hợp tiếp tục nhân lên.

Không có quy luật “108 role luôn sai”: một số tổ chức lớn có nhiều vai trò thật. Dấu hiệu bất ổn là role khác nhau **chỉ vì một giá trị dữ liệu**, một tenant, một đối tượng hay một thời điểm hết hạn.

### 5.2. Dấu hiệu cảnh báo

- Role trùng gần hết permission: `EDITOR_NORTH` và `EDITOR_SOUTH` chỉ khác vùng.
- Tên role chứa ID tài liệu/tenant, ngày tháng, trạng thái `DRAFT/PENDING` hoặc tài khoản cá nhân.
- Mỗi yêu cầu ngoại lệ dẫn tới tạo role mới; gỡ role cũ có nguy cơ ảnh hưởng nhóm không rõ.
- User có hàng chục role để ghép quyền; kiểm toán không phân biệt được role nào tạo ra quyết định.
- Có role toàn quyền “tạm” mà không có thời hạn/giới hạn scope được kiểm chứng.
- API điều kiện hóa theo chuỗi tên role rải rác nhiều lớp thay vì kiểm tra permission/policy.
- Role mới xuất hiện thường xuyên hơn chức danh/trách nhiệm thực của tổ chức.

### 5.3. Tách các chiều thay vì nhân tổ hợp

**Thiết kế dễ phình to:**

```text
ROLE_EDITOR_TENANT_ALPHA_SALES_DRAFT
ROLE_EDITOR_TENANT_ALPHA_HR_DRAFT
ROLE_EDITOR_TENANT_BETA_SALES_DRAFT
ROLE_EDITOR_TENANT_BETA_HR_DRAFT
ROLE_EDITOR_TENANT_ALPHA_SALES_APPROVED
...
```

**Thiết kế phân tách:**

```text
Role: DOCUMENT_EDITOR
  └─ permission: document:edit

Membership/Scope:
  └─ user u42 thuộc tenant alpha, department sales

Resource:
  └─ d72.tenant = alpha
  └─ d72.department = sales
  └─ d72.owner = u42
  └─ d72.status = DRAFT

Policy:
  └─ canEdit = hasPermission("document:edit")
              AND sameTenant
              AND ownerOrAssignedEditor
              AND status == DRAFT
              AND NOT readOnly
```

Role được giữ ổn định khi tài liệu đổi trạng thái. Khi user chuyển phòng ban, chỉ cập nhật membership/scope phù hợp; khi document đổi owner hoặc status, không phải đổi role của user.

### 5.4. Dùng permission làm giao diện giữa role và ứng dụng

Không rải khắp code những đoạn như `if (role == "SALES_MANAGER_APAC")`. Thay vào đó, xây danh mục permission mô tả hành động nghiệp vụ:

| Permission | Ý nghĩa |
| --- | --- |
| `document:read` | Có thể yêu cầu đọc tài liệu thuộc phạm vi được phép |
| `document:edit` | Có thể yêu cầu sửa tài liệu hợp lệ |
| `document:approve` | Có thể tham gia quy trình duyệt tài liệu |
| `document:export` | Có thể xuất tài liệu trong phạm vi cho phép |
| `user:invite` | Có thể mời người dùng trong phạm vi quản trị |

Map role sang permission ở một nơi có chủ sở hữu rõ ràng. Điều kiện owner, tenant, status và MFA không phải permission riêng cho mọi tổ hợp.

**Một lưu ý:** đừng tạo permission cho từng ID (`document:d72:edit`) nếu nhu cầu chủ yếu là quyền trên đối tượng. Quan hệ/ACL thường biểu diễn tốt hơn. Chỉ tạo permission dạng có tham số khi kiến trúc policy có quy ước, cơ chế phân quyền và giới hạn số lượng phù hợp.

## 6. Thiết kế phân quyền bền vững cho tài liệu đa tenant

Giả sử ứng dụng có ba role tương đối ổn định:

| Role | Permission cơ sở | Ý nghĩa |
| --- | --- | --- |
| `VIEWER` | `document:read` | Được dùng chức năng xem |
| `EDITOR` | `document:read`, `document:edit` | Được dùng chức năng xem/sửa |
| `APPROVER` | `document:read`, `document:approve` | Được dùng chức năng xem/duyệt |

**Lưu ý:** các role trong bảng chỉ biểu diễn quyền chức năng. Chính sách theo đối tượng ví dụ:

- Cùng tenant là điều kiện nền tảng cho mọi thao tác.
- `READ`: người dùng là owner hoặc reviewer được giao.
- `EDIT`: người dùng là owner, tài liệu `DRAFT` và hệ thống không ở chế độ chỉ đọc.
- `APPROVE`: người dùng là reviewer được giao, **khác owner**, tài liệu `PENDING`, phiên đạt điều kiện MFA và hệ thống không ở chế độ chỉ đọc.
- Thiếu bất kỳ quyền hay thông tin tin cậy cần thiết nào: `DENY`.

### Ví dụ kiểm tra

| Tình huống | Permission chức năng | Scope/quan hệ/trạng thái | Quyết định |
| --- | --- | --- | --- |
| Alice có `EDITOR` sửa bản nháp do Alice sở hữu | Đạt | Cùng tenant, owner, `DRAFT` | **ALLOW** |
| Bob có `EDITOR` sửa bản nháp do Alice sở hữu | Đạt | Không phải owner | **DENY** |
| Alice có `VIEWER` sửa bản nháp do Alice sở hữu | Không đạt | Dù là owner | **DENY** |
| Ruth có `APPROVER` duyệt tài liệu `PENDING` được giao | Đạt | Cùng tenant, là reviewer, đã MFA | **ALLOW** |
| Ruth duyệt tài liệu đang `DRAFT` | Đạt | Sai trạng thái | **DENY** |
| Eve có `EDITOR` ở tenant khác muốn sửa | Đạt về loại quyền | Sai scope tenant | **DENY** |
| Alice sửa bản nháp của mình khi hệ thống chỉ đọc | Đạt | Context không cho ghi | **DENY** |

Chính sách này chỉ là ví dụ học tập, **không phải default Spring Security**. Một sản phẩm khác có thể cho phép người được chia sẻ quyền sửa hoặc role quản trị dự án có thể có ngoại lệ. Hãy xác định rõ quy tắc và test chính xác, thay vì ngầm hiểu tên role là toàn quyền.

### Đối với một người thuộc nhiều tenant

Không gán `ROLE_ADMIN_TENANT_1`, `ROLE_ADMIN_TENANT_2` cho từng tenant nếu số lượng tenant lớn. Lưu quyền/role dưới dạng **membership có scope**:

```text
user_id  tenant_id  role
u42      alpha      EDITOR
u42      beta       VIEWER
u43      alpha      APPROVER
```

Khi yêu cầu đến cho document `d72`, server xác minh membership của chủ thể trong `document.tenantId`, xác định quyền trong **đúng tenant đó**, rồi kiểm tra policy object. Chuyển “tenant đang chọn” trên UI **không** được tự cấp quyền tenant tương ứng. Với ứng dụng chỉ có một tenant/user, mô hình membership có thể đơn giản hơn; quan trọng là scope không bị nhập nhằng.

## 7. Java 17+ độc lập: ít role nhưng vẫn kiểm soát đúng đối tượng

Ví dụ sau cài đặt **ba role**, mỗi role gán permission ổn định. Quan hệ owner/reviewer, tenant, trạng thái và MFA được đánh giá riêng. Không cần tạo role cho từng chủ sở hữu hay trạng thái.

Tạo tệp `AccessModelDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class AccessModelDemo {

    enum Action { READ, EDIT, APPROVE }
    enum State { DRAFT, PENDING, APPROVED }
    enum Decision { ALLOW, DENY_PERMISSION, DENY_SCOPE, DENY_POLICY }

    static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.of(
            "VIEWER", Set.of("document:read"),
            "EDITOR", Set.of("document:read", "document:edit"),
            "APPROVER", Set.of("document:read", "document:approve")
    );

    record Subject(
            String userId,
            String tenantId,
            Set<String> roles,
            boolean active) {
        Subject {
            roles = roles == null ? Set.of() : Set.copyOf(roles);
        }
    }

    record Document(
            String id,
            String tenantId,
            String ownerId,
            String reviewerId,
            State state) {}

    record Context(boolean mfaVerified, boolean readOnly) {}

    static String requiredPermission(Action action) {
        return switch (action) {
            case READ -> "document:read";
            case EDIT -> "document:edit";
            case APPROVE -> "document:approve";
        };
    }

    static boolean hasPermission(Subject subject, String permission) {
        for (String role : subject.roles()) {
            Set<String> grants = ROLE_PERMISSIONS.get(role);
            if (grants != null && grants.contains(permission)) {
                return true;
            }
        }
        return false;
    }

    static Decision authorize(
            Subject subject, Document document, Action action, Context context) {
        if (subject == null || action == null || !subject.active()
                || subject.userId() == null) {
            return Decision.DENY_PERMISSION;
        }
        if (!hasPermission(subject, requiredPermission(action))) {
            return Decision.DENY_PERMISSION;
        }

        if (document == null || subject.tenantId() == null
                || !subject.tenantId().equals(document.tenantId())) {
            return Decision.DENY_SCOPE;
        }

        if (context == null || (context.readOnly() && action != Action.READ)) {
            return Decision.DENY_POLICY;
        }

        boolean owner = subject.userId().equals(document.ownerId());
        boolean reviewer = subject.userId().equals(document.reviewerId());

        boolean allowed = switch (action) {
            case READ -> owner || reviewer;
            case EDIT -> owner && document.state() == State.DRAFT;
            case APPROVE -> reviewer && !owner
                    && document.state() == State.PENDING
                    && context.mfaVerified();
        };

        return allowed ? Decision.ALLOW : Decision.DENY_POLICY;
    }

    public static void main(String[] args) {
        Subject alice = new Subject(
                "alice", "alpha", Set.of("EDITOR"), true);
        Subject bob = new Subject(
                "bob", "alpha", Set.of("APPROVER"), true);
        Subject guest = new Subject(
                "guest", "alpha", Set.of("VIEWER"), true);
        Subject eve = new Subject(
                "eve", "beta", Set.of("EDITOR"), true);

        Document draft = new Document(
                "d1", "alpha", "alice", "bob", State.DRAFT);
        Document pending = new Document(
                "d2", "alpha", "alice", "bob", State.PENDING);
        Document other = new Document(
                "d3", "alpha", "charlie", "bob", State.DRAFT);

        Context normal = new Context(false, false);
        Context mfa = new Context(true, false);
        Context readOnly = new Context(false, true);

        System.out.println("owner-edits-draft="
                + authorize(alice, draft, Action.EDIT, normal));
        System.out.println("editor-edits-other="
                + authorize(alice, other, Action.EDIT, normal));
        System.out.println("owner-edits-readonly="
                + authorize(alice, draft, Action.EDIT, readOnly));
        System.out.println("reviewer-approves-with-mfa="
                + authorize(bob, pending, Action.APPROVE, mfa));
        System.out.println("reviewer-approves-without-mfa="
                + authorize(bob, pending, Action.APPROVE, normal));
        System.out.println("reviewer-approves-draft="
                + authorize(bob, draft, Action.APPROVE, mfa));
        System.out.println("viewer-edits-draft="
                + authorize(guest, draft, Action.EDIT, normal));
        System.out.println("cross-tenant-edit="
                + authorize(eve, draft, Action.EDIT, normal));
        System.out.println("reviewer-reads-assigned="
                + authorize(bob, draft, Action.READ, normal));
        System.out.println("viewer-reads-unshared="
                + authorize(guest, draft, Action.READ, normal));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AccessModelDemo.java
java AccessModelDemo
```

Kết quả:

```text
owner-edits-draft=ALLOW
editor-edits-other=DENY_POLICY
owner-edits-readonly=DENY_POLICY
reviewer-approves-with-mfa=ALLOW
reviewer-approves-without-mfa=DENY_POLICY
reviewer-approves-draft=DENY_POLICY
viewer-edits-draft=DENY_PERMISSION
cross-tenant-edit=DENY_SCOPE
reviewer-reads-assigned=ALLOW
viewer-reads-unshared=DENY_POLICY
```

**Ý nghĩa:**

- Alice và Eve đều có role `EDITOR`, nhưng Eve bị từ chối vì khác tenant. Không cần hai role `EDITOR_ALPHA` và `EDITOR_BETA` cho ví dụ này.
- Alice chỉ sửa được tài liệu do Alice sở hữu và còn là bản nháp. Khi trạng thái tài liệu đổi, **không phải tạo role mới**.
- Bob có role `APPROVER` vẫn phải là reviewer được giao và đáp ứng MFA/trạng thái.
- Guest có `document:read` theo role nhưng không đọc được tài liệu chưa được chia sẻ hoặc giao cho mình.

Các mã `DENY_PERMISSION`, `DENY_SCOPE`, `DENY_POLICY` là **mã minh họa để học và audit**, không phải response code hay class sẵn có của Spring Security. Không cần trả chi tiết tài nguyên/quan hệ cho caller trái phép.

Ví dụ dùng một `tenantId` trên subject để giữ chương trình ngắn. Sản phẩm cho phép nhiều tenant phải giải quyết **membership theo từng tenant** từ nguồn tin cậy như mục 6. Role mapping `Map.of` là dữ liệu mẫu; trong hệ thống thực có thể được quản lý trong cấu hình hoặc kho quyền có kiểm soát thay đổi.

## 8. Tích hợp với Spring Security theo lớp trách nhiệm

### 8.1. Role và GrantedAuthority

Spring Security cung cấp `Authentication` và tập `GrantedAuthority`. Tùy cách cấp quyền, một role có thể được biểu diễn bằng authority `ROLE_EDITOR`, còn quyền chức năng là `document:edit`.

- `hasRole("EDITOR")` thường kiểm tra authority `ROLE_EDITOR` theo quy ước prefix mặc định.
- `hasAuthority("document:edit")` kiểm tra chính xác authority `document:edit`; Spring Security **không tự ánh xạ** role nghiệp vụ `EDITOR` sang permission này nếu ứng dụng chưa cấu hình mapping.

Với nhiều chức năng dùng chung một permission catalog, một phương án là giải quyết role/scoped membership ở tầng xác thực hoặc dịch vụ quyền, rồi tạo tập authorities tương ứng. Nhưng danh tính, membership và scope có thể thay đổi sau khi token được phát hành; các dữ liệu cần thu hồi nhanh phải có chiến lược kiểm tra hiệu lực cập nhật.

### 8.2. Lớp HTTP: chỉ cho phép gọi đúng chức năng

Đây là **mảnh cấu hình Spring MVC/Servlet**, không phải chương trình Java độc lập. Nó yêu cầu các import và lớp `@Configuration` phù hợp:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority("document:edit")
            .requestMatchers(HttpMethod.POST, "/api/documents/*/approve")
                .hasAuthority("document:approve")
            .anyRequest().denyAll()
    ).build();
}
```

Lớp này trả lời “có quyền gọi thao tác không?”. Nó **không biết** `document.ownerId`, `document.tenantId` hoặc `document.status` khi chưa có logic ứng dụng truy xuất tài nguyên và kiểm tra policy.

Với endpoint khác như danh sách, export, xóa, batch hoặc admin, phải định nghĩa matcher/chức năng tương ứng thay vì tưởng các quy tắc trên đã bảo vệ mọi route.

### 8.3. Lớp nghiệp vụ: kiểm tra đối tượng, quan hệ và thuộc tính

Bật method security bằng `@EnableMethodSecurity`. Có thể sử dụng bean policy với `@PreAuthorize`:

```java
// Đoạn minh họa bên trong Spring-managed @Service.
@PreAuthorize("hasAuthority('document:edit') and " +
        "@documentPolicy.canEdit(authentication, #documentId)")
public void editDocument(String documentId, EditDocumentCommand command) {
    documentRepository.update(documentId, command);
}
```

Ứng dụng phải tự định nghĩa `documentPolicy`, `EditDocumentCommand`, `documentRepository` và `canEdit`. Bean policy có trách nhiệm nhận subject đã xác thực, tải document từ nguồn dữ liệu tin cậy, xác minh tenant/membership, owner/trạng thái và các điều kiện runtime. Nếu nhiều đối tượng có chính sách khác nhau, mỗi use case phải gọi policy đúng với action.

**Các lưu ý triển khai:**

1. `#documentId` trong SpEL cần tên tham số khả dụng khi chạy (chẳng hạn biên dịch với `-parameters` hoặc cơ chế khai báo tên tham số tương ứng).
2. Method security dạng proxy có thể bị bỏ qua khi một method trong bean gọi trực tiếp method khác của chính nó (*self-invocation*). Chọn ranh giới service và bảo vệ cả đường gọi qua job/consumer, không chỉ controller.
3. Với thao tác ghi, cần xét khoảng thời gian giữa kiểm tra và cập nhật tài nguyên. Nếu trạng thái, owner hay quyền có thể đổi, phải dùng transaction, optimistic locking, predicate update hoặc khóa thích hợp.
4. Hãy cân nhắc query dữ liệu theo tenant và scope ngay từ nguồn, đặc biệt với danh sách/phân trang; không lọc trễ sau khi đã tính count hay serialize dữ liệu nhạy cảm.
5. **Deny by default:** không có authority, không có membership, thiếu dữ liệu hoặc rule không khớp đều phải chặn. Đừng tự chọn fallback “có đăng nhập thì cho”.

### 8.4. Khi cần policy engine riêng?

Một service nhỏ với vài chục quy tắc có thể đủ rõ ràng với các hàm Java và test. Khi nhiều ứng dụng cùng dùng chính sách, cần lưu phiên bản policy, giải thích quyết định và trao đổi dữ liệu đa dịch vụ, có thể cân nhắc tách **Policy Decision Point (PDP)** và **Policy Enforcement Point (PEP)**:

```text
PEP (controller/service/repository boundary)
  └── gửi Subject + Action + Resource + Context tới PDP
        └── PDP đánh giá policy đã được version hóa
              └── ALLOW / DENY (+ reason code nội bộ)
  └── PEP thực thi hoặc từ chối
```

Dù policy ở cùng JVM hay ở dịch vụ ngoài, **PEP vẫn phải chặn thực sự**; một lời gọi policy không được bỏ qua khi timeout/lỗi. Với dịch vụ PDP bên ngoài, cần cân nhắc latency, tính sẵn sàng, tính toàn vẹn thông tin truyền vào, cache và cách xử lý khi không thể lấy quyết định.

## 9. Kiểm soát role mà không đánh đổi bảo mật

### 9.1. Least privilege và separation of duties

Quyền chỉ nên đủ cho công việc hiện tại; role `EDITOR` không cần tự động có `document:delete`, `user:invite` hoặc `document:approve`.

Với nghiệp vụ nhạy cảm, **separation of duties (SoD)** yêu cầu một người không tự làm toàn bộ chu trình. Ví dụ người tạo chứng từ không được tự phê duyệt chính chứng từ đó. Có hai kiểu:

- **Static SoD:** hạn chế một user đồng thời sở hữu hai role xung đột khi chính sách tổ chức yêu cầu.
- **Dynamic SoD:** user có thể có nhiều năng lực nhưng không được duyệt một giao dịch do chính mình tạo. Đây là điều kiện quan hệ/resource ở thời điểm thực hiện, không chỉ là quy tắc role.

Việc tạo role `CREATOR_WHO_CANNOT_APPROVE_OWN` cho từng loại tài liệu thường làm role phình to; điều kiện “khác người tạo” nên thuộc policy nghiệp vụ.

### 9.2. Hierarchy và role composition: dùng có kiểm soát

Role hierarchy giúp cấp tập quyền bao hàm nhau: ví dụ `EDITOR` bao gồm quyền `VIEWER`. Điều này có thể giảm trùng lặp, nhưng nếu role cấp cao kế thừa mọi quyền một cách không kiểm soát, quy tắc least privilege và SoD dễ bị phá.

Chỉ tạo hierarchy khi quan hệ bao hàm thật sự ổn định. Tránh coi `ADMIN` là “có thể bỏ qua owner/tenant/state” nếu chưa có quy định được phê duyệt. Cần ghi rõ **scope của role** và ý nghĩa các permission kế thừa.

### 9.3. Ngoại lệ tạm thời và quyền khẩn cấp

Nếu một cá nhân cần quyền duyệt trong 2 ngày, tốt hơn là một **grant có scope + hạn hiệu lực + lý do + người phê duyệt** thay vì tạo role tên `APPROVER_TEMP_TWO_DAYS_USER42`. Chính sách phải kiểm tra hiệu lực hạn và thu hồi; audit phải thể hiện ai cấp quyền, thời gian và phạm vi.

Quyền “break glass” cho tình huống khẩn cấp cần chính sách đặc biệt, xác thực tăng cường và audit rõ. Không dùng một role admin không giới hạn như giải pháp mặc định.

### 9.4. Revocation, cache và token

Nếu role/permission nằm trong JWT sống lâu, việc gỡ role ở server không nhất thiết làm token đang còn hiệu lực lập tức mất quyền. Tương tự, kết quả policy cache có thể tiếp tục `ALLOW` sau khi tài liệu đổi owner.

Hãy quyết định trước yêu cầu **độ trễ thu hồi** của từng quyền. Có thể dùng token ngắn hạn, tra cứu membership mới, cơ chế invalidation/version, cache TTL phù hợp hoặc kiểm tra trạng thái tại thời điểm thực thi đối với tác vụ nhạy cảm. Đây là lựa chọn kiến trúc theo mức rủi ro; không có một TTL “an toàn cho mọi hệ thống”.

### 9.5. Giải thích và kiểm toán chính sách

Cần có khả năng truy vết:

- Subject, action, resource ID, tenant/scope và kết quả.
- Permission nào cho phép/không cho phép sử dụng chức năng.
- Rule nào trong policy quyết định `ALLOW`/`DENY`; version policy.
- Thông tin thu hồi, thay đổi membership/ACL, cấp ngoại lệ và người phê duyệt.

Hạn chế đưa access token, PII không cần thiết hoặc nội dung tài liệu vào log. Thông báo lỗi cho caller có thể là `403` hoặc `404` theo API contract, nhưng lý do nội bộ không nên tự động bị lộ ra ngoài.

## 10. Quy trình giảm role explosion trong dự án hiện có

Thay role cũ cần kiểm soát để không vô tình thu hồi quyền hợp lệ hoặc mở quyền trái phép. Một quy trình có thể áp dụng:

1. **Kiểm kê:** liệt kê role thực tế, permission, nơi kiểm tra, tần suất sử dụng và người sở hữu mỗi role. Xác định tên role chỉ khác tenant, dự án, vùng, owner, trạng thái hoặc thời hạn.
2. **Định nghĩa nghiệp vụ:** ghi các action/resource, ai được thực hiện trong điều kiện nào. Viết thành ma trận quyền trước khi thay code.
3. **Tách permission:** gom các hành động ổn định như `document:edit`, `document:approve`; giữ các role phản ánh trách nhiệm thực sự.
4. **Tách scope/relationship/attribute:** chuyển tenant membership, owner, reviewer, trạng thái, MFA sang policy/nguồn dữ liệu phù hợp.
5. **Kiểm tra quyền cũ:** đánh giá từng trường hợp được phép và bị từ chối; xác định những trường hợp role cũ đã vô tình cấp thừa quyền.
6. **Thử song song bằng dữ liệu an toàn:** có thể chạy đánh giá chính sách mới ở chế độ quan sát (shadow evaluation) khi phù hợp để so sánh quyết định mà không dùng kết quả shadow để cho phép truy cập. Tránh ghi dữ liệu nhạy cảm vào log.
7. **Chuyển đổi có kiểm soát:** cập nhật ánh xạ role → permission và các điểm enforcement theo phạm vi rõ ràng; bảo đảm endpoint, service, batch và background job tuân cùng policy.
8. **Dọn role dư:** chỉ loại bỏ role cũ sau khi các tài khoản đã được chuyển và test/hậu kiểm đạt; theo dõi tỷ lệ `DENY` bất thường và audit.
9. **Thiết lập quản trị lâu dài:** một người/nhóm chịu trách nhiệm danh mục permission, review định kỳ các role không dùng, owner cho từng chính sách và quy trình thay đổi có version.

**Điểm quyết định:** giảm số role không phải mục đích riêng rẽ. Mục tiêu là **mô hình dễ hiểu, đúng quyền và dễ thay đổi**. Một hệ thống có 20 role được thiết kế rõ ràng có thể tốt hơn hệ thống ép xuống 3 role nhưng mỗi endpoint chứa một tập exception không thể kiểm thử.

## 11. Kiểm thử mô hình đã chọn

### 11.1. Ma trận kiểm thử quyền

| Ca thử | Permission chức năng | Scope/quan hệ/thuộc tính | Kỳ vọng |
| --- | --- | --- | --- |
| Editor sửa tài liệu nháp của mình, đúng tenant | Có | Đạt | `ALLOW` |
| Editor sửa tài liệu nháp người khác | Có | Không phải owner | `DENY` |
| Viewer sửa tài liệu nháp do chính mình sở hữu | Không có quyền sửa | Đạt về owner | `DENY` |
| Editor sửa tài liệu khác tenant | Có | Sai tenant | `DENY` |
| Editor sửa tài liệu đã duyệt | Có | Sai trạng thái | `DENY` |
| Approver được giao duyệt bản `PENDING`, đã MFA | Có | Đạt | `ALLOW` |
| Approver được giao nhưng thiếu MFA | Có | Thiếu điều kiện context | `DENY` |
| User không còn active / membership bị thu hồi | Không còn hiệu lực | Bất kỳ | `DENY` |
| Resource không tồn tại/không tải được | Có thể có | Không xác minh được | Từ chối theo API contract |
| Role không được hệ thống nhận diện | Không | Bất kỳ | `DENY` |

Ngoài unit test cho policy, nên có integration test cho request filter/method interceptor và đường đi thực thi service. Đặc biệt test phân trang/tổng bản ghi của API danh sách, tác vụ batch, thay đổi owner/trạng thái trong lúc xử lý, invalidation khi thu hồi quyền và self-invocation trong môi trường dùng Spring AOP.

### 11.2. Câu hỏi tự kiểm tra

1. **Doanh nghiệp thêm một tenant mới, có cần tạo role `EDITOR_NEW_TENANT` không?** Thường không. Nếu trách nhiệm biên tập không đổi, giữ `EDITOR` và kiểm soát membership/scope tenant.
2. **Hai người cùng role `EDITOR`, một người được sửa tài liệu còn người kia bị từ chối. Có mâu thuẫn không?** Không. Role cho permission thao tác; quyết định theo resource còn phụ thuộc owner, tenant, trạng thái và context.
3. **Quy tắc “người tạo không được tự duyệt” phù hợp đặt ở đâu?** Trong policy xét quan hệ giữa chủ thể và tài liệu/giao dịch, với permission duyệt được kiểm tra riêng.
4. **RBAC có vô ích nếu dự án dùng ABAC không?** Không. RBAC có thể giữ lớp quyền chức năng ổn định, còn ABAC xử lý điều kiện động.
5. **Có nên cache vĩnh viễn `ALLOW` cho `document:edit` không?** Không. Kết quả có thể phụ thuộc trạng thái tài liệu, quan hệ, membership và quyền đã được thu hồi.

**Ghi nhớ:** Hãy dùng **role** cho trách nhiệm tương đối ổn định, **permission** cho hành động, **scope** cho phạm vi, **quan hệ/thuộc tính** cho điều kiện của từng đối tượng, và **policy** để kết hợp. Một hệ thống quyền tốt giúp trả lời được “ai được làm gì trên đối tượng nào, trong điều kiện nào, vì sao” mà không phải tạo một role mới cho mỗi trường hợp.

## Tài liệu tham khảo

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- NIST RBAC Project: https://csrc.nist.gov/projects/role-based-access-control
