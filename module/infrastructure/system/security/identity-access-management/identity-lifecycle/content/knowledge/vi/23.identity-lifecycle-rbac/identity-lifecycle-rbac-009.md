# Role explosion trong RBAC và quản lý vòng đời danh tính IAM

## 1. Role explosion là gì?

**Role explosion** (bùng nổ vai trò) là tình trạng số lượng **role** trong hệ thống **Role-Based Access Control (RBAC)** tăng quá mức so với khả năng quản trị, nhu cầu nghiệp vụ và mức độ khác biệt thực sự về quyền. Việc tạo thêm nhiều role không nhất thiết làm bảo mật tốt hơn: các role có thể trùng quyền, khác nhau chỉ một điều kiện nhỏ, thiếu chủ sở hữu, khó được phê duyệt hoặc không còn phản ánh cách tổ chức hoạt động.

Ví dụ, doanh nghiệp có các vai trò **Sales Reader**, **Sales Editor** và **Finance Approver**. Ban đầu chỉ cần một số role rõ ràng. Khi quản trị viên tiếp tục tạo biến thể theo **phòng ban, quốc gia, chi nhánh, sản phẩm, môi trường, cấp độ dữ liệu và ngoại lệ cá nhân**, hệ thống có thể xuất hiện hàng trăm role gần giống nhau: **Sales-Reader-North-Prod**, **Sales-Reader-South-Prod**, **Sales-Reader-North-Test**, v.v. Một thay đổi chính sách phải cập nhật hàng loạt role, và một nhân viên chuyển bộ phận có thể giữ sót nhiều role cũ.

Trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, vấn đề này trực tiếp ảnh hưởng mô hình **Joiner–Mover–Leaver (JML)**, từ xác minh và tạo tài khoản, cấp quyền, rà soát đến thu hồi khi thay đổi vai trò. Bài học kết nối RBAC với **IdP, SSO, SCIM, ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**.

### Những điều cần phân biệt

| Khái niệm | Ý nghĩa | Không nên hiểu nhầm |
|---|---|---|
| **Role** | Tập quyền được tổ chức theo chức năng/ngữ nghĩa nghiệp vụ | Một role luôn tương ứng đúng một chức danh HR |
| **Permission** | Quyền thực hiện action trên loại tài nguyên hoặc phạm vi phù hợp | Một permission là quyền làm mọi việc trên mọi đối tượng |
| **Entitlement** | Quyền/nhóm/role cụ thể do ứng dụng hoặc nền tảng cung cấp | Entitlement từ hệ thống đích luôn khớp một role nghiệp vụ |
| **Role explosion** | Số lượng/độ phức tạp role vượt mức cần thiết và có thể quản trị | Cứ nhiều role là sai trong mọi trường hợp |
| **Permission sprawl** | Các quyền phân tán, trùng lặp hoặc không còn được kiểm soát | Chỉ xuất hiện khi có nhiều role |
| **Privilege accumulation** | Người dùng giữ thêm quyền qua thời gian, đặc biệt sau Mover | Chỉ do role explosion gây ra |
| **Role mining** | Phân tích dữ liệu account–permission để phát hiện mẫu vai trò | Thuật toán có thể tự quyết định policy đúng mà không cần owner |

**Role explosion là một vấn đề về mô hình quyền và vận hành**, không đơn giản là vượt một con số role cố định. Một tổ chức có 500 role được quản trị tốt có thể ít rủi ro hơn tổ chức có 50 role thiếu owner và có quyền quá rộng.

## 2. Ôn lại RBAC: User, Role, Permission và Session

Trong mô hình RBAC cốt lõi, người dùng được **gán role**, role chứa **permission**, và một phiên hoặc ngữ cảnh sử dụng role xác định quyền có thể thực hiện. Những biến thể **hierarchical RBAC** và **constrained RBAC** bổ sung kế thừa role, ràng buộc và nguyên tắc **Separation of Duties (SoD)**.

Một biểu diễn đơn giản:

~~~mermaid
flowchart LR
    HR[HRIS / quan hệ JML] --> IAM[IAM / IGA]
    IAM --> UR[User-Role Assignments]
    UR --> ROLE[Business/Technical Roles]
    ROLE --> RP[Role-Permission Assignments]
    RP --> PERM[Action trên Resource]
    PERM --> API[Ứng dụng / API enforcement]
    IAM --> AUDIT[Access review / Reconciliation]
    API --> AUDIT
~~~

Với ký hiệu:

- \(U\): tập chủ thể hoặc tài khoản người dùng thuộc phạm vi.
- \(R\): tập role.
- \(P\): tập permission.
- \(UA \subseteq U \times R\): quan hệ gán user–role.
- \(PA \subseteq R \times P\): quan hệ gán role–permission.

Mô hình trên giúp giảm việc gán trực tiếp từng permission cho từng user. Thay vì quản lý \(U \times P\) tùy tiện, tổ chức quản lý \(UA\) và \(PA\) theo chức năng hợp lệ.

**Role explosion xuất hiện khi chính lớp trừu tượng role trở nên quá phân mảnh**, khiến nó không còn giúp giảm chi phí quản trị.

### Permission và action trong RBAC

Ví dụ một permission có thể là **invoice.approve** trên phạm vi đơn vị được giao. API vẫn cần kiểm tra tài nguyên cụ thể, hạn mức, người tạo và trạng thái hóa đơn. Role **FINANCE_APPROVER** không mặc nhiên cho phép duyệt mọi hóa đơn trong toàn bộ hệ thống.

## 3. Role explosion hình thành như thế nào?

Các nguyên nhân phổ biến có thể tồn tại đồng thời:

1. **Mỗi tổ hợp thuộc tính thành một role:** bộ phận × khu vực × môi trường × cấp dữ liệu × sản phẩm.
2. **Ngoại lệ cá nhân hóa:** tạo role mới mỗi khi một người cần thêm một permission, thay vì quy trình entitlement có hạn.
3. **Sao chép role:** role mới được clone từ role cũ và sửa vài quyền, không có chiến lược hợp nhất/phiên bản.
4. **Thay đổi cơ cấu tổ chức:** Mover, tái cơ cấu, đổi tên phòng ban tạo role mới nhưng không nghỉ hưu role cũ.
5. **Nhiều hệ thống có quyền khác nhau:** IAM nhập nguyên role/nhóm của từng SaaS mà không tách lớp nghiệp vụ khỏi kỹ thuật.
6. **Role theo dự án ngắn hạn:** mỗi chiến dịch hoặc dự án sinh thêm role tồn tại vô thời hạn.
7. **Role hierarchy không kiểm soát:** nhiều lớp kế thừa chồng chéo khiến khó đoán effective permissions.
8. **Không có owner và chuẩn đặt tên:** các nhóm triển khai tự tạo biến thể cùng chức năng.
9. **Không có giới hạn thời gian:** quyền tạm được biến thành role vĩnh viễn.
10. **Áp RBAC cho điều kiện động:** tài nguyên thuộc ai, đang ở trạng thái nào, phiên MFA ra sao đều bị “mã hóa” thành hậu tố role.

### Dấu hiệu thấy được trong catalog

~~~text
sales_viewer_north_prod
sales_viewer_north_staging
sales_viewer_south_prod
sales_viewer_south_staging
sales_viewer_north_prod_special
sales_viewer_north_prod_special_v2
sales_viewer_north_prod_special_temp
~~~

Danh sách trên cho thấy nhiều role có cùng **chức năng đọc Sales**, nhưng khác thuộc tính tài nguyên, môi trường và ngoại lệ. Đây là **dấu hiệu cần phân tích**, không đủ để tự xóa role khi chưa hiểu policy và đối tượng đang sử dụng.

## 4. Tăng trưởng tổ hợp: vì sao role có thể nhân rất nhanh?

Giả sử mô hình cấp quyền đặt role riêng cho mỗi tổ hợp của các chiều:

- 6 chức năng công việc.
- 5 vùng kinh doanh.
- 4 nhóm sản phẩm.
- 3 môi trường.

Nếu tạo đầy đủ một role cho mọi tổ hợp thì số role tiềm năng là:

\[
R_{\text{composite}} = 6 \times 5 \times 4 \times 3 = 360
\]

Nếu bổ sung 3 mức phân loại dữ liệu, số tổ hợp tăng thành:

\[
R_{\text{new}} = 360 \times 3 = 1080
\]

Đây là **số tổ hợp tối đa trong ví dụ giả định**, không phải khẳng định mọi tổ chức thực sự cần 1.080 role. Một số tổ hợp không hợp lệ hoặc không bao giờ dùng; một số có quyền khác thực chất và cần role riêng.

### So sánh các mô hình

| Mô hình | Cách mô tả | Rủi ro vận hành |
|---|---|---|
| **Composite-role-only** | SalesReader-North-ProductA-Prod | Role tăng theo tổ hợp, clone và drift |
| **Role + attributes** | Role SalesReader; region/product/environment là điều kiện policy | Phụ thuộc chất lượng ABAC và enforcement |
| **Role + resource bindings** | Role SalesReader được gán với resource scope cụ thể | Cần engine hỗ trợ binding đúng ngữ nghĩa |
| **Role + temporary grant** | Base role và quyền bổ sung được duyệt có thời hạn | Cần quản trị ngoại lệ và tự thu hồi |
| **Role hierarchy được kiểm soát** | Role nền tảng kế thừa tập permission rõ ràng | Cần tránh role kế thừa sai và SoD conflict |

**Không dùng một phép tính tổ hợp để tuyên bố chắc chắn phải bỏ RBAC.** Thường chỉ cần đổi cách biểu diễn những chiều vốn thuộc **resource/context** thay vì nhúng tất cả vào tên role.

## 5. Hệ quả của role explosion

### 5.1. Cấp quyền sai và quyền tồn dư

Khi một người chuyển bộ phận, hệ thống phải thu hồi nhiều role theo các biến thể region, product, team. Nếu một role bị bỏ sót, người đó có thể vẫn đọc hoặc xuất dữ liệu của bộ phận cũ.

### 5.2. Kiểm toán và access review khó hiểu

Manager được yêu cầu chứng nhận **17 role có tên gần giống nhau** nhưng không biết chúng cấp quyền gì. Quy trình chứng nhận trở thành hình thức vì khó phân biệt **Sales_Reader_A**, **Sales_Reader_B** và **Sales_Reader_A_v2**.

### 5.3. Xung đột SoD bị che giấu

Một người có thể giữ **payment.create** qua role A và **payment.approve** qua role B, dù mỗi role riêng lẻ nhìn có vẻ hợp lệ. Xem role theo từng tên mà không tính **effective permissions** sẽ bỏ sót vi phạm **Segregation of Duties**.

### 5.4. Hiệu năng và vận hành

Số lượng role lớn có thể làm tăng chi phí **policy evaluation, đồng bộ nhóm, kích thước token/claim, chi phí API, phân trang và cache**. Mức ảnh hưởng phụ thuộc hệ thống; nhiều role không tự đồng nghĩa API chậm, nhưng làm tăng khả năng vượt giới hạn của một số sản phẩm.

### 5.5. Khó chứng minh least privilege

Khi một role được clone từ role cũ và không loại bỏ quyền dư, chính sách “ít quyền nhất” chỉ còn là khẩu hiệu. Càng nhiều role không rõ nguồn, khả năng kiểm tra **vì sao một user được một permission** càng thấp.

### 5.6. Tăng rủi ro khi phản ứng sự cố

Trong sự cố, đội bảo mật cần nhanh chóng trả lời **ai có thể export dữ liệu X?** hoặc **role nào cấp quyền disable account?**. Một đồ thị role trùng lặp và quyền chồng chéo khiến truy vết và thu hồi mất thời gian.

## 6. Phân biệt nhiều role hợp lệ với role explosion

Không phải mọi tổ chức có nhiều role đều mắc lỗi thiết kế. Những hệ thống lớn có hàng nghìn chức năng hoặc nhiều tenant hợp pháp có thể cần nhiều role.

### Câu hỏi đánh giá

- Mỗi role có **mục đích khác biệt**, owner và nhóm đối tượng rõ không?
- Role có được gắn với **bằng chứng nghiệp vụ, phê duyệt và chu kỳ rà soát** không?
- Có nhiều role có **cùng effective permission set** nhưng khác tên không?
- Sự khác nhau giữa các role là **chức năng thực sự** hay chỉ là thuộc tính vùng/tenant?
- User có thể được mô tả bằng **ít role nền tảng hơn** cộng điều kiện resource mà vẫn giữ đúng quyền không?
- SoD có thể được kiểm chứng ở **permission-level** sau khi giải quyết kế thừa không?
- Quyền cũ sau Mover/Leaver có được thu hồi chính xác và nhanh không?
- Một người quản lý có thể hiểu và phê duyệt các role được gán trong thực tế không?

**Ngưỡng cảnh báo phải được điều chỉnh theo quy mô, số ứng dụng và tính nhạy cảm**, không có một tỷ lệ role/user duy nhất được công nhận cho mọi ngành.

## 7. Business role và technical role: tách lớp để giảm phức tạp

Một thiết kế IAM/IGA thường tách:

- **Business role:** chức năng theo nghiệp vụ, chẳng hạn FINANCE_ANALYST, SUPPORT_AGENT.
- **Technical role hoặc entitlement:** nhóm, role cloud, quyền SaaS hoặc policy cụ thể trong hệ thống đích.
- **Mapping:** quy tắc liên kết business role với các entitlement cần thiết, có version và owner.

~~~mermaid
flowchart TD
    HR[HRIS / Job Function] --> BR[Business Role: Finance Analyst]
    BR --> MAP[Role-to-Entitlement Mapping]
    MAP --> G1[SCIM Group: finance-read]
    MAP --> G2[Cloud Role: reports-viewer]
    MAP --> G3[DB Permission: read approved views]
    G1 --> APP1[SaaS]
    G2 --> APP2[Cloud]
    G3 --> APP3[Database]
    POLICY[ABAC: tenant/department/classification] --> APP1
    POLICY --> APP2
    POLICY --> APP3
~~~

### Ưu điểm

Một business role có thể cấp **nhiều entitlement kỹ thuật có căn cứ** mà không bắt manager chọn từng tên group đích. Khi SaaS đổi role nội bộ, đội IAM sửa **mapping kỹ thuật**, không nhất thiết tạo business role mới.

### Cảnh báo

Không biến business role thành **gói quyền khổng lồ** dùng chung cho mọi bộ phận. Nếu chức năng khác nhau về trách nhiệm nghiệp vụ, việc tách business role có thể cần thiết. **Tách lớp chỉ có giá trị khi role và mapping vẫn được kiểm soát, không phải thêm một lớp tên gọi che giấu quyền dư.**

## 8. Đưa resource scope ra khỏi tên role

Một nguồn gây explosion là tạo role riêng cho từng tài nguyên:

~~~text
REPORT_VIEWER_TENANT_A
REPORT_VIEWER_TENANT_B
REPORT_VIEWER_TENANT_C
REPORT_VIEWER_TENANT_D
~~~

Nếu policy engine và ứng dụng hỗ trợ **role binding kèm phạm vi tài nguyên**, có thể biểu diễn:

~~~json
{
  "subjectId": "person-2046",
  "role": "REPORT_VIEWER",
  "scope": {
    "tenantId": "tenant-a",
    "department": "Finance"
  },
  "effectiveFrom": "2026-11-23T00:00:00+07:00",
  "effectiveUntil": "2027-02-23T00:00:00+07:00"
}
~~~

Ví dụ này là **mô hình cấp quyền nội bộ**, không phải schema tiêu chuẩn SCIM hoặc OIDC. Điều quan trọng là backend phải **thực sự kiểm tra** scope của binding khi đọc đối tượng, lọc danh sách, export và gọi API; chỉ lưu scope trong IAM database mà ứng dụng bỏ qua vẫn là lỗi authorization.

### Những chiều thường phù hợp đưa vào policy

- **Tenant/organization** có ID bất biến và được xác minh.
- **Vùng/chi nhánh** nếu có nguồn có thẩm quyền.
- **Department/project** theo quan hệ còn hiệu lực.
- **Resource owner** hoặc nhóm sở hữu.
- **Classification/sensitivity** của dữ liệu.
- **Environment** (dev/test/prod) ở điểm thực thi có nhận diện tin cậy.
- **Thời hạn** và sự phê duyệt của quyền tạm thời.

Không phải chiều nào cũng nên đưa ra ngoài role. **Chức năng nghiệp vụ khác nhau** như *approve payment* và *read report* vẫn thường cần permission/role riêng để đảm bảo minh bạch.

## 9. Kết hợp RBAC với ABAC có kiểm soát

**Attribute-Based Access Control (ABAC)** dùng thuộc tính của subject, resource, action và context để quyết định quyền. Cách kết hợp phổ biến:

> RBAC xác định **loại thao tác mà vai trò được phép**, ABAC xác định **trên tài nguyên nào, trong điều kiện gì**.

~~~text
permit if
    subject.lifecycleState == ACTIVE
    and subject.hasRole("REPORT_VIEWER")
    and action == "report.read"
    and subject.tenantId == resource.tenantId
    and resource.department in subject.authorizedDepartments
    and context.authenticationMeetsPolicy
else deny
~~~

Đây là **giả mã minh họa**, không phải cú pháp có sẵn của một policy engine. Hệ thống phải lấy **lifecycleState, tenantId, authorizedDepartments và resource.department** từ nguồn được bảo vệ; không tin các giá trị do client tự khai.

### Lợi ích khi tránh explosion

Thay vì tạo role cho mọi tổ hợp **ReportViewer × Tenant × Department**, tổ chức giữ một role chức năng và ràng buộc bằng điều kiện ở lúc truy cập.

### Những chi phí mới cần quản lý

- Chất lượng và nguồn gốc thuộc tính, nhất là thuộc tính HRIS và tài nguyên.
- Độ trễ đồng bộ/thu hồi khi Mover hoặc Leaver.
- Khả năng explain quyết định và test policy.
- Ranh giới tenant, tính sẵn sàng của PIP/PDP.
- Chính sách xử lý khi thiếu thuộc tính: **mặc định an toàn**, không cấp quyền bừa.
- Khả năng ứng dụng đích hỗ trợ ABAC trên từng API/resource.

**ABAC không tự động chữa role explosion** nếu tổ chức vẫn tạo role tổ hợp bên cạnh các policy ABAC hoặc nếu dữ liệu thuộc tính thiếu chất lượng.

## 10. ReBAC và quyền quan hệ thay cho role cá nhân hóa

Trong các ứng dụng tài liệu/dự án, quyền thường phụ thuộc quan hệ: **owner**, **member**, **reviewer**, **delegated approver**.

Thay vì tạo role **PROJECT_ALPHA_EDITOR**, **PROJECT_BETA_EDITOR** cho mọi dự án, có thể mô hình:

~~~text
relationship:
    subjectId: person-2046
    relation: editor
    object: project-alpha
    validUntil: 2027-01-31T00:00:00Z
~~~

Điểm thực thi chỉ cho phép action **document.edit** nếu quan hệ hiện hành và các điều kiện RBAC/ABAC phù hợp.

### Lưu ý khi dùng ReBAC

- Phải đảm bảo quan hệ được tạo bởi **chủ thể có thẩm quyền**.
- Kiểm tra **quyền ủy quyền**: người chỉ có quyền đọc không được tự cấp quyền chỉnh sửa cho người khác.
- Quan hệ phải có **owner, scope, expiry và khả năng thu hồi**.
- Đối soát quan hệ khi dự án kết thúc hoặc người dùng Leaver.
- Thiết kế chính sách chống lạm dụng **quan hệ kế thừa**, chia sẻ dây chuyền và cross-tenant.

ReBAC có thể giảm role theo dự án, nhưng nếu bỏ quản trị quan hệ, tổ chức chỉ chuyển **role sprawl** thành **relationship sprawl**.

## 11. Role hierarchy: dùng khi hữu ích, tránh kế thừa sai

**Hierarchical RBAC** cho phép role có quan hệ kế thừa permission của role khác. Nó giúp giảm trùng lặp khi cấu trúc rõ ràng, nhưng cũng có thể làm rủi ro khó quan sát.

~~~mermaid
flowchart TD
    BASE[EMPLOYEE_BASIC] --> R[REPORT_READER]
    BASE --> T[TEAM_MEMBER]
    R --> A[FINANCE_ANALYST]
    T --> A
    A --> P[FINANCE_APPROVER]
    P --> C[Approval + SoD/ABAC checks]
~~~

Sơ đồ chỉ minh họa liên kết kế thừa; hướng chính xác và ngữ nghĩa “role cao hơn” cần được thống nhất theo mô hình nội bộ.

### Khi nên dùng

- Một tập quyền nền tảng **ổn định, ít rủi ro và được dùng rộng rãi**.
- Quy tắc kế thừa có thể được giải thích và kiểm thử.
- Các quyền đặc biệt không vượt qua ràng buộc SoD.

### Khi nên tránh

- Role cấp cao **tự động được mọi quyền** không cần thiết.
- Một thay đổi ở role cơ sở ảnh hưởng nhiều hệ thống mà không có impact analysis.
- Kế thừa nhiều lớp khiến manager không hiểu **effective permission**.
- Kế thừa vô tình vi phạm SoD hoặc mở quyền ở tenant khác.

**Role hierarchy không thay thế bước phân tích quyền hiệu lực cuối cùng.** Khi rà soát, phải tính cả role kế thừa, nhóm lồng nhau và quyền cấp trực tiếp.

## 12. Role mining: tìm mẫu từ dữ liệu thực tế

**Role mining** là quá trình phân tích **User–Permission Assignment** hiện tại để đề xuất các nhóm quyền có ý nghĩa. Có thể dùng thống kê tần suất, clustering, set-cover hoặc các phương pháp học máy, nhưng kết quả luôn cần được **chủ nghiệp vụ và security xác minh**.

### Pipeline role mining

~~~mermaid
flowchart TD
    INV[Inventory Users, Roles, Permissions] --> CLEAN[Chuẩn hóa và đối chiếu danh tính]
    CLEAN --> MAT[Ma trận User-Permission hiệu lực]
    MAT --> OUT[Phát hiện vai trò giống/trùng/chồng lấn]
    OUT --> CL[Clustering / gợi ý role]
    CL --> OWNER[Business owner + Security review]
    OWNER --> DESIGN[Role catalog chuẩn hóa]
    DESIGN --> TEST[Policy & SoD tests]
    TEST --> MIG[Migration có kiểm soát]
    MIG --> REC[Reconciliation / Access review]
~~~

### Các bước thực hiện

1. Thu thập role và entitlement từ IGA, IdP, SaaS, cloud, directory, PAM và ứng dụng thuộc phạm vi.
2. Chuẩn hóa user/subject ID, quyền trực tiếp, nhóm lồng nhau và quyền kế thừa.
3. Xác định tài khoản **inactive, Leaver, test và non-human** để xử lý theo mô hình riêng; không dùng lẫn làm mẫu quyền của nhân viên active.
4. Tính **effective permission set** của từng chủ thể, phạm vi và tenant.
5. Tìm role trùng quyền, role không dùng, nhóm permission thường đi cùng và biến thể chỉ khác một điều kiện.
6. Đề xuất role theo chức năng thực tế; phân biệt **baseline**, **sensitive permission** và **exception**.
7. Nhờ owner nghiệp vụ và security phê duyệt, kiểm tra SoD, least privilege, tenure và phân tách môi trường.
8. Thử chính sách với dữ liệu lịch sử hoặc shadow mode **không tự thay đổi quyền production**.
9. Thực hiện migration có kiểm soát, đọc lại trạng thái quyền và tiếp tục access review.

### Cảnh báo: không hợp thức hóa quyền đang sai

Dữ liệu hiện hành có thể chứa nhiều quyền **được cấp nhầm** hoặc tích lũy từ các lần Mover trước. Nếu role mining chỉ nhóm những quyền đang thấy, thuật toán có thể biến **privilege creep** thành **role chuẩn**.

**Dữ liệu quan sát là đầu vào, không phải nguồn chính sách có thẩm quyền.** Phải đối chiếu với job responsibilities, approval và SoD.

## 13. Ví dụ ma trận User–Permission khi role mining

Giả sử một nhóm người dùng có permission như sau:

| Người dùng | report.read | report.export | invoice.read | invoice.approve | payment.execute |
|---|---:|---:|---:|---:|---:|
| Lan (Analyst) | 1 | 0 | 1 | 0 | 0 |
| Minh (Analyst) | 1 | 0 | 1 | 0 | 0 |
| Huy (Approver) | 1 | 0 | 1 | 1 | 0 |
| Hà (Auditor) | 1 | 1 | 1 | 0 | 0 |
| Nam (Payment operator) | 0 | 0 | 1 | 0 | 1 |

Một đề xuất có thể là:

- **REPORT_READER**: report.read.
- **INVOICE_READER**: invoice.read.
- **FINANCE_APPROVER**: invoice.approve, với điều kiện SoD và resource scope.
- **REPORT_EXPORTER**: report.export theo phê duyệt và dữ liệu được phép.
- **PAYMENT_OPERATOR**: payment.execute, tách khỏi người duyệt.

Nhưng không nên kết luận ngay rằng **Huy phải có REPORT_READER** vì role hiện tại đang cấp nó. Cần xác minh nhu cầu công việc và policy. Tương tự, **Hà** có quyền export không có nghĩa mọi auditor mặc định được export dữ liệu nhạy cảm.

### Không chỉ xem bit 0/1

Ma trận đơn giản bỏ qua những khác biệt có thể rất quan trọng:

- Quyền áp dụng cho **tenant** nào.
- Action tác động lên **resource** và **classification** nào.
- Quyền có **thời hạn/phê duyệt** hay không.
- User đang có **quan hệ JML** nào.
- Quyền trực tiếp, kế thừa hay qua tài khoản phụ.
- Có phiên/token thực sự dùng quyền cũ sau khi thu hồi không.

Role mining thực tế phải bổ sung ngữ cảnh để tránh hợp nhất những quyền trông giống nhau nhưng khác phạm vi.

## 14. Các chỉ số phát hiện role explosion

Không có một ngưỡng chuẩn cho mọi doanh nghiệp; nên theo dõi **xu hướng**, mức độ hợp lý và rủi ro.

| Chỉ số | Cách hiểu | Dấu hiệu cần điều tra |
|---|---|---|
| **Role count** | Tổng số role có hiệu lực và role legacy | Tăng nhanh hơn thay đổi nhu cầu nghiệp vụ |
| **Roles per active user** | Số role người dùng active đang giữ (bao gồm kế thừa khi phân tích) | Nhiều role gần giống hoặc quyền chồng lấn |
| **Permissions per role** | Mức rộng của role | Role quá rộng, khó giải thích |
| **Empty roles** | Role không có assignee và không thuộc ngoại lệ giữ lại | Role rác hoặc catalog lỗi thời |
| **Duplicate permission sets** | Role khác tên nhưng cấp quyền hiệu lực giống nhau trong cùng scope | Có thể hợp nhất sau khi kiểm tra |
| **Role overlap** | Tỷ lệ quyền trùng giữa các role | Tách role quá mức hoặc phân cấp sai |
| **Direct grants** | Quyền cấp ngoài role/nhóm quản trị | Khó kiểm toán, tích lũy qua Mover |
| **Role assignment churn** | Tốc độ thay đổi gán role theo JML | Provisioning phức tạp, có thể phát sinh drift |
| **Leaver residual roles** | Role còn hoạt động sau khi quan hệ kết thúc | Rủi ro cao |
| **Mover revocation lag** | Thời gian quyền cũ còn hiệu lực | Chưa giảm privilege creep |
| **Unowned roles** | Role thiếu owner chịu trách nhiệm | Không ai có thể chứng nhận nhu cầu |
| **Certification completion quality** | Chất lượng/rủi ro của access review | Người duyệt chỉ bấm approve hàng loạt |

### Một vài công thức minh họa

Tỷ lệ role không có owner:

\[
UnownedRate = \frac{\text{số role không có owner hợp lệ}}{\text{tổng role trong phạm vi}}
\]

Tỷ lệ role không có assignee:

\[
EmptyRate = \frac{\text{số role không có assignee}}{\text{tổng role trong phạm vi}}
\]

Độ chồng lấn hai tập permission \(P_A\) và \(P_B\) có thể được quan sát bằng hệ số Jaccard:

\[
J(A,B)=\frac{|P_A\cap P_B|}{|P_A\cup P_B|}
\]

**Jaccard cao không tự chứng minh hai role được phép hợp nhất.** Một role có ngoại lệ SoD, scope khác hoặc policy nhạy cảm có thể cần giữ riêng dù permission list trùng gần hết.

## 15. SQL minh họa: phát hiện role không có người được gán

Một bước inventory phổ biến là tìm những role không có user-role assignment. Giả sử hệ thống có:

- **roles(role_id, role_name, owner_id)**.
- **user_roles(user_id, role_id, assigned_at)**.

SQL chỉ đọc dữ liệu:

~~~sql
SELECT
    r.role_id,
    r.role_name,
    r.owner_id,
    COUNT(ur.user_id) AS direct_assignees
FROM roles AS r
LEFT JOIN user_roles AS ur
    ON ur.role_id = r.role_id
GROUP BY r.role_id, r.role_name, r.owner_id
HAVING COUNT(ur.user_id) = 0;
~~~

**Không chạy DELETE dựa trực tiếp trên truy vấn này.** Một role không có gán trực tiếp vẫn có thể được **kế thừa** trong role hierarchy, được giữ cho break-glass, nằm trong kế hoạch onboarding hoặc dùng bởi assignment thuộc bảng khác.

### Truy vấn thống kê số role trực tiếp theo user

~~~sql
SELECT
    ur.user_id,
    COUNT(DISTINCT ur.role_id) AS direct_role_count
FROM user_roles AS ur
GROUP BY ur.user_id
ORDER BY direct_role_count DESC;
~~~

Chỉ số này **không tính quyền kế thừa**, nested groups, grant trực tiếp ngoài RBAC hoặc scope. Nó hữu ích để chọn mẫu điều tra, không chứng minh người đứng đầu danh sách đang được cấp sai.

### Điều kiện trước khi đo

- Loại trừ hoặc tách loại user service, test và dormant theo chính sách, không xóa chúng khỏi inventory.
- Dùng cùng kỳ snapshot và tenant để tránh sai số.
- Tính effective permission nếu đánh giá rủi ro, không chỉ role name.
- Kiểm tra các nguồn quyền không qua IGA, chẳng hạn local admin và direct SaaS grants.

## 16. Governance: ai được tạo, sửa, hợp nhất hoặc nghỉ hưu role?

Một role cần **vòng đời quản trị** tương tự tài nguyên bảo mật khác.

| Vai trò tham gia | Trách nhiệm |
|---|---|
| **Business owner** | Xác định mục đích nghiệp vụ, ai cần role, phạm vi sử dụng |
| **Application owner** | Xác minh permission/entitlement thực tế ở ứng dụng |
| **IAM/IGA owner** | Quản lý catalog, mapping, automation và JML |
| **Security/Compliance** | SoD, least privilege, rủi ro và audit |
| **HR/contract authority** | Nguồn trạng thái nhân sự, quan hệ và ngày hiệu lực |
| **Reviewer/Approver** | Chứng nhận role/assignment theo quyền hạn được giao |

### Vòng đời role đề xuất

~~~mermaid
stateDiagram-v2
    [*] --> Proposed: Đề xuất role mới
    Proposed --> Designed: Tài liệu hóa permission + scope
    Designed --> Reviewed: Owner/Security/SoD review
    Reviewed --> Active: Phê duyệt và triển khai
    Reviewed --> Rejected: Không cần role mới
    Active --> Monitored: Usage + access review
    Monitored --> Active: Tiếp tục hợp lệ
    Monitored --> Deprecated: Trùng/không còn mục đích
    Deprecated --> Migrating: Chuyển assignment sang model mới
    Migrating --> Retired: Đối soát quyền sau thay đổi
    Rejected --> [*]
    Retired --> [*]
~~~

### Điều kiện trước khi tạo role mới

1. Có **một chức năng nghiệp vụ khác biệt** chưa được role hiện tại hỗ trợ?
2. Sự khác biệt có thể biểu diễn tốt hơn bằng **resource scope, attribute hoặc delegation có hạn**?
3. Nếu cần role riêng, có **owner, purpose, permission set, SoD review**?
4. Có bao nhiêu người dùng thực sự cần role?
5. Role sẽ được **nghỉ hưu** khi nào hoặc khi điều kiện nào không còn?
6. Có **cơ chế test** tránh mở quyền trái ý khi triển khai?
7. Application/IdP/SCIM có thể thực hiện mapping tương ứng không?

**Phải có lộ trình xóa bỏ role cũ**, không chỉ quy trình tạo thêm role mới.

## 17. Phân quyền ngoại lệ mà không tạo role vĩnh viễn

Một nhóm thường tạo role mới khi có một yêu cầu kiểu: “Lan cần xuất báo cáo cho dự án A trong hai tuần”. Nếu role **EXPORT_SPECIAL_LAN_PROJECT_A** được tạo rồi bỏ quên, catalog sẽ tăng nhanh.

### Phương án kiểm soát

- **Temporary entitlement:** cấp quyền cụ thể có owner, effectiveFrom/effectiveUntil.
- **Resource-scoped binding:** cấp role hiện có với phạm vi dự án A.
- **JIT/PAM:** kích hoạt quyền nhạy cảm theo yêu cầu, bước xác thực tăng cường và thời hạn.
- **Delegation:** quyền ủy quyền có nguồn, giới hạn và ngày hết hạn.
- **Approval workflow:** yêu cầu giải trình, kiểm tra SoD và tự động thu hồi.

Ví dụ một grant nội bộ minh họa:

~~~json
{
  "identityId": "person-2046",
  "permission": "report.export",
  "resourceScope": "project-alpha",
  "approvedBy": "manager-710",
  "ticket": "REQ-2026-184",
  "validFrom": "2026-11-23T09:00:00+07:00",
  "validUntil": "2026-12-07T09:00:00+07:00",
  "reviewRequired": true,
  "status": "ACTIVE"
}
~~~

**Không coi bản ghi này là token hoặc entitlement có hiệu lực chỉ vì nó đã nằm trong database**. PEP/ứng dụng phải thực thi điều kiện scope và expiry, trong khi provisioning connector phải cấp/thu hồi quyền tương ứng nếu ứng dụng cần quyền vật lý ở đích.

### Khi ngoại lệ cần role riêng?

Một ngoại lệ được dùng rộng, lâu dài và phản ánh **một chức năng nghiệp vụ ổn định, được phê duyệt** có thể nên trở thành role chính thức. Quyết định phải dựa trên **chức năng và chính sách**, không dựa riêng vào số lượng yêu cầu.

## 18. Role explosion và Separation of Duties (SoD)

**SoD** ngăn một cá nhân nắm đồng thời hoặc thực hiện các bước có xung đột quyền hạn.

### Static SoD

Tổ chức có thể cấm một người được gán đồng thời hai permission/role xung đột, ví dụ:

- **vendor.create** và **vendor.payment.approve** trong cùng phạm vi, nếu chính sách cấm.
- **user.assignRole** và **accessReview.selfApprove**.
- **deployment.author** và **deployment.release** trong một số luồng nhạy cảm.

### Dynamic SoD

Cấm người **tạo** một hóa đơn thực hiện **invoice.approve** trên chính hóa đơn đó, dù role của họ có chức năng duyệt hóa đơn của người khác.

### Vì sao role explosion làm SoD khó hơn?

Một permission nhạy cảm có thể xuất hiện trong nhiều role, kể cả role được clone hoặc kế thừa. Chỉ kiểm tra **tên role** không đủ; phải tính **effective permissions** và **scope**.

Ví dụ:

~~~text
role_A: invoice.create + report.read
role_B: invoice.approve + report.read
role_C: invoice.create + invoice.approve (được clone nhầm)
~~~

Nếu chỉ xây rule “không cùng gán role_A và role_B”, người có **role_C** vẫn có hai quyền xung đột. Cần kiểm tra quy tắc theo **permission/action và ngữ cảnh** thay vì dựa vào tên role duy nhất.

## 19. Phương pháp giảm role explosion theo từng bước

Một chương trình tối ưu role không nên bắt đầu bằng việc xóa bừa role ít dùng. Hãy làm theo chu kỳ có kiểm soát:

### Bước 1 — Inventory và xác định coverage

Lấy role từ IAM/IGA, IdP, directory, SaaS, cloud và các hệ thống legacy. Ghi rõ nguồn nào thiếu quyền đọc, nhóm nested, direct grants hoặc phiên/token độc lập.

### Bước 2 — Chụp snapshot quyền thực tế

Tính user–role, role–permission, effective grants, scope, owner, tài khoản đặc biệt và thời điểm cập nhật. Đồng thời xác định nhân sự **active, Mover, Leaver và rejoiner**.

### Bước 3 — Phân loại role

Tách **business roles**, **technical roles**, **scope/tenant variants**, **temporary roles**, **privileged roles**, **service/workload roles**, **unused/legacy** và role đang tranh chấp owner.

### Bước 4 — Đo và đề xuất

Tìm role trùng permission, quyền giống nhau khác khu vực, role không dùng, direct grants và nơi có SoD conflict. Đưa ra **role model mới** dựa trên chức năng và policy scope.

### Bước 5 — Review với owner

Chủ nghiệp vụ xác nhận **nhu cầu** và mục đích, security xác nhận **least privilege/SoD**, application owner xác nhận **mapping khả thi ở hệ thống đích**.

### Bước 6 — Kiểm thử trong môi trường hoặc chế độ thích hợp

Chạy chính sách mới trên dữ liệu test hoặc **shadow evaluation** để so sánh quyết định permit/deny với quyền mong muốn. Không tự coi quyền cũ là chuẩn vì có thể chứa quyền dư.

### Bước 7 — Di trú theo đợt

Chuyển từng nhóm người dùng và ứng dụng sang role mới, giữ traceability role cũ → role mới → entitlement đích. Bảo đảm những quyền không còn hợp lệ **bị thu hồi**, không chỉ thêm role mới.

### Bước 8 — Đối soát và nghỉ hưu

Readback quyền ở đích, đo sai lệch, xác minh SoD và tính sẵn sàng của nghiệp vụ. Chỉ retire role cũ khi các assignment hợp lệ đã được chuyển và quyền không hợp lệ đã bị thu hồi đúng.

### Bước 9 — Ngăn tái phát

Thêm yêu cầu catalog/owner/review cho role mới, process cho exception có hạn và dashboard phát hiện role trùng hoặc không còn dùng.

## 20. Kế hoạch migration: không làm mất nghiệp vụ hoặc tái cấp quyền sai

Một migration role có thể làm gián đoạn sản xuất nếu role cũ đang cấp quyền thật cho ứng dụng, hoặc tạo lỗ hổng nếu giữ role cũ quá lâu.

### Trước migration

- Chụp **desired state và observed state** theo tài khoản/entitlement.
- Xác định permission nào thuộc **baseline**, **sensitive**, **exception** và **direct grant**.
- Tạo bảng ánh xạ role cũ → business role mới → entitlement/scope.
- Kiểm thử deny/permit quan trọng, tenant isolation và SoD.
- Xác định rollback plan có **kiểm soát bảo mật**, không mặc nhiên phục hồi quyền đã bị thu hồi vì Leaver.

### Trong migration

- Ưu tiên đợt nhỏ, có owner chịu trách nhiệm.
- Có thể chạy **song song đánh giá policy** mà chưa thực thi thay đổi thật.
- Theo dõi login failures, 403 hợp lệ/sai, chênh lệch tài nguyên được phép.
- Cập nhật SCIM/API/connector phù hợp, tôn trọng rate limit và idempotency.
- Khi gỡ role cũ, xác minh quyền không bị cấp gián tiếp bởi nhóm khác.
- Với quyền đặc quyền, cân nhắc JIT/approval thay vì gán thường trực.

### Sau migration

- Reconciliation tại từng ứng dụng: **đúng account, đúng group, đúng effective permissions**.
- Rà soát token/claim/session chứa role cũ theo thời hạn và rủi ro.
- Từ chối các action đã thu hồi; xác minh những action hợp lệ vẫn chạy.
- Ghi bằng chứng kiểm toán và retire role không còn assignee hoặc phụ thuộc hợp lệ.

**Rollback không được đảo ngược trạng thái JML mới hơn.** Nếu người dùng đã Leaver trong quá trình chuyển đổi, không có lý do “để hệ thống chạy lại” mà bật lại role cũ cho người đó.

## 21. Tích hợp IdP, SSO, SCIM và các role ở ứng dụng

### IdP/SSO

IdP xác thực và chuyển kết quả đăng nhập cho ứng dụng qua **SAML hoặc OIDC**. Nó có thể đưa group/role claim vào token/assertion, nhưng **token là một snapshot có thời hạn**. Nếu role bị thu hồi, ứng dụng vẫn có thể giữ claim cũ trong phiên/token nếu không có cơ chế cập nhật quyền.

### SCIM provisioning

IAM/IGA có thể ánh xạ business role vào **Group.members** hoặc các entitlement của ứng dụng qua SCIM/API. SCIM không tự định nghĩa nghĩa vụ nghiệp vụ của role; ứng dụng có thể ánh xạ nhóm sang quyền riêng.

### Role explosion ở điểm tích hợp

Giả sử IAM có **SALES_READER**, nhưng mỗi SaaS có các nhóm riêng như:

~~~text
crm_sales_read
reports_sales_view
docs_sales_member
analytics_sales_basic
~~~

Điều này **không nhất thiết là role explosion** nếu những nhóm kỹ thuật là chi tiết triển khai và được mapping rõ tới một business role. Vấn đề xảy ra khi từng nhóm kỹ thuật được copy thành **business role độc lập** rồi yêu cầu manager tự chọn và rà soát từng tên mà không hiểu chức năng.

### Những giới hạn cần biết

- Không phải mọi SaaS hỗ trợ **ABAC/role binding theo resource**. Khi đó có thể vẫn cần nhóm/role kỹ thuật cho từng scope.
- **SCIM User.groups** thường là read-only theo schema; thay đổi thành viên nhóm thường qua **Group.members** nếu nhà cung cấp hỗ trợ.
- Một số ứng dụng hỗ trợ JIT provisioning khi đăng nhập SSO; cách này **không tự bảo đảm Leaver deprovisioning**.
- Claims quá lớn có thể gây giới hạn kích thước token/header/cookie tùy sản phẩm; không nên đưa hàng trăm role không cần thiết vào token.
- Khi thay đổi role, ứng dụng phải **kiểm authorization ở resource server**, không tin mỗi lần SSO thành công là quyền luôn mới.

## 22. Role explosion trong Joiner–Mover–Leaver

### Joiner — Gán role theo nhu cầu thực

Khi người mới gia nhập:

1. HRIS xác nhận **personId, relationshipId, job function và effectiveAt**.
2. Identity proofing/enrollment diễn ra theo chính sách.
3. IAM tính **business role baseline** và các scope hợp lệ.
4. Approval/SoD áp dụng cho quyền đặc biệt, không mặc nhiên cấp qua role lớn.
5. IdP được chuẩn bị; SCIM/API tạo account và entitlement đúng thời điểm.
6. Ứng dụng thực thi RBAC/ABAC theo tài nguyên.
7. Readback xác minh quyền đúng, không có quyền ngoài nhu cầu.

**Không “copy role của người tiền nhiệm” một cách mù quáng.** Người tiền nhiệm có thể đã tích lũy quyền ngoại lệ qua nhiều năm.

### Mover — Thu hồi role cũ và quyền dư

Người chuyển từ Sales sang Finance có thể giữ lại các role như:

~~~text
sales_read_north
sales_export_north
sales_view_legacy
finance_read
finance_approve_temp
~~~

Chỉ **thêm finance_read** là chưa đủ. Hệ thống cần tính desired effective permissions mới, **gỡ role/entitlement của Sales không còn hợp lệ**, kiểm tra SoD và thu hồi quyền tạm đúng thời hạn. **Role explosion làm bước này khó hơn** vì quyền Sales có thể nằm trong nhiều tên role khác nhau.

### Leaver — Ngăn mọi quyền hiệu lực, không chỉ gỡ tên role

Khi quan hệ kết thúc:

- Disable IdP/login theo chính sách.
- Vô hiệu hóa account/nhóm ở hệ thống đích qua SCIM/API.
- Thu hồi hoặc chặn phiên, access/refresh token, API key, SSH key và credential độc lập.
- Xóa role assignment thuộc quan hệ đã hết hiệu lực, theo dõi cả quyền kế thừa và direct grants.
- Đối soát các action nhạy cảm như export, approve, deploy và IAM admin ở hệ thống đích.
- Nếu một quyền chưa thu hồi được, tạo finding có owner, hạn, mức rủi ro và biện pháp bù trừ.

**Không coi thao tác gỡ role ở IGA là bằng chứng API không còn cho phép truy cập**: cache, token, local session hoặc quyền trực tiếp vẫn có thể tồn tại.

### Rejoiner — Không hồi sinh role lịch sử

Khi nhân sự tái gia nhập, IAM có thể liên kết identity lịch sử theo chính sách nhưng phải **xác minh quan hệ mới**, enroll authenticator và tính role từ công việc hiện tại. Không tự cấp lại role/entitlement đã gỡ ở Leaver vì user có cùng email hoặc cùng identity ID.

## 23. Service account, workload và non-human roles

**Service account, device identity, bot và workload identity** cũng cần quyền, nhưng không nên đưa thẳng vào cùng danh mục role HR dành cho nhân viên.

| Chủ thể | Nhu cầu | Cách hạn chế sprawl |
|---|---|---|
| **Batch service** | Đọc một bucket và ghi một queue | Workload role scoped theo resource, owner |
| **CI/CD pipeline** | Deploy một service vào một environment | Role/policy cho workload và môi trường cụ thể |
| **Device identity** | Truy cập API thiết bị được ủy quyền | Device policy theo asset/MDM state |
| **Monitoring agent** | Đọc metric/log thuộc phạm vi | Permission set tối thiểu, không dùng admin |
| **Break-glass account** | Thao tác khẩn cấp được kiểm soát | Role riêng có audit, thời hạn và thủ tục rõ |

### Rủi ro role explosion cho máy

Một môi trường cloud có thể có hàng trăm service account với role được clone: **svcA-read**, **svcB-read**, **svcC-read**, trong khi khác biệt chỉ là bucket hoặc resource scope. Nếu nền tảng hỗ trợ binding/policy có điều kiện, có thể giảm lặp cấu hình. Nhưng **không nên hợp nhất bí mật/định danh nhiều workload chỉ để giảm số role**: việc tách workload identity giúp kiểm soát và audit tốt hơn.

### Owner Leaver

Nếu người sở hữu bot nghỉ việc, cần **chuyển owner, rà soát bí mật người cũ biết, rotate khi cần, đối soát permission**. Không tự xóa bot production còn hợp lệ hoặc duy trì role đặc quyền vô chủ vô hạn.

## 24. Tình huống thực hành: công ty có 480 role gần giống nhau

Giả sử một doanh nghiệp có:

- 8 nhóm chức năng.
- 5 vùng kinh doanh.
- 3 mức dữ liệu.
- 4 danh mục sản phẩm.

Nhóm IAM trước đây tạo một role riêng cho mọi tổ hợp: **8 × 5 × 3 × 4 = 480 biến thể** trong một ứng dụng. Trên thực tế nhiều biến thể có **cùng tập action**; chỉ khác vùng, sản phẩm và classification.

### Giai đoạn A — Phát hiện

Dashboard cho thấy role count cao, nhiều role không có owner, người dùng active trung bình giữ nhiều role phân mảnh và tỷ lệ Mover giữ quyền cũ tăng. Một số role chỉ khác tên sản phẩm nhưng có permission giống nhau. Nhóm mở dự án chuẩn hóa.

### Giai đoạn B — Phân tích

Role mining cho thấy **8 chức năng thực sự khác biệt**, còn vùng/sản phẩm/mức dữ liệu là điều kiện phạm vi. Security phát hiện một số role xuất dữ liệu nhạy cảm được clone sai. Owner xác nhận **export** phải là permission riêng có approval và độ tin cậy phiên phù hợp.

### Giai đoạn C — Thiết kế

Kiến trúc mới giữ business roles theo 8 nhóm chức năng, scope bằng **region/product**, classification và SoD bằng policy. Những action đặc quyền thực sự khác biệt được giữ riêng, không ép vào vai trò nền tảng.

~~~json
{
  "identityId": "person-2046",
  "businessRoles": ["SALES_ANALYST"],
  "bindings": [
    {
      "role": "SALES_ANALYST",
      "regions": ["north"],
      "productLines": ["product-a", "product-b"]
    }
  ],
  "exceptionGrants": [
    {
      "permission": "customer.export",
      "resourceScope": "region:north",
      "approvedUntil": "2026-12-07T00:00:00+07:00"
    }
  ]
}
~~~

Đây là **mô hình minh họa**. Để hoạt động an toàn, ứng dụng bắt buộc phải thực thi region/product scope và expiry; chỉ chuyển tên role vào JSON mà không thay đổi enforcement sẽ không giảm rủi ro.

### Giai đoạn D — Migration

Nhóm IAM tạo mapping cũ → mới, kiểm tra shadow decisions và triển khai theo vùng. Role cũ chỉ được retire khi quyền hợp lệ đã chuyển và quyền dư bị gỡ. Security kiểm thử **cross-region read, export không được duyệt, self-approval và stale token**.

### Giai đoạn E — Mover và Leaver

Lan từ North Sales chuyển sang Finance: IAM gỡ binding North Sales, cấp quyền Finance theo phê duyệt. Nếu token cũ còn role Sales, backend kiểm tra thuộc tính/scope hiện hành trước action nhạy cảm. Sau Leaver, API phải từ chối quyền cũ dù session/claim chưa hết hạn.

### Kết luận tình huống

Mục tiêu **không phải giảm 480 về đúng 8 bằng mọi giá**. Mục tiêu là giảm số cấu hình role tổ hợp không cần thiết, giữ những phân biệt nghiệp vụ quan trọng và đảm bảo **effective permissions** được quản lý, hiểu, thu hồi và kiểm toán chính xác.

## 25. Checklist chống Role explosion

1. **Định nghĩa:** role có đại diện cho chức năng nghiệp vụ thật, hay chỉ mã hóa region/tenant/product?
2. **Owner:** mỗi role có người chịu trách nhiệm, purpose, scope, permission và chu kỳ review?
3. **Catalog:** naming convention, lifecycle và versioning có được áp dụng nhất quán?
4. **Metrics:** có đo role count, empty/unowned roles, overlap, direct grants và trend theo thời gian?
5. **Effective permissions:** có tính quyền qua hierarchy, nested group, direct grant và scope thay vì chỉ role name?
6. **Role mining:** dữ liệu đầu vào có được làm sạch và kiểm tra bởi business/security, không hợp thức hóa privilege creep?
7. **Business/technical separation:** business roles có được tách khỏi entitlement cụ thể ở SaaS/cloud?
8. **RBAC + ABAC:** có thể đưa tenant, region, data classification và resource scope vào policy mà ứng dụng thực thi thật không?
9. **ReBAC:** quyền theo owner/member/project có mô hình quan hệ và expiry thay vì tạo role cho từng dự án không?
10. **Hierarchy:** kế thừa role có được review SoD và kiểm tra ảnh hưởng thay đổi?
11. **Exceptions:** quyền đặc biệt được cấp có thời hạn và approval thay vì role cá nhân vĩnh viễn?
12. **Privileged access:** admin/export/deploy/approve được kiểm soát riêng với JIT/PAM và MFA khi cần?
13. **SCIM/IdP:** mapping Group/entitlement đã chuẩn hóa, claim/token không bị phình và role cũ được thu hồi?
14. **Joiner:** cấp quyền nền tảng từ quan hệ chính thức, không copy mọi role của đồng nghiệp?
15. **Mover:** có kiểm tra giảm quyền cũ, đặc biệt role clone và quyền đặc biệt?
16. **Leaver:** đã gỡ entitlement ở đích và chặn token/session/local account còn quyền?
17. **Non-human:** workload có role/owner/scope riêng, không bị lẫn với nhân viên?
18. **Testing:** có thử deny/permit theo resource, cross-tenant, SoD, JML và claim cũ?
19. **Migration:** có so sánh desired–observed, shadow test, rollback không tái cấp quyền trái phép?
20. **Audit:** có thể trả lời vì sao user này có action kia và ai đã phê duyệt không?
21. **Governance:** trước khi tạo role mới, có xét các phương án binding, ABAC, temporary grant và role hiện có?
22. **Coverage:** có ghi rõ ứng dụng legacy hoặc quyền trực tiếp không thể quan sát đầy đủ khi báo cáo tuân thủ không?

### Ghi nhớ

**Role explosion là sự tăng trưởng role quá mức khiến lớp RBAC khó hiểu, khó cấp đúng, khó kiểm toán và khó thu hồi**, đặc biệt trong các sự kiện **Mover và Leaver**. Nguyên nhân thường nằm ở việc biến mọi tổ hợp bộ phận, vùng, sản phẩm, môi trường và ngoại lệ thành role vĩnh viễn. Giải pháp không phải xóa role hàng loạt mà là **quản trị role theo chức năng, dùng role mining có kiểm chứng, tách business role khỏi technical entitlement, kết hợp RBAC với ABAC/ReBAC khi hệ thống thực thi được, kiểm soát SoD/JIT và quyền có thời hạn**. Trong **IAM Identity Lifecycle**, thành công chỉ được xác nhận khi **IdP/SSO, SCIM, role/entitlement, phiên/token và quyền thực tế ở hệ thống đích** đã được đối soát theo đúng quan hệ **Joiner–Mover–Leaver**, không còn quyền truy cập tồn dư trái chính sách.
