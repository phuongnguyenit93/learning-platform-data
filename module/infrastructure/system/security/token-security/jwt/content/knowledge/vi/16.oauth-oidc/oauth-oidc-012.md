# Ranh giới giữa xác minh JWT và thực thi đầy đủ giao thức

## 1. Vì sao xác minh JWT không đồng nghĩa với thực thi đúng OAuth/OIDC?

Một hệ thống có thể xác minh chữ ký JWT thành công nhưng vẫn triển khai sai giao thức OAuth 2.0 hoặc OpenID Connect (OIDC). Nguyên nhân là **JWT là định dạng token**, còn OAuth/OIDC là các giao thức quy định cách client yêu cầu quyền, cách authorization server xác thực và cấp token, cách client nhận phản hồi, cũng như cách resource server sử dụng token.

Xác minh JWT thường tập trung vào một token đã được phát hành: cấu trúc, chữ ký hoặc mã hóa, khóa, issuer, audience, thời gian và claims. Thực thi OAuth/OIDC còn phải kiểm tra toàn bộ ngữ cảnh đã dẫn đến token đó:

- Client nào gửi yêu cầu và đã được đăng ký như thế nào?
- Người dùng đã xác thực và cấp consent theo đúng luồng chưa?
- Redirect URI, response type, grant type và scope có hợp lệ không?
- Authorization code có được ràng buộc với client, redirect URI và PKCE challenge không?
- Token được cấp có đúng resource, audience, loại token và quyền đã được chấp thuận không?
- Nếu là OIDC, ID Token có gắn với đúng phiên đăng nhập và authentication request của client không?

Ví dụ, một ID Token có chữ ký hợp lệ, issuer đúng và chưa hết hạn vẫn không thể tự động được dùng làm access token để gọi API. Nó được phát hành cho client OIDC nhằm truyền đạt kết quả xác thực người dùng. API cần access token có đúng audience và profile của resource server.

**Xác minh token trả lời token có đáng tin theo một profile hay không; thực thi giao thức trả lời toàn bộ request/response và việc sử dụng token có đúng quy tắc của OAuth/OIDC hay không.**

## 2. Phân biệt định dạng JWT với giao thức OAuth 2.0 và OIDC

### 2.1. JWT là định dạng biểu diễn thông tin

JWT định nghĩa cách biểu diễn một tập claims dưới dạng JSON, thường được truyền bằng Compact Serialization. JWT có thể được bảo vệ bằng:

- JWS: cung cấp tính toàn vẹn và xác thực nguồn ký theo khóa.
- JWE: cung cấp tính bí mật và bảo vệ nội dung theo cơ chế mã hóa.
- Nested JWT: kết hợp nhiều lớp JWS/JWE theo cấu trúc được định nghĩa.

JWT không tự định nghĩa cách người dùng đăng nhập, cách client xin quyền, cách authorization server xử lý consent, hay cách một API quyết định cấp quyền trên tài nguyên.

### 2.2. OAuth 2.0 là framework ủy quyền

OAuth 2.0 định nghĩa các vai trò và luồng ủy quyền chính:

| Vai trò | Trách nhiệm |
| --- | --- |
| Resource Owner | Chủ thể có quyền cho phép truy cập tài nguyên; thường là người dùng |
| Client | Ứng dụng yêu cầu quyền truy cập thay mặt resource owner hoặc chính nó |
| Authorization Server | Xác thực/đánh giá yêu cầu và cấp authorization grant hoặc access token |
| Resource Server | Bảo vệ tài nguyên và kiểm tra access token trước khi phục vụ yêu cầu |

OAuth 2.0 không bắt buộc access token phải là JWT. Access token có thể là chuỗi opaque, JWT hoặc một định dạng khác theo thỏa thuận giữa authorization server và resource server. Resource server không được tự giả định mọi access token đều có thể Base64URL decode thành Claims Set.

### 2.3. OIDC bổ sung lớp xác thực danh tính

OpenID Connect xây dựng trên OAuth 2.0 và bổ sung một giao thức xác thực người dùng. OIDC định nghĩa ID Token, UserInfo Endpoint, các scope/claims định danh, cách gắn kết kết quả xác thực với client và các quy tắc kiểm tra riêng.

| Thành phần | Mục đích chính |
| --- | --- |
| OAuth access token | Cho phép client gọi resource server trong phạm vi được cấp |
| OIDC ID Token | Truyền đạt kết quả xác thực và thông tin định danh người dùng cho client |
| UserInfo response | Cung cấp claims về người dùng cho client có access token phù hợp |

OIDC ID Token là JWT theo OIDC Core. OAuth access token thì không nhất thiết là JWT. Hai loại token có mục đích, audience và quy tắc validation khác nhau.

## 3. Một JWT có thể xuất hiện ở nhiều vị trí trong OAuth/OIDC

Không nên chỉ nhìn thấy một chuỗi JWT rồi suy ra nó là access token. JWT có thể được dùng ở nhiều vai trò:

| Vị trí | Ví dụ | Bên nhận/kiểm tra |
| --- | --- | --- |
| OIDC ID Token | Kết quả xác thực người dùng | OIDC Client |
| JWT Access Token | Access token theo một profile JWT | Resource Server |
| Client Authentication | JWT client assertion tại token endpoint | Authorization Server |
| Token Exchange | Subject token hoặc actor token theo RFC 8693 | Authorization Server |
| Request Object | Tham số yêu cầu OIDC được ký hoặc mã hóa | OpenID Provider |
| Logout Token | Token thông báo logout theo OIDC Back-Channel Logout | RP/client nhận thông báo |

Mỗi vị trí có profile và quy tắc kiểm tra riêng. Chữ ký hợp lệ của một JWT không cho phép đem token đó dùng ở vị trí khác. Ví dụ, client assertion được phát hành để xác thực client tại token endpoint không phải access token để gọi API.

## 4. Hai lớp validation cần được tách riêng

### 4.1. Lớp giao thức và giao dịch

Lớp này kiểm tra yêu cầu/đáp ứng có tuân thủ OAuth/OIDC hay không:

- Client ID có hợp lệ và được phép dùng grant/response type không?
- Redirect URI có khớp URI đã đăng ký theo quy tắc của giao thức không?
- Scope, resource và authorization details có được phép không?
- State, nonce và PKCE có gắn với đúng giao dịch không?
- Authorization code có còn hiệu lực, dùng một lần và đúng client không?
- Token endpoint có xác thực client theo phương thức đã đăng ký không?
- Token response có đúng định dạng và chứa các trường cần thiết không?

### 4.2. Lớp token và claims

Lớp này kiểm tra token đã nhận:

- Định dạng, chữ ký/mã hóa và thuật toán.
- Khóa xác minh gắn với issuer.
- Issuer, audience, loại token và profile.
- Thời hạn và các claims bắt buộc.
- Kiểu dữ liệu, ngữ nghĩa và ràng buộc giữa claims.
- Scope/entitlement cần thiết cho resource server.

Hai lớp liên quan nhưng không thay thế nhau. Một token có thể vượt qua token validation trong khi giao dịch cấp token đã sai. Ngược lại, một authorization flow hợp lệ không có nghĩa resource server được bỏ qua validation của access token.

## 5. Authorization Code Flow: giao thức bảo vệ việc tạo token

Authorization Code Flow là luồng phổ biến cho ứng dụng web và native app. Ở mức khái quát:

~~~text
Client
  |
  | 1. Authorization Request
  |    client_id, redirect_uri, response_type=code
  |    scope, state, code_challenge
  v
Authorization Server
  |
  | 2. Xác thực người dùng, consent và policy
  |
  | 3. Redirect với authorization code + state
  v
Client callback
  |
  | 4. Kiểm tra state, gửi code + code_verifier
  |    và client authentication nếu cần
  v
Token Endpoint
  |
  | 5. Xác minh code, client, redirect_uri, PKCE
  |    và điều kiện cấp token
  v
Access Token (+ ID Token nếu là OIDC)
~~~

Chữ ký của JWT được cấp ở bước cuối không thể thay thế các kiểm tra ở những bước trước.

### 5.1. Client và redirect URI

Authorization server phải xác định client dựa trên đăng ký và chính sách. Client ID là định danh công khai của client, không phải bằng chứng xác thực client bí mật.

Redirect URI cần được kiểm tra theo quy tắc đăng ký của authorization server. Không dùng kiểm tra tiền tố, wildcard rộng hoặc so khớp lỏng lẻo khiến attacker điều hướng authorization response đến endpoint do họ kiểm soát. Với native app có một số ngoại lệ chuẩn hóa cho loopback redirect URI; phải áp dụng đúng quy tắc của loại client thay vì mở rộng wildcard chung.

Client không được dùng redirect URI nhận tùy ý từ request làm đích callback mà không đối chiếu với cấu hình đăng ký.

### 5.2. State gắn kết authorization response

Client thường tạo giá trị state khó đoán, lưu gắn với giao dịch đăng nhập và gửi trong authorization request. Khi nhận callback, client phải so khớp state với giao dịch đang chờ trước khi xử lý authorization response.

State hỗ trợ tương quan request/response và phòng chống CSRF trong authorization flow. Không chấp nhận một state bất kỳ chỉ vì callback có chứa trường này. State cần được tạo, lưu, kiểm tra và hết hạn theo một giao dịch cụ thể.

Trong một số thiết kế, PKCE có thể cung cấp bảo vệ CSRF khi được triển khai đúng theo hướng dẫn bảo mật OAuth hiện hành. Tuy nhiên, state vẫn hữu ích cho tương quan giao dịch và các thông tin ứng dụng cần khôi phục. Vai trò của state và PKCE cần được định nghĩa rõ thay vì bỏ qua kiểm tra response correlation.

### 5.3. PKCE ràng buộc authorization code với client khởi tạo

Client tạo code_verifier ngẫu nhiên, tính code_challenge theo phương thức được hỗ trợ (thường là S256) và gửi challenge trong authorization request. Khi đổi code lấy token, client gửi verifier. Authorization server kiểm tra verifier có khớp challenge đã lưu với authorization code không.

PKCE giảm nguy cơ kẻ tấn công chặn hoặc chèn authorization code rồi đổi code đó lấy token. Authorization server phải ràng buộc code với code challenge của đúng giao dịch và không chấp nhận verifier từ một giao dịch khác.

Không dùng plain khi có thể dùng S256. Không tái sử dụng verifier giữa các giao dịch. PKCE không phải chữ ký JWT; nó bảo vệ quá trình trao đổi authorization code.

### 5.4. Authorization code phải được ràng buộc và dùng một lần

Authorization code cần:

- Có thời hạn ngắn.
- Chỉ sử dụng một lần.
- Được ràng buộc với client đã yêu cầu.
- Được ràng buộc với redirect URI của giao dịch.
- Được ràng buộc với PKCE challenge nếu PKCE được dùng/yêu cầu.
- Không bị đổi cho client khác hoặc audience tùy ý.

Nếu code đã được sử dụng, hết hạn hoặc không khớp client/redirect URI/verifier, token endpoint phải từ chối. Việc sau đó ký một access token đúng không thể sửa được lỗi đã xảy ra ở bước redeem code.

### 5.5. Phòng chống authorization-server mix-up

Một client có thể kết nối với nhiều authorization server. Nếu client không xác định response đến từ issuer nào, kẻ tấn công có thể tìm cách khiến client gửi authorization code hoặc token đến nhầm token endpoint. Chữ ký của token cuối cùng không bảo vệ được client khỏi việc xử lý nhầm máy chủ trong quá trình trao đổi.

Khi hỗ trợ nhiều authorization server, client cần gắn mỗi giao dịch với issuer dự kiến và xác minh issuer trong authorization response. Có thể sử dụng tham số issuer identification trong authorization response theo RFC 9207; client phải so khớp giá trị đó với issuer đã chọn khi bắt đầu giao dịch. Một phương án khác theo hướng dẫn bảo mật là dùng redirect URI riêng biệt cho từng authorization server. Không suy ra issuer chỉ từ dữ liệu callback chưa được xác minh hoặc từ token được gửi đến sau đó.

## 6. Token Endpoint cũng có quy tắc riêng

Token endpoint không chỉ là nơi tạo JWT. Nó phải xử lý đúng grant type và xác thực client theo cấu hình.

### 6.1. Xác thực client

Phương thức xác thực phụ thuộc loại client và đăng ký, có thể là client secret, private_key_jwt, mutual TLS hoặc phương thức khác được hỗ trợ. Public client không thể bảo vệ một client secret nhúng trong ứng dụng phân phối cho người dùng; không coi một giá trị client_id là bí mật.

Nếu dùng JWT client assertion, assertion có profile riêng. Authorization server cần kiểm tra issuer/subject gắn với client, audience của token endpoint, thời hạn ngắn, định danh assertion và cơ chế chống replay theo đặc tả. Không chấp nhận bất kỳ JWT có chữ ký hợp lệ nào làm client assertion.

### 6.2. Grant type và quyền được cấp

Token endpoint phải xác minh grant hợp lệ và các điều kiện của grant:

- Authorization code có hợp lệ và chưa được dùng không?
- Refresh token có thuộc client/session và còn được phép sử dụng không?
- Client credentials có được cấp cho client đó không?
- Device authorization hoặc các grant khác có hoàn tất đúng bước không?
- Scope/resource được yêu cầu có nằm trong phạm vi được phép không?

Không sao chép nguyên scope client yêu cầu vào token. Authorization server phải tính tập quyền được cấp theo grant, consent và policy. Token phản ánh quyền đã cấp, không phản ánh đơn thuần điều client muốn.

### 6.3. Token response

Client phải xử lý token response theo giao thức:

- Kiểm tra HTTP status và lỗi OAuth.
- Đọc access_token, token_type, expires_in và các trường được profile quy định.
- Nếu OIDC, kiểm tra và xác minh ID Token theo OIDC Core.
- Bảo vệ token trong bộ nhớ/lưu trữ và không đưa vào URL/log.
- Không giả định access_token là JWT nếu authorization server không cam kết định dạng/profile đó.

Một response HTTP thành công không có nghĩa client có thể bỏ qua kiểm tra ID Token. Tương tự, nếu response báo lỗi, client không được sử dụng token cũ hoặc dữ liệu callback chưa xác minh như thể giao dịch đã thành công.

## 7. OIDC: ID Token có quy tắc kiểm tra riêng

OIDC ID Token là JWT mang các claims xác thực. Client cần xác minh nó theo OIDC Core, không chỉ gọi một hàm kiểm tra chữ ký chung.

Các kiểm tra cốt lõi bao gồm:

| Thành phần | Quy tắc kiểm tra |
| --- | --- |
| Chữ ký | Xác minh theo thuật toán và khóa được cấu hình/metadata tin cậy của OpenID Provider |
| iss | Phải khớp chính xác issuer đã được client tin cậy/discovery |
| aud | Phải chứa client_id của client đang thực hiện authentication request |
| azp | Nếu có, phải xác minh authorized party phù hợp; khi có nhiều audience, client nên kiểm tra azp theo OIDC Core |
| exp | ID Token chưa hết hạn theo quy tắc thời gian |
| iat | Thời điểm phát hành hợp lý theo chính sách |
| nonce | Nếu request đã gửi nonce, ID Token phải chứa nonce tương ứng và client phải so khớp |
| auth_time | Phải có và được kiểm tra khi request có max_age |
| Hash claims | c_hash/at_hash được kiểm tra khi có và theo điều kiện flow/profile tương ứng |

OIDC Core quy định thêm các quy tắc tùy theo flow và cách yêu cầu. Bảng trên là các điểm quan trọng, không thay thế việc đọc đúng profile/flow đang triển khai.

### 7.1. Issuer và discovery metadata

Client có thể dùng OpenID Provider Discovery để lấy metadata như issuer, authorization endpoint, token endpoint, UserInfo endpoint, JWKS URI và các phương thức được hỗ trợ. Metadata phải được lấy từ nguồn tin cậy và issuer trong metadata phải khớp issuer mà client dự định sử dụng.

Không lấy discovery URL hoặc JWKS URI tùy ý từ một ID Token chưa xác minh. Không chấp nhận issuer chỉ vì token tự khai báo một URL trông hợp lệ. Discovery là cơ chế cấu hình/khám phá endpoint có kiểm soát, không phải cách tin dữ liệu do token cung cấp.

### 7.2. Audience của ID Token là client

Trong ID Token, aud xác định client hoặc các client mà ID Token được phát hành cho. Với access token, aud xác định resource server. Vì vậy cùng một claim aud nhưng ý nghĩa bên nhận phụ thuộc loại token và profile.

Nếu ID Token có audience không chứa client_id của client đang xử lý, client phải từ chối. Không dùng quy tắc audience của API để xác minh ID Token, và cũng không dùng quy tắc audience của ID Token cho access token.

### 7.3. Nonce gắn ID Token với authentication request

OIDC nonce giúp client gắn ID Token nhận được với authentication request đã gửi. Khi client gửi nonce, client phải xác minh giá trị trong ID Token khớp chính xác với nonce đã lưu cho giao dịch đó.

Nonce phải khó đoán, gắn với đúng phiên/giao dịch và được quản lý vòng đời. Chỉ kiểm tra chữ ký hoặc iss/aud mà bỏ nonce trong flow đã yêu cầu nonce có thể làm mất một lớp bảo vệ chống replay/response injection.

### 7.4. Không dùng ID Token làm bearer credential cho API

ID Token dành cho client OIDC để xác nhận kết quả đăng nhập và subject. Nó không mặc nhiên cấp quyền gọi resource server. API cần access token có audience phù hợp và scope/entitlement tương ứng.

Nếu API chấp nhận ID Token như access token, nó có thể nhầm audience, loại token, mục đích và cách diễn giải claims. Đây là một dạng cross-JWT confusion.

## 8. Resource Server: xác minh access token theo hợp đồng

Resource server cần xác định access token được phát hành cho nó và được phép sử dụng theo chính sách OAuth.

Nếu access token là JWT theo RFC 9068, resource server phải áp dụng profile JWT access token, bao gồm loại token và các claim bắt buộc theo RFC/profile. Ví dụ, profile sử dụng typ là at+jwt, kiểm tra issuer, audience, thời gian và các claims như client_id, jti, iat, exp, cùng sub/scope theo quy tắc của profile.

Nếu authorization server phát hành opaque access token, resource server không được cố parse nó như JWT. Có thể dùng token introspection theo RFC 7662 hoặc cơ chế xác minh được hệ thống định nghĩa.

Dù token là JWT hay opaque, resource server cần:

1. Xác định token type/profile được chấp nhận.
2. Xác minh issuer/authorization server và trạng thái token theo kiến trúc.
3. Xác minh audience/resource phù hợp.
4. Kiểm tra thời hạn, scope và entitlement.
5. Kiểm tra quyền trên tài nguyên cụ thể, ví dụ tenant và ownership.
6. Áp dụng chính sách thu hồi hoặc trạng thái hiện hành khi cần.

## 9. Các tình huống JWT hợp lệ nhưng giao thức hoặc ngữ cảnh sai

| Tình huống | Vì sao chữ ký chưa đủ? | Kiểm tra còn thiếu |
| --- | --- | --- |
| ID Token được gửi đến API | Token được phát hành cho OIDC client | Token type/profile và audience của resource server |
| Access token dành cho API A được gửi đến API B | Issuer có thể đúng nhưng resource sai | aud và resource binding |
| Client dùng redirect URI chưa đăng ký | JWT chưa liên quan đến tính hợp lệ của authorization response | Redirect URI validation |
| Authorization response có state sai | Token sau đó có thể vẫn được ký đúng | Gắn kết response với request/phiên client |
| Authorization code bị chặn và redeem lại | Token đầu ra có thể hợp lệ về chữ ký | Code one-time, client binding, redirect URI, PKCE |
| PKCE verifier không khớp | Giao dịch redeem code không đúng client khởi tạo | Code challenge/verifier validation |
| Scope client yêu cầu vượt quyền | Token có thể được ký đúng nếu issuer cấp sai | Grant, consent và authorization policy |
| Client assertion JWT dùng sai audience | Chữ ký assertion có thể đúng | Assertion profile và token endpoint audience |
| ID Token có nonce không khớp | Chữ ký hợp lệ nhưng không gắn với request hiện tại | Nonce validation |
| Issuer đúng nhưng token đã hết hạn | Chữ ký không hết hiệu lực theo thời gian | exp, nbf, policy về token age |
| UserInfo trả sub khác ID Token | Response có thể hợp lệ ở tầng HTTP | So khớp subject theo OIDC |

## 10. Ví dụ: hai token ký đúng nhưng chỉ một token phù hợp với API

Giả sử OpenID Provider phát hành ID Token cho client:

~~~json
{
  "iss": "https://login.example.org",
  "sub": "user_42",
  "aud": "web-client-123",
  "exp": 1893456900,
  "iat": 1893456000,
  "nonce": "n-0S6_WzA2Mj"
}
~~~

Và access token cho API đơn hàng:

~~~json
{
  "iss": "https://login.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "iat": 1893456000,
  "scope": "orders:read"
}
~~~

Giả sử cả hai đều được ký hợp lệ:

| Consumer | ID Token | Access Token |
| --- | --- | --- |
| OIDC Client | Có thể xác minh để hoàn tất đăng nhập nếu các kiểm tra OIDC đạt | Không thay thế ID Token trong giao thức đăng nhập |
| API đơn hàng | Từ chối vì sai loại token/audience | Có thể chấp nhận nếu validation profile và authorization đạt |

API không được coi ID Token là access token chỉ vì cùng issuer và cùng subject. Client cũng không dùng access token làm bằng chứng thay cho ID Token để hoàn tất OIDC authentication.

## 11. Luồng xác minh tổng thể theo từng vai trò

### 11.1. OIDC Client

~~~text
Tạo authentication request
  |
  +--> client_id / redirect_uri / response_type
  +--> scope có openid
  +--> state / nonce (theo flow)
  +--> PKCE code_challenge
  |
  v
Gửi người dùng đến Authorization Endpoint
  |
  v
Nhận callback
  |
  +--> So khớp state
  +--> Xử lý authorization error hoặc code
  |
  v
Gửi code + code_verifier đến Token Endpoint
  |
  v
Nhận token response
  |
  +--> Xác minh ID Token theo OIDC Core
  +--> Kiểm tra iss, aud, exp, iat, nonce, ...
  +--> Lưu phiên ứng dụng an toàn
  |
  v
Đăng nhập hoàn tất
~~~

### 11.2. Resource Server

~~~text
Nhận API request + access token
  |
  v
Xác định profile và issuer được tin cậy
  |
  v
Xác minh chữ ký hoặc introspection
  |
  v
Kiểm tra token type, iss, aud, exp, nbf
  |
  v
Kiểm tra claims, scope, client/subject
  |
  v
Kiểm tra tenant, ownership và policy tài nguyên
  |
  v
Cho phép hoặc từ chối request
~~~

Client và resource server có trách nhiệm khác nhau. Client kiểm tra phản hồi đăng nhập và ID Token theo OIDC; resource server kiểm tra access token theo hợp đồng bảo vệ API. Không chuyển một bộ validation của bên này sang bên kia mà không xét profile.

## 12. Xử lý lỗi và phản hồi theo đúng lớp

Phân biệt lỗi giao thức với lỗi token và lỗi authorization giúp xử lý chính xác:

| Lớp lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Authorization request | redirect_uri không hợp lệ, client không được phép dùng response type | Authorization Server từ chối request theo OAuth |
| Authorization response | State không khớp, response không thuộc giao dịch đang chờ | Client không hoàn tất đăng nhập; kết thúc giao dịch an toàn |
| Token endpoint | Code hết hạn/đã dùng, PKCE sai, client authentication thất bại | Trả lỗi OAuth phù hợp; không phát hành token |
| ID Token validation | Issuer/audience/nonce/thời gian/chữ ký sai | OIDC Client từ chối kết quả authentication |
| Access token validation | Chữ ký, issuer, audience, profile hoặc thời gian sai | Resource Server từ chối token |
| Authorization | Token hợp lệ nhưng thiếu scope hoặc không có quyền trên tài nguyên | Từ chối thao tác theo chính sách |
| Dependency failure | Introspection hoặc policy service không khả dụng | Xử lý theo fail-closed/fallback đã được phê duyệt |

Không trả cùng một lỗi cho mọi tình huống nếu giao thức yêu cầu phân biệt. Ví dụ OAuth token endpoint có các error code chuẩn; resource server dùng quy tắc Bearer Token trong RFC 6750; OIDC client xử lý authentication failure theo giao thức và chính sách ứng dụng.

## 13. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ xác minh chữ ký ID Token | Bỏ sót issuer, audience, nonce và ràng buộc authentication request | Áp dụng đầy đủ OIDC ID Token Validation |
| Dùng ID Token gọi API | Nhầm mục đích và audience | API chỉ nhận access token theo profile |
| Giả định access token luôn là JWT | Từ chối opaque token hợp lệ hoặc parse sai | Theo hợp đồng token; introspection khi cần |
| Không xác minh redirect URI | Authorization code có thể bị chuyển hướng | Đăng ký và so khớp redirect URI chặt chẽ |
| Không kiểm tra state | Có thể xử lý response không thuộc giao dịch hiện tại | Gắn state với phiên và request đang chờ |
| Bỏ PKCE hoặc không kiểm tra verifier | Authorization code bị chặn/chèn có thể bị redeem | Dùng PKCE S256 và xác minh tại token endpoint |
| Không ràng buộc code với client | Code có thể bị dùng ở client khác | Kiểm tra client binding và one-time use |
| Chấp nhận mọi scope client yêu cầu | Cấp quyền vượt consent/policy | Tính granted scope tại authorization server |
| Tin issuer/JWKS URL do token cung cấp | Có thể xác minh bằng khóa do attacker kiểm soát | Dùng issuer và metadata đã cấu hình tin cậy |
| Bỏ qua token type | Cross-JWT confusion | Phân biệt access token, ID Token, assertion và token chuyên biệt |
| Dùng chung validation cho client và resource server | Bỏ sót các điều kiện riêng của từng vai trò | Áp dụng profile tương ứng cho từng consumer |
| Không kiểm tra UserInfo subject | Ghép nhầm thông tin người dùng | So khớp subject với ID Token đã xác minh |

## 14. Checklist kiểm tra ranh giới giao thức và JWT

### Authorization Server

- Client đã đăng ký và grant/response type được phép.
- Redirect URI được kiểm tra đúng quy tắc.
- Người dùng, client, consent và policy được xác minh.
- PKCE challenge được lưu và kiểm tra khi redeem code.
- Authorization code ngắn hạn, dùng một lần và ràng buộc với client/redirect URI.
- Scope/resource được yêu cầu được chuyển thành quyền thực sự được cấp.
- Token được tạo theo đúng profile và audience.
- Khóa ký, thuật toán và metadata được quản lý an toàn.

### OIDC Client

- Sử dụng đúng issuer và discovery metadata tin cậy.
- Tạo và kiểm tra state theo từng giao dịch.
- Dùng PKCE phù hợp với client/flow.
- Xác minh chữ ký ID Token và toàn bộ điều kiện OIDC Core.
- Kiểm tra issuer, audience, authorized party khi áp dụng, thời gian, nonce và auth_time khi được yêu cầu.
- Không dùng ID Token làm access token.
- Nếu gọi UserInfo, kiểm tra subject khớp với subject đã xác minh trong ID Token.

### Resource Server

- Xác định access token profile được chấp nhận.
- Không giả định access token luôn là JWT.
- Kiểm tra issuer, audience, token type, thời hạn và schema.
- Dùng introspection hoặc trạng thái tập trung nếu kiến trúc yêu cầu.
- Kiểm tra scope/entitlement và quyền trên tài nguyên.
- Không chấp nhận ID Token, client assertion hoặc token của API khác làm access token.

## 15. Tình huống tự kiểm tra

Một ứng dụng web dùng OIDC Authorization Code Flow. Client nhận một ID Token có chữ ký hợp lệ, issuer đúng và exp còn hạn. Tuy nhiên, ID Token có audience là mobile-client-456, trong khi client hiện tại có client_id là web-client-123. Token cũng không chứa nonce đã gửi trong authorization request.

**Câu hỏi 1:** Client có được coi đăng nhập thành công chỉ vì chữ ký hợp lệ không?

**Trả lời:** Không. Audience không chứa client hiện tại, nên ID Token không được phát hành cho client này. Nonce cũng không khớp với authentication request. Client phải từ chối ID Token và không tạo phiên đăng nhập từ nó.

**Câu hỏi 2:** Nếu client gửi ID Token đó đến API đơn hàng, API có thể xác minh chữ ký rồi chấp nhận không?

**Trả lời:** Không. API cần access token được phát hành cho audience của API và có scope/entitlement phù hợp. ID Token dành cho client OIDC.

**Câu hỏi 3:** Nếu access token là chuỗi opaque, resource server có thể từ chối vì không parse được JWT không?

**Trả lời:** Không nếu hợp đồng cho phép opaque access token. Resource server cần dùng cơ chế validation được thiết kế, chẳng hạn introspection, thay vì giả định mọi access token đều là JWT.

## 16. Ghi nhớ

JWT là định dạng token; OAuth 2.0 là framework ủy quyền; OIDC bổ sung giao thức xác thực danh tính. Mỗi vai trò và mỗi loại token có ranh giới kiểm tra riêng. Xác minh chữ ký chỉ là một phần của validation token, còn thực thi đúng giao thức đòi hỏi kiểm tra request, response, client, redirect URI, state, PKCE, grant, consent, scope, resource và các ràng buộc flow.

OIDC Client phải xác minh ID Token theo OIDC Core; Resource Server phải xác minh access token theo profile dành cho API. Không tráo đổi hai loại token. **Một token chỉ được sử dụng khi vừa hợp lệ theo profile của nó, vừa xuất hiện trong đúng giao dịch, đúng vai trò và đúng ngữ cảnh mà giao thức cho phép.**

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò, authorization endpoint, token endpoint và grant.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách sử dụng access token bearer tại resource server.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): code verifier và code challenge.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata của authorization server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): resource server tra cứu trạng thái token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trao đổi token và subject/actor context.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): nhận diện issuer trong authorization response và phòng ngừa mix-up.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo mật OAuth hiện hành.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authentication request, ID Token và quy tắc xác minh OIDC.
