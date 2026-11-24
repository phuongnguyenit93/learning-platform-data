# Role mining trong RBAC: khai phá vai trò từ quyền truy cập và kiểm chứng theo vòng đời danh tính

**Role mining (khai phá vai trò)** là quá trình phân tích dữ liệu **người dùng–tài khoản–quyền truy cập (user/account–entitlement)**, kết hợp thông tin tổ chức và nghiệp vụ, để **đề xuất những vai trò (role) có thể tái sử dụng** trong mô hình **Role-Based Access Control (RBAC)**. Thay vì cấp riêng từng quyền cho hàng nghìn tài khoản, tổ chức tìm những tập quyền thường đi cùng nhau, xác định nhiệm vụ mà chúng phục vụ, rồi xây dựng **vai trò có tên, owner, phạm vi và quy tắc cấp/thu hồi** rõ ràng.

Role mining thường xuất hiện khi hệ thống đã có nhiều **direct grant**, nhóm được tạo tùy tiện, quyền cũ sau khi nhân viên đổi bộ phận hoặc tài khoản chưa được gắn với vai trò nghiệp vụ. Nó giúp **đơn giản hóa quản trị**, nhưng **không phải phép biến dữ liệu hiện trạng thành chính sách đúng một cách tự động**. Nếu quyền đầu vào đã sai, thuật toán có thể học đúng một *mẫu sai* rồi biến quyền thừa thành “role chuẩn”.

Bài học thuộc chương **RBAC** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tập trung quản lý danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh người mới, tạo tài khoản và cấp quyền, điều chỉnh khi thay vai trò, rồi rà soát và thu hồi khi kết thúc nhiệm vụ. **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** cung cấp dữ liệu và điểm thực thi để triển khai các vai trò được kiểm chứng, ngăn **quyền truy cập tồn dư**.

**Thông điệp trung tâm:** **Role mining sinh ra *ứng viên vai trò*, không tự động phê duyệt vai trò.** Vai trò chỉ nên được sử dụng khi có ý nghĩa nghiệp vụ, quyền tối thiểu, ranh giới tài nguyên rõ, owner chịu trách nhiệm, kiểm tra xung đột nhiệm vụ và cơ chế vận hành xuyên suốt JML.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mục đích, dữ liệu đầu vào và sản phẩm đầu ra của **role mining** trong một chương trình RBAC.
2. Phân biệt **role mining, role engineering, access review, entitlement cleanup và role certification**.
3. Chuẩn hóa dữ liệu **identity–account–entitlement**, lập ma trận user–permission và xác định **quyền hiệu dụng**.
4. So sánh tiếp cận **bottom-up, top-down và hybrid**, cùng ưu nhược điểm của từng cách.
5. Thực hiện ví dụ khai phá tập quyền lặp lại, đánh giá **coverage, overgrant, exception, role count và role overlap**.
6. Nhận diện rủi ro **role explosion, privilege creep, SoD conflict, quyền đặc quyền, tenant leakage và vai trò sinh từ dữ liệu sai**.
7. Chuyển ứng viên thành **business role/technical role** có owner, policy và quy trình phê duyệt.
8. Thiết kế triển khai qua **IAM/IGA, IdP, directory, SCIM/API và authorization tại ứng dụng**.
9. Liên hệ **Joiner, Mover, Leaver, service account, token/session và audit** với việc duy trì role catalog.

## 2. Vì sao doanh nghiệp cần role mining?

Giả sử tổ chức có 700 nhân viên và 30 ứng dụng. Qua nhiều năm, quyền được cấp theo ticket, nhóm, role cục bộ và thao tác trực tiếp. Hai người cùng nhiệm vụ có thể có quyền gần giống nhau, nhưng cách gán khác nhau; người đã chuyển phòng ban còn giữ group cũ; nhà thầu hết dự án vẫn có quyền chia sẻ.

Nếu mỗi lần Joiner đều **sao chép quyền của nhân viên cũ**, sai lệch sẽ tích lũy. Nếu Mover chỉ cộng thêm quyền mới, role cũ không được thu hồi. Khi Leaver, IAM có thể không biết quyền thuộc ứng dụng nào để xử lý.

**Role mining** giúp đặt câu hỏi:

- Những **quyền nào thực sự thường cùng xuất hiện** trong cùng nhiệm vụ?
- Các tập quyền đó có **lý do nghiệp vụ và chủ sở hữu** không?
- Có thể tạo **vai trò chung và phần quyền bổ sung có kiểm soát** thay vì quá nhiều role riêng lẻ không?
- Ai nên nhận vai trò và **trong bao lâu**?
- Quyền nào là **ngoại lệ**, sai lệch, quá đặc quyền hoặc đã hết hiệu lực?
- Khi nhân viên đổi vị trí, **vai trò nào phải bị gỡ** thay vì được giữ theo thói quen?

### 2.1. Vai trò RBAC là gì?

Trong RBAC, một **role** đại diện tập permission gắn với nhiệm vụ hoặc chức năng. Người dùng được **gán role**; role được **gán permission**. Tùy mô hình, session có thể kích hoạt một tập role hợp lệ và có thể có **role hierarchy** cùng ràng buộc phân tách nhiệm vụ.

~~~text
Subject / User
    |
    | user-role assignment
    v
Role: sales_representative
    |
    | role-permission assignment
    +---- lead.read
    +---- lead.update
    +---- quote.create

Quyền thực tế còn bị giới hạn bởi:
  account/engagement status, tenant, project,
  resource ownership, SoD, session và ABAC policy.
~~~

**Đếm role chưa đủ để khẳng định an toàn.** Một role chứa `production.admin` có phạm vi quá rộng có thể dễ quản trị nhưng gây rủi ro lớn hơn nhiều role hạn quyền.

## 3. Phân biệt role mining và những hoạt động gần kề

| Hoạt động | Trọng tâm | Sản phẩm |
|---|---|---|
| **Role mining** | Khám phá mẫu quyền/người dùng từ dữ liệu và ngữ cảnh | Các **candidate roles** và gợi ý phân nhóm |
| **Role engineering** | Thiết kế role dựa trên nhiệm vụ, quy trình và kiểm soát | Role có ý nghĩa nghiệp vụ, policy và cấu trúc chuẩn |
| **Role certification** | Người có thẩm quyền xác nhận role còn đúng/đủ | Phê duyệt, điều chỉnh hoặc loại bỏ role |
| **Access review** | Rà soát quyền đang có của subject/tài nguyên | Keep/revoke/escalate và bằng chứng |
| **Entitlement cleanup** | Loại grant không hợp lệ, trùng, hết hạn hoặc quá rộng | Tập quyền sạch hơn và ít ngoại lệ hơn |
| **Role assignment** | Gán role đã duyệt cho subject đủ điều kiện | User–role binding có thời hạn và căn cứ |
| **Role lifecycle management** | Tạo, đổi, hợp nhất, phiên bản hóa, ngừng role | Danh mục vai trò được quản trị lâu dài |

**Role mining không thay thế access review.** Nếu một nhóm người đều đang giữ quyền export tài chính không đúng, dữ liệu mining có thể cho thấy nhóm quyền rất phổ biến. Nhiệm vụ của review và business owner là **xác minh có được phép hay không**.

**Role mining cũng không phải toàn bộ role engineering.** Khai phá bottom-up cung cấp bằng chứng hiện trạng; thiết kế top-down cung cấp **nghĩa vụ, công việc và giới hạn đáng ra phải có**. Hai chiều thường cần kết hợp.

## 4. Định nghĩa dữ liệu: User, Account, Role, Permission và Entitlement

Một bài toán mining cần **mô hình dữ liệu nhất quán** trước khi chọn thuật toán.

| Khái niệm | Ví dụ | Điểm cần chú ý |
|---|---|---|
| **Canonical identity** | `personId=P-2048` | Một người có thể có nhiều account |
| **Application account** | `crmUserId=CRM-908` | ID do ứng dụng quản lý, cần mapping |
| **Permission** | `invoice.read` | Hành động logic trên loại tài nguyên |
| **Entitlement/grant** | `invoice.read@tenant=A` | Quyền được cấp có **scope và nguồn** |
| **Role** | `finance_reader` | Tập permission có policy |
| **User-role assignment** | P-2048 → finance_reader | Có thể có tenant, thời hạn, căn cứ |
| **Role-permission assignment** | finance_reader → invoice.read | Cần giới hạn bởi policy tài nguyên |
| **Direct grant** | P-2048 → invoice.export | Có thể nằm ngoài role |
| **Subject attributes** | department, project, location, status | Có nguồn có thẩm quyền và độ mới |
| **Grant provenance** | Request, manager, role, ticket, JIT | Giải thích vì sao quyền tồn tại |

### 4.1. Ma trận User–Permission (UP)

Cho:

- `U` là tập subject hợp lệ để phân tích.
- `P` là tập permission hoặc entitlement đã chuẩn hóa.
- `E ⊆ U × P` là quan hệ **quyền quan sát được** trong snapshot.

Ma trận nhị phân có:

~~~text
M[u, p] = 1 nếu subject u có entitlement p
M[u, p] = 0 nếu không quan sát thấy entitlement p
~~~

**Cẩn trọng:** `M[u,p]=1` nghĩa là *đang có quyền theo dữ liệu đã thu thập*, **không có nghĩa được cấp đúng**. `M[u,p]=0` có thể do thiếu connector, dữ liệu chưa đồng bộ hoặc grant nằm ở hệ thống khác. Tổ chức cần tách **unknown** khỏi **không có quyền** khi độ phủ dữ liệu chưa đầy đủ.

### 4.2. Quyền hiệu dụng không luôn bằng quyền được gán trực tiếp

Quyền có thể đến từ:

- Nhóm directory/IdP và **nhóm lồng nhau**.
- Role ứng dụng, role phân cấp và policy resource.
- Direct ACL/share tới account hoặc subject.
- Quyền đặc quyền tạm thời qua PAM/JIT.
- Token, API key, local session hoặc khả năng được cấp ngoài IAM.
- Điều kiện ABAC và quan hệ với dữ liệu cụ thể.

Do đó cần phân biệt:

~~~text
Assigned entitlements: các grant đã cấu hình
Effective access: khả năng thực tế mà PEP/ứng dụng cho phép

Hai giá trị không nhất thiết bằng nhau:
  - group lồng nhau có thể mở thêm quyền
  - policy deny có thể chặn grant đã gán
  - token/cache cũ có thể giữ quyền sau khi gỡ group
~~~

Mining thường bắt đầu từ **assigned/effective entitlements** tùy mục tiêu, nhưng phải ghi rõ loại dữ liệu. **Không tự coi token còn hạn, log có hành động thành công hay một role name là toàn bộ bằng chứng quyền hiệu dụng**.

## 5. Nguồn dữ liệu cho role mining

| Nguồn | Dữ liệu quan trọng | Giới hạn thường gặp |
|---|---|---|
| **HR** | Person ID, bộ phận, vị trí, manager, trạng thái | Không bao phủ đầy đủ contractor/workload |
| **VMS/hợp đồng** | Engagement, sponsor, ngày hiệu lực/hết hạn | Có thể thiếu account ngoài luồng |
| **IAM/IGA** | Identity mapping, request, approval, nhóm và role | Quyền cấp trực tiếp ở đích có thể không có |
| **Directory/IdP** | User, group, nested group, trạng thái account | Nhóm không chắc biểu đạt permission nghiệp vụ |
| **SCIM/provisioning logs** | User/group được tạo/cập nhật ở đích | Lệnh thành công chưa bảo đảm ứng dụng áp đủ quyền |
| **Ứng dụng/API** | Local role, ACL, resource policy, direct grant | Mapping và tên quyền khác nhau |
| **Cloud/PAM/secret manager** | Privileged role, service principal, key, owner | Cần phân biệt người và workload |
| **Access logs** | Dấu vết thao tác thực tế và bất thường | Không dùng ≠ không cần; không có log ≠ không có quyền |
| **Service catalog/CMDB** | App/workload owner, môi trường, phụ thuộc | Metadata có thể lỗi thời |
| **Audit/access review** | Kết luận giữ/thu hồi, ngoại lệ và lý do | Kết quả review cũng có thể cũ hoặc thiếu bằng chứng |

### 5.1. Cửa sổ thời gian là quyết định thiết kế

Role mining dựa trên một snapshot ngày cuối tháng có thể bao gồm:

- Nhân viên vừa chuyển bộ phận **chưa kịp thu hồi quyền cũ**.
- Contractor sắp hết hạn; một tuần sau không còn hợp lệ.
- Quyền admin được cấp tạm cho sự cố rồi quên gỡ.
- Những quyền chỉ xuất hiện trong đợt đóng sổ cuối quý.

Nên ghi **`snapshotAt`, `effectiveAt`, trạng thái JML, khoảng thời gian lấy log và mức độ hoàn thiện dữ liệu**. Tách **quyền thường trực**, **quyền tạm thời**, **quyền khẩn cấp** và **các exception**; tránh lấy dữ liệu của Leaver làm khuôn mẫu cho Joiner mới.

## 6. Chuẩn hóa dữ liệu trước khi khai phá

Một quy trình chuẩn hóa có thể gồm:

1. **Đối chiếu identity:** Map account đích về canonical person/workload, đúng tenant.
2. **Xác định eligibility:** Lọc hoặc đánh dấu subject chưa active, Leaver, contractor hết hạn, account mồ côi.
3. **Chuẩn hóa permission:** Dùng tên logic, application ID, action và scope rõ ràng.
4. **Giải quyết quyền kế thừa:** Xác định nhóm lồng nhau, role hierarchy và grant trực tiếp theo khả năng.
5. **Phân loại mức rủi ro:** Read, write, export, approve, admin, production, secret access.
6. **Phân biệt scope:** Tenant, dự án, khu vực, môi trường, dữ liệu nhạy cảm.
7. **Ghi nguồn và thời gian:** Grant provenance, người duyệt, TTL và phiên bản policy.
8. **Đánh dấu unknown:** Quyền chưa đọc được, connector lỗi, app chưa kiểm kê.
9. **Giảm dữ liệu:** Chỉ dùng thuộc tính cá nhân cần thiết, bảo vệ tập dữ liệu mining.
10. **Xác nhận độ phủ:** Không bắt đầu triển khai role khi ma trận còn thiếu hệ thống trọng yếu.

### 6.1. Ví dụ chuẩn hóa tên quyền

~~~text
Nguồn:
  CRM role:   "CanViewLead"
  API claim:  "leads_read"
  Group name: "APP_CRM_LEAD_VIEW"
  Local ACL:  "read:/leads"

Permission logic có thể đề xuất:
  app=CRM
  action=lead.read
  resourceType=lead
  tenantScope=được xác minh riêng

Không tự hợp nhất nếu ý nghĩa thực tế khác nhau:
  API leads_read có thể bao gồm toàn tenant,
  còn local ACL chỉ có một project.
~~~

**Điều kiện quan trọng:** Hai entitlement có tên gần giống nhau không chắc có cùng hiệu lực; ngược lại, cùng một tên role giữa hai hệ thống có thể mang quyền rất khác. Mapping phải được **application owner xác nhận**.

### 6.2. Không gộp con người và service account

Một service account có thể dùng quyền đọc hóa đơn giống Finance nhưng **không phải nhân viên Finance**. Nếu mining chung, thuật toán có thể đề xuất cấp role người dùng cho workload hoặc ngược lại. Nên phân nhóm theo **loại subject** trước, rồi quản lý role/workload entitlement có owner và thời hạn riêng.

## 7. Quy trình Role mining từ dữ liệu đến role được duyệt

~~~mermaid
flowchart TD
    A["HR / VMS / IAM / IdP / app<br/>Snapshot entitlement"] --> B["Liên kết identity-account<br/>chuẩn hóa permission + scope"]
    B --> C["Lọc Leaver, exception,<br/>privileged/JIT và dữ liệu lỗi"]
    C --> D["Tạo ma trận User–Permission<br/>và bối cảnh nghiệp vụ"]
    D --> E["Khai phá candidate roles<br/>bottom-up / top-down / hybrid"]
    E --> F["Chấm điểm coverage,<br/>overgrant, SoD, risk, complexity"]
    F --> G{"Business/application owner<br/>xác nhận nhiệm vụ và quyền?"}
    G -->|Không| H["Chỉnh/split/merge hoặc<br/>loại candidate"]
    H --> E
    G -->|Có| I["Kiểm SoD + least privilege<br/>định nghĩa owner, TTL, policy"]
    I --> J["Pilot có kiểm soát<br/>mapping, cấp và thu hồi"]
    J --> K{"Readback effective access<br/>và JML test đạt?"}
    K -->|Không| H
    K -->|Có| L["Publish role catalog<br/>đo drift và re-certification"]
~~~

**Đây là pipeline có con người trong vòng kiểm soát**, không phải một thuật toán tự động cấp quyền. Candidate role nên có **dấu vết dữ liệu tạo ra nó**, kết luận phê duyệt và thời gian hiệu lực; role bị từ chối cần ghi lý do để các vòng mining sau không tiếp tục đề xuất sai.

### 7.1. Đầu ra nên có gì?

Mỗi ứng viên có thể chứa:

- `candidateRoleId` và tên tạm.
- Mục đích/nghiệp vụ nghi vấn, nhóm user mẫu.
- Danh sách permission, hệ thống, tenant/resource scope.
- Số subject có tập quyền đó và **support**, mức biến thiên.
- Tỷ lệ bao phủ và số entitlement phải xử lý như ngoại lệ.
- Permission nhạy cảm, SoD conflict và các cờ rủi ro.
- Dữ liệu thời điểm, nguồn, khoảng nhìn và chất lượng mapping.
- Người được đề xuất làm **business owner** và **technical owner**.
- Trạng thái: `PROPOSED` → `REVIEWED` → `APPROVED` hoặc `REJECTED`.
- Bằng chứng thử nghiệm và quyết định cuối.

## 8. Ba phương pháp: bottom-up, top-down và hybrid

### 8.1. Bottom-up mining

**Bottom-up** khởi đầu từ dữ liệu quyền thực tế. Thuật toán tìm các tập permission thường xuất hiện cùng nhau, người dùng có mẫu tương tự hoặc cấu trúc permission có thể gom thành role.

**Điểm mạnh:**

- Khám phá các pattern tồn tại nhưng chưa được tài liệu hóa.
- Tìm các entitlement lặp lại có thể gom vào role chung.
- Hỗ trợ hệ thống legacy có nhiều direct grants.

**Giới hạn:**

- **Có thể hợp thức hóa quyền thừa/đã lỗi thời**.
- Không thể từ thống kê suy ra đầy đủ nhiệm vụ và SoD.
- Bị ảnh hưởng bởi dữ liệu thiếu, nhóm quá rộng hoặc quyền admin hiếm.
- Kết quả có thể tạo ra **role khó giải thích với quản lý nghiệp vụ**.

### 8.2. Top-down role engineering

**Top-down** bắt đầu từ sơ đồ tổ chức, chức năng công việc, quy trình và trách nhiệm. Ví dụ một vai trò `invoice_reviewer` được thiết kế từ quy trình đối chiếu hóa đơn, không phải vì mọi người đang cùng có quyền.

**Điểm mạnh:** Có ý nghĩa nghiệp vụ, dễ đặt owner, ràng buộc SoD và lifecycle. **Giới hạn:** Bỏ sót thực tế ứng dụng legacy và quyền phát sinh ngoài quy trình nếu chỉ phỏng vấn.

### 8.3. Hybrid mining

**Hybrid** kết hợp:

1. Định nghĩa **nhóm nhiệm vụ và policy đáng ra phải có** theo top-down.
2. Dùng mining bottom-up để tìm quyền đang được thực thi/cấp.
3. So sánh **quyền quan sát được** với **quyền mong muốn**.
4. Review từng khoảng chênh lệch: cần cấp, cần thu hồi, ngoại lệ hợp lệ hay lỗi dữ liệu.
5. Chuyển kết quả đã duyệt thành role và quy trình JML.

| Tiêu chí | Bottom-up | Top-down | Hybrid |
|---|---|---|---|
| Điểm khởi đầu | Quyền hiện trạng | Nhiệm vụ và quy trình | Cả hai |
| Tìm direct grant bị quên | Có ích | Có thể bỏ sót | Có ích |
| Giải thích nghiệp vụ | Cần review thêm | Thường rõ hơn | Có thể vừa rõ vừa sát thực tế |
| Nguy cơ học quyền sai | Cao nếu dữ liệu chưa sạch | Thấp hơn nhưng vẫn có sai sót thiết kế | Kiểm soát được bằng đối chiếu |
| Thời gian chuẩn bị | Tốn công thu thập/chuẩn hóa | Tốn công nghiệp vụ/owner | Tốn cả hai, đổi lại khả năng xác minh |
| Phù hợp | Khám phá hệ thống legacy | Thiết kế hệ thống mới | Cải tổ RBAC doanh nghiệp |

**Trong môi trường JML**, hybrid thường là lựa chọn đáng cân nhắc vì cần vừa nhận diện **quyền còn sót sau Mover/Leaver**, vừa xây bộ role đúng cho **Joiner tương lai**.

## 9. Ví dụ cụ thể: khai phá role từ ma trận quyền

Xét bảy subject **đang active** đã được phân loại là con người. Một tập permission mẫu:

| Mã | Permission | Ý nghĩa |
|---|---|---|
| **L** | `lead.read` | Xem khách hàng tiềm năng |
| **U** | `lead.update` | Cập nhật lead |
| **Q** | `quote.create` | Tạo báo giá |
| **A** | `quote.approve` | Phê duyệt báo giá |
| **I** | `invoice.read` | Đọc hóa đơn |
| **E** | `invoice.export` | Xuất dữ liệu hóa đơn |

Ma trận snapshot:

| Subject | Bộ phận | L | U | Q | A | I | E |
|---|---|---:|---:|---:|---:|---:|---:|
| An | Sales – Bắc | 1 | 1 | 1 | 0 | 0 | 0 |
| Bình | Sales – Bắc | 1 | 1 | 1 | 0 | 0 | 0 |
| Chi | Sales – Nam | 1 | 1 | 1 | 0 | 0 | 0 |
| Dũng | Sales manager – Bắc | 1 | 1 | 1 | 1 | 0 | 0 |
| Hà | Finance | 0 | 0 | 0 | 0 | 1 | 1 |
| Lan | Finance | 0 | 0 | 0 | 0 | 1 | 1 |
| Minh | Finance trainee | 0 | 0 | 0 | 0 | 1 | 0 |

### 9.1. Nhìn ra các mẫu quyền

- Quyền **L + U + Q** cùng xuất hiện ở **4 người**. Có thể đề xuất `sales_representative`.
- Quyền **I** xuất hiện ở **3 người**. Có thể tạo `finance_reader` làm nền.
- Quyền **E** xuất hiện ở **2 người** trong nhóm có I. Có thể là **role bổ sung** hoặc quyền nhạy cảm theo approval riêng.
- Quyền **A** chỉ xuất hiện ở Dũng. Không nên tự cấp `quote.approve` cho cả nhóm Sales chỉ vì cùng có L/U/Q.

Các candidate:

| Candidate | Permission | Có thể cấp cho | Cần xem lại |
|---|---|---|---|
| `sales_representative` | L, U, Q | An, Bình, Chi, Dũng | Quyền lead theo vùng và tenant |
| `sales_quote_approver` | A | Dũng nếu được phê duyệt | SoD giữa tạo và phê duyệt chính mình |
| `finance_reader` | I | Hà, Lan, Minh | Dữ liệu hóa đơn trong phạm vi nào |
| `finance_exporter` | E | Hà, Lan nếu được phê duyệt | Quyền export nhạy cảm, giám sát, TTL |

**Đây là gợi ý, chưa phải chính sách được duyệt.** Application owner cần xác nhận liệu Dũng vừa tạo vừa phê duyệt báo giá có vi phạm SoD không. Có thể tổ chức cho người quản lý có cả hai khả năng nhưng **cấm phê duyệt báo giá do chính họ tạo** bằng kiểm tra quan hệ tại tài nguyên. Nếu SoD đòi tách vai trò tuyệt đối, cần chỉnh role/assignment.

### 9.2. Đừng biến scope vùng thành role riêng vô hạn

An/Bình thuộc Bắc, Chi thuộc Nam. Nếu các thao tác giống nhau nhưng tài nguyên khác vùng, có thể kết hợp:

~~~text
Role (RBAC): sales_representative
  Permissions: lead.read, lead.update, quote.create

Subject attributes (ABAC):
  allowedRegionIds: ["north"] hoặc ["south"]

Policy:
  Cho phép lead.read nếu
  subject có role sales_representative
  VÀ lead.region thuộc subject.allowedRegionIds
  VÀ subject/engagement/tenant đang hợp lệ.
~~~

Điều này tránh tạo tràn lan `sales_representative_north`, `sales_representative_south`… nếu **phạm vi tài nguyên** phù hợp hơn với ABAC. Nhưng với yêu cầu quản trị khác nhau rõ rệt theo vùng, role phân phạm vi vẫn có thể hợp lý. Cần quyết định theo nghiệp vụ và độ phức tạp thật.

### 9.3. Quyền I và E có nên gom thành một role?

Nếu mọi người đủ điều kiện export luôn có quyền đọc, ta có thể chọn:

- **Role nền `finance_reader={I}`** và **role bổ sung `finance_exporter={E}`**; ưu điểm là kiểm soát chặt hoạt động export.
- Hoặc role `finance_analyst={I,E}` cùng role `finance_reader={I}`; ưu điểm là ít assignment trong một số ngữ cảnh, nhưng có nguy cơ chồng chéo quyền.

**Không có đáp án duy nhất từ ma trận 0/1.** Quyết định dựa vào cách tổ chức phê duyệt export, tính nhạy cảm dữ liệu, SoD, tần suất sử dụng và chi phí vận hành.

## 10. Mô hình toán học khái niệm cho Role mining

Gọi:

- `U`: tập user/subject được phân tích.
- `P`: tập permission đã chuẩn hóa.
- `R`: tập candidate roles.
- `UA ⊆ U × R`: quan hệ gán user–role.
- `PA ⊆ R × P`: quan hệ gán role–permission.

Quyền do role suy ra:

~~~text
E_role = {
  (u,p) | tồn tại r:
    (u,r) thuộc UA
    AND (r,p) thuộc PA
}

E_observed = tập user-permission quan sát từ nguồn
E_desired  = tập quyền đã được nghiệp vụ/pháp chế/chính sách chấp nhận
~~~

Nếu chỉ dùng snapshot, thuật toán cố làm cho `E_role` gần `E_observed`. Nhưng mục tiêu bảo mật là **đưa quyền thực tế về gần `E_desired`**, sau khi đã xác minh nguồn và nghiệp vụ.

### 10.1. Những sai lệch cần theo dõi

~~~text
ObservedCoverage:
  |E_role ∩ E_observed| / |E_observed|

OvergrantAgainstDesired:
  E_role - E_desired

MissingRequiredAccess:
  E_desired - E_role

UnmodelledObservedGrants:
  E_observed - E_role
~~~

**Cảnh báo:** Nếu lấy `E_observed` làm “đúng tuyệt đối”, mọi quyền sai đang tồn tại có thể được tính là coverage tốt. Nên đo **overgrant so với tập đã xác minh `E_desired`**, không chỉ so với dữ liệu hiện trạng.

### 10.2. Hàm mục tiêu cân bằng

Một cách tư duy:

~~~text
Minimize:
   w1 × số overgrant rủi ro
 + w2 × số permission cần nhưng chưa được mô hình hóa
 + w3 × chi phí quản trị role/assignment
 + w4 × mức chồng chéo và sự phức tạp
 + w5 × số SoD conflicts
 + w6 × chi phí ngoại lệ có thời hạn

Subject to:
   business-approved permissions,
   tenant/resource boundary,
   SoD constraints,
   JML eligibility,
   privileged-access policy.
~~~

Các trọng số `w1..w6` là **tham số quyết định quản trị**, không có giá trị mặc định chung. **Rủi ro overgrant thường cần ưu tiên cao hơn việc giảm số lượng role**, nhưng mức cụ thể do tổ chức xác nhận.

### 10.3. Role support và similarity

- **Support** của một tập quyền: số lượng/tỷ lệ subject có tập quyền đó trong nhóm được xét.
- **Jaccard similarity** giữa hai tập quyền A và B: `|A ∩ B| / |A ∪ B|` khi mẫu số khác 0.
- **Entropy/variation** hay độ đồng nhất của một nhóm: có thể hỗ trợ chọn candidate, nhưng không thay thế business validation.

Ví dụ:

~~~text
Permissions An  = {L, U, Q}
Permissions Bình = {L, U, Q}
Jaccard         = 3 / 3 = 1.0

Permissions Dũng = {L, U, Q, A}
Jaccard(An,Dũng) = 3 / 4 = 0.75
~~~

Dù similarity cao, **không được kéo A vào role Sales cơ bản** vì A là quyền phê duyệt có rủi ro SoD.

## 11. Các kỹ thuật mining thường dùng

| Kỹ thuật | Ý tưởng | Điều cần kiểm soát |
|---|---|---|
| **Frequent itemset mining** | Tìm tập permission xuất hiện cùng nhau đủ thường xuyên | Support cao không có nghĩa quyền hợp lệ |
| **Clustering** | Nhóm user theo tập quyền tương tự | Cần giải thích nghiệp vụ và ngoại lệ |
| **Formal Concept Analysis (FCA)** | Tìm cấu trúc giữa tập subject và tập thuộc tính/quyền | Có thể sinh rất nhiều concept/role |
| **Matrix factorization/Boolean matrix decomposition** | Xấp xỉ ma trận UP bằng user–role và role–permission | Giảm sai lệch toán học không bảo đảm least privilege |
| **Graph/community detection** | Tìm cụm trong đồ thị user–permission–app | Cần xử lý quyền đặc biệt và liên kết gián tiếp |
| **Rule/attribute-assisted mining** | Kết hợp job code, department, location, project | Thuộc tính phải chính xác, tránh suy quyền từ dữ liệu lỗi |
| **Risk-weighted mining** | Phạt mạnh quyền nhạy cảm/SoD/overgrant | Trọng số và quyết định rủi ro cần chủ sở hữu |

**Không bắt buộc dùng AI/ML.** Với một hệ thống nhỏ, phân tích ma trận và workshop với owner có thể hiệu quả hơn mô hình phức tạp. Với hệ thống lớn, thuật toán giúp giảm công sức khám phá nhưng **vai trò sau cùng vẫn phải được giải thích và phê duyệt**.

### 11.1. Lựa chọn ngưỡng support

Support thấp có thể tạo hàng nghìn role hiếm; support quá cao có thể bỏ qua vai trò chuyên môn cần thiết. Ngưỡng nên được đánh giá theo:

- Quy mô nhóm nghiệp vụ và số subject.
- Độ hiếm nhưng thiết yếu của nhiệm vụ.
- Quyền nhạy cảm như admin, export, approve.
- Sự khác biệt tenant/site/environment.
- Chi phí review và vận hành.
- Mức độ sạch và đầy đủ của dữ liệu.

**Không có con số tối ưu chung** như “tối thiểu ba người mới được phép có role”. Role chuyên trách có thể chỉ có một người nhưng vẫn cần được quản trị chính thức; role quá rộng cho hàng trăm người cũng có thể không hợp lệ.

## 12. Mã giả khai phá candidate roles từ mẫu quyền

Ví dụ dưới đây cố ý chỉ **đề xuất**, không ghi lại quyền ở hệ thống thật. Nó sử dụng nhóm business context đã được xác nhận để không trộn account người dùng với workload.

~~~python
# Pseudocode phục vụ bài học, không phải engine role mining production.
from collections import Counter
from itertools import combinations

def suggest_permission_bundles(subjects, min_support=2, max_bundle_size=3):
    """
    subjects: danh sách bản ghi sau chuẩn hóa:
      {
        "subjectId": "...",
        "kind": "HUMAN",
        "businessContext": "sales",
        "active": True,
        "permissions": {"lead.read", "quote.create", ...}
      }
    Trả về ứng viên để người có thẩm quyền thẩm định.
    """
    grouped = {}

    for s in subjects:
        if not s["active"]:
            continue
        if s["kind"] != "HUMAN":
            continue

        key = s["businessContext"]
        grouped.setdefault(key, []).append(s)

    candidates = []

    for context, members in grouped.items():
        counts = Counter()

        for s in members:
            rights = sorted(s["permissions"])

            # Chỉ xét tập nhỏ để minh họa; mining thật cần tối ưu.
            for size in range(1, min(max_bundle_size, len(rights)) + 1):
                for bundle in combinations(rights, size):
                    counts[bundle] += 1

        for bundle, support in counts.items():
            if support >= min_support:
                candidates.append({
                    "context": context,
                    "permissions": list(bundle),
                    "support": support,
                    "reviewRequired": True
                })

    return candidates


# Không có dòng nào ở đây tự assign role hoặc cấp quyền.
# Ứng viên phải qua normalization, SoD, least privilege,
# business approval, scope validation và pilot/readback.
~~~

**Giới hạn:** Cách liệt kê tổ hợp tăng rất nhanh khi quyền nhiều. Đoạn mã không giải quyết trọng số rủi ro, nested groups, hierarchy, exception, SoD, tenant scope hay đánh giá độ tin cậy của nguồn. Trong thực tế cần thuật toán phù hợp dữ liệu và **đường phê duyệt kiểm soát thay đổi**.

### 12.1. Những điều không nên tự động hóa trực tiếp

- Không tự gán role mới cho tất cả người có quyền giống nhau.
- Không tự xóa quyền hiếm chỉ vì support thấp.
- Không tự tạo role admin từ cụm nhiều user admin.
- Không chuyển quyền đặc quyền tạm thời thành quyền thường trực.
- Không tự mở rộng tenant hoặc dữ liệu từ region A sang region B.
- Không gán role người dùng cho service account trùng permission.
- Không coi thiếu bản ghi là `0` khi connector đang lỗi.

## 13. Đánh giá chất lượng candidate role

Một ứng viên nên được đánh giá từ **nhiều chiều**, không chỉ mức coverage.

| Tiêu chí | Câu hỏi | Phép đo/bằng chứng |
|---|---|---|
| **Business meaning** | Role có một nhiệm vụ xác định không? | Tên role, owner, quy trình, mô tả trách nhiệm |
| **Least privilege** | Có quyền nào thừa so với nhiệm vụ? | Overgrant review, app owner certification |
| **Coverage** | Role mô hình hóa được bao nhiêu quyền hợp lệ? | Tỷ lệ entitlement được xác minh |
| **Exceptions** | Bao nhiêu user cần grant ngoài role? | Direct grant có căn cứ, TTL |
| **SoD compliance** | Role có chứa quyền xung đột? | Ma trận SoD, test workflow |
| **Risk concentration** | Role có admin/export/secret access? | Nhãn rủi ro, yêu cầu PAM/JIT |
| **Understandability** | Người quản lý có biết khi nào dùng role? | Định nghĩa đầu vào, ví dụ nhiệm vụ |
| **Stability** | Role có thay đổi liên tục theo từng snapshot? | Role drift, thời gian hiệu lực |
| **Assignment complexity** | Bao nhiêu role/user, hierarchy và inheritance? | Số role, số binding, số overlap |
| **Tenant/project scoping** | Role có vô tình mở rộng phạm vi tài nguyên? | ABAC/RS tests theo tenant/resource |
| **JML readiness** | Có điều kiện tự cấp/thu hồi theo lifecycle? | Joiner/Mover/Leaver test cases |
| **Auditability** | Có biết ai duyệt, vì sao, ở đâu? | Provenance, policy version, readback |

### 13.1. Role explosion

**Role explosion** là hiện tượng số role tăng nhanh do mỗi biến thể nhỏ tạo một role mới: `sales_read_north`, `sales_read_south`, `sales_read_north_temporary`, rồi thêm tenant, dự án và thời hạn.

Giảm role explosion bằng cách:

- Giữ **role nghiệp vụ** cho nhóm nhiệm vụ ổn định.
- Dùng **ABAC/resource scope** cho biến số như region/project khi phù hợp.
- Dùng **time-bound entitlement/JIT** cho quyền ngắn hạn.
- Gộp role thực sự trùng nghĩa và tách role chứa quyền không cùng mục đích.
- Không tạo role chỉ để biểu diễn một ngoại lệ tạm thời.
- Rà soát **role không còn được gán, ít sử dụng nhưng vẫn có trách nhiệm**, và hierarchy không cần thiết.

**Đừng đánh đổi an toàn để giảm số role bằng mọi giá.** Một role “all_employees_all_apps” có thể giảm số cấu hình nhưng là thiết kế quyền quá rộng.

### 13.2. Role overlap và role hierarchy

Hai role có thể cùng chứa một permission. Việc chồng chéo không tự sai, nhưng có thể gây khó giải thích khi gỡ một role **mà permission vẫn còn do role khác**.

Cần biết **nguồn cấp quyền (grant provenance)**. Khi Mover, gỡ role cũ nhưng API vẫn cho phép do một role khác hoặc direct grant, kết quả thu hồi phải được xét theo **quyền hiệu dụng**, không chỉ số role đã bị gỡ.

## 14. Separation of Duties (SoD) trong role mining

**Separation of Duties (SoD)** là nguyên tắc tách những quyền có thể xung đột để giảm gian lận và sai sót. Role mining dễ tạo vai trò nguy hiểm nếu các quyền xung đột thường xuất hiện cùng nhau trong hệ thống cũ.

Ví dụ:

~~~text
expense.create
expense.approve

Risk:
  Một người vừa tạo vừa phê duyệt
  cùng một expense có thể vi phạm quy trình kiểm soát.
~~~

### 14.1. Static và Dynamic SoD

- **Static SoD:** Không cho cùng một subject được gán đồng thời hai role xung đột, tùy policy.
- **Dynamic SoD:** Có thể có nhiều role nhưng **không được kích hoạt hoặc sử dụng kết hợp** trong một phiên/hành động/quy trình cụ thể.

Ví dụ quản lý có quyền tạo và phê duyệt báo giá nhưng **không được duyệt báo giá do chính họ tạo**. Đây là ràng buộc theo **quan hệ giữa subject và resource**; có thể cần ABAC/transactional authorization chứ không chỉ tách role.

### 14.2. Ma trận SoD minh họa

| Permission A | Permission B | Rủi ro | Kiểm soát |
|---|---|---|---|
| `invoice.create` | `invoice.approve` | Tạo và tự phê duyệt giao dịch | Static/dynamic SoD theo quy trình |
| `user.create` | `access.certify` | Người cấp tài khoản tự xác nhận quyền | Phân tách người tạo và người duyệt |
| `vendor.create` | `payment.release` | Tạo nhà cung cấp và phát hành thanh toán | Phê duyệt độc lập, workflow checks |
| `security.log.modify` | `security.event.review` | Thay đổi và tự kiểm tra dấu vết | Hạn quyền, bảo toàn log, review độc lập |

Các xung đột trên chỉ là **mẫu cần thẩm định**. Chính sách SoD thực tế phải dựa trên rủi ro, quy trình, thẩm quyền và đặc thù nghiệp vụ. Thuật toán không được tự giả định mọi cặp đều bị cấm ở mọi tổ chức.

## 15. Business role, technical role và entitlement package

Một số tổ chức quản lý **hai lớp**:

- **Business role:** “Nhân viên kinh doanh”, “Kiểm toán viên nội bộ”, “Người duyệt hóa đơn” – dùng cho request và phê duyệt theo nhiệm vụ.
- **Technical/application role:** Tập group, application role hoặc permission mà hệ thống thực sự cấp.
- **Entitlement package/access package:** Gói quyền phục vụ một nhiệm vụ hoặc thời hạn, có thể gồm nhiều ứng dụng và yêu cầu review.

Ví dụ:

~~~text
Business role: Sales Representative
  ├─ IdP group: sales-users
  ├─ CRM role: lead-editor
  ├─ Quote app role: quote-creator
  └─ ABAC scope: project/region thuộc assignment hợp lệ

Quyền đặc biệt:
  quote.approve -> role bổ sung, kiểm SoD và phê duyệt riêng
~~~

Một role nghiệp vụ **không cần trùng một-nhất với một group IdP**. Có thể ánh xạ sang nhiều target, nhưng phải có **quy tắc provisioning/deprovisioning nhất quán**. Mỗi target cần owner và bằng chứng rằng những quyền mong muốn đã thực sự được áp.

### 15.1. Ai là owner của role?

| Trách nhiệm | Chủ thể thường phù hợp |
|---|---|
| Định nghĩa nhiệm vụ và ai đủ điều kiện | Business owner/manager có thẩm quyền |
| Kiểm tra permission thực tế | Application owner |
| Chính sách truy cập, SoD, least privilege | Security/IAM governance |
| Mapping nhóm/role, provisioning và sync | IAM/IGA/platform team |
| Tính chính xác trạng thái nhân sự/hợp đồng | HR/VMS owner |
| Phê duyệt ngoại lệ hoặc rủi ro | Người có thẩm quyền theo policy |

**Role phải có người chịu trách nhiệm thực sự.** Nếu business owner rời tổ chức hoặc ứng dụng đổi chủ, role cần được **chuyển ownership**; không chỉ giữ một tên trong catalog rồi coi đã được quản trị.

## 16. Phê duyệt vai trò trước khi đưa vào sản xuất

Một **candidate role** chỉ nên chuyển thành role được dùng khi:

1. **Nhiệm vụ rõ:** Người nghiệp vụ hiểu ai cần role và lý do.
2. **Permission được kiểm chứng:** App owner xác nhận danh sách quyền, semantics và scope.
3. **Least privilege:** Quyền rộng/nhạy cảm được loại hoặc bảo vệ bổ sung.
4. **SoD:** Có đánh giá và biện pháp cho các quyền xung đột.
5. **JML policy:** Xác định điều kiện Joiner, Mover, Leaver và ngoại lệ.
6. **Provisioning mapping:** Biết chính xác role áp vào hệ thống đích qua IdP/SCIM/API hoặc thủ công.
7. **Thu hồi được:** Có thể gỡ role/permission, session/token và direct grants nếu cần.
8. **Kiểm thử:** Pilot ở scope hạn chế, test allow/deny, readback và rollback.
9. **Owner/expiry:** Có owner, lịch certification và version policy.
10. **Audit:** Có hồ sơ dữ liệu đầu vào, phê duyệt, ngày hiệu lực và thay đổi.

### 16.1. Quy tắc tạo role gợi ý

~~~text
Candidate:
  roleId: finance_exporter
  businessPurpose: Xuất hóa đơn cho báo cáo đã duyệt
  permissions: [invoice.export]
  requiredBaseRole: finance_reader
  scope: tenant/project được phân công
  assignment:
    - Finance manager approval
    - Security review khi dữ liệu nhạy cảm
    - Time limit theo nhu cầu công việc
  exclusions:
    - Account không có engagement hợp lệ
    - Subject đang bị đình chỉ / Leaver
  owner: Finance Data Owner
  status: PROPOSED -> REVIEWED -> APPROVED
~~~

Đây là **mẫu chính sách**, không phải cấu hình chuẩn của một sản phẩm IAM. Giá trị owner, thời hạn và phê duyệt phải được định nghĩa theo tổ chức.

## 17. Triển khai qua IdP, directory, SCIM và ứng dụng

Role mining không trực tiếp tạo ra quyền thực tế. Sau phê duyệt, phải triển khai mapping và xác minh trên từng target.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Business + IAM governance
    participant G as IGA / Role catalog
    participant D as IdP / Directory
    participant S as SCIM / App connector
    participant A as Application / API
    participant V as Verification / Audit

    B->>G: Phê duyệt role, policy, owner, scope
    G->>G: Tính user-role assignment hợp lệ
    G->>D: Cập nhật group / attribute khi dùng
    D-->>G: Trạng thái áp dụng
    G->>S: Provision/deprovision entitlement
    S->>A: Ghi account / role / group
    A-->>S: Kết quả thao tác
    G->>V: Yêu cầu readback và kiểm quyền
    V->>D: Đối soát IdP/directory state
    V->>A: Đọc role, ACL, effective access
    A-->>V: Trạng thái thực tế
    V-->>B: Kết quả, exception và audit trail
~~~

### 17.1. SSO không có nghĩa quyền tự đồng bộ

**SSO** giúp ứng dụng xác thực người dùng từ IdP, nhưng không nhất thiết tạo account hay gán mọi role trong app. Có thể cần **SCIM/API** hoặc cơ chế application-specific để provision.

SCIM có thể cập nhật group/member khi ứng dụng hỗ trợ, nhưng **không thể tự suy ra mọi local ACL, token hoặc quyền đặc biệt đều được thu hồi**. Cần kiểm tra hành vi connector và ứng dụng.

### 17.2. Khi role thay đổi trong lúc phiên đang hoạt động

Sau khi gỡ `finance_exporter` khỏi subject, token JWT/cookie hoặc session ở ứng dụng có thể vẫn chứa claim cũ. Thiết kế cần chính sách cho:

- Thời hạn token và phiên.
- Refresh/reauthentication khi đổi quyền.
- Role/entitlement cache invalidation.
- Introspection hoặc kiểm tra state hiện hành với quyền nhạy cảm.
- Readback permission thực tế tại API.
- Audit thời điểm **quyền thực sự mất hiệu lực**, không chỉ khi gửi lệnh.

## 18. Role mining trong Joiner: không sao chép nguyên quyền người cũ

Khi nhân viên mới gia nhập, tổ chức muốn cấp **quyền đủ để bắt đầu công việc** mà không phải phê duyệt từng quyền nhỏ.

**Role mining hỗ trợ** bằng cách cung cấp **role catalog đã được duyệt** cho chức danh/nhiệm vụ phù hợp.

~~~text
Joiner event:
  personId=P-3108
  role/position=Sales Representative
  engagementStatus=ACTIVE at effectiveAt
  tenant=company-vn
  region=south

Role assignment sau kiểm tra:
  sales_representative
  resource scope: region=south

Không tự cấp:
  quote.approve
  CRM global admin
  export mọi dữ liệu
~~~

### Chuỗi kiểm tra cần thiết

1. HR/VMS xác minh engagement và mốc hiệu lực.
2. IAM liên kết canonical identity với account.
3. Role catalog xác định role theo **nhiệm vụ, bộ phận và approval**, không chỉ theo job title nếu chức danh không đủ chính xác.
4. IdP/SCIM/API áp role/entitlement đến target.
5. Ứng dụng/RBAC/ABAC kiểm quyền trong phạm vi region/project đúng.
6. Readback account, nhóm và quyền hiệu dụng trước khi kết luận sẵn sàng.
7. Có quy trình sửa sai và xử lý ngoại lệ nếu nhiệm vụ thực tế khác khuôn mẫu.

**Không cấp quyền bằng cách clone account của người tiền nhiệm.** Người cũ có thể có quyền lịch sử, quyền admin khẩn cấp hoặc exception không được chuyển cho Joiner mới.

## 19. Role mining trong Mover: ngăn tích lũy quyền

Mover xảy ra khi subject chuyển phòng ban, dự án, site, vị trí hoặc nhiệm vụ. **Role catalog** nên cho phép tính lại tập role mong muốn thay vì chỉ cộng thêm.

Ví dụ:

~~~text
Trước Mover:
  sales_representative@project-A
  finance_reader@project-A   (ngoại lệ đã duyệt)

Sau Mover sang Finance/project-B:
  finance_reader@project-B
  finance_exporter@project-B (nếu được duyệt riêng)

Cần xử lý:
  - Thu hồi role/project-A không còn căn cứ.
  - Kiểm tra ngoại lệ cũ có phải hết hạn không.
  - Cấp quyền B đúng scope.
  - Xử lý token/cache chứa role A.
  - Đối soát direct grant và quyền kế thừa.
~~~

### 19.1. Công thức thay đổi

~~~text
DesiredAssignments = role được phép theo nhiệm vụ hiện tại
CurrentAssignments = role đang gán thực tế

Assign   = DesiredAssignments - CurrentAssignments
Unassign = CurrentAssignments - DesiredAssignments
~~~

Nhưng **gỡ role không bảo đảm quyền mất** nếu permission vẫn tồn tại qua role khác hoặc ACL trực tiếp. Cần phân tích **grant provenance và effective access**.

### 19.2. Một người có nhiều engagement

Một nhân viên vừa làm dự án A vừa tham gia B có thể được phép giữ quyền A sau khi thay vai trò chính. Không tự xóa mọi grant A nếu còn engagement hợp lệ, cũng không giữ tất cả vì “account vẫn active”. Role assignment cần thể hiện **nguồn cấp, phạm vi và thời gian hiệu lực của từng nhiệm vụ**.

## 20. Role mining trong Leaver: quyền phải được thu hồi thực sự

Role mining hỗ trợ Leaver bằng cách tập trung hóa **đường cấp quyền** và làm rõ role/entitlement cần gỡ. Tuy nhiên, khi một subject rời tổ chức, không thể chỉ xóa user–role assignment ở IGA rồi kết luận tài khoản đã mất mọi quyền.

Quy trình cần:

1. Xác nhận biến cố Leaver từ nguồn HR/VMS có thẩm quyền.
2. Xác định đúng canonical subject, engagement và account ở từng target.
3. Hủy gán role/entitlement hết căn cứ, bao gồm nhóm, app role, direct grants.
4. Vô hiệu hóa account theo chính sách nếu không còn engagement hợp lệ.
5. Xử lý **phiên SSO, session ứng dụng, refresh/access token, PAT/API key** khi cần.
6. Kiểm tra nested group, resource policy, privilege tạm thời/PAM.
7. Readback trạng thái quyền tại IdP, SCIM target, app/API.
8. Ghi kết quả, lỗi đồng bộ, owner và hạn xử lý; không đánh dấu hoàn tất khi thiếu bằng chứng.

**Role catalog không tự xử lý quyền nằm ngoài role.** Việc role mining phát hiện direct grants, ownerless accounts và các ngoại lệ là đầu vào quan trọng cho quy trình deprovisioning.

### 20.1. Leaver của một engagement khác Leaver toàn tổ chức

Nếu contractor hết dự án A nhưng còn hợp đồng B:

- Thu hồi role và grant có căn cứ từ A.
- Giữ role B đã được xác minh và còn hiệu lực.
- Không tự vô hiệu hóa toàn bộ account nếu B vẫn cần account và policy cho phép.
- Không giữ privilege của A chỉ vì subject còn login được qua B.

## 21. Service account, role đặc quyền và break-glass có nên đưa vào mining?

### 21.1. Service account cần luồng riêng

Một workload có thể dùng permission giống người dùng (ví dụ `invoice.read`), nhưng mục đích và lifecycle khác:

| Loại | Đặc trưng | Cách mining/role engineering |
|---|---|---|
| **Human user** | Engagement, manager, MFA, JML | Mining theo nhiệm vụ/nghiệp vụ |
| **Service account** | Workload ID, service owner, credential | Mining riêng theo workload/function |
| **PAM/JIT privileged role** | Quyền nhạy cảm, time-bound, approval | Tách khỏi role thường trực, theo policy đặc quyền |
| **Break-glass account** | Dùng trong tình huống khẩn cấp, ít hoạt động | Quản trị bằng policy đặc biệt, không suy từ tần suất sử dụng |
| **Shared/legacy account** | Khó quy trách nhiệm actor | Điều tra, phân loại rủi ro, kế hoạch thay thế/kiểm soát |

**Không đưa tài khoản máy vào cùng cụm với nhân viên** rồi cấp role `finance_user` cho service account chỉ vì quyền trùng. Workload nên có owner kỹ thuật, scope/audience, môi trường, credential rotation và đánh giá dependency.

### 21.2. Quyền ít dùng có thể vẫn quan trọng

Break-glass có thể không bao giờ được sử dụng trong suốt một năm. Quyền khẩn cấp là **policy riêng**, không nên bị xóa dựa trên “usage = 0” hoặc biến thành role phổ biến vì có nhiều account dự phòng.

### 21.3. Service owner rời tổ chức

Một service account có thể còn cần cho production dù người tạo đã Leaver. Cần xác nhận workload, **chuyển owner có thẩm quyền**, rà soát secret từng bị người cũ biết, rotate/revoke khi cần và hạn chế quyền. Không vô hiệu hóa bừa tài khoản máy gây gián đoạn dịch vụ.

## 22. Kiểm thử role trước khi phát hành

Một role được chấp nhận cần **test cả quyền được phép và quyền phải bị từ chối**.

| Trường hợp kiểm thử | Kỳ vọng |
|---|---|
| Joiner Sales Nam đọc lead Nam | PERMIT nếu mọi điều kiện hợp lệ |
| Joiner Sales Nam đọc lead Bắc | DENY nếu không có grant khác |
| Sales thường phê duyệt báo giá | DENY nếu không có vai trò/ủy quyền approve |
| Manager phê duyệt giao dịch do chính họ tạo | DENY nếu SoD quy định |
| Finance reader xem hóa đơn trong scope | PERMIT |
| Finance reader export dữ liệu | DENY nếu không có quyền export |
| Account contractor hết hạn nhưng còn session | DENY theo chính sách thu hồi |
| Subject đã Mover giữ token role cũ | Không được giữ quyền trái policy sau thời hạn thu hồi |
| Workload client gọi API ngoài audience | DENY |
| Role mất dữ liệu thuộc tính quan trọng | Không tự động PERMIT |
| User ở tenant A truy cập resource B | DENY khi không có quyền xuyên tenant được duyệt |
| Direct grant còn sau khi gỡ role | Phát hiện và xử lý trước khi xác nhận đã thu hồi |

### 22.1. Pilot và rollback

- Chọn **nhóm nhỏ có nghiệp vụ đại diện**, có owner phê duyệt.
- Chạy **shadow evaluation** nếu nền tảng hỗ trợ: tính quyết định mới nhưng chưa thực thi.
- So sánh kết quả policy mới với nhu cầu đã duyệt, không chỉ so với quyền cũ.
- Thử Joiner/ Mover/ Leaver bằng identity kiểm thử an toàn.
- Xác nhận triển khai group/role qua IdP/SCIM/ứng dụng và readback.
- Có phương án rollback **không tái cấp quyền đã bị thu hồi do Leaver hoặc sự cố**.
- Ghi version và change ID để điều tra.

**Rollback một role phải có điều kiện an toàn.** Không dùng snapshot quyền cũ chưa làm sạch để khôi phục quyền cho mọi user sau lỗi triển khai.

## 23. Đo lường chất lượng Role mining và role catalog

| Chỉ số | Định nghĩa gợi ý | Bẫy cần tránh |
|---|---|---|
| **Reviewed coverage** | Tỷ lệ entitlement được biểu diễn bằng role đã duyệt trong phạm vi đã kiểm kê | Coverage cao có thể che overgrant |
| **Overgrant findings** | Quyền không có căn cứ so với desired state | Chưa xác minh source-of-truth thì khó kết luận |
| **Role count / growth** | Số role và tốc độ tăng | Số role thấp không tự bằng an toàn |
| **Role assignment density** | Role trung bình mỗi subject | Không tối ưu thuần số lượng |
| **Role overlap** | Tỷ lệ permission trùng giữa role | Chồng chéo đôi khi là thiết kế hợp lệ |
| **Direct-grant exception rate** | Tỷ lệ grant ngoài role catalog | Phải phân biệt JIT hợp lệ và quyền tồn dư |
| **SoD violation count** | Vi phạm chính sách phân tách nhiệm vụ | Tính cả xung đột ở role lẫn tại resource |
| **Certification coverage** | Role có owner và review còn hiệu lực | Owner ký duyệt không thay kiểm tra thực tế |
| **JML provisioning convergence** | Thời gian từ event đến role/quyền mong muốn ở target | Không dùng thời điểm gửi lệnh làm thời điểm hoàn tất |
| **Leaver residual access** | Quyền/phiên/token còn trái chính sách sau Leaver | Gỡ nhóm không bảo đảm gỡ hết quyền |
| **Role drift** | Role thay đổi không có phê duyệt hoặc lệch catalog | Phát hiện grant trực tiếp và đổi mapping |
| **Rework/exception aging** | Candidate hoặc exception chưa được giải quyết bao lâu | Không nên giữ ngoại lệ vô thời hạn |
| **Unowned roles** | Role không có owner chịu trách nhiệm | Metadata owner có thể đã lỗi thời |
| **Privilege concentration** | Quyền nhạy cảm tập trung trong role nào | Không đánh giá chỉ bằng số user được gán |

### 23.1. Cách đọc coverage cho đúng

Ví dụ có 100 entitlement cần thiết sau review; role đã duyệt mô hình hóa 90, nhưng lại dự kiến cấp thêm 15 entitlement không có căn cứ. **Coverage 90% không chứng minh thành công**; 15 quyền thừa phải được sửa trước. Nên trình bày **coverage, overgrant, ngoại lệ, SoD và độ mới quyền** cùng nhau.

### 23.2. Không có ngưỡng cố định áp cho mọi tổ chức

Tỷ lệ role mining thành công phụ thuộc cấu trúc công việc, số app, chất lượng dữ liệu, rủi ro và nghĩa vụ kiểm soát. Không có một số **support, role/user hoặc SLA** chung cho mọi ngành. Mục tiêu phải được business owner, IAM governance và security thống nhất.

## 24. Tình huống thực hành 1: role quá rộng từ dữ liệu lịch sử

**Bối cảnh:** Thuật toán phát hiện 18/20 nhân viên Finance có `invoice.read` và `invoice.export`. Nó đề xuất `finance_basic={invoice.read,invoice.export}` cho mọi Joiner Finance.

**Vấn đề:** Trong số 18 người, nhiều người được cấp export từ trước khi chính sách mới yêu cầu phê duyệt riêng. Hai người không có export là nhân viên mới đã theo đúng chính sách.

**Cách xử lý:**

1. Xác minh phiên bản chính sách **hiện hành** và phân loại export là quyền nhạy cảm.
2. Business owner xác nhận nhiệm vụ nào cần export, ai phê duyệt.
3. Không đưa export vào role cơ bản chỉ vì tần suất 90%.
4. Thiết kế `finance_reader` và quyền export bổ sung có review/TTL phù hợp.
5. Thu hồi export không có căn cứ từ các account cũ, kiểm tra token/session.
6. Chạy lại mining sau cleanup; ghi lý do ứng viên ban đầu bị loại.

**Bài học:** **Frequency không tạo ra legitimacy**. Thuật toán có thể tìm mẫu rất rõ của một sai lệch lịch sử.

## 25. Tình huống thực hành 2: Mover và quyền được cấp từ nhiều nguồn

**Bối cảnh:** Mai chuyển từ Sales sang Finance. IAM gỡ role `sales_representative`, nhưng Mai vẫn có direct ACL `lead.export@north` do một quản trị viên cấp thủ công hai năm trước.

**Vì sao role mining liên quan?**

- Ma trận entitlement cho thấy direct grant không được mô hình hóa.
- Nếu mining chỉ dựa group IdP, nó có thể bỏ sót quyền này.
- Khi Mover, role removal thành công nhưng **effective access vẫn còn**.

**Cách xử lý:**

1. Map account ứng dụng của Mai với canonical identity.
2. Thu thập đầy đủ role, group, direct ACL và quyền token hiện tại.
3. Xác định grant `lead.export@north` có nguồn phê duyệt còn hiệu lực không.
4. Nếu không còn căn cứ, thu hồi grant trực tiếp và xử lý cache/token liên quan.
5. Readback kết quả tại API.
6. Sửa quy trình request/certification để quyền ngoài role được ghi và có expiry.

**Bài học:** Role mining không chỉ phát hiện candidate role; nó còn phơi bày **ngoại lệ và direct grant** cần quản trị.

## 26. Tình huống thực hành 3: service account bị đưa vào role người dùng

**Bối cảnh:** Pipeline dữ liệu `svc_finance_reconcile` có `invoice.read` và `report.export`. Thuật toán clustering ghép nó vào nhóm nhân viên Finance, đề xuất cấp `finance_analyst` cho workload và mọi người thuộc nhóm tương tự.

**Rủi ro:**

- Service account có thể bị cấp thêm khả năng không phục vụ workload.
- Một role người dùng có thể nhận quyền service cần đặc quyền máy.
- Khác biệt owner, credential, phạm vi dữ liệu và thời hạn bị bỏ qua.

**Thiết kế đúng:**

- Phân loại **subject kind** trước khi mining.
- Dùng **workload identity** có owner kỹ thuật, audience, scope và quyền tối thiểu.
- Xác minh service account có cần `report.export` hay đã quá quyền.
- Quản lý credential, rotation, thay owner khi Leaver và log riêng.
- Không dùng email/tên người tạo service account làm canonical workload identity.

## 27. Tình huống thực hành 4: role theo vùng làm rò dữ liệu

**Bối cảnh:** Ba nhân viên Sales có cùng ba permission L/U/Q, nhưng hai người phụ trách miền Bắc, một người miền Nam. Ứng dụng dùng role `sales_representative` mà không kiểm vùng của lead.

**Sai lầm:** Role mining đúng về tập hành động nhưng **thiếu resource scope**. Sau triển khai, tất cả có thể sửa lead toàn quốc nếu API không kiểm thuộc tính.

**Cách xử lý:**

1. Giữ candidate role cho các **action** chung sau khi được duyệt.
2. Bổ sung ABAC hoặc resource scoping tại API theo `allowedRegionIds` đáng tin.
3. Kiểm tra tenant/project, không nhận vùng chỉ từ query string của client.
4. Thử cả **PERMIT** ở vùng được phép và **DENY** ở vùng không được phép.
5. Khi Mover địa điểm hoặc đổi khách hàng, cập nhật thuộc tính và kiểm token/cache cũ.

**Bài học:** Role mining của permission names không thay thế **authorization theo tài nguyên và ngữ cảnh**.

## 28. Checklist thực hành Role mining trong IAM

- [ ] **Mục tiêu:** Nêu rõ muốn giảm direct grant, chuẩn hóa Joiner role, xử lý drift hay thiết kế lại RBAC?
- [ ] **Nguồn dữ liệu:** HR/VMS, IAM, IdP/directory, SCIM, ứng dụng, PAM và direct ACL đã được kiểm kê?
- [ ] **Mapping:** User/account/workload được liên kết bằng ID đáng tin, đúng tenant?
- [ ] **Chất lượng dữ liệu:** Có snapshot time, scope, entitlement semantics và đánh dấu missing/unknown?
- [ ] **Lifecycle filter:** Leaver, contractor hết hạn, Mover chưa hội tụ và account mồ côi đã được phân loại?
- [ ] **Loại chủ thể:** Human, workload, privileged và break-glass không bị gom sai?
- [ ] **Quyền hiệu dụng:** Có xét nhóm lồng nhau, resource policy, direct grant và trạng thái ứng dụng?
- [ ] **Approach:** Đã cân nhắc bottom-up/top-down/hybrid, ưu tiên khả năng giải thích và business validation?
- [ ] **Candidate roles:** Có support, permission list, scope, nguồn dữ liệu và risk flags?
- [ ] **Least privilege:** Không mặc định quyền phổ biến là quyền hợp lệ; overgrant được kiểm chứng?
- [ ] **SoD:** Create/approve, cấp/review và các cặp xung đột đã được đánh giá?
- [ ] **Role explosion:** Đã xét RBAC + ABAC, TTL và JIT thay vì tạo role cho mọi biến thể?
- [ ] **Business ownership:** Role có owner chấp nhận trách nhiệm, tên và mục đích rõ?
- [ ] **Approval:** App owner, security/IAM và business owner đã xác nhận theo policy?
- [ ] **Provisioning:** Role mapping qua IdP/SCIM/API cụ thể, có kiểm lỗi và retry an toàn?
- [ ] **Joiner:** Không clone quyền cũ; cấp role đúng nhiệm vụ, đúng mốc và scope?
- [ ] **Mover:** Thêm quyền mới, gỡ role/grant cũ, kiểm token/session và nhiều engagement?
- [ ] **Leaver:** Gỡ entitlement toàn phạm vi, khóa account và xử lý token/phiên theo chính sách?
- [ ] **Workload:** Service account có owner, credential/secret lifecycle và role riêng?
- [ ] **Pilot/readback:** Kiểm ALLOW/DENY tại API/target, cả tenant và resource ngoài scope?
- [ ] **Audit:** Có candidate origin, policy version, quyết định, người duyệt, thời điểm và ngoại lệ?
- [ ] **Governance:** Có lịch certification, phát hiện role drift, đổi owner, deprecation và rollback an toàn?
- [ ] **Metrics:** Theo dõi coverage **cùng** overgrant, SoD, direct grant và JML convergence?

## 29. Câu hỏi tự kiểm tra

**Câu 1:** Role mining phát hiện 95% nhân viên Marketing có quyền xuất toàn bộ dữ liệu khách hàng. Có nên đưa quyền này vào role mặc định?

**Gợi ý:** Không dựa riêng tần suất. Phải xác nhận nhu cầu nghiệp vụ, quyền tối thiểu, chính sách dữ liệu và nguồn grant; đây có thể là privilege creep lịch sử.

**Câu 2:** Hai nhân viên cùng job title nhưng một người ở tenant A, người còn lại ở tenant B. Tập permission names giống nhau. Có thể cấp role chung không?

**Gợi ý:** Có thể dùng role action chung **nếu** policy resource/ABAC ràng buộc tenant đúng; tuyệt đối không cấp quyền xuyên tenant chỉ vì tên role trùng.

**Câu 3:** Mover đã gỡ nhóm cũ khỏi IdP. Có thể khẳng định quyền cũ đã hết không?

**Gợi ý:** Chưa. Phải kiểm app role, direct ACL, token/session và quyền hiệu dụng tại target.

**Câu 4:** Một quyền break-glass không xuất hiện trong log 12 tháng. Mining nên tự xóa?

**Gợi ý:** Không. Quyền khẩn cấp có policy và owner riêng, cần kiểm tra khả năng sử dụng hợp lệ và controls, không dựa duy nhất vào usage.

**Câu 5:** Vì sao không được đưa service account vào cùng cụm mining với nhân viên Finance?

**Gợi ý:** Workload có chủ thể, owner, credential, phạm vi và lifecycle khác người dùng; trộn dữ liệu dễ tạo role cấp sai.

**Câu 6:** Hai role khác nhau đều cấp `invoice.read`. Gỡ một role có bảo đảm mất quyền đọc không?

**Gợi ý:** Không. Còn role/direct grant khác có thể duy trì quyền; cần đối soát quyền hiệu dụng.

**Câu 7:** Nếu chỉ tối ưu cho số role ít nhất, rủi ro nào xuất hiện?

**Gợi ý:** Role quá rộng, lẫn nhiệm vụ và SoD, role không giải thích được, overgrant hoặc truy cập nhiều tenant.

**Câu 8:** Role mining có thay thế được role approval và certification không?

**Gợi ý:** Không. Nó đề xuất ứng viên; chủ nghiệp vụ, app owner và security phải kiểm tra tính hợp lệ, quyền tối thiểu và vòng đời.

**Câu 9:** Dữ liệu connector thiếu một ứng dụng quan trọng, phép đo coverage vẫn rất cao. Có thể triển khai ngay?

**Gợi ý:** Chưa đủ. Phải công bố độ phủ dữ liệu và đánh dấu unknown, hoàn thiện inventory hoặc khoanh phạm vi được kiểm chứng trước khi triển khai.

**Câu 10:** Một role có permission tạo và phê duyệt hóa đơn. Khi nào cần tách hoặc đặt điều kiện?

**Gợi ý:** Kiểm SoD, quy trình nghiệp vụ và tài nguyên cụ thể; có thể yêu cầu tách vai trò hoặc dynamic SoD cấm phê duyệt giao dịch tự tạo.

## 30. Kết luận và nguyên tắc cần nhớ

**Role mining là công cụ biến dữ liệu phân quyền rời rạc thành các *ứng viên role có thể kiểm chứng*.** Nó giúp tổ chức nhận ra mẫu quyền lặp lại, bất thường, direct grant và cơ hội đơn giản hóa RBAC. Nhưng **quyền đã tồn tại không đồng nghĩa quyền đúng**; kết quả mining phải qua **phê duyệt nghiệp vụ, least privilege, SoD, tenant/resource scoping và kiểm chứng quyền thực tế**.

Để role mining tạo giá trị bền vững, hãy gắn nó với **vòng đời Identity and Access Management**: **Joiner** nhận role đã duyệt, **Mover** được tính lại tập role và gỡ quyền cũ, **Leaver** bị thu hồi account/quyền/phiên/token theo chính sách. **IdP/SSO, SCIM, RBAC kết hợp ABAC, quản lý service account, readback và kiểm toán** bảo đảm role catalog không chỉ đẹp trên giấy mà có thể **cấp đúng quyền, phát hiện sai lệch và hạn chế quyền truy cập tồn dư** trong hệ thống thực.
