# ACR và AMR

Một người dùng đã đăng nhập ứng dụng tài chính bằng mật khẩu từ sáng. Buổi chiều, họ chọn **Phê duyệt chuyển khoản lớn**. Ứng dụng biết người dùng đã đăng nhập, nhưng liệu phiên xác thực hiện tại có **đủ mức bảo đảm** cho giao dịch? Người dùng đã dùng phương thức nào, và lần xác thực đó xảy ra **khi nào**?

Trong **OpenID Connect (OIDC)**, ba thông tin thường phải phân tích cùng nhau:

- **`acr` — Authentication Context Class Reference:** lớp/ngữ cảnh xác thực đã được đáp ứng, theo ngữ nghĩa **OpenID Provider (OP) và Relying Party (RP) thỏa thuận**.
- **`amr` — Authentication Methods References:** các phương thức xác thực đã được sử dụng, ví dụ mật khẩu (`pwd`), mã OTP (`otp`) hoặc bằng chứng liên quan khóa phần cứng (`hwk`).
- **`auth_time`:** thời điểm End User authentication diễn ra, rất quan trọng khi RP cần xác thực lại gần đây.

**ACR trả lời “đạt ngữ cảnh bảo đảm nào?”, AMR trả lời “dùng phương thức gì?”, `auth_time` trả lời “xác thực lúc nào?”**. Không được tính ACR bằng cách đếm AMR, dùng `iat` của ID token thay `auth_time` hoặc coi ID token được ký hợp lệ là chứng cứ đủ **quyền phê duyệt nghiệp vụ**.

Bài **“ACR và AMR”** thuộc chương **OpenID Connect** của module **Security Token Security Fundamentals**. Mục tiêu là nắm mô hình tin cậy OIDC/OAuth 2.0, ID token, yêu cầu step-up, chống token bị đánh cắp và replay, kiểm issuer/audience, scope và phân quyền tại Resource Server. Bài có ví dụ request/response, sơ đồ, mã Java minh họa, tình huống và kiểm thử âm tính.

## 1. Vì sao cần ACR và AMR?

“Đăng nhập thành công” không tạo ra một mức bảo đảm đủ cho mọi hành động. Ví dụ:

| Hành động | Chính sách RP minh họa | Rủi ro cần kiểm |
|---|---|---|
| Xem trang công khai | Không cần step-up | Không có thông tin riêng |
| Xem hóa đơn của chính mình | Phiên hợp lệ + `invoice:read` và ownership | Truy cập sai tenant/chủ sở hữu |
| Đổi email khôi phục | Phiên đủ mới, assurance phù hợp | Chiếm tài khoản qua thay đổi recovery |
| Phê duyệt chuyển khoản lớn | ACR được tin, `auth_time` đủ mới, quyền giao dịch và chống gian lận | Tác động tài chính |

Mức bảo đảm và thời gian trong bảng **là ví dụ**, không phải mức OIDC áp đặt. Ứng dụng cần:

1. Xác minh danh tính từ **OP tin cậy**.
2. Kiểm **assurance** cho hành động nhạy cảm.
3. Kiểm **freshness** của authentication event.
4. Kiểm **authorization** đối với giao dịch/tenant/tài nguyên.
5. Chống **trộn phiên, replay, đổi chủ thể** và sử dụng trạng thái lỗi cũ.

### Phân biệt các vai trò và loại token

| Thành phần | Vai trò |
|---|---|
| **OpenID Provider / Authorization Server** | Xác thực người dùng, định nghĩa ACR/AMR, phát ID/access token |
| **Relying Party (OIDC Client)** | Xác minh ID token, lập phiên và đánh giá assurance |
| **Resource Server** | Nhận **access token** dành cho API, kiểm audience/scope/quyền đối tượng |
| **End User** | Xác thực và hoàn tất tương tác bổ sung nếu được yêu cầu |

**ID token** mô tả authentication event và dành cho RP; **access token** được dùng ở Resource Server. API không được chấp nhận ID token có `aud` hướng tới RP thay cho access token dành riêng cho API.

## 2. `acr`: Authentication Context Class Reference

Theo **OpenID Connect Core**, `acr` là một **string** định danh Authentication Context Class mà quá trình xác thực đã đáp ứng. Ví dụ OP và RP **thỏa thuận riêng**:

~~~text
urn:example:assurance:basic
urn:example:assurance:strong-transaction
~~~

Một ID token đã được ký có thể có payload:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "finance-web",
  "iat": 1800000000,
  "exp": 1800000900,
  "auth_time": 1799999970,
  "acr": "urn:example:assurance:strong-transaction"
}
~~~

Đây chỉ là **payload minh họa**. Các giá trị `urn:example:...` không phải mức chuẩn hóa toàn cầu: chúng có ý nghĩa khi **hợp đồng giữa issuer và RP** nêu chính xác những điều kiện mà OP phải kiểm để phát claim đó.

### ACR không phải điểm số tùy ý

Ngữ nghĩa ACR của một OP có thể xét đến độ tin cậy của phương thức, các yếu tố, bảo vệ chống phishing, mức độ xác minh danh tính, độ mới hoặc những quy tắc khác. **Không thể nhìn tên ACR rồi khẳng định nó đạt NIST AAL2/AAL3, eIDAS hoặc một chuẩn assurance pháp lý**, trừ khi profile/hợp đồng thực sự định nghĩa tương đương đó.

**Cần document** issuer nào được tin, ACR vocabulary nào được chấp nhận, ý nghĩa từng giá trị, cơ chế kiểm toán/đổi policy và thời điểm cần reauthentication.

~~~text
UNSAFE:
  if acr >= "2": allowTransfer()
  if acr.contains("high"): allowTransfer()
  if issuer1.acr == issuer2.acr: assumeSameMeaning()

SAFER:
  trustedAcrs = configuredExactValuesForThisIssuerAndAction
  require verified acr is member of trustedAcrs
~~~

RP có thể dùng một ánh xạ mức bảo đảm **do mình cấu hình và kiểm soát**, nhưng không so sánh các chuỗi ACR theo thứ tự từ điển hoặc tự xếp hạng giá trị của hai issuer khác nhau.

### ACR có bắt buộc xuất hiện không?

Trong OIDC Core, `acr` là một **claim tùy chọn** trong ID token. Nó có thể vắng nếu OP không trả theo profile. **Thiếu `acr` không được tự suy ra assurance cao**: với hành động yêu cầu một ACR cụ thể, RP phải **không cho thực hiện** cho tới khi có bằng chứng hợp lệ.

## 3. `amr`: Authentication Methods References

`amr` là **mảng JSON các string**, mô tả phương thức xác thực thực sự đã được dùng. **RFC 8176** có registry cho một số AMR values; OP/RP còn phải thống nhất cách biểu diễn phương thức cụ thể.

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "finance-web",
  "iat": 1800000000,
  "exp": 1800000900,
  "auth_time": 1799999970,
  "amr": ["pwd", "otp"]
}
~~~

`pwd` mô tả password-based method; `otp` mô tả one-time password. **Mảng này không tự chứng minh hai yếu tố là độc lập, OTP chống phishing hay OP đã đáp ứng một ACR cụ thể**.

### Một số giá trị AMR thường gặp

| AMR | Diễn giải thường gặp theo registry/profile | Không được tự suy |
|---|---|---|
| `pwd` | Password-based authentication | Password đủ mạnh hoặc không bị lộ |
| `otp` | One-time password | OTP độc lập hoàn toàn với password hoặc chống phishing |
| `sms` | Xác thực có sử dụng SMS | An toàn trước SIM swap, đạt assurance cao |
| `mfa` | Nhiều yếu tố theo cách OP xác định | Những yếu tố cụ thể hoặc ACR của RP đã được đáp ứng |
| `hwk` | Dùng hardware-secured key theo profile | Attestation, user verification hoặc mọi chính sách phần cứng đã đạt |
| `swk` | Dùng software-secured key theo profile | Khóa không thể trích xuất |
| `fpt` | Fingerprint biometric | Tương đương một yếu tố từ xa độc lập ở mọi hệ thống |
| `pin` | PIN-based method | Chắc chắn có yếu tố phần cứng đi kèm |
| `user` | User presence test | Chắc chắn có user verification |
| `wia` | Windows Integrated Authentication | Cấu hình mạng/thiết bị đáp ứng chính sách RP |

**Không có một AMR string “passkey” được mọi OP diễn giải giống nhau.** Với WebAuthn/FIDO2, cần hợp đồng về AMR mapping, user presence, user verification, origin binding, khóa/thiết bị và ACR thật sự được OP phát.

### AMR không phải phép đếm yếu tố

~~~text
amr = ["pwd", "otp"]
  -> Có các chỉ báo password và OTP.
  -> Chưa tự động chứng minh chuẩn chống phishing hoặc ACR X.

amr = ["mfa"]
  -> OP mô tả MFA theo vocabulary của mình.
  -> Chưa tự chứng minh đúng yêu cầu assurance của RP.

amr = ["hwk", "user"]
  -> Có các chỉ báo khóa phần cứng và user presence.
  -> Không tự chứng minh đã có user verification nếu profile không nói vậy.
~~~

`amr` là **claim tùy chọn** và các giá trị **case-sensitive**. Kiểm giá trị theo registry/profile thay vì dùng substring; không dựa thứ tự phần tử trừ khi OP đã định nghĩa ý nghĩa. Thiếu AMR phải được xử lý theo policy, không tự đoán user vừa dùng password, OTP hoặc WebAuthn.

## 4. `auth_time`, `iat` và tuổi của xác thực

Nhiều lỗi step-up xảy ra vì RP nghĩ “ID token vừa được phát” đồng nghĩa “người dùng vừa xác thực lại”. Hai việc đó khác nhau.

| Claim | Ý nghĩa | Không thể thay cho |
|---|---|---|
| `auth_time` | Thời điểm End User authentication diễn ra theo OIDC, Unix time | `iat` của token |
| `iat` | Thời điểm ID token được phát hành | Thời điểm user nhập lại credential |
| `exp` | ID token hết hạn theo JWT/OIDC | Thời hạn session hoặc thời điểm step-up |
| `acr` | Authentication Context Class đã đạt | Thời điểm event |
| `amr` | Các phương thức đã sử dụng | Độ mới hoặc mức quyền |

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "finance-web",
  "iat": 1800003600,
  "exp": 1800004500,
  "auth_time": 1799996400,
  "acr": "urn:example:assurance:basic",
  "amr": ["pwd"]
}
~~~

ID token trong ví dụ được phát sau authentication event khá lâu; OP có thể tái sử dụng phiên SSO. **Không lấy `iat` để kết luận authentication đủ mới**, nhất là với silent sign-in, token renewal hay SSO cookies.

### Policy freshness minh họa

~~~text
requiredAcr = "urn:example:assurance:strong-transaction"
maxAuthenticationAge = 300 seconds (chính sách nội bộ ví dụ)

ALLOW only when:
  verified OP == trusted issuer
  verified ID token aud includes finance-web
  ID token is valid, not expired
  sub matches expected active subject
  acr is exactly in allowed ACR set
  auth_time exists, is plausible, and not too far in future
  now - auth_time <= maxAuthenticationAge
  transaction-specific authorization also succeeds
~~~

**300 giây chỉ là ví dụ đào tạo, không phải mức OIDC bắt buộc.** Chính sách thực cần xác định SLA, clock skew và UX, đồng thời không để skew cho phép kéo dài mức assurance quá thời hạn.

### `max_age` khác `prompt=login`

Trong OIDC authentication request:

- `max_age` yêu cầu OP kiểm **tuổi của authentication event** theo số giây. Nếu quá lâu, cần tái xác thực trước khi hoàn tất theo ngữ nghĩa chuẩn. **Khi `max_age` xuất hiện, ID token phải chứa `auth_time`**.
- `max_age=0` thường được dùng để yêu cầu xác thực lại.
- `prompt=login` yêu cầu OP nhắc người dùng đăng nhập lại, nhưng **không tự khẳng định** đã đạt ACR mạnh.
- `acr_values` yêu cầu/đề xuất context cần thiết, **không phải kết quả đã được xác minh**.

**RP vẫn phải kiểm kết quả trong ID token đã được xác minh.** Không chỉ dựa vào việc mình đã gửi `max_age=0` hay `prompt=login` để cho phép thanh toán.

## 5. Yêu cầu ACR từ OpenID Provider

RP có thể truyền yêu cầu về context xác thực khi bắt đầu OIDC Authorization Code Flow.

### 5.1. `acr_values` trong authorization request

~~~http
GET /authorize?response_type=code&client_id=finance-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Foidc%2Fcallback&scope=openid&state=<random-state>&nonce=<random-nonce>&code_challenge=<challenge>&code_challenge_method=S256&acr_values=urn%3Aexample%3Aassurance%3Astrong-transaction%20urn%3Aexample%3Aassurance%3Abasic HTTP/1.1
Host: login.example.test
~~~

`acr_values` là **chuỗi các giá trị ACR cách nhau bằng khoảng trắng, theo thứ tự ưu tiên**. OP xử lý theo chính sách và profile; tham số này **không xác nhận OP đã thực sự đáp ứng giá trị đầu tiên**. Nếu ứng dụng **chỉ** chấp nhận strong transaction assurance, không được fallback về basic chỉ vì OP đã trả ID token.

### 5.2. Yêu cầu essential ACR qua `claims`

OIDC cho phép mô tả yêu cầu ID token claims qua tham số `claims` (JSON phải được URL-encode khi đưa vào HTTP request):

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:assurance:strong-transaction"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

`essential: true` thể hiện RP coi claim này quan trọng với giao dịch. Mức độ OP hỗ trợ `claims`, cách thực thi `acr` và việc không thể đáp ứng phải theo OIDC Core, profile và hợp đồng OP. **Không giả định OP chắc chắn cấp đúng ACR chỉ vì RP đã gửi yêu cầu**. RP phải tự kiểm claim trả về, và **fail closed** cho hành động nhạy cảm khi ACR thiếu/sai.

### 5.3. RP có thể bắt OP dùng AMR cụ thể không?

`amr` là claim **mô tả phương thức thực tế**, không phải một API phổ quát để mọi RP đặt tùy ý trình tự xác thực. Một số OP có cơ chế riêng yêu cầu method hoặc policy nhưng **không tự sáng tạo tham số `amr_values` rồi giả định OP hiểu**.

Nếu chính sách đòi **phishing-resistant authentication**, hãy dùng một **ACR được OP/RP thỏa thuận với bảo đảm cụ thể**, sau đó kiểm kết quả. Chỉ yêu cầu/đọc `amr=["mfa"]` hoặc `["otp"]` là không đủ để chứng minh chống phishing.

### 5.4. `prompt=none` trong trường hợp cần step-up

`prompt=none` yêu cầu OP không hiển thị UI tương tác. Nếu context/freshness chưa đạt, OP có thể trả lỗi như `login_required` hoặc `interaction_required` theo ngữ cảnh. RP cần chuyển sang **interactive authorization flow** nếu người dùng đồng ý, không hạ yêu cầu assurance chỉ để silent login thành công.

## 6. Step-up authentication: từ phiên thường tới giao dịch nhạy cảm

**Step-up** là yêu cầu tăng mức bảo đảm hoặc xác thực lại khi user thực hiện thao tác có rủi ro cao hơn thông thường.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as Finance Web (Relying Party)
    participant OP as OpenID Provider
    participant API as Payment API
    U->>RP: Chọn phê duyệt chuyển khoản
    RP->>RP: Đánh giá ACR/auth_time của phiên và chính sách
    alt Chưa đáp ứng ACR hoặc freshness
        RP-->>U: Bắt đầu step-up
        RP->>OP: /authorize với state/nonce/PKCE, acr_values, max_age
        OP->>OP: Kiểm session và yêu cầu xác thực tương ứng
        OP->>U: Hiển thị bước xác thực nếu cần
        U-->>OP: Hoàn tất hoặc từ chối
        OP-->>RP: Callback authorization code/state
        RP->>OP: POST /token: code + verifier + client authentication
        OP-->>RP: ID token với acr/amr/auth_time thực tế
        RP->>RP: Kiểm chữ ký, iss/aud, sub, nonce, ACR, freshness
    end
    RP->>API: Gọi API với access token dành cho Payment API
    API->>API: Kiểm token, scope, quyền tài khoản/giao dịch
    API-->>RP: Cho phép hoặc từ chối theo policy
~~~

Đây là sơ đồ giản lược luồng OIDC Authorization Code + PKCE. **Step-up thành công chưa phải quyền chuyển tiền**: API vẫn phải kiểm chủ sở hữu tài khoản, hạn mức, beneficiary, trạng thái giao dịch và chống gian lận; tùy threat model có thể cần **transaction-bound verification** gắn bước xác nhận với số tiền/đích cụ thể.

### Các binding cần bảo vệ

1. **Transaction RP:** Lưu state, nonce, PKCE verifier, expected issuer và yêu cầu ACR/freshness của hành động đang chờ.
2. **Issuer/client:** Chỉ chấp nhận callback và ID token từ OP tin cậy, đúng client registration và redirect URI.
3. **Subject continuity:** Sau step-up, `sub` phải là **subject dự kiến** của phiên hiện tại; user B không được nâng assurance cho giao dịch của user A.
4. **Claim validation:** Xác minh ID token bằng SDK tin cậy; `acr` phải có trong danh sách hợp lệ; `auth_time` đủ mới và `amr` (nếu cần) có ngữ nghĩa đúng.
5. **Action continuity:** Ràng buộc giao dịch đang chờ và kiểm lại quyền trước khi thực hiện; không cho frontend đổi số tiền hoặc người thụ hưởng sau step-up mà không kiểm.
6. **Lỗi/denial:** Nếu OP trả context thấp hơn, user từ chối hoặc transaction hết hạn, **không thực hiện hành động nhạy cảm**. Có thể giữ phiên xem thông tin theo policy ít nhạy cảm hơn.

### State machine minh họa

~~~mermaid
stateDiagram-v2
    [*] --> NORMAL_SESSION
    NORMAL_SESSION --> CHECK_ASSURANCE: Người dùng chọn hành động
    CHECK_ASSURANCE --> CHECK_AUTHORIZATION: ACR/freshness đạt
    CHECK_ASSURANCE --> STEP_UP_REQUIRED: Thiếu ACR hoặc auth_time
    STEP_UP_REQUIRED --> STEP_UP_PENDING: Bắt đầu OIDC flow
    STEP_UP_PENDING --> CHECK_AUTHORIZATION: Claims mới đã xác minh và đạt policy
    STEP_UP_PENDING --> DENY_ACTION: Denial, timeout hoặc context thấp
    CHECK_AUTHORIZATION --> ALLOW_ACTION: Quyền nghiệp vụ vẫn hợp lệ
    CHECK_AUTHORIZATION --> DENY_ACTION: Quyền hoặc giao dịch thay đổi
    ALLOW_ACTION --> [*]
    DENY_ACTION --> [*]
~~~

Đây là state machine **của ứng dụng**, không phải tập trạng thái OIDC bắt buộc. Nó ngăn lỗi phổ biến: sau khi user xác thực lại, ứng dụng quên kiểm điều kiện của **hành động cụ thể**.

## 7. ACR, AMR và yêu cầu chống phishing

Một AMR cụ thể **không tự chứng minh** phiên chống phishing; cùng nhãn có thể bị các OP triển khai theo profile khác nhau.

| Phương thức được mô tả | AMR minh họa | RP cần biết thêm |
|---|---|---|
| Mật khẩu + SMS OTP | `["pwd","sms"]` | SMS có thể bị SIM swap/phishing; không tự đạt ACR mạnh |
| Mật khẩu + TOTP | `["pwd","otp"]` | OTP có thể bị relay qua trang giả |
| WebAuthn/FIDO2 có user verification | Mapping tùy OP, có thể gồm chỉ báo khóa và xác minh user | Cần hợp đồng về origin binding, authenticator, UV/UP và policy OP |
| OP cho biết đã dùng MFA | `["mfa"]` | Chỉ là tuyên bố phương thức, chưa xác nhận ACR RP cần |
| Tái dùng phiên SSO | AMR có thể phản ánh sự kiện cũ hoặc vắng | Cần `auth_time`/freshness, không lấy `iat` |

Không kiểm bảo đảm MFA bằng cách đếm số phần tử mảng AMR. Một yếu tố có thể được thể hiện bởi nhiều AMR, và một phương thức mạnh có những đặc tính không thể đo bằng số nhãn.

### Policy cụ thể thay vì “AMR nhiều hơn một phần tử”

~~~text
POLICY EXAMPLE:

Read public report:
  authenticated session not required

Read own invoice:
  require authenticated session
  require scope invoice:read and ownership

Approve sensitive transfer:
  require verified ACR:
    urn:example:assurance:strong-transaction
  require auth_time within last 300 seconds
  require transfer authority, limits, beneficiary checks
  optionally require transaction-bound approval
~~~

Các giá trị và thời gian là **chính sách minh họa**, không phải ACR registry dùng chung. Để yêu cầu phishing resistance, OP phải thực sự thực thi tiêu chí đó và RP phải có hợp đồng/kiểm chứng về claim.

## 8. Kiểm ID token trước khi tin ACR/AMR

**Không Base64URL-decode ID token rồi tin payload**. Quyết định bảo mật phải dựa trên **ID token đã được xác minh** bởi OIDC client library phù hợp, gắn với đúng authorization transaction.

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "finance-web",
  "exp": 1800000900,
  "iat": 1800000000,
  "auth_time": 1799999970,
  "acr": "urn:example:assurance:strong-transaction",
  "amr": ["pwd", "otp"],
  "nonce": "n-transaction-123"
}
~~~

| Kiểm soát | Câu hỏi cần trả lời |
|---|---|
| **Chữ ký và thuật toán** | ID token được ký/kiểm theo alg, khóa và trust contract OP đã đăng ký? |
| **Issuer `iss`** | Có đúng issuer của transaction và OP discovery/JWKS tin cậy? |
| **Audience `aud` và `azp`** | ID token được phát cho client; khi có nhiều audience thì kiểm authorized party theo OIDC? |
| **`exp`/`iat`** | ID token còn hạn, các mốc hợp lý và clock skew được giới hạn? |
| **Subject `sub`** | Có đúng subject mà session/giao dịch đang chờ yêu cầu? |
| **`state`/`nonce`** | Callback được gắn với transaction; nonce được kiểm theo flow/profile? |
| **`acr`** | Có mặt khi policy cần và thuộc tập giá trị được tin **của issuer đó**? |
| **`amr`** | Nếu policy cần, có phải mảng string hợp lệ, đúng ý nghĩa OP đã thỏa thuận? |
| **`auth_time`** | Có mặt khi `max_age`/policy yêu cầu; đủ mới, không bất thường? |

Các claim trong request query, local storage hoặc header do frontend tự đặt **không thể vượt độ tin cậy của ID token đã xác minh**. Không nhận từ JavaScript một giá trị `acr=strong` rồi cho phép thanh toán.

### ID token và access token không thể thay thế nhau

ID token có `aud=finance-web` dành cho RP, **không phải bearer access token dành cho Payment API**. Resource Server cần access token có issuer/audience/scope, expiry và quyền nghiệp vụ hợp lệ. Nếu API cần assurance, có một số kiến trúc:

- **Access token** chứa claim assurance theo profile giữa AS và RS; RS kiểm chữ ký/introspection, claim, freshness và audience.
- **BFF** đã xác minh phiên OIDC truyền ngữ cảnh qua kênh server-to-server đáng tin, gắn với đúng request/subject; không chấp nhận header assurance do caller internet khai.
- Resource Server yêu cầu **step-up** qua error/challenge theo **RFC 9470**, nếu AS/client/RS triển khai profile đó.

**Không forward nguyên ID token cho API** để tiện lấy `acr`; dễ gây nhầm token purpose/audience và làm lộ authentication claims không cần thiết.

## 9. Java 17: đánh giá policy trên identity đã được xác minh

Đoạn code dưới đây minh họa bước **authorization decision tại RP**, chạy **sau** khi thư viện OIDC đã xác minh mật mã và semantics của ID token. Nó **không** tự parse JWT, fetch JWKS hoặc xác thực ID token.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Set;

record VerifiedOidcIdentity(
    String issuer,
    String subject,
    Set<String> audiences,
    Instant authenticationTime,
    String acr,
    List<String> amr
) {}

record AssurancePolicy(
    String expectedIssuer,
    String expectedAudience,
    Set<String> acceptableAcrs,
    Duration maximumAuthenticationAge,
    Duration allowedClockSkew
) {}

final class AssuranceEvaluator {

    static boolean permitsSensitiveOperation(
            VerifiedOidcIdentity id,
            AssurancePolicy policy,
            String expectedSubject,
            Clock clock) {

        Objects.requireNonNull(id);
        Objects.requireNonNull(policy);
        Instant now = clock.instant();

        if (!policy.expectedIssuer().equals(id.issuer())) {
            return false;
        }
        if (id.audiences() == null ||
            !id.audiences().contains(policy.expectedAudience())) {
            return false;
        }
        if (!expectedSubject.equals(id.subject())) {
            return false;
        }
        if (id.acr() == null ||
            !policy.acceptableAcrs().contains(id.acr())) {
            return false;
        }
        if (id.authenticationTime() == null) {
            return false;
        }

        Duration age = Duration.between(
            id.authenticationTime(), now);
        if (age.compareTo(policy.allowedClockSkew().negated()) < 0) {
            // Authentication time nằm quá xa trong tương lai.
            return false;
        }
        if (age.compareTo(policy.maximumAuthenticationAge()) > 0) {
            return false;
        }

        // AMR là thông tin bổ trợ. Chỉ kiểm nó khi RP/OP
        // đã có policy/contract cụ thể cho các giá trị AMR.
        // Quyền giao dịch/tenant/hạn mức được kiểm ở bước KHÁC.
        return true;
    }

    private AssuranceEvaluator() {}
}
~~~

**Ranh giới của ví dụ:**

- `VerifiedOidcIdentity` phải được tạo **chỉ bởi adapter tin cậy** lấy thông tin từ **ID token đã được OIDC SDK xác minh**. Bất kỳ input từ browser chưa kiểm hay dữ liệu giải mã JWT không có chữ ký đều **không đủ điều kiện** tạo object này.
- Code giả định policy có `expectedIssuer`, `expectedAudience`, `acceptableAcrs` không rỗng, thời lượng không âm và `expectedSubject` hợp lệ. **Production phải validate cấu hình policy** trước khi gọi hàm.
- Check audience chỉ minh họa **một phần** của ID token validation; `azp`, nonce, alg, signature, `exp`, `iat`, token substitution và các kiểm tra OIDC khác phải được OIDC library xử lý.
- Nếu `auth_time` hơi trong tương lai nhưng nằm trong skew, code cho phép theo cấu hình. Skew phải có **giới hạn nhỏ được review**.
- Hàm **không thay thế** API authorization. Sau khi trả true, giao dịch vẫn cần kiểm quyền, chủ thể, hạn mức, beneficiary, trạng thái và anti-fraud.

### Sử dụng policy

~~~java
AssurancePolicy transferPolicy = new AssurancePolicy(
    "https://login.example.test",
    "finance-web",
    Set.of("urn:example:assurance:strong-transaction"),
    Duration.ofMinutes(5),
    Duration.ofSeconds(30)
);

// verifiedIdentity phải đến từ OIDC SDK, không phải JSON tự khai.
boolean assuranceOk = AssuranceEvaluator.permitsSensitiveOperation(
    verifiedIdentity,
    transferPolicy,
    expectedSessionSubject,
    Clock.systemUTC()
);

if (!assuranceOk) {
    // Khởi tạo flow step-up hoặc từ chối hành động theo policy.
}
~~~

Các biến `verifiedIdentity` và `expectedSessionSubject` là dữ liệu ứng dụng đã có trước đó; code **không phải file Java độc lập biên dịch và chạy ngay**.

### Nếu muốn kiểm AMR trong policy

Không dùng:

~~~java
// SAI: Mảng có 2 phần tử không tự chứng minh MFA.
boolean mfa = verifiedIdentity.amr().size() >= 2;

// SAI: pwd+otp không tự đồng nghĩa ACR strong-transaction.
boolean strong = verifiedIdentity.amr().contains("otp");
~~~

Nếu hợp đồng OP-RP yêu cầu một tập AMR cụ thể, có thể thêm **check có điều kiện** nhưng vẫn **không bỏ kiểm ACR/freshness** và cần xem xét threat model của từng phương thức.

## 10. Khi có nhiều issuer, tenant hoặc Identity Provider

Một doanh nghiệp có thể cho đăng nhập qua hai OpenID Provider. Cả hai đều trả ACR tên `high`, nhưng chưa chắc **cùng mức bảo đảm**.

~~~text
OP A:
  issuer = https://idp-a.example.test
  acr    = high
  định nghĩa: password + TOTP theo policy A

OP B:
  issuer = https://idp-b.example.test
  acr    = high
  định nghĩa: hardware-backed phishing-resistant authentication theo policy B

UNSAFE:
  if acr == "high": grant sensitive access

SAFER:
  lookup policy by verified issuer + client/tenant + action
  check actual ACR value against trusted mapping for that issuer
~~~

Hai giá trị giống chữ **không có nghĩa cùng ngữ nghĩa**. Một RP đa tenant phải xác định:

- Tenant nào được dùng OP nào, theo **issuer đã đăng ký**.
- ACR nào OP đó thực sự bảo đảm, có hợp đồng/profile và quy trình cập nhật.
- Identity mapping giữa `sub` của OP và subject nội bộ; không trộn `sub` giống nhau từ hai issuer.
- Khi user đổi OP hoặc tenant giữa step-up, ứng dụng có cho phép chuyển chủ thể không; mặc định nên **không nâng assurance sang phiên khác**.
- Các policy scope/role/resource luôn do API thực thi sau khi identity được xác minh.

### OIDC Discovery metadata giúp gì?

Một số OP công bố OIDC discovery metadata như `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `claims_supported` và `acr_values_supported` khi có hỗ trợ. Tuy nhiên:

1. `acr_values_supported` (nếu có) cho biết OP **quảng bá những giá trị có thể hỗ trợ**, không chứng minh user hiện tại đạt một giá trị.
2. `claims_supported` (nếu có) không chứng minh mọi flow và client sẽ nhận mọi claim ở mọi tình huống.
3. Metadata phải được lấy từ **issuer được tin cậy**, không để input của end user quyết định hostname/JWKS/token endpoint.
4. RP vẫn phải kiểm **ID token thực nhận**, không chỉ dựa trên danh sách trong metadata.

**Không dùng discovery metadata để bỏ qua kiểm chữ ký, issuer, audience hoặc PKCE.**

### Chính sách ACR thay đổi theo thời gian

Nếu OP sửa nghĩa của `urn:example:assurance:strong-transaction` nhưng RP không biết, policy có thể vô tình yếu đi. Cần versioning/đàm phán contract, đánh giá lại trust, kiểm audit và xử lý phiên cũ theo thời hạn thích hợp. Không coi ACR string là cam kết bất biến nếu nhà cung cấp có quyền đổi cách thực thi.

## 11. API cần step-up: OAuth challenge theo RFC 9470

Đôi khi **Resource Server** phát hiện access token hiện tại chỉ tương ứng một authentication event quá cũ hoặc mức assurance không đủ. **RFC 9470** mở rộng OAuth 2.0 để Resource Server có thể trả challenge yêu cầu **step-up authentication**.

Ví dụ minh họa HTTP:

~~~http
POST /api/transfers/TX-42/approve HTTP/1.1
Host: payments.example.test
Authorization: Bearer <redacted-access-token>
Content-Type: application/json

{"decision":"approve"}
~~~

Nếu token hợp lệ cho resource nhưng ngữ cảnh xác thực không đáp ứng policy, Resource Server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication", acr_values="urn:example:assurance:strong-transaction", max_age="300"
Cache-Control: no-store
~~~

Đây là **minh họa challenge**: Resource Server đang yêu cầu mức ACR và tuổi authentication phù hợp để có thể tiếp tục. Client vẫn phải giới hạn nguồn challenge đáng tin và kiểm kết quả xác thực sau step-up.

### Sau challenge, client nên làm gì?

1. Xác minh response là từ **Resource Server đang gọi**, không từ một trang attacker hoặc proxy không tin cậy.
2. Kiểm yêu cầu challenge với chính sách RP và danh sách ACR mà OP hỗ trợ; **không tuân thủ vô hạn mọi chuỗi do server lạ gợi ý**.
3. Khởi tạo OIDC Authorization Code + PKCE và các tham số `state`, `nonce`, `acr_values`/`max_age` phù hợp.
4. Kiểm ID token mới đã xác minh, `acr`, `auth_time` và continuity của `sub`.
5. Nhận **access token đúng audience/resource** mà RS có thể dùng để xác định assurance theo profile.
6. Chỉ thử lại request khi **an toàn về idempotency và trạng thái giao dịch**. Với thao tác chuyển tiền, cần idempotency key hoặc kiểm request đã được xử lý chưa, không gửi lại tùy ý.

### Vì sao không chỉ thêm `acr` vào request header?

~~~http
X-Authentication-Level: high
~~~

Nếu header đó được browser/client bất kỳ tự đặt, nó **không phải bằng chứng**. RS phải kiểm assurance từ nguồn tin cậy, thường là claim trong access token đã xác minh/introspection hoặc session assertion server-to-server có ràng buộc chủ thể và nguồn phát.

### `401` vì assurance khác `403` vì thiếu quyền

| Tình huống | Hướng xử lý |
|---|---|
| Access token không hợp lệ/hết hạn | `401` theo OAuth Bearer challenge, có thể cần token mới |
| Token hợp lệ nhưng authentication context chưa đủ | `insufficient_user_authentication` theo RFC 9470 nếu triển khai; yêu cầu step-up |
| Token hợp lệ nhưng thiếu scope `transfer:approve` | Authorization/scope denial, ví dụ `403 insufficient_scope`; step-up không tự tạo scope |
| Token có scope nhưng user không được duyệt tài khoản này | `403`/`404` theo chính sách dữ liệu; xác thực mạnh hơn không tự tạo quyền |
| User từ chối hoặc OP không đáp ứng ACR | Không thực hiện hành động; không fallback về mức thấp |

**Challenge phải được thiết kế theo hệ thống:** Không phải mọi OAuth/OIDC server hỗ trợ RFC 9470 hoặc tự mang ACR vào access token. Khi không có profile này, RP/BFF và API cần một trust contract riêng hoặc kiểm ở lớp ứng dụng được bảo vệ.

## 12. Phiên, cache và refresh token: mức assurance có thể “cũ” đi

Một vấn đề thường gặp là ứng dụng cache `acr=strong` từ một lần step-up rồi **duy trì cờ “strong=true” vô hạn**. Đây là lỗi vòng đời trạng thái.

### Ví dụ timeline

~~~text
09:00  User xác thực bằng password; acr=basic, auth_time=09:00.
09:20  User thực hiện MFA/step-up; acr=strong, auth_time=09:20.
09:22  RP cho phép một thao tác nhạy cảm (đạt policy 5 phút).
10:15  Session SSO và refresh token vẫn có thể đang tồn tại.
10:15  RP nhận ID token mới có iat=10:15.

Không được tự kết luận:
  iat mới -> user vừa step-up lại tại 10:15.

Phải kiểm:
  auth_time thực sự là mấy giờ?
  OP phát acr tương ứng event nào?
  RP policy cho phép high-assurance session tồn tại bao lâu?
~~~

**Refresh token rotation không tự duy trì freshness của authentication event.** Rotation chống rủi ro refresh token bị sao chép/phát lại, nhưng không thay đổi việc user đã xác thực lúc nào. Nếu một OP phát ID token mới từ refresh token, RP vẫn phải đánh giá `auth_time`/ACR theo ngữ nghĩa OIDC/profile hiện hành.

### Cache assurance theo phiên như thế nào?

Một RP có thể lưu:

~~~text
SessionAssurance {
  issuer = verified OP
  subject = verified subject
  acr = verified ACR at authentication event
  amr = verified AMR if supplied
  authTime = verified authentication timestamp
  assuranceExpiresAt = local policy deadline
  transaction = optional step-up request binding
}
~~~

Đây là **mô hình ứng dụng**, không phải session schema OIDC bắt buộc. Phải:

- Gắn cache vào **đúng session, issuer và subject**.
- Không cho browser tự đặt `assuranceExpiresAt` hoặc sửa `acr`.
- Tính hạn assurance độc lập với `exp` của access token, thời hạn refresh token và cookie lifetime.
- Invalidate hoặc đánh giá lại khi user logout, chuyển tài khoản, session bị revoke, OP trust thay đổi hoặc policy step-up tăng.
- Không chia sẻ một assurance flag giữa tenant, trình duyệt, thiết bị hoặc client không cùng trust context.

### Step-up có cần cấp access token mới?

**Tùy mô hình AS/RS và profile.** Một RP xác thực lại có ID token ACR cao không có nghĩa access token cũ tự mang assurance mới. Nếu API dựa trên access token claim để thực thi step-up, client cần **access token mới đúng ngữ cảnh** (hoặc token exchange/claims hợp lệ theo thiết kế). Không dùng một JWT access token cũ rồi thêm local header “đã MFA” để vượt RS.

## 13. Những sai lầm dễ tạo lỗ hổng

| Sai lầm | Hậu quả | Biện pháp |
|---|---|---|
| Tin `acr` từ query/body do frontend gửi | Attacker tự khai context cao | Chỉ dùng claim từ OP/AS tin cậy đã xác minh |
| Đọc JWT payload mà không xác minh chữ ký | Token giả thay `acr/amr/sub` | OIDC SDK kiểm JWS/issuer/audience/time/nonce |
| So sánh `acr >= "2"` | Chuỗi không có thứ tự chuẩn | Per-issuer exact allowlist/policy mapping |
| Coi `["pwd","otp"]` mặc nhiên là phishing-resistant | Chấp nhận phương thức dễ bị relay | Hợp đồng ACR đúng assurance, review OTP/WebAuthn policy |
| Đếm số AMR để suy MFA | AMR không phải bộ đếm yếu tố | Kiểm ngữ nghĩa OP, ưu tiên ACR phù hợp |
| Dùng `iat` mới thay `auth_time` | User SSO cũ được coi như vừa xác thực lại | Kiểm `auth_time` và freshness |
| Gửi `acr_values` rồi tự cho phép ngay | OP có thể không đáp ứng yêu cầu | Kiểm `acr` trong ID token thực nhận |
| Thiếu ACR mà mặc định `strong` | Bỏ qua assurance policy | Fail closed, yêu cầu step-up nếu phù hợp |
| Dùng `prompt=login` như chứng nhận MFA | Re-login không nhất thiết tăng ACR | Kiểm ACR và AMR theo contract |
| Dùng ID token gửi Resource Server | Sai token purpose/audience | RS nhận access token phù hợp |
| Step-up đổi thành user khác | Nâng quyền phiên A bằng xác thực của B | Kiểm `iss`+`sub` continuity |
| Cờ `mfa=true` không có hạn phiên | Giữ assurance vĩnh viễn | Gắn `auth_time` và policy deadline |
| Chấp nhận ACR `high` từ mọi issuer | Hai OP định nghĩa khác nhau | Mapping theo verified issuer/client |
| Đổi amount/beneficiary sau step-up | Người dùng phê duyệt nhầm giao dịch | Transaction binding, kiểm lại quyền và dữ liệu |
| 401 step-up bị retry vòng lặp | Lặp login vô hạn hoặc spam OP | Giới hạn retry, kiểm kết quả, fail closed |
| Gửi lại POST thanh toán không có idempotency | Có thể xử lý giao dịch hai lần | Idempotency key và kiểm trạng thái |
| OP metadata không được tin | Token/JWKS injection hoặc mix-up | Pin trusted issuer, kiểm discovery và token |
| Log ID token/ACR session với PII | Rò claims người dùng, privacy issue | Redact token, tối thiểu hóa audit và retention |

## 14. Ma trận kiểm thử ACR, AMR và step-up

Giả định:

~~~text
Trusted OP issuer: https://login.example.test
RP client_id: finance-web
Payment API audience: payments-api
Strong ACR: urn:example:assurance:strong-transaction
Required authentication freshness: 300 giây (ví dụ)
Required API scope: transfer:approve
~~~

| Ca kiểm thử | Input/trạng thái | Kết quả kỳ vọng |
|---|---|---|
| **ACR đúng** | Verified ID token có strong ACR, auth_time mới | Assurance đạt, **vẫn phải** kiểm quyền giao dịch |
| **ACR basic** | RP cần strong nhưng token `acr=basic` | Step-up hoặc từ chối thao tác |
| **Thiếu ACR** | ID token không có claim `acr` | Không được mặc định strong |
| **ACR issuer khác** | OP B trả chuỗi ACR trùng tên OP A | Không chấp nhận nếu issuer không được policy tin |
| **ACR dạng số** | OP trả số thay string, trái profile | Token/claim không hợp lệ theo schema áp dụng |
| **AMR password-only** | `["pwd"]` | Không suy MFA/strong từ password |
| **AMR password+OTP** | `["pwd","otp"]` | Chỉ mô tả methods, không tự suy phishing-resistant |
| **AMR có một phần tử mfa** | `["mfa"]` | Chỉ chấp nhận theo hợp đồng OP, không tự thay ACR |
| **Thiếu AMR** | ID token không có AMR | Policy không dựa vào AMR vắng; nếu yêu cầu thì không cho qua |
| **AMR sai kiểu** | `"pwd,otp"` thay JSON array | Từ chối/không dùng làm bằng chứng methods |
| **AMR sai hoa thường** | `"PWD"` thay `"pwd"` | Không so khớp giá trị registry nếu không có mapping |
| **`auth_time` mới** | Giới hạn 300 s, event 2 phút trước | Đạt freshness nếu mọi kiểm khác đạt |
| **`auth_time` cũ** | Event 1 giờ trước, ID token vừa phát | Từ chối step-up dù `iat` mới |
| **Thiếu `auth_time`** | RP yêu cầu freshness/`max_age` | Không cho thực hiện action nhạy cảm |
| **`auth_time` tương lai** | Timestamp vượt allowed skew | Từ chối |
| **`max_age=0`** | RP xin xác thực lại, OP trả event cũ | RP kiểm `auth_time` và từ chối nếu không đạt |
| **`prompt=login`** | OP yêu cầu nhập lại password nhưng ACR vẫn basic | Không coi là strong |
| **`acr_values` được yêu cầu** | Xin strong, OP trả basic | RP từ chối action; không tin request input |
| **Essential claim** | `claims.id_token.acr.essential=true` nhưng claim thiếu | Không cho phép action; xử lý OP không đáp ứng |
| **Silent auth không đáp ứng** | `prompt=none` và OP trả `interaction_required` | Chuyển sang interactive step-up nếu user chấp nhận |
| **ID token giả** | Payload `acr=strong` nhưng chữ ký sai | OIDC SDK từ chối trước policy |
| **Issuer sai** | `iss` là OP lạ | Từ chối |
| **Audience sai** | ID token `aud=other-client` | RP từ chối |
| **Nonce/state sai** | Callback thuộc transaction khác | RP từ chối và không nâng session |
| **Subject thay đổi** | Step-up user B trong session user A | Từ chối nâng session A |
| **Multi-tenant** | ACR OP A được dùng cho tenant B với policy khác | Từ chối hoặc đánh giá lại theo tenant |
| **Access token sai audience** | Gửi token `aud=profile-api` tới Payment API | RS từ chối dù ACR trong ID token strong |
| **Thiếu scope** | Assurance đủ nhưng không có `transfer:approve` | RS từ chối, step-up không tự tạo scope |
| **Sai chủ tài khoản** | Scope và assurance hợp lệ nhưng tài khoản của user khác | RS từ chối theo object-level auth |
| **Step-up bị hủy** | User cancel/OP error | Không thực thi hành động, không tự downgrade |
| **Refresh token reuse** | Nhận token mới nhưng `auth_time` vẫn cũ | Không reset freshness bằng issuance mới |
| **Thay đổi giao dịch** | User đổi beneficiary sau step-up | Cần transaction binding/kiểm lại trước approve |
| **401 challenge vòng lặp** | RS cứ trả insufficient_user_authentication | Client dừng có giới hạn, không retry vô tận |
| **Đồng thời nhiều phiên** | Hai tab/user session step-up | Không lấy assurance tab/subject này gán cho tab/subject khác |
| **Log ID token/claims** | Kiểm APM, proxy, audit | Không log raw ID/access token hoặc PII không cần thiết |

## 15. Bài tập tình huống: chuyển khoản khi có SSO và TOTP

Giả sử Finance Web có phiên của An. OP phát ID token:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "finance-web",
  "iat": 1800003600,
  "exp": 1800004500,
  "auth_time": 1799996400,
  "acr": "urn:example:assurance:basic",
  "amr": ["pwd"]
}
~~~

Ứng dụng yêu cầu phê duyệt khoản chuyển `TX-42`: chỉ được khi có `urn:example:assurance:strong-transaction` và authentication event trong vòng 5 phút, cùng quyền `transfer:approve` và hạn mức phù hợp. Người dùng từng mở trang từ trước nhờ SSO.

**Câu 1. ID token vừa phát có đủ để chứng minh “vừa xác thực” không?**

**Không.** `iat` là token issuance time. Trong ví dụ `auth_time` cũ hơn nhiều; RP cần đánh giá freshness từ `auth_time`.

**Câu 2. RP gửi `acr_values=urn:example:assurance:strong-transaction` thì đã có quyền phê duyệt chưa?**

**Chưa.** Đây là request, không phải kết quả. RP phải kiểm ID token mới, đúng issuer/audience/subject, ACR và `auth_time`.

**Câu 3. Sau step-up, OP trả `amr=["pwd","otp"]` nhưng `acr` vẫn là basic. Có cho phép không?**

**Không** theo policy bài tập. RP đòi strong ACR, nên không được tự nâng cấp chỉ vì AMR có OTP. Cần OP đáp ứng giá trị ACR đã thỏa thuận.

**Câu 4. Nếu OP trả strong ACR và auth_time đủ mới nhưng `sub=user:binh` thay vì `user:an`?**

RP phải từ chối việc dùng step-up của Bình để phê duyệt giao dịch trong phiên của An. Cần xử lý chuyển tài khoản theo một luồng minh bạch nếu được phép.

**Câu 5. Nếu strong ACR đạt nhưng An không có quyền approve tài khoản nguồn?**

Payment API vẫn phải từ chối, vì **authentication assurance không phải authorization**.

**Câu 6. Một attacker gửi ID token tự tạo với `acr=strong` nhưng không có chữ ký OP hợp lệ. Có được dùng không?**

Không. OIDC client SDK phải từ chối token sai chữ ký/issuer/audience trước khi đánh giá ACR.

**Câu 7. Người dùng có access token `aud=payments-api` được phát trước step-up. Có thể tự gắn thêm `acr=strong` vào HTTP header để gọi API không?**

Không. API chỉ tin claim/assurance từ cơ chế được AS/RS thống nhất và xác thực; header do frontend tự đặt không đáng tin. Có thể cần access token mới chứa context phù hợp hoặc một proof server-to-server đáng tin.

**Câu 8. Người dùng tăng số tiền giao dịch từ một triệu lên một trăm triệu sau step-up. Có thể dùng nguyên approval cũ không?**

Không mặc nhiên. Phải kiểm lại transaction binding, hạn mức và quyền, và yêu cầu xác nhận lại nếu policy đòi hỏi. Step-up của phiên user không tự ký duyệt một **số tiền/beneficiary** cụ thể.

**Câu 9. Nếu RP chọn OP thứ hai và OP này cũng phát `acr=strong`, có được chấp nhận không?**

Chỉ khi **issuer được tin cậy** và RP có **mapping/hợp đồng assurance** cho giá trị của issuer đó. Trùng chuỗi không chứng minh tương đương.

## 16. Checklist production cho ACR, AMR và step-up

1. **Định nghĩa ACR bằng hợp đồng:** Những context nào được OP bảo đảm, thuộc issuer/profile nào, ai kiểm chứng và quản trị thay đổi?
2. **AMR đúng ngữ nghĩa:** Mảng AMR được hiểu theo RFC 8176/OP contract; không suy ACR bằng cách đếm elements?
3. **Freshness chính xác:** Dùng `auth_time` để kiểm tuổi xác thực; không dùng `iat` hoặc thời gian refresh token?
4. **OIDC request rõ:** `acr_values`, `max_age` và essential `claims` được gửi đúng profile khi cần, không coi request là bằng chứng đã đạt?
5. **Step-up fail closed:** OP không trả ACR yêu cầu, auth_time cũ hoặc user cancel → không thực hiện hành động nhạy cảm?
6. **ID token được verify:** Kiểm chữ ký/alg/key, `iss`, `aud`/`azp`, `exp`, `iat`, nonce/transaction theo OIDC SDK?
7. **Giữ đúng chủ thể:** `sub` sau step-up trùng phiên/giao dịch dự kiến, không nâng session của tài khoản khác?
8. **Issuer mapping:** Nhiều OP/tenant có allowlist ACR riêng; không tin cùng tên “high” từ issuer lạ?
9. **Không nhầm ID và access token:** Resource Server nhận access token đúng `aud`, type/profile và scope; không dùng ID token như bearer API?
10. **Resource Server thật sự biết assurance:** Nếu API cần context, AS phát claims trong access token/introspection hoặc có trust boundary server-to-server được kiểm?
11. **Phân quyền độc lập:** Role/scope, ownership/tenant, hạn mức, anti-fraud và transaction binding vẫn được kiểm sau authentication?
12. **Không coi AMR là chống phishing:** Với thao tác cần phishing resistance, policy có assurance contract rõ cho phương thức và OP?
13. **Cache có hạn:** ACR/`auth_time` gắn session, issuer, sub và deadline; không giữ `mfa=true` vĩnh viễn hoặc share chéo user/tenant?
14. **Refresh/revoke xử lý riêng:** Refresh token rotation không làm mới `auth_time`; logout/revoke token/grant được AS/RS thực thi theo policy?
15. **Challenge/retry an toàn:** Nếu dùng RFC 9470, client giới hạn step-up loop, không tự tin header lạ, retry POST có idempotency?
16. **Không để claim lộ ra ngoài:** Không log raw ID/access token, nonce hoặc dữ liệu cá nhân; bảo vệ TLS, session cookie, CSP/CSRF/XSS?
17. **Kiểm thử âm tính:** ACR thiếu/sai, AMR sai kiểu, auth_time cũ, subject mismatch, issuer mix-up, token sai audience, insufficient scope và giao dịch thay đổi?

**Ghi nhớ:** **`acr` là ngữ cảnh assurance mà OP xác nhận theo hợp đồng, `amr` là các phương thức xác thực đã sử dụng, `auth_time` là thời điểm xác thực**. Cả ba cần được diễn giải từ **ID token/OIDC session đã được xác minh**, không từ input do browser tự khai. Với hành động rủi ro cao, RP cần yêu cầu và kiểm step-up; API vẫn cần **access token đúng audience/scope và quyền nghiệp vụ riêng**. **Authentication mạnh không thay thế authorization, và ID token mới không tự chứng minh authentication mới**.

### Chuẩn và tài liệu tham khảo

- **OpenID Connect Core 1.0:** các ID token claims `acr`, `amr`, `auth_time`; `acr_values`, `claims` parameter, `max_age`, `prompt`, nonce và validation.
- **RFC 8176 — Authentication Method Reference Values:** registry của các AMR identifiers như `pwd`, `otp`, `mfa`, `hwk`, `user`.
- **OpenID Connect Discovery 1.0:** issuer và metadata như `acr_values_supported`, `claims_supported` nếu OP cung cấp.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization code, client authentication, token endpoint và grants.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ code exchange, không thay xác thực nhiều yếu tố.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer identification chống mix-up.
- **RFC 9470 — OAuth 2.0 Step Up Authentication Challenge Protocol:** `insufficient_user_authentication`, challenge với `acr_values`/`max_age` từ Resource Server.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth/OIDC, redirect, replay, token và refresh.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `iat`, `exp`, `sub` và JWT claim validation.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** token profile và validation tại Resource Server.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái và ngữ cảnh access token opaque/reference.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant, khác việc authentication assurance hết freshness.
- **OWASP Authentication Cheat Sheet và OAuth 2.0 Cheat Sheet:** reauthentication, step-up, session security, MFA, CSRF và token handling.
