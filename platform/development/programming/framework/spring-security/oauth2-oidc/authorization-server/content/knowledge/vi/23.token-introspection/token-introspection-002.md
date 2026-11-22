# Xác thực và phân quyền client được phép introspect

## Mục tiêu bài học

Trong chương **Introspection** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn cách xác thực ứng dụng gọi **OAuth 2.0 Token Introspection Endpoint** và phân quyền ứng dụng đó được phép tra cứu những token nào. Nội dung tập trung vào **Spring Security**, **Spring Authorization Server** và **Spring Boot** trong hệ thống OAuth 2.0/OpenID Connect Authorization Server.

Token introspection là thao tác nhạy cảm: endpoint nhận một bearer credential và trả thông tin về trạng thái, scope, chủ thể, audience, thời hạn và ngữ cảnh authorization của token. Nếu chỉ kiểm tra client có đăng nhập thành công mà không kiểm soát client được phép xem token nào, một Resource Server bị xâm nhập có thể trở thành công cụ dò token hoặc thu thập thông tin của hệ thống khác.

Sau bài học, bạn có thể:

- Phân biệt **xác thực client gọi introspection** với **phân quyền client được xem thông tin token**.
- Giải thích yêu cầu bảo vệ endpoint theo RFC 7662, đặc biệt chống token scanning và rò rỉ trạng thái.
- Cấu hình client authentication cho introspection bằng **client_secret_basic**, **private_key_jwt** hoặc mTLS khi phù hợp.
- Đăng ký Resource Server/Protected Resource riêng trong **RegisteredClientRepository** và quản lý credential của nó.
- Thiết kế allowlist/policy dựa trên client identity, audience/resource, token type, tenant và scope.
- Mở rộng **OAuth2TokenIntrospectionAuthenticationProvider** qua **OAuth2TokenIntrospectionEndpointConfigurer** mà vẫn giữ xử lý token chuẩn.
- Trả **active=false** cho token không tồn tại, không hoạt động hoặc caller không được phép biết token đó.
- Giới hạn claims trả về, bảo vệ logs, rate limit, cache và kiểm thử cả trường hợp hợp lệ lẫn bị từ chối.

> **Tình huống xuyên suốt:** **inventory-api** là Resource Server gọi **POST /oauth2/introspect** để xác minh access token. Một token có thể do **inventory-worker**, **employee-portal** hoặc đối tác phát sinh. **inventory-api** chỉ được tra cứu token dành cho audience **inventory-api**; không được đọc thông tin token chỉ dành cho **billing-api**.

## 1. Introspection là một endpoint có quyền truy cập đặc biệt

Theo RFC 7662, Token Introspection Endpoint nhận một token và trả JSON mô tả metadata của token, trong đó trường **active** cho biết token có đang hoạt động hay không. Endpoint thường được Resource Server/Protected Resource gọi để quyết định có chấp nhận token cho request hiện tại không.

Introspection hữu ích với opaque/reference token vì Resource Server không thể tự xác minh trạng thái từ chuỗi token. Nó cũng có thể được dùng với JWT khi hệ thống muốn kiểm tra trạng thái thu hồi hoặc policy mới nhất ở Authorization Server.

### 1.1. Ai gọi endpoint và token nào được tra cứu?

Có hai danh tính độc lập:

| Danh tính | Vai trò | Ví dụ |
|---|---|---|
| **Introspection caller** | Ứng dụng/Resource Server đang gọi endpoint. | **inventory-api-introspector** |
| **Token subject / issuing client** | Chủ thể hoặc client mà token được phát hành cho. | **inventory-worker** |
| **Resource Server đích** | API sẽ sử dụng metadata để ra quyết định. | **inventory-api** |
| **Authorization Server** | Nơi xác thực caller, tra trạng thái token và trả response. | **auth.example.com** |

Client ID dùng để xác thực introspection caller có thể **khác** client ID được trả trong response của token đang tra cứu. Resource Server có thể cần introspect token do nhiều OAuth2 client phát hành; điều đó không có nghĩa mọi Resource Server đều được phép tra cứu mọi token.

**Không nhầm hai credential:**

- Credential của **inventory-api-introspector** dùng để chứng minh ứng dụng được gọi endpoint introspection.
- Access token trong body **token** là đối tượng đang được tra cứu.
- Hai giá trị này không phải một và không được thay thế cho nhau.

### 1.2. Hai lớp kiểm soát: Authentication và Authorization

~~~mermaid
flowchart TD
    A[POST /oauth2/introspect] --> B[Client Authentication Filter]
    B --> C{Caller credential hợp lệ?}
    C -->|Không| D[401 Unauthorized]
    C -->|Có| E[OAuth2TokenIntrospectionAuthenticationToken]
    E --> F[Introspection AuthenticationProvider]
    F --> G[Tra cứu token và kiểm tra trạng thái]
    G --> H{Caller có quyền biết token này?}
    H -->|Không| I[200 active=false]
    H -->|Có| J{Token còn hiệu lực?}
    J -->|Không| I
    J -->|Có| K[200 active=true + claims được phép]
    K --> L[Resource Server kiểm scope, audience và policy API]
~~~

- **Authentication:** Ai đang gọi? Credential có khớp một client đã đăng ký không?
- **Authorization:** Client đã xác thực đó có quyền introspect token cụ thể này không?
- **Token validation:** Token có tồn tại, chưa hết hạn, chưa bị revoke và đáp ứng điều kiện active không?
- **Resource authorization:** API có cho phép token truy cập endpoint/đối tượng nghiệp vụ hiện tại không?

Chỉ qua bước Authentication không đồng nghĩa đã qua bước Authorization. Một client xác thực hợp lệ vẫn có thể không được phép xem token của resource khác.

## 2. Yêu cầu của RFC 7662

### 2.1. Introspection Request

RFC 7662 mục 2.1 yêu cầu Protected Resource gửi HTTP **POST** với body **application/x-www-form-urlencoded**. Trường **token** là bắt buộc; **token_type_hint** có thể được gửi để gợi ý loại token.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <BASE64_CLIENT_CREDENTIAL>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN_TO_INSPECT>&token_type_hint=access_token
~~~

Các giá trị trong dấu ngoặc nhọn là placeholder. Request thực phải dùng HTTPS/TLS, kiểm tra chứng chỉ máy chủ và giữ kín cả client credential lẫn token body.

**Không gửi token qua query string hoặc URL GET.** URL thường bị ghi vào reverse proxy logs, browser history, monitoring và tracing. POST form-urlencoded giúp giữ token trong body, nhưng vẫn cần cấu hình redaction ở gateway/APM.

### 2.2. Vì sao endpoint phải yêu cầu authorization?

RFC 7662 mục 2.1 yêu cầu endpoint có cơ chế authorization để chống token scanning. Kẻ tấn công có thể gửi hàng loạt giá trị đoán được và dùng response để tìm token hợp lệ. RFC cho phép bảo vệ bằng client authentication hoặc một access token riêng có quyền gọi endpoint.

RFC 7662 mục 4 còn khuyến nghị Authorization Server nên **ủy quyền rõ Protected Resource nào được phép introspect**. Đây là lý do cần policy cho từng caller và phạm vi token được phép xem.

Các nguyên tắc:

1. Không public endpoint introspection để bất kỳ ai gửi token.
2. Không coi client ID đơn thuần của public client là một credential mạnh.
3. Chỉ cấp credential cho Resource Server/Protected Resource có owner và nhu cầu rõ ràng.
4. Giới hạn mỗi caller theo resource/audience, tenant, loại token và claims cần thiết.
5. Nếu dùng một access token riêng để gọi introspection, token đó phải được giới hạn cho mục đích này và được kiểm tra quyền tại endpoint.

### 2.3. Quy tắc chống dò token: trả active=false

RFC 7662 mục 2.2 quy định rằng nếu request được authorization hợp lệ nhưng token:

- Không hoạt động hoặc đã hết hạn.
- Không tồn tại tại Authorization Server.
- Đã bị revoke.
- Là token mà Protected Resource gọi **không được phép biết**.

thì server phải trả response introspection có **active=false**. Server **không nên** gửi thêm thông tin giải thích vì sao token inactive.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

Điều này tránh tạo ra oracle cho biết token có tồn tại hay không, token thuộc client nào hoặc đã bị revoke vì lý do gì.

Phân biệt với lỗi credential của caller:

| Trường hợp | Response phù hợp |
|---|---|
| Caller không xác thực được bằng client credential | HTTP 401 theo cơ chế client authentication. |
| Request thiếu token hoặc sai định dạng | OAuth2 error response phù hợp, thường HTTP 400. |
| Caller được xác thực, token không tồn tại | HTTP 200 với **active=false**. |
| Caller được xác thực, token đã hết hạn/revoke | HTTP 200 với **active=false**. |
| Caller được xác thực nhưng không được phép biết token này | HTTP 200 với **active=false**, không giải thích thêm. |
| Caller được phép, token active | HTTP 200 với **active=true** và các metadata được phép tiết lộ. |

Không trả **403 token belongs to billing-api** hoặc **404 token exists but forbidden** cho một token cụ thể; những response đó làm lộ trạng thái nội bộ.

## 3. Phản hồi introspection và dữ liệu được phép xem

### 3.1. Response cho token active

Ví dụ RFC 7662:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "client_id": "inventory-worker",
  "scope": "inventory.read",
  "sub": "service-inventory",
  "aud": ["inventory-api"],
  "iss": "https://auth.example.com",
  "exp": 1794861000,
  "iat": 1794859200,
  "token_type": "Bearer"
}
~~~

Response là metadata của **token được tra cứu**, không phải profile đầy đủ của introspection caller.

| Claim | Ý nghĩa | Lưu ý phân quyền |
|---|---|---|
| **active** | Token có đang active không. | Boolean bắt buộc. |
| **client_id** | Client đã yêu cầu/phát sinh token. | Không phải client đang gọi introspection. |
| **scope** | Quyền được cấp cho token. | Chỉ trả scope cần thiết cho Resource Server đang gọi. |
| **sub** | Chủ thể của token. | Có thể là user hoặc machine principal; bảo vệ PII. |
| **aud** | Resource/audience mà token hướng tới. | Dùng để kiểm tra caller có thuộc audience được phép không. |
| **iss** | Issuer của token. | Giúp Resource Server ràng buộc trust domain. |
| **exp**, **iat**, **nbf** | Thời gian token. | Dùng để ra quyết định và cache an toàn. |
| **jti** | Định danh token nếu có. | Có thể nhạy cảm trong hệ thống correlation. |
| Trường mở rộng | Metadata do server định nghĩa. | Chỉ trả theo policy, không phát tán nội bộ không cần thiết. |

### 3.2. Cùng token, response có thể khác theo caller

RFC 7662 cho phép Authorization Server trả response khác nhau cho các Protected Resource khác nhau khi cùng introspect một token. Ví dụ:

- **inventory-api** chỉ cần **scope**, **aud**, **exp** và **sub** machine.
- **billing-api** có thể được phép xem một tập claims khác nếu token thực sự hướng tới billing.
- Một API chỉ được biết **active** và **scope**, không được biết username/email hoặc metadata của hệ thống khác.

Điều này giảm lượng dữ liệu bị lộ khi một Resource Server bị xâm nhập. Đừng tạo một introspection response chứa toàn bộ claims cho mọi client rồi để từng API tự bỏ qua phần không cần thiết.

### 3.3. Audience và scope không phải quyền introspect

- **aud** của token mô tả resource nhận token.
- **scope** mô tả quyền của token khi truy cập API.
- Quyền introspect là **quyền của caller đối với dữ liệu token**, được xác định bởi policy của Authorization Server.

Một token có scope **inventory.read** không tự cấp cho client bất kỳ quyền nào gọi introspection. Tương tự, client đăng ký scope **inventory.read** không có nghĩa nó được phép xem token của mọi ứng dụng có scope đó.

## 4. Đăng ký và xác thực introspection caller trong Spring Authorization Server

Spring Authorization Server 1.5.x cấu hình client authentication qua **OAuth2ClientAuthenticationFilter**. Theo cấu hình mặc định, client authentication được yêu cầu tại Token Endpoint, Token Introspection Endpoint và Token Revocation Endpoint.

Các phương thức thường được hỗ trợ gồm:

| Phương thức | Mô tả | Khuyến nghị cho introspection service |
|---|---|---|
| **client_secret_basic** | Client ID/secret trong HTTP Basic. | Phù hợp khi secret mạnh, TLS và rotation tốt. |
| **client_secret_post** | Client ID/secret trong form body. | Chỉ dùng khi cần tương thích; cần redaction body. |
| **private_key_jwt** | Client ký JWT assertion bằng private key. | Tốt khi có PKI/key management và assertion validation. |
| **client_secret_jwt** | JWT assertion được xác minh bằng shared secret. | Dùng theo policy/version hỗ trợ. |
| **tls_client_auth** | Xác thực bằng client certificate mTLS. | Phù hợp service-to-service có PKI. |
| **self_signed_tls_client_auth** | mTLS với certificate tự ký đã đăng ký. | Cần quản lý pinning/rotation certificate chặt chẽ. |
| **none** | Public client không có client secret. | Không nên dùng làm bảo vệ duy nhất cho introspection endpoint. |

### 4.1. Introspection client là một RegisteredClient riêng

Ví dụ kiến trúc:

| Registered client | Mục đích | Credential |
|---|---|---|
| **inventory-worker** | Xin access token để gọi Inventory API. | Credential của worker. |
| **employee-portal** | Thực hiện login/authorization cho nhân viên. | Credential của portal. |
| **inventory-api-introspector** | Gọi introspection để xác minh token tới Inventory API. | Secret riêng hoặc private key/certificate. |
| **billing-api-introspector** | Gọi introspection cho Billing API. | Credential riêng với inventory. |

Tách caller theo Resource Server giúp thu hồi hoặc rotate credential của một API mà không ảnh hưởng API khác. Không dùng chung secret của **inventory-worker** cho **inventory-api-introspector** chỉ vì hai hệ thống cùng thuộc một sản phẩm.

Trong **RegisteredClientRepository**, introspection caller phải có registration hợp lệ và phương thức client authentication tương ứng. Việc đăng ký grant **client_credentials** chỉ cần khi client đó cũng cần xin access token qua grant này; nó **không tự động cấp quyền introspect**.

### 4.2. Resource Server cấu hình credential gọi introspection

Với Spring Security Resource Server dùng opaque token, Spring Boot có thể cấu hình endpoint và credential:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: inventory-api-introspector
          client-secret: secret-from-secret-manager
~~~

Đây là cấu hình ở **Resource Server**, không phải Authorization Server. Secret phải được inject từ secret manager/credential store và không commit vào YAML. Resource Server dùng credential này để xác thực khi gửi request introspection.

Nếu một Resource Server cần quyền introspect giới hạn theo audience, Authorization Server phải kiểm tra caller **inventory-api-introspector** có được phép xem token có **aud** tương ứng hay không. Chỉ đặt client ID và client secret ở Resource Server chưa tạo ra policy đó.

## 5. Phân quyền client được phép introspect

### 5.1. Xây dựng policy theo caller và token

Một policy thực tế nên kiểm tra ít nhất:

1. **Caller identity:** RegisteredClient đã xác thực là client nào?
2. **Resource/audience:** token được phát cho API nào?
3. **Token type:** caller có được phép introspect access token, refresh token hoặc token type extension không?
4. **Tenant/domain:** token thuộc tenant hoặc trust domain nào?
5. **Data disclosure:** caller được xem những claims nào?
6. **Operational status:** caller có đang bị disable, credential hết hạn hoặc bị giới hạn rate không?

Mô hình quyền ví dụ:

| Introspection caller | Audience token | Kết quả |
|---|---|---|
| **inventory-api-introspector** | **inventory-api** | Được phép; trả claims cần cho inventory. |
| **inventory-api-introspector** | **billing-api** | Không được phép; trả **active=false**. |
| **billing-api-introspector** | **billing-api** | Được phép; trả claims cần cho billing. |
| **support-tool-introspector** | Mọi audience | Chỉ được phép nếu có quyền hỗ trợ được phê duyệt, audit và giới hạn thời gian. |
| Client chưa đăng ký hoặc credential sai | Bất kỳ | Client authentication thất bại. |

Không dùng tên client hoặc scope trong body token request do caller tự gửi làm căn cứ cấp quyền. Caller identity phải lấy từ Authentication đã được filter xác thực.

### 5.2. Allowlist theo audience/resource

Một chính sách dễ kiểm soát là ánh xạ introspection client sang audience được phép:

~~~text
inventory-api-introspector -> inventory-api
billing-api-introspector   -> billing-api
reporting-introspector     -> reporting-api
~~~

Khi provider xử lý request:
- Lấy client ID từ RegisteredClient đã xác thực.
- Tra authorization/token record từ **OAuth2AuthorizationService**.
- Đọc audience/resource metadata từ access token hoặc authorization attributes theo schema của hệ thống.
- So sánh audience với allowlist của caller.
- Nếu caller không được phép, trả response inactive tối giản.
- Nếu được phép, giao việc kiểm tra token active và tạo claims cho provider chuẩn.

Audience phải được phát hành từ nguồn policy tin cậy. Không suy ra audience chỉ từ client ID của token nếu hệ thống có nhiều API hoặc token có thể dùng cho nhiều resource.

### 5.3. Allowlist không thay thế scope và tenant checks

Một caller được phép introspect **inventory-api** vẫn phải nhận đúng phạm vi dữ liệu:

- Chỉ trả scope mà Inventory API cần để quyết định request.
- Chỉ trả subject/tenant claims cần thiết.
- Không tiết lộ email, tên nhân viên, role nội bộ hoặc metadata billing nếu không liên quan.
- Nếu token mang nhiều audience, response có thể được giới hạn cho caller hiện tại.
- Resource Server tiếp tục kiểm scope, audience, tenant và quyền trên endpoint thực tế.

### 5.4. Không dùng RegisteredClient.scope làm quyền introspection một cách ngầm định

**RegisteredClient.getScopes()** mô tả scope client có thể yêu cầu khi xin token. Nó không phải một danh sách audience hoặc danh sách token được phép tra cứu.

Có thể xây một policy registry riêng, hoặc dùng metadata ứng dụng được quản lý cùng registration, nhưng cần đặt tên và semantics rõ ràng, ví dụ:

- **allowedIntrospectionAudiences**.
- **allowedIntrospectionTokenTypes**.
- **introspectionClaimProfile**.
- **introspectionEnabled**.

Các thuộc tính trên là **schema do ứng dụng định nghĩa**, không phải field mặc định có sẵn trong mọi **RegisteredClient**.

## 6. Cấu hình Token Introspection Endpoint trong Spring Authorization Server

**OAuth2AuthorizationServerConfigurer** cung cấp **tokenIntrospectionEndpoint(...)** để cấu hình endpoint. **OAuth2TokenIntrospectionEndpointConfigurer** có các extension point:

| API | Vai trò |
|---|---|
| **introspectionRequestConverter(...)** | Thêm converter parse request thành **OAuth2TokenIntrospectionAuthenticationToken**. |
| **introspectionRequestConverters(...)** | Truy cập danh sách converter mặc định để bổ sung/điều chỉnh. |
| **authenticationProvider(...)** | Thêm provider xử lý introspection authentication. |
| **authenticationProviders(...)** | Truy cập danh sách provider mặc định để bổ sung/thay thế. |
| **introspectionResponseHandler(...)** | Xử lý response thành công và serialize **OAuth2TokenIntrospection**. |
| **errorResponseHandler(...)** | Xử lý OAuth2 error khi authentication/request thất bại. |

Cấu hình khung:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    var authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenIntrospectionEndpoint(introspection -> {
                // Đăng ký policy/provider tùy chỉnh ở đây.
            }))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung minh họa cho Spring Authorization Server 1.x. Ứng dụng hoàn chỉnh còn cần **RegisteredClientRepository**, **OAuth2AuthorizationService**, **AuthorizationServerSettings**, token generator/JWK và các filter chain khác theo grant được hỗ trợ.

### 6.1. Các thành phần mặc định

Theo tài liệu Spring Authorization Server 1.5.8, **OAuth2TokenIntrospectionEndpointFilter** được cấu hình với:

- **OAuth2TokenIntrospectionAuthenticationConverter** để parse request.
- **AuthenticationManager** gồm **OAuth2TokenIntrospectionAuthenticationProvider**.
- Success handler nội bộ tạo response **OAuth2TokenIntrospection**.
- **OAuth2ErrorAuthenticationFailureHandler** để trả OAuth2 error.

**OAuth2TokenIntrospectionAuthenticationProvider** nhận **RegisteredClientRepository** và **OAuth2AuthorizationService**. Provider chuẩn chịu trách nhiệm xử lý token introspection và tạo kết quả theo authorization/token state.

**Giữ converter và success/error handler mặc định nếu không có yêu cầu cụ thể.** Nếu chỉ cần policy caller-to-token, tập trung vào provider. Không tự parse hoặc serialize lại toàn bộ giao thức.

## 7. Thêm policy vào provider mà vẫn giữ xử lý token chuẩn

### 7.1. Dữ liệu authentication có sẵn

**OAuth2TokenIntrospectionAuthenticationToken** chứa:

- Token được gửi trong request qua **getToken()**.
- Client principal đã xác thực qua **getPrincipal()**.
- **token_type_hint** qua **getTokenTypeHint()**.
- Additional parameters nếu có.

Client principal thường là **OAuth2ClientAuthenticationToken** sau khi **OAuth2ClientAuthenticationFilter** xác thực. Lấy RegisteredClient từ principal đã xác thực, không lấy caller ID từ tham số tùy ý.

### 7.2. Policy interface do ứng dụng định nghĩa

Ví dụ interface:

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

interface IntrospectionAccessPolicy {

    boolean mayIntrospect(
            RegisteredClient caller,
            OAuth2Authorization targetAuthorization,
            String tokenTypeHint);
}
~~~

**IntrospectionAccessPolicy** là interface **do ứng dụng tự triển khai**, không phải API có sẵn của Spring. Implementation có thể kiểm tra allowlist audience, tenant, token type và claim profile. Nếu authorization không chứa audience rõ ràng, hãy thiết kế metadata/resource association có nguồn tin cậy thay vì suy đoán.

### 7.3. Bọc provider chuẩn

Có thể bọc **OAuth2TokenIntrospectionAuthenticationProvider** để thêm authorization check, rồi delegate phần kiểm tra trạng thái token cho provider chuẩn:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenIntrospection;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2TokenIntrospectionAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2TokenIntrospectionAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

final class ClientAwareIntrospectionAuthenticationProvider
        implements AuthenticationProvider {

    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenIntrospectionAuthenticationProvider delegate;
    private final IntrospectionAccessPolicy accessPolicy;

    ClientAwareIntrospectionAuthenticationProvider(
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenIntrospectionAuthenticationProvider delegate,
            IntrospectionAccessPolicy accessPolicy) {
        this.authorizationService = authorizationService;
        this.delegate = delegate;
        this.accessPolicy = accessPolicy;
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        OAuth2TokenIntrospectionAuthenticationToken request =
                (OAuth2TokenIntrospectionAuthenticationToken) authentication;

        if (!(request.getPrincipal() instanceof
                OAuth2ClientAuthenticationToken clientAuthentication)
                || !clientAuthentication.isAuthenticated()
                || clientAuthentication.getRegisteredClient() == null) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
        }

        RegisteredClient caller = clientAuthentication.getRegisteredClient();

        OAuth2Authorization targetAuthorization =
                this.authorizationService.findByToken(request.getToken(), null);

        if (targetAuthorization != null
                && !this.accessPolicy.mayIntrospect(
                        caller,
                        targetAuthorization,
                        request.getTokenTypeHint())) {

            // Không tiết lộ token có tồn tại, thuộc client nào hay vì sao bị từ chối.
            OAuth2TokenIntrospection inactive =
                    OAuth2TokenIntrospection.builder(false).build();

            return new OAuth2TokenIntrospectionAuthenticationToken(
                    request.getToken(), clientAuthentication, inactive);
        }

        // Provider chuẩn kiểm tra trạng thái token và tạo claims response.
        return this.delegate.authenticate(authentication);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return OAuth2TokenIntrospectionAuthenticationToken.class
                .isAssignableFrom(authentication);
    }
}
~~~

Đây là mẫu triển khai cho API Spring Authorization Server 1.x; cần kiểm thử với đúng phiên bản dependency và các token type thực tế của ứng dụng. Các điểm quan trọng:

- **OAuth2AuthorizationService.findByToken(...)** dùng để tra authorization tương ứng; truyền token type hint phù hợp nếu policy cần phân biệt loại token.
- **token_type_hint** chỉ là gợi ý tối ưu lookup; không được xem nó là bằng chứng về loại token hoặc quyền của caller. Policy phải dựa trên token/authorization thực tế đã tìm được.
- Caller lấy từ **OAuth2ClientAuthenticationToken** đã xác thực.
- Nếu token tồn tại nhưng caller không được phép biết token đó, provider trả kết quả inactive tối giản.
- Nếu token không tìm thấy, provider chuẩn tiếp tục xử lý và trả inactive theo behavior của nó.
- Nếu caller được phép, provider chuẩn vẫn thực hiện kiểm tra active/expiry/revocation và xây claims.
- Không log **request.getToken()** hoặc toàn bộ authentication object.

Trong ứng dụng thực, phải xử lý an toàn trường hợp principal không đúng kiểu hoặc không có RegisteredClient. Client authentication filter cần đảm bảo request đi tới provider đã có client principal hợp lệ; vẫn nên có guard và test regression.

### 7.4. Thay provider mặc định trong danh sách

**authenticationProviders(...)** cho phép truy cập danh sách provider mặc định. Có thể thay provider introspection bằng wrapper ở cùng vị trí để giữ thứ tự xử lý:

~~~java
.tokenIntrospectionEndpoint(introspection ->
    introspection.authenticationProviders(providers -> {
        for (int i = 0; i < providers.size(); i++) {
            AuthenticationProvider provider = providers.get(i);

            if (provider instanceof
                    OAuth2TokenIntrospectionAuthenticationProvider standard) {

                providers.set(i,
                    new ClientAwareIntrospectionAuthenticationProvider(
                        authorizationService,
                        standard,
                        introspectionAccessPolicy));
                break;
            }
        }
    }))
~~~

**authorizationService** và **introspectionAccessPolicy** là Bean của ứng dụng. Đoạn code nằm trong lambda cấu hình **OAuth2AuthorizationServerConfigurer**; cần import **AuthenticationProvider** và các class tương ứng.

Nếu không tìm thấy provider mặc định ở version đang dùng, đừng âm thầm bỏ policy. Hãy kiểm tra API/version, fail startup hoặc có test bảo đảm policy được cài đúng. Không thêm một provider không được sắp thứ tự kiểm soát rồi giả định nó luôn chạy trước provider chuẩn.

### 7.5. Vì sao trả inactive thay vì throw forbidden?

Với một caller đã được xác thực và có quyền gọi endpoint nói chung, RFC 7662 yêu cầu response **active=false** khi token không hoạt động hoặc caller không được phép biết token đó. Throw AccessDeniedException hoặc trả HTTP 403 với nội dung “token exists but forbidden” có thể làm lộ sự tồn tại của token.

Ngược lại, nếu caller **không xác thực được** hoặc không có quyền gọi endpoint introspection nói chung, request phải bị từ chối ở lớp endpoint/client authentication. Không dùng **active=false** để che lỗi credential của chính caller.

## 8. Giới hạn response claims theo từng Resource Server

### 8.1. Response handler là lớp hậu xử lý

**introspectionResponseHandler(...)** nhận authentication thành công và trả JSON response. Có thể dùng để điều chỉnh projection claims theo caller, nhưng authorization policy cần được kiểm tra **trước** khi tạo kết quả. Response handler không nên là nơi duy nhất quyết định caller có được introspect token hay không.

Ví dụ response cho Inventory API:

~~~json
{
  "active": true,
  "client_id": "inventory-worker",
  "scope": "inventory.read",
  "aud": ["inventory-api"],
  "sub": "service-inventory",
  "exp": 1794861000
}
~~~

Không trả **email**, **phone_number**, danh sách quyền của Billing hoặc thông tin nội bộ nếu Inventory API không cần.

### 8.2. Claim projection theo policy

Một **IntrospectionAccessPolicy** hoặc component liên quan có thể xác định profile response:

| Caller | Claims tối thiểu |
|---|---|
| **inventory-api-introspector** | **active**, **scope**, **aud**, **exp**, **sub** machine. |
| **billing-api-introspector** | **active**, **scope**, **aud**, **exp**, subject cần thiết cho billing. |
| **analytics-introspector** | **active**, scope/audience cần cho báo cáo, không trả PII nếu không cần. |

Nếu tùy chỉnh **OAuth2TokenIntrospection** hoặc response handler, phải giữ các trường chuẩn và semantics **active**. Không trả claims đã bị loại bỏ bởi policy chỉ vì chúng có sẵn trong JWT payload hoặc authorization record.

### 8.3. Claims của token JWT và opaque token

- Với JWT access token, Authorization Server có thể đọc claims đã lưu trong authorization/token wrapper hoặc xác minh JWT theo cơ chế phù hợp.
- Với opaque/reference token, metadata nằm trong authorization store và được provider/introspection service truy xuất.
- Không giả định mọi token đều có cùng tập claims.
- Không tự parse JWT payload mà bỏ qua signature, issuer, expiry hoặc trạng thái revoke.
- Không trả toàn bộ custom claims chỉ vì token generator đã thêm chúng.

## 9. Bảo vệ endpoint và vận hành

### 9.1. TLS và client credential

RFC 7662 yêu cầu TLS cho introspection endpoint. Bên gọi phải xác minh chứng chỉ server. Với client authentication:

- Dùng secret đủ mạnh, không dùng secret mặc định/demo trong production.
- Ưu tiên private_key_jwt hoặc mTLS khi hạ tầng hỗ trợ và có quản lý khóa phù hợp.
- Tách credential theo Resource Server.
- Rotate credential có overlap/rollout, audit và rollback.
- Không để credential trong source code, container image, command history hoặc log.
- Không cho phép HTTP không mã hóa ở ingress nội bộ chỉ vì traffic ở private network.

### 9.2. Rate limit và chống token scanning

Áp dụng:

- Rate limit theo authenticated client ID và có thể theo IP/network identity.
- Giới hạn request body size và token length.
- Giới hạn concurrency và timeout tới authorization storage.
- Audit số lần introspection, tỷ lệ inactive, lỗi client authentication và latency.
- Alert khi một caller thử số lượng token bất thường.
- Không phân biệt response unknown/expired/revoked/unauthorized-to-see bằng nội dung công khai.

Rate limit phải tính đến tải hợp lệ của Resource Server: mỗi API request có thể kéo theo một lần introspection nếu không cache. Thiết kế quota đủ cao cho traffic bình thường và có burst policy.

### 9.3. Cache introspection response

RFC 7662 cho phép Protected Resource cache response để giảm tải, nhưng cache làm chậm việc nhận biết token bị revoke hoặc policy thay đổi.

- Nếu response có **exp**, không cache quá thời điểm hết hạn đó.
- TTL cache nên ngắn hơn hoặc bằng thời gian rủi ro chấp nhận được của revocation.
- Cache key phải phân biệt issuer, token fingerprint và resource/caller context.
- Không dùng response claims đầy đủ của một Resource Server cho Resource Server khác.
- Khi revoke token hoặc disable caller, cân nhắc cache invalidation hoặc giảm TTL.
- Nếu cần trạng thái gần real-time, dùng cache rất ngắn hoặc introspect mỗi request theo capacity đã tính.

Không cache raw token như một metric/log label. Cache nội bộ phải bảo vệ dữ liệu nhạy cảm và có giới hạn memory.

### 9.4. Observability không được làm rò token

Có thể log:
- Client ID của introspection caller đã xác thực.
- Resource Server/audience policy được chọn.
- Kết quả active/inactive và category nội bộ đã chuẩn hóa.
- Latency, request ID, status code và token type hint.
- Số lần rate limit hoặc policy deny.

Không log:
- Raw access token hoặc refresh token.
- Client secret, Basic Authorization header, private key hoặc client assertion.
- Toàn bộ introspection request/response body.
- Subject/PII nếu không cần và không có retention policy.

Khi support cần tra cứu một token, dùng fingerprint một chiều có salt/key quản lý phù hợp và quyền truy cập audit giới hạn, không sao chép token thật vào ticket.

## 10. Kiểm thử client authentication và introspection authorization

### 10.1. Ma trận kiểm thử endpoint

| Request | Kết quả mong đợi |
|---|---|
| Introspection caller hợp lệ, token active và audience được phép | 200, **active=true**, claims tối thiểu. |
| Client secret sai hoặc client không tồn tại | 401 theo client authentication. |
| Client xác thực được nhưng không được phép introspect endpoint | Bị từ chối ở lớp endpoint authorization. |
| Caller được xác thực nhưng token không tồn tại | 200, **active=false**. |
| Token đã hết hạn hoặc revoke | 200, **active=false**. |
| Token tồn tại nhưng audience không thuộc caller | 200, **active=false**, không giải thích. |
| Caller có audience đúng nhưng token thiếu scope cần thiết | Token có thể active; response thể hiện scope thực tế, Resource Server từ chối API request nếu thiếu quyền. |
| Token body thiếu **token** | OAuth2 **invalid_request**. |
| Request dùng GET/query string | Bị từ chối hoặc endpoint chỉ chấp nhận POST theo cấu hình. |
| Caller gửi token_type_hint sai | Không được bỏ qua việc xác định trạng thái token thực tế. |
| Caller A introspect token của audience B | Inactive theo policy, không tiết lộ token có tồn tại. |
| Caller B introspect token của audience B | Active và claims được phép. |
| Cùng token, hai Resource Server | Response được giới hạn theo caller/resource context. |

### 10.2. Ma trận kiểm thử policy

- **inventory-api-introspector** chỉ introspect token có audience **inventory-api**.
- **billing-api-introspector** không được xem token chỉ dành cho **inventory-api**.
- Client bị disable/credential revoke không tiếp tục gọi introspection.
- Client không có trong allowlist bị từ chối hoặc nhận inactive theo policy target-token, không lộ trạng thái.
- Tenant A không xem metadata token của tenant B.
- Refresh token introspection được bật hoặc tắt theo policy rõ ràng; không suy ra từ access-token permission.
- Scope được trả chỉ gồm quyền Resource Server được phép biết.
- Custom claim nhạy cảm không xuất hiện trong response.

### 10.3. Ví dụ MockMvc kiểm tra token không được phép introspect

Đoạn test minh họa trường hợp caller đã xác thực nhưng policy không cho biết token thuộc audience khác:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class IntrospectionAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedCallerCannotDiscoverForeignAudienceToken()
            throws Exception {

        mvc.perform(post("/oauth2/introspect")
                .with(httpBasic(
                        "inventory-api-introspector",
                        "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", "TOKEN_FOR_BILLING_API")
                .param("token_type_hint", "access_token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.active").value(false))
            .andExpect(jsonPath("$.client_id").doesNotExist())
            .andExpect(jsonPath("$.scope").doesNotExist());
    }
}
~~~

Test giả định fixture đã có:
- Client introspection hợp lệ và credential test.
- Token tồn tại nhưng audience chỉ dành cho Billing API.
- Policy wrapper được cài vào provider list.
- Endpoint path mặc định **/oauth2/introspect**.

Không dùng token thật trong test hoặc log. Cần thêm test token không tồn tại để xác nhận response công khai không thể phân biệt hai trường hợp.

### 10.4. Kiểm thử happy path và failure path

Ngoài test inactive:

1. Gửi token active có audience được phép; xác nhận **active=true** và scope đúng.
2. Gửi token expired/revoked; xác nhận **active=false**.
3. Gửi sai secret; xác nhận 401.
4. Gửi request không có token; xác nhận lỗi request.
5. Gửi token của audience khác; xác nhận response chỉ có active=false.
6. Gửi token có PII/custom claims; xác nhận projection loại bỏ claims không cần.
7. Kiểm tra qua reverse proxy; xác nhận TLS và POST body không bị log.
8. Gọi nhiều request song song; xác nhận rate limit và storage không quá tải.
9. Thay đổi allowlist/disable caller; xác nhận policy có hiệu lực theo SLA.
10. Chạy nhiều Authorization Server instance; xác nhận policy và authorization state đồng nhất.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Introspection trả 401 | Credential caller sai hoặc auth method không khớp registration. | Kiểm RegisteredClient, secret/certificate/JWT assertion và TLS. |
| Client hợp lệ nhưng token của API khác vẫn introspect được | Chỉ kiểm authentication, thiếu caller-to-token authorization. | Thêm policy audience/resource và trả inactive khi không được phép biết. |
| Mọi token đều inactive | Token không được lưu/lookup sai, authorization service khác instance hoặc token type hint xử lý sai. | Kiểm OAuth2AuthorizationService và token state. |
| Resource Server không gọi được endpoint | Sai URI, TLS, client ID/secret hoặc firewall. | Kiểm cấu hình opaque token và network. |
| Token không tồn tại trả lỗi khác token bị revoke | Error handler hoặc custom provider làm lộ trạng thái. | Chuẩn hóa response active=false. |
| Resource Server thấy quá nhiều claims | Response handler/provider trả toàn bộ claims mặc định hoặc customizer thiếu projection. | Giới hạn claim profile theo caller. |
| Client dùng GET làm token xuất hiện trong logs | SDK hoặc custom client gọi sai method. | Bắt buộc POST form-urlencoded và redaction. |
| Revoke token nhưng API vẫn chấp nhận | Cache introspection quá lâu. | Giảm TTL, invalidate cache hoặc introspect thường xuyên hơn. |
| API A dùng nhầm response cache của API B | Cache key thiếu caller/resource context. | Phân vùng cache theo issuer, token fingerprint và resource identity. |
| Custom provider không chạy | Không thay đúng provider mặc định hoặc thứ tự provider sai. | Kiểm provider list khi startup và test endpoint integration. |
| Client introspection dùng nhầm client ID của token subject | Nhầm introspection caller với issuing client. | Dùng credential riêng của Resource Server. |
| Scope introspect bị hiểu nhầm là quyền tra token | Lẫn scope token với endpoint authorization. | Xây policy riêng cho introspection caller và audience. |

## 12. Bài tập thực hành

**Bối cảnh:** Authorization Server phát token cho ba API: **inventory-api**, **billing-api** và **reporting-api**. Các API dùng opaque token introspection. Nhóm bảo mật phát hiện credential của một Resource Server có thể introspect token thuộc API khác.

Yêu cầu:

1. Đăng ký ba introspection caller riêng: **inventory-api-introspector**, **billing-api-introspector** và **reporting-introspector**.
2. Cấu hình client authentication bằng **client_secret_basic** trong môi trường test, sau đó đề xuất private_key_jwt hoặc mTLS cho production.
3. Xác định audience/resource tin cậy của từng token; không suy ra từ client ID.
4. Tạo **IntrospectionAccessPolicy** ánh xạ caller sang audience được phép.
5. Bọc **OAuth2TokenIntrospectionAuthenticationProvider** bằng provider tùy chỉnh, delegate token activity check cho provider chuẩn.
6. Khi token tồn tại nhưng caller không được phép biết, trả **active=false** không có claims khác.
7. Giữ response active chỉ chứa scope, subject, expiry và audience mà API thực sự cần.
8. Viết MockMvc test cho caller hợp lệ, caller sai credential, token không tồn tại, token expired/revoked và token của audience khác.
9. Cấu hình Spring Resource Server opaque token dùng credential riêng.
10. Thử cache introspection, revoke token, rate limit và audit; đo độ trễ cập nhật trạng thái.
11. Kiểm tra logs/APM không có raw token, secret hoặc response body.
12. Chạy qua nhiều Authorization Server instance và xác nhận allowlist/policy nhất quán.

**Tiêu chí hoàn thành:** mỗi Resource Server chỉ introspect được token trong phạm vi được cấp; caller sai credential bị 401; token không tồn tại, inactive hoặc ngoài phạm vi được trả active=false; claims được lọc; policy có test và audit.

## 13. Checklist trước khi triển khai production

- [ ] Introspection Endpoint chỉ truy cập qua HTTPS/TLS và xác minh chứng chỉ.
- [ ] Endpoint yêu cầu client authentication hoặc cơ chế authorization tương đương.
- [ ] Introspection caller là Resource Server/Protected Resource được đăng ký và có owner.
- [ ] Credential introspection tách riêng theo Resource Server, có rotation và least privilege.
- [ ] Không dùng public client **none** làm bảo vệ duy nhất cho endpoint nhạy cảm.
- [ ] Đã tách authentication caller khỏi authorization caller-to-token.
- [ ] Policy kiểm tra audience/resource, tenant, token type và claim profile.
- [ ] Không dùng scope của token để ngầm cấp quyền introspect.
- [ ] Caller không được phép biết token nhận **active=false** không kèm lý do.
- [ ] Token không tồn tại/expired/revoked cũng có response inactive tối giản.
- [ ] Client authentication sai trả lỗi phù hợp, không giả thành active=false.
- [ ] Response active chỉ chứa claims tối thiểu cần cho Resource Server.
- [ ] Response claims không tiết lộ PII hoặc metadata của resource khác.
- [ ] Token request dùng POST form-urlencoded; không truyền token qua URL.
- [ ] Có rate limit, request-size limit, timeout, audit và alert.
- [ ] Cache tôn trọng exp, revocation SLA và phân vùng theo caller/resource.
- [ ] Provider tùy chỉnh giữ delegate chuẩn để kiểm tra token activity.
- [ ] MockMvc/E2E test bao gồm credential, audience, inactive token và token enumeration.
- [ ] Logs/APM/tracing không chứa raw token, secret, assertion hoặc introspection body.
- [ ] Policy, allowlist, rollback và incident response có owner/runbook.

## Tổng kết

Token Introspection Endpoint phải được bảo vệ ở **hai lớp**. Spring Authorization Server xác thực client gọi endpoint qua client authentication filter; sau đó hệ thống cần quyết định client đó có được phép biết trạng thái và claims của token cụ thể hay không. RFC 7662 yêu cầu bảo vệ endpoint để chống token scanning và khuyến nghị chỉ cho Protected Resource được ủy quyền gọi introspection.

Với Spring Authorization Server, **OAuth2TokenIntrospectionEndpointConfigurer** cho phép tùy chỉnh converter, provider và response handler. Có thể bọc **OAuth2TokenIntrospectionAuthenticationProvider** để thêm policy dựa trên client đã xác thực và audience/resource của token, rồi delegate việc xác định token active cho provider chuẩn. Khi caller không được phép biết token, response cần là **active=false** tối giản, tránh tiết lộ token có tồn tại hay không.

Phân quyền introspection không thay thế kiểm tra scope/audience/tenant tại Resource Server. Hệ thống production cần credential riêng, TLS, least privilege, claim projection, rate limiting, cache có giới hạn, audit không chứa raw token và kiểm thử chống token enumeration.

## Tài liệu tham khảo

1. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): endpoint authorization, introspection request/response, active=false, privacy, caching và TLS.
2. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth2TokenIntrospectionEndpointConfigurer và các extension point.
3. [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospectionAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationProvider.html): provider chuẩn, RegisteredClientRepository và OAuth2AuthorizationService.
4. [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospectionAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationToken.html): token, client principal, token type hint và additional parameters.
5. [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospection API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2TokenIntrospection.html): representation của introspection response.
6. [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): client authentication filter và cấu hình Authorization Server.
7. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClientRepository, OAuth2AuthorizationService và authorization data.
8. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình introspection-uri và credential phía Resource Server.
9. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication và HTTP authorization errors.
10. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): sử dụng Bearer access token.

