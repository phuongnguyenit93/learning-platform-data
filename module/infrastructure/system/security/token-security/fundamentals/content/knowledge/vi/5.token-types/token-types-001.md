# Access token và phạm vi sử dụng

## Mục tiêu học tập

Trong chương **Token types** của học phần bảo mật token, **access token** là thông tin mà một ứng dụng (client) trình cho API để yêu cầu truy cập tài nguyên theo quyền đã được cấp. Bản thân việc sở hữu một token **không đồng nghĩa** với quyền truy cập mọi API, mọi thao tác hay mọi bản ghi.

Sau bài học, bạn có thể:

1. Giải thích chức năng của access token trong OAuth 2.0/OIDC, phân biệt nó với **ID token**, **refresh token** và **authorization code**.
2. Phân biệt ba trục độc lập: **mục đích token** (access/refresh/ID), **định dạng** (JWT/opaque) và **cách sử dụng** (bearer/sender-constrained).
3. Hiểu cách **scope**, **audience** và **thời hạn hiệu lực** giới hạn phạm vi sử dụng token; nhận ra tại sao scope không thay thế quyền trên tài nguyên.
4. Mô tả yêu cầu kiểm tra access token ở Resource Server, xử lý lỗi 401/403, lưu trữ an toàn, làm mới và thu hồi token.
5. Phân tích tình huống token bị đưa nhầm API, bị lấy cắp/phát lại hoặc có quyền rộng hơn nhu cầu.

## 1. Access token trả lời câu hỏi gì?

Một **access token** đại diện cho quyền truy cập đã được hệ thống cấp theo một luồng ủy quyền thích hợp. **Client** gửi access token đến **Resource Server** (API) để chứng minh yêu cầu có một căn cứ ủy quyền; API vẫn phải xác minh token và áp dụng chính sách phân quyền của chính mình.

Ví dụ, ứng dụng bán hàng lấy access token để xem danh sách đơn:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN_PLACEHOLDER>
~~~

Khi tiếp nhận, `orders-api` cần trả lời ít nhất:

- Token có do **Authorization Server được tin cậy** phát hành và còn hiệu lực không?
- Token có **dành cho orders-api** không?
- Token có phạm vi được phép gọi thao tác **đọc đơn hàng** không?
- Người dùng hoặc dịch vụ đứng sau token có quyền đọc **những đơn hàng cụ thể** nào?

Nếu thiếu một điều kiện bắt buộc, API phải từ chối. Token không phải một “thẻ toàn năng”; nó chỉ hữu ích trong **ranh giới tin cậy và quyền** mà nơi phát hành và nơi nhận thống nhất.

### Ba trục dễ nhầm lẫn

| Trục phân loại | Các ví dụ | Câu hỏi nó trả lời |
|---|---|---|
| **Mục đích** | Access token, refresh token, ID token | Token được dùng để làm gì và gửi đến thành phần nào? |
| **Định dạng** | JWT, opaque token | Token mang dữ liệu có cấu trúc tự kiểm tra được hay là chuỗi cần tra cứu? |
| **Cách chứng minh quyền sử dụng** | Bearer, sender-constrained | Chỉ cần sở hữu token là dùng được, hay phải chứng minh thêm quyền sở hữu khóa/chứng chỉ? |

Một access token có thể là **JWT dạng bearer**, **opaque dạng bearer**, hoặc được **ràng buộc với người gửi**. Không thể suy ra quyền từ việc chuỗi token có các dấu chấm, decode được JSON hoặc bắt đầu bằng một prefix.

## 2. Access token nằm ở đâu trong OAuth 2.0/OIDC?

**OAuth 2.0** định nghĩa khung ủy quyền để client truy cập tài nguyên thay mặt một chủ thể hoặc với danh tính dịch vụ trong phạm vi được phép. **OIDC** bổ sung lớp xác thực danh tính người dùng trên OAuth 2.0, thường liên quan đến **ID token**. Trong cả hai trường hợp, token trình cho **API tài nguyên** là **access token** phù hợp với API đó.

Các vai trò quan trọng:

| Vai trò | Nhiệm vụ |
|---|---|
| **Resource Owner** | Chủ thể kiểm soát tài nguyên; thường là người dùng trong luồng có người dùng. |
| **Client** | Ứng dụng muốn truy cập tài nguyên: web, mobile hoặc backend service. |
| **Authorization Server (AS)** | Xác thực/ủy quyền theo luồng tương ứng và phát hành token cho client. |
| **Resource Server (RS)** | API tiếp nhận và kiểm tra access token để bảo vệ dữ liệu và thao tác. |

Ví dụ luồng **Authorization Code với PKCE** cho ứng dụng có người dùng:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant API as Orders API
    U->>C: Mở chức năng xem đơn
    C->>AS: Authorization request + scope + PKCE challenge
    AS->>U: Xác thực và lấy quyết định ủy quyền khi cần
    AS-->>C: Authorization code
    C->>AS: Đổi code + PKCE verifier tại token endpoint
    AS-->>C: Access token (+ refresh token nếu được cấp)
    C->>API: GET /orders, Authorization: Bearer <access_token>
    API->>API: Xác minh token, audience, scope và quyền trên đơn
    API-->>C: Chỉ trả dữ liệu được phép
~~~

Luồng `client_credentials` là ví dụ khác: client là một ứng dụng/dịch vụ được cấp token cho chính nó, không nhất thiết có người dùng cuối. Khi phân quyền, API cần biết token đại diện cho **người dùng, service principal hay một loại chủ thể khác** theo hợp đồng token và grant. Không được mặc định mọi `sub` là user ID.

### Xin scope không đồng nghĩa được cấp scope

Client có thể yêu cầu:

~~~text
scope=orders:read orders:write
~~~

AS phải quyết định **phạm vi được cấp thực tế**, căn cứ client, tài nguyên, chính sách và sự đồng ý của Resource Owner khi áp dụng. Phạm vi cấp có thể **hẹp hơn** phạm vi được yêu cầu. Client không được cho rằng nó luôn nhận được toàn bộ quyền mà nó xin; API phải dựa trên token đã xác minh, không dựa vào request cấp token ban đầu.

Các luồng OAuth 2.0 khác nhau có thể có cách cấp token, điều kiện tương tác người dùng và khả năng cấp refresh token khác nhau. Không tự suy rằng cứ đăng nhập thành công là bắt buộc có refresh token.

## 3. Scope: token được phép yêu cầu những thao tác nào?

**Scope** (phạm vi ủy quyền) mô tả các giới hạn quyền mà token được cấp. Trong OAuth 2.0, các scope thường biểu diễn thành những chuỗi phân tách bằng dấu cách. Tên scope và ý nghĩa chính xác do hệ thống phát hành và bảo vệ tài nguyên thỏa thuận; **không tồn tại một danh sách scope chuẩn toàn cục cho mọi API**.

Ví dụ quy ước của một ứng dụng:

| Scope | Ý nghĩa theo hợp đồng của `orders-api` |
|---|---|
| `orders:read` | Yêu cầu đọc các đơn mà principal có quyền xem. |
| `orders:write` | Yêu cầu tạo/sửa các đơn được phép thao tác, tùy chính sách. |
| `orders:cancel` | Yêu cầu hủy đơn nếu principal được phép và trạng thái đơn cho phép. |
| `payments:refund` | Yêu cầu hoàn tiền trên API thanh toán, cần chính sách và audience tương ứng. |

Scope **không phải** một lời cam kết rằng mọi request trong nhóm thao tác đó sẽ được cho phép. Ví dụ:

~~~text
Token có: scope = "orders:read", sub = "user-123", tenant = "tenant-a"
Request:   GET /orders/42
Order 42:  ownerId = "user-999", tenant = "tenant-b"
Kết quả:   DENY, trừ khi có chính sách ủy quyền riêng hợp lệ.
~~~

Token đáp ứng yêu cầu tổng quát “đọc đơn” nhưng **không vượt qua** kiểm tra quyền sở hữu và ranh giới tenant. Từ góc nhìn mô hình bảo mật, cần phân biệt:

- **Scope:** việc truy cập API được cấp trong phạm vi nào.
- **Role/permission:** principal có vai trò hay quyền nghiệp vụ gì, có thể đến từ token đáng tin hoặc kho chính sách hiện hành.
- **Object-level authorization:** principal được làm gì trên **tài nguyên cụ thể** như order 42.
- **Context:** điều kiện bổ sung như trạng thái đơn, giới hạn tenant hoặc bước xác thực bổ sung.

Khi đặt tên scope, ưu tiên tên thể hiện **tài nguyên + hành động**, thống nhất giữa AS, client và RS. Tránh cấp scope quá rộng như `admin` cho một chức năng chỉ cần xem lịch sử đơn. Các chuỗi scope trong OAuth có tính phân biệt chữ hoa/chữ thường theo chuẩn; cách so sánh “gần giống”, chứa chuỗi con hoặc tự động mở rộng không được thay cho so khớp theo hợp đồng.

### Một cách kiểm tra quyền đúng hướng

~~~text
if token is not valid for this resource server:
    deny as unauthenticated

if "orders:read" not in grantedScopes(token):
    deny insufficient_scope

order = loadOrder(orderId)
if not canRead(principalFromVerifiedToken, order):
    deny forbidden

return authorizedOrderFields(order)
~~~

**Không dùng** role, scope hoặc user ID mà client tự gửi trong JSON body hay query string làm căn cứ quyết định. Các giá trị kiểm tra quyền phải đến từ token đã xác minh và những nguồn chính sách đáng tin cậy.

## 4. Audience: token dành cho API nào?

**Audience** xác định đối tượng được phép tiếp nhận token. Trong JWT, claim `aud` thường mang audience dưới dạng chuỗi hoặc mảng, tùy profile. Với opaque token, audience có thể do AS trả qua introspection hoặc cơ chế tra cứu nội bộ. Không phải mọi access token đều chứa claim JWT vì **không phải mọi access token đều là JWT**.

Giả sử cùng một AS phát hành token cho hai API:

~~~text
Access token A: aud = "orders-api",  scope = "orders:read"
Access token B: aud = "billing-api", scope = "payments:refund"
~~~

Token A được cấp cho `orders-api`. Nếu ứng dụng mang token A đến `billing-api`, billing API phải **từ chối**, kể cả khi token A được ký bởi AS mà billing API cũng tin cậy. Chữ ký chỉ hỗ trợ xác nhận nguồn phát hành/toàn vẹn; nó **không chuyển quyền sử dụng** token sang một đối tượng nhận khác.

~~~mermaid
flowchart LR
    AS["Authorization Server"] --> A["Token A: aud orders-api"]
    AS --> B["Token B: aud billing-api"]
    A --> Orders["Orders API: xác minh và xét quyền"]
    A -. sai audience .-> Billing["Billing API: từ chối A"]
    B --> Billing
~~~

### Audience và scope bổ sung cho nhau

| Kiểm tra | Ý nghĩa | Khi thiếu |
|---|---|---|
| **Issuer/nguồn phát hành** | Ai là bên được API tin để cấp token? | Chuỗi có thể là token giả hoặc của tổ chức khác. |
| **Audience** | API hiện tại có phải người nhận được cấp phép không? | Dễ xảy ra **token substitution/confusion** giữa dịch vụ. |
| **Scope** | Token được quyền yêu cầu những loại hành động nào? | Token hợp lệ có thể bị dùng ngoài phạm vi ủy quyền. |
| **Quyền trên tài nguyên** | Principal được tác động đến dữ liệu cụ thể không? | Dễ xảy ra **BOLA/IDOR** và truy cập chéo tenant. |

Trong OAuth 2.0, **Resource Indicators** (RFC 8707) cho phép client chỉ rõ tài nguyên đích khi xin token, nếu AS hỗ trợ. Trong kiến trúc nhiều API, nên cấp token giới hạn cho tài nguyên cần thiết thay vì mặc định một access token dùng ở mọi nơi. Một token có nhiều audience chỉ nên được chấp nhận nếu hệ thống **cố ý hỗ trợ và kiểm soát đầy đủ** trường hợp ấy.

Khi backend cần gọi API tiếp theo, không được tự tiện chuyển tiếp access token đầu vào sang API khác. Có thể cần token riêng, luồng cấp quyền cho dịch vụ, hoặc **token exchange** được AS hỗ trợ, với audience và scope mới đúng mục đích.

## 5. Access token khác refresh token và ID token ra sao?

| Tiêu chí | **Access token** | **Refresh token** | **ID token (OIDC)** |
|---|---|---|---|
| **Dùng để** | Gọi Resource Server/API theo quyền được cấp. | Xin access token mới tại token endpoint. | Cho **client** biết kết quả xác thực của người dùng. |
| **Nơi nhận** | API có audience phù hợp. | Authorization Server/token endpoint. | Client OIDC được chỉ định. |
| **Thời hạn** | Thường ngắn để giảm cửa sổ lạm dụng; tùy chính sách. | Có thể dài hơn, có điều kiện rotation/hết hạn/thu hồi. | Theo chính sách phiên xác thực OIDC. |
| **Nội dung** | JWT hoặc opaque; có thể mang hoặc tham chiếu tới scope, audience. | Thường là bí mật do AS quản lý; không nên suy diễn cấu trúc. | JWT với claims xác thực OIDC theo profile. |
| **Không nên làm** | Dùng tại API không được cấp audience. | Gửi trực tiếp cho API nghiệp vụ. | Dùng thay access token để API quyết định cấp quyền. |

**Authorization code** còn khác ba loại trên: đó là mã ngắn hạn dùng một lần trong luồng ủy quyền để client đổi lấy token tại token endpoint. Không gửi authorization code cho API như access token.

Một lỗi phổ biến là “ID token cũng là JWT, lại chứa `sub` và `email`, vậy có thể dùng để gọi API”. Kết luận này sai vì **ID token dành cho client** và có audience/mục đích khác. Tương tự, refresh token có giá trị lớn trong việc kéo dài phiên nhưng **không phải quyền trực tiếp gọi API**.

## 6. Dạng JWT và opaque ảnh hưởng việc API xác minh thế nào?

### Access token JWT

JWT có thể mang các claims để API xác minh cục bộ bằng chữ ký đáng tin cậy. Ví dụ **payload minh họa**, không phải token thật:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Các trường cần hiểu:

- `iss`: issuer. API phải so sánh với nơi phát hành **được cấu hình tin cậy**.
- `sub`: principal/chủ thể mà token mô tả; có thể là người dùng hoặc dịch vụ tùy luồng.
- `aud`: API/đối tượng nhận được phép chấp nhận token.
- `scope`: phạm vi ủy quyền được cấp; cách biểu diễn có thể tùy profile.
- `iat`, `nbf`, `exp`: thời điểm phát hành, chưa có hiệu lực trước thời điểm nhất định, và hết hiệu lực (Unix time).
- `client_id`: client được cấp token; không thay thế danh tính người dùng.

**Giải mã Base64URL không phải xác minh JWT.** API phải kiểm tra chữ ký bằng khóa phù hợp thuộc issuer tin cậy, giới hạn thuật toán được phép, kiểm tra issuer/audience/thời gian/mục đích rồi mới sử dụng claims để phân quyền. Không tự tin URL cung cấp khóa hoặc thuật toán do token yêu cầu khi nguồn đó chưa được tin cậy.

Đặc biệt, JWT dạng JWS ký thông thường **không mã hóa payload**. Không nhét mật khẩu, thông tin thanh toán hay bí mật vào claims với giả định người nhận duy nhất mới đọc được. Chữ ký bảo vệ tính toàn vẹn và nguồn gốc trong mô hình tin cậy tương ứng, **không tự đảm bảo bí mật**.

### Access token opaque

Opaque token là chuỗi mà client và API không nên tự suy diễn quyền từ hình thức. API có thể xác minh thông qua kho trạng thái được kiểm soát hoặc **token introspection** (RFC 7662) của AS, rồi kiểm tra trạng thái `active` và metadata như audience, scope, subject, thời hạn nếu cần.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Orders API
    participant AS as Authorization Server
    C->>API: Authorization: Bearer <opaque token>
    API->>AS: Introspection qua kết nối và xác thực tin cậy
    AS-->>API: active, aud, scope, sub, exp (nếu được cung cấp)
    API->>API: Kiểm tra metadata + quyền trên đơn
    API-->>C: Cho phép hoặc từ chối
~~~

**`active: true` không thay thế audience hay quyền trên từng đối tượng.** Nếu introspection thiếu thuộc tính mà chính sách API bắt buộc, API không được tự mặc định rằng token có quyền. Việc cache introspection tăng hiệu năng nhưng có thể làm **chậm hiệu lực thu hồi**; phải xác định thời gian cache phù hợp.

### So sánh thực tế

| Tiêu chí | JWT access token ký | Opaque access token |
|---|---|---|
| Cách kiểm tra thường gặp | API xác minh chữ ký và claims, có thể làm cục bộ. | API gọi introspection/tra cứu ở nguồn tin cậy. |
| Phụ thuộc mạng khi kiểm tra | Có thể ít hơn nếu có JWKS cache hợp lệ. | Có thể cần truy vấn AS hoặc kho trạng thái. |
| Thu hồi ngay | Không tự có nếu chỉ kiểm tra chữ ký và `exp`. | Có thể hỗ trợ kiểm tra trạng thái tập trung, phụ thuộc cache. |
| Rò rỉ nội dung | Payload JWS có thể đọc được dù chữ ký đúng. | Nội dung không tự mô tả cho bên giữ token. |
| Đánh giá quyền trên tài nguyên | **Luôn do API thực hiện.** | **Luôn do API thực hiện.** |

Không có một định dạng thắng tuyệt đối: lựa chọn dựa vào hệ sinh thái, khả năng thu hồi, yêu cầu độ trễ, giới hạn dữ liệu trong token và thiết kế tin cậy.

## 7. Resource Server kiểm tra access token như thế nào?

Quy trình dưới đây là **mã giả kiểm soát**, không thay thế thư viện OAuth/JWT có kiểm chứng:

~~~text
handle(GET /orders/{id}, request):
    token = parseAuthorizationBearer(request)
    if token missing or malformed:
        return 401

    policy = trustedConfigFor("orders-api")
    verified = verifyAccessToken(token, policy)
        # JWT: trusted issuer/key/algorithm, signature, claims
        # opaque: trusted introspection/lookup, active + metadata
    if verified invalid, wrong audience, expired or inactive:
        return 401

    if policy.requiresSenderProof and not verifySenderProof(request, token):
        return 401

    if "orders:read" not in verified.scopes:
        return 403

    order = loadOrder(id)
    if order not found:
        return 404
    if not canRead(verified.principal, order, currentPolicy):
        return 403  # hoặc 404 theo chính sách che giấu tài nguyên

    return 200 with permittedOrderFields(order)
~~~

**Điểm quyết định:** access token được chấp nhận ở lớp xác thực/ủy quyền ban đầu **không đồng nghĩa** request đã được phân quyền ở cấp bản ghi. Scope `orders:read` không tự xác nhận quyền trên order 42, tenant B hoặc dữ liệu đã bị hạn chế vì trạng thái nghiệp vụ.

### HTTP 401 và 403 khi dùng bearer token

| Tình huống | Phản hồi thường dùng |
|---|---|
| Thiếu token ở tài nguyên được bảo vệ | **401 Unauthorized** với thách thức `WWW-Authenticate` phù hợp. |
| Token sai chữ ký, hết hạn, bị từ chối hoặc sai audience | **401 Unauthorized**; với bearer có thể dùng lỗi `invalid_token`. |
| Token hợp lệ nhưng scope không đủ | **403 Forbidden**; với bearer có thể dùng `insufficient_scope` và scope cần thiết theo chính sách. |
| Có scope nhưng không được xem bản ghi cụ thể | **403** hoặc **404** nếu cần hạn chế lộ sự tồn tại của bản ghi. |

Ví dụ phản hồi minh họa theo cơ chế thách thức bearer:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:read"
~~~

Không phản hồi nguyên token hoặc chi tiết nhạy cảm về principal. Client có thể xin access token mới khi gặp lỗi hết hạn trong giới hạn chính sách, nhưng **không tự lặp vô hạn** với 403 vì thiếu quyền không nhất thiết được giải quyết bằng refresh.

## 8. Giới hạn sử dụng token trong suốt vòng đời

### Phát hành theo nguyên tắc quyền tối thiểu

- Giới hạn **audience** đến Resource Server thực sự cần.
- Chỉ cấp các **scope** cần cho chức năng hiện tại; chia quyền đọc, ghi và tác vụ nhạy cảm khi hợp lý.
- Đặt **thời hạn hiệu lực** vừa đủ, thường ngắn đối với access token bearer vì token bị lộ có thể bị dùng lại trước khi hết hạn.
- Có thể ràng buộc token với client hoặc khóa/chứng chỉ theo chính sách; không mặc định mọi access token đều là bearer thuần túy.
- Không dựa vào `sub`, scope hay role chưa được xác minh, dù payload JWT đọc được rõ ràng.

### Lưu trữ và truyền đúng nơi

**Trên đường truyền**, client thông thường gửi access token trong header:

~~~http
Authorization: Bearer <ACCESS_TOKEN_PLACEHOLDER>
~~~

Sử dụng HTTPS/TLS; không gửi token đến domain không tin cậy và tránh đưa token vào URL query, log, error tracking, analytics, lịch sử trình duyệt hoặc thông báo hỗ trợ. RFC 6750 mô tả một số cách truyền bearer token; **header Authorization là cách ưu tiên** trong sử dụng API thông thường. Đừng gửi refresh token cho Resource Server.

**Trên trình duyệt**, access token trong `localStorage`/`sessionStorage` có thể bị JavaScript của cùng origin đọc và dễ bị lộ khi có XSS. Token chỉ nằm trong bộ nhớ giảm thời gian tồn tại nhưng XSS vẫn có thể đọc hoặc dùng nó khi trang đang chạy. Một kiến trúc **Backend for Frontend (BFF)** có thể giữ token trên máy chủ và dùng cookie phiên `HttpOnly`, `Secure`, `SameSite` phù hợp, song phải đánh giá và chống CSRF và XSS theo mô hình tương ứng. `HttpOnly` không làm trang miễn nhiễm với XSS.

**Trên mobile/desktop**, dùng kho lưu bí mật phù hợp nền tảng và hạn chế log/backup không bảo vệ. **Trên backend**, giữ token/secret trong vùng quản lý bí mật, cấp quyền truy cập tối thiểu và tránh ghi vào repository.

### Làm mới, hết hạn, đăng xuất và thu hồi

Khi access token hết hạn, client phải có cách hợp lệ để lấy token mới, chẳng hạn thực hiện lại luồng ủy quyền hoặc dùng **refresh token nếu đã được cấp**. Refresh token chỉ gửi đến **token endpoint** của AS; hệ thống nên bảo vệ nó đặc biệt và áp dụng rotation/ràng buộc người gửi phù hợp với loại client và mức rủi ro.

Điều quan trọng là:

- **Hết hạn** giảm thời gian token bị đánh cắp có thể dùng; không chặn việc lạm dụng trong khoảng token còn hiệu lực.
- **Đăng xuất** khỏi client không mặc định vô hiệu hóa tức thời mọi access token đã phát hành.
- **Thu hồi** token cần cơ chế rõ ràng. Opaque token có thể dễ tra cứu trạng thái hơn nếu introspection không cache quá lâu; JWT tự xác minh cục bộ thường vẫn hợp lệ đến `exp` trừ khi API có denylist, kiểm tra phiên, introspection hoặc chính sách trạng thái bổ sung.
- **Thay đổi role hoặc membership** có thể làm claims cũ không phản ánh quyền hiện tại; action nhạy cảm cần chiến lược làm mới/đối chiếu chính sách.

Không nên thiết kế access token sống rất lâu chỉ để client khỏi phải xin lại; như vậy kéo dài khoảng thời gian attacker sử dụng token nếu bị lộ.

## 9. Token bị đánh cắp: bearer và sender-constrained khác nhau ra sao?

Với **bearer access token**, bất kỳ ai có token còn hiệu lực đều có thể trình nó. API không thể suy ra người gửi hiện tại chính là người nhận ban đầu chỉ từ chữ ký JWT hoặc chuỗi opaque có `active: true`.

~~~mermaid
sequenceDiagram
    participant U as Client hợp lệ
    participant A as Attacker
    participant API as Resource Server
    Note over U,A: Token bearer bị lộ qua log, XSS hoặc thiết bị
    U->>API: Bearer access token
    API-->>U: Cho phép nếu đủ quyền
    A->>API: Phát lại cùng bearer access token
    API-->>A: Có thể cho phép nếu token còn hiệu lực và đủ quyền
~~~

Để giảm rủi ro:

| Biện pháp | Tác dụng | Giới hạn |
|---|---|---|
| TLS, chống XSS, giảm log bí mật, lưu trữ bảo mật | Giảm nguy cơ bị đánh cắp. | Không bảo đảm tuyệt đối nếu endpoint/thiết bị bị chiếm. |
| Scope/audience hẹp | Giới hạn loại thao tác và API kẻ tấn công dùng được. | Không tự ngăn thao tác trong phạm vi đã cấp. |
| Access token ngắn hạn và thu hồi | Thu hẹp cửa sổ lạm dụng. | Có thể tồn tại độ trễ thu hồi hoặc cache. |
| **DPoP** hoặc **mTLS certificate-bound token** | Ràng buộc token với bằng chứng sở hữu khóa/chứng chỉ của bên gửi. | Nếu attacker có cả token và quyền dùng khóa thì vẫn có nguy cơ. |

DPoP (RFC 9449) có bằng chứng ký gắn với request và khóa của client; mTLS (RFC 8705) có thể ràng buộc token với chứng chỉ client. Resource Server phải kiểm tra proof tương ứng, không chỉ kiểm tra token. Đây là cơ chế **sender-constrained**; khác với bearer token thuần túy ở chỗ chỉ chép riêng token có thể chưa đủ để phát lại.

**JWT có chữ ký không tự chống replay.** `jti` nếu có chỉ là mã định danh; cần chính sách và bộ nhớ trạng thái/kiểm tra proof phù hợp mới sử dụng nó để phát hiện phát lại trong trường hợp yêu cầu.

## 10. Sai lầm thường gặp khi xác định phạm vi access token

| Nhận định/sai lầm | Vấn đề | Cách hiểu đúng |
|---|---|---|
| “JWT có `role=admin` nên dùng ở API nào cũng được.” | Không kiểm tra issuer, audience, loại token và chính sách tài nguyên. | Luôn xác minh token cho API hiện tại; quyền không tự vượt ranh giới dịch vụ. |
| “Có `orders:read` là xem được mọi đơn.” | Bỏ qua chủ sở hữu, tenant, trạng thái. | Scope chỉ là một lớp; cần object-level authorization. |
| “Refresh token là access token mạnh hơn.” | Dùng sai nơi; tăng nguy cơ kéo dài phiên bị chiếm. | Refresh token chỉ phục vụ xin token mới ở AS. |
| “ID token OIDC cũng dùng được với API.” | Nhầm mục đích token. | API yêu cầu access token đúng audience. |
| “Opaque token trông đúng format nên là thật.” | Chuỗi không có ý nghĩa tự xác minh. | Tra cứu/introspection với nguồn tin cậy. |
| “JWT đã ký thì không ai đọc payload.” | JWS ký không mã hóa nội dung. | Không đưa bí mật vào payload khi không có bảo vệ bí mật phù hợp. |
| “Đăng xuất hoặc đổi mật khẩu làm mọi access token cũ hết hiệu lực ngay.” | Phụ thuộc chính sách thu hồi/session. | Thiết kế TTL, trạng thái và thu hồi rõ ràng. |
| “Frontend ẩn nút sửa nên không cần kiểm tra API.” | Caller có thể gửi HTTP request trực tiếp. | Quyết định cuối và chặn quyền ở backend. |
| “Cùng một AS ký, có thể gửi token qua các microservice.” | Dễ token confusion và mở rộng quyền ngoài dự kiến. | Audience đúng từng RS; đổi token/cấp token riêng khi cần. |

## 11. Tình huống suy luận

**Tình huống A — Đúng scope, sai audience.** Client có JWT access token với `scope=orders:read`, `aud=orders-api` và gọi `billing-api`. Billing API xác minh được chữ ký của cùng AS. Có được xử lý không?

**Giải thích:** Không. Token dành cho `orders-api`; cần token được cấp hợp lệ cho `billing-api`, đồng thời đáp ứng scope và quyền của API đó.

**Tình huống B — Cùng tenant nhưng khác chủ sở hữu.** Token có `aud=orders-api`, `scope=orders:read`, `sub=user-123`. Order 42 thuộc `user-456` cùng tenant. API có thể trả order 42 chỉ vì cùng tenant không?

**Giải thích:** Không, trừ khi chính sách nghiệp vụ cho phép quyền đọc chung hoặc quyền hỗ trợ đã được cấp. Cần kiểm tra quyền trên **order cụ thể**.

**Tình huống C — Refresh token bị gửi cho API.** Client gửi giá trị refresh token vào header `Authorization: Bearer ...` khi gọi `GET /orders`. API nên làm gì?

**Giải thích:** Từ chối. Refresh token không dành cho Resource Server; nó phải được bảo vệ và chỉ sử dụng ở token endpoint theo luồng được cho phép.

**Tình huống D — Token JWT còn hạn sau đăng xuất.** Client xóa phiên và token trên trình duyệt, nhưng attacker đã sao chép access token trước đó. API chỉ kiểm tra chữ ký và `exp`. Attacker có thể dùng token không?

**Giải thích:** Có thể, đến khi hết hạn hoặc cho đến khi có cơ chế thu hồi được API thực thi. Xóa token phía client không thể thu lại mọi bản sao đã bị lộ.

**Tình huống E — Token opaque còn hoạt động nhưng scope thiếu.** Introspection trả `active=true`, `aud=orders-api`, `scope=orders:read`. Client yêu cầu `POST /orders/42/cancel`. Điều gì xảy ra?

**Giải thích:** Từ chối nếu chính sách hủy yêu cầu `orders:cancel` và quyền đối tượng phù hợp. `active` và audience đúng chưa đủ.

## Checklist thiết kế access token

1. **Đúng mục đích:** chỉ access token được hỗ trợ mới được dùng để gọi API; không dùng ID/refresh token thay thế.
2. **Đúng nơi nhận:** kiểm tra issuer tin cậy, audience đích và loại token theo profile.
3. **Đúng quyền:** so khớp scope thực sự được cấp, permission/role hợp lệ và chính sách trên tài nguyên/tenant.
4. **Đúng thời điểm:** kiểm tra hạn dùng, thời điểm bắt đầu, trạng thái thu hồi và sự thay đổi quyền theo yêu cầu.
5. **Đúng người gửi khi cần:** xác minh proof cho DPoP/mTLS nếu dùng sender-constrained token.
6. **Bảo vệ suốt vòng đời:** TLS, lưu trữ thích hợp, log không chứa token, TTL phù hợp, bảo vệ refresh token và có kế hoạch phản ứng khi token lộ.

## Ghi nhớ

**Access token dùng để yêu cầu truy cập một Resource Server theo quyền đã cấp**. **Audience** giới hạn nơi token được chấp nhận; **scope** giới hạn loại hành động được ủy quyền; **authorization ở API** quyết định principal có quyền đối với tài nguyên cụ thể hay không. JWT và opaque là cách biểu diễn, bearer và sender-constrained là cách sử dụng. Token cần được xác minh, bảo vệ, giới hạn thời hạn và có chiến lược thu hồi phù hợp; một access token hợp lệ **không tự mở mọi cánh cửa**.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
