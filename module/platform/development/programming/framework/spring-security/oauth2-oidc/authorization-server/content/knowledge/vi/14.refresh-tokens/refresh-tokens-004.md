# Kiểm tra liên kết refresh token với client và authorization

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security** và **Spring Authorization Server** trên **Spring Boot**, refresh token là một credential có giá trị cao: nó cho phép client xin access token mới mà người dùng không cần thực hiện lại toàn bộ luồng Authorization Code và đăng nhập. Vì có thể được sử dụng trong thời gian dài hơn access token, refresh token phải được kiểm tra chặt chẽ trước khi phát hành quyền truy cập mới.

Giả sử Alice đăng nhập qua ứng dụng <code>orders-web</code> và cho phép scope <code>orders.read</code>. Authorization Server phát hành access token <code>AT-1</code> và refresh token <code>RT-1</code> cho **một authorization cụ thể của <code>orders-web</code>**. Kẻ tấn công lấy được <code>RT-1</code> rồi thử dùng một client khác là <code>billing-web</code> để đổi lấy access token. Nếu Authorization Server chỉ kiểm tra chuỗi refresh token còn tồn tại, nó có thể cấp nhầm quyền của Alice cho client sai. Việc ràng buộc refresh token với **client đã được cấp** và **authorization gốc** giúp ngăn kịch bản này.

Sau bài học, bạn sẽ có thể:

1. Phân biệt <code>client_id</code> theo giao thức với <code>RegisteredClient.getId()</code> dùng trong kho dữ liệu.
2. Hiểu dữ liệu liên kết refresh token, client, principal, authorization, scopes và resource trong <code>OAuth2Authorization</code>.
3. Mô tả cách <code>OAuth2RefreshTokenAuthenticationProvider</code> tra authorization, xác minh client, token còn hiệu lực và scope trước khi cấp token mới.
4. Cấu hình đăng ký client, thời hạn và xoay refresh token bằng Spring Authorization Server.
5. Thiết kế thêm kiểm soát trạng thái người dùng, revocation, replay detection, lưu trữ bền vững và transaction trong hệ thống nhiều instance.
6. Viết kiểm thử cho refresh hợp lệ, sai client, sai authorization, token hết hạn, token bị thu hồi, scope leo thang và các lỗi đồng thời.

**Ví dụ xuyên suốt:** Authorization Server tại <code>https://auth.example.com</code> có hai confidential client <code>orders-web</code> và <code>billing-web</code>. Alice cấp cho <code>orders-web</code> quyền <code>orders.read</code>. Các minh họa Java theo nhóm API Spring Authorization Server 1.x; ở các phiên bản Spring Security tích hợp Authorization Server mới hơn, vị trí package/configurer có thể thay đổi. Bài tập trung vào **kiểm tra liên kết**, không thay thế toàn bộ hướng dẫn triển khai hệ thống.

## 2. Refresh token gắn với những gì?

Theo [RFC 6749, §6](https://www.rfc-editor.org/rfc/rfc6749#section-6), khi một confidential client sử dụng refresh token, Authorization Server phải xác thực client, xác minh refresh token **đã được cấp cho chính client đó**, và kiểm tra refresh token hợp lệ. [RFC 9700, §4.14](https://www.rfc-editor.org/rfc/rfc9700#section-4.14) bổ sung yêu cầu bảo vệ, trong đó refresh token phải bị giới hạn theo scope và resource servers mà resource owner đã chấp thuận.

Một thiết kế an toàn nhìn vào nhiều liên kết cùng lúc:

~~~mermaid
flowchart LR
    C["RegisteredClient<br/>record ID = client-record-A<br/>client_id = orders-web"]
    A["OAuth2Authorization<br/>id = auth-1001<br/>registeredClientId = client-record-A<br/>principalName = user-42<br/>authorizedScopes = orders.read"]
    RT["Refresh Token<br/>RT-1<br/>trạng thái active"]
    AT["Access Token<br/>AT-1 / AT-2"]
    API["Orders API<br/>resource/audience được phép"]
    C -->|"được tham chiếu bởi ID nội bộ"| A
    A -->|"lưu token và metadata"| RT
    A -->|"phát hành/cập nhật"| AT
    AT --> API
~~~

| Liên kết | Điều cần xác minh | Nếu bỏ qua |
| --- | --- | --- |
| **Refresh token → Authorization** | Tra đúng bản ghi chứa **chính refresh token đã gửi**, theo đúng loại token. | Chuỗi không thuộc authorization vẫn có thể được dùng nếu repository tra cứu sai. |
| **Authorization → RegisteredClient** | <code>authorization.getRegisteredClientId()</code> trùng <code>registeredClient.getId()</code> của client đang được xác thực. | Client B có thể đổi refresh token của client A. |
| **Refresh token → trạng thái** | Token tồn tại, chưa hết hạn, chưa bị invalidated/revoked. | Token cũ hoặc đã thu hồi vẫn cấp được token mới. |
| **Client → quyền sử dụng refresh grant** | Client vẫn được đăng ký <code>AuthorizationGrantType.REFRESH_TOKEN</code>. | Một client đã mất quyền dùng refresh grant vẫn tiếp tục refresh. |
| **Authorization → scopes và resources** | Token mới không vượt phạm vi đã được cấp và các resource được phép. | Client xin thêm scope hoặc đổi resource bằng token cũ. |
| **Authorization → principal/chính sách hiện tại** | Nếu sản phẩm yêu cầu, người dùng/tenant/phiên còn được phép duy trì grant. | Tài khoản disabled nhưng refresh token vẫn tiếp tục phát access token. |
| **Token → sender/thiết bị (khi có)** | Ràng buộc theo DPoP, mTLS hoặc cơ chế đã đăng ký và triển khai. | Refresh token bị đánh cắp có thể bị sử dụng lại từ môi trường khác. |

Vì vậy, **refresh token không phải mật khẩu đăng nhập của Alice** và cũng không thể được coi là một “vé” có thể chuyển tùy ý giữa các client. Đây là credential được Authorization Server cấp trong ngữ cảnh cụ thể, phải được bảo quản và kiểm tra tại token endpoint.

## 3. Mô hình dữ liệu Spring Authorization Server

### 3.1. <code>RegisteredClient</code> có hai định danh cần phân biệt

Ví dụ đăng ký:

~~~text
RegisteredClient.id       = "client-record-A"
RegisteredClient.clientId = "orders-web"

RegisteredClient.id       = "client-record-B"
RegisteredClient.clientId = "billing-web"
~~~

<code>clientId</code> là định danh client trong request OAuth 2.0, ví dụ giá trị được dùng khi gửi HTTP Basic. <code>id</code> là khóa **bản ghi registered client ở phía Authorization Server**. Trong <code>OAuth2Authorization</code>, trường <code>registeredClientId</code> lưu **<code>RegisteredClient.getId()</code>**, không mặc định là <code>getClientId()</code>.

Một số dự án đặt hai giá trị bằng nhau cho tiện demo, nhưng điều đó không làm chúng có cùng vai trò. Khi migration database hoặc tạo lại client, nếu <code>RegisteredClient.id</code> bị thay đổi, các authorization cũ có thể trỏ đến ID không còn hợp lệ. Cần giữ ID ổn định và xử lý migration/revocation theo chính sách.

### 3.2. <code>OAuth2Authorization</code> là bản ghi liên kết token với grant

Spring Authorization Server dùng <code>OAuth2Authorization</code> để lưu trạng thái authorization:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| <code>id</code> | ID authorization, tách biệt khỏi token value. | <code>auth-1001</code> |
| <code>registeredClientId</code> | ID nội bộ của client được cấp quyền. | <code>client-record-A</code> |
| <code>principalName</code> | Chủ thể của authorization, thường là End-User trong Authorization Code Flow. | <code>user-42</code> |
| <code>authorizationGrantType</code> | Grant **đã tạo authorization ban đầu**. | <code>authorization_code</code> |
| <code>authorizedScopes</code> | Scope đã được chấp thuận/cấp theo authorization. | <code>orders.read</code> |
| <code>attributes</code> | Ngữ cảnh ủy quyền được lưu, có thể chứa authentication hoặc dữ liệu phục vụ token generation. | Principal/authorization request liên quan |
| <code>tokens</code> | Các token và metadata có liên quan đến authorization. | Access token, refresh token, ID Token nếu OIDC |

Trong Authorization Code Flow, authorization gốc thường lưu authorization code, access token và có thể có refresh token; trong OIDC có thể có ID Token. Theo mô hình mặc định Spring Authorization Server, Client Credentials thường chỉ có access token, **không tự giả định mọi grant đều có refresh token**.

Điểm cần nhớ: trong một lần gọi <code>grant_type=refresh_token</code>, <code>authorization.getAuthorizationGrantType()</code> có thể vẫn là <code>authorization_code</code>, vì đây là loại grant **khởi tạo bản ghi authorization**. Đừng viết kiểm tra sai kiểu “authorizationGrantType phải là refresh_token” rồi từ chối mọi refresh hợp lệ.

### 3.3. Token metadata và <code>isActive()</code>

<code>OAuth2Authorization</code> có thể chứa:

~~~java
OAuth2Authorization.Token<OAuth2RefreshToken> stored =
    authorization.getRefreshToken();

if (stored == null || !stored.isActive()) {
    // Không được cấp token mới từ refresh token thiếu/hết hạn/invalidated.
}
~~~

<code>isActive()</code> phản ánh token chưa hết hạn và chưa bị invalidated theo mô hình Spring Authorization Server. Nó **không đồng nghĩa** tài khoản người dùng còn active, client chưa bị khóa bởi một policy ngoài framework hoặc token chưa bị phát hiện lộ ở một hệ thống giám sát khác. Những điều kiện nghiệp vụ đó cần tích hợp riêng.

Một bản ghi authorization cũng có thể chứa access token đã hết hạn nhưng refresh token còn active. Đây là tình huống bình thường của refresh grant.

## 4. Yêu cầu HTTP và chuỗi kiểm tra ở Token Endpoint

Một confidential client dùng refresh token thường gửi request đến token endpoint bằng HTTPS:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-of-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT-1&scope=orders.read
~~~

Đoạn mã trên dùng giá trị giả lập, không chứa credential thật. Trong thực tế chuỗi client ID/secret phải được mã hóa theo quy tắc HTTP Basic của OAuth 2.0 và các form value được URL-encode chính xác. Client **không được** gửi refresh token trong query URL, log hoặc analytics.

Các tham số:

| Tham số | Vai trò |
| --- | --- |
| <code>grant_type=refresh_token</code> | Nêu rõ yêu cầu đang dùng refresh grant. |
| <code>refresh_token</code> | Giá trị token đã được cấp trước đó. |
| <code>scope</code> (tùy chọn) | Phạm vi được yêu cầu cho access token mới; không được vượt quá scope đã cấp trước đó. |
| Client authentication | Chứng minh confidential client là client đã đăng ký, ví dụ <code>client_secret_basic</code> hoặc <code>private_key_jwt</code>. |

Theo RFC 6749, nếu bỏ <code>scope</code>, yêu cầu được hiểu là dùng scope đã được cấp ban đầu. Nếu gửi scope mới, server phải kiểm tra không có quyền vượt quá scope cũ. Ngoài ra, RFC 9700 yêu cầu ràng buộc refresh token với **resources** đã được resource owner chấp thuận, ngay cả khi client thử thay resource indicator ở request refresh.

### 4.1. Từ HTTP request đến provider

~~~mermaid
sequenceDiagram
    autonumber
    participant C as orders-web
    participant F as OAuth2ClientAuthenticationFilter
    participant T as OAuth2TokenEndpointFilter
    participant P as OAuth2RefreshTokenAuthenticationProvider
    participant S as OAuth2AuthorizationService
    participant G as OAuth2TokenGenerator
    C->>F: POST /oauth2/token + client credentials + RT-1
    F->>F: Xác thực client theo RegisteredClient
    F->>T: Tiếp tục request khi client hợp lệ
    T->>P: OAuth2RefreshTokenAuthenticationToken
    P->>S: findByToken(RT-1, REFRESH_TOKEN)
    S-->>P: OAuth2Authorization auth-1001
    P->>P: So RegisteredClient.id với authorization.registeredClientId
    P->>P: Kiểm tra client được dùng refresh grant
    P->>P: Kiểm tra refresh token active và scopes hợp lệ
    P->>G: Sinh access token mới (+ refresh token theo settings)
    P->>S: Lưu OAuth2Authorization cập nhật
    P-->>T: OAuth2AccessTokenAuthenticationToken
    T-->>C: JSON token response hoặc lỗi OAuth
~~~

Sơ đồ mô tả **những bước logic chính**, không cố định thứ tự tất cả filter/context trong mọi phiên bản. Trong Spring Authorization Server, <code>OAuth2TokenEndpointFilter</code> sử dụng <code>OAuth2RefreshTokenAuthenticationConverter</code> và <code>OAuth2RefreshTokenAuthenticationProvider</code> trong cấu hình mặc định của token endpoint. Việc xác thực client diễn ra theo cơ chế client authentication riêng của Authorization Server.

### 4.2. Cách provider ràng buộc refresh token vào client

Điểm then chốt của quy trình mặc định có thể mô tả bằng pseudocode bám sát API của Spring:

~~~java
// Minh họa logic cốt lõi, KHÔNG thay thế provider thật.
OAuth2ClientAuthenticationToken authenticatedClient =
    getAuthenticatedClientFromSecurityContext();
RegisteredClient client = authenticatedClient.getRegisteredClient();

OAuth2Authorization authorization = authorizationService.findByToken(
    presentedRefreshToken, OAuth2TokenType.REFRESH_TOKEN);

if (authorization == null) {
    reject("invalid_grant");
}

if (!client.getId().equals(authorization.getRegisteredClientId())) {
    reject("client/token binding mismatch");
}

if (!client.getAuthorizationGrantTypes()
        .contains(AuthorizationGrantType.REFRESH_TOKEN)) {
    reject("unauthorized_client");
}

OAuth2Authorization.Token<OAuth2RefreshToken> refresh =
    authorization.getRefreshToken();
if (refresh == null || !refresh.isActive()) {
    reject("invalid_grant");
}

Set<String> granted = authorization.getAuthorizedScopes();
Set<String> requested = requestedRefreshScopes.isEmpty()
    ? granted : requestedRefreshScopes;

if (!granted.containsAll(requested)) {
    reject("invalid_scope");
}

// Tiếp tục áp dụng các policy bổ sung và phát hành token mới.
~~~

Các hàm <code>getAuthenticatedClientFromSecurityContext()</code> và <code>reject(...)</code> là **pseudocode giải thích**, không phải phương thức Java có sẵn để copy vào controller. Spring Authorization Server có logic nội bộ tương đương trong <code>OAuth2RefreshTokenAuthenticationProvider</code>. Cách ánh xạ lỗi mismatch có thể khác theo phiên bản; logic nghiệp vụ cần bảo đảm request bị từ chối, không phụ thuộc duy nhất vào tên lỗi trả về.

**Không viết riêng một endpoint <code>/refresh</code> nhận chuỗi token và gọi <code>findByToken()</code> rồi phát JWT** nếu không tái tạo đầy đủ kiểm tra client, grant, scopes, resource, trạng thái và replay. Hãy tái sử dụng token endpoint cùng provider của framework, sau đó chỉ bổ sung policy cần thiết qua điểm mở rộng phù hợp.

## 5. Tại sao phải so ID nội bộ, không so client ID giao thức?

Giả sử:

~~~text
Client A:
  RegisteredClient.id       = "db-client-A"
  RegisteredClient.clientId = "orders-web"

Client B:
  RegisteredClient.id       = "db-client-B"
  RegisteredClient.clientId = "billing-web"

Authorization auth-1001:
  registeredClientId = "db-client-A"
  principalName      = "user-42"
  refreshToken        = "RT-1"
~~~

Khi <code>billing-web</code> xác thực thành công bằng secret riêng và gửi <code>RT-1</code>, repository có thể tìm thấy <code>auth-1001</code> (vì token tồn tại), nhưng **client hiện tại không phải client được cấp RT-1**:

~~~java
boolean sameClient = registeredClient.getId()
    .equals(authorization.getRegisteredClientId());

// "db-client-B".equals("db-client-A") => false
~~~

Authorization Server phải từ chối. Việc <code>billing-web</code> có cùng issuer, chung người dùng Alice hoặc có scope <code>orders.read</code> trong danh sách đăng ký **không hợp thức hóa refresh token của client khác**.

### 5.1. Khi nào sai liên kết dù <code>client_id</code> nhìn như giống nhau?

Một số trường hợp đặc biệt:

- **Migration sai ID:** Client <code>orders-web</code> được tạo lại với <code>RegisteredClient.id</code> mới. Authorization cũ vẫn tham chiếu ID cũ; không nên tự động sửa client binding dựa trên chuỗi client ID hiển thị.
- **Multi-tenancy:** Hai tenant có client ID cùng tên nhưng cần phân vùng đăng ký riêng. Nếu dùng chung repository/issuer, khóa nội bộ và quyền truy cập phải được phân biệt chặt chẽ.
- **Khôi phục database:** Sao lưu authorization nhưng bỏ sót registered clients hoặc dùng bản sao khác môi trường có ID trùng không tương ứng; phải kiểm tra nhất quán khi restore.
- **Token store tùy biến:** Repository trả về authorization theo token value nhưng quên kiểm tra loại token hoặc trả record sai. Provider có thể tin kết quả lookup của service; đây là lỗi nghiêm trọng của tầng dữ liệu.

**Không “sửa” lỗi mismatch bằng cách bỏ phép so <code>getRegisteredClientId()</code>.** Cần khôi phục ánh xạ đúng bằng migration có kiểm soát hoặc vô hiệu hóa authorization cũ và yêu cầu người dùng cấp lại quyền.

### 5.2. Client authentication không thay thế token binding

Một confidential client xác thực thành công chỉ chứng minh nó là **một client hợp lệ**, không chứng minh refresh token được cấp cho nó. Hai điều kiện phải đồng thời đúng:

~~~text
authenticatedClient == client được đăng ký
AND
authorization.registeredClientId == authenticatedClient.registeredClient.id
AND
authorization chứa đúng refresh token còn active
~~~

Đối với public client, chỉ khai báo <code>client_id</code> không phải bằng chứng bảo vệ bí mật. RFC 9700 yêu cầu refresh token của public client phải **sender-constrained hoặc rotation** có phát hiện replay. Cần kiểm tra phiên bản Spring Authorization Server đang dùng có phát hành refresh token cho public client trong điều kiện nào; không tự coi một đăng ký public client có <code>refresh_token</code> grant là bằng chứng đã đáp ứng chuẩn.

## 6. Kiểm tra chính authorization, trạng thái và scope

### 6.1. Tra chính token được trình và loại token đúng

API chuẩn của Spring:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        tokenValue, OAuth2TokenType.REFRESH_TOKEN);
~~~

<code>OAuth2AuthorizationService.findByToken(String, OAuth2TokenType)</code> phải tra chính xác token được gửi trong nhóm **refresh token**, không nhầm với access token, authorization code hoặc ID Token.

Trong một implementation JDBC/JPA tùy biến, nên xác nhận:

1. Truy vấn có tham số token type và token value đúng.
2. Không trả authorization nếu token value không khớp chính xác với refresh token của bản ghi.
3. Không chỉ tìm theo <code>principalName</code>, <code>client_id</code> hoặc ID authorization tự lấy từ client.
4. Không trả về một record authorization bị hỏng hoặc có token metadata không đồng nhất.
5. Quyền đọc/ghi token store được hạn chế; tránh log raw token, mật khẩu/secret hoặc bearer credentials.

Nếu dùng token opaque, **độ ngẫu nhiên/khó đoán** phải đủ cao và kho lưu trữ phải bảo vệ giá trị token. Nếu dùng định dạng token khác, cần kiểm tra toàn vẹn cryptographic và liên kết tới authorization trước khi tin nội dung token tự khai.

### 6.2. Token phải còn hiệu lực

~~~java
OAuth2Authorization.Token<OAuth2RefreshToken> tokenState =
    authorization.getRefreshToken();

boolean valid = tokenState != null
    && tokenState.isActive()
    && tokenValue.equals(tokenState.getToken().getTokenValue());
~~~

Việc so <code>tokenValue</code> trong đoạn ví dụ giúp làm rõ bất biến về **đúng token** nếu bạn tự xây validation/storage. Khi dùng provider chuẩn, dự án cần bảo đảm service <code>findByToken()</code> có ngữ nghĩa đúng; không nên tạo lại logic provider trong controller.

Token không còn hợp lệ nếu hết hạn hoặc bị invalidated. Một refresh token được thay thế do rotation cũng không được tiếp tục cấp token mới. Những trạng thái khác, như tài khoản bị khóa hoặc policy tenant bị thu hồi, có thể đòi hỏi kiểm soát bổ sung ngoài <code>isActive()</code>.

### 6.3. Phạm vi mới không vượt scope cũ

Nếu authorization lưu:

~~~text
authorizedScopes = {"orders.read", "orders.write"}
~~~

thì refresh request với <code>scope=orders.read</code> là yêu cầu giảm quyền; request với <code>scope=orders.read billing.admin</code> phải bị từ chối vì có scope chưa từng được cấp. Bỏ scope trong request thường yêu cầu dùng scope đã được cấp ban đầu theo RFC 6749.

Đối với chính sách thu hồi quyền động, kiểm tra tập scope cũ vẫn chưa đủ. Ví dụ admin đã gỡ quyền <code>orders.write</code> khỏi Alice hoặc <code>orders-web</code>; nếu yêu cầu không cấp quyền đó nữa, phải tích hợp policy và giới hạn token mới theo **quyền hiện tại**, đồng thời xử lý authorization/refresh token cũ theo thiết kế.

### 6.4. Giới hạn resource và audience

RFC 9700 yêu cầu refresh token bị ràng buộc với scope **và resource servers** đã được chủ tài nguyên cho phép. Nếu authorization ban đầu chỉ dành cho Orders API, client không được dùng cùng refresh token để xin token cho Billing API chỉ bằng cách thay tham số <code>resource</code> (RFC 8707) hoặc audience.

Tại Spring Authorization Server, có thể cần lưu/đối chiếu **resource indicator** trong authorization và thực thi chính sách phát hành audience của access token. Không giả định framework tự hỗ trợ toàn bộ RFC 8707 chỉ vì client gửi tham số <code>resource</code>, và không sao chép nguyên URI do client gửi vào <code>aud</code> mà chưa xác thực.

## 7. Cấu hình client và refresh token trong Spring Authorization Server

### 7.1. Đăng ký client có quyền dùng refresh grant

Ví dụ một **confidential web client**:

~~~java
RegisteredClient ordersWeb = RegisteredClient
    .withId("client-record-A")
    .clientId("orders-web")
    .clientSecret(encodedClientSecret) // Hash an toàn từ secret manager.
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://orders.example.com/login/oauth2/code/orders-web")
    .scope("openid")
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .requireProofKey(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build())
    .build();
~~~

<code>encodedClientSecret</code> là secret **đã mã hóa bằng PasswordEncoder phù hợp** và được ứng dụng cung cấp từ nguồn an toàn; không đưa mật khẩu/secret thật vào tài liệu hay Git. Đây là mẫu cấu hình cho **server-side confidential client**, không dùng client secret trong SPA/mobile.

Điều kiện liên quan:

- <code>AuthorizationGrantType.REFRESH_TOKEN</code> phải xuất hiện trong đăng ký nếu muốn dùng refresh grant.
- <code>TokenSettings.refreshTokenTimeToLive(...)</code> quy định TTL của refresh token do server phát hành.
- <code>TokenSettings.reuseRefreshTokens(false)</code> yêu cầu tạo refresh token mới khi refresh thành công, thay vì tiếp tục dùng cùng giá trị.
- <code>ClientSettings.requireProofKey(true)</code> áp dụng PKCE ở authorization flow; nó không tự ràng buộc refresh token với một instance của client.
- <code>requireAuthorizationConsent(true)</code> điều khiển bước consent tương ứng; **consent đã lưu và refresh token đang tồn tại có vòng đời khác nhau**.

Các giá trị 10 phút, 7 ngày chỉ để minh họa; phải chọn TTL theo rủi ro, loại client, chính sách đăng nhập, token storage và thời gian thu hồi yêu cầu.

### 7.2. Bean giữ trạng thái authorization

Với môi trường thử nghiệm:

~~~java
@Bean
OAuth2AuthorizationService authorizationService() {
    return new InMemoryOAuth2AuthorizationService();
}
~~~

Với một ứng dụng JDBC có schema tương ứng, có thể chuyển sang:

~~~java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbc,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(jdbc, registeredClients);
}
~~~

**Chú ý:** Đây là các lựa chọn thay thế, **không khai báo hai bean cùng loại trong một ứng dụng** rồi mong token endpoint tự phân biệt. JDBC cần bảng <code>oauth2_authorization</code> và schema đúng phiên bản thư viện, migration, connection pool và quyền truy cập DB. <code>JdbcOAuth2AuthorizationService</code> lưu cả ngữ cảnh authorization và metadata của nhiều loại token; không được thiết kế như một bảng chỉ lưu refresh token value.

Để vận hành nhiều instance Authorization Server, toàn bộ node phải dùng chung kho authorization hợp lệ, cấu hình client registration/issuer/khóa nhất quán và chính sách transaction phù hợp.

### 7.3. SecurityFilterChain dành cho token endpoint

Token refresh nên tiếp tục đi qua chain mặc định của Authorization Server:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer as =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(as.getEndpointsMatcher())
        .with(as, Customizer.withDefaults())
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là **khung cấu hình**; ứng dụng cần RegisteredClientRepository, OAuth2AuthorizationService, token generator, JWK/decoder nếu có OIDC và các bean liên quan. <code>getEndpointsMatcher()</code> giúp chain AS nhận đúng endpoint giao thức. <code>oauth2/token</code> được xử lý bởi token endpoint filter, nơi các provider kiểm tra client và refresh token.

Không sửa lỗi refresh bằng <code>requestMatchers("/oauth2/token").permitAll()</code> hoặc tự miễn client authentication. <code>permitAll()</code> là quy tắc phân quyền HTTP; nó không thay thế các kiểm tra OAuth của token endpoint.

### 7.4. Luồng OIDC khi refresh

Một authorization OIDC có thể chứa ID Token và nhiều token khác; refresh grant phục vụ việc cấp access token mới và tùy cấu hình có thể phát hành ID Token mới theo các quy tắc OIDC tương ứng. Tuy nhiên, **refresh không tự bắt người dùng đăng nhập lại**, không tự kiểm tra trạng thái tài khoản bị khóa, cũng không phải cách dùng một ID Token để xác thực client.

Nếu chính sách yêu cầu <code>max_age</code>, MFA, trạng thái phiên hoặc tái xác thực, cần thiết kế các điểm kiểm tra riêng phù hợp với chuẩn OIDC và ứng dụng.

## 8. Rotation, replay detection và authorization lineage

### 8.1. <code>reuseRefreshTokens(false)</code> làm gì?

~~~mermaid
sequenceDiagram
    autonumber
    participant C as orders-web
    participant AS as Authorization Server
    participant DB as Authorization Store
    C->>AS: Gửi RT-1
    AS->>DB: Tra RT-1 và kiểm tra client + authorization
    DB-->>AS: RT-1 active, thuộc client-record-A
    AS->>AS: Sinh AT-2 và RT-2
    AS->>DB: Lưu authorization với refresh token mới
    AS-->>C: Trả AT-2 + RT-2
    Note over C,DB: RT-1 phải không thể dùng để refresh thành công lần nữa
~~~

Khi <code>reuseRefreshTokens(false)</code>, framework tạo refresh token mới trong phản hồi refresh thành công. Client phải **thay thế token cũ bằng token mới** trong kho an toàn. Đây là **rotation** ở mức phát hành.

**Cần phân biệt rotation với replay detection hoàn chỉnh:** nếu chỉ thay giá trị refresh token hiện hành và xóa dấu vết token cũ, một request dùng lại <code>RT-1</code> có thể chỉ được báo <code>invalid_grant</code> mà server không biết token đó thuộc family nào để thu hồi <code>RT-2</code>. RFC 9700 yêu cầu cơ chế **giữ quan hệ token family và xử lý replay** cho public client khi chọn rotation thay vì sender-constrained token. Đừng coi việc đặt <code>reuseRefreshTokens(false)</code> là bằng chứng framework đã tự triển khai toàn bộ phát hiện token family bị đánh cắp trên nhiều node.

### 8.2. Thiết kế lineage và replay detection khi cần

Một kho refresh token family tùy biến có thể cần các trường:

| Trường | Vai trò |
| --- | --- |
| <code>family_id</code> | Nhóm refresh token bắt nguồn từ cùng một authorization/grant. |
| <code>authorization_id</code> | ID authorization gốc. |
| <code>registered_client_id</code> | Client sở hữu family. |
| <code>token_hash</code> | Dấu vết token một chiều để nhận diện mà không lưu raw token ở log/audit. |
| <code>generation</code>, <code>parent_token_id</code> | Quan hệ thứ tự giữa các token. |
| <code>status</code> | Active / rotated / revoked / replay_detected. |
| <code>issued_at</code>, <code>expires_at</code> | Giới hạn thời gian và dọn dữ liệu. |

Đây là **gợi ý dữ liệu riêng của ứng dụng**, không phải schema mặc định của Spring Authorization Server. Khi phát hiện một refresh token đã bị rotate được sử dụng lại, server cần đánh dấu family là compromised và thu hồi token hiện hành/theo policy. Cần phân biệt retry đồng thời vô hại do lỗi mạng với replay nghi ngờ, nhưng không được mở rộng “grace period” thiếu kiểm soát khiến kẻ tấn công dùng lại token thành công.

### 8.3. Race condition khi có hai refresh request đồng thời

Giả sử hai instance nhận cùng <code>RT-1</code> gần như cùng lúc:

~~~text
Node A: đọc RT-1 active
Node B: đọc RT-1 active
Node A: phát RT-2 và lưu
Node B: phát RT-3 và lưu
Client: có thể chỉ nhận RT-2 (trong khi DB giữ RT-3)
~~~

Nếu không có lock/optimistic version hoặc cơ chế **atomic compare-and-update**, cả hai request có thể vượt qua kiểm tra active trước khi token cũ bị thay thế. Hệ quả gồm phát hành song song, làm mất token hợp lệ và khó phát hiện replay. Với hệ thống nhiều instance, phải kiểm thử cùng database thật và thiết kế thao tác **đánh dấu token đã dùng + tạo token kế tiếp** có tính nguyên tử theo authorization/family. Không giải quyết bằng <code>synchronized</code> trong một JVM.

### 8.4. Sender-constrained refresh token

Theo RFC 9700, public clients có thể đáp ứng chống replay bằng **sender-constrained refresh token** thay cho rotation, ví dụ dùng DPoP (RFC 9449) hoặc mTLS (RFC 8705) khi phù hợp. Nếu triển khai, phải ràng buộc token với material khóa/cert của đúng client instance và xác minh proof trong mỗi refresh request. <code>client_id</code> khai trong form **không** tự là sender constraint.

Hỗ trợ và mức hoàn chỉnh của DPoP/mTLS refresh token phụ thuộc phiên bản framework, cấu hình và hạ tầng; không khẳng định cứ bật một thuộc tính là tự đạt yêu cầu RFC 9700.

## 9. Thu hồi authorization và thay đổi trạng thái user/client

### 9.1. Xóa consent không tương đương thu hồi refresh token

<code>OAuth2AuthorizationConsentService</code> lưu sự đồng ý của user cho một registered client; <code>OAuth2AuthorizationService</code> lưu authorization/token đã phát hành. Nếu người dùng bấm “Ngắt kết nối ứng dụng”, chỉ xóa bản ghi consent **không tự động** khiến refresh token trong authorization store mất hiệu lực. Cần quyết định sản phẩm có muốn chặn refresh ngay không; nếu có, phải thu hồi những authorization/token liên quan hoặc áp dụng kiểm tra trạng thái tập trung.

### 9.2. Người dùng bị khóa hoặc vô hiệu hóa sau khi phát hành refresh token

Refresh grant thường **không yêu cầu nhập lại mật khẩu của End-User**. Một account bị disabled trong database không chắc khiến <code>OAuth2RefreshTokenAuthenticationProvider</code> tự gọi lại <code>UserDetailsService</code>. Nếu chính sách đòi hỏi chặn token mới sau khi khóa account:

1. Xác định principal/tenant của authorization bằng dữ liệu đáng tin, không lấy từ request body.
2. Kiểm tra trạng thái account mới nhất ở điểm refresh/issue token thích hợp hoặc thu hồi toàn bộ authorization/refresh token liên quan.
3. Ngăn race giữa thao tác vô hiệu hóa và refresh bằng cơ chế nhất quán có thể kiểm thử.
4. Xử lý JWT access token đã phát hành theo chiến lược TTL/denylist/introspection; xóa refresh token không làm một JWT offline đã phát hành tự hết hạn.

**Lưu ý:** Việc tra mọi authorization của một user **không được định nghĩa bởi một phương thức <code>findAllByPrincipalName()</code> trong interface chuẩn <code>OAuth2AuthorizationService</code>**. Dự án cần thêm repository/query riêng hoặc quy trình revoke phù hợp, không quét tùy tiện toàn bộ token store trong token endpoint.

### 9.3. Client bị xóa hoặc thay đổi registration

Nếu <code>orders-web</code> bị vô hiệu hóa, gỡ refresh grant hoặc bị xóa khỏi repository, server phải không tiếp tục cấp token từ authorization cũ theo chính sách. Không tự tạo lại client với <code>RegisteredClient.id</code> khác rồi cho rằng token cũ vẫn thuộc nó. Việc rotation secret cho confidential client cũng cần bảo đảm các request refresh sử dụng phương thức client authentication hợp lệ ở thời điểm hiện tại.

### 9.4. Revocation endpoint và token đã phát hành

RFC 7009 mô tả endpoint revocation: client trình token cần thu hồi, server áp dụng quy tắc xác thực và kiểm tra client liên quan. Nó **không cung cấp một nút sẵn** để xóa toàn bộ refresh token của một user trên mọi client. Khi xây quản trị “Thu hồi tất cả phiên”, phải định nghĩa cách truy vấn authorization theo principal/tenant, xử lý token family, transaction, audit và hiệu lực thực tế tại Resource Server.

## 10. Kiểm thử liên kết bằng code và request thật

### 10.1. Unit test: authorization gắn với đúng client record ID

Ví dụ sử dụng một in-memory authorization service để chứng minh mô hình dữ liệu và lookup; đây **không phải** test của toàn bộ token endpoint:

~~~java
@Test
void refreshTokenRecordBelongsToRegisteredClient() {
    RegisteredClient clientA = RegisteredClient.withId("client-record-A")
        .clientId("orders-web")
        .clientSecret("{noop}test-only-secret")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://orders.example.com/callback")
        .scope("orders.read")
        .build();

    Instant now = Instant.now();
    OAuth2RefreshToken rt = new OAuth2RefreshToken(
        "test-refresh-value", now, now.plusSeconds(600));
    OAuth2Authorization authorization =
        OAuth2Authorization.withRegisteredClient(clientA)
            .principalName("user-42")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizedScopes(Set.of("orders.read"))
            .refreshToken(rt)
            .build();

    OAuth2AuthorizationService service =
        new InMemoryOAuth2AuthorizationService();
    service.save(authorization);

    OAuth2Authorization found = service.findByToken(
        "test-refresh-value", OAuth2TokenType.REFRESH_TOKEN);

    assertThat(found).isNotNull();
    assertThat(found.getRegisteredClientId()).isEqualTo(clientA.getId());
    assertThat(found.getRefreshToken().isActive()).isTrue();
    assertThat(service.findByToken(
        "unknown-value", OAuth2TokenType.REFRESH_TOKEN)).isNull();
}
~~~

Test này chứng minh repository trả về authorization chứa refresh token đúng và ID client đúng. Nó **không** chứng minh token endpoint đã từ chối client B; muốn kiểm tra client-binding ở provider, cần **integration test đi qua token endpoint và client authentication**.

### 10.2. Integration test: client A được phép, client B bị từ chối

Tình huống test:

1. Đăng ký <code>orders-web</code> và <code>billing-web</code> là hai confidential client **có ID bản ghi khác nhau**, secret riêng và refresh grant phù hợp.
2. Tạo authorization thực của <code>orders-web</code> với refresh token <code>RT-1</code>, <code>authorizedScopes = {orders.read}</code>, trạng thái active.
3. Gửi <code>POST /oauth2/token</code> với <code>grant_type=refresh_token</code>, <code>RT-1</code> và client authentication của **billing-web**.
4. Xác minh request **không nhận access token** và authorization state không bị đổi sai; mã lỗi OAuth cụ thể tùy phiên bản/provider.
5. Gửi cùng request với client authentication **orders-web**, scope hợp lệ; nếu policy không chặn, nhận access token mới và refresh token theo <code>TokenSettings</code>.
6. Kiểm tra JWT/access token mới có issuer, audience và scope đúng; không dùng ID Token để gọi API.

Để test có giá trị, cần giữ nguyên chuỗi filter và provider thật, không dùng mock <code>Authentication</code> đánh dấu client đã xác thực rồi kết luận cơ chế client authentication hoạt động. Có thể dùng <code>MockMvc</code> hoặc HTTP integration test; phần setup client/authorization service và kho token phải là dữ liệu có kiểm soát.

### 10.3. Ma trận kiểm thử

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| Token active, thuộc client A, scope hợp lệ | Refresh thành công nếu các policy khác cho phép. |
| Token thuộc client A nhưng request xác thực client B | Bị từ chối, không phát token. |
| Token không có trong <code>OAuth2AuthorizationService</code> | <code>invalid_grant</code> hoặc lỗi giao thức phù hợp. |
| Repository trả về authorization không chứa đúng refresh token | Không được phát token; phát hiện lỗi data access. |
| Token đã hết hạn | Từ chối, thường <code>invalid_grant</code>. |
| Token đã invalidated/revoked | Từ chối; không tái kích hoạt nhờ refresh request. |
| Client đã mất quyền dùng refresh grant | Từ chối dù token còn hạn. |
| Scope yêu cầu là tập con đã được cấp | Cấp token với scope hợp lệ theo chính sách. |
| Scope yêu cầu chứa quyền chưa từng được cấp | <code>invalid_scope</code> hoặc lỗi tương ứng, không mở rộng quyền. |
| Resource indicator đổi từ Orders API sang Billing API | Từ chối phạm vi resource không được chấp thuận. |
| Dùng <code>clientId</code> thay <code>getId()</code> để so binding | Test phải bắt được mismatch/sai schema. |
| Client record ID thay đổi sau migration | Phát hiện authorization orphaned, không bỏ qua binding. |
| Refresh token cũ được gửi lại sau rotation | Không được cấp token lần nữa; nếu có replay detection thì xử lý family. |
| Hai refresh request đồng thời | Không được cùng cấp hai refresh token hợp lệ ngoài policy. |
| User bị disabled hoặc tenant bị khóa | Chặn refresh nếu chính sách yêu cầu kiểm tra trạng thái hiện tại. |
| Account session đã logout nhưng refresh token vẫn còn | Hành vi phải theo chính sách revoke; không tự suy logout luôn xóa refresh. |
| Hai instance dùng chung database | Không tạo race khi rotation, trạng thái nhất quán. |
| Token bị lấy cắp, log/proxy lộ credential | Phát hiện, thu hồi, thay secret và điều tra theo quy trình. |

### 10.4. Kiểm thử repository tùy biến với dữ liệu sai

Nếu dự án viết <code>OAuth2AuthorizationService</code> riêng (JPA/Redis/Cassandra), nên thêm test:

- <code>findByToken(value, REFRESH_TOKEN)</code> chỉ trả bản ghi khi **token type và value** đúng.
- Authorization có <code>registeredClientId</code> không tồn tại phải bị xử lý an toàn, không tự cấp token cho client theo tên tương tự.
- Dữ liệu token metadata không nhất quán hoặc không thể deserialize phải bị từ chối, không mặc định coi là active.
- Không có sự khác biệt kết quả giữa những node khi lưu authorization chung.
- Cập nhật rotation/revocation đồng thời dùng optimistic lock/transaction thực sự.

Không test bằng cách sửa thẳng client ID trong một token và mặc định rằng chữ ký JWT của access token chứng minh refresh token binding; hai loại token và nơi lưu trạng thái có vai trò khác nhau.

## 11. Lỗi thiết kế thường gặp

### Lỗi 1: Chỉ tra refresh token tồn tại rồi phát token

<code>findByToken()</code> trả về authorization là **bước đầu**. Phải đối chiếu registered client ID, refresh grant, token active, scopes/resources và policy bổ sung. Nếu xây custom provider, không bỏ qua bất kỳ điều kiện bảo mật cơ bản nào.

### Lỗi 2: So sai ID client

So <code>authorization.getRegisteredClientId()</code> với <code>registeredClient.getClientId()</code> có thể sai khi ID nội bộ khác client ID giao thức. Hãy so với <code>getId()</code> và giữ ID ổn định qua migration.

### Lỗi 3: Tin refresh token là JWT tự xác thực đầy đủ

Dù refresh token được biểu diễn ở dạng có chữ ký, cần kiểm tra trạng thái, revocation, binding với client/authorization, scopes và sender constraint theo chính sách. Payload JWT tự khai không thay thế dữ liệu authorization đáng tin.

### Lỗi 4: Mặc định rotation phát hiện mọi replay

<code>reuseRefreshTokens(false)</code> làm framework tạo token mới, nhưng để phát hiện replay và thu hồi cả family cần thiết kế lưu quan hệ token cũ/mới, nhận diện reuse và thao tác atomic. Điều này đặc biệt quan trọng với public client theo RFC 9700.

### Lỗi 5: Bỏ qua kiểm tra resource/audience khi refresh

Một refresh token đã được cấp cho Orders API không phải giấy phép đổi sang Billing API chỉ vì client có thể gửi tham số <code>resource</code> mới. Cần ràng buộc với resource đã consent theo RFC 9700 và triển khai kiểm tra có chủ đích.

### Lỗi 6: Đăng xuất/disable user là coi token đã bị thu hồi

Session login, consent, authorization và refresh token là các vòng đời khác nhau. Đăng xuất hoặc vô hiệu hóa tài khoản không tự động làm JWT access token cũ mất hiệu lực. Nếu cần ngắt kết nối nhanh, phải có chính sách token revocation/TTL/introspection hoặc kiểm tra trạng thái.

### Lỗi 7: Lưu token thô trong log và bảng audit

Refresh token là bearer credential. Không ghi nó vào URL, log, exception message, tracing baggage hoặc sự kiện analytics. Khi cần tra cứu bảo mật, dùng token ID/hash được kiểm soát và chính sách hạn chế quyền truy cập dữ liệu.

### Lỗi 8: Test dùng mock authentication rồi tuyên bố an toàn

Unit test repository chỉ chứng minh mapping. Một mock principal đã xác thực có thể bỏ qua client credential validation. Cần ít nhất một integration test gửi HTTP request refresh thật với hai client có credential khác nhau để chứng minh liên kết ở token endpoint.

## 12. Vận hành production

Một triển khai hoàn chỉnh cần trả lời:

| Chủ đề | Câu hỏi kiểm soát |
| --- | --- |
| Client registration | ID nội bộ ổn định không? Client có quyền refresh grant không? Secret/cert/key đã quản lý an toàn chưa? |
| Authorization store | Có lưu refresh token với đúng authorization, scope, client ID và metadata không? |
| Transaction | Refresh đồng thời có thể cấp hai token mới hoặc overwrite nhau không? |
| Rotation/replay | Có giữ token family đủ để phát hiện reuse và revoke family khi cần không? |
| TTL | Có idle expiry, max lifetime và chính sách không kéo dài family vô hạn không? |
| Resource restriction | Refresh có thể dùng ở API khác với audience/resource ban đầu không? |
| Revocation | Có xử lý account disabled, password reset, consent revoke và token revoked theo yêu cầu không? |
| Multi-node | Các instance có chia sẻ DB/cache trạng thái, issuer, key và locking strategy không? |
| Logging | Có ẩn refresh token, client secret, authorization code và dữ liệu nhạy cảm không? |
| Client behavior | Client có lưu token mới an toàn, thay token cũ và tránh refresh đồng thời không? |
| Test/monitoring | Có kiểm thử sai client, replay, scope/resource escalation và cảnh báo bất thường không? |

Với confidential web client, giữ refresh token ở backend hoặc storage phù hợp được kiểm soát truy cập, tránh localStorage của trình duyệt. Nếu dùng public client, cần đánh giá nghiêm túc rủi ro token bị trích xuất và đáp ứng yêu cầu sender-constrained hoặc rotation có replay detection của RFC 9700. Chính sách token lifetime và tài nguyên phải được thiết kế theo mức độ nhạy cảm dữ liệu.

## 13. Bài tập ứng dụng

Hệ thống có ba client <code>orders-web</code>, <code>billing-web</code>, <code>mobile-public</code> dùng chung một Authorization Server. Alice cấp <code>orders.read</code> cho <code>orders-web</code>, nhận refresh token <code>RT-1</code>. Sau một giờ, token được refresh, và phía server đang cân nhắc cấu hình rotation.

1. Thiết kế bản ghi <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, <code>OAuth2RefreshToken</code> tương ứng, chỉ rõ <code>RegisteredClient.id</code> và <code>clientId</code> khác nhau thế nào.
2. Mô tả thứ tự kiểm tra khi <code>billing-web</code> gửi <code>RT-1</code> cùng client authentication hợp lệ của chính nó. Kết quả phải là gì?
3. Xây dựng code dùng <code>OAuth2AuthorizationService.findByToken(..., REFRESH_TOKEN)</code>, kiểm tra ID client, trạng thái token và <code>authorizedScopes</code>; đánh dấu đâu là pseudocode, đâu là Spring API thật.
4. Client xin <code>scope=orders.read billing.admin</code> từ <code>RT-1</code>. Nêu chính sách từ chối và cách test.
5. Nếu <code>RT-1</code> được đổi thành <code>RT-2</code>, mô tả lưu trữ lineage cần thiết để phát hiện <code>RT-1</code> bị dùng lại, cùng hành vi khi có hai request đồng thời.
6. Đề xuất ràng buộc resource khi <code>orders-web</code> cố xin access token cho Billing API bằng refresh token ban đầu.
7. Chọn chiến lược bảo vệ refresh token cho <code>mobile-public</code> theo RFC 9700, giải thích yêu cầu liên quan sender constraint hoặc rotation.
8. Thiết kế thao tác vô hiệu hóa Alice và thu hồi refresh token của toàn bộ client liên quan, trong khi Orders API đang xác minh access token JWT offline.
9. Viết integration test đi qua token endpoint thật để bảo đảm client B không thể đổi refresh token thuộc client A.

Một bài làm đạt yêu cầu phải chứng minh được **refresh token chỉ thuộc đúng authorization**, **authorization chỉ thuộc đúng registered client**, **scope/resource không tăng vượt quyền được cấp**, và **token bị thu hồi, hết hạn hay bị replay không thể tiếp tục phát quyền mới ngoài chính sách**.

## 14. Tài liệu đối chiếu

- [RFC 6749, §6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): client authentication, refresh token binding, scope khi refresh và hành vi cấp token mới.
- [RFC 6749, §10.4 — Refresh Tokens](https://www.rfc-editor.org/rfc/rfc6749#section-10.4): giữ bí mật, TLS và liên kết client.
- [RFC 9700, §4.14 — Refresh Token Protection](https://www.rfc-editor.org/rfc/rfc9700#section-4.14): best current practice về scope/resource binding, rotation, replay và public client.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint thu hồi token và mô hình lỗi.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số resource và token giới hạn theo tài nguyên.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens bằng application-layer proof.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, <code>OAuth2AuthorizationService</code>, token metadata.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): token endpoint và providers xử lý refresh grant.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): Java DSL và mở rộng token endpoint.
- [Spring Authorization Server — JPA Core Services Guide](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): ánh xạ authorization, client ID và token trong persistence.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): <code>refreshTokenTimeToLive</code> và <code>reuseRefreshTokens</code>.
