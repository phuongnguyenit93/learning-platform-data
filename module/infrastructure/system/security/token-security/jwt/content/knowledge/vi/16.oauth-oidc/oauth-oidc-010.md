# JWT assertion trong xác thực ứng dụng và cấp quyền

## 1. JWT assertion là gì?

Trong OAuth 2.0, **JWT assertion** là một JWT được một bên phát hành tạo ra để chứng minh một thông tin hoặc trình bày một cơ sở cấp quyền với Authorization Server (AS). Assertion thường được ký bằng JWS; AS xác minh chữ ký, kiểm tra issuer, subject, audience, thời hạn và chính sách tin cậy trước khi chấp nhận.

JWT assertion có hai mục đích quan trọng được định nghĩa trong **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants**:

1. **JWT bearer authorization grant:** dùng JWT làm authorization grant để yêu cầu AS cấp access token cho một chủ thể.
2. **JWT client authentication:** dùng JWT để client chứng minh danh tính của chính mình với AS tại token endpoint.

Hai mục đích này dùng các tham số OAuth và cách diễn giải claim khác nhau. Có thể sử dụng cả hai trong cùng một yêu cầu token, nhưng không được nhầm lẫn chúng.

JWT assertion không phải access token. Assertion là thông tin xác thực hoặc grant được gửi đến AS; access token là credential AS phát hành sau khi kiểm tra yêu cầu. Resource Server (RS) nhận access token để bảo vệ API, không mặc nhiên nhận assertion thay cho access token.

## 2. Hai cách dùng JWT assertion trong OAuth

| Cách dùng | Câu hỏi được trả lời | Vai trò của JWT | Kết quả mong đợi |
| --- | --- | --- | --- |
| **JWT bearer authorization grant** | Chủ thể nào đang được yêu cầu cấp quyền, và grant này đến từ issuer nào? | Trình bày grant được issuer đáng tin cậy phát hành cho một subject | AS có thể cấp access token nếu grant và chính sách đều hợp lệ |
| **JWT client authentication** | Ứng dụng client nào đang gọi token endpoint? | Chứng minh danh tính client với AS | AS xác thực client trước khi xử lý yêu cầu token |

### Authorization grant: JWT đại diện cho grant

Một hệ thống tin cậy có thể phát hành JWT khẳng định rằng một subject cụ thể được phép yêu cầu token trong một ngữ cảnh nhất định. Client gửi JWT này tới AS bằng grant type JWT bearer.

AS cần tin cậy issuer của assertion và xác định subject có được phép nhận quyền theo chính sách hay không. Chữ ký hợp lệ không tự động cấp mọi scope mà client yêu cầu.

### Client authentication: JWT đại diện cho client

Client có thể dùng khóa riêng tư của mình để ký JWT assertion. AS xác minh bằng khóa công khai đã đăng ký hoặc liên kết với client đó. Trong profile RFC 7523, claim iss và sub của client authentication assertion đều mang client identifier.

Cách này cho phép client chứng minh quyền kiểm soát khóa mà không gửi một shared secret tĩnh trong từng request. Khóa riêng tư vẫn phải được bảo vệ như credential có giá trị cao.

## 3. JWT bearer authorization grant theo RFC 7523

Client gửi một JWT trong tham số assertion, đồng thời chỉ định grant type:

~~~text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<signed-jwt-assertion>
~~~

Yêu cầu được gửi đến token endpoint bằng HTTPS, thường dưới dạng application/x-www-form-urlencoded. Client có thể gửi thêm scope nếu AS và profile cho phép.

### Các claim bắt buộc

Đối với JWT được dùng làm authorization grant, RFC 7523 yêu cầu các claim sau:

| Claim | Yêu cầu | Ý nghĩa trong authorization grant |
| --- | --- | --- |
| **iss** | Bắt buộc | Issuer của assertion; AS phải xác định issuer có được tin cậy hay không |
| **sub** | Bắt buộc | Chủ thể mà grant đề cập đến |
| **aud** | Bắt buộc | Authorization Server là bên nhận dự kiến của assertion |
| **exp** | Bắt buộc | Thời điểm assertion hết hạn |
| **jti** | Tùy chọn theo profile cơ bản | Định danh duy nhất; hữu ích để phát hiện assertion bị phát lại |

Claim sub có thể đại diện cho người dùng hoặc một chủ thể khác tùy hệ thống. Nếu subject là một OAuth client, profile yêu cầu định danh subject tương ứng với client identifier. AS phải ánh xạ subject sang danh tính hoặc tài khoản mà nó quản lý.

### Ví dụ JWT assertion cho grant

Header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "identity-signing-key-2026",
  "typ": "JWT"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "https://as.example/token",
  "iat": 1893456000,
  "exp": 1893456300,
  "jti": "grant-assertion-7f91"
}
~~~

Đây là payload minh họa; giá trị thời gian cần được thay bằng thời điểm thực tế khi phát hành. typ và iat có thể được yêu cầu thêm bởi profile triển khai, nhưng các claim bắt buộc của JWT bearer grant là iss, sub, aud và exp.

AS chỉ chấp nhận grant khi issuer được tin cậy, subject hợp lệ, audience phù hợp, assertion chưa hết hạn, chữ ký hợp lệ và các điều kiện cấp quyền khác được đáp ứng.

## 4. JWT client authentication theo RFC 7523

JWT client authentication cho phép client chứng minh danh tính của mình tại token endpoint bằng JWT assertion. Request sử dụng hai tham số:

~~~text
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<signed-jwt-client-assertion>
~~~

Các tham số này được gửi trong yêu cầu tới token endpoint. Client assertion không phải authorization grant; nó thực hiện chức năng xác thực client.

### Các claim bắt buộc

| Claim | Yêu cầu | Ý nghĩa trong client authentication |
| --- | --- | --- |
| **iss** | Bắt buộc | Client identifier của client đang xác thực |
| **sub** | Bắt buộc | Cũng phải là client identifier đó |
| **aud** | Bắt buộc | Authorization Server là bên nhận dự kiến |
| **exp** | Bắt buộc | Thời điểm assertion hết hạn |
| **jti** | Tùy chọn theo profile cơ bản | Định danh duy nhất, hỗ trợ chống phát lại |

Với client authentication, iss và sub phải xác định cùng client. AS dùng thông tin đăng ký client để tìm khóa hoặc bí mật tương ứng và xác minh chữ ký/MAC.

### Ví dụ JWT client assertion

Header:

~~~json
{
  "alg": "RS256",
  "kid": "orders-client-key-03",
  "typ": "JWT"
}
~~~

Payload:

~~~json
{
  "iss": "orders-service",
  "sub": "orders-service",
  "aud": "https://as.example/token",
  "iat": 1893456000,
  "exp": 1893456300,
  "jti": "client-auth-8d21"
}
~~~

Trong ví dụ, orders-service là client identifier đã được đăng ký với AS. Khóa công khai tương ứng phải được liên kết với client này trong cấu hình tin cậy. Client không thể tự khai một iss bất kỳ rồi yêu cầu AS tin nó.

## 5. So sánh hai loại assertion

| Tiêu chí | JWT bearer authorization grant | JWT client authentication |
| --- | --- | --- |
| Tham số phân biệt | grant_type và assertion | client_assertion_type và client_assertion |
| URN | urn:ietf:params:oauth:grant-type:jwt-bearer | urn:ietf:params:oauth:client-assertion-type:jwt-bearer |
| Mục tiêu | Trình bày grant cho AS | Xác thực OAuth client |
| iss | Issuer của grant assertion | Client identifier |
| sub | Chủ thể mà grant đề cập | Client identifier, trùng với iss |
| aud | AS nhận assertion | AS nhận assertion |
| exp | Bắt buộc | Bắt buộc |
| jti | Tùy chọn theo RFC 7523; nên dùng nếu cần chống replay | Tùy chọn theo RFC 7523; nên dùng nếu cần chống replay |

Không được lấy assertion dùng cho client authentication rồi coi nó tự động là authorization grant. Ngược lại, JWT grant xác định subject không có nghĩa nó đã xác thực client gửi request.

## 6. Kết hợp grant assertion và client assertion trong một request

Một client có thể cần chứng minh cả hai điều:

- Client là ứng dụng orders-service đã đăng ký với AS.
- Client đang trình bày grant assertion do issuer tin cậy phát hành cho user-123.

Khi AS hỗ trợ cả hai profile, request có thể chứa cả tham số grant và tham số client authentication:

~~~http
POST /token HTTP/1.1
Host: as.example
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&
assertion=<grant-jwt>&
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer&
client_assertion=<client-jwt>&
scope=orders:read
~~~

AS xử lý hai assertion theo hai vai trò độc lập:

1. Xác thực client bằng client assertion và khóa đã liên kết với client.
2. Xác minh grant assertion bằng khóa/issuer đã được tin cậy cho authorization grant.
3. Kiểm tra audience, thời hạn, replay và các điều kiện profile.
4. Ánh xạ subject của grant sang chủ thể được quản lý.
5. Đánh giá scope được yêu cầu và chính sách cấp quyền.
6. Nếu tất cả điều kiện thành công, phát hành access token theo chính sách của AS.

Một AS có thể không hỗ trợ đồng thời cả hai cơ chế hoặc có yêu cầu bổ sung. Client phải tuân theo metadata và tài liệu của AS; không suy đoán rằng mọi token endpoint đều hỗ trợ RFC 7523.

## 7. Assertion được ký và xác minh như thế nào?

JWT assertion theo RFC 7523 **phải được ký số hoặc bảo vệ bằng MAC**. Assertion cũng có thể được mã hóa bằng JWE khi cần giữ bí mật nội dung; nếu mã hóa, JWT phải được ký/MAC trước rồi mới mã hóa. Assertion không được chấp nhận chỉ vì có thể Base64url decode. AS phải xác minh chữ ký hoặc MAC với thuật toán và khóa tin cậy, đồng thời giải mã có xác thực nếu profile dùng JWE.

Quy trình khái quát:

~~~mermaid
sequenceDiagram
    participant Client as OAuth Client
    participant Issuer as Assertion Issuer
    participant AS as Authorization Server
    participant RS as Resource Server

    Issuer->>Issuer: Tạo claims và ký JWT grant
    Client->>Client: Tạo client assertion bằng khóa client
    Client->>AS: POST token request + grant assertion + client assertion
    AS->>AS: Xác thực client assertion
    AS->>AS: Xác minh grant assertion
    AS->>AS: Kiểm tra iss, sub, aud, exp và replay
    AS->>AS: Áp dụng chính sách cấp scope
    AS-->>Client: Access token
    Client->>RS: Gửi access token tới API
    RS->>RS: Xác minh access token theo profile của API
    RS-->>Client: Trả kết quả được phép
~~~

### Chọn khóa và thuật toán

- Chỉ chấp nhận thuật toán được cấu hình trước cho issuer/client tương ứng.
- Liên kết khóa với đúng issuer hoặc client đã đăng ký.
- Dùng kid để chọn khóa ứng viên trong tập khóa tin cậy; kid không tự chứng minh khóa đáng tin.
- Không tải khóa từ URL tùy ý do assertion cung cấp.
- Từ chối alg: none và các thuật toán không nằm trong allowlist.
- Kiểm tra loại khóa, mục đích sử dụng và thuật toán tương ứng.

Với chữ ký bất đối xứng, issuer/client giữ private key còn AS xác minh bằng public key. Nếu dùng MAC, các bên giữ cùng secret và mọi bên có secret đều có thể tạo assertion hợp lệ; cần giới hạn phạm vi chia sẻ secret.

### Ký rồi mã hóa khi cần bảo mật nội dung

Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành theo khóa, nhưng payload JWS có thể được đọc bởi người có token. Nếu assertion chứa dữ liệu cần giữ kín, có thể áp dụng JWE theo profile được thỏa thuận. Khi assertion được mã hóa, bên nhận phải giải mã có xác thực và xác minh chữ ký theo đúng cấu trúc bảo vệ đã chọn. Không mặc định mọi AS đều hỗ trợ assertion dạng nested hoặc encrypted; phải kiểm tra profile của AS.

## 8. Audience và thời hạn của assertion

### Audience phải hướng đến đúng Authorization Server

aud xác định bên nhận dự kiến của JWT assertion. Giá trị cụ thể phải khớp với định danh AS mà hai bên đã thống nhất. Một số triển khai dùng token endpoint URL; triển khai khác dùng issuer identifier của AS. Client phải theo đúng giá trị được AS công bố hoặc quy định.

Không dùng audience của Resource Server thay cho audience của token endpoint chỉ vì access token cuối cùng sẽ được gửi đến Resource Server. Assertion được gửi đến AS nên AS là audience của assertion.

### Assertion cần thời hạn ngắn

exp là claim bắt buộc và có kiểu NumericDate (số giây kể từ Unix epoch). Assertion nên chỉ có hiệu lực trong một khoảng ngắn phù hợp với độ trễ mạng, xử lý và clock skew. Thời hạn ngắn làm giảm cửa sổ mà assertion bị đánh cắp có thể bị sử dụng.

Có thể dùng thêm:

- iat: thời điểm phát hành, giúp AS kiểm tra assertion quá cũ.
- nbf: thời điểm bắt đầu hiệu lực, nếu profile cần.
- jti: định danh duy nhất để phát hiện việc dùng lại assertion.

AS nên áp dụng dung sai đồng hồ nhỏ và thống nhất. Không nên kéo dài thời hạn chỉ để xử lý đồng hồ hệ thống lệch; cần đồng bộ thời gian của các máy chủ.

## 9. Chống phát lại assertion

JWT assertion là bearer artifact: bất kỳ ai lấy được assertion và gửi đến AS trong thời gian còn hiệu lực đều có thể thử sử dụng nó. Chữ ký hợp lệ không tự ngăn phát lại.

### Sử dụng jti và kho replay

Nếu profile yêu cầu assertion dùng một lần, AS có thể thực hiện:

1. Xác minh chữ ký và các claim cơ bản.
2. Tạo khóa tra cứu từ issuer và jti.
3. Thực hiện thao tác kiểm tra-và-ghi nguyên tử để bảo đảm jti chưa được dùng.
4. Ghi nhận jti đến ít nhất thời điểm assertion hết hạn cộng clock skew.
5. Từ chối assertion nếu jti đã tồn tại.

~~~text
replayKey = issuer + ":" + jti

if atomic_insert_if_absent(replayKey, expiresAt):
    accept_replay_check
else:
    reject_replayed_assertion
~~~

Kho replay phải dùng chung giữa các instance AS hoặc có cơ chế đồng bộ phù hợp. Nếu mỗi instance chỉ giữ cache riêng, kẻ tấn công có thể gửi cùng assertion đến nhiều instance khác nhau.

### Retry và assertion đã dùng

Nếu request bị timeout sau khi AS đã ghi nhận jti, việc gửi lại đúng assertion có thể bị từ chối như replay. Client nên tạo assertion mới với jti mới cho lần thử mới, trừ khi AS cung cấp cơ chế idempotency riêng. Cần phân biệt retry của request với việc tái sử dụng một credential dùng một lần.

## 10. Assertion không tự cấp quyền: AS vẫn phải áp dụng policy

Một grant assertion hợp lệ là bằng chứng được phát hành bởi issuer mà AS tin cậy. Nó không tự động cho phép client yêu cầu mọi scope hoặc truy cập mọi tài nguyên.

AS cần đánh giá:

- Issuer có được phép phát hành grant cho loại subject này không?
- Subject có tồn tại và có trạng thái hợp lệ không?
- Client có được phép dùng grant này không?
- Grant có giới hạn audience, tenant, resource hoặc mục đích không?
- Scope được yêu cầu có nằm trong phạm vi mà issuer/subject/client được phép không?
- Có yêu cầu consent, delegation, policy hoặc kiểm tra bổ sung nào không?

Ví dụ, grant assertion xác định sub là user-123, nhưng client yêu cầu scope=orders:write. AS vẫn cần kiểm tra subject, client và issuer có được phép cấp quyền ghi đơn hàng hay không. Không nên coi claim tùy ý như role=admin là mệnh lệnh cấp quyền nếu profile và trust policy không quy định rõ nguồn gốc cũng như ý nghĩa của claim đó.

Sau khi cấp token, Resource Server tiếp tục xác minh access token theo audience và policy riêng của API. Việc AS đã chấp nhận assertion không thay thế bước kiểm tra access token ở Resource Server.

## 11. Phân biệt JWT assertion, access token và OIDC ID token

| Loại JWT | Mục đích chính | Bên nhận điển hình | Có dùng trực tiếp để gọi API không? |
| --- | --- | --- | --- |
| **JWT authorization grant assertion** | Trình bày grant tại token endpoint | Authorization Server | Không; dùng để yêu cầu cấp access token |
| **JWT client assertion** | Xác thực OAuth client | Authorization Server | Không; dùng trong client authentication |
| **JWT access token** | Mang quyền truy cập được AS cấp | Resource Server | Có, nếu API chấp nhận đúng profile |
| **OIDC ID token** | Cung cấp thông tin xác thực về người dùng cho OIDC client | Relying Party / OIDC Client | Không; không dùng thay access token |

ID token được thiết kế cho OIDC client và có audience, nonce cùng các quy tắc riêng. Không dùng ID token làm JWT bearer grant hoặc client assertion chỉ vì cả hai đều là JWT. Cần kiểm tra đúng loại token, issuer, audience và mục đích của từng profile.

## 12. Những lỗi bảo mật thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm grant assertion với client assertion | Xác thực client và cấp quyền bị trộn lẫn | Dùng đúng tham số và claim semantics cho từng profile |
| Nhầm assertion với access token | Gửi assertion trực tiếp đến API | Chỉ gửi access token đến Resource Server |
| Chấp nhận JWT chỉ vì decode được | Assertion giả mạo có thể được xử lý | Xác minh JWS/JWE và trust policy |
| Không kiểm tra aud | Assertion phát hành cho AS khác có thể bị dùng sai ngữ cảnh | Kiểm tra audience theo định danh AS đã cấu hình |
| Không kiểm tra exp | Assertion bị đánh cắp có cửa sổ sử dụng dài | Bắt buộc thời hạn ngắn và kiểm tra clock skew |
| Không chống replay | Một assertion có thể được sử dụng nhiều lần | Dùng jti và replay store nguyên tử khi profile yêu cầu |
| Tin iss hoặc sub tự khai | Kẻ tấn công có thể mạo danh issuer/subject | Ánh xạ issuer, client và subject vào nguồn tin cậy |
| Cho token quyết định thuật toán | Có nguy cơ algorithm confusion | Allowlist thuật toán và gắn khóa với thuật toán |
| Tải JWKS từ URL tùy ý trong header | Có thể xác minh bằng khóa do attacker kiểm soát | Dùng JWKS URI/khóa đã đăng ký và tin cậy |
| Coi scope yêu cầu là scope được cấp | Client có thể vượt quyền | AS phải áp dụng policy và chỉ cấp scope được phép |
| Ghi assertion vào log | Credential có thể bị đánh cắp từ log | Redact assertion và bảo vệ log |
| Dùng ID token thay assertion | Nhầm lẫn mục đích và audience | Phân biệt profile OAuth và OIDC |

## 13. Checklist triển khai JWT assertion

**Phía phát hành/client**

- Xác định rõ JWT được dùng làm authorization grant hay client authentication.
- Dùng đúng URN và tham số OAuth theo RFC 7523.
- Tạo iss, sub, aud, exp đúng ngữ nghĩa của profile.
- Dùng jti duy nhất nếu AS yêu cầu hoặc cần chống replay.
- Ký assertion bằng thuật toán và khóa đã đăng ký.
- Bảo vệ private key/secret, giới hạn quyền truy cập và có kế hoạch rotation.
- Gửi assertion đến token endpoint qua HTTPS.
- Không ghi assertion hoặc private key vào log.

**Phía Authorization Server**

- Chỉ bật profile RFC 7523 khi endpoint được cấu hình hỗ trợ.
- Xác định issuer/client nào được tin cậy và khóa nào tương ứng.
- Allowlist thuật toán; kiểm tra kid, loại khóa và mục đích sử dụng.
- Kiểm tra chữ ký/MAC, iss, sub, aud, exp, cùng nbf/iat nếu profile yêu cầu.
- Chống replay bằng jti và kho dùng chung khi cần.
- Áp dụng policy cho subject, client, scope và resource.
- Phát hành access token riêng theo audience và quyền đã được cấp.
- Từ chối assertion sai profile, sai audience, hết hạn, bị phát lại hoặc không xác minh được.

**Phía Resource Server**

- Chỉ nhận access token được cấp cho API.
- Xác minh access token theo issuer, audience, thuật toán, khóa và thời hạn của profile API.
- Kiểm tra scope/permission cho từng hành động và tài nguyên.
- Không coi JWT assertion đã dùng tại token endpoint là access token.

**Ghi nhớ:** RFC 7523 định nghĩa hai cách dùng JWT khác nhau trong OAuth: JWT bearer authorization grant và JWT client authentication. Cả hai đều cần issuer, subject, audience và expiration hợp lệ, nhưng ý nghĩa của iss và sub khác nhau. Assertion phải được xác minh bằng khóa tin cậy, kiểm tra audience và thời hạn, đồng thời có biện pháp chống replay phù hợp. AS vẫn phải áp dụng authorization policy trước khi cấp access token; Resource Server sau đó xác minh access token riêng.

### Tài liệu chuẩn để tra cứu

- **RFC 7521 — Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants:** khung tổng quát cho assertion trong OAuth.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT bearer authorization grant và JWT client authentication.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** token endpoint, client authentication, access token và scope.
- **RFC 7519 — JSON Web Token (JWT):** claims iss, sub, aud, exp, nbf, iat, jti.
- **RFC 7515 — JSON Web Signature (JWS):** bảo vệ và xác minh JWT assertion bằng chữ ký/MAC.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm tra thuật toán, issuer, audience và các rủi ro JWT.
