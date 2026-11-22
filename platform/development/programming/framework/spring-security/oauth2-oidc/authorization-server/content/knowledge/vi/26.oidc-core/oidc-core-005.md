# Ý nghĩa của azp, acr, amr và các claims xác thực mở rộng

> **Chương:** OIDC Core và ID Token  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phiên bản minh họa:** OpenID Connect Core 1.0 incorporating Errata Set 2, RFC 8176, Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x (Servlet stack). Khi dùng Spring Security 7.x có Authorization Server tích hợp, đối chiếu lại API của phiên bản thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `azp` (*Authorized Party*), `acr` (*Authentication Context Class Reference*) và `amr` (*Authentication Methods References*).
2. Hiểu các claim này trong mối quan hệ với `iss`, `sub`, `aud`, `nonce`, `auth_time`, `iat` và `exp` của **OIDC ID Token**.
3. Giải thích quy tắc phát hành và xác minh `azp` mà không nhầm với audience hoặc client authorization.
4. Thiết kế từ điển `acr` do OpenID Provider (OP) và Relying Party (RP) thống nhất, không tự suy từ vai trò user.
5. Dùng các giá trị `amr` được đăng ký tại IANA/RFC 8176 theo đúng ngữ nghĩa.
6. Phân biệt `acr_values`, `claims.id_token.acr` với `essential:true`, `max_age` và `prompt`.
7. Thiết kế authentication evidence, step-up và MFA sao cho claims chỉ phản ánh các sự kiện xác thực **đã thành công**.
8. Tùy biến ID Token bằng `OAuth2TokenCustomizer<JwtEncodingContext>` trong Spring Authorization Server.
9. Xác minh ID Token và kiểm tra `acr`, `amr`, `auth_time` tại RP theo policy.
10. Kiểm thử các kịch bản nhiều audiences, client mismatch, stale authentication, refresh token và thiếu bằng chứng MFA.

**Thông điệp:** `azp` cho biết **authorized party** của ID Token; `acr` cho biết **lớp ngữ cảnh xác thực đã đạt**; `amr` liệt kê **những phương thức thực sự đã dùng**. Chúng không thay thế chữ ký JWT, issuer, audience, nonce, access token hoặc kiểm tra phân quyền của ứng dụng.

## 2. ID Token là phát biểu về Authentication

OIDC bổ sung một lớp danh tính lên OAuth 2.0. Trong Authorization Code + PKCE Flow:

1. RP gửi Authorization Request chứa `scope=openid`.
2. OP xác thực End-User và xử lý consent/authorization.
3. RP đổi authorization code ở Token Endpoint.
4. RP nhận ID Token chứa những phát biểu về user/authentication event, và access token dành cho Resource Server.
5. RP xác minh ID Token, xác lập session ứng dụng và đánh giá các yêu cầu assurance/freshness.
6. Khi gọi API, RP dùng **access token**, không phải ID Token.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant RP as OIDC Client / RP
    participant OP as OpenID Provider / Spring AS
    participant API as Resource Server

    U->>RP: Đăng nhập
    RP->>OP: Authorization Code + PKCE + nonce
    OP->>U: Login và MFA nếu policy yêu cầu
    U-->>OP: Bằng chứng xác thực
    OP->>OP: Xác minh, ghi auth_time/acr/amr
    OP-->>RP: Authorization code
    RP->>OP: Đổi code tại Token Endpoint
    OP-->>RP: ID Token và access token
    RP->>RP: Xác minh ID Token và authentication claims
    RP->>API: Authorization: Bearer access token
    API->>API: Kiểm tra scope và quyền nghiệp vụ
~~~

### 2.1. Những claim cơ bản

| Claim | Ý nghĩa | Tính bắt buộc |
| --- | --- | --- |
| `iss` | Issuer của OP | REQUIRED |
| `sub` | Subject identifier của End-User | REQUIRED |
| `aud` | Audience, bắt buộc chứa `client_id` của RP | REQUIRED |
| `exp` | Thời điểm ID Token hết hiệu lực | REQUIRED |
| `iat` | Thời điểm phát hành token | REQUIRED |
| `nonce` | Liên kết ID Token với Authentication Request | Bắt buộc khi request chứa nonce |
| `auth_time` | Thời điểm End-User thực sự xác thực | Bắt buộc khi `max_age` hoặc Essential auth_time được yêu cầu |
| `azp` | Authorized party | OPTIONAL |
| `acr` | Lớp ngữ cảnh xác thực đã đáp ứng | OPTIONAL |
| `amr` | Các phương thức xác thực đã được dùng | OPTIONAL |

Không có `acr`/`amr` **không mặc nhiên** làm ID Token sai OIDC. Nhưng nếu RP yêu cầu một lớp assurance cụ thể, absence có thể khiến RP phải từ chối thao tác/đăng nhập theo policy.

### 2.2. Một ID Token có thể chứa thông tin này

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-4831",
  "aud": ["booking-bff"],
  "exp": 1893457200,
  "iat": 1893456300,
  "auth_time": 1893456210,
  "azp": "booking-bff",
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp"]
}
~~~

Đây chỉ là ví dụ; Spring Authorization Server không tự động khẳng định `acr=mfa` hay `amr=["pwd","otp"]` nếu chưa có authentication policy/evidence tương ứng. `urn:example:acr:mfa` là giá trị nội bộ minh họa, không phải mức bảo đảm chuẩn toàn cầu.

### 2.3. Authentication khác Authorization

| Thành phần | Chứng minh điều gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| `sub` | Chủ thể được OP xác thực | Quyền với từng booking |
| `azp` | Authorized party theo OIDC/profile | Vai trò admin của user |
| `acr` | Class assurance đã đáp ứng | Scope để gọi API |
| `amr` | Methods đã thực hiện | Độ mới, thẩm quyền hay ownership |
| `scope` trong access token | Quyền được cấp trong OAuth2 grant | User vừa dùng MFA |
| Role/permissions đã xác minh | Quyền theo business policy | Token audience/signature đúng |

Ngay cả khi user đã MFA, Resource Server vẫn cần kiểm tra quyền trên từng object/tenant. Ngược lại, một access token có `booking.read` không tự chứng minh End-User mới đăng nhập trong 5 phút qua.

## 3. azp — Authorized Party

### 3.1. Định nghĩa

Theo OpenID Connect Core 1.0, `azp` là claim **OPTIONAL**. Nếu có, nó **MUST** chứa OAuth 2.0 `client_id` của authorized party mà ID Token được phát hành cho. Giá trị phân biệt chữ hoa/thường và được biểu diễn bằng JSON string.

OIDC Core lưu ý `azp` thường xuất hiện khi triển khai extension ngoài phạm vi Core; hệ thống không có extension tương ứng được khuyến khích tránh đưa `azp` vào một cách tùy tiện.

### 3.2. azp khác aud và sub

| Claim | Đại diện cho | Ví dụ |
| --- | --- | --- |
| `sub` | End-User | `user-4831` |
| `aud` | Danh sách audience của ID Token, phải gồm RP `client_id` | `["booking-bff"]` |
| `azp` | Authorized party khi được khai báo | `booking-bff` |

Với một RP duy nhất:

~~~json
{
  "aud": "booking-bff",
  "sub": "user-4831"
}
~~~

Đây có thể là ID Token hợp lệ dù **không có `azp`**.

Với extension nhiều audiences:

~~~json
{
  "aud": ["booking-bff", "partner-rp"],
  "azp": "booking-bff",
  "sub": "user-4831"
}
~~~

RP phải:

1. Xác minh `aud` có `client_id` của chính RP.
2. Từ chối token có audience bổ sung mà RP không tin cậy.
3. Nếu `azp` xuất hiện, áp dụng kiểm tra theo contract/profile của extension.
4. Với profile đơn giản, thường kiểm tra `azp == client_id`; không bỏ kiểm tra `aud`.

**Chú ý chuẩn:** Không phát biểu rằng “OIDC Core bắt buộc `azp` với mọi ID Token có nhiều `aud`”. Theo Core incorporating Errata Set 2, `azp` vẫn OPTIONAL; validation chi tiết khi extension tạo `azp` phụ thuộc extension, và RP nên xác minh authorized party đáng tin theo contract.

### 3.3. azp không cho biết quyền user

Nếu:

~~~json
{
  "aud": "booking-bff",
  "azp": "booking-bff",
  "sub": "user-4831"
}
~~~

thì **không thể suy** user được xem booking của tenant khác hoặc có quyền quản trị. `azp` cũng không phải `scope` hay `roles`.

### 3.4. Không lấy azp từ tham số HTTP thô

Ví dụ sai:

~~~java
// Sai: client_id từ request chưa được xác minh.
String azp = request.getParameter("client_id");
claims.claim("azp", azp);
~~~

Nếu extension yêu cầu `azp`, hãy lấy OAuth2 Client đã xác thực:

~~~java
String clientId = context.getRegisteredClient().getClientId();

// Chỉ khi extension/profile áp dụng và audience hợp lệ:
// context.getClaims().claim("azp", clientId);
~~~

Không thêm claim chỉ vì biến `clientId` tồn tại. Việc phát `azp` cần policy độc lập và kiểm tra consistency với `aud`.

## 4. acr — Authentication Context Class Reference

### 4.1. acr xác định một lớp xác thực

`acr` là **OPTIONAL**, kiểu JSON string. Nó xác định Authentication Context Class mà sự kiện xác thực thực tế đã đáp ứng.

Ví dụ một tổ chức tự định nghĩa:

| ACR ví dụ | Định nghĩa nội bộ |
| --- | --- |
| `urn:example:acr:password` | User đăng nhập theo chính sách mật khẩu |
| `urn:example:acr:mfa` | User hoàn tất nhiều yếu tố độc lập theo MFA policy |
| `urn:example:acr:phishing-resistant` | User dùng cơ chế đã được OP xác minh thỏa chính sách chống phishing |

Các chuỗi này **không mang mức bảo đảm chuẩn toàn cầu**. RP và OP phải thống nhất ý nghĩa, profile, factor requirements, session lifetime và policy version. Nếu dùng ACR theo một tiêu chuẩn bên ngoài, không gán lại nghĩa theo cảm tính.

### 4.2. acr không phải điểm số

Không so sánh ACR bằng chuỗi:

~~~java
// Không an toàn: không có thứ tự từ điển bảo đảm.
if (acr.compareTo("urn:example:acr:mfa") >= 0) {
    approveSensitiveAction();
}
~~~

Nếu OP có thứ bậc assurance, tạo mapping **tường minh và có version**. Ví dụ:

~~~java
Map<String, Integer> policyLevels = Map.of(
    "urn:example:acr:password", 1,
    "urn:example:acr:mfa", 2,
    "urn:example:acr:phishing-resistant", 3);
~~~

Đây chỉ là mapping minh họa khi một **policy engine được kiểm toán** đã xác lập quan hệ đó. Không tự suy mọi method hardware key hoặc OTP tương đương một ACR cấp cao.

### 4.3. Vì sao không tính acr từ số lượng amr?

`amr=["pwd","otp"]` có thể chỉ ra hai phương thức, nhưng còn phụ thuộc:

- OTP đã được OP xác minh thành công chưa?
- Hai bước có thuộc **hai yếu tố độc lập** không?
- Các authenticator có được đăng ký/xác minh trước không?
- Có phishing resistance, device binding hay origin binding không?
- Session đã đủ mới cho giao dịch nhạy cảm chưa?
- Có recovery/fallback path yếu hơn làm thay đổi assurance không?

OP phải đánh giá từng bằng chứng và policy trước khi đưa `acr` vào ID Token. Không ghi `acr=mfa` chỉ vì RP gửi `acr_values=mfa`.

### 4.4. acr bằng "0"

OIDC Core định nghĩa `acr="0"` là trường hợp xác thực End-User **không đáp ứng ISO/IEC 29115 Level 1**. Không tự hiểu `"0"` thành “người dùng ẩn danh” trong mọi hệ thống.

Khi chọn giá trị ACR, có thể dùng URI tuyệt đối hoặc tên đã được đăng ký theo profile, và không được dùng tên đăng ký với ý nghĩa trái chuẩn.

### 4.5. acr và scope khác nhau

`acr` mô tả assurance của **Authentication**; `scope` mô tả phạm vi **Authorization**.

User đăng nhập MFA vẫn có thể không có `booking.write`. User có `booking.read` có thể được xem dữ liệu thường, nhưng phải step-up trước khi thay đổi số tài khoản ngân hàng theo policy.

## 5. amr — Authentication Methods References

### 5.1. Định nghĩa

`amr` là **OPTIONAL**, JSON array of strings chứa các tên phương thức đã dùng để xác thực. Giá trị phân biệt chữ hoa/thường.

Ví dụ:

~~~json
{"amr":["pwd","otp"]}
~~~

Nó mô tả những phương thức đã xảy ra, **không tự khẳng định lớp assurance** hoặc phân quyền.

### 5.2. Các giá trị từ RFC 8176 / IANA

| Giá trị | Diễn giải |
| --- | --- |
| `pwd` | Password-based authentication |
| `otp` | One-Time Password |
| `mfa` | Multiple-Factor Authentication |
| `sms` | Xác nhận bằng SMS |
| `hwk` | Proof-of-Possession của khóa được bảo vệ phần cứng |
| `swk` | Proof-of-Possession của khóa được bảo vệ phần mềm |
| `fpt` | Sinh trắc vân tay |
| `face` | Sinh trắc khuôn mặt |
| `pin` | PIN/pattern |
| `sc` | Smart card |
| `user` | Kiểm tra sự hiện diện của user |
| `rba` | Risk-Based Authentication |
| `kba` | Knowledge-Based Authentication |
| `tel` | Xác nhận bằng cuộc gọi điện thoại |

IANA duy trì registry; những giá trị custom như `"webauthn"` hoặc `"push"` phải có agreement giữa OP/RP, không tự nhận là giá trị được RFC 8176 định nghĩa.

### 5.3. amr không phải audit log theo thời gian

~~~json
{"amr":["pwd","otp","mfa"]}
~~~

Không có nghĩa rằng vị trí các phần tử biểu diễn timestamp hoặc thứ tự chính thức của các bước challenge. Nếu cần chứng minh một MFA step-up xảy ra sau khi user đăng nhập, lưu event thời gian và transaction binding ở server-side store, không suy từ thứ tự mảng.

### 5.4. amr và bảo đảm xác thực

- `amr=["sms"]` không tự chứng minh MFA.
- `amr=["pwd","pwd"]` không phải hai yếu tố.
- `amr=["hwk"]` không đủ tự suy phishing resistance mà không biết authenticator/protocol.
- `amr=["fpt"]` có thể mô tả local user verification trên thiết bị, không nhất thiết fingerprint được OP trực tiếp xử lý.
- `amr=["mfa"]` là assertion về MFA theo policy của OP, cần tin vào issuer và quy trình phát hành.

Một OP có thể phát:

~~~json
{
  "acr": "urn:example:acr:password",
  "amr": ["pwd"]
}
~~~

hoặc sau khi thực sự hoàn tất MFA:

~~~json
{
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp", "mfa"]
}
~~~

Không tự tạo tổ hợp trên nếu authentication challenge chưa thành công.

## 6. auth_time, iat và độ mới của phiên

### 6.1. Ba thời điểm cần tách biệt

- `auth_time`: thời điểm End-User thực sự được xác thực.
- `iat`: thời điểm ID Token được phát hành.
- `exp`: thời điểm ID Token hết hiệu lực.

~~~json
{
  "auth_time": 1893456000,
  "iat": 1893459600,
  "exp": 1893460200
}
~~~

ID Token có thể được phát hành một giờ sau authentication event. Vì thế một ID Token vừa ký không đồng nghĩa user vừa đăng nhập lại.

### 6.2. Khi nào auth_time là bắt buộc?

Theo OIDC Core, `auth_time` phải hiện diện:

- Khi RP gửi tham số `max_age`.
- Khi RP yêu cầu `auth_time` như Essential Claim.

Các tình huống khác `auth_time` OPTIONAL.

Không chèn `auth_time=Instant.now()` tại Token Endpoint chỉ để làm đủ claim khi thực tế chỉ có refresh token hoặc session cũ.

### 6.3. max_age và reauthentication

~~~text
GET /oauth2/authorize?response_type=code
  &client_id=booking-bff
  &scope=openid%20profile
  &max_age=300
  &code_challenge=...
  &code_challenge_method=S256
~~~

Đây là request được xuống dòng để dễ đọc; request thật phải có `redirect_uri`/`state`/`nonce` theo policy và được URL-encode hợp lệ.

`max_age=300` yêu cầu authentication event trong khoảng tối đa 300 giây. Khi session quá cũ, OP phải xử lý reauthentication. `max_age=0` buộc authentication mới theo semantics OIDC. OP trả `auth_time` để RP đánh giá độ mới.

### 6.4. prompt=login và prompt=none

- `prompt=login` yêu cầu OP prompt xác thực lại.
- `prompt=none` không cho phép tương tác UI. Nếu user cần MFA/reauthentication mà không thể thực hiện im lặng, OP trả lỗi như `login_required` hoặc `interaction_required` theo flow.
- `max_age` yêu cầu độ mới và `auth_time`; không thay bằng `iat`.

Không tự phát `acr=mfa` để “xử lý” request `prompt=none` không thể hoàn thành.

### 6.5. Refresh ID Token không làm mới authentication

OIDC có thể phát ID Token mới khi dùng refresh token, tùy profile/flow. Khi đó:

- `iat` thể hiện thời điểm token mới được phát hành.
- `auth_time` nếu có phải phản ánh thời điểm **authentication gốc**.
- Refresh không tự thực hiện MFA mới.
- `acr`/`amr` không được nâng cấp nếu không có verified authentication event mới.

Nếu RP yêu cầu user MFA trong 5 phút gần nhất, một ID Token vừa phát lại từ refresh token cũ **không thỏa** chỉ vì `iat` mới.

## 7. acr_values, claims parameter và Essential Claim

### 7.1. acr_values là yêu cầu ưu tiên

~~~text
acr_values=urn:example:acr:mfa urn:example:acr:password
~~~

`acr_values` là chuỗi space-separated theo thứ tự ưu tiên. OP được **yêu cầu** xét những giá trị đó khi xử lý Authentication Request, nhưng `acr_values` yêu cầu `acr` như **Voluntary Claim**, không phải Essential Claim.

RP không được suy rằng chỉ vì đã gửi `acr_values=mfa` thì user chắc chắn đã hoàn tất MFA. Phải kiểm tra `acr` thực tế của ID Token được xác minh.

### 7.2. Yêu cầu Essential ACR qua claims parameter

Nếu OP hỗ trợ `claims` request parameter, RP có thể gửi JSON sau (được URL-encode trong request thật):

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:acr:mfa",
        "urn:example:acr:phishing-resistant"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

Theo OIDC Core, khi `acr` là Essential Claim và có `values` cụ thể:

- OP **MUST** trả `acr` khớp một trong các giá trị được yêu cầu nếu hỗ trợ `claims` parameter.
- OP **MAY** yêu cầu End-User xác thực lại với các yếu tố bổ sung.
- Nếu không đạt yêu cầu, OP **MUST** xem đó là thất bại authentication.
- RP vẫn phải xác minh giá trị thực tế, không chỉ dựa vào request.
- `auth_time` Essential làm `auth_time` bắt buộc trong ID Token.

**Không giả định** Spring Authorization Server 1.x tự triển khai mọi semantics `claims`/Essential ACR và workflow step-up. Cần kiểm tra version/extension rồi tích hợp authentication policy.

### 7.3. Không gửi đồng thời những yêu cầu ACR mâu thuẫn

OIDC Core quy định kết hợp `acr_values` với một individual `acr` request qua `claims` có danh sách `values` cụ thể có behavior chưa được chuẩn hóa đầy đủ. Nên chọn cách yêu cầu theo contract OP/RP và luôn kiểm tra kết quả.

### 7.4. Bảng quyết định

| Tham số | Dùng để làm gì? | Hậu quả khi không đáp ứng |
| --- | --- | --- |
| `acr_values` | Ưu tiên ACR, voluntary | RP tự quyết định từ kết quả thực tế |
| `claims.id_token.acr.essential=true` | Yêu cầu ACR trong tập được nêu | OP hỗ trợ claims phải đáp ứng hoặc fail authentication |
| `claims.id_token.auth_time.essential=true` | Yêu cầu thời điểm xác thực | ID Token phải có auth_time |
| `max_age` | Giới hạn tuổi tối đa authentication event | OP reauthenticate khi cần; trả auth_time |
| `prompt=login` | Yêu cầu đăng nhập lại | Không chứng minh MFA, vẫn cần kiểm tra claim |
| `prompt=none` | Không cho phép interaction | Trả lỗi nếu cần reauth/step-up tương tác |

## 8. Case study: step-up trước hành động nhạy cảm

Giả sử ứng dụng BFF cho phép xem booking khi user đăng nhập bằng mật khẩu, nhưng yêu cầu MFA khi sửa thông tin thanh toán.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant BFF as Booking BFF
    participant OP as OpenID Provider
    participant S as Server-side Evidence Store

    U->>BFF: Đăng nhập
    BFF->>OP: OIDC Authorization Code + PKCE
    OP->>U: Password login
    U-->>OP: Password hợp lệ
    OP->>S: auth_time, amr=pwd, acr=password
    OP-->>BFF: ID Token acr=password
    BFF->>BFF: Cho phép session thường
    U->>BFF: Yêu cầu đổi tài khoản thanh toán
    BFF->>OP: Step-up request + Essential acr=mfa + max_age
    OP->>U: MFA challenge
    U-->>OP: Yếu tố thứ hai hợp lệ
    OP->>S: Ghi evidence MFA đã hoàn tất
    OP-->>BFF: ID Token acr=mfa, amr=pwd+otp
    BFF->>BFF: Verify token, acr, auth_time và quyền
    BFF-->>U: Cho tiếp tục nếu business authorization đạt
~~~

Đây là **kiến trúc mục tiêu**, không phải tính năng được bật tự động khi gọi `OidcConfigurer` hoặc thêm `JwtEncodingContext` customizer.

### 8.1. Nếu user đã có session MFA

OP có thể tái sử dụng authentication context nếu policy cho phép và `auth_time` đủ mới. Nếu MFA quá cũ hoặc policy đòi reauthentication, OP phải thực hiện step-up/reauthentication mới.

### 8.2. Nếu challenge thất bại

- Không nâng `acr`.
- Không thêm `amr=["pwd","otp","mfa"]` như thể OTP đã thành công.
- Không phát ID Token thỏa Essential ACR.
- Áp dụng error response OIDC, rate limit và audit phù hợp.

### 8.3. Nếu RP không dùng Essential ACR

Nếu RP chỉ gửi `acr_values=mfa` (voluntary), OP có thể không đáp ứng đầy đủ. RP phải tự đánh giá `acr` và từ chối thao tác nhạy cảm nếu assurance không đủ.

## 9. Bật OIDC trong Spring Authorization Server

### 9.1. OIDC configurer

Ví dụ SAS 1.5.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là fragment: ứng dụng cần application SecurityFilterChain phục vụ Resource Owner login, `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer/JWK signing và các bean khác. OIDC UserInfo Endpoint có yêu cầu JWT/Resource Server riêng theo cấu hình và phiên bản.

### 9.2. Đăng ký client dùng OIDC và PKCE

~~~java
RegisteredClient bookingBff = RegisteredClient.withId("booking-bff-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.test/login/oauth2/code/booking")
    .scope("openid")
    .scope("profile")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

Đây là mảnh registration; `passwordEncoder` và `secretFromSecureConfig` là dependency/secret manager, không hardcode credential. Việc đăng ký `openid` không tự xác minh MFA và không bảo đảm xuất hiện `acr/amr`.

### 9.3. JwtEncodingContext là nơi tùy biến claims

Theo Spring Authorization Server, `JwtGenerator` có thể nhận `OAuth2TokenCustomizer<JwtEncodingContext>`.

~~~java
if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
    // Tùy biến access token cho Resource Server.
} else if (OidcParameterNames.ID_TOKEN.equals(
        context.getTokenType().getValue())) {
    // Tùy biến ID Token cho Relying Party.
}
~~~

`OidcParameterNames` có package `org.springframework.security.oauth2.core.oidc`. Không thêm `acr/amr/azp` bừa vào mọi JWT access token khi chỉ muốn tùy biến ID Token.

## 10. Lưu verified authentication evidence

### 10.1. Tại sao cần evidence store?

User đã đăng nhập ở Authorization Endpoint, trong khi ID Token thường được tạo khi client đổi code tại Token Endpoint. Hai request có thể khác connection, khác server instance và khác thời điểm.

Nếu chỉ đọc request parameter `acr_values` ở Token Endpoint, đó là yêu cầu của RP, **không chứng minh user đã qua MFA**.

Một record nội bộ minh họa:

~~~java
import java.time.Instant;
import java.util.List;

public record VerifiedAuthenticationEvidence(
    String subject,
    Instant authenticatedAt,
    String acr,
    List<String> amr
) {
}
~~~

Model do ứng dụng tự định nghĩa, không phải class SAS có sẵn.

### 10.2. Những bằng chứng đáng tin

| Nguồn dữ liệu | Có thể dùng? | Điều kiện |
| --- | --- | --- |
| Successful password authentication event ở OP | Có | OP thực sự kiểm tra credential |
| Successful MFA challenge với transaction binding | Có | Đã xác minh yếu tố độc lập theo policy |
| Server-side authentication/authorization store | Có | Bind đúng user/session/client/auth request |
| HTTP `acr_values` chưa xử lý | **Không** | Chỉ là request preference |
| Header `X-MFA: true` từ internet | **Không** | Có thể bị giả mạo |
| User profile tự khai | Không | Không chứng minh authentication method |
| `Instant.now()` lúc Token Endpoint phát token | Không cho auth_time | Không phải thời điểm xác thực |
| Refresh token grant | Không cho MFA mới | Không có user challenge |

### 10.3. Evidence phải được gắn đúng event

Production nên lưu:

- User subject + authentication event ID.
- Session/authorization transaction binding và client/tenant context phù hợp.
- Thời điểm user thực sự xác thực.
- Các factors đã vượt qua kiểm tra, MFA challenge ID không chứa secret.
- ACR do policy engine tính sau khi xác thực thành công.
- Version của assurance policy và retention/TTL hợp lệ.

Không lưu một biến toàn cục `lastAcrByUserId` rồi tái sử dụng cho mọi phiên của user. Điều này có thể khiến session A đã MFA làm session B chỉ dùng mật khẩu nhận nhầm claim assurance cao.

## 11. Code tùy biến acr/amr/auth_time có kiểm soát

### 11.1. Service contract do ứng dụng triển khai

~~~java
import java.util.Optional;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;

public interface AuthenticationEvidenceService {

    // Chỉ trả evidence đã xác minh cho đúng principal,
    // session và authorization transaction trong context.
    Optional<VerifiedAuthenticationEvidence> findVerifiedFor(
        JwtEncodingContext context);
}
~~~

Implementation phải tra từ server-side store đáng tin, không trực tiếp dùng HTTP body hoặc untrusted headers.

### 11.2. Tùy biến ID Token bằng một bean

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration
class OidcClaimsConfig {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> oidcClaimsCustomizer(
            AuthenticationEvidenceService evidenceService) {

        return context -> {
            if (!OidcParameterNames.ID_TOKEN.equals(
                    context.getTokenType().getValue())) {
                return;
            }

            Optional<VerifiedAuthenticationEvidence> evidence =
                evidenceService.findVerifiedFor(context);

            if (evidence.isEmpty()) {
                // Không tự bịa auth_time/acr/amr. Nếu Essential ACR
                // hoặc max_age bắt buộc, policy phải từ chối flow
                // TRƯỚC bước phát ID Token.
                return;
            }

            VerifiedAuthenticationEvidence verified = evidence.get();

            if (verified.authenticatedAt() != null) {
                context.getClaims().claim(
                    "auth_time",
                    verified.authenticatedAt().getEpochSecond());
            }

            if (verified.acr() != null && !verified.acr().isBlank()) {
                context.getClaims().claim("acr", verified.acr());
            }

            if (verified.amr() != null && !verified.amr().isEmpty()) {
                context.getClaims().claim(
                    "amr",
                    List.copyOf(verified.amr()));
            }
        };
    }
}
~~~

`AuthenticationEvidenceService` và `VerifiedAuthenticationEvidence` là những thành phần ứng dụng tự triển khai. Đây **không phải** ứng dụng OIDC hoàn chỉnh và **không** tạo MFA challenge. Cần thêm authentication policy engine có khả năng xử lý step-up/Essential ACR trước khi phát authorization code/ID Token.

### 11.3. Thêm azp theo extension

Nếu một extension yêu cầu `azp` và audience policy đã được kiểm tra, có thể thêm trong cùng customizer:

~~~java
if (profileRequiresAuthorizedParty
        && OidcParameterNames.ID_TOKEN.equals(
            context.getTokenType().getValue())) {

    String authorizedClientId =
        context.getRegisteredClient().getClientId();

    context.getClaims().claim("azp", authorizedClientId);
}
~~~

`profileRequiresAuthorizedParty` là kết quả cấu hình/policy server, không phải biến do client tự gửi. Không tạo một bean customizer thứ hai trùng kiểu chỉ để thêm `azp`; có thể dùng composite/wiring tường minh.

### 11.4. Không ghi đè claim chuẩn

Không sửa tùy tiện:

- `iss`: issuer của OP.
- `sub`: subject user (không thay bằng email).
- `aud`: audience của ID Token, phải gồm client ID.
- `nonce`: ràng buộc authentication request khi có nonce.
- `iat`/`exp`: thời điểm theo protocol/token policy.

Một lỗi tùy biến claim có thể làm ID Token **ký hợp lệ nhưng sai giao thức**.

### 11.5. Khi tự cấu hình DelegatingOAuth2TokenGenerator

Khi không tự cấu hình generator, SAS có thể tự phát hiện bean `OAuth2TokenCustomizer<JwtEncodingContext>` để gắn vào `JwtGenerator`. Nếu tự tạo delegating bean, cần wire tường minh:

~~~java
JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
jwtGenerator.setJwtCustomizer(oidcClaimsCustomizer);

OAuth2TokenGenerator<?> generator =
    new DelegatingOAuth2TokenGenerator(
        jwtGenerator,
        new OAuth2AccessTokenGenerator(),
        new OAuth2RefreshTokenGenerator());
~~~

Đây là fragment giả định các bean `jwtEncoder` và `oidcClaimsCustomizer` đã tồn tại. Giữ generator access/reference/refresh phù hợp thay vì chỉ còn `JwtGenerator`. Với nhiều customizer cùng generic type, cần composite hoặc qualifier rõ ràng.

## 12. Policy acr phải chạy trước khi phát ID Token

`JwtEncodingContext` chỉ nên phản ánh **kết quả xác thực thực sự**. Nếu `acr` là Essential Claim và OP không thể đáp ứng, flow phải thất bại ở authentication/policy layer.

~~~mermaid
flowchart TD
    REQ["OIDC Authorization Request<br/>acr_values / claims / max_age"]
    POLICY["Authentication Policy Engine"]
    EXIST{"Session đạt assurance<br/>và freshness?"}
    STEP["Password / MFA / Step-up"]
    PASS{"Authentication pass?"}
    EVID["Verified Evidence Store"]
    AUTHZ["Authorization Code / Consent"]
    JWT["JwtGenerator + JwtEncodingContext"]
    IDT["ID Token"]
    ERR["OIDC authentication error"]

    REQ --> POLICY --> EXIST
    EXIST -->|"Có"| EVID
    EXIST -->|"Không"| STEP --> PASS
    PASS -->|"Có"| EVID
    PASS -->|"Không"| ERR
    EVID --> AUTHZ --> JWT --> IDT
~~~

Quan trọng:

1. `acr_values` là request preference, không phải kết quả.
2. Essential ACR không được giả lập bằng customizer.
3. `max_age` cần reauthentication và `auth_time` thật.
4. `prompt=none` không được âm thầm bỏ qua challenge cần user tương tác.
5. Evidence phải bind với đúng subject/client/authorization transaction.
6. Nếu không có evidence bắt buộc, **không** phát ID Token với các claim giả; phải xử lý lỗi trong flow.

## 13. RP xác minh azp, acr, amr và auth_time

### 13.1. Bước 1: xác minh ID Token cơ bản

Trước khi đọc authentication claims, RP dùng OIDC library để:

- Xác minh chữ ký/alg/key từ issuer tin cậy theo flow.
- `iss` khớp OP issuer.
- `aud` chứa `client_id` của RP và không chứa audience bổ sung không tin cậy.
- `exp` chưa hết hạn; `iat` hợp lý với clock skew.
- `nonce` khớp request nếu đã gửi và kiểm soát replay.
- Kiểm tra hash claims `at_hash`/`c_hash` khi flow/profile yêu cầu.

Nếu bất kỳ kiểm tra bắt buộc nào thất bại, không được dựa vào `acr`/`amr` để “cứu” token.

### 13.2. Bước 2: kiểm tra azp nếu có

Pseudocode:

~~~java
// idToken đã được xác minh chữ ký, iss và aud.
if (!idToken.audiences().contains(clientId)) {
    throw new AuthenticationFailure("Audience mismatch");
}

if (idToken.hasClaim("azp")) {
    String authorizedParty = idToken.getStringClaim("azp");

    if (!authorizedPartyPolicy.allows(clientId, authorizedParty)) {
        throw new AuthenticationFailure("Untrusted azp");
    }
}
~~~

`authorizedPartyPolicy` thể hiện contract của extension/OP/RP. Với profile đơn giản, rule thường là `authorizedParty.equals(clientId)`; nhưng không bỏ check audience.

### 13.3. Bước 3: kiểm tra ACR

~~~java
Set<String> acceptedAcrs = Set.of(
    "urn:example:acr:mfa",
    "urn:example:acr:phishing-resistant");

if (!acceptedAcrs.contains(idToken.getStringClaim("acr"))) {
    throw new StepUpRequiredException();
}
~~~

Đây là pseudocode RP đã xác minh token; nó không mô tả toàn bộ OpenID client library. Không so ACR theo alphabet hoặc thứ tự Unicode; policy phải liệt kê các lớp được phép.

### 13.4. Bước 4: kiểm tra AMR khi có requirement

Nếu nghiệp vụ cần một phương thức cụ thể, RP có thể xem `amr` theo contract với OP. Tuy nhiên:

- Một số OP không công bố `amr` dù xác thực có hiệu lực.
- `pwd` và `otp` không tự chứng minh phishing resistance.
- `mfa` cần được tin vào policy của OP.
- Nếu thiếu `amr`, RP phải có quy tắc fail/fallback/step-up rõ ràng.
- `amr` không thay kiểm tra `acr`/freshness khi action nhạy cảm.

### 13.5. Bước 5: kiểm tra auth_time

~~~java
Instant authenticatedAt =
    Instant.ofEpochSecond(idToken.getLongClaim("auth_time"));

Duration maxAge = Duration.ofMinutes(5);

if (authenticatedAt.isAfter(now.plus(allowedClockSkew))) {
    throw new AuthenticationFailure("Invalid auth_time");
}

if (authenticatedAt.isBefore(
        now.minus(maxAge).minus(allowedClockSkew))) {
    throw new StepUpRequiredException();
}
~~~

`now` và `allowedClockSkew` do RP cấu hình. `max_age` yêu cầu dựa vào `auth_time`, không phải `iat`. Clock skew không nên được dùng quá rộng làm mất ý nghĩa freshness.

## 14. Không dùng ID Token làm access token

| Thuộc tính | OIDC ID Token | OAuth2 access token |
| --- | --- | --- |
| Đối tượng nhận | RP / OIDC Client | Resource Server |
| Mục đích | Kết quả xác thực, thông tin danh tính | Authorization cho API |
| Audience | Client ID của RP | Resource/audience theo token policy |
| `azp`/`acr`/`amr` | Khi profile/flow áp dụng | Chỉ khi access-token profile/contract riêng yêu cầu |
| `scope` | Không phải nguồn quyền API | Dùng theo authorization grant |
| Cách sử dụng | RP xác minh rồi quản lý login session | Client gửi như Bearer hoặc sender-constrained token |

Sai:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer ID_TOKEN_VALUE
~~~

Resource Server phải từ chối ID Token dùng thay access token theo API security policy, ngay cả khi chữ ký OP hợp lệ và ID Token có `acr=mfa`.

### 14.1. UserInfo và sub

Nếu RP gọi OIDC UserInfo Endpoint, nó phải xác minh `sub` trong UserInfo response khớp `sub` ID Token. Không dùng việc `amr` giống nhau để thay subject consistency.

`email_verified` là thông tin về email, **không phải** bằng chứng authentication MFA.

## 15. Những claims xác thực mở rộng liên quan

| Claim/parameter | Vai trò | Lưu ý |
| --- | --- | --- |
| `auth_time` | Thời điểm xác thực user | Khác `iat` và bắt buộc trong trường hợp `max_age` |
| `nonce` | Chống replay/ràng buộc ID Token với request | So exact-match nếu request có nonce |
| `at_hash` | Hash rút gọn access token theo một số OIDC flows | Yêu cầu phụ thuộc flow |
| `c_hash` | Hash rút gọn authorization code trong Hybrid Flow | Không phải chữ ký trên code |
| `sid` | Session ID theo OIDC session/logout extensions | Không đồng nhất HTTP session ID thô |
| `email_verified` | Trạng thái email đã được OP xác minh | Không tự bằng MFA |
| `updated_at` | Thời điểm profile được cập nhật | Không phải lúc login |
| `acr_values` | Request tham chiếu ACR ưu tiên | Không phải ACR đã đạt |
| `claims` | Request individual claims | Essential ACR có semantics riêng |
| `prompt` | Điều khiển tương tác OP | Không tự cho kết quả authentication mạnh |
| `max_age` | Yêu cầu auth đủ mới | Cần auth_time |

`at_hash` và `c_hash` có nghĩa vụ khác nhau theo Authorization Code, Implicit và Hybrid Flow. Khi dùng Code + PKCE hiện đại, không tự thêm claim bất kỳ mà không kiểm tra profile.

## 16. Case studies

### 16.1. Mật khẩu đủ cho thao tác thông thường

~~~json
{
  "aud": "booking-bff",
  "sub": "user-4831",
  "auth_time": 1893456000,
  "acr": "urn:example:acr:password",
  "amr": ["pwd"]
}
~~~

BFF có thể thiết lập session thường, vẫn phải kiểm tra scope/quyền khi gọi API.

### 16.2. MFA thành công cho thao tác nhạy cảm

~~~json
{
  "aud": "booking-bff",
  "sub": "user-4831",
  "auth_time": 1893456600,
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp", "mfa"]
}
~~~

RP chỉ coi đủ assurance nếu ID Token đã được xác minh và policy chấp nhận ACR/freshness. API còn phải kiểm tra quyền thay đổi đối tượng.

### 16.3. RP yêu cầu MFA nhưng OP không đáp ứng

Nếu chỉ gửi `acr_values=mfa` (voluntary), OP có thể trả `acr=password`. RP phải tự yêu cầu step-up/thất bại thao tác.

Nếu OP hỗ trợ `claims` và RP yêu cầu Essential ACR thuộc tập cụ thể, OP phải đáp ứng hoặc coi authentication thất bại; không ký ID Token nói đã MFA khi OTP chưa thành công.

### 16.4. ID Token có nhiều audiences

~~~json
{
  "aud": ["booking-bff", "untrusted-rp"],
  "azp": "booking-bff"
}
~~~

RP `booking-bff` không được chấp nhận chỉ vì `azp` khớp; audience bổ sung không tin cậy phải bị từ chối theo ID Token validation.

### 16.5. Refresh ID Token sau 60 phút

~~~json
{
  "auth_time": 1893456000,
  "iat": 1893459600,
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp"]
}
~~~

`auth_time` vẫn mô tả authentication gốc. Một policy MFA trong vòng 5 phút không được dựa vào `iat` mới.

### 16.6. Hardware key chưa đủ chứng minh policy

~~~json
{
  "amr": ["hwk", "user"]
}
~~~

Không tự suy `acr=phishing-resistant`. OP cần xác minh chính sách về authenticator, user verification, origin binding và điều kiện chống phishing tương ứng.

## 17. Các lỗi bảo mật và phòng tránh

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `azp` là `aud` | Token substitution/mix-up | Luôn validate aud, azp theo profile |
| Luôn gắn `azp` không có extension | Claim thừa/sai contract | Chỉ thêm nếu thật sự cần |
| Coi `acr_values` là bằng chứng MFA | OP tuyên bố assurance giả | Tách request khỏi verified evidence |
| Đếm `amr` là số factors | MFA false positive | Đánh giá factor independence và policy |
| `auth_time=iat` lúc refresh | Session cũ trở thành “mới” | Giữ original auth event time |
| Dùng `email_verified` để xác định MFA | Sai assurance | Dùng successful authentication events |
| Lấy `X-MFA` từ untrusted proxy header | Claim spoofing | Strip/verify headers; server-side evidence |
| Chỉ lưu `lastAcrByUserId` | Trộn assurance giữa sessions | Bind evidence theo transaction/session/client |
| Chỉ kiểm tra acr, bỏ signature | Token giả có thể tự khai MFA | Verify ID Token trước |
| Dùng ID Token gọi Resource Server | Sai token audience/type | API chỉ chấp nhận access token |
| Coi `OidcConfigurer` là MFA engine | Không có step-up thật | Tự triển khai login/MFA challenge policy |
| Bỏ qua Essential ACR | Vi phạm OIDC contract | Fail authentication nếu không đạt |
| Dùng ACR theo so sánh chuỗi | Sai policy | Versioned explicit mapping |
| Coi OTP/SMS chắc chắn phishing-resistant | Overclaim assurance | Đánh giá authenticator theo chính sách |
| Không test refresh ID Token | auth_time sai và nâng assurance | Test retention auth context |

## 18. Ma trận kiểm thử

| Kịch bản | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| OIDC Code + PKCE login | Scope openid, client đúng | ID Token có iss/sub/aud/iat/exp |
| azp absent | Không dùng profile cần azp | RP không từ chối chỉ vì azp thiếu |
| azp present và hợp lệ | Extension yêu cầu | RP chấp nhận theo contract |
| azp mismatch | Giá trị khác client ID | RP từ chối theo policy |
| Audience không chứa client | ID Token cho RP khác | RP từ chối |
| Extra audience không tin cậy | aud có client khác | RP từ chối |
| Password only | Login chỉ pwd | Không phát acr=mfa |
| OTP success | MFA challenge pass | amr/ACR phản ánh evidence |
| OTP failure | Challenge sai | Không nâng acr/amr |
| acr_values voluntary | OP không đáp ứng | RP đánh giá actual acr |
| Essential ACR | OP hỗ trợ claims | Thành công đúng class hoặc lỗi authentication |
| Unsupported claims parameter | OP không hỗ trợ | Không khẳng định Essential ACR tự hoạt động |
| max_age trong request | Session cũ | Reauth, ID Token có auth_time |
| prompt=none cần MFA | Không thể làm im lặng | OIDC error |
| auth_time khác iat | Token phát sau login | Giữ auth time thật |
| Refresh ID Token | Có refresh grant | auth_time giữ nghĩa authentication gốc |
| User có hai sessions | Một session MFA, một password | Evidence không trộn |
| Claim amr custom | Giá trị chưa đăng ký | Có contract hoặc RP xử lý unknown |
| ID Token làm Bearer ở RS | Gửi nhầm token type | RS từ chối |
| OIDC UserInfo | Có `sub` | sub match ID Token |
| Signature tamper | JWT bị sửa | RP từ chối |
| Issuer mismatch | OP issuer khác | RP từ chối |
| Nonce mismatch | Nonce khác request | RP từ chối |
| Clock skew | Thời gian hơi lệch | Theo policy skew hạn chế |
| Sensitive PII | Token có secret/PII thừa | Test phát hiện regression |

### 18.1. Test claims với JwtDecoder thật

~~~java
@Test
void idTokenContainsVerifiedMfaEvidence() {
    Jwt idToken = jwtDecoder.decode(actualIdTokenValue);

    assertThat(idToken.getAudience()).contains("booking-bff");
    assertThat(idToken.getClaimAsString("acr"))
        .isEqualTo("urn:example:acr:mfa");
    assertThat(idToken.getClaimAsStringList("amr"))
        .contains("pwd", "otp");
    assertThat(idToken.getClaim("auth_time"))
        .isNotNull();
}
~~~

Đây là test body minh họa; phải cung cấp `jwtDecoder`, ID Token được phát bằng test keys, assertion library và fixture thật. Test decode chỉ chứng minh token mang claims và xác minh chữ ký/issuer theo decoder; **không chứng minh MFA đã thực sự diễn ra**. Cần end-to-end challenge test.

### 18.2. Kiểm thử không ảnh hưởng access token

Khi cùng flow phát ID Token và access token:

- ID Token chứa `acr/amr/auth_time` theo verified evidence.
- Access token không tự chứa authentication claims của ID Token nếu RS profile không yêu cầu.
- ID Token `aud` là RP client ID.
- Access token `aud` theo Resource Server policy.
- Không ghi đè `iss/sub/nonce/exp`.
- Nếu custom generator được cung cấp, customizer vẫn được gắn và refresh/reference generator không bị mất.

### 18.3. Test step-up và refresh end-to-end

1. Login bằng mật khẩu: nhận ACR password.
2. Request Essential ACR MFA: OP yêu cầu step-up.
3. OTP sai: không phát ACR MFA.
4. OTP đúng: evidence store ghi method và ACR.
5. RP kiểm tra ACR/freshness và chỉ tiếp tục khi policy đạt.
6. Sau một thời gian, refresh ID Token: auth_time không tự thay bằng iat.
7. Yêu cầu `max_age=0`: OP phải xử lý reauthentication.
8. Test song song hai sessions của cùng user: không được dùng evidence của session khác.

## 19. Vận hành và audit

### 19.1. Quản trị từ điển ACR

Mỗi ACR cần tài liệu có version:

- Giá trị string/URI ổn định, không tái sử dụng với nghĩa khác.
- Phương thức/factors được chấp nhận.
- Yêu cầu thiết bị, authenticator, phishing resistance.
- Độ mới tối đa và quy tắc reauthentication.
- Session/evidence binding và storage retention.
- Quy tắc fallback, recovery và step-up.
- Quy trình migration khi nhiều RPs phụ thuộc vào cùng class.
- Security review và regression tests trước khi sửa nghĩa.

Không thay ý nghĩa `urn:example:acr:mfa` đột ngột mà không đánh giá những RP đang tin cậy claim này.

### 19.2. Monitoring

| Metric | Mục tiêu |
| --- | --- |
| ID Token issuance count theo ACR | Theo dõi thay đổi assurance |
| MFA success/failure | Quan sát authentication challenge |
| Requested ACR vs satisfied ACR | Phát hiện mismatch OP/RP |
| Essential ACR failures | Policy không đáp ứng |
| max_age reauthentication count | Theo dõi freshness |
| auth_time missing when required | OIDC contract regression |
| azp mismatch | Token audience/client mix-up |
| Unknown amr values | Sai contract OP/RP |
| Refresh auth_time anomalies | Phát hiện reset auth_time |
| Step-up denied after policy pass | Kiểm tra business authorization |

Không log raw ID Token, OTP, private key, session cookie, client secret, biometric details hoặc authenticator secret. Audit chỉ cần correlation ID, policy version, client đã xác minh, protected subject identifier và kết quả.

### 19.3. Runbook khi RP báo không đủ MFA

1. Xác minh chữ ký, issuer, audience và nonce ID Token trước.
2. Đọc `acr`, `amr` và `auth_time` từ token đã xác minh.
3. Xác định RP yêu cầu `acr_values` (voluntary) hay Essential ACR qua `claims`.
4. Xác định OP/version có hỗ trợ cơ chế request tương ứng không.
5. Kiểm tra successful authentication events và evidence store ở OP.
6. Kiểm tra evidence bind đúng subject, session, client và authorization transaction.
7. Với `max_age`, kiểm tra auth_time thực và clock skew.
8. Với refresh, kiểm tra auth_time không bị reset thành iat.
9. Kiểm tra RP ACR allowlist và quy tắc bổ sung về AMR.
10. Chạy integration test; không “sửa” bằng cách hardcode `acr=mfa` tại token customizer.

## 20. Câu hỏi tự kiểm tra

**Câu 1:** azp và aud khác nhau thế nào?  
**Đáp án:** aud xác định audiences của ID Token, trong đó bắt buộc có RP client ID. azp là authorized party và OPTIONAL; nếu có phải chứa OAuth2 Client ID theo semantics áp dụng.

**Câu 2:** azp vắng mặt có khiến ID Token luôn sai không?  
**Đáp án:** Không. azp là OPTIONAL trong OIDC Core, trừ khi extension/profile cụ thể yêu cầu.

**Câu 3:** acr có thể tính bằng cách đếm số phần tử amr không?  
**Đáp án:** Không. acr là policy/context class; amr chỉ mô tả methods thực sự được dùng.

**Câu 4:** `amr=["pwd","otp"]` có nhất thiết chứng minh MFA mạnh không?  
**Đáp án:** Không. OP phải kiểm tra factor independence, challenge result, authenticator properties và policy.

**Câu 5:** acr_values có buộc OP trả ACR đầu tiên không?  
**Đáp án:** Không; đây là voluntary request theo thứ tự ưu tiên.

**Câu 6:** Essential ACR không đạt thì sao?  
**Đáp án:** Với OP hỗ trợ claims parameter, ACR essential có values được yêu cầu phải được đáp ứng hoặc coi flow là failed authentication.

**Câu 7:** auth_time và iat khác nhau ra sao?  
**Đáp án:** auth_time là lúc user được xác thực; iat là lúc ID Token được phát hành.

**Câu 8:** Refresh ID Token có làm auth_time mới lại không?  
**Đáp án:** Không; auth_time nếu có phản ánh authentication gốc.

**Câu 9:** JwtEncodingContext customizer có tự bật MFA không?  
**Đáp án:** Không; chỉ gắn claim. MFA cần login challenge, policy engine và verified evidence.

**Câu 10:** Có thể dùng ID Token để gọi API thay access token không?  
**Đáp án:** Không. ID Token dành cho RP, không dành cho Resource Server.

**Câu 11:** RP có được bỏ check aud vì azp khớp không?  
**Đáp án:** Không. Audience, issuer, signature, expiry và nonce vẫn bắt buộc theo profile.

**Câu 12:** Có được lấy acr trực tiếp từ HTTP request không?  
**Đáp án:** Không. Request là mong muốn của RP; claim phải đến từ bằng chứng xác thực do OP kiểm chứng.

## 21. Checklist production

- [ ] RP/OP hiểu đúng `azp`, `acr`, `amr` và phạm vi áp dụng.
- [ ] ID Token được ký/xác minh với `iss/sub/aud/iat/exp` hợp lệ.
- [ ] RP xác minh signature, issuer, audience và nonce trước khi dùng claims.
- [ ] azp chỉ phát/kiểm tra theo extension/profile, không thay aud.
- [ ] Từ điển ACR có định nghĩa, version và kiểm thử chính sách.
- [ ] ACR do authentication policy xác nhận, không lấy từ `acr_values`.
- [ ] AMR chứa phương thức đã thành công, dùng IANA names khi thích hợp.
- [ ] Không suy MFA/phishing resistance chỉ từ số lượng/tên amr.
- [ ] `acr_values` được coi là voluntary.
- [ ] Essential ACR được enforce khi OP hỗ trợ claims parameter.
- [ ] `max_age` làm OP reauthenticate khi cần, có auth_time thực.
- [ ] auth_time được lưu từ authentication event, không đặt bằng iat.
- [ ] Refresh ID Token không nâng assurance hoặc sửa auth_time giả.
- [ ] Evidence được bind với user/session/client/authorization transaction.
- [ ] JwtEncodingContext customizer chỉ tác động đúng ID_TOKEN.
- [ ] Không ghi đè claim chuẩn hoặc leak secrets/OTP/PII.
- [ ] Không dùng ID Token như API access token.
- [ ] Có test MFA success/failure, acr mismatch, multi-audience, refresh và multiple sessions.
- [ ] Có metrics/audit an toàn và runbook bước chẩn đoán.

## 22. Tài liệu chính thức và kết luận

- [OpenID Connect Core 1.0 — ID Token claims](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 — Authentication Request / acr_values](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest)
- [OpenID Connect Core 1.0 — Claims Parameter](https://openid.net/specs/openid-connect-core-1_0.html#ClaimsParameter)
- [OpenID Connect Core 1.0 — Requesting the acr Claim](https://openid.net/specs/openid-connect-core-1_0.html#acrRequests)
- [OpenID Connect Core 1.0 — Refreshing an Access Token](https://openid.net/specs/openid-connect-core-1_0.html#RefreshingAccessToken)
- [RFC 8176 — Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176)
- [IANA Authentication Method Reference Values Registry](https://www.iana.org/assignments/authentication-method-reference-values/)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Core Model / JwtEncodingContext](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints / OIDC](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)

**Kết luận:** `azp` mô tả authorized party, `acr` mô tả lớp ngữ cảnh xác thực, còn `amr` mô tả những phương thức đã được sử dụng. Chúng giúp RP quyết định khi nào cần reauthentication/step-up, nhưng chỉ hữu ích sau khi ID Token đã được xác minh và OP có bằng chứng xác thực đáng tin. Với Spring Authorization Server, hãy xử lý `acr_values`, Essential ACR, `max_age` và MFA trong authentication policy layer; sau đó mới phản ánh sự kiện đã xác minh vào ID Token bằng `JwtEncodingContext`. Không suy diễn từ request, không tự nâng quyền, không nhầm ID Token với access token và phải kiểm thử end-to-end toàn bộ flow.

