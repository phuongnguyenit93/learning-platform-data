# Audience confusion

**Audience confusion** là lỗi bảo mật xảy ra khi một hệ thống chấp nhận **token hợp lệ về mặt mật mã** nhưng **không được phát hành cho chính hệ thống đó**. Trong OAuth 2.0/OIDC, attacker có thể lấy một **access token** dành cho API A rồi trình nó tới API B, hoặc đưa **ID token** dành cho OIDC client tới Resource Server (RS). Nếu bên nhận chỉ kiểm tra chữ ký, `iss`, `exp` hoặc `scope` mà bỏ qua **audience (`aud`)** và **token purpose**, token của bối cảnh này có thể bị dùng sai ở bối cảnh khác.

Bài học thuộc chương **Threats** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, trong phạm vi mô hình tin cậy và vòng đời token: phân biệt JWT với opaque token, access/refresh/ID token, xác thực, phân quyền OAuth 2.0/OIDC, phát hành, kiểm tra claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại.

**Nguyên tắc xuyên suốt:** một Resource Server phải **chỉ chấp nhận access token mà Authorization Server (AS) tin cậy đã phát hành cho Resource Server đó**, với token type, issuer, thời hạn, scope và binding phù hợp. Chữ ký hợp lệ chứng minh **bên ký** và **tính toàn vẹn**, không chứng minh **mọi dịch vụ đều là người nhận hợp lệ**.

> Một token có thể **valid** ở Billing API và **invalid** ở Orders API trong cùng một thời điểm, dù hai API dùng chung issuer và JWKS. Đây là hành vi đúng, không phải lỗi của OAuth.

## 1. Audience confusion giải quyết câu hỏi nào?

Hãy hình dung hệ thống có một issuer `https://auth.example.test` và ba thành phần:

- **`orders-web`:** OIDC/OAuth client cho người dùng đăng nhập.
- **`orders-api`:** API đọc và sửa đơn hàng.
- **`billing-api`:** API xử lý hóa đơn.

AS phát token `T_BILLING` có:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://billing-api.example.test",
  "client_id": "orders-web",
  "scope": "billing:read",
  "exp": 1800003600
}
~~~

Giả sử JWT thực tế có chữ ký đúng, chưa hết hạn tại thời điểm kiểm tra và được phát hành cho client `orders-web`. **Orders API vẫn phải từ chối** khi nhận `T_BILLING`, vì `aud` trỏ tới **Billing API**, không phải Orders API.

Một triển khai sai thường làm thế này:

~~~text
verify JWT signature        PASS
check iss                   PASS
check exp                   PASS
check user exists           PASS
check some role/scope       PASS hoặc kiểm tra quá lỏng
--------------------------
allow request               SAI: chưa kiểm tra aud/purpose
~~~

Một triển khai đúng:

~~~text
verify token structure/type, signature, trusted key
check iss, exp, nbf and other profile claims
require access-token purpose
require aud contains THIS resource's configured audience
require scope/permissions for THIS endpoint
require sender proof, if bound token
require tenant/object-level policy
--------------------------
allow only if ALL checks PASS
~~~

Audience confusion thuộc nhóm **token substitution/cross-resource token misuse**. Nó không đòi attacker phá chữ ký, giải mã JWT hay biết private key; kẻ tấn công lợi dụng chính **sự thiếu ràng buộc người nhận** tại bên kiểm tra token.

## 2. Mô hình tin cậy: issuer, client và Resource Server

~~~mermaid
flowchart LR
    U["User"]
    C["OAuth/OIDC Client: orders-web"]
    AS["Authorization Server: auth.example.test"]
    O["Orders API: aud=orders-api"]
    B["Billing API: aud=billing-api"]
    JWKS[("Trusted JWKS của AS")]

    U -->|"Login / consent"| C
    C -->|"Authorization Code + PKCE"| AS
    AS -->|"Access token cho Orders"| C
    AS -->|"Access token cho Billing (nếu grant cho phép)"| C
    AS -->|"Publish signing public keys"| JWKS
    C -->|"Bearer token aud=orders"| O
    C -->|"Bearer token aud=billing"| B
    O -->|"Verify signature bằng key đúng issuer"| JWKS
    B -->|"Verify signature bằng key đúng issuer"| JWKS
~~~

Hai API có thể dùng **cùng một JWKS và issuer**, vì chữ ký được AS phát hành. Chính vì vậy, **chữ ký không phân biệt token dành cho API nào**: việc đó phải do **claim `aud` hoặc ràng buộc audience tương đương trong contract introspection** thực hiện.

Phân biệt năm định danh:

| Giá trị | Ai/điều gì được định danh? | Dùng để kiểm tra gì? |
|---|---|---|
| **`iss`** | Bên **phát hành** token, thường là AS/OP | Đúng issuer/tenant tin cậy |
| **`aud`** | **Bên nhận dự kiến** của token | Token có được dành cho chính RS/RP đang xử lý không |
| **`client_id`** | OAuth client được cấp/đứng sau grant | Client registration và policy, **không thay `aud`** |
| **`sub`** | Subject: user hoặc client/service identity tùy grant/profile | Identity/authorization của chủ thể, **không thay `aud`** |
| **`scope`** | Quyền hạn được cấp trong grant/access token | Hành động được phép, **không thay `aud`** |

**Đúng người dùng, đúng client và đúng issuer vẫn có thể sai audience.**

## 3. `aud` trong RFC 7519: chuỗi hoặc mảng

Trong JSON Web Token (RFC 7519), `aud` (*Audience*) là claim xác định các principal mà JWT được dự kiến dành cho. Một bên xử lý JWT **phải từ chối** khi claim audience có mặt mà **không xác định được chính mình trong tập audience**.

Hai cách biểu diễn chuẩn:

~~~json
{
  "aud": "https://orders-api.example.test"
}
~~~

~~~json
{
  "aud": [
    "https://orders-api.example.test",
    "https://reports-api.example.test"
  ]
}
~~~

- `aud` có thể là **chuỗi** hoặc **mảng các chuỗi**.
- So sánh StringOrURI theo RFC 7519 dùng **chuỗi chính xác, phân biệt chữ hoa–thường**, không tự biến đổi để “gần khớp”.
- Không được dùng `contains()` trên chuỗi để tìm một phần audience.
- Không được mặc định `aud` vắng mặt là “token cho mọi API”.
- Một JWT **chung** có thể không bắt buộc khai báo `aud` trong mọi use case; nhưng **OAuth JWT access token profile RFC 9068 yêu cầu claim này**, và RS cần ràng buộc audience theo contract của hệ thống.

Ví dụ:

~~~text
Expected audience:
    https://orders-api.example.test

Token aud:
    https://orders-api.example.test            => MATCH
    https://billing-api.example.test           => REJECT
    https://orders-api.example.test/admin      => REJECT
    https://orders-api.example.test/           => REJECT nếu config khác slash
    https://ORDERS-api.example.test            => REJECT theo exact string
    https://orders-api.example.test.attacker.tld => REJECT
    [https://billing-api.example.test,
     https://orders-api.example.test]          => MATCH về audience,
                                                 vẫn phải qua các checks khác
~~~

**Đừng tự lowercase hostname, bỏ slash, cắt path hoặc resolve DNS để so khớp audience.** Audience là **định danh logic được AS và RS thỏa thuận**, không phải URL mà ứng dụng cần thực sự gọi trong lúc validate. Sửa/chuẩn hóa nó ngầm có thể khiến hai định danh khác nhau bị xem là một.

## 4. Kịch bản tấn công: token Billing bị chấp nhận tại Orders

~~~mermaid
sequenceDiagram
    autonumber
    actor A as Attacker hoặc client bị chiếm
    participant AS as Authorization Server
    participant BA as Billing API
    participant OA as Orders API sai cấu hình

    A->>AS: Xin AT cho Billing theo grant hợp lệ
    AS-->>A: JWT T với aud=billing-api, iss hợp lệ
    A->>BA: GET /invoices với T
    BA->>BA: Verify signature, aud=billing, scope
    BA-->>A: Response theo quyền Billing
    A->>OA: GET /orders/123 với chính token T
    OA->>OA: Verify signature + exp + iss
    Note over OA: Thiếu check aud=orders-api
    OA-->>A: Dữ liệu Orders bị lộ nếu ACL/scope cũng yếu
~~~

**Điều kiện để khai thác:** attacker phải có một token được AS ký hợp lệ (có thể cấp cho chính họ ở service khác hoặc chiếm được của user), và RS đích phải kiểm tra thiếu hoặc kiểm tra sai audience/purpose. Chỉ riêng token audience sai **không chắc đã đủ** nếu scope, role, tenant và object-level ACL còn mạnh; nhưng thiếu audience vẫn là lỗ hổng độc lập cần sửa.

**Các lớp bảo vệ đúng:**

1. AS cấp access token với audience chỉ rõ resource được phép.
2. Orders API pin `expectedAudience=orders-api` và so khớp chính xác.
3. Orders API kiểm tra `scope=orders:read` hoặc quyền tương ứng.
4. Orders API kiểm tra quyền đối với **đơn hàng 123** của user/tenant.
5. Token đúng mục đích và sender proof khi áp dụng.

Một token được **cấp hợp pháp cho một API** có thể trở thành **vũ khí nhầm ngữ cảnh** nếu API khác bỏ audience check.

## 5. Phân biệt access token và ID token để chống cross-JWT confusion

OAuth access token và OIDC ID token có mục đích khác nhau:

| Token | Nơi nhận dự kiến | Audience thường gặp | Không được dùng làm gì? |
|---|---|---|---|
| **OAuth access token** | **Resource Server/API** | RS identifier, ví dụ `https://orders-api.example.test` | Không tự coi là ID token đăng nhập RP |
| **OIDC ID token** | **Relying Party/OIDC Client** | OAuth/OIDC `client_id` như `orders-web` | Không được dùng như bearer access token gọi Orders API |
| **Refresh token** | **Authorization Server token endpoint** | Ràng buộc grant/client theo AS, không nhất thiết JWT `aud` như AT | Không được gửi đến RS để gọi API |
| **Authorization code** | AS token endpoint theo flow | Code + redirect/client/PKCE binding | Không phải access token |
| **Device code** | AS token endpoint cho device grant | Device/client binding | Không phải token gọi API |

ID token payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "orders-web",
  "iat": 1800000000,
  "exp": 1800000600,
  "nonce": "nonce-for-oidc-request"
}
~~~

Access token JWT profile dành Orders API:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "access-token-pseudo-001"
}
~~~

**Cả hai JSON trên là payload giả để học, không phải JWT đã ký.** Chúng có `iss` và `sub` giống nhau nhưng **người nhận và mục đích khác nhau**. RS kiểm tra `aud=orders-web` rồi kết luận “ID token dành cho app này nên gọi Orders API được” là sai: client ID là đối tượng nhận ID token, không phải audience của access token.

### JWT type phân biệt token use

JWT access token theo **RFC 9068** có JOSE header `typ` mang giá trị `at+jwt` (hoặc dạng `application/at+jwt` được profile cho phép). Ví dụ header giả:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "orders-signing-2026"
}
~~~

Resource Server triển khai RFC 9068 cần kiểm tra **token type/profile** song song với chữ ký, issuer, audience, thời gian và scope. **Không chỉ dựa trên `typ`**: attacker không thể ký token với header giả nếu RS verify đúng, nhưng chính header `typ` tự nó **không** chứng minh token được AS cấp cho RS.

**Không áp tiêu chí RFC 9068 cho mọi token OAuth nếu AS chưa dùng profile này.** Nếu provider dùng opaque token hoặc JWT access token theo profile khác, cần hợp đồng xác thực rõ ràng mà RS kiểm tra được. Tuyệt đối không “bật ignore audience/typ” để tránh lỗi tích hợp.

## 6. `client_id`, `azp`, `sub` và `scope` không thay `aud`

Một sai sót phổ biến là **đối chiếu client ID thay cho resource audience**:

~~~text
JWT:
    iss       = https://auth.example.test
    client_id = orders-web
    aud       = https://billing-api.example.test
    scope     = billing:read

Orders API:
    if client_id == "orders-web":
        accept   # SAI: token vẫn dành cho Billing
~~~

**`client_id`** chỉ cho biết OAuth client có liên quan tới issuance. Một client có thể được cấp token cho **nhiều RS** trong những grant riêng.

**`azp`** (*authorized party*) là claim OIDC có thể xuất hiện trong **ID token**, đặc biệt liên quan ID token nhiều audience. Nó **không thay thế** check `aud` của access token ở Resource Server. Tự suy `azp=orders-web` nên Orders API được phép nhận mọi token của client là lỗi.

**`sub`** là chủ thể được cấp token; ở `client_credentials` flow, subject có thể là client/service principal tùy profile. Một RS nhận ra `sub=user-42` không chứng minh token dành cho RS đó hoặc có đủ scope.

**`scope`** mô tả quyền, không phải người nhận. Ngay cả khi hai API đều có một scope trùng tên như `read`, mỗi RS vẫn cần audience hợp lệ. Tránh scope tên quá chung và không dùng substring matching:

~~~java
// SAI: "orders:read:any" chứa "orders:read".
boolean allowed = scopeString.contains("orders:read");
~~~

Tách scope theo dấu cách và so khớp **phần tử chính xác**, nhưng **chỉ sau khi audience và token purpose đã đạt**.

## 7. Audience confusion có thể đi kèm issuer/multi-tenant confusion

Cùng hostname không có nghĩa cùng issuer, ví dụ:

~~~text
Issuer Retail:
    https://login.example.test/realms/retail

Issuer Admin:
    https://login.example.test/realms/admin

Orders API Retail chấp nhận:
    iss = https://login.example.test/realms/retail
    aud = https://orders-api.example.test/retail
~~~

Một token từ Admin tenant có thể có chữ ký hợp lệ theo keyset khác, hoặc một JWKS chung. Nếu Orders API cache JWK **chỉ theo `kid`**, không pin issuer và không so khớp `aud`, token từ tenant khác có thể bị nhầm.

Bảo vệ:

- **Issuer exact match** với issuer được pin cho tenant.
- **JWKS/key set gắn với issuer tin cậy**, không lấy URL từ JWT `jku`/`x5u` hoặc user input.
- **Audience exact match** trong context tenant/resource tương ứng.
- **Không dùng email hoặc subject đơn lẻ làm identity toàn cục**: cặp `(iss, sub)` thường phù hợp hơn.
- **Tenant/object authorization** sau khi token hợp lệ, không chỉ nhìn claim `tenant_id` từ payload chưa verify.

Một access token từ issuer tin cậy **nhưng audience sai** phải bị từ chối, kể cả khi cùng user/client và tenant.

## 8. Những điều kiện khiến lỗi đặc biệt nguy hiểm

| Bối cảnh | Tại sao audience confusion dễ xảy ra? | Biện pháp chính |
|---|---|---|
| **Nhiều API cùng AS/JWKS** | Signature check ở mọi API đều PASS | Mỗi RS có expected audience riêng |
| **API Gateway** | Gateway validate token một lần rồi forward mọi upstream | Propagate verified context đúng scope; downstream enforce own audience/policy |
| **Microservice gọi chéo** | Service A forward token user tới B mà token chỉ dành A | Token exchange hoặc AT dành B |
| **Multi-tenant SaaS** | Cache metadata/key theo hostname, không theo issuer/tenant | Partition trust config, issuer, aud và tenant |
| **OIDC app** | ID token được nhầm thành API token vì cùng JWT format | Token-type separation và OIDC vs OAuth audience |
| **Mobile/SPA nhiều resource** | Một token bị giữ global và dùng cho mọi API | Lưu/định tuyến token theo RS/resource |
| **Legacy introspection** | RS chỉ đọc `active:true`, bỏ `aud` | RS-specific AS contract, enforce audience |
| **JWT library permissive** | Token decoder chỉ kiểm tra signature/exp | Custom audience validator và tests âm tính |
| **Access token có multi-audience** | Một token có quyền ở nhiều RS, làm tăng blast radius | Chỉ multi-aud khi intentional và scope/policy rõ |
| **Token exchange/OBO thiếu ràng buộc** | Internal service tự chấp nhận token source | Đổi sang target audience được AS cấp |
| **Proxies/reverse proxy** | RS dùng request Host header để suy audience | Dùng expected audience từ trusted config |

**Đừng tính audience bằng cách tin `Host`, `X-Forwarded-Host` hoặc query parameter của request**. Attacker có thể kiểm soát các header này nếu trust proxy cấu hình sai. Expected audience phải đến từ **registration/trusted deployment configuration**.

## 9. Audience phải được kiểm tra tại đúng Resource Server

Resource Server là **bên nhận dự kiến** của OAuth access token. Dù token được ký bằng key của đúng AS, RS phải xác minh:

1. **Token được chấp nhận bởi profile hiện hành**: JWT access token, opaque token introspection hoặc sender-constrained profile.
2. **Nguồn xác thực**: issuer/AS tin cậy; chữ ký/algorithm/JWKS hoặc authenticated introspection.
3. **Audience**: có đúng RS identifier trong `aud` hay được bảo đảm tương đương qua AS–RS contract.
4. **Hạn và thời gian**: `exp`/`nbf`, `iat`, clock policy và trạng thái revoke nếu áp dụng.
5. **Scope/permission**: quyền cần cho HTTP method/resource action.
6. **Sender proof**: DPoP/mTLS nếu token có ràng buộc khóa/cert.
7. **Authorization nghiệp vụ**: subject/client/tenant/object ownership và quy tắc cấp quyền.

Một JWT access token profile theo RFC 9068 có các claim `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti` cùng các điều kiện profile khác. Đối với Resource Server, **`aud` không phải gợi ý UI**; nó là ràng buộc chống token substitution.

### Nếu token có `aud` vắng mặt?

Với **JWT access token theo RFC 9068**, coi là sai profile và **từ chối**. Với opaque token, introspection metadata có thể tùy chọn và AS có thể có chính sách RS-specific, nhưng RS phải có **hợp đồng tin cậy rõ** (xem phần introspection). **Không tự mặc định token không có audience dùng được cho mọi service.**

## 10. Đừng nhầm dấu hiệu hợp lệ với quyền truy cập

Một request mang token `T` có thể có:

~~~text
Signature valid?                YES
Issuer trusted?                 YES
Token not expired?              YES
Client allowed to obtain token? YES
Subject recognized?             YES
Audience matches this RS?       NO
-------------------------------------
Authorization decision:         REJECT
~~~

Ngay cả nếu audience khớp:

~~~text
Audience matches?               YES
Scope includes orders:read?     YES
Order 123 belongs to subject?   NO
-------------------------------------
Authorization decision:         REJECT
~~~

**Audience check là cần, không đủ.** Tương tự, role, scope và owner check **không thể bù** cho audience sai. Các kiểm soát này phòng vệ theo lớp, không phải điều kiện “OR”.

### Mã HTTP trả cho client

- **Access token sai audience, sai issuer, sai token purpose, hết hạn hoặc signature sai:** thường là **401 Unauthorized**, challenge `Bearer error="invalid_token"` theo RFC 6750 khi dùng Bearer.
- **Token đúng audience và còn hiệu lực nhưng thiếu scope:** thường là **403 Forbidden**, có thể `insufficient_scope`.
- **Token đúng scope nhưng không được đọc object cụ thể:** **403** hoặc **404** theo chính sách tránh lộ sự tồn tại object.
- **AS introspection bị timeout/không thể xác thực RS:** không có verdict đáng tin; fail closed và có thể trả **503** phù hợp, không tự coi token active.

**Không phản hồi token nguyên vẹn hay detailed claims nhạy cảm** trong thông báo lỗi chỉ để giải thích audience mismatch.

## 11. Multi-audience token: được phép nhưng phải có chủ đích

RFC 7519 cho phép `aud` là mảng:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": [
    "https://orders-api.example.test",
    "https://reports-api.example.test"
  ],
  "scope": "orders:read reports:read",
  "exp": 1800003600
}
~~~

Cả Orders và Reports **có thể** coi audience của mình nằm trong mảng, **nếu AS thực sự cấp token có phạm vi đó và các RS được thiết kế cho một token đa tài nguyên**. Tuy nhiên:

- Token bị lộ có **blast radius lớn hơn** vì có thể dùng ở nhiều RS.
- `scope` và claim permission phải có ý nghĩa thống nhất hoặc được phân vùng theo resource; scope names trùng có thể gây hiểu nhầm.
- Logs/cache và token binding phải duy trì context RS, không gộp policy của hai API thành một.
- Một RS thấy audience match vẫn không được **bỏ qua** các checks khác.
- Không cho client tùy ý thêm mọi audience vào một token bằng request mà AS không kiểm soát.
- Nếu các RS có mức tin cậy hoặc độ nhạy dữ liệu khác nhau, **ưu tiên access token theo từng RS**.

**Không nên quy định “mọi token nhiều audience đều phải reject” theo mặc định toàn cầu**, vì JWT/OAuth có thể hợp lệ với multi-audience. Nhưng hệ thống cụ thể **có thể** cấm bằng policy nếu không cần và không muốn tăng rủi ro.

## 12. AS phải cấp token hướng tới đúng resource

Nhiều lỗ hổng “audience confusion” bắt nguồn **từ khâu cấp token**:

- AS cấp mọi access token với `aud=all-services` quá rộng.
- Client xin audience theo input không giới hạn, AS không kiểm tra quyền của client đối với resource.
- AS đưa `client_id` của app vào `aud` của access token cho API, khiến RS không có định danh riêng.
- AS phát cùng một token cho mọi microservice dù chỉ một service được user đồng ý dùng.
- Scope không gắn với resource và được diễn giải khác nhau ở các RS.

### `resource` parameter theo RFC 8707

**OAuth 2.0 Resource Indicators (RFC 8707)** cho phép client chỉ ra resource mục tiêu, ví dụ:

~~~http
GET /authorize?response_type=code&client_id=orders-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=openid%20orders%3Aread&state=<STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256&resource=https%3A%2F%2Forders-api.example.test HTTP/1.1
Host: auth.example.test
~~~

AS phải **kiểm tra client registration, resource được phép, consent, scope và policy** trước khi phát token. Khi token được cấp, `aud` có thể được định nghĩa từ resource indicator hoặc mapping của AS; **không giả định token `aud` luôn byte-for-byte bằng tham số `resource`** nếu provider có hợp đồng ánh xạ riêng.

Ví dụ token response giả sau Authorization Code + PKCE:

~~~json
{
  "access_token": "<AT_FOR_ORDERS_API>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

Client muốn gọi Billing API nên xin **token mới dành Billing**, hoặc dùng cơ chế **token exchange** đã được AS hỗ trợ, thay vì gửi `AT_FOR_ORDERS_API` sang Billing.

**`resource` là yêu cầu, không phải “vé” do client tự ghi audience.** AS kiểm soát kết quả cấp và RS kiểm tra audience thực tế của token nhận được.

## 13. Token exchange/OBO: truyền danh tính qua service mà không lẫn audience

Một flow phổ biến:

~~~text
Browser/App -> Gateway -> Orders API -> Shipping API
                         (user muốn xem tình trạng giao)
~~~

Nếu client có `AT_ORDERS` với `aud=orders-api`, Orders API **không nên tự động forward token đó** tới Shipping API. Shipping API là một Resource Server khác, có expected audience `shipping-api`.

### Giải pháp đúng

- Orders API gọi AS để **token exchange** theo RFC 8693 hoặc cơ chế delegated/on-behalf-of của provider đã đăng ký.
- AS kiểm tra subject token, client/service, quyền delegation, requested audience/resource, scope và policy.
- AS phát `AT_SHIPPING` giới hạn audience `shipping-api` và scope đủ nhỏ, có thể kèm actor/delegation context theo profile.
- Shipping API kiểm tra **token `AT_SHIPPING`**, không tin việc Orders API nói “đã kiểm tra ở đầu chuỗi”.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant O as Orders API
    participant AS as Authorization Server
    participant S as Shipping API

    C->>O: GET /orders/123/shipping + AT_ORDERS (aud=orders)
    O->>O: Verify issuer, aud=orders, scope, order ACL
    O->>AS: Token exchange: subject_token=AT_ORDERS, audience=shipping
    AS->>AS: Verify delegation + allowed resource/scope/client
    AS-->>O: AT_SHIPPING (aud=shipping, scope=shipping:read)
    O->>S: GET /shipments/... + AT_SHIPPING
    S->>S: Verify issuer, aud=shipping, scope/tenant
    S-->>O: Shipping data
    O-->>C: Authorized aggregated response
~~~

**Token Exchange RFC 8693 không có nghĩa AS bắt buộc cấp mọi audience được request.** Mọi yêu cầu exchange phải chịu **client authentication, grant/consent và authorization policy**. Không được dùng exchange như cách sửa lỗi sai audience bằng một service token toàn quyền.

### Phân biệt `actor` và `subject`

Trong delegated tokens, `sub` có thể đại diện user, còn `act` (*actor*) mô tả service đang hành động theo profile. **`act` không thay `aud`**: Shipping API vẫn phải là đối tượng nhận token, và phải kiểm tra quyền theo actor/subject/tenant phù hợp.

## 14. API Gateway kiểm tra token không miễn downstream kiểm tra audience

Các hệ thống thường có gateway đứng trước nhiều API. Hai mô hình cần phân biệt:

| Kiến trúc | Ai xác minh token? | Audience nên được ràng buộc thế nào? |
|---|---|---|
| **Gateway pass-through token** | Gateway có thể kiểm tra, backend RS vẫn thấy AT | Backend validate `aud`/scope cho resource mình, hoặc contract rõ |
| **Gateway terminate auth + trusted identity headers** | Gateway verify token, backend chỉ nhận context đã được gateway ký/xác thực qua kênh tin cậy | Gateway phải route đúng audience theo backend, backend giới hạn nguồn header và authorization |
| **Gateway token exchange** | Gateway đổi AT sang internal token riêng cho downstream | Internal token audience chỉ đúng downstream, binding ngắn hạn |
| **Service mesh identity** | mTLS giữa services xác thực workload | Không tự chứng minh end-user access token đúng audience |

Một lỗi đáng chú ý:

~~~text
Gateway checks:
    signature OK
    iss OK
    exp OK

Gateway routes:
    /api/billing/* -> Billing
    /api/orders/*  -> Orders

Gateway FORGETS:
    Match token audience to target route/resource

Result:
    token with aud=billing may pass gateway to Orders.
~~~

**Không lấy path do client gửi rồi tạo expected audience tùy tiện mà không dựa trên mapping đáng tin.** Gateway cần bảng ánh xạ routes → resource audience có thể kiểm toán.

Nếu downstream nhận identity qua headers như `X-User-Id`/`X-Scope`, gateway phải **xóa headers do client tự gửi**, sau đó đưa claims đã xác minh qua kênh **mTLS/authenticated internal hop**; backend phải từ chối đường truy cập bypass gateway. Đây là **một trust model khác** so với việc backend trực tiếp verify JWT, và phải được thiết kế rõ ràng.

## 15. Opaque token và introspection: `active:true` chưa thay audience

Opaque access token không cho RS tự đọc các claims. Theo **RFC 7662**, RS hỏi AS qua introspection endpoint bằng POST có xác thực:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <RESOURCE_SERVER_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

Response active có thể như sau:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "client_id": "orders-web",
  "exp": 1800003600
}
~~~

RS phải tiếp tục đối chiếu audience và scope theo **contract**; `active:true` chưa đủ.

### Trường hợp response thiếu `aud`

RFC 7662 chỉ bắt buộc trường `active`; `aud` là **metadata tùy chọn**. Nếu không có `aud` nhưng AS có **RS-specific introspection** (chỉ trả `active:true` khi token đúng resource đang gọi), RS có thể dựa vào **hợp đồng AS–RS xác thực được**. Nếu không có binding tương đương rõ ràng, **fail closed**.

Một số AS trả `active:false` với token đang active nhưng **RS hỏi không được phép xem token của resource khác**. Vì vậy, `active:false` không có nghĩa token bị revoke toàn cục.

### Token type hint không phải audience

`token_type_hint=access_token` chỉ là **gợi ý tìm token**. Nó **không chứng minh** credential là access token dành cho API đang hỏi. RS/AS cần enforce token-purpose binding và không chấp nhận refresh token/ID token làm API bearer token.

## 16. JWT access token: quy trình kiểm tra theo RFC 9068

Với JWT access token (RFC 9068), các bước nên được áp dụng theo **profile và registration thực tế**:

| Bước | Kiểm tra | Sai thì làm gì? |
|---|---|---|
| 1 | Request có token qua transport đúng (Bearer hoặc PoP profile) | Từ chối |
| 2 | JWT structure và JOSE `typ` là access-token profile được phép | Từ chối token type khác |
| 3 | `alg` trong allowlist và key type phù hợp | Từ chối downgrade/`none` |
| 4 | Chữ ký JWS hợp lệ bằng public key của issuer tin cậy | Từ chối |
| 5 | `iss` khớp chính xác AS đã cấu hình | Từ chối wrong issuer |
| 6 | `aud` chứa đúng **configured audience của THIS RS** | Từ chối wrong audience |
| 7 | `exp`, `iat`, `nbf` hợp lệ theo policy | Từ chối hết hạn/chưa có hiệu lực |
| 8 | `client_id`/`sub` và claims đúng profile/grant context | Từ chối sai purpose/client nếu policy |
| 9 | `scope`/authorization details đúng action | 403 khi chỉ thiếu scope |
| 10 | `cnf` và proof DPoP/mTLS đúng nếu sender-constrained | Từ chối proof sai |
| 11 | Tenant/object policy và revocation state nếu hệ thống yêu cầu | Từ chối quyền không đủ |

**Thứ tự “type/header rồi signature” không có nghĩa được tin nội dung header trước chữ ký.** Header là dữ liệu chưa được tin cho đến khi cryptographic verification thành công; có thể dùng nó để **chọn ứng viên thuật toán/khóa trong allowlist**, không dùng `jku` do token cung cấp để fetch khóa lạ.

### Không tự viết parser từ Base64url

~~~text
jwt.split(".")[1]
BASE64URL-DECODE(payload)
JSON.parse(payload)
if claims.aud == orders:
    allow
~~~

Cách này **không xác minh chữ ký, alg, issuer và purpose**. Nó là ví dụ chống chỉ định. Dùng thư viện JOSE/JWT được bảo trì để xác minh, rồi mới áp dụng audience/authorization policy.

## 17. Đừng nhầm `typ`, `token_type` và token purpose

Những giá trị dễ bị nhầm:

| Giá trị | Xuất hiện ở đâu? | Nó nói gì? |
|---|---|---|
| JOSE header **`typ=at+jwt`** | JWT access token RFC 9068 | Token là JWT access-token profile, cần verify cùng chữ ký/claims |
| Token response **`token_type=Bearer`** | OAuth token response | Cách client trình token, **không nói token là JWT hay đúng RS** |
| Introspection **`token_type=Bearer`** | Response metadata khi AS cung cấp | Presentation style, không tự phân biệt refresh vs access usage |
| ID token `aud=client_id` | Payload ID token OIDC | RP/client được dự kiến xác minh authentication |
| Access token `aud=resource` | Payload AT hoặc RS-specific contract | Resource Server nhận token |
| Token exchange `requested_token_type` | Request token exchange | Loại token client muốn nhận, AS vẫn quyết định và ràng buộc purpose |

**“Bearer” không có nghĩa “mọi API chấp nhận được”.** Token bearer vẫn có issuer, audience, scope và expiry; nếu bị đánh cắp, người có token có thể thử replay **tại đúng RS**. Kiểm tra audience giới hạn vùng dùng nhưng không thay được chống đánh cắp/replay.

## 18. Java 17: policy audience trên token đã verify mật mã

Ví dụ Java 17 sau minh họa **phần authorization policy của Orders API**. Đầu vào là `VerifiedAccessToken` do **thư viện JWT/JWS validator đã xác minh chữ ký/issuer/algorithm và token profile** hoặc adapter introspection tin cậy tạo ra. Không được tạo object này từ JSON payload chưa verify.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Set;

public final class AudienceGuard {
    private static final String EXPECTED_ISSUER =
            "https://auth.example.test";
    private static final String EXPECTED_AUDIENCE =
            "https://orders-api.example.test";
    private static final String REQUIRED_SCOPE =
            "orders:read";

    public record VerifiedAccessToken(
            String issuer,
            Set<String> audiences,
            Set<String> scopes,
            Instant expiresAt,
            Instant notBefore,
            String purpose
    ) {
        // Only trusted cryptographic/introspection adapter
        // may construct records passed to authorize().
    }

    public enum Decision {
        ALLOW_TOKEN_POLICY,
        REJECT_INVALID_TOKEN,
        REJECT_INSUFFICIENT_SCOPE
    }

    public static Decision authorize(
            VerifiedAccessToken token,
            Clock clock
    ) {
        if (token == null
                || token.issuer() == null
                || !EXPECTED_ISSUER.equals(token.issuer())
                || token.audiences() == null
                || !token.audiences().contains(EXPECTED_AUDIENCE)
                || !"access_token".equals(token.purpose())
                || token.expiresAt() == null) {
            return Decision.REJECT_INVALID_TOKEN;
        }

        Instant now = clock.instant();
        if (!now.isBefore(token.expiresAt())
                || (token.notBefore() != null
                    && now.isBefore(token.notBefore()))) {
            return Decision.REJECT_INVALID_TOKEN;
        }

        if (token.scopes() == null
                || !token.scopes().contains(REQUIRED_SCOPE)) {
            return Decision.REJECT_INSUFFICIENT_SCOPE;
        }

        return Decision.ALLOW_TOKEN_POLICY;
        // Caller MUST still check tenant/object-level ACL
        // and sender proof when token is sender-constrained.
    }

    public static void main(String[] args) {
        Clock demoClock = Clock.fixed(
                Instant.parse("2026-11-23T10:00:00Z"),
                java.time.ZoneOffset.UTC
        );
        Instant expiry = Instant.parse("2026-11-23T10:15:00Z");

        VerifiedAccessToken billing = new VerifiedAccessToken(
                EXPECTED_ISSUER,
                Set.of("https://billing-api.example.test"),
                Set.of("orders:read"),
                expiry, null, "access_token"
        );

        VerifiedAccessToken orders = new VerifiedAccessToken(
                EXPECTED_ISSUER,
                Set.of(EXPECTED_AUDIENCE),
                Set.of("orders:read"),
                expiry, null, "access_token"
        );

        System.out.println(authorize(billing, demoClock));
        System.out.println(authorize(orders, demoClock));
        // REJECT_INVALID_TOKEN
        // ALLOW_TOKEN_POLICY
    }

    private AudienceGuard() {}
}
~~~

### Những giả định bắt buộc khi đưa vào production

1. `VerifiedAccessToken` là **kiểu dữ liệu sau khi đã verify**, không phải record có thể tự dựng từ untrusted payload. Java record constructor mặc định public trong ví dụ để minh họa; production nên đóng gói constructor/trusted adapter để bảo vệ provenance.
2. `purpose="access_token"` là **kết quả phân loại tin cậy** từ `typ` RFC 9068 hoặc introspection contract, không phải claim tự đặt của client.
3. `audiences` được parse từ `aud` dạng chuỗi **hoặc** mảng chuỗi bằng thư viện có schema validation, không convert `null`/number/object thành chuỗi.
4. `scopes` được tách theo token scope contract, không dùng substring.
5. Code chưa tự verify `iat`, token signature/algorithm, token revocation state, DPoP/mTLS proof, hoặc **tenant/object ACL**. Những lớp này vẫn bắt buộc theo môi trường.
6. Expected audience lấy từ **trusted config** cố định của Orders API, không từ `Host` hay request body.
7. `ALLOW_TOKEN_POLICY` chưa cho phép đọc order; ứng dụng phải kiểm tra resource authorization ở service layer.

## 19. Java/Jackson: chuyển `aud` dạng string hoặc array sau khi verify

Nhiều thư viện JWT đã trả audience dưới dạng danh sách. Nếu adapter làm việc với JSON của **verified JWT payload** hoặc authenticated introspection response, cần parse rõ cả hai dạng chuẩn.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashSet;
import java.util.Set;

public final class AudienceClaimParser {
    public static Set<String> readVerifiedAudience(JsonNode claims) {
        JsonNode aud = claims.path("aud");
        if (aud.isTextual() && !aud.asText().isBlank()) {
            return Set.of(aud.asText());
        }

        if (aud.isArray() && !aud.isEmpty()) {
            Set<String> audiences = new LinkedHashSet<>();
            for (JsonNode item : aud) {
                if (!item.isTextual() || item.asText().isBlank()) {
                    throw new SecurityException("Invalid aud array");
                }
                audiences.add(item.asText());
            }
            return Set.copyOf(audiences);
        }

        throw new SecurityException("Missing or invalid aud");
    }

    private AudienceClaimParser() {}
}
~~~

**Lưu ý quan trọng:** hàm này **không xác minh JWT chữ ký**. Chỉ gọi khi `claims` đến từ thư viện **đã verify signature, issuer và token type**, hoặc từ introspection endpoint đã xác thực theo RS contract.

Không:

~~~java
// SAI: ép "aud" thành một chuỗi tùy ý rồi dùng contains.
String audText = claims.get("aud").toString();
boolean permitted = audText.contains("orders-api");
~~~

Với `["billing-api", "orders-api"]`, một policy có thể cho phép Orders nếu multi-audience được AS chấp thuận, nhưng backend vẫn phải kiểm tra tất cả policy constraints khác. Với `["orders-api", 123]`, adapter phải reject vì `aud` malformed, không tự convert `123` sang chuỗi.

## 20. Spring Security 6: thêm Audience Validator cho JWT Resource Server

Một ứng dụng Spring Security có thể dùng decoder JWT theo issuer tin cậy, nhưng **cần đảm bảo audience validator được cấu hình** đúng resource. Ví dụ dưới đây minh họa với Spring Security 6.x API (phụ thuộc version/dependency thực tế):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public class OrdersJwtValidationConfig {
    private static final String ISSUER =
            "https://auth.example.test";
    private static final String AUDIENCE =
            "https://orders-api.example.test";

    @Bean
    JwtDecoder ordersJwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Invalid token audience",
                            null
                    )
            );
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator
        ));
        return decoder;
    }
}
~~~

**Không coi ví dụ này là toàn bộ cấu hình bảo mật.**

- Tùy Spring Security version, default decoder/type handling có thể khác; cần **thử token ID token, sai `typ`, sai `alg`, multi-issuer** và **chỉ chấp nhận đúng JWT access token profile** đã đăng ký. Nếu AS dùng RFC 9068, kiểm tra `typ=at+jwt` (hoặc form chuẩn) và tập alg theo policy.
- `withIssuerLocation` thực hiện discovery/metadata theo hỗ trợ của thư viện; **issuer cấu hình phải đáng tin**, không lấy trực tiếp từ request.
- Custom validator phải được **gộp** với kiểm tra issuer/time/signature mặc định chứ không được thay thế chúng bằng mỗi audience check.
- `hasAuthority("SCOPE_orders:read")` nếu dùng còn phải áp dụng ở route/method, kết hợp object-level authorization.
- Nếu ứng dụng có **nhiều issuer**, cần trusted issuer resolver/mapping và key/audience policy **theo từng issuer/tenant**, không chấp nhận issuer tùy ý.
- Khi dùng **opaque token** thay JWT, nên kiểm tra `active`/audience theo introspection contract, không áp mã decoder JWT cho opaque token.

### Vì sao default JWT validation có thể chưa đủ?

Một số cấu hình framework sẽ validate signature/issuer/expiry nhưng **không tự biết audience nghiệp vụ** của ứng dụng nếu không được khai báo. Kỹ sư cần xác minh **thực tế** token từ Billing API bị Orders API từ chối, không chỉ thấy API trả 200 với token của Orders rồi coi đã đủ kiểm thử.

## 21. Sender-constrained tokens cũng cần audience

**DPoP** (RFC 9449) và **mTLS-bound access tokens** (RFC 8705) giới hạn khả năng attacker **sao chép token rồi sử dụng từ một sender khác**. Nhưng chúng **không thay thế ràng buộc tài nguyên nhận**.

~~~text
Access token:
    aud = billing-api
    cnf = thumbprint of client's key

Request to Orders API:
    token + valid DPoP proof for Orders endpoint

Wrong audience => REJECT.
Proof đúng không biến token Billing thành token Orders.
~~~

RS phải kiểm tra:

- Đúng **issuer, token purpose và audience**.
- DPoP proof đúng `htm`/`htu`, `iat`, `jti`, `ath` và `cnf.jkt` theo profile, chống replay proof.
- Hoặc mTLS certificate binding phù hợp `cnf.x5t#S256`.
- Đúng scope/object/tenant policy.

Sender constraint ngăn kiểu **token replay do copy token một mình**, trong khi audience ngăn **token substitution giữa RS**. Hai bảo vệ giải quyết **hai trục khác nhau** và có thể cùng cần thiết.

## 22. JWT được mã hóa JWE có loại bỏ audience confusion không?

Không. **JWE** bảo vệ tính bí mật nội dung token với người không có khóa giải mã; nó **không tự quyết định token dành cho API nào** sau khi giải mã.

Ví dụ token JWE được mã hóa cho service chung, chứa một JWT access token:

~~~text
outer JWE: decrypt using configured recipient key
inner JWS: verify signature from trusted AS
payload aud: https://billing-api.example.test

Orders API:
    decrypt succeeded
    signature succeeded
    aud does not match Orders
    => REJECT
~~~

Tương tự, **TLS/HTTPS** chỉ bảo vệ token khi truyền; **chữ ký JWS** chỉ chứng minh nguồn và tính toàn vẹn; **JWE** giúp giữ bí mật. Tất cả vẫn cần **audience/purpose/authorization validation**.

Một lỗi thiết kế nguy hiểm là: “Chỉ Orders API có private key JWE nên token chắc chắn dành Orders.” Nếu cùng khóa được chia sẻ cho nhiều RS hoặc phát sinh việc mã hóa token sai đích, kết luận đó không bền vững. `aud` vẫn phải được ràng buộc theo token profile.

## 23. Case study: Orders, Billing và API Gateway trong SaaS nhiều tenant

Hệ thống giả định:

- Issuer: `https://auth.example.test/realms/retail`.
- Client: `retail-dashboard`.
- Orders RS: `https://api.example.test/orders`.
- Billing RS: `https://api.example.test/billing`.
- Gateway: `https://api.example.test`.
- Tenant: `shop-42`.

**Audience là logical resource identifier đã đăng ký**, không phải tùy ý cắt `/orders/123` thành `/orders` bằng string manipulation. AS và gateway/RS phải thống nhất mapping.

### Cấu hình đúng theo resource

~~~json
{
  "trusted_issuer": "https://auth.example.test/realms/retail",
  "resource_audiences": {
    "orders": "https://api.example.test/orders",
    "billing": "https://api.example.test/billing"
  },
  "token_profile": "RFC9068",
  "allowed_access_token_algs": ["RS256"],
  "tenant_claim_required": true
}
~~~

JSON trên là **cấu hình ví dụ ứng dụng**, không phải metadata tiêu chuẩn AS và không chứa khóa bí mật.

### Đường lỗi

~~~text
10:00   retail-dashboard nhận AT_BILLING
        iss=https://auth.example.test/realms/retail
        aud=https://api.example.test/billing
        scope=billing:read
        tenant=shop-42

10:01   Client/attacker gửi GET /orders/123 kèm AT_BILLING
10:01   Gateway chỉ verify signature + iss + exp
10:01   Gateway forward tới Orders service
10:01   Orders service tin gateway và bỏ check aud
10:01   Nếu object ACL/scope quá rộng, dữ liệu order có thể lộ
~~~

### Đường sửa

1. Gateway map `/orders/*` vào **Orders expected audience**, không tự suy từ Host header.
2. Gateway **reject token audience Billing** ngay tại edge.
3. Orders service validate lại token/identity contract đã được xác thực hoặc chỉ nhận internal token aud=Orders.
4. Orders service kiểm tra scope `orders:read` và tenant/order authorization.
5. Khi Retail dashboard cần Billing, client xin access token audience Billing riêng.
6. Token cache ở client dùng key theo **issuer + account + resource + scope/client policy**, không có một biến `globalAccessToken` cho mọi API.
7. Negative tests có Billing token hợp lệ nhưng Orders phải trả **401 invalid_token**.

### Khi share cùng hostname?

`https://api.example.test/orders` và `https://api.example.test/billing` có thể cùng hostname nhưng là **hai audience logic khác**. Nếu gateway muốn một audience chung cho tất cả API, phải **chủ đích** coi gateway là RS/security boundary và thiết kế authorization cho từng route/backend; không tự bỏ qua boundary giữa các domain nghiệp vụ.

## 24. Phát hiện và ứng phó audience confusion trong vận hành

Triệu chứng thực tế có thể là **một access token hợp lệ của API A được chấp nhận ở API B**, hoặc hệ thống liên tục báo `invalid_token` sai audience sau thay đổi AS/client registration.

### Nếu phát hiện API chấp nhận wrong audience

1. **Chặn tạm các requests sai audience** tại gateway/RS bằng policy, không chờ sự cố lặp lại.
2. Xác định **RS, issuer, audience, client, tenant và phiên bản cấu hình** bị ảnh hưởng; không lưu raw token.
3. Rà lại **authorization checks ở service layer**: có lộ object nào do scope/ACL cũng sai không?
4. Bổ sung **RS-specific audience validation** và test negative cross-resource.
5. Kiểm tra **AS token issuance**: có phát multi-audience quá rộng hoặc sai mapping `resource` không?
6. Nếu token đã bị khai thác, cân nhắc **revoke access/refresh token/grant** theo risk; đánh giá latency JWT offline/RS caches.
7. Kiểm tra gateway, service mesh, BFF, token exchange, issuer/JWKS cache và các client bị ảnh hưởng.
8. Áp dụng rollout, logging, monitoring và regression tests để không làm gián đoạn resource legitimately multi-audience.

**Không dùng log nguyên Bearer token để điều tra.** Dùng `jti`/issuer/client/resource/correlation ID được bảo vệ, hoặc HMAC fingerprint nội bộ của token khi thực sự cần, với TTL/retention và quyền truy cập chặt.

### Event audit an toàn

~~~json
{
  "event_type": "security.access_token.rejected",
  "occurred_at": "2026-11-23T10:10:00Z",
  "resource_server": "orders-api",
  "trusted_issuer": "https://auth.example.test/realms/retail",
  "expected_audience": "https://api.example.test/orders",
  "reason": "AUDIENCE_MISMATCH",
  "token_ref": "hmac-token-pseudonym",
  "client_id": "retail-dashboard",
  "raw_token_logged": false
}
~~~

`raw_token_logged=false` chỉ mô tả mong muốn telemetry, không tự bảo đảm reverse proxy, APM hay crash reporter thật sự đã redaction. Test bằng **canary fake token** trong staging; tránh dùng production bearer token trong HAR, CI và screenshot.

### Metric nên theo dõi

- Số lượng `AUDIENCE_MISMATCH` theo RS/issuer/client và version release.
- Tỷ lệ wrong `typ`/ID-as-access token/refresh token substitution.
- AS phát token multi-audience và token exchange requests bất thường.
- Gateway/backend disagreement về token validity.
- Wrong issuer, invalid signature, expiry, scope denies và object ACL denies.
- Suspicious replay từ token reference bị gửi nhiều RS không liên quan.

## 25. Ma trận kiểm thử Audience confusion

| Test | Đầu vào/thao tác | Kết quả mong đợi |
|---|---|---|
| **T1 — Correct audience string** | JWT AT `aud=orders-api` | Qua audience check; vẫn cần scope/object checks |
| **T2 — Billing audience** | Orders RS nhận AT `aud=billing-api` | **401 invalid_token** |
| **T3 — ID token substitution** | RP ID token `aud=orders-web` gửi Orders API | **Từ chối** |
| **T4 — Refresh token substitution** | RT được gửi như Bearer tới RS | **Từ chối purpose** |
| **T5 — Auth code/device code** | Mã authorization/device được gửi API | **Từ chối** |
| **T6 — Missing aud** | JWT RFC9068 không có `aud` | Từ chối |
| **T7 — Aud null/object** | `aud=null` hoặc `aud={}` | Từ chối |
| **T8 — Aud number** | `aud=123` | Từ chối |
| **T9 — Aud array valid** | `aud=[billing,orders]` khi policy cho multi-aud | Orders chỉ pass audience rồi còn các checks |
| **T10 — Aud array no match** | `aud=[billing,shipping]` | Từ chối |
| **T11 — Aud mixed types** | `aud=[orders,123]` | Từ chối malformed |
| **T12 — Empty audience** | `aud=""` hoặc `aud=[]` | Từ chối |
| **T13 — Substring bypass** | `aud=orders-api.attacker.test` | Không khớp bằng contains/prefix |
| **T14 — Trailing slash** | Expected `https://api/orders`, token `https://api/orders/` | Từ chối theo exact identifier |
| **T15 — Uppercase drift** | `ORDERS` thay `orders` | Từ chối nếu chuỗi khác |
| **T16 — Wrong issuer** | `aud` đúng, `iss` tenant khác | Từ chối |
| **T17 — JWKS kid collision** | Hai issuer có cùng `kid` | Không dùng key cache chéo |
| **T18 — JWT jku injection** | Header `jku` trỏ attacker | Không fetch, từ chối nếu không verify trusted key |
| **T19 — Invalid signature** | Claims có aud đúng nhưng ký giả | Từ chối |
| **T20 — alg none** | JWT unsigned/`alg=none` khi policy yêu cầu JWS | Từ chối |
| **T21 — Wrong typ** | JWT ID token `typ=JWT` vào RS RFC9068 | Từ chối |
| **T22 — Expired token** | `now >= exp` | Từ chối |
| **T23 — Future nbf** | `nbf > now` | Từ chối |
| **T24 — Client id confusion** | `client_id=orders-web`, `aud=billing` | Từ chối |
| **T25 — azp confusion** | ID token `azp=orders-web`, `aud=orders-web` | Không dùng như Orders AT |
| **T26 — Scope confusion** | `aud=orders` nhưng không `orders:read` | 403 insufficient_scope |
| **T27 — Scope substring** | `orders:read:any` không có `orders:read` | Không coi là quyền tương đương |
| **T28 — Object ACL** | Audience/scope đúng, order khác tenant | Từ chối |
| **T29 — AS resource indicator** | Xin `resource=orders` được phép | AS phát audience đúng theo contract |
| **T30 — Forbidden resource** | Client xin `resource=admin-api` không được phép | AS từ chối/thu hẹp theo policy |
| **T31 — Token exchange** | Orders đổi token sang Shipping | Shipping nhận token audience Shipping, không token Orders cũ |
| **T32 — OBO token actor** | Actor hợp lệ nhưng aud sai | RS từ chối |
| **T33 — Gateway cross-route** | Billing token qua path `/orders/*` | Gateway/RS từ chối |
| **T34 — Forwarded header attack** | Attacker tự đặt `X-Forwarded-Host` | Không thay expected audience |
| **T35 — Gateway bypass** | Gọi backend trực tiếp với forged `X-User` | Bị từ chối ngoài trust boundary |
| **T36 — Opaque introspection** | `active:true` nhưng `aud=billing` | Orders từ chối |
| **T37 — Opaque no aud** | `active:true`, không có aud và không có AS–RS contract | Fail closed |
| **T38 — RS-specific introspection** | Token chỉ dành Billing, Orders introspect | AS có thể trả `active:false` theo policy |
| **T39 — Introspection outage** | AS timeout/401 credential RS | Không tự cho phép vì cache/active không đáng tin |
| **T40 — Sender-bound** | DPoP proof đúng nhưng aud sai | Từ chối |
| **T41 — Missing proof** | Aud đúng nhưng DPoP/mTLS proof sai | Từ chối |
| **T42 — JWE** | Giải mã đúng nhưng payload aud sai | Từ chối |
| **T43 — Multi-tenant** | Token Retail được gửi Admin API | Từ chối issuer/tenant/audience |
| **T44 — Token cache by resource** | Client có AT Orders và Billing | Gọi đúng token cho đúng API |
| **T45 — Negative regression** | Tập token mỗi service được kiểm thử ở mọi RS khác | Mọi cross-resource mismatch đều bị từ chối |
| **T46 — Audit privacy** | Canary token qua gateway/RS/APM staging | Không log raw token |
| **T47 — Revocation** | Token bị revoke sau sự cố audience bypass | RS thấy revoke theo policy/SLA hoặc chờ exp có công bố |
| **T48 — Legacy services** | Microservice cũ chỉ verify signature/exp | Test phát hiện thiếu audience validator |
| **T49 — Unknown key** | Header có `kid` lạ liên tục | Không fetch URL attacker, JWKS refresh rate-limited |
| **T50 — Service identity** | `client_credentials` token aud=orders, `sub` là service | RS đánh giá service principal và quyền riêng, không coi sub=user |

**Kiểm thử có chủ đích:** phát một token thật về mặt mật mã cho **API B trên staging**, rồi gửi token đó tới **API A**. Một test chỉ dùng token chữ ký sai sẽ không phát hiện thiếu audience check, vì token đã bị reject từ bước signature.

## 26. Những hiểu nhầm cần loại bỏ

**“JWT ký đúng thì mọi API trong cùng hệ thống được nhận.”** Sai. Signature chỉ kiểm tra nguồn phát và tính toàn vẹn; audience chỉ định người nhận.

**“`aud` là URL của client/frontend.”** Không mặc định. Với ID token OIDC, `aud` thường là **client ID**; với access token, audience thường là **Resource Server**.

**“`client_id=orders-web` nghĩa token dùng được ở Orders API.”** Sai. Một OAuth client có thể có token dành cho Billing hoặc nhiều resource khác.

**“Scope đủ thì không cần aud.”** Sai. Scope nói quyền, aud nói người nhận; cả hai cần đúng.

**“Có `azp` thì thay được aud.”** Sai. `azp` là ngữ cảnh authorized party, không xác định RS của access token.

**“Mảng aud luôn nguy hiểm/luôn không hợp lệ.”** Sai. RFC cho phép nhiều audience. Nhưng AS và RS phải đồng ý policy; tránh phát đa resource quá rộng.

**“So sánh URL audience có thể tự đổi slash, chữ hoa và host thành chuẩn.”** Không nên. Identifiers phải so khớp theo **hợp đồng string exact** đã đăng ký; không tự hợp nhất các resources khác nhau.

**“Token đã được gateway verify nên backend khỏi quan tâm audience.”** Chỉ có thể đúng khi gateway là **trust boundary được thiết kế chặt**, kiểm tra audience theo từng route và downstream nhận context từ đường nội bộ đã xác thực. Không phải hệ quả tự nhiên của việc đặt gateway.

**“DPoP/mTLS proof đúng thì token sai audience cũng hợp lệ.”** Sai. Sender proof và audience bảo vệ hai chiều khác nhau.

**“JWE đã mã hóa thì API nào decrypt được cũng nhận.”** Sai. Decrypt không thay signature, issuer, audience, scope hay policy.

**“`active:true` từ introspection nghĩa API nên trả 200.”** Sai. RS vẫn kiểm tra token purpose, audience, scope và object ACL, hoặc dựa trên AS–RS contract tương đương đã được bảo đảm.

**“Bắt đầu bằng https là audience đúng.”** Sai. `https://orders-api.example.test.attacker.tld` vẫn là một audience khác và có thể thuộc attacker.

## 27. Checklist triển khai và tài liệu tham khảo

### Checklist cho Authorization Server

1. Phát access token **có audience/resource rõ** theo client registration, grant và consent/policy.
2. Dùng RFC 8707 `resource`/audience mapping khi hỗ trợ, không tin resource tùy ý từ client.
3. Hạn chế **multi-audience access token** theo use case và blast radius.
4. Phân biệt **ID token vs access token vs refresh token** theo profile và endpoint.
5. Nếu dùng RFC 9068, ký JWT AT với `typ` và các claims đúng profile, thuật toán an toàn.
6. Token exchange/delegation phải xác minh actor/client/subject/resource và scope phù hợp, không tự cấp mọi target audience.

### Checklist cho Resource Server / Gateway

7. Pin **trusted issuer, expected audience và algorithm/token-type policy** từ cấu hình.
8. Verify JWT signature bằng trusted JWKS theo issuer, hoặc authenticated opaque introspection.
9. Require **audience exact match**, chấp nhận string/array hợp lệ theo contract, không substring/prefix/host normalization.
10. Reject **ID token/refresh token/code** dùng làm API access token.
11. Verify `exp`/`nbf`/`iat`, `iss`, `scope`, `sub`/`client_id` theo profile.
12. Check sender proof cho DPoP/mTLS-bound tokens.
13. Authorize **object/tenant/role** sau khi token hợp lệ; audience không thay permission.
14. Với opaque token không có `aud`, yêu cầu **AS–RS binding contract**; không tự allow.
15. Gateway route → audience mapping phải do trusted config; downstream chỉ tin headers qua **authenticated internal channel**, không bypass.
16. Service-to-service phải dùng token dành target RS hoặc token exchange, không forward sai audience.
17. Cache keys/metadata/JWKS phải **partition theo issuer/tenant/resource**; chống unknown `kid` flood.
18. Dùng **401 invalid_token** cho token sai audience/type/issuer; **403 insufficient_scope** khi token hợp lệ nhưng không đủ scope.
19. Không log Bearer/ID/refresh tokens; audit bằng pseudonym/correlation reference được bảo vệ.
20. Chạy negative tests **token hợp lệ của API B ở API A** trong CI/staging trước và sau mọi thay đổi AS/gateway/library.
21. Rà lại token revocation propagation và key-rotation policy khi phát hiện substitution đã bị khai thác.

### Tài liệu chuẩn

- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): ý nghĩa và kiểu dữ liệu `aud`, `iss`, `sub`, `exp`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `typ=at+jwt`, expected audience, mandatory access-token claims và RS validation.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token security, audience restriction và chống misuse.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): request access token cho resource mục tiêu.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): audience/resource, actor/delegation và exchange.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): cross-JWT confusion, algorithm verification và token-type separation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): roles, client, RS, access/refresh token semantics.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer transport, invalid_token và insufficient_scope.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`/`aud` và bảo vệ introspection endpoint.
- [RFC 9449 — DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — mTLS-bound tokens](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained proof và token binding.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token audience/authorized party và phân biệt OIDC với OAuth API authorization.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, issuer/audience validators và authorization.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): token audience và những phòng vệ OAuth thực tế.

**Kết luận:** **Audience confusion** là ví dụ tiêu biểu của việc một credential **đúng về mật mã nhưng sai bối cảnh**. Resource Server không chỉ hỏi “AS có ký token này không?” mà phải hỏi **“AS có phát token này cho CHÍNH TÔI không, với đúng mục đích và quyền hay không?”**. Áp dụng **`aud` chính xác, token-type separation, issuer trust, scope/object authorization, sender proof khi cần và token exchange cho service-to-service** sẽ chặn phần lớn các đường token substitution giữa API/tenant/ứng dụng.
