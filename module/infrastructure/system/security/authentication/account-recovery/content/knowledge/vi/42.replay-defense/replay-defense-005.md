# Device replay attempt — Phát hiện và ngăn phát lại từ thiết bị

## 1. Device replay attempt là gì?

Trong khôi phục tài khoản, **device replay attempt** là nỗ lực sử dụng lại một bằng chứng hoặc yêu cầu đã được tạo trước đó từ một thiết bị, nhằm làm máy chủ chấp nhận lại một thao tác. Dữ liệu bị phát lại có thể là challenge response, recovery token, yêu cầu thay authenticator hoặc một thông điệp chứng minh quyền sử dụng thiết bị.

Từ “device” mô tả bối cảnh của yêu cầu, không có nghĩa máy chủ luôn biết chắc thiết bị vật lý nào đang gửi nó. Hai thiết bị có thể gửi cùng một `deviceId`; một thiết bị cũng có thể thay đổi IP, trình duyệt hoặc cookie.

NIST mô tả replay resistance là khả năng ngăn thành công việc ghi lại rồi phát lại một thông điệp xác thực trước đó. Challenge hoặc nonce giúp chứng minh tính mới của giao dịch; bảo vệ này cần được xem xét ngoài việc sử dụng kênh truyền an toàn. [NIST SP 800-63B-4, Replay Resistance](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#replay-resistance)

Bài học sử dụng một dịch vụ khôi phục tài khoản cho người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Tình huống chính là người dùng có một yêu cầu khôi phục đang hoạt động và cần chứng minh quyền thực hiện một thay đổi nhạy cảm.

Mục tiêu của thiết kế là: **một bằng chứng chỉ cho phép đúng thao tác đã được ủy quyền, trong đúng ngữ cảnh và số lần đã quy định**.

## 2. Nhìn vào bằng chứng bị dùng lại, không chỉ nhìn vào thiết bị

### 2.1. Ví dụ hai thiết bị gửi cùng một yêu cầu

An bắt đầu yêu cầu khôi phục `R-17` trên thiết bị A. Máy chủ tạo challenge `C-17` cho một bước xác minh. Thiết bị A gửi bằng chứng `P-17`, máy chủ chấp nhận và chuyển yêu cầu sang bước tiếp theo.

Sau đó, một bên khác gửi lại `P-17` từ thiết bị B:

```text
Thiết bị A                    Máy chủ
    |--- bằng chứng P-17 ------->|
    |                           | xác minh hợp lệ
    |                           | tiêu thụ challenge C-17
    |<-- bước xác minh hoàn tất -|

Thiết bị B                    Máy chủ
    |--- cùng bằng chứng P-17 -->|
    |                           | challenge đã được tiêu thụ
    |<-- từ chối phát lại -------|
```

Máy chủ phải từ chối lần sử dụng thứ hai kể cả khi B sao chép IP hiển thị, User-Agent hoặc `deviceId` của A. Quyết định quan trọng nằm ở trạng thái bằng chứng phía máy chủ.

### 2.2. Những tình huống dễ bị gọi chung là replay

| Tình huống | Bản chất cần phân biệt | Kiểm soát phù hợp |
| --- | --- | --- |
| Gửi lại bằng chứng đã được chấp nhận | Phát lại một bằng chứng đã dùng | Kiểm tra trạng thái dùng một lần |
| Hai yêu cầu cùng sử dụng một token chưa dùng | Tranh chấp lần sử dụng đầu tiên | Tiêu thụ nguyên tử cùng thay đổi được cấp phép |
| Đánh cắp token chưa dùng rồi sử dụng trước nạn nhân | Chiếm quyền sử dụng bearer token | Bảo vệ token, ràng buộc phù hợp và kiểm soát recovery |
| Đánh cắp khóa riêng rồi tạo chữ ký mới | Giả mạo bằng credential bị xâm phạm | Thu hồi khóa và xử lý sự cố credential |
| Gửi lại sau khi trình duyệt không nhận được phản hồi | Có thể là retry hợp lệ | Trạng thái thao tác và cơ chế idempotency có ủy quyền |
| Đổi mạng khi tiếp tục yêu cầu hợp lệ | Thay đổi tín hiệu môi trường | Đánh giá rủi ro; không tự kết luận replay |

Một token chỉ dùng một lần không bảo đảm người dùng hợp pháp sẽ là người sử dụng đầu tiên. Một chữ ký mới cũng không chứng minh khóa riêng chưa từng bị sao chép.

## 3. Device ID, fingerprint và IP cung cấp mức tin cậy nào?

### 3.1. Định danh tự khai không phải bằng chứng sở hữu

Ví dụ client gửi:

```http
X-Device-Id: browser-123
User-Agent: ExampleBrowser
```

Nếu backend chỉ so sánh hai chuỗi này với dữ liệu đã lưu, người có bản sao có thể gửi lại chúng. Việc hash một chuỗi do client tự khai không biến chuỗi đó thành bằng chứng mật mã.

Tương tự, một cookie “thiết bị được ghi nhớ” có thể vẫn là bearer credential: ai có giá trị cookie thì có khả năng sử dụng nó, trừ khi giao thức còn yêu cầu bằng chứng khác.

Có thể xem các thông tin trên là tín hiệu để:

- Phát hiện thay đổi đáng chú ý giữa các lần sử dụng.
- Điều chỉnh mức xác minh cần thiết.
- Liên kết sự kiện phục vụ điều tra trong phạm vi lưu trữ phù hợp.
- Thông báo cho người dùng về hoạt động đáng ngờ.

Không nên dùng chúng làm căn cứ duy nhất để cho phép thay MFA hoặc đăng ký passkey mới.

### 3.2. Thay đổi môi trường không đồng nghĩa với kẻ tấn công

Người dùng có thể chuyển từ Wi-Fi sang mạng di động, cập nhật trình duyệt hoặc sử dụng thiết bị mới sau khi mất điện thoại. Trong account recovery, việc xuất hiện thiết bị mới thậm chí là một tình huống dự kiến.

OWASP trình bày việc theo dõi IP, User-Agent và thuộc tính client để phát hiện bất thường của session. Đây là dữ liệu hỗ trợ kiểm soát session; cách diễn giải và phản ứng cần phù hợp với mô hình sử dụng thực tế. [OWASP, Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#binding-the-session-id-to-other-user-properties)

Trong thiết kế minh họa, dịch vụ không khóa vĩnh viễn tài khoản chỉ vì IP thay đổi. Một lần dùng lại challenge đã tiêu thụ được xử lý khác với một lần đổi IP nhưng có bằng chứng mới, hợp lệ.

## 4. Bằng chứng sở hữu khóa cần được gắn với ngữ cảnh đúng

Nếu thiết bị có một credential đã đăng ký, máy chủ có thể yêu cầu bằng chứng sở hữu khóa riêng tương ứng. Tuy nhiên, một chữ ký hợp lệ chỉ có ý nghĩa khi máy chủ biết:

- Khóa nào được phép sử dụng.
- Khóa đó thuộc tài khoản nào.
- Bằng chứng dành cho yêu cầu và thao tác nào.
- Challenge nào đang được xác minh.
- Credential và yêu cầu còn hiệu lực hay không.

WebAuthn là một lựa chọn khi sử dụng credential phù hợp. Quy trình xác minh assertion của W3C có các kiểm tra về challenge, origin, RP ID, chữ ký và các cờ liên quan. Không thể thay cả quy trình bằng việc kiểm tra riêng chữ ký. [W3C WebAuthn Level 2, Verifying an Authentication Assertion](https://www.w3.org/TR/webauthn-2/#sctn-verifying-assertion)

### 4.1. Bản ghi challenge minh họa

Một dịch vụ có thể lưu trạng thái tương tự:

```text
RecoveryChallenge:
    challenge_id
    challenge_value
    account_id
    recovery_request_id
    purpose
    expected_credential_id
    expected_recovery_session_id
    account_security_version
    verification_context_revision
    expires_at
    state
    consumed_at
```

Đây là mô hình ứng dụng đề xuất, không phải schema bắt buộc của WebAuthn.

| Ràng buộc | Ngăn nhầm lẫn hoặc lạm dụng nào? |
| --- | --- |
| `account_id` | Dùng bằng chứng của tài khoản A cho tài khoản B |
| `recovery_request_id` | Dùng bằng chứng của hồ sơ recovery cũ cho hồ sơ mới |
| `purpose` | Dùng bằng chứng của thao tác ít nhạy cảm để thay authenticator |
| Credential dự kiến | Tự gửi một khóa công khai khác để được chấp nhận |
| Recovery session dự kiến | Chuyển bằng chứng sang phiên khác trái với chính sách |
| Phiên bản bảo mật tài khoản | Tiếp tục dùng bằng chứng thuộc trạng thái đã bị thu hồi |
| Hạn dùng và trạng thái | Dùng challenge quá hạn hoặc đã tiêu thụ |

Các ràng buộc nghiệp vụ có thể được duy trì bằng liên kết challenge với bản ghi phía máy chủ. Không phải mọi trường trong bảng đều cần được đưa trực tiếp vào một thông điệp ký mới do ứng dụng tự sáng tạo.

### 4.2. Không nhận khóa mới làm bằng chứng về chủ tài khoản

Một lỗi thiết kế là cho người yêu cầu tự gửi khóa công khai, xác minh chữ ký bằng chính khóa đó rồi kết luận “đây là thiết bị của chủ tài khoản”.

Điều này chỉ chứng minh người gửi kiểm soát khóa mà họ vừa cung cấp. Khóa mới cần được gắn với tài khoản thông qua một quyết định recovery hoặc một bước xác thực đã được ủy quyền.

Nếu người dùng mất tất cả credential cũ, dịch vụ cần chính sách recovery riêng. Yêu cầu chứng minh quyền sở hữu một thiết bị không còn sử dụng được sẽ không giải quyết được tình huống đó.

## 5. Tiêu thụ bằng chứng phải nguyên tử

### 5.1. Cách kiểm tra rồi cập nhật có thể bị tranh chấp

Một triển khai ngây thơ:

```text
if challenge.state == PENDING:
    performSensitiveChange()
    challenge.state = CONSUMED
```

Nếu hai máy chủ cùng đọc `PENDING` trước khi một bên cập nhật, cả hai có thể thực hiện thay đổi. Thêm kiểm tra `deviceId` không loại bỏ cuộc đua này.

Đối với thao tác nhạy cảm, cần bảo đảm việc chuyển trạng thái và thay đổi được cấp phép có cùng ranh giới nhất quán.

### 5.2. Giả mã cho nhánh xác minh bằng credential thiết bị

Ví dụ dưới đây áp dụng cho một nhánh recovery có credential đã được phép sử dụng. Hàm xác minh giao thức được coi là thành phần đã triển khai đầy đủ; đoạn giả mã chỉ thể hiện cách phối hợp trạng thái ứng dụng.

```text
completeDeviceVerification(requestId, clientResponse, recoverySession):
    snapshot = loadVerificationContext(requestId)

    verified = protocolVerifier.verify(
        response = clientResponse,
        expectedContext = snapshot
    )
    require verified.success

    transaction:
        account = lockAccount(snapshot.accountId)
        request = lockRecoveryRequest(requestId)
        challenge = lockChallenge(snapshot.challengeId)
        credential = loadCredentialUnderAccountLock(snapshot.credentialId)

        require recoverySession.isActive()
        require recoverySession.accountId == account.id
        require recoverySession.id == request.recoverySessionId
        require recoverySession.securityVersion == account.securityVersion

        require request.accountId == account.id
        require request.state == WAITING_FOR_DEVICE_PROOF
        require request.verificationRevision == snapshot.revision

        require challenge.recoveryRequestId == request.id
        require challenge.accountId == account.id
        require challenge.purpose == VERIFY_RECOVERY_DEVICE
        require challenge.expectedCredentialId == verified.credentialId
        require challenge.accountSecurityVersion == account.securityVersion
        require challenge.expiresAt > trustedServerTime()
        require challenge.state == PENDING

        require credential.accountId == account.id
        require credential.isActive()

        challenge.state = CONSUMED
        challenge.consumedAt = trustedServerTime()

        request.state = DEVICE_PROOF_ACCEPTED
        operation = recordCompletedVerification(request, challenge)
        appendAuditEventWithoutSecrets(operation)

    return operation.reference
```

Trong mô hình này:

- Kết quả `verified` được backend tạo từ việc xác minh, không phải cờ do client gửi.
- Nếu ngữ cảnh thay đổi trong lúc xác minh mật mã, revision không còn khớp và yêu cầu bị từ chối.
- Hai yêu cầu đồng thời bị tuần tự hóa khi truy cập trạng thái challenge.
- Một yêu cầu đến sau phải thấy `CONSUMED`, kể cả khi nó đến từ thiết bị có vẻ quen thuộc.
- Kết quả mới chỉ hoàn tất một bước xác minh. Nó không mặc nhiên cấp session đầy đủ hay cho phép thay mọi credential.

Các thao tác thu hồi credential hoặc tăng phiên bản bảo mật cũng phải tuân theo cơ chế khóa tương ứng của ứng dụng. Nếu không, việc đọc `isActive` có thể vẫn tranh chấp với thu hồi.

Đối với hệ thống nhiều vùng hoặc nhiều node, cần chọn nơi quyết định tiêu thụ có tính nhất quán phù hợp. Một cache cục bộ riêng trên từng node không đủ làm nguồn chuẩn cho cùng một challenge.

### 5.3. Thay đổi ngoài giao dịch cơ sở dữ liệu

Nếu bước tiếp theo cần gọi một dịch vụ khác, không nên giả định giao dịch cơ sở dữ liệu tự làm lời gọi đó nguyên tử.

Một thiết kế có thể ghi sự kiện cần xử lý vào outbox trong cùng giao dịch, sau đó worker xử lý bằng khóa nghiệp vụ để tránh lặp tác động. Trạng thái challenge và kết quả thao tác cần phân biệt rõ “đã nhận bằng chứng”, “đang thực hiện” và “đã hoàn tất”.

Đây là lựa chọn thiết kế để phối hợp tác động, không phải lý do để cho phép cùng một bằng chứng tạo thêm yêu cầu recovery.

## 6. Hạn dùng, chữ ký và cache không thay thế trạng thái dùng một lần

### 6.1. Token còn hạn vẫn có thể đã dùng

Kiểm tra `expires_at` chỉ trả lời token còn nằm trong cửa sổ thời gian cho phép hay không. Một token còn hạn nhưng đã được tiêu thụ vẫn phải bị từ chối theo chính sách dùng một lần.

OWASP khuyến nghị token đặt lại mật khẩu có hạn dùng, chỉ dùng một lần, được sinh an toàn và lưu trữ an toàn. Những thuộc tính này cần được phối hợp, không chọn một thuộc tính để thay cho những thuộc tính còn lại. [OWASP, Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

### 6.2. Chữ ký hợp lệ không chứng minh thông điệp chưa được dùng

Chữ ký của một thông điệp cũ có thể vẫn xác minh thành công. Tính mới và việc đã được tiêu thụ phải được kiểm tra trong ngữ cảnh giao thức cùng trạng thái nghiệp vụ.

Tương tự, một JWT có chữ ký đúng và chưa hết hạn có thể vẫn bị phát lại nếu endpoint chấp nhận nó nhiều lần cho một tác vụ lẽ ra chỉ được phép thực hiện một lần.

### 6.3. Không mất trạng thái chống replay khi đổi node

Giả sử yêu cầu đầu đến node A và yêu cầu sau đến node B. Nếu mỗi node chỉ giữ một tập `usedChallenges` trong bộ nhớ riêng, B có thể không biết A đã xử lý.

Trong thiết kế minh họa, nguồn trạng thái dùng một lần phải có hiệu lực với mọi node có khả năng chấp nhận cùng bằng chứng. Khi nguồn trạng thái này không khả dụng, endpoint thay credential cần dừng thao tác nhạy cảm thay vì tự chuyển sang chấp nhận không kiểm tra.

Không ghi nhận sự cố hạ tầng là bằng chứng chắc chắn người dùng đang tấn công. Hệ thống cần phân biệt lỗi phụ thuộc với một bằng chứng thực sự đã dùng.

## 7. Retry hợp lệ cần được xử lý như thế nào?

### 7.1. Không có phản hồi không có nghĩa thao tác chưa xảy ra

Thiết bị A gửi bằng chứng, máy chủ commit thành công nhưng phản hồi bị mất. A gửi lại cùng dữ liệu.

Nếu dịch vụ chỉ nhìn vào request trùng nhau và kết luận “thiết bị độc hại”, người dùng có thể bị xử lý sai. Nếu dịch vụ lại thực hiện thay đổi lần nữa, nó đã bỏ qua yêu cầu dùng một lần.

Một cách giải quyết trong mô hình của bài:

1. Mỗi thao tác có mã tham chiếu để theo dõi.
2. Kết quả đã commit được lưu lại.
3. Client truy vấn trạng thái qua một endpoint có kiểm tra quyền độc lập.
4. Endpoint đó trả trạng thái phù hợp, không thực hiện lại thao tác bằng chứng cũ.

Bằng chứng đã dùng không tự trở thành quyền đọc kết quả nhạy cảm. Người gọi vẫn cần session hoặc quyền recovery thích hợp để xem trạng thái.

### 7.2. Idempotency không phải bỏ qua xác thực

Nếu sử dụng idempotency key, dịch vụ cần gắn nó với tài khoản, loại thao tác và nội dung yêu cầu. Cùng key nhưng khác nội dung không được xem là cùng một hành động.

Không dùng quy tắc:

```text
đã thấy idempotency key
    -> bỏ qua mọi xác thực
    -> trả lại session token cũ
```

Đặc biệt, việc trả lại token truy cập cho bất kỳ người nào biết một mã tham chiếu có thể tạo thêm đường chiếm đoạt. Trạng thái thao tác và credential cho phép truy cập là hai loại dữ liệu có quyền sử dụng khác nhau.

## 8. Nếu hệ thống dùng token ràng buộc khóa

Trong một hệ thống OAuth phù hợp, DPoP ràng buộc token với khóa công khai và yêu cầu bằng chứng sở hữu khóa cho request. Việc kiểm tra bao gồm ngữ cảnh request và ràng buộc khóa/token; vẫn cần chống dùng lại proof trong cửa sổ chấp nhận. Chỉ thêm header có tên `DPoP` không tạo ra bảo vệ này. [RFC 9449, DPoP Proof Replay](https://www.rfc-editor.org/rfc/rfc9449.html#section-11.1)

Cần phân biệt:

- **Ràng buộc token với khóa:** có token nhưng thiếu khóa thì không đủ tạo bằng chứng mới hợp lệ.
- **Chống phát lại proof:** không cho một proof đã chấp nhận được dùng lại trái chính sách.
- **Ủy quyền recovery:** quyết định người sở hữu token và khóa được làm gì với tài khoản.

DPoP không mặc nhiên ký toàn bộ body của request và không tự bảo đảm một tác vụ nghiệp vụ chỉ xảy ra một lần. Không nên tự áp dụng quy tắc “mọi nonce DPoP chỉ được dùng một lần” như thể đó là yêu cầu của chuẩn; RFC cho phép sử dụng lại nonce trong những điều kiện kiểm soát proof phù hợp.

Đối với ứng dụng không dùng OAuth, ví dụ này giúp hiểu sự khác biệt giữa sở hữu token và sở hữu khóa. Nó không yêu cầu thêm một giao thức mới vào mọi luồng khôi phục.

## 9. Thu hồi thiết bị phải làm thay đổi khả năng chấp nhận bằng chứng

Người dùng có thể báo mất thiết bị sau khi challenge được tạo nhưng trước khi bằng chứng được gửi về. Nếu máy chủ chỉ kiểm tra chữ ký, credential của thiết bị mất vẫn có thể được chấp nhận.

Một thiết kế có thể sử dụng phiên bản bảo mật tài khoản để làm mất hiệu lực các bằng chứng thuộc trạng thái cũ:

```text
Lúc tạo challenge:
    account.securityVersion = 8
    challenge.accountSecurityVersion = 8

Sau sự kiện thu hồi:
    account.securityVersion = 9

Lúc hoàn tất xác minh:
    8 != 9
    -> yêu cầu một quy trình còn hợp lệ theo trạng thái mới
```

Phạm vi tăng phiên bản và thu hồi cần được thiết kế rõ. Không phải mọi thay đổi vô hại đều cần hủy toàn bộ phiên; ngược lại, việc đã đánh dấu thiết bị mất nhưng vẫn chấp nhận mọi session và bằng chứng của nó sẽ làm việc thu hồi thiếu hiệu lực.

Nếu mọi thiết bị cũ đều đã bị mất hoặc thu hồi, người dùng cần chuyển sang nhánh recovery phù hợp, thay vì được hướng dẫn dùng lại credential đã vô hiệu hóa.

## 10. Ghi nhận và phản ứng khi có replay attempt

### 10.1. Phân biệt lý do từ chối

Ví dụ các mã sự kiện nội bộ:

| Mã sự kiện minh họa | Ý nghĩa |
| --- | --- |
| `PROOF_ALREADY_CONSUMED` | Bằng chứng hợp lệ về cấu trúc nhưng trạng thái đã được dùng |
| `PROOF_CONTEXT_MISMATCH` | Sai yêu cầu, mục đích, session hoặc ngữ cảnh xác minh |
| `PROOF_EXPIRED` | Đã quá hạn theo thời gian tin cậy |
| `DEVICE_CREDENTIAL_REVOKED` | Credential thiết bị không còn được phép sử dụng |
| `ACCOUNT_SECURITY_VERSION_CHANGED` | Trạng thái bảo mật đã thay đổi |
| `REPLAY_STATE_UNAVAILABLE` | Không kiểm tra được trạng thái vì lỗi phụ thuộc |

Đây là tên minh họa cho audit và vận hành, không phải nội dung bắt buộc trả nguyên văn cho client.

Có thể ghi mã yêu cầu nội bộ, loại thao tác, thời điểm, kết quả và tham chiếu credential đã giảm thiểu dữ liệu. Không ghi recovery token, cookie, khóa riêng hoặc toàn bộ bằng chứng nhạy cảm vào log.

### 10.2. Không biến replay defense thành công cụ khóa tài khoản

Kẻ tấn công có thể cố tình gửi yêu cầu trùng hoặc dữ liệu sai. Nếu mỗi lần bị từ chối đều khóa toàn bộ tài khoản, hệ thống sẽ tạo ra một cơ chế gây gián đoạn cho nạn nhân.

Phản ứng nên dựa vào loại sự kiện và mức rủi ro:

- Từ chối bằng chứng đã dùng.
- Giới hạn tần suất theo nhiều chiều phù hợp.
- Tăng mức xác minh cho hoạt động đáng ngờ.
- Thông báo hoặc chuyển xử lý sự cố khi có bằng chứng chiếm đoạt.
- Giữ một lộ trình recovery có kiểm soát cho người dùng hợp pháp.

Việc nhận diện “thiết bị lạ” hỗ trợ quyết định, nhưng không thay thế điều kiện chấp nhận bằng chứng.

## 11. Tình huống vận dụng

**Tình huống A — Cùng device ID, khác bên gửi:** một người sao chép `deviceId` của An và gửi lại challenge response đã được tiêu thụ. Dịch vụ từ chối vì trạng thái challenge, không cho phép vượt qua chỉ vì device ID khớp.

**Tình huống B — Đổi mạng, bằng chứng còn hợp lệ:** An đổi sang mạng di động trong khi tiếp tục recovery. Dịch vụ đánh giá thay đổi mạng nhưng vẫn kiểm tra bằng chứng và trạng thái đúng quy trình. IP mới không tự chứng minh phát lại.

**Tình huống C — Hai request song song:** hai node cùng nhận một bằng chứng cho cùng yêu cầu. Chỉ một giao dịch được chuyển challenge từ `PENDING` sang `CONSUMED`; giao dịch còn lại không tạo thêm quyền.

**Tình huống D — Mất phản hồi sau commit:** An không nhận được phản hồi và bấm lại. Dịch vụ không thực hiện lại bước nhạy cảm; An có thể xem kết quả qua luồng kiểm tra trạng thái có ủy quyền.

**Tình huống E — Khóa thiết bị đã bị lộ:** kẻ tấn công tạo được một chữ ký mới bằng khóa bị đánh cắp. Đây không chỉ là bài toán phát lại. Dịch vụ cần thu hồi credential và xử lý session liên quan, thay vì trông chờ việc chặn challenge cũ.

## 12. Câu hỏi tự kiểm tra

1. Vì sao hai yêu cầu có cùng `deviceId` chưa đủ chứng minh chúng đến từ cùng một thiết bị?
2. Một token còn hạn nhưng đã dùng cần được xử lý thế nào?
3. Vì sao chữ ký hợp lệ vẫn cần kiểm tra trạng thái challenge và credential?
4. Điều gì xảy ra nếu hai node chỉ giữ danh sách bằng chứng đã dùng trong bộ nhớ riêng?
5. Làm thế nào để người dùng biết kết quả sau khi phản hồi bị mất mà không thực hiện lại thao tác?
6. Một credential bị sao chép có thể tạo proof mới khác với việc phát lại proof cũ như thế nào?
7. Khi người dùng mất mọi thiết bị xác thực, vì sao cần một nhánh recovery riêng?

Điểm cốt lõi là quản lý quyền sử dụng bằng chứng ở phía máy chủ. Tín hiệu thiết bị giúp hiểu bối cảnh; ràng buộc ngữ cảnh, trạng thái dùng một lần, tính nguyên tử và thu hồi credential mới quyết định một yêu cầu khôi phục có được chấp nhận hay không.
