# Kiểm tra token type và usage

Trong hệ thống OAuth 2.0/OpenID Connect (OIDC), một chuỗi có chữ ký hợp lệ **chưa đủ để được sử dụng ở bất kỳ endpoint nào**. Hệ thống còn phải xác định **đó là loại token gì, được phát hành cho mục đích nào, ai được nhận và cách sử dụng có đúng giao thức hay không**. Ví dụ, **ID token** có thể được ký bằng cùng một hệ thống khóa với access token nhưng **không được dùng như access token để gọi API**. Refresh token có thể còn hiệu lực tại Authorization Server (AS), nhưng **không phải credential để gọi Resource Server**.

Bài học này thuộc chương **Token validation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, tập trung vào **“Kiểm tra token type và usage”**. Nội dung kết nối mô hình tin cậy và vòng đời token: JWT, opaque token, access token, refresh token, phát hành và xác minh claims, scope, audience, OAuth 2.0/OIDC, lưu trữ, thu hồi và phòng chống việc token bị đánh cắp hoặc phát lại.

**Nguyên tắc cốt lõi:** trước khi chấp nhận credential, thành phần nhận phải trả lời được **“Tôi có phải bên nhận được chỉ định không, đây có đúng loại token tôi mong đợi không, và request hiện tại có đúng cách sử dụng được phép không?”**. Chỉ khi các điều kiện đó và những kiểm tra mật mã/trạng thái cùng thành công, hệ thống mới xét quyền nghiệp vụ.

## 1. “Token type” và “usage” không chỉ có một nghĩa

Trong tài liệu và API OAuth/JOSE, cụm từ *token type* có thể nói tới nhiều lớp thông tin. Cần tách rõ để tránh nhầm lẫn:

| Khái niệm | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| **Mục đích/loại hiện vật** | Access token, refresh token, ID token, authorization code, client assertion, DPoP proof | Token/hiện vật này **được phép làm gì**? |
| **OAuth token type trong token response** | `"token_type": "Bearer"` hoặc `"DPoP"` | Client phải **trình access token theo cơ chế nào**? |
| **Định dạng token** | JWT được ký bằng JWS, JWT được mã hóa bằng JWE, opaque string | Bên nhận **xác minh bằng kỹ thuật nào**? |
| **JOSE protected header `typ`** | `"at+jwt"`, `"JWT"`, `"dpop+jwt"` | Profile JWT **tự công bố loại đối tượng nào**? |
| **Claims/metadata ràng buộc usage** | `iss`, `aud`, `scope`, `client_id`, `cnf`, `exp` | Token dành cho **issuer, audience, quyền, thời gian và chủ thể** nào? |
| **Vị trí/giao thức sử dụng** | `Authorization: Bearer`, token endpoint `grant_type=refresh_token`, OIDC client validation | **Endpoint nào** có quyền chấp nhận hiện vật này? |

Ba ví dụ dễ nhầm:

- `token_type: Bearer` trong OAuth token response **không nói** access token là JWT hay opaque. Nó mô tả cách trình bearer token.
- `typ: at+jwt` trong JWS header biểu thị một **JWT access token theo profile phù hợp**; nó không có nghĩa client phải dùng OAuth `token_type=at+jwt`.
- `grant_type=refresh_token` là **loại grant** gửi tới token endpoint, **không phải** JOSE `typ` và cũng không phải định dạng của refresh token.

**Phải kiểm tra đồng thời nhiều lớp phù hợp với điểm nhận**, thay vì so sánh một trường tên `type` rồi chấp nhận tất cả.

## 2. Bản đồ các hiện vật và nơi chúng được dùng

| Hiện vật | Bên phát hành/tạo | Bên nhận đúng | Cách sử dụng chính | Sai lầm cần chặn |
|---|---|---|---|---|
| **Access token** | Authorization Server | Resource Server có audience phù hợp | Client gửi theo cơ chế được cấp (Bearer hoặc sender-constrained) | Dùng token API A ở API B; dùng ID token thay thế |
| **Refresh token** | Authorization Server | Token endpoint của AS | Client xin access token mới theo grant còn hợp lệ | Gửi tới API nghiệp vụ; dùng với client khác |
| **ID token (OIDC)** | OpenID Provider | OIDC Client/Relying Party | Client xác minh sự kiện xác thực user | API coi ID token là access token |
| **Authorization code** | AS | Token endpoint qua client | Đổi một lần theo client/redirect/PKCE | Dùng code trực tiếp gọi API hoặc đổi nhiều lần |
| **Client assertion JWT** | Confidential client | AS token endpoint | Xác thực client, ví dụ `private_key_jwt` | API nhận assertion như access token |
| **DPoP proof JWT** | Bên sở hữu khóa DPoP | AS/RS theo request cụ thể | Chứng minh sở hữu khóa, ràng buộc request và token | Dùng proof đơn lẻ như access token |
| **Cookie phiên AS/ứng dụng** | Server quản lý phiên | Miền/server phiên tương ứng | Duy trì session theo chính sách | Cho rằng cookie phiên là bearer access token API |

**Không phải tất cả các dòng trong bảng đều là “token” theo cùng một chuẩn.** Authorization code và cookie là các hiện vật giao thức/phiên; bảng dùng để so sánh *usage*, không khẳng định chúng có cấu trúc JWT.

**Lưu ý:** cùng một access token có thể được gửi trong nhiều request hợp lệ đến **API được chỉ định**, nhưng authorization code thường dùng một lần, refresh token có quy tắc rotation, và DPoP proof có cơ chế chống replay riêng. Không suy luận vòng đời của hiện vật này từ hiện vật khác.

## 3. Mô hình tin cậy: mỗi bên kiểm tra token theo mục đích của mình

~~~mermaid
flowchart LR
    U["User / Resource owner"]
    C["Client / Relying Party"]
    AS["Authorization Server / OpenID Provider"]
    RS["Resource Server: Orders API"]
    DB[("Orders + ACL / tenant policy")]

    U -->|"Authentication / consent khi cần"| AS
    C -->|"Authorization request + code exchange"| AS
    AS -->|"Access token cho Orders API"| C
    AS -->|"ID token cho client khi OIDC"| C
    AS -->|"Refresh token nếu được phép"| C
    C -->|"Access token đúng usage"| RS
    C -->|"Refresh token chỉ đến token endpoint"| AS
    RS -->|"Kiểm tra claims, scope và quyền object"| DB
~~~

Các ranh giới cần phân biệt:

1. **AS phát hành hoặc quản lý token:** chịu trách nhiệm kiểm tra grant, client, người dùng/chính sách, loại token, audience, scope và thời hạn.
2. **Client OIDC kiểm tra ID token:** xác minh issuer, audience là client ID, chữ ký, thời gian, `nonce` nếu gửi và các quy tắc OIDC liên quan **trước khi tạo phiên ứng dụng**.
3. **Resource Server kiểm tra access token:** xác minh nguồn phát hành, đúng loại/usage, audience của API, thời hạn, quyền và trạng thái phù hợp **trước khi trả dữ liệu**.
4. **Token endpoint kiểm tra refresh token:** xác minh đúng loại grant, client binding, trạng thái, rotation/replay và scope; không trả token mới chỉ vì refresh token trông giống JWT hợp lệ.
5. **Request sender-constrained:** Resource Server còn phải kiểm tra bằng chứng sở hữu khóa nếu access token được ràng buộc bằng DPoP/mTLS.

Nếu một Resource Server chấp nhận bất kỳ JWT nào có chữ ký đúng từ issuer, nó đã bỏ qua **mục đích sử dụng** và tạo điều kiện cho *token confusion* hoặc *cross-JWT confusion*.

## 4. Cần một “token acceptance policy” cho từng điểm nhận

Một chính sách chấp nhận token (acceptance policy) cần mô tả tường minh:

| Thuộc tính | Ví dụ tại Orders API | Vì sao quan trọng |
|---|---|---|
| **Đường nhận** | Header `Authorization` theo Bearer/DPoP được hỗ trợ | Ngăn credential bị đưa qua đường không mong đợi |
| **Issuer tin cậy** | `https://auth.example.test` | Ngăn token từ issuer khác |
| **Token purpose** | **Access token**, không ID/refresh/client assertion | Ngăn token confusion |
| **JOSE/profile** | RFC 9068 JWT access token với `typ=at+jwt`, hoặc opaque introspection theo cấu hình | Ràng buộc cách parse và xác minh |
| **Audience** | `https://orders-api.example.test` | Không nhận token dành cho Billing API hoặc client đăng nhập |
| **Thuật toán/khóa** | Các thuật toán allowlist và JWKS của issuer đã cấu hình | Không để header untrusted chọn nguồn/thuật toán tùy ý |
| **Thời gian** | `exp`, `nbf`, chính sách clock skew | Không chấp nhận token quá hạn/chưa hiệu lực |
| **Quyền** | Scope `orders:read` hoặc `orders:write` theo endpoint | Token hợp lệ vẫn có thể thiếu quyền |
| **Quyền đối tượng** | ACL/tenant/chủ đơn hàng | Scope không thay thế quyền với từng bản ghi |
| **Trạng thái/ràng buộc** | Revocation khi cần; DPoP/mTLS proof nếu `cnf` yêu cầu | Ngăn replay hoặc lạm dụng token bị thu hồi |

Một công ty có thể chấp nhận nhiều issuer hoặc nhiều định dạng, nhưng cần **cấu hình chính sách riêng cho từng issuer/audience/profile**, tránh “thử tất cả decoder đến khi có cái nhận” mà không xác định token thuộc miền tin cậy nào.

### Điểm khác biệt giữa parse, validate và authorize

~~~text
parse      -> Nhận biết cấu trúc, chưa có tin cậy
validate   -> Xác minh chữ ký/trạng thái, issuer, audience, mục đích,
              thời gian và các ràng buộc giao thức
authorize  -> Kiểm tra scope, client/user, ACL, tenant và đối tượng cụ thể
~~~

**Decode Base64url không phải validation.** JWT JWS có payload đọc được mà không cần khóa, nhưng mọi claim chỉ đáng tin **sau khi** xác minh và áp dụng đúng profile.

## 5. JWT header `typ`: “at+jwt” không đồng nghĩa mọi JWT

JOSE header có thể có `typ` nhằm xác định loại đối tượng. Theo **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**, JWT access token được phát hành theo profile này phải có protected header `typ` phù hợp như `at+jwt` (hoặc dạng media-type `application/at+jwt` theo profile).

Header access token minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "as-signing-key-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000600,
  "jti": "access-2026-1001"
}
~~~

Hai khối trên chỉ là **header và payload JSON để học**, chưa phải token có chữ ký. Các timestamp là Unix seconds minh họa.

**Resource Server áp dụng RFC 9068** cần thực hiện **explicit typing**: chỉ chấp nhận loại header đã quy định cho JWT access token, kiểm tra đúng issuer, audience, chữ ký, thời gian và claims bắt buộc. Nếu token có `typ: JWT` chung chung hoặc thiếu `typ`, không mặc định nó đáp ứng RFC 9068.

### Header `typ` có phải “sự thật” khi vừa decode?

Không. Trước khi chữ ký và cấu hình được xác minh, cả protected header và payload đều là **dữ liệu do người gửi token cung cấp**. `typ` giúp parser chọn một **chính sách xác minh đã được cấu hình**, nhưng **không tự xác thực nguồn phát hành**. Nếu cho phép các thuật toán hoặc URL JWKS tùy ý từ header, attacker có thể lách hệ thống xác minh dù có `typ=at+jwt`.

### Nếu hệ thống dùng JWT access token không theo RFC 9068?

Không phải mọi AS đều phát hành JWT access token RFC 9068. Một hệ thống legacy có thể dùng `typ: JWT` hoặc thiếu `typ`. Khi đó, phải có **hợp đồng token được cấu hình riêng**, với ranh giới xác nhận đủ mạnh bằng issuer, audience, khóa, claims bắt buộc và nơi nhận; có thể cần phân tách khóa/profile hoặc chuyển dần sang explicit typing.

**Không “sửa” bằng cách tắt kiểm tra type toàn hệ thống.** Nếu API A có policy mới còn API B là legacy, cấu hình ngoại lệ nên được giới hạn rõ cho đúng issuer/API và được kiểm thử chống nhầm ID token. Hệ thống mới nên ưu tiên kiểu token có chỉ báo mục đích rõ ràng.

## 6. OAuth `token_type`: Bearer hay DPoP là cách trình access token

Một token response OAuth có thể trông như sau:

~~~json
{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Ở đây `token_type=Bearer` quy định **cơ chế sử dụng** access token: client gửi giá trị token theo RFC 6750, phổ biến là header:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Trong trường hợp sender-constrained DPoP được hỗ trợ, response có thể sử dụng:

~~~json
{
  "access_token": "<DPOP_BOUND_ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Client cần trình token bằng cơ chế DPoP tương ứng, bao gồm proof hợp lệ. Cả Bearer và DPoP **không nói token bên trong là JWT hay opaque**. Mặt khác, JWT có `typ: at+jwt` không tự chứng minh nó được gửi theo cơ chế Bearer thay vì DPoP; AS/RS phải thỏa thuận và kiểm tra binding.

**Không nhầm:**

- `token_type` trong token response: *cách dùng access token*.
- `typ` trong JOSE protected header: *loại đối tượng JWT* theo profile.
- `token_type_hint` khi introspection/revocation: *gợi ý để AS tìm token*, không phải bằng chứng quyền/loại token.
- `grant_type`: *cách client yêu cầu token*, không phải usage tại API.

## 7. API phải xác minh JWT access token theo đúng purpose

Một Resource Server kiểm tra JWT đã ký (JWS) cần dùng thư viện xác minh được duy trì và một chính sách xác minh **riêng cho access token**.

Quy trình khuyến nghị:

1. **Nhận token từ đường hỗ trợ:** lấy từ `Authorization` theo scheme được cấu hình, giới hạn kích thước và từ chối nhiều credential mâu thuẫn.
2. **Chọn profile tin cậy từ cấu hình endpoint:** biết issuer, audience, JOSE algorithm allowlist và token purpose cần nhận; không để attacker chọn verifier không kiểm soát.
3. **Kiểm tra cấu trúc JOSE và token type:** nếu áp dụng RFC 9068, header `typ` phải hợp lệ cho JWT access token; không lấy một ID token có `typ=JWT` để “thử tiếp” như access token.
4. **Xác minh mật mã:** chữ ký JWS và khóa đã đăng ký từ issuer; kiểm soát `alg`, `kid` và nguồn JWKS. Từ chối `alg=none`, key confusion, URL `jku`/`x5u` tùy ý và sự hạ cấp thuật toán.
5. **Xác minh claims ràng buộc:** `iss` đúng, `aud` chứa resource/API dự kiến, `exp` và `nbf` hợp lệ, các claim bắt buộc theo profile. Độ lệch đồng hồ phải nhỏ và có giới hạn.
6. **Kiểm tra mục đích một cách độc lập:** không nhận JWT client assertion, ID token, DPoP proof hoặc JWT khác thay access token, dù có cùng issuer và thuật toán.
7. **Kiểm tra trạng thái/binding:** thu hồi/denylist nếu cần; nếu token ràng buộc DPoP/mTLS, yêu cầu bằng chứng sở hữu khóa trên request.
8. **Kiểm tra scope và quyền đối tượng:** token có `orders:read` chưa chắc cho phép đọc đơn của người khác; kiểm tra ACL/tenant và chính sách nghiệp vụ.
9. **Fail closed:** khi có lỗi, trả phản hồi thích hợp, không dùng payload chưa xác minh để lấy user ID hoặc role.

### Ma trận kiểm tra claim

| Trường | Ý nghĩa | Không được chấp nhận khi |
|---|---|---|
| `iss` | Nguồn phát hành token | Không khớp issuer được cấu hình/tin cậy |
| `aud` | Resource Server dự kiến | Token dành cho API hoặc client khác |
| `exp` | Hạn cuối hiệu lực | Đã hết hạn theo đồng hồ tin cậy |
| `nbf` | Thời điểm bắt đầu hiệu lực nếu có | Chưa tới thời điểm hiệu lực |
| `iat` | Thời điểm phát hành | Bất thường/không hợp lệ theo policy và profile |
| `scope` | Phạm vi quyền đã cấp | Thiếu scope endpoint yêu cầu |
| `client_id` | Client đã được cấp token theo profile | Client bị policy hạn chế hoặc token không ràng buộc đúng client khi cần |
| `sub` | Chủ thể theo profile issuer | Subject không được phép truy cập object; không tự đoán là email |
| `cnf` | Bằng chứng khóa liên kết khi sender-constrained | Request không chứng minh khóa tương ứng |

Trạng thái thu hồi có thể **không** thể hiện ngay trong JWT được ký. Nếu quyền user bị gỡ hoặc grant bị revoke, API cần cơ chế bổ sung (denylist/introspection/policy lookup/token ngắn hạn) theo mức độ cần chặn ngay.

## 8. ID token dùng cho OIDC client, không dùng để gọi API

Trong OIDC, **ID token** thông báo cho client về sự kiện xác thực người dùng. Nó thường được ký dưới dạng JWT; tuy nhiên, `typ` trong ID token có thể là `JWT` hoặc không có tùy profile, nên **không dùng một giá trị `typ` duy nhất để xác định và chấp nhận ID token**.

Payload ID token minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "orders-web",
  "iat": 1800000000,
  "exp": 1800000600,
  "nonce": "oidc-nonce-example-15",
  "auth_time": 1800000000
}
~~~

So sánh với access token ở mục 5:

| Câu hỏi | Access token cho Orders API | ID token OIDC |
|---|---|---|
| **Bên nhận dự kiến** | Resource Server / Orders API | Relying Party / `orders-web` |
| **Audience thường gặp** | `https://orders-api.example.test` | Client ID `orders-web` |
| **Mục đích** | Cấp quyền truy cập API | Cung cấp thông tin xác thực user cho client |
| **Kiểm tra tiêu biểu** | Token profile, signature/status, `iss`, `aud`, `exp`, scope, object policy | Signature, `iss`, `aud` client ID, `exp`, `nonce` khi đã gửi, `azp`/`auth_time` khi yêu cầu |
| **Có gửi tới API nghiệp vụ không?** | Có, nếu đúng audience và usage | **Không**, trừ một giao thức khác được định nghĩa riêng; không coi nó là access token |
| **Đủ điều kiện tạo session?** | Không tự động khẳng định đã login | Client có thể tạo session sau khi kiểm tra OIDC thành công |

**Client OIDC cần xác minh** chữ ký của issuer đáng tin, audience của chính client, các mốc thời gian, `nonce` nếu request đã dùng, `azp` nếu áp dụng và `auth_time` khi yêu cầu xác thực gần đây; đồng thời kiểm tra các yêu cầu khác của profile và flow.

Một **ID token có chữ ký hợp lệ** và `aud=orders-web` vẫn phải bị **Orders API từ chối** vì API không phải audience tương ứng và token không phải access token dành cho Resource Server.

### Trường hợp nguy hiểm: cùng issuer, cùng khóa ký

AS có thể sử dụng một nhóm khóa để ký nhiều loại JWT. Nếu API chỉ kiểm tra **chữ ký đúng với JWKS của AS và `sub` tồn tại**, một ID token được đưa vào `Authorization: Bearer` có thể bị chấp nhận sai.

Cách chống:

- Explicit typing khi profile cho phép, ví dụ `typ=at+jwt` với RFC 9068.
- **Audience riêng biệt**: ID token cho client ID, access token cho API.
- Các claim và validation rule **khác nhau** cho từng loại token.
- Phân tách khóa/issuer/validation endpoints theo khả năng thiết kế, giảm việc một loại JWT bị dùng thay loại khác.
- Test âm tính: ID token ký đúng vẫn không gọi được API.

Đây là **cross-JWT confusion**: chữ ký là điều kiện cần nhưng **không đủ để quyết định cách sử dụng token**.

## 9. Refresh token chỉ dùng tại token endpoint

**Refresh token** đại diện khả năng xin access token mới theo grant đã cấp. Nó thường là chuỗi **opaque bí mật**; nếu hệ thống chọn định dạng khác, nó vẫn không trở thành access token.

Client có thể gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <AUTHENTICATED_CONFIDENTIAL_CLIENT>

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>&scope=orders%3Aread
~~~

Token endpoint cần xác minh:

1. Refresh token có do AS này cấp và đúng **loại refresh token** không; còn hiệu lực, chưa thu hồi hay rotation không?
2. Client có đúng là client được cấp refresh token không; confidential client đã xác thực theo phương thức đăng ký chưa?
3. Refresh token/grant có còn được phép sử dụng, có đúng tenant/resource/user context không?
4. Scope được yêu cầu có nằm trong phạm vi grant đã cấp (không tự nâng quyền) không?
5. Nếu có rotation/sender constraint, token family, reuse detection và bằng chứng khóa đã được kiểm tra chưa?
6. Khi cấp access token mới, scope, audience, TTL và chính sách hiện tại có đúng không?

**API nghiệp vụ không bao giờ chấp nhận refresh token làm access token** chỉ vì chuỗi có thể parse thành JWT hoặc introspection trả một vài trường. Token không đúng usage phải bị từ chối.

### Reuse và replay

Với refresh token rotation, `RT1` được đổi thành `RT2`; AS vô hiệu hóa `RT1`. Nếu có request tiếp tục dùng `RT1`, đó có thể là dấu hiệu replay và AS cần phản ứng theo chính sách (ví dụ revoke token family). Cũng phải xét các request refresh đồng thời hợp lệ để tránh false positive.

Client authentication bằng secret/private key **không tự thay thế kiểm tra refresh token-client binding**. Một client A đã xác thực hợp lệ vẫn không được dùng refresh token cấp cho client B.

## 10. Authorization code và client assertion không phải access token

Một số hiện vật khác cũng có thể trông giống token JWT hoặc chuỗi ngẫu nhiên:

| Hiện vật | Cơ chế và nơi sử dụng | API nghiệp vụ có nhận không? |
|---|---|---|
| **Authorization code** | Dùng một lần tại AS token endpoint với ràng buộc client, redirect URI, PKCE | Không |
| **Client assertion JWT** | Confidential client ký assertion và gửi token endpoint để xác thực client | Không |
| **JWT bearer authorization grant** (khi có profile RFC 7523) | Client gửi assertion tới AS theo một grant được cấu hình, AS kiểm tra audience và các claim đặc thù | Không phải access token API |
| **DPoP proof JWT** | Chứng minh người gửi sở hữu khóa gắn với request và token | Không thay access token |
| **OIDC logout token** (nếu có OpenID Connect Back-Channel Logout) | Thông báo sự kiện logout đến endpoint client đúng profile | Không |

Ví dụ client assertion `private_key_jwt` có thể chứa:

~~~json
{
  "iss": "orders-bff",
  "sub": "orders-bff",
  "aud": "https://auth.example.test/oauth2/token",
  "iat": 1800000000,
  "exp": 1800000060,
  "jti": "client-assertion-42"
}
~~~

Assertion này **dành cho AS**. Resource Server không được coi nó là access token dù chữ ký hợp lệ vì audience là token endpoint và claims nói về **danh tính client**, không phải grant truy cập API.

AS cũng không được nhận một **ID token** làm client assertion chỉ vì cả hai đều là JWT có chữ ký, hoặc nhận một authorization code thuộc client khác chỉ vì request có credential client hợp lệ. Mỗi loại có **quy tắc issuer, audience, client binding, hạn dùng và chống replay riêng**.

## 11. Opaque token: không nhìn hình thức để đoán mục đích

Opaque access token thường không có claims mà API tự decode được. API phải dùng **introspection hoặc cơ chế tra trạng thái đáng tin cậy** mà AS và Resource Server đã thỏa thuận.

Ví dụ Resource Server yêu cầu introspection:

~~~http
POST /introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <RESOURCE_SERVER_AUTHENTICATION>

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

AS có thể trả:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "token_type": "Bearer",
  "exp": 1800000600
}
~~~

**Quan trọng về `token_type_hint`:** `access_token` trong request introspection là một **gợi ý** để AS tìm đúng token hiệu quả, không phải bằng chứng rằng chuỗi nhận được thực sự là access token. AS phải kiểm tra token trong hệ thống của mình, còn API chỉ được tin **kết quả từ nguồn introspection đã xác thực và đúng hợp đồng**.

Tương tự, `token_type: Bearer` trong introspection phản ánh cơ chế bearer, **không phải bằng chứng độc lập rằng token có purpose “access token”**. Cần bảo đảm AS/introspection endpoint chỉ cung cấp thông tin thích hợp cho Resource Server đang xác thực, và rằng API không thể được lừa sử dụng refresh token hoặc hiện vật khác làm access token.

### Cách sử dụng kết quả introspection

1. Gọi endpoint qua TLS, **xác thực Resource Server** theo quy tắc AS.
2. Chỉ tin response từ AS đã cấu hình; không cho client chọn introspection URL.
3. Từ chối nếu `active` không phải `true` hoặc thiếu thông tin bắt buộc.
4. Kiểm tra issuer/resource/audience, scope, expiry và token purpose theo hợp đồng AS/RS.
5. Kiểm tra sender constraint nếu introspection trả token-bound metadata.
6. Kiểm tra quyền user/client và đối tượng dữ liệu.
7. Giới hạn cache theo `exp` và yêu cầu thu hồi; cache có thể làm chậm tác dụng revocation.

**Không có quy tắc “JWT Compact ba phân đoạn là access token, còn chuỗi không có dấu chấm là refresh token”**. Hình thức không bảo đảm mục đích, đặc biệt khi AS dùng nhiều token format hoặc nested/JWE token.

## 12. DPoP và mTLS: token usage có thể yêu cầu bằng chứng khóa

Một access token **sender-constrained** không chỉ cần được ký/xác minh đúng mà còn cần **bên gọi chứng minh sở hữu khóa** tương ứng. Điều này giảm khả năng dùng một bản sao token riêng lẻ.

### DPoP

Trong OAuth 2.0 DPoP (RFC 9449), access token có thể được cấp với `token_type: DPoP`. Một request điển hình:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

Resource Server phải xác minh ít nhất các ràng buộc thích hợp:

- Access token hợp lệ, đúng issuer, audience, scope và thời gian.
- Proof JWT có JOSE type `dpop+jwt`, chữ ký hợp lệ bằng public key được chỉ ra đúng chuẩn; thuật toán phù hợp, không dùng `none`.
- `htm` và `htu` trong proof tương ứng HTTP method và URI mục tiêu theo quy tắc chuẩn hóa của DPoP.
- `iat` nằm trong cửa sổ chấp nhận; `jti` chưa dùng lại theo chính sách chống replay.
- `ath` trong proof ràng buộc với **access token thực sự được trình**; tính/hash theo RFC 9449.
- JWK thumbprint của khóa proof khớp ràng buộc trong token, thường là `cnf.jkt`.
- `nonce` khi AS/RS yêu cầu, cùng các bước kiểm tra bổ sung theo profile.

Claims proof minh họa (chỉ payload, **không phải proof JWT đã ký**):

~~~json
{
  "htm": "GET",
  "htu": "https://orders-api.example.test/orders/123",
  "iat": 1800000010,
  "jti": "proof-request-cc1",
  "ath": "<BASE64URL_SHA256_OF_ACCESS_TOKEN>"
}
~~~

**Không nhận DPoP proof thay access token.** Proof là bằng chứng sở hữu khóa liên quan **request và access token**, không có `scope` hoặc grant API thay thế access token. DPoP proof cũng **không tự động là client authentication** cho danh tính client được đăng ký.

### mTLS certificate-bound access token

Theo RFC 8705, AS có thể phát hành access token ràng buộc với client certificate; metadata token có thể chứa `cnf` với thumbprint certificate như `x5t#S256`. Resource Server phải đối chiếu bằng chứng TLS client certificate tương ứng tại request API. Chỉ kiểm tra signature của token mà **bỏ qua certificate binding** sẽ làm mất ý nghĩa sender constraint.

**mTLS client authentication tại token endpoint** và **mTLS-bound access token tại API** là hai cơ chế liên quan nhưng độc lập: xác thực client khi xin token không tự bảo đảm mọi API call sau đó được chứng minh bằng certificate.

## 13. JWE, nested JWT và format-specific validation

JWT có thể ở dạng **JWS** (thường ba phân đoạn trong Compact Serialization) hoặc **JWE** (thường năm phân đoạn). Điều đó nói về **cách bảo vệ nội dung** chứ không tự chỉ ra token là access hay ID token.

Với JWE, payload mã hóa không thể Base64url decode trực tiếp thành JSON claims. Resource Server/Client cần **giải mã bằng khóa phù hợp, xác minh cơ chế xác thực mã hóa, rồi kiểm tra token purpose và claims**. Nếu JWE chứa JWS (nested JWT), cần thực hiện đúng thứ tự xử lý/kiểm tra của profile, không dừng ở bước “giải mã thành công”.

Một hệ thống có thể gặp:

- JWT access token JWS: chữ ký và claims được API xác minh.
- JWT access token JWE: API hoặc thành phần được chỉ định giải mã/xác minh theo profile.
- OIDC ID token ký/mã hóa: chỉ client OIDC được chỉ định xử lý để xác nhận authentication.
- Opaque access token: API dùng introspection.
- Refresh token dạng opaque hay định dạng nội bộ: chỉ AS token endpoint xử lý.

**Không xây thuật toán tự đoán usage dựa vào số dấu chấm, độ dài, ký tự Base64url hoặc việc payload có `sub`.** Token purpose là hợp đồng giữa issuer và bên nhận, được thực thi bằng profile/metadata, audience và kiểm tra bảo mật.

## 14. Java: tách bộ xác minh theo từng token purpose

Trong ứng dụng Java/Spring Security, nên cấu hình **bộ xác minh access token riêng cho Resource Server**, **bộ kiểm tra ID token riêng tại OIDC Client** và **logic refresh token riêng tại AS**. Không dùng một hàm `decodeJwt()` chung rồi trả claims cho mọi endpoint.

Pseudo-interface Java 17 sau cho thấy cách **tách trách nhiệm**, không phải API thực của thư viện; implementation cần dùng thư viện JWT/OAuth đã được kiểm thử:

~~~java
import java.time.Instant;
import java.util.Set;

public final class TokenPurposeExample {
    private TokenPurposeExample() {}

    // Chỉ được tạo sau khi verifier đáng tin đã kiểm tra
    // format/profile, signature hoặc introspection, type,
    // issuer, audience, expiry và sender constraint nếu có.
    public record VerifiedApiAccess(
            String issuer,
            Set<String> audiences,
            String subject,
            Set<String> scopes,
            Instant expiresAt
    ) {}

    public interface AccessTokenVerifier {
        VerifiedApiAccess verifyForOrdersApi(
                String rawAccessToken,
                String requestMethod,
                String requestUri,
                String dpopProofOrNull
        ) throws TokenValidationException;
    }

    public static class TokenValidationException
            extends Exception {
        public TokenValidationException(String message) {
            super(message);
        }
    }

    public interface OrderPolicy {
        boolean mayRead(String subject, String orderId);
    }

    public static int decideReadOrder(
            VerifiedApiAccess access,
            String orderId,
            OrderPolicy policy
    ) {
        // Một lớp phòng vệ bổ sung. Bộ verifier vẫn phải
        // từ chối token sai type, issuer, audience hoặc time.
        if (!access.audiences().contains(
                "https://orders-api.example.test")) {
            return 401;
        }

        if (!access.expiresAt().isAfter(Instant.now())) {
            return 401;
        }

        if (!access.scopes().contains("orders:read")) {
            return 403;
        }

        return policy.mayRead(access.subject(), orderId) ? 200 : 403;
    }
}
~~~

**Giới hạn bảo mật của ví dụ:**

- `VerifiedApiAccess` là dữ liệu **đã xác minh**, không phải kết quả Base64url decode hoặc JSON do client gửi. Java record này không tự chống được việc một lập trình viên tạo instance giả, vì vậy trong triển khai thật cần tổ chức API/middleware để chỉ verifier có quyền tạo security principal được tin cậy.
- Method `verifyForOrdersApi` cần ràng buộc **đúng token purpose (access)**, issuer, audience, JOSE type/profile, signature/introspection, TTL và DPoP/mTLS proof (nếu được yêu cầu); interface không tự thực hiện các bước đó.
- Scope và `OrderPolicy` chỉ được dùng **sau khi verifier thành công**. Không dùng ID token OIDC hoặc refresh token để tạo `VerifiedApiAccess`.
- Kết quả 401/403 chỉ minh họa phân loại. Code ứng dụng cần xây HTTP response và `WWW-Authenticate` đúng giao thức, tránh lộ thông tin đối tượng; kết quả đọc dữ liệu thật còn phụ thuộc controller/database.

### Pseudocode Resource Server cho token type/usage

~~~text
function authenticateApiRequest(request):
    scheme, rawToken = parseConfiguredAuthorizationHeader(request)

    if scheme not supported or rawToken absent:
        reject(401)

    policy = ordersApiTokenAcceptancePolicy
    // Ví dụ: trusted issuer, accepted token formats and profiles,
    // purpose=ACCESS, audience=Orders API, allowed auth schemes.

    if scheme == "Bearer":
        reject if policy requires sender-constrained access
        access = policy.accessTokenVerifier.validateBearer(rawToken)

    else if scheme == "DPoP":
        proof = request.header("DPoP")
        access = policy.accessTokenVerifier.validateDpopBound(
            rawToken, proof, request.method, request.targetUri
        )

    // Do not parse ID/refresh/client_assertion in an API verifier.
    reject if access invalid or wrong token purpose

    require scope for endpoint
    require resource ownership, tenant and application policy
    continue request
~~~

Việc `validateBearer`/`validateDpopBound` có thể sử dụng JWS verifier hoặc opaque introspection tùy contract. Không nên dùng mẹo “thử ID-token verifier nếu access-token verifier lỗi”, vì như vậy đã mở đường cho token confusion.

## 15. Phản hồi lỗi và audit theo nguyên nhân, không chỉ theo chữ ký

Khi token sai mục đích, API cần phản hồi có kiểm soát, không tiết lộ raw token hoặc thông tin cấu hình nhạy cảm.

| Tình huống | Cách xử lý phù hợp | Nhóm audit nội bộ |
|---|---|---|
| Thiếu access token | Thường `401` và Bearer challenge nếu dùng Bearer | `TOKEN_MISSING` |
| ID token được trình như access token | Từ chối `401`/`invalid_token` theo profile | `WRONG_TOKEN_PURPOSE` |
| JWT access token thiếu `typ=at+jwt` khi policy RFC 9068 bắt buộc | Từ chối | `INVALID_TOKEN_TYPE` |
| Access token đúng purpose nhưng sai `aud` | Từ chối `401` | `INVALID_AUDIENCE` |
| Access token hết hạn | Từ chối `401` | `EXPIRED_TOKEN` |
| Token hợp lệ nhưng thiếu `orders:read` | Thường `403`, có thể `insufficient_scope` | `INSUFFICIENT_SCOPE` |
| Token hợp lệ, đủ scope nhưng user không có quyền trên order | `403` hoặc `404` theo policy | `OBJECT_POLICY_DENIED` |
| DPoP-bound token không có proof hoặc proof sai | Từ chối theo DPoP profile | `DPOP_PROOF_INVALID` |
| Refresh token gửi trực tiếp tới API | Từ chối, không chuyển sang token endpoint thay client | `WRONG_TOKEN_PURPOSE` |
| Refresh token sai client hoặc đã rotation | AS từ chối grant; dùng error phù hợp như `invalid_grant` | `REFRESH_BINDING_OR_REUSE` |

Ví dụ Bearer challenge khi access token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Khi token hợp lệ nhưng thiếu scope, Resource Server có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:read"
~~~

Lỗi DPoP có thể có cách challenge và nonce riêng theo RFC 9449; không áp dụng mù quáng mọi mã lỗi Bearer sang DPoP.

**Không log raw access/refresh/ID token, DPoP proof, client assertion, authorization code, PKCE verifier, secret hoặc session cookie.** Log nên dùng mã sự kiện, issuer/client ID hợp lệ, audience, route template, reason code, token reference pseudonym, correlation ID và thời điểm. Nếu token chưa được xác minh, không ghi `sub` của payload untrusted như một chủ thể đã xác thực.

## 16. Case study: bốn token cùng một AS, nhưng chỉ một token hợp lệ cho API

Giả sử `auth.example.test` là issuer tin cậy. Ứng dụng `orders-web` đăng nhập user `user-42` và được cấp:

1. **Access token A**: JWT theo RFC 9068, `typ=at+jwt`, `aud=https://orders-api.example.test`, `scope=orders:read`, còn hiệu lực.
2. **ID token I**: JWT OIDC, `aud=orders-web`, `nonce` khớp login request, chữ ký hợp lệ.
3. **Refresh token R**: opaque, chỉ dùng ở `/oauth2/token` để xin token mới và ràng buộc với `orders-web`.
4. **Client assertion C**: JWT ký bởi `orders-bff`, `aud=https://auth.example.test/oauth2/token`, dùng xác thực client.

Orders API có policy **chỉ nhận access token dành cho chính nó**. Kết quả:

| Credential mà client trình cho Orders API | Kết quả | Lý do |
|---|---|---|
| Token A, Bearer đúng, scope và quyền trên order phù hợp | **Có thể cho phép** | Đúng type, issuer, audience, time và policy |
| Token I, chữ ký hợp lệ | **Từ chối** | ID token dành cho OIDC client, `aud` sai API |
| Token R (opaque) | **Từ chối** | Refresh token dành cho AS token endpoint |
| Assertion C (JWT) | **Từ chối** | Dùng xác thực client tại AS, audience là token endpoint |
| Token A gửi tới Billing API | **Từ chối ở Billing API** | Sai audience |
| Token A bị sửa scope thành `orders:write` rồi Base64url encode lại | **Từ chối** | Chữ ký JWS không còn hợp lệ |
| Token A hợp lệ nhưng user không được xem order `999` | **Từ chối** | Thiếu quyền tài nguyên, dù token hợp lệ |
| Token A đã hết `exp` | **Từ chối** | Hết hạn; client cần token mới theo grant |
| Access token DPoP-bound nhưng chỉ gửi Bearer token, không proof | **Từ chối** | Thiếu bằng chứng khóa theo usage |
| Token A bị thu hồi nhưng API không kiểm tra trạng thái thu hồi | **Có rủi ro còn được chấp nhận đến `exp`** | Cần cơ chế revoke/denylist/introspection hoặc thời hạn ngắn theo policy |

**Điểm mấu chốt:** token I và assertion C **có thể có chữ ký số hợp lệ**; đó không phải lỗi ký. Việc sử dụng chúng ở Orders API vẫn sai vì **purpose và audience**. Ngược lại, access token A đúng type cũng không tự cấp quyền trên mọi đơn hàng.

### Những quyết định tại AS

Khi `orders-web` gửi R để xin token mới, AS cần kiểm tra refresh token còn hiệu lực, chưa dùng lại ngoài chính sách rotation, đúng client/grant, scope và audience được phép. AS **không** lấy nội dung từ ID token I để tự cấp access token A mới chỉ vì cả hai có `sub=user-42`.

Khi `orders-bff` gửi assertion C, AS xác minh private key JWT client authentication theo registration; assertion chỉ chứng minh client theo profile, **không thay** việc kiểm tra authorization code hoặc refresh grant.

## 17. Ma trận kiểm thử âm tính chống token confusion

Một bộ kiểm thử tốt phải **cố ý đưa đúng token vào sai chỗ**, không chỉ kiểm tra case thành công.

| Test | Đầu vào | Kết quả mong đợi |
|---|---|---|
| **T1 — Correct access token** | JWT `at+jwt`, đúng issuer/aud/scope/expiry | Qua lớp token validation; vẫn xét quyền tài nguyên |
| **T2 — ID token substitution** | ID token ký đúng cùng issuer nhưng `aud=client_id` | Resource Server từ chối |
| **T3 — Refresh token substitution** | Refresh token opaque gửi vào `Authorization` API | API từ chối |
| **T4 — Client assertion substitution** | Assertion JWT có `aud=token endpoint` | API từ chối |
| **T5 — DPoP proof substitution** | Chỉ có DPoP proof JWT mà không có access token | API từ chối |
| **T6 — Wrong audience** | Access token Orders tại Billing API | Billing từ chối |
| **T7 — Wrong type** | JWT `typ=JWT` hoặc thiếu `typ` khi API buộc RFC 9068 | API từ chối, không fallback tùy tiện |
| **T8 — Forged type** | Sửa `typ` hoặc `scope` rồi giữ chữ ký cũ | Xác minh chữ ký thất bại |
| **T9 — Unknown issuer/key** | JWT có `jku` trỏ endpoint attacker | Không tải/tin khóa tùy ý; từ chối |
| **T10 — Expired/not-yet-valid** | `exp` quá hạn hoặc `nbf` ở tương lai | Từ chối |
| **T11 — Missing scope** | Access token hợp lệ nhưng thiếu scope | Thường `403 insufficient_scope` |
| **T12 — BOLA/tenant** | Đủ scope, sai quyền trên object | Từ chối theo object policy |
| **T13 — DPoP mismatch** | DPoP access token + proof sai `ath`/`htm`/`htu`/`jkt` | Từ chối |
| **T14 — DPoP replay** | Dùng lại proof `jti` trong cửa sổ chống replay | Từ chối theo policy |
| **T15 — Refresh token cross-client** | Client B dùng refresh token của A | AS từ chối `invalid_grant`/chính sách phù hợp |
| **T16 — Revocation** | Token/grant bị thu hồi, tiếp tục request | Kết quả theo chiến lược chặn và SLA thu hồi; không mặc định revoke tức thì với JWT offline |

Khi chạy test, cần đặt **cùng issuer, cùng khóa ký** cho một số token thuộc các purpose khác nhau để chắc chắn API không chỉ dựa vào chữ ký. Cũng cần test khi có hai issuer hoặc các profile legacy để ngăn “cross-issuer confusion”.

Lưu ý **test T16**: nếu policy yêu cầu từ chối ngay sau thu hồi, hệ thống phải có biện pháp trạng thái tương ứng. Nếu chấp nhận token hết hạn tự nhiên, test cần xác nhận giới hạn thời gian/không có refresh tiếp; không được hứa bảo đảm tức thời khi kiến trúc không có.

## 18. Checklist triển khai kiểm tra type và usage

1. **Định nghĩa acceptance policy theo từng endpoint:** loại token, issuer, audience, thuật toán, format, claim bắt buộc và cách sử dụng.
2. **Tách các hiện vật:** access token cho Resource Server, ID token cho OIDC client, refresh token cho token endpoint, authorization code cho code exchange, client assertion cho AS.
3. **Không nhầm các trường tên gần giống:** `token_type` (Bearer/DPoP), JWT `typ` (at+jwt/dpop+jwt), `token_type_hint` và `grant_type`.
4. **Áp dụng explicit typing khi profile hỗ trợ:** với RFC 9068, yêu cầu JWT `typ=at+jwt` đúng quy tắc; không mặc định mọi JWT đều là access token.
5. **Xác minh chữ ký hoặc introspection trước khi tin claims:** không dựa trên Base64url decode, `kid`/`jku` tự khai hoặc thuật toán tùy ý.
6. **Luôn kiểm tra `iss` và `aud`:** token API A không được dùng cho API B; ID token cho client không được dùng gọi API.
7. **Kiểm tra thời gian và trạng thái:** `exp`, `nbf`, clock skew hợp lý, revocation/denylist khi cần.
8. **Kiểm tra sender constraint:** DPoP `ath`, `htm`, `htu`, `jti`, `cnf.jkt`; mTLS-bound certificate thumbprint nếu áp dụng.
9. **Phân quyền đúng:** scope được cấp, client/user/tenant và quyền đối tượng; không thay object policy bằng kiểm tra type.
10. **Bảo vệ refresh token tại AS:** đúng client/grant, rotation/reuse detection, không cấp thêm scope ngoài grant.
11. **Không trộn verifier:** Resource Server không “thử” OIDC ID token decoder sau khi access token validator từ chối.
12. **Không suy đoán theo hình thức:** JWT/opaque/JWE và số dấu chấm không phải tiêu chí xác định purpose.
13. **Ghi audit an toàn:** token purpose, failure reason, issuer/audience phù hợp và correlation; không log raw token hoặc secret.
14. **Test các trường hợp sai usage:** ID/refresh/assertion/proof tại API, access token sai audience, typ giả, replay và token sau thu hồi.
15. **Rà soát chuẩn/profile khi nâng cấp:** nhiều issuer, legacy token, token exchange và downstream API cần policy mục đích riêng.

**Ghi nhớ:** một token chỉ được chấp nhận khi **đúng điểm nhận, đúng mục đích, đúng cách trình, được xác minh bằng nguồn tin cậy, còn hiệu lực và đáp ứng scope/chính sách tài nguyên**. Kiểm tra chữ ký, giải mã JWT hoặc thấy `active: true` chỉ là **một phần** của quá trình đó. Việc tách đúng *token type* và *usage* là lớp bảo vệ quan trọng chống **token substitution, cross-JWT confusion và replay**.

### Tài liệu chuẩn để tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization grant, access token, refresh token, `token_type` và token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách trình bearer token và xử lý lỗi.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims và `typ` trong JWT.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515) và [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): bảo vệ mật mã và định dạng JOSE.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): explicit typing, algorithm validation và cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token profile và `typ=at+jwt`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token validation và audience dành cho client.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `token_type` và trạng thái opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint và `token_type_hint`.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, thumbprint binding và chống replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc certificate và token usage.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): quản lý token, refresh và yêu cầu bảo mật OAuth hiện đại.
