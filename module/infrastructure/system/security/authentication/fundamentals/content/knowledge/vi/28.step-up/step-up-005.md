# High-value action — Bảo vệ hành động có giá trị hoặc rủi ro cao

> **Chương:** Step-up  
> **Chủ đề:** High-value action  
> **Phạm vi:** Security Authentication Fundamentals — phân loại hành động nhạy cảm, xác thực tăng cường đúng lúc, xác nhận nội dung giao dịch, authorization độc lập và kiểm toán.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện hành động có giá trị cao theo tác động, quyền hạn, độ nhạy cảm và khả năng đảo ngược.
2. Phân biệt step-up authentication, transaction confirmation, authorization và approval.
3. Thiết kế policy theo freshness, assurance, loại hành động và risk context.
4. Chọn phương thức step-up phù hợp, ưu tiên xác thực chống phishing cho hành động critical.
5. Ràng buộc proof với đúng subject, tenant, action và dữ liệu giao dịch.
6. Chống replay, substitution, TOCTOU và thực thi trùng.
7. Thiết kế maker-checker, recovery, audit và bộ kiểm thử cho hành động nhạy cảm.

## 1. High-value action là gì?

**High-value action** là hành động mà việc thực hiện trái phép, nhầm lẫn hoặc bị thay đổi có thể gây hậu quả đáng kể cho người dùng, tổ chức hoặc bên thứ ba. Giá trị không chỉ là tiền; nó còn bao gồm quyền quản trị, dữ liệu nhạy cảm, danh tính, quyền truy cập và thay đổi khó đảo ngược.

Ví dụ:

- Chuyển tiền, hoàn tiền, đổi tài khoản nhận thanh toán hoặc người thụ hưởng;
- Phê duyệt hóa đơn, giải ngân, thay đổi hạn mức;
- Thêm/xóa quản trị viên, cấp quyền đặc quyền hoặc thay đổi policy bảo mật;
- Đổi email/điện thoại khôi phục, tắt MFA hoặc xóa passkey cuối cùng;
- Xuất dữ liệu nhân sự, khách hàng hoặc tài chính quy mô lớn;
- Liên kết/huỷ liên kết danh tính hoặc thay đổi federation trust;
- Thay khóa ký, CA, issuer hoặc cấu hình xác thực;
- Xóa vĩnh viễn tài nguyên hoặc đóng tài khoản.

Một thao tác đọc hồ sơ có thể có rủi ro thấp; tải toàn bộ hồ sơ của hàng nghìn nhân viên có thể là high-value action. Cùng endpoint cũng có thể có mức rủi ro khác nhau tùy số lượng, giá trị, tenant và chủ thể bị ảnh hưởng.

### Các chiều đánh giá

| Chiều | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Impact | Hậu quả nếu bị lạm dụng lớn đến đâu? | Chuyển tiền lớn |
| Privilege | Có làm tăng quyền hoặc đổi ranh giới tin cậy? | Tạo global administrator |
| Reversibility | Có khôi phục đầy đủ được không? | Xóa vĩnh viễn dữ liệu |
| Scope | Bao nhiêu người/tenant/tài nguyên bị ảnh hưởng? | Export toàn tổ chức |
| Sensitivity | Dữ liệu hoặc credential nhạy cảm đến mức nào? | Thay recovery factor |
| Financial/legal exposure | Có phát sinh nghĩa vụ tài chính/pháp lý? | Phê duyệt thanh toán |
| Context | Hành động có bất thường với user/session/device? | Thêm người nhận ngay sau login từ thiết bị mới |

Có thể phân loại low, elevated, high và critical. Hành động đặc biệt nhạy cảm có thể luôn cần approval độc lập, bất kể risk score.

## 2. Step-up authentication giải quyết vấn đề gì?

Người dùng có thể đã đăng nhập từ trước nhưng lần xác thực đó quá cũ hoặc không đủ mạnh cho hành động sắp thực hiện. Ví dụ, một session tạo buổi sáng bằng mật khẩu vẫn còn hiệu lực vào buổi chiều, khi người dùng muốn đổi tài khoản nhận tiền. Session còn hiệu lực không chứng minh người đang yêu cầu thao tác vừa xác thực lại bằng phương thức phù hợp.

**Step-up authentication** là yêu cầu người dùng thực hiện thêm một lần xác thực hoặc dùng phương thức có mức đảm bảo cao hơn trước khi tiếp tục hành động cụ thể.

Các trigger thường gặp:

- Action nằm trong danh sách nhạy cảm;
- Lần xác thực gần nhất quá cũ;
- Session chưa đạt assurance cần thiết;
- Người dùng vừa đổi thiết bị, credential hoặc recovery setting;
- Có tín hiệu bất thường về thiết bị, mạng, vị trí hoặc hành vi;
- Giao dịch vượt ngưỡng giá trị hoặc thay đổi người thụ hưởng;
- Policy yêu cầu xác thực mới trước khi thay đổi quyền.

Step-up không nên xuất hiện trước mọi thao tác nhỏ. Prompt quá thường xuyên tạo thói quen bấm chấp thuận mà không đọc nội dung. Cần định nghĩa rõ trigger và phạm vi reuse.

## 3. Bốn quyết định phải tách biệt

| Quyết định | Câu hỏi | Bằng chứng/chính sách |
| --- | --- | --- |
| Authentication | Ai đang thao tác và vừa chứng minh điều gì? | Credential, passkey, MFA, auth_time, assurance |
| Transaction confirmation | Người dùng xác nhận đúng nội dung hành động nào? | Chi tiết giao dịch và challenge gắn transaction |
| Authorization | Chủ thể có quyền làm việc đó trên tài nguyên này không? | Role, scope, tenant, ownership, policy |
| Approval | Có cần người khác/quy trình độc lập phê duyệt không? | Maker-checker, quorum, separation of duties |

Không gộp các quyết định này thành một cờ authenticated=true. Step-up thành công không tự chứng minh người dùng có quyền, đã nhìn thấy đúng nội dung giao dịch hoặc đã có phê duyệt độc lập.

`````````mermaid
flowchart TD
    A["Yêu cầu hành động"] --> B["Tải dữ liệu giao dịch từ server"]
    B --> C["Đánh giá risk và phân loại action"]
    C --> D{"Authorization cho phép?"}
    D -- "Không" --> X["Từ chối và audit"]
    D -- "Có" --> E{"Cần step-up?"}
    E -- "Có" --> F["Xác thực mới theo assurance policy"]
    E -- "Không" --> G["Xác nhận và approval theo policy"]
    F --> H{"Step-up hợp lệ và fresh?"}
    H -- "Không" --> X
    H -- "Có" --> G
    G --> I{"Transaction và approval hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Thực thi một lần và ghi audit"]
`````````

## 4. Policy cho high-value action

Policy cần chỉ rõ hành động nào cần step-up, phương thức nào được chấp nhận, freshness bao lâu và điều kiện nào làm mất hiệu lực lần xác thực trước.

| Hành động | Rủi ro minh họa | Step-up | Kiểm soát bổ sung |
| --- | --- | --- | --- |
| Xem hồ sơ cá nhân | Thấp | Có thể không cần khi session hợp lệ | Authorization theo account |
| Export báo cáo giới hạn | Trung bình | Khi session cũ hoặc risk tăng | Giới hạn dữ liệu, audit export |
| Thêm người thụ hưởng | Cao | Phương thức mạnh, ưu tiên chống phishing | Notification, thời gian chờ/hạn mức |
| Chuyển tiền lớn | Cao/critical | Phishing-resistant authentication | Transaction confirmation, risk check, có thể dual approval |
| Tắt MFA/xóa passkey cuối | Cao | Reauthentication mạnh | Recovery plan và notification |
| Tạo global administrator | Critical | Step-up mạnh | Approval độc lập, least privilege |
| Thay CA/issuer/JWKS trust | Critical | Step-up mạnh cho admin | Maker-checker và change control |
| Xóa dữ liệu không thể khôi phục | Critical | Step-up mạnh | Delay, dual control, backup validation |

Đây là ví dụ thiết kế, không phải ngưỡng áp dụng chung. Mỗi tổ chức phải xác định policy theo threat model, nghĩa vụ pháp lý, giá trị giao dịch và khả năng khôi phục.

Mỗi rule nên xác định action type, resource scope, subject/role, assurance, freshness, user verification, approval, fallback, context invalidation và audit reason code. Không dùng rule mơ hồ như “MFA nếu thấy rủi ro” mà thiếu định nghĩa tín hiệu, nguồn, freshness và hành vi khi risk service không khả dụng.

## 5. Freshness và assurance

Hai thuộc tính quan trọng của step-up:

- **Freshness:** lần xác thực gần nhất cách hiện tại bao lâu?
- **Assurance:** phương thức và quy trình xác thực đạt mức tin cậy nào theo policy?

Một lần đăng nhập mới bằng mật khẩu yếu không nhất thiết đáp ứng hành động critical. Một passkey phishing-resistant vừa được xác minh có thể đáp ứng yêu cầu xác thực mạnh, nhưng vẫn không thay thế transaction confirmation hoặc authorization.

Ví dụ policy minh họa:

- Hành động nhạy cảm vừa phải: xác thực mạnh trong 10 phút;
- Thay đổi recovery factor: xác thực lại ngay trước thao tác;
- Hành động quản trị critical: xác thực mạnh mới và approval độc lập.

Khoảng thời gian cần được xác định theo rủi ro, không dùng một giá trị cố định cho mọi hệ thống.

### Reuse step-up context

Nếu cho phép tái sử dụng một lần step-up, phải giới hạn thời gian, action class, resource/tenant, assurance, session và số lần dùng. Không dùng cờ step_up=true vô thời hạn cho mọi thao tác. Xác thực để xem thông tin thanh toán không tự cấp quyền đổi recovery email hoặc tạo administrator.

Ví dụ metadata:

`````````yaml
authentication_context:
  subject_id: user-1042
  authenticated_at: "2026-11-22T06:15:00Z"
  method: webauthn_passkey
  phishing_resistant: true
  user_verified: true
  assurance_policy: high_value_action_v2
  step_up_at: "2026-11-22T06:15:00Z"
  action_scope: payment.transfer
  transaction_id: txn-7d21
  expires_at: "2026-11-22T06:20:00Z"
`````````

Đây là metadata minh họa. Các thuộc tính phishing_resistant, user_verified và assurance_policy chỉ được đặt sau khi verifier kiểm chứng bằng chứng theo giao thức; không lấy giá trị do client tự khai.

## 6. Chọn phương thức step-up

| Phương thức | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Passkey/WebAuthn | Có thể chống phishing nhờ ràng buộc origin/RP ID; private key không rời authenticator | Cần xác minh user verification và credential policy |
| Security key | Phishing-resistant khi dùng FIDO đúng cách | Cần quản lý mất khóa và credential dự phòng |
| Smart card/client certificate | Xác thực mật mã mạnh và tích hợp PKI | Cần quản lý thẻ, PIN, certificate và revocation |
| TOTP | Phổ biến, hoạt động offline | Mã có thể bị phishing/relay trong thời gian hiệu lực |
| Push approval | Thuận tiện | Push đơn giản có nguy cơ fatigue và không tự chống phishing |
| Push number matching | Giảm phê duyệt nhầm | Không tự ràng buộc mật mã với transaction |
| SMS/voice OTP | Có thể dùng làm fallback hạn chế | SIM swap và tấn công viễn thông; không phù hợp làm lựa chọn mạnh cho critical |
| Password re-entry | Dễ triển khai | Không phải yếu tố độc lập mới; vẫn có thể bị phishing |

Với hành động giá trị cao, ưu tiên passkey/WebAuthn hoặc security key có user verification theo policy. TOTP, SMS và push có thể tăng độ khó nhưng vẫn có thể bị phishing, relay hoặc social engineering. Number matching cải thiện push approval nhưng không thay thế proof mật mã ràng buộc với website và giao dịch.

MFA không chỉ là số lượng yếu tố. Cần xem xét tính độc lập, khả năng chống phishing, user verification, nguy cơ relay, thiết bị bị chiếm và khả năng thu hồi/recovery.

## 7. Transaction confirmation

Step-up chứng minh người dùng vừa thực hiện thao tác xác thực. Để bảo vệ giao dịch, ứng dụng cần hiển thị nội dung quan trọng và yêu cầu xác nhận riêng.

Với giao dịch chuyển tiền, màn hình cần hiển thị:

- Tài khoản nguồn;
- Người nhận và thông tin định danh;
- Số tiền, đơn vị tiền tệ, phí và tổng tiền bị trừ;
- Nội dung và thời điểm xử lý;
- Hạn mức hoặc điều kiện đặc biệt.

Với thay đổi quyền, màn hình cần nêu tài khoản nhận quyền, role, tenant, tài nguyên, thời hạn và người phê duyệt.

Không chỉ hiển thị “Bạn có chắc muốn tiếp tục?” cho hành động tác động lớn. Người dùng cần hiểu đối tượng và hệ quả.

### What you see is what you sign

Nội dung người dùng xem phải tương ứng với dữ liệu server sẽ thực thi. Trang web bị compromise có thể hiển thị người nhận X nhưng gửi recipient Y. Nếu authenticator chỉ ký challenge chung mà không hiển thị giao dịch trên trusted display, không nên tuyên bố người dùng đã ký đúng nội dung họ nhìn thấy.

Với giao dịch rất rủi ro, cân nhắc thiết bị xác nhận độc lập hoặc quy trình ngoài băng có khả năng hiển thị chi tiết giao dịch đáng tin cậy.

## 8. Ràng buộc step-up với transaction

Không tái sử dụng proof của hành động A để xác nhận hành động B. Server cần tạo transaction ID và snapshot dữ liệu có thẩm quyền. Challenge nên ràng buộc:

- Transaction ID;
- Subject/account và tenant;
- Action type và resource;
- Recipient/target principal;
- Amount/currency hoặc quyền được cấp;
- Version dữ liệu và thời điểm tạo;
- Nonce ngẫu nhiên, expiry và audience/service nhận proof.

Có thể tạo digest trên biểu diễn canonical của dữ liệu cần xác nhận. Canonicalization phải xác định thứ tự trường, encoding, Unicode, đơn vị tiền và biểu diễn số. Không hash chuỗi JSON tùy tiện có format không ổn định.

Ví dụ dữ liệu:

`````````json
{
  "transaction_id": "txn-7d21",
  "subject": "user-1042",
  "tenant": "tenant-42",
  "action": "payment.transfer",
  "recipient_id": "beneficiary-82",
  "amount_minor": 12500000,
  "currency": "VND",
  "nonce": "server-generated-random-value",
  "expires_at": "2026-11-22T06:20:00Z"
}
`````````

amount_minor là số nguyên theo đơn vị nhỏ nhất của currency; không dùng số thực dấu phẩy động cho tiền.

Quy trình:

1. Server tạo transaction snapshot và digest.
2. Server phát challenge gắn digest, transaction ID, subject, audience và expiry.
3. Người dùng xem chi tiết rồi thực hiện step-up/confirmation.
4. Client gửi proof và transaction reference.
5. Server xác minh proof, freshness, subject, tenant và challenge.
6. Server tải lại trạng thái có thẩm quyền, kiểm tra dữ liệu chưa đổi.
7. Server chạy authorization và approval policy lần cuối.
8. Server tiêu thụ confirmation atomically và thực thi idempotently.

Nếu recipient, amount, role hoặc resource thay đổi sau xác nhận, transaction cũ phải bị vô hiệu hóa và cần xác nhận lại.

`````````
confirmHighValueAction(transactionId, userProof):
    txn = loadTransactionFromServer(transactionId)
    require(txn.status == PENDING_CONFIRMATION)
    require(txn.subjectId == authenticatedUser.id)
    require(txn.tenantId == authenticatedUser.tenantId)
    require(not txn.expired)

    currentData = reloadAuthoritativeActionData(txn.resourceId)
    require(canonicalDigest(currentData) == txn.confirmedDigest)
    require(verifyStepUpProof(userProof, txn.challenge, txn.confirmedDigest))
    require(stepUpIsFreshAndMeetsPolicy(userProof, txn.actionType))
    require(authorizationAllows(authenticatedUser, currentData))
    require(requiredApprovalsAreComplete(txn))

    atomicallyConsumeConfirmationAndMarkExecuting(txn)
    return executeIdempotently(txn)
`````````

Đây là pseudocode khái niệm. Consume và chuyển trạng thái cần atomic bằng transaction/locking hoặc cơ chế tương đương. Không tin dữ liệu giao dịch do browser gửi lại nếu chưa đối chiếu snapshot server.

## 9. Chống replay, substitution và TOCTOU

**Replay:** Attacker ghi lại proof hợp lệ và gửi lại để thực hiện cùng hành động nhiều lần. Dùng challenge entropy cao, transaction ID duy nhất, expiry ngắn, trạng thái consumed phía server, atomic compare-and-set và idempotency key.

**Substitution:** Attacker lấy proof của giao dịch A dùng cho B. Proof cần ràng buộc với transaction digest, subject, tenant, action và audience. Không chấp nhận assertion chung kiểu “user đã MFA” cho mọi giao dịch.

**TOCTOU:** Dữ liệu thay đổi sau khi người dùng xác nhận nhưng trước khi thực thi. Ví dụ recipient đổi từ X sang Y do race condition. Biện pháp:

1. Tạo immutable snapshot hoặc version cho trường quan trọng;
2. Gắn proof với digest/version;
3. Kiểm tra version/digest ngay trước execute;
4. Nếu thay đổi, hủy confirmation và yêu cầu xác nhận mới;
5. Thực thi trong transaction nhất quán;
6. Dùng idempotency để ngăn double-submit.

## 10. State machine cho high-value action

`````````mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_CONFIRMATION: Snapshot và challenge
    PENDING_CONFIRMATION --> CONFIRMED: Step-up và confirmation hợp lệ
    PENDING_CONFIRMATION --> EXPIRED: Hết hạn
    PENDING_CONFIRMATION --> CANCELLED: Hủy hoặc dữ liệu đổi
    CONFIRMED --> PENDING_APPROVAL: Cần maker-checker
    CONFIRMED --> READY: Không cần approval khác
    PENDING_APPROVAL --> READY: Đủ phê duyệt
    PENDING_APPROVAL --> REJECTED: Bị từ chối
    READY --> EXECUTING: Atomic claim
    EXECUTING --> COMPLETED: Thành công
    EXECUTING --> FAILED: Lỗi
    FAILED --> READY: Retry an toàn theo policy
    COMPLETED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
`````````

| Trạng thái | Ý nghĩa |
| --- | --- |
| DRAFT | Đang chuẩn bị, chưa có confirmation |
| PENDING_CONFIRMATION | Snapshot tạo xong, chờ step-up và xác nhận |
| CONFIRMED | Người dùng xác nhận đúng transaction |
| PENDING_APPROVAL | Chờ checker độc lập |
| READY | Đạt mọi điều kiện trước thực thi |
| EXECUTING | Một worker/request nhận quyền thực thi duy nhất |
| COMPLETED | Side effect đã hoàn tất |
| FAILED | Thực thi thất bại; retry theo idempotency policy |
| EXPIRED/CANCELLED/REJECTED | Không còn được thực thi |

Client không được tự gửi status=confirmed để chuyển trạng thái. Chỉ service có thẩm quyền cập nhật state sau khi xác minh đủ điều kiện.

## 11. Risk-based step-up

Policy có thể kết hợp mức rủi ro của action với tín hiệu phiên, user và device:

- Thời điểm và phương thức xác thực gần nhất;
- Tuổi session và step-up gần nhất;
- Thiết bị mới, credential mới hoặc compliance;
- IP/ASN, vị trí bất thường và thay đổi mạng;
- Tốc độ/thứ tự hành động;
- Người thụ hưởng vừa được thêm;
- Số tiền, số lượng tài nguyên hoặc phạm vi dữ liệu;
- Thay đổi recovery/MFA gần đây;
- Dấu hiệu credential stuffing, session theft hoặc account takeover.

IP quen thuộc hoặc thiết bị managed không chứng minh user hợp lệ. Người dùng hợp lệ cũng có thể đổi mạng hoặc đi du lịch. Risk signals hỗ trợ policy, không thay credential verification.

`````````
evaluateAction(user, session, device, action):
    require(user.status == ACTIVE)
    require(baseAuthorizationAllows(user, action))

    risk = assessRisk(user, session, device, action)
    assurance = requiredAssurance(action, risk)

    if not session.authenticationIsFresh(assurance.maxAge):
        require(stepUp(assurance.methods, action))

    if action.isCritical:
        require(transactionConfirmationBoundTo(action.transaction))

    if action.requiresDualControl:
        require(independentApprovalFromDifferentPrincipal(action))

    return ALLOW
`````````

Đây là pseudocode minh họa. Critical và dual control phải do policy server quyết định. Không để client tự gửi risk score hoặc tự khai step-up đã đạt.

## 12. Dual control và separation of duties

Một số hành động quá nhạy cảm để một người vừa tạo vừa tự phê duyệt. Maker-checker tách:

- Maker chuẩn bị giao dịch;
- Checker khác xác minh dữ liệu và phê duyệt;
- Hệ thống kiểm tra hai principal độc lập và quyền phù hợp;
- Một người không được thỏa cả hai vai trò nếu policy cấm;
- Mọi thay đổi sau phê duyệt làm mất hiệu lực approval.

Checker phải nhìn thấy cùng snapshot hoặc digest mà hệ thống sẽ thực thi. Không phê duyệt transaction ID rồi cho phép maker thay amount, recipient hoặc role.

Có thể yêu cầu nhiều checker theo quorum. Mỗi approval cần actor, thời điểm, policy version, transaction digest và context xác thực. Step-up của maker không thay approval của checker; approval của checker cũng không tự chứng minh maker có quyền tạo giao dịch.

## 13. Session và phạm vi hiệu lực step-up

Step-up context cần gắn với subject, session và transaction/action. Lưu method, assurance, auth_time, step_up_at và policy version đã đánh giá. Giới hạn freshness window và chỉ reuse với action class được phép.

Không nâng assurance của toàn bộ session vô thời hạn. Vô hiệu hóa context khi session bị revoke, account disabled hoặc credential liên quan bị thu hồi. Yêu cầu xác thực lại sau thay đổi password, MFA, passkey hoặc recovery setting nếu policy quy định.

Một số hệ thống có thể tạo elevated session. Khi đó elevated state phải có thời hạn ngắn, chỉ mở tập action xác định, có audit và không được refresh token kéo dài vô hạn. API vẫn kiểm tra authorization và transaction binding.

Không dùng boolean trong browser storage để chứng minh step-up. Bằng chứng phải được giữ và xác minh ở server hoặc trong session/token được bảo vệ.

## 14. Fallback và recovery

Người dùng có thể mất security key, điện thoại hoặc không truy cập authenticator. Fallback phải đủ an toàn cho mức rủi ro:

- Ưu tiên credential dự phòng đã enrollment và xác minh trước;
- Nếu dùng helpdesk, xác minh danh tính qua quy trình độc lập và audit;
- Áp dụng dual control cho tài khoản đặc quyền;
- Có thời gian chờ và notification cho thay đổi recovery;
- Giới hạn high-value action trong giai đoạn recovery nếu risk policy yêu cầu;
- Không tự động hạ mọi hành động xuống SMS/email OTP chỉ vì mất passkey;
- Thu hồi credential cũ khi có bằng chứng mất hoặc compromise.

Recovery không được là đường vòng yếu hơn. Nếu action yêu cầu phishing-resistant authentication, recovery chỉ dựa vào email có thể trở thành điểm yếu nhất. Cần assurance tương xứng hoặc trì hoãn hành động tới khi trust được khôi phục.

## 15. Trải nghiệm người dùng và notification

Giao diện cần nêu hành động cụ thể, hiển thị dữ liệu quan trọng, giải thích lý do step-up ở mức phù hợp và cho phép hủy trước khi xác nhận. Nếu transaction hết hạn hoặc dữ liệu đổi, phải báo rõ và tạo xác nhận mới.

Để giảm approval fatigue:

- Không gửi push lặp lại để người dùng cuối cùng bấm chấp thuận;
- Giới hạn số challenge đang chờ;
- Dùng number matching hoặc hiển thị context nếu có push;
- Nêu tên dịch vụ và hành động đang yêu cầu;
- Cho phép báo cáo yêu cầu không do người dùng khởi tạo;
- Tự hết hạn challenge chưa xử lý.

Sau thay đổi nhạy cảm, thông báo qua kênh đã đăng ký trước đó. Không chỉ thông báo tới email/điện thoại vừa được thay đổi trong chính giao dịch đó.

## 16. Threat model

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| Session hijacking | Attacker chiếm session còn hiệu lực | Fresh step-up, risk checks, revocation |
| Phishing relay | OTP bị lấy và relay | Passkey/WebAuthn hoặc security key |
| Push fatigue | User approve do bị spam | Number matching, rate limit, context |
| Transaction substitution | Proof A dùng cho B | Digest binding, audience, nonce |
| Replay | Gửi lại proof đã xác nhận | Single-use challenge, atomic consume, idempotency |
| TOCTOU | Dữ liệu đổi sau confirmation | Snapshot, version check, atomic execution |
| CSRF | Browser bị dụ xác nhận action | CSRF, origin checks, transaction binding |
| Authorization bypass | Step-up bị hiểu nhầm là có quyền | Authorization riêng phía server |
| Self approval | Maker tự làm checker | Principal independence và separation of duties |
| Recovery downgrade | Recovery yếu được dùng để qua step-up | Assurance tương xứng, dual control, delay |
| Double execution | Retry/race tạo side effect nhiều lần | State machine, idempotency, atomic transition |
| Stale step-up | Reuse context cũ cho action mới | Freshness, action scope, session binding |
| Insider misuse | Người có quyền lạm dụng thao tác | Least privilege, dual control, immutable audit |

## 17. Tình huống: thay đổi người thụ hưởng và chuyển tiền

Một ứng dụng tài chính cho phép thêm người thụ hưởng và chuyển tiền. Nếu chỉ kiểm tra session active, attacker chiếm session có thể thêm người nhận rồi chuyển tiền.

Thiết kế ban đầu có vấn đề:

1. Thêm người thụ hưởng chỉ cần session đang đăng nhập.
2. Chuyển tiền chỉ yêu cầu nhập lại mật khẩu.
3. Màn hình hiển thị người nhận X nhưng server lấy recipient ID từ request khác.
4. Challenge MFA không gắn với số tiền hoặc người nhận.
5. Challenge không được đánh dấu đã dùng; retry có thể chuyển tiền lần nữa.
6. Mất passkey thì support có thể tắt MFA chỉ bằng email.

Thiết kế lại:

1. Thêm người thụ hưởng yêu cầu step-up phishing-resistant và notification theo policy.
2. Server tải beneficiary, tài khoản nguồn, amount và currency từ nguồn có thẩm quyền.
3. Server tạo transaction snapshot, ID, digest, nonce và expiry.
4. UI hiển thị người nhận, tài khoản nguồn, số tiền, phí và tổng tiền.
5. User thực hiện passkey step-up và xác nhận transaction; proof gắn digest.
6. Server kiểm tra freshness, subject, beneficiary, amount, account status, hạn mức và authorization.
7. Giao dịch vượt ngưỡng cần checker độc lập phê duyệt cùng digest.
8. Server atomically chuyển EXECUTING và thực thi idempotently.
9. Nếu dữ liệu đổi, transaction bị hủy và cần confirmation mới.
10. Gửi notification tới kênh đã đăng ký trước đó và ghi audit.
11. Recovery passkey dùng quy trình xác minh riêng, không cho email đơn lẻ tắt step-up critical.

Kết quả mong đợi: session bị chiếm không đủ để tự chuyển tiền; proof cũ không dùng cho người nhận/số tiền mới; retry không tạo giao dịch trùng; user thiếu quyền vẫn bị từ chối; dual control không thể tự phê duyệt.

## 18. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Session còn hiệu lực nhưng step-up cũ | Gọi endpoint sau freshness window | Yêu cầu step-up mới |
| Step-up hợp lệ | Dùng authenticator đáp ứng policy | Tiếp tục kiểm tra transaction và authorization |
| Phương thức yếu | Dùng SMS/TOTP khi critical chỉ cho phishing-resistant | Từ chối hoặc yêu cầu phương thức đạt chuẩn |
| User verification thiếu | WebAuthn assertion không đáp ứng UV policy | Từ chối |
| Sai subject | Proof thuộc user khác | Từ chối |
| Sai action scope | Step-up cho profile settings dùng cho payment | Từ chối |
| Sai transaction | Proof A gửi cho B | Từ chối |
| Sai digest | Thay amount/recipient sau confirmation | Hủy confirmation |
| Sai tenant/resource | Dùng proof ở tenant khác | Từ chối |
| Challenge replay | Gửi lại proof đã tiêu thụ | Từ chối |
| Challenge expired | Gửi proof sau expiry | Từ chối |
| Concurrent submit | Hai request cùng consume confirmation | Chỉ một request thực thi |
| Idempotent retry | Retry sau timeout khi side effect hoàn tất | Trả kết quả cũ, không lặp side effect |
| TOCTOU | Đổi dữ liệu giữa confirm và execute | Version/digest mismatch, không thực thi |
| Authorization denied | Step-up thành công nhưng thiếu role | Từ chối |
| Dual approval missing | Critical action chưa có checker | Không chuyển READY/EXECUTING |
| Self approval | Maker cố tự làm checker | Từ chối |
| Approval invalidated | Sửa giao dịch sau checker duyệt | Approval mất hiệu lực |
| Recovery downgrade | Email-only recovery cho critical action | Không chấp nhận |
| Account disabled | Disable account sau step-up | Không thực thi |
| Credential revoked | Passkey/security key bị revoke | Proof mới bị từ chối |
| Push fatigue | Gửi nhiều push không có transaction context | Rate limit và cảnh báo |
| CSRF | Confirmation thiếu CSRF/transaction binding | Từ chối |
| Audit redaction | Kiểm tra log/tracing | Không có password, OTP, key, token hoặc secret thô |
| Notification | Đổi người thụ hưởng | Gửi tới kênh đã đăng ký trước đó |

Kiểm thử tại authentication verifier, transaction service, authorization engine và nơi thực thi side effect. Chỉ kiểm tra UI hiển thị prompt không chứng minh giao dịch được ràng buộc an toàn.

## 19. Audit và chỉ số vận hành

| Event | Trường gợi ý |
| --- | --- |
| high_value_action.started | Transaction ID, actor reference, tenant, action type |
| high_value_action.risk_evaluated | Risk policy version, risk band, reason codes |
| step_up.requested | Subject/session reference, assurance, freshness, action scope |
| step_up.succeeded/failed | Method reference, assurance result, reason code, timestamp |
| transaction.displayed | Transaction ID, digest/version, UI confirmation version |
| transaction.confirmed/rejected | Actor, digest, challenge reference, time |
| approval.requested/approved/rejected | Maker/checker, policy, transaction digest |
| high_value_action.executing | Idempotency reference, execution attempt |
| high_value_action.completed/failed | Result reference, side-effect ID, reason |
| step_up.context.revoked | Subject/session, action scope, reason |
| recovery.completed | Recovery method, approval and affected credentials |

Không ghi password, OTP, raw authenticator assertion, private key, access/refresh token, session cookie hoặc secret challenge. Ghi credential reference và transaction digest theo retention policy.

Chỉ số nên theo dõi:

- Step-up challenge rate theo loại hành động;
- Step-up success/failure theo method và reason code;
- Freshness rejection rate;
- Phishing-resistant coverage cho high-value action;
- Transaction mismatch và replay rejection count;
- TOCTOU cancellation count;
- Dual-control compliance;
- Recovery downgrade attempts;
- Duplicate execution prevention;
- Post-revocation acceptance;
- User abandonment rate để phát hiện UX khó hiểu hoặc prompt quá thường xuyên.

Không tối ưu success rate bằng cách hạ assurance. Tỷ lệ thất bại cao có thể do phishing, credential issue, UX kém hoặc policy sai; cần phân loại trước khi thay đổi ngưỡng.

## 20. Checklist triển khai

- **Action inventory:** Đã liệt kê hành động theo impact, privilege, sensitivity và reversibility?
- **Policy:** Mỗi hành động có risk band, assurance, freshness và fallback?
- **Step-up method:** Phương thức phù hợp threat model và mức chống phishing?
- **Freshness:** Context có expiry và action scope?
- **Confirmation:** Người dùng thấy đúng recipient, amount, resource hoặc role?
- **Transaction binding:** Proof gắn subject, tenant, action, digest, audience và expiry?
- **Authorization:** Quyền được kiểm tra riêng sau step-up và ngay trước execute?
- **Dual control:** Critical action có maker-checker/quorum khi cần?
- **Replay:** Challenge single-use, atomic consume và idempotency?
- **TOCTOU:** Dữ liệu được đối chiếu bằng version/digest trước thực thi?
- **State machine:** Pending, confirmed, approved, executing, completed và cancelled có transition được kiểm soát?
- **Session:** Step-up context không reuse vô hạn hoặc cho action khác?
- **Recovery:** Fallback không yếu hơn assurance cần thiết?
- **Notification:** Người dùng được báo qua kênh đã đăng ký trước đó?
- **Audit:** Có reason code, transaction reference và approval history mà không lưu secret?
- **Testing:** Đã thử substitution, replay, concurrency, authorization denial, recovery downgrade và duplicate execution?

### Câu hỏi tự kiểm tra

1. High-value action được xác định theo chiều nào ngoài giá trị tiền?
2. Step-up khác transaction confirmation và authorization ra sao?
3. Vì sao MFA thành công không tự phê duyệt giao dịch?
4. Freshness và assurance khác nhau thế nào?
5. Vì sao passkey/WebAuthn phù hợp với hành động nhạy cảm hơn OTP có thể bị phishing?
6. Transaction digest cần ràng buộc dữ liệu nào?
7. Làm thế nào ngăn dữ liệu thay đổi giữa lúc xác nhận và thực thi?
8. Vì sao critical action có thể cần maker-checker dù cả hai đều step-up?
9. Recovery yếu có thể phá vỡ policy step-up ra sao?
10. Cần kiểm thử gì để bảo đảm confirmation không bị thực thi hai lần?

## Kết luận

**High-value action cần một chuỗi quyết định độc lập: xác thực đủ mạnh và đủ mới, xác nhận đúng nội dung giao dịch, kiểm tra quyền và phê duyệt bổ sung khi cần.** Step-up chứng minh người dùng vừa đáp ứng yêu cầu xác thực; transaction binding chứng minh confirmation áp dụng cho đúng hành động; authorization quyết định chủ thể có quyền; maker-checker tách người tạo và người duyệt khi tác động đủ lớn. Challenge phải có thời hạn, dùng một lần và gắn với subject, tenant, action cùng dữ liệu giao dịch có thẩm quyền. Server cần kiểm tra lại dữ liệu ngay trước thực thi, chuyển trạng thái atomically và dùng idempotency để chống replay/double execution. Hệ thống an toàn phải bảo đảm đúng người, đúng quyền, đúng giao dịch và đúng thời điểm.
