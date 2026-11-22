# Tích hợp service-to-service bằng Client Credentials

## 1. Bối cảnh và mục tiêu

Trong hệ thống microservices, nhiều request được gửi bởi một ứng dụng hoặc workload thay vì một người dùng đang đăng nhập. Ví dụ: service Billing gọi Inventory API để giữ hàng; một job worker chạy ban đêm đọc dữ liệu báo cáo; service Notification gửi yêu cầu tới Communication API. Các thành phần này cần một danh tính máy-máy (machine identity) và quyền truy cập có giới hạn.

OAuth 2.0 **Client Credentials Grant** được thiết kế cho trường hợp confidential client tự đại diện cho chính nó khi truy cập resource. Client xác thực với Authorization Server bằng credential của client, nhận access token và gửi token đó tới Resource Server. Không có bước redirect browser, không có resource owner đăng nhập và không có consent screen tương tác trong flow này.

Ví dụ xuyên suốt:

- `billing-service` là OAuth client.
- `inventory-api` là Resource Server.
- Authorization Server chạy tại `https://auth.example.com`.
- Billing chỉ được đọc tồn kho và giữ hàng trong phạm vi API được cấp quyền.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as billing-service
    participant AS as Authorization Server
    participant I as inventory-api
    B->>AS: POST /oauth2/token (client authentication + grant_type)
    AS->>AS: Xác thực client và kiểm tra grant/scope
    AS-->>B: access_token + token_type + expires_in
    B->>I: GET /inventory (Authorization: Bearer token)
    I->>I: Xác minh token, audience và scope
    I-->>B: 200 OK + inventory data
~~~

Sau bài học, bạn có thể:

1. Phân biệt machine identity với user identity.
2. Mô tả chính xác Client Credentials Grant và giới hạn của nó.
3. Đăng ký confidential client trong Spring Authorization Server.
4. Cấu hình client authentication, grant type, scope và token lifetime.
5. Phát hành JWT access token có audience phù hợp với API.
6. Cấu hình Resource Server xác minh issuer, audience và scope.
7. Dùng Spring Security OAuth2 Client để lấy và quản lý access token.
8. Cache token đúng cách và tránh gọi token endpoint cho mỗi API request.
9. Xử lý secret rotation, token expiry, lỗi xác thực và retry.
10. Kiểm thử toàn bộ service-to-service flow và vận hành an toàn.

**Phạm vi phiên bản:** Ví dụ tham chiếu Spring Authorization Server 1.5.8, Spring Security 6.x và Spring Boot 3.x. Một số API tích hợp OAuth2 Client thay đổi theo minor version; hãy đối chiếu dependency version của ứng dụng khi triển khai.

## 2. Client Credentials Grant hoạt động thế nào?

### 2.1. Các vai trò

| Vai trò | Thành phần trong ví dụ | Trách nhiệm |
| --- | --- | --- |
| OAuth client | `billing-service` | Xác thực bằng client credential và yêu cầu access token. |
| Authorization Server | `auth.example.com` | Xác thực client, kiểm tra quyền và phát hành token. |
| Resource Server | `inventory-api` | Xác minh token và quyết định request có được phép hay không. |
| Resource owner | Không tham gia trực tiếp | Flow này không đại diện cho một user đang đăng nhập. |

Client Credentials chỉ dành cho confidential client có khả năng giữ credential an toàn. Không nhúng client secret vào mobile app, SPA hoặc binary phân phối cho người dùng cuối.

### 2.2. Request tới Token Endpoint

Client gửi request tới Token Endpoint, thường là `POST /oauth2/token`, với:

- Client authentication theo phương thức đã đăng ký.
- `grant_type=client_credentials`.
- `scope` tùy chọn, nếu client cần một tập quyền cụ thể.

Ví dụ dùng HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

HTTP Basic là cách biểu diễn credential trong request; luôn dùng TLS. Không ghi header Authorization hoặc client secret vào access log, trace hay exception message.

### 2.3. Token response

Một response thành công có dạng:

~~~json
{
  "access_token": "eyJraWQiOiJrZXktMjAyNi0wMSIs...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

`expires_in` biểu diễn lifetime của access token tính bằng giây. Client phải dùng token trước thời điểm hết hạn và yêu cầu token mới khi cần.

Client Credentials Grant không phát hành refresh token theo RFC 6749. Khi access token hết hạn, client xác thực lại với Token Endpoint để lấy token mới.

### 2.4. Không có user trong flow

Token đại diện cho client/workload, không phải user. Vì vậy:

- Không dùng flow này để thay thế Authorization Code + PKCE cho người dùng.
- Không tự gắn user identity vào token chỉ vì request ban đầu được kích hoạt bởi user.
- Không suy ra user hiện tại từ client ID.
- Nếu nghiệp vụ cần cả user và service identity, hãy thiết kế token exchange/on-behalf-of theo authorization model phù hợp thay vì giả vờ Client Credentials là user delegation.

Resource Server có thể nhận biết client bằng claim `client_id` hoặc subject tùy token profile, nhưng phải xác định rõ semantics của token được phát hành. Nếu áp dụng JWT Access Token Profile tại RFC 9068 cho Client Credentials, `sub` xác định client và `client_id` là claim bắt buộc; hãy giữ đúng semantics đó ở cả issuer lẫn API.

## 3. Đăng ký confidential client trong Spring Authorization Server

### 3.1. RegisteredClient

Spring Authorization Server lưu client metadata qua `RegisteredClientRepository`. Một client Credentials registration thường cần:

- Client ID ổn định.
- Client secret đã encode hoặc cơ chế xác thực mạnh hơn.
- Client authentication method.
- Authorization grant type `client_credentials`.
- Các scope được phép.
- Token settings, bao gồm access token time-to-live.

Ví dụ tạo client:

~~~java
RegisteredClient billingClient = RegisteredClient.withId(UUID.randomUUID().toString())
    .clientId("billing-service")
    .clientSecret(passwordEncoder.encode(configuredClientSecret))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("inventory.read")
    .scope("inventory.reserve")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(false)
        .build())
    .build();

registeredClientRepository.save(billingClient);
~~~

`configuredClientSecret` phải đến từ secret manager hoặc provisioning process an toàn. Không hard-code secret vào source code hoặc commit file cấu hình chứa giá trị thật. `PasswordEncoder` cần cùng thuật toán/strength policy mà server dùng để xác thực client secret.

### 3.2. Vì sao dùng client_secret_basic?

Các client authentication method thường gặp:

| Phương thức | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| `client_secret_basic` | Client ID/secret trong HTTP Basic Authorization. | Confidential service có secret được quản lý an toàn. |
| `client_secret_post` | Client ID/secret trong form body. | Chỉ dùng khi có lý do tương thích; credential có thể dễ bị ghi log cùng body. |
| `private_key_jwt` | Client ký JWT assertion bằng private key. | Workload có key management tốt và cần tránh shared secret. |
| `tls_client_auth` | Xác thực client bằng certificate ở TLS layer. | Hạ tầng hỗ trợ mutual TLS và certificate lifecycle. |

Chọn phương thức mà Authorization Server và client đều hỗ trợ. Với hệ thống có HSM/KMS hoặc workload identity, `private_key_jwt` hay mutual TLS có thể phù hợp hơn shared secret.

### 3.3. Client ID phải định danh workload

Không dùng chung một client ID cho mọi service nếu các service có quyền khác nhau. Ví dụ:

| Client | Scope được cấp |
| --- | --- |
| `billing-service` | `inventory.read`, `inventory.reserve` |
| `reporting-worker` | `inventory.read`, `reports.export` |
| `notification-service` | `notifications.send` |

Nếu mọi service dùng chung credential, một service bị compromise có thể có toàn bộ quyền của các service khác. Tách client identity giúp giới hạn blast radius và hỗ trợ audit.

### 3.4. Scope là giới hạn quyền tối đa

Danh sách scope trong RegisteredClient xác định tập quyền client có thể yêu cầu. Client chỉ nên nhận scope cần thiết cho công việc.

Authorization Server phải từ chối scope không được đăng ký. Resource Server tiếp tục kiểm tra scope trên từng endpoint; việc token có scope không có nghĩa mọi endpoint đều chấp nhận nó.

Không cấp `admin`, `*` hoặc scope tổng quát cho tiện triển khai. Tạo scope theo API/resource/action có ý nghĩa, ví dụ `inventory.read`, `inventory.reserve`, `invoice.issue`.

## 4. Cấu hình Authorization Server

### 4.1. Endpoint và core services

Spring Authorization Server xử lý Client Credentials thông qua Token Endpoint và các core components:

- `RegisteredClientRepository`: tìm client và cấu hình client.
- `OAuth2AuthorizationService`: lưu authorization/token state nếu cấu hình cần persistence.
- `OAuth2TokenGenerator`: tạo access token.
- `OAuth2AuthorizationServerSettings`: cấu hình issuer và endpoint.

Trong production, dùng persistent repository phù hợp với deployment; in-memory repository phù hợp cho thử nghiệm hoặc demo đơn giản. Nhiều instance phải chia sẻ durable client/token state theo thiết kế.

### 4.2. SecurityFilterChain cho Authorization Server

Một cấu hình cơ bản có thể dùng configurer của Spring Authorization Server:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, Customizer.withDefaults());

    return http.build();
}
~~~

Đây là phần minh họa cho filter chain xử lý endpoint của Authorization Server. Ứng dụng thực tế còn cần cấu hình authentication, exception handling, JWK source, issuer, các endpoint và filter chain cho phần ứng dụng khác.

### 4.3. Cấu hình issuer và token endpoint

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .tokenEndpoint("/oauth2/token")
        .build();
}
~~~

Issuer phải ổn định và khớp discovery metadata cũng như claim `iss` trong token. Không tạo issuer từ Host header không đáng tin cậy.

### 4.4. JWT access token và audience

JWT access token có thể được Resource Server xác minh cục bộ bằng chữ ký và claims. Một claim quan trọng là `aud` (audience), xác định resource server/API mà token hướng tới.

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "billing-service",
  "aud": ["inventory-api"],
  "client_id": "billing-service",
  "scope": "inventory.read inventory.reserve",
  "iat": 1794850000,
  "exp": 1794850300
}
~~~

Không mặc định mọi access token đều tự có audience đúng theo API. Cần xác định audience policy và bảo đảm Resource Server kiểm tra nó.

### 4.5. Thêm audience và client_id cho JWT access token

Với JWT access token, có thể dùng `OAuth2TokenCustomizer<JwtEncodingContext>`:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            RegisteredClient client = context.getRegisteredClient();
            context.getClaims().claim("client_id", client.getClientId());

            if (client.getClientId().equals("billing-service")) {
                context.getClaims().audience(List.of("inventory-api"));
            }
        }
    };
}
~~~

Đây là ví dụ policy nhỏ. Với nhiều client/API, hãy quản lý mapping client-scope-audience bằng cấu hình hoặc policy service. Không cho client tự gửi một audience bất kỳ rồi đưa thẳng vào token.

Nếu một client có quyền gọi nhiều API, chỉ đưa audience của resource thực sự được yêu cầu/được phép vào token. Có thể phát token riêng cho từng audience để giảm khả năng token bị dùng nhầm API.

### 4.6. Tenant claim khi service hoạt động theo tenant

Nếu mỗi workload được giới hạn vào tenant cụ thể, tenant binding phải đến từ client registration hoặc policy đáng tin cậy. Không lấy `tenant_id` tùy ý từ request token endpoint.

Ví dụ customizer có thể đọc metadata đã được quản trị trong client registration hoặc service mapping:

~~~java
context.getClaims().claim("tenant_id", tenantPolicy.tenantFor(client.getId()));
~~~

Đây là pseudocode; `tenantPolicy` phải là nguồn cấu hình tin cậy. Resource Server phải xác minh tenant claim khớp tenant của resource đang truy cập.

### 4.7. JWT hay opaque access token?

| Tiêu chí | JWT | Opaque token |
| --- | --- | --- |
| Validation | Resource Server xác minh chữ ký và claims. | Resource Server introspect với Authorization Server. |
| Network dependency | Không cần introspection cho mỗi request. | Cần introspection hoặc cache kết quả. |
| Revocation | JWT đã phát hành có thể còn hợp lệ đến `exp` nếu API chỉ validate local. | Authorization Server có thể phản ánh trạng thái token qua introspection. |
| Payload | Claims có thể đọc được, không được coi là bí mật. | Không lộ claims cho client/API nếu chưa introspect. |
| Phân tán | API có thể validate độc lập nếu có JWKS. | API phụ thuộc availability/latency của introspection endpoint. |

JWT không được mã hóa chỉ vì nó được ký. Không đặt secret, private data hoặc thông tin không cần thiết trong claims.

## 5. Resource Server bảo vệ API

### 5.1. Xác minh issuer và chữ ký

Inventory API phải xác minh token được phát hành bởi Authorization Server tin cậy. Với Spring Boot, có thể cấu hình issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

Spring Security dùng issuer metadata/JWKS để cấu hình JWT decoder và xác minh issuer, chữ ký cùng các validator mặc định phù hợp.

### 5.2. Opaque token và introspection

Nếu Authorization Server phát hành opaque access token, Resource Server cần introspect token. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: inventory-api-introspector
          client-secret: ${INVENTORY_INTROSPECTION_SECRET}
~~~

Credential trong cấu hình này là credential riêng để Inventory API gọi introspection endpoint. Nó không nhất thiết là client credential `billing-service` đã dùng để lấy access token. Chỉ cấp quyền introspection cần thiết và bảo vệ secret bằng secret manager.

Kết quả introspection cung cấp trạng thái token và các thuộc tính như scope, client và audience tùy token profile. Resource Server vẫn phải kiểm tra scope/audience/tenant policy sau khi xác nhận token active.

### 5.3. Kiểm tra audience

Issuer hợp lệ chưa đủ. Token dành cho `billing-api` không nên được chấp nhận ở `inventory-api` chỉ vì cùng do một Authorization Server phát hành.

Ví dụ validator:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com";
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("inventory-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null);
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
    return decoder;
}
~~~

Ví dụ kiểm tra audience cụ thể cho Inventory API. Trong ứng dụng có nhiều Resource Server, mỗi API phải cấu hình audience riêng. Không dùng một audience chung cho mọi API nếu mục tiêu là giới hạn token theo resource.

### 5.4. Kiểm tra scope

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/inventory/**")
                .hasAuthority("SCOPE_inventory.read")
            .requestMatchers(HttpMethod.POST, "/inventory/reservations")
                .hasAuthority("SCOPE_inventory.reserve")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

Spring Security ánh xạ scope thành authority có prefix `SCOPE_` theo cấu hình mặc định. Nếu thay đổi authority converter, phải đồng bộ cách kiểm tra quyền trong endpoint/method security.

### 5.5. Kết hợp scope với tenant authorization

Scope chỉ mô tả quyền ở mức API/action. Nếu resource thuộc tenant cụ thể, API phải xác minh tenant claim và tenant ownership của resource.

~~~java
@PreAuthorize("hasAuthority('SCOPE_inventory.read')")
public Inventory findInventory(String tenantId, String sku) {
    String tokenTenant = currentJwt().getClaimAsString("tenant_id");
    if (!tenantId.equals(tokenTenant)) {
        throw new AccessDeniedException("Tenant mismatch");
    }
    return inventoryRepository.findByTenantIdAndSku(tenantId, sku);
}
~~~

Đây là pseudocode cho tenant authorization. Phải bảo đảm repository query luôn có tenant predicate, kể cả khi method authorization đã kiểm tra claim.

## 6. Tích hợp OAuth2 Client trong service gọi API

### 6.1. Khai báo client registration

Service Billing cần biết Token Endpoint, client ID, secret, grant type, authentication method và scope. Với Spring Boot, có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: platform-auth
            client-id: billing-service
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
              - inventory.reserve
        provider:
          platform-auth:
            token-uri: https://auth.example.com/oauth2/token
~~~

Trong file cấu hình thực tế, dùng placeholder environment/secret manager trỏ tới biến môi trường `INVENTORY_CLIENT_SECRET`. Giá trị secret thật không được lưu trong repository. Với production, cân nhắc secret manager, workload identity, private_key_jwt hoặc mTLS.

### 6.2. OAuth2AuthorizedClientManager

`OAuth2AuthorizedClientManager` điều phối việc lấy và lưu authorized client/access token. Với service-to-service, có thể dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, authorizedClients);

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Provider hỗ trợ Client Credentials và manager dùng `OAuth2AuthorizedClientService` để lưu token theo client registration/principal. Có thể dùng implementation in-memory cho service đơn giản hoặc persistence phù hợp với môi trường chạy.

### 6.3. Lấy token và gọi API

~~~java
@Service
public class InventoryGateway {

    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final RestClient restClient;

    public InventoryGateway(
            OAuth2AuthorizedClientManager authorizedClientManager,
            RestClient.Builder restClientBuilder) {
        this.authorizedClientManager = authorizedClientManager;
        this.restClient = restClientBuilder
            .baseUrl("https://inventory.example.com")
            .build();
    }

    public Inventory getInventory(String sku) {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest.withClientRegistrationId("inventory-service")
                .principal("billing-service")
                .build();

        OAuth2AuthorizedClient authorizedClient =
            authorizedClientManager.authorize(authorizeRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Could not obtain inventory access token");
        }

        String token = authorizedClient.getAccessToken().getTokenValue();

        return restClient.get()
            .uri("/inventory/{sku}", sku)
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(Inventory.class);
    }
}
~~~

`principal("billing-service")` là tên principal kỹ thuật dùng để lưu authorized client; nó không biến request thành user login. Dùng một principal name ổn định cho workload để token được tái sử dụng theo đúng registration/principal key.

Trong ứng dụng thực tế, nên đóng gói logic lấy token vào một gateway/interceptor dùng chung thay vì lặp lại trong mọi method. Không log giá trị token.

### 6.4. Lưu token phía client

`OAuth2AuthorizedClientService` lưu authorized client và access token. Khi token hết hạn hoặc cần cấp token mới, Client Credentials provider xác thực lại với Token Endpoint bằng client authentication. Đây là lần cấp token mới, không phải sử dụng refresh token.

Nếu dùng in-memory service:

- Token mất khi process restart.
- Mỗi instance có cache riêng.
- Nhiều instance có thể cùng gọi Token Endpoint.

Điều này có thể chấp nhận cho workload đơn giản. Với hệ thống scale lớn, hãy cân nhắc token cache chia sẻ hoặc thiết kế token acquisition riêng có kiểm soát; không chia sẻ token nếu các instance có credential/tenant/audience khác nhau.

### 6.5. Tích hợp RestClient interceptor

Spring Security cung cấp các integration để gắn OAuth2 authorized client vào HTTP client. Với version hỗ trợ `OAuth2ClientHttpRequestInterceptor`, có thể cấu hình interceptor để chọn client registration và principal cho từng request.

Nếu dùng interceptor, kiểm tra registration ID được chọn đúng, principal name ổn định, token chỉ gửi tới trusted destination, không tự forward inbound user bearer token và không để redirect gửi Authorization header sang host khác.

Nếu version Spring Security của ứng dụng chưa có interceptor tương ứng, có thể dùng manager trực tiếp như ví dụ trước hoặc viết interceptor nhỏ gọi manager.

## 7. Cache token và quản lý vòng đời

### 7.1. Không yêu cầu token cho mọi API request

Một lỗi thường gặp là gọi Token Endpoint trước mỗi request tới Resource Server. Cách đó tăng latency, tải Authorization Server và dễ gây rate spike khi nhiều request đồng thời.

Client nên tái sử dụng access token cho đến gần thời điểm hết hạn. `OAuth2AuthorizedClientManager` có thể quản lý việc authorize và lưu token theo registration/principal.

### 7.2. Cache key của token

Nếu tự xây token cache, key phải bao gồm mọi yếu tố làm thay đổi quyền của token:

~~~text
token-cache:{issuer}:{client-registration}:{principal}:{audience}:{scope-set}:{tenant}
~~~

Không dùng một cache entry cho các scope/audience/tenant khác nhau. Canonicalize scope set trước khi tạo key. Không dùng raw client secret hoặc raw access token làm cache key.

### 7.3. Làm mới trước expiry

Token cache nên tính thời điểm hết hạn từ `expires_in`/`expiresAt` và làm mới sớm một khoảng an toàn để tránh request sử dụng token vừa hết hạn do clock skew hoặc network latency.

Ví dụ policy: token lifetime 5 phút, bắt đầu lấy token mới khi còn 30 giây và thêm jitter nhỏ để các instance không refresh đồng loạt. Đây là giá trị minh họa; cần đồng bộ clock và chọn skew theo latency, clock drift và token lifetime.

### 7.4. Chống token request stampede

Khi token hết hạn, hàng trăm request có thể cùng yêu cầu token mới. Cần single-flight/mutex theo cache key, chỉ một request lấy token mới, timeout và bounded retry cho Token Endpoint, backoff có jitter và giới hạn số lần retry.

Không retry `invalid_client`, `unauthorized_client` hoặc `invalid_scope` như lỗi mạng. Đây là lỗi cấu hình/credential cần alert và xử lý.

### 7.5. Token cache và multi-instance

Không nhất thiết phải chia sẻ access token giữa các instance. Một số hệ thống chọn mỗi instance tự lấy token và giữ cache local vì token lifetime ngắn, giảm rủi ro token bị chia sẻ rộng. Nếu dùng shared cache, bảo vệ quyền đọc, mã hóa at-rest khi phù hợp và đảm bảo namespace theo client/tenant/audience/scope.

Khi client secret rotate hoặc client bị disable, cần xóa authorized client/token cache và ngăn token endpoint tiếp tục được gọi bằng credential cũ.

## 8. Bảo vệ client credential

### 8.1. Secret lifecycle

Client secret là credential dài hạn để lấy access token. Cần:

- Sinh secret bằng cryptographically secure random generator.
- Lưu secret trong secret manager/vault.
- Không commit vào Git, image hoặc log.
- Giới hạn quyền đọc secret theo workload identity.
- Có quy trình rotate và revoke.
- Không gửi secret qua chat/email hoặc ticket không bảo vệ.
- Dùng TLS tới Token Endpoint.

Authorization Server chỉ cần lưu password hash/encoded secret phù hợp với PasswordEncoder; không cần khả năng đọc lại plaintext secret.

### 8.2. Rotation không gián đoạn

Một quy trình rotation:

1. Tạo credential mới hoặc client registration mới theo khả năng hệ thống.
2. Cập nhật secret manager cho workload.
3. Rollout service caller và xác nhận lấy token bằng credential mới.
4. Theo dõi `invalid_client` và token issuance.
5. Revoke secret cũ sau khi mọi instance đã chuyển.
6. Evict token cache/authorized client cache cũ.

Nếu framework/storage chỉ hỗ trợ một secret active tại một thời điểm, có thể dùng hai client registration trong giai đoạn chuyển tiếp để không phải rotate đồng loạt.

### 8.3. Client authentication mạnh hơn

Với hệ thống production nhạy cảm:

- `private_key_jwt` tránh phân phối shared secret, nhưng cần bảo vệ private key và quản lý public JWK.
- Mutual TLS gắn client authentication với certificate và có thể hỗ trợ certificate-bound access token nếu cả Authorization Server và Resource Server được cấu hình phù hợp.
- Workload identity của cloud/platform có thể cấp credential ngắn hạn hoặc ký assertion thay cho secret tĩnh.

Chỉ bật phương thức mà cả client, Authorization Server và hạ tầng hỗ trợ đầy đủ. Cần kiểm thử certificate rotation, key compromise và client disable.

### 8.4. Không dùng Client Credentials để impersonate user

Nếu Billing service xử lý đơn hàng do Alice tạo, access token Client Credentials vẫn đại diện cho Billing service. Nếu Inventory API cần biết Alice là người dùng và kiểm tra quyền của Alice, cần một delegation design:

- Authorization Code Flow để client lấy token theo user.
- Token Exchange/on-behalf-of nếu Authorization Server hỗ trợ và policy cho phép.
- Truyền business actor context đã được xác thực riêng, không giả mạo `sub` trong client token.

Ghi audit có thể lưu cả service principal và business actor, nhưng không được trộn hai danh tính trong cùng semantics của token.

## 9. Bảo mật token và API

### 9.1. Bearer token là credential

Ai có bearer token đều có thể sử dụng token cho tới khi token hết hạn hoặc bị vô hiệu hóa theo cơ chế được áp dụng. Do đó:

- Chỉ gửi qua HTTPS.
- Đặt trong `Authorization: Bearer`.
- Không đưa vào URL query parameter.
- Không log token trong request/response body.
- Không gửi tới host không tin cậy.
- Không lưu trong browser storage.

### 9.2. Audience restriction

Token nên chỉ dành cho API cần sử dụng. Nếu Billing lấy token cho Inventory API, token không nên tự động dùng được ở Payments API. Resource Server phải xác minh `aud`, không chỉ kiểm tra chữ ký và issuer.

### 9.3. Scope restriction

Client chỉ yêu cầu scope đã được cấp. Resource Server map scope thành authority và kiểm tra từng endpoint. Không tin scope do caller tự gửi trong HTTP request.

### 9.4. Token lifetime và revocation

Access token Client Credentials nên có lifetime ngắn phù hợp với risk và operational cost. JWT self-contained có thể vẫn được Resource Server chấp nhận tới `exp` nếu API chỉ xác minh chữ ký local, dù client đã bị disable ở Authorization Server.

Nếu cần revoke ngay, dùng opaque token và introspection, denylist/revocation lookup ở Resource Server, token version/workload state check hoặc JWT lifetime ngắn với cửa sổ tồn tại tối đa đã xác định.

Không tuyên bố disable client tự động vô hiệu hóa mọi JWT đã phát hành.

### 9.5. Rate limit và abuse control

Token Endpoint cần rate limit theo client, IP, tenant và authentication outcome. Theo dõi các client gửi token request bất thường, invalid credential hoặc scope ngoài policy.

Resource Server cũng cần rate limit theo client/workload và business operation; scope không thay thế quota.

## 10. Xử lý lỗi

### 10.1. Lỗi ở Token Endpoint

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `invalid_client` | Client ID/secret sai, client bị disable hoặc authentication method không khớp. | Kiểm tra secret manager, registration và auth method; không retry liên tục. |
| `unauthorized_client` | Client không được phép dùng grant Client Credentials. | Bổ sung grant đúng nếu policy cho phép. |
| `invalid_scope` | Scope không được đăng ký hoặc không được cấp. | Sửa client registration/request scope. |
| `unsupported_grant_type` | Sai grant type hoặc server không bật provider. | Kiểm tra `grant_type=client_credentials` và server configuration. |
| `invalid_request` | Form thiếu/sai parameter hoặc Content-Type. | Gửi POST form-urlencoded theo chuẩn. |
| HTTP 429 | Rate limit/quota. | Backoff có jitter và giảm request rate. |
| HTTP 5xx/network timeout | Authorization Server hoặc network tạm thời lỗi. | Retry có giới hạn; giữ token còn hạn nếu policy cho phép. |

### 10.2. Lỗi ở Resource Server

| HTTP status | Ý nghĩa thường gặp | Cách kiểm tra |
| --- | --- | --- |
| 401 Unauthorized | Token thiếu, sai chữ ký, issuer, expiry hoặc malformed. | Kiểm tra token, clock, issuer và JWKS. |
| 403 Forbidden | Token hợp lệ nhưng thiếu scope/authority hoặc tenant permission. | Kiểm tra scope, audience, tenant và authorization policy. |
| 404 Not Found | Resource không tồn tại hoặc API che giấu resource ngoài tenant. | Kiểm tra tenant-scoped lookup. |
| 429 Too Many Requests | Client vượt quota/rate limit. | Kiểm tra client identity và retry-after. |
| 5xx | Lỗi xử lý API hoặc dependency. | Correlation ID, trace và dependency health. |

Không tự động lấy token mới khi Resource Server trả 403 do thiếu quyền. Token mới với cùng client/scope policy sẽ không giải quyết được authorization failure.

### 10.3. Retry policy

Chỉ retry lỗi tạm thời như timeout, connection reset, 429 hoặc 5xx theo policy. Với `invalid_client`, `invalid_scope`, `unauthorized_client` và token signature failure, dừng retry và phát cảnh báo.

Không retry API mutation không idempotent nếu chưa có idempotency key hoặc cơ chế chống xử lý lặp.

## 11. Kiểm thử end-to-end

### 11.1. Kiểm thử Token Endpoint

~~~bash
curl --request POST \
  --url https://auth.example.com/oauth2/token \
  --user "$CLIENT_ID:$CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=inventory.read"
~~~

Trong shell thực tế, lấy credential từ secret manager hoặc môi trường test an toàn. Không bật shell tracing (`set -x`) khi command chứa secret.

### 11.2. Kiểm thử API

~~~bash
curl --request GET \
  --url https://inventory.example.com/inventory/SKU-123 \
  --header "Authorization: Bearer $ACCESS_TOKEN"
~~~

Kiểm thử cả token hợp lệ đúng issuer/audience/scope, token thiếu scope, sai audience, sai issuer/chữ ký, hết hạn, tenant A truy cập resource tenant B và request không có token.

### 11.3. Unit test RegisteredClient

Kiểm tra grant Client Credentials, client authentication method, secret encoding, scope được phê duyệt, access token TTL và việc client không có grant không cần thiết.

### 11.4. Integration test Authorization Server

Dùng HTTP client test hoặc Spring Boot integration test để xác nhận:

1. Client hợp lệ lấy token thành công.
2. Client secret sai nhận `invalid_client`.
3. Client không được đăng ký Client Credentials bị từ chối.
4. Scope ngoài allow-list bị từ chối.
5. JWT chứa issuer, audience, client ID và scope đúng.
6. Token được lưu/tra cứu đúng nếu authorization persistence được bật.
7. Secret rotation khiến credential cũ bị từ chối theo kế hoạch.

### 11.5. Integration test Resource Server

Kiểm tra issuer, signature, `exp`/`nbf`, audience, scope mapping, tenant claim và opaque token introspection nếu dùng opaque access token.

### 11.6. Kiểm thử tải và concurrency

Mô phỏng nhiều request đồng thời từ cùng client khi token sắp hết hạn. Đo số lần gọi Token Endpoint, cache hit ratio, token acquisition latency, API p95/p99 latency, tỷ lệ 401 do token expiry và hành vi khi Authorization Server unavailable.

Kết quả mong đợi là một lần token acquisition cho mỗi cache key trong cửa sổ refresh, không phải một token request cho mỗi API call.

## 12. Observability và vận hành

### 12.1. Metrics

Theo dõi số token request theo client/grant/result; tỷ lệ `invalid_client`, `invalid_scope` và `unauthorized_client`; token issuance latency; access token lifetime; OAuth2 client cache hit/miss; Resource Server 401/403; JWKS refresh/error; credential rotation age và rate limit.

Không đưa raw client ID không kiểm soát cardinality, secret, token, subject hoặc claims nhạy cảm vào metric label. Dùng identifier được phân loại và log có kiểm soát.

### 12.2. Audit

Audit event nên cho biết client nào đã yêu cầu token, grant type và scope được cấp, audience nếu policy cho phép, tenant context, kết quả authentication, thời gian và correlation ID. Không ghi access token hoặc client secret vào audit log.

### 12.3. Availability và dependency

Client Credentials phụ thuộc Authorization Server khi cần token mới. Nếu Authorization Server unavailable, client có thể tiếp tục dùng access token còn hạn; không dùng token đã hết hạn chỉ để duy trì availability. Dùng timeout, retry có giới hạn, circuit breaker/bulkhead cho Token Endpoint. Resource Server có thể tiếp tục xác minh JWT local nếu JWKS đã cache hợp lệ; với opaque token, introspection dependency phải nằm trong availability budget.

### 12.4. Secret và key rotation vận hành

Có lịch rotate client secret/private key/certificate, theo dõi credential age, kiểm tra rollout hoàn tất và revoke credential cũ. Signing key của Authorization Server là lifecycle khác với client credential; rotation signing key phải cập nhật JWKS và bảo đảm Resource Server xử lý key overlap đúng.

## 13. Các lỗi thường gặp

### Lỗi 1: Dùng Client Credentials cho user login

**Triệu chứng:** API không biết user nào thực hiện hành động hoặc mọi hành động đều có cùng client identity.

**Nguyên nhân:** Nhầm machine identity với resource owner identity.

**Cách xử lý:** Dùng Authorization Code + PKCE hoặc delegation/token exchange phù hợp.

### Lỗi 2: Dùng chung client ID/secret cho mọi service

**Triệu chứng:** Không phân biệt được service gây request và không giới hạn blast radius.

**Nguyên nhân:** Dùng một credential cho nhiều workload.

**Cách xử lý:** Một client identity cho từng workload hoặc trust boundary, scope riêng.

### Lỗi 3: Lưu secret trong source code

**Triệu chứng:** Secret xuất hiện trong Git history, image hoặc log.

**Nguyên nhân:** Hard-code credential.

**Cách xử lý:** Secret manager, rotation và quyền đọc theo workload identity.

### Lỗi 4: Không kiểm tra audience

**Triệu chứng:** Token dành cho API A được chấp nhận ở API B.

**Nguyên nhân:** Chỉ xác minh issuer và chữ ký.

**Cách xử lý:** Phát hành audience phù hợp và validator riêng ở mỗi Resource Server.

### Lỗi 5: Cấp scope quá rộng

**Triệu chứng:** Một service chỉ cần đọc nhưng có thể ghi hoặc xóa.

**Nguyên nhân:** Dùng wildcard/admin scope.

**Cách xử lý:** Least privilege và endpoint-level authority checks.

### Lỗi 6: Gọi Token Endpoint mỗi request

**Triệu chứng:** Token endpoint tải cao và API latency tăng.

**Nguyên nhân:** Không cache authorized client/access token.

**Cách xử lý:** Dùng OAuth2AuthorizedClientManager hoặc token cache có expiry.

### Lỗi 7: Token cache key thiếu scope/audience

**Triệu chứng:** Service dùng token có quyền hoặc audience không đúng request.

**Nguyên nhân:** Cache theo client ID duy nhất.

**Cách xử lý:** Namespace cache theo issuer, client registration, principal, scope, audience và tenant.

### Lỗi 8: Retry lỗi credential

**Triệu chứng:** Token Endpoint bị spam bởi client secret sai.

**Nguyên nhân:** Retry mọi HTTP status như lỗi mạng.

**Cách xử lý:** Chỉ retry lỗi transient; lỗi OAuth client phải dừng và alert.

### Lỗi 9: Cho rằng disable client thu hồi JWT ngay

**Triệu chứng:** API vẫn chấp nhận JWT cũ.

**Nguyên nhân:** Resource Server xác minh JWT local và token chưa hết hạn.

**Cách xử lý:** Opaque/introspection, denylist hoặc TTL ngắn theo yêu cầu.

### Lỗi 10: Gửi bearer token tới host ngoài ý muốn

**Triệu chứng:** Token bị lộ khi HTTP client theo redirect hoặc gọi nhầm base URL.

**Nguyên nhân:** Không giới hạn destination và redirect behavior.

**Cách xử lý:** HTTPS, allow-list host, kiểm soát redirect và không forward Authorization header qua origin khác.

## 14. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Client identity | Mỗi workload có client identity riêng theo quyền và trust boundary? |
| Grant | Chỉ bật `client_credentials` khi đúng use case? |
| Authentication | Basic secret, private_key_jwt hoặc mTLS phù hợp? |
| Secret storage | Secret nằm trong secret manager, không ở source/image/log? |
| Secret encoding | Authorization Server lưu secret đã encode? |
| Scope | Scope theo least privilege và được kiểm tra ở API? |
| Audience | Token chỉ dành cho đúng Resource Server? |
| Issuer | Resource Server xác minh issuer và chữ ký? |
| Tenant | Tenant binding lấy từ nguồn tin cậy và được kiểm tra tại API? |
| Token lifetime | TTL ngắn phù hợp risk/latency? |
| Refresh | Không giả định Client Credentials có refresh token? |
| Token cache | Reuse token, refresh sớm và chống stampede? |
| Cache key | Bao gồm issuer/client/principal/scope/audience/tenant? |
| Retry | Retry có giới hạn, phân biệt lỗi credential với transient? |
| Rotation | Có rollout và revoke credential cũ? |
| Revocation | Có policy cho JWT còn hiệu lực sau disable/revoke? |
| TLS | Token Endpoint và Resource Server chỉ dùng HTTPS? |
| Logging | Không log secret/access token/Authorization header? |
| Audit | Có client, scope, grant, result và correlation ID? |
| Availability | Có timeout, circuit breaker và dependency SLO? |
| Tests | Có test sai issuer/audience/scope/tenant và secret rotation? |

## 15. Bài tập thực hành

Một hệ thống thương mại điện tử có ba service:

- `billing-service` cần đọc tồn kho và tạo reservation.
- `reporting-worker` chỉ đọc dữ liệu để xuất báo cáo.
- `notification-service` chỉ gửi thông báo.

Authorization Server phát JWT access token. Inventory API và Notification API là Resource Server độc lập. Hệ thống chạy nhiều instance và cần chịu được Authorization Server gián đoạn ngắn.

Hãy thực hiện:

1. Tạo ba RegisteredClient với client ID, secret và scope riêng.
2. Chọn client authentication method và giải thích vì sao.
3. Cấu hình Client Credentials Grant và access token TTL.
4. Phát JWT chứa issuer, audience, client ID và scope phù hợp.
5. Cấu hình audience riêng cho Inventory API và Notification API.
6. Cấu hình Resource Server xác minh issuer, audience và scope.
7. Dùng OAuth2AuthorizedClientManager trong Billing service.
8. Thiết kế token cache, refresh skew và single-flight.
9. Lập kế hoạch secret rotation không gián đoạn.
10. Mô phỏng Authorization Server timeout, invalid_client, invalid_scope và API 403.
11. Kiểm thử token của Reporting không thể tạo reservation.
12. Đo số token request và API latency trước/sau khi cache.

**Tiêu chí đạt:** Mỗi workload có danh tính riêng; token chỉ chứa quyền cần thiết và đúng audience; Resource Server xác minh issuer/audience/scope; client tái sử dụng token an toàn; lỗi credential không bị retry vô hạn; secret/token không xuất hiện trong log.

## 16. Tài liệu đối chiếu

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): Client Credentials Grant.
- [RFC 6749 — Section 3.2.1](https://www.rfc-editor.org/rfc/rfc6749#section-3.2.1): Client Authentication.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): gửi và bảo vệ bearer access token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): các claim iss, sub, aud và exp.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và claims liên quan client.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, token generation và core services.
- [Spring Authorization Server 1.5.8 — OAuth2TokenCustomizer Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenCustomizer.html): tùy chỉnh claims/token.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint và protocol processing.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized client và manager.
- [Spring Security — OAuth2AuthorizedClientManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): điều phối authorize và authorized client lifecycle.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder và Resource Server validation.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection cho opaque access token.
