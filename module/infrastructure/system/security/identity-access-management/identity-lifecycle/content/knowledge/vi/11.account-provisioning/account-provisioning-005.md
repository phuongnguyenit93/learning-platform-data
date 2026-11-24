# Provisioning theo group trong IAM

> **Chương:** Account provisioning  
> **Bài:** Provisioning theo group (*group-based provisioning*)  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Bối cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ cấp tài khoản và quyền đến điều chỉnh, thu hồi, rà soát. Nội dung kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

## 1. Provisioning theo group giải quyết vấn đề gì?

Một công ty dùng email, CRM, hệ thống nhân sự, kho tài liệu, hệ thống kế toán và nhiều ứng dụng SaaS. Khi có nhân viên mới, quản trị viên có thể tạo tài khoản tại từng ứng dụng và gán quyền bằng tay. Cách này dễ dẫn đến cấp thiếu, cấp nhầm, khó thu hồi và không biết nguồn nào đã cấp quyền.

**Provisioning theo group** là phương pháp sử dụng **tư cách thành viên của nhóm (group membership)** làm tín hiệu để tự động tạo hoặc kích hoạt tài khoản, gán vai trò/quyền trong ứng dụng đích, đồng thời cập nhật hoặc thu hồi chúng khi thành viên thay đổi. Group có thể do quản trị viên cấp theo quy trình, hoặc được tính từ thuộc tính danh tính đáng tin cậy theo chính sách.

Ví dụ, nhân viên Mai thuộc bộ phận chăm sóc khách hàng, chi nhánh Hà Nội:

- Group `app-crm-users` biểu diễn ai cần được cấp tài khoản CRM.
- Group `crm-support-hanoi` biểu diễn ai được thao tác trên nghiệp vụ chăm sóc khách hàng ở Hà Nội.
- Group `crm-export-approvers` chỉ dành cho người đã được duyệt quyền xuất dữ liệu nhạy cảm.

Khi Mai được thêm vào các group phù hợp, IAM có thể đồng bộ account và membership sang CRM. Khi Mai đổi vị trí, membership cũ được đánh giá lại. Nếu Mai không còn cần CRM, hệ thống phải thu hồi quyền/khả năng truy cập theo chính sách. Quyết định được ghi nhận từ **sự kiện, chính sách, nguồn nhóm và trạng thái thực tế tại hệ thống đích**.

Group-based provisioning giúp giảm thao tác lặp nhưng **không tự bảo đảm** phân quyền đúng. Hiệu quả phụ thuộc vào ai quản lý group, group có ý nghĩa gì, nhóm được ánh xạ sang quyền nào và connector có thực thi/đối soát chính xác hay không.

## 2. Phân biệt group, role, entitlement và account

| Đối tượng | Vai trò trong provisioning | Ví dụ |
|---|---|---|
| **Identity** | Danh tính gốc cần quản lý vòng đời | Nhân viên Mai, nhà thầu Nam, workload `invoice-worker` |
| **Account** | Biểu diễn danh tính tại hệ thống đích | Tài khoản của Mai trong CRM |
| **Group** | Tập chủ thể được quản lý với membership | `app-crm-users`, `crm-support-hanoi` |
| **Role** | Tập năng lực được một hệ thống định nghĩa | `crm.viewer`, `crm.editor` |
| **Entitlement** | Đơn vị quyền hoặc grant cụ thể | Quyền `customer.read` trên tenant `hanoi` |
| **Attribute** | Dữ liệu mô tả chủ thể/tài nguyên để tính chính sách | `department=support`, `region=north` |
| **Provisioning rule** | Quy tắc nối sự kiện/membership sang tác vụ đích | Group `app-crm-users` → tạo account CRM |
| **Target mapping** | Quy tắc ánh xạ group sang role/group/quyền trong ứng dụng | Group nguồn `crm-support-hanoi` → role `support` cùng phạm vi vùng |
| **Approval** | Quyết định của người có thẩm quyền với quyền nhạy cảm | Chủ dữ liệu duyệt việc xuất toàn bộ khách hàng |

Một **group không phải role** về bản chất. Group là tập thành viên; role là cách biểu diễn năng lực hoặc trách nhiệm trong hệ thống. Trong triển khai cụ thể, việc là thành viên group có thể dẫn đến role assignment, nhưng cần một quy tắc ánh xạ rõ ràng.

Tương tự, **có account không đồng nghĩa có entitlement**. CRM có thể đã tạo user nhưng chưa gán role; người dùng đăng nhập được mà không xem được tài liệu. Ngược lại, một user bị xóa khỏi group IdP vẫn có thể giữ local role được gán thủ công trong SaaS.

### 2.1. Hai ý nghĩa phổ biến của group

Group có thể được sử dụng theo hai lớp:

1. **Group để quyết định provisioning:** ai được tạo account hoặc được đưa vào phạm vi quản lý của một ứng dụng.
2. **Group để cấp quyền nghiệp vụ:** user có role/permission hoặc phạm vi dữ liệu nào trong ứng dụng.

Không nên buộc hai lớp này trùng nhau. Ví dụ, `app-crm-users` là điều kiện được tạo account, còn `crm-support-hanoi` dùng để giới hạn tính năng và khu vực. Có account CRM không tự động cho phép xuất danh sách khách hàng.

### 2.2. Group trong IdP và group tại SaaS không nhất thiết là một

Một doanh nghiệp có thể có nhóm `crm-support-hanoi` trong IdP, nhưng SaaS lại dùng nhóm nội bộ `SupportNorth`. IAM cần một **mapping có quản lý**, tránh dựa hoàn toàn vào trùng tên hiển thị.

Đặc biệt, group ID ổn định thường đáng tin hơn một tên nhóm có thể bị đổi. Khi một group được đổi tên hoặc di chuyển, hệ thống phải kiểm tra tác động lên connector và các mapping hiện hành.

## 3. Kiến trúc tham chiếu cho provisioning theo group

~~~mermaid
flowchart TD
    HR[HRIS / hợp đồng: nguồn danh tính có thẩm quyền] --> EV[Sự kiện Joiner, Mover, Leaver]
    EV --> IAM[IAM lifecycle / Identity Governance]
    IAM --> RULE[Chính sách tính group và duyệt ngoại lệ]
    OWNER[Chủ dữ liệu / chủ ứng dụng] --> RULE
    RULE --> IDP[IdP / Directory: membership, user, group]
    IDP --> CONN[Provisioning connector: SCIM / API / tác vụ thủ công]
    CONN --> APP[SaaS / hệ thống nội bộ]
    APP --> CHECK[Readback trạng thái account, group, role]
    CHECK -->|Khớp| AUDIT[Audit / bằng chứng kết thúc]
    CHECK -->|Lệch hoặc lỗi| REPAIR[Ticket, cảnh báo, retry có kiểm soát]
    REPAIR --> CONN
~~~

> Trong sơ đồ, mỗi khối thể hiện **chức năng**, không nhất thiết là một sản phẩm riêng. Có tổ chức tính membership ngay trong IdP, tổ chức khác dùng bộ máy governance riêng. Hệ thống đích có thể hỗ trợ SCIM hoặc chỉ có API riêng.

Một luồng thông thường gồm các bước:

1. Hệ thống có thẩm quyền phát sự kiện hoặc thuộc tính danh tính mới.
2. Chính sách xác định danh tính có đủ điều kiện tham gia group nào; ngoại lệ được phê duyệt riêng.
3. IAM/IdP tính membership và phát sinh sự kiện bổ sung hoặc loại bỏ thành viên.
4. Provisioning engine xác định ứng dụng nào cần account và role/group nào phải thay đổi.
5. Connector thực thi đến hệ thống đích; thao tác có thể bất đồng bộ.
6. IAM đối soát account, membership và quyền hiệu lực, phát hiện phần còn thiếu hoặc quyền tồn dư.
7. Mỗi quyết định được gắn với event ID, owner, approval, kết quả và thời điểm.

**Điểm mấu chốt:** thay đổi group trong IdP là một bước, còn **cấp/thu hồi quyền thực tế tại ứng dụng** là kết quả cần chứng minh.

## 4. Các loại group và cách quản lý membership

### 4.1. Group tĩnh do người có thẩm quyền quản lý

Một quản trị viên hoặc chủ ứng dụng phê duyệt ai được vào `crm-export-approvers`. Đây là group phù hợp khi quyền nhạy cảm đòi hỏi quyết định riêng, không thể suy ra chỉ từ chức danh.

Điều kiện quản lý:

- Có owner, mục đích, hệ thống đích, mức nhạy cảm và lịch rà soát.
- Thêm/gỡ thành viên theo ticket hoặc workflow có căn cứ.
- Ghi nhận người yêu cầu, người duyệt, người thực thi và ngày hiệu lực.
- Thành viên tạm thời có ngày hết hạn, được thu hồi khi hết hạn.
- Có cơ chế xử lý khi owner rời tổ chức hoặc group không còn dùng.

### 4.2. Group động theo thuộc tính

Một group có thể tính thành viên từ điều kiện:

~~~text
group: crm-support-hanoi

include if:
  identity.type == "employee"
  AND identity.status == "ACTIVE"
  AND identity.department == "customer-support"
  AND identity.region == "HN"

exclude if:
  identity.suspended == true
~~~

Đây là **pseudocode minh họa**, không phải cú pháp policy được hỗ trợ sẵn bởi mọi IdP. Thuộc tính phải đến từ nguồn đáng tin; không nên cho user tự thay `department` hoặc `region` để nhận quyền.

Rủi ro của group động nằm ở chất lượng dữ liệu. Nếu HRIS cập nhật region chậm, membership có thể chậm thay đổi. Nếu một thuộc tính bị nhập sai, nhiều quyền có thể được cấp nhầm đồng thời. Cần kiểm tra chất lượng nguồn, thời điểm hiệu lực và điều kiện loại trừ.

### 4.3. Nhóm lồng nhau (nested groups)

Giả sử:

~~~text
all-customer-support
  ├─ customer-support-hanoi
  └─ customer-support-danang
~~~

Nếu ứng dụng được cấp theo group cha, thành viên nhóm con **có thể** thừa hưởng quyền, nhưng chỉ khi hệ thống IAM/connector/target thực sự hỗ trợ ngữ nghĩa membership lồng nhau phù hợp. Không nên mặc định SCIM hay mọi SaaS tự mở rộng nested groups.

Nested group gây khó khi kiểm toán: nhân viên không có direct membership với group quyền cao nhưng vẫn nhận quyền theo đường kế thừa. Cần tính **effective membership**, xác định nguồn quyền và giới hạn độ sâu hoặc vòng tham chiếu nếu nền tảng yêu cầu.

### 4.4. Group hỗn hợp hoặc ngoại lệ

Group động có thể loại trừ một số thành viên hoặc hỗ trợ ngoại lệ có phê duyệt. Khi thiết kế:

- Quy định thứ tự ưu tiên giữa dynamic rule, manual assignment, deny policy và exception.
- Không cho một thao tác đồng bộ tự động ghi đè quyết định thu hồi khẩn cấp.
- Buộc ngoại lệ có owner, thời hạn và lý do có thể kiểm toán.
- Nếu group bắt nguồn từ cơ sở nhân sự, thay đổi nguồn phải được đánh giá trước khi áp dụng diện rộng.

## 5. Joiner: cấp account và entitlement từ membership

Giả sử doanh nghiệp tuyển Lan vào bộ phận hỗ trợ khách hàng ở Hà Nội. Sự kiện Joiner bắt đầu khi nguồn nhân sự xác nhận bản ghi hợp lệ, trạng thái và ngày bắt đầu.

### 5.1. Luồng Joiner chuẩn

1. **Xác minh danh tính:** có identity ID ổn định, không tạo trùng, có owner và ngày hiệu lực.
2. **Tính group cơ sở:** xác định `employee-base` và nhóm dành cho ứng dụng cần thiết theo vị trí.
3. **Đánh giá quyền nhạy cảm:** group `crm-export-approvers` không tự động được cấp chỉ vì Lan thuộc phòng ban support.
4. **Tạo account/đăng ký SSO:** provisioning engine xử lý account CRM, gán hoặc đồng bộ group cần thiết.
5. **Gán quyền:** connector map group đến role hoặc entitlement thực tế, theo khả năng của CRM.
6. **Đảm bảo ngày hiệu lực:** có thể chuẩn bị trước account nhưng chỉ cho truy cập theo chính sách và thời điểm hợp lệ.
7. **Xác minh:** đăng nhập và thao tác hợp lệ hoạt động; chức năng ngoài quyền bị từ chối.
8. **Lưu bằng chứng:** event, trạng thái account, role, thời điểm, approval và kết quả readback.

### 5.2. Ví dụ mapping cấp account và quyền

| Group nguồn | Điều kiện tham gia | Hành động provisioning | Quyền đích |
|---|---|---|---|
| `app-crm-users` | Công việc yêu cầu CRM | Tạo/kích hoạt tài khoản CRM | Quyền vào ứng dụng, chưa mặc nhiên có quyền cao |
| `crm-support-hanoi` | Nhân viên support thuộc Hà Nội | Cập nhật membership/role trong CRM | Xử lý ticket khách hàng đúng phạm vi Hà Nội |
| `crm-report-viewer` | Có yêu cầu báo cáo được duyệt | Gán role xem báo cáo | Chỉ đọc báo cáo phù hợp |
| `crm-export-approvers` | Chủ dữ liệu phê duyệt có thời hạn | Gán quyền xuất nhạy cảm | Xuất dữ liệu trong phạm vi, hạn sử dụng đã duyệt |

Đây là mô hình nghiệp vụ. Connector có thể chỉ đồng bộ User/Group; ứng dụng đích cần cấu hình role mapping riêng để membership biến thành quyền. Hệ thống không có cơ chế group-to-role tự động có thể cần API đặc thù hoặc thao tác có xác nhận.

### 5.3. SCIM dùng ở bước nào?

**SCIM (System for Cross-domain Identity Management)** hỗ trợ trao đổi dữ liệu danh tính giữa các hệ thống tương thích. Một triển khai điển hình sử dụng endpoint tài nguyên `/Users` và `/Groups` để tạo/cập nhật user, group và membership theo khả năng provider.

Group SCIM có thể được biểu diễn khái niệm như sau:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "displayName": "crm-support-hanoi",
  "members": [
    {
      "value": "user-scim-218",
      "type": "User"
    }
  ]
}
~~~

Đoạn JSON chỉ minh họa cấu trúc tài nguyên Group; `value` phải là định danh phù hợp của user trong hệ thống đích. Trên thực tế, việc thêm thành viên thường dùng API create/update/PATCH theo capability provider, với quy tắc đồng bộ và xử lý lỗi cụ thể.

**SCIM không đồng nghĩa SSO.** SCIM có thể tạo/tắt account hoặc cập nhật membership, còn SSO giúp user xác thực vào ứng dụng. Một ứng dụng đã có SSO nhưng thiếu provisioning vẫn có thể giữ tài khoản cục bộ hoặc group riêng cần quản lý bổ sung.

## 6. Mover: thay đổi group phải gỡ đúng quyền cũ

Mover diễn ra khi Lan đổi phòng ban, khu vực, dự án, vai trò hoặc thời hạn hợp đồng. Với group-based provisioning, hệ thống cần tính lại membership và **quyền hiệu lực** sau sự kiện.

### 6.1. Tình huống chuyển chi nhánh

Lan chuyển từ Hà Nội sang Đà Nẵng:

| Trạng thái | Group Hà Nội | Group Đà Nẵng | Quyền hiệu lực mong đợi |
|---|---:|---:|---|
| Trước Mover | Có | Không | Xem và xử lý dữ liệu thuộc Hà Nội |
| Sau Mover đúng | Không | Có | Chỉ quyền phù hợp Đà Nẵng |
| Sau Mover sai | Có | Có | Có khả năng truy cập dữ liệu cả hai khu vực |

Một engine chỉ *add* group mới mà không *remove* group cũ sẽ tích lũy quyền. Đây là **quyền truy cập tồn dư (residual access)**.

Khi có bàn giao thực sự, quyền cũ có thể giữ tạm nhưng phải có **lý do, phê duyệt, phạm vi hẹp và ngày hết hạn**. Không để group `crm-support-hanoi` tồn tại vô thời hạn vì sợ gián đoạn công việc.

### 6.2. Quyền nhóm không phải nguồn duy nhất

Giả sử Lan không còn thuộc group xuất dữ liệu, nhưng từng được một quản trị viên CRM cấp quyền `export-all` trực tiếp. Sau Mover, xóa membership chưa đủ: direct grant có thể giữ quyền hiệu lực.

IAM phải kiểm tra:

- Direct membership và membership từ nested group.
- Dynamic rule có tái thêm Lan vào group sau khi xóa thủ công không.
- Local role hoặc role mapping khác đang cấp quyền tương đương.
- Group/quyền từ tenant khác hoặc ứng dụng tích hợp.
- Token, session hoặc cache còn phản ánh quyền cũ.
- Ngoại lệ/JIT permission còn hiệu lực.

Đối soát tốt cần nhận diện **con đường cấp quyền (entitlement provenance)**, không chỉ danh sách group ở IdP.

### 6.3. Kiểm tra xung đột nhiệm vụ (SoD)

Giả sử vai trò cũ cho Lan quyền tạo yêu cầu thanh toán, vai trò mới cho Lan quyền phê duyệt. Nếu chính sách yêu cầu tách hai nhiệm vụ, workflow không nên chỉ thêm `finance-approver` vào Lan. Cần kiểm tra *Separation of Duties (SoD)* và có quyết định xử lý trước khi quyền xung đột có hiệu lực.

Lưu ý: với một số quy trình, SoD phải kiểm tra **ở mức giao dịch**, ví dụ một người không được duyệt chính yêu cầu do mình tạo, dù người đó có cả hai vai trò theo chính sách kiểm soát bù trừ đã duyệt.

### 6.4. Thứ tự áp dụng khi Mover

Không có một thứ tự grant/revoke chung cho mọi tình huống:

- Quyền nhạy cảm có xung đột SoD: ưu tiên xử lý quyền cũ trước hoặc đồng thời theo chính sách.
- Chuyển giao cần duy trì hoạt động: có thể dùng cửa sổ chồng lấn ngắn, có TTL và phê duyệt.
- Connector lỗi giữa chừng: trạng thái phải là **PARTIAL**, ghi rõ ứng dụng nào chưa đồng bộ và người xử lý.

Sự kiện phải gắn thời điểm hiệu lực; việc đổi group ngay khi nhận thông báo Mover tương lai có thể cho phép truy cập dữ liệu trước khi nhiệm vụ mới bắt đầu.

## 7. Leaver: vô hiệu hóa identity và thu hồi các đường truy cập liên quan

Khi Lan nghỉ việc, hệ thống có thể xóa Lan khỏi `employee-base` cùng các group ứng dụng hoặc đánh dấu identity inactive. Tuy nhiên, **gỡ membership không tự chấm dứt mọi khả năng truy cập**.

Một quy trình Leaver cần:

1. Xác minh sự kiện kết thúc và thời điểm hiệu lực từ nguồn có thẩm quyền.
2. Chặn đăng nhập mới tại IdP/SSO theo chính sách.
3. Loại bỏ quyền nhóm, role và entitlement tại các ứng dụng; điều chỉnh tài khoản qua SCIM/API nếu provider hỗ trợ.
4. Tìm direct grants, tài khoản cục bộ và group không thuộc nguồn đồng bộ.
5. Thu hồi phiên, refresh token, API key và credential liên quan theo khả năng từng hệ thống.
6. Chuyển giao ownership của tài liệu, tiến trình và nhóm nếu Lan đang giữ vai trò chủ trì.
7. Đọc lại trạng thái account và effective permissions tại từng đích; xử lý connector chưa xác nhận.
8. Ghi bằng chứng, trạng thái cuối và ngoại lệ còn mở.

**Chặn tài khoản IdP không bảo đảm** tất cả SaaS tự hủy session hiện hành. SCIM `active=false` (nếu provider thực thi) thường biểu thị vô hiệu hóa account theo nghĩa API, nhưng cách phiên/token bị ảnh hưởng vẫn phụ thuộc ứng dụng.

Cần phân biệt **disable** để chặn truy cập với **delete** theo chính sách lưu giữ và phụ thuộc dữ liệu. Không xóa account khi vẫn cần chuyển giao dữ liệu hoặc bảo toàn chứng cứ, trừ khi chính sách và yêu cầu áp dụng quy định khác.

## 8. RBAC, ABAC và group-based provisioning

### 8.1. Group là công cụ gán vai trò cho RBAC

**Role-Based Access Control (RBAC)** định nghĩa vai trò và tập quyền; membership trong group có thể là cách điều phối role assignment.

~~~text
Group: crm-support-hanoi
  -> Target role: crm.support-agent
  -> Target scope: region=HN
  -> Allowed actions: ticket.read, ticket.update

Group: crm-report-viewer
  -> Target role: crm.report-reader
  -> Allowed actions: report.read
~~~

Các giá trị là ví dụ; tên group không chứng minh role mapping thực tế. IAM cần sở hữu cấu hình ánh xạ, kiểm soát cập nhật và phát hiện mapping không còn dùng.

### 8.2. ABAC không chỉ là một loại group động

**Attribute-Based Access Control (ABAC)** quyết định dựa trên thuộc tính subject, resource, action và môi trường. Ví dụ:

~~~text
ALLOW nếu:
  subject.status == "ACTIVE"
  AND subject.department == "customer-support"
  AND subject.region == resource.region
  AND action IN ["ticket.read", "ticket.update"]
  AND resource.classification != "restricted"

DENY nếu các điều kiện trên không thỏa
~~~

Khác biệt quan trọng:

- **Dynamic group:** tính membership theo dữ liệu thuộc tính tại một thời điểm; membership có thể được đồng bộ sang SaaS và trở nên chậm cập nhật.
- **ABAC tại API:** có thể xét thuộc tính mới nhất ở mỗi request nếu thiết kế hỗ trợ, không nhất thiết cần group tương ứng cho từng vùng dữ liệu.

Cùng một tổ chức có thể dùng dynamic group để **provision account** và dùng ABAC để **giới hạn dữ liệu theo tenant**. Không tạo hàng nghìn group chỉ để thay thế kiểm tra quyền dữ liệu có thể thực hiện trực tiếp tại API.

### 8.3. Phân quyền theo group không bỏ qua kiểm tra ở API

Giả sử nhân viên nằm trong group `crm-support-hanoi`. API nhận yêu cầu xem hồ sơ `customerId=987`, nhưng hồ sơ thuộc chi nhánh khác. Nếu API chỉ kiểm tra group mà không kiểm tra chi nhánh trên dữ liệu thật, nhân viên có thể xem thông tin trái phạm vi.

Vì vậy, **group/role chỉ cung cấp một phần thông tin**; điểm thực thi quyền phải kiểm tra action và resource thực tế cùng điều kiện áp dụng.

## 9. Thiết kế an toàn cho group và mapping

### 9.1. Đặt group theo mục đích và ranh giới quyền

Những nguyên tắc thực hành:

- Dùng tên thể hiện ứng dụng, môi trường, mức quyền và phạm vi khi phù hợp.
- Duy trì ID ổn định; không lấy tên hiển thị làm khóa duy nhất.
- Không dùng một group `all-users-admin` cho nhiều hệ thống có mức rủi ro khác nhau.
- Tách group **đủ điều kiện truy cập ứng dụng** khỏi group **có quyền nhạy cảm**.
- Tách production và staging nếu ranh giới tin cậy/quyền khác nhau.
- Mỗi mapping cần owner, ngày áp dụng, lý do và quy trình thay đổi.

### 9.2. Tránh group sprawl

**Group sprawl** là hiện tượng số nhóm tăng nhanh nhưng ý nghĩa chồng lấn hoặc không còn được quản trị. Ví dụ, một dự án tạo `sales-read-2024`, `sales-read-v2` và `sales-read-temp`, nhưng cả ba còn cấp quyền sau khi dự án kết thúc.

Để giảm rủi ro:

- Lập danh mục group và mapping đi kèm owner, purpose, target và review date.
- Áp dụng quy trình tạo/đổi/xóa group; không cho phép tùy tiện đặt tên gần trùng.
- Tách group vĩnh viễn theo công việc khỏi ngoại lệ có TTL.
- Phát hiện group không thành viên, không hệ thống đích, không owner hoặc không hoạt động.
- Trước khi xóa group, kiểm tra ứng dụng/phụ thuộc có còn sử dụng hay không.

### 9.3. Dùng group quyền cao có kiểm soát

Với group cấp quyền admin, cần xem xét **Privileged Access Management (PAM)** hoặc **Just-In-Time (JIT)**:

- Người yêu cầu nêu tác vụ và thời gian sử dụng.
- Quyền được duyệt theo chính sách và phạm vi cụ thể.
- Chỉ thêm membership có thời hạn hoặc kích hoạt role tương ứng đúng lúc.
- Hết hạn thì loại khỏi group, thu hồi/kiểm tra phiên và quyền thực tế.
- Audit ghi lại ai kích hoạt, thời gian, tài nguyên và thao tác liên quan.

Việc xóa người khỏi group JIT **chưa chứng minh** session đặc quyền đã chấm dứt ở hệ thống đích.

### 9.4. Phân tách trách nhiệm quản lý group

Người tạo group, người phê duyệt group nhạy cảm, người cấu hình mapping và người kiểm toán có thể cần vai trò khác nhau. Một quản trị viên có khả năng kỹ thuật sửa membership không mặc nhiên nên có quyền tự cấp cho mình mọi đặc quyền mà không có kiểm soát.

## 10. SCIM và ứng dụng đích: các giới hạn cần thiết kế trước

Không phải connector nào cũng hỗ trợ group theo cùng cách.

| Tình huống | Khả năng gặp phải | Cách xử lý |
|---|---|---|
| App nhận User nhưng không hỗ trợ Group | Account tạo được, membership không đồng bộ | Dùng mapping role/API khác hoặc tác vụ có xác nhận |
| App chỉ nhận group được chỉ định | Người ở nhóm ngoài phạm vi không được sync | Xác minh danh sách group/assignment và người không có account |
| Nested group không tự mở rộng | Thành viên gián tiếp không được cấp quyền | Tính effective membership ở nguồn nếu mô hình và connector cho phép |
| Group được đổi tên | Mapping theo tên bị lệch | Dùng ID ổn định hoặc quản lý thay đổi mapping có readback |
| Local grants không do connector quản lý | Gỡ group nguồn nhưng quyền ở SaaS vẫn còn | Rà soát entitlement thực tế và xử lý quyền ngoài phạm vi connector |
| Token/session không bị thu hồi | Tài khoản/role đổi nhưng phiên cũ vẫn dùng được | Xem khả năng revoke, tuổi token, session control và kiểm chứng |
| Provider áp dụng bất đồng bộ | API nhận lệnh nhưng quyền chưa đổi | Dùng trạng thái pending, retry/backoff và đối soát |
| Connector giới hạn số lượng/nhịp | Lỗi khi cập nhật hàng loạt | Queue, batch, quota control, retry có giới hạn và cảnh báo |

Một số hệ thống dùng “group push” như luồng đồng bộ đối tượng nhóm, một số dùng **assignment group** chỉ để chọn người được provisioning. Hai cơ chế này không đương nhiên tương đương. Cần kiểm tra rõ **nhóm nào tạo account, nhóm nào được đồng bộ sang đích và nhóm nào thực sự gán role**.

### 10.1. Không đồng bộ quyền khi nguồn chưa đủ tin cậy

Khi HRIS thay đổi thuộc tính từ `region=HN` sang rỗng, không nên lập tức suy đoán region mặc định `ALL`. Một giá trị thiếu có thể cần giữ trạng thái `PENDING_REVIEW`, áp dụng chính sách deny cho quyền nhạy cảm hoặc yêu cầu xác minh nguồn. Hành vi phải được thiết kế trước và nhất quán, nhất là với group động có quyền truy cập dữ liệu lớn.

### 10.2. Nhận sự kiện trùng và không đúng thứ tự

Giả sử sự kiện Mover đổi Lan sang Đà Nẵng đến sau sự kiện Leaver do độ trễ hàng đợi. Nếu hệ thống tự chạy Mover cũ để thêm `crm-support-danang`, tài khoản đã thu hồi có thể được cấp quyền trở lại.

Cần có:

- ID sự kiện, thời điểm hiệu lực và phiên bản trạng thái danh tính.
- Quy tắc không cấp quyền cho identity đã kết thúc trừ khi có quy trình khôi phục hợp lệ.
- Idempotency để xử lý sự kiện lặp không thêm group hai lần hoặc tạo account trùng.
- Kiểm tra trạng thái hiện tại trước khi retry những yêu cầu cũ.
- Readback tại đích sau mỗi đợt đồng bộ.

## 11. Ví dụ end-to-end: một nhân viên đi qua Joiner–Mover–Leaver

Giả sử công ty có ba nhóm:

~~~text
app-crm-users
crm-support-hanoi
crm-support-danang
~~~

Quy định: người làm support được dùng CRM; quyền dữ liệu dựa trên chi nhánh đang phụ trách.

### 11.1. Joiner

**Sự kiện:** Ngày 01/12, Lan bắt đầu làm việc tại chi nhánh Hà Nội.

- Nguồn nhân sự phát danh tính `emp-0218`, `department=support`, `region=HN`, `status=active` đúng ngày hiệu lực.
- Chính sách đưa Lan vào `app-crm-users` và `crm-support-hanoi`.
- Connector tạo tài khoản CRM nếu chưa có, đồng bộ group/role theo khả năng ứng dụng.
- IAM đối soát Lan có thể xử lý ticket Hà Nội và không được đọc ticket Đà Nẵng.

### 11.2. Mover

**Sự kiện:** Ngày 01/03, Lan chuyển sang Đà Nẵng.

| Giai đoạn | app-crm-users | crm-support-hanoi | crm-support-danang |
|---|---|---|---|
| Trước Mover | Có | Có | Không |
| Trạng thái đích | Có | Không | Có |
| Nếu xử lý lỗi | Có | Có | Có |

Quy trình đúng loại bỏ membership Hà Nội, cấp Đà Nẵng, kiểm tra quyền qua API và giải quyết cache/token còn mang dữ liệu quyền cũ nếu có. Tài khoản CRM vẫn tồn tại vì Lan tiếp tục cần ứng dụng.

### 11.3. Leaver

**Sự kiện:** Ngày 15/05, Lan kết thúc hợp đồng.

- Identity được đưa vào trạng thái không còn hiệu lực.
- Hệ thống thu hồi membership, tắt account CRM theo chính sách và connector.
- Kiểm tra không có local grant, session hoặc token còn đường truy cập trái chính sách.
- Đối soát mọi ứng dụng thuộc phạm vi Lan từng sử dụng, không chỉ CRM.
- Lưu bằng chứng theo event ID và người chịu trách nhiệm.

### 11.4. Bảng kết quả kiểm tra

| Kiểm tra | Expected | Điều cần xác minh |
|---|---|---|
| Sau Joiner | Có CRM account | Tồn tại đúng một account gắn `emp-0218` |
| Sau Joiner | Chỉ có quyền khu vực Hà Nội | Quyền trong API không vượt tenant/region |
| Sau Mover | Không còn quyền Hà Nội | Gỡ membership và direct grant liên quan |
| Sau Mover | Có quyền Đà Nẵng | Quyền mới đã được cấp và cho phép thao tác hợp lệ |
| Sau Leaver | Không còn truy cập CRM | Account, session/token và local permissions theo khả năng hệ thống |
| Sau Leaver | Có dấu vết | Sự kiện, lệnh, người duyệt, kết quả và readback |

## 12. Account provisioning theo group cho ứng dụng và tài khoản dịch vụ

Group thường được liên hệ với user, nhưng một số hệ thống còn quản lý service account hoặc workload principal bằng group/role để cấp quyền. Cần xác định rõ nguồn thẩm quyền:

- Nhân viên có sự kiện vòng đời từ HRIS.
- Service principal có sự kiện từ danh mục ứng dụng, deployment, CI/CD hoặc hệ thống sở hữu workload.
- User và service principal không nên mặc nhiên dùng chung group có quyền cao.
- Mỗi tài khoản dịch vụ cần owner kỹ thuật/nghiệp vụ, mục đích và ngày rà soát.
- Khi dịch vụ chuyển từ staging sang production, đánh giá group/role và trust theo ranh giới môi trường.
- Khi dịch vụ ngừng sử dụng, thu hồi group, API key, secret, certificate và quyền còn ở hệ thống đích.

Group cấp quyền cho workload nên giới hạn tài nguyên và thời hạn theo nhu cầu. Một **service account** không có con người đăng nhập vẫn có thể tích lũy quyền và trở thành mục tiêu khi credential bị lộ.

## 13. Kiểm toán và đối soát quyền theo group

### 13.1. Nguồn quyền cần có khả năng truy vết

Khi kiểm toán hỏi “Tại sao Lan có quyền `crm.export`?”, hệ thống lý tưởng có thể trả lời:

- Lan là identity nào và hiện có trạng thái hợp lệ không.
- Quyền được cấp từ group nào, thuộc tính nào hoặc approval nào.
- Group do ai quản lý và rule mapping nào tạo ra entitlement.
- Quyền phát sinh lúc nào, có hết hạn hay không.
- Hệ thống đích nào đã xác nhận quyền được cấp.
- Có đường cấp quyền khác như direct assignment hoặc nested membership không.

Không lưu secret, token thô hoặc dữ liệu cá nhân không cần thiết vào nhật ký chỉ để phục vụ audit.

### 13.2. Ví dụ bản ghi thay đổi group

~~~json
{
  "eventId": "iam-group-2026-0251",
  "identityId": "emp-0218",
  "eventType": "GROUP_MEMBERSHIP_REMOVED",
  "groupId": "grp-crm-support-hanoi",
  "trigger": "MOVER_REGION_CHANGE",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "policyVersion": "crm-group-policy-v4",
  "targetApplication": "crm",
  "executionStatus": "SUCCESS",
  "verificationStatus": "PENDING_TARGET_READBACK",
  "correlationId": "CHG-6219"
}
~~~

Đây là **schema minh họa**. `executionStatus=SUCCESS` chỉ phản ánh thao tác đã thực hiện; `verificationStatus` vẫn chờ cho đến khi có bằng chứng quyền thực tế ở CRM. Không nên đánh dấu `CONFIRMED_REVOKED` nếu chưa đối soát.

### 13.3. Chỉ số hiệu quả

| Chỉ số | Ý nghĩa | Sai lầm khi đo |
|---|---|---|
| Tỷ lệ user được provisioning đúng hạn | Joiner có account/quyền cần thiết theo ngày hiệu lực | Chỉ đo “đã gửi yêu cầu”, không kiểm tra app |
| Thời gian thu hồi quyền nhóm | Từ lúc Mover/Leaver có hiệu lực đến khi xác minh | Lấy thời gian xóa nhóm nguồn làm thời gian kết thúc |
| Số entitlement tồn dư | Quyền có tại đích mà không còn căn cứ | Bỏ qua direct grants, nested groups, local accounts |
| Tỷ lệ mapping có owner | Group-to-target mapping được quản trị | Chỉ đếm group có tên mà không xét owner |
| Số ngoại lệ hết hạn chưa xử lý | Quyền cấp tạm còn tồn tại quá hạn | Không phân biệt đã duyệt với đã thực thu hồi |
| Tỷ lệ đồng bộ có readback | Connector thay đổi thành công và đích được kiểm chứng | Đếm phản hồi API là trạng thái cuối |
| Số group không có mục đích/chủ | Dấu hiệu group sprawl | Xóa ngay mà không rà soát phụ thuộc |

Đặt mục tiêu thời gian theo độ nhạy cảm tài nguyên và quy định của tổ chức, không giả định một SLA phù hợp với mọi loại quyền.

## 14. Các tình huống lỗi thường gặp

### 14.1. Người dùng bị gỡ group nhưng vẫn xem được dữ liệu

**Nguyên nhân có thể:** membership lồng nhau, direct grant, role local, token cũ hoặc cache.  
**Xử lý:** xác định nguồn quyền, tính effective membership, truy vấn quyền tại ứng dụng, xử lý phiên và xác minh hành động bị từ chối khi không còn hợp lệ.

### 14.2. Thành viên group được tạo nhưng không có account

**Nguyên nhân có thể:** group chỉ dùng để gán role, chưa nằm trong phạm vi application assignment; connector lỗi hoặc app chưa hỗ trợ provisioning user.  
**Xử lý:** kiểm tra mapping group, assignment scope, phản hồi SCIM/API và trạng thái user tại đích. Không đánh đồng group membership với account đã được tạo.

### 14.3. Chuyển chi nhánh xong lại được thêm về group cũ

**Nguyên nhân có thể:** dynamic rule đọc dữ liệu HRIS chưa cập nhật, cache thuộc tính hoặc còn một nguồn gán membership khác.  
**Xử lý:** điều tra source of truth và thứ tự sự kiện; sửa rule và đối soát quyền sau khi dữ liệu nguồn ổn định.

### 14.4. Cấp lại quyền sau khi người dùng đã nghỉ việc

**Nguyên nhân có thể:** job retry sự kiện Joiner/Mover cũ, sự kiện đến sai thứ tự hoặc rule chưa xét trạng thái Leaver.  
**Xử lý:** dùng event version, policy chặn cấp quyền cho identity đã kết thúc và readback account đích.

### 14.5. Group cấp quyền admin cho một ứng dụng nhưng không rõ ai sở hữu

**Nguyên nhân:** group được tạo ad hoc, owner đổi vai trò hoặc dự án kết thúc.  
**Xử lý:** xác minh mục đích và owner, rà soát thành viên, phân quyền tối thiểu, áp dụng PAM/JIT nếu phù hợp, xử lý group không còn cần.

## 15. Bài tập tự kiểm tra

**Tình huống A:** Nhân viên mới nằm trong group `app-finance-users` nhưng không thể đọc báo cáo. Có phải provisioning thất bại hoàn toàn?

**Gợi ý:** Chưa chắc. Có thể account được tạo đúng nhưng role/entitlement đọc báo cáo chưa được cấp hoặc chưa được đồng bộ. Cần kiểm tra cả account và quyền ở hệ thống đích.

**Tình huống B:** Sau khi chuyển phòng ban, người dùng bị xóa khỏi group `sales` nhưng vẫn xuất được báo cáo bán hàng.

**Gợi ý:** Kiểm tra nested groups, direct grants, role nội bộ, token và session. Kết luận thu hồi chỉ dựa trên group nguồn là chưa đủ.

**Tình huống C:** Một group động lấy `department=finance` từ thuộc tính có thể do user tự cập nhật.

**Gợi ý:** Đây là lỗ hổng nguồn thuộc tính: quyền nhạy cảm có thể bị tự cấp. Thuộc tính làm căn cứ IAM cần nguồn có thẩm quyền và kiểm soát thay đổi.

**Tình huống D:** IAM gửi lệnh SCIM thêm nhóm thành công nhưng app chưa hiện membership sau hai phút.

**Gợi ý:** Đừng đánh dấu hoàn tất theo phản hồi gửi lệnh. Kiểm tra tính bất đồng bộ, retry phù hợp, đọc lại trạng thái đích và phản ánh PENDING/PARTIAL đúng thực tế.

**Tình huống E:** Một bot dùng quyền production dựa trên group vốn dành cho nhân viên.

**Gợi ý:** Đánh giá tách group và principal theo workload, owner, môi trường, TTL/credential, audit và nguồn kích hoạt vòng đời riêng.

## 16. Checklist triển khai provisioning theo group

Trước khi triển khai một luồng mới, kiểm tra các câu hỏi sau:

1. **Nguồn danh tính:** HRIS/hợp đồng/danh mục workload nào có thẩm quyền và cung cấp ID ổn định?
2. **Ngữ nghĩa group:** group dùng để tạo account, đồng bộ membership hay cấp role? Có phân biệt rõ?
3. **Ownership:** ai sở hữu group, mapping và entitlement đích; ai duyệt quyền nhạy cảm?
4. **Membership:** group tĩnh/động/lồng nhau được tính thế nào và thuộc tính có đáng tin không?
5. **Ngày hiệu lực:** Joiner, Mover, Leaver có cập nhật membership đúng thời điểm không?
6. **RBAC/ABAC:** role/permission và điều kiện trên tài nguyên được thực thi ở đâu?
7. **Least privilege/SoD:** group có cấp dư quyền hoặc tạo xung đột nhiệm vụ không?
8. **SSO/SCIM:** xác thực, provisioning user và đồng bộ group được tách đúng chức năng chưa?
9. **Connector:** hệ thống đích có hỗ trợ group, nested membership và role mapping cần thiết không?
10. **Quyền tồn dư:** đã kiểm tra direct grant, local role, credential, token, session và đường cấp quyền khác chưa?
11. **Lỗi đồng bộ:** có idempotency, thứ tự sự kiện, retry, PENDING/PARTIAL và escalation không?
12. **Readback:** trạng thái account và quyền thực tế tại từng đích đã được xác minh chưa?
13. **Audit:** có truy được event, policy, approval, group, connector và kết quả cuối không?
14. **Rà soát:** có lịch đánh giá group/mapping, owner và ngoại lệ hết hạn không?

**Ghi nhớ:** Provisioning theo group dùng **membership làm tín hiệu điều phối tài khoản và quyền**, giúp tự động hóa IAM theo vòng đời **Joiner–Mover–Leaver**. Sự an toàn phụ thuộc vào nguồn danh tính có thẩm quyền, group/mapping rõ ý nghĩa, RBAC/ABAC đúng phạm vi, phối hợp IdP–SCIM–ứng dụng và bước **đối soát quyền thực tế**. Mỗi lần thêm nhóm phải có căn cứ; mỗi lần đổi vai trò hoặc kết thúc quan hệ phải tìm và thu hồi cả quyền truy cập tồn dư ngoài group.
