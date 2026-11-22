# 10.9. Phân tích `access_token`, `token_type`, `expires_in`, `scope` và `refresh_token`

Trong **Spring Security OAuth 2.0/OIDC Client**, sau khi người dùng hoàn tất xác thực tại Authorization Server, ứng dụng Client thường nhận một **authorization code** qua Redirect URI. Client gửi code đến **Token Endpoint** để đổi lấy token. Kết quả thành công là một **token response** chứa những thuộc tính quyết định Client có thể gọi API ra sao, token sử dụng trong bao lâu và có thể tiếp tục lấy token mới mà không yêu cầu người dùng đăng nhập lại hay không.

Năm trường quan trọng của OAuth 2.0 token response là **`access_token`**, **`token_type`**, **`expires_in`**, **`scope`** và **`refresh_token`**. Chúng có liên quan nhưng không thể thay thế nhau:

- `access_token` là chứng chỉ để Client truy cập tài nguyên được bảo vệ.
- `token_type` chỉ ra **cách** sử dụng access token; phổ biến nhất là `Bearer`.
- `expires_in` cho biết **thời gian sống** của access token, thường tính bằng giây.
- `scope` mô tả **phạm vi quyền được cấp** cho access token.
- `refresh_token`, nếu có, được dùng trong một yêu cầu riêng để lấy access token mới.

Trong luồng OIDC, token response còn có **`id_token`** để Client xác minh danh tính người dùng. Bài này tập trung vào năm trường OAuth 2.0 đã nêu, đồng thời giải thích vai trò của chúng bên cạnh ID Token trong Spring Security.

## 1. Token Endpoint và vị trí của token response

### 1.1. Từ authorization code tới token

Trong **Authorization Code Flow**, trình duyệt đi qua Authorization Endpoint và quay về ứng dụng Spring tại một Redirect URI như:

```text
https://app.example.test/login/oauth2/code/company?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Spring Security kiểm tra `state` và authorization request trước đó, sau đó gọi Token Endpoint từ phía máy chủ qua HTTPS. Ví dụ request đã đơn giản hóa:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=ORIGINAL_PKCE_VERIFIER
```

Các tham số được xuống dòng chỉ để minh họa; một HTTP form body thực tế được mã hóa đúng dạng `application/x-www-form-urlencoded`. Ví dụ sử dụng `client_secret_basic` cho một confidential web client. Với public client hoặc phương thức xác thực Client khác, request sẽ khác theo đăng ký tại Authorization Server. `code_verifier` được gửi khi flow sử dụng PKCE.

Token response thành công có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "id_token": "EXAMPLE_ID_TOKEN"
}
```

**Đây là dữ liệu minh họa**, không phải token thật hoặc giá trị có thể dùng để xác thực. Trong OAuth 2.0, `access_token` và `token_type` là các trường cốt lõi của token response thành công. `expires_in` được khuyến nghị, còn `scope` có thể không xuất hiện khi phạm vi được cấp giống phạm vi Client đã yêu cầu. `refresh_token` là tùy chọn và phụ thuộc loại grant, chính sách cùng cách đăng ký Client.

Ở một **OIDC Authorization Code Flow thành công**, phản hồi Token Endpoint có `id_token` theo quy tắc OIDC. Với OAuth 2.0 thuần túy hoặc Client Credentials Grant không có OIDC login, phản hồi thường **không có** ID Token.

### 1.2. Tại sao response phải được bảo vệ?

Access token và refresh token thường là **thông tin có giá trị sử dụng trực tiếp**. Token response cần đi qua **kết nối back channel TLS/HTTPS** tới Client, không qua URL trên thanh địa chỉ trình duyệt.

Các header như `Cache-Control: no-store` và `Pragma: no-cache` giúp ngăn lưu phản hồi nhạy cảm trong các HTTP cache. Tuy vậy, ứng dụng vẫn phải tránh ghi token vào log, exception message, hệ thống giám sát, cookie không phù hợp hoặc URL redirect.

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Client as Spring Security Client
    participant AS as Authorization Server
    participant API as Resource Server

    Browser->>Client: GET /oauth2/authorization/company
    Client-->>Browser: 302 tới Authorization Endpoint
    Browser->>AS: Người dùng xác thực và cấp quyền
    AS-->>Browser: 302 tới callback?code=...&state=...
    Browser->>Client: GET /login/oauth2/code/company?code=...&state=...
    Client->>AS: POST Token Endpoint (authorization_code)
    AS-->>Client: access_token, token_type, expires_in, scope, refresh_token?
    Client->>Client: Lưu OAuth2AuthorizedClient và thiết lập phiên
    Client->>API: Authorization: Bearer access_token
    API-->>Client: Dữ liệu theo quyền token
    opt Access token hết hạn và refresh được phép
        Client->>AS: POST Token Endpoint (refresh_token)
        AS-->>Client: Access token mới, refresh token mới nếu xoay vòng
    end
```

Lưu ý: **Resource Server** xác minh access token do Client trình ra khi gọi API. **Spring OAuth2 Client** chịu trách nhiệm nhận và quản lý token. Cùng một ứng dụng có thể đóng cả hai vai trò, nhưng logic và cấu hình của chúng khác nhau.

## 2. Bảng ý nghĩa nhanh của năm trường

| Trường JSON | Kiểu dữ liệu điển hình | Yêu cầu theo OAuth 2.0 | Ý nghĩa |
|---|---|---|---|
| `access_token` | String | **Bắt buộc** trong token response thành công | Credential dùng truy cập tài nguyên |
| `token_type` | String | **Bắt buộc** | Cơ chế sử dụng token, phổ biến là `Bearer` |
| `expires_in` | Number, số giây | **Khuyến nghị**, không phải trường bắt buộc tuyệt đối | Thời gian sống còn lại được mô tả khi token cấp phát |
| `scope` | String, các scope cách nhau bằng dấu cách | **Bắt buộc nếu khác** phạm vi Client đã yêu cầu; nếu giống có thể bỏ | Quyền hoặc phạm vi thực sự được cấp |
| `refresh_token` | String | **Tùy chọn** | Credential để yêu cầu access token mới tại Token Endpoint |

Bảng dựa trên mô hình token response của [RFC 6749, Section 5.1](https://www.rfc-editor.org/rfc/rfc6749#section-5.1). Quy định cụ thể có thể được mở rộng bởi các chuẩn khác hoặc hợp đồng của một Authorization Server.

Không nên tự đặt quy tắc rằng “thiếu `expires_in` thì token vĩnh viễn” hoặc “thiếu `refresh_token` thì Server triển khai sai”. Cả hai kết luận đều không chính xác.

## 3. `access_token` — token để truy cập tài nguyên

### 3.1. Access token trả lời câu hỏi gì?

Access token là credential mà Client trình cho **Resource Server/API** để yêu cầu một tài nguyên theo quyền đã được cấp. Ví dụ sau khi người dùng đăng nhập OIDC, Spring có thể gọi một API hồ sơ:

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

Resource Server sẽ kiểm tra token theo chính sách của nó, chẳng hạn:

- Token do Authorization Server đáng tin phát hành hay không.
- Token còn hiệu lực hay đã hết hạn/đã bị thu hồi.
- Token có dành cho **đúng API** hay không (audience hoặc thông tin tương đương).
- Token có scope/permission cần thiết cho endpoint hay không.
- Quy tắc nghiệp vụ và quyền của chủ thể có cho phép truy cập hay không.

Access token **không thay thế tất cả điều kiện phân quyền**. Có token hợp lệ không có nghĩa được dùng mọi API hoặc thao tác.

### 3.2. Access token có bắt buộc là JWT không?

**Không.** OAuth 2.0 không bắt buộc access token phải là JWT. Có hai hình thức thường gặp:

| Dạng | Ví dụ | Đặc điểm |
|---|---|---|
| **Opaque token** | `a1b2c3...` | Chuỗi không có cấu trúc công khai; Resource Server có thể cần introspection hoặc cơ chế xác minh riêng |
| **JWT access token** | `eyJhbGciOi...` | Chuỗi chứa header, payload và chữ ký; có thể có claim như `iss`, `aud`, `exp`, `scope` |

Một JWT payload minh họa:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-782",
  "aud": "https://api.example.test",
  "iat": 1780000000,
  "exp": 1780003600,
  "scope": "reports.read profile.read"
}
```

Đây là nội dung giả định **sau khi giải mã**; nó không phải JWT đã ký. Danh sách claim thực tế và cách biểu diễn scope có thể khác theo profile token và provider.

**Client không được suy ra quyền hoặc danh tính đáng tin chỉ bằng cách Base64-decode token.** JWT payload có thể đọc được mà không cần khóa, nhưng tính xác thực phải được kiểm tra. OAuth2 Client thường không cần giải mã access token để đăng nhập người dùng: Spring Security OIDC Login sử dụng ID Token đã được xác minh cho danh tính, còn Resource Server có trách nhiệm kiểm tra access token khi API được gọi.

### 3.3. Access token khác ID Token

| Tiêu chí | Access token | ID Token |
|---|---|---|
| Mục đích chính | Truy cập tài nguyên/API | Xác nhận sự kiện xác thực và danh tính người dùng trong OIDC |
| Bên nhận chính | Resource Server | OIDC Relying Party/Client |
| Audience | Thường hướng tới API | Chứa Client ID trong `aud` theo OIDC |
| Định dạng | JWT hoặc opaque | JWT theo OIDC |
| Có dùng làm `Authorization: Bearer` tới API không? | Có, khi phù hợp loại token và API | **Không dùng thay** access token |
| Có dùng một mình để tạo quyền admin? | Không | Không |

Nếu Token Endpoint trả cả hai loại, **không tráo ID Token vào vị trí access token** khi gọi API. Một API có thể từ chối ID Token vì audience không đúng hoặc vì bản chất token không dành cho tài nguyên đó.

### 3.4. Access token bị lộ có nguy hiểm không?

Với token kiểu **Bearer**, người giữ token thường có thể sử dụng nó trong phạm vi được cấp cho đến khi hết hạn hoặc bị thu hồi. Vì vậy:

- Không ghi token trong URL query hoặc fragment.
- Không đưa raw token vào exception, analytics, access log hoặc response debug.
- Không lưu token ở frontend nếu kiến trúc ứng dụng dựa trên backend session và không có lý do rõ ràng.
- Chỉ gửi token tới API đích đáng tin, qua HTTPS.
- Chọn scope, audience và thời gian sống phù hợp.
- Bảo vệ kho lưu token và các thông tin được dùng để lấy token mới.

Một JWT chỉ được **ký** vẫn có thể đọc payload. Không đặt secret ứng dụng hoặc dữ liệu cá nhân không cần thiết vào token rồi xem chữ ký như cơ chế mã hóa.

## 4. `token_type` — cách Client trình access token

### 4.1. Giá trị `Bearer` có nghĩa gì?

Phần lớn OAuth 2.0 token responses dùng:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer"
}
```

`Bearer` là loại token theo [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750). Khi Resource Server nhận Bearer token qua HTTP, cách thông dụng và được khuyến nghị là header:

```http
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Phần `Bearer` là **authentication scheme** trong header, còn `EXAMPLE_ACCESS_TOKEN` là **giá trị token**. Không nên lưu `"Bearer EXAMPLE_ACCESS_TOKEN"` như chính giá trị `access_token` rồi ghép thêm một `Bearer` nữa.

So sánh:

```text
Đúng:
Authorization: Bearer EXAMPLE_ACCESS_TOKEN

Sai:
Authorization: Bearer Bearer EXAMPLE_ACCESS_TOKEN

Không phù hợp:
Authorization: Basic EXAMPLE_ACCESS_TOKEN
```

`Basic` thường dùng cho một số phương thức Client authentication tại Token Endpoint, không phải cách mặc định sử dụng Bearer access token để gọi Resource Server.

### 4.2. Giá trị có thể khác `Bearer` không?

Có. Trường `token_type` xác định loại token mà Client phải hiểu để sử dụng đúng. Một số mở rộng OAuth sử dụng cơ chế chứng minh quyền sở hữu/token binding và token type khác, ví dụ `DPoP` trong bối cảnh hỗ trợ DPoP.

**Không tự giả định mọi token type đều tương đương Bearer.** Nếu Client nhận token type chưa được thư viện và Resource Server hỗ trợ, cần dùng cơ chế tương ứng hoặc báo lỗi cấu hình. Chỉ nhìn access token có dạng JWT không đủ để kết luận token là Bearer.

### 4.3. Trong Spring Security, token type được biểu diễn ra sao?

Spring lưu nó trong đối tượng `OAuth2AccessToken`:

```java
import org.springframework.security.oauth2.core.OAuth2AccessToken;

// accessToken được lấy từ một OAuth2AuthorizedClient hợp lệ.
OAuth2AccessToken.TokenType type = accessToken.getTokenType();
String scheme = type.getValue();  // Thường là "Bearer"
```

Đoạn minh họa giả định biến `accessToken` đã được lấy từ authorized client. Các API OAuth2 Client phổ biến của Spring Security xử lý Bearer token và sẵn sàng tích hợp HTTP client; khi cần token type đặc thù, phải xem phiên bản/framework có hỗ trợ hay không.

## 5. `expires_in` — thời gian sống của access token

### 5.1. Đơn vị và cách hiểu

Token response:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

`expires_in: 3600` nghĩa là **thời gian sống khoảng 3.600 giây (1 giờ)** của access token khi response được phát hành. Đây **không phải** Unix timestamp và không có nghĩa token hết hạn đúng lúc 03:600 hay vào ngày 1/1/1970 cộng 3.600 giây.

Một cách tính gần đúng ở Client:

```text
receivedAt ≈ thời điểm nhận token response
expiresAt ≈ receivedAt + expires_in seconds

Ví dụ:
receivedAt = 2026-11-16T09:00:00+07:00
expires_in = 3600
expiresAt ≈ 2026-11-16T10:00:00+07:00
```

Đây là minh họa về cách tính; thời điểm cấp token có thể sớm hơn lúc Client nhận phản hồi. Thư viện quản lý token có thể sử dụng thời điểm nhận phù hợp và **clock skew** để tránh dùng token quá sát hạn.

### 5.2. `expires_in` và claim `exp` có giống nhau không?

Không.

| Thuộc tính | Nằm ở đâu? | Kiểu/đơn vị | Ý nghĩa |
|---|---|---|---|
| `expires_in` | Top-level token response JSON | Số giây tương đối | Thời gian sống của access token khi được cấp |
| `exp` | Claim trong JWT khi token có dạng JWT | Thời điểm tuyệt đối theo NumericDate (giây từ Unix epoch) | Mốc hết hạn mà bên xác minh JWT sử dụng |

Với opaque access token, Client không đọc được `exp` từ payload JWT vì token không phải JWT công khai. Ngay cả khi token là JWT, Spring OAuth2 Client nên sử dụng **metadata hết hạn** do framework quản lý thay vì tự decode access token chỉ để lấy thời gian.

Khi Resource Server xác minh JWT, nó phải kiểm tra hạn token theo cơ chế của Resource Server. Việc Client dự tính token chưa hết hạn không bảo đảm Resource Server chắc chắn chấp nhận token: token có thể bị thu hồi, audience sai hoặc đồng hồ giữa các hệ thống lệch nhau.

### 5.3. Nếu `expires_in` vắng mặt thì sao?

RFC 6749 khuyến nghị có `expires_in`, nhưng không biến nó thành trường bắt buộc trong mọi phản hồi. Authorization Server có thể mô tả thời hạn bằng cơ chế khác hoặc tài liệu riêng.

Không được suy luận:

```text
expires_in không có => token không bao giờ hết hạn
```

Client phải tuân theo hợp đồng của provider và khả năng parser/framework. Khi không thể biết thời hạn đáng tin, cần xử lý lỗi từ API hoặc yêu cầu xác thực lại theo chính sách; không tự đặt một TTL quá dài rồi coi đó là thời hạn được cấp.

### 5.4. Refresh sớm hơn hạn để giảm lỗi

Giả sử token hết hạn lúc 10:00 nhưng một API call bắt đầu lúc 09:59:59, đi qua mạng và tới Resource Server lúc 10:00:01. Token có thể bị từ chối dù phía Client thấy còn vài giây.

Vì vậy client libraries thường sử dụng **clock skew** hoặc **khoảng đệm làm mới** trước hạn. Ví dụ khái niệm:

```text
Token expiresAt = 10:00
Safety skew = 60 giây
Client cân nhắc token đã cần làm mới từ 09:59
```

Đây là ví dụ, **không phải** quy định rằng mọi Spring Security version đều có cùng khoảng đệm hoặc phải chọn 60 giây. Việc xử lý expiration và refresh nên do `OAuth2AuthorizedClientManager` cùng provider quản lý khi phù hợp.

### 5.5. Hết hạn access token khác hết phiên đăng nhập

Trong OIDC Login có backend session, người dùng có thể vẫn có một `SecurityContext`/HTTP session hợp lệ khi access token dùng gọi API đã hết hạn.

- **HTTP session:** trạng thái đăng nhập của ứng dụng.
- **Access token:** thời hạn truy cập một Resource Server cụ thể.
- **Refresh token:** khả năng lấy token mới nếu provider đã cấp.
- **ID Token:** bằng chứng về một sự kiện xác thực OIDC, với `exp` và các claim riêng.

Không đồng nhất “access token hết hạn” với “HTTP session lập tức hết hạn”. Ngược lại, session hết hạn cũng không đảm bảo refresh token phía server đã được thu hồi; cần thiết kế logout và quản lý token rõ ràng.

## 6. `scope` — phạm vi mà Authorization Server đã cấp

### 6.1. Định dạng của trường `scope`

Trong OAuth 2.0 token response, `scope` thường là **một chuỗi gồm các tên scope cách nhau bằng dấu cách**, không phải JSON array:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "scope": "openid profile email"
}
```

Authorization request cũng có thể xin scope, chẳng hạn:

```text
scope=openid%20profile%20email%20reports.read
```

Tập scope **được yêu cầu** và tập scope **được cấp** có thể khác nhau vì chính sách nhà cung cấp hoặc consent của người dùng.

### 6.2. Scope yêu cầu và scope được cấp

Giả sử Client gửi:

```text
openid profile email reports.read reports.write
```

Authorization Server chỉ chấp thuận:

```text
openid profile email reports.read
```

Token response có thể chứa:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email reports.read"
}
```

Ứng dụng không thể coi `reports.write` là đã được cấp. Nếu một thao tác đòi quyền ghi báo cáo, Client phải xử lý tình huống thiếu scope bằng UI/flow cấp quyền phù hợp hoặc từ chối thao tác. Resource Server có trách nhiệm kiểm tra phạm vi token thực tế.

### 6.3. Nếu token response không chứa `scope`?

Theo RFC 6749, khi scope được cấp **trùng với** scope Client yêu cầu, trường `scope` có thể bị bỏ. Khi khác, Server phải trả `scope` để Client hiểu phạm vi được cấp.

Vì vậy, hai trường hợp không tương đương:

```text
A. Client yêu cầu openid profile email
   Token response không có trường scope.
   => Theo quy tắc OAuth2, có thể hiểu scope được cấp như yêu cầu.

B. Client yêu cầu openid profile email reports.write
   Token response scope = "openid profile email".
   => Quyền reports.write không được cấp.
```

Cách giải thích trên giả định provider tuân thủ OAuth2. Khi kết nối hệ thống tùy biến không tuân chuẩn, cần xác minh hành vi thực tế và cấu hình mapping của Client.

### 6.4. Scope không phải role của ứng dụng

Một điểm rất quan trọng khi lập trình Spring Security:

- Scope `openid` có ý nghĩa bắt đầu xác thực OIDC.
- `profile` và `email` yêu cầu nhóm claim hồ sơ người dùng.
- `reports.read` có thể là scope API do nhà cung cấp định nghĩa.
- `ROLE_ADMIN` là một ví dụ **GrantedAuthority** cho phân quyền nội bộ trong Spring.

Không có quy tắc chung rằng `scope=profile email` tạo `ROLE_USER` hoặc `ROLE_ADMIN`. Việc ánh xạ scope, roles, groups và business permissions phải được thiết kế riêng, dựa trên nguồn dữ liệu đã được xác minh.

### 6.5. Scope và audience cùng ảnh hưởng quyền truy cập

Một token có `scope=reports.read` chưa chắc gọi được mọi API có endpoint tên `/reports`. Nó còn phải **hướng tới đúng Resource Server** và phù hợp audience cùng chính sách của API.

Ví dụ:

```text
Access token A:
aud = https://api-a.example.test
scope = reports.read

Access token B:
aud = https://api-b.example.test
scope = reports.read
```

Một API B có thể từ chối token A dù scope giống token B. Không dùng access token cấp cho UserInfo Endpoint hoặc một API khác như thể nó tự động dùng được mọi tài nguyên.

## 7. `refresh_token` — lấy access token mới khi được phép

### 7.1. Refresh token dùng để làm gì?

Access token thường có thời hạn tương đối ngắn để hạn chế thiệt hại khi bị lộ. Refresh token, nếu Authorization Server cấp, cho phép Client gọi **Token Endpoint** với grant `refresh_token` để yêu cầu access token mới mà không bắt buộc điều hướng người dùng qua màn hình đăng nhập lại ngay tại thời điểm đó.

Ví dụ token response ban đầu:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN_1",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_1",
  "id_token": "EXAMPLE_ID_TOKEN"
}
```

Khi cần làm mới:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=EXAMPLE_REFRESH_TOKEN_1
```

Đây là một **POST trực tiếp từ Client tới Token Endpoint** theo phương thức xác thực Client đã được đăng ký. Không đưa refresh token vào URL của trình duyệt.

Token response khi refresh thành công có thể là:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN_2",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_2"
}
```

Trường `refresh_token` trong response làm mới có thể là **token mới** theo cơ chế **refresh token rotation**. Nếu Authorization Server không cấp refresh token mới trong lần refresh, việc tiếp tục dùng token cũ phải tuân theo chính sách và quy tắc của provider. Không tự suy đoán token cũ còn hiệu lực khi provider đã thông báo thu hồi hoặc thay thế.

### 7.2. Refresh token có phải lúc nào cũng được cấp không?

Không. Điều này phụ thuộc:

- Loại Client: confidential server-side, public native/SPA, v.v.
- Authorization grant: authorization code, client credentials hoặc grant khác.
- Các scope và consent được phép.
- Chính sách thời hạn và refresh token của Authorization Server.
- Mức độ tin cậy của Client và cơ chế bảo vệ refresh token.
- Thiết lập về truy cập khi người dùng không còn hiện diện.

Với **Client Credentials Grant**, RFC 6749 ghi nhận refresh token thông thường **không nên** được đưa vào token response vì Client có thể xác thực trực tiếp để xin token mới. Với **OIDC Login**, scope `offline_access` có thể liên quan đến yêu cầu cấp khả năng truy cập offline, nhưng **không bảo đảm** mọi provider hoặc mọi Client chắc chắn nhận refresh token. Cần kiểm tra chính sách và điều kiện consent của nhà cung cấp.

### 7.3. Refresh token có thể hết hạn hoặc bị thu hồi

Refresh token không phải quyền truy cập vĩnh viễn. Các tình huống khiến refresh thất bại:

- Refresh token hết hạn hoặc không còn hợp lệ.
- Người dùng rút quyền consent.
- Client bị vô hiệu hóa hoặc secret/credentials thay đổi.
- Authorization Server thu hồi phiên hoặc token family.
- Refresh token cũ đã bị thay thế sau rotation.
- Chính sách bảo mật yêu cầu tương tác người dùng lại.

Token Endpoint có thể trả lỗi như:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or expired"
}
```

Không nên tự gọi lại vô hạn bằng chính refresh token bị từ chối. Một chiến lược phù hợp là xóa authorized client lỗi khi cần, đưa người dùng qua luồng xác thực/consent mới, và báo tình trạng có thể hiểu được cho giao diện.

### 7.4. Refresh token rotation và nguy cơ race condition

Một số provider cấp **refresh token mới sau mỗi lần sử dụng** và làm mất hiệu lực token trước. Ví dụ:

```text
T0: Client đang giữ RT-1
T1: Client gửi RT-1 tới Token Endpoint
T2: Server cấp AT-2 và RT-2, có thể vô hiệu hóa RT-1
T3: Client phải lưu RT-2 và không dùng RT-1 nữa
```

Nếu hai request song song cùng dùng `RT-1`, một request có thể thành công còn request kia thất bại. Vì vậy việc làm mới token trong ứng dụng nhiều request/instance cần một cơ chế quản lý nhất quán, tránh thao tác refresh độc lập từ mỗi controller.

Các thư viện OAuth2 Client giúp quản lý authorized client và refresh, nhưng ứng dụng vẫn cần chọn **cơ chế lưu trữ và đồng bộ** phù hợp với số instance, session và chính sách rotation của provider.

### 7.5. Vì sao refresh token cần bảo vệ nghiêm ngặt?

Refresh token thường cho khả năng tiếp tục lấy access token mới. Nếu bị lộ, thiệt hại có thể kéo dài hơn việc lộ một access token sắp hết hạn. Nguyên tắc:

1. Chỉ lưu tại vị trí được kiểm soát; với confidential web app thường là phía backend.
2. Không log, hiển thị hoặc trả về refresh token trong JSON cho frontend.
3. Bảo vệ dữ liệu lưu trữ và đường truyền, áp dụng phân quyền truy cập.
4. Hỗ trợ rotation và cập nhật token mới đúng lúc.
5. Xử lý thu hồi khi logout hoặc sự kiện bảo mật nếu provider hỗ trợ và thiết kế yêu cầu.
6. Không dùng cùng một refresh token giữa những Client/tenant không thuộc cùng đăng ký.

**Token lưu phía server vẫn cần bảo vệ.** Việc người dùng không nhìn thấy token trên browser không tự đảm bảo database, cache, backup hay log vận hành là an toàn.

## 8. So sánh ba token quan trọng của OIDC Client

Trong một lần OIDC Authorization Code Flow, có thể gặp **access token**, **ID Token** và **refresh token**:

| Token | Bên sử dụng | Mục tiêu | Có gửi tới API? | Có dùng để refresh? |
|---|---|---|---|---|
| Access token | OAuth2 Client và Resource Server | Cấp quyền truy cập tài nguyên | **Có**, khi token đúng loại/audience/scope | Không dùng làm credential refresh |
| ID Token | OIDC Client/Relying Party | Xác minh danh tính người dùng | **Không** dùng thay access token | Không dùng làm refresh token |
| Refresh token | OAuth2 Client và Authorization Server | Yêu cầu token mới | **Không** gửi như bearer token tới API nghiệp vụ | **Có**, tại Token Endpoint |

Thêm vào đó còn **authorization code**: một mã tạm thời Client nhận qua callback, dùng một lần để xin token. Authorization code khác cả ba token trên.

Ví dụ một ứng dụng Spring Security OIDC Login:

1. Nhận `code` qua browser redirect.
2. Đổi code tại Token Endpoint.
3. Xác minh ID Token để thiết lập `OidcUser`/`Authentication`.
4. Dùng access token được phép gọi UserInfo Endpoint hoặc downstream API.
5. Khi access token cần làm mới và có refresh token, dùng refresh token qua back channel.
6. Khi refresh không còn hợp lệ, thực hiện lại bước yêu cầu xác thực/ủy quyền theo chính sách.

Không tự kết luận rằng `access_token` hết hạn đồng nghĩa với `OidcUser` phải bị xóa ngay lập tức. Trạng thái session và quy trình refresh cần được quản lý riêng.

## 9. Token response trong Spring Security được biểu diễn thế nào?

Spring Security có các abstraction để ứng dụng không phải tự parse JSON và giữ token dưới dạng chuỗi rời rạc.

### 9.1. Từ HTTP JSON tới `OAuth2AccessTokenResponse`

Trong bước token exchange, Spring Security xử lý phản hồi từ Token Endpoint và biểu diễn dữ liệu OAuth2 bằng:

```text
OAuth2AccessTokenResponse
 ├── OAuth2AccessToken accessToken
 │    ├── TokenType (thường BEARER)
 │    ├── tokenValue
 │    ├── issuedAt
 │    ├── expiresAt
 │    └── scopes
 ├── OAuth2RefreshToken refreshToken? 
 └── additionalParameters
      └── có thể chứa các trường mở rộng (OIDC id_token, ...)
```

Đây là sơ đồ khái niệm, không phải JSON serialization của các class.

Các lớp liên quan:

| Class | Package | Dữ liệu/mục đích |
|---|---|---|
| `OAuth2AccessTokenResponse` | `org.springframework.security.oauth2.core.endpoint` | Token response sau khi parse |
| `OAuth2AccessToken` | `org.springframework.security.oauth2.core` | Access token, loại token, issued/expires, scopes |
| `OAuth2RefreshToken` | `org.springframework.security.oauth2.core` | Refresh token |
| `OAuth2AuthorizedClient` | `org.springframework.security.oauth2.client` | ClientRegistration + principal name + access/refresh token đã được cấp |
| `OAuth2AuthorizedClientRepository` | `org.springframework.security.oauth2.client.web` | Lưu/đọc authorized client trong ngữ cảnh web request |
| `OAuth2AuthorizedClientService` | `org.springframework.security.oauth2.client` | Quản lý authorized client theo client registration và principal |

Đặc biệt, `OAuth2AuthorizedClient` là đối tượng mà ứng dụng thường nhận được **sau khi login** hoặc khi client authorization thành công. Bạn hiếm khi cần tự tạo request HTTP tới Token Endpoint khi sử dụng Spring Security OAuth2 Client.

### 9.2. Bảng ánh xạ từ response JSON sang Spring

| JSON Token Endpoint | Spring Security | Lưu ý |
|---|---|---|
| `access_token` | `OAuth2AccessToken#getTokenValue()` | Giá trị nhạy cảm, không log |
| `token_type` | `OAuth2AccessToken#getTokenType()` | Thường là `TokenType.BEARER` |
| `expires_in` | Thông tin `issuedAt` / `expiresAt` trong `OAuth2AccessToken` | Spring biểu diễn hạn dưới dạng thời điểm, không trực tiếp là chuỗi JSON |
| `scope` | `OAuth2AccessToken#getScopes()` | `Set<String>` sau khi Spring xử lý scope |
| `refresh_token` | `OAuth2AuthorizedClient#getRefreshToken()` | Có thể `null` |

Việc `OAuth2AccessToken#getExpiresAt()` là một `Instant` (hoặc thiếu thời hạn theo trường hợp) giúp mã nguồn so sánh thời gian thuận tiện, tránh hiểu nhầm `expires_in` là epoch timestamp.

### 9.3. Cấu hình ClientRegistration và OAuth2 Login

Ví dụ `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

Spring Security Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

Cấu hình này minh họa web application đăng nhập OIDC và sử dụng OAuth2 Client. Muốn chạy thật, cần dependency Spring Security OAuth2 Client phù hợp với phiên bản Spring Boot, IdP hợp lệ và Redirect URI đã được đăng ký tại provider.

`client-id` và `client-secret` cần được cấp bằng biến môi trường hoặc secret manager. Những URL `example.test` chỉ là placeholder.

### 9.4. Đọc metadata token an toàn với `OAuth2AuthorizedClient`

Trong ứng dụng MVC, Spring Security có annotation `@RegisteredOAuth2AuthorizedClient` để inject authorized client theo registration. Ví dụ một endpoint trả **metadata không chứa token bí mật**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TokenMetadataController {

    @GetMapping("/account/token-metadata")
    public Map<String, Object> metadata(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        OAuth2AccessToken accessToken = authorizedClient.getAccessToken();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put(
            "registrationId",
            authorizedClient.getClientRegistration().getRegistrationId()
        );
        result.put("tokenType", accessToken.getTokenType().getValue());
        result.put("scopes", accessToken.getScopes());
        result.put(
            "expiresAt",
            accessToken.getExpiresAt() == null
                ? null
                : accessToken.getExpiresAt().toString()
        );
        result.put(
            "refreshTokenAvailable",
            authorizedClient.getRefreshToken() != null
        );
        return result;
    }
}
```

Ví dụ response:

```json
{
  "registrationId": "company",
  "tokenType": "Bearer",
  "scopes": ["openid", "profile", "email"],
  "expiresAt": "2026-11-16T03:00:00Z",
  "refreshTokenAvailable": true
}
```

Ví dụ cho thấy cách đọc thuộc tính token trong Spring. Endpoint cần bảo vệ bằng security rules tương ứng; trong production, chỉ công khai metadata thật sự phục vụ chức năng. **Tuyệt đối không thêm**:

```java
// KHÔNG NÊN trả cho frontend trong web login backend session.
result.put("accessToken", accessToken.getTokenValue());
result.put("refreshToken", authorizedClient.getRefreshToken().getTokenValue());
```

Việc trả token ra JSON có thể mở rộng bề mặt rò rỉ token không cần thiết.

### 9.5. Khi `getRefreshToken()` trả về `null`

Điều này có thể hoàn toàn bình thường. Ứng dụng cần:

- Kiểm tra xem provider có cấp refresh token trong flow này không.
- Xem lại scope, consent và Client registration nếu chức năng thật sự cần refresh.
- Sẵn sàng yêu cầu người dùng đăng nhập lại khi access token hết hạn mà không có cách refresh hợp lệ.
- Không dùng chuỗi giả hay tự tái sử dụng access token trong field refresh token.

Một thao tác chỉ phụ thuộc session có thể tiếp tục hoạt động ngay cả khi không có refresh token. Chỉ những chức năng cần access token còn hạn cho downstream API mới phải xử lý vòng đời token đó.

## 10. Làm mới token với `OAuth2AuthorizedClientManager`

### 10.1. Vì sao không tự viết `POST /token` trong controller?

Spring Security cung cấp `OAuth2AuthorizedClientManager` cùng các provider thực hiện flow cấp quyền, bao gồm refresh token. Sử dụng hạ tầng này giúp quản lý:

- Tìm authorized client theo `ClientRegistration` và principal.
- Kiểm tra token đã hoặc gần hết hạn theo cơ chế của provider.
- Sử dụng refresh token nếu có và được phép.
- Lưu authorized client đã cập nhật.
- Phối hợp cơ chế xử lý lỗi như `invalid_grant` theo cấu hình.

Không phải mọi lời gọi `authorize(...)` đều chắc chắn có refresh token hoặc nhận được token mới. Nếu access token còn hiệu lực, manager có thể trả về authorized client hiện tại. Nếu không thể làm mới, ứng dụng cần xử lý lỗi hoặc chuyển qua flow đăng nhập lại.

### 10.2. Ví dụ cấu hình manager cho Servlet request

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

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
}
```

Trong ví dụ này, `DefaultOAuth2AuthorizedClientManager` hoạt động trong bối cảnh có `HttpServletRequest`/`HttpServletResponse`. Đối với công việc chạy ngoài HTTP request (scheduled job/background process), Spring Security có lựa chọn quản lý authorized client dựa trên `OAuth2AuthorizedClientService`, thường là `AuthorizedClientServiceOAuth2AuthorizedClientManager`. Chọn đúng loại manager theo môi trường.

### 10.3. Yêu cầu manager cung cấp authorized client hợp lệ

Trong một controller hoặc service có ngữ cảnh request và principal thích hợp:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

// manager và authentication được cung cấp qua DI / Spring Security.
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("company")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);

if (client == null) {
    // Không có authorized client phù hợp; cần bắt đầu/khôi phục flow login.
}

String tokenType = client.getAccessToken().getTokenType().getValue();
```

Đoạn code minh họa cách sử dụng API, không phải một method độc lập có thể paste chạy ngay. Trong ứng dụng thật, cần xử lý nhánh `client == null` và lỗi provider theo ngữ cảnh. Với OAuth2 Login, principal phải gắn đúng authorized client; không lấy một token của người dùng này để gọi API dưới danh nghĩa người dùng khác.

Khi Client cần gọi API, có thể sử dụng tích hợp `RestClient`/`WebClient` của Spring Security OAuth2 Client với `OAuth2AuthorizedClientManager` thích hợp, thay vì tự ghép header và viết logic refresh trong mỗi controller. Chi tiết tích hợp HTTP client phụ thuộc phiên bản Spring Security đang dùng.

### 10.4. Refresh thất bại thì xử lý thế nào?

Các chiến lược thường gặp:

| Tình huống | Hành vi hợp lý |
|---|---|
| Access token còn hạn | Dùng token hiện tại cho API phù hợp |
| Access token sắp hết hạn, có refresh token hợp lệ | Manager/provider có thể làm mới trước khi gọi API |
| Không có refresh token | Yêu cầu đăng nhập/ủy quyền lại khi cần access token mới |
| Refresh trả `invalid_grant` | Bỏ thông tin refresh không hợp lệ, tránh retry vô hạn; cần reauthorization |
| API trả `401 invalid_token` | Kiểm tra token thực tế, audience, expiry, revocation; có thể cần refresh/relogin |
| API trả `403 insufficient_scope` | Phạm vi không đủ; refresh cùng scope thường không giải quyết được |
| Nhiều request cùng refresh | Cần chiến lược lưu/đồng bộ authorized client và rotation phù hợp |

Không bao giờ gửi refresh token như `Authorization: Bearer` tới downstream API. Refresh token chỉ được gửi tới Token Endpoint (hoặc endpoint được provider quy định cho thao tác tương ứng) và phải được bảo vệ như một credential quan trọng.

## 11. Lưu trữ authorized client trong ứng dụng nhiều instance

Trong ví dụ một máy phát triển, authorized client có thể được giữ trong bộ nhớ hoặc session theo cấu hình Spring Security. Với ứng dụng production nhiều instance, cần quan tâm tới:

- **Session affinity hoặc session store chung:** OAuth2 Login cần giữ liên kết với phiên người dùng qua các redirect.
- **Kho lưu `OAuth2AuthorizedClient`:** ứng dụng phải truy xuất đúng access/refresh token của người dùng và registration.
- **Refresh token rotation:** token mới phải được lưu nguyên vẹn; tránh instance khác tiếp tục dùng token cũ.
- **Bảo vệ dữ liệu:** encryption at rest, access controls, log redaction, chính sách sao lưu và xóa dữ liệu.
- **Logout và revocation:** logout khỏi ứng dụng không luôn tương đương thu hồi token tại Authorization Server; cần hỗ trợ lifecycle rõ ràng.
- **Giới hạn quyền truy cập:** access token cho API A không được vô tình dùng cho API B hay Client khác.

Ví dụ kiến trúc:

```text
Browser ──> Spring MVC + OAuth2 Login
                     |
                     v
               SecurityContext
                     |
                     v
         OAuth2AuthorizedClientRepository
                     |
          Access token + Refresh token
                     |
                     v
       OAuth2AuthorizedClientManager
                     |
          (refresh nếu cần và được phép)
                     |
                     v
          API request với access token
```

Nếu mỗi instance lưu token độc lập và người dùng bị chuyển giữa các node, ứng dụng có thể không tìm thấy authorized client hoặc có phiên token cũ. Chọn cơ chế lưu phù hợp và kiểm tra hành vi khi scale out.

## 12. Các token response thường gặp trong thực tế

### 12.1. OIDC login có refresh token

```json
{
  "access_token": "AT-1",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "refresh_token": "RT-1",
  "id_token": "IDT-1"
}
```

Cách đọc: access token Bearer có thời gian sống được mô tả khoảng một giờ; scope được cấp gồm ba giá trị; Client có refresh token; OIDC login có ID Token để xác minh danh tính.

### 12.2. OIDC login không có refresh token

```json
{
  "access_token": "AT-2",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "openid profile",
  "id_token": "IDT-2"
}
```

Đây vẫn có thể là phản hồi hợp lệ của OIDC Code Flow. Khi access token hết hạn, Client không thể tự refresh chỉ từ response này; cần flow reauthorization hoặc cơ chế nhà cung cấp hỗ trợ.

### 12.3. OAuth2 Client Credentials

```json
{
  "access_token": "SERVICE-AT",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "invoices.read"
}
```

Không có ID Token OIDC hoặc thông tin người dùng đăng nhập. Client có thể xin token mới bằng chính Client Credentials Grant khi cần và được Server cho phép. Refresh token thường không được cấp trong trường hợp này.

### 12.4. Token response sau refresh có rotation

```json
{
  "access_token": "AT-NEW",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email",
  "refresh_token": "RT-NEW"
}
```

Client cần lưu `RT-NEW` theo chính sách rotation, không tự xem `RT-OLD` vẫn sử dụng được. Một phản hồi refresh cũng có thể không mang `refresh_token` mới; khi đó xử lý theo hợp đồng provider và hành vi thư viện OAuth2 Client.

### 12.5. Server không trả scope vì giống request

Authorization request:

```text
scope=openid%20profile%20email
```

Token response:

```json
{
  "access_token": "AT-3",
  "token_type": "Bearer",
  "expires_in": 3600,
  "id_token": "IDT-3"
}
```

Theo quy tắc OAuth2, thiếu `scope` trong response này có thể hợp lệ nếu scope được cấp trùng scope đã yêu cầu. Không suy ra “token không có quyền nào”.

## 13. Lỗi thường gặp khi phân tích token response

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `access_token` không dùng được để gọi API | Token sai audience, scope, resource hoặc đã bị thu hồi/hết hạn | Xem API đích, quyền được cấp, cách Resource Server xác minh |
| `Authorization` header bị từ chối | Ghép `Bearer` hai lần, sai token type hoặc gửi ID Token | Đọc `token_type`, chỉ dùng đúng access token |
| `expires_in=3600` nhưng token hết hạn sớm | Lệch đồng hồ, token bị thu hồi, TTL được tính từ thời điểm cấp sớm hơn | Kiểm tra clock skew, response/API lỗi và chính sách provider |
| `expires_in` bị hiểu như Unix timestamp | Nhầm thời gian tương đối với `exp` của JWT | Dùng `Instant`/expiresAt do Spring quản lý |
| Access token không có dạng JWT | Provider trả opaque token | Không tự decode; để Resource Server introspect/xác minh theo hợp đồng |
| Có `openid` nhưng không có email trong ID Token | Scope yêu cầu không đảm bảo claim; email có thể nằm ở UserInfo | Xem OIDC provider, claim thực tế, consent và scope |
| Token response không có `scope` | Scope được cấp có thể giống scope yêu cầu | Áp dụng RFC6749; kiểm tra hành vi provider |
| Scope chỉ có `read` dù đã yêu cầu `write` | Provider giới hạn quyền được cấp | Không giả định đã có `write`; xử lý cấp quyền phù hợp |
| Không có `refresh_token` | Provider không cấp cho Client/flow này | Kiểm tra chính sách, consent, grant và scope liên quan |
| Refresh trả `invalid_grant` | Token hết hạn, bị thu hồi, đã rotation hoặc thuộc Client khác | Xóa trạng thái hỏng, tránh retry vô hạn, reauthorization |
| Nhiều request cùng refresh thất bại | Rotation + cạnh tranh cập nhật token | Điều phối refresh và cơ chế lưu authorized client |
| Sau logout vẫn gọi được API bằng token cũ | Logout session không tự thu hồi token | Thiết kế revocation/token lifecycle theo provider |
| Login session còn nhưng API trả 401 | Access token không còn được chấp nhận | Phân biệt session và token API; refresh hoặc reauthorization |
| API trả 403 dù token chưa hết hạn | Thiếu scope/role/business authorization | Kiểm tra quyền và audience, không chỉ hạn token |
| Log chứa toàn bộ token response | HTTP logging/debug ghi dữ liệu nhạy cảm | Redact từ nguồn, giảm verbosity, xóa dữ liệu rò rỉ theo quy trình |

### 13.1. Đọc lỗi HTTP của Resource Server đúng cách

Khi Client gọi API bằng Bearer token, lỗi có thể được phản ánh trong `WWW-Authenticate`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

hoặc:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

`invalid_token` có thể là hết hạn, thu hồi hoặc các lý do xác minh token khác. `insufficient_scope` chỉ rõ không đủ quyền; việc refresh một token với cùng tập scope có thể không khắc phục được. Ứng dụng cần phân biệt hai tình huống trước khi quyết định xin token mới hay yêu cầu quyền bổ sung.

## 14. Bài thực hành: đọc và quyết định sử dụng token

### Bài tập 1: Tìm trường bắt buộc và tùy chọn

Cho response:

```json
{
  "access_token": "TOKEN_A",
  "token_type": "Bearer",
  "expires_in": 1200,
  "scope": "reports.read"
}
```

Hãy trả lời:

1. Token được gửi tới API theo scheme nào?
2. `expires_in` có phải Unix timestamp không?
3. Có thể tự động refresh bằng trường nào trong response?
4. Có thể dùng token để ghi báo cáo không?

**Gợi ý đáp án:** Scheme `Bearer`; `expires_in` là số giây tương đối; không có `refresh_token` nên không thể suy ra có khả năng refresh; `reports.read` không chứng minh quyền `reports.write`.

### Bài tập 2: ID Token và Access Token

Một Client nhận `id_token` và `access_token` sau OIDC login. Lập trình viên lấy `id_token` đưa vào `Authorization: Bearer` khi gọi API hóa đơn.

**Gợi ý đáp án:** Sai mục đích. ID Token phục vụ xác minh danh tính tại OIDC Client; API cần access token được cấp cho đúng Resource Server và có quyền phù hợp.

### Bài tập 3: Đồng hồ lệch nhau

Token response có `expires_in=600`. Client ghi nhận `expiresAt≈10:00`, nhưng API call lúc `09:59:59` bị từ chối vì token hết hạn.

**Gợi ý đáp án:** Cần xử lý clock skew, thời gian mạng hoặc revocation; dùng `OAuth2AuthorizedClientManager` và refresh token khi có thay vì đợi đúng giây cuối cùng.

### Bài tập 4: Refresh token rotation

Hai request song song đọc `RT-1`. Request thứ nhất refresh thành công và nhận `RT-2`; request thứ hai thử lại `RT-1` rồi bị từ chối.

**Gợi ý đáp án:** Thiết kế phải cập nhật refresh token mới nhất và điều phối tranh chấp. Không tự retry vô hạn với RT cũ; kiểm tra kho lưu authorized client và logic refresh của các instance.

### Bài tập 5: Đọc metadata bằng Spring

Sau OAuth2 Login thành công, hãy viết một endpoint chỉ trả:

```json
{
  "tokenType": "Bearer",
  "scopes": ["openid", "profile", "email"],
  "refreshTokenAvailable": false
}
```

**Gợi ý:** dùng `OAuth2AuthorizedClient#getAccessToken()`, `getRefreshToken()`; không trả `getTokenValue()`. Nếu API phục vụ người dùng cuối, xem có thực sự cần tiết lộ các metadata này không.

## 15. Các nguyên tắc vận hành và bảo mật cần nhớ

- **`access_token`** là credential để truy cập Resource Server; có thể opaque hoặc JWT và phải dùng đúng audience/scope.
- **`token_type`** cho biết cách trình token; với `Bearer`, cách thường dùng là `Authorization: Bearer ...`.
- **`expires_in`** là thời gian sống tương đối tính bằng giây; khác `exp` của JWT và khác thời hạn HTTP session.
- **`scope`** mô tả quyền được cấp; nếu bị thu hẹp, ứng dụng phải xử lý giới hạn thực tế. Scope không tự trở thành role nội bộ.
- **`refresh_token`** là credential tùy chọn để xin token mới; rất nhạy cảm và có thể bị xoay vòng, hết hạn hoặc thu hồi.
- **OIDC ID Token** xác minh danh tính tại Client, không thay thế access token cho API.
- **Token response là dữ liệu backend nhạy cảm.** Không đẩy toàn bộ token response ra browser, log hoặc URL.
- **Spring Security OAuth2 Client** lưu token qua `OAuth2AuthorizedClient` và có `OAuth2AuthorizedClientManager` để điều phối việc lấy/làm mới authorized client.
- **Hết hạn token API và hết phiên login là hai chuyện riêng.** Thiết kế logout, refresh, reauthorization và quyền truy cập API theo nhu cầu sản phẩm.
- **Không tự parse hay tự làm mới token nếu thư viện đang có cơ chế phù hợp.** Chỉ mở rộng hành vi khi có yêu cầu rõ ràng của provider và đã hiểu giới hạn tương thích.

## 16. Tài liệu tham khảo

1. [RFC 6749, Section 5.1 — Successful Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): `access_token`, `token_type`, `expires_in`, `scope` và `refresh_token`.
2. [RFC 6749, Section 6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): refresh token grant, cách Server phản hồi và khả năng thay refresh token.
3. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): HTTP `Authorization: Bearer`, `invalid_token` và `insufficient_scope`.
4. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Token Endpoint, ID Token, refresh token và ý nghĩa `openid`.
5. [Spring Security Reference — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): cấu hình OAuth2 Client và authorized client.
6. [Spring Security Reference — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): authorization code, refresh token và client credentials.
7. [Spring Security API — OAuth2AccessTokenResponse](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/endpoint/OAuth2AccessTokenResponse.html): đối tượng ánh xạ token response.
8. [Spring Security API — OAuth2AccessToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AccessToken.html): `getTokenType()`, `getScopes()`, `getIssuedAt()` và `getExpiresAt()`.
9. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): access/refresh token và ClientRegistration.
10. [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): quản lý, cấp và làm mới authorized client.

Khi phân tích kết quả Token Endpoint, hãy đọc **token dùng làm gì (`access_token`, `token_type`), còn hiệu lực bao lâu (`expires_in`), được phép làm gì (`scope`), và có cơ chế tiếp tục lấy token mới hay không (`refresh_token`)**. Spring Security giúp lưu và sử dụng những dữ liệu này theo mô hình `OAuth2AuthorizedClient`; phần việc còn lại của ứng dụng là sử dụng token đúng API, kiểm soát quyền và bảo vệ toàn bộ vòng đời của token.
