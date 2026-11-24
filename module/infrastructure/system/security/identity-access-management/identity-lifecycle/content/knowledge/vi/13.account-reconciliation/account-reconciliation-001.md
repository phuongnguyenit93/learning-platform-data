# Reconciliation là gì trong quản lý vòng đời danh tính IAM?

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **reconciliation (đối soát)** trong IAM là gì, vì sao nó khác **provisioning**, **đồng bộ dữ liệu** và **rà soát quyền thủ công**.
- Phân biệt **trạng thái mong muốn (desired state)**, **trạng thái quan sát được (observed state)**, **trạng thái nguồn có thẩm quyền** và **quyền hiệu lực**.
- Nhận diện sai lệch: **tài khoản mồ côi, tài khoản chưa liên kết, tài khoản trùng, thiếu quyền, thừa quyền, thuộc tính sai, trạng thái tài khoản sai**, cùng tình huống không đủ dữ liệu để kết luận.
- Mô tả quy trình đối soát an toàn qua **HRIS/nguồn hợp đồng, Identity Provider (IdP), SSO, SCIM/API, RBAC/ABAC**, các ứng dụng và tài khoản dịch vụ.
- Giải thích cách reconciliation củng cố **Joiner–Mover–Leaver (JML)**, đặc biệt ở bước thu hồi quyền sau chuyển vai trò và nghỉ việc.
- Thiết kế cách phát hiện, phân loại, khắc phục, kiểm tra lại và kiểm toán sai lệch mà không vô tình cấp thêm quyền hoặc khóa nhầm người hợp lệ.

## 1. Reconciliation là gì?

**Account reconciliation** là quá trình **thu thập và đối chiếu trạng thái tài khoản, thuộc tính, nhóm và quyền truy cập thực tế ở các hệ thống** với **trạng thái đáng lẽ phải có theo nguồn dữ liệu và chính sách IAM**, từ đó phát hiện sai lệch và điều phối hành động phù hợp.

Định nghĩa này có ba vế quan trọng:

1. **Biết điều gì được phép tồn tại:** hồ sơ danh tính, quan hệ làm việc, phê duyệt, chính sách, vai trò, ngoại lệ và ngày hiệu lực quyết định trạng thái mong muốn.
2. **Biết điều gì thực sự tồn tại:** IAM đọc lại account, group, role, entitlement và trạng thái khác tại ứng dụng đích thay vì chỉ tin vào kết quả đã gửi lệnh.
3. **So sánh và xử lý:** phát hiện những gì thiếu, thừa, không đúng chủ thể hoặc chưa xác định, sau đó ghi nhận, khắc phục và xác minh kết quả.

Ví dụ, nhân viên **An** chuyển từ Support sang Finance lúc 08:00. HRIS đã cập nhật department, IGA xác định role CRM-Support phải bị gỡ và FinanceReader cần được cấp. Tới 08:15, IdP đã thay group nhưng ứng dụng CRM vẫn giữ quyền Support do kết nối SCIM lỗi. **Reconciliation phát hiện khoảng cách giữa quyền mong muốn và quyền hiện có tại CRM**, thay vì kết luận Mover hoàn tất chỉ vì IdP cập nhật thành công.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, reconciliation là **vòng phản hồi kiểm soát** nối xác minh danh tính, provisioning, thay đổi vai trò, thu hồi quyền và kiểm toán. Nó đặc biệt quan trọng khi IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và từng ứng dụng không chia sẻ một cơ sở dữ liệu hoặc một giao dịch nguyên tử.

### 1.1. Reconciliation không phải là gì?

| Khái niệm | Câu hỏi chính | Khác với reconciliation |
| --- | --- | --- |
| **Identity proofing** | Chủ thể được khai báo có đúng người/thực thể không? | Xác lập sự tin cậy ban đầu, không tự kiểm tra quyền ở mọi ứng dụng |
| **Provisioning** | Cần tạo, cập nhật, cấp hoặc thu hồi gì? | Thực thi hành động; kết quả gửi lệnh chưa chứng minh trạng thái cuối |
| **Synchronization** | Dữ liệu được sao chép/trao đổi giữa các hệ thống chưa? | Dữ liệu có thể đồng bộ đúng giao thức nhưng vẫn sai chính sách |
| **SSO authentication** | Người dùng có đăng nhập hợp lệ qua IdP không? | Không đảm bảo tài khoản và quyền ở ứng dụng đích phù hợp |
| **Access review / certification** | Người có thẩm quyền có xác nhận quyền còn cần thiết không? | Là một quyết định quản trị có thể làm thay đổi desired state |
| **Reconciliation** | Trạng thái quan sát tại các hệ thống có khớp trạng thái được phép không? | Cần cả nguồn, chính sách, đọc lại thực tế và xử lý sai lệch |
| **Audit logging** | Điều gì đã xảy ra và có bằng chứng không? | Cung cấp lịch sử; reconciliation dùng bằng chứng để đánh giá sai lệch |

**Cấp phát thành công và đối soát thành công là hai mốc khác nhau.** Đối soát không chỉ dành cho lúc có lỗi; nó có thể chạy sau mọi sự kiện JML và định kỳ để phát hiện thay đổi ngoài luồng.

## 2. Bốn lớp trạng thái phải phân biệt

Một sai lầm phổ biến là dùng một trường “active” cho mọi ý nghĩa. Reconciliation cần mô hình hóa các lớp trạng thái riêng.

| Lớp | Ví dụ | Điều phản ánh |
| --- | --- | --- |
| **Authoritative business state** | HRIS ghi nhân viên ACTIVE, Finance từ 01/12 | Quan hệ làm việc và thuộc tính nghiệp vụ từ nguồn được công nhận |
| **Desired IAM state** | CRM-Support = ABSENT; FinanceReader = PRESENT | Quyền và tài khoản được phép theo chính sách/phê duyệt hiện hành |
| **Observed target state** | CRM-Support = PRESENT; FinanceReader = PRESENT | Group/role/account ứng dụng đang báo có |
| **Effective access state** | Phiên CRM cũ vẫn có thể đọc dữ liệu Support | Khả năng thực thi truy cập sau group, ACL, policy, cache, token và phiên |

**Desired state** không nhất thiết là bản sao HRIS: chính sách IAM có thể thêm điều kiện bảo mật, phân tách nhiệm vụ, cấp quyền tạm thời đã phê duyệt hoặc chặn truy cập khẩn cấp.

**Observed state** không tự chứng minh mọi quyền hiệu lực: API có thể chỉ trả group, trong khi role cục bộ, quyền kế thừa, token đã phát hành và ACL khác vẫn tồn tại.

**Effective access** cần được kiểm tra tới mức khả thi đối với tài nguyên có rủi ro phù hợp. Khi không quan sát được session hoặc token, nên ghi **giới hạn bằng chứng**, thay vì kết luận chắc chắn người dùng không còn đường truy cập.

### 2.1. Ví dụ tập hợp quyền

~~~text
Identity: person-1042
Department source: Finance

Desired entitlements:
  ERP: {InvoiceRead}
  CRM: {}
  VPN: {BasicVPN}

Observed entitlements:
  ERP: {InvoiceRead}
  CRM: {SupportCustomerRead}
  VPN: {BasicVPN}

Diff:
  MISSING_ACCESS = {}
  EXTRA_ACCESS   = {CRM.SupportCustomerRead}

Action:
  yêu cầu thu hồi CRM.SupportCustomerRead
  -> đọc lại CRM -> xác minh quyền đã mất
~~~

Tập hợp được minh họa có tính đơn giản. Trong thực tế phải tính tới **role kế thừa, quyền theo nhóm lồng nhau, permission phủ định, policy ABAC, quyền trực tiếp, tài nguyên theo tenant** và độ mới của thông tin lấy từ ứng dụng.

## 3. Vì sao hệ thống thường bị lệch?

Nhiều hệ thống cùng tham gia quản trị danh tính nhưng không dùng chung mô hình dữ liệu hoặc thời điểm cập nhật:

- HRIS đã đổi bộ phận nhưng sự kiện Mover chưa đến IAM.
- IdP đã xóa nhóm nhưng ứng dụng SaaS đồng bộ chậm hoặc mapping group sai.
- SCIM/API trả thành công cho yêu cầu, trong khi đích xử lý bất đồng bộ hoặc chỉ hỗ trợ một phần chức năng.
- Quản trị viên cấp quyền trực tiếp tại ứng dụng, bỏ qua workflow phê duyệt IAM.
- Người dùng có tài khoản legacy tạo trước khi doanh nghiệp triển khai IdP/SSO.
- Một người chuyển pháp nhân nhưng account ở pháp nhân cũ chưa được thu hồi.
- Nhân viên đã nghỉ nhưng một ứng dụng còn tài khoản local hoặc refresh token đang hoạt động.
- Service principal tiếp tục tồn tại sau khi workload giải thể hoặc owner nghỉ.
- Sự kiện HRIS đến trễ, lặp hoặc sai thứ tự và một tác vụ cũ phục hồi quyền.
- Dữ liệu account discovery không đầy đủ do connector bị mất quyền, lỗi phân trang, rate limit hoặc API timeout.

Một cơ chế đồng bộ đáng tin vẫn có thể gặp **drift** vì ứng dụng hỗ trợ thao tác ngoài luồng. Reconciliation chính là cách tìm lại khoảng cách giữa mục tiêu và thực tế.

## 4. Kiến trúc vòng đối soát

~~~mermaid
flowchart TD
  A["HRIS / nguồn hợp đồng / service registry"] --> B["Identity registry / IGA"]
  B --> C["Chính sách RBAC/ABAC + approval"]
  C --> D["Tính desired accounts và entitlements"]
  E["IdP / directory"] --> F["Thu thập observed state"]
  G["SaaS qua SCIM hoặc API"] --> F
  H["Cloud, VPN, hệ thống legacy"] --> F
  I["Danh tính dịch vụ / workload"] --> F
  D --> J["Engine reconciliation"]
  F --> J
  J --> K{"Sai lệch hoặc thiếu dữ liệu?"}
  K -->|"Khớp, dữ liệu đủ mới"| L["Ghi verifiedAt + bằng chứng"]
  K -->|"Lệch có đủ bằng chứng"| M["Phân loại + chính sách xử lý"]
  K -->|"Không thể xác định"| N["UNKNOWN / exception / thu thập lại"]
  M --> O["Provisioning/deprovisioning hoặc review"]
  O --> P["Đọc lại trạng thái đích"]
  P --> J
  J --> Q["Audit / SIEM / số liệu vận hành"]
~~~

Các trách nhiệm chính:

1. **Nguồn có thẩm quyền:** xác nhận thông tin trong phạm vi được giao. HRIS thường có thẩm quyền với trạng thái việc làm của nhân viên; nguồn hợp đồng với nhà thầu; service registry với workload.
2. **Identity registry/IGA:** liên kết identityId với từng account, lưu quan hệ làm việc và điều kiện truy cập, theo dõi quyền đã được chấp thuận.
3. **Policy engine/governance:** tính quyền mong muốn từ RBAC, ABAC, least privilege, SoD, ngày hiệu lực và ngoại lệ.
4. **Connector/discovery:** đọc user, group, role và trạng thái thực tế từ các hệ thống đích; cần báo cáo rõ giới hạn dữ liệu.
5. **Reconciliation engine:** chuẩn hóa, nối dữ liệu, so sánh, ưu tiên lỗi và sinh hồ sơ sai lệch.
6. **Remediation/orchestration:** sửa đổi ở hệ thống có quyền thay đổi theo chính sách, với phê duyệt và kiểm soát an toàn.
7. **Audit/monitoring:** giữ lịch sử, bằng chứng, độ trễ và trách nhiệm xử lý.

Không nên tự động coi nguồn nào “đúng tuyệt đối” trong mọi trường hợp. Ví dụ HRIS có thẩm quyền về employment status nhưng không phải nguồn quyết định việc tài khoản đang bị khóa do sự cố bảo mật có thể được mở lại hay không.

## 5. Phạm vi và đơn vị đối soát

Trước khi lập thuật toán, cần xác định **đối tượng nào được đưa vào so sánh**.

### 5.1. Những lớp thường được đối soát

| Lớp | Ví dụ kiểm tra | Giới hạn |
| --- | --- | --- |
| **Identity ↔ account** | Mỗi user ERP có identity/owner hợp lệ? | Account không liên kết có thể hợp lệ nhưng phải có người xử lý |
| **Account existence/status** | Account cần có đã được tạo? Account Leaver đã bị khóa? | Enabled/disabled không đồng nhất với session |
| **Attributes** | Department, manager, workerType, expiry có đúng nguồn? | Mỗi thuộc tính có nguồn thẩm quyền riêng |
| **Group membership** | Tư cách thành viên nhóm có khớp mục tiêu? | Group có thể lồng nhau hoặc được ánh xạ sang role |
| **Entitlements/roles** | Tài khoản có đúng permission đã phê duyệt? | Quyền trực tiếp và role ứng dụng có thể nằm ngoài SCIM |
| **Access policy** | ABAC có phản ánh thuộc tính hiện hành? | Policy có thể đổi theo tài nguyên, thời điểm, context |
| **Session/credential** | Token hoặc phiên không còn hợp lệ khi cần thu hồi? | Có hệ thống không cho kiểm tra hoặc revoke trực tiếp |
| **Service/workload identity** | Workload có owner, mục đích và quyền còn hiệu lực? | Không dùng employment status của người như trạng thái workload |
| **Delegation/sharing** | Ủy quyền và quyền chia sẻ có hết hạn đúng chưa? | Có thể nằm ở ứng dụng, không ở IdP |

### 5.2. Phạm vi theo thời gian

Reconciliation có thể diễn ra:

- **Post-provisioning:** ngay sau Joiner, Mover hoặc Leaver để xác minh thao tác.
- **Event-triggered:** khi HRIS cập nhật, tài khoản bị sửa ngoài luồng hoặc phát hiện cảnh báo.
- **Scheduled/full scan:** đối soát định kỳ toàn bộ tài khoản, phát hiện drift cũ và tài khoản bị bỏ sót.
- **Targeted scan:** chỉ rà tài khoản đặc quyền, một ứng dụng rủi ro cao hoặc một nhóm người dùng cụ thể.
- **Incident-driven:** điều tra tài khoản bị nghi chiếm đoạt hoặc quyền truy cập tồn dư.

Đối soát định kỳ **không thay thế** thu hồi quyền tức thời theo sự kiện Leaver. Ngược lại, chỉ kiểm tra sau workflow cũng có thể không phát hiện sửa quyền thủ công xảy ra nhiều tuần sau.

## 6. Dữ liệu cần để reconciliation đáng tin

### 6.1. Khóa nhận diện và account linking

| Trường | Mục đích |
| --- | --- |
| identityId | Định danh nội bộ ổn định, không tái sử dụng cho người khác |
| identityType | HUMAN, SERVICE, WORKLOAD hoặc phân loại do tổ chức chọn |
| sourceSystem + sourceRecordId | Gắn danh tính với nguồn có thẩm quyền |
| employmentRelationshipId | Tách nhiều quan hệ làm việc của cùng một người |
| targetSystem + targetAccountId | Tham chiếu tài khoản thực tế tại từng ứng dụng |
| targetTenant / organization | Tránh nhầm tài khoản cùng ID ở các tenant khác nhau |
| entitlementId / resourceId | Xác định đúng quyền cụ thể trên tài nguyên |
| policyVersion + approvalRef | Giải thích căn cứ desired access |
| effectiveAt / expiresAt | Ngày quyền hoặc quan hệ có hiệu lực và hết hạn |
| observedAt / snapshotId | Cho biết trạng thái đích được đọc lúc nào |
| sourceVersion / correlationId | Chống sự kiện cũ và liên kết quá trình xử lý |

**Email hoặc tên hiển thị không phải khóa nối an toàn** vì có thể thay đổi hoặc tái sử dụng. Nếu ứng dụng chỉ trả email, cần quy tắc xác minh liên kết và luồng ngoại lệ; không tự gán account chưa rõ cho người có email trùng.

### 6.2. Ví dụ bản ghi đối soát

~~~json
{
  "reconciliationRunId": "rec-20261123-0007",
  "identityId": "person-1042",
  "sourceSystem": "HRIS",
  "sourceRecordId": "worker-1042",
  "sourceVersion": 31,
  "targetSystem": "CRM",
  "targetTenant": "corp",
  "targetAccountId": "crm-user-722",
  "objectType": "ENTITLEMENT",
  "entitlementId": "crm-support-reader",
  "desiredState": "ABSENT",
  "observedState": "PRESENT",
  "discrepancyType": "EXTRA_ACCESS",
  "desiredEffectiveAt": "2026-11-20T08:00:00+07:00",
  "observedAt": "2026-11-23T09:00:00+07:00",
  "policyVersion": "mover-policy-v5",
  "status": "OPEN",
  "exceptionOwner": "iam-operations",
  "correlationId": "mover-20261120-8391"
}
~~~

Đây là **JSON minh họa**, không phải schema chuẩn của SCIM, OIDC hoặc một sản phẩm IAM. Một run có thể chứa nhiều discrepancy; nên lưu **bản ghi quan sát theo từng target** và **lý do không thể đọc** nếu connector gặp lỗi.

### 6.3. Nguồn và độ mới

Mỗi snapshot nên có ít nhất:

- Hệ thống/tenant được đọc, phạm vi user/role trả về.
- Thời điểm bắt đầu/kết thúc thu thập.
- Kết quả phân trang và quyền của connector có đủ không.
- Phiên bản hoặc thời điểm cập nhật nếu API cung cấp.
- Độ mới tối đa được chính sách chấp nhận.
- Thông tin lỗi, giới hạn API hoặc danh mục không thể quan sát.

**Không suy ra “không có quyền” từ một kết quả đọc thất bại hoặc bị cắt trang.** Nếu dữ liệu chưa đủ, kết quả đúng là **UNKNOWN/INCOMPLETE**, không phải **ABSENT**.

## 7. Nhận diện và liên kết tài khoản trước khi so sánh

Một bước khó của reconciliation là **account correlation**: xác định account nào đại diện cho identity nào.

Ví dụ, người dùng có thể xuất hiện dưới các giá trị khác nhau:

~~~text
HRIS.sourceRecordId   = worker-1042
IAM.identityId        = person-1042
IdP.userId            = idp-user-0031
ERP.userId            = erp-884
CRM.userId            = crm-user-722
Git.subjectId         = git-2181
~~~

Nếu chỉ so sánh username hoặc email, có thể xảy ra:

- Người đổi tên/email bị nhìn như đã có account mới và mất liên kết cũ.
- Email của Leaver bị tái sử dụng, account cũ bị gắn nhầm vào Joiner mới.
- Tài khoản quản trị riêng bị bỏ qua vì username khác tài khoản chính.
- Một người có nhiều relationship với tổ chức và các quyền không cùng phạm vi.
- Tài khoản dùng chung hoặc service principal bị coi nhầm là danh tính con người.

### 7.1. Quy trình nối account an toàn

1. Ưu tiên liên kết đã có, dựa trên **ID ổn định** của nguồn và account.
2. Xác minh tính hợp lệ của mapping trong tenant/organization cụ thể.
3. Khi phát hiện account chưa có liên kết, tìm bằng chứng bổ sung và áp dụng quy tắc match được phê duyệt.
4. Nếu có nhiều khả năng cùng khớp, ghi **AMBIGUOUS_LINK** và chuyển owner; không tự merge.
5. Lưu kết quả, người quyết định, bằng chứng đủ mức và thời gian.
6. Nếu phát hiện liên kết sai, thực hiện quy trình **split/correct** có audit và rà lại quyền đã cấp/thu hồi theo liên kết cũ.

Không nên sửa hồ sơ HRIS chỉ để “khớp tên tài khoản”. Nguồn có thẩm quyền phải được bảo toàn và mọi correction cần có trách nhiệm rõ ràng.

### 7.2. Tài khoản mồ côi và tài khoản chưa liên kết

Hai khái niệm dễ bị dùng lẫn:

- **Unlinked/unmatched account:** đã phát hiện account ở hệ thống đích nhưng **chưa xác lập được identity/owner hợp lệ**. Chưa đủ dữ liệu để kết luận có phải account mồ côi.
- **Orphan account:** account **không còn chủ thể, owner hoặc cơ sở nghiệp vụ hợp lệ** theo định nghĩa tổ chức; ví dụ tài khoản người đã nghỉ vẫn được bật và không có ngoại lệ được phê duyệt.

Một account chưa liên kết cần điều tra và ràng buộc quản trị; không tự động xóa mọi account unmatched, vì có thể là integration account, tài khoản break-glass hoặc đối tượng hợp lệ chưa được nhập vào inventory.

## 8. Phân loại sai lệch

| Mã minh họa | Ý nghĩa | Ví dụ | Cách xử lý ban đầu |
| --- | --- | --- | --- |
| **MISSING_ACCOUNT** | Tài khoản cần có nhưng chưa tồn tại | Joiner chưa được tạo ERP user | Kiểm tra eligibility, connector, tạo có kiểm soát |
| **EXTRA_ACCOUNT** | Account tồn tại nhưng không còn được phép | Leaver còn user SaaS active | Ưu tiên kiểm tra/thu hồi theo mức rủi ro |
| **ACCOUNT_STATUS_DRIFT** | Enabled/disabled khác mục tiêu | Account đang bật dù đã quyết định khóa | Xác định nguồn và hành động đúng |
| **MISSING_ACCESS** | Quyền hợp lệ chưa được cấp | FinanceReader thiếu | Kiểm tra approval và thực thi |
| **EXTRA_ACCESS** | Quyền không còn hợp lệ vẫn tồn tại | Role Support sau Mover | Ưu tiên thu hồi sau xác nhận liên kết |
| **ATTRIBUTE_DRIFT** | Thuộc tính sai nguồn hoặc thời điểm | Department IdP cũ | Xác minh nguồn, cập nhật mapping |
| **UNLINKED_ACCOUNT** | Không thể xác định chủ thể/owner | Local account legacy không có identityId | Điều tra, gắn owner hoặc xử lý |
| **DUPLICATE_ACCOUNT** | Nhiều account có thể trùng một chủ thể ngoài chính sách | Hai CRM user sinh từ retry | Kiểm tra trước khi merge/delete |
| **UNAPPROVED_ENTITLEMENT** | Quyền không có approval/policy còn hiệu lực | Role admin cấp thủ công | Rà soát căn cứ, xử lý ngoại lệ |
| **EXPIRED_EXCEPTION** | Quyền ngoại lệ quá ngày được duyệt | Quyền tạm thời chưa gỡ | Thu hồi và ghi nguyên nhân |
| **OWNER_MISSING** | Danh tính phi con người thiếu chủ sở hữu | Bot vẫn chạy, owner cũ nghỉ | Bàn giao, rà quyền và credential |
| **UNKNOWN/INCOMPLETE** | Không đủ dữ liệu kết luận | Connector chỉ tải được 30/100 trang | Thu thập lại, alert, không ghi “khớp” |

Những tên mã là **quy ước minh họa**, có thể mở rộng cho quyền hiệu lực, token, SoD, role kế thừa, tenant hoặc sai cấu hình federation.

### 8.1. Phân biệt thiếu quyền và thừa quyền

**MISSING_ACCESS** thường làm người dùng không thực hiện được công việc. **EXTRA_ACCESS** có thể tạo rủi ro bảo mật dù người dùng không có ý định lạm dụng. Với Leaver hoặc Mover có đặc quyền, quyền thừa nên có **mức ưu tiên cao**, deadline thu hồi và biện pháp chặn bổ sung nếu hệ thống không thể xử lý ngay.

Không nên áp dụng một phép tự động “đồng bộ mọi quyền thiếu” khi chưa kiểm tra desired state có dựa trên nguồn mới nhất và phê duyệt hợp lệ. Tương tự, không tự xóa account khi chưa nhận diện chính xác owner và phụ thuộc dịch vụ.

## 9. Quy trình reconciliation từ đầu đến cuối

~~~mermaid
flowchart TD
  A["Chọn scope, target, thời điểm"] --> B["Đọc nguồn có thẩm quyền và approval"]
  B --> C["Tính desired state theo policy"]
  A --> D["Discover toàn bộ accounts / entitlements đích"]
  D --> E{"Dữ liệu thu thập đầy đủ?"}
  E -->|"Không"| X["UNKNOWN: retry discovery + alert"]
  E -->|"Có"| F["Account linking + chuẩn hóa dữ liệu"]
  C --> G["So sánh desired vs observed"]
  F --> G
  G --> H{"Có discrepancy?"}
  H -->|"Không"| I["Verified: lưu bằng chứng và độ mới"]
  H -->|"Có"| J["Phân loại + đánh giá mức rủi ro"]
  J --> K{"Được phép auto-remediate?"}
  K -->|"Không"| L["Review / ticket / approval / owner"]
  K -->|"Có"| M["Lập task cấp/gỡ/khóa theo policy"]
  L --> M
  M --> N["Thực thi idempotent + ghi kết quả"]
  N --> O["Đọc lại target, xác minh"]
  O --> P{"Đã đúng và đủ bằng chứng?"}
  P -->|"Chưa"| Q["Exception, SLA, biện pháp bù trừ"]
  Q --> O
  P -->|"Có"| I
~~~

### Bước 1 – Định nghĩa mục tiêu

Xác định **danh mục hệ thống**, tenant, loại tài khoản, entitlement cần kiểm tra, tần suất, mức rủi ro và tiêu chí hoàn tất. Không thể kết luận “toàn doanh nghiệp không còn quyền thừa” nếu mới quét một ứng dụng.

### Bước 2 – Thu dữ liệu nguồn và tính desired state

Đọc trạng thái nhân sự/hợp đồng và chính sách hiện hành, kiểm tra:

- Identity còn hợp lệ không? Có nhiều employment relationships cùng lúc không?
- Vai trò, phòng ban, dự án và quyền cần thiết hiện tại là gì?
- Có approval, SoD, ngoại lệ có hạn hoặc chặn bảo mật không?
- Những quyền nào phải gỡ do Mover hoặc Leaver?
- Ngày giờ nào quyền nên có hiệu lực?

**Desired state là một quyết định được tính toán có căn cứ**, không phải sao chép tất cả quyền đang tồn tại sang danh sách “được phép”.

### Bước 3 – Thu thập observed state

Dùng SCIM/API, directory, cloud IAM hoặc báo cáo hệ thống, lưu kết quả kèm **observedAt**, phạm vi đã quét và lỗi. Đối soát phải biết những phần không đọc được; nếu API chỉ cấp 50 user mỗi trang, phải xử lý phân trang trước khi suy luận account không tồn tại.

### Bước 4 – Chuẩn hóa và liên kết

Ánh xạ userId, roleId, group, tenant, resource tới danh mục entitlement và identityId trong IAM. Phân biệt role trực tiếp với quyền kế thừa. Nếu không nối được, tạo discrepancy riêng thay vì gán bừa vào người gần giống.

### Bước 5 – So sánh

Có thể tính theo tập hợp đơn giản:

~~~text
MISSING = desired - observed
EXTRA   = observed - desired
MATCHED = desired intersect observed
~~~

Tuy nhiên chỉ dùng phép trừ tập hợp sau khi **đã thống nhất scope, thời gian hiệu lực, loại quyền và độ tin cậy dữ liệu**. Không so sánh quyền ở tenant A với quyền của tenant B hoặc snapshot ngày hôm qua với desired state vừa đổi mà không có cửa sổ chờ.

### Bước 6 – Đánh giá nguyên nhân và mức độ ưu tiên

Sai lệch có thể xuất phát từ lỗi provisioning, mapping, nguồn sai, thay đổi thủ công, hồ sơ hết hạn hoặc eventual consistency. Mức ưu tiên phụ thuộc:

- Quyền thừa hay thiếu; đặc quyền hay thông thường.
- Người còn làm việc hay Leaver đã hết hiệu lực.
- Tài nguyên nhạy cảm, dữ liệu khách hàng hoặc môi trường production.
- Phạm vi tài khoản bị ảnh hưởng và thời gian sai lệch.
- Có thể chặn tạm bằng biện pháp an toàn khác không.

### Bước 7 – Khắc phục có kiểm soát

Lập task phù hợp: cấp quyền thiếu hợp lệ, gỡ quyền thừa, vô hiệu hóa account, sửa mapping, liên kết owner hoặc yêu cầu phê duyệt. Mỗi hành động phải theo **policy, thẩm quyền và idempotency**; phải phân biệt thay đổi account người với service workload có phụ thuộc sản xuất.

### Bước 8 – Đọc lại và đóng

Sau thay đổi, **đọc lại observed state** khi dữ liệu đã có khả năng nhất quán, xác minh sai lệch biến mất và lưu **verifiedAt** cùng bằng chứng. Nếu API chỉ báo accepted hoặc hệ thống không quan sát được, giữ trạng thái **PENDING/PARTIAL/UNKNOWN** với owner và deadline thay vì đánh dấu thành công giả.

## 10. Quan hệ giữa reconciliation và Joiner–Mover–Leaver

### 10.1. Joiner: xác minh cấp đúng người, đúng quyền

Ở giai đoạn Joiner, reconciliation trả lời:

- Account IdP và các ứng dụng bắt buộc đã được tạo chưa?
- Account mới có liên kết đúng identityId không, hay bị tạo trùng?
- MFA/điều kiện đăng nhập có đúng chính sách không?
- Role được cấp có đúng nhu cầu công việc, không có đặc quyền ngoài phạm vi không?
- Quyền trước ngày bắt đầu có bị mở quá sớm không?

Một Joiner tạo thành công 4/5 account nhưng còn thiếu ERP cần được ghi **PARTIAL** theo tiêu chí tổ chức. Nếu tài khoản ERP vừa được tạo có quyền admin ngoài dự kiến, đó là **EXTRA_ACCESS**, không thể coi là hoàn tất dù user đã đăng nhập được.

### 10.2. Mover: phát hiện quyền cũ bị bỏ quên

Mover thường không thay đổi employment status = ACTIVE, nhưng department, project, manager hoặc policy role thay đổi. Reconciliation cần so sánh **tập quyền mới đáng có** với **mọi quyền hiện hữu**, chứ không chỉ kiểm tra role mới đã cấp.

~~~text
Trước Mover: {SupportReader, VPNBasic}
Sau Mover được duyệt: {FinanceReader, VPNBasic}
Thực tế: {SupportReader, FinanceReader, VPNBasic}

Kết luận: EXTRA_ACCESS = SupportReader
Không phải: "Mover thành công vì FinanceReader đã có"
~~~

Khi policy ABAC dùng department, cần kiểm tra thuộc tính mà ứng dụng thực sự đọc và token/phiên có thể giữ claim cũ; group IdP đã đổi không nhất thiết đủ để gỡ quyền ở mọi tài nguyên.

### 10.3. Leaver: chứng minh thu hồi cuối cùng

Đối với Leaver, reconciliation cần tìm **mọi account liên kết** và account chưa liên kết có khả năng thuộc chủ thể, rồi xác minh trạng thái:

- IdP đã chặn đăng nhập mới theo yêu cầu.
- Ứng dụng đã vô hiệu hóa/deprovision account hoặc thu hồi entitlement phù hợp.
- Cloud role, VPN, SSH, khóa, chứng chỉ, API token hoặc delegation thuộc phạm vi đã xử lý.
- Phiên và refresh token còn giá trị được xử lý theo khả năng hệ thống.
- Quyền cấp trực tiếp hoặc group riêng của ứng dụng không bị bỏ sót.
- Các ngoại lệ và công việc chưa hoàn tất có người chịu trách nhiệm.

**Leaver không hoàn tất chỉ vì HRIS ghi TERMINATED hoặc IdP disabled.** Kết luận hoàn tất cần dựa trên phạm vi đích được xác định và bằng chứng thực tế, đồng thời minh bạch giới hạn quan sát.

### 10.4. Nguồn của quyền và trạng thái Leaver phức tạp

Một người có thể thôi làm ở đơn vị A nhưng vẫn có quan hệ hợp lệ với đơn vị B. Nếu reconciliation chỉ thấy **một employment relationship đã kết thúc** rồi tự khóa toàn bộ account, có thể gây mất truy cập hợp lệ. Desired state cần xét **từng quan hệ và quyền tương ứng**, nhất là khi hoạt động xuyên pháp nhân hoặc nhiều hợp đồng.

## 11. IdP, SSO, SCIM, RBAC/ABAC cung cấp gì cho đối soát?

### 11.1. Identity Provider (IdP)

IdP thường cung cấp thông tin account, trạng thái kích hoạt, nhóm, phương thức xác thực hoặc sự kiện quản lý phiên trong phạm vi nó hỗ trợ. Đây là dữ liệu quan trọng để kiểm tra tài khoản doanh nghiệp.

Nhưng **IdP không tự biết mọi local account, role hoặc token độc lập ở SaaS**. Vì vậy đối soát IdP chỉ là một phần của đối soát toàn doanh nghiệp.

### 11.2. Single Sign-On (SSO)

SSO qua OIDC hoặc SAML giúp ứng dụng tin vào IdP khi xác thực. Reconciliation cần lưu ý:

- Một ứng dụng có thể có account riêng dù đăng nhập bằng SSO.
- Claim về role/department có thể cũ ở token hoặc phiên được phát hành trước Mover.
- Một số ứng dụng **Just-in-Time provisioning** tạo account khi đăng nhập lần đầu.
- Liên kết user theo email có thể nhầm nếu email thay đổi hoặc được tái sử dụng.
- Việc đăng nhập thành công không chứng minh quyền ở ứng dụng phù hợp với chính sách.

Đọc nhóm từ IdP cần kết hợp kiểm tra mapping của ứng dụng đích và entitlement hiệu lực khi có yêu cầu.

### 11.3. SCIM

SCIM hỗ trợ quản lý tài nguyên như User và Group ở hệ thống tương thích. Nó có thể hỗ trợ liệt kê tài khoản, đọc thuộc tính, quản lý nhóm, tạo hoặc vô hiệu hóa user.

**Giới hạn:** không mặc định ứng dụng hỗ trợ đầy đủ các capability, role đặc thù, phiên hoặc API token. Thuộc tính **active** trong tài nguyên User SCIM mô tả trạng thái user tại hệ thống đó, không thay thế employment status nghiệp vụ. Một truy vấn SCIM thành công cũng không chứng minh toàn bộ quyền của ứng dụng đã được thu thập.

### 11.4. RBAC

**Role-Based Access Control** cung cấp quan hệ role–permission và role–user. Reconciliation phải so sánh cả role được cấp **trực tiếp** và role **kế thừa qua group hoặc cấu trúc tổ chức** khi mô hình cho phép. Nếu chỉ đối chiếu các role direct, có thể bỏ sót quyền thừa từ nhóm lồng nhau.

### 11.5. ABAC

**Attribute-Based Access Control** sử dụng các thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh. Nếu department tại HRIS đổi nhưng bản sao thuộc tính tại IdP hoặc ứng dụng còn cũ, quyền có thể khác desired policy dù role không đổi.

Một rule minh họa:

~~~text
PERMIT invoice.read WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.department == resource.ownerDepartment
    AND subject.hasApprovedRole("InvoiceReader")
    AND resource.classification <= subject.clearance
ELSE DENY
~~~

Đây là **mã giả**, không phải ngôn ngữ policy chuẩn. Khi kiểm tra quyền hiệu lực, cần biết **phiên bản policy**, thuộc tính đã dùng, nguồn thuộc tính và thời gian quan sát, không chỉ lấy policy hiện tại áp ngược lên quá khứ.

## 12. Đối soát tài khoản dịch vụ và workload

**Non-human identities (NHI)** như service account, bot, CI/CD pipeline và workload principal cần reconciliation riêng. Chúng thường không có bản ghi employment status trong HRIS.

Nguồn có thẩm quyền có thể là **service registry, CMDB, nền tảng triển khai, secret inventory hoặc cloud identity inventory**. Cần tìm hiểu:

| Đối tượng kiểm tra | Câu hỏi |
| --- | --- |
| Service principal | Workload nào đang dùng, mục đích hợp lệ không? |
| Owner / owner team | Có người hoặc nhóm chịu trách nhiệm đang hoạt động không? |
| Credential | Token/chứng chỉ/secret có còn cần, có quá hạn hoặc chưa rotate? |
| Permission | Có quyền vượt quá scope workload không? |
| Environment | Principal production có bị dùng nhầm ở dev không? |
| Last usage / inventory | Có dấu hiệu không còn sử dụng không; dữ liệu sử dụng có đủ tin cậy không? |
| End-of-life | Workload đã giải thể nhưng tài khoản/quyền còn tồn tại không? |

Khi nhân viên quản lý một workload nghỉ việc, **Leaver của nhân viên** không nên tự động xóa workload vẫn phục vụ sản xuất. Thay vào đó cần **chuyển owner, gỡ quyền quản lý của người cũ, đánh giá secret/credential và đối soát quyền dịch vụ**.

Đối với credential, chỉ lưu **identifier, metadata vòng đời và bằng chứng trạng thái**, không đưa private key hoặc token thực vào báo cáo đối soát.

## 13. An toàn khi tự động khắc phục sai lệch

Một công cụ reconciliation có quyền cập nhật account ở nhiều nơi rất dễ gây ảnh hưởng lớn nếu dữ liệu nguồn hoặc mapping sai. **Phát hiện sai lệch không có nghĩa luôn được phép sửa tự động.**

### 13.1. Phân loại theo khả năng tự động hóa

| Loại tình huống | Có thể tự động? | Điều kiện và cảnh báo |
| --- | --- | --- |
| Cấp quyền còn thiếu đã có approval | Có thể | Chắc chắn identity link, nguồn mới nhất, scope và SoD |
| Thu hồi quyền thừa sau Mover | Có thể ưu tiên tự động theo policy | Xác định đúng account/role; quản lý ngoại lệ và quyền có phụ thuộc |
| Vô hiệu hóa account Leaver | Thường cần thực hiện theo SLA | Phân biệt quan hệ việc làm, break-glass và account dịch vụ |
| Account chưa liên kết được owner | Không nên xóa tự động chỉ vì không match | Điều tra, gắn owner, dùng biện pháp an toàn theo rủi ro |
| Role admin ở production xuất hiện ngoài luồng | Cần phản ứng nhanh | Có thể chặn tạm theo playbook, đồng thời review nguồn và quyền |
| Connector bị lỗi đọc dữ liệu | Không thể kết luận account vắng mặt | Retry, cảnh báo, giữ UNKNOWN |
| Thay đổi role cho workload quan trọng | Tùy chính sách | Kiểm tra owner/phụ thuộc, kế hoạch không gián đoạn |
| Tài khoản hợp pháp nhưng mapping HRIS mới chưa hoàn thiện | Cần review | Không cấp thêm quyền; tránh khóa nhầm nếu bằng chứng chưa đủ |

**Khôi phục từ snapshot cũ không phải luôn đúng.** Khi nhiều sự kiện JML xảy ra liên tiếp, task sửa sai phải tính lại desired state từ nguồn hiện hành thay vì tự động khôi phục những quyền không còn hợp lệ.

### 13.2. Chống loop và thao tác cạnh tranh

Nếu hai connector liên tục “sửa lại” cùng thuộc tính theo hai nguồn khác nhau, sẽ xuất hiện **reconciliation loop**. Cần:

- Xác định **source of truth cho từng thuộc tính**, không chỉ từng hệ thống tổng thể.
- Phân biệt chiều đọc và chiều ghi; hạn chế viết ngược về nguồn nhân sự ngoài thẩm quyền.
- Dùng version hoặc optimistic concurrency khi nền tảng hỗ trợ.
- Sử dụng idempotency key, giới hạn retry và lịch sử task.
- Chặn các workflow cũ khôi phục quyền sau Leaver hoặc sau quyết định bảo mật mới.
- Khi không giải quyết được tranh chấp, đưa ngoại lệ cho owner thay vì chạy vòng sửa vô hạn.

## 14. Tính nhất quán theo thời gian và độ tin cậy bằng chứng

### 14.1. Eventual consistency

Một ứng dụng có thể nhận PATCH SCIM lúc 08:00 nhưng đến 08:03 mới phản ánh thay đổi qua API đọc. Nếu quét lúc 08:00:10, dữ liệu vẫn cũ.

Điều này không cho phép bỏ qua sai lệch. Hệ thống cần **cửa sổ quan sát được định nghĩa, deadline theo mức rủi ro, retry có giới hạn và cảnh báo quá hạn**. Quyền đặc quyền hoặc Leaver khẩn cấp có thể cần biện pháp chặn ngay thay vì chờ API hội tụ.

### 14.2. Năm mốc thời gian nên lưu

| Mốc | Câu hỏi |
| --- | --- |
| **effectiveAt** | Quyền đáng lẽ thay đổi từ khi nào? |
| **requestedAt** | IAM đã gửi lệnh lúc nào? |
| **appliedAt** | Đích cho biết đã áp dụng lúc nào, nếu có? |
| **observedAt** | Snapshot đích được thu thập lúc nào? |
| **verifiedAt** | Lúc nào IAM có đủ bằng chứng trạng thái khớp? |

**Không tự điền appliedAt = requestedAt** khi API chỉ trả “accepted”. Khi đích không báo thời điểm áp dụng, giữ thông tin không xác định và dùng observedAt/verifiedAt với diễn giải thích hợp.

### 14.3. Không biết khác với không tồn tại

Nếu API lỗi, kết quả có thể là:

~~~text
CRM account inventory: COMPLETE   -> 1500/1500 users
Cloud role inventory: INCOMPLETE   -> 2 pages failed
ERP permission list: UNAVAILABLE   -> API timeout

Kết luận:
  - Có thể đối soát CRM nếu dữ liệu đủ mới.
  - Không thể khẳng định Cloud và ERP không có quyền thừa.
  - Cần đánh dấu UNKNOWN, xử lý lỗi đọc và thử lại.
~~~

Nếu hệ thống ghi “verified” khi snapshot chưa đầy đủ, báo cáo có thể khiến đội vận hành **tin sai rằng quyền đã được thu hồi**.

### 14.4. Sự kiện cũ, lặp và thay đổi trong lúc quét

Reconciliation có thể bắt đầu khi HRIS vẫn ACTIVE, nhưng Leaver đến lúc scan chưa xong. Trước khi thực thi remediation có tác động, cần **kiểm tra lại phiên bản nguồn và desired state** hoặc dùng cơ chế kiểm soát nhất quán.

Một sự kiện Joiner cũ đến muộn không được tạo lại account sau Leaver. Tương tự, một scan cũ không nên cấp lại role đã bị gỡ bởi Mover mới hơn.

## 15. Mô hình thuật toán đối soát

Mã giả sau minh họa quy trình tổng quát:

~~~text
function reconcile(scope, runId):
    policyContext = loadApprovedPolicies(scope)
    authoritative = readAuthoritativeSources(scope)
    discovered = discoverTargetAccountsAndPermissions(scope)

    if not discovered.isCompleteOrWithinDefinedScope():
        recordRunStatus(runId, "INCOMPLETE")
        createOwnedException("DISCOVERY_FAILED", discovered.errors)
        return INCOMPLETE

    links = correlateAccounts(authoritative, discovered.accounts)

    for each ambiguousLink in links.ambiguous:
        createOwnedException("AMBIGUOUS_LINK", ambiguousLink)
        // Không tự gán tài khoản chưa rõ chủ thể.

    desired = calculateDesiredAccess(
        authoritative,
        policyContext,
        links.verified
    )
    observed = normalizeTargetState(discovered, links.verified)

    discrepancies = compareByIdentityTargetTenantAndResource(
        desired,
        observed
    )

    for each gap in discrepancies:
        recordGap(runId, gap)
        if canAutoRemediate(gap, currentSourceVersion(), policyContext):
            task = planIdempotentChange(gap)
            executeWithAudit(task)
        else:
            routeToOwnerForReview(gap)

    refreshed = readBackAffectedTargets(discrepancies)
    verifyAgainstCurrentDesiredState(refreshed)
    return summarizedRunStatus()
~~~

**Đây là mã giả**, không phải thư viện hoặc API cụ thể. Một hệ thống thực tế phải xử lý snapshot lớn, phân trang, lịch scan, dữ liệu thiếu, phiên bản nguồn, transaction boundary, concurrency, giới hạn API, retry và bảo vệ credential.

### 15.1. Điểm cần cảnh giác trong thuật toán

- Không đưa account chưa liên kết vào phép diff của một identity tùy ý.
- Không xem tất cả quyền đang có là desired state.
- Không dùng quyền được cấp ở hệ thống A để suy luận đầy đủ quyền của hệ thống B.
- Không cấp quyền mới khi chỉ có nguồn thuộc tính cũ hoặc approval chưa có.
- Không khôi phục quyền sau khi một quyết định bảo mật/Leaver có hiệu lực.
- Không đánh dấu “khớp toàn bộ” nếu chưa có bằng chứng đầy đủ cho các đích bắt buộc.

## 16. Ví dụ SQL minh họa

Các bảng sau là **mô hình giả định**, chỉ để hiểu phép đối chiếu.

~~~text
desired_entitlements:
  identity_id, tenant_id, target_system, entitlement_id,
  desired_state, effective_from, effective_until

observed_entitlements:
  snapshot_id, identity_id, tenant_id, target_system,
  entitlement_id, observed_state, observed_at

target_snapshots:
  snapshot_id, target_system, tenant_id, collected_at,
  is_complete
~~~

### 16.1. Tìm quyền thừa trong snapshot đầy đủ

~~~sql
SELECT
    o.identity_id,
    o.tenant_id,
    o.target_system,
    o.entitlement_id,
    o.observed_at
FROM observed_entitlements AS o
JOIN target_snapshots AS s
  ON s.snapshot_id = o.snapshot_id
 AND s.target_system = o.target_system
 AND s.tenant_id = o.tenant_id
LEFT JOIN desired_entitlements AS d
  ON d.identity_id = o.identity_id
 AND d.tenant_id = o.tenant_id
 AND d.target_system = o.target_system
 AND d.entitlement_id = o.entitlement_id
 AND d.desired_state = 'PRESENT'
 AND d.effective_from <= o.observed_at
 AND (d.effective_until IS NULL OR o.observed_at < d.effective_until)
WHERE s.is_complete = TRUE
  AND o.observed_state = 'PRESENT'
  AND d.entitlement_id IS NULL;
~~~

Truy vấn này chỉ minh họa nguyên tắc **observed PRESENT nhưng không tìm thấy desired PRESENT hợp lệ cùng thời điểm và scope**. Trên hệ thống thực, dữ liệu quyền có thể phát sinh từ nhiều relationship/approval, có ngoại lệ được phép, role kế thừa hoặc account chưa nối identity, cần **tính effective entitlement đúng trước khi query**. Nếu bảng desired có trùng hoặc snapshot không có đủ coverage, kết quả sẽ chưa đáng tin.

### 16.2. Tìm quyền hợp lệ còn thiếu

~~~sql
SELECT
    d.identity_id,
    d.tenant_id,
    d.target_system,
    d.entitlement_id
FROM desired_entitlements AS d
JOIN target_snapshots AS s
  ON s.target_system = d.target_system
 AND s.tenant_id = d.tenant_id
 AND s.is_complete = TRUE
LEFT JOIN observed_entitlements AS o
  ON o.snapshot_id = s.snapshot_id
 AND o.identity_id = d.identity_id
 AND o.tenant_id = d.tenant_id
 AND o.target_system = d.target_system
 AND o.entitlement_id = d.entitlement_id
 AND o.observed_state = 'PRESENT'
WHERE d.desired_state = 'PRESENT'
  AND d.effective_from <= s.collected_at
  AND (d.effective_until IS NULL OR s.collected_at < d.effective_until)
  AND o.entitlement_id IS NULL;
~~~

Cần chọn **snapshot hoàn chỉnh mới nhất** của mỗi target/tenant trong khoảng chấp nhận; truy vấn đơn giản phía trên có thể sinh nhiều dòng do nhiều snapshot và không thay thế xử lý **độ mới, group inheritance hoặc trạng thái account bị khóa**.

### 16.3. Không tìm được trong desired chưa đủ chứng minh quyền sai

Các câu SQL minh họa sử dụng assumption rằng desired store đã phản ánh **đầy đủ tất cả entitlement hợp lệ**. Nếu desired store thiếu quyền ngoại lệ được phê duyệt hoặc một nhóm quyền chưa được import, hệ thống phải phân loại là **thiếu dữ liệu quản trị** hoặc cần review, không lập tức thu hồi hàng loạt.

## 17. Tình huống thực tế: một Mover, một Leaver và tài khoản ngoài luồng

### 17.1. Mover để lại quyền cũ

Nhân viên **Lan** chuyển từ Customer Support sang Finance ngày 20/11/2026. Nguồn HRIS đã cập nhật, IGA yêu cầu gỡ CRM-Support và cấp ERP-InvoiceRead. ERP thành công, CRM báo 429 và chưa gỡ role.

| Kiểm tra | Desired | Observed lúc 08:10 | Kết quả |
| --- | --- | --- | --- |
| IdP department | Finance | Finance | MATCH |
| ERP InvoiceRead | PRESENT | PRESENT | MATCH |
| CRM SupportReader | ABSENT | PRESENT | EXTRA_ACCESS |
| VPN Basic | PRESENT | PRESENT | MATCH |

Reconciliation mở discrepancy **EXTRA_ACCESS**, lưu effectiveAt, target, lỗi và owner. Sau retry, CRM trả role absent và IAM đọc lại ở 08:18. **Thời gian từ lúc Mover hiệu lực đến lúc xác minh thu hồi** được ghi cho chỉ số residual access.

### 17.2. Leaver còn tài khoản SaaS

Nhân viên **Minh** nghỉ từ 18:00. IdP đã disabled lúc 18:00, nhưng một ứng dụng SaaS chỉ được gắn SSO và chưa từng tích hợp API deprovision. Reconciliation phát hiện account local vẫn enabled cùng nhóm quyền cũ.

Cần xử lý qua connector hoặc tác vụ thủ công có owner, kiểm tra phiên/token theo khả năng ứng dụng, sau đó xác minh account và entitlement. Không được kết luận Leaver hoàn tất chỉ vì trạng thái IdP đã chính xác.

### 17.3. Account không có chủ thể rõ ràng

Trong đợt quét hệ thống Git xuất hiện account **legacy-ops-17**, không có account link với identity nào. Đội vận hành không nên xóa ngay account này chỉ vì không tìm thấy mã nhân sự: có thể đó là service account của hệ thống tích hợp hoặc tài khoản break-glass có quy trình riêng.

Reconciliation đánh dấu **UNLINKED_ACCOUNT**, hạn chế rủi ro nếu cần theo playbook, yêu cầu xác định owner/mục đích và truy vết nguồn tạo. Nếu không có cơ sở nghiệp vụ hợp lệ và có thẩm quyền thu hồi, hệ thống mới thực hiện vô hiệu hóa theo quy trình an toàn.

### 17.4. Điều gì khiến ba tình huống khác nhau?

Tình huống Mover có **identity link rõ, desired rõ, observed sai**: thích hợp cho remediation có kiểm soát. Tình huống Leaver có **đường truy cập chưa được quản lý bởi IdP**: cần mở rộng coverage. Tình huống Git có **owner chưa rõ**: điều tra trước khi quyết định xóa.

Cùng được gọi là reconciliation, nhưng **cách khắc phục phụ thuộc loại sai lệch, dữ liệu đã xác minh và mức rủi ro**.

## 18. Audit, bảo mật và quyền riêng tư

Một run reconciliation nên lưu:

| Nhóm bằng chứng | Nội dung cần có |
| --- | --- |
| **Phạm vi** | Run ID, target, tenant, tài nguyên, bộ lọc, thời điểm quét |
| **Nguồn** | Authoritative source, source version, policy/approval version |
| **Chất lượng quan sát** | Phân trang, độ mới, completeness, error của connector |
| **Liên kết danh tính** | identityId, targetAccountId, kết quả correlation, ngoại lệ |
| **Sai lệch** | Desired/observed, loại gap, mức rủi ro, effectiveAt |
| **Xử lý** | Người phê duyệt, tác vụ, request ID, retry, trạng thái |
| **Xác minh** | Snapshot đọc lại, verifiedAt, kết quả cuối và giới hạn bằng chứng |
| **Truy vết** | Correlation ID nối JML event, policy, provisioning, reconciliation |

**Không ghi mật khẩu, token, private key, recovery code hoặc thông tin giấy tờ định danh đầy đủ** vào log. Nên dùng identityId và reference bảo vệ để giảm sao chép dữ liệu nhân sự.

Hệ thống reconciliation thường sở hữu connector có quyền đọc rộng hoặc quyền quản trị nhiều ứng dụng; cần:

- Tách **quyền đọc để phát hiện** và **quyền ghi để sửa** nếu kiến trúc cho phép.
- Dùng service identity có owner, quyền tối thiểu và credential được quản lý an toàn.
- Bảo vệ log và snapshot khỏi chỉnh sửa trái phép, có kiểm soát truy cập và retention phù hợp.
- Giám sát việc chạy sai phạm vi, việc thu thập dữ liệu cá nhân quá mức và thao tác khắc phục hàng loạt.
- Áp dụng approval hoặc kiểm soát giới hạn thay đổi cho remediation rủi ro cao.

## 19. Chỉ số vận hành và chất lượng reconciliation

| Chỉ số | Định nghĩa cần làm rõ | Giá trị |
| --- | --- | --- |
| **Coverage** | Tỷ lệ target/tenant/account nằm trong phạm vi đã quét và có thể đọc | Biết còn điểm mù ở đâu |
| **Inventory completeness** | Phần dữ liệu được xác nhận thu đủ theo cơ chế đích | Tránh suy luận sai từ snapshot thiếu |
| **Freshness** | Độ tuổi snapshot/nguồn so với giới hạn chấp nhận | Phát hiện dữ liệu cũ |
| **Match rate** | Tỷ lệ account/permission khớp desired trong scope đủ điều kiện | Theo dõi mức sai lệch |
| **Unlinked account count** | Số tài khoản chưa nối được identity/owner hợp lệ | Giảm vùng ngoài governance |
| **Extra access count** | Số quyền thừa đã xác định với bằng chứng đủ | Đo privilege creep/residual access |
| **Missing access count** | Số quyền hợp lệ còn thiếu | Đo chất lượng onboarding |
| **Time to detect** | Từ thời điểm quyền sai có thể bắt đầu đến khi phát hiện | Đánh giá tốc độ giám sát |
| **Time to remediate** | Từ lúc phát hiện đến verifiedAt của sửa đổi | Đánh giá hiệu quả xử lý |
| **Leaver deprovision latency** | Từ effectiveAt Leaver đến verifiedAt quyền bị thu hồi | Đo khoảng quyền có thể tồn dư |
| **Overdue exceptions** | Sai lệch chưa xử lý sau deadline policy | Tập trung rủi ro tồn đọng |
| **False positive rate** | Sai lệch bị kết luận nhầm do dữ liệu/semantics | Cải thiện chất lượng mapping |
| **Service identity ownership** | Tỷ lệ workload/connector có owner còn hiệu lực | Giảm principal không người chịu trách nhiệm |

**Không dùng match rate cao để che lấp một quyền đặc quyền thừa.** Một sai lệch tài khoản admin production có thể nguy hiểm hơn hàng trăm quyền phổ thông chưa cấp. Dashboard nên phân loại theo **mức rủi ro, hệ thống, trạng thái Leaver, độ mới và độ đầy đủ dữ liệu**.

## 20. Bảng kiểm tra triển khai reconciliation

| Câu hỏi | Kết quả cần có |
| --- | --- |
| Đã xác định các nguồn có thẩm quyền cho nhân viên, nhà thầu, service identity chưa? | Data ownership và quy tắc rõ theo từng thuộc tính |
| Có định nghĩa desired state độc lập với observed state không? | Policy RBAC/ABAC, approval và ngày hiệu lực |
| Có bản đồ identity–account theo tenant ổn định không? | ID liên kết, trường hợp trùng và ngoại lệ được xử lý |
| Có phát hiện account chưa có owner không? | Inventory và quy trình account correlation |
| Connector có đọc đủ user, group và quyền ứng dụng không? | Capability matrix và giới hạn rõ ràng |
| Có kiểm tra completeness và độ mới snapshot không? | UNKNOWN khi không thể quan sát |
| Có phân biệt account status, entitlement và session không? | Mô hình nhiều lớp, không kết luận sai từ IdP |
| Có phát hiện quyền thừa sau Mover không? | Desired–observed diff, quyền cũ được thu hồi |
| Có kiểm tra account và quyền của Leaver trên mọi hệ thống trong scope không? | Bằng chứng deprovision theo từng đích |
| Có xử lý nhiều employment relationships không? | Quyền theo quan hệ, không khóa nhầm toàn bộ |
| Có kiểm soát role trực tiếp, group kế thừa và ABAC không? | Phân tích quyền hiệu lực phù hợp |
| Có chống sự kiện lặp, trễ và tác vụ cũ không? | Idempotency, version guard và current-state check |
| Sai lệch được phân loại theo rủi ro chưa? | Priority, owner, deadline, escalation |
| Auto-remediation có đủ căn cứ không? | Verified link, policy, approval, hạn chế tác động hàng loạt |
| Có xác minh lại sau remediation không? | Readback, verifiedAt và audit |
| Tài khoản dịch vụ có chủ sở hữu hợp lệ không? | Service registry, owner transfer, credential review |
| Có bảo vệ credential connector và dữ liệu snapshot không? | Least privilege, secret management, retention |
| Có đủ bằng chứng để giải thích kết quả “MATCH” hoặc “UNKNOWN” không? | Run ID, scope, timestamp, completeness và nguồn |

## 21. Những nhầm lẫn thường gặp

1. **“SCIM đồng bộ thành công tức là mọi quyền đã đúng.”** Phải đọc lại group/role/entitlement ở hệ thống đích và kiểm tra những quyền ngoài phạm vi SCIM.
2. **“IdP đã disabled nên Leaver hoàn tất.”** Ứng dụng có thể còn local account, phiên hoặc token độc lập.
3. **“Không thấy account trong API nghĩa là account không tồn tại.”** API có thể thiếu trang, thiếu quyền hoặc timeout.
4. **“Tài khoản unmatched chắc chắn là tài khoản mồ côi, nên xóa ngay.”** Cần xác định owner, loại account và cơ sở nghiệp vụ.
5. **“Desired access bằng tất cả quyền đang có.”** Desired phải được tính từ nguồn và chính sách được chấp thuận.
6. **“Chỉ cần cấp role mới sau Mover.”** Phải gỡ quyền cũ không còn phù hợp.
7. **“Quyền nhóm IdP giống quyền hiệu lực ở mọi ứng dụng.”** Mapping, role cục bộ, token, ACL và ABAC có thể khác.
8. **“Reconciliation tự động luôn an toàn.”** Dữ liệu hoặc account linking sai có thể khiến sửa nhầm hàng loạt.
9. **“Một snapshot đủ cho mọi điều tra.”** Cần dấu thời gian, scope, lịch sử thay đổi và bằng chứng quyền thực tế.
10. **“Reconciliation chỉ chạy khi người dùng báo lỗi.”** Cần kết hợp sau JML, theo sự kiện, định kỳ và theo rủi ro.

## 22. Câu hỏi tự đánh giá

1. Reconciliation khác provisioning ở điểm nào? Một response HTTP thành công đã đủ để xác nhận quyền đúng chưa?
2. Vì sao cần tách **authoritative**, **desired**, **observed** và **effective** state?
3. An chuyển từ Support sang Finance và đã nhận FinanceReader nhưng vẫn có SupportReader. Loại discrepancy nào phát sinh?
4. Tại sao không nên dùng email làm khóa duy nhất để đối soát tài khoản giữa HRIS, IdP và SaaS?
5. Một connector đọc thất bại 2/5 trang users. Có được kết luận những người không xuất hiện đã bị xóa không? Cần ghi trạng thái nào?
6. Khi SCIM User.active = false, những đường truy cập nào vẫn cần đánh giá riêng?
7. Một người kết thúc hợp đồng với pháp nhân A nhưng vẫn làm ở B. Vì sao không được mặc định khóa mọi account?
8. Một account Git chưa có identityId. Cần làm gì trước khi quyết định xóa?
9. Tại sao policy ABAC có thể ra quyết định sai dù role RBAC đang đúng?
10. Nếu remediation đã cấp role mới nhưng nguồn HRIS vừa phát Leaver, biện pháp nào ngăn role bị phục hồi?
11. Khi owner một service principal nghỉ việc, reconciliation nên đánh giá mối quan hệ và credential nào?
12. Những chỉ số và bằng chứng nào chứng minh Leaver được thu hồi đủ tại các hệ thống trong scope?

## 23. Ghi nhớ

**Reconciliation là vòng kiểm soát kiểm tra trạng thái tài khoản và quyền thực tế có khớp trạng thái được phép hay không.** Nó đòi hỏi **nguồn có thẩm quyền, danh tính liên kết chính xác, desired state từ policy/phê duyệt, observed state đủ mới và đủ phạm vi, phép so sánh, xử lý sai lệch và đọc lại bằng chứng**.

Trong vòng đời **Joiner–Mover–Leaver**, reconciliation phát hiện account chưa được tạo khi Joiner, quyền cũ chưa thu hồi khi Mover, và tài khoản/phiên/tài nguyên còn đường truy cập khi Leaver. **IdP/SSO, SCIM/API, RBAC/ABAC, quản trị service identities và audit** đóng vai trò khác nhau nên không được dùng kết quả của một lớp để suy diễn toàn bộ hệ thống. Việc phân biệt **MATCH, DISCREPANCY và UNKNOWN**, khắc phục theo mức rủi ro và xác minh lại là nền tảng để giảm **tài khoản mồ côi, quyền tích lũy và quyền truy cập tồn dư**.
