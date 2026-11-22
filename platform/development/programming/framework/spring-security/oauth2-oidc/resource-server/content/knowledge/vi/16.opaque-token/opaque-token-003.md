# RFC 7662, introspection request và metadata phản hồi

## 1. Vì sao Resource Server cần Token Introspection?

Một API sử dụng OAuth 2.0 nhận **access token** qua HTTP `Authorization: Bearer ...`. Nếu token là JWT có chữ ký mà Resource Server được phép xác minh cục bộ, API có thể tải public key/JWKS và tự kiểm tra JWS, issuer, audience, thời hạn và quyền. Nhưng nhiều Authorization Server phát hành access token ở dạng **opaque**: đối với API, token chỉ là một chuỗi ngẫu nhiên, không có cấu trúc nội dung đáng tin để giải mã.

Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer 5c6e86a0-opaque-token-example
```

Resource Server không được suy ra danh tính, phạm vi quyền hoặc ngày hết hạn từ vẻ ngoài của chuỗi trên. Để biết token có đang hoạt động không và được cấp những quyền nào, API có thể hỏi **Authorization Server** qua **OAuth 2.0 Token Introspection** được chuẩn hóa trong **RFC 7662**.

Trong phương pháp này, Resource Server **gửi token đến introspection endpoint**, tự xác thực với endpoint theo chính sách của Authorization Server, rồi nhận JSON metadata phản ánh trạng thái token. Resource Server tiếp tục kiểm tra điều kiện của API (scope, audience, tenant, ownership) trước khi cho thực thi nghiệp vụ.

> **Điểm mấu chốt:** `active: true` là kết quả kiểm tra trạng thái token theo góc nhìn Authorization Server và quyền của bên hỏi introspection. Nó **không tự động có nghĩa** caller được phép sử dụng mọi endpoint hay xem mọi tài nguyên.

Ví dụ trong bài dùng:

- **Authorization Server**: `https://auth.example.test`.
- **Introspection endpoint**: `https://auth.example.test/oauth2/introspect`.
- **Resource Server**: `orders-api`, bảo vệ `/api/orders/**`.
- **Introspection client**: `orders-api-introspector`, có credential riêng để gọi endpoint.
- **OAuth client nhận token**: `web-portal`, đã xin token thay mặt user.
- **User subject**: `alice-123`.

Tên miền, mật khẩu và token trong các ví dụ chỉ là ký hiệu; **không dùng các giá trị minh họa làm credential thật**.

### 1.1. Một sơ đồ trao đổi

```mermaid
sequenceDiagram
    participant U as User / Browser
    participant C as OAuth Client web-portal
    participant AS as Authorization Server
    participant RS as Resource Server orders-api

    U->>C: Đăng nhập và yêu cầu xem đơn
    C->>AS: OAuth authorization / token request
    AS-->>C: Access token dạng opaque
    C->>RS: GET /api/orders/42 + Bearer token
    RS->>AS: HTTPS POST /oauth2/introspect
    Note over RS,AS: Gửi token và xác thực orders-api-introspector
    AS->>AS: Kiểm tra quyền introspect và trạng thái token
    AS-->>RS: JSON active + metadata được phép tiết lộ
    RS->>RS: Xác thực token, audience, scope, object-level policy
    RS-->>C: 200 / 401 / 403 / 404 theo chính sách
```

Request Bearer từ client tới API và request introspection từ API tới Authorization Server là **hai giao dịch khác nhau**, sử dụng hai bộ credential khác nhau:

| Vị trí | Credential | Chủ sở hữu | Dùng để làm gì? |
|---|---|---|---|
| `Client -> orders-api` | **Access token** của request | Client được cấp token; có thể đại diện user | API cần biết token này có hợp lệ, scope nào. |
| `orders-api -> Authorization Server` | **Introspection client credential** | Dịch vụ Resource Server | AS xác thực và quyết định Resource Server có quyền hỏi metadata token. |

Không lấy `client_id` trong introspection response làm introspection client ID, cũng không dùng client secret của frontend hoặc token của user làm mật khẩu introspection.

### 1.2. “Opaque Token Resource Server” không ép token phải có định dạng gì

RFC 7662 không yêu cầu token được đưa vào introspection phải là chuỗi hoàn toàn ngẫu nhiên; endpoint có thể introspect cả một JWT nếu AS hỗ trợ. “Opaque” trong cách gọi cấu hình Spring Security chủ yếu nhấn mạnh **Resource Server dùng kết quả introspection làm nguồn xác thực**, thay vì tự giải mã và xác minh JWT theo đường local decoder.

Vì thế hai chế độ cần phân biệt:

| Đặc điểm | JWT validation cục bộ | Introspection qua RFC 7662 |
|---|---|---|
| Cách xác minh | JWS public key/JWKS và JWT validators của API. | Hỏi Authorization Server xem token có active và lấy metadata. |
| Phụ thuộc mạng khi kiểm tra token | Không phải từng request nếu có public key trong cache. | Thường gọi introspection theo từng token/request, trừ khi thiết kế cache. |
| Thu hồi token sớm | JWT tự xác minh không tự biết bị thu hồi. | AS có thể báo `active=false` nếu biết token bị thu hồi. |
| Nội dung nhận được | JWT claims được issuer phát hành. | JSON metadata do AS quyết định cung cấp cho resource requester. |
| Bảo mật tích hợp | Quản lý public keys và token validation. | Thêm introspection endpoint credential, TLS, rate limit và response trust. |
| Phân quyền nghiệp vụ | Luôn phải kiểm tra scope/role/owner/tenant. | **Vẫn phải kiểm tra scope/role/owner/tenant.** |

Cả hai cách đều phải kiểm tra đúng audience/token profile theo hợp đồng. Đừng nhận token chỉ vì nó là JWT có thể decode hoặc vì introspection trả `active=true`.

---

## 2. RFC 7662 định nghĩa những gì?

RFC 7662, **OAuth 2.0 Token Introspection**, mô tả:

1. **Introspection endpoint** của Authorization Server.
2. **Introspection request**: một HTTP `POST` dùng `application/x-www-form-urlencoded`, bắt buộc có tham số `token`; có thể kèm `token_type_hint`.
3. **Xác thực và ủy quyền của requester**: AS phải bảo vệ endpoint để tránh tiết lộ trạng thái/danh tính token cho đối tượng không được phép.
4. **Introspection response**: JSON object chứa trường bắt buộc `active` (boolean) và các metadata tùy chọn.
5. **Quy tắc phản hồi cho token inactive hoặc token mà caller không được phép biết**.
6. **Yêu cầu bảo vệ kênh** bằng TLS và cân nhắc riêng tư, khả năng caching, giới hạn lượng gọi.

Có hai quyết định an ninh hoàn toàn khác nhau ở AS:

- **Resource Server có quyền gọi introspection endpoint không?** Điều này được xác định bằng credential và chính sách AS.
- **Access token trong tham số `token` có active và có thể được tiết lộ cho requester này không?** Đây là quyết định theo trạng thái token và quyền introspection cụ thể.

Đã xác thực introspection client không đồng nghĩa được xem trạng thái của **mọi** token. AS có thể giới hạn theo audience, resource, tenant, client hoặc phạm vi được ủy quyền.

### 2.1. Những vai trò cùng xuất hiện trong một request

Giả sử AS trả:

```json
{
  "active": true,
  "client_id": "web-portal",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read"
}
```

Các danh tính không đồng nghĩa:

| Danh tính | Ví dụ | Ý nghĩa |
|---|---|---|
| **Introspection requester** | `orders-api-introspector` | Client đang gọi `/oauth2/introspect` để hỏi trạng thái token. |
| **OAuth token client** | `web-portal` | `client_id` của client đã yêu cầu access token, nếu AS cung cấp. |
| **Subject** | `alice-123` | `sub` của chủ thể mà token đại diện, nếu có. |
| **Audience / resource** | `orders-api` | `aud` mô tả resource mục tiêu, nếu profile cung cấp. |
| **Issuer** | `https://auth.example.test` | AS chịu trách nhiệm phát hành, nếu response có `iss`. |

Với Client Credentials, `sub` có thể đại diện workload/client chứ không phải người dùng tương tác. Resource Server không được mặc định `sub` nào cũng là user để suy ra ownership.

---

## 3. Cấu trúc introspection request

### 3.1. Phương thức, URL và Content-Type

Theo RFC 7662, introspection request gửi đến endpoint đã đăng ký của AS bằng **HTTP POST** với các tham số form:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-of-introspection-client-credentials>

token=opaque-access-token-value&token_type_hint=access_token
```

Trong ví dụ:

- `token` là **tham số bắt buộc** chứa token cần tra trạng thái. Đó là access token của request tới `orders-api`, không phải introspection client secret.
- `token_type_hint` là **tham số tùy chọn** gợi ý loại token, thường là `access_token` hoặc `refresh_token`. Nó chỉ hỗ trợ AS chọn cách tra cứu hiệu quả; Resource Server không thể tự bảo đảm token thuộc loại nào chỉ vì đã khai tham số này.
- `Authorization: Basic ...` là một **cách xác thực introspection requester**. Authorization Server có thể yêu cầu cơ chế khác như `client_secret_post`, mutual TLS hoặc private-key JWT tùy khả năng và chính sách.
- HTTPS phải xác minh chứng chỉ và hostname. **Base64 của Basic Auth không bảo mật hóa client secret**; chỉ TLS và bảo vệ endpoint/logs mới bảo đảm bí mật trên đường truyền.
- Không đưa access token vào query string của URL hoặc gửi bằng `GET` chỉ vì dễ debug; URL query có thể bị log ở gateway/browser/proxy.

**Form encoding** cần được thư viện HTTP xử lý đúng. Access token có thể chứa các ký tự đặc biệt, vì vậy nối chuỗi form thủ công không escape có thể làm AS nhận sai giá trị token. Dùng client/library chuẩn để truyền `application/x-www-form-urlencoded`.

### 3.2. Ví dụ curl phục vụ phòng thực hành

Nếu cần quan sát giao thức trên một AS **dev/test** do mình quản lý:

```bash
curl --request POST \
  --url 'https://auth-dev.example.test/oauth2/introspect' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --data-urlencode "token=$TEST_ACCESS_TOKEN" \
  --data-urlencode 'token_type_hint=access_token'
```

Để đoạn lệnh này hữu ích, ba biến môi trường phải được cấp bằng credential thử nghiệm phù hợp, **không điền credential production vào terminal lịch sử hoặc tài liệu**. Tránh `curl -v`/`--trace` khi có token thật, vì phần header/form có thể xuất hiện trong log. Ở một số môi trường shell/process, argument và environment có thể bị quan sát; không xem script mẫu là phương pháp cung cấp secret an toàn mặc định cho production.

Nếu AS dùng cơ chế client authentication khác, cấu trúc `--user` phải được thay theo **metadata và tài liệu của issuer**, không tự giả định mọi introspection endpoint đều hỗ trợ Basic Auth.

### 3.3. `token_type_hint` giúp gì?

Một Authorization Server có thể lưu access token và refresh token ở các kho khác nhau. Khi request có:

```text
token_type_hint=access_token
```

AS có thể ưu tiên tìm trong kho access token. Đây là **hint**, không phải bằng chứng xác thực hoặc điều kiện phân quyền. RFC 7662 cho phép AS bỏ qua hint; hành vi xử lý hint lạ hoặc không khớp phụ thuộc implementation.

Không dùng `token_type_hint=access_token` để biến refresh token thành access token, cũng không cho phép API chấp nhận refresh token chỉ vì request có hint này. API chỉ nên nhận **access token đúng profile/resource**, không dùng refresh token làm Bearer credential.

### 3.4. Có cần gửi `client_id` và `client_secret` trong body?

Không có yêu cầu RFC 7662 rằng mọi introspection request đều phải dùng client secret; RFC tập trung vào việc endpoint phải được bảo vệ theo chính sách AS. Một AS dùng Basic có thể nhận credential ở HTTP Authorization header. Một AS khác có thể hỗ trợ body credentials hoặc mTLS/private_key_jwt.

Ví dụ nếu AS yêu cầu `client_secret_basic`, không nên tự thêm `client_id`/`client_secret` vào body “cho chắc”, vì có thể vi phạm cách xác thực đã đăng ký và tăng bề mặt rò rỉ. Cần cấu hình **client authentication method** chính xác cho introspection client.

---

## 4. Phản hồi: `active` là trường bắt buộc

Introspection response theo RFC 7662 là JSON object với trường bắt buộc:

```json
{
  "active": true
}
```

hoặc:

```json
{
  "active": false
}
```

`active` phải là **JSON boolean**, không phải chuỗi `"true"` hoặc số `1`. Khi `active=true`, Authorization Server kết luận token active theo trạng thái và chính sách của nó tại thời điểm introspection; các metadata khác có thể được kèm theo.

### 4.1. Token active

Ví dụ phản hồi đầy đủ hơn:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders:read orders:write",
  "client_id": "web-portal",
  "username": "alice",
  "token_type": "Bearer",
  "exp": 1890003600,
  "iat": 1890000000,
  "nbf": 1890000000,
  "sub": "alice-123",
  "aud": ["orders-api"],
  "iss": "https://auth.example.test",
  "jti": "token-id-abc-123"
}
```

Đây là phản hồi **minh họa**. Các trường ngoài `active` chỉ xuất hiện nếu AS hỗ trợ, có dữ liệu và cho phép requester nhìn thấy. Không ép mọi issuer phải trả toàn bộ danh sách.

### 4.2. Token inactive hoặc không thể introspect

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
```

Một token có thể không active vì hết hạn, bị thu hồi, không tồn tại, chưa có hiệu lực hoặc **không thể được introspection requester này tra cứu** theo chính sách AS. RFC 7662 khuyến nghị đối với token inactive chỉ trả `active=false` và không cung cấp metadata token.

Điểm đáng lưu ý: AS có thể dùng cùng phản hồi inactive cho những trường hợp **token không tồn tại** và **token mà requester không được phép nhìn thấy**. Điều này tránh tạo oracle tiết lộ token hợp lệ cho những bên không được cấp quyền.

Resource Server phải xem `active=false` là **không đủ điều kiện xác thực request**. Không giải mã token rồi sử dụng claims fallback, không coi token “chỉ hơi hết hạn” là hợp lệ, và không cho request đi tiếp vì route có `authenticated()`.

### 4.3. AS trả HTTP 200 không có nghĩa token hợp lệ

Ở tầng transport, một introspection request thành công có thể nhận **HTTP 200** nhưng JSON chứa `active=false`. Phân biệt:

| HTTP status của introspection | JSON body | Diễn giải |
|---|---|---|
| `200 OK` | `{"active":true,...}` | Request introspection được xử lý; token active theo AS, tiếp tục kiểm tra policy. |
| `200 OK` | `{"active":false}` | Token không active/không được cho xem; Resource Server từ chối xác thực token. |
| `400 Bad Request` | Error object tùy AS | Request bị lỗi cú pháp/tham số, không phải bằng chứng token inactive. |
| `401 Unauthorized` | Error hoặc không body | Credential introspection client sai/thiếu; đây là lỗi tích hợp/ủy quyền với AS. |
| `403 Forbidden` | Tùy implementation | Introspection requester thiếu quyền truy cập endpoint hoặc resource, cần phân biệt với `active=false`. |
| `429 Too Many Requests` | Tùy implementation | AS giới hạn tải; áp dụng backoff/circuit breaker theo chính sách, không cho qua. |
| `5xx`/timeout | Không nhận được kết quả hợp lệ | Không thể xác minh token; phải **fail closed**. |

Mã lỗi chính xác tùy AS và Spring Security version. Khi Resource Server không xác minh được vì lỗi mạng, phản hồi HTTP đến client có thể khác 401 tùy exception handling; điều bất biến là request **không được thực thi nghiệp vụ được bảo vệ** khi chưa có xác thực đáng tin.

---

## 5. Metadata chuẩn trong introspection response

RFC 7662 định nghĩa `active` bắt buộc và một số tên trường **tùy chọn**. Bảng sau tập trung vào ý nghĩa, kiểu dữ liệu và chính sách sử dụng.

| Trường | Kiểu thường gặp theo RFC 7662 | Ý nghĩa | Lưu ý cho Resource Server |
|---|---|---|---|
| **`active`** | Boolean, **bắt buộc** | Token có active theo AS hay không. | `false` → không tạo authenticated principal. `true` → vẫn cần scope/resource policy. |
| **`scope`** | String cách nhau bằng dấu cách | Các OAuth scopes được gắn với token. | Chuyển thành authorities theo profile; không tự thêm quyền nếu vắng mặt. |
| **`client_id`** | String | OAuth client đã yêu cầu token. | Khác với introspection requester; không tự cho phép client này đọc mọi tài nguyên. |
| **`username`** | String | Tên người dùng tương đối thân thiện khi token đại diện resource owner. | Không dùng làm primary authorization key ổn định. |
| **`token_type`** | String | Loại token, thường là `Bearer`. | Không tự cho rằng mọi AS đều trả; kiểm tra loại token phù hợp nếu contract yêu cầu. |
| **`exp`** | Number, NumericDate | Thời điểm hết hạn (Unix seconds). | Hữu ích để chặn token hết hạn và ràng buộc TTL cache. |
| **`iat`** | Number, NumericDate | Thời điểm token được phát hành. | Hữu ích cho audit hoặc chính sách tuổi token; không tự thành quyền. |
| **`nbf`** | Number, NumericDate | Thời điểm token bắt đầu có hiệu lực. | Nếu contract dùng, token chưa tới thời điểm không được chấp nhận. |
| **`sub`** | String | Chủ thể mà token đại diện. | Dùng theo namespace issuer và grant; không suy đoán luôn là user. |
| **`aud`** | String hoặc array of strings | Audience/resource của token. | Kiểm tra `orders-api` có nằm trong tập audience theo policy. |
| **`iss`** | String | Bên phát hành token. | Kiểm tra với issuer tin cậy nếu contract cung cấp. |
| **`jti`** | String | Token identifier, nếu có. | Có thể dùng trong audit/revocation policy; không làm bằng chứng độc lập của token. |

Bảng không có nghĩa các trường này **bắt buộc** với mọi introspection response. Ngoại trừ `active`, sự hiện diện và diễn giải phải dựa trên **hợp đồng giữa Authorization Server và Resource Server**.

### 5.1. `scope` và ánh xạ authorities

Theo OAuth 2.0, scope được mô tả bằng các scope token phân tách bởi dấu cách:

```json
{
  "active": true,
  "scope": "orders:read orders:write"
}
```

Trong Spring Security Resource Server dùng opaque token, các scopes theo cơ chế mặc định thường được ánh xạ thành:

```text
SCOPE_orders:read
SCOPE_orders:write
```

Vì vậy:

```java
.hasAuthority("SCOPE_orders:read")
```

kiểm tra authority của Spring, không so trực tiếp chuỗi form request hay một query parameter `scope`.

Một số IdP đưa permissions vào `scp`, `roles`, `permissions` hoặc claim tùy biến. **Không tự nhận chúng tương đương `scope`** nếu AS không định nghĩa rõ profile. Nếu cần custom mapper, phải kiểm tra schema, tên resource và giới hạn quyền.

### 5.2. `client_id` không phải introspection client ID

Response:

```json
{
  "active": true,
  "client_id": "web-portal",
  "sub": "alice-123"
}
```

không nói rằng Resource Server đã gọi introspection bằng `web-portal`. Nó mô tả OAuth client được liên kết với access token. Client thực hiện introspection thường là `orders-api-introspector` với credential riêng.

Sự phân biệt này rất quan trọng khi áp dụng:

- Rate limit theo OAuth client đã yêu cầu token.
- Chính sách chỉ cho phép một số client gọi API.
- Audit về nguồn cấp access token.
- Service-to-service integration.

Nếu API cần allowlist `client_id`, hãy làm theo **token profile đã xác minh** và **không xem client_id đơn lẻ là bằng chứng người dùng sở hữu đối tượng**.

### 5.3. `sub`, `username` và subject không phải lúc nào cũng là user

Một token Authorization Code có thể chứa:

```json
{
  "sub": "alice-123",
  "username": "alice"
}
```

Nhưng một token Client Credentials có thể chứa subject tương ứng service account:

```json
{
  "client_id": "orders-importer",
  "sub": "orders-importer-service"
}
```

Không nên dùng `username` (có thể đổi hoặc tái sử dụng) làm khoá owner trong database. Nếu dùng `sub` cho quan hệ ownership, kết hợp với issuer hoặc internal identity mapping tin cậy. Với client credentials, phải tách policy của workload ra khỏi policy người dùng.

### 5.4. `iss` và `aud` là ranh giới tin cậy

Một AS có thể cấp token cho nhiều API. Vì vậy chỉ thấy `active=true` vẫn chưa đủ để khẳng định token dành cho `orders-api`.

Ví dụ phản hồi:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "orders:read",
  "iss": "https://auth.example.test"
}
```

Nếu policy yêu cầu audience chứa `orders-api`, Resource Server phải từ chối token này, dù scope có tên `orders:read`.

Không phải mọi AS đều trả `aud` hay `iss` trong introspection response. Để bảo đảm resource binding, API và AS cần một trong những mô hình đã được hợp đồng hóa:

1. AS **chỉ trả active/metadata có thể sử dụng đối với token dành cho resource requester này**, dựa trên credential introspection và policy resource.
2. AS trả `aud`/`iss` rõ ràng, Resource Server **kiểm tra** các trường này.
3. Sử dụng một hợp đồng/endpoint/provider-specific extension tương đương để xác định token đúng issuer/resource.

**Nếu không có audience trong response và AS không bảo đảm giới hạn theo resource, Resource Server không có bằng chứng đủ để tự khẳng định token dành cho API.** Không nên bỏ qua vấn đề bằng cách chỉ kiểm tra `active=true`.

### 5.5. `exp`, `iat` và `nbf` không phải thời gian HTTP cache

Đây là **NumericDate** (Unix timestamp giây), ví dụ:

```json
{
  "active": true,
  "iat": 1890000000,
  "nbf": 1890000000,
  "exp": 1890003600
}
```

Ý nghĩa:

- `iat`: token được phát hành khi nào.
- `nbf`: token chưa có hiệu lực trước thời điểm nào.
- `exp`: token không hợp lệ tại hoặc sau thời điểm nào.

Không so sánh các giá trị này với epoch milliseconds mà không chuyển đơn vị. Spring có thể xử lý thông tin theo kiểu thời gian phù hợp trong authentication principal, nhưng custom code phải hiểu schema provider đang trả.

Không nhầm `exp` với:

- **Cache-Control** header của HTTP introspection response.
- **Cache TTL** của một cache application.
- **Token refresh interval** phía OAuth client.
- **JWT `exp`** trong token được parse cục bộ.

Nếu cache introspection result, thời gian giữ tối đa phải xét `exp`, mục tiêu revocation, chính sách cache và chênh lệch đồng hồ; **không cache một response “active” quá thời điểm token hết hạn**.

### 5.6. `jti` và truy vết

`jti` có thể là định danh token, nhưng không phải lúc nào AS cũng cung cấp. Nó có thể hữu ích cho audit/denylist nếu sản phẩm có thiết kế này.

Không lưu raw access token trong log chỉ để truy vết; access token là Bearer credential. Cũng không tự đưa `jti` hoặc `sub` thành nhãn metric có cardinality không giới hạn. Nếu cần correlation, dùng request ID và dữ liệu được phép lưu theo chính sách riêng tư.

### 5.7. Những claims ngoài RFC 7662

Một issuer có thể trả:

```json
{
  "active": true,
  "scope": "orders:read",
  "tenant_id": "tenant-a",
  "roles": ["orders-viewer"],
  "department": "sales",
  "authorization_details": [
    {
      "type": "order_access",
      "actions": ["read"],
      "locations": ["orders-api"]
    }
  ]
}
```

Đây là một **hồ sơ mở rộng giả định**. Không có quy tắc chung rằng `tenant_id`, `roles` hoặc `authorization_details` luôn được cung cấp hoặc luôn có đúng schema này. Nếu API sử dụng chúng để phân quyền, cần có tài liệu contract:

- Tên claim và kiểu dữ liệu được phép.
- Issuer nào phát hành, cho audience/resource nào.
- Trường hợp thiếu/null/sai kiểu phải xử lý thế nào.
- Tên quyền và phạm vi tài nguyên.
- Cách kết hợp với scopes.
- Cách nhận biết context user vs workload.
- Chính sách cập nhật quyền trong lúc token còn active.

**Không lấy bất kỳ chuỗi “admin” nào trong JSON để tạo role quản trị toàn hệ thống.**

---

## 6. Spring Security Resource Server với opaque token

Spring Security có hỗ trợ OAuth 2.0 Resource Server xác thực Bearer token bằng **OpaqueTokenIntrospector**. Ở đường đi này, ứng dụng không cần giải mã access token theo định dạng JWT; nó gửi token cho AS và xử lý metadata đã được xác thực.

### 6.1. Các dependency cần thiết

Ví dụ Maven với Spring Boot parent/BOM quản lý phiên bản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 6.2. Cấu hình introspection endpoint và credentials

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Các placeholders được Spring Boot lấy từ property sources/environment runtime. **Giá trị secret không được hardcode trong mã nguồn, file cấu hình Git, Dockerfile hay log**. Một secret manager hoặc platform runtime injection nên cấp `INTROSPECTION_CLIENT_SECRET` cho tiến trình.

Ví dụ tên biến:

```text
INTROSPECTION_CLIENT_ID=orders-api-introspector
INTROSPECTION_CLIENT_SECRET=<injected-at-runtime>
```

Dòng secret là placeholder, không phải mật khẩu dùng thật.

Đối với trường hợp AS chỉ hỗ trợ một cơ chế introspection client authentication khác Basic, hoặc cần cấu hình custom HTTP timeout/mTLS/private_key_jwt, cần tùy chỉnh `OpaqueTokenIntrospector` hoặc HTTP client tương ứng. Không tự giả định các property trên đủ cho mọi nhà cung cấp.

### 6.3. SecurityFilterChain yêu cầu scope

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueTokenSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Phù hợp API stateless dùng Bearer token trong Authorization header.
            // App có session cookie phải đánh giá CSRF riêng.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Với cơ chế mặc định, Resource Server tạo authentication cho token active và chuyển các scopes thành authorities `SCOPE_...`. Sau đó `authorizeHttpRequests` sử dụng những authorities đó để quyết định route. Đừng chuyển `.anyRequest().denyAll()` sang `.anyRequest().authenticated()` chỉ để tránh lỗi 403, vì nó có thể khiến những route mới không được gắn scope đúng yêu cầu.

Phần trên chỉ thiết kế **một kiểu xác thực cho API**. Nếu ứng dụng cần chấp nhận cả JWT cục bộ và introspection, phải có resolver/policy phân loại rõ token, issuer và audience; không cho phép token “thất bại ở chế độ này thì thử chế độ khác tới khi được chấp nhận” mà không có ranh giới tin cậy.

### 6.4. Spring làm gì với kết quả introspection?

Luồng khái niệm:

```mermaid
flowchart TD
    A["Request Authorization: Bearer opaque token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["OpaqueTokenIntrospector"]
    C --> D["HTTPS POST /oauth2/introspect"]
    D --> E{"AS trả active?"}
    E -->|false / lỗi| F["Authentication thất bại hoặc lỗi upstream; không cho qua"]
    E -->|true| G["Tạo OAuth2AuthenticatedPrincipal từ metadata"]
    G --> H["Ánh xạ scope thành SCOPE_..."]
    H --> I["Tạo BearerTokenAuthentication"]
    I --> J{"Đủ authority của endpoint?"}
    J -->|Không| K["403"]
    J -->|Có| L["Kiểm tra owner, tenant, nghiệp vụ"]
    L --> M["Trả dữ liệu hoặc từ chối theo policy"]
```

Tên lớp và một số chi tiết implementation có thể khác theo Spring Security version. Cấu trúc chủ đạo là `OpaqueTokenIntrospector` trả về một `OAuth2AuthenticatedPrincipal` chứa attributes và authorities, sau đó Resource Server tạo authentication phù hợp.

### 6.5. Đọc metadata trong controller hoặc service

Một ví dụ chỉ xuất **thông tin được phép** và không trả raw token:

```java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class WhoAmIController {

    @GetMapping("/api/whoami")
    Map<String, Object> whoami(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of(
            "name", principal.getName(),
            "authorities", principal.getAuthorities().stream()
                .map(authority -> authority.getAuthority())
                .sorted()
                .toList()
        );
    }
}
```

Trong hệ thống thật, không nên trả `sub`/`roles`/PII ra public API chỉ để debug. Endpoint minh họa cũng chỉ chạy sau security filter; cần bảo đảm `/api/whoami` có route policy yêu cầu authenticated và chỉ phục vụ thông tin caller được phép xem.

Để đọc attribute:

```java
Object rawScope = principal.getAttribute("scope");
Object rawSubject = principal.getAttribute("sub");
Object rawClientId = principal.getAttribute("client_id");
```

**Không cast mù** mọi trường sang `String` vì kiểu Java có thể phụ thuộc JSON/claim conversion của phiên bản Spring, introspector và issuer; `aud` có thể là chuỗi hoặc collection. Viết mapper/validator theo contract, không dùng `String.valueOf(null)` như thể nó là dữ liệu hợp lệ.

### 6.6. Không dùng `JwtAuthenticationToken` trong opaque mode

Khi Resource Server chạy theo opaque-token introspection, application authentication có thể là `BearerTokenAuthentication` với principal kiểu `OAuth2AuthenticatedPrincipal`, không phải `JwtAuthenticationToken`. Tránh code service cứng:

```java
// KHÔNG DÙNG CHO MỌI LOẠI TOKEN:
JwtAuthenticationToken auth =
    (JwtAuthenticationToken) SecurityContextHolder
        .getContext().getAuthentication();
```

Nếu hệ thống có nhiều token mechanisms, nên xây dựng một **AuthenticatedActor/AccessContext** đã chuẩn hóa từ cơ chế xác thực đang dùng và giữ policy nghiệp vụ độc lập với lớp token của framework.

---

## 7. `active=true` vẫn chưa đủ để truy cập tài nguyên

Xét metadata:

```json
{
  "active": true,
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
```

Token active có thể cho phép đọc một số đơn hàng. Nhưng API phải tiếp tục phân quyền theo:

1. **Audience/resource**: `orders-api` là đúng resource nhận token.
2. **Scope**: `orders:read` cho phép loại thao tác đọc.
3. **Actor context**: subject/user hay service; issuer/tenant/định danh ổn định.
4. **Object-level access**: bản ghi đơn có thuộc phạm vi được phép không.
5. **Business rule**: trạng thái đơn, loại dữ liệu, quyền đối tác, phân tách nhiệm vụ, hạn mức.

Ví dụ:

| Caller | Token active? | Scope đọc? | Đơn | Quyền object | Kết quả |
|---|---:|---:|---|---:|---|
| Alice | Có | Có | Đơn của Alice | Có | Có thể cho phép. |
| Alice | Có | Có | Đơn Bob cùng tenant | Không | 403/404 theo policy. |
| Alice | Có | Không | Đơn của Alice | Có | 403 vì thiếu scope. |
| Service `orders-importer` | Có | Chỉ `orders:import` | Đơn user | Không đúng actor/path | Từ chối. |
| Carol | Có | Có | Đơn tenant khác | Không | Từ chối. |
| Token inactive | Không | Không xét | Bất kỳ | Không xét | Authentication thất bại, thường 401. |

**Phân quyền theo URL chỉ là một tầng**. Route `GET /api/orders/{id}` có `SCOPE_orders:read` vẫn có thể bị **BOLA/IDOR** nếu controller gọi `findById(id)` và trả dữ liệu không kiểm tra subject/tenant.

### 7.1. Lọc dữ liệu bằng chủ thể đã được xác thực

Giả sử bảng `orders` lưu `id`, `tenant_id`, `owner_issuer` và `owner_subject`. Một query thích hợp với policy **read-own**:

```sql
SELECT *
FROM orders
WHERE id = :requested_id
  AND tenant_id = :trusted_tenant_id
  AND owner_issuer = :trusted_issuer
  AND owner_subject = :trusted_subject;
```

Các tham số `trusted_*` phải xuất phát từ metadata introspection đã được xác thực và hợp đồng identity/entitlement của API, **không phải query parameter hoặc JSON body do client nhập**. Nếu AS không trả issuer hoặc tenant, cần một cách giải quyết identity tin cậy khác; không tự điền mặc định giúp request đi qua.

Một user có scope `orders:read` không tự được quyền đọc mọi đơn trong tenant. Nếu cần quyền hỗ trợ/quản trị, đó phải là chính sách riêng có giới hạn scope/role/tenant rõ ràng.

### 7.2. Metadata có thể bị giới hạn theo requester

RFC 7662 cho phép AS quyết định **thông tin nào được tiết lộ** cho caller. Hai Resource Server khác nhau có thể nhận metadata khác nhau cho cùng một token, nếu AS áp dụng policy như vậy.

Vì vậy:

- Không lấy token response của API A rồi giả định API B sẽ nhận tương tự.
- Không chuyển metadata của introspection qua các dịch vụ như một nguồn quyền chung không ràng buộc resource.
- Không cache/chia sẻ metadata giữa nhiều audience/tenant nếu không có namespace/chính sách rõ ràng.
- Không xem thiếu trường `aud` hoặc `client_id` là lỗi RFC mặc định; phải dựa vào contract của từng issuer/resource.

---

## 8. Bảo mật introspection endpoint và client credential

Introspection có thể tiết lộ thông tin token rất nhạy cảm: subject, user, client, scopes, audience, thời gian, tenant hoặc roles. Do đó endpoint không nên là API công khai cho bất kỳ caller nào có token.

### 8.1. Xác thực và ủy quyền bên hỏi

Một thiết kế điển hình:

- Mỗi Resource Server có **introspection client riêng**, ví dụ `orders-api-introspector`.
- AS giới hạn quyền tra cứu token cho đúng resource `orders-api`, theo khả năng AS.
- Staging và production có client/secret riêng.
- Client authentication dùng `client_secret_basic`, private-key JWT hoặc mTLS theo hợp đồng của nhà phát hành.
- Không cấp quyền quản trị AS hoặc quyền xem mọi token nếu API không cần.
- Audit tại AS ghi client ID/tình trạng request phù hợp, **không log raw token hoặc secret**.

**Introspection client ID và token response `client_id` có ý nghĩa khác nhau.** Nếu reviewer nhầm chúng, có thể phát sinh lỗi cấp quyền hoặc ghi nhận audit sai.

### 8.2. Quản lý client secret

Không đặt:

```yaml
# KHÔNG DÙNG TRONG GIT/IMAGE:
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-secret: "orders-prod-real-secret"
```

Thay bằng placeholder và runtime secret injection. Secret Manager, Kubernetes Secret tham chiếu bằng `secretKeyRef`, mounted files hoặc cơ chế phù hợp nền tảng có thể được dùng với quyền tối thiểu.

**Kubernetes Secret lưu Base64 trong manifest không phải mã hóa bảo mật.** Không commit manifest chứa credential Base64 thô rồi coi như an toàn. Với env var injection, sửa secret trên cluster không khiến JVM đang chạy tự nạp giá trị mới; cần rollout/restart hoặc cơ chế reload đã thiết kế.

Không log:

- `Authorization: Basic ...` tới introspection endpoint.
- Body `token=...` của introspection request.
- `Authorization: Bearer ...` của request đến Resource Server.
- Credential trong CI/CD, Docker layer, Java system properties hiển thị ngoài ý muốn hoặc trace HTTP.
- Toàn bộ introspection response chứa PII khi debug.

### 8.3. TLS, fixed endpoint và SSRF

`introspection-uri` phải được lấy từ cấu hình tin cậy, không lấy từ input người dùng hoặc nội dung token chưa xác minh. Nếu attacker thay được URL introspection, Resource Server có thể gửi **cả access token lẫn introspection client credential** đến server của attacker.

Yêu cầu:

1. Dùng **HTTPS** và xác thực đúng TLS certificate/hostname.
2. Kiểm soát redirect; không tự động gửi credentials sang host không tin cậy.
3. Giới hạn outbound network tới AS endpoints phù hợp.
4. Không tắt xác minh TLS khi issuer/proxy gặp lỗi.
5. Đặt HTTP timeout, giới hạn concurrency và kiểm soát response size.
6. Tách observability metadata khỏi dữ liệu nhạy cảm của token và user.

### 8.4. Phân biệt lỗi client credential với token inactive

Nếu AS trả `401 Unauthorized` vì introspection client secret sai, **không** được diễn giải thành `active=false` cho từng token rồi đánh mất tín hiệu sự cố. Trong cả hai tình huống đều phải fail closed, nhưng cách xử lý vận hành khác:

- **Token inactive**: client cần lấy token hợp lệ, API từ chối credential.
- **Introspection client credential sai/hết hạn**: operator phải sửa secret/cấp quyền/rotation; nhiều token hợp lệ cũng sẽ không xác minh được.
- **AS timeout/5xx**: xử lý hạ tầng, retry có giới hạn, alert; không tự cho phép request.

---

## 9. Caching: hiệu năng đối đầu với khả năng thu hồi

Một trong những giá trị của introspection là Authorization Server có thể trả `active=false` ngay cả khi token chưa đến thời điểm `exp` nếu nó đã bị thu hồi. Nếu Resource Server cache kết quả `active=true` quá lâu, lợi ích thu hồi gần thời gian thực sẽ giảm.

### 9.1. Bài toán latency

Giả sử một API nhận 2.000 request/giây, mỗi request gọi introspection:

```text
Client request → orders-api → auth/introspect → orders-api → business response
```

Nếu AS hoặc mạng chậm, latency xác thực trở thành một phần lớn tổng thời gian trả lời. Số lượng request introspection có thể cao ngang số request tới API (tùy cache/framework/cấu hình), tạo tải đáng kể cho AS.

Một số hệ thống muốn cache introspection response theo access token, trong khoảng thời gian ngắn có kiểm soát. Nhưng cache là **quyết định an ninh**, không chỉ là tối ưu thời gian.

### 9.2. Các điều kiện nếu cache introspection

| Nguyên tắc | Vì sao |
|---|---|
| **TTL hữu hạn, ngắn phù hợp chính sách thu hồi** | Tránh tiếp tục tin token đã bị vô hiệu hóa quá lâu. |
| **Không vượt quá `exp`** | Không dùng cache để kéo dài token lifetime. |
| **Phân biệt active=false và lỗi upstream** | Timeout không có nghĩa token inactive; không cache một tình trạng mạng như kết quả trạng thái token. |
| **Cache namespace theo issuer/resource/policy** | Không đem metadata của token trong tài nguyên khác áp dụng cho API này. |
| **Giới hạn số entries và kích thước** | Tránh cache exhaustion do token ngẫu nhiên. |
| **Không ghi raw token trong logs/metrics** | Token là Bearer credential; cache key cần được bảo vệ, không xuất thẳng vào observability. |
| **Thiết kế emergency revocation** | Khi token hoặc client bị lộ, cần cơ chế invalidate/short TTL. |
| **Xác minh policy trên từng request** | Một cached principal không thay thế object authorization, tenant/owner/business state. |

Một cache key có thể cần dùng giá trị HMAC/digest có khóa nội bộ để tránh lưu raw token ở vị trí vận hành dễ quan sát; thiết kế cần chống collision, kiểm soát key và bảo vệ token nguyên gốc trong memory. Không coi SHA-256 hiển thị công khai của bearer token là một credential thay thế hoặc là giải pháp riêng tư tuyệt đối.

### 9.3. Cache TTL và tính mới của quyền

Ngay cả khi token chưa bị thu hồi, quyền user có thể thay đổi:

- User bị rời khỏi tenant.
- Client mất một scope.
- Support role bị thu hồi.
- Order chuyển owner.
- User bị khóa.

Introspection có thể phản ánh một số thay đổi đó **nếu AS có cơ chế cập nhật metadata/trạng thái token**. Nhưng AS không nhất thiết biết mọi thay đổi nghiệp vụ của `orders-api`. Đặc biệt, owner của một order nên được kiểm tra từ nguồn nghiệp vụ tin cậy, không chỉ dựa trên metadata token đã cache.

Có thể chấp nhận khoảng trễ thu hồi khác nhau cho API đọc dữ liệu công khai so với thao tác thanh toán/quản trị. Đây là điều phải được thống nhất với yêu cầu an ninh và SLO, không suy đoán từ default của thư viện.

---

## 10. Timeout, retry và xử lý lỗi mạng

Vì Resource Server phải gọi AS, có thể xuất hiện lỗi DNS, TCP/TLS, connect timeout, read timeout, response không hợp lệ hoặc HTTP `429`/`5xx`.

### 10.1. Quy tắc không bao giờ thay đổi: fail closed

Khi không có response introspection đáng tin hoặc token không active, Resource Server **không thể tạo authenticated principal hợp lệ cho request**. Không được:

- Cho request qua vì AS “chắc tạm thời lỗi”.
- Dùng claims lấy từ token opaque bằng cách parse chuỗi tùy ý.
- Bỏ `scope` check để tránh 403.
- Dùng response introspection từ một issuer/tenant khác.
- Chuyển token chưa xác minh thành user mặc định.
- Retry vô hạn cho đến khi API/gateway timeout.

### 10.2. Phân loại xử lý lỗi

| Sự cố | Retry? | Xử lý bảo mật |
|---|---|---|
| `active=false` | **Không**. | Từ chối authentication. |
| Token chưa có `scope` cần thiết | Không retry introspection để “đợi quyền”. | Từ chối authorization. |
| `401` do Basic credential sai | Không retry vô hạn. | Alert operator, rotate/sửa credential. |
| `403` do client introspection thiếu quyền | Không retry vô hạn. | Sửa grant/policy của AS. |
| `400` do form request sai | Không, trừ khi sửa code/config. | Không chấp nhận token, điều tra request. |
| `429` | Có thể thử lại rất giới hạn, tuân `Retry-After` nếu phù hợp. | Không làm AS quá tải hơn. |
| `503`/`502`/`504` | Có thể retry ngắn nếu còn deadline. | Fail closed khi không có kết quả. |
| Network connect/read timeout | Có thể retry có giới hạn, backoff/jitter. | Không vượt budget của request. |
| TLS certificate invalid | Không cố “sửa” bằng tắt TLS check. | Không gửi secret qua kênh mất tin cậy. |
| Response `active` không phải boolean | Không xem là active. | Xem response không hợp lệ; có thể báo lỗi tích hợp. |
| Response active=true nhưng sai audience/issuer contract | Không retry để bỏ qua policy. | Từ chối authentication/authorization theo lớp thiết kế. |

### 10.3. Bounded retry và giới hạn tải

Một hệ thống có thể cấu hình:

- Connect timeout hữu hạn.
- Read/response timeout hữu hạn.
- Max attempts thấp cho lỗi tạm thời.
- Exponential backoff và jitter.
- Total request deadline bảo vệ SLO.
- Giới hạn số kết nối/requests introspection đồng thời.
- Circuit breaker nếu AS outage kéo dài.
- Rate limit tại API gateway đối với request/token lỗi bất thường.

Các ngưỡng cần xác định từ đo lường p95/p99, số request và năng lực AS. **Không đặt retry ở cả HTTP client, service mesh và gateway với hệ số nhân không được kiểm soát**.

Pseudocode mô tả:

```text
introspect(token):
    if token missing or obviously malformed:
        reject

    for attempt in 1..MAX_ATTEMPTS:
        if request deadline exceeded:
            fail closed

        try:
            response = POST trusted_introspection_endpoint
                       with authorized client authentication
                       and short connect/read timeouts
            validate response schema
            return response
        catch transientNetworkFailure:
            if no attempts remain:
                fail closed
            bounded exponential backoff with jitter

    fail closed
```

Ở đây `return response` **chưa phải là “authorize API”**: vẫn cần đọc `active`, kiểm tra resource/scope/claims contract rồi áp dụng object-level policy. Retry chỉ áp dụng cho lỗi mạng/transient upstream, không phải token sai hoặc thiếu quyền.

### 10.4. HTTP status trả về client

Resource Server nhận `active=false` cho Bearer token của request được bảo vệ thường phản hồi **401**; token active nhưng không có `orders:read` thường phản hồi **403**. Với dependency failure từ introspection, mã phản hồi tùy lớp exception handling: có thể là lỗi authentication hoặc lỗi máy chủ/upstream; nếu cần hiển thị `503`, phải thiết kế và test chính xác, tránh tiết lộ secret.

Đừng đồng nhất:

```text
HTTP 401 của AS với client introspection -> lỗi credential của Resource Server
HTTP 401 của orders-api với Bearer request -> token client không được chấp nhận
HTTP 403 của orders-api -> token đã xác thực nhưng quyền thiếu
```

Chúng là ba HTTP response khác vai trò, dù mã có thể giống nhau.

---

## 11. Kiểm thử introspection với Spring Security

Để test đúng, phải tách:

1. **Route authorization**: principal có quyền nào được phép làm gì?
2. **Introspection client integration**: API gửi đúng POST, header credentials và body form?
3. **Response parsing và contract**: `active`, claims, audience, scope, thời gian.
4. **Failure behavior**: network/HTTP errors và fail-closed.
5. **Business object authorization**: owner/tenant/ACL sau khi token active.

### 11.1. MockMvc test route bằng `opaqueToken()`

`spring-security-test` cung cấp request post-processor `opaqueToken()` tạo authentication giả, phù hợp để kiểm tra HTTP authorization mà không cần gọi AS.

```java
package com.example.orders.security;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void activePrincipalWithReadAuthorityCanReachRoute() throws Exception {
        mvc.perform(get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
            // Giả sử fixture controller/service cho phép principal thử nghiệm
            // đọc order 42 và trả 200.
            .andExpect(status().isOk());
    }

    @Test
    void principalWithoutReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:write"))))
            .andExpect(status().isForbidden());
    }
}
```

Đây là **mẫu kiểm tra route**, giả định controller `GET /api/orders/42` tồn tại và business policy cho phép principal fixture truy cập. Nếu service còn đòi `sub`/tenant/owner, phải cung cấp attributes/fixture tương ứng; không nên loại bỏ object-level policy chỉ để test xanh.

**`opaqueToken()` không gửi introspection HTTP, không kiểm tra client secret, không parse response `active` từ AS và không kiểm tra timeout/TLS.** Nó tạo principal đã xác thực trong test, vì vậy không thể dùng để chứng minh RFC 7662 integration.

### 11.2. HTTP stub mô phỏng Authorization Server

Dùng HTTP server cục bộ như WireMock/MockWebServer để kiểm tra:

- Request là `POST` đến đúng path `/oauth2/introspect`.
- Content-Type là form URL encoded.
- Form thực sự chứa token đầu vào, `token_type_hint` nếu cấu hình sử dụng.
- Cơ chế xác thực requester đúng `client_secret_basic` hoặc cơ chế được AS dev cam kết.
- Không gửi credentials tới host/redirect khác.
- `active=true` với `scope` phù hợp ánh xạ thành authority.
- `active=false` khiến authentication thất bại.
- HTTP `401`/`403` từ AS vì credential sai được xử lý như lỗi tích hợp, không cho user qua.
- Timeout, `503`, JSON sai không tạo authenticated principal.
- Response thiếu `aud`/`iss` được xử lý theo contract cụ thể, không tự cấp quyền nếu policy bắt buộc các trường đó.

Chỉ dùng client secret **giả** trong fixture. Tránh in header Basic, form token hoặc introspection body chứa thông tin user vào test reports.

### 11.3. Ma trận response mẫu

| Response từ stub | Kỳ vọng |
|---|---|
| `{"active":false}` | Token không được chấp nhận, không vào controller. |
| `{"active":true,"scope":"orders:read"}` | Chỉ có quyền đọc, nếu contract resource cho phép. |
| `{"active":true,"scope":"orders:write"}` | Không có quyền `SCOPE_orders:read`; route GET cần read bị 403. |
| `{"active":true}` | Không được tự phát sinh scope. Route cần scope bị từ chối. |
| `{"active":"true"}` | Phản hồi sai kiểu; không chấp nhận token theo schema chuẩn. |
| `{"scope":"orders:read"}` | Thiếu `active` bắt buộc; không chấp nhận. |
| `{"active":true,"aud":"payments-api","scope":"orders:read"}` | Bị từ chối nếu policy của API yêu cầu audience chứa `orders-api`. |
| `{"active":true,"exp":<expired-time>}` | Phải tuân hợp đồng về thời hạn/AS policy, không cho cache kéo dài token. |
| `{"active":true,"roles":["ADMIN"]}` | Không tự tạo admin authority nếu không có converter/contract riêng. |
| HTTP 401 từ AS | Không cấp quyền, cảnh báo credential introspection. |
| HTTP 429 hoặc 503 từ AS | Retry có giới hạn nếu policy cho phép, sau đó fail closed. |
| Network timeout | Không cấp quyền; quan sát latency, timeout và handler. |

Dòng `<expired-time>` chỉ là placeholder trình bày, không phải JSON hợp lệ; trong fixture thực phải dùng NumericDate là số (ví dụ 1700000000) hoặc tạo động so với clock test.

### 11.4. Test object-level authorization

Giả sử Alice có `SCOPE_orders:read` và token active. Test phải vẫn chứng minh:

- Alice đọc đơn của Alice được phép.
- Alice đọc đơn của Bob **trong cùng tenant** bị từ chối.
- Alice đọc đơn của tenant khác bị từ chối.
- Client Credentials token không bị nhầm thành user token.
- Endpoint list/export/bulk kiểm tra phạm vi **mọi bản ghi**, không chỉ route-level scope.
- Hành vi khi thiếu `sub` hoặc `tenant_id` theo contract: từ chối/không cấp quyền, không chọn một user mặc định.

Một response `active=true` trong test không thể thay thế các kiểm tra quyền trên dữ liệu thật.

### 11.5. Contract test với AS thật ở staging

Các test bằng stub vẫn có thể bỏ sót khác biệt nhà cung cấp. Trong staging, dùng **client introspection riêng** và token staging:

1. Tạo access token hợp lệ, gọi introspection thành công.
2. Thu hồi token, xác nhận `active=false` theo semantics provider.
3. Đợi token hết hạn, kiểm tra phản hồi và behavior API.
4. Thử token thuộc audience/resource khác, kiểm tra AS trả metadata/`active` thế nào.
5. Thử access token Client Credentials và user token, so sánh `sub`, `client_id`, `scope`.
6. Kiểm tra metadata nào thực sự có mặt (`iss`, `aud`, `exp`, `jti`, custom claims).
7. Thử credential introspection sai/thiếu quyền; không nhầm nó với token inactive.
8. Thử quota, timeout và sự cố mạng có kiểm soát.
9. Kiểm tra logs/traces/APM không tiết lộ raw token hoặc secret.
10. Xác nhận schema/contract được ghi lại cho team Resource Server, kể cả những trường tùy chọn **không** được AS cung cấp.

Không dùng credential production cho staging hoặc developer local.

---

## 12. Lỗi tích hợp và cách chẩn đoán

### 12.1. Token hợp lệ nhưng API trả 401

Các nguyên nhân có thể:

- AS trả `active=false` do token hết hạn/bị thu hồi/không thuộc phạm vi introspection requester.
- Resource Server gửi nhầm **refresh token** hoặc ID Token vào API.
- API sử dụng introspection endpoint sai tenant/realm/issuer.
- Credential introspection của Resource Server hết hiệu lực.
- AS trả kiểu `active` không tương thích parser hoặc response sai định dạng.
- Token chỉ được cấp cho audience khác.
- Policy của API yêu cầu một claim không có trong response.

Cách điều tra: tra request correlation ID, status AS, tên client introspection, token profile và kết quả kiểm tra claims **không log raw token hoặc secret**.

### 12.2. Token active, nhưng API trả 403

Nguyên nhân thường gặp:

- Không có `scope` hoặc scope khác với endpoint yêu cầu.
- Tên authority không khớp tiền tố `SCOPE_`.
- Issuer trả `scp`/`permissions`/`roles` nhưng API vẫn dùng mapping mặc định chỉ đọc `scope`.
- Token là client credential token có quyền khác user token.
- Token có scope đúng nhưng không có quyền trên resource/tenant/owner cụ thể.

Không sửa bằng cách thay `hasAuthority("SCOPE_orders:read")` thành `authenticated()` để tất cả request qua; hãy kiểm tra contract và định nghĩa policy đúng.

### 12.3. Hệ thống bị chậm hoặc outage khi AS chậm

Nguyên nhân có thể là mỗi request API đều cần round-trip introspection, retry không giới hạn, thiếu timeout, connection pool bị cạn hoặc AS rate-limit. Hướng khắc phục gồm:

- Đặt connect/read/overall timeout.
- Bounded retry cho transient errors, có backoff/jitter.
- Giới hạn concurrency, connection pool và circuit breaker.
- Tối ưu AS availability và network route.
- Cache introspection có TTL **theo policy revocation**, không mặc định cache vô hạn.
- Tách alert dependency failure khỏi token invalid và thiếu scope.

Không bỏ qua token verification hoặc bật `permitAll()` để che sự cố.

### 12.4. Vừa migrate từ JWT sang opaque token

Cần kiểm tra:

- Spring filter chain đã chuyển từ `jwt()` sang `opaqueToken()` hoặc có giải pháp đa loại token được kiểm soát.
- Principal type đã thay đổi; service không cast cứng `JwtAuthenticationToken`.
- Các claim/authorities có thể không giống JWT payload cũ.
- Thời hạn/issuer/audience metadata introspection có thể không được trả đủ như token JWT.
- Thao tác logout/revocation/caching phải được đánh giá lại.
- Credential introspection và timeout/network đã được provision.
- Test authentication và route/business policies được tách thành các lớp.

**Migrate token format không làm quyền nghiệp vụ tự chính xác hơn.** Resource Server vẫn phải thực thi scope, owner và tenant.

---

## 13. Thiết kế hợp đồng introspection có thể bàn giao

Trước khi production, đội Identity và API nên thống nhất thành văn:

| Mục hợp đồng | Câu hỏi phải trả lời |
|---|---|
| **Issuer / realm** | AS nào có quyền xác nhận token? Làm sao Resource Server chống nhầm issuer? |
| **Endpoint** | HTTPS introspection URL cố định là gì? Có proxy/mTLS không? |
| **Client authentication** | Basic/client secret, private-key JWT, mTLS hay cơ chế khác? Quyền requester được giới hạn thế nào? |
| **Token profile** | Chỉ access token? Opaque hay JWT được introspect? Có khác theo grant? |
| **`active` semantics** | AS xem token active/không được truy cập ra sao? Khi revocation trả gì? |
| **Metadata bắt buộc theo ứng dụng** | `scope`, `client_id`, `sub`, `aud`, `iss`, `exp`, tenant/roles có phải luôn xuất hiện không? |
| **Kiểu dữ liệu** | Scope string hay custom collection? Audience string hay array? NumericDate ở đơn vị giây? |
| **Resource binding** | Token dành cho `orders-api` được chứng minh bằng `aud` hay AS hạn chế `active` theo requester? |
| **Authority mapping** | `scope` ánh xạ `SCOPE_...`; custom roles/perms được cho phép thế nào? |
| **Object authorization** | Quyền owner/tenant/ACL được kiểm tra ở đâu? |
| **Error contract** | 200 inactive, 400 invalid request, 401/403 credential, 429/5xx; behavior fail closed. |
| **Timeout và retry** | SLO, tổng deadline, max attempts, backoff, concurrency limits. |
| **Caching và thu hồi** | Cache TTL tối đa, cơ chế invalidate và chênh lệch trạng thái quyền cho phép. |
| **Logging/audit** | Những trường nào được phép lưu; chặn log raw token, client secret và PII. |
| **Rotation/incident** | Khi introspection client secret bị lộ/đổi, API rollout thế nào? |
| **Testing** | Stub protocol test, schema test, staging integration và BOLA/tenant negative tests. |

### 13.1. Một checklist triển khai theo thứ tự

1. **Đăng ký introspection client** với AS, có quyền tối thiểu cho `orders-api`.
2. **Cấp secret/private credential** từ Secret Manager tại runtime, không đưa vào source code.
3. **Cấu hình Spring Boot** với `introspection-uri`, `client-id`, `client-secret` hoặc custom authentication method phù hợp.
4. **Chọn filter chain** opaque token và xác định route-level scope authorities.
5. **Xác định metadata contract**: `active`, `scope`, `sub`, `aud`, `iss`, `exp` và custom claims.
6. **Kiểm tra audience/issuer/resource binding**, không chỉ `active=true`.
7. **Kiểm tra object-level authorization** tại service/repository cho dữ liệu đơn hàng.
8. **Thiết lập TLS, timeout, rate limit và log masking**.
9. **Chọn cache policy** dựa trên thời gian sống token và yêu cầu thu hồi.
10. **Kiểm thử** bằng token active/inactive, credential sai, thiếu scope, khác audience/tenant, timeout và AS outage.
11. **Diễn tập rotation** credential introspection và incident response khi bị lộ.
12. **Quan sát production** theo tỷ lệ introspection success/failure, latency, 401/403 và lỗi dependency, không ghi raw token.

---

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Opaque token chỉ cần Base64 decode là đọc được scope.” | Token opaque không có nội dung đáng tin để tự suy ra quyền. Cần introspection hoặc cơ chế do AS cung cấp. |
| “Introspection là một lệnh GET tiện để debug.” | RFC 7662 định nghĩa POST form-urlencoded, với `token` bắt buộc và auth/transport an toàn. |
| “`token_type_hint=access_token` chứng minh token là access token.” | Đây chỉ là hint; AS xác định trạng thái/loại token theo chính sách của mình. |
| “HTTP 200 nghĩa là token valid.” | Phải kiểm tra JSON `active`; `200 + active=false` là token không active/không xem được. |
| “HTTP 401 từ AS giống token inactive.” | Thường là client introspection chưa xác thực; đây là lỗi credential/tích hợp. |
| “`active=true` cấp mọi quyền.” | Vẫn cần resource binding, scope, role, tenant và object-level authorization. |
| “`client_id` trong response là client ID gọi introspection.” | Thường là OAuth client đã yêu cầu token, không phải introspection requester. |
| “Response luôn có `sub`, `aud`, `exp`.” | Theo RFC 7662, ngoài `active` những metadata đó là tùy chọn. |
| “`username` là owner ID ổn định.” | Username có thể đổi; dùng identity contract như issuer + subject/internal ID. |
| “`scope` và `roles` luôn tương đương.” | Đây là các claim/ngữ nghĩa khác nhau; cần mapper theo issuer/profile. |
| “Access token đã bị revoke thì Resource Server luôn biết tức thì.” | Nếu cache introspection response, API có thể tiếp tục thấy active=true đến khi cache hết hạn/được invalidate. |
| “AS không phản hồi thì cho request qua để giữ uptime.” | Không có kết quả xác thực đáng tin → **fail closed**. |
| “Spring `opaqueToken()` test đã gọi AS.” | Mock principal bỏ qua introspection HTTP, cần integration test riêng. |
| “Sang opaque token thì không cần kiểm tra owner/tenant.” | BOLA và phân quyền dữ liệu không biến mất khi thay token format. |
| “Vì JWKS công khai nên introspection endpoint cũng phải công khai.” | Introspection có thể tiết lộ trạng thái/metadata nhạy cảm và phải bảo vệ requester bằng xác thực/ủy quyền. |

## 15. Tóm lược luồng tư duy

Một triển khai Resource Server an toàn với RFC 7662 nên tuân theo chuỗi:

```text
Client gửi Bearer access token đến orders-api
                │
                ▼
Resource Server nhận token nhưng chưa tin nội dung
                │
                ▼
HTTPS POST introspection request
  ├─ token=<access token của request>
  ├─ token_type_hint=access_token (tùy chọn)
  └─ client authentication của orders-api-introspector
                │
                ▼
Authorization Server xử lý
  ├─ requester được phép gọi endpoint?
  ├─ requester được phép xem trạng thái token?
  ├─ token tồn tại, còn hạn, chưa bị revoke?
  └─ metadata nào được phép trả về?
                │
                ▼
JSON response
  ├─ active=false -> từ chối authentication
  └─ active=true  -> tiếp tục xác minh contract
                       ├─ audience/issuer/resource đúng?
                       ├─ token type/profile đúng?
                       ├─ scopes/roles đủ?
                       └─ owner/tenant/business constraints đạt?
                                 │
                                 ▼
                           Cho phép nghiệp vụ
                    hoặc từ chối 401 / 403 / 404
```

**Ghi nhớ:** **RFC 7662 cung cấp trạng thái token và metadata cho một requester được phép; nó không thay thế các quy tắc phân quyền của chính Resource Server.** `active` là điều kiện đầu tiên. Scope, audience, subject và dữ liệu bổ sung chỉ có ý nghĩa khi được hiểu đúng theo hợp đồng issuer; object-level authorization vẫn là trách nhiệm của API.

### Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): request, response, `active`, client authorization và cân nhắc bảo mật.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication, access token và scope.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cách dùng Bearer token và lỗi protected resource.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): NumericDate, `sub`, `iss`, `aud` nếu metadata response sử dụng các tên claim tương tự.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): hợp đồng JWT access token và khác biệt với introspection.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình `opaquetoken`, authorities và `OpaqueTokenIntrospector`.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): đối chiếu mô hình local JWT verification.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): lý do phải kiểm tra quyền đối với đúng tài nguyên sau khi token được xác thực.
