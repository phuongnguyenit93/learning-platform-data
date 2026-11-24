# Access review — Rà soát quyền truy cập và vòng đời quyền danh tính

## 1. Access review là gì?

**Access review** (rà soát quyền truy cập) là quy trình định kỳ hoặc theo sự kiện để xác nhận mỗi người dùng, service identity và workload chỉ còn những quyền cần thiết, đúng phạm vi và có người chịu trách nhiệm. Người rà soát xem ai đang có quyền gì, quyền đó được cấp vì mục đích nào, còn cần thiết không, có vượt quá vai trò hay không và cần giữ, giảm, thu hồi hoặc điều tra.

Ví dụ: một nhân viên chuyển từ nhóm vận hành sang nhóm phát triển. Hệ thống nhân sự đã cập nhật phòng ban nhưng quyền truy cập production, nhóm quản trị và OAuth grant cũ vẫn còn. Access review đối chiếu vai trò hiện tại với các quyền thực tế, yêu cầu owner xác nhận quyền còn cần, sau đó thu hồi các quyền không còn phù hợp và ghi lại bằng chứng.

Trong chương **Compliance** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, access review kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần hiểu access review là kiểm soát vòng đời quyền: xác định danh tính, xác minh người phê duyệt, rà soát entitlement, thực thi quyết định và giữ audit evidence. Việc xác thực thành công chỉ chứng minh một principal đã được xác minh theo một mức assurance; nó không tự chứng minh principal được phép truy cập mọi tài nguyên.

**Access review không chỉ là gửi danh sách quyền cho quản lý bấm Approve.** Review có giá trị khi dữ liệu đầy đủ, người phê duyệt hiểu phạm vi, quyết định có căn cứ, quyền bị thu hồi thực sự ở mọi hệ thống và bằng chứng có thể kiểm tra lại.

## 2. Vì sao access review quan trọng?

Quyền truy cập thay đổi theo thời gian. Nhân viên chuyển nhóm, nghỉ việc, làm dự án tạm thời; nhà cung cấp kết thúc hợp đồng; workload được thay thế; ứng dụng được tích hợp qua OAuth; certificate và API key có thể tồn tại lâu hơn mục đích ban đầu.

Nếu quyền không được rà soát:

- Người dùng giữ quyền cũ sau khi chuyển vai trò.
- Tài khoản đã nghỉ việc vẫn còn session, token hoặc key hoạt động.
- Nhóm đặc quyền có thành viên không còn nhiệm vụ phù hợp.
- Service account có scope rộng và không có owner.
- OAuth grant vẫn truy cập dữ liệu sau khi dự án kết thúc.
- Tài khoản khẩn cấp hoặc break-glass không được kiểm tra sau khi sử dụng.
- Credential dự phòng hoặc thiết bị cũ vẫn được tin cậy.
- Một người có thể vừa tạo vừa tự phê duyệt quyền của mình.

Access review giúp phát hiện quyền dư thừa và xác nhận trách nhiệm. Nó bổ sung cho provisioning, deprovisioning, authorization policy, MFA và monitoring; không thay thế các kiểm soát này.

## 3. Phân biệt identity, authentication, entitlement và authorization

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Identity** | Ai hoặc workload nào đang được đại diện? | Nhân viên, service principal, thiết bị hoặc đối tác. |
| **Authentication** | Bằng chứng nào xác minh principal? | Password + MFA, passkey, certificate hoặc workload credential. |
| **Entitlement** | Principal được cấp những quyền nào? | Nhóm, role, scope, policy assignment, API grant. |
| **Authorization** | Principal có được phép thực hiện hành động cụ thể trên resource này không? | Được đọc hồ sơ thuộc tenant A nhưng không được sửa. |
| **Access review** | Các entitlement hiện tại có còn đúng và được phê duyệt không? | Owner xác nhận hoặc thu hồi role production. |

Một access token hợp lệ không đảm bảo mọi quyền trong token vẫn phù hợp. Token có thể được phát hành trước khi role hoặc membership bị thu hồi. Resource server cần authorization theo policy hiện tại hoặc freshness contract phù hợp; access review giúp phát hiện và sửa quyền không còn cần thiết.

## 4. Phạm vi cần rà soát

Access review nên bao phủ cả người dùng và danh tính phi con người:

| Đối tượng | Quyền hoặc tài sản cần xem |
| --- | --- |
| Nhân viên | Role, group, application access, tenant membership, dữ liệu và môi trường. |
| Contractor/vendor | Phạm vi dự án, thời hạn hợp đồng, sponsor và quyền truy cập đối tác. |
| Privileged user | Admin role, production access, break-glass và quyền phê duyệt. |
| Service account | Database role, API scope, secret, certificate và quyền triển khai. |
| Workload identity | Cloud role, federation trust, audience, namespace và resource permission. |
| OAuth application | Consent, delegated scope, application permission và owner. |
| Device/credential | Passkey, security key, certificate, API key và binding còn active. |
| Group/nested group | Thành viên trực tiếp, membership kế thừa và quyền phát sinh. |
| External identity | IdP trust, partner account, federation mapping và guest access. |
| Emergency account | Người quản lý, điều kiện sử dụng, credential, alert và review sau sử dụng. |

Không chỉ xem danh sách user trong ứng dụng chính. Quyền có thể được kế thừa qua group, role mapping, cloud policy, CI/CD, database, API gateway hoặc federation. Cần biết nguồn nào là authoritative và cách quyền lan truyền tới từng resource.

## 5. Ranh giới tin cậy và quy trình access review

Một quy trình điển hình kết hợp nguồn nhân sự/danh tính, entitlement inventory, người sở hữu quyền, hệ thống thực thi và kho bằng chứng:

~~~mermaid
flowchart TD
    HR["HR / Vendor / Workload registry"]
    ID["Identity governance"]
    INV["Entitlement inventory"]
    CAM["Access review campaign"]
    OWNER["Manager / Resource owner"]
    DEC["Decision: keep / reduce / revoke"]
    EXEC["Provisioning / Authorization systems"]
    AUD[("Audit evidence")]
    HR --> ID --> INV --> CAM
    CAM --> OWNER --> DEC
    DEC --> EXEC
    DEC --> AUD
    EXEC --> AUD
    INV --> AUD
~~~

Identity governance tổng hợp principal và quan hệ vai trò. Entitlement inventory thu thập quyền từ ứng dụng, cloud, database và hệ thống federation. Campaign tạo danh sách cần review. Manager hoặc resource owner đưa ra quyết định. Provisioning/authorization system thực thi quyết định; audit store lưu trạng thái trước/sau và bằng chứng.

Các ranh giới phải rõ:

- Người dùng không tự khai quyền hiện có để thay thế inventory từ hệ thống.
- Người phê duyệt phải được xác thực và có thẩm quyền với resource.
- Quyết định phải gắn với đúng principal, entitlement, scope và thời hạn.
- Hệ thống thực thi phải xác nhận đã áp dụng thay đổi.
- Audit evidence không được sửa bởi chính actor đang bị review.
- Quyền đọc danh sách entitlement phải tuân theo tenant và data access policy.

## 6. Nguồn dữ liệu và entitlement inventory

Một review đáng tin cần inventory đầy đủ và có thể đối chiếu:

- Principal ID, loại identity, trạng thái account và tenant.
- Manager, sponsor, resource owner hoặc service owner.
- Role/group trực tiếp và membership kế thừa.
- Application, resource, environment và data classification.
- Scope, permission, action và điều kiện policy.
- Ngày cấp, nguồn cấp, ticket/approval reference và expiry.
- Credential hoặc authentication method liên quan ở mức reference.
- Last used, last authenticated và hoạt động gần nhất nếu có dữ liệu đáng tin.
- Session/token grant và trạng thái revoke nếu phạm vi review bao gồm.
- Owner của service account/workload và hệ thống tiêu thụ credential.

Inventory nên lưu nguồn và thời điểm đồng bộ để reviewer biết dữ liệu mới đến đâu. Nếu một connector không trả được quyền hoặc group membership, phải đánh dấu coverage gap thay vì hiển thị danh sách như thể đầy đủ.

### Quyền trực tiếp và quyền kế thừa

Ví dụ, user không được gán trực tiếp role Administrator nhưng là thành viên của group Operations-Admin, và group đó được lồng trong Production-Operators. Review phải tính quyền hiệu lực sau khi mở rộng membership và policy inheritance.

Không chỉ xóa membership trực tiếp nếu quyền vẫn được kế thừa từ group khác. Cần hiển thị đường dẫn entitlement để reviewer hiểu quyền đến từ đâu.

## 7. Các loại access review

| Loại review | Trigger | Ví dụ |
| --- | --- | --- |
| **Periodic review** | Theo lịch cố định | Rà soát quyền hàng quý hoặc nửa năm. |
| **Event-driven review** | Sự kiện vòng đời | Chuyển nhóm, nghỉ việc, đổi sponsor hoặc kết thúc hợp đồng. |
| **Privileged access review** | Quyền có impact cao | Rà soát admin, production, security console. |
| **Application review** | Theo ứng dụng/resource | Owner xác nhận user và scope đang truy cập ứng dụng. |
| **Role/group review** | Theo entitlement | Xác nhận membership và nested group. |
| **Third-party review** | Theo đối tác/vendor | Kiểm tra guest access và quyền hỗ trợ. |
| **Service identity review** | Theo workload | Xác nhận owner, scope, key, certificate và dependency. |
| **Emergency access review** | Sau khi break-glass được dùng | Kiểm tra actor, thời gian, lý do và hành động. |

Tần suất phải dựa trên rủi ro và yêu cầu tổ chức/khung áp dụng. Quyền quản trị production có thể cần review thường xuyên hơn quyền đọc tài liệu công khai. Không áp một chu kỳ chung mà bỏ qua sensitivity, exposure và tốc độ thay đổi.

## 8. Ai nên phê duyệt?

Người phê duyệt phải hiểu mục đích quyền và chịu trách nhiệm cho resource:

- **Line manager:** xác nhận nhân viên còn thuộc nhóm và cần quyền theo công việc.
- **Resource owner:** xác nhận quyền truy cập vào hệ thống/dữ liệu họ quản lý.
- **Application owner:** xác nhận role và scope của ứng dụng.
- **Data owner:** xác nhận quyền với dữ liệu nhạy cảm.
- **Service/workload owner:** xác nhận service identity còn cần quyền và có consumer hợp lệ.
- **Security/IAM:** kiểm tra policy, đặc quyền, ngoại lệ và xung đột nhiệm vụ.

Manager có thể không hiểu scope kỹ thuật của OAuth grant hoặc quyền database. Với entitlement nhạy cảm, nên cần cả manager và resource owner hoặc approval chuyên môn. Không để một người tự phê duyệt quyền của chính mình nếu policy yêu cầu independent review.

### Delegation

Nếu người review vắng mặt, có thể ủy quyền cho người khác theo thời hạn, phạm vi và quyền rõ ràng. Delegation phải được ghi audit; người được ủy quyền không được mở rộng phạm vi review hoặc tự ủy quyền tiếp nếu policy không cho phép.

## 9. Quyết định review: keep, reduce, revoke và investigate

Mỗi entitlement cần một quyết định có nghĩa rõ:

| Quyết định | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Keep** | Quyền còn cần và đúng scope. | Giữ quyền, ghi lý do/owner và thời điểm review. |
| **Reduce** | Chỉ một phần quyền còn cần. | Giảm role, scope, resource hoặc thời hạn. |
| **Revoke** | Quyền không còn cần hoặc không được phê duyệt. | Thu hồi entitlement và xác minh hiệu lực. |
| **Time-bound** | Quyền chỉ cần tạm thời. | Gắn expiry và owner; tự động thu hồi khi hết hạn. |
| **Investigate** | Dữ liệu thiếu, bất thường hoặc có xung đột. | Tạm giữ hoặc hạn chế theo risk; mở ticket xác minh. |
| **Exception** | Có lý do nghiệp vụ đặc biệt. | Ghi rationale, approver, compensating control và ngày hết hạn. |

Không coi im lặng là approval. Nếu reviewer không phản hồi trước deadline, áp dụng escalation hoặc default action đã được policy phê duyệt. Với quyền đặc quyền, có thể tạm suspend hoặc yêu cầu revalidation thay vì tự động giữ.

## 10. Least privilege và quyền có thời hạn

Access review là cơ hội áp dụng **least privilege**:

- Chỉ cấp action cần thiết, không cấp role rộng hơn chỉ để tiện.
- Giới hạn resource, tenant, environment và data scope.
- Dùng role chuyên biệt thay vì group admin tổng quát.
- Quyền đặc quyền chỉ active trong thời gian cần thiết.
- Tách quyền đọc, ghi, deploy, approve và quản trị.
- Dùng just-in-time access khi phù hợp.
- Gắn owner và expiry cho entitlement tạm thời.

Quyền có thời hạn vẫn cần review nếu được gia hạn nhiều lần hoặc không có owner. Một expiry tự động không thay thế việc xác nhận lý do và scope trước khi cấp lại.

## 11. Access review cho privileged access

Quyền đặc quyền có thể gây impact lớn nên cần quy trình riêng:

- Liệt kê admin role, cloud control plane, production shell và database superuser.
- Kiểm tra quyền trực tiếp và quyền kế thừa.
- Xác nhận người sở hữu và nhiệm vụ cần quyền.
- Kiểm tra MFA/phishing-resistant authentication và step-up policy.
- Xem thời điểm sử dụng gần nhất, nhưng không dùng “chưa dùng” làm tiêu chí duy nhất.
- Xác minh break-glass account, custody và alert.
- Kiểm tra quyền tạo user, cấp role, thay đổi policy và xóa audit.
- Yêu cầu independent approval cho thay đổi rủi ro cao.

Một admin account không hoạt động có thể vẫn cần giữ cho tình huống dự phòng; khi đó phải có kiểm soát bù như credential custody, disabled-by-default, alert và test định kỳ. Không xóa tài khoản khẩn cấp mà chưa có phương án thay thế đã kiểm chứng.

## 12. Access review cho service account và workload identity

Service identity thường bị bỏ sót vì không có manager như nhân viên. Mỗi identity cần:

- Owner chịu trách nhiệm và nhóm hỗ trợ.
- Purpose/business function cụ thể.
- Workload, namespace, pipeline hoặc application tiêu thụ.
- Role, scope, audience và resource được phép.
- Authentication method: certificate, federated identity, API key hoặc managed identity.
- Credential expiry, rotation và revocation owner.
- Last used và dependency inventory.
- Cơ chế thay thế/retire khi workload kết thúc.

Không dùng một service account chung cho nhiều ứng dụng hoặc nhiều môi trường nếu không cần. Shared identity làm khó attribution và tăng blast radius. Nếu service identity không có owner hoặc không xác định được consumer, đánh dấu investigate và hạn chế theo policy.

## 13. OAuth grant, application permission và federation access

Access review cần xem quyền được cấp qua giao thức và liên kết danh tính:

- Delegated OAuth scopes được người dùng hoặc admin consent.
- Application permissions chạy dưới danh tính ứng dụng.
- Refresh token/grant còn active.
- OIDC/SAML federation trust và claim mapping.
- External IdP, guest account và partner access.
- Service principal có quyền truy cập dữ liệu tenant.

Kiểm tra scope theo nguyên tắc tối thiểu và xác nhận ứng dụng vẫn còn owner. Một ứng dụng không còn sử dụng nhưng vẫn giữ grant có thể tiếp tục truy cập dữ liệu. Khi revoke consent hoặc grant, cần xác minh token đã phát hành và refresh token family được xử lý theo semantics của hệ thống; chỉ xóa application assignment có thể chưa đủ.

## 14. Credential inventory liên quan đến access review

Review quyền không phải lúc nào cũng cần xem secret, nhưng cần biết credential nào có thể mở đường truy cập:

- Passkey/security key đang active và thuộc principal nào.
- TOTP/push authenticator và thiết bị binding.
- Certificate, issuer, serial, key usage và expiry.
- API key/client secret reference, scope và consumer.
- Recovery method và kênh đã xác minh.
- Session/token family liên quan đến quyền đang review.

Không hiển thị password, OTP, recovery code, private key hoặc token bản rõ trong review interface. Reviewer cần thấy loại credential, trạng thái, owner, thời điểm tạo/sử dụng và thao tác thu hồi ở mức được phép.

Nếu credential không còn thuộc quyền kiểm soát của người dùng hoặc workload, xử lý như một vấn đề credential lifecycle: suspend/revoke, re-enroll hoặc rotate. Không chỉ xóa role trong ứng dụng mà bỏ qua token, certificate hoặc key có quyền tương đương ở downstream.

## 15. Joiner, mover, leaver và access review

Access review nên kết nối với quy trình vòng đời nhân sự:

| Sự kiện | Kiểm soát cần thực hiện |
| --- | --- |
| **Joiner** | Tạo identity, xác minh, cấp quyền tối thiểu theo role và owner. |
| **Mover** | Đánh giá quyền cũ và mới; thu hồi entitlement không còn phù hợp khi chuyển nhóm. |
| **Leaver** | Disable account, revoke session/token, thu hồi credential và external access theo thời điểm hiệu lực. |
| **Contract end** | Kiểm tra sponsor, tài khoản đối tác, VPN, guest và service access liên quan. |
| **Role change** | Cập nhật group/role, re-evaluate policy và review quyền đặc quyền. |

Không chỉ dựa vào lịch review định kỳ. Khi HR hoặc vendor registry phát event mover/leaver, hệ thống cần kích hoạt workflow kịp thời. Nếu nguồn nhân sự không sẵn sàng, cần quy trình manual có owner và audit, tránh để quyền cũ tồn tại vô thời hạn.

## 16. Segregation of duties và toxic combination

Một người có thể có nhiều quyền riêng lẻ hợp lệ nhưng khi kết hợp lại tạo rủi ro:

- Người tạo nhà cung cấp đồng thời phê duyệt thanh toán.
- Người triển khai production đồng thời phê duyệt thay đổi của chính mình.
- Người quản trị IAM đồng thời xóa audit trail.
- Người yêu cầu recovery đồng thời là approver helpdesk.
- Người tạo credential đồng thời có quyền cấp role đặc quyền cho nó.

**Segregation of duties (SoD)** tách các nhiệm vụ nhạy cảm giữa các actor. Access review cần kiểm tra toxic combinations theo policy và context, không chỉ đếm số role.

Khi không thể tách hoàn toàn, có thể dùng compensating controls: independent approval, dual control, time-bound privilege, transaction limit, monitoring và review sau hành động. Ngoại lệ phải có owner, rationale và expiry.

## 17. Tần suất, campaign và phạm vi review

Một campaign nên xác định:

- Mục tiêu và lý do review.
- Population: principal, application, tenant, resource và entitlement.
- Risk tier và tần suất.
- Người phê duyệt và người hỗ trợ.
- Ngày bắt đầu, deadline và escalation.
- Quy tắc xử lý non-response.
- Hành động được phép và approval bổ sung.
- Bằng chứng cần lưu.
- Tiêu chí hoàn tất và metrics.

Có thể chia campaign theo application owner, data sensitivity, privileged role hoặc business unit. Tránh gửi hàng nghìn entitlement không có nhóm hoặc ngữ cảnh; reviewer khó hiểu và có xu hướng approve hàng loạt.

### Risk-based cadence

Quyền quản trị, dữ liệu nhạy cảm và external access thường cần review thường xuyên hơn quyền ít rủi ro. Tần suất phải phù hợp yêu cầu nội bộ, hợp đồng và khung tuân thủ áp dụng. Không tự tuyên bố một chu kỳ cụ thể là bắt buộc cho mọi tổ chức.

## 18. Workflow và bằng chứng phê duyệt

Một entitlement nên đi qua các trạng thái có thể theo dõi:

1. Inventory snapshot được tạo và gắn thời điểm/source version.
2. Campaign xác định reviewer và deadline.
3. Reviewer xác thực, kiểm tra entitlement và đưa quyết định.
4. Quyết định được lưu cùng actor, thời điểm, rationale và policy version.
5. Approval bổ sung được thực hiện nếu quyền nhạy cảm hoặc có SoD conflict.
6. Provisioning system thực thi keep/reduce/revoke/expiry.
7. Hệ thống xác minh trạng thái thực tế đã thay đổi.
8. Exception hoặc lỗi được đưa vào queue xử lý.
9. Audit evidence được lưu và campaign được đóng khi tiêu chí hoàn tất đạt.

Không đánh dấu campaign complete chỉ vì reviewer đã bấm Submit. Phải xác nhận các revoke/reduce đã được áp dụng, các lỗi có owner và ngoại lệ có expiry.

## 19. Automation và continuous access review

Automation có thể:

- Đồng bộ entitlement inventory từ IdP, cloud, SaaS, database và code platform.
- Tính quyền hiệu lực từ group/role inheritance.
- Phát hiện account không có owner, stale credential hoặc entitlement không dùng.
- Kích hoạt review khi mover/leaver, đổi role hoặc thay đổi risk.
- Tạo task cho manager/resource owner.
- Thực thi quyết định qua provisioning API.
- Kiểm tra lại trạng thái sau khi thực thi.
- Tạo audit evidence và metrics.

Automation không nên tự động revoke chỉ dựa trên last-used nếu chưa hiểu workload và dependency. Một service account chỉ chạy theo quý có thể là hợp lệ. Dùng owner, purpose, schedule, dependency graph và policy để phân loại.

Continuous access evaluation có thể phát hiện thay đổi giữa các campaign, nhưng vẫn cần review có trách nhiệm cho những quyền mà policy yêu cầu con người xác nhận.

## 20. Xử lý ngoại lệ và quyền khẩn cấp

Ngoại lệ thường xuất hiện do migration, incident response, vendor support hoặc nhiệm vụ đặc biệt:

- Ghi lý do nghiệp vụ và resource cụ thể.
- Chỉ định sponsor/owner và approver độc lập.
- Giới hạn scope, tenant, environment và thời hạn.
- Áp dụng MFA/step-up và monitoring phù hợp.
- Có ngày hết hạn và quy trình gia hạn.
- Review sau khi sử dụng hoặc sau incident.
- Tự động thu hồi khi hết hạn nếu không được gia hạn hợp lệ.

Break-glass access cần credential custody riêng, cảnh báo khi sử dụng và review sau sự kiện. Không dùng break-glass như tài khoản admin thông thường hoặc bỏ qua audit vì đây là quyền khẩn cấp.

## 21. Metrics đánh giá chất lượng access review

Đo chất lượng và hiệu quả, không chỉ tỷ lệ hoàn thành:

| Metric | Ý nghĩa |
| --- | --- |
| Review completion rate | Tỷ lệ entitlement được quyết định trước deadline. |
| Revocation completion time | Thời gian từ quyết định tới khi quyền thực sự bị thu hồi. |
| Overdue entitlement count | Số quyền chưa được review đúng hạn. |
| Orphan identity count | Số identity/service account không có owner. |
| Stale entitlement count | Quyền không còn cần hoặc không có activity phù hợp. |
| Exception age | Thời gian ngoại lệ tồn tại và số lần gia hạn. |
| Privileged access coverage | Tỷ lệ quyền đặc quyền nằm trong campaign. |
| Evidence completeness | Tỷ lệ quyết định có actor, rationale, timestamp và execution proof. |
| Reversal/rework rate | Quyết định phải sửa do inventory hoặc context sai. |
| Toxic combination findings | Xung đột SoD được phát hiện và xử lý. |

Không tối ưu completion rate bằng cách tự động approve mọi quyền hoặc đóng campaign khi chưa thực thi revoke. Metrics cần phản ánh kết quả kiểm soát và chất lượng dữ liệu.

## 22. Rủi ro và lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Inventory thiếu group kế thừa | Quyền hiệu lực bị bỏ sót. | Tính entitlement theo toàn bộ inheritance path. |
| Reviewer không hiểu scope | Approve theo thói quen. | Cung cấp purpose, resource, sensitivity và last-use context. |
| Im lặng được coi là approval | Quyền dư thừa tiếp tục tồn tại. | Escalation/default action theo policy. |
| Chỉ review nhân viên | Bỏ sót service account, OAuth grant và vendor. | Mở rộng population theo identity type. |
| Không xác minh revoke | Dashboard nói đã thu hồi nhưng downstream vẫn chấp nhận. | Kiểm tra effective state tại verifier/resource. |
| Chỉ dựa vào last-used | Thu hồi nhầm workload theo lịch thưa. | Kết hợp owner, purpose và dependency. |
| Self-approval | Người cấp quyền tự hợp thức hóa quyền. | SoD và independent approval. |
| Exception không expiry | Quyền tạm thời trở thành vĩnh viễn. | Owner, deadline và auto-expiry. |
| Chỉ xóa role, quên token | Token cũ vẫn mang scope hoặc session còn hiệu lực. | Revoke grant/family/session theo semantics. |
| Inventory stale | Review dựa trên dữ liệu cũ. | Gắn timestamp, source version và coverage gap. |
| Bulk revoke không kiểm soát | Gián đoạn production hoặc recovery. | Change plan, dependency validation và rollback an toàn. |

## 23. Mã giả: campaign access review

Mã giả minh họa một workflow có quyết định, thực thi và xác minh:

~~~text
runAccessReviewCampaign(scope, reviewer):
    inventory = collectAuthoritativeEntitlements(scope)
    require inventory.coverageIsKnown
    snapshot = createVersionedInventorySnapshot(inventory)

    tasks = buildReviewTasks(
        snapshot,
        reviewer,
        includeInheritedPermissions = true
    )

    for task in tasks:
        decision = collectAuthenticatedDecision(
            reviewer,
            task.entitlement,
            allowed = ["keep", "reduce", "revoke", "investigate", "exception"]
        )
        require reviewerAuthorizedFor(task.resourceOwner)
        require rationalePresentWhenRequired(decision)
        require independentApprovalForSensitiveChange(decision)

        recordDecisionWithAudit(
            campaign = scope.campaignId,
            snapshotVersion = snapshot.version,
            task = task,
            decision = decision,
            actor = reviewer
        )

        if decision.action in ["reduce", "revoke"]:
            result = executeEntitlementChange(decision)
            verifyEffectiveAccessChanged(result)

        if decision.action == "exception":
            require decision.owner and decision.expiresAt
            scheduleExpiryAndFollowUp(decision)

    reconcileAllExecutionResults(tasks)
    reportIncompleteTasksAndCoverageGaps()
    closeCampaignOnlyWhenCompletionCriteriaMet()
~~~

Trong triển khai thật:

- Inventory phải lấy từ connector/API có xác thực và gắn source timestamp.
- Quyết định của reviewer phải gắn principal, resource, entitlement và snapshot version.
- Approval không được replay hoặc sửa bởi actor không có quyền.
- Provisioning có thể thất bại một phần; cần retry idempotent và reconciliation.
- Kiểm tra effective permission ở resource server, không chỉ trạng thái trong governance tool.
- Ngoại lệ phải có expiry và owner; không tự gia hạn vô hạn.

## 24. Tình huống thực tế: nhân viên chuyển nhóm nhưng giữ quyền production

Một nhân viên chuyển từ vận hành sang phát triển sản phẩm. HR cập nhật bộ phận, nhưng đồng bộ group sang cloud chậm. Nhân viên vẫn thuộc nhóm Production-Admin và có OAuth grant tới hệ thống dữ liệu khách hàng.

### Phân tích

1. Mover event cho biết role mới không còn cần quyền production.
2. Inventory cho thấy quyền admin được kế thừa qua nested group.
3. OAuth grant vẫn active dù dự án cũ đã kết thúc.
4. Một refresh token family có thể tiếp tục cấp access token trong thời gian quyền chưa được đồng bộ.
5. Review owner phải xác nhận quyền nào còn cần cho nhiệm vụ mới.

### Xử lý

1. Thu hồi membership cũ và kiểm tra quyền hiệu lực ở cloud/resource server.
2. Revoke grant hoặc scope không còn cần; xử lý token/session liên quan theo policy.
3. Cấp role mới theo least privilege và thời hạn nếu là quyền tạm.
4. Kiểm tra các key/certificate/workload access có liên quan tới nhiệm vụ cũ.
5. Ghi audit actor, approver, entitlement trước/sau và kết quả thực thi.
6. Theo dõi propagation và xác nhận quyền production cũ bị từ chối.

Nếu nhân viên vẫn cần quyền hỗ trợ production trong giai đoạn chuyển tiếp, tạo exception time-bound với owner và independent approval thay vì giữ nguyên quyền cũ không thời hạn.

## 25. Kiểm thử access review

| Tình huống | Kết quả mong đợi |
| --- | --- |
| User có role trực tiếp | Inventory hiển thị entitlement và nguồn cấp. |
| User có nested group | Quyền kế thừa được tính và có đường dẫn giải thích. |
| User chuyển nhóm | Mover event kích hoạt review/thu hồi quyền cũ theo policy. |
| Nhân viên nghỉ việc | Account, session, token và credential được xử lý theo leaver workflow. |
| Service account không có owner | Được đánh dấu orphan và đưa vào xử lý. |
| OAuth grant không còn owner | Scope/application permission được review và revoke khi phù hợp. |
| Privileged role | Có reviewer chuyên môn, independent approval và evidence đầy đủ. |
| Reviewer không phản hồi | Escalation/default policy; không tự coi là approved. |
| Reviewer không có quyền | Hệ thống từ chối quyết định. |
| Self-approval | Bị chặn theo SoD policy. |
| Exception thiếu expiry | Không được phê duyệt hoặc không thể đóng campaign. |
| Revoke API timeout | Task giữ trạng thái pending/failed; không báo completed. |
| Provisioning thành công nhưng resource stale | Reconciliation tiếp tục cho tới khi verifier từ chối quyền cũ. |
| Token còn scope sau revoke | Token/grant/session được xử lý theo revocation semantics. |
| Inventory connector mất dữ liệu | Campaign báo coverage gap; không hiển thị complete. |
| Event duplicate | Workflow idempotent, không tạo quyết định/thao tác lặp. |
| Snapshot thay đổi giữa review | Version conflict được phát hiện và task cần re-evaluate. |
| Emergency access vừa được dùng | Post-use review và alert được tạo. |

### Kiểm thử vận hành

- Đo inventory freshness và connector coverage.
- Kiểm tra thời gian từ decision tới effective revocation.
- Diễn tập review quyền đặc quyền và vendor access.
- Kiểm tra evidence export, retention và access control.
- Kiểm thử nested group, role inheritance và cross-tenant boundary.
- Kiểm tra expiry job, retry và reconciliation khi provisioning lỗi.

## 26. Checklist thiết kế access review

- [ ] Xác định population gồm employee, contractor, guest, service account, workload và application.
- [ ] Inventory bao gồm quyền trực tiếp, kế thừa, OAuth grant, cloud role và downstream permission.
- [ ] Gắn owner, purpose, source, timestamp, scope và expiry cho entitlement.
- [ ] Hiển thị nguồn gốc quyền để reviewer hiểu vì sao principal có access.
- [ ] Chọn reviewer có thẩm quyền và chuyên môn phù hợp resource.
- [ ] Tách actor, requester, approver và executor cho quyền nhạy cảm.
- [ ] Có periodic và event-driven review cho joiner/mover/leaver.
- [ ] Phân loại risk và đặt cadence phù hợp.
- [ ] Quyết định keep/reduce/revoke/investigate/exception có rationale.
- [ ] Không coi non-response là approval nếu policy chưa quy định.
- [ ] Quyền tạm có owner, expiry và auto-revocation.
- [ ] Kiểm tra SoD/toxic combination và independent approval.
- [ ] Rà soát service identity, API key, certificate, passkey và OAuth grant theo reference.
- [ ] Không hiển thị secret bản rõ trong review interface hoặc evidence.
- [ ] Thực thi quyết định qua provisioning/authorization system và xác minh effective state.
- [ ] Xử lý session, refresh token và cache khi quyền bị thu hồi.
- [ ] Lưu inventory snapshot, decision, approver, execution result và audit evidence.
- [ ] Có reconciliation, escalation, exception expiry và metrics chất lượng.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Authentication thành công có chứng minh người dùng được phép truy cập resource không?

**Gợi ý:** Không. Authentication xác minh principal; authorization quyết định quyền trên resource/action. Access review kiểm tra entitlement còn phù hợp.

**Câu 2.** Vì sao access review phải tính nested group và quyền kế thừa?

**Gợi ý:** User có thể nhận quyền hiệu lực qua nhiều lớp group hoặc policy dù không được gán role trực tiếp.

**Câu 3.** Vì sao service account cần owner và purpose?

**Gợi ý:** Không có manager như con người; owner/purpose giúp xác định workload còn cần quyền và ai chịu trách nhiệm thu hồi.

**Câu 4.** Reviewer không phản hồi có nên được coi là đã phê duyệt?

**Gợi ý:** Không mặc định. Cần escalation hoặc default action được policy phê duyệt, đặc biệt với quyền đặc quyền.

**Câu 5.** Thu hồi role có đảm bảo token cũ mất quyền ngay không?

**Gợi ý:** Không nhất thiết. Cần xử lý grant, token family, session, cache và authorization state ở resource server.

**Câu 6.** Khi nào cần independent approval?

**Gợi ý:** Với quyền đặc quyền, thay đổi rủi ro cao hoặc tình huống có xung đột nhiệm vụ/self-approval.

**Câu 7.** Vì sao campaign chỉ được đóng sau khi xác minh thực thi?

**Gợi ý:** Quyết định review có thể không được provisioning áp dụng hoặc downstream còn stale; phải kiểm tra effective access.

## 28. Ghi nhớ

**Access review xác nhận quyền hiện tại của người dùng và workload còn cần thiết, đúng scope và có người chịu trách nhiệm hay không.** Quy trình cần inventory đầy đủ cả quyền trực tiếp, quyền kế thừa, OAuth grant, cloud role, credential và service identity; reviewer có thẩm quyền; quyết định keep/reduce/revoke/exception có rationale; và kiểm tra quyền thực tế sau khi thực thi. Review phải kết nối joiner/mover/leaver, least privilege, privileged access, segregation of duties, session/token revocation và audit evidence. Không coi im lặng là approval, không chỉ xóa role ở một hệ thống rồi giả định token/downstream đã mất quyền, và không đóng campaign trước khi coverage cùng kết quả thực thi được xác minh.
