# Không dùng refresh token để gọi resource API

Giả sử một ứng dụng thương mại điện tử lưu hai giá trị: **access token** và **refresh token**. Khi access token hết hạn, lập trình viên thay nó bằng refresh token trong header **Authorization: Bearer** rồi gọi lại Orders API. Cách làm này **sai mục đích sử dụng token và vi phạm ranh giới tin cậy**: refresh token là credential để client xin cấp access token mới tại **Authorization Server**, không phải credential để gọi **Resource Server**.

Lỗi này còn nguy hiểm hơn một request thất bại. Refresh token thường có giá trị duy trì quyền truy cập lâu hơn access token. Nếu gửi nó đến API nghiệp vụ, gateway, proxy và các thành phần không cần biết có thể nhận được bản sao credential dài hạn. Nếu Resource Server lại chấp nhận nhầm refresh token như access token, hệ thống có thể tạo lỗ hổng **token-type confusion/token substitution**, bỏ qua kiểm soát scope, audience và vòng đời làm mới.

Bài học thuộc chương **Refresh token** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung làm rõ sự khác nhau giữa access token, refresh token, JWT, opaque token và OIDC ID token; cách kiểm tra claims, audience, scope, trạng thái thu hồi, lưu trữ, cùng biện pháp giảm nguy cơ credential bị đánh cắp hoặc phát lại.

Sau bài học, bạn sẽ biết **gửi token nào đến endpoint nào**, thiết kế client làm mới token đúng quy trình, cấu hình Resource Server chỉ nhận access token phù hợp, xử lý lỗi an toàn và kiểm thử để refresh token không bị sử dụng như chìa khóa gọi API.

## 1. Quy tắc cơ bản: Hai credential, hai nơi nhận

Trong OAuth 2.0, các thành phần có trách nhiệm tách biệt:

| Thành phần | Nhận gì? | Làm gì? |
|---|---|---|
| **Client** | Access token và có thể refresh token do Authorization Server cấp | Dùng access token gọi API; khi cần, dùng refresh token xin access token mới |
| **Authorization Server (AS)** | Yêu cầu ủy quyền, đổi code, refresh token, credential của client theo flow | Xác minh grant/client và quyết định có phát token mới hay không |
| **Resource Server (RS)** | **Access token** phù hợp với API đang bảo vệ | Xác minh access token và quyết định quyền trên tài nguyên |
| **OpenID Connect client/Relying Party** | Có thể nhận **ID token** theo OIDC | Xác minh kết quả đăng nhập; không biến ID token thành access token |

Nhớ cặp phân biệt quan trọng:

~~~text
Client -- access token --> Resource Server / API
Client -- refresh token --> Authorization Server / token endpoint
~~~

Refresh token **không phải access token dự phòng**. Khi access token không còn hợp lệ, client phải làm mới qua Authorization Server hoặc thực hiện lại flow ủy quyền phù hợp, chứ không tự đổi loại credential trong request tới API.

### Mục đích, định dạng và phương thức dùng không giống nhau

- **Access token** nói về *mục đích*: truy cập tài nguyên được bảo vệ. Access token có thể là **JWT** hoặc **opaque token**.
- **Refresh token** nói về *mục đích*: xin token mới từ Authorization Server. Client không cần hiểu cấu trúc nội bộ của nó; thường được xử lý như một bí mật opaque.
- **Bearer** nói về *cách sử dụng credential*: bên giữ một bearer token có thể dùng nó trong phạm vi và thời hạn hợp lệ, nếu không có sender-constraining hoặc hạn chế bổ sung.
- **JWT/JWS/JWE** nói về *định dạng và lớp bảo vệ*: JWT ký có thể đọc payload, còn JWE có thể mã hóa; **cấu trúc JWT không cho phép tự suy mục đích sử dụng**.
- **OIDC ID token** là bằng chứng xác thực danh tính dành cho client, không thay access token tại Resource Server.

Một refresh token tình cờ có định dạng JWT vẫn phải được dùng ở **token endpoint**. Một access token có định dạng opaque vẫn dùng ở **Resource Server**. Không quyết định token dùng ở đâu dựa trên việc chuỗi có hai dấu chấm hay nhìn giống ký tự ngẫu nhiên.

## 2. Luồng đúng: Refresh tại Authorization Server rồi dùng access token mới

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant API as Orders API / Resource Server
    U->>C: Sử dụng ứng dụng
    C->>AS: Flow ủy quyền phù hợp
    AS-->>C: Access token AT1, có thể Refresh token RT1
    C->>API: Bearer AT1
    API->>API: Validate AT1 + policy tài nguyên
    API-->>C: Dữ liệu được phép
    Note over C: AT1 hết hạn hoặc cần làm mới
    C->>AS: POST /token, grant_type=refresh_token, RT1
    AS->>AS: Kiểm RT1, client, grant, scope, trạng thái
    AS-->>C: Access token AT2 và có thể RT2
    C->>API: Bearer AT2
    API->>API: Validate AT2 + policy tài nguyên
    API-->>C: Kết quả được phép
~~~

Luồng trên giả định Authorization Server **đã cấp refresh token hợp lệ** cho client. Không phải mọi flow và mọi loại client đều được cấp refresh token.

### Request đúng đến Resource Server

~~~http
GET /orders/ord-17 HTTP/1.1
Host: orders.example.org
Authorization: Bearer <access-token-for-orders-api>
~~~

Resource Server chỉ chấp nhận token được thiết kế cho nó. Nếu dùng JWT access token, API xác minh chữ ký và các claims theo profile; nếu dùng opaque access token, API kiểm tra qua nguồn introspection hoặc cơ chế được cấu hình tin cậy. Sau đó API mới đánh giá scope và quyền với đơn hàng cụ thể.

### Request đúng đến token endpoint để làm mới

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-value>&client_id=shop-public-client
~~~

Ví dụ chỉ minh họa **public client**. Một **confidential client** phải xác thực với token endpoint theo phương thức đã đăng ký; việc khai báo **client_id** tự nó không phải chứng cứ xác thực client. Các cơ chế như refresh token rotation hoặc sender-constraining có thể được yêu cầu tùy loại client và profile bảo mật.

Authorization Server kiểm tra refresh token có còn hợp lệ, có đúng client và grant không, quyền được phép có thay đổi không, có dấu hiệu reuse không, rồi mới có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "<new-refresh-token-if-rotated>"
}
~~~

Đây là response minh họa. **Refresh token mới không nhất thiết được cấp ở mọi lần làm mới**; khi có rotation, client phải thay thế token cũ một cách an toàn. Giá trị **expires_in=900** là thời hạn access token minh họa bằng giây, không phải thời hạn chuẩn cho mọi triển khai hoặc thời hạn của refresh token.

### Request sai cần tránh

~~~http
GET /orders/ord-17 HTTP/1.1
Host: orders.example.org
Authorization: Bearer <refresh-token-value>
~~~

Resource Server đúng phải **từ chối**. Request sai còn làm lộ refresh token cho một điểm nhận không có nhu cầu giữ nó. Đừng “sửa” bằng cách cho Orders API gửi tiếp refresh token đến Authorization Server thay client; đó sẽ làm phân tán quyền giữ credential và phá thiết kế ranh giới. Nếu ứng dụng cần kiến trúc **Backend for Frontend (BFF)** thì BFF là bên được thiết kế và bảo vệ riêng để giữ token, không phải mọi API nghiệp vụ mặc nhiên trở thành token broker.

## 3. Vì sao gửi refresh token tới API nguy hiểm?

### 3.1. Lộ một bí mật có khả năng xin token mới

Access token thường có hạn dùng tương đối ngắn. Refresh token có thể tồn tại lâu hơn vì mục tiêu của nó là duy trì ủy quyền giữa các lần cấp access token. Nếu kẻ tấn công lấy được refresh token, họ có thể cố đổi lấy access token mới qua Authorization Server khi credential còn hợp lệ, nếu các biện pháp client binding hoặc sender-constraining không ngăn được.

Gửi refresh token đến Resource Server mở rộng các nơi nhìn thấy nó:

- **API gateway và reverse proxy** nhận header hoặc có thể ghi log request.
- **APM, tracing, crash report** có thể thu thập dữ liệu HTTP nếu chưa redaction.
- **Resource Server, middleware, các dịch vụ chuyển tiếp** có thể lưu tạm credential trong bộ nhớ hoặc telemetry.
- **Nhân sự vận hành, hệ thống phân tích, support tools** có thể thấy bản sao do cấu hình log sai.

Với refresh token, hậu quả có thể vượt một access token đã hết hạn vì credential bị lộ có thể được dùng để **duy trì** truy cập. Không nên trao bí mật đó cho mọi thành phần chỉ cần xác minh access token.

### 3.2. Nhầm quyền cấp token với quyền truy cập tài nguyên

Refresh token là chứng cứ để Authorization Server xem xét **cấp token mới**. Nó không tự chứng minh:

- Người giữ token được đọc tất cả đơn hàng.
- Token có audience hợp lệ cho **orders-api**.
- Token có scope **orders:read** cần thiết.
- Token đang đại diện cho một người dùng hiện còn membership trong tenant.
- Resource Server được phép nhận loại credential ấy.

Quyền làm mới và quyền thao tác tài nguyên là **hai quyết định khác nhau**. Authorization Server đánh giá refresh grant; Resource Server đánh giá access token và policy nghiệp vụ.

### 3.3. Token-type confusion: Nhận nhầm refresh token như access token

Nếu Authorization Server dùng cùng hệ thống ký hoặc định dạng JWT cho nhiều loại token, một validator chỉ kiểm **chữ ký đúng + iss đúng + chưa hết hạn** có thể nhận nhầm refresh token. Đây là lỗi **token substitution**: một credential được tạo cho mục đích A bị chấp nhận trong ngữ cảnh B.

Nguy cơ đặc biệt nghiêm trọng khi Resource Server:

1. Chấp nhận JWT bất kỳ từ một issuer, không xác minh **token type/profile** và **audience**.
2. Tự giải mã Base64url rồi tin claims **sub**, **roles**, **scope** chưa xác minh.
3. Suy một chuỗi có cấu trúc hoặc claim do token tự đặt là access token hợp lệ.
4. Cho phép JWT refresh token không có audience của API đi qua vì “cùng chữ ký”.
5. Sử dụng chung kho khóa và validation rules cho token có mục đích khác nhau mà không có cơ chế phân biệt đáng tin.

**Đúng chữ ký không đồng nghĩa đúng mục đích.** Resource Server phải áp dụng bộ quy tắc dành riêng cho **access token**, độc lập với bộ quy tắc Authorization Server dùng để kiểm refresh token.

## 4. Resource Server phải nhận diện access token đúng cách

Một API dùng OAuth Bearer access token cần xây dựng chuỗi xác minh với **trust configuration** từ phía server, không để request tự chỉ nguồn tin cậy. Các điều kiện điển hình:

| Điều kiện | JWT access token | Opaque access token |
|---|---|---|
| **Nguồn được tin** | Issuer trong allowlist, key/JWKS gắn đúng issuer | Endpoint introspection hoặc nguồn trạng thái của issuer được cấu hình |
| **Chứng cứ hợp lệ** | Chữ ký/MAC đúng thuật toán và key được cho phép | Introspection có bảo vệ, trả token còn hoạt động |
| **Loại token** | JWT access token đúng profile, không phải ID/refresh token | Nguồn xác minh ràng buộc handle với access token, không phải refresh token |
| **Audience** | **aud** chứa Resource Server dự kiến, theo hợp đồng | Có bằng chứng ràng buộc token với API từ introspection hoặc cơ chế tương đương |
| **Thời gian** | **exp**, **nbf** (nếu có), các điều kiện của profile | Trạng thái active, thời hạn và độ mới metadata theo hợp đồng |
| **Quyền cấp** | Scope/entitlement được xác minh | Scope/entitlement từ nguồn introspection tin cậy |
| **Quyền đối tượng** | Membership, ownership, role, trạng thái tài nguyên hiện hành | Chính các điều kiện nghiệp vụ tương tự |

Với **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, profile có các quy định về JOSE **typ** (ví dụ **at+jwt**) và claims bắt buộc như **iss, sub, aud, exp, iat, jti, client_id**. Nếu hệ thống chọn profile đó, Resource Server cần thực thi toàn bộ các điều kiện phù hợp, không chỉ so sánh chuỗi **typ**. Một JWT refresh token tự đặt **typ=at+jwt** nhưng không được ký/kiểm chứng đúng như access token cũng không trở thành access token hợp lệ.

Với **opaque token**, việc chuỗi “không đọc được” không cung cấp bằng chứng nó là access token. API phải dựa trên nguồn đáng tin xác nhận **đúng loại và ngữ cảnh**.

### Introspection active=true chưa đủ

Ví dụ Resource Server nhận:

~~~json
{
  "active": true,
  "client_id": "shop-web",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Đây là metadata minh họa từ **OAuth 2.0 Token Introspection (RFC 7662)**. **active** là trường cốt lõi; các trường khác tùy chính sách của Authorization Server. Resource Server phải có **hợp đồng xác minh** để biết đây là **access token có hiệu lực cho API này**. Không coi **active=true** là quyền truy cập nếu endpoint introspection cũng có thể xác nhận trạng thái của **refresh token** mà không phân biệt rõ loại.

Tham số **token_type_hint=access_token** trong request introspection chỉ là **gợi ý** giúp server tìm kiếm; caller tự điền giá trị này không chứng minh token là access token. Tương tự, một trường **token_type=Bearer** thể hiện kiểu sử dụng bearer theo hợp đồng, **không thay thế mọi kiểm tra mục đích/access-token profile**.

Nếu introspection không cung cấp đủ thông tin để phân biệt token loại nào hoặc chứng minh audience, Resource Server phải dùng cơ chế ràng buộc an toàn đã thống nhất với issuer, hoặc **từ chối**. Không mặc định cho phép chỉ vì kết quả HTTP là **200 OK** hoặc **active=true**.

### Issuer và audience là ranh giới khác nhau

Một issuer có thể phát hành token cho nhiều API. Access token đúng issuer nhưng có **aud=payments-api** không dùng cho **orders-api**. Refresh token không tự thừa hưởng “audience của mọi API” chỉ vì được tạo từ cùng một grant. **Scope** cũng không thay audience: **orders:read** không chứng minh token được cấp cho Orders API nếu không có ràng buộc người nhận hợp lệ.

## 5. Quy trình bảo vệ API khỏi refresh token

~~~mermaid
flowchart TD
    A["Resource Server nhận Bearer token"] --> B{"Có credential đúng cú pháp?"}
    B -->|Không| X["401: không có access token hợp lệ"]
    B -->|Có| C["Validator được cấu hình chỉ nhận access token"]
    C --> D{"Nguồn/chữ ký hoặc introspection đáng tin?"}
    D -->|Không| X
    D -->|Có| E{"Đúng loại token/profile access token?"}
    E -->|Không: refresh/ID token| X
    E -->|Có| F{"Issuer, audience, thời gian và trạng thái đạt?"}
    F -->|Không| X
    F -->|Có| G{"Scope đủ cho endpoint?"}
    G -->|Không| Y["403: thiếu quyền được cấp"]
    G -->|Có| H{"Quyền trên đối tượng/tenant đạt?"}
    H -->|Không| Y
    H -->|Có| I["Cho phép thao tác được yêu cầu"]
~~~

Pseudocode kiểm tra tại Orders API:

~~~text
getOrder(request):
    token = requireBearerToken(request)
    if token missing:
        return 401

    # Cấu hình này phải đến từ phía server, không từ token/request.
    validation = trustedAccessTokenValidator.validate(
        token,
        trustedIssuer = "https://auth.example.org",
        expectedAudience = "orders-api",
        expectedTokenKind = "access_token",
        acceptedProfile = configuredProfile
    )
    if validation invalid:
        return 401

    principal = validation.verifiedPrincipal
    if not principal.hasExactScope("orders:read"):
        return 403

    order = loadOrderInValidatedTenant(request.orderId)
    if order missing:
        return 404

    if not currentPolicy.canReadOrder(principal, order):
        return 403

    return 200, allowedOrderFields(order)
~~~

Đây là **pseudocode thiết kế**, không phải thư viện bảo mật có thể dùng trực tiếp. Với JWT, validator phải xác minh chữ ký, issuer, audience, thời gian, header/profile, thuật toán và trust/key state; với opaque token, validator phải dùng introspection an toàn và cơ chế phân biệt loại token. Không chỉ đọc claim **token_kind** do client khai rồi cho phép.

Các bước quan trọng khi triển khai:

1. **Phân biệt token tại điểm vào:** API không chấp nhận refresh token, ID token, authorization code hay client secret như bearer access token.
2. **Gắn keys và issuer:** JWT phải được xác minh với key của nguồn đã tin; không tự tải key theo URL do token cung cấp.
3. **Kiểm audience:** API nhận token dành cho chính nó, không nhận token của API khác.
4. **Kiểm quyền tối thiểu:** scope đúng hành động, rồi policy theo tài nguyên/tenant.
5. **Fail closed:** khi verifier không thể xác minh token, không tự chuyển sang nhánh decode-only hoặc mặc định cho phép.

Không phải mọi hệ thống có thể phân biệt access/refresh token chỉ bằng một claim công khai. Kiến trúc đúng cần phối hợp **Authorization Server và Resource Server** để có profile riêng, token namespace/format phù hợp, hoặc introspection contract không thể khiến refresh token được diễn giải thành access token.

## 6. Tránh lỗi khi cả access token và refresh token đều là JWT

Một hệ thống có thể ký access token và refresh token bằng những khóa, issuer hoặc cơ chế chung. Cùng kiểu chữ ký không làm hai token được phép hoán đổi.

Ví dụ giả định (payload chỉ để học):

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "purpose": "refresh",
  "client_id": "shop-web",
  "exp": 1902592800
}
~~~

Claim **purpose** ở đây là **trường tùy biến để minh họa**, không phải claim tiêu chuẩn tự bảo đảm phân biệt refresh token. Nếu Orders API chỉ kiểm chữ ký và **sub** rồi bỏ qua purpose/audience/token profile, refresh token có thể bị chấp nhận nhầm. Nếu attacker có khả năng sửa token nhưng không thể tạo chữ ký hợp lệ thì chữ ký vẫn chống sửa; nhưng **một refresh token hợp lệ do chính issuer tạo** sẽ nguy hiểm nếu validator sai mục đích.

**Cách phòng tránh**:

- Dùng **access-token validator** chỉ chấp nhận cấu trúc, claims, header và audience phù hợp profile API. Với JWT access token chuẩn hóa theo RFC 9068, xác minh cả **typ** và required claims.
- Giữ **refresh token validation** trong Authorization Server/token endpoint, với trạng thái, client binding, thời hạn, rotation và revocation riêng.
- Tránh chia sẻ một validator tổng quát giữa ID token, access token và refresh token mà thiếu các quy tắc loại trừ chéo.
- Nếu dùng token có chung issuer/key, cần quy tắc **mutually exclusive** đủ mạnh giữa các loại token, kèm negative tests: mỗi loại bị từ chối tại nơi nhận của loại kia.
- Không cho API tự xác minh “refresh token JWT” rồi tạo access token mới. **Phát token là quyền của Authorization Server** và phải đi qua flow/kiểm soát của nó.

### Không chỉ dựa vào chuỗi typ hoặc purpose

Một header **typ=at+jwt** từ token chưa xác minh cũng là dữ liệu chưa đáng tin cho đến khi mật mã được kiểm. Sau xác minh, nó vẫn phải khớp profile và audience. Tương tự, claim tùy biến **purpose=access** không thay thế audience, signature verification hoặc chính sách của Authorization Server. **Phân biệt loại token phải được thực thi bằng hợp đồng hoàn chỉnh**, không một phép so chuỗi lẻ.

## 7. Refresh token bị gửi nhầm: API và client nên làm gì?

Nếu client lỡ đưa refresh token tới Resource Server, mục tiêu là **ngăn sử dụng token sai mục đích và giảm hậu quả lộ credential**.

### 7.1. Resource Server

Resource Server nên:

- **Từ chối** yêu cầu vì không có access token hợp lệ, thường bằng **401 Unauthorized** theo quy tắc Bearer token áp dụng.
- **Không** gọi endpoint refresh thay client và không trả về access token mới thay cho Authorization Server.
- **Không** đưa nguyên refresh token vào response, log, tracing, exception, analytics hoặc thông báo gửi support.
- Ghi mã lỗi an toàn như **WRONG_TOKEN_TYPE** (khi hệ thống có thể xác định chính xác), request ID và dữ liệu quan sát tối thiểu; không cần ghi credential thật.
- Cân nhắc cơ chế phát hiện sự kiện credential có giá trị cao bị gửi sai đích để đội vận hành đánh giá rủi ro rò rỉ, tránh công bố thông tin chi tiết cho caller.

Ví dụ một Bearer challenge dành cho token không chấp nhận được:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

HTTP 401 là phản hồi thường gặp khi credential không hợp lệ với API; API cần tuân thủ cách sử dụng **WWW-Authenticate** theo RFC 6750. Nếu mạng/JWKS/introspection không thể xác minh do sự cố hệ thống, có thể dùng lỗi **503** hoặc từ chối theo chính sách; nhưng **không tự chấp nhận token** chỉ vì dịch vụ xác minh lỗi.

### 7.2. Client

Client cần sửa luồng xử lý:

1. Lưu rõ **accessToken** và **refreshToken** ở hai vị trí logic khác nhau; API client chỉ đọc accessToken.
2. Khi access token hết hạn, gọi **token endpoint** bằng refresh token theo grant được cấp.
3. Chỉ khi refresh thành công mới thay access token trong các request API.
4. Nếu Authorization Server trả refresh token mới do **rotation**, lưu thay thế một cách an toàn và ngừng dùng token cũ.
5. Nếu refresh thất bại vì token bị thu hồi/hết hạn, xóa credential không hợp lệ và chuyển sang flow đăng nhập/ủy quyền phù hợp.
6. Không retry vô hạn request API bằng refresh token và không tự tăng scope/audience khi làm mới.

Nếu nghi refresh token đã bị sao chép vào log hoặc gửi tới endpoint ngoài kiểm soát, cần xem là **sự cố có thể lộ credential**, đánh giá phạm vi phát tán và dùng quy trình thu hồi/đăng nhập lại khi cần. Không đủ để chỉ thay một dòng code rồi giữ nguyên token có khả năng bị lộ.

## 8. Luồng client an toàn: Refresh có kiểm soát

Client có thể làm mới token **trước khi access token hết hạn** hoặc khi API trả lỗi access token không hợp lệ, tùy cơ chế. Phải phân biệt lỗi **401** do không có access token hợp lệ với lỗi **403** do token hợp lệ nhưng không đủ quyền.

### 8.1. Tránh dùng refresh token như phương án fallback trong interceptor

Sai:

~~~text
onApi401(request):
    request.Authorization = "Bearer " + refreshToken
    retry(request)
~~~

Đúng về mặt luồng trách nhiệm:

~~~text
onApi401(request):
    if not eligibleToRefresh(request):
        handleAuthenticationFailure()
        return

    tokens = await singleFlightRefreshAtAuthorizationServer()
    if tokens invalid:
        clearInvalidCredentials()
        requireReauthorizationWhenAppropriate()
        return

    safelyStoreNewTokens(tokens)
    retryOriginalApiRequestAtMostOnceWith(tokens.accessToken)
~~~

Mã là **pseudocode**, không phải khuyến nghị retry tự động mọi request. Ví dụ thanh toán hoặc hoàn tiền có side effect phải xử lý **idempotency và trạng thái server** trước khi retry; nếu không, việc refresh thành công có thể dẫn đến giao dịch bị thực hiện nhiều lần.

### 8.2. Nhiều request cùng hết hạn access token

Giả sử trình duyệt có ba request API đồng thời phát hiện access token đã hết hạn. Nếu mỗi request đều gửi cùng **RT1** để refresh trong khi Authorization Server dùng **refresh token rotation**, một request có thể thành công, còn hai request khác bị xem là reuse. Điều này có thể dẫn đến thu hồi cả token family theo chính sách.

**Single-flight refresh** nghĩa là các request cùng chờ **một tác vụ refresh**, rồi dùng cùng access token mới. Nếu có nhiều tab, nhiều worker hoặc nhiều phiên xử lý backend, cần thêm cơ chế đồng bộ phù hợp. Không giải quyết bằng cách cho refresh token cũ được sử dụng vô hạn.

### 8.3. Không làm mới token khi thiếu quyền

| Phản hồi | Ý nghĩa thường gặp | Hành vi phù hợp |
|---|---|---|
| **401 invalid_token** do access token hết hạn | Chưa có access token hợp lệ | Có thể refresh qua Authorization Server nếu được phép, sau đó retry có kiểm soát |
| **403 insufficient_scope** | Access token hợp lệ nhưng thiếu scope | Không refresh lặp vô hạn để tìm quyền chưa được cấp; xử lý thiếu quyền/ủy quyền lại theo flow |
| **403** do role, tenant, ownership | Phân quyền nghiệp vụ từ chối | Không đổi refresh token thành access token rồi mong có quyền |
| **invalid_grant** từ token endpoint | Refresh token/grant không được chấp nhận | Ngừng dùng credential, yêu cầu xác thực/ủy quyền lại khi thích hợp |
| Token endpoint tạm lỗi mạng | Chưa biết refresh đã được xử lý chưa | Retry có kiểm soát; nếu rotation đã xảy ra, gửi lại RT cũ có thể bị đánh dấu reuse |

Không phải mọi lỗi 401 nhất thiết có thể sửa bằng refresh (ví dụ sai audience/issuer, token bị thu hồi hoặc client dùng sai loại token). Cần tránh vòng lặp vô hạn và có giới hạn retry rõ.

## 9. Token rotation, thu hồi và cửa sổ rủi ro

Refresh token có thể được cấp cùng **rotation**: RT1 được dùng một lần để nhận AT2 và RT2, rồi RT1 bị vô hiệu hóa. Nếu RT1 được dùng lại, Authorization Server có thể phát hiện dấu hiệu bị sao chép.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant API as Orders API
    C->>AS: Refresh RT1 hợp lệ
    AS->>AS: Kiểm client/grant và tiêu thụ RT1
    AS-->>C: AT2 + RT2
    C->>API: Bearer AT2
    API-->>C: Kết quả theo quyền
    C->>AS: RT1 cũ bị dùng lại
    AS->>AS: Phát hiện reuse, áp dụng chính sách
    AS-->>C: Từ chối và có thể thu hồi token family
~~~

Rotation và kiểm soát đồng thời cần được thiết kế **atomic**, tránh RT1 tạo ra nhiều nhánh refresh token hợp lệ. Sự kiện reuse không mặc nhiên cho biết bên nào là client hợp pháp và bên nào là kẻ tấn công. AS cần có chính sách phát hiện, thu hồi family, cảnh báo và yêu cầu đăng nhập lại khi thích hợp.

### Thu hồi refresh token không tự vô hiệu hóa mọi access token đã cấp

Giả sử AS vô hiệu hóa RT2 lúc 10:05 nhưng JWT access token AT2 đã phát hành còn hạn tới 10:15. Nếu Resource Server chỉ kiểm chữ ký và thời hạn, AT2 có thể vẫn được chấp nhận tới lúc hết hạn. Nếu API còn sử dụng **opaque access token** qua introspection, có thể biết trạng thái token mới hơn, nhưng cache introspection vẫn tạo độ trễ.

Vì vậy cần phân biệt:

- **Thu hồi refresh token**: ngăn khả năng xin access token mới.
- **Thu hồi access token**: ngăn credential đã cấp tiếp tục dùng ở Resource Server, theo kiến trúc introspection/denylist/epoch hoặc phương án tương đương.
- **Thu hồi key/issuer**: ngừng tin nguồn phát hành khi khóa ký hoặc Authorization Server bị xâm phạm.

Chỉ “đăng xuất ở UI” hoặc xóa token khỏi một tab trình duyệt không đảm bảo bản sao credential bị lộ ngoài hệ thống không còn dùng được. Khi cần thu hồi, hãy gọi cơ chế do Authorization Server cung cấp, ví dụ **OAuth 2.0 Token Revocation (RFC 7009)** theo quyền và flow cho phép, và xử lý các access token còn hiệu lực theo chính sách hệ thống.

## 10. Bảo vệ refresh token để không xuất hiện ở Resource Server

Một thiết kế tốt hạn chế số thành phần **có thể chạm vào refresh token**:

| Nơi lưu/luồng | Chiến lược giảm rủi ro | Điều cần hiểu |
|---|---|---|
| **Backend/confidential client** | Giữ RT ở server, secret manager/kho dữ liệu có phân quyền, mã hóa và log redaction phù hợp | Bản sao trong backup, tracing, lỗi vận hành vẫn phải bảo vệ |
| **Web app với BFF** | BFF giữ RT; browser chủ yếu giữ session cookie được bảo vệ | Cookie **HttpOnly; Secure; SameSite** hỗ trợ giảm lộ RT cho JS, nhưng vẫn cần phòng XSS/CSRF |
| **SPA/public client** | Hạn chế token JS-accessible, bảo vệ chống XSS, rotation hoặc sender-constraining theo profile | localStorage dài hạn có thể làm tăng hậu quả khi script độc hại chạy |
| **Native/mobile** | Keychain/Keystore hoặc secure storage phù hợp, bảo vệ redirect flow và backup | Thiết bị bị xâm nhập vẫn là rủi ro |
| **Authorization Server** | RT dạng tham chiếu có entropy cao, trạng thái/rotation/revoke, kiểm client binding | Có thể lưu token handle dạng dẫn xuất một chiều khi kiến trúc cho phép |
| **Resource Server** | Chỉ nhận access token, không lưu/cấp/chuyển tiếp refresh token | Chặn log raw Authorization và xử lý credential gửi sai đích |

**Không đưa refresh token vào payload JWT access token hoặc ID token.** JWT ký thông thường **đọc được payload** bằng Base64url-decoding, nên mọi thành phần có access token sẽ dễ lấy được refresh token bị nhúng. Kể cả nếu mã hóa bằng JWE, việc trộn hai credential với những nơi nhận khác nhau vẫn làm tăng rủi ro và phức tạp hóa vòng đời.

### Các vị trí thường vô tình làm rò token

- Header Authorization được đưa nguyên vào access log của reverse proxy.
- HTTP tracing hoặc APM ghi lại request body của token endpoint.
- Error handler gửi toàn bộ request khi báo lỗi cho hệ thống giám sát.
- Công cụ hỗ trợ khách hàng yêu cầu người dùng dán token thật để debug.
- Client đưa token vào URL query string, history hoặc analytics.
- API client library tái sử dụng một biến **token** chung cho cả access/refresh và gắn nhầm vào mọi request.

Nên có **kiểm thử và cấu hình redaction** để ngăn mọi credential xuất hiện trong log, không chỉ mã hóa phương tiện lưu log. Nếu cần audit, ghi request ID, client ID phù hợp, mã lỗi và policy version mà **không thể tái sử dụng các giá trị đó làm credential**.

## 11. Khi API gọi API khác, refresh token cũng không phải lời giải

Giả sử client gọi Orders API bằng access token có **aud=orders-api**, sau đó Orders API cần lấy thông tin thanh toán từ Payments API.

Không nên:

- Dùng refresh token của client làm **Bearer** cho Payments API.
- Chuyển nguyên access token dành cho orders-api sang Payments API rồi bỏ qua audience.
- Cho mọi Resource Server giữ refresh token để tự phát hành token phục vụ gọi dịch vụ khác.

Có thể chọn một trong các phương án theo chính sách:

1. **Client Credentials / service identity:** Orders API lấy access token dành cho Payments API theo quyền của chính dịch vụ, nếu công việc không yêu cầu đại diện người dùng.
2. **Delegation hoặc OAuth 2.0 Token Exchange (RFC 8693):** khi cần hành động thay mặt người dùng và hạ tầng hỗ trợ, đổi chứng cứ ủy quyền theo chính sách để nhận **access token mới có audience=payments-api** và scope giới hạn.
3. **BFF/token broker được thiết kế rõ:** chỉ thành phần được ủy quyền giữ refresh token và tương tác với Authorization Server; các Resource Server nghiệp vụ vẫn không tự nhận refresh token làm API credential.

**Token Exchange không giống refresh grant.** Token Exchange xử lý việc nhận token phù hợp audience/chủ thể/actor theo ủy quyền được kiểm tra; refresh grant duy trì một grant để xin access token mới. Không được chuyển một token bất kỳ giữa các dịch vụ rồi tự đổi tên nó thành access token.

## 12. Ví dụ toàn bộ: Ứng dụng mua sắm và Orders API

Giả sử hệ thống có:

- Authorization Server: **https://auth.example.org**.
- Client ứng dụng web: **shop-web**.
- Resource Server: **orders-api**.
- Access token AT1 có audience **orders-api**, scope **orders:read**, sống 15 phút theo ví dụ.
- Refresh token RT1 chỉ được lưu tại thành phần client/BFF đủ quyền, do AS phát hành khi chính sách cho phép.

| Mốc giả định | Sự kiện | Cách xử lý đúng |
|---|---|---|
| 09:00 | AS phát AT1 và RT1 | Lưu riêng hai credential, không đưa RT1 vào API client |
| 09:06 | Client xem đơn hàng | Gửi **AT1** đến Orders API; API kiểm issuer, audience, scope và quyền |
| 09:16 | AT1 hết hạn | Client gửi **RT1** đến token endpoint của AS |
| 09:16 | AS xác minh và rotation | Trả **AT2** và **RT2**; RT1 không còn dùng |
| 09:17 | Client tiếp tục xem đơn hàng | Gửi **AT2** đến Orders API, không bao giờ gửi RT2 |
| 09:30 | Quản trị viên thu hồi grant | AS từ chối refresh tiếp theo; RS xử lý AT2 theo chính sách hiệu lực/thu hồi |

Đây là **mốc thời gian minh họa**, không phải TTL hoặc lịch phát hành tiêu chuẩn. Các khoảng thời gian/độ trễ thực tế phụ thuộc issuer, Resource Server, cache và chính sách rủi ro.

### Bốn tình huống dễ nhầm

**Tình huống A: API trả 401 do AT1 hết hạn.** Client không gắn RT1 vào request Orders API. Client refresh với AS, lưu token mới rồi chỉ dùng access token mới.

**Tình huống B: API trả 403 vì thiếu orders:write.** Refresh cùng grant **không tự tạo quyền viết**; client không nên gọi refresh liên tục để dò quyền. Cần ủy quyền phù hợp hoặc từ chối thao tác.

**Tình huống C: RT1 bị gửi nhầm cho Orders API.** API phải từ chối và không log credential; vận hành đánh giá nguy cơ lộ RT1 nếu đường ghi log hoặc các thành phần trung gian có thể đã sao chép nó.

**Tình huống D: RT1 bị đánh cắp và người dùng đã đổi thành RT2.** Kẻ tấn công thử dùng RT1; AS phát hiện reuse và có thể thu hồi toàn bộ token family, yêu cầu xác thực lại. Orders API không xử lý reuse đó: **đây là trách nhiệm của AS**.

## 13. Ma trận kiểm thử: Resource Server không được nhận refresh token

| Test case | Kết quả mong đợi |
|---|---|
| Access token đúng issuer/audience, chưa hết hạn, đủ scope và quyền tài nguyên | **Permit** hành động cụ thể |
| Refresh token opaque gửi đến Orders API dưới dạng Bearer | **Reject**, không dùng nó gọi token endpoint thay client |
| Refresh token nội bộ dùng JWT, chữ ký cùng issuer với access token | **Reject** vì sai profile/loại token hoặc không đạt access-token contract |
| JWT refresh token có sub hợp lệ nhưng không có audience orders-api | **Reject** |
| OIDC ID token có chữ ký hợp lệ và aud=shop-web gửi tới API | **Reject** vì sai mục đích/audience |
| Opaque token được introspect active=true nhưng không chứng minh đây là access token cho Orders API | **Reject** hoặc áp dụng ràng buộc tin cậy bổ sung đã được thiết kế; không Permit mặc định |
| JWT access token sai issuer hoặc audience | **Reject** |
| JWT access token hết hạn | **Reject**, client có thể refresh qua AS nếu được phép |
| Access token hợp lệ nhưng thiếu scope | **Deny authorization**; không tự chuyển sang RT |
| Access token đủ scope nhưng sai tenant/owner | **Deny authorization** |
| Token endpoint nhận RT đã revoke hoặc hết hạn | **Reject refresh grant** |
| Token endpoint nhận RT1 đã dùng sau rotation | **Reject**, kích hoạt reuse policy |
| Nhiều request refresh cùng RT1 | Không phát nhiều nhánh hợp lệ trái policy; client và AS xử lý đồng thời |
| API nhận RT và có tracing enabled | Log/traces **không chứa RT thô** |
| Introspection/JWKS không xác minh được do sự cố | **Không fail open** |
| Sau khi revoke RT, JWT access token cũ vẫn còn hạn | Kết quả ở RS đúng với chính sách thu hồi/token TTL, không giả định vô hiệu hóa tức thì |

Test phải kiểm **không có dữ liệu bảo vệ được trả ra và không có side effect** khi API nhận sai loại token. Không chỉ kiểm rằng endpoint trả 401; cần bảo đảm credential không bị log, gửi tiếp hoặc dùng làm bằng chứng phân quyền tại các đường gọi nội bộ, background jobs và message consumers.

### Gợi ý kiểm thử ở tầng tích hợp

Trong môi trường thử nghiệm:

~~~text
Given:
  - Authorization Server test cấp AT(access) và RT(refresh)
  - Orders API chỉ chấp nhận access token có aud=orders-api

When:
  - GET /orders/ord-17 dùng AT -> kiểm quyền tài nguyên
  - GET /orders/ord-17 dùng RT -> bị từ chối
  - POST /oauth2/token dùng RT hợp lệ -> có thể cấp AT mới
  - POST /oauth2/token dùng RT đã rotation -> bị từ chối

Then:
  - Không có request API nào dùng RT nhận dữ liệu bảo vệ
  - Không bản ghi log/tracing nào chứa credential thô
  - Token mới chỉ do AS cấp theo grant/client/policy
~~~

Không sử dụng refresh token production trong các bài test. Dùng credential giả trong môi trường được phép, đồng thời kiểm tra cấu hình **separate validators** của Resource Server và Authorization Server.

## 14. Checklist trước khi triển khai

1. **Đúng nơi nhận:** API chỉ nhận access token; refresh token chỉ đến token endpoint của AS?
2. **Đúng biến/kiểu dữ liệu:** client có tách accessToken và refreshToken, không dùng biến chung dễ gắn nhầm header?
3. **Đúng profile:** Resource Server có kiểm chữ ký hoặc introspection cùng token type, issuer, audience và thời gian, không nhận ID/refresh token?
4. **Đúng scope:** API có kiểm scope chính xác theo action và quyền trên tài nguyên không?
5. **Đúng grant:** AS có kiểm refresh token còn hạn, đúng client, đúng quyền gốc, không mở rộng scope/audience tùy ý?
6. **Chống replay:** refresh token rotation hoặc sender-constraining có được thiết kế theo loại client và yêu cầu profile?
7. **Đồng thời:** client có single-flight refresh; AS có kiểm soát atomic khi rotation?
8. **Lưu trữ:** refresh token có được giữ tại thành phần tối thiểu và an toàn, tránh JS-accessible storage khi rủi ro không chấp nhận được?
9. **Logging:** API gateway, proxy, token endpoint, APM, tracing và exception handlers có redaction cho credential?
10. **Lỗi:** 401 access token không hợp lệ có luồng refresh riêng, còn 403 thiếu quyền không gây refresh vô hạn?
11. **Thu hồi:** đã phân biệt revoke refresh token, access token, key/issuer và độ trễ cache?
12. **Dịch vụ trung gian:** API-to-API dùng service token/delegation có audience đúng, không chuyển tiếp refresh token?
13. **Kiểm thử:** có negative tests trực tiếp thử gửi RT tới API, thử RT dạng JWT/opaque và xác minh không có side effect?

## 15. Câu hỏi tự đánh giá

**1. Access token hết hạn thì có thể gửi refresh token thay thế đến API không?** Không. Client phải dùng refresh token tại token endpoint của Authorization Server để xin access token mới, nếu grant vẫn được phép.

**2. Tại sao refresh token gửi tới Resource Server làm tăng rủi ro?** Vì refresh token có thể duy trì khả năng cấp access token mới và có thể bị lộ qua gateway, log, tracing hoặc API không cần biết credential này.

**3. Refresh token có định dạng JWT và ký đúng thì Resource Server được nhận không?** Không. Chữ ký đúng không biến refresh token thành access token. Resource Server phải kiểm **đúng loại/profile, audience và các điều kiện access token**.

**4. Introspection active=true có đủ chứng minh token là access token không?** Không mặc nhiên. Resource Server cần hợp đồng tin cậy phân biệt loại token và ràng buộc audience; có thể phải từ chối nếu không đủ bằng chứng.

**5. Lỗi 403 thiếu scope có thể sửa bằng cách refresh token liên tục không?** Không. Refresh không được tự nâng scope ngoài grant; cần xử lý phân quyền hoặc thực hiện flow xin quyền mới hợp lệ.

**6. Ai xử lý refresh token rotation và phát hiện reuse?** Authorization Server. Client phải lưu thay token mới an toàn và tránh refresh đồng thời; Resource Server không tự đổi refresh token.

**7. Thu hồi refresh token có làm access token đã cấp hết hạn ngay không?** Không mặc định. JWT access token có thể còn hợp lệ tới exp nếu Resource Server không có cơ chế thu hồi bổ sung; opaque access token cũng có thể bị ảnh hưởng bởi cache introspection.

**8. Orders API cần gọi Payments API thay mặt người dùng thì có nên mượn refresh token của user không?** Không. Nên dùng access token phù hợp audience và ủy quyền theo service identity/delegation hoặc Token Exchange được AS cho phép.

**9. Client nhận lại refresh token mới khi rotation thì phải làm gì?** Thay refresh token cũ trong bộ lưu trữ an toàn; không gửi refresh token mới đến API và không sử dụng lại token cũ.

**Ghi nhớ:** **Refresh token dùng để xin cấp access token mới tại Authorization Server; access token mới dùng để truy cập Resource Server.** Không đưa refresh token vào header Bearer khi gọi API, không chuyển tiếp nó qua các service và không coi một JWT ký đúng là bằng chứng token đúng mục đích. Client phải tách credential, bảo vệ refresh token và xử lý refresh/rotation an toàn; Resource Server phải từ chối token sai loại, kiểm issuer, audience, scope và quyền trên từng tài nguyên.
