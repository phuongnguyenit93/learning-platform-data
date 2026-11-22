# 3.10. Thông tin xác thực trong ID Token và thông tin hồ sơ từ UserInfo

## Mục tiêu bài học

Sau bài học, bạn có thể:

- Phân biệt **thông tin xác thực** mà OpenID Connect (OIDC) đưa vào **ID Token** với **thông tin hồ sơ** mà ứng dụng có thể lấy từ **UserInfo Endpoint**.
- Đọc các claim quan trọng của ID Token như `iss`, `sub`, `aud`, `exp`, `iat`, `auth_time`, `nonce`, `acr`, `amr`, `azp` và hiểu điều kiện xuất hiện của chúng.
- Giải thích tại sao việc giải mã payload JWT không đủ để tin ID Token, và những gì OIDC Client phải kiểm tra trước khi tạo phiên đăng nhập.
- Dùng access token đúng cách để gọi UserInfo, so sánh `sub` giữa UserInfo và ID Token, đồng thời xử lý claim thiếu hoặc thay đổi.
- Xác định dữ liệu đến từ ID Token hay UserInfo trong Spring Security, qua `OidcUser`, `OidcIdToken`, `OidcUserInfo` và cơ chế `oauth2Login()`.
- Thiết kế mapping danh tính, chính sách quyền riêng tư và phân quyền ứng dụng một cách an toàn.

## 1. Bối cảnh: hai nguồn thông tin có hai nhiệm vụ khác nhau

Giả sử **Learning Portal** là một ứng dụng Spring Boot cho sinh viên đăng nhập qua **Campus Identity**. Campus Identity là OpenID Provider (OP), còn Learning Portal là Relying Party (RP), tức ứng dụng tin cậy kết quả xác thực do OP phát hành.

Sau khi người dùng đăng nhập bằng OIDC Authorization Code Flow, Learning Portal có thể nhận:

1. **ID Token:** bằng chứng có cấu trúc do OP phát hành **cho chính Client/Relying Party**, cho biết sự kiện xác thực người dùng và định danh chủ thể.
2. **Access Token:** credential cho phép client truy cập tài nguyên phù hợp; trong một số trường hợp được dùng để truy vấn **UserInfo Endpoint**.
3. **UserInfo response:** các claim hồ sơ về người dùng mà OP cho phép trả về, ví dụ tên hiển thị, email, ngôn ngữ, ảnh đại diện.

Không nên coi ba đối tượng này là ba tên gọi của cùng một token hay cùng một JSON.

| Đối tượng | Mục tiêu chính | Ai tiếp nhận? | Câu hỏi nó giúp trả lời |
| --- | --- | --- | --- |
| **ID Token** | Xác thực sự kiện đăng nhập và danh tính End-User theo OIDC | OIDC Client / RP đã được chỉ định bởi `aud` | “OP đã xác thực chủ thể nào, cho client nào, lúc nào và trong ngữ cảnh nào?” |
| **Access Token** | Ủy quyền truy cập tài nguyên | Resource Server hoặc UserInfo Endpoint phù hợp | “Client có quyền gọi endpoint được bảo vệ này không?” |
| **UserInfo response** | Cung cấp các claim hồ sơ của End-User | OIDC Client gọi UserInfo bằng access token | “Tên, email hoặc thông tin hồ sơ mà OP cho phép chia sẻ là gì?” |

**Nguyên tắc quan trọng:** ID Token phục vụ Relying Party để hiểu kết quả xác thực; UserInfo là nguồn claims hồ sơ; Access Token là credential ủy quyền truy cập. Không gửi ID Token để thay thế access token khi gọi API nghiệp vụ.

### 1.1. Luồng tổng quát

```mermaid
sequenceDiagram
    autonumber
    actor U as End-User
    participant C as Learning Portal (OIDC Client)
    participant OP as Campus Identity (OpenID Provider)
    participant UI as UserInfo Endpoint

    U->>C: Bắt đầu đăng nhập
    C-->>U: Redirect sang OP với openid, scope, state, nonce
    U->>OP: Xác thực / consent khi cần
    OP-->>C: Callback có authorization code
    C->>OP: Đổi code tại token endpoint
    OP-->>C: ID Token + Access Token (và token khác nếu được cấp)
    C->>C: Kiểm tra ID Token, liên kết giao dịch với state/nonce
    opt Cần claims hồ sơ; provider hỗ trợ UserInfo
        C->>UI: GET /userinfo, Bearer Access Token
        UI-->>C: Claims chứa sub và các claim được cho phép
        C->>C: So sánh sub của UserInfo với ID Token
    end
    C->>C: Thiết lập principal/phiên đăng nhập
    C-->>U: Giao diện ứng dụng
```

Trong triển khai thực tế, UserInfo Endpoint thường là một endpoint thuộc cùng OP; sơ đồ tách riêng để thấy rõ chức năng. Việc có ID Token không đồng nghĩa luôn phải gọi UserInfo: client chỉ gọi khi cần và khi cấu hình, token, scope cùng provider cho phép.

## 2. ID Token là gì?

Theo OIDC, **ID Token** là token chứa claims về sự kiện xác thực End-User bởi OpenID Provider và có thể chứa các claims khác. Token này thường ở định dạng **JSON Web Token (JWT)**, được ký bằng JWS, hoặc được bảo vệ thêm bằng cơ chế mã hóa JWE khi được cấu hình.

Một ID Token thường có ba phần JWT:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Chuỗi trên minh họa JWT dạng ký (JWS) ba phần. Đọc payload sau khi Base64URL-decode chỉ giúp **quan sát nội dung**; muốn **tin** nội dung, OIDC Client phải xác minh token theo quy tắc giao thức.

Ví dụ **header** được giải mã (các giá trị chỉ để minh họa):

```json
{
  "alg": "RS256",
  "kid": "campus-key-01",
  "typ": "JWT"
}
```

Ví dụ **payload** được giải mã:

```json
{
  "iss": "https://login.example.org",
  "sub": "student-8fa3b7",
  "aud": "learning-portal",
  "exp": 1893456300,
  "iat": 1893456000,
  "auth_time": 1893455900,
  "nonce": "n-7fb32acb",
  "acr": "urn:example:assurance:mfa",
  "amr": ["pwd", "otp"]
}
```

Đây **không phải token hợp lệ** để sử dụng; chữ ký không được cung cấp và giá trị thời gian, khóa cùng chủ thể đều giả định. Không lưu secret, ID Token hoặc các giá trị thực vào tài liệu/log để mô phỏng.

### 2.1. Các claim cốt lõi của ID Token

| Claim | Ý nghĩa | Khi diễn giải cần chú ý |
| --- | --- | --- |
| `iss` (*issuer*) | Định danh OP phát hành ID Token, thường là URL HTTPS | Phải khớp issuer mà Client đã cấu hình và tin cậy |
| `sub` (*subject*) | Định danh End-User do issuer cung cấp | Không mặc định là email, username hay ID dùng chung mọi OP |
| `aud` (*audience*) | Client ID hoặc tập Client ID mà token dành cho | Phải chứa Client ID của ứng dụng hiện tại; có thể là chuỗi hoặc mảng |
| `exp` (*expiration time*) | Mốc thời gian token hết hiệu lực, tính theo Unix time | Client phải từ chối token quá hạn, xét clock skew phù hợp |
| `iat` (*issued at*) | Thời điểm ID Token được phát hành | Không đồng nghĩa thời điểm người dùng nhập mật khẩu hoặc hoàn tất MFA |

Năm claim trên mang vai trò trung tâm trong ID Token OIDC. Những claim tùy chọn bên dưới có thể rất quan trọng trong chính sách xác thực cụ thể.

| Claim | Tình huống sử dụng | Cách hiểu đúng |
| --- | --- | --- |
| `auth_time` | Cần biết thời điểm OP đã xác thực người dùng; đặc biệt khi dùng `max_age` | Thời điểm xác thực, không phải ngày phát hành token |
| `nonce` | Client gửi nonce trong authentication request để liên kết ID Token với giao dịch | Nếu client đã gửi nonce, phải kiểm tra nonce nhận lại khớp giá trị đã lưu |
| `acr` | Yêu cầu/ghi nhận lớp ngữ cảnh hoặc mức bảo đảm xác thực | Ý nghĩa các giá trị thường phụ thuộc chính sách và thỏa thuận với OP |
| `amr` | Ghi nhận phương thức xác thực đã áp dụng | Ví dụ `pwd`, `otp`; không suy diễn “đã MFA” chỉ vì chuỗi trông quen thuộc |
| `azp` (*authorized party*) | Bổ sung nhận diện bên được ủy quyền, đặc biệt khi token có nhiều audience | Cần áp dụng quy tắc kiểm tra `azp` khi hoàn cảnh phát hành yêu cầu |
| `at_hash` | Liên kết ID Token với Access Token trong những response/flow có claim này | Không phải mọi ID Token trong Authorization Code Flow đều có |
| `c_hash` | Liên kết ID Token với authorization code trong những flow/response thích hợp | Không phải claim mặc định của mọi Authorization Code Flow |
| `sid` | Một số OP hỗ trợ quản lý phiên và logout dựa trên session ID | Không đồng nghĩa cookie session của ứng dụng Spring |
| `jti` | Một định danh JWT có thể do nhà cung cấp phát hành | Không phải claim ID Token bắt buộc của OIDC Core |

**`iss` + `sub` thường là cặp định danh để liên kết một tài khoản cục bộ với một danh tính OIDC.** Hai OP khác nhau có thể cùng trả `sub = "123"` cho hai người khác nhau. Một OP cũng có thể cấp *pairwise subject identifier* để cùng một người dùng có các giá trị `sub` khác nhau giữa các nhóm client. Vì thế, không dùng `sub` đơn lẻ làm khóa toàn cục giữa nhiều issuer.

### 2.2. `auth_time` khác `iat` thế nào?

Giả sử người dùng đã đăng nhập SSO lúc 09:00, mở Learning Portal lúc 09:20 và OP cấp ID Token lúc 09:20:

```text
auth_time = 09:00   // lần OP xác thực người dùng
iat       = 09:20   // lúc OP phát hành ID Token cho Learning Portal
```

Nếu Portal yêu cầu xác thực đủ mới để xem một chức năng nhạy cảm, nó có thể gửi tham số OIDC `max_age`. Khi đó cần kiểm tra `auth_time` theo quy tắc OIDC để xác định OP đã xác thực người dùng trong khoảng thời gian cho phép. Việc ID Token vừa được phát hành **không tự bảo đảm** người dùng vừa nhập mật khẩu hoặc làm MFA.

Trong một số trường hợp client yêu cầu `acr_values` hoặc một claim `acr` cụ thể để có mức bảo đảm xác thực phù hợp. Tuy nhiên, client và OP phải thống nhất ý nghĩa của giá trị `acr` cùng cách xử lý khi yêu cầu không được đáp ứng. Không nên mã hóa giả định “mọi giá trị `acr` có từ `mfa` đều có cùng bảo đảm” mà không có hợp đồng tin cậy.

### 2.3. `amr` có phải luôn chứng minh MFA?

`amr` thường là mảng các phương thức xác thực mà OP đã sử dụng, ví dụ:

```json
{
  "amr": ["pwd", "otp"]
}
```

Nó có thể hữu ích cho auditing hoặc điều kiện truy cập theo chính sách, nhưng cách biểu diễn và mức độ bảo đảm phụ thuộc OP. Nếu một nghiệp vụ cần xác thực tăng cường, nên dùng chính sách đã được định nghĩa rõ, gồm issuer đáng tin cậy, `acr` hoặc quy tắc `amr` được thỏa thuận, `auth_time` và thông tin ngữ cảnh khác. Đừng chỉ kiểm tra sự tồn tại của claim `amr`.

### 2.4. Thông tin hồ sơ có thể có trong ID Token không?

**Có thể.** Ngoài các claim xác thực, ID Token có thể mang những claim tiêu chuẩn hoặc claim riêng do OP cấp, chẳng hạn `name` hay `email`. Việc một claim có mặt trong ID Token không làm nó trở thành điều kiện bắt buộc của OIDC cho mọi client.

Không giả định rằng:

- ID Token luôn chứa `email`, `name`, `picture` hay `roles`.
- Trường `email` là khóa định danh không đổi.
- Có `email` thì email đã được kiểm chứng; hãy xét `email_verified` khi chính sách cần và vẫn lưu ý ngữ nghĩa của OP.
- Có `groups`, `roles` hoặc `permissions` thì ứng dụng đã được cấp quyền API. Các claim đó có thể là mở rộng riêng, cần mapping và kiểm tra chính sách.

## 3. Kiểm tra ID Token trước khi tin danh tính

Một client không được tin payload chỉ vì JWT có thể giải mã thành JSON. Trước khi tạo `Authentication`/session dựa trên ID Token, cần áp dụng các kiểm tra OIDC thích hợp.

### 3.1. Nhận đúng issuer và khóa ký

Client xác định OP đã cấu hình, thường thông qua OIDC Discovery:

```http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.org
```

Metadata của OP có thể công bố `issuer`, `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, `jwks_uri` và những khả năng khác. Với ID Token được ký bằng khóa bất đối xứng, client lấy khóa xác minh tin cậy từ JWKS tương ứng với issuer. `kid` là gợi ý chọn khóa, **không phải nguồn tin cậy tự thân**.

Phải giới hạn thuật toán theo những gì client và OP đã thống nhất. Không chấp nhận tùy ý một thuật toán chỉ vì JWT header khai báo như vậy; cũng không tin khóa lấy từ URL tùy ý do payload/header không đáng tin cậy đưa vào. Với trường hợp ID Token mã hóa, client còn cần giải mã theo cấu hình và kiểm tra các lớp bảo vệ tương ứng.

### 3.2. Kiểm tra ID Token thuộc đúng client

`aud` phải chứa Client ID mà ứng dụng đã đăng ký với OP. Nếu token có nhiều audience hoặc `azp` xuất hiện, thực hiện các quy tắc kiểm tra `azp` phù hợp OIDC.

Ví dụ Learning Portal có `client_id = learning-portal`, nhưng token có:

```json
{
  "iss": "https://login.example.org",
  "sub": "student-8fa3b7",
  "aud": "another-application"
}
```

Dù token do issuer đáng tin phát hành và chữ ký hợp lệ, nó **không được dùng** làm ID Token xác thực cho Learning Portal vì audience không đúng.

### 3.3. Kiểm tra thời gian và mối liên hệ với request

OIDC Client cần kiểm tra:

1. Token còn hiệu lực theo `exp` và có các giá trị thời gian hợp lệ với chính sách.
2. `iat` phù hợp quy tắc xác thực, kể cả mức độ “mới” nếu client áp dụng.
3. Nếu request đã gửi `nonce`, ID Token phải chứa nonce khớp với giá trị client đã lưu cho phiên authorization tương ứng.
4. Nếu có yêu cầu `max_age`, kiểm tra `auth_time`; khi cần mức bảo đảm cụ thể, kiểm tra `acr` theo thỏa thuận.
5. Với các flow/response có `at_hash` hoặc `c_hash` liên quan, áp dụng kiểm tra ràng buộc tương ứng.

Ngoài ID Token, client còn cần kiểm tra **`state` của authorization response** để liên kết callback với yêu cầu đã khởi tạo. `state` nằm ở lớp OAuth authorization response; nó không phải claim bắt buộc của ID Token.

### 3.4. Vì sao không tự `Base64.decode()` rồi đăng nhập?

Ví dụ sai về nguyên tắc:

```java
// KHÔNG LÀM THEO: giải mã phần payload không xác thực token.
String[] parts = idTokenString.split("\\.");
String json = new String(
    Base64.getUrlDecoder().decode(parts[1]),
    StandardCharsets.UTF_8
);
// Sai nếu tự đọc "sub" từ json rồi tạo phiên đăng nhập.
```

Bất kỳ ai cũng có thể tạo một chuỗi JWT trông hợp lệ về mặt JSON. Thư viện OIDC chuyên dụng cần xác minh chữ ký/nguồn phát hành, audience và các điều kiện liên quan trước khi tin claims. Spring Security hỗ trợ quá trình xác thực OIDC trong luồng `oauth2Login()` khi được cấu hình đúng; không cần tự viết giải mã JWT cho thao tác đăng nhập.

## 4. UserInfo Endpoint là gì?

**UserInfo Endpoint** là một OAuth 2.0 protected resource được OIDC định nghĩa, trả về claims về End-User đã được xác thực. Client gọi endpoint này bằng **access token** phù hợp do OP phát hành, theo kênh trực tiếp qua HTTPS.

Ví dụ:

```http
GET /userinfo HTTP/1.1
Host: login.example.org
Authorization: Bearer <access-token>
Accept: application/json
```

Phản hồi JSON minh họa:

```json
{
  "sub": "student-8fa3b7",
  "name": "Nguyen Anh",
  "given_name": "Anh",
  "family_name": "Nguyen",
  "preferred_username": "anh.nguyen",
  "email": "anh@example.org",
  "email_verified": true,
  "picture": "https://profile.example.org/avatar/8fa3b7",
  "locale": "vi-VN"
}
```

Mỗi trường ngoài `sub` là **ví dụ có thể có**, không phải cam kết. UserInfo cũng có thể trả một **JWT được ký và/hoặc mã hóa** nếu OP và client được cấu hình cho kiểu phản hồi đó, nên không phải mọi tích hợp đều luôn nhận JSON thuần với cùng HTTP content type.

### 4.1. Tại sao cần UserInfo nếu ID Token đã có `sub`?

Vì phần lớn ứng dụng cần dữ liệu hồ sơ khác với thông tin xác thực cốt lõi:

- Hiển thị tên và ảnh đại diện.
- Cho phép điền sẵn email đã được OP chia sẻ.
- Chọn ngôn ngữ giao diện, múi giờ hoặc định dạng theo `locale`.
- Liên kết hồ sơ từ hệ thống danh tính với dữ liệu nghiệp vụ tại ứng dụng.

ID Token nên được xử lý như kết quả xác thực cho client, còn UserInfo giúp client lấy dữ liệu hồ sơ khi được phép. OP có thể đặt một số claims trong ID Token, một số trong UserInfo, cả hai hoặc không trả, tùy scope, yêu cầu claims, consent và chính sách dữ liệu.

### 4.2. UserInfo có phải nơi xác minh access token không?

**Không.** UserInfo là endpoint dữ liệu hồ sơ, không phải token introspection endpoint. Nó tự kiểm tra access token nhận vào để quyết định trả hồ sơ nào. Client không nên gọi UserInfo như một cách thay thế kiểm tra ID Token, cũng không dùng UserInfo để kiểm tra JWT cho API của mình.

**Không gửi ID Token đến UserInfo** trong header Bearer. ID Token có audience là OIDC Client; UserInfo cần access token có quyền phù hợp.

### 4.3. `sub` từ UserInfo phải khớp ID Token

Đây là điều kiện an toàn nền tảng:

```text
ID Token.sub   = "student-8fa3b7"
UserInfo.sub   = "student-8fa3b7"
Kết quả        = khớp, có thể tiếp tục xử lý claims
```

Nếu:

```text
ID Token.sub   = "student-8fa3b7"
UserInfo.sub   = "student-different"
Kết quả        = không khớp, PHẢI từ chối sử dụng UserInfo response
```

OIDC Core yêu cầu UserInfo response có `sub` và client phải so sánh giá trị đó với `sub` của ID Token. Sự khác biệt có thể chỉ ra lẫn token, lẫn phiên, sai cấu hình hoặc nguy cơ thay thế danh tính. Đừng “chữa” bằng cách dùng `sub` của UserInfo ghi đè principal đã xác thực từ ID Token.

Nếu OP trả UserInfo dạng JWT ký/mã hóa, client còn phải xử lý cơ chế bảo vệ và kiểm tra áp dụng cho kiểu response đó. Với response JSON qua HTTPS, token access và kênh vận chuyển vẫn cần được bảo vệ.

## 5. Những claim hồ sơ phổ biến trong UserInfo

OIDC Standard Claims hỗ trợ nhiều nhóm dữ liệu về End-User. Chúng có thể xuất hiện ở UserInfo hoặc được OP đưa vào ID Token theo chính sách.

| Claim | Ý nghĩa | Lưu ý ứng dụng |
| --- | --- | --- |
| `sub` | Định danh End-User thuộc OP | Phải khớp `sub` ID Token |
| `name` | Tên hiển thị đầy đủ | Không phù hợp làm khóa định danh |
| `given_name` | Tên riêng | Có thể thiếu, tùy văn hóa và nguồn hồ sơ |
| `family_name` | Họ | Không áp đặt định dạng họ/tên cho mọi người dùng |
| `middle_name` | Tên đệm | Tùy chọn |
| `nickname` | Biệt danh | Tùy chọn |
| `preferred_username` | Tên người dùng ưa thích | Có thể trùng, đổi hoặc không được cấp |
| `profile` | URL trang hồ sơ | Cần xử lý URL an toàn khi hiển thị |
| `picture` | URL ảnh đại diện | Dữ liệu có thể thay đổi; không tải tự động từ domain không đáng tin theo cách gây rủi ro |
| `website` | URL website | Tùy chọn |
| `email` | Địa chỉ email | Có thể thay đổi; cần kiểm tra yêu cầu xác minh nếu dùng vào quy trình bảo mật |
| `email_verified` | OP biểu thị đã xác minh địa chỉ email theo nghĩa của nó | Trường boolean, không thay thế kiểm chứng nghiệp vụ hiện tại |
| `gender` | Thông tin giới tính được chia sẻ | Dữ liệu nhạy cảm; chỉ xử lý khi có nhu cầu rõ ràng |
| `birthdate` | Ngày sinh ở định dạng OIDC cho phép | Dữ liệu cá nhân nhạy cảm; cần xác thực định dạng/độ chính xác |
| `zoneinfo` | Múi giờ | Có thể hỗ trợ hiển thị thời gian |
| `locale` | Ngôn ngữ/vùng của người dùng | Ví dụ `vi-VN` |
| `phone_number` | Số điện thoại | Không mặc định đã được xác minh |
| `phone_number_verified` | Trạng thái xác minh số điện thoại theo OP | Có thể không có |
| `address` | Đối tượng địa chỉ có cấu trúc | Dữ liệu cá nhân; giảm thiểu thu thập |
| `updated_at` | Thời điểm hồ sơ được cập nhật tại nguồn | Không có nghĩa toàn bộ claims luôn mới tại thời điểm client đọc |

Các claim dạng JSON phức tạp như `address` có cấu trúc riêng; không giả định mọi claim đều là chuỗi. Các claim mở rộng như `department`, `student_code`, `employee_id`, `groups` hoặc `roles` là **quy ước của nhà cung cấp**, không phải danh sách OIDC Standard Claims cốt lõi.

**Một claim không có trong response không nhất thiết là lỗi.** Nó có thể bị giới hạn bởi scope, consent, privacy policy, người dùng chưa nhập hoặc OP chưa hỗ trợ.

## 6. Scope ảnh hưởng đến claims như thế nào?

Yêu cầu OIDC được nhận biết bằng scope **`openid`**. Các scope tiêu chuẩn thường xin thêm nhóm thông tin:

| Scope | Nhóm thông tin thường được yêu cầu | Không bảo đảm điều gì? |
| --- | --- | --- |
| `openid` | Kích hoạt yêu cầu xác thực OIDC; nhận ID Token theo flow | Không cam kết có email, tên hay ảnh |
| `profile` | Claims hồ sơ như `name`, `family_name`, `given_name`, `preferred_username`, `picture`, `locale`... | Không cam kết tất cả claim hoặc vị trí trả |
| `email` | `email`, `email_verified` | Không bảo đảm email luôn hiện diện hoặc đã xác minh |
| `address` | Claim `address` | Không bảo đảm có địa chỉ hoặc được chia sẻ |
| `phone` | `phone_number`, `phone_number_verified` | Không bảo đảm có số điện thoại hoặc đã xác minh |

Một yêu cầu ví dụ:

```text
scope=openid profile email
```

Có nghĩa client **xin** quyền xác thực theo OIDC và chia sẻ claims hồ sơ/email theo chính sách. Authorization Server/OpenID Provider có thể yêu cầu consent, giới hạn quyền, loại bỏ claim, hoặc không cung cấp các claim cụ thể.

OIDC cũng hỗ trợ tham số **`claims`** để yêu cầu claims cụ thể cho `id_token` và/hoặc `userinfo` khi OP hỗ trợ. Ví dụ minh họa dạng JSON của tham số này:

```json
{
  "id_token": {
    "auth_time": { "essential": true }
  },
  "userinfo": {
    "email": { "essential": true },
    "email_verified": null
  }
}
```

`essential` thể hiện ý nghĩa claim đối với yêu cầu, nhưng không phải giấy phép buộc OP tiết lộ dữ liệu ngoài chính sách và không có nghĩa mọi OP đều hỗ trợ cùng cách xử lý. Client cần xác định khả năng hỗ trợ của provider và cách ứng dụng xử lý khi dữ liệu không được cung cấp.

### 6.1. Khi nào lấy claim trong ID Token, khi nào gọi UserInfo?

Một hướng thiết kế thường gặp:

- **Danh tính đã xác thực:** dùng ID Token hợp lệ; khóa mapping tài khoản bằng issuer và subject.
- **Dữ liệu trình bày:** ưu tiên các claims hồ sơ mà provider cho phép, có thể từ UserInfo khi client cần.
- **Thuộc tính phục vụ quyền nhạy cảm:** lấy từ nguồn đã được xác định là có thẩm quyền; không mặc định mọi claim hồ sơ là cơ sở phân quyền.
- **Tính mới dữ liệu:** nếu tên/email có thể đổi, đặt chiến lược làm mới hoặc đồng bộ rõ ràng thay vì chỉ lấy một lần rồi giữ mãi.

Không có quy tắc bắt buộc “luôn gọi UserInfo” hay “luôn chỉ dùng ID Token” cho mọi ứng dụng. Điều quan trọng là bảo đảm **nguồn tin cậy, mục đích, quyền dữ liệu và sự nhất quán của `sub`**.

## 7. Một ví dụ hoàn chỉnh: từ ID Token đến UserInfo

Giả sử Learning Portal có `client_id = learning-portal` và đã gửi scope `openid profile email`.

### Bước 1: Redirect đến OpenID Provider

Client khởi tạo Authorization Code Flow:

```http
GET /oauth2/authorize?response_type=code
  &client_id=learning-portal
  &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcampus
  &scope=openid%20profile%20email
  &state=<random-state>
  &nonce=<random-nonce>
  &code_challenge=<pkce-challenge>
  &code_challenge_method=S256 HTTP/1.1
Host: login.example.org
```

Ví dụ chỉ diễn tả tham số; khi tạo request thực, URL phải được mã hóa và xây dựng đúng chuẩn HTTP. Giá trị `state`, `nonce` và PKCE verifier/challenge phải được tạo cho từng giao dịch, không dùng chuỗi cố định.

### Bước 2: Nhận token từ token endpoint

Sau khi client xác minh `state` và đổi authorization code thành công (kèm PKCE và xác thực client khi áp dụng), OP trả về:

```json
{
  "access_token": "access_token_example",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "<signed-id-token>",
  "scope": "openid profile email"
}
```

Response có thể có `refresh_token` nếu chính sách cho phép. Nó **không phải bắt buộc** trong mọi Authorization Code Flow.

### Bước 3: Xác thực ID Token

Client kiểm tra chữ ký, issuer, audience, thời gian, nonce đã gửi, các điều kiện khác tùy flow; sau đó xác định danh tính:

```text
issuer    = https://login.example.org
subject   = student-8fa3b7
local key = (https://login.example.org, student-8fa3b7)
```

Đây là căn cứ liên kết người dùng tại RP. Không dùng riêng email hoặc tên hiển thị để tự động hợp nhất tài khoản giữa các issuer.

### Bước 4: Lấy hồ sơ khi cần

Client gọi UserInfo bằng **access token**:

```http
GET /userinfo HTTP/1.1
Host: login.example.org
Authorization: Bearer <access-token>
```

OP trả:

```json
{
  "sub": "student-8fa3b7",
  "name": "Nguyen Anh",
  "email": "anh@example.org",
  "email_verified": true,
  "locale": "vi-VN"
}
```

Client kiểm tra:

```text
userinfo.sub == id_token.sub
```

Khi khớp, client có thể dùng `name` để hiển thị, `locale` để chọn giao diện, và `email` theo chính sách phù hợp. Nếu UserInfo không có `name`, ứng dụng có thể dùng giá trị thay thế như mã định danh nội bộ hoặc lời chào chung.

### Bước 5: Thiết lập principal và truy cập ứng dụng

Learning Portal thiết lập authenticated principal/phiên local sau khi OIDC login hợp lệ. Một endpoint nghiệp vụ vẫn phải kiểm tra phân quyền riêng: dù người dùng đã đăng nhập, họ không tự động có quyền truy cập toàn bộ hồ sơ sinh viên.

## 8. Spring Security: ID Token và UserInfo được biểu diễn như thế nào?

Trong ứng dụng Spring Boot dùng Spring Security OAuth2/OIDC Client:

- `ClientRegistration` giữ cấu hình client/provider.
- `oauth2Login()` thực hiện luồng đăng nhập OAuth2; nếu scope có `openid`, Spring Security xử lý luồng OIDC tương ứng.
- `OidcUser` là principal OIDC được xác thực.
- `OidcIdToken` biểu diễn ID Token đã được xử lý trong luồng OIDC.
- `OidcUserInfo` biểu diễn các claims lấy từ UserInfo, khi có.
- `OidcUserService` là thành phần tải và hợp nhất dữ liệu OIDC UserInfo theo cấu hình và điều kiện của Spring Security.
- `OidcUser.getClaims()` cung cấp các claims được tổng hợp phục vụ ứng dụng; nếu cần **nguồn gốc** của từng claim, nên đọc riêng `getIdToken().getClaims()` và `getUserInfo().getClaims()`.

### 8.1. Cấu hình OIDC Client bằng Spring Boot

Ví dụ trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          campus:
            provider: campus
            client-id: ${CAMPUS_CLIENT_ID}
            client-secret: ${CAMPUS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          campus:
            issuer-uri: https://login.example.org
```

Ví dụ giả định **confidential client** ở backend với secret trong cấu hình an toàn. Với public client như SPA/mobile, không thể bảo vệ client secret nhúng trong ứng dụng và cần cấu hình theo loại client tương ứng.

`issuer-uri` cho phép Spring Security khám phá metadata của provider nếu OP hỗ trợ OIDC Discovery. Issuer, endpoint, phương thức xác thực client, redirect URI và phạm vi quyền thực tế phải khớp cấu hình tại OP.

Ví dụ security chain:

```java
@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Với cấu hình đăng nhập này, luồng OIDC có thể bắt đầu qua:

```text
/oauth2/authorization/campus
```

Callback mặc định theo `registrationId`:

```text
/login/oauth2/code/campus
```

Các snippet tập trung vào API và cấu hình liên quan; giả định dự án có dependency và import Spring Boot/Spring Security thích hợp.

### 8.2. Đọc OIDC principal trong controller

Sau khi đăng nhập thành công, Spring Security có thể inject principal:

```java
@RestController
class MyProfileController {

    @GetMapping("/me")
    Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> response = new LinkedHashMap<>();

        response.put("subject", user.getSubject());
        response.put("name", user.getClaimAsString("name"));
        response.put("email", user.getClaimAsString("email"));
        response.put("emailVerified", user.getClaims().get("email_verified"));
        response.put("hasUserInfo", user.getUserInfo() != null);

        return response;
    }
}
```

Ví dụ chỉ trả một số trường đã chọn của người dùng **cho chính họ** ở endpoint đã được bảo vệ. Trong ứng dụng thật, cần áp dụng kiểm soát quyền truy cập, tránh lộ PII ngoài phạm vi và không đưa các token vào response.

Lưu ý rằng `OidcUser.getClaimAsString("name")` có thể là `null`. Nếu người dùng không có tên từ OP, UI nên có fallback phù hợp. Các claim trả về có thể được tổng hợp từ ID Token và UserInfo; dùng cách đọc tách nguồn nếu tính xuất xứ có ý nghĩa.

### 8.3. Phân biệt rõ claim từ ID Token và từ UserInfo

Ví dụ một component chỉ kiểm tra dữ liệu trong backend, **không xuất nguyên toàn bộ claims ra API**:

```java
@Service
class OidcClaimInspector {

    boolean idTokenContainsEmail(OidcUser user) {
        OidcIdToken idToken = user.getIdToken();
        return idToken.getClaims().containsKey("email");
    }

    boolean userInfoContainsEmail(OidcUser user) {
        OidcUserInfo userInfo = user.getUserInfo();
        return userInfo != null
            && userInfo.getClaims().containsKey("email");
    }

    String authenticatedSubject(OidcUser user) {
        return user.getIdToken().getSubject();
    }
}
```

- `user.getIdToken()` chứa ID Token đã được Spring dùng để xây principal.
- `user.getUserInfo()` có thể là `null` nếu UserInfo không được gọi hoặc không có dữ liệu.
- `user.getClaims()` có thể thể hiện dữ liệu được tổng hợp. Không dựa vào nó để kết luận tất cả claims xuất hiện trong ID Token.
- `user.getSubject()` là định danh OIDC chủ thể đã được xác thực; khi UserInfo được sử dụng, yêu cầu `sub` phải khớp.

Trong code nghiệp vụ, nếu cần email đã xác minh, hãy xây quy tắc rõ ràng về provider, claim `email_verified`, mục đích xử lý và trường hợp claim vắng mặt. Không coi việc không có email là bằng chứng đăng nhập OIDC thất bại.

### 8.4. UserInfo có được Spring Security gọi tự động không?

Spring Security tích hợp `OidcUserService`, có thể lấy các claims từ UserInfo Endpoint theo khả năng provider và các điều kiện được cấu hình. Trong các phiên bản và cấu hình thường gặp, việc truy vấn UserInfo phụ thuộc metadata `userinfo_endpoint`, access token và scope liên quan đến hồ sơ như `profile`, `email`, `address` hoặc `phone`.

**Đừng giả định mọi request OIDC đều gọi UserInfo.** Ứng dụng chỉ có `openid`, provider không công bố UserInfo, scope bị giới hạn hoặc chính sách tùy biến có thể dẫn đến `OidcUserInfo` vắng mặt. Hành vi chi tiết còn phụ thuộc phiên bản Spring Security và cấu hình dịch vụ OIDC. Muốn chắc nguồn claim, hãy kiểm tra cấu hình của tích hợp cụ thể và truy xuất riêng các đối tượng ID Token/UserInfo.

Có thể cấu hình tùy biến bằng hook:

```java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)
    )
);
```

Ở đây `customOidcUserService` là một `OAuth2UserService<OidcUserRequest, OidcUser>` do ứng dụng cung cấp, thường delegate cho `OidcUserService` chuẩn để giữ nguyên cơ chế xác thực/tải UserInfo rồi bổ sung quy tắc miền nghiệp vụ. Không nên viết một phiên bản tự gọi HTTP UserInfo mà bỏ kiểm tra subject, token và các biện pháp bảo mật sẵn có của thư viện.

### 8.5. Ví dụ custom OidcUserService khi ứng dụng yêu cầu email đã xác minh

Chỉ áp dụng yêu cầu này **nếu chính sách sản phẩm thật sự đòi hỏi email đã xác minh**. Một số OP không cấp email hoặc `email_verified`, và đăng nhập bằng ID Token hợp lệ không mặc định cần email.

```java
@Configuration
class OidcProfilePolicyConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> verifiedEmailOidcService() {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);

            if (!Boolean.TRUE.equals(
                    user.getClaimAsBoolean("email_verified"))) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("unverified_email"),
                    "This application requires a verified email"
                );
            }

            return user;
        };
    }
}
```

Để sử dụng, truyền bean trên vào cấu hình `.userInfoEndpoint(...oidcUserService(...))`. Chính sách này từ chối cả trường hợp không có claim `email_verified`; đó là **quyết định riêng của ứng dụng** chứ không phải quy tắc OIDC bắt buộc. Nếu có nhiều OP, cần xác định có thể tin cách mỗi OP xác minh email hay không trước khi dùng cho nghiệp vụ.

Không đưa `email`, raw claims hoặc token vào log lỗi chỉ để giải thích tại sao đăng nhập bị từ chối.

## 9. Quản lý danh tính cục bộ và quyền truy cập

### 9.1. Định danh tài khoản bằng `(issuer, subject)`

Một hệ thống có nhiều provider nên lưu quan hệ như:

| Local user ID | OIDC issuer | OIDC subject |
| --- | --- | --- |
| `user-101` | `https://login.example.org` | `student-8fa3b7` |
| `user-202` | `https://idp.partner.example.org` | `student-8fa3b7` |

Hai dòng trên **không nhất thiết chỉ cùng một người** vì issuer khác nhau. Không tự động hợp nhất chỉ vì `sub`, `email` hoặc `preferred_username` giống nhau.

Một mô hình đơn giản trong ứng dụng:

```text
LocalAccount
  id                   // khóa nội bộ ổn định
  displayName          // dữ liệu trình bày, có thể cập nhật

ExternalIdentity
  localAccountId       // liên kết với LocalAccount
  issuer               // OIDC iss
  subject              // OIDC sub
  linkedAt             // thời điểm liên kết
```

Nên có ràng buộc uniqueness phù hợp trên `(issuer, subject)` và quy trình liên kết tài khoản rõ ràng. Với OP cung cấp pairwise subject identifier, một người dùng có thể có `sub` khác nhau giữa các client; đó không phải lỗi của OIDC.

### 9.2. Authentication không đồng nghĩa Authorization

OIDC xác thực rằng OP đã xác thực một chủ thể trong ngữ cảnh của ID Token. Nó **không tự cấp** quyền đối với nghiệp vụ của Learning Portal.

Ví dụ:

- ID Token hợp lệ xác định sinh viên `student-8fa3b7`.
- UserInfo cung cấp tên “Nguyen Anh” và email đã xác minh.
- Một endpoint `/admin/users` vẫn phải kiểm tra role/quyền quản trị từ nguồn có thẩm quyền theo chính sách.
- Một endpoint `/courses/123/grades` vẫn phải kiểm tra người dùng có được xem điểm của khóa học/bản ghi đó không.

Nếu provider đưa `roles` hoặc `groups` vào token/UserInfo, cần thiết kế mapping issuer, claim, giá trị và quyền nội bộ rõ ràng. Không tự tin mọi giá trị tự khai báo hoặc mọi claim hồ sơ đều đủ làm quyền.

### 9.3. Dùng `email_verified` đúng mức

`email_verified: true` có nghĩa OP biểu thị đã xác minh địa chỉ email theo quy trình của nó. Nó không có nghĩa:

- Email không bao giờ thay đổi.
- Email luôn thuộc độc quyền người đó trong mọi hệ thống và mọi thời điểm.
- User được phép truy cập dữ liệu chỉ vì email có tên miền của trường.
- Có thể tự động liên kết với một tài khoản nội bộ có cùng email mà không kiểm tra rủi ro chiếm đoạt tài khoản.

Với tác vụ nhạy cảm như account linking, đổi địa chỉ khôi phục, hoặc cấp quyền theo domain, nên có quy tắc nghiệp vụ, xác minh cần thiết và audit cụ thể.

## 10. Quyền riêng tư, tính mới và xử lý thiếu dữ liệu

### 10.1. Data minimization

Chỉ xin các scope và claim cần cho tính năng. Nếu UI chỉ cần tên hiển thị, không nhất thiết xin `address`, `phone` hoặc `birthdate`. Cần bảo vệ dữ liệu cá nhân ở mọi nơi:

- Đừng ghi raw ID Token, access token hay toàn bộ response UserInfo vào log, telemetry hoặc exception.
- Chỉ đưa claims cần thiết đến browser; backend có thể lọc/ẩn dữ liệu nhạy cảm.
- Cân nhắc lưu trữ mã hóa, phân quyền truy cập, thời hạn lưu và quy trình xóa dữ liệu.
- Không tự động nhúng URL ảnh/hồ sơ từ nguồn không tin cậy trong ngữ cảnh có thể gây XSS hoặc rủi ro tải tài nguyên không kiểm soát.
- Phân tách claims phục vụ hiển thị khỏi dữ liệu dùng cho kiểm soát truy cập.

### 10.2. Hồ sơ có thể thay đổi giữa hai lần đăng nhập

`name`, `picture`, `email`, `locale`, trạng thái xác minh và một số claim khác có thể được OP cập nhật. Một ID Token hoặc UserInfo response cũ không tự cập nhật khi OP sửa hồ sơ. Nếu ứng dụng cần dữ liệu mới, hãy định nghĩa khi nào truy vấn lại UserInfo, kiểm tra quyền hiện hành và xử lý cache theo kỳ hạn.

**Thay đổi claims không luôn đồng nghĩa thay đổi danh tính.** Cặp `(iss, sub)` có tính chất định danh khác với email hoặc tên.

### 10.3. Không có UserInfo thì phải làm sao?

Điều này có thể hoàn toàn hợp lệ. Ứng dụng cần:

1. Tiếp tục dùng ID Token đã được xác thực để xác định chủ thể khi quy trình login hợp lệ.
2. Chỉ sử dụng các claims hồ sơ thực sự được provider cung cấp.
3. Đặt fallback hợp lý cho tên/ảnh/email và tránh crash vì `null`.
4. Nếu tính năng bắt buộc một thuộc tính mà OP không trả, hiển thị hướng dẫn hoặc áp dụng quy trình thu thập/xác minh bổ sung theo chính sách.

Không tạo email hoặc user ID giả rồi đối xử như dữ liệu đã được OP xác minh.

## 11. Lỗi tích hợp thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ID Token decode được nhưng Spring từ chối đăng nhập | Sai issuer, audience, chữ ký, thời gian hoặc nonce | Kiểm tra registration/issuer, khóa công khai, đồng hồ hệ thống và transaction OIDC |
| Đăng nhập thành công nhưng `OidcUserInfo == null` | UserInfo không được gọi, không có endpoint/điều kiện/scope phù hợp | Xem metadata, scope đã cấp và cấu hình OIDC User Service |
| UserInfo trả HTTP 401 | Access token hết hạn, sai token hoặc token không được UserInfo chấp nhận | Kiểm tra access token và cách gọi đúng provider |
| ID Token và UserInfo có `sub` khác nhau | Trộn phiên/token hoặc provider triển khai sai | Từ chối dùng UserInfo; điều tra session/client/issuer |
| `name` hoặc `email` vắng mặt | Provider không cấp claim hoặc scope/consent hạn chế | Kiểm tra scope, consent, provider mapping và dùng fallback |
| Cùng email nhưng có hai tài khoản | Hai issuer/subject khác nhau hoặc lịch sử mapping khác nhau | Thiết kế quy trình account linking; không tự hợp nhất |
| Người dùng đã đăng nhập nhưng API trả 403 | Authentication thành công nhưng thiếu quyền nghiệp vụ hoặc access token không có scope phù hợp | Kiểm tra authorization ở API; không sửa bằng ID Token |
| Sau cập nhật hồ sơ, giao diện vẫn hiện tên cũ | Ứng dụng giữ claims từ phiên/login trước | Định nghĩa chiến lược cập nhật dữ liệu và cache |
| Sau khi refresh, ứng dụng mặc định profile đã cập nhật | Refresh access token không buộc UserInfo/ID Token được lấy lại và cập nhật hồ sơ | Làm mới hồ sơ theo cơ chế riêng khi cần |
| Tài khoản A nhìn thấy dữ liệu của B | Dùng tên/email thay subject làm khóa, hoặc kiểm tra ownership không đúng | Sửa mapping `(iss, sub)` và authorization của từng tài nguyên |

### 11.1. Quan sát lỗi đúng cách

Trong log/metrics, ưu tiên lưu thông tin kỹ thuật không nhạy cảm: registration ID, issuer được cấu hình, loại lỗi OIDC, mã HTTP, correlation ID và thời điểm. Với dữ liệu liên quan người dùng, cần chính sách giảm thiểu và bảo vệ; không log token hay toàn bộ claims chứa PII.

Khi cần debug nguồn claim, có thể kiểm tra cục bộ sự tồn tại của `getIdToken()` và `getUserInfo()` cùng tên claim cụ thể. Không tạo endpoint trả toàn bộ ID Token payload hoặc UserInfo response ra công khai.

## 12. Các tình huống thực hành

### Tình huống A — ID Token không chứa email

Portal nhận ID Token có `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`; không có `email`. Sau khi gọi UserInfo bằng access token, Portal nhận `email`, `email_verified`, `name`.

**Cách xử lý:** Xác thực ID Token trước, đối chiếu `userinfo.sub` với `id_token.sub`, rồi dùng email cho mục đích đã được phép. Không cần coi ID Token thiếu email là lỗi đăng nhập.

### Tình huống B — ID Token có email nhưng người dùng đã đổi email

Portal giữ hồ sơ cũ từ lần đăng nhập trước, trong khi OP đã đổi email trong nguồn chính. Một UserInfo response mới có thể phản ánh cập nhật, tùy provider và cache.

**Cách xử lý:** dùng `(iss, sub)` để định danh ổn định; xác định chính sách làm mới, thông báo và xác minh email nếu nghiệp vụ phụ thuộc email. Không tạo tài khoản mới chỉ vì email đổi.

### Tình huống C — ID Token có `iat` mới nhưng `auth_time` cũ

Người dùng có phiên SSO 10 giờ trước; OP vừa cấp ID Token mới lúc này. Một tính năng nhạy cảm yêu cầu xác thực không quá 5 phút.

**Cách xử lý:** cân nhắc yêu cầu `max_age` hoặc ngữ cảnh xác thực thích hợp, và kiểm tra `auth_time` theo chính sách. Không dùng riêng `iat` để suy ra lần xác thực mới.

### Tình huống D — UserInfo trả `sub` khác ID Token

Client đã xác thực ID Token cho `student-A`, nhưng UserInfo trả `student-B`.

**Cách xử lý:** từ chối sử dụng UserInfo response. Kiểm tra việc dùng nhầm access token từ phiên khác, lỗi kho token, registration và cấu hình provider. Không sửa principal thành `student-B`.

### Tình huống E — Có nhóm `ADMIN` trong hồ sơ

UserInfo trả thêm `groups: ["ADMIN"]` theo mở rộng riêng của OP.

**Cách xử lý:** chỉ ánh xạ thành quyền quản trị nếu ứng dụng có hợp đồng rõ với OP về độ tin cậy, phạm vi, tính mới của claim và kiểm soát truy cập. OIDC Standard Claims không tự biến chuỗi `ADMIN` thành quyền hợp lệ.

## 13. Câu hỏi tự kiểm tra

**1. ID Token và UserInfo đều có `sub`. Có cần so sánh không?**

> Có. OIDC Client phải kiểm tra `sub` trong UserInfo response khớp `sub` trong ID Token; nếu khác phải từ chối dùng UserInfo response.

**2. Có thể dùng ID Token gửi `Authorization: Bearer` đến Course API không?**

> Không. ID Token dành cho OIDC Client/RP; API cần access token phù hợp, có quyền, audience và hiệu lực hợp lệ.

**3. Vì sao `iat` không chứng minh người dùng vừa hoàn thành MFA?**

> `iat` là thời điểm phát hành token, không phải thời điểm xác thực. Cần xem `auth_time` và chính sách `acr`/`amr` khi yêu cầu mức bảo đảm xác thực cụ thể.

**4. Scope `openid profile email` có bảo đảm UserInfo trả toàn bộ `name`, `email`, `picture` không?**

> Không. Scope là yêu cầu nhóm thông tin; claims thực tế phụ thuộc provider, người dùng, consent và chính sách. Client cần xử lý dữ liệu thiếu.

**5. Trong Spring Security, làm sao phân biệt email đến từ ID Token hay UserInfo?**

> Kiểm tra `user.getIdToken().getClaims()` và, nếu `user.getUserInfo()` khác `null`, kiểm tra `user.getUserInfo().getClaims()`. `user.getClaims()` là tập claims tổng hợp và không thể hiện đầy đủ nguồn gốc.

**6. Hai người ở hai OP khác nhau có cùng `sub = "123"`. Có thể gộp thành một tài khoản?**

> Không thể dựa vào `sub` đơn lẻ. Sử dụng issuer cùng subject, và chỉ liên kết tài khoản qua quy trình được thiết kế rõ.

**7. Tại sao không tự Base64URL-decode JWT rồi lấy `sub` để đăng nhập?**

> Decode không kiểm tra chữ ký, issuer, audience, expiration, nonce và các ràng buộc OIDC. Dùng thư viện xác thực OIDC đúng cách như tích hợp `oauth2Login()` của Spring Security.

---

## Ghi nhớ

**ID Token trả lời câu hỏi về việc OpenID Provider đã xác thực ai cho Relying Party nào, vào thời điểm và ngữ cảnh nào.** Client cần xác minh ID Token đầy đủ trước khi tin `iss` và `sub`. **UserInfo trả các claims hồ sơ được phép chia sẻ**, được lấy bằng access token qua UserInfo Endpoint; `sub` từ UserInfo phải khớp ID Token. Trong Spring Security, `OidcUser` cho phép truy cập riêng `OidcIdToken` và `OidcUserInfo`, đồng thời cung cấp claims tổng hợp cho ứng dụng. Danh tính liên kết bằng `(iss, sub)` nên được tách khỏi các thông tin hồ sơ có thể thay đổi và khỏi quyết định phân quyền nghiệp vụ.
