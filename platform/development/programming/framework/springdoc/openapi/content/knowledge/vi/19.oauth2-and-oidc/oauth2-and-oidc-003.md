# Client Credentials và bối cảnh sử dụng phù hợp

OAuth 2.0 Client Credentials là grant type dành cho ứng dụng hoặc dịch vụ tự xác thực bằng danh tính của chính nó để gọi API được bảo vệ. Ví dụ, dịch vụ lập hóa đơn gọi dịch vụ kho để đọc tồn kho; một tác vụ nền gửi báo cáo đến API đối tác; hoặc một backend đồng bộ dữ liệu giữa hai hệ thống. Trong các tình huống này, request đại diện cho client/service, không đại diện cho người dùng đang đăng nhập.

Với Spring Boot, một ứng dụng có thể đóng vai trò OAuth2 Client để lấy access token từ Authorization Server, hoặc đóng vai trò Resource Server để xác minh Bearer token nhận được. Springdoc-openapi mô tả flow này trong Security Scheme Object loại `oauth2`, giúp Swagger UI và client hiểu token endpoint, scope và operation cần quyền nào. Metadata OpenAPI không tự đăng ký client, lấy token hay bảo vệ endpoint; các hành vi đó cần được cấu hình riêng bằng Spring Security và Authorization Server.

## 1. Client Credentials giải quyết bài toán nào?

Hãy xét một hệ thống gồm ba dịch vụ:

- `order-service` quản lý đơn hàng.
- `inventory-service` cung cấp thông tin tồn kho.
- `reporting-job` chạy theo lịch và tổng hợp báo cáo.

Khi `order-service` cần đọc tồn kho hoặc `reporting-job` cần gọi API báo cáo, không có người dùng tương tác trực tiếp để đăng nhập. Mỗi ứng dụng cần một danh tính máy riêng và chỉ được cấp quyền cần thiết.

Client Credentials cho phép client gửi thông tin xác thực của chính nó đến token endpoint để nhận access token. Sau đó client gửi token đến API đích:

```text
inventory-service
       |
       | client_id + client_secret
       v
Authorization Server
       |
       | access_token (scope: inventory.read)
       v
inventory-service
       |
       | Authorization: Bearer <access_token>
       v
inventory API (Resource Server)
```

Token thể hiện danh tính và quyền được cấp cho client. Resource Server xác minh token và kiểm tra quyền trước khi trả dữ liệu.

## 2. Vai trò của các thành phần OAuth 2.0

| Thành phần | Vai trò trong Client Credentials |
|---|---|
| Client | Ứng dụng/dịch vụ cần gọi API và có khả năng bảo vệ credential của chính nó |
| Client ID | Định danh client đã đăng ký tại Authorization Server |
| Client Secret hoặc phương thức client authentication khác | Chứng minh client là ứng dụng đã đăng ký |
| Authorization Server | Xác thực client, kiểm tra quyền được cấp và phát hành access token |
| Token Endpoint | Endpoint nhận yêu cầu token, thường là `/oauth2/token` |
| Resource Server | API nhận Bearer token, xác minh token và áp dụng authorization |
| Access Token | Credential có thời hạn được gửi trong request đến API |
| Scope | Quyền mà client yêu cầu hoặc được cấp, ví dụ `inventory.read` |

Client Credentials là luồng giữa client và Authorization Server. Resource Server không cần nhận client secret; nó chỉ nhận access token và xác minh token theo cơ chế được cấu hình.

## 3. Quy trình Client Credentials grant

Một luồng điển hình gồm các bước:

1. Quản trị viên đăng ký client tại Authorization Server và cấp một `client_id` cùng credential hoặc phương thức xác thực client khác.
2. Client gửi yêu cầu đến token endpoint với `grant_type=client_credentials` và scope cần thiết.
3. Authorization Server xác thực client và quyết định quyền được cấp.
4. Authorization Server trả access token cùng loại token, thời hạn và scope được cấp.
5. Client gửi access token đến Resource Server bằng header `Authorization: Bearer ...`.
6. Resource Server xác minh token, kiểm tra issuer, chữ ký hoặc trạng thái token, thời hạn và quyền truy cập.
7. Khi token hết hạn, client lấy token mới bằng cách thực hiện lại Client Credentials grant.

Luồng này không có bước chuyển hướng trình duyệt đến trang đăng nhập người dùng, không có authorization code và không cần redirect URI.

## 4. Yêu cầu token tại endpoint

Theo OAuth 2.0, client gửi POST đến token endpoint với content type `application/x-www-form-urlencoded`. Ví dụ yêu cầu:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Ở đây, `<client-credentials>` là biểu diễn Base64 của cặp client ID và client secret theo cơ chế HTTP Basic. Đây chỉ là ví dụ minh họa; client có thể dùng phương thức xác thực khác nếu Authorization Server hỗ trợ, chẳng hạn private key JWT hoặc mTLS.

Không gửi client secret trong URL. OAuth 2.0 khuyến nghị client authentication bằng HTTP Basic khi phù hợp; việc gửi credential trong body chỉ nên dùng khi Authorization Server yêu cầu và client không thể dùng phương thức khác được hỗ trợ. Mọi trao đổi token phải qua HTTPS/TLS.

Theo quy tắc OAuth 2.0, `client_id` và `client_secret` được mã hóa theo `application/x-www-form-urlencoded` trước khi ghép bằng dấu hai chấm và đưa qua HTTP Basic. Các thư viện OAuth2 thường xử lý bước này; khi tự tạo header, không giả định Base64 trực tiếp của hai chuỗi thô luôn đúng nếu credential có ký tự đặc biệt.

Ví dụ curl dùng biến môi trường để tránh ghi trực tiếp secret vào lệnh:

```bash
curl --request POST \
  --user "$OAUTH_CLIENT_ID:$OAUTH_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data "grant_type=client_credentials&scope=inventory.read" \
  https://identity.example.com/oauth2/token
```

Không lưu secret thật trong shell history, source code hoặc file cấu hình được commit. Trong môi trường triển khai, lấy credential từ secret manager hoặc cơ chế quản lý bí mật của nền tảng.

## 5. Token response

Authorization Server thường trả JSON tương tự:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "inventory.read"
}
```

Các trường thường gặp:

| Trường | Ý nghĩa |
|---|---|
| `access_token` | Token client dùng để gọi Resource Server |
| `token_type` | Loại token; thường là `Bearer` |
| `expires_in` | Thời gian sống của token tính bằng giây |
| `scope` | Scope được cấp; có thể khác tập scope client yêu cầu |
| `refresh_token` | Thông thường không được phát hành cho Client Credentials grant |

Client phải sử dụng scope thực tế trong response hoặc claims token, không giả định Authorization Server luôn cấp toàn bộ scope đã yêu cầu. Với Client Credentials, client thường lấy access token mới khi token hết hạn thay vì dùng refresh token.

## 6. Client Credentials không đại diện cho người dùng

Đây là khác biệt quan trọng nhất khi chọn grant type. Token của Client Credentials đại diện cho ứng dụng hoặc workload. Nó không cho biết một người dùng cuối cụ thể đã đăng nhập hay đồng ý thao tác.

Ví dụ phù hợp:

- `billing-service` gọi API tỷ giá theo lịch.
- `analytics-job` đọc dữ liệu tổng hợp từ nhiều dịch vụ.
- Backend của đối tác gửi dữ liệu theo hợp đồng tích hợp máy-máy.
- Một service gọi API nội bộ với scope chỉ đọc.

Ví dụ không phù hợp:

- Ứng dụng web cần truy cập dữ liệu riêng của người dùng đang đăng nhập.
- Mobile app cần xin quyền truy cập tài nguyên thay mặt người dùng.
- Một thao tác cần ghi nhận sự đồng ý hoặc danh tính người dùng cuối.
- Client cần quyền thay đổi theo quyền của người dùng hiện tại.

Trong các trường hợp có người dùng, thường cần Authorization Code Flow với PKCE hoặc một flow phù hợp khác theo kiến trúc Identity Provider. Không dùng Client Credentials để giả lập đăng nhập người dùng.

## 7. Phân biệt OAuth 2.0 Client Credentials, Authorization Code và OIDC

| Tiêu chí | Client Credentials | Authorization Code + PKCE | OpenID Connect |
|---|---|---|---|
| Chủ thể được đại diện | Client/service | Người dùng đã xác thực và client | Người dùng được xác thực qua lớp OIDC |
| Có tương tác đăng nhập người dùng | Không | Có | Thường có qua Authorization Code |
| Dùng cho | Machine-to-machine | Web, SPA, mobile và ứng dụng có người dùng | Đăng nhập, xác minh danh tính người dùng |
| Redirect URI | Không cần | Có | Thường có trong flow đăng nhập OIDC |
| ID Token | Không được phát hành chỉ vì dùng Client Credentials | Không phải thành phần bắt buộc của OAuth2 thuần | Là thành phần cốt lõi của OIDC |
| Access Token | Có | Có | Có thể có để gọi API |

OAuth 2.0 là framework ủy quyền. OpenID Connect mở rộng OAuth 2.0 để cung cấp lớp xác thực và ID Token mô tả danh tính người dùng. Client Credentials thường được dùng để cấp quyền cho workload; nó không phải flow đăng nhập OIDC và không tạo ID Token chỉ vì client đang dùng OAuth2.

Một hệ thống có thể dùng OIDC để đăng nhập nhân viên và đồng thời dùng Client Credentials cho service-to-service. Hai luồng phục vụ các mục đích khác nhau và có thể cùng tồn tại.

## 8. Client cần là confidential client

Client Credentials yêu cầu client có khả năng giữ bí mật thông tin xác thực hoặc dùng một phương thức client authentication mạnh khác. Một ứng dụng chạy hoàn toàn trong browser hoặc trên thiết bị người dùng không thể bảo vệ client secret khỏi người sử dụng thiết bị.

Các client phù hợp thường là:

- Backend server.
- Worker hoặc scheduled job chạy trong môi trường được kiểm soát.
- Daemon hoặc service trong hạ tầng doanh nghiệp.
- Workload có danh tính máy được quản lý bởi nền tảng.

Không nhúng client secret vào JavaScript frontend, ứng dụng mobile hoặc desktop phân phối rộng. Nếu cần client công khai gọi API thay mặt người dùng, hãy dùng Authorization Code với PKCE và thiết kế token theo đúng đối tượng sử dụng.

Ngoài client secret, Authorization Server có thể hỗ trợ phương thức xác thực client mạnh hơn như `private_key_jwt` hoặc mutual TLS. Cơ chế cụ thể phụ thuộc khả năng của Authorization Server và chính sách triển khai.

## 9. Scope và nguyên tắc quyền tối thiểu

Scope mô tả phạm vi quyền mà client yêu cầu. Ví dụ:

| Scope | Quyền minh họa |
|---|---|
| `inventory.read` | Đọc thông tin tồn kho |
| `inventory.write` | Cập nhật tồn kho |
| `orders.read` | Đọc đơn hàng |
| `orders.export` | Xuất dữ liệu đơn hàng |

Một client chỉ cần đọc tồn kho không nên được cấp `inventory.write`. Hãy cấp scope tối thiểu để giới hạn tác động nếu credential bị lộ.

Scope là quy ước do Authorization Server và Resource Server cùng hiểu. Tên scope trong OpenAPI phải khớp với scope mà Authorization Server cấp và Resource Server kiểm tra. Nếu hệ thống dùng claim/authority riêng thay vì scope chuẩn, cần mô tả rõ quy tắc đó.

Không nhầm scope với role người dùng. Client Credentials đại diện cho workload; quyền của nó thường gắn với client, tenant, audience hoặc policy của dịch vụ.

## 10. Audience và giới hạn nơi sử dụng token

Scope trả lời client được phép làm gì; audience (đối tượng nhận) giúp xác định token được phát hành cho Resource Server nào. Một token dành cho `inventory-api` không nên được chấp nhận bởi `billing-api` nếu token không có audience phù hợp.

Với JWT, Resource Server thường cần kiểm tra các claim như:

- `iss`: issuer đã phát hành token.
- `aud`: audience/Resource Server mà token hướng tới.
- `exp`: thời điểm token hết hạn.
- `nbf`: thời điểm token bắt đầu có hiệu lực nếu có.
- `scope` hoặc `scp`: các quyền được cấp theo quy ước của hệ thống.
- `sub` hoặc claim định danh client: danh tính client, theo cách Authorization Server biểu diễn.

Không phải mọi Authorization Server đều dùng cùng tên claim hoặc cùng quy tắc ánh xạ. Cần đối chiếu cấu hình thực tế và xác minh audience ở Resource Server. Chỉ kiểm tra chữ ký mà bỏ qua issuer, audience, thời hạn hoặc quyền có thể khiến token hợp lệ về mật mã nhưng không phù hợp với API đích.

## 11. Mô tả Client Credentials trong OpenAPI

OpenAPI mô tả Client Credentials bằng Security Scheme Object loại `oauth2`, trong đó `flows.clientCredentials` chứa `tokenUrl` và danh sách scope.

```yaml
components:
  securitySchemes:
    serviceClientAuth:
      type: oauth2
      description: OAuth2 Client Credentials cho service-to-service
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            inventory.read: Đọc thông tin tồn kho
            inventory.write: Cập nhật thông tin tồn kho
```

Các trường quan trọng:

- `type: oauth2`: đây là security scheme OAuth 2.0.
- `flows.clientCredentials`: khai báo grant type Client Credentials.
- `tokenUrl`: endpoint phát hành access token.
- `scopes`: tên và mô tả các quyền mà client có thể yêu cầu.
- `description`: hướng dẫn ngữ cảnh sử dụng, cách đăng ký client và yêu cầu môi trường.

`tokenUrl` là URL của Authorization Server, không phải URL của Resource Server. Nếu API chạy ở một host và Authorization Server ở host khác, hãy khai báo đúng token endpoint do nhà cung cấp danh tính công bố.

Không đưa `client_secret` vào OpenAPI document. Tài liệu API thường được phân phối cho nhiều người; credential client phải được quản lý ngoài tài liệu.

## 12. Gắn scope vào operation bằng Security Requirement

Sau khi khai báo scheme, operation cần quyền đọc tồn kho có thể tham chiếu scope:

```yaml
paths:
  /api/inventory:
    get:
      operationId: listInventory
      security:
        - serviceClientAuth:
            - inventory.read
      responses:
        '200':
          description: Danh sách tồn kho
        '401':
          description: Access token không hợp lệ hoặc thiếu
        '403':
          description: Client không có scope inventory.read
```

Operation cập nhật tồn kho dùng scope khác:

```yaml
  /api/inventory/{itemId}:
    put:
      operationId: updateInventory
      security:
        - serviceClientAuth:
            - inventory.write
      responses:
        '204':
          description: Đã cập nhật tồn kho
```

Scope trong Security Requirement phải là một scope đã khai báo trong flow. OpenAPI chỉ mô tả scope yêu cầu; Authorization Server quyết định scope thực tế cấp và Resource Server phải kiểm tra quyền tương ứng.

## 13. Khai báo flow bằng springdoc annotations

Springdoc tích hợp Swagger Annotations để mô tả OAuth2 flow. Ví dụ:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "serviceClientAuth",
    type = SecuritySchemeType.OAUTH2,
    description = "OAuth2 Client Credentials cho service-to-service",
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "inventory.read",
                    description = "Đọc thông tin tồn kho"
                ),
                @OAuthScope(
                    name = "inventory.write",
                    description = "Cập nhật thông tin tồn kho"
                )
            }
        )
    )
)
class OpenApiOAuthConfiguration {
}
```

Gắn scope vào operation:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@Operation(
    summary = "Liệt kê tồn kho",
    security = @SecurityRequirement(
        name = "serviceClientAuth",
        scopes = {"inventory.read"}
    )
)
@GetMapping("/api/inventory")
List<InventoryItemResponse> listInventory() {
    return inventoryService.list();
}
```

Tên scheme `serviceClientAuth` và scope `inventory.read` phải khớp với khai báo trong `@SecurityScheme`. Nếu dùng scope khác nhau theo operation, khai báo requirement tương ứng ở từng method hoặc nhóm endpoint.

## 14. Cấu hình Spring Boot làm OAuth2 Client

Một service Spring Boot cần lấy token để gọi API khác có thể dùng Spring Security OAuth2 Client. Khai báo registration và provider trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: company-identity
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          company-identity:
            token-uri: https://identity.example.com/oauth2/token
```

Giải thích:

- `registration.inventory-service` là tên registration mà ứng dụng tham chiếu.
- `client-id` và `client-secret` lấy từ biến môi trường hoặc secret manager.
- `authorization-grant-type: client_credentials` chọn đúng grant type.
- `scope` liệt kê quyền client yêu cầu.
- `provider.company-identity.token-uri` trỏ đến token endpoint.

Không commit giá trị secret thật vào `application.yml`. Với môi trường production, dùng secret manager, workload identity hoặc cơ chế cấp credential của nền tảng. Nếu Authorization Server hỗ trợ private key JWT hoặc mTLS, cân nhắc dùng phương thức đó theo yêu cầu bảo mật.

## 15. Lấy access token bằng `OAuth2AuthorizedClientManager`

Spring Security có thể quản lý quá trình authorize, lưu thông tin client đã được authorize và làm mới access token khi cần. Với ứng dụng backend hoặc tác vụ nền không gắn với phiên người dùng, có thể dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class OAuth2ClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClientService
        );

        manager.setAuthorizedClientProvider(
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build()
        );

        return manager;
    }
}
```

Khi cần gọi API, yêu cầu manager authorize registration:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

class InventoryApiClient {

    private final OAuth2AuthorizedClientManager authorizedClientManager;

    InventoryApiClient(OAuth2AuthorizedClientManager authorizedClientManager) {
        this.authorizedClientManager = authorizedClientManager;
    }

    String accessToken() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-service")
                .principal("inventory-service")
                .build();

        OAuth2AuthorizedClient client = authorizedClientManager.authorize(request);
        if (client == null) {
            throw new IllegalStateException("Không thể lấy access token");
        }

        return client.getAccessToken().getTokenValue();
    }
}
```

Sau đó client gửi token bằng header `Authorization: Bearer ...` khi gọi API đích. Trong ứng dụng thực, nên đóng gói việc thêm header trong một HTTP client/interceptor dùng chung, tránh tự xử lý token ở nhiều nơi và tránh log token.

`OAuth2AuthorizedClientManager` giúp quản lý vòng đời access token theo registration. Không cần tự gọi token endpoint cho từng request nghiệp vụ; provider có thể tái sử dụng token còn hiệu lực và yêu cầu token mới khi cần.

## 16. Spring Boot làm Resource Server nhận Bearer token

Một ứng dụng khác có thể đóng vai trò Resource Server. Nếu Authorization Server phát hành JWT, thêm dependency OAuth2 Resource Server phù hợp và cấu hình issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
```

Cấu hình filter chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/inventory/**")
                            .hasAuthority("SCOPE_inventory.read")
                        .requestMatchers(HttpMethod.PUT, "/api/inventory/**")
                            .hasAuthority("SCOPE_inventory.write")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Spring Security thường ánh xạ scope thành authority có tiền tố `SCOPE_`. Vì vậy scope `inventory.read` có thể được kiểm tra bằng `hasAuthority("SCOPE_inventory.read")`. Cách ánh xạ có thể được tùy chỉnh; hãy kiểm tra claim token và converter thực tế.

`issuer-uri` giúp cấu hình xác minh issuer và khám phá khóa theo metadata. Nếu cần kiểm tra audience cụ thể, hãy bổ sung validator phù hợp; không giả định chỉ cấu hình issuer là đã đáp ứng mọi yêu cầu bảo mật của hệ thống.

Nếu access token là opaque, cấu hình opaque token introspection thay cho JWT decoder. OpenAPI vẫn mô tả HTTP Bearer hoặc OAuth2 Client Credentials flow theo cách Authorization Server cấp token.

## 17. Phân biệt OAuth2 Client và Resource Server

Hai vai trò thường cùng xuất hiện trong kiến trúc service-to-service nhưng thực hiện công việc khác nhau:

| Vai trò | Cấu hình chính | Trách nhiệm |
|---|---|---|
| OAuth2 Client | `spring.security.oauth2.client.registration` | Lấy và quản lý access token để gọi API khác |
| Resource Server | `spring.security.oauth2.resourceserver` | Nhận Bearer token, xác minh token và kiểm tra quyền |
| Authorization Server | Hệ thống cấp token | Xác thực client và phát hành token theo policy |
| springdoc-openapi | `@SecurityScheme`, `@SecurityRequirement` | Mô tả flow, token URL, scope và operation requirement trong tài liệu |

Một service có thể vừa là OAuth2 Client để gọi dịch vụ khác, vừa là Resource Server để nhận request từ dịch vụ khác. Khi đó cần cấu hình hai vai trò độc lập và tránh nhầm credential client dùng lấy token với access token mà service phát hành/nhận.

## 18. Swagger UI và Client Credentials

Khi OpenAPI khai báo `flows.clientCredentials`, Swagger UI có thể nhận biết OAuth2 Client Credentials flow và hiển thị các trường cần thiết trong hộp thoại Authorize, tùy phiên bản Swagger UI được springdoc đóng gói.

Tuy nhiên, Swagger UI chạy trong trình duyệt. Nếu nhập `client_secret` vào giao diện, secret được gửi từ browser và có thể bị người dùng, extension, devtools hoặc môi trường trình duyệt kiểm soát đọc được. Vì Client Credentials dành cho confidential client, không dùng client secret production trong Swagger UI công khai hoặc trong browser của người dùng.

Nếu cần thử flow bằng giao diện:

- Dùng Authorization Server và client riêng cho môi trường development/test.
- Tạo client có scope giới hạn, thời hạn và quyền tối thiểu.
- Dùng secret dùng một lần hoặc có thể thu hồi; không dùng credential production.
- Chỉ mở Swagger UI cho nhóm người dùng được phép.
- Thu hồi credential thử nghiệm sau khi hoàn tất.

Đối với kiểm thử service-to-service thật, ưu tiên một backend test client, curl trong môi trường an toàn hoặc integration test dùng secret được quản lý. Không nhúng `clientSecret` vào cấu hình frontend hoặc tài liệu OpenAPI.

Client Credentials không cần redirect URI và không dùng PKCE theo cách của Authorization Code flow. Không cấu hình `oauth2RedirectUrl` như thể đây là đăng nhập người dùng.

## 19. Xử lý token hết hạn, cache và thu hồi

Access token thường có thời hạn ngắn hơn client credential. Client nên:

- Đọc `expires_in` hoặc thời điểm hết hạn từ token response.
- Tái sử dụng token còn hiệu lực thay vì xin token mới cho từng request.
- Làm mới bằng cách thực hiện lại Client Credentials grant khi token hết hạn hoặc sắp hết hạn.
- Có biên an toàn nhỏ trước thời điểm hết hạn để tránh token hết hạn giữa request.
- Xử lý lỗi `invalid_client`, `invalid_scope` và lỗi token endpoint theo cách có thể quan sát.
- Không retry vô hạn khi client secret sai hoặc client bị vô hiệu hóa.

Khi credential client bị lộ, cần thu hồi hoặc xoay vòng credential tại Authorization Server, cập nhật secret manager và xem xét thu hồi token đang còn hiệu lực nếu hệ thống hỗ trợ. Với JWT tự chứa, thu hồi tức thời có thể khó hơn opaque token; thời hạn token ngắn và cơ chế denylist/introspection có thể là một phần của thiết kế.

## 20. Response lỗi thường gặp

Token endpoint và Resource Server có các nhóm lỗi khác nhau:

| Lỗi | Nơi phát sinh | Ý nghĩa |
|---|---|---|
| `invalid_client` | Token endpoint | Client authentication thất bại hoặc client không hợp lệ |
| `invalid_scope` | Token endpoint | Scope yêu cầu không hợp lệ hoặc không được cấp |
| `unsupported_grant_type` | Token endpoint | Authorization Server không hỗ trợ grant type được gửi |
| `invalid_request` | Token endpoint | Thiếu hoặc sai tham số theo giao thức |
| `401 Unauthorized` | Resource Server | Thiếu token, token sai, hết hạn hoặc không hợp lệ |
| `403 Forbidden` | Resource Server | Token hợp lệ nhưng client không đủ scope/quyền |

Không trả client secret, chi tiết chữ ký hoặc thông tin nội bộ trong error message. Log nên ghi correlation ID và mã lỗi có thể tra cứu, đồng thời loại bỏ token và credential.

## 21. Kiểm tra cấu hình và hợp đồng OpenAPI

Sau khi cấu hình OAuth2 Client, Resource Server và springdoc, kiểm tra từng phần độc lập:

1. Xác nhận registration dùng `authorization-grant-type: client_credentials`.
2. Xác nhận `token-uri` trỏ đúng Authorization Server.
3. Xác nhận client ID/secret được nạp từ secret store hoặc biến môi trường.
4. Gọi token endpoint trong môi trường test và kiểm tra scope thực tế được cấp.
5. Gửi token đến Resource Server bằng header Bearer.
6. Kiểm tra token sai/hết hạn trả `401` và token thiếu quyền trả `403` theo policy.
7. Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
8. Xác nhận `components.securitySchemes.serviceClientAuth.type` là `oauth2`.
9. Xác nhận `flows.clientCredentials.tokenUrl` và danh sách scope chính xác.
10. Xác nhận operation có `security` tham chiếu đúng scheme và scope.
11. Kiểm tra Swagger UI hiển thị flow đúng; không dùng secret production trong browser.
12. Chạy OpenAPI validator và kiểm tra client generator nếu API được phân phối cho đối tác.

Ví dụ tài liệu cần có cấu trúc tương tự:

```yaml
components:
  securitySchemes:
    serviceClientAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            inventory.read: Đọc tồn kho
paths:
  /api/inventory:
    get:
      security:
        - serviceClientAuth:
            - inventory.read
```

Nếu tài liệu ghi scope `inventory.read` nhưng Authorization Server cấp tên scope khác hoặc Resource Server không kiểm tra scope đó, hợp đồng và runtime sẽ không đồng nhất.

## 22. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Token endpoint trả `invalid_client` | Sai client ID/secret, authentication method không khớp hoặc client bị vô hiệu hóa | Kiểm tra registration và phương thức client authentication |
| Token endpoint trả `invalid_scope` | Scope không được đăng ký hoặc client không được cấp | Đồng bộ scope giữa client, Authorization Server và API |
| Client gửi secret trong URL | Hiểu sai cách truyền credential | Dùng client authentication qua HTTPS theo phương thức server hỗ trợ |
| API nhận token nhưng trả 401 | Issuer, chữ ký, audience hoặc thời hạn không hợp lệ | Kiểm tra cấu hình Resource Server và claims |
| Token hợp lệ nhưng trả 403 | Client thiếu scope/authority cần thiết | Điều chỉnh quyền được cấp hoặc yêu cầu API đúng scope |
| Swagger UI có nút Authorize nhưng gọi API thất bại | Chưa cấu hình đúng OAuth2 flow hoặc runtime không chấp nhận token | Kiểm tra token URL, client registration và Resource Server |
| Client Credentials bị dùng cho đăng nhập người dùng | Nhầm danh tính client với danh tính user | Dùng Authorization Code + PKCE/OIDC cho luồng người dùng |
| Client secret xuất hiện trong JavaScript | Dùng confidential client trong browser | Chuyển việc lấy token về backend hoặc dùng public-client flow phù hợp |
| Token được xin lại ở mọi request | Không tái sử dụng authorized client/token còn hạn | Dùng OAuth2AuthorizedClientManager và cache/lifecycle phù hợp |
| Tài liệu khai báo scope nhưng server không kiểm tra | Chỉ mô tả OpenAPI mà thiếu authorization runtime | Cấu hình scope authority và kiểm thử endpoint |

## 23. Nguyên tắc thiết kế

- Chọn Client Credentials cho workload hoặc service cần gọi API bằng danh tính của chính nó.
- Không dùng flow này để đại diện cho người dùng cuối hoặc thay thế đăng nhập OIDC.
- Chỉ dùng confidential client có thể bảo vệ credential hoặc phương thức client authentication mạnh tương đương.
- Gửi yêu cầu token bằng HTTPS và không đặt secret trong URL hoặc source code.
- Cấp scope tối thiểu và giới hạn audience của token theo Resource Server đích.
- Không nhầm Bearer với JWT; token có thể là JWT hoặc opaque.
- Mô tả `flows.clientCredentials.tokenUrl` và scope trong OpenAPI; gắn Security Requirement vào đúng operation.
- Không đưa client secret vào tài liệu OpenAPI hoặc Swagger UI public.
- Dùng Spring Security OAuth2 Client để lấy/quản lý token và Resource Server để xác minh token độc lập.
- Tái sử dụng token còn hạn, lấy token mới khi hết hạn và có quy trình xoay vòng credential.
- Kiểm tra cả token endpoint, Resource Server, scope, audience và tài liệu `/v3/api-docs`.

## Kết luận

OAuth 2.0 Client Credentials phù hợp với giao tiếp máy-máy khi một service cần xác thực bằng danh tính của chính nó để gọi API. Client gửi credential đến token endpoint, nhận access token với scope được cấp rồi dùng Bearer token gọi Resource Server. Flow này không đăng nhập người dùng và không tạo ID Token OIDC. Trong Spring Boot, OAuth2 Client quản lý việc lấy token; Resource Server xác minh token và quyền; springdoc-openapi mô tả flow bằng `type: oauth2`, `flows.clientCredentials`, `tokenUrl` và scope. Hãy dùng confidential client, bảo vệ credential, cấp quyền tối thiểu và đồng bộ hợp đồng OpenAPI với chính sách Authorization Server cùng Resource Server.
