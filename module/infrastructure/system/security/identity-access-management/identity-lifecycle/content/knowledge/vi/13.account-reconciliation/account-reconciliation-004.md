# Phát hiện account thừa trong Account Reconciliation

## 1. Khái niệm và mục tiêu

Trong **Identity and Access Management (IAM)**, **account reconciliation** là quá trình đối chiếu tài khoản và quyền hiện có ở các hệ thống đích với trạng thái danh tính, quan hệ công việc và quyền **đáng lẽ phải có** theo chính sách. **Phát hiện account thừa** là nhận diện những account không có căn cứ hợp lệ để tiếp tục tồn tại hoặc tiếp tục truy cập trong phạm vi được quản lý.

Ví dụ, nhân viên A đã nghỉ việc và bị khóa tại Identity Provider (IdP), nhưng một ứng dụng kế toán legacy vẫn có local account hoạt động của A. Nếu tài khoản đó không còn được bảo trợ bởi quan hệ hợp lệ và vẫn có thể đăng nhập, đây là ứng viên account thừa có rủi ro cao. Nhưng không phải mọi account không xuất hiện trong HRIS đều thừa: tài khoản dịch vụ và tài khoản khẩn cấp có thể hợp lệ nếu có nguồn bảo trợ, owner và kiểm soát phù hợp.

Bài học thuộc chương **Account reconciliation** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Quy trình kết nối mô hình **Joiner–Mover–Leaver (JML)**, xác minh và ghi danh danh tính, cấp/thu hồi quyền, **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**.

### Các đối tượng cần phân biệt

| Khái niệm | Dấu hiệu | Kết luận sơ bộ |
|---|---|---|
| **Expected account** | Có danh tính/owner, mục đích, quyền và quan hệ hợp lệ | Không thừa |
| **Orphan account** | Không tìm được owner, danh tính hoặc quan hệ bảo trợ đáng tin | Nghi vấn cao, phải xác minh |
| **Unauthorized account** | Được tạo ngoài phê duyệt hoặc chính sách | Cần điều tra/thu hồi theo rủi ro |
| **Residual account** | Vẫn còn sau sự kiện yêu cầu deprovision | Có thể là quyền truy cập tồn dư |
| **Duplicate account** | Có nhiều tài khoản cùng mục đích ngoài thiết kế | Một hoặc nhiều tài khoản có thể thừa |
| **Dormant/stale account** | Lâu không có hoạt động được quan sát | Là tín hiệu, **không tự chứng minh thừa** |
| **Disabled/retained account** | Đã bị khóa, còn bản ghi do lưu giữ hoặc kiểm toán | Có thể hợp lệ nếu không còn đường truy cập |
| **Service/device/break-glass account** | Principal kỹ thuật hoặc ngoại lệ hợp lệ | Cần nguồn mong muốn riêng, không chỉ HRIS |
| **Excess entitlement** | Account hợp lệ nhưng có group/role/quyền dư | Thừa quyền, chưa chắc thừa toàn account |

**Điểm mấu chốt:** “không nằm trong HRIS”, “90 ngày không đăng nhập” và “có tài khoản trùng tên” đều **không đủ cơ sở để tự động xóa**. Cần xác định đúng phạm vi, đối tượng, rủi ro và khả năng truy cập thực tế.

## 2. Bài toán Desired state và Observed state

**Desired state** là tài khoản và quyền **đáng có** theo nguồn có thẩm quyền, quan hệ JML, RBAC/ABAC, phê duyệt, ngoại lệ và thời hạn. **Observed state** là tài khoản, quyền và trạng thái **đọc được từ hệ thống đích** như SaaS, directory, cloud hoặc local server.

Gọi:

- \(D\) là tập tài khoản đáng có tại hệ thống đích.
- \(O\) là tập tài khoản quan sát được tại hệ thống đích.
- \(O \setminus D\) là ứng viên account thừa.
- \(D \setminus O\) là account đáng có nhưng chưa được provision.
- \(O \cap D\) là account nằm trong hai tập, **vẫn cần đối soát quyền và trạng thái**.

Phép so sánh chỉ đáng tin khi record đã được ánh xạ bằng **khóa định danh ổn định**. Nếu dùng email hoặc tên hiển thị làm khóa duy nhất, kết quả có thể sai khi tài khoản đổi tên hoặc địa chỉ được tái sử dụng.

### Ví dụ đơn giản

| Hệ thống | Account | Có căn cứ trong desired state? | Trạng thái thực tế | Kết luận ban đầu |
|---|---|---|---|---|
| ERP | erp-a104 | Có | Active, đúng nhóm | Hợp lệ |
| ERP | erp-b278 | Không | Active | Ứng viên account thừa |
| CRM | crm-c611 | Có | Disabled dù cần active | Thiếu provisioning, không phải thừa |
| CRM | crm-d002 | Không | Disabled, giữ theo retention | Kiểm tra lưu giữ hợp lệ |
| Cloud | svc-data-sync | Không có trong HRIS | Active, có service owner | Có thể là machine identity hợp lệ |
| Directory | admin-emergency-01 | Không có trong HRIS | Active theo cơ chế break-glass | Cần kiểm soát riêng, không tự xóa |

Có thể tồn tại một account hoàn toàn hợp lệ nhưng **quyền cấp trực tiếp hoặc vai trò kế thừa của nó đã vượt desired state**. Vì vậy, cần tách **account reconciliation** khỏi **entitlement reconciliation**.

## 3. Nguồn dữ liệu cho reconciliation

Để kết luận account thừa, cần **nguồn trạng thái mong muốn đáng tin** và **nguồn trạng thái quan sát ở đích**. Với môi trường nhiều hệ thống, không nguồn nào một mình đầy đủ.

| Nguồn | Dữ liệu cung cấp | Giới hạn |
|---|---|---|
| **HRIS** | Mã người, quan hệ lao động, Joiner/Mover/Leaver, ngày hiệu lực | Không bao phủ toàn bộ nhà thầu hoặc bot |
| **Contract/vendor management** | Nhà thầu, đối tác, người bảo trợ, thời hạn | Có thể cập nhật chậm hoặc nhiều quan hệ |
| **IAM/IGA** | Identity ID, account mapping, policy, phê duyệt, ngoại lệ | Chính sách và dữ liệu đồng bộ có thể chưa hoàn chỉnh |
| **IdP/AD/LDAP** | User, computer account, trạng thái đăng nhập, nhóm | Không thấy hết local account, session hoặc API key độc lập |
| **SCIM/API của SaaS** | User/Group, trạng thái và một số entitlement | SCIM không chuẩn hóa mọi quyền hoặc cơ chế thu hồi phiên |
| **Cloud IAM/PAM** | Principal, role, access key, tài khoản đặc quyền | Có quyền gián tiếp qua policy/federation |
| **CMDB/service registry** | Owner workload/device/service, vòng đời tài sản | Owner có thể đã nghỉ hoặc metadata lỗi thời |
| **Logs/telemetry** | Bằng chứng xác thực và hoạt động | Vắng log không chứng minh không thể truy cập |
| **Exception registry** | Quyền đặc biệt, break-glass, lưu giữ, thời hạn duyệt | Ngoại lệ hết hạn phải rà soát lại |

### Kiểm tra chất lượng nguồn

1. **Scope:** hệ thống, tenant, region, OU, loại account và môi trường nào được đối soát?
2. **Completeness:** API có trả đủ phân trang, không bị lọc hoặc rate limit làm thiếu account không?
3. **Freshness:** thời gian snapshot mong muốn và thực tế có đủ gần nhau? Có eventual consistency?
4. **Authority:** nguồn nào có thẩm quyền cho nhân viên, nhà thầu, thiết bị, workload và emergency account?
5. **Coverage:** connector có thấy được account local, group, direct grant, token và quyền độc lập với SSO?
6. **Mapping:** khóa định danh nào dùng để nối; có lịch sử đổi tên, email, rehire và chuyển hệ thống không?
7. **Evidence:** có lưu thời gian thu thập, phiên bản connector, lỗi và khoảng trống dữ liệu không?

**Snapshot thiếu phân trang hoặc đọc sai tenant có thể tạo hàng loạt false positive.** Chưa xác minh độ phủ dữ liệu thì chưa nên thực hiện thu hồi hàng loạt.

## 4. Phân loại account thừa và các tín hiệu liên quan

### 4.1. Account mồ côi (orphan)

Tài khoản không liên kết được với danh tính, workload, owner hoặc quan hệ bảo trợ còn hiệu lực. Ví dụ một local admin tồn tại trên máy chủ từ dự án cũ mà không có ticket hay chủ sở hữu. Rủi ro thường cao, nhưng cần kiểm tra khả năng đó là tài khoản khẩn cấp hợp lệ chưa được đưa vào inventory.

### 4.2. Account của Leaver còn truy cập

Người đã kết thúc quan hệ làm việc nhưng local account, cloud principal, token hoặc phiên ở ứng dụng vẫn hoạt động. Đặc biệt nguy hiểm nếu tài khoản còn quyền quản trị, VPN hoặc truy cập dữ liệu nhạy cảm. Cần xác minh có quan hệ hợp lệ khác và cơ chế chặn thực tế, không suy từ cờ disabled của IdP.

### 4.3. Account trùng (duplicate) và shadow account

Do retry không idempotent, tạo account thủ công, thay email hoặc di trú hệ thống, một người có thể có nhiều account ngoài thiết kế. Phải xác minh **target ID và tài nguyên thuộc account** trước khi hợp nhất hoặc khóa. Một tài khoản admin tách biệt có thể được duy trì hợp lệ theo phân tách đặc quyền.

### 4.4. Account lâu không hoạt động (dormant)

Không thấy đăng nhập trong thời gian theo dõi là tín hiệu cần rà soát. Tuy nhiên account break-glass, batch chỉ chạy theo quý, workload dùng chứng chỉ hoặc hệ thống thiếu log có thể khiến chỉ báo này sai. Cần kết hợp mục đích, owner, credential, lifecycle và thời gian đánh giá.

### 4.5. Account ngoài quy trình IAM

Một user được tạo trực tiếp trên SaaS hoặc cloud mà không qua IGA và không có ticket. Cần kiểm tra authorization và nhu cầu hiện tại. Nếu hợp lệ, nên đưa vào quản lý; nếu không hợp lệ, cần thu hồi và kiểm chứng.

### 4.6. Account vô hiệu nhưng còn bản ghi

Một user đã disabled có thể cần được giữ theo lưu trữ dữ liệu, kiểm toán hoặc yêu cầu pháp lý. **Tồn tại object không có nghĩa account còn truy cập**. Phải kiểm tra được trạng thái đăng nhập, session/token và đường xác thực độc lập; đồng thời kiểm tra hạn retention.

## 5. Identity mapping: nối đúng account với chủ thể

Một hệ thống IAM có thể quản lý những khóa sau:

- **personId/subjectId:** định danh bền vững từ nguồn có thẩm quyền.
- **relationshipId:** mối quan hệ nhân viên/nhà thầu cụ thể.
- **identityId:** bản ghi định danh trong IAM/IGA.
- **targetAccountId:** ID bền vững của tài khoản tại hệ thống đích.
- **externalId** hoặc khóa liên kết do provisioning quản lý.
- **workloadId/assetId:** định danh dịch vụ hoặc thiết bị phi con người.

**Không tự động map account chỉ vì username hoặc email giống nhau.** Email có thể được tái sử dụng, đổi tên hoặc trỏ tới hộp thư dùng chung; tên hiển thị có thể trùng giữa hai người.

### Quy tắc liên kết

1. Ưu tiên targetAccountId đã được liên kết đáng tin với identityId.
2. Với account thiếu mapping, kiểm tra nguồn, owner, lịch sử provisioning, ID nội bộ và bằng chứng hoạt động trước khi nối.
3. Không tự hợp nhất hai account nếu chưa biết dữ liệu, quyền và phiên của từng account.
4. Phân biệt một người có **nhiều account hợp lệ** và nhiều account ngoài thiết kế.
5. Với rehire, liên kết lịch sử danh tính nhưng không khôi phục quyền của quan hệ cũ.
6. Với service account, dùng workload registry và owner kỹ thuật, không ép gắn với một HR personId như account nhân viên.

### Ví dụ email được tái sử dụng

Nhân viên A nghỉ việc, email support@example.org sau đó được chuyển cho B. Nếu account CRM cũ của A cũng dùng địa chỉ này và reconciliation nối chỉ bằng email, hệ thống có thể coi account cũ hợp lệ của B. Hậu quả là bỏ sót quyền tồn dư. Cần dùng liên kết target ID, source identity, relationship và lịch sử provisioning.

## 6. Quy trình phát hiện account thừa

~~~mermaid
flowchart TD
    H[HRIS / hợp đồng] --> D[Desired identities + accounts]
    R[RBAC / ABAC / phê duyệt / ngoại lệ] --> D
    W[Service / device / break-glass registry] --> D
    I[IdP / Directory] --> O[Observed accounts + rights]
    A[SaaS / SCIM / local accounts] --> O
    C[Cloud IAM / PAM] --> O
    D --> M[Chuẩn hóa và liên kết ID]
    O --> M
    M --> X[So sánh desired - observed]
    X --> Q{Có sai lệch?}
    Q -->|Không| P[Ghi kết quả và coverage]
    Q -->|Có| F[Finding + risk + evidence]
    F --> T[Điều tra và quyết định]
    T --> Z[Thu hồi / chuyển owner / sửa mapping / ngoại lệ]
    Z --> V[Readback tại đích]
    V --> Q
~~~

### Bước 1 — Định nghĩa scope

Chọn tenant, ứng dụng, principal type, dữ liệu cần kiểm tra và những trường hợp ngoại lệ. Nêu rõ account, trạng thái, entitlement, credential và phiên nào có thể quan sát được.

### Bước 2 — Tính desired state

Dùng nguồn có thẩm quyền cùng chính sách RBAC/ABAC, hợp đồng, phê duyệt, vòng đời JML và registry tài khoản đặc biệt để xác định mỗi account **phải tồn tại hay không, có được active không, và được cấp quyền nào**.

### Bước 3 — Lấy observed state

Quét tài khoản ở IdP, directory, ứng dụng, cloud, PAM và các đường local. Lưu target ID, account type, trạng thái, nhóm/quyền, snapshot time và thông tin về độ phủ; không chỉ lấy dữ liệu từ IAM database.

### Bước 4 — Chuẩn hóa và đối chiếu

Chuẩn hóa ID, trạng thái, kiểu tài khoản và thời gian. Nếu chưa chứng minh được mapping, tạo finding **UNMATCHED/NEEDS_REVIEW** thay vì tự gán owner hay tự xóa.

### Bước 5 — Tạo finding

Tách rõ unexpected active, unexpected disabled, potential duplicate, unknown owner, stale credential, excess entitlement và disabled account có retention. Ghi mức tin cậy của phép đối chiếu.

### Bước 6 — Đánh giá tác động

Xác minh tài khoản có mục đích hợp lệ, nằm trong ngoại lệ nào, gắn với workload production hay không, có quyền nhạy cảm và có thể bị lạm dụng không. Chọn biện pháp theo rủi ro.

### Bước 7 — Khắc phục và xác minh

Khóa/thu hồi hoặc bổ sung quản trị theo quyết định được duyệt, sau đó **đọc lại trạng thái tại hệ thống đích**. Nếu chưa đóng được tất cả đường truy cập, workflow tiếp tục mở với owner, deadline và biện pháp bù trừ.

## 7. Ví dụ SQL: tìm account không nằm trong danh sách mong muốn

Giả sử có các bảng:

- **expected_accounts(identity_id, system_id, target_account_id, should_be_active)**: kết quả policy về những account phải tồn tại.
- **observed_accounts(system_id, target_account_id, is_active, observed_at)**: các account đọc từ hệ thống đích.
- **retained_accounts(system_id, target_account_id, retention_until)**: bản ghi đã ngừng truy cập nhưng còn được giữ hợp lệ.

SQL minh họa sau chỉ **trả về ứng viên**, không thực hiện hành động xóa:

~~~sql
SELECT
    o.system_id,
    o.target_account_id,
    o.is_active,
    o.observed_at
FROM observed_accounts AS o
LEFT JOIN expected_accounts AS e
       ON e.system_id = o.system_id
      AND e.target_account_id = o.target_account_id
LEFT JOIN retained_accounts AS r
       ON r.system_id = o.system_id
      AND r.target_account_id = o.target_account_id
      AND r.retention_until >= CURRENT_TIMESTAMP
WHERE e.target_account_id IS NULL
  AND r.target_account_id IS NULL;
~~~

Kết quả là account **không nằm trong desired list hoặc retention list đã mô hình hóa**. Nó **không phải danh sách xóa tự động**: cần xem xét mapping thiếu, service registry, ngoại lệ hợp lệ, dữ liệu đích chưa đầy đủ và propagation delay.

### Kiểm tra account vẫn active dù desired là inactive

~~~sql
SELECT
    e.identity_id,
    o.system_id,
    o.target_account_id,
    o.observed_at
FROM expected_accounts AS e
JOIN observed_accounts AS o
  ON e.system_id = o.system_id
 AND e.target_account_id = o.target_account_id
WHERE e.should_be_active = FALSE
  AND o.is_active = TRUE;
~~~

Truy vấn thứ hai tìm **trạng thái active ngoài mong muốn** ngay cả khi account có mapping hợp lệ. Điều này đặc biệt hữu ích khi account của Leaver phải giữ bản ghi nhưng không được đăng nhập.

**Cảnh báo:** Hai ví dụ chỉ thể hiện logic SQL phổ biến. Triển khai thật cần bổ sung scope, loại principal, exception policy, phiên bản snapshot và khả năng dữ liệu bị null/trùng. Tuyệt đối không dùng chúng để chạy lệnh disable/delete hàng loạt mà thiếu quy trình kiểm soát.

## 8. Account thừa khác với entitlement thừa

Một nhân viên còn làm việc có account CRM hợp lệ nhưng vẫn giữ vai trò Export Admin từ bộ phận cũ. Account đó **không thừa**; quyền Admin là **excess entitlement**.

| Tình huống | Phân loại | Xử lý |
|---|---|---|
| Account hợp lệ, dư group Admin | Excess entitlement | Gỡ group/quyền, giữ account |
| Leaver còn local account active | Residual account/access | Chặn, thu hồi, xác minh |
| Account disabled theo lưu giữ | Retained record | Kiểm tra không còn quyền truy cập và hạn lưu |
| Account SaaS không mapping, có phê duyệt và owner | Unmanaged/unlinked | Bổ sung mapping hợp lệ hoặc rà soát |
| Bot có owner và workload còn chạy | Expected non-human identity | Duy trì kiểm soát và đánh giá định kỳ |
| Hai user account ngoài thiết kế cho cùng một người | Potential duplicate | Phân tích target ID, dữ liệu và credential trước khi hợp nhất |

Đối soát entitlement cần bao gồm **quyền trực tiếp, quyền thừa hưởng qua nhóm, nested group, vai trò cloud, quyền tạm thời, PAM, khóa API, SSH key và phiên ứng dụng** nếu hệ thống cho phép. Chỉ gỡ account khỏi một nhóm trong IdP không tự động thu hồi mọi phiên hoặc credential độc lập của ứng dụng.

## 9. Phát hiện account thừa theo Joiner–Mover–Leaver

### 9.1. Joiner: tránh tạo trùng

Nếu một lần tạo user thành công tại đích nhưng phản hồi bị mất, retry POST không idempotent có thể tạo account thứ hai. Khi Joiner, phải kiểm tra **account đã tồn tại** theo target ID, mapping và quan hệ trước khi tạo mới. Với nhân viên tái gia nhập, không tự kích hoạt toàn bộ quyền cũ.

### 9.2. Mover: xóa quyền cũ và account không còn mục đích

Khi người dùng chuyển từ Sales sang Finance, quyền CRM Export có thể không còn hợp lệ dù account CRM vẫn cần cho công việc mới. Cần tính **chênh lệch quyền trước/sau** và gỡ quyền dư. Nếu account chỉ dành cho hệ thống Sales và không còn mục đích, đưa account đó vào quy trình offboarding riêng.

### 9.3. Leaver: ưu tiên account còn truy cập sau hiệu lực

Sự kiện Leaver từ nguồn có thẩm quyền đặt thời điểm cắt quyền. Cần đối soát:

- User ở IdP đã disabled, nhưng SaaS local account vẫn enabled.
- Account disabled nhưng token, PAT, API key, SSH key hoặc credential riêng còn dùng được.
- Quyền qua VPN, cloud, PAM, database hoặc local system còn tồn tại.
- Account đích bị bỏ khỏi IAM inventory nhưng chưa bị khóa ở hệ thống đích.
- Cùng một người còn **quan hệ khác hợp lệ**, vì thế chỉ phần quyền gắn với quan hệ chấm dứt phải thu hồi.

**Cắt SSO không đồng nghĩa thu hồi mọi đường truy cập.** Cần xác minh trực tiếp hoặc có bằng chứng thay thế được phê duyệt.

### 9.4. Rejoiner

Người tái gia nhập có thể giữ identity ID để duy trì lịch sử, nhưng phải tạo hoặc xác nhận quan hệ mới, thực hiện proofing/enrollment theo chính sách và cấp quyền hiện hành. Account cũ hoặc dữ liệu lưu giữ không được tự động biến thành quyền truy cập mới.

## 10. Account phi con người và các ngoại lệ hợp lệ

### Service account và workload identity

Bot, CI/CD identity và connector không xuất hiện trong HRIS. Desired state của chúng dựa trên **service/application registry, workload ID, owner kỹ thuật, mục đích, quyền tối thiểu, credential và môi trường**. Khi owner nghỉ việc, chuyển quyền sở hữu, rà soát secret/role và đánh giá có cần luân chuyển credential; **không xóa bot production chỉ vì owner cá nhân đã Leaver**.

### Device account

Máy tính, máy chủ và IoT có thể có object tại IdP, Active Directory, MDM, PKI và asset inventory. Khi thiết bị bị mất, tái cấp hoặc thải loại, cần đối soát device account, chứng chỉ, enrollment và quyền mạng/VPN. Đổi owner không tự chứng minh credential cũ đã bị thu hồi.

### Shared account

Một số ứng dụng legacy có account dùng chung. Nếu tổ chức cho phép ngoại lệ này, account phải có owner, phương pháp kiểm soát truy cập, lịch sử sử dụng, phương án credential và thời hạn đánh giá. Không thể coi account hợp lệ chỉ vì nhiều người đang dùng; cũng không tự xóa trước khi xác định tác động vận hành.

### Break-glass account

Tài khoản khẩn cấp có thể không được dùng trong nhiều tháng. Nó cần owner, bảo vệ credential, giám sát chặt, thử nghiệm theo chính sách và quy trình sử dụng có kiểm toán. **Không có hoạt động không có nghĩa nó thừa**, nhưng không có hồ sơ/kiểm soát là finding cần xử lý.

## 11. Phân loại rủi ro và độ tin cậy của finding

| Finding | Tình huống | Mức ưu tiên gợi ý |
|---|---|---|
| Leaver account active, có quyền admin hoặc API key | Đường truy cập tồn dư có thể khai thác | Khẩn/cao |
| Cloud account không owner, được cấp quyền rộng | Không có authorization rõ ràng | Cao |
| Nhiều active account ngoài thiết kế trong ứng dụng nhạy cảm | Có thể bỏ sót khi thu hồi | Cao |
| Dormant user account vẫn enabled, owner rõ | Cần xác minh nhu cầu và chính sách | Theo rủi ro |
| Account disabled, lưu giữ có thời hạn và không có đường truy cập | Bản ghi lịch sử hợp lệ | Thấp nếu đúng chính sách |
| Service account có registry/owner hợp lệ | Không nằm trong HRIS | Không phải finding thừa chỉ vì thiếu HR record |

Mức độ rủi ro phụ thuộc **quyền thực tế, phạm vi tài nguyên, độ nhạy dữ liệu, exposure, credential còn sử dụng, dấu hiệu bất thường và tác động khi chặn**.

### Độ tin cậy là chiều riêng

- **Cao:** target ID đã được map chắc chắn, HRIS/nguồn bảo trợ xác nhận quan hệ đã hết, account vẫn active.
- **Trung bình:** thiếu mapping hoặc owner nhưng chưa rõ account có hợp lệ với hệ thống khác không.
- **Thấp:** nguồn đích thiếu dữ liệu, phân trang lỗi, thời điểm snapshot cũ hoặc id mapping yếu.

Với kết quả rủi ro cao nhưng độ tin cậy thấp, có thể cần **giới hạn truy cập tạm thời theo thẩm quyền** và điều tra nhanh, thay vì tự động xóa hoàn toàn.

## 12. Từ finding đến hành động an toàn

~~~mermaid
stateDiagram-v2
    [*] --> Detected: Phát hiện chênh lệch
    Detected --> Triaging: Xác minh nguồn, owner, ID, quyền
    Triaging --> FalsePositive: Sai mapping hoặc snapshot
    Triaging --> ApprovedException: Ngoại lệ còn hợp lệ
    Triaging --> Remediation: Không còn căn cứ giữ account/quyền
    Remediation --> Restricted: Chặn truy cập nếu rủi ro cao
    Remediation --> Verifying: Thu hồi/chuyển owner/sửa liên kết
    Restricted --> Verifying: Hoàn tất xử lý
    Verifying --> Closed: Readback và bằng chứng đạt
    Verifying --> Remediation: Còn sai lệch
    FalsePositive --> Closed: Sửa nguồn/mapping và lưu chứng cứ
    ApprovedException --> Closed: Có owner và hạn review
    Closed --> [*]
~~~

Tùy kết quả phân loại:

1. **Account hợp lệ nhưng thiếu mapping:** xác minh rồi liên kết vào IAM, gán owner và đưa vào review.
2. **Account hợp lệ nhưng quyền dư:** chỉ thu hồi entitlement không hợp lệ, tránh xóa account cần dùng.
3. **Leaver account còn hoạt động:** vô hiệu hóa, thu hồi phiên/token/credential và kiểm chứng.
4. **Account trùng:** xác định bản chính, dữ liệu, lịch sử và credential rồi khóa/hợp nhất theo kế hoạch.
5. **Disabled record cần giữ:** duy trì theo retention nhưng chứng minh không thể dùng truy cập.
6. **Service account thiếu owner:** chuyển owner, xem lại quyền/secret, retire nếu workload không còn.
7. **Unknown privileged account:** điều tra an ninh, hạn chế quyền theo thẩm quyền, bảo toàn bằng chứng.
8. **Ngoại lệ hợp lệ:** ghi lý do nghiệp vụ, owner, phạm vi, ngày hết hạn và kiểm soát bù trừ.

**Không xóa account trước khi đánh giá quyền sở hữu dữ liệu, lịch sử kiểm toán và tác động vận hành.** Với quyền truy cập rủi ro cao, thường cần hạn chế truy cập trước, xử lý bàn giao và lưu giữ sau.

## 13. Đối soát theo sự kiện và định kỳ

**Event-driven reconciliation** được kích hoạt khi Joiner/Mover/Leaver có hiệu lực hoặc khi connector trả kết quả provisioning/deprovisioning. Nó giúp phát hiện nhanh trạng thái chưa đạt sau mỗi thay đổi.

**Periodic reconciliation** là quét định kỳ để phát hiện account tạo thủ công, job bị mất, dữ liệu sync bị lệch, secret tồn dư hoặc quyền đã tích lũy qua thời gian.

Hai phương thức bổ sung nhau:

- Event-driven nhanh nhưng có thể bỏ sót **sự kiện không đến** hoặc thay đổi ngoài IAM.
- Periodic nhìn lại toàn cảnh nhưng có **độ trễ phát hiện** tùy chu kỳ.
- Với account nhạy cảm, có thể cần kiểm soát mạnh, tần suất cao hơn và giám sát bất thường bổ sung.
- Snapshot và hệ thống đích có thể **eventually consistent**; cần cửa sổ nhất quán có giới hạn rồi xác minh lại.
- Không dùng propagation delay làm lý do để quyền Leaver còn hiệu lực kéo dài vô thời hạn.

### Cảnh báo về sự kiện cũ

Một job Mover cũ có thể đến sau Leaver mới và cố **kích hoạt lại** account đã thu hồi. Hệ thống phải dùng version hoặc fencing phù hợp, so sánh với trạng thái nguồn hiện hành và cấm thao tác cũ mở lại quyền. Reconciliation chỉ là một hàng rào phát hiện; tốt hơn nữa là chặn sai lệch ngay khi provisioning.

## 14. Lỗi kỹ thuật làm phát hiện account thừa sai

| Lỗi thiết kế | Hậu quả | Biện pháp |
|---|---|---|
| Thiếu phân trang/quyền đọc API | Bỏ sót hoặc báo sai account | Kiểm tra coverage và quyền connector |
| Dùng email/username duy nhất | Gắn nhầm identity hoặc bỏ sót Leaver | Dùng target ID và identity mapping đã xác minh |
| Chỉ xem user IdP | Bỏ qua local account, cloud principal và token | Quét các hệ thống/đường truy cập thực tế |
| Không có registry cho machine account | Xóa nhầm bot hoặc bỏ sót workload không owner | Desired state riêng cho non-human identities |
| Snapshot không cùng mốc thời gian | Tạo chênh lệch giả trong lúc provisioning | Ghi thời gian, version, cửa sổ xác minh |
| Không phân biệt disabled/retained | Xóa hồ sơ cần lưu hoặc ghi sai rủi ro | Kiểm tra active, session và retention |
| Không xét quyền trực tiếp | Account hợp lệ nhưng admin grant không hợp lệ | Reconcile cả account lẫn entitlement |
| Tin vào HTTP 200/ticket DONE | Đích chưa chắc đã thay đổi | Readback/verification |
| Tự retry tạo account sau timeout | Duplicate account | Lookup target state, idempotency |
| Ngoại lệ không hết hạn | Account cũ được hợp thức hóa vô thời hạn | Owner, lý do, review date và policy |
| Replay event cũ | Mở lại quyền đã thu hồi | Version/fencing và kiểm tra source lifecycle |
| Chỉ kiểm tra last-login | Nhầm service account hoặc thiếu log với account thừa | Dùng nhiều tín hiệu và phân loại principal |

**Đừng công bố “0 account thừa” khi có ứng dụng chưa thể quét.** Phải ghi rõ hệ thống nằm ngoài phạm vi, trường không quan sát được và phương pháp kiểm tra thay thế.

## 15. Kiểm toán và chỉ số vận hành

### Finding cần lưu dữ liệu gì?

- Finding ID, reconciliation run ID, hệ thống đích, target account ID và loại account.
- Identity/relationship ID hoặc workload/asset ID nếu có; **mapping confidence**.
- Desired và observed state, thời gian snapshot, coverage và phiên bản policy.
- Nguồn JML hoặc owner registry, quyết định nghiệp vụ và ngoại lệ liên quan.
- Risk/severity, trạng thái, người chịu trách nhiệm, thời hạn xử lý.
- Lệnh thu hồi, trạng thái tại hệ thống đích, readback, bằng chứng đóng và biện pháp bù trừ.

Một bản ghi minh họa, **không phải SCIM schema chuẩn**:

~~~json
{
  "findingId": "recon-20261123-0084",
  "systemId": "finance-reporting",
  "targetAccountId": "acct-b278",
  "accountType": "HUMAN_USER",
  "findingType": "UNEXPECTED_ACTIVE_ACCOUNT",
  "observed": {
    "active": true,
    "observedAt": "2026-11-23T09:00:00+07:00"
  },
  "desired": {
    "shouldExist": false,
    "reason": "NO_CURRENT_AUTHORIZED_RELATIONSHIP"
  },
  "mappingConfidence": "HIGH",
  "risk": "HIGH",
  "ownerTeam": "IAM_OPERATIONS",
  "state": "OPEN",
  "policyVersion": "reconciliation-policy-v3"
}
~~~

Không lưu mật khẩu, token thô, private key hoặc dữ liệu nhân sự nhạy cảm không cần thiết vào finding/SIEM.

### Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| **Unexpected active accounts** | Account không có căn cứ hợp lệ mà vẫn hoạt động |
| **Orphan accounts** | Account chưa xác định được owner/identity đáng tin |
| **Duplicate accounts** | Account trùng ngoài mô hình được phép |
| **Residual access after Leaver** | Đường truy cập còn hiệu lực sau thời điểm phải cắt |
| **Excess entitlements** | Quyền vượt desired state tại account hợp lệ |
| **Time to verified remediation** | Độ trễ từ phát hiện đến khi đối soát thành công |
| **Exception aging** | Ngoại lệ đang mở hoặc quá hạn đánh giá |
| **Reconciliation coverage** | Tỷ lệ hệ thống, principal, account và quyền quan sát được |
| **False-positive rate** | Chất lượng identity mapping/snapshot/rule |
| **Unowned non-human identities** | Device, bot, service account thiếu owner được xác nhận |

Nên tách kết quả theo rủi ro và phạm vi; số finding ít không nhất thiết tốt nếu quy trình quét còn thiếu hoặc bỏ qua các ứng dụng nhạy cảm.

## 16. Tình huống thực tế: bốn kết quả khác nhau

Giả sử IAM quản lý CRM, cloud, tài khoản kỹ thuật và nguồn HRIS.

**Tình huống A — Leaver vẫn có account CRM:** Minh nghỉ ngày 15/11. IdP đã disabled, nhưng ngày 23/11 CRM vẫn có local account active thuộc target ID đã xác minh của Minh. IAM xác nhận không có quan hệ hợp lệ khác, tạo finding **residual active account** và ưu tiên vô hiệu hóa CRM, thu hồi session/token theo khả năng, đối soát rồi đóng. Nếu không có API, mở ticket có owner và biện pháp giảm thiểu.

**Tình huống B — Mover có quyền dư, không thừa account:** Lan chuyển từ Sales sang Finance. Lan vẫn cần CRM nhưng không cần nhóm SALES_EXPORT_ADMIN. Đối soát phải kết luận **excess entitlement**: gỡ group và kiểm chứng, không xóa account của Lan.

**Tình huống C — Bot không có trong HRIS nhưng hợp lệ:** Account svc-crm-sync không tương ứng với nhân viên, ít đăng nhập tương tác. Service registry cho biết bot chạy batch và có owner nhóm Integration, credential đang được quản lý. Không được coi thừa chỉ vì HRIS không ghi nhận. Nếu owner trước đã nghỉ, cần cập nhật owner và xoay secret khi cần.

**Tình huống D — Local admin không rõ nguồn:** Máy chủ cũ còn account backup-admin-old có quyền cao, không thấy ticket/owner/ngoại lệ và không thuộc registry break-glass. Đây là finding cần kiểm tra nhanh và có thể chặn quyền theo quy trình an ninh. Trước khi xóa vĩnh viễn, xác minh ảnh hưởng đến backup/khôi phục, bảo toàn chứng cứ, thay credential phụ thuộc và readback.

Bốn tình huống dẫn đến **bốn hành động khác nhau**: chặn account Leaver, gỡ entitlement dư, giữ bot hợp lệ và điều tra account local. Vì vậy, phát hiện account thừa là vấn đề **đối soát có ngữ cảnh**, không phải một câu truy vấn “account không có trong HRIS”.

## 17. Checklist thực hành

1. **Authority:** đã biết nguồn có thẩm quyền cho người, nhà thầu, device, workload và break-glass account chưa?
2. **Coverage:** đã bao phủ IdP, directory, SaaS, cloud, local account, PAM, VPN và credential độc lập chưa?
3. **Identity mapping:** dùng ID ổn định và liên kết có bằng chứng thay vì email/name duy nhất chưa?
4. **Snapshot:** nguồn đã đủ phân trang, tenant, quyền đọc, timestamp và độ mới chưa?
5. **Desired state:** quan hệ JML, RBAC/ABAC, phê duyệt, hợp đồng và exception đã được áp dụng chưa?
6. **Phân loại:** có tách orphan, unauthorized, duplicate, dormant, residual, retained và excess entitlement chưa?
7. **Phi con người:** đã đưa service/device accounts, owner và vòng đời credential vào desired state chưa?
8. **Ưu tiên:** Leaver còn active, account admin không owner và token truy cập ngoài SSO đã được xử lý theo rủi ro chưa?
9. **Hành động:** có kiểm tra ảnh hưởng nghiệp vụ, bàn giao, phê duyệt và retention trước khi xóa không?
10. **Chống stale jobs:** một job Joiner/Mover cũ có thể mở lại account Leaver không?
11. **Readback:** có xác minh trạng thái đích thay vì chỉ tin response hoặc báo cáo “đã gửi lệnh” không?
12. **Audit:** mỗi finding có evidence, owner, SLA, decision, ngoại lệ và kết quả xác minh chưa?
13. **Định kỳ:** có cả event-driven và full-scan periodic reconciliation không?
14. **Trung thực về giới hạn:** account và quyền chưa truy vấn được có được ghi thành coverage gap không?

### Ghi nhớ

**Account thừa là tài khoản không còn căn cứ hợp lệ để tiếp tục tồn tại hoặc tiếp tục được sử dụng trong phạm vi quản lý; không phải mọi account vắng trong HRIS hoặc ít hoạt động đều cần xóa.** Phát hiện chính xác đòi hỏi **desired state so với observed state**, identity mapping đáng tin cậy, phân loại account và entitlement, chú ý ngoại lệ của principal phi con người và lựa chọn hành động theo rủi ro. Trong vòng đời **Joiner–Mover–Leaver**, chỉ khi quyền không hợp lệ đã được **thu hồi và xác minh ở hệ thống đích** thì sai lệch mới thật sự được đóng, thay vì bị che giấu bởi trạng thái IdP hay phản hồi provisioning thành công.
