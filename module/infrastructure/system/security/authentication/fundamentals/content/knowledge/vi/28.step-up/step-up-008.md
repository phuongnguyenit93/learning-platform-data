# Step-up recovery — Khôi phục an toàn khi không hoàn tất được xác thực nâng cấp

## 1. Step-up recovery là gì?

**Step-up authentication** là yêu cầu người dùng cung cấp bằng chứng xác thực mạnh hơn hoặc mới hơn trước khi thực hiện một hành động nhạy cảm. **Step-up recovery** là quy trình giúp người dùng tiếp tục truy cập hợp lệ khi họ không thể hoàn tất bước xác thực nâng cấp, chẳng hạn mất thiết bị passkey, điện thoại hết pin, ứng dụng TOTP không còn đồng bộ hoặc authenticator push không khả dụng.

Ví dụ: nhân viên đã đăng nhập hệ thống nhân sự bằng mật khẩu và TOTP từ đầu ngày. Khi thay đổi tài khoản nhận lương, ứng dụng yêu cầu xác thực gần đây bằng passkey. Người dùng làm mất điện thoại chứa passkey. Hệ thống cần một quy trình khôi phục đủ tin cậy để người dùng chứng minh quyền kiểm soát tài khoản, đăng ký lại phương thức mạnh và thực hiện lại step-up. Hệ thống không được tự động bỏ yêu cầu xác thực chỉ vì người dùng không còn thiết bị.

Trong chương **Step-up** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần thiết kế luồng khôi phục có ranh giới tin cậy rõ ràng, chống phishing, replay, social engineering và lạm dụng quy trình hỗ trợ.

**Khôi phục step-up không phải là bỏ qua step-up.** Nó khôi phục khả năng chứng minh danh tính và đạt mức assurance cần thiết. Sau recovery, ứng dụng phải đánh giá lại authentication context và yêu cầu step-up cho hành động đang chờ theo chính sách ban đầu.

## 2. Phân biệt step-up, reauthentication và account recovery

Các thuật ngữ có liên quan nhưng không đồng nghĩa:

| Quy trình | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Step-up authentication** | Nâng mức assurance hoặc làm mới bằng chứng trước một hành động. | Yêu cầu passkey trước khi thay đổi thông tin nhận lương. |
| **Reauthentication** | Xác minh lại người dùng, có thể bằng yếu tố hiện tại. | Nhập lại mật khẩu hoặc xác nhận passkey vì phiên đã cũ. |
| **Step-up recovery** | Khôi phục khả năng hoàn tất step-up khi phương thức yêu cầu không khả dụng. | Dùng passkey dự phòng hoặc recovery code để khôi phục authenticator. |
| **Account recovery** | Khôi phục quyền kiểm soát tài khoản khi người dùng không thể đăng nhập hoặc đã mất các credential chính. | Quy trình recovery có xác minh danh tính và kiểm tra rủi ro. |
| **Factor replacement** | Thay authenticator đã mất/hỏng bằng authenticator mới. | Thu hồi passkey trên thiết bị mất, đăng ký khóa mới. |

Một recovery code có thể hỗ trợ account/factor recovery, nhưng việc nhập mã đó không tự động chứng minh người dùng đã đạt mọi mức assurance mà thao tác nhạy cảm yêu cầu. Policy phải xác định recovery evidence có thể khôi phục yếu tố nào, trong điều kiện nào và có cần xác thực mạnh bổ sung hay không.

## 3. Vì sao step-up có thể thất bại?

Không phải mọi lần step-up thất bại đều có nghĩa tài khoản bị tấn công. Có thể phân loại nguyên nhân:

| Nhóm nguyên nhân | Ví dụ | Cách xử lý ban đầu |
| --- | --- | --- |
| **Thiết bị không khả dụng** | Điện thoại mất, khóa bảo mật bị hỏng, thiết bị hết pin. | Kiểm tra authenticator dự phòng hoặc bắt đầu recovery đã phê duyệt. |
| **Authenticator lỗi kỹ thuật** | TOTP lệch thời gian, push không tới, browser không hỗ trợ WebAuthn. | Hiển thị hướng dẫn khắc phục an toàn; không hạ assurance tự động. |
| **Người dùng không còn kiểm soát yếu tố** | Đổi điện thoại, mất SIM, mất khóa bảo mật. | Xác minh qua phương thức độc lập đã đăng ký hoặc recovery process. |
| **Context không đạt policy** | Authentication quá cũ, ACR không phù hợp, thiếu claim cần thiết. | Yêu cầu IdP reauthenticate/step-up theo giao thức. |
| **Tín hiệu rủi ro** | Đăng nhập bất thường, thiết bị mới, nhiều lần thất bại. | Tạm dừng, đánh giá rủi ro và có thể chuyển sang xác minh tăng cường. |
| **Lỗi dịch vụ** | IdP, session store hoặc notification service tạm ngừng. | Báo lỗi tạm thời và cho phép thử lại có kiểm soát; không fail-open. |

Giao diện nên phân biệt lỗi kỹ thuật có thể thử lại với tình huống cần recovery. Không tiết lộ thông tin giúp attacker xác định yếu tố của tài khoản khác hoặc đoán trạng thái credential.

## 4. Mô hình ranh giới tin cậy

Step-up recovery thường liên quan ứng dụng RP, IdP, authenticator, recovery service, kênh thông báo và nhân viên hỗ trợ. Mỗi bên chỉ được phép thực hiện phần việc đã được phân quyền:

~~~mermaid
flowchart LR
    U["Người dùng"]
    RP["Ứng dụng / RP<br/>giữ hành động đang chờ"]
    IDP["IdP / Authenticator service<br/>xác minh step-up"]
    REC["Recovery service<br/>xác minh recovery evidence"]
    REG[("Credential registry<br/>factor status")]
    AUD[("Audit / risk signals")]
    HELP["Helpdesk / approver"]
    U <--> RP
    RP <--> IDP
    RP -->|"Tạo recovery transaction"| REC
    REC <--> REG
    REC --> AUD
    HELP -->|"Xác minh theo quy trình"| REC
    REC -->|"Kết quả recovery có ràng buộc"| RP
    IDP -->|"Authentication context đã xác minh"| RP
~~~

RP quyết định hành động nào đang chờ và mức assurance cần thiết. IdP xác minh credential và phát hành authentication context. Recovery service kiểm tra bằng chứng khôi phục, quản lý trạng thái yếu tố và ghi audit. Helpdesk chỉ được hỗ trợ theo quy trình đã xác minh, không thể tự tuyên bố người dùng đã đạt MFA.

Không tin các cờ do client tự gửi như step_up_passed=true, recovered=true hoặc device_trusted=true. Kết quả recovery phải được lưu và xác minh ở phía server, gắn với principal, tenant, session, purpose và transaction.

## 5. Giữ nguyên hành động đang chờ trong suốt recovery

Khi người dùng yêu cầu hành động nhạy cảm, ứng dụng nên tạo một giao dịch chờ có ràng buộc:

- Principal và tenant đã xác minh.
- Resource và action cụ thể.
- Nội dung hoặc tham số quan trọng của giao dịch, hoặc hash/phiên bản để phát hiện thay đổi.
- Session khởi tạo và mức assurance hiện tại.
- Assurance cần đạt, thời hạn và policy version.
- State/transaction ID ngẫu nhiên, một lần.

Ví dụ, nếu người dùng bắt đầu thay đổi tài khoản nhận lương rồi phải recovery passkey, hệ thống cần giữ chính xác yêu cầu thay đổi đang chờ. Sau recovery, người dùng phải xem lại thông tin nhận lương và xác nhận lại. Không để một giao dịch khác được thay thế vào cùng transaction chỉ vì recovery đã hoàn tất.

### Không tự thực hiện hành động sau recovery

Recovery chỉ khôi phục khả năng xác thực. Sau đó:

1. Xác minh recovery transaction đã hoàn tất.
2. Đăng ký hoặc khôi phục authenticator theo policy.
3. Tạo authentication event mới và xác minh context.
4. Thực hiện step-up riêng cho resource/action đang chờ.
5. Kiểm tra lại authorization và trạng thái dữ liệu ngay trước commit.

Điều này ngăn recovery bị dùng như một đường tắt để bỏ qua xác thực giao dịch.

## 6. Chọn phương thức recovery theo assurance

Không có một phương thức recovery phù hợp cho mọi tài khoản. Cần đánh giá mức tin cậy của bằng chứng, khả năng bị chiếm và hậu quả nếu attacker khôi phục thành công:

| Phương thức | Khi có thể phù hợp | Giới hạn cần đánh giá |
| --- | --- | --- |
| **Passkey/khóa bảo mật dự phòng** | Người dùng đã đăng ký nhiều authenticator độc lập. | Thiết bị dự phòng cũng có thể bị mất; phải kiểm tra credential còn active. |
| **Recovery code dùng một lần** | Người dùng đã tạo và lưu mã trước sự cố. | Là bearer secret; có thể bị sao chép hoặc lưu không an toàn. |
| **Authenticator khác đã đăng ký** | TOTP hoặc push dự phòng còn kiểm soát được. | Có thể cùng phụ thuộc một thiết bị/kênh hoặc không đạt mức chống phishing. |
| **Thiết bị quản lý bởi tổ chức** | Có MDM, device identity và quy trình xác minh nhân viên. | Thiết bị quản lý không tự chứng minh người đang cầm máy là chủ tài khoản. |
| **Helpdesk/administrator recovery** | Người dùng mất các yếu tố và cần quy trình có người phê duyệt. | Dễ bị social engineering, giả danh và lạm quyền nội bộ. |
| **Recovery có thời gian chờ** | Thay đổi rủi ro cao cần thời gian phát hiện và phản đối. | Không phù hợp cho mọi tình huống khẩn cấp; cần thông báo và ngoại lệ có kiểm soát. |

Policy cần đặt **assurance floor**: mức bảo đảm tối thiểu mà recovery phải đạt. Nếu bằng chứng hiện có không đáp ứng mức này, hệ thống có thể trì hoãn hoặc từ chối hành động nhạy cảm, đồng thời hướng người dùng tới kênh hỗ trợ chính thức.

## 7. Recovery bằng authenticator dự phòng

Đây thường là đường recovery ít phức tạp nhất nếu người dùng đã đăng ký trước một passkey hoặc khóa bảo mật khác:

1. Người dùng chọn phương thức dự phòng đã được liệt kê trong tài khoản.
2. Server kiểm tra credential ID thuộc đúng principal/tenant và trạng thái vẫn active.
3. Tạo challenge mới gắn với recovery/step-up transaction.
4. Người dùng thực hiện WebAuthn assertion hoặc bằng chứng tương ứng.
5. Server xác minh challenge, origin, RP ID, chữ ký và trạng thái credential.
6. Tạo authentication event mới; đánh giá assurance theo policy.
7. Nếu thiết bị cũ bị mất, thu hồi credential đó sau khi xác minh quyền và thông báo.

Không cho phép client gửi credential ID tùy ý rồi tự chọn tài khoản. Server phải lấy danh sách authenticator thuộc principal đã xác minh và kiểm tra bằng chứng mật mã.

## 8. Recovery bằng recovery code

Recovery code nên được tạo **trước khi người dùng mất yếu tố**, trong lúc thiết lập MFA hoặc quản lý bảo mật tài khoản:

- Mỗi mã có entropy đủ mạnh và dùng một lần.
- Server lưu verifier/hash phù hợp; không lưu mã bản rõ nếu không cần.
- Mã được hiển thị một lần và người dùng được hướng dẫn lưu ở nơi an toàn.
- Khi dùng, mã được tiêu thụ nguyên tử để ngăn hai request đồng thời sử dụng cùng mã.
- Bộ mã mới làm vô hiệu hóa bộ mã cũ.
- Việc sử dụng recovery code tạo audit event và thông báo chủ tài khoản.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant R as Recovery service
    participant D as Credential store
    U->>A: Chọn dùng recovery code
    A->>R: Gửi transaction ID + code
    R->>D: Tra verifier theo principal
    R->>R: Kiểm tra expiry, purpose, attempts
    R->>D: Consume code atomically
    D-->>R: Consume thành công
    R->>R: Ghi recovery event
    R-->>A: Recovery evidence hợp lệ
    A-->>U: Yêu cầu đăng ký/xác minh authenticator mới
~~~

Recovery code chỉ chứng minh người dùng có một bí mật dự phòng đã được cấp trước. Tùy policy, nó có thể cho phép bắt đầu factor replacement nhưng chưa chắc đủ để hoàn tất một hành động rủi ro cao. Không hiển thị code đã dùng, không gửi code qua email/chat hỗ trợ và không cho phép nhân viên helpdesk yêu cầu người dùng đọc mã.

## 9. Helpdesk và recovery có người phê duyệt

Khi người dùng mất mọi authenticator, có thể cần quy trình hỗ trợ. Đây là một ranh giới rủi ro cao vì attacker có thể giả danh nhân viên hoặc gây áp lực lên helpdesk.

Một quy trình có kiểm soát nên:

1. Người dùng mở yêu cầu qua cổng hỗ trợ chính thức hoặc kênh đã xác minh.
2. Helpdesk kiểm tra danh tính bằng các nguồn độc lập được tổ chức phê duyệt; không dựa chỉ vào email/điện thoại mà attacker có thể kiểm soát.
3. Yêu cầu có mã tham chiếu, principal, tenant, lý do và phạm vi recovery; không chứa secret.
4. Thao tác nhạy cảm cần phê duyệt độc lập/dual control nếu policy yêu cầu.
5. Recovery token hoặc invitation có thời hạn ngắn, ràng buộc đúng tài khoản, purpose và một lần.
6. Người dùng đăng ký authenticator mới và xác minh bằng chứng trước khi kích hoạt.
7. Hệ thống thu hồi yếu tố đã mất, session/token liên quan theo policy và gửi thông báo qua kênh độc lập.
8. Audit actor, approver, thời điểm và kết quả.

Helpdesk không được hỏi mật khẩu, OTP, recovery code hoặc private key. Không chấp nhận yêu cầu thay số điện thoại/email khôi phục chỉ dựa trên cuộc gọi đến. Nếu không đủ bằng chứng, cần từ chối hoặc chuyển sang quy trình xác minh cao hơn.

## 10. Thời gian chờ, thông báo và quyền phản đối

Với thay đổi có rủi ro cao, hệ thống có thể áp dụng thời gian chờ trước khi authenticator mới được dùng cho thao tác nhạy cảm. Thời gian chờ giúp chủ tài khoản phát hiện thay đổi không do mình yêu cầu:

- Gửi thông báo qua kênh đã đăng ký trước, không chỉ kênh vừa được thay đổi.
- Hiển thị thiết bị, thời gian và loại yếu tố được thêm/xóa ở mức không lộ bí mật.
- Cung cấp nút báo cáo/khóa recovery nếu người dùng không thực hiện yêu cầu.
- Có thời gian chờ hoặc hạn chế giao dịch nhạy cảm sau recovery theo risk policy.
- Không gửi recovery code, QR, secret hoặc token trong thông báo.

Thời gian chờ không thay thế xác minh danh tính. Nó là biện pháp giảm thiệt hại và tạo cơ hội phát hiện, cần cân nhắc trải nghiệm và tình huống khẩn cấp.

## 11. Session, token và credential sau recovery

Recovery có thể cho thấy credential hoặc session cũ đã bị mất kiểm soát. Hệ thống phải quyết định những trạng thái nào cần thu hồi:

| Tài sản | Hành động có thể cần |
| --- | --- |
| Authenticator bị mất | Đánh dấu revoked; không chấp nhận assertion/OTP mới từ credential đó. |
| Recovery code đã dùng | Consume một lần; không thể sử dụng lại. |
| Session đang hoạt động | Thu hồi session nghi bị chiếm hoặc tất cả session theo incident policy. |
| Refresh token family | Thu hồi khi có khả năng token bị lộ hoặc được tạo từ session bị chiếm. |
| Access token | Dùng TTL ngắn, introspection/denylist hoặc cơ chế revocation nếu cần chặn sớm. |
| Recovery transaction | Hoàn tất, hủy hoặc hết hạn; không tái sử dụng challenge. |
| Credential mới | Chỉ active sau khi xác minh; ghi nhận thời điểm và nguồn recovery. |

Thu hồi một passkey hoặc TOTP secret không tự động vô hiệu hóa mọi session/token đã được phát hành trước đó. Phải có quan hệ chính sách rõ giữa credential, authentication event, session và token.

Sau recovery, ứng dụng có thể yêu cầu đăng xuất các phiên cũ và tạo session mới. Nếu giữ lại một số phiên để tránh gián đoạn, cần xác định rõ lý do, giới hạn và cách kiểm tra rủi ro.

## 12. Ngăn hạ cấp assurance trong recovery

Một hệ thống có thể quảng bá passkey chống phishing nhưng lại cho phép người dùng chuyển sang email OTP hoặc câu hỏi bảo mật khi passkey thất bại. Attacker sẽ nhắm vào nhánh recovery yếu nhất.

Các nguyên tắc:

- Xác định assurance floor cho từng nhóm hành động và tài khoản.
- Không tự động hạ từ passkey/WebAuthn sang SMS/email chỉ vì authenticator lỗi.
- Recovery phải có bằng chứng độc lập đủ mạnh hoặc quy trình phê duyệt tương đương.
- Nếu recovery chỉ cho phép khôi phục yếu tố, yêu cầu đăng ký lại và step-up trước khi hành động ban đầu được thực hiện.
- Thay đổi phương thức recovery cần step-up và thông báo.
- Không để support override assurance mà không có dual control, lý do và audit.

Nếu không có recovery method đủ tin cậy, lựa chọn an toàn có thể là trì hoãn thao tác nhạy cảm và yêu cầu xác minh danh tính qua quy trình chính thức. Availability không nên được duy trì bằng cách âm thầm bỏ kiểm soát cốt lõi.

## 13. Các tấn công nhắm vào step-up recovery

| Rủi ro | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Recovery phishing** | Attacker gửi trang giả yêu cầu recovery code hoặc OTP. | Dùng domain/kênh chính thức, không yêu cầu đọc mã qua hỗ trợ, thông báo giao dịch. |
| **Helpdesk social engineering** | Attacker giả danh nhân viên để yêu cầu reset MFA. | Xác minh độc lập, dual control, audit và đào tạo hỗ trợ. |
| **SIM swap** | Attacker chiếm số điện thoại rồi dùng SMS recovery. | Không dùng SMS làm recovery duy nhất cho tài khoản assurance cao. |
| **Email account takeover** | Attacker chiếm hộp thư và đặt lại yếu tố. | Kênh độc lập, recovery assurance và không tin email mới vừa thay. |
| **Recovery code replay** | Mã đã dùng được gửi lại hoặc hai request cùng tiêu thụ. | One-time use, atomic consume và transaction binding. |
| **Transaction substitution** | Recovery hoàn tất nhưng action/resource chờ bị thay đổi. | Gắn recovery với transaction/action; xác nhận lại nội dung trước commit. |
| **Session hijack** | Attacker dùng session yếu để bắt đầu recovery. | Step-up hiện có, risk checks, session binding và notification. |
| **Factor downgrade** | Chuyển sang phương thức yếu hơn để vượt policy. | Assurance floor và phê duyệt thay đổi. |
| **Recovery token theft** | Token hỗ trợ hết hạn dài hoặc dùng nhiều lần. | TTL ngắn, purpose/account binding, one-time use và không đưa vào URL/log. |
| **Race condition** | Hai yêu cầu recovery đồng thời kích hoạt hai authenticator. | State transition nguyên tử, unique constraints và idempotency. |
| **Insider abuse** | Nhân viên hỗ trợ tự ý thêm yếu tố hoặc bỏ kiểm soát. | Least privilege, dual control, immutable audit và cảnh báo. |
| **Notification suppression** | Attacker đổi kênh thông báo trước rồi recovery. | Thông báo qua kênh cũ/độc lập và trì hoãn thay đổi nhạy cảm. |

## 14. Mã giả: recovery có ràng buộc và không bỏ qua step-up

Mã giả sau mô tả logic khái niệm, không thay thế triển khai mật mã hoặc identity proofing đã được kiểm thử:

~~~text
beginStepUpRecovery(session, pendingActionId):
    principal = requireActivePrincipalFromSession(session)
    action = loadPendingAction(pendingActionId)
    require action.principalId == principal.id
    require action.tenantId == principal.tenantId
    require action.status == "awaiting_step_up"
    require session.status == "active"
    require recoveryPolicyAllows(principal, action)

    tx = createOneTimeTransaction(
        principalId = principal.id,
        tenantId = principal.tenantId,
        sessionId = session.id,
        actionId = action.id,
        purpose = "step_up_recovery",
        requiredAssurance = action.requiredAssurance,
        expiresAt = shortExpiry()
    )
    return tx.publicReference

completeRecovery(txId, recoveryEvidence):
    tx = loadTransaction(txId)
    require tx.status == "pending"
    require tx.notExpired
    require recoveryEvidenceMatchesPrincipalAndPurpose(recoveryEvidence, tx)
    require riskPolicyAllows(recoveryEvidence, tx)
    require atomicallyConsumeRecoveryEvidence(recoveryEvidence)

    atomically:
        markRecoveryTransaction(tx, "verified")
        revokeLostFactorsIfConfirmed(tx.principalId)
        createFactorReplacementPendingIfRequired(tx.principalId)

    notifyThroughPreviouslyVerifiedChannel(tx.principalId)
    return recoveryVerifiedButActionStillPending()

resumeSensitiveAction(txId, newAuthenticationContext):
    tx = loadTransaction(txId)
    require tx.status == "verified"
    require tx.notExpired
    require newAuthenticationContext.issuerIsTrusted
    require newAuthenticationContext.principalId == tx.principalId
    require newAuthenticationContext.meets(tx.requiredAssurance)
    require newAuthenticationContext.isFresh
    require actionStillMatchesOriginalTransaction(tx.actionId)
    require currentAuthorizationAllows(tx.principalId, tx.actionId)

    atomically:
        markTransactionConsumed(tx)
        executeOrAuthorizePendingAction(tx.actionId)
    return success()
~~~

Trong triển khai thật:

- Recovery evidence phải được xác minh bằng verifier chuyên dụng; không tin cờ client gửi.
- atomicallyConsumeRecoveryEvidence phải chống hai request đồng thời dùng cùng mã.
- Transaction phải ràng buộc principal, tenant, session, action, resource, purpose và expiry.
- Không phát hành context assurance cao chỉ vì recovery code hợp lệ; cần xác minh authenticator mới hoặc policy recovery tương ứng.
- Action phải được kiểm tra lại nội dung, trạng thái và quyền ngay trước commit.
- Lỗi dependency không được chuyển trạng thái recovery thành verified hoặc action thành completed.

## 15. Tình huống thực tế: mất passkey trước giao dịch nhạy cảm

Một nhân viên đã đăng nhập ứng dụng tài chính bằng passkey buổi sáng. Buổi chiều họ yêu cầu thay đổi tài khoản nhận lương; policy yêu cầu passkey hoặc phương thức chống phishing tương đương trong vòng vài phút. Nhân viên làm mất điện thoại có passkey.

### Đánh giá

| Kiểm tra | Trạng thái | Quyết định |
| --- | --- | --- |
| RP session | Active | Có thể tiếp tục quy trình recovery, chưa đủ cho giao dịch. |
| Authentication context cũ | Passkey nhưng đã quá thời hạn | Không đạt freshness. |
| Passkey chính | Không còn kiểm soát được | Đánh dấu cần thu hồi sau xác minh. |
| Passkey dự phòng | Đã đăng ký trên khóa bảo mật riêng | Có thể dùng để xác thực recovery/step-up. |
| Recovery code | Có, chưa sử dụng | Dự phòng nếu khóa bảo mật không khả dụng theo policy. |
| Hành động đổi tài khoản | Đang pending | Không thực hiện trước step-up mới. |

### Luồng xử lý

1. Ứng dụng giữ yêu cầu đổi tài khoản ở trạng thái pending, gắn với principal và dữ liệu đã nhập.
2. Người dùng chọn passkey/khóa bảo mật dự phòng đã đăng ký.
3. Server tạo challenge mới và xác minh origin, RP ID, chữ ký và credential status.
4. Nếu đạt policy, hệ thống ghi authentication event mới; thu hồi passkey trên điện thoại bị mất theo xác nhận.
5. Ứng dụng xoay session ID, cập nhật context đã xác minh và yêu cầu xác nhận lại thông tin nhận lương.
6. Authorization policy được kiểm tra lại trước khi commit.
7. Hệ thống thông báo về yếu tố bị thu hồi và yếu tố dự phòng đã sử dụng.

Nếu không còn yếu tố dự phòng, nhân viên phải đi theo helpdesk recovery. Hệ thống có thể áp dụng thời gian chờ và hạn chế giao dịch nhạy cảm cho đến khi đăng ký passkey mới và đạt assurance policy. Việc này có thể gây chậm nhưng tránh biến mất thiết bị thành cơ hội cho attacker.

## 16. Kiểm thử step-up recovery

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người dùng có authenticator dự phòng active | Có thể xác minh và tiếp tục step-up theo policy. |
| Recovery code đúng, chưa dùng, còn hạn | Consume một lần; bắt đầu factor replacement hoặc recovery action được phép. |
| Recovery code đã dùng hoặc hết hạn | Từ chối; không thay đổi credential/session. |
| Hai request dùng cùng recovery code đồng thời | Chỉ một request consume thành công. |
| Client đổi principal/tenant/action ID | Server từ chối do transaction binding không khớp. |
| Recovery transaction hết hạn | Từ chối và yêu cầu bắt đầu lại. |
| Session bị thu hồi trong khi recovery đang chạy | Không hoàn tất recovery qua session cũ; yêu cầu xác minh lại theo policy. |
| Helpdesk không đủ bằng chứng hoặc thiếu approver | Không cấp recovery token/không kích hoạt yếu tố. |
| Recovery token bị replay | Từ chối; token đã consume hoặc hết hạn. |
| Passkey mới chưa hoàn tất registration | Không đánh dấu active và không đạt step-up. |
| Recovery hoàn tất nhưng action đã thay đổi | Yêu cầu xác nhận/giao dịch mới; không thực hiện action khác. |
| Tài khoản bị khóa trong quá trình recovery | Hủy hoặc đình chỉ transaction theo policy. |
| Notification service lỗi | Không làm yếu kiểm soát; retry/ghi nhận theo policy và không báo hoàn tất nếu notification là điều kiện bắt buộc. |
| Credential cũ bị mất đã revoke | Assertion/OTP từ credential cũ bị từ chối. |
| Session/token cũ còn tồn tại sau recovery | Thu hồi hoặc giới hạn theo chính sách đã định; không giả định tự hết hiệu lực. |

### Kiểm thử vận hành

- Kiểm tra thông báo tới kênh đã xác minh trước recovery.
- Kiểm tra dual control và audit của helpdesk.
- Kiểm tra không log recovery code, OTP, token, QR hoặc private key.
- Đo thời gian xử lý recovery, tỷ lệ thất bại và trường hợp nghi gian lận.
- Kiểm tra người dùng có thể hủy yêu cầu và biết cách liên hệ hỗ trợ chính thức.
- Kiểm tra policy không cho fallback yếu hơn assurance floor.

## 17. Checklist thiết kế step-up recovery

- [ ] Phân biệt step-up, reauthentication, factor replacement và account recovery.
- [ ] Giữ nguyên hành động nhạy cảm ở trạng thái pending; recovery không tự thực thi hành động.
- [ ] Ràng buộc transaction với principal, tenant, session, purpose, action/resource và expiry.
- [ ] Xác định assurance floor và phương thức recovery được phép cho từng nhóm hành động.
- [ ] Ưu tiên authenticator dự phòng đã đăng ký và còn active.
- [ ] Recovery code có entropy cao, one-time use, verifier được bảo vệ và consume nguyên tử.
- [ ] Helpdesk dùng xác minh độc lập, dual control và least privilege theo rủi ro.
- [ ] Recovery token ngắn hạn, purpose-bound, account-bound và không dùng trong URL/log.
- [ ] Có thông báo qua kênh đã xác minh trước đó và quyền phản đối thay đổi.
- [ ] Thu hồi authenticator bị mất và session/token liên quan theo policy.
- [ ] Yếu tố mới chỉ active sau khi xác minh registration; không dùng pending factor để step-up.
- [ ] Sau recovery, tạo authentication context mới và kiểm tra lại freshness/assurance.
- [ ] Kiểm tra lại authorization và dữ liệu action ngay trước commit.
- [ ] Không fallback âm thầm xuống SMS/email hoặc mật khẩu khi policy yêu cầu phương thức mạnh.
- [ ] Kiểm thử replay, CSRF, IDOR, race condition, social engineering và lỗi dịch vụ.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao step-up recovery không được tự động cho phép hành động đang chờ?

**Gợi ý:** Recovery khôi phục khả năng xác thực; hành động vẫn cần authentication context đạt policy và authorization được kiểm tra lại.

**Câu 2.** Recovery code hợp lệ có luôn tương đương passkey chống phishing không?

**Gợi ý:** Không. Recovery code là bearer secret dự phòng; policy phải xác định nó cho phép khôi phục yếu tố hay đạt assurance nào.

**Câu 3.** Vì sao helpdesk không nên chỉ dựa vào email hoặc số điện thoại người gọi cung cấp?

**Gợi ý:** Kênh có thể đã bị chiếm hoặc thay đổi; cần nguồn xác minh độc lập, phê duyệt và audit.

**Câu 4.** Vì sao phải thông báo qua kênh đã xác minh trước recovery?

**Gợi ý:** Nếu attacker vừa thay kênh liên hệ, thông báo tới kênh mới sẽ không giúp chủ tài khoản phát hiện hành vi trái phép.

**Câu 5.** Khi mất passkey, có nên chuyển tự động sang SMS OTP?

**Gợi ý:** Không nếu SMS không đáp ứng assurance floor. Cần yếu tố dự phòng hoặc recovery flow được phê duyệt.

**Câu 6.** Vì sao recovery transaction cần gắn với action/resource?

**Gợi ý:** Ngăn transaction substitution, nơi recovery cho một hành động lại bị dùng để thực hiện hành động khác.

**Câu 7.** Thu hồi passkey bị mất có tự động vô hiệu hóa mọi session đã tạo trước đó không?

**Gợi ý:** Không. Credential, session và token có vòng đời riêng; cần policy thu hồi liên kết và kiểm tra ở verifier.

## 19. Ghi nhớ

**Step-up recovery khôi phục khả năng đạt mức xác thực cần thiết khi authenticator không khả dụng, nhưng không phải đường tắt bỏ qua step-up.** Hệ thống cần giữ hành động nhạy cảm ở trạng thái pending, ràng buộc recovery với đúng principal/session/action, dùng yếu tố dự phòng hoặc recovery evidence đủ tin cậy, chống replay và social engineering, rồi đăng ký/xác minh authenticator mới. Sau recovery, ứng dụng phải nhận authentication context mới, đánh giá freshness/assurance và kiểm tra lại authorization trước khi thực hiện hành động. Recovery an toàn còn bao gồm thu hồi credential bị mất, quản lý session/token liên quan, thông báo qua kênh độc lập và audit đầy đủ.
