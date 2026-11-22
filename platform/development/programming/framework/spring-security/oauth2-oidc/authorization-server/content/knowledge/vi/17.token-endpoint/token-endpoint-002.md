# Điều phối provider theo grant_type

> **Chương:** Token Endpoint  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi ví dụ:** Spring Boot 3.x, Spring Security 6.x, Spring Authorization Server 1.5.x trên Servlet stack; các ví dụ dùng API `OAuth2AuthorizationServerConfigurer.authorizationServer()`. Với Spring Security 7.x tích hợp chức năng Authorization Server, cần đối chiếu package và DSL của phiên bản đó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích tác dụng của `grant_type` trong HTTP request đến `/oauth2/token` và phân biệt nó với **phương thức xác thực OAuth2 Client**.
2. Mô tả pipeline `OAuth2TokenEndpointFilter → AuthenticationConverter → AuthenticationManager/ProviderManager → AuthenticationProvider → OAuth2TokenGenerator → response handler`.
3. Nhận diện các cặp converter/provider mặc định cho `authorization_code`, `refresh_token`, `client_credentials`, Device Code và Token Exchange trong Spring Authorization Server phiên bản phù hợp.
4. Hiểu quy tắc chọn provider bằng **kiểu `Authentication`** và `supports(...)`, thay vì cho rằng framework chỉ dùng một câu lệnh `switch(grant_type)` trực tiếp.
5. Biết các kiểm tra khác nhau theo grant: code/PKCE/redirect URI, refresh-token binding, scope của client, trạng thái device authorization và subject token của token exchange.
6. Cấu hình `OAuth2TokenEndpointConfigurer`, điều chỉnh provider mặc định có kiểm soát và thêm extension grant mà không phá cơ chế sẵn có.
7. Kiểm thử đầy đủ các nhánh thành công và lỗi, bao gồm trường hợp không có provider, client bị từ chối grant, provider sai loại và hai yêu cầu đồng thời.

**Ý tưởng quan trọng:** `grant_type` giúp nhận ra **loại grant mà client đang yêu cầu**. Nhưng để phát token an toàn, AS còn phải xác minh **client nào đang gọi**, liệu client **được phép dùng grant đó** và từng loại grant **đáp ứng đủ điều kiện riêng** hay chưa.

## 2. Token Endpoint không phải trang đăng nhập

Trong OAuth 2.0, Token Endpoint là điểm HTTP để OAuth2 Client trình bày một authorization grant hoặc credential phù hợp nhằm xin token. Với cấu hình mặc định của Spring Authorization Server 1.x, URL thường là:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=booking.read
~~~

Ví dụ này **chưa đưa thông tin client authentication**; confidential client thông thường phải cung cấp `Authorization: Basic ...` hoặc phương thức đã đăng ký. `grant_type` là tham số của body `application/x-www-form-urlencoded`, không phải path riêng theo từng grant.

Khác với `/oauth2/authorize`:

- **Authorization Endpoint** chủ yếu điều phối trình duyệt, Resource Owner login, consent và phát authorization code.
- **Token Endpoint** là API back-channel nhận request của OAuth2 Client; không dùng redirect tới trang `/login` làm phản hồi mặc định cho lỗi grant.
- Client có thể là backend BFF, service account, ứng dụng di động/public client hoặc thiết bị giới hạn nhập liệu, tùy loại grant.
- Resource Owner không nhất thiết tham gia request token. Ví dụ Client Credentials không có user đang đăng nhập; Refresh Token dựa vào authorization đã được lưu từ trước.

### 2.1. Hai câu hỏi khác nhau trước khi cấp token

| Câu hỏi | Thành phần giải quyết | Ví dụ |
| --- | --- | --- |
| **Ai đang gọi Token Endpoint?** | `OAuth2ClientAuthenticationFilter` cùng các client authentication converters/providers | `client_secret_basic`, `private_key_jwt`, mTLS, `none` |
| **Client yêu cầu token bằng grant nào?** | `OAuth2TokenEndpointFilter` cùng các grant converters/providers | `authorization_code`, `refresh_token`, `client_credentials`, Device Code, Token Exchange |

Không được xem `grant_type=client_credentials` là “client đã xác thực”, và cũng không xem một `client_secret` đúng là “được phép thực hiện tất cả grant”.

## 3. Kiến trúc xử lý request trong Spring Authorization Server

Ở Servlet stack, `OAuth2AuthorizationServerConfigurer` cấu hình các filter liên quan trong `SecurityFilterChain`. Hai thành phần quan trọng với token endpoint:

1. `OAuth2ClientAuthenticationFilter`: xử lý các phương thức xác thực/nhận diện client theo registered client.
2. `OAuth2TokenEndpointFilter`: xử lý access-token request, chọn converter và provider phù hợp, trả token hoặc OAuth2 error.

~~~mermaid
flowchart TD
    R["POST /oauth2/token"]
    F["SecurityFilterChain cho Authorization Server"]
    CA["OAuth2ClientAuthenticationFilter<br/>ClientAuthenticationConverter / Provider"]
    CI{"Client hợp lệ theo<br/>registration và policy?"}
    TE["OAuth2TokenEndpointFilter"]
    CO["DelegatingAuthenticationConverter<br/>Phân loại theo grant_type"]
    GT["Authentication token đại diện grant<br/>Code / Refresh / ClientCredentials / Device / Exchange"]
    AM["AuthenticationManager / ProviderManager"]
    PV["AuthenticationProvider hỗ trợ kiểu Authentication"]
    V{"Grant hợp lệ?<br/>Client được grant?<br/>Điều kiện riêng đạt?"}
    GEN["OAuth2TokenGenerator + AuthorizationService"]
    OK["OAuth2AccessTokenAuthenticationToken"]
    RESP["Access Token Response Handler<br/>200 JSON + no-store"]
    ERR["OAuth2 Error / Client Authentication Error<br/>không phát token"]

    R --> F --> CA --> CI
    CI -->|"Không"| ERR
    CI -->|"Có"| TE --> CO --> GT --> AM --> PV --> V
    V -->|"Không"| ERR
    V -->|"Có"| GEN --> OK --> RESP
~~~

Sơ đồ này thể hiện **luồng logic điển hình**, không khẳng định mọi request đều qua đúng thứ tự phương thức ở từng implementation hoặc mọi lỗi đều được ném từ cùng filter. Lỗi client authentication có thể kết thúc request trước khi grant provider được gọi.

### 3.1. Cấu trúc mở rộng

`OAuth2TokenEndpointConfigurer` là DSL của Spring Authorization Server dùng để tùy chỉnh `OAuth2TokenEndpointFilter`. Theo tài liệu nhánh 1.5.x, có sáu extension point chính:

| API | Giai đoạn | Trách nhiệm |
| --- | --- | --- |
| `accessTokenRequestConverter(...)` | Trước xác thực grant | Thêm một `AuthenticationConverter` |
| `accessTokenRequestConverters(...)` | Trước xác thực grant | Truy cập, thêm, sắp xếp hoặc điều chỉnh danh sách converters |
| `authenticationProvider(...)` | Xử lý grant | Thêm một `AuthenticationProvider` |
| `authenticationProviders(...)` | Xử lý grant | Truy cập danh sách providers mặc định và bổ sung để tùy biến |
| `accessTokenResponseHandler(...)` | Sau xử lý thành công | Tạo OAuth2 token response từ `OAuth2AccessTokenAuthenticationToken` |
| `errorResponseHandler(...)` | Sau xử lý thất bại | Tạo OAuth2 error response từ `OAuth2AuthenticationException` |

Đa số hệ thống chỉ cần cấu hình `RegisteredClient` và các core services; **không cần tự viết lại converter/provider/response handler**. Tùy chỉnh càng sâu càng đòi hỏi test giao thức và bảo mật đầy đủ.

## 4. Danh sách grant_type và provider mặc định

Trong Spring Authorization Server **1.5.x**, Token Endpoint hỗ trợ các grant sau; bản 1.2.x cũ hơn không có đầy đủ tất cả, đặc biệt Token Exchange cần kiểm tra release/version trước khi dùng.

| `grant_type` gửi lên | Converter mặc định | Provider mặc định | Dữ liệu chứng minh grant |
| --- | --- | --- | --- |
| `authorization_code` | `OAuth2AuthorizationCodeAuthenticationConverter` | `OAuth2AuthorizationCodeAuthenticationProvider` | Code còn hạn, đúng client/redirect URI, PKCE |
| `refresh_token` | `OAuth2RefreshTokenAuthenticationConverter` | `OAuth2RefreshTokenAuthenticationProvider` | Refresh token còn active, đúng client, scope không mở rộng |
| `client_credentials` | `OAuth2ClientCredentialsAuthenticationConverter` | `OAuth2ClientCredentialsAuthenticationProvider` | Client hợp lệ, được grant type, scopes hợp lệ |
| `urn:ietf:params:oauth:grant-type:device_code` | `OAuth2DeviceCodeAuthenticationConverter` | `OAuth2DeviceCodeAuthenticationProvider` | Device code còn hạn, trạng thái approval/denial, client binding |
| `urn:ietf:params:oauth:grant-type:token-exchange` | `OAuth2TokenExchangeAuthenticationConverter` | `OAuth2TokenExchangeAuthenticationProvider` | Subject token và yêu cầu exchange hợp lệ theo RFC 8693/chính sách |

Nguồn chính thức: [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html).

### 4.1. Điều gì xảy ra với grant_type không hỗ trợ?

Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <valid-confidential-client-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=lan&password=not-for-production
~~~

`password` (Resource Owner Password Credentials) là grant lịch sử, **không nằm trong danh sách provider mặc định nói trên** và không nên được bổ sung để bỏ qua tương tác đăng nhập người dùng trong hệ thống mới. Khi grant type không được hỗ trợ, token endpoint phải trả OAuth2 error phù hợp, thường `unsupported_grant_type`.

Nếu grant type **được server hỗ trợ** nhưng **client không được phép dùng** do `RegisteredClient.authorizationGrantTypes`, đây là trường hợp khác; mã lỗi thường là `unauthorized_client`. Không được tự thêm grant vào RegisteredClient chỉ để làm hết lỗi mà chưa xét threat model.

### 4.2. “Token Exchange” không đồng nghĩa mọi phép đổi token đều được cấp phép

Ở phiên bản có hỗ trợ Token Exchange, `grant_type=urn:ietf:params:oauth:grant-type:token-exchange` là trường hợp theo RFC 8693. Provider phải kiểm tra subject token, token type, actor token nếu có, audience/resource, scope và chính sách delegated/impersonation.

Không suy từ việc converter/provider đã có sẵn rằng client được quyền đổi token của mọi user, mọi API hoặc mọi tenant. Mọi trường hợp token exchange đều cần điều kiện cấp quyền rõ ràng và test cả ràng buộc audience.

## 5. Bước A: xác thực OAuth2 Client trước khi điều phối grant

Ở Token Endpoint, bước xác thực client **độc lập với** việc xem xét `grant_type`. Một số cơ chế được Spring Authorization Server hỗ trợ gồm:

- `client_secret_basic`: confidential client gửi ID/secret qua HTTP Basic.
- `client_secret_post`: gửi credential trong body theo chính sách registration; nên cân nhắc tránh khi không cần.
- `private_key_jwt` hoặc `client_secret_jwt`: client assertion được ký và được AS xác minh.
- `tls_client_auth` hoặc `self_signed_tls_client_auth`: ràng buộc danh tính client bằng chứng chỉ TLS.
- `none`: public client không có secret, chỉ được dùng các grant/biện pháp bảo vệ thích hợp.

Ví dụ confidential client:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

Khi client authentication thành công, Spring Authorization Server có thể đặt một `OAuth2ClientAuthenticationToken` vào `SecurityContext` để các provider của grant dùng xác định client đã nhận diện.

**Cảnh báo:** `client_id` là định danh, không phải secret. Với public client, `none` chỉ phù hợp với grant được hỗ trợ và biện pháp bảo vệ liên quan (ví dụ PKCE cho Authorization Code). Không được chuyển `ClientAuthenticationMethod.NONE` vào Client Credentials chỉ để tránh quản lý secret trong service backend.

### 5.1. Khi nào nhận `invalid_client`?

Nếu secret sai, client assertion không hợp lệ, phương thức xác thực không đúng registration hoặc client chưa được xác thực theo chính sách, request có thể bị từ chối **trước khi** `OAuth2TokenEndpointFilter` chọn grant provider.

Đừng debug lỗi này bằng cách tùy biến `OAuth2ClientCredentialsAuthenticationProvider` — tên class gần giống nhưng class đó xử lý **Client Credentials Grant**, không phải bước xác thực client secret chung cho tất cả grant.

## 6. Bước B: Converter nhận request theo grant_type

### 6.1. `DelegatingAuthenticationConverter` phân loại request

Token endpoint nhận request form-encoded rồi áp dụng các converters. Với cấu hình mặc định, `DelegatingAuthenticationConverter` thử các converter theo thứ tự và dùng kết quả `Authentication` của converter phù hợp.

Mỗi converter được thiết kế nhận một loại grant:

~~~text
grant_type=authorization_code
   -> OAuth2AuthorizationCodeAuthenticationConverter
   -> OAuth2AuthorizationCodeAuthenticationToken

grant_type=refresh_token
   -> OAuth2RefreshTokenAuthenticationConverter
   -> OAuth2RefreshTokenAuthenticationToken

grant_type=client_credentials
   -> OAuth2ClientCredentialsAuthenticationConverter
   -> OAuth2ClientCredentialsAuthenticationToken

grant_type=urn:ietf:params:oauth:grant-type:device_code
   -> OAuth2DeviceCodeAuthenticationConverter
   -> OAuth2DeviceCodeAuthenticationToken

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
   -> OAuth2TokenExchangeAuthenticationConverter
   -> OAuth2TokenExchangeAuthenticationToken
~~~

Tên các lớp minh họa thành phần mặc định của **nhánh 1.5.x**. Không ép tất cả grant vào `UsernamePasswordAuthenticationToken`: kiểu `Authentication` chuyên biệt cho phép provider biết phải kiểm tra ràng buộc nào.

### 6.2. Converter không phải provider

Converter thường có nhiệm vụ:

- Nhận diện `grant_type` phù hợp, trả `null` nếu không xử lý loại đó.
- Lấy các tham số `code`, `refresh_token`, `scope`, `device_code`, v.v.
- Kiểm tra sơ bộ hình dạng request, như tham số bắt buộc hoặc số lần xuất hiện không hợp lệ.
- Đưa thông tin client authentication phù hợp vào đối tượng authentication grant.
- Tạo đối tượng `Authentication` mà provider tương ứng có thể xử lý.

Converter **không** thay cho những bước sau:

- Xác thực chữ ký client assertion.
- Kiểm tra authorization code thuộc client.
- Kiểm tra refresh token còn active.
- Xác minh scope đã được cấp cho Resource Owner.
- Sinh access token hoặc lưu authorization.

Vì vậy, việc custom converter “nhận thêm tham số” không được biến nó thành nơi tự trả token hoặc tự bỏ kiểm tra trên server.

### 6.3. Đừng để custom converter nhận mọi request

Một implementation sai có thể luôn trả `Authentication` bất kể `grant_type`, khiến các converter chuẩn không còn cơ hội xử lý. Với extension grant, converter phải:

1. Kiểm tra chính xác giá trị `grant_type` mà nó hỗ trợ.
2. Trả `null` khi request không thuộc grant đó.
3. Chỉ parse những tham số cần thiết, từ chối nhiều giá trị khi không hợp lệ.
4. Không nhận raw access token/refresh token từ query string nếu grant yêu cầu body.
5. Không tự đặt `authenticated=true` để qua mặt provider.
6. Có test nhận diện đúng grant và **không nhận diện nhầm** grant khác.

## 7. Bước C: AuthenticationManager chọn đúng provider

Sau converter, `OAuth2TokenEndpointFilter` gửi `Authentication` cho một `AuthenticationManager`, thường do `ProviderManager` điều phối.

### 7.1. Vì sao không gọi provider bằng một switch thuần túy?

Có thể hiểu logic khái niệm như:

~~~text
Authentication authRequest = converter.convert(httpRequest);
Authentication result = authenticationManager.authenticate(authRequest);
~~~

Sau đó `ProviderManager` xét các provider đã cấu hình bằng hợp đồng `supports(Class<?> authentication)` và xử lý yêu cầu theo quy tắc của Spring Security. Các provider mặc định có thể từ chối loại `Authentication` ngoài trách nhiệm; provider hợp lệ xác minh grant và trả kết quả.

**Đây là mã giả**, không phải implementation đầy đủ của `OAuth2TokenEndpointFilter`. Điểm cần nhớ là **giá trị `grant_type` được chuyển thành một kiểu authentication grant**, và provider được lựa chọn qua **hợp đồng hỗ trợ kiểu đó**. `supports(...)` **không chứng minh** request có quyền dùng grant; việc grant được phép hay không phải được kiểm tra thêm ở provider.

### 7.2. Thứ tự provider có ý nghĩa khi tùy biến

Giả sử ứng dụng thêm một provider mới cho grant nội bộ. Cần xác nhận:

- `supports(...)` của provider mới chỉ nhận đúng `Authentication` custom.
- Provider không vô tình bắt các token mặc định như `OAuth2RefreshTokenAuthenticationToken`.
- Nếu nhiều provider cùng hỗ trợ một kiểu, thứ tự và cách ném exception/return của chúng tạo hành vi mong muốn.
- Provider không xem một exception bảo mật là “thử provider khác cho tới khi có người cấp token”.
- Những provider mặc định vẫn tồn tại và các grant không liên quan vẫn hoạt động.

Khi custom quá rộng, một request có thể bị định tuyến sai, trả sai lỗi hoặc bỏ qua những validation mặc định quan trọng.

## 8. Mỗi provider phải thực thi chính sách riêng của grant

### 8.1. Authorization Code Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=VALID_PKCE_VERIFIER
~~~

`OAuth2AuthorizationCodeAuthenticationProvider` phải kiểm tra, tùy trường hợp:

- Client đã được nhận diện/xác thực đúng registration.
- Client được phép sử dụng `authorization_code`.
- Authorization code thuộc đúng client và grant đã được lưu.
- Code còn hạn, chưa bị sử dụng, không bị vô hiệu hóa.
- `redirect_uri` khớp giá trị từ authorization request khi có yêu cầu.
- `code_verifier` đáp ứng PKCE challenge nếu flow yêu cầu.
- Token phát hành chỉ có scope/claims được cấp theo chính sách.

Không xem việc một client biết `code` là đủ. Mã chỉ dùng một lần; mọi lần đổi không hợp lệ phải **không cấp token**. Người dùng đăng nhập ở `/oauth2/authorize`, không nhập lại mật khẩu ở Token Endpoint.

### 8.2. Refresh Token Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE&scope=booking.read
~~~

`OAuth2RefreshTokenAuthenticationProvider` kiểm tra:

- Client đã xác thực phù hợp và được đăng ký `refresh_token`.
- Refresh token nằm trong authorization được AS công nhận, thuộc **đúng client**.
- Token còn active, chưa hết hạn, chưa bị vô hiệu hóa hoặc tiêu thụ theo chính sách.
- Scope xin mới không vượt `OAuth2Authorization.getAuthorizedScopes()`.
- Access token mới và refresh token mới/cũ được phát hành, cập nhật theo `TokenSettings`.

Không dùng `RegisteredClient.getScopes()` làm nguồn duy nhất để mở rộng quyền; một client có thể đăng ký nhiều scope nhưng Resource Owner chỉ cấp một tập con. `reuseRefreshTokens(false)` yêu cầu rotation theo chính sách, **không tự bảo đảm toàn bộ hệ thống phát hiện replay/token-family revocation**.

### 8.3. Client Credentials Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

`OAuth2ClientCredentialsAuthenticationProvider` thường kiểm tra:

- Client được phép dùng `client_credentials`.
- Client authentication hợp lệ ở bước riêng trước đó.
- Các scope yêu cầu nằm trong registration và chính sách áp dụng.
- Token được phát hành cho client/service identity, không tự đại diện Resource Owner.
- Không tự giả định có refresh token; RFC 6749 khuyến nghị không cấp refresh token cho Client Credentials.

Ví dụ authorization service sinh token có `sub` hoặc `client_id` biểu thị client. Ở Resource Server, **không ép principal thành user** chỉ vì có một claim `sub`. Đối tượng nghiệp vụ có thể cần quyền ứng dụng và phân vùng tenant riêng.

### 8.4. Device Authorization Grant tại Token Endpoint

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=DEVICE_CODE_VALUE&client_id=booking-tv
~~~

Đối với public client, `client_id` giúp nhận diện client theo registration. `OAuth2DeviceCodeAuthenticationProvider` cần kiểm tra device code, client binding, thời hạn và trạng thái user verification/consent.

Một số phản hồi phù hợp theo RFC 8628:

| Trạng thái | OAuth2 error | Hành động của thiết bị |
| --- | --- | --- |
| User chưa hoàn tất | `authorization_pending` | Tiếp tục poll sau ít nhất `interval` |
| Polling quá nhanh | `slow_down` | Tăng khoảng chờ thêm 5 giây |
| User từ chối | `access_denied` | Dừng polling |
| Device session hết hạn | `expired_token` | Dừng, khởi tạo phiên mới khi user yêu cầu |
| User đã approve và grant hợp lệ | Token response thành công | Lưu token an toàn, dừng polling |

**Thiết bị không được gửi `user_code` thay `device_code`.** `user_code` được nhập bởi Resource Owner ở Device Verification Endpoint; `device_code` là credential của thiết bị tại Token Endpoint.

### 8.5. Token Exchange Grant

Ví dụ khái niệm theo RFC 8693:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&subject_token=SUBJECT_TOKEN&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&audience=booking-api
~~~

Trong phiên bản có `OAuth2TokenExchangeAuthenticationProvider`, hệ thống phải kiểm tra các ràng buộc như loại subject token, token còn hợp lệ và đáng tin, client được phép exchange, đối tượng nhận token, scopes và mối quan hệ user/client được phép ủy quyền. Nếu có `actor_token` hoặc `requested_token_type`, cần tuân thủ quy tắc của RFC và implementation.

**Không suy rằng Token Exchange cho phép client bất kỳ dùng token của khách hàng bất kỳ để lấy token mới.** Client phải có quyền exchange cụ thể, token đầu vào phải được xác minh và audience/resource đích phải bị giới hạn. Khả năng hỗ trợ các biến thể của RFC 8693 phụ thuộc phiên bản Spring và cấu hình cụ thể; hãy kiểm thử trên môi trường mục tiêu.

## 9. Bước D: Token Generator và Authorization Service làm gì?

Khi provider đã xác minh grant hợp lệ, nó có thể sử dụng các core components:

| Thành phần | Vai trò |
| --- | --- |
| `OAuth2TokenGenerator` | API tạo token dựa trên `OAuth2TokenContext`, loại token và settings |
| `DelegatingOAuth2TokenGenerator` | Điều phối các token generator phù hợp |
| `JwtGenerator` | Tạo JWT cho loại token được cấu hình phù hợp |
| `OAuth2AccessTokenGenerator` | Tạo access token, thường reference/opaque khi cấu hình dạng đó |
| `OAuth2RefreshTokenGenerator` | Tạo refresh token theo policy |
| `OAuth2TokenCustomizer` | Tùy biến claim hoặc thông tin token trong phạm vi cho phép |
| `OAuth2AuthorizationService` | Lưu trạng thái authorization, code/token, metadata, invalidation |
| `RegisteredClientRepository` | Cung cấp grant types, token settings, scopes và client auth methods |
| `OAuth2AuthorizationConsentService` | Dữ liệu consent, khi grant liên quan tới Resource Owner |

**Tách biệt trách nhiệm:** provider quyết định grant có hợp lệ hay không; token generator tạo token theo context; authorization service quản lý trạng thái. Nếu tùy biến generator làm mất một generator cần thiết, một grant có thể không tạo được access token/ID token/refresh token tương ứng.

### 9.1. Token response thành công

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "booking.read"
}
~~~

Tùy grant và chính sách, response có thể chứa `refresh_token` và/hoặc `id_token`. **ID token** thuộc OpenID Connect và không được phát chỉ vì một client gửi `scope=openid` trên grant tùy ý nếu protocol/provider không cho phép. **Access token** mới là credential để Resource Server xem xét quyền truy cập API.

### 9.2. Không dùng Token Generator thay cho authorization check

Ví dụ sai lầm:

~~~java
// Sai nguyên tắc: tự tạo access token sau khi chỉ nhìn grant_type.
if ("client_credentials".equals(request.getParameter("grant_type"))) {
    // Không xác minh client, grant permission, scope, rate limit...
    // rồi tự phát token ngay từ controller.
}
~~~

Hãy để request đi qua provider chuẩn. Nếu thêm grant đặc thù, custom provider phải **tự thực hiện đầy đủ điều kiện grant của chính nó** và chỉ gọi token generator sau khi hợp lệ.

## 10. Cấu hình SecurityFilterChain và Token Endpoint

### 10.1. Cấu hình mặc định nên là điểm xuất phát

Trên Spring Authorization Server 1.x, token endpoint được cấu hình qua `OAuth2AuthorizationServerConfigurer`. Ví dụ sau không override provider mặc định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, configurer ->
                configurer.tokenEndpoint(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giới hạn:** đoạn này giả định đã có bean `RegisteredClientRepository`, `OAuth2AuthorizationService`, cấu hình token generator/keys/issuer, user authentication, và các thành phần cần thiết cho AS. Đối với authorization endpoint cần redirect user chưa login, ứng dụng thực tế thường cấu hình `LoginUrlAuthenticationEntryPoint("/login")` cho request HTML thuộc chain AS. Ví dụ ở đây tập trung vào pipeline token nên chưa đưa mọi chi tiết browser login/OIDC.

`SecurityFilterChain` đầu tiên dùng `getEndpointsMatcher()` để các endpoint OAuth2 được xử lý bởi filter chuyên dụng; chain thứ hai là ứng dụng web/login. Không để chain tổng quát bắt `anyRequest` trước chain AS.

### 10.2. Tùy chỉnh chính sách của provider mặc định

Nếu muốn bổ sung validation cho `client_credentials`, dùng `authenticationProviders(...)` để tìm provider mặc định rồi gắn validator, **giữ validation scope mặc định**.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(token -> token
                .authenticationProviders(providers ->
                    providers.forEach(provider -> {
                        if (provider instanceof
                                OAuth2ClientCredentialsAuthenticationProvider
                                    clientCredentialsProvider) {

                            var validator =
                                OAuth2ClientCredentialsAuthenticationValidator
                                    .DEFAULT_SCOPE_VALIDATOR
                                    .andThen(context -> {
                                        String clientId = context
                                            .getRegisteredClient().getClientId();
                                        boolean wantsSensitiveScope = context
                                            .getAuthentication().getScopes()
                                            .contains("payments.write");

                                        if ("batch-reporter".equals(clientId)
                                                && wantsSensitiveScope) {
                                            throw new OAuth2AuthenticationException(
                                                new OAuth2Error(
                                                    OAuth2ErrorCodes.INVALID_SCOPE));
                                        }
                                    });

                            clientCredentialsProvider
                                .setAuthenticationValidator(validator);
                        }
                    })
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Các import bổ sung:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientCredentialsAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientCredentialsAuthenticationValidator;
~~~

**Hai snippet là hai lựa chọn cấu hình thay thế**, không khai báo đồng thời hai bean `@Order(1)` giống nhau từ các ví dụ. Cấu hình thứ hai giả định các bean và import của ví dụ đầu tiên đã tồn tại.

Tại sao dùng `DEFAULT_SCOPE_VALIDATOR.andThen(...)`?

- `setAuthenticationValidator(...)` **thay validator hiện tại**, không tự giữ validator cũ.
- Default validator bảo vệ giới hạn scope theo registration.
- Logic riêng chỉ siết yêu cầu cho client `batch-reporter`.
- Không vô tình hợp thức hóa `payments.write` cho client chưa được cấp scope đó.
- Chính sách custom cần có test rằng scope không đăng ký vẫn bị từ chối, kể cả khi custom rule không match.

Cách này cho thấy **thay đổi đúng provider của grant liên quan**, không sửa các provider `authorization_code` hay `refresh_token`.

### 10.3. Khi nào dùng `authenticationProvider(...)`?

Khi muốn thêm **một loại grant mới** không nằm trong bộ provider mặc định, cần:

1. Định nghĩa một `AuthorizationGrantType` mới bằng một URI có namespace rõ ràng.
2. Đăng ký grant type đó trong `RegisteredClient` được phép sử dụng.
3. Viết `AuthenticationConverter` nhận diện chính xác request và tạo loại `Authentication` riêng.
4. Viết `AuthenticationProvider` với `supports(...)` đúng loại riêng, xác minh client, proof, scope và policy của grant.
5. Sử dụng `OAuth2TokenGenerator` và `OAuth2AuthorizationService` để phát/lưu token theo quy tắc.
6. Đăng ký cả converter và provider tại `OAuth2TokenEndpointConfigurer`.
7. Test request hợp lệ, sai, replay, nhiều client, token lifecycle và các grant mặc định không bị ảnh hưởng.

Không thêm một provider mới có `supports(Authentication.class) == true`. Một provider bắt mọi authentication có thể làm hỏng hoặc làm yếu toàn bộ pipeline.

## 11. Ví dụ triển khai extension grant có kiểm soát

Giả sử hệ thống có grant nội bộ `urn:example:params:oauth:grant-type:partner_ticket`. **Đây không phải grant chuẩn OAuth2** và chỉ được dùng nếu tổ chức thực sự có một credential/proof để xác minh; không nên coi bất kỳ chuỗi `ticket` do client gửi cũng đáng tin.

### 11.1. Registration phải cho phép grant cụ thể

~~~java
AuthorizationGrantType partnerGrant = new AuthorizationGrantType(
    "urn:example:params:oauth:grant-type:partner_ticket");

RegisteredClient partnerClient = RegisteredClient
    .withId("partner-client-id")
    .clientId("partner-backend")
    .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(partnerGrant)
    .scope("booking.read")
    .build();
~~~

Đoạn trên cần được đặt trong factory/configuration có các import và biến `passwordEncoder`, `secretFromSecureConfig`. Đối với client production, phải lưu secret an toàn, xoay credential và lưu registration nhất quán.

### 11.2. Converter chỉ nhận đúng grant của nó

Ví dụ **khung logic**:

~~~java
final class PartnerTicketAuthenticationConverter
        implements AuthenticationConverter {

    private static final String GRANT_TYPE =
        "urn:example:params:oauth:grant-type:partner_ticket";

    @Override
    public Authentication convert(HttpServletRequest request) {
        if (!GRANT_TYPE.equals(
                request.getParameter(OAuth2ParameterNames.GRANT_TYPE))) {
            return null; // Không làm mất converter của grant chuẩn.
        }

        // Phải kiểm tra HTTP method, tham số trùng lặp,
        // ticket bắt buộc, định dạng và client authentication.
        //
        // Sau khi validate request:
        // return new PartnerTicketAuthenticationToken(clientPrincipal, ticket);
        //
        // Đoạn này là skeleton, chưa có kiểu Token tự định nghĩa.
        throw new UnsupportedOperationException(
            "Complete parsing + validation before use");
    }
}
~~~

Đây là **mẫu mô tả ranh giới**, cố ý không phải implementation có thể chạy production. `PartnerTicketAuthenticationToken` phải là loại `Authentication` riêng của ứng dụng, thường kế thừa `OAuth2AuthorizationGrantAuthenticationToken` theo thiết kế của Spring Authorization Server.

### 11.3. Provider custom phải thực sự xác minh credential

Một provider đúng phải:

- Xác định `OAuth2ClientAuthenticationToken` đã được xác thực/nhận diện và client được phép `partner_ticket`.
- Kiểm tra ticket có thật, còn hạn, đúng issuer/tenant/client và **chưa được sử dụng** nếu ticket một lần.
- Chống replay với transaction/atomicity khi cần.
- Xác định subject và scopes từ **nguồn tin cậy**; không chấp nhận user/role do client tự khai.
- Kiểm tra audience, resource và các ràng buộc policy.
- Chỉ sau đó tạo token qua generator, ghi trạng thái qua authorization service.
- Trả `OAuth2AccessTokenAuthenticationToken` hoặc ném `OAuth2AuthenticationException` đúng semantics.

Không tự viết một provider “nhận mọi ticket, đổi thành JWT” chỉ vì converter đã phân loại đúng grant type. Phân loại request và **chứng minh quyền cấp token** là hai trách nhiệm khác nhau.

### 11.4. Đăng ký cặp converter/provider

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(
        HttpSecurity http,
        AuthenticationConverter partnerTicketConverter,
        AuthenticationProvider partnerTicketProvider)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(token -> token
                .accessTokenRequestConverter(partnerTicketConverter)
                .authenticationProvider(partnerTicketProvider)
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Ở đây `partnerTicketConverter`/`partnerTicketProvider` phải là **bean ứng dụng đã triển khai đầy đủ**; khung converter ở mục 11.2 chưa đủ. Không copy đồng thời bean `authorizationServerSecurity` từ mục 10 vào cùng dự án.

Tài liệu Spring có hướng dẫn chính thức: [How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html). Hãy ưu tiên cách tổ chức converter/provider và token context theo guide thay vì tự viết HTTP token response từ controller.

### 11.5. Cần test “không phá grant mặc định”

Khi cài extension grant, ngoài test `partner_ticket`, hãy xác minh:

- Authorization Code vẫn xử lý code/redirect URI/PKCE.
- Refresh Token vẫn kiểm tra active/scope/client binding.
- Client Credentials vẫn kiểm tra scope.
- Device Code vẫn trả `authorization_pending` hoặc token theo approval.
- Token Exchange (nếu sử dụng) vẫn xác minh subject token/audience.
- Một request `partner_ticket` từ client không được đăng ký grant bị từ chối.
- Một request `client_credentials` không bị custom converter “nuốt”.

**Tối ưu hóa bảo mật là giữ nguyên provider mặc định và bổ sung trong phạm vi hẹp**, thay vì thay cả danh sách converters/providers chỉ để hỗ trợ một use case.

## 12. OAuth2 error response và cách đọc nguyên nhân

Khi token endpoint không cấp token, client thường nhận JSON error theo OAuth2. Các lỗi không có cùng nguyên nhân:

| Error | Tình huống thường gặp | Thành phần cần điều tra |
| --- | --- | --- |
| `invalid_request` | Thiếu hoặc trùng tham số bắt buộc, body sai định dạng | Converter/filter, HTTP request |
| `invalid_client` | Client auth sai hoặc client không được nhận diện | Client authentication filter/provider |
| `unauthorized_client` | Client hợp lệ nhưng không được đăng ký sử dụng grant yêu cầu | RegisteredClient + grant provider |
| `unsupported_grant_type` | Grant type không được Token Endpoint hỗ trợ | Danh sách converters/providers |
| `invalid_grant` | Authorization code/refresh token/grant không hợp lệ, sai binding hoặc hết hạn | Provider của grant, authorization store |
| `invalid_scope` | Xin scope trái registration/authorization | Provider của grant, validator |
| `authorization_pending` | Device user chưa approve | Device Code Provider |
| `slow_down` | Device poll quá nhanh | Device Code Provider + polling interval |
| `access_denied` | User từ chối device approval | Device state và Token Endpoint |
| `expired_token` | Device code hết hạn | Device Code Provider |
| `server_error` | AS xử lý lỗi nội bộ phù hợp giao thức | Observability, DB, generator; không log token |

Các mã ở bảng biểu thị **những nguyên nhân phổ biến**, không cam kết mỗi bản Spring hoặc profile đều trả cùng lỗi cho mọi combination sai. Đối với token exchange, có thêm error theo RFC 8693 như `invalid_target` tùy yêu cầu `resource/audience` và implementation.

### 12.1. Ví dụ unsupported grant_type

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "unsupported_grant_type"
}
~~~

Ví dụ trên giả định client authentication đã hợp lệ để request đi đến lớp phân loại grant. Nếu credential client sai, client có thể nhận `invalid_client` trước khi kiểm tra `grant_type`.

### 12.2. Ví dụ invalid grant

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

Không nên trả `error_description` tiết lộ một code thuộc user nào, refresh token có thật hay thiết bị nào đã được approve. AS cần log metadata tối thiểu để điều tra mà không rò credential.

### 12.3. Đừng thay tất cả lỗi bằng redirect tới /login

Token endpoint là API của client. Đưa SDK OAuth2 đến trang HTML login khi `invalid_grant` hoặc `invalid_client` chỉ làm hỏng contract và có thể che giấu lỗi thực tế.

Khi login người dùng cần tương tác, flow phù hợp là bắt đầu **authorization request mới ở Authorization Endpoint**, không phải để token endpoint phản hồi một form login tùy ý.

## 13. Bảo mật khi tùy chỉnh provider và converter

### 13.1. Những điều tuyệt đối không được bỏ qua

- **Client authentication:** confidential client phải chứng minh credential hợp lệ; public client chỉ dùng grant được thiết kế cho nó.
- **Grant type permission:** `RegisteredClient.authorizationGrantTypes` phải cho phép grant đang dùng.
- **Token binding:** authorization code, refresh token và device code phải được đối chiếu với client/authorization phù hợp.
- **Scope:** không cấp vượt scope trong registration hoặc `authorizedScopes` thực sự của grant.
- **PKCE:** không bỏ kiểm tra `code_verifier` khi code được ràng buộc PKCE.
- **Redirect URI:** authorization code phải khớp callback theo quy tắc OAuth2.
- **Token exchange:** không cho phép đổi token tới audience/resource tùy tiện hoặc impersonation không được phép.
- **Token format và audience:** JWT/opaque cần đúng issuer, audience, lifetime và claim policy.
- **Atomicity:** code một lần, refresh rotation và những credential dùng một lần cần bảo vệ trước request đồng thời.

### 13.2. Chia ranh giới trách nhiệm giữa các nguồn dữ liệu

| Nguồn | Ý nghĩa | Lỗi nếu dùng sai |
| --- | --- | --- |
| `RegisteredClientRepository` | Client, grant types, auth methods, scopes đã đăng ký | Chỉ dựa vào client registration để tự cấp scope consent chưa có |
| `OAuth2AuthorizationService` | Grant, code, token, authorized scopes và trạng thái | Bỏ trạng thái revoke/reuse khi đổi token |
| `OAuth2AuthorizationConsentService` | Consent của Resource Owner khi cần | Xem consent là quyền truy cập mọi tài nguyên vĩnh viễn |
| `UserDetailsService` | Nguồn tài khoản Resource Owner khi login | Dùng để xác minh client secret tại token endpoint |
| `OAuth2TokenGenerator` | Tạo token từ context đã qua kiểm tra | Gọi trực tiếp mà bỏ grant validation |
| `SecurityContextHolder` | Authentication của request hiện tại | Cho rằng luôn là Resource Owner, kể cả Client Credentials |

### 13.3. Không log request body token endpoint

Token endpoint có thể nhận client secret, authorization code, refresh token, device code, subject token hoặc client assertion. **Không ghi raw `Authorization` header, body hay response token** vào log, tracing, reverse proxy access log hoặc APM.

Thay vào đó log có kiểm soát: request/correlation ID, grant type trong allowlist, client ID sau xác thực, outcome, error code, latency, tên provider (nếu cần) và sự kiện audit. Khi log token identifier, dùng mã audit nội bộ hoặc giá trị đã hash với chính sách phù hợp, không log raw credential.

## 14. Kiểm thử đúng nghĩa “điều phối theo grant_type”

### 14.1. Ma trận test tối thiểu

| Yêu cầu | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| `authorization_code` hợp lệ | Đúng client, code, URI, PKCE | Cấp token theo grant |
| `authorization_code` sai client | Code cấp cho A, client B đổi | Từ chối, không phát token |
| `authorization_code` dùng lại | Code đã đổi một lần | Từ chối |
| `refresh_token` hợp lệ | RT active, đúng client, authorized scopes | Cấp access token mới |
| `refresh_token` sai scope | Scope xin thêm ngoài authorization | Từ chối, không cấp rộng hơn |
| `refresh_token` sai client | RT cấp cho A, B dùng | Từ chối |
| `client_credentials` hợp lệ | Confidential client có grant/scope | Cấp access token |
| `client_credentials` với public client không được phép | Method/grant không phù hợp | Từ chối |
| `client_credentials` xin scope trái phép | Scope ngoài registration/policy | `invalid_scope` |
| Device Code đang pending | User chưa approve | `authorization_pending` |
| Device Code bị từ chối | User deny có ghi trạng thái đúng | `access_denied` |
| Device Code hết hạn | Vượt device session TTL | `expired_token` |
| Device Code poll quá nhanh | Không tôn trọng interval | `slow_down` theo policy |
| Token Exchange hợp lệ | Subject token, audience, policy đúng | Cấp token nếu tính năng được bật và hỗ trợ |
| Token Exchange audience không được phép | Sai target policy | Từ chối |
| Grant type không được hỗ trợ | `grant_type=urn:example:unknown` | `unsupported_grant_type` nếu client auth hợp lệ |
| Client được xác thực nhưng không được grant | RegisteredClient thiếu grant type | `unauthorized_client` hoặc lỗi phù hợp |
| Client secret sai | Bất kể grant nào | `invalid_client`, không gọi cấp token |
| Grant thiếu tham số bắt buộc | Body sai | `invalid_request` hoặc lỗi grant phù hợp |
| Custom grant nhận đúng loại | Converter/provider custom | Chỉ chạy với grant custom |
| Custom grant không nhận grant khác | Grant mặc định vẫn có converter | Không chặn, không thay đổi semantics |
| Token store lỗi | DB outage/transaction rollback | Không phản hồi thành công khi không lưu grant đúng |

**Phương pháp test:** làm sai **một điều kiện tại một thời điểm**. Nếu code đã được dùng rồi, test “redirect URI sai” có thể fail chỉ vì code replay — không chứng minh URI validator chạy.

### 14.2. Kiểm thử HTTP bằng MockMvc

Với `spring-security-test` và context AS thật, ví dụ kiểm tra client credentials hợp lệ:

~~~java
@Test
void clientCredentialsGrantIssuesAccessToken() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("batch-reporter", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "booking.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

Điều kiện: test fixture đã đăng ký `batch-reporter` với `CLIENT_SECRET_BASIC`, `CLIENT_CREDENTIALS`, `booking.read`, secret được hash phù hợp với `PasswordEncoder`, và AS có token generator/JWK chính xác. Ví dụ cần static imports của MockMvc `post`, `httpBasic`, matchers và `jsonPath`.

Kiểm tra grant bị cấm:

~~~java
@Test
void clientNotAllowedToRefreshIsRejected() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("batch-reporter", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "refresh_token")
            .param("refresh_token", "not-a-real-token"))
        .andExpect(status().is4xxClientError())
        .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

Đây là **smoke test phủ định**, nhưng vì refresh token cũng không có thật nên chưa chứng minh rõ *quy tắc cấm grant*. Muốn kiểm tra chính xác `unauthorized_client`, chuẩn bị một refresh token hợp lệ thuộc client phù hợp nhưng client đang yêu cầu không được grant; hoặc test provider với fixture phù hợp. Khi test client binding, cần có hai clients có registration/credential hợp lệ để tránh fail sớm ở client authentication.

### 14.3. Test riêng converter/provider

Với một extension grant, nên có ba tầng kiểm thử:

1. **Unit test converter**: grant custom trả đúng authentication; grant mặc định trả `null`; tham số thiếu/trùng bị từ chối.
2. **Unit test provider**: `supports(...)` chỉ nhận loại custom; credential sai, client sai, scope sai, replay phải từ chối; credential hợp lệ phát token từ context đã xác thực.
3. **Integration test FilterChain**: POST tới `/oauth2/token` qua client authentication filter và token endpoint; có JWT/opaque token response; các grant mặc định vẫn hoạt động.

`@WithMockUser` không thay cho test Client Authentication. Nó giả lập user principal và có thể khiến test không đi qua `OAuth2ClientAuthenticationFilter` như production. Khi đánh giá protocol đúng nghĩa, test phải dùng các client credentials/assertions/PKCE/code tương ứng qua endpoint.

### 14.4. Test thứ tự và behavior khi nhiều provider

Nếu hệ thống có custom provider hỗ trợ cùng loại với provider mặc định, cần test:

- Provider nào được chọn và tại sao.
- Provider có return `null`/throw exception/return Authentication theo đúng hợp đồng hay không.
- Lỗi security có bị provider kế tiếp “nuốt” và cấp token không.
- Việc thay list providers có làm mất một grant mặc định không.
- Khi tăng version Spring, list converters/providers có thay đổi thứ tự hoặc bổ sung loại mới không.

Với đa số ứng dụng, cách ổn định hơn là **mở rộng bằng một loại `Authentication` riêng**, không chồng lên loại của grant chuẩn.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| `invalid_client` ngay với mọi grant | Sai secret, auth method, key/cert, client chưa đăng ký | Kiểm tra client authentication trước, không debug grant provider vội |
| `unsupported_grant_type` | Grant không có converter/provider, thiếu extension registration | Kiểm tra version và `OAuth2TokenEndpointConfigurer` |
| `unauthorized_client` | RegisteredClient không có grant type | Kiểm tra `authorizationGrantTypes` |
| `invalid_grant` khi đổi code | Code hết hạn, đã dùng, sai client/URI/PKCE | Authorization record và Authorization Code provider |
| `invalid_grant` khi refresh | Token hết hạn, revoked, rotated, client mismatch | Refresh Token provider và authorization store |
| `invalid_scope` với client_credentials | Scope ngoài registration hoặc custom validator | Provider/validator của Client Credentials |
| Device polling mãi pending | User chưa approve hoặc store không chia sẻ | Device Verification flow, authorization persistence |
| Device polling `slow_down` liên tục | Client gửi quá nhanh | Tôn trọng `interval`, tăng backoff |
| Token exchange bị từ chối | Version chưa hỗ trợ, client thiếu grant hoặc audience/subject token sai | RFC 8693, provider/policy |
| Client Credentials nhận thông tin người dùng không đúng | Đồng nhất client principal với Resource Owner | Phân biệt client identity và user identity |
| Token phát ra nhưng RS trả 401 | Issuer, audience, key/format, token type không khớp | JWT decoder hoặc opaque introspector ở RS |
| Có provider custom nhưng không được gọi | Converter không tạo đúng loại Authentication; `supports(...)` sai | Test converter, provider registration và matcher |
| Provider custom “nuốt” mọi grant | Converter trả Authentication quá rộng hoặc provider supports quá rộng | Giới hạn grant type và class |
| Sau nâng cấp framework grant mới không hoạt động | Thay đổi API/provider/setting giữa versions | Đối chiếu tài liệu và regression test |
| Lỗi chỉ xảy ra trên một AS instance | Registration/authorization/key store không nhất quán | Kiểm tra persistence, JWK rotation, deployment |

### 15.1. Lộ trình chẩn đoán trong production

1. Xác minh request đến đúng issuer và `/oauth2/token` qua HTTPS.
2. Kiểm tra `SecurityFilterChain` nào nhận request.
3. Client authentication filter có nhận diện/xác thực đúng RegisteredClient không?
4. `grant_type` nhận được là giá trị nào, converter có tạo đúng loại Authentication không?
5. Provider nào hỗ trợ loại đó, client có quyền dùng grant không?
6. Các điều kiện riêng của grant (code/PKCE, RT, scope, device, subject token) đạt không?
7. Token generator có tạo được token mong muốn và authorization service đã lưu trạng thái chưa?
8. Response handler có trả OAuth2 JSON đúng không?
9. Nếu RS từ chối access token, kiểm tra độc lập issuer/audience/expiry/scope và token format.

Không ghi raw token, client assertion, secret hoặc toàn bộ body để tìm nguyên nhân lỗi.

## 16. Các lỗi thiết kế cần tránh

| Sai lầm | Hệ quả | Nguyên tắc đúng |
| --- | --- | --- |
| Xem `grant_type` như client authentication | Client không được xác minh trước cấp token | Tách client auth filter với grant provider |
| Chỉ có client secret đúng là được mọi grant | Bỏ qua quyền grant type | Kiểm tra RegisteredClient và policy |
| Chọn provider theo chuỗi mà không kiểm tra supports/type | Dễ xử lý sai loại credential | Dùng AuthenticationConverter và AuthenticationProvider đúng hợp đồng |
| Custom converter luôn trả non-null | Các grant chuẩn không còn hoạt động | Trả `null` cho grant không thuộc phạm vi |
| Custom provider hỗ trợ mọi Authentication | Bỏ qua provider chuẩn, mở rộng quyền trái phép | Chỉ hỗ trợ loại Authentication custom |
| Thay provider list mà bỏ các provider mặc định | Grant hợp lệ thất bại hoặc logic thiếu kiểm tra | Giữ defaults và thêm extension có test |
| Custom scope validator bỏ default validator | Client xin scope không đăng ký được chấp nhận | Chain `DEFAULT_SCOPE_VALIDATOR` và policy riêng |
| Dùng Client Credentials để tạo user token giả | Không có Resource Owner authentication/consent | Giữ client identity, dùng grant phù hợp |
| Refresh token cấp thêm scope theo registration | Vượt scope đã được consent | Giới hạn `authorizedScopes` |
| Bỏ kiểm tra PKCE khi đổi code | Code bị đánh cắp có thể đổi token | Giữ Authorization Code provider mặc định |
| Token exchange không kiểm tra audience | Token mới có quyền tới API trái phép | Ràng buộc token type, target và policy |
| Dùng refresh token làm access token | Credential bị gửi sai nơi | Chỉ dùng RT tại Token Endpoint |
| Redirect token endpoint tới /login | SDK nhận HTML thay OAuth2 JSON | Trả OAuth2 error đúng chuẩn |
| Tắt/ghi toàn bộ HTTP body vào log | Lộ secret/code/refresh token | Redact và audit metadata tối thiểu |
| Không thử test AS nhiều instance | Mất code/RT hoặc lỗi race | Authorization store nhất quán và test concurrent |
| Test bằng `@WithMockUser` rồi kết luận client auth đúng | Bỏ qua xác minh client thực tế | HTTP test qua filter với credential thực của fixture |

## 17. Checklist trước khi đưa vào vận hành

- [ ] Token Endpoint được bảo vệ bởi AS SecurityFilterChain, matcher và `@Order` chính xác.
- [ ] Đã xác định các grant types thực sự hỗ trợ theo **phiên bản thư viện đang triển khai**.
- [ ] Client authentication methods được cấu hình và test tách biệt khỏi grant providers.
- [ ] Mỗi RegisteredClient chỉ có các `authorizationGrantTypes` cần thiết.
- [ ] Các converter mặc định còn hoạt động; converter custom chỉ nhận đúng grant riêng.
- [ ] Provider custom có `supports(...)` hẹp và kiểm tra client, proof, scope, audience.
- [ ] Authorization Code có kiểm tra code một lần, client binding, redirect URI, PKCE.
- [ ] Refresh Token có kiểm tra trạng thái, binding, scopes và rotation/reuse.
- [ ] Client Credentials không giả định có Resource Owner hay refresh token.
- [ ] Device Code tuân thủ pending, slow_down, denied, expired và interval.
- [ ] Token Exchange (nếu bật) có policy subject token, audience/resource và delegation.
- [ ] OAuth2TokenGenerator + AuthorizationService hoạt động chính xác sau restart/failover.
- [ ] Token response và error response tuân thủ OAuth2; không redirect HTML cho lỗi grant.
- [ ] Có test cả happy path, wrong client, forbidden grant, invalid scope, replay và custom extension.
- [ ] Có bảo vệ rate limit, TLS, secret management, audit và không log raw token.
- [ ] Có quy trình theo dõi security advisories, release notes và regression khi nâng version.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `OAuth2ClientAuthenticationFilter` và `OAuth2TokenEndpointFilter` khác nhau thế nào?

**Đáp án:** Filter thứ nhất xác thực/nhận diện OAuth2 Client theo phương thức đăng ký. Filter thứ hai parse grant request, chọn provider xử lý grant và trả OAuth2 token/error response.

**Câu 2.** Vì sao `ProviderManager` không đơn giản là `switch(grant_type)`?

**Đáp án:** `grant_type` được converter ánh xạ thành một loại `Authentication` chuyên biệt; `AuthenticationManager` điều phối các provider dựa trên `supports(...)` và kết quả xác thực. Loại grant trong HTTP request không thay thế các kiểm tra client, quyền grant, trạng thái token.

**Câu 3.** Client đã xác thực đúng secret nhưng không được phép dùng `refresh_token`, điều gì phải xảy ra?

**Đáp án:** AS từ chối grant. Xác thực client thành công không có nghĩa client được cấp mọi loại authorization grant.

**Câu 4.** Tại sao `OAuth2ClientCredentialsAuthenticationProvider` không phải thành phần xử lý `client_secret_basic` cho mọi grant?

**Đáp án:** Nó xử lý **Client Credentials Grant**. Xác thực client secret chung được thực hiện qua các component client authentication khác của AS.

**Câu 5.** Khi bổ sung validator scope cho Client Credentials, vì sao cần dùng `DEFAULT_SCOPE_VALIDATOR.andThen(...)`?

**Đáp án:** Vì `setAuthenticationValidator(...)` thay validator hiện tại. Nối validator mặc định giúp giữ giới hạn scope theo registration trước khi áp dụng điều kiện nghiệp vụ bổ sung.

**Câu 6.** `grant_type=authorization_code` và `grant_type=refresh_token` đều nhận một chuỗi credential, có thể dùng cùng provider không?

**Đáp án:** Không nên. Code và refresh token có lifetime, binding, replay policy và scope khác nhau; Spring Authorization Server cung cấp provider riêng để kiểm tra đúng semantics từng grant.

**Câu 7.** `grant_type=password` mặc định có được hỗ trợ không?

**Đáp án:** Không trong danh sách provider mặc định của SAS 1.5.x. Không nên bổ sung grant này chỉ để đơn giản hóa UI/login.

**Câu 8.** Converter custom xử lý đúng `partner_ticket`, vậy đã đủ an toàn để cấp JWT chưa?

**Đáp án:** Chưa. Provider phải xác minh client, proof/ticket, authorization, scope, audience, replay; token generator chỉ được gọi sau khi kiểm tra đạt.

**Câu 9.** Với Device Code, tại sao `authorization_pending` không phải lỗi cấu hình Token Endpoint?

**Đáp án:** Đây là trạng thái hợp lệ của Device Grant khi user chưa hoàn tất verification/consent. Client phải chờ đúng interval và tiếp tục polling theo RFC 8628.

## 19. Tài liệu chính thức và kết luận

Tài liệu cần đối chiếu theo **đúng phiên bản chạy trên dự án**:

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html)
- [Spring Authorization Server — How-to: Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [RFC 6749 — OAuth 2.0 Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)

**Kết luận:** Trong Spring Authorization Server, điều phối `grant_type` là chuỗi hai lớp: **converter hiểu request và tạo đúng loại `Authentication`**, sau đó **AuthenticationManager chọn provider hỗ trợ loại đó**. Mỗi provider phải kiểm tra client đã xác thực, quyền sử dụng grant, scopes và bằng chứng riêng trước khi token generator phát token. Cách tổ chức này giúp bổ sung extension grant có kiểm soát mà không viết lại toàn bộ Token Endpoint; đồng thời ngăn việc nhầm client authentication với grant authentication và tránh cấp token sai quyền trong hệ thống OAuth 2.0/OIDC.

