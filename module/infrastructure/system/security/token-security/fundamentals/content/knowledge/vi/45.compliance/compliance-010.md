# Separation of duties: Phân tách nhiệm vụ trong quản trị token

## 1. Mục tiêu và phạm vi

Trong hệ thống OAuth 2.0/OIDC, một token có thể mở quyền truy cập dữ liệu, thực hiện giao dịch hoặc cho phép service gọi hệ thống nội bộ. Nếu một cá nhân hoặc một tài khoản có thể tự tạo client, tự cấp scope đặc quyền, tự phát hành token, tự thay đổi khóa ký và tự xóa dấu vết audit, tổ chức khó phát hiện hoặc ngăn chặn lạm dụng quyền. **Separation of duties (SoD)** là nguyên tắc phân chia các bước nhạy cảm giữa những vai trò hoặc danh tính độc lập, để một chủ thể không thể đơn phương hoàn thành toàn bộ hành động có rủi ro cao.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, SoD áp dụng xuyên suốt vòng đời token: đăng ký OAuth client, cấp scope/audience, phê duyệt quyền, phát hành và exchange token, quản lý signing key, cấu hình introspection, thu hồi token, xử lý sự cố và truy cập audit. Mục tiêu là giảm khả năng lạm dụng đặc quyền, sai sót không được phát hiện và sửa đổi trái phép đối với ranh giới tin cậy.

Sau bài học, người học có thể:

- Giải thích SoD, least privilege, dual control và maker-checker.
- Xác định các nhiệm vụ xung đột trong quản trị OAuth client, scope, audience và signing key.
- Thiết kế vai trò, quyền và quy trình phê duyệt độc lập cho hành động nhạy cảm.
- Phân biệt danh tính con người, service account và workload identity.
- Áp dụng SoD cho phát hành token, token exchange, thu hồi và audit.
- Xử lý trường hợp khẩn cấp mà vẫn giữ được kiểm soát và bằng chứng.

## 2. Separation of duties là gì?

SoD chia một quy trình nhạy cảm thành các nhiệm vụ có trách nhiệm khác nhau. Người khởi tạo yêu cầu (maker/requester) không đồng thời là người phê duyệt (checker/approver); người triển khai thay đổi không có quyền tự xóa bằng chứng hoặc tự xác nhận thay đổi của mình. Tùy rủi ro, có thể cần hai người độc lập, hai vai trò độc lập hoặc một bước phê duyệt tự động dựa trên policy do nhóm khác quản lý.

Ví dụ, một kỹ sư cần thêm scope quản trị cho OAuth client:

1. Kỹ sư tạo yêu cầu, nêu business purpose, audience, scope, thời hạn và owner.
2. Chủ sở hữu API xác nhận scope thực sự cần thiết.
3. Security hoặc IAM approver kiểm tra rủi ro, least privilege và môi trường.
4. Pipeline/administrator được phép triển khai thay đổi sau khi đủ phê duyệt.
5. Hệ thống ghi audit event về requester, approver, policy version, thay đổi trước/sau và thời điểm áp dụng.

Người yêu cầu không tự phê duyệt yêu cầu của mình. Người triển khai cũng không được sửa lịch sử audit để che giấu thay đổi. Với hành động rủi ro thấp, quy trình có thể tự động nếu policy và quyền sở hữu được kiểm soát độc lập.

### 2.1 SoD, least privilege và dual control

| Nguyên tắc | Câu hỏi chính | Cách áp dụng |
| --- | --- | --- |
| Least privilege | Chủ thể cần quyền tối thiểu nào để làm nhiệm vụ? | Chỉ cấp scope, audience, role và thời hạn cần thiết |
| Separation of duties | Có nhiệm vụ xung đột nào do cùng một chủ thể kiểm soát? | Tách requester, approver, deployer, auditor |
| Dual control / two-person rule | Hành động nào cần hai người độc lập cùng xác nhận? | Phê duyệt thay đổi khóa ký hoặc cấp quyền đặc quyền |
| Maker-checker | Người tạo yêu cầu có tự kiểm tra/phê duyệt được không? | Hệ thống chặn self-approval |
| Privileged access management | Quyền đặc quyền được cấp và giám sát ra sao? | Just-in-time access, session recording, time-bound elevation |

Các nguyên tắc hỗ trợ lẫn nhau nhưng không đồng nghĩa. Chia vai trò mà mỗi vai trò vẫn có quyền quá rộng không đạt least privilege. Cấp quyền tối thiểu nhưng cho một người tự tạo, tự duyệt và tự triển khai một thay đổi đặc quyền vẫn thiếu SoD. Dual control là một biện pháp cụ thể trong những trường hợp cần hai xác nhận.

## 3. Xác định nhiệm vụ xung đột trong vòng đời token

Để thiết kế SoD, trước tiên liệt kê tài sản, hành động nhạy cảm và khả năng một chủ thể tự thực hiện toàn bộ chuỗi. Các nhiệm vụ có rủi ro cao thường gồm:

- Tạo hoặc sửa OAuth client, redirect URI, client authentication method và credential.
- Cấp scope đặc quyền, audience/resource mới hoặc quyền impersonation/delegation.
- Thay đổi policy token exchange, token lifetime, refresh-token rotation và revocation.
- Tạo, kích hoạt, xoay hoặc vô hiệu hóa JWT signing key.
- Thay đổi introspection endpoint, issuer trust, JWKS configuration hoặc truststore.
- Cấp quyền đọc/export audit hoặc thay đổi retention và integrity control.
- Thực hiện break-glass, thu hồi hàng loạt token hoặc vô hiệu hóa client production.

Ví dụ ma trận xung đột:

| Nhiệm vụ A | Nhiệm vụ B | Rủi ro nếu cùng một chủ thể kiểm soát |
| --- | --- | --- |
| Đăng ký OAuth client | Phê duyệt client của chính mình | Tạo client ngoài quy trình |
| Yêu cầu scope/audience | Phê duyệt scope/audience | Tự cấp quyền vượt nhu cầu |
| Thay đổi token exchange policy | Tự xác nhận policy đó | Cho phép exchange sang resource đặc quyền |
| Tạo signing key | Phê duyệt/đưa key vào trust | Phát hành token giả hoặc không được kiểm soát |
| Triển khai cấu hình IAM | Quản trị audit trail | Che giấu thay đổi hoặc xóa bằng chứng |
| Thu hồi token/client | Phê duyệt ngoại lệ giữ token | Tự vô hiệu hóa hoặc giữ quyền không phù hợp |
| Quản trị production | Kiểm tra độc lập quyền production | Tự mở rộng quyền mà không có kiểm tra |

Không phải mọi cặp nhiệm vụ đều phải tách tuyệt đối. Đánh giá dựa trên mức độ đặc quyền, khả năng gây thiệt hại, tác động đến dữ liệu, khả năng khôi phục, quy mô hệ thống và yêu cầu pháp lý/hợp đồng. Kết quả nên được ghi thành ma trận SoD và policy kiểm tra xung đột.

## 4. Vai trò và trách nhiệm tham khảo

Một mô hình IAM có thể chia vai trò như sau. Tên vai trò chỉ là ví dụ; tổ chức cần ánh xạ vào cấu trúc thực tế:

| Vai trò | Trách nhiệm | Quyền nên có | Quyền cần tránh |
| --- | --- | --- | --- |
| Application owner | Xác nhận nhu cầu nghiệp vụ, owner và phạm vi client | Đọc cấu hình client thuộc ứng dụng; yêu cầu thay đổi | Tự phê duyệt scope đặc quyền |
| OAuth client requester | Tạo yêu cầu đăng ký/cập nhật client | Submit request, xem trạng thái của yêu cầu | Approve hoặc deploy yêu cầu của mình |
| API/resource owner | Xác nhận audience và scope API | Phê duyệt quyền thuộc resource của mình | Quản trị signing key toàn hệ thống |
| Security/IAM approver | Đánh giá rủi ro, policy và SoD | Approve/reject theo phạm vi được giao | Tự triển khai thay đổi đã duyệt nếu không có kiểm soát độc lập |
| IAM operator | Thực thi cấu hình theo change đã duyệt | Deploy đúng artifact/request được phê duyệt | Tự sửa approval hoặc xóa audit |
| Key custodian | Quản lý quy trình key ceremony, HSM/KMS và rotation | Thực hiện thao tác key theo policy | Tự phê duyệt toàn bộ thay đổi trust |
| Auditor/compliance reviewer | Kiểm tra bằng chứng và quyền truy cập | Read-only audit, truy vấn lịch sử | Sửa cấu hình hoặc xóa audit record |
| Incident commander | Điều phối ứng phó sự cố | Kích hoạt quy trình khẩn cấp có giới hạn | Tự bỏ qua mọi kiểm soát mà không ghi lý do |

Một người có thể đảm nhiệm nhiều vai trò trong tổ chức nhỏ, nhưng hệ thống phải phát hiện và kiểm soát các xung đột có rủi ro cao. Khi không đủ nhân sự độc lập, có thể dùng phê duyệt từ người quản lý khác, kiểm soát tự động, kiểm tra hậu kiểm độc lập hoặc giới hạn thời gian và phạm vi của quyền.

### 4.1 Human identity và workload identity

Không trộn danh tính con người với danh tính máy:

- **Human identity** là tài khoản của nhân viên/administrator, thường được xác thực qua SSO, MFA và chính sách truy cập đặc quyền.
- **Workload identity** là danh tính của ứng dụng, pod, service hoặc job; dùng để xác thực service-to-service và lấy token.
- **OAuth client identity** là client đã đăng ký với authorization server; client ID xác định ứng dụng, không chứng minh cá nhân nào đã phê duyệt thay đổi.

Một service account không nên được dùng chung như tài khoản quản trị của nhiều người. Credential của workload nên được cấp tự động theo môi trường, giới hạn audience/scope và xoay theo chính sách. Phê duyệt thay đổi quyền của workload cần gắn với người yêu cầu, approver và pipeline đã xác thực; không chỉ ghi client ID.

## 5. SoD trong đăng ký client và cấp scope

### 5.1 Quy trình maker-checker

Yêu cầu thay đổi OAuth client nên chứa đủ thông tin để approver đánh giá:

- Client ID/owner và môi trường.
- Loại client và phương thức xác thực client.
- Redirect URI hoặc endpoint callback khi áp dụng.
- Audience/resource cần truy cập.
- Requested scopes và lý do nghiệp vụ cho từng scope.
- Access token/refresh token lifetime và yêu cầu rotation.
- Có dùng impersonation, delegation hoặc token exchange hay không.
- Ngày bắt đầu, ngày hết hạn hoặc thời điểm review lại.

Quy trình:

~~~mermaid
flowchart TD
    A[Requester tạo yêu cầu client/scope] --> B[Kiểm tra schema và policy tự động]
    B --> C{Có xung đột SoD?}
    C -->|Có| X[Từ chối hoặc chuyển approver độc lập]
    C -->|Không| D[Resource owner đánh giá audience/scope]
    D --> E[Security/IAM approver đánh giá rủi ro]
    E --> F{Đủ phê duyệt?}
    F -->|Không| R[Reject và ghi lý do]
    F -->|Có| G[Pipeline triển khai artifact đã duyệt]
    G --> H[Readback và kiểm tra cấu hình thực tế]
    H --> I[Audit event và thông báo owner]
~~~

Pipeline cần kiểm tra requester và approver không phải cùng một identity khi policy yêu cầu hai người. Không chấp nhận approval chỉ dựa trên tên hiển thị hoặc email tự khai trong request body; phải lấy identity từ phiên xác thực đáng tin cậy. Approval cần ràng buộc với đúng nội dung được duyệt, ví dụ hash/version của change artifact, để tránh thay đổi scope sau khi đã được phê duyệt.

### 5.2 Scope và audience theo least privilege

Một client chỉ nên nhận scope phục vụ đúng use case. Ví dụ:

| Client | Audience | Scope phù hợp |
| --- | --- | --- |
| orders-web | orders-api | orders.read, orders.create |
| orders-worker | inventory-api | inventory.read |
| billing-worker | billing-api | billing.invoice.read, billing.payment.create |
| audit-console | audit-api | audit.read |

Không cấp scope quản trị chỉ vì client "có thể cần trong tương lai". Khi cần mở rộng, requester nêu lý do và resource owner phê duyệt. Scope nhạy cảm như quyền hoàn tiền, export dữ liệu, quản trị người dùng hoặc impersonation cần kiểm soát chặt hơn, có thể yêu cầu hai approver độc lập.

Token exchange cũng cần ràng buộc theo client, subject/actor, audience và scope. STS không nên cho client tự yêu cầu bất kỳ audience/scope nào rồi tin rằng token nguồn đã có quyền đó. Policy phải giới hạn tập audience/scope được phép phát hành; thay đổi policy cần SoD riêng.

## 6. SoD trong quản lý signing key và trust

JWT signing key có thể cho phép phát hành token được resource server tin cậy. Quyền tạo, kích hoạt, phân phối public key và thu hồi key vì vậy có tác động lớn.

Một quy trình quản lý key có thể chia:

1. Security/key owner đề xuất rotation hoặc tạo key mới theo lịch.
2. Key custodian tạo key trong HSM/KMS theo quy trình được kiểm soát; private key không được xuất ra dạng plaintext.
3. Approver độc lập xác nhận key ID, thuật toán, mục đích và phạm vi issuer.
4. Operator cập nhật JWKS/trust configuration theo change đã duyệt.
5. Hệ thống kiểm tra resource server tải được public key mới và xác minh token thử nghiệm.
6. Key owner theo dõi giai đoạn overlap và phê duyệt thời điểm ngừng key cũ.
7. Auditor kiểm tra log thao tác, approval và bằng chứng xác minh.

Không một cá nhân đơn lẻ nên vừa tạo key, tự đưa key vào trust, phát hành token đặc quyền và xóa audit. Tùy HSM/KMS, có thể dùng quorum hoặc dual authorization để thao tác key nhạy cảm cần nhiều người.

### 6.1 Không nhầm TLS certificate với JWT signing key

TLS certificate bảo vệ kênh kết nối và xác thực peer. JWT signing key ký token. Chúng có thể được quản lý bởi các hệ thống khác nhau và có vòng đời khác nhau. SoD phải bao phủ cả hai nhóm nếu chúng thuộc phạm vi tổ chức, nhưng không dùng cùng một approval hoặc runbook một cách máy móc.

Ví dụ, gia hạn TLS certificate của introspection endpoint cần owner endpoint và người triển khai; xoay JWT signing key cần key custodian, approver và xác minh JWKS/resource server. Khi một CA hoặc trust anchor thay đổi, cần đánh giá ảnh hưởng tới nhiều client và dịch vụ phụ thuộc.

## 7. SoD trong phát hành, exchange và thu hồi token

Phát hành token thông thường là hoạt động tự động theo policy; không yêu cầu con người phê duyệt từng token. SoD tập trung vào **ai được thay đổi policy và credential để hệ thống phát hành token**, không làm chậm từng request nghiệp vụ.

| Hoạt động | Kiểm soát SoD đề xuất |
| --- | --- |
| Cấp access token theo flow đã duyệt | STS/Authorization Server tự động thực thi policy; không cho application tự ký token bằng key issuer |
| Cấp refresh token | Policy quy định client, rotation, reuse detection và lifetime; thay đổi policy cần owner/approver độc lập |
| Token exchange | Client được allowlist audience/scope; thay đổi allowlist và delegation policy cần phê duyệt |
| Impersonation/delegation | Phân biệt subject và actor; yêu cầu lý do, thời hạn và approval theo mức rủi ro |
| Thu hồi một token | Quyền thao tác giới hạn theo issuer/client/resource; audit bắt buộc |
| Thu hồi hàng loạt hoặc vô hiệu hóa client | Có thể yêu cầu hai người xác nhận; incident process có ngoại lệ khẩn cấp |
| Thay đổi introspection/JWKS trust | Tách người yêu cầu, người duyệt và người triển khai |

Một administrator có thể cần quyền revoke token trong sự cố, nhưng không nên có quyền tự thay đổi policy để giữ token của mình active hoặc xóa dấu vết revoke. Tách quyền revoke khỏi quyền sửa audit retention và quyền quản trị signing key.

## 8. Audit và bằng chứng phê duyệt

SoD chỉ hiệu quả khi có thể chứng minh ai đã yêu cầu, ai phê duyệt, ai triển khai và kết quả thực tế có khớp với nội dung được duyệt hay không.

Audit event cho một change có thể chứa:

| Field | Ý nghĩa |
| --- | --- |
| change_id | Định danh change request |
| requester_id | Human identity đã xác thực khởi tạo |
| approver_ids | Identity độc lập đã phê duyệt |
| executor_id | Operator hoặc pipeline identity triển khai |
| resource | Client, audience, scope, policy hoặc key bị thay đổi |
| before/after | Diff cấu hình cần thiết, không chứa secret |
| artifact_hash | Hash/version của nội dung đã được duyệt |
| approval_time / execution_time | Thời điểm theo UTC |
| policy_version | Phiên bản policy kiểm tra SoD |
| outcome | Approved, rejected, deployed, failed hoặc rolled_back |
| correlation_id | Liên kết log/trace liên quan |

Không ghi client secret, private key, access token, refresh token hoặc raw credential vào audit. Khi cần định danh credential, dùng secret reference hoặc fingerprint được bảo vệ theo policy. Bản ghi audit nên được lưu ở hệ thống có quyền ghi hạn chế, chống sửa/xóa và retention phù hợp.

### 8.1 Kiểm tra approval ràng buộc với change

Một lỗi nguy hiểm là requester gửi yêu cầu scope A, approver duyệt A, nhưng operator hoặc pipeline triển khai scope B. Để tránh:

- Chuẩn hóa nội dung change thành artifact bất biến.
- Tính hash/version của artifact và đưa vào approval.
- Pipeline chỉ triển khai artifact có approval hợp lệ cho đúng hash.
- Sau triển khai, đọc lại cấu hình thực tế và so sánh với artifact.
- Nếu có drift, chặn hoặc rollback theo policy và tạo security event.

Không cho phép người triển khai chỉnh artifact sau khi duyệt mà không tạo vòng phê duyệt mới.

## 9. Break-glass và trường hợp khẩn cấp

Trong incident, có thể cần vô hiệu hóa client bị xâm nhập, thu hồi token hoặc xoay key ngay lập tức. Quy trình khẩn cấp không thể luôn chờ đủ người như thay đổi thông thường, nhưng cần giới hạn và hậu kiểm:

1. Chỉ định người kích hoạt break-glass theo danh sách đã phê duyệt.
2. Xác thực mạnh (MFA/phương thức tương đương) và cấp quyền JIT có thời hạn ngắn.
3. Chỉ cấp đúng quyền cần thiết cho incident, ví dụ revoke một client hoặc một nhóm token.
4. Ghi lý do, ticket/incident ID, phạm vi và thời điểm bắt đầu.
5. Gửi thông báo ngay cho incident commander/security owner.
6. Hậu kiểm độc lập trong thời hạn quy định; bổ sung approval hoặc xác nhận quyết định.
7. Thu hồi quyền break-glass, kiểm tra thay đổi và lưu audit bằng chứng.

Không dùng break-glass làm tài khoản vận hành thường ngày. Tài khoản khẩn cấp phải được giám sát, kiểm tra định kỳ, thử nghiệm phục hồi và có cảnh báo khi sử dụng. Nếu audit pipeline đang lỗi, cần cơ chế ghi bằng chứng thay thế có kiểm soát và đồng bộ lại sau khi hệ thống phục hồi.

## 10. Phát hiện và xử lý xung đột SoD

Xung đột có thể được phát hiện lúc cấp quyền, lúc tạo change request hoặc qua review định kỳ. Một số kiểm tra tự động:

- Requester và approver cùng một immutable user ID.
- Executor đồng thời là người phê duyệt change đặc quyền.
- Một identity có cả quyền quản lý signing key và quyền xóa audit.
- Service account có quyền admin ngoài audience/resource cần thiết.
- Một người có quyền tự tạo OAuth client, tự cấp scope và tự triển khai production.
- Break-glass identity được dùng ngoài incident hoặc vượt thời hạn.
- Approval không còn hợp lệ do artifact hash đã thay đổi.

Pseudo-policy minh họa:

~~~text
rule: privileged_client_scope_change
require:
  requester_authenticated: true
  resource_owner_approval: true
  security_approval: true
  artifact_hash_bound_to_approval: true
deny_if:
  requester_id == resource_owner_approver_id
  requester_id == security_approver_id
  executor_id == security_approver_id
  requested_scope not_in approved_scope_catalog
  target_environment == production and approval_expired
audit:
  record_request_approval_execution_and_readback: true
~~~

Đây là pseudo-policy để minh họa logic; schema và cách biểu diễn phải theo IAM/change management platform của tổ chức. Với nhiều approver, có thể cần kiểm tra độc lập cả requester, approver và executor. Không chỉ so sánh display name; dùng immutable identity ID và kiểm tra quan hệ tài khoản/nhóm có thể gây xung đột.

## 11. Kiểm thử Separation of duties

Kiểm thử SoD cần bao phủ cả trường hợp hợp lệ và trường hợp xung đột. Không chỉ test giao diện phê duyệt; phải test API/pipeline phía sau để tránh bypass bằng request trực tiếp.

| ID | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| SOD-01 | Requester tự phê duyệt yêu cầu scope đặc quyền | Bị từ chối |
| SOD-02 | Requester và approver là hai identity độc lập, đủ quyền | Có thể được duyệt |
| SOD-03 | Approver không phải owner của resource | Bị từ chối hoặc yêu cầu đúng approver |
| SOD-04 | Artifact thay đổi sau approval | Approval mất hiệu lực; không deploy |
| SOD-05 | Executor triển khai artifact chưa được duyệt | Pipeline chặn |
| SOD-06 | Một người có quyền sửa signing key và xóa audit | Phát hiện conflict/không cấp đồng thời |
| SOD-07 | Service account yêu cầu audience ngoài allowlist | STS từ chối |
| SOD-08 | Token exchange yêu cầu scope cao hơn policy | Không phát token vượt quyền |
| SOD-09 | Thu hồi hàng loạt không có phê duyệt theo policy | Chặn hoặc yêu cầu dual control |
| SOD-10 | Break-glass được kích hoạt đúng điều kiện | Cấp JIT ngắn hạn, audit và alert |
| SOD-11 | Break-glass hết hạn | Quyền bị thu hồi tự động |
| SOD-12 | Auditor chỉ có quyền đọc | Không thể sửa client, policy, key hoặc audit |
| SOD-13 | Approval log bị sửa/xóa | Integrity control phát hiện hoặc ngăn chặn |
| SOD-14 | Người dùng bị disable sau khi duyệt nhưng trước deploy | Pipeline kiểm tra lại trạng thái/ủy quyền theo policy |

### 11.1 Kiểm tra ma trận quyền

Có thể biểu diễn ma trận role-permission để rà soát:

| Permission | Requester | Resource owner | Security approver | Operator | Auditor |
| --- | ---: | ---: | ---: | ---: | ---: |
| Submit client change | Có | Có thể | Có thể | Không cần | Không |
| Approve resource scope | Không cho yêu cầu của mình | Có | Có thể | Không | Không |
| Approve security policy | Không | Không | Có | Không | Không |
| Deploy approved change | Không | Không | Không mặc định | Có | Không |
| Manage signing key | Không | Không | Theo key policy | Key custodian | Read-only |
| Read audit | Theo phạm vi | Theo phạm vi | Có | Theo phạm vi | Có |
| Delete/alter audit | Không | Không | Không | Không | Không |

Ma trận là ví dụ định hướng. Quyền đọc audit có thể được cấp cho nhiều vai trò theo nhu cầu; quyền sửa/xóa audit phải được hạn chế và có kiểm soát riêng. Một permission có thể được chia nhỏ hơn trong hệ thống thực tế.

## 12. Vận hành và review định kỳ

SoD không dừng ở thời điểm thiết kế. Khi nhân viên chuyển nhóm, workload được thay thế hoặc dự án kết thúc, quyền cũ có thể tạo xung đột mới.

Chu kỳ review nên:

- Rà soát membership của nhóm IAM/security/key custodian và approver.
- Đối chiếu quyền thực tế với ma trận SoD và danh mục client/scope.
- Xác định tài khoản không dùng, quyền JIT quá hạn và service account không còn owner.
- Kiểm tra change request, approval, artifact hash, deployment và readback.
- Kiểm tra break-glass usage và hậu kiểm còn thiếu.
- Kiểm tra quyền truy cập audit, retention và tính toàn vẹn.
- Rà soát ngoại lệ SoD, owner, lý do, biện pháp bù trừ và ngày hết hạn.

Mọi ngoại lệ cần có owner, lý do, phạm vi, thời hạn và biện pháp bù trừ. Ngoại lệ không nên trở thành quyền vĩnh viễn. Khi nhân sự thay đổi, thu hồi quyền approver/operator cũ và xác minh các workflow đang chờ không còn dựa trên approval không hợp lệ.

## 13. Checklist triển khai

- [ ] Đã lập danh mục hành động nhạy cảm trong vòng đời token.
- [ ] Có ma trận nhiệm vụ xung đột và vai trò chịu trách nhiệm.
- [ ] Requester không thể tự phê duyệt yêu cầu đặc quyền của mình.
- [ ] Resource owner xác nhận audience/scope thuộc API của mình.
- [ ] Security/IAM approver đánh giá thay đổi có rủi ro cao.
- [ ] Pipeline chỉ triển khai artifact đúng hash/version đã được duyệt.
- [ ] Quyền quản lý signing key, trust configuration và audit được tách phù hợp.
- [ ] Workload identity không dùng chung với tài khoản quản trị con người.
- [ ] Token exchange giới hạn audience/scope theo allowlist và policy.
- [ ] Thu hồi token/client và thay đổi khẩn cấp có audit, scope và owner rõ ràng.
- [ ] Break-glass có MFA, JIT, thời hạn, cảnh báo và hậu kiểm.
- [ ] Auditor có quyền đọc độc lập; không thể sửa/xóa bằng chứng.
- [ ] Có review định kỳ và xử lý ngoại lệ SoD hết hạn.
- [ ] Test API/pipeline để chứng minh không thể bypass approval bằng request trực tiếp.

## Tài liệu tham khảo

- **NIST SP 800-53 Rev. 5 — AC-5 Separation of Duties:** kiểm soát phân tách nhiệm vụ để giảm rủi ro lạm dụng đặc quyền.
- **NIST SP 800-53 Rev. 5 — AC-6 Least Privilege:** giới hạn quyền theo nhiệm vụ được giao.
- **NIST SP 800-53 Rev. 5 — IA-2 / IA-5:** nhận dạng, xác thực và quản lý authenticator.
- **NIST SP 800-57:** hướng dẫn quản lý khóa mật mã và vòng đời khóa.
- **OAuth 2.0 Security Best Current Practice (RFC 9700):** khuyến nghị bảo vệ OAuth client, token và authorization flow.
- **RFC 8693 — OAuth 2.0 Token Exchange:** subject/actor token, audience và scope trong token exchange.

Separation of duties giúp bảo đảm một quyết định đặc quyền có người yêu cầu, người đánh giá, người triển khai và bằng chứng độc lập phù hợp với mức rủi ro. Khi áp dụng cùng least privilege, quản lý workload identity và audit bền vững, tổ chức giảm khả năng một tài khoản hoặc một cá nhân đơn phương thay đổi ranh giới tin cậy của hệ thống token.
