# Token validation

**Token validation** là quá trình API hoặc resource server kiểm tra một access token trước khi dùng nó làm bằng chứng cho request. Việc kiểm tra phải xác định token do issuer nào phát hành, dành cho resource nào, còn hiệu lực hay không, có đúng loại token và đáp ứng điều kiện bảo mật nào. Sau đó API mới dùng scope, claim và context đã xác minh làm đầu vào cho quyết định authorization trên action và resource cụ thể.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, federation và account recovery. Trong API, token thường đại diện quyền truy cập được cấp cho client hoặc workload. API cần xác minh token theo profile đã thỏa thuận với authorization server; không thể chỉ decode payload hoặc tin rằng một chuỗi trông giống JWT là hợp lệ.

Điểm cốt lõi: **token hợp lệ về mật mã vẫn có thể không hợp lệ đối với API đang nhận request**. Chữ ký đúng không thay thế issuer, audience, expiry, token type, scope, sender constraint và authorization. Một ID Token dành cho client không phải access token cho API; một access token dành cho API A không được mặc nhiên chấp nhận ở API B.

## 1. Token validation giải quyết điều gì?

Access token là credential được authorization server cấp cho client để truy cập resource theo một grant, scope, audience và policy. Khi API nhận request mang token, resource server phải xác minh token trước khi thực hiện nghiệp vụ.

Token validation thường trả lời các câu hỏi:
- Token có được phát hành bởi issuer được API tin cậy không?
- Token có nguyên vẹn và được ký bằng key phù hợp không, nếu token có chữ ký?
- Token có dành cho API/resource server hiện tại không?
- Token đã bắt đầu có hiệu lực và còn trong thời hạn không?
- Token có đúng loại/profile và được dùng đúng mục đích không?
- Client, subject, scope, tenant và các claim cần thiết có hợp lệ không?
- Token đã bị revoke hoặc bị đánh dấu không còn được tin cậy không?
- Nếu token bị ràng buộc với key/certificate, request có chứng minh quyền kiểm soát key đó không?

### 1.1. Authentication, token validation và authorization

| Bước | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Chủ thể đã chứng minh danh tính bằng cách nào? | User đăng nhập bằng passkey tại IdP. |
| **Token issuance** | Authorization server cấp credential nào cho client? | Access token có audience là orders-api và scope orders.read. |
| **Token validation** | API có thể tin token cho request này không? | Kiểm tra signature, issuer, audience, expiry và token type. |
| **Authorization** | Principal được phép làm action nào trên resource nào? | User được đọc order thuộc account của mình. |

Token validation không tự quyết định người dùng được đọc mọi dữ liệu. Sau khi token hợp lệ, API vẫn cần kiểm tra object ownership, tenant, role, business rule và các điều kiện authorization khác.

### 1.2. Token không phải bằng chứng tự xác minh

Một token là dữ liệu được phát hành theo một giao thức. API chỉ được tin token khi đã xác định đúng trust anchor, issuer, profile và điều kiện sử dụng. Các trường như sub, role, tenant hoặc scope có thể bị giả mạo nếu token chưa được xác minh.

Không dùng các giá trị do client gửi ngoài token đã xác minh như X-User, X-Role, X-Tenant hoặc X-Authenticated để thay thế kết quả xác thực. Nếu gateway inject header identity, gateway phải xóa header cùng tên do client tự gửi, tự tạo giá trị sau khi xác minh và bảo vệ đường truyền tới backend.

## 2. Phân biệt các loại token

Các token có thể cùng được biểu diễn dưới dạng chuỗi hoặc JWT nhưng có mục đích khác nhau. API phải biết loại token nó mong đợi.

| Loại token | Consumer chính | Mục đích |
| --- | --- | --- |
| **Access token** | Resource server/API. | Cho phép truy cập resource theo audience, scope và policy. |
| **ID Token** | OIDC client/Relying Party. | Truyền assertion về authentication và subject cho client. |
| **Refresh token** | OAuth client với authorization server. | Xin access token mới theo grant; không gửi tới resource API. |
| **Client assertion** | Authorization server/token endpoint. | Xác thực client trong một flow hỗ trợ assertion. |
| **Logout Token** | RP logout endpoint theo OIDC Back-Channel Logout. | Thông báo sự kiện logout; không phải access token API. |
| **Token nội bộ** | Service đã được cấu hình tin cậy. | Trao đổi identity hoặc delegation theo profile riêng. |

### 2.1. Không dùng ID Token làm access token

ID Token được phát hành cho OIDC client và audience thường là client ID. Nó chứng minh kết quả authentication trong OIDC flow. Access token được cấp cho resource server để truy cập API.

Nếu API chấp nhận ID Token như bearer access token, attacker có thể tận dụng token được phát hành cho client khác hoặc mục đích khác. Chữ ký của ID Token vẫn có thể hợp lệ nhưng audience và semantics không phù hợp.

### 2.2. JWT và opaque token

Access token có thể là:

- **JWT/self-contained token:** chứa claims, thường được ký và có thể được API xác minh offline bằng public key.
- **Opaque/reference token:** là chuỗi không tự mô tả claims; API hoặc gateway cần introspection hoặc một cơ chế tra trạng thái đáng tin.

Không phải mọi access token đều là JWT. Client không nên phụ thuộc vào việc decode access token trừ khi provider công bố profile và cho phép điều đó. API chỉ dùng token theo cơ chế đã được cấu hình.

## 3. Xác định trust configuration trước khi nhận token

API cần biết issuer và cách xác minh token từ cấu hình đáng tin cậy. Không lấy issuer hoặc URL JWKS tùy ý từ token chưa xác minh rồi tự động truy cập.

Trust configuration thường gồm:
- Issuer identifier chính xác.
- Authorization server hoặc metadata endpoint được quản trị.
- JWKS URI hoặc trust anchor đã được xác minh.
- Danh sách thuật toán chữ ký cho phép.
- Audience/resource identifier của API.
- Token type/profile được chấp nhận.
- Quy tắc claim, scope, tenant và client.
- Clock tolerance và cache policy.
- Cơ chế introspection, revocation và key rotation.
- Quy trình xử lý issuer/key compromise.

### 3.1. Issuer phải được so khớp chính xác

Claim iss xác định issuer. API phải so khớp với issuer đã cấu hình theo đúng profile, bao gồm scheme, host, path và các thành phần được quy định. Không bỏ qua path, không tự normalize khác với specification và không chấp nhận issuer gần giống.

Ví dụ, hai issuer sau là hai định danh khác nhau:
- https://identity.example/tenant-a
- https://identity.example/tenant-b

Không chọn issuer theo email, domain của request hoặc một query parameter không được bảo vệ. Với multi-issuer, xác định issuer dự kiến theo client/tenant/transaction từ cấu hình tin cậy.

### 3.2. Audience phải khớp resource server

Claim aud chỉ ra token dành cho ai. API phải kiểm tra audience có chứa identifier của chính resource server theo profile được sử dụng.

Ví dụ:
- Token dành cho inventory-api không được orders-api chấp nhận.
- ID Token dành cho web-client không được dùng để gọi payments-api.
- Token của staging không nên được chấp nhận ở production nếu trust policy tách environment.

Nếu token có nhiều audience, API phải áp dụng đúng quy tắc profile và kiểm tra authorized party/client khi cần. Không coi việc issuer tin cậy là đủ.

### 3.3. Tenant là một ranh giới riêng

Một token có tenant claim không tự cấp quyền truy cập mọi resource trong tenant đó. API cần ràng buộc tenant với issuer, client, subject, membership và resource. Không tin tenant ID do body, query hoặc header client tự khai.

Trong multi-tenant API, kiểm tra:
- Token có audience là API hiện tại.
- Subject/client được liên kết với tenant theo mapping đã phê duyệt.
- Membership hoặc service registration còn active.
- Resource thuộc tenant tương ứng.
- Scope/action được phép trong tenant đó.
- Không có cross-tenant reference hoặc IDOR.

## 4. Xác minh chữ ký JWT

Nếu access token là signed JWT (JWS), API phải xác minh chữ ký bằng key tương ứng từ issuer tin cậy trước khi tin payload. Decode header/payload chỉ là đọc dữ liệu; nó không chứng minh token không bị sửa.

### 4.1. Quy trình kiểm tra JWS

Một validator thường thực hiện:
1. Parse JWT bằng thư viện đã được kiểm chứng.
2. Xác định issuer dự kiến từ cấu hình tin cậy.
3. Lấy public key từ JWKS đã gắn với issuer đó.
4. Chọn key phù hợp với kid và loại key.
5. Kiểm tra thuật toán nằm trong allowlist cố định của server.
6. Xác minh chữ ký trên đúng signing input.
7. Sau đó mới đọc và kiểm tra claims.
8. Kiểm tra token type, issuer, audience và thời gian.
9. Kiểm tra claim bắt buộc và policy bổ sung.
10. Chỉ chuyển principal đã xác minh sang authorization layer.

Không lấy key từ URL jku/x5u do token tự cung cấp nếu profile không quy định và không có kiểm soát trust rõ. Không để kid trở thành đường dẫn file, URL hoặc câu truy vấn tùy ý.

### 4.2. Chọn thuật toán an toàn

Server phải cấu hình danh sách thuật toán được phép, phù hợp với issuer và profile. Không tin giá trị alg do token tự chọn. Từ chối thuật toán không được hỗ trợ hoặc không nằm trong allowlist; không chấp nhận alg=none cho access token cần chữ ký.

Tránh các lỗi:
- Algorithm confusion giữa RSA và HMAC.
- Dùng public key như HMAC secret.
- Chấp nhận thuật toán yếu hoặc không được policy cho phép.
- Bỏ qua signature verification khi có lỗi.
- Chọn key sai loại hoặc sai issuer.
- Xác minh một token bằng key lấy từ nguồn attacker kiểm soát.

Thư viện JWT cần được cấu hình rõ issuer, audience, algorithms và required claims. Không chỉ gọi hàm decode hoặc parse rồi coi kết quả là đã xác thực.

### 4.3. JWKS và kid

JWKS chứa public keys của issuer. Header kid giúp chọn key tương ứng nhưng không tự xác thực key. API cần:
- Chỉ lấy JWKS từ endpoint được cấu hình cho issuer.
- Cache key với TTL có giới hạn.
- Xử lý kid chưa biết bằng refresh có rate limit.
- Không fetch JWKS theo URL do token cung cấp.
- Kiểm tra key type, use, alg và key material.
- Có cơ chế overlap key cũ/mới trong rotation.
- Xử lý khẩn cấp khi signing key bị compromise.
- Theo dõi metadata/JWKS thay đổi và lỗi tải key.

Nếu issuer xoay key, token mới có thể dùng kid mới. API nên refresh JWKS có kiểm soát rồi thử xác minh lại một lần; không thực hiện network fetch không giới hạn cho mọi token sai chữ ký vì có thể tạo DoS.

### 4.4. Chữ ký hợp lệ không chứng minh claim đúng

Chữ ký chỉ chứng minh token được ký bởi private key tương ứng với public key đã tin cậy và payload không bị sửa sau khi ký. Issuer có thể phát hành dữ liệu sai, stale hoặc quá rộng. API vẫn cần kiểm tra semantics, freshness và authorization.

## 5. Kiểm tra thời gian và vòng đời token

Token thường có các claim thời gian:
- exp: thời điểm token hết hạn.
- nbf: thời điểm token bắt đầu có hiệu lực.
- iat: thời điểm token được phát hành.

API phải kiểm tra theo đồng hồ server đáng tin cậy và clock tolerance nhỏ được policy quy định.

### 5.1. exp, nbf và iat

- Nếu hiện tại bằng hoặc sau exp, token hết hạn và phải bị từ chối.
- Nếu hiện tại trước nbf, token chưa có hiệu lực.
- iat ở tương lai vượt tolerance hoặc quá cũ so với profile có thể là dấu hiệu token bất thường.
- Token lifetime cần có giới hạn tối đa theo policy; không chấp nhận token tồn tại quá lâu chỉ vì exp chưa qua nếu profile yêu cầu giới hạn khác.

Không lấy thời gian do client gửi để xác định token còn hạn. Lưu audit time bằng UTC; đồng bộ clock giữa API, issuer và gateway.

### 5.2. Clock skew

Một tolerance nhỏ có thể xử lý sai lệch đồng hồ giữa issuer và resource server. Tolerance không nên quá rộng vì nó kéo dài cửa sổ chấp nhận token đã hết hạn hoặc chưa có hiệu lực.

Theo dõi clock drift, dùng nguồn thời gian được quản lý và kiểm thử các biên thời gian. Không bỏ qua exp/nbf khi NTP hoặc clock service gặp lỗi.

### 5.3. jti và replay

jti là identifier của token nếu issuer phát hành claim này. Bản thân jti không tự chống replay. Muốn phát hiện replay, hệ thống phải duy trì trạng thái đã sử dụng hoặc denylist phù hợp với semantics của token.

Với bearer access token thông thường, việc sử dụng lại token trong thời hạn có thể là hành vi dự kiến. Chỉ áp dụng one-time semantics khi profile/giao thức quy định; nếu cần hạn chế replay, cân nhắc sender-constrained token, token ngắn hạn và kiểm soát trạng thái.

## 6. Kiểm tra token type và profile

API cần xác định loại JWT hoặc access token đang nhận. Một JWT có chữ ký hợp lệ có thể là ID Token, client assertion, logout token hoặc token nội bộ khác.

### 6.1. typ và access token profile

Header typ hoặc claim/profile-specific field có thể giúp xác định loại token. Ví dụ, profile JWT Access Token có thể dùng media type application/at+jwt. Cách kiểm tra phải theo profile mà authorization server và API đã thỏa thuận.

Không dựa riêng vào việc token có ba đoạn phân cách bởi dấu chấm. Dùng validator/profile riêng cho:
- Access token.
- ID Token.
- Client assertion.
- Logout Token.
- Token nội bộ hoặc delegation token.

### 6.2. Tránh cross-JWT confusion

Cross-JWT confusion xảy ra khi token được tạo cho một protocol/context lại được chấp nhận trong context khác. Biện pháp:
- Tách audience cho từng consumer.
- Tách token type và required claims.
- Dùng issuer/key trust đúng mục đích.
- Không chia sẻ validator quá tổng quát.
- Kiểm tra profile, typ và claim semantics.
- Không cho một ID Token dùng làm access token hoặc một logout token gọi API.

## 7. Kiểm tra scope, client và claims

Sau khi xác minh mật mã và claims chuẩn, API kiểm tra token có được cấp quyền cần thiết cho endpoint hay không. Scope thường là tập quyền được cấp cho client/resource, không nhất thiết là role đầy đủ của người dùng.

### 7.1. Scope validation

Ví dụ:
- GET /orders/{id} yêu cầu scope orders.read.
- POST /orders yêu cầu scope orders.write.
- GET /admin/audit yêu cầu scope audit.read và policy admin bổ sung.

API phải kiểm tra scope theo contract. Không kiểm tra chuỗi con như scope.contains("read") vì có thể match nhầm giá trị. Parse theo format scope được định nghĩa, so khớp token chính xác và kiểm tra mọi scope bắt buộc.

Scope hợp lệ vẫn chưa đủ để cho phép mọi object. API cần kiểm tra subject có quyền trên order cụ thể, tenant và trạng thái nghiệp vụ.

### 7.2. Client identity và subject

Với client credentials, token thường đại diện client/workload, không phải user cuối. Claims có thể gồm client_id hoặc sub theo profile. API cần phân biệt:
- Machine principal gọi thay mặt chính nó.
- User subject đang đăng nhập.
- Service acting on behalf of a user.
- Actor và delegated subject trong token exchange/on-behalf-of flow.

Không tự suy ra user từ header hoặc tên service. Nếu có delegation, phải xác minh claim/token profile, audience và scope cho đúng service.

### 7.3. Role, group và claim mapping

Role/group có thể là custom claim. Chỉ tin khi issuer và mapping đã được phê duyệt. Cần ràng buộc mapping với issuer, tenant, client và version; không tự coi group tên admin từ bất kỳ issuer nào là quyền quản trị nội bộ.

Nếu role/membership có thể thay đổi nhanh, token có thể chứa claim stale. Với action nhạy cảm, API có thể cần introspection, account/session version, cache invalidation hoặc truy vấn nguồn có thẩm quyền.

## 8. Opaque token và introspection

Opaque token không chứa claims để API tự xác minh. Resource server thường gọi OAuth Token Introspection endpoint theo RFC 7662 hoặc dùng một cơ chế nội bộ tương đương.

### 8.1. Những gì cần kiểm tra từ introspection

Response có thể cung cấp:
- active: token có đang được coi là active không.
- scope: quyền được cấp.
- client_id: client được gắn với token.
- sub: subject nếu token đại diện một user.
- aud: resource/audience.
- iss: issuer nếu profile cung cấp.
- exp, iat, nbf: thời gian.
- token_type và các metadata khác theo server.

API phải xác minh response đến từ introspection endpoint tin cậy qua kênh xác thực, không để client tự gửi một JSON active=true.

### 8.2. Bảo vệ introspection endpoint

Resource server phải xác thực với authorization server theo cơ chế được hỗ trợ, giới hạn network access và bảo vệ credential của resource server. Không công khai endpoint introspection để bất kỳ ai cũng có thể hỏi token có active hay không.

Không gửi token tới endpoint không rõ nguồn. Tránh log token trong request body hoặc query string.

### 8.3. Cache introspection response

Cache active response giúp giảm latency và tải, nhưng làm chậm việc nhận biết revoke. TTL phải phù hợp với rủi ro và lifetime token. Với token bị revoke khẩn cấp, cache cũ có thể tiếp tục cho phép truy cập tới khi hết TTL.

Có thể dùng:
- TTL ngắn hơn cho action nhạy cảm.
- Invalidation event khi token/session bị revoke.
- Không cache response lỗi hoặc malformed như active.
- Cache key bằng keyed token fingerprint/reference thay vì lưu raw token.
- Giới hạn kích thước và số entry.

Nếu introspection timeout, API không được tự suy ra token active. Fallback phải được định nghĩa theo độ nhạy tài nguyên; hard checks như issuer/audience/token validity vẫn phải giữ.

## 9. Revocation và trạng thái token

Token có thể bị thu hồi trước khi hết hạn do logout, account disable, grant revoke, credential compromise hoặc thay đổi policy.

### 9.1. JWT offline validation có giới hạn thu hồi

JWT được xác minh offline không cần gọi issuer mỗi request. Điều này tăng availability và giảm latency, nhưng resource server có thể không biết token vừa bị revoke.

Các cách giảm cửa sổ:
- Access token lifetime ngắn.
- Introspection hoặc state lookup.
- Denylist theo jti/token reference tới expiry.
- Account/session version hoặc authorization epoch.
- Event-driven invalidation.
- Sender-constrained token để giảm nguy cơ token bị đánh cắp có thể dùng ở nơi khác.

Không dùng denylist lưu raw bearer token. Nếu cần reference, dùng jti do issuer cấp hoặc keyed fingerprint có quản lý key.

### 9.2. Logout và token revocation

OAuth token revocation endpoint có thể thu hồi token theo semantics của authorization server. Tuy nhiên, JWT access token đã được resource server xác minh offline có thể tiếp tục được chấp nhận tới exp nếu không có state check hoặc cơ chế thu hồi khác.

API và issuer cần thống nhất:
- Token nào được revoke.
- Token family/grant nào bị ảnh hưởng.
- Khi nào resource server nhận trạng thái mới.
- Cache TTL và propagation delay.
- Hành vi khi revocation service không khả dụng.

### 9.3. Account hoặc role thay đổi

Nếu account bị disable hoặc user bị gỡ role, token cũ có thể vẫn chứa claim trước đó. Với dữ liệu nhạy cảm hoặc quyền đặc quyền, kiểm tra account/session version hoặc entitlement hiện tại gần thời điểm thực thi.

Không phải mọi API cần truy vấn database ở mọi request. Chọn consistency model theo hậu quả nếu quyền cũ tiếp tục tồn tại.

## 10. Sender-constrained token: mTLS và DPoP

Bearer token có thể được sử dụng bởi bất kỳ bên nào sở hữu token. Nếu token bị sao chép, attacker có thể replay trong thời hạn. Sender-constrained token ràng buộc token với key/certificate mà client phải chứng minh đang kiểm soát.

### 10.1. Mutual TLS-bound access token

Với OAuth mTLS, access token có thể được ràng buộc với client certificate. Resource server cần:
- Xác minh TLS client certificate theo trust policy.
- Xác minh token và audience như bình thường.
- Kiểm tra confirmation claim hoặc binding theo profile, ví dụ fingerprint certificate.
- Bảo đảm certificate trong TLS connection khớp certificate được token ràng buộc.
- Xử lý proxy termination và certificate forwarding qua kênh tin cậy.
- Revoke hoặc rotate certificate/token khi key compromise.

Nếu TLS kết thúc tại gateway, backend chỉ tin metadata certificate do gateway xác minh và inject qua kênh được bảo vệ; không tin header do client ngoài gửi.

### 10.2. DPoP

Demonstrating Proof of Possession (DPoP) ràng buộc access token với public key của client thông qua proof JWT cho từng request. API cần kiểm tra proof theo profile:
- Chữ ký proof bằng public key được chỉ ra theo cơ chế DPoP.
- HTTP method và target URI khớp request.
- Thời điểm iat nằm trong cửa sổ cho phép.
- jti chưa được dùng trong replay window.
- ath ràng buộc proof với access token khi yêu cầu.
- Nonce của server nếu policy/profile yêu cầu.
- Confirmation claim của access token khớp key thumbprint.

DPoP proof không thay thế việc xác minh access token. API vẫn phải kiểm tra issuer, audience, expiry, scope và authorization. Cần lưu jti/replay state đủ thời gian để ngăn proof bị dùng lại.

### 10.3. Sender constraint không giải quyết mọi rủi ro

Nếu attacker kiểm soát endpoint hoặc private key của client, họ vẫn có thể tạo proof hợp lệ. Sender constraint giảm giá trị của token bị đánh cắp riêng lẻ, nhưng không thay thế bảo vệ key, endpoint security, short lifetime, revocation và monitoring.

## 11. Kiến trúc middleware token validation

Token validation nên được thực hiện ở một middleware hoặc security component dùng chung, được cấu hình rõ cho từng API. Tuy nhiên, dùng chung code không có nghĩa dùng chung một audience hoặc policy cho mọi service.

Luồng khái quát:

    HTTP request
        |
        v
    Extract Authorization: Bearer token
        |
        v
    Parse safely and enforce size/format limits
        |
        v
    Select preconfigured issuer/profile
        |
        v
    Verify signature or introspect opaque token
        |
        v
    Validate issuer, audience, type and time
        |
        v
    Validate sender constraint if required
        |
        v
    Build verified principal/context
        |
        v
    Endpoint scope and authorization checks
        |
        v
    Object/tenant/business policy
        |
        v
    Execute request

### 11.1. Pseudocode validation

    validateAccessToken(request, apiPolicy):
        token = extractBearerToken(request)
        require token exists
        require token.size <= apiPolicy.maxTokenSize

        profile = apiPolicy.expectedTokenProfile
        issuerConfig = apiPolicy.trustedIssuer
        require issuerConfig is configured

        if profile.usesJwt:
            parsed = jwtLibrary.parse(token)
            require parsed.header.alg in issuerConfig.allowedAlgorithms
            require parsed.header.kid is validKeyIdentifier
            key = jwksCache.getKey(issuerConfig.jwksUri, parsed.header.kid)
            require key is trustedFor(issuerConfig.issuer)
            claims = jwtLibrary.verifyAndDecode(token, key, allowedAlgorithms)
        else:
            claims = introspectionClient.introspect(token)
            require claims.active == true

        require claims.iss == issuerConfig.issuer
        require apiPolicy.audience in claims.aud
        require claims.exp is validAndNotExpired
        require claims.nbf is absentOrAlreadyEffective
        require tokenTypeMatches(profile, parsed, claims)
        require requiredClaimsPresent(profile, claims)

        if apiPolicy.senderConstraintRequired:
            verifyBoundKeyOrCertificate(request, token, claims)

        principal = mapVerifiedPrincipal(claims, issuerConfig.mapping)
        return principal

    authorizeRequest(principal, request, endpointPolicy):
        require principal has requiredScope(endpointPolicy)
        require principal tenant matches resource tenant
        require policyAllows(principal, request.action, request.resource)
        return allow

Pseudocode minh họa, không phải implementation copy-paste. Thư viện cụ thể phải tự bảo đảm cách parse, signature verification, key selection và claim validation đúng profile. Với JWT, không đọc claims để ra quyết định trước khi chữ ký được xác minh. Với opaque token, không chấp nhận introspection response chưa được xác thực.

### 11.2. Ràng buộc cấu hình theo API

Mỗi API nên khai báo:
- Issuer được tin cậy.
- Audience/resource identifier.
- Token profile/type.
- Allowed signing algorithms hoặc introspection endpoint.
- Scope tối thiểu theo endpoint.
- Sender constraint có bắt buộc không.
- Clock tolerance và token size limit.
- Revocation/cache policy.
- Claim mapping và tenant rules.

Không để một middleware toàn hệ thống chấp nhận mọi issuer, mọi audience và mọi token type chỉ để giảm cấu hình.

## 12. Trích xuất token an toàn từ HTTP request

OAuth Bearer Token Usage thường truyền access token trong Authorization header:

    Authorization: Bearer ACCESS_TOKEN_VALUE

API cần:
- Chỉ chấp nhận phương thức truyền được profile cho phép.
- Không chấp nhận token qua query string nếu không có lý do giao thức rất cụ thể.
- Từ chối nhiều Authorization header hoặc cú pháp mơ hồ.
- Giới hạn kích thước header/token.
- Không ghi header vào access log.
- Bảo đảm reverse proxy không làm mất hoặc ghép sai header.
- Dùng TLS để bảo vệ token trên đường truyền.
- Không chuyển tiếp token tới service không nằm trong audience/trust path.

Query string có thể xuất hiện trong browser history, proxy log, analytics và Referer. Vì vậy không đặt bearer token trong URL.

### 12.1. WWW-Authenticate và lỗi API

Khi token thiếu hoặc không hợp lệ, API thường trả 401 và challenge phù hợp, ví dụ Bearer với error invalid_token. Khi token hợp lệ nhưng scope không đủ, API thường trả 403 và có thể báo insufficient_scope theo profile.

Không trả chi tiết như key ID nội bộ, issuer secret, stack trace hoặc quy tắc risk engine cho client không tin cậy. Audit nội bộ có thể giữ reason code chi tiết.

Phân biệt:
- **401 Unauthorized:** request chưa có credential hợp lệ cho API.
- **403 Forbidden:** principal đã được xác định nhưng không được phép thực hiện action.
- **400 Bad Request:** cú pháp/header request không hợp lệ theo contract.
- **503 Service Unavailable:** dependency bắt buộc như introspection không khả dụng và policy chọn từ chối an toàn.

Không dùng 401/403 thay thế tùy tiện; semantics nhất quán giúp client xử lý refresh và người vận hành điều tra.

## 13. Caching, performance và availability

Token validation ảnh hưởng mọi request được bảo vệ. Caching có thể giảm latency nhưng phải giữ đúng ranh giới tin cậy.

### 13.1. Cache JWKS

JWKS cache lưu public keys của issuer, không phải kết quả xác thực token. Cần TTL, refresh và key rotation strategy. Khi kid chưa biết, refresh có kiểm soát; không để attacker tạo hàng triệu kid giả khiến API gọi JWKS liên tục.

### 13.2. Cache validation result

Có thể cache kết quả validation trong một khoảng ngắn theo token fingerprint, issuer, audience, profile và policy version. Nhưng cache phải:
- Không dùng raw bearer token làm cache key nếu không cần.
- Không vượt quá exp hoặc thời điểm revoke policy yêu cầu.
- Invalidate khi key, issuer, account hoặc policy bị thu hồi.
- Tách cache giữa audience và tenant.
- Không cache failure dependency như kết quả active.
- Giới hạn memory và chịu được cache stampede.

Cache validation result không thể biết role/membership thay đổi ngay nếu không có invalidation hoặc state check.

### 13.3. Khi dependency lỗi

Nếu JWKS endpoint hoặc introspection endpoint lỗi:
- Không tự chấp nhận token chưa xác minh.
- Có thể dùng key cache còn trong TTL nếu policy cho phép và key chưa bị revoke.
- Với opaque token, nếu không thể xác nhận active, thường phải từ chối hoặc dùng fallback được phê duyệt.
- Không bỏ qua expiry, audience hoặc signature.
- Ghi metric/alert và reason code cho dependency outage.
- Có circuit breaker, timeout và bounded retry.

Fail-open có thể biến outage thành bypass authentication. Nếu có fallback, nó phải giới hạn resource/action và được threat model phê duyệt.

## 14. Threat model cho token validation

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Signature bypass** | Decode token nhưng không verify chữ ký. | Attacker tự sửa sub, scope hoặc role. | Dùng thư viện chuẩn và bắt buộc verify trước khi đọc claim. |
| **Algorithm confusion** | Tin alg do token chọn hoặc nhầm RSA/HMAC. | Chấp nhận chữ ký giả. | Algorithm allowlist cố định, key type validation. |
| **Issuer confusion** | Chấp nhận token từ issuer tùy ý hoặc issuer gần giống. | Trust một nguồn giả. | Issuer exact match từ cấu hình tin cậy. |
| **Audience confusion** | Token dành cho API/client khác được chấp nhận. | Token bị dùng chéo service. | Audience/resource validation và token profile riêng. |
| **ID Token substitution** | Dùng ID Token làm bearer access token. | Bypass semantics và audience. | Phân biệt token type, audience và validator. |
| **Expired/not-yet-valid token** | Bỏ qua exp/nbf hoặc clock sai. | Credential được chấp nhận ngoài thời hạn. | Trusted clock, boundary checks và tolerance nhỏ. |
| **JWKS injection/DoS** | Tin jku/x5u/kid hoặc fetch key không giới hạn. | Lấy key từ attacker hoặc làm cạn tài nguyên. | JWKS URI cấu hình sẵn, kid validation, rate limit. |
| **Stale authorization claim** | Role/membership bị thu hồi nhưng token cũ còn hạn. | Quyền cũ tiếp tục hoạt động. | Short lifetime, introspection, version hoặc invalidation. |
| **Bearer token replay** | Token bị sao chép và dùng từ client khác. | Truy cập trái phép trong thời hạn. | Sender constraint, bảo vệ token, revoke và monitoring. |
| **DPoP proof replay** | Proof JWT bị dùng lại trong replay window. | Request giả được chấp nhận. | jti store, iat window, ath, nonce và key binding. |
| **Opaque token cache stale** | Cache active còn tồn tại sau revoke. | Token bị thu hồi vẫn được chấp nhận. | TTL ngắn, event invalidation và policy theo action. |
| **Cross-tenant access** | Tin tenant claim hoặc resource ID do client gửi. | Truy cập dữ liệu tenant khác. | Tenant mapping và object-level authorization. |
| **Token leakage** | Token xuất hiện trong URL, log hoặc telemetry. | Bearer credential bị lộ. | Authorization header, TLS, redaction và secret-safe logging. |

## 15. Kiểm thử token validation

Kiểm thử cần bao gồm token hợp lệ, token lỗi, ranh giới thời gian, key rotation, issuer outage và các tình huống authorization. Không chỉ test một JWT có chữ ký đúng.

| Test case | Kết quả mong đợi |
| --- | --- |
| JWT có signature hợp lệ, issuer/audience đúng và chưa hết hạn | Token qua validation; authorization được đánh giá tiếp. |
| Sửa payload nhưng giữ signature cũ | Từ chối vì signature invalid. |
| alg không nằm trong allowlist hoặc alg=none | Từ chối. |
| kid không tồn tại | Refresh JWKS có giới hạn; từ chối nếu vẫn không tìm thấy key. |
| Issuer gần giống nhưng không exact match | Từ chối. |
| Audience là API khác | Từ chối. |
| ID Token gửi tới resource API | Từ chối vì sai token profile/audience. |
| exp đã qua hoặc nbf ở tương lai | Từ chối theo clock tolerance. |
| Token có scope thiếu | Validation có thể thành công; endpoint authorization trả insufficient_scope/403. |
| Opaque token introspection active=false | Từ chối. |
| Introspection timeout | Áp dụng fallback đã định nghĩa; không tự coi active. |
| JWT role đã stale sau khi user bị gỡ quyền | State check/invalidation chặn action nhạy cảm theo policy. |
| mTLS-bound token dùng với certificate khác | Từ chối proof/binding. |
| DPoP proof dùng lại jti | Từ chối replay. |
| Token của staging gửi tới production API | Từ chối theo issuer/audience/environment policy. |
| Token thiếu hoặc quá lớn trong Authorization header | Từ chối an toàn, không log token. |

### 15.1. Kiểm thử thư viện và cấu hình

- Dùng bộ test theo JWT/OAuth/OIDC profile.
- Kiểm tra parser với token malformed, header duplicate và claim type sai.
- Kiểm tra Unicode/URL và issuer string theo profile.
- Kiểm tra key rotation có overlap và key bị compromise.
- Kiểm tra cache invalidation và dependency outage.
- Kiểm tra log không chứa token hoặc Authorization header.
- Kiểm tra endpoint không chấp nhận token qua query string.
- Kiểm tra gateway/backend không tin identity header giả.

## 16. Tình huống thực hành: access token hợp lệ nhưng sai audience

**Bối cảnh:** Một client backend lấy access token từ authorization server để gọi inventory-api. Do cấu hình nhầm, client gửi cùng token đó tới payments-api. JWT có chữ ký hợp lệ, issuer đúng và exp còn 10 phút. Token có scope inventory.read.

**Phân tích:**

1. Chữ ký hợp lệ chứng minh token được issuer tin cậy ký.
2. Issuer đúng xác nhận nguồn phát hành.
3. Nhưng audience là inventory-api, không phải payments-api.
4. Scope inventory.read không cấp quyền gọi payments API.
5. Nếu payments-api chỉ kiểm chữ ký và exp, nó có thể chấp nhận token ngoài mục đích được cấp.

**Phản ứng đúng:**

- payments-api kiểm tra audience/resource identifier của chính nó và từ chối token.
- Client yêu cầu access token mới với resource/audience và scope phù hợp.
- API ghi audit reason code AUDIENCE_MISMATCH, không ghi token thô.
- Rà soát gateway và shared middleware để bảo đảm mỗi API có audience config riêng.
- Thêm negative test ngăn token của inventory-api được dùng tại payments-api.

**Câu hỏi:** Nếu token có scope payments.write nhưng audience vẫn là inventory-api thì payments-api có nên chấp nhận không? Không. Scope không thay thế audience; token phải được phát hành cho resource server đang nhận request.

## 17. Checklist triển khai token validation

- [ ] Xác định API là resource server và chỉ chấp nhận loại access token đã thỏa thuận.
- [ ] Phân biệt access token, ID Token, refresh token, client assertion và logout token.
- [ ] Cấu hình issuer và JWKS/introspection endpoint từ nguồn tin cậy.
- [ ] Xác minh chữ ký trước khi tin JWT claims; không chỉ decode token.
- [ ] Dùng algorithm allowlist cố định và kiểm tra key type/use.
- [ ] Không chấp nhận alg=none hoặc algorithm confusion.
- [ ] Không lấy JWKS từ URL tùy ý trong token; giới hạn refresh theo kid chưa biết.
- [ ] So khớp issuer chính xác và kiểm tra audience/resource của API.
- [ ] Kiểm tra exp, nbf, iat, clock skew và maximum lifetime.
- [ ] Kiểm tra token type/profile và required claims.
- [ ] Parse scope chính xác; không dùng substring match.
- [ ] Phân biệt client principal, user subject và delegated identity.
- [ ] Ràng buộc tenant, membership và resource ownership.
- [ ] Kiểm tra revocation/stale claim theo mức nhạy cảm.
- [ ] Nếu dùng opaque token, xác thực introspection response và cache theo TTL phù hợp.
- [ ] Nếu dùng mTLS/DPoP, kiểm tra proof và key/certificate binding.
- [ ] Chỉ nhận bearer token qua Authorization header theo profile; tránh query string.
- [ ] Không log raw token, Authorization header hoặc secret.
- [ ] Trả 401/403 và WWW-Authenticate nhất quán, không tiết lộ cấu hình nội bộ.
- [ ] Có timeout, rate limit, cache, circuit breaker và fallback được phê duyệt.
- [ ] Kiểm thử issuer/audience/type confusion, signature bypass, expiry, replay, revocation và cross-tenant.

## 18. Câu hỏi tự kiểm tra

**1. Token validation là gì?**  
Là kiểm tra nguồn phát hành, tính toàn vẹn, audience, thời hạn, loại token và điều kiện liên quan trước khi API dùng token làm bằng chứng cho request.

**2. Decode JWT có đồng nghĩa xác minh JWT không?**  
Không. Decode chỉ đọc header/payload; phải xác minh chữ ký bằng key từ issuer tin cậy và kiểm tra claims theo profile.

**3. Vì sao API phải kiểm tra audience?**  
Để bảo đảm token được phát hành cho đúng resource server. Token hợp lệ ở API A không tự có quyền ở API B.

**4. ID Token có thể dùng làm access token không?**  
Không. ID Token dành cho OIDC client; access token dành cho resource server/API. Cần validator và audience riêng.

**5. Chữ ký hợp lệ có đủ để cho phép request không?**  
Không. Còn phải kiểm tra issuer, audience, expiry, token type, scope, sender constraint và authorization trên resource/action.

**6. Opaque token được kiểm tra như thế nào?**  
Thường qua introspection endpoint tin cậy hoặc cơ chế state lookup đã thỏa thuận; không thể tự xác minh claims bằng cách decode.

**7. Vì sao JWT offline validation khó revoke tức thì?**  
Resource server có thể xác minh token mà không hỏi issuer, nên không biết trạng thái revoke mới nếu không có denylist, introspection, version hoặc event invalidation.

**8. Scope có thay thế object-level authorization không?**  
Không. Scope là quyền được cấp ở mức API/resource; API vẫn phải kiểm tra subject có quyền trên object và tenant cụ thể.

**9. DPoP hoặc mTLS-bound token giúp gì?**  
Chúng ràng buộc token với key/certificate mà client phải chứng minh kiểm soát, giảm khả năng dùng token bị đánh cắp riêng lẻ. API vẫn phải validate token và authorization.

**10. Nếu introspection hoặc JWKS endpoint lỗi thì sao?**  
Áp dụng fallback đã định nghĩa; không tự chấp nhận token chưa xác minh, không bỏ qua issuer/audience/expiry và phải ghi nhận sự cố dependency.

**Ghi nhớ:** Token validation là ranh giới tin cậy của API. Hãy xác minh token theo đúng issuer, key, audience, thời hạn và profile; phân biệt access token với các token khác; kiểm tra scope và sender constraint; xử lý revocation/caching có chủ đích; rồi authorization riêng trên tenant, action và resource. Một chữ ký hợp lệ chỉ là một phần của quyết định chấp nhận request.
