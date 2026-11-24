# Phê duyệt sau sự kiện trong Emergency access: hậu kiểm quyền khẩn cấp có trách nhiệm

Lúc 02:15, hệ thống xác thực tập trung gặp sự cố đúng khi đội vận hành cần khôi phục một dịch vụ production quan trọng. Kênh phê duyệt quyền thông thường không khả dụng; kỹ sư trực ca sử dụng **quyền truy cập khẩn cấp (emergency access)** được tổ chức chuẩn bị trước để xử lý. Đến 03:10, hệ thống hoạt động trở lại, phiên quyền cao được đóng. Câu hỏi tiếp theo không phải chỉ là “sự cố đã hết chưa?” mà còn là: **Ai đã dùng đặc quyền, có thật sự thuộc trường hợp khẩn được cho phép, đã làm những gì, ai đủ thẩm quyền đánh giá độc lập, quyền đã được thu hồi thật chưa và hành động nào cần khắc phục?**

Trong IAM, **phê duyệt sau sự kiện (post-event approval/post-event review or ratification)** là bước xem xét có thẩm quyền **sau khi đã xảy ra việc sử dụng quyền khẩn cấp**, dựa trên bằng chứng và chính sách. Mục đích là **xác định tính chính đáng, tính tương xứng, kết quả, sai lệch và trách nhiệm**, không phải dùng chữ “Approved” để hợp thức hóa mọi hành động đã diễn ra.

Bài thuộc chương **Emergency access**, đề tài trực tiếp **Phê duyệt sau sự kiện**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun bao gồm quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền tới rà soát và thu hồi khi đổi vai trò; liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

Sau bài học, người học có thể:

- Phân biệt **phê duyệt trước**, **quyền khẩn được định nghĩa sẵn**, **hậu kiểm** và **quyết định chấp nhận rủi ro**.
- Thiết kế quy trình **kích hoạt → thông báo → thu hồi → bảo toàn chứng cứ → đánh giá độc lập → xử lý sai lệch → đóng hồ sơ**.
- Xác định người đánh giá đủ thẩm quyền, chống **tự phê duyệt** và xung đột **Separation of Duties (SoD)**.
- Thu thập bằng chứng từ **PAM, IdP, SSO, hệ thống đích, cloud/API, SCIM, session/token** mà không làm lộ bí mật.
- Phân loại quyết định **hợp lệ, hợp lệ có khắc phục, chưa đủ bằng chứng hoặc không hợp lệ**, và xử lý tương ứng.
- Liên kết hậu kiểm với **JML, privilege creep, tài khoản break-glass, service/workload principal và quyền tồn dư**.
- Xây dựng checklist, dữ liệu kiểm toán và KPI đo tốc độ hậu kiểm, hiệu lực thu hồi, ngoại lệ quá hạn.

## 1. Phê duyệt sau sự kiện là gì?

Trong hoạt động bình thường, một request quyền đặc biệt nên được **xác thực danh tính, xét điều kiện, phê duyệt đúng người và cấp theo phạm vi/thời hạn** trước khi quyền được sử dụng. Tuy nhiên, trong tình huống khẩn thực sự, hệ thống phê duyệt có thể không khả dụng hoặc việc chờ có thể làm thiệt hại nghiêm trọng hơn. **Emergency access** là cơ chế ngoại lệ được chuẩn bị và quản trị trước, dành cho những kịch bản được xác định rõ.

**Phê duyệt sau sự kiện** là quyết định và hồ sơ đánh giá **việc sử dụng quyền đã xảy ra**, chứ **không phải quyền cho phép ngược thời gian**.

### 1.1. Ba thời điểm cần tách

| Thời điểm | Kiểm soát | Điều cần chứng minh |
| --- | --- | --- |
| **Trước sự kiện** | Chính sách và phương án emergency access được phê duyệt, giới hạn kịch bản, principal, owner và giám sát. | Tổ chức đã định nghĩa khi nào và ai được dùng cơ chế khẩn. |
| **Trong sự kiện** | Xác thực phù hợp khả năng, ghi dấu kích hoạt, hạn chế quyền, cảnh báo, session tracking và thao tác theo nhiệm vụ. | Người dùng/tiến trình đã làm gì, lúc nào, trong phạm vi nào. |
| **Sau sự kiện** | Thu hồi/đối soát, đánh giá độc lập, xác nhận căn cứ, phân loại sai lệch, khắc phục, lưu chứng cứ. | Quyền đã được xử lý, hành động được đánh giá và rủi ro còn lại có owner. |

**Không nên hiểu** rằng thiếu phê duyệt trước thì bất kỳ ai cũng có thể tự nhận “khẩn cấp”, thao tác tùy ý rồi xin chấp thuận sau. Cơ chế chỉ hợp lệ khi tuân thủ **emergency access policy** do tổ chức ban hành và giới hạn thẩm quyền được ủy quyền từ trước.

### 1.2. “Post-event approval” và “post-event review” không hoàn toàn đồng nghĩa

- **Review (hậu kiểm):** xem lại sự kiện, thu thập sự thật, đối chiếu policy và tìm sai lệch.
- **Ratification/approval (chấp thuận sau sự kiện):** quyết định có thẩm quyền rằng việc sử dụng quyền **phù hợp hoặc được xử lý theo chính sách ngoại lệ**, trong phạm vi đánh giá và bằng chứng cụ thể.
- **Risk acceptance:** quyết định riêng về **rủi ro tồn dư chưa xử lý** trong thời hạn/biện pháp bù đã phê duyệt.
- **Remediation:** hành động loại bỏ sai lệch, thu hồi quyền, sửa quy trình hoặc xử lý hậu quả.
- **Incident investigation:** điều tra khi có nghi vấn lạm dụng, gian lận, vi phạm chính sách hoặc rò rỉ dữ liệu.

Tổ chức có thể dùng các nhãn khác nhau, nhưng **không được gộp chúng thành một ô “Approved” làm mất ý nghĩa**. Một sự kiện được đánh giá hợp lệ vẫn có thể có lỗi kỹ thuật cần sửa; một sự kiện sai chính sách không trở thành hợp lệ chỉ vì quản lý ký sau.

## 2. Khi nào dùng quyền khẩn cấp, và khi nào không?

### 2.1. Những tình huống thường phải có phương án khẩn

- **IdP/SSO/PAM không khả dụng** khiến quản trị viên hợp lệ không thể đăng nhập để phục hồi.
- **Sự cố production nghiêm trọng** đòi quyền tăng cường ngay để khôi phục dịch vụ trọng yếu.
- **Sự cố bảo mật đang diễn ra** cần cô lập tài nguyên hoặc thu hồi credential khẩn.
- **Mất khóa hoặc điều kiện truy cập thông thường** cần phương án phục hồi/continuity đã được định nghĩa.
- **Thành phần điều phối quyền bị lỗi** nhưng cần duy trì một đường quản trị phục hồi độc lập đủ an toàn.

Đây là **ví dụ về tình huống cần thiết kế cơ chế khẩn cấp**, không mặc định mọi trường hợp đều cho phép bỏ quy trình phê duyệt. Quyền dùng thực tế phụ thuộc mức nghiêm trọng, policy, thẩm quyền và biện pháp kiểm soát.

### 2.2. Không nên dùng post-event approval để giải quyết việc thường ngày

| Tình huống | Phân loại phù hợp | Lý do |
| --- | --- | --- |
| Dịch vụ identity outage, cần account dự phòng đã được phê duyệt trước. | Có thể là emergency access. | Đường phê duyệt thường không sẵn có. |
| Triển khai bản nâng cấp theo lịch nhưng quên xin quyền JIT. | **Không mặc nhiên** là emergency. | Có thể dùng quy trình change/access request bình thường. |
| Nhân viên muốn quyền admin vì ticket 403. | Điều tra authorization/provisioning. | Tiện lợi hoặc thiếu quyền không tự tạo tình huống khẩn. |
| Phát hiện credential bị xâm phạm, phải khóa nhanh. | Có thể kích hoạt quy trình ứng cứu khẩn theo policy. | Giảm rủi ro cấp thời có thể quan trọng hơn chờ duyệt thường. |
| Người đã Leaver cần vào lại tài khoản để chuyển dữ liệu. | Không tự cho dùng account cũ. | Phải dùng quy trình bàn giao/đại diện hợp lệ, không mở lại quyền Leaver. |
| Cần phá giới hạn SoD để làm xong công việc trước deadline. | Cần escalation/exception có thẩm quyền. | Deadline nghiệp vụ không phải lý do mặc nhiên vượt SoD. |

**Câu hỏi gốc:** Nếu kênh thông thường vẫn hoạt động và thời gian cho phép, vì sao không dùng **phê duyệt trước + JIT/PAM**? Câu trả lời phải được ghi trong hồ sơ hậu kiểm.

## 3. Các loại emergency access và hệ quả hậu kiểm

| Cơ chế | Bản chất | Điều cần hậu kiểm đặc biệt |
| --- | --- | --- |
| **Break-glass account** | Tài khoản khẩn riêng khi cơ chế thường gặp sự cố. | Ai đã mở credential, xác thực/nhận diện, hành động, rotation và bảo vệ đường dự phòng. |
| **JIT emergency elevation** | Kích hoạt role mạnh trong khoảng thời gian ngắn. | Eligibility, lý do, approval bypass được định nghĩa, duration và role deactivation. |
| **PAM emergency session** | Mở phiên đặc quyền qua cơ chế khẩn của PAM. | Vault checkout, session ID, lệnh/hoạt động có căn cứ và đóng phiên. |
| **Emergency cloud role** | Vai trò cloud để khôi phục hoặc cô lập sự cố. | Scope account/project, trust, role assumption, policy changes, key/session còn sống. |
| **Application-local emergency admin** | Quyền dự phòng ở SaaS/ứng dụng khi SSO lỗi. | Local role, mật khẩu/secret, session, quyền ngoài IGA/SCIM. |
| **Emergency service/workload principal** | Tài khoản kỹ thuật phục vụ tự động hóa khẩn được cho phép. | OwnerTeam, purpose, credential, scope API và hoạt động của automation. |

Một số hệ thống không cho chặn ngay phiên/token sau khi gỡ role. Vì vậy, hậu kiểm phải xác định **quyền còn sử dụng được hay không**, không chỉ kiểm cờ `enabled=false`.

## 4. Mô hình trách nhiệm và người có thẩm quyền phê duyệt

Một hồ sơ emergency access thường liên quan nhiều vai trò:

| Vai trò | Nhiệm vụ chính | Kiểm soát độc lập |
| --- | --- | --- |
| **Emergency actor/operator** | Kích hoạt và sử dụng quyền khẩn được phép. | Không tự kết luận hành động của mình đã hợp lệ. |
| **Incident commander/on-call lead** | Điều phối tình huống, ghi mức nghiêm trọng và ưu tiên phục hồi. | Không mặc nhiên có thẩm quyền chấp nhận mọi sai lệch IAM. |
| **System/application owner** | Xác nhận sự cần thiết và phạm vi hành động ở tài nguyên. | Không chỉ kiểm khôi phục dịch vụ; phải xem quyền đã dùng. |
| **IAM/PAM owner** | Kiểm chứng account, activation, nhóm, token, session và trạng thái thu hồi. | Kết quả được đối soát với nguồn đích. |
| **Security/risk reviewer** | Đánh giá lý do khẩn, vi phạm, SoD, bằng chứng và risk. | Nên độc lập với người sử dụng quyền. |
| **Approving authority** | Đưa quyết định ratification/denial theo policy. | Đủ thẩm quyền, không self-approve. |
| **Compliance/legal/privacy** | Tham gia khi có dữ liệu nhạy cảm hoặc yêu cầu báo cáo/luật cụ thể. | Căn cứ theo chính sách và nghĩa vụ liên quan. |
| **Auditor** | Kiểm tra tính đầy đủ và khả năng chứng minh kiểm soát. | Không thay người chịu trách nhiệm phê duyệt nghiệp vụ. |

### 4.1. Separation of Duties trong hậu kiểm

Hãy phân biệt:

~~~text
actor       = người trực tiếp dùng quyền emergency
beneficiary = người hoặc workload nhận quyền khẩn
reviewer    = người kiểm tra evidence và tác động
approver    = người ra quyết định sau sự kiện
remediator  = người hoặc connector thu hồi/sửa quyền
verifier    = người/hệ thống đối chiếu quyền thực tế
~~~

Đặc biệt:

- **Actor không tự phê duyệt** việc dùng đặc quyền của chính mình, kể cả bằng tài khoản admin phụ.
- **Approver phải đủ thẩm quyền tại thời điểm quyết định**, không chỉ đã từng là manager.
- **Manager có thể xác nhận nhu cầu**, còn Security/owner có thể cần đánh giá permission và sự kiện.
- **Người thực thi thu hồi không nên tự tuyên bố hoàn tất** nếu không có readback/verification.
- **Reviewer đã Leaver/Mover mất authority** phải được thay tuyến theo policy.

### 4.2. Một người, nhiều tài khoản

Kiểm self-approval bằng `accountId` là chưa đủ. Một người có user account, admin account và local emergency account vẫn là **cùng Person**. Hệ thống cần tương quan **canonical personId/subjectId**, account namespace và **engagementId** khi áp dụng policy.

## 5. Chính sách phải được chuẩn bị trước sự cố

**Hậu kiểm không phải là cơ chế thay thế việc xây dựng chính sách**. Trước khi sự cố diễn ra, tổ chức cần xác định:

1. **Các kịch bản hợp lệ** và điều kiện kích hoạt emergency access.
2. **Ai được phép khởi tạo/sử dụng**, cách xác minh danh tính khi IdP bình thường mất sẵn sàng.
3. **Loại quyền, phạm vi tài nguyên và khoảng thời gian tối đa** cho từng cơ chế.
4. **Cảnh báo tức thời/near-real-time** đến nhóm phụ trách, kể cả sau khi dùng đường đăng nhập dự phòng.
5. **Bằng chứng bắt buộc**: incident reference, người sử dụng, session, hành động, thay đổi cấu hình, kết quả.
6. **Thời hạn hậu kiểm** và thẩm quyền đánh giá theo mức nghiêm trọng.
7. **SoD, exception và escalation** khi người duyệt không sẵn có.
8. **Thu hồi/rotation/cleanup**: quy định xử lý role, session, token, credential và thay đổi cấu hình.
9. **Cách xử lý khi không đủ chứng cứ, vi phạm chính sách hoặc nghi lộ credential**.
10. **Kỳ kiểm thử và rà soát cơ chế break-glass** để tránh có tài khoản khẩn không dùng được lúc cần.

Không có một SLA hậu kiểm **24 giờ/48 giờ/7 ngày** mặc nhiên phù hợp cho mọi tổ chức. Hãy dùng **thời hạn do policy và nghĩa vụ riêng áp dụng quy định**. Với quyền rủi ro đặc biệt cao, nên có cảnh báo và triage tức thời thay vì đợi kỳ đánh giá.

### 5.1. Trạng thái đăng ký kịch bản khẩn

Ví dụ dữ liệu thiết kế nội bộ:

~~~yaml
# Ví dụ policy metadata minh họa, không phải SCIM/PAM standard.
emergencyPolicyId: EMERGENCY-PROD-RECOVERY
policyVersion: 5
allowedPurposes:
  - RESTORE_IDENTITY_SERVICE
  - CONTAIN_ACTIVE_SECURITY_INCIDENT
eligibleRoles:
  - emergency-identity-operator
activationRequirements:
  emergencyReasonRequired: true
  incidentReferenceRequired: true
  alertOnActivation: true
  namedActorTracking: true
maximumSessionDurationMinutes: 60
postEvent:
  reviewerGroup: security-incident-governance
  independentApprovalRequired: true
  evidenceChecklistVersion: 3
  reviewDuePolicy: risk-based
  requireRevocationReadback: true
~~~

Những trường và giá trị chỉ để **giải thích cách tổ chức policy**, không phải khuyến nghị thời lượng cố định hay schema sản phẩm. Với tình huống mất IdP, điều kiện kích hoạt và xác thực cần được thiết kế sao cho **không phụ thuộc hoàn toàn vào hệ thống đang lỗi**, nhưng vẫn giới hạn được rủi ro và giữ trách nhiệm giải trình.

## 6. Chu trình đầu-cuối: kích hoạt → hậu kiểm → khép kín

~~~mermaid
flowchart TD
    A["Emergency condition được phát hiện"] --> B["Kích hoạt theo policy khẩn<br/>actor + incidentId + scope"]
    B --> C["Cảnh báo và ghi hoạt động<br/>session / audit / provider events"]
    C --> D["Thực hiện nhiệm vụ khẩn<br/>theo scope và thời gian"]
    D --> E["Kết thúc khẩn cấp<br/>thu hồi quyền và đóng phiên"]
    E --> F["Đọc lại target/IdP/PAM<br/>token / local grants / session"]
    F --> G["Bảo toàn evidence<br/>và gói hậu kiểm"]
    G --> H["Reviewer độc lập<br/>đối chiếu policy + JML + SoD"]
    H --> I{"Kết luận?"}
    I -->|"Hợp lệ"| J["Ratified với phạm vi/bằng chứng"]
    I -->|"Hợp lệ nhưng cần sửa"| K["Ratified with actions<br/>owner + dueAt"]
    I -->|"Không hợp lệ / nghi vấn"| L["Rejected / Incident<br/>điều tra + giảm thiểu"]
    I -->|"Chưa đủ bằng chứng"| M["Pending / Unverifiable<br/>exception + deadline"]
    J --> N["Audit + lessons learned<br/>đóng khi đủ điều kiện"]
    K --> O["Remediation + verification"]
    L --> O
    M --> O
    O --> N
~~~

### 6.1. Hai đường thời gian song song

**Đường phục hồi dịch vụ** không nhất thiết phải chờ **đường ratification**. Tuy nhiên, **thu hồi quyền và bảo vệ bằng chứng** không nên bị trì hoãn chỉ vì reviewer chưa đưa ra quyết định. Nếu phát hiện khả năng lạm dụng trong khi phiên đang mở, phải chuyển sang quy trình ứng cứu tương ứng.

### 6.2. Mốc trạng thái nên tách

| Giai đoạn | Trạng thái ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Emergency event** | DETECTED, ACTIVATED, ENDED | Hoạt động emergency ở mốc nào. |
| **Privilege access** | ELIGIBLE, ACTIVE, REVOKE_REQUESTED, REVOKED_VERIFIED, UNKNOWN | Quyền có thể còn sử dụng được không. |
| **Evidence** | COLLECTING, COMPLETE, PARTIAL, UNAVAILABLE | Mức đủ dữ liệu cho hậu kiểm. |
| **Post-event review** | PENDING, UNDER_REVIEW, RATIFIED, RATIFIED_WITH_ACTIONS, REJECTED, INDETERMINATE | Kết luận của người có thẩm quyền. |
| **Remediation** | OPEN, IN_PROGRESS, VERIFIED, OVERDUE | Sai lệch đã được xử lý thực tế chưa. |
| **Exception/incident** | OPEN, MITIGATED, CLOSED | Rủi ro chưa được đóng và kết quả điều tra. |

Một sự kiện có thể **review=RATIFIED** nhưng **privilege=UNKNOWN** do không quan sát được session. Không được tự đổi thành **REVOKED_VERIFIED** chỉ vì reviewer chấp thuận.

## 7. Bước 1 – Thông báo và mở hồ sơ hậu kiểm

Ngay khi quyền khẩn được sử dụng, cần tạo dấu vết đủ để kích hoạt hậu kiểm, ngay cả khi phiên sử dụng xảy ra ngoài giờ hành chính.

Các trường tối thiểu:

- **eventId, incidentId, severity** và hệ thống bị ảnh hưởng.
- **actorSubjectId, accountId, principalType**: con người, shared emergency account hay workload.
- **activationAt**, môi trường, tenant, target resource.
- **policyId/version**, lý do khẩn, đường kích hoạt.
- **privilege/role, sessionId hoặc credential reference** (không phải raw secret).
- **alert recipients, alertSentAt, ackAt**.
- **sự kiện kết thúc, incident close marker** khi có.

### 7.1. Đừng chờ người dùng nhớ điền form sau sự cố

Phần lớn metadata có thể được tự động ghi từ **PAM/IdP/cloud audit/incident platform**, sau đó yêu cầu actor bổ sung bối cảnh nghiệp vụ. Người vận hành có thể làm việc áp lực cao; nếu phụ thuộc hoàn toàn vào lời kể vài ngày sau, bằng chứng dễ thiếu hoặc sai thời điểm.

### 7.2. Khi kênh cảnh báo lỗi

Nếu hệ thống chính không gửi được thông báo do outage, chính sách nên có **đường cảnh báo dự phòng** và cơ chế đối soát khi dịch vụ hồi phục. Test phải ghi nhận việc cảnh báo bị trì hoãn; không tuyên bố “alert success” chỉ vì có cấu hình mà không có bằng chứng gửi/nhận.

## 8. Bước 2 – Thu hồi quyền và kiểm session/credential

Sau khi tác vụ khẩn kết thúc hoặc điều kiện sử dụng không còn đúng, cần thu hồi quyền theo **phạm vi thực tế**.

| Đối tượng | Điều phải kiểm | Sai lầm thường gặp |
| --- | --- | --- |
| **JIT/PAM elevation** | Role đã deactivated, eligibility và session theo policy. | Coi đồng hồ JIT hết giờ là API chắc chắn từ chối. |
| **Break-glass account** | Session đóng, credential được bảo vệ/rotate khi cần, account sẵn sàng đúng mức cho sự kiện sau. | Chỉ đổi password mà bỏ active sessions. |
| **IdP/directory groups** | Membership và account state đúng. | Gỡ group nhưng quyền app-local còn. |
| **SCIM SaaS** | User/Group thay đổi, app role readback. | Coi 200/204 là toàn bộ quyền đã mất. |
| **Cloud IAM** | Role/policy/trust, role assumptions và credentials liên quan. | Gỡ assignment mà không xét phiên token đã phát. |
| **Database/Kubernetes** | Grants, session/role binding, delegated access nếu thuộc phạm vi. | Bỏ local privilege không thuộc IdP. |
| **API/PAT/token** | Token/key có scope khẩn còn hoạt động hay không theo issuer/resource. | Chỉ revoke user mà để PAT còn. |
| **Workload** | Principal, temporary credentials, owner, job tiếp tục chạy cần quyền nào. | Để quyền admin thường trực sau sự kiện. |

### 8.1. Ghi kết quả theo ba lớp

~~~text
REVOKE_REQUESTED:
    IAM/PAM đã yêu cầu thu hồi.

REVOKE_ACKNOWLEDGED:
    Đích/connector trả phản hồi nhận hoặc xử lý.

REVOKED_VERIFIED:
    Đọc lại và kiểm đường truy cập thuộc phạm vi đã xác minh không còn quyền.
~~~

Nếu không thể kiểm một phiên/token, dùng trạng thái **UNKNOWN/UNVERIFIABLE với owner và giảm thiểu theo rủi ro**, không đánh dấu “đã thu hồi 100%”.

### 8.2. Không xóa nhầm phương án khôi phục

Break-glass có thể phải **tiếp tục tồn tại** để bảo đảm business continuity. Phải phân biệt **đóng phiên và xử lý credential sau một lần dùng** với **xóa vĩnh viễn tài khoản emergency**. Việc duy trì account chỉ chính đáng khi tiếp tục có owner, chính sách, biện pháp bảo vệ và cơ chế kiểm thử.

## 9. Bước 3 – Bảo toàn bằng chứng và kiểm toàn vẹn

Hậu kiểm đáng tin phải có **evidence package** trước khi ký quyết định.

### 9.1. Những nguồn bằng chứng thường gặp

| Nguồn | Bằng chứng cần lấy | Giới hạn cần ghi |
| --- | --- | --- |
| **Incident/ticket system** | Mức độ, triệu chứng, impact, incident commander, timeline. | Lời khai có thể được bổ sung sau, không thay log thực tế. |
| **PAM** | Vault checkout, session start/end, actor, command/session metadata. | Đường trực tiếp ngoài PAM có thể không thấy. |
| **IdP/SSO** | Authentication events, MFA method, emergency account activity. | Sign-in success không chứng minh toàn bộ app actions. |
| **SCIM/provisioning** | Group/role change requests, provider response, retries. | Success không đồng nghĩa session đã hết quyền. |
| **Cloud/API audit** | Role assumption, policy/credential changes, resource actions. | Phạm vi logging có thể thiếu ở một dịch vụ. |
| **Application/database logs** | Các thao tác liên quan, dữ liệu/đối tượng chịu ảnh hưởng. | Cần hiểu semantic của event và độ tin cậy timestamp. |
| **Change management** | Thay đổi cấu hình, artifact, rollback, review. | Ticket change không chứng minh thao tác thực tế trùng mô tả. |
| **Current entitlement readback** | Trạng thái role/group/grant sau sự kiện. | Chỉ phản ánh thời điểm đọc, không tái dựng toàn bộ lịch sử. |

### 9.2. Những câu hỏi evidence phải trả lời

1. Quyền được kích hoạt **trước, trong hay sau** thời điểm sự cố đủ điều kiện?
2. Ai thực sự điều khiển principal? Có **shared account** hoặc nhiều người biết credential không?
3. Actor đã làm những **hành động nào**, trên tài nguyên và dữ liệu nào?
4. Hành động có liên quan trực tiếp đến **giảm thiệt hại/khôi phục** hay không?
5. Có thay **role, policy, secret, trust, audit config** vượt phạm vi mục đích?
6. Có dấu hiệu **che giấu, sửa log, sử dụng ngoài cửa sổ hoặc ngoài incident**?
7. Khi kết thúc, **session/token/role/grant** đã được xử lý đến đâu?
8. Có tài nguyên, hệ thống hay đường truy cập **không thể quan sát**?

### 9.3. Giữ tính toàn vẹn, riêng tư

Không sao chép **raw password, API key, refresh/access token, private key, OTP, cookie**, hoặc toàn bộ dữ liệu khách hàng vào hồ sơ. Dùng reference ID, metadata, liên kết log có quyền truy cập hạn chế; bảo vệ integrity, timestamps, quyền xem và thời hạn lưu theo policy.

Nếu có nghi vấn sự cố bảo mật, thực hiện **preservation/chain-of-custody** theo quy trình điều tra để tránh bằng chứng bị thay đổi trong quá trình khắc phục. Không xóa audit chỉ để “dọn sau khẩn”.

## 10. Bước 4 – Đánh giá tính cần thiết, tương xứng và tuân thủ

Người duyệt sau sự kiện phải đánh giá bằng chứng theo một **rubric nhất quán**, không chỉ nhìn việc hệ thống đã hoạt động lại.

### 10.1. Các chiều đánh giá

| Tiêu chí | Câu hỏi kiểm tra | Dấu hiệu cần điều tra |
| --- | --- | --- |
| **Emergency legitimacy** | Tình huống có đáp ứng policy về khẩn cấp không? | Dùng emergency cho công việc kế hoạch. |
| **Actor eligibility** | Principal/người dùng có thuộc nhóm được phép và quan hệ còn hợp lệ? | Account đã Leaver hoặc không có owner. |
| **Purpose** | Tác vụ có nhằm khôi phục/ứng cứu hợp lệ? | Thao tác không liên quan incident. |
| **Scope minimization** | Chỉ dùng quyền và tài nguyên cần thiết? | Admin toàn tenant khi chỉ cần một service. |
| **Time minimization** | Bắt đầu/kết thúc đúng cửa sổ cần thiết? | Session kéo dài nhiều giờ sau khôi phục. |
| **SoD/independence** | Ai đánh giá, ai thực thi; có tự phê duyệt không? | Actor cũng là approver và người xác minh. |
| **Evidence completeness** | Có đủ log, session và readback để kết luận? | Không xác định được người dùng shared account. |
| **Security hygiene** | Có giữ log, bảo vệ secret, thay key đúng chính sách? | Key lộ trong ticket hoặc tắt audit. |
| **Outcome/integrity** | Thay đổi có đúng mục đích và còn tác động tồn dư? | Policy permissive vẫn ở trạng thái mới. |
| **Revocation verification** | Đường quyền đã đóng? | Token/PAT hoặc local role vẫn hoạt động. |

### 10.2. Không sử dụng tiêu chí “đã thành công” làm thay mọi kiểm tra

Một thao tác có thể **khôi phục được hệ thống nhưng vượt phạm vi quyền, tắt logging hoặc để lại credential quá rộng**. Ngược lại, nỗ lực đúng policy có thể không khôi phục được dịch vụ vì nguyên nhân kỹ thuật. Hậu kiểm phải xem **quyết định và hành vi trong bối cảnh có lúc đó**, kết quả kỹ thuật và rủi ro hậu sự kiện như những chiều riêng.

## 11. Bước 5 – Quyết định sau sự kiện và cách ghi nhận

### 11.1. Các kết quả cần phân biệt

| Quyết định | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| **RATIFIED** | Bằng chứng hỗ trợ kết luận việc sử dụng đáp ứng chính sách trong phạm vi xác định. | Lưu attestation và kết quả thu hồi; lên review kế tiếp khi cần. |
| **RATIFIED_WITH_ACTIONS** | Cơ sở khẩn hợp lệ nhưng có thiếu sót kiểm soát cần sửa. | Gán owner, mức rủi ro và deadline; theo dõi remediation. |
| **REJECTED / NOT_RATIFIED** | Hành vi không đáp ứng chính sách hoặc trái thẩm quyền. | Điều tra/ứng cứu hoặc quy trình nội bộ phù hợp, xử lý quyền và tác động. |
| **INDETERMINATE** | Chưa đủ bằng chứng để quyết định. | Bổ sung evidence, exception/mitigation, hạn review mới. |
| **ESCALATED_TO_INCIDENT** | Có dấu hiệu lạm dụng, rò rỉ hay vi phạm nghiêm trọng. | Chuyển Security/incident response, bảo toàn chứng cứ. |

**Phê duyệt sau sự kiện không thể làm hành vi trái phép ở thời điểm xảy ra trở thành được phê duyệt trước.** Nhãn RATIFIED phản ánh kết luận hậu kiểm **theo policy và bằng chứng**, không xóa nghĩa vụ báo cáo, xử lý vi phạm hoặc trách nhiệm khi đã có hậu quả.

### 11.2. Chấp thuận có điều kiện không được đóng nhầm

Ví dụ reviewer đánh giá khẩn cấp là thật, nhưng phát hiện một API key còn quyền admin. Có thể kết luận:

~~~text
postEventDecision = RATIFIED_WITH_ACTIONS
reason = "Tình huống khôi phục hợp lệ; phát hiện credential tồn dư."
remediation = "Thu hồi key, kiểm scope và xác minh API từ chối."
securityRiskStatus = OPEN
accessVerification = NOT_YET_VERIFIED
~~~

Không được báo cáo **“case closed/no residual access”** chỉ vì trường `postEventDecision` đã có chữ RATIFIED.

### 11.3. Nếu không phê duyệt?

Không có thao tác **“undo thời gian”**. Tổ chức cần đánh giá hậu quả thực tế:

- Đối chiếu những hành động đã làm và những dữ liệu có thể bị tác động.
- Thu hồi quyền/credential còn tồn tại.
- Nếu có nghi vấn, chuyển quy trình điều tra và bảo vệ bằng chứng.
- Khắc phục cấu hình/dữ liệu thay đổi vượt phạm vi, có change review nếu cần.
- Xác định có phải **policy gap** hay hành vi vi phạm đã có policy.
- Ghi kết quả, người chịu trách nhiệm, hạn và kiểm chứng đóng.

### 11.4. Nếu reviewer thiếu bằng chứng?

**INDETERMINATE không phải PASS cũng không mặc nhiên kết luận người dùng sai phạm**. Cần ghi rõ nguồn nào thiếu, vì sao thiếu, ai bổ sung được, biện pháp giảm rủi ro, deadline và giới hạn kết luận. Việc thiếu log của hệ thống khẩn không được giải quyết bằng cách tự tạo lời xác nhận không có nguồn.

## 12. Bước 6 – Hành động khắc phục, hoàn nguyên và cải tiến

Một lần emergency access có thể để lại **persistent change**, ngay cả khi role khẩn đã được gỡ:

| Loại thay đổi | Ví dụ | Cách kiểm |
| --- | --- | --- |
| **IAM/role** | Thêm admin group hoặc trust policy. | So config trước/sau, đối chiếu baseline. |
| **Credential/secret** | Phát thêm API key hoặc recovery credential. | Inventory key và lifecycle; thu hồi key dư. |
| **Application configuration** | Vô hiệu một kiểm soát để phục hồi. | Change record và xác minh kiểm soát được bật lại. |
| **Network rule** | Mở đường kết nối ngoài chuẩn. | So policy/firewall rules với approved baseline. |
| **Data operation** | Chỉnh sửa dữ liệu vận hành. | Kiểm business/data owner và integrity. |
| **Monitoring/logging** | Điều chỉnh collector/logging. | Xác minh khôi phục độ bao phủ và phát hiện gap. |
| **Workload ownership** | Dùng tài khoản cá nhân chạy job cứu hệ thống. | Chuyển về principal workload được quản trị. |

Không phải mọi emergency change phải rollback toàn bộ: một bản vá sửa cấu hình có thể trở thành trạng thái mong muốn mới **sau change control có thẩm quyền**. Vấn đề là mỗi thay đổi phải có **owner, lý do giữ/hoàn nguyên và xác minh**.

## 13. Thời hạn, nhắc việc và escalation trong hậu kiểm

Cần phân biệt tối thiểu:

- **Alert acknowledgement SLA:** từ `activationAt` tới khi đội được chỉ định biết sự kiện.
- **Session/privilege revocation SLA:** từ khi quyền không còn cần hoặc hết hạn tới `revokedVerifiedAt`.
- **Post-event review SLA:** từ `eventEndedAt` hoặc mốc policy định nghĩa tới `decisionAt`.
- **Remediation SLA:** từ finding/decision tới `remediationVerifiedAt`.
- **Incident reporting SLA:** nếu có sự cố phải báo cáo theo quy định/chính sách áp dụng.

### 13.1. Escalation không có nghĩa auto-approve

Nếu reviewer không trả lời đúng hạn:

1. Nhắc việc và xác minh người duyệt còn thẩm quyền.
2. Escalate theo **risk tier** và danh sách người thay thế đã được policy duyệt.
3. Kiểm SoD lại: người thay thế không được chính là actor hoặc người hưởng lợi.
4. Nếu vẫn chưa có quyết định, giữ **PENDING/OVERDUE**, có owner và biện pháp giảm thiểu.
5. Chuyển incident nếu bằng chứng cho thấy hoạt động không kiểm soát hoặc nguy cơ hiện hữu.

Không có **“approved by timeout”** cho việc sử dụng quyền khẩn. Việc chậm hậu kiểm phải được báo trung thực, không tự động hợp thức hóa.

### 13.2. Đồng hồ và timezone

Log từ PAM, IdP, SaaS thường lưu UTC; thông báo incident có thể dùng giờ địa phương. Cần lưu timestamp có offset rõ ràng, ví dụ `2026-12-01T02:15:00+07:00`, đối chiếu với UTC và phát hiện **clock skew** giữa nguồn. Những sự kiện sắp xếp sai do timezone có thể khiến reviewer kết luận nhầm “quyền dùng trước sự cố”.

## 14. Liên kết phê duyệt sau sự kiện với Joiner–Mover–Leaver

Hậu kiểm phải đánh giá **tư cách của actor tại thời điểm kích hoạt** và **tình trạng hiện tại lúc đưa ra quyết định**. Hai mốc này có thể khác nhau.

### 14.1. Joiner – chưa đủ điều kiện không thể được hợp thức hóa tùy tiện

Nhân viên mới có thể được pre-provision tài khoản IdP trước Start date. Nếu người đó dùng role emergency khi **engagement chưa hiệu lực**, cần kiểm:

1. Họ đã được xác minh danh tính bằng quy trình nào?
2. Emergency policy có cho **preboarding** tham gia ứng cứu không?
3. Ai đã trao credential/eligibility, và bằng chứng thẩm quyền ở thời điểm đó?
4. Hành động có vượt role/tenant/mục đích khẩn?
5. Quyền khẩn đã bị thu hồi, account đã trở về baseline chưa?

**Sự kiện xảy ra trước Start date không được mặc nhiên coi hợp lệ chỉ vì sau đó nhân viên thực sự bắt đầu làm việc.** Hậu kiểm phải dựa trên policy có hiệu lực tại thời điểm dùng quyền.

### 14.2. Mover – quyền khẩn có thể không còn đúng vai trò

Một kỹ sư từng thuộc SRE nhưng đã chuyển sang Product có thể vẫn nằm trong **PAM emergency eligible group**. Sau Mover, việc dùng quyền cũ có thể không còn căn cứ.

| Kiểm tra | Ý nghĩa |
| --- | --- |
| **Effective role at activationAt** | Actor có còn thuộc nhóm trực sự cố/owner không? |
| **Current role at reviewAt** | Reviewer có thẩm quyền và chính sách hiện tại khác trước không? |
| **Grant source** | Eligibility đến từ HRIS/IGA, group động, local PAM hay direct role? |
| **Change event history** | Mover có đến muộn, bị retry hoặc mapping sai không? |
| **Revocation outcome** | Role cũ/eligible emergency đã được loại khỏi mọi đích chưa? |

**Căn cứ phê duyệt phải xét thời điểm hành động**, còn **việc giữ quyền trong tương lai** phải xét vai trò hiện tại. Không dùng phê duyệt sau sự kiện để duy trì quyền SRE đã hết nhu cầu.

### 14.3. Leaver – không chờ hậu kiểm mới thu hồi

Nếu một principal đã kết thúc engagement nhưng emergency account/token vẫn sử dụng được:

- Ưu tiên **ngăn truy cập và điều tra** theo mức rủi ro.
- Đối chiếu termination effectiveAt, account disable, SCIM/group removal, local grants và active sessions.
- Kiểm liệu actor có thực sự là người đã nghỉ hay account bị dùng bởi người khác.
- Bảo toàn bằng chứng, xác định mọi hành động sau mốc kết thúc.
- Hậu kiểm bởi người độc lập, không tự chấp thuận vì “giúp cứu dịch vụ”.
- Đảm bảo retry Job Joiner/Mover cũ không tái cấp emergency eligibility.

Một Leaver **không phải chờ người duyệt sau sự kiện** mới bị vô hiệu hóa. **Quy trình thu hồi là luồng kiểm soát riêng, ưu tiên theo lifecycle/security policy**.

### 14.4. Rehire và chuyển hợp đồng

Khi một người được tuyển lại:

- Có thể xác minh đó là cùng **Person**, nhưng phải có **Engagement mới**.
- Không tự khôi phục privileged/emergency role, approval hoặc secret từ lần làm việc trước.
- Kiểm account phụ và local role còn tồn tại từ giai đoạn cũ.
- Review đúng role, sponsor và thời hạn hợp đồng hiện tại.
- Không lấy email tái cấp làm khóa duy nhất cho evidence.

### 14.5. Manager hoặc reviewer đổi trong lúc chờ hậu kiểm

Reviewer được chỉ định sau sự cố có thể đã Mover/Leaver trước khi nhấn nút. API phải **kiểm authority ngay lúc ra quyết định**, không chỉ lúc gán ticket. Nếu reviewer mất quyền, chuyển tuyến sang người đủ thẩm quyền; **không auto-approve** hay ký bằng identity cũ.

## 15. Đối chiếu dữ liệu hậu kiểm qua HRIS, IGA, IdP, SSO, SCIM và ứng dụng

Emergency access có thể được sử dụng đúng lúc một thành phần IAM đang lỗi, nên việc tổng hợp bằng chứng **chỉ từ hệ thống đó** thường không đủ.

~~~mermaid
flowchart LR
    HR["HRIS / Contract<br/>Person + JML effectiveAt"] --> COR["Identity correlation<br/>Person / Engagement / Workload"]
    PAM["PAM / Break-glass<br/>Activation + session"] --> EVID["Emergency evidence<br/>event + audit timeline"]
    IDP["IdP / SSO<br/>Auth + groups + claims"] --> EVID
    SCIM["SCIM / Directory<br/>Provisioning + readback"] --> EVID
    APP["Application / Cloud / DB<br/>Local grants + API actions"] --> EVID
    COR --> REVIEW["Independent post-event review<br/>policy + SoD + scope"]
    EVID --> REVIEW
    REVIEW --> DEC["Decision + findings"]
    DEC --> FIX["Remediation / revoke<br/>session + credential + policy"]
    FIX --> VER["Effective-access verification"]
    VER --> AUD["Audit + KPI + lessons learned"]
~~~

### 15.1. Vai trò và giới hạn từng hệ thống

| Thành phần | Thông tin có ích | Không tự chứng minh |
| --- | --- | --- |
| **HRIS/contract source** | Person, engagement, manager, Start/End, role hiện hành. | Account/credential ở đích đã bị chặn. |
| **IGA** | Policy, eligibility, approval, review, expected entitlements. | App-local role và token còn quyền. |
| **IdP** | Account, nhóm, auth event, MFA, SSO application mapping. | Mọi session và direct grants trong SaaS. |
| **SAML/OIDC SSO** | Issuer, authenticated subject, time và claims được gửi. | Claimed groups còn mới sau Mover/Leaver. |
| **SCIM** | User/Group lifecycle và phản hồi cập nhật. | Mọi role đặc quyền hoặc session có thể bị thu hồi ngay. |
| **PAM** | Emergency activation, checkout, session metadata, vault controls. | Đường local admin ngoài PAM hoặc account dùng chung không map được cá nhân. |
| **Cloud/App/API** | Role/policy, thao tác thực tế, trạng thái authorization. | Tư cách nhân sự nếu không liên kết HRIS. |

### 15.2. SSO/token là bằng chứng xác thực, không là toàn bộ bằng chứng hành động

Một OIDC token đã được phát hành trước Mover có thể mang claim group cũ. Một ứng dụng có thể duy trì session sau khi IdP trở lại bình thường. Khi hậu kiểm, cần xét **issuer, audience, subject, issuance/expiry, session lifetime và policy kiểm tại resource** trong phạm vi liên quan. Không dùng **ID token** như bằng chứng thay thế authorization ở API đích.

Với federation, một `sub` chỉ có ý nghĩa trong namespace của `iss`; không tự gộp hai principal từ hai issuer dựa trên chuỗi giống nhau. Email có thể đổi/tái sử dụng và không phải identity key bền vững.

### 15.3. SCIM PATCH success và effective privilege

Ví dụ SCIM trả HTTP 204 khi xóa thành viên khỏi Group emergency, nhưng SaaS vẫn giữ:

- Local admin role cấp trực tiếp.
- Group khác kế thừa cùng permission.
- API key/PAT độc lập.
- Session cookie mang role cũ.

Trong trường hợp đó, **post-event review có thể đã ghi quyết định** nhưng **access revocation vẫn chưa VERIFIED**. Phải đọc lại từng đường quyền và báo rủi ro tồn dư thay vì đóng hồ sơ quá sớm.

## 16. SoD, reviewer độc lập và cơ chế chống tự phê duyệt

### 16.1. Những tổ hợp cần kiểm

| Tổ hợp | Rủi ro | Kiểm soát |
| --- | --- | --- |
| **Actor = post-event approver** | Tự hợp thức hóa việc dùng quyền của mình. | Từ chối theo canonical Person/subject. |
| **Actor có quyền chỉnh approval policy** | Có thể sửa chuẩn đánh giá để được chấp thuận. | Change control, policy version và reviewer độc lập. |
| **Executor có quyền sửa/xóa audit** | Có thể che các hành động ngoài phạm vi. | Audit integrity, tách log control. |
| **Reviewer là subordinate chịu áp lực từ actor** | Xung đột lợi ích theo hoàn cảnh. | Risk-tier approver/escalation độc lập. |
| **Shared emergency account không có named actor** | Không truy được cá nhân điều khiển. | Vault checkout/session binding; điều tra nếu vẫn mơ hồ. |
| **Reviewer cũng là beneficiary gián tiếp** | Có thể chấp thuận quyền mình được hưởng qua delegation/team. | Conflict-of-interest checks. |
| **Một người vừa ra exception vừa xác minh chính mình** | Không có kiểm soát bù độc lập. | Tách risk acceptance và verification theo policy. |

### 16.2. Cấp quyền khẩn có thể vi phạm SSD/DSD?

Trong kịch bản đặc biệt, một role khẩn có thể tạo **tổ hợp quyền SoD** mà thông thường không được phép. Chính sách có thể quy định **exception có kiểm soát**, gồm scope, thời hạn, cảnh báo và phê duyệt/hậu kiểm độc lập; nó không nên vô hiệu SoD trên mọi giao dịch.

Phải phân biệt:

- **SSD:** một người không nên được gán đồng thời hai quyền xung đột ngoài exception hợp lệ.
- **DSD:** không được thực hiện cả hai bước trên cùng giao dịch/phiên trái policy.
- **Procedural SoD:** người dùng không tự kích hoạt và tự chuẩn y một hành động không được phép.

Nếu emergency role thực sự cần quyền rộng, cần ghi rõ **đường sử dụng nào là ngoại lệ, quyền nào đã dùng và khi nào phải thu hồi**, không ghi “emergency bypass” như một quyền miễn trừ tất cả kiểm soát.

### 16.3. Khi không đủ người duyệt độc lập

Không phải tình huống khẩn đều có sẵn hội đồng duyệt. Hậu kiểm có thể **bắt đầu** bằng thu thập evidence và giữ trạng thái pending, sau đó escalate tới reviewer có thẩm quyền. Nếu tổ chức chấp nhận **dual control hoặc hậu kiểm độc lập ở cấp khác**, cần có policy định nghĩa rõ. **Không để actor tự ký vì “không có người khác”.**

## 17. Emergency access đối với tài khoản dịch vụ và workload identity

Emergency action không nhất thiết do con người đăng nhập. Một pipeline cô lập cloud resource, một runbook tự động thu hồi API token hoặc một service principal phục hồi cấu hình đều có thể dùng **đặc quyền mạnh**.

### 17.1. Principal kỹ thuật cần có owner và mục đích

| Thuộc tính | Nội dung cần kiểm |
| --- | --- |
| **principalId/workloadId** | Danh tính máy nào đã hành động. |
| **ownerTeam/technicalOwner** | Ai chịu trách nhiệm cấu hình và hậu kiểm. |
| **automation/runbook version** | Mã/quy trình nào đã thực thi, ai phê duyệt version. |
| **trigger source** | Sự kiện nào kích hoạt và có được policy cho phép? |
| **credential type/scope** | Managed identity, federated token, key/certificate và quyền API. |
| **resource/tenant** | Chỉ những tài nguyên nào được tác động. |
| **actions/results** | Job đã sửa/xóa/thay đổi điều gì. |
| **deactivation/rotation** | Privilege/credential đã trở về baseline ra sao. |
| **reviewer independence** | Ai đánh giá nếu người viết runbook cũng sở hữu job? |

### 17.2. Không dùng PAT cá nhân dài hạn cho cứu hệ thống

Nếu automation tạm dùng **Personal Access Token (PAT)** của một kỹ sư và người đó Mover/Leaver, hậu kiểm phải xác định:

- Token thuộc chủ thể nào, được phát hành khi nào, scope và expiry.
- Lệnh nào đã dùng token, có lộ qua log, ticket hoặc script không.
- Có thể chuyển workload sang **managed/workload identity hoặc credential ngắn hạn** được quản lý không.
- Khi nào thu hồi PAT và cách bảo đảm job hợp lệ vẫn hoạt động.

Không duy trì account của Leaver chỉ để tránh phải sửa automation. **Owner của job và vòng đời principal máy phải độc lập với vòng đời account cá nhân**.

### 17.3. Phê duyệt chính sách automation và hậu kiểm từng activation

Một runbook emergency có thể được **phê duyệt trước ở cấp policy/version**. Sau mỗi activation vẫn cần:

1. Xác nhận trigger khẩn là hợp lệ.
2. Kiểm runbook version và actor/workload đã thực thi đúng.
3. So actual resource changes với phạm vi thiết kế.
4. Thu hồi elevation/credential nếu phát sinh.
5. Xác minh kết quả và ghi hậu kiểm, ngoại lệ.

**Auto-execution không đồng nghĩa auto-ratification**, nhất là khi có hành động vượt playbook hoặc logging thiếu.

## 18. Mô hình dữ liệu hồ sơ phê duyệt sau sự kiện

Một hồ sơ nên tách **sự kiện kích hoạt**, **quyền thực tế**, **đánh giá**, **quyết định** và **tác vụ sửa** để audit không bị mất lịch sử.

### 18.1. Các thực thể khái niệm

| Entity | Trường chính | Mục tiêu |
| --- | --- | --- |
| **EmergencyEvent** | eventId, incidentId, trigger, severity, activationAt/endAt. | Một lần sử dụng emergency. |
| **ActorIdentity** | subjectId, personId/engagementId hoặc workloadId, accountId. | Biết ai hoặc workload nào điều khiển. |
| **PrivilegeActivation** | role, tenant/resource scope, access path, sessionRef. | Xác định khả năng truy cập được mở. |
| **EvidenceReference** | evidenceId, sourceSystem, observedAt, integrityRef. | Truy vết sự thật không nhúng secret. |
| **ReviewAssignment** | reviewerId, authorityScope, assignedAt, dueAt. | Quản lý người đánh giá và hạn. |
| **ReviewDecision** | decisionId, result, reason, policyVersion, decisionAt. | Lưu quyết định có căn cứ. |
| **RemediationTask** | taskId, target, action, owner, dueAt, state. | Theo dõi việc phải sửa. |
| **VerificationEvidence** | verifiedAt, observedState, method, reviewer/agent. | Chứng minh trạng thái cuối. |
| **RiskException** | exceptionId, riskOwner, mitigations, expiresAt. | Quản trị điều chưa thể đóng. |

### 18.2. Ví dụ JSON sự kiện (giả định)

~~~json
{
  "eventId": "emg-20261201-007",
  "incidentId": "inc-20261201-identity-outage",
  "policyId": "EMERGENCY-PROD-RECOVERY",
  "policyVersion": 5,
  "activationAt": "2026-12-01T02:15:00+07:00",
  "eventEndedAt": "2026-12-01T03:10:00+07:00",
  "principalType": "HUMAN",
  "actorSubjectId": "person-1042",
  "engagementId": "EMP-5812",
  "accountId": "breakglass-account-a",
  "privilegeId": "emergency-identity-operator",
  "tenantId": "tenant-a",
  "resourceScope": "identity-recovery",
  "sessionEvidenceRefs": ["pam-session-ref-8801"],
  "alertStatus": "ACKNOWLEDGED",
  "revocation": {
    "state": "REVOKED_VERIFIED",
    "verifiedAt": "2026-12-01T03:18:00+07:00",
    "evidenceRef": "verify-8808"
  },
  "postEventReview": {
    "state": "RATIFIED_WITH_ACTIONS",
    "reviewerSubjectId": "person-2088",
    "decisionAt": "2026-12-01T09:30:00+07:00",
    "reason": "Khôi phục hợp lệ; thiếu một cảnh báo dự phòng.",
    "remediationTaskRefs": ["fix-alert-103"]
  }
}
~~~

Đây là **schema nội bộ minh họa**, không phải định dạng API chuẩn của PAM, SCIM hoặc OAuth. ID và thời gian hoàn toàn giả định. Trong hệ thống thật, các trạng thái có thể đến qua **nhiều event bất đồng bộ**, cần lưu event version và không sửa đè bằng chứng cũ.

### 18.3. Các mốc bắt buộc không đồng nhất

~~~text
triggerDetectedAt
activationAt
firstPrivilegedActionAt
incidentContainmentAt
lastPrivilegedActionAt
eventEndedAt
revocationRequestedAt
revokedVerifiedAt
reviewAssignedAt
reviewDecisionAt
remediationVerifiedAt
~~~

**“Incident resolved” khác “privileged access revoked”, và khác “post-event review completed”.** Báo cáo phải tách ba dòng thời gian để phát hiện cửa sổ quyền tồn dư và chậm hậu kiểm.

## 19. Quy tắc quyết định (pseudocode) có kiểm soát

~~~text
openPostEventReview(emergencyEvent):
    requireKnownEventAndIncidentReferences(emergencyEvent)
    actor = correlateIdentityUsingTrustedSources(emergencyEvent)
    preserveEvidenceReferencesAndSourceVersions(emergencyEvent)

    if actor is unknown:
        openIdentityExceptionWithRiskMitigation(emergencyEvent)

    collectActivationScopeSessionAndTargetActions(emergencyEvent)
    triggerOrVerifyPrivilegeRevocationWithoutWaitingForApproval()
    approver = chooseIndependentAuthorizedReviewer(
        emergencyEvent.policyId,
        emergencyEvent.riskTier,
        currentReviewerAuthority()
    )
    assignReviewWithDueAtAndImmutableAuditRefs(approver)

evaluatePostEvent(emergencyEvent, authenticatedReviewer):
    verifyReviewerAuthorityNow(authenticatedReviewer)
    rejectSelfApprovalAtCanonicalPersonAndControlLevel()
    evidence = loadEvidenceWithIntegrityAndFreshnessChecks()
    policy = loadApplicablePolicyVersionAtActivationTime()
    current = loadCurrentJmlAndPrivilegeStateForFutureAccess()

    if evidence is insufficient:
        return INDETERMINATE_WITH_OWNER_AND_MITIGATION
    if suspiciousOrUnauthorizedActionsExist(evidence, policy):
        referToSecurityInvestigationAndProtectEvidence()
        return REJECTED_OR_ESCALATED
    if legitimateButControlsNeedRemediation(evidence, policy):
        openTrackedRemediationWithDueAtAndVerification()
        return RATIFIED_WITH_ACTIONS

    recordReasonEvidenceScopeAndDecisionTime()
    return RATIFIED

closePostEventCase(case):
    requireReviewerDecisionOrDocumentedEscalatedResolution()
    requireAllCriticalRemediationVerifiedOrApprovedTimeBoundException()
    requireRevocationEvidenceOrExplicitTrackedUnverifiableRisk()
    attachAuditTimelineAndOwnerSignoff()
    closeOnlyWithinDocumentedAssuranceScope()
~~~

**Giả mã nhằm minh họa luồng logic**, không phải phần mềm sẵn sàng chạy. Triển khai thực cần xử lý request version, idempotency, audit integrity, concurrent event, timeout, quyền reviewer, lỗi provider và chính sách exception riêng của tổ chức.

### 19.1. Không nhận quyết định từ client tự khai

Không nên chấp nhận payload có `reviewApproved=true` hoặc `approverId` do actor tự điền làm bằng chứng phê duyệt. Endpoint phải lấy **reviewer đã xác thực**, kiểm authority/SoD và ràng buộc quyết định với **event ID, action scope, policy version và evidence snapshot**.

### 19.2. Policy version nào được dùng?

Hai góc nhìn cần tách:

- **Đánh giá hành động quá khứ:** dùng policy có hiệu lực **tại thời điểm activation/use**, đồng thời xem nghĩa vụ khác có liên quan.
- **Quản trị quyền còn tồn tại:** dùng policy và trạng thái hiện hành để quyết định **giữ, giảm hoặc thu hồi**.

Nếu chỉ dùng policy mới để áp ngược mà không làm rõ thay đổi, reviewer có thể đánh giá không nhất quán. Ngược lại, policy cũ không cho phép duy trì một quyền hiện đã bị cấm.

## 20. Case study 1 – IdP/SSO outage và break-glass hợp lệ

**Bối cảnh giả định:** IdP không cấp đăng nhập mới, khiến nhóm vận hành không thể sửa cấu hình identity gateway qua SSO. Tổ chức có emergency account dự phòng được quản lý theo policy.

### 20.1. Dòng thời gian

| Thời điểm giả định | Sự kiện | Bằng chứng cần giữ |
| --- | --- | --- |
| **02:10** | Monitoring xác nhận IdP outage. | Incident ref, alert source, mức độ ảnh hưởng. |
| **02:15** | Kỹ sư trực ca kích hoạt break-glass hợp lệ. | Actor, account, checkout/activation metadata. |
| **02:16** | Alert gửi Security/on-call. | Dấu thời gian gửi và acknowledgement. |
| **02:20–03:00** | Actor thực hiện những thay đổi recovery được phép. | Session/command metadata, change reference. |
| **03:10** | IdP hồi phục, phiên emergency kết thúc. | Service state, session end. |
| **03:18** | PAM và ứng dụng xác minh quyền khẩn không còn sử dụng ngoài scope. | Revoke/readback và session evidence. |
| **09:30** | Reviewer độc lập kiểm log và ra quyết định. | Review record, policy version, kết luận và lý do. |

### 20.2. Kết luận đúng

Giả sử mọi thao tác phù hợp mục đích và phiên đã đóng, nhưng alert dự phòng bị trễ trong lúc hệ thống giám sát phụ lỗi. Reviewer có thể đưa ra:

~~~text
Decision: RATIFIED_WITH_ACTIONS
LegitimateEmergency: YES (theo evidence và policy có hiệu lực)
ActionsInScope: VERIFIED
PrivilegeRevocation: VERIFIED
Finding: Alert fallback chưa bảo đảm timing theo policy
ActionOwner: Security Operations
FollowUp: Kiểm thử kênh cảnh báo dự phòng và lưu evidence
~~~

**Không nên gọi đây là “bypass được phê duyệt trước”**; nó là một lần sử dụng emergency theo cơ chế có sẵn, được đánh giá và kết luận sau khi xảy ra.

### 20.3. Điều gì sẽ thay đổi kết luận?

- Không liên kết được emergency account với actor cụ thể.
- Có thao tác export dữ liệu không liên quan khôi phục.
- Một admin role mới vẫn thường trực sau outage.
- Sự kiện xảy ra ngoài khoảng khẩn thực tế hoặc dùng tài khoản của Leaver.
- Log bị vô hiệu hóa hoặc xuất hiện thay đổi audit policy không có căn cứ.

Những dấu hiệu này cần điều tra, phân loại vi phạm và có thể **không phê duyệt**, dù IdP đã được khôi phục.

## 21. Case study 2 – Dùng emergency access để tránh quy trình thường

**Bối cảnh giả định:** một đội muốn triển khai thay đổi production lúc cuối ngày. Không có incident nghiêm trọng, IAM/IGA và PAM approval vẫn sẵn có, nhưng người thực hiện không muốn chờ người duyệt. Họ kích hoạt cơ chế emergency với lý do “deadline”.

| Tiêu chí | Quan sát giả định | Đánh giá |
| --- | --- | --- |
| **Tình huống khẩn** | Không có outage/incident đáp ứng policy. | Không đủ căn cứ emergency. |
| **Đường phê duyệt thường** | Đang hoạt động. | Có lựa chọn ít rủi ro hơn. |
| **Scope** | Admin toàn production thay vì role deploy hẹp. | Vượt least privilege. |
| **Hành động** | Thay cấu hình ngoài change được phê duyệt. | Cần kiểm tác động và owner. |
| **Phiên/token** | Một token được phát còn hạn sau deploy. | Cần thu hồi và xác minh. |

### 21.1. Xử lý đúng

1. **Không ratify** một cách tự động vì deployment chạy thành công.
2. Thu hồi hoặc hạn chế quyền còn tồn tại, đọc lại quyền tại đích.
3. Đối chiếu change đã thực hiện với baseline và kiểm log.
4. Security/owner đánh giá vi phạm policy, tác động và biện pháp xử lý phù hợp.
5. Sửa quy trình JIT/access request để công việc thường không phải dùng emergency.
6. Ghi decision, incident/exception nếu có, remediation và bằng chứng.

**Bài học:** hậu kiểm phải có khả năng kết luận **NOT_RATIFIED**, nếu không nó chỉ trở thành thủ tục hợp thức hóa.

## 22. Case study 3 – Mover/Leaver và quyền khẩn tồn dư

**Bối cảnh giả định:** một kỹ sư đã Mover khỏi SRE nhưng còn eligible role emergency trong PAM. Họ sử dụng quyền khi có sự cố production; sau đó HRIS phát Leaver có hiệu lực trong khi token API còn sống.

### 22.1. Những câu hỏi không được bỏ qua

1. Tại thời điểm kích hoạt, kỹ sư **còn thuộc nhóm người đủ điều kiện emergency** không?
2. Role cũ tồn tại vì **dynamic group stale, direct PAM grant hay lỗi chuyển vai trò**?
3. Người đó đã thực hiện hành động nào, có liên quan trực tiếp tới incident không?
4. Leaver effectiveAt trước hay sau các hành động?
5. Token/session sau Leaver có thể thực thi những quyền gì?
6. Ai có thẩm quyền hậu kiểm độc lập, khi manager cũ đã không còn vai trò?
7. Đã thu hồi ở PAM, IdP, cloud, app-local và API issuer đầy đủ trong phạm vi chưa?

### 22.2. Bảng quyết định theo giai đoạn

| Thời đoạn | Mục tiêu | Không được suy luận |
| --- | --- | --- |
| **Trước Mover** | Kiểm quyền emergency từng được cấp hợp lệ. | Vì từng hợp lệ nên hiện còn hợp lệ. |
| **Sau Mover, trước Leaver** | Đánh giá eligibility và hành động theo chính sách có hiệu lực. | Nếu cứu dịch vụ thành công thì grant tồn dư được chấp nhận. |
| **Sau Leaver effectiveAt** | Chặn mọi đường đặc quyền không còn hợp lệ, xác minh và điều tra. | IdP disabled nghĩa là API token chắc chắn bị thu hồi. |
| **Khi hậu kiểm** | Chốt sự thật, decision theo từng giai đoạn, root cause và remediation. | Decision được phép mở lại account đã kết thúc engagement. |

### 22.3. Kết quả kỳ vọng

Với bằng chứng đủ, review có thể xác nhận **một số hành động phục hồi có ích** nhưng vẫn xác định **lỗi privilege creep, không tuân thủ eligibility hoặc cửa sổ token tồn dư**. Quyết định cần giải thích cụ thể **điều gì hợp lệ, điều gì không**, xử lý theo policy và cải tiến JML sync. Không nén toàn bộ sự kiện vào một boolean “approved=true”.

## 23. Case study 4 – Workload cứu hệ thống nhưng để lại cloud credential

**Bối cảnh giả định:** một automation được kích hoạt để cô lập một dịch vụ cloud khi có dấu hiệu xâm nhập. Runbook được phê duyệt trước, nhưng trong lúc khẩn, job tạo một credential mới để gọi API và không thu hồi sau khi hoàn tất.

### 23.1. Hậu kiểm chia thành hai kết luận

| Đối tượng đánh giá | Bằng chứng | Kết luận có thể có |
| --- | --- | --- |
| **Trigger sự cố** | Security alert, incident, time. | Đúng điều kiện chạy emergency runbook. |
| **Workload identity** | service principal, ownerTeam, runbook version. | Principal hợp lệ và có owner. |
| **Quyền sử dụng** | Resource action logs, role policy. | Các hành động cô lập nằm trong scope. |
| **Credential mới** | Credential inventory, issuer, scope, createdAt. | Quyền tồn dư không cần thiết, phải thu hồi. |
| **Thực thi cleanup** | Revocation request/readback/API access check. | Chưa được VERIFIED cho tới khi kiểm đích. |
| **Post-event decision** | Reviewer độc lập, evidence. | Có thể RATIFIED_WITH_ACTIONS nếu policy cho phép, nhưng rủi ro vẫn OPEN. |

### 23.2. Hành động đúng

Thay vì xóa vội workload đang cần phục vụ điều tra, nhóm chịu trách nhiệm:

1. Kiểm những workload/job nào đang dùng credential.
2. Chuyển hoạt động hợp lệ sang **managed/workload identity, token ngắn hạn hoặc role được quản trị** khi có thể.
3. Thu hồi credential và role thừa theo change plan.
4. Đọc lại effective access và thử quyền theo phạm vi được ủy quyền.
5. Bổ sung cleanup vào runbook và test hồi quy sau khi nâng phiên bản.
6. Ghi thời gian credential từng tồn tại ngoài nhu cầu, risk owner và bằng chứng đã khắc phục.

**Bài học:** kết quả automation hoàn thành tác vụ khẩn không bảo đảm quyền đặc biệt của automation đã biến mất.

## 24. Rủi ro từ sự kiện đến muộn, retry và phê duyệt trên snapshot cũ

IAM/JML là hệ thống phân tán. Một emergency event, revoke task hoặc review decision có thể đến hệ thống theo thứ tự khác thực tế.

### 24.1. Một tình huống nguy hiểm

~~~text
02:15  Emergency JIT role được kích hoạt cho Person P-1042.
03:10  Sự cố kết thúc, hệ thống yêu cầu revoke.
03:11  Connector thu hồi role bị timeout; trạng thái UNKNOWN.
03:12  Nhân viên nhận sự kiện Leaver có hiệu lực ngay.
03:15  Retry một activation job cũ cố gán role emergency trở lại.
09:30  Reviewer chuẩn y phiên 02:15 dựa trên bằng chứng hợp lệ.
~~~

Nếu có lỗi, một hệ thống có thể hiểu quyết định lúc 09:30 là **cho phép cấp lại role**. Đây là cách dùng sai bản chất của phê duyệt sau sự kiện.

### 24.2. Những kiểm soát cần có

| Kiểm soát | Mục đích |
| --- | --- |
| **Event ID và idempotency key** | Không xử lý trùng activation/revoke. |
| **Source version/effectiveAt** | Không dùng Mover/Joiner cũ để vượt Leaver mới. |
| **Current authoritative JML lookup** | Kiểm trạng thái chủ thể trước mọi grant/elevation còn tác động. |
| **Review decision bound to past event** | Kết luận hậu kiểm không là authorization grant mới. |
| **Separate command domains** | Review API không có quyền phát role admin trực tiếp. |
| **Target readback & retry reconciliation** | Timeout không bị hiểu nhầm thành thành công/thất bại. |
| **Exception on unverifiable access** | Quyền chưa rõ có owner và biện pháp giảm thiểu. |
| **Audit immutable versioning** | Giữ thứ tự quyết định và thay đổi có thể truy vết. |

### 24.3. Không để phê duyệt lại tạo hiệu lực mới

Một thiết kế an toàn cần ràng buộc:

~~~text
POST_EVENT_RATIFICATION
  -> chỉ cập nhật trạng thái đánh giá cho eventId đã xảy ra
  -> không tự gọi GRANT, ACTIVATE hoặc REOPEN_ACCOUNT

NEW_PRIVILEGE_REQUEST
  -> workflow khác, kiểm current JML + eligibility + SoD
  -> approval trước hoặc emergency procedure riêng nếu hợp lệ
~~~

Đây là **quy tắc kiến trúc gợi ý**, không phải tên API tiêu chuẩn. Mục đích là giữ ranh giới giữa **đánh giá quá khứ** và **cấp quyền tương lai**.

## 25. Kiểm thử quy trình phê duyệt sau sự kiện

Đừng chờ một outage thật mới biết reviewer route, session record hoặc revoke không hoạt động. Cần **tabletop exercises, integration tests và controlled break-glass drills** trong môi trường an toàn.

### 25.1. Ma trận test cơ bản

| Test ID | Điều kiện | Expected |
| --- | --- | --- |
| **PE-01** | Emergency activation hợp lệ, session record đủ. | Tạo event, alert, hậu kiểm có owner và deadline. |
| **PE-02** | Actor tự đăng nhập reviewer account phụ để ratify. | Từ chối self-approval theo canonical Person. |
| **PE-03** | Reviewer đã Mover và mất authority. | Revalidate, chuyển tuyến; không chấp thuận từ link cũ. |
| **PE-04** | Incident hợp lệ, role chưa revoke được. | Quyết định review và revoke state tách riêng; exception OPEN. |
| **PE-05** | Lý do “khẩn” nhưng không có incident đáp ứng policy. | Không auto-ratify, yêu cầu review/điều tra. |
| **PE-06** | Session evidence thiếu do log collector outage. | INDETERMINATE hoặc xử lý theo policy, không suy ra PASS. |
| **PE-07** | Break-glass account đã đóng, token API vẫn hoạt động. | Cảnh báo residual access và remediation. |
| **PE-08** | Leaver phát sinh sau activation, trước reviewer decision. | Thu hồi đúng thời điểm; review không phục hồi role. |
| **PE-09** | Hai review decisions đến đồng thời cho cùng event. | Version/concurrency control, không tạo hai kết luận mâu thuẫn đang active. |
| **PE-10** | Review quá hạn. | Nhắc việc/escalate độc lập, không tự approved. |
| **PE-11** | Revoke API trả HTTP 204, app-local admin vẫn ACTIVE. | Chưa REVOKED_VERIFIED, cần xử lý đường direct. |
| **PE-12** | Workload emergency dùng credential còn sống sau incident. | Cleanup/rotation/readback và post-action risk tracking. |
| **PE-13** | Incident thực sự hợp lệ nhưng không giải quyết được vấn đề. | Đánh giá hành vi theo policy, không dùng “chưa phục hồi” làm tiêu chí duy nhất. |
| **PE-14** | Post-event approval bị replay để kích hoạt quyền mới. | Không grant quyền; review decision chỉ gắn past event. |

### 25.2. Positive và negative tests phải đi đôi

- **Positive:** một emergency event đúng policy, có actor, evidence, reviewer độc lập và quyền đã thu hồi được xử lý thành công.
- **Negative:** event không đúng policy, self-approval, thiếu evidence hoặc token tồn dư phải **bị phát hiện và xử lý**, không bị đánh dấu hoàn tất.
- **Boundary:** kịch bản ngay trước/sau `expiresAt`, manager change, Mover/Leaver, timezone khác nhau, session quá hạn.
- **Failure injection:** PAM unavailable, SCIM timeout, audit sink lỗi, HRIS event đến muộn, reviewer không thể truy cập.

### 25.3. Test không được gây thêm rủi ro

Các cuộc diễn tập chỉ nên dùng **tài khoản thử nghiệm có owner, kịch bản được cấp phép, scope hẹp và dữ liệu giả**; kiểm cleanup bằng readback. Không phá IdP production, mở quyền admin toàn tenant hoặc truy xuất dữ liệu thật chỉ để chứng minh hệ thống có break-glass. Khi cần thử production, chọn phương pháp được ban an toàn/change owner cho phép, giới hạn phạm vi và thời gian.

## 26. Báo cáo hậu kiểm và bằng chứng kiểm toán

Một post-event approval report cần giải trình được cả **việc dùng quyền** lẫn **việc chấp thuận hoặc không chấp thuận**:

### 26.1. Bộ trường audit khuyến nghị

| Trường | Ý nghĩa |
| --- | --- |
| **eventId, incidentId, traceId** | Liên kết activation, incident và post-event review. |
| **policyId/version** | Luật có hiệu lực khi activation. |
| **actorSubjectId, personId/engagementId, accountId** | Biết principal nào và người nào đã dùng quyền. |
| **workloadId/ownerTeam** | Trách nhiệm của sự kiện non-human nếu có. |
| **roleId, resourceScope, accessPath** | Quyền nào, tenant nào và qua đường nào. |
| **activationAt, actionTimes, eventEndedAt** | Dòng thời gian quyền sử dụng. |
| **evidenceRef/sourceObservedAt** | Nguồn log, tính mới và toàn vẹn. |
| **reviewerSubjectId, authorityRef** | Ai đánh giá và vì sao có quyền duyệt. |
| **decision, reason, decisionAt** | Kết luận và lý do. |
| **sodOutcome, exceptionRef** | SoD, rủi ro và ngoại lệ. |
| **revokeRequestId, providerResult** | Lệnh thu hồi thực tế. |
| **revokedVerifiedAt, verificationMethod** | Bằng chứng quyền không còn hoạt động theo scope. |
| **remediationTasks, owner, dueAt** | Điều phải sửa tiếp và người chịu trách nhiệm. |

### 26.2. Mẫu executive summary

~~~text
POST-EVENT EMERGENCY ACCESS REVIEW – EXAMPLE
Incident: INC-20261201-IDENTITY-OUTAGE
Review as-of: 2026-12-01 10:00 +07:00
Policy: EMERGENCY-PROD-RECOVERY / version 5

Actor / principal: P-1042 / breakglass-account-a
Activation: 02:15      Session ended: 03:10
Purpose: Khôi phục identity gateway khi SSO outage

Emergency legitimacy: Supported by incident evidence
Actions: Within reviewed recovery scope
Post-event decision: RATIFIED_WITH_ACTIONS
Reviewer: Independent security owner

Revocation: REVOKED_VERIFIED at 03:18
Outstanding finding: Alert fallback delayed
Finding owner: Security Operations
Remediation due: theo policy được phê duyệt
Assurance limitation: chỉ những app/session paths đã liệt kê
~~~

Mẫu này là **dữ liệu giả định**, không phải tài liệu của doanh nghiệp thực. Mọi kết luận cần có evidence; nếu không có số liệu hoặc phạm vi chưa kiểm, ghi **UNKNOWN/NOT_VERIFIED**, không tự điền “0 rủi ro”.

### 26.3. Snapshot và điều chỉnh hậu kiểm

Nếu có phát hiện mới sau khi reviewer ký, không nên sửa đè record cũ để làm như trước đó đã biết mọi thứ. Sử dụng:

1. **Decision event** gốc với version, reviewer và evidence snapshot.
2. **Supplemental finding** có thời gian và nguồn mới.
3. **Reopened review/escalation** khi phát hiện làm thay đổi kết luận.
4. **Remediation và verification event** riêng.

Nhờ vậy, kiểm toán có thể phân biệt **quyết định dựa trên thông tin sẵn có** và **thông tin phát sinh sau đó**.

## 27. KPI cho phê duyệt sau sự kiện

Một tổ chức nên đo **độ đầy đủ, kịp thời, độc lập và hiệu quả khắc phục**, không chỉ phần trăm “Approved”.

| Chỉ số | Cách tính/quan sát gợi ý | Điều phản ánh |
| --- | --- | --- |
| **Emergency event capture rate** | Events có hồ sơ và owner ÷ events phát hiện từ các nguồn. | Độ đầy đủ của inventory. |
| **Alert delivery/ack latency** | Khoảng từ activation tới alert/ack theo SLA. | Giám sát có hoạt động khi khẩn? |
| **Post-event review coverage** | Events trong scope có review được giao ÷ events bắt buộc. | Mức bao phủ đánh giá. |
| **Timely independent review rate** | Review đủ thẩm quyền hoàn tất đúng hạn ÷ review đến hạn. | Kỷ luật và SoD trong hậu kiểm. |
| **RATIFIED / REJECTED / INDETERMINATE distribution** | Số events theo quyết định, có lý do. | Chất lượng và khả năng phát hiện vấn đề. |
| **Revocation verification rate** | Emergency privilege paths được xác minh thu hồi ÷ paths phải thu hồi. | Quyền thực tế đã chấm dứt. |
| **Post-event residual privilege count** | Grant/session/token được xác nhận còn vượt nhu cầu. | Rủi ro tồn dư. |
| **Revoke verification latency** | `revokedVerifiedAt - endOfNeededAccessAt`. | Thời gian phơi lộ sau khi hết nhu cầu. |
| **Remediation overdue count** | Finding chưa VERIFIED và đã quá dueAt. | Nợ kiểm soát sau emergency. |
| **Evidence completeness rate** | Events có đủ chứng cứ theo risk tier ÷ events cần chứng cứ. | Khả năng ra quyết định đáng tin. |
| **Self-approval attempts blocked** | Số lần bị chặn do actor/approver trùng hoặc xung đột. | Tình trạng kiểm soát độc lập. |
| **Unauthorized emergency usage** | Những sự kiện không đáp ứng policy đã xác minh. | Dùng khẩn thay quy trình thường. |
| **Unverifiable access paths** | Số đường truy cập không thể kiểm effective access. | Giới hạn tính bảo đảm. |
| **Break-glass readiness** | Kết quả diễn tập, owner/monitoring/credential policy. | Khả năng cứu hệ thống mà vẫn kiểm soát. |

### 27.1. Không dùng tỷ lệ chấp thuận làm tiêu chí thành công

Một hệ thống báo **100% RATIFIED** có thể thực sự an toàn, nhưng cũng có thể do reviewer luôn nhấn Approve hoặc không có cách đánh giá độc lập. Cần xem:

- Bao nhiêu activation thực sự xảy ra, có **nghiệp vụ hợp lệ** không?
- Có bao nhiêu event **không đủ bằng chứng**?
- Có bao nhiêu quyền vẫn có thể được sử dụng sau khi event kết thúc?
- Có bao nhiêu sai lệch được sửa và **VERIFIED**?
- Quyền emergency có bị lạm dụng thay access request thường xuyên không?

### 27.2. Mẫu số và giới hạn

Nếu không có lần emergency nào trong kỳ, `0/0` không nên ghi 100% review success; dùng **N/A, không phát sinh**. Nếu PAM mới quan sát được 80% hệ thống, phải nêu rõ **coverage**, không kết luận toàn doanh nghiệp không có emergency use.

## 28. Những sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| **Mọi việc khẩn đều được auto-approve sau đó** | Hậu kiểm mất ý nghĩa; lạm dụng trở thành thói quen. | Reviewer độc lập có quyền RATIFIED/REJECTED/INDETERMINATE. |
| **Coi incident resolved là review completed** | Quyền/token tồn dư hoặc hành động ngoài scope chưa được đánh giá. | Tách recovery, revocation và review status. |
| **Actor tự duyệt qua admin account phụ** | Self-approval giả độc lập. | SoD theo canonical Person và owner/control. |
| **Không alert khi kích hoạt break-glass** | Không phát hiện kịp lạm dụng hoặc chia sẻ credential. | Alert, fallback channel và kiểm thử định kỳ. |
| **Tin PAM session ended là toàn bộ quyền đã mất** | Local role, cloud token, PAT còn hoạt động. | Đọc lại effective access theo từng target/path. |
| **Chờ hậu kiểm rồi mới thu hồi** | Cửa sổ quyền cao kéo dài không cần thiết. | Revoke/mitigate ngay khi hết mục đích. |
| **Dùng policy hiện tại để đánh giá mọi sự kiện quá khứ** | Kết luận sai do policy thay đổi. | Lưu version có hiệu lực khi activation, xem current policy cho quyền tương lai. |
| **Không tính Joiner/Mover/Leaver** | Actor không còn eligible hoặc reviewer mất authority. | Kiểm authoritative lifecycle/effectiveAt. |
| **Gộp REJECTED với PENDING** | Che vi phạm chính sách hoặc thiếu chứng cứ. | Enum rõ và quy trình escalation riêng. |
| **Exception không owner/expiry** | Rủi ro được hợp thức hóa vô hạn. | Risk acceptance có thẩm quyền, hạn và controls. |
| **Xóa log sau khi xử lý sự cố** | Không còn khả năng điều tra hoặc chứng minh. | Bảo vệ evidence và event history. |
| **Dùng account của Leaver cho automation** | Truy cập tồn dư ngoài vòng đời cá nhân. | Managed/workload identity, transfer owner và credential lifecycle. |
| **Hậu kiểm chỉ dựa lời kể người dùng** | Không đủ bằng chứng về hành động thực tế. | PAM/API audit, change record, target readback. |
| **Không kiểm hành động sau khẩn** | Policy/config/secret còn bị mở rộng. | Diff baseline, fix và verification. |
| **Cấp lại quyền khi case được RATIFIED** | Biến review quá khứ thành lệnh grant mới trái JML. | Tách API review và activation, kiểm source hiện hành. |

## 29. Checklist triển khai phê duyệt sau sự kiện

### 29.1. Chính sách và chuẩn bị

1. Đã định nghĩa **kịch bản khẩn hợp lệ**, thẩm quyền, risk tier, scope và thời hạn chưa?
2. Có phân biệt **phê duyệt trước, emergency exception và phê duyệt/hậu kiểm sau sự kiện** không?
3. Break-glass/JIT/PAM có owner, danh tính được phép, bảo quản credential và kế hoạch kiểm thử không?
4. Có kênh **alert/notification dự phòng** khi IdP/PAM/monitoring thông thường gặp sự cố không?
5. Có thời hạn **acknowledgement, thu hồi, hậu kiểm và remediation** do policy xác định không?

### 29.2. Trong sự kiện

6. Mỗi activation có **eventId, incidentId, actor/principal, role, tenant, scope và timestamp** không?
7. Có ghi session/command hoặc action audit phù hợp, bảo vệ bằng chứng mà không lộ secret không?
8. Actor có được xác minh và liên kết đúng Person/Engagement hoặc workloadId/owner không?
9. Quyền được dùng **theo mục đích khẩn**, ít quyền và ít thời gian nhất có thể không?
10. Khi phát hiện hoạt động bất thường, có luồng **incident response** riêng không?

### 29.3. Sau sự kiện: quyền và bằng chứng

11. Đã đóng **PAM/JIT session**, revoke role/token/PAT và xử lý credential theo chính sách chưa?
12. Có phân biệt **REVOKE_REQUESTED, ACKNOWLEDGED, REVOKED_VERIFIED** không?
13. Có đọc lại **IdP/directory, SCIM, SaaS local role, cloud/API và session** trong phạm vi không?
14. Có đánh dấu **UNKNOWN/UNVERIFIABLE** khi không thể kiểm quyền thực tế không?
15. Có đối chiếu thay đổi cấu hình, policy, secret, data và logging với baseline không?
16. Có lưu evidence version, source timestamps, trace IDs và bảo vệ tính toàn vẹn không?

### 29.4. Hậu kiểm và quyết định

17. Reviewer và approver có **đúng authority, độc lập với actor/beneficiary** và tránh self-approval không?
18. Có đánh giá theo **policy tại lúc activation** và kiểm JML hiện hành cho quyền còn tồn tại không?
19. Có phân biệt **RATIFIED, RATIFIED_WITH_ACTIONS, REJECTED, INDETERMINATE** không?
20. Khi không có người duyệt đúng hạn, có **escalation** thay vì auto-approve không?
21. Nếu action không hợp lệ, có quy trình điều tra, xử lý hậu quả và bảo toàn bằng chứng không?
22. Nếu bằng chứng không đủ, có ghi gap, owner, hạn và biện pháp giảm rủi ro không?
23. Quyết định ratification có được ràng buộc **chỉ với sự kiện đã xảy ra**, không tự tạo grant mới không?

### 29.5. Vòng đời và cải tiến

24. Joiner có bị ngăn dùng quyền khẩn trước Start date nếu policy không cho phép không?
25. Mover có được **thu hồi eligibility/role cũ** và cập nhật approver/reviewer theo nguồn đáng tin không?
26. Leaver có được chặn **mọi đường quyền khẩn**, kể cả session/token và retry grant cũ không?
27. Rehire có được xét theo engagement mới, không tự phục hồi secret/approval cũ không?
28. Service/workload principal có owner, scope, credential lifecycle và cleanup đúng không?
29. Finding/exception có **owner, severity, dueAt, acceptance authority và verified closure** không?
30. Có diễn tập tình huống **outage, thiếu log, timeout, self-approval, reviewer Mover/Leaver và token tồn dư** không?
31. KPI có tách **event capture, independent review, revocation verification và overdue remediation** không?
32. Báo cáo có công bố **giới hạn quan sát**, không tự tuyên bố an toàn tuyệt đối không?

## 30. Kết luận: chấp thuận quá khứ không thay thế kiểm soát hiện tại

Trong emergency access, tổ chức phải giải quyết đồng thời hai nhu cầu:

~~~text
KHÔI PHỤC / ỨNG CỨU ĐÚNG LÚC
  Đường khẩn được chuẩn bị trước, actor và phạm vi hợp lệ
                   |
                   v
CHẤM DỨT QUYỀN KHẨN SAU KHI HẾT NHU CẦU
  Đóng session, revoke credential/role, kiểm effective access
                   |
                   v
HẬU KIỂM ĐỘC LẬP VÀ CÓ BẰNG CHỨNG
  Đánh giá legitimacy, purpose, scope, time, SoD, impact
                   |
                   v
QUYẾT ĐỊNH MINH BẠCH + XỬ LÝ SAI LỆCH
  Ratified / with actions / rejected / indeterminate
                   |
                   v
KIỂM TOÁN VÀ CẢI TIẾN VÒNG ĐỜI IAM
  JML, PAM, IdP/SSO/SCIM, role/credential/session, test
~~~

**Ghi nhớ:** **Phê duyệt sau sự kiện là sự đánh giá độc lập, có căn cứ, đối với việc sử dụng quyền khẩn cấp đã xảy ra — không phải tấm vé cho mọi hành động chưa được phê duyệt trước**. Hệ thống phải biết **ai dùng quyền gì, khi nào, vì sao, trong phạm vi nào**, bảo toàn chứng cứ và **thu hồi quyền ngay khi không còn cần** mà không chờ reviewer. Người duyệt có thể **ratify, yêu cầu khắc phục, không chấp thuận hoặc kết luận chưa đủ bằng chứng**; mọi ngoại lệ đều cần owner, hạn và kiểm soát bù. Khi liên kết với **Joiner–Mover–Leaver, IdP/SSO, SCIM, RBAC/ABAC, PAM/JIT, tài khoản dịch vụ và audit**, hậu kiểm giúp duy trì khả năng ứng cứu **mà không biến đặc quyền khẩn thành quyền tồn dư hoặc lỗ hổng trách nhiệm**.
