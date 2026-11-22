# 3.2. Scope `openid`, `profile`, `email`, `address` và `phone`

Trong **Spring Security OAuth 2.0/OIDC Client**, khi người dùng đăng nhập bằng một OpenID Provider (OP), ứng dụng thường yêu cầu các **scope** để cho biết mình muốn thực hiện đăng nhập OIDC và cần những nhóm thông tin nào về người dùng. Năm scope chuẩn thường gặp là `openid`, `profile`, `email`, `address` và `phone`.

Câu hỏi cốt lõi của bài học là: **yêu cầu một scope có ý nghĩa gì, scope đó gắn với claim nào, và Spring Security đọc thông tin được cấp ở đâu?** Trả lời đúng giúp tránh nhầm lẫn giữa *yêu cầu quyền truy cập*, *được người dùng đồng ý*, *thực sự nhận được claim* và *quyết định phân quyền trong ứng dụng*.

## 1. Bức tranh chung: Scope khác claim như thế nào?

Trong OAuth 2.0, `scope` là một danh sách các chuỗi do Client yêu cầu trong authorization request. Authorization Server quyết định cấp những scope nào dựa trên cấu hình Client, chính sách, sự đồng ý của người dùng và ngữ cảnh xác thực.

**OIDC** xây dựng trên OAuth 2.0, quy định scope `openid` làm tín hiệu cho yêu cầu xác thực danh tính và định nghĩa thêm các scope dùng để **yêu cầu nhóm claim tiêu chuẩn**.

- **Scope** là *tên nhóm quyền hoặc nhóm thông tin được yêu cầu*, ví dụ `email`.
- **Claim** là *thuộc tính có tên và giá trị của người dùng hoặc sự kiện xác thực*, ví dụ `"email": "lan@example.test"`.
- **ID Token** là token OIDC đã được ký/xác thực, dùng để xác nhận danh tính và sự kiện đăng nhập.
- **UserInfo Endpoint** là endpoint OIDC mà Client có thể gọi bằng access token để nhận một tập claim về người dùng.
- **Access token** dùng để truy cập tài nguyên được cấp phép, ví dụ UserInfo Endpoint; không phải bản thân nó luôn chứa tất cả claim mà Client yêu cầu.

Ví dụ, Client yêu cầu `scope=openid%20profile%20email`. Điều đó không có nghĩa IdP bắt buộc trả về mọi trường của `profile`, cũng không có nghĩa chắc chắn có `email_verified=true`. Các claim trong nhóm này có thể thiếu vì dữ liệu không tồn tại, người dùng không đồng ý, Client chưa được cấp quyền hoặc chính sách IdP hạn chế việc tiết lộ.

### 1.1. Bảng tổng quan năm scope tiêu chuẩn

| Scope | Công dụng | Các claim tiêu chuẩn được yêu cầu |
|---|---|---|
| `openid` | Khởi tạo **yêu cầu xác thực OIDC**; phân biệt với OAuth 2.0 thuần túy | Dẫn đến ID Token; định danh chủ thể qua `sub` (ID Token có các claim giao thức bắt buộc khác) |
| `profile` | Xin các thông tin hồ sơ cơ bản | `name`, `family_name`, `given_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` |
| `email` | Xin địa chỉ email và trạng thái xác minh email | `email`, `email_verified` |
| `address` | Xin địa chỉ liên hệ của người dùng | `address` (một đối tượng có các trường con) |
| `phone` | Xin số điện thoại và trạng thái xác minh số điện thoại | `phone_number`, `phone_number_verified` |

Danh sách trong bảng là **các claim mà scope yêu cầu theo OIDC**, không phải cam kết mọi claim sẽ có mặt. IdP có thể có những scope bổ sung như `roles`, `groups` hoặc scope riêng cho API; các scope đó **không thuộc** năm scope chuẩn đang học và phải đọc tài liệu của nhà cung cấp.

### 1.2. Tại sao phải có `openid`?

Trong một yêu cầu OAuth 2.0 không có `openid`, Server không được yêu cầu xử lý đó như một yêu cầu OIDC. Khi có `openid` trong authorization request và flow thành công theo OIDC, Client nhận **ID Token** để xác minh danh tính. ID Token có các claim giao thức như `iss` (issuer), `sub` (subject), `aud` (audience), `exp` và `iat`.

Cần phân biệt rõ:

- `openid` là **scope bắt buộc của OIDC**.
- `profile`, `email`, `address`, `phone` là **scope tùy chọn** để yêu cầu thêm thông tin.
- `sub` là định danh của chủ thể do issuer cấp; không phải tên, email hay số điện thoại.
- Việc nhận ID Token **không phụ thuộc** vào việc xin `profile` hay `email`.

Một cấu hình chỉ có `scope=openid` vẫn có thể cho phép người dùng đăng nhập OIDC nếu IdP/Client hỗ trợ flow tương ứng. Nếu giao diện cần tên hiển thị, ứng dụng có thể yêu cầu thêm `profile`; nếu chức năng cần địa chỉ liên lạc qua email, có thể cân nhắc `email`.

## 2. Các scope xuất hiện ở đâu trong luồng đăng nhập?

Trong Authorization Code Flow, Spring Security OAuth2 Login điều hướng trình duyệt tới Authorization Endpoint của IdP. Ở đó có tham số `scope`, ví dụ:

```http
GET /authorize?
    response_type=code&
    client_id=web-client&
    redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
    scope=openid%20profile%20email%20address%20phone&
    state=RANDOM_STATE&
    code_challenge=RANDOM_CHALLENGE&
    code_challenge_method=S256 HTTP/1.1
Host: id.example.test
```

Ví dụ được xuống dòng chỉ để dễ đọc; request thực tế phải có URI đã URL-encode hợp lệ. Đây là authorization request do Spring Security Client tạo từ `ClientRegistration` và đưa trình duyệt đến nhà cung cấp. Với OIDC, các tham số như `nonce` cũng thường được sử dụng trong yêu cầu xác thực.

```mermaid
sequenceDiagram
    autonumber
    participant Browser as Trình duyệt
    participant Spring as Spring Security Client
    participant OP as OpenID Provider

    Browser->>Spring: GET /oauth2/authorization/company
    Spring-->>Browser: 302 tới OP với scope=openid profile email...
    Browser->>OP: Authorization request
    OP->>OP: Đăng nhập, xét chính sách và consent
    OP-->>Browser: Redirect URI với code, state
    Browser->>Spring: /login/oauth2/code/company?code=...&state=...
    Spring->>OP: POST Token Endpoint để đổi code
    OP-->>Spring: Access token, ID Token, ...
    opt Có UserInfo Endpoint và Client có quyền truy cập
        Spring->>OP: GET UserInfo với access token
        OP-->>Spring: Các claim được phép tiết lộ
    end
    Spring->>Spring: Xác minh ID Token, tạo OidcUser
    Spring-->>Browser: Thiết lập phiên đăng nhập
```

Trong bảng trên, scope được **yêu cầu ở Authorization Endpoint**; token và claim được nhận **sau khi flow thành công**. Tùy cấu hình provider, các claim có thể nằm trong ID Token, phản hồi UserInfo hoặc được tổng hợp từ hai nguồn. Không nên tự cho rằng chỉ cần mở payload ID Token là sẽ thấy đầy đủ `profile`, `email`, `address` và `phone`.

### 2.1. Phân biệt scope yêu cầu và scope thực sự được cấp

Giả sử Client yêu cầu:

```text
openid profile email address phone
```

Nhà cung cấp có thể chỉ chấp thuận một tập con, hoặc từ chối scope không hợp lệ. Token response của OAuth 2.0 có thể chứa trường `scope` để mô tả scope được cấp:

```json
{
  "access_token": "example-access-token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "example-id-token"
}
```

Trong ví dụ này, ứng dụng không thể suy ra mình đã nhận `address` và `phone` chỉ vì đã yêu cầu chúng. Nếu `scope` vắng mặt trong token response, cần áp dụng quy tắc OAuth 2.0 và cấu hình provider để hiểu scope đã cấp; không nên tự diễn giải rằng mọi trường dữ liệu mong muốn đều có.

**Scope được chấp thuận vẫn không đảm bảo claim được trả về.** Cách thiết kế an toàn là kiểm tra claim có tồn tại và có kiểu dữ liệu phù hợp trước khi dùng.

## 3. Scope `openid`: xác thực danh tính, không chỉ đọc hồ sơ

`openid` biến yêu cầu thành một yêu cầu xác thực OpenID Connect. Với Authorization Code Flow, sau khi Spring đổi authorization code thành công, phản hồi token OIDC bao gồm ID Token. Spring Security kiểm tra ID Token bằng cơ chế OIDC, chẳng hạn chữ ký, issuer, audience, hạn sử dụng và các kiểm tra tương quan với authorization request theo flow.

ID Token ví dụ, trình bày **payload giải mã** cho dễ hiểu (không phải token JWT thật):

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "u_314159",
  "aud": "spring-web-client",
  "exp": 1781111000,
  "iat": 1781107400,
  "auth_time": 1781107390
}
```

Chỉ các claim thích hợp với flow và trường hợp cụ thể mới xuất hiện; `auth_time` chẳng hạn không bắt buộc ở mọi ID Token. Giá trị thời gian và tên miền trong ví dụ là minh họa.

### 3.1. `sub` là chìa khóa định danh

Ứng dụng thường cần một khóa ổn định để liên kết tài khoản của người dùng trong hệ thống nội bộ. Với OIDC, nên dùng cặp:

```text
(iss, sub)
```

Ví dụ:

```text
("https://id.example.test/realms/company", "u_314159")
```

Lý do phải có `iss`: hai IdP khác nhau có thể cấp cùng một chuỗi `sub` cho các người dùng khác nhau. Lý do không dùng `email` làm khóa chính: email có thể thay đổi, thiếu, hoặc được tái sử dụng theo chính sách của provider. `preferred_username` và `name` cũng có thể đổi và không đảm bảo duy nhất.

Một IdP có thể dùng **pairwise subject identifier**, nghĩa là cùng một người có thể nhận `sub` khác nhau ở các Client/sector khác nhau. Do đó không tự ghép tài khoản giữa nhiều ứng dụng chỉ bằng cách so sánh tên hoặc email.

### 3.2. `openid` không đồng nghĩa với quyền truy cập API nghiệp vụ

Đăng nhập OIDC trả lời câu hỏi **“Người dùng là ai theo provider?”**. Quyết định “người này được phép duyệt hóa đơn hay quản trị người dùng?” là **authorization** của ứng dụng. Scope `openid` không tự cấp vai trò `ADMIN` hoặc quyền vào một API bất kỳ.

Nếu ứng dụng gọi thêm API được bảo vệ, cần xem access token có audience, scope và chính sách phù hợp với API đó. Scope OIDC dùng yêu cầu claim và scope cấp quyền API là hai mục đích có liên quan nhưng không nên đánh đồng.

## 4. Scope `profile`: yêu cầu dữ liệu hồ sơ cơ bản

`profile` dùng để xin nhóm claim mô tả hồ sơ người dùng. Các claim tiêu chuẩn có ý nghĩa như sau:

| Claim | Ví dụ | Ý nghĩa và lưu ý |
|---|---|---|
| `name` | `"Nguyễn Thị Lan"` | Tên hiển thị đầy đủ; không phải định danh duy nhất |
| `family_name` | `"Nguyễn"` | Họ hoặc tên gia đình |
| `given_name` | `"Lan"` | Tên gọi |
| `middle_name` | `"Thị"` | Tên đệm |
| `nickname` | `"Lan"` | Biệt danh |
| `preferred_username` | `"lan.nguyen"` | Tên đăng nhập hoặc tên người dùng ưa dùng; có thể thay đổi và không đảm bảo duy nhất |
| `profile` | `"https://id.example.test/users/u314159"` | URL trang hồ sơ |
| `picture` | `"https://cdn.example.test/u314159.png"` | URL ảnh đại diện |
| `website` | `"https://example.test"` | URL website của người dùng |
| `gender` | `"female"` | Thông tin giới tính nếu được người dùng/provider cung cấp |
| `birthdate` | `"1995-06-03"` | Ngày sinh theo biểu diễn được OIDC hỗ trợ; đôi khi chỉ có năm hoặc tháng/ngày |
| `zoneinfo` | `"Asia/Ho_Chi_Minh"` | Múi giờ theo cơ sở dữ liệu timezone |
| `locale` | `"vi-VN"` | Ngôn ngữ/vùng ưu tiên theo language tag |
| `updated_at` | `1781100000` | Thời điểm thông tin người dùng được cập nhật, dạng số giây Unix |

Một phản hồi hồ sơ tối giản có thể chỉ gồm:

```json
{
  "sub": "u_314159",
  "name": "Nguyễn Thị Lan",
  "preferred_username": "lan.nguyen",
  "picture": "https://cdn.example.test/avatars/u314159.png",
  "locale": "vi-VN"
}
```

Việc xin `profile` **không có nghĩa** IdP bắt buộc lưu đủ 14 claim hoặc cho phép Client đọc tất cả. Từng provider quyết định dữ liệu nào có sẵn và được phép tiết lộ.

### 4.1. Có thể dùng `name`, `picture` và `locale` thế nào?

- Dùng `name` hoặc `preferred_username` như một lựa chọn để hiển thị lời chào, sau khi kiểm tra giá trị trống.
- Dùng `picture` để hiển thị avatar sau khi xử lý URL an toàn theo yêu cầu của giao diện.
- Dùng `locale` để đề xuất ngôn ngữ giao diện, nhưng vẫn tôn trọng lựa chọn ngôn ngữ thực tế của người dùng.

Không dùng các giá trị này làm căn cứ bảo mật hoặc phân quyền. Ngay cả trường `updated_at` cũng chỉ mô tả bản cập nhật hồ sơ theo IdP; nó không bảo đảm ứng dụng đang có dữ liệu được đồng bộ tức thời.

## 5. Scope `email`: email và trạng thái xác minh

`email` yêu cầu hai claim tiêu chuẩn:

| Claim | Kiểu | Ví dụ | Diễn giải |
|---|---|---|---|
| `email` | String | `"lan@example.test"` | Địa chỉ email của người dùng |
| `email_verified` | Boolean | `true` | Provider cho biết họ đã thực hiện bước xác minh quyền kiểm soát địa chỉ email theo cơ chế của họ |

Ví dụ:

```json
{
  "sub": "u_314159",
  "email": "lan@example.test",
  "email_verified": true
}
```

### 5.1. Ba trạng thái cần phân biệt

Trong chương trình Java, claim `email_verified` có thể:

1. Có mặt và mang giá trị `true`.
2. Có mặt và mang giá trị `false`.
3. **Không có mặt**.

Trường hợp thứ ba không được tùy tiện diễn giải là provider khẳng định email chưa được xác minh; đó là tình trạng **chưa có thông tin xác minh** ở dữ liệu Client nhận được. Trong các tính năng nhạy cảm, chỉ chấp nhận `Boolean.TRUE.equals(value)` nếu yêu cầu phải có email đã được xác minh.

### 5.2. “Email verified” không thay thế phân quyền

`email_verified=true` không chứng minh người dùng thuộc một phòng ban, đang là nhân viên của một công ty hoặc có quyền quản trị. Nó cũng không tự bảo đảm địa chỉ email không bao giờ thay đổi hoặc quyền kiểm soát email không thể mất về sau.

Ví dụ một ứng dụng SaaS muốn giới hạn người dùng của tổ chức:

- Chỉ kiểm tra email có hậu tố `@company.test` là chưa đủ để phân quyền.
- Cần có quản lý thành viên tổ chức, mời tham gia, vai trò/quyền nội bộ hoặc thông tin từ hệ thống nhận dạng được tin cậy.
- Nếu cần xác minh email để gửi thông báo, có thể yêu cầu `email_verified=true` theo chính sách chức năng.

Để liên kết tài khoản, dùng `(iss, sub)` và một cơ chế xác nhận sở hữu tài khoản nội bộ phù hợp; không tự động gộp hai tài khoản chỉ vì email hiện tại giống nhau.

## 6. Scope `address`: địa chỉ là một đối tượng có cấu trúc

Khác với `email`, scope `address` chủ yếu yêu cầu **một claim `address` có dạng JSON object**. Theo danh sách Address Claim tiêu chuẩn của OIDC, object có các trường:

| Trường con | Ví dụ | Ý nghĩa |
|---|---|---|
| `formatted` | `"12 Đường A\nQuận B\nTP. Hồ Chí Minh"` | Địa chỉ đã được định dạng để hiển thị |
| `street_address` | `"12 Đường A"` | Đường, số nhà, địa chỉ chi tiết |
| `locality` | `"Thành phố Hồ Chí Minh"` | Thành phố hoặc địa phương |
| `region` | `"Hồ Chí Minh"` | Tỉnh, bang hoặc vùng |
| `postal_code` | `"700000"` | Mã bưu chính |
| `country` | `"VN"` | Quốc gia; cách biểu diễn cụ thể phụ thuộc dữ liệu của provider |

Ví dụ phản hồi:

```json
{
  "sub": "u_314159",
  "address": {
    "formatted": "12 Đường A\nPhường B\nThành phố Hồ Chí Minh",
    "street_address": "12 Đường A",
    "locality": "Thành phố Hồ Chí Minh",
    "region": "Hồ Chí Minh",
    "postal_code": "700000",
    "country": "VN"
  }
}
```

### 6.1. Vì sao không coi `address` là một chuỗi?

Trong JSON, `address` là một object; ví dụ trong Java, dữ liệu có thể được biểu diễn bằng `Map<String, Object>`. Đọc nó như một `String` có thể gây lỗi ép kiểu hoặc bỏ sót cấu trúc.

Ngoài ra:

- `formatted` là cách trình bày thuận tiện; các thành phần chi tiết có thể thiếu hoặc khác biệt theo quốc gia.
- Địa chỉ hồ sơ không tự động là **địa chỉ giao hàng** hoặc **địa chỉ thanh toán** được người dùng chọn cho một giao dịch.
- Dữ liệu có thể cũ hoặc chỉ đúng một phần. Khi xử lý vận chuyển, xuất hóa đơn hoặc xác định nơi cư trú, nên xác nhận lại trong quy trình nghiệp vụ tương ứng.
- `address` là dữ liệu cá nhân nhạy cảm về ngữ cảnh; chỉ xin và lưu khi tính năng thực sự cần.

Không phải IdP nào cũng hỗ trợ scope `address`. Với một số hệ thống đăng nhập doanh nghiệp, thông tin địa chỉ có thể chỉ có trong directory nội bộ hoặc không được công bố qua OIDC.

## 7. Scope `phone`: số điện thoại và trạng thái xác minh

`phone` yêu cầu hai claim:

| Claim | Kiểu | Ví dụ | Diễn giải |
|---|---|---|---|
| `phone_number` | String | `"+84901234567"` | Số điện thoại, nên theo định dạng quốc tế E.164 khi provider có thể cung cấp |
| `phone_number_verified` | Boolean | `false` | Provider cho biết trạng thái đã xác minh quyền kiểm soát số điện thoại theo cơ chế của họ |

Ví dụ:

```json
{
  "sub": "u_314159",
  "phone_number": "+84901234567",
  "phone_number_verified": true
}
```

### 7.1. Có số điện thoại không đồng nghĩa với đã xác minh

Ngay cả khi `phone_number` có mặt, `phone_number_verified` vẫn có thể là `false` hoặc không được trả về. Một ứng dụng yêu cầu số điện thoại đã xác minh cần kiểm tra rõ trạng thái, thay vì chỉ kiểm tra `phone_number != null`.

Tương tự `email_verified`, việc provider từng xác minh số điện thoại không phải bằng chứng chắc chắn rằng số đó vẫn thuộc cùng người ở mọi thời điểm. Nếu số điện thoại được sử dụng để xác thực giao dịch rủi ro cao, ứng dụng có thể cần các bước xác minh hoặc chính sách bảo mật bổ sung.

### 7.2. Scope `phone` không tự cấp quyền gửi SMS hoặc thực hiện MFA

Nhận claim `phone_number` chỉ cung cấp thông tin nếu được chấp thuận; nó **không** tự cấp sự đồng ý cho mọi hoạt động liên lạc và cũng không có nghĩa provider đã tiến hành MFA bằng SMS trong phiên đăng nhập. Muốn xác định phương thức xác thực đã dùng, phải dựa vào dữ liệu xác thực mà provider cung cấp, ví dụ claim `amr` hoặc `acr` khi có và được thỏa thuận sử dụng; không suy ra từ việc đã xin scope `phone`.

## 8. ID Token và UserInfo: cùng scope nhưng claim có thể nằm ở các nơi khác nhau

Đây là một trong những điểm dễ gây hiểu nhầm nhất khi làm việc với Spring Security OIDC Client.

### 8.1. ID Token không phải bản hồ sơ đầy đủ

ID Token được dùng để **xác minh phiên xác thực và định danh chủ thể**. Provider có thể đưa thêm `name`, `email` hay claim khác vào ID Token, nhưng việc Client yêu cầu `profile email` không bảo đảm các claim này sẽ xuất hiện ở đó.

Ví dụ ID Token đã giải mã:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-782",
  "aud": "spring-web",
  "iat": 1781107200,
  "exp": 1781110800
}
```

UserInfo response có thể riêng biệt:

```json
{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true,
  "phone_number": "+84901234567",
  "phone_number_verified": false
}
```

Hai ví dụ thể hiện **cùng một chủ thể** có `sub="user-782"`. Theo OIDC, `sub` trong UserInfo response phải phù hợp với `sub` của ID Token; Client phải bảo đảm không nhầm dữ liệu của hai người dùng.

### 8.2. Khi nào Client gọi UserInfo?

Provider công bố `userinfo_endpoint` trong metadata OIDC nếu có hỗ trợ. Client có thể dùng access token nhận từ Token Endpoint để gọi endpoint này:

```http
GET /userinfo HTTP/1.1
Host: id.example.test
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
Accept: application/json
```

Phản hồi ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true
}
```

Spring Security OAuth2 Login tích hợp việc đọc thông tin OIDC và tạo `OidcUser` theo cấu hình provider. Việc có gọi UserInfo Endpoint hay không, và claim nào được lấy, phụ thuộc vào khả năng của provider và cấu hình Spring Security, không nên coi UserInfo là một lời gọi luôn bắt buộc.

Nếu có UserInfo, ứng dụng thường truy cập dữ liệu qua `OidcUser#getClaims()`; đồng thời có thể xem riêng `getIdToken()` và `getUserInfo()` để xác định nguồn claim. Trước khi xử lý `getUserInfo()`, cần xét khả năng không có dữ liệu.

### 8.3. Đã được cấp scope nhưng thiếu claim: có bình thường không?

Có. Các lý do gồm:

- Người dùng chưa từng nhập thông tin đó.
- IdP không lưu hoặc không công bố trường đó.
- Người dùng chưa chấp thuận chia sẻ trường thông tin.
- Tài khoản hoặc Client bị giới hạn bởi chính sách.
- UserInfo không được Client gọi trong cấu hình đang chạy.
- Provider trả claim trong UserInfo nhưng người lập trình chỉ nhìn ID Token.
- Scope không được cấp hoặc IdP không hỗ trợ scope đã yêu cầu.

Chính vì vậy, ứng dụng nên xử lý dữ liệu theo **giá trị thực tế nhận được**, thay vì suy luận từ danh sách scope đã gửi.

### 8.4. Claims Parameter là gì?

OIDC còn định nghĩa authorization request parameter `claims` để Client diễn đạt yêu cầu chi tiết hơn về claim trong ID Token hoặc UserInfo response, ví dụ yêu cầu một claim cụ thể là thiết yếu. Tuy nhiên, đây là một cơ chế riêng và phụ thuộc mức hỗ trợ của provider. Việc thêm scope `email` **không tương đương** với một cam kết sẽ trả `email`; ngay cả yêu cầu claims chi tiết hơn vẫn phải tuân thủ chính sách IdP và quyền của người dùng.

## 9. Cấu hình năm scope trong Spring Boot

Với ứng dụng Spring Boot dùng **Spring Security OAuth2 Client**, có thể cấu hình OIDC registration trong `application.yml` như sau:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - address
              - phone
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

Đây là địa chỉ minh họa; đổi `issuer-uri` thành issuer thực tế mà nhà cung cấp công bố. Với provider có OIDC discovery, Spring có thể lấy Authorization Endpoint, Token Endpoint, UserInfo Endpoint và thông tin khóa xác minh từ metadata. Những endpoint đó không phải chính các scope.

Các thành phần cấu hình quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `registration.company` | Tên đăng ký Client trong Spring; `company` là `registrationId` |
| `client-id` | ID Client được cấp bởi IdP |
| `client-secret` | Bí mật Client nếu dùng confidential client; lưu bằng secret manager hoặc biến môi trường |
| `scope` | Danh sách scope được yêu cầu khi bắt đầu Authorization Code Flow |
| `redirect-uri` | Callback của Spring Client sau khi IdP hoàn tất authorization request |
| `issuer-uri` | Địa chỉ issuer OIDC để kiểm tra danh tính provider và khám phá metadata |

Nếu chỉ cần đăng nhập và hiển thị tên/email, nhiều ứng dụng có thể bắt đầu bằng:

```yaml
scope:
  - openid
  - profile
  - email
```

Chỉ thêm `address` và `phone` khi đã xác định rõ tính năng dùng chúng và IdP thực sự hỗ trợ. Với nhà cung cấp không cho phép một scope nào đó, authorization request có thể thất bại với `invalid_scope` hoặc thông báo tương đương.

### 9.1. Bật OAuth2 Login trong SecurityFilterChain

Ví dụ cấu hình Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Với cấu hình mặc định, người dùng có thể bắt đầu đăng nhập thông qua:

```text
GET /oauth2/authorization/company
```

Sau khi IdP xử lý, trình duyệt quay về đường dẫn callback:

```text
GET /login/oauth2/code/company?code=...&state=...
```

Spring Security sẽ tiếp tục đổi code, xác minh token OIDC và tạo authenticated principal. Spring dùng các scope đã đăng ký khi tạo yêu cầu ủy quyền; ứng dụng **không cần tự nối** `scope=...` vào URL đăng nhập.

## 10. Đọc claim từ `OidcUser` trong Spring Security

Khi đăng nhập OIDC thành công, principal thường là một `OidcUser`. Đối tượng này cung cấp cách đọc ID Token, UserInfo và tập claim tổng hợp.

### 10.1. Ví dụ một endpoint trả thông tin tối thiểu

Ví dụ dưới đây minh họa lấy dữ liệu có chọn lọc, dùng `@AuthenticationPrincipal`. Trong hệ thống thật, chỉ trả về các trường giao diện cần và chỉ cho chính chủ tài khoản hoặc người được phân quyền xem.

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class AccountController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> response = new LinkedHashMap<>();

        // Định danh chuẩn để ánh xạ tài khoản.
        response.put("subject", user.getSubject());
        response.put("issuer", user.getIdToken().getIssuer().toString());

        putIfPresent(response, "name", user.getClaim("name"));
        putIfPresent(response, "email", user.getClaim("email"));

        // Claim xác minh có thể vắng mặt; không ép mặc định thành true.
        Object emailVerified = user.getClaim("email_verified");
        if (emailVerified instanceof Boolean) {
            response.put("emailVerified", emailVerified);
        }

        return response;
    }

    private static void putIfPresent(
            Map<String, Object> target, String name, Object value) {
        if (value != null) {
            target.put(name, value);
        }
    }
}
```

Một phản hồi ví dụ:

```json
{
  "subject": "u_314159",
  "issuer": "https://id.example.test/realms/company",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "emailVerified": true
}
```

Ví dụ tránh trả toàn bộ `user.getClaims()` vì tập dữ liệu có thể chứa ngày sinh, địa chỉ, số điện thoại hoặc các claim nhạy cảm khác không liên quan đến chức năng hiện tại.

### 10.2. Đọc `address`, `phone` và các trường xác minh

Nếu chức năng nghiệp vụ thực sự cần chúng, có thể đọc riêng từng claim:

```java
import java.util.Map;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Bên trong một method đã nhận OidcUser user từ Spring:
String phoneNumber = user.getClaimAsString("phone_number");
Boolean phoneVerified = user.getClaimAsBoolean("phone_number_verified");

Map<String, Object> address = user.getClaim("address");

if (Boolean.TRUE.equals(phoneVerified) && phoneNumber != null) {
    // Tiếp tục nghiệp vụ yêu cầu số điện thoại đã được IdP xác minh.
}

if (address != null) {
    Object city = address.get("locality");
    Object street = address.get("street_address");
    // Chỉ đọc và sử dụng các trường cần thiết; kiểm tra kiểu dữ liệu.
}
```

Ở đây `address` là một JSON object, được ví dụ dưới dạng `Map<String, Object>` do thư viện ánh xạ dữ liệu cung cấp. Với provider hoặc mapper tùy biến, ứng dụng có thể cần kiểm tra kiểu trước khi sử dụng.

Nếu muốn phân biệt claim xuất hiện trong ID Token hay trong UserInfo:

```java
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Bên trong một method đã nhận OidcUser user từ Spring:
Object emailFromIdToken = user.getIdToken().getClaim("email");

OidcUserInfo userInfo = user.getUserInfo();
Object emailFromUserInfo =
    userInfo == null ? null : userInfo.getClaim("email");
```

Đoạn này cho thấy việc **thiếu `email` trong ID Token không đồng nghĩa với thiếu `email` hoàn toàn**. Khi có UserInfo, Spring có thể tổng hợp các claim của đối tượng `OidcUser`; tuy nhiên chính sách của provider vẫn quyết định dữ liệu trả về.

### 10.3. Đọc `openid` từ cấu hình Client không phải cách kiểm tra đã xác thực

Không nên viết logic kiểu:

```java
// Không dùng danh sách scope trong cấu hình làm bằng chứng đăng nhập:
boolean loggedIn = configuredScopes.contains("openid");
```

Danh sách scope chỉ cho biết Client *dự định yêu cầu* gì. Trạng thái đăng nhập phải dựa vào `Authentication` đã được Spring Security xác minh và thiết lập trong `SecurityContext`. Tương tự, không dùng việc có `email` hoặc `phone_number` làm bằng chứng rằng người dùng sở hữu vai trò nghiệp vụ.

## 11. Scope và quyết định phân quyền là hai tầng khác nhau

Một lỗi thiết kế phổ biến là đồng nhất việc IdP trả `email` hoặc `profile` với việc ứng dụng cho phép hành động nghiệp vụ.

Xét ba nhu cầu:

| Tính năng | Dữ liệu OIDC có thể cần | Điều kiện nghiệp vụ bổ sung |
|---|---|---|
| Hiển thị lời chào trên dashboard | `openid profile`, đọc `name` nếu có | Người dùng đã đăng nhập |
| Gửi email thông báo | `openid email`, đọc `email` và cân nhắc `email_verified` | Đồng ý nhận thông báo, địa chỉ hợp lệ, chính sách liên lạc |
| Gửi đơn hàng đến một địa chỉ | `openid address` nếu provider hỗ trợ | Người dùng xác nhận địa chỉ giao hàng; quy định xử lý dữ liệu |
| Liên hệ qua số điện thoại | `openid phone` | Có số hợp lệ, mục đích sử dụng phù hợp và quyền liên hệ cần thiết |
| Truy cập chức năng quản trị | `openid` có thể đủ để xác thực danh tính | Vai trò/quyền tại hệ thống hoặc nguồn thẩm quyền đáng tin cậy |

Nếu một nhà cung cấp trả thêm claim `groups` hoặc `roles`, Client vẫn phải xác định rõ claim đó thuộc cơ chế nào, đáng tin cậy ra sao và ánh xạ nó sang `GrantedAuthority` như thế nào. Năm scope OIDC chuẩn trong bài không tự động giải quyết phân quyền chi tiết.

## 12. Nguyên tắc tối thiểu hóa dữ liệu và bảo vệ quyền riêng tư

Các scope không chỉ là tham số kỹ thuật; chúng quyết định loại dữ liệu cá nhân mà ứng dụng xin được truy cập. Cách thực hiện tốt là:

1. **Chỉ xin scope phục vụ tính năng.** Ví dụ app chỉ hiển thị tên/email không cần xin `address` và `phone` mặc định.
2. **Giải thích rõ mục đích sử dụng.** Consent và mô tả quyền truy cập phải phù hợp với hành vi sản phẩm.
3. **Chỉ lưu những claim cần lưu.** Không sao chép toàn bộ hồ sơ OIDC vào database để “phòng khi cần”.
4. **Không đưa token hoặc hồ sơ đầy đủ vào log.** Tránh log ID Token, access token, refresh token, số điện thoại và địa chỉ.
5. **Xử lý claim thiếu hoặc đã thay đổi.** Không mặc định claim sẽ luôn tồn tại hoặc giữ nguyên.
6. **Phân quyền dữ liệu theo chính chủ thể.** Endpoint trả claim cá nhân phải được bảo vệ và không để người dùng đoán URL nhằm xem dữ liệu người khác.
7. **Cân nhắc vòng đời cập nhật.** Thông tin lấy tại thời điểm đăng nhập có thể không còn mới; nếu nghiệp vụ cần dữ liệu cập nhật, xác định cơ chế làm mới phù hợp.

Đặc biệt, dữ liệu `address` và `phone_number` thường nhạy cảm hơn tên hiển thị. Không nên đưa chúng vào các response gửi cho frontend nếu giao diện không cần.

## 13. Chẩn đoán khi xin scope nhưng không nhận được thông tin

Có thể gặp các tình huống dưới đây khi tích hợp một provider thực tế.

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Đăng nhập thành công nhưng không có `email` | Thiếu scope `email`, tài khoản không có email hoặc IdP không chia sẻ email | Kiểm tra scope của authorization request và claim ở UserInfo/ID Token |
| Có `email` nhưng không có `email_verified` | Provider không trả claim xác minh | Xử lý trạng thái không rõ, xem tài liệu/chính sách IdP |
| Có `profile` nhưng không có `given_name` | Người dùng không có dữ liệu hoặc provider không công bố claim | Dùng fallback hiển thị phù hợp; không mặc định mọi trường profile đều có |
| `address` trả về object thay vì string | Đây là kiểu dữ liệu tiêu chuẩn của address claim | Đọc như object/map; kiểm tra trường con |
| Xin `phone` nhưng không có `phone_number` | Scope không được cấp, provider không hỗ trợ hoặc dữ liệu không có | Kiểm tra phạm vi được cấp và mapping UserInfo |
| Provider trả `invalid_scope` | Scope chưa được hỗ trợ hoặc Client chưa được phép xin | Xác nhận danh sách scope/consent được cấu hình tại IdP |
| ID Token không có thông tin hồ sơ | Provider cung cấp dữ liệu qua UserInfo hoặc không cấp claim tùy chọn | Kiểm tra UserInfo và cấu hình OIDC Client |
| Có email nhưng không tạo được user nội bộ | Logic đối chiếu tài khoản dựa vào email gây xung đột | Liên kết danh tính bằng `(iss, sub)` |
| Client tự nối `scope` vào URL nhưng không thấy tác dụng | Đang thao tác sai URL hoặc Spring dùng registration riêng | Kiểm tra `spring.security.oauth2.client.registration.<id>.scope` và request cuối cùng |
| `phone_number_verified=false` dù số có giá trị | IdP chưa xác minh số theo chính sách của mình | Không tự coi số điện thoại đã xác minh; xử lý theo yêu cầu nghiệp vụ |

Để khoanh vùng, đi theo thứ tự: **Client đã yêu cầu scope nào → IdP có chấp thuận không → ID Token chứa claim nào → UserInfo có được gọi và trả claim nào → ứng dụng đã đọc đúng tên/kiểu claim chưa**.

### 13.1. Tình huống thực hành: trang hồ sơ người dùng

Một ứng dụng quản lý học viên đăng nhập bằng OIDC và muốn hiển thị:

- Tên và ảnh: xin `profile`.
- Email để thông báo kết quả: xin `email`.
- Số điện thoại để hỗ trợ liên hệ: chỉ xin `phone` nếu tính năng thật sự sử dụng số này.
- Địa chỉ gửi chứng chỉ giấy: chỉ xin `address` nếu sản phẩm có gửi chứng chỉ; luôn cho người dùng kiểm tra lại địa chỉ.

Tập scope có thể bắt đầu từ:

```text
openid profile email
```

Khi người dùng chọn tính năng cần địa chỉ hoặc số điện thoại, tùy khả năng IdP và kiến trúc sản phẩm, ứng dụng có thể cần mở rộng yêu cầu quyền, thực hiện một luồng consent bổ sung hoặc thu thập dữ liệu trực tiếp theo chính sách. Không nên mặc định xin mọi thông tin cá nhân ngay từ màn hình đăng nhập đầu tiên.

## 14. Những nhầm lẫn cần tránh

**“Thêm `scope=profile` chắc chắn ID Token có `name`.”** Không đúng. Scope yêu cầu một tập claim; claim thực tế phụ thuộc provider và có thể ở UserInfo hoặc không được trả về.

**“`email_verified=true` nghĩa là được phép đăng nhập vào mọi hệ thống có domain email đó.”** Không đúng. Tín hiệu xác minh email không thay thế quyết định quyền truy cập nội bộ.

**“Scope `phone` nghĩa là OTP/MFA đã hoàn thành.”** Không đúng. Scope yêu cầu thông tin số điện thoại, còn thông tin phương thức xác thực là phạm vi khác.

**“`address` là một chuỗi địa chỉ.”** Không chính xác theo mô hình OIDC chuẩn; đó là một object gồm các trường như `formatted`, `street_address` và `locality`.

**“Nếu user có email thì có thể dùng email thay cho `sub`.”** Không nên. Email có thể thay đổi; cặp `(iss, sub)` mới là định danh OIDC thích hợp để liên kết tài khoản theo issuer.

**“Spring phải tự gọi UserInfo bằng RestTemplate/WebClient mỗi lần đăng nhập.”** Không nhất thiết. `oauth2Login` có hỗ trợ OIDC UserInfo trong hạ tầng Spring Security. Cấu hình provider và cơ chế xử lý người dùng quyết định cách nhận claim.

**“Thêm `address` và `phone` vào YAML là IdP bắt buộc trả dữ liệu.”** Không đúng. Provider có thể không hỗ trợ scope, yêu cầu phê duyệt quyền hoặc không có dữ liệu cho tài khoản đó.

## 15. Tổng kết kiến thức cần ghi nhớ

- `openid` là scope cốt lõi để bắt đầu **xác thực OIDC** và nhận ID Token theo flow phù hợp.
- `profile` yêu cầu các claim hồ sơ như `name`, `picture`, `locale`; `email` yêu cầu `email` và `email_verified`.
- `address` yêu cầu claim `address` dạng object; `phone` yêu cầu `phone_number` và `phone_number_verified`.
- **Yêu cầu scope ≠ được cấp scope ≠ chắc chắn nhận claim**. Ứng dụng phải xử lý claim thiếu hoặc không hợp lệ.
- Claim hồ sơ có thể nằm ở **ID Token, UserInfo hoặc cả hai**. Với Spring Security, `OidcUser` cung cấp cách truy cập các nguồn dữ liệu này.
- Dùng `(iss, sub)` để định danh OIDC, không dùng tên hiển thị, email hoặc số điện thoại làm khóa danh tính.
- Các scope tiêu chuẩn không thay thế **phân quyền ứng dụng**, xác minh dữ liệu cho nghiệp vụ và chính sách bảo vệ thông tin cá nhân.
- Trong Spring Boot, cấu hình scope tại `spring.security.oauth2.client.registration.<registrationId>.scope` và bật `oauth2Login` để Spring thực hiện flow đăng nhập.

## 16. Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Standard Claims và Requesting Claims using Scope Values](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims): danh sách claim tiêu chuẩn, `openid`, `profile`, `email`, `address`, `phone` và quy tắc yêu cầu claim.
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): các claim giao thức và yêu cầu xác minh ID Token.
- [OpenID Connect Core 1.0 — UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo): sử dụng access token để yêu cầu thông tin người dùng.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): khái niệm `scope`, authorization request, token response và phạm vi được cấp.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration`, `oauth2Login` và tích hợp OpenID Connect trong ứng dụng Servlet.
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/OidcUser.html): cách truy cập ID Token, UserInfo và các claim trong principal OIDC.
