# Đối soát account trong Account provisioning

> **Chương: Account provisioning.** Đối soát account (**account reconciliation**) là quá trình xác định, so sánh và xử lý chênh lệch giữa **trạng thái tài khoản, quyền truy cập phải có theo chính sách** và **trạng thái thực tế tại các hệ thống đích**. Nó giúp phát hiện tài khoản thiếu, tài khoản mồ côi, quyền dư thừa, đồng bộ sai và truy cập tồn dư sau Joiner–Mover–Leaver. Đối soát là một vòng kiểm soát liên tục, không chỉ là thao tác kiểm tra API sau khi cấp phát.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **provisioning**, **reconciliation**, **access review** và **authentication**, cũng như ba trạng thái **desired**, **observed** và **verified**.
2. Xây dựng danh mục tài khoản với định danh ổn định và ánh xạ từ HR/nguồn có thẩm quyền qua IAM, IdP đến ứng dụng đích.
3. So sánh tài khoản, trạng thái kích hoạt, nhóm, vai trò, quyền trực tiếp, phạm vi dữ liệu và các đường truy cập ngoài SSO.
4. Thiết kế đối soát theo **Joiner–Mover–Leaver**, ưu tiên thu hồi khi có Leaver và ngăn quyền cũ được tái cấp.
5. Xử lý sai lệch an toàn bằng retry có kiểm soát, idempotency, phân loại rủi ro, phê duyệt và xác minh kết quả.
6. Áp dụng IdP, SCIM, RBAC/ABAC, kiểm toán và các chỉ số vận hành để giảm **residual access**.

## 1. Đối soát account là gì?

Khi một nhân viên vào công ty, workflow IAM có thể tạo User tại IdP, thêm người đó vào nhóm và gửi lệnh SCIM tới các ứng dụng. Khi họ chuyển vị trí, hệ thống phải tính lại quyền. Khi nghỉ việc, hệ thống phải ngừng quyền truy cập. Nhưng các lệnh này có thể bị timeout, bị cấu hình sai, bị ghi đè thủ công hoặc không bao phủ hết những tài khoản đã tồn tại.

**Provisioning** thực thi việc tạo, sửa, vô hiệu hóa hoặc thu hồi tài khoản và quyền. **Reconciliation** kiểm tra thực tế, tìm độ lệch so với trạng thái mong muốn và quyết định bước xử lý tiếp theo.

Ví dụ:

- HR báo nhân viên **Lan** đã chuyển từ nhóm hỗ trợ sang kế toán.
- IAM tính rằng Lan **không còn** role SupportAgent và **cần** role FinanceViewer.
- IdP đã cập nhật nhóm đúng; ứng dụng CRM vẫn giữ role SupportAgent do một connector lỗi.
- Đối soát phát hiện role thừa ở CRM và yêu cầu thu hồi; sau đó **đọc lại từ CRM** để xác nhận quyền thật sự đã mất.

Nếu chỉ tin thông báo “workflow thành công”, quyền dư thừa có thể tồn tại nhiều tuần. Đối soát giải quyết khoảng cách giữa **lệnh đã gửi** và **kết quả thực tế**.

### Các khái niệm cần tách biệt

| Khái niệm | Câu hỏi trả lời | Đầu ra |
| --- | --- | --- |
| **Provisioning** | Hệ thống cần thực hiện thay đổi gì? | Lệnh tạo, cập nhật, vô hiệu hóa User/Group/quyền. |
| **Reconciliation** | Trạng thái đích hiện tại có khớp chính sách và thay đổi được yêu cầu không? | Sai lệch, nguyên nhân, hành động sửa và bằng chứng readback. |
| **Access certification / review** | Chủ sở hữu hoặc người quản lý có xác nhận người này còn cần quyền không? | Quyết định nghiệp vụ, thu hồi hoặc ngoại lệ được duyệt. |
| **Authentication** | Người đang đăng nhập có chứng minh được quyền kiểm soát authenticator không? | Kết quả xác thực, phiên, token. |
| **Authorization** | Chủ thể có được thực hiện hành động trên tài nguyên trong điều kiện hiện tại không? | Quyết định allow/deny tại ứng dụng/API. |
| **Identity correlation** | Account ở ứng dụng đích thuộc danh tính IAM nào? | Liên kết có căn cứ, hoặc case cần điều tra. |

Đối soát account **không thay thế** access certification: kỹ thuật có thể chứng minh Lan đang có role FinanceViewer, nhưng việc role đó có cần cho công việc hay không vẫn thuộc chính sách và các chủ sở hữu có thẩm quyền.

## 2. Desired state, observed state và verified state

Mô hình cốt lõi của đối soát có ba lớp:

1. **Desired state (trạng thái mong muốn):** account và quyền mà người dùng **được phép và cần có**, tính từ nguồn nhân sự/hợp đồng, sự kiện JML, chính sách RBAC/ABAC, phê duyệt và ngoại lệ còn hiệu lực.
2. **Observed state (trạng thái quan sát):** account và quyền **đang được hệ thống đích báo cáo**, thu thập qua SCIM/API, directory, IAM connector, export được kiểm soát hoặc phương thức được phép khác.
3. **Verified state (trạng thái đã kiểm chứng):** kết quả quan sát đủ mới và đủ độ tin cậy để khẳng định điều kiện kiểm soát cần thiết đã đạt, sau khi xét phạm vi API, độ trễ, quyền gián tiếp, phiên và đường truy cập ngoài nguồn quan sát.

**Một phản hồi 200 OK từ lệnh cập nhật không phải là readback.** Nó thường chỉ cho biết máy chủ tiếp nhận hoặc xử lý yêu cầu theo hợp đồng API; kiểm chứng cần dùng khả năng đọc trạng thái thực tế và hiểu đúng ngữ nghĩa của hệ thống.

### Ví dụ sai lệch

| Đối tượng | Desired | Observed | Kết luận sơ bộ |
| --- | --- | --- | --- |
| IdP User của Lan | ENABLED | ENABLED | Khớp ở lớp tài khoản IdP. |
| Vai trò FinanceViewer tại ERP | Có, phạm vi đơn vị B | Không có | Thiếu quyền hợp lệ; có thể gây gián đoạn công việc. |
| Vai trò SupportAgent tại CRM | Không còn | Vẫn có | Quyền thừa sau Mover; ưu tiên xử lý theo rủi ro. |
| API token cá nhân tại Git | Không còn sau Leaver | Còn hoạt động | Truy cập tồn dư; cần thu hồi và xác minh riêng. |
| Tài khoản SaaS X | Không có vì chưa được phê duyệt | Tìm thấy tài khoản không rõ owner | Cần xác minh danh tính; không vội xóa nhầm. |

Trạng thái **unknown** phải khác **absent**. Nếu API đích bị lỗi hoặc chưa quét đủ trang, ta **không biết** account có tồn tại hay không; không được kết luận rằng tài khoản đã bị xóa.

### Đối soát theo chiều và phạm vi

Không chỉ so sánh cờ hoạt động:

| Chiều so sánh | Ví dụ | Rủi ro khi bỏ qua |
| --- | --- | --- |
| **Tồn tại account** | User Git có/không có. | Tài khoản mồ côi hoặc thiếu account cần cho công việc. |
| **Trạng thái** | Enabled, disabled, suspended. | Account vẫn đăng nhập được sau Leaver. |
| **Nhóm và vai trò** | Member của SupportAgent, GitMaintainer. | Quyền thừa hoặc thiếu theo role. |
| **Quyền trực tiếp** | ACL trên repository, database grant. | Quyền nằm ngoài nhóm IdP không được thu hồi. |
| **Phạm vi** | Tenant, department, project, dữ liệu được phân công. | Đọc dữ liệu chéo tenant dù role hợp lệ. |
| **Thời hạn và ngoại lệ** | JIT admin hết hạn, quyền dự án 30 ngày. | Quyền tạm trở thành quyền vĩnh viễn. |
| **Phiên và credential** | PAT, API key, SSH key, session. | Khóa User nhưng vẫn dùng token/credential cũ. |
| **Owner và nguồn** | Identity người dùng, service owner, source system. | Không biết ai chịu trách nhiệm hoặc thu hồi nhầm. |

Các chiều không phải lúc nào cũng đọc được qua cùng một API. Nếu SCIM chỉ trả account và Group, muốn kiểm tra ACL cục bộ hoặc PAT có thể cần API quản trị ứng dụng hoặc quy trình inventory riêng.

## 3. Tập dữ liệu cần để đối soát đúng người

Điều kiện đầu tiên của một phép diff có ý nghĩa là biết **account nào thuộc identity nào**. Một người có thể có nhiều account ở IdP, email, CRM, Git, ERP hoặc cloud; một account có thể có tên giống người khác.

### Mô hình ánh xạ

~~~mermaid
flowchart LR
    HR["Nguồn có thẩm quyền<br/>HR / hợp đồng / service registry"] --> IAM["IAM Identity<br/>identityId + lifecycle state"]
    IAM --> IDP["IdP User<br/>idpUserId"]
    IAM --> CRM["CRM Account<br/>crmAccountId"]
    IAM --> GIT["Git Account<br/>gitAccountId"]
    IAM --> SAAS["SaaS Account<br/>scim User id"]
    IAM --> D["Desired entitlements<br/>policy + approval"]
    IDP --> O["Observed inventory"]
    CRM --> O
    GIT --> O
    SAAS --> O
    D --> R["Reconciliation engine"]
    O --> R
    R --> A["Diff, xử lý, xác minh<br/>và kiểm toán"]
~~~

Các thông tin tối thiểu:

| Trường dữ liệu | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **identityId** | Định danh bền vững trong IAM. | Không đồng nhất với username hoặc email. |
| **sourceAuthority + sourcePersonId** | Khóa được cấp bởi nguồn có thẩm quyền. | Phải có namespace; cùng một ID số có thể xuất hiện ở hai nguồn. |
| **targetSystem + tenant** | Đích và phạm vi quản lý của account. | Mã User có thể chỉ duy nhất trong một tenant. |
| **localAccountId** | Mã account do hệ thống đích cấp. | Ưu tiên dùng để truy vấn/ghi thay vì tìm bằng tên hiển thị. |
| **externalId/correlationKey** | Khóa liên kết từ provisioning nếu đích hỗ trợ. | Kiểm tra quyền sở hữu, tính duy nhất và độ tin cậy của phép ánh xạ. |
| **owner** | Người/nhóm chịu trách nhiệm cho account hoặc dịch vụ. | Bắt buộc khi phát hiện ngoại lệ/tài khoản máy. |
| **desiredEntitlements** | Nhóm, role, scope, giới hạn thời gian được duyệt. | Phải có nguồn chính sách và phiên bản. |
| **observedEntitlements** | Quyền đích thực sự trả về. | Ghi thời điểm quét, độ đầy đủ và API đã dùng. |
| **lastReconciledAt** | Thời điểm đọc và xác minh gần nhất. | Quá cũ phải được đánh dấu stale, không coi là current. |

**Không ghép account chỉ bằng email hoặc displayName.** Email có thể đổi/tái sử dụng; tên có thể trùng. Nếu khóa liên kết mâu thuẫn, xử lý qua case identity resolution có bằng chứng. Đừng gán một tài khoản quản trị chưa rõ chủ sở hữu cho người bất kỳ chỉ để giải quyết cảnh báo.

### Ví dụ record đối soát nội bộ

Đây là JSON minh họa cho một hệ thống IAM, **không phải SCIM schema**:

~~~json
{
  "identityId": "ID-LAN-104",
  "sourceKey": "HRIS:EMP-104",
  "target": {
    "system": "CRM",
    "tenant": "tenant-b",
    "localAccountId": "crm-u-509"
  },
  "desired": {
    "accountState": "ENABLED",
    "roles": [],
    "effectiveAt": "2026-12-01T08:00:00+07:00",
    "policyVersion": "iam-roles-v7"
  },
  "observed": {
    "accountState": "ENABLED",
    "roles": ["SupportAgent"],
    "observedAt": "2026-12-01T08:05:00+07:00"
  },
  "diff": ["UNEXPECTED_ROLE"],
  "reconciliationState": "ACTION_REQUIRED"
}
~~~

Với tình huống này, chưa thể chỉ dựa vào JSON để nói Lan chắc chắn không có token hoặc ACL cục bộ khác. Engine cần biết dữ liệu quét đã đầy đủ và có khả năng kiểm chứng những chiều quyền liên quan.

## 4. Nguồn dữ liệu và tính tin cậy của kết quả

**Desired state** phải được tính từ dữ liệu có thẩm quyền, không lấy trực tiếp từ hiện trạng đang sai. **Observed state** phải được đọc từ hệ thống đích hoặc nguồn inventory được kiểm soát, không suy ra từ việc connector trước đó đã gửi lệnh gì.

| Nguồn | Cung cấp | Không thể tự chứng minh |
| --- | --- | --- |
| **HRIS/HCM / hệ thống hợp đồng** | Quan hệ công việc, ngày hiệu lực, bộ phận, manager/sponsor. | Account SaaS đã khóa và token đã rút. |
| **IAM/IGA** | identityId, mapping, quyết định quyền, yêu cầu, phê duyệt, ngoại lệ. | Quyền đích đã áp dụng chỉ vì workflow ghi SUCCESS. |
| **IdP/directory** | User, nhóm, trạng thái xác thực và các thông tin được quản lý. | ACL cục bộ trong mọi ứng dụng và mọi session. |
| **SCIM service provider** | User/Group theo schema và khả năng triển khai. | Mọi role nghiệp vụ, PAT và session nằm ngoài SCIM. |
| **Application admin API** | Role, ACL, license, dữ liệu dự án hoặc token tùy ứng dụng. | Những đường truy cập mà API không liệt kê. |
| **PAM/cloud IAM** | Phiên đặc quyền, role, policy và đường cấp quyền quản trị. | Tất cả tài khoản doanh nghiệp nếu chưa tích hợp. |
| **Audit/telemetry** | Hoạt động sử dụng quyền và dấu hiệu truy cập bất thường. | Một quyền không dùng gần đây là quyền không cần thiết. |

### Snapshot, delta và checkpoint

Có hai cách lấy trạng thái:

- **Full reconciliation:** đọc toàn bộ account/entitlement thuộc phạm vi quản lý để tìm drift, account bỏ sót và lỗi lâu ngày. Tốn chi phí hơn nhưng cần thiết khi dữ liệu thay đổi ngoài luồng hoặc mất sự kiện.
- **Incremental reconciliation:** chỉ đọc thay đổi sau một checkpoint/sự kiện, giúp phản ứng nhanh và giảm tải. Phải có cơ chế phát hiện event bị mất, checkpoint sai hoặc trễ.

Nên kết hợp **event-driven checks** ngay sau Joiner/Mover/Leaver với **full scan có lịch theo rủi ro**. Độ đầy đủ của inventory phụ thuộc phân trang, giới hạn API, tenant, filter, quyền connector và thời gian quét; kết quả quét dở dang phải được đánh dấu **INCOMPLETE**, không thay thế snapshot đầy đủ trước đó bằng một danh sách rỗng.

### Tính nhất quán cuối cùng

Sau khi cập nhật SCIM hoặc directory, trạng thái ứng dụng có thể chưa phản ánh ngay vì cache, hàng đợi hoặc **eventual consistency**. Không phải mọi chênh lệch xuất hiện vài giây đều là lỗi vĩnh viễn.

Một bộ đối soát cần:

1. Ghi thời điểm gửi lệnh và khoảng trễ đã được hệ thống đích công bố/đo lường.
2. Đặt trạng thái **PENDING_VERIFICATION** trong thời gian chờ hợp lệ.
3. Retry readback với giới hạn hợp lý; phân biệt lỗi API và dữ liệu thật sự sai.
4. Đưa sai lệch quá hạn tới owner, ưu tiên cao hơn nếu là quyền thừa sau Leaver.
5. Không kéo dài vô hạn khoảng chờ để che giấu quyền truy cập tồn dư.

## 5. Đối soát trong Joiner–Mover–Leaver

Mỗi sự kiện vòng đời phải dẫn đến một **desired state được tính lại**, chứ không chỉ là một lệnh cộng/trừ nhóm rời rạc.

| Sự kiện | Desired account state | Sai lệch cần chú ý | Phản ứng |
| --- | --- | --- | --- |
| **Joiner** | Identity hợp lệ; tài khoản cần thiết được tạo/kích hoạt đúng ngày; quyền nền tối thiểu. | Account thiếu, được kích hoạt sớm, gán sai người hoặc có admin mặc định. | Kiểm tra nguồn/proofing, sửa provisioning, giới hạn kích hoạt. |
| **Mover** | Giữ account hợp lệ nhưng tính lại role, nhóm, tenant và phạm vi. | Quyền cũ vẫn còn, quyền mới chưa cấp, SoD vi phạm. | Gỡ quyền cũ, cấp quyền mới được duyệt, xác minh toàn bộ quyền hiệu lực. |
| **Leaver** | Không còn đường truy cập trái chính sách; account và credential được vô hiệu hóa/thu hồi. | Account cục bộ còn active, token còn hạn, nhóm lồng nhau hoặc PAT chưa thu hồi. | Ưu tiên khóa, revoke, kiểm soát bù và readback từng đích. |
| **Rehire** | Tái liên kết danh tính có căn cứ; cấp lại quyền theo công việc mới. | Tái mở account cũ với quyền quản trị/quyền tích lũy. | Identity resolution và proofing khi cần, không tự khôi phục quyền cũ. |
| **Contract extension** | Tiếp tục quyền đúng hợp đồng mới, thời hạn và phê duyệt. | Quyền đã hết hạn hoặc bị kéo dài không duyệt. | Xác minh sự kiện nguồn, cập nhật thời hạn và lịch thu hồi. |

### Joiner: vừa đủ quyền, đúng thời điểm

Đối soát ngay sau provisioning cần kiểm tra:

- Account đích có được tạo cho **đúng người** hay không.
- User chưa được kích hoạt trước ngày hiệu lực nếu chính sách không cho phép.
- Chỉ có những nhóm, role và quyền nền cần cho nhiệm vụ, không có quyền quản trị mặc định.
- Ứng dụng bắt buộc đã sẵn sàng; những đích lỗi ở trạng thái pending/failure rõ ràng.

**IdP đã có User** không đồng nghĩa mọi ứng dụng đã có account hoặc đã có đúng quyền. Đối soát theo từng hệ thống giúp phân biệt thành công một phần và hoàn tất thực tế.

### Mover: xử lý tích lũy đặc quyền

Ví dụ Lan chuyển từ hỗ trợ sang kế toán. Đối soát phải phát hiện và gỡ SupportAgent tại CRM, giữ những quyền chung vẫn hợp lệ, đồng thời kiểm tra FinanceViewer ở ERP có đúng scope hay chưa.

Nếu IAM chỉ gửi “thêm FinanceViewer” và đọc lại vai trò mới, có thể bỏ sót **quyền tồn dư** từ nhóm cũ. Vì thế phải tính **toàn bộ tập quyền mong muốn** và so sánh cả quyền đáng lẽ bị loại.

### Leaver: ưu tiên không còn truy cập

Mục tiêu Leaver không chỉ là đổi một cờ `active=false`. Từng đích cần đánh giá khả năng đăng nhập, session/token, nhóm và tài khoản quản trị.

**Đặc biệt quan trọng:** nếu một job Joiner hoặc Mover cũ được retry sau Leaver, nó không được mở lại quyền. Mọi hành động cấp/bật account cần kiểm tra **trạng thái vòng đời và version mới nhất** trước khi thực thi.

### Quyền truy cập tồn dư không chỉ là group membership

Một nhân viên đã nghỉ việc có thể không còn trong nhóm IdP nhưng vẫn giữ:

- Tài khoản nội bộ không liên kết SSO.
- Session đã đăng nhập trên SaaS.
- Access token tự chứa vẫn còn hạn.
- PAT, API key, SSH key hoặc client certificate cá nhân.
- Quyền ACL trực tiếp tại repository hoặc database.
- Một tài khoản admin khác chưa được ánh xạ đúng.

Những đường này cần inventory và thu hồi riêng. SCIM không tự động rút mọi session/token; ID token hay thông báo logout cũng không thay thế kiểm tra từng hệ thống.

## 6. Quy trình đối soát end-to-end

~~~mermaid
flowchart TD
    T["Sự kiện JML hoặc lịch quét"] --> D["Tính desired state<br/>HR + chính sách + phê duyệt"]
    D --> O["Đọc observed state<br/>IdP, SCIM, app API, PAM"]
    O --> C{"Dữ liệu quan sát<br/>đủ và tin cậy?"}
    C -->|Không| U["INCOMPLETE / UNKNOWN<br/>retry, cảnh báo, không xóa mù"]
    C -->|Có| I["Liên kết identity ↔ account<br/>kiểm tra namespace/tenant"]
    I --> E{"Ánh xạ có chắc chắn?"}
    E -->|Không| M["MANUAL_REVIEW<br/>ngăn sửa nhầm người"]
    E -->|Có| F["Diff account, role, scope,<br/>credential và hiệu lực"]
    F --> K{"Loại sai lệch?"}
    K -->|Khớp| V["VERIFIED<br/>lưu bằng chứng"]
    K -->|Thiếu quyền hợp lệ| P["Provision theo chính sách<br/>phê duyệt khi cần"]
    K -->|Quyền thừa/truy cập tồn dư| R["Revoke / disable<br/>ưu tiên theo rủi ro"]
    P --> Q["Readback và kiểm tra kết quả"]
    R --> Q
    Q --> Z{"Đúng trạng thái?"}
    Z -->|Có| V
    Z -->|Chưa| X["PARTIAL_FAILURE<br/>retry / escalation / owner"]
~~~

### Bước 1 — Xác định phạm vi và chủ sở hữu

Chọn nguồn, hệ thống đích, tenant, loại identity và các chiều quyền được kiểm tra. Phân biệt **tài nguyên do IAM quản lý** với những quyền cục bộ do owner ứng dụng quản lý. Nếu kết quả đối soát đòi thay đổi dữ liệu ngoài phạm vi quản lý, phải chuyển owner và quy trình phê duyệt phù hợp, không xóa tùy tiện.

### Bước 2 — Tính desired state hiện hành

Lấy trạng thái HR/hợp đồng, role công việc, thuộc tính ABAC, yêu cầu được duyệt, SoD và thời hạn ngoại lệ. **Leaver đã có hiệu lực** phải ngăn lệnh cấp lại quyền dù queue cũ vẫn còn job. Các ngoại lệ chỉ thuộc desired state nếu có chủ sở hữu, căn cứ, phạm vi và hạn hiệu lực.

### Bước 3 — Thu thập observed state với dấu thời gian

Gọi API có đủ quyền đọc, phân trang toàn bộ kết quả, lưu version/checkpoint nếu được hỗ trợ. Ghi **observedAt**, mức đầy đủ của phép quét và lỗi từng nguồn. Không xem dữ liệu cache cũ như một snapshot hiện hành.

### Bước 4 — Normalize và correlate account

Chuẩn hóa tên nhóm/role theo mapping được quản trị; xác định account bằng **local ID, source key và tenant**, tránh suy luận theo email. Kiểm tra xung đột và tài khoản trùng. Nếu không chắc chắn, mở case cần review thay vì gắn account cho sai người.

### Bước 5 — Diff và đánh giá tác động

So sánh account tồn tại/trạng thái, membership, role, scope, thời hạn, credential và điểm kiểm soát đăng nhập. Phân loại:

- **MATCH:** đủ bằng chứng rằng các chiều trong phạm vi đã khớp.
- **MISSING_ACCOUNT / MISSING_ENTITLEMENT:** thiếu tài khoản hoặc quyền hợp lệ.
- **UNEXPECTED_ACCOUNT / UNEXPECTED_ENTITLEMENT:** tài khoản hoặc quyền thừa.
- **STATE_MISMATCH:** account phải disabled nhưng vẫn enabled, hoặc ngược lại.
- **IDENTITY_CONFLICT:** account liên kết mơ hồ, trùng hoặc có dấu hiệu nhầm người.
- **OBSERVATION_INCOMPLETE:** thiếu dữ liệu để kết luận.

### Bước 6 — Remediate có kiểm soát

Với sai lệch rủi ro thấp, thuộc phạm vi IAM quản lý và có chính sách rõ, có thể tự động sửa. Với xóa dữ liệu, tài khoản đặc quyền, mâu thuẫn định danh, credential dùng chung hoặc thay đổi vượt owner, nên yêu cầu đánh giá thích hợp.

**Thu hồi quyền thừa** và **cấp quyền thiếu** có mức độ rủi ro khác nhau. Không tự cấp đặc quyền chỉ vì thấy “thiếu” nếu quyền chưa được phê duyệt; cũng không giữ quyền nguy hiểm vô hạn chỉ vì API từ chối lệnh thu hồi.

### Bước 7 — Verify, audit và theo dõi sai lệch

Sau khi thay đổi, truy vấn lại hệ thống đích, so sánh kết quả với desired state mới nhất, xác minh account hoặc entitlement liên quan. Nếu chưa khớp, đặt trạng thái **PENDING_VERIFICATION** hoặc **PARTIAL_FAILURE**, mở cảnh báo, retry có hạn và gán owner. Log cần chứng minh **điều gì đã thay đổi, vì sao, bởi ai, khi nào và được xác minh thế nào**.

## 7. Triển khai đối soát qua SCIM và IdP

**SCIM 2.0 (System for Cross-domain Identity Management)** cung cấp mô hình User/Group và API giúp quản lý tài khoản. Đây là một nguồn quan sát hữu ích nếu ứng dụng đích hỗ trợ các truy vấn cần thiết.

### Đọc User bằng định danh và filter

Ví dụ HTTP minh họa, endpoint/khả năng filter tùy service provider:

~~~http
GET /scim/v2/Users?filter=externalId%20eq%20%22EMP-104%22 HTTP/1.1
Accept: application/scim+json
Authorization: Bearer [REDACTED]
~~~

Một phản hồi User đơn giản có thể chứa:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "id": "scim-u-509",
  "externalId": "EMP-104",
  "userName": "lan@example.org",
  "active": true
}
~~~

Các lưu ý:

- **id** là mã tài nguyên do SCIM service provider cấp; dùng làm khóa đích khi cập nhật đúng User.
- **externalId** do provisioning client cung cấp để liên kết với nguồn. Cần xem độ tin cậy, tính duy nhất và phạm vi tenant, không mặc định mọi ứng dụng sử dụng giống nhau.
- **userName** có thể thay đổi theo cấu hình; không dùng email/username làm bằng chứng duy nhất khi liên kết tài khoản.
- **active** là trạng thái tài khoản theo cách triển khai service provider, không chứng minh mọi access token, session và quyền nghiệp vụ đã bị thu hồi.

Với quét toàn bộ User/Group, cần xử lý phản hồi **ListResponse**, phân trang (chẳng hạn startIndex/count), tổng số và các giới hạn mà nhà cung cấp công bố. Đừng bỏ qua các bản ghi ngoài trang đầu hoặc kết luận “account không tồn tại” khi truy vấn bị từ chối hoặc timeout.

### Đối soát Group membership và role

SCIM hỗ trợ tài nguyên Group, nhưng **ứng dụng có thể thực thi quyền bằng role hoặc ACL ngoài Group**. Đối soát phải xác định mapping:

| Nguồn quyền | Quan sát ở đâu? | Ví dụ sai lệch |
| --- | --- | --- |
| Nhóm IdP | IdP/directory | Lan đã rời SupportAgent nhưng còn group gián tiếp. |
| SCIM Group | SCIM service provider | Lan còn là member của nhóm CRM-Support. |
| Application role | Admin API của ứng dụng | Role BillingAdmin được gán trực tiếp ngoài SCIM. |
| Cloud IAM policy | API quyền cloud | Quyền wildcard ở project cũ chưa gỡ. |
| Permission ở cấp dữ liệu | Resource API / policy engine | Lan đọc được dữ liệu tenant khác dù role đúng. |

Đối soát group ở SCIM không đồng nghĩa xác nhận được **effective permission** của mọi API. Khi muốn chứng minh quyền bị thu hồi, cần hiểu mô hình authorization của ứng dụng và kiểm tra tại điểm thực thi phù hợp.

### Cập nhật đích chỉ khi xác minh đúng User

Ví dụ một lệnh SCIM PatchOp để vô hiệu hóa account sau Leaver, chỉ áp dụng khi **đã resolve chính xác local User ID** và service provider hỗ trợ:

~~~http
PATCH /scim/v2/Users/scim-u-509 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Sau lệnh phải **GET/readback** account đích và kiểm tra những kênh truy cập ngoài SCIM. Không dùng response của lệnh PATCH làm bằng chứng duy nhất về việc người dùng đã hoàn toàn mất quyền.

## 8. Thuật toán đối soát và tính an toàn khi thực thi

Pseudocode sau minh họa kiến trúc **reconcile loop**, không phải mã có thể đưa trực tiếp vào sản xuất:

~~~text
reconcileAccount(identityId, targetId):
    identity = loadIdentity(identityId)
    latest = loadAuthoritativeLifecycle(identity.sourceKey)
    desired = calculateDesiredState(identity, latest, policies, approvals)

    snapshot = readTargetSnapshot(targetId, withPagination=true)
    if not snapshot.complete or snapshot.stale:
        recordUnknown(identityId, targetId, snapshot.reason)
        scheduleSafeRetry()
        return OBSERVATION_INCOMPLETE

    account = correlateByTrustedKeys(
        identityId,
        targetId,
        snapshot,
        tenantNamespace
    )
    if account.isAmbiguous:
        openIdentityResolutionCase(identityId, targetId)
        return MANUAL_REVIEW

    differences = diff(desired, account.observedState)
    decisions = classifyByRiskAndOwnership(differences)

    for each decision in decisions:
        if decision.requiresApproval:
            createApprovalCase(decision)
            continue
        if decision.actionIsGrant:
            assert noEffectiveLeaver(latest)
            assert policyAndApprovalStillValid(identity)
        applyIdempotently(decision, expectedVersion=latest.version)

    verified = readBackAndCheckCurrentDesiredState(identityId, targetId)
    recordAudit(identityId, targetId, differences, decisions, verified)

    if verified.allRequiredChecksPass:
        return VERIFIED
    return PARTIAL_FAILURE
~~~

### Vì sao phải đọc desired state lại trước khi cấp quyền?

Trong hệ thống bất đồng bộ:

1. Joiner tạo task cấp DeveloperReader.
2. HR phát Mover sang bộ phận khác hoặc Leaver có hiệu lực.
3. Task cũ được retry sau timeout.

Nếu retry vẫn cấp theo snapshot cũ, quyền không còn hợp lệ có thể được khôi phục. Vì vậy, job mang **source version/correlation ID**, hành động cấp quyền phải kiểm tra trạng thái **hiện hành**; thao tác ghi có thể cần compare-and-set, khóa đồng thời hoặc fencing token tùy kiến trúc. Leaver hiệu lực phải chặn cấp lại quyền trái chính sách.

### Idempotency và partial failure

Một lần đối soát có thể thực hiện nhiều thao tác ở nhiều hệ thống không hỗ trợ giao dịch nguyên tử. Quy trình cần:

- **Idempotency:** lệnh lặp không tạo account mới hoặc cấp role trùng; dùng khóa tác vụ và mapping ổn định.
- **Checkpoint có kiểm soát:** chỉ đánh dấu đã xử lý một batch khi dữ liệu và kết quả đạt điều kiện; có khả năng resume.
- **Retry với backoff và giới hạn:** phân biệt timeout/rate limit với lỗi dữ liệu/chính sách không thể retry tự động.
- **Readback:** khi không chắc lệnh PATCH/POST đã thành công, truy vấn lại trước khi gửi tiếp.
- **Per-target status:** ghi riêng từng đích, không nuốt lỗi chỉ vì IdP đã cập nhật.
- **Compensation:** nếu phải hoàn tác, chỉ đụng đến tài nguyên/quyền mà hệ thống thực sự có quyền quản lý và biết chính xác trạng thái trước đó.

Không xóa tự động một account chỉ vì nó xuất hiện trong observed nhưng không có trong desired: có thể đó là account đang phục vụ người khác, do hệ thống khác quản lý, hoặc đang bị ánh xạ sai. Cần kiểm tra owner, nguồn và quyền hạn của phép sửa.

## 9. Các dạng drift và cách xử lý

| Dạng sai lệch | Dấu hiệu | Xử lý ưu tiên |
| --- | --- | --- |
| **Orphan account** | Account hoạt động nhưng không có identity/owner hợp lệ. | Điều tra nguồn, tenant và người sử dụng; hạn chế rủi ro, gán owner hoặc thu hồi theo thẩm quyền. |
| **Missing account** | Joiner hợp lệ nhưng app bắt buộc không có User. | Kiểm tra event, mapping và provisioning; tạo đúng account nếu đủ điều kiện. |
| **Duplicate account** | Nhiều User ở cùng đích có vẻ thuộc một identity. | Soát bằng khóa ổn định, không gộp hoặc xóa chỉ dựa tên/email. |
| **Excess privilege** | Role/ACL trực tiếp ngoài desired; quyền không có phê duyệt. | Ưu tiên thu hồi theo rủi ro, kiểm tra SoD và owner. |
| **Missing entitlement** | Role hợp lệ chưa xuất hiện tại đích. | Xác minh nhu cầu/approval hiện hành trước khi cấp. |
| **Stale group** | Thành viên nhóm cũ sau Mover. | Tính lại quyền toàn phần và thu hồi ở IdP/ứng dụng. |
| **Leaver residual access** | Account disabled nhưng token, PAT hoặc session còn dùng được. | Chặn/thu hồi đường truy cập theo tính năng đích; ghi hạn tồn dư và kiểm soát bù. |
| **Unmanaged local admin** | Có account admin không gắn identity IAM. | Điều tra owner, chuyển vào quản trị hoặc xử lý truy cập theo chính sách đặc quyền. |
| **Service identity drift** | Workload bị bỏ nhưng credential/role vẫn còn. | Kiểm tra registry, owner, trust policy; thu hồi khi dịch vụ không còn. |
| **Observation gap** | API lỗi, thiếu pagination, quyền connector đọc không đủ. | Khôi phục quan sát, chưa kết luận absent hoặc verified. |
| **Unauthorized manual change** | Admin tự sửa role tại SaaS ngoài workflow. | Kiểm tra nguồn thay đổi, mức rủi ro, SoD; xử lý và audit. |

### Quyền trực tiếp và quyền kế thừa

Một quyền có thể xuất phát từ:

- Gán role trực tiếp cho User.
- Nhóm con thuộc nhóm lớn, hoặc vai trò kế thừa.
- ACL trên tài nguyên riêng lẻ.
- Điều kiện ABAC dựa trên department, tenant, ownership hoặc trạng thái phiên.
- Phiên đặc quyền tạm thời thông qua PAM.

Nếu chỉ đọc danh sách role gán trực tiếp, engine có thể đánh giá thiếu quyền hiệu lực hoặc bỏ qua quyền gián tiếp. Cần mô hình hóa cách từng sản phẩm **tính effective permissions**, và ghi rõ những lớp nào đã kiểm tra được.

## 10. Đối soát tài khoản dịch vụ và workload

Tài khoản máy thường không có HR event trực tiếp, nhưng vẫn có vòng đời và rủi ro quyền tồn dư. Một job có thể bị ngừng hoặc chuyển owner mà token vẫn chạy, service principal vẫn có quyền production hoặc trust relationship vẫn chấp nhận workload cũ.

Đối soát workload nên dùng:

| Thành phần | Desired state | Observed cần kiểm tra |
| --- | --- | --- |
| **Workload registry** | Dịch vụ đang được phê duyệt, có owner kỹ thuật/nghiệp vụ. | Danh tính service principal thực tế có owner và purpose hay không. |
| **Deployment/environment** | Workload chỉ chạy ở môi trường được duyệt. | Namespace, cloud project, cluster và liên kết trust. |
| **Permissions** | Chỉ API/tài nguyên/hành động cần thiết. | Role, policy, quyền wildcard hoặc kế thừa. |
| **Credentials** | Ưu tiên token/chứng chỉ ngắn hạn và quản lý bí mật theo chính sách. | Secret tồn lâu, credential không owner hoặc chưa rotate. |
| **Decommission** | Không còn identity/credential khi dịch vụ ngừng. | Account, key và trust relationship vẫn còn hoặc còn được dùng. |

Nếu nhân viên sở hữu dịch vụ nghỉ việc, **không xóa máy móc service account đang phục vụ hệ thống hợp lệ**. Cần xác định owner mới, loại bỏ credential cá nhân còn được biết, xoay vòng bí mật và đối soát quyền máy. Khi workload bị decommission, mới thực hiện thu hồi identity máy theo quy trình tương ứng.

## 11. Kiểm toán và chỉ số chất lượng đối soát

### Bằng chứng kiểm toán cần có

Một lần reconciliation nên cho phép trả lời:

1. **Identity nào, account nào, tenant nào** được rà soát? Căn cứ liên kết là gì?
2. **Desired state** được tính từ nguồn nào, version nào, role/approval nào và có hiệu lực lúc nào?
3. **Observed state** được đọc từ API nào, vào thời điểm nào, có quét đủ hay không?
4. **Diff nào** được phát hiện? Mức rủi ro, người chịu trách nhiệm và lý do quyết định sửa?
5. **Ai/cái gì** đã thực thi lệnh, kết quả API ra sao, có retry hoặc ngoại lệ không?
6. **Readback** chứng minh gì, thiếu bằng chứng ở lớp account, role, token hay session nào?
7. **Lỗi còn lại** có owner, hạn xử lý, kiểm soát bù và cảnh báo phù hợp không?

Ví dụ log nội bộ, không phải schema tiêu chuẩn:

~~~json
{
  "runId": "recon-20261201-001",
  "identityId": "ID-LAN-104",
  "sourceKey": "HRIS:EMP-104",
  "sourceVersion": 51,
  "target": "CRM",
  "tenant": "tenant-b",
  "localAccountId": "crm-u-509",
  "observation": {
    "capturedAt": "2026-12-01T08:05:00+07:00",
    "complete": true
  },
  "differences": [
    {"type": "UNEXPECTED_ROLE", "value": "SupportAgent"}
  ],
  "action": "REMOVE_ROLE",
  "result": "VERIFIED",
  "verifiedAt": "2026-12-01T08:06:10+07:00",
  "correlationId": "move-104-v51"
}
~~~

Nhật ký cần bảo vệ quyền đọc, tính toàn vẹn và thời hạn lưu giữ. Không lưu mật khẩu, secret, private key, access token nguyên vẹn hoặc dữ liệu cá nhân không cần cho kiểm toán. Những API đọc quyền có thể rất nhạy cảm và phải được kiểm soát quyền truy cập như API ghi.

### Chỉ số vận hành

| Chỉ số | Cách dùng | Lưu ý |
| --- | --- | --- |
| **Reconciliation coverage** | Tỷ lệ account/đích nằm trong phạm vi đã có inventory đáng tin. | Đừng đánh đồng “đã kết nối API” với quét đủ account và quyền. |
| **Drift rate** | Số account/entitlement khác desired state trong một kỳ. | Phân nhóm theo quyền thừa, thiếu và loại ứng dụng. |
| **Residual access after Leaver** | Số đường truy cập còn lại sau mốc kết thúc. | Ưu tiên quyền đặc quyền, dữ liệu nhạy cảm và kênh không SSO. |
| **Time to detect / remediate** | Độ trễ phát hiện và xử lý drift. | So với thời điểm sự kiện có hiệu lực, không chỉ thời điểm batch chạy. |
| **Orphan/duplicate account count** | Chất lượng ánh xạ danh tính và owner. | Xác minh trước khi sửa để không khóa nhầm. |
| **Partial failure rate** | Tỷ lệ phép đồng bộ sửa sai chưa hoàn tất. | Ghi kết quả theo từng hệ thống và nguyên nhân. |
| **Unverified / incomplete scan rate** | Tỷ lệ kết quả chưa đủ dữ liệu kết luận. | Theo dõi retry, quyền connector và lỗi phân trang. |
| **Exception overdue** | Ngoại lệ và sai lệch quá hạn vẫn chưa giải quyết. | Đảm bảo có người chịu trách nhiệm và hạn rõ ràng. |
| **Unauthorized change recurrence** | Tần suất quyền bị sửa ngoài quy trình rồi xuất hiện lại. | Cần xử lý nguyên nhân gốc, không chỉ liên tục ghi đè. |

Đặt chu kỳ quét và mức ưu tiên dựa trên rủi ro. Tài khoản đặc quyền hay quyền truy cập dữ liệu nhạy cảm thường cần quan sát thường xuyên và xử lý nhanh hơn tài khoản ít nhạy cảm. Không áp một ngưỡng SLA duy nhất cho mọi hệ thống.

## 12. Tình huống thực hành

### Tình huống A — Mover nhưng quyền cũ còn tồn tại

**Bối cảnh:** Lan chuyển từ hỗ trợ sang kế toán. IdP đã bỏ nhóm SupportAgent; CRM còn role SupportAgent được gán trực tiếp.

**Câu hỏi:** Nếu chỉ đối soát nhóm IdP, kết luận nào có thể sai?

**Gợi ý:** Có thể kết luận quyền cũ đã thu hồi dù CRM vẫn cho phép sử dụng role trực tiếp. Cần đọc role/ACL tại CRM, so với desired state và thu hồi qua kênh có thẩm quyền, rồi readback.

### Tình huống B — Leaver và token còn hạn

**Bối cảnh:** IdP và SCIM đều ghi account của Minh là disabled, nhưng PAT của Git vẫn được dùng sau thời điểm nghỉ việc.

**Câu hỏi:** Có thể đánh dấu Leaver là VERIFIED toàn bộ không?

**Gợi ý:** Chưa. SCIM và IdP không chứng minh tất cả token/phiên đã bị rút. Cần inventory PAT, cơ chế revoke riêng, kiểm tra mức tiếp tục sử dụng và ghi nhận hạn hoặc biện pháp kiểm soát bù.

### Tình huống C — Bản quét trả danh sách rỗng

**Bối cảnh:** Đợt quét một SaaS trả trang đầu rỗng do API bị giới hạn quyền; batch ghi nhận “không có tài khoản tồn dư”.

**Câu hỏi:** Lỗi suy luận nằm ở đâu?

**Gợi ý:** Phản hồi quét thiếu/không được cấp quyền đọc không phải bằng chứng account absent. Cần phát hiện incomplete, lỗi API/pagination/tenant và không coi kết quả đó là verified.

### Tình huống D — Tài khoản lạ cùng email

**Bối cảnh:** SaaS báo một account dùng cùng email với nhân viên vừa nghỉ việc, nhưng account không có mapping identityId, có thể thuộc tenant khác.

**Câu hỏi:** Có nên disable account ngay không?

**Gợi ý:** Không suy luận chỉ từ email. Cần xác minh tenant, local account ID, nguồn tạo và owner; áp kiểm soát theo rủi ro/thẩm quyền đối với đường truy cập thực sự thuộc Leaver, tránh khóa nhầm.

### Tình huống E — Quyền được sửa rồi tự xuất hiện trở lại

**Bối cảnh:** Reconciliation xóa role admin trái chính sách nhưng một đồng bộ khác lại thêm role đó sau mỗi giờ.

**Câu hỏi:** Vì sao việc tự động xóa liên tục chưa giải quyết vấn đề?

**Gợi ý:** Có ít nhất hai nguồn quản lý quyền xung đột hoặc một nguồn cấp quyền ngoài quy trình. Cần xác định **field ownership** và source of authority, sửa nguyên nhân cấp lại, kiểm tra phê duyệt, SoD và audit.

### Tình huống F — Service account không còn owner

**Bối cảnh:** Chủ dịch vụ nghỉ việc, account của job sao lưu vẫn hoạt động và giữ quyền database rộng.

**Câu hỏi:** Đối soát nên làm gì để vừa an toàn vừa tránh làm hỏng backup?

**Gợi ý:** Kiểm tra workload còn cần thiết, chuyển owner hợp lệ, giảm quyền theo chức năng, rotate credential và kiểm tra job. Nếu không còn dịch vụ, thu hồi trust/account sau khi xác minh phụ thuộc.

## 13. Câu hỏi tự kiểm tra

**1. Một API trả thành công khi gửi yêu cầu xóa nhóm. Điều này chứng minh quyền đã mất chưa?**

Chưa chắc. Cần đọc lại nhóm/role tại đích, xét quyền kế thừa và những đường truy cập độc lập.

**2. Vì sao desired state không thể đơn thuần sao chép từ observed state?**

Observed có thể chứa quyền sai, quyền dư thừa hoặc account không owner. Desired phải dựa trên sự kiện nguồn, chính sách, approval và ngoại lệ hợp lệ.

**3. Khi API quét thất bại, observed state nên được diễn giải là gì?**

**UNKNOWN/INCOMPLETE**, không phải không có account hay không có quyền.

**4. Khi Mover, đối soát phải chỉ kiểm tra role mới hay cả role cũ?**

Phải so sánh **toàn bộ tập quyền mong muốn** để nhận diện cả quyền thiếu và quyền tích lũy không còn hợp lệ.

**5. Có thể dùng email làm khóa duy nhất để nối User ở HR với tài khoản SaaS không?**

Không nên. Email có thể đổi, trùng hoặc tái sử dụng; cần khóa nguồn ổn định, local ID, namespace/tenant và bước resolve đáng tin cậy.

**6. Leaver đã có hiệu lực, nhưng job Joiner cũ được retry. Phải làm gì?**

Chặn cấp lại quyền dựa trên trạng thái và version nguồn hiện hành, thu hồi đường truy cập đã tạo nhầm và kiểm tra readback.

**7. Vì sao service account cũng phải được đối soát?**

Danh tính máy có thể giữ quyền quá rộng hoặc tồn tại sau khi workload ngừng, dù không có HR event. Cần owner, source có thẩm quyền, permission scope và quy trình thu hồi riêng.

## Ghi nhớ

- **Đối soát account** là so sánh **desired state** với **observed state**, xử lý drift và chỉ khẳng định thành công ở phần **đã kiểm chứng bằng bằng chứng phù hợp**.
- Cần nối identity tới account bằng **định danh ổn định, local account ID và namespace/tenant**, không suy luận chỉ từ tên/email.
- **Joiner** kiểm tra đúng account và quyền nền; **Mover** loại quyền cũ và cập nhật quyền mới; **Leaver** kiểm chứng không còn đường truy cập trái chính sách.
- **IdP/SSO/SCIM** hỗ trợ xác thực và provisioning nhưng không tự cho biết tất cả role, ACL, token, session hoặc credential tại mọi ứng dụng.
- **Idempotency, nguồn dữ liệu có thẩm quyền, trạng thái JML mới nhất, kiểm tra completeness, retry có hạn và readback** ngăn cấp quyền sai, bỏ sót account và mở lại quyền sau thu hồi.
- **Least privilege, RBAC/ABAC, owner rõ ràng, kiểm toán và đo lường rủi ro** giúp biến đối soát thành cơ chế giảm quyền truy cập tồn dư một cách liên tục.
