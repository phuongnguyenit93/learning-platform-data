# Luồng cấp và thu hồi quyền trong IAM

> **Chương:** Tổng kết IAM lifecycle  
> **Phạm vi:** Quản lý vòng đời danh tính (Identity and Access Management, IAM) theo mô hình **Joiner–Mover–Leaver**, từ xác minh, tạo tài khoản, cấp quyền, thay đổi vai trò, rà soát đến thu hồi. Bài học tập trung vào cách phối hợp IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán nhằm giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả từng bước trong luồng **yêu cầu → xác minh → quyết định quyền → phê duyệt → thực thi → đối soát → kiểm toán**.
2. Phân biệt **quyền mong muốn** với **quyền thực tế**, tìm được quyền đến từ nhóm, vai trò, ACL trực tiếp, token hoặc tài khoản phụ.
3. Thiết kế cấp quyền tối thiểu dựa trên vai trò/thuộc tính, có chủ sở hữu, mục đích, phê duyệt và thời hạn.
4. Xây dựng thu hồi quyền cho Mover, Leaver, quyền hết hạn, access review và tình huống an ninh khẩn cấp.
5. Giải thích vì sao khóa IdP/SSO hoặc xóa một nhóm chưa đủ chứng minh quyền ở ứng dụng đích đã mất.
6. Xử lý lỗi đồng bộ, sự kiện đến sai thứ tự và lưu đủ bằng chứng chứng minh cấp/thu hồi hoàn tất.

**Câu hỏi trung tâm:** *Ai được làm gì trên tài nguyên nào, vì sao, được ai cho phép, đến khi nào, và lấy bằng chứng ở đâu để chứng minh quyền đã được cấp hoặc thu hồi đúng?*

**Grant** (cấp quyền) làm xuất hiện khả năng thực hiện hành động được phê duyệt. **Revoke** (thu hồi) loại bỏ khả năng đó khi lý do cấp quyền hết hiệu lực. Mỗi đường cấp quyền phải có cách thu hồi tương ứng và một phương pháp kiểm chứng kết quả.

## 2. Thành phần của một quyền truy cập

Một yêu cầu “cho người dùng truy cập ứng dụng” có thể liên quan nhiều đối tượng:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity** | Danh tính của chủ thể trong tổ chức | Nhân viên mã EMP-2104 |
| **Account** | Đối tượng ở IdP hoặc từng ứng dụng | Tài khoản CRM, user repository |
| **Credential** | Bằng chứng để xác thực | Passkey, mật khẩu, SSH key, certificate |
| **Session/token** | Quyền đăng nhập/ủy quyền đã phát hành | Phiên trình duyệt, refresh token, PAT |
| **Role/group** | Tập quyền theo công việc hoặc nhóm | Support-Agent, Finance-Viewer |
| **Entitlement** | Quyền cụ thể trên tài nguyên | tickets:update, reports:export |
| **Resource** | Đối tượng cần bảo vệ | Ticket, dữ liệu khách hàng, bucket |
| **Policy** | Quy tắc quyết định điều kiện truy cập | RBAC, ABAC, MFA, thiết bị tin cậy |
| **Grant source** | Đường cấp ra quyền hiệu lực | Nhóm IdP, app role, ACL trực tiếp, key |
| **Owner** | Người/nhóm chịu trách nhiệm phê duyệt | Chủ dữ liệu, chủ ứng dụng, quản lý |

**Authentication** xác minh *chủ thể là ai*; **authorization** quyết định *chủ thể được làm gì*. SSO hỗ trợ xác thực liên kết, SCIM hỗ trợ provision user/group tại hệ thống đích. Không nên dùng thành công của một luồng để suy ra luồng kia đã hoàn tất.

### 2.1. Quyền mong muốn khác quyền hiệu lực thực tế

Ký hiệu:

- **D (desired)**: tập quyền được phép theo chính sách và phê duyệt tại thời điểm đang xét.
- **A (actual/effective)**: tập quyền thực sự có hiệu lực ở ứng dụng sau khi tính toàn bộ nguồn cấp và điều kiện.

~~~text
grantCandidates  = D - A     # Quyền hợp lệ còn thiếu
revokeCandidates = A - D     # Quyền hiệu lực không còn lý do
keep             = A ∩ D     # Quyền vẫn cần duy trì
~~~

Đây là phép tính **mục tiêu**, chưa phải thao tác API. Một quyền có thể đến từ nhiều nguồn; để thực sự thu hồi, phải xử lý mọi đường còn cấp quyền đó. Đồng thời, role có mặt không nhất thiết đồng nghĩa quyền thực thi được, vì hệ đích có thể áp dụng **deny**, điều kiện ABAC hoặc policy theo bối cảnh.

### 2.2. Một quyền có nhiều đường cấp

~~~mermaid
flowchart LR
    U["Chủ thể EMP-2104"] --> G1["Nhóm IdP: Support"]
    U --> G2["Nhóm app: Data-Exporters"]
    U --> D["Direct grant: reports:export"]
    G1 --> R1["tickets:read"]
    G2 --> R2["reports:export"]
    D --> R2
    R2 --> X["Quyền xuất dữ liệu"]
~~~

Khi gỡ nhóm Data-Exporters, direct grant vẫn có thể cho phép người dùng xuất dữ liệu. **Xóa membership thành công** là bằng chứng một thao tác đã xảy ra; **thu hồi quyền thành công** đòi hỏi chứng minh người dùng không còn đường truy cập hợp lệ.

## 3. Luồng chung cấp và thu hồi quyền

~~~mermaid
flowchart TD
    E["Yêu cầu / sự kiện JML / lịch hết hạn / kết quả rà soát"] --> V{"Xác minh nguồn, danh tính, mục đích, thời điểm"}
    V -->|Không hợp lệ| REJ["Từ chối, bổ sung dữ liệu hoặc ghi ngoại lệ"]
    V -->|Hợp lệ| P["Tính trạng thái quyền mong muốn"]
    P --> A{"Cần phê duyệt / kiểm tra SoD?"}
    A -->|Có| REVIEW["Owner / chủ dữ liệu quyết định"]
    REVIEW -->|Từ chối| REJ
    REVIEW -->|Cho phép| PLAN["Lập kế hoạch thay đổi theo hệ đích"]
    A -->|Không| PLAN
    PLAN --> APPLY["Thực thi: IdP, SCIM/API, ACL, token, session"]
    APPLY --> VERIFY["Đọc lại quyền hiệu lực tại từng đích"]
    VERIFY --> M{"Khớp trạng thái mục tiêu?"}
    M -->|Có| DONE["Lưu bằng chứng và đóng workflow"]
    M -->|Không| FIX["Retry có giới hạn / escalation / đối soát"]
    FIX --> VERIFY
~~~

Sáu công đoạn cần tách bạch:

1. **Kích hoạt:** ghi rõ ai yêu cầu hoặc sự kiện nguồn nào khiến quyền phải thay đổi.
2. **Xác minh:** kiểm tra chủ thể, nguồn đáng tin cậy, thời điểm có hiệu lực, mapping tài khoản và dữ liệu nghiệp vụ.
3. **Quyết định:** tính quyền hợp lệ theo vai trò/thuộc tính, phê duyệt đặc quyền và kiểm tra xung đột nhiệm vụ.
4. **Thực thi:** thay đổi trên IdP, ứng dụng, cloud, ACL, credential và session theo phạm vi thực tế.
5. **Đối soát:** đọc lại quyền hiệu lực; phân biệt kết quả gửi lệnh với trạng thái cuối.
6. **Kiểm toán:** lưu nguồn quyết định, người duyệt, thao tác, kết quả, ngoại lệ và thời gian.

### 3.1. Đầu vào của một yêu cầu grant/revoke

~~~yaml
requestId: ACCESS-2026-00482
subjectId: EMP-2104
resourceId: crm-production
entitlementId: tickets:update
operation: GRANT
reason: "Xử lý ticket nhóm hỗ trợ"
requestedBy: EMP-2104
businessOwner: EMP-0088
effectiveAt: "2026-11-23T09:00:00+07:00"
expiresAt: "2026-12-23T18:00:00+07:00"
sourceEventId: HR-2026-0211
~~~

Đây là **dữ liệu mẫu minh họa**, không phải schema SCIM hay chuẩn bắt buộc. Tùy loại quyền, bổ sung mức nhạy cảm, hệ thống đích, môi trường dev/test/prod, người phê duyệt, policy version và dấu vết phê duyệt. Với quyền tạm thời, thời điểm hết hạn phải thực sự dẫn tới **hành động thu hồi**, không chỉ là ghi chú.

| Trường | Mục đích kiểm soát |
| --- | --- |
| requestId / sourceEventId | Chống xử lý trùng và truy vết nguồn |
| subjectId | Gắn đúng người hoặc workload; tránh dựa vào email có thể đổi |
| resourceId / entitlementId | Biết chính xác quyền nào và phạm vi tài nguyên |
| operation | Phân biệt GRANT với REVOKE |
| reason / requestedBy / businessOwner | Giải trình mục đích và trách nhiệm |
| effectiveAt / expiresAt | Kiểm soát thời điểm bắt đầu và kết thúc |
| sourceVersion / policyVersion | Chống sự kiện cũ ghi đè chính sách mới |

## 4. Luồng cấp quyền: làm đúng ngay từ yêu cầu

### 4.1. Tiếp nhận và xác minh nhu cầu

Trước khi mở quyền:

1. Xác nhận chủ thể tồn tại, danh tính đã được kiểm chứng và quan hệ với tổ chức vẫn hợp lệ.
2. Chỉ rõ **hành động**, **tài nguyên**, **môi trường**, **phạm vi dữ liệu**, **mục đích**, **ngày bắt đầu** và **ngày hết hạn**.
3. Kiểm tra người dùng có những quyền nào, account nào đã tồn tại và liệu có request trùng hay không.
4. Xác định quản lý, sponsor hoặc owner phải đồng ý; nhà thầu cần thời hạn hợp đồng và người chịu trách nhiệm.
5. Tách trường hợp cấp trước ngày đi làm khỏi thời điểm được phép truy cập dữ liệu thật.

Ví dụ, yêu cầu “admin CRM” mơ hồ. Một yêu cầu rõ ràng hơn là “cập nhật ticket của nhóm Support trong dự án X từ ngày 01/12 đến ngày 31/12”, từ đó chính sách có thể gắn vai trò ít quyền hơn.

### 4.2. Tính quyền theo RBAC và ABAC

**RBAC** gán tập quyền qua role; **ABAC** xét thuộc tính chủ thể, tài nguyên, hành động và bối cảnh. Chúng có thể được kết hợp:

~~~text
role Support-Agent:
  allow tickets:read
  allow tickets:update

access condition:
  subject.employmentStatus == "active"
  AND subject.department == "Support"
  AND resource.environment == "production"
  AND device.trusted == true

temporary exception:
  entitlement = customers:export
  approvedBy = DataOwner
  expiresAt = request.expiresAt
~~~

Đoạn trên là **giả mã chính sách**, không phải cú pháp sản phẩm. ABAC chỉ bảo vệ được truy cập nếu thuộc tính cập nhật kịp thời và được app đánh giá lúc phù hợp. Không được suy ra HRIS đã đổi trạng thái thì mọi tài nguyên tự động chặn quyền.

**Các quy tắc thiết kế** gồm: đặc quyền tối thiểu (*least privilege*), chỉ truy cập dữ liệu cần biết (*need to know*), từ chối khi thiếu căn cứ (*default deny*), kiểm tra phân tách nhiệm vụ (*SoD*), phê duyệt độc lập với quyền nhạy cảm và tự kết thúc quyền tạm thời.

### 4.3. Phê duyệt đúng người, đúng rủi ro

| Loại yêu cầu | Chủ thể duyệt hoặc cơ chế quyết định | Kiểm soát |
| --- | --- | --- |
| Quyền cơ bản theo vị trí | Policy role đã được phê duyệt; xác minh thuộc tính nhân sự | Đúng vị trí, trạng thái và danh mục role |
| Dữ liệu nhạy cảm, xuất dữ liệu | Chủ dữ liệu/chủ ứng dụng | Mục đích, phạm vi, thời hạn và nhật ký |
| Quyền quản trị production | Chủ hệ thống và bên kiểm soát theo chính sách | MFA, SoD, thời hạn, theo dõi phiên |
| Nhà thầu/đối tác | Sponsor nội bộ và chủ tài nguyên | Hợp đồng, phạm vi, expiry |
| Truy cập khẩn cấp | Quy trình break-glass đã được ủy quyền | Ghi log, cảnh báo, rà soát sau sử dụng |

**Đã duyệt không có nghĩa đã cấp.** Trạng thái yêu cầu cần phân biệt quyết định phê duyệt, thời gian hiệu lực, thao tác ở hệ đích và kết quả xác minh. Người yêu cầu không mặc nhiên được tự phê duyệt quyền rủi ro cao.

### 4.4. Thực thi tại từng hệ đích

- **IdP:** tạo hoặc cập nhật identity, account, group, trạng thái, MFA theo chính sách.
- **SCIM/API:** provision user/group và entitlement ở SaaS hỗ trợ; lưu liên kết giữa subjectId và appUserId.
- **API chuyên biệt:** cấp cloud role, repository permission, database grant, chia sẻ tài nguyên khi ngoài phạm vi SCIM.
- **Thao tác thủ công:** tạo task cho app owner, ghi người nhận, thời hạn, kết quả và bằng chứng.
- **PAM/JIT:** với quyền quản trị, ưu tiên phiên hoặc quyền ngắn hạn thay vì mở đặc quyền thường trực nếu hệ thống hỗ trợ.

Không gộp mọi ứng dụng thành một thao tác “enable SSO”. SSO quyết định đường xác thực liên kết; một SaaS có thể lưu role và token riêng. Nếu app chưa có account, có thể cần provision trước khi SSO hoạt động; nếu app có account, vẫn phải xác minh role đã được cấp chính xác.

### 4.5. Xác minh sau cấp quyền

Workflow chỉ xem là hoàn tất khi có bằng chứng:

- User/account tại hệ đích khớp subject đã duyệt.
- Role, group và grant trực tiếp tạo ra **đúng quyền hiệu lực** cần có.
- Không xuất hiện đặc quyền ngoài yêu cầu hoặc xung đột SoD chưa giải quyết.
- MFA, điều kiện ABAC và thời điểm hiệu lực được thực thi đúng nơi cần thiết.
- Các quyền có hạn được theo dõi để tự thu hồi hoặc được áp dụng TTL phù hợp.
- App trả trạng thái xác minh; lỗi hoặc việc đang chờ đồng bộ được theo dõi.

**HTTP 200** từ connector có thể chỉ biểu thị yêu cầu đã nhận, nhất là với đồng bộ bất đồng bộ. Hãy đọc lại account/entitlement từ đích và chỉ ghi **COMPLETED** khi điều kiện kết thúc thực sự đạt.

## 5. Luồng thu hồi: từ mất lý do đến mất khả năng truy cập

Các nguyên nhân kích hoạt revoke:

| Nguồn | Ví dụ | Cần bảo đảm |
| --- | --- | --- |
| **Mover** | Người từ Support sang Finance | Gỡ quyền không còn hợp lệ; tránh tích lũy đặc quyền |
| **Leaver** | Nghỉ việc/kết thúc hợp đồng | Vô hiệu mọi đường truy cập gắn quan hệ đã chấm dứt |
| **Quyền hết hạn** | Quyền export tạm thời đã quá ngày | Hệ thống thực thi expiry; kiểm tra không còn quyền |
| **Access review** | Owner từ chối quyền đang có | Biến kết quả review thành revoke thực tế |
| **Sự cố bảo mật** | Credential bị lộ, nghi compromise | Chặn nhanh, revoke/rotate, giữ bằng chứng |
| **Thay đổi chính sách** | Role bị thu hẹp; phát hiện SoD | Đồng bộ quyền mục tiêu mới |
| **Ngừng workload** | Pipeline ngừng hoạt động | Thu hồi role, key, token và trust không còn cần |

### 5.1. Xác định phạm vi trước khi thu hồi

Revoke có thể nhằm vào **một permission**, **một role**, **một account**, **một phiên**, hoặc **mọi đường truy cập** của chủ thể. Một Mover thường chỉ bỏ quyền cũ, trong khi Leaver cần danh mục toàn bộ hệ đích và credential.

| Đối tượng | Cách thức xử lý có thể cần | Kiểm chứng |
| --- | --- | --- |
| Nhóm/vai trò IdP | Gỡ membership, cập nhật thuộc tính | Truy vấn membership và quyền hiệu lực |
| Role/ACL trong SaaS | Gỡ quyền trực tiếp, cập nhật group, disable account nếu thích hợp | Trạng thái account và entitlement |
| Token và khóa | Revoke PAT, API key, SSH key, certificate hoặc rotate secret đã lộ | Token/key không còn chấp nhận truy cập |
| Phiên đã mở | Revoke phiên/refresh token nếu app hỗ trợ; xét TTL | Trạng thái phiên và đường truy cập |
| Account local/phụ | Disable hoặc gỡ quyền theo phạm vi | Account không còn truy cập ngoài chính sách |
| VPN/thiết bị | Thu hồi quyền từ xa, chứng chỉ thiết bị theo chính sách | Đường truy cập liên quan bị chặn |
| Tài nguyên sở hữu | Bàn giao dashboard, repo, dữ liệu và automation | Owner mới xác nhận và dữ liệu được giữ đúng quy định |

Đặc biệt khi thu hồi do sự cố hoặc Leaver, **khóa IdP không bảo đảm ứng dụng tự thu hồi PAT/API key**. Cần kiểm kê đường đăng nhập ngoài SSO và truy vấn hệ thống đích.

### 5.2. Tính lại quyền mục tiêu và thứ tự thao tác

~~~text
actualBefore = {tickets:read, tickets:update, customers:export}
desiredAfterMover = {finance:reports:read}

revoke = {tickets:read, tickets:update, customers:export}
grant  = {finance:reports:read}
~~~

Nếu hai tập quyền xung đột SoD, cần lựa chọn thứ tự giảm rủi ro, có thể thu hồi quyền cũ trước khi cấp quyền mới. Nếu bàn giao đòi hỏi tạm giữ cả hai role, ngoại lệ phải có lý do, owner, giới hạn phạm vi và ngày hết hạn. Với Leaver khẩn cấp, thường ưu tiên **chặn truy cập mới và credential nguy hiểm ngay**, tiếp theo thu hồi các app còn lại và xác minh.

### 5.3. Thực thi revoke và kiểm chứng

~~~mermaid
sequenceDiagram
    participant SRC as HR / Review / Security
    participant IAM as Workflow IAM
    participant IDP as IdP
    participant APP as App / SaaS
    participant KEY as Token / Session / Key
    participant AUD as Audit / Owner
    SRC->>IAM: Sự kiện thu hồi đã xác minh
    IAM->>IAM: Tính quyền mục tiêu và grant paths
    IAM->>IDP: Disable/gỡ group nếu cần
    IAM->>APP: Revoke role/ACL hoặc disable account
    IAM->>KEY: Revoke/rotate credential, đóng phiên theo hỗ trợ
    IDP-->>IAM: Phản hồi
    APP-->>IAM: Phản hồi
    KEY-->>IAM: Phản hồi
    IAM->>APP: Đọc lại account và effective access
    IAM->>KEY: Xác minh đường truy cập độc lập
    IAM->>AUD: Bằng chứng và ngoại lệ còn mở
~~~

Điều kiện kết thúc **revoke**:

1. Xác định quyền mục tiêu theo chính sách và thời điểm.
2. Gỡ hoặc vô hiệu các đường grant không còn hợp lệ trong phạm vi, bao gồm quyền app trực tiếp và token độc lập.
3. Đọc lại trạng thái/entitlement thực tế; kiểm chứng session và credential theo khả năng hệ đích.
4. Quyền còn hiệu lực đều có căn cứ; ngoại lệ được quản lý với owner và hạn xử lý.
5. Lưu bằng chứng, thời gian và hệ đích. Không đánh dấu hoàn tất khi hệ quan trọng còn trạng thái không rõ hoặc thất bại.

**Thu hồi quyền không đồng nghĩa xóa dữ liệu.** Có thể phải giữ account inactive hoặc tài sản theo chính sách lưu giữ, bàn giao và yêu cầu pháp lý. Xóa vĩnh viễn là bước quản trị dữ liệu riêng.

## 6. Cấp và thu hồi trong Joiner–Mover–Leaver

| Nhánh JML | Điểm kích hoạt | Luồng cấp quyền | Luồng thu hồi quyền | Bằng chứng phải có |
| --- | --- | --- | --- | --- |
| **Joiner** | HR/sponsor xác minh người mới và ngày bắt đầu | Tạo identity, account, quyền cơ bản, MFA; đặc quyền chỉ khi duyệt | Gỡ quyền cấp nhầm hoặc quyền chuẩn bị không còn cần | Tài khoản đúng chủ thể, đúng vai trò, đúng mốc hiệu lực |
| **Mover** | Vai trò, bộ phận, dự án hoặc manager đổi | Cấp role/phạm vi mới hợp lệ | Gỡ nhóm, ACL, role và credential gắn nhiệm vụ cũ | Không có quyền cũ tồn dư; không vi phạm SoD |
| **Leaver** | Kết thúc quan hệ hoặc quyết định chấm dứt khẩn cấp | Thường không cấp thêm; có thể có workflow bàn giao riêng được kiểm soát | Khóa IdP/app, nhóm, token, key, phiên và đường truy cập độc lập | Trạng thái thực tế đã mất quyền, tài sản bàn giao, ngoại lệ được quản lý |

### 6.1. Joiner: cấp quyền trước và sau ngày bắt đầu

HR có thể gửi sự kiện trước ngày đi làm để IT chuẩn bị thiết bị và account. Workflow cần tách **tạo trước** khỏi **cho phép truy cập**: tài khoản có thể tồn tại trạng thái chưa kích hoạt, hoặc chỉ có một phạm vi pre-hire được phép. Khi đến ngày hiệu lực, xác minh điều kiện và bật đúng quyền đã duyệt.

Nếu nguồn hủy tiếp nhận trước ngày bắt đầu, phải có nhánh xử lý **hủy cấp phát**: loại bỏ hoặc disable account đã chuẩn bị, revoke credential thử nghiệm và xác minh không còn quyền được cấp sớm. Không để tài khoản Joiner bị hủy trở thành orphan account.

### 6.2. Mover: thu hồi là một nửa bắt buộc

Khi người từ Support chuyển sang Finance, workflow không chỉ thêm role Finance. Phải:

1. Đọc quyền hiệu lực hiện tại ở các hệ thống liên quan.
2. Tính quyền mục tiêu theo vai trò và thuộc tính mới.
3. Xác định quyền cũ phải thu hồi và quyền mới được cấp; kiểm tra SoD.
4. Lập kế hoạch chuyển đổi có ngày hiệu lực; quản lý ngoại lệ bàn giao có hạn.
5. Thực thi và đọc lại quyền trên từng app, bao gồm direct grant và phiên/token nếu liên quan.

Nếu quy trình chỉ cập nhật HRIS hoặc nhóm IdP mà không truy vấn quyền trực tiếp trong ứng dụng, không có cơ sở để khẳng định Mover đã dọn sạch quyền cũ.

### 6.3. Leaver: cắt đường truy cập và bàn giao có kiểm soát

Phân biệt **Leaver có kế hoạch** với **thu hồi khẩn cấp**. Trường hợp có lịch cần kích hoạt đúng thời điểm hiệu lực, có timezone rõ ràng. Trường hợp khẩn cấp cần hành động chặn theo mức độ rủi ro được quy trình ủy quyền và báo cáo ngay khi hệ đích chưa thể xác nhận.

Sau khi khóa đăng nhập liên kết, vẫn phải xem xét:

- Phiên đã phát hành bởi SaaS hoặc ứng dụng nội bộ.
- API key, PAT, SSH key, certificate, refresh token, VPN và credential thiết bị.
- Account local, account phụ, grant trực tiếp, cloud role, nhóm lồng nhau.
- Automation dùng token cá nhân; dashboard, workflow, repo và dữ liệu cần chuyển owner.
- Nghĩa vụ lưu giữ dữ liệu hoặc bảo quản chứng cứ mà không cần giữ tài khoản ở trạng thái truy cập được.

## 7. Vai trò của IdP, SSO, SCIM, RBAC/ABAC và IGA

| Thành phần | Hỗ trợ cấp quyền | Hỗ trợ thu hồi quyền | Giới hạn cần kiểm tra |
| --- | --- | --- | --- |
| **IdP** | Identity, trạng thái, group, MFA và chính sách đăng nhập | Disable danh tính, gỡ group, revoke phiên do IdP quản lý | Không mặc nhiên quản lý mọi credential và account app |
| **SSO (SAML/OIDC)** | Liên kết đăng nhập đến ứng dụng | Chặn những lần đăng nhập liên kết mới khi danh tính không hợp lệ | Phiên app và token cấp trước có thể còn hiệu lực |
| **SCIM** | Provision user/group, sửa thuộc tính/membership | Disable user hoặc gỡ membership theo app hỗ trợ | Không tự quyết định ai xứng đáng quyền nào và không mặc định kết thúc mọi phiên |
| **RBAC** | Gán quyền qua role | Gỡ role, tính lại entitlement | Role quá rộng và nhiều nguồn grant có thể gây thừa quyền |
| **ABAC** | Đánh giá thuộc tính subject/resource/context | Thay thuộc tính/policy để loại quyền theo điều kiện | Chỉ có hiệu quả nếu policy được thực thi và thuộc tính đúng, cập nhật kịp |
| **IGA / Access review** | Yêu cầu, phê duyệt, role catalog, SoD | Đánh giá quyền còn hợp lệ, phát hiện ngoại lệ | Không thay connector/API và bằng chứng đọc lại |
| **PAM / JIT** | Đặc quyền tạm thời, có thời hạn | Kết thúc role/credential/phiên đặc quyền | Phải kiểm tra phiên/credential thực tế ở đích |

### 7.1. Cách đọc một luồng SCIM

Ứng dụng có hỗ trợ SCIM thường có tài nguyên **User** và **Group**. Connector có thể tạo User, thêm membership hoặc thay trạng thái User, chẳng hạn chuyển thuộc tính **active** sang false khi Leaver. Tuy nhiên, ứng dụng quyết định semantics của thuộc tính, quyền gắn Group, xử lý session và dữ liệu.

Vì vậy một workflow cần ghi **hợp đồng tích hợp theo từng ứng dụng**:

1. User ở IdP ánh xạ tới User ở app bằng ID nào?
2. App hỗ trợ create, update, disable, delete và group membership tới mức nào?
3. Thao tác nào xử lý quyền trực tiếp, API token, session hoặc tài khoản local?
4. Làm sao đọc lại trạng thái thật của User, role và entitlement?
5. Nếu đồng bộ bất đồng bộ, khi nào kết quả có thể được xem là xác minh?
6. Ai nhận cảnh báo và thao tác thủ công nếu connector không hoạt động?

**Không mặc định xóa tài khoản vĩnh viễn khi Leaver.** Nhiều ứng dụng cần disable để giữ lịch sử thao tác và dữ liệu theo chính sách. Khả năng đăng nhập và lưu giữ dữ liệu cần điều khiển riêng.

### 7.2. Quyền nâng cao theo yêu cầu (Just-in-Time)

Một role production admin thường trực tạo rủi ro lớn. Luồng JIT mẫu:

~~~mermaid
flowchart LR
    REQ["Yêu cầu đặc quyền + lý do + thời hạn"] --> CHECK["Xác minh identity, MFA, SoD"]
    CHECK --> APPROVE["Phê duyệt theo chính sách"]
    APPROVE --> ENABLE["Kích hoạt quyền đúng phạm vi"]
    ENABLE --> USE["Thực hiện công việc có log"]
    USE --> EXPIRE["Hết hạn hoặc thu hồi sớm"]
    EXPIRE --> VERIFY["Đọc lại quyền/phiên và kiểm toán"]
~~~

Nếu nền tảng hỗ trợ credential ngắn hạn, có thể ưu tiên thay secret tĩnh. Tuy nhiên phải xác minh điều gì xảy ra với **phiên đang chạy** và credential đã phát hành sau thời hạn; chỉ gỡ group chưa chắc dừng ngay những phiên đó.

## 8. Quyền tồn dư và phương pháp đối soát

**Residual access** là đường truy cập còn tồn tại sau khi lý do nghiệp vụ đã mất. Đây là dấu hiệu quan trọng đánh giá chất lượng luồng thu hồi.

| Vấn đề | Vì sao xuất hiện? | Hành động kiểm soát |
| --- | --- | --- |
| Quyền cấp qua nhiều nhóm | Gỡ một nhóm, nhóm khác vẫn cấp entitlement | Tính quyền hiệu lực và toàn bộ nguồn grant |
| Direct grant trong app | Workflow chỉ biết nhóm IdP | Kiểm kê ACL và role trong từng app |
| Session/token còn hiệu lực | App không kiểm tra lại IdP mỗi yêu cầu | Revoke nếu hỗ trợ; quản lý TTL, kiểm thử và xác minh |
| Token cá nhân trong automation | Đã khóa nhân viên nhưng pipeline vẫn dùng PAT | Chuyển sang workload identity, revoke PAT, kiểm tra workflow |
| Account local hoặc phụ | Tài khoản tạo ngoài provisioning | Đối soát hệ đích với nguồn danh tính |
| ABAC sử dụng thuộc tính cũ | Sự kiện Mover không cập nhật kịp tại app | Kiểm tra độ mới dữ liệu và điểm thực thi policy |
| Quyền tạm thời quá hạn | Không có trigger revoke hoặc connector lỗi | Expiry tự động, cảnh báo và xử lý ngoại lệ |
| Job cấp cũ chạy lại | Retry sau sự kiện Leaver mới hơn | Chặn grant dựa vào version/trạng thái nguồn |
| Service account vô chủ | Người phụ trách nghỉ, không chuyển owner | Quy định sponsor, review và rotation |

### 8.1. Đối soát hai chiều

**Nguồn danh tính/quyền → hệ đích:** một chủ thể hợp lệ theo HRIS và chính sách có thực sự nhận đúng các entitlement được duyệt không? Luồng này phát hiện thiếu cấp phát và thu hồi chưa chạy.

**Hệ đích → nguồn danh tính/quyền:** mỗi account, ACL, key và role đang tồn tại có thuộc về một chủ thể hoặc workload hợp lệ, có owner và lý do hay không? Luồng ngược phát hiện orphan account và grant thủ công nằm ngoài IGA.

Nếu app không hỗ trợ API truy vấn entitlement, cần có **bước đối chiếu thủ công có người xác nhận và bằng chứng**, đồng thời ghi rõ giới hạn của phương pháp. Chỉ có log “đã gửi lệnh” là chưa đủ.

### 8.2. Phân biệt quyền tồn dư với ngoại lệ được phê duyệt

Một ngoại lệ cho phép giữ quyền tạm thời khi bàn giao có thể hợp lệ nếu có **owner, mục đích, giới hạn, người phê duyệt và ngày hết hạn**. Khi quá hạn mà vẫn truy cập được, nó trở thành sai lệch phải xử lý. Báo cáo cần phân biệt ngoại lệ còn hạn, ngoại lệ quá hạn và quyền không có chủ sở hữu; không gộp mọi trường hợp thành “đã chấp thuận”.

## 9. Tài khoản dịch vụ và danh tính workload

Danh tính không phải con người như **service account, service principal, bot, CI/CD identity, workload federation** cũng cần vòng đời cấp/thu hồi quyền, nhưng nguồn sự kiện thường là tạo, sửa hoặc ngừng workload.

| Giai đoạn | Cần quản lý |
| --- | --- |
| **Tạo workload** | Tên dịch vụ, owner, môi trường, mục đích, thời hạn, quyền tối thiểu |
| **Cấp quyền** | Cloud role, repository, API scope theo đúng một workload/môi trường; ưu tiên identity ngắn hạn nếu khả thi |
| **Đổi nhiệm vụ** | So quyền cũ và mục tiêu, gỡ grant dự án không còn dùng |
| **Đổi owner** | Chuyển trách nhiệm, kiểm tra secret/trust, bỏ token cá nhân trong automation |
| **Ngừng workload** | Revoke role, key, secret, certificate, trust relationship và tài khoản không còn dùng |

Ví dụ pipeline CI của dự án A từng được cấp quyền deploy lên cluster production A. Khi chuyển sang dự án B, workflow cần gỡ role A, cấp role B được duyệt và kiểm tra effective access của service principal; không nên giữ cả hai quyền vô hạn. Nếu người tạo pipeline nghỉ việc, trước khi thu hồi PAT cá nhân cần xác định đường chuyển sang service identity có owner để hệ thống vẫn hoạt động theo chính sách, đồng thời xử lý khẩn cấp phù hợp nếu token có nguy cơ bị lộ.

Với **break-glass account**, lưu chủ sở hữu, điều kiện sử dụng, biện pháp bảo vệ credential, cảnh báo và hoạt động hậu kiểm. Đây là ngoại lệ có quản trị riêng, không phải một đường cấp quyền để bỏ qua Leaver.

## 10. Xử lý trạng thái phân tán và sự kiện đến sai thứ tự

IAM có thể phải thay đổi nhiều hệ thống không nằm trong cùng một giao dịch. Kết quả có thể là **IdP đã gỡ group, CRM chưa cập nhật, token vẫn còn hiệu lực**. Điều phối phải giữ trạng thái theo từng hệ đích.

| Trạng thái workflow minh họa | Ý nghĩa |
| --- | --- |
| **PENDING_APPROVAL** | Đang chờ quyết định hợp lệ |
| **APPROVED** | Đã duyệt, chưa chứng minh đã cấp |
| **IN_PROGRESS** | Đang thực thi trên các hệ đích |
| **PENDING_VERIFICATION** | Chờ đọc lại trạng thái thực tế |
| **PARTIAL** | Một phần thành công, phần khác chưa hoàn tất |
| **FAILED** | Lỗi cần escalated hoặc xử lý thủ công |
| **COMPLETED** | Thỏa điều kiện xác minh và lưu bằng chứng |
| **REJECTED** | Không đáp ứng yêu cầu/chính sách |

Tên trạng thái do mỗi tổ chức quyết định; quan trọng là **không đánh đồng “đã được duyệt” hoặc “đã gửi” với “đã xác minh”**.

### 10.1. Các cơ chế tránh sai lệch

1. **Idempotency:** xử lý lại cùng requestId/eventId không tạo thêm role hoặc account trùng.
2. **Kiểm tra phiên bản:** lưu sourceVersion, policyVersion và thời điểm hiệu lực; không cho sự kiện cũ ghi đè trạng thái mới.
3. **Chặn cấp khi chủ thể không còn hợp lệ:** kiểm tra lại trạng thái nguồn trước grant hoặc retry.
4. **Retry có giới hạn:** xử lý lỗi timeout, rate limit với backoff; chuyển cho owner khi lỗi mapping, thiếu quyền API hoặc cần xử lý thủ công.
5. **Theo dõi từng target:** CRM=VERIFIED, Billing=FAILED, IdP=VERIFIED phải được tổng hợp thành trạng thái chưa hoàn tất.
6. **Đối soát định kỳ:** phát hiện grant thủ công, event thất lạc và drift ngay cả khi webhook hoạt động.
7. **Bảo vệ automation:** connector được cấp quyền tối thiểu, credential quản lý an toàn, log không lộ secret hoặc PII không cần thiết.

### 10.2. Race condition nguy hiểm: Mover chạy lại sau Leaver

~~~text
09:00  HR phát MOVER v17: Support -> Finance
09:01  Job grant Finance bị timeout và được xếp hàng retry
09:02  HR phát LEAVER v18: chấm dứt có hiệu lực ngay
09:03  Workflow LEAVER disable account và gỡ các quyền cũ
09:04  Job grant Finance v17 chạy lại
~~~

**Nếu cấp theo job cũ:** quyền Finance có thể được bật lại cho một danh tính đã rời tổ chức.

**Cách xử lý:** trước khi grant, đối chiếu phiên bản và trạng thái mới nhất của nguồn. Khi Leaver v18 đã có hiệu lực, bỏ qua Mover v17 hoặc tính lại quyền theo trạng thái v18; ghi dấu vết quyết định và chạy đối soát. Điều phối tuần tự theo subjectId có thể giảm cạnh tranh nhưng không thay thế kiểm tra phiên bản khi retry.

### 10.3. Khi app không phản hồi lúc cần revoke

Nếu Leaver khẩn cấp nhưng một SaaS offline: giữ workflow ở trạng thái **PARTIAL/FAILED**, thông báo owner và đội phụ trách rủi ro theo quy trình, thực hiện các biện pháp chặn đang khả dụng và tiếp tục kiểm tra khi app trở lại. Chỉ khi đọc lại được trạng thái hoặc có bằng chứng thay thế phù hợp mới coi phần đó đã hoàn tất. Không suy đoán toàn bộ credential đã mất hiệu lực chỉ vì IdP bị khóa.

## 11. Tình huống xuyên suốt: quyền xuất báo cáo của nhân viên

Một tổ chức có HRIS, IdP, CRM đăng nhập bằng OIDC và nhận SCIM, hệ báo cáo dùng role riêng, kho mã có PAT. **Mai**, mã EMP-2104, trải qua ba giai đoạn.

### 11.1. Joiner và quyền được phê duyệt

HR xác minh Mai bắt đầu ở bộ phận Support. IAM tính quyền **tickets:read** và **tickets:update**. Quyền **reports:export** không có trong role cơ bản. Quản lý đề xuất quyền export trong hai tuần cho một báo cáo; chủ dữ liệu phê duyệt có thời hạn.

Workflow tạo account CRM, cấp role Support, mở ngoại lệ export, áp dụng MFA và đọc lại quyền thực tế. Khi hết hai tuần, hệ thống phải thu hồi quyền export dù Mai vẫn thuộc Support.

### 11.2. Mover và direct grant còn tồn dư

Mai chuyển sang Finance. Quyền mới chỉ cần **finance:reports:read**, trong khi quyền sửa ticket và export không còn lý do. IAM gỡ nhóm Support, cấp Finance-Viewer. Tuy nhiên, khi đọc lại CRM, direct grant **reports:export** còn tồn tại. Mover vì vậy vẫn ở trạng thái **PARTIAL**; phải gỡ grant trực tiếp và xác minh.

~~~text
Before:
  CRM: tickets:read, tickets:update, reports:export
  Finance: (none)

Desired after move:
  CRM: (none)
  Finance: finance:reports:read

Actions:
  revoke CRM tickets:read
  revoke CRM tickets:update
  revoke CRM reports:export (bao gồm direct grant)
  grant Finance finance:reports:read
~~~

### 11.3. Leaver và token cá nhân

Mai nghỉ việc. IdP bị khóa đúng mốc hiệu lực, CRM nhận lệnh SCIM, Finance gỡ role, repo gỡ membership. Một pipeline vẫn dùng PAT cá nhân của Mai; đây là đường truy cập còn tồn dư. Chủ hệ thống cần chuyển automation sang workload identity được cấp quyền hợp lệ, revoke PAT cũ, kiểm tra pipeline và lưu bằng chứng. Nếu PAT đã bị nghi lộ, biện pháp chặn khẩn cấp phải được ưu tiên theo mức độ rủi ro.

| Hệ thống | Trạng thái mong muốn sau Leaver | Cách kiểm chứng |
| --- | --- | --- |
| IdP | Không tạo đăng nhập mới được; phiên thuộc phạm vi đã xử lý | Trạng thái inactive và log |
| CRM | Không còn tài khoản/quyền truy cập hợp lệ | Readback account và entitlement |
| Finance | Role không còn hiệu lực | Danh sách quyền thực tế |
| Repository | Membership và PAT cá nhân bị revoke | Token status, membership, kết quả kiểm thử phù hợp |
| Pipeline | Có owner mới và credential workload đúng quyền | Xác nhận từ owner, log job, không còn PAT cũ |

## 12. Kiểm toán và đo chất lượng luồng

Một bản ghi bằng chứng có thể gồm:

| Trường | Vì sao cần? |
| --- | --- |
| requestId, eventId, subjectId | Truy vết yêu cầu, chủ thể và sự kiện |
| source, sourceVersion, effectiveAt | Chứng minh nguồn và mốc hiệu lực |
| resourceId, entitlementId, operation | Xác định quyền thay đổi |
| policyVersion, approvedBy, reason | Truy lại căn cứ quyết định |
| desiredBefore, desiredAfter | Biết quyền mục tiêu là gì |
| connectorResult, targetAccountId | Gắn lệnh với hệ thống đích |
| actualAfter, verifiedAt | Chứng minh quyền thực tế và thời gian |
| expiresAt, exceptionOwner, resolutionAt | Theo dõi thời hạn và ngoại lệ |

Không ghi mật khẩu, private key, access token hoặc dữ liệu cá nhân không cần thiết vào log; giới hạn người được xem và thời hạn lưu phù hợp chính sách.

### 12.1. Các chỉ số có ý nghĩa

| Chỉ số | Cách đánh giá |
| --- | --- |
| **Grant turnaround** | Từ khi yêu cầu hợp lệ/được duyệt đến khi quyền thực tế sẵn sàng |
| **Grant correctness** | Tỷ lệ entitlement thực tế khớp phê duyệt, không thiếu hoặc thừa |
| **Revoke latency** | Từ mốc cần thu hồi đến khi hệ đích cuối cùng xác minh mất quyền |
| **Overdue temporary access** | Quyền tạm thời còn hiệu lực sau ngày hết hạn |
| **Orphan/direct grants** | Account/grant không liên kết được với chủ thể hoặc owner hợp lệ |
| **Review remediation** | Quyền bị từ chối trong review đã thực sự bị thu hồi |
| **Partial/failed workflow** | Bao nhiêu workflow còn target lỗi hoặc chưa xác minh |
| **Reconciliation drift** | Số trường hợp quyền thực tế lệch quyền mục tiêu |

Ngưỡng SLA nên phụ thuộc phân loại rủi ro, hệ thống, thời điểm và yêu cầu tổ chức. Không nên báo cáo “thu hồi nhanh” chỉ vì đã disable IdP, trong khi app hoặc token chưa được xác minh.

## 13. Bài tập tự kiểm tra

### 13.1. Bài tập 1 — Một quyền có hai nguồn

Một nhân viên có **orders:export** nhờ nhóm Order-Analyst và direct grant tại app. Mover đã gỡ nhóm, nhưng quyền export vẫn hoạt động. **Yêu cầu:** giải thích nguyên nhân và cách kết thúc revoke.

**Gợi ý:** direct grant vẫn cấp quyền; truy vấn toàn bộ grant paths, gỡ phần thừa, kiểm tra token/phiên nếu liên quan, đọc lại effective access và lưu bằng chứng. Xóa một group chưa hoàn tất revoke.

### 13.2. Bài tập 2 — Quyền production admin quá hạn

Role production admin được phê duyệt bốn giờ nhưng sau hai ngày vẫn xuất hiện. **Yêu cầu:** thiết kế ngăn ngừa và khắc phục.

**Gợi ý:** dùng expiry có cơ chế thực thi (JIT/TTL hoặc trigger revoke), cảnh báo quá hạn, owner xử lý và đối soát. Nếu có phiên đặc quyền còn mở, kiểm tra cách chấm dứt phiên theo khả năng nền tảng. Sau khắc phục, lưu bằng chứng và rà soát nguyên nhân.

### 13.3. Bài tập 3 — SSO đã khóa, app vẫn truy cập được

IdP disable người dùng Leaver, nhưng app vẫn chấp nhận local password và API key. **Yêu cầu:** nêu phần SSO/SCIM không xử lý được và bước cần bổ sung.

**Gợi ý:** phải disable account app, revoke API key, xử lý phiên, chặn đường đăng nhập local theo chính sách, kiểm tra ở hệ đích và ghi lại kết quả. SCIM chỉ giúp phần nào mà app hỗ trợ, không mặc định thu hồi toàn bộ credential.

### 13.4. Bài tập 4 — Job grant đến muộn

Mover v9 yêu cầu grant role mới và đang retry; Leaver v10 đã xử lý thành công trước đó. **Yêu cầu:** đưa ra điều kiện để không cấp lại quyền.

**Gợi ý:** xác minh sourceVersion và trạng thái hiện tại trước grant; bỏ event v9 khi v10 đã có hiệu lực, giữ tính idempotent, đối soát các quyền ở hệ đích sau xử lý.

### 13.5. Bài tập 5 — Lập bản đồ grant/revoke cho một SaaS

Chọn một ứng dụng và điền bảng:

| Cần xác định | Câu hỏi |
| --- | --- |
| Nguồn | Ai xác nhận Joiner/Mover/Leaver và hết hạn? |
| Owner | Ai duyệt, ai bảo trì role catalog, ai xử lý lỗi? |
| Đường cấp | Nhóm, role, ACL, token và local account gồm những gì? |
| Thực thi | SCIM, API hay manual task thực hiện thế nào? |
| Thu hồi | Làm sao gỡ từng đường grant và ngăn cấp lại? |
| Readback | Có thể truy vấn effective access và trạng thái app không? |
| Ngoại lệ | App offline, thiếu API, thiếu owner xử lý thế nào? |
| Bằng chứng | Quyết định, lệnh và kết quả được lưu ở đâu? |

Một thiết kế đầy đủ phải trả lời được **“quyền hiện có đến từ đâu?”** và **“muốn chặn quyền ngay, phải tác động vào những đường nào và xác minh bằng gì?”**

## 14. Ghi nhớ

**Cấp quyền đúng** bắt đầu từ danh tính hợp lệ, nhu cầu cụ thể và quyền tối thiểu được phê duyệt; tiếp tục bằng thao tác ở đúng hệ đích và kết thúc bằng **đọc lại quyền thực tế**. **Thu hồi đúng** phải tìm tất cả đường grant, xử lý role, ACL, account, phiên và token liên quan, đối soát và lưu bằng chứng.

Trong IAM lifecycle, **Joiner** tạo quyền cơ bản, **Mover** vừa thu hồi vừa cấp quyền theo trách nhiệm mới, còn **Leaver** loại bỏ các đường truy cập không còn hợp lệ. IdP/SSO hỗ trợ định danh và xác thực; SCIM/API hỗ trợ provision; RBAC/ABAC quyết định phạm vi; IGA và kiểm toán quản trị, chứng minh kết quả. Điểm kết thúc đáng tin của mỗi workflow là **quyền đã đúng tại hệ thống thực thi và có bằng chứng kiểm chứng được**.
