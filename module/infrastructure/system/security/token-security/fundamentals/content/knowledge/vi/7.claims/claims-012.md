# Claim optional và claim bắt buộc

Giả sử Orders API nhận được hai access token. Token A có **iss**, **sub**, **aud**, **exp** và **scope**; token B cũng có chữ ký hợp lệ nhưng không chứa **scope**. Có phải token B luôn sai chuẩn? Câu trả lời phụ thuộc vào **loại token, profile được áp dụng và hợp đồng bảo mật của API**. Một claim có thể là *optional* trong chuẩn JWT nền tảng nhưng là *required* trong profile JWT access token hoặc trong chính sách của một Resource Server.

Bài học thuộc chương **Claims** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trong OAuth 2.0/OpenID Connect (OIDC), claims là thông tin về token, chủ thể, audience, quyền được cấp và thời gian hiệu lực. Hiểu đúng claim optional và claim bắt buộc giúp bạn phân biệt JWT, opaque token, access token, refresh token, kiểm tra chữ ký/claims, phân quyền theo scope và tránh chấp nhận một token thiếu điều kiện an toàn.

Sau bài này, bạn sẽ xác định được **bắt buộc theo chuẩn nào**, hiểu các claim bắt buộc có điều kiện, thiết kế hợp đồng claims cho API, xử lý claim thiếu hoặc sai kiểu và viết các trường hợp kiểm thử xác thực/phân quyền.

## 1. “Bắt buộc” luôn cần một ngữ cảnh

**Claim** là một cặp tên và giá trị biểu diễn một phát biểu về token hay chủ thể, ví dụ **iss** chỉ issuer, **aud** chỉ đối tượng nhận, **exp** chỉ thời hạn. Với JWT, claims thường nằm trong JSON payload; với opaque token dạng tham chiếu, Resource Server thường nhận metadata tương ứng thông qua introspection.

Để trả lời một claim có bắt buộc hay không, cần phân biệt bốn tầng:

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Định dạng JWT nền tảng** | RFC 7519 yêu cầu các registered claims nào luôn xuất hiện? | Các registered claims như **iss**, **sub**, **aud**, **exp** không mặc nhiên bắt buộc cho *mọi* JWT chỉ theo RFC 7519. |
| **Token profile/giao thức** | Loại token cụ thể phải có những claims nào? | OIDC ID token yêu cầu **iss**, **sub**, **aud**, **exp**, **iat**; JWT access token theo RFC 9068 có bộ yêu cầu riêng. |
| **Hợp đồng giữa issuer và Resource Server** | API này chỉ chấp nhận token có thuộc tính nào? | Orders API yêu cầu issuer tin cậy và audience **orders-api**; token phải thuộc loại access token. |
| **Chính sách phân quyền nghiệp vụ** | Hành động này đòi thông tin gì để cho phép truy cập? | Endpoint GET /orders cần quyền **orders:read** và người dùng có quyền với các đơn hàng được truy vấn. |

Vì vậy, không nên tạo một bộ **required claims** áp dụng đồng loạt cho mọi JWT và mọi flow. Việc xác thực đúng cần bắt đầu bằng **loại token nào được phép xuất hiện tại điểm nhận**, sau đó áp dụng bộ quy tắc của đúng profile và chính sách.

**Optional không có nghĩa có thể bỏ qua kiểm tra.** Nếu một claim optional **có xuất hiện**, verifier vẫn cần kiểm tra kiểu dữ liệu và ngữ nghĩa theo chuẩn/profile và hợp đồng hệ thống. Ví dụ **nbf** có thể không bắt buộc nhưng khi có mặt phải được kiểm tra để không chấp nhận token trước thời điểm được phép.

## 2. Registered claims trong JWT nền tảng (RFC 7519)

RFC 7519 định nghĩa một số **registered claim names**. Bản thân RFC này **không bắt buộc tất cả JWT phải chứa từng claim đăng ký**; nhu cầu sử dụng do ứng dụng hoặc profile cụ thể quyết định.

| Claim | Ý nghĩa | Khi có mặt, cần hiểu/kiểm tra thế nào? |
|---|---|---|
| **iss** | Issuer: bên phát hành JWT | So với issuer đã được cấu hình tin cậy, không tự tin chuỗi do token khai báo. |
| **sub** | Subject: chủ thể mà JWT nói đến | Định danh trong ngữ cảnh issuer; có thể là người dùng hoặc client/service tùy flow. |
| **aud** | Audience: các bên được phép nhận token | Giá trị có thể là chuỗi hoặc mảng chuỗi; verifier phải thuộc audience hợp lệ. |
| **exp** | Expiration Time: mốc hết hạn | NumericDate tính bằng giây; tại/sau thời điểm hết hạn phải từ chối, có thể áp dụng sai lệch đồng hồ nhỏ. |
| **nbf** | Not Before: chưa có hiệu lực trước mốc này | Nếu thời điểm hiện tại còn trước **nbf** (sau khi tính clock skew hợp lý) thì không chấp nhận. |
| **iat** | Issued At: thời điểm phát hành | NumericDate; hữu ích để đánh giá tuổi token nếu chính sách cần; **iat không thay exp**. |
| **jti** | JWT ID: định danh riêng của JWT | Dùng cho liên kết log, phát hiện lặp/denylist nếu có cơ chế trạng thái; **không tự chống replay**. |

Với những claims thời gian (**exp**, **nbf**, **iat**), giá trị chuẩn là **NumericDate**: số giây tính từ Unix epoch, có thể biểu diễn phần lẻ, **không phải chuỗi ngày ISO**, không mặc nhiên tính bằng mili giây. Nếu ứng dụng chỉ chấp nhận số nguyên giây, đó là quy tắc bổ sung của profile hoặc hợp đồng nội bộ.

Header JWT thường có **alg**, **kid**, **typ**; **đây là các trường header của JOSE, không phải claims trong payload**. Ví dụ **kid** giúp chọn trong tập khóa tin cậy, nhưng không cho phép token tự chỉ định một nguồn khóa bất kỳ. **alg** phải nằm trong tập thuật toán được verifier cho phép và được áp dụng đúng với khóa tin cậy.

Một token có payload:

~~~json
{
  "sub": "user-42",
  "exp": 1900000800
}
~~~

có thể là một JWT hợp lệ về **cú pháp/nội dung nền tảng** nếu được tạo đúng định dạng, nhưng **không đủ để Orders API chấp nhận** nếu API yêu cầu issuer, audience, chữ ký và access token profile cụ thể. **Đúng cú pháp không bằng đủ chứng cứ bảo mật**.

## 3. Các yêu cầu khác nhau theo loại token và profile

### 3.1. JWT access token theo RFC 9068

OAuth 2.0 **không mặc định yêu cầu access token phải là JWT**. Tuy nhiên, nếu hệ thống tuyên bố dùng **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, profile đó quy định chặt hơn JWT nền tảng.

Trong profile này, bộ claims bắt buộc của JWT access token gồm **iss, exp, aud, sub, client_id, iat, jti**. Profile cũng đặt yêu cầu cho JOSE header, trong đó có kiểu token **at+jwt** theo cách biểu diễn được profile cho phép. **Scope**, **roles**, **groups**, **entitlements** hoặc claims nghiệp vụ khác không mặc nhiên thuộc bộ claims bắt buộc chung của mọi token.

Ví dụ payload theo hướng profile này:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "exp": 1900000800,
  "iat": 1899999000,
  "jti": "token-example-892",
  "client_id": "orders-web",
  "scope": "orders:read"
}
~~~

Đây là **payload minh họa**, không phải JWT hoàn chỉnh hoặc credential có thể sử dụng. Một JWT đúng profile còn phải được ký đúng, có JOSE header phù hợp, dùng thuật toán được phép và được verifier kiểm tra theo toàn bộ profile.

**Điểm dễ nhầm:** **sub** không đồng nghĩa lúc nào cũng là tài khoản người dùng. Trong một số luồng như client credentials, chủ thể có thể đại diện cho chính ứng dụng/dịch vụ. **client_id** mô tả OAuth client; **sub** mô tả subject được token nói đến. Resource Server không được tự giả định tất cả token đều có người dùng cuối.

### 3.2. OIDC ID token

Với **OpenID Connect ID token**, nhóm claims **bắt buộc** cơ bản gồm:

| Claim | Vai trò trong ID token |
|---|---|
| **iss** | OpenID Provider/issuer của ID token |
| **sub** | Định danh subject của người dùng trong phạm vi issuer |
| **aud** | Phải chứa **client_id** của Relying Party (client) được nhận ID token |
| **exp** | Thời hạn ID token |
| **iat** | Thời điểm phát hành ID token |

Một số claims là **bắt buộc theo điều kiện**:

- **nonce:** nếu yêu cầu xác thực có gửi nonce, ID token phải chứa nonce tương ứng và client phải xác minh. Yêu cầu nonce cụ thể còn phụ thuộc flow/profile OIDC.
- **auth_time:** được yêu cầu trong những ngữ cảnh như yêu cầu **max_age** theo OIDC; khi đó client phải kiểm tra theo quy tắc liên quan.
- **at_hash** và **c_hash:** xuất hiện/được yêu cầu ở những luồng phản hồi OIDC nhất định có liên quan đến access token hoặc authorization code; không ép chúng xuất hiện trong mọi ID token.
- **azp:** có quy tắc kiểm tra riêng khi có nhiều audience hoặc khi claim này hiện diện; cần tuân theo profile OIDC áp dụng thay vì coi nó là trường luôn bắt buộc cho mọi ID token.

**ID token phục vụ client xác minh kết quả đăng nhập**, không phải access token để gọi API. Trong ID token, **aud** thường chứa client ID; trong access token, **aud** hướng tới Resource Server. Nếu một API chấp nhận ID token vì nhìn thấy **sub** hợp lệ, nó có nguy cơ chấp nhận sai loại token (*token substitution*).

### 3.3. Opaque token và token introspection

Opaque token không cung cấp cho Resource Server một JSON payload mà nó được phép tự giải mã theo nghĩa vụ của JWT. Resource Server thường gọi **introspection endpoint** tin cậy (RFC 7662). Trường bắt buộc cốt lõi của **phản hồi introspection** là **active**:

~~~json
{
  "active": true,
  "client_id": "orders-web",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Các trường ngoài **active** trong ví dụ là metadata **có thể được cung cấp tùy tình huống và chính sách issuer**; chúng không trở thành bắt buộc chỉ vì xuất hiện trong ví dụ. Nếu kết quả là:

~~~json
{
  "active": false
}
~~~

Resource Server phải từ chối token bất kể endpoint introspection trả **HTTP 200**. Khi **active=true**, API vẫn phải kiểm tra đúng audience/loại token, scope và quyền tài nguyên theo hợp đồng tin cậy. Nếu issuer không cấp đủ dữ liệu để xác minh một điều kiện cần thiết, API **không được tự suy đoán Permit**.

### 3.4. Refresh token

**Refresh token** là credential để client xin access token mới tại Authorization Server; có thể là chuỗi opaque và không có hợp đồng claims dành cho Resource Server. Không mặc định áp bộ claims bắt buộc của JWT access token lên refresh token và **không gửi refresh token tới API nghiệp vụ**. Authorization Server phải quản lý hiệu lực, ràng buộc client, thu hồi và cơ chế rotation/sender-constraining khi phù hợp với loại client và chính sách.

## 4. Bảng so sánh required/optional theo đúng ngữ cảnh

| Claim hoặc thuộc tính | JWT nền tảng RFC 7519 | JWT access token RFC 9068 | OIDC ID token | Introspection RFC 7662 |
|---|---|---|---|---|
| **iss** | Registered, không bắt buộc chỉ theo RFC 7519 | Bắt buộc | Bắt buộc | Metadata tùy chọn |
| **sub** | Registered, không bắt buộc chỉ theo RFC 7519 | Bắt buộc | Bắt buộc | Metadata tùy chọn |
| **aud** | Registered, không bắt buộc chỉ theo RFC 7519 | Bắt buộc | Bắt buộc, chứa client ID phù hợp | Metadata tùy chọn; API có thể yêu cầu theo hợp đồng |
| **exp** | Registered, không bắt buộc chỉ theo RFC 7519 | Bắt buộc | Bắt buộc | Metadata tùy chọn |
| **iat** | Registered, không bắt buộc chỉ theo RFC 7519 | Bắt buộc | Bắt buộc | Metadata tùy chọn |
| **jti** | Registered, không bắt buộc chỉ theo RFC 7519 | Bắt buộc | Không phải claim bắt buộc chung | Metadata tùy chọn |
| **client_id** | Không phải registered claim của RFC 7519 | Bắt buộc | Không phải claim bắt buộc chung | Metadata tùy chọn |
| **scope** | Không phải registered claim của RFC 7519 | Tùy việc cấp quyền/profile và hợp đồng | Không phải claim bắt buộc chung của ID token | Metadata tùy chọn |
| **nonce** | Không phải registered claim của RFC 7519 | Không phải claim bắt buộc chung | Bắt buộc khi điều kiện OIDC yêu cầu | Không phải trường bắt buộc |
| **nbf** | Registered, không bắt buộc chỉ theo RFC 7519 | Không phải claim bắt buộc chung | Không phải claim bắt buộc chung | Metadata tùy chọn |
| **active** | Không phải registered claim của JWT | Không phải claim bắt buộc chung | Không phải claim bắt buộc chung | **Bắt buộc** trong phản hồi introspection |

**Cách đọc bảng:** các cột nói về **hợp đồng khác nhau**, không phải một danh sách tổng quát để trộn lẫn. Đặc biệt, một trường “metadata tùy chọn” của introspection vẫn có thể trở thành **dữ liệu bắt buộc theo chính sách cụ thể của Resource Server**; nếu thiếu thì API phải tìm cơ chế xác minh tương đương hoặc từ chối.

## 5. Claim bắt buộc có điều kiện: hiện diện không thôi vẫn chưa đủ

Một claim có thể không bắt buộc cho mọi token nhưng **bắt buộc khi một điều kiện phát sinh**. Những trường hợp quan trọng:

| Điều kiện | Claim cần xét | Cách verifier xử lý |
|---|---|---|
| JWT có **nbf** | **nbf** | Không chấp nhận token trước thời điểm **nbf**, có thể trừ sai lệch đồng hồ nhỏ theo policy. |
| Access token dành cho nhiều API | **aud** | Verifier chỉ chấp nhận khi chính mình là audience được phép; không “chọn đại” audience đầu tiên. |
| Endpoint yêu cầu phạm vi quyền cụ thể | **scope** hoặc quyền tương đương có xác minh | Nếu thiếu bằng chứng đủ quyền, từ chối; không suy quyền mặc định rộng hơn. |
| OIDC request có **nonce** | **nonce** | Kiểm tra nonce trong ID token khớp yêu cầu gốc và quy tắc của flow. |
| OIDC request dùng **max_age** | **auth_time** | Kiểm tra thời điểm xác thực và tuổi phiên đúng giới hạn. |
| Policy yêu cầu chặn token theo định danh | **jti** hoặc token handle tương đương | Nếu định danh thiếu, không áp dụng được cơ chế đó; profile/hợp đồng phải quy định rõ. |
| Cần xử lý thay đổi quyền theo phiên bản | Version/epoch quyền hoặc trạng thái hiện hành | Nếu không có dữ liệu đủ tin cậy để chứng minh quyền còn hiệu lực, từ chối thao tác nhạy cảm. |

Nguyên tắc: **bắt buộc theo điều kiện = nếu điều kiện đúng thì giá trị phải hiện diện, đúng kiểu, đúng nguồn và được xác minh**. Không giải quyết bằng cách gán giá trị giả để bypass bước kiểm tra.

Ví dụ **iat** không chứng minh “người dùng vừa đăng nhập” nếu không có ràng buộc rõ về phiên xác thực. Khi cần xác minh **lần xác thực thực tế**, OIDC dùng **auth_time** trong những ngữ cảnh phù hợp; không tùy tiện thay bằng **iat**.

## 6. Một hợp đồng claims thực tế cho Resource Server

Giả sử hệ thống quản lý đơn hàng có hai endpoint:

~~~http
GET /orders HTTP/1.1
Host: api.example.org
Authorization: Bearer <access_token>
~~~

~~~http
POST /orders/ord-77/refund HTTP/1.1
Host: api.example.org
Authorization: Bearer <access_token>
~~~

Authorization Server phát hành **JWT access token theo RFC 9068** dành cho **orders-api**; Resource Server đã cấu hình issuer là **https://auth.example.org**. Hợp đồng nên phân tầng:

### 6.1. Điều kiện nhận token chung

- Token phải được ký đúng bởi khóa đã tin cậy gắn với issuer và thuật toán nằm trong allowlist; **không dùng claims chưa xác minh** để quyết định quyền.
- Header và claims bắt buộc của JWT access token profile phải hợp lệ; **iss** khớp issuer được cấu hình, **aud** chứa **orders-api**, **exp** chưa hết hạn; kiểm tra **nbf** nếu có.
- **sub**, **client_id**, **iat**, **jti** có đúng kiểu, ngữ nghĩa theo profile và chính sách cục bộ; có cơ chế xử lý revoke/key compromise khi cần.
- Không chấp nhận ID token, refresh token hoặc access token cấp cho một API khác chỉ vì chúng cũng chứa **sub** hay **scope**.

### 6.2. Điều kiện cho từng endpoint

| Endpoint | Scope theo chính sách | Policy phía Resource Server |
|---|---|---|
| **GET /orders** | **orders:read** | Subject/client có quyền đọc các đơn hàng được trả về theo tenant và ownership. |
| **POST /orders/{id}/refund** | **orders:refund** | Subject/client được phép hoàn tiền đơn đó; trạng thái giao dịch và hạn mức/điều kiện nghiệp vụ vẫn hợp lệ. |

Nếu token không có claim **scope** nhưng flow/profile cho phép điều đó, token có thể vẫn qua bước **xác thực token**; tuy nhiên **hai endpoint trên sẽ từ chối do thiếu quyền cần thiết**, trừ khi có một cơ chế quyền tương đương được policy chấp nhận và xác minh rõ ràng. Không cho phép chỉ vì chữ ký token đúng.

Nếu token chứa **scope=orders:refund** nhưng đơn hàng thuộc tenant khác, API **vẫn phải từ chối**. Scope giới hạn quyền cấp cho token; phân quyền theo **tài nguyên thực tế** luôn là trách nhiệm của Resource Server.

## 7. Quy trình xác minh: thiếu claim và claim sai kiểu xử lý ra sao?

~~~mermaid
flowchart TD
    A["Nhận token tại Resource Server"] --> B{"Đúng loại token và profile?"}
    B -->|Không| X["Từ chối token"]
    B -->|Có| C["Xác minh chữ ký hoặc introspection từ nguồn tin cậy"]
    C -->|Thất bại| X
    C -->|Thành công| D{"Đủ required claims theo profile?"}
    D -->|Thiếu hoặc sai kiểu| X
    D -->|Đủ| E["Kiểm tra iss, aud, thời gian, key/trust policy"]
    E -->|Không đạt| X
    E -->|Đạt| F["Kiểm tra optional claims khi hiện diện"]
    F -->|Không đạt| X
    F -->|Đạt| G["Đánh giá scope, chủ thể, tài nguyên, ngữ cảnh"]
    G -->|Không đủ quyền| Y["Từ chối phân quyền"]
    G -->|Đủ quyền| H["Cho phép thao tác"]
~~~

**Ví dụ pseudocode** cho một Resource Server chỉ nhận JWT access token theo profile đã thống nhất:

~~~text
authorize(request):
    token = requireBearerToken(request)
    if token missing:
        return 401

    # Dùng thư viện bảo mật được duy trì; không tự viết mã mật mã
    verified = verifyJwtAccessToken(
        token,
        trustedIssuer = "https://auth.example.org",
        expectedAudience = "orders-api",
        allowedAlgorithms = configuredAlgorithms,
        expectedType = "at+jwt"
    )
    if verified invalid:
        return 401

    claims = verified.claims
    required = ["iss", "sub", "aud", "exp", "iat", "jti", "client_id"]
    if missingAny(required, claims) or invalidTypesOrValues(claims):
        return 401

    if claims.nbf exists and nowBefore(claims.nbf):
        return 401
    if not issuerAudienceAndTimeValid(claims):
        return 401

    requiredScope = policy.scopeFor(request.action)
    if requiredScope not in parsedScopes(claims.scope):
        return 403

    resource = loadResourceInTrustedTenantBoundary(request)
    if not canAccess(claims.sub, claims.client_id, resource, request.action):
        return 403

    return performAuthorizedOperation()
~~~

Ví dụ trên **minh họa trách nhiệm và các bước kiểm tra**, không phải mã chạy trực tiếp hay thay thế cấu hình profile chuẩn của thư viện. Thư viện phải kiểm tra thuật toán, chữ ký, trusted key, issuer, audience, thời gian, kiểu claims và header token một cách nhất quán. Các bước liệt kê sau lời gọi verifier nhằm làm rõ hợp đồng, không phải lời khuyên xác minh bằng các thao tác thủ công riêng lẻ.

### 7.1. Cách phân biệt lỗi xác thực với lỗi phân quyền

| Tình huống | Phản hồi thông dụng | Lý do |
|---|---|---|
| Không có token, chữ ký sai, thiếu claim bắt buộc theo profile, sai audience/issuer, hết hạn | **401 Unauthorized** | Không có access token hợp lệ cho API |
| Token hợp lệ nhưng thiếu scope bắt buộc cho hành động | **403 Forbidden** | Token không đủ quyền được cấp |
| Token đủ scope nhưng không có quyền trên order hoặc tenant cụ thể | **403 Forbidden** hoặc **404 Not Found** theo policy | Phân quyền tài nguyên bị từ chối; có thể che giấu sự tồn tại |
| Introspection không hoạt động hoặc hệ thống không xác minh được token | **Từ chối/fail closed**, có thể 5xx/503 tùy chính sách | Không được tự cho phép vì dịch vụ xác minh lỗi |

Với Bearer token, cách biểu diễn lỗi và header **WWW-Authenticate** cần tuân thủ RFC 6750 khi áp dụng. Đừng tiết lộ cấu hình bảo mật, dữ liệu người dùng hay toàn bộ token qua thông báo lỗi.

### 7.2. Kiểm tra kiểu dữ liệu là yêu cầu thực tế

Một claim tồn tại nhưng **sai kiểu** không được coi là đã thỏa yêu cầu:

- **exp** là chuỗi **"1900000800"** thay vì NumericDate: không tự ép kiểu âm thầm nếu profile đòi đúng kiểu số.
- **aud** là object bất kỳ thay vì string hoặc mảng string: từ chối.
- **scope** có kiểu array khi hợp đồng yêu cầu chuỗi các scope cách nhau bằng khoảng trắng: từ chối hoặc áp dụng profile riêng đã khai báo trước; không phỏng đoán.
- **sub** rỗng hoặc không thỏa quy tắc định danh của issuer: xem là không hợp lệ theo profile/hợp đồng.
- **roles** có giá trị không thuộc tập được phép: không suy ra vai trò đặc quyền cao; áp dụng kiểm tra dữ liệu hiện hành.

Khi xử lý **scope**, phải tách thành các tên scope chính xác. So khớp chuỗi con là lỗi: **orders:read** không đồng nghĩa với **orders:read:all**.

## 8. Optional claim, giới hạn dữ liệu và quyền hiện hành

Một token có nhiều claims hơn không nhất thiết an toàn hay hữu ích hơn. **JWT ký thông thường được Base64url-encode, không được mã hóa**; client hoặc thành phần giữ token thường có thể đọc claims. Do đó:

- Chỉ cấp claims thực sự cần cho audience và policy đã định.
- Không đưa mật khẩu, refresh token, client secret, private key, thông tin tài chính/nhân sự hoặc hồ sơ cá nhân không cần thiết vào access token dễ đọc.
- Phân biệt **scope** với **roles**, **groups**, **entitlements**: cách biểu diễn của từng trường phải được hợp đồng định nghĩa; không dùng một field tự tạo mà chưa xác minh nguồn.
- Giới hạn tuổi token và chiến lược thu hồi. **Role/membership** được ghi vào JWT tại lúc phát hành có thể trở nên **cũ** khi quyền thay đổi.
- Để kiểm tra quyền trên đơn hàng/tenant, Resource Server có thể cần dữ liệu hiện hành; không cho phép mọi tài nguyên chỉ vì có **scope=orders:read**.

Ví dụ một access token có **role=ADMIN** trong payload ký hợp lệ nhưng vai trò đã bị thu hồi tại database. Nếu hệ thống cần chặn quyền tức thời, nó phải kiểm tra trạng thái quyền hiện hành, dùng cơ chế version/revocation thích hợp hoặc chấp nhận rõ độ trễ của token sống ngắn. **Claim đúng lúc phát hành không bảo đảm quyền vẫn đúng hiện tại.**

**jti** có thể hỗ trợ denylist hoặc nhận diện token; việc claim này có mặt **không tự ngăn việc kẻ tấn công phát lại bearer token**. Nếu cần hạn chế dùng lại token bị đánh cắp, cân nhắc sender-constrained tokens như DPoP hoặc mTLS trong hệ thống hỗ trợ, kết hợp kiểm soát lưu trữ, HTTPS và thu hồi.

## 9. Trường hợp đặc biệt: nhiều audience, nhiều issuer và sai loại token

### 9.1. Audience là tập hợp

JWT có thể biểu diễn **aud** bằng string hoặc mảng string. API phải kiểm tra **audience của chính nó có nằm trong giá trị cho phép**; không nhất thiết so sánh cả mảng bằng một chuỗi đơn. Tuy nhiên, nếu hệ thống yêu cầu **một audience duy nhất** để giảm phạm vi token, đó là ràng buộc bổ sung hợp lệ trong profile/hợp đồng.

~~~json
{
  "iss": "https://auth.example.org",
  "aud": ["orders-api", "reports-api"],
  "sub": "user-42",
  "exp": 1900000800
}
~~~

Payload trên chỉ minh họa trường **aud**; nó **chưa đủ** để tạo JWT access token theo RFC 9068. Orders API không vì nhận đúng audience mà mặc nhiên cho dùng mọi scope hoặc tài nguyên.

### 9.2. Issuer phải có danh tính được tin cậy

Nếu ứng dụng chấp nhận nhiều issuer, phải có **cấu hình tin cậy riêng cho từng issuer**, gồm key set, thuật toán, audience/profile và policy. Không tìm key ở issuer khác chỉ vì **kid** trùng. Không chấp nhận URL **jku/x5u** do token tự đưa vào để tạo niềm tin mới ngoài cấu hình. Khi issuer/key bị xâm phạm, Resource Server phải có cách từ chối nguồn bị ảnh hưởng, kể cả khi JWKS cũ còn trong cache.

### 9.3. Phân biệt ID token và access token

Giả sử một OIDC ID token có đủ **iss, sub, aud, exp, iat** và chữ ký hợp lệ dành cho client **orders-web**. Nó **không phải** token được thiết kế cho Orders API, ngay cả khi cùng issuer và cùng subject. API phải xác minh **loại token** và audience dành cho Resource Server; không lấy các claims đăng nhập của ID token làm bằng chứng cho quyền gọi API.

Việc một claim bắt buộc trong ID token không cho phép API suy luận nó bắt buộc theo cùng ý nghĩa trong một opaque access token hoặc refresh token.

## 10. Thiết kế contract và ma trận kiểm thử

Thay vì một danh sách claims “bắt buộc chung” không rõ bối cảnh, hãy viết **claim contract** ngắn gọn cho từng loại token:

| Thuộc tính hợp đồng | Ví dụ cho Orders API |
|---|---|
| Loại token chấp nhận | OAuth 2.0 JWT access token theo RFC 9068 |
| Issuer được tin | **https://auth.example.org** |
| Audience đích | **orders-api** |
| Header/thuật toán | Token type và thuật toán phù hợp profile, key từ issuer đã tin |
| Claims bắt buộc theo profile | **iss, exp, aud, sub, client_id, iat, jti** |
| Claims optional hoặc có điều kiện | **nbf** nếu có; **scope** nếu được cấp và nếu endpoint cần; các entitlement tùy chính sách |
| Điều kiện phân quyền | Scope chính xác theo action, quyền theo tenant/ownership và trạng thái tài nguyên |
| Thu hồi và độ mới | Chính sách token hết hạn, key/issuer revocation, kiểm tra entitlement hiện hành khi cần |
| Dữ liệu không cấp trong claims | Password, refresh token, secrets, thông tin nhạy cảm không liên quan |

**Những kiểm thử nên có**:

| Input | Kết quả mong đợi |
|---|---|
| Token đúng chữ ký, đủ required claims, đúng iss/aud/exp, đủ scope và quyền tài nguyên | **Permit** |
| Token chữ ký đúng nhưng thiếu **aud** theo RFC 9068 | **Reject token** |
| Token thiếu **scope** nhưng endpoint yêu cầu **orders:read** | **Deny authorization** nếu không có cơ chế quyền tương đương |
| Token có **nbf** trong tương lai | **Reject token** |
| Token có **exp** sai kiểu hoặc đã hết hạn | **Reject token** |
| Token sai **iss** hoặc **aud** | **Reject token** |
| ID token hợp lệ dành cho client đem gọi Orders API | **Reject token** |
| Scope đủ nhưng đơn hàng thuộc tenant khác | **Deny authorization** |
| Token còn hạn nhưng membership đã bị thu hồi | **Deny** nếu chính sách yêu cầu quyền hiện hành |
| Opaque token introspection trả HTTP 200, **active=false** | **Reject token** |
| Introspection trả **active=true** nhưng thiếu bằng chứng audience theo contract | **Reject** hoặc dùng cơ chế ràng buộc đáng tin được định nghĩa rõ |

Khi viết test, kiểm tra **kết quả HTTP và sự vắng mặt của side effects**, không chỉ giá trị boolean của một helper. Test cho permission cũ, sai tenant, thay đổi trạng thái nghiệp vụ và token sai loại là cách phát hiện nhiều lỗ hổng hơn việc chỉ kiểm tra chữ ký.

## 11. Câu hỏi tự đánh giá

**1. RFC 7519 có quy định mọi JWT phải chứa iss, sub, aud, exp và iat không?** Không. Đây là các registered claims, nhưng mức bắt buộc phụ thuộc profile hoặc ứng dụng sử dụng JWT.

**2. Với JWT access token tuân RFC 9068, có thể bỏ jti vì JWT nền tảng coi nó optional không?** Không. Profile access token đặt ra yêu cầu riêng, trong đó có jti; verifier phải áp dụng profile đã thỏa thuận.

**3. OIDC ID token có nhóm claims cơ bản bắt buộc nào?** iss, sub, aud, exp, iat. Các claim như nonce/auth_time có thể trở thành bắt buộc khi điều kiện tương ứng xuất hiện.

**4. Introspection trả HTTP 200 và active=false: Resource Server có được cho phép không?** Không. Endpoint trả lời thành công về HTTP không đồng nghĩa token còn hiệu lực.

**5. Nếu scope không phải claim bắt buộc trong mọi JWT, API có thể cho gọi endpoint khi token thiếu scope không?** Không tự động. Policy của endpoint phải có bằng chứng đủ quyền; nếu yêu cầu orders:read mà thiếu bằng chứng thì từ chối.

**6. JWT có role=ADMIN và chữ ký hợp lệ có bảo đảm người dùng luôn còn quyền ADMIN không?** Không. Role trong token phản ánh thời điểm phát hành và có thể cũ; quyền hiện hành có thể cần kiểm tra thêm.

**7. Nếu một claim optional xuất hiện với kiểu dữ liệu sai, nên bỏ qua để tiếp tục không?** Không mặc định. Hãy áp dụng quy tắc của chuẩn/profile và chính sách verifier; dữ liệu sai kiểu hoặc mâu thuẫn có thể khiến token không hợp lệ.

**Ghi nhớ:** Không có một danh sách claim bắt buộc duy nhất cho mọi token. **RFC 7519, RFC 9068, OIDC, introspection và Resource Server policy đặt ra những hợp đồng khác nhau.** Trước tiên hãy xác định loại token và profile, sau đó kiểm tra đầy đủ các required claims, kiểm tra optional claims khi xuất hiện, đối chiếu issuer/audience/thời gian và cuối cùng đánh giá scope cùng quyền trên tài nguyên. Một token đúng định dạng nhưng thiếu bằng chứng cho hành động vẫn phải bị từ chối.
