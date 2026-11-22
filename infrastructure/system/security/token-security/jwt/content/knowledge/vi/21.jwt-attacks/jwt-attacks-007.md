# Nhầm issuer, audience hoặc loại token giữa các luồng

## 1. Vì sao nhầm issuer, audience và token type nguy hiểm?

Một JSON Web Token (JWT) có thể có chữ ký hợp lệ nhưng vẫn không phù hợp với API hoặc luồng đang nhận nó. Chữ ký chỉ chứng minh token được tạo bởi bên sở hữu khóa ký tương ứng và nội dung chưa bị thay đổi. Nó không tự chứng minh:

- Token được phát hành bởi đúng issuer mà API tin cậy.
- Token được dành cho đúng resource server đang nhận request.
- Token thuộc đúng loại và mục đích sử dụng.
- Token được cấp trong đúng authorization flow.
- Các claims trong token có ngữ nghĩa phù hợp với quyết định mà API đang thực hiện.

Một lỗi phổ biến là dùng một bộ xác minh JWT tổng quát cho nhiều loại token hoặc nhiều issuer, rồi chỉ kiểm tra chữ ký và thời hạn. Kẻ tấn công có thể tận dụng sự khác nhau giữa các luồng để đưa một token hợp lệ ở ngữ cảnh A sang ngữ cảnh B.

Ví dụ:

~~~text
OpenID Provider phát hành ID Token cho Web Client.
OAuth Authorization Server phát hành Access Token cho Billing API.
Một dịch vụ nhận JWT nhưng không phân biệt hai loại token.

Attacker gửi ID Token tới Billing API.
Billing API chỉ kiểm tra chữ ký và exp.
Billing API chấp nhận ID Token như Access Token.
~~~

Đây là **cross-JWT confusion** hoặc token-type confusion. Tương tự, một token dành cho API A có thể bị gửi tới API B nếu B không kiểm tra audience; token từ issuer không được tin có thể bị chấp nhận nếu API dùng nhầm key set hoặc so khớp issuer lỏng lẻo.

Nguyên tắc cốt lõi:

> **Xác minh JWT phải gắn với một issuer, audience và token profile cụ thể. Chữ ký hợp lệ không làm token trở nên hợp lệ cho mọi luồng.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), OAuth 2.0 và OpenID Connect (OIDC). Các nguyên tắc áp dụng cho client, API Gateway, Authorization Server và resource server, không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Phân biệt issuer, audience và token type

Ba khái niệm này trả lời ba câu hỏi khác nhau.

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Issuer (iss)** | Ai phát hành token và chịu trách nhiệm cho claims? | https://identity.example.test |
| **Audience (aud)** | Token được dành cho bên nhận/resource server nào? | https://api.example.test/billing |
| **Token type/profile** | Token thuộc loại nào và phải được xác minh theo quy tắc nào? | JWT access token theo RFC 9068, OIDC ID Token, DPoP proof. |

Các claim/header khác cũng có vai trò riêng:

- **sub:** subject mà token đại diện; subject thường chỉ duy nhất trong phạm vi issuer.
- **client_id:** client OAuth được gắn với token theo profile.
- **azp:** authorized party trong OIDC ID Token; không thay thế audience.
- **scope:** quyền hoặc phạm vi hành động được cấp theo hợp đồng; không thay thế audience.
- **typ:** JOSE header parameter dùng để biểu thị loại nội dung JWT theo profile.
- **exp, nbf, iat:** các mốc thời gian liên quan đến hiệu lực và thời điểm phát hành.

Không được dùng một trường để thay thế trường khác. Ví dụ, scope invoice:read không chứng minh token dành cho Billing API; issuer đúng không chứng minh token được phát hành cho đúng client hoặc resource server.

## 3. Issuer confusion: chấp nhận token từ sai nguồn phát hành

Issuer confusion xảy ra khi resource server không ràng buộc token với đúng issuer hoặc lấy nhầm khóa của issuer khác.

### 3.1. Cùng subject không có nghĩa cùng danh tính

Hai Identity Provider có thể cùng phát hành:

~~~json
{
  "iss": "https://idp-a.example.test",
  "sub": "user-100"
}
~~~

và:

~~~json
{
  "iss": "https://idp-b.example.test",
  "sub": "user-100"
}
~~~

Hai token này đại diện cho hai subject trong hai không gian định danh khác nhau. Không nên chỉ dùng sub để ánh xạ tài khoản nội bộ. Khóa định danh thường phải là cặp (iss, sub), hoặc một mapping đã được quản lý có thẩm quyền.

Nếu API bỏ qua iss, một token từ issuer B có thể bị hiểu nhầm là token của user-100 thuộc issuer A.

### 3.2. Chấp nhận issuer bất kỳ vì chữ ký hợp lệ

Một hệ thống có thể tin nhiều issuer, nhưng phải có registry/configuration xác định rõ các issuer đó. Nếu verifier chấp nhận token từ bất kỳ issuer nào có thể tìm được public key, attacker có thể tự vận hành issuer của họ, ký token với subject hoặc role tùy ý rồi gửi tới API.

Không được coi một chữ ký hợp lệ bằng một public key bất kỳ trong hệ thống là đủ. Khóa phải được liên kết với issuer dự kiến theo trust configuration.

### 3.3. So khớp issuer bằng prefix hoặc domain suffix

Giả sử API mong đợi:

~~~text
https://identity.example.test
~~~

Các giá trị sau không phải cùng issuer:

~~~text
https://identity.example.test.attacker.example
https://identity.example.test/other-tenant
https://attacker.example/identity.example.test
~~~

So khớp bằng contains, prefix, hostname suffix hoặc domain gốc có thể khiến issuer giả được chấp nhận.

Verifier cần so khớp issuer identifier chính xác theo hợp đồng và đặc tả áp dụng. Không tự ý bỏ path, đổi hostname alias hoặc bỏ dấu slash để làm hai issuer khác nhau trở thành một.

### 3.4. Lấy issuer từ token chưa xác minh

Payload JWT có thể được giải mã trước khi xác minh chữ ký. Vì vậy, claim iss ở giai đoạn này chỉ là dữ liệu chưa tin cậy.

Nếu server dùng iss chưa xác minh để tự động:

- Fetch Discovery metadata.
- Tải JWKS từ URL do attacker kiểm soát.
- Thêm issuer mới vào trust registry.
- Chọn một tenant hoặc tài khoản mà không kiểm tra mapping.

thì attacker có thể gây SSRF hoặc đưa khóa của họ vào đường xác minh.

Nếu cần chọn issuer động, chỉ dùng giá trị iss chưa xác minh như một khóa tra cứu chính xác trong registry allowlist đã được quản lý. Không biến nó thành URL outbound tự do. Metadata và JWKS phải được lấy theo trust bootstrap của issuer đã đăng ký.

### 3.5. Key lookup phải gắn với issuer

Hai issuer có thể cùng dùng kid = key-01. Không tra cứu kid trong một key set toàn cục rồi dùng khóa đầu tiên khớp.

Khóa cần được chọn trong ngữ cảnh:

~~~text
trusted issuer
    + issuer-specific JWKS
    + kid
    + allowed algorithm and key type
    + token profile
~~~

Nếu chữ ký được xác minh bằng khóa của issuer A, claim iss vẫn phải khớp chính xác issuer A. Không dùng việc chữ ký hợp lệ để bỏ qua issuer validation.

## 4. Audience confusion: dùng token cho sai resource server

Audience confusion xảy ra khi token được phát hành cho một recipient nhưng lại được chấp nhận ở recipient khác.

Ví dụ access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "scope": "invoice:read",
  "exp": 1900003600
}
~~~

Token này được dành cho Billing API. Nếu Documents API nhận token và chỉ kiểm tra chữ ký, issuer và exp mà bỏ qua aud, nó có thể chấp nhận token không dành cho mình.

### 4.1. Audience là recipient, không phải scope

~~~text
aud = API nào được phép nhận token?
scope = client/subject được cấp quyền yêu cầu hành động nào?
~~~

Một token có scope document:read nhưng audience chỉ là Billing API không tự động được dùng tại Documents API. Tương tự, audience đúng không tự cấp quyền document:read nếu token không có scope hoặc policy tương ứng.

### 4.2. Không so khớp audience bằng prefix

Nếu API mong đợi:

~~~text
https://api.example.test/billing
~~~

thì không chấp nhận các audience chỉ vì chúng có cùng hostname hoặc bắt đầu bằng chuỗi đó:

~~~text
https://api.example.test/billing-admin
https://api.example.test
https://api.example.test/billing/other
~~~

Verifier phải áp dụng phép so khớp audience theo profile và cấu hình chính xác. Không dùng substring, prefix hoặc so khớp domain gốc.

### 4.3. aud có thể là string hoặc array

Theo JWT, aud có thể là một StringOrURI hoặc một mảng các giá trị. Vì vậy, verifier cần xử lý đúng cả hai dạng theo profile.

Ví dụ:

~~~json
{
  "aud": [
    "https://api.example.test/billing",
    "https://api.example.test/reports"
  ]
}
~~~

Một resource server chỉ được chấp nhận token nếu identifier của chính nó nằm trong audience theo đúng quy tắc của profile. Nếu token có nhiều audience, các recipient phải được chủ đích cho phép; không nên phát hành audience rộng chỉ để tránh phải token exchange.

Một số profile hoặc hệ thống có thể yêu cầu một audience duy nhất. Khi đó verifier phải thực thi quy tắc chặt hơn của profile, thay vì mặc định mọi mảng audience đều được phép.

### 4.4. Token cho Gateway không tự dành cho backend

Giả sử client nhận token có audience là API Gateway. Gateway chuyển nguyên token đến Billing API. Billing API không nên chấp nhận token nếu audience không dành cho Billing API. Gateway là một recipient khác với backend.

Các cách xử lý:

- Cấp token có audience đúng cho backend theo thiết kế.
- Dùng OAuth Token Exchange để lấy token mới dành cho downstream.
- Gateway xác minh token và chuyển một assertion nội bộ theo hợp đồng tin cậy rõ ràng, với backend chỉ nhận từ Gateway đã xác thực.

Không bỏ qua audience chỉ vì request đã đi qua một proxy nội bộ.

### 4.5. ID Token và Access Token có audience khác nhau

Trong OIDC:

- ID Token có audience là client OIDC, thường là client_id của ứng dụng đã thực hiện đăng nhập.
- Access Token có audience là resource server hoặc resource được token hướng tới.

Một ID Token có aud chứa client_id không có nghĩa nó được dành cho API nghiệp vụ. API không được chấp nhận ID Token chỉ vì issuer và chữ ký đúng.

## 5. Token-type confusion và Cross-JWT Confusion

Token-type confusion xảy ra khi một JWT được phát hành cho mục đích này bị sử dụng như một loại token khác. RFC 8725 gọi đây là một rủi ro cross-JWT confusion và khuyến nghị explicit typing cùng các quy tắc xác minh loại trừ lẫn nhau.

### 5.1. ID Token bị dùng như Access Token

ID Token được OpenID Provider phát hành cho client để truyền đạt kết quả xác thực người dùng. Nó không phải access token dành cho resource server.

Ví dụ:

~~~text
ID Token:
    iss = OpenID Provider
    aud = web-client-123
    sub = user-514

API:
    expected audience = billing-api
~~~

Nếu Billing API chỉ xác minh chữ ký và exp, nó có thể chấp nhận ID Token và coi user-514 đã được phép gọi API. Đây là lỗi nghiêm trọng vì API đã nhầm bằng chứng đăng nhập dành cho client với credential truy cập resource.

Biện pháp:

- API chỉ chấp nhận access token theo profile được cấu hình.
- Kiểm tra audience là resource server hiện tại.
- Dùng validation rules riêng cho ID Token và access token.
- Nếu dùng JWT access token theo RFC 9068, yêu cầu typ phù hợp, chẳng hạn at+jwt.
- Không dùng ID Token làm Bearer credential tới API.

### 5.2. Access Token bị dùng như ID Token

Chiều ngược lại cũng nguy hiểm. Một client OIDC không nên coi bất kỳ JWT có chữ ký hợp lệ từ cùng issuer là ID Token.

ID Token có các yêu cầu riêng như audience dành cho client, thời điểm xác thực và nonce nếu được gửi trong authentication request. Access token có thể có subject và issuer giống nhưng không mang ý nghĩa xác thực đăng nhập theo OIDC.

Client phải xác minh ID Token theo OIDC Core, gồm issuer, audience, chữ ký, thời gian và nonce khi áp dụng. Không dùng một hàm xác minh access token chung để xác minh ID Token.

### 5.3. Refresh Token bị dùng như Access Token

Refresh token chỉ được gửi tới Authorization Server/token endpoint để lấy token mới. Nó không phải credential gọi resource API.

Nếu refresh token là JWT và resource server chỉ kiểm tra chữ ký, issuer và exp, nó có thể vô tình chấp nhận refresh token. Nếu refresh token opaque, API có thể vẫn mắc lỗi nếu coi bất kỳ chuỗi credential nào là access token mà không xác định profile.

Biện pháp:

- Resource server chỉ chấp nhận access token theo đúng profile.
- Token endpoint chỉ chấp nhận refresh token trong refresh grant và theo client/grant binding.
- Dùng audience và token type tách biệt.
- Không chia sẻ validator tổng quát cho mọi loại token.

### 5.4. Client Assertion bị dùng như Access Token

OAuth client assertion là JWT được client gửi tới Authorization Server để xác thực client hoặc thực hiện một mục đích giao thức cụ thể. Nó không phải access token dành cho resource server.

Một client assertion có thể có issuer/subject là client_id và audience là token endpoint. Nếu API chấp nhận nó như access token vì chữ ký hợp lệ, API đã nhầm credential xác thực client với quyền truy cập resource.

Validator của client assertion cần kiểm tra audience token endpoint, issuer/subject/client binding, thời hạn và các yêu cầu replay theo profile. Resource server phải từ chối loại token này.

### 5.5. DPoP Proof bị dùng như Access Token

DPoP proof là JWT ngắn hạn chứng minh quyền sở hữu private key cho một request. Nó có typ dpop+jwt và claims như htm, htu, iat, jti, cùng ath khi gắn với access token.

Proof không đại diện cho grant hoặc scope truy cập API. Resource server không được chấp nhận DPoP proof như access token. Khi sử dụng DPoP-bound access token, server phải xác minh cả access token và proof, đồng thời so khớp key binding.

### 5.6. Logout Token hoặc JWT nghiệp vụ bị dùng sai mục đích

OIDC Back-Channel Logout Token có profile và claims riêng, chẳng hạn events, sid hoặc sub, cùng yêu cầu về issuer, audience, thời gian và jti. Nó được gửi tới logout endpoint để thông báo logout, không phải để gọi API nghiệp vụ.

Tương tự, JWT dùng cho password reset, email verification, invitation, request object hoặc client authentication không tự trở thành access token. Mỗi mục đích cần validator và endpoint riêng.

## 6. Explicit typing: dùng typ để phân biệt JWT

RFC 8725 khuyến nghị explicit typing để giảm nguy cơ một JWT được hiểu nhầm thành loại khác. JOSE header parameter typ có thể cho biết media type hoặc loại JWT.

Ví dụ:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "access-signing-key-01"
}
~~~

Với JWT access token theo RFC 9068, typ được đặt là at+jwt. DPoP proof theo RFC 9449 dùng typ dpop+jwt.

### 6.1. typ giúp gì?

Verifier có thể từ chối ngay những JWT không có loại nội dung mà endpoint mong đợi. Điều này làm rõ hợp đồng giữa issuer và recipient.

Ví dụ:

~~~text
Billing API:
    expected token profile = OAuth JWT Access Token
    expected typ = at+jwt

DPoP verifier:
    expected proof typ = dpop+jwt
~~~

### 6.2. typ không thay thế validation rules

JOSE header chưa được xác minh trước khi chữ ký hợp lệ. Vì vậy, typ chỉ là dữ liệu chưa tin cậy trong bước đầu. Sau khi xác minh chữ ký theo issuer/key được tin cậy, verifier vẫn phải xác nhận typ đúng profile.

Không chấp nhận token chỉ vì header tự khai báo typ = at+jwt. Kẻ tấn công có thể tự viết header đó.

### 6.3. Không phải mọi JWT profile đều có typ giống nhau

OIDC ID Token không nên bị giả định có cùng typ với JWT access token. Một số profile có quy tắc typ riêng; một số loại JWT cũ hoặc ứng dụng riêng có thể không có typ. Cần tuân thủ đặc tả của từng profile và thiết kế các quy tắc xác minh loại trừ lẫn nhau.

Không tự thêm quy tắc chung như “mọi JWT phải có typ = JWT” rồi coi đó là đủ phân biệt access token, ID Token và token nghiệp vụ.

### 6.4. Phân biệt typ và cty

- typ mô tả loại nội dung JWT trong JOSE header.
- cty mô tả content type của nội dung được bảo vệ bên trong, thường liên quan nested JWT/JWE.

Không dùng cty thay typ để phân biệt access token với ID Token.

## 7. Mutually exclusive validation rules

RFC 8725 khuyến nghị mỗi loại JWT có bộ quy tắc xác minh riêng biệt để một token hợp lệ ở profile này không thể vượt qua validator của profile khác.

Đây là nguyên tắc **mutually exclusive validation rules**.

Ví dụ các validator:

| Loại token | Issuer | Audience | Header/type | Claims hoặc kiểm tra riêng |
| --- | --- | --- | --- | --- |
| OIDC ID Token | OpenID Provider | OIDC client_id | Theo OIDC/JWT profile; không coi là at+jwt | nonce khi áp dụng, auth_time nếu yêu cầu, azp khi cần. |
| JWT Access Token | Authorization Server | Resource server | at+jwt theo RFC 9068 | sub, client_id, iat, jti, exp và scope/claims theo profile. |
| DPoP Proof | Client tạo proof | Không dùng aud access-token như ID | dpop+jwt | htm, htu, iat, jti, jwk, ath/nonce theo ngữ cảnh. |
| Client Assertion | Client hoặc issuer client | Token endpoint/AS theo profile | Profile assertion tương ứng | client binding, thời hạn ngắn, jti/replay policy. |
| Logout Token | OpenID Provider | Relying Party/client | Logout Token profile | events, sid hoặc sub, jti, yêu cầu nonce khác ID Token. |

Các cột là mô tả khái quát. Mỗi profile có yêu cầu chi tiết riêng; phải triển khai theo đúng đặc tả chứ không dùng bảng này thay cho chuẩn.

### 7.1. Validator riêng theo mục đích

Thiết kế API nên thể hiện rõ mục đích:

~~~text
validateOidcIdToken(...)
validateJwtAccessTokenForBilling(...)
validateDpopProof(...)
validateOAuthClientAssertion(...)
validateOidcLogoutToken(...)
~~~

Các hàm trên là tên khái niệm, không phải API của một thư viện cụ thể. Mục tiêu là không có một hàm kiểu validateAnyJwt() trả về principal cho mọi endpoint.

### 7.2. Các quy tắc phải khác nhau đủ để loại trừ

Tùy profile, sự khác biệt có thể gồm:

- Issuer hoặc trust domain khác nhau.
- Audience khác nhau.
- typ khác nhau.
- Required claims khác nhau.
- Token lifetime khác nhau.
- Cách kiểm tra nonce hoặc jti khác nhau.
- Key set hoặc signing profile riêng.
- Quy tắc subject/client binding khác nhau.

Chỉ khác tên hàm mà dùng cùng một bộ điều kiện lỏng không tạo ra mutually exclusive validation.

### 7.3. Dedicated signing keys là defense-in-depth

Issuer có thể dùng key pair riêng cho ID Token, access token và token nghiệp vụ. Điều này giúp giảm nguy cơ một token ký bằng cùng khóa bị nhầm giữa nhiều profile.

Tuy nhiên, dùng khóa riêng không thay thế kiểm tra issuer, audience, typ và claims. Nếu verifier vẫn chấp nhận sai profile, lỗi logic vẫn tồn tại.

## 8. OIDC ID Token và OAuth JWT Access Token: khác nhau ở đâu?

Hai loại token có thể cùng là JWT, cùng được ký bởi một hệ thống và cùng chứa iss/sub/exp. Nhưng chúng có mục đích khác nhau.

### 8.1. ID Token

ID Token truyền đạt thông tin xác thực người dùng cho OIDC client. Ví dụ payload:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "web-client-123",
  "exp": 1900003600,
  "iat": 1900000000,
  "nonce": "client-request-nonce"
}
~~~

Client phải xác minh token theo OIDC Core. Audience phải bao gồm client_id của chính client. Nếu có nonce trong authentication request, client phải kiểm tra nonce tương ứng. Các quy tắc khác như azp và auth_time được áp dụng theo trường hợp OIDC.

### 8.2. JWT Access Token

JWT access token theo RFC 9068 dành cho resource server:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "client_id": "web-client-123",
  "iat": 1900000000,
  "exp": 1900000300,
  "jti": "access-token-id-901",
  "scope": "invoice:read"
}
~~~

Header của token theo profile RFC 9068 có typ at+jwt. Resource server kiểm tra issuer, audience, chữ ký, thời hạn, token profile và authorization.

### 8.3. Không dùng nonce như scope

OIDC nonce gắn authentication request với ID Token và giúp phát hiện một số kiểu replay/substitution trong OIDC flow. Nó không phải permission và không thay thế scope của access token.

### 8.4. azp không thay thế aud

azp biểu thị authorized party trong OIDC ID Token. Khi có nhiều audience, client có các quy tắc kiểm tra azp theo OIDC Core. Không dùng azp như một cách thay thế kiểm tra audience và không giả định mọi access token đều có azp.

## 9. OAuth Authorization Server mix-up

Trong một số client, người dùng có thể đăng nhập qua nhiều Authorization Server. Nếu client không gắn đúng authorization response với issuer đã khởi tạo request, attacker có thể lợi dụng sự nhầm lẫn để làm client gửi authorization code tới token endpoint sai.

Đây là nhóm **authorization server mix-up attack**. Nó liên quan đến việc client phân biệt issuer trong một authorization flow, không chỉ việc API xác minh claim iss trong access token.

### 9.1. Kịch bản khái quát

~~~text
Client hỗ trợ Authorization Server A và B.
Client bắt đầu flow với A.
Attacker tạo tình huống khiến response từ B xuất hiện ở transaction mà client nghĩ là A.
Client gửi code tới token endpoint không tương ứng.
Code hoặc token có thể bị lộ/đổi ngữ cảnh tùy kiến trúc.
~~~

### 9.2. Ràng buộc response với đúng issuer

RFC 9207 định nghĩa Authorization Server Issuer Identification trong Authorization Response, sử dụng tham số iss để client xác định Authorization Server đã tạo response.

Client cần:

- Lưu issuer đã chọn khi khởi tạo transaction.
- Xác minh tham số iss trong response khi Authorization Server hỗ trợ cơ chế này.
- Từ chối response có issuer không khớp transaction.
- Gửi authorization code tới token endpoint của đúng issuer.
- Bảo vệ transaction bằng state và PKCE theo flow.

Một số kiến trúc còn dùng redirect URI riêng cho từng issuer để tăng khả năng phân biệt. Cần áp dụng đúng hướng dẫn OAuth Security BCP và profile đang dùng.

### 9.3. state và PKCE không làm mất nhu cầu xác định issuer

state giúp liên kết response với client transaction và chống CSRF theo thiết kế. PKCE ràng buộc authorization code với code verifier. Chúng rất quan trọng nhưng không nên được coi là lý do để bỏ qua issuer identification trong multi-issuer flow.

Client phải xác định rõ response thuộc Authorization Server nào trước khi trao đổi code.

## 10. Token substitution giữa môi trường và tenant

Issuer/audience confusion không chỉ xảy ra giữa các sản phẩm. Nó cũng xảy ra giữa development, staging, production hoặc các tenant.

Ví dụ:

~~~text
Development issuer:
https://id.dev.example.test

Production issuer:
https://id.example.test

Production API:
https://api.example.test/payments
~~~

Không để production API tin issuer development chỉ vì cùng tổ chức hoặc cùng signing key. Token test có thể được phát hành với dữ liệu và quyền yếu hơn, hoặc khóa test có thể được nhiều người biết.

Tương tự, token của tenant A không tự dùng được ở tenant B. Tenant claim phải được đối chiếu với membership và resource thực tế. Không chỉ kiểm tra tenant do client gửi trong URL.

## 11. Những nguyên nhân thiết kế tạo ra token confusion

### 11.1. Một validator dùng cho mọi JWT

Hàm chung chỉ kiểm tra:

~~~text
signature valid
AND exp not passed
~~~

không đủ để phân biệt token loại nào, do ai phát hành và dành cho ai.

### 11.2. Cùng signing key cho nhiều loại token nhưng thiếu profile validation

Một issuer có thể ký ID Token, access token và token nghiệp vụ bằng cùng một key set. Điều này không tự động sai, nhưng làm tăng yêu cầu phải kiểm tra audience, typ và claims riêng biệt.

### 11.3. Audience quá rộng

Nếu một token được phát hành cho nhiều API mà không có lý do rõ ràng, token bị lộ ở một nơi có thể được sử dụng ở nơi khác. Dùng audience hẹp hoặc token exchange cho downstream giúp giới hạn phạm vi.

### 11.4. Bỏ qua claim vì nghĩ chữ ký đã đủ

Chữ ký không kiểm tra ngữ nghĩa. Một ID Token có chữ ký đúng vẫn không phải access token. Một access token cho Billing API có chữ ký đúng vẫn không phải token cho Documents API.

### 11.5. Không ràng buộc transaction với issuer

Client multi-issuer không lưu issuer đã chọn hoặc không kiểm tra response issuer có thể gửi code/token sai endpoint.

## 12. Pipeline xác minh JWT chống issuer/audience/type confusion

Một pipeline rõ ràng nên xác định profile trước khi chấp nhận token.

~~~mermaid
flowchart TD
    A["Request đến endpoint"] --> B["Endpoint xác định token profile cần nhận"]
    B --> C["Chọn issuer từ trust registry/config"]
    C --> D["Lấy key set gắn với issuer"]
    D --> E["Parse JOSE header như dữ liệu chưa tin cậy"]
    E --> F["Kiểm tra alg/kid/type theo allowlist"]
    F --> G["Xác minh chữ ký"]
    G --> H["So khớp iss chính xác"]
    H --> I["So khớp aud với recipient"]
    I --> J["Kiểm tra typ và profile-specific claims"]
    J --> K["Kiểm tra thời gian và trạng thái cần thiết"]
    K --> L["Authorization: scope, tenant, resource, action"]
    L --> M["Cho phép hoặc từ chối"]
~~~

### 12.1. Xác định loại token theo endpoint

Endpoint cần biết nó nhận loại token nào. Ví dụ:

- Resource API nhận OAuth access token.
- OIDC callback xử lý ID Token.
- Token endpoint xử lý refresh token hoặc client assertion theo grant.
- DPoP verifier xử lý proof JWT cùng access token.
- Logout endpoint xử lý logout token.

Không để request tự chọn validator bằng một claim chưa xác minh rồi dùng validator đó mà không ràng buộc endpoint.

### 12.2. Chọn issuer và key set

Issuer phải nằm trong trust registry. Key set phải được liên kết với issuer. Không lấy khóa từ jku/x5u hoặc URL do token tự cung cấp nếu không có một trust profile được phê duyệt.

### 12.3. Xác minh chữ ký và thuật toán

Chỉ chấp nhận thuật toán nằm trong allowlist của issuer/profile. Không để header alg tự quyết định chính sách. Key type, use, key_ops và kích thước khóa phải tương thích.

### 12.4. Kiểm tra iss và aud

So khớp issuer với định danh dự kiến. So khớp audience với recipient hiện tại theo profile. Không bỏ qua hai bước này chỉ vì chữ ký hợp lệ.

### 12.5. Kiểm tra typ và claims riêng

Với access token profile RFC 9068, kiểm tra typ at+jwt và các claims bắt buộc. Với DPoP proof, kiểm tra typ dpop+jwt và các claim proof. Với ID Token, áp dụng OIDC Core. Với các JWT khác, dùng profile tương ứng.

### 12.6. Authorization sau authentication

Token hợp lệ vẫn cần được đánh giá scope, tenant, ownership, relationship, action và trạng thái resource. Issuer/audience/type validation chỉ xác định token có thể được dùng trong luồng hiện tại; nó không thay thế object-level authorization.

## 13. Pseudocode: validator riêng cho access token

~~~text
function validateBillingAccessToken(compactJwt):
    expectedIssuer = trustedIssuerRegistry.exactLookupFor("billing-api")
    if expectedIssuer is null:
        return REJECT

    header = parseUntrustedJoseHeader(compactJwt)
    if header.alg not in billingAccessTokenAlgorithms:
        return REJECT
    if header.typ != "at+jwt":
        return REJECT

    key = findKey(
        issuer = expectedIssuer,
        kid = header.kid,
        purpose = "signature-verification"
    )
    if key is null:
        return REJECT

    if not verifyJwtSignature(compactJwt, key, header.alg):
        return REJECT

    claims = parseVerifiedClaims(compactJwt)
    if claims.iss != expectedIssuer:
        return REJECT
    if not exactAudienceMatch(
        claims.aud,
        "https://api.example.test/billing"
    ):
        return REJECT
    if claims.exp <= now:
        return REJECT
    if claims.nbf exists and claims.nbf > now + allowedClockSkew:
        return REJECT
    if not hasRequiredAccessTokenClaims(claims):
        return REJECT

    return VERIFIED_ACCESS_TOKEN(claims)
~~~

Đây là pseudocode minh họa. Trong thực tế, JOSE header chưa được xác minh nên chỉ được dùng để chọn ứng viên trong policy cố định; chữ ký phải được xác minh trước khi tin claims. Profile RFC 9068 còn có các yêu cầu cụ thể về issuer, audience, claims và thuật toán cần được triển khai đầy đủ.

## 14. Pseudocode: xác minh OIDC ID Token

~~~text
function validateOidcIdToken(compactJwt, authTransaction):
    expectedIssuer = authTransaction.expectedIssuer
    expectedClientId = authTransaction.clientId

    key = findTrustedOidcSigningKey(
        issuer = expectedIssuer,
        untrustedHeader = parseUntrustedJoseHeader(compactJwt)
    )
    if key is null:
        return REJECT

    if not verifyOidcIdTokenSignature(compactJwt, key):
        return REJECT

    claims = parseVerifiedClaims(compactJwt)
    if claims.iss != expectedIssuer:
        return REJECT
    if expectedClientId not in normalizeAudience(claims.aud):
        return REJECT
    if claims.exp <= now or claims.iat > now + allowedClockSkew:
        return REJECT
    if authTransaction.sentNonce and claims.nonce != authTransaction.nonce:
        return REJECT
    if claims.azp exists and claims.azp != expectedClientId:
        return REJECT

    return VERIFIED_ID_TOKEN(claims)
~~~

Đây là ví dụ rút gọn, không phải toàn bộ OIDC Core validation. Tùy flow, client còn phải kiểm tra các điều kiện như auth_time, max_age, at_hash, c_hash, thuật toán, audience nhiều giá trị và các yêu cầu khác của profile.

## 15. Bảng tình huống tấn công và phòng vệ

| Tình huống | Lỗi xác minh | Phòng vệ chính |
| --- | --- | --- |
| Token từ issuer attacker | Không kiểm tra iss hoặc tin issuer bất kỳ. | Trust registry và exact issuer match. |
| Cùng sub từ hai issuer | Dùng sub làm ID toàn cục. | Principal key theo (iss, sub) hoặc mapping có thẩm quyền. |
| Token cho API A tới API B | Bỏ qua aud. | Audience check theo resource server. |
| ID Token tới resource API | Dùng validator JWT chung. | Access-token profile và audience riêng. |
| Access Token tới OIDC callback | Không áp dụng ID Token validation. | OIDC Core validation riêng. |
| Refresh Token tới resource API | Không phân biệt grant/token purpose. | Chỉ chấp nhận access token tại resource server. |
| Client Assertion tới API | Coi JWT client credential là access token. | Audience/token endpoint và assertion profile riêng. |
| DPoP proof tới API như access token | Chỉ xác minh chữ ký proof. | Xác minh access token và DPoP proof riêng. |
| Token Gateway tới backend | Backend không kiểm tra aud. | Token audience backend hoặc token exchange. |
| Token dev tới production | Dùng chung trust/key không phân tách môi trường. | Issuer, audience và key configuration tách biệt. |
| OAuth AS mix-up | Không ràng buộc response với issuer đã chọn. | RFC 9207 issuer identification, state, PKCE và transaction binding. |
| Token có nhiều aud ngoài dự kiến | Chấp nhận mọi audience array. | Profile-specific audience policy và token audience hẹp. |

## 16. Kiểm thử chống issuer, audience và token-type confusion

Kiểm thử nên dùng token được ký hợp lệ cho một ngữ cảnh khác, vì token sai chữ ký thường chỉ chứng minh signature validation hoạt động chứ không chứng minh API phân biệt đúng profile.

### 16.1. Issuer tests

- Token có iss đúng và chữ ký từ key của issuer tin cậy.
- Token có iss khác nhưng cùng sub.
- Token có iss là prefix gần giống issuer đúng.
- Token có iss khác path.
- Token được ký bằng key của issuer B nhưng gửi tới endpoint chỉ tin issuer A.
- Token có iss chưa xác minh trỏ tới localhost/private URL; xác minh rằng server không fetch URL đó.
- Issuer bị disable hoặc removed khỏi registry.

### 16.2. Audience tests

- aud là string đúng recipient.
- aud là array có chứa đúng recipient theo profile.
- aud chỉ chứa API khác.
- aud chứa hostname giống nhưng path khác.
- aud là prefix hoặc domain gần giống.
- Token cho Gateway được chuyển nguyên tới backend có audience khác.
- Token có nhiều audience vượt policy đã cấu hình.

### 16.3. Token-type tests

- ID Token hợp lệ được gửi tới resource API.
- Access Token hợp lệ được gửi tới OIDC ID Token validator.
- Refresh Token được gửi tới resource API.
- Client Assertion được gửi tới resource API.
- DPoP proof được gửi thay access token.
- Logout Token được gửi tới API nghiệp vụ.
- Token có typ sai hoặc thiếu typ trong profile bắt buộc.
- Token có typ đúng nhưng audience hoặc issuer sai.
- Token có chữ ký hợp lệ nhưng thiếu claims riêng của profile.

### 16.4. OAuth mix-up tests

- Authorization response issuer khớp transaction.
- Response iss khác issuer đã chọn.
- Response thiếu iss khi profile yêu cầu issuer identification.
- Code từ issuer B bị gửi tới token endpoint issuer A.
- state sai hoặc transaction không tồn tại.
- PKCE verifier không khớp.
- Redirect URI riêng theo issuer được ánh xạ sai.

### 16.5. Negative authorization tests

Ngay cả token đúng issuer, audience và type cũng phải bị từ chối nếu:

- Thiếu scope.
- Tenant không khớp.
- Subject không có membership.
- Resource thuộc owner khác.
- Action vượt quyền.
- Token hết hạn hoặc chưa có hiệu lực.

## 17. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký và exp | Token hợp lệ ở luồng khác có thể được chấp nhận. | Kiểm tra issuer, audience và token profile. |
| Dùng sub làm định danh toàn cục | Trộn người dùng từ nhiều issuer. | Dùng (iss, sub) hoặc mapping được quản lý. |
| So khớp iss/aud bằng prefix | Chấp nhận định danh gần giống. | So khớp chính xác theo profile. |
| Dùng một JWT validator cho mọi token | Cross-JWT confusion. | Mutually exclusive validation rules. |
| Không kiểm tra typ | ID Token hoặc JWT nghiệp vụ có thể bị nhầm với access token. | Explicit typing theo profile và kiểm tra sau khi xác minh chữ ký. |
| Chỉ kiểm tra typ | Attacker tự ghi typ đúng trong token giả. | Vẫn xác minh issuer, chữ ký, audience và required claims. |
| Coi scope thay cho audience | Token cho API khác bị chấp nhận. | Kiểm tra cả recipient và quyền. |
| Coi ID Token là access token | Dùng sai bằng chứng đăng nhập để gọi API. | ID Token chỉ dành cho OIDC client; API nhận access token. |
| Chấp nhận mọi audience trong array | Token bị dùng ở recipient ngoài dự kiến. | Chỉ chấp nhận audience theo policy đã định nghĩa. |
| Chọn key chỉ theo kid | Có thể dùng nhầm key của issuer khác. | Key lookup theo issuer/JWKS/profile. |
| Chọn issuer từ iss chưa xác minh rồi fetch | SSRF hoặc attacker-controlled trust. | Issuer allowlist và bootstrap tin cậy. |
| Dùng mTLS/client authentication để bỏ qua aud | Xác thực client không làm token dành cho API hiện tại. | Vẫn kiểm tra audience. |
| Không ràng buộc OAuth response với issuer | Authorization server mix-up. | RFC 9207, state, PKCE và transaction binding. |
| Không tách môi trường | Token dev/staging có thể được chấp nhận ở production. | Issuer, key và audience tách biệt. |

## 18. Checklist thiết kế validator JWT

Trước khi API chấp nhận một JWT, hãy trả lời:

1. **Purpose:** endpoint này nhận chính xác loại JWT nào?
2. **Issuer:** issuer nào được tin và được cấu hình ở đâu?
3. **Subject:** principal có được định danh theo issuer cùng subject không?
4. **Audience:** token có dành cho recipient hiện tại không; string/array được xử lý theo profile nào?
5. **Type:** typ hoặc profile identifier nào được yêu cầu?
6. **Mutual exclusivity:** validator này có từ chối token thuộc profile khác không?
7. **Keys:** key set có gắn với đúng issuer và token profile không?
8. **Algorithms:** thuật toán có allowlist độc lập với header không?
9. **Claims:** các claim bắt buộc, thời gian và quan hệ client/subject có được kiểm tra không?
10. **OIDC:** ID Token có được xác minh theo OIDC Core, bao gồm nonce và audience không?
11. **OAuth client:** client assertion và authorization response có được gắn với đúng issuer/transaction không?
12. **Downstream:** token có được phát hành cho backend audience hoặc exchange đúng cách không?
13. **Environments:** issuer, key và audience dev/staging/prod có tách biệt không?
14. **Authorization:** sau khi xác minh token, API có kiểm tra scope, tenant và quyền trên object không?
15. **Testing:** có test token hợp lệ nhưng sai issuer, sai audience hoặc sai type không?

## 19. Ghi nhớ trọng tâm

- Issuer trả lời ai phát hành; audience trả lời token dành cho ai; token type trả lời token thuộc profile và mục đích nào.
- Chữ ký hợp lệ không đủ để chấp nhận token. Phải xác minh iss, aud, thời gian, thuật toán và các yêu cầu profile.
- Dùng cặp (iss, sub) để tránh nhầm subject giữa nhiều issuer.
- Không lấy issuer chưa xác minh làm URL tự do để tải metadata/JWKS.
- Không so khớp issuer hoặc audience bằng prefix, substring hoặc domain suffix.
- ID Token dành cho OIDC client; Access Token dành cho resource server. Hai loại có audience và validation rules khác nhau.
- Refresh token, client assertion, DPoP proof, logout token và JWT nghiệp vụ không được dùng thay access token.
- RFC 8725 khuyến nghị explicit typing và mutually exclusive validation rules để chống cross-JWT confusion.
- typ hỗ trợ phân biệt loại token nhưng không thay thế chữ ký, issuer, audience và claims bắt buộc.
- OAuth multi-issuer client phải gắn authorization response với đúng issuer, ví dụ dùng issuer identification theo RFC 9207.
- Sau khi token đúng issuer, audience và type, resource server vẫn phải kiểm tra authorization trên action và resource cụ thể.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token); RFC 8725 (JSON Web Token Best Current Practices, explicit typing và mutually exclusive validation rules); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); OpenID Connect Core 1.0; RFC 9207 (OAuth 2.0 Authorization Server Issuer Identification); RFC 8693 (OAuth 2.0 Token Exchange); RFC 9449 (OAuth 2.0 Demonstrating Proof of Possession). Các chuẩn này xác định claims, token profile và cơ chế nhận diện issuer; validator phải kết hợp đúng profile và trust configuration của ứng dụng.
