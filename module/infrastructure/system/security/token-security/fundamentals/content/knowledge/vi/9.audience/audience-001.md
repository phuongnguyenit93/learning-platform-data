# Audience giới hạn nơi token được dùng

Giả sử ứng dụng có hai API: **Orders API** quản lý đơn hàng và **Payments API** quản lý thanh toán. Client nhận được access token hợp lệ để gọi Orders API, rồi thử chuyển nguyên token đó sang Payments API. Dù token chưa hết hạn, chữ ký hoàn toàn đúng và cùng một Authorization Server phát hành cho cả hệ thống, **Payments API vẫn phải từ chối nếu token không được cấp cho Payments API**.

Ranh giới ấy được thể hiện qua khái niệm **audience**: bên hoặc nhóm bên mà token được dự định sử dụng. Trong JWT, audience thường xuất hiện dưới claim **aud**. Khi sử dụng đúng, audience ngăn một token phát hành cho dịch vụ A bị chấp nhận nhầm tại dịch vụ B. Đây là một lớp bảo vệ thiết yếu trong mô hình tin cậy, cùng với **issuer**, **chữ ký**, **thời hạn**, **scope** và chính sách phân quyền trên tài nguyên.

Bài học thuộc chương **Audience** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung gắn với vòng đời token bảo mật trong OAuth 2.0/OIDC, phân biệt JWT và opaque access token, phân quyền ở Resource Server, thu hồi và rủi ro khi bearer token bị đánh cắp hoặc chuyển tiếp sai nơi nhận.

Sau bài học, bạn có thể:

- Giải thích **audience định danh nơi được phép nhận token**, khác với issuer, subject, client ID và scope.
- Hiểu cách claim **aud** được biểu diễn và Resource Server cần kiểm tra nó như thế nào.
- Phân biệt audience của **OAuth access token** và **OIDC ID token**.
- Thiết kế luồng cấp token cho đúng API, kể cả API gọi API, multi-tenant và token có nhiều audience.
- Phát hiện lỗi **token substitution**, **confused deputy** và việc dùng lại token của dịch vụ khác.

## 1. Audience trả lời câu hỏi nào?

Trong hệ thống có token, các thông tin sau có nhiệm vụ khác nhau:

| Thông tin | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **Issuer – iss** | Ai phát hành token mà hệ thống đã chọn tin? | https://auth.example.org |
| **Subject – sub** | Token nói về chủ thể nào? | user-42 hoặc service-account-7 |
| **Client – client_id** | OAuth client nào được cấp token? | shop-web |
| **Audience – aud** | Token được dự định sử dụng ở đâu/cho ai? | orders-api |
| **Scope** | Token được cấp những phạm vi quyền nào? | orders:read |
| **Policy tài nguyên** | Chủ thể được thao tác với tài nguyên cụ thể không? | user-42 được xem order-900 của tenant T17 |

Với JWT, claim **aud** được định nghĩa trong RFC 7519. Giá trị có thể là **một chuỗi** hoặc **mảng các chuỗi** biểu thị các bên nhận dự kiến. Mỗi bên nhận JWT phải kiểm tra rằng chính mình được nhận diện trong audience; JWT có claim aud nhưng bên nhận không thuộc audience thì phải bị từ chối.

Ví dụ một payload JWT access token dành cho Orders API:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800,
  "jti": "example-token-901"
}
~~~

Đây là **payload minh họa**, không phải một token có chữ ký có thể sử dụng. Trong hệ thống thực tế, Resource Server còn phải kiểm tra định dạng/loại token, chữ ký hoặc introspection, issuer, thời gian hiệu lực và chính sách thu hồi. **aud=orders-api** nghĩa là token được định hướng tới Orders API theo hợp đồng của issuer và API; **không đồng nghĩa** rằng bất cứ ai cầm token đều có quyền xem tất cả đơn hàng.

Một JWT chỉ ký bằng JWS thường có payload **đọc được bằng Base64url-decoding**. Audience hạn chế **nơi token được chấp nhận**, không giấu nội dung token hay tự ngăn người khác sao chép bearer token.

## 2. Audience tạo ranh giới giữa các Resource Server

Trong OAuth 2.0, **Authorization Server** cấp access token; **client** mang token tới **Resource Server** để gọi tài nguyên được bảo vệ. Một Authorization Server có thể cấp token cho nhiều Resource Server. Vì vậy, chỉ biết token đến từ một issuer chung là **chưa đủ** để một API chấp nhận token.

~~~mermaid
flowchart LR
    AS["Authorization Server<br/>Issuer đáng tin cậy"] -->|"Access token: aud=orders-api"| C["Client"]
    C -->|"Bearer token"| O["Orders API"]
    C -.->|"Cùng token"| P["Payments API"]
    O --> V1["Kiểm chữ ký, iss, aud,<br/>scope và quyền order"]
    P --> V2["Kiểm aud: thiếu payments-api<br/>=> từ chối"]
~~~

Ví dụ có hai request cùng mang **một token**:

~~~http
GET /orders HTTP/1.1
Host: orders.example.org
Authorization: Bearer <access-token-for-orders-api>
~~~

~~~http
GET /payments HTTP/1.1
Host: payments.example.org
Authorization: Bearer <access-token-for-orders-api>
~~~

Giả sử hai API đều tin **https://auth.example.org**. Đối với Orders API, aud=orders-api có thể hợp lệ. Đối với Payments API, **audience không khớp** nên token bị từ chối **trước khi** xét quyền thanh toán. Một claim **scope=payments:read** nếu bị đưa nhầm vào token có aud=orders-api cũng **không làm token trở nên hợp lệ cho Payments API**.

Ranh giới này giảm rủi ro **cross-resource token reuse**: token lộ tại API hoặc client của một dịch vụ sẽ không tự trở thành credential dùng được ở dịch vụ khác nếu mỗi Resource Server thực thi audience đúng.

## 3. Audience được xác định lúc phát hành token như thế nào?

Audience là kết quả của **chính sách cấp token** và cấu hình giữa Authorization Server với Resource Server, không phải chuỗi tùy ý client tự khai rồi mặc nhiên có hiệu lực.

Trong OAuth 2.0, client có thể yêu cầu quyền truy cập cho tài nguyên cụ thể theo khả năng hỗ trợ của Authorization Server. **Resource Indicators for OAuth 2.0 (RFC 8707)** định nghĩa tham số **resource** để diễn đạt tài nguyên được yêu cầu tại authorization request hoặc token request trong những flow hỗ trợ. Authorization Server phải quyết định tài nguyên nào được phép cấp và token dành cho tài nguyên nào.

Ví dụ minh họa một yêu cầu ủy quyền có resource indicator, bỏ qua các tham số bổ sung của OAuth flow để tập trung vào ý nghĩa:

~~~text
resource=https://api.example.org/orders
scope=orders:read
client_id=shop-web
~~~

Authorization Server có thể ánh xạ resource indicator **https://api.example.org/orders** thành định danh audience logic **orders-api** trong access token nếu đó là hợp đồng đã thống nhất. Không có quy tắc chung rằng giá trị **aud** phải luôn là URL, phải là chính xác giá trị **resource**, hoặc phải là hostname của request. Điều quan trọng là bên phát hành và Resource Server thống nhất định danh, còn Resource Server thực thi so khớp theo hợp đồng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant O as Orders API
    C->>AS: OAuth flow, yêu cầu resource=Orders, scope=orders:read
    AS->>AS: Kiểm client, quyền cấp và resource được phép
    AS-->>C: Access token với aud=orders-api
    C->>O: Bearer access token
    O->>O: Validate issuer, chữ ký, audience, thời hạn
    O->>O: Kiểm scope và quyền trên đơn hàng
    O-->>C: Kết quả phù hợp chính sách
~~~

Ba điểm dễ nhầm:

1. **Client ID không phải mặc định là audience của access token.** Client được cấp token; Resource Server mới là bên được dự kiến nhận access token.
2. **Scope không quyết định audience thay cho issuer.** Một chuỗi scope đặt tên theo dịch vụ không chứng minh token được cấp cho dịch vụ ấy.
3. **Resource indicator không tự cấp quyền.** Client có thể yêu cầu resource, nhưng Authorization Server phải xác thực, áp dụng chính sách cho client/chủ thể, từ chối hoặc thu hẹp yêu cầu không hợp lệ.

Không phải mọi Authorization Server đều triển khai RFC 8707. Các hệ thống khác có thể chọn audience dựa trên đăng ký client, API identifier, token endpoint hoặc chính sách cấp token. Dù cơ chế phát hành nào, **Resource Server vẫn phải biết audience hợp lệ của mình**.

## 4. Resource Server kiểm tra audience theo quy trình nào?

### 4.1. Với JWT access token tự chứa

Resource Server phải xác minh token theo profile đã chọn, không chỉ tìm một chuỗi trong payload. Quy trình điển hình:

1. **Xác định token được chấp nhận:** API chỉ dùng access token thuộc profile/issuer đã cấu hình; không chấp nhận ID token hoặc refresh token dùng nhầm ngữ cảnh.
2. **Xác minh nguồn:** kiểm tra chữ ký bằng khóa được tin của issuer, giới hạn thuật toán, xác minh claim **iss** khớp issuer cấu hình. Không tự tải key tùy ý theo URL do header token cung cấp.
3. **Xác minh audience:** lấy định danh audience từ cấu hình tin cậy của API (ví dụ **orders-api**) và kiểm tra nó xuất hiện hợp lệ trong claim **aud**.
4. **Kiểm tra hiệu lực:** kiểm tra **exp**, **nbf** (nếu có), chính sách đồng hồ và trạng thái thu hồi/key/issuer theo kiến trúc.
5. **Kiểm tra phân quyền:** so scope chính xác theo endpoint; xét subject, client, tenant, ownership và trạng thái tài nguyên trước khi cho phép.

Không lấy giá trị aud từ token để “cấu hình ngược” tên API đang nhận; verifier phải có **expected audience độc lập với token**. Nếu chính sách API đòi audience nhưng JWT thiếu **aud**, phải **từ chối**, không mặc nhiên coi token hợp lệ cho mọi dịch vụ.

Ví dụ pseudocode minh họa:

~~~text
verifyForOrdersApi(request):
    token = requireBearerAccessToken(request)
    if token missing:
        return 401

    verified = trustedJwtVerifier.verify(
        token,
        issuer = "https://auth.example.org",
        allowedAlgorithms = configuredAlgorithms,
        expectedTokenType = "access_token"
    )
    if verified invalid:
        return 401

    audiences = parseAudienceAsStringOrStringArray(verified.claims.aud)
    if audiences invalid or "orders-api" not in audiences:
        return 401

    if tokenExpiredOrNotYetValid(verified.claims):
        return 401

    if not hasExactScope(verified.claims.scope, "orders:read"):
        return 403

    resource = loadOrderWithTrustedTenantBoundary(request.orderId)
    if not hasCurrentRightToRead(verified.subject, resource):
        return 403

    return authorizedResponse(resource)
~~~

Đây là **pseudocode kiến trúc**, không phải thư viện JWT hoàn chỉnh. Triển khai thật nên dùng thư viện OAuth/JWT được duy trì để kiểm tra chữ ký, issuer, audience, profile và thời gian **như một chuỗi kiểm tra thống nhất**; chỉ sử dụng claims cho phân quyền sau khi token đã được xác minh.

### 4.2. Kiểu của aud và quy tắc so khớp

JWT có thể biểu diễn audience bằng chuỗi:

~~~json
{
  "aud": "orders-api"
}
~~~

hoặc mảng chuỗi:

~~~json
{
  "aud": ["orders-api", "reports-api"]
}
~~~

Theo RFC 7519, các giá trị audience là **chuỗi phân biệt chữ hoa/chữ thường**. Không dùng **contains substring**, tiền tố, hậu tố hoặc wildcard để so khớp. Nếu expected audience là **orders-api**, các giá trị **orders-api-v2**, **my-orders-api** hoặc **ORDERS-API** không tự động tương đương. Cũng không tự động loại dấu gạch chéo cuối hoặc chuyển đổi URL trước khi so khớp nếu hợp đồng không quy định.

Một token có **aud** dạng object, number hoặc mảng pha kiểu không đúng phải bị từ chối theo profile và policy. Nếu hệ thống yêu cầu **duy nhất một audience**, một token có nhiều audience có thể bị từ chối ngay cả khi chứa audience của API; đây là chính sách chặt hơn, cần được áp dụng nhất quán giữa nơi cấp và nơi nhận.

### 4.3. Với opaque access token

Opaque access token không công bố claims để Resource Server tự giải mã. API thường gọi **OAuth 2.0 Token Introspection (RFC 7662)** hoặc nguồn kiểm tra trạng thái đáng tin. Ví dụ phản hồi:

~~~json
{
  "active": true,
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Trong RFC 7662, **active** là trường cốt lõi; những metadata khác, gồm **aud**, có thể tùy chọn ở cấp giao thức. Tuy nhiên, **không có aud trong phản hồi không đồng nghĩa token được sử dụng ở mọi API**. Resource Server phải có **bằng chứng ràng buộc token với chính API của nó**: thông qua aud được issuer trả về, chính sách introspection có ràng buộc Resource Server, hoặc một cơ chế tin cậy tương đương được thỏa thuận và kiểm chứng. Nếu không chứng minh được điều kiện audience cần thiết, phải từ chối.

Một introspection trả HTTP 200 và **active=true** không tự cho phép đọc mọi tài nguyên; API vẫn kiểm scope, chủ thể, tenant và policy hiện hành. Nếu introspection lỗi hoặc mất tin cậy, không **fail open** bằng cách bỏ qua audience.

## 5. Audience của access token và ID token trong OIDC khác nhau

Đây là một lỗi phổ biến: một ứng dụng nhận **OIDC ID token** để xác nhận đăng nhập, sau đó đem ID token gọi API nghiệp vụ vì nó có **sub**, **iss** và chữ ký hợp lệ.

| Token | Ai là bên nhận dự kiến? | aud thường đại diện cho gì? | Cách sử dụng |
|---|---|---|---|
| **OAuth access token** | Resource Server/API | Định danh API hoặc resource được cấp quyền | Client gửi đến API qua cơ chế phù hợp, ví dụ Bearer |
| **OIDC ID token** | Client/Relying Party | **client_id** của ứng dụng nhận kết quả xác thực | Client xác minh người dùng đăng nhập, không dùng làm access token cho API |
| **Refresh token** | Authorization Server/token endpoint | Không áp bộ quy tắc audience của access token lên chuỗi opaque refresh token tùy tiện | Xin access token mới theo flow hợp lệ |

Ví dụ:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "shop-web",
  "iat": 1899999000,
  "exp": 1900000800
}
~~~

Payload này minh họa audience của một **ID token** dành cho client **shop-web**; không phải token gọi Orders API. OIDC có thêm những quy tắc như **azp**, **nonce**, **auth_time** tùy flow và ngữ cảnh. Việc ID token hợp lệ với client **không cho Orders API quyền chấp nhận nó**. Orders API cần access token được cấp cho chính API, kiểm tra đúng loại token và audience.

Nếu hệ thống dùng JWT cho cả ID token lẫn access token, cần ngăn **cross-JWT confusion** bằng token type/profile rõ ràng và validation độc lập. Ví dụ, profile JWT access token RFC 9068 sử dụng kiểu token **at+jwt** theo quy tắc của profile; các thành phần xác minh phải áp dụng đúng ngữ cảnh thay vì chấp nhận “JWT nào có chữ ký hợp lệ”.

## 6. Một token có nhiều audience có luôn là lựa chọn tốt?

Một access token có thể được cấp cho nhiều Resource Server:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": ["orders-api", "reports-api"],
  "scope": "orders:read reports:read",
  "exp": 1900000800
}
~~~

Theo định dạng JWT, mảng audience là hợp lệ; việc **có cho phép multi-audience hay không** phụ thuộc chính sách của Authorization Server và Resource Server. Nếu cả hai API đều xác minh aud đúng, một token như vậy có thể được chấp nhận ở cả hai nơi.

Nhưng khả năng tái sử dụng rộng hơn cũng tạo rủi ro:

- **Vùng ảnh hưởng khi bearer token bị lộ lớn hơn:** bản sao token có thể được dùng ở nhiều API thay vì một.
- **Khó áp dụng đặc quyền tối thiểu:** khi scope lẫn giữa các API, mỗi API phải xử lý chặt scope của chính mình và quyền theo đối tượng.
- **Khó cô lập sự cố:** thu hồi token hoặc một audience có thể ảnh hưởng các API khác; cache và cơ chế revoke phải được xem xét chung.
- **Dễ chuyển tiếp token bừa bãi:** client hoặc service có thể nghĩ rằng mọi API đều nên nhận cùng một token, rồi làm token xuất hiện ở nhiều log và thành phần hơn.

Nếu nghiệp vụ không đòi multi-audience, **access token gắn với một Resource Server cụ thể** thường làm ranh giới tin cậy và blast radius dễ kiểm soát hơn. Trường hợp cần nhiều audience phải có lý do rõ ràng, chính sách issuer minh bạch và kiểm tra từng API độc lập. Dù aud chứa nhiều giá trị, **scope vẫn không tự cấp quyền với mọi bản ghi**.

## 7. Khi một API cần gọi API khác: không chuyển tiếp token tùy tiện

Giả sử người dùng gọi **Orders API** bằng token có aud=orders-api. Orders API cần gọi **Payments API** để lấy trạng thái thanh toán. Nếu Orders API chuyển nguyên bearer token của người dùng sang Payments API, token đó **không có audience payments-api** và phải bị từ chối.

Thiết kế thường có hai lựa chọn, tùy ngữ cảnh:

1. **API gọi API bằng danh tính của chính dịch vụ:** Orders API dùng cơ chế client credentials hoặc service identity để nhận một access token dành cho **payments-api**, với quyền máy phù hợp. Payments API phân quyền chủ thể là dịch vụ, không tự hiểu token này là người dùng cuối.
2. **API gọi thay mặt người dùng:** sử dụng một cơ chế ủy quyền trung gian hoặc **OAuth 2.0 Token Exchange (RFC 8693)** khi hệ thống hỗ trợ, nhận token mới có audience **payments-api** và quyền được giới hạn. Resource Server đích phải xác minh token mới, ngữ cảnh ủy quyền và quan hệ ủy nhiệm theo hợp đồng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orders API
    participant AS as Authorization Server
    participant P as Payments API
    C->>O: Token A (aud=orders-api)
    O->>AS: Xin token phù hợp cho Payments API
    AS->>AS: Kiểm chính sách client, resource, delegation
    AS-->>O: Token B (aud=payments-api)
    O->>P: Token B
    P->>P: Kiểm aud, scope, issuer và policy
    P-->>O: Kết quả được phép
~~~

Token Exchange **không phải quyền mặc nhiên** để một dịch vụ đổi lấy bất kỳ audience nào. Authorization Server phải quyết định liệu caller được đại diện cho người dùng, dùng scope nào và cấp token đến Resource Server nào. Các điều kiện như consent, chủ thể và actor có thể cần được thể hiện theo profile đã chọn.

Nếu microservice dùng cùng một token khắp mạng nội bộ chỉ vì “đã qua gateway”, ranh giới audience bị suy yếu. Các service nhận token nên thực thi validation phù hợp, kể cả khi hệ thống có gateway kiểm tra bước đầu.

## 8. Audience không thay thế phân quyền hay bảo vệ token

Audience là điều kiện **nơi token được chấp nhận**, còn phân quyền nghiệp vụ trả lời **yêu cầu cụ thể có được phép không**.

Ví dụ token có:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Orders API có thể xác nhận token dành cho mình và được cấp scope đọc đơn hàng, nhưng vẫn cần kiểm tra:

- Đơn hàng có thuộc **tenant** mà user-42 đang là thành viên không?
- User-42 có quyền xem đơn hàng đó theo **owner, role hoặc relationship** không?
- Tài khoản còn hoạt động, quyền đã bị thu hồi hoặc tài nguyên đã chuyển trạng thái chưa?
- Endpoint có giới hạn dữ liệu nhạy cảm theo thuộc tính hoặc quyền bổ sung không?

Nếu câu trả lời không thỏa chính sách, phải từ chối ngay cả khi aud, issuer, thời gian và scope đều đúng. **audience không phải tenant ID**, không đại diện cho người sở hữu bản ghi, và không xác nhận một người dùng còn quyền tại thời điểm hiện tại.

Audience cũng **không chống token bị đánh cắp hoặc replay** trong phạm vi API đích. Người có được bearer access token dành cho orders-api vẫn có thể gọi Orders API theo quyền và thời hạn token nếu không có biện pháp bổ sung. Các lớp bảo vệ tiếp theo gồm HTTPS, nơi lưu token an toàn, access token sống ngắn, không ghi token vào log/URL, thu hồi và cơ chế sender-constrained như DPoP/mTLS khi phù hợp. 

## 9. Lỗi bảo mật thường gặp khi xử lý audience

### 9.1. So khớp audience bằng chuỗi con

Sai:

~~~text
if token.aud contains "orders":
    allow()
~~~

Cách này có thể vô tình cho phép aud=**orders-test**, **orders-admin** hoặc **my-orders-app**. Phải kiểm tra **giá trị audience chính xác** trong tập giá trị hợp lệ của API, tuân thủ kiểu claim string/mảng string và chính sách phân biệt hoa thường.

### 9.2. Chỉ kiểm issuer và chữ ký

Nếu Orders API và Payments API cùng tin một issuer, token dành cho Orders API cũng qua bước kiểm chữ ký tại Payments API. Không kiểm audience dẫn đến nguy cơ **token substitution** giữa các Resource Server. Chữ ký đúng chứng minh phù hợp key tin cậy; **không chứng minh token được cấp cho mọi API mà issuer quản lý**.

### 9.3. Dùng client_id hoặc scope làm audience

**client_id=shop-web** cho biết client được cấp token; **scope=orders:read** là phạm vi quyền; cả hai **không phải** bằng chứng rằng token được cấp cho Resource Server. Đừng suy aud từ tên scope hoặc giả định mọi token do shop-web nhận đều dùng được ở mọi API.

### 9.4. Coi header Host/URL request là audience tự động

Audience có thể là URI, chuỗi định danh logic hoặc tập giá trị đã đăng ký. Hostname, route, path và các proxy rewrite không nhất thiết trùng aud. Hợp đồng phải quy định **expected audience** độc lập với dữ liệu client tự gửi như Host header, query parameter hoặc URL tùy biến; không tự “sửa” aud để khớp request.

### 9.5. Nhận token của môi trường khác

Token cấp cho **orders-api-staging** không được dùng ở **orders-api-production** chỉ vì chữ ký có thể kiểm bằng key chung hoặc issuer dùng chung. Tách audience, chính sách issuer/khóa, các tầng triển khai và kiểm thử negative case cho môi trường khác nhau.

### 9.6. Chỉ kiểm audience tại gateway

Gateway có thể chặn sớm token sai audience. Nhưng nếu API có đường gọi nội bộ, worker, batch, hoặc route khác bỏ qua gateway, sẽ tồn tại đường vòng. Tại những điểm nhận token độc lập, **Resource Server vẫn phải xác minh ranh giới tin cậy của chính mình** hoặc dựa trên một cơ chế xác thực nội bộ được thiết kế rõ và không thể bị caller giả mạo.

### 9.7. Coi introspection active=true là đủ

Opaque token được introspect có thể còn hiệu lực nhưng dành cho API khác. Khi introspection không có metadata audience, Resource Server cần cơ chế ràng buộc được Authorization Server bảo đảm; không để thiếu aud trở thành “wildcard”.

### 9.8. Tin JWT ID token để gọi API

ID token có aud là client ID theo OIDC; sử dụng nó như access token làm sai ranh giới người nhận và mục đích. Resource Server phải nhận **đúng loại token**, đúng issuer, đúng audience và đúng profile.

## 10. Ví dụ kiểm tra ranh giới audience trong ứng dụng đa dịch vụ

Giả sử hệ thống có:

| Thành phần | Issuer tin cậy | Expected audience | Scope cho thao tác |
|---|---|---|---|
| Orders API | https://auth.example.org | **orders-api** | orders:read, orders:write |
| Payments API | https://auth.example.org | **payments-api** | payments:read, payments:charge |
| Reports API | https://auth.example.org | **reports-api** | reports:read |
| Shop web client | https://auth.example.org | **shop-web** trong ID token | Dùng ID token để xác minh đăng nhập |

Các trường hợp kiểm thử:

| Tình huống | Kết quả mong đợi |
|---|---|
| JWT access token ký đúng, aud=orders-api, gọi Orders API, đủ quyền trên order | **Cho phép** |
| Cùng token được gửi sang Payments API | **Từ chối token** do sai audience |
| aud=orders-api-v2, gọi Orders API chỉ cho phép orders-api | **Từ chối token** |
| aud=["orders-api","reports-api"], gọi Orders API khi policy cho phép multi-audience | **Qua bước audience**, còn phải kiểm scope và quyền |
| aud mảng chứa orders-api nhưng policy chỉ chấp nhận single-audience | **Từ chối token** theo hợp đồng |
| aud thiếu hoặc sai kiểu trong profile yêu cầu aud | **Từ chối token** |
| JWT đúng audience nhưng sai issuer hoặc chữ ký | **Từ chối token** |
| JWT đúng audience nhưng hết hạn | **Từ chối token** |
| JWT đúng audience nhưng thiếu scope orders:read | **Từ chối phân quyền** |
| JWT đúng audience/scope, order thuộc tenant khác | **Từ chối phân quyền** |
| OIDC ID token có aud=shop-web gửi vào Orders API | **Từ chối token** vì sai mục đích/audience |
| Opaque token active=true nhưng chỉ được cấp cho payments-api | **Từ chối tại Orders API** |
| Introspection hoặc nơi xác minh không truy cập được, không có thông tin tin cậy | **Không fail open** |

Với Bearer token, thiếu hoặc không hợp lệ thường dẫn đến **HTTP 401 Unauthorized** và header WWW-Authenticate phù hợp; token hợp lệ nhưng thiếu quyền/scope thường dẫn đến **HTTP 403 Forbidden**. Resource Server có thể trả 404 khi chính sách cần che giấu sự tồn tại tài nguyên, nhưng điều đó không thay thế kiểm tra audience. Không làm lộ toàn bộ claims hoặc bearer token trong thông báo lỗi.

Đặc biệt, test phải đi đến **điểm bảo vệ dữ liệu**: xác nhận token sai audience không nhận được dữ liệu và không tạo side effect, kể cả qua đường nội bộ hoặc yêu cầu bất đồng bộ.

## 11. Checklist khi thiết kế audience

Trước khi phát hành hoặc chấp nhận access token, hãy trả lời:

1. **Resource Server được định danh bằng gì?** URI, API identifier hay một chuỗi logic ổn định? Giá trị expected audience được cấu hình ở đâu?
2. **Issuer quyết định audience theo chính sách nào?** Client được phép yêu cầu resource nào; có hỗ trợ RFC 8707 resource indicators không?
3. **Mỗi Resource Server có tự kiểm tra aud không?** Có đường vòng qua gateway, region hoặc luồng nội bộ không?
4. **Đã phân biệt ID token và access token chưa?** Audience của OIDC ID token phải dùng cho client, không phải để mở quyền API.
5. **Có cho phép multi-audience không?** Nếu có, vì sao cần và ảnh hưởng khi bearer token bị lộ ở một API là gì?
6. **Token được chuyển tiếp giữa API thế nào?** Có cần service token hoặc Token Exchange theo ngữ cảnh thay vì chuyển nguyên access token của API trước?
7. **Scope và quyền tài nguyên được kiểm tra riêng chưa?** Đúng audience không thể thay cho kiểm tra tenant, owner hay policy.
8. **Nếu token là opaque, ràng buộc audience được chứng minh từ đâu?** Introspection có aud hay có hợp đồng ràng buộc đáng tin khác?
9. **Cấu hình có tách môi trường và issuer/key phù hợp không?** Token test hoặc staging có bị chấp nhận nhầm tại production không?
10. **Các trường hợp lỗi đã được kiểm thử chưa?** Thiếu aud, aud sai kiểu, aud giống một phần, token sai resource, sai issuer, token hết hạn, thiếu scope và quyền tài nguyên bị thu hồi.

**Audience là một phần của hợp đồng tin cậy giữa Authorization Server và Resource Server**. Nó cần được thiết kế tại lúc phát hành, xác minh tại mỗi điểm nhận và duy trì nhất quán khi triển khai, đổi tên API, xoay issuer/key hoặc bổ sung luồng ủy quyền.

## 12. Câu hỏi tự đánh giá

**1. Issuer và chữ ký hợp lệ có đủ để Payments API nhận token của Orders API không?** Không. Payments API còn phải xác nhận chính mình thuộc audience được cấp.

**2. aud có luôn bằng URL Host của request không?** Không. Audience là identifier theo hợp đồng của issuer và Resource Server; có thể là URI hoặc tên logic. Host header không được tự biến thành nguồn chân lý.

**3. Access token có scope payments:read nhưng aud=orders-api thì Payments API có được chấp nhận không?** Không. Scope không thay thế giới hạn audience.

**4. JWT có aud=["orders-api","reports-api"] có sai định dạng JWT không?** Không. Mảng chuỗi là cách biểu diễn được JWT hỗ trợ. Nhưng policy của hệ thống có thể cấm multi-audience để giữ token đúng một Resource Server.

**5. OIDC ID token có aud=shop-web thì Orders API có nên nhận không?** Không. ID token được cấp cho client để xác minh danh tính, còn Orders API phải nhận access token dành cho mình.

**6. Opaque token introspection active=true nhưng không có aud thì API làm gì?** Phải có một cơ chế đáng tin khác chứng minh token được dành cho API; nếu không có bằng chứng thì từ chối.

**7. Audience có ngăn kẻ tấn công dùng lại bearer token tại đúng API đích không?** Không. Audience chỉ giới hạn nơi nhận; cần bảo vệ token, thu hồi, thời hạn ngắn và sender-constraining khi phù hợp để giảm rủi ro bị đánh cắp/phát lại.

**8. Orders API nên làm gì để gọi Payments API thay mặt người dùng?** Dùng cơ chế được ủy quyền phù hợp, có thể là token exchange nếu hệ thống hỗ trợ, để nhận token mới dành cho Payments API với quyền giới hạn. Không tự chuyển tiếp token aud=orders-api và đòi Payments API bỏ qua audience.

**Ghi nhớ:** **Audience giới hạn nơi token được dùng; issuer xác định nguồn phát hành, scope giới hạn quyền được cấp, policy quyết định truy cập tài nguyên.** Resource Server phải chấp nhận **đúng loại token, đúng issuer, đúng audience, còn hiệu lực và đủ quyền**. Mỗi API cần kiểm ranh giới của chính mình để token bị lộ hoặc bị chuyển tiếp sai nơi không trở thành chìa khóa dùng chung cho toàn hệ thống.
