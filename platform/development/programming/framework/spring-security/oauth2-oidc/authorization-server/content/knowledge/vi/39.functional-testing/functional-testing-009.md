# Kiểm thử client registration động, PAR và client authentication

Một Authorization Server cần kiểm soát chặt chẽ client nào được phép tham gia, cách client gửi authorization request và cách client chứng minh danh tính tại các endpoint bảo mật. Khi hệ thống hỗ trợ OpenID Connect Dynamic Client Registration, Pushed Authorization Requests (PAR) và nhiều phương thức client authentication, kiểm thử chức năng phải xác minh cả metadata được lưu, hành vi HTTP và các quy tắc bảo mật.

Ba nhóm chức năng có quan hệ với nhau:

- **Dynamic Client Registration (DCR):** client đăng ký động và nhận metadata như `client_id`, redirect URI, grant type, scope và phương thức xác thực.
- **Pushed Authorization Requests (PAR):** client gửi authorization parameters trực tiếp đến server qua một request có xác thực, sau đó dùng `request_uri` ngắn hạn ở authorization endpoint.
- **Client authentication:** Authorization Server xác minh client tại các endpoint yêu cầu xác thực, chẳng hạn token endpoint hoặc PAR endpoint.

Bài học này tập trung vào kiểm thử chức năng cho Spring Authorization Server: xác minh cấu hình, chuẩn bị client, gửi request, kiểm tra response, kiểm tra dữ liệu được lưu và thử các tình huống từ chối.

## 1. Phạm vi và mục tiêu kiểm thử

Kiểm thử chức năng cần xác minh hành vi quan sát được từ góc nhìn client và Authorization Server. Một ca kiểm thử tốt không chỉ kiểm tra HTTP status; nó còn kiểm tra metadata, trạng thái lưu trữ và tác động bảo mật.

| Nhóm | Điều cần xác minh |
|---|---|
| Dynamic Client Registration | Endpoint được công bố và bật; metadata hợp lệ tạo client; dữ liệu được lưu; metadata không hợp lệ bị từ chối |
| Client registration policy | Redirect URI, grant type, response type, scope và auth method tuân theo allowlist/policy |
| PAR | Request được tiếp nhận; response chứa `request_uri` và thời hạn; authorization request tham chiếu đúng request đã push |
| PAR security | Client binding, thời hạn, request parameters và chính sách replay được kiểm soát |
| Client authentication | Phương thức đã đăng ký khớp với credential/assertion/certificate gửi lên |
| Negative paths | Thiếu credential, credential sai, assertion hết hạn, audience sai, chữ ký sai hoặc phương thức không được hỗ trợ đều bị từ chối |
| Persistence | Client registration và authorization request được lưu theo cơ chế bền vững cần thiết |
| Operational consistency | Discovery/metadata, issuer, JWKS và endpoint URI nhất quán giữa các replica |

Các bài kiểm thử nên chạy qua HTTP filter chain thật, với repository và encoder phù hợp. Unit test riêng cho validator hoặc service vẫn hữu ích, nhưng không thay thế kiểm thử tích hợp qua SecurityFilterChain, converter và authentication provider.

## 2. Chuẩn bị cấu hình và môi trường kiểm thử

### 2.1. Kiểm tra phiên bản và khả năng hỗ trợ

Spring Authorization Server phát triển theo phiên bản; tên API configurer, endpoint và khả năng hỗ trợ giao thức có thể thay đổi. Trước khi viết test, chốt phiên bản Spring Authorization Server và Spring Security đang dùng, sau đó xác nhận các tính năng được phiên bản đó cung cấp.

Đặc biệt, hãy xác minh:

- OIDC Client Registration Endpoint có trong phiên bản đang dùng và đã được bật.
- Pushed Authorization Request Endpoint có được hỗ trợ và đã được cấu hình.
- Các phương thức client authentication cần kiểm thử được hỗ trợ.
- Cấu hình JWT, JWK và mTLS phù hợp với phiên bản Spring Security tương ứng.

Không tạo endpoint giả trong test để bù cho tính năng chưa được framework hỗ trợ. Nếu DCR hoặc PAR được triển khai bằng extension riêng, test phải khởi chạy đúng extension đó và kiểm tra hành vi thực tế của nó.

### 2.2. Bật các endpoint cần kiểm thử

Ví dụ cấu hình theo API configurer mới, với endpoint OIDC Client Registration và PAR được bật rõ ràng:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .oidc(oidc -> oidc
                    .clientRegistrationEndpoint(Customizer.withDefaults())
                )
                .pushedAuthorizationRequestEndpoint(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Đây là cấu trúc minh họa. Trong ứng dụng thực tế, giữ các quy tắc authorization, Resource Server, exception handling, consent và các endpoint khác đang được sử dụng. Đối chiếu API với phiên bản dependency của dự án.

Có thể cấu hình đường dẫn endpoint trong `AuthorizationServerSettings`. Giá trị mặc định thường gặp của Spring Authorization Server là:

| Endpoint | Đường dẫn mặc định thường gặp |
|---|---|
| Token | `/oauth2/token` |
| Authorization | `/oauth2/authorize` |
| Pushed Authorization Request | `/oauth2/par` |
| OIDC Client Registration | `/connect/register` |
| JWK Set | `/oauth2/jwks` |

Dùng giá trị từ metadata/discovery hoặc cấu hình của ứng dụng làm nguồn chuẩn. Test không nên phụ thuộc vào chuỗi đường dẫn được chép từ một ví dụ nếu ứng dụng đã tùy chỉnh endpoint.

### 2.3. Dùng repository và credential test riêng

Test cần một `RegisteredClientRepository` có thể đọc lại client vừa đăng ký. Trong môi trường kiểm thử tích hợp, có thể dùng JDBC repository với database test hoặc repository in-memory nếu mục tiêu không bao gồm kiểm tra persistence.

Chuẩn bị tối thiểu:

- Một client confidential dùng `client_secret_basic`.
- Một client public dùng `none` và authorization code với PKCE.
- Một client dùng `private_key_jwt`, nếu phương thức này được bật.
- Một client dùng `client_secret_post`, nếu phương thức này được cho phép.
- Một client có redirect URI, grant type hoặc auth method không hợp lệ để kiểm tra nhánh từ chối.
- Một user test đã đăng nhập để hoàn tất authorization flow sau PAR.

Không dùng secret production, private key thật, certificate thật hoặc dữ liệu người dùng thật trong test.

## 3. Kiểm thử Dynamic Client Registration

### 3.1. Xác nhận endpoint được công bố

OIDC Discovery có thể công bố trường `registration_endpoint` khi server hỗ trợ Dynamic Client Registration.

Gọi discovery document:

~~~bash
curl -i https://auth.example.com/.well-known/openid-configuration
~~~

Kiểm tra:

- `issuer` đúng với issuer công khai.
- `registration_endpoint` tồn tại khi DCR được bật.
- URL registration trỏ đến đúng host, scheme và context path.
- Endpoint có thể truy cập qua ingress/reverse proxy theo cấu hình triển khai.

Nếu server không công bố `registration_endpoint`, xác minh OIDC Client Registration Endpoint đã được bật trong configurer và metadata provider của phiên bản đang dùng. Nếu endpoint được công bố nhưng trả `404`, kiểm tra endpoint setting và proxy routing.

### 3.2. Đăng ký một confidential web client

Một registration request minh họa:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Content-Type: application/json
Accept: application/json

{
  "application_type": "web",
  "client_name": "Billing Portal",
  "redirect_uris": [
    "https://billing.example.com/login/oauth2/code/portal"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "scope": "openid profile email",
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Nếu registration endpoint được bảo vệ bằng initial access token hoặc một cơ chế cấp quyền riêng, request phải gửi credential theo đúng policy đó. Không giả định endpoint luôn mở cho anonymous registration.

Khi request hợp lệ, kiểm tra response theo giao thức và cấu hình server. Thông thường registration thành công trả `201 Created` với metadata client được cấp, gồm `client_id` và các trường liên quan. Với confidential client dùng client secret, response có thể trả `client_secret` mới được sinh.

Các assertion cần kiểm tra:

- Response có `client_id` không rỗng và duy nhất.
- `redirect_uris`, `grant_types`, `response_types`, `scope` và `token_endpoint_auth_method` phản ánh metadata được chấp nhận.
- Client có thể được đọc lại qua `RegisteredClientRepository`.
- Redirect URI không bị tự ý mở rộng hoặc chuẩn hóa thành URI nguy hiểm.
- Secret được trả đúng theo giao thức và được lưu dưới dạng đã mã hóa bằng PasswordEncoder.
- Client có thể thực hiện authorization/token flow với cấu hình vừa được đăng ký.

Không log hoặc lưu bản rõ `client_secret` trong test report. Nếu response trả secret, chỉ giữ trong bộ nhớ test và dùng ngay trong ca kiểm thử.

### 3.3. Ví dụ kiểm thử bằng MockMvc

Ví dụ dưới đây giả định endpoint đã được bật và chính sách registration cho phép request test. Nếu endpoint cần initial access token, thêm header xác thực đúng với extension/policy của ứng dụng.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ClientRegistrationFunctionalTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RegisteredClientRepository registeredClientRepository;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void shouldRegisterConfidentialWebClient() throws Exception {
        String request = """
            {
              "application_type": "web",
              "client_name": "Billing Portal",
              "redirect_uris": [
                "https://billing.example.com/login/oauth2/code/portal"
              ],
              "grant_types": ["authorization_code", "refresh_token"],
              "response_types": ["code"],
              "scope": "openid profile email",
              "token_endpoint_auth_method": "client_secret_basic"
            }
            """;

        MvcResult result = mockMvc.perform(post("/connect/register")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(request))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.client_id").isNotEmpty())
            .andExpect(jsonPath("$.redirect_uris[0]")
                    .value("https://billing.example.com/login/oauth2/code/portal"))
            .andExpect(jsonPath("$.token_endpoint_auth_method")
                    .value("client_secret_basic"))
            .andReturn();

        String responseBody = result.getResponse().getContentAsString();
        JsonNode response = objectMapper.readTree(responseBody);
        String clientId = response.path("client_id").asText();

        RegisteredClient registeredClient =
                registeredClientRepository.findByClientId(clientId);

        assertThat(registeredClient).isNotNull();
        assertThat(registeredClient.getAuthorizationGrantTypes())
                .contains(AuthorizationGrantType.AUTHORIZATION_CODE);
        assertThat(registeredClient.getClientAuthenticationMethods())
                .contains(ClientAuthenticationMethod.CLIENT_SECRET_BASIC);
    }
}
~~~

Đoạn test cần các import và bean test thông thường như `post`, `status`, `jsonPath`, `objectMapper` và AssertJ. Endpoint path trong ví dụ là mặc định thường gặp; nên lấy từ cấu hình test nếu dự án đã tùy chỉnh.

Không assert secret đã lưu bằng cách so sánh với secret bản rõ. Hãy xác minh repository lưu giá trị đã mã hóa bằng PasswordEncoder hoặc xác minh client có thể xác thực bằng secret được trả trong response.

### 3.4. Kiểm tra policy của metadata

Dynamic registration là một đầu vào có ảnh hưởng trực tiếp đến bề mặt tấn công. Server không nên chấp nhận mọi metadata client gửi lên.

Các ca kiểm thử quan trọng:

| Dữ liệu gửi lên | Kết quả mong đợi |
|---|---|
| Thiếu `redirect_uris` trong trường hợp giao thức yêu cầu | Từ chối registration |
| Redirect URI không hợp lệ hoặc nằm ngoài policy | Từ chối registration |
| Grant type không được server hỗ trợ | Từ chối hoặc loại bỏ theo policy giao thức đã công bố |
| Response type không tương thích grant type | Từ chối registration |
| Scope không được phép | Từ chối hoặc giới hạn theo policy |
| `token_endpoint_auth_method` không hỗ trợ | Từ chối registration |
| `jwks_uri` không hợp lệ hoặc không thể tin cậy | Từ chối khi phương thức đăng ký yêu cầu JWKS URI |
| Metadata quá lớn hoặc JSON sai cấu trúc | Từ chối request |
| Client name chứa nội dung không hợp lệ | Xử lý an toàn, không ảnh hưởng log/UI |
| Đăng ký lặp lại cùng metadata | Cấp client ID mới hoặc xử lý theo policy; không ghi đè client cũ ngoài ý muốn |

Đối với redirect URI, áp dụng quy tắc so khớp nghiêm ngặt. Không chấp nhận wildcard hoặc tiền tố URL tùy tiện cho web client. Với native application, chỉ cho phép các dạng redirect URI được tiêu chuẩn và policy của ứng dụng chấp nhận.

### 3.5. Kiểm thử public client và PKCE

Public client không giữ được client secret an toàn trong ứng dụng cài trên thiết bị người dùng. Registration metadata thường khai báo:

~~~json
{
  "application_type": "native",
  "client_name": "Mobile App",
  "redirect_uris": [
    "com.example.mobile:/oauth2redirect"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "scope": "openid profile",
  "token_endpoint_auth_method": "none"
}
~~~

Sau khi đăng ký, kiểm tra:

- Client được lưu là public client theo policy.
- Không phát hành secret để client nhúng vào ứng dụng native.
- Grant type được giới hạn theo yêu cầu.
- PKCE được bắt buộc bằng `ClientSettings.requireProofKey(true)` hoặc cơ chế tương đương.
- Authorization request thiếu `code_challenge` hoặc dùng `plain` khi policy yêu cầu S256 sẽ bị từ chối.
- Token request có `code_verifier` sai sẽ bị từ chối.

Không tin metadata do client tự khai báo để quyết định client có được bỏ qua PKCE hay không. Server cần áp dụng policy dựa trên loại client và cấu hình tin cậy của chính server.

### 3.6. Kiểm thử registration access và quản trị client

Nếu server phát hành registration access token hoặc dùng initial access token, kiểm tra vòng đời token:

- Token được gửi trong header theo đúng cơ chế bearer được triển khai.
- Token sai, hết hạn hoặc không có quyền registration bị từ chối.
- Token chỉ cho phép thao tác trên client/resource mà nó đại diện.
- Client registration token không bị nhầm với access token dùng cho UserInfo hoặc API nghiệp vụ.
- Cập nhật/xóa client chỉ được phép khi endpoint và policy tương ứng đã bật.
- Thu hồi quyền quản lý registration làm token cũ mất hiệu lực theo policy.

Nếu ứng dụng không triển khai registration management token, không viết test giả định tính năng này tồn tại. Hãy kiểm thử chính xác cơ chế bảo vệ endpoint đang được dùng.

## 4. Kiểm thử Pushed Authorization Requests (PAR)

### 4.1. Mục tiêu của PAR

PAR cho phép client gửi authorization parameters đến Authorization Server qua một request back-channel. Server lưu request và trả về một `request_uri` ngắn hạn. Client dùng URI này khi chuyển người dùng đến authorization endpoint.

Luồng PAR:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as PAR Endpoint
    participant A as Authorization Endpoint
    participant U as End User

    C->>P: POST authorization parameters + client authentication
    P->>P: Xác thực client và validate parameters
    P-->>C: 201 Created, request_uri, expires_in
    C->>U: Chuyển trình duyệt đến authorization endpoint
    U->>A: GET /oauth2/authorize?client_id=...&request_uri=...
    A->>A: Tra cứu request_uri, kiểm tra client và thời hạn
    A-->>U: Tiếp tục xác thực/consent
~~~

PAR giúp giảm việc đưa toàn bộ authorization parameters qua front-channel và cho phép server kiểm tra request trước khi chuyển người dùng đến authorization endpoint.

### 4.2. Gửi một pushed authorization request hợp lệ

Một request minh họa với client secret basic:

~~~http
POST /oauth2/par HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=portal-client&
response_type=code&
redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&
scope=openid%20profile%20email&
state=st-123&
nonce=no-456&
code_challenge=<S256-CHALLENGE>&
code_challenge_method=S256
~~~

Các tham số thực tế phải phù hợp với client đã đăng ký. Ví dụ trên minh họa Authorization Code Flow có PKCE; không gửi code verifier đến PAR endpoint vì verifier được giữ ở client và gửi ở token request.

Response thành công thường có dạng:

~~~json
{
  "request_uri": "urn:ietf:params:oauth:request_uri:opaque-value",
  "expires_in": 90
}
~~~

Giá trị URI và thời hạn ở đây chỉ minh họa. Kiểm tra response thực tế phải bảo đảm:

- HTTP status là `201 Created` theo PAR.
- Có `request_uri` không rỗng và có định dạng URI được server hỗ trợ.
- `expires_in` là số giây dương.
- Request URI không tiết lộ authorization parameters hoặc dữ liệu người dùng.
- Server lưu request gắn với đúng client và thời hạn.
- Client có thể dùng request URI để bắt đầu authorization flow.

### 4.3. Ví dụ kiểm thử PAR endpoint

Ví dụ với `client_secret_basic`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PushedAuthorizationRequestFunctionalTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void shouldAcceptValidPushedAuthorizationRequest() throws Exception {
        MvcResult result = mockMvc.perform(post("/oauth2/par")
                .with(httpBasic("portal-client", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("client_id", "portal-client")
                .param("response_type", "code")
                .param("redirect_uri",
                        "https://portal.example.com/callback")
                .param("scope", "openid profile")
                .param("state", "state-123")
                .param("nonce", "nonce-456")
                .param("code_challenge", "S256_CHALLENGE_VALUE")
                .param("code_challenge_method", "S256")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.request_uri").isNotEmpty())
            .andExpect(jsonPath("$.expires_in").isNumber())
            .andReturn();

        JsonNode response = objectMapper.readTree(
                result.getResponse().getContentAsString());

        assertThat(response.path("expires_in").asLong()).isPositive();
    }
}
~~~

Trong test thực tế, tạo `code_challenge` đúng từ một `code_verifier` ngẫu nhiên theo S256, không dùng chuỗi tùy ý nếu validator của ứng dụng kiểm tra định dạng challenge. Credential và client phải được seed vào repository test trước khi gửi request.

### 4.4. Dùng request_uri tại authorization endpoint

Sau khi nhận `request_uri`, client chuyển trình duyệt đến authorization endpoint bằng `client_id` và `request_uri`:

~~~http
GET /oauth2/authorize?client_id=portal-client&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3Aopaque-value HTTP/1.1
Host: auth.example.com
~~~

Kiểm thử nên xác minh:

- Authorization Server tìm được request đã push.
- Request được gắn với đúng client.
- Redirect URI, response type, scope, state, nonce và PKCE parameters được lấy từ request đã lưu.
- Client không thể thay đổi các authorization parameter đã được server chấp nhận bằng cách thêm giá trị xung đột ở front-channel.
- Người dùng được chuyển đến bước xác thực/consent như authorization flow thông thường.
- Nếu request URI hết hạn hoặc không tồn tại, server trả lỗi giao thức phù hợp, thường là `invalid_request_uri`.

Không coi việc authorization endpoint trả về trang login là test thất bại. Khi user chưa đăng nhập, redirect đến trang login có thể là hành vi đúng. Test cần phân biệt redirect hợp lệ với lỗi `invalid_request_uri`, `invalid_request` hoặc `unauthorized_client`.

### 4.5. Các ca PAR âm và bảo mật

| Tình huống | Kết quả mong đợi |
|---|---|
| Không có client authentication với confidential client | Từ chối theo phương thức auth đã đăng ký |
| Sai client secret | `invalid_client` |
| `client_id` trong body khác client đã xác thực | Từ chối request |
| Redirect URI chưa đăng ký | `invalid_request` hoặc lỗi giao thức tương ứng |
| Response type/grant type không được phép | Từ chối request |
| Thiếu tham số bắt buộc | `invalid_request` |
| PKCE challenge sai định dạng hoặc method không được phép | Từ chối theo policy PKCE |
| Request URI không tồn tại | `invalid_request_uri` |
| Request URI hết hạn | `invalid_request_uri` |
| Client A dùng request URI thuộc Client B | Từ chối; không tiết lộ dữ liệu request của B |
| Request bị sửa tham số ở authorization endpoint | Server tiếp tục dùng dữ liệu đã push hoặc từ chối theo quy tắc PAR |
| Gửi quá nhiều PAR request | Rate limit hoặc policy bảo vệ được thực thi |

Kiểm tra hành vi sử dụng lại request URI theo chính sách và đặc tả mà implementation áp dụng. Nếu hệ thống yêu cầu request URI chỉ dùng một lần, phải có ca replay test và xác minh lần sử dụng thứ hai bị từ chối. Dù policy cho phép tái sử dụng trong một khoảng thời gian, request URI vẫn phải khó đoán, có thời hạn và được ràng buộc với client.

### 4.6. Kiểm thử thời hạn và dữ liệu được lưu

Không nên dùng `Thread.sleep` dài trong functional test để đợi PAR hết hạn. Có thể cấu hình TTL ngắn trong profile test, dùng Clock có thể điều khiển nếu implementation hỗ trợ, hoặc kiểm tra qua integration test với thời gian giả lập.

Kiểm tra:

- `expires_in` khớp TTL mà server công bố.
- Request hết hạn không thể tiếp tục authorization.
- Request URI của client này không thể dùng bởi client khác.
- Restart server không làm mất request nếu kiến trúc yêu cầu PAR state bền vững; nếu state chỉ lưu tạm thời, hành vi sau restart phải được quy định rõ.
- Các replica cùng truy cập PAR state nếu load balancer có thể chuyển request sang instance khác.

## 5. Kiểm thử client authentication

Client authentication xác minh ứng dụng đang gọi endpoint. Nó khác với xác thực End-User: client authentication không chứng minh người dùng đã đăng nhập.

### 5.1. Ma trận phương thức phổ biến

| Phương thức | Credential được gửi | Kiểm tra trọng tâm |
|---|---|---|
| `client_secret_basic` | Client ID và secret trong HTTP Basic Authorization | Secret đúng, encoding đúng, không nhận credential trùng lặp mâu thuẫn |
| `client_secret_post` | Client ID và secret trong form body | Chỉ bật khi cần; từ chối secret sai và body credential không hợp lệ |
| `client_secret_jwt` | JWT client assertion ký bằng shared secret | Chữ ký, thuật toán, iss/sub, aud, exp và jti |
| `private_key_jwt` | JWT client assertion ký bằng private key của client | Chữ ký với public key/JWKS đã đăng ký, iss/sub, aud, exp và jti |
| `tls_client_auth` | Client certificate được CA tin cậy cấp | Chain, validity, subject/SAN mapping và client registration |
| `self_signed_tls_client_auth` | Self-signed certificate đã đăng ký/trusted | Certificate fingerprint/key binding và mapping client |
| `none` | Không có client secret; public client định danh bằng client_id | Chỉ cho phép endpoint/flow phù hợp, bắt buộc PKCE cho authorization code |

Chỉ bật các phương thức server thực sự hỗ trợ và có quy trình quản lý credential tương ứng. Không chấp nhận một phương thức chỉ vì client tự khai báo nó trong registration metadata.

### 5.2. Kiểm thử client_secret_basic

Request minh họa đến token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=api.read
~~~

Ví dụ kiểm thử:

~~~java
@Test
void shouldAuthenticateConfidentialClientWithBasic() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("service-client", "test-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "api.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

Đảm bảo client test đã được đăng ký với:

- `ClientAuthenticationMethod.CLIENT_SECRET_BASIC`.
- `AuthorizationGrantType.CLIENT_CREDENTIALS`.
- Scope `api.read` được cho phép.
- Secret được mã hóa bằng PasswordEncoder phù hợp.

Các ca âm gồm secret sai, client ID không tồn tại, client bị disabled, grant type không được phép và credential gửi sai định dạng. Với lỗi xác thực client, kiểm tra response có `invalid_client` và không tiết lộ client ID nào tồn tại.

### 5.3. Kiểm thử client_secret_post

Với phương thức này, client gửi thông tin xác thực trong form body:

~~~bash
curl -i -X POST https://auth.example.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=legacy-client" \
  -d "client_secret=$CLIENT_SECRET"
~~~

Chỉ chấp nhận body credential nếu client đã đăng ký `client_secret_post`. Kiểm thử thêm trường hợp client đăng ký `client_secret_basic` nhưng lại gửi secret trong body; server phải xử lý theo cấu hình auth method, không tự động hạ chuẩn hoặc thử tất cả phương thức.

### 5.4. Kiểm thử private_key_jwt

Với `private_key_jwt`, client tạo JWT assertion và ký bằng private key. Authorization Server dùng public key đã đăng ký để xác minh.

Các claim thường cần kiểm tra:

- `iss` và `sub` xác định client theo yêu cầu của client authentication.
- `aud` khớp audience mà Authorization Server chấp nhận cho endpoint đang gọi.
- `exp` nằm trong khoảng thời gian cho phép.
- `jti` duy nhất để hỗ trợ phát hiện replay.
- Header `alg` thuộc nhóm thuật toán được server cho phép; `kid` trỏ đúng khóa công khai đã đăng ký.

Request minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=jwt-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=<SIGNED-CLIENT-ASSERTION>
~~~

Test cần tạo assertion bằng private key test và public JWKS tương ứng đã đăng ký cho client. Không dùng private key của Authorization Server để ký assertion của client.

Ma trận negative test:

| Assertion | Kết quả mong đợi |
|---|---|
| Chữ ký hợp lệ, audience đúng, còn hạn | Client authentication thành công |
| Chữ ký sai hoặc public key không khớp | `invalid_client` |
| `iss` hoặc `sub` không khớp client | `invalid_client` |
| Audience không được server chấp nhận | `invalid_client` |
| Assertion hết hạn | `invalid_client` |
| `jti` bị replay trong thời gian chống replay | Từ chối assertion trùng |
| Thuật toán không nằm trong allowlist | Từ chối assertion |
| `kid` không tìm thấy | Từ chối assertion |

### 5.5. Kiểm thử client_secret_jwt

Phương thức này dùng shared secret của client để ký JWT assertion. Test cần xác minh thuật toán MAC được cho phép, chữ ký hợp lệ và các claim assertion hợp lệ.

Không chấp nhận `alg=none`. Không dùng thuật toán đối xứng ngoài allowlist hoặc secret có entropy thấp. Nếu server không bật `client_secret_jwt`, request phải bị từ chối thay vì tự chuyển sang `client_secret_basic`.

### 5.6. Kiểm thử mTLS client authentication

mTLS cần một kết nối TLS thực sự để server nhận client certificate. MockMvc thuần túy không mô phỏng đầy đủ quá trình TLS handshake và certificate mapping ở connector/proxy.

Với test mTLS, dùng embedded server hoặc môi trường integration có HTTPS, test keystore/truststore riêng và cấu hình certificate forwarding đáng tin cậy nếu TLS kết thúc ở proxy.

Các ca cần kiểm tra:

- Certificate được CA tin cậy cấp và khớp client registration.
- Certificate hết hạn hoặc chưa có hiệu lực.
- Certificate không nằm trong trust chain.
- Subject DN hoặc SAN không khớp metadata client.
- Certificate của client A được dùng với client ID của client B.
- Certificate bị thu hồi nếu hệ thống có kiểm tra CRL/OCSP.
- Proxy không cho phép client giả mạo header chứa certificate.

Nếu TLS terminate ở ingress, chỉ tin forwarded certificate header khi proxy xóa header do client tự gửi và tự ghi header sau khi xác minh certificate. Không nhận trực tiếp header certificate từ internet.

### 5.7. Kiểm thử public client

Public client dùng `token_endpoint_auth_method=none` không có client secret. Với Authorization Code Flow, cần kiểm tra:

- Client ID hợp lệ.
- Redirect URI khớp registration.
- PKCE được yêu cầu theo policy.
- Token request có `code_verifier` khớp challenge.
- Client không thể dùng client secret giả để được nâng thành confidential client.
- Public client không được dùng grant type hoặc scope vượt quá policy.

Không dùng client credentials grant cho public client để thay thế xác thực người dùng.

## 6. Kiểm thử sự nhất quán giữa registration, PAR và token endpoint

Các tính năng phải phối hợp đúng. Một client đăng ký thành công nhưng không thể dùng phương thức auth đã đăng ký vẫn là lỗi chức năng.

Một luồng tích hợp nên:

1. Đăng ký confidential client với redirect URI, authorization code grant, scope và `private_key_jwt` hoặc `client_secret_basic`.
2. Đọc lại client qua `RegisteredClientRepository` để xác minh metadata đã được lưu.
3. Gửi PAR với đúng phương thức client authentication.
4. Nhận `request_uri` và chuyển trình duyệt đến authorization endpoint.
5. Hoàn tất xác thực người dùng và consent.
6. Đổi authorization code tại token endpoint bằng đúng client authentication và PKCE verifier nếu áp dụng.
7. Xác minh token response và các scope đã cấp.
8. Thử lại với credential sai hoặc client khác để bảo đảm server từ chối đúng.

Luồng public client cần dùng test riêng: registration với `none`, PAR theo chính sách public client, authorization code với PKCE và token request không gửi secret.

## 7. Bộ test chức năng gợi ý

### 7.1. Registration test matrix

| ID | Kịch bản | Kết quả |
|---|---|---|
| REG-01 | Đăng ký web client hợp lệ | Tạo client, trả client ID |
| REG-02 | Đăng ký native public client | Tạo client không có secret, áp dụng PKCE |
| REG-03 | Redirect URI sai | Registration bị từ chối |
| REG-04 | Grant/response type không được phép | Registration bị từ chối |
| REG-05 | Auth method không hỗ trợ | Registration bị từ chối |
| REG-06 | Registration thiếu quyền/initial access token | Bị từ chối nếu endpoint được bảo vệ |
| REG-07 | Đọc lại client từ repository | Metadata được lưu đúng |
| REG-08 | Secret của confidential client | Secret response dùng được; repository giữ giá trị đã mã hóa |
| REG-09 | Registration request JSON quá lớn/sai cấu trúc | Bị từ chối an toàn |

### 7.2. PAR test matrix

| ID | Kịch bản | Kết quả |
|---|---|---|
| PAR-01 | PAR hợp lệ với client authentication đúng | Trả request URI và expires_in |
| PAR-02 | Client authentication sai | Bị từ chối |
| PAR-03 | Redirect URI chưa đăng ký | Bị từ chối |
| PAR-04 | Request thiếu response_type hoặc client_id | Bị từ chối |
| PAR-05 | Authorization endpoint dùng request_uri hợp lệ | Tiếp tục authorization flow |
| PAR-06 | Request URI không tồn tại | invalid_request_uri |
| PAR-07 | Request URI hết hạn | invalid_request_uri |
| PAR-08 | Client khác dùng request_uri | Bị từ chối |
| PAR-09 | Thay đổi parameter front-channel | Không làm thay đổi request đã push |
| PAR-10 | Replay request_uri | Hành vi đúng với replay policy đã chọn |

### 7.3. Client authentication test matrix

| ID | Kịch bản | Kết quả |
|---|---|---|
| AUTH-01 | Basic credential hợp lệ | Xác thực thành công |
| AUTH-02 | Basic secret sai | invalid_client |
| AUTH-03 | Secret post hợp lệ với client đã đăng ký method đó | Xác thực thành công |
| AUTH-04 | Dùng sai auth method | invalid_client |
| AUTH-05 | Private key JWT hợp lệ | Xác thực thành công |
| AUTH-06 | JWT assertion sai chữ ký/audience/expiry | invalid_client |
| AUTH-07 | Assertion jti bị replay | Bị từ chối theo replay protection |
| AUTH-08 | mTLS certificate đúng | Xác thực thành công |
| AUTH-09 | mTLS certificate sai/hết hạn | TLS hoặc client authentication thất bại |
| AUTH-10 | Public client với PKCE hợp lệ | Authorization code exchange thành công |

## 8. Quan sát lỗi và bảo vệ dữ liệu test

Trong quá trình test, log cần đủ thông tin để chẩn đoán nhưng không chứa credential.

Có thể ghi:

- Test case ID và correlation ID.
- Endpoint và HTTP status.
- Client ID giả lập trong môi trường test.
- Tên authentication method.
- Loại OAuth error, ví dụ `invalid_client`, `invalid_request` hoặc `invalid_request_uri`.
- Thời gian xử lý và replica xử lý request.

Không ghi:

- Client secret bản rõ.
- Access token, refresh token hoặc registration access token.
- Toàn bộ client assertion JWT.
- Private key hoặc nội dung keystore.
- Cookie session, authorization code hoặc dữ liệu cá nhân.

Nếu cần debug JWT assertion, chỉ ghi các claim không nhạy cảm sau khi đã loại bỏ dữ liệu có thể tái sử dụng, chẳng hạn algorithm, key ID, thời điểm hết hạn và kết quả xác minh.

## 9. Lỗi thường gặp trong quá trình kiểm thử

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Registration endpoint trả 404 | OIDC registration endpoint chưa bật hoặc sai endpoint path | Kiểm tra configurer, metadata và AuthorizationServerSettings |
| Registration trả 401/403 | Thiếu initial access token hoặc policy bảo vệ registration | Dùng credential test đúng với policy |
| Registration trả client ID nhưng repository không có client | Repository test không phải repository được endpoint dùng hoặc transaction rollback | Inject đúng repository và kiểm tra transaction |
| Secret response không dùng được | PasswordEncoder không nhất quán hoặc secret bị xử lý sai | Kiểm tra encoder khi tạo và xác minh client |
| PAR trả 401 | Sai auth method, secret hoặc client không được phép dùng PAR | Kiểm tra registration metadata và request authentication |
| PAR trả invalid_request | Thiếu tham số, redirect URI sai hoặc PKCE không hợp lệ | Kiểm tra request parameters so với client registration |
| Authorization endpoint báo invalid_request_uri | Request URI sai, hết hạn hoặc không được lưu/chia sẻ giữa replica | Kiểm tra TTL, PAR storage và client binding |
| Basic auth test pass nhưng post auth test fail | Client chỉ đăng ký basic hoặc server không bật post | Đăng ký đúng method và kiểm tra allowlist |
| private_key_jwt thất bại | Assertion audience, chữ ký, kid hoặc thời hạn sai | So sánh assertion với policy và JWKS client |
| mTLS test pass ở MockMvc nhưng fail production | MockMvc không thực hiện TLS handshake thật | Chạy test HTTPS ở embedded server hoặc môi trường integration |
| PAR hoạt động trên một replica nhưng lỗi trên replica khác | PAR state chỉ nằm trong memory của từng instance | Dùng state store dùng chung hoặc sticky policy được xác định rõ |

## 10. Checklist trước khi phát hành

- [ ] Phiên bản Spring Authorization Server hỗ trợ các endpoint và auth method đang bật.
- [ ] Discovery/metadata công bố đúng registration endpoint và PAR endpoint nếu được hỗ trợ.
- [ ] Dynamic Client Registration được bảo vệ bằng policy rõ ràng.
- [ ] Redirect URI, grant type, response type, scope và auth method được validate.
- [ ] Confidential client secret được sinh an toàn và lưu đã mã hóa.
- [ ] Public client không nhận secret và phải dùng PKCE theo policy.
- [ ] PAR xác thực client theo metadata đã đăng ký.
- [ ] PAR trả request URI khó đoán và expires_in hợp lệ.
- [ ] Request URI được ràng buộc với client và hết hạn đúng thời gian.
- [ ] Authorization endpoint sử dụng các tham số đã push.
- [ ] Client authentication method tại token/PAR endpoint khớp registration.
- [ ] private_key_jwt kiểm tra chữ ký, iss, sub, aud, exp, jti và kid.
- [ ] mTLS được kiểm thử qua HTTPS thật, certificate mapping và proxy trust.
- [ ] Negative test xác minh credential sai, assertion replay, client mismatch và request URI hết hạn.
- [ ] Các replica chia sẻ client registration và PAR state theo yêu cầu kiến trúc.
- [ ] Log không ghi secret, token, assertion đầy đủ hoặc private key.
- [ ] Có test tích hợp từ registration qua PAR đến token endpoint.

Kiểm thử DCR xác nhận server chỉ tạo client với metadata được phép. Kiểm thử PAR xác nhận authorization request được tiếp nhận, ràng buộc với client và sử dụng trong thời hạn. Kiểm thử client authentication xác nhận mỗi endpoint chỉ chấp nhận đúng phương thức đã đăng ký. Khi kết hợp ba nhóm test trong một luồng tích hợp, có thể phát hiện sớm lỗi cấu hình, lỗi persistence và lỗ hổng phân quyền trước khi đưa Authorization Server vào vận hành.

