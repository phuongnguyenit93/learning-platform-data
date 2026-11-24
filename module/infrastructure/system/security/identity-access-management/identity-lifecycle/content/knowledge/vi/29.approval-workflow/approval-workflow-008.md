# Approval timeout trong IAM: kiểm soát thời hạn phê duyệt, escalation và cấp quyền an toàn

## 1. Approval timeout là gì?

Trong **Identity and Access Management (IAM)**, **Approval workflow** là chuỗi bước xác minh, xét duyệt và ghi nhận quyết định đối với một yêu cầu cấp, thay đổi, gia hạn hoặc thu hồi quyền truy cập. **Approval timeout** là tình huống **một bước hoặc toàn bộ quy trình phê duyệt không nhận được quyết định hợp lệ trước thời hạn đã quy định**.

Ví dụ, nhân viên An yêu cầu role **ReportEditor** cho dự án Atlas lúc 09:00. Chính sách yêu cầu resource owner phản hồi trong hai ngày làm việc, nhưng tới hạn vẫn chưa có quyết định. Hệ thống phát sinh **approval timeout**; nó không được mặc định coi sự im lặng là đồng ý.

Approval timeout có hai mặt:

- **Vận hành:** nhân viên không có quyền cần thiết, tiến độ dự án chậm hoặc yêu cầu bị mắc kẹt.
- **Bảo mật:** cơ chế xử lý timeout không phù hợp có thể làm bỏ qua phê duyệt, cấp quyền quá rộng, duyệt bởi người không đủ thẩm quyền hoặc tái cấp quyền đã bị thu hồi.

Trong vòng đời **Joiner–Mover–Leaver (JML)**, timeout có thể làm Joiner chưa sẵn sàng, Mover thiếu quyền mới hoặc quyền cũ chưa được xử lý, và các thao tác liên quan Leaver bị chậm. Tuy nhiên, **luồng cắt quyền bắt buộc sau Leaver không nên phụ thuộc vào việc có ai đó phản hồi một access request bình thường**.

Nguyên tắc cần ghi nhớ:

> **Không có phê duyệt hợp lệ thì không được tự cấp quyền chỉ vì đã quá thời gian chờ.** Timeout phải dẫn đến một chuyển trạng thái, escalation, reassignment, denial/expiry hoặc ngoại lệ đã được định nghĩa trước, có kiểm toán.

## 2. Phân biệt timeout với những trạng thái thường gặp

| Tình huống | Ý nghĩa | Có thể cấp quyền mới không? |
| --- | --- | --- |
| **PENDING_APPROVAL** | Đang chờ người có thẩm quyền xem xét | Chưa; trừ nhánh chính sách khác đã có căn cứ phê duyệt độc lập |
| **APPROVAL_TIMEOUT** | Đã vượt deadline của bước/yêu cầu mà chưa có quyết định hợp lệ | Không tự động chỉ vì timeout |
| **ESCALATED** | Chuyển xử lý tới cấp được ủy quyền theo chính sách | Chưa; chờ quyết định mới |
| **REASSIGNED** | Giao nhiệm vụ duyệt cho người thay thế hợp lệ | Chưa; quyền cấp phụ thuộc quyết định hợp lệ |
| **APPROVED** | Có quyết định chấp thuận, đúng role/scope/thời hạn | Có thể đi tới provisioning sau khi tái kiểm tra |
| **REJECTED** | Người có thẩm quyền từ chối | Không |
| **EXPIRED/CANCELLED** | Yêu cầu không còn hiệu lực hoặc bị hủy | Không; request mới nếu có nhu cầu hợp lệ |
| **PROVISIONING_TIMEOUT** | Đã duyệt nhưng việc áp quyền ở hệ thống đích quá hạn | Không có nghĩa quyền chưa được cấp; phải readback |
| **ACCESS_EXPIRED** | Quyền đã được cấp trước đó đến thời điểm hết hạn | Phải thu hồi/chặn theo policy, khác với approval timeout |

**Timeout là một sự kiện/thời điểm quan sát, không nhất thiết là một trạng thái kết thúc.** Một hệ thống có thể ghi sự kiện **APPROVAL_TIMED_OUT** rồi đưa workflow sang **ESCALATED**; hệ thống khác đánh dấu **EXPIRED** sau một khoảng gia hạn. Cần có **state machine và hợp đồng trạng thái** rõ ràng.

Đừng nhầm **thời hạn người duyệt phải phản hồi** với **thời hạn role được cấp**. Một quyền có thể đã phê duyệt và bắt đầu có hiệu lực từ ngày sau, còn approval deadline xảy ra trước đó.

## 3. Những ai tham gia khi một phê duyệt quá hạn?

| Chủ thể/thành phần | Vai trò |
| --- | --- |
| **Requester** | Tạo access request, nêu nhiệm vụ và thời hạn cần quyền |
| **Beneficiary** | Người hoặc workload sẽ nhận quyền, có thể khác requester |
| **Manager** | Xác nhận nhu cầu công việc và mức ưu tiên theo thẩm quyền |
| **Resource owner** | Quyết định quyền đối với tài nguyên mình sở hữu |
| **Sponsor** | Chịu trách nhiệm nhu cầu của contractor/partner khi áp dụng |
| **Security/IGA approver** | Đánh giá đặc quyền, SoD, dữ liệu nhạy cảm hoặc ngoại lệ |
| **Backup approver/delegate** | Xử lý thay khi được ủy quyền hợp lệ |
| **IAM workflow engine** | Quản lý deadline, state, notification, escalation và audit |
| **Provisioning connector** | Chỉ cấp quyền khi có quyết định hợp lệ và các điều kiện vẫn đạt |
| **IdP, SCIM target, API/PEP** | Duy trì trạng thái account, nhóm, role và quyền hiệu lực ở nơi thực thi |

**Requester không mặc nhiên là approver; approver không mặc nhiên được tự cấp quyền; provisioning actor không được tự thay đổi nội dung quyết định.** Phân tách nhiệm vụ này tránh một request bị timeout trở thành lý do cấp quyền qua một đường không kiểm soát.

Nếu người duyệt đã nghỉ việc, đổi nhóm hoặc mất quyền phê duyệt, workflow phải **xác định lại người có thẩm quyền** thay vì chuyển tùy tiện sang một tài khoản administrator.

## 4. Những loại deadline cần phân biệt

Một workflow có thể có nhiều đồng hồ thời gian khác nhau:

| Deadline | Điều kiện tính | Ý nghĩa |
| --- | --- | --- |
| **Step approval deadline** | Bắt đầu khi một bước được giao cho approver | Thời hạn quyết định của bước đó |
| **Overall request deadline** | Từ lúc request hợp lệ được tiếp nhận hoặc mốc policy định nghĩa | Giới hạn thời gian cho toàn bộ workflow |
| **Escalation deadline** | Sau khi bước đang chờ đạt mốc nhắc/chuyển cấp | Khi cần chuyển sang owner mới hoặc cấp xử lý tiếp |
| **Business need-by** | Ngày người dùng cần bắt đầu sử dụng quyền | Ưu tiên nghiệp vụ, không thay approval |
| **Approved access start/end** | Mốc sử dụng quyền do policy và approver chấp thuận | Khi nào quyền được bật và phải chấm dứt |
| **Provisioning SLA** | Sau khi quyết định cấp hợp lệ | Thời hạn connector áp quyền ở target |
| **Revocation cutoff** | Mốc phải chặn quyền sau Mover/Leaver/expiry | Có thể cần ưu tiên cao hơn mọi request thông thường |

Ví dụ, role Reader có thể có **step approval deadline = 1 ngày làm việc**, **overall deadline = 3 ngày làm việc** và **access end = sau 30 ngày**. Đó là **ba điều kiện khác nhau**, không phải cùng một timestamp.

**SLA** là cam kết mức dịch vụ với đối tượng nhận dịch vụ; **OLA** là cam kết vận hành giữa các đội nội bộ hỗ trợ SLA. Thời hạn nhắc việc của từng approver thường là OLA/step timer; hoàn thành access request có thể được đo theo SLA rộng hơn. Cách gọi cụ thể cần theo hợp đồng dịch vụ của tổ chức.

## 5. Cấu trúc trạng thái cho Approval timeout

Một state machine nên xác định trạng thái **đang chờ**, **đã được quyết định**, **chuyển cấp**, **hết hiệu lực** và **cấp phát**. Ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> VALIDATING
    VALIDATING --> PENDING_APPROVAL: Eligibility hợp lệ
    VALIDATING --> REJECTED: Không đạt điều kiện
    PENDING_APPROVAL --> APPROVED: Approver hợp lệ đồng ý
    PENDING_APPROVAL --> REJECTED: Approver hợp lệ từ chối
    PENDING_APPROVAL --> TIMED_OUT: Hết hạn bước
    PENDING_APPROVAL --> CANCELLED: Hủy có thẩm quyền
    TIMED_OUT --> ESCALATED: Quy tắc escalation
    TIMED_OUT --> EXPIRED: Hết hạn request
    ESCALATED --> PENDING_APPROVAL: Giao bước mới / deadline mới
    ESCALATED --> REJECTED: Người có quyền từ chối
    ESCALATED --> EXPIRED: Hết hạn tổng
    APPROVED --> PROVISIONING: Revalidate thành công
    APPROVED --> CANCELLED: Điều kiện không còn hợp lệ
    PROVISIONING --> VERIFIED: Target readback và access test đạt
    PROVISIONING --> PARTIAL: Không xác minh đủ
    PARTIAL --> VERIFIED: Khắc phục và xác minh
    PARTIAL --> CANCELLED: Hủy theo quy trình phù hợp
    REJECTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    VERIFIED --> [*]
~~~

Đây là **một state machine minh họa**, không phải sơ đồ chuẩn bắt buộc. Trong thực tế, **TIMED_OUT** có thể chỉ là event, còn trạng thái trực tiếp chuyển từ **PENDING_APPROVAL → ESCALATED**. Nếu hệ thống có nhiều bước song song, state của **approval task** và **overall request** phải tách riêng.

Những bất biến quan trọng:

1. **APPROVED** chỉ đến từ một quyết định hợp lệ hoặc chính sách auto-approval đã được phê duyệt độc lập.
2. **TIMED_OUT, ESCALATED và REASSIGNED** không tự cấp entitlement.
3. Request đã **CANCELLED/EXPIRED/REJECTED** không được mở lại chỉ bởi callback chậm.
4. Workflow mới phải kiểm tra lại **employment, role, scope, tenant, SoD và policy** trước khi provision.
5. Một terminal state phải được xử lý nhất quán, tránh vừa APPROVED vừa EXPIRED do race condition.

## 6. Chọn chính sách timeout theo mức rủi ro

Không nên dùng cùng một hành vi timeout cho mọi loại quyền.

| Loại yêu cầu | Ví dụ | Chính sách timeout hợp lý để cân nhắc |
| --- | --- | --- |
| **Baseline/low-risk** | Quyền đọc app nội bộ trong vai trò đã duyệt | Nhắc việc, chuyển manager/resource owner, expiry nếu hết hạn |
| **Moderate-risk** | Chỉnh sửa tài liệu dự án | Escalation đến approver dự phòng và giới hạn tổng thời gian |
| **High-risk** | Xuất dữ liệu nhạy cảm | Không auto-approve; chuyển cấp tới data/security owner phù hợp |
| **Privileged** | IAM administrator, production deploy | Fail-closed, PAM/SoD và quyết định độc lập bắt buộc |
| **Cross-tenant** | Quyền đọc dữ liệu của pháp nhân khác | Duyệt đúng owner từng phạm vi; timeout không bỏ qua owner |
| **Contractor** | Quyền cho nhà thầu theo hợp đồng | Deadline không vượt ngày kết thúc bảo trợ/hợp đồng |
| **Emergency access** | Xử lý incident nghiêm trọng | Dùng playbook break-glass/JIT riêng, không ngầm auto-approve |

Chính sách có thể cho phép **auto-approval** đối với một số quyền nền tảng **nếu các điều kiện được đánh giá trước, đăng ký trong policy và đã được phê duyệt ở cấp quản trị**. Nhưng **“ai cũng im lặng quá 48 giờ thì cấp admin”** là một cơ chế nguy hiểm, không phải auto-approval hợp lệ.

Trước khi cấu hình timeout, phải trả lời: **role có cấp quyền trên tài nguyên nào, dữ liệu nhạy cảm tới đâu, approver nào có thẩm quyền, có SoD không và nếu chưa duyệt thì tác động nghiệp vụ nào xảy ra?**

## 7. Tính dueAt: thời gian lịch, ngày làm việc và múi giờ

**Deadline** phải được biểu diễn rõ ràng, không chỉ là một số “48” không đơn vị. Các biến thường cần:

- **startedAt:** thời điểm task được kích hoạt/giao cho approver.
- **durationPolicy:** 4 giờ làm việc, 24 giờ liên tục hoặc hai ngày làm việc.
- **calendarId:** lịch làm việc áp dụng cho approver hoặc service.
- **timezone:** múi giờ hiển thị/vận hành của lịch.
- **holidays:** những ngày nghỉ theo lịch được phê duyệt.
- **pause/resume policy:** trạng thái nào được dừng đồng hồ và ai được phép.
- **dueAt:** thời điểm tuyệt đối đã tính để hệ thống so sánh.
- **overallDueAt:** deadline cứng của cả request, nếu có.

Ví dụ **minh họa giả định**: task được giao lúc **16:00 thứ Sáu**, chính sách **4 giờ làm việc**, lịch làm việc từ 09:00 đến 17:00 thứ Hai–thứ Sáu, không có ngày lễ trong khoảng này. Nếu trong thứ Sáu còn một giờ làm việc thì ba giờ còn lại chuyển sang thứ Hai, nên **dueAt = 12:00 thứ Hai**, theo múi giờ của lịch. **Không phải 20:00 thứ Sáu**.

Với hệ thống đa quốc gia, người yêu cầu ở Việt Nam và resource owner ở khu vực khác có thể dùng **lịch làm việc khác nhau**. Hãy quy định lịch nào điều khiển timer; giao diện có thể hiển thị theo múi giờ người dùng nhưng backend lưu **instant có offset/UTC**. Không cộng “2 ngày” bằng cách cộng 48 giờ nếu policy nói **hai ngày làm việc**.

### Quy tắc tính thời hạn mẫu

~~~text
deadlinePolicy:
  trigger: STEP_ACTIVATED
  duration: 2
  unit: BUSINESS_DAYS
  calendarId: approver-business-calendar
  timezone: Asia/Ho_Chi_Minh
  firstReminderBeforeDue: 4 BUSINESS_HOURS
  maxEscalationAttempts: 2
  maxOverallDuration: 5 BUSINESS_DAYS
  terminalAction: EXPIRE_WITHOUT_GRANT
~~~

Đây là **cấu hình ví dụ**; mỗi workflow engine có cách biểu diễn riêng. Nếu ngày nghỉ hoặc lịch bị cập nhật giữa chừng, cần có chính sách **giữ dueAt đã chốt hay tính lại**, log phiên bản lịch và thông báo cho người liên quan.

## 8. Thời điểm kích hoạt và reset đồng hồ

Một timeout chính xác cần biết **đồng hồ bắt đầu ở đâu**:

| Sự kiện | Có nên khởi động/reset timer? |
| --- | --- |
| Request được tạo ở trạng thái DRAFT | Thường chưa |
| Request đã VALIDATED và giao bước đầu tiên | Thường có |
| Approver mở giao diện xem | Không nên tự reset deadline |
| Approver gửi câu hỏi cần bổ sung thông tin | Tùy chính sách pause/clarification |
| Requester bổ sung đủ thông tin được yêu cầu | Có thể resume hoặc bắt đầu deadline mới đã định nghĩa |
| Approver chuyển giao theo delegation hợp lệ | Có thể giữ dueAt hoặc tạo deadline mới, nhưng phải có chính sách |
| Escalation sang cấp tiếp theo | Có thể tạo step timer mới, vẫn bị giới hạn overall dueAt |
| Hệ thống restart/redeploy | Không được tự kéo dài deadline |
| Event nhân sự làm request không còn hợp lệ | Hủy/deny theo policy, không chờ timer |

Một lỗi dễ gặp là **mỗi lần worker retry hoặc user refresh làm deadline dời thêm**, khiến yêu cầu không bao giờ timeout. Deadline cần được lưu trong trạng thái bền vững và có ràng buộc phiên bản.

**Pause clock** chỉ nên xảy ra khi workflow định nghĩa lý do rõ, ví dụ cần người yêu cầu cung cấp tài liệu bắt buộc; mọi lần pause/resume phải có actor, lý do, thời điểm, policy và giới hạn tổng, không để requester lợi dụng để kéo dài phê duyệt vô hạn.

## 9. Nhắc việc trước hạn: notification không phải approval

Một hệ thống có thể gửi reminder khi còn 50% thời gian, trước hạn bốn giờ hoặc theo chính sách. Nội dung nên giúp approver hiểu:

- **Request ID, beneficiary, role, target, tenant, scope và lý do nghiệp vụ**.
- Deadline đang áp dụng, múi giờ và mức rủi ro.
- Link an toàn đến giao diện phê duyệt đã xác thực.
- Các lựa chọn **Approve, Reject, Request clarification** theo quyền.
- Tác động khi quá hạn: escalation, expiry hoặc chuyển người duyệt.

Không đưa **credential, access token, mật khẩu hoặc dữ liệu nhân sự nhạy cảm** vào email/chat notification. Nếu thông báo có nút phê duyệt nhanh, thao tác phải được **xác thực, chống giả mạo, ràng buộc request/version và kiểm tra approver authorization**.

**Một reminder được gửi thành công không chứng minh approver đã nhận/đọc hoặc có thẩm quyền quyết định.** Hệ thống nên ghi notification attempt và kết quả vận chuyển có thể quan sát, nhưng quyết định cuối cùng vẫn phải đến từ approval event hợp lệ.

### Tránh notification storm

Các worker có thể retry do lỗi network; cần idempotency và rate limit cho reminder. Không gửi hàng trăm email mỗi phút chỉ vì bộ quét deadline nhận cùng task nhiều lần. Với escalation lặp, nên có **chính sách số lần tối đa và kênh liên hệ tiếp theo**.

## 10. Escalation: chuyển cấp xử lý khi không có phản hồi

**Escalation** đưa task đến một chủ thể/nhóm có thẩm quyền cao hơn hoặc được chỉ định thay thế khi deadline không đạt. Nó không tự thay quyết định phê duyệt.

Ví dụ:

~~~mermaid
flowchart TD
    R["Access request hợp lệ"] --> A["Manager approval<br/>dueAt = T1"]
    A -->|"Approve"| O["Resource owner approval<br/>dueAt = T2"]
    A -->|"Reject"| X["Rejected"]
    A -->|"T1 quá hạn"| M["Escalation manager backup"]
    M -->|"Approve hợp lệ"| O
    M -->|"Quá hạn tiếp"| E["Hết hạn theo overall deadline"]
    O -->|"Approve"| P["Revalidate và Provision"]
    O -->|"Reject"| X
    O -->|"Timeout"| S["Escalate đúng resource owner delegate"]
    S -->|"Decision hợp lệ"| P
    S -->|"Không có thẩm quyền/overall expired"| E
~~~

Chính sách escalation cần định nghĩa:

1. **Trigger:** stepDueAt, overallDueAt hay một ngưỡng OLA.
2. **Target:** người duyệt dự phòng, manager cấp trên, owner group hoặc đội governance được ủy quyền.
3. **Authority:** người nhận có thật sự được phép duyệt role/tenant/data classification đó không?
4. **Decision semantics:** bước cũ còn mở hay bị khóa; quyết định nào có hiệu lực?
5. **Deadline mới:** có kéo dài step nhưng vẫn giữ overall deadline cứng không?
6. **Thông báo:** ai được báo, trường hợp nào cần ưu tiên sự cố.
7. **Audit:** lưu escalation chain và actor đã nhận nhiệm vụ.

**Escalation không đồng nghĩa auto-approve**. Một manager cấp trên có thể được quyền **điều phối** nhưng không phải **data owner** để duyệt quyền đọc dữ liệu nhạy cảm. Nếu thiếu người duyệt hợp lệ, trạng thái đúng thường là **BLOCKED/EXPIRED/NEEDS_APPROVER**, không phải cấp tạm admin.

## 11. Delegation và reassignment: không đánh mất thẩm quyền

**Delegation** là ủy quyền phê duyệt được quy định; **reassignment** là giao lại task cho một người khác. Hai hành động có thể khác nhau:

- **Delegation có trước:** resource owner đăng ký người thay thế trong kỳ nghỉ, với phạm vi role/tenant và thời hạn.
- **Reassignment do workflow:** hệ thống chuyển task do approver nghỉ phép, thôi việc, mất quyền hoặc quá hạn.
- **Escalation theo cấp:** task được gửi cho nhóm/quyền phê duyệt thay thế theo policy.

Một người được phân công lại **không tự có quyền phê duyệt** nếu không nằm trong danh sách có thẩm quyền. Hãy kiểm tra:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Identity** | Delegate đã được xác thực và còn active? |
| **Authority scope** | Có quyền duyệt role, tenant và classification này không? |
| **SoD** | Delegate có phải requester hoặc beneficiary bị cấm tự duyệt? |
| **Delegation validity** | Quyền ủy quyền còn trong thời gian đã duyệt? |
| **Original approval step** | Bước cũ bị đóng hay còn quyết định song song? |
| **Audit provenance** | Ai ủy quyền, ai chuyển task, ai quyết định cuối cùng? |

Khi người duyệt đã **Leaver**, approval task của họ phải được khóa và chuyển tới người có thẩm quyền hiện hành. Không tiếp nhận một click từ email cũ chỉ vì URL vẫn hoạt động.

## 12. Multi-stage approval: timeout của bước không phải của cả quy trình

Một yêu cầu quyền nhạy cảm có thể cần **manager → resource owner → security/PAM owner**. Các bước này có thể **tuần tự** hoặc **song song**, mỗi bước có deadline riêng.

### Phê duyệt tuần tự

Với bước tuần tự, bước sau thường chưa bắt đầu cho tới khi bước trước có quyết định hợp lệ. Nếu bước manager quá hạn thì cần escalation của bước manager; không được tự nhảy qua resource owner khi chính sách yêu cầu đủ cả hai.

### Phê duyệt song song

Ví dụ role export nhạy cảm cần **resource owner** và **security approver** đồng thời:

| Resource owner | Security approver | Kết quả nếu cần cả hai |
| --- | --- | --- |
| Approve | Approve | Có thể tiếp tục sau revalidation |
| Approve | Pending | Vẫn chờ |
| Approve | Timed out | Escalate/expire nhánh security, chưa cấp |
| Reject | Approve | Reject theo policy |
| Approve | Reject | Reject |
| Timed out | Timed out | Chưa có đầy đủ phê duyệt, không cấp |

Nếu một bước bị **Reject**, engine cần xác định có đóng các task còn lại hay giữ audit cho chúng. Với n-of-m quorum, cần văn bản policy quy định **ai đủ điều kiện tham gia quorum**; không đếm một approve từ người không có thẩm quyền.

**Mốc hoàn tất tổng** phải tính trên toàn request, tránh một chuỗi escalation khiến mỗi bước cứ được thêm thời gian và yêu cầu không bao giờ kết thúc.

## 13. SoD: timeout không được dùng để bỏ qua người kiểm soát độc lập

**Separation of Duties (SoD)** ngăn một người nắm những trách nhiệm xung đột, chẳng hạn tự yêu cầu, tự phê duyệt và tự cấp quyền quản trị.

| Tình huống timeout | Rủi ro | Cách kiểm soát |
| --- | --- | --- |
| Người duyệt chính quá hạn; hệ thống giao lại cho chính requester | Self-approval | Loại requester khi policy yêu cầu độc lập |
| Approver là beneficiary của role | Tự cấp đặc quyền | Kiểm tra beneficiary/role và conflict |
| Resource owner quá hạn; chuyển cho provisioning operator | Actor kỹ thuật tự duyệt | Phê duyệt phải đến từ authority được ủy quyền |
| Security review quá hạn; tự đánh dấu pass | Bỏ qua kiểm soát rủi ro | Hard gate, escalation trong security |
| Người duyệt đã mất role nhưng callback cũ đến muộn | Quyết định trái thẩm quyền | Recheck authority tại thời điểm accept decision |

Một workflow có thể cho phép **ngoại lệ break-glass** theo playbook riêng, nhưng không nên biến mọi timeout thành break-glass. Quyền khẩn cấp phải có **điều kiện kích hoạt, phạm vi tối thiểu, thời hạn, theo dõi độc lập và review sau sự kiện**.

## 14. Phê duyệt rủi ro cao: thời hạn không thay nguyên tắc an toàn

Những role như **IAM administrator**, **production database owner**, **secret reader** hoặc **payment approver** có tác động lớn. Khi timeout:

1. **Không tự động chấp thuận** chỉ vì mức ưu tiên công việc cao.
2. Đánh giá có cần **PAM/JIT** thay quyền thường trực không.
3. Chuyển tới **approver dự phòng cùng mức thẩm quyền**, không chuyển sang bất kỳ người rảnh nào.
4. Giữ **SoD** giữa requester, beneficiary, approver và provisioning actor.
5. Kiểm tra **phishing-resistant MFA/step-up** nếu chính sách yêu cầu ở thời điểm duyệt hoặc dùng quyền.
6. Đặt **thời hạn quyền** phù hợp nhiệm vụ và expiry/revocation tự động.
7. Audit đầy đủ quyền đã yêu cầu, người duyệt, lý do, hạn và effective access.

**Nhu cầu cấp bách không tự là chứng cứ đủ để bỏ qua quyền quyết định của resource owner.** Nếu ảnh hưởng hoạt động nghiêm trọng, sử dụng quy trình incident/break-glass được ủy quyền riêng, có phạm vi chặt và hậu kiểm.

## 15. Approval timeout khác auto-approval theo chính sách

**Auto-approval** có thể hợp lệ khi tổ chức **đã phê duyệt trước chính sách tự động cấp quyền**, ví dụ:

- Joiner có identity đã xác minh, job code khớp và ứng dụng nằm trong **birthright access**.
- Quyền Viewer chỉ áp dụng nội bộ dự án đã có entitlement nền tảng.
- Request trong giới hạn role, tenant, duration và không có SoD hoặc risk flag.

Khi đó hệ thống có thể không cần một approver con người cho request cụ thể, nhưng quyết định phải **dựa trên policy và bằng chứng điều kiện**.

| Cơ chế | Căn cứ cho phép | Đánh giá |
| --- | --- | --- |
| Auto-approval đã được phê duyệt | Policy, eligibility, source/version, scope và audit | Có thể phù hợp với role thấp rủi ro |
| Approval bởi người có thẩm quyền | Quyết định hợp lệ, ràng buộc request/version | Phù hợp với role cần review |
| Auto-approve do im lặng quá hạn | Không có quyết định hoặc rule hợp lệ cho quyền cụ thể | **Không chấp nhận làm mặc định an toàn** |

Trong mọi trường hợp, **quyền được cấp ở API/resource server phải còn hợp lệ theo RBAC/ABAC**, không phải cứ approval workflow kết thúc là có thể bỏ qua policy kiểm tra tại request.

## 16. Khi nào từ chối, hết hạn hoặc hủy yêu cầu?

Không phải timeout nào cũng phải chờ vô thời hạn. Có thể đặt **terminal policy**:

| Điều kiện | Hành động cân nhắc |
| --- | --- |
| Step quá hạn lần đầu | Reminder + escalation |
| Escalation quá hạn | Reassignment tới owner dự phòng hoặc EXPIRE |
| Overall deadline vượt quá | EXPIRE_WITHOUT_GRANT |
| Beneficiary không còn quan hệ hợp lệ | CANCEL/DENY theo chính sách, không tiếp tục chờ |
| Role catalog bị deprecated/đổi ngữ nghĩa | Revalidate và xin approval mới khi cần |
| Resource không còn thuộc scope yêu cầu | Hủy hoặc yêu cầu tạo request phù hợp |
| Contractor hết hợp đồng trước ngày dự kiến cấp | Từ chối cấp do không đủ eligibility |
| Requester chủ động rút yêu cầu | CANCEL nếu có quyền và chưa vượt điểm không thể hủy |
| Approval đến sau khi request terminal | Reject late decision, ghi audit |

**EXPIRED không nhất thiết đồng nghĩa REJECTED bởi approver.** EXPIRED cho biết không có quyết định hợp lệ trước hạn; REJECTED là quyết định từ chối hoặc kết quả policy. Phân biệt hai trạng thái giúp phân tích KPI và tránh quy trách nhiệm sai.

Một request hết hạn có thể được **tạo lại** khi nhu cầu còn hợp lệ, nhưng request mới cần kiểm tra **identity, employment, role version, scope và SoD** theo trạng thái hiện hành. Không sao chép một approval chưa có thành approval mới.

## 17. Joiner: tránh onboarding bị treo do approval timeout

**Joiner** thường gồm xác minh người mới từ **HRIS/nguồn bảo trợ**, tạo identity/account, cấp quyền ứng dụng và kiểm tra khả năng truy cập. Timeout có thể phát sinh khi manager/resource owner chậm duyệt role ngoài baseline.

### Nguyên tắc xử lý

1. Xác nhận **person/worker/employment ID** và ngày bắt đầu.
2. Phân biệt quyền **baseline được policy tự động cấp** với quyền phải duyệt riêng.
3. Với quyền phải duyệt, tính deadline theo ngày làm việc và mức rủi ro.
4. Gửi reminder/escalation đúng tuyến trước mốc Joiner cần quyền.
5. Nếu quá hạn, **không tự cấp role nhạy cảm** để kịp ngày đầu.
6. Nếu cần duy trì công việc, cân nhắc **role Viewer/quyền thay thế tối thiểu đã được phê duyệt độc lập**, không dùng admin.
7. Sau approval hợp lệ, provisioning qua IdP/SCIM/API và **readback** tại target.
8. Đóng Joiner theo từng cổng: identity verified, account created, authentication ready, entitlement verified.

**SCIM tạo account thành công không chứng minh role đang chờ phê duyệt đã được cấp.** Người dùng có thể đăng nhập SSO nhưng vẫn phải bị từ chối hành động chưa được approve.

### Ví dụ

Nhân viên mới cần quyền **Reports Viewer** theo baseline và **Reports Exporter** theo request có resource owner approval. Nếu Exporter timeout, có thể cho Viewer theo chính sách độc lập, nhưng **Exporter vẫn chưa được cấp**. Tránh biến một phần quyền hợp lệ thành lý do bỏ qua phần phê duyệt còn thiếu.

## 18. Mover: quyền mới timeout nhưng quyền cũ phải xử lý đúng

**Mover** thay đổi vai trò, dự án hoặc organization. Có thể xảy ra tình huống quyền mới **chưa được duyệt** trong khi quyền cũ đã hết căn cứ.

Ví dụ Lan chuyển **Atlas → Nova** tại 09:00 ngày 01/12:

| Quyền | Trước chuyển | Mong muốn sau chuyển | Nếu approval Nova timeout |
| --- | --- | --- | --- |
| READ Atlas | Có | Không | Không mặc định giữ vô thời hạn |
| ADMIN Atlas | Có trong nhiệm vụ cũ | Không | Thu hồi theo mốc và risk policy |
| READ Nova | Chưa có | Có khi được duyệt/baseline | Chờ hoặc dùng nhánh policy độc lập hợp lệ |
| ADMIN Nova | Không | Không trừ khi duyệt riêng | Không tự cấp |

**Không dùng timeout của quyền mới để tự động kéo dài quyền cũ**, đặc biệt quyền admin. Nếu nghiệp vụ cần bàn giao, phải có **exception riêng, owner, phạm vi và thời hạn**, không mặc định giữ role cũ khi waiting approval.

Khi Nova cuối cùng được phê duyệt, hệ thống vẫn phải kiểm tra **Lan còn thuộc Nova hay không**. Một approval sau nhiều tuần không còn hợp lệ nếu HR/project assignment lại thay đổi.

## 19. Leaver: không chờ approval timeout để thu hồi bắt buộc

Khi **Leaver** được xác nhận từ nguồn có thẩm quyền, những quyền phát sinh từ quan hệ đã kết thúc cần bị thu hồi theo quy định. **Quy trình revoke mang tính bắt buộc không được treo vì một approver không trả lời**, trừ trường hợp chính sách pháp lý hoặc quy trình đặc thù được định nghĩa rõ.

Những việc cần làm:

- **Vô hiệu hoặc giới hạn đăng nhập ở IdP** theo mốc Leaver.
- **SCIM deactivate** User/Group ở ứng dụng hỗ trợ.
- Thu hồi **role/ACL/grant/PAT/API key, session và token** ở nơi cần thiết.
- **Hủy những access request đang chờ** liên quan đến quan hệ đã kết thúc.
- Ngăn callback approve cũ, job retry hoặc provisioning pending **cấp lại quyền**.
- Đối soát trạng thái **effective access** ở target, không chỉ kiểm tra IdP.

Một người còn quan hệ hợp lệ tại **org-b** nhưng đã Leaver **org-a** có thể vẫn cần quyền của org-b. Phải **gắn request/approval với employmentRelation và tenant** để rút đúng phần quyền đã hết căn cứ.

**Phê duyệt đến muộn sau khi beneficiary đã Leaver không được làm account hoạt động trở lại.** Luồng cấp phải tái kiểm tra HR/sponsor state và version trước khi provision.

## 20. Tài khoản dịch vụ và workload: ai phê duyệt khi owner vắng mặt?

**Service account/workload identity** không có người dùng tương tác như nhân viên. Quyền của nó có thể yêu cầu approval từ **service owner, platform owner hoặc data/resource owner**, theo phạm vi.

| Yêu cầu workload | Người có thể duyệt theo policy | Cần kiểm tra thêm |
| --- | --- | --- |
| Bot đọc metric của production | Monitoring/Platform owner | serviceId, môi trường, scope và TTL |
| CI/CD deploy một service | DevOps/Production owner | SoD giữa commit/review/deploy, approval và hạn |
| Client credentials đọc billing | Billing data owner | Audience, tenant, secret và least privilege |
| Service principal được sửa IAM policy | IAM/Security privileged owner | Đặc quyền, tách nhiệm vụ, JIT/PAM nếu hỗ trợ |

Nếu owner workload đã nghỉ hoặc đổi nhóm, cần **chuyển ownership**, xác minh owner mới và **định tuyến lại approval**. Không tự động cho phép role của service principal chỉ vì người duyệt cũ timeout.

Một bot sản xuất vẫn có nhiệm vụ hợp lệ không nhất thiết phải bị xóa khi người sở hữu cũ Leaver; tuy nhiên cần rà soát **credential từng do người đó biết, PAT cá nhân, quyền và secret rotation**.

## 21. Đường xác thực và phân quyền sau khi approval hoàn tất

**Approval** và **authorization hiệu lực** là hai điều khác nhau. Một workflow APPROVED chỉ cho phép bắt đầu **provisioning** theo điều kiện; tại API vẫn có thể có:

- **IdP/SSO/MFA:** người dùng có phiên và mức xác thực thích hợp hay không?
- **OAuth/OIDC:** access token có issuer, audience, signature/introspection, thời hạn và scope phù hợp hay không?
- **RBAC:** role được gán đúng chủ thể và đúng organization/project chưa?
- **ABAC/PBAC:** thuộc tính employment, project, data classification và policy còn đạt không?
- **PEP:** API có thực thi quyết định trên object cụ thể hay không?
- **SCIM:** User/Group đã được đồng bộ đúng tại Service Provider chưa?

Ví dụ, một access request **Reports Editor** được duyệt sau escalation nhưng ứng dụng vẫn chỉ cấp Viewer. Không thể đánh dấu hoàn tất chỉ vì approval hợp lệ. Ngược lại, role được provisioned trước khi approval hợp lệ là **sai quy trình**, kể cả người dùng vẫn đăng nhập được.

**Approval timeout không phải OAuth token timeout.** Access token expiry, refresh token revocation, session expiry và grant expiry là những cơ chế khác, cần kiểm soát riêng trong JML.

## 22. Approval tới muộn: race condition phổ biến

Các tác nhân có thể cạnh tranh vào đúng thời điểm deadline:

~~~text
09:59:59.950   Approver nhấn Approve
10:00:00.000   dueAt của approval task
10:00:00.010   Timeout worker đánh dấu hết hạn
10:00:00.020   API approval nhận request chậm hơn
10:00:00.030   Provisioning worker nhận event cũ
~~~

Nếu không có quy tắc nhất quán, một hệ thống có thể vừa ghi **TIMED_OUT** vừa ghi **APPROVED**, rồi tạo role ngoài ý muốn.

### Những quy tắc cần thiết

1. Mỗi approval task có **id, state, version và dueAt** lưu bền vững.
2. Định nghĩa ranh giới thời gian rõ, ví dụ **server nhận và chấp nhận quyết định trước dueAt**; không lấy giờ client tự gửi để hợp thức hóa quyết định muộn.
3. **Compare-and-set/optimistic locking** hoặc transaction bảo đảm chỉ một transition cạnh tranh thắng.
4. API phải kiểm tra **approver còn thẩm quyền, request còn hợp lệ, decision version đúng**.
5. Timeout worker chỉ transition task còn **PENDING** theo phiên bản kỳ vọng.
6. Late approval của task đã **EXPIRED/CANCELLED/ESCALATED** bị từ chối hoặc phải tạo quyết định mới qua task hợp lệ, không áp dụng âm thầm.
7. Provisioning phải **revalidate** employment, approval và role/scope trước khi gọi target.

Một event được phát ra trước nhưng tới queue chậm **không tự bảo đảm tính hợp lệ**. Quyền chỉ được cấp dựa trên trạng thái workflow có thẩm quyền tại thời điểm cấp và chính sách hiệu lực.

## 23. Đúng thời điểm timeout: clock và scheduler

Worker quét deadline không nên dựa vào đồng hồ browser. Có thể dùng timestamp của cơ sở dữ liệu/hệ thống backend đã được quản lý và đồng bộ.

Những lưu ý:

- Lưu **dueAt dạng instant** để so sánh nhất quán; lưu thêm calendarId/timezone/policyVersion để giải thích.
- Dùng một nguồn thời gian tin cậy phù hợp kiến trúc, kiểm soát clock skew giữa các node.
- Deadline nên được đánh giá theo điều kiện rõ: **now >= dueAt** nếu policy coi dueAt là mốc kết thúc.
- Scheduler có thể chạy muộn; **thời điểm phát hiện** khác **thời điểm đáng lẽ hết hạn**.
- Không tính lại dueAt tùy tiện mỗi lần worker restart.
- Retry phải **idempotent**: một deadline không tạo nhiều escalation task không được kiểm soát.
- Bảo đảm không có lỗ hổng khi người dùng đổi timezone hiển thị.

Ví dụ một worker chạy mỗi phút có thể phát hiện task quá hạn muộn vài chục giây. Nếu tác vụ bắt buộc cần thời gian chính xác hơn, phải thiết kế job scheduling và kiểm tra **deadline ngay tại approval API**, không chỉ trông chờ batch worker.

## 24. Xử lý event và retry: trạng thái bền vững, idempotency, outbox

Approval workflow thường có nhiều hệ thống: portal → database → event bus → email/chat → approval API → IGA → SCIM/SaaS. Lỗi kết nối có thể làm event trùng hoặc thất lạc.

Một thiết kế có thể dùng:

1. **Persist request/task** với state, version, dueAt, approver và authority scope.
2. **Atomic transition** khi approve/reject/timeout/cancel theo version hiện hành.
3. **Transactional outbox** để ghi sự kiện tương ứng cùng transaction thay đổi trạng thái, nếu kiến trúc hỗ trợ.
4. **Idempotency key** để ngăn tạo escalation, notification hoặc provisioning lặp.
5. **At-least-once message consumption** với deduplication thay vì giả định chỉ có đúng một event.
6. **Readback** từ hệ thống đích sau provisioning nếu timeout làm trạng thái phản hồi không rõ.
7. **Reconciliation** định kỳ để bắt job lỗi, approval chưa hết hạn và quyền tồn dư.

### Ví dụ identity của một sự kiện

~~~json
{
  "eventId": "approval-timeout-event-209",
  "requestId": "access-req-1042",
  "approvalTaskId": "approval-task-77",
  "taskVersion": 6,
  "eventType": "APPROVAL_TIMED_OUT",
  "dueAt": "2026-11-25T10:00:00+07:00",
  "detectedAt": "2026-11-25T10:00:07+07:00",
  "nextAction": "ESCALATE",
  "escalationPolicyVersion": "approval-policy-v12"
}
~~~

**eventId** và **taskVersion** giúp deduplication/ordering, nhưng cần có kiểm tra trạng thái hiện hành chứ không chỉ tin số thứ tự từ một nguồn bên ngoài. Sự kiện nghiệp vụ có thể đến sai thứ tự; khi đó xử lý theo **source version, effectiveAt và workflow state**.

## 25. Mã giả kiểm tra timeout an toàn

Đoạn sau là **mã giả nghiệp vụ**, không phụ thuộc sản phẩm workflow cụ thể:

~~~text
handleApprovalDeadline(taskId, expectedVersion, nowInstant):
    beginTransaction()

    task = approvalStore.lockOrCompareVersion(taskId, expectedVersion)
    if task.notFound:
        rollback()
        return NOT_FOUND

    if task.state != PENDING_APPROVAL:
        commit()
        return NO_ACTION_ALREADY_TRANSITIONED

    if nowInstant < task.dueAt:
        commit()
        return NOT_DUE

    request = loadCurrentRequest(task.requestId)
    policy = loadApprovedPolicyVersion(request.policyReference)

    if request.isCancelledOrTerminal:
        markTaskClosedWithoutGrant(task)
        appendAuditEvent("CLOSED_AFTER_REQUEST_TERMINAL")
        commit()
        return CLOSED

    if not request.beneficiaryHasValidCurrentRelation():
        cancelRequestAndBlockProvisioning(request)
        appendAuditEvent("ELIGIBILITY_REVOKED")
        commit()
        return CANCELLED

    nextState = policy.timeoutActionFor(task, request)
    transitionTask(task, nextState, expectedVersion)

    writeOutboxEvent(
        idempotencyKey = task.id + task.version + nextState,
        event = "APPROVAL_DEADLINE_HANDLED",
        requestId = request.id,
        newState = nextState
    )
    appendAuditEvent("APPROVAL_TIMEOUT", task, nextState)

    commit()
    return nextState
~~~

Mã giả giả định có transaction/state store để ngăn cập nhật cạnh tranh. Trong triển khai thật, **loadCurrentRequest** và kiểm tra employment liên quan có thể cần xử lý bất đồng bộ; **không được giữ transaction dài khi gọi hệ thống HRIS từ xa** nếu không có thiết kế độ sẵn sàng phù hợp. Có thể lưu snapshot/version đáng tin và tái kiểm tra trước provisioning.

Điều bắt buộc: **hàm timeout không tự gọi grantRole** chỉ vì đã quá hạn. Quyền cấp phát phụ thuộc approval hoặc policy độc lập hợp lệ.

## 26. Mã giả chấp nhận quyết định phê duyệt

~~~text
submitApprovalDecision(taskId, actor, decision, expectedVersion, now):
    task = loadTaskWithConcurrencyControl(taskId, expectedVersion)
    request = loadRequest(task.requestId)

    if task.state != PENDING_APPROVAL:
        return CONFLICT_STALE_TASK
    if now >= task.dueAt:
        return EXPIRED_TASK
    if request.isTerminalOrCancelled:
        return CONFLICT_STALE_REQUEST

    if not actor.isAuthenticatedWithRequiredAssurance():
        return UNAUTHORIZED_OR_STEP_UP_REQUIRED
    if not approvalPolicy.isActorAuthorized(actor, task, request):
        return FORBIDDEN
    if approvalPolicy.violatesSeparationOfDuties(actor, request):
        return FORBIDDEN_SOD

    if not matchesApprovedRequestFingerprint(
        request.beneficiary,
        request.roleId,
        request.tenant,
        request.resourceScope,
        request.duration,
        request.roleCatalogVersion
    ):
        return REVALIDATION_REQUIRED

    atomicallyRecordDecisionAndTransition(task, decision, expectedVersion)
    emitAuditAndWorkflowEvent()
    return DECISION_ACCEPTED
~~~

Đây là cách **định nghĩa thời điểm chấp nhận quyết định**; chính sách có thể chọn một ranh giới khác nếu được quy định, nhưng phải nhất quán. Approval gửi đúng trước dueAt mà được hệ thống chấp nhận thành công vẫn phải qua **revalidation trước provisioning**, nhất là khi có Mover/Leaver hoặc thay đổi role catalog.

**Không dùng timestamp do client cung cấp để backdate approval**. Một email có thời gian gửi trước hạn nhưng tới workflow engine sau khi request đã EXPIRED không tự khôi phục quyền, trừ khi có quy trình khiếu nại/khôi phục đã được định nghĩa và kiểm chứng.

## 27. Dữ liệu cần lưu để điều tra timeout

Một bản ghi approval task nên chứa:

| Trường | Mục đích |
| --- | --- |
| **requestId/taskId** | Xác định request và bước cụ thể |
| **requesterId/beneficiaryId** | Biết ai yêu cầu và ai nhận quyền |
| **employmentRelationId** | Gắn quyền với quan hệ lao động/tenant đúng |
| **roleId/catalogVersion** | Biết quyền có ý nghĩa gì lúc xét duyệt |
| **resourceScope/targetTenant** | Giới hạn tài nguyên được yêu cầu |
| **approvalPolicyId/version** | Căn cứ routing, timeout và exception |
| **assignedApproverIds/authorityScope** | Ai có quyền quyết định |
| **createdAt/activatedAt/dueAt** | Thời điểm bắt đầu và deadline |
| **calendarId/timezone** | Giải thích cách tính ngày làm việc |
| **state/version** | Chống transition cạnh tranh |
| **reminder/escalationCount** | Theo dõi hành động khi gần/quá hạn |
| **overallDueAt** | Giới hạn toàn workflow |
| **decisionAt/decisionBy** | Bằng chứng phê duyệt/từ chối nếu có |
| **escalationHistory** | Lưu chuỗi giao/ủy quyền và thời hạn |
| **targetProvisioningStatus** | Phân biệt approved với provisioned |
| **lastVerifiedAt** | Thời điểm quyền hiệu lực được kiểm chứng |

Không cần chép toàn bộ hồ sơ HR hoặc credential vào task. Lưu **identity references, policy/version và thông tin tối thiểu** phục vụ decision/audit.

## 28. Ví dụ JSON của workflow đã timeout

~~~json
{
  "requestId": "access-req-1042",
  "requesterIdentityId": "iam-manager-17",
  "beneficiaryIdentityId": "iam-user-482",
  "employmentRelationId": "emp-org-a-01",
  "targetSystem": "reports-saas",
  "targetTenant": "org-a",
  "roleId": "reports.editor.v2",
  "roleCatalogVersion": "roles-v24",
  "resourceScope": "project-atlas",
  "status": "ESCALATED",
  "approvalTask": {
    "taskId": "approval-task-77",
    "previousApproverRef": "atlas-resource-owner",
    "currentApproverRef": "atlas-backup-owner",
    "state": "PENDING_APPROVAL",
    "attempt": 2,
    "version": 7,
    "activatedAt": "2026-11-25T10:00:07+07:00",
    "dueAt": "2026-11-26T10:00:00+07:00"
  },
  "overallDueAt": "2026-11-28T17:00:00+07:00",
  "approvalPolicyVersion": "approval-policy-v12",
  "lastTimeoutEventAt": "2026-11-25T10:00:07+07:00",
  "provisioningStatus": "NOT_STARTED",
  "effectiveAccessStatus": "NOT_GRANTED"
}
~~~

Ví dụ này minh họa **request đã escalation**, task mới đang chờ và **chưa provision quyền**. Các field mang tính thiết kế nội bộ; không phải schema bắt buộc của SCIM/OIDC.

Trong production, **effectiveAccessStatus = NOT_GRANTED** chỉ nên dùng khi có bằng chứng quyền chưa được cấp; nếu không có khả năng đọc target thì dùng **UNKNOWN/UNVERIFIED**, không suy từ trạng thái workflow. Có thể trước đó người dùng đã có một role khác cung cấp cùng quyền, vì vậy request mới chưa cấp không đồng nghĩa API chắc chắn Deny.

## 29. Approval timeout và lỗi HTTP/API

Approval API cần trả lỗi phù hợp khi quyết định đến muộn hoặc không đủ quyền.

| Tình huống | Phản hồi có thể phù hợp | Lưu ý |
| --- | --- | --- |
| Không có authentication hợp lệ | **401 Unauthorized** | Theo contract AuthN |
| Người dùng không được duyệt task này | **403 Forbidden** | Không tiết lộ dữ liệu nhạy cảm |
| Task đã timeout và chuyển trạng thái | **409 Conflict** hoặc **410 Gone** tùy API contract | Không tiếp nhận quyết định cũ |
| Approval request đã bị hủy | **409/410** theo thiết kế | Không mở lại chỉ bằng POST |
| Dữ liệu role/tenant không còn hợp lệ | **400/409/422** tùy contract | Yêu cầu sửa hoặc tạo lại |
| Workflow/PIP không sẵn sàng | **503 Service Unavailable** có thể phù hợp | Không tự cấp quyền vì lỗi |
| Gửi decision hợp lệ, hệ thống ghi nhận | **2xx** | Chỉ chứng minh decision được nhận, chưa chứng minh role đã provision |

Ví dụ một lỗi do task đã quá hạn:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "APPROVAL_TASK_EXPIRED",
  "requestId": "access-req-1042",
  "taskId": "approval-task-77",
  "message": "Approval task is no longer actionable."
}
~~~

Đây là **API minh họa**, không phải mã lỗi HTTP do SCIM/OAuth quy định cho approval timeout. Trạng thái chuẩn cụ thể cần tuân theo contract của sản phẩm.

## 30. Approval timeout khác provisioning timeout

Hai lỗi có phương thức xử lý rất khác:

| Tình huống | Điều biết chắc | Điều chưa biết | Phản ứng đúng |
| --- | --- | --- | --- |
| **Approval timeout** | Chưa có quyết định hợp lệ trước deadline | Quyền đã có sẵn từ nguồn khác hay chưa | Không cấp quyền mới chỉ vì timeout; escalation/expiry |
| **Provisioning timeout** | Đã có approval, connector gửi yêu cầu nhưng không có response đúng hạn | Target có thể đã cấp role | Đọc lại target trước khi retry, tránh duplicate |
| **Revocation timeout** | Lệnh thu hồi đã phát nhưng chưa có bằng chứng hoàn tất | Token/role có thể còn dùng được | Ưu tiên kiểm chứng quyền tồn dư, xử lý theo SLA cắt quyền |

Một connector SCIM **PATCH Group** có thể thành công tại Service Provider nhưng response bị mất. Nếu workflow retry mù sau timeout, có thể tạo event trùng, lẫn trạng thái hoặc kéo dài thời hạn sai. Với provisioning, cần **idempotency và reconciliation**.

**Không dùng quy tắc approval timeout để xử lý vấn đề technical provisioning.** Nếu approval đã hợp lệ mà SCIM/API lỗi, task đúng là của provisioning/operations, không phải yêu cầu approver duyệt lại vô hạn khi không có thay đổi quyền.

## 31. Monitoring: phát hiện workflow tắc nghẽn trước khi quá hạn

Một hệ thống vận hành tốt cần nhận diện **nguyên nhân timeout**, không chỉ đếm request trễ.

| Tín hiệu | Ý nghĩa | Hành động gợi ý |
| --- | --- | --- |
| Nhiều task chờ cùng một approver | Bottleneck cá nhân/owner | Cấu hình backup và điều phối công việc |
| Nhiều owner không còn ACTIVE | Owner lifecycle không được quản lý | Đồng bộ HR/IGA, reassignment |
| Role nhạy cảm luôn timeout | Approval chain quá dài hoặc thiếu thẩm quyền | Rà soát workflow, không bỏ security gate |
| Thời gian thực tế gần dueAt thường xuyên | OLA có thể chưa phù hợp | Xem lịch làm việc và capacity |
| Escalated nhiều lần nhưng không kết thúc | Thiếu overall deadline | Áp hạn cứng và terminal policy |
| Reminder gửi thất bại | Notification integration lỗi | Giám sát kênh và retry an toàn |
| Task có dueAt trong quá khứ nhưng vẫn PENDING | Scheduler hoặc state transition lỗi | Repair job và reconciliation |
| APPROVED sau EXPIRED | Race condition hoặc API thiếu guard | Kiểm tra atomic transition và audit |
| Role cấp khi approval vẫn PENDING | Lỗ hổng workflow/enforcement | Điều tra bảo mật và thu hồi trái policy |

Các metric nên được phân loại theo **role risk, application, tenant, approver group, loại beneficiary và JML event**. Một số lượng timeout tổng thể thấp không chứng minh những role đặc quyền đã được xử lý đúng.

## 32. KPI và SLO của approval workflow

| KPI | Cách hiểu |
| --- | --- |
| **On-time approval rate** | Tỷ lệ task có quyết định hợp lệ trước dueAt |
| **Approval timeout rate** | Tỷ lệ task timeout trong nhóm được đo |
| **Escalation rate** | Tỷ lệ task phải chuyển cấp |
| **Mean/median/p95 time to decision** | Độ trễ phản hồi, nên phân loại theo loại role |
| **Timeout to resolution time** | Từ lúc quá hạn tới khi có kết quả hợp lệ/terminal |
| **Pending beyond overall deadline** | Số request vi phạm hạn tổng mà chưa xử lý |
| **Unauthorized late approval attempts** | Số lần quyết định không hợp lệ sau timeout |
| **Approver availability coverage** | Tỷ lệ role có owner và backup hợp lệ |
| **Time to verified access** | Từ khi được duyệt đến khi quyền thực sự có hiệu lực |
| **Leaver pending requests cancelled** | Tỷ lệ request đang chờ được khóa sau Leaver |
| **Privilege granted without approval** | Phát hiện quyền cấp ngoài policy, cần ưu tiên cao |
| **Audit completeness** | Tỷ lệ task có lịch sử assignment, decision, escalation và proof |

Ví dụ công thức:

~~~text
Approval timeout rate
  = Số approval task đến hạn mà chưa có quyết định hợp lệ
    / Tổng approval task đã đến hạn trong kỳ

On-time approval rate
  = Số task có quyết định hợp lệ trước dueAt
    / Tổng task có dueAt thuộc kỳ đo
~~~

Phải xác định rõ **denominator** và xử lý task đã hủy trước hạn, task chỉ auto-approved, task pause và task bị thay thế; không nên so sánh giữa các nhóm nếu cách tính khác nhau. **Approval nhanh không phải mục tiêu duy nhất**: bỏ qua SoD và resource-owner approval để cải thiện thời gian là làm giảm an toàn.

## 33. Audit và bảo vệ bằng chứng

Một sự kiện timeout nên truy vết được từ **request ban đầu → task/approver → dueAt → reminder → escalation/expiry → quyết định nếu có → provisioning/effective access**.

Ví dụ audit record:

~~~json
{
  "eventId": "approval-audit-901",
  "correlationId": "access-req-1042",
  "approvalTaskId": "approval-task-77",
  "eventType": "APPROVAL_TIMEOUT",
  "beneficiaryRef": "iam-user-482",
  "roleRef": "reports.editor.v2",
  "targetRef": "reports-saas/org-a/project-atlas",
  "policyVersion": "approval-policy-v12",
  "approvalTaskVersion": 6,
  "originalApproverRef": "atlas-resource-owner",
  "newApproverRef": "atlas-backup-owner",
  "dueAt": "2026-11-25T10:00:00+07:00",
  "detectedAt": "2026-11-25T10:00:07+07:00",
  "transition": "PENDING_APPROVAL_TO_ESCALATED",
  "decision": "NONE",
  "provisioningTriggered": false,
  "occurredAt": "2026-11-25T10:00:07+07:00"
}
~~~

Những điểm cần lưu:

- Ai và role nào được yêu cầu, thuộc tenant/resource nào?
- Bước đã được giao cho ai, quyền phê duyệt từ đâu, có delegation không?
- Deadline được tính theo policy/calendar/version nào?
- Reminder và escalation đã được gửi/nhận ra sao?
- Có approve/reject đến muộn, trùng hoặc trái SoD không?
- Có job provisioning nào chạy trước approval hoặc sau terminal state không?
- Quyền thực tế tại target đang **ALLOW, DENY hay UNKNOWN**?

**Không log access token, refresh token, session cookie, mật khẩu, private key, seed MFA hoặc toàn bộ hồ sơ HR.** Log approval có thể tiết lộ vai trò đặc quyền, tổ chức, dự án và danh tính, nên phải phân quyền truy cập, tối thiểu hóa và lưu giữ theo policy.

## 34. Xử lý sự cố: phê duyệt quá hạn nhưng role đã được cấp

Đây là trường hợp nghiêm trọng hơn một request bị chậm.

~~~mermaid
flowchart TD
    A["Phát hiện role cấp khi approval timeout"] --> B["Xác minh request, beneficiary, role, tenant và target"]
    B --> C{"Có căn cứ cấp quyền độc lập hợp lệ?"}
    C -->|"Có"| D["Đối chiếu policy, approval và effective access"]
    C -->|"Không / chưa xác minh"| E["Đánh giá và chặn quyền trái chính sách theo playbook"]
    D --> F["Kiểm tra logic state, event và provisioning"]
    E --> F
    F --> G["Tìm race, auto-approve sai, retry, callback muộn"]
    G --> H["Sửa workflow guard, approval API và provisioning revalidate"]
    H --> I["Kiểm thử timeout, SoD, JML và API quyền hiệu lực"]
    I --> J{"Đạt bằng chứng?"}
    J -->|"Không"| K["Giữ incident mở, owner và deadline"]
    K --> I
    J -->|"Có"| L["Audit, review và đóng incident"]
~~~

Quy trình:

1. Xác định **role và quyền thực tế** tại API, không chỉ tên nhóm.
2. Kiểm tra có **baseline policy, approval khác hoặc grant còn hiệu lực** giải thích quyền không.
3. Nếu quyền trái policy, áp dụng **biện pháp chặn an toàn** theo quyền hạn.
4. Điều tra **task state/version, timestamp, event bus, retry, approval callback**.
5. Kiểm tra những request khác có thể bị cùng lỗi.
6. Sửa **atomic transition, SoD, issuer/actor validation và provisioning gate**.
7. Đối soát token/session/ACL có thể còn được chấp nhận dù đã xóa role.
8. Ghi nhận tác động thực tế và những giới hạn bằng chứng trong báo cáo.

Một kết quả **SCIM update thành công** hoặc **IdP group đã xóa** không chứng minh mọi token/phiên và direct ACL đã vô hiệu. Cần readback và kiểm thử quyền thực tế theo mức rủi ro.

## 35. Kiểm thử deadline, escalation và race condition

Một bộ kiểm thử cần bao gồm cả trường hợp bình thường và các ranh giới:

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Approver hợp lệ duyệt trước dueAt | Decision được ghi đúng, qua bước kế tiếp |
| T02 | Approver không phản hồi đến hạn | Timeout event/transition đúng policy, không grant |
| T03 | Deadline rơi vào ngày nghỉ | Tính theo đúng business calendar nếu policy yêu cầu |
| T04 | Approver ở múi giờ khác | dueAt tuyệt đối nhất quán, hiển thị đúng |
| T05 | Approver refresh giao diện nhiều lần | dueAt không bị reset |
| T06 | Hệ thống restart sau khi đặt timer | Deadline giữ nguyên và được quét lại |
| T07 | Notification retry | Không gửi vô hạn hoặc tạo nhiều task |
| T08 | Timeout worker chạy hai lần | Transition/escalation idempotent |
| T09 | Approve gần đồng thời với timeout | Chỉ một transition hợp lệ thắng |
| T10 | Approve sau EXPIRED | Bị từ chối, không cấp quyền |
| T11 | Delegate không có authority trên tenant | Không được duyệt |
| T12 | Delegate trùng beneficiary và vi phạm SoD | Bị chặn |
| T13 | Multi-stage: 1 bước duyệt, 1 bước timeout | Không provision khi thiếu bước bắt buộc |
| T14 | Overall deadline đến trước step mới | Request kết thúc theo policy, không kéo dài vô hạn |
| T15 | HR thay đổi sang Mover khi chờ | Revalidate role và scope trước quyết định/cấp |
| T16 | Beneficiary Leaver trước khi approve | Cancel/deny, ngăn provisioning |
| T17 | Event Joiner cũ đến sau Leaver | Không mở lại access request đã hết căn cứ |
| T18 | Role catalog v1 đổi permission thành v2 | Tái kiểm tra approval fingerprint |
| T19 | High-risk role timeout | Không tự auto-approve, escalated đúng tuyến |
| T20 | Provisioning timeout sau approval | Readback target trước retry; không nhầm approval timeout |
| T21 | Workflow engine không đọc được HR/PIP | Không tự grant, đánh dấu BLOCKED/UNKNOWN |
| T22 | Workload owner đã Leaver | Route tới owner hợp lệ, không tự cấp role cho bot |

**Test timeout nên điều khiển clock giả lập** ở unit/integration test để kiểm tra trước, đúng và sau dueAt, thay vì chờ theo thời gian thật. Integration test cần xác minh cả database transition, outbox, notification, event consumer và hành động tại target.

Không chỉ kiểm tra **status** của workflow: phải có negative test chứng minh **API/resource server không cho người chưa có phê duyệt hợp lệ thực hiện hành động ngoài quyền**.

## 36. Tình huống thực hành: Exporter timeout trước kỳ báo cáo

**Bối cảnh:** Bộ phận Tài chính cần nhân viên Thu xuất báo cáo doanh thu của **org-a / Dự án Atlas** vào thứ Sáu. Thu đã có role Viewer hợp lệ, nhưng quyền **ReportExporter** yêu cầu resource owner phê duyệt vì liên quan dữ liệu nhạy cảm. Request được tạo và giao approver theo policy với deadline 12:00 thứ Năm.

### Diễn biến

1. **Thứ Ba 09:00:** Thu tạo access request Exporter, nêu lý do, tenant, resource, thời hạn từ thứ Sáu tới cuối ngày làm việc.
2. **Thứ Ba 09:01:** Workflow xác minh employment ACTIVE, role catalog, SoD và điều kiện; task gửi đến resource owner.
3. **Thứ Năm 08:00:** Reminder được gửi, chưa có decision.
4. **Thứ Năm 12:00:** Step timeout; engine ghi event, chuyển đến backup resource owner đã được ủy quyền.
5. **Thứ Năm 15:00:** Backup owner xác thực và phê duyệt đúng scope sau khi xem nhu cầu.
6. **Thứ Năm 15:01:** Provisioning revalidate Thu còn thuộc Atlas, role/vùng dữ liệu chưa thay đổi và role chưa hết thời hạn.
7. **Thứ Sáu:** Role Exporter được kích hoạt theo mốc đã duyệt, API chỉ cho EXPORT đúng báo cáo thuộc phạm vi được phép.
8. **Cuối hạn:** Hệ thống phải revoke/expire quyền và xác minh không còn khả năng Export ngoài thời điểm phê duyệt.

### Kịch bản phụ A: owner dự phòng cũng timeout

Nếu backup owner không phản hồi và **overall deadline** đến, request chuyển **EXPIRED_WITHOUT_GRANT**. Thu vẫn có thể dùng Viewer đã được duyệt độc lập, nhưng không thể EXPORT chỉ vì deadline nghiệp vụ đang đến gần. Nếu xuất dữ liệu thật sự khẩn cấp, cần playbook riêng có kiểm soát, không cấp quyền ngầm.

### Kịch bản phụ B: Thu chuyển dự án trong lúc chờ

Giả sử HR/project registry xác nhận Thu đã chuyển sang Nova trước khi backup duyệt. Approval cũ cho Atlas không còn đủ điều kiện. Workflow phải **revalidate beneficiary, resource scope và assignment**, từ chối hoặc yêu cầu request mới; không provision Exporter cho Atlas.

### Kịch bản phụ C: approval cũ đến muộn

Approver ban đầu bấm link trong email sau khi bước của họ đã bị escalation. Hệ thống trả **CONFLICT_STALE_TASK**, lưu audit và không tạo decision thứ hai. Nếu role đã provision theo quyết định backup hợp lệ thì event muộn cũng không được thay đổi hạn hoặc scope đã duyệt.

### Câu hỏi tự kiểm tra

**Câu 1:** Quá deadline có thể coi như resource owner đã đồng ý không?

**Trả lời:** Không. Timeout không phải phê duyệt. Phải áp dụng escalation, expiry hoặc chính sách độc lập đã được phê duyệt.

**Câu 2:** Escalation sang manager của requester có luôn hợp lệ không?

**Trả lời:** Không. Người nhận phải có quyền phê duyệt đúng role, tenant, dữ liệu và không vi phạm SoD.

**Câu 3:** Vì sao phải kiểm tra lại quan hệ công việc khi approval đến muộn?

**Trả lời:** Vì beneficiary có thể đã Mover/Leaver, role hoặc tài nguyên đã đổi; điều kiện lúc tạo request không còn đúng.

**Câu 4:** Nếu connector provisioning timeout nhưng role đã APPROVED, có nên gửi SCIM request lặp ngay không?

**Trả lời:** Không nên retry mù. Phải kiểm tra target trước vì thay đổi đầu tiên có thể đã được áp dụng.

**Câu 5:** Khi role Exporter đã có hiệu lực rồi tới accessEndAt, hệ thống có thể chờ một approval mới để thu hồi không?

**Trả lời:** Không nên. Thu hồi theo hạn/policy là nghĩa vụ độc lập; nếu có ngoại lệ gia hạn phải được phê duyệt riêng trước khi giữ quyền.

## 37. Checklist thiết kế Approval timeout

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Đã định nghĩa timeout của task khác overall request? | State machine, stepDueAt và overallDueAt |
| Deadline có đúng calendar và timezone? | Business day/continuous time, holidays và dueAt |
| Có định nghĩa nguồn kích hoạt và pause/resume? | activatedAt, pause reason, policy version |
| Có nhắc việc trước hạn? | Reminder plan, delivery status, idempotency |
| Có escalation target hợp lệ? | Authority scope, backup owner, mapping phê duyệt |
| Có kiểm tra approver và SoD tại thời điểm quyết định? | AuthN, MFA/assurance, actor authorization, self-approval guard |
| Timeout có mặc định không cấp quyền? | Không có đường grant chỉ vì task quá hạn |
| Role rủi ro cao có tuyến riêng? | Resource/security/PAM approval và hard gate |
| Có phân biệt auto-approval policy với silence? | Policy-based approval được phê duyệt và audit |
| Có ngăn quyết định đến muộn? | Atomic transition, state/version, dueAt validation |
| Có chống event trùng và worker retry? | Idempotency keys, outbox, deduplication |
| Có giới hạn overall workflow? | Max escalation, terminal action |
| Có revalidate trước provisioning? | Employment, role version, tenant, scope, SoD và current state |
| Joiner có xử lý quyền baseline độc lập? | Không chờ role ngoài baseline để hoàn thành những cổng hợp lệ |
| Mover có thu hồi quyền cũ dù quyền mới timeout? | Recompute expected access, remove stale grants |
| Leaver có hủy pending requests? | Cancel, block late approve và retry |
| Workload có owner/approver còn hợp lệ? | Service catalog và delegate authority |
| Có phân biệt approval timeout với provisioning timeout? | Correct state, target readback và retry policy |
| Có xác minh quyền thực tế ở target? | Assigned/effective access, positive và negative API tests |
| Có log và metric đủ giải thích? | Request/task/actor/dueAt/policy/escalation/decision/enforcement |
| Có kiểm tra độ trễ và lịch ngày nghỉ? | Boundary tests, fake clock và multi-timezone tests |
| Có xử lý trường hợp policy/PIP lỗi an toàn? | Fail-closed, BLOCKED/INDETERMINATE thay vì Permit |

## 38. Tổng kết

**Approval timeout** là tình huống một **bước hoặc toàn bộ quy trình xét duyệt quyền truy cập quá hạn mà chưa có quyết định hợp lệ**. Đây là vấn đề vừa về hiệu suất vận hành, vừa về kiểm soát bảo mật. Cơ chế đúng cần **deadline rõ ràng, lịch làm việc và múi giờ chính xác, nhắc việc, escalation/delegation có thẩm quyền, giới hạn tổng thời gian, state machine chặt, ngăn quyết định đến muộn và lưu audit**.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** xác định quan hệ và thời điểm hiệu lực; **IAM/IGA** quản lý request, role catalog, eligibility, SoD và approval; **IdP/SSO/MFA** xác thực approver và beneficiary; **SCIM/API provisioning** áp dụng User/Group/role sau phê duyệt; **RBAC/ABAC/PBAC và PEP** kiểm soát quyền thực sự tại tài nguyên; còn **service/workload identities** cần owner và approval riêng. **Timeout không được biến thành phê duyệt ngầm**, và quyết định từng hợp lệ vẫn phải được **tái kiểm tra trước khi cấp quyền**, đặc biệt sau Mover/Leaver. Chỉ khi **quyền được cấp đúng căn cứ, được đối soát ở target và thu hồi theo hạn**, tổ chức mới vừa bảo đảm thời gian xử lý yêu cầu vừa giảm **quyền truy cập tồn dư**.
