# Kiểm tra issuer

Một Resource Server nhận access token có chữ ký hợp lệ, chưa hết hạn và chứa scope **orders:read**. Nếu token ấy lại được ký bởi Authorization Server dùng cho môi trường thử nghiệm, API production có nên chấp nhận? **Không.** Chữ ký đúng chỉ chứng minh token khớp một khóa xác minh; nó không chứng minh nguồn phát hành là nguồn mà API đã lựa chọn tin cậy.

**Issuer** là bên phát hành token. Trong JWT, tên claim **iss** (*issuer*) nhận diện bên phát hành. **Kiểm tra issuer** nghĩa là đối chiếu danh tính nguồn phát hành được token khai báo với **issuer đã được Resource Server cấu hình tin cậy từ trước**, đồng thời xác minh chữ ký hoặc trạng thái token theo chính nguồn đó. Đây là bước xác định **gốc tin cậy**, trước khi đánh giá audience, scope và quyền truy cập tài nguyên.

Bài học thuộc chương **Token validation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ JWT, opaque token, OAuth 2.0/OIDC, việc kiểm tra claims, scope, audience, lưu trữ và thu hồi, cũng như cách ứng phó khi issuer hoặc signing key bị xâm phạm.

Sau bài này, bạn có thể giải thích vai trò của issuer trong mô hình tin cậy, kiểm tra **iss** đúng cách, gắn issuer với JWKS/khóa xác minh hoặc introspection, phân biệt issuer với audience và subject, và kiểm thử các tình huống sai issuer trong hệ thống nhiều API hoặc nhiều tenant.

## 1. Issuer trả lời câu hỏi: Ai phát hành token?

Trong hệ thống OAuth 2.0:

- **Authorization Server (AS)** xác thực/chấp thuận các điều kiện cấp token và phát hành access token.
- **Client** nhận token để gọi tài nguyên được bảo vệ.
- **Resource Server (RS)** nhận token, kiểm tra tính hợp lệ và đánh giá phân quyền với API/tài nguyên cụ thể.

Đối với JWT, issuer thường được biểu diễn bằng claim **iss**. Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.org/realms/shop",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800
}
~~~

Đây chỉ là JSON minh họa, **không phải token có thể sử dụng**. Claim iss cho biết token *tự khai* được phát hành bởi **https://auth.example.org/realms/shop**; để tin vào khai báo đó, verifier phải xác minh nguồn khóa, chữ ký, chính sách issuer và các điều kiện token liên quan.

| Thông tin | Trả lời điều gì? | Ví dụ |
|---|---|---|
| **iss – issuer** | Ai phát hành token? | https://auth.example.org/realms/shop |
| **sub – subject** | Token nói về chủ thể nào? | user-42, hoặc service account tùy grant |
| **aud – audience** | Token được dự định gửi cho ai? | orders-api |
| **client_id** | OAuth client nào được cấp token? | shop-web |
| **scope** | Token được cấp phạm vi quyền nào? | orders:read |
| **exp** | Token hết hiệu lực khi nào? | Unix timestamp tính bằng giây |

**Issuer khác audience.** Orders API và Payments API có thể cùng tin issuer của tổ chức nhưng chấp nhận các audience khác nhau. Một token có issuer đúng mà audience là **payments-api** vẫn không được dùng ở Orders API. Ngược lại, token có audience **orders-api** nhưng issuer đến từ hệ thống không được tin cũng phải bị từ chối.

**Issuer khác subject.** ID **user-42** do issuer A cấp có thể hoàn toàn khác **user-42** do issuer B cấp. Trong hệ thống có nhiều issuer, không được gộp danh tính chỉ theo sub; cần xem **cặp (issuer, subject)** hoặc một định danh nội bộ được ánh xạ bằng quy trình đáng tin.

## 2. Claim iss không tự tạo niềm tin

JWT có cấu trúc rõ ràng nên ai giữ token có thể Base64url-decode payload để đọc **iss**. Kẻ tấn công cũng có thể tự tạo một JSON chứa iss là URL của issuer hợp pháp. Do đó:

> **Đọc được iss chỉ biết token tuyên bố nguồn phát hành nào; xác minh token với cấu hình tin cậy mới biết nguồn ấy có được chấp nhận không.**

Hãy xét ba tình huống:

1. Token có **iss=https://auth.example.org/realms/shop** nhưng chữ ký giả → **từ chối**.
2. Token có chữ ký hợp lệ bởi một issuer khác như **https://auth.attacker.example** và có aud=orders-api → **từ chối** vì issuer chưa được cấu hình tin cậy.
3. Token có chữ ký hợp lệ bởi đúng issuer và aud=orders-api, nhưng đã hết hạn hoặc thiếu scope → vẫn **từ chối** theo điều kiện tương ứng.

Đây là các kiểm tra bổ sung cho nhau. Không được dùng *một* kết quả đạt để bỏ qua các kết quả còn lại.

### Ranh giới tin cậy nằm ở cấu hình Resource Server

Resource Server cần có **danh sách issuer được cho phép** từ cấu hình đáng tin. Với hệ thống một issuer, cấu hình đơn giản có thể là:

~~~yaml
security:
  trusted-issuer: https://auth.example.org/realms/shop
  expected-audience: orders-api
~~~

YAML trên là **mẫu cấu hình khái niệm**, không phải cấu hình chuẩn của một framework cụ thể. Điều cần chú ý là **trusted-issuer** và **expected-audience** do bên vận hành đặt, không lấy từ request của client rồi đưa thẳng vào verifier.

Nếu hệ thống hỗ trợ nhiều issuer, phải cấu hình **từng issuer hợp lệ cùng nguồn khóa/phương thức xác minh, thuật toán và chính sách tương ứng**. Không cho phép token khai báo một issuer bất kỳ rồi tự động đưa nó vào danh sách tin cậy.

## 3. Kiểm tra issuer gắn liền với chữ ký và khóa

Với JWT access token có chữ ký số bất đối xứng, Authorization Server giữ **private signing key**, còn Resource Server dùng **public key** phù hợp để xác minh. Public keys thường được công bố qua **JWKS (JSON Web Key Set)**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant CONF as Trust Configuration
    participant AS as Issuer / JWKS
    C->>RS: Bearer JWT access token
    RS->>CONF: Issuer được phép, audience, thuật toán?
    CONF-->>RS: Danh sách issuer và nguồn khóa tin cậy
    RS->>AS: Lấy JWKS từ nguồn đã xác thực khi cần
    AS-->>RS: Public keys
    RS->>RS: Xác minh chữ ký, iss, aud, thời hạn, loại token
    RS->>RS: Đánh giá scope và quyền trên tài nguyên
    RS-->>C: Permit hoặc từ chối
~~~

Một triển khai an toàn cần phân biệt:

- **Chọn issuer được phép:** nhận diện issuer dự kiến từ cấu hình của ứng dụng, route hoặc tenant đã xác thực.
- **Lấy khóa tin cậy:** chỉ lấy khóa từ JWKS/metadata gắn với issuer đã cấu hình và được kiểm tra qua kết nối bảo mật.
- **Xác minh chữ ký:** dùng thư viện hỗ trợ JOSE/JWT, thuật toán được cho phép và key phù hợp.
- **Đối chiếu iss:** sau xác minh, claim iss phải khớp issuer đang được chọn theo quy tắc so khớp của profile.
- **Tiếp tục kiểm tra token:** kiểm aud, thời gian, loại token, trạng thái thu hồi và policy phân quyền.

**kid** trong header JWT chỉ là *key identifier*, giúp chọn một key trong tập key của issuer đã tin cậy. Hai issuer khác nhau có thể cùng dùng giá trị kid; verifier không được lấy public key của issuer B để xác minh token được xử lý trong ngữ cảnh issuer A chỉ vì kid trùng.

Header chứa **alg**, **jku** hoặc **x5u** cũng không trao quyền cho token tự định nghĩa thuật toán hoặc nơi tải khóa tùy ý. Chỉ hỗ trợ thuật toán được cấu hình, hạn chế nguồn JWKS và tránh các kiểu nhầm lẫn key/algorithm.

### Phải tránh vòng lặp “token tự chứng minh token”

Một anti-pattern nguy hiểm:

~~~text
payload = base64urlDecode(token.payload)
jwks = download(payload.iss + "/keys")
key = jwks.find(token.header.kid)
if verifySignature(token, key):
    allow()
~~~

Vì payload chưa xác minh có thể do kẻ tấn công tùy ý đặt, quy trình này khiến **iss do token cung cấp điều khiển nguồn khóa đáng tin**. Kẻ tấn công có thể chỉ verifier đến JWKS của mình, tự ký token rồi được chấp nhận nếu không có giới hạn issuer độc lập.

Trong hệ thống hỗ trợ nhiều issuer, có thể *đọc sơ bộ* iss như một **gợi ý định tuyến** đến issuer đã nằm trong allowlist, nhưng gợi ý ấy **không được coi là tin cậy** cho đến khi chữ ký và iss được kiểm lại với đúng cấu hình issuer. Mọi issuer không có trong allowlist phải bị từ chối trước khi truy xuất khóa bên ngoài.

## 4. Metadata và phát hiện issuer trong OAuth 2.0/OIDC

Issuer không chỉ là một chuỗi trong token; nhiều hệ thống công bố metadata để Resource Server hoặc client tìm hiểu **endpoint, khóa và khả năng của issuer**. Với OAuth 2.0 Authorization Server Metadata (RFC 8414) hoặc OIDC Discovery, bên tiêu thụ có thể tìm được trường **issuer** và **jwks_uri** theo cơ chế phát hiện của profile.

Một metadata giả định:

~~~json
{
  "issuer": "https://auth.example.org/realms/shop",
  "jwks_uri": "https://auth.example.org/realms/shop/protocol/openid-connect/certs"
}
~~~

Đây chỉ là minh họa, không phải lời khẳng định mọi nhà cung cấp có cùng endpoint. Trong các profile có discovery:

1. Bên tiêu thụ bắt đầu từ **issuer đã được cấu hình tin cậy**.
2. Tải metadata từ vị trí discovery theo quy tắc của profile, qua kênh bảo mật và với quy tắc chống chuyển hướng tới nguồn không tin cậy.
3. Kiểm tra **issuer trong metadata khớp chính xác issuer được mong đợi**.
4. Chỉ sau đó mới dùng các endpoint/khóa được metadata công bố theo chính sách.
5. Gắn tập khóa đó với issuer tương ứng; không dùng chung tự do giữa các issuer.

Một ứng dụng có thể cấu hình **JWKS URI tĩnh** mà không cần discovery tự động, nhưng vẫn phải gắn URI/key với issuer cụ thể, kiểm tra kết nối và quy tắc update/revocation.

**Không lấy URL discovery từ yêu cầu của người dùng hoặc từ JWT chưa xác minh rồi tin ngay.** Việc tải URL tùy ý còn tạo thêm rủi ro truy cập mạng ngoài ý muốn và trộn lẫn ranh giới tin cậy.

### So khớp issuer: chính xác từng ký tự

Trong JWT, claim **iss** có kiểu **StringOrURI** và giá trị được so khớp phân biệt chữ hoa/chữ thường. Trong OIDC, issuer identifier có các ràng buộc URI của riêng profile. Đừng tự động:

- Bỏ dấu gạch chéo cuối đường dẫn.
- Đổi chữ hoa/chữ thường của một phần identifier.
- Bỏ các path segment như **/realms/shop**.
- Đổi **http** thành **https** hoặc ngược lại.
- Thay hostname theo DNS alias hay lấy issuer bằng hostname của request.

Ví dụ **https://auth.example.org/realms/shop** và **https://auth.example.org/realms/shop/** không phải hai chuỗi bằng nhau. Nếu có thay đổi danh tính issuer, cần điều phối cấu hình nơi cấp và nơi nhận token thay vì “chuẩn hóa cho dễ qua”.

**Issuer là một danh tính theo hợp đồng**, không mặc định là hostname của endpoint token, endpoint JWKS hay Resource Server. Một Authorization Server có thể phục vụ nhiều realm/tenant trên cùng host nhưng mỗi realm có issuer khác nhau.

## 5. Issuer theo từng loại token và cơ chế xác minh

| Trường hợp | Nguồn issuer cần tin | Kiểm tra ở đâu? | Điều phải tránh |
|---|---|---|---|
| **JWT access token** | Issuer đã cấu hình cho Resource Server | Kiểm chữ ký/key và claim **iss**, audience, thời gian, loại token | Nhận JWT ký bởi issuer khác chỉ vì cùng key/kid hoặc scope |
| **JWT access token theo RFC 9068** | Issuer theo Authorization Server metadata và hợp đồng profile | **iss** là claim bắt buộc; áp dụng toàn bộ profile | Áp dụng riêng iss mà bỏ **aud**, **exp**, token type |
| **OIDC ID token** | OpenID Provider đã được Relying Party cấu hình | Client kiểm **iss**, chữ ký, **aud** chứa client ID và điều kiện OIDC | Gửi ID token tới Resource Server như access token |
| **Opaque access token** | Authorization Server/introspection endpoint được cấu hình đáng tin | Resource Server kiểm trạng thái và metadata từ nguồn được xác thực | Chỉ đọc chuỗi opaque rồi tự suy issuer, hoặc tin HTTP 200 là active |
| **Refresh token** | Authorization Server đã phát hành và quản lý token | Token endpoint kiểm credential, client binding, thời hạn, thu hồi | Gửi refresh token vào API nghiệp vụ hoặc áp bộ claims JWT bắt buộc một cách máy móc |

### 5.1. JWT access token

Trong JWT nền tảng RFC 7519, **iss** là một registered claim nhưng không tự bắt buộc cho *mọi* JWT chỉ dựa trên RFC đó. Tuy nhiên, một Resource Server có thể và thường nên **yêu cầu issuer rõ ràng** theo hợp đồng an ninh. Với **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, **iss là claim bắt buộc**.

Xác minh chữ ký đúng nhưng **không kiểm iss** có thể dẫn đến nhận token từ môi trường khác hoặc một nhà phát hành không được cho phép trong hệ thống đa issuer.

### 5.2. OIDC ID token

Theo OIDC, **iss** là claim bắt buộc trong ID token. Client/Relying Party phải kiểm rằng issuer tương ứng với OpenID Provider được lựa chọn và tin cậy. Nhưng **aud của ID token hướng đến client**, trong khi audience của OAuth access token hướng đến Resource Server. Vì thế không dùng ID token như một access token, ngay cả khi **iss** và **sub** đều giống nhau.

OIDC còn có các điều kiện riêng như nonce, auth_time, azp theo flow và ngữ cảnh. Kiểm issuer là một phần của **chuỗi xác minh ID token**, không thay thế các điều kiện khác.

### 5.3. Opaque token và introspection

Với opaque token, Resource Server thường gửi token đến **introspection endpoint** của Authorization Server đã được cấu hình tin cậy, ví dụ:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-resource-server-credentials>

token=<opaque-access-token>&token_type_hint=access_token
~~~

Phản hồi giả định:

~~~json
{
  "active": true,
  "iss": "https://auth.example.org/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Trong **RFC 7662**, **active** là trường cốt lõi, còn **iss** và **aud** là metadata có thể được cung cấp theo hợp đồng. Không phải issuer nào cũng trả các trường giống ví dụ. Resource Server phải:

1. Xác thực và bảo vệ kết nối đến introspection của **issuer đã tin cậy**.
2. Kiểm **active=true**, loại token, thời hạn và các điều kiện cần thiết theo profile.
3. Nếu hợp đồng yêu cầu **iss** trong phản hồi, đối chiếu với issuer tin cậy; nếu không có trường đó, cần ràng buộc nguồn introspection/token bằng cơ chế đã thiết kế.
4. Kiểm audience và scope theo policy; không suy token hợp lệ cho mọi API chỉ vì introspection active.
5. Từ chối khi không xác minh được nguồn, response không hợp lệ hoặc điều kiện an ninh cần thiết thiếu.

**Introspection không loại bỏ khái niệm issuer**: bạn đang tin Authority nào xác nhận trạng thái token. Một response **HTTP 200** kèm **active=false** vẫn biểu thị token không hoạt động. Cache introspection cần giới hạn TTL và hỗ trợ thu hồi theo mức rủi ro.

## 6. Kiểm tra issuer trong hệ thống có nhiều tenant hoặc nhiều nhà phát hành

Ví dụ một nền tảng SaaS sử dụng hai issuer:

| Tenant/miền tin cậy | Issuer được phép | Tài nguyên đích |
|---|---|---|
| Tenant A | https://auth.example.org/realms/tenant-a | orders-api |
| Tenant B | https://auth.example.org/realms/tenant-b | orders-api |

Cùng domain và cùng Resource Server **không làm hai issuer tương đương**. Hệ thống phải quyết định rõ khi request đi vào tenant A, issuer nào được phép cấp token cho request này.

Một quy trình đa issuer an toàn có thể là:

1. Xác định **ngữ cảnh tenant** từ route, host hoặc dữ liệu khác theo cơ chế đã được bảo vệ/kiểm chứng, không chỉ tin một tenant ID do client tự khai.
2. Từ ngữ cảnh đó lấy **tập issuer được phép** từ cấu hình server.
3. Nếu cần dùng **iss chưa xác minh** để chọn trong tập ấy, chỉ dùng nó như gợi ý định tuyến; tuyệt đối không làm nguồn thêm issuer mới.
4. Xác minh chữ ký bằng **khóa của issuer đã chọn** và đối chiếu chính xác claim **iss**.
5. Kiểm audience, scope và quyền trên tài nguyên của đúng tenant sau khi token được xác minh.

### Tránh nhầm chủ thể giữa các issuer

Giả sử:

~~~text
Issuer tenant-a + sub "user-42" -> Alice
Issuer tenant-b + sub "user-42" -> Bob
~~~

Nếu database chỉ lưu **user-42**, hai người có thể bị gộp thành một danh tính. Nên dùng một định danh nội bộ được ánh xạ từ **(issuer, subject)** và bảo vệ quy trình liên kết tài khoản. Không dùng **sub**, email hay username đơn lẻ để quyết định danh tính trong hệ thống có nhiều issuer.

### Khi đổi tên hoặc chuyển issuer

Chuyển từ issuer **.../tenant-a** sang **.../tenant-a-v2** là thay đổi danh tính tin cậy, không chỉ đổi URL tải JWKS. Các Resource Server phải được cấu hình chấp nhận issuer mới theo kế hoạch chuyển đổi; issuer cũ bị vô hiệu hóa khi kết thúc chuyển đổi, theo chính sách. **Không tự chấp nhận cả hai vô thời hạn** nếu không có nhu cầu được phê duyệt và giám sát.

## 7. Quy trình xác minh JWT: từ issuer đến phân quyền

~~~mermaid
flowchart TD
    A["Nhận Bearer access token"] --> B{"Token thuộc profile được chấp nhận?"}
    B -->|Không| X["Từ chối token"]
    B -->|Có| C["Chọn issuer đã cấu hình, khóa và thuật toán tin cậy"]
    C --> D{"Chữ ký hợp lệ với đúng issuer?"}
    D -->|Không| X
    D -->|Có| E{"iss khớp issuer mong đợi?"}
    E -->|Không| X
    E -->|Có| F{"aud, exp, nbf và token type hợp lệ?"}
    F -->|Không| X
    F -->|Có| G{"Scope và quyền trên tài nguyên đủ?"}
    G -->|Không| Y["Từ chối phân quyền"]
    G -->|Có| H["Thực hiện hành động được phép"]
~~~

Pseudocode an toàn ở mức khái niệm:

~~~text
validateAndAuthorize(request):
    token = requireBearerToken(request)
    if token missing:
        return 401

    # Ngữ cảnh issuer/audience xuất phát từ cấu hình tin cậy
    policy = trustedRoutePolicy(request.route, validatedTenantContext)
    expectedIssuer = policy.issuer
    expectedAudience = policy.audience

    result = trustedJwtVerifier.verify(
        token,
        issuer = expectedIssuer,
        trustedKeys = keysBoundTo(expectedIssuer),
        allowedAlgorithms = policy.allowedAlgorithms,
        expectedTokenProfile = policy.accessTokenProfile
    )
    if result invalid:
        return 401

    claims = result.verifiedClaims
    if claims.iss != expectedIssuer:
        return 401
    if not audienceIncludesExactly(claims.aud, expectedAudience):
        return 401
    if not requiredTimeAndTypeChecksPass(claims, result.header):
        return 401
    if not scopeAllows(claims.scope, request.action):
        return 403

    resource = loadResourceInValidatedTenant(request)
    if not currentPolicyAllows(claims.iss, claims.sub, resource):
        return 403

    return executeAuthorizedOperation()
~~~

Mã trên là **pseudocode**. Trong Java hoặc ngôn ngữ khác, hãy dùng bộ kiểm tra JWT/OAuth được duy trì để thực hiện đầy đủ chữ ký, issuer, audience, thuật toán, claims, thời hạn và token type; không tự xây một JWT validator chỉ bằng giải mã Base64url. Mục tiêu của mã là làm rõ **issuer phải đi cùng đúng nguồn khóa và chính sách xác minh**, không chỉ so một chuỗi.

### Ví dụ cấu hình Java/Spring Security ở mức tham khảo

Trong ứng dụng Spring Boot dùng OAuth2 Resource Server JWT, cấu hình thường có dạng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.org/realms/shop
~~~

Đây là ví dụ về **một issuer cố định**; tính năng tự tìm metadata, thuật toán được hỗ trợ và các validators mặc định phụ thuộc phiên bản Spring Security/cấu hình. **Không suy rằng issuer-uri tự giải quyết kiểm tra audience, phân quyền trên tài nguyên, thu hồi hoặc chấp nhận nhiều issuer.** Cần cấu hình/kiểm thử expected audience và policy quyền riêng cho API, đồng thời xử lý khóa/metadata theo yêu cầu vận hành.

## 8. Vì sao sai issuer có thể tạo lỗ hổng nghiêm trọng?

### 8.1. Token từ môi trường thử nghiệm được dùng ở production

Issuer staging là **https://auth-staging.example.org**; issuer production là **https://auth.example.org**. Nếu Orders API production chấp nhận mọi JWT có chữ ký thuộc một kho key chung nhưng không kiểm **iss**, token do staging cấp có thể được chấp nhận nhầm. Tách issuer và khóa theo môi trường; viết negative test cho token staging.

### 8.2. Trộn key của nhiều issuer

Hai issuer có key ID **K1** giống nhau. Verifier chỉ tìm key theo kid toàn cục, không gắn với issuer, có thể dùng sai key để kiểm token. **Key lookup phải thuộc về issuer đã chọn**; không chọn public key theo kid như một danh tính có phạm vi toàn hệ thống.

### 8.3. Để token tự chỉ địa chỉ JWKS

Một JWT chưa xác minh đưa URL trong **jku** đến máy chủ do kẻ tấn công kiểm soát. Nếu verifier tải key ở URL đó rồi coi là đáng tin, kẻ tấn công có thể tạo chữ ký và tự xác minh. Chỉ lấy JWKS từ nguồn thuộc **issuer allowlist đã được cấu hình**, xử lý header như dữ liệu chưa đáng tin.

### 8.4. Không phân biệt ID token và access token

OIDC ID token có iss hợp lệ và chữ ký đúng nhưng aud dành cho client. Resource Server không được chấp nhận nó làm access token. Phải kiểm **đúng profile/loại token và audience**, không chỉ iss.

### 8.5. Sử dụng thông tin người dùng theo sub không có namespace

API hoặc database gán **sub=user-42** trực tiếp vào tài khoản, bỏ qua issuer. Khi tenant khác có cùng sub, thông tin định danh bị nhập nhằng. Nguồn issuer và cách ánh xạ danh tính phải là một phần của policy.

### 8.6. Tự “sửa” issuer bằng chuẩn hóa chuỗi

Verifier bỏ dấu gạch chéo cuối, chuyển host hoặc xóa path để ép một iss không khớp thành khớp. Điều này làm mờ ranh giới khi chuyển realm/tenant. Dùng so khớp đúng profile và cấu hình issuer rõ ràng.

### 8.7. Coi token có chữ ký hợp lệ là đủ

Token có thể còn hạn và được ký đúng bởi issuer tin cậy, nhưng có aud của API khác, scope thiếu hoặc user đã mất quyền trong tenant. **Issuer validation là điều kiện cần, không phải quyết định Permit toàn bộ**.

## 9. Thu hồi niềm tin khi issuer hoặc signing key bị xâm phạm

Để kiểm tra issuer đúng, Resource Server cần có khả năng **ngừng tin** issuer khi không còn an toàn.

- **Một bearer access token bị lộ:** kẻ tấn công có thể phát lại token trong phạm vi còn hiệu lực; thu hồi token theo khả năng hệ thống, hạn dùng ngắn và bảo vệ nơi lưu là các biện pháp bổ trợ.
- **Private signing key bị lộ:** kẻ tấn công có thể ký token mới với iss của issuer hợp lệ. **Kiểm tra iss và chữ ký thông thường không còn đủ**, bởi nguồn khóa dùng để kiểm đã bị chiếm. Cần chặn key bị lộ tại mọi verifier, kể cả nơi còn cache JWKS.
- **Issuer hoặc endpoint introspection bị chiếm quyền:** ngay cả khóa mới hoặc response active=true cũng có thể không đáng tin. Resource Server có thể phải tạm **vô hiệu hóa toàn bộ issuer** đến khi hạ tầng được khôi phục và kiểm chứng độc lập.

**Xóa public key khỏi JWKS trên Authorization Server chưa bảo đảm mọi API dừng chấp nhận key**: nhiều Resource Server có cache JWKS hoặc cấu hình key tĩnh. Cần cơ chế phân phối trust policy, thu hồi key/issuer ưu tiên hơn cache và kiểm thử trên mọi instance, gateway, region.

**Thu hồi refresh token không tự động làm mọi JWT access token đang tồn tại mất hiệu lực** khi Resource Server chỉ kiểm chữ ký và thời hạn. Quy trình ứng cứu cần xem xét riêng revoke token, key và issuer. Nếu hệ thống phải dừng chấp nhận ngay, policy phải có đường kiểm tra trạng thái hoặc chặn key/issuer.

Trong sự cố mạng thông thường, một số hệ thống có thể dùng public key đã cache theo chính sách sẵn sàng được định trước. Nhưng khi **key/issuer đã bị xác nhận xâm phạm**, không thể lấy lý do cache còn hạn để tiếp tục tin nguồn đã bị thu hồi.

## 10. Lỗi và phản hồi khi issuer không hợp lệ

Một API dùng Bearer token nên phân biệt **token không hợp lệ** và **quyền không đủ**:

| Tình huống | Lỗi thường gặp | Ý nghĩa |
|---|---|---|
| Token thiếu, chữ ký sai, sai issuer, sai audience, hết hạn | **401 Unauthorized** | Không có access token được API chấp nhận |
| Token hợp lệ nhưng thiếu scope bắt buộc | **403 Forbidden** | Thiếu quyền được cấp cho hành động |
| Token đủ scope nhưng subject không có quyền trên tài nguyên | **403 Forbidden**, đôi khi **404** theo policy | Từ chối phân quyền đối tượng |
| Metadata/JWKS/introspection không xác minh được do lỗi hệ thống | **Từ chối/fail closed**, có thể phản hồi tạm thời 5xx/503 | Không được bỏ qua bước xác minh issuer/chữ ký để duy trì truy cập |

Ví dụ lỗi token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Chính sách HTTP/challenge phải tuân thủ quy định Bearer token (RFC 6750) và hợp đồng API. Không nên tiết lộ public key cấu hình nội bộ, nguyên JWT, dữ liệu người dùng hoặc lý do quá chi tiết giúp kẻ tấn công dò cấu hình issuer. Ở log server, nên ghi **mã nguyên nhân an toàn** như INVALID_ISSUER, yêu cầu nào bị ảnh hưởng, issuer dự kiến và policy version, **không ghi nguyên token, authorization code hoặc refresh token**.

## 11. Ma trận kiểm thử issuer validation

| Trường hợp | Kết quả mong đợi |
|---|---|
| JWT đúng issuer, đúng chữ ký/key, đúng audience, còn hạn, đủ scope và quyền | Permit |
| JWT có iss của issuer không nằm trong allowlist | Reject token |
| JWT ghi iss hợp lệ nhưng được ký bởi key của issuer khác | Reject token |
| JWT có chữ ký hợp lệ từ staging nhưng gọi production | Reject token |
| JWT có iss thiếu path segment realm hoặc thừa dấu gạch chéo | Reject token nếu không khớp cấu hình |
| JWT có iss đúng nhưng aud của API khác | Reject token |
| JWT có iss đúng nhưng exp hết hạn | Reject token |
| JWT có iss đúng nhưng scope thiếu | Deny authorization |
| JWT có iss đúng, scope đủ nhưng user không thuộc tenant | Deny authorization |
| Token có kid trùng với key issuer khác | Không dùng key sai issuer; reject nếu không xác minh được đúng nguồn |
| Token chứa jku/x5u ngoài nguồn được phép | Không tải/tin URL tùy ý; reject khi không có key tin cậy |
| OIDC ID token hợp lệ được gửi như access token đến API | Reject token |
| Opaque token introspection của issuer tin cậy trả active=false | Reject token |
| Opaque token active=true nhưng issuer/audience binding không chứng minh được | Reject hoặc yêu cầu cơ chế xác minh tương đương đã cấu hình |
| JWKS không thể tải, không có key đáng tin | Fail closed; không bỏ bước xác minh chữ ký |
| Issuer bị chặn do sự cố, token vẫn có chữ ký từ key trong cache | Reject token trên mọi instance |
| Hai issuer cùng dùng sub=user-42 | Danh tính được phân biệt theo issuer và subject |

Đánh giá kết quả **thực tế ở API**, bao gồm không trả dữ liệu nhạy cảm hoặc tạo side effect khi issuer validation thất bại. Trường hợp âm nên chạy bằng token/khóa kiểm thử trong môi trường được kiểm soát, không cần dùng token production hay chia sẻ credential thật.

## 12. Checklist triển khai kiểm tra issuer

1. **Trust anchor:** issuer nào được cấu hình tin cậy? Cấu hình đến từ nơi được kiểm soát, không từ token/request chưa xác minh?
2. **Metadata:** nếu dùng discovery, trường issuer trong metadata có trùng issuer kỳ vọng và được tải qua kênh bảo mật không?
3. **Key binding:** JWKS và key được gắn đúng issuer chưa? kid có bị chọn từ key store toàn cục không phân biệt issuer?
4. **Algorithms:** verifier giới hạn thuật toán và thực thi đúng profile, tránh tin header alg/jku/x5u không kiểm soát chưa?
5. **Exact match:** iss có được so khớp theo giá trị đã cấu hình, không tự chuẩn hóa host/path/dấu gạch chéo không?
6. **Token type:** API chỉ nhận access token dành cho mình, không nhận ID token/refresh token hay token môi trường khác?
7. **Audience và scope:** có kiểm aud, thời hạn, nbf và quyền nghiệp vụ sau khi xác minh issuer không?
8. **Nhiều issuer:** tập issuer có allowlist rõ ràng, tách tenant và sử dụng cặp (issuer, subject) để định danh không?
9. **Opaque token:** introspection có xác thực, được gắn với issuer tin cậy và trả đủ bằng chứng cho audience/loại token không?
10. **Thu hồi:** khi issuer/key bị xâm phạm, có thể đẩy lệnh ngừng tin tới mọi Resource Server, kể cả nơi cache JWKS không?
11. **Logging:** lỗi issuer có được ghi an toàn, không làm lộ bearer token, refresh token hay secrets không?
12. **Kiểm thử:** đã có negative tests cho sai issuer, sai key, sai audience, token sai loại và môi trường staging/production chưa?

## 13. Tự kiểm tra kiến thức

**1. JWT chứa iss=https://auth.example.org đã đủ đáng tin chưa?** Chưa. Issuer do token tự khai báo; Resource Server phải đối chiếu issuer tin cậy, xác minh chữ ký đúng nguồn khóa và các điều kiện hợp lệ khác.

**2. Vì sao cùng issuer nhưng Payments API không được nhận access token của Orders API?** Vì audience khác nhau. Issuer kiểm nguồn phát hành; audience giới hạn nơi token có thể dùng.

**3. Nếu hai issuer có cùng giá trị kid, có thể dùng key của issuer nào cũng được không?** Không. kid là chỉ dẫn chọn key trong **tập khóa của issuer đã tin cậy**, không phải định danh key có hiệu lực toàn cục.

**4. Resource Server có thể tự lấy issuer từ JWT rồi tải JWKS theo URL đó không?** Không được tạo niềm tin tự động từ một JWT chưa xác minh. Chỉ cho phép issuer từ allowlist và dùng nguồn JWKS được gắn với issuer ấy.

**5. Vì sao cần ghép iss với sub trong hệ thống nhiều issuer?** Vì cùng sub có thể biểu diễn các chủ thể khác nhau do các issuer khác nhau cấp; bỏ iss có thể làm gộp sai danh tính.

**6. Opaque token không có claim iss đọc được thì có bỏ kiểm nguồn phát hành không?** Không. Nguồn introspection và cơ chế ràng buộc token với Authorization Server phải được cấu hình và xác thực đáng tin.

**7. Khi private key ký bị lộ, token có chữ ký đúng và iss khớp có còn an toàn không?** Không thể kết luận. Kẻ tấn công có thể ký token giả; hệ thống phải thu hồi niềm tin vào key/issuer và cập nhật mọi verifier.

**8. Kiểm issuer thành công có cho phép xem mọi đơn hàng không?** Không. API còn phải kiểm audience, scope, thời hạn, trạng thái token và quyền trên đơn hàng hoặc tenant cụ thể.

**Ghi nhớ:** **Kiểm tra issuer là kiểm tra gốc tin cậy của token, không phải chỉ đọc một claim.** Resource Server cần issuer được cấu hình trước, khóa hoặc nguồn introspection gắn đúng issuer, xác minh chữ ký/trạng thái token, rồi đối chiếu chính xác **iss** theo profile. Sau bước ấy vẫn phải kiểm audience, thời hạn, loại token, scope và quyền trên tài nguyên. Nếu issuer hoặc key không còn đáng tin, mọi verifier phải ngừng chấp nhận token từ nguồn bị ảnh hưởng, kể cả khi chữ ký cũ vẫn xác minh được.
