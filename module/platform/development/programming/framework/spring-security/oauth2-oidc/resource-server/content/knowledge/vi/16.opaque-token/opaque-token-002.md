# Định dạng token không quyết định bắt buộc phải xác minh cục bộ hay từ xa

Khi xây dựng **Spring Security OAuth 2.0/OIDC Resource Server**, người học thường bắt gặp một cách diễn giải ngắn gọn:

> “JWT thì Resource Server tự xác minh ở máy của mình; opaque token thì phải gọi Authorization Server để introspect.”

Đó là **hai cách triển khai rất phổ biến**, nhưng **không phải một quy tắc bắt buộc xuất phát từ định dạng token**. Một JWT có thể được kiểm tra qua một dịch vụ introspection từ xa; ngược lại, một opaque token có thể được xác minh hoặc đối chiếu ngay tại hạ tầng nội bộ của Resource Server nếu hệ thống sở hữu thông tin, khóa hoặc trạng thái đáng tin cậy cần thiết.

Muốn hiểu chính xác, cần tách **hai câu hỏi độc lập**:

1. **Token trông như thế nào và bên nhận có thể hiểu được nội dung không?** Đây là câu hỏi về **định dạng/biểu diễn token**: JWT, chuỗi opaque ngẫu nhiên, token được mã hóa, định dạng riêng.
2. **Resource Server lấy bằng chứng về tính hợp lệ ở đâu?** Đây là câu hỏi về **kiến trúc xác minh**: kiểm tra chữ ký/khóa hoặc trạng thái cục bộ, gọi introspection từ xa, hay kết hợp nhiều nguồn.

Trong chương **Opaque token** của module **Spring Security OAuth 2.0 OIDC Resource Server**, bài học này phân tích bốn tổ hợp thường bị nhầm lẫn, cách Spring Security triển khai chúng, các ràng buộc bảo mật và cách chọn giải pháp theo hợp đồng giữa Authorization Server và Resource Server.

> **Phạm vi:** chủ yếu là **OAuth 2.0 access token** được gửi qua `Authorization: Bearer ...`. **OIDC ID token** phục vụ xác thực danh tính cho client, không tự động là access token dành cho API. Các URI, token và mã định danh trong ví dụ đều là dữ liệu giả lập.

## 1. Hai trục độc lập: định dạng và cách xác minh

### 1.1. Định dạng token trả lời điều gì?

| Dạng token | Bên nhận quan sát được gì? | Có tự chứng minh token đang hợp lệ không? |
|---|---|---|
| **JWT dạng JWS** | Chuỗi compact gồm header, claims, chữ ký; payload thường đọc được bằng Base64URL decode | **Không**. Phải xác minh chữ ký, thuật toán, khóa và claims theo policy |
| **Opaque token ngẫu nhiên** | Chuỗi không có ý nghĩa được công bố cho Resource Server/client; thường là một handle | **Không**. Phải đối chiếu với nguồn sự thật tin cậy hoặc cơ chế xác minh nội bộ |
| **Token tự chứa nhưng được mã hóa** | Có thể trông opaque đối với bên không có khóa giải mã | **Không**. Phải có khóa phù hợp, kiểm tra tính toàn vẹn, claims và thời hạn |
| **Token định dạng riêng** | Có thể là chuỗi có cấu trúc hoặc có chữ ký/MAC riêng | **Không**. Cần thuật toán và hợp đồng kiểm tra được thiết kế an toàn |

JWT không chỉ là một chuỗi “có ba dấu chấm”: JWT là một cấu trúc token theo chuẩn, được bảo vệ bằng những cơ chế JOSE phù hợp. JWT ký dạng JWS compact thường có **ba phần**; JWT mã hóa dạng JWE compact thường có **năm phần**. Không nên chọn đường xác minh chỉ bằng cách đếm dấu chấm của chuỗi chưa tin cậy.

**Opaque** là nhận xét về **giao diện đối với bên sử dụng token**: client hoặc Resource Server không được kỳ vọng trích xuất ngữ nghĩa token bằng cách đọc nội dung của nó. Từ đó **không thể suy ra** token bắt buộc phải được kiểm tra từ xa trong mọi kiến trúc.

### 1.2. Cách xác minh trả lời điều gì?

| Phương án xác minh | Nguồn tin cậy | Điểm cần có |
|---|---|---|
| **Cục bộ bằng mật mã** | Khóa công khai/bí mật hoặc vật liệu xác minh đã tin cậy | Kiểm tra chữ ký/MAC, issuer, audience, thời gian và policy |
| **Cục bộ bằng trạng thái** | Kho token/session/ủy quyền được Resource Server tin cậy và được đồng bộ | Lookup handle, trạng thái active/revoked, expiry, client/audience/scope |
| **Từ xa bằng introspection** | Authorization Server hoặc dịch vụ kiểm tra token đáng tin | Kênh bảo mật, thông tin xác thực gọi introspection, xử lý `active` và attributes |
| **Kết hợp** | Kiểm tra local cùng dữ liệu thu hồi/cache/dịch vụ từ xa | Chính sách freshness, tính nhất quán, ưu tiên khi upstream lỗi |

**Từ xa** có thể là OAuth 2.0 Token Introspection theo RFC 7662 hoặc một dịch vụ xác minh chuyên dụng trong kiến trúc nội bộ. **Cục bộ** có thể nghĩa là xác minh chữ ký **hoặc** tra cứu trạng thái do ứng dụng sở hữu; không chỉ có một nghĩa “giải mã JWT”.

### 1.3. Ma trận bốn khả năng

| | **Xác minh cục bộ** | **Xác minh từ xa** |
|---|---|---|
| **JWT** | Resource Server dùng `JwtDecoder`, JWK/khóa tin cậy, validators để xác minh JWT | Resource Server gửi JWT nguyên vẹn tới introspection endpoint nếu Authorization Server **có hỗ trợ** introspect loại JWT đó |
| **Opaque token** | Resource Server tra cứu handle trong token store nội bộ/đồng bộ, hoặc xác minh định dạng opaque có bảo vệ mật mã mà nó được thiết kế để hiểu | Resource Server gửi opaque token tới introspection endpoint; đây là cách phổ biến khi API không biết cấu trúc token |

Những ô này thể hiện **tính khả thi theo kiến trúc**, không nói rằng Spring Security mặc định tự hỗ trợ tất cả mà không cần cấu hình.

~~~mermaid
flowchart TD
    A["Client gửi Bearer access token"] --> B{"Hợp đồng xác minh đã chọn?"}
    B -->|"Local crypto"| C["Decoder/logic tin cậy xác minh chữ ký hoặc MAC"]
    B -->|"Local state"| D["Tra cứu token handle trong kho tin cậy"]
    B -->|"Remote introspection"| E["Gọi Authorization Server"]
    C --> F["Kiểm tra token policy: thời gian, iss, aud, trạng thái cần thiết"]
    D --> F
    E --> F
    F --> G{"Được chấp nhận?"}
    G -->|No| H["Từ chối authentication"]
    G -->|Yes| I["Authentication + GrantedAuthority"]
    I --> J["HTTP/method/domain authorization"]
~~~

**Kết luận nền tảng:** định dạng token cho biết *cần hiểu token bằng cách nào*; cách xác minh là quyết định *nguồn nào có quyền tuyên bố token đang hợp lệ*.

## 2. JWT: có cấu trúc không đồng nghĩa bắt buộc xác minh tại chỗ

Một JWT access token ký bằng JWS có thể gồm:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(CLAIMS).BASE64URL(SIGNATURE)
~~~

JOSE header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "auth-key-2026-11",
  "typ": "at+jwt"
}
~~~

Claims minh họa:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "client_id": "shop-web",
  "iat": 1924988400,
  "exp": 1924992000
}
~~~

Đây không phải token có chữ ký thật. `typ=at+jwt` là một ví dụ theo token profile như RFC 9068; cách nhận diện token type và các claims bắt buộc phải phù hợp hợp đồng của Authorization Server.

### 2.1. Cách phổ biến: JWT được kiểm tra cục bộ

Resource Server:

1. Lấy public keys từ JWK Set đáng tin (có thể cache).
2. Chọn key và thuật toán ký **được cho phép**, không tin tùy tiện vào `alg`, `kid`, `jku` do JWT gửi lên.
3. Xác minh JWS signature.
4. Kiểm tra issuer, thời gian `exp`/`nbf`, audience của API, token profile và những claims bắt buộc khác.
5. Chuyển JWT đã xác minh thành principal/authorities rồi áp phân quyền HTTP và nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Resource Server
    participant K as Trusted JWK Set
    C->>R: Authorization: Bearer <JWT>
    R->>K: Lấy/refresh public keys khi cần
    K-->>R: JWK Set đã tin cậy
    R->>R: Verify JWS, iss, exp, nbf, aud...
    R->>R: Tạo Authentication + authorities
    R-->>C: Response nghiệp vụ hoặc lỗi
~~~

Ưu điểm: không cần gọi Authorization Server **cho mỗi request** chỉ để xác nhận chữ ký khi đã có key. Nhưng không vì vậy mà “JWT local = không có phụ thuộc mạng”: việc tải/refresh JWKS, issuer metadata, key rotation hoặc các kiểm tra thu hồi bổ sung vẫn có thể cần truy cập hệ thống khác.

### 2.2. JWT hoàn toàn có thể được introspect từ xa

Nếu Authorization Server hỗ trợ OAuth 2.0 Token Introspection cho JWT access token, Resource Server có thể gửi **nguyên chuỗi JWT** đến introspection endpoint. Authorization Server sẽ đánh giá token theo chính sách của nó và trả metadata, trong đó `active` cho biết trạng thái được chấp nhận theo định nghĩa của server.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Orders Resource Server
    participant A as Authorization Server
    C->>R: Authorization: Bearer <JWT>
    R->>A: POST /introspect, token=<JWT> + caller authentication
    A->>A: Kiểm tra token và trạng thái cấp phép
    A-->>R: active=true, sub, scope, aud, exp...
    R->>R: Áp policy cho Orders API
    R-->>C: API response
~~~

Từ góc nhìn Spring Security, nếu bạn cấu hình `opaqueToken()`, **đường xử lý đó dùng introspection**, kể cả khi chuỗi token có hình dạng JWT. Tên DSL **`opaqueToken` mô tả chiến lược authentication đã chọn**, không phải một bộ phân tích “bắt buộc token phải không có dấu chấm”.

Điều kiện tiên quyết:

- Authorization Server thực sự cho phép introspection loại JWT access token đó.
- Resource Server có quyền gọi introspection và bảo vệ client credentials.
- Introspection response đủ metadata để Resource Server áp chính sách audience, thời gian, client/tenant và scopes.
- Các trường `active`, `exp` hoặc metadata khác được xử lý theo hợp đồng; không tự giả định mọi introspection endpoint đều trả toàn bộ claims của JWT.

Một Authorization Server có thể **không hỗ trợ** introspection cho JWT, hoặc chỉ cho phép một số client introspect một số loại token. Khi đó không thể kết luận “JWT nào cũng introspect được” chỉ từ định dạng JWT.

### 2.3. Vì sao tổ chức chọn introspection cho JWT?

| Lý do | Ý nghĩa |
|---|---|
| Kiểm tra trạng thái thu hồi gần thời gian thực | AS có thể biết token đã bị vô hiệu hóa dù `exp` chưa đến |
| Chính sách động | AS áp trạng thái user/client/session hoặc chính sách bảo mật mới |
| Không muốn nhiều Resource Server tự quản lý JOSE/JWK | Dồn việc xác thực token vào dịch vụ tập trung |
| Tập trung audit/quyền quan sát | Mỗi request được kiểm tra qua AS hoặc dịch vụ kiểm tra |
| Kiểm soát metadata trả về | AS có thể chỉ trả claims/attributes mà caller introspection được phép nhận |

Đổi lại là **độ trễ mạng, chi phí truy vấn, phụ thuộc tính sẵn sàng của AS**, và bài toán cache introspection nếu cần tăng hiệu năng.

### 2.4. JWT decode payload không phải JWT validation

Đoạn code chỉ Base64URL decode phần claims:

~~~java
// PHẢN VÍ DỤ — chỉ đọc payload, KHÔNG xác minh chữ ký.
String[] parts = token.split("\\.");
String json = new String(
    java.util.Base64.getUrlDecoder().decode(parts[1]),
    java.nio.charset.StandardCharsets.UTF_8
);
~~~

Không được lấy `scope`, `sub` hoặc `role` từ JSON chưa xác minh rồi tạo `Authentication`. Nếu muốn xác minh cục bộ, dùng decoder/JOSE library đáng tin. Nếu muốn từ xa, dùng introspection endpoint đáng tin và kiểm tra response. **Không có phương án “xem JWT đọc được là đủ tin”.**

## 3. Opaque token: không đọc được không đồng nghĩa không thể xác minh cục bộ

Một opaque access token có thể trông như:

~~~text
Authorization: Bearer opaque_7WxbS4N5KrFvXyN9Tq...<redacted>
~~~

Đây là **minh họa chuỗi**, không phải credential thật. Đối với Resource Server không biết cách diễn giải, nội dung chỉ là token handle. Nó không thể lấy `sub` hay `scope` trực tiếp bằng Base64URL decode giống JWT có payload công khai.

### 3.1. Trường hợp phổ biến: opaque token tra cứu từ xa

Authorization Server phát hành một chuỗi ngẫu nhiên, lưu trạng thái liên quan và cung cấp introspection endpoint:

~~~text
Token handle:   giá trị ngẫu nhiên khó đoán
AS token store:
    handle / fingerprint → active, exp, sub, aud, scope, client_id...

Resource Server:
    nhận handle
    → gọi AS introspection
    → xem active + metadata
    → tạo principal và authorities
~~~

Cách này phù hợp khi Resource Server không sở hữu token store và không có thông tin nội bộ để quyết định token nào còn active.

### 3.2. Opaque token có thể được kiểm tra cục bộ bằng kho dữ liệu tin cậy

Giả sử **chính nền tảng triển khai cả token issuing và Resource Server**, hoặc có một kho trạng thái được sao chép/đồng bộ đáng tin tới hạ tầng của Resource Server:

~~~text
Client token:
  256-bit random bearer handle

Local trusted token store:
  digest(handle) → {
      subject,
      audience,
      scopes,
      expiresAt,
      revoked,
      issuer,
      clientId
  }
~~~

Resource Server nhận handle, tính một fingerprint có thiết kế phù hợp, **tra cứu bản ghi cục bộ**, rồi kiểm tra hết hạn, trạng thái thu hồi, resource được phép nhận và các điều kiện khác.

Không có HTTP introspection mỗi request ở đây, nhưng **vẫn có một nguồn sự thật tin cậy**: kho token cục bộ/đồng bộ. Đây là local validation theo **trạng thái**, không phải “giải mã opaque string để đoán danh tính”.

Điều kiện an toàn quan trọng:

- Token phải có entropy đủ cao, không thể đoán hoặc liệt kê.
- Store không được tự chấp nhận một handle chưa từng được phát hành.
- Lookup và so khớp không tiết lộ token trong logs hoặc lỗi.
- Metadata gắn với token phải có nguồn đáng tin, có TTL/expiry và revocation state.
- Với đa Resource Server, dữ liệu phải được phân phối nhất quán theo policy.
- Token gửi tới API khác không được chấp nhận chỉ vì handle tồn tại: cần kiểm tra audience/resource.
- Khi store lỗi hoặc thiếu dữ liệu xác thực, phải **fail closed**, không tự cấp principal.

Nếu Resource Server **không có** kho dữ liệu/khóa/thuật toán xác minh tương ứng, một opaque random string riêng lẻ **không đủ thông tin để xác minh cục bộ**. Khi ấy cần introspection hoặc phương án chia sẻ trạng thái được thiết kế trước.

### 3.3. Opaque đối với client, có cấu trúc mật mã đối với issuer

Không phải mọi opaque token đều là random database key. Issuer có thể phát hành một token có payload **được mã hóa và xác thực**, hoặc token định dạng riêng có MAC/signature, nhưng không công bố cấu trúc cho client.

Nếu Resource Server nắm khóa, thuật toán và hợp đồng phù hợp, nó có thể:

1. Xác minh integrity/authenticity của token.
2. Giải mã nội dung khi cần và khi có quyền.
3. Kiểm tra thời gian, issuer, audience và token type.
4. Tạo principal và authorities theo claims đã được xác thực.

Từ phía client, token vẫn **opaque**: client chỉ chuyển tiếp nguyên giá trị mà không cần hiểu nội dung. Từ phía Resource Server được ủy quyền, nó có thể mang dữ liệu tự chứa có thể kiểm tra cục bộ.

**Không suy ra rằng Spring Security mặc định có thể giải mã mọi opaque/encrypted token.** Một `JwtDecoder` xử lý JWT theo những định dạng, thuật toán mà implementation hỗ trợ; token được mã hóa như JWE hoặc định dạng proprietary có thể cần thành phần xác minh/giải mã riêng và phải tuân thủ hợp đồng mật mã. Không tự thiết kế một thuật toán “mã hóa base64” để coi đó là xác thực.

### 3.4. “Opaque token local” không đồng nghĩa bỏ revocation và expiry

Nếu token store cục bộ chỉ map `handle → subject` mà không có `active/revoked/exp/aud`, Resource Server có thể tiếp tục chấp nhận token đã hết hạn hoặc bị thu hồi, hoặc chấp nhận token dành cho API khác.

Một token validator local an toàn cần ít nhất những chính sách:

~~~text
Handle tồn tại trong nguồn tin cậy?
AND token đang active, chưa revoked?
AND chưa hết hạn và đã bắt đầu hiệu lực (nếu có)?
AND được cấp cho Resource Server hiện tại?
AND issuer/client/tenant/profile đáp ứng hợp đồng?
    ↓
Chỉ khi đạt mới tạo Authentication
~~~

Với token tự chứa được xác minh cục bộ bằng mật mã mà không có state lookup, trạng thái **thu hồi tức thời** có thể không biết được; cần cân nhắc thời hạn ngắn, denylist, state synchronization hoặc introspection bổ sung.

## 4. RFC 7662: introspection là một giao thức, không phải định dạng token

OAuth 2.0 Token Introspection (**RFC 7662**) định nghĩa cách một bên được phép hỏi Authorization Server về một token. Thao tác nhận một **token string** và trả một response JSON có trường `active`. Định dạng token mà Authorization Server dùng nội bộ không phải điều kiện quyết định của giao thức này.

### 4.1. Request introspection

Ví dụ:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <ENCODED_INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

Chú ý:

- `Authorization: Basic ...` ở đây mang **thông tin xác thực của Resource Server gọi introspection**, không phải Bearer JWT của người dùng.
- Parameter `token` mang credential cần kiểm tra; **không log request body** này.
- `token_type_hint` chỉ là **gợi ý**, không phải bằng chứng token type; Authorization Server có thể bỏ qua hint theo chuẩn.
- Introspection endpoint phải sử dụng HTTPS và kiểm soát quyền truy cập, không cho một client không được phép dò trạng thái token tùy ý.
- Các cơ chế client authentication khác ngoài Basic có thể được sử dụng nếu Authorization Server hỗ trợ và cấu hình hợp đồng phù hợp.

### 4.2. Response khi token được chấp nhận

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "client_id": "shop-web",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1924992000,
  "iat": 1924988400,
  "iss": "https://login.example.test/realms/company",
  "aud": "orders-api"
}
~~~

Các metadata này là minh họa. **RFC 7662 không bắt buộc mọi response active phải có đầy đủ mọi field trên**. Authorization Server có thể chọn các trường trả về dựa trên token và quyền của caller introspection. Resource Server cần biết **trường nào bắt buộc theo hợp đồng API** và từ chối/không cấp quyền khi thiếu thông tin cần thiết.

Một response `active=true` thường cho biết Authorization Server nhận thấy token hợp lệ/active theo tiêu chí của nó. Nhưng Resource Server vẫn cần xác định token có được phép dùng cho **resource này**, có scope cần thiết và có quyền trên tài nguyên cụ thể hay không. Không mặc định `active=true` có nghĩa “cho gọi mọi endpoint”.

### 4.3. Response khi token không active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

Đây là response introspection **thành công ở mức HTTP**, nhưng nói token **không được chấp nhận**. Phải phân biệt:

| Tình huống | Kết luận |
|---|---|
| Introspection trả HTTP 200 và `active=true` | Token active theo AS; tiếp tục áp chính sách resource/scope |
| Introspection trả HTTP 200 và `active=false` | **Không tạo authentication thành công** |
| Introspection trả HTTP 401/403 cho caller introspection | Resource Server có thể sai client credentials/permission; không phải tự động kết luận token user sai |
| Introspection timeout, TLS lỗi hoặc AS 5xx | **Không thể xác minh an toàn**; không tự cho token qua |
| Response thiếu trường `active` hoặc sai định dạng | Xử lý là response không hợp lệ theo giao thức/hợp đồng |
| `active=true` nhưng thiếu audience bắt buộc | Không đủ bằng chứng cấp quyền cho API nếu contract yêu cầu audience |

Đừng chuyển mọi lỗi mạng thành “user cố ý gửi token sai” trong telemetry nội bộ. Tuy vậy, dù phân loại khác nhau cho vận hành, **không chấp nhận request nếu không có kết quả xác thực đáng tin**.

### 4.4. Introspection khác UserInfo, token endpoint và revocation

| Endpoint/giao thức | Mục đích |
|---|---|
| **Token endpoint** | Cấp access token/refresh token theo OAuth grant |
| **Token introspection** | Hỏi trạng thái và metadata của một token |
| **Token revocation** | Yêu cầu thu hồi token trong phạm vi hỗ trợ của AS |
| **OIDC UserInfo** | Cung cấp thông tin claims người dùng cho OIDC client được phép |
| **JWKS endpoint** | Công bố public keys để verifier xác minh chữ ký/token |

Không gọi UserInfo để thay token introspection; một UserInfo response không phải bằng chứng tổng quát rằng access token phù hợp audience, scope và profile của Resource Server. Cũng không coi JWKS là danh sách các token “đang active”: JWKS chỉ cung cấp public keys.

## 5. Spring Security đặt tên cấu hình theo chiến lược xác thực

Spring Security OAuth 2.0 Resource Server phổ biến có hai nhánh cấu hình:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
~~~

và:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()));
~~~

Hai lời gọi này không phải phép thử “token có giống JWT không?”:

- **`jwt()`**: sử dụng `JwtDecoder` để xác minh JWT bằng nguồn khóa/JOSE/validators phù hợp.
- **`opaqueToken()`**: sử dụng `OpaqueTokenIntrospector` để xác nhận token qua introspection strategy và tạo principal/authorities. Token **có thể là JWT** nếu endpoint introspection chấp nhận nó.

Một vài tên type liên quan:

| Vấn đề | Nhánh JWT | Nhánh opaque/introspection |
|---|---|---|
| Servlet provider | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Điểm mở rộng xác thực | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Principal thường gặp | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Authentication kết quả | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Nguồn dữ liệu | JWT claims đã xác minh | Introspection attributes đã được tin cậy |
| Thời hạn/issuer/audience | Validators ở decoder | Chính sách AS/introspector và bổ sung theo contract |
| Authorities từ scope | Thường `SCOPE_*` | Thường `SCOPE_*` nếu introspection cung cấp scope |

Những tên này mô tả pipeline thông dụng trong Servlet Spring Security hiện đại; chi tiết mapping claims/authorities có thể phụ thuộc phiên bản và custom converter/introspector.

### 5.1. Dependencies chung

Ví dụ ứng dụng Servlet/Spring MVC:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Với nhánh JWT sử dụng JOSE, cần các thư viện hỗ trợ JWT/JWS; starter Resource Server của Spring Boot hiện đại thông thường đem vào những dependency phù hợp. Nếu tự quản dependency hoặc phiên bản cũ, phải kiểm tra module `spring-security-oauth2-jose` và các dependency liên quan theo phiên bản đang chạy.

## 6. Trường hợp A: JWT access token, xác minh cục bộ bằng `JwtDecoder`

Đây là lựa chọn phù hợp khi issuer phát hành JWT ký theo profile đã biết và Resource Server có thể tin một JWK Set/public key phù hợp.

### 6.1. Khai báo issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Spring Boot/Spring Security có thể tạo decoder dựa trên issuer khi ứng dụng không tự cung cấp bean decoder khác. Decoder xác minh JWS và thực hiện các claim validations mặc định theo phiên bản. Với API riêng, thường cần thêm **audience validation** cho resource ID như `orders-api`; không giả định chỉ khai báo issuer tự động chứng minh token dành cho đúng API.

### 6.2. `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OrdersJwtSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Một token hợp lệ có `scope=orders.read` thường được Spring Security chuyển thành `SCOPE_orders.read`. Phân quyền trên từng đơn hàng (owner/tenant) vẫn thuộc service/domain. Ví dụ trên chỉ minh họa HTTP authentication/authorization, không cung cấp đầy đủ controller, audience validator hoặc policy CSRF/CORS của một sản phẩm cụ thể.

### 6.3. Nếu đã biết chính xác JWKS URL

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
          jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
~~~

Khi framework/phiên bản hỗ trợ cấu hình này, Resource Server có thể dùng JWKS URL đã biết thay vì phải khám phá URL qua metadata lúc khởi động, trong khi vẫn giữ issuer validation theo cấu hình issuer. Tuy nhiên, nó **vẫn có thể cần mạng** khi lấy/refresh keys.

Không nhầm:

~~~text
Local JWT verification ≠ no network ever
Local JWT verification ≠ immediate revocation knowledge
Local JWT verification ≠ automatic audience authorization
~~~

### 6.4. Tự tạo decoder và giữ validator cần thiết

Một ví dụ cần chọn JWS algorithm và audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class LocalJwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                expectedAudience
            )
        );
        return decoder;
    }
}
~~~

Ví dụ dùng property ứng dụng `app.security.*` (phải khai báo riêng), không phải magic properties của Spring Boot. `setJwtValidator(...)` **thay bộ validator** trên decoder, nên chủ động ghép `JwtValidators.createDefaultWithIssuer(...)` để không bỏ mất kiểm tra mặc định về issuer và thời gian. Những ràng buộc profile bắt buộc khác (như token type hoặc yêu cầu `exp` tồn tại) phải được bổ sung khi hợp đồng cần.

Đây là ví dụ **xác minh JWT tại Resource Server**. Không có introspection cho mỗi request sau khi decoder có thông tin khóa đủ tin cậy.

## 7. Trường hợp B: JWT access token nhưng xác minh qua introspection

Hình dạng token **không buộc** Spring Security phải dùng `jwt()`. Nếu AS hỗ trợ introspection cho JWT, có thể cấu hình nhánh opaque-token/introspection.

### 7.1. Cấu hình introspection endpoint

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Các giá trị từ biến môi trường trong ví dụ minh họa cách **không hard-code client secret** trong mã nguồn. Trong production, nên dùng secret manager và chính sách rotation/permission phù hợp. URL phải là endpoint introspection do AS công bố và có kênh TLS tin cậy; không được lấy URI từ token chưa xác minh.

### 7.2. HTTP security gọi `opaqueToken()`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersIntrospectionSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

**Nếu client gửi một JWT thay vì opaque random string**, Resource Server vẫn đưa **nguyên giá trị chuỗi** tới introspection strategy. Nó không tự chọn `JwtDecoder` chỉ vì thấy ba phần Base64URL. Authentication thành công hay không phụ thuộc vào **AS introspection thực sự công nhận JWT**, client credentials, `active` và những chính sách áp thêm.

Không dùng đồng thời hai class `OrdersJwtSecurity` ở mục 6 và `OrdersIntrospectionSecurity` cùng với matcher không giới hạn trong một ứng dụng mà chưa thiết kế thứ tự/security chains; chúng là **hai phương án cấu hình thay thế** cho cùng API.

### 7.3. Principal khi dùng introspection

Trong đường introspection, principal thường là một `OAuth2AuthenticatedPrincipal` chứa attributes từ kết quả introspection; `BearerTokenAuthentication` giữ principal/authorities.

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IntrospectedIdentityController {

    @GetMapping("/api/me")
    MeResponse me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        // Chỉ dùng attributes mà contract cho phép và đã được kiểm tra.
        return new MeResponse(principal.getName());
    }
}

record MeResponse(String displayName) {}
~~~

Đây là mã minh họa endpoint được bảo vệ, không phải khuyến nghị công khai nguyên `principal.getName()` trong mọi API: tên có thể là `sub` hoặc thông tin nhạy cảm, phải có chính sách response cụ thể. **Không trả `principal.getAttributes()` hoặc `BearerTokenAuthentication` trực tiếp** vì introspection có thể mang dữ liệu nhạy cảm và token/credentials.

### 7.4. Điểm được và mất khi JWT cũng introspect

| Đặc điểm | JWT local | JWT qua introspection |
|---|---|---|
| Xác minh chữ ký ở đâu? | Resource Server/decoder | Thường do AS hoặc dịch vụ introspection đáng tin chịu trách nhiệm |
| Call AS ở mỗi request? | Không nhất thiết sau khi có JWK | Thông thường có, trừ khi thiết kế cache |
| Thu hồi trước `exp` | Cần dữ liệu thu hồi bổ sung | AS có thể phản ánh `active=false` nếu đã nhận revocation |
| JWT claims trực tiếp | Resource Server đọc sau khi xác minh | Resource Server nhận metadata introspection; không mặc định đủ mọi claim |
| Phụ thuộc mạng runtime | Thấp hơn cho việc xác minh khi keys đã cache | Cao hơn nếu không cache introspection |
| Quản lý JWK rotation tại từng API | Cần xử lý qua decoder/JWKS | Có thể tập trung tại AS/introspection service |
| Scope/role mapping | JWT claims → authorities | Introspection attributes → authorities |
| Bảo mật đường outbound | JWKS endpoint, trust/TLS | Introspection request có token + client auth, phải bảo vệ kỹ |

**Cảnh báo:** Dùng introspection **không tự đảm bảo thu hồi tức thời tuyệt đối**. Một AS có thể có độ trễ đồng bộ trạng thái; nếu Resource Server cache response `active=true`, nó có thể tiếp tục chấp nhận token trong cửa sổ cache dù AS đã thu hồi.

## 8. Trường hợp C: opaque random token, xác minh qua introspection

Đây là mô hình tương ứng trực tiếp với các ví dụ opaque-token Resource Server thông dụng.

### 8.1. Tổng quan

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Orders Resource Server
    participant A as Authorization Server
    C->>R: GET /api/orders/42 + Bearer opaque handle
    R->>A: POST /introspect (token, client authentication)
    A->>A: Tìm token, active/expired/revoked, policy
    A-->>R: active=true, scope=orders.read, sub, aud...
    R->>R: Kiểm tra metadata bắt buộc + tạo authorities
    R-->>C: Response nghiệp vụ nếu đủ quyền
~~~

Resource Server không cần hiểu cấu trúc nội bộ của token, nhưng cần tin tưởng **Authorization Server đã xác thực việc phát hành và trạng thái token**. Khi nhận `active=false`, request phải bị từ chối xác thực.

### 8.2. Phân quyền scope sau introspection

Nếu introspection response cho:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-123",
  "aud": "orders-api",
  "exp": 1924992000
}
~~~

Spring Security opaque-token support thường ánh xạ `scope` thành authorities dạng:

~~~text
SCOPE_orders.read
~~~

Khi đó `hasAuthority("SCOPE_orders.read")` có thể áp trên endpoint đọc. Nhưng **`active=true` chỉ thể hiện tính hợp lệ**, còn quyền đọc một đơn hàng cụ thể phải được kiểm tra thêm theo user/tenant/domain.

### 8.3. Introspection server không nhất thiết trả issuer/audience

RFC 7662 có metadata chuẩn, nhưng không bắt buộc response phải chứa mọi field trong mọi trường hợp. Nếu Orders API cần `aud=orders-api`, hãy:

1. Thống nhất với AS rằng introspection response dành cho caller sẽ bao gồm audience đủ tin cậy, **hoặc** AS thực thi ràng buộc resource cụ thể khi đánh giá `active`.
2. Cấu hình introspector/authorization bổ sung kiểm tra audience theo response contract.
3. **Từ chối khi không đủ bằng chứng** token dành cho Orders API.

Đừng dùng cách “introspection trả active nên bỏ luôn audience check” nếu Authorization Server chỉ kiểm tra token còn sống mà không giới hạn resource được phép nhận.

### 8.4. Client authentication không phải access token của người dùng

Trong remote introspection có hai credential độc lập:

~~~text
Bearer access token từ client → Resource Server

Resource Server credentials → Authorization Server introspection
~~~

Chúng có chủ sở hữu, quyền và vòng đời khác nhau. Không chuyển nguyên introspection client secret về client API và không log request introspection chứa cả Basic credentials lẫn token được kiểm tra.

## 9. Trường hợp D: opaque token, xác minh cục bộ bằng kho trạng thái

Ví dụ kiến trúc cho nền tảng **có quyền quản lý token issuance** hoặc được tin cậy sử dụng token store nội bộ:

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"Sinh random handle + ghi record"| DB["Trusted token store"]
    AS -->|"Trả token cho client"| C["Client"]
    C -->|"Bearer opaque token"| R["Resource Server"]
    R -->|"Lookup digest(handle)"| DB
    DB -->|"issuer, aud, sub, scopes, exp, revoked"| R
    R --> V["Validation và authorization cục bộ"]
~~~

**Không có network request đến AS introspection endpoint trong mỗi lần gọi** nếu Resource Server có dữ liệu tra cứu tin cậy ngay tại chỗ. Nhưng vẫn có một phụ thuộc dữ liệu: local database, in-memory store, shared cache hoặc một bản sao trạng thái.

### 9.1. Cấu trúc một token record

Một record nội bộ có thể mang:

~~~text
tokenDigest        = digest của random opaque handle (không lưu raw token)
subject            = user-123
issuer             = https://login.example.test/realms/company
audience           = orders-api
clientId           = shop-web
scopes             = [orders.read]
issuedAt           = ...
expiresAt          = ...
revoked            = false
~~~

**Không coi đây là định dạng token gửi cho client**. Client chỉ giữ random handle; record và claims nằm trong kho tin cậy của server.

### 9.2. Điều kiện cục bộ để token active

~~~text
1. Token handle phải là giá trị đủ entropy, không đoán được.
2. Digest/lookup phải tìm được record từ kho tin cậy.
3. Record không bị đánh dấu revoked hoặc disabled.
4. expiresAt phải sau thời gian hiện tại theo clock policy.
5. Token phải có issuer/client/audience đúng hợp đồng.
6. Scope/permissions được map thành authorities một cách kiểm soát.
7. Request vẫn phải qua HTTP/method/domain authorization.
~~~

Với kho trạng thái sao chép, phải biết **độ trễ đồng bộ revocation**. Một bản ghi đã bị thu hồi ở hệ thống phát hành nhưng chưa tới cache địa phương có thể còn được chấp nhận; local lookup không tự giải quyết freshness.

### 9.3. Khi nào không nên tự làm local opaque validation?

- Authorization Server là nhà cung cấp bên ngoài không cho Resource Server truy cập token issuance/state.
- Không có schema hoặc contract được duy trì cho token record.
- Không thể bảo đảm token entropy, ký/mã hóa, expiry hoặc revocation consistency.
- Nhiều API dùng chung token nhưng không có cách đồng bộ trạng thái an toàn.
- Cần kiểm tra chính sách phiên/tenant động mà chỉ AS biết.
- Việc tạo local validation sẽ khiến API tin những token mà AS không còn chấp nhận.

Trong các tình huống này, **remote introspection** hoặc một dịch vụ kiểm tra token đáng tin thường là mô hình dễ quản trị hơn. **Không cố giải mã opaque string** bằng cách đoán hoặc tin các trường tự khai báo trong request.

### 9.4. Điểm mở rộng `OpaqueTokenIntrospector` cho local store

Spring Security cho phép ứng dụng cung cấp một `OpaqueTokenIntrospector` riêng. Nó nhận token string và phải trả `OAuth2AuthenticatedPrincipal` **chỉ khi token đã được xác minh phù hợp**.

Một ví dụ cấu trúc của ứng dụng có token store nội bộ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class LocalOpaqueTokenConfiguration {

    @Bean
    OpaqueTokenIntrospector localOpaqueTokenIntrospector(
            TrustedTokenRepository repository,
            TokenFingerprint fingerprint,
            Clock clock) {

        return token -> {
            if (token == null || token.isBlank()) {
                throw new OAuth2IntrospectionException("Invalid token");
            }

            // Tính digest/fingerprint an toàn; KHÔNG log raw token.
            String digest = fingerprint.of(token);
            StoredToken record = repository.findByDigest(digest)
                .orElseThrow(() ->
                    new OAuth2IntrospectionException("Token not active"));

            if (record.revoked()
                    || !record.expiresAt().isAfter(clock.instant())
                    || !"orders-api".equals(record.audience())
                    || !"https://login.example.test/realms/company"
                        .equals(record.issuer())) {
                throw new OAuth2IntrospectionException("Token not active");
            }

            List<GrantedAuthority> authorities = new ArrayList<>();
            for (String scope : record.scopes()) {
                authorities.add(
                    new SimpleGrantedAuthority("SCOPE_" + scope));
            }

            Map<String, Object> attributes = new HashMap<>();
            attributes.put("sub", record.subject());
            attributes.put("iss", record.issuer());
            attributes.put("aud", record.audience());
            attributes.put("client_id", record.clientId());
            attributes.put("scope", String.join(" ", record.scopes()));
            attributes.put("exp", record.expiresAt().getEpochSecond());

            return new DefaultOAuth2AuthenticatedPrincipal(
                record.subject(),
                attributes,
                authorities
            );
        };
    }

    interface TrustedTokenRepository {
        Optional<StoredToken> findByDigest(String digest);
    }

    interface TokenFingerprint {
        String of(String token);
    }

    record StoredToken(
        String subject,
        String issuer,
        String audience,
        String clientId,
        Instant expiresAt,
        boolean revoked,
        Set<String> scopes
    ) {}
}
~~~

**Giới hạn và điều kiện của ví dụ:**

- `TrustedTokenRepository` và `TokenFingerprint` chỉ là interfaces minh họa; muốn chạy ứng dụng phải có implementation, nguồn dữ liệu tin cậy, quản lý secret, cách phát hành/revoke và cơ chế đồng bộ phù hợp.
- Store giả định có **token handle ngẫu nhiên, entropy cao** và lưu fingerprint/digest thay vì raw token. Chọn SHA-256/HMAC hoặc cơ chế khác phụ thuộc threat model và chính sách lưu token; không dùng hash yếu hoặc token có thể đoán.
- `Clock` phải được cung cấp bởi ứng dụng/test infrastructure; dùng clock nhất quán và thiết kế giới hạn skew theo hợp đồng.
- Exception khi token invalid cần được ánh xạ đúng vào **lỗi Bearer authentication** ở phiên bản Spring Security đang triển khai. Ví dụ dùng `OAuth2IntrospectionException` để minh họa việc **không trả principal cho token invalid**, nhưng chính sách phân loại lỗi và exception type phải tương thích provider hiện tại.
- Nếu store có trạng thái `notBefore`, tenant, token type, disabled user, client binding hoặc chính sách khác, phải kiểm tra những điều kiện đó chứ không chỉ những field trong mẫu.
- Chỉ được dùng local store khi Resource Server **thực sự có thẩm quyền** tin dữ liệu đó. Đây không phải cách “thay introspection” cho token opaque của IdP bên thứ ba mà không có contract.
- Không đưa thông tin token gốc hoặc record nhạy cảm vào response hay logs.

### 9.5. SecurityFilterChain giữ cấu hình opaque-token

Nếu một bean `OpaqueTokenIntrospector` như trên được Spring Security sử dụng, HTTP DSL có thể vẫn là:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(withDefaults())
);
~~~

Trong ví dụ này, nhánh **opaque token** không nhất thiết gọi **introspection endpoint HTTP** vì `OpaqueTokenIntrospector` là implementation nội bộ do ứng dụng cung cấp. Đó chính là minh chứng rằng **tên nhánh DSL không đồng nghĩa xác minh từ xa**.

Khi ứng dụng vừa khai báo introspection properties của Spring Boot vừa cung cấp custom bean, phải kiểm soát chính xác decoder/introspector nào được chain sử dụng; không giả định các property tự động ghép chính sách vào custom implementation.

## 10. Một opaque token có thể được xác minh cục bộ bằng mật mã không?

Có, nếu **token format và hạ tầng bảo mật được thiết kế cho việc đó**. Ví dụ một token mà client chỉ xem là chuỗi không cần hiểu, nhưng bên phát hành bảo vệ nội dung bằng authenticated encryption. Resource Server có khóa và phần mềm theo đúng token profile có thể xác minh và lấy claims cục bộ.

Tuy nhiên, cần phân biệt:

1. **Opaque random handle**: không có cấu trúc đủ cho kiểm tra mật mã trong chuỗi; cần token store/lookup đáng tin.
2. **Encrypted/self-contained token**: nội dung có thể chứa claims đã được xác thực theo thuật toán, key, expiry và issuer policy; verifier có thể giải mã/kiểm tra khi được cấp đúng keys.
3. **Signed but non-JWT proprietary token**: có thể xác minh cục bộ nếu contract và chữ ký/MAC an toàn được triển khai đúng.

### 10.1. Đừng tự thiết kế “token bí mật” bằng Base64

Đoạn logic:

~~~text
token = Base64(userId + ":" + expiresAt + ":" + role)
~~~

không tạo một credential đáng tin: client có thể giải mã và tự sửa role/expiry nếu không có bảo vệ toàn vẹn mật mã. Nếu có yêu cầu self-contained token, nên dùng những chuẩn và thư viện bảo mật được duy trì, với key management, encryption/signature, token type và audience rõ ràng.

### 10.2. Confidentiality và authenticity là hai câu hỏi riêng

Một token mã hóa có thể **che nội dung khỏi người quan sát** nếu encryption được làm đúng, nhưng Resource Server vẫn phải kiểm tra token có được issuer đáng tin phát hành hay không, chưa hết hạn và dành cho API nào. Một token ký có thể **chứng minh integrity/authenticity** mà không hề che payload khỏi client.

Không đồng nhất:

~~~text
Readable token    ≠ untrusted token
Unreadable token  ≠ trusted token
Encrypted token   ≠ automatically active/revocation-aware
Signed token      ≠ automatically confidential
~~~

### 10.3. JWT dạng JWE không phải `NimbusJwtDecoder` JWS thông thường

JWT có thể được biểu diễn dưới dạng JWE mã hóa. Nếu client/Resource Server đang dùng token profile JWE, phải có thành phần giải mã và xác minh phù hợp. **Không mặc định các ví dụ `NimbusJwtDecoder.withJwkSetUri(...)` dùng để xác minh JWT ký JWS sẽ tự giải mã mọi JWE**.

Do đó, “opaque đối với client” và “JWT bên trong” cũng có thể cùng đúng, nhưng **cần hợp đồng kỹ thuật rõ ràng**, không chỉ nhìn số đoạn token để đoán.

## 11. Introspection có thể phân phối trạng thái thu hồi, nhưng không phải phép màu

Một ưu điểm được nhắc nhiều khi chọn introspection là khả năng phát hiện token bị thu hồi trước `exp`. Cần làm rõ sự khác biệt giữa **biết một token còn hạn** và **biết AS hiện còn chấp nhận token**.

### 11.1. Local JWT signature validation thường biết gì?

Nếu JWT tự chứa và Resource Server chỉ kiểm tra:

~~~text
JWS signature valid
AND trusted issuer
AND exp/nbf valid
AND audience valid
AND profile/claims valid
~~~

thì nó biết token đạt **các bằng chứng được biểu diễn trong JWT và cấu hình key**. Nó có thể **không biết** liệu AS vừa khóa user, thu hồi client, hủy session hoặc revoke token sau khi phát hành.

Nếu cần thu hồi nhanh, có các lựa chọn kiến trúc:

- JWT TTL ngắn để giới hạn cửa sổ.
- Local denylist/allowlist hoặc state lookup theo `jti`/issuer/subject được đồng bộ.
- Introspection hoặc policy service từ xa ngay tại request.
- Một cơ chế push/revocation event đáng tin để cập nhật trạng thái gần thời gian thực.

Các phương án trên có chi phí vận hành và consistency khác nhau. JWT format **không cấm** thêm revocation lookup cục bộ hoặc từ xa.

### 11.2. Remote introspection biết gì?

Một introspection endpoint có thể trả `active=false` khi:

- Token hết hạn hoặc chưa có hiệu lực.
- Token bị revoke.
- Authorization grant/client/session không còn được AS chấp nhận.
- Token không được phép introspect bởi Resource Server đang hỏi.
- Có chính sách khác của issuer khiến token không còn active.

Các lý do cụ thể phụ thuộc AS; **không nên đoán nguyên nhân** chỉ từ `active=false`. Nếu AS trả false, Resource Server phải từ chối token. Nếu cần lý do vận hành, dùng kênh audit/admin riêng của AS theo quyền phù hợp, không tự lộ nội bộ cho client.

### 11.3. Cache response introspection làm thay đổi độ tươi

Giả sử:

~~~text
10:00:00 AS trả active=true
10:00:01 Resource Server cache kết quả 60 giây
10:00:10 AS revoke token
10:00:20 Resource Server dùng cache active=true
10:01:01 cache hết hạn và kiểm tra lại
~~~

Nếu cache không có cơ chế invalidation, một token đã bị revoke có thể vẫn được chấp nhận trong cửa sổ 60 giây. Vì thế không thể nói “cứ dùng introspection là thu hồi tức thì” khi ứng dụng bật cache.

Một TTL thích hợp phải xét:

~~~text
cacheTTL <= thời gian chấp nhận stale revocation theo risk policy

cacheExpiresAt <= token.expiresAt (khi có và được tin cậy)
~~~

Những bất đẳng thức này mô tả **mục tiêu thiết kế**, không phải một thuộc tính tự động của mọi Spring Security version. Với token không có `exp` trong introspection response, không nên chọn cache “vô thời hạn” chỉ vì metadata thiếu.

### 11.4. Local opaque store cũng có consistency window

Một kho local replication có thể nhận revocation trễ:

~~~text
AS token store: revoked=true
Local RS cache: revoked=false
~~~

Đây là cùng một bài toán **freshness**; khác nhau ở cách dữ liệu được phân phối. Quyết định không nằm ở JWT/opaque mà ở **mô hình đồng bộ trạng thái**.

### 11.5. Sự cố signing key và revocation

Nếu private key JWT bị lộ, việc tiếp tục tin public key cũ có thể khiến attacker tạo token giả có chữ ký hợp lệ. Remote introspection có khả năng dựa trên database/issuance registry để từ chối token không được phát hành, **nếu** AS kiểm tra điều đó và thiết kế phù hợp. Không được giả định introspection mặc nhiên kiểm tra issuance registry cho tất cả JWT; một số AS có thể chỉ xác minh chữ ký và claims.

Ngược lại, opaque random token store nội bộ không phụ thuộc JWKS rotation theo cách JWT JWS, nhưng phụ thuộc bảo vệ handle/token database và quyền cập nhật trạng thái. Mỗi kiến trúc có trust boundary riêng.

## 12. Độ trễ, tính sẵn sàng và khả năng mở rộng

Lựa chọn local hay remote ảnh hưởng trực tiếp đến hành vi hệ thống khi Authorization Server hoặc network gặp sự cố.

| Thuộc tính | Local JWT/JWS | Remote introspection | Local opaque store |
|---|---|---|---|
| Xác minh mỗi request | Crypto + validators tại RS | HTTP request/response hoặc cache | Lookup state/digest tại RS/store |
| Phụ thuộc AS mỗi request | Thường không sau khi có key | Thường có nếu không cache | Không trực tiếp nếu store được replicate |
| Vấn đề latency | Chi phí signature verification, JWK refresh | Network, AS processing, TLS, retries | Local DB/cache/read latency |
| Mở rộng ngang | Dễ nếu đủ keys/policy | AS phải đáp ứng tổng request volume | Store/replication cần mở rộng |
| Thu hồi sớm | Cần state bổ sung | Có thể có qua `active` | Có thể có nếu store cập nhật kịp |
| Xử lý outage AS | Có thể tiếp tục xác minh với keys còn tin cậy | Có thể không xác thực được token mới/yêu cầu introspect | Tùy trạng thái store/replication |
| Bảo vệ secret | Public JWKS/issuer trust; signing keys ở AS | Client credentials + token trên outbound channel | Token store và secret/hash policy |
| Sai lệch cache | Stale JWKS/revocation | Stale `active` response | Stale token state |

### 12.1. Fail closed khi không đủ bằng chứng

Nếu introspection endpoint không truy cập được và Resource Server **không có kết quả xác minh đủ tin cậy**, nó không được tự chấp nhận token để tránh downtime. Tương tự, local opaque store bị mất kết nối hoặc JWT decoder không có trusted verification key cũng không được sinh principal “tạm”.

Không phải mọi lỗi hạ tầng bắt buộc trả HTTP 401 như token invalid. Hệ thống có thể phân biệt lỗi xác thực không hợp lệ và lỗi dịch vụ tạm thời trong response/telemetry theo kiến trúc, nhưng **tuyệt đối không cho request chưa được xác minh đi tiếp vào nghiệp vụ đã bảo vệ**.

### 12.2. Đừng retry introspection vô hạn

Nếu AS chậm hoặc outage, retry không giới hạn có thể làm tăng tải, làm cạn thread/connection pool và tạo lỗi dây chuyền. Cần chính sách timeout, giới hạn retry, circuit breaker/bulkhead nếu phù hợp, quan sát `active=false` tách khỏi HTTP 5xx và có kế hoạch capacity.

### 12.3. Cache phải gắn với bảo mật, không chỉ hiệu năng

Khi cache introspection hoặc local token store:

- Không log raw token hoặc dùng raw token làm metric label.
- Nếu dùng token làm cache key, bảo vệ cache khỏi lộ credential; cân nhắc fingerprint có thiết kế phù hợp và entropy token cao.
- Phân biệt cache theo issuer/client/audience khi hợp đồng cần; một chuỗi token có thể không đủ để suy ra mọi ngữ cảnh nếu nhiều tenant/AS.
- Không cache kết quả `active=true` vượt hạn token.
- Đặt TTL theo revocation freshness/SLA/risk policy, không theo con số tùy ý.
- Xác định cách invalidation khi token, client hoặc session bị thu hồi.
- Không biến outage thành chính sách “cache active mãi mãi”.

## 13. Audience, issuer và scope phải có nghĩa ở cả bốn mô hình

Dù token dạng nào, Resource Server vẫn cần biết **ai cấp token, token dành cho ai và nó cho phép làm gì**.

### 13.1. JWT local

Thường kiểm tra:

~~~text
Trusted JWS key / allowed alg
AND iss = trusted issuer
AND aud contains orders-api
AND exp/nbf valid
AND required token profile claims
~~~

Sau đó `scope`/`scp` được map thành authorities, và endpoint rule quyết định request nào cần authority nào.

### 13.2. JWT hoặc opaque qua introspection

Resource Server nhận **AS assertion** qua HTTPS về `active` và metadata. Nếu AS trả:

~~~json
{
  "active": true,
  "aud": "billing-api",
  "scope": "orders.read",
  "sub": "user-123"
}
~~~

Orders API **không nên chấp nhận** token chỉ vì scope giống quyền đọc orders. Audience là `billing-api`; đó là token dành cho resource khác. Nếu AS không đưa audience ra introspection, Resource Server phải có một chính sách tin cậy khác xác nhận resource binding, hoặc từ chối vì thiếu bằng chứng theo hợp đồng.

### 13.3. Opaque local store

Record nội bộ phải gắn với issuer/client/audience/scope rõ ràng. Một handle tồn tại trong DB không có nghĩa mọi API dùng chung DB đều được phép tin token. Trong hệ thống microservices, cần phân quyền truy cập kho token và phân biệt resource audience.

### 13.4. Role và scope là tầng khác

Spring Security thường dùng authority:

~~~text
scope: "orders.read" → SCOPE_orders.read
role: "ADMIN"       → ROLE_ADMIN (nếu đã ánh xạ đúng)
~~~

`JwtAuthenticationConverter` hoặc custom introspector xác định cách tạo authorities. `authorizeHttpRequests`/`@PreAuthorize` dùng authorities để áp policy. **Dữ liệu role/scope chỉ đáng tin sau khi token được xác thực**, không phải vì claim có mặt trong chuỗi.

## 14. Spring Security không tự chọn phương án xác minh theo hình dạng token

Một lỗi kiến trúc dễ xuất hiện khi ứng dụng muốn “nhận cả JWT lẫn opaque”:

~~~java
// PHẢN VÍ DỤ: không dùng hình dạng token chưa tin cậy làm trust policy.
if (token.split("\\.").length == 3) {
    return validateLikeJwt(token);
}
return introspectOpaque(token);
~~~

Vấn đề:

1. Chuỗi token là **dữ liệu do client cung cấp**; định dạng có thể bị làm giả hoặc chứa dấu chấm tùy ý.
2. JWT có thể được mã hóa/định dạng khác, không phải mọi JWT đều đúng ba phần JWS compact.
3. Một AS có thể phát hành opaque token chứa dấu chấm, hoặc JWT token mà Resource Server phải introspect.
4. Fallback từ validation thất bại sang một phương án dễ hơn có thể tạo **downgrade/bypass**.
5. Hai provider có thể có issuer, audience, key và scopes khác nhau; tự chuyển theo shape dễ khiến chính sách không nhất quán.

### 14.1. Nếu cần hỗ trợ nhiều loại access token

Nên xác định **một hợp đồng explicit**:

- Cổng/endpoint hoặc security chain nào dùng loại token nào?
- Mỗi loại token được phát hành bởi issuer nào và dành cho audience nào?
- Mỗi Resource Server biết nguồn trust/validation nào?
- Nếu có resolver, bằng chứng nào được phép dùng để định tuyến trước khi token được xác minh?
- Có bảo đảm không **chuyển sang cơ chế yếu hơn** khi validation của cơ chế dự kiến thất bại?
- Token profile/alg/issuer/client khác nhau được hạn chế thế nào?

Trong Spring Security, có thể cấu hình nhiều `SecurityFilterChain` với `securityMatcher`, `@Order` và từng chiến lược `jwt()`/`opaqueToken()` theo phạm vi HTTP. Nếu cùng endpoint phải chấp nhận nhiều kiểu token, có thể cần `AuthenticationManagerResolver<HttpServletRequest>` hoặc chiến lược provider/decoder tùy chỉnh, nhưng **định tuyến và xác minh phải do thiết kế tin cậy quyết định**, không chỉ bởi regex trên token.

### 14.2. Hai chain là ví dụ chính sách theo endpoint, không theo token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class TwoApiValidationStrategies {

    @Bean
    @Order(1)
    SecurityFilterChain internalJwtApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/internal-api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_internal.read")
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain partnerIntrospectionApi(
            HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/partner-api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_partner.read")
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

Đây là **ví dụ cấu hình ý tưởng**: để chạy cần cung cấp đúng bean/properties `JwtDecoder` và `OpaqueTokenIntrospector`, authorization profiles và HTTP policies phù hợp. Hai chain đầu chọn strategy theo **URL scope**, không phải đoán hình dạng bearer token. Chain cuối đóng lại các URL không được bao phủ. Nếu có CORS, CSRF, session hoặc các authentication mechanisms khác, cần cấu hình theo sản phẩm.

Đặc biệt, `anyRequest().denyAll()` của một chain chỉ có hiệu lực **bên trong chain đã chọn**; fallback chain ở ví dụ tránh để route bên ngoài hai nhóm API không được bảo vệ bởi Spring Security.

## 15. Spring WebFlux: cùng nguyên tắc, khác interface

Với **Spring WebFlux**, Resource Server xử lý request theo reactive pipeline. Sự khác biệt về kiểu API không thay đổi luận điểm: JWT có thể được xác minh cục bộ hoặc qua introspection; opaque token có thể được kiểm tra qua một dịch vụ từ xa hoặc qua trạng thái/logic nội bộ được xây dựng an toàn.

### 15.1. Các interface tương ứng

| Trách nhiệm | Servlet / Spring MVC | Spring WebFlux |
|---|---|---|
| HTTP security | `HttpSecurity` | `ServerHttpSecurity` |
| Chain bảo mật | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Xác minh JWT cục bộ | `JwtDecoder` | `ReactiveJwtDecoder` |
| Nimbus JWT decoder | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Opaque/introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Kết quả introspection | `OAuth2AuthenticatedPrincipal` | `Mono<OAuth2AuthenticatedPrincipal>` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Quy tắc HTTP | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |

Dependency ví dụ:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 15.2. Reactive JWT verification

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveJwtApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Khi ứng dụng có `ReactiveJwtDecoder` từ cấu hình tin cậy, token sẽ được xác minh theo decoder đó trước khi áp authorities. Nếu token profile đòi audience hay claims riêng, phải cấu hình validator phù hợp; không tự suy ra token được phát hành cho API chỉ vì chữ ký đúng.

### 15.3. Reactive introspection: JWT hoặc opaque handle

Cũng có thể dùng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveIntrospectionApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

Với `ReactiveOpaqueTokenIntrospector` từ Spring Boot configuration hoặc custom bean, pipeline này xác minh token theo introspection strategy đã cấu hình, **không tự chuyển sang JWT decoder** vì token giống JWT. Hai class security config này là **hai phương án thay thế**, không phải hai bean toàn cục cùng matcher nên được sử dụng không phân biệt thứ tự.

### 15.4. Opaque local trên WebFlux

Một `ReactiveOpaqueTokenIntrospector` tùy chỉnh có thể tra cứu một reactive token store:

~~~text
Bearer token
   |
   v
ReactiveOpaqueTokenIntrospector.introspect(token)
   |
   v
Mono<TrustedTokenRecord> từ reactive repository/cache
   |
   v
validate active / exp / issuer / audience / scope
   |
   v
Mono<OAuth2AuthenticatedPrincipal>
~~~

Đây là **mẫu kiến trúc**, không phải một API tự động của Spring Security để truy cập mọi local token store. Ứng dụng phải tự cung cấp nguồn dữ liệu và code xác minh. Tránh gọi blocking JDBC hoặc HTTP client đồng bộ ngay trên Reactor event loop. Nếu bắt buộc dùng thư viện blocking, cần một cơ chế scheduling phù hợp, có giới hạn tải và được đánh giá đầy đủ; tốt hơn là dùng repository/client reactive khi kiến trúc cho phép.

### 15.5. Opaque không có nghĩa phải trả metadata trống

Kết quả của reactive hoặc Servlet introspector có thể chứa attributes về `sub`, `scope`, `client_id`, `aud`. Nhờ đó controller/service vẫn có principal và authorities để áp policy. Sự khác biệt với JWT local là **nguồn của dữ liệu đáng tin**: introspection response hoặc local record, không phải JWT claims đã được decoder xác minh.

## 16. Một tình huống di trú kiến trúc: JWT local → JWT introspection

Một hệ thống ban đầu dùng JWT local vì muốn phục vụ nhiều request:

~~~text
2026, giai đoạn 1:
  Authorization Server phát hành JWT RS256
  Resource Server dùng issuer-uri + JWKS
  Token TTL = 15 phút
  JWT local signature/claim validation
~~~

Sau đó tổ chức cần hủy quyền truy cập nhanh hơn trong những tình huống như khóa tài khoản hoặc revoke grant. Một lựa chọn là **vẫn giữ JWT access token** nhưng chuyển Resource Server sang introspection:

~~~text
Giai đoạn 2:
  Authorization Server vẫn phát hành JWT RS256
  Authorization Server hỗ trợ RFC 7662 cho JWT
  Resource Server dùng opaqueToken() + introspection-uri
  active=false phản ánh revocation theo policy của AS
~~~

Token **không nhất thiết phải đổi từ JWT sang random opaque string** mới có thể có introspection. Điều phải thay đổi là **cách Resource Server lấy bằng chứng về trạng thái token**.

### 16.1. Các việc phải kiểm soát khi chuyển

1. Xác nhận AS thực sự introspect JWT được cấp cho API, với đúng client auth và permissions.
2. Xác nhận introspection response có đủ `scope`, subject, audience, expiry, token type theo hợp đồng.
3. Đánh giá throughput/latency: trước đây Resource Server chỉ xác minh chữ ký local, bây giờ cần một HTTP call hoặc cache lookup.
4. Chọn timeout, retry và phản ứng khi AS mất kết nối; không tự chấp nhận token chưa xác minh.
5. Đặt cache TTL theo yêu cầu revocation freshness nếu dùng cache.
6. Bảo vệ client secret và access token trong request/response logs của HTTP client.
7. Kiểm tra authorities từ introspection có tương đương hoặc khác biệt có chủ đích so với JWT converter.
8. Không đánh đồng thời điểm `active=false` với mọi 401 ở client; nhiều lỗi có thể do network/client credentials.

### 16.2. Một thay đổi có thể làm khác principal

Trước khi chuyển:

~~~text
JWT path:
  Authentication = JwtAuthenticationToken
  principal = Jwt
~~~

Sau khi chuyển:

~~~text
Introspection path:
  Authentication = BearerTokenAuthentication
  principal = OAuth2AuthenticatedPrincipal
~~~

Một controller đang khai báo `@AuthenticationPrincipal Jwt jwt` có thể cần thay đổi cách truy cập attributes; không nên kỳ vọng introspection tự tạo lại đúng object `Jwt` chỉ vì raw token ban đầu là JWT.

Nếu API muốn cách truy cập identity ổn định qua nhiều chiến lược, có thể đưa một **lớp adapter identity nội bộ** nhận `Authentication` và tạo một domain principal riêng với các fields được phép. Không trả thẳng principal framework ra JSON.

## 17. Một tình huống di trú khác: opaque remote → opaque local

Giả sử một nền tảng phát hành random opaque access token và mọi microservice đều introspect qua Authorization Server:

~~~text
Giai đoạn 1:
    Resource Servers --HTTPS--> Central introspection endpoint
                                    |
                                    v
                                Token store
~~~

Vì throughput cao và các services nằm trong cùng một ranh giới tin cậy, tổ chức cân nhắc phân phối một token-state cache tin cậy đến từng cụm Resource Server:

~~~text
Giai đoạn 2:
    Authorization Server → token issuance/revocation events
                                  |
                                  v
                      Trusted replicated token state
                                  |
                                  v
                      Resource Servers local lookup
~~~

Opaque string vẫn **không đổi**. Resource Server không học cách decode JWT; nó **thay nguồn xác minh từ call HTTP sang một bản sao dữ liệu tin cậy**.

### 17.1. Điều kiện để thay thế an toàn

| Yêu cầu | Vì sao quan trọng |
|---|---|
| AS sở hữu và cung cấp nguồn dữ liệu chính thức | Ngăn API tự nhận token giả |
| Token handles đủ entropy | Ngăn brute-force/đoán token |
| State có expiry và revoke | Không chấp nhận token hết hạn/thu hồi |
| Phân phối sự kiện đáng tin, đúng thứ tự | Giảm cửa sổ stale state |
| Cơ chế reconnect/reconcile sau outage | Không chấp nhận cache cũ vô hạn |
| Phân biệt issuer/audience | Không chấp nhận token sai resource |
| Quyền truy cập/tenant bảo vệ store | Không để service không được phép đọc/sửa token state |
| Audit không chứa raw token | Bảo vệ credential trong hệ thống quan sát |

Nếu không thể đạt các điều kiện trên, local lookup có thể làm mất bảo đảm an toàn của AS. Trong trường hợp đó, cải thiện capacity/introspection caching có kiểm soát có thể là lựa chọn khác.

### 17.2. Nguy cơ khi copy token store thành “cache vĩnh viễn”

Một bản sao state tồn tại nhưng không nhận thông tin revoke mới sẽ trở thành **nguồn dữ liệu lỗi thời**. Khi AS xóa token, client hết quyền hoặc thay đổi client consent, Resource Server có thể vẫn nhìn thấy bản ghi cũ và cho phép truy cập.

Vì vậy, local state cần có:

- **TTL cứng** không vượt quá token expiry.
- **Staleness bound**: giới hạn độ trễ đồng bộ chấp nhận được.
- Cơ chế phát hiện consumer bị lag, mất event hoặc snapshot không còn đáng tin.
- Cách làm mới toàn bộ snapshot hoặc quay về introspection theo policy khi không đủ trạng thái.
- Quy tắc fail-closed khi dữ liệu đã quá tuổi tin cậy hoặc không chứng minh được nguồn phát hành.

Đây là chi phí của một phương án local-state validation, không liên quan đến việc token là chuỗi không có dấu chấm.

## 18. Quy tắc an toàn không phụ thuộc định dạng

Dưới đây là những yêu cầu nên áp dụng bất kể token dạng JWT hay opaque, xác minh local hay remote.

### 18.1. Bảo vệ bearer credential

Raw access token là credential. Không:

- Ghi token vào log, metrics, traces, exception messages hoặc URL query.
- Trả token ra JSON response của API nghiệp vụ.
- Đưa token vào message queue/event bus không được phép.
- Dùng token làm correlation ID.
- Lưu token trong browser/local environment thiếu bảo vệ.
- Sao chép token thật vào test fixture hoặc ticket.

Trong remote introspection, client credentials và `token` trong form body cũng phải được bảo vệ; không bật wire logging chứa header Basic hoặc body.

### 18.2. Giữ authentication khác authorization

~~~text
Authentication:
   token hợp lệ và đáng tin?
       |
       v
Authorities:
   token/principal có scope/roles gì?
       |
       v
HTTP authorization:
   endpoint cần authority nào?
       |
       v
Domain authorization:
   principal có quyền với record cụ thể không?
~~~

Một token hợp lệ không tự cấp quyền xem mọi order. Chỉ có `active=true` hoặc JWT signature đúng không đủ để bỏ qua owner/tenant policy.

### 18.3. Không để người gửi tự chọn nguồn trust

Tránh lấy `iss`, `jku`, `x5u`, introspection URI, JWKS URI hoặc hostname của verifier từ một request/token chưa xác minh mà không có allowlist. Nếu hỗ trợ nhiều issuer, phải có registry issuer được tin cậy và chọn đúng decoder/introspector.

### 18.4. Không tin phương pháp “đọc được token nên hợp lệ”

JWT Base64URL decode được payload không đồng nghĩa có quyền truy cập. Opaque token có độ dài đúng pattern cũng không đồng nghĩa đã được phát hành. Phải có kiểm tra cryptographic/state/AS assertion phù hợp.

### 18.5. Không tin kết quả introspection vượt phạm vi resource

Nếu response chỉ có `active=true` nhưng thiếu thông tin cần thiết để chứng minh audience/resource, cần ràng buộc policy bổ sung hoặc yêu cầu AS cung cấp bằng chứng theo hợp đồng. Không mở endpoint vì “Authorization Server đã nhận token”.

### 18.6. Không tự cho request qua lúc xác minh lỗi

Không có trusted key, store lỗi, introspection timeout hoặc response sai định dạng đều là trường hợp **không đủ cơ sở authentication**. Có thể phân loại các lỗi cho vận hành, nhưng không biến chúng thành principal đã xác thực.

### 18.7. Token type phải đúng mục đích

OIDC ID token có thể là JWT hợp lệ của cùng issuer nhưng dành cho OIDC client, **không tự động dùng làm access token**. JWT access token profile có thể yêu cầu `typ=at+jwt` và claims cụ thể theo RFC 9068; opaque access token có hợp đồng introspection riêng. Resource Server phải xác định đúng loại credential được phép nhận.

## 19. Quyết định nên dựa vào tiêu chí nào?

Một nhóm phát triển có thể dùng bảng dưới đây khi chọn cách xác minh.

| Câu hỏi thiết kế | Nếu câu trả lời nghiêng về... | Lựa chọn đáng cân nhắc |
|---|---|---|
| AS đã phát hành JWT ký và công bố JWKS tin cậy? | Có, API muốn giảm phụ thuộc mỗi request | JWT local verification |
| AS yêu cầu kiểm tra revocation/status động mỗi request? | Có, có introspection hỗ trợ | Remote introspection cho JWT hoặc opaque |
| AS chỉ cấp opaque random handles và không chia sẻ store? | Có | Remote introspection |
| API và AS cùng quản trị một token store được thiết kế an toàn? | Có, local lookup được cho phép | Local opaque validation bằng state |
| Token được mã hóa/tự chứa và verifier có key/profile chính thức? | Có | Local crypto validation với implementation thích hợp |
| Latency AS introspection quá lớn? | Có | Xem xét cache có TTL/risk bound, local JWT hoặc state replication |
| Thu hồi phải được phản ánh rất nhanh? | Có | Introspection không cache hoặc state synchronization có SLA phù hợp |
| Hạ tầng không thể vận hành local token state tin cậy? | Có | Ưu tiên mô hình AS/issuer sở hữu validation |
| Nhiều issuer và token profile? | Có | Thiết kế allowlist, routing và policy theo từng issuer |
| API chỉ muốn “hỗ trợ cả hai vì token khác định dạng”? | Chưa có contract | **Dừng lại để xác định trust model**, không sniff chuỗi token |

### 19.1. Bốn trường hợp tóm lại bằng một câu

**JWT + local:** Resource Server kiểm tra JWS, key và claims bằng `JwtDecoder`.

**JWT + remote:** Resource Server gửi JWT tới introspection endpoint được AS hỗ trợ và tin response.

**Opaque + remote:** Resource Server gửi token handle tới introspection để hỏi trạng thái và metadata.

**Opaque + local:** Resource Server có nguồn trạng thái/khóa và implementation chính thức để xác minh handle hoặc token opaque được thiết kế đặc biệt.

Không trường hợp nào miễn yêu cầu về issuer/audience, thời gian hiệu lực, scope, quyền trên tài nguyên và bảo vệ credential.

## 20. Kiểm thử đúng kiến trúc thay vì chỉ nhìn token string

Với Resource Server, kiểm thử nên được thiết kế theo **nguồn xác minh** thực tế. Một token giả “trông như JWT” chưa chứng minh được JWS validation; một opaque string được tạo ngẫu nhiên trong test chưa chứng minh introspection kết nối đúng AS.

### 20.1. Bảng tình huống cho bốn kiến trúc

| Hệ thống được test | Input | Bằng chứng được kiểm tra | Kỳ vọng |
|---|---|---|---|
| JWT local | JWT ký bởi key tin cậy, `iss/aud/exp` hợp lệ | `JwtDecoder` xác minh JWS/validators | Authentication thành công |
| JWT local | JWT bị sửa payload nhưng giữ chữ ký cũ | JWS signature | Bị từ chối |
| JWT local | JWT đúng chữ ký, `aud=billing-api` | Audience validator | Orders API từ chối |
| JWT local | JWT đã hết hạn | Timestamp validator | Bị từ chối |
| JWT remote | JWT hợp lệ được AS hỗ trợ introspect | RFC 7662 `active=true` và metadata | Authentication thành công nếu đủ policy |
| JWT remote | JWT có chữ ký đúng nhưng bị AS revoke | `active=false` theo AS | Bị từ chối |
| JWT remote | JWT không được AS introspect hỗ trợ | Response/token-state từ AS | Không chấp nhận chỉ vì JWT parse được |
| Opaque remote | Handle active, scope/audience phù hợp | Introspection response | Authentication thành công |
| Opaque remote | Handle không tồn tại hoặc revoked | `active=false` | Bị từ chối |
| Opaque remote | Endpoint timeout/5xx | Không có AS assertion đáng tin | Fail closed; phân loại lỗi vận hành |
| Opaque local | Handle có record active, chưa hết hạn, đúng audience | Trusted token store | Authentication thành công |
| Opaque local | Handle không có record | Local lookup | Bị từ chối |
| Opaque local | Record đã revoke | Local revocation state | Bị từ chối |
| Opaque local | Replica state quá cũ | Freshness policy | Fail closed hoặc dùng phương án fallback đã phê duyệt |
| Mọi phương án | Principal xác thực nhưng thiếu `SCOPE_orders.read` | HTTP authorization | Thường 403 |
| Mọi phương án | Principal đủ scope nhưng xem order sai owner | Domain authorization | Bị từ chối theo policy |

### 20.2. Spring Security Test `jwt()` chỉ mock kết quả xác thực

Với Spring MVC/Servlet:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ test rule HTTP, giả định endpoint `GET /api/orders/42` tồn tại và trả HTTP 200 cho principal có quyền:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JwtHttpAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readScopeCanReachReadEndpoint() throws Exception {
        mockMvc.perform(
                get("/api/orders/42")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    ))
            )
            .andExpect(status().isOk());
    }
}
~~~

Test này **không có nghĩa Spring Security đã xác minh JWS**, vì `jwt()` tạo authentication mô phỏng. Nó kiểm tra rule `hasAuthority("SCOPE_orders.read")` và cách endpoint xử lý principal, không chứng minh JWT decoder có kiểm tra issuer/audience/time.

Để test **JWT local verification thực**, cần JWT thử nghiệm **được ký bằng private key thử nghiệm**, decoder tin đúng public JWK thử nghiệm, rồi thử token đúng/sai signature, issuer, audience và expiry.

### 20.3. Test `opaqueToken()` cũng có giới hạn tương tự

Spring Security Test có hỗ trợ giả lập principal/attributes cho opaque token. Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

mockMvc.perform(
        get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
    )
    .andExpect(status().isOk());
~~~

Đoạn này thuộc ngữ cảnh test Spring Security với `MockMvc` đã thiết lập. Nó minh họa cách kiểm tra **HTTP authorization sau authentication**, không chứng minh introspection endpoint đã nhận token hoặc xử lý `active`. Cần bổ sung integration test thật bằng **test-only token** và một introspection service stub/fixture phù hợp.

### 20.4. Test remote introspection độc lập với token format

Một môi trường test có thể dựng một introspection endpoint mô phỏng:

~~~text
POST /introspect token=synthetic-jwt-looking-string
    → {active:true, aud:"orders-api", scope:"orders.read"}

POST /introspect token=synthetic-opaque-handle
    → {active:true, aud:"orders-api", scope:"orders.read"}

POST /introspect token=revoked-test-token
    → {active:false}
~~~

Với cả JWT-looking token và opaque handle, **cùng một nhánh `opaqueToken()`** có thể hỏi introspection endpoint. Cần kiểm tra:

1. Request gửi đúng URI qua HTTPS trong môi trường phù hợp.
2. Client authentication đúng (không log secret).
3. `active=true` tạo principal/authorities đúng mapping.
4. `active=false` không tạo authentication thành công.
5. Missing `aud`/wrong `aud` bị xử lý đúng hợp đồng.
6. Timeout/5xx không làm hệ thống tự cấp quyền.
7. Cache TTL/revocation được xử lý theo freshness policy.

Khi triển khai thực tế, test stub chỉ mô phỏng được hợp đồng. Còn một kiểm tra tích hợp với Authorization Server thật hoặc staging issuer được phép sẽ xác nhận **AS có hỗ trợ introspection JWT** và trả metadata đúng như kỳ vọng.

### 20.5. Test local opaque validation

Với local token store giả lập:

~~~text
Repository:
  digest(handleA) → active, expiresAt future, audience orders-api
  digest(handleB) → revoked
  digest(handleC) → expired
  digest(handleD) → audience billing-api

Expected:
  handleA → authenticated
  handleB → rejected
  handleC → rejected
  handleD → rejected
  unknown → rejected
~~~

Ngoài logic lookup, phải kiểm tra lỗi store, cache stale, concurrent revoke, clock skew và khả năng thiếu dữ liệu. **Không đặt raw access token production vào test fixture**, không lưu token trong source code hoặc CI logs.

## 21. Chẩn đoán lỗi thường gặp khi hiểu sai định dạng token

| Hiện tượng | Nhầm lẫn có thể có | Hướng phân tích |
|---|---|---|
| JWT nhìn hợp lệ nhưng API trả 401 | Tưởng JWT parse được là đủ | Kiểm tra chữ ký, issuer, audience, expiry, JWK/allowed algorithm hoặc response introspection tùy strategy |
| JWT gọi qua `opaqueToken()` bị 401 | Tưởng Spring tự decode JWT thay vì introspect | Xác nhận AS có hỗ trợ JWT introspection và caller có quyền |
| Opaque token gọi qua `jwt()` bị lỗi parse | Chọn JWT decoder cho handle không phải JWT | Dùng đúng opaque/introspection hoặc custom local token scheme |
| Opaque local nhận token không tồn tại | Tưởng handle có định dạng đúng là đủ | Yêu cầu record đáng tin và active state |
| `active=true` nhưng Orders API không có audience | Tưởng active nghĩa là cho mọi resource | Kiểm tra audience/resource binding của AS/introspection contract |
| Introspection trả HTTP 200 với `active=false` | Tưởng HTTP 200 nghĩa token hợp lệ | Đọc `active`, không tạo principal |
| AS token bị revoke nhưng Resource Server vẫn cho qua | Tưởng mọi remote introspection là tức thì | Kiểm tra cache TTL, replica lag, AS revocation semantics |
| JWT local vẫn dùng được sau khi logout | Tưởng local JWT tự biết session revoked | Cần TTL, denylist, state hoặc introspection theo contract |
| Introspection timeout làm nhiều API chậm | Phụ thuộc network/AS mỗi request | Timeout, capacity, cache freshness, resilience/fail closed |
| Cùng opaque token có lúc hợp lệ, lúc không | Local store replicas không nhất quán | Kiểm tra replication, lag, invalidation và freshness bounds |
| Authentication đúng nhưng 403 | Nhầm xác thực với phân quyền | Kiểm tra authorities, scope prefix, HTTP/method/domain rules |
| ID token JWT cùng issuer được API chấp nhận | Nhầm ID token với access token | Kiểm tra token type/profile/audience và mục đích sử dụng |
| Bearer token xuất hiện trong logs | Bật wire logging introspection/downstream | Redact header/body, bảo vệ client secret, xử lý credential leak |
| Nhiều token profile mà code chỉ xét dấu chấm | Chọn validation bằng shape chưa tin cậy | Thiết kế routing theo issuer/endpoint/contract; tránh downgrade |

### 21.1. 401, 403 và lỗi mạng là những tầng khác nhau

- **401 Unauthorized** thường xuất hiện khi Resource Server không xác thực được token: hết hạn, sai chữ ký, `active=false` hoặc credential không hợp lệ.
- **403 Forbidden** thường xuất hiện khi principal đã xác thực nhưng không có quyền thực hiện request: thiếu `SCOPE_orders.read`, không có role cần thiết hoặc bị business authorization từ chối.
- **Lỗi mạng/introspection/DB/JWK** có thể biểu hiện thành lỗi dịch vụ tùy exception handling, không nhất thiết có cùng mã 401 như token thực sự invalid.

Một số cơ chế exception handling còn có trường hợp anonymous bị từ chối tạo 401 dù rule authorization là `denyAll`. Vì thế nên phân biệt bằng nguồn lỗi và security configuration, không suy ra toàn bộ đường đi chỉ từ HTTP status.

### 21.2. Fail-closed và khả năng sử dụng

Một lỗi upstream không đồng nghĩa “khách hàng đáng lẽ phải bị 401”; nhưng cũng không cho phép bỏ xác minh để trả thành công. Khi AS hoặc token store outage, đội vận hành cần cách phân loại lỗi đủ tốt cho support/alerting, không làm yếu security policy.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Một JWT access token có nhất thiết được Resource Server xác minh cục bộ không?

**Không.** Nếu Authorization Server hỗ trợ introspection cho JWT và Resource Server được phép sử dụng, JWT có thể được xác minh/trạng thái được hỏi từ xa. Spring Security có thể dùng nhánh `opaqueToken()` để thực hiện introspection cho JWT đó.

**Câu 2.** Một opaque random token có thể xác minh cục bộ chỉ bằng cách kiểm tra chuỗi đủ dài không?

**Không.** Độ dài/pattern không chứng minh token được phát hành và đang active. Resource Server cần token store/lookup đáng tin hoặc một cơ chế bảo vệ mật mã được thiết kế cho token đó.

**Câu 3.** `opaqueToken()` trong Spring Security có luôn luôn nghĩa là “chuỗi token phải opaque, không được là JWT” không?

**Không.** Đây là tên chiến lược xử lý token qua `OpaqueTokenIntrospector`. Nếu introspector dùng remote RFC 7662, nó gửi token string đến AS; AS có thể hỗ trợ JWT hoặc opaque handles. Nếu ứng dụng cung cấp custom introspector dùng local state, nhánh đó cũng không nhất thiết gọi mạng.

**Câu 4.** JWT local có tự biết một token vừa bị revoke không?

**Không, nếu chỉ kiểm tra chữ ký/claims tự chứa.** Cần thêm state/revocation feed, denylist hoặc introspection theo chính sách. Token ngắn hạn chỉ giảm cửa sổ rủi ro, không tương đương tức thời.

**Câu 5.** Nếu introspection trả HTTP 200 với `active=false`, request có được xác thực không?

**Không.** HTTP 200 chỉ cho biết introspection HTTP call được xử lý; `active=false` nói token không được chấp nhận.

**Câu 6.** Introspection trả `active=true` nhưng không có audience. Có thể mặc định cho qua mọi API không?

**Không.** Nếu audience/resource binding là điều kiện bắt buộc của API, cần bằng chứng từ introspection/AS policy hoặc kiểm tra khác đáng tin cậy. Thiếu bằng chứng thì không được cấp quyền.

**Câu 7.** Tại sao token có cấu trúc mã hóa vẫn được gọi là opaque?

Vì “opaque” mô tả việc **bên sử dụng token không được kỳ vọng hiểu nội dung**. Issuer hoặc verifier có khóa/contract có thể xử lý nội dung; client vẫn chỉ nắm chuỗi để trình.

**Câu 8.** Tại sao không chọn strategy bằng `token.split("\\.").length`?

Vì đó là dữ liệu chưa tin cậy do client cung cấp, token profile có thể khác nhau, và fallback theo hình dạng có thể tạo cơ chế downgrade. Strategy phải được quyết định bởi policy/issuer/endpoint/contract.

**Câu 9.** Cache introspection 5 phút có giữ nguyên lời hứa revoke gần tức thì không?

**Không.** Nếu cache không được invalidate, response `active=true` có thể còn được dùng trong nhiều phút sau khi AS đã revoke. Chọn TTL/freshness theo risk policy và hạn token.

**Câu 10.** Khi một token được xác thực thành công, có được phép xem mọi order không?

**Không.** Cần kiểm tra scopes/authorities ở HTTP/method layer và owner/tenant/domain authorization cho từng bản ghi.

## 23. Kết luận: nguồn tin cậy mới là quyết định cốt lõi

Hãy nhớ bốn tổ hợp:

~~~text
               XÁC MINH CỤC BỘ             XÁC MINH TỪ XA

JWT            JWS/JOSE + trusted keys       Introspection JWT nếu AS hỗ trợ
               + claim validators            + AS active/metadata

Opaque         Trusted local token store     Introspection handle
               hoặc crypto-aware verifier    + AS active/metadata
~~~

Một thiết kế Resource Server an toàn phải trả lời được:

1. **Issuer đáng tin là ai?** Token có được phát hành cho đúng resource và theo đúng token profile không?
2. **Nguồn nào xác minh tính hợp lệ?** Khóa/claims, token store cục bộ, hay Authorization Server introspection?
3. **Tình trạng active/revoked được cập nhật nhanh thế nào?** Có cache/replication lag không và window đó có được chấp nhận không?
4. **Resource Server xử lý sai lệch và outage ra sao?** Không chấp nhận token chưa đủ bằng chứng.
5. **Claims/attributes biến thành quyền như thế nào?** Scope không tự thay thế authorization cho route và tài nguyên cụ thể.
6. **Credential được bảo vệ ở đâu?** Header, outbound introspection, logs, traces, caches và error responses.

**Định dạng token không quyết định bắt buộc phải xác minh cục bộ hay từ xa.** JWT thường tiện cho xác minh mật mã local; opaque random token thường tiện cho introspection/state lookup. Nhưng đây là **xu hướng thiết kế**, không phải một định luật kỹ thuật. Việc chọn đường xác minh phải căn cứ vào **hợp đồng phát hành token, nguồn tin cậy, yêu cầu thu hồi, độ trễ, tính sẵn sàng và chính sách phân quyền**, không căn cứ duy nhất vào việc token nhìn thấy được claims hay không.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — OpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
