# Kiểm tra chữ ký hoặc trạng thái opaque token

Giả sử Orders API nhận header `Authorization: Bearer eyJ...`. Có nên tách chuỗi token thành ba phần rồi đọc payload? Có nên gọi authorization server để hỏi token còn hiệu lực không? Hai cách này phục vụ những mô hình token khác nhau, và **chọn sai cơ chế kiểm tra có thể khiến API tin một credential giả, token đã bị thu hồi hoặc token dành cho dịch vụ khác**.

Với **JWT access token được ký (JWS)**, resource server thường có thể **xác minh chữ ký và những claims bắt buộc ở cục bộ** bằng khóa được ủy quyền của issuer. Với **opaque access token**, resource server không biết quyền của token bằng cách tự giải mã chuỗi; nó phải **tra cứu trạng thái và metadata từ thành phần có thẩm quyền**, thường thông qua OAuth 2.0 Token Introspection (RFC 7662). Đây là hai cách xác định một credential có được chấp nhận không, nhưng **cả hai vẫn phải đi tiếp tới kiểm tra audience, scope, thời gian và quyền trên tài nguyên thực tế**.

Bài thuộc chương **Token validation** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là nắm ranh giới tin cậy và vòng đời token, phân biệt JWT/opaque, access/refresh/ID token trong xác thực và phân quyền OAuth 2.0/OIDC, cũng như cách phát hiện token sai mục đích, bị đánh cắp, bị thu hồi hoặc phát lại.

Sau khi học, bạn có thể:

- Phân biệt **xác minh chữ ký JWT**, **kiểm tra claims**, **kiểm tra trạng thái opaque token** và **quyết định authorization**.
- Xây dựng luồng xác minh JWT access token an toàn với issuer/JWKS, thuật toán cho phép, `aud`, `exp`, `nbf`, `scope` và loại token.
- Sử dụng phản hồi introspection `active` để kiểm tra opaque token mà không mặc định nó luôn có trường `aud` hoặc `scope`.
- Giải thích tác động của **cache, hết hạn, khóa ký bị xoay, thu hồi và lỗi kết nối introspection**.
- Nhận diện các lỗi: chấp nhận `alg=none`, nhầm HS256/RS256, tin URL khóa từ token, dùng ID token như access token, thiếu kiểm tra audience, hoặc mặc định `active=true` là đủ.
- Thiết kế negative tests và xử lý sự cố cho API web, mobile và service-to-service.

## 1. Cần xác minh điều gì khi nhận một token?

Token là một **credential** mà bên gọi trình ra. Một API cần trả lời nhiều câu hỏi độc lập:

| Câu hỏi | JWT được ký | Opaque token |
| --- | --- | --- |
| **Ai phát hành?** | Kiểm tra issuer và chữ ký bằng khóa đáng tin | Tin AS/nguồn tra cứu được cấu hình, xác minh metadata nếu có |
| **Token có bị sửa?** | JWS signature bảo vệ tính toàn vẹn theo thuật toán được chấp nhận | Bản thân chuỗi opaque không có ý nghĩa để API tự giải mã; AS xác định token có tồn tại/hợp lệ không |
| **Còn hiệu lực?** | Kiểm tra `exp`, `nbf`, các điều kiện khác | Kiểm tra `active` từ introspection, `exp` và policy tương ứng |
| **Dành cho API nào?** | Kiểm tra `aud` đã được AS ký và token profile | Xác định audience/resource từ introspection hoặc hợp đồng ràng buộc tài nguyên đáng tin |
| **Được làm gì?** | Kiểm tra scope/permission đã xác minh | Kiểm tra scope/permission từ phản hồi tin cậy |
| **Có bị thu hồi chưa?** | JWT tự chứa không tự báo revocation; cần cơ chế bổ sung nếu bắt buộc | Introspection thường có thể trả `active=false`, tùy độ mới của cache và chính sách |
| **Có quyền với dữ liệu này?** | API kiểm tra owner/tenant/role và nghiệp vụ | API vẫn kiểm tra owner/tenant/role và nghiệp vụ |

**Chữ ký đúng** không đồng nghĩa **token có thể dùng tại API này**. **`active=true`** cũng không đồng nghĩa **được phép thực hiện mọi thao tác**. Cả hai chỉ là những bước trong quá trình xác minh credential.

Một chính sách tổng quát:

```text
allow(request, token) =
    trustedTokenType(token)
    AND trustedIssuer(token)
    AND validIntegrityOrTrustedStatus(token)
    AND validTimeAndCurrentState(token)
    AND intendedAudienceIncludesThisApi(token)
    AND grantedScopeAllowsAction(token, request.action)
    AND subjectHasPermissionOnObject(token, request.object)
    AND additionalPolicyPasses(token, request)
```

Mỗi điều kiện phải kiểm tra bằng dữ liệu đến từ **nguồn đáng tin**, không được client tự khai qua header hay body.

## 2. Mô hình tin cậy: bên phát hành và bên sử dụng token

Trong OAuth 2.0 có ba vai trò liên quan trực tiếp:

1. **Authorization server (AS):** xác thực client hoặc người dùng theo grant thích hợp, áp dụng chính sách và phát hành access token. AS hoặc dịch vụ được ủy quyền quản lý khóa ký/trạng thái token.
2. **Client:** web app, mobile app hoặc service nhận token, giữ và trình token khi gọi API. Việc client **nắm giữ** token không khiến các claims do client tự gửi trở nên đáng tin.
3. **Resource server (RS):** API sở hữu tài nguyên, chịu trách nhiệm xác minh credential và quyết định request được thực hiện hay không.

```mermaid
flowchart TD
    C[Client có access token] -->|HTTPS + Bearer token| API[Resource server]
    API --> FORMAT{Profile/loại token được API chấp nhận}
    FORMAT -->|JWT access token ký| JWT[Kiểm tra JWS + iss + aud + exp + scope]
    FORMAT -->|Opaque access token| INT[Hỏi AS qua introspection đáng tin]
    FORMAT -->|Sai loại/không hỗ trợ| DENY[Từ chối]
    INT --> STATUS{active và resource binding hợp lệ?}
    STATUS -->|Không| DENY
    STATUS -->|Có| POLICY[Kiểm tra quyền nghiệp vụ]
    JWT -->|Không hợp lệ| DENY
    JWT -->|Hợp lệ| POLICY
    POLICY -->|Đủ quyền| OK[Thực hiện thao tác]
    POLICY -->|Thiếu quyền| DENY
```

**Không nên quyết định verifier chỉ bằng cách nhìn “token có hai dấu chấm” do attacker gửi.** Hệ thống có thể hỗ trợ cả JWT và opaque, nhưng phải xác định **trusted issuer, token profile, đường tiếp nhận và chính sách chấp nhận** rõ ràng. Một fallback từ kiểm tra JWT thất bại sang tra cứu opaque, hoặc ngược lại, chỉ được thực hiện khi **được thiết kế và ràng buộc an toàn**, không phải cách né lỗi kiểm tra chữ ký.

### 2.1. Access token không phải ID token hoặc refresh token

| Credential | Dùng ở đâu? | Vì sao không thay thế nhau? |
| --- | --- | --- |
| **Access token** | Gửi tới API/resource server đúng audience | Mang quyền truy cập theo scope và policy |
| **ID token (OIDC)** | OIDC client kiểm tra kết quả đăng nhập | `aud` thường là client ID, không phải API; không thay access token |
| **Refresh token** | Token endpoint của AS | Xin access token mới theo grant, không gửi API |
| **Session cookie** | Web backend/IdP quản lý phiên | Là credential phiên của ứng dụng, không mặc nhiên là OAuth access token |

API không được chấp nhận mọi JWT “ký đúng” như access token. Trong hệ thống dùng **RFC 9068 JWT Access Token Profile**, header `typ` có thể là `at+jwt`; cần kiểm tra profile/loại token cùng issuer, audience và các claims bắt buộc. `typ` hỗ trợ tách loại nhưng **không tự tạo sự tin cậy**.

## 3. JWT được ký: chữ ký thực sự chứng minh điều gì?

Một JWS Compact Serialization thông dụng có cấu trúc:

```text
BASE64URL(protected_header) . BASE64URL(payload) . BASE64URL(signature)
```

**Header** mô tả thuật toán `alg` và có thể chứa `kid` để chọn khóa. **Payload** có thể là JSON JWT Claims Set chứa `iss`, `sub`, `aud`, `exp`, `scope`. **Chữ ký** chứng minh thông điệp chưa bị thay đổi và được tạo bằng khóa ký tương ứng với khóa xác minh.

Ví dụ **header minh họa**:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-2026-01"
}
```

Ví dụ **payload minh họa**:

```json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "client_id": "orders-web",
  "scope": "orders.read",
  "iat": 1795000000,
  "nbf": 1795000000,
  "exp": 1795000900,
  "jti": "token-identifier-001"
}
```

Các JSON trên **chưa phải JWT hợp lệ** và không thể được tin khi chưa có chữ ký kiểm chứng được. Bất cứ ai cũng có thể Base64URL-encode payload giả với `scope=orders.admin`. Giải mã được payload **không phải** xác minh token.

### 3.1. Ký không phải mã hóa

JWT dùng **JWS ký** thường có payload dễ đọc. Chữ ký bảo đảm tính toàn vẹn/xác thực nguồn khóa, không giấu `sub`, email, role hoặc scope. Nếu cần giữ bí mật nội dung, có thể dùng **JWE** hoặc opaque token theo thiết kế, nhưng mã hóa **không thay thế** các kiểm tra issuer, audience, expiry và policy.

JWE Compact Serialization thường có **năm phần**. Một hệ thống chấp nhận JWE hoặc nested JWT cần cấu hình riêng để giải mã, kiểm tra nguồn và cấu trúc token sau giải mã theo profile; không được chỉ thấy “giải mã thành công” rồi cho phép API. Phạm vi bài này tập trung vào access token dạng **JWS** và opaque.

### 3.2. Khóa bí mật và khóa công khai

- **Chữ ký bất đối xứng** như RS256 hoặc ES256: AS giữ **private signing key**; RS chỉ cần **public verification key**. RS có thể xác minh mà không có khả năng ký token mới.
- **HMAC** như HS256: AS và RS dùng **shared secret**. Bất kỳ bên nào có secret dùng để kiểm tra cũng có thể tạo MAC hợp lệ; mô hình tin cậy vì vậy khác biệt đáng kể và cần kiểm soát nơi phân phối secret.
- **`alg=none`** biểu thị JWT không được bảo vệ bằng chữ ký theo JWS Unsecured JWT, **không phù hợp** làm access token có yêu cầu xác minh mật mã trong API thông thường; verifier phải từ chối nếu profile không cho phép.

Không có thuật toán “an toàn nhất trong mọi hệ thống”; chọn và giới hạn thuật toán theo threat model, khuyến nghị/profile và thư viện được bảo trì. **Verifier không nên tự động tin bất kỳ `alg` nào attacker ghi trong header.**

## 4. Pipeline kiểm tra JWT access token

Một resource server dùng JWT access token nên thực hiện các bước sau trong **một quy trình có chính sách rõ ràng**:

1. **Nhận credential đúng kênh:** dùng HTTPS và cơ chế chuẩn như `Authorization: Bearer <access-token>` hoặc DPoP token khi triển khai DPoP. Không nhận token tuỳ ý từ query string, log hoặc header tự chế.
2. **Xác định token profile được chấp nhận:** chỉ chấp nhận access token từ các AS đã cấu hình. Kiểm tra `typ` hoặc dấu hiệu loại token theo profile; không cho ID token, refresh token hoặc JWT nghiệp vụ khác đi qua.
3. **Kiểm tra JOSE header an toàn:** thuật toán nằm trong allowlist; loại khóa, `use`/`key_ops` và `kid` phù hợp với tập khóa tin cậy. Từ chối các cấu hình nguy hiểm như `alg=none` hoặc nhầm HS/RS.
4. **Xác minh chữ ký:** sử dụng thư viện mật mã uy tín và khóa xác minh thuộc **issuer tin cậy được cấu hình trước**, không tin khóa tùy ý do token tự đính kèm.
5. **Xác minh issuer:** `iss` trùng issuer đã cấu hình theo so khớp chính xác/semantics của profile, không nhầm hai nhà cung cấp cùng `sub`.
6. **Xác minh audience:** `aud` chứa identifier của **chính API hiện tại**. Một token dành cho Billing API không dùng được ở Orders API, dù cùng khóa ký.
7. **Xác minh thời gian:** kiểm tra `exp`, `nbf` và các claims thời gian khác theo profile. Chỉ cho clock skew nhỏ có giới hạn; từ chối token quá hạn hoặc chưa hiệu lực.
8. **Xác minh schema:** kiểu JSON/claims bắt buộc, token type, giá trị audience string/mảng, scope string/định dạng nhà cung cấp, giới hạn kích thước và các điều kiện profile.
9. **Xác minh trạng thái bổ sung nếu cần:** `jti`/denylist, `session_version`, membership hoặc trạng thái tài khoản nếu cần thu hồi kịp thời.
10. **Phân quyền:** xác minh scope, quyền user/service, tenant, owner, object và mọi điều kiện nghiệp vụ. Nếu token ràng buộc người gửi, kiểm tra DPoP/mTLS.

```mermaid
flowchart TD
    IN[Bearer JWT] --> TYPE[Profile, JOSE header và thuật toán được phép]
    TYPE -->|Không hợp lệ| REJ[Từ chối]
    TYPE --> KEY[Khóa xác minh của issuer đã cấu hình]
    KEY --> SIG{Chữ ký hợp lệ?}
    SIG -->|Không| REJ
    SIG -->|Có| CLAIMS{iss, aud, exp, nbf, token type hợp lệ?}
    CLAIMS -->|Không| REJ
    CLAIMS -->|Có| SCOPE{Scope và context phù hợp?}
    SCOPE -->|Không| REJ
    SCOPE -->|Có| OBJECT[Owner, tenant, trạng thái nghiệp vụ]
    OBJECT -->|Không đủ quyền| REJ
    OBJECT -->|Đủ quyền| OK[Cho phép]
```

### 4.1. `iss` và `aud` không thể bỏ qua

Ví dụ:

| `iss` | `aud` | Resource server hiện tại | Kết luận |
| --- | --- | --- | --- |
| `https://login.example.com` | `https://api.example.com/orders` | Orders API tin issuer đó | Có thể xét tiếp nếu chữ ký/thời hạn/quyền hợp lệ |
| `https://other-idp.example` | `https://api.example.com/orders` | Orders API không tin issuer này | Từ chối |
| `https://login.example.com` | `https://api.example.com/payroll` | Orders API | Từ chối: sai audience |
| `https://login.example.com` | `orders-web-client` | Orders API | Thường là ID token/client audience; từ chối theo access-token profile |

`iss` trả lời **ai phát hành**, `aud` trả lời **ai được nhận**. Không thể coi `sub=user-42` và chữ ký đúng là đủ để cấp quyền đọc mọi dữ liệu. API phải giới hạn scope theo least privilege.

### 4.2. `exp`, `nbf`, `iat`: đơn vị là giây

JWT `NumericDate` biểu diễn **số giây** từ epoch Unix, không phải mili-giây của JavaScript. `exp` là mốc token không được chấp nhận kể từ đó; `nbf` là mốc bắt đầu chấp nhận. `iat` cho biết lúc phát hành, **không có nghĩa người dùng vừa xác thực lại**.

Ví dụ rule khái niệm:

```text
if now >= exp + allowedClockSkew: reject
if now + allowedClockSkew < nbf: reject
if tokenLifetime > maxAllowedLifetime: reject    # nếu policy đặt TTL tối đa
if iat is impossibly far in future: reject       # nếu policy yêu cầu
```

Clock skew chỉ nên là một **dung sai nhỏ đã cấu hình**, không là lý do chấp nhận access token hết hạn rất lâu. Hãy đồng bộ đồng hồ hạ tầng và xử lý claim sai kiểu theo cách từ chối an toàn.

## 5. JWKS và xoay khóa ký: API lấy public key ở đâu?

Với chữ ký bất đối xứng, AS thường công bố **JSON Web Key Set (JWKS)** chứa các public keys. Resource server cấu hình trusted issuer và JWKS endpoint theo metadata đã được quản lý tin cậy. `kid` trong header chỉ giúp chọn khóa **bên trong tập khóa của issuer đáng tin**.

```mermaid
sequenceDiagram
    participant API as Resource server
    participant CONFIG as Trusted issuer configuration
    participant JWKS as AS JWKS endpoint
    participant CLIENT as Client
    API->>CONFIG: Lấy issuer và URL JWKS đã cấu hình
    API->>JWKS: Tải JWKS qua kênh tin cậy
    JWKS-->>API: Bộ public keys hiện hành
    CLIENT->>API: JWT có kid và chữ ký
    API->>API: Chọn key theo kid từ JWKS cache đã tin
    API->>API: Kiểm tra alg, chữ ký, claims và quyền
    API-->>CLIENT: Cho phép hoặc từ chối
```

Những điểm triển khai quan trọng:

- **Không tải `jku`, `x5u` hay URL khóa do header JWT chưa xác minh tự đưa ra**, trừ khi một profile cụ thể có cơ chế pinning/allowlist/kiểm chứng an toàn rõ ràng. Nếu không, nguy cơ SSRF và nhận khóa của attacker.
- **Không cho `kid` là đường dẫn file, SQL/LDAP expression hoặc URL** được đem dùng ngoài danh sách khóa hợp lệ. `kid` là đầu vào không đáng tin để tra cứu một key identifier.
- **Gắn cache JWKS với issuer**: key ID có thể trùng giữa hai issuer, không thể dùng chung khóa chỉ vì `kid` giống nhau.
- **Kiểm tra loại và mục đích khóa** phù hợp với thuật toán ký; không dùng nhầm khóa encryption hoặc khóa đối xứng cho bất đối xứng.
- **Khi AS xoay khóa**, có thể cần chấp nhận cả public key cũ và mới trong một khoảng thời gian để xác minh token còn hạn. Chu kỳ phân phối JWKS và TTL access token phải được thiết kế đồng bộ.
- **Không tải JWKS lại không giới hạn cho mỗi `kid` lạ**: attacker có thể gây DoS bằng hàng loạt token có kid ngẫu nhiên. Dùng cache, refresh có kiểm soát, rate limit và fail-closed khi không tìm được khóa hợp lệ.

### 5.1. Khóa ký bị lộ hoặc bị thu hồi

Nếu **private signing key bị lộ**, attacker có thể tạo JWT có chữ ký hợp lệ. Việc chỉ kiểm tra chữ ký bằng public key bị ảnh hưởng **không còn đủ tin cậy**. AS/RS phải triển khai quy trình ứng phó: ngừng dùng khóa, cập nhật JWKS/trust configuration, vô hiệu các token bị ảnh hưởng, xoay key và phân tích tác động. Điều này khác với **thu hồi một access token riêng lẻ**.

JWKS rotation bình thường không nên làm gián đoạn token còn hợp lệ; **key compromise** có thể yêu cầu vô hiệu hóa ngay cả token chưa hết hạn. Quyết định cụ thể do chính sách và khả năng hạ tầng.

## 6. Mã giả xác minh JWT trong Java/backend

Không nên tự viết thuật toán RSA/ECDSA hoặc parser JWT bằng cách nối chuỗi. Hãy sử dụng thư viện bảo mật được bảo trì, cấu hình issuer, audience, thuật toán và token profile. Pseudocode mang phong cách Java:

```java
// MÃ GIẢ: dùng framework JWT verifier đáng tin, không phải API thực tế.
VerifiedAccessToken verifyJwtAccessToken(String compactJwt) {
    JwtVerificationPolicy policy = JwtVerificationPolicy.builder()
        .trustedIssuer("https://login.example.com")
        .trustedJwksUri("https://login.example.com/.well-known/jwks.json")
        .expectedAudience("https://api.example.com/orders")
        .allowedSigningAlgorithms(Set.of("RS256"))
        .requiredTokenType("at+jwt")
        .maxClockSkewSeconds(60)
        .build();

    // verify(...) phải xác minh cả signature, header, issuer, audience,
    // expiration, not-before, token profile và schema của claims.
    return trustedJwtVerifier.verify(compactJwt, policy);
}

HttpResponse getOrder(HttpRequest request, String orderId) {
    VerifiedAccessToken token = verifyJwtAccessToken(
        readBearerCredential(request)
    );
    if (!token.scopes().contains("orders.read")) {
        return forbidden();
    }
    Order order = ordersRepository.load(orderId);
    if (order == null) {
        return notFound();
    }
    if (!authorizationPolicy.canReadOrder(
            token.subject(), token.issuer(), order)) {
        return forbidden();
    }
    return ok(onlyAllowedFields(order, token.subject()));
}
```

Trong code thật, thư viện có thể không kiểm đầy đủ các ràng buộc chỉ bằng một lời gọi: phải **cấu hình validators** riêng cho issuer/audience/type/clock/claims nếu framework yêu cầu. `trustedJwksUri` là ví dụ URL do ứng dụng **cấu hình trước**; không lấy URI tùy ý từ token. Kiểm tra chủ thể theo cặp **issuer + subject** khi hệ thống hỗ trợ nhiều issuer.

### 6.1. Đừng “decode rồi check `exp`”

Sai:

```java
// SAI: ví dụ anti-pattern, tuyệt đối không dùng để authorize.
String payload = base64UrlDecode(jwt.split("\\.")[1]);
if (json(payload).getLong("exp") > now()) {
    return allow();
}
```

Đoạn này **không xác minh chữ ký, issuer, audience, loại token, scope hoặc quyền đối tượng**. Attacker có thể tự tạo payload và `exp` tương lai. `Base64URL` là mã hóa biểu diễn, **không phải bảo vệ dữ liệu**.

## 7. Opaque token: xác minh trạng thái qua authorization server

**Opaque access token** thường là một chuỗi khó đoán, không mang cấu trúc mà resource server có thể tự giải mã để suy ra quyền. Ví dụ:

```text
Authorization: Bearer riZ8Mf9QnB...opaque-random-value
```

Resource server không tự tin rằng chuỗi này hợp lệ chỉ vì trông “ngẫu nhiên” hoặc đã xuất hiện trong request. Nó cần hỏi **AS/token service có thẩm quyền** hoặc tra trạng thái trong hạ tầng đáng tin.

OAuth 2.0 Token Introspection (RFC 7662) định nghĩa một endpoint để resource server gửi token và nhận **metadata về trạng thái hiệu lực**. Điểm cốt lõi là trường boolean `active`; thông tin khác như scope, client ID, subject, audience, issuer, hạn dùng có thể được trả theo quyền và cấu hình AS.

### 7.1. Luồng introspection

```mermaid
sequenceDiagram
    participant CLIENT as OAuth client
    participant API as Orders API
    participant AS as Authorization server
    participant DB as Token status / grant store
    CLIENT->>API: Authorization: Bearer opaque-token
    API->>AS: POST /introspect + token (API xác thực với AS)
    AS->>AS: Kiểm tra danh tính và quyền của resource server
    AS->>DB: Tra cứu token, trạng thái, audience, scope, expiry
    DB-->>AS: Kết quả
    AS-->>API: active=true + metadata được phép, hoặc active=false
    API->>API: Kiểm tra resource binding, scope, policy
    API-->>CLIENT: 200/401/403 theo kết quả
```

Ví dụ HTTP minh họa theo RFC 7662 (cơ chế xác thực resource server ở đây **được giả định đã cấu hình**, không đặt secret thật trong ví dụ):

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
```

AS phải bảo vệ introspection endpoint, dùng HTTPS và **xác thực bên gọi theo chính sách** như mTLS, client authentication hoặc cơ chế tương đương; không nên để một endpoint introspection công khai cho bất kỳ ai kiểm tra token và lấy metadata riêng tư.

`token_type_hint` là **gợi ý** giúp AS tối ưu tra cứu, **không phải bằng chứng** token đã được kiểm tra là access token. AS có thể bỏ qua hint và kiểm tra định dạng/loại thật theo hợp đồng. Resource server không được tự chấp nhận refresh token qua introspection chỉ vì client gửi `token_type_hint=access_token`.

### 7.2. Response khi token còn hiệu lực

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-web",
  "sub": "user-42",
  "iss": "https://login.example.com",
  "aud": "https://api.example.com/orders",
  "exp": 1795000900,
  "iat": 1795000000
}
```

Đây là **response minh họa theo hợp đồng AS**, không phải tất cả trường đều bắt buộc trong RFC 7662. `active=true` là tín hiệu AS coi token đang hoạt động **trong ngữ cảnh trả lời**; resource server vẫn phải xác minh **token dành cho API hiện tại**, có scope phù hợp và quyền dữ liệu đáp ứng policy.

### 7.3. Response khi token không còn hoạt động

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"active": false}
```

Theo RFC 7662, một token không hợp lệ/không còn hoạt động hoặc không được resource server phép introspect có thể nhận response `active=false`. AS không cần tiết lộ vì sao token thất bại; cách này giảm rủi ro lộ trạng thái tài khoản/token. **HTTP 200 ở đây là thành công của cuộc gọi introspection, không phải token hợp lệ.** Resource server phải đọc boolean `active`, không chỉ nhìn status HTTP.

Nếu response lỗi 401/403 của **introspection endpoint** do API xác thực sai với AS, đó là **lỗi kết nối/xác thực giữa các service**, không phải tín hiệu cho phép client cuối truy cập.

## 8. `active=true` chưa đủ: ràng buộc audience và quyền

Một thiếu sót phổ biến khi dùng opaque token là:

```text
if introspection.active == true:
    allowAll()
```

**Sai.** Token có thể được phát hành cho Billing API hoặc có `scope=orders.read` nhưng client yêu cầu xóa đơn. Phải kiểm tra **resource binding, scope và chính sách nghiệp vụ**.

| Metadata từ introspection | RS cần xác minh | Lưu ý |
| --- | --- | --- |
| `active` | Phải là boolean `true` | Không chuyển string `"true"` thành boolean một cách lỏng lẻo |
| `aud` | Chứa resource identifier của API hiện tại, **nếu AS trả claim này** | RFC 7662 không buộc mọi AS trả `aud` |
| `scope` | Có quyền cần cho endpoint theo hợp đồng | Không suy ra toàn quyền nếu response thiếu scope |
| `iss` | Issuer được cấu hình và tin cậy khi metadata hiện diện | Bảo vệ endpoint và route theo đúng AS |
| `client_id` | Client được cấp token, kiểm tra policy khi cần | Không thay thế audience |
| `sub` | Chủ thể token để áp dụng quyền owner/tenant | Với S2S có thể đại diện client/workload |
| `exp` | Hạn dùng và giới hạn cache/policy nếu trả | `active` cũng có thể phản ánh hết hạn tại AS |
| `token_type`/`cnf` | Loại token và sender constraint khi hợp đồng sử dụng | Không tự chấp nhận sai loại hoặc bỏ qua proof |

### 8.1. Nếu introspection không trả `aud` thì sao?

**Không được suy ra token dành cho mình chỉ vì `active=true`.** Cần một cơ chế resource binding **đáng tin đã được thống nhất với AS**, chẳng hạn:

- Introspection được **phân quyền theo danh tính resource server**, chỉ trả active với token dành cho chính RS đó; hoặc
- Metadata/resource identifier riêng theo hợp đồng, được AS xác nhận và RS so sánh; hoặc
- Thiết kế AS/gateway quản lý audience tập trung, chứng minh token không thể bị chấp nhận tại API ngoài phạm vi.

Nếu không có căn cứ đáng tin để xác định token được cấp cho API nào, resource server nên **từ chối và sửa cấu hình/hợp đồng**, thay vì mở rộng quyền. Hãy ghi rõ **introspection endpoint nào, danh tính RS nào, audience nào và các metadata nào** được kiểm tra.

### 8.2. Introspection thành công không bảo đảm quyền trên object

Token `active=true` và `scope=orders.read` vẫn không được phép đọc `GET /orders/9001` nếu đơn 9001 thuộc tenant khác. Quyết định cuối phải kiểm tra **owner, tenant, role, trạng thái và field-level policy** với dữ liệu hiện hành.

## 9. Mã giả xử lý opaque access token

```text
function authorizeOpaqueToken(request, orderId):
    rawToken = readBearerCredential(request)
    if rawToken missing or violatesInputPolicy:
        return 401 Unauthorized

    result = trustedIntrospectionClient.introspect(
        token = rawToken,
        asEndpoint = CONFIGURED_INTROSPECTION_URL,
        resourceServerIdentity = CONFIGURED_RS_CREDENTIAL
    )

    if result unavailable or response invalid:
        # Không được coi lỗi network của AS là token hợp lệ.
        return rejectOrServiceUnavailableAccordingToPolicy()
    if result.active != true:
        return 401 Unauthorized

    if !isForThisResource(result, CONFIGURED_AUDIENCE_POLICY):
        return 401 Unauthorized
    if !hasScope(result.scope, "orders.read"):
        return 403 Forbidden

    order = orderRepository.load(orderId)
    if order not found:
        return 404 Not Found
    if !currentAuthorizationPolicy.canRead(result.sub, order):
        return 403 Forbidden

    return 200 OK with allowedFields(order)
```

Đây là **pseudocode**: không phải tên method của thư viện Java thật. `isForThisResource` phải dựa trên **metadata đáng tin hoặc hợp đồng introspection resource-bound**, không dựa vào request từ client.

**Fail closed** nghĩa là khi không xác minh được credential, API **không cho phép truy cập**. Tùy thiết kế, lỗi AS unavailable có thể trả `503 Service Unavailable` thay vì `401` để thể hiện vấn đề hạ tầng, nhưng không được trả dữ liệu bảo vệ chỉ vì introspection tạm ngừng.

## 10. JWT cục bộ so với introspection: độ trễ, cache, thu hồi

| Tiêu chí | JWT/JWS xác minh cục bộ | Opaque token qua introspection |
| --- | --- | --- |
| Nơi giữ trạng thái token | JWT chứa claims đã ký; có thể xác minh offline | AS/token store là nguồn xác nhận trạng thái hiện hành |
| Xác minh cơ bản | Chữ ký + issuer, audience, thời gian, token type, claims | HTTP call đáng tin để nhận `active` + metadata, tiếp theo kiểm tra policy |
| Network per request | Không bắt buộc sau khi có public key/JWKS cache | Thường có nếu không cache introspection |
| Độ trễ | Thường thấp, có thể scale ngang độc lập | Phụ thuộc AS/network/cache |
| Thu hồi token riêng lẻ | Cần denylist, short TTL, session/policy lookup hoặc thiết kế khác | AS có thể phản ánh bằng `active=false`, nhưng cache làm chậm |
| Key rotation | Cần phân phối/cập nhật JWKS | Backend AS xử lý việc phát hành/trạng thái token; RS vẫn phải bảo vệ kênh kết nối |
| Rủi ro lộ claims | JWT ký thường có payload đọc được | Chuỗi opaque không tiết lộ nội dung trực tiếp cho bên cầm token |
| Rủi ro tập trung | Tính đúng đắn thư viện/JWKS/claims tại từng RS | Khả dụng/bảo mật introspection endpoint và token store |
| Quyền dữ liệu thực tế | Vẫn kiểm tra owner, tenant và policy hiện hành | Vẫn kiểm tra owner, tenant và policy hiện hành |

**Opaque không mặc nhiên an toàn hơn JWT** và JWT cũng không mặc nhiên hiệu quả hơn trong mọi kiến trúc. Opaque phù hợp khi cần quản lý trạng thái tập trung và không muốn lộ claims trong token; JWT thuận tiện khi cần kiểm tra phân tán, độ trễ thấp và cân đối thời gian sống/thu hồi.

### 10.1. Cache introspection sao cho không vô hiệu hóa revocation?

Mỗi lần gọi introspection qua mạng có thể tăng độ trễ và tải AS. RS thường muốn **cache metadata đã xác minh**, nhưng điều này tạo **cửa sổ token đã bị thu hồi vẫn được chấp nhận theo cache**.

Một chính sách cache nên:

1. Chỉ cache kết quả từ AS đã được xác thực, không cache response lỗi mạng như `active=true`.
2. Giới hạn thời gian cache theo **mức rủi ro, thời hạn `exp` nếu có và mục tiêu độ trễ thu hồi**.
3. Phân biệt cache theo **token và ngữ cảnh resource server/issuer**, tránh dùng kết quả introspection của API A làm bằng chứng API B có quyền.
4. Cân nhắc cache `active=false` ngắn có kiểm soát nhằm hạn chế tải/abuse; không làm hỏng trải nghiệm token mới nếu luồng có cơ chế đặc biệt.
5. Giới hạn memory/size cache, tránh lưu token thô ở log hoặc key dễ lộ; cân nhắc digest/HMAC của token làm cache key theo thiết kế.
6. Có cơ chế invalidation/push event hoặc thời hạn rất ngắn cho thao tác nhạy cảm nếu cần thu hồi gần tức thời.

**Ví dụ:** AS thu hồi token lúc 12:00 nhưng RS cache `active=true` đến 12:02. Trong hai phút ấy, RS có thể vẫn cho phép request nếu không có kiểm tra khác. Đây là **trade-off có chủ đích** cần ghi rõ trong threat model, không phải tính chất “thu hồi ngay” của opaque token.

### 10.2. JWT và sự thay đổi quyền

JWT ký có `exp` còn 10 phút nhưng user vừa mất quyền `orders.write`. Nếu API chỉ đọc claims `scope/roles` từ JWT mà không kiểm tra policy hiện hành, quyền cũ có thể được sử dụng đến hạn token. Cần cân nhắc:

- Access token **ngắn hạn**, scoped/audience-restricted.
- Dữ liệu **owner/tenant/permission** được kiểm tra ở API ở thời điểm request.
- **Denylist/`jti`** hoặc kiểm tra session/credential version với backend khi cần thu hồi nhanh.
- Introspection/token status checking cho JWT nếu kiến trúc hỗ trợ kết hợp.
- Xử lý key compromise khác với logout thông thường.

Việc thu hồi **refresh token** thường ngăn tạo access token mới, nhưng **không làm mọi JWT access token đã cấp mất hiệu lực tức thì** nếu verifier chấp nhận offline đến `exp`.

## 11. Xác minh access token không thay thế authorization

API có thể nhận JWT đã ký hợp lệ hoặc opaque `active=true`, có `scope=orders.read`. Điều đó chỉ nói API **có thể xét tiếp yêu cầu đọc**. Nó không chứng minh user được xem mọi đơn.

```mermaid
flowchart TD
    TOKEN[Token hợp lệ] --> AUD{Đúng API audience?}
    AUD -->|Không| DENY[Từ chối]
    AUD -->|Có| SC{Có scope orders.read?}
    SC -->|Không| DENY
    SC -->|Có| DATA{User có quyền với order và tenant?}
    DATA -->|Không| DENY
    DATA -->|Có| FIELD{Trường dữ liệu được phép hiển thị?}
    FIELD -->|Không| DENY
    FIELD -->|Có| OK[Trả dữ liệu]
```

Một số loại quyền phổ biến:

| Thuộc tính | Vai trò |
| --- | --- |
| `scope` | Quyền thao tác được cấp **cho token** |
| `sub` hoặc actor | Định danh chủ thể để áp dụng chính sách |
| `roles` / `permissions` | Claims riêng hoặc theo profile, cần issuer tin cậy và hợp đồng |
| `tenant_id` | Ngữ cảnh tenant, không thay thế kiểm tra tenant thực tế |
| `aud` | Resource server được phép sử dụng token |
| `auth_time`, `acr` | Ngữ cảnh xác thực từ IdP/OP đáng tin nếu nghiệp vụ cần step-up |

Đừng tin header `X-Role: admin`, JSON `{"isAdmin":true}` hoặc `tenant_id` do client tự khai. Nếu quyền thay đổi nhanh, cần cân bằng TTL token với policy lookup theo hiện trạng.

## 12. Sender-constrained token: khi chữ ký hoặc `active` vẫn chưa đủ

Phần lớn bearer access token cho phép bên sở hữu chuỗi token sử dụng nó. Nếu token bị đánh cắp, **chữ ký vẫn đúng** và **`active` vẫn có thể là true**, nên cả hai hình thức validation cơ bản không tự ngăn replay.

OAuth có những cơ chế **sender-constrained access token**:

- **DPoP (RFC 9449):** client ký một proof cho request bằng private key; access token liên kết với public-key thumbprint, thường qua `cnf.jkt`. API cần xác minh proof, `htm`, `htu`, `iat`, `jti`, nonce nếu dùng và `ath` liên kết với access token theo profile.
- **mTLS-bound access token (RFC 8705):** token ràng buộc với client certificate; resource server kiểm tra chứng chỉ của kết nối mTLS khớp metadata ràng buộc trong token/trạng thái AS.

```text
JWT signature valid OR opaque active=true
    + valid audience/scope/time
    + token.sender_constrained?
         YES -> verify DPoP proof or mTLS certificate binding
         NO  -> apply bearer-token safeguards
    + object-level authorization
```

Nếu token yêu cầu DPoP hoặc mTLS nhưng không có proof/chứng chỉ hợp lệ, phải từ chối. **Chỉ nhìn `cnf` mà bỏ qua bằng chứng sở hữu khóa là sai.** Sender constraint làm việc sử dụng **bản sao token** khó hơn nhưng không thay scope, audience, quyền dữ liệu hoặc kiểm tra mức xác thực người dùng.

## 13. Đưa JWT và opaque token vào ứng dụng web, mobile, S2S

### 13.1. Web với Backend-for-Frontend (BFF)

Browser có thể chỉ giữ **session cookie** còn BFF giữ OAuth access/refresh token trên server. BFF gửi access token tới API đích, API kiểm tra bằng JWT verifier hoặc introspection theo hợp đồng. Cookie có `HttpOnly`, `Secure` và `SameSite` phù hợp, đồng thời bảo vệ CSRF/XSS. API **không nên** tin cookie của ứng dụng khác như OAuth access token nếu chưa có session/credential trust contract.

### 13.2. SPA

SPA có thể nhận access token và gửi tới API trực tiếp. Authorization Code + PKCE giúp bảo vệ code exchange, **không bảo vệ token đã cấp khỏi XSS**. Nếu access token bị lộ, JWT signature hoặc opaque active vẫn hợp lệ cho đến khi hết hạn/thu hồi; do đó cần token TTL hợp lý, chống XSS, scope/audience hẹp và cân nhắc BFF khi phù hợp.

### 13.3. Mobile

Native app là public client, thường dùng Authorization Code + PKCE qua trình duyệt hệ thống. Refresh token nếu được cấp cần được bảo vệ trong Keychain/Keystore; API vẫn phải tự xác minh access token **đúng issuer và resource**, không tin app vì đã qua màn hình login. Vân tay/PIN cục bộ không làm `iat` của token thành bằng chứng người dùng vừa đăng nhập tại OP.

### 13.4. Service-to-service

Với OAuth `client_credentials`, AS xác thực workload/client bằng private-key JWT, mTLS, workload identity hoặc secret quản lý an toàn. Access token được cấp cho API có thể mang `sub` đại diện service theo profile; API xác minh scope và service permissions. Không mặc định mọi token đều có user `sub` hoặc đều mang MFA claims.

Khi service A gọi B, **không chuyển nguyên token có `aud=A` sang B**. Dùng token exchange/delegation (nếu hỗ trợ) hoặc cấp token riêng cho B theo policy, tránh confused deputy. Token nội bộ cũng cần kiểm audience và quyền, không chỉ dựa vào network isolation.

## 14. Xử lý lỗi và fail-closed

| Tình huống | Nhóm nguyên nhân | Hành vi API nên thực hiện |
| --- | --- | --- |
| Không có access token | Credential thiếu | 401; nêu challenge phù hợp nếu cần |
| JWT sai chữ ký/thuật toán/issuer/audience | Credential không đáng tin hoặc sai đối tượng | 401; không parse payload làm quyền |
| JWT hết hạn/chưa hiệu lực | Điều kiện thời gian thất bại | 401; client có thể xin token mới qua luồng hợp lệ |
| Opaque introspection `active=false` | Token không hợp lệ/đã thu hồi/chưa được phép dùng | 401; không suy nguyên nhân từ HTTP 200 |
| Introspection timeout/503 hoặc JSON không đúng schema | Hạ tầng AS/trust lookup lỗi | **Không cho phép request**; trả 503/5xx hoặc mã phù hợp theo policy, alert |
| Token hợp lệ nhưng thiếu scope | Authorization thiếu | 403, có thể `insufficient_scope` |
| Scope đủ nhưng sai owner/tenant | Object-level authorization thiếu | 403 hoặc 404 để che đối tượng |
| Token ràng buộc DPoP/mTLS nhưng proof sai | Credential chưa chứng minh sở hữu khóa | Từ chối theo profile |
| JWKS chứa khóa mới chưa được cache | Cần refresh key có kiểm soát | Refresh JWKS trong giới hạn, nếu vẫn không xác minh được thì từ chối |

Ví dụ error OAuth Bearer:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Hoặc token hợp lệ nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
```

Không ghi nguyên access token hoặc refresh token vào error response, log, tracing, URL hay crash report. Thông điệp bên ngoài nên hạn chế tiết lộ chi tiết ký/mật mã; chi tiết nội bộ phục vụ audit phải được bảo vệ phù hợp.

### 14.1. Tránh biến hỏng AS thành “cho phép tạm”

Anti-pattern:

```text
try:
    tokenInfo = introspect(token)
except NetworkTimeout:
    return allow()  # SAI: fail open
```

Cách đúng: **không cho phép truy cập dữ liệu bảo vệ nếu không có bằng chứng credential hợp lệ**. Hệ thống có thể dùng một **cache còn hạn đã được xác minh** theo policy để giảm phụ thuộc mạng, nhưng không tự coi request hợp lệ khi cache hết hạn và AS không trả lời.

## 15. Các tình huống thực hành

### Tình huống A: JWT payload giả có `scope=orders.admin`

Attacker tự tạo ba phần Base64URL có `sub=user-42`, `scope=orders.admin`, `exp` tương lai nhưng chữ ký không được tạo bằng private key của AS. Nếu API chỉ decode payload, attacker có quyền quản trị. **Kết quả đúng:** verifier từ chối ngay tại bước chữ ký.

### Tình huống B: ID token ký đúng, API sai audience

Một client nhận ID token `aud=orders-web-client` và đưa nó cho Orders API. Hai token có thể cùng issuer và `sub`, nhưng Orders API chỉ nhận access token `aud=orders-api`. **Kết quả đúng:** từ chối token type/audience, không dùng ID token làm bearer access token.

### Tình huống C: Opaque token `active=true` của API khác

Billing API và Orders API cùng dùng AS; AS trả `active=true` cho token Billing. Nếu Orders API chỉ nhìn `active`, nó nhận nhầm. **Kết quả đúng:** Orders API chỉ chấp nhận token có **resource binding dành cho Orders**, qua `aud` hoặc hợp đồng introspection an toàn.

### Tình huống D: Thu hồi token nhưng RS vẫn cache

AS trả `active=true` lúc 10:00. Token bị thu hồi lúc 10:01, nhưng Orders API giữ cache đến 10:05. **Kết luận:** API có thể tiếp tục chấp nhận token trong TTL cache. **Giải pháp:** điều chỉnh TTL/invalidation theo mục tiêu thu hồi và độ nhạy cảm của API; không tuyên bố revocation tức thì nếu kiến trúc chưa đáp ứng.

### Tình huống E: Refresh token bị thu hồi, JWT access token vẫn còn hạn

Sau logout, AS thu hồi refresh token. Một access JWT cũ có `exp` sau ba phút vẫn được Orders API xác minh offline. **Kết luận:** không có cơ chế trạng thái bổ sung thì token cũ có thể còn hiệu lực. **Giải pháp:** session version/denylist hoặc TTL phù hợp và policy thu hồi nhanh nếu cần.

### Tình huống F: `kid` tùy ý gây SSRF/DoS

Attacker tạo JWT có `kid` ngẫu nhiên hoặc `jku` trỏ tới máy chủ họ kiểm soát. API tải URL này hoặc refresh JWKS vô hạn, gây SSRF/DoS, thậm chí tin khóa sai. **Giải pháp:** issuer/JWKS cấu hình sẵn, allowlist thuật toán/loại khóa, chọn key trong tập tin cậy, giới hạn refresh và fail closed.

### Tình huống G: Có scope nhưng sai tenant

Token JWT ký đúng hoặc opaque active có `orders.read`. Client gọi `GET /orders/9001` thuộc tenant khác. **Kết quả đúng:** từ chối dù token hợp lệ. Validation xác lập **credential**, còn authorization kiểm tra **tài nguyên cụ thể**.

## 16. Ma trận negative tests

Khi triển khai API, nên chạy ít nhất các tình huống sau:

| # | Đầu vào kiểm thử | Kỳ vọng |
| --- | --- | --- |
| 1 | JWT có payload đọc được nhưng chữ ký sai | Từ chối |
| 2 | JWT có `alg=none` hoặc thuật toán ngoài allowlist | Từ chối |
| 3 | JWT dùng khóa sai issuer hoặc `kid` không tìm thấy sau refresh hợp lệ | Từ chối |
| 4 | JWT `iss` lạ dù có `sub` quen thuộc | Từ chối |
| 5 | JWT `aud` của API B gửi tới API A | Từ chối |
| 6 | ID token `aud=client_id` gửi làm Bearer cho API | Từ chối |
| 7 | Access JWT hết hạn hoặc chưa tới `nbf` | Từ chối theo clock policy |
| 8 | JWT có `exp` sai kiểu, scope sai schema hoặc claim trùng tên | Từ chối theo parser/profile an toàn |
| 9 | Opaque introspection trả HTTP 200 với `active=false` | Từ chối |
| 10 | Opaque introspection trả `active=true` nhưng không có resource binding đáng tin | Không tự cho phép |
| 11 | Introspection timeout/AS lỗi HTTP 5xx | Fail closed, không trả dữ liệu |
| 12 | Token hợp lệ nhưng thiếu `orders.read` | Từ chối: thiếu scope |
| 13 | Token hợp lệ và đủ scope nhưng sai tenant/owner | Từ chối |
| 14 | Token bị thu hồi với cache đang còn hiệu lực | Xác nhận độ trễ không vượt mục tiêu đã thiết kế |
| 15 | AS xoay khóa, có token ký bằng khóa cũ còn hạn | Xử lý theo kế hoạch key rotation |
| 16 | JWKS endpoint bị giả mạo hoặc `jku` từ token lạ | Không chấp nhận khóa tùy ý |
| 17 | DPoP/mTLS-bound token được gửi mà thiếu proof/chứng chỉ | Từ chối |
| 18 | Refresh token hoặc session cookie được gửi làm access token | Từ chối |
| 19 | Client gửi claim `role=admin`/`tenant_id` ngoài token đã xác minh | Không dùng làm quyền |
| 20 | JWT hợp lệ nhưng membership bị gỡ và API yêu cầu policy realtime | Từ chối theo trạng thái hiện hành |

Nên tách **unit tests** (parser/claims/authorization), **integration tests** với AS/JWKS/introspection, **failure injection** (timeout, cache stale, key rotation) và **security tests** cho token theft/replay. Một test “JWT hợp lệ, API trả 200” không đủ chứng minh verifier an toàn.

## 17. Checklist triển khai token validation

Trước production, người thiết kế API phải trả lời:

1. **API nhận loại token nào?** JWT access token theo profile nào, opaque token của AS nào? Có chặn ID/refresh token không?
2. **Nguồn tin cậy?** Trusted issuer/JWKS/introspection endpoint có cấu hình rõ và bảo vệ chống thay khóa không?
3. **Chữ ký?** Có enforce thuật toán allowlist, key type, chữ ký, `typ` theo profile và xử lý `kid`/JWKS rotation an toàn?
4. **Claims?** Có kiểm `iss`, `aud`, `exp`, `nbf`, kiểu dữ liệu, profile/claims bắt buộc và TTL tối đa khi cần?
5. **Opaque?** Có xác thực resource server với introspection endpoint, kiểm `active`, scope và **resource binding đáng tin** không?
6. **Cache?** JWKS và introspection cache có giới hạn, cách refresh, mục tiêu revocation và xử lý AS unavailable?
7. **Quyền?** Có kiểm scope và quyền theo user/service, owner, tenant, field, trạng thái nghiệp vụ?
8. **Phát lại?** Có biện pháp phù hợp cho token theft/replay; kiểm DPoP/mTLS proof nếu token ràng buộc sender?
9. **Vòng đời?** JWT hết hạn, refresh token bị thu hồi, logout, khóa tài khoản, đổi quyền và key compromise được xử lý có thể kiểm chứng?
10. **Theo dõi?** Có ghi audit metadata vừa đủ (issuer, client, audience, endpoint, kết quả kiểm tra, lý do policy) mà không log token/PII thừa?
11. **Kiểm thử?** Đã thử sai chữ ký/thuật toán/issuer/audience/type, opaque inactive, introspection timeout, thiếu scope, sai tenant và cache stale?

**Điểm cần nhớ:** xác minh chữ ký JWT và kiểm tra trạng thái opaque token là hai cách giải bài toán **tin credential có điều kiện**. JWT signature chỉ có giá trị khi được xác minh bằng khóa và thuật toán đã tin, tiếp theo là kiểm tra issuer/audience/thời hạn/loại token. Opaque `active=true` chỉ có giá trị khi đến từ AS đáng tin và được ràng buộc với đúng resource server. **Không cách nào thay thế kiểm tra scope và quyền trên dữ liệu thực**, và không cách nào tự ngăn việc dùng lại bearer token đã bị đánh cắp nếu thiếu các biện pháp bảo vệ bổ sung.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, `iss`, `aud`, `exp`, `nbf`, `jti` và NumericDate.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký, protected header, Compact Serialization.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JSON Web Key và JWKS.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): phân biệt mã hóa với ký.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): chống algorithm/key confusion, token type và issuer/audience validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile và xác minh tại resource server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, introspection request/response và kiểm soát truy cập.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi OAuth token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, xử lý lỗi và bảo vệ bearer token.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): gắn quyền với tài nguyên đích.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): token ràng buộc chứng chỉ.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): bằng chứng sở hữu khóa và chống replay.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ OAuth token, refresh token và các rủi ro thực tế.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, audience client và ngữ cảnh xác thực.
