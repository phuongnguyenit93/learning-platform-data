# One-time code — Mã xác thực dùng một lần

> **Chương:** Passwordless  
> **Chủ đề:** One-time code  
> **Phạm vi:** Security Authentication Fundamentals — sử dụng mã dùng một lần trong luồng đăng nhập không mật khẩu, xác minh bổ sung, liên kết kênh nhận mã, chống phishing/replay và bảo vệ vòng đời tài khoản.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **one-time code (OTC/OTP)** là gì và phân biệt mã do máy chủ phát hành với mã được tạo từ secret dùng chung.
2. Mô tả HOTP, TOTP, mã qua SMS/email và các luồng passwordless bằng mã.
3. Thiết kế vòng đời mã: tạo, ràng buộc mục đích, phân phối, xác minh, giới hạn thử, tiêu thụ một lần và hết hạn.
4. Nhận diện rủi ro của mã ngắn như phishing, replay, brute force, SIM swap, chiếm hộp thư, enumeration và race condition.
5. Lựa chọn cách dùng one-time code phù hợp với mức assurance và biết khi nào nên ưu tiên passkey/WebAuthn.

## 1. One-time code là gì?

**One-time code** là một giá trị xác minh chỉ được chấp nhận trong một phạm vi sử dụng đã định và không được phép tái sử dụng sau khi đã tiêu thụ thành công. Người dùng thường nhập một chuỗi số ngắn, ví dụ 6 chữ số, để chứng minh họ đang kiểm soát một authenticator hoặc một kênh nhận mã đã đăng ký.

Từ **OTP (one-time password)** thường được dùng cho mã xác thực dùng một lần. Trong thực tế, có nhiều cơ chế khác nhau cùng tạo ra một mã trông giống nhau:

- **HOTP:** mã được tính từ secret và bộ đếm tăng dần.
- **TOTP:** mã được tính từ secret và bước thời gian hiện tại.
- **Server-generated code:** máy chủ sinh ngẫu nhiên, lưu trạng thái xác minh và gửi mã qua SMS, email hoặc một kênh khác.
- **Push/approval code:** một thử thách hoặc mã gắn với yêu cầu cụ thể, được xác nhận qua ứng dụng đã đăng ký.

Các cơ chế này **không có cùng đặc tính bảo mật**. Chúng khác nhau về nơi giữ secret, cách đồng bộ, cách chống replay và độ tin cậy của kênh truyền.

### Mã dùng một lần trả lời câu hỏi nào?

Mã có thể hỗ trợ xác minh rằng người yêu cầu:

- kiểm soát thiết bị/app đã đăng ký secret TOTP/HOTP;
- nhận được tin nhắn hoặc email gửi tới kênh đã đăng ký;
- truy cập được một thiết bị hoặc ứng dụng đã được liên kết với tài khoản;
- đang hoàn tất một giao dịch xác minh cụ thể còn hiệu lực.

Mã **không tự chứng minh** người nhập là chủ thể ngoài đời thực, không bảo đảm kênh nhận mã chưa bị chiếm, không cấp quyền cho mọi hành động và không chống phishing chỉ vì nó hết hạn nhanh.

## 2. Phân biệt các loại one-time code

| Loại mã | Nơi tạo | Nguồn tin cậy chính | Đặc điểm và giới hạn |
| --- | --- | --- | --- |
| **HOTP** | Authenticator và verifier cùng tính toán | Secret chia sẻ và counter | Không phụ thuộc đồng hồ; cần đồng bộ counter và chống chấp nhận lại |
| **TOTP** | Authenticator và verifier cùng tính toán | Secret chia sẻ và thời gian | Thuận tiện khi offline; có cửa sổ thời gian và nguy cơ phishing/replay trong cửa sổ |
| **SMS OTP** | Máy chủ | Máy chủ sinh mã và số điện thoại/kênh viễn thông | Dễ triển khai; có SIM swap, chuyển hướng tin nhắn, phishing và phụ thuộc mạng |
| **Email code** | Máy chủ | Máy chủ sinh mã và hộp thư | Dễ tiếp cận; phụ thuộc bảo mật email, forwarding, session email và phishing |
| **Recovery code** | Máy chủ lúc thiết lập hoặc đổi phương thức | Secret dự phòng được cấp và lưu bởi người dùng | Thường dùng ít lần hoặc một lần; cần bảo vệ như credential có giá trị cao |
| **Magic link** | Máy chủ | Token ngẫu nhiên trong URL và hộp thư/kênh nhận | Là bearer token; người giữ link có thể hoàn tất đăng nhập nếu chưa bị ràng buộc thêm |

Tên gọi “OTP” không nên làm mờ cách xác minh. Ví dụ, mã TOTP do app tạo không cần tin nhắn từ máy chủ, trong khi mã SMS thường là giá trị ngẫu nhiên do máy chủ phát hành. Một magic link không phải chuỗi số ngắn nhưng vẫn có thể là **bằng chứng dùng một lần**.

## 3. HOTP: mã dựa trên bộ đếm

**HOTP (HMAC-based One-Time Password)** dùng secret chia sẻ giữa authenticator và verifier cùng với một bộ đếm. Về khái quát, thuật toán tạo mã bằng HMAC, sau đó rút gọn kết quả thành số có số chữ số đã cấu hình.

`````````
HOTP(secret, counter):
    hmac_result = HMAC(algorithm, secret, counter)
    binary_code = dynamic_truncate(hmac_result)
    return binary_code mod 10^digits
`````````

Authenticator tăng counter khi tạo mã. Verifier cần tìm mã trong một **look-ahead window** có giới hạn để xử lý trường hợp người dùng bấm tạo mã nhiều lần hoặc hai bên lệch counter.

### Ưu điểm

- Không cần đồng hồ chính xác hoặc kết nối mạng tại thời điểm tạo mã.
- Phù hợp với một số token phần cứng hoặc thiết bị tạo mã độc lập.

### Rủi ro và vận hành

- Nếu verifier chấp nhận counter đã dùng, cùng mã có thể bị replay.
- Nếu look-ahead window quá rộng, kẻ tấn công có nhiều cơ hội đoán hơn.
- Nếu counter lệch, người dùng có thể bị từ chối; cần cơ chế đồng bộ có giới hạn.
- Secret phải được bảo vệ, vì người có secret và counter có thể tạo mã hợp lệ.

Khi xác minh thành công, verifier cần cập nhật counter đã chấp nhận **một cách nguyên tử**. Hai request đồng thời không được cùng tiêu thụ một counter.

## 4. TOTP: mã dựa trên thời gian

**TOTP (Time-based One-Time Password)** là HOTP dùng một giá trị thời gian được chia thành các bước cố định thay cho counter do người dùng tăng. Authenticator và verifier cần có cùng secret, cùng thuật toán, số chữ số và tham số bước thời gian.

Khái quát:

`````````
time_counter = floor((current_unix_time - T0) / time_step)
code = HOTP(shared_secret, time_counter)
`````````

Một số ứng dụng phổ biến dùng bước thời gian 30 giây, nhưng đó là cấu hình thường gặp chứ không phải quy tắc duy nhất. Mã có thể được chấp nhận trong cửa sổ gồm bước hiện tại và một số bước lân cận để bù lệch đồng hồ.

### Luồng xác minh TOTP

1. Khi enrollment, máy chủ tạo secret ngẫu nhiên có độ mạnh phù hợp và cung cấp qua một kênh đăng ký an toàn.
2. Người dùng quét QR hoặc nhập secret vào authenticator app.
3. Máy chủ lưu secret trong kho được bảo vệ; không lưu mã TOTP hiện tại như thể nó là password hash.
4. Khi đăng nhập, máy chủ xác định tài khoản và lấy secret đúng của authenticator đã đăng ký.
5. Verifier tính các mã trong cửa sổ thời gian cho phép và so sánh với mã người dùng gửi.
6. Nếu hợp lệ, máy chủ kiểm tra mã/bước thời gian đã được chấp nhận trước đó chưa, ghi nhận tiêu thụ nguyên tử và cập nhật giao dịch xác thực.

### Ví dụ pseudocode

`````````
verifyTotp(account, submittedCode, transaction):
    require(transaction.accountId == account.id)
    require(transaction.purpose == LOGIN)
    require(transaction.state == PENDING)
    require(not transaction.expired)
    require(account.status == ACTIVE)
    enforceAttemptLimit(account, transaction)

    secret = loadProtectedTotpSecret(account)
    matchedStep = findMatchingStep(secret, submittedCode, allowedClockSkew)
    if matchedStep is null:
        recordFailure(transaction)
        return DENIED

    atomically:
        if stepAlreadyConsumed(account.authenticatorId, matchedStep):
            return REPLAY_DENIED
        markStepConsumed(account.authenticatorId, matchedStep)
        markFactorVerified(transaction, "totp")

    return FACTOR_VERIFIED
`````````

Đây là mã giả; thư viện TOTP nên được chọn và kiểm thử thay vì tự viết thuật toán mật mã. Trong hệ thống phân tán, thao tác đánh dấu step đã dùng cần có tính nguyên tử hoặc cơ chế đồng bộ tương đương để tránh hai node chấp nhận cùng mã.

### Vì sao TOTP vẫn có thể bị phishing?

Người dùng có thể bị dụ nhập mã TOTP vào website giả. Kẻ tấn công chuyển tiếp mã ngay lập tức tới website thật trước khi mã hết hạn. Vì vậy:

- TOTP có thể chống một số hình thức đánh cắp mật khẩu đơn thuần;
- TOTP có thể giúp giảm rủi ro so với chỉ mật khẩu;
- TOTP **không ràng buộc bằng chứng với origin của website** như WebAuthn;
- hạn dùng ngắn không tự biến TOTP thành phishing-resistant.

## 5. Mã do máy chủ tạo: SMS và email

Với SMS OTP hoặc email code, máy chủ tạo một giá trị ngẫu nhiên, gắn với tài khoản và mục đích, sau đó gửi qua kênh đã đăng ký.

### Vòng đời mã

1. Người dùng yêu cầu đăng nhập hoặc xác minh một hành động.
2. Máy chủ tạo challenge ID và mã ngẫu nhiên bằng **cryptographically secure random number generator (CSPRNG)**.
3. Mã được liên kết với account, purpose, transaction, thời điểm hết hạn và số lần thử tối đa.
4. Máy chủ gửi mã qua kênh đã đăng ký, không dùng địa chỉ/số điện thoại tùy ý do client vừa nhập làm bằng chứng sở hữu.
5. Người dùng nhập mã; verifier kiểm tra đúng giao dịch, còn hạn, chưa dùng, chưa vượt số lần thử và mã khớp.
6. Nếu thành công, mã được tiêu thụ nguyên tử và giao dịch chuyển sang trạng thái đã xác minh.

### Pseudocode

`````````
issueServerCode(account, purpose):
    require(account.status == ACTIVE)
    require(channelIsVerifiedAndEligible(account, purpose))
    enforceSendRateLimit(account, purpose)

    code = secureRandomDigits(6)
    challengeId = randomUnpredictableId()
    storeChallenge(
        id=challengeId,
        accountId=account.id,
        purpose=purpose,
        codeVerifier=protectedCodeVerifier(code),
        expiresAt=serverNow() + configuredTTL,
        maxAttempts=configuredAttemptLimit,
        consumed=false
    )
    sendToRegisteredChannel(account, code)
    return challengeId

verifyServerCode(account, challengeId, submittedCode, purpose):
    challenge = loadChallengeForUpdate(challengeId)
    require(challenge.accountId == account.id)
    require(challenge.purpose == purpose)
    require(not challenge.expired and not challenge.consumed)
    require(challenge.attempts < challenge.maxAttempts)

    if not constantTimeCompare(
        protectedCodeVerifier(submittedCode),
        challenge.codeVerifier
    ):
        incrementAttemptsAtomically(challenge)
        return DENIED

    consumeChallengeAtomically(challenge)
    return FACTOR_VERIFIED
`````````

Đây là pseudocode khái niệm. Với mã ngắn chỉ có một triệu khả năng nếu dùng 6 chữ số, một hash thông thường không tự bảo vệ được dữ liệu khi database bị lộ và attacker có thể thử offline. Cần cân nhắc HMAC/pepper được giữ ngoài database, TTL ngắn, giới hạn thử chặt và bảo vệ secret của dịch vụ. Không log mã ở bất kỳ bước nào.

### SMS OTP: những giới hạn cần biết

- **SIM swap/port-out:** Kẻ tấn công chiếm quyền số điện thoại bằng cách thao túng nhà mạng hoặc quy trình chuyển mạng.
- **SMS forwarding/interception:** Tin nhắn có thể bị chuyển tiếp, đọc trên thiết bị bị chiếm hoặc lộ qua bản sao lưu.
- **Phishing/AiTM:** Người dùng nhập mã vào trang giả, kẻ tấn công chuyển tiếp ngay.
- **SS7/telecom weaknesses:** Hạ tầng viễn thông và định tuyến tin nhắn có những rủi ro ngoài quyền kiểm soát ứng dụng.
- **Delivery failure:** Mất sóng, roaming, chậm tin nhắn hoặc số điện thoại thay đổi.

SMS có thể hữu ích như phương thức dự phòng hoặc trong môi trường có ràng buộc thiết bị hạn chế, nhưng không nên được coi là lựa chọn mạnh nhất cho tài khoản quản trị hoặc hành động rủi ro cao.

### Email code: những giới hạn cần biết

- Email account có thể đã bị chiếm, mật khẩu dùng lại hoặc session email bị đánh cắp.
- Hộp thư có thể tự động forward mã tới nơi khác.
- Link/mã trong email có thể bị lộ qua thiết bị, extension, notification preview hoặc hệ thống phân tích.
- Nếu email vừa được thay đổi bằng một luồng yếu, nó không nên lập tức trở thành kênh recovery đáng tin.

Email code chứng minh khả năng truy cập hộp thư tại thời điểm đó theo mô hình hệ thống, **không tự chứng minh danh tính pháp lý** và không nên thay thế các biện pháp mạnh hơn cho thao tác nhạy cảm.

## 6. Passwordless bằng one-time code

**Passwordless** nghĩa là người dùng không phải cung cấp mật khẩu trong luồng đăng nhập đó. Mã một lần có thể được dùng để hoàn tất đăng nhập nếu kênh nhận mã đã được đăng ký và verifier kiểm tra đúng quy trình.

Ví dụ: Người dùng nhập email, máy chủ gửi mã vào hộp thư đã xác minh, người dùng nhập mã và nhận session. Cách này giảm việc tạo và nhớ password, nhưng mức assurance phụ thuộc **bảo mật của hộp thư, quy trình enrollment, mã và session**.

### Email one-time code flow

`````````
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant A as Authentication service
    participant DB as Account / challenge store
    participant M as Email provider
    U->>B: Nhập email
    B->>A: Yêu cầu gửi mã
    A->>DB: Kiểm tra account, trạng thái và rate limit
    A->>DB: Tạo challenge gắn account + purpose + TTL
    A->>M: Gửi mã tới email đã đăng ký
    M-->>U: Email chứa mã
    U->>B: Nhập mã
    B->>A: Gửi challenge ID và mã
    A->>DB: Kiểm tra mã, hạn dùng, số lần thử và consumed
    A->>DB: Tiêu thụ challenge một lần
    A->>DB: Kiểm tra account vẫn ACTIVE
    A-->>B: Tạo cookie phiên an toàn
`````````

### Điều kiện cần ràng buộc

- Mã gắn với **một tài khoản và một mục đích cụ thể**, ví dụ login, verify email, đổi recovery address hoặc xác nhận hành động.
- Challenge ID phải khó đoán và không thể dùng để suy ra mã.
- Mã có TTL ngắn phù hợp, số lần thử tối đa, giới hạn gửi lại và chống gửi spam.
- Resend phải tạo challenge mới hoặc thay thế challenge cũ theo quy tắc rõ; không để nhiều mã cùng có hiệu lực vô hạn.
- Thành công phải **tiêu thụ một lần** và không thể hoàn tất hai session từ cùng challenge.
- Sau khi xác minh, máy chủ kiểm tra trạng thái account, risk policy và chỉ phát session nếu điều kiện đầy đủ.
- Không cho phép đổi email nhận mã rồi dùng mã vừa gửi để chứng minh email mới đã được liên kết an toàn.

### Magic link khác mã nhập tay ở đâu?

Magic link chứa token trong URL. Khi người dùng bấm link, browser gửi token đến server. Token là **bearer credential**: người giữ được token có thể sử dụng nếu nó chưa hết hạn/chưa bị tiêu thụ. Một số hệ thống dùng cơ chế prefetch của email scanner hoặc link preview, có thể vô tình mở link trước người dùng.

Để giảm rủi ro:

- Token đủ ngẫu nhiên, ngắn hạn, một lần và gắn đúng account/purpose.
- Cân nhắc bước xác nhận bổ sung trên trang đích, tránh tiêu thụ token chỉ bởi một GET request tự động.
- Không để token xuất hiện trong analytics, referrer, log truy cập hoặc trang bên thứ ba.
- Dùng HTTPS, hạn chế script/third-party resource trên trang xử lý token và đặt chính sách referrer phù hợp.
- Sau khi hoàn tất, tạo session mới và làm sạch URL khỏi token.

## 7. Chống brute force, replay và lạm dụng gửi mã

Mã ngắn có không gian đoán hữu hạn. Với mã 6 chữ số, có 1.000.000 giá trị có thể; nếu attacker có thể thử nhiều lần hoặc yêu cầu mã liên tục, rủi ro tăng nhanh.

### Các lớp giới hạn

| Kiểm soát | Mục đích | Lưu ý |
| --- | --- | --- |
| **Per-challenge attempt limit** | Giới hạn số lần đoán cho một mã | Không reset chỉ bằng cách reload trang |
| **Per-account throttling** | Hạn chế thử liên tục vào một tài khoản | Tránh khóa vĩnh viễn dễ bị DoS |
| **Per-IP/device/risk throttling** | Phát hiện phân tán và tự động hóa | Không phụ thuộc duy nhất IP vì NAT/VPN/mobile |
| **Send rate limit** | Ngăn SMS/email bombing và tiêu tốn chi phí | Giới hạn resend và số kênh |
| **Challenge expiration** | Thu hẹp thời gian mã có thể bị lạm dụng | TTL ngắn nhưng đủ cho trải nghiệm và độ trễ |
| **Single-use consumption** | Chặn replay sau thành công | Cần atomic update/transaction |
| **Purpose binding** | Chặn mã login dùng cho hành động khác | Mỗi action có challenge/transaction riêng |
| **Risk-based step-up** | Tăng bảo vệ khi có tín hiệu bất thường | Không dùng risk score không giải thích được làm lý do duy nhất |

### Replay và race condition

Một lỗi phổ biến là:

1. Request A đọc challenge thấy chưa tiêu thụ.
2. Request B cũng đọc cùng trạng thái.
3. Cả hai cùng xác minh mã đúng.
4. Cả hai cùng tạo session trước khi trạng thái consumed được lưu.

Giải pháp là kiểm tra và tiêu thụ challenge trong một transaction hoặc compare-and-swap nguyên tử, bảo đảm **chỉ một request chuyển được trạng thái PENDING → CONSUMED**. Các request tiếp theo nhận kết quả replay/đã dùng.

### Không chỉ giới hạn nhập mã

Kẻ tấn công có thể lạm dụng endpoint gửi mã để:

- Gửi hàng nghìn tin nhắn hoặc email làm phiền nạn nhân.
- Làm cạn ngân sách SMS provider.
- Dò xem email/số điện thoại có tài khoản hay không.
- Gây lockout hoặc làm nhiễu tín hiệu bảo mật.

Vì vậy, rate limit phải áp dụng cả **issue, resend và verify**, có giám sát chi phí và phản hồi nhất quán để tránh account enumeration.

## 8. One-time code và phishing resistance

One-time code thông thường là **phishing-vulnerable**: người dùng có thể bị dụ nhập mã vào website giả. Attacker có thể chuyển tiếp mã đến website thật trước khi mã hết hạn, sau đó lấy session hoặc hoàn tất đăng nhập.

| Phương thức | Chống phishing ở mức giao thức? | Lý do |
| --- | --- | --- |
| Password + SMS OTP | Không | Credential/mã có thể được chuyển tiếp |
| Password + TOTP | Không | Mã TOTP không gắn với origin của website |
| Email code / magic link | Không mặc định | Token/mã có thể bị chuyển tiếp hoặc chiếm qua hộp thư |
| Push approval chung | Không mặc định | Người dùng có thể phê duyệt nhầm yêu cầu do attacker tạo |
| Passkey/WebAuthn đúng cấu hình | Có khả năng chống phishing mạnh | Assertion gắn với RP ID/origin và challenge |

Đối với tài khoản quản trị, hệ thống tài chính hoặc hành động nhạy cảm, nên ưu tiên phương thức chống phishing như passkey/WebAuthn hoặc security key đáp ứng yêu cầu. Nếu phải dùng OTP làm dự phòng, cần giới hạn chức năng, giám sát rủi ro và tránh tuyên bố rằng phương thức này chống phishing.

**Number matching** trong push MFA giúp người dùng đối chiếu yêu cầu đang hiển thị, giảm phê duyệt nhầm; nhưng không tự biến mọi push flow thành giao thức chống phishing. **Transaction signing** hoặc cơ chế ràng buộc ý định giao dịch có thể cần thiết cho các thao tác giá trị cao.

## 9. Enrollment, thay đổi kênh và khôi phục

One-time code chỉ đáng tin khi **kênh hoặc authenticator đã được liên kết an toàn** với tài khoản.

### Enrollment TOTP

1. Yêu cầu người dùng xác thực bằng phương thức hiện có hoặc quy trình tạo tài khoản đáng tin.
2. Tạo secret ngẫu nhiên đủ mạnh và hiển thị QR/secret trong phiên enrollment được bảo vệ.
3. Yêu cầu người dùng nhập mã TOTP đầu tiên để chứng minh đã thiết lập đúng authenticator.
4. Chỉ sau khi mã hợp lệ mới đánh dấu authenticator active.
5. Thông báo việc thêm authenticator; cung cấp quy trình quản lý và thu hồi.

Secret TOTP là **shared secret**: server cần dùng nó để xác minh mã. Vì vậy phải bảo vệ trong kho secret, hạn chế truy cập, mã hóa khi lưu và không đưa vào log. QR enrollment cũng chứa secret, nên không gửi qua analytics, screenshot service hoặc kênh không tin cậy.

### Đổi số điện thoại/email

Không nên chỉ yêu cầu mã gửi tới **địa chỉ/số mới do người dùng vừa nhập** rồi coi đó là bằng chứng đủ để thay kênh. Một luồng an toàn hơn:

- Xác minh quyền kiểm soát tài khoản bằng phương thức hiện có hoặc step-up phù hợp.
- Xác minh kênh mới và gắn nó với đúng account.
- Thông báo qua kênh cũ hoặc kênh độc lập khi phù hợp.
- Có thời gian chờ/kiểm tra rủi ro cho thay đổi nhạy cảm nếu chính sách yêu cầu.
- Thu hồi kênh cũ khi thay đổi đã được xác nhận và cập nhật audit.

### Recovery code

Recovery code thường được tạo một lần và cung cấp cho người dùng lưu ở nơi an toàn. Mỗi mã cần:

- Đủ ngẫu nhiên và khó đoán;
- Gắn với đúng tài khoản và mục đích recovery;
- Có thể dùng một lần, được tiêu thụ nguyên tử;
- Được lưu ở server dưới dạng verifier bảo vệ phù hợp;
- Có thể thu hồi/tạo lại một bộ mới sau khi dùng;
- Không hiển thị lại toàn bộ sau lần cấp đầu và không ghi log.

Recovery code là **credential dự phòng**. Nếu bị lộ, attacker có thể chiếm tài khoản; do đó cần thông báo khi sử dụng, theo dõi bất thường và khuyến nghị thay bộ mã sau sự kiện.

### Tài khoản bị disable

Mã đúng không được tự động vượt qua trạng thái tài khoản. Verifier phải kiểm tra trạng thái hiện hành trước khi phát session/token. Password reset, email code, SMS OTP hay recovery code không tự chuyển DISABLED thành ACTIVE; kích hoạt lại cần một quyết định có thẩm quyền riêng.

## 10. Quản lý session sau khi mã hợp lệ

Xác minh one-time code thành công chỉ là một sự kiện authentication. Ứng dụng thường tạo **session cookie** hoặc phát token cho những request tiếp theo.

Với web session:

- Session ID phải ngẫu nhiên, khó đoán và được tạo mới sau khi xác thực thành công.
- Cookie thường cần Secure, HttpOnly, SameSite phù hợp và phạm vi Domain/Path hẹp.
- Có idle timeout và absolute timeout phù hợp với mức rủi ro.
- Có khả năng thu hồi khi logout, đổi credential, mất thiết bị, account disable hoặc phát hiện session compromise.
- Chống CSRF nếu cookie được trình duyệt tự động gửi; SameSite giúp giảm một số tình huống nhưng không thay thế mọi kiểm soát.

Với access token:

- Giới hạn audience, scope và thời hạn.
- Không để bearer token trong URL hoặc log.
- Có chiến lược refresh rotation/revocation phù hợp.
- API kiểm tra chữ ký, issuer, audience, thời hạn, trạng thái tài khoản và quyền theo tài nguyên.

**Không gửi mã OTP trong mỗi API request.** Mã dùng một lần chỉ phục vụ giao dịch xác thực/step-up; session/token được phát hành sau đó có vòng đời và cơ chế bảo vệ riêng.

## 11. Thiết kế thông báo và xử lý lỗi

| Tình huống | Phản hồi người dùng | Xử lý phía server |
| --- | --- | --- |
| Mã sai | “Mã không hợp lệ hoặc đã hết hạn” | Tăng attempt counter, áp rate limit |
| Mã hết hạn | “Vui lòng yêu cầu mã mới” | Đánh dấu challenge expired |
| Mã đã dùng | Có thể trả thông báo chung | Ghi nhận replay/consumed và từ chối |
| Gửi mã quá thường xuyên | “Vui lòng chờ trước khi yêu cầu mã khác” | Áp send throttle và giám sát abuse |
| Kênh không còn hợp lệ | Hướng dẫn recovery theo chính sách | Không tiết lộ quá nhiều về account/channel |
| Tài khoản disabled | Thông báo theo policy | Không cấp session, không tự kích hoạt |
| Provider SMS/email lỗi | “Không thể gửi mã lúc này” | Retry có giới hạn, theo dõi delivery và chi phí |
| Verifier/database lỗi | “Không thể xác minh lúc này” | Không cho qua mặc định; log lỗi vận hành |

Thông báo không nên cho attacker biết chính xác một email/số điện thoại có tồn tại trong hệ thống. Tuy nhiên, sau khi người dùng đã xác thực đủ quyền, sản phẩm có thể hiển thị hướng dẫn hỗ trợ chi tiết hơn theo chính sách.

## 12. Tình huống thiết kế: đăng nhập passwordless cho cổng nhân viên

Một doanh nghiệp triển khai cổng nhân viên với hai lựa chọn: email one-time code và passkey. Nhân viên mới được mời qua email; nhân viên hiện hữu có thể thêm passkey từ trang bảo mật. Hệ thống có thao tác nhạy cảm như thay đổi tài khoản nhận lương.

### Yêu cầu

- Không dùng mật khẩu truyền thống trong luồng login mặc định.
- Mã email phải gắn với tài khoản đã được mời và mục đích login.
- Không cho phép một mã được dùng hai lần hoặc tạo nhiều session khi request song song.
- Thay đổi thông tin nhận lương phải có xác thực tăng cường và kiểm tra quyền nghiệp vụ.
- Người dùng mất email phải có quy trình recovery được phê duyệt.

### Luồng đề xuất

1. Người dùng nhập identifier; hệ thống phản hồi nhất quán để hạn chế account enumeration.
2. Nếu account đã có passkey, ưu tiên WebAuthn và tạo challenge mới.
3. Nếu dùng email code, server tạo challenge ngẫu nhiên, ràng buộc account/purpose, TTL và attempt limit; gửi đến email đã xác minh.
4. Khi nhập mã, server xác minh, tiêu thụ challenge nguyên tử và kiểm tra account vẫn active.
5. Chỉ sau khi hoàn tất verification mới tạo session cookie an toàn.
6. Với thay đổi tài khoản nhận lương, yêu cầu step-up bằng passkey hoặc phương thức được chính sách chấp nhận; OTP email thông thường có thể không đủ.
7. Nếu email bị mất, quy trình recovery xác minh người yêu cầu theo mức rủi ro và thông báo thay đổi qua kênh độc lập.

### Các chỉ số cần theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| Code issue rate / resend rate | Có bị lạm dụng gửi mã hoặc gửi spam không |
| Code verification success/failure | Tỷ lệ hoàn tất, sai mã, hết hạn và lỗi kỹ thuật |
| Replay rejection count | Có request cố sử dụng lại challenge không |
| Delivery latency/failure | Email provider có gửi kịp và ổn định không |
| Recovery completion and abuse | Người dùng hợp lệ có khôi phục được không, có đường bypass không |
| Passwordless method mix | Bao nhiêu login dùng passkey, bao nhiêu dùng email code |
| Sensitive action step-up coverage | Hành động nhạy cảm nào đã có bằng chứng đủ mạnh |

Tỷ lệ hoàn tất cao không tự chứng minh an toàn. Nếu email code được sử dụng cho toàn bộ thao tác quản trị, hệ thống có thể thuận tiện nhưng assurance không đáp ứng mục tiêu chống phishing.

## 13. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Mã hợp lệ** | Nhập đúng mã trong TTL và đúng purpose | Xác minh thành công, challenge bị tiêu thụ |
| **Mã sai** | Thử giá trị khác | Từ chối và tăng attempt count |
| **Mã hết hạn** | Nộp sau TTL | Từ chối |
| **Mã dùng lại** | Gửi lại mã đã thành công | Từ chối replay |
| **Hai request đồng thời** | Cùng gửi một mã hợp lệ | Chỉ một request tiêu thụ thành công |
| **Sai tài khoản** | Dùng mã của account A cho B | Từ chối |
| **Sai mục đích** | Dùng mã login cho đổi email | Từ chối |
| **Resend** | Yêu cầu mã mới rồi thử mã cũ | Theo policy, mã cũ bị vô hiệu hóa hoặc có trạng thái rõ ràng |
| **Brute force** | Thử quá số lần | Rate limit/chặn theo thời gian |
| **SMS/email bombing** | Gửi liên tục yêu cầu mã | Send rate limit và cảnh báo |
| **Account enumeration** | So sánh phản hồi identifier có/không tồn tại | Không rò rỉ rõ ràng qua nội dung hoặc thời gian |
| **Phishing simulation** | Nhập mã vào trang giả và chuyển tiếp | Xác định giới hạn phishing của phương thức; không tuyên bố OTP chống phishing |
| **TOTP clock drift** | Authenticator lệch thời gian trong giới hạn | Hành vi theo cửa sổ đã cấu hình |
| **TOTP replay** | Gửi lại cùng mã/bước thời gian | Từ chối theo chính sách chống dùng lại |
| **Recovery code reuse** | Dùng lại mã recovery đã tiêu thụ | Từ chối |
| **Account disabled** | Nhập mã đúng cho account disabled | Không cấp session/token |
| **Provider outage** | Làm SMS/email provider lỗi | Không bỏ qua verification; phản hồi và retry có giới hạn |
| **Session after OTP** | Xác minh mã rồi kiểm tra cookie/session | Session mới, cookie an toàn, có TTL và thu hồi |

Kiểm thử phải diễn ra trên môi trường và tài khoản được phép. Các tình huống concurrency, replay và rate limit cần kiểm tra ở phía server, không chỉ thao tác thủ công qua giao diện.

## 14. Checklist triển khai one-time code

- **Mục đích:** Mã dùng cho login, MFA, verify channel, recovery hay transaction confirmation? Có ràng buộc riêng từng purpose không?
- **Nguồn tạo:** HOTP/TOTP hay mã server-generated? Secret và CSPRNG có được bảo vệ không?
- **Enrollment:** Kênh nhận mã hoặc authenticator đã được liên kết với account bằng cách đáng tin chưa?
- **Ràng buộc:** Mã gắn đúng account, transaction, purpose và challenge ID không?
- **TTL và số lần thử:** Có thời hạn, giới hạn thử, giới hạn resend và chống enumeration không?
- **Single-use:** Tiêu thụ mã có nguyên tử và chống race/replay không?
- **Kênh truyền:** SMS/email có được đánh giá rủi ro SIM swap, mailbox compromise, forwarding và phishing không?
- **Phishing resistance:** Phương thức có bị chuyển tiếp không? Hành động nhạy cảm có nên dùng passkey/WebAuthn thay thế không?
- **Session/token:** Chỉ phát session sau verification đầy đủ? Có cookie/token bảo vệ, TTL, revocation và authorization riêng không?
- **Recovery:** Recovery code và đổi kênh có assurance phù hợp, thông báo và audit không?
- **Account lifecycle:** Account disabled hoặc credential revoked có bị từ chối không?
- **Telemetry:** Có ghi kết quả và reason code mà không lưu OTP, secret, link hoặc token thô không?

### Câu hỏi tự kiểm tra

1. HOTP khác TOTP ở đầu vào thay đổi theo counter hay thời gian như thế nào?
2. Tại sao một mã TOTP còn trong cửa sổ 30 giây vẫn có thể bị replay?
3. Với mã do server gửi qua email, những thuộc tính nào phải gắn vào challenge để tránh dùng sai tài khoản hoặc sai mục đích?
4. Vì sao SMS OTP không được coi là phương thức chống phishing?
5. Nếu hai request đồng thời cùng nộp mã đúng, hệ thống cần bảo đảm điều gì ở thao tác consume?
6. Tại sao magic link cần cân nhắc email scanner hoặc link preview tự mở URL?
7. Một tài khoản đã bị disable nhưng người dùng nhập recovery code đúng. Hệ thống có nên tạo session không?
8. Khi nào nên ưu tiên passkey/WebAuthn thay cho one-time code?

## Kết luận

**One-time code là một cách xác minh hữu ích, nhưng mức bảo vệ phụ thuộc vào cách tạo mã, ràng buộc với tài khoản và mục đích, kênh phân phối, thời hạn, giới hạn thử và cơ chế tiêu thụ một lần.** HOTP, TOTP, SMS/email code và magic link có các mô hình tin cậy khác nhau; không nên gộp chúng thành một mức assurance. Mã ngắn có thể bị đoán, phát lại hoặc chuyển tiếp qua phishing, nên phải có kiểm soát server-side, chống race condition, bảo vệ session/token và recovery. Với tài khoản hoặc hành động cần chống phishing mạnh, **passkey/WebAuthn thường là lựa chọn phù hợp hơn** khi thiết bị và quy trình hỗ trợ đáp ứng yêu cầu.
