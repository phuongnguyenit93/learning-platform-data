# Sử dụng request_uri tại Authorization Endpoint

## 1. Từ authorization request dài sang một tham chiếu ngắn

Trong OAuth 2.0 Authorization Code Flow, client thường đưa các tham số như `client_id`, `redirect_uri`, `scope`, `state` và PKCE challenge vào URL mà trình duyệt gửi tới Authorization Endpoint. Cách này đơn giản nhưng có ba hạn chế:

- URL có thể dài, vượt giới hạn của browser, reverse proxy hoặc web server.
- Tham số có thể xuất hiện trong browser history, access log, hệ thống analytics hoặc referrer.
- Người dùng và browser mang một request có thể bị thay đổi trên đường truyền ứng dụng, dù HTTPS vẫn bảo vệ từng kết nối.

**Pushed Authorization Requests (PAR)** theo RFC 9126 giải quyết vấn đề bằng cách để client gửi authorization request trực tiếp tới Authorization Server qua một HTTP POST được xác thực. Server lưu payload, trả về một tham chiếu `request_uri`. Sau đó client chỉ đưa tham chiếu ấy vào Authorization Endpoint thông qua user agent.

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth/OIDC Client
    participant AS as Authorization Server
    participant B as Browser
    participant U as Người dùng
    C->>AS: POST PAR: authorization parameters
    AS->>AS: Authenticate client + validate request
    AS-->>C: 201 + request_uri + expires_in
    C->>B: Mở authorization_endpoint?client_id=...&request_uri=...
    B->>AS: GET Authorization Endpoint với request_uri
    AS->>AS: Tra request đã lưu và kiểm tra binding/expiry
    AS->>AS: Tiếp tục login, consent và authorization
    AS-->>B: Redirect về redirect_uri với code + state
    B-->>C: Callback
    C->>AS: Đổi code tại token endpoint + PKCE verifier
    AS-->>C: Access token / ID token nếu OIDC
```

**Trọng tâm bài học:** `request_uri` trả về từ PAR là một tham chiếu tới authorization request đã được lưu tại server. Khi trình duyệt gọi Authorization Endpoint, server phải nhận diện đúng tham chiếu ấy, khôi phục đúng request và tiếp tục xử lý theo OAuth/OIDC.

Bài thuộc chương **Pushed Authorization Requests** của module học thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OIDC Authorization Server bằng Spring Security và Spring Authorization Server. Người học cần làm được:

1. Phân biệt `request_uri` của PAR với `redirect_uri` và `request_uri` của JWT-Secured Authorization Request (JAR).
2. Mô tả vòng đời từ PAR POST, response `201 Created` đến Authorization Endpoint.
3. Hiểu client binding, thời hạn, tính dùng một lần và hành vi reload browser.
4. Cấu hình endpoint PAR và kiểm tra khả năng hỗ trợ theo phiên bản Spring.
5. Thiết kế chính sách chỉ cho phép authorization request đi qua PAR, nếu sản phẩm yêu cầu.
6. Kiểm thử request hợp lệ, URI sai/hết hạn, request URI bị tráo, replay và nhiều instance.

## 2. Phân biệt các URI dễ nhầm

| Giá trị | Vai trò | Ví dụ | Ai sử dụng? |
| --- | --- | --- | --- |
| `authorization_endpoint` | Endpoint nhận yêu cầu authorization qua user agent | `https://auth.example.com/oauth2/authorize` | Browser/client |
| `pushed_authorization_request_endpoint` | Endpoint nhận payload PAR trực tiếp qua back channel | `https://auth.example.com/oauth2/par` | Client gọi server-to-server |
| `request_uri` do PAR trả về | Tham chiếu ngắn, opaque tới request được server lưu | `urn:ietf:params:oauth:request_uri:abc...` | Client đưa vào Authorization Endpoint |
| `redirect_uri` | Callback đã đăng ký của client, nơi server trả kết quả authorization | `https://portal.example.com/login/oauth2/code/portal` | Authorization Server redirect browser |
| `request_uri` của JAR/OIDC Request Object | Tham chiếu tới Request Object được client lưu tại một URI theo cơ chế JAR/OIDC | Có thể là HTTPS URI được đăng ký | Authorization Server có thể cần lấy Request Object theo profile |

**`request_uri` không phải `redirect_uri`.** Một giá trị chỉ đường tới dữ liệu authorization request đã được đẩy lên AS; giá trị kia chỉ địa chỉ callback mà AS được phép chuyển trình duyệt tới.

### 2.1. PAR request_uri và JAR request_uri cùng tên nhưng khác semantics

JAR (RFC 9101) cho phép gửi một Request Object ký số, có thể mã hóa, trực tiếp qua tham số `request` hoặc tham chiếu qua `request_uri`. PAR (RFC 9126) tạo `request_uri` của chính Authorization Server sau khi client đẩy request tới PAR endpoint.

Trong PAR:
- Server tạo tham chiếu và lưu payload theo cơ chế nội bộ.
- Client nhận tham chiếu từ response của PAR endpoint.
- Client dùng tham chiếu đó tại chính Authorization Server.
- Server không cần công bố payload qua một URL mà bên khác có thể tải.

Trong JAR:
- Client tạo Request Object theo profile JAR.
- Request Object có thể được truyền trực tiếp hoặc tham chiếu theo cơ chế JAR.
- Việc xác minh chữ ký, issuer, audience, expiry và quy tắc Request Object là trách nhiệm riêng.

RFC 9126 xác định `request_uri` được trả từ PAR có thể dùng tại Authorization Endpoint **bất kể** metadata OIDC `request_uri_parameter_supported` hoặc `require_request_uri_registration`. Không được dùng hai metadata OIDC đó để suy luận rằng PAR request URI bị cấm hay phải đăng ký trước.

## 3. Vòng đời request_uri theo RFC 9126

### 3.1. Client đẩy authorization request

Client gửi HTTP **POST** tới PAR endpoint. Body dùng `application/x-www-form-urlencoded` với UTF-8. PAR endpoint phải dùng HTTPS. Các tham số thường bao gồm:

- `response_type=code`;
- `client_id`;
- `redirect_uri`;
- `scope`;
- `state`;
- `code_challenge` và `code_challenge_method=S256` khi dùng PKCE;
- `nonce` nếu là OIDC và client cần kiểm tra nonce;
- Các tham số mở rộng như `claims`, `resource` hoặc Request Object theo profile hỗ trợ.

PAR endpoint áp dụng quy tắc xác thực client như token endpoint. Với confidential client, dùng đúng phương thức đã đăng ký, chẳng hạn `client_secret_basic`, `private_key_jwt` hoặc mTLS nếu hệ thống hỗ trợ. Với public client, tuân theo cơ chế client authentication/nhận diện được đăng ký; không nhúng một client secret giả vào ứng dụng mobile hoặc SPA.

**PAR request không được chứa `request_uri`**: client đang tạo một request mới, không gửi tham chiếu PAR đã có để tạo lồng nhau.

### 3.2. Server xác thực và trả tham chiếu

Nếu xử lý thành công, PAR endpoint trả HTTP `201 Created` cùng JSON body:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-cache, no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:Qx7d9mR8...",
  "expires_in": 90
}
```

Các điểm bắt buộc cần nhớ:

- `request_uri` là tham chiếu duy nhất cho authorization request đã gửi.
- Giá trị phải chứa thành phần được sinh bằng thuật toán giả ngẫu nhiên mật mã mạnh, không thể đoán thực tế.
- `request_uri` **MUST be bound to the client** đã gửi PAR request.
- `expires_in` là thời hạn tính bằng giây, số nguyên dương; RFC gợi ý khoảng ngắn, thường 5–600 giây, nhưng server quyết định theo policy.
- Response có `Cache-Control: no-cache, no-store` để tránh lưu response chứa tham chiếu nhạy cảm ngoài ý muốn.

Server có thể dùng namespace URN `urn:ietf:params:oauth:request_uri:`, nhưng client phải coi giá trị là **opaque** và dùng nguyên văn. Không tự cắt prefix, giải mã phần đuôi, tạo lại URI hoặc suy đoán endpoint nội bộ từ nó.

### 3.3. Client dùng request_uri tại Authorization Endpoint

Client điều hướng browser tới Authorization Endpoint. Ví dụ theo RFC:

```http
GET /oauth2/authorize?client_id=portal-web
  &request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AQx7d9mR8...
Host: auth.example.com
```

Request trình duyệt chỉ cần mang `client_id` và `request_uri` trong ví dụ này. Các tham số như `redirect_uri`, `scope`, `state` và PKCE challenge đã nằm trong payload mà client gửi ở PAR request. Authorization Server phải lấy lại payload gốc, đối chiếu client binding và tiếp tục xử lý nó.

**Không gửi một bộ tham số mới mâu thuẫn với payload đã đẩy.** Ví dụ, client không được đổi `redirect_uri` hoặc `scope` bằng cách nối thêm giá trị khác vào URL để sửa nội dung request đã được xác thực. Client nên tuân theo mẫu tối thiểu và cách ghép tham số mà RFC/profile của server quy định.

### 3.4. Request URI hết hạn hoặc bị sử dụng lại

RFC 9126 phân biệt trách nhiệm client và server:

| Hành vi | Yêu cầu |
| --- | --- |
| Client dùng một `request_uri` nhiều lần | Client **MUST** chỉ sử dụng mỗi giá trị một lần |
| Authorization Server nhận lại cùng `request_uri` | Server **SHOULD** xử lý như một lần sử dụng; server **MAY** cho phép duplicate do người dùng reload/refresh user agent |
| `request_uri` hết hạn | Server **MUST** từ chối như một tham chiếu không hợp lệ |
| `request_uri` thuộc client A nhưng được client B dùng | Server phải từ chối do client binding không khớp |
| `request_uri` không do PAR endpoint của server phát hành | Server không được coi nó là một pushed request hợp lệ |

Ngoại lệ cho browser reload không có nghĩa client được phép cố ý gửi lại cùng URI để bắt đầu một authorization transaction mới. Client vẫn phải tuân thủ yêu cầu dùng một lần. Nếu server cho phép duplicate để phục hồi thao tác reload, hành vi đó cần có kiểm soát, không được biến thành khả năng replay vô hạn.

## 4. Ví dụ đầy đủ từ client tới callback

Giả sử có:

```text
Authorization Server:
  issuer = https://auth.example.com
  PAR endpoint = https://auth.example.com/oauth2/par
  Authorization endpoint = https://auth.example.com/oauth2/authorize

Client:
  client_id = portal-web
  redirect_uri = https://portal.example.com/login/oauth2/code/portal

Yêu cầu:
  response_type = code
  scope = openid profile orders.read
  state = STATE_FOR_THIS_TRANSACTION
  code_challenge = S256_CHALLENGE
```

### 4.1. Bước 1 — phát hiện endpoint qua metadata

Client lấy metadata của Authorization Server qua OAuth Authorization Server Metadata (RFC 8414) hoặc OIDC Discovery tùy issuer/deployment. Metadata PAR có trường:

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "pushed_authorization_request_endpoint": "https://auth.example.com/oauth2/par"
}
```

Đây là JSON giản lược. Trong response thật có thể có thêm token endpoint, JWK Set URI, các phương thức xác thực client và những metadata khác.

Sự hiện diện của `pushed_authorization_request_endpoint` cho biết server có thể nhận PAR. Trường `require_pushed_authorization_requests` là tín hiệu bổ sung về policy bắt buộc PAR; nếu vắng mặt, RFC 9126 định nghĩa mặc định là `false`.

### 4.2. Bước 2 — POST payload đến PAR endpoint

Ví dụ request với client authentication Basic:

```http
POST /oauth2/par HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_PORTAL_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

response_type=code
&client_id=portal-web
&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal
&scope=openid%20profile%20orders.read
&state=STATE_FOR_THIS_TRANSACTION
&code_challenge=S256_CHALLENGE
&code_challenge_method=S256
&nonce=NONCE_FOR_THIS_OIDC_TRANSACTION
```

`BASE64_PORTAL_CLIENT_CREDENTIALS`, `STATE_FOR_THIS_TRANSACTION`, `S256_CHALLENGE` và `NONCE_FOR_THIS_OIDC_TRANSACTION` là placeholder. Body thật phải URL-encode đúng; không đưa secret vào query string. Với `private_key_jwt`, client gửi `client_assertion_type` và `client_assertion` theo profile client authentication.

### 4.3. Bước 3 — nhận request_uri và expires_in

```json
{
  "request_uri": "urn:ietf:params:oauth:request_uri:Qx7d9mR8f4...",
  "expires_in": 90
}
```

Client lưu tham chiếu trong transaction hiện tại đủ để điều hướng browser. Không lưu chung vào một biến toàn cục dùng cho mọi tab/người dùng. Nếu nhiều login transaction diễn ra đồng thời, mỗi transaction phải giữ request URI, state và context của chính nó.

### 4.4. Bước 4 — điều hướng browser

Client tạo URL theo endpoint metadata:

```text
https://auth.example.com/oauth2/authorize
    ?client_id=portal-web
    &request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AQx7d9mR8f4...
```

Không cần gửi lại toàn bộ scope, redirect URI, PKCE challenge hoặc nonce trong URL. Đây là lợi ích quan trọng của PAR: payload authorization đi trực tiếp từ client tới server qua HTTPS, còn browser chỉ mang tham chiếu ngắn.

### 4.5. Bước 5 — Authorization Server xử lý request đã push

Authorization Server phải:

1. Nhận `client_id` và `request_uri`.
2. Tìm tham chiếu trong kho request PAR.
3. Xác nhận tham chiếu còn hạn và thuộc đúng client.
4. Khôi phục authorization request đã lưu.
5. Kiểm tra request theo các quy tắc Authorization Endpoint như một authorization request bình thường.
6. Thực hiện xác thực người dùng, consent, chính sách scope và các bước OIDC/OAuth tiếp theo.
7. Trả kết quả qua `redirect_uri` đã được xác minh, thường là authorization code cùng `state`.

Server **MUST** validate authorization request phát sinh từ PAR như các request khác. RFC cho phép bỏ qua một số kiểm tra lặp lại khi server chứng minh dữ liệu/policy không đổi; đó là tối ưu có điều kiện, không phải mặc định “đã push thì tin toàn bộ”.

### 4.6. Bước 6 — callback và token exchange vẫn diễn ra bình thường

Sau khi nhận code và state tại callback, client vẫn phải kiểm tra state/transaction rồi đổi code tại token endpoint bằng `code_verifier` của giao dịch tương ứng. **PAR không thay thế PKCE, state, nonce, client authentication, redirect URI validation hoặc consent.**

## 5. Bảo vệ client assertion khi xác thực PAR

PAR endpoint dùng cùng quy tắc client authentication áp dụng cho token endpoint. Nhiều confidential client sử dụng `private_key_jwt` hoặc `client_secret_jwt` để xác thực trực tiếp với PAR endpoint.

**Cập nhật chuẩn mới cần lưu ý:** RFC 10070, được công bố tháng 11/2026, đã cập nhật RFC 9126 về audience của JWT client authentication assertion. Với JWT client assertion dùng tại PAR endpoint:

- `aud` **MUST** là duy nhất giá trị issuer identifier URL của Authorization Server theo RFC 8414.
- Authorization Server **MUST** từ chối assertion không chứa chính issuer identifier của mình làm audience duy nhất.
- Client assertion JWT **SHOULD** có explicit type `client-authentication+jwt` hoặc type cụ thể hơn do profile định nghĩa.
- Server **NOT RECOMMENDED** từ chối chỉ vì thiếu explicit `typ`, nhằm tránh phá tương thích với client đã tuân thủ audience mới nhưng chưa thêm type.

Điểm này thay đổi ví dụ audience cũ của RFC 9126, vốn từng cho phép nhiều cách biểu diễn endpoint. Khi cấu hình `private_key_jwt` cho PAR, hãy dùng issuer identifier chính xác của AS làm audience duy nhất; không mặc định dùng riêng URL `/oauth2/par` hoặc `/oauth2/token` làm audience.

```json
{
  "iss": "portal-web",
  "sub": "portal-web",
  "aud": "https://auth.example.com",
  "exp": 1794859200,
  "jti": "UNIQUE_ASSERTION_ID"
}
```

Payload trên chỉ minh họa các claim quan trọng; JWT thật cần được ký bằng khóa đã đăng ký, có thời hạn ngắn, `jti` phù hợp chính sách chống replay và header/claims tuân thủ profile. Giá trị `aud` là issuer identifier của AS, không phải request URI do PAR trả.

## 6. request_uri là tham chiếu opaque và phải được bảo vệ

### 6.1. Không tải request_uri như một URL bên ngoài

Một lỗi triển khai là nhìn `request_uri` như URL mà server phải gọi HTTP GET. Với PAR, server **đã sở hữu dữ liệu request** và chỉ cần tra cứu nó trong kho lưu trữ nội bộ. Không fetch URI do client/browser gửi tùy ý.

Điều này tránh các rủi ro:
- SSRF tới địa chỉ nội bộ hoặc metadata endpoint ngoài dự kiến.
- Gửi credential/header tới host không tin cậy.
- Redirect chain khiến server truy cập tài nguyên ngoài allowlist.
- Phân biệt nhầm PAR URN với JAR Request Object URI.

Nếu server hỗ trợ cả PAR và JAR, phải phân loại rõ loại tham chiếu, áp dụng cơ chế tin cậy tương ứng và không dùng fallback kiểu “không tìm thấy trong PAR thì thử fetch URL này”.

### 6.2. Client binding

Mỗi `request_uri` phải gắn với client đã đẩy request. Khi Authorization Endpoint nhận `client_id` cùng `request_uri`, server phải xác minh:

```text
request.client_id == par_record.registered_client_id / client_id đã lưu
```

Không cho client B dùng request URI của client A, kể cả hai client cùng có redirect URI hoặc scope. Không chỉ kiểm tra chuỗi `client_id` trong query: phải đối chiếu với client binding trong bản ghi PAR đã được server tạo và lưu.

### 6.3. Entropy, expiration và storage

Server cần:
- Sinh reference không thể đoán thực tế bằng CSPRNG.
- Giới hạn TTL ngắn và trả `expires_in` tương ứng.
- Lưu request parameters theo một cơ chế có thể truy cập bởi mọi instance.
- Đánh dấu trạng thái đã dùng hoặc xử lý duplicate theo policy.
- Xóa dữ liệu hết hạn sau một khoảng retention hợp lý.
- Không để request URI trở thành khóa tuần tự, UUID đoán được hoặc ID nội bộ có thể liệt kê.

Có thể lưu record theo dạng:

```text
request_uri_fingerprint
registered_client_id
authorization_request_payload
created_at
expires_at
status: ACTIVE | CONSUMED
consumed_at
```

Đây là mô hình dữ liệu minh họa, không phải schema mặc định được SAS công bố. Nếu dùng fingerprint thay cho request URI gốc, cần thiết kế cách tra cứu nhất quán; payload phải được bảo vệ như dữ liệu authorization nhạy cảm.

### 6.4. Chống request_uri swapping

Một request URI được chụp từ transaction A có thể bị đưa vào transaction B. Ví dụ, request A yêu cầu mức xác thực cao, request B yêu cầu mức thấp hơn; attacker cố làm browser của B sử dụng request URI của A hoặc ngược lại.

RFC 9126 khuyến nghị client dùng các cơ chế ràng buộc transaction như:
- `state` ngẫu nhiên theo transaction;
- PKCE với verifier/challenge riêng;
- OIDC `nonce` khi cần.

Request URI binding theo client không tự ràng buộc tất cả ngữ cảnh của browser transaction. Client vẫn phải kiểm tra state/PKCE/nonce đúng giao dịch.

## 7. Chính sách PAR bắt buộc và metadata

RFC 9126 định nghĩa hai metadata có tên giống nhau nhưng phạm vi khác nhau:

| Metadata | Nơi công bố | Ý nghĩa |
| --- | --- | --- |
| `pushed_authorization_request_endpoint` | Authorization Server Metadata | URL của PAR endpoint |
| `require_pushed_authorization_requests` | Authorization Server Metadata | AS chỉ nhận authorization request qua PAR khi giá trị là `true` |
| `require_pushed_authorization_requests` | Client Metadata | Client cụ thể chỉ được khởi tạo authorization qua PAR khi giá trị là `true` |

Nếu metadata `require_pushed_authorization_requests` vắng mặt, mặc định của RFC là `false`. AS có thể áp policy toàn cục hoặc theo từng client. Khi bắt buộc PAR, Authorization Endpoint phải từ chối authorization request không có `request_uri` được cấp từ PAR endpoint, thường bằng `invalid_request`.

**Không nhầm ba cờ:**
- `pushed_authorization_request_endpoint` nói rằng server **có endpoint PAR**.
- `require_pushed_authorization_requests` nói rằng PAR **có bắt buộc hay không**.
- `request_uri_parameter_supported` và `require_request_uri_registration` thuộc metadata OIDC/JAR, không thay thế metadata PAR.

### 7.1. Khả năng và giới hạn cần kiểm tra ở Spring Authorization Server

Tại thời điểm viết bài:
- Spring Authorization Server **1.5** là nhánh bổ sung hỗ trợ PAR; release 1.5 GA công bố hỗ trợ RFC 9126.
- SAS **1.5.8** có `OAuth2PushedAuthorizationRequestEndpointConfigurer`, `OAuth2PushedAuthorizationRequestEndpointFilter`, `OAuth2PushedAuthorizationRequestAuthenticationProvider` và `OAuth2PushedAuthorizationRequestAuthenticationToken`.
- `AuthorizationServerSettings.getPushedAuthorizationRequestEndpoint()` có từ SAS **1.5**, mặc định là `/oauth2/par`.
- Spring Security **7.0+** có các lớp Authorization Server PAR tương ứng; Javadoc đánh dấu provider từ 7.0.
- SAS **1.4.x và trước đó** không có PAR endpoint tích hợp theo release notes 1.5; cần nâng phiên bản hoặc tự triển khai grant/endpoint theo RFC nếu chưa thể nâng.

Tài liệu Protocol Endpoints của SAS 1.5.8 mô tả endpoint, converter, provider, response handler và custom validator. Tài liệu cũng trình bày validation mặc định cho `redirect_uri` và `scope`.

**Điểm cần xác minh riêng:** sự hiện diện của endpoint và metadata URL không tự chứng minh server đã bật chế độ **PAR-only**. Reference 1.5.8 mô tả cấu hình endpoint PAR nhưng không đưa ra một cờ cấu hình riêng tương đương `require_pushed_authorization_requests` trong phần endpoint được tài liệu hóa. Nếu sản phẩm bắt buộc PAR, hãy kiểm tra metadata discovery thực tế, triển khai enforcement cho client/server và viết test chứng minh authorization request thường bị từ chối.

## 8. Cấu hình PAR trong Spring Authorization Server 1.5.x

### 8.1. AuthorizationServerSettings

SAS 1.5.x có endpoint mặc định:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .authorizationEndpoint("/oauth2/authorize")
            .pushedAuthorizationRequestEndpoint("/oauth2/par")
            .tokenEndpoint("/oauth2/token")
            .build();
}
```

`AuthorizationServerSettings` là thành phần cấu hình bắt buộc của Authorization Server. Nếu dùng cấu hình mặc định được import, SAS có thể tự đăng ký bean settings; khai báo rõ ràng khi cần cố định issuer và đường dẫn endpoint. Nếu đổi path PAR, metadata phải phản ánh URL mới để client gọi đúng endpoint.

### 8.2. Bật endpoint PAR và extension point

Ví dụ theo API SAS 1.5.x:

```java
@Bean
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .pushedAuthorizationRequestEndpoint(par -> par
                .authenticationProviders(configureParValidation())
            )
        );

    return http.build();
}
```

Đây là phần cấu hình tập trung vào PAR, không phải toàn bộ Authorization Server. Ứng dụng vẫn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, JWK signing key, issuer, client authentication và security chain cho user login.

### 8.3. Giữ validator mặc định khi bổ sung policy

SAS 1.5.8 cho phép tùy chỉnh `OAuth2PushedAuthorizationRequestAuthenticationProvider` bằng `setAuthenticationValidator`. Default validator kiểm tra redirect URI và scope. Nếu thêm policy riêng, hãy nối thêm thay vì vô tình xóa các kiểm tra này.

Ví dụ:

```java
private Consumer<List<AuthenticationProvider>> configureParValidation() {
    return providers -> providers.forEach(provider -> {
        if (provider instanceof OAuth2PushedAuthorizationRequestAuthenticationProvider parProvider) {
            Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
                    OAuth2AuthorizationCodeRequestAuthenticationValidator
                            .DEFAULT_REDIRECT_URI_VALIDATOR
                    .andThen(OAuth2AuthorizationCodeRequestAuthenticationValidator
                            .DEFAULT_SCOPE_VALIDATOR)
                    .andThen(context -> {
                        RegisteredClient client = context.getRegisteredClient();

                        // Policy nghiệp vụ bổ sung, ví dụ:
                        // - client có được dùng PAR cho flow này?
                        // - scope nhạy cảm có cần điều kiện bổ sung?
                        // - redirect URI có đáp ứng chính sách tenant?
                        validateParBusinessPolicy(client, context.getAuthentication());
                    });

            parProvider.setAuthenticationValidator(validator);
        }
    });
}
```

`validateParBusinessPolicy` là hàm nghiệp vụ do ứng dụng tự triển khai. Mẫu code không thay thế xác thực client của endpoint, binding request URI, kiểm tra expiry hay validation tại Authorization Endpoint. Không nới lỏng redirect URI chỉ vì request đã đi qua PAR; RFC cho phép AS có policy riêng đối với redirect URI động của confidential client đã xác thực, nhưng việc đó phải được thiết kế rõ ràng, giới hạn và kiểm thử.

### 8.4. PAR-only policy cần được thực thi ở Authorization Endpoint

Nếu yêu cầu tất cả authorization request của một client phải đi qua PAR, chỉ kiểm tra endpoint PAR hoạt động là chưa đủ. Authorization Endpoint cần xác minh request có `request_uri` hợp lệ do chính server cấp, gắn với client và chưa hết hạn.

Thiết kế enforcement cần bảo đảm:
1. Request thường không có `request_uri` bị từ chối với `invalid_request` khi client/server bắt buộc PAR.
2. `request_uri` không được đoán, tự tạo hoặc lấy từ JAR URI bên ngoài thay cho PAR.
3. Client binding được kiểm tra trong kho request.
4. TTL và trạng thái sử dụng được kiểm tra.
5. Không có đường xử lý khác (ví dụ custom converter hoặc endpoint phụ) bỏ qua policy.
6. Metadata `require_pushed_authorization_requests` được công bố nhất quán với policy đang thực thi.

Vì API/cấu hình cho policy PAR-only có thể khác giữa các phiên bản, không sao chép một property tự đặt rồi cho rằng framework đã tự enforce. Nếu cần, xây policy qua extension point phù hợp của Authorization Endpoint hoặc lớp filter/policy tích hợp có kiểm thử; giữ nguyên provider mặc định và không tạo đường vòng cấp authorization code.


## 9. Các kiểm tra tại Authorization Endpoint vẫn cần thiết

PAR cho phép AS kiểm tra sớm, nhưng authorization request vẫn phải được xử lý theo OAuth/OIDC. Khi nhận `request_uri`, server cần bảo đảm:

- Tham chiếu tồn tại trong kho PAR của chính issuer.
- Client trong authorization request khớp client đã push.
- Request chưa hết hạn.
- Request chưa bị tiêu thụ, hoặc duplicate thuộc trường hợp reload được policy cho phép.
- Redirect URI hợp lệ theo client registration/policy.
- Response type và grant được hỗ trợ.
- Scope được client đăng ký và được policy cho phép.
- PKCE challenge/method đúng chính sách.
- `state`, `nonce` và các tham số mở rộng vẫn thuộc request đã lưu.
- Consent và xác thực người dùng được thực hiện theo policy.
- Client policy chưa thay đổi theo cách làm request trở nên không còn hợp lệ.

Không được bỏ các kiểm tra authorization chỉ vì PAR endpoint đã chấp nhận payload. RFC cho phép bỏ một số kiểm tra lặp lại khi server chứng minh dữ liệu/policy không đổi; đó là tối ưu có điều kiện, không phải mặc định “đã push thì tin toàn bộ”.

## 10. Lỗi và hành vi phản hồi

| Tình huống | Hành vi/lỗi phù hợp |
| --- | --- |
| PAR body thiếu tham số bắt buộc hoặc sai định dạng | `invalid_request` |
| Client authentication sai hoặc thiếu credential bắt buộc | `invalid_client` |
| Client không được phép dùng response type/grant tương ứng | `unauthorized_client` hoặc `unsupported_response_type` tùy nguyên nhân |
| Scope không được phép | `invalid_scope` |
| Redirect URI không hợp lệ | `invalid_request`; không redirect về URI chưa xác minh |
| HTTP method không phải POST tại PAR endpoint | HTTP `405 Method Not Allowed` |
| Payload vượt giới hạn server | HTTP `413 Payload Too Large` |
| Client gửi quá nhiều PAR request | Có thể trả HTTP `429 Too Many Requests` |
| request_uri hết hạn hoặc không tồn tại | Từ chối tại Authorization Endpoint, thường là `invalid_request` |
| request_uri thuộc client khác | Từ chối, không tiết lộ request của client khác |
| Authorization request không dùng PAR khi PAR-only bắt buộc | `invalid_request` |
| Request URI bị sử dụng lại | Từ chối theo one-time policy; ngoại lệ reload phải được kiểm soát |

Thông báo lỗi cho client không nên tiết lộ nội dung payload, user, scope nhạy cảm hoặc trạng thái chi tiết của request URI. Log nội bộ có thể dùng correlation ID và phân loại nguyên nhân, nhưng không ghi raw request_uri, state, client assertion hay dữ liệu nhạy cảm.

## 11. Bảo mật và vận hành

### 11.1. Request URI guessing và request URI replay

Một attacker có thể cố đoán request URI hoặc replay một giá trị đã chụp được. Server cần entropy cao, TTL ngắn, client binding và one-time policy. Không dùng số thứ tự, timestamp, UUID không đủ ngẫu nhiên hoặc ID database tuần tự làm toàn bộ giá trị công khai.

### 11.2. Request URI swapping

Một request URI được chụp từ transaction A có thể bị đưa vào transaction B. Dùng `state` ngẫu nhiên theo transaction, PKCE challenge riêng và OIDC nonce khi cần. Client phải kiểm tra state tại callback; AS phải kiểm tra client binding và không cho request URI bị tráo giữa client.

### 11.3. Open redirect và redirect URI động

PAR cho phép AS xác thực client trước khi tương tác người dùng. RFC 9126 cho phép AS có thể nới quy tắc exact-match redirect URI đối với client đã thiết lập credential, ví dụ cho phép URI theo transaction. Đây là **quyền lựa chọn của AS**, không phải yêu cầu phải mở redirect động.

Nếu cho phép:
- Chỉ áp dụng với confidential client đã xác thực mạnh.
- Giới hạn scheme/host/path hoặc quy tắc biến đổi query theo policy.
- Không cho phép URI từ domain tùy ý.
- Kiểm tra open redirect phía client.
- Ghi audit khi redirect URI động được chấp nhận.

Với cấu hình thông thường, giữ redirect URI đã đăng ký và so khớp chính xác là lựa chọn dễ kiểm soát.

### 11.4. Không log payload PAR nguyên vẹn

Payload có thể chứa scope, state, nonce, claims, login hint hoặc dữ liệu giao dịch nhạy cảm. PAR giảm việc đưa dữ liệu qua browser URL nhưng không ngăn AS, reverse proxy hoặc APM ghi lại request body. Hãy:
- Che hoặc loại body PAR khỏi access log.
- Không ghi request_uri, state, nonce, client assertion và token thô.
- Hạn chế quyền đọc kho PAR.
- Mã hóa dữ liệu lưu khi cần theo chính sách dữ liệu.
- Đặt TTL và cleanup để không giữ payload lâu hơn yêu cầu.
- Kiểm soát kích thước payload và rate limit endpoint.

### 11.5. Nhiều instance và cleanup

Khi AS chạy nhiều instance, PAR record phải được lưu trong kho dùng chung hoặc một cơ chế chia sẻ có tính nhất quán. Nếu node A tạo request URI nhưng browser chuyển sang node B mà node B không tra được, luồng sẽ thất bại ngẫu nhiên.

Thiết kế storage cần:
- Cùng một namespace issuer/client.
- Tra cứu theo request URI/fingerprint.
- Kiểm tra client binding và expiry ở mọi instance.
- Cập nhật trạng thái consumed có kiểm soát cạnh tranh.
- TTL/cleanup và metrics cho record hết hạn.
- Khả năng phục hồi sau restart và failover.

### 11.6. Client assertion audience sau RFC 10070

Với `private_key_jwt` hoặc `client_secret_jwt` dùng ở PAR endpoint, hãy cập nhật client và AS theo RFC 10070: `aud` duy nhất là issuer identifier của AS. Các cấu hình cũ dùng token endpoint hoặc PAR endpoint làm audience cần được rà soát và chuyển đổi. Khi triển khai theo nhiều issuer/tenant, mỗi assertion phải nhắm đúng issuer tương ứng với client transaction.

## 12. Kiểm thử PAR và request_uri

### 12.1. Ma trận kiểm thử chức năng

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| PAR hợp lệ | POST đúng body và client authentication | `201 Created` với `request_uri` và `expires_in` |
| Discovery | Đọc Authorization Server metadata | Có `pushed_authorization_request_endpoint` đúng URL |
| Authorization qua PAR | Gọi Authorization Endpoint bằng client_id + request_uri | Khôi phục đúng request và tiếp tục flow |
| URI client A dùng với client B | Thay client_id ở Authorization Endpoint | Từ chối do binding |
| URI hết hạn | Đợi quá `expires_in` | Từ chối |
| URI không tồn tại | Gửi chuỗi ngẫu nhiên | Từ chối |
| URI đoán được | Thử ID tuần tự/giá trị giả | Không tìm được request hợp lệ |
| PAR request lặp | Gửi lại body PAR mới | Mỗi request được cấp tham chiếu riêng hoặc policy xử lý rõ |
| Request URI replay | Dùng lại cùng request_uri sau khi đã tiêu thụ | Từ chối theo policy |
| Browser reload | Reload authorization URL trong giới hạn policy | Hành vi duplicate có kiểm soát; không tạo code/token ngoài dự kiến |
| Client không auth | Bỏ client credential khi method yêu cầu | `invalid_client` |
| Client auth sai | Secret/assertion không hợp lệ | Từ chối |
| Redirect URI sai | Push redirect URI ngoài policy | Từ chối ngay ở PAR hoặc ở Authorization Endpoint nếu validation được trì hoãn |
| Scope ngoài quyền | Push scope chưa đăng ký | Từ chối |
| request_uri trong PAR body | Gửi request_uri khi tạo PAR mới | Từ chối theo RFC |
| Không có request_uri ở PAR-only mode | Gọi Authorization Endpoint bằng tham số truyền thống | `invalid_request` |
| Request URI từ JAR | Gửi HTTPS JAR URI thay cho PAR handle khi client bắt buộc PAR | Từ chối nếu policy chỉ cho PAR |
| State/PKCE/nonce | Thay giá trị ở callback hoặc transaction khác | Client từ chối; không hoàn tất đăng nhập sai transaction |

### 12.2. Kiểm thử bảo mật và vận hành

| Test | Mục tiêu |
| --- | --- |
| Hai client cùng dùng request_uri | Không thể truy cập request của client khác |
| Hai browser session cùng client | Không tráo state/nonce/PKCE giữa hai transaction |
| Request URI bị replay đồng thời | Chỉ hành vi được policy cho phép xảy ra; không phát sinh hai authorization code ngoài ý muốn |
| Hai instance xử lý cùng URI | Binding, expiry và consumed state nhất quán |
| Restart giữa PAR POST và browser redirect | Record còn hiệu lực trong TTL nếu storage được thiết kế bền vững |
| Database/cache lỗi | Không chấp nhận request URI khi không xác minh được binding/expiry |
| Payload lớn | Bị giới hạn và trả lỗi phù hợp, không gây cạn bộ nhớ |
| Burst PAR request | Rate limit hoạt động, có telemetry |
| Log inspection | Không lộ state, nonce, client assertion, payload nhạy cảm hoặc request_uri |
| RFC 10070 client assertion | Audience là duy nhất issuer identifier; assertion nhắm issuer khác bị từ chối |
| Metadata PAR-only | Metadata phản ánh đúng policy và Authorization Endpoint thực thi policy đó |
| Client policy thay đổi sau PAR | Request được đánh giá lại khi cần; không dùng quyền cũ trái policy mới |

### 12.3. Test callback vẫn cần thiết

PAR không thay thế các test của Authorization Code Flow:
- State khớp transaction.
- PKCE verifier khớp challenge đã lưu trong request.
- Redirect URI đúng.
- Authorization code một lần.
- OIDC nonce và ID token được xác minh.
- Token endpoint client authentication phù hợp.

## 13. Lỗi tích hợp thường gặp

**Lỗi 1 — gửi toàn bộ request parameters lại tại Authorization Endpoint.** Client đã push payload nhưng vẫn nối scope, redirect_uri hoặc state mới vào URL. Điều này tạo mơ hồ và có thể khiến client/server xử lý hai nguồn tham số khác nhau. Hãy dùng request_uri làm tham chiếu và tuân theo cấu trúc request của RFC.

**Lỗi 2 — coi request_uri là redirect_uri.** Một bên trỏ tới payload đã lưu, một bên là callback client. Hai giá trị không thay thế nhau.

**Lỗi 3 — client tự tạo request_uri.** Request URI phải được server cấp sau khi xác thực và lưu PAR request. Client không được đoán hoặc tự dựng giá trị.

**Lỗi 4 — fetch request_uri qua HTTP GET.** PAR URI là handle tra cứu nội bộ. Không fetch tùy ý để tránh SSRF và lẫn với JAR.

**Lỗi 5 — không kiểm tra client binding.** Một client khác có thể dùng tham chiếu của client gốc. Phải xác minh với record server đã lưu.

**Lỗi 6 — nghĩ PAR tự động bắt buộc cho mọi client.** Có endpoint PAR không đồng nghĩa metadata/policy đã đặt `require_pushed_authorization_requests=true`. Phải xác minh cả discovery và enforcement.

**Lỗi 7 — bỏ PKCE vì PAR đã xác thực client.** PAR bảo vệ authorization request trên back channel; PKCE vẫn ràng buộc authorization code với client transaction.

**Lỗi 8 — chỉ validate ở PAR endpoint.** Client policy hoặc redirect URI có thể thay đổi trước khi browser tới Authorization Endpoint. Server phải bảo đảm các kiểm tra cần thiết vẫn còn hiệu lực.

**Lỗi 9 — cho phép request_uri dùng lại vô hạn để hỗ trợ refresh browser.** RFC chỉ cho phép AS có thể hỗ trợ duplicate do reload; client vẫn phải dùng một lần. Hãy giới hạn số lần, thời gian và trạng thái.

**Lỗi 10 — dùng JWT client assertion với audience cũ.** Cấu hình `aud` là URL PAR endpoint hoặc token endpoint không còn phù hợp sau cập nhật RFC 10070; dùng issuer identifier duy nhất của AS.

## 14. Bài tập tình huống

Một Authorization Server có issuer `https://auth.example.com`, PAR endpoint `/oauth2/par` và Authorization Endpoint `/oauth2/authorize`. Client `portal-web` gửi một authorization request chứa `scope=openid orders.read`, `state`, PKCE challenge và OIDC nonce. Server trả `request_uri` có `expires_in=60`.

Hãy phân tích các tình huống:

1. Client gửi browser tới Authorization Endpoint với `client_id` và `request_uri` đúng. Server cần kiểm tra những gì trước khi khôi phục payload?
2. Một attacker đổi `client_id` thành client khác nhưng giữ nguyên `request_uri`. Server phản hồi thế nào?
3. Browser được mở lại sau 30 giây và gửi cùng request URI lần nữa. Khác biệt giữa nghĩa vụ client và lựa chọn của AS là gì?
4. Browser mở lại sau 70 giây. Vì sao request phải bị từ chối?
5. Client gửi lại `redirect_uri` khác trong query Authorization Endpoint. Vì sao không được dùng giá trị mới để thay payload đã push?
6. Metadata có `pushed_authorization_request_endpoint` nhưng không có `require_pushed_authorization_requests`. Client có thể hiểu server đang bắt buộc PAR không?
7. Nếu client dùng `private_key_jwt` ở PAR endpoint, `aud` phải mang giá trị nào theo RFC 10070?
8. Nếu SAS có PAR endpoint nhưng không có cấu hình enforcement PAR-only được chứng minh, cần thêm những kiểm thử/policy nào?

**Gợi ý:** request URI phải tồn tại, còn hạn và gắn đúng client; client chỉ dùng một lần; AS có thể cho phép duplicate reload có kiểm soát; hết hạn phải từ chối. Metadata endpoint chỉ báo khả năng PAR. Chế độ PAR-only cần metadata/policy thực thi. JWT client assertion phải dùng issuer identifier duy nhất của AS làm audience.

## 15. Checklist triển khai production

1. **Discovery:** client lấy đúng `pushed_authorization_request_endpoint` từ metadata và xác minh issuer.
2. **Back channel:** PAR dùng HTTPS POST, form-urlencoded UTF-8, client authentication đúng phương thức đã đăng ký.
3. **Validation:** server kiểm tra client, response type, redirect URI, scope, PKCE, OIDC nonce và các extension liên quan.
4. **Response:** trả `201`, `request_uri` entropy cao, client binding, `expires_in` và cache-control phù hợp.
5. **Authorization Endpoint:** chỉ nhận request URI hợp lệ từ PAR store, đối chiếu client và khôi phục payload gốc.
6. **Lifecycle:** TTL ngắn, client chỉ dùng một lần, AS xử lý duplicate reload có kiểm soát, hết hạn luôn bị từ chối.
7. **PAR-only:** metadata và enforcement thống nhất toàn server/theo client; không nhầm endpoint support với mandatory policy.
8. **Version:** xác nhận PAR có sẵn trong SAS 1.5+ hoặc Spring Security 7.0+; nếu cũ hơn phải nâng cấp hoặc triển khai custom có kiểm thử.
9. **JWT client assertion:** áp dụng audience duy nhất là issuer identifier theo RFC 10070.
10. **Storage:** chia sẻ giữa các instance, bảo vệ payload, chống replay, cleanup và rate limit.
11. **Observability:** che payload/request_uri/state/nonce/credential; có metrics lỗi, hết hạn, replay, rate limit và storage.
12. **End-to-end:** kiểm thử cả PAR endpoint, Authorization Endpoint, browser reload, callback, PKCE, consent và token endpoint.

## 16. Tài liệu chuẩn và Spring cần đối chiếu

- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): PAR endpoint, response request_uri, Authorization Request, client binding, expiry, replay và metadata.
- [RFC 10070 — Updates to OAuth 2.0 JWT Client Authentication and Assertion-Based Authorization Grants](https://www.rfc-editor.org/rfc/rfc10070.html): cập nhật RFC 9126 về audience duy nhất của JWT client authentication assertion.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): metadata endpoint và issuer identifier.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): authorization request, client authentication và response.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636.html): ràng buộc authorization code bằng code_verifier/code_challenge.
- [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101.html): Request Object và sự khác nhau với PAR request URI.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): cấu hình PAR endpoint, converter/provider và custom validator.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): endpoint mặc định `/oauth2/par` và mốc hỗ trợ từ 1.5.
- [Spring Security 7.x — OAuth 2.0 Authorization Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/index.html): các endpoint Authorization Server trong thế hệ Spring Security mới.
- [Spring Authorization Server 1.5 goes GA](https://spring.io/blog/2025/05/20/spring-authorization-server-1-5-goes-ga/): thông báo hỗ trợ PAR trong nhánh 1.5.

**Ghi nhớ:** Client không gửi toàn bộ authorization request qua browser sau khi đã push; client gửi **`client_id` và `request_uri`** để Authorization Server khôi phục payload đã lưu. Request URI phải khó đoán, gắn đúng client, có thời hạn và được dùng theo chính sách một lần. PAR giảm lộ và sửa đổi tham số trên browser nhưng vẫn cần PKCE, state, nonce, redirect URI validation, consent và kiểm tra authorization bình thường. Với Spring Authorization Server, hỗ trợ tích hợp bắt đầu từ **1.5**; muốn bắt buộc PAR phải kiểm tra cả metadata lẫn enforcement thực tế, đồng thời cập nhật JWT client assertion audience theo RFC 10070.

