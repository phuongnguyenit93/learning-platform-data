# Xác định ranh giới kiểm thử giữa client, authorization server và resource server

## Mục tiêu học tập

Trong một hệ thống OAuth2 thực tế, việc đăng nhập và gọi API thường đi qua nhiều thành phần. OAuth2 client điều hướng người dùng hoặc lấy token, authorization server (AS) xác thực client/người dùng và cấp token, còn resource server (RS) nhận access token rồi quyết định có cho phép truy cập tài nguyên hay không.

Nếu gom tất cả thành một bài test có tên `oauth2LoginWorks`, rất khó biết thành phần nào đã được kiểm chứng. Một test dùng principal giả lập có thể chứng minh ứng dụng hiển thị đúng tên người dùng, nhưng không chứng minh redirect, PKCE, code exchange, chữ ký token hay API authorization hoạt động.

Sau bài học này, bạn có thể:

- Phân biệt trách nhiệm và ranh giới tin cậy của OAuth2 client, authorization server và resource server.
- Xác định test nào thuộc ứng dụng client, test nào thuộc AS và test nào thuộc RS.
- Kiểm thử Authorization Code flow, PKCE, client authentication, token issuance và bearer-token validation theo đúng chủ thể.
- Phân biệt access token dùng gọi API với ID token dùng để xác nhận đăng nhập OIDC.
- Chọn giữa mock principal, mock token, HTTP stub, test realm của IdP và E2E.
- Thiết kế contract test giữa các thành phần mà không nhầm việc kiểm tra client với việc kiểm tra nhà cung cấp danh tính bên ngoài.

Bài này thuộc module **SPRING_SECURITY_TESTING**, tập trung vào kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Ba thành phần, ba trách nhiệm kiểm thử

OAuth2 là giao thức ủy quyền. Trong Authorization Code flow, client nhận authorization code từ authorization server, đổi code lấy token, sau đó dùng access token gọi resource server. OIDC bổ sung lớp xác thực người dùng trên OAuth2, thường thông qua ID token.

| Thành phần | Vai trò | Câu hỏi kiểm thử chính |
| --- | --- | --- |
| OAuth2 client | Ứng dụng cần quyền truy cập tài nguyên thay mặt người dùng hoặc chính ứng dụng. | Client tạo authorization request đúng, bảo vệ callback, đổi code, lưu/refresh token và gửi access token đúng cách không? |
| Authorization server (AS) | Xác thực người dùng/client, áp dụng consent và policy, cấp hoặc từ chối token. | AS kiểm tra client, redirect URI, grant, scope, PKCE, consent, code reuse và token policy đúng không? |
| Resource server (RS) | API nhận access token và bảo vệ tài nguyên. | RS đọc bearer token, xác minh token, ánh xạ scope thành authority và áp dụng authorization đúng không? |

Ba vai trò có thể nằm ở ba sản phẩm độc lập hoặc được triển khai trong cùng một hệ thống. Ranh giới kiểm thử vẫn cần giữ rõ theo trách nhiệm. Nếu ứng dụng đang dùng một IdP bên ngoài, nhóm phát triển client/RS thường kiểm tra hợp đồng tích hợp với IdP; họ không thể thay thế test nội bộ của nhà cung cấp đó.

### 1.1. Luồng Authorization Code cơ bản

~~~mermaid
sequenceDiagram
    participant B as Browser / User
    participant C as OAuth2 Client
    participant A as Authorization Server
    participant R as Resource Server

    B->>C: Mở trang cần đăng nhập
    C->>B: Redirect tới /authorize (state, PKCE, scope)
    B->>A: Authorization request
    A->>B: Login / consent nếu cần
    B->>C: Redirect callback (code, state)
    C->>C: Kiểm tra state
    C->>A: POST /token (code, verifier, client authentication)
    A->>C: Access token (+ ID token nếu OIDC)
    C->>C: Lưu authorized client / session
    C->>R: API request + Bearer access token
    R->>R: Validate token và authorize
    R->>C: API response
~~~

Sơ đồ thể hiện các bước chính. Trong triển khai thực tế, redirect, session, client authentication, token format và endpoint cụ thể phụ thuộc registration và policy của AS.

### 1.2. Ranh giới tin cậy

- Browser là môi trường không đáng tin cậy để giữ client secret. Public client phải dùng PKCE; không nhúng client secret vào ứng dụng chạy trên trình duyệt hoặc thiết bị người dùng.
- Client phải bảo vệ giao dịch authorization đang chờ, đặc biệt là `state`; với OIDC, còn phải kiểm tra `nonce` trong ID token.
- AS là nguồn quyết định token được phát hành cho client nào, với scope và audience nào.
- RS chỉ tin token theo chính sách issuer, chữ ký hoặc introspection, thời hạn và audience của API.
- Access token là credential nhạy cảm. Không đưa token vào URL, log, screenshot, assertion message hoặc báo cáo CI.

## 2. Lập bản đồ test theo chủ sở hữu

Trước khi viết test, hãy ghi rõ thành phần nào sở hữu hành vi và bằng chứng nào cần thu thập.

| Hành vi | Chủ sở hữu chính | Test phù hợp |
| --- | --- | --- |
| Tạo authorization request, redirect URI, scope | Client | Unit/configuration + client integration |
| Sinh và lưu state, PKCE verifier | Client | Unit + callback integration |
| Kiểm tra state ở callback | Client | HTTP integration / browser flow |
| Xác thực người dùng và consent | AS | AS integration với test user/realm |
| Xác thực client ở token endpoint | AS | AS protocol test |
| Kiểm tra redirect URI, grant type, PKCE | AS | AS negative/positive protocol test |
| Phát authorization code và token | AS | AS protocol/contract test |
| Đổi code và xử lý token response | Client và AS ở hai phía hợp đồng | Client integration với AS stub hoặc test AS |
| Lưu authorized client và refresh token | Client | Client integration |
| Bearer token validation và authorization | RS | Resource server integration |
| Introspection opaque token | RS gọi AS | RS integration với introspection stub/test AS |
| Scope thành authority và bảo vệ endpoint | RS | Converter unit + HTTP allow/deny |
| Cookie, session, login/logout, redirect trên browser | Client và AS phối hợp | E2E |

Một test có thể chạm nhiều thành phần, nhưng phải chỉ rõ hợp đồng nào đang được kiểm tra. Ví dụ client integration gọi token endpoint giả lập sẽ kiểm tra client gửi request đúng và xử lý response đúng; nó không chứng minh AS thật đã phát token theo policy đúng.

## 3. OAuth2 client: kiểm thử phía ứng dụng khởi tạo ủy quyền

OAuth2 client có thể là ứng dụng web dùng đăng nhập OIDC, backend gọi API thay mặt người dùng, hoặc service machine-to-machine dùng client credentials. Những bài test này thuộc phía client.

### 3.1. Kiểm tra cấu hình client registration

Với Spring Security, client registration mô tả client ID, client secret (nếu là confidential client), authorization URI, token URI, redirect URI, scopes và client authentication method.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: portal-test
            client-secret: test-only-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-idp:
            issuer-uri: https://idp.test.example
~~~

Test cấu hình nên xác minh:

- Registration ID và client ID đúng môi trường.
- Authorization grant type và client authentication method phù hợp với loại client.
- Redirect URI trùng chính xác với URI được đăng ký ở AS.
- Scope tối thiểu cần thiết, không yêu cầu quyền dư thừa.
- Provider metadata/issuer trỏ tới môi trường test phù hợp.
- Client secret chỉ được nạp từ secret store của môi trường test khi cần; không commit secret thật vào repository.

Một test bind properties hoặc kiểm tra bean registration giúp phát hiện sai cấu hình sớm. Nó chưa chứng minh AS chấp nhận registration đó.

### 3.2. Kiểm tra authorization request

Khi client bắt đầu Authorization Code flow, request cần có các tham số phù hợp với registration và policy:

- `response_type=code`.
- `client_id` đúng.
- `redirect_uri` đúng và đã đăng ký.
- `scope` đúng.
- `state` khó đoán, gắn với giao dịch đang chờ và được kiểm tra ở callback.
- `code_challenge` và `code_challenge_method` khi dùng PKCE.
- `nonce` trong OIDC request nếu cấu hình yêu cầu.

Client test nên xác minh redirect location và các tham số. Không chỉ assert status redirect; cần parse URI và kiểm tra giá trị cụ thể. Không ghi nguyên state, nonce hoặc verifier vào log test nếu không cần thiết.

### 3.3. Kiểm tra callback và state

Callback của client phải từ chối giao dịch không khớp state. Những trường hợp cần có:

| Kịch bản callback | Kỳ vọng |
| --- | --- |
| State khớp giao dịch đã khởi tạo | Tiếp tục xử lý code. |
| State thiếu | Từ chối callback. |
| State sai hoặc đã hết hạn | Từ chối callback. |
| State được dùng lại | Không chấp nhận như giao dịch mới. |
| Callback có error từ AS | Xử lý lỗi theo hợp đồng, không tạo session đã đăng nhập. |
| Callback code thiếu hoặc không hợp lệ | Không thiết lập principal thành công. |

Không dùng `oauth2Login()` để tuyên bố callback/state đã được kiểm tra. Configurer đó dựng một OAuth2 authentication đã thành công cho test. Muốn kiểm tra callback thực, phải chạy authorization redirect và callback qua filter chain/client flow.

### 3.4. Kiểm tra token exchange và PKCE

Sau callback, client gửi authorization code tới token endpoint. Với PKCE, client gửi `code_verifier` tương ứng với challenge đã đưa trong authorization request. AS kiểm tra verifier trước khi phát token.

Client test với HTTP stub nên xác minh:

- Client gọi đúng token endpoint.
- Gửi đúng grant type và authorization code.
- Gửi đúng redirect URI khi flow yêu cầu.
- Gửi code verifier đã lưu cho giao dịch đó.
- Thực hiện client authentication theo registration nếu là confidential client.
- Xử lý response thành công, lỗi OAuth2 và response không hợp lệ.
- Không log access token, refresh token hoặc client secret.

Stub xác minh request client gửi đi. Một test với AS test thật mới xác minh cả hai phía của hợp đồng.

### 3.5. Kiểm tra authorized client và refresh token

Client có thể lưu access token cùng refresh token trong `OAuth2AuthorizedClient` hoặc kho lưu trữ tương ứng. Test cần bao phủ:

- Authorized client gắn đúng principal và registration.
- Access token được dùng cho đúng resource server.
- Token hết hạn dẫn đến refresh theo policy.
- Refresh thành công cập nhật token được lưu.
- Refresh bị từ chối hoặc refresh token hết hạn dẫn đến trạng thái đăng nhập/ủy quyền phù hợp.
- Token không bị chia sẻ nhầm giữa user, tenant hoặc client registration.
- Logout hoặc revoke xóa/invalidates dữ liệu theo hợp đồng của ứng dụng.

Nếu refresh token rotation được AS hỗ trợ, kiểm tra client thay token cũ bằng token mới và không tiếp tục dùng token đã bị thu hồi.

### 3.6. Kiểm tra client gọi API

Khi client gọi resource server, test phải xác minh access token được gửi trong header `Authorization: Bearer ...` cho đúng đích. Kiểm tra không gửi token tới host không tin cậy hoặc endpoint không thuộc resource server dự kiến.

Có thể dùng HTTP mock server để bắt request và xác minh:

- HTTP method và URL.
- Bearer header được thêm đúng.
- Không gửi refresh token đến resource server.
- Khi API trả `401`, client xử lý token hết hạn hoặc yêu cầu đăng nhập lại theo policy.
- Khi API trả `403`, client không tự coi đó là lỗi token hết hạn và lặp refresh vô hạn.

## 4. Authorization server: kiểm thử nơi phát hành token

Authorization server sở hữu endpoint authorization, token, consent, metadata, JWKS và có thể cả introspection/revocation. Nếu nhóm phát triển chính AS, phải kiểm tra logic và protocol của chính AS. Nếu AS là dịch vụ bên ngoài, nhóm client/RS kiểm tra hợp đồng tương tác với AS qua stub hoặc test realm; không khẳng định đã kiểm thử nội bộ của nhà cung cấp.

### 4.1. Client registration và client authentication

AS cần xác minh client được đăng ký và dùng đúng phương thức xác thực. Các ca nên kiểm tra:

- Client ID tồn tại và đang hoạt động.
- Client secret hoặc private key hợp lệ với confidential client.
- Client public không bị yêu cầu gửi secret không thể bảo vệ.
- Client authentication method được hỗ trợ và khớp registration.
- Client bị vô hiệu hóa hoặc credential sai bị từ chối.
- Client không thể dùng registration của ứng dụng khác.

Không đưa secret thật vào test fixture. Dùng client/secret chỉ dành cho môi trường kiểm thử.

### 4.2. Authorization endpoint và consent

Với Authorization Code flow, AS cần kiểm tra:

- Client ID và redirect URI hợp lệ.
- Response type được hỗ trợ.
- Scope được phép cấp cho client và user.
- User đã xác thực.
- Consent được yêu cầu/ghi nhận theo policy.
- State được giữ nguyên khi redirect về client.
- PKCE challenge/method hợp lệ theo policy.
- Authorization code có thời hạn ngắn, gắn với client, redirect URI và giao dịch tương ứng.

Các test negative quan trọng:

| Đầu vào | Kết quả cần xác minh |
| --- | --- |
| Redirect URI chưa đăng ký hoặc không khớp | AS không redirect code tới URI đó. |
| Response type không hỗ trợ | Trả lỗi OAuth2 phù hợp. |
| Scope vượt quyền client/user | Từ chối hoặc chỉ cấp scope hợp lệ theo policy đã công bố. |
| PKCE challenge sai định dạng hoặc thiếu khi bắt buộc | Từ chối authorization request. |
| User từ chối consent | Không phát authorization code có quyền đã từ chối. |
| Client bị disable | Không cấp authorization code. |

Không chỉ kiểm tra trang login hiển thị được. Cần kiểm tra AS không phát code hoặc token khi điều kiện bảo mật không thỏa.

### 4.3. Token endpoint và authorization code một lần

AS phải kiểm tra authorization code ở token endpoint. Test cần chứng minh:

- Code hợp lệ, chưa hết hạn và thuộc client đúng thì được đổi token.
- Code đã dùng không thể đổi lần hai.
- Code hết hạn bị từ chối.
- Code gắn với redirect URI/client khác không thể được đổi.
- PKCE verifier sai bị từ chối.
- Client authentication sai bị từ chối với confidential client.
- Grant type không được hỗ trợ bị từ chối.
- Scope hoặc audience được cấp theo policy, không tự mở rộng.

Một test phát hiện code reuse đặc biệt quan trọng: sau lần đổi thành công, gửi lại cùng code và xác minh AS không phát token thứ hai.

### 4.4. Refresh, revoke và introspection

Tùy AS có hỗ trợ các grant/endpoint này, kiểm tra:

- Refresh token hợp lệ chỉ cấp access token theo scope được phép.
- Refresh token đã hết hạn, bị revoke hoặc bị rotation thay thế không được chấp nhận.
- Token revocation endpoint xác minh client và xử lý token đúng.
- Introspection chỉ tiết lộ trạng thái token cho resource server/client được phép.
- Token inactive không được RS chấp nhận.
- Metadata và JWKS công bố đúng issuer, key ID và public key.

Không phải mọi AS đều hỗ trợ cùng tính năng. Bộ test phải bám theo protocol/profile và hợp đồng mà hệ thống đã chọn.

### 4.5. Nếu AS là dịch vụ bên ngoài

Khi ứng dụng tích hợp với một IdP do nhà cung cấp quản lý:

- Dùng sandbox/test realm và client registration riêng.
- Kiểm tra discovery metadata, authorization endpoint, token endpoint và JWKS.
- Có thể dùng stub cho lỗi timeout, malformed response, key rotation và negative cases khó tái tạo.
- Chạy một số contract smoke test với sandbox để xác nhận kết nối và cấu hình.
- Không gọi môi trường production trong test tự động thông thường.
- Không tuyên bố test client đã xác minh nội bộ của AS.

## 5. Resource server: kiểm thử nơi access token được tiêu thụ

Resource server không chịu trách nhiệm đăng nhập người dùng hoặc điều hướng tới authorization endpoint. Nhiệm vụ của nó là nhận access token, xác minh token theo policy và quyết định request có được phép truy cập tài nguyên không.

### 5.1. JWT access token

Với JWT, RS cần xác minh các điều kiện phù hợp với cấu hình:

- Chữ ký bằng key tin cậy và thuật toán được chấp nhận.
- Issuer (`iss`) đúng.
- Expiration (`exp`) và not-before (`nbf`) hợp lệ.
- Audience (`aud`) có chứa API/resource server này nếu policy yêu cầu.
- Claim scope/role được ánh xạ thành authority đúng.
- Token không được dùng sai mục đích hoặc sai loại.

Test mock `jwt()` trong MockMvc có thể kiểm tra authorization với JWT đã dựng sẵn. Nó không gọi decoder, không xác minh chữ ký, không kiểm tra JWKS và không chứng minh issuer/audience validator đang hoạt động.

Để kiểm tra xác thực thật, gửi bearer token đã ký qua header và để `JwtDecoder` của RS xử lý. Dùng key test riêng để tạo token hợp lệ và token có chữ ký/claim sai.

### 5.2. Opaque access token

Với opaque token, RS gọi `OpaqueTokenIntrospector` tới introspection endpoint. Phân biệt:

- `opaqueToken()`: dựng principal đã xác thực để kiểm tra downstream authorization.
- Introspection stub: chạy introspector HTTP thật của RS và xác minh request/response.
- AS test realm: kiểm tra tích hợp với provider thật trong môi trường test.

Introspection cần kiểm tra token active/inactive, scope, subject, audience/expiry nếu provider trả và client authentication. Nếu endpoint lỗi hoặc timeout, RS phải xử lý theo policy an toàn đã chọn.

### 5.3. Authorization sau xác thực

Sau khi token được xác minh, RS còn phải áp dụng scope/role và policy tài nguyên:

- `orders.read` chỉ đọc đơn hàng trong phạm vi được phép.
- `orders.approve` chỉ duyệt đơn đang chờ duyệt.
- Tenant/ownership phải được kiểm tra ở dữ liệu thực.
- User hợp lệ nhưng thiếu authority thường nhận `403 Forbidden`.
- Token thiếu, sai chữ ký, hết hạn hoặc không được tin thường nhận `401 Unauthorized`.

Kiểm tra cả response body, headers, dữ liệu trả về và side effect. Request bị từ chối không được thay đổi trạng thái nghiệp vụ hoặc gọi downstream service trái phép.

## 6. Dùng Spring Security Test đúng ranh giới

Các helper của `spring-security-test` rất hữu ích, nhưng mỗi helper tạo ra một loại bằng chứng khác nhau.

| Helper / cơ chế | Thành phần thường được kiểm tra | Nó không tự chứng minh |
| --- | --- | --- |
| `@WithMockUser` | Method security hoặc logic ứng dụng với user giả lập. | Password login, token issuance, protocol OAuth2/OIDC. |
| MockMvc `user()` | URL authorization với principal giả lập. | User store hoặc authentication provider thật. |
| MockMvc `jwt()` | Authorization sau khi JWT principal đã được dựng. | JWT signature, decoder, issuer/JWKS. |
| WebTestClient `mockJwt()` | Reactive authorization với JWT mock. | Reactive decoder xác minh bearer token. |
| MockMvc `opaqueToken()` | Authorization với opaque principal mock. | HTTP introspection thực. |
| `oauth2Login()` / `oidcLogin()` | Logic ứng dụng sau khi OAuth2/OIDC principal đã đăng nhập. | Redirect, callback, state, nonce, code exchange hoặc ID token signature. |
| `oauth2Client()` / configurer client tương ứng | Thiết lập authorized client cho test xử lý phía sau. | Token endpoint thật đã cấp token hoặc refresh protocol chạy đúng. |
| Bearer header + decoder/introspector thật | Xác thực access token tại RS. | AS bên ngoài phát hành token theo policy đúng nếu chỉ dùng key/stub cục bộ. |

### 6.1. Test logic sau OIDC login bằng mock

Ví dụ controller đọc claim từ OIDC principal:

~~~java
@GetMapping("/profile")
String profile(@AuthenticationPrincipal OidcUser user) {
    return user.getFullName();
}
~~~

Có thể dùng `oidcLogin()` để kiểm tra controller/service xử lý claim và authority:

~~~java
mvc.perform(get("/profile")
        .with(oidcLogin().idToken(token -> token
            .claim("sub", "user-42")
            .claim("name", "Mai Nguyen"))))
    .andExpect(status().isOk())
    .andExpect(content().string("Mai Nguyen"));
~~~

Test này kiểm tra logic sau khi principal OIDC đã có. Nó không xác minh chữ ký ID token hoặc thực hiện Authorization Code flow.

### 6.2. Test resource server với JWT mock và bearer token thực

Test authorization nhanh:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(token -> token
            .subject("user-42")
            .claim("scope", "orders.read"))))
    .andExpect(status().isOk());
~~~

Test decoder thực:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + signedToken))
    .andExpect(status().isOk());
~~~

Hai test trả lời hai câu hỏi khác nhau. Test đầu cô lập authorization; test sau đi qua bearer-token filter và decoder được cấu hình trong ứng dụng.

## 7. Contract test giữa các ranh giới

Một contract test tốt xác định request và response mà hai thành phần trao đổi, thay vì giả định toàn bộ implementation của bên kia.

### 7.1. Client ↔ Authorization server

Contract cần bao phủ:

- Authorization URI và các query parameter.
- Redirect URI và callback.
- Token endpoint, grant type và client authentication.
- PKCE verifier/challenge.
- Response token, token type, expiry và scope.
- OAuth2 error response như `invalid_request`, `invalid_client`, `invalid_grant`, `invalid_scope` hoặc `unauthorized_client`.
- Refresh/revoke nếu ứng dụng sử dụng.

Client test với stub chứng minh client tuân thủ hợp đồng đã mô phỏng. Một smoke test với AS sandbox chứng minh cấu hình và kết nối hiện tại tương thích ở mức cơ bản.

### 7.2. Resource server ↔ Authorization server

Với JWT:

- RS lấy JWKS từ endpoint đã cấu hình.
- Key ID và public key tương ứng xác minh được token.
- Issuer và audience khớp policy.
- RS xử lý key rotation và lỗi tải JWKS theo cấu hình.

Với opaque token:

- RS gọi đúng introspection endpoint.
- Gửi client authentication theo cấu hình.
- Gửi token trong request theo chuẩn.
- Xử lý `active=true` và `active=false`.
- Xử lý timeout, lỗi HTTP và response không hợp lệ theo policy.

### 7.3. Client ↔ Resource server

Contract cần xác minh:

- Client gửi access token đúng audience/resource.
- Không gửi ID token thay cho access token.
- RS trả 401 khi access token không hợp lệ.
- RS trả 403 khi token hợp lệ nhưng thiếu quyền.
- Client xử lý 401 và 403 khác nhau.
- Response error không khiến client lặp refresh vô hạn hoặc rò rỉ token.

## 8. OIDC: ID token và access token có mục đích khác nhau

OIDC mở rộng OAuth2 để client xác minh người dùng đã đăng nhập. Hai token thường xuất hiện trong flow có mục đích khác nhau:

| Token | Bên nhận/chủ thể sử dụng | Mục đích |
| --- | --- | --- |
| ID token | OAuth2/OIDC client | Thông tin xác thực về lần đăng nhập và subject, với audience dành cho client. |
| Access token | Resource server | Cấp quyền truy cập API theo audience/scope/resource policy. |
| Refresh token | OAuth2 client gửi tới token endpoint | Xin access token mới theo policy; không gửi tới API. |

Client cần kiểm tra các claim ID token theo OIDC, bao gồm issuer, audience, thời hạn và nonce khi được dùng trong request. RS cần xác minh access token theo policy của API.

Không dùng ID token làm bearer token cho API chỉ vì nó cũng là JWT. Audience của ID token thường là client, còn API cần access token dành cho resource server. Test phải phát hiện trường hợp client gửi nhầm ID token hoặc RS chấp nhận token sai audience.

## 9. Chọn chiến lược theo loại flow

| Flow | Client cần test | AS cần test | RS cần test |
| --- | --- | --- | --- |
| Authorization Code + PKCE | Redirect, state, verifier, callback, code exchange, session. | Redirect URI, challenge, code một lần, token issuance. | Access token validation và scope authorization. |
| Authorization Code confidential client | Client authentication và callback/code exchange. | Client credential, redirect URI, grant và scope. | Như trên. |
| Client Credentials | Client lấy token bằng client identity, cache/refresh nếu policy có. | Client authentication, allowed grant/scope/audience. | Token client-only và quyền API tương ứng. |
| Refresh Token | Client refresh, cập nhật token, xử lý invalid_grant. | Rotation, expiry, revoke và client binding. | Access token mới được xác minh theo policy. |
| OIDC login | State, nonce, ID token, session/logout. | Authentication, consent, ID token claims/signature. | RS vẫn kiểm tra access token; không dùng ID token thay thế. |
| Opaque access token | Client dùng token đúng cách. | Introspection/revocation state. | Gọi introspection và áp dụng scope/authority. |

Không phải flow nào cũng có đủ ba thành phần trong cùng một sản phẩm. Ví dụ client credentials không có người dùng tương tác hoặc browser redirect; test không cần tạo giả định về login UI.

## 10. Test môi trường và dữ liệu an toàn

Test OAuth2/OIDC thường dùng credential và token có khả năng truy cập tài nguyên. Quản lý fixture như secret:

- Dùng client registration, account, key pair và token chỉ dành cho test.
- Không dùng tài khoản người dùng thật hoặc secret production.
- Không commit client secret, private key, refresh token hoặc access token.
- Không log Authorization header, code, verifier, state, nonce hoặc token response đầy đủ.
- Cô lập redirect URI và callback host trong test.
- Dọn session, cookie, authorized client và test user sau test.
- Giới hạn scope ở mức tối thiểu.
- Khi dùng sandbox, bảo đảm dữ liệu và tài nguyên đều là test data.

Với token được tạo trong test, đặt thời gian có kiểm soát hoặc dùng clock/fixture phù hợp để tránh test chập chờn do token hết hạn trong lúc chạy.

## 11. Ma trận chọn mức kiểm thử

| Câu hỏi | Mức phù hợp | Bằng chứng |
| --- | --- | --- |
| Client properties có đúng không? | Unit/configuration | Registration, scopes, redirect URI, provider metadata. |
| Client tạo authorization request đúng không? | Client integration | Redirect URI và query parameters. |
| Callback có kiểm tra state không? | Client HTTP/protocol integration | State khớp được xử lý; state sai bị từ chối. |
| AS có từ chối redirect URI sai không? | AS protocol test | Không phát authorization code tới URI không đăng ký. |
| AS có từ chối PKCE verifier sai không? | AS token endpoint test | `invalid_grant` hoặc lỗi tương ứng; không phát token. |
| RS có kiểm tra chữ ký JWT không? | RS integration | Bearer token ký bằng key không tin cậy bị 401. |
| RS có gọi introspection không? | RS integration với stub/test AS | Request HTTP và xử lý active/inactive. |
| API có kiểm tra scope/tenant không? | HTTP authorization test | Cặp allow/deny và side-effect assertions. |
| Login/logout/session có đúng trên browser không? | E2E | Redirect, cookie, session, logout và truy cập sau login. |

## 12. Những lỗi thường gặp khi nhầm ranh giới

### 12.1. Dùng oauth2Login() để kết luận code flow thành công

`oauth2Login()` dựng principal đã đăng nhập cho test. Nó không redirect tới AS, không đổi authorization code và không xác minh state/nonce. Dùng nó cho logic sau đăng nhập; thêm protocol test khi cần kiểm chứng flow.

### 12.2. Dùng jwt() để kết luận JWT signature hợp lệ

JWT mock bỏ qua decoder. Gửi bearer token có chữ ký qua filter chain để test decoder, validators và JWKS.

### 12.3. Test client bằng mock authorized client rồi kết luận AS đã cấp token

Authorized client mock giúp kiểm tra logic sử dụng token ở phía client. Nó không gọi token endpoint. Dùng stub hoặc AS test thật để kiểm tra code exchange và refresh.

### 12.4. Test RS với token giả lập rồi kết luận AS policy đúng

RS test bằng key test chứng minh RS tin và xác minh token theo cấu hình. Nó không chứng minh AS thật chỉ cấp scope đúng hoặc xử lý consent đúng. Cần AS protocol test hoặc contract test với test realm.

### 12.5. Dùng ID token gọi API

ID token xác nhận thông tin đăng nhập cho client. API cần access token dành cho audience/resource tương ứng. Test nên có ca từ chối ID token nếu audience/issuer/policy không phù hợp với RS.

### 12.6. Gộp mọi lỗi thành 401

Token hợp lệ nhưng thiếu scope thường là lỗi authorization và có thể trả 403. Token thiếu hoặc không hợp lệ thường là 401. Client cần xử lý hai trường hợp khác nhau theo hợp đồng API.

### 12.7. Chỉ chạy sandbox test

Sandbox giúp kiểm tra tương thích với provider hiện tại, nhưng có thể không tái hiện timeout, key rotation, malformed response hoặc lỗi hiếm. Dùng stub để kiểm tra các nhánh lỗi có kiểm soát, thêm smoke test sandbox cho cấu hình thật.

## 13. Bài thực hành tổng hợp

Giả sử một portal Spring Security dùng OIDC để đăng nhập, gọi API orders bằng access token, và API orders là resource server.

1. **Client unit/config:** xác minh registration, issuer, redirect URI, scopes và client authentication method.
2. **Client protocol:** kiểm tra authorization request có state, PKCE challenge và OIDC nonce phù hợp.
3. **Client callback:** test state hợp lệ, thiếu, sai và callback error; không dùng `oauth2Login()` cho các ca protocol này.
4. **Client token exchange:** dùng HTTP stub để kiểm tra code, verifier, redirect URI, client authentication và xử lý token response.
5. **AS contract:** dùng test realm/stub kiểm tra redirect URI, PKCE, consent, code reuse, client authentication và refresh policy.
6. **RS JWT:** gửi access token đã ký qua bearer header; kiểm tra signature, issuer, audience, expiry và scope.
7. **RS opaque:** nếu hỗ trợ, kiểm tra introspection active/inactive, client authentication và timeout.
8. **API authorization:** dùng `jwt()`/`mockJwt()` để kiểm tra nhanh scope, tenant và ownership; xác minh response và side effects.
9. **OIDC:** xác minh client kiểm tra ID token/nonce; xác minh RS không nhận nhầm ID token làm access token.
10. **E2E:** dùng browser và IdP test realm để kiểm tra login, redirect, session, gọi API, logout và truy cập sau logout.
11. **Báo cáo:** với mỗi test, ghi rõ chủ sở hữu hành vi, thành phần thật hay mock, hợp đồng được kiểm tra và phần còn nằm ngoài phạm vi.

**Tiêu chí hoàn thành:** bạn có thể chỉ ra test nào chứng minh client gửi request đúng, test nào chứng minh AS cấp token đúng, test nào chứng minh RS xác minh token và bảo vệ API đúng, cùng những phần chỉ được kiểm tra khi chạy flow tích hợp.

## 14. Ghi nhớ

OAuth2 client, authorization server và resource server là ba ranh giới có trách nhiệm khác nhau. Client điều phối authorization request, callback, code exchange và việc sử dụng token. AS xác thực client/người dùng, áp dụng consent/policy và phát hành token. RS xác minh access token rồi kiểm tra scope, role, tenant và quyền trên tài nguyên.

`@WithMockUser`, `oauth2Login()`, `oidcLogin()`, `jwt()` và các helper tương ứng giúp kiểm tra logic khi principal đã được dựng. Chúng không thay thế protocol test. Muốn kiểm tra state, PKCE, token exchange, client authentication, chữ ký JWT, introspection hoặc session thực, hãy chạy thành phần chịu trách nhiệm qua stub, test realm hoặc môi trường tích hợp phù hợp.

Một báo cáo test tốt phải nói rõ **thành phần nào đang được kiểm tra, bên kia ranh giới là mock hay hệ thống thật, và bằng chứng bao phủ đến bước nào của OAuth2/OIDC**.
