# Refresh token thuộc trách nhiệm client và authorization server

Trong OAuth 2.0, **access token** và **refresh token** có hai mục đích khác nhau. Access token được OAuth client gửi tới **Resource Server** để truy cập API. Refresh token được OAuth client gửi tới **Authorization Server** để xin một access token mới khi access token hiện tại hết hạn hoặc không còn dùng được. Refresh token không phải credential để gọi API nghiệp vụ và Resource Server không có trách nhiệm đổi nó thành access token.

Ranh giới này rất quan trọng trong một hệ thống **Spring Security OAuth 2.0 / OIDC Resource Server**. Khi access token hết hạn, Resource Server cần từ chối request theo hợp đồng Bearer, thường bằng **401 Unauthorized** và challenge phù hợp. OAuth client quyết định có thể refresh hay cần yêu cầu người dùng xác thực lại. Authorization Server xác minh refresh token, kiểm tra client và chính sách cấp quyền, rồi phát hành access token mới hoặc từ chối grant.

Có thể hình dung:

```text
OAuth Client                         Authorization Server
     |                                        |
     | 1. Xin access token                    |
     |--------------------------------------->|
     | 2. access_token + refresh_token        |
     |<---------------------------------------|
     |
     | 3. Authorization: Bearer access_token
     v
Resource Server
     |
     | 4. Xác minh access token / scope
     | 5. Trả dữ liệu hoặc 401/403
     |
     | 6. Nếu cần, client gọi token endpoint
     |    bằng refresh_token
     +---------------------------------------> Authorization Server
     |                                        |
     | 7. access_token mới và có thể          |
     |    refresh_token mới                   |
     |<---------------------------------------+
```

**Điểm cần nhớ:** Resource Server xử lý access token của request hiện tại. OAuth client quản lý vòng đời token mà nó sở hữu. Authorization Server quyết định refresh token còn hợp lệ hay không và có cấp token mới hay không.

> **Ngữ cảnh minh họa:** Orders API chạy Spring Boot 3.x / Spring Security 6.x như OAuth 2.0 Resource Server. Web frontend hoặc BFF là OAuth client đăng nhập qua Authorization Code flow. Access token được gửi tới Orders API bằng `Authorization: Bearer ...`. Tên endpoint, client ID và các giá trị trong ví dụ chỉ mang tính minh họa.

## 1. Access token và refresh token có trách nhiệm khác nhau

| Thuộc tính | Access token | Refresh token |
|---|---|---|
| Mục đích | Truy cập Resource Server/API | Xin access token mới từ Authorization Server |
| Nơi gửi | Resource Server | Authorization Server token endpoint |
| Ai sở hữu/quản lý trong flow | OAuth client nhận token | OAuth client nhận token |
| Ai xác minh | Resource Server theo JWT validation hoặc introspection | Authorization Server |
| Phạm vi sử dụng | Resource/audience, scope và thời hạn cụ thể | Token endpoint, client/grant và chính sách AS |
| Có thể chứa quyền | Có, qua scope/claims hoặc introspection metadata | Không dùng trực tiếp làm quyền gọi API |
| Có được gửi trong API request? | Có, dưới dạng Bearer nếu đúng audience | **Không** |
| Khi hết hạn | Client xin token mới; API từ chối token hết hạn | Client cần authorization grant mới hoặc quy trình cấp lại theo AS |
| Thu hồi | Có thể cần introspection, denylist hoặc TTL ngắn để tác động nhanh | AS có thể vô hiệu hóa refresh token/token family |
| Mức độ nhạy cảm | Bearer credential có thể bị replay | Credential dài hạn hơn, thường có tác động lớn hơn nếu bị lộ |

### 1.1. Access token là credential dành cho Resource Server

Ví dụ client gọi Orders API:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
```

Resource Server xác minh token theo loại token được cấu hình:

- Với **JWT**, kiểm tra chữ ký bằng khóa đáng tin, issuer, audience, thời hạn, token profile và validators khác.
- Với **opaque token**, gọi introspection endpoint đã cấu hình và kiểm tra `active` cùng metadata cần thiết.
- Sau authentication, kiểm tra scope, tenant, ownership và quyền nghiệp vụ.

Resource Server không cần biết refresh token của client để thực hiện các bước đó.

### 1.2. Refresh token là credential dành cho token endpoint

Khi access token hết hạn, client có thể gửi:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET

grant_type=refresh_token&
refresh_token=REFRESH_TOKEN
```

Đây là request **client → Authorization Server**, không phải request **client → Orders API**.

Authorization Server kiểm tra tối thiểu các yếu tố theo grant và chính sách:

- Refresh token có tồn tại, còn hiệu lực và chưa bị thu hồi không?
- Refresh token có được cấp cho client đang gọi không?
- Client authentication có hợp lệ nếu client là confidential không?
- Token có được cấp trong grant/session phù hợp không?
- Requested scope/resource có nằm trong phạm vi được phép không?
- Chính sách rotation, reuse detection, inactivity và absolute lifetime có được thỏa mãn không?

Nếu hợp lệ, AS phát hành access token mới và có thể phát hành refresh token mới.

### 1.3. Không coi refresh token là access token thứ hai

Refresh token thường là chuỗi opaque và có thể dài hạn. Nó không có nghĩa là “một Bearer token mạnh hơn” để gọi API.

Một Resource Server không nên chấp nhận:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer REFRESH_TOKEN
```

Nếu refresh token vô tình được gửi tới API, Resource Server phải từ chối nó theo access-token validation/introspection contract. Không thử dùng nó để gọi token endpoint, không lưu nó vào security context như access token và không tự suy đoán loại token từ độ dài hoặc hình thức chuỗi.

## 2. Ba vai trò trong vòng đời refresh token

### 2.1. OAuth client

Client có trách nhiệm:

- Nhận và bảo vệ access token/refresh token theo loại client.
- Gửi access token tới đúng Resource Server/audience.
- Phát hiện khi access token không còn dùng được.
- Gửi refresh token tới đúng Authorization Server token endpoint.
- Thực hiện client authentication khi cần.
- Xử lý refresh token rotation và lưu token mới an toàn.
- Ngăn nhiều request đồng thời refresh cùng một token theo cách gây reuse.
- Yêu cầu người dùng xác thực lại khi refresh thất bại và không có grant hợp lệ khác.
- Không đưa refresh token vào URL, API request, logs, traces hoặc analytics.

### 2.2. Authorization Server

AS có trách nhiệm:

- Phát hành refresh token chỉ trong grant/client/flow được phép.
- Gắn refresh token với client, authorization grant, user/session và chính sách.
- Xác minh refresh token khi nhận `grant_type=refresh_token`.
- Xác minh client khi cần và giới hạn scope/resource.
- Thực hiện rotation hoặc sender-constraining theo security policy.
- Phát hiện refresh token reuse khi áp dụng rotation.
- Thu hồi refresh token/token family khi cần.
- Áp dụng expiry, inactivity timeout, absolute lifetime và consent policy.
- Ghi audit và bảo vệ token store.

### 2.3. Resource Server

Resource Server có trách nhiệm:

- Chấp nhận **access token** dành cho API.
- Xác minh chữ ký/claims hoặc introspect token.
- Trả 401 khi access token thiếu hoặc không hợp lệ.
- Trả 403 khi token hợp lệ nhưng thiếu quyền.
- Không nhận refresh token để truy cập tài nguyên.
- Không gọi token endpoint để refresh token của caller.
- Không yêu cầu caller gửi refresh token trong request API.
- Không lưu refresh token của caller trong session hoặc database chỉ để phục vụ việc truy cập API, trừ khi ứng dụng thực sự đóng vai trò OAuth client/BFF trong một flow outbound riêng.

| Tác nhân | Việc cần làm | Việc không thuộc trách nhiệm mặc định |
|---|---|---|
| OAuth client | Quyết định refresh, gửi refresh grant, lưu token mới | Tự khẳng định refresh token vẫn active mà không hỏi AS |
| Authorization Server | Xác minh refresh token, cấp/rotation/revoke | Để Resource Server tự đoán trạng thái token |
| Resource Server | Xác minh access token và authorization | Đổi refresh token của API caller thành access token |

## 3. Refresh token grant theo OAuth 2.0

RFC 6749 `6 mô tả refresh token grant. Client gửi token endpoint request với `grant_type=refresh_token` và refresh token đã nhận trước đó.

### 3.1. Request cơ bản

```http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic b3JkZXJzLWJmZjpwYXNzd29yZA==

grant_type=refresh_token&
refresh_token=REFRESH_TOKEN_VALUE
```

Với confidential client, Authorization Server thường xác thực client bằng phương thức đã đăng ký, ví dụ HTTP Basic trong minh họa. Client secret phải được bảo vệ như credential server-side.

Với public client, không có client secret an toàn để giữ. AS cần nhận diện client theo registration và áp dụng biện pháp bảo vệ refresh token phù hợp, chẳng hạn rotation hoặc sender-constrained refresh token theo OAuth 2.0 Security Best Current Practice.

### 3.2. Response thành công

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "orders.read orders.write"
}
```

Các trường cần hiểu:

- `access_token`: access token mới dùng để gọi Resource Server.
- `token_type`: loại token, thường là `Bearer`.
- `expires_in`: thời gian hiệu lực access token theo giây nếu AS trả trường này.
- `refresh_token`: refresh token mới nếu AS phát hành/rotation.
- `scope`: scope được cấp; client phải dùng đúng quyền được trả, không giả định nó luôn bằng yêu cầu trước.

Không phải mọi response đều bắt buộc phát refresh token mới trong mọi triển khai. Tuy nhiên nếu AS áp dụng **refresh token rotation**, client phải thay thế token cũ bằng token mới khi nhận thành công.

### 3.3. Refresh grant không phải Authorization Code flow mới

Refresh token grant sử dụng một grant đã được cấp trước đó. Nó không yêu cầu người dùng nhập lại mật khẩu hay mở browser trong mỗi lần refresh.

Nếu refresh token hết hạn, bị thu hồi, reuse hoặc không còn hợp lệ, client thường cần bắt đầu lại authorization flow phù hợp (ví dụ Authorization Code + PKCE) để lấy grant mới. Không cố “refresh refresh token” bằng cách gửi nó tới Resource Server.

## 4. Vì sao Resource Server không nên refresh token?

Một Resource Server nhận request từ nhiều OAuth client khác nhau. Nó không mặc định sở hữu:

- Client registration của caller.
- Client secret hoặc private key của caller.
- Refresh token.
- Consent và authorization grant ban đầu.
- Session/browser context cần thiết để thực hiện reauthentication.
- Quyền thay đổi scope/resource của client.

Nếu Resource Server nhận refresh token rồi tự gọi token endpoint, nó đang đảm nhận một vai trò OAuth client mà không có ranh giới và quyền quản lý rõ ràng.

### 4.1. Những rủi ro nếu API nhận refresh token

**Lộ credential:** refresh token thường sống lâu hơn access token. Nếu xuất hiện trong access logs, tracing hoặc API gateway, tác động của sự cố lớn hơn.

**Confused deputy:** Resource Server có thể dùng credential của caller theo client identity hoặc audience không đúng, đặc biệt khi nhiều client/tenant dùng chung API.

**Sai ranh giới quyền:** API có thể không biết refresh token thuộc client nào, grant nào, user nào hoặc resource nào.

**Refresh token replay:** nếu nhiều API instance cùng refresh một token, rotation/reuse detection có thể vô hiệu hóa cả token family.

**Khó quản lý session:** Resource Server không sở hữu authorization session của browser/mobile client và không nên tự điều khiển login flow của chúng.

**Khó audit:** việc refresh ở API khiến không rõ client nào đã yêu cầu cấp token mới và theo grant nào.

### 4.2. Hợp đồng đúng giữa client và API

```text
Client
  |
  | Authorization: Bearer access_token
  v
Resource Server
  |
  | 200 / 401 / 403
  v
Client decides next step
  |
  +-- access token still usable -> continue
  |
  +-- expired/invalid -> call AS token endpoint
  |
  +-- refresh rejected -> start authorization flow again
```

Resource Server trả kết quả xác thực. Client điều phối refresh. AS quyết định refresh grant có được chấp nhận hay không.

### 4.3. Ngoại lệ: một ứng dụng vừa là Resource Server vừa là OAuth client

Một backend có thể đồng thời:

- Nhận access token inbound để bảo vệ API của chính nó.
- Dùng OAuth client registration riêng để gọi downstream API.
- Lưu authorized client và refresh token **của chính outbound grant**.
- Refresh access token outbound bằng Spring OAuth2 Client.

Đây là hai vai trò riêng trong cùng ứng dụng. Nó **không** cho phép backend lấy refresh token của caller inbound rồi dùng nó như refresh token của service hoặc chuyển tiếp nó sang downstream.

## 5. Access token hết hạn: API và client xử lý thế nào?

Giả sử access token hết hạn lúc 10:00. Client gọi Orders API lúc 10:01:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer EXPIRED_ACCESS_TOKEN
```

Với JWT, decoder kiểm tra `exp` và từ chối. Với opaque token, introspection có thể trả `active=false`. Resource Server thường trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

Sau đó client có thể thử refresh theo chính sách của nó.

### 5.1. Resource Server không tự gửi redirect login

API không nên trả 302 tới `/login` hoặc OpenID Provider chỉ vì access token hết hạn. Client có thể là mobile app, CLI, backend service hoặc SPA; mỗi client có cách xử lý đăng nhập khác nhau.

Với Bearer API, 401 và `WWW-Authenticate` cho client biết authentication không được chấp nhận. Client tự quyết định refresh hoặc yêu cầu user đăng nhập lại theo authorization flow.

### 5.2. Client không nên refresh sau mọi lỗi 401 một cách mù quáng

401 có thể đến từ:

- Access token hết hạn.
- Signature/issuer/audience sai.
- Token bị thu hồi.
- Token không dành cho resource này.
- Token malformed.
- Gateway hoặc authentication layer khác từ chối.

Một client có thể thử refresh **một lần có kiểm soát** khi lỗi phù hợp với access-token failure và refresh policy cho phép. Nếu token mới vẫn bị 401, không lặp refresh vô hạn. Lỗi audience/issuer sai thường là cấu hình/client bug, refresh lại cùng grant có thể không sửa được.

### 5.3. 403 không phải tín hiệu refresh mặc định

Nếu access token hợp lệ nhưng thiếu `orders.write`, API có thể trả 403. Refresh token không tự cấp thêm scope. AS chỉ có thể cấp scope mới nếu authorization grant, consent và policy cho phép.

Client không nên xử lý mọi 403 bằng refresh/login loop. Nó cần hiển thị lỗi quyền hoặc đi theo quy trình xin quyền phù hợp.

## 6. Client refresh flow từng bước

Một flow phổ biến:

```mermaid
sequenceDiagram
    autonumber
    participant App as OAuth Client
    participant API as Orders Resource Server
    participant AS as Authorization Server

    App->>API: Request + access token A1
    API-->>App: 401 invalid_token
    App->>AS: POST token endpoint, refresh_token=R1
    AS->>AS: Validate R1, client, grant, scope and policy
    AS-->>App: access token A2 + refresh token R2
    App->>App: Atomically replace A1/R1 with A2/R2
    App->>API: Retry request + access token A2
    API->>API: Verify A2 and authorize
    API-->>App: API response
```

### 6.1. Bước 1: giữ access token và refresh token theo đúng client

Client lưu token pair trong nơi bảo vệ phù hợp:

- BFF/server-side application: server-side authorized-client store, mã hóa dữ liệu nhạy cảm, access control và backup phù hợp.
- Native mobile app: secure storage của hệ điều hành, bảo vệ bằng platform keystore/keychain.
- SPA: cân nhắc BFF để tránh lưu refresh token dài hạn trong JavaScript-accessible storage. Nếu SPA giữ token, cần threat model browser/XSS và biện pháp bảo vệ theo OAuth security BCP.

Không gửi refresh token trong request tới Orders API.

### 6.2. Bước 2: gọi đúng token endpoint

Client gửi refresh token tới token endpoint của **đúng issuer/authorization server** nơi grant được cấp. Không suy ra endpoint từ một URL tùy ý do API trả về, JWT claim chưa xác minh hoặc query parameter.

### 6.3. Bước 3: AS xác minh grant

AS kiểm tra refresh token và client. Nếu refresh token thuộc client A mà client B gửi, request phải bị từ chối. Nếu token bị thu hồi, hết hạn hoặc không hợp lệ, AS không phát access token mới.

### 6.4. Bước 4: thay token pair nguyên tử

Nếu response chứa refresh token mới, client cần cập nhật **cả access token và refresh token** như một đơn vị logic. Không ghi access token mới nhưng quên refresh token mới; không tiếp tục dùng refresh token cũ sau khi rotation thành công.

### 6.5. Bước 5: retry API request có kiểm soát

Client gửi lại request với access token mới. Chỉ retry số lần hữu hạn, có cơ chế chống lặp và xem xét request có an toàn để replay không.

Với POST/PUT/PATCH gây side effect, cần idempotency key hoặc semantics phù hợp. Nếu response đầu tiên bị mất sau khi server đã xử lý, việc retry có thể tạo side effect trùng lặp. Refresh token không giải quyết vấn đề idempotency.

## 7. Refresh token rotation

**Refresh token rotation** là cơ chế AS phát hành refresh token mới sau khi refresh thành công và làm token cũ mất hiệu lực.

Ví dụ:

```text
Ban đầu:
  Access token A1
  Refresh token R1

Refresh thành công:
  Access token A2
  Refresh token R2

Sau rotation:
  R1 = invalid
  R2 = current
```

Rotation làm giảm thời gian một refresh token bị đánh cắp có thể tiếp tục được sử dụng. Nó đặc biệt quan trọng với public clients không thể giữ client secret an toàn.

### 7.1. Response rotation

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "R2",
  "scope": "orders.read"
}
```

Client phải lưu `R2` và ngừng dùng `R1`. Việc giữ lại R1 để “phòng trường hợp” có thể kích hoạt reuse detection hoặc bị AS từ chối.

### 7.2. Reuse detection

Giả sử attacker đánh cắp R1. Người dùng hợp lệ refresh trước:

```text
R1 -> refresh thành công -> R2
R1 bị vô hiệu hóa
```

Sau đó attacker dùng lại R1. AS phát hiện một refresh token đã bị sử dụng lại. Tùy policy/implementation, AS có thể thu hồi **token family/grant** liên quan để ngăn attacker tiếp tục sử dụng R2.

Điều này có thể làm phiên hợp lệ của người dùng cũng phải đăng nhập lại. Đây là một phản ứng bảo mật có chủ đích để xử lý dấu hiệu replay.

### 7.3. Rotation yêu cầu lưu trạng thái phía AS

Một triển khai rotation thường cần liên kết token với:

- Token family/grant ID.
- Client ID.
- Subject hoặc user/session.
- Token generation/parent relationship.
- Trạng thái active/used/revoked.
- Issued-at, expiry và inactivity timestamps.
- Sender constraint nếu có.

Refresh token nên được bảo vệ trong token store; có thể lưu hash hoặc dạng bảo vệ tương đương để giảm tác động nếu database bị đọc. Cách lưu cụ thể phụ thuộc AS implementation.

## 8. Race condition khi nhiều request cùng refresh

Một lỗi thường gặp ở SPA/BFF/mobile: nhiều API request cùng nhận 401 gần như đồng thời và tất cả cùng dùng R1 để refresh.

```text
Request A -> 401 -> refresh R1
Request B -> 401 -> refresh R1
Request C -> 401 -> refresh R1

AS nhận:
  R1 -> success, issue R2
  R1 -> reuse/replay
  R1 -> reuse/replay

Possible result:
  token family bị revoke
  các request khác thất bại
  user phải login lại
```

### 8.1. Single-flight refresh

Client nên có một cơ chế **single-flight/mutex** theo authorized client/session:

1. Request đầu tiên phát hiện token cần refresh và giữ lock.
2. Các request khác chờ kết quả refresh thay vì gọi AS bằng R1.
3. Request đầu tiên refresh thành công và lưu A2/R2 nguyên tử.
4. Các request chờ lấy token mới từ store.
5. Chỉ retry API sau khi cập nhật token pair hoàn tất.
6. Nếu refresh thất bại, các request chờ cùng nhận trạng thái cần reauthentication.

Không dùng một global lock cho mọi user trong hệ thống. Lock cần có phạm vi theo client/session/authorization grant, và nếu chạy nhiều application instances thì phải có coordination phù hợp.

### 8.2. Cập nhật token pair nguyên tử

Pseudo-code:

```text
refreshIfNeeded(authorizedClient):
    acquire lock for (registrationId, principal/session)

    reload latest authorized client from store
    if latest access token is still valid:
        return latest access token

    response = call AS refresh grant with latest refresh token

    if response successful:
        atomically persist:
            new access token
            new expiry
            new refresh token if returned
        return new access token

    if response invalid_grant:
        remove/revoke local authorized-client state as policy requires
        require reauthentication

    release lock
```

Điểm quan trọng là **reload sau khi lấy lock**. Một request khác có thể đã refresh và cập nhật token trong lúc request hiện tại đang chờ.

### 8.3. Multi-instance BFF

Nếu BFF chạy nhiều pods, mutex trong memory chỉ bảo vệ một pod. Cần lựa chọn:

- Sticky routing theo session nếu có thể và đủ tin cậy.
- Distributed lock theo authorized-client/grant.
- Compare-and-set/versioned update trong persistent token store.
- Một refresh coordinator có ownership rõ ràng.
- Xử lý conflict khi hai instance nhận cùng generation.

Không để hai pods đồng thời sử dụng một refresh token rotating mà không có coordination.

## 9. Khi refresh request thất bại

Một response lỗi phổ biến:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant",
  "error_description": "The refresh token is invalid or expired"
}
```

### 9.1. `invalid_grant`

Có thể do:

- Refresh token hết hạn.
- Token bị thu hồi.
- Token cũ đã bị rotation và sử dụng lại.
- Token không thuộc client/grant hiện tại.
- Grant/session không còn hiệu lực.
- Refresh token sai định dạng hoặc không tồn tại.

Client thường cần xóa authorized-client state không còn dùng được và khởi động lại authorization flow nếu user cần tiếp tục. Không retry vô hạn cùng refresh token.

### 9.2. `invalid_client`

Client authentication không hợp lệ, ví dụ client secret sai hoặc client không được phép dùng grant. Đây thường là lỗi cấu hình/client registration hoặc secret rotation. Không yêu cầu người dùng đăng nhập lại để che một client secret sai ở server-side BFF.

### 9.3. `invalid_scope`

Client yêu cầu scope vượt quá quyền grant ban đầu hoặc AS không cho phép. Client không nên tự lặp request với scope rộng hơn. Nó phải tuân theo scope được AS cấp và quy trình consent/authorization thích hợp.

### 9.4. Timeout hoặc mất kết nối: kết quả có thể không rõ

Một trường hợp khó:

1. Client gửi R1.
2. AS xử lý thành công, vô hiệu hóa R1 và phát R2.
3. Response bị mất trên mạng.
4. Client chỉ biết request timeout, không biết R2 đã được phát hành.

Nếu client gửi lại R1, AS có thể coi đó là reuse và revoke token family.

Vì vậy, retry refresh grant **không giống retry GET idempotent**. Cần có chiến lược phù hợp AS: hỗ trợ grace/reuse handling có giới hạn, sender-constrained token, recovery protocol hoặc buộc reauthentication khi không thể khôi phục an toàn. Client không nên tự giả định R1 còn dùng được sau timeout.

## 10. Refresh token expiry, inactivity và revocation

Một refresh token có thể chịu nhiều giới hạn thời gian:

| Giới hạn | Ý nghĩa |
|---|---|
| Absolute lifetime | Thời gian tối đa từ lúc phát hành, dù token có được sử dụng |
| Inactivity/idle timeout | Hết hạn nếu không được sử dụng trong khoảng thời gian quy định |
| Grant/session lifetime | Thời hạn của authorization grant hoặc phiên user |
| Rotation generation policy | Giới hạn vòng đời token family hoặc generation |
| Risk-based expiry | AS thu hồi/hết hạn sớm theo risk policy |
| Administrative revocation | Người dùng/admin/security team thu hồi grant hoặc token |

Không giả định refresh token luôn sống lâu hơn access token vô hạn. AS có thể áp expiry ngắn, idle timeout hoặc absolute lifetime.

### 10.1. Refresh token bị revoke không nhất thiết vô hiệu hóa access token đã phát hành ngay lập tức

Đây là điểm quan trọng khi thiết kế vòng đời:

- Thu hồi refresh token ngăn client dùng token đó để xin access token mới.
- Nhưng access token đã phát hành trước đó có thể vẫn hợp lệ tới `exp` nếu Resource Server chỉ xác minh JWT offline.
- Với opaque token introspection, AS có thể trả `active=false` cho access token bị thu hồi nếu AS có liên kết và policy tương ứng.
- Nếu cần thu hồi access token JWT gần như tức thời, cần cơ chế bổ sung như denylist, token version/session checks, introspection, hoặc access token lifetime ngắn.

**Không suy luận “đã revoke refresh token thì mọi API access token đang tồn tại tự động chết ngay”.** Hành vi phụ thuộc cách AS quản lý grant và cách Resource Server kiểm tra access token.

### 10.2. Logout không đồng nghĩa revoke mọi token

Logout có thể gồm nhiều hành động:

- Xóa session cookie/local application session.
- Kết thúc OIDC RP session hoặc điều hướng qua end-session endpoint nếu được hỗ trợ.
- Revoke refresh token/grant qua revocation endpoint theo RFC 7009.
- Thu hồi access token nếu AS hỗ trợ và API có cơ chế nhận biết.
- Xóa token cache/authorized-client state ở BFF.

OIDC logout và OAuth token revocation là các giao thức/chính sách liên quan nhưng **không tự động tương đương**. Cần xác định rõ logout có thu hồi refresh token không, có thu hồi access token không, và các Resource Server nhìn thấy thay đổi sau bao lâu.

## 11. Scope và resource khi refresh

Refresh grant không phải quyền yêu cầu cấp scope mới tùy ý.

Theo OAuth 2.0, scope được yêu cầu khi refresh không được vượt quá scope đã được cấp trong authorization grant ban đầu. AS có thể trả scope giống hoặc hẹp hơn theo policy.

Ví dụ ban đầu:

```json
{
  "access_token": "A1",
  "refresh_token": "R1",
  "scope": "orders.read orders.write"
}
```

Khi refresh, client chỉ được tiếp tục sử dụng scope đã được cấp theo grant. Nếu response mới chỉ có:

```json
{
  "access_token": "A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

client không được giả định `orders.write` vẫn tồn tại. Các request POST cần quyền write phải xử lý 403 hoặc authorization state mới.

### 11.1. Audience/resource binding

Nếu AS hỗ trợ resource indicators hoặc audience-specific access tokens, refresh token có thể được gắn với resource/grant. Client không nên dùng refresh token của một API để xin token cho resource không được phép.

Resource Server chỉ kiểm tra access token được cấp cho **chính resource của nó**. Nó không nên chấp nhận refresh token rồi cố suy ra resource cần cấp.

### 11.2. Tenant binding

Trong multi-tenant application, refresh token/grant có thể thuộc một issuer, tenant hoặc client context. BFF phải giữ association này khi refresh. Không dùng refresh token của tenant A để xin access token rồi áp dụng vào tenant B chỉ vì subject/email trùng nhau.

## 12. Public client, confidential client và nơi lưu refresh token

### 12.1. Confidential client

Một server-side BFF có thể giữ client secret hoặc private key theo cơ chế đăng ký. Refresh token thường được lưu server-side và liên kết với user session/authorized client.

Biện pháp bảo vệ:

- Secret manager/KMS cho client credential.
- Mã hóa refresh token khi lưu trữ.
- Hạn chế quyền đọc token store.
- Không trả refresh token cho browser nếu BFF có thể quản lý server-side.
- Redact token khỏi logs/traces/errors.
- Xóa/revoke token khi logout hoặc grant bị thu hồi theo policy.
- Bảo vệ backup/export và database administrator access.

### 12.2. Public client

SPA hoặc native mobile app không thể giữ client secret như bí mật server-side. Khi public client nhận refresh token:

- AS nên áp dụng rotation hoặc sender-constrained refresh token theo security policy.
- Client cần lưu token trong storage phù hợp với platform và threat model.
- Native app nên dùng OS-provided secure storage.
- SPA cần cân nhắc BFF để giảm việc refresh token dài hạn nằm trong JavaScript runtime.
- Nếu SPA lưu token phía browser, XSS có thể đọc token từ storage accessible cho script; HttpOnly cookie/BFF có tradeoff khác và phải xử lý CSRF/session security.

Không copy client secret vào frontend bundle, mobile source hoặc environment variable build-time rồi gọi đó là confidential client.

### 12.3. Tránh lưu refresh token trong localStorage như mặc định

`localStorage` tồn tại lâu và có thể bị JavaScript trên origin đọc. Nếu ứng dụng có XSS, refresh token có thể bị đánh cắp và dùng từ nơi khác, đặc biệt nếu token không sender-constrained.

BFF pattern thường giữ refresh token ở server và browser chỉ có session cookie được bảo vệ. Tuy nhiên BFF vẫn cần CSRF defense, cookie Secure/HttpOnly/SameSite phù hợp, session lifecycle và logout/revocation.

Không có một lựa chọn storage đúng cho mọi client; quyết định cần dựa trên platform, XSS/CSRF threat model, token lifetime và khả năng sender-constraining.

## 13. Sender-constrained refresh token: DPoP và mTLS

Refresh token dạng Bearer có thể bị người lấy cắp replay từ thiết bị khác. OAuth 2.0 Security BCP khuyến nghị bảo vệ refresh token của public clients bằng **rotation** hoặc **sender-constraining**.

### 13.1. mTLS-bound tokens

Với mutual TLS, AS có thể gắn token với certificate của client. Khi refresh, client cần chứng minh sở hữu private key/certificate tương ứng. Một attacker chỉ lấy được token string có thể không dùng được token nếu không có key material.

mTLS phù hợp hơn với workload/server environments có khả năng quản lý certificate và private keys.

### 13.2. DPoP

**Demonstrating Proof of Possession (DPoP)** dùng một key pair phía client và proof JWT cho từng request theo protocol. Token được ràng buộc với public key thumbprint. Với token endpoint/resource request, client gửi DPoP proof theo quy tắc DPoP.

DPoP giảm khả năng replay token string đơn lẻ nếu attacker không có private key. Tuy nhiên:

- Private key phía client vẫn phải được bảo vệ.
- Proof phải có method/URL/time/nonce claims theo protocol.
- AS và Resource Server phải hỗ trợ DPoP.
- Không tự thêm header tên DPoP rồi coi đã sender-constrained.
- DPoP không thay thế scope, audience, issuer hoặc object authorization.

### 13.3. Sender constraint không phải thay refresh token rotation trong mọi trường hợp

Rotation và sender-constraining là hai biện pháp khác nhau. Tùy threat model, AS có thể áp dụng một hoặc kết hợp. Cần hiểu chính sách provider và test behavior reuse/rotation thực tế.

## 14. Spring Security Resource Server: chỉ xác thực access token

### 14.1. JWT Resource Server

Ví dụ cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

Security chain WebFlux:

```java
@Configuration
@EnableWebFluxSecurity
public class OrdersResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Resource Server kiểm tra access token bằng decoder. Không có `refreshToken()` ở đây vì Resource Server không phải nơi quản lý refresh grant của inbound caller.

### 14.2. Opaque token Resource Server

Cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

WebFlux chain:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Resource Server gửi **access token** tới introspection endpoint. Client credential trong YAML là credential **của Resource Server để gọi AS introspection**, không phải refresh token của API caller.

### 14.3. Không thêm refresh endpoint vào Resource Server chỉ để sửa 401

Một endpoint tự viết kiểu:

```java
@PostMapping("/api/refresh")
public Mono<TokenResponse> refresh(@RequestBody RefreshRequest request) {
    // Anti-pattern nếu đây chỉ là Resource Server.
    return tokenEndpointClient.exchange(request.refreshToken());
}
```

có thể biến Orders API thành một token broker không được thiết kế, làm lộ refresh token và nhập nhằng client identity. Nếu ứng dụng là BFF và có nhiệm vụ quản lý authorized client, hãy dùng OAuth2 Client subsystem với session/client binding và endpoint BFF được thiết kế riêng. Không đặt refresh grant chung vào API nghiệp vụ.

## 15. Khi backend là BFF/OAuth2 Client: Spring quản lý refresh token outbound

Có một trường hợp hợp lệ: ứng dụng Spring vừa bảo vệ inbound web/API vừa gọi downstream services thay mặt user. Khi đó nó có thể đóng vai trò OAuth2 Client.

Ví dụ:

```text
Browser
  |
  | session cookie
  v
BFF (OAuth2 Client)
  |
  | access token A1
  v
Orders downstream API (Resource Server)
  |
  | 401 invalid_token
  v
BFF / OAuth2AuthorizedClientManager
  |
  | refresh token R1 -> Authorization Server
  v
Authorization Server
  |
  | access token A2 (+ rotated refresh token R2)
  v
BFF
  |
  | retry downstream request with A2
  v
Orders downstream API
```

Trong kiến trúc này, BFF sở hữu authorized-client state đã được tạo từ OAuth login/authorization grant. Spring OAuth2 Client có thể quản lý refresh flow cho outbound request.

**Đây là refresh token của BFF's authorized client**, không phải refresh token được gửi bởi caller vào Resource Server endpoint.

### 15.1. Dependencies

Ví dụ Spring WebFlux application:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Nếu ứng dụng cũng nhận access token inbound để bảo vệ API, thêm Resource Server starter và cấu hình hai vai trò theo route/chain phù hợp.

### 15.2. Client registration

Ví dụ cấu hình OAuth client:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-bff:
            provider: company-idp
            client-id: ${ORDERS_BFF_CLIENT_ID}
            client-secret: ${ORDERS_BFF_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
              - offline_access
        provider:
          company-idp:
            issuer-uri: https://login.example.com
```

`offline_access` là scope được một số OIDC providers sử dụng để yêu cầu quyền cấp refresh token. Hành vi consent và phát hành refresh token phụ thuộc OIDC/provider policy; chỉ khai báo scope không bảo đảm AS luôn trả refresh token.

### 15.3. ReactiveOAuth2AuthorizedClientManager

Một cấu hình reactive minh họa:

```java
package com.example.bff.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
public class OAuth2ClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Manager này cần được gọi trong đúng **server web request/session context** để load và save authorized client tương ứng. Với background service không có server request, dùng manager/service variant phù hợp như `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và storage/identity context tương ứng.

`refreshToken()` bật provider xử lý refresh khi authorized client có refresh token và access token cần được authorize/renew theo provider rules. Nó **không** làm Resource Server tự refresh inbound token.

### 15.4. WebClient dùng authorized client manager

Ví dụ WebClient filter function:

```java
package com.example.bff.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamWebClientConfiguration {

    @Bean
    WebClient ordersWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager
            );

        oauth.setDefaultClientRegistrationId("orders-bff");

        return WebClient.builder()
            .filter(oauth)
            .baseUrl("https://orders.internal.example")
            .build();
    }
}
```

Cấu hình cụ thể phụ thuộc cách lưu authorized client và cách gắn principal/registration ID vào request. Cần bảo đảm request outbound dùng đúng user/session/client identity. Không dùng một authorized client của user A cho request của user B.

### 15.5. Khi refresh thất bại trong OAuth2 Client

BFF cần xử lý các trường hợp:

- Refresh token hết hạn hoặc revoked: authorized client có thể bị remove và user cần đăng nhập lại.
- Client authentication lỗi: sửa registration/secret, không đổ lỗi cho user.
- AS outage: phản ánh dependency failure, không tự tạo access token.
- Rotation thành công: lưu refresh token mới theo authorized-client persistence policy.
- Nhiều request đồng thời: phối hợp để không reuse refresh token đã rotation.
- Downstream 403: không mặc định refresh; đó thường là quyền thiếu.

Spring OAuth2 Client cung cấp provider/manager plumbing, nhưng **không loại bỏ nhu cầu kiểm soát storage, concurrency, failure handling và session binding**.

## 16. Servlet OAuth2 Client cũng có authorized-client manager

Trong Servlet stack, các lớp tương ứng thường gồm:

- `OAuth2AuthorizedClientManager`.
- `DefaultOAuth2AuthorizedClientManager` cho web request context.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` cho service/background context.
- `OAuth2AuthorizedClientProviderBuilder` với `refreshToken()`.
- `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService` để lưu authorized client.

Ví dụ cấu hình provider:

```java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .build();

    DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
            registrations,
            authorizedClients
        );

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Khi manager được gọi để authorize outbound client, nó có thể dùng refresh token đã lưu để lấy access token mới. Đây là **OAuth2 Client responsibility** của backend, tách khỏi inbound Resource Server authentication.

## 17. Client xử lý 401 và refresh trong ứng dụng như thế nào?

Một client có thể dùng logic khái niệm:

```text
send API request with current access token

if response is success:
    return response

if response is 401 and request has a refreshable grant:
    refresh once using AS token endpoint
    atomically store new token pair
    retry request once with new access token
    if retry still fails:
        surface error; do not loop

if response is 403:
    surface authorization error; do not refresh by default

if response is 5xx/network:
    apply API retry policy; do not assume token expired
```

### 17.1. Ví dụ pseudocode

```javascript
async function callOrdersApi(request, tokenStore, authClient) {
  const current = await tokenStore.load();

  const first = await sendRequest(request, current.accessToken);

  if (first.status !== 401) {
    return first;
  }

  // Single-flight lock phải được triển khai theo session/grant.
  const updated = await authClient.refreshIfNeeded(current);

  if (!updated) {
    throw new Error("REAUTHENTICATION_REQUIRED");
  }

  // Chỉ retry một lần; request có side effect cần idempotency policy.
  const second = await sendRequest(request, updated.accessToken);

  if (second.status === 401) {
    throw new Error("NEW_ACCESS_TOKEN_REJECTED");
  }

  return second;
}
```

Đây là pseudocode, không phải production-ready token storage hoặc lock implementation. Nó minh họa việc **client** điều phối refresh và giới hạn retry. Cần bảo vệ token store, xử lý rotation, multi-tab/multi-instance concurrency, cancellation và request idempotency.

### 17.2. Không refresh mọi 401 không phân biệt

Client có thể chỉ refresh khi có bằng chứng lỗi access token phù hợp. Nếu server trả 401 vì wrong audience, unknown issuer hoặc malformed token, refresh cùng grant có thể trả token cùng lỗi. Cần phân biệt cấu hình sai với hết hạn/revocation.

### 17.3. Không retry vòng lặp

Một pattern lỗi:

```text
401 -> refresh -> retry -> 401 -> refresh -> retry -> ...
```

Đặt giới hạn rõ: một refresh attempt cho một request/token generation, sau đó trả lỗi lên tầng ứng dụng. Nếu token mới bị từ chối, cần điều tra issuer/audience/clock/client configuration hoặc session state.

## 18. Refresh token và nhiều tab/browser requests

SPA có thể mở nhiều tab. Một tab refresh R1 thành R2, tab khác vẫn giữ R1 trong memory. Khi tab thứ hai refresh, AS có thể nhận reuse.

Các lựa chọn thiết kế:

- BFF quản lý refresh token server-side, browser chỉ có session cookie.
- Single-flight coordinator chia sẻ trạng thái refresh giữa tabs nếu SPA tự quản lý token.
- BroadcastChannel hoặc coordination mechanism phù hợp nhưng không gửi raw refresh token vào nơi không an toàn.
- Token store có generation/version và atomic update.
- Khi phát hiện stale token generation, tab reload token pair mới thay vì refresh token cũ.
- Nếu reuse detection revoke token family, chuyển sang reauthentication và hiển thị trạng thái rõ.

Không cho mỗi component trong SPA tự tạo một refresh timer độc lập. Centralized auth client giảm race conditions.

## 19. Refresh token và service-to-service

Với `client_credentials`, một workload thường xin access token bằng client authentication mỗi khi cần token mới. Theo OAuth 2.0, refresh token thường không được cấp cho client credentials grant; client có thể xin access token mới bằng chính client credentials khi token hết hạn.

Ví dụ:

```http
POST /oauth2/token HTTP/1.1
Authorization: Basic BASE64_SERVICE_CLIENT
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders.export
```

Đây không phải refresh token grant. Service identity tự xác thực với AS bằng credential của service, hoặc dùng private_key_jwt/mTLS theo registration. Không tạo refresh token dài hạn nếu grant/policy không yêu cầu.

### 19.1. Phân biệt service token và user delegated token

| Trường hợp | Token đại diện | Cách lấy token mới |
|---|---|---|
| Authorization Code user session | User grant/client | Refresh token nếu AS cấp và còn hợp lệ |
| Client Credentials | Service client | Xin access token mới bằng client authentication |
| Device Authorization | User grant/client | Refresh theo policy nếu AS cấp |
| Token Exchange | Subject/actor token theo grant | Thực hiện token exchange theo contract, không giả refresh grant |
| On-Behalf-Of/provider-specific | User/service delegation | Theo giao thức và policy của provider |

Không dùng refresh token của một user để tạo service identity rộng hơn. Cần phân biệt actor, subject, client và delegation.

## 20. OIDC và scope offline_access

Trong OpenID Connect, `offline_access` là scope được dùng trong một số trường hợp để yêu cầu quyền truy cập offline và thường liên quan việc cấp refresh token. Việc cấp còn phụ thuộc:

- Provider có hỗ trợ scope này không.
- Client registration và grant type.
- Consent/prompt requirements của provider.
- Chính sách phiên đăng nhập và risk.
- Client có được phép giữ refresh token hay không.

Không giả định chỉ cần thêm:

```yaml
scope:
  - openid
  - offline_access
```

là mọi OIDC Provider chắc chắn trả refresh token. Client phải kiểm tra token response và xử lý trường hợp không có refresh token.

### 20.1. ID token không phải access token

OIDC client có thể nhận ID token cùng access token. ID token chứng minh authentication event/claims cho client theo OIDC; nó không phải credential thay thế access token để gọi Orders API.

Tương tự, refresh token không phải ID token và không được gửi tới Resource Server. Ba token có vai trò riêng:

| Token | Đối tượng sử dụng chính | Mục đích |
|---|---|---|
| ID token | OIDC client | Thông tin authentication của user |
| Access token | Resource Server | Truy cập API |
| Refresh token | Authorization Server token endpoint | Xin access token mới |

## 21. Thu hồi refresh token và token endpoint revocation

RFC 7009 định nghĩa OAuth 2.0 Token Revocation endpoint. Client có thể gửi token tới AS để yêu cầu thu hồi theo policy.

Ví dụ:

```http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_CREDENTIALS

token=REFRESH_TOKEN_VALUE&
token_type_hint=refresh_token
```

`token_type_hint` là gợi ý cho AS, không phải bằng chứng. AS có thể thu hồi token liên quan theo implementation/policy.

### 21.1. Client cần làm gì khi logout?

- Xóa local access/refresh token state.
- Gọi revocation endpoint nếu flow/policy yêu cầu và client có quyền.
- Kết thúc application session.
- Với OIDC, gọi end-session/logout endpoint nếu được cấu hình và cần thiết.
- Xóa BFF authorized-client record.
- Xử lý cache/session ở các downstream components theo policy.

Xóa token khỏi browser **không tự thu hồi token ở AS**. Ngược lại, revoke refresh token **không nhất thiết** làm access JWT đã phát hành hết hiệu lực ngay lập tức ở Resource Server offline.

### 21.2. Resource Server có gọi revocation endpoint không?

Thông thường **không**. Resource Server xác minh access token inbound. Nó không sở hữu refresh token và không nên revoke grant của caller chỉ vì một request bị 401/403.

Nếu Resource Server phát hiện abuse, nó có thể phát audit/security event hoặc gọi một administrative workflow được thiết kế riêng. Việc revoke grant thuộc quyền quản trị/AS policy, không phải phản ứng tùy tiện trong filter xác thực request.

## 22. Tác động của refresh token revocation lên JWT và opaque access token

### 22.1. JWT access token

JWT có thể được xác minh offline bằng public key. Nếu AS revoke refresh token, JWT access token đã phát hành vẫn có thể hợp lệ đến `exp` nếu không có cơ chế kiểm tra trạng thái bổ sung.

Các cách giảm cửa sổ rủi ro:

- Access token lifetime ngắn hợp lý.
- Audience/scope tối thiểu.
- Key/issuer validation chuẩn.
- Denylist hoặc session/token-version lookup cho use case cần revoke sớm.
- Token introspection thay vì offline JWT khi cần trạng thái tập trung, với tradeoff latency/availability.

### 22.2. Opaque access token

Resource Server thường introspect opaque token. AS có thể trả `active=false` sau khi access token/grant bị thu hồi, tùy trạng thái và chính sách AS.

Nếu Resource Server cache introspection result, revocation có thể bị trễ tới khi cache hết hạn hoặc invalidated. TTL cache phải cân bằng latency, capacity và acceptable revocation delay.

### 22.3. Không dùng refresh token để kiểm tra access token

Một lỗi kiến trúc là khi JWT decoder trả invalid, Resource Server gọi token endpoint với refresh token do caller gửi để “xem còn session không”. Điều này:

- Gửi refresh credential tới sai service boundary.
- Có thể tạo access token mới ngoài ý muốn.
- Không giải quyết xác thực request ban đầu.
- Làm sai semantics 401/403.
- Tạo nguy cơ replay và token leakage.

Resource Server chỉ dùng **access-token validation/introspection contract**.

## 23. Bảo vệ refresh token trong logs, storage và transport

Refresh token là credential nhạy cảm. Cần bảo vệ trên mọi tầng:

### 23.1. Transport

- Gửi tới token endpoint qua HTTPS.
- Xác minh certificate và hostname.
- Không gửi refresh token qua URL/query.
- Không gửi trong API business request.
- Không follow redirect tới host ngoài trust policy với request mang token.
- Dùng client authentication đúng registration.
- Không gửi token tới issuer/endpoint lấy từ input không tin cậy.

### 23.2. Storage

- Server-side store có access control và encryption at rest.
- OS secure storage cho native apps.
- BFF session binding và token store server-side nếu phù hợp.
- Hạn chế bản sao trong memory, backups, crash dumps và debugging tools.
- Xóa/rotate token cũ theo lifecycle.
- Phân tách token của từng user/client/tenant.

### 23.3. Logs và telemetry

Không log:

```text
refresh_token
access_token
Authorization: Bearer ...
Authorization: Basic ...
Cookie/session identifiers
raw token endpoint request/response
```

Có thể ghi metadata không nhạy cảm như registration ID, grant outcome, error code, latency, rotation event ID hoặc token family ID đã được xử lý phù hợp. Tránh dùng token raw hoặc subject PII làm metric label.

### 23.4. Không đưa refresh token vào frontend error

Nếu BFF gặp `invalid_grant`, browser chỉ cần biết phiên cần đăng nhập lại hoặc thao tác không thể tiếp tục. Không trả refresh token, client secret, raw AS error details hoặc nội dung introspection ra frontend.

## 24. Kiểm thử vòng đời refresh token

Cần tách test theo từng vai trò.

### 24.1. Resource Server tests

Resource Server test cần chứng minh:

- Không có access token trên endpoint bảo vệ → 401 Bearer.
- Access JWT hết hạn → 401 invalid_token.
- JWT sai issuer/audience/signature → từ chối.
- Opaque token `active=false` → 401.
- Access token hợp lệ thiếu scope → 403.
- Refresh token gửi nhầm tới API → bị từ chối như access token không hợp lệ.
- Resource Server **không gọi token endpoint** khi access token inbound hết hạn.
- Resource Server không ghi token vào log/response.
- API không redirect HTML login ngoài hợp đồng.

### 24.2. OAuth client tests

Client/BFF test cần chứng minh:

- Access token hết hạn kích hoạt refresh grant đúng một lần theo policy.
- Refresh request gửi tới đúng AS token endpoint.
- Confidential client authentication được thực hiện đúng.
- Public client không gửi client secret giả.
- Token response được parse đúng.
- Refresh token mới được lưu nếu AS rotation.
- Refresh token cũ không được dùng lại sau rotation thành công.
- `invalid_grant` chuyển client sang reauthentication phù hợp.
- `invalid_client` được phân loại thành lỗi cấu hình.
- Timeout có kết quả không rõ được xử lý thận trọng.
- Concurrent requests không đồng thời reuse một rotating refresh token.
- 403 không gây refresh loop.
- API retry chỉ một lần và tôn trọng idempotency.

### 24.3. Authorization Server tests

AS test cần kiểm tra:

- Refresh token thuộc đúng client/grant.
- Token hết hạn hoặc revoked bị từ chối.
- Rotation phát token mới và vô hiệu hóa token cũ.
- Reuse detection thực thi theo policy.
- Scope/resource không được mở rộng trái phép.
- Client authentication bắt buộc được kiểm tra.
- Sender-constrained binding được xác minh nếu bật.
- Logout/revocation cập nhật token family/grant.
- Token family revoke có tác động được định nghĩa rõ.
- Audit event không chứa raw credential.

### 24.4. Ma trận kiểm thử tổng hợp

| Kịch bản | Component chịu trách nhiệm | Kết quả mong đợi |
|---|---|---|
| Access token A1 hợp lệ | Resource Server | Cho phép theo scope/policy |
| Access token hết hạn | Resource Server | 401 Bearer invalid_token |
| Client nhận 401 phù hợp | OAuth client | Có thể thử refresh một lần |
| Refresh token R1 hợp lệ | Authorization Server | Phát access token mới |
| Rotation bật | AS + client | R1 bị thay bằng R2; client lưu R2 |
| R1 bị dùng lại | AS | Reuse detection/revoke theo policy |
| Refresh token hết hạn | AS | invalid_grant; client cần authorization mới |
| Client secret sai | AS | invalid_client; sửa cấu hình client |
| Refresh scope vượt grant | AS | Không cấp quyền vượt phạm vi |
| Token mới thiếu scope | API/client | Authorization theo scope mới, có thể 403 |
| Refresh timeout sau khi AS xử lý | Client + AS policy | Không retry mù quáng R1 |
| Hai request refresh đồng thời | Client coordination | Single-flight/atomic update |
| Refresh token gửi tới Orders API | Resource Server | 401; không gọi token endpoint |
| Revoke refresh token | AS | Không cấp access token mới từ grant đó |
| JWT access token đã phát hành | Resource Server | Còn hiệu lực tới exp nếu không có status check bổ sung |
| Opaque access token đã revoke | AS introspection + RS | active=false theo policy |
| Logout BFF | BFF + AS | Xóa local state và revoke theo contract |

## 25. Ví dụ kiểm thử fake Authorization Server

Một integration test client có thể dùng mock HTTP server để mô phỏng token endpoint:

```text
POST /oauth2/token
  grant_type=refresh_token
  refresh_token=R1
  Authorization: Basic ...

Response:
  access_token=A2
  refresh_token=R2
  expires_in=600
```

Sau đó kiểm tra:

1. Client gửi đúng `grant_type`.
2. Refresh token R1 được gửi trong form body, không phải URL.
3. Client authentication đúng phương thức.
4. Token response có `Cache-Control: no-store`/`Pragma: no-cache` theo AS.
5. Client persist A2/R2.
6. Request outbound tiếp theo dùng A2.
7. R1 không xuất hiện trong request sau rotation.
8. Một lỗi `invalid_grant` xóa/đánh dấu authorized client cần reauth theo policy.
9. Hai request đồng thời chỉ tạo một refresh operation cho cùng grant/token generation.
10. Token không xuất hiện trong logs/assertion output.

Đối với Resource Server, fake token endpoint có thể được cấu hình để **đếm số request**. Khi gửi access token hết hạn tới API, test phải chứng minh Resource Server không gọi endpoint refresh; chỉ decoder/introspector của access token hoạt động theo cấu hình.

## 26. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| API trả 401, client không refresh | Client không giữ refresh token hoặc policy không cho refresh | Kiểm tra grant/token response và client state |
| API nhận refresh token nhưng trả 401 | Caller gửi sai loại token | Sửa client: chỉ gửi access token tới API |
| Refresh trả invalid_grant | Hết hạn, revoked, reuse hoặc sai client/grant | Kiểm tra token family, rotation và session |
| Refresh trả invalid_client | Client secret/auth method sai | Kiểm tra registration/secret rotation |
| Sau refresh vẫn 403 | Token mới thiếu scope/quyền | Kiểm tra AS grant, scope response và domain policy |
| Nhiều request làm user logout bất ngờ | Refresh rotation race/reuse detection | Single-flight và atomic token update |
| Timeout refresh rồi mọi lần sau invalid_grant | AS có thể đã rotate nhưng response mất | Recovery policy; không retry mù token cũ |
| Logout xong JWT vẫn gọi API được | Access JWT còn hiệu lực offline | TTL ngắn, introspection hoặc revoke strategy |
| BFF refresh token user A cho request user B | Authorized-client/session binding sai | Ràng buộc token store theo principal/session |
| Resource Server gọi token endpoint | Trộn vai trò OAuth client và Resource Server | Chuyển refresh về client/BFF subsystem |
| Log có refresh token | HTTP logging/debug capture quá rộng | Redact và rotate/revoke token bị lộ |
| SPA nhiều tab refresh thất bại | Shared token state không đồng bộ | BFF hoặc cross-tab coordination |
| Token response không có refresh_token | AS không cấp theo policy/consent | Xử lý không có refresh grant; không giả định luôn có |
| Refresh grant không đổi scope | Client kỳ vọng AS tự cấp thêm quyền | Authorization/consent flow mới nếu cần scope rộng hơn |

## 27. Những anti-pattern cần tránh

### 27.1. Gửi refresh token trong Authorization header tới API

Sai vì API cần access token dành cho resource. Refresh token chỉ gửi tới AS token endpoint.

### 27.2. Để Resource Server tự refresh access token của caller

Sai ranh giới vai trò và có thể làm lộ refresh token, client credential hoặc grant.

### 27.3. Refresh sau mọi 401/403

Sai vì issuer/audience/signature error hoặc insufficient scope không tự sửa được bằng refresh.

### 27.4. Retry refresh vô hạn sau timeout

Sai vì AS có thể đã rotation và vô hiệu hóa token cũ dù response bị mất.

### 27.5. Giữ refresh token cũ sau rotation thành công

Sai vì có thể kích hoạt reuse detection và thu hồi token family.

### 27.6. Mỗi request tự refresh độc lập

Sai vì race condition; dùng single-flight và atomic update theo grant/session.

### 27.7. Lưu refresh token vào log/localStorage mặc định

Sai vì tăng khả năng credential theft và replay. Chọn storage theo client type/threat model.

### 27.8. Dùng client secret trong SPA

Sai vì secret trong frontend bundle không còn là bí mật.

### 27.9. Coi logout là revoke token tự động

Sai; cần token revocation/session termination theo contract.

### 27.10. Cho rằng refresh token revoke sẽ vô hiệu JWT access token ngay

Sai nếu Resource Server chỉ xác minh JWT offline. Cần chiến lược revoke access token riêng.

### 27.11. Dùng refresh token của user làm service identity

Sai vì lẫn user delegation với workload identity/client credentials.

### 27.12. Chấp nhận ID token làm access token khi refresh

Sai vì ID token, access token và refresh token có audience/mục đích khác nhau.

## 28. Checklist thiết kế và vận hành

| Câu hỏi | Yêu cầu |
|---|---|
| Ai gửi access token tới Resource Server? | OAuth client |
| Ai gửi refresh token? | OAuth client tới AS token endpoint |
| Resource Server có refresh inbound token không? | **Không** |
| AS có kiểm tra client/grant/token state không? | **Có** |
| Refresh token có gắn với client/grant/session không? | **Có** |
| Có expiry/idle timeout/absolute lifetime không? | Được định nghĩa rõ |
| Public client có rotation hoặc sender constraint không? | Theo OAuth Security BCP |
| Rotation response được client lưu atomically không? | **Có** |
| Có reuse detection không? | Theo AS security policy |
| Có single-flight khi concurrent refresh không? | **Có** |
| Timeout có thể tạo trạng thái kết quả không rõ không? | **Có recovery policy** |
| 403 có kích hoạt refresh mặc định không? | **Không** |
| Logout có revoke refresh token/grant không? | Theo contract rõ |
| JWT access token sau refresh-token revoke có còn dùng được không? | Xác định theo TTL/status-check strategy |
| Refresh token có xuất hiện trong logs/traces/URL không? | **Không** |
| BFF authorized client có gắn đúng user/session không? | **Có** |
| Resource Server test có chứng minh không gọi refresh endpoint không? | **Có** |
| Có test token reuse, rotation và race conditions không? | **Có** |

## 29. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `6 Refreshing an Access Token, client authentication, refresh token grant và scope.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation, sender-constrained tokens và public clients.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint và token revocation semantics.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi access token tới Resource Server và Bearer errors.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token bằng proof-of-possession.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS và certificate-bound tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC scopes, authorization code flow và `offline_access`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized client, client manager và refresh-token provider.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): `ReactiveOAuth2AuthorizedClientManager` và WebClient integration.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): xác minh access token inbound.
- [Spring Security — Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): Bearer authentication trong WebFlux.

**Kết luận:** Refresh token là credential của **OAuth client đối với Authorization Server**. Client gửi nó tới token endpoint theo refresh grant; AS xác minh client/grant, kiểm tra expiry/revocation/reuse và phát access token mới theo policy. **Resource Server chỉ xác minh access token** và trả 401/403 theo hợp đồng API; nó không nhận refresh token của caller và không tự refresh token đó. Nếu một backend đồng thời là BFF/OAuth client, Spring OAuth2 Client có thể quản lý refresh cho **authorized client outbound của chính backend**, với storage, session binding, rotation và concurrency được kiểm soát. Tách đúng ba vai trò giúp vòng đời token có thể audit, thu hồi và vận hành an toàn.
