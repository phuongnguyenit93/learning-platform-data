# Điểm cuối revoke

Một người dùng đăng nhập ứng dụng quản lý hóa đơn, cấp quyền để ứng dụng đọc hóa đơn qua Invoice API. Sau đó, người dùng chọn **Ngắt kết nối ứng dụng**. Ứng dụng đã xóa access token và refresh token khỏi bộ nhớ của mình. Liệu như vậy có bảo đảm các token cũ không còn dùng được tại Authorization Server và Resource Server?

**Không.** Xóa token ở phía client chỉ xóa **một bản sao**. Token có thể đã bị đánh cắp, được lưu ở một thiết bị khác hoặc vẫn nằm trong bộ nhớ của ứng dụng khác. Trong OAuth 2.0, client có thể yêu cầu **Authorization Server (AS) thu hồi token** thông qua **token revocation endpoint**, thường gọi ngắn gọn là **điểm cuối revoke**, theo **RFC 7009**. Việc AS thu hồi thành công có thể ngăn **refresh token** tiếp tục xin access token mới; còn access token đang tồn tại có bị Resource Server (RS) từ chối **ngay lập tức** hay không tùy chính sách AS và cách RS xác minh token.

Đây là điểm quan trọng của chương **OAuth2 roles** trong module **Security Token Security Fundamentals**: **client gửi yêu cầu thu hồi, AS là bên có thẩm quyền xử lý và RS phải thực thi trạng thái token theo cơ chế mà hệ thống đã thiết kế**. Điểm cuối revoke không thay thế kiểm chữ ký, `iss`, `aud`, `exp`, `scope`, authorization trên từng tài nguyên hay phương án phòng chống token bị đánh cắp và phát lại.

## 1. Điểm cuối revoke nằm ở đâu trong các vai trò OAuth 2.0?

Trong OAuth 2.0, một request có liên quan đến token có thể đi đến những thành phần khác nhau. Đừng nhầm việc “gửi bearer token tới API” với “gửi token để thu hồi”.

| Vai trò | Nhiệm vụ chính | Quan hệ với revoke |
|---|---|---|
| **Resource Owner** | Người dùng/chủ thể có thể cấp quyền cho client theo luồng phù hợp | Có thể yêu cầu ngắt kết nối hoặc thu hồi quyền qua giao diện được hệ thống cung cấp |
| **Client** | Ứng dụng sử dụng grant/token để gọi API | Gửi **revocation request** tới AS, đồng thời dọn trạng thái token/session phía mình |
| **Authorization Server (AS)** | Xác thực client, cấp token, quản lý grant và trạng thái token | **Tiếp nhận/kiểm soát việc thu hồi**, xác định các token/grant liên quan cần vô hiệu |
| **Resource Server (RS)** | Nhận access token để bảo vệ API | **Từ chối access token** khi đã hết hạn, không còn active hoặc bị chặn theo chính sách RS |
| **Identity Provider / OIDC Provider** | Cung cấp xác thực và chức năng OIDC | Có thể đồng thời là AS; có thêm cơ chế logout/SSO riêng, không đồng nghĩa với RFC 7009 |

Ví dụ luồng tổng quát:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Expense App (OAuth client)
    participant AS as Authorization Server
    participant RS as Invoice API (Resource Server)
    U->>C: Ngắt kết nối tài khoản
    C->>AS: POST /oauth2/revoke, token=refresh_token
    AS->>AS: Kiểm client, binding, token và chính sách grant
    AS->>AS: Thu hồi refresh token/grant/token liên quan
    AS-->>C: HTTP 200 (không xác nhận token từng active)
    C->>C: Xóa token và phiên ứng dụng phù hợp
    C->>RS: Nếu còn gửi access token cũ
    RS->>RS: Kiểm exp, audience, scope và trạng thái theo policy
    RS-->>C: 401 nếu access token bị chặn/hết hạn; nếu không, có thể vẫn được chấp nhận
~~~

**Đọc sơ đồ đúng cách:** Kết quả `200` ở `/revoke` có nghĩa yêu cầu thu hồi được xử lý thành công theo hợp đồng endpoint. Nó **không phải phép thử token có tồn tại hay đã được cấp trước đó**, và cũng không tự chứng minh mọi bản sao access token đã bị tất cả RS từ chối trong cùng một phần nghìn giây.

### “Revoke” có phải là một OAuth role không?

Không. **OAuth roles** là resource owner, client, authorization server và resource server. **Revocation endpoint** là **một giao diện do AS cung cấp** để client yêu cầu thu hồi token theo RFC 7009. Việc đặt bài ở chương “OAuth2 roles” giúp xác định **ai chịu trách nhiệm** trong quá trình thu hồi, không tạo thêm một role thứ năm tên “Revoker”.

## 2. Hợp đồng HTTP cơ bản theo RFC 7009

RFC 7009 chuẩn hóa **OAuth 2.0 Token Revocation**. Điểm cuối này được AS công bố/cấu hình cho client; **không có một đường dẫn cố định bắt buộc**. Nó có thể là `/oauth2/revoke`, `/connect/revocation` hoặc đường dẫn khác tùy AS.

Địa chỉ revocation endpoint có thể được công bố qua **Authorization Server Metadata (RFC 8414)** dưới trường `revocation_endpoint` khi AS cung cấp metadata. Client nên lấy cấu hình từ nguồn AS đáng tin, không tự tạo URL từ email hoặc HTTP input.

### Request chuẩn

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-client-authentication>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<redacted-refresh-token>&token_type_hint=refresh_token
~~~

Đặc tính chính:

- **Phương thức:** HTTP `POST` qua **HTTPS/TLS** được xác minh đúng.
- **Content type:** `application/x-www-form-urlencoded` cho các tham số theo RFC.
- **`token`:** tham số **bắt buộc**, chứa giá trị token client muốn thu hồi. Đây là credential nhạy cảm; phải truyền an toàn, không đưa lên URL.
- **`token_type_hint`:** tham số **tùy chọn**, là gợi ý loại token để AS tìm kiếm hiệu quả hơn, thường `access_token` hoặc `refresh_token`.
- **Client authentication:** confidential client phải xác thực với AS theo phương thức đã đăng ký. Public client không thể giả vờ có client secret bí mật giống backend; AS áp dụng cách định danh/binding phù hợp với loại client.
- **Token ownership/client binding:** AS phải kiểm token có thuộc client/grant thích hợp cho request theo hợp đồng bảo mật, không cho client A tùy ý thu hồi token của client B.

**Không gửi refresh token tới Resource Server như bearer token.** Refresh token được sử dụng tại token endpoint/revocation endpoint của AS; còn resource API nhận **access token dành cho chính API** và xác minh theo token profile.

### `token_type_hint` chỉ là gợi ý, không phải bằng chứng

~~~text
token=<R1-redacted>&token_type_hint=refresh_token
~~~

`token_type_hint` không có tác dụng tự xác minh rằng R1 là refresh token, cũng không cấp quyền cho caller. AS cần xác định token thực bằng trạng thái/ký hiệu định danh đáng tin. Nếu hint không phù hợp nhưng token vẫn có thể thuộc loại khác mà AS hỗ trợ, AS phải xử lý theo quy tắc tìm kiếm của RFC, **không** lấy hint làm lý do bỏ qua kiểm client/binding.

Trong thiết kế triển khai, tránh trả một lỗi tiết lộ “token này thực ra là access token của người dùng X”. Một token bị đánh cắp có thể bị lợi dụng để dò hệ thống nếu endpoint tiết lộ quá nhiều trạng thái.

### Phản hồi thông thường

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Content-Length: 0
~~~

Theo **RFC 7009**, AS trả **HTTP 200** khi xử lý revocation request thành công, **kể cả nếu token trong request vốn không hợp lệ hoặc không tồn tại**, miễn request đủ điều kiện xác thực/ủy quyền khác. Điều đó giúp giảm khả năng dùng revoke endpoint như một “máy dò token nào đang active”.

Response `200` của revocation endpoint **không cần trả một token mới**. `Cache-Control: no-store` và không ghi response/request bí mật vào log là thực hành phù hợp khi endpoint xử lý credential nhạy cảm. **Không** tạo JSON như `{"revoked": true, "was_active": true}` chỉ để client dò trạng thái từng token.

## 3. Vì sao token không tồn tại cũng trả 200?

Giả sử một attacker gửi một chuỗi ngẫu nhiên:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <valid-client-auth-redacted>
Content-Type: application/x-www-form-urlencoded

token=never-issued-random-string&token_type_hint=access_token
~~~

Nếu AS trả:

~~~text
200 -> token từng tồn tại
404 -> token chưa từng tồn tại
409 -> token đã bị revoke
~~~

thì endpoint có thể trở thành **token status oracle**, làm lộ thông tin không cần thiết cho caller. RFC 7009 yêu cầu phản hồi thành công thống nhất ngay cả khi token không hợp lệ. Nếu cần **kiểm token đang hoạt động**, RS dùng cơ chế như **introspection (RFC 7662)** với kiểm soát truy cập thích hợp, không dùng `POST /revoke` để thăm dò.

### Nhưng 200 không có nghĩa mọi lỗi đều bị bỏ qua

Cần phân biệt:

| Tình huống | Ngữ nghĩa thích hợp |
|---|---|
| Client hợp lệ gửi token thuộc phạm vi được xử lý, AS thu hồi thành công | **HTTP 200** |
| Client hợp lệ gửi token **không tồn tại/đã bị thu hồi**, request vẫn hợp lệ | **HTTP 200**, không tiết lộ token đã từng active |
| Thiếu tham số `token` hoặc request sai định dạng | Lỗi request theo hợp đồng OAuth/HTTP, không coi là revocation thành công |
| Confidential client xác thực sai | Lỗi **client authentication**, chẳng hạn `invalid_client` theo OAuth; không trả 200 chỉ để che credential sai |
| Request không đáp ứng quyền client/token binding | Từ chối phù hợp; tránh tiết lộ chi tiết token thuộc ai |
| AS không hỗ trợ thu hồi một **loại token hợp lệ cụ thể** | Có thể trả `unsupported_token_type` theo RFC 7009 |
| Endpoint tạm thời không thể xử lý | Lỗi khả dụng phù hợp; client không được mặc định token đã bị revoke |

**Quy tắc tổng quát:** Giấu thông tin về tình trạng tồn tại/hiệu lực của token **không** đồng nghĩa bỏ qua xác thực client hoặc chính sách sở hữu token.

### Lỗi `unsupported_token_type`

RFC 7009 xác định thêm mã lỗi `unsupported_token_type` cho trường hợp AS không hỗ trợ revocation của **loại token cụ thể**, ví dụ AS hỗ trợ refresh token revocation nhưng không hỗ trợ access token revocation:

~~~http
HTTP/1.1 400 Bad Request
Cache-Control: no-store
Content-Type: application/json

{"error":"unsupported_token_type"}
~~~

Đừng sử dụng lỗi này như kênh tiết lộ token còn active hay token thuộc client khác. AS nên trả lỗi theo đúng hợp đồng giao thức, không tạo biến thể lỗi tùy tiện làm thay đổi semantics của RFC.

## 4. Revoke access token, refresh token hay cả grant?

**Tham số `token` nhận token cụ thể**, nhưng **phạm vi hiệu lực của hành động thu hồi** có thể rộng hơn token đó, tùy chính sách AS và chuẩn.

| Đối tượng client gửi | Tác động trực tiếp | Tác động tới token/grant liên quan |
|---|---|---|
| **Refresh token** | Ngăn refresh token đó tiếp tục được đổi | Theo RFC 7009, AS **nên** vô hiệu các access token dựa trên cùng authorization grant, trong giới hạn khả năng triển khai; có thể chấm dứt grant/refresh family theo policy |
| **Access token** | Đề nghị AS vô hiệu access token đó nếu AS hỗ trợ | AS **có thể** thu hồi refresh token liên quan theo chính sách; không mặc nhiên bắt buộc |
| **Token đã revoke/hết hạn** | Không tạo quyền mới; không làm token sống lại | Response thường vẫn 200 nếu request hợp lệ |
| **Token thuộc grant khác** | Không được tự động mở rộng theo một client không có quyền | AS cần kiểm client binding và chính sách phạm vi thu hồi |

Lưu ý: **“AS nên thu hồi access token khi refresh token bị revoke”** và **“mọi RS lập tức dừng chấp nhận access token”** là hai mệnh đề khác nhau. Với JWT tự xác minh offline, AS có thể đánh dấu grant đã revoke nhưng các RS không tra trạng thái hiện hành vẫn chấp nhận JWT cho tới `exp`. Hệ thống phải **thiết kế cơ chế truyền/kiểm trạng thái thực tế** nếu yêu cầu vô hiệu hóa tức thời.

### Hai cách hiểu phổ biến

~~~text
Tình huống 1: Client revoke R1 (refresh token)
  -> AS chặn đổi R1 thành access token mới.
  -> Theo policy, AS cũng vô hiệu các access token của grant.
  -> RS chỉ biết access token vô hiệu nếu có kiểm trạng thái phù hợp.

Tình huống 2: Client revoke A1 (access token)
  -> AS chặn A1 (nếu loại access token này được hỗ trợ revoke).
  -> R1 có thể còn dùng được hoặc bị thu hồi kèm, tùy policy.
  -> Không tự kết luận logout toàn bộ tài khoản.
~~~

Với hệ thống có **refresh token rotation**, một grant có thể được biểu diễn bằng **refresh token family**. Việc ngắt kết nối ứng dụng nên có chính sách rõ: revoke token hiện hành, revoke **family** của phiên, hay revoke **mọi family** của chủ thể? Các mức phạm vi này không giống nhau.

### Không dùng `scope` để quyết định quyền thu hồi token của client khác

Scope như `invoice:read` hoặc `payments:write` là phạm vi cho access token gọi resource API. Nó không tự cấp quyền quản trị revoke token của người dùng/client khác. Khả năng revoke token có được chấp nhận hay không phụ thuộc **client authentication, token binding, quyền quản trị/consent theo thiết kế AS** và không được suy từ việc attacker có token với scope rộng.

## 5. JWT và opaque token khác nhau ra sao khi revoke?

Token format ảnh hưởng trực tiếp đến cách **Resource Server biết rằng token đã bị revoke**.

### 5.1. Opaque/reference access token

Một opaque access token thường chỉ là chuỗi không tự chứa claims rõ cho RS. RS có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)**:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "exp": 1800000900
}
~~~

Sau revoke, AS có thể trả:

~~~json
{"active": false}
~~~

Khi RS nhận trạng thái `active=false` từ introspection đáng tin, token phải bị từ chối. Nhưng nếu RS **cache kết quả `active=true`**, vẫn có một **khoảng trễ thu hồi**. Thời gian cache là một quyết định bảo mật và hiệu năng phải được công bố trong chính sách, đặc biệt với API nhạy cảm.

### 5.2. JWT access token tự xác minh

Một JWT access token có thể chứa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "jti": "A1-123",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Khi AS revoke token, **payload JWT đã phát hành không tự biến đổi**. Chữ ký vẫn có thể hợp lệ, `exp` vẫn ở tương lai. Một RS chỉ kiểm chữ ký, issuer, audience và expiry mà **không biết trạng thái revoke** có thể tiếp tục chấp nhận JWT.

Các lựa chọn kiến trúc để tăng khả năng phản ứng:

| Cách làm | Khi nào có hiệu lực tại RS? | Giới hạn/đánh đổi |
|---|---|---|
| **Access token TTL ngắn** | Token tự hết hiệu lực gần `exp` | Không revoke ngay; TTL ngắn làm tăng tải token issuance/refresh |
| **Introspection cho access token** | Khi RS hỏi lại AS hoặc cache hết hạn | Phụ thuộc AS, latency, availability và cache |
| **Denylist theo `jti`/token ID** | Khi RS tra được dữ liệu đã cập nhật | Cần lưu và đồng bộ trạng thái theo expiry; không tin `jti` chưa xác minh |
| **Grant/session version hoặc cutoff time** | Khi RS kiểm nguồn quyền/trạng thái tin cậy | Cần mapping subject/client/grant, xử lý cache và đồng hồ |
| **Sự kiện revoke tới RS/cache** | Khi sự kiện đến và được xử lý đúng | Cần đảm bảo delivery, xử lý mất/kém thứ tự và cơ chế đồng bộ lại |
| **Sender-constrained access token** | Khi attacker không có khóa/chứng chỉ phù hợp | Giảm rủi ro dùng token bị đánh cắp, nhưng không tự revoke token đã cấp |

**Đổi khóa ký JWT toàn cục không phải biện pháp mặc định để thu hồi một token**: có thể khiến hàng loạt token hợp lệ khác bị từ chối. Chỉ cân nhắc rotation khẩn cấp khi chính **khóa ký** bị nghi xâm phạm hoặc chính sách vận hành yêu cầu.

### 5.3. Thu hồi token đã lộ không chỉ là chuyện format

Một JWT tự chứa có thể được introspect hoặc đối chiếu denylist nếu hệ thống thiết kế vậy. Một opaque token có thể bị cache quá lâu hoặc được xác minh sai. **JWT không mặc nhiên “không revoke được”; opaque cũng không mặc nhiên “revoke tức thì”.** Khác biệt nằm ở **cách AS/RS phối hợp trạng thái** và giới hạn chấp nhận được của khoảng trễ thu hồi.

## 6. Revoke liên quan gì đến refresh token family và reuse detection?

Với refresh token rotation:

~~~text
Grant / family F1:
  R0 (USED) -> R1 (USED) -> R2 (ACTIVE)
~~~

Có ít nhất ba sự kiện riêng:

1. **Revoke có chủ ý:** Người dùng ngắt kết nối, client yêu cầu AS thu hồi refresh token hiện hành/grant.
2. **Reuse detection:** AS nhận một token cũ **đã được dùng** tại **token endpoint để xin access token mới**; đây có thể là hành vi đánh cắp và AS có thể đánh dấu family bị xâm phạm.
3. **Refresh token hết hạn hoặc bị thu hồi:** Token không còn hợp lệ; AS từ chối đổi token mới.

**Không được đánh đồng:** Gửi R0 đã từng dùng vào revocation endpoint **không phải** một lần refresh replay; AS không nhất thiết phải đánh dấu family `COMPROMISED` chỉ vì client yêu cầu revoke token vốn đã inactive. Tuy nhiên, hệ thống có thể có chính sách an ninh riêng để ghi sự kiện nghi vấn; điều đó không thay thế quy tắc HTTP 200 khi request hợp lệ.

### Revoke “token hiện hành” và revoke “toàn family”

Khi client đang giữ R2 và muốn ngắt kết nối phiên F1, chính sách an toàn thường là **không cấp thêm token mới cho F1**. AS có thể lưu:

~~~text
family_id = F1
family_status = REVOKED
R2_status = REVOKED
revoked_at = trusted_server_time
reason = USER_DISCONNECTED_CLIENT
~~~

Tên trường chỉ là **mô hình triển khai**, không phải claims OAuth bắt buộc. Nếu AS chỉ đánh dấu R2 đã revoke nhưng còn một nhánh refresh khác trái chính sách, rủi ro vẫn tồn tại. Vì vậy **thu hồi phải tôn trọng mô hình grant/family thực tế của hệ thống**.

### Khả năng xử lý race tại revoke/refresh

Giả sử cùng lúc:

~~~text
Request A: POST /token    với refresh token R2
Request B: POST /revoke   với refresh token R2
~~~

Nếu AS xử lý thiếu nhất quán, một request có thể phát R3 trong khi request còn lại mới revoke R2, khiến **R3 vẫn active ngoài ý muốn**. Cần transaction/lock/CAS hoặc điều khiển trạng thái grant đủ mạnh để bảo đảm **sau khi revoke đã commit, không có refresh token hậu duệ của grant tiếp tục active trái chính sách**. Nếu token issuance đã hoàn tất trước khi revoke, AS và RS vẫn phải xử lý access token đã cấp theo policy.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as Request refresh R2
    participant B as Request revoke R2
    participant AS as Authorization Server
    participant DB as Grant/Family Store
    C->>A: Refresh được khởi tạo
    C->>B: Disconnect được khởi tạo
    A->>AS: POST /token (R2)
    B->>AS: POST /revoke (R2)
    AS->>DB: Serialize/kiểm trạng thái grant
    DB->>DB: Một thứ tự commit được xác định
    DB-->>AS: Grant REVOKED sau revoke
    AS-->>B: HTTP 200
    AS-->>A: Không phát token sau trạng thái revoke
~~~

Sơ đồ là **bất biến mong muốn cho các tác vụ được sắp thứ tự sau revoke**, không cam kết request refresh đã hoàn thành trước khi revoke sẽ bị “thu hồi ngược” bằng phép màu. Quy trình phải tính cả access token đã phát hành trước khi request revoke xử lý.

## 7. Điểm cuối revoke, introspection, logout và xóa phiên khác nhau thế nào?

Một nút “Đăng xuất” có thể cần nhiều bước; RFC 7009 chỉ chuẩn hóa **một loại hành động**.

| Hành động | Nơi xử lý | Điều nó làm | Điều nó không tự làm |
|---|---|---|---|
| **OAuth token revocation (RFC 7009)** | AS revocation endpoint | Đề nghị AS vô hiệu token và token/grant liên quan theo chính sách | Không tự xóa cookie/app session, không bảo đảm JWT offline bị RS từ chối tức thì |
| **Token introspection (RFC 7662)** | AS introspection endpoint, thường RS gọi | Hỏi token còn `active` và ngữ cảnh cần thiết không | Không tự revoke token chỉ vì đã hỏi |
| **Local logout** | Client/BFF | Xóa session cookie/cache, token cục bộ, trạng thái đăng nhập ở app | Không tự vô hiệu token ở AS |
| **OIDC RP-Initiated Logout** | OpenID Provider theo OIDC profile | Hỗ trợ kết thúc phiên đăng nhập tại OP theo cơ chế quy định | Không đồng nhất với revoke mọi OAuth token của mọi client |
| **Thu hồi consent/authorization grant** | AS hoặc giao diện người dùng của AS | Rút quyền đã cấp cho client; có thể kéo theo revoke token/grant | Phạm vi, cách thực thi tùy AS; không chỉ là xóa token trên frontend |
| **Đăng xuất mọi thiết bị** | App/AS/session infrastructure | Kết thúc nhiều phiên/family theo chính sách tài khoản | Không tự có trong một request RFC 7009 nếu không được AS thiết kế |

### BFF: một luồng disconnect hợp lý

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant W as Browser
    participant B as Backend For Frontend
    participant AS as Authorization Server
    participant RS as Invoice API
    U->>W: Nhấn Ngắt kết nối
    W->>B: POST /account/disconnect với session + CSRF protection
    B->>B: Kiểm user/session và quyền thao tác
    B->>AS: POST revocation endpoint, client authentication
    AS-->>B: 200 hoặc lỗi theo hợp đồng
    B->>B: Xóa/cập nhật grant và session cục bộ theo kết quả/policy
    B-->>W: Trạng thái disconnect rõ ràng
    Note over RS: Access token đã cấp được từ chối khi RS biết revoke/hết hạn
~~~

Trong trường hợp mạng lỗi, BFF **không được báo “đã revoke trên AS” nếu chưa có kết quả đáng tin**. Có thể chặn sử dụng token ngay tại BFF, ghi nhận trạng thái `revocation_pending` và có quy trình retry an toàn theo policy. Thông điệp tới người dùng cần phân biệt **đã đăng xuất khỏi ứng dụng** với **quyền/token đã bị thu hồi tại AS** khi hai trạng thái chưa đồng bộ.

### Tài khoản của người dùng và client grant là hai phạm vi khác nhau

Nếu người dùng có:

~~~text
Mobile App:   grant/mobile family Fm
Desktop App:  grant/desktop family Fd
Partner App:  grant/partner family Fp
~~~

Một lần revoke token của `Fm` không mặc nhiên thu hồi `Fd` và `Fp`. Đây là điểm cần hiểu khi thiết kế UI “Ngắt kết nối thiết bị này”, “Đăng xuất mọi nơi” và “Thu hồi quyền truy cập của ứng dụng bên thứ ba”. AS phải biết scope thực sự của thao tác; không dùng một tên nút mơ hồ để giả định đã thu hồi mọi phiên.

## 8. Xác thực client và bảo vệ revocation endpoint

### Confidential client

Backend service có thể dùng OAuth client secret, `private_key_jwt` hoặc mTLS theo cấu hình AS. Khi gọi revoke, nó phải được **xác thực** và AS phải kiểm token đó thuộc client/grant hợp lệ:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-registered-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<redacted-refresh-token>
~~~

**Không** truyền `client_secret` bằng query URL, không log header `Authorization`, không lưu client secret trong SPA/mobile dưới giả định rằng có thể giữ bí mật khỏi người dùng thiết bị. Khi dùng `client_secret_basic`, credential phải được mã hóa/đóng gói đúng giao thức và gửi qua HTTPS.

### Public client

SPA/native app là **public client** khi không giữ được secret bí mật dùng chung. AS cần thực hiện kiểm tra theo **registration, grant và token binding** thích hợp; `client_id` là thông tin định danh public, **không phải password**. Revocation endpoint không nên từ chối mọi public client chỉ vì nó không có Basic Authentication nếu AS đã hỗ trợ public client, nhưng cũng không được dùng `client_id` tự khai làm bằng chứng mật mã đủ để quản trị token của client khác.

Với refresh token sender-constrained (DPoP/mTLS, nếu profile hỗ trợ) AS cần kiểm bằng chứng ràng buộc theo luồng áp dụng. **Chỉ có bearer token string** trong request không tự hợp pháp hóa mọi yêu cầu từ mọi client khi còn điều kiện ownership/binding phải kiểm.

### Browser CORS và CSRF

RFC 7009 có hướng dẫn **hỗ trợ cross-origin**; AS có thể cho phép browser-based client gọi endpoint bằng CORS theo thiết kế. Nhưng:

- **CORS không phải client authentication** và không quyết định token được phép revoke hay không.
- Một `fetch` cross-origin gửi `Content-Type: application/x-www-form-urlencoded` có thể không cần preflight nếu những điều kiện CORS-safelisted khác đều đạt; **không dùng preflight như lớp bảo vệ bắt buộc**.
- Không phản chiếu mọi `Origin` rồi bật `Access-Control-Allow-Credentials: true` khi endpoint có thể xử lý cookie/credentialed requests.
- Với BFF dùng session cookie, endpoint disconnect của **BFF** cần CSRF defense/kiểm Origin theo chính sách. Gọi revoke từ server đến AS **không chịu browser CORS**.
- Từ chối request chứa bí mật đến từ nguồn không tin cậy bằng **client/grant binding và token validation**, chứ không chỉ so `Origin`.

Nếu revocation request có token bị lộ, attacker có thể gây **denial-of-service bằng cách yêu cầu revoke** (nếu AS chấp nhận request của họ). Do đó cần phân quyền, chống giả mạo token/client và rate limiting, nhưng không được bảo vệ endpoint bằng cách cho một client thu hồi token của client khác.

## 9. Revoke token bị đánh cắp và hạn chế replay

Hai nguy cơ cần phân biệt:

**Access token bị đánh cắp:** Attacker có bearer access token có thể gọi RS trong scope/audience và thời gian hiệu lực. Revoke tại AS có thể hạn chế truy cập **nếu RS biết trạng thái revoked**, nhưng chưa chắc chặn được request đã xảy ra hoặc JWT offline còn hợp lệ.

**Refresh token bị đánh cắp:** Attacker có thể xin access token mới nếu refresh token còn hợp lệ và có thể vượt qua điều kiện client/sender binding. Revoke refresh token/grant tại AS có thể ngăn token mới; nếu rotation phát hiện reuse, có thể chặn cả family theo policy.

### Những lớp bảo vệ cần kết hợp

| Lớp bảo vệ | Tác dụng | Không thay thế |
|---|---|---|
| **TLS/HTTPS** | Giảm nghe lén token trên đường truyền | Không ngăn XSS/log/malware |
| **Không log token** | Giảm rò rỉ từ APM, trace, proxy, CI | Không kiểm được API permission |
| **Token TTL ngắn** | Giới hạn cửa sổ sử dụng bearer access token | Không ngăn giao dịch xấu tức thời |
| **Scope/audience tối thiểu** | Giới hạn đích/hành động | Không bảo đảm quyền trên từng object |
| **Refresh token rotation/reuse detection** | Giảm việc duy trì phiên sau khi token bị sao chép | Không tự ngăn dùng access token hiện có |
| **Sender-constrained token (DPoP/mTLS)** | Token string bị đánh cắp đơn lẻ thường không dùng được nếu thiếu khóa/chứng chỉ | Không chống attacker có cả khóa hoặc chạy mã trong client |
| **Revocation/introspection/denylist** | Chặn token sau sự cố tùy khả năng cập nhật trạng thái | Không ngăn yêu cầu đã được xử lý trước khi revoke |
| **Resource Server authorization** | Kiểm `iss`, `aud`, `scope`, tenant, owner, role, business rule | Không thể được thay bằng response 200 của AS |
| **Rate limit + fraud monitoring** | Giảm lạm dụng/DoS và phát hiện bất thường | Không phải proof of possession |

**`jti` không tự chặn replay.** Một JWT có `jti` được dùng nhiều lần trong thời gian hiệu lực là bình thường với nhiều bearer access token. Nếu hệ thống muốn chặn token đã revoke bằng `jti`, cần **nguồn trạng thái tin cậy và kiểm tra thật tại RS**, không chỉ thêm claim rồi coi xong.

### Revoke bị lặp lại

Trong góc nhìn client, gửi lại yêu cầu revoke **cùng token** thường có ngữ nghĩa **idempotent theo trạng thái cuối**: token cuối cùng vẫn không còn hiệu lực; RFC 7009 cho phép trả 200 dù token đã vô hiệu. Tuy nhiên, nếu request đầu đã đến AS rồi response bị mất, việc retry không chứng minh chính xác **phạm vi nào** đã được AS thu hồi và **không được làm sống lại grant**.

Client nên:

- Giới hạn retry, dùng backoff và jitter cho lỗi mạng/5xx hoặc `429` nếu server dùng.
- Không gửi token vào URL/log khi retry.
- Không hiểu `200` như bằng chứng token từng tồn tại hoặc tình trạng access token ở mọi RS.
- Không chấp nhận fail-open quyền truy cập khi AS không xác nhận revoke; có thể chặn local session và xử lý `pending` phù hợp.

## 10. Bảo vệ endpoint khỏi abuse, dò token và lỗi vận hành

Revocation endpoint thường nhận **token bí mật trong request body**, nên cần các bảo vệ của một endpoint an ninh nhạy cảm:

1. **TLS bắt buộc**, kiểm chứng chứng chỉ; không cho token qua HTTP plaintext.
2. **Xác thực confidential client** và kiểm quyền/token ownership khi AS yêu cầu.
3. **Giới hạn request size**, token length và thời gian xử lý để giảm DoS.
4. **Rate limit nhiều lớp**: nguồn mạng đáng tin ở edge, client đã xác thực tại AS, tổng throughput/concurrency; tránh khóa tài khoản nạn nhân bằng `client_id` tự khai.
5. **Trả status đồng nhất cho token không tồn tại** theo RFC 7009, hạn chế chênh lệch phản hồi có thể biến thành oracle thời gian nếu có thể.
6. **Không log plaintext token**, kể cả body, header client authentication, DPoP proof, refresh token; chỉ ghi metadata/audit ID đã kiểm soát.
7. **Cơ chế chống race** giữa revocation và refresh/token exchange, đảm bảo grant không tái sinh token active ngoài policy sau commit.
8. **Theo dõi sự cố**: số request, client class, lỗi authentication, revoke success, grant affected, latency, cache lag, invalid grant và downstream denial.
9. **Bảo vệ cơ sở dữ liệu grant** bằng transaction, quyền truy cập tối thiểu và audit; không cho đường gọi không hợp lệ tự revoke hàng loạt grant.
10. **Kiểm retry và tác động availability**: outage của AS/DB không được khiến backend chấp nhận token đã biết revoked hoặc bỏ client validation.

### Khi AS không khả dụng

Nếu client không nhận được response đáng tin do network timeout hoặc HTTP 5xx, có thể xảy ra:

~~~text
A. Request chưa đến AS        -> token có thể vẫn active.
B. AS đã revoke nhưng mất ACK -> token có thể đã inactive.
C. AS lỗi giữa transaction    -> phải theo trạng thái commit thực tế.
~~~

Client **không thể tự suy từ timeout rằng revoke thành công**. Nó nên vô hiệu sử dụng token ở phía mình ngay khi thực hiện disconnect, và có xử lý retry/status cho grant phù hợp; hiển thị trạng thái tránh khẳng định quá mức. AS cần bảo đảm idempotency về trạng thái và không phát hành token ngoài ý muốn qua các retry.

### Quan sát hệ thống mà không tạo kênh lộ secret

~~~text
GOOD audit fields:
  event = oauth_token_revocation
  client_id = verified_client_id
  token_type = classified_server_side
  grant_id = internal_reference
  result = accepted / rejected_auth / unsupported_type
  request_id = correlation_id
  occurred_at = server_time

NEVER audit:
  token=<raw_refresh_token>
  Authorization: Basic <raw_client_secret>
  access_token=<raw_bearer>
~~~

Ngay cả `grant_id` và subject ID cũng có thể nhạy cảm; áp dụng retention/ACL và hạn chế cardinality trong metrics. Audit chỉ nên cung cấp đủ dữ liệu để điều tra và đo bảo mật, không trở thành một kho token thứ hai.

## 11. Thiết kế một revocation service: Java minh họa

Ứng dụng nên **ưu tiên endpoint RFC 7009 do thư viện Authorization Server đã trưởng thành cung cấp** thay vì tự viết từ đầu. Đoạn **Java 17 mã giả theo interface** sau minh họa các kiểm soát cốt lõi phía AS; nó **không phải implementation production** và không thay thế đặc tả lỗi đầy đủ, client authentication hay DB transaction thật.

~~~java
interface TokenRevocationService {
    RevocationResult revoke(
        VerifiedOAuthClient client,
        char[] rawToken,
        Optional<String> tokenTypeHint);
}

record VerifiedOAuthClient(String id, boolean confidential) {}

enum RevocationResult {
    ACCEPTED, UNSUPPORTED_TOKEN_TYPE
}

final class IllustrativeRevocationService implements TokenRevocationService {
    private final TokenRegistry tokenRegistry;
    private final GrantStore grantStore;
    private final Clock clock;

    // TokenRegistry và GrantStore là giao diện do ứng dụng định nghĩa.
    IllustrativeRevocationService(
            TokenRegistry tokens, GrantStore grants, Clock clock) {
        this.tokenRegistry = tokens;
        this.grantStore = grants;
        this.clock = clock;
    }

    @Override
    public RevocationResult revoke(
            VerifiedOAuthClient client,
            char[] rawToken,
            Optional<String> tokenTypeHint) {

        // Chỉ gọi khi OAuth client authentication / client binding
        // đã được framework kiểm. Hint không phải nguồn ủy quyền.
        // Hint chỉ gợi ý nơi tìm; nếu sai thì vẫn tìm loại token khác
        // theo đúng hợp đồng RFC, không coi hint là loại token thật.
        // Tìm token bằng digest/lookup an toàn, kiểm ownership.
        Optional<VerifiedTokenRecord> maybeToken =
            tokenRegistry.findByProtectedLookup(rawToken, tokenTypeHint);

        if (maybeToken.isEmpty()) {
            // RFC 7009: token không tồn tại vẫn thành công.
            return RevocationResult.ACCEPTED;
        }

        VerifiedTokenRecord token = maybeToken.get();
        if (!token.issuedToClientId().equals(client.id())) {
            // Lỗi authorization được framework xử lý theo policy;
            // tuyệt đối không cho client A revoke token của B.
            throw new OAuthClientTokenBindingException();
        }

        if (!tokenRegistry.supportsActualTokenType(token.type())) {
            return RevocationResult.UNSUPPORTED_TOKEN_TYPE;
        }

        // Phải là transaction/lock có cùng semantics với refresh flow.
        grantStore.revokeAccordingToPolicyAtomically(
            token.grantId(), token.id(), token.type(), clock.instant());

        return RevocationResult.ACCEPTED;
    }
}
~~~

**Các giới hạn rất quan trọng của ví dụ:**

- Các interface `TokenRegistry`, `GrantStore`, `VerifiedTokenRecord` và exception là **kiểu minh họa**, không phải API có sẵn trong Spring Security.
- **Client phải được xác thực trước**; public client cần chính sách binding theo profile. Không lấy `client_id` trong body rồi mặc nhiên coi đó là `VerifiedOAuthClient`.
- Kiểm `supportsActualTokenType` phải theo **khả năng revoke loại token thực sự**, không ngầm tin hint là loại thật. Hàm tìm kiếm phải xử lý trường hợp hint sai/không có theo RFC 7009; mã trên cố ý không triển khai mọi nhánh.
- Quy trình DB cần ngăn race giữa revoke và refresh; `revokeAccordingToPolicyAtomically` là **yêu cầu kiến trúc**, không chứng minh một lời gọi Java tự tạo giao dịch phân tán.
- Nếu token là JWT tự chứa, có thể cần `jti`/denylist hoặc trạng thái grant tại RS. Một record `REVOKED` trong database AS không tự lan đến các RS.
- Không quăng exception chứa raw token; xóa/sơ tán dữ liệu nhạy cảm khỏi memory/log khi có thể. `char[]` giảm một số bản sao nhưng không bảo đảm SDK/HTTP library không tạo bản sao khác.
- Trên HTTP layer, `ACCEPTED` được ánh xạ thành **HTTP 200**, còn lỗi client authentication/binding và loại token không hỗ trợ phải theo hợp đồng OAuth.

### Spring Security: hai ứng dụng có nhiệm vụ khác nhau

**Resource Server** thường có cấu hình:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()));
~~~

Cấu hình này cho phép nhận và xác minh JWT access token tại API, **không tự tạo revocation endpoint**. Khi cần endpoint revoke, phải cấu hình **OAuth Authorization Server** tương ứng, quản lý grant/token store và định nghĩa chính sách revocation. Nên dùng khả năng revocation tích hợp của Authorization Server framework theo phiên bản đã triển khai thay vì copy mã giả ở trên thành `@PostMapping("/revoke")` mà bỏ sót xác thực/binding.

Đồng thời Resource Server cần cấu hình **audience validator** và chính sách tra trạng thái revoke theo yêu cầu độ trễ của hệ thống. Nếu chỉ cấu hình JWT verification offline, việc client gọi `/revoke` ở AS chưa chắc khiến API từ chối ngay JWT còn hạn.

## 12. Mô hình dữ liệu và tiêu chí nhất quán

Đối với AS phát opaque refresh token, dữ liệu nội bộ có thể gồm:

| Đối tượng | Trường gợi ý | Mục đích |
|---|---|---|
| **OAuth grant** | `grant_id`, `subject_id`, `client_id`, `status`, `issued_at`, `revoked_at`, `version` | Quyền ủy quyền, phạm vi và trạng thái chung |
| **Refresh token family** | `family_id`, `grant_id`, `current_refresh_token_id`, `status` | Rotation, reuse detection và revoke một chuỗi phiên |
| **Token record** | `token_id`, `grant_id`, `type`, `lookup_digest`/`jti`, `status`, `expires_at` | Phát hiện token và trạng thái từng access/refresh token |
| **Revocation event** | `event_id`, `client_id`, `grant_id`, `occurred_at`, `scope_of_revocation` | Audit, đồng bộ denylist/cache và xử lý sự cố |

Đây là mô hình **tham khảo**, không phải bảng được RFC 7009 yêu cầu. AS có thể chọn representation khác nếu vẫn bảo đảm yêu cầu bảo mật.

### Những bất biến nên có

1. **Revoked grant không phát hành refresh/access token mới** qua flow đang gắn với grant đó sau khi revoke có hiệu lực, trừ một grant mới được cấp hợp lệ.
2. **Refresh và revoke không double-spend trạng thái**: nếu revoke thắng race, token hậu duệ không tiếp tục active ngoài policy.
3. **Mỗi revocation request hợp lệ không tiết lộ token đã từng tồn tại** qua HTTP 200.
4. **AS không revoke token của client khác** chỉ dựa vào chuỗi token do caller cung cấp và `client_id` tự khai.
5. **RS áp dụng thời hạn revocation propagation đã công bố**; nếu API cần immediate revoke, kiểm trạng thái phải tương thích.
6. **Revoke nhiều lần không làm token sống lại**, không cấp token mới và không phá trạng thái audit quan trọng.
7. **Không để token plaintext trong audit/cache ngoài policy**, hash/HMAC dùng tra token có entropy cao nếu thích hợp.

### Trạng thái cấp quyền và trạng thái token là hai lớp

~~~text
Grant G1: REVOKED
  Refresh family F1: REVOKED
  R2: REVOKED
  Access token A2: JWT tự chứa, exp còn 5 phút
    RS offline-only -> có thể chưa biết G1 revoked
    RS có denylist/grant check -> có thể từ chối ngay
~~~

Nếu sản phẩm yêu cầu “người dùng bấm ngắt kết nối thì API từ chối mọi token sau 1 giây”, kiến trúc cần **chứng minh điều đó bằng test**: TTL cache, mất event, service outage, cách truy vấn trạng thái và consistency ở mọi region. Chỉ gọi `POST /revoke` rồi ghi “logout realtime” trong tài liệu là không đủ.

## 13. Ma trận kiểm thử revocation endpoint

Một bộ test chỉ kiểm HTTP 200 khi token còn hợp lệ sẽ bỏ sót nhiều lỗ hổng. Cần test cả OAuth semantics và **hậu quả tại Resource Server**.

| Kịch bản | Request/trạng thái | Kết quả kỳ vọng |
|---|---|---|
| **Revoke refresh token hợp lệ** | Client A đúng, R1 đang active và thuộc A | AS trả **200**, refresh R1 không đổi được nữa; grant/token liên quan theo policy |
| **Revoke access token hợp lệ** | Client A gửi A1, AS hỗ trợ loại này | Trả **200**; RS từ chối A1 theo cơ chế revocation propagation |
| **Token chưa từng phát hành** | Client hợp lệ, chuỗi token ngẫu nhiên | **200**, không tiết lộ token tồn tại |
| **Token đã bị revoke** | Client hợp lệ gửi lại R1 đã revoke | **200**, không tạo token mới |
| **Không có `token`** | Body thiếu tham số bắt buộc | Từ chối request sai định dạng |
| **`token_type_hint` bỏ trống/không gửi** | Token hợp lệ, không có hint | AS tìm loại hỗ trợ theo RFC và xử lý phù hợp |
| **Hint sai** | Access token nhưng hint `refresh_token` | Không tự tin hint; AS tìm kiếm/kiểm token theo contract |
| **Loại token không được hỗ trợ** | AS không hỗ trợ revoke loại token xác định | Lỗi `unsupported_token_type` nếu áp dụng |
| **Client authentication sai** | Confidential client gửi secret sai | Lỗi xác thực; không 200 thành công |
| **Cross-client revoke** | Client A gửi token đã phát hành cho client B | Không được revoke token/grant B trái quyền |
| **Không có secret ở public client** | Public client theo đăng ký hợp lệ | Áp dụng policy nhận diện/binding của public client, không yêu cầu secret giả |
| **Replay request revoke** | Cùng token gửi revoke nhiều lần | Không sinh grant/token mới; kết quả nhất quán theo RFC |
| **Refresh/race revoke** | Một request refresh và một request revoke đồng thời | Trạng thái commit nhất quán; không để descendant refresh active trái policy |
| **Refresh token family** | R2 hiện hành thuộc family F1 | Revoke đúng grant/family theo policy, không làm sống R0/R1 |
| **Logout một thiết bị** | User có F-mobile và F-browser | Phạm vi revoke đúng family/thiết bị, không thu hồi bừa family khác |
| **Logout mọi thiết bị** | Policy thu hồi nhiều grant | AS xử lý đúng các grant/phiên được phép, có audit |
| **JWT offline RS** | A1 còn `exp`, AS đánh dấu revoked | Test xác nhận khoảng trễ thực tế, không giả định revoke tức thì |
| **Opaque introspection** | Trước/sau revoke, không có cache | Sau revoke `active=false` theo policy |
| **Introspection cache** | RS cache `active=true` trước revoke | Kiểm TTL/invalidation và SLA propagation |
| **Sai audience** | Token `aud=report-api` gửi Invoice API | Invoice API từ chối, bất kể trạng thái revoke |
| **Sai scope/object** | Token đúng audience nhưng thiếu `invoice:read` hoặc sai tenant | API từ chối theo authorization độc lập |
| **AS unavailable** | Timeout hoặc 5xx khi revoke | Client không báo đã revoke trên AS; có retry/backoff/pending phù hợp |
| **Token bị log** | Request revoke qua proxy/APM | Không có raw token/client secret trong log |
| **CORS public client** | Browser gọi revocation endpoint cross-origin | CORS theo allowlist nếu hỗ trợ; auth/binding vẫn áp dụng |
| **Rate limit/DoS** | Request hợp lệ/không hợp lệ dồn dập | AS bảo vệ quota, không biến thành token status oracle |

### Kiểm thử độ trễ thu hồi bằng timeline

~~~text
T0:  Client nhận A1 và R1.
T1:  Resource Server introspect A1 => active=true (cache 30 giây).
T2:  Client POST /revoke R1 => HTTP 200.
T3:  API nhận A1 trong thời gian cache còn hiệu lực.
T4:  Cache hết hạn / nhận sự kiện revoke / tra lại trạng thái.
T5:  API từ chối A1 theo cơ chế mới.
~~~

Từ T2 đến T4 có thể là **khoảng trễ thu hồi**. Nếu chính sách yêu cầu không được có khoảng trễ, cần cơ chế kiểm trạng thái phù hợp ở mọi request hoặc hạ tầng chặn tương đương; không thể chỉ giả định cache `active=true` tự biến mất khi AS nhận `/revoke`.

## 14. Bài tập tình huống: ngắt kết nối ứng dụng bên thứ ba

Người dùng An đã cấp cho **Expense App** quyền đọc hóa đơn. Hệ thống sử dụng:

~~~text
Authorization Server: https://auth.example.test
Revocation endpoint: https://auth.example.test/oauth2/revoke

Expense App:
  client_id = expense-web
  refresh token R2 thuộc grant G1 / family F1

Invoice API:
  expected aud = invoice-api
  required scope = invoice:read
  JWT access token A2 còn 10 phút
  RS hiện chỉ xác minh chữ ký, issuer, audience, exp, scope offline
~~~

An chọn **Ngắt kết nối**, Expense App gửi:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<R2-redacted>&token_type_hint=refresh_token
~~~

AS trả `HTTP 200` và đánh dấu grant G1/family F1 đã revoke.

**Câu 1. Expense App có được tiếp tục đổi R2 thành access token mới không?**

**Không.** AS phải từ chối refresh grant đã revoke, dù client vẫn còn bản sao token trong bộ nhớ hoặc log.

**Câu 2. Access token A2 có chắc bị Invoice API từ chối ngay tại thời điểm AS trả 200 không?**

**Không chắc.** Invoice API đang xác minh JWT offline mà chưa kiểm revocation. Nếu A2 có chữ ký hợp lệ và còn 10 phút, API **có thể tiếp tục chấp nhận** cho đến `exp`. Muốn ngừng sớm cần introspection/denylist/grant check/sự kiện revoke với cơ chế nhất quán thực sự.

**Câu 3. Nếu Expense App xóa token cục bộ nhưng quên gọi revocation endpoint, điều gì có thể xảy ra?**

AS vẫn có thể coi grant còn active. Bản sao R2 bị đánh cắp trước đó có thể tiếp tục dùng ở token endpoint nếu không bị chặn bởi expiry, client binding, rotation hoặc chính sách khác. Xóa bản sao phía client không phải server-side revoke.

**Câu 4. Nếu một client khác gửi R2 đến `/revoke` và tuyên bố `client_id=expense-web`, có được chấp nhận không?**

**Không được mặc nhiên chấp nhận.** AS phải xác minh client theo loại client và token binding/grant; tham số `client_id` tự khai không phải proof of identity.

**Câu 5. Nếu R2 đã không tồn tại và client hợp lệ gửi một chuỗi ngẫu nhiên đến revoke endpoint, response có nên là 404 không?**

**Không.** Với request hợp lệ, RFC 7009 yêu cầu **HTTP 200** kể cả token không tồn tại/không hợp lệ, nhằm hạn chế dò tình trạng token.

**Câu 6. Nếu An nhấn ngắt kết nối ở Expense App, các phiên của ứng dụng khác có tự bị revoke không?**

**Không tự động.** Phạm vi thu hồi phụ thuộc grant/family và chính sách AS. Không suy rằng một `/revoke` cho R2 đồng nghĩa logout mọi thiết bị hoặc mọi OAuth client.

**Câu 7. Nếu AS trả 503 và Expense App xóa token local, có được hiển thị “Đã thu hồi toàn bộ quyền truy cập” không?**

Không nên khẳng định đã revoke phía AS khi chưa có kết quả đáng tin. Có thể ngừng dùng local token, đánh dấu ngắt kết nối đang chờ, retry an toàn hoặc hướng dẫn người dùng kiểm soát grant trên AS.

## 15. Checklist thiết kế và vận hành revocation endpoint

1. **Đúng vai trò:** Điểm cuối revoke thuộc AS, client gọi và RS thực thi trạng thái access token theo policy?
2. **Công bố URL đáng tin:** Client lấy `revocation_endpoint` từ cấu hình/AS metadata phù hợp, không tự đoán hostname hoặc nhận URL tùy ý?
3. **Tuân thủ RFC 7009:** POST HTTPS, `application/x-www-form-urlencoded`, tham số `token` bắt buộc và `token_type_hint` tùy chọn?
4. **Client authentication/binding:** Confidential client xác thực đúng; public client được xử lý theo registration/profile, không dùng `client_id` như mật khẩu?
5. **Quyền sở hữu:** Token/grant cần thuộc client được phép; không cho cross-client revoke hoặc lộ chi tiết token cho caller lạ?
6. **200 không thành oracle:** Token không hợp lệ/không tồn tại vẫn trả 200 trong request hợp lệ, tránh body chứa trạng thái token bí mật?
7. **Loại token hỗ trợ rõ:** AS hỗ trợ revoke refresh token, quy định access token revocation và xử lý `unsupported_token_type` đúng trường hợp?
8. **Phạm vi thu hồi nhất quán:** Revoke access, refresh, grant hay family? Access token đã phát hành có bị vô hiệu theo chính sách nào?
9. **JWT/opaque được xử lý thật:** RS có introspection, denylist, expiry, grant version hoặc sự kiện đồng bộ đủ để đáp ứng SLA revoke?
10. **Độ trễ có thể đo:** Cache `active`, nhiều vùng dữ liệu, eventual consistency và lỗi event delivery được test?
11. **Refresh token family an toàn:** Revoke/refresh cùng lúc có giao dịch/lock/CAS; không phát descendant active ngoài policy?
12. **Logout được tách lớp:** Local session, consent, OIDC logout, logout mọi thiết bị và RFC 7009 không bị coi là một thao tác duy nhất?
13. **CORS/CSRF theo kiến trúc:** Browser public client có policy CORS nếu cần; BFF cookie có CSRF defense; không dùng Origin làm client auth?
14. **Bảo vệ token trong transport/storage:** TLS, redaction, không token trong URL/log, sender-constraining/rotation khi phù hợp?
15. **Giảm abuse:** Rate limit, request size cap, timeout, monitoring/audit và retry an toàn khi AS outage?
16. **Thử các trường hợp âm tính:** Token sai, client sai, cross-client, hint sai, token revoked, JWT offline, race, cache lag, nhiều thiết bị và lỗi mạng?

**Ghi nhớ:** **Revocation endpoint là giao diện của Authorization Server để client yêu cầu ngừng hiệu lực token, không phải giao diện của Resource Server để kiểm token.** Theo RFC 7009, request hợp lệ có thể nhận **HTTP 200 dù token không tồn tại**. Việc thu hồi refresh token/grant ngăn cấp token mới; việc access token đã phát hành có bị chặn **ngay** hay không phụ thuộc định dạng token và cách RS tra trạng thái. Một hệ thống an toàn phải bảo vệ **client authentication, token binding, refresh family, propagation tới RS, quyền đối tượng và xử lý sự cố**, thay vì chỉ xóa token phía client rồi coi như đã logout.

### Chuẩn và tài liệu tham khảo

- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation endpoint, request `token`/`token_type_hint`, HTTP 200, `unsupported_token_type` và ảnh hưởng tới grant/token liên quan.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** các vai trò OAuth, client authentication, token endpoint và `invalid_grant`.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata như `revocation_endpoint` khi AS công bố.
- **RFC 7662 — OAuth 2.0 Token Introspection:** xác minh `active` của access token, khác hành động thu hồi.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `exp` và `jti`, giới hạn của JWT tự xác minh về revocation.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access token profile và yêu cầu kiểm tại RS.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** giảm rủi ro đánh cắp/replay, refresh token rotation và sender-constraining.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** token ràng buộc khóa người gửi, khác revocation.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client authentication và access token binding theo chứng chỉ.
- **OpenID Connect RP-Initiated Logout 1.0:** kết thúc phiên tại OpenID Provider theo OIDC, khác RFC 7009.
