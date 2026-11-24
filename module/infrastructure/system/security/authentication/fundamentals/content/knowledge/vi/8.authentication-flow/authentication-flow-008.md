# Success path (Luồng xác thực thành công)

> **Chương:** Authentication flow  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — nguyên lý xác thực danh tính bằng credential, mật khẩu, MFA, passkey, chứng chỉ; cách dùng token, phiên, liên kết danh tính, khôi phục tài khoản; mô hình hóa ranh giới tin cậy để chống phishing, replay và lạm dụng đăng nhập.  
> **Trọng tâm:** Theo dõi một yêu cầu hợp lệ đi từ trạng thái **chưa xác thực** đến **đã xác thực**, nhận phiên hoặc token thích hợp, rồi truy cập một tài nguyên **được phân quyền**. Mỗi bước phải có điều kiện thành công rõ ràng và được kiểm chứng bởi thành phần đáng tin cậy.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **success path** hay **happy path** của một luồng xác thực và phân biệt kết quả xác thực với kết quả phân quyền.
2. Chỉ ra vai trò của người dùng, client, authenticator, máy chủ xác thực/verifier, Identity Provider (IdP), ứng dụng và API; xác định các **ranh giới tin cậy** giữa chúng.
3. Mô tả thứ tự xử lý an toàn từ yêu cầu đăng nhập, thử thách, kiểm chứng credential, MFA, thiết lập phiên/token đến request API đầu tiên.
4. So sánh success path của **mật khẩu + TOTP**, **passkey/WebAuthn**, **OIDC Authorization Code + PKCE** và **xác thực dịch vụ** bằng mTLS hoặc credential phù hợp.
5. Nhận biết các kiểm tra bắt buộc để chống phishing, replay, session fixation, chiếm cookie/token và liên kết tài khoản sai.
6. Đọc sơ đồ trạng thái, sequence diagram và giả mã kiểm tra thành công, rồi vận dụng vào thiết kế luồng xác thực có khả năng kiểm thử.

## 1. Success path là gì?

**Success path** là chuỗi sự kiện kỳ vọng khi chủ thể hợp lệ thực hiện đúng các bước và hệ thống kiểm chứng thành công tất cả điều kiện để xác lập trạng thái xác thực.

Ví dụ ngắn:

1. Lan mở trang đăng nhập của ứng dụng học tập.
2. Lan chọn tài khoản và chứng minh quyền kiểm soát credential đã đăng ký.
3. Máy chủ kiểm chứng bằng chứng và chính sách tương ứng.
4. Nếu chính sách yêu cầu MFA, Lan hoàn tất yếu tố tiếp theo một cách hợp lệ.
5. Máy chủ tạo phiên an toàn hoặc phát hành token có phạm vi phù hợp.
6. Lan yêu cầu xem khóa học của mình; API xác minh phiên/token **và kiểm tra quyền xem đúng khóa học**.
7. Ứng dụng trả dữ liệu được phép.

Thành công tại bước 4 hoặc 5 **không có nghĩa** mọi request về sau đều được chấp nhận. Một người đã xác thực vẫn có thể không có quyền quản trị hoặc không được xem khóa học của người khác.

### Điều kiện “thành công” cần chính xác

| Mốc | Kết luận hợp lệ | Điều chưa được phép suy ra |
| --- | --- | --- |
| Client nhận response HTTP 200 của trang login | Giao tiếp đã nhận một phản hồi ứng dụng. | Chưa chứng minh credential hợp lệ; không thể dựa vào mã 200 đơn thuần. |
| Password hoặc assertion được verifier chấp nhận | Một bằng chứng đã qua kiểm chứng. | Chưa chắc đạt MFA hoặc đủ chính sách cho thao tác nhạy cảm. |
| Tất cả yêu cầu xác thực của luồng đạt | Có thể xác lập ngữ cảnh xác thực theo chính sách. | Chưa cấp quyền tới mọi tài nguyên. |
| Session/token được tạo và gửi đúng client | Client có cơ chế trình kết quả đăng nhập cho các request tiếp theo. | Token chưa chắc dành cho mọi API; bearer token vẫn có nguy cơ bị đánh cắp. |
| API kiểm tra bằng chứng và quyền thành công | Request cụ thể có thể thực hiện. | Không trao quyền vô hạn cho những request khác. |

**Success path đúng nghĩa là chuỗi kiểm chứng an toàn**, không đơn giản là “nhập đúng mật khẩu rồi chuyển đến dashboard”.

## 2. Các thành phần tham gia và ranh giới tin cậy

Một luồng xác thực có thể có những vai trò sau:

| Thành phần | Trách nhiệm | Giới hạn tin cậy |
| --- | --- | --- |
| **Người dùng/chủ thể** | Bắt đầu đăng nhập và kiểm soát authenticator hợp lệ. | Hành động có thể bị phishing hoặc thao túng; không dựa vào lời tự khai để cấp quyền. |
| **Client (browser/mobile app)** | Hiển thị giao diện, gửi yêu cầu và nhận trạng thái phiên. | Có thể bị sửa, giả lập hoặc chịu XSS; dữ liệu do client gửi phải được xác minh. |
| **Authenticator** | Bảo vệ hoặc sử dụng bí mật/khóa, tạo bằng chứng xác thực. | Cần được gắn với tài khoản và quản lý vòng đời; thiết bị có thể bị mất hoặc bị chiếm. |
| **Verifier / dịch vụ xác thực** | Phát thử thách khi cần, xác minh credential, kiểm tra chính sách và quyết định xác thực. | Là thành phần tin cậy; phải bảo vệ secret, khóa, kết nối và trạng thái thử thách. |
| **IdP** | Xác thực chủ thể và cung cấp kết quả theo giao thức liên kết cho ứng dụng tin cậy. | Ứng dụng chỉ chấp nhận assertion/token từ nguồn, đối tượng nhận và luồng đã cấu hình. |
| **Ứng dụng (Relying Party, RP)** | Tiếp nhận kết quả xác thực, ánh xạ chủ thể, tạo phiên ứng dụng và điều phối trải nghiệm. | Phải kiểm chứng kết quả từ IdP; không lấy email làm căn cứ gộp tài khoản tùy tiện. |
| **API / resource server** | Kiểm tra bằng chứng truy cập và quyền trên tài nguyên. | Không tin userId, role hay cờ mfaPassed do client tự đặt. |
| **Kho lưu danh tính / phiên** | Lưu liên kết credential, trạng thái tài khoản, phiên và chính sách. | Chỉ các thành phần được cấp quyền mới được đọc/ghi; cần bảo vệ và thu hồi. |

Không phải hệ thống nào cũng có tất cả vai trò dưới dạng dịch vụ riêng. Trong ứng dụng đơn giản, verifier, ứng dụng và kho phiên có thể nằm cùng máy chủ. Trong SSO, IdP thường nằm ở hệ thống khác. **Trách nhiệm kiểm chứng vẫn phải rõ ràng dù kiến trúc triển khai khác nhau.**

### Sơ đồ ranh giới

~~~mermaid
flowchart LR
    subgraph Untrusted["Phía người dùng / client"]
        U["Người dùng"]
        C["Browser / mobile"]
        K["Authenticator"]
        U --> C
        U --> K
    end
    subgraph Trusted["Phía dịch vụ"]
        V["Verifier / IdP"]
        S["Dịch vụ phiên"]
        R["Ứng dụng / API"]
        D[("Danh tính và chính sách")]
        V --> D
        V -->|"Kết quả hợp lệ"| S
        S --> R
        R --> D
    end
    C -->|"Yêu cầu, bằng chứng"| V
    K -->|"Assertion / OTP theo luồng"| C
    C -->|"Cookie / token cho request"| R
~~~

Các đường nối trong sơ đồ **không tự biểu thị quan hệ tin cậy**. Ví dụ, một JWT chỉ đáng tin sau khi dịch vụ nhận kiểm tra chữ ký, bên phát hành, audience, thời hạn và điều kiện áp dụng; một kết quả từ IdP chỉ đáng tin trong mối quan hệ liên kết được cấu hình đúng.

## 3. Điều kiện đầu vào để success path có thể xảy ra

Trước khi đăng nhập, một số điều kiện thường đã có:

1. **Danh tính/tài khoản đã tồn tại và ở trạng thái cho phép đăng nhập.** Việc tạo tài khoản hoặc kiểm chứng danh tính ngoài đời có thể thuộc quy trình enrollment riêng.
2. **Credential hoặc authenticator đã được gắn hợp lệ** với tài khoản, chẳng hạn bản băm mật khẩu, khóa công khai passkey, bí mật TOTP hoặc chứng chỉ dịch vụ được chấp nhận.
3. **Chính sách xác thực được xác định:** loại bằng chứng, MFA, yêu cầu user verification, mức assurance, giới hạn thử và hành động được phép.
4. **Kênh truyền được bảo vệ:** ứng dụng dùng HTTPS/TLS và cấu hình domain, origin, redirect URI, RP ID, khóa hay trust anchor đúng trường hợp.
5. **Hệ thống có thể tạo trạng thái đăng nhập:** bộ tạo session ID bảo mật, kho phiên, cơ chế ký/kiểm tra token và chính sách hiệu lực.
6. **Kênh khôi phục và thu hồi được thiết kế:** thành công hôm nay không được khiến một credential đã vô hiệu hóa vẫn hoạt động về sau.

Các điều kiện này là **tiền đề**. Khi chúng không đạt, hệ thống cần đi qua một nhánh lỗi hoặc khôi phục riêng; success path không được “nới kiểm tra cho thuận tiện” để buộc đăng nhập thành công.

## 4. Máy trạng thái: từ chưa xác thực đến phiên hợp lệ

Một cách thiết kế tốt là đặt tên rõ từng trạng thái và điều kiện để đi tiếp.

~~~mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> AuthenticationStarted: Bắt đầu luồng hợp lệ
    AuthenticationStarted --> ChallengeIssued: Tạo thử thách / transaction
    ChallengeIssued --> EvidencePresented: Client trình bằng chứng
    EvidencePresented --> PrimaryVerified: Verifier kiểm chứng thành công
    PrimaryVerified --> AdditionalVerification: Chính sách cần MFA / step-up
    AdditionalVerification --> AuthenticationSatisfied: Yếu tố bổ sung hợp lệ
    PrimaryVerified --> AuthenticationSatisfied: Chính sách đã đủ
    AuthenticationSatisfied --> SessionEstablished: Tạo phiên / phát token an toàn
    SessionEstablished --> ResourceRequest: Client gửi request tiếp theo
    ResourceRequest --> AccessGranted: Bằng chứng + quyền đều hợp lệ
    AccessGranted --> [*]
~~~

Sơ đồ chỉ thể hiện **nhánh thành công**. Trong triển khai thực tế, tại mỗi bước đều có thể chuyển sang *từ chối, hết hạn, thử lại có kiểm soát, yêu cầu khôi phục hoặc kết thúc*. Không được đi thẳng từ **EvidencePresented** tới **SessionEstablished** nếu verifier chưa xác nhận toàn bộ điều kiện.

Điểm quan trọng của máy trạng thái:

- **ChallengeIssued** có trạng thái, thời hạn và mối liên hệ với transaction/luồng; không chấp nhận challenge không khớp.
- **PrimaryVerified** chưa đủ nếu cần thêm MFA.
- **AuthenticationSatisfied** là kết luận **từ máy chủ tin cậy**, không phải cờ do trình duyệt đặt.
- **SessionEstablished** cần tránh session fixation, giới hạn hiệu lực và lưu ngữ cảnh xác thực được phép.
- **AccessGranted** là kết quả của **request cụ thể** với kiểm tra quyền, không phải đặc quyền vĩnh viễn.

## 5. Các bước xử lý một success path tổng quát

### Bước 1 — Bắt đầu yêu cầu xác thực

Client khởi tạo luồng tới endpoint đăng nhập hoặc chuyển hướng đến IdP. Máy chủ gắn yêu cầu với một **transaction** hoặc trạng thái thích hợp để tránh nhầm lẫn các lần đăng nhập đồng thời và để hỗ trợ giới hạn thử sai.

Tùy phương thức, người dùng có thể nhập tên tài khoản, chọn passkey, chọn IdP hoặc đăng nhập không cần nhập username. Tên tài khoản/email là **định danh đầu vào**, chưa phải bằng chứng danh tính.

**Điều kiện thành công:** luồng đã được khởi tạo trong ngữ cảnh hợp lệ; chưa có session xác thực được cấp chỉ vì người dùng mở trang.

### Bước 2 — Phát thử thách hoặc yêu cầu bằng chứng

Với WebAuthn, verifier sinh **challenge ngẫu nhiên, khó đoán và mới**. Với password, client gửi bí mật qua kênh bảo mật để verifier kiểm tra; với OIDC, RP khởi tạo giao dịch liên kết cùng các giá trị chống nhầm lẫn/CSRF và PKCE khi dùng authorization code.

**Điều kiện thành công:** yêu cầu bằng chứng được ràng buộc với đúng luồng, đúng dịch vụ và có thời hạn/chính sách hợp lệ.

### Bước 3 — Client/Authenticator trình bằng chứng

Người dùng nhập password/TOTP, hoặc authenticator tạo assertion ký thử thách. Trong SSO, người dùng trình bằng chứng cho IdP theo chính sách của IdP rồi ứng dụng nhận kết quả theo giao thức đã thống nhất.

**Điều kiện thành công:** client gửi được bằng chứng cho **đúng bên tiếp nhận** qua kênh phù hợp; việc hiển thị “Đã gửi” không có nghĩa verifier đã chấp nhận.

### Bước 4 — Verifier xác minh bằng chứng

Verifier thực hiện kiểm tra đặc thù: mật khẩu so với bản băm chuyên dụng; TOTP so với bí mật và cửa sổ thời gian kèm chống dùng lại; WebAuthn kiểm tra challenge, origin/RP ID, chữ ký, credential và các cờ cần thiết; dịch vụ kiểm chứng token/chứng chỉ theo chính sách.

Đồng thời kiểm tra tài khoản/credential còn hiệu lực, giao dịch chưa hết hạn, giới hạn thử và trạng thái rủi ro phù hợp.

**Điều kiện thành công:** bằng chứng hợp lệ và gắn với **đúng chủ thể** đã được xác định từ quá trình kiểm chứng, không phải một userId client tự khai.

### Bước 5 — Hoàn tất MFA hoặc kiểm tra tăng cường khi được yêu cầu

Nếu chính sách cần MFA, verifier chỉ xác nhận hoàn thành khi **tất cả yếu tố bắt buộc** đã được xác minh và ràng buộc cùng một yêu cầu đăng nhập, cùng chủ thể.

Một phép kiểm tra password thành công **không được tự tạo full session** nếu TOTP/khóa bảo mật còn chưa hoàn tất. Có thể dùng trạng thái tạm thời giới hạn chỉ cho phép hoàn tất MFA; trạng thái này **không phải phiên đăng nhập đầy đủ** và không được dùng truy cập API thông thường.

**Điều kiện thành công:** đủ mức bảo đảm yêu cầu, không có lý do từ chối theo chính sách áp dụng.

### Bước 6 — Thiết lập ngữ cảnh xác thực và phiên

Máy chủ tạo **session ID mới, ngẫu nhiên, khó đoán** hoặc phát hành token theo kiến trúc. Nếu đã có session trước đó, cần xoay danh tính phiên theo chính sách để giảm nguy cơ **session fixation**. Ngữ cảnh máy chủ có thể lưu:

- Mã chủ thể nội bộ (subject ID).
- Thời điểm xác thực đạt chính sách, phương thức/mức bảo đảm có căn cứ.
- Thời điểm tạo, hết hạn, trạng thái và phạm vi phiên.
- Dấu hiệu cần thiết để hỗ trợ đăng xuất, thu hồi, step-up và audit.

**Điều kiện thành công:** bằng chứng mang phiên được phát đúng client, với thời hạn và cách bảo vệ thích hợp; không đưa secret của authenticator vào response.

### Bước 7 — Client nhận kết quả và vào ứng dụng

Client nhận cookie phiên được đặt bằng **Set-Cookie** hoặc cơ chế token phù hợp rồi chuyển tới màn hình sau đăng nhập. Giao diện dựa vào **phản hồi hợp lệ của server**, không tự xem đã đăng nhập chỉ vì localStorage có chuỗi “loggedIn=true”.

**Điều kiện thành công:** client có thể thực hiện request tiếp theo và ứng dụng xác định được trạng thái qua cơ chế phía máy chủ.

### Bước 8 — API kiểm tra phiên/token và phân quyền

Khi client tải dữ liệu riêng tư, API kiểm tra:

1. Session ID/token có hợp lệ, đúng nguồn và chưa hết hạn hoặc chưa bị thu hồi theo kiến trúc không?
2. Bằng chứng có dành cho API này, đúng audience/phạm vi và ngữ cảnh không?
3. Chủ thể có quyền thực hiện **hành động cụ thể trên tài nguyên cụ thể** không?
4. Thao tác có yêu cầu mức bảo đảm, độ mới của xác thực hoặc step-up bổ sung không?

**Điều kiện thành công:** chỉ request thỏa **cả xác thực lẫn phân quyền** mới nhận dữ liệu/hành động.

### Bước 9 — Duy trì, giới hạn và kết thúc phiên

Trong phiên đang hoạt động, hệ thống tiếp tục áp thời hạn, xử lý đăng xuất, thay credential, khóa tài khoản và các sự kiện rủi ro. Nếu truy cập hành động nhạy cảm, có thể yêu cầu reauthentication/step-up thay vì dùng mãi kết quả đăng nhập ban đầu.

Success path đầy đủ vì vậy **không kết thúc ở một lần redirect**; nó còn bao gồm việc sử dụng và quản lý đúng kết quả xác thực.

## 6. Sequence diagram: đăng nhập, cấp phiên và tải dữ liệu

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Client as Browser / Mobile
    participant Auth as Verifier / Auth service
    participant Store as Danh tính và phiên
    participant API as Resource API
    User->>Client: Bắt đầu đăng nhập
    Client->>Auth: Yêu cầu mở luồng xác thực
    Auth->>Store: Tra chính sách và credential phù hợp
    Store-->>Auth: Thông tin cần kiểm chứng
    Auth-->>Client: Challenge / transaction hợp lệ
    User->>Client: Trình bằng chứng bằng authenticator
    Client->>Auth: Gửi bằng chứng trong luồng hiện tại
    Auth->>Auth: Kiểm chứng bằng chứng và chính sách
    opt Cần yếu tố bổ sung
        Auth-->>Client: Yêu cầu MFA phù hợp
        User->>Client: Hoàn thành thử thách MFA
        Client->>Auth: Bằng chứng MFA
        Auth->>Auth: Kiểm chứng cùng subject/transaction
    end
    Auth->>Store: Tạo phiên mới, ghi ngữ cảnh xác thực
    Store-->>Auth: Phiên hợp lệ
    Auth-->>Client: Set-Cookie / kết quả xác thực
    Client->>API: Request với cookie/token
    API->>Store: Kiểm tra trạng thái và quyền nếu cần
    Store-->>API: Chủ thể, trạng thái, chính sách
    API-->>Client: Trả dữ liệu đã được cho phép
~~~

Đây là sơ đồ **mang tính khái niệm**. Trong WebAuthn, authenticator thường tạo assertion mà trình duyệt chuyển đến verifier. Trong OIDC, các bên và thông điệp khác đi đáng kể. Không dùng sơ đồ này như mô tả chuẩn của mọi giao thức.

## 7. Ví dụ A — Success path với mật khẩu và TOTP

Xét ứng dụng dùng mật khẩu làm yếu tố thứ nhất và ứng dụng TOTP làm yếu tố thứ hai.

### 7.1 Luồng thành công

1. Minh truy cập trang đăng nhập qua HTTPS, nhập định danh và mật khẩu.
2. Server tìm bản ghi xác thực, áp kiểm soát thử và kiểm tra mật khẩu với **bản băm có salt** do thuật toán chuyên dụng như Argon2id tạo.
3. Mật khẩu hợp lệ; server tạo trạng thái **pending_mfa** ngắn hạn, gắn với tài khoản và giao dịch hiện tại.
4. Minh mở ứng dụng TOTP đã đăng ký và nhập mã còn hợp lệ.
5. Server kiểm tra mã theo bí mật của **chính tài khoản đó**, với cửa sổ thời gian, giới hạn thử và cơ chế tránh sử dụng lại mã thành công.
6. Server đánh dấu giao dịch xác thực đã hoàn tất, vô hiệu hóa trạng thái tạm thời rồi tạo **session ID mới**.
7. Server đặt cookie phiên, trả response thành công; Minh mở trang khóa học.
8. API kiểm tra phiên và quyền truy cập khóa học, rồi trả dữ liệu cho Minh.

### 7.2 Giả mã phía server

~~~text
function loginWithPasswordAndTotp(identifier, password, totpCode, context):
    transaction = loadActiveAuthenticationTransaction(context)
    if transaction is absent or transaction.isExpired:
        return REJECT_SAFELY

    account = resolveAccountForAuthentication(identifier)

    if shouldRateLimit(context, account):
        return REJECT_SAFELY

    if !verifyPasswordUsingStoredPasswordHash(account, password):
        recordFailedAttempt()
        return REJECT_SAFELY

    markPrimaryVerified(transaction, account.internalId)

    otpAuthenticator = getActiveTotpAuthenticator(account.internalId)
    if otpAuthenticator is absent:
        return REJECT_SAFELY

    if !verifyTotp(
            otpAuthenticator,
            totpCode,
            acceptableTimeWindow,
            replayProtection):
        recordFailedAttempt()
        return REJECT_SAFELY

    if !passesAdditionalPolicies(account, context):
        return REJECT_SAFELY

    finishAndInvalidateTransaction(transaction)
    session = issueNewSession(
        subjectId = account.internalId,
        authenticationMethods = ["password", "totp"],
        lastQualifyingAuthAt = currentTime,
        expiryPolicy = configuredPolicy
    )
    return setProtectedSessionCookie(session)
~~~

Giả mã cố ý không triển khai thuật toán TOTP, kiểm tra mật khẩu hoặc session ID. Các bước này phải dùng thư viện/cấu hình phù hợp; chỉ minh họa **trình tự tin cậy và điều kiện chuyển trạng thái**. Trong triển khai hai request, bước kiểm tra mật khẩu và TOTP có thể tách endpoint; khi đó transaction pending MFA phải bị ràng buộc, hết hạn và không cấp quyền vượt quá việc hoàn tất MFA.

### 7.3 Kết quả bảo mật

Đây có thể là MFA nếu hai nhóm yếu tố đã được đăng ký và kiểm chứng đúng cách. Nhưng TOTP vẫn có thể bị **phishing thời gian thực**: trang giả lấy mật khẩu và mã để chuyển ngay đến server thật. Do đó, với tác vụ đòi hỏi chống phishing mạnh, nên cân nhắc passkey/FIDO2 hoặc phương thức đáp ứng chính sách phù hợp.

Không nên ghi password hoặc TOTP vào log. Thông điệp lỗi cho người dùng phải tránh tiết lộ tùy tiện tài khoản tồn tại hay không; việc này là một phần bảo vệ luồng, kể cả khi ví dụ đang mô tả nhánh thành công.

## 8. Ví dụ B — Success path với passkey/WebAuthn

Passkey dựa trên mật mã khóa công khai. Khi đăng ký, **khóa công khai và credential ID** được gắn với tài khoản; **khóa riêng** được authenticator bảo vệ và không gửi cho server trong lần xác thực thông thường.

### 8.1 Luồng xác thực thành công

1. Người dùng mở đúng origin của ứng dụng và chọn đăng nhập bằng passkey. Tùy thiết kế, giao diện có thể cho chọn tài khoản trước hoặc dùng **discoverable credential**.
2. Server tạo challenge ngẫu nhiên mới, khó đoán, lưu liên kết với giao dịch, thời hạn và **Relying Party ID (RP ID)**.
3. Browser gọi WebAuthn để lấy assertion từ authenticator phù hợp. Authenticator có thể yêu cầu mở khóa cục bộ bằng PIN hoặc sinh trắc và tạo chữ ký bằng khóa riêng.
4. Browser gửi assertion về server. Server kiểm tra **challenge**, **origin**, **RP ID hash**, chữ ký theo khóa công khai đã lưu, credential ID, cờ **user presence** và **user verification** nếu chính sách yêu cầu, cùng các thông tin/điều kiện khác của giao thức.
5. Server ánh xạ credential được kiểm chứng tới đúng tài khoản, kiểm tra trạng thái và chính sách; challenge được đánh dấu dùng xong.
6. Server tạo phiên hoặc cấp kết quả xác thực mới, trả response hợp lệ.
7. Client sử dụng phiên để gọi API; API kiểm tra quyền theo từng tài nguyên.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Browser
    participant Authenticator as Passkey authenticator
    participant Server as WebAuthn verifier
    User->>Browser: Chọn đăng nhập bằng passkey
    Browser->>Server: Xin authentication options
    Server-->>Browser: Challenge mới, RP ID, options
    Browser->>Authenticator: navigator.credentials.get(options)
    Authenticator->>Authenticator: Kiểm tra người dùng nếu được yêu cầu
    Authenticator-->>Browser: Assertion đã ký
    Browser->>Server: Gửi assertion và transaction
    Server->>Server: Kiểm tra challenge/origin/RP ID/chữ ký/cờ
    Server->>Server: Liên kết credential với subject hợp lệ
    Server-->>Browser: Phiên đã xác thực
~~~

### 8.2 Vì sao success path này giúp chống phishing?

WebAuthn ràng buộc phản hồi với RP ID và origin theo quy tắc giao thức, đồng thời dùng challenge mới. Website giả tại domain khác không thể đơn giản lấy một **mật khẩu dùng lại** hay một assertion hợp lệ cho RP thật.

Tuy nhiên, đăng nhập bằng passkey **không tự loại bỏ** nguy cơ đánh cắp session cookie, XSS, thiết bị bị chiếm hoặc quy trình khôi phục yếu. Mức bảo đảm cũng phụ thuộc cách authenticator giữ khóa, user verification, khả năng đồng bộ và các yêu cầu áp dụng.

**Không tự kết luận mọi passkey đều là MFA hoặc AAL3.** Cần xét kiểu authenticator, cờ xác minh người dùng, yêu cầu chính sách và toàn bộ profile bảo đảm nếu sử dụng nhãn AAL chính thức.

## 9. Ví dụ C — Success path SSO với OpenID Connect và PKCE

Trong SSO, ứng dụng (**Relying Party/RP**) giao bước xác thực danh tính cho **Identity Provider (IdP)** được tin cậy. Một luồng phổ biến là **OIDC Authorization Code Flow** có **PKCE**.

### 9.1 Các bước chính

1. Người dùng yêu cầu đăng nhập tại RP. RP tạo giao dịch và giá trị **state** để ràng buộc request/callback, **nonce** nếu luồng yêu cầu, cùng **code_verifier** bí mật và **code_challenge** dẫn xuất theo PKCE.
2. RP chuyển browser đến **authorization endpoint** của đúng IdP đã cấu hình, kèm tham số phù hợp như client ID, redirect URI đã đăng ký, scope, state, nonce và code_challenge.
3. IdP xác thực người dùng theo chính sách (có thể gồm MFA/passkey), rồi sau khi các điều kiện luồng được đáp ứng chuyển browser trở lại **redirect URI** đã đăng ký với **authorization code** và state.
4. RP kiểm tra callback thuộc giao dịch đã khởi tạo, **state** khớp và các điều kiện bảo vệ callback. RP trao code với **token endpoint** của IdP qua kênh phù hợp, trình **code_verifier** và xác thực client nếu loại client yêu cầu.
5. IdP kiểm chứng code và PKCE, cấp token theo giao thức. RP kiểm tra **ID token** theo cấu hình: chữ ký và thuật toán, **issuer**, **audience**, **thời hạn**, nonce và các điều kiện cần thiết.
6. RP ánh xạ cặp **issuer + subject** từ ID token đã được kiểm chứng tới **tài khoản nội bộ đúng**. Không tự gộp hai tài khoản chỉ vì email trùng.
7. RP tạo **session ứng dụng** cho người dùng. Khi ứng dụng gọi API, access token phải dành cho **resource server tương ứng** và được kiểm chứng theo chính sách; ID token không phải token dùng thay thế tùy tiện cho mọi API.
8. API kiểm tra quyền của chủ thể và ngữ cảnh truy cập cho request cụ thể.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as Ứng dụng (RP)
    participant B as Browser
    participant IdP as Identity Provider
    U->>RP: Yêu cầu đăng nhập
    RP->>RP: Sinh state, nonce, PKCE verifier/challenge
    RP-->>B: Redirect đến authorization endpoint
    B->>IdP: Authorization request
    IdP->>IdP: Xác thực người dùng theo chính sách
    IdP-->>B: Redirect về RP với code + state
    B->>RP: Callback với code + state
    RP->>RP: Đối chiếu giao dịch và state
    RP->>IdP: Đổi code tại token endpoint, dùng code_verifier
    IdP-->>RP: Token response hợp lệ
    RP->>RP: Xác minh ID token, issuer, audience, nonce
    RP->>RP: Ánh xạ issuer + subject vào tài khoản
    RP-->>B: Thiết lập session RP
~~~

Sơ đồ mô tả một kiến trúc web với **RP backend** tham gia trao đổi code. Trong SPA/mobile, cách lưu và trao đổi token phụ thuộc loại client, profile bảo mật và thiết kế BFF/PKCE. Không được giả định có thể đưa client secret vào ứng dụng công khai rồi giữ nó bí mật.

### 9.2 Ba phân biệt quan trọng

**OIDC ID token** cung cấp thông tin về sự kiện xác thực cho đúng client khi được xác minh. **OAuth access token** được dùng để truy cập tài nguyên được cấp quyền theo audience và phạm vi. **Refresh token** nếu được cấp dùng để lấy token mới theo chính sách; nó cần được bảo vệ, giới hạn và xoay/thu hồi phù hợp.

Một token mới có **iat** mới **không chứng minh người dùng vừa xác thực lại**. Nếu cần độ mới cho hành động nhạy cảm, sử dụng ngữ nghĩa **auth_time** và cơ chế yêu cầu reauthentication/step-up được IdP hỗ trợ, với cách kiểm chứng phù hợp.

**SSO không phải một yếu tố xác thực mới.** IdP thực thi phương thức xác thực cụ thể; ứng dụng tiếp nhận phải biết đủ ngữ cảnh từ nguồn tin cậy nếu chính sách yêu cầu mức assurance nhất định.

## 10. Ví dụ D — Success path của dịch vụ gọi dịch vụ

Trong hệ thống phân tán, chủ thể có thể là một **dịch vụ**, không phải con người.

Ví dụ **dịch vụ đơn hàng** gọi **API thanh toán**:

1. Dịch vụ đơn hàng có danh tính riêng và credential đã được cấp/đăng ký.
2. Khi thiết lập kết nối **mTLS**, mỗi bên kiểm tra chứng chỉ và chứng minh quyền sở hữu khóa riêng tương ứng theo cơ chế TLS; API ánh xạ danh tính dịch vụ đã xác thực theo chính sách.
3. Hoặc dịch vụ dùng một cơ chế cấp **access token cho workload/client** (ví dụ OAuth client credentials khi phù hợp), rồi gửi token dành cho API thanh toán.
4. API kiểm chứng danh tính dịch vụ, trạng thái khóa/chứng chỉ hoặc token, audience, thời hạn và quyền tối thiểu đối với tác vụ.
5. API chỉ chấp nhận thao tác được phép và ghi nhận sự kiện cần thiết.

Ví dụ logic:

~~~text
Service A --mTLS hoặc access token phù hợp--> API B
API B:
  verify service credential / token
  establish service identity
  check permitted operation and resource scope
  execute operation only if allowed
~~~

**Tên dịch vụ trong header HTTP do client tự đặt không phải credential.** Chứng chỉ hợp lệ của một thiết bị/dịch vụ cũng không tự chứng minh người dùng cuối đã thực hiện MFA.

Nếu API thực hiện hành động **thay mặt người dùng**, cần mô hình ủy quyền hoặc trao đổi token phù hợp để phân biệt **dịch vụ đang gọi** và **người dùng được đại diện**; không tự sao chép userId từ request để coi đó là danh tính đã xác thực.

## 11. Phiên và token: làm sao duy trì kết quả thành công?

Phần lớn ứng dụng không muốn yêu cầu mật khẩu, passkey hoặc MFA cho **mỗi** request. Sau lần xác thực đủ điều kiện, hệ thống duy trì một ngữ cảnh truy cập bằng phiên hoặc token.

| Cơ chế | Điều được lưu/trình | Kiểm tra cần thiết |
| --- | --- | --- |
| **Server-side session** | Browser giữ session ID; server lưu trạng thái và chủ thể liên quan. | ID khó đoán, tồn tại, còn hạn, chưa thu hồi, đúng ngữ cảnh, có quyền. |
| **Access token** | Client trình token cho resource server phù hợp. | Chữ ký/MAC nếu dùng, issuer, audience, hạn dùng, phạm vi, trạng thái và ràng buộc theo chính sách. |
| **Refresh token** | Credential có quyền xin access token mới trong phạm vi cho phép. | Lưu an toàn, giới hạn hiệu lực, phát hiện tái sử dụng/xoay vòng hoặc ràng buộc và thu hồi theo thiết kế. |
| **ID token (OIDC)** | Truyền thông tin đăng nhập từ IdP tới RP nhận đúng client. | Kiểm tra token và ngữ cảnh giao thức; không dùng thay access token cho API khác. |

### Ví dụ response thiết lập phiên web

~~~http
HTTP/1.1 303 See Other
Location: /dashboard
Set-Cookie: __Host-sid=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Đây là **ví dụ cấu trúc**, không chứa session ID thật. Cookie có tiền tố **__Host-** phải đáp ứng điều kiện của trình duyệt, gồm Secure, Path=/ và không có thuộc tính Domain. **HttpOnly** giúp ngăn JavaScript đọc trực tiếp cookie; **Secure** giới hạn truyền qua kết nối bảo mật; **SameSite** hỗ trợ giảm một số tình huống CSRF, nhưng **không thay thế toàn bộ cơ chế chống CSRF**, đặc biệt ở các request thay đổi trạng thái.

Với ứng dụng browser, nhiều kiến trúc ưu tiên session qua cookie HttpOnly hoặc **Backend for Frontend (BFF)** để hạn chế token nhạy cảm xuất hiện trong JavaScript. Lưu bearer token bền lâu ở vùng dữ liệu mà JavaScript dễ đọc làm tăng hậu quả của XSS.

### Thời hạn và chuyển trạng thái

- **Idle timeout:** giảm thời gian phiên không hoạt động còn có thể bị sử dụng.
- **Absolute timeout:** giới hạn thời gian tối đa bất kể hoạt động.
- **Session rotation:** làm mới session ID sau các mốc nhạy cảm, đặc biệt khi chuyển từ chưa đăng nhập sang đã đăng nhập.
- **Logout/revocation:** chấm dứt hiệu lực trong phạm vi kiến trúc; token tự chứa có thể tiếp tục dùng tới khi hết hạn nếu không có cơ chế xử lý bổ sung.
- **Reauthentication/step-up:** xác minh lại hoặc nâng mức bảo đảm nếu hành động yêu cầu.

Có session hợp lệ chỉ có nghĩa **bằng chứng truy cập hiện tại qua các kiểm tra áp dụng**; nó không phải cam kết vĩnh viễn về người đang ngồi trước thiết bị.

## 12. Thành công ở API: xác thực rồi mới phân quyền

Giả sử Minh đã đăng nhập thành công và muốn xem một khóa học. API không thể chỉ dựa vào một URL chứa mã khóa học.

~~~http
GET /api/courses/course-123/progress HTTP/1.1
Host: learn.example.test
Cookie: __Host-sid=<opaque-random-value>
Accept: application/json
~~~

Server cần:

1. Trích xuất bằng chứng phiên theo cách đã cấu hình.
2. Kiểm chứng phiên hợp lệ, chưa hết hạn hoặc bị vô hiệu hóa.
3. Xác định **subjectId đáng tin** từ phiên hoặc token; không lấy **subjectId** từ payload do client tự đặt.
4. Kiểm tra subjectId có quyền xem **course-123** hoặc tiến độ học tương ứng.
5. Áp các điều kiện nghiệp vụ, assurance/độ mới nếu thao tác cần.
6. Trả đúng dữ liệu cho đúng chủ thể; nếu không đạt thì từ chối.

~~~text
function getCourseProgress(request, courseId):
    principal = authenticateRequestOnServer(request)
    if principal is absent:
        return UNAUTHENTICATED

    if !isActive(principal.subjectId):
        return DENIED

    if !canViewProgress(principal.subjectId, courseId):
        return FORBIDDEN

    progress = loadPermittedProgress(principal.subjectId, courseId)
    return OK(progress)
~~~

**Điểm kiểm soát:** dù client gửi **role=admin**, **isAuthenticated=true** hoặc một tên tài khoản khác, API vẫn phải sử dụng thông tin lấy từ **bằng chứng đã được xác minh và nguồn quyền đáng tin cậy**. Tránh lỗi IDOR/BOLA bằng phân quyền trên từng tài nguyên.

## 13. Success path và chống phishing, replay, chiếm phiên

Một luồng có thể *hoạt động đúng chức năng* nhưng vẫn thiếu bảo vệ bảo mật. Khi thiết kế nhánh thành công, cần biết **mỗi biện pháp bảo vệ áp vào bước nào**.

| Rủi ro | Bước dễ bị khai thác | Kiểm soát thích hợp |
| --- | --- | --- |
| **Phishing mật khẩu/OTP** | Client nhập bằng chứng vào trang giả. | HTTPS/origin đúng, ưu tiên WebAuthn/passkey chống phishing khi rủi ro yêu cầu; truyền thông và kiểm tra luồng. |
| **Credential stuffing** | Thử password hàng loạt. | Giới hạn thử theo rủi ro, kiểm tra mật khẩu bị lộ khi phù hợp, MFA, quan sát lạm dụng. |
| **Replay challenge/OTP** | Gửi lại bằng chứng hợp lệ. | Challenge mới, thời hạn, nonce/ràng buộc luồng, chống dùng lại OTP trong cửa sổ được chấp nhận. |
| **MFA bypass** | Tạo session sau bước thứ nhất. | Trạng thái pending MFA có quyền tối thiểu; chỉ cấp full session khi mọi yếu tố bắt buộc đạt. |
| **Session fixation** | Giữ session ID có trước khi đăng nhập. | Cấp/xoay session ID mới khi nâng trạng thái xác thực. |
| **Session hijacking** | Đánh cắp cookie hoặc bearer token. | Cookie bảo vệ, giảm XSS, token scope/TTL phù hợp, thu hồi, giám sát và reauthentication. |
| **CSRF** | Trình duyệt gửi request có cookie ngoài ý muốn. | CSRF token hoặc cơ chế phù hợp, SameSite như biện pháp hỗ trợ, kiểm tra origin khi thích hợp. |
| **OIDC mix-up / callback tampering** | Nhận callback/token sai luồng hoặc sai IdP. | Ràng buộc giao dịch, state, issuer, redirect URI, PKCE, nonce và xác minh token. |
| **Gộp sai tài khoản liên kết** | Dùng email để nối danh tính từ IdP khác. | Ánh xạ issuer+subject, kiểm chứng quyền kiểm soát các tài khoản trước khi liên kết. |
| **Lạm dụng khôi phục** | Thay authenticator bằng đường reset yếu. | Khôi phục/enrollment có mức bảo vệ tương xứng; thông báo thay đổi và xử lý phiên/credential cũ. |
| **Lạm dụng quyền sau đăng nhập** | Dùng ID khác hoặc role tự khai. | API kiểm tra quyền theo subject, đối tượng, hành động và ngữ cảnh. |

**Không có một yếu tố nào bảo vệ mọi bước.** MFA tăng khó khăn khi kẻ tấn công chỉ có một yếu tố; passkey giảm nguy cơ phishing; các biện pháp phiên và phân quyền bảo vệ giai đoạn **sau đăng nhập**.

## 14. Logging và kiểm thử success path

Luồng thành công cần đủ dấu vết để vận hành, phát hiện bất thường và điều tra sự cố, nhưng không được đưa bí mật vào log.

### Sự kiện nên quan sát

- Khởi tạo transaction và phương thức được yêu cầu, với mã giao dịch không nhạy cảm.
- Phương thức xác thực hoàn thành; có đạt chính sách MFA/assurance cần thiết không.
- Session mới được tạo, phiên được xoay hoặc xác thực lại được yêu cầu.
- Đăng nhập qua IdP nào, với subject ID nội bộ và các định danh được rút gọn/giới hạn phù hợp.
- API cho phép hay từ chối hành động nhạy cảm, dựa trên kết quả kiểm tra quyền.
- Những thay đổi credential, khóa tài khoản và đăng xuất khi có ý nghĩa bảo mật.

**Không ghi:** mật khẩu rõ, mã OTP, secret TOTP, khóa riêng, raw session ID, access/refresh token nguyên vẹn hoặc dữ liệu sinh trắc không cần thiết. Mã phiên nội bộ có thể được tham chiếu bằng ID audit riêng hoặc dạng dẫn xuất không cho phép tái sử dụng quyền truy cập.

### Kịch bản kiểm thử có ý nghĩa

| Kịch bản | Kết quả đúng của success path |
| --- | --- |
| Credential hợp lệ, chính sách không cần MFA | Verifier xác thực thành công, cấp phiên mới, vào đúng tài khoản. |
| Password hợp lệ và MFA bắt buộc | **Chỉ sau** khi MFA hợp lệ, full session mới được tạo. |
| WebAuthn assertion đúng challenge/origin/RP ID | Verifier chấp nhận nếu mọi điều kiện khác đạt; challenge đã dùng không được chấp nhận lại. |
| OIDC callback đúng state và code + PKCE hợp lệ | RP xác minh token, ánh xạ issuer+subject và tạo session đúng tài khoản. |
| Người dùng có quyền xem tài nguyên | API chấp nhận phiên/token hợp lệ và trả **đúng dữ liệu được phép**. |
| Đăng nhập thành công sau session vô danh | Server sử dụng session ID mới/xoay phiên để tránh fixation. |
| Thao tác nhạy cảm yêu cầu reauthentication | Chỉ tiếp tục sau khi có ngữ cảnh mới, đủ bảo đảm và đủ mới. |

Để kiểm chứng nhánh thành công **mang ý nghĩa bảo mật**, cũng cần bài kiểm thử nhánh từ chối cho cùng điểm kiểm soát: challenge sai/hết hạn, MFA chưa xong, token sai audience, phiên bị thu hồi, tài nguyên không có quyền. Những trường hợp này thuộc nhánh lỗi riêng, nhưng giúp chứng minh success path không bị bỏ qua kiểm tra.

## 15. Những ngộ nhận về “đăng nhập thành công”

**Ngộ nhận 1 — “Frontend chuyển được vào dashboard nghĩa là đã xác thực.”**  
Không. UI có thể bị sửa. API phải tự xác minh phiên/token từ cơ chế đáng tin cậy.

**Ngộ nhận 2 — “Biết email/username là đủ xác định chủ tài khoản.”**  
Không. Định danh chỉ giúp chọn hoặc tham chiếu hồ sơ; verifier còn phải kiểm tra bằng chứng được gắn với nó.

**Ngộ nhận 3 — “Mật khẩu đúng là được tạo full session dù MFA chưa xong.”**  
Không. Khi MFA bắt buộc, trạng thái tạm chỉ phục vụ hoàn tất thử thách; không được trao quyền truy cập thông thường.

**Ngộ nhận 4 — “TOTP có thời hạn ngắn nên không thể replay.”**  
Không. Mã có thể bị dùng lại trong khoảng còn hiệu lực nếu server không áp cơ chế tránh tái sử dụng phù hợp.

**Ngộ nhận 5 — “Passkey hợp lệ nên mọi request trong phiên đều an toàn.”**  
Không. Session/token có thể bị đánh cắp; từng tài nguyên vẫn cần kiểm tra quyền và đôi khi xác thực lại.

**Ngộ nhận 6 — “OIDC access token và ID token dùng thay nhau được.”**  
Không. Hai loại token có mục đích, đối tượng nhận và cách kiểm chứng khác nhau.

**Ngộ nhận 7 — “Hai tài khoản trùng email nên tự liên kết được.”**  
Không. Danh tính liên kết phải dựa trên nguồn issuer, subject và quy trình chứng minh quyền kiểm soát phù hợp.

**Ngộ nhận 8 — “Client gửi mfaPassed=true để API biết đã đạt MFA.”**  
Không. Chỉ dùng ngữ cảnh xác thực đã được kiểm chứng từ server/IdP, không tin cờ do client tự đặt.

**Ngộ nhận 9 — “Mọi HTTP 200 là thành công bảo mật.”**  
Không. Cần kiểm tra chính xác trạng thái nghiệp vụ, các bước xác thực, quyền, dữ liệu và các điều kiện của luồng.

## 16. Bài tập tự kiểm tra

**Câu 1.** Hãy nêu tối thiểu bốn kiểm tra server phải hoàn tất trước khi tạo phiên sau đăng nhập mật khẩu + TOTP.

**Đáp án:** Kiểm tra mật khẩu bằng cơ chế lưu trữ an toàn; TOTP thuộc authenticator đã đăng ký cho **cùng tài khoản**; mã còn hợp lệ và chưa bị dùng lại theo chính sách; giới hạn thử/trạng thái tài khoản/chính sách MFA đều đạt. Server sau đó cấp phiên mới, bảo vệ cookie/token và ghi ngữ cảnh cần thiết.

**Câu 2.** Máy chủ xác thực passkey phải kiểm tra gì trong assertion?

**Đáp án:** Tối thiểu những điều kiện phù hợp của WebAuthn như challenge mới và khớp giao dịch, origin/RP ID, credential ID và khóa công khai đã đăng ký, chữ ký, cờ user presence/user verification theo chính sách, trạng thái credential và các điều kiện xác thực liên quan. Không tin chỉ vì browser báo “success”.

**Câu 3.** Vì sao pending MFA không được dùng gọi API xem dữ liệu riêng tư?

**Đáp án:** Vì người dùng mới vượt qua một phần chính sách; cấp quyền đầy đủ trước khi yếu tố còn lại được kiểm chứng tạo đường bỏ qua MFA.

**Câu 4.** Khi OIDC callback trả về code và state, RP cần làm gì trước khi tạo session?

**Đáp án:** Đối chiếu state/giao dịch; đổi code qua kênh đúng với PKCE và các yêu cầu client; xác minh ID token (issuer, audience, chữ ký, hạn, nonce khi cần); ánh xạ issuer+subject vào đúng tài khoản; chỉ sau đó thiết lập session hợp lệ.

**Câu 5.** Một client vừa có access token hợp lệ nhưng request tải tiến độ học của người khác. Tại sao API có thể từ chối?

**Đáp án:** Token hợp lệ chỉ xác thực hoặc biểu thị quyền truy cập theo phạm vi nhất định; API vẫn phải kiểm tra quyền trên **tài nguyên cụ thể** đối với chủ thể đã xác thực.

**Câu 6.** Vì sao sau khi đăng nhập cần tạo hoặc xoay session ID thay vì dùng nguyên ID của phiên vô danh?

**Đáp án:** Để giảm nguy cơ session fixation: attacker có thể đã biết hoặc điều khiển ID cũ, nên nếu ID đó chuyển thành phiên xác thực thì họ có thể lợi dụng.

**Câu 7.** Một access token có **iat** vừa được cập nhật có đủ chứng minh người dùng vừa xác thực lại không?

**Đáp án:** Không. iat là thời điểm phát hành token; token mới có thể xuất hiện từ refresh token hoặc SSO session cũ. Cần nguồn ngữ cảnh xác thực đáng tin cậy để kiểm tra độ mới theo chính sách.

**Câu 8.** Vì sao mTLS giữa hai dịch vụ không tự chứng minh người dùng cuối đã MFA?

**Đáp án:** mTLS có thể chứng minh danh tính dịch vụ/thiết bị kiểm soát khóa riêng, không phải bằng chứng các yếu tố của con người. Nếu request thay mặt người dùng, cần cơ chế xác thực/ủy quyền người dùng riêng.

**Câu 9.** Nếu một hệ thống báo login thành công nhưng API nhận **role=admin** từ JSON body để cho phép sửa dữ liệu, ranh giới nào đã bị vi phạm?

**Đáp án:** API đã tin dữ liệu phân quyền do client tự khai vượt qua ranh giới tin cậy. Role/quyền phải được xác định và kiểm tra ở thành phần có thẩm quyền.

**Câu 10.** Hãy chỉ ra ba nơi quan trọng cần kiểm soát replay trong success path.

**Đáp án:** Challenge/nonce của phép xác thực mật mã; mã OTP trong cửa sổ còn hiệu lực; token hoặc thông điệp yêu cầu được áp điều kiện thời hạn, audience và cơ chế chống phát lại/ràng buộc phù hợp với nghiệp vụ.

## Ghi nhớ

**Success path của xác thực** là chuỗi điều kiện đã được **server/IdP có thẩm quyền kiểm chứng**: bắt đầu giao dịch hợp lệ, trình và kiểm tra bằng chứng gắn đúng danh tính, hoàn tất MFA nếu cần, tạo phiên/token được bảo vệ, rồi kiểm tra quyền ở từng API. Kết quả xác thực và quyết định phân quyền là hai bước riêng.

Khi triển khai với mật khẩu, TOTP, passkey, chứng chỉ hay OIDC, cần giữ nguyên những nguyên tắc cốt lõi: **đúng chủ thể, đúng bằng chứng, đúng giao dịch, đúng nguồn và đối tượng nhận, đúng chính sách, đúng phạm vi quyền**. Chống phishing và replay bảo vệ bằng chứng; bảo vệ cookie/token và kiểm soát phiên bảo vệ giai đoạn sau đăng nhập; phân quyền và step-up bảo vệ hành động nhạy cảm. Một luồng chỉ được coi là thành công an toàn khi **không có bước kiểm chứng bắt buộc nào bị bỏ qua**.
