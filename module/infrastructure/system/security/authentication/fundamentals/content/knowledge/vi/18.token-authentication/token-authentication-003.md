# Access token

> **Chương:** Token authentication  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Hiểu access token là credential được cấp để truy cập resource server trong một phạm vi cụ thể; biết cách phát hành, truyền, kiểm chứng, giới hạn, lưu trữ và thu hồi token mà không nhầm nó với mật khẩu, phiên đăng nhập, refresh token hay ID token.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích access token dùng để làm gì trong mô hình client, authorization server và resource server.
2. Phân biệt access token với ID token, refresh token, session cookie, API key và credential xác thực ban đầu.
3. So sánh token opaque và token tự chứa (self-contained), đặc biệt là JWT.
4. Phân biệt bearer token với sender-constrained token và giải thích rủi ro replay khi token bị lộ.
5. Đọc các thuộc tính quan trọng như issuer, audience, scope, subject, thời hạn và client identity mà không suy diễn quyền vượt quá ngữ nghĩa của chúng.
6. Mô tả quy trình cấp token và xác minh tại resource server, gồm chữ ký, issuer, audience, expiry, scope và trạng thái.
7. Thiết kế cách truyền, lưu trữ, xoay vòng và thu hồi token phù hợp với web, mobile và service-to-service.
8. Nhận diện các lỗi thường gặp: token leakage, token substitution, algorithm confusion, audience mismatch, scope overreach, refresh-token misuse và thiếu kiểm soát quyền trên tài nguyên.

## 1. Access token là gì?

**Access token** là một credential được authorization server cấp cho client để client trình lên **resource server** khi yêu cầu truy cập tài nguyên được bảo vệ. Token cho biết request có thể được chấp nhận trong phạm vi quyền, đối tượng nhận, thời hạn và điều kiện mà hệ thống đã cấp.

Trong OAuth 2.0, access token là đại diện cho **authorization**. Nó có thể biểu diễn quyền của một người dùng đã ủy quyền cho client, hoặc quyền của chính một ứng dụng/dịch vụ trong một luồng machine-to-machine. Vì vậy, không phải access token nào cũng có nghĩa “một con người đã đăng nhập”.

Ví dụ: người dùng cấp cho ứng dụng lịch quyền đọc sự kiện. Ứng dụng nhận access token dành cho Calendar API với scope đọc lịch. Khi gọi API, resource server kiểm tra token và quyết định request có thuộc quyền được cấp hay không.

Một access token thường được gửi trong HTTP header:

~~~http
GET /v1/calendar/events HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Từ **Bearer** có nghĩa là bên nắm giữ token có thể trình token để sử dụng quyền tương ứng, nếu resource server chấp nhận nó. Vì vậy token phải được bảo vệ như một bí mật có thể trao quyền truy cập.

### Access token trả lời câu hỏi nào?

- Token được phát hành bởi authorization server nào?
- Token dành cho resource server/API nào?
- Token đại diện cho client nào và, nếu có, chủ thể nào?
- Quyền hoặc scope nào đã được cấp?
- Token còn trong thời hạn và trạng thái hợp lệ không?
- Có điều kiện ràng buộc nào với client, thiết bị hoặc khóa trình token không?

Access token **không tự trả lời mọi câu hỏi phân quyền nghiệp vụ**. Ví dụ, scope courses:read có thể cho phép đọc một loại tài nguyên, nhưng API vẫn cần kiểm tra người dùng có quyền xem khóa học cụ thể hay không.

## 2. Các thành phần trong mô hình access token

Một mô hình phổ biến có ba vai trò:

| Thành phần | Trách nhiệm | Điều cần tin cậy |
| --- | --- | --- |
| **Client** | Ứng dụng thay mặt người dùng hoặc chính workload yêu cầu token và gửi token tới API. | Client không được tự tuyên bố đã có quyền; phải bảo vệ token và dùng đúng resource. |
| **Authorization Server (AS)** | Xác thực/ủy quyền theo luồng phù hợp, áp chính sách và phát hành token. | Chỉ phát token sau khi kiểm tra client, chủ thể, grant, scope và các điều kiện liên quan. |
| **Resource Server (RS)** | API nhận token, xác minh token và thực thi quyền trên tài nguyên. | Không tin token chưa xác minh; không coi token hợp lệ là quyền truy cập mọi đối tượng. |

Một hệ thống có thể tách authorization server khỏi identity provider, hoặc một nhà cung cấp đảm nhiệm cả hai vai trò. Tuy nhiên, **xác thực danh tính** và **cấp quyền truy cập API** vẫn là hai mục đích cần phân biệt.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Yêu cầu một chức năng
    C->>AS: Yêu cầu access token theo grant phù hợp
    AS->>AS: Kiểm tra client, grant, subject và policy
    AS-->>C: Access token và metadata liên quan
    C->>RS: API request + Authorization: Bearer
    RS->>RS: Xác minh token và chính sách
    RS->>RS: Kiểm tra quyền trên resource/action
    RS-->>C: Dữ liệu được phép hoặc từ chối
~~~

Sơ đồ chỉ thể hiện luồng khái niệm. Trong Authorization Code Flow, browser thường được chuyển hướng tới authorization server; trong Client Credentials, workload xác thực trực tiếp với authorization server. Resource server không nên nhận mật khẩu người dùng để tự đổi thành token.

## 3. Access token khác ID token, refresh token và session

Các token có thể cùng được trả về trong một token response nhưng phục vụ những mục đích khác nhau.

| Loại | Mục đích chính | Ai thường sử dụng? | Có dùng để gọi API được bảo vệ không? |
| --- | --- | --- | --- |
| **Access token** | Mang quyền truy cập tới resource server cụ thể. | Client trình cho API. | Có, nếu token dành cho API đó và còn hợp lệ. |
| **ID token (OIDC)** | Truyền kết quả xác thực và thông tin subject tới client OIDC. | Client/Relying Party. | Không mặc nhiên; không dùng thay access token. |
| **Refresh token** | Xin access token mới theo grant và chính sách đã cấp. | Client gửi tới authorization server. | Không; không gửi tới resource API như bearer access token. |
| **Session cookie** | Duy trì phiên ứng dụng giữa browser và ứng dụng. | Browser trình cho ứng dụng của phiên đó. | Có thể được ứng dụng dùng nội bộ, nhưng không tự động là OAuth access token. |
| **API key** | Nhận diện client/workload hoặc tích hợp theo thiết kế của API. | Client gửi cho API/gateway. | Có thể, theo API contract; ngữ nghĩa và vòng đời khác OAuth token. |

### 3.1 Access token không phải ID token

OpenID Connect (OIDC) bổ sung lớp xác thực danh tính trên OAuth 2.0. **ID token** được phát hành cho OIDC client để truyền thông tin về lần xác thực. **Access token** được cấp để truy cập resource server.

Ví dụ, ID token có audience là client learning-app, trong khi access token có audience là learning-api. Gửi ID token tới learning-api có thể bị từ chối vì sai audience và sai mục đích.

Không được kết luận rằng token nào có claim subject cũng là bằng chứng phù hợp cho mọi API. Resource server phải biết loại token nào được chấp nhận và kiểm tra đúng issuer, audience, chữ ký cùng chính sách.

### 3.2 Access token không phải refresh token

Access token thường có thời hạn tương đối ngắn để giới hạn cửa sổ sử dụng nếu bị lộ. Refresh token có giá trị lâu hơn và chỉ nên được trình tới authorization server để lấy access token mới.

Nếu refresh token bị đánh cắp, attacker có thể duy trì khả năng xin token mới. Do đó cần bảo vệ refresh token, quản lý rotation/reuse detection hoặc sender constraint theo kiến trúc, giới hạn quyền và có cơ chế thu hồi.

### 3.3 Access token không phải session cookie

Một ứng dụng web có thể dùng session cookie riêng cho browser và chỉ dùng access token ở backend khi gọi API. Cookie được kiểm tra theo trạng thái phiên ứng dụng; access token được kiểm tra theo chính sách resource server. Không nên gộp hai khái niệm chỉ vì cả hai đều được gửi cùng request.

## 4. Hai dạng access token phổ biến: opaque và self-contained

Access token không bắt buộc phải có định dạng JWT. OAuth 2.0 không buộc mọi access token phải là JWT; định dạng phụ thuộc authorization server và profile triển khai.

| Đặc điểm | Opaque token | Self-contained token (ví dụ JWT) |
| --- | --- | --- |
| Nội dung | Chuỗi không mang claim có thể đọc trực tiếp. | Chứa claim được đóng gói theo định dạng token. |
| Xác minh | Resource server tra cứu hoặc gọi introspection tới authorization server. | Resource server kiểm tra chữ ký và claim theo cấu hình tin cậy. |
| Trạng thái | Thường dễ phản ánh trạng thái thu hồi trung tâm hơn. | Có thể xác minh cục bộ nhưng trạng thái thu hồi tức thì khó hơn nếu không có cơ chế bổ sung. |
| Kích thước | Thường ngắn hơn, không mang nhiều claim. | Có thể lớn do header, payload và chữ ký. |
| Riêng tư | Nội dung không tự giải mã từ chuỗi token, nhưng vẫn là bí mật bearer. | Payload JWT thường chỉ Base64URL-encode, không được mã hóa; người nắm token có thể đọc claim. |
| Phụ thuộc | Cần kết nối tới nơi tra cứu/introspection hoặc cache trạng thái. | Cần khóa xác minh và chính sách chấp nhận nhất quán. |

### Opaque token

Opaque token có thể là chuỗi ngẫu nhiên đủ entropy. Resource server không diễn giải nội dung mà xác minh bằng introspection hoặc cơ chế tra cứu được thiết kế:

~~~text
Client -> Resource Server: Bearer opaque-token
Resource Server -> Authorization Server: Introspect token
Authorization Server -> Resource Server:
    active, client_id, subject, scope, audience, expiry
Resource Server:
    verify response and apply resource policy
~~~

Introspection response phải được bảo vệ và chỉ resource server được phép truy vấn. Cache kết quả cần có TTL phù hợp: cache quá lâu có thể tiếp tục chấp nhận token vừa bị thu hồi.

### Self-contained token

JWT (JSON Web Token) là định dạng phổ biến cho token tự chứa. Một JWT dạng ký (JWS compact serialization) thường có cấu trúc:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Header và payload được Base64URL-encode, không mặc nhiên được mã hóa. Chữ ký giúp phát hiện sửa đổi và xác minh nguồn phát hành nếu thuật toán/khóa được cấu hình đúng. Không đặt mật khẩu, secret, dữ liệu sinh trắc hoặc thông tin nhạy cảm không cần thiết vào payload.

JWT có thể tiện cho resource server xác minh cục bộ mà không gọi introspection mỗi request. Đổi lại, token có thể tiếp tục được chấp nhận đến khi hết hạn nếu server không kiểm tra trạng thái hoặc có cơ chế thu hồi bổ sung.

**Opaque và JWT đều có thể là access token.** Không thể kết luận token an toàn chỉ vì nó là JWT hoặc chỉ vì payload đã được ký.

## 5. Đọc cấu trúc JWT và các claim quan trọng

Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "learning-api",
  "client_id": "learning-web",
  "scope": "courses:read profile:read",
  "iat": 1795334400,
  "exp": 1795335300,
  "jti": "token-instance-unique-id"
}
~~~

Các giá trị trên chỉ để giải thích. Đây không phải token đã ký và không được dùng trong môi trường thực.

| Claim | Ý nghĩa phổ biến | Cách kiểm tra |
| --- | --- | --- |
| **iss** | Issuer, nhà phát hành token. | Phải khớp chính xác issuer được cấu hình tin cậy. |
| **sub** | Subject, chủ thể mà token nói tới. | Diễn giải theo issuer và loại grant; có thể là người dùng hoặc một chủ thể khác. |
| **aud** | Audience, đối tượng nhận token. | Resource server phải thấy chính mình trong audience theo chính sách. |
| **client_id** | Client đã yêu cầu hoặc được gắn với token theo profile. | Dùng cho chính sách client; không thay thế subject hoặc quyền. |
| **scope** | Quyền/phạm vi đã cấp. | Chỉ chấp nhận scope cần thiết cho endpoint/action. |
| **iat** | Thời điểm phát hành. | Dùng để kiểm tra thời gian và audit; không chứng minh người dùng vừa xác thực lại. |
| **exp** | Thời điểm hết hạn. | Từ chối sau thời điểm hết hạn, có thể áp clock skew nhỏ theo policy. |
| **nbf** | Không có hiệu lực trước thời điểm này, nếu có. | Không chấp nhận trước thời điểm được phép. |
| **jti** | Mã định danh token, nếu có. | Có thể hỗ trợ audit/denylist hoặc phát hiện trùng; tự nó không ngăn replay. |

Không phải mọi access token đều có đủ các claim trên. Ý nghĩa của claim phụ thuộc token profile, issuer và giao thức. Resource server phải có hợp đồng rõ về claim nào bắt buộc và cách diễn giải.

### Không tin nội dung JWT chỉ vì decode được

Một người có thể sửa payload Base64URL rồi tạo lại chuỗi JWT. Nếu resource server chỉ decode và đọc scope=admin mà không kiểm tra chữ ký, attacker có thể tự gán quyền.

**Quy trình đúng:** xác minh chữ ký bằng khóa được tin cậy, kiểm tra thuật toán được cho phép, issuer, audience, thời hạn và các claim bắt buộc; sau đó mới sử dụng claim để áp chính sách.

## 6. Bearer token và sender-constrained token

### 6.1 Bearer token

Với bearer token, người nắm token có thể trình nó để sử dụng quyền. Resource server không nhất thiết biết người gửi có phải client ban đầu hay không.

Rủi ro:

- Token bị lộ trong log, URL, browser storage, crash report hoặc proxy.
- Token bị lấy từ malware/XSS hoặc thiết bị dùng chung.
- Token được phát lại từ một máy khác trong thời gian còn hiệu lực.
- Client gửi token tới nhầm domain hoặc endpoint do redirect không an toàn.

Do đó bearer token cần truyền qua TLS, lưu trữ an toàn, thời hạn phù hợp, audience/scope giới hạn và kiểm soát rò rỉ.

### 6.2 Sender-constrained token

Sender-constrained token được ràng buộc với một khóa hoặc phương thức chứng minh quyền kiểm soát của client. Khi token bị sao chép, attacker không thể sử dụng dễ dàng nếu không có khóa tương ứng.

Một số cơ chế:

- **mTLS-bound access token:** token được ràng buộc với chứng chỉ client; resource server kiểm tra token và chứng chỉ trong kết nối.
- **DPoP (Demonstrating Proof of Possession):** client tạo proof có chữ ký bằng khóa riêng, gắn với HTTP method, URI và các thuộc tính theo giao thức; resource server kiểm tra proof và token binding.

Các cơ chế này giảm rủi ro replay token bị đánh cắp, nhưng không làm mọi nguy cơ biến mất. Nếu attacker kiểm soát chính thiết bị/client hoặc lấy được cả khóa riêng, họ vẫn có thể sử dụng credential. Cần bảo vệ khóa, kiểm tra proof và quản lý vòng đời.

| Loại | Khi token bị sao chép riêng lẻ | Kiểm tra bổ sung |
| --- | --- | --- |
| Bearer | Có thể bị dùng lại nếu còn hiệu lực và đúng audience/scope. | Chữ ký/introspection, expiry, TLS và policy. |
| mTLS-bound | Thiếu chứng chỉ/khóa client tương ứng thì request không đạt điều kiện binding. | Chứng chỉ client và binding trong token. |
| DPoP-bound | Thiếu proof ký bằng khóa tương ứng thì request bị từ chối. | Chữ ký proof, method, URI, thời gian, nonce/replay cache và token binding. |

## 7. Quy trình phát hành access token

Authorization server chỉ nên phát token sau khi xác định được **ai đang yêu cầu, theo grant nào, cho resource nào và quyền gì**.

Một quy trình khái quát:

1. Client khởi tạo yêu cầu theo OAuth grant/flow được phép.
2. Authorization server xác minh client theo loại client và phương thức xác thực phù hợp.
3. Nếu có người dùng, hệ thống xác thực người dùng và thu thập consent/ủy quyền theo chính sách.
4. Server kiểm tra grant, scope được yêu cầu, audience/resource, trạng thái tài khoản và chính sách.
5. Server tạo token theo profile đã chọn, với thời hạn và thông tin cần thiết.
6. Server trả token qua kênh được bảo vệ, không ghi token vào log.
7. Client giữ token và chỉ trình tới resource server được chỉ định.

### Các grant thường gặp

| Luồng | Chủ thể/quyền được đại diện | Ghi chú |
| --- | --- | --- |
| **Authorization Code + PKCE** | Người dùng ủy quyền cho client. | Luồng phổ biến cho web/mobile; kiểm tra redirect URI, state, PKCE và token response. |
| **Client Credentials** | Chính client/workload. | Không có người dùng cuối mặc định; scope phải phản ánh quyền dịch vụ. |
| **Device Authorization Grant** | Người dùng hoàn tất xác thực/ủy quyền trên thiết bị khác. | Phù hợp thiết bị nhập liệu hạn chế; phải giới hạn polling và thời hạn. |
| **Refresh Token Grant** | Client dùng refresh token để xin access token mới. | Cần kiểm soát rotation, reuse, scope và client binding. |

Không dùng Resource Owner Password Credentials grant trong thiết kế mới; luồng này yêu cầu client xử lý mật khẩu người dùng và không phù hợp với mô hình OAuth hiện đại. Không tự phát minh grant hoặc bỏ qua kiểm tra redirect/PKCE để làm luồng đơn giản hơn.

### Access token có thể đại diện cho ai?

- Trong authorization code flow, token thường gắn với client và quyền mà người dùng đã cấp.
- Trong client credentials, token thường đại diện cho chính workload/client, không phải người dùng cuối.
- Trong một số kiến trúc ủy quyền, token có thể mang thông tin actor/delegation theo profile cụ thể.

Resource server phải hiểu đúng ngữ nghĩa của subject và client. Không mặc định subject luôn là user ID hoặc client_id là danh tính người dùng.

## 8. Xác minh access token tại resource server

Resource server là nơi thực thi quyền trên API. Không được tin token chỉ vì client gửi nó trong header.

### 8.1 Các bước kiểm tra

Với JWT access token, quy trình thường bao gồm:

1. **Kiểm tra định dạng và kích thước:** từ chối token sai định dạng hoặc vượt giới hạn.
2. **Chọn issuer/key theo cấu hình tin cậy:** không lấy iss, jku hoặc x5u từ token để tự động tải khóa tùy ý.
3. **Kiểm tra thuật toán:** chỉ cho phép thuật toán đã cấu hình; từ chối none và các kiểu algorithm confusion.
4. **Xác minh chữ ký:** dùng khóa công khai phù hợp với issuer và kid theo JWKS/cache được kiểm soát.
5. **Kiểm tra issuer:** iss phải đúng nguồn phát hành được tin cậy.
6. **Kiểm tra audience:** token phải dành cho API hiện tại.
7. **Kiểm tra thời gian:** exp, nbf, iat theo chính sách và sai lệch đồng hồ nhỏ được cho phép.
8. **Kiểm tra loại token/profile:** không nhận ID token, refresh token hoặc token khác mục đích thay access token.
9. **Kiểm tra scope/claim và trạng thái:** token chưa bị thu hồi nếu kiến trúc hỗ trợ kiểm tra; client, subject và điều kiện khác phải hợp lệ.
10. **Thực thi authorization:** kiểm tra quyền trên resource/action cụ thể.

Với opaque token, resource server thường gọi introspection hoặc tra trạng thái từ kho tin cậy. Cần bảo vệ kết nối, xác thực resource server với introspection endpoint, kiểm tra active, audience, scope, expiry và cache phù hợp.

### 8.2 Pseudocode

~~~text
function authorizeApiRequest(request, resource, action):
    token = extractBearerToken(request)
    if token is absent or token exceeds size limit:
        return UNAUTHENTICATED

    claims = verifyAccessTokenUsingTrustedConfiguration(token)
    if claims is invalid:
        return UNAUTHENTICATED

    if not audienceIncludesThisResourceServer(claims.aud):
        return UNAUTHENTICATED

    if tokenExpiredOrNotYetValid(claims):
        return UNAUTHENTICATED

    if not requiredScopePresent(claims.scope, action):
        return FORBIDDEN

    principal = resolvePrincipalFromTrustedClaims(claims)
    if not hasPermission(principal, resource, action):
        return FORBIDDEN

    return ALLOW
~~~

Đây là giả mã, không phải thư viện JWT hoàn chỉnh. Trong triển khai, cần dùng thư viện đã được kiểm chứng, cấu hình thuật toán rõ ràng và kiểm tra loại token. Không tự viết thuật toán xác minh chữ ký.

### 8.3 Vì sao audience rất quan trọng?

Giả sử authorization server phát token dành cho billing-api. Nếu profile-api cũng chấp nhận token đó mà không kiểm tra audience, token có thể bị sử dụng sai dịch vụ. Điều này tạo nguy cơ **token substitution** hoặc confused deputy.

Một token hợp lệ về chữ ký nhưng sai audience vẫn phải bị từ chối. Chữ ký chỉ chứng minh token không bị sửa và được phát hành bởi khóa tương ứng; nó không chứng minh token dành cho API đang nhận.

## 9. Scope không thay thế kiểm tra quyền trên tài nguyên

Scope mô tả phạm vi quyền đã được cấp ở mức giao thức/API. Ví dụ:

~~~text
scope = "courses:read profile:read"
~~~

Nó có thể cho biết client được gọi nhóm chức năng đọc khóa học và hồ sơ. Tuy nhiên, resource server vẫn cần kiểm tra:

- Subject có phải thành viên khóa học đang yêu cầu không?
- Client có được truy cập dữ liệu thay mặt subject đó không?
- Tài nguyên có thuộc tenant/organization phù hợp không?
- Hành động cụ thể có yêu cầu vai trò hoặc trạng thái nghiệp vụ bổ sung không?
- Có chính sách bảo vệ dữ liệu nhạy cảm hoặc step-up không?

Ví dụ, token có scope courses:read không tự cho phép học viên A đọc tiến độ của học viên B. API phải kiểm tra quan hệ giữa principal, course và dữ liệu đích.

**Scope thường là một lớp quyền tổng quát; authorization nghiệp vụ vẫn diễn ra ở resource server.** Không đưa mọi role chi tiết hoặc dữ liệu cá nhân vào token nếu API có thể truy vấn nguồn quyền đáng tin cậy và token sẽ phình to hoặc khó thu hồi.

## 10. Thời hạn, refresh và thu hồi token

### 10.1 Access token nên có thời hạn phù hợp

Token càng sống lâu thì cửa sổ lạm dụng khi bị lộ càng lớn. Token quá ngắn có thể tăng tải refresh và gây trải nghiệm kém. Thời hạn cần dựa trên:

- Giá trị tài nguyên và hậu quả nếu token bị lộ.
- Mức tin cậy của client và nơi lưu token.
- Khả năng thu hồi hoặc kiểm tra trạng thái.
- Cơ chế sender constraint.
- Yêu cầu độ mới xác thực và chính sách nghiệp vụ.

Không có một TTL duy nhất phù hợp cho mọi API. Access token thường ngắn hạn hơn refresh token, nhưng con số cụ thể cần được định nghĩa trong profile và threat model.

### 10.2 Refresh token

Refresh token được gửi tới authorization server, không gửi tới resource server. Khi hợp lệ, authorization server có thể cấp access token mới theo quyền đã được ủy quyền.

Các biện pháp:

- Giới hạn refresh token theo client và grant.
- Lưu ở nơi an toàn, tránh log và URL.
- Xoay vòng refresh token khi phù hợp; phát hiện reuse token cũ theo profile.
- Thu hồi khi logout, đổi mật khẩu, thu hồi consent hoặc nghi ngờ tài khoản bị chiếm.
- Xem xét sender constraint hoặc ràng buộc với client.
- Không cấp scope rộng hơn grant ban đầu nếu không có ủy quyền mới.

### 10.3 Thu hồi access token

Có sự khác nhau giữa hai mô hình:

| Mô hình | Thu hồi |
| --- | --- |
| Opaque token + introspection | Authorization server có thể trả active=false; hiệu lực phụ thuộc cache và tần suất introspection. |
| JWT tự chứa xác minh cục bộ | Thường khó thu hồi ngay nếu resource server không kiểm tra trạng thái/denylist hoặc phiên bản khóa/subject; token có thể còn hiệu lực đến exp. |

Một số biện pháp:

- TTL ngắn để giới hạn cửa sổ rủi ro.
- Denylist theo jti hoặc token reference khi cần thu hồi chọn lọc.
- Token introspection hoặc kiểm tra session/version tập trung.
- Xoay khóa ký khi khóa bị lộ, đồng thời có kế hoạch xử lý token cũ.
- Thu hồi refresh token để ngăn phát hành access token mới.
- Kiểm tra trạng thái tài khoản/ủy quyền ở API cho hành động nhạy cảm.

Xoay khóa ký có phạm vi ảnh hưởng lớn; không nên dùng nó như cách thu hồi một token đơn lẻ nếu có phương án phù hợp hơn.

## 11. Lưu trữ và truyền token an toàn

### 11.1 Trình token

Thông thường, access token được gửi trong header:

~~~http
Authorization: Bearer <access-token>
~~~

Không nên gửi token trong query string. URL thường bị lưu ở browser history, server/proxy log, analytics, referrer hoặc ảnh chụp màn hình. Header cũng có thể bị log, nên cần redaction ở gateway, tracing và error reporting.

### 11.2 Browser

Với ứng dụng web, các lựa chọn lưu token có rủi ro khác nhau:

- **BFF/server-side session:** browser giữ cookie phiên được bảo vệ; backend giữ token và gọi API thay browser. Cách này có thể giảm việc để access/refresh token trong JavaScript.
- **HttpOnly Secure cookie:** JavaScript không đọc trực tiếp cookie, nhưng request có cookie tự động gửi nên phải xử lý CSRF và SameSite.
- **Web storage (localStorage/sessionStorage):** JavaScript có thể đọc; XSS có thể lấy token. Tránh lưu token dài hạn hoặc quyền cao ở đây nếu có kiến trúc an toàn hơn.

Không có cách lưu trữ nào tự động an toàn khi ứng dụng có XSS hoặc logic xác thực bị lỗi. Cần giảm XSS, CSP phù hợp, encode đầu ra, dependency hygiene và kiểm soát CSRF theo kiến trúc.

### 11.3 Mobile và workload

- Mobile nên dùng secure storage/keychain/keystore theo nền tảng, giới hạn token tồn tại và bảo vệ thiết bị.
- Workload/server nên dùng secret manager, workload identity hoặc cơ chế cấp token ngắn hạn; tránh hard-code token trong source/config được commit.
- Không chia sẻ một token giữa nhiều workload không liên quan.
- Không đưa token vào command line, shell history, build artifact hoặc log.
- Phân biệt credential dùng để lấy token với access token đã cấp.

### 11.4 TLS và domain

Access token phải được truyền qua TLS tới đúng resource server. Client cần kiểm soát redirect và không chuyển tiếp header Authorization sang host không được phép. Gateway/proxy phải tránh ghi token nguyên vẹn vào access log.

## 12. Rủi ro thường gặp với access token

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Token leakage** | Token lộ qua log, URL, storage, crash dump hoặc source code. | Redaction, storage an toàn, secret scanning, TLS, TTL và revoke. |
| **Replay** | Bearer token bị sao chép rồi trình lại. | Sender constraint, TTL, audience, TLS và kiểm soát hành vi. |
| **Audience confusion** | API chấp nhận token phát cho dịch vụ khác. | Kiểm tra aud bắt buộc. |
| **Issuer confusion** | Tin token từ issuer không được cấu hình. | Allowlist issuer và cấu hình khóa tin cậy. |
| **Algorithm confusion** | Resource server chấp nhận thuật toán không mong muốn hoặc xử lý sai header. | Allowlist thuật toán, thư viện chuẩn, từ chối none và cấu hình không an toàn. |
| **Key confusion / JWKS abuse** | Token chỉ định URL khóa tùy ý hoặc kid không được xử lý an toàn. | Lấy JWKS từ issuer cấu hình sẵn, kiểm soát kid, cache và xoay khóa. |
| **Token substitution** | Dùng ID token/refresh token hoặc token sai resource ở API. | Kiểm tra token type/profile, audience và mục đích. |
| **Scope overreach** | Cấp scope rộng hơn cần thiết. | Least privilege, consent/policy và kiểm tra endpoint. |
| **Long-lived token** | Token bị lộ nhưng còn hiệu lực lâu. | TTL phù hợp, refresh flow an toàn và thu hồi. |
| **Claim trust error** | API tin role/sub mà không kiểm tra ngữ nghĩa và nguồn. | Hợp đồng issuer/claim, kiểm chứng chữ ký và authorization riêng. |
| **Refresh token reuse** | Refresh token cũ bị phát lại sau rotation. | Reuse detection, revoke token family/session và sender constraint khi phù hợp. |
| **Confused deputy** | API dùng quyền của chính nó thay mặt caller mà không ràng buộc subject/resource. | Delegation rõ, audience/scope, actor context và kiểm tra quyền. |

### JWT không được mã hóa mặc định

JWT dạng JWS thường chỉ ký nội dung. Payload có thể đọc bằng cách Base64URL decode. Không đưa secret hoặc dữ liệu nhạy cảm vào JWT với giả định chữ ký sẽ che nội dung. Nếu cần tính bí mật, phải dùng cơ chế mã hóa phù hợp hoặc tránh đặt dữ liệu đó trong token.

## 13. Phân quyền và ranh giới tin cậy

Một resource server nên xem token là **đầu vào cần kiểm chứng**, không phải một quyết định quyền hoàn chỉnh.

~~~mermaid
flowchart TD
    C["Client gửi request + access token"] --> V["Resource server xác minh token"]
    V --> Q{"Token hợp lệ, đúng issuer/audience,\nchưa hết hạn và đúng loại?"}
    Q -->|"Không"| X["401 Unauthorized"]
    Q -->|"Có"| S["Tạo principal từ claim đáng tin"]
    S --> P{"Scope và quyền trên resource/action đạt?"}
    P -->|"Không"| F["403 Forbidden"]
    P -->|"Có"| R["Thực thi nghiệp vụ"]
    R --> O["Trả kết quả được phép"]
~~~

Phân biệt response thường gặp:

- **401 Unauthorized:** thiếu hoặc không có credential hợp lệ; token sai, hết hạn hoặc không được chấp nhận.
- **403 Forbidden:** token/identity đã được chấp nhận nhưng principal không có quyền thực hiện hành động cụ thể.

API có thể dùng response tổng quát hơn theo threat model để tránh tiết lộ thông tin, nhưng phải giữ đúng ngữ nghĩa trong thiết kế và client behavior.

### Không tin claim do client gửi

Các trường sau trong body/header không tự chứng minh quyền:

~~~json
{
  "userId": "admin-1",
  "role": "administrator",
  "mfaPassed": true
}
~~~

Server phải lấy principal từ token/session đã xác minh và tra cứu quyền từ nguồn có thẩm quyền. Nếu token có claim quyền, chỉ dùng theo hợp đồng đã định nghĩa với issuer và vẫn kiểm tra tài nguyên cụ thể.

## 14. Ví dụ thực tế: API học tập

Giả sử học viên đăng nhập qua OIDC và cấp cho ứng dụng quyền đọc tiến độ học tập.

### 14.1 Cấp token

1. Học viên mở ứng dụng học tập.
2. Ứng dụng chuyển hướng tới IdP/authorization server theo Authorization Code + PKCE.
3. Người dùng xác thực và đồng ý quyền đọc tiến độ.
4. Authorization server phát access token dành cho learning-api với scope progress:read.
5. Ứng dụng giữ token theo kiến trúc phù hợp.

### 14.2 Gọi API

~~~http
GET /api/courses/course-123/progress HTTP/1.1
Host: api.learning.example
Authorization: Bearer <access-token>
Accept: application/json
~~~

Resource server:

1. Xác minh token từ issuer được cấu hình.
2. Kiểm tra audience là learning-api.
3. Kiểm tra thời hạn, chữ ký/introspection, token type và trạng thái.
4. Kiểm tra scope progress:read.
5. Xác định subject và client từ claim đáng tin cậy.
6. Kiểm tra học viên có quyền xem tiến độ course-123.
7. Trả dữ liệu chỉ thuộc phạm vi được phép.

Nếu token có scope đúng nhưng subject không ghi danh khóa học, API vẫn từ chối. Nếu token dành cho billing-api, learning-api cũng phải từ chối dù chữ ký hợp lệ.

### 14.3 Khi access token bị lộ

Nếu token bị lộ, đội vận hành cần xác định:

- Issuer, client, subject và audience.
- Scope và thời hạn còn lại.
- Token là bearer hay sender-constrained.
- API nào đã chấp nhận token và dữ liệu/hành động liên quan.
- Có refresh token bị lộ hay không.
- Cần revoke token, refresh-token family, phiên hoặc credential gốc nào.
- Có cần thông báo chủ tài khoản hoặc điều tra thiết bị/client không.

Không chỉ xóa token khỏi database phía client rồi cho rằng attacker mất quyền; cần xử lý token tại authorization/resource server theo cơ chế thu hồi đã thiết kế.

## 15. Kiểm thử access token

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token hợp lệ, đúng audience, scope và thời hạn | API tiếp tục kiểm tra quyền trên resource/action rồi mới cho phép. |
| Token hết hạn | Từ chối; client có thể xin token mới qua refresh flow nếu được phép. |
| Token có chữ ký sai | Từ chối. |
| Token từ issuer không tin cậy | Từ chối. |
| Token có audience là API khác | Từ chối. |
| ID token được gửi như access token | Từ chối do sai loại/mục đích hoặc audience. |
| Refresh token gửi tới resource server | Từ chối. |
| Token đúng nhưng scope thiếu | Từ chối quyền. |
| Token đúng scope nhưng subject không có quyền với resource | Từ chối theo authorization nghiệp vụ. |
| JWT có thuật toán không nằm trong allowlist | Từ chối. |
| Token bị revoke trong introspection/denylist | Từ chối theo trạng thái có thẩm quyền. |
| Bearer token bị sao chép sang client khác | Rủi ro được giới hạn bởi TTL; sender-constrained token phải yêu cầu proof/khóa tương ứng. |
| Token xuất hiện trong log | Redaction bảo đảm không có token rõ. |
| JWT có kid lạ hoặc header trỏ JWKS ngoài cấu hình | Không tải khóa tùy ý; từ chối hoặc xử lý theo nguồn tin cậy. |
| Token chứa scope hợp lệ nhưng gọi endpoint admin | API từ chối nếu scope/role/resource policy không cho phép. |

## 16. Checklist thiết kế và vận hành

- [ ] Đã xác định token đại diện cho client, user hay workload.
- [ ] Đã phân biệt access token với ID token, refresh token, session và API key.
- [ ] Đã chọn opaque hay self-contained dựa trên yêu cầu introspection, latency và revocation.
- [ ] Đã định nghĩa issuer, audience, scope, subject, token type và thời hạn.
- [ ] Đã chọn grant/flow OAuth phù hợp; dùng Authorization Code + PKCE cho client công khai theo profile.
- [ ] Đã cấu hình resource server xác minh token bằng thư viện chuẩn.
- [ ] Đã allowlist thuật toán và quản lý JWKS/kid từ nguồn tin cậy.
- [ ] Đã kiểm tra chữ ký, issuer, audience, expiry, nbf và token type.
- [ ] Đã thực thi authorization theo resource/action, không chỉ scope.
- [ ] Đã bảo vệ token khỏi log, URL, frontend storage và crash report.
- [ ] Đã giới hạn TTL, scope, audience và quota.
- [ ] Đã có rotation/revocation hoặc chấp nhận rõ giới hạn thu hồi của JWT.
- [ ] Đã bảo vệ refresh token và phát hiện reuse khi rotation được dùng.
- [ ] Đã cân nhắc DPoP/mTLS sender constraint cho token có rủi ro cao.
- [ ] Đã có test sai issuer, audience, chữ ký, thời hạn, scope, token type và resource ownership.

## 17. Tự kiểm tra

**Câu 1.** Access token dùng để làm gì trong OAuth?

**Đáp án:** Nó là credential được client trình cho resource server để truy cập tài nguyên trong phạm vi quyền đã cấp. Nó không mặc nhiên là bằng chứng đăng nhập cho mọi ứng dụng.

**Câu 2.** Vì sao không được gửi OIDC ID token tới API thay cho access token?

**Đáp án:** ID token dành cho OIDC client và mang ngữ nghĩa xác thực; access token dành cho resource server và quyền truy cập API. Audience và mục đích khác nhau.

**Câu 3.** Opaque token và JWT khác nhau thế nào?

**Đáp án:** Opaque token cần tra cứu/introspection để biết trạng thái và quyền; JWT tự chứa claim có thể được xác minh cục bộ bằng chữ ký và chính sách. JWT thường khó thu hồi tức thì nếu không có cơ chế bổ sung.

**Câu 4.** Vì sao bearer token bị lộ có thể bị replay?

**Đáp án:** Vì bên nắm giữ token có thể trình nó mà không cần chứng minh sở hữu khóa khác. Token cần được bảo vệ, giới hạn thời hạn/audience và có thể ràng buộc với client bằng DPoP hoặc mTLS.

**Câu 5.** Chữ ký JWT hợp lệ có đủ để API chấp nhận token không?

**Đáp án:** Không. Cần kiểm tra thuật toán, issuer, audience, thời hạn, token type, scope và trạng thái/chính sách; sau đó còn phải phân quyền trên resource/action.

**Câu 6.** iat mới có chứng minh người dùng vừa xác thực lại không?

**Đáp án:** Không. iat là thời điểm token được phát hành. Token mới có thể được cấp bằng refresh token mà không có tương tác xác thực lại của người dùng.

**Câu 7.** Vì sao aud quan trọng?

**Đáp án:** Nó xác định đối tượng nhận. Token hợp lệ dành cho API khác không được chấp nhận, giúp ngăn token substitution và confused deputy.

**Câu 8.** Scope courses:read có cho phép người dùng xem khóa học của người khác không?

**Đáp án:** Không tự động. API vẫn kiểm tra quan hệ giữa principal, tài nguyên và hành động.

**Câu 9.** Vì sao refresh token không nên gửi tới resource server?

**Đáp án:** Refresh token chỉ dùng với authorization server để xin access token mới. Resource server không có trách nhiệm chấp nhận nó như credential truy cập API.

**Câu 10.** Khi JWT bị thu hồi, vì sao resource server có thể vẫn chấp nhận nó?

**Đáp án:** Nếu resource server chỉ xác minh chữ ký cục bộ, JWT có thể còn hợp lệ tới exp. Muốn thu hồi sớm cần introspection, denylist, kiểm tra trạng thái hoặc cơ chế tương đương.

## Ghi nhớ

**Access token là credential cấp quyền truy cập resource server trong phạm vi được xác định.** Nó có thể là opaque token cần introspection hoặc JWT tự chứa cần xác minh chữ ký và claim. Token hợp lệ phải đúng issuer, audience, thời hạn, loại token và scope; resource server còn phải kiểm tra quyền trên tài nguyên và hành động cụ thể.

Hãy bảo vệ access token như bearer secret: chỉ truyền qua TLS, tránh URL/log, lưu theo kiến trúc phù hợp, giới hạn TTL/scope/audience, bảo vệ refresh token và có kế hoạch rotation/revocation. Phân biệt rõ access token với ID token, refresh token, session và API key; cân nhắc DPoP/mTLS khi cần ràng buộc token với client. **Chữ ký hợp lệ chỉ là một phần của quyết định; an toàn phụ thuộc vào toàn bộ quá trình cấp, truyền, kiểm chứng và sử dụng token.**
