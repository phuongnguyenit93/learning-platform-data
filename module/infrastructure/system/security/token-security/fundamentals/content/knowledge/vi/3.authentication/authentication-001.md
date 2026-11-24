# Xác minh danh tính người dùng

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **xác minh danh tính trong authentication** là gì, ai thực hiện và hệ thống đang xác minh điều gì.
- Phân biệt **định danh** (identification), **xác thực** (authentication), **ủy quyền/phân quyền** (authorization) và **quản lý phiên** (session management).
- Mô tả cách mật khẩu, OTP, khóa bảo mật và passkey/WebAuthn tạo bằng chứng xác thực với mức đảm bảo khác nhau.
- Theo dõi quá trình đăng nhập qua OpenID Connect (OIDC), hiểu vai trò của Authorization Server/OpenID Provider, client, ID token, access token và refresh token.
- Kiểm tra các ràng buộc tin cậy quan trọng của token như issuer, audience, subject, thời hạn, nonce, thời điểm xác thực và trạng thái phiên.
- Nhận diện nguy cơ mạo danh, đánh cắp thông tin đăng nhập, token bị sao chép/phát lại và lựa chọn biện pháp phòng vệ phù hợp.

## 1. “Xác minh danh tính” thực sự có nghĩa gì?

Khi một người nhập tên tài khoản rồi đăng nhập, hệ thống cần trả lời hai câu hỏi riêng:

1. **Người này đang tuyên bố mình là ai?** Ví dụ: tài khoản `employee-42`. Đây là bước **định danh**.
2. **Người này đưa ra được bằng chứng phù hợp để hệ thống tin rằng họ có quyền sử dụng tài khoản đó không?** Đây là bước **xác thực**.

Bằng chứng có thể là mật khẩu, một thiết bị giữ khóa riêng, mã OTP, hoặc kết hợp nhiều yếu tố. Xác thực thành công có nghĩa hệ thống đã kiểm tra bằng chứng theo một **phương pháp và chính sách cụ thể** tại một **thời điểm cụ thể**. Nó không phải lời bảo đảm rằng con người trước màn hình chắc chắn là người được khai trong mọi bối cảnh, càng không cấp quyền truy cập vô hạn.

Ví dụ: nhân viên A đăng nhập thành công bằng passkey lúc 08:00. Đến 09:00, tài khoản A bị khóa; đến 09:05, một access token được cấp trước đó vẫn chưa hết hạn. Việc xác thực từng thành công không bắt buộc API phải chấp nhận yêu cầu lúc 09:05. API cần áp dụng chính sách hiệu lực token, trạng thái tài khoản và quyền hiện tại.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Định danh (identification) | Người dùng muốn hệ thống nhận diện tài khoản nào? | Nhập tên đăng nhập hoặc chọn tài khoản tổ chức. |
| Xác thực (authentication) | Có bằng chứng hợp lệ về quyền kiểm soát tài khoản/credential không? | Kiểm tra mật khẩu và bằng chứng từ passkey. |
| Ủy quyền/phân quyền (authorization) | Chủ thể/client được phép làm gì với tài nguyên này? | Cho phép xem đơn hàng được giao, từ chối xem đơn hàng của nhóm khác. |
| Phiên (session) | Hệ thống duy trì trạng thái đăng nhập và điều kiện tiếp tục ra sao? | Cookie phiên hết hạn, phiên bị thu hồi sau khi khóa tài khoản. |

**Phân biệt quan trọng:** Một người dùng được xác thực không mặc nhiên có mọi quyền. Một token có chữ ký hợp lệ không tự động xác minh người gửi yêu cầu hiện tại chính là người vừa đăng nhập.

## 2. Xác minh điều gì: tài khoản, yếu tố xác thực và mức đảm bảo

Trong phần lớn ứng dụng web, luồng đăng nhập xác minh **quyền kiểm soát những yếu tố gắn với một tài khoản**, không trực tiếp kiểm chứng toàn bộ danh tính pháp lý của con người. Để khẳng định họ tên, căn cước, tư cách đại diện doanh nghiệp..., hệ thống cần thêm quy trình **identity proofing** phù hợp và quản lý vòng đời thông tin đó.

Các yếu tố xác thực thường được chia như sau:

| Nhóm yếu tố | Ví dụ | Điều chứng minh | Giới hạn thường gặp |
| --- | --- | --- | --- |
| **Điều người dùng biết** (knowledge) | Mật khẩu, PIN | Biết bí mật đúng. | Có thể bị đoán, tái sử dụng, lộ qua phishing hoặc mã độc. |
| **Điều người dùng có** (possession) | Khóa bảo mật FIDO2, ứng dụng sinh OTP, thiết bị chứa khóa riêng | Kiểm soát thiết bị hoặc bí mật liên quan. | Có thể mất thiết bị; OTP vẫn có thể bị lừa nhập vào trang giả. |
| **Đặc điểm vốn có** (inherence) | Sinh trắc học dùng để mở khóa thiết bị | Người hiện tại vượt qua cơ chế xác minh cục bộ theo chính sách thiết bị. | Không tự chứng minh cho máy chủ biết danh tính pháp lý; cần xem cách hệ thống tạo và xác minh kết quả. |

**MFA (multi-factor authentication)** yêu cầu bằng chứng thuộc từ hai nhóm yếu tố **độc lập phù hợp**. Hai mật khẩu khác nhau không trở thành MFA chỉ vì có hai bước. Passkey được bảo vệ bằng xác minh người dùng tại thiết bị (PIN hoặc sinh trắc học) có thể đáp ứng mục tiêu nhiều yếu tố tùy loại authenticator và chính sách áp dụng, nhưng mức bảo đảm vẫn phải xét thiết bị, khả năng đồng bộ và cách cấu hình.

Xác thực còn chịu ảnh hưởng của:

- **Ràng buộc chống phishing:** bằng chứng có gắn với tên miền dịch vụ thực và phiên yêu cầu hay không?
- **Chống phát lại:** một bằng chứng từ lần xác thực trước có dùng lại được không?
- **Sự hiện diện/xác minh người dùng:** thiết bị có yêu cầu người dùng thao tác hoặc xác minh cục bộ không?
- **Độ mới của xác thực:** đã bao lâu kể từ khi người dùng thực sự xác thực, thay vì chỉ làm mới token?
- **Khôi phục tài khoản:** một kênh đặt lại yếu hơn có thể làm suy giảm mức bảo đảm của phương thức đăng nhập mạnh.

Ví dụ: nhận được OTP qua SMS chứng minh người dùng đang có khả năng nhận tin trên số điện thoại ở thời điểm đó, nhưng không tự xác nhận người cầm điện thoại là người đã khai trong hồ sơ; SMS cũng chịu rủi ro chuyển SIM, lừa đảo và chặn tin.

## 3. Những bên tham gia và ranh giới tin cậy

Trong một kiến trúc ứng dụng dùng OAuth 2.0/OIDC, thường có:

- **Người dùng (end-user):** thực hiện đăng nhập và có thể đồng ý cấp quyền tùy ngữ cảnh.
- **Client / Relying Party (RP):** ứng dụng muốn cho người dùng đăng nhập, ví dụ trang quản lý đơn hàng.
- **Authorization Server (AS) / OpenID Provider (OP):** thực hiện hoặc điều phối xác thực người dùng, phát hành token theo giao thức.
- **Resource Server (RS):** API nhận access token để bảo vệ dữ liệu hoặc thao tác nghiệp vụ.
- **Nguồn tài khoản/chính sách:** nơi lưu trạng thái tài khoản, credential, vai trò, quyền với tài nguyên và thông tin thu hồi phiên.

Trong OIDC, client thường **tin vào thông tin xác thực đã được OP xác minh** nếu OP đúng là nguồn tin cậy đã cấu hình và thông điệp/token vượt qua các phép kiểm tra. Client không nhất thiết tự giữ mật khẩu hay tự triển khai MFA của tổ chức.

~~~mermaid
flowchart LR
    U[Người dùng] -->|Đăng nhập| OP[OpenID Provider]
    OP -->|Kết quả xác thực / ID token| C[Ứng dụng client]
    OP -->|Access token| C
    C -->|Yêu cầu + access token| API[Resource Server / API]
    API -->|Kiểm quyền hiện hành khi cần| P[Chính sách / trạng thái tài khoản]
~~~

**Ranh giới tin cậy:** Client phải kiểm chứng kết quả đến từ **đúng OP** và được phát hành **cho chính client đó**; API phải kiểm tra access token dành **cho API**, không tin một ID token chỉ vì token ấy được ký bởi cùng tổ chức.

OAuth 2.0 chủ yếu là **khung ủy quyền**; bản thân việc có OAuth access token không tạo ra một giao thức đăng nhập đầy đủ. **OIDC** bổ sung lớp nhận diện/xác thực (đặc biệt là ID token và các quy tắc xác minh), nhờ đó ứng dụng có thể đăng nhập qua nhà cung cấp danh tính.

## 4. Xác thực bằng mật khẩu: từ bằng chứng đến kết quả

Với hệ thống dùng mật khẩu, một quy trình đơn giản có thể như sau:

1. Client dùng kết nối HTTPS gửi tên tài khoản và mật khẩu đến thành phần xác thực đúng thẩm quyền.
2. Máy chủ tìm hồ sơ credential, xác minh mật khẩu bằng cơ chế **password hashing có muối và được thiết kế cho mật khẩu** (ví dụ Argon2id với tham số phù hợp). Không lưu plaintext, không mã hóa hai chiều chỉ để lấy lại mật khẩu.
3. Máy chủ áp dụng kiểm soát thử sai, tài khoản bị vô hiệu, yếu tố bổ sung hoặc kiểm tra rủi ro theo chính sách.
4. Sau khi xác thực đạt yêu cầu, hệ thống thiết lập trạng thái phiên và có thể phát hành token phù hợp với ứng dụng đích.
5. Mỗi yêu cầu tiếp theo được xử lý theo **hiệu lực phiên/token** và **chính sách phân quyền**; không tự suy luận rằng mật khẩu vừa được nhập lại.

Ví dụ thông báo đăng nhập thất bại nên tránh tiết lộ chi tiết “tài khoản có tồn tại nhưng mật khẩu sai” cho người ngoài. Hạn chế thử sai cần xét cả tài khoản, địa chỉ mạng, thiết bị và hành vi để giảm credential stuffing mà không gây khóa tài khoản hàng loạt một cách dễ dàng.

**Không đưa mật khẩu vào JWT, access token, log hoặc thông số URL.** Nếu client là ứng dụng web, ưu tiên những luồng đăng nhập được thiết kế cho ứng dụng đó, thay vì tự thu thập rồi chuyển tiếp mật khẩu của người dùng cho nhiều dịch vụ.

### Vì sao mật khẩu đúng vẫn chưa phải kết luận cuối cùng?

Một mật khẩu đã lộ có thể được kẻ tấn công nhập đúng. Máy chủ xác minh rằng *người gửi biết mật khẩu*, nhưng không có bằng chứng chắc chắn rằng đó là chủ tài khoản. Vì vậy cần đánh giá thêm bối cảnh, khuyến khích MFA chống phishing và có kịch bản khóa/thu hồi khi phát hiện chiếm đoạt tài khoản.

## 5. MFA, OTP, passkey và WebAuthn

### 5.1. OTP bổ sung bằng chứng nhưng không miễn nhiễm phishing

TOTP thường dựa trên bí mật chia sẻ giữa máy chủ và ứng dụng xác thực để sinh mã có hiệu lực trong khoảng thời gian ngắn. Máy chủ cần kiểm tra mã, giới hạn số lần thử và cân nhắc cơ chế ngăn dùng lại cùng mã trong cửa sổ hợp lệ theo thiết kế.

Ví dụ kẻ tấn công dựng trang đăng nhập giả, dẫn người dùng nhập mật khẩu và mã TOTP, rồi chuyển tiếp ngay hai giá trị đến trang thật. Cả hai yếu tố đều **đúng**, nhưng người sử dụng chúng với dịch vụ thực có thể là kẻ tấn công. Vì vậy “có MFA” không đồng nghĩa “chống phishing”.

### 5.2. Passkey/WebAuthn xác minh bằng khóa mật mã

Khi đăng ký passkey, authenticator tạo hoặc quản lý cặp khóa liên quan đến dịch vụ. Máy chủ lưu thông tin **khóa công khai** và credential phù hợp; khóa riêng được authenticator bảo vệ. Khi đăng nhập:

1. Máy chủ tạo **challenge ngẫu nhiên, đủ mạnh và có hạn dùng**.
2. Client yêu cầu authenticator tạo **assertion** gắn với challenge và thông tin ngữ cảnh dịch vụ.
3. Authenticator xác minh yêu cầu hiện diện/xác minh người dùng theo chính sách (ví dụ chạm khóa, nhập PIN hoặc sinh trắc học cục bộ).
4. Máy chủ kiểm tra chữ ký bằng khóa công khai đã đăng ký, challenge, **origin**, **RP ID** và các cờ/trạng thái cần thiết.
5. Nếu đạt yêu cầu và tài khoản còn cho phép đăng nhập, máy chủ công nhận sự kiện xác thực.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt / Client
    participant RP as Relying Party
    participant A as Authenticator

    U->>B: Chọn đăng nhập bằng passkey
    B->>RP: Yêu cầu đăng nhập
    RP-->>B: Challenge mới + tùy chọn WebAuthn
    B->>A: Yêu cầu assertion cho RP
    A->>U: Yêu cầu hiện diện / xác minh cục bộ
    U-->>A: Xác nhận
    A-->>B: Assertion có chữ ký
    B->>RP: Gửi assertion
    RP->>RP: Xác minh chữ ký, challenge, origin, RP ID, chính sách
    RP-->>B: Xác thực thành công hoặc từ chối
~~~

**Sinh trắc học ở đây thường chỉ được dùng cục bộ** để mở quyền sử dụng khóa; máy chủ không cần nhận ảnh vân tay hoặc khuôn mặt. Cơ chế WebAuthn có khả năng chống phishing vì credential và xác minh gắn với **dịch vụ gốc (RP)**, khác với việc người dùng chủ động gõ OTP vào bất kỳ trang nào.

Phải quản lý cả vòng đời credential: đăng ký thêm khóa, mất thiết bị, vô hiệu hóa khóa, thay đổi tên miền hoặc khôi phục tài khoản. Nếu quy trình khôi phục chỉ cần một email dễ bị chiếm, mức an toàn tổng thể có thể yếu hơn luồng passkey chính.

## 6. Từ xác thực người dùng đến đăng nhập qua OIDC

Một luồng phổ biến cho ứng dụng web là **OIDC Authorization Code Flow kết hợp PKCE**, với Authorization Server/OpenID Provider là bên xác thực. Ứng dụng có thể tạo phiên riêng sau khi nhận và kiểm tra kết quả.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client/Relying Party
    participant OP as OpenID Provider
    participant API as Resource Server

    U->>C: Chọn đăng nhập
    C->>C: Tạo state + PKCE code_verifier/challenge, nonce nếu dùng
    C-->>U: Chuyển đến authorization endpoint
    U->>OP: Xác thực (ví dụ passkey + chính sách MFA)
    OP-->>C: Redirect về đúng redirect_uri + authorization code + state
    C->>C: Kiểm tra state, ràng buộc phiên đăng nhập
    C->>OP: Đổi code tại token endpoint + code_verifier
    OP-->>C: ID token + access token (+ refresh token nếu được cấp)
    C->>C: Xác minh ID token, tạo phiên ứng dụng
    C->>API: Gọi API với access token phù hợp
    API-->>C: Dữ liệu nếu token và quyền hợp lệ
~~~

Mỗi phần có nhiệm vụ riêng:

- **Authorization code** là mã ngắn hạn để đổi lấy token tại token endpoint; không phải bằng chứng trực tiếp để mở quyền gọi API.
- **PKCE** ràng buộc quá trình đổi code với bên đã khởi tạo yêu cầu, giúp giảm rủi ro code bị chặn/chiếm đoạt.
- **state** giúp ràng buộc phản hồi chuyển hướng với yêu cầu đăng nhập ban đầu, chống nhiều kiểu tấn công CSRF/nhầm phiên. Cần tạo ngẫu nhiên, kiểm tra và dùng đúng phiên.
- **nonce** trong OIDC, khi được gửi, phải được kiểm tra với giá trị trong ID token để ràng buộc token trả về với yêu cầu; quy tắc sử dụng phụ thuộc flow và cấu hình.
- **ID token** chuyển thông tin về sự kiện xác thực từ OP đến client.
- **Access token** dùng cho Resource Server có audience/phạm vi phù hợp; không phải ID token.
- **Refresh token**, nếu được cấp, dùng để lấy access token mới theo chính sách; không được dùng làm token truy cập API nghiệp vụ.

Nếu ứng dụng dùng phiên dựa trên cookie, việc nhận ID token thành công thường chỉ là **đầu vào để thiết lập phiên ứng dụng**. Cookie phiên sau đó có vòng đời, ràng buộc và cơ chế thu hồi riêng. Không nên coi việc trình duyệt đang giữ một ID token cũ là bằng chứng có người dùng hiện diện ở thời điểm hiện tại.

## 7. ID token chứng minh điều gì và cần kiểm tra ra sao?

ID token thường là JWT được ký bởi OP để client nhận thông tin xác thực. Một **payload minh họa**:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-8672",
  "aud": "orders-web-client",
  "iat": 1760000000,
  "exp": 1760000300,
  "auth_time": 1759999980,
  "amr": ["pwd", "otp"],
  "nonce": "random-request-bound-value"
}
~~~

Đây **không phải ID token hoàn chỉnh**: payload chưa có header, chữ ký hay kết quả mã hóa. Các giá trị được tạo để minh họa, không phải tài khoản hoặc bí mật thật. Không dựa vào việc *đọc được* payload mà kết luận token đáng tin.

| Claim | Ý nghĩa | Cách sử dụng cẩn trọng |
| --- | --- | --- |
| **iss** | OP đã phát hành token. | So khớp chính xác với issuer đã cấu hình qua kênh tin cậy; không chấp nhận issuer tùy ý từ dữ liệu của người dùng. |
| **sub** | Mã định danh chủ thể theo OP. | Dùng cặp **(iss, sub)** làm khóa định danh khi liên kết tài khoản; không mặc nhiên dùng email làm định danh bất biến. |
| **aud** | Client được phép nhận ID token. | Phải bao gồm **client_id** của ứng dụng; xử lý thêm `azp` và các quy tắc OIDC liên quan khi có nhiều audience. |
| **iat** | Thời điểm phát hành token. | Phân biệt với thời điểm người dùng thực sự xác thực. |
| **exp** | Hạn cuối chấp nhận ID token. | Từ chối token hết hạn, có thể bù lệch đồng hồ nhỏ theo chính sách. |
| **auth_time** | Thời điểm người dùng xác thực gần nhất theo OP. | Phục vụ chính sách xác thực lại/độ mới; không phải lúc access token vừa được làm mới. |
| **amr** | Tham chiếu các phương pháp xác thực được sử dụng nếu OP cung cấp. | Diễn giải theo hợp đồng của OP; không chỉ nhìn chuỗi mà mặc định đáp ứng MFA hoặc mức đảm bảo mong muốn. |
| **acr** | Lớp ngữ cảnh xác thực nếu OP cung cấp. | Chỉ tin mức đảm bảo đã định nghĩa và được OP cam kết; kiểm tra có đáp ứng yêu cầu nghiệp vụ không. |
| **nonce** | Giá trị gắn kết ID token với yêu cầu xác thực nếu dùng. | Phải khớp nonce client đã tạo/lưu trong phiên tương ứng. |

Để chấp nhận ID token, client phải áp dụng **quy tắc xác minh OIDC đúng flow**, bao gồm nguồn phát hành, đối tượng nhận, chữ ký/thuật toán và khóa được tin cậy, hiệu lực thời gian cùng các trường ràng buộc cần thiết. Khi các điều kiện không khớp phải từ chối, kể cả khi JWT có dạng hợp lệ.

Pseudocode minh họa:

~~~text
handleOidcCallback(callback, loginAttempt):
    require callback.state == loginAttempt.state

    tokens = exchangeAuthorizationCode(
        code = callback.code,
        codeVerifier = loginAttempt.codeVerifier,
        redirectUri = configuredRedirectUri
    )

    id = verifyIdToken(
        tokens.idToken,
        trustedIssuer = configuredIssuer,
        allowedAlgorithms = configuredAlgorithms,
        expectedAudience = configuredClientId,
        trustedKeys = configuredProviderKeys
    )
    require id.isWithinValidityWindow
    require id.nonce == loginAttempt.nonce if nonce was sent
    require additionalOidcClaimsAreValid(id)  // ví dụ azp khi áp dụng
    require requiredAuthenticationAssuranceSatisfied(id, loginAttempt.policy)
    require localAccountIsEligible(id.iss, id.sub)

    session = createApplicationSession(id.iss, id.sub)
    return session
~~~

Đây là thuật toán khái niệm, không phải thư viện xác thực hoàn chỉnh. Trong triển khai thực tế, nên dùng thư viện OIDC được duy trì tốt, có xác minh token và chống tấn công chuyển hướng/phản hồi theo chuẩn. Tránh cho phép token tự chọn thuật toán xác minh không nằm trong danh sách hệ thống tin cậy hoặc tự tải khóa từ URL do token chỉ định tùy ý.

### Vì sao không dùng email làm bằng chứng danh tính duy nhất?

Email có thể thay đổi, được cấp lại, hoặc chưa được xác minh trong hệ thống nguồn. Claim `email_verified`, nếu có, thể hiện kết luận của OP theo chính sách của OP tại thời điểm áp dụng; không bảo đảm người đang dùng token hôm nay vẫn kiểm soát hộp thư. Khi liên kết tài khoản giữa các nhà cung cấp, cần chính sách đối chiếu và xác minh bổ sung để tránh ghép nhầm người dùng.

## 8. Xác thực người dùng khác với xác minh access token tại API

Hãy xét ba lớp hành động:

1. **OpenID Provider xác thực người dùng** khi họ nhập mật khẩu, sử dụng passkey hoặc hoàn thành MFA.
2. **Client kiểm chứng kết quả xác thực** bằng ID token và thiết lập phiên ứng dụng theo chính sách.
3. **Resource Server xác minh quyền truy cập của yêu cầu** bằng access token và chính sách dữ liệu.

Access token có thể là **JWT** (API thường có thể xác minh chữ ký và claims cục bộ) hoặc **opaque token** (API thường tra cứu/introspection để lấy thông tin hiệu lực). Đây là **định dạng/cách xác minh token**, còn “access token”, “refresh token” và “ID token” là các **vai trò giao thức** khác nhau.

Ví dụ API quản lý đơn hàng:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Chuỗi `<access-token>` là ký hiệu minh họa, không phải giá trị token thật. Nếu là JWT, API cần kiểm tra ít nhất các điều kiện phù hợp với giao thức và chính sách: **issuer, thuật toán/chữ ký, audience = orders-api, thời hạn, loại token và scope**. Nếu là opaque token, API cần dùng endpoint/hệ thống kiểm tra được tin cậy, bao gồm trạng thái active và các ràng buộc tương đương. Sau đó API vẫn phải kiểm tra **quyền hiện hành đối với đơn hàng 123**.

Không nên kết luận “người dùng vừa xác thực” chỉ vì nhận được access token chưa hết hạn. Kẻ tấn công có thể gửi bản sao bearer token; ứng dụng cũng có thể vừa dùng refresh token để xin access token mới mà **không có xác thực tương tác mới**.

| Dữ kiện | Có thể kết luận gì? | Chưa thể kết luận gì? |
| --- | --- | --- |
| Người dùng nhập đúng mật khẩu | Người gửi biết mật khẩu tại thời điểm kiểm tra. | Người gửi chắc chắn là chủ tài khoản hoặc không bị phishing. |
| Passkey assertion hợp lệ | Authenticator kiểm soát khóa phù hợp và đáp ứng thử thách/điều kiện đã kiểm. | Danh tính pháp lý của người sử dụng đã được xác minh mới tại mọi thời điểm. |
| ID token hợp lệ cho client | OP đáng tin đã phát hành thông tin về sự kiện xác thực, theo claims được kiểm tra. | ID token được phép gọi mọi API hoặc phiên hiện nay chưa bị thu hồi. |
| Access token hợp lệ cho API | Token được API chấp nhận trong phạm vi và thời hạn xác định. | Người gửi token chính là người dùng ban đầu hoặc có quyền trên mọi tài nguyên. |
| Refresh token được chấp nhận | Client đủ điều kiện được cấp token mới theo chính sách tại thời điểm xử lý. | Người dùng vừa xác thực lại hoặc quyền truy cập là vĩnh viễn. |

## 9. Độ mới của xác thực và step-up authentication

Một ứng dụng thường cho phép người dùng xem danh sách đơn hàng sau khi đăng nhập, nhưng yêu cầu xác thực bổ sung trước khi:

- Đổi email khôi phục hoặc đặt lại phương thức MFA.
- Thêm khóa bảo mật/passkey mới.
- Xuất dữ liệu nhạy cảm, thực hiện thanh toán hoặc thay đổi quyền quản trị.
- Thực hiện thao tác có dấu hiệu bất thường về thiết bị, vị trí hoặc hành vi.

Đó là **step-up authentication**: nâng yêu cầu xác thực khi rủi ro tăng hoặc hành động cần mức bảo đảm cao hơn.

Trong OIDC, ứng dụng có thể sử dụng `max_age` để yêu cầu giới hạn tuổi của lần xác thực và kiểm tra `auth_time` trong ID token trả về theo quy tắc của giao thức. Khi yêu cầu lớp xác thực cụ thể, có thể sử dụng thông tin `acr_values` nếu OP hỗ trợ và **xác nhận kết quả bằng claim thích hợp**, thay vì giả định việc gửi yêu cầu đã khiến OP đáp ứng.

Ví dụ:

~~~text
Quy định nghiệp vụ: hành động "thêm passkey"
- Phiên ứng dụng phải hợp lệ.
- Tài khoản không bị khóa.
- Người dùng phải đáp ứng xác thực đủ mạnh.
- Lần xác thực đáp ứng yêu cầu phải còn mới theo ngưỡng của chính sách.
- Nếu chưa thỏa: chuyển đến OP để xác thực lại, kiểm tra kết quả OIDC.
- Chỉ sau đó mới cho phép thêm credential mới.
~~~

Cần phân biệt `iat` (lúc token được phát hành) với `auth_time` (lúc xác thực người dùng). Khi access token được làm mới bằng refresh token, `iat` mới hơn không nhất thiết có nghĩa `auth_time` mới hơn.

## 10. Vòng đời phiên và token sau xác thực

Việc đăng nhập thành công tạo ra một **trạng thái tin cậy có thời hạn**, thường gồm phiên tại OP, phiên tại ứng dụng, và một hoặc nhiều token dùng cho mục đích khác nhau.

~~~mermaid
stateDiagram-v2
    [*] --> ChuaXacThuc
    ChuaXacThuc --> DaXacThuc: Credential / passkey được chấp nhận
    DaXacThuc --> CoPhien: Thiết lập phiên và phát hành token
    CoPhien --> CoPhien: Access token còn hạn / refresh phù hợp
    CoPhien --> CanXacThucLai: Độ mới hoặc mức bảo đảm không đủ
    CanXacThucLai --> CoPhien: Xác thực lại thành công
    CoPhien --> HetHieuLuc: Hết hạn, thu hồi, khóa tài khoản
    CanXacThucLai --> HetHieuLuc: Không đáp ứng chính sách
    HetHieuLuc --> ChuaXacThuc: Đăng nhập mới nếu còn được phép
~~~

Một số nguyên tắc quan trọng:

- **Access token:** thời gian sống giới hạn, audience và scope cụ thể; có thể cần kiểm tra thu hồi hoặc quyền động khi chính sách yêu cầu hiệu lực thay đổi nhanh.
- **Refresh token:** chỉ dùng với Authorization Server; cần bảo vệ tốt, giới hạn vòng đời, cân nhắc rotation hoặc ràng buộc bên gửi theo loại client và chính sách.
- **ID token:** chỉ dùng ở client được phép nhận để xử lý kết quả OIDC; không thay access token trong lời gọi API.
- **Phiên ứng dụng:** có thể được đại diện bằng session ID trong cookie; phải có giới hạn thời gian, kiểm soát đăng xuất, cố định phiên (session fixation), ràng buộc bảo mật và chính sách thu hồi.
- **Khóa tài khoản hoặc rút quyền:** phải xác định rõ cơ chế và độ trễ mà OP, client và Resource Server nhận biết thay đổi; không dựa duy nhất vào thời hạn còn lại của JWT.

Đăng xuất khỏi giao diện chỉ xóa một số trạng thái phía client. Nếu token đã bị sao chép trước đó, cần cơ chế ở phía máy chủ để giảm hoặc chấm dứt khả năng sử dụng: thu hồi phiên/refresh token, introspection, danh sách từ chối hoặc token sống ngắn cùng các kiểm tra quyền bổ sung.

### Lưu trữ và truyền token

- Truyền credential và token qua HTTPS/TLS; không đưa token vào URL hay log, telemetry, thông báo lỗi.
- Với ứng dụng web, cân nhắc mô hình backend quản lý token và cookie phiên **Secure, HttpOnly, SameSite** theo yêu cầu. Cookie tự động gửi cần có cơ chế chống CSRF phù hợp; HttpOnly không tự chặn XSS thực hiện hành động nhân danh người dùng.
- Với client cài trên thiết bị, dùng nơi lưu credential an toàn do nền tảng cung cấp khi có thể.
- Hạn chế phạm vi, thời hạn và quyền của token; ràng buộc token với bên gửi (DPoP/mTLS) khi phù hợp để giảm giá trị của bản sao bị đánh cắp.
- Cân nhắc refresh token rotation và phát hiện tái sử dụng bất thường, đồng thời xử lý yêu cầu làm mới đồng thời hợp lệ theo thiết kế hệ thống.

## 11. Nguy cơ mạo danh, đánh cắp và phát lại

| Rủi ro | Tình huống | Biện pháp bảo vệ |
| --- | --- | --- |
| **Credential stuffing** | Kẻ tấn công thử mật khẩu đã rò rỉ từ dịch vụ khác. | Mật khẩu độc lập, hỗ trợ passkey/MFA, giới hạn thử sai theo tín hiệu rủi ro, giám sát hành vi. |
| **Phishing và proxy đăng nhập giả** | Người dùng nhập mật khẩu và OTP vào trang giả, kẻ tấn công chuyển tiếp. | Ưu tiên WebAuthn/FIDO2 chống phishing, bảo vệ đường dẫn đăng nhập, huấn luyện và giám sát bất thường. |
| **Đánh cắp phiên/token** | XSS, log hoặc thiết bị bị xâm nhập làm lộ bearer token. | Chống XSS, bảo vệ lưu trữ, không log token, hạn token, phát hiện và thu hồi; cân nhắc sender-constrained token. |
| **Replay WebAuthn hoặc giao thức** | Một assertion/token cũ được gửi lại. | Challenge dùng một lần/có hạn, xác minh origin/RP ID; kiểm tra nonce, state và PKCE đúng nơi áp dụng. |
| **Login CSRF hoặc nhầm phiên** | Kẻ tấn công khiến trình duyệt của nạn nhân đăng nhập vào tài khoản khác hoặc dùng phản hồi OIDC sai yêu cầu. | Ràng buộc state/nonce với phiên khởi tạo; redirect URI đã đăng ký chính xác; dùng thư viện OIDC đúng chuẩn. |
| **Liên kết nhầm tài khoản** | Ứng dụng gắn hai tài khoản khác issuer chỉ dựa trên email giống nhau. | Sử dụng `iss` + `sub` và quy trình liên kết tài khoản có xác minh phù hợp. |
| **Đặc quyền cũ còn lưu trong token** | Nhân viên đổi vai trò sau khi JWT được cấp. | Kiểm tra quyền tài nguyên hiện tại, cơ chế thu hồi/trạng thái phiên, định nghĩa độ trễ cho quyền động. |
| **Khôi phục tài khoản yếu** | Kẻ tấn công chiếm email khôi phục và thêm credential mới. | Bảo vệ quy trình recovery, thông báo thay đổi, giới hạn rủi ro và yêu cầu xác minh bổ sung cho hành động nhạy cảm. |

Một giá trị đặc biệt phải tránh nhầm lẫn: **chữ ký số xác minh tính toàn vẹn và nguồn khóa ký**, không chứng minh người gửi HTTP request đang nắm quyền kiểm soát hợp pháp tài khoản. Với bearer token, người nhặt được token hoàn chỉnh có thể thử gửi yêu cầu hợp lệ; bảo vệ khỏi replay cần cơ chế ràng buộc người gửi hoặc trạng thái/challenge phù hợp với giao thức và hành động.

## 12. Ví dụ tổng hợp: đăng nhập và truy cập đơn hàng

Giả sử một công ty vận hành ba thành phần:

- `login.example.test`: OpenID Provider xác thực nhân viên.
- `portal.example.test`: ứng dụng web quản lý đơn hàng.
- `orders.example.test`: API bảo vệ đơn hàng.

### Kịch bản A — Đăng nhập hợp lệ, được xem tài nguyên

1. Nhân viên A đăng nhập qua OP bằng passkey; máy chủ xác minh challenge và credential thành công.
2. Portal nhận authorization code qua redirect đã đăng ký, kiểm tra state, đổi code bằng PKCE và kiểm chứng ID token.
3. Portal dùng cặp `(iss, sub)` để định danh tài khoản nhân viên, kiểm tra tài khoản đủ điều kiện sử dụng và tạo phiên.
4. Portal gọi Orders API bằng **access token dành cho Orders API**.
5. API kiểm tra issuer, chữ ký/trạng thái token, audience, thời hạn và scope `orders:read`, sau đó xác minh A được quyền xem đơn hàng 123.
6. API trả dữ liệu nếu mọi điều kiện đều đạt.

### Kịch bản B — Đăng nhập hợp lệ nhưng quyền đã bị thu hồi

1. Nhân viên A xác thực thành công lúc 10:00, nhận access token hết hạn lúc 10:10.
2. Lúc 10:03, quản trị viên thu hồi quyền truy cập nhóm đơn hàng 123.
3. Lúc 10:04, A hoặc người có bản sao bearer token gọi API với token còn hạn.
4. API có thể xác minh **token vẫn hợp lệ về mật mã và thời gian**, nhưng phải **từ chối truy cập đơn hàng 123** nếu chính sách yêu cầu phản ánh việc thu hồi quyền tại thời điểm gọi.
5. Để đáp ứng yêu cầu này, API cần nguồn quyền hiện hành hoặc cách phát hiện thay đổi đủ nhanh; chỉ đọc scope/role cũ từ JWT không đáp ứng yêu cầu thu hồi tức thời.

### Kịch bản C — Người dùng cần xác thực lại

1. Portal có phiên hợp lệ và access token còn hạn nhưng người dùng muốn thêm passkey mới.
2. Chính sách yêu cầu một lần xác thực mạnh và đủ mới.
3. Portal yêu cầu OP thực hiện xác thực lại, sau đó kiểm tra kết quả cùng `auth_time` và mức bảo đảm cần thiết.
4. Chỉ khi tài khoản, phiên, quyền thao tác và độ mới đều phù hợp, portal mới cho phép thêm credential mới.

Ba kịch bản cho thấy **xác minh danh tính**, **duy trì phiên** và **quyết định truy cập** nối tiếp nhau nhưng không thể thay thế cho nhau.

## 13. Checklist thiết kế và kiểm tra

Khi triển khai chức năng xác minh người dùng cho một hệ thống có token, hãy xác định:

1. **Nguồn danh tính:** Nhà cung cấp danh tính nào được tin? Dùng `iss` và `sub` như thế nào để tránh mạo danh/liên kết nhầm?
2. **Phương pháp xác thực:** Mật khẩu, OTP, passkey hay cơ chế khác? Có chống thử sai, phishing, replay và recovery không?
3. **Mức bảo đảm:** Những hành động nào cần MFA hoặc xác thực lại? Kết quả `auth_time`, `acr`, `amr` có được kiểm tra đúng quy ước OP không?
4. **OIDC:** Có dùng luồng phù hợp, PKCE, state, nonce khi áp dụng, redirect URI cố định và thư viện xác minh ID token đáng tin cậy không?
5. **Phân loại token:** Client nhận ID token để xử lý kết quả xác thực; API chỉ chấp nhận access token đúng loại, issuer, audience và scope?
6. **Vòng đời:** Access token, refresh token và phiên được giới hạn và thu hồi thế nào? Việc khóa tài khoản/rút quyền có độ trễ tối đa bao lâu?
7. **Lưu trữ:** Credential và token có bị đưa vào URL, log hoặc nơi lưu dễ đọc qua XSS không? Có biện pháp CSRF phù hợp với cookie?
8. **Kiểm thử kịch bản xấu:** Có thử token hết hạn, token sai audience, nonce/state sai, code bị replay, tài khoản bị khóa, quyền đổi giữa phiên và token bị sao chép không?

### Tự kiểm tra

**Câu 1.** Người dùng nhập đúng mật khẩu; có thể kết luận chắc chắn đó là chủ tài khoản không?

Không. Hệ thống đã kiểm chứng người gửi **biết mật khẩu**, nhưng mật khẩu có thể bị đánh cắp. Cần đánh giá mức bảo đảm của các yếu tố và bối cảnh xác thực.

**Câu 2.** Portal nhận được một ID token ký đúng bởi OP, nhưng `aud` là client ứng dụng khác. Có nên đăng nhập người dùng bằng token đó không?

Không. ID token phải được phát hành cho chính client nhận theo quy tắc OIDC. Chữ ký đúng không thay thế kiểm tra audience.

**Câu 3.** Người dùng xác thực 60 phút trước; ứng dụng vừa xin access token mới bằng refresh token. Có thể coi người dùng vừa xác thực trong phút cuối không?

Không. Access token mới được cấp không nhất thiết đi kèm một lần xác thực người dùng mới. Với chính sách yêu cầu xác thực gần đây, cần xem bằng chứng về `auth_time` và thực hiện step-up khi cần.

**Câu 4.** API nhận access token có scope `orders:read`, nhưng người dùng đã mất quyền đọc đơn hàng 123. Có cho phép không?

Không, nếu chính sách hiện hành yêu cầu quyền trên chính đơn hàng đó. Scope là điều kiện cần theo ủy quyền của token; API vẫn phải kiểm tra quyền trên tài nguyên cụ thể.

## Kết luận

Xác minh danh tính người dùng là quá trình kiểm tra **bằng chứng người gửi kiểm soát credential gắn với tài khoản**, theo phương thức, thời điểm và mức bảo đảm cụ thể. OAuth 2.0/OIDC giúp truyền và sử dụng kết quả đó giữa những thành phần có ranh giới tin cậy rõ ràng: OP xác thực, client kiểm tra ID token, Resource Server kiểm tra access token và quyền truy cập.

Kết quả xác thực không trở thành giấy phép vĩnh viễn. Mỗi hệ thống cần thiết kế thời hạn phiên/token, kiểm tra issuer/audience/claims, xác thực lại cho hành động nhạy cảm, thu hồi khi trạng thái thay đổi và bảo vệ chống token bị đánh cắp hoặc phát lại. Bằng chứng hợp lệ tại một thời điểm chỉ có ý nghĩa trong **đúng phạm vi và ngữ cảnh** mà hệ thống đã xác minh.

### Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Authentication, ID Token và các quy tắc kiểm tra](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [Web Authentication: WebAuthn Level 3 — W3C](https://www.w3.org/TR/webauthn-3/)
- [NIST SP 800-63B — Authentication and Lifecycle Management](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
