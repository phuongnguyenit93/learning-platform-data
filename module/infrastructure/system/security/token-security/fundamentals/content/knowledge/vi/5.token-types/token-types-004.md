# Bearer token

## 1. Bearer token là gì?

Trong chương **Token types** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, **bearer token** là một khái niệm quan trọng vì nó mô tả **cách bên cầm token được phép sử dụng token**, thay vì mô tả hình thức dữ liệu của token. Theo OAuth 2.0 Bearer Token Usage (RFC 6750), bên nào đang sở hữu một bearer token hợp lệ thì có thể trình token đó để truy cập tài nguyên được bảo vệ; bên nhận không bắt buộc bên gửi chứng minh thêm quyền sở hữu một khóa mật mã riêng gắn với token.

Nói ngắn gọn:

> **Bearer = ai cầm token thì có thể dùng token, trong giới hạn quyền và thời hạn mà resource server chấp nhận.**

Giả sử dịch vụ `order-service` có access token chứa quyền `inventory.read` và được cấp cho `inventory-api`:

~~~http
GET /v1/inventory/sku-123 HTTP/1.1
Host: inventory.example.test
Authorization: Bearer eyJhbGciOi...
~~~

Nếu kẻ tấn công lấy được **toàn bộ token còn hiệu lực**, trong một hệ thống chỉ yêu cầu bearer token, kẻ đó có thể gửi lại cùng token từ một máy khác và được API đánh giá như người dùng/client hợp lệ — miễn là request thỏa điều kiện kiểm tra token, audience, scope và chính sách API. Đây là rủi ro **token theft** và **replay**.

Bearer token **không đồng nghĩa** với JWT; JWT **không mặc nhiên** là bearer token. Một access token có thể là JWT được ký hoặc chuỗi opaque, và cả hai đều có thể được sử dụng theo ngữ nghĩa bearer.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **cách sử dụng bearer** với **định dạng JWT/opaque** và **mục đích access/ID/refresh token**.
2. Gửi bearer access token đúng cách theo OAuth 2.0 và hiểu phản hồi lỗi từ resource server.
3. Xác định chính xác API phải kiểm tra những gì trước khi chấp nhận token.
4. Phân tích tại sao HTTPS, token sống ngắn, scope/audience hẹp và lưu trữ an toàn là bắt buộc.
5. Biết khi nào cần nâng cấp lên **sender-constrained access token** như mTLS certificate-bound token hoặc DPoP.

## 2. Đặt bearer token vào đúng các trục phân loại

Các thuật ngữ token security thuộc những câu hỏi khác nhau:

| Câu hỏi | Các loại thường gặp | Giải thích |
| --- | --- | --- |
| **Token được dùng để làm gì?** | Access token, ID token, refresh token | Access token dùng để truy cập resource server; ID token OIDC nói về phiên xác thực của end-user cho client; refresh token dùng để xin token mới ở authorization server. |
| **Token có dạng dữ liệu nào?** | JWT, opaque/reference token | JWT có cấu trúc claims; opaque không có hợp đồng để resource server tự phân tích. |
| **Bên gửi chứng minh quyền dùng token bằng gì?** | Bearer, sender-constrained/proof-of-possession | Bearer dựa vào việc sở hữu chuỗi token; sender-constrained đòi hỏi thêm bằng chứng khóa/chứng chỉ tương ứng. |
| **Token được xác minh ở đâu?** | Xác minh JWT cục bộ bằng JWKS; introspection tại AS | Cách resource server kiểm tra nguồn phát hành, trạng thái và điều kiện hiệu lực. |

Hai cách kết hợp minh họa:

- **Bearer JWT access token:** API dùng public key tin cậy để xác minh chữ ký JWT, rồi kiểm tra `iss`, `aud`, `exp`, `scope`. Sau đó token vẫn có tính chất bearer: ai lấy được chuỗi JWT đều có thể sử dụng tới khi bị từ chối.
- **Bearer opaque access token:** API gọi introspection endpoint đã tin cậy để biết token còn `active` và được cấp quyền nào. Vì chuỗi token là bearer, ai lấy được chuỗi đó cũng có thể gửi cho API.

**Không nên kết luận:** “JWT có chữ ký nên kẻ đánh cắp không dùng được”. Chữ ký chứng minh token không bị sửa sau khi issuer ký; chữ ký **không xác thực người đang cầm token**. Kẻ tấn công không cần sửa token: chỉ cần phát lại nguyên token là đủ.

### 2.1. Bearer access token khác với refresh token và ID token

| Token | Bên nhận đúng | Vai trò | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Bearer access token** | API/resource server là `aud` hợp lệ | Ủy quyền truy cập tài nguyên với scope/quyền giới hạn | Cho API chấp nhận access token dành cho API khác |
| **ID token (OIDC)** | Client ứng dụng đăng nhập, thường có `aud` là client ID | Thông báo kết quả xác thực người dùng | Gửi ID token tới API như access token |
| **Refresh token** | Token endpoint của authorization server | Xin access token mới theo grant/chính sách phù hợp | Đưa refresh token vào `Authorization: Bearer` khi gọi resource API |

Refresh token cũng là credential nhạy cảm; một số triển khai có thể cấp refresh token theo cơ chế ràng buộc người gửi hoặc dạng bearer. Tuy nhiên, trong bài này, thuật ngữ **Bearer** khi gọi resource server chủ yếu chỉ **bearer access token** trong OAuth 2.0. `token_type: "Bearer"` trong phản hồi token endpoint cho client biết cách trình **access token** với API, không nói token đó là JWT hay opaque.

## 3. Luồng bearer access token trong OAuth 2.0

Mô hình gồm **resource owner** (nếu có người dùng), **client**, **authorization server (AS)** và **resource server (RS)**. Client nhận access token từ AS qua một OAuth grant được hỗ trợ, rồi dùng token đó để gọi RS.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server (inventory-api)
    C->>AS: Xin access token qua OAuth flow phù hợp
    AS->>AS: Xác thực/ủy quyền và quyết định scope, audience, TTL
    AS-->>C: access_token, token_type=Bearer, expires_in
    C->>RS: Authorization: Bearer <access_token> (HTTPS)
    RS->>RS: Xác minh issuer, chữ ký/introspection, aud, exp, scope
    RS->>RS: Kiểm tra quyền trên tài nguyên/tenant cụ thể
    alt Token hợp lệ và đủ quyền
        RS-->>C: 200 OK và dữ liệu được phép
    else Token không hợp lệ hoặc thiếu quyền
        RS-->>C: 401 / 403 cùng WWW-Authenticate phù hợp
    end
~~~

Lưu ý rằng bearer token không nhất thiết có người dùng tương tác. Khi `order-service` được cấp token bằng `client_credentials`, token đại diện cho quyền của chính service/client. Khi Alice đăng nhập và đồng ý ủy quyền, token có thể biểu diễn quyền thay mặt Alice. **Ngữ nghĩa bearer vẫn giống nhau**: RS không biết người gửi hiện tại có thật là Alice hoặc `order-service` chỉ từ việc sở hữu chuỗi token.

### 3.1. Phản hồi token endpoint

Một phản hồi OAuth 2.0 minh họa:

~~~json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Ở đây `expires_in: 300` biểu thị thời gian hiệu lực 300 giây kể từ lúc cấp token. Client cần tính thời điểm hết hạn với khoảng dự phòng để xin token mới trước khi gọi API; `expires_in` không cho phép bỏ qua `exp` hoặc trạng thái thu hồi ở phía RS. Access token có thể là opaque dù ví dụ dùng tiền tố thường gặp của JWT.

Không tự cho rằng token có mọi scope client đã yêu cầu: AS có thể cấp phạm vi hẹp hơn. Khi scope được trả về, client cần xử lý quyền thực sự được cấp; RS phải kiểm tra quyền theo token hoặc thông tin introspection, không dựa vào scope do client tự khai.

## 4. Ba cách truyền bearer token theo RFC 6750

RFC 6750 mô tả các cách sử dụng bearer access token trong HTTP. **Ưu tiên header `Authorization`**; những cách khác có điều kiện và rủi ro riêng.

### 4.1. Cách khuyến nghị: HTTP Authorization header

~~~http
GET /v1/orders/123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access_token>
Accept: application/json
~~~

Đây là cách phổ biến và được khuyến nghị cho ứng dụng web, mobile, backend hoặc gateway. Tên scheme là `Bearer` và theo HTTP không phân biệt hoa thường; để dễ đọc và tương thích, nên dùng chính xác `Authorization: Bearer ...`. Client cần bảo đảm API đích là endpoint chính xác và kết nối HTTPS đã được xác thực. Token không được đưa vào `Referer`, nội dung log, URL chia sẻ hay tham số theo dõi.

Ví dụ `curl` với biến môi trường/token được cấp động:

~~~bash
curl --fail-with-body \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://api.example.test/v1/orders/123"
~~~

`$ACCESS_TOKEN` là placeholder cho biến môi trường ở shell kiểu Unix; tránh đưa giá trị thật trực tiếp vào history hoặc log. Lệnh chỉ minh họa cách đặt header, không có nghĩa là một token mẫu có thể dùng thật.

### 4.2. HTTP form-encoded body: chỉ trong điều kiện phù hợp

RFC 6750 còn mô tả truyền token trong body của request với `Content-Type: application/x-www-form-urlencoded` và tham số `access_token`, nhưng chỉ áp dụng trong những điều kiện giới hạn: body phải là form-encoded, request phải có entity body, không dùng với phương thức mà việc có body không có ngữ nghĩa phù hợp như GET, và token không được lặp ở nơi khác trong cùng request.

~~~http
POST /legacy-endpoint HTTP/1.1
Host: api.example.test
Content-Type: application/x-www-form-urlencoded

access_token=<url-encoded-token>&action=read
~~~

Kỹ thuật này **không phải cách khuyến nghị** cho API hiện đại. Dù token tránh URL, token vẫn có thể lọt vào log body, tracing, lỗi hoặc hệ thống thu thập form; ngoài ra nhiều framework không nhận dạng token theo cách này nếu không cấu hình riêng. Chỉ dùng khi có lý do tương thích rõ ràng và đáp ứng đúng RFC.

### 4.3. URI query parameter: nên tránh

~~~http
GET /v1/orders/123?access_token=<token> HTTP/1.1
Host: api.example.test
~~~

RFC 6750 mô tả cách đặt `access_token` trong query nhưng **không khuyến nghị** vì URL thường bị lưu vào browser history, reverse-proxy logs, analytics, APM, cache và có thể bị gửi theo referrer trong những tình huống nhất định. Một URL đã chụp màn hình, chia sẻ hoặc xuất hiện trong log có thể trở thành nơi làm lộ bearer token.

Không triển khai kiểu `?token=...` hoặc `?access_token=...` cho API chỉ vì dễ thử trong trình duyệt. Nếu một hệ thống legacy buộc phải dùng, cần đánh giá nguy cơ, hạn chế thời hạn và phạm vi token, tắt thu thập URL nhạy cảm, nhưng ưu tiên sửa giao thức để dùng header.

### 4.4. Không truyền một token ở nhiều vị trí

Một request không nên đồng thời đặt cùng bearer token ở header, query và form body. Việc làm này tăng bề mặt rò rỉ và dễ khiến proxy, gateway và backend xác minh **hai giá trị khác nhau**. Client nên chọn đúng một cơ chế; phía RS/gateway cần xác định quy tắc từ chối request mơ hồ thay vì chọn token tùy tiện.

## 5. Resource server phải xác minh điều gì?

Nhận header bearer **chưa đủ** để cho phép truy cập. Resource server cần quyết định **token có đáng tin và dành cho API này không**, sau đó mới phân quyền cho request.

| Kiểm tra | Câu hỏi API cần trả lời | Hậu quả khi bỏ qua |
| --- | --- | --- |
| **Issuer / nguồn tin cậy** | AS nào được phép cấp token cho API này? | Chấp nhận token của hệ thống hoặc kẻ tấn công không được ủy quyền |
| **Chữ ký hoặc introspection** | Token có thực sự do AS tin cậy cấp và còn `active` không? | Chấp nhận token giả, sửa đổi hoặc đã bị vô hiệu |
| **Audience (`aud`)** | Token có được cấp cho API/resource này không? | Token dành cho API A bị dùng tại API B |
| **Thời gian (`exp`, `nbf`, …)** | Token đã hết hạn hoặc chưa có hiệu lực chưa? | Dùng lại token cũ hoặc token chưa tới thời điểm có hiệu lực |
| **Đúng mục đích** | Đây có phải access token chứ không phải ID/refresh token hay client assertion? | Token confusion, kiểm tra sai mục đích |
| **Scope/permission** | Endpoint yêu cầu `orders.read` hay `orders.write`; token có quyền đó không? | Vượt quá phạm vi quyền được cấp |
| **Quy tắc tài nguyên** | Principal có quyền với đơn hàng 123 và tenant này không? | Truy cập bản ghi của người khác hoặc tenant khác |
| **Ràng buộc người gửi (nếu có)** | Token có yêu cầu DPoP/mTLS và bằng chứng gửi hợp lệ không? | Token lẽ ra bị ràng buộc bị xử lý nhầm thành bearer |

### 5.1. Với bearer JWT access token

JWT có thể chứa claims như:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1795400000,
  "nbf": 1795400000,
  "exp": 1795400300
}
~~~

Đây chỉ là **payload minh họa**, không phải JWT đã ký. RS phải:

1. Tin một issuer xác định qua cấu hình hoặc danh sách issuer được cho phép; truy xuất JWKS đúng issuer đó bằng TLS và cơ chế metadata được kiểm chứng nếu cần.
2. Xác minh chữ ký bằng thuật toán được cấu hình cho phép. `kid` chỉ chọn khóa trong tập khóa đã tin; không tải URL `jku`/`x5u` tùy ý từ token hay cho phép `alg=none`.
3. Kiểm tra `iss`, `aud`, `exp`, `nbf` và các yêu cầu token profile thích hợp (ví dụ access token JWT theo RFC 9068). Không lấy `scope` trước khi token được xác minh rồi dùng nó để quyết định cấp quyền.
4. Kiểm tra quyền trên endpoint và tài nguyên. Scope `orders.read` vẫn không bảo đảm người dùng có quyền đọc **mọi** đơn hàng.

**Hạn chế của xác minh JWT cục bộ:** Nếu token bị đánh cắp nhưng chữ ký, audience và thời hạn vẫn đúng, RS không phát hiện được người cầm token là kẻ trộm. Nếu chưa có cơ chế trạng thái bổ sung, token bị thu hồi trước hạn có thể vẫn được chấp nhận tới `exp`.

### 5.2. Với bearer opaque access token

Opaque token là chuỗi mà RS không có hợp đồng tự giải nghĩa. RS gọi **introspection endpoint của AS đã được tin cậy** (RFC 7662), xác thực chính RS với AS theo phương thức cho phép và nhận về trạng thái:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1795400300
}
~~~

`active` là trường quan trọng của introspection; các trường còn lại có thể có hoặc không tùy AS và hợp đồng tích hợp. `active: true` **không tự động chứng minh** rằng token dành cho mọi API. Nếu response không có audience, cần một hợp đồng AS/RS bảo đảm token được introspect đúng ngữ cảnh tài nguyên và không thể dùng sai API.

API phải từ chối khi `active: false`, token sai audience, thiếu scope hoặc không được AS công nhận cho API. Nếu introspection endpoint timeout hay lỗi, **không tự mặc định token hợp lệ**. Cache response giúp giảm độ trễ nhưng tạo cửa sổ chấp nhận token đã bị thu hồi; TTL cache phải bị giới hạn bởi `exp` và yêu cầu thu hồi của ứng dụng.

### 5.3. Vì sao chữ ký JWT không biến bearer thành proof-of-possession?

Chữ ký JWT trả lời **“issuer có ký nội dung token không?”**. Proof-of-possession trả lời **“bên gửi request có sở hữu khóa riêng đã ràng buộc với token không?”**. Đây là hai phép kiểm tra khác nhau.

~~~mermaid
flowchart LR
    T["Access token bị đánh cắp"] --> B["Bearer API"]
    B --> V["JWT hợp lệ / opaque active"]
    V --> OK["Có thể truy cập trong phạm vi token"]
    T --> P["Sender-constrained API"]
    P --> PROOF{"Có bằng chứng khóa/chứng chỉ hợp lệ?"}
    PROOF -->|"Không"| DENY["Từ chối request"]
    PROOF -->|"Có"| CHECK["Tiếp tục xác minh token và quyền"]
~~~

Một bearer token có thể là JWT bất đối xứng ký rất mạnh và vẫn bị phát lại nguyên văn nếu bị lộ. Điều đó giải thích vì sao bảo vệ token khi truyền, khi lưu và trong log là phần thiết yếu của token security.

## 6. HTTP 401, 403 và WWW-Authenticate: cách API báo lỗi bearer

OAuth 2.0 Bearer Token Usage chuẩn hóa cách resource server trả về lỗi xác thực/ủy quyền bằng header `WWW-Authenticate`. Đây là phần quan trọng để client biết cần xin token mới hay cần quyền khác.

| Tình huống | HTTP thường gặp | Giá trị liên quan | Client nên xử lý |
| --- | --- | --- | --- |
| Chưa gửi access token đến API yêu cầu xác thực | `401 Unauthorized` | `WWW-Authenticate: Bearer realm="orders"` | Thực hiện OAuth flow phù hợp để có token |
| Token hết hạn, không hợp lệ hoặc bị thu hồi | `401 Unauthorized` | `error="invalid_token"` | Xin access token hợp lệ; tránh thử lại vô hạn với cùng token |
| Token hợp lệ nhưng thiếu `orders.write` | `403 Forbidden` | `error="insufficient_scope"` và có thể kèm `scope="orders.write"` | Không tự động leo thang quyền; cần xin scope/ủy quyền phù hợp |
| Request mang token không đúng cú pháp hoặc có nhiều cách truyền token | `400 Bad Request` thường gặp | `error="invalid_request"` | Sửa request/header theo giao thức |

Ví dụ token hết hạn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Ví dụ token đúng nhưng thiếu quyền ghi:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders.write"
Cache-Control: no-store
~~~

Header trên giúp client phân biệt **authentication** (token không được chấp nhận) và **authorization** (token được chấp nhận nhưng không có quyền). Đừng trả toàn bộ token hay chi tiết hạ tầng nội bộ trong `error_description`; thông tin trả về nên đủ để client xử lý mà không tiết lộ dữ liệu bảo mật.

Không phải mọi lỗi đều nên biến thành `401`. Nếu introspection endpoint của AS bị timeout, hệ thống có thể trả lỗi vận hành như `503 Service Unavailable` tùy thiết kế để tránh client nhầm token đã bị revoke. Tuy nhiên, trong thời gian không xác minh được, resource server phải **không cho phép truy cập**.

### 6.1. Client có được tự động thử lại không?

Với `invalid_token` do hết hạn, client hợp lệ có thể xin access token mới rồi **thử lại có giới hạn**, đặc biệt với request idempotent. Với lệnh ghi dữ liệu, phải cẩn thận retry tránh thực hiện hai lần nếu request trước đã được xử lý; dùng idempotency key/chính sách retry khi cần. Với `insufficient_scope`, lặp lại cùng token chỉ gây lỗi 403; cần thay đổi quyền được cấp hoặc thông báo không đủ quyền.

## 7. Nguy cơ bearer token bị đánh cắp và phát lại

Điểm yếu cốt lõi của bearer token không nằm ở thuật toán chữ ký mà ở **việc sao chép token**. Nếu token bị lộ ra ngoài ranh giới tin cậy và vẫn hợp lệ, kẻ tấn công có thể phát lại request có header `Authorization`.

### 7.1. Kịch bản tấn công thực tế

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Client hợp lệ
    participant L as Log / Browser / Proxy bị lộ
    participant A as Kẻ tấn công
    participant API as Resource server
    U->>API: Authorization: Bearer token-123
    U-->>L: Vô tình ghi lại token-123
    A->>L: Đọc hoặc đánh cắp token-123
    A->>API: Authorization: Bearer token-123
    API->>API: Token vẫn hợp lệ, aud/scope đúng
    API-->>A: Trả dữ liệu nếu chỉ xác thực bearer
~~~

Những nguồn rò rỉ thường gặp:

- **URL và query string:** access token xuất hiện trong browser history, log reverse proxy, APM hoặc link được chia sẻ.
- **Log và tracing:** ghi nguyên `Authorization`, HTTP request/response, crash dump hoặc lỗi có chứa token.
- **JavaScript/browser:** lỗ hổng XSS và dependency độc hại có thể đọc token ở nơi JavaScript có quyền truy cập.
- **Ứng dụng di động và desktop:** lưu token trong file không bảo vệ, debug log hoặc đồng bộ/backup ngoài ý muốn.
- **Hệ thống backend:** secret/token bị đưa vào container image, environment dump, CI logs, queue messages, bộ nhớ đệm dùng chung hoặc hệ thống observability.
- **Chuyển tiếp token sai nơi:** HTTP client tự động đính kèm token vào request sang host không đáng tin, hoặc chuyển tiếp token qua proxy/redirect không kiểm soát.

Bearer token bị lộ có thể gây **replay** từ mạng khác, thiết bị khác hoặc phiên khác. Hạn chế số lần gọi API hay kiểm tra địa chỉ IP đôi khi giúp phát hiện bất thường, nhưng **IP binding đơn giản không phải bảo vệ mật mã đáng tin**, vì NAT, proxy và di chuyển mạng có thể làm thay đổi IP hợp lệ.

### 7.2. HTTPS bảo vệ được gì và không bảo vệ được gì?

HTTPS/TLS với xác thực server đúng bảo vệ tính bí mật và toàn vẹn của bearer token **trong quá trình truyền giữa hai đầu TLS**. TLS không cứu được token đã bị lộ trong browser, mã nguồn, log hoặc một tiến trình bị chiếm quyền.

Một request có thể đi qua:

~~~text
Client --HTTPS--> CDN/Gateway --mTLS hoặc HTTPS--> API
                      |
                 Access logs / tracing
~~~

Nếu TLS kết thúc ở gateway, token trở thành dữ liệu mà gateway có thể thấy. Cần bảo vệ log, bộ nhớ, quyền truy cập của gateway và kết nối tới backend. Khi backend tin header danh tính do gateway đính kèm, phải chặn client bên ngoài tự giả mạo những header này và bảo vệ kết nối gateway–backend.

### 7.3. Biện pháp giảm thiểu theo lớp

| Lớp | Biện pháp | Mục tiêu |
| --- | --- | --- |
| **Kênh truyền** | HTTPS bắt buộc; xác thực chứng chỉ; mTLS nội bộ khi phù hợp | Ngăn đánh cắp token trên đường truyền |
| **Lưu trữ** | Tránh localStorage nếu mô hình đe dọa có XSS; cân nhắc backend-for-frontend (BFF) hoặc token trong bộ nhớ, bảo vệ cookie/session phù hợp | Thu hẹp khả năng script và bên thứ ba đọc token |
| **Giảm giá trị token** | Access token sống ngắn, audience/scope/tenant hẹp | Giảm thời gian và phạm vi lạm dụng sau khi lộ |
| **Logging** | Mask `Authorization`, query/body nhạy cảm, headers và exception; kiểm tra APM | Tránh tạo bản sao token trong hệ thống giám sát |
| **Thu hồi** | Revocation, introspection, denylist khi cần; cache TTL ngắn | Chặn token bị đánh cắp khi còn thời hạn |
| **Phát hiện** | Theo dõi access bất thường, token issuance, spike 401/403, credential compromise | Phát hiện và ứng phó sớm |
| **Ràng buộc người gửi** | DPoP hoặc mTLS certificate-bound access token | Khi token bị sao chép, kẻ tấn công còn cần khóa riêng tương ứng |

Đối với browser: chuyển bearer token sang cookie `HttpOnly` có thể giảm khả năng JavaScript đọc token, **nhưng cookie tự động gửi có nguy cơ CSRF** và cần cấu hình `Secure`, `SameSite`, kiểm tra Origin/CSRF token theo kiến trúc. Cookie chứa session ID cũng là một dạng credential bearer nếu chỉ cần cầm giá trị đó là dùng được. Vì vậy không có nơi lưu nào thay thế việc kiểm soát XSS, CSRF và ranh giới tin cậy.

## 8. Sender-constrained access token: bước tiến khi bearer chưa đủ

**Sender-constrained token** yêu cầu client chứng minh quyền kiểm soát một khóa/chứng chỉ đã gắn với token. Lúc này chỉ biết **chuỗi access token** không đủ để dùng. Hai cơ chế tiêu biểu:

### 8.1. Mutual TLS certificate-bound access token (RFC 8705)

Client có chứng chỉ TLS và private key. Authorization server có thể cấp access token kèm ràng buộc với fingerprint của chứng chỉ, ví dụ claim `cnf` trong JWT:

~~~json
{
  "aud": ["payments-api"],
  "scope": "payments.read",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint"
  }
}
~~~

Resource server phải kiểm tra token như bình thường **và** xác minh chứng chỉ mà client đã trình trong phiên mTLS khớp thumbprint trong token. Nếu gateway thực hiện mTLS termination, cần một cách truyền chứng chỉ/danh tính đã xác thực tới RS an toàn, chống giả mạo và đúng thiết kế.

Điểm cần phân biệt: Một access token có thể vẫn được mang trong header `Authorization: Bearer ...` nhưng đồng thời có **ràng buộc chứng chỉ** ở tầng xác minh. Khi đó token không còn có tính chất bearer thuần túy ở nơi RS thực thi đầy đủ ràng buộc này. Nếu RS bỏ qua `cnf` thì cơ chế bảo vệ bị vô hiệu.

### 8.2. Demonstrating Proof of Possession (DPoP, RFC 9449)

DPoP cho phép client gửi một proof JWT được ký bằng private key, ràng buộc proof với request. Một request mẫu:

~~~http
GET /v1/payments HTTP/1.1
Host: payments.example.test
Authorization: DPoP <access_token>
DPoP: <signed-DPoP-proof-JWT>
~~~

Resource server kiểm tra access token, public key được ràng buộc với token (thường `cnf.jkt`), chữ ký proof, HTTP method `htm`, URI `htu`, dấu thời gian `iat`, định danh proof `jti`, hash access token `ath` và nonce nếu được yêu cầu. Cơ chế kiểm tra replay và giới hạn thời gian phải được thực thi, chứ không chỉ xem proof có chữ ký hợp lệ.

DPoP khác với chỉ thêm header `DPoP` vào request bearer. Khi token được cấp theo DPoP và được sử dụng theo RFC 9449, authorization scheme là `DPoP`; AS và resource server đều phải hỗ trợ cơ chế này. Một hệ thống chỉ chấp nhận `Bearer` nhưng bỏ qua proof không đạt mục tiêu ràng buộc.

| Thuộc tính | Bearer thông thường | mTLS certificate-bound | DPoP |
| --- | --- | --- | --- |
| Chỉ có chuỗi token là đủ gọi API? | Có, nếu token hợp lệ và đủ quyền | Không, còn cần private key/chứng chỉ đúng | Không, còn cần private key để ký proof hợp lệ |
| Chứng minh người gửi tại đâu? | Không có bằng chứng khóa riêng | Tại TLS và kiểm tra fingerprint | Tại proof JWT ràng buộc mỗi request |
| Hỗ trợ với JWT/opaque? | Cả hai theo thiết kế | Cả hai nếu AS/RS hỗ trợ binding | Cả hai nếu AS/RS hỗ trợ binding |
| Yêu cầu triển khai | Token validation và authorization | PKI/mTLS, kiểm tra `cnf` | Quản lý khóa client, proof, thời gian và replay |

**Giới hạn:** Proof-of-possession không giải quyết mọi trường hợp. Nếu kẻ tấn công chiếm cả access token **và private key**, hoặc chiếm tiến trình có thể yêu cầu ký proof, họ vẫn có thể lạm dụng. DPoP/mTLS giúp chống một số kịch bản token bị sao chép, nhưng không thay thế phòng vệ đầu cuối.

## 9. Triển khai bearer token với Java và Spring Security

### 9.1. Resource server: chỉ chấp nhận token đúng issuer, audience và scope

Ví dụ trong Spring Boot/Spring Security 6.x khi API sử dụng JWT access token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

`issuer-uri` biểu thị issuer tin cậy. Framework có thể khám phá metadata/JWKS và kiểm tra issuer cùng các điều kiện thời gian chuẩn khi cấu hình phù hợp. **Vẫn phải kiểm tra audience cho API**; chỉ xác minh chữ ký và issuer không có nghĩa là token dành cho ứng dụng hiện tại.

Ví dụ Java ràng buộc audience `orders-api` và kiểm tra scope ở endpoint:

~~~java
@Configuration
@EnableWebSecurity
class ApiSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://auth.example.test";
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                            "Access token sai audience", null));
        };
        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll());
        http.oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đoạn code minh họa trong lớp cấu hình; cần import Spring Security tương ứng và kiểm tra API theo phiên bản đang sử dụng. Để phù hợp profile JWT access token của AS, cần thêm validation loại token (`typ`/`token_use`) nếu framework/AS không tự bảo đảm; kiểm soát thuật toán được phép theo hợp đồng với issuer. Thực tế cần thêm phân quyền trên **đơn hàng cụ thể** trong service/domain layer, không chỉ so scope `orders.read`.

Với opaque access token, có thể cấu hình Spring Security dùng introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ENV_OR_SECRET_MANAGER_VALUE
~~~

Giá trị `ENV_OR_SECRET_MANAGER_VALUE` là placeholder, không phải secret thật. Hãy lấy credential từ secret manager hoặc biến môi trường an toàn. Cấu hình introspection endpoint phải nằm trong trust configuration của API; sau khi introspect vẫn cần kiểm tra audience/resource binding và quyền theo profile của AS. Ví dụ trên là cấu hình nền tảng, **không phải** trọn bộ policy production.

### 9.2. Client Java: gửi token đúng endpoint, đúng header

Khi một service đã nhận được access token hợp lệ từ OAuth client manager hoặc AS, việc gọi API bằng Spring `RestClient` có thể như sau:

~~~java
String accessToken = authorizedClient.getAccessToken().getTokenValue();

OrderView order = restClient.get()
        .uri("https://orders.example.test/v1/orders/{id}", orderId)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .body(OrderView.class);
~~~

`authorizedClient` ở đây là OAuth2 authorized client đã được cấp token cho resource `orders-api`; code chỉ minh họa phần gửi request. Ứng dụng cần kiểm soát host/URI đích, thời hạn token, scope đã cấp và lỗi 401/403. Không tái sử dụng token một cách mù quáng khi gọi domain khác hoặc sau redirect.

**Lưu ý về error handling:** Đừng log giá trị `accessToken` nếu request thất bại. Chỉ ghi thông tin an toàn như endpoint, mã trạng thái, correlation ID và loại lỗi; hạn chế ghi nguyên request header/response của OAuth token endpoint.

## 10. Vòng đời bearer access token và thu hồi

Token có thể đi qua các bước:

~~~mermaid
flowchart TD
    A["AS phát hành bearer access token"] --> B["Client bảo vệ/lưu token"]
    B --> C["Client trình token cho RS qua HTTPS"]
    C --> D{"RS xác minh và phân quyền"}
    D -->|"Hợp lệ, đủ quyền"| E["Cho truy cập"]
    D -->|"Sai/thiếu quyền"| F["401/403 hoặc lỗi vận hành"]
    E --> G{"Hết hạn hoặc bị thu hồi?"}
    G -->|"Chưa"| C
    G -->|"Rồi"| H["Xin access token mới qua OAuth flow hợp lệ"]
    H --> A
~~~

| Giai đoạn | Kiểm soát chính | Ví dụ sự cố |
| --- | --- | --- |
| **Phát hành** | AS xác thực/ủy quyền client, giới hạn scope/audience, TTL | Cấp token quyền admin cho client chỉ cần đọc |
| **Truyền** | TLS, đúng host và header, không ghi log | Bearer token lọt vào URL query |
| **Lưu trữ** | Tránh lộ qua script, log, backup, chia sẻ cache | Đưa token vào localStorage trên trang có XSS |
| **Xác minh** | JWT signature/JWKS hoặc introspection, issuer, aud, exp, scope | Nhận token của API khác |
| **Gia hạn** | Client xin access token mới khi hết hạn | Retry vô hạn gây quá tải token endpoint |
| **Thu hồi** | AS/RS hỗ trợ revocation, introspection hoặc denylist theo thiết kế | JWT cũ vẫn hợp lệ tới `exp` |
| **Hủy bỏ** | Xóa bản sao token/credential khi hoàn tất hoặc khi có sự cố | Token còn trong log dù ứng dụng đã logout |

Bearer access token sống ngắn giúp giảm **thời gian khai thác** khi bị lộ, nhưng không thay thế thu hồi token. Với JWT được xác minh cục bộ, RS có thể không biết token đã bị revoke trừ khi có denylist, introspection hoặc cơ chế khác. Với opaque token, AS có thể trả `active: false`, nhưng nếu RS cache `active: true` quá lâu thì token đã revoke vẫn được chấp nhận trong thời gian cache.

**Đăng xuất không tự xóa token khỏi mọi nơi.** Nếu client xóa token khỏi bộ nhớ nhưng kẻ tấn công đã sao chép trước đó, token có thể còn dùng được. Quy trình logout và incident response phải xét đến session, refresh token, access token đã phát hành và cache trạng thái tại RS.

### 10.1. TTL ngắn có tác dụng đến đâu?

Giả sử một bearer access token có TTL 5 phút. Kẻ tấn công lấy được token sau khi phát hành 2 phút, thì về mặt thời hạn lý thuyết họ còn khoảng 3 phút để lạm dụng — trừ khi token bị vô hiệu sớm hoặc có kiểm soát khác. Nếu TTL là 24 giờ thì cửa sổ rủi ro lớn hơn nhiều.

Không có một TTL duy nhất đúng cho mọi hệ thống. Lựa chọn phụ thuộc độ nhạy thao tác, khả năng cấp token mới, độ trễ AS, yêu cầu offline và nhu cầu thu hồi. Quan trọng là **giới hạn token theo thời gian, audience và scope đồng thời**, thay vì chỉ tối ưu một yếu tố.

## 11. Ba tình huống quyết định thiết kế

### Tình huống A: JWT access token bị copy từ log

Một API nhận JWT có chữ ký hợp lệ, `aud = orders-api`, `scope = orders.read`, còn 10 phút hiệu lực. Kẻ tấn công chép token từ log gateway và gọi lại API.

**Kết quả nếu API chỉ dùng bearer:** Token có thể được chấp nhận vì API kiểm tra chuỗi token hợp lệ chứ không xác thực máy cầm token. Chữ ký JWT không phát hiện việc token bị copy.

**Biện pháp:** Mask `Authorization` trong log, giảm TTL, hạn chế scope/audience, áp dụng quyền trên đơn hàng, theo dõi truy cập lạ; cân nhắc sender-constrained token khi rủi ro cao.

### Tình huống B: Access token của payments-api được gửi đến orders-api

Client có token được cấp đúng từ AS chung, chữ ký chuẩn, nhưng `aud = payments-api`. Client gửi token đó khi gọi `orders-api`.

**Kết quả đúng:** `orders-api` từ chối vì audience không khớp, kể cả token còn hiệu lực và scope có tên trùng. Nếu API chỉ kiểm tra chữ ký/issuer, hệ thống mắc lỗi *cross-resource token confusion*.

**Biện pháp:** Mỗi RS kiểm tra đúng audience/resource và loại token, giới hạn đường truyền token giữa các dịch vụ; cần delegation/token exchange rõ ràng khi một service gọi thay mặt service khác.

### Tình huống C: Opaque token đã revoke nhưng introspection bị cache

AS đã đánh dấu token `active = false`. Resource server vẫn giữ phản hồi introspection `active = true` từ trước trong cache 60 giây.

**Kết quả:** Trong cửa sổ cache, resource server có thể tiếp tục cho phép token nếu không có cơ chế invalidation. Opaque token không bảo đảm thu hồi tức thời chỉ nhờ định dạng.

**Biện pháp:** Xác định SLA thu hồi, TTL cache ngắn phù hợp, giới hạn TTL không vượt thời hạn token, cân nhắc không cache với tài nguyên có rủi ro cao.

## 12. Checklist khi xây dựng API dùng bearer token

1. **Đúng loại token:** API chỉ nhận access token được cấp đúng mục đích, không nhận ID token, refresh token hoặc assertion.
2. **Đúng nguồn tin cậy:** issuer, metadata/JWKS hoặc introspection endpoint được cấu hình và kiểm chứng; không tin URL/khóa do token tự khai.
3. **Đúng tài nguyên:** kiểm tra `aud`/resource binding, `exp`, `nbf` và policy thời gian; không nhận token dành cho API khác.
4. **Đúng quyền:** kiểm tra scope/role rồi kiểm tra quyền nghiệp vụ đến từng tài nguyên, tenant và hành động.
5. **Đúng cách truyền:** dùng `Authorization: Bearer ...` qua HTTPS; tránh query token, log token và truyền token qua redirect/host lạ.
6. **Đúng nơi lưu:** bảo vệ token trong browser/backend/mobile, kiểm soát XSS/CSRF khi liên quan, không đưa vào source code hoặc artifact.
7. **Đúng vòng đời:** TTL phù hợp, cơ chế xin token mới, revocation/introspection/cache, cách xử lý khi mất kết nối AS.
8. **Đúng cách báo lỗi:** trả 401/403 và `WWW-Authenticate` phù hợp; không tiết lộ token trong lỗi.
9. **Đúng mức bảo vệ:** với API rủi ro cao, đánh giá mTLS certificate-bound token hoặc DPoP và bảo đảm RS **thực sự** xác minh proof.

### Câu hỏi tự kiểm tra

**1. Một JWT access token có chữ ký RS256 hợp lệ có còn là bearer token không?**

Có, nếu bên nhận chỉ yêu cầu sở hữu token mà không xác minh một proof từ người gửi. RS256 chỉ chứng minh chữ ký issuer.

**2. “Bearer token” có nghĩa là token phải ở dạng JWT và payload đọc được không?**

Không. Bearer nói về ngữ nghĩa sử dụng; JWT hay opaque nói về định dạng.

**3. Có thể gửi ID token OIDC trong `Authorization: Bearer ...` để gọi orders-api không?**

Không nên và API phải từ chối nếu token không phải access token dành cho `orders-api`. Cú pháp header đúng không biến ID token thành access token.

**4. API trả `403 insufficient_scope` thì client nên gửi lại cùng token nhiều lần không?**

Không. Cần scope/ủy quyền hợp lệ mới hoặc thay đổi yêu cầu theo quyền hiện có.

**5. Nếu bật HTTPS nhưng token bị ghi vào access log, HTTPS có ngăn việc phát lại không?**

Không. HTTPS bảo vệ đường truyền, còn log bị lộ cho phép kẻ tấn công sao chép bearer token.

**6. DPoP proof chỉ cần đúng chữ ký là đủ chưa?**

Chưa. RS phải kiểm tra binding với access token, HTTP method/URI, thời gian, hash token, nonce khi áp dụng và chính sách chống replay.

## Tài liệu chuẩn tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): định nghĩa bearer, cách truyền token, header `WWW-Authenticate` và rủi ro bảo mật.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò client/AS/RS, token endpoint và `token_type`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc claims của JWT.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra opaque token và trạng thái `active`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): cơ chế thu hồi tại authorization server.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tránh nhầm mục đích token, thuật toán và nguồn khóa không đáng tin.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, issuer, audience và xác minh token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): chứng chỉ ràng buộc với access token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): bảo vệ chống token theft/replay bằng proof ký theo request.

**Điểm cần nhớ:** Bearer token là cơ chế cho phép **bên đang sở hữu chuỗi token** dùng quyền mà token đại diện. JWT, opaque, access token, refresh token và ID token thuộc các trục phân loại khác; không nên trộn lẫn. Bảo vệ bearer access token đòi hỏi xác minh đúng issuer, audience, thời hạn, scope và quyền nghiệp vụ, đồng thời giữ kín token trong truyền tải/lưu trữ, kiểm soát thu hồi và cân nhắc sender-constrained token khi cần chống phát lại.
