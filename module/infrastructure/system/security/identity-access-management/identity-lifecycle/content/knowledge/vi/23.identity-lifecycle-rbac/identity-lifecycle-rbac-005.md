# Role hierarchy trong RBAC: kế thừa vai trò và kiểm soát quyền theo vòng đời danh tính

**Role hierarchy** (hệ phân cấp vai trò) là khả năng trong **Role-Based Access Control (RBAC)** cho phép một vai trò **cấp trên** (*senior role*) kế thừa các quyền được gán cho vai trò **cấp dưới** (*junior role*). Nhờ đó, tổ chức có thể xây dựng nhiều tầng quyền dùng chung thay vì lặp lại mọi permission ở từng role.

Ví dụ, ứng dụng quản lý báo cáo có role `ReportReader` được phép xem báo cáo, `ReportEditor` được phép chỉnh sửa và kế thừa quyền đọc từ `ReportReader`. Nếu người dùng được gán `ReportEditor`, họ nhận quyền đọc một cách **gián tiếp** qua role hierarchy, dù không có bản ghi cấp `ReportReader` trực tiếp.

Đây là một công cụ thiết kế quan trọng nhưng cũng là nguồn rủi ro. **Một cạnh kế thừa sai có thể mở rộng quyền cho mọi người đang giữ vai trò cấp trên**, kể cả các account không có yêu cầu nghiệp vụ cho quyền mới. Với những quyền nhạy cảm, hierarchy còn có thể gây xung đột **Segregation of Duties (SoD)**, ảnh hưởng đến **least privilege**, và khiến quy trình **Mover/Leaver** tưởng đã thu hồi một role nhưng quyền vẫn còn qua đường kế thừa khác.

Bài thuộc chương **RBAC** của module **quản lý vòng đời danh tính IAM (Identity and Access Management)** theo mô hình **Joiner–Mover–Leaver (JML)**. Nội dung kết nối **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**. Sau bài, người học cần phân biệt **gán role**, **kế thừa permission**, **group membership** và **effective access**; đọc/thiết kế đồ thị role; kiểm tra SoD và xác minh thu hồi quyền trên ứng dụng đích.

> **Điểm cốt lõi:** Trong RBAC, cấp trên/cấp dưới nói về **quan hệ kế thừa quyền**, **không nhất thiết** nói về cấp bậc nhân sự, quản lý trực tiếp hay sơ đồ tổ chức. Muốn biết người dùng thật sự được làm gì, phải xét **tất cả đường cấp quyền và các điều kiện chính sách**.

## 1. Các thành phần nền tảng của RBAC

Trong mô hình RBAC, các khái niệm chủ yếu gồm:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **User / subject** | Danh tính hoặc account được gán role. | `person-2048`, `erp-user-9008`. |
| **Role** | Tập trách nhiệm/quyền được tổ chức thành một đơn vị quản trị. | `ReportReader`, `ReportEditor`. |
| **Permission** | Quyền thực hiện một thao tác trên tài nguyên theo mô hình ứng dụng. | `report:read`, `report:update`. |
| **User–Role Assignment (UA)** | Quan hệ gán một user vào role. | Lan → `ReportEditor`. |
| **Permission–Role Assignment (PA)** | Quan hệ gán permission trực tiếp cho role. | `report:update` → `ReportEditor`. |
| **Role hierarchy (RH)** | Quan hệ kế thừa giữa role senior và junior. | `ReportEditor` ≥ `ReportReader`. |
| **Session / active roles** | Những role đang được kích hoạt cho một phiên theo mô hình/chính sách triển khai. | Một phiên chỉ kích hoạt vai trò được phép. |
| **Effective permissions** | Tập quyền thực tế sau khi xét role trực tiếp, kế thừa và các điều kiện thực thi. | Lan có `report:read` và `report:update`. |

**Một role không đồng nhất với account, group, chức danh hoặc phòng ban.** `Finance Analyst` là một business role nếu được quản trị theo nghiệp vụ; `ERP_REPORT_READ` có thể là technical role bên trong ERP; `Finance Department` thường là một thuộc tính tổ chức. Hệ thống IAM có thể liên kết chúng nhưng không nên coi là một kiểu dữ liệu duy nhất.

### 1.1. Role trực tiếp và permission kế thừa

Giả sử:

~~~text
PA(ReportReader) = {report:read}
PA(ReportEditor) = {report:update}
ReportEditor >= ReportReader

UA(Lan) = {ReportEditor}
~~~

Quyền effective của `ReportEditor` theo hierarchy này:

~~~text
Perm(ReportEditor) = PA(ReportEditor) ∪ PA(ReportReader)
                   = {report:update, report:read}
~~~

Lan không cần một UA trực tiếp với `ReportReader` để được đọc báo cáo qua hierarchy. Vì vậy, khi kiểm toán, câu hỏi **“Lan được gán role nào?”** và **“Lan có quyền nào?”** có thể có câu trả lời khác.

### 1.2. Permission là gì trong triển khai thực tế?

Permission có thể là một cặp **operation–object**, một entitlement, scope tài nguyên, thao tác API hoặc chức năng UI được bảo vệ phía server. Ví dụ:

- `report:read` — xem báo cáo thuộc phạm vi được duyệt.
- `report:update` — chỉnh sửa báo cáo.
- `payment:create` — tạo lệnh thanh toán.
- `payment:approve` — phê duyệt thanh toán.
- `user:manage` — quản trị user/role trong ứng dụng.

**Permission name chỉ là nhãn** nếu không gắn với enforcement thực tế. Một nút UI bị ẩn không bảo đảm API phía sau từ chối thao tác. Khi hierarchy làm kế thừa permission, ứng dụng phải kiểm tra quyền tại tài nguyên/hành động cần bảo vệ.

## 2. Ngữ nghĩa senior role và junior role

Trong role hierarchy, ký hiệu:

~~~text
Senior >= Junior
~~~

được hiểu là **Senior kế thừa các permission của Junior**. Nếu:

~~~text
PlatformAdmin >= PlatformOperator
PlatformOperator >= PlatformViewer
~~~

thì `PlatformAdmin` kế thừa permission của cả `PlatformOperator` và `PlatformViewer` thông qua quan hệ **bắc cầu**.

~~~mermaid
flowchart TD
    A["PlatformAdmin (senior)"] -->|inherits| O["PlatformOperator"]
    O -->|inherits| V["PlatformViewer (junior)"]
    V --> PR["read metrics / inspect status"]
    O --> PO["operate approved workloads"]
    A --> PA["manage platform settings"]
~~~

**Cách đọc mũi tên:** role phía trên **nhận permission** của role phía dưới; đây **không** phải mũi tên quản lý nhân sự.

### 2.1. Những thuộc tính toán học hữu ích

RBAC role hierarchy thường được mô hình bằng **quan hệ thứ tự bộ phận** (*partial order*) trên tập role:

| Thuộc tính | Diễn giải | Tác dụng |
| --- | --- | --- |
| **Phản xạ (reflexive)** | Một role được xem là bao gồm chính nó. | `R ≥ R`. |
| **Phản đối xứng (antisymmetric)** | Nếu `A ≥ B` và `B ≥ A` thì chúng không phải hai role độc lập theo thứ tự bộ phận. | Tránh chu trình làm mất phân biệt vai trò. |
| **Bắc cầu (transitive)** | Nếu `A ≥ B` và `B ≥ C` thì `A ≥ C`. | Quyền thừa hưởng qua nhiều tầng. |

Một tập cạnh trực tiếp thường được biểu diễn bằng **Directed Acyclic Graph (DAG)**. Khi dựng đồ thị dữ liệu, **không thêm chu trình** `A → B → C → A`. Chu trình có thể làm đồng nhất permission của nhiều vai trò, gây lỗi truy vấn hoặc phát sinh quyền không dự kiến.

**Vai trò senior/junior là về quyền**, không có nghĩa một role junior luôn “được phép kích hoạt” trong phiên của user có senior theo mọi sản phẩm. Các triển khai khác nhau có ngữ nghĩa **role authorization** và **role activation** riêng, phải kiểm tra chính sách session và đặc tả ứng dụng.

### 2.2. Phân cấp tổng quát và phân cấp hạn chế

- **General role hierarchy:** một role có thể kế thừa nhiều role, và một role có thể được kế thừa bởi nhiều role khác — hỗ trợ **multiple inheritance**.
- **Limited role hierarchy:** hạn chế cách kết nối, thường gần dạng cây để đơn giản hóa quản trị và tránh nhiều đường kế thừa.

**General hierarchy** linh hoạt hơn nhưng khó phân tích hơn: một permission có thể đến qua nhiều đường. **Limited hierarchy** dễ đọc nhưng có thể tạo nhiều role trùng lặp hoặc buộc thiết kế cứng hơn. Chọn theo khả năng engine, tính minh bạch, quy mô và yêu cầu SoD.

### 2.3. Role hierarchy không phải org chart

Sơ đồ tổ chức có thể là:

~~~text
Finance Director
    |
Finance Manager
    |
Finance Analyst
~~~

Không thể tự suy ra:

~~~text
FinanceDirector >= FinanceManager >= FinanceAnalyst
~~~

Tại sao? Director có thể có quyền xem tổng hợp hoặc phê duyệt, **không nên kế thừa quyền tự tạo giao dịch** của Analyst nếu điều đó vi phạm SoD. Role hierarchy chỉ được thêm sau khi **business owner xác nhận quan hệ tập quyền hợp lệ**.

## 3. Đồ thị kế thừa đơn và kế thừa nhiều nhánh

### 3.1. Kế thừa dạng chuỗi

Ví dụ hệ thống quản lý tri thức:

| Role | Permission gán trực tiếp | Permission effective |
| --- | --- | --- |
| `KnowledgeViewer` | `article:read` | `article:read` |
| `KnowledgeContributor` | `article:create` | `article:create` + `article:read` |
| `KnowledgePublisher` | `article:publish` | `article:publish` + `article:create` + `article:read` |

Khi có quan hệ:

~~~text
KnowledgePublisher >= KnowledgeContributor
KnowledgeContributor >= KnowledgeViewer
~~~

ta có thể không cần gán `article:read` lặp lại cho `KnowledgePublisher`. Nhưng nếu policy yêu cầu người duyệt **không được tự soạn rồi duyệt**, hierarchy trên có thể **không phù hợp** do SoD; cần tách role hoặc ràng buộc phiên/quy trình.

### 3.2. Multiple inheritance

Trong môi trường kỹ thuật, một role có thể thừa hưởng từ nhiều role:

~~~mermaid
flowchart TD
    L["ReleaseCoordinator"] --> D["DeployViewer"]
    L --> C["ChangeTicketReviewer"]
    D --> DP["deployment:read"]
    C --> CP["change-ticket:read"]
    L --> LP["release:coordinate"]
~~~

Nếu:

~~~text
PA(DeployViewer)        = {deployment:read}
PA(ChangeTicketReviewer)= {change-ticket:read}
PA(ReleaseCoordinator)  = {release:coordinate}
~~~

thì:

~~~text
Perm(ReleaseCoordinator)
  = {deployment:read, change-ticket:read, release:coordinate}
~~~

**Không phải mọi cặp vai trò đều so sánh được.** `DeployViewer` và `ChangeTicketReviewer` là hai vai trò **không có quan hệ kế thừa với nhau**; đó là thuộc tính bình thường của partial order.

### 3.3. Quyền có thể đến từ nhiều đường

~~~mermaid
flowchart TD
    A["OpsLead"] --> B["ProductionViewer"]
    A --> C["IncidentResponder"]
    B --> P["logs:read"]
    C --> P
    C --> R["incident:acknowledge"]
~~~

Một permission như `logs:read` có thể đến từ hai nhánh. Nếu xóa cạnh `OpsLead >= ProductionViewer`, `OpsLead` **vẫn có `logs:read` qua `IncidentResponder`**. Vì thế **thu hồi một cạnh kế thừa không tự chứng minh một permission đã mất**. Phải tính lại toàn bộ đường quyền.

### 3.4. Tránh kế thừa ngược chiều

Giả sử role viewer chỉ đọc báo cáo, còn editor cần quyền sửa. Quan hệ hợp lý có thể là:

~~~text
ReportEditor >= ReportViewer
~~~

Quan hệ ngược:

~~~text
ReportViewer >= ReportEditor
~~~

sẽ khiến người xem cũng có quyền sửa — một ví dụ đơn giản của **privilege escalation do thiết kế hierarchy sai**, không phải do một người bị cấp role admin trực tiếp.

## 4. Cách tính effective permissions

Với một role `r`:
- `DirectPerm(r)` là permission gán trực tiếp vào role.
- `JuniorClosure(r)` là tập gồm `r` và mọi role junior đi tới được qua các cạnh kế thừa.
- `EffectivePerm(r)` là **hợp** permission gán cho mọi role trong closure.

~~~text
EffectivePerm(r) = union(DirectPerm(j) for j in JuniorClosure(r))
~~~

Với một user được gán các role trực tiếp:

~~~text
EffectivePerm(user) =
    union(EffectivePerm(r) for r in AssignedRoles(user))
~~~

Đây là **mô hình RBAC cấp quyền cơ bản**. Trong hệ thống thực, **active roles**, SoD, điều kiện tài nguyên/đơn vị, thời hạn, trạng thái account, chính sách deny hoặc ABAC có thể tiếp tục giới hạn quyền effective được thực thi. **Không lấy phép hợp permission làm toàn bộ quyết định ALLOW cho mọi ứng dụng.**

### 4.1. Ví dụ dữ liệu policy minh họa

~~~yaml
roleDefinitions:
  ReportViewer:
    directPermissions:
      - report:read

  ReportEditor:
    inherits:
      - ReportViewer
    directPermissions:
      - report:update

  AuditViewer:
    directPermissions:
      - audit:read

  FinancePowerUser:
    inherits:
      - ReportEditor
      - AuditViewer
    directPermissions:
      - export:restricted

assignments:
  person-2048:
    roles:
      - FinancePowerUser

scopePolicy:
  department: Finance
  environment: production
~~~

Đây là **schema YAML minh họa do tổ chức tự định nghĩa**, không phải định dạng chuẩn của SCIM, OIDC hay một sản phẩm IAM cụ thể. Với mô hình trên:

~~~text
FinancePowerUser inherits:
  ReportEditor -> ReportViewer
  AuditViewer

Effective permissions:
  report:read
  report:update
  audit:read
  export:restricted
~~~

Tuy nhiên, `department: Finance` hay `environment: production` chỉ có tác dụng **nếu PDP/ứng dụng thực sự thực thi điều kiện tương ứng**. Không tự nghĩ rằng một dòng YAML metadata sẽ làm quyền tự bị giới hạn.

### 4.2. Pseudocode tính closure và phát hiện chu trình

~~~text
function effectivePermissions(role, roleGraph, directPermissions):
    visited = set()
    visiting = set()
    resultPermissions = set()

    function visit(current):
        if current in visiting:
            throw InvalidRoleHierarchyCycle(current)

        if current in visited:
            return

        visiting.add(current)
        for each junior in roleGraph.juniorsOf(current):
            visit(junior)

        visiting.remove(current)
        visited.add(current)

        for each permission in directPermissions[current]:
            resultPermissions.add(permission)

    visit(role)
    return resultPermissions
~~~

Ý tưởng này duyệt đồ thị theo hướng **senior → junior**; dùng `visiting` để phát hiện chu trình trên đường đệ quy và `visited` để tránh tính lặp lại. Mỗi permission được hợp vào một tập nên không bị nhân đôi khi có multiple inheritance.

**Đây chỉ là pseudocode**, chưa gồm mọi yêu cầu production: kiểm soát tenant, version policy, phân trang role, cache, thay đổi đồng thời, giới hạn độ sâu, role activation, SoD, deny policy, thuộc tính ABAC, thời gian và audit. Không dùng trực tiếp như authorization engine cho ứng dụng nhạy cảm.

### 4.3. Caching effective permissions

Khi số lượng role hoặc user lớn, hệ thống có thể cache closure hoặc tập effective permissions. Cần thiết kế rõ:
- **Cache key** gồm tenant, role-policy version, graph version và scope áp dụng.
- Invalidation khi thêm/xóa cạnh hierarchy, đổi permission hoặc assignment.
- Cách giảm độ trễ giữa chính sách mới và token/session/role cache cũ.
- Cách xử lý lỗi cache hoặc nguồn graph không sẵn sàng.
- Cách chứng minh **readback actual access** sau thu hồi.

Đặc biệt với Leaver hoặc thu hồi role admin, **đợi cache hết hạn theo mặc định có thể để lại quyền tồn dư không được phép**. Cần cơ chế revocation/check policy phù hợp rủi ro và ứng dụng.

## 5. Role hierarchy và nguyên tắc least privilege

**Least privilege** đòi hỏi một chủ thể chỉ nhận những quyền cần thiết cho nhiệm vụ và khoảng thời gian hợp lệ. Hierarchy có thể giúp tập trung quyền phổ biến, nhưng cũng có thể mở rộng quyền quá mức.

### 5.1. Kế thừa có thể làm thừa quyền

Giả sử một role `FinanceManager` nhận:

~~~text
FinanceManager >= FinanceAnalyst
FinanceManager >= PaymentApprover
~~~

Trong khi:
- `FinanceAnalyst` có `payment:create`.
- `PaymentApprover` có `payment:approve`.

Nếu chính sách SoD cấm một người vừa tạo vừa duyệt thanh toán, hierarchy này **làm phát sinh tổ hợp quyền xung đột**, dù người đó chỉ được gán **một** role trực tiếp là `FinanceManager`.

**Không giải quyết bằng cách nói “Manager chắc phải có tất cả quyền của cấp dưới”.** Cần thiết kế lại các role, quan hệ kế thừa, workflow approval hoặc ràng buộc tách nhiệm vụ theo chính sách.

### 5.2. Tách reusable role nhỏ và business role

Một cách tiếp cận là:

| Loại | Chức năng | Ví dụ |
| --- | --- | --- |
| **Technical permission role** | Gom các permission kỹ thuật ổn định trong ứng dụng. | `ERP_ReportReader`. |
| **Business role** | Biểu đạt trách nhiệm công việc và ánh xạ sang role kỹ thuật được duyệt. | `FinanceAnalyst`. |
| **Privileged role** | Quyền quản trị nhạy cảm có kiểm soát bổ sung. | `ERP_UserAdmin`. |
| **Temporary/project role** | Quyền theo dự án hoặc có hạn sử dụng. | `AuditProjectReader_2026Q4`. |

Không nhất thiết mọi loại role đều phải đặt chung vào một hierarchy. **Business role có thể dùng mapping/assignment policy** thay vì luôn làm “senior” của role kỹ thuật. Chọn cấu trúc mà owner có thể hiểu, rà soát và chứng minh được SoD.

### 5.3. Độ rộng và độ sâu của hierarchy

- **Quá sâu:** khó truy vết lý do user có permission, hiệu ứng thay đổi lan xa.
- **Quá rộng:** một senior role gom nhiều permission không liên quan, khó đảm bảo least privilege.
- **Quá nhiều role tương tự:** tạo **role explosion**, khó governance và dễ chồng chéo.
- **Cạnh không có owner:** một thay đổi nhỏ có thể cấp quyền sản xuất ngoài ý muốn.

Chỉ thêm quan hệ kế thừa khi thực sự có **quan hệ bao hàm quyền hợp lệ, tương đối ổn định và được chủ sở hữu phê duyệt**. Nếu một role chỉ chia sẻ vài permission với role khác nhưng có lifecycle khác nhau, có thể dùng role nhỏ tái sử dụng hoặc gán permission trực tiếp thay vì áp hierarchy cưỡng ép.

## 6. SoD với role hierarchy: xung đột khó thấy

**Segregation of Duties (SoD)** hạn chế việc một chủ thể nắm hoặc đồng thời sử dụng những quyền xung đột theo chính sách. Hai kiểu thường được nhắc đến:

| Kiểu | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Static SoD (SSD)** | Ngăn một user được ủy quyền/gán tổ hợp role xung đột; phải tính đến hierarchy và chính sách cụ thể. | Không một người nào được nắm quyền tạo và phê duyệt cùng loại giao dịch ở phạm vi cấm. |
| **Dynamic SoD (DSD)** | Ngăn việc kích hoạt/sử dụng tổ hợp role xung đột trong **cùng phiên/ngữ cảnh** theo mô hình triển khai. | Người có nhiều trách nhiệm được phép nhưng không kích hoạt hai role xung đột cùng lúc. |

**SoD thực tế** có thể còn yêu cầu kiểm tra **hai người khác nhau trên cùng giao dịch**, không thể giải quyết chỉ bằng tập role/phiên. Ví dụ, chính sách “người duyệt không được là người tạo chính khoản thanh toán này” cần kiểm tra **actor của giao dịch**, không chỉ tên role.

### 6.1. Tại sao cần xét permission kế thừa?

Giả sử:

~~~text
PaymentCreator   -> payment:create
PaymentApprover  -> payment:approve
FinanceSuperUser >= PaymentCreator
FinanceSuperUser >= PaymentApprover
~~~

Nếu engine SoD chỉ kiểm tra hai role **được gán trực tiếp**, user có `FinanceSuperUser` sẽ không bị phát hiện vì họ không có UA trực tiếp tới `PaymentCreator` và `PaymentApprover`. Nhưng effective permissions cho phép cả hai hành động.

Kiểm tra SoD cần phân tích:
1. Role gán trực tiếp.
2. Closure của role hierarchy.
3. Permission thực tế được kế thừa.
4. Scope/tài nguyên/trạng thái nghiệp vụ có xung đột.
5. Dynamic activation và kiểm tra transaction-level nếu chính sách yêu cầu.

### 6.2. Hierarchy và DSD

DSD có thể cho phép user giữ hai role nhưng **không kích hoạt đồng thời**. Tuy nhiên, nếu một **senior role tự kế thừa cả hai tập permission**, chỉ giới hạn tên role được activate có thể **không đủ**: kích hoạt senior vẫn cho cả hai permission. Cần xác định **ngữ nghĩa role activation/inheritance** của hệ thống và xem có cần tách senior role hoặc enforcement bổ sung.

**Một policy SoD chỉ tồn tại trong bảng Excel/IGA nhưng không được engine thực thi tại ứng dụng** không phải bảo đảm kỹ thuật. Phải kiểm thử quyền hiệu lực với tình huống thực tế.

### 6.3. Ví dụ ma trận SoD

| Permission A | Permission B | Rủi ro | Kiểm soát |
| --- | --- | --- | --- |
| `payment:create` | `payment:approve` | Tự tạo và tự duyệt thanh toán. | Tách role/quyền; transaction check và approval độc lập. |
| `user:create` | `audit-log:delete` | Có thể tạo account và xóa dấu vết. | Hạn chế quyền log, quản lý độc lập. |
| `source:merge` | `release:approve` | Có thể tự thay đổi và tự phê duyệt release. | Quy trình four-eyes và policy branch/release. |
| `vendor:update-bank` | `payment:release` | Có thể sửa thông tin thanh toán và xuất tiền. | SoD theo nghiệp vụ/tài nguyên. |

Ma trận chỉ là **ví dụ**, cần application/data owner xác định phạm vi, loại giao dịch và ngoại lệ. Không mặc nhiên mọi cặp quyền xung đột trong mọi tổ chức.

## 7. Role hierarchy và group nesting: giống nhưng không đồng nhất

Các hệ thống như directory/IdP có thể hỗ trợ **nhóm lồng nhau** (*nested groups*). Một nhóm có thể làm thành viên của nhóm khác, nhưng **ngữ nghĩa kế thừa quyền RBAC** không tự bằng **ngữ nghĩa membership của directory**.

| Tiêu chí | RBAC role hierarchy | Directory/IdP group nesting |
| --- | --- | --- |
| **Đối tượng** | Role và quan hệ kế thừa permission. | Group và quan hệ membership giữa group/user. |
| **Hướng ngữ nghĩa** | Senior nhận permission của junior. | Thành viên nhóm con có thể được xem thuộc nhóm cha trong một số hệ thống. |
| **Tính chuẩn hóa** | Mô hình RBAC xác định ngữ nghĩa permission inheritance. | Phụ thuộc directory, ứng dụng và hỗ trợ nested membership. |
| **Vai trò trong SSO** | Có thể được ánh xạ thành claim/role theo tích hợp. | IdP có thể phát group claims, thường có giới hạn/cấu hình. |
| **SoD** | Cần kiểm tra role và permission closure. | Danh sách group có thể chỉ là dữ liệu đầu vào cho policy. |
| **Thay đổi vòng đời** | Sửa hierarchy/assignment ảnh hưởng effective rights. | Sửa group membership ảnh hưởng theo cơ chế đồng bộ của target. |

### 7.1. SCIM 2.0 Group không phải chuẩn RBAC hierarchy

**SCIM** chuẩn hóa tài nguyên **User/Group** và giao thức provisioning, nhưng **không định nghĩa một chuẩn chung cho mọi ứng dụng về senior/junior RBAC role hierarchy**. SCIM Group có thể có mảng `members` gồm user hoặc group nếu provider hỗ trợ; nhưng điều đó **không tự đảm bảo**:
- Nhóm lồng nhau được tính thành effective membership.
- Mọi role ứng dụng sẽ kế thừa permission theo mô hình RBAC.
- SCIM sẽ biết toàn bộ permission trong ứng dụng.
- Quyền sẽ mất ngay khi connector xóa membership.

Nếu ứng dụng dùng role riêng, IAM phải có **mapping rõ ràng** từ business role/technical role sang Group/entitlement/API phù hợp.

### 7.2. Ví dụ “có group nhưng không có quyền”

Một IdP phát claim nhóm `finance-portal-users` cho RP qua OIDC/SAML. Ứng dụng có thể xác thực user và tạo session nhưng vẫn thiếu role nội bộ `REPORT_READER`. Ngược lại, user bị gỡ khỏi group IdP nhưng app còn direct role hoặc session cũ.

**SSO AuthN** xác minh người dùng, **SCIM provisioning** đồng bộ account/group, còn **RBAC engine/ứng dụng** áp dụng role hierarchy và permission. Không gộp ba lớp thành một kết quả “đăng nhập thành công”.

## 8. Kết hợp RBAC hierarchy với ABAC và điều kiện ngữ cảnh

Role hierarchy mô tả **permission nào có thể được thừa hưởng**. Nhưng nhiều ứng dụng cần xem thêm **phòng ban, tài nguyên, địa điểm, loại giao dịch, trạng thái account và thời gian** — đó là phạm vi của **Attribute-Based Access Control (ABAC)** hoặc các kiểm soát ngữ cảnh.

### 8.1. Ví dụ cùng permission, khác phạm vi dữ liệu

Giả sử `FinanceEditor >= FinanceReader` và cả hai cho phép thao tác trên báo cáo. Hai user cùng có `FinanceEditor` nhưng:
- Lan có `department=VN-Finance`.
- Mai có `department=SG-Finance`.

Nếu policy chỉ cho truy cập báo cáo có `resource.department == subject.department`, Lan và Mai **không có quyền đọc cùng một tập báo cáo**, dù role hierarchy giống nhau.

~~~text
decision = (
    account.isActive
    AND roleEffectivePermissions.contains("report:read")
    AND resource.department == subject.department
    AND session.authAssurance >= policy.requiredAssurance
    AND noApplicableSoDConflict
)
~~~

Đây là **pseudocode chính sách khái niệm**, không phải cú pháp chung của ABAC engine. Quy tắc phải thực sự được enforcement point kiểm tra ở server, không chỉ chứa trong claim tùy ý từ client.

### 8.2. Vai trò cấp cao không được bỏ qua data scope

Khi role senior kế thừa `report:read`, điều đó không mặc nhiên đồng nghĩa đọc **mọi báo cáo trong doanh nghiệp**. Cần mô hình rõ:
- Permission định nghĩa loại hành động.
- Role chỉ ra trách nhiệm hoặc quyền được phép xét.
- Resource attributes và subject attributes giới hạn đối tượng dữ liệu.
- Policy quyết định theo hoàn cảnh thực tế.

**Một bẫy thiết kế:** dùng role `GlobalManager` kế thừa `RegionalManager` rồi mặc nhiên đổi điều kiện tài nguyên thành “global”. Phạm vi quyền cần được biểu diễn và phê duyệt rõ, không tự sinh do tên role.

### 8.3. Deny policy và thứ tự đánh giá

RBAC cơ bản thường hình dung permission được **cộng dồn** qua các vai trò. Nhưng sản phẩm có thể có **explicit deny**, attribute conditions, policy precedence hoặc conflict-resolution khác nhau. Khi có hai đường cấp và một deny:
- Không tự giả định “allow luôn thắng”.
- Không tự giả định “deny luôn thắng” nếu chưa biết policy engine cụ thể.
- Phải kiểm tra logic policy/enforcement của ứng dụng và test tình huống.

Bài toán thu hồi quyền do hierarchy yêu cầu quan sát **effective access**, không chỉ hợp permission lý thuyết.

## 9. Role hierarchy trong Joiner: cấp đúng role nền tảng

Joiner bắt đầu bằng **nguồn nhân sự hoặc sponsor có thẩm quyền**, proofing/enrollment đúng người và xác định quan hệ có hiệu lực. Sau đó IAM tính quyền cần có theo business role, assignment, nhóm dự án và chính sách.

~~~mermaid
flowchart TD
    H["HRIS / sponsor: Joiner"] --> I["Xác minh identity, employment, effective date"]
    I --> R["Tính business roles và technical roles"]
    R --> C["Tính hierarchy closure + effective permissions"]
    C --> S{"Least privilege, SSD/SoD, approval đạt?"}
    S -->|Không| Q["Chờ phê duyệt / sửa role design"]
    S -->|Có| P["Provision account + role/group ở targets"]
    P --> V["Readback entitlement và kiểm tra quyền thực tế"]
    V --> A["Lưu audit và đăng ký access review/JML"]
~~~

### 9.1. Đừng cấp cả junior role chỉ vì senior đã có

Nếu `ReportEditor >= ReportReader`, gán cả hai role trực tiếp cho user có thể không cần thiết và làm rối nguồn quyền. Trong một số hệ thống, việc gán junior trực tiếp còn tạo **đường quyền độc lập**: khi gỡ `ReportEditor` lúc Mover, user vẫn giữ `ReportReader` do UA trực tiếp.

Tuy nhiên, có thể có lý do nghiệp vụ hợp lệ để user giữ junior role độc lập (ví dụ một assignment khác cần quyền đọc). IAM phải ghi **grant source, owner và thời hạn** cho từng đường, không xóa bừa mọi role trùng permission.

### 9.2. Kích hoạt đúng thời điểm

Có thể chuẩn bị account trước ngày nhân viên vào làm theo policy; nhưng vai trò nhạy cảm và session AuthN/SSO chỉ được kích hoạt đúng điều kiện hiệu lực. Hierarchy không tự làm thay đổi mốc JML. Khi một senior role đã được cấp sớm, toàn bộ junior permissions có thể trở nên khả dụng nếu ứng dụng cho account active.

**Ví dụ:** account được tạo trước 3 ngày để onboarding; nếu senior role `ProductionOperator` đã active, quyền thừa hưởng `ProductionViewer` và quyền trực tiếp thao tác sản xuất có thể có hiệu lực ngay. Giải pháp là thiết kế staged/disabled/account state, effectiveAt và verification phù hợp.

## 10. Role hierarchy trong Mover: gỡ quyền cũ không chỉ sửa chức danh

Mover thường giữ nguyên identity/IdP account nhưng phải tính lại **desired access** theo vai trò mới, các assignment đồng thời, project có thời hạn và ngoại lệ đã phê duyệt.

### 10.1. Ví dụ chuyển Operations → Finance

| Quyền/role | Trước Mover | Sau Mover mong muốn | Hành động |
| --- | --- | --- | --- |
| `AllEmployees` | Có. | Giữ. | Không gỡ membership chung còn cần thiết. |
| `ProductionOperator` (senior) | Có. | Không. | Thu hồi assignment senior và kiểm tra junior permissions. |
| `ProductionViewer` qua hierarchy | Có, gián tiếp. | Không nếu không còn căn cứ. | Kiểm tra có đường cấp khác không, không chỉ kiểm tra UA. |
| `FinanceReader` | Chưa có. | Có theo baseline/approval. | Cấp đúng role/tenant/data scope. |
| `PaymentApprover` | Chưa có. | Chỉ nếu đủ approval và SoD. | Không tự cấp từ chức danh “Manager”. |
| `IncidentResponder` (ngoại lệ) | Có, có hạn. | Có thể giữ tới khi hết hạn nếu hợp lệ. | Lưu owner, phạm vi và expiration. |

**Nguyên tắc:** Mover không phải “thêm role mới rồi quên role cũ”. Phải tính **KEEP / REMOVE / GRANT** trên effective permissions, đánh giá SoD và kiểm tra ứng dụng đích.

### 10.2. Khi thu hồi senior role nhưng quyền vẫn còn

Giả sử Lan có:
- UA trực tiếp `ProductionOperator`.
- UA trực tiếp `IncidentResponder`.
- `ProductionOperator >= ProductionViewer`.
- `IncidentResponder >= ProductionViewer`.

Thu hồi `ProductionOperator` **không làm Lan mất `ProductionViewer`**, vì còn đường qua `IncidentResponder`. Nếu policy Mover yêu cầu ngừng toàn bộ quyền production, phải xem `IncidentResponder` có còn hợp lệ hay không, xử lý ngoại lệ và mọi đường kế thừa.

### 10.3. Kiểm tra thay đổi role hierarchy ảnh hưởng người không liên quan

Một thay đổi khác với Mover là quản trị viên **sửa cạnh hierarchy toàn cục**. Ví dụ thêm:

~~~text
FinancialAuditor >= PaymentApprover
~~~

Điều này có thể làm **mọi user đang có `FinancialAuditor`** nhận quyền duyệt thanh toán. Quy trình phê duyệt phải tính **impact analysis toàn bộ người được ảnh hưởng**, không chỉ ticket người yêu cầu thay đổi cạnh.

## 11. Role hierarchy trong Leaver: đóng mọi đường truy cập

Khi HRIS/sponsor phát Leaver có hiệu lực, IAM phải nhận diện **mọi account và entitlement** của chủ thể, gồm role được gán trực tiếp, permission kế thừa, tài khoản local/privileged và quyền tạm.

Leaver thường cần kết hợp:
1. **Chặn AuthN/account** ở IdP/ứng dụng theo policy và mốc hiệu lực.
2. Thu hồi các UA hoặc group/entitlement tại target.
3. Kiểm tra role hierarchy và các đường quyền khác nếu account không được xóa ngay.
4. Thu hồi/kiểm soát session, token, API key và local credential khi phù hợp.
5. Đối soát **effective access** trên các ứng dụng bắt buộc.
6. Ghi bằng chứng, lỗi còn tồn tại và owner khắc phục.

**Chỉ gỡ một senior role chưa đủ để tuyên bố Leaver đã mất quyền.** Ngoài role khác, ứng dụng có thể duy trì session hoặc token đã phát hành trước đó. IdP disable cũng không nhất thiết chặn local login hoặc mọi API token của ứng dụng legacy.

### 11.1. Rehire và hồi phục account

Với người tái tuyển, việc sử dụng lại identity/account cũ cần xác minh **person linking**, trạng thái lao động mới và chính sách. Không tự khôi phục role hierarchy assignment cũ vì employee number/email giống trước đây. Tính desired access từ **công việc hiện tại**, xét SoD và policy mới, sau đó provision/readback lại.

## 12. Tài khoản dịch vụ và role hierarchy

**Service account/workload identity** có thể dùng một số role kỹ thuật giống người dùng, nhưng vòng đời không hoàn toàn theo HR JML. Ví dụ một job `billing-etl` có role `DataExporter` kế thừa `DataReader` để đọc và xuất tập dữ liệu hợp lệ.

| Yếu tố | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Workload identity | `billing-etl` | Có ID, owner và mục đích rõ. |
| Target account | `svc-billing-01` | Tách khỏi account cá nhân và HR employee identifier. |
| Senior role | `DataExporter` | Xác minh mọi junior permission. |
| Permission kế thừa | `data:read` | Giới hạn tài nguyên/tenant theo policy. |
| Permission trực tiếp | `data:export` | Phê duyệt scope và giám sát dữ liệu. |
| Credential | Workload federation, certificate hoặc secret được bảo vệ. | Rotation/revocation và audit phù hợp. |
| Vòng đời | Owner chuyển vai trò, workload ngừng hoạt động. | Bàn giao owner, rà soát quyền, deprovision khi thật sự hết nhu cầu. |

**Không gỡ role của workload chỉ vì kỹ sư phụ trách nghỉ việc**, nếu dịch vụ còn cần chạy. Nhưng phải thu hồi quyền quản trị của cá nhân cũ, đánh giá credential mà họ từng biết hoặc có khả năng truy cập, chuyển owner và rà soát các quyền kế thừa của service account.

### 12.1. Hạn chế dùng role người cho workload

Một role `HumanPlatformAdmin` có thể mang permission liên quan tới giao diện, quản lý người dùng hoặc audit không cần cho job. Gán role đó cho service account có thể tạo **đặc quyền dư thừa**, nhất là do senior role kế thừa quá nhiều junior roles. Nên thiết kế role phục vụ workload theo **tài nguyên và thao tác tối thiểu**, kèm scope/environment và giới hạn credential.

## 13. IdP, SSO, SCIM và việc lan truyền role hierarchy

Role hierarchy có thể được quản lý ở **IAM/IGA**, **directory/IdP**, **ứng dụng đích** hoặc một **authorization service**. Mỗi nơi có cách biểu diễn khác nhau.

~~~mermaid
flowchart TD
    H["HRIS/JML authoritative events"] --> IAM["IAM/IGA: desired roles + approvals"]
    IAM --> GRAPH["Role hierarchy + SoD policy + effective access"]
    GRAPH --> PROV["Provisioning mappings"]
    PROV --> IDP["IdP groups / app assignments"]
    PROV --> APP["App roles / entitlement / SCIM Group"]
    IDP --> SSO["SSO: AuthN, MFA, claims"]
    SSO --> APP
    APP --> PDP["RBAC/ABAC enforcement tại ứng dụng"]
    PDP --> AUDIT["Audit + reconciliation"]
    AUDIT --> IAM
~~~

### 13.1. Quyền có thể được “expand” ở nhiều lớp

| Lớp | Điều có thể xảy ra | Rủi ro cần kiểm tra |
| --- | --- | --- |
| **IAM/IGA** | Tính quyền kế thừa rồi phát lệnh cấp role kỹ thuật. | Graph lỗi gây cấp nhiều entitlement ngoài ý muốn. |
| **IdP/directory** | Group nesting hoặc app assignment tạo hiệu lực truy cập. | Không chắc ứng dụng xử lý nested group giống IdP. |
| **SCIM connector** | Tạo/cập nhật User/Group tại target. | SCIM không chuẩn hóa mọi semantics hierarchy. |
| **Ứng dụng** | Role nội bộ kế thừa permission theo policy riêng. | Mapping không nhất quán với IAM, direct grants bị bỏ sót. |
| **SSO token/claim** | Token phản ánh một snapshot role/group khi phát hành. | Claim cũ có thể còn hiệu lực sau Mover/Leaver. |
| **PDP/PEP** | Quyết định ALLOW/DENY theo permission và thuộc tính ngữ cảnh. | Cache hoặc kiểm tra không đủ dẫn đến residual access. |

**Không có tiêu chuẩn SCIM chung cho “tạo cạnh Senior ≥ Junior”.** Một provider có thể dùng API riêng để quản lý role hierarchy, hoặc chỉ hỗ trợ flat groups. Khi tích hợp phải nêu rõ **nguồn sự thật của role graph**, mapping và cách kiểm chứng quyền thực tế.

### 13.2. SSO không tự đánh giá role hierarchy

**IdP/SSO** xác minh người dùng bằng OIDC/SAML và có thể phát group/role claims theo cấu hình. Ứng dụng phải kiểm tra issuer, audience, signature, thời gian và ánh xạ account, sau đó áp authorization theo policy có thẩm quyền.

Một claim `roles=["ReportEditor"]` có thể là dữ liệu đầu vào; **nó không đảm bảo ReportEditor kế thừa gì** nếu ứng dụng không có graph tương ứng. Ngược lại, RP có thể nhận claim cũ khi hierarchy đã thay đổi. Cần xác định **ai tính effective permissions và khi nào chính sách được làm mới**.

### 13.3. SCIM Group không tự biết SoD

SCIM có thể đồng bộ user/group memberships, nhưng **SoD và least privilege phải được áp dụng ở lớp ra quyết định và/hoặc enforcement**. Nếu IAM cấp hai nhóm xung đột vì graph mapping sai, API SCIM có thể trả thành công mà vẫn tạo rủi ro nghiệp vụ. Do đó, “provisioning success” không đồng nghĩa “policy compliant”.

## 14. Thiết kế quản trị và phê duyệt thay đổi hierarchy

Role hierarchy không nên được chỉnh như một bảng cấu hình tùy tiện. Nó là **chính sách ủy quyền** có tác động rộng. Mỗi role và cạnh cần metadata, owner và quy trình thay đổi.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Role ID / namespace / tenant** | Định danh ổn định, tránh nhầm role trùng tên. |
| **Role description / purpose** | Vì sao role tồn tại, nhiệm vụ nào được phục vụ. |
| **Direct permission set** | Quyền gốc của role, nguồn công bố và chủ sở hữu. |
| **Parent/child edges** | Quan hệ senior/junior, lý do kế thừa. |
| **Business/application owner** | Người chịu trách nhiệm tính hợp lệ và phê duyệt. |
| **Risk classification** | Role có đặc quyền, dữ liệu nhạy cảm hay SoD conflict không. |
| **Policy version/effectiveAt** | Phiên bản graph và mốc bắt đầu có hiệu lực. |
| **Approval and review refs** | Bằng chứng ai duyệt và kỳ rà soát. |
| **Provisioning mappings** | Liên hệ với IdP groups, SCIM Groups, app roles. |
| **Deprovisioning rules** | Cách thu hồi role và xác minh permission tại target. |

### 14.1. Quy trình change management cho cạnh kế thừa

1. Tạo đề xuất `Senior >= Junior` với **business justification** và owner.
2. Xác minh không có **chu trình**, không làm sai semantics hierarchy.
3. Tính **permission delta** cho senior và tất cả **ancestor roles** có thể thừa hưởng từ senior sau thay đổi.
4. Tính tập **user/service accounts** bị ảnh hưởng, kể cả indirect assignments và active sessions nếu liên quan.
5. Chạy kiểm tra **least privilege, SSD/DSD/SoD, dữ liệu nhạy cảm và privilege escalation**.
6. Đánh giá tác động tới môi trường/tenant, API/mapping, IdP groups và ứng dụng.
7. Phê duyệt theo policy, đặc biệt role đặc quyền hoặc tài chính.
8. Triển khai với **version, thời điểm hiệu lực và phương án rollback** được đánh giá.
9. **Readback effective permissions/target entitlements**, không chỉ lưu graph thành công.
10. Ghi audit, theo dõi sai lệch và lên lịch access review.

### 14.2. Delta analysis có thể phát hiện thay đổi nguy hiểm

Giả sử thêm cạnh:

~~~text
OpsSupervisor >= CloudAdmin
~~~

Nếu `CloudAdmin` có `iam:manage-users` và `cloud:full-access`, toàn bộ người có `OpsSupervisor` (hoặc role senior hơn) có thể nhận những quyền này. Trước khi phê duyệt, cần trả lời:
- Có bao nhiêu user/service accounts chịu tác động?
- Có quyền nhạy cảm mới nào và thuộc tenant nào?
- Có SoD conflict hoặc vượt data scope không?
- Session/token/role cache có cần cập nhật hoặc chặn không?
- Khi rollback cạnh, app có thật sự bỏ permission đã được provision độc lập không?

**Việc thêm một cạnh không chỉ ảnh hưởng hai role ở hai đầu cạnh**: quyền có thể lan qua **toàn bộ ancestor closure**.

### 14.3. Version và rollback

Rollback một cạnh hierarchy không nhất thiết rollback **entitlement đã cấp riêng** hoặc session/tokens tại mọi target. Khi rollback, cần thực hiện reconciliation và kiểm tra quyền còn tồn dư.

Một bản ghi thay đổi ví dụ:

~~~json
{
  "changeId": "RBAC-CHG-2026-041",
  "tenant": "workforce",
  "roleEdge": {
    "seniorRoleId": "finance-report-editor",
    "juniorRoleId": "finance-report-reader",
    "operation": "ADD"
  },
  "policyVersionBefore": "rbac-v20",
  "policyVersionAfter": "rbac-v21",
  "risk": "MEDIUM",
  "approvalRef": "APPROVAL-4881",
  "impactAnalysisRef": "RBAC-IMPACT-104",
  "effectiveAt": "2026-12-01T00:00:00+07:00",
  "implementationStatus": "PENDING_VERIFICATION"
}
~~~

Đây là **JSON minh họa hệ thống quản trị policy**, không phải định dạng chuẩn RBAC/SCIM/OIDC. `PENDING_VERIFICATION` quan trọng: thay đổi graph đã lưu không đảm bảo các ứng dụng đích đã đồng bộ xong.

## 15. Reconciliation: từ role assignment đến effective access

**Desired state** là tập role/permission/constraints mà IAM cho rằng một identity **được phép có** theo thời điểm hiệu lực. **Actual state** là account, group, role, quyền và session/token **thực tế** tại các target.

Các kiểm tra khác nhau:

| Kiểm tra | Câu hỏi | Nếu bỏ qua |
| --- | --- | --- |
| **UA direct** | User đang được gán role nào trực tiếp? | Bỏ sót assignment không còn căn cứ. |
| **Hierarchy graph** | Role senior kế thừa những junior roles nào? | Bỏ sót indirect permissions. |
| **PA direct** | Role nào được gán permission cụ thể nào? | Không biết quyền lan từ đâu. |
| **Effective permission** | User có thể thực hiện những hành động nào? | Đóng ticket khi quyền vẫn còn qua nhánh khác. |
| **SoD/ABAC** | Có xung đột hoặc vượt tài nguyên/phạm vi không? | Tưởng hợp RBAC nhưng sai nghiệp vụ. |
| **Target account/group** | SCIM/IdP/app có đồng bộ đúng không? | Sai lệch giữa IAM và ứng dụng. |
| **Session/token/credential** | Quyền cũ còn khả dụng qua phiên/token đã cấp không? | Residual access sau Mover/Leaver. |
| **Audit evidence** | Có thể chứng minh ai quyết định và kết quả nào không? | Khó điều tra và chứng minh tuân thủ. |

### 15.1. Không đồng nhất “đã gỡ role” với “đã mất permission”

Giả sử:

~~~text
AssignedRoles(Lan) = {RoleA, RoleB}
RoleA >= Viewer
RoleB >= Viewer
PA(Viewer) = {report:read}
~~~

Gỡ `RoleA` vẫn để Lan có `report:read` qua `RoleB`. **Nếu quyền đọc vẫn hợp lệ vì RoleB** thì không cần gỡ. **Nếu policy yêu cầu mất hoàn toàn quyền**, phải xác minh RoleB có còn căn cứ hay không và xử lý phù hợp.

### 15.2. Audit chứng minh đường cấp quyền

Một bản ghi giải thích một permission nên có **đường nguồn**:

~~~text
identity: person-2048
target: finance-portal / tenant-vn
targetAccount: finance-user-882

effectivePermission: report:read
sourceAssignment: FinancePowerUser
inheritancePath:
  - FinancePowerUser
  - ReportEditor
  - ReportViewer
permissionOrigin: ReportViewer
policyVersion: rbac-v21
sourceEvent: HR-MOVER-2026-088
verifiedAt: 2026-12-01T08:05:00+07:00
~~~

Đây là **mô hình giải thích đường quyền**, không phải payload SCIM chuẩn. Nó giúp trả lời “vì sao user có quyền?”; trong kiểm toán phải bảo vệ dữ liệu cá nhân, không đưa credential/token vào bằng chứng.

### 15.3. Độ trễ và eventual consistency

Trong hệ thống phân tán, IAM có thể cập nhật hierarchy trước, SCIM connector cập nhật Group sau, ứng dụng refresh cache/token sau nữa. Workflow có thể cần các trạng thái:
- `PLANNED` — quyết định đã duyệt.
- `EXECUTING` — đang thay đổi graph/assignments.
- `PENDING_RECONCILIATION` — chưa chứng minh target khớp.
- `VERIFIED` — kiểm chứng đạt yêu cầu.
- `REMEDIATION_REQUIRED` — quyền còn tồn dư hoặc đồng bộ lỗi.

Không đánh dấu `VERIFIED` chỉ vì API trả HTTP 200. Với quyền đặc quyền, cần giám sát thời gian thu hồi theo chính sách; một lỗi sync phải có owner và biện pháp giảm rủi ro.

## 16. Tình huống thực tế: role hierarchy gây xung đột SoD

**Bối cảnh:** Ứng dụng thanh toán nội bộ có role:

~~~text
PaymentViewer       -> payment:read
PaymentCreator      -> payment:create
PaymentApprover     -> payment:approve
FinanceTeamLead     -> finance:manage-workflow
~~~

Một đề xuất role hierarchy:

~~~text
FinanceTeamLead >= PaymentViewer
FinanceTeamLead >= PaymentCreator
FinanceTeamLead >= PaymentApprover
~~~

### 16.1. Phân tích trước khi triển khai

Nếu policy yêu cầu tách người tạo và người duyệt thanh toán, `FinanceTeamLead` kế thừa cả hai permission là **rủi ro SoD**. Không nên chấp nhận đề xuất chỉ vì tên “TeamLead” hàm ý quản lý cả nhóm.

Phương án điều chỉnh có thể gồm:
1. `FinanceTeamLead` chỉ kế thừa `PaymentViewer` cùng permission điều phối, **không** tự nhận create/approve.
2. Gán `PaymentCreator` và `PaymentApprover` theo nhiệm vụ riêng, có ràng buộc SSD/DSD hoặc kiểm soát transaction-level phù hợp.
3. Nếu lead cần phê duyệt tạm thời, dùng **role có thời hạn/JIT privileged access** theo policy với audit và kiểm tra xung đột.
4. Ứng dụng kiểm tra **người tạo khác người duyệt** cho từng giao dịch, nếu đó là yêu cầu nghiệp vụ.
5. Readback quyền và chạy tình huống kiểm thử trước production.

### 16.2. Kịch bản Mover

Lan đang có `PaymentCreator` và chuyển sang nhiệm vụ phê duyệt. IAM phải:
- Xác minh HR/sponsor event và `effectiveAt`.
- Gỡ quyền creator không còn hợp lệ và các đường kế thừa creator.
- Kiểm tra transaction/case còn mở, role grants và session.
- Chỉ cấp approver khi policy/SoD cho phép.
- Xác minh application account không còn cho Lan tự tạo và tự duyệt giao dịch cùng phạm vi.

Việc chuyển role không thể được giải quyết bằng cách **gán cả hai role vào `FinanceTeamLead`** nếu policy SoD cấm.

### 16.3. Kịch bản Leaver

Sau khi Lan nghỉ việc, IdP account bị disable nhưng Finance Portal vẫn có phiên cũ hoặc một tài khoản local. IAM cần chặn đường truy cập đó và thu hồi role/group trong target. **Role hierarchy analysis chỉ là một phần** của kiểm soát deprovisioning; vẫn phải đánh giá account, session và credential.

## 17. Chỉ số và cảnh báo cho role hierarchy

| Chỉ số | Cách đo tham khảo | Rủi ro khi hiểu sai |
| --- | --- | --- |
| **Unreviewed hierarchy edges** | Số cạnh senior–junior chưa có owner/approval hoặc quá hạn review. | Tưởng mọi cạnh do ứng dụng định nghĩa đều hợp chính sách. |
| **Role hierarchy depth** | Số cạnh trên đường kế thừa dài nhất trong từng tenant/ứng dụng. | Không đồng nghĩa độ sâu lớn luôn xấu; cần xét khả năng giải thích. |
| **Role fan-out** | Số junior roles hoặc permission mà một senior có thể kế thừa. | Chỉ đếm cạnh trực tiếp, bỏ qua transitive closure. |
| **Permission overgrant count** | Permission effective ngoài desired state được phát hiện trong reconciliation. | Không tính direct grants hoặc token/session. |
| **SoD violations via inheritance** | Trường hợp role closure tạo cặp permission/role xung đột. | Chỉ quét role gán trực tiếp. |
| **Role change impact size** | Số identity/service accounts và entitlement bị tác động khi sửa một cạnh. | Bỏ qua ancestor roles và multiple inheritance. |
| **Mover revocation latency** | Từ mốc quyền cũ phải hết tới lúc target effective access được xác minh đã mất. | Dùng thời điểm ticket được đóng làm mốc. |
| **Leaver closure coverage** | Tỷ lệ account/đường truy cập phải chặn đã được kiểm chứng theo policy. | Coi disable IdP là đủ mọi target. |
| **Hierarchy drift rate** | Chênh lệch giữa role graph/mapping mong muốn và quyền thực tế ở target. | Chỉ kiểm tra tên role, không kiểm tra permission. |
| **Orphaned privileged roles** | Role/cạnh/assignment nhạy cảm không còn owner hoặc không có căn cứ. | Bỏ qua service accounts và ngoại lệ tạm thời. |

Không có một ngưỡng fan-out/độ sâu chung phù hợp mọi hệ thống. Một role nhỏ nhưng có permission `iam:assign-admin` có thể rủi ro hơn role nhiều quyền chỉ đọc. Ưu tiên **độ nhạy permission và đường khai thác thực tế** trong đánh giá.

### 17.1. Cảnh báo nên có

- Một cạnh mới khiến role phổ thông kế thừa permission admin hoặc quyền dữ liệu nhạy cảm.
- Role graph có chu trình, role không có owner hoặc tham chiếu role đã bị xóa.
- Một permission nhạy cảm lan tới nhiều account ngoài phạm vi được duyệt.
- Mover hoàn tất tại HR/IGA nhưng target vẫn có quyền cũ.
- Một user có quyền xung đột chỉ thông qua senior role.
- Role được gỡ nhưng permission vẫn tồn tại qua cạnh khác hoặc direct grant.
- Service account kế thừa quyền broad admin do thay đổi role graph.
- Thay đổi policy không có version, approval hoặc kết quả readback.

## 18. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Coi role hierarchy là sơ đồ cấp bậc nhân sự. | Manager tự nhận quyền tạo giao dịch/đặc quyền không cần thiết. | Thiết kế theo permission inclusion và SoD. |
| Đảo chiều senior/junior. | Viewer vô tình nhận quyền editor/admin. | Sơ đồ hướng rõ và kiểm thử effective permissions. |
| Chỉ xét quyền trực tiếp của role. | Bỏ sót permission kế thừa. | Tính transitive closure, kiểm tra DAG. |
| Cho phép chu trình role. | Permission phình ra hoặc mô hình trở nên không rõ nghĩa. | Từ chối cycle khi change validation. |
| Không xét multiple inheritance. | Thu hồi một nhánh nhưng quyền vẫn còn qua nhánh khác. | Truy vết mọi đường cấp quyền. |
| Chỉ chạy SSD trên role được gán trực tiếp. | Bỏ sót xung đột do senior role kế thừa. | SoD trên role closure/effective permissions theo policy. |
| Coi DSD đủ khi senior role chứa cả hai permission xung đột. | Một role active vẫn cho phép hành động bị cấm. | Thiết kế lại role và enforcement ở transaction. |
| Dùng group nesting như thay thế mặc định role hierarchy. | IdP và ứng dụng đánh giá membership khác nhau. | Định nghĩa mapping, khả năng target và readback. |
| Coi SCIM User/Group mặc nhiên chuẩn hóa mọi role graph. | Đồng bộ group thành công nhưng role nội bộ sai. | Kiểm tra API/schema target và policy ownership. |
| Dùng token claim cũ làm authority vĩnh viễn. | Quyền cũ tồn tại sau Mover/Leaver. | Session/token policy, refresh/revocation và application checks. |
| Gán account nhân viên đã nghỉ việc vào role mới để “sửa login”. | Bypass lifecycle controls. | Xác minh HR status; không kích hoạt lại Leaver ngoài quy trình. |
| Khi owner service account nghỉ việc thì xóa role workload tùy ý. | Gián đoạn hệ thống hoặc tồn dư secret. | Bàn giao owner, quyền cá nhân và workload lifecycle riêng. |
| Thay cạnh hierarchy không có impact analysis. | Hàng loạt user nhận quyền mới. | Tính ancestor closure, review/approval và test. |
| Đóng ticket khi graph được lưu mà không kiểm tra target. | Residual access hoặc provisioning drift. | Readback permission/group/role và effective access. |

## 19. Checklist thiết kế, vận hành và bài tập

### 19.1. Checklist trước khi đưa role hierarchy vào production

- [ ] Có **role ID, mô tả, owner và permission set** được công nhận cho từng role.
- [ ] Xác định rõ chiều `Senior >= Junior`: **senior kế thừa permission của junior**.
- [ ] Graph là DAG/partial order hợp lệ; không có chu trình hoặc quan hệ nhập nhằng.
- [ ] Tính cả **transitive closure** và **multiple inheritance** khi xác định effective permissions.
- [ ] Role hierarchy xuất phát từ **permission inclusion hợp lệ**, không sao chép org chart.
- [ ] Mọi cạnh có business justification, approval, version và effectiveAt.
- [ ] Đã phân tích số identity/account/permission chịu tác động khi thêm/gỡ cạnh.
- [ ] Kiểm tra **least privilege, SSD/DSD/SoD** cả trên quyền kế thừa và hành động nghiệp vụ.
- [ ] Không dùng senior role để bỏ qua transaction-level SoD khi cần.
- [ ] Hiểu rõ role activation/session và thuật toán allow/deny của hệ thống thực.
- [ ] Khi kết hợp ABAC, policy data scope và context được enforcement phía server.
- [ ] Có mapping rõ IAM role ↔ IdP group ↔ SCIM Group ↔ app role/entitlement.
- [ ] Không đồng nhất SSO AuthN, SCIM provisioning và authorization RBAC.
- [ ] Joiner cấp đúng role theo identity/effective date; không tự gán trùng junior ngoài nhu cầu.
- [ ] Mover tính KEEP/REMOVE/GRANT và kiểm tra quyền vẫn có qua đường khác.
- [ ] Leaver chặn account và các đường session/token/local credential bắt buộc.
- [ ] Service/workload identity có role, owner, secret và vòng đời riêng.
- [ ] Reconciliation so sánh **desired vs actual effective access**, không chỉ role name.
- [ ] Audit ghi role path, phiên bản policy, actor/approval, target và verification.
- [ ] Có cảnh báo privilege escalation, SoD violation, orphaned role và lỗi đồng bộ.

### 19.2. Bài tập A — Kế thừa nhiều tầng

Cho `Admin >= Editor >= Viewer`. `Viewer` có `document:read`, `Editor` có `document:update`, `Admin` có `user:manage`. Hãy liệt kê effective permissions của mỗi role và giải thích vì sao gán `Admin` có thể đủ để nhận các quyền junior mà không cần gán thêm từng role.

### 19.3. Bài tập B — Thu hồi một nhánh không mất quyền

Cho `OpsLead >= ReportViewer` và `IncidentResponder >= ReportViewer`. Lan được gán trực tiếp cả `OpsLead` và `IncidentResponder`. Khi Mover bỏ `OpsLead`, Lan còn `report:read` không? Hãy trình bày **đường kế thừa còn lại** và khi nào nên hoặc không nên thu hồi `IncidentResponder`.

### 19.4. Bài tập C — Xung đột SoD do senior role

`FinanceSuperUser` kế thừa `PaymentCreator` và `PaymentApprover`. Chính sách cấm một người tạo và phê duyệt cùng khoản thanh toán. Tại sao chỉ kiểm tra hai UA trực tiếp lại không đủ? Hãy đề xuất **role redesign, SSD/DSD và transaction-level check** phù hợp.

### 19.5. Bài tập D — Group nesting không đồng nhất

IdP có group `finance-users`, ứng dụng ERP có role `FINANCE_REPORT_READ`. Người dùng thuộc group nhưng ERP vẫn báo 403. Hãy phân biệt **SSO/AuthN, SCIM/group provisioning, mapping RBAC hierarchy và AuthZ tại tài nguyên**, xác định các bước readback cần thực hiện.

### 19.6. Bài tập E — Thêm cạnh mới gây overgrant

Quản trị viên đề xuất `SupportLead >= UserAdmin` để đơn giản hóa vận hành. Hãy xác định **ancestor roles, user/service accounts chịu ảnh hưởng, permission delta, SoD và phương án rollback** cần đánh giá trước khi chấp thuận thay đổi.

### 19.7. Bài tập F — Mover, ABAC và phạm vi dữ liệu

Mai chuyển từ `Finance-VN` sang `Finance-SG`, vẫn giữ role `ReportEditor`. Hierarchy cho `report:read` và `report:update` nhưng policy ABAC yêu cầu `subject.department == resource.department`. Hãy giải thích vì sao giữ role không có nghĩa Mai được tiếp tục đọc báo cáo VN, và cách kiểm tra session/claim cũ.

### 19.8. Bài tập G — Service account và owner rời tổ chức

Workload `billing-etl` có role `DataExporter >= DataReader`. Engineer owner nghỉ việc nhưng job vẫn được doanh nghiệp cần. Có nên gỡ `DataExporter` ngay? Hãy phân biệt **quyền của người cũ**, **ownership**, **credential rotation** và **effective permissions của workload**, sau đó đề xuất checklist đối soát.

**Điểm cần ghi nhớ:** **Role hierarchy trong RBAC** giúp role senior kế thừa permission của junior qua **quan hệ bắc cầu và có thể nhiều nhánh**, giảm lặp lại cấu hình nhưng tăng rủi ro nếu một cạnh sai lan quyền cho nhiều identity. Thiết kế phải dựa trên **permission inclusion, least privilege và SoD**, không theo cấp bậc nhân sự. Trong IAM **Joiner–Mover–Leaver**, cần tính **effective permissions qua mọi đường kế thừa**, phối hợp **IdP/SSO, SCIM provisioning, RBAC/ABAC và session/token controls**, rồi **readback/reconciliation trên hệ thống đích** để chứng minh quyền không còn căn cứ thực sự đã bị thu hồi.

