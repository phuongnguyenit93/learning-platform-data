# Điểm cuối thu hồi token

## Mục tiêu học tập

Trong chương **Revocation** của học phần **Token Security Fundamentals**, **điểm cuối thu hồi token** (*token revocation endpoint*) là một giao diện của **Authorization Server (AS)** để OAuth Client thông báo rằng một access token hoặc refresh token **không còn nên được sử dụng**. Đặc tả nền tảng là **RFC 7009 — OAuth 2.0 Token Revocation**.

Điểm khó nhất của chủ đề không phải chỉ là gửi một HTTP POST. Cần phân biệt **thu hồi token tại AS**, **khả năng Resource Server (RS) nhận biết trạng thái đó**, **thu hồi authorization grant**, **đăng xuất phiên** và **vòng đời của token đã phát hành**. Nếu một API chỉ kiểm tra chữ ký JWT và trường `exp`, yêu cầu revocation thành công tại AS **không mặc nhiên** khiến JWT ấy bị từ chối ngay tại API.

Sau bài này, bạn có thể:

1. Mô tả vai trò **revocation endpoint** và phân biệt nó với **token endpoint**, **introspection endpoint** và **OIDC logout**.
2. Viết request chuẩn RFC 7009 bằng **HTTP POST** với `token` và `token_type_hint`, kèm xác thực OAuth Client phù hợp.
3. Giải thích vì sao RFC 7009 trả **HTTP 200** cho cả token đã được thu hồi thành công và token không hợp lệ/không tồn tại, sau khi các kiểm tra cần thiết đã qua.
4. Phân biệt phạm vi tác động khi thu hồi **refresh token**, **access token**, **token family**, **authorization grant** hoặc vô hiệu hóa **client credential**.
5. Phân tích thu hồi **opaque token** bằng trạng thái tập trung/introspection và **JWT access token** bằng TTL, denylist hoặc kiểm tra state.
6. Xây dựng phương án **cache, propagation, concurrency, retry, refresh rotation và xử lý token bị đánh cắp/phát lại**.
7. Triển khai ví dụ Java/Spring Security, kiểm thử các lỗi xác thực Client, sai owner/tenant/scope và xử lý logout hoặc ngắt kết nối ứng dụng.

## 1. Thu hồi token là gì?

Trong OAuth 2.0, **access token** cho Client quyền truy cập Resource Server trong một phạm vi và thời hạn được cấp. **Refresh token** cho Client khả năng yêu cầu access token mới tại Authorization Server nếu grant và policy vẫn hợp lệ.

Khi người dùng ngắt kết nối một ứng dụng, một thiết bị bị mất, hoặc Client muốn bỏ quyền không còn dùng, chỉ **xóa token khỏi bộ nhớ Client** là chưa đủ nếu token vẫn còn được bên khác giữ. Token revocation là cơ chế **thông báo cho AS vô hiệu hóa token** theo hợp đồng OAuth.

~~~text
User:                user-123
Client:              spend-insights-web
Authorization Server: https://auth.example.test
Resource Server:      orders-api
Grant:                user đồng ý orders:read

Access token A:       token dùng để gọi Orders API, TTL 10 phút
Refresh token R:      credential dùng để xin access token mới

User chọn "Ngắt kết nối":
  -> Client/AS xử lý thu hồi R và grant liên quan
  -> Có thể cần thu hồi A hoặc kiểm tra trạng thái tại RS
  -> Client xóa token/session local
~~~

**Từ "đã thu hồi" phải luôn gắn với chủ thể và mức hiệu lực cụ thể.** Token R bị AS đánh dấu revoked không tự chứng minh mọi bản sao access token A đã bị tất cả Resource Server từ chối ngay tức thì.

### Thu hồi token so với hết hạn tự nhiên

| Cơ chế | Kích hoạt | Ý nghĩa |
|---|---|---|
| **Hết hạn `exp`/TTL** | Đồng hồ đạt thời hạn token. | Token không được chấp nhận sau hạn, theo clock-skew policy. |
| **Token revocation (RFC 7009)** | Client gửi token tới AS để yêu cầu vô hiệu hóa. | AS invalidates token/grant liên quan theo chính sách và khả năng hỗ trợ. |
| **Grant revocation** | User/admin/AS hủy ủy quyền gốc. | Không còn được cấp token mới dựa trên grant bị hủy. |
| **Refresh-token rotation** | Mỗi lần dùng refresh token phát token mới và vô hiệu bản trước. | Giảm khả năng lạm dụng token bị sao chép; reuse có thể kích hoạt thu hồi family. |
| **JWT signing key revocation** | Khóa ký AS bị lộ hoặc bị ngừng tin. | Ảnh hưởng những JWT được ký bằng khóa đó, có thể rộng hơn một user/Client. |
| **Logout** | Kết thúc session của user tại Client hoặc OP. | Không mặc nhiên tương đương thu hồi mọi token OAuth. |

## 2. Ai gọi endpoint và ai phải kiểm tra?

### Các vai trò

| Vai trò | Ví dụ | Trách nhiệm |
|---|---|---|
| **Resource Owner** | `user-123` | Có thể yêu cầu ngắt quyền theo UI quản lý ứng dụng đã kết nối. |
| **OAuth Client** | `spend-insights-web` | Lưu token an toàn, gọi revocation endpoint cho token thuộc Client, xóa trạng thái local. |
| **Authorization Server (AS)** | `auth.example.test` | Xác thực Client theo yêu cầu, kiểm tra token thuộc Client, vô hiệu hóa token/grant trong phạm vi phù hợp. |
| **Resource Server (RS)** | `orders-api` | Xác minh token mỗi request và nhận biết revocation nếu kiến trúc yêu cầu. |
| **Tenant administrator** | Admin tenant A | Có thể revoke Client/grant/sessions theo chính sách quản trị. |

Một **Client không tự quyền thu hồi token của bất kỳ Client nào khác** chỉ vì biết `client_id`. AS phải kiểm tra credential của confidential client khi áp dụng và **ràng buộc token với Client được phép yêu cầu thu hồi**.

### Đường đi điển hình

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as OAuth Client / BFF
    participant AS as Authorization Server
    participant RS as Orders API
    U->>C: Chọn Ngắt kết nối
    C->>C: Chặn dùng token mới trong session này
    C->>AS: POST /revoke token=R + client authentication
    AS->>AS: Xác minh Client, token và quan hệ grant
    AS->>AS: Vô hiệu R; cập nhật tokens liên quan theo policy
    AS-->>C: HTTP 200 khi đã xử lý hợp lệ
    C->>C: Xóa token, hủy local authorized-client state/session
    C-->>U: Trạng thái ngắt kết nối và hướng dẫn thích hợp
    Note over C,RS: JWT access token cũ có thể còn hiệu lực nếu RS chỉ xác minh offline
    C->>RS: Nếu có ai dùng bản sao A còn hạn
    RS->>RS: Verify chữ ký/exp và revocation state nếu có
    RS-->>C: Kết quả phụ thuộc cơ chế RS nhận trạng thái thu hồi
~~~

Trong triển khai thật, thứ tự **chặn phiên local, remote revoke và xóa dữ liệu local** cần được thiết kế để không tiếp tục sử dụng token khi user đã yêu cầu ngắt kết nối, nhưng cũng không làm mất mọi khả năng xử lý sự cố nếu remote revocation đang thất bại.

## 3. Phân biệt các endpoint thường bị nhầm

| Endpoint/chức năng | Request ví dụ | Kết quả chính |
|---|---|---|
| **Authorization endpoint** | `GET /authorize` qua browser theo flow. | User authentication/consent, phát code hoặc kết quả authorization. |
| **Token endpoint** | `POST /token` với `authorization_code`/`refresh_token`/`client_credentials`. | Cấp access token và có thể refresh/ID token. |
| **Revocation endpoint (RFC 7009)** | `POST /revoke`, form `token=...`. | AS vô hiệu token phù hợp, có thể ảnh hưởng grant/tokens liên quan. |
| **Introspection endpoint (RFC 7662)** | `POST /introspect` với `token=...`, RS xác thực theo policy. | Trả metadata/trạng thái token, thường có `active`. |
| **OIDC logout** | RP-initiated, front-/back-channel logout nếu hỗ trợ. | Kết thúc/đồng bộ phiên xác thực, không luôn là revocation token. |
| **Connected-app management** | UI tài khoản “Thu hồi ứng dụng”. | Phát sinh hành động admin/user-side để hủy grant, sessions/tokens theo thiết kế AS. |

**Revocation là thao tác làm mất hiệu lực; introspection là thao tác hỏi trạng thái.** Gọi introspection không tự thu hồi token, và gửi revocation request không tự trả về thông tin user/scope/audience như một introspection response.

### Chức năng nào xử lý loại token nào?

~~~text
Client -> AS token endpoint:
  client_credentials / authorization_code / refresh_token
  => xin token

Client -> AS revocation endpoint:
  token=<ACCESS_OR_REFRESH_TOKEN>
  => xin vô hiệu token

Resource Server -> AS introspection endpoint:
  token=<OPAQUE_OR_SUPPORTED_TOKEN>
  => xác minh trạng thái và metadata nếu AS cho phép
~~~

## 4. Tìm revocation endpoint từ đâu?

Client không nên suy đoán tùy ý rằng mọi AS đều sử dụng `/revoke`. Trong **OAuth 2.0 Authorization Server Metadata (RFC 8414)**, một AS có thể công bố:

~~~json
{
  "issuer": "https://auth.example.test",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "revocation_endpoint": "https://auth.example.test/oauth2/revoke",
  "revocation_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
~~~

Đây là **metadata minh họa**, không phải cấu hình của một nhà cung cấp cụ thể. Nơi đặt metadata và những trường có mặt tùy AS/profile; một số môi trường cấu hình endpoint thủ công theo hợp đồng đáng tin. Không lấy URL endpoint từ JWT `iss` **chưa xác minh** hoặc request do browser/Client khác gửi để tự động POST token nhạy cảm.

### Các yêu cầu về nguồn tin cậy

1. Xác định **trusted issuer** của AS qua cấu hình/onboarding an toàn.
2. Lấy endpoint từ metadata **đã được kiểm tra issuer/TLS** hoặc từ cấu hình do vận hành phê duyệt.
3. Yêu cầu HTTPS, xác minh chain và hostname của TLS certificate.
4. Không gửi token/client secret tới endpoint do user tự truyền vào query parameter.
5. Không tự theo redirect 301/302/307/308 đến host lạ khi gửi secret/token; API client nên ràng buộc điểm cuối.
6. Chỉ dùng phương thức client authentication phù hợp registration và metadata, không suy từ chuỗi tên endpoint.

**Rủi ro SSRF và credential exfiltration:** nếu một URL do attacker kiểm soát được dùng làm revocation endpoint, Client có thể vô tình gửi **refresh token còn hiệu lực và client secret** tới server attacker.

## 5. HTTP request chuẩn RFC 7009

### Nội dung tối thiểu

Client gửi **HTTP POST** đến revocation endpoint với body **`application/x-www-form-urlencoded`** chứa:

| Tham số | Bắt buộc? | Ý nghĩa |
|---|---|---|
| **`token`** | **Có**. | Chuỗi token mà Client yêu cầu thu hồi; có thể là refresh/access token theo AS. |
| **`token_type_hint`** | Không. | Gợi ý loại token, thường `refresh_token` hoặc `access_token`, hỗ trợ AS tra cứu nhanh hơn. |
| **Client authentication** | Theo client type/AS policy. | Confidential Client xác thực theo registration; public Client không có shared secret đáng tin. |

### Ví dụ thu hồi refresh token

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_ENCODED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<URL_FORM_ENCODED_REFRESH_TOKEN>&token_type_hint=refresh_token
~~~

Toàn bộ request phải chạy qua **HTTPS**. Chuỗi ở ngoặc nhọn là **placeholder**, không phải credential thật.

Với `client_secret_basic`, HTTP Basic sử dụng **Base64 chuẩn** trên `client_id:client_secret` sau khi **form-encode từng giá trị theo RFC 6749 `2.3.1`**, không phải Base64URL và không phải mã hóa bí mật. Dùng thư viện OAuth/HTTP đáng tin để tránh encode sai. Không log `Authorization` header.

### Ví dụ thu hồi access token

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_ENCODED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<URL_FORM_ENCODED_ACCESS_TOKEN>&token_type_hint=access_token
~~~

Việc gửi access token vào revocation endpoint **không bảo đảm** server hỗ trợ access-token revocation; RFC 7009 yêu cầu hỗ trợ refresh token revocation, còn hỗ trợ access token revocation là **SHOULD** và cần xem khả năng của AS.

### Những anti-pattern cần tránh

~~~text
GET /revoke?token=<REFRESH_TOKEN>
GET /revoke?client_secret=<SECRET>&token=<TOKEN>
POST body JSON {"token": "..."} khi AS chỉ hỗ trợ RFC 7009 form encoding
POST token=<TOKEN> tới URL do user/request cung cấp
Gửi "Authorization: Bearer <ACCESS_TOKEN>" tới RS và xem đó là revoke
Lưu full token hoặc Basic header trong audit log để debug
~~~

RFC 7009 có mô tả hỗ trợ cross-origin/JSONP tùy chọn ở phần riêng cho các môi trường lịch sử, nhưng **không nên lấy đó làm lý do thiết kế endpoint GET chứa secret/token**. Với triển khai hiện đại, ưu tiên **POST form qua HTTPS** và không để token xuất hiện trong URL.

## 6. AS phải kiểm tra Client và quan hệ sở hữu token

**Client authentication** và **authorization để revoke token** là hai câu hỏi khác nhau.

### Confidential client

Một BFF hoặc backend confidential client có thể dùng:

- `client_secret_basic` theo đăng ký.
- `private_key_jwt` khi AS hỗ trợ và đã đăng ký.
- mTLS client authentication hoặc phương thức mạnh hơn theo chính sách.

AS phải kiểm tra **client credential** đúng trước khi xử lý quyền của Client trên token. Một confidential Client đã bị vô hiệu secret không được tiếp tục revoke/xin token dưới danh tính cũ mà không có cơ chế nhận dạng phù hợp.

### Public client

SPA/native app thông thường không thể bảo vệ một shared client secret. Với public client, `client_id` là **định danh** chứ **không phải bằng chứng xác thực**. AS phải áp dụng quy tắc token binding/client association và chính sách revocation tương ứng; đừng tin người dùng chỉ biết client ID có quyền thu hồi token của người khác.

### Token không thuộc Client

~~~text
Client A: spend-insights-web
Client B: reports-worker

Refresh token Rb được AS cấp cho Client B.
Client A xác thực hợp lệ và gửi Rb tới /revoke.

=> AS phải kiểm tra Rb thuộc Client nào và không cho A
   thu hồi tùy ý token của B chỉ vì A biết một chuỗi.
~~~

Phản hồi lỗi chính xác cho trường hợp không đúng Client tùy quy tắc bảo mật và AS; RFC 7009 yêu cầu kiểm tra token được cấp cho Client yêu cầu thu hồi. **Không dùng cơ chế trả lỗi để làm lộ thông tin tồn tại của token** cho bên không có quyền.

### Một xác thực Client hợp lệ chưa đủ cấp scope

Nếu BFF thu hồi token của mình, hành động đó không cho BFF quyền truy cập token của tenant khác hoặc cấp thêm `payments:refund`. AS vẫn áp dụng client registration, grant policy và ranh giới tenant trong toàn bộ vòng đời authorization.

## 7. Phản hồi thành công: vì sao HTTP 200 cả với token không hợp lệ?

Một đặc điểm quan trọng của **RFC 7009** là:

> Sau các kiểm tra Client/request cần thiết, AS trả **HTTP 200** nếu token được thu hồi thành công **hoặc** token được trình không hợp lệ.

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

Phản hồi thành công **không cần body chứa claims** hay danh tính token. Việc trả cùng kết quả cho token đã hết hạn/không tồn tại giúp **giảm rò rỉ thông tin qua truy vấn xem token có tồn tại không**.

### Các trường hợp khác nhau nhưng cùng 200

| Tình huống | Phản hồi revocation điển hình |
|---|---|
| Token R đang active, request hợp lệ và được phép revoke | **200 OK** sau khi AS thực hiện revocation. |
| Token R đã bị revoke trước đó | **200 OK** sau khi xử lý phù hợp. |
| Token R đã hết hạn/không còn hợp lệ | **200 OK** khi các kiểm tra request/Client đã qua. |
| Chuỗi token không tồn tại trong hệ thống | **200 OK** trong ngữ cảnh request được phép xử lý. |

**Không diễn giải 200 là “token trước đây chắc chắn tồn tại”**, hoặc “mọi RS đã ngừng chấp nhận access token này”. 200 nói về **kết quả xử lý yêu cầu ở AS**, không phải báo cáo trạng thái phân tán của tất cả hệ thống.

### Idempotency theo ý nghĩa API

Một Client có thể gửi lại revocation request khi mạng lỗi hoặc không nhận được response. Nếu token đã bị vô hiệu, xử lý yêu cầu lần nữa không cần làm nó hợp lệ trở lại.

~~~text
POST revoke(R) -> AS xử lý nhưng response bị mất
POST revoke(R) -> token R đã revoked / invalid
HTTP 200        -> Client có thể hoàn tất cleanup
~~~

Tuy nhiên, **không retry vô hạn**, và không dùng `200 OK` để giả định đã hoàn tất **các tác dụng phụ cross-service** khi AS/RS có propagation delay.

## 8. Lỗi và `unsupported_token_type`

### Những lỗi quan trọng

| Lỗi/tình huống | Kết quả theo giao thức/chính sách | Hành động Client |
|---|---|---|
| Missing `token` hoặc body sai định dạng | OAuth error như `invalid_request`. | Sửa request, không retry mù. |
| Client authentication sai | `invalid_client` hoặc lỗi xác thực tương ứng. | Kiểm tra registration, secret/key/certificate; không bỏ xác thực. |
| Token thuộc Client khác | AS từ chối theo quy tắc client-token association. | Không cố revoke token của bên khác. |
| Token type không được endpoint hỗ trợ | **`unsupported_token_type`** (RFC 7009). | Xem khả năng AS/policy, không giả định access token đã bị revoke. |
| Token không tồn tại/hết hạn/đã revoked | **200 OK** sau kiểm tra thích hợp. | Kết thúc cleanup local nếu không còn yêu cầu khác. |
| Rate limit/AS unavailable | HTTP 429/5xx hoặc timeout tùy triển khai. | Bounded retry/backoff, theo dõi trạng thái không chắc chắn. |

### Ví dụ khi loại token không được hỗ trợ

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "unsupported_token_type"
}
~~~

**`unsupported_token_type` không chỉ vì Client gửi một `token_type_hint` lạ.** `token_type_hint` chỉ là **gợi ý tra cứu**, không phải nguồn xác định loại token chính thức. AS có thể bỏ qua hint và xác định loại thực dựa trên kho token/issuer.

### Một lỗi bảo mật cần tránh

~~~text
SAI:
  "Token có tồn tại và thuộc user-123, nhưng Client không đủ quyền"
  "Refresh token này còn 30 ngày"

ĐÚNG:
  Trả lỗi xác thực/ủy quyền phù hợp mà không tiết lộ
  trạng thái chi tiết của credential cho caller trái phép.
~~~

Thông điệp lỗi không nên chứa raw token, client secret, token owner hay dữ liệu cá nhân.

## 9. `token_type_hint` là gợi ý, không phải nguồn chân lý

RFC 7009 cho phép Client gửi:

~~~text
token_type_hint=refresh_token
token_type_hint=access_token
~~~

Mục đích: giúp AS có thể **chọn kho tra cứu phù hợp trước**. Khi hint sai, AS **không được lấy hint làm bằng chứng xác thực** và có thể tìm ở loại token khác theo cách triển khai/phạm vi hỗ trợ.

### Ví dụ

~~~text
Actual token:      refresh token R
Client's hint:     access_token

AS:
  xác thực client
  tra cứu token theo quy tắc an toàn
  xác định loại thực là refresh
  xử lý revocation theo loại thực, nếu hỗ trợ và được phép
~~~

| Sai lầm | Hậu quả |
|---|---|
| Xác định token type chỉ theo hint | Có thể xử lý sai kho, nhầm policy hoặc báo trạng thái sai. |
| Coi `access_token` hint chứng minh request được quyền revoke mọi access token | Bỏ qua association với Client/grant. |
| In hint và raw token vào log | Tăng rủi ro credential leakage. |
| Trả thông tin nội bộ chi tiết cho hint sai | Gợi ý cách đoán token type/state. |

### Token format không phải token purpose

Một token có ba phần giống JWT **không tự chứng minh nó là access token**, và một chuỗi opaque **không chắc chắn là refresh token**. AS phải biết loại token dựa trên phát hành/trạng thái; RS chỉ chấp nhận **access token đúng profile và audience**, không chấp nhận refresh/ID token làm bearer credential cho API.

## 10. Thu hồi refresh token và access token tác động khác nhau

### Revoking refresh token

Refresh token là credential dùng để duy trì quyền xin access token mới; do đó thu hồi R thường:

1. Chặn việc dùng **R** tại token endpoint từ lần refresh tiếp theo.
2. Có thể ảnh hưởng token/grant liên quan theo cơ chế và chính sách AS.
3. Nếu AS hỗ trợ access token revocation, **RFC 7009 khuyến nghị (`SHOULD`)** AS cũng vô hiệu hóa access tokens dựa trên cùng authorization grant khi refresh token được revoke.

### Revoking access token

Thu hồi A nhằm chặn **token A** được RS chấp nhận theo cơ chế của AS/RS. Theo RFC 7009, khi access token được revoke, AS **MAY** thu hồi refresh token liên quan.

| Token được gửi tới /revoke | Tác động được kỳ vọng | Điều không được mặc định |
|---|---|---|
| **Refresh token R** | R không thể đổi token mới sau khi revoke có hiệu lực. | Mọi JWT access token đã cấp lập tức chết ở RS offline. |
| **Access token A** | A bị vô hiệu nếu AS hỗ trợ access-token revocation và RS thực thi trạng thái đó. | Refresh token R và mọi token khác luôn bị revoke. |
| **Token R đã rotated** | Xử lý theo trạng thái token family và reuse policy. | Chỉ gọi revoke R cũ là chắc chắn revoke token R mới đang giữ bởi attacker. |
| **Grant cấp quyền cho Client** | Có thể chặn cả family/authorization dựa trên chính sách. | Logout của Client hoặc dữ liệu đã tải về tự biến mất. |

### Sơ đồ quan hệ

~~~mermaid
flowchart TD
    G["Authorization grant cho user/client/resource/scope"] --> R["Refresh token R"]
    G --> A1["Access token A1"]
    R --> A2["Access token A2 sau refresh"]
    R --> R2["Refresh token R2 sau rotation"]
    R2 --> A3["Access token A3"]
    X["Revocation event"] --> P{"Chính sách AS"}
    P -->|Revoke R hoặc token family| R
    P -->|Có thể cascade| A1
    P -->|Có thể cascade| A2
    P -->|Có thể cascade| R2
    P -->|Có thể cascade| A3
~~~

**Cascade cụ thể không giống nhau ở mọi AS.** Khi thiết kế disconnect, phải biết hệ thống thu hồi **một token**, **một family** hay **một grant**, và resource servers nhận biết thay đổi trong bao lâu.

## 11. Opaque access token: revocation và introspection

Với **opaque access token**, chuỗi token không tự mang đầy đủ claims để RS xác minh offline. AS có thể lưu trạng thái phát hành và thu hồi trong một kho đáng tin.

### Luồng introspection

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>RS: GET /orders, Bearer opaque token A
    RS->>AS: POST /introspect token=A + RS auth
    AS-->>RS: active=true, iss/client/aud/scope/exp theo hợp đồng
    RS->>RS: Kiểm tra audience/scope/tenant/owner
    RS-->>C: Trả dữ liệu nếu được phép
    C->>AS: POST /revoke token=A + client auth
    AS->>AS: Đánh dấu A revoked
    C->>RS: Dùng lại token A
    RS->>AS: POST /introspect token=A nếu cache không che trạng thái
    AS-->>RS: active=false
    RS-->>C: Từ chối request
~~~

### Response introspection minh họa

~~~json
{
  "active": false
}
~~~

**`active=false` là kết quả introspection**, **không phải body response của revocation endpoint**. AS có thể giấu thông tin token trong introspection nếu token không hợp lệ hoặc caller không đủ quyền.

### Tác động của cache

Nếu RS cache `active=true` trong 60 giây, AS revocation thành công tại T0 không đảm bảo RS biết token bị revoke ngay tại T0. Cửa sổ độ trễ phụ thuộc:

~~~text
revocation propagation latency
  ~= token store update
     + AS/RS replication
     + introspection cache TTL
     + request processing delay
~~~

Đây là mô hình khái niệm, **không phải công thức SLA cố định**. Với endpoint có rủi ro cao, có thể giảm cache TTL, kiểm tra trạng thái trực tiếp hoặc sử dụng event-driven invalidation theo thiết kế.

### Nhược điểm cần đánh đổi

Introspection làm RS phụ thuộc nhiều hơn vào AS/network. Nếu AS tạm lỗi, RS cần **quy tắc rõ ràng cho availability vs security**: không tự động bỏ qua token validation hoặc chấp nhận mọi token vì introspection thất bại.

## 12. JWT access token: vì sao ký đúng vẫn có thể bị revoke?

Một JWT access token có thể chứa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "spend-insights-web",
  "scope": "orders:read",
  "jti": "jwt-example-a1",
  "iat": 1893456000,
  "exp": 1893456600
}
~~~

Đây là payload **minh họa**, không phải JWT được ký có thể dùng thật. Nếu RS chỉ kiểm tra **signature, issuer, audience, time và scope**, token vẫn có thể được chấp nhận tới hạn `exp` **dù AS đã đánh dấu grant revoked**.

### Ba thiết kế phổ biến

| Thiết kế | Cách xử lý revocation | Đánh đổi |
|---|---|---|
| **JWT TTL ngắn + không tra state** | Token đã cấp hết giá trị theo `exp`; việc revoke chủ yếu chặn refresh/cấp mới. | Đơn giản, độ trễ thấp nhưng có cửa sổ token cũ còn dùng được. |
| **JWT + denylist/jti/token fingerprint** | RS kiểm tra JWT hợp lệ rồi tra trạng thái revoke của token/grant. | Phản ứng nhanh hơn, đổi lại storage/cache/synchronization. |
| **JWT + introspection/status check** | RS hỏi AS hoặc một nguồn trạng thái đáng tin khi cần. | Kiểm soát thời gian thực hơn, tốn network và cần availability policy. |

### Denylist theo `jti`

~~~text
Trusted JWT:
  iss = https://auth.example.test
  aud = orders-api
  jti = a1
  exp = T+600

Revocation store:
  revoked[(issuer, jti)] = expires_at

RS check:
  1. Verify signature, issuer, audience, token type và exp/nbf
  2. Kiểm tra revoked[(issuer, jti)]
  3. Kiểm tra scope, subject, tenant và quyền trên object
  4. Deny nếu revoked hoặc authorization không đủ
~~~

**Đừng lấy `jti` từ JWT chưa được verify làm bằng chứng token thật.** Nếu token issuer không đảm bảo `jti` duy nhất/đúng profile, hệ thống có thể dùng **hash token có chủ đích**, grant ID hoặc token version kết hợp identity để tránh collision. Denylist phải lưu đủ lâu đến khi token tương ứng hết hạn, và không cần giữ token plaintext.

### Grant version / subject version

Một mô hình khác là dùng **security version** ở phía AS/RS:

~~~text
JWT grant_version = 7
Current grant_version for (user-123, client, tenant, resource) = 8
=> Reject token version 7
~~~

Thiết kế này cần lookup trạng thái đáng tin và xử lý concurrency/cache, **không mặc định có trong RFC 7009**. Version này phải được định nghĩa rõ theo grant/client/tenant thay vì một biến global gây logout nhầm toàn tổ chức.

## 13. Refresh token rotation, reuse detection và thu hồi token family

**Refresh token rotation** giảm khả năng sử dụng lâu dài một refresh token bị sao chép:

~~~text
Token R1 active

Client hợp lệ gửi R1 -> AS trả A2 và R2
AS đánh dấu R1 consumed/revoked

Attacker gửi lại R1:
  => Phát hiện reuse hoặc replay theo chính sách AS
  => Có thể thu hồi R2/token family và yêu cầu user kết nối lại
~~~

### Vì sao chỉ revoke R1 có thể chưa đủ?

Nếu attacker đã kịp dùng R1 để nhận R2 trước Client hợp lệ, R1 đã hết hiệu lực nhưng **R2 mới là credential nguy hiểm**. Một yêu cầu revoke đối với **R1 cũ** không nên được xem là đã vô hiệu hóa mọi descendant trừ khi AS có **token-family lineage/reuse policy** tương ứng.

### State machine minh họa

~~~mermaid
stateDiagram-v2
    [*] --> Active: Refresh token R1 issued
    Active --> Rotated: R1 used; issue R2
    Active --> Revoked: Explicit revocation
    Rotated --> ReuseDetected: R1 presented again
    ReuseDetected --> FamilyRevoked: Policy revokes family/grant
    Revoked --> [*]
    FamilyRevoked --> [*]
~~~

### Các điều kiện cần xem

1. **Atomic rotation:** hai refresh request đồng thời không được tạo hai nhánh token family ngoài ý muốn.
2. **Reuse signal:** phân biệt lỗi mạng/retry với credential theft trong phạm vi policy, không biến retry hợp lệ thành cơ hội attacker dùng lại vô hạn.
3. **Client binding:** refresh token không được dùng bởi Client khác.
4. **Sender-constraining:** public client cần refresh token rotation hoặc sender-constraining theo BCP/profile áp dụng.
5. **Grant revoke:** user/admin ngắt quyền cần xác định và thu hồi credential family phù hợp, không chỉ bản sao đang nằm trong một tab.
6. **Audit:** sự kiện rotation/reuse có client/grant/token family ID **không phải raw refresh token**.

Refresh token có độ nhạy cảm đặc biệt vì nó dùng để **xin access token mới**. Không gửi refresh token tới RS và không lưu nó dưới dạng log hoặc query URL.

## 14. Logout, disconnect, revoke và delete token không giống nhau

### Bốn hành động độc lập

| Người dùng/chương trình làm gì? | Tác động trực tiếp | Điều không được mặc định |
|---|---|---|
| **Xóa access token local** | Client không còn dùng bản sao ấy trong trạng thái hiện tại. | Token ở attacker hoặc browser khác tự bị AS vô hiệu. |
| **Logout ở Client/BFF** | Kết thúc phiên ứng dụng, xóa cookie/session và state phù hợp. | Refresh token tại AS tự bị revoke. |
| **Logout ở OpenID Provider (OIDC)** | Kết thúc phiên đăng nhập OP theo luồng hỗ trợ. | Mọi access token của mọi Client tự bị thu hồi. |
| **Revoke token tại AS (RFC 7009)** | Vô hiệu token được trình và token/grant liên quan theo chính sách. | Mọi JWT offline đã cấp bị từ chối tức thời. |
| **Disconnect ứng dụng đã kết nối** | Thường hủy grant và tài nguyên phiên/refresh token tương ứng. | Client phải xóa dữ liệu đã tải trước đó nếu chưa có cơ chế thực thi. |

### Logout BFF nên thực hiện những gì?

~~~text
User click "Disconnect":
  1. Đánh dấu local connection không còn được sử dụng.
  2. Xác định refresh/access token cần revoke từ token store an toàn.
  3. Gửi yêu cầu revoke đến AS bằng client auth đúng.
  4. Xử lý response, timeout hoặc lỗi xác thực.
  5. Xóa/hủy local tokens + session/cookie theo policy.
  6. Nếu remote revoke chưa chắc thành công:
     ghi trạng thái sự cố an toàn, retry bounded qua job có kiểm soát,
     không tiếp tục dùng token cho API.
  7. Nếu yêu cầu thu hồi access token ngay, kiểm tra RS state/denylist.
~~~

**Không được nói “tất cả token đã bị thu hồi” nếu chỉ xóa cache phía Client.** UI nên phân biệt “Đã ngắt kết nối tại ứng dụng này” với “AS đã xác nhận revocation” và thông tin giới hạn hiệu lực nếu còn.

## 15. Endpoint revocation không phải quyền của Resource Server

Một Resource Server không nên tự thay thế AS bằng cách cung cấp endpoint kiểu:

~~~text
POST /orders/revoke?access_token=...
~~~

rồi gọi đó là RFC 7009 nếu nó không thực hiện hợp đồng OAuth tại AS. RS có thể có **API nội bộ để vô hiệu token/session** hoặc nhận sự kiện thu hồi, nhưng **revocation endpoint chuẩn là chức năng của AS**.

### Hợp đồng RS đối với token đã revoked

~~~text
Request:
  Authorization: Bearer <ACCESS_TOKEN>

RS:
  -> verify issuer/signature or introspection
  -> verify token type, aud, exp/nbf, scope
  -> verify revocation state if required by design
  -> verify object owner/tenant/action
  -> reject when token inactive/revoked/unauthorized
~~~

Ví dụ, token có `aud=orders-api`, `scope=orders:read`, `sub=user-123` vẫn **không cho quyền đọc order của tenant-b** nếu dữ liệu thuộc tenant khác. Revocation hỗ trợ vòng đời credential, còn phân quyền object là trách nhiệm riêng của RS.

## 16. Bảo mật revocation endpoint

Revocation endpoint **nhận credential nhạy cảm**. Bảo mật của nó cần tương xứng với token endpoint.

### Transport và HTTP

- Dùng **HTTPS/TLS** với xác minh server certificate.
- Dùng **POST form**, không đặt token/client secret trong query string, URL path hoặc browser history.
- Không ghi token, Authorization header hoặc request body đầy đủ vào access log/tracing/APM.
- Giới hạn request body size, token length và thời gian xử lý; chống request flooding.
- Không cho server **follow arbitrary redirect** khi gửi token/secret sang host khác.
- Chỉ nhận dạng Client bằng phương thức hợp lệ theo registration; `client_id` không phải secret.
- Dùng `Cache-Control: no-store` cho response phù hợp, tránh cache thông tin không cần thiết.

### CORS và CSRF

RFC 7009 có nêu khả năng hỗ trợ các kiểu **cross-origin clients** tùy triển khai. Tuy nhiên:

- **CORS không phải cơ chế authentication** và không chứng minh caller được revoke token.
- Không mở `Access-Control-Allow-Origin: *` cùng credentialed cookies/headers để mọi website gửi yêu cầu nhạy cảm.
- Với confidential BFF, secret nên ở backend và browser gọi **BFF API** trong phiên đã bảo vệ, không gửi client secret trực tiếp từ JavaScript.
- Một endpoint AS nhận **client authentication/token trong body** có threat model CSRF khác trang quản lý tài khoản dựa trên cookie; nếu có browser cookie/session mutation, phải phân tích CSRF riêng.
- Không tắt CSRF protection trên **UI “Ngắt kết nối”** của user chỉ vì remote revocation endpoint dùng POST.

### Abuse và enumeration

~~~text
Attacker mục tiêu:
  thử hàng triệu chuỗi token và đo:
  - token có tồn tại hay không
  - token thuộc Client nào
  - token type, account, scope và lifetime

Phòng vệ:
  200 đồng nhất cho invalid token theo RFC 7009 sau kiểm tra phù hợp
  client authentication/association
  giới hạn tốc độ, độ dài, tài nguyên lookup
  audit với metadata không nhạy cảm
  không lộ token state trong thông báo lỗi
~~~

Thời gian xử lý cũng có thể lộ thông tin nếu phân nhánh quá khác biệt; cân nhắc thiết kế lookup và timing phù hợp rủi ro, không phải lúc nào cũng cần cố định thời gian toàn bộ HTTP request.

## 17. Java: gọi RFC 7009 revocation endpoint an toàn

Đoạn Java dưới đây minh họa một **confidential backend** sử dụng JDK HTTP Client. Secret được **truyền từ cấu hình runtime/secret manager**, không hardcode. Endpoint được lấy từ **trusted issuer configuration**, không được lấy từ input user.

### Ví dụ Java 17+

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.Objects;

final class OAuthTokenRevoker {
    private final HttpClient httpClient = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private final URI revocationEndpoint;
    private final String clientId;
    private final String clientSecret;

    OAuthTokenRevoker(URI trustedEndpoint,
                      String runtimeClientId,
                      String secretFromProtectedRuntime) {
        Objects.requireNonNull(trustedEndpoint);
        if (!"https".equalsIgnoreCase(trustedEndpoint.getScheme())) {
            throw new IllegalArgumentException("HTTPS required");
        }
        revocationEndpoint = trustedEndpoint;
        clientId = Objects.requireNonNull(runtimeClientId);
        clientSecret = Objects.requireNonNull(secretFromProtectedRuntime);
    }

    private static String encode(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }

    int revoke(String token, String tokenTypeHint)
            throws IOException, InterruptedException {
        Objects.requireNonNull(token);
        if (token.isBlank()) {
            throw new IllegalArgumentException("Missing token");
        }
        if (!"access_token".equals(tokenTypeHint)
                && !"refresh_token".equals(tokenTypeHint)) {
            throw new IllegalArgumentException("Unsupported hint");
        }

        // OAuth 2.0 RFC 6749 2.3.1:
        // form-encode client_id and client_secret independently,
        // then join with ":" and encode using STANDARD Base64.
        String basicInput = encode(clientId) + ":" + encode(clientSecret);
        String basic = Base64.getEncoder().encodeToString(
                basicInput.getBytes(StandardCharsets.US_ASCII));
        String formBody = "token=" + encode(token)
                + "&token_type_hint=" + encode(tokenTypeHint);

        HttpRequest request = HttpRequest.newBuilder(revocationEndpoint)
                .timeout(Duration.ofSeconds(10))
                .header("Authorization", "Basic " + basic)
                .header("Content-Type",
                        "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString(
                        formBody, StandardCharsets.UTF_8))
                .build();

        // Do not log request, Authorization header, token or response body.
        HttpResponse<Void> response = httpClient.send(
                request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }
}
~~~

### Cách gọi từ backend

~~~java
// Values must be provisioned by trusted application configuration.
URI trustedRevocationEndpoint =
        URI.create("https://auth.example.test/oauth2/revoke");
String clientId = runtimeConfig.clientId();
String clientSecret = secretManager.currentClientSecret();
String refreshToken = serverSideTokenStore.loadRefreshToken();

OAuthTokenRevoker revoker = new OAuthTokenRevoker(
        trustedRevocationEndpoint, clientId, clientSecret);

int status = revoker.revoke(refreshToken, "refresh_token");
if (status == 200) {
    serverSideTokenStore.markGrantRevocationRequestAccepted();
} else {
    // Classify 400 unsupported_token_type, 401 invalid_client,
    // 429/5xx and unexpected statuses without printing credentials.
    incidentTracker.recordSafeRevocationFailure(status);
}
~~~

Đoạn gọi trên là **mã minh họa**, giả định các object `runtimeConfig`, `secretManager`, `serverSideTokenStore` và `incidentTracker` đã được hệ thống cung cấp. Trình tự xử lý session/cleanup/remote failure phải theo kiến trúc ứng dụng; không coi đây là một service sản xuất hoàn chỉnh.

### Giới hạn quan trọng

1. **Không đưa client secret/token vào log**, kể cả exception context hoặc HTTP wire debug.
2. Có thể cần client authentication khác `client_secret_basic` như `private_key_jwt` hoặc mTLS; khi đó **không dùng Basic**.
3. Dữ liệu secret ở `String` có thể tồn tại trong memory lâu hơn mong muốn; lựa chọn thư viện/secret manager cần phù hợp threat model.
4. URL phải được **allowlist từ issuer metadata/cấu hình đáng tin**. Kiểm tra `https` riêng lẻ không ngăn gửi token tới host attacker có HTTPS.
5. HTTP client ở ví dụ không follow redirect; request timeout/IOException là **trạng thái chưa rõ AS đã revoke hay chưa**, không đồng nghĩa thất bại chắc chắn.
6. Chỉ kiểm tra `200` chưa bảo đảm mọi RS đã áp dụng revocation; cần observability và chính sách propagation riêng.
7. Trong code production, ưu tiên **OAuth2 client library** có hỗ trợ revocation/method đã đăng ký hơn việc tự lắp request và Basic header.

## 18. Spring Security: xóa local authorized client không phải remote revoke

Trong Spring Security OAuth2 Client, **`OAuth2AuthorizedClientService`** hoặc repository liên quan có thể quản lý access/refresh token của Client. Xóa authorized-client record local **không đồng nghĩa gọi RFC 7009 revocation endpoint**.

### Ví dụ xóa trạng thái local

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

final class AuthorizedClientCleanup {
    private final OAuth2AuthorizedClientService clients;

    AuthorizedClientCleanup(OAuth2AuthorizedClientService clients) {
        this.clients = clients;
    }

    void removeLocalConnection(String registrationId,
                               String principalName) {
        clients.removeAuthorizedClient(registrationId, principalName);
    }
}
~~~

**`removeAuthorizedClient` chỉ xóa bản ghi local trong service đó**. Nếu refresh token vẫn active ở AS và tồn tại bản sao bên khác, nó có thể tiếp tục bị lạm dụng. Để disconnect đúng mục tiêu:

~~~text
AS remote revocation (RFC 7009) + xử lý lỗi/timeout
          ↓
local authorized-client/session cleanup
          ↓
chính sách thông báo và chặn dùng token
          ↓
RS revocation/TTL enforcement theo kiến trúc
~~~

### Spring Resource Server với opaque token

Nếu API sử dụng introspection, Spring Boot có thể cấu hình (ví dụ cấu trúc Spring Security):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

`${INTROSPECTION_CLIENT_SECRET}` chỉ là **placeholder lấy secret từ môi trường/secret manager**, không phải giá trị để commit. **Introspection client** là principal được AS cho phép hỏi token state, không phải bản sao của OAuth Client đang sử dụng token.

### Nếu dùng JWT Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Issuer configuration hỗ trợ xác minh chữ ký/issuer theo framework; **không tự bổ sung revocation denylist** và không thể suy audience đúng cho mọi API nếu chưa cấu hình validator thích hợp. Với JWT, cần chủ động thiết kế `aud`, token type, scope, tenant và cơ chế revocation state nếu yêu cầu thu hồi nhanh.

## 19. AS xử lý revocation request: pseudocode

Đây là **mô hình thuật toán cấp cao** cho Authorization Server, không phải implementation đủ để tự xây hệ thống token. Mỗi AS có cách lưu token, grant, refresh family và quyền Client khác nhau.

~~~text
revokeToken(request):
    requireHttpsAndValidFormPost(request)

    client = authenticateClientPerRegistrationWhenRequired(request)
    if client authentication failed:
        return appropriateClientAuthError

    presentedToken = requireFormParameter("token")
    hint = optionalFormParameter("token_type_hint")
    if malformed request:
        return invalid_request

    tokenRecord = lookupTokenSafely(presentedToken, hint)
    if tokenRecord not found, expired or alreadyInvalid:
        return HTTP 200

    if tokenRecord.clientId != client.id:
        return accessDeniedOrAppropriateOAuthErrorWithoutDisclosure

    if tokenRecord.type not supported by AS revocation:
        return unsupported_token_type

    grant = lookupTrustedGrant(tokenRecord.grantId)
    if grant requires extra checks and policy denies:
        return appropriateError

    atomicallyMarkTokenRevoked(tokenRecord)
    if tokenRecord.type == refresh_token:
        applyRefreshFamilyAndRelatedAccessRevocationPolicy(grant)
    if tokenRecord.type == access_token:
        applyAccessToRefreshCascadePolicyIfConfigured(grant)

    publishRevocationStateToTrustedConsumersAsConfigured()
    return HTTP 200
~~~

### Những chỗ dễ sai

- AS phải **xác thực và kiểm tra client-token association** trước khi làm lộ trạng thái token.
- `token_type_hint` chỉ gợi ý cách tra cứu; **không cho phép ép loại token hoặc bypass policy**.
- Cần xử lý **đồng thời**: revoke và refresh có thể xảy ra cùng lúc; thứ tự commit/locking/atomic update phải được định nghĩa.
- **Không mở rộng** revocation từ một Client sang grant của Client khác vì trùng user hoặc token prefix.
- Không lưu raw token không cần thiết; có thể dùng token hash/verifier, key quản lý riêng.
- Phản hồi **200** không cần mô tả token existed/revoked để tránh enumeration.
- Không “gửi sự kiện revoke xong” rồi coi mọi RS đã áp dụng nếu sự kiện chỉ được queue; cần quản lý eventual consistency và failure.

## 20. Race conditions, cache và propagation

Revocation thường diễn ra trong hệ thống phân tán:

~~~text
T0: User chọn disconnect
T1: Client gửi POST /revoke(R1)
T2: AS primary store đánh dấu R1 revoked
T3: Replica/edge cache chưa nhận thay đổi
T4: Một refresh request hoặc API request song song xuất hiện
T5: Mọi thành phần hội tụ về trạng thái revoked
~~~

### Các cuộc đua quan trọng

| Race | Nguy cơ | Giảm rủi ro |
|---|---|---|
| **Refresh vs revoke** | R1 được dùng đồng thời với revoke, phát R2 sau khi user muốn ngắt quyền. | Transaction/locking/version check atomically trên grant/family. |
| **Two revoke requests** | Trùng xử lý hoặc ghi log sai “already revoked error”. | Idempotent state, 200 cho token invalid. |
| **Opaque introspection cache** | RS dùng `active=true` cũ sau AS revoke. | TTL nhỏ cho dữ liệu nhạy cảm, push invalidation khi cần. |
| **JWT offline verification** | RS tiếp tục tin signature/`exp`. | TTL ngắn hoặc denylist/grant version/state check. |
| **Multiple AS nodes** | Node A revoked nhưng node B vẫn nhận refresh token. | Shared authoritative state/consistent update. |
| **Token store cleanup** | Xóa token row quá sớm làm mất lineage/forensic. | Retention và tombstone phù hợp, không lưu token plaintext thừa. |
| **Network timeout** | Client không biết AS đã xử lý chưa. | Retry có giới hạn, correlation ID, không fail-open. |

### "Thu hồi ngay lập tức" phải có định nghĩa đo được

Nếu nghiệp vụ yêu cầu revoke trong 5 giây, cần xác định:

- Mốc bắt đầu: user bấm, Client gửi, hay AS commit?
- Mốc kết thúc: AS không cấp refresh, tất cả RS từ chối access token, hay cả hai?
- Cách đo: synthetic test qua từng region/edge cache và log trạng thái an toàn.
- Các kênh ngoại lệ: offline device, network partition, JWT tự xác minh, cache TTL dài.

Không công bố SLA “thu hồi tức thời” nếu kiến trúc dựa trên JWT offline còn hạn vài phút.

## 21. Revoke trong BFF, SPA, native và Client Credentials

### BFF (Backend for Frontend)

BFF có thể giữ access/refresh token **phía server**, browser chỉ giữ session cookie `HttpOnly; Secure; SameSite`. Khi user disconnect:

1. BFF nhận thao tác user trong phiên đã xác thực và CSRF-protected.
2. BFF xác định token/grant thuộc **đúng account, tenant và Client**.
3. BFF gọi AS revocation endpoint với client authentication thích hợp.
4. BFF hủy session/local authorized-client state, không gửi refresh token tới browser.
5. BFF xử lý remote timeout/RS propagation theo chính sách.

**HttpOnly không ngăn XSS thực hiện request trong phiên**, và SameSite không thay CSRF protection trên endpoint disconnect.

### SPA/public browser Client

SPA thường là **public client**, không giữ client secret lâu dài. Nếu AS hỗ trợ revocation từ public client, cần tuân thủ policy, CORS và token association. Một số kiến trúc đưa revocation qua BFF/Token Handler để tránh JavaScript phải giữ refresh token trong browser.

Không nhúng `client_secret` vào bundle và giả rằng việc minify/obfuscate sẽ bảo vệ credential.

### Mobile/native Client

Native Client dùng storage được nền tảng hỗ trợ để giữ token, ngừng sử dụng token ngay khi user logout. Nếu có mạng, gọi revocation endpoint theo registration và xóa credential local; nếu offline, lưu ý việc hủy local token **không chắc** đã vô hiệu bản sao trên AS, cần kế hoạch đồng bộ.

### Client Credentials grant

Trong grant `client_credentials`, Client thường chỉ nhận access token. **RFC 6749 khuyến nghị (`SHOULD NOT`)** không cấp refresh token cho loại grant này. Nếu muốn hủy token service, có thể revoke access token **nếu AS hỗ trợ** và áp dụng policy; muốn ngăn xin token mới, cần **vô hiệu Client registration/credential hoặc policy**.

**Thu hồi một access token không tự vô hiệu client secret**. Service còn credential hợp lệ có thể xin token khác trong quyền được phép, nên khóa Client/secret nếu phát hiện compromised workload.

## 22. Multi-tenant và giới hạn quyền thu hồi

Giả sử AS quản lý hai tenant:

~~~text
Tenant A:
    user-123
    client = reports-web
    grant = reports:read
    refresh token = RA

Tenant B:
    user-123 (cùng identifier được mapping khác)
    client = reports-web
    grant = reports:export
    refresh token = RB
~~~

### Những giới hạn cần thực thi

1. **User/Client/tenant/grant là những chiều khác nhau**; không revoke nhầm tenant B chỉ vì cùng `user_id` dạng chuỗi.
2. Admin tenant A không có quyền ngắt grant của tenant B nếu policy không cấp rõ.
3. Credential của Client A không được dùng để thao tác token Client B.
4. RS kiểm tra **tenant của dữ liệu thật**, không tin header `X-Tenant-Id` do caller tự khai.
5. Token family, denylist và audit cần namespace theo **trusted issuer, client, subject/tenant, grant** thích hợp.
6. Nếu muốn “revoke all user sessions”, xác định rõ **phạm vi**: chỉ một Client, một tenant, một thiết bị hay toàn bộ identity provider.

### Ví dụ sai phạm quyền tại API

~~~text
Revocation thành công đối với grant user-123 / tenant-a.
Một access token khác của tenant-b vẫn còn hạn.

RS không được:
  nhận token tenant-b để đọc dữ liệu tenant-a;
  coi user-123 có quyền mọi tenant;
  lược bỏ object authorization vì token còn active.
~~~

## 23. DPoP, mTLS và replay: revocation không thay proof-of-possession

**Bearer access token** bị sao chép có thể bị attacker sử dụng trong thời gian còn hiệu lực, đúng audience/scope và không bị RS từ chối. Revocation giảm thời gian lạm dụng **nếu RS nhận biết đủ sớm**, nhưng không ngăn mọi lần phát lại trước khi trạng thái được cập nhật.

### Các lớp bảo vệ

| Cơ chế | Điểm bảo vệ | Không tự giải quyết |
|---|---|---|
| **Revocation** | Hủy hiệu lực token/grant trong AS/RS state. | Attacker dùng token trước khi revoke kịp lan truyền. |
| **TTL ngắn** | Giảm cửa sổ bearer replay. | Không thu hồi tức thời token chưa hết hạn. |
| **DPoP (RFC 9449)** | Access token ràng buộc với khóa proof và request. | Script/malware vẫn có thể dùng khóa trên thiết bị bị chiếm. |
| **mTLS-bound access token (RFC 8705)** | Token ràng buộc với chứng chỉ Client tại RS. | Private key/certificate bị chiếm hoặc TLS termination lỗi. |
| **Scope/audience** | Hạn chế API và hành động được phép. | Không xác minh owner/tenant của từng object. |
| **Object authorization** | Quyền trên bản ghi và ngữ cảnh nghiệp vụ. | Credential không bị đánh cắp. |

### Token binding có giúp revoke dễ hơn?

Sender-constraining giảm giá trị của **bản sao token không đi cùng khóa**, nhưng **không thay revocation** khi user mất quyền, thiết bị bị mất, private key bị lộ hoặc Client bị vô hiệu. Nếu attacker có cả token và khả năng ký proof, cần thu hồi token/grant/key theo mức rủi ro.

### DPoP không dùng `jti` theo cùng một nghĩa

JWT access token có thể có `jti` để định danh token. DPoP proof cũng có `jti` riêng để chống phát lại proof. **Hai giá trị này không cùng mục đích**; denylist access token không được nhầm với replay cache của DPoP proof.

## 24. Quan sát vận hành và incident response

### Trường audit nên có

~~~json
{
  "event": "oauth.token_revocation",
  "issuer": "https://auth.example.test",
  "client_id": "spend-insights-web",
  "environment": "production",
  "token_kind": "refresh_token",
  "result": "accepted",
  "grant_reference": "grant-safe-id",
  "tenant": "tenant-a",
  "correlation_id": "revocation-event-42"
}
~~~

Đây là **mẫu audit minh họa**. Không ghi:

~~~text
access_token=<SECRET>
refresh_token=<SECRET>
Authorization: Basic <CLIENT_CREDENTIALS>
Authorization: Bearer <ACCESS_TOKEN>
raw token hash có thể bị sử dụng như credential trong hệ thống yếu
session cookie, PKCE verifier, private key
~~~

Một token fingerprint **không thể dùng để xác thực** hoặc một định danh grant nội bộ có thể phục vụ điều tra theo chính sách bảo vệ dữ liệu. Không ghi raw token chỉ để dễ tra cứu.

### Metric hữu ích

| Metric/sự kiện | Ý nghĩa |
|---|---|
| `revocation_requests_total` theo Client/issuer/result | Phát hiện spike, retry loop hoặc Client lỗi. |
| `revocation_client_auth_failures` | Có thể là secret rotation sai hoặc attacker thử credential. |
| `revocation_unsupported_type` | Client sai token type hoặc AS không hỗ trợ capability mong đợi. |
| `revocation_processing_latency` | Đo phản hồi AS, chưa phải latency RS propagation. |
| `revocation_propagation_delay` | Đo thời gian RS bắt đầu từ chối token sau commit. |
| `refresh_token_reuse_detected` | Tín hiệu token family có thể bị sao chép/phát lại. |
| `introspection_active_after_revoke` | Tìm cache/replica còn cho `active=true`. |

### Khi nghi token bị lộ

1. Xác định **token loại gì**, Client/grant/tenant/audience/scope nào bị ảnh hưởng.
2. **Revoke credential thích hợp**: refresh token/family, access token hoặc grant; khóa Client credential nếu Client bị chiếm.
3. Kiểm tra **các token mới đã cấp** trong thời gian attacker có credential.
4. Điều tra access logs tại RS ở mức metadata an toàn, không xuất full tokens.
5. Nếu dùng JWT offline, kích hoạt denylist/TTL/permission checks theo kế hoạch, không tuyên bố lập tức vô hiệu.
6. Nếu lộ khóa ký AS, đây là **sự cố signing key**, ảnh hưởng rộng hơn một token; cần rotation/trust-cache invalidation.
7. Thông báo user/admin phù hợp, sửa nguồn lộ, kiểm thử không còn quyền trái phép.

## 25. Ma trận kiểm thử revocation endpoint

Giả sử Client `spend-insights-web` là confidential client dùng `client_secret_basic`, được cấp grant `orders:read` cho `orders-api`, có refresh token R và access token A. AS hỗ trợ refresh-token revocation, còn access-token revocation phụ thuộc cấu hình.

| Kịch bản | Kết quả kỳ vọng | Nội dung kiểm chứng |
|---|---|---|
| POST revoke R với client auth đúng | **200 OK** và R không còn dùng refresh được. | Luồng chuẩn RFC 7009. |
| POST revoke R lần hai | **200 OK** nếu request hợp lệ. | Idempotent invalid token handling. |
| POST token random không tồn tại, client auth hợp lệ | **200 OK**. | Không token enumeration. |
| POST token đã hết hạn | **200 OK** theo quy tắc invalid token. | Không lộ token state. |
| POST thiếu field `token` | OAuth request error, ví dụ `invalid_request`. | Form validation. |
| POST request JSON thay vì form | Từ chối hoặc xử lý theo hợp đồng AS; không mặc định chấp nhận. | RFC 7009 content type. |
| GET revoke với token trong URL | Không được triển khai làm API revocation thông thường. | Không lộ token qua URL. |
| Không dùng HTTPS | Từ chối thiết kế/request; Client không gửi token. | Transport security. |
| Client secret sai hoặc credential bị revoke | AS từ chối client authentication. | `invalid_client` handling. |
| Client A cố revoke token Client B | AS từ chối theo association/authorization policy. | Client-token binding. |
| Public Client chỉ gửi `client_id` | AS áp dụng chính sách public client, không coi ID là secret. | Public-client treatment. |
| Hint `refresh_token` đúng với R | AS có thể dùng lookup tối ưu. | Hint performance. |
| Hint `access_token` sai với R | AS không xem hint là quyền/loại token đáng tin. | Hint robustness. |
| Loại token không được AS hỗ trợ revocation | Trả `unsupported_token_type` khi thích hợp. | Capability negotiation. |
| Revoke access token A khi AS hỗ trợ | A bị đánh dấu revoked theo backend. | Access token revocation. |
| Revoke access token A khi AS không hỗ trợ | Lỗi/capability phù hợp; không báo mọi RS đã chặn. | Honest unsupported handling. |
| Revoke R rồi Client cố refresh R | AS từ chối refresh, thường `invalid_grant`. | Refresh lifecycle. |
| Revocation R và refresh R đồng thời | Không phát R2 trái grant state. | Atomic race safety. |
| Refresh token rotation R1 → R2, attacker reuse R1 | AS xử lý reuse/family policy phù hợp. | Replay detection. |
| Attacker đã có R2, chỉ revoke R1 cũ | Test xác định có revoke family hay không. | Token lineage. |
| Token R revoked, RS cache `active=true` của A | Đánh giá thời gian A còn được chấp nhận. | Cache propagation. |
| JWT A còn hạn, RS chỉ verify offline | A có thể vẫn được nhận; test ghi giới hạn. | JWT revocation realism. |
| JWT A có `jti` trong denylist | RS từ chối dù signature/exp hợp lệ. | Revocation state. |
| Token `aud=billing-api` trình Orders | RS từ chối. | Audience validation. |
| Token thiếu `orders:read` dùng đọc đơn | RS từ chối. | Scope authorization. |
| Token đúng scope nhưng order tenant khác | RS từ chối. | Object/tenant authorization. |
| OIDC ID token được gửi /revoke rồi dùng làm API token | AS/RS xử lý đúng loại token; không chấp nhận ID token làm access. | Token purpose separation. |
| Client Credentials token A bị revoke, secret còn hiệu lực | Client có thể xin token mới theo policy. | Revocation khác client disable. |
| User logout Client mà không remote revoke R | Không tuyên bố AS đã revoke R. | Local vs remote cleanup. |
| User disconnect và remote revoke timeout | Không tiếp tục dùng token; theo dõi trạng thái chưa rõ, retry có giới hạn. | Uncertain result handling. |
| AS 503, Client tự bỏ auth để thử revoke | Không được phép fail open. | Availability vs security. |
| AS POST phản hồi redirect tới host lạ | Client không follow khi mang credential. | Exfiltration prevention. |
| Tracing chứa raw `token` hoặc Basic header | Test fail, cần redaction/incident. | Secret logging. |
| Nhiều revoke requests token random | AS rate-limit, không làm lộ token state. | Enumeration/DoS protection. |
| Two tenants cùng subject string | Grant/token family không bị trộn tenant. | Isolation. |
| Admin tenant A revoke grant tenant B | Bị chặn nếu thiếu quyền cross-tenant. | Admin policy. |
| User revoke toàn bộ connected app | Kiểm tra phạm vi tất cả grants/families mong muốn. | Grant lifecycle. |
| Key ký JWT bị lộ nhưng chỉ revoke một token | Incident vẫn tồn tại; cần key trust response. | Key compromise scope. |

**Một kết quả HTTP 200 từ /revoke không đủ chứng minh end-to-end.** Cần kiểm tra **token endpoint có chặn refresh**, **RS có từ chối access token theo SLA**, **grant/family nào bị ảnh hưởng** và **Client không còn giữ credential**.

## 26. Tình huống tự luyện

**Tình huống A — Token không tồn tại nhưng endpoint trả 200.** Client gửi token ngẫu nhiên, nhận HTTP 200. Có phải lỗi bảo mật vì AS không báo “token not found”?

**Giải thích:** Không. RFC 7009 quy định phản hồi thành công/invalid token đồng nhất sau các kiểm tra thích hợp để tránh làm lộ sự tồn tại của token.

**Tình huống B — Secret đúng nhưng token Client khác.** BFF A có client secret hợp lệ và biết refresh token của B. Có thể revoke R của B?

**Giải thích:** AS phải xác minh token thuộc Client yêu cầu. Việc biết một chuỗi và xác thực là A không trao quyền thao tác credential của B.

**Tình huống C — User logout nhưng token vẫn hoạt động.** BFF chỉ xóa session cookie. Attacker vẫn cầm access token. Tại sao API còn nhận?

**Giải thích:** Logout local không đồng nghĩa revoke token ở AS/RS. Access token bearer còn hạn có thể tiếp tục được chấp nhận nếu RS chưa có trạng thái revoke hoặc sender binding.

**Tình huống D — JWT còn 8 phút.** AS revoke R thành công, Orders API chỉ verify chữ ký và `exp` của JWT A. A có chết ngay không?

**Giải thích:** Không mặc định. Cần JWT TTL ngắn, denylist/introspection hoặc RS state check để chặn sớm; nếu không, A có thể sống đến `exp`.

**Tình huống E — Hint sai.** Refresh token R được gửi với `token_type_hint=access_token`. AS có thể tin hint để đánh dấu access token thay vì xác định loại thực?

**Giải thích:** Không. Hint chỉ giúp lookup; loại token và association phải dựa trên trạng thái đáng tin.

**Tình huống F — Unsupported access-token revocation.** AS hỗ trợ revoke refresh token nhưng không access token; Client gửi access token. Phải làm gì?

**Giải thích:** Hệ thống cần xử lý capability/lỗi như `unsupported_token_type`; không tuyên bố đã hủy A. Nếu cần chặn ngay, phải dùng chính sách/RS mechanisms khác hoặc chọn kiến trúc hỗ trợ.

**Tình huống G — R1 đã bị rotate.** Attacker có R2, user chỉ yêu cầu revoke R1 cũ. Làm sao bảo đảm attacker không tiếp tục refresh?

**Giải thích:** AS cần nhận dạng **grant/token family** và chính sách revoke/reuse phù hợp. Chỉ revoke một token cũ có thể không ảnh hưởng R2 nếu không có lineage.

**Tình huống H — HTTP 200 nhưng introspection còn active.** User revoke A lúc T0, RS cache `active=true` tới T0+60s. Đây là vấn đề gì?

**Giải thích:** **Propagation/cache delay**. Hệ thống phải xác định TTL/cache invalidation và SLA; không dùng kết quả 200 để hứa tức thời khi RS còn cache.

**Tình huống I — Client Credentials compromised.** Worker bị lộ secret và access token. Team chỉ gọi /revoke với access token cũ. Đã an toàn chưa?

**Giải thích:** Chưa. Secret còn hiệu lực cho attacker xin token mới. Phải rotate/disable client credential và điều tra token/grant liên quan.

**Tình huống J — Token chứa dữ liệu tenant B.** RS nhận token đúng issuer/audience/scope nhưng user chỉ có quyền tenant A. Revocation có thay quyền đối tượng không?

**Giải thích:** Không. RS phải kiểm tra tenant/owner và dữ liệu thật dù token chưa revoked.

**Tình huống K — Endpoint được Client lấy từ URL người dùng nhập.** Một form cho admin nhập `revocation_endpoint` rồi backend POST refresh token vào đó. Rủi ro?

**Giải thích:** Credential exfiltration/SSRF. Endpoint phải đến từ trusted issuer metadata/cấu hình đã kiểm tra; không gửi secret/token sang URL không tin cậy.

**Tình huống L — Xóa token local trước khi revoke.** Client xóa vĩnh viễn R khỏi mọi storage rồi mới cố gọi AS. Điều gì xảy ra nếu không còn bản sao?

**Giải thích:** Client có thể không còn giá trị R để trình tới revocation endpoint. Cần thiết kế thứ tự xử lý, kết thúc session an toàn ngay, và xử lý remote revoke/failure mà không giữ token lâu dài ngoài kiểm soát.

**Tình huống M — Revoke trả timeout.** Server đã thực hiện revoke nhưng mạng làm mất response. Có được retry?

**Giải thích:** Có thể retry có giới hạn theo RFC behavior của invalid token, nhưng cần tránh request storm và luôn coi kết quả remote chưa chắc chắn cho tới khi có xác nhận phù hợp.

**Tình huống N — OIDC logout có cần revoke?** User đăng xuất khỏi OP. Có phải mọi OAuth access/refresh token của mọi RP tự vô hiệu?

**Giải thích:** Không mặc định. OIDC logout và OAuth token revocation là cơ chế riêng; thiết kế hệ thống quyết định liên kết chúng như thế nào.

## Checklist triển khai điểm cuối thu hồi token

1. **Hiểu endpoint:** RFC 7009 là yêu cầu Client gửi tới AS để revoke token, khác introspection/token endpoint và logout.
2. **Trusted issuer/endpoint:** cấu hình hoặc lấy từ metadata RFC 8414 đã kiểm tra, HTTPS/TLS, không chấp nhận URL do user tự khai.
3. **Đúng request:** POST `application/x-www-form-urlencoded`, `token` bắt buộc, `token_type_hint` tùy chọn.
4. **Client authentication:** confidential Client dùng method đã đăng ký; public Client không coi `client_id` là bí mật; kiểm tra token thuộc Client.
5. **Đúng response semantics:** HTTP 200 cho token revoked/invalid sau kiểm tra phù hợp; xử lý `invalid_client`, `invalid_request`, `unsupported_token_type` đúng mục đích.
6. **Phân biệt token types:** refresh/access/ID/opaque/JWT, không dùng refresh token trực tiếp tại RS và không coi hint là nguồn chân lý.
7. **Định nghĩa cascade:** revoke một token, token family hay grant; refresh → access revocation theo capability và policy.
8. **Refresh rotation và reuse:** quản lý lineage, atomic state, revoke descendants theo policy, cảnh báo token theft/replay.
9. **JWT offline:** TTL ngắn và denylist/grant version/introspection khi cần chặn sớm; không hứa revocation tức thời nếu chỉ verify `exp`.
10. **Opaque introspection:** kiểm tra `active`, cache TTL, error handling và RS authorization.
11. **Bảo vệ transport/secrets:** không log request/Authorization/credential, không gửi token trong URL, chống redirect SSRF/exfiltration.
12. **Quản lý cache/propagation:** xác định SLA và đo thời điểm RS thực sự từ chối token; xử lý concurrency và network partition.
13. **Logout/disconnect đúng nghĩa:** chặn local session sử dụng token, remote revoke, cleanup, bounded retry nếu không chắc chắn, thông báo giới hạn hiệu lực.
14. **Least privilege/multi-tenant:** token association, scope/audience và grant theo Client/user/tenant; admin chỉ revoke đúng phạm vi.
15. **RS luôn phân quyền:** trusted issuer, signature/introspection, audience, token type, exp/nbf, scope, sender proof và object/tenant authorization.
16. **Incident response:** lộ refresh token/bearer token/client credential/private signing key là các mức độ khác nhau, xử lý phù hợp.
17. **Test cả đường thất bại:** token invalid/revoked, sai Client, hint sai, unsupported type, 429/503/timeout, race/rotation, JWT cache, mixed tenant và bearer replay.

## Ghi nhớ

**Revocation endpoint (RFC 7009)** nhận **POST form** với `token` và `token_type_hint` tùy chọn, qua HTTPS và với **client authentication/association** đúng chính sách. AS phản hồi **200 OK** cho token được revoke hoặc invalid nhằm tránh token enumeration; khi không hỗ trợ một loại token, có thể trả **`unsupported_token_type`**. Thu hồi **refresh token** chủ yếu chặn xin token mới và có thể lan sang grant/access token theo khả năng AS; thu hồi **access token** không mặc định thu hồi refresh token hay vô hiệu client secret. **JWT tự xác minh offline có thể vẫn được RS chấp nhận tới `exp` nếu thiếu denylist/introspection/state check**. Vì thế một hệ thống an toàn phải kết hợp **token storage, refresh rotation/reuse detection, issuer/audience/scope, cơ chế RS nhận trạng thái revoke, client credential lifecycle và object-level authorization**. Logout, disconnect, revocation và token expiration **không phải cùng một thao tác**.

### Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
