# Phân phối claims theo scope profile, email, address và phone

## 1. Từ OIDC scope tới thông tin người dùng

Trong OAuth 2.0, `scope` biểu diễn phạm vi quyền mà client yêu cầu và Authorization Server có thể cấp. Trong **OpenID Connect (OIDC)**, các scope chuẩn `profile`, `email`, `address` và `phone` còn giúp Relying Party (RP) đề nghị OpenID Provider (OP) cung cấp **standard claims** về người dùng đã xác thực.

Một Authorization Server viết bằng Spring Boot, Spring Security và Spring Authorization Server (SAS) phải giải quyết ba câu hỏi khác nhau:

1. **Client được phép yêu cầu scope nào?** — phụ thuộc client registration và policy.
2. **Người dùng/Authorization Server thực sự đồng ý cấp scope nào?** — phụ thuộc authentication, consent và chính sách dữ liệu.
3. **Các claims nào thực sự có thể trả cho RP, tại endpoint nào?** — phụ thuộc dữ liệu, độ tin cậy, mục đích sử dụng và cách triển khai ID Token/UserInfo.

Ví dụ, ứng dụng đặt lịch có thể đề nghị `openid profile email` để hiển thị tên và gửi xác nhận. Ứng dụng giao hàng có thể xin thêm `address phone`, nhưng không vì thế mà mọi người dùng bắt buộc phải có địa chỉ/điện thoại hoặc mọi client đều được nhận dữ liệu đó.

Bài thuộc chương **OIDC Core và ID Token** của module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, với mục tiêu học thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OIDC Authorization Server trong Spring Boot. Trọng tâm là **phân phối claims theo đúng bốn scope chuẩn**, chứ không đồng nhất scope được yêu cầu với dữ liệu chắc chắn được tiết lộ.

Sau khi học, bạn cần:
- Nhớ chính xác danh sách OIDC standard claims gắn với từng scope.
- Phân biệt `openid`, các scope yêu cầu claims, scope được cấp và claim thực sự phát hành.
- Chọn đúng giữa **ID Token**, **UserInfo Response** và **access token**.
- Trả `sub` ổn định, không giả mạo email/phone verification status và không lộ PII vượt nhu cầu.
- Thiết kế mapper theo **authorized scopes**, client policy và trạng thái dữ liệu.
- Cấu hình SAS để giới hạn scope/consent, tùy chỉnh UserInfo và kiểm thử với RP.

### 1.1. Bức tranh luồng phân phối

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Relying Party
    participant BR as Browser
    participant AS as Spring Authorization Server / OP
    participant U as Người dùng
    RP->>BR: Redirect authorization: scope=openid profile email
    BR->>AS: Authorization Code + PKCE request
    AS->>U: Login và hỏi consent theo policy
    U-->>AS: Chấp thuận phạm vi được phép
    AS->>AS: Xác định authorized scopes
    AS-->>BR: Authorization code + state
    BR-->>RP: Callback
    RP->>AS: POST token endpoint + code_verifier
    AS-->>RP: ID Token, access token (scope được cấp)
    RP->>AS: GET UserInfo với access token
    AS->>AS: Lọc claims theo scope + client policy + dữ liệu
    AS-->>RP: JSON gồm sub và các claims được phép
    RP->>RP: So sánh sub UserInfo với sub ID Token
~~~

## 2. Scope yêu cầu claims khác với claim đã được cấp

OIDC Core 1.0 định nghĩa các scope:
- `openid`: dấu hiệu bắt buộc để yêu cầu xác thực theo OIDC; tạo nền tảng cho ID Token.
- `profile`: đề nghị bộ thông tin hồ sơ tiêu chuẩn.
- `email`: đề nghị email và trạng thái xác minh email.
- `address`: đề nghị thông tin địa chỉ có cấu trúc.
- `phone`: đề nghị số điện thoại và trạng thái xác minh số điện thoại.

Chúng là **scope values để yêu cầu claims**, không phải bằng chứng rằng người dùng sở hữu dữ liệu hoặc đã đồng ý cho mọi client đọc tất cả các claim.

| Khái niệm | Ví dụ | Điều có thể kết luận |
| --- | --- | --- |
| **Requested scope** | Client gửi `scope=openid profile email phone` | Client mong muốn các nhóm thông tin đó |
| **Registered/allowed scopes** | Client được đăng ký `openid`, `profile`, `email` | Client không được phép tự nâng lên `phone` |
| **Authorized/granted scopes** | AS thực sự cấp `openid profile email` | Chỉ những scope này được dùng để quyết định claims |
| **Available claims** | User có `name`, `email` nhưng không có `picture` | Không thể tự tạo `picture` từ scope |
| **Released claims** | UserInfo trả `sub`, `name`, `email` | Đây là dữ liệu thật đã qua policy, không nhất thiết là mọi claim trong scope |

Trong SAS, `RegisteredClient.getScopes()` là tập phạm vi **client được đăng ký**. Tập đó không tự thay cho **authorized scopes** của một authorization/access token cụ thể.

### 2.1. Không có scope openid thì không thành OIDC authentication request

Ví dụ:
- `scope=openid profile email`: một yêu cầu OIDC hợp lệ về mặt scope (các điều kiện khác vẫn phải đúng).
- `scope=profile email`: chỉ các tên scope này **không biến** OAuth request thành yêu cầu OpenID Connect; không được mặc nhiên trả ID Token chỉ vì có `profile`.
- `scope=openid`: vẫn thực hiện OIDC login với `sub` trong ID Token, không đồng nghĩa được trả email, tên hoặc số điện thoại.

### 2.2. Scope cấp quyền yêu cầu, không cưỡng ép OP tiết lộ dữ liệu

OIDC Core `5.4` dùng các scope profile/email/address/phone để đề nghị **standard claims**, và các claim được yêu cầu qua scope được xử lý theo cơ chế **Voluntary Claims**. OP có thể không trả một claim nếu dữ liệu không tồn tại, không được xác minh, bị policy hạn chế hoặc người dùng không đồng ý.

Do đó, RP không nên viết logic:

~~~java
// SAI: scope email không bảo đảm có một email không-null
String email = oidcUser.getClaimAsString("email");
sendVerificationMail(email); // có thể null hoặc chưa được xác minh
~~~

Hãy xử lý thiếu claim, phân biệt verification state và có luồng yêu cầu người dùng nhập dữ liệu bổ sung ở ứng dụng nếu thực sự cần.

## 3. Bảng chuẩn: scope nào yêu cầu những claims nào?

Đây là bảng trọng tâm theo **OpenID Connect Core 1.0, `5.4 Requesting Claims using Scope Values**.

| OIDC scope | Standard claims được yêu cầu | Dạng dữ liệu / lưu ý |
| --- | --- | --- |
| `profile` | `name`, `family_name`, `given_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` | Claim hồ sơ; các trường có thể thiếu |
| `email` | `email`, `email_verified` | `email` là string; `email_verified` là boolean |
| `address` | `address` | JSON object theo cấu trúc `formatted`, `street_address`, `locality`, `region`, `postal_code`, `country` |
| `phone` | `phone_number`, `phone_number_verified` | Số điện thoại dạng string; verification là boolean |
| `openid` | Không yêu cầu bộ profile/email/address/phone; kích hoạt ngữ nghĩa OIDC và ID Token có `sub` | `sub` là định danh subject của người dùng tại issuer |

**Đừng nhầm tên scope và tên claim:** scope `profile` có một claim cũng tên `profile` (thường chứa URL trang hồ sơ), nhưng scope đó còn đề nghị nhiều claims khác. Ngược lại, `address` là scope và cũng là tên của một claim có giá trị dạng **object**, không phải string đơn giản.

### 3.1. Ví dụ các tổ hợp scope

| Requested scopes | Nhóm claims RP có thể nhận (nếu được cấp và có dữ liệu) |
| --- | --- |
| `openid` | `sub` và các standard ID Token authentication claims |
| `openid profile` | Thêm tên, nickname, locale, avatar, URL hồ sơ... |
| `openid email` | Thêm `email` và `email_verified` |
| `openid address` | Thêm object `address` |
| `openid phone` | Thêm `phone_number` và `phone_number_verified` |
| `openid profile email address phone` | Có thể đề nghị toàn bộ nhóm; không đồng nghĩa tất cả được trả |

Nếu server có các custom scopes như `orders.read`, `role.read` hoặc `tenant.admin`, chúng **không** tự thuộc scope chuẩn OIDC. Muốn công bố claims tùy biến theo các scope đó cần thiết kế policy, schema và tài liệu rõ ràng, không nhét mọi dữ liệu vào `profile`.

## 4. Scope profile: bộ dữ liệu hồ sơ, không phải quyền truy cập toàn bộ tài khoản

Các claim tiêu chuẩn được đề nghị bởi `profile` có semantics riêng:

| Claim | Mô tả | Cách xử lý |
| --- | --- | --- |
| `name` | Tên đầy đủ để hiển thị | Không coi là định danh duy nhất |
| `family_name` | Họ/tên gia đình | Có thể không phù hợp mọi văn hóa đặt tên |
| `given_name` | Tên gọi | Có thể thiếu |
| `middle_name` | Tên đệm | Có thể thiếu |
| `nickname` | Biệt danh | Có thể trùng giữa người dùng |
| `preferred_username` | Username người dùng muốn hiển thị | Không mặc nhiên là duy nhất/toàn cục |
| `profile` | URL trang hồ sơ | Là URL, không phải JSON object |
| `picture` | URL ảnh đại diện | Có thể thay đổi, cần bảo vệ privacy khi tải |
| `website` | URL website của người dùng | Không xem là URL đáng tin cho server-side fetch |
| `gender` | Giá trị giới tính tự khai theo format OIDC | Dữ liệu cá nhân nhạy cảm; không ép điền |
| `birthdate` | Ngày sinh theo định dạng ISO 8601 | Có thể chỉ có năm hoặc tháng/ngày; tránh suy tuổi khi dữ liệu không đủ |
| `zoneinfo` | Múi giờ theo database IANA | Ví dụ `Asia/Ho_Chi_Minh` |
| `locale` | Locale theo BCP 47 | Ví dụ `vi-VN`, `en-US` |
| `updated_at` | Unix time (NumericDate) khi profile cập nhật | Không tự đồng nhất với thời điểm cấp token |

Ví dụ một phần UserInfo khi chỉ cấp `openid profile`:

~~~json
{
  "sub": "user-7c92",
  "name": "Nguyễn An",
  "given_name": "An",
  "family_name": "Nguyễn",
  "preferred_username": "an.nguyen",
  "locale": "vi-VN",
  "zoneinfo": "Asia/Ho_Chi_Minh",
  "picture": "https://cdn.example.com/avatars/user-7c92.png",
  "updated_at": 1794800000
}
~~~

Không phải mọi claim profile đều phải xuất hiện. Một người có thể không có website, không lưu nickname hoặc không muốn chia sẻ birthdate. **Không đưa `null` hàng loạt để “đủ schema” nếu chính sách sản phẩm muốn biểu diễn claim vắng mặt**; RP phải hiểu claim được phép thiếu.

### 4.1. Lỗi định danh bằng tên hiển thị

**Không dùng** `name`, `preferred_username` hoặc `picture` làm primary key tài khoản RP. Các giá trị này có thể đổi, bị trùng hoặc do người dùng tự đặt. RP nên dùng cặp **`(iss, sub)`** đã xác minh để định danh người dùng OIDC.

### 4.2. Không biến profile thành nguồn PII mặc định

Scope `profile` có thể đề nghị `gender` và `birthdate`. Chúng có tính riêng tư cao và có thể không cần cho đa số ứng dụng. OP nên triển khai data minimization: chỉ tiết lộ claims trong phạm vi dữ liệu đã có, mục đích đã được cho phép và policy hiện hành. Nếu sản phẩm cần phân loại độ tuổi, cân nhắc trả assertion “đủ tuổi theo ngưỡng” theo extension riêng thay vì cấp ngày sinh chính xác.

## 5. Scope email: email và email_verified

### 5.1. Hai claim có vai trò khác nhau

~~~json
{
  "sub": "user-7c92",
  "email": "an@example.com",
  "email_verified": true
}
~~~

- `email`: địa chỉ email của end-user, kiểu string. Không bảo đảm duy nhất, bất biến hoặc là key định danh toàn cục.
- `email_verified`: boolean cho biết OP đã xác minh quyền kiểm soát email theo cơ chế xác minh của mình (`true` khi đã xác minh, `false` khi chưa).

**`email_verified=true` không có nghĩa OP bảo đảm email vẫn có quyền kiểm soát vĩnh viễn**, cũng không đồng nghĩa email là danh tính đủ mạnh để liên kết hai tài khoản từ hai OP khác nhau.

### 5.2. Cách biểu diễn trạng thái

| Trường hợp | JSON nên trả | Cách RP diễn giải |
| --- | --- | --- |
| Email có sẵn và được OP xác minh | `email` + `email_verified: true` | Có thể dùng theo mức tin cậy và chính sách sản phẩm |
| Email có sẵn nhưng chưa được xác minh | `email` + `email_verified: false` | Không được mặc nhiên coi là địa chỉ đã được chứng minh |
| Không có email / người dùng không cho phép chia sẻ | Bỏ `email`; xử lý verified flag theo chính sách dữ liệu | RP phải có luồng thiếu email |
| Không biết được verification state | Không tự đặt `true` | Tránh thổi phồng độ tin cậy |

Đặc biệt trong đăng nhập liên kết, **không gộp tài khoản chỉ bằng cách so email** trừ khi có quy trình linking độc lập với bằng chứng đủ mạnh. Hai OP có thể cấp cùng địa chỉ email cho hai subject khác nhau hoặc email có thể được tái cấp cho người khác.

### 5.3. Email không tự bảo đảm khả năng gửi thư

Một địa chỉ có thể đã xác minh lúc đăng ký nhưng nay không còn nhận được thư. Nếu ứng dụng dùng email để reset password, thanh toán hay gửi dữ liệu nhạy cảm, hãy áp dụng thêm kiểm tra, rate limit và chính sách bảo mật theo ngữ cảnh.

## 6. Scope address: claim object có cấu trúc

`address` vừa là scope name, vừa là tên standard claim. **Giá trị claim `address` là JSON object** theo mô hình address của OIDC Core, không đơn thuần là một chuỗi địa chỉ.

Ví dụ:

~~~json
{
  "sub": "user-7c92",
  "address": {
    "formatted": "12 Đường Hoa Sen\nPhường Trung Tâm, TP. Hồ Chí Minh\nViệt Nam",
    "street_address": "12 Đường Hoa Sen",
    "locality": "TP. Hồ Chí Minh",
    "region": "Hồ Chí Minh",
    "postal_code": "700000",
    "country": "Việt Nam"
  }
}
~~~

### 6.1. Ý nghĩa thành phần

| Key | Ý nghĩa |
| --- | --- |
| `formatted` | Địa chỉ ở dạng văn bản nhiều dòng phù hợp hiển thị, dùng newline nếu cần |
| `street_address` | Thành phần số nhà/tên đường/địa chỉ cấp phố |
| `locality` | Thành phố hoặc địa phương |
| `region` | Tỉnh, bang, vùng hành chính |
| `postal_code` | Mã bưu chính |
| `country` | Quốc gia; theo OIDC Core là thành phần tên quốc gia, **không mặc định ISO-3166 alpha-2 code** |

OIDC Core mô tả `country` là giá trị tên quốc gia (ví dụ "USA"). Một hệ thống có thể có mã quốc gia nội bộ theo ISO-3166 nhưng không được suy rằng mọi OIDC Provider đều dùng mã hai ký tự. Nếu cần interoperability, hãy tài liệu hóa format thực tế và chuẩn hóa dữ liệu trước khi phát hành claim.

Một address object có thể chỉ có `formatted` hoặc chỉ có vài trường thành phần. **Không bắt buộc** mọi key đều xuất hiện. Dữ liệu địa chỉ mang tính nhạy cảm và dễ lỗi thời; không xem “địa chỉ hồ sơ” là địa chỉ nhận hàng đã được người dùng xác nhận cho mỗi giao dịch.

### 6.2. Địa chỉ cho giao hàng hay hóa đơn cần policy riêng

Đơn hàng thực tế cần tên người nhận, địa chỉ giao nhận, kiểm tra quy tắc hành chính và consent tại thời điểm giao dịch. Claim `address` do OP trả có thể chỉ là địa chỉ liên hệ đã lưu. RP nên cho người dùng xác nhận/cập nhật, thay vì âm thầm dùng thông tin OIDC cho mục đích khác.

## 7. Scope phone: phone_number và phone_number_verified

~~~json
{
  "sub": "user-7c92",
  "phone_number": "+84901234567",
  "phone_number_verified": false
}
~~~

- `phone_number`: số điện thoại end-user; OIDC Core khuyến nghị biểu diễn theo chuẩn **E.164** khi có thể để tránh mơ hồ mã quốc gia.
- `phone_number_verified`: boolean cho biết OP đã xác minh quyền kiểm soát số điện thoại bằng phương pháp của mình.

| Trạng thái | Cách xử lý |
| --- | --- |
| `phone_number_verified=true` | OP báo số đã được xác minh theo policy; RP vẫn cân nhắc mức tin cậy/ngữ cảnh |
| `phone_number_verified=false` | Không coi số là kênh đáng tin để xác minh lại giao dịch nhạy cảm |
| Thiếu `phone_number` | Không giả định số tồn tại hoặc tự gắn số từ nguồn không được ủy quyền |
| Đổi/recycle số | Cần re-verification/đánh giá lại linking theo chính sách sản phẩm |

Một số điện thoại từng được xác minh có thể được nhà mạng tái cấp. Vì vậy, `phone_number_verified=true` không nên tự động trở thành MFA mạnh vĩnh viễn, đặc biệt với giao dịch tài chính hoặc khôi phục tài khoản.

## 8. Phân phối ở đâu: ID Token, UserInfo hay access token?

Một lỗi OIDC phổ biến là nhìn thấy các scope profile/email/address/phone rồi đưa **toàn bộ PII vào ID Token hoặc access token**. Cách làm này vừa tăng bề mặt lộ dữ liệu, vừa khiến downstream services nhận dữ liệu không cần thiết.

| Nơi chứa | Mục đích | Khuyến nghị cho standard profile claims |
| --- | --- | --- |
| **ID Token** | Chứng minh kết quả authentication cho RP; xác nhận issuer, subject, audience và ngữ cảnh đăng nhập | Ưu tiên tối thiểu; chỉ thêm claims nếu thực sự cần và được policy cho phép |
| **UserInfo Endpoint** | Trả thông tin end-user cho RP dùng access token phù hợp | Nơi tự nhiên để trả claims theo các standard scopes |
| **Access Token (JWT/opaque)** | Credential/ủy quyền gọi protected resources | Chỉ nên chứa token-related claims, authorization data tối thiểu; không mặc định chép PII OIDC |
| **Introspection** | Trả metadata về trạng thái token cho resource server được xác thực | Không mặc định là nguồn toàn bộ hồ sơ OIDC |
| **Consent record** | Ghi phạm vi đã chấp thuận cho client | Không phải UserInfo response và không tự tạo claims |

### 8.1. Authorization Code Flow: ID Token tối thiểu, UserInfo theo scope

Với OIDC Authorization Code Flow, OP có thể trả ID Token có claims nền tảng:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-7c92",
  "aud": "portal-client",
  "iat": 1794800100,
  "exp": 1794803700
}
~~~

Đây là payload giản lược; ID Token thực tế có thể có thêm claims bắt buộc theo flow và cấu hình, ví dụ `auth_time`, `nonce` (nếu RP yêu cầu), `azp` trong một số tình huống, `at_hash` tùy profile. Token phải được ký/xác minh theo OIDC Core.

RP dùng access token để gọi `/userinfo` và lấy những claims mà OP thực sự cho phép phát hành. Điều này cho phép giữ ID Token gọn, đồng thời phân quyền truy cập UserInfo theo scope và lifetime của access token.

**Quan trọng:** OIDC Core cho phép một số claims được trả trong ID Token theo flow/profile và tùy yêu cầu `claims` parameter; không có quy tắc rằng mọi claim profile bắt buộc phải nằm trong ID Token. Ngược lại, đưa tất cả vào UserInfo cũng phải kiểm tra consent, scope và policy.

### 8.2. UserInfo phải có sub và chống token substitution

Một UserInfo response chuẩn cần có `sub` của người dùng. **RP MUST xác minh `sub` trong UserInfo response trùng chính xác `sub` đã nhận trong ID Token**; nếu không khớp, không được sử dụng UserInfo response.

~~~text
ID Token:  iss = https://auth.example.com
           sub = user-7c92

UserInfo:  sub = user-7c92        -> có thể tiếp tục dùng claims

UserInfo:  sub = other-user       -> PHẢI từ chối response
~~~

Dù cả hai tài liệu đều có email giống nhau, subject mismatch vẫn là lỗi bảo mật. Cặp `(iss, sub)` là khóa liên kết danh tính của RP, không phải email hay phone number.

### 8.3. UserInfo access token không phải ID Token

HTTP request tới UserInfo thường dùng:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Không gửi ID Token trong header Authorization thay access token. OP phải kiểm tra access token hợp lệ, đúng loại/ngữ cảnh, chưa hết hạn/thu hồi theo policy và có scope thích hợp trước khi tiết lộ claims.

### 8.4. Scope email không tự cho API quyền gửi email

`email` là một OIDC scope yêu cầu standard claims. Nó **không** cấp quyền thao tác như `mail.send`, `contacts.write`, `orders.read`, không cấp quyền truy cập mailbox và không thể thay một OAuth API permission riêng.

## 9. Quy trình quyết định claim được phát hành

Một thiết kế rõ ràng không dùng logic “nếu client đã từng được đăng ký scope thì trả hết claims”. Thay vào đó, với mỗi request, cần xác định:

~~~mermaid
flowchart TD
    A[UserInfo request nhận access token] --> B{Token hợp lệ và thuộc OIDC authorization?}
    B -->|Không| X[Từ chối]
    B -->|Có| C[Tra chủ thể sub và effective authorized scopes]
    C --> D[Đối chiếu RegisteredClient và policy/consent]
    D --> E[Đọc dữ liệu hồ sơ từ nguồn tin cậy]
    E --> F{Dữ liệu có và được phép tiết lộ?}
    F -->|Không| G[Bỏ claim hoặc từ chối theo contract cụ thể]
    F -->|Có| H[Chọn claims phù hợp scope]
    H --> I[Kiểm tra schema, kiểu dữ liệu và PII policy]
    I --> J[Trả UserInfo có sub hợp lệ]
    G --> J
    B --> K[Không được tự bypass token validation]
~~~

Một cách nghĩ hữu ích là:

~~~text
released_claims =
    standardClaimsFor(authorized_scopes)
    ∩ claimsActuallyAvailableFor(subject)
    ∩ claimsAllowedByPolicy(client, subject, tenant, purpose)
    ∩ claimsAllowedByUserConsent(...)
~~~

Công thức trên diễn giải **policy thiết kế**, không phải một phép giao tập hợp mà SAS tự thực hiện nguyên vẹn. Consent có thể ở cấp scope hoặc granular claims tùy hệ thống. Khi consent cấp scope `profile`, bạn vẫn có thể áp data-minimization và bỏ những claims nhạy cảm.

### 9.1. Xác định scope hiệu lực từ đâu?

Trong Authorization Code Flow, client gửi `scope` khi bắt đầu authorization. Authorization Server phải xác định tập scope cuối cùng hợp lệ và ghi nhận trong authorization/token. Khi UserInfo được gọi, **không** sử dụng query parameter `scope` do caller tự gửi để quyết định claims; phải dựa vào authorization đã được xác thực của access token đang trình.

Các tầng cần tách:

| Nguồn | Có thể dùng làm nguồn kiểm tra? | Vì sao |
| --- | --- | --- |
| `RegisteredClient.scopes` | Có, để kiểm tra client được phép yêu cầu gì | Chỉ là giới hạn tối đa, không phải toàn bộ scope đã cấp |
| Requested `scope` tại authorization endpoint | Có, sau khi kiểm tra/chuẩn hóa | Chỉ thể hiện yêu cầu của client |
| Consent/authorization đã lưu | Có | Cho biết kết quả chấp thuận theo mô hình của AS |
| Scope gắn với access token đã xác thực | **Có; nguồn quyết định thực tế ở UserInfo** | Giới hạn dữ liệu cho đúng token được gửi |
| Header tùy ý như `X-Scope: email` | **Không** | Có thể bị client giả mạo |
| Claim tùy ý trong JWT chưa xác thực | **Không** | Không có bằng chứng issuer/authorization |

### 9.2. Khác biệt giữa consent, client policy và tính sẵn có

Giả sử:
- Client được đăng ký `openid profile email address phone`.
- Người dùng chỉ đồng ý `openid profile email`.
- Email của người dùng chưa xác minh.
- Hệ thống có địa chỉ và số điện thoại.

Kết quả mong đợi: không trả `address` và `phone_number` chỉ vì server đang lưu các giá trị đó; có thể trả `email` với `email_verified: false` nếu policy cho phép. Các trường `profile` cũng không bắt buộc phải có đầy đủ.

### 9.3. Claims Parameter khi cần chính xác hơn

OIDC Core còn có authorization request parameter `claims` để RP yêu cầu claim cụ thể tại `userinfo` và/hoặc `id_token`:

~~~json
{
  "userinfo": {
    "given_name": null,
    "email": {"essential": true}
  },
  "id_token": {
    "auth_time": {"essential": true}
  }
}
~~~

Đây là **nội dung JSON** của `claims` parameter (khi đưa vào authorization URL phải URL-encode đúng). Nó không tự cấp thêm quyền. `essential: true` diễn đạt mức độ quan trọng của claim đối với RP; OP vẫn phải thực thi quyền, consent và policy, và nếu không đáp ứng được thì xử lý theo protocol/profile phù hợp.

Ví dụ RP muốn `given_name` và `email` có thể dùng `openid profile email` kết hợp `claims` nếu OP hỗ trợ. Trước khi dựa vào feature này, hãy kiểm tra metadata `claims_parameter_supported` và hành vi thực tế của SAS/version đang triển khai. **Đừng giả định mọi phiên bản SAS hỗ trợ Claims Parameter đầy đủ chỉ vì có OIDC.**

## 10. Ví dụ end-to-end: client xin profile/email, không xin address/phone

### 10.1. Authorization request

Client đăng ký Authorization Code + PKCE, consent được cấu hình theo policy. Browser đến:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20email&state=OPAQUE_TRANSACTION_STATE&code_challenge=PKCE_S256_CHALLENGE&code_challenge_method=S256&nonce=OIDC_NONCE HTTP/1.1
Host: auth.example.com
~~~

Các giá trị `OPAQUE_TRANSACTION_STATE`, `PKCE_S256_CHALLENGE` và `OIDC_NONCE` là placeholder được thay bằng giá trị sinh ngẫu nhiên/PKCE hợp lệ trong request thực tế.

Sau login/consent, server redirect về `redirect_uri` đã đăng ký với authorization code và state. Client kiểm tra state, rồi đổi code ở token endpoint bằng verifier:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=ORIGINAL_PKCE_VERIFIER
~~~

### 10.2. Token response và scope được cấp

Response minh họa:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email",
  "id_token": "SIGNED_ID_TOKEN_VALUE"
}
~~~

Scope được cấp là `openid profile email`, không có `address` hay `phone`. Nếu `scope` trong token response vắng mặt, client phải áp dụng các quy tắc OAuth liên quan để hiểu scope được cấp; không được tự nghĩ rằng scope mới đã được bổ sung.

ID Token có `sub` cùng các authentication claims bắt buộc; không nhất thiết có email, name hoặc các nhóm PII khác.

### 10.3. UserInfo response

Client gọi:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Một response hợp lệ có thể là:

~~~json
{
  "sub": "user-7c92",
  "name": "Nguyễn An",
  "given_name": "An",
  "family_name": "Nguyễn",
  "locale": "vi-VN",
  "email": "an@example.com",
  "email_verified": true
}
~~~

Không có `address` hay `phone_number`. Việc OP tình cờ có dữ liệu giao hàng hoặc số điện thoại **không cho phép** đưa chúng vào response khi scope tương ứng chưa được cấp, trừ khi có một quyền và consent khác được chuẩn hóa rõ.

### 10.4. Khi client đề nghị nhưng scope không được cấp

Nếu client gửi `openid profile email phone` nhưng policy chỉ cấp `openid profile email`, token/UserInfo chỉ được dùng scope hiệu lực. OP có thể từ chối authorization request sai chính sách hoặc cấp tập con theo quy tắc grant và user consent; RP phải đọc đúng kết quả, không dựa vào requested scope cũ để giả định đã được cấp `phone`.

## 11. Cấu hình RegisteredClient và consent trong Spring Authorization Server

### 11.1. Cho phép đúng các OIDC scopes

Ví dụ SAS 1.5.x với confidential web client:

~~~java
@Bean
RegisteredClient portalRegisteredClient(PasswordEncoder passwordEncoder,
                                        ClientSecrets secrets) {
    return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("portal-web")
            .clientSecret(passwordEncoder.encode(secrets.portalClientSecret()))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                    AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.com/login/oauth2/code/portal")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope(OidcScopes.EMAIL)
            .scope(OidcScopes.ADDRESS)
            .scope(OidcScopes.PHONE)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .build();
}
~~~

`ClientSecrets` là interface/service ứng dụng tự xây để lấy secret từ secret manager; code tập trung vào RegisteredClient builder, chưa có imports/beans repository để thành dự án chạy độc lập.

**Điểm cần nhớ:**
- Đăng ký `scope(OidcScopes.EMAIL)` chỉ có nghĩa client **được phép xin scope email**.
- `requireAuthorizationConsent(true)` yêu cầu bước consent theo SAS, nhưng giao diện/policy consent vẫn phải bảo đảm thông tin người dùng rõ ràng.
- Đăng ký `address` và `phone` cho mọi client không phải lựa chọn tốt mặc định; sản phẩm thật nên chỉ cho phép client có mục đích được phê duyệt.
- `requireProofKey(true)` là bảo vệ Authorization Code Flow bằng PKCE, không thay thế consent hay PII policy.

### 11.2. Kích hoạt OIDC UserInfo Endpoint

Trong SAS 1.5.x, OpenID Connect bị tắt theo cấu hình mặc định; cần bật `oidc(...)` và có đủ Authorization Server infrastructure, signing keys, issuer, client repository, user login.

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        Function<OidcUserInfoAuthenticationContext, OidcUserInfo> mapper)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .userInfoEndpoint(userInfo -> userInfo
                    .userInfoMapper(mapper)
                )
            )
        )
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .exceptionHandling(ex -> ex.authenticationEntryPoint(
                new LoginUrlAuthenticationEntryPoint("/login")));

    return http.build();
}
~~~

`OidcUserInfoEndpointConfigurer.userInfoMapper(...)` là extension point của SAS để cung cấp claims UserInfo từ authorization đã xác thực. Cấu hình trên là phần tập trung vào OIDC/UserInfo; ứng dụng thật vẫn cần các bean `RegisteredClientRepository`, `OAuth2AuthorizationService`, `JWKSource<SecurityContext>`, `JwtDecoder`, user login chain và các cấu hình khác.

**Không bảo vệ UserInfo bằng cơ chế “chỉ cần login session”.** UserInfo Endpoint nhận **access token**; mặc định provider/filter của framework phải xác thực token và authorization trước khi mapper trả claims. Custom mapper chỉ được biến đổi dữ liệu đã được xác thực, không tự bỏ qua bước token validation hoặc kiểm tra scope.

### 11.3. Nguồn dữ liệu và thời điểm lấy

Một OP thực tế có thể đọc claims từ:
- Kho hồ sơ người dùng nội bộ, đã có identity mapping ổn định.
- Hệ thống xác minh email/điện thoại.
- Kho địa chỉ có consent và nguồn dữ liệu rõ.
- User attributes được lấy từ federation, nhưng phải biết độ tin cậy và timestamp.

Không đưa mật khẩu, OTP, secret, private key, access token hoặc nội dung session vào UserInfo. Các trường `email_verified`/`phone_number_verified` chỉ lấy từ quy trình xác minh có bằng chứng. Nếu dữ liệu còn thiếu hoặc đã bị rút quyền chia sẻ, bỏ claim theo policy; không fallback sang thông tin của người dùng khác.

## 12. Xây dựng UserInfo mapper có lọc claims theo scope trong Java

### 12.1. Mô hình dữ liệu và policy

Ví dụ này dùng Java 17+ và API minh họa theo SAS **1.5.x**. Các interface `ProfileRepository`, `DisclosurePolicy` và cơ chế kiểm tra dữ liệu là thành phần ứng dụng tự triển khai. Mục tiêu là tránh cả hai lỗi: **lấy danh sách scope đã đăng ký thay scope đã cấp** và **trả toàn bộ hồ sơ bất kể consent/policy**.

~~~java
record ProfileSnapshot(
        String name,
        String givenName,
        String familyName,
        String preferredUsername,
        String locale,
        String email,
        Boolean emailVerified,
        Map<String, ?> address,
        String phoneNumber,
        Boolean phoneNumberVerified) {
}

interface ProfileRepository {
    ProfileSnapshot loadByInternalPrincipal(String principalName);
}

@FunctionalInterface
interface DisclosurePolicy {
    boolean allows(String clientId, String claimName);
}
~~~

Một hệ thống production sẽ còn tenant, consent version, thời điểm dữ liệu xác minh và chính sách truy cập riêng; record trên cố ý giữ đơn giản. Lớp profile repository cần đọc dữ liệu người dùng đúng principal nội bộ và không dùng email như một định danh duy nhất.

### 12.2. Helper chỉ cho phép standard claims đã được cấp scope

~~~java
private static void putString(
        Map<String, Object> target,
        String claim,
        String value,
        String clientId,
        DisclosurePolicy policy) {

    if (value != null && !value.isBlank() && policy.allows(clientId, claim)) {
        target.put(claim, value);
    }
}

static Map<String, Object> buildUserInfoClaims(
        String idTokenSubject,
        Set<String> authorizedScopes,
        String clientId,
        ProfileSnapshot data,
        DisclosurePolicy policy) {

    Map<String, Object> result = new LinkedHashMap<>();

    // Luôn dùng cùng subject mà OP đã phát hành trong ID Token.
    result.put("sub", idTokenSubject);

    if (authorizedScopes.contains(OidcScopes.PROFILE)) {
        putString(result, "name", data.name(), clientId, policy);
        putString(result, "given_name", data.givenName(), clientId, policy);
        putString(result, "family_name", data.familyName(), clientId, policy);
        putString(result, "preferred_username",
                data.preferredUsername(), clientId, policy);
        putString(result, "locale", data.locale(), clientId, policy);
    }

    if (authorizedScopes.contains(OidcScopes.EMAIL)) {
        putString(result, "email", data.email(), clientId, policy);
        if (result.containsKey("email")
                && data.emailVerified() != null
                && policy.allows(clientId, "email_verified")) {
            result.put("email_verified", data.emailVerified());
        }
    }

    if (authorizedScopes.contains(OidcScopes.PHONE)) {
        putString(result, "phone_number", data.phoneNumber(),
                clientId, policy);
        if (result.containsKey("phone_number")
                && data.phoneNumberVerified() != null
                && policy.allows(clientId, "phone_number_verified")) {
            result.put("phone_number_verified", data.phoneNumberVerified());
        }
    }

    if (authorizedScopes.contains(OidcScopes.ADDRESS)
            && data.address() != null
            && policy.allows(clientId, "address")) {
        Set<String> allowedKeys = Set.of(
                "formatted", "street_address", "locality",
                "region", "postal_code", "country");
        Map<String, Object> address = new LinkedHashMap<>();
        for (String key : allowedKeys) {
            Object value = data.address().get(key);
            if (value instanceof String s && !s.isBlank()) {
                address.put(key, s);
            }
        }
        if (!address.isEmpty()) {
            result.put("address", address);
        }
    }

    return result;
}
~~~

Helper này chỉ minh họa nhóm claims phổ biến. Nếu ứng dụng thực sự cung cấp đầy đủ `profile` thì bổ sung các trường `middle_name`, `nickname`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo` và `updated_at` với validation dữ liệu tương ứng. Không được suy rằng thiếu trường trong code mẫu nghĩa là OIDC Core không có trường đó.

**Tại sao `sub` lấy từ ID Token thay vì `principalName`?** Ở OP có pairwise subject identifiers hoặc federation, `sub` mà RP thấy có thể không giống username nội bộ. UserInfo phải trả **cùng OIDC subject** mà ID Token đã phát hành cho RP. Hàm này chỉ nhận `idTokenSubject` từ nguồn đã được OP phát hành, không để HTTP caller chọn.

### 12.3. Mapper truy cập authorization và access token đã xác thực

Một cách nối helper vào SAS UserInfo endpoint:

~~~java
@Bean
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
        ProfileRepository profiles,
        DisclosurePolicy policy) {

    return context -> {
        OAuth2Authorization authorization = context.getAuthorization();

        var idTokenHolder = authorization.getToken(OidcIdToken.class);
        if (idTokenHolder == null) {
            throw new IllegalStateException("OIDC ID Token is missing");
        }

        String subject = idTokenHolder.getToken().getSubject();
        Set<String> scopes =
                authorization.getAccessToken().getToken().getScopes();

        ProfileSnapshot data =
                profiles.loadByInternalPrincipal(
                        authorization.getPrincipalName());

        Map<String, Object> released = buildUserInfoClaims(
                subject,
                scopes,
                context.getRegisteredClient().getClientId(),
                data,
                policy
        );

        return new OidcUserInfo(released);
    };
}
~~~

Những điểm cần kiểm tra khi đưa vào hệ thống thực:
- `OidcUserInfoAuthenticationContext` đến từ **UserInfo authentication flow**, sau khi provider xác minh access token; mapper không được biến thành endpoint công khai không cần token.
- `authorization.getAccessToken()` biểu diễn access token trong authorization đã tra cứu. Trong custom token persistence hoặc nhiều token cùng authorization, phải chắc chắn tập scope dùng để lọc chính là tập scope của **token đã xác thực trong request**, không phải tập scope tối đa của authorization lịch sử.
- `OidcIdToken` dùng để lấy `sub` của cùng OIDC authorization; nếu không tồn tại hoặc subject không hợp lệ thì xử lý lỗi an toàn, không trả UserInfo cho một principal đoán được.
- `ProfileRepository`, `DisclosurePolicy` không phải class có sẵn của Spring Security. Chúng là contract của ứng dụng cần bảo vệ theo tenant/client/user.
- Khi UserInfo của một subject chưa có dữ liệu, vẫn phải trả `sub` chính xác nếu request hợp lệ; các claims tùy chọn có thể vắng theo policy.
- Không trả `email_verified=true`/`phone_number_verified=true` nếu không có bằng chứng xác minh.

Một mapper trả thẳng `new OidcUserInfo(idToken.getClaims())` có thể là cách demo ban đầu trong một số tài liệu, nhưng cần rà soát **những claims đã có trong ID Token**, phạm vi token hiện tại và mục tiêu data-minimization. Với hệ thống thật, không nên coi mọi ID Token claim đều mặc nhiên được cấp cho mọi caller UserInfo.

### 12.4. Test trực tiếp helper

~~~java
@Test
void releaseOnlyGrantedAndAllowedClaims() {
    ProfileSnapshot profile = new ProfileSnapshot(
            "Nguyễn An", "An", "Nguyễn", "an.nguyen", "vi-VN",
            "an@example.com", true,
            Map.of("locality", "Hà Nội", "country", "Việt Nam"),
            "+84901234567", false
    );

    DisclosurePolicy allowAll = (clientId, claim) -> true;

    Map<String, Object> claims = buildUserInfoClaims(
            "pairwise-sub-123",
            Set.of(OidcScopes.OPENID, OidcScopes.PROFILE, OidcScopes.EMAIL),
            "portal-web",
            profile,
            allowAll
    );

    assertEquals("pairwise-sub-123", claims.get("sub"));
    assertEquals("Nguyễn An", claims.get("name"));
    assertEquals("an@example.com", claims.get("email"));
    assertEquals(true, claims.get("email_verified"));

    assertFalse(claims.containsKey("address"));
    assertFalse(claims.containsKey("phone_number"));
}
~~~

Dù user profile chứa địa chỉ và số điện thoại, helper không tiết lộ chúng nếu scope tương ứng không được cấp.

## 13. Khi nào nên đưa claims vào ID Token?

Trong nhiều OP, RP cần lập session hoặc hiển thị tên sau login, nhưng không phải lúc nào cũng cần gọi UserInfo. OIDC cho phép bổ sung một số user claims vào ID Token, song phải kiểm soát rủi ro **phát hành PII lâu sống, bị log, được copy và khó thu hồi khỏi client**.

### 13.1. Khác biệt giữa claims của ID Token và UserInfo

| Tiêu chí | ID Token | UserInfo |
| --- | --- | --- |
| Cách nhận | Token response hoặc authorization response theo flow | Gọi endpoint với access token |
| Audience chính | OIDC Relying Party | RP đang được cho phép dùng token |
| Chức năng lõi | Authentication assertions, `iss`, `sub`, `aud`, `exp`... | User claims như name, email, address, phone |
| Khả năng cập nhật dữ liệu | Claims là snapshot tại thời điểm phát hành | Có thể đọc dữ liệu mới theo chính sách/cache |
| Rủi ro khi lộ | Token chứa PII đã phát hành có thể tiếp tục lưu ở RP | Gọi endpoint theo access token, policy, thời hạn |
| Trường `sub` | Bắt buộc | Bắt buộc, phải trùng `sub` ID Token |

Khuyến nghị: ID Token giữ tối thiểu những gì RP cần xác minh authentication, còn UserInfo trả thông tin có thể thay đổi và nhạy cảm. Nếu một use case thật sự cần email claim trong ID Token, cần kiểm tra scope đã cấp, consent, client policy, verification source và lifetime/logging.

### 13.2. JWT token customizer trong SAS là extension point khác

Khi dùng JWT ID Token, `OAuth2TokenCustomizer<JwtEncodingContext>` có thể tùy chỉnh claims. Một thiết kế cẩn trọng:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer(
        ProfileRepository profiles,
        DisclosurePolicy policy) {

    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        // Giữ ID Token tối thiểu. Chỉ ví dụ release email cho
        // đúng client và scope đã được cấp nếu use case thực sự cần.
        Set<String> grantedScopes = context.getAuthorizedScopes();
        String clientId = context.getRegisteredClient().getClientId();

        if (grantedScopes.contains(OidcScopes.EMAIL)
                && policy.allows(clientId, "id_token.email")) {
            ProfileSnapshot profile = profiles.loadByInternalPrincipal(
                    context.getPrincipal().getName());
            if (profile.email() != null && !profile.email().isBlank()) {
                context.getClaims().claim("email", profile.email());
                if (profile.emailVerified() != null) {
                    context.getClaims().claim(
                            "email_verified", profile.emailVerified());
                }
            }
        }
    };
}
~~~

Ví dụ là **policy lựa chọn** chứ không phải yêu cầu của OIDC phải nhét email vào ID Token. Khi áp dụng:
- Đừng ghi đè `iss`, `sub`, `aud`, `exp` hoặc các security claims do framework quản lý.
- Chỉ dùng `context.getPrincipal().getName()` để tra hồ sơ nội bộ nếu ứng dụng đã có mapping đúng principal.
- `getAuthorizedScopes()` phải phản ánh grant hợp lệ tại thời điểm token phát hành.
- Đối chiếu version SAS: các class/provider/customizer DSL có thể chuyển package hoặc thay đổi trong Spring Security 7.x.
- Không dùng access token JWT customizer để vô tình đưa email, address, phone vào mọi access token của tất cả API.

### 13.3. Tránh trùng lặp và dữ liệu lỗi thời

Nếu ID Token đã chứa `email` tại thời điểm đăng nhập nhưng UserInfo sau đó trả địa chỉ email khác do người dùng vừa cập nhật, RP cần định nghĩa nguồn dữ liệu ưu tiên và xử lý thay đổi an toàn. Không tự quyết định rằng email cũ là danh tính gốc; **`sub` mới là định danh RP dùng cho account linking**.

## 14. Relying Party xử lý claims an toàn trong Spring Security

### 14.1. Đọc OIDC claims từ OidcUser

Sau OIDC login, Spring Security có thể đặt `OidcUser` làm principal. Dữ liệu UserInfo không phải lúc nào cũng tồn tại, nên code RP cần xử lý null và xác minh identity:

~~~java
@GetMapping("/account/summary")
Map<String, Object> accountSummary(@AuthenticationPrincipal OidcUser user) {
    // Spring Security OIDC login đã chạy bước xác minh token theo config.
    String subject = user.getSubject();
    String issuer = user.getIssuer().toString();

    OidcUserInfo userInfo = user.getUserInfo(); // Có thể null.
    String email = userInfo == null ? null : userInfo.getEmail();
    Boolean verified = userInfo == null
            ? null : userInfo.getEmailVerified();

    return Map.of(
            "identity", issuer + "|" + subject,
            "hasEmail", email != null,
            "emailVerified", Boolean.TRUE.equals(verified)
    );
}
~~~

Đoạn code trên chỉ trả trạng thái, không phản chiếu email nhạy cảm ra API không cần thiết. `@AuthenticationPrincipal` có thể là null với request chưa đăng nhập; controller phải được bảo vệ bởi Spring Security. Trong ứng dụng thực, hãy dùng kiểu dữ liệu định danh có hai field `issuer` và `subject` riêng thay vì nối thành chuỗi nếu có nguy cơ delimiter collision.

**Đừng bỏ qua null của UserInfo:** một RP có thể đăng nhập bằng ID Token mà không gọi UserInfo (ví dụ provider không công bố endpoint hoặc client không yêu cầu dữ liệu). RP không nên lỗi 500 chỉ vì thiếu `email`, `address` hoặc `phone_number`.

### 14.2. OidcUser chứa claims đã hợp nhất nhưng không thay validation

`OidcUser.getClaims()` là cách Spring Security biểu diễn các OIDC claims liên quan, có thể gồm claims từ ID Token và UserInfo. Nếu ứng dụng cần biết một claim đến từ đâu, hãy đọc rõ `getIdToken()` và `getUserInfo()` thay vì cho rằng `getClaims()` luôn có nguồn hoặc độ mới giống nhau.

Với email:
- Nếu có `email_verified=true`, RP có thể dùng kết quả theo mức độ tin cậy OP và chính sách đã thống nhất.
- Nếu false/missing, ứng dụng có thể yêu cầu xác minh độc lập trước một nghiệp vụ nhạy cảm.
- Không tự động gán roles dựa trên domain email nếu không có trust agreement và kiểm tra account lifecycle.

### 14.3. Không dùng claim cá nhân làm resource authorization

Một API đơn hàng không nên nhận yêu cầu chỉ vì `email` trong UserInfo trùng email ghi trên đơn. Authorization phải dựa trên token nhận dạng đúng resource audience, scopes/authorities và chính sách truy cập của hệ thống. Identity từ `(iss, sub)` chỉ là đầu vào xác định account.

## 15. Quy tắc bảo mật, privacy và vận hành

### 15.1. Data minimization và consent

Dữ liệu hồ sơ OIDC có thể là PII. Nên xác định cho từng client:
- Mục đích sử dụng từng claim, không chỉ từng scope.
- Cơ sở pháp lý/consent theo yêu cầu của tổ chức và nơi vận hành.
- Dữ liệu nào cần ở ID Token, dữ liệu nào chỉ nên cấp qua UserInfo.
- Có cần hiển thị claim-level disclosure trong màn hình consent hay không.
- Khi nào consent hết hiệu lực, cần xin lại hoặc ngừng trả một claim.
- Thời gian lưu/cache dữ liệu ở RP và quyền xóa/sửa.

**Scope consent không phải lời hứa rằng OP sẽ trả tất cả claims.** Có thể hiển thị “Ứng dụng có thể truy cập email của bạn” thay vì “Ứng dụng chắc chắn nhận được email đã xác minh”. Nếu UI chỉ nói “Thông tin hồ sơ” mà thực tế tiết lộ ngày sinh/giới tính, nên thiết kế UI chi tiết hơn.

### 15.2. Độ mới của dữ liệu và verification state

`updated_at` của profile không tự nói lúc nào email/phone được xác minh. Nếu cần đánh giá tuổi của bằng chứng xác minh, hệ thống có thể có metadata nội bộ, ví dụ `email_verified_at`, nhưng đó **không phải standard claim** thuộc `email` scope trong OIDC Core. Không tự quảng cáo claim riêng là standard.

Nếu user đổi email:
1. Tùy policy, đánh dấu email mới chưa xác minh.
2. Chạy verification workflow.
3. Cập nhật claim `email_verified` theo trạng thái thực.
4. Không để session/token cũ tự động thay đổi dữ liệu đã ký trong ID Token.
5. RP có thể fetch lại UserInfo hoặc yêu cầu xác minh lại tùy use case.

### 15.3. Tránh lộ claims trong log, token và telemetry

Không ghi full UserInfo response hoặc toàn bộ ID Token vào log ứng dụng production. Các rủi ro gồm:
- Email/số điện thoại hiển thị trong APM traces.
- Địa chỉ đầy đủ được lưu trong API gateway access log.
- ID Token chứa PII bị dán vào ticket hoặc crash dump.
- Browser analytics thu thập response payload.
- Debug endpoint phản chiếu mọi claim.

Nên dùng correlation ID, `client_id`, `issuer` và mã lý do từ chối được chuẩn hóa; nếu cần debug profile, mask email/phone và kiểm soát quyền log. Không đưa private signing keys hoặc secrets vào UserInfo.

### 15.4. Không sử dụng Resource Server access token như UserInfo profile token

Resource Server thường cần scopes kiểu `orders.read`, `orders.write` hoặc resource-specific claims, trong khi UserInfo trả dữ liệu của end-user cho RP. Trộn hai mục đích có thể làm một API không liên quan nhận PII. Hãy cấu hình audience, scope và token handling cho đúng từng loại consumer.

Trong OIDC UserInfo, access token phải đại diện authorization phù hợp, do OP phát hành và được UserInfo endpoint xác thực; không để bất kỳ token có chữ ký đúng nhưng audience hoặc issuer không hợp lệ đều được đọc hồ sơ.

### 15.5. UserInfo lấy dữ liệu mới, nhưng không cấp thêm quyền

UserInfo có thể đọc hồ sơ mới nhất, nhưng phải luôn giới hạn claims bởi scope/consent của access token đang dùng. Ví dụ, người dùng thêm số điện thoại sau thời điểm cấp token `openid email`, UserInfo không được trả `phone_number` chỉ vì hồ sơ giờ đã có số đó.

Khi người dùng thu hồi consent, cần chính sách rõ ràng về token revocation và trạng thái authorization; không để cache UserInfo trả claims đã bị rút quyền trong thời gian dài.

### 15.6. Tenant isolation và subject identifier

Ở hệ thống multi-tenant hoặc OP có pairwise subject:
- Cặp `(iss, sub)` xác định identity trong trust domain.
- `sub` có thể khác giữa hai RP tùy pairwise subject sector policy.
- Không lấy username hoặc email làm `sub` cho mọi client nếu profile yêu cầu pairwise.
- UserInfo mapper phải lấy đúng subject của authorization/ID Token đang dùng, không tự dùng principal nội bộ khi nó khác.
- User repository, consent, scope policy và response cache phải cách ly theo tenant/client/subject.
- Hai user có cùng `email` ở hai issuer không mặc nhiên là cùng account.

### 15.7. Lỗi Authorization Server và UserInfo

Những tình huống cần xử lý tách biệt:
- Access token thiếu/không hợp lệ: HTTP `401` và OAuth bearer challenge/error phù hợp; **không** trả UserInfo với `sub` giả.
- Token hợp lệ nhưng thiếu quyền đọc UserInfo theo policy: từ chối theo cơ chế phù hợp, không nâng scope hoặc trả claim nhạy cảm.
- Claim tùy chọn không tồn tại: thường **bỏ claim**, không nhất thiết coi toàn bộ UserInfo request là lỗi.
- Data source tạm thời không hoạt động: chính sách fail-closed cho claims nhạy cảm hoặc trả lỗi có kiểm soát; không lấy cache user khác.
- Subject từ UserInfo khác ID Token: RP phải bỏ response dù các trường khác trông hợp lệ.

## 16. Ma trận kiểm thử scope-to-claims

### 16.1. Unit tests cho policy mapper

| Test case | Authorized scopes / dữ liệu | Kết quả cần đạt |
| --- | --- | --- |
| `openid` only | User có full profile | Chỉ `sub`; không profile/email/address/phone |
| `openid profile` | Có name, locale, picture | Trả claims profile được phép, không email |
| `openid email` | Email đã xác minh | Trả `email`, `email_verified: true` |
| `openid email` | Email chưa xác minh | `email_verified: false`, không tự đổi thành true |
| `openid email` | Email không tồn tại | Bỏ `email`, không sinh email giả |
| `openid address` | Có address object | Trả `address` object đúng schema |
| `openid address` | Address không có dữ liệu | Bỏ `address`, không trả null hay object rỗng tùy policy |
| `openid phone` | Có số E.164 và trạng thái chưa xác minh | `phone_number`, `phone_number_verified: false` |
| `openid phone` | Không có số | Bỏ phone claims |
| `openid profile email` | Data có address và phone | Không tiết lộ `address`/`phone_number` |
| Requested ≠ granted | Client xin phone, AS không cấp phone | Không trả `phone_number` |
| Registered ≠ granted | Client được đăng ký address, token không có address | Không trả `address` |
| Consent thu hồi | Token/authorization đã thu hồi hoặc policy cấm | Không tiết lộ claims sau khi policy có hiệu lực |
| Client policy cấm | Granted `email` nhưng client bị cấm đọc email | Không trả `email` |
| Pairwise subject | Internal username khác ID Token `sub` | UserInfo `sub` đúng ID Token subject |
| Data typo | `email_verified="true"` dạng string | Không trả sai kiểu; bắt lỗi dữ liệu |
| Tenant A/B | Hai subject trùng username | Không trộn hồ sơ/claims |
| Scope mở rộng | `orders.read` không có email | Không suy ra email |
| Thiếu `openid` | OAuth request chỉ có `profile` | Không biến thành OIDC login/ID Token |
| JSON schema | `address` bị map thành string | Bị phát hiện, sửa thành object |

### 16.2. Integration tests Authorization Code + UserInfo

| Bước | Kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Registration | Client chỉ có `openid profile` | Không thể xin `email` khi không được đăng ký |
| Authorization | Người dùng không đồng ý `phone` | Không cấp phone scope |
| Token response | Check `scope` được cấp | Phản ánh grant theo protocol |
| ID Token | Check `iss`, `sub`, `aud`, `exp` | Đúng OIDC, không chứa PII không có policy |
| UserInfo | GET với token `openid profile email` | Trả `sub`, profile/email được phép |
| UserInfo | GET với token `openid` only | Không trả email/phone/address |
| UserInfo | Gọi bằng ID Token | Từ chối; không thay access token |
| UserInfo | Gọi bằng expired/revoked token | Từ chối |
| UserInfo | Access token khác user | Không trả hồ sơ của user ban đầu |
| UserInfo | RP nhận UserInfo `sub` khác ID Token | RP từ chối |
| Data update | Email thay đổi sau login | UserInfo mới xử lý theo profile policy |
| Concurrent sessions | Hai tab dùng token khác scope | Mỗi request chỉ thấy claims của token tương ứng |
| Claims Parameter | Client yêu cầu essential email nhưng không được cấp | Không bypass consent; xử lý theo profile |
| OAuth-only | Token không thuộc OIDC authorization | Không cho phép truy cập UserInfo như OIDC token |
| Multi-node | Dữ liệu và consent nhất quán | Không rò rỉ scopes hoặc cache user |
| Multi-tenant | Cùng `sub` string ở issuer khác | Không trộn claims |
| Privacy | Ghi HTTP/access logs và APM | Không lộ full UserInfo hay raw token |

### 16.3. Kiểm thử kiểu dữ liệu bắt buộc

~~~json
{
  "sub": "subject-from-id-token",
  "email": "user@example.com",
  "email_verified": false,
  "phone_number": "+84901234567",
  "phone_number_verified": true,
  "address": {
    "formatted": "Example address",
    "country": "Việt Nam"
  },
  "updated_at": 1794800000
}
~~~

Kiểm tra:
- `email_verified` và `phone_number_verified` là JSON **booleans**, không phải strings `"true"`/`"false"`.
- `address` là JSON **object**, không phải một text string hoặc list.
- `updated_at` là NumericDate, không phải formatted date string.
- `phone_number` là string (có thể chứa dấu `+`), không ép sang số nguyên làm mất `+` và số 0.
- `email`, `name`, `given_name` là strings; giá trị vắng mặt được xử lý theo policy.
- `sub` là string, ổn định đúng subject identifier của OP.

## 17. Lỗi tích hợp thường gặp

### 17.1. Tưởng rằng RegisteredClient.scope(...) chính là granted scope

**Sai:**

~~~java
if (registeredClient.getScopes().contains("phone")) {
    userInfo.put("phone_number", profile.phoneNumber());
}
~~~

Client được đăng ký scope `phone` nhưng token hiện tại có thể không được cấp scope đó. Dùng **effective authorized scopes** của request/token sau khi xác thực, rồi áp client disclosure policy.

### 17.2. Giả định scope email đồng nghĩa email_verified=true

Không gán `email_verified=true` khi dữ liệu email chưa có verification record. RP cũng không nên dùng `email_verified` làm chứng cứ đủ mạnh để liên kết tài khoản tự động giữa nhiều issuer.

### 17.3. Trả address dưới dạng string

**Sai:**

~~~json
{"address": "12 Đường Hoa Sen, TP. Hồ Chí Minh"}
~~~

**Đúng kiểu dữ liệu:**

~~~json
{
  "address": {
    "formatted": "12 Đường Hoa Sen, TP. Hồ Chí Minh"
  }
}
~~~

Nếu API nội bộ đang lưu địa chỉ dạng string, cần adapter để biểu diễn thành object theo OIDC, không công bố `address` standard claim sai schema.

### 17.4. Tạo phone_number như number

**Sai:**

~~~json
{"phone_number": 84901234567}
~~~

**Đúng:**

~~~json
{"phone_number": "+84901234567"}
~~~

Số điện thoại là text, có dấu `+` và số 0 đầu; chuyển sang integer có thể mất thông tin.

### 17.5. Dùng UserInfo sub khác ID Token sub

Nếu `UserInfo.sub` là username nội bộ nhưng ID Token `sub` là pairwise subject ID, RP phải từ chối response. Mapper phải lấy đúng subject identifier đã phát hành cho cùng client/authorization, không sửa `sub` theo profile repository tùy ý.

### 17.6. Dùng ID Token để gọi UserInfo

ID Token được phát hành cho RP chứng minh authentication. Nó không phải OAuth access token và không được thay thế header `Authorization: Bearer ...` tại UserInfo.

### 17.7. Lộ PII trong access token JWT

Khi resource server hoặc nhiều downstream service nhận cùng access token, việc nhét `address` và `phone_number` vào token sẽ khiến tất cả các bên có thể đọc dữ liệu đó. Hãy hạn chế token claims theo audience và scope; sử dụng UserInfo cho OIDC user claims khi phù hợp.

### 17.8. Chỉ dùng scope mà quên tenant/client policy

Hai client có cùng `openid email` không nhất thiết được nhận cùng dữ liệu. Policy có thể yêu cầu client thuộc trust tier nhất định, user consent hợp lệ hoặc mục đích sử dụng đã đăng ký. Đừng để `context.getRegisteredClient().getScopes()` thành “quyền vô điều kiện đọc mọi hồ sơ”.

### 17.9. Trộn claims từ hai identity providers

Một user đã kết nối tài khoản Google và một OP doanh nghiệp có thể có cùng email nhưng khác issuer/subject. Khi RP hiển thị thông tin, phải xác định rõ nguồn dữ liệu và **không** tự ghép hai subject vì email trùng.

### 17.10. Phát hành claim profile dù chỉ có scope openid

`openid` chỉ kích hoạt OIDC authentication; không mặc nhiên cho phép tiết lộ `birthdate`, `gender`, `picture` hay `email`. Nếu OP có cơ chế consent/claims request bổ sung, phải thực thi explicit policy đó.

## 18. Bài tập tình huống: cổng đặt lịch và hệ thống giao hàng

Giả sử OP nội bộ dùng Spring Authorization Server có hai Relying Parties:

| Khía cạnh | Portal lịch hẹn | Delivery App |
| --- | --- | --- |
| Client ID | `portal-web` | `delivery-mobile` |
| Registered scopes | `openid profile email` | `openid profile email address phone` |
| Requested scopes | `openid profile email` | `openid profile email address phone` |
| User consent | `openid profile email` | Người dùng chỉ chấp thuận `openid profile phone` |
| Dữ liệu có sẵn | Name, email, address, phone | Cùng một người dùng |
| Verification | Email đã verified; phone chưa verified | Cùng nguồn dữ liệu |

OP lưu snapshot:

~~~json
{
  "internal_user_id": "u-839",
  "public_subject": "pairwise-sub-for-client",
  "name": "Nguyễn An",
  "email": "an@example.com",
  "email_verified": true,
  "phone_number": "+84901234567",
  "phone_number_verified": false,
  "address": {
    "formatted": "12 Đường Hoa Sen, TP. Hồ Chí Minh",
    "country": "Việt Nam"
  }
}
~~~

Hãy trả lời:

1. Portal lịch hẹn có được thấy `phone_number` và `address` không? Vì sao?
2. Delivery App đã được đăng ký `address` và `email` nhưng user không chấp thuận hai scope đó. UserInfo có được trả claims tương ứng không?
3. Delivery App nhận `phone_number_verified=false`. Có nên tự xem số đó là số đủ tin cậy để reset password?
4. Khi OP dùng pairwise `sub`, kết quả UserInfo phải lấy subject từ đâu?
5. Nếu user đổi email sau khi nhận ID Token, RP có thể gặp sự khác biệt nào giữa ID Token và UserInfo?
6. Có thể dùng `email` để tự liên kết subject của Portal và Delivery App không?
7. Ứng dụng Delivery App cần địa chỉ chính xác để giao hàng. Chỉ đọc OIDC `address` đã đủ bảo đảm địa chỉ giao hàng hợp lệ chưa?
8. Đề xuất ít nhất tám test về granted scopes, data availability, verified flags, tenant/client separation và schema types.
9. Nếu không dùng UserInfo, muốn thêm `email` vào ID Token cho Portal thì cần những policy và kiểm tra gì?
10. Trình bày cách dùng `RegisteredClient`, `OidcUserInfoAuthenticationContext` và `OidcIdToken` để tạo response đúng.

**Gợi ý đáp án:** Portal không nhận address/phone nếu chỉ có profile/email; Delivery App chỉ nhận phone (và có thể profile) theo scope đã thực sự cấp. Verification state không được tự đổi thành true. UserInfo `sub` phải trùng ID Token `sub`, không lấy subject nội bộ khác. Email không phải khóa linking tin cậy. Địa chỉ OIDC không mặc nhiên là địa chỉ giao hàng đã được người dùng xác nhận cho giao dịch.

## 19. Checklist triển khai production

1. **Scopes đúng chuẩn:** công bố `openid`, `profile`, `email`, `address`, `phone` chỉ khi có implementation/policy hỗ trợ.
2. **Client registration:** cấp allowed scopes tối thiểu cho từng `RegisteredClient`; không bật address/phone đại trà.
3. **Consent:** user nhìn thấy phạm vi truy cập rõ ràng; nếu cần, cung cấp thông tin cụ thể về những PII sẽ được chia sẻ.
4. **Effective scopes:** quyết định phát hành claims bằng scope của authorization/access token thực tế, không dùng requested/registered scopes làm quyền cuối cùng.
5. **Subject:** `sub` trong UserInfo bằng chính `sub` của ID Token; tách khỏi username, email, tenant ID nội bộ.
6. **Profile mappings:** hỗ trợ đầy đủ schema nếu công bố claim; cho phép thiếu claim tùy chọn, không sinh dữ liệu giả.
7. **Email:** boolean `email_verified` lấy từ verification store, không suy từ việc email tồn tại.
8. **Address:** `address` là object; hạn chế tiết lộ thông tin địa chỉ chi tiết và bảo đảm mục đích sử dụng.
9. **Phone:** lưu số dạng text, ưu tiên E.164; `phone_number_verified` không thay MFA policy.
10. **UserInfo:** bảo vệ bằng access token hợp lệ; kiểm tra issuer/grant/expiry/revocation và scope trước mapper.
11. **ID Token:** chứa authentication claims cần thiết; không biến thành bản sao toàn bộ user database.
12. **Access Token:** chỉ dành cho protected resource, không tự nhúng full OIDC profile; audience/scope được xác minh.
13. **Spring extensions:** dùng `userInfoMapper` và `OAuth2TokenCustomizer` đúng version; không bỏ default OAuth/OIDC validators.
14. **PII policy:** client/tenant/subject separation, allowlist claims, retention, masking và thu hồi consent/token.
15. **Verification/freshness:** có chính sách re-verify email/phone, cập nhật `updated_at` theo nghĩa thực.
16. **Testing:** unit + integration cho từng scope, requested vs granted, missing data, schema, subject mismatch và privacy leakage.
17. **Operations:** metrics lỗi UserInfo/claim mapping không chứa PII; kiểm tra cache và token lifetime khi dữ liệu đổi.

## 20. Tài liệu chuẩn để đối chiếu

- [OpenID Connect Core 1.0 — Final](https://openid.net/specs/openid-connect-core-1_0.html): `5.1 Standard Claims`, `5.3 UserInfo Endpoint`, `5.4 Requesting Claims using Scope Values`, `5.5 Claims Parameter`, subject và ID Token validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `scopes_supported`, `claims_supported` và capability metadata của OP.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): semantics của scope, authorization và token response.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636.html): PKCE trong Authorization Code Flow.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): JWT payload và registered claims, bao gồm NumericDate.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC UserInfo endpoint và `userInfoMapper` customization.
- [Spring Authorization Server 1.5.x — Core Model / RegisteredClient](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): client allowed scopes và ClientSettings consent.
- [Spring Authorization Server — JwtEncodingContext](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/JwtEncodingContext.html): JWT token customizer và authorized scopes.
- [Spring Security — OAuth2 Login / OIDC](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): RP login và OIDC claims.
- [Spring Security — OidcUserInfo](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserInfo.html): mô hình UserInfo claims trong Spring Security.

**Ghi nhớ:** `openid` kích hoạt OIDC, còn `profile`, `email`, `address` và `phone` **yêu cầu** các nhóm standard claims tương ứng, không bảo đảm OP sẽ trả tất cả. Quyết định thực tế cần dựa trên **authorized scopes của access token**, nguồn dữ liệu hiện có, consent và client/tenant privacy policy. UserInfo phải chứa `sub` đúng với ID Token; `email_verified`/`phone_number_verified` là boolean phản ánh trạng thái xác minh thực, `address` là JSON object. Trong SAS, cấu hình RegisteredClient giới hạn scope được phép, còn UserInfo mapper và token customizer là nơi kiểm soát claims được phát hành; không biến ID Token hoặc access token thành nơi phát tán toàn bộ hồ sơ người dùng.
