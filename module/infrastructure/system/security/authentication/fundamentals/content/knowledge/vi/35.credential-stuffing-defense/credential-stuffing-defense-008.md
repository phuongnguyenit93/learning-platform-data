# Lockout trade-off — Cân bằng giữa chống đoán credential và nguy cơ khóa tài khoản

## 1. Lockout trade-off là gì?

**Account lockout** là cơ chế tạm ngăn một tài khoản thực hiện một số lần đăng nhập sau khi phát hiện nhiều lần xác thực thất bại. Mục tiêu là làm chậm brute force và một số hình thức đoán mật khẩu. Tuy nhiên, nếu chỉ cần gửi mật khẩu sai là có thể khóa tài khoản, attacker có thể cố tình gây khóa tài khoản của người khác. Đây là **account lockout denial of service (DoS)**.

Vì vậy, thiết kế lockout luôn có một đánh đổi: kiểm soát càng cứng có thể làm attacker khó thử credential hơn, nhưng cũng có thể khiến người dùng hợp lệ mất quyền truy cập. Kiểm soát quá lỏng lại cho phép attacker thử nhiều mật khẩu hoặc dùng credential bị lộ. Bài toán không phải chọn một ngưỡng khóa duy nhất, mà là phối hợp throttling, phát hiện rủi ro, MFA, bảo vệ session và recovery sao cho phù hợp với loại tấn công.

Ví dụ: cổng nhân viên khóa tài khoản sau năm lần nhập sai mật khẩu. Attacker biết địa chỉ email của giám đốc và cố tình gửi năm request sai. Tài khoản bị khóa dù giám đốc chưa hề tương tác với hệ thống. Nếu attacker lặp lại với hàng trăm nhân viên, cơ chế chống brute force trở thành công cụ gây gián đoạn dịch vụ.

Trong chương **Chống đoán credential** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này kết nối mật khẩu, MFA, passkey, credential stuffing, session, token và account recovery. Người học cần mô hình hóa ranh giới tin cậy và cân bằng khả năng chống phishing, replay, lạm dụng đăng nhập với tính sẵn sàng của tài khoản.

## 2. Phân biệt brute force, password spraying và credential stuffing

Ba kiểu tấn công có đặc điểm khác nhau, vì vậy một bộ đếm thất bại đơn giản có thể bỏ sót:

| Kiểu tấn công | Cách attacker thử | Vì sao lockout đơn giản có thể thất bại |
| --- | --- | --- |
| **Brute force** | Thử nhiều mật khẩu cho một tài khoản hoặc một số ít tài khoản. | Bộ đếm theo tài khoản có thể phát hiện, nhưng attacker cũng có thể cố tình khóa nạn nhân. |
| **Password spraying** | Thử một vài mật khẩu phổ biến trên nhiều tài khoản. | Mỗi tài khoản chỉ có ít lần sai nên không chạm ngưỡng lockout. |
| **Credential stuffing** | Dùng cặp username/password bị lộ từ dịch vụ khác. | Mỗi tài khoản có thể chỉ nhận một lần thử; nhiều cặp có thể được phân tán qua nhiều IP. |

Credential stuffing đặc biệt nguy hiểm vì attacker không nhất thiết đoán mật khẩu. Họ thử thông tin đăng nhập đã từng hợp lệ ở một dịch vụ khác. Nếu người dùng tái sử dụng mật khẩu, một lần thử có thể thành công ngay.

Lockout có thể làm chậm brute force tập trung, nhưng không thay thế mật khẩu duy nhất, kiểm tra mật khẩu bị lộ, MFA chống phishing, phát hiện đăng nhập bất thường và kiểm soát session.

## 3. Hard lockout và rủi ro DoS

**Hard lockout** thường khóa tài khoản sau một số lần thất bại cố định, buộc người dùng chờ hoặc liên hệ hỗ trợ. Cách này dễ hiểu và có thể hữu ích trong một số môi trường được kiểm soát, nhưng tạo một bề mặt DoS nếu attacker biết identifier của nạn nhân.

Các rủi ro:

- Attacker có thể khóa tài khoản mà không cần biết mật khẩu.
- Tài khoản đặc quyền hoặc tài khoản hỗ trợ khách hàng có thể bị khóa có chủ đích.
- Password spraying có thể gây khóa hàng loạt khi ngưỡng thấp.
- Người dùng hợp lệ có thể nhập sai do bàn phím, thiết bị hoặc password manager.
- Helpdesk và recovery bị quá tải khi nhiều tài khoản bị khóa đồng thời.
- Nếu thông báo cho biết rõ tài khoản bị khóa, hệ thống có thể tiết lộ trạng thái tài khoản.

### Khi nào hard lockout có thể phù hợp?

Hard lockout có thể được dùng như một lớp kiểm soát trong môi trường có danh tính đã xác minh, kênh hỗ trợ đáng tin và quy trình mở khóa an toàn. Ví dụ, một hệ thống nội bộ có thiết bị quản lý và helpdesk trực 24/7 có thể áp dụng suspension tạm thời cho tài khoản đặc quyền khi phát hiện dấu hiệu compromise rõ ràng.

Ngay cả trong trường hợp đó, cần phân biệt khóa do policy với lỗi credential thông thường, có audit, thông báo qua kênh độc lập và quy trình mở khóa có xác minh. Không nên dùng hard lockout làm biện pháp duy nhất chống mọi kiểu đoán credential.

## 4. Soft lockout, throttling và progressive delay

Thay vì khóa cứng ngay, hệ thống có thể tăng dần chi phí của các lần thử:

- **Rate limiting:** giới hạn số request trong một khoảng thời gian.
- **Throttling:** giảm tốc độ hoặc giới hạn hoạt động khi vượt ngưỡng.
- **Progressive delay:** tăng thời gian chờ sau các lần thất bại liên tiếp.
- **Risk hold:** tạm giữ yêu cầu có rủi ro cao để xác minh thêm.
- **Challenge:** yêu cầu bước bổ sung như CAPTCHA có khả năng truy cập hoặc MFA phù hợp.

Ví dụ delay minh họa:

~~~text
delay = min(baseDelay * 2^consecutiveFailures, maximumDelay)
delay = addRandomJitter(delay)
~~~

Đây chỉ là một dạng backoff; không có một ngưỡng hoặc thời gian chờ phù hợp cho mọi hệ thống. Cần đặt trần để tránh người dùng hợp lệ phải chờ quá lâu, dùng jitter để giảm đồng bộ request và thực hiện delay bằng cơ chế không giữ worker/thread trong lúc chờ.

### Soft lockout vẫn cần chống abuse

Nếu attacker có thể tạo vô hạn request khiến hệ thống thực hiện password hash đắt đỏ, soft lockout có thể không đủ bảo vệ tài nguyên. Cần rate limit ở nhiều lớp, bảo vệ endpoint, giới hạn tổng tải và giám sát bất thường. Đừng để một tài khoản bị khóa cứng chỉ vì attacker liên tục gửi request từ các nguồn khác nhau.

## 5. Chọn chiều đếm: account, source hay toàn hệ thống?

Không có một chiều đếm đơn lẻ nào đủ tốt:

| Chiều kiểm soát | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| **Theo account identifier** | Phát hiện nhiều lần thử vào cùng một tài khoản. | Dễ bị dùng để khóa nạn nhân; attacker có thể phân tán số lần thử. |
| **Theo IP** | Hạn chế nguồn gửi quá nhiều request. | NAT, VPN, proxy và mạng di động có thể gom nhiều người dùng; botnet phân tán dễ né. |
| **Theo subnet/ASN** | Phát hiện cụm nguồn hoặc hạ tầng đáng ngờ. | Có thể ảnh hưởng người dùng hợp lệ dùng chung nhà mạng hoặc tổ chức. |
| **Theo device/session** | Bổ sung tín hiệu về client đã biết. | Fingerprint có thể thay đổi hoặc bị giả mạo; không phải định danh chắc chắn. |
| **Theo client/application** | Bảo vệ endpoint và phát hiện một integration bị lạm dụng. | Không phát hiện mọi nguồn tấn công ngoài client đó. |
| **Toàn hệ thống** | Bảo vệ capacity và phát hiện đợt tấn công diện rộng. | Cần tránh giới hạn quá mạnh gây ảnh hưởng diện rộng. |

Thiết kế thực tế kết hợp nhiều chiều. Account counter giúp nhận diện thử tập trung; source counter giúp hạn chế một nguồn; distinct-account và distinct-source metrics giúp nhận diện spraying và brute force phân tán; global limit bảo vệ dịch vụ khỏi cạn tài nguyên.

Không dùng IP hoặc browser fingerprint như bằng chứng danh tính. Chúng chỉ là tín hiệu rủi ro, có thể bị chia sẻ, thay đổi hoặc giả mạo.

## 6. Bộ đếm thất bại và cửa sổ thời gian

Một bộ đếm cần có semantics rõ ràng:

- Đếm loại thất bại nào: mật khẩu sai, MFA sai, challenge thất bại hay mọi lỗi?
- Cửa sổ thời gian là cố định hay trượt?
- Thành công có xóa bộ đếm không, hay chỉ giảm điểm rủi ro?
- Bộ đếm áp dụng cho account, source, device, client hay kết hợp?
- Bộ đếm có được chia sẻ nhất quán giữa các server instance?
- Khi account không tồn tại, hệ thống có xử lý tương đương để tránh enumeration không?

### Fixed window và sliding window

| Cách đếm | Mô tả | Đánh đổi |
| --- | --- | --- |
| **Fixed window** | Đếm trong các khoảng thời gian cố định, sau đó reset. | Dễ triển khai nhưng attacker có thể tận dụng ranh giới hai cửa sổ để gửi nhiều request sát nhau. |
| **Sliding window** | Chỉ tính các lần thử trong khoảng thời gian lùi từ thời điểm hiện tại. | Phản ánh hành vi gần đây tốt hơn nhưng cần lưu/ước lượng sự kiện và tốn tài nguyên hơn. |
| **Token bucket/leaky bucket** | Điều tiết tốc độ request theo quota và khả năng tích lũy. | Hữu ích cho rate limit, nhưng không tự thay thế phân tích rủi ro theo account. |

Bộ đếm phân tán cần thao tác nguyên tử hoặc cơ chế nhất quán phù hợp. Nếu mỗi node có bộ đếm riêng, attacker có thể phân phối request qua nhiều node để vượt ngưỡng. Nếu store bộ đếm lỗi, hệ thống cần hành vi fallback được định nghĩa thay vì vô tình bỏ qua mọi giới hạn.

## 7. Không để lockout tiết lộ tài khoản

Thông báo công khai như “tài khoản đã bị khóa” có thể xác nhận identifier tồn tại. Kẻ tấn công có thể dùng nó để xác thực danh sách tài khoản hoặc xác định nạn nhân đang bị ảnh hưởng.

Ở giao diện chưa xác thực, nên dùng phản hồi tổng quát như:

> Không thể hoàn tất đăng nhập bằng thông tin đã cung cấp. Hãy thử lại sau hoặc sử dụng kênh hỗ trợ chính thức nếu bạn vẫn gặp sự cố.

Thông tin cụ thể hơn có thể được cung cấp qua kênh đã xác minh hoặc sau khi người dùng chứng minh quyền kiểm soát tài khoản.

### Side channel cần xem xét

Không chỉ nội dung thông báo mới tiết lộ lockout:

- HTTP status code khác nhau giữa account tồn tại và không tồn tại.
- Response body hoặc redirect khác nhau.
- Thời gian phản hồi thay đổi rõ.
- CAPTCHA/challenge chỉ xuất hiện khi account tồn tại.
- Endpoint recovery hoặc resend OTP trả trạng thái khác.
- Email/SMS được gửi chỉ với một nhóm identifier và phản hồi công khai xác nhận điều đó.

Hãy kiểm thử toàn bộ luồng login, unlock, password reset, MFA recovery và resend. Không sửa riêng thông báo login rồi để endpoint khác tiết lộ account state.

## 8. Lockout và credential stuffing: vì sao một ngưỡng không đủ?

Giả sử policy khóa tài khoản sau sáu lần nhập sai trong 15 phút:

- Brute force tập trung có thể bị chặn sau sáu lần thử.
- Password spraying thử một mật khẩu trên hàng nghìn tài khoản có thể không chạm ngưỡng.
- Credential stuffing có thể thử một cặp bị lộ trên mỗi tài khoản; nếu thành công ngay, bộ đếm thất bại không tăng.
- Attacker có thể cố ý gửi sáu mật khẩu sai cho từng tài khoản để khóa hàng loạt.

Vì vậy, cần các lớp kiểm soát bổ sung:

- Phát hiện nhiều account identifier bị thử từ cùng nguồn/cụm nguồn.
- Phát hiện một account bị thử từ nhiều nguồn khác nhau.
- Kiểm tra mật khẩu mới hoặc đang dùng có nằm trong danh sách bị lộ.
- MFA, ưu tiên phương thức chống phishing cho tài khoản rủi ro cao.
- Risk-based challenge và đánh giá sau đăng nhập thành công.
- Session management, thông báo đăng nhập mới và khả năng revoke.

Credential stuffing có thể thành công bằng credential đúng. Do đó, chỉ theo dõi failed login không đủ; cần theo dõi cả successful login bất thường sau các pattern đáng ngờ.

## 9. Risk-based authentication thay cho khóa cứng

Hệ thống có thể kết hợp nhiều tín hiệu để quyết định mức phản ứng:

- Số lần thử và tốc độ thử.
- Số account khác nhau được thử từ một nguồn.
- Số nguồn khác nhau thử cùng một account.
- Thiết bị mới, client bất thường hoặc thay đổi hành vi.
- ASN, mạng hoặc vị trí khác biệt so với baseline.
- Credential xuất hiện trong dữ liệu lộ lọt đã biết.
- MFA bị từ chối nhiều lần hoặc push request bất thường.
- Lịch sử đăng nhập thành công/thất bại gần đây.

Các tín hiệu này không phải bằng chứng tuyệt đối. VPN, roaming, NAT và thiết bị dùng chung có thể tạo false positive. Policy nên kết hợp tín hiệu, có ngưỡng và khả năng review, không tự động khóa chỉ vì IP hoặc vị trí thay đổi.

### Phản ứng theo mức rủi ro

| Mức rủi ro | Phản ứng tham khảo |
| --- | --- |
| Thấp | Cho phép thử bình thường, ghi nhận baseline. |
| Tăng nhẹ | Backoff, rate limit hoặc challenge accessible. |
| Trung bình | Yêu cầu MFA/step-up phù hợp, giảm tốc độ và tăng giám sát. |
| Cao | Tạm giữ đăng nhập, xác minh qua kênh độc lập hoặc khóa credential nghi bị lộ. |
| Đã xác nhận compromise | Revoke credential, session/token liên quan và thực hiện incident recovery. |

Risk engine cần giải thích được lý do nội bộ, ghi policy version và đo false positive. Không tiết lộ chi tiết ngưỡng hoặc rule cho attacker qua public response.

## 10. MFA và passkey làm giảm nhu cầu hard lockout

MFA giúp giảm khả năng mật khẩu bị đoán hoặc bị lộ đơn lẻ dẫn tới chiếm tài khoản. Tuy nhiên, mức bảo vệ phụ thuộc phương thức:

- **TOTP/SMS OTP:** bổ sung yếu tố nhưng có thể bị phishing hoặc chuyển tiếp.
- **Push:** có nguy cơ MFA fatigue nếu không có number matching, cooldown và xác nhận ý định.
- **Passkey/WebAuthn:** chống phishing tốt hơn nhờ ràng buộc origin/RP ID và chữ ký bằng khóa riêng.
- **Security key:** có thể cung cấp yếu tố possession mạnh nếu enrollment và recovery được bảo vệ.

MFA không loại bỏ nhu cầu rate limit. Attacker vẫn có thể spam login, làm cạn tài nguyên, gây push fatigue hoặc khai thác recovery. Passkey cũng không giúp nếu hệ thống có fallback yếu cho phép bypass.

### Không khóa account vì MFA sai theo cách dễ bị lạm dụng

Giới hạn số lần nhập TOTP hoặc push approval nên áp dụng cho challenge/authenticator và nguồn gửi, kết hợp cooldown. Nếu attacker có thể yêu cầu challenge rồi cố ý nhập sai để khóa toàn bộ account, hệ thống lại tạo ra DoS. Có thể tạm dừng challenge hoặc yêu cầu recovery mà không vô hiệu hóa mọi credential hợp lệ khác.

## 11. Khi nào nên suspend credential thay vì khóa account?

Nếu có bằng chứng rủi ro tập trung vào một credential hoặc thiết bị, suspend/revoke đúng đối tượng có thể giảm tác động:

- Mất một passkey: suspend credential ID cụ thể; giữ passkey dự phòng nếu policy cho phép.
- TOTP secret bị lộ: revoke binding và yêu cầu enrollment mới.
- API key bị đăng lên repository: suspend/revoke key ID, rotate key và rà soát workload.
- Client certificate nghi bị lộ: kiểm tra PKI status và suspend/revoke certificate.
- Password bị credential stuffing: buộc reset hoặc chặn password authentication theo policy; không nhất thiết khóa passkey độc lập.

Tuy nhiên, nếu có dấu hiệu compromise toàn tài khoản, account-level suspension và thu hồi session/token có thể cần thiết. Phải xác định phạm vi từ bằng chứng và risk policy, không chỉ từ số lần đăng nhập sai.

## 12. Recovery sau lockout

Một người dùng hợp lệ cần con đường lấy lại quyền truy cập mà không phải nhờ helpdesk tắt toàn bộ kiểm soát:

- Cho phép chờ hết throttling hoặc xác minh qua yếu tố độc lập còn active.
- Password reset token phải ngắn hạn, purpose-bound và one-time.
- Factor recovery cần bằng chứng phù hợp; không tự động hạ từ passkey xuống SMS/email.
- Thông báo qua kênh đã xác minh trước đó.
- Với tài khoản đặc quyền, dùng quy trình xác minh và phê duyệt mạnh hơn.
- Sau khi xác nhận compromise, thu hồi credential, session và refresh token liên quan.
- Không tiết lộ account existence hoặc trạng thái lockout trong trang recovery công khai.

Recovery không được biến thành đường vòng cho attacker. Nếu hard lockout có thể được kích hoạt từ xa, unlock cũng không nên chỉ dựa vào email hoặc số điện thoại vừa được thay đổi.

## 13. Giám sát và phát hiện password spraying/credential stuffing

Để đánh giá lockout policy, cần theo dõi nhiều chỉ số:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Failed attempts per account | Phát hiện thử tập trung vào một tài khoản. |
| Distinct accounts per source | Phát hiện password spraying. |
| Distinct sources per account | Phát hiện brute force phân tán. |
| Successful logins after suspicious failures | Phát hiện credential stuffing hoặc thử credential có mục tiêu. |
| Lockout/throttle rate | Đo mức ảnh hưởng của policy và nguy cơ DoS. |
| Unlock/recovery volume | Phát hiện attacker đang cố khóa hàng loạt hoặc recovery flow bị lạm dụng. |
| MFA denial/push rate | Phát hiện MFA fatigue và lạm dụng challenge. |
| False-positive challenge rate | Đo tác động lên người dùng hợp lệ. |
| Hash verification latency | Theo dõi chi phí CPU và khả năng bị DoS. |

Log cần có timestamp, correlation ID, account reference đã pseudonymize, client, source metadata đã giảm thiểu, outcome và policy version. Không ghi password, OTP, recovery code, cookie, access token hoặc refresh token.

### Cảnh báo và phản ứng

- Tăng đột biến distinct accounts per source: xem xét spraying.
- Tăng distinct sources per account: xem xét brute force phân tán.
- Nhiều login thành công sau chuỗi thử bất thường: kiểm tra session, thiết bị và hành động tiếp theo.
- Nhiều lockout/recovery request: xem xét DoS hoặc abuse recovery.
- Tăng latency password hash: kiểm tra tải và giới hạn endpoint.

Không tự động khóa mọi tài khoản có liên quan tới một cảnh báo. Phản ứng phải dựa trên mức tin cậy của tín hiệu, phạm vi ảnh hưởng và khả năng gây gián đoạn.

## 14. Mã giả: kết hợp throttling và risk policy

Đoạn mã dưới đây minh họa luồng khái niệm, không phải cấu hình ngưỡng dùng trực tiếp trong production:

~~~text
handleLogin(identifier, source, device, password):
    normalizedId = normalizeIdentifier(identifier)
    risk = evaluateSignals(normalizedId, source, device)

    if globalCapacityLimitExceeded():
        return genericTemporaryFailure()

    if sourceRateLimitExceeded(source):
        recordEvent("source_throttled", risk)
        return genericTemporaryFailure()

    account = lookupAccount(normalizedId)
    hashToVerify = account.passwordHash if account exists
                   else configuredDummyHash

    passwordValid = verifyPasswordWithSafeHashLibrary(
        password,
        hashToVerify
    )

    recordAttemptAtomically(
        accountReference = pseudonymize(normalizedId),
        source = reduceSourceMetadata(source),
        outcome = passwordValid and account is active
    )

    if not account exists or not account is active or not passwordValid:
        applyProgressiveAccountAndSourceThrottling(risk)
        detectSprayingAndDistributedGuessing()
        return genericLoginFailure()

    if risk.requiresChallenge:
        return requireConfiguredMfaOrRiskChallenge()

    if risk.indicatesCompromise:
        return holdForIndependentVerification()

    session = createSessionAfterAllRequiredFactorsPass(account)
    rotateSessionIdentifier(session)
    recordSuccessfulLoginAndMonitorPostAuthBehavior(session, risk)
    return success()
~~~

Các nguyên tắc triển khai:

- Bộ đếm và rate limit cần hoạt động nhất quán giữa nhiều instance.
- Account không tồn tại vẫn cần nhánh xử lý giảm timing enumeration.
- Không khóa vĩnh viễn chỉ từ request không đáng tin.
- MFA/pending challenge chưa hoàn tất không được tạo session authenticated.
- Khi có dấu hiệu compromise, đánh giá session/token đã tồn tại và áp dụng revoke policy.
- Thông báo công khai không tiết lộ account state hoặc rule nội bộ.

## 15. Tình huống thực tế: attacker cố tình khóa tài khoản nhân viên

Một ứng dụng nội bộ áp dụng hard lockout sau năm lần đăng nhập sai trong mười phút. Attacker có danh sách email nhân viên từ một nguồn công khai. Họ gửi năm request với mật khẩu sai cho mỗi email, phân tán qua nhiều IP.

### Hệ quả

- Nhiều tài khoản hợp lệ bị khóa dù không có credential nào bị đoán đúng.
- Helpdesk nhận lượng lớn yêu cầu mở khóa.
- Nhân viên không thể truy cập dịch vụ trong giờ làm việc.
- Attacker có thể lặp lại sau khi tài khoản được mở khóa.
- Nếu giao diện hiển thị “account locked”, attacker xác nhận được identifier tồn tại.

### Thiết kế thay thế

1. Bỏ hard lockout cố định làm phản ứng duy nhất.
2. Áp dụng progressive delay theo account cùng rate limit theo source, subnet và global capacity.
3. Phát hiện distinct accounts per source và phân tích nguồn phân tán.
4. Dùng MFA/passkey và risk challenge theo policy; không gửi push không giới hạn.
5. Giữ thông báo công khai chung; cung cấp thông tin cụ thể qua kênh đã xác minh.
6. Chỉ suspend credential hoặc account khi có bằng chứng/risk threshold phù hợp.
7. Cung cấp recovery và session management an toàn.
8. Theo dõi lockout rate, false positive, recovery volume và successful login sau chuỗi thử.

Kết quả mong muốn là attacker khó tiếp tục đoán credential và khó gây gián đoạn diện rộng, trong khi người dùng hợp lệ vẫn có cách đăng nhập hoặc khôi phục.

## 16. Kiểm thử lockout policy

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Một account nhận nhiều mật khẩu sai từ một nguồn | Throttling/backoff tăng dần; không mặc định khóa vĩnh viễn. |
| Một nguồn thử ít mật khẩu trên nhiều account | Phát hiện spraying qua distinct-account metrics. |
| Nhiều nguồn thử một account | Phát hiện brute force phân tán; policy theo rủi ro. |
| Một credential bị lộ được thử trên nhiều account | Phát hiện pattern stuffing và giám sát successful login. |
| Attacker cố tình khóa nạn nhân | Không thể gây hard lockout chỉ bằng vài request không xác thực, trừ policy đặc biệt có kiểm soát. |
| Nhiều người dùng chung NAT | Không khóa/challenge toàn bộ chỉ vì IP chung. |
| Request phân tán qua nhiều app node | Bộ đếm và rate limit vẫn nhất quán theo thiết kế. |
| Account không tồn tại | Response/status/timing không dễ phân biệt với account tồn tại. |
| User nhập sai do lỗi gõ | Có thể thử lại sau backoff hợp lý; không bị đình chỉ dài vô cớ. |
| MFA challenge bị spam | Cooldown/limit áp dụng; không tạo MFA fatigue. |
| Passkey active, password bị throttled | Passkey vẫn hoạt động nếu account-level policy cho phép. |
| Credential bị xác nhận compromise | Revoke/replace credential và xử lý session/token liên quan. |
| Recovery request bị spam | Rate limit và không tiết lộ account existence. |
| Rate-limit store không sẵn sàng | Fallback theo policy; không bỏ qua mọi kiểm soát một cách âm thầm. |
| Password hash service quá tải | Bảo vệ capacity; không tạo hàng đợi vô hạn hoặc giữ worker bằng sleep. |
| Người dùng hợp lệ bị false positive | Có đường xác minh/recovery phù hợp và audit. |

### Đánh giá hiệu quả và tác động

Không chỉ đo số lần brute force bị chặn. Cần đánh giá:

- Tỷ lệ đăng nhập hợp lệ bị throttled/blocked.
- Thời gian người dùng hợp lệ lấy lại quyền truy cập.
- Số tài khoản bị lockout theo từng nguồn và tenant.
- Tỷ lệ phát hiện spraying/stuffing trước khi có đăng nhập thành công.
- Tải CPU và latency của password hash verification.
- Tỷ lệ challenge, MFA denial và false positive.
- Khả năng xử lý khi một dependency như Redis, IdP hoặc notification service gặp lỗi.

## 17. Checklist thiết kế lockout trade-off

- [ ] Phân biệt brute force, password spraying và credential stuffing.
- [ ] Không dùng hard lockout theo account làm biện pháp duy nhất.
- [ ] Đánh giá nguy cơ account lockout DoS trước khi đặt ngưỡng.
- [ ] Kết hợp rate limit theo account, source, subnet/ASN, device/client và toàn hệ thống.
- [ ] Có progressive delay/backoff với trần và jitter phù hợp.
- [ ] Bộ đếm có cửa sổ thời gian và semantics rõ ràng; cập nhật nguyên tử, dùng được trong môi trường phân tán.
- [ ] Không dùng IP/fingerprint như bằng chứng danh tính duy nhất.
- [ ] Phản hồi công khai chống account enumeration ở login, unlock và recovery.
- [ ] Phát hiện spraying và brute force phân tán bằng distinct-account/source metrics.
- [ ] Theo dõi cả successful login bất thường, không chỉ failed login.
- [ ] Dùng MFA/passkey phù hợp; chống push fatigue và không fallback yếu.
- [ ] Suspend/revoke đúng credential khi có bằng chứng compromise; phân biệt với account suspension.
- [ ] Recovery có purpose binding, TTL, one-time use và xác minh độc lập.
- [ ] Có session/token revocation policy sau compromise.
- [ ] Audit đủ điều tra nhưng không ghi password, OTP, cookie hoặc token.
- [ ] Đo false positive, lockout rate, recovery volume, latency và capacity.
- [ ] Kiểm thử NAT, VPN, botnet, race condition, dependency failure và tấn công diện rộng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao hard lockout sau một số lần sai có thể trở thành DoS?

**Gợi ý:** Attacker chỉ cần biết identifier và gửi mật khẩu sai để khóa tài khoản mà không cần chiếm credential.

**Câu 2.** Vì sao một bộ đếm theo account có thể bỏ sót password spraying?

**Gợi ý:** Attacker thử ít mật khẩu trên nhiều tài khoản; từng tài khoản không chạm ngưỡng dù tổng số lần thử rất lớn.

**Câu 3.** Credential stuffing khác brute force ở điểm nào?

**Gợi ý:** Credential stuffing dùng cặp username/password đã bị lộ; brute force thử đoán mật khẩu. Một lần stuffing có thể thành công ngay.

**Câu 4.** Vì sao cần kết hợp giới hạn theo account và source?

**Gợi ý:** Account limit phát hiện thử tập trung nhưng dễ bị lợi dụng khóa nạn nhân; source limit giảm tốc một nguồn nhưng có thể bị botnet né và ảnh hưởng NAT.

**Câu 5.** Thành công đăng nhập sau chuỗi thử đáng ngờ có cần giám sát không?

**Gợi ý:** Có. Credential stuffing có thể dùng đúng mật khẩu; cần đánh giá session, thiết bị và hành động sau đăng nhập.

**Câu 6.** Khi password bị nghi lộ, có nhất thiết khóa toàn bộ account không?

**Gợi ý:** Không luôn luôn. Có thể chặn/reset password credential, giữ passkey độc lập nếu policy cho phép, đồng thời kiểm tra session/token liên quan.

**Câu 7.** Vì sao không nên hiển thị chi tiết “account locked” cho người chưa xác thực?

**Gợi ý:** Nó có thể tiết lộ tài khoản tồn tại và trạng thái bảo mật; thông tin cụ thể nên đi qua kênh đã xác minh.

## 19. Ghi nhớ

**Lockout trade-off là bài toán cân bằng giữa làm chậm việc đoán credential và giữ khả năng truy cập của người dùng hợp lệ.** Hard lockout theo một ngưỡng account cố định có thể chặn brute force tập trung nhưng cũng cho phép attacker gây DoS và không đủ sức phát hiện password spraying hoặc credential stuffing phân tán. Thiết kế vững chắc kết hợp throttling đa chiều, progressive delay, risk-based challenge, MFA/passkey, phát hiện đăng nhập thành công bất thường và recovery an toàn. Trạng thái credential, account, session và token phải được quản lý riêng; mọi phản ứng cần dựa trên bằng chứng, hạn chế account enumeration, đo false positive và giữ đường khôi phục đủ tin cậy.
