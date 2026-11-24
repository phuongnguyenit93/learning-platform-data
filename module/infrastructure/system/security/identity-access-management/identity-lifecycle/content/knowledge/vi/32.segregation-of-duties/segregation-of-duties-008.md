# Phê duyệt ngoại lệ SoD: chấp nhận rủi ro có điều kiện và thu hồi đúng hạn trong IAM

**Phê duyệt ngoại lệ** (*Segregation of Duties exception approval*) là cơ chế quản trị **một tình huống xung đột phân tách nhiệm vụ (SoD)** mà tổ chức **không thể loại bỏ ngay bằng thiết kế role, phân công nhân sự hoặc quy trình thông thường**, nhưng vẫn có lý do nghiệp vụ được xem xét. Ngoại lệ chỉ có thể được chấp nhận khi **chính sách cho phép**, có **người có thẩm quyền chịu trách nhiệm**, đánh giá **rủi ro còn lại**, quy định **phạm vi, thời hạn và kiểm soát bù trừ**, đồng thời có **giám sát, tái đánh giá và cơ chế kết thúc**.

Ví dụ, tại một nhóm vận hành nhỏ, một kỹ sư có thể tạm thời cần vừa sửa cấu hình vừa thực hiện thao tác triển khai khẩn cấp. Nếu chính sách thông thường yêu cầu người sửa và người phê duyệt release là **hai người độc lập**, việc giao cả hai quyền cho cùng kỹ sư tạo xung đột SoD. Một lời nhắn “quản lý đã đồng ý” không đủ làm ngoại lệ hợp lệ. Tổ chức có thể phải chỉ định **người phê duyệt độc lập từ đội khác**, giới hạn quyền ở **một dịch vụ, một incident, một phiên JIT ngắn**, yêu cầu kiểm tra log và tự động thu hồi. Nếu quy định áp dụng **cấm tuyệt đối cùng một người thực hiện hai bước**, thì **không có ngoại lệ nội bộ nào được phép bỏ qua yêu cầu đó**; phải thiết kế phương án khác.

Bài thuộc chương **Segregation of duties** trong module **Identity and Access Management (IAM) — Identity Lifecycle**, theo mô hình **Joiner–Mover–Leaver (JML)**. Nội dung kết nối **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM/JIT, kiểm toán và giảm quyền truy cập tồn dư**. Trọng tâm không chỉ là “ai ký ngoại lệ”, mà còn là **ngoại lệ được áp ở đâu, điều kiện nào còn hiệu lực, quyền thực tế có vượt phạm vi hay không, hết hạn đã thực sự bị chặn chưa**.

> **Nguyên tắc:** **Ngoại lệ SoD là quyết định rủi ro có giới hạn**, không phải nút “bỏ qua kiểm tra SoD” cho mọi ứng dụng. Một ngoại lệ được phê duyệt **không tự cấp quyền**, không thay thế xác thực/ủy quyền tại tài nguyên, không hợp thức hóa vi phạm quy định bắt buộc và **không được tiếp tục sống sau khi căn cứ nghiệp vụ hết hiệu lực**.

## 1. SoD bảo vệ điều gì?

**Segregation of Duties (SoD)**, hay **phân tách nhiệm vụ**, nhằm ngăn một chủ thể có khả năng **tự hoàn thành toàn bộ một chuỗi hành động nhạy cảm** mà không có kiểm tra độc lập. SoD giảm rủi ro gian lận, sai sót không bị phát hiện, thay đổi hệ thống không được kiểm tra và che giấu dấu vết.

Một số cặp trách nhiệm có thể xung đột tùy chính sách:

| Nhiệm vụ A | Nhiệm vụ B | Rủi ro cần xét |
| --- | --- | --- |
| Tạo yêu cầu thanh toán | Phê duyệt chính yêu cầu thanh toán đó | Tự lập và tự duyệt khoản chi. |
| Tạo nhà cung cấp | Thay đổi tài khoản ngân hàng và giải ngân cho nhà cung cấp | Có thể chuyển tiền trái thẩm quyền. |
| Sửa mã nguồn production | Tự phê duyệt triển khai thay đổi đó | Bỏ qua kiểm tra độc lập. |
| Gán role admin | Phê duyệt yêu cầu admin của chính mình | Tự nâng quyền truy cập. |
| Quản lý tài khoản | Xóa/chỉnh sửa audit log về việc quản lý đó | Có thể che giấu hành động. |
| Tạo bản ghi kiểm toán | Tự xác nhận hoàn tất kiểm toán | Không còn tính độc lập của việc đối chiếu. |
| Thay đổi cấu hình security policy | Tự chấp nhận ngoại lệ của chính thay đổi | Vô hiệu hóa kiểm soát mà không có reviewer độc lập. |

**Không phải mọi cặp trong bảng luôn bị cấm trong mọi môi trường.** Cần xác định **quy trình, đối tượng dữ liệu, mức độ nhạy cảm và ma trận SoD đã được chủ sở hữu chính sách phê duyệt**. Ví dụ, xem báo cáo và sửa nhãn hiển thị có thể không cần tách; nhưng tạo thanh toán và phê duyệt **cùng khoản thanh toán** thường là kiểm soát then chốt.

### 1.1. SoD khác Least Privilege như thế nào?

- **Least privilege** đặt câu hỏi: “Chủ thể cần **bao nhiêu quyền** để làm đúng nhiệm vụ?”
- **SoD** đặt câu hỏi: “Chủ thể có đang giữ hoặc sử dụng **tổ hợp quyền/trách nhiệm** tạo xung đột không?”
- **Approval workflow** đặt câu hỏi: “Ai có **thẩm quyền đưa ra quyết định** cho yêu cầu và rủi ro này?”
- **Audit/reconciliation** đặt câu hỏi: “Điều kiện và quyết định đó **có được áp dụng thực tế** ở hệ thống đích không?”

Có thể một người chỉ giữ **hai quyền**, nhưng hai quyền ấy đủ để tự tạo và tự duyệt giao dịch — vẫn vi phạm SoD. Ngược lại, một người giữ nhiều quyền chỉ đọc có thể không tạo xung đột SoD, dù vẫn cần rà soát least privilege.

### 1.2. Ngoại lệ khác việc sửa chính sách chuẩn

Một **exception** cho phép một trường hợp cụ thể được xử lý khác baseline **trong giới hạn chính sách ngoại lệ**. Một **policy change** thay đổi ma trận xung đột hoặc điều kiện áp cho nhiều identity/resource. Không nên dùng ngoại lệ cho hàng trăm người để lách một chính sách cũ; nếu việc ngoại lệ thành phổ biến, cần đánh giá **mô hình SoD và cấu trúc công việc** bằng quy trình thay đổi chính sách độc lập.

## 2. Static SoD, Dynamic SoD và SoD theo giao dịch

Để phê duyệt ngoại lệ đúng, trước hết phải biết **kiểm soát nào đang bị xung đột**.

| Cơ chế | Câu hỏi kiểm soát | Ví dụ |
| --- | --- | --- |
| **Static SoD (SSD)** | Người dùng có được **được gán/được ủy quyền** đồng thời các role xung đột không? | Không gán cùng lúc `PaymentCreator` và `PaymentApprover` theo policy. |
| **Dynamic SoD (DSD)** | Người dùng có được **kích hoạt đồng thời** các role xung đột trong cùng session/ngữ cảnh không? | Hai vai trò có thể tồn tại nhưng không được active cùng lúc. |
| **Transaction-level SoD** | Chủ thể có được thực hiện bước B trên **chính giao dịch đã làm bước A** không? | Người tạo hóa đơn không được duyệt chính hóa đơn đó. |
| **Workflow/approval SoD** | Người yêu cầu, người phê duyệt và người triển khai quyền có độc lập theo yêu cầu không? | Beneficiary không tự duyệt ngoại lệ SoD của mình. |
| **Administrative SoD** | Người quản trị role/SoD policy có tự bỏ kiểm soát rồi xóa log được không? | Tách quyền sửa policy và quyền audit/exception approval. |

### 2.1. SSD không chỉ kiểm tra role gán trực tiếp

~~~text
FinanceSuperUser >= PaymentCreator
FinanceSuperUser >= PaymentApprover

User assignments:
  person-2048 -> FinanceSuperUser
~~~

Một kiểm tra chỉ hỏi “có gán trực tiếp `PaymentCreator` và `PaymentApprover` hay không?” sẽ bỏ sót xung đột **thông qua senior role**. Cần tính **role hierarchy closure, multiple inheritance, direct grants và effective permissions**. Thực hiện điều này trước khi xin ngoại lệ; nếu đồ thị role sai, cách khắc phục có thể là **sửa role design** thay vì phê duyệt ngoại lệ.

### 2.2. DSD chưa đủ nếu một senior role đã chứa cả hai permission

Giả sử policy cấm kích hoạt hai role xung đột trong cùng phiên, nhưng một senior role duy nhất đã kế thừa cả hai permission. Chỉ giới hạn tên role active có thể không chặn được người dùng thực hiện hai thao tác. Phải đánh giá **ngữ nghĩa kế thừa/activation thực tế của authorization engine** và đặt kiểm soát ở nơi hành động được thực thi.

### 2.3. Transaction-level SoD thường phải đặt tại ứng dụng

Trong thanh toán:

~~~text
allowApprove(payment, subject) =
    subject.hasPermission("payment:approve")
    AND subject.accountActive
    AND payment.status == "PENDING_APPROVAL"
    AND payment.createdByIdentityId != subject.identityId
    AND payment.tenantId == subject.tenantId
~~~

Đây là **pseudocode khái niệm**. `createdByIdentityId` phải được hệ thống ghi nhận đáng tin, không do client tự sửa. **Ngoại lệ cho việc cùng nắm hai role** không tự bỏ qua điều kiện **người tạo khác người duyệt trên cùng giao dịch** nếu đó là điều kiện bắt buộc.

## 3. Khi nào có thể xem xét ngoại lệ SoD?

Không phải cứ người dùng cần hai role là phải duyệt ngoại lệ. Cần xác định **phương án không xung đột** trước.

| Tình huống | Nên xem xét điều gì? |
| --- | --- |
| Nhóm nhỏ thiếu người phê duyệt độc lập trong thời gian ngắn. | Có thể nhờ owner từ đơn vị khác, dùng remote approval hoặc temporary delegated checker? |
| Sự cố production cần hành động ngay. | Có JIT/PAM, ticket incident, người giám sát độc lập, emergency workflow phù hợp không? |
| Chuyển giao nhiệm vụ giữa hai vai trò. | Có thể thu hồi quyền cũ trước khi cấp quyền mới, hoặc scope overlap chỉ đọc không? |
| Role chuẩn gom quyền không cần thiết. | Có thể split role/JEA, bỏ inheritance sai thay vì ngoại lệ? |
| Một workload phải đọc và ghi nhiều hệ thống. | Có thể tách service identities/credentials theo tác vụ không? |
| Quy trình kiểm soát có bước phê duyệt rất chậm. | Có alternate approver, delegation đúng authority hoặc cải tiến workflow không? |
| Yêu cầu pháp lý/chính sách bắt buộc tách hai người. | Không tự cấp ngoại lệ vượt yêu cầu; phải dùng người/luồng độc lập hợp lệ. |

### 3.1. Thứ tự ưu tiên xử lý

1. **Loại bỏ xung đột** bằng phân công người khác hoặc tách role/permission.
2. **Giới hạn hành động và tài nguyên** để các quyền không còn xung đột trong cùng phạm vi.
3. **Tách thời gian/session** nếu DSD và semantics hệ thống thực sự bảo vệ được.
4. **Dùng workflow có người kiểm soát độc lập** hoặc cơ chế dual control phù hợp.
5. Chỉ khi vẫn còn rủi ro cần chấp nhận và **chính sách cho phép**, tạo **exception với điều kiện bù trừ và expiry**.

Không được dùng một exemption flag toàn cục như `ignoreSoD=true` cho tài khoản chỉ vì nhu cầu thao tác nhanh.

### 3.2. Trường hợp phải từ chối

**Không phê duyệt** khi:
- Yêu cầu vi phạm quy định/phân tách bắt buộc mà tổ chức **không có thẩm quyền miễn trừ**.
- Không xác định được beneficiary, account, target hoặc permission đang xung đột.
- Người đề nghị không có business need hợp lệ hoặc đã là Leaver.
- Không có risk owner có thẩm quyền hoặc người duyệt không độc lập theo policy.
- Ngoại lệ không có giới hạn thời gian/phạm vi đối với quyền nhạy cảm mà policy yêu cầu.
- Không có kiểm soát bù trừ phù hợp cho rủi ro còn lại.
- Không có khả năng giám sát, thu hồi hoặc chứng minh việc sử dụng.
- Biện pháp thực tế là tắt authorization/monitoring cho cả hệ thống.

**Một cấp quản lý ký tên không biến trường hợp bị cấm thành được phép.**

## 4. Ai chịu trách nhiệm trong approval ngoại lệ?

### 4.1. Các vai trò nên tách biệt

| Chủ thể | Trách nhiệm | Không được mặc định |
| --- | --- | --- |
| **Requester** | Đề xuất nhu cầu, nhiệm vụ, duration và phương án thay thế đã xét. | Có quyền phê duyệt chính mình. |
| **Beneficiary** | Người/workload thực sự nhận hoặc sử dụng quyền xung đột. | Requester và beneficiary luôn trùng. |
| **Line manager / sponsor** | Xác nhận nhiệm vụ và quan hệ công việc. | Có quyền chấp nhận mọi rủi ro dữ liệu hoặc hệ thống. |
| **Application/resource owner** | Xác nhận tài nguyên/action/role và ảnh hưởng vận hành. | Có thể tự miễn trừ chính sách SoD của Security. |
| **Risk/control owner** | Quyết định rủi ro còn lại có thể chấp nhận trong thẩm quyền hay không. | Được bỏ mọi quy định pháp lý hoặc tự phê duyệt ngoại lệ của mình. |
| **Security/IGA/SoD governance** | Đánh giá xung đột, kiểm soát bù trừ, cách enforcement và policy compliance. | Thay thế nhu cầu nghiệp vụ. |
| **Implementer/provisioner** | Cấp quyền đúng scope và hạn theo quyết định, có audit. | Được tự thay đổi phạm vi đã duyệt. |
| **Independent monitor/reviewer** | Giám sát, đối soát giao dịch và báo cáo sai lệch. | Đồng thời là người được ngoại lệ tự xác nhận đã tuân thủ. |
| **Auditor** | Đánh giá bằng chứng và tính tuân thủ của quy trình. | Tham gia phê duyệt vận hành hằng ngày trong mọi trường hợp. |

Chức năng có thể do cùng một nhóm đảm nhiệm tùy quy mô tổ chức, **nhưng ràng buộc độc lập** cần được giữ ở những bước policy yêu cầu.

### 4.2. No-self-approval ở mức person identity

Hai account `lan-user` và `lan-admin` có thể liên kết với **cùng IAM person identity**. Nếu Lan là beneficiary thì không thể dùng `lan-admin` để phê duyệt ngoại lệ của chính Lan nếu chính sách yêu cầu người độc lập. Cần đối chiếu **identity binding**, không chỉ account name/email.

### 4.3. Manager không mặc nhiên là risk owner

Manager xác nhận một nhân viên đang chịu trách nhiệm dự án; nhưng rủi ro đối với giao dịch tài chính, dữ liệu nhạy cảm hoặc control plane phải do **người có authority phù hợp** quyết định. Một ngoại lệ có thể cần **business owner AND resource owner AND security/risk acceptance**; số cấp và quyền veto phụ thuộc policy.

### 4.4. Quyền sửa exception policy cũng là đặc quyền

Một quản trị viên không nên được tự ý:
- Chỉnh danh sách role conflict.
- Bỏ required reviewer trong routing.
- Thay `expiresAt` của ngoại lệ đã duyệt.
- Sửa beneficiary/tenant/role sau approval.
- Đánh dấu `VERIFIED` khi target chưa đọc lại.
- Xóa log tạo/thu hồi exception.

Các thao tác này cần access control, change review, logging và phân tách người theo rủi ro.

## 5. Hồ sơ ngoại lệ phải mô tả đúng xung đột

Một request chất lượng không chỉ ghi “Cần hai role để làm việc”.

| Thuộc tính | Ví dụ và ý nghĩa |
| --- | --- |
| `exceptionId` / `requestVersion` | Định danh ổn định, phiên bản được phê duyệt. |
| `beneficiaryIdentityId` | IAM identity của người/workload hưởng ngoại lệ. |
| `targetAccountId` | Liên kết tới đúng account tại ứng dụng đích. |
| `targetSystem` / `tenant` | Nơi có conflict và phạm vi tổ chức. |
| `conflictRuleId` | Rule SoD bị kích hoạt, owner và policy version. |
| `conflictingPermissions` | Hai/nhóm quyền nào tạo xung đột thực tế. |
| `grantPaths` | Role trực tiếp, kế thừa, group, direct grants, PAM activation. |
| `businessPurpose` | Nhiệm vụ, change/incident hoặc yêu cầu hợp lệ. |
| `alternativesConsidered` | Vì sao không thể tách quyền, người, nhiệm vụ. |
| `requestedScope` | Tài nguyên/action/transaction được ngoại lệ. |
| `validFrom` / `validUntil` | Mốc bắt đầu và kết thúc, kể cả múi giờ. |
| `riskRating` / `residualRisk` | Mức rủi ro trước/sau các biện pháp kiểm soát. |
| `compensatingControls` | Kiểm soát cụ thể, owner, bằng chứng áp dụng. |
| `approverDecisions` | Ai chấp nhận rủi ro, authority, thời điểm, version. |
| `monitoringPlan` | Ai kiểm tra, kiểm tra gì, tần suất, cảnh báo. |
| `revocationPlan` | Gỡ role/activation/credential/session bằng cách nào. |
| `verificationCriteria` | Điều kiện chứng minh ngoại lệ chỉ đúng scope và đã hết hạn. |

### 5.1. Exception scope phải chặt

So sánh:

~~~text
Không đủ:
  User: Lan
  Reason: công việc khẩn
  Permission: Admin
  End: không xác định
  Approver: Manager

Cụ thể hơn:
  Beneficiary: person-2048
  Role conflict: deploy:execute AND deploy:approve
  Target: production / tenant-vn / service-catalog
  Incident: INC-2026-482
  Approved action: restart one service
  Valid from/until: 2026-12-02T10:00:00+07:00
                    2026-12-02T10:45:00+07:00
  Independent checker: person-901
  Required monitoring: session + ticket + post-action review
  Revocation: PAM grant + target session/token check
~~~

Đây là **dữ liệu minh họa**, không phải yêu cầu mọi sản phẩm phải có đúng fields. Ngay cả phiên bản “cụ thể hơn” cũng **chỉ được phép** nếu nó đáp ứng SoD policy của doanh nghiệp và không bỏ qua kiểm soát bắt buộc.

### 5.2. Phân biệt exception cho role assignment và exception cho transaction

Một approval cho người dùng **được giữ cả hai role** theo scope/time không tự đồng nghĩa được phép **tự duyệt mọi giao dịch**. Cần ghi rõ loại ngoại lệ:
- Assignment-level/SSD exception.
- Activation-level/DSD exception.
- Transaction-level exception (nếu chính sách cho phép).
- Policy/procedure exception có kiểm soát độc lập.

Thực thi cần đúng loại; không được dùng một record `exceptionApproved=true` chung để bypass mọi lớp.

## 6. Phân tích rủi ro trước khi cấp ngoại lệ

Một bản đánh giá cần trình bày **rủi ro vốn có (inherent risk)** và **rủi ro còn lại (residual risk)** sau kiểm soát bù trừ.

### 6.1. Những câu hỏi quan trọng

1. Chủ thể có thể tự tạo, tự duyệt, tự thực thi hoặc tự che giấu hành động không?
2. Xung đột ảnh hưởng dữ liệu, tiền, IAM control plane, production hay audit trail?
3. Đường tăng quyền gián tiếp nào có thể khiến scope thực tế lớn hơn request?
4. Nếu credential/session bị chiếm dụng, mức thiệt hại tối đa là gì?
5. Ngoại lệ cần bao lâu và có thể chia thành nhiều phiên ngắn hơn không?
6. Kiểm soát bù trừ **ngăn ngừa** hay chỉ **phát hiện sau**?
7. Người giám sát có độc lập, đủ khả năng và được thông báo đúng thời điểm?
8. Thiếu người/owner hoặc hệ thống monitoring lỗi thì quyền xử lý ra sao?
9. Có nghĩa vụ pháp lý/hợp đồng không cho phép miễn trừ không?
10. Làm sao kiểm chứng ngoại lệ đã **hết hiệu lực** và không tự được re-provision?

### 6.2. Ma trận định tính minh họa

| Điều kiện | Rủi ro có thể cao | Khả năng giảm |
| --- | --- | --- |
| Scope | Toàn tổ chức, nhiều tenant, mọi giao dịch. | Một tài nguyên, một transaction, một service. |
| Permission | Cấp admin, giải ngân, sửa audit log. | Chỉ đọc, restart hẹp, action giới hạn. |
| Thời gian | Quyền tồn tại vô hạn. | JIT 30–60 phút, expiry enforced. |
| Người kiểm soát | Beneficiary tự duyệt hoặc tự xem log. | Reviewer độc lập, dual control. |
| Khả năng giám sát | Log có thể bị sửa/xóa bởi người được ngoại lệ. | Log tập trung, chống sửa đổi, cảnh báo độc lập. |
| Credential/session | Long-lived key, local admin không quản lý. | Short-lived credential và brokered session. |
| Chính sách | Conflict không có owner, risk unclear. | Rule rõ, approved route và monitoring plan. |

Không có công thức điểm rủi ro chung đúng cho mọi tổ chức. **Người có authority cần ký vào rủi ro còn lại** theo thang và ngưỡng nội bộ, không chỉ gán nhãn “LOW” do requester tự điền.

### 6.3. Kiểm tra tác động của role hierarchy

~~~text
Role A: FinanceSuperUser
  inherits PaymentCreator
  inherits PaymentApprover

Direct assignments:
  person-2048 -> FinanceSuperUser

Effective conflict:
  payment:create
  payment:approve
~~~

Nếu một senior role làm phát sinh xung đột cho hàng trăm user, **không nên cấp hàng trăm ngoại lệ** như phương án mặc định. Hãy đánh giá sửa **role hierarchy** hoặc tách assignment tại nguồn, với impact analysis toàn bộ affected users.

## 7. Compensating controls: kiểm soát bù trừ không phải lời hứa

**Compensating control** là kiểm soát thay thế/bổ sung nhằm giảm rủi ro khi kiểm soát SoD chuẩn không thể áp dụng nguyên trạng trong phạm vi ngoại lệ được phép. Nó phải có **thiết kế, chủ sở hữu, tần suất, enforcement và bằng chứng vận hành**.

| Kiểm soát | Loại | Giá trị | Hạn chế |
| --- | --- | --- | --- |
| **Dual authorization** | Preventive | Cần người thứ hai phê duyệt trước hành động nhạy cảm. | Phải thực sự enforce, không chỉ mô tả trong ticket. |
| **Transaction-level maker–checker** | Preventive | Ngăn tự duyệt giao dịch do chính actor tạo. | Không tự hạn chế khả năng giữ cả hai role nếu SSD cấm. |
| **JIT/PAM time-bound elevation** | Preventive / exposure reduction | Giảm thời gian privilege khả dụng. | Token/session có thể còn sống sau expiry. |
| **JEA/scoped permission** | Preventive | Chỉ cho đúng action/resource. | Phải kiểm thử đường nâng quyền gián tiếp. |
| **Independent daily reconciliation** | Detective | Phát hiện giao dịch/grant bất thường. | Chỉ phát hiện sau, khó ngăn thiệt hại đã xảy ra. |
| **Real-time alerting** | Detective / response | Cảnh báo hành động xung đột và sự cố. | Cần người xử lý, SLA và log đáng tin. |
| **Immutable/separate audit logs** | Detective/evidence | Ngăn beneficiary tự che giấu dấu vết. | Log không tự chặn thao tác. |
| **Approval per transaction** | Preventive | Kiểm soát từng khoản thanh toán hoặc release. | Owner phải được xác minh và có đủ authority. |
| **Limits/quotas** | Preventive | Giảm giá trị hoặc số lượng thao tác được phép. | Không chặn mọi dạng gian lận chia nhỏ giao dịch. |
| **Periodic access recertification** | Detective/governance | Phát hiện ngoại lệ kéo dài hoặc drift. | Không thay kiểm tra runtime cho giao dịch nhạy cảm. |

### 7.1. Kiểm soát phải độc lập với người có xung đột

Nếu Lan có cả quyền sửa giao dịch và quyền xóa log, yêu cầu Lan **tự xem log cuối ngày và tự ký xác nhận** không phải một compensating control độc lập. Cần người/hệ thống khác có authority, có quyền truy cập log đáng tin và **không bị Lan sửa/silence**.

### 7.2. Detective control chưa chắc đủ để chấp nhận rủi ro

**Session recording, alerting hoặc kiểm toán sau 24 giờ** có thể giúp phát hiện và điều tra, nhưng **không ngăn được** chuyển tiền đã hoàn tất hoặc tiết lộ secret. Với hậu quả không thể đảo ngược hoặc yêu cầu SoD bắt buộc, có thể cần **preventive independent approval** trước thao tác, hoặc **từ chối ngoại lệ**.

### 7.3. Compensating control phải kiểm chứng được

Một control định nghĩa:
- **Owner:** ai vận hành/nhận cảnh báo.
- **Trigger:** event hoặc điều kiện nào kích hoạt.
- **Action:** làm gì khi bất thường.
- **Latency/SLA:** xử lý trong bao lâu.
- **Evidence:** log/ticket/signature và kết quả.
- **Failure behavior:** nếu control không hoạt động thì chặn hay hạ privilege thế nào.
- **Review:** ai đánh giá hiệu quả và khi nào.

Không phê duyệt bằng một dòng “Có người giám sát” khi chưa có phân công và bằng chứng thực thi.

## 8. Routing phê duyệt ngoại lệ theo rủi ro

Phê duyệt ngoại lệ SoD thường phải **độc lập hơn approval cấp quyền thông thường**. Quy trình ví dụ:

~~~mermaid
flowchart TD
    R["Requester mô tả xung đột, purpose, scope, expiry"] --> V["IAM/IGA verify identity + grant paths"]
    V --> ALT{"Có cách loại bỏ SoD conflict?"}
    ALT -->|Có| FIX["Redesign role/process, không cần exception"]
    ALT -->|Không| RISK["Risk + residual-risk assessment"]
    RISK --> LEGAL{"Chính sách/quy định cho phép exception?"}
    LEGAL -->|Không| DENY["REJECTED + phương án hợp lệ khác"]
    LEGAL -->|Có| CTRL["Define compensating controls + owners"]
    CTRL --> BUS["Business/resource owner approval"]
    BUS --> SEC["Independent security/SoD risk approval"]
    SEC --> DEC{"All mandatory decisions valid?"}
    DEC -->|Không| DENY
    DEC -->|Có| CURRENT["Revalidate JML, SoD, scope, control readiness"]
    CURRENT --> ACT["Activate/provision scoped grant"]
    ACT --> MON["Monitor usage + audit"]
    MON --> EXP["Expiry/revoke + reconcile"]
    EXP --> CLOSE["VERIFIED_CLOSED"]
~~~

Đây là **mẫu**, không phải route bắt buộc cho mọi trường hợp. Chính sách có thể thêm Data owner, compliance, risk committee hoặc delegated emergency approver. **Một mandatory approval không được thay bằng đa số phiếu từ nhóm khác**.

### 8.1. Quyết định của từng người duyệt

| Quyết định | Ý nghĩa | Hành động |
| --- | --- | --- |
| **APPROVE_WITH_CONDITIONS** | Chấp thuận đúng scope/time và controls được chỉ định. | Chỉ activate khi controls đã sẵn sàng. |
| **REJECT** | Rủi ro không chấp nhận hoặc thiếu authority. | Không cấp exception; đề xuất phương án khác. |
| **REQUEST_CHANGES** | Cần thu hẹp role/scope, thêm người kiểm soát. | Tạo phiên bản request mới và reapprove cần thiết. |
| **NEEDS_EVIDENCE** | Thiếu dữ liệu về grant path, assignment hoặc monitoring. | Không mặc định coi là approved. |
| **ESCALATE** | Cần risk owner/ủy ban có thẩm quyền cao hơn. | Chuyển đúng routing, không bypass. |

### 8.2. Không tự phê duyệt bằng account khác

Nếu requester/beneficiary cũng có account admin hoặc vai trò Security, phải áp **distinct-person requirement** theo policy. Đối chiếu `personId`/identity binding của mọi account, không tính các account khác nhau của cùng người như nhiều quyết định độc lập.

### 8.3. Delegation, vắng mặt và timeout

- Alternate approver phải **có authority đối với loại SoD conflict và resource**.
- Delegation có giới hạn thời gian/scope; không thể ủy quyền một mức rủi ro cao hơn thẩm quyền của delegator.
- Timeout dẫn tới reminder/escalation/expire, **không tự auto-approve** quyền xung đột nhạy cảm.
- Trong trường hợp khẩn cấp, dùng **emergency/break-glass policy riêng** có kiểm soát, không dùng timeout làm đường vòng.

## 9. Phiên bản yêu cầu và phê duyệt lại khi thay đổi

Approval chỉ có hiệu lực cho **request snapshot cụ thể**.

~~~text
V1:
  user = person-2048
  conflict = deploy:execute + deploy:approve
  scope = one service, tenant-vn
  duration = 45 minutes
  controls = independent release checker

APPROVED V1

V2:
  scope = all production clusters
  duration = 90 days
  controls = no independent checker

Không hợp lệ:
  Dùng APPROVED V1 để activate V2.
~~~

Khi đổi **beneficiary, resource, role/permission, thời gian, risk rating, compensating control, approver hoặc policy version có ảnh hưởng**, phải theo chính sách **revalidate và reapprove**. Nên gắn decision với `requestVersion` và hash/snapshot có integrity protection.

### 9.1. Policy thay đổi giữa lúc pending

Nếu tổ chức sửa SoD rule khiến conflict trở nên nghiêm trọng hơn, yêu cầu đang chờ phải xử lý theo **transition policy** đã được phê duyệt: route lại hoặc chặn trước khi cấp, không tiếp tục dựa vào đánh giá cũ một cách máy móc. Quyền đã active cũng có thể cần **re-evaluation** khi rule trở thành mandatory.

### 9.2. Không kéo dài ngoại lệ bằng thay ngày trong database

Gia hạn `validUntil` phải là **new decision/renewal** có business justification và risk review. Việc chỉnh ngày trực tiếp trên grant mà không thay request version hoặc approval là một đường bypass.

## 10. Thời hạn, JIT và giới hạn phạm vi ngoại lệ

Ngoại lệ nên có **validFrom**, **validUntil**, **purpose** và **scope** rõ. Với đặc quyền nhạy cảm, ưu tiên khoảng thời gian ngắn hoặc activation theo ticket.

~~~text
exceptionIsValidAt(now) =
    now >= validFrom
    AND now < validUntil
    AND approvedScopeMatchesRequest
    AND mandatoryCompensatingControlsActive
    AND beneficiaryStillEligible
~~~

Khoảng thời gian **nửa mở** khiến ngoại lệ mất hiệu lực ngay tại `validUntil`. Hệ thống phải dùng **instant đã chuẩn hóa**, xử lý timezone/DST/effective date. Việc lưu timestamp không tự làm ứng dụng ngừng nhận token/phiên; cần runtime enforcement hoặc revocation phù hợp.

### 10.1. JIT khác standing role exception

Một user có thể giữ **eligibility** được phê duyệt để *xin* một quyền, nhưng vẫn phải có **activation approval** trước mỗi phiên. Điều này giảm cửa sổ rủi ro. Nếu SoD conflict bị cấm ở **assignment-level SSD**, chỉ dùng JIT chưa chắc đã giải quyết: cần kiểm tra policy cho phép eligibility/activation đến mức nào.

### 10.2. Giới hạn tài nguyên và hành động

Nếu nhiệm vụ là restart một dịch vụ, không cấp `GlobalAdmin` cho toàn tenant khi có thể dùng `service:restart` đúng resource. Có thể dùng RBAC role hẹp + ABAC điều kiện:
- Tenant/resource ID.
- Incident/change ticket còn active.
- Người hưởng ngoại lệ/role đúng.
- Step-up MFA hoặc workload trust.
- Session duration và device posture khi phù hợp.
- Independent control đã được thiết lập.

### 10.3. Renewal và review định kỳ

Một ngoại lệ “ngắn hạn” được gia hạn 20 lần liên tiếp có thể đã trở thành **standing privilege** trá hình. Nên đặt:
- Giới hạn số lần gia hạn hoặc mốc review tăng cường theo policy.
- Phân tích nguyên nhân phải giữ ngoại lệ.
- Owner chịu trách nhiệm loại bỏ root cause.
- Quyết định có tiếp tục hay phải thiết kế lại quy trình.

## 11. Tính toán xung đột thực tế: RBAC, ABAC và quyền gián tiếp

### 11.1. Direct role không phải toàn bộ quyền

Nguồn grant có thể gồm:
- IAM-assigned business roles.
- Role kỹ thuật tại ứng dụng.
- Role hierarchy/senior–junior.
- Nested/dynamic groups.
- Direct/resource-based grants.
- Delegation/JIT/PAM eligibility.
- Local admin account, service account impersonation.
- Scopes/claims trong access token còn hiệu lực.

Ngoại lệ cần dựa trên **effective permissions** trong scope cụ thể, không chỉ hai tên role hiện trên UI.

### 11.2. Đồ thị SoD và multiple inheritance

~~~mermaid
flowchart TD
    S["FinanceSuperUser"] --> C["PaymentCreator"]
    S --> A["PaymentApprover"]
    C --> PC["payment:create"]
    A --> PA["payment:approve"]
    PC --> X["Conflict rule FIN-SOD-01"]
    PA --> X
~~~

Một assignment `FinanceSuperUser` làm user có hai quyền theo hierarchy. Nếu policy cấm cặp này, cần sửa role hoặc có exception hợp lệ **đúng cấp/loại xung đột**, không chỉ tắt check khi UA trực tiếp không chứa cả hai role.

### 11.3. ABAC giới hạn conflict theo resource

Giả sử user có `payment:create` trong **tenant-vn** và `payment:approve` chỉ trong **tenant-sg**. Hai permission có tên khác scope nên có thể **không gây xung đột trong cùng phạm vi**, tùy ma trận SoD. Ngược lại, nếu user có quyền tạo và duyệt cùng tenant/giao dịch, nguy cơ còn nguyên.

~~~text
conflictExists =
    hasPermission(subject, "payment:create", scopeA)
    AND hasPermission(subject, "payment:approve", scopeB)
    AND scopesOverlap(scopeA, scopeB)
    AND conflictRuleAppliesTo(subject, resource, context)
~~~

Đây là **mô hình khái niệm**, không phải cú pháp engine. Cần tính cả tenant, resource, transaction, time, active roles và policy-specific constraints; không đánh giá SoD chỉ bằng string equality của permission name.

### 11.4. Ngoại lệ không tự thay đổi policy deny

Nếu PEP tại ứng dụng có rule `createdBy != approver` bắt buộc, một record exception ở IGA **không tự khiến rule đó biến mất**. Muốn hỗ trợ ngoại lệ theo chính sách phải có **integration/decision logic** được thiết kế, có audit và không vượt kiểm soát bắt buộc. Không sửa trực tiếp database giao dịch hoặc claim client để “vượt” PEP.

## 12. Kết nối IdP, SSO, SCIM, PAM và enforcement

~~~mermaid
flowchart TD
    HR["HRIS / JML authoritative events"] --> IAM["IAM/IGA: identity + desired access"]
    IAM --> EX["SoD engine + exception registry"]
    EX --> ROUTE["Independent approval / risk acceptance"]
    ROUTE --> READY["Control readiness + JML revalidation"]
    READY --> PROV["SCIM / target API / PAM JIT"]
    PROV --> IDP["IdP groups, SSO and MFA"]
    PROV --> APP["Target roles, resource policies"]
    IDP --> APP
    APP --> PEP["RBAC/ABAC policy enforcement"]
    PEP --> MON["Monitoring + audit + reconciliation"]
    MON --> EX
~~~

| Lớp | Có thể làm | Không tự chứng minh |
| --- | --- | --- |
| **HRIS/IAM** | Identity, assignment, JML, owner, desired permissions. | Target đã thực sự cấp/gỡ đúng quyền. |
| **IGA/SoD engine** | Phát hiện conflict, ghi exception approval và conditions. | Application PEP đang áp exception đúng scope. |
| **IdP/SSO** | Xác thực danh tính, MFA/claims và session. | Xung đột SoD đã được giải quyết. |
| **SCIM** | Provision User/Group theo provider capability. | Mọi rule SoD, local role/credential đều đã đồng bộ. |
| **RBAC** | Tổ chức role/permission và hierarchy. | Data/resource scope đã tự được giới hạn. |
| **ABAC/PDP/PEP** | Ra quyết định và enforce condition runtime khi được tích hợp. | Entitlement dư thừa ở hệ thống khác đã được thu hồi. |
| **PAM/JIT** | Giới hạn activation, credential/session đặc quyền. | Đường admin trực tiếp ngoài PAM không còn. |
| **Audit/reconciliation** | Phát hiện điều kiện không thực thi hoặc quyền tồn dư. | Chính bản thân log thay thế preventive control. |

### 12.1. SCIM không có “SoD exception” chuẩn chung

**SCIM 2.0** cung cấp mô hình User/Group và các thao tác provisioning, nhưng **không định nghĩa một giao diện chuẩn chung cho mọi hệ thống để bật/tắt ngoại lệ SoD, risk acceptance và compensating controls**. Exception registry thường ở IGA/GRC/PAM hoặc ứng dụng tùy kiến trúc.

Một connector có thể gán nhóm qua SCIM thành công, trong khi application vẫn từ chối vì SoD runtime rule. Đây có thể là kết quả **đúng chính sách** nếu exception không áp tại application. Không tự đồng nhất “grant provisioned” với “exception usable”.

### 12.2. SSO và token là nguồn ngữ cảnh, không phải sự chấp thuận ngoại lệ

Một access token có role/scope được phát hành tại T0 có thể còn hợp lệ khi exception hết hạn ở T1. Resource server cần policy về session/token lifetime, revocation/introspection hoặc runtime authorization để chặn theo deadline. **MFA thành công xác minh phiên**, không phải bằng chứng rằng SoD conflict đã được risk owner chấp thuận.

## 13. Joiner: ngoại lệ không nên là baseline

Trong **Joiner**, nhân viên/người hợp đồng được xác minh danh tính, gán baseline roles theo HRIS/assignment và policy. Một nhu cầu ngoại lệ SoD ngay từ ngày đầu là dấu hiệu cần kiểm tra:
- Role chuẩn có bị gộp quá nhiều permission?
- Business role mapping có khiến người mới vừa tạo vừa duyệt giao dịch?
- Người mới có thực sự được bổ nhiệm vào hai nhiệm vụ?
- Có thể tách resource/action hoặc chọn một approver khác không?
- Có yêu cầu pre-start hoặc temporary onboarding khiến quyền bị bật sớm?

**Đừng xây “Joiner package” tự động cấp ngoại lệ SoD cho mọi nhân viên trong cùng job title.** Nếu có ngoại lệ được phê duyệt, phải nêu rõ beneficiary, owner, date, scope và review.

### 13.1. Trường hợp kỹ thuật viên ở chi nhánh nhỏ

Một chi nhánh chỉ có một IT operator vừa cài đặt máy trạm vừa quản lý local account. Nếu chính sách cấm cùng một người **tạo account và phê duyệt account**, có thể dùng **remote independent approver** từ đội trung tâm và giữ operator ở nhiệm vụ thực thi. Đây thường tốt hơn một ngoại lệ cho phép operator tự duyệt.

### 13.2. Ngày bắt đầu và thời gian ngoại lệ

Ngoại lệ không có hiệu lực trước mốc người mới được phép làm việc và tài khoản đã được xác thực/bind đúng người. Account có thể được chuẩn bị sớm nhưng SoD exception không phải lý do mở role admin production trước ngày hợp lệ.

## 14. Mover: nơi ngoại lệ dễ biến thành quyền tích lũy

**Mover** thay đổi phòng ban, vị trí, chức năng hoặc dự án. Trong khoảng chuyển tiếp, nhân viên có thể **giữ role cũ** đồng thời **nhận role mới**, làm xuất hiện SoD conflict.

### 14.1. Quy trình Mover với xung đột

~~~mermaid
flowchart TD
    HR["HRIS Mover event + effectiveAt"] --> DES["Compute KEEP / REMOVE / GRANT"]
    DES --> SOD["Analyze effective permissions + SoD"]
    SOD --> C{"Conflict?"}
    C -->|Không| APPLY["Provision approved roles, revoke old roles"]
    C -->|Có| ALT["Try revoke old or redesign roles first"]
    ALT --> E{"Needs permitted temporary exception?"}
    E -->|Không| APPLY
    E -->|Có| RISK["Risk owner approval + compensating controls"]
    RISK --> APPLY
    APPLY --> CHECK["Target entitlement/session readback"]
    CHECK --> CLOSE["Verify no stale access"]
~~~

Sơ đồ minh họa các đường xử lý hợp lệ; nếu ngoại lệ bị Reject hoặc không đủ điều kiện phải **chặn grant mới gây xung đột**, không đi thẳng tới APPLY.

### 14.2. Không dùng exception để tránh thu hồi quyền cũ

Ví dụ Lan chuyển từ `PaymentCreator` sang `PaymentApprover`. Nếu nhiệm vụ tạo thanh toán không còn, cần **gỡ `PaymentCreator` trước/đúng thời điểm role mới active**. Không xin ngoại lệ 90 ngày chỉ vì quy trình deprovisioning chậm.

Một handover hợp lệ có thể yêu cầu **role xem dữ liệu cũ** trong 7 ngày, không cần giữ quyền tạo thanh toán. Phân tích hành động cần thiết trước khi chấp nhận xung đột.

### 14.3. Exception mất căn cứ khi Mover thay đổi

Nếu một exception gắn với assignment Operations, Mover sang Finance phải kích hoạt **re-evaluation** dù `validUntil` còn xa. Thời hạn mới không tự kéo dài ngoại lệ. Có thể cần revoke ngay, reapprove đúng scope hoặc chuyển sang phương án không xung đột.

### 14.4. Nhiều assignment hợp lệ

Một nhân viên có thể song song phục vụ hai dự án. Điều này không mặc nhiên sai; nhưng phải kiểm tra **overlap của action/resource**, khác biệt tenant, effective dates và SoD rule. Không dùng `department` duy nhất để bỏ qua những assignment có phê duyệt khác hoặc mặc định toàn bộ quyền hai dự án được hợp chung không giới hạn.

## 15. Leaver: ngoại lệ phải kết thúc theo vòng đời

Khi HRIS/contractor source xác nhận **Leaver có hiệu lực**, quyền truy cập theo quan hệ làm việc thông thường phải bị chặn theo chính sách, kể cả những quyền trước đó có exception.

Cần xét:
1. IdP/account state và đăng nhập SSO mới.
2. Role/group/direct grants được exception cho phép.
3. PAM eligibility và JIT activation.
4. Local/privileged accounts.
5. Access/refresh tokens, PAT, API keys, SSH keys/certificates.
6. Application sessions và delegated approvals.
7. Exception registry status và các scheduled jobs có thể cấp lại quyền.
8. Target readback/effective access.
9. Owner/remediation nếu không thể chặn ngay.

**Không cần chờ exception approver “cho phép thu hồi” khi Leaver đã khiến quyền hết căn cứ theo policy**. Trường hợp dữ liệu lịch sử hoặc ownership transfer cần tiếp tục lưu giữ là vấn đề khác với việc user đã nghỉ còn được login.

### 15.1. Rehire không hồi sinh ngoại lệ cũ

Người tái tuyển có thể được nối với identity/account cũ theo chính sách, nhưng phải **review lại role assignment và SoD** cho công việc hiện tại. `EXCEPTION_EXPIRED` hoặc `REVOKED` từ lần làm việc trước không được tự động chuyển lại `ACTIVE`.

## 16. Service account, workload identity và SoD exception

**Non-human identities** như service account, service principal, pipeline và batch job thường có quyền máy–máy, vòng đời khác HR JML. Một workload có thể vừa đọc dữ liệu nguồn vừa ghi kết quả; cần xác định **rủi ro quyền và hành động** thay vì áp máy móc role của người.

### 16.1. Ví dụ pipeline deploy

Một CI/CD pipeline có quyền:
- Build và push artifact.
- Tạo release candidate.
- Triển khai production.
- Sửa policy phê duyệt release.

Rủi ro lớn nhất có thể nằm ở quyền **vừa thay đổi artifact vừa tự bỏ approval**. Thay vì exception cho một bot có mọi quyền, nên:
- Dùng **separate identities/tokens** cho build và deploy.
- Bảo vệ release artifact bằng provenance/signature phù hợp.
- Cần approval độc lập trước production.
- Không cho pipeline sửa policy của chính nó.
- Grant quyền deploy chỉ cho target environment và artifact được duyệt.
- Dùng short-lived workload credentials.
- Audit cả code revision, change ticket và actor phê duyệt.

### 16.2. Khi nào workflow service account cần exception?

Nếu legacy job chưa thể tách tài khoản hoặc hệ thống không hỗ trợ quyền hẹp, tổ chức có thể xem xét **temporary exception có owner**, cùng biện pháp:
- Scope network/resource và command allowlist nếu khả thi.
- Credential vault/rotation và giới hạn secret access.
- Monitoring giao dịch, anomaly detection và independent review.
- Thời hạn thay thế bằng thiết kế tốt hơn.
- Không dùng exception để mặc định bỏ mọi SoD check tại target.

### 16.3. Owner con người nghỉ việc

Khi một engineer owner Mover/Leaver:
- Thu hồi quyền **cá nhân** vào CI/CD, secret manager và IAM.
- Bàn giao **workload owner team**.
- Đánh giá credential từng có thể bị người đó biết hoặc sao chép.
- Rotate/revoke credential theo risk.
- Re-evaluate SoD exception và service purpose.
- Không xóa workload account đang chạy nếu nghiệp vụ còn cần, nhưng không để owner trống.

**Một exception cho workload phải gắn với dịch vụ/tài nguyên và owner**, không chỉ gắn một employee ID hết hiệu lực.

## 17. Emergency, break-glass và SoD

Một incident nghiêm trọng có thể khiến bộ phận không sẵn người phê duyệt độc lập đúng lúc. Tuy nhiên **emergency không có nghĩa mọi rule đều tự được bỏ qua**.

Một emergency workflow được phê duyệt trước có thể:
- Xác định loại tình huống được kích hoạt.
- Dùng tài khoản hoặc capability dự phòng phù hợp.
- Giới hạn tenant/resource/action và thời gian.
- Yêu cầu MFA/credential control phù hợp khả năng khẩn cấp.
- Có alert tới risk/security owner và ghi session.
- Giao người khác **review nhanh nhất có thể** theo policy.
- Revoke/rotate sau sự cố, lưu incident/exception ID.
- Đánh giá liệu trigger có hợp lệ, có hoạt động không được phép và có cần sửa control không.

### 17.1. Break-glass khác exception thường xuyên

- **Ngoại lệ SoD thông thường**: có thể đánh giá/duyệt trước, chủ động gắn controls và hạn.
- **Break-glass**: cơ chế dự phòng khi một điều kiện vận hành quan trọng không khả dụng; đòi hỏi thiết kế phục hồi, monitoring và post-use review riêng.
- **Không loại nào** được miễn kiểm soát luật/chính sách bắt buộc chỉ vì tên “emergency”.

**Không thiết kế:** “Nếu Security approver không phản hồi sau 15 phút thì tự động bật GlobalAdmin”. Đó là đường **fail-open** cho quyền nhạy cảm, không phải compensating control.

## 18. Quy trình cấp và kiểm chứng ngoại lệ trong hệ thống đích

### 18.1. Tách bốn trạng thái

| Mốc | Ý nghĩa | Cần tránh |
| --- | --- | --- |
| **APPROVED** | Risk owner/mandatory approvers đồng ý đúng scope/version. | Tự coi đã được cấp quyền. |
| **CONTROLS_READY** | Compensating controls đã được cấu hình và kiểm chứng. | Chỉ ghi “có monitoring” mà không có người nhận/log. |
| **ACTIVE/PROVISIONED** | Target đang cho khả năng dùng grant đúng phạm vi. | Cấp toàn role admin rộng hơn đề nghị. |
| **VERIFIED_CLOSED** | Quyền ngoại lệ hết và target không còn đường truy cập ngoài desired state. | Chỉ đổi `status=EXPIRED` tại exception registry. |

### 18.2. Quy trình thực thi từng bước

1. Đọc approved exception snapshot và kiểm tra chữ ký/authority.
2. Revalidate **identity, JML state, target account, resource/tenant, scope và current SoD rule**.
3. Kiểm tra compensating control **đang hoạt động** và được giám sát.
4. Xác nhận nếu cấp role thì không vượt scope ngoại lệ; tính cả quyền kế thừa/direct.
5. Provision/activate qua source có thẩm quyền: IAM, IdP, SCIM, app API hoặc PAM.
6. Readback target role/group/grant, runtime policy và session scope.
7. Kích hoạt monitoring/alert và ghi decision/verification.
8. Khi hết hạn/Mover/Leaver hoặc incident kết thúc: **deactivate/revoke**.
9. Kiểm tra token/session/local credential và các grant path còn lại.
10. Negative test an toàn hoặc bằng chứng target chứng minh quyền xung đột không còn usable.
11. Nếu còn quyền, đánh dấu `REMEDIATION_REQUIRED` với owner/SLA, không đóng verified.

### 18.3. Không cấp rộng hơn ngoại lệ

Một ngoại lệ cho `service:restart` trên `cluster-vn-2` không cho phép connector chọn `ClusterAdmin` trên mọi cluster cho tiện. Nếu target không có role hẹp, phải **reassess residual risk và approval**; không giả vờ mapping là tương đương.

### 18.4. Multiple grant paths

Gỡ JIT activation có thể không đủ nếu user còn direct grant hoặc local admin. Nếu mục tiêu là **thu hồi toàn bộ quyền xung đột**, phải kiểm tra mọi nguồn. Nhưng cũng không được gỡ những quyền khác **được approve hợp lệ** ngoài phạm vi exception mà không qua quy trình tương ứng.

## 19. State machine và exception lifecycle

Một exception cần state độc lập với trạng thái entitlement của target.

| State khái niệm | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| `DRAFT` | Chưa submit. | Không tạo grant/waiver. |
| `PENDING_ASSESSMENT` | Đang kiểm tra conflict, alternatives và risk. | Chưa approved. |
| `PENDING_APPROVAL` | Chờ người có authority ký. | Không activate. |
| `REJECTED` | Không được chấp nhận. | Không có quyền ngoại lệ. |
| `APPROVED_CONDITIONAL` | Approval hợp lệ nhưng controls chưa ready. | Chưa được phép dùng. |
| `READY_FOR_ACTIVATION` | Đã xác minh controls và eligibility. | Có thể activate trong window. |
| `ACTIVE` | Ngoại lệ đang được thực thi đúng scope/time. | Liên tục monitoring. |
| `SUSPENDED` | Tạm ngưng do control failure/incident. | Runtime phải chặn phù hợp. |
| `EXPIRED` | Đến thời hạn hết hiệu lực. | Cần revoke/readback, chưa mặc định Verified. |
| `REVOKING` | Đang loại quyền ngoại lệ. | Chưa đóng. |
| `PENDING_RECONCILIATION` | Chờ target evidence. | Chưa đóng. |
| `VERIFIED_CLOSED` | Kiểm chứng không còn privilege ngoài desired state. | Có audit evidence. |
| `REMEDIATION_REQUIRED` | Có sai lệch/vi phạm cần xử lý. | Có owner, containment và SLA. |
| `SUPERSEDED` | Bản cũ được thay bằng decision mới hợp lệ. | Không cho job cũ tự activate. |

**Đây là mô hình minh họa**, không phải enum chuẩn SCIM/IGA.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_ASSESSMENT
    PENDING_ASSESSMENT --> PENDING_APPROVAL
    PENDING_APPROVAL --> REJECTED
    PENDING_APPROVAL --> APPROVED_CONDITIONAL
    APPROVED_CONDITIONAL --> READY_FOR_ACTIVATION: controls verified + identity eligible
    READY_FOR_ACTIVATION --> ACTIVE: grant applied + readback
    ACTIVE --> SUSPENDED: control failure / risk alert
    ACTIVE --> EXPIRED: end time
    SUSPENDED --> REVOKING
    EXPIRED --> REVOKING
    REVOKING --> PENDING_RECONCILIATION
    PENDING_RECONCILIATION --> VERIFIED_CLOSED: effective rights removed
    PENDING_RECONCILIATION --> REMEDIATION_REQUIRED: residual access
    REMEDIATION_REQUIRED --> REVOKING: correction
    VERIFIED_CLOSED --> [*]
~~~

### 19.1. Ràng buộc bất biến (invariants)

- Không được **ACTIVE** nếu thiếu mandatory approvals hoặc thiếu control.
- Approval của phiên bản cũ không mở rộng scope/thời hạn bản mới.
- Beneficiary ở trạng thái Leaver không thể tiếp tục nhận ngoại lệ lao động thông thường.
- Hết `validUntil` không được tiếp tục Permit chỉ vì token/session cũ.
- Một lần Reject/Cancel không tạo grant mới.
- Người hưởng ngoại lệ không tự xác nhận compliance khi policy yêu cầu reviewer độc lập.
- Exception không được thay thế required transaction-level independent approval.
- Không đánh dấu `VERIFIED_CLOSED` khi target chưa đạt tiêu chí thu hồi.

## 20. Pseudocode ra quyết định và kiểm tra hiệu lực

### 20.1. Kiểm tra trước khi activate

~~~text
function mayActivateSoDException(request, approvedException, now):
    identity = resolveAuthoritativeIdentity(request.beneficiary)
    target = resolveTrustedTargetAccountAndScope(request)

    if not identity.active or identity.lifecycleIsLeaver(now):
        return DENY

    if approvedException.requestVersion != request.version:
        return DENY

    if not approvedException.includes(request.action, target.resource, target.tenant):
        return DENY

    if now < approvedException.validFrom or now >= approvedException.validUntil:
        return DENY

    if not approvedException.hasAllMandatoryIndependentApprovals:
        return DENY

    if approvedException.isProhibitedByMandatoryPolicy:
        return DENY

    if not compensatingControlsAreVerifiedActive(approvedException):
        return DENY

    actualConflict = evaluateEffectivePermissionsAndSoD(identity, target)
    if not actualConflict.isCoveredByExactException(approvedException):
        return DENY

    return PERMIT_SCOPED_ACTIVATION
~~~

Pseudocode không áp dụng trực tiếp cho một sản phẩm; trong thực tế cần xử lý **race conditions, audit events, policy version, synchronized clock, attribute freshness và authorization at target**. Ngoại lệ được duyệt không tự làm PEP trả Permit nếu ứng dụng không tích hợp.

### 20.2. Kiểm soát trong từng request

~~~text
function authorizeSensitiveAction(subject, action, resource, context):
    if not baselineIdentityAndRolePolicyAllows(subject, action, resource):
        return DENY

    conflict = evaluateCurrentSoD(subject, action, resource, context)

    if not conflict.exists:
        return evaluateRemainingABACAndTransactionConstraints()

    exception = findActiveExceptionBoundTo(
        subject.identityId, action, resource, conflict.ruleId, context.now
    )

    if exception missing or exception.controlsNotSatisfied:
        return DENY

    if conflict.ruleIsNonWaivable:
        return DENY

    return evaluateRemainingABACAndTransactionConstraints()
~~~

Đây là **kiểu xử lý minh họa**, không định nghĩa semantics cho mọi SoD engine. Đặc biệt, **không được bỏ các chính sách cấm tuyệt đối, tenant isolation, transaction SoD bắt buộc hoặc MFA** khi đã có exception.

### 20.3. Vì sao kiểm tra lúc cấp chưa đủ?

Trong thời gian 45 phút:
- User có thể bị Mover/Leaver.
- Compensating control hoặc approver có thể bị vô hiệu hóa.
- Incident kết thúc sớm.
- Scope tài nguyên bị thay đổi.
- JIT/session/token còn sống hơn dự kiến.

Vì vậy cần request-time checks hoặc cơ chế session/permission revocation phù hợp mức rủi ro.

## 21. Concurrency, idempotency và dữ liệu cũ

Ngoại lệ có thể đi qua nhiều hệ thống: GRC/IGA, IdP, PAM, SCIM, app và audit collector. Chúng không cập nhật atomic trong một giao dịch.

| Race condition | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Risk owner Approve đúng lúc HRIS phát Leaver. | Activate grant cho người đã nghỉ. | Revalidate lifecycle ngay trước activation/PEP. |
| Hai approvers ký đồng thời. | Hai worker cùng provision. | Atomic finalization, idempotency key. |
| Scope request đổi sau approval. | Cấp quyền rộng hơn bản được duyệt. | Snapshot version/hash và reapproval. |
| `validUntil` đã qua nhưng queue còn job activate. | Grant xuất hiện sau expiry. | Check deadline lúc worker chạy, hủy stale jobs. |
| Role hierarchy đổi khi exception active. | Conflict mở rộng tới permission mới. | Policy/version monitoring và re-evaluate impact. |
| SCIM PATCH timeout nhưng target đã thay group. | Retry có thể tạo grant lặp/sai. | Readback actual state và idempotent sync. |
| PAM deactivate nhưng token cũ còn. | Vẫn có effective privilege. | Revocation/session checks và negative tests. |
| Compensating control ngừng hoạt động. | Rủi ro không còn được bù trừ. | Alert và `SUSPEND`/containment theo policy. |
| Dynamic group tự cấp lại role. | Grant bị thu hồi rồi xuất hiện lại. | Xử lý authoritative group rule/attribute. |

### 21.1. Không thay thế ràng buộc bằng thời hạn trên giấy

Một exception có timestamp hết hạn nhưng ứng dụng **không đọc** timestamp đó và không nhận revoke event thì không được coi là time-limited về mặt enforcement. Cần chứng minh **target thực sự chặn action** khi hết hạn.

### 21.2. Chuyển trạng thái phải chống chạy lại

- Dùng `exceptionId + version + target + action` làm định danh idempotency.
- Worker kiểm tra state hiện hành và approval snapshot.
- Không chạy lại `APPROVED` từ một decision đã `SUPERSEDED`.
- Khi API timeout, readback trước retry.
- Có retry budget, dead-letter queue/remediation owner.
- Không đóng exception khi chưa đủ target evidence.

## 22. Audit, monitoring và reconciliation

### 22.1. Một record audit nên trả lời

1. SoD conflict rule nào đã được áp?
2. Identity/account nào có quyền xung đột và từ grant paths nào?
3. Business purpose, scope, thời gian, alternatives nào đã được đánh giá?
4. Risk owner và Security/SoD reviewer nào chấp thuận?
5. Residual risk nào được chấp nhận, control nào được áp?
6. Ai đã provision và target phản hồi gì?
7. Quyền nào được sử dụng, trong transaction/resource nào?
8. Người giám sát độc lập đã kiểm tra những gì?
9. Ngoại lệ hết hạn/thu hồi lúc nào, session/token xử lý ra sao?
10. Actual effective permissions và policy enforcement đã khớp desired state chưa?

### 22.2. JSON minh họa hồ sơ ngoại lệ

~~~json
{
  "exceptionId": "SOD-EX-2026-014",
  "requestVersion": 2,
  "beneficiary": {
    "identityId": "person-2048",
    "targetAccountRef": "production-user-88"
  },
  "target": {
    "system": "production-platform",
    "tenant": "tenant-vn",
    "resource": "cluster-vn-2/service-catalog"
  },
  "conflict": {
    "ruleId": "OPS-SOD-07",
    "permissions": ["deploy:execute", "deploy:approve"],
    "detectionSource": "IGA_EFFECTIVE_PERMISSION_ANALYSIS"
  },
  "approval": {
    "businessOwnerRef": "person-320",
    "riskOwnerRef": "person-901",
    "securityReviewerRef": "person-902",
    "decision": "APPROVED_WITH_CONTROLS",
    "policyVersion": "sod-policy-v9"
  },
  "scope": {
    "actions": ["service:restart"],
    "incidentRef": "INC-2026-482",
    "validFrom": "2026-12-02T10:00:00+07:00",
    "validUntil": "2026-12-02T10:45:00+07:00"
  },
  "compensatingControls": [
    {
      "type": "INDEPENDENT_APPROVAL",
      "ownerRef": "person-901",
      "state": "VERIFIED"
    },
    {
      "type": "SESSION_MONITORING",
      "ownerRef": "security-operations",
      "state": "VERIFIED"
    }
  ],
  "execution": {
    "source": "pam-jit",
    "activationRef": "pam-activation-440",
    "status": "ACTIVE"
  },
  "verification": {
    "status": "PENDING_EXPIRY_RECONCILIATION"
  }
}
~~~

**JSON minh họa nội bộ, không phải schema chuẩn của SCIM/OIDC/IGA.** Không để một record `APPROVED_WITH_CONTROLS` tự bật quyền tại target khi chưa có enforce/monitor. Không ghi password, OTP, private key, full access token, bí mật giao dịch hoặc PII không cần thiết vào log.

### 22.3. Phân biệt approval, execution và verification

| Cấp bằng chứng | Có gì? | Chưa nói được gì? |
| --- | --- | --- |
| **Approval evidence** | Actor, authority, risk acceptance, scope, policy version. | Target đã bật đúng action/resource. |
| **Control readiness evidence** | Independent checker, alert/monitoring, JIT settings. | Controls sẽ hoạt động đúng trong mọi tình huống. |
| **Execution evidence** | PAM activation hoặc SCIM/API result. | Token/session và quyền ngoài scope đã bị chặn. |
| **Usage evidence** | Action/transaction/session logs. | Mọi hành động đều đã được reviewer xem xét. |
| **Closure evidence** | Readback, negative test hoặc target authorization evidence. | Không còn quyền khác hợp lệ ngoài scope đang rà soát. |

### 22.4. Không cung cấp toàn bộ policy nhạy cảm cho client

Người dùng có thể thấy “Yêu cầu ngoại lệ không được chấp nhận” và một ticket ID. Reviewer có authority có thể thấy risk/control details. Không trả toàn bộ HR profile, security thresholds, SoD detection rules hay thông tin khác có thể làm lộ hệ thống trong response công khai.

## 23. KPI và cảnh báo ngoại lệ SoD

| Chỉ số | Định nghĩa tham khảo | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Active SoD exceptions** | Ngoại lệ đang có hiệu lực theo policy, theo risk class. | Không chỉ đếm số record APPROVED. |
| **Standing high-risk exceptions** | Ngoại lệ nhạy cảm được kéo dài hoặc active liên tục. | “Chỉ là một record” nhưng scope có thể toàn tenant. |
| **Exceptions without controls** | Ngoại lệ thiếu compensating control có owner/bằng chứng. | Có text control không đồng nghĩa đang hoạt động. |
| **Overdue exceptions** | Đã quá hạn nhưng target permission/session chưa verified revoked. | Chỉ nhìn database expiry sẽ bỏ residual access. |
| **Renewal frequency** | Số lần gia hạn theo rule/beneficiary. | Gia hạn liên tiếp có thể là role design failure. |
| **Independent approval violations** | Lần self-approval/authority conflict bị phát hiện. | Hai account của cùng người không phải hai reviewer. |
| **Control failures during active grant** | Trường hợp monitoring/dual control ngừng hiệu lực. | Không coi ngoại lệ vẫn an toàn mặc định. |
| **Actual SoD violation incidents** | Hành động xung đột thực tế được phát hiện. | Không chỉ dựa trên assigned role. |
| **Revocation latency** | Từ hạn/mốc JML tới lúc target effective privilege chấm dứt. | Không dùng thời điểm ticket đóng làm mốc. |
| **Exception re-grants** | Quyền xung đột xuất hiện lại sau revoke. | Có thể do dynamic group hoặc workflow cũ. |
| **Workload exception owner coverage** | Non-human exception có service owner đang hiệu lực. | Không phải owner con người nghỉ là job hết nhu cầu. |
| **Compensating-control effectiveness** | Control đã chạy, có kiểm tra và xử lý bất thường đúng SLA. | Log có dữ liệu không có nghĩa reviewer đã đọc. |

Không có ngưỡng ngoại lệ toàn cầu phù hợp mọi tổ chức. Nên phân tầng theo **permission impact, data sensitivity, scope, duration, likelihood và chính sách quản trị rủi ro**.

### 23.1. Cảnh báo cần kích hoạt

- Ngoại lệ đã expired nhưng grant/token/session vẫn cho action.
- Một approver chính là beneficiary hoặc cùng person identity.
- Exception scope hoặc role bị mở rộng sau approval mà không reapprove.
- SoD rule đổi tạo thêm conflict không nằm trong exception cũ.
- Compensating control mất tín hiệu/log hoặc owner đã Leaver.
- JIT/PAM role tồn tại quá deadline hoặc bị reactivated từ job cũ.
- Người hưởng ngoại lệ chuyển bộ phận nhưng vẫn active.
- Workload có exception không còn owner/service purpose.
- Quyền bị thu hồi được dynamic group/automation cấp lại.
- Không có independent review cho hành động đã thực hiện dưới exception.

## 24. Case study A — Nhóm tài chính nhỏ

**Bối cảnh:** Một chi nhánh chỉ có một nhân viên kế toán phụ trách lập chứng từ, trong khi người phê duyệt thường ngày đi vắng. Hệ thống có role `PaymentCreator` và `PaymentApprover`, chính sách cấm một người **tự tạo và tự phê duyệt cùng khoản thanh toán**.

### 24.1. Phương án nguy hiểm

Cấp cả hai role rồi tắt rule maker–checker cho toàn user trong 30 ngày. Điều này có thể cho phép tạo và duyệt bất kỳ khoản nào mà không có người kiểm tra độc lập. **Không hợp lệ nếu transaction SoD bắt buộc**; ngay cả khi không bị cấm tuyệt đối, residual risk rất cao.

### 24.2. Phương án ưu tiên

- Kế toán tiếp tục **tạo chứng từ**.
- Bổ nhiệm một **remote approver có thẩm quyền** ở đơn vị khác để duyệt.
- Giao approval task qua workflow có xác thực và audit.
- Giới hạn giá trị/tenant và đối chiếu người tạo ≠ người duyệt.
- Nếu cần truy cập tạm vào một role kỹ thuật khác, yêu cầu ngoại lệ chỉ cho **vai trò/đường tác nghiệp hẹp**, không bỏ transaction checker.

### 24.3. Nếu chính sách cho phép ngoại lệ role assignment

Trường hợp không thể tách hoàn toàn việc nắm role nhưng vẫn có một **người phê duyệt cuối cùng độc lập**:
- Xin ngoại lệ SSD có thời hạn ở phạm vi chi nhánh.
- Risk/control owner đánh giá và approve.
- Ứng dụng **vẫn bắt buộc kiểm tra maker–checker ở giao dịch**.
- Tăng giám sát và daily reconciliation có người độc lập.
- Hết hạn, thu hồi role dư và kiểm tra actual permissions.

**Bài học:** Một ngoại lệ ở cấp **assignment** không phải ngoại lệ ở cấp **giao dịch**, và không được gọi audit sau giao dịch là tương đương một phê duyệt độc lập trước giao dịch khi policy yêu cầu phòng ngừa.

## 25. Case study B — DevOps khôi phục production

**Bối cảnh:** Một engineer được phép sửa cấu hình nhưng release production phải do người khác phê duyệt. Trong incident, người kiểm tra thường ngày không sẵn.

### 25.1. Nhận diện conflict

- Action A: `config:change`.
- Action B: `release:approve` hoặc `deployment:execute`.
- Resource: một service production cụ thể.
- Thời gian: incident window 45 phút.
- Người chịu ảnh hưởng: khách hàng của service, độ nhạy cao.

### 25.2. Phương án có kiểm soát

1. Dùng runbook/pipeline **đã phê duyệt** có khả năng rollback.
2. Xác định **người giám sát độc lập** qua on-call escalation, nếu có.
3. Giới hạn JIT vào `service:restart` hoặc action nhỏ nhất cần cho recovery.
4. Gắn incident ID, change diff, environment và MFA/session requirements.
5. Thu log độc lập, cảnh báo và post-incident review.
6. Hết incident hoặc validUntil thì revoke permission, session/token phù hợp.
7. Reconciliation các grants ngoài PAM để loại quyền còn tồn dư.

Nếu chính sách không cho bất kỳ ngoại lệ nào đối với release approval, cần dùng đường **emergency change có người có thẩm quyền độc lập** hoặc cơ chế khác tuân thủ rule, không tắt branch protection/logging để deploy nhanh.

### 25.3. Không để ngoại lệ ở lại sau khẩn cấp

Khi incident đóng, quyền JIT không cần kéo dài tới cuối ca nếu policy quy định hết theo ticket. Phải thu hồi và kiểm chứng **thao tác ngoài scope/ngoài thời gian bị chặn**.

## 26. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Coi “Manager Approved” là đủ miễn trừ mọi SoD. | Bỏ risk owner/independent controls. | Routing và authority theo conflict/risk. |
| Requester tự đặt `risk=LOW`. | Dễ hạ cấp kiểm soát. | Tính risk từ authoritative policy/catalog. |
| Beneficiary dùng admin account thứ hai tự duyệt. | Self-approval bị che giấu. | Person-level identity binding. |
| Phê duyệt ngoại lệ vô hạn. | Standing SoD violation. | Expiration, owner, renewal review. |
| Mở toàn role admin khi chỉ cần một action. | Permission vượt scope. | JEA/JIT và RBAC/ABAC resource controls. |
| Tắt SoD toàn tenant để một user thực hiện nhiệm vụ. | Nhiều user khác cũng bị mất bảo vệ. | Exception bound to identity/action/resource/time. |
| Chỉ ghi “monitor logs” không có reviewer. | Detective control không vận hành. | Owner, schedule, evidence, failure response. |
| Dùng log sau sự kiện thay bắt buộc phê duyệt độc lập trước giao dịch. | Giao dịch gây thiệt hại đã hoàn thành. | Preventive independent approval hoặc từ chối. |
| Không xét role hierarchy. | Conflict gián tiếp bị bỏ sót. | Effective permission closure. |
| Chỉ xét IdP group, bỏ app direct grants. | Target vẫn có quyền xung đột. | Target grant-path reconciliation. |
| SCIM PATCH thành công được coi là exception đã hết quyền. | Token/PAM session/local account còn. | Session/token and effective-access verification. |
| Ngoại lệ còn active sau Mover/Leaver. | Quyền tồn dư không có căn cứ. | Event-driven revalidation/revocation. |
| Hết `validUntil` nhưng không revoke target. | Chỉ “hết trên giấy”. | Enforced expiry và readback. |
| Gia hạn bằng cách sửa date field. | Bypass independent approval. | New version/reapproval/decision history. |
| Owner workload nghỉ, bot vẫn không có chủ quản. | Orphaned exception và secret exposure. | Owner handover, credential review. |
| Auto-approve khi approver không phản hồi. | Fail-open cho đặc quyền. | Escalation/alternate/break-glass được quản trị. |
| Tắt MFA/logging khi cần khẩn cấp. | Mất kiểm soát và accountability. | Emergency policy độc lập, phạm vi hẹp. |
| Đóng ticket khi exception registry `EXPIRED`. | Actual access vẫn còn. | Target revocation + verification evidence. |
| Coi mọi SoD conflict đều có thể miễn trừ nội bộ. | Vi phạm ràng buộc bắt buộc. | Check non-waivable rules và từ chối nếu cần. |
| Xóa workload account vì người owner nghỉ. | Gián đoạn vận hành. | Revoke quyền cá nhân, bàn giao, review scope workload. |

## 27. Checklist thiết kế và vận hành ngoại lệ SoD

### 27.1. Trước khi phê duyệt

- [ ] Xác minh beneficiary, IAM identity, target account và tenant.
- [ ] SoD rule có ID/version, owner và semantics rõ: SSD, DSD, transaction hay administrative.
- [ ] Phân tích **effective permissions** qua role hierarchy, groups, direct grants, JIT và scope.
- [ ] Xác định rõ **có thể miễn trừ theo policy/pháp lý hay không**.
- [ ] Đã đánh giá phương án tách người, tách nhiệm vụ, sửa role hoặc JEA.
- [ ] Business need và dữ liệu HR/JML còn hiệu lực.
- [ ] Có risk rating, residual risk và risk owner có authority.
- [ ] Exception có **action/resource/tenant/time** tối thiểu và purpose/ticket.
- [ ] Compensating controls có preventive/detective classification, owner, evidence và failure behavior.
- [ ] Approver độc lập; không self-approval qua account khác.
- [ ] Request snapshot và policy version rõ; mọi thay đổi material cần reapproval.

### 27.2. Khi thực thi

- [ ] Revalidate account state, JML, role conflicts và approval version.
- [ ] Controls đã active và monitoring có người nhận.
- [ ] Provision/activate qua source of authority, không vượt scope.
- [ ] IdP/SSO/MFA và target RBAC/ABAC enforcement đúng ngữ nghĩa.
- [ ] SCIM chỉ được dùng theo capability của target; không giả định có SoD exception schema.
- [ ] PAM/JIT/credential/session được giới hạn trong thời gian được duyệt.
- [ ] Target readback cho biết quyền được cấp đúng role/action/resource.
- [ ] Có audit của người yêu cầu, approver, executor và independent reviewer.
- [ ] Race/timeout/retry không làm grant trùng hoặc kích hoạt request đã superseded.

### 27.3. Khi hết hạn, Mover hoặc Leaver

- [ ] Đến `validUntil` hoặc khi mất business basis thì revoke, không đợi quarterly review.
- [ ] Gỡ role/group/direct grants và PAM eligibility/activation theo phạm vi.
- [ ] Kiểm tra local accounts, session, access/refresh tokens, PAT/API keys/SSH credentials.
- [ ] Đối soát effective permissions, ABAC conditions và đường quyền gián tiếp.
- [ ] Negative tests an toàn hoặc target evidence chứng minh action xung đột đã bị chặn.
- [ ] Nếu quyền vẫn hoạt động, đặt `REMEDIATION_REQUIRED`, owner và SLA.
- [ ] Với workload, kiểm tra owner/credential lifecycle riêng; không tự cắt dịch vụ hợp lệ.
- [ ] Chỉ ghi `VERIFIED_CLOSED` khi closure evidence đáp ứng tiêu chí.
- [ ] Gia hạn ngoại lệ phải qua quyết định/version mới, không sửa thẳng expiration.

## 28. Bài tập thực hành

### 28.1. Bài A — SSD và role hierarchy

User Lan chỉ được gán `FinanceSuperUser`, nhưng role đó kế thừa `PaymentCreator` và `PaymentApprover`. SoD engine chỉ quét role trực tiếp nên không phát hiện conflict. Hãy mô tả cách tính permission closure và xác định liệu cần **sửa role design** hay xét exception.

### 28.2. Bài B — Ngoại lệ không phá maker–checker

Một người được approve ngoại lệ giữ hai role `PaymentCreator` và `PaymentApprover`. Họ tự tạo một khoản chi và muốn tự duyệt. Giải thích vì sao ngoại lệ assignment không tự hợp thức hóa transaction này; đề xuất kiểm tra independent approval.

### 28.3. Bài C — Timeout phê duyệt

Security reviewer không phản hồi sau 60 phút. Developer đề xuất tự Approve vì incident khẩn. Hãy thiết kế escalation/alternate approver hoặc emergency flow bảo vệ SoD, và giải thích rủi ro fail-open.

### 28.4. Bài D — Token cũ sau expiry

Exception JIT cho `service:restart` hết hạn 10:45 nhưng access token vẫn gọi được API lúc 11:00. Tại sao record `EXPIRED` chưa đạt `VERIFIED_CLOSED`? Những bước PEP/session/token/readback nào cần có?

### 28.5. Bài E — Mover có hai nhiệm vụ

Lan chuyển từ Operations sang Finance, được giao hỗ trợ Operations thêm 7 ngày. Hãy thiết kế **role hẹp, scope, expiry, SoD review và target verification**, thay vì giữ `OpsGlobalAdmin` 90 ngày.

### 28.6. Bài F — Leaver và exception chưa hết hạn

HRIS xác nhận Leaver ngày 05/12, nhưng exception có `validUntil=31/12`. Hệ thống nào phải trigger revoke? Tại sao `validUntil` không được ghi đè lifecycle event và cần kiểm tra những access paths nào?

### 28.7. Bài G — Workload pipeline tự phê duyệt

Pipeline vừa build, vừa approve release, vừa deploy production. Owner nói “bot không phải người, không cần SoD”. Hãy phân tích xung đột và thiết kế separate identities, approval authority và credential scopes.

### 28.8. Bài H — Kiểm soát bù trừ chỉ là ghi log

Một ngoại lệ cho phép tự duyệt thanh toán và yêu cầu “xem log cuối ngày”. Ai phải xem log? Điều gì xảy ra nếu khoản tiền không thể thu hồi? Khi nào phải từ chối ngoại lệ hoặc bắt buộc preventive independent approval?

### 28.9. Bài I — Scope thay đổi sau approval

Risk owner Approve exception 45 phút trên `cluster-vn-2`. Sau đó operator đổi scope thành `all-clusters` trong UI. Những trường nào của request phải được versioned và vì sao mọi approval cũ phải bị invalidate/reassess?

### 28.10. Bài J — Đo chất lượng exception register

Một dashboard có 100% requests được quyết định, nhưng 15 exception đã hết hạn còn token active, 8 không có control owner và 3 được cùng người hưởng quyền tự ký bằng admin account. Có thể gọi là 100% compliance không? Hãy đề xuất KPI riêng cho **approval quality, control readiness, expiry/revocation, independence và residual access**.

**Điểm cần ghi nhớ:** **Phê duyệt ngoại lệ SoD** không phải cách tắt kiểm soát phân tách nhiệm vụ để cấp quyền nhanh. Ngoại lệ chỉ hợp lệ khi **pháp lý/chính sách cho phép**, có **business need, risk owner độc lập, scope/time tối thiểu, compensating controls và bằng chứng thực thi**; phải phân biệt SSD, DSD, transaction-level và administrative SoD. Trong IAM **Joiner–Mover–Leaver**, ngoại lệ phải đi cùng **IdP/SSO, SCIM, RBAC/ABAC, PAM/JIT, quản lý credential/session, audit và reconciliation**. Chỉ khi **quyền xung đột không còn khả dụng ngoài phạm vi được phép**, có **target readback và verification**, ngoại lệ mới thật sự được đóng.

