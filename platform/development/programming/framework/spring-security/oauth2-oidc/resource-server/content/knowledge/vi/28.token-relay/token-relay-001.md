# Resource Server gọi dịch vụ khác có thể đồng thời đóng vai trò OAuth2 Client

Một ứng dụng Spring Security có thể vừa là **OAuth 2.0 Resource Server** đối với request đi vào, vừa là **OAuth 2.0 Client** khi gọi một dịch vụ được bảo vệ khác. Đây là mô hình phổ biến trong kiến trúc microservices: Orders API nhận access token của người dùng, xác minh token và quyền truy cập, sau đó gọi Inventory API, Pricing API hoặc Shipping API bằng một access token phù hợp với dịch vụ đích.

Hai vai trò này không loại trừ nhau. Một service có thể đồng thời:

- Nhận và xác minh access token từ Client phía trước bằng Resource Server.
- Dùng OAuth2 Client để lấy hoặc quản lý access token cho request đi ra.
- Chọn credential đi ra theo mục đích nghiệp vụ: danh tính của chính service, danh tính người dùng được ủy quyền, hoặc một token mới được Authorization Server trao đổi từ token đi vào.

**Không nên mặc định token đi vào là token phải gửi tiếp đi ra.** Token đó có thể chỉ dành cho audience của service hiện tại, không có scope cần thiết ở service kế tiếp, hoặc không được phép chuyển tiếp. Lựa chọn outbound token phải theo hợp đồng giữa các service và Authorization Server.

> **Nguyên tắc:** Resource Server xác minh **ai đang gọi service hiện tại và được làm gì ở đây**. OAuth2 Client xác định **service hiện tại sẽ đại diện cho ai khi gọi hệ thống khác**. Hai quyết định liên quan nhau nhưng không đồng nhất. Chọn token đi ra theo least privilege, đúng audience, đúng scope và đúng mô hình delegation.

## 1. Một service có thể mang hai vai trò OAuth2

Giả sử hệ thống bán hàng có:

- **Shop Web**: OAuth2 Client, lấy access token để gọi Orders API.
- **Orders API**: Resource Server đối với Shop Web; đồng thời OAuth2 Client khi gọi Inventory API.
- **Inventory API**: Resource Server, cung cấp tồn kho.
- **Authorization Server**: cấp access token cho từng resource server.

~~~mermaid
flowchart LR
    U["Người dùng / Shop Web"]
    AS["Authorization Server"]
    O["Orders API<br/>Resource Server + OAuth2 Client"]
    I["Inventory API<br/>Resource Server"]

    U -->|"Bearer token cho Orders API"| O
    O <-->|"Xác minh JWT / introspection"| AS
    O -->|"Token đi ra phù hợp"| I
    I <-->|"Xác minh token của Inventory"| AS
~~~

Trong một request:

1. Shop Web gửi token dành cho Orders API.
2. Orders API xác minh token, audience, thời hạn và scope.
3. Orders API thực hiện authorization nghiệp vụ, ví dụ người dùng có thể xem đơn hàng hay không.
4. Nếu cần gọi Inventory API, Orders API chọn một cơ chế OAuth2 Client để có credential đi ra.
5. Inventory API xác minh token dành cho chính nó và thực thi quyền tồn kho.

**Orders API không chỉ chuyển nguyên token đi vào theo thói quen.** Có thể dùng một token khác với danh tính của service hoặc một token exchange đại diện người dùng.

## 2. Phân biệt Resource Server và OAuth2 Client trong cùng ứng dụng

| Vai trò | Hướng request | Trách nhiệm |
| --- | --- | --- |
| **Resource Server** | Inbound: Client → Orders API | Đọc Bearer token, xác minh token, tạo Authentication, kiểm tra scope/authority và bảo vệ endpoint |
| **OAuth2 Client** | Outbound: Orders API → Inventory API | Chọn ClientRegistration, xin/đổi access token, quản lý authorized client và gắn token vào request đi ra |
| **Authorization Server** | Token endpoint | Xác thực OAuth2 Client, cấp token, xử lý grant và policy delegation |

Spring Security cung cấp hai nhóm tính năng tương ứng:

- `oauth2ResourceServer()` trong `HttpSecurity` hoặc `ServerHttpSecurity` để bảo vệ API.
- `oauth2Client()` và các thành phần `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager` để thực hiện OAuth2 Client flow.

Ví dụ cấu hình Servlet có thể bật cả hai:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là cấu hình khung. JWT decoder, issuer/audience validators, ClientRegistration, grant provider, authorized-client storage và các rule scope cụ thể vẫn phải được cấu hình theo hệ thống.

**Bật `oauth2Client()` không tự động quyết định token nào sẽ được gửi tới từng downstream service.** Phần gọi dịch vụ phải chọn registration và principal/context phù hợp.

### 2.1. Authentication đi vào không tự trở thành OAuth2AuthorizedClient đi ra

Khi Resource Server xác minh JWT, Spring Security thường tạo `JwtAuthenticationToken`. Nó đại diện cho request hiện tại và chứa JWT đã xác minh cùng authorities.

`OAuth2AuthorizedClient` là khái niệm khác: nó liên kết một `ClientRegistration` với `OAuth2AccessToken`, có thể có `OAuth2RefreshToken`, và một principal mà authorized client được lưu/định danh theo đó.

`OAuth2AuthorizedClientManager` quản lý quá trình authorize hoặc re-authorize, gọi provider tương ứng và lưu authorized client qua repository/service. Nó không mặc định lấy inbound JWT rồi gửi nguyên văn cho mọi downstream.

## 3. Chọn chiến lược outbound token

Có ba chiến lược thường gặp:

| Chiến lược | Token đi ra đại diện cho ai? | Khi phù hợp |
| --- | --- | --- |
| **Client Credentials** | Chính Orders API/service | Downstream cần biết service nào đang gọi, không cần user context |
| **Token relay / forward incoming token** | Người dùng hoặc principal đã cấp inbound token | Token ban đầu được thiết kế để dùng tại downstream, đúng audience/scope và policy cho phép |
| **Token Exchange / On-Behalf-Of** | Người dùng được ủy quyền, qua token mới dành cho downstream | Downstream cần danh tính người dùng nhưng token inbound không dành cho nó hoặc cần giảm scope/audience |

### 3.1. Client Credentials: service gọi bằng danh tính của chính mình

Ví dụ Orders API cần lấy thông tin tồn kho tổng hợp để xử lý một tác vụ nội bộ. Inventory API chỉ cần biết caller là `orders-api`, không cần biết Alice hay Bob đã gửi request.

Luồng:

~~~text
Orders API
  -> client_id/client_secret hoặc private_key_jwt
  -> Authorization Server token endpoint
  -> grant_type=client_credentials
  -> access token audience=inventory-api, scope=inventory.read
  -> Inventory API
~~~

Token này đại diện **OAuth2 Client**, không đại diện người dùng cuối. Vì vậy Inventory API có thể audit `client_id=orders-api` thay vì `sub=alice`.

Client Credentials phù hợp cho tác vụ nền, scheduler, batch hoặc service-to-service khi downstream cần service identity. Không dùng Client Credentials để giả vờ rằng người dùng đã được ủy quyền. Nếu downstream phải kiểm tra quyền của Alice, token chỉ đại diện Orders API sẽ không cung cấp đủ user context.

### 3.2. Token relay: chuyển tiếp token đi vào

Một số kiến trúc cho phép Orders API chuyển tiếp nguyên access token:

~~~text
Shop Web -- token T --> Orders API -- token T --> Inventory API
~~~

Chỉ làm vậy nếu **token T được phát hành dành cho Inventory API hoặc một audience set có chứa Inventory API**, và scope/permission trong token đủ cho thao tác ở đó.

Ví dụ token có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api", "inventory-api"],
  "scope": "orders.read inventory.read",
  "exp": 1893459600
}
~~~

Nếu token chỉ có `aud=["orders-api"]`, Inventory API nên từ chối token đó. Không nên yêu cầu downstream bỏ kiểm tra audience để việc relay hoạt động.

Token relay có thể phù hợp khi nhiều API cùng tin issuer, token profile và AS chủ động cấp audience/scope cho các downstream liên quan. Rủi ro là token đi qua nhiều service, tăng bề mặt lộ token và có thể mang scope rộng hơn mức downstream cần.

**Không relay token đến URL tùy ý do request/body cung cấp.** Chọn downstream host từ cấu hình/allowlist; tránh biến API thành confused deputy hoặc token exfiltration proxy.

### 3.3. Token Exchange: đổi token đi vào thành token mới cho downstream

Token Exchange theo **RFC 8693** cho phép một Client gửi token hiện tại làm `subject_token` tới Authorization Server để nhận một token khác phù hợp với resource/actor/scope mới, nếu AS hỗ trợ policy đó.

~~~text
Client -> Orders API: access token T1 (aud=orders-api)
Orders API -> Authorization Server:
    grant_type=urn:ietf:params:oauth:grant-type:token-exchange
    subject_token=T1
    subject_token_type=urn:ietf:params:oauth:token-type:access_token
    audience/resource=inventory-api
    scope=inventory.read
Authorization Server -> Orders API: access token T2
Orders API -> Inventory API: Authorization: Bearer T2
~~~

T2 có thể có audience riêng và scope nhỏ hơn, vẫn đại diện subject người dùng theo policy AS. Token Exchange là lựa chọn hữu ích cho delegation xuyên service.

Nó không đồng nghĩa với việc Orders API tự ký một JWT khác. Authorization Server là bên quyết định có cấp token mới hay không.

### 3.4. On-Behalf-Of (OBO) là một cách triển khai delegation

Một số nền tảng gọi mô hình này là **On-Behalf-Of**. OBO thường mô tả một service dùng token inbound để xin token downstream thay mặt user. RFC 8693 Token Exchange cung cấp một chuẩn tổng quát cho token exchange; các nhà cung cấp có thể triển khai OBO với tham số, endpoint hoặc policy riêng.

Không mặc định mọi Authorization Server hỗ trợ cùng một giao thức OBO chỉ vì nó hỗ trợ OAuth2 Client Credentials.

## 4. Chọn đúng chiến lược

| Nhu cầu downstream | Chiến lược thường phù hợp |
| --- | --- |
| Chỉ cần xác định Orders API là caller | Client Credentials |
| Cần quyền user, token inbound đã có audience/scope đúng | Token relay có kiểm soát |
| Cần quyền user nhưng token inbound chỉ dành cho Orders API | Token Exchange/OBO |
| Cần quyền user và service identity trong delegation chain | Token Exchange với subject token và actor token nếu AS hỗ trợ |
| Tác vụ nền không có user request | Client Credentials |
| Service chỉ được đọc một nhóm dữ liệu hẹp | Client Credentials với scope hẹp hoặc exchanged token downscoped |

**Đừng dùng Client Credentials cho mọi trường hợp chỉ vì dễ cấu hình.** Nếu downstream cần biết Alice có quyền xem Order 42 hay không, token đại diện Orders API có thể làm mất thông tin chủ thể hoặc khiến downstream chỉ còn thấy quyền của service.

Ngược lại, **đừng dùng token exchange khi downstream chỉ cần service identity**. Không cần mang user context vào một tác vụ nội bộ nếu policy không yêu cầu.

## 5. Cấu hình OAuth2 Client cho Client Credentials

Ví dụ dùng **Spring Boot 3 / Spring Security 6+ với Servlet stack**. Các class/API dưới đây tiếp tục có trong tài liệu Spring Security 7.1.

### 5.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Resource Server starter bảo vệ inbound API; OAuth2 Client starter cung cấp ClientRegistration, authorized-client manager và tích hợp HTTP client.

### 5.2. Đăng ký client trong application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
      client:
        registration:
          inventory:
            provider: identity
            client-id: orders-api
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          identity:
            token-uri: https://identity.example.test/oauth2/token
~~~

Các giá trị là ví dụ:

- `inventory` là registration ID nội bộ của Spring, được dùng để chọn ClientRegistration.
- `client-id`/`client-secret` xác thực Orders API với AS.
- `client_credentials` yêu cầu token đại diện service.
- `inventory.read` là scope cần cho Inventory API.
- `token-uri` là token endpoint của AS.

Không commit secret thật vào repository. Dùng secret manager, workload identity, private_key_jwt hoặc cơ chế client authentication phù hợp môi trường. Nếu AS hỗ trợ private-key JWT, có thể chọn `client-authentication-method` tương ứng thay cho client secret.

### 5.3. Tạo OAuth2AuthorizedClientManager cho service/background

`DefaultOAuth2AuthorizedClientManager` được thiết kế để hoạt động trong ngữ cảnh `HttpServletRequest`. Với service application, scheduler hoặc tác vụ chạy ngoài request, dùng **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

@Configuration
class OAuth2ClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Manager có thể tìm authorized client đã lưu, xin access token mới khi chưa có token phù hợp, re-authorize khi token hết hạn theo provider được cấu hình, lưu authorized client qua `OAuth2AuthorizedClientService` và xử lý lỗi authorization theo success/failure handler.

Provider trong ví dụ chỉ bật `client_credentials`. Nếu cần refresh-token grant hoặc extension grant, thêm provider tương ứng theo contract. Không cho phép mọi grant một cách không cần thiết.

### 5.4. Lấy access token cho một service principal

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
class InventoryAccessTokenService {

    private final OAuth2AuthorizedClientManager manager;

    InventoryAccessTokenService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String getAccessToken() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory")
                    .principal("orders-api")
                    .build();

        OAuth2AuthorizedClient authorizedClient =
                manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Could not authorize Inventory API client");
        }

        return authorizedClient.getAccessToken().getTokenValue();
    }
}
~~~

`principal("orders-api")` là tên principal dùng để gắn authorized client được lưu với service. Nó không phải access token và cũng không phải end-user. Dùng một định danh ổn định cho service client để tránh tạo quá nhiều authorized-client entries theo từng user nếu grant là Client Credentials.

### 5.5. Dùng token với RestClient

Một cách đơn giản là lấy token qua manager rồi gắn vào request:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryClient {

    private final InventoryAccessTokenService tokens;
    private final RestClient restClient;

    InventoryClient(InventoryAccessTokenService tokens,
                    RestClient.Builder builder) {
        this.tokens = tokens;
        this.restClient = builder
            .baseUrl("https://inventory.example.test")
            .build();
    }

    InventoryDto getInventory(String sku) {
        String token = tokens.getAccessToken();

        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(InventoryDto.class);
    }
}

record InventoryDto(String sku, int available) {}
~~~

Ở đây Orders API dùng **token service identity** cho request đi ra. Không có token của Alice trong Authorization header này.

### 5.6. Tích hợp OAuth2 Client trực tiếp vào RestClient

Spring Security 7.1 có `OAuth2ClientHttpRequestInterceptor` để dùng `OAuth2AuthorizedClientManager` tự động gắn Bearer token vào outbound request.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration
class InventoryRestClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            OAuth2AuthorizedClientManager manager) {

        OAuth2ClientHttpRequestInterceptor interceptor =
                new OAuth2ClientHttpRequestInterceptor(manager);

        // Principal riêng của application, không gắn theo user hiện tại.
        interceptor.setPrincipalResolver(
                new RequestAttributePrincipalResolver());

        return RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .requestInterceptor(interceptor)
            .build();
    }
}
~~~

Khi gọi:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributePrincipalResolver.principal;

InventoryDto inventory = inventoryRestClient.get()
    .uri("/api/inventory/{sku}", sku)
    .attributes(clientRegistrationId("inventory"))
    .attributes(principal("orders-api"))
    .retrieve()
    .body(InventoryDto.class);
~~~

Interceptor dùng registration ID và principal attributes để tìm/authorize đúng client. Cách này hữu ích khi một ứng dụng gọi nhiều downstream với registrations khác nhau.

**Chú ý:** nếu không cấu hình principal resolver/request attribute phù hợp, interceptor mặc định có thể dùng principal hiện tại trong SecurityContext. Với Client Credentials, điều đó có thể tạo authorized-client records theo từng user trong khi mục tiêu là service identity dùng chung. Chọn principal một cách có chủ đích.

## 6. Chuyển tiếp incoming access token có kiểm soát

Nếu token đi vào đã được phát hành với audience và scope dành cho downstream, có thể dùng token đó trong request đi ra.

Ví dụ controller nhận JWT:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    private final InventoryRelayService inventory;

    OrdersController(InventoryRelayService inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/api/orders/inventory-check")
    InventoryDto checkInventory(@AuthenticationPrincipal Jwt jwt) {
        return inventory.getForUser(jwt, "SKU-42");
    }
}
~~~

Service có thể đọc token value từ JWT đã được xác minh:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryRelayService {

    private final RestClient restClient;

    InventoryRelayService(RestClient.Builder builder) {
        this.restClient = builder
            .baseUrl("https://inventory.example.test")
            .build();
    }

    InventoryDto getForUser(Jwt jwt, String sku) {
        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .headers(headers ->
                headers.setBearerAuth(jwt.getTokenValue()))
            .retrieve()
            .body(InventoryDto.class);
    }
}
~~~

Đoạn code trên chỉ là **cách vận chuyển token**. Nó không tự chứng minh token được phép tới Inventory API. Trước khi dùng, hệ thống phải bảo đảm token đã được Orders API xác minh, audience bao gồm Inventory API, scope đủ cho thao tác, Inventory API tin issuer/profile đó, việc chuyển tiếp phù hợp privacy policy và host downstream đã được cấu hình tin cậy.

Nếu token có `aud` chỉ là `orders-api`, không dùng relay. Hãy yêu cầu AS cấp token đa audience có chủ đích hoặc dùng token exchange để tạo token dành cho Inventory.

### 6.1. Opaque token relay

Với opaque token, principal sau introspection không nhất thiết là `Jwt`. Nếu muốn relay nguyên token, cần lấy token value từ đúng authentication type, ví dụ `BearerTokenAuthentication` theo cấu hình. Không cố gọi `getTokenValue()` trên một principal không có method đó.

Relay opaque token cũng phải thỏa audience, scope và trust contract. Token introspection thành công ở Orders API không tự chứng minh Inventory API sẽ chấp nhận token.

### 6.2. Không tự tạo header từ token chưa xác minh

Không viết filter tự đọc `Authorization` header thô rồi chuyển tiếp token đến một URL tùy ý. Nếu token không qua Resource Server authentication hoặc destination không được allowlist, service có thể trở thành một proxy làm lộ credential.

## 7. Token Exchange với Spring Security

Spring Security có provider cho **Token Exchange**. Theo tài liệu hiện hành, provider này phải được thêm vào `OAuth2AuthorizedClientProvider`; nó không nằm trong bộ provider mặc định như authorization code, refresh token và client credentials.

Token Exchange phù hợp khi inbound token được cấp cho Orders API, Orders API cần token khác cho Inventory API, downstream cần tiếp tục biết user subject, và AS có policy cho phép Orders API exchange token sang audience/scope mới.

### 7.1. Cấu hình registration cho token exchange

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-exchange:
            provider: identity
            client-id: orders-api
            client-secret: ${INVENTORY_EXCHANGE_CLIENT_SECRET}
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            scope:
              - inventory.read
        provider:
          identity:
            token-uri: https://identity.example.test/oauth2/token
~~~

Registration ID `inventory-exchange` là tên local trong ứng dụng. Authorization Server phải hỗ trợ RFC 8693 hoặc extension tương ứng, và phải cho phép client `orders-api` exchange subject token sang audience/resource cần thiết.

### 7.2. Bật TokenExchangeOAuth2AuthorizedClientProvider

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;

@Configuration
class TokenExchangeConfiguration {

    @Bean
    OAuth2AuthorizedClientManager tokenExchangeManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
                new TokenExchangeOAuth2AuthorizedClientProvider();

        OAuth2AuthorizedClientProvider providers =
                OAuth2AuthorizedClientProviderBuilder.builder()
                    .provider(exchangeProvider)
                    .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);
        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
~~~

Đây là cấu hình service-tier. Nếu ứng dụng chạy trong HTTP request context và cần repository gắn theo request/session, có thể dùng `DefaultOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientRepository` tương ứng.

### 7.2.1. Thêm audience hoặc resource theo hợp đồng Authorization Server

`TokenExchangeOAuth2AuthorizedClientProvider` dùng `TokenExchangeGrantRequest` và token response client để gửi request đến token endpoint. Nếu AS yêu cầu tham số bổ sung như `audience` hoặc `resource`, cấu hình `TokenExchangeOAuth2AuthorizedClientProvider` với một `RestClientTokenExchangeTokenResponseClient` tùy chỉnh:

~~~java
import org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

RestClientTokenExchangeTokenResponseClient responseClient =
        new RestClientTokenExchangeTokenResponseClient();

responseClient.addParametersConverter(grantRequest -> {
    MultiValueMap<String, String> parameters =
            new LinkedMultiValueMap<>();

    // "audience" là ví dụ theo AS; AS khác có thể dùng "resource".
    parameters.set("audience", "inventory-api");
    return parameters;
});

TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
        new TokenExchangeOAuth2AuthorizedClientProvider();
exchangeProvider.setAccessTokenResponseClient(responseClient);
~~~

Đây là phần cấu hình bổ sung cho ví dụ manager ở mục 7.2; truyền `exchangeProvider` đã cấu hình vào `OAuth2AuthorizedClientProviderBuilder`. Không gửi cả `audience` và `resource` một cách tùy tiện: chọn tham số theo contract của AS, và xác nhận token response thực sự có audience/scope mong muốn. `resource` theo RFC 8707 là một cách chỉ định resource; `audience` thường là tham số được một số nhà cung cấp hỗ trợ.

### 7.3. Exchange token từ JwtAuthenticationToken

Spring Security mặc định có thể lấy subject token từ principal của `JwtAuthenticationToken`. Ví dụ:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
class InventoryTokenExchangeService {

    private final OAuth2AuthorizedClientManager manager;

    InventoryTokenExchangeService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    OAuth2AuthorizedClient exchange(Authentication incomingAuthentication) {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory-exchange")
                    .principal(incomingAuthentication)
                    .build();

        OAuth2AuthorizedClient authorizedClient =
                manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Token exchange did not return an authorized client");
        }
        return authorizedClient;
    }
}
~~~

Khi authentication là `JwtAuthenticationToken`, provider mặc định lấy `Jwt` từ `Authentication.getPrincipal()` làm subject token. Nếu principal type khác, hoặc subject token đến từ một nguồn khác, phải cấu hình `setSubjectTokenResolver(...)`.

### 7.4. Gửi token mới tới Inventory API

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class ExchangedInventoryClient {

    private final InventoryTokenExchangeService tokenExchange;
    private final RestClient restClient;

    ExchangedInventoryClient(
            InventoryTokenExchangeService tokenExchange,
            RestClient.Builder builder) {
        this.tokenExchange = tokenExchange;
        this.restClient = builder
            .baseUrl("https://inventory.example.test")
            .build();
    }

    InventoryDto getInventory(Authentication incoming, String sku) {
        OAuth2AuthorizedClient exchanged =
                tokenExchange.exchange(incoming);

        String downstreamToken =
                exchanged.getAccessToken().getTokenValue();

        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .headers(headers ->
                headers.setBearerAuth(downstreamToken))
            .retrieve()
            .body(InventoryDto.class);
    }
}
~~~

Token nhận được phải dành cho Inventory API, có scope tối thiểu và vẫn đại diện đúng user/actor theo policy AS. Đừng ghi token này vào log hoặc trả cho browser.

### 7.5. Subject token và actor token

RFC 8693 phân biệt:

- **Subject token**: token đại diện subject mà delegation đang thực hiện thay.
- **Actor token**: token đại diện actor đang thực hiện hành động thay subject.

Trong chuỗi Shop Web → Orders API → Inventory API, token exchange có thể giữ Alice là subject và ghi nhận Orders API là actor, nếu AS hỗ trợ actor token/actor claims. Spring Security `TokenExchangeOAuth2AuthorizedClientProvider` **không tự resolve actor token mặc định**; cần cấu hình `setActorTokenResolver(...)` nếu use case cần.

Đây là khác biệt quan trọng cho audit và delegation chain. Nếu chỉ có subject token, Inventory API có thể thấy Alice nhưng không có đầy đủ bằng chứng service nào đã thực hiện bước gọi.

### 7.6. Token Exchange không tự động downscope

Client phải gửi yêu cầu audience/resource/scope phù hợp và AS phải enforce policy. Chỉ đăng ký grant type token exchange không đảm bảo token mới sẽ có quyền hẹp hơn. Cần kiểm tra response claims/metadata và test token được cấp.

## 8. WebFlux: Resource Server và Reactive OAuth2 Client cùng tồn tại

Trong WebFlux, các thành phần tương ứng là:

| Servlet | Reactive |
| --- | --- |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| `HttpSecurity` | `ServerHttpSecurity` |

### 8.1. Cấu hình WebFlux Resource Server + OAuth2 Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

WebFlux cần cấu hình `ReactiveJwtDecoder` hoặc opaque introspector cho inbound token, cùng OAuth2 Client registrations và reactive authorized-client manager cho outbound.

### 8.2. Reactive Client Credentials manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;

@Configuration
class ReactiveOAuth2ClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp khi chạy ngoài `ServerWebExchange`, ví dụ service-tier/background work. Trong request context WebFlux, dùng `DefaultReactiveOAuth2AuthorizedClientManager` với `ServerOAuth2AuthorizedClientRepository`.

### 8.3. Reactive WebClient gọi downstream

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryWebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://inventory.example.test")
            .filter(oauth)
            .build();
    }
}
~~~

Sử dụng registration cho request:

~~~java
Mono<InventoryDto> inventory =
    inventoryWebClient.get()
        .uri("/api/inventory/{sku}", sku)
        .attributes(clientRegistrationId("inventory"))
        .retrieve()
        .bodyToMono(InventoryDto.class);
~~~

Filter function dùng manager để authorize/re-authorize client và đặt Bearer token vào outbound request. Có thể cung cấp `OAuth2AuthorizedClient` cụ thể hoặc `clientRegistrationId` qua request attributes.

### 8.4. Không mặc định gắn token vào mọi WebClient request

Spring Security cho phép đặt default authorized client hoặc default registration ID trên exchange filter function. Tài liệu khuyến cáo thận trọng vì **mọi request qua WebClient đó có thể nhận access token**.

Tốt hơn:

- Dùng WebClient riêng cho từng downstream trust boundary.
- Chọn registration ID tường minh ở request.
- Không dùng một WebClient có OAuth filter cho URL tùy ý.
- Không cho caller điều khiển host/URI rồi để interceptor gắn token.

### 8.5. Reactive Token Exchange

WebFlux có `TokenExchangeReactiveOAuth2AuthorizedClientProvider` và `WebClientReactiveTokenExchangeTokenResponseClient`. Tương tự Servlet, provider cần được cấu hình rõ và Authorization Server phải hỗ trợ grant/policy.

Khi dùng `JwtAuthenticationToken`, provider có thể lấy subject token từ principal JWT. Nếu cần actor token hoặc nguồn subject token khác, cấu hình resolver reactive tương ứng. Đừng gọi `block()` để lấy token trong WebFlux controller/service; giữ toàn bộ luồng trong `Mono`/`Flux`.

## 9. Chọn principal để lưu authorized client

Một chi tiết dễ bị bỏ qua là **authorized client được gắn với principal name**. Cùng một registration có thể tạo authorized-client record khác nhau theo principal.

| Principal được dùng | Ý nghĩa lưu trữ |
| --- | --- |
| `orders-api` | Một service-level authorized client dùng chung cho service identity |
| `alice` | Authorized client gắn với user Alice |
| `JwtAuthenticationToken` | Có thể dùng principal hiện tại để token exchange/delegation |
| `anonymousUser` | Có thể tạo record chung nếu dùng có chủ đích; thường cần xem lại semantics |

### 9.1. Client Credentials thường dùng application principal

Nếu registration `inventory` dùng `client_credentials`, authorized client thường là service identity. Dùng principal ổn định như `orders-api` sẽ tránh tạo một token cache entry riêng cho từng end user khi không cần.

### 9.2. Delegated token nên gắn theo user/context

Nếu dùng authorization code hoặc token exchange thay mặt user, authorized client có thể cần được phân biệt theo user hoặc delegation context. Nếu mọi user cùng lưu vào principal `orders-api`, token của Alice có thể bị dùng nhầm cho Bob.

Không dùng một principal global cho delegated token trừ khi cache/storage key còn ràng buộc subject/tenant/delegation context theo cách an toàn.

### 9.3. Principal name không phải token subject tự động

Principal dùng để lưu authorized client là key của Spring persistence. Nó không tự thay đổi `sub` bên trong access token. Khi cần audit subject/actor, đọc claims/token theo contract hoặc dùng metadata từ token exchange.

## 10. Token lifetime, refresh và persistence

`OAuth2AuthorizedClientManager` quản lý authorized client, không chỉ lấy token một lần.

### 10.1. Client Credentials

Client Credentials thường không trả refresh token theo nhiều Authorization Server. Khi access token hết hạn, manager có thể yêu cầu token mới bằng client credentials grant. Vì vậy, provider `clientCredentials()` có thể re-authorize khi token hết hạn.

### 10.2. Authorization Code

Nếu authorized client có refresh token và provider `refreshToken()` được cấu hình, manager có thể dùng refresh token để lấy access token mới. Token cũ hoặc refresh token không hợp lệ cần được xử lý theo failure handler.

### 10.3. Token Exchange

Token exchange lifecycle tùy AS và provider. Không giả định mọi token exchanged có refresh token. Khi hết hạn, ứng dụng có thể phải exchange lại từ subject token còn hợp lệ; nếu subject token đã hết hạn, cần luồng xác thực/delegation mới.

### 10.4. Authorized-client storage

Spring có:

- `OAuth2AuthorizedClientRepository`: lưu authorized clients giữa các web requests.
- `OAuth2AuthorizedClientService`: quản lý authorized clients ở application level.
- `InMemoryOAuth2AuthorizedClientService`: mặc định in-memory trong một số cấu hình.
- `JdbcOAuth2AuthorizedClientService`: lưu trữ bằng JDBC.

Chọn storage theo số replica, restart, scale và mức độ nhạy cảm. Nếu nhiều instance cùng cần một authorized client, storage in-memory có thể dẫn đến nhiều lần xin token và không chia sẻ cache. JDBC/shared store giúp persistence nhưng phải bảo vệ token tại rest/in transit và quản lý retention.

### 10.5. Xóa authorized client khi downstream báo token invalid

Spring Security hỗ trợ authorization failure handler để xóa authorized client bị invalid, ví dụ downstream trả `invalid_token`. Cấu hình handler phù hợp giúp lần request sau manager có thể xin token mới.

Không xóa authorized client một cách mù quáng cho mọi lỗi 401/403:

- 401 có thể là token hết hạn/invalid.
- 403 thường có thể là scope/permission thiếu; xin token mới liên tục không giải quyết policy.
- 5xx/timeout không chứng minh token invalid.

## 11. Token audience và scope ở downstream

Audience trả lời: **token được cấp cho Resource Server nào?** Scope trả lời: **token cho phép loại thao tác nào?**

Ví dụ:

~~~json
{
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Không nên gửi token này tới Inventory API rồi yêu cầu Inventory API chấp nhận chỉ vì issuer giống nhau.

Token cho downstream có thể cần:

~~~json
{
  "aud": ["inventory-api"],
  "scope": "inventory.read"
}
~~~

### 11.1. Downstream không nên tin mọi token do cùng issuer phát

Inventory API cần xác minh issuer được tin cậy, audience chứa Inventory API, token còn hiệu lực, scope/authority đủ cho endpoint, token type/profile phù hợp, và tenant/owner/business authorization nếu cần.

Issuer chung không đồng nghĩa audience chung. Một token hợp lệ cho Orders API vẫn có thể không hợp lệ cho Inventory API.

### 11.2. Downscoping

Khi exchange, nên xin quyền tối thiểu cho downstream:

~~~text
Inbound token:
    aud = orders-api
    scope = orders.read orders.cancel inventory.read inventory.write

Exchanged token:
    aud = inventory-api
    scope = inventory.read
~~~

Ví dụ minh họa: token mới chỉ giữ scope mà Inventory API cần. AS phải enforce việc downscope; Orders API không tự xóa claim trong token cũ rồi coi đó là token mới hợp lệ.

### 11.3. Tenant và user context

Nếu Inventory API phân quyền theo tenant, token exchange hoặc Client Credentials phải có tenant context được cấp theo policy. Không lấy `X-Tenant-Id` do caller tự gửi rồi đưa vào token request như bằng chứng membership.

Với service token, có thể cần scope riêng cho tenant operations hoặc policy kiểm tra membership bằng service identity. Với delegated token, giữ user subject và tenant context theo hợp đồng AS/downstream.

## 12. Token relay và token exchange: quyết định bằng audience

**Trường hợp 1: Token đa audience có chủ đích**

~~~text
Inbound token:
  aud = [orders-api, inventory-api]
  scope = orders.read inventory.read

Orders API -> Inventory API:
  có thể relay token nếu contract cho phép
~~~

**Trường hợp 2: Token chỉ dành cho Orders API**

~~~text
Inbound token:
  aud = orders-api
  scope = orders.read

Orders API -> Inventory API:
  không relay
  -> Client Credentials nếu chỉ cần service identity
  -> Token Exchange nếu cần user delegation
~~~

### 12.1. Không sửa audience trong JWT

Không lấy token inbound, decode payload, sửa `aud` thành `inventory-api` rồi gửi tiếp. Chữ ký sẽ không còn hợp lệ. Cũng không ký lại token bằng private key của Orders API rồi tự nhận đó là access token của AS.

Chỉ Authorization Server mới được cấp access token theo policy của nó. Token Exchange là cách chuẩn để yêu cầu token mới.

## 13. Security risks khi Resource Server cũng là OAuth2 Client

### 13.1. Confused deputy

Orders API có quyền gọi Inventory API bằng service token. Nếu endpoint cho Client truyền URL tùy ý và Orders API gắn token vào request, attacker có thể khiến service gửi credential đến host của attacker.

**Giải pháp:** allowlist destination host, dùng client riêng cho downstream cụ thể, không lấy URI tùy ý từ request, và chỉ thêm Authorization header sau khi đã xác định destination đáng tin.

### 13.2. Token leakage qua log/trace

Không log:

- Inbound `Authorization` header.
- Outbound `Authorization` header.
- Access/refresh token value.
- Token response body.
- Client secret/private key.

Trace có thể ghi destination, registration ID, status, latency và correlation ID nhưng cần che credential. Cấu hình HTTP wiretap/debug log phải được xem xét kỹ.

### 13.3. Over-privileged service token

Client Credentials token đại diện service. Nếu cấp `inventory.admin` cho Orders API trong khi chỉ cần `inventory.read`, mọi lỗi SSRF/compromise ở Orders API có thể mở rộng thành quyền admin tồn kho.

Yêu cầu scope tối thiểu, audience cụ thể và policy service account riêng.

### 13.4. Delegation confusion

Nếu Orders API dùng Client Credentials thay cho delegated token, Inventory API có thể chỉ thấy service identity và không kiểm tra được quyền của user. Ngược lại, nếu relay inbound token quá rộng, Inventory có thể nhận token có scope không cần thiết.

Chọn rõ service identity hay user delegation, không trộn hai ý nghĩa.

### 13.5. User/tenant context bị dùng sai khi cache

Authorized-client cache cần key theo principal/context phù hợp. Nếu token exchange của Alice được lưu dưới principal global `orders-api`, Bob có thể nhận token đại diện Alice. Nếu Client Credentials dùng principal theo từng user, cache lại phình to không cần thiết.

### 13.6. Redirect và outbound host

Nếu HTTP client tự follow redirect từ host trusted sang host khác, cần bảo đảm Authorization header không bị chuyển tiếp ngoài ý muốn. Cấu hình redirect policy, allowlist và kiểm thử redirect sang external host.

### 13.7. Retry có thể tạo nhiều token request

Retry toàn bộ pipeline khi Authorization Server timeout có thể tạo nhiều token requests và làm tăng tải. Dùng timeout, retry có backoff/jitter và chỉ retry lỗi transient; không retry liên tục `invalid_client`/`invalid_scope`.

### 13.8. Inbound token hết hạn giữa workflow

Một request dài có thể bắt đầu khi token còn hạn nhưng token hết hạn trước khi service exchange hoặc downstream xử lý. Thiết kế token lifetime, timeout và re-auth/delegation phù hợp; không bỏ validation để hoàn tất workflow.

## 14. Xử lý lỗi giữa các service

| Lỗi outbound | Cách hiểu | Hành động thường phù hợp |
| --- | --- | --- |
| Token endpoint `invalid_client` | Client credentials sai/không được phép | Báo lỗi cấu hình, không retry vô hạn |
| Token endpoint `invalid_scope` | Scope yêu cầu không được cấp | Sửa policy/request, không giảm validation |
| Token exchange `invalid_grant` | Subject token không hợp lệ/không đủ điều kiện | Kiểm tra inbound token/delegation; không fallback sang quyền service cao hơn |
| Token endpoint timeout/5xx | AS tạm thời không sẵn sàng | Timeout/backoff/circuit breaker |
| Downstream 401 `invalid_token` | Token đi ra không được chấp nhận | Có thể xóa authorized client và authorize lại theo handler |
| Downstream 403 | Token hợp lệ nhưng không đủ quyền | Không retry bằng token mạnh hơn; xử lý authorization denial |
| Downstream 404 | Resource không tồn tại/không hiển thị | Giữ contract API, không tự đổi credential |
| Downstream 429 | Rate limit | Respect Retry-After và backoff |
| Downstream 5xx | Lỗi service đích | Retry có kiểm soát nếu thao tác idempotent |

**Không chuyển mọi lỗi downstream thành 401 cho Client gọi Orders API.** Inbound token có thể hoàn toàn hợp lệ; lỗi nằm ở token outbound, AS hoặc Inventory API. Ánh xạ lỗi phải giữ đúng ranh giới và không tiết lộ token/secret.

## 15. Ví dụ tổng hợp: Orders API dùng Client Credentials

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant S as Shop Web
    participant AS as Authorization Server
    participant O as Orders API
    participant I as Inventory API

    U->>S: Xem đơn hàng
    S->>O: Bearer token dành cho Orders API
    O->>O: Resource Server xác minh JWT + orders.read
    O->>O: Kiểm tra Alice có quyền xem order
    O->>AS: Client Credentials cho inventory.read
    AS-->>O: Token service identity, aud=inventory-api
    O->>I: Bearer token service identity
    I->>I: Xác minh aud + inventory.read
    I-->>O: Tồn kho
    O-->>S: Kết quả đơn hàng
~~~

Trong luồng này:

- Inbound token xác định Alice.
- Outbound token xác định Orders API.
- Inventory API chỉ thấy service identity.
- Nếu Inventory cần kiểm tra quyền Alice, Client Credentials không đủ; chuyển sang token exchange/relay theo contract.

## 16. Ví dụ tổng hợp: Orders API exchange token thay Alice

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant S as Shop Web
    participant AS as Authorization Server
    participant O as Orders API
    participant I as Inventory API

    U->>S: Xem thông tin tồn kho liên quan đơn
    S->>O: Inbound token T1 (aud=orders-api)
    O->>O: Verify T1 và authorization
    O->>AS: Token Exchange: subject_token=T1, audience=inventory-api, scope=inventory.read
    AS->>AS: Kiểm tra client, user, grant và delegation policy
    AS-->>O: Token T2 (aud=inventory-api)
    O->>I: Bearer T2
    I->>I: Verify T2, subject, scope và tenant policy
    I-->>O: Tồn kho được phép xem
    O-->>S: Response
~~~

T2 là token mới được AS cấp. Inventory API có thể thấy Alice là subject, còn Orders API có thể được ghi nhận là actor nếu token exchange dùng actor token/claim theo policy.

## 17. Test khi một service vừa Resource Server vừa OAuth2 Client

Một test suite nên chia theo inbound, outbound và end-to-end:

| Nhóm | Điều cần xác nhận |
| --- | --- |
| Inbound Resource Server | Token sai chữ ký/issuer/audience/expiry bị từ chối; scope và user policy đúng |
| Client Credentials | Đúng client registration, grant type, client authentication và scope |
| Token relay | Token đi ra đúng là inbound token; chỉ dùng với audience/scope phù hợp |
| Token Exchange | Subject token đúng, audience/resource và scope đúng; actor token nếu cần |
| Authorized-client persistence | Principal key không làm trộn user/service |
| Refresh/re-authorize | Token hết hạn được xin lại; invalid_grant xử lý đúng |
| Downstream request | Authorization scheme/token đúng, không gửi token đến host không tin |
| Error handling | 401/403/429/5xx được phân loại; retry và remove-authorized-client đúng |
| Secret/logging | Không xuất hiện token, refresh token hoặc client secret trong logs |

### 17.1. Mock Authorization Server và downstream

Có thể dùng WireMock/MockWebServer hoặc một test Authorization Server để:

1. Nhận token request.
2. Xác minh `grant_type` và client authentication.
3. Trả access token test có expiry/scope/audience theo scenario.
4. Nhận outbound request từ Orders API.
5. Xác minh Authorization header đúng token mong đợi.

Với JWT inbound, dùng JWT ký bằng test key và Resource Server decoder thật cho integration test. Với unit test service, có thể mock `JwtAuthenticationToken` hoặc manager, nhưng phải có test pipeline thật để chứng minh filter/decoder hoạt động.

### 17.2. Test Client Credentials không phụ thuộc end-user

Gửi request với hai users khác nhau:

~~~text
Alice -> Orders API -> Inventory API
Bob   -> Orders API -> Inventory API
~~~

Nếu outbound identity là Orders API, token service-level có thể được tái sử dụng theo principal `orders-api`. Test xác nhận:

- Inventory API nhận service token đúng.
- Không có token Alice/Bob bị gửi nhầm.
- Cache không tạo hoặc trộn user-specific authorized client ngoài ý muốn.

### 17.3. Test token relay đúng audience

Scenario:

- Token A có audience `orders-api` và scope `orders.read`.
- Orders API nhận A hợp lệ.
- Inventory API chỉ chấp nhận audience `inventory-api`.

Kỳ vọng: Orders API **không relay A** đến Inventory như thể token đó hợp lệ. Test cần chứng minh API chọn exchange/service token hoặc từ chối theo policy.

### 17.4. Test token exchange

Test token request có:

~~~text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=T1
subject_token_type=urn:ietf:params:oauth:token-type:access_token
scope=inventory.read
audience=inventory-api
~~~

Các tham số cụ thể có thể khác theo AS contract; điều cần xác nhận là subject token, target audience/resource và scope được truyền đúng. Sau đó kiểm tra downstream nhận T2, không phải T1.

Negative cases:

- Subject token hết hạn.
- Client không được phép exchange.
- Scope vượt policy.
- Audience/resource không được AS cho phép.
- Actor token sai hoặc thiếu khi policy yêu cầu.
- AS timeout hoặc trả `invalid_grant`.

### 17.5. Test principal isolation

Đối với delegated token:

~~~text
Alice -> token exchange -> T_A (sub=alice)
Bob   -> token exchange -> T_B (sub=bob)
~~~

Test xác nhận authorized-client storage key không làm T_A được trả cho Bob. Đối với Client Credentials:

~~~text
principal=orders-api -> service token
~~~

Test xác nhận service token không bị cache thành một user token hoặc ngược lại.

### 17.6. Test downstream 401 và 403

- Downstream trả `401 invalid_token`: kiểm tra failure handler có xóa authorized client invalid nếu cấu hình.
- Request sau: manager có thể authorize lại.
- Downstream trả `403 insufficient_scope`: không lặp lại token request vô hạn hoặc tự tăng scope.
- Downstream trả `500`: không xóa authorized client chỉ vì lỗi server.

## 18. Những hiểu nhầm phổ biến

**“Resource Server đã xác minh token nên có thể dùng token đó gọi mọi service.”** Sai. Audience và scope có thể chỉ dành cho service hiện tại.

**“Chỉ cần bật `oauth2Client()` là Spring tự biết token outbound.”** Không. Cần chọn ClientRegistration, principal và grant/provider.

**“Client Credentials đại diện cho user đang đăng nhập.”** Không. Nó đại diện OAuth2 Client/service.

**“Token relay luôn tốt hơn token exchange vì không phải gọi token endpoint.”** Không. Relay có thể vi phạm audience, scope và delegation policy.

**“Token Exchange tự động được bật cùng client_credentials.”** Không. Token Exchange provider cần được đăng ký/cấu hình theo tài liệu.

**“Token exchange là Orders API tự ký lại JWT.”** Không. AS cấp token mới theo policy.

**“Token exchange luôn downscope.”** Không. Client cần yêu cầu đúng scope/resource và AS phải enforce.

**“Một token đổi được thì không cần kiểm tra downstream authorization.”** Sai. Downstream vẫn kiểm tra audience, scope, tenant, owner và business policy.

**“Dùng principal hiện tại cho mọi outbound client là an toàn.”** Không. Client Credentials có thể cần application principal; delegated token cần user/context riêng.

**“Dùng một WebClient có default OAuth client cho mọi host.”** Rủi ro gửi token tới destination không mong muốn. Dùng client riêng và registration tường minh.

**“Token 401 từ downstream nghĩa inbound token của user sai.”** Không nhất thiết. Có thể outbound token hết hạn/invalid hoặc audience sai.

**“403 thì xin token mới mạnh hơn.”** Không. 403 thường là authorization denial; không tự nâng quyền.

**“Service token có scope rộng giúp downstream đơn giản hơn.”** Nó mở rộng blast radius khi service bị compromise. Cấp scope nhỏ nhất.

**“WebFlux có thể gọi manager bằng `block()`.”** Không nên trong reactive pipeline; giữ `Mono`/`Flux` để tránh block event loop.

## 19. Checklist triển khai

### Inbound Resource Server

- [ ] Xác minh signature/introspection, issuer, audience, expiry và token profile.
- [ ] Kiểm tra scope/authority của endpoint.
- [ ] Kiểm tra owner, tenant và business policy trước khi xử lý.
- [ ] Không coi inbound token là credential cho mọi downstream.

### Outbound OAuth2 Client

- [ ] Mỗi downstream có ClientRegistration và audience/scope phù hợp.
- [ ] Chọn rõ Client Credentials, token relay hay token exchange.
- [ ] Chọn principal phù hợp: service-level hoặc user/delegation context.
- [ ] Dùng OAuth2AuthorizedClientManager hoặc ReactiveOAuth2AuthorizedClientManager.
- [ ] Chọn authorized-client repository/service phù hợp lifecycle và số replica.
- [ ] Cấu hình refresh/re-authorize và failure handler.
- [ ] Không gửi token tới URL tùy ý.
- [ ] Không log token/secret.

### Delegation/token exchange

- [ ] Authorization Server hỗ trợ grant và policy.
- [ ] Subject token là token inbound đã xác minh.
- [ ] Target audience/resource đúng downstream.
- [ ] Scope được downscope theo least privilege.
- [ ] Actor token được cấu hình nếu cần audit delegation chain.
- [ ] Token exchange failure không fallback sang service privilege cao hơn ngoài policy.

### WebFlux

- [ ] Dùng Reactive manager/provider/repository.
- [ ] Không gọi `block()` trong request pipeline.
- [ ] Chọn đúng manager trong/ngoài ServerWebExchange.
- [ ] Chọn WebClient và registration cụ thể cho từng downstream.

## 20. Tình huống thực hành

**A.** Orders API nhận JWT audience `orders-api`, cần gọi Inventory API. Có thể gửi nguyên token không?

**Không**, trừ khi token contract có audience phù hợp cho Inventory. Nếu không, dùng Client Credentials nếu chỉ cần service identity, hoặc Token Exchange nếu cần user delegation.

**B.** Inventory API chỉ cần biết Orders API đang gọi. Nên chọn grant nào?

Thường là **Client Credentials** với audience Inventory và scope tối thiểu.

**C.** Inventory cần kiểm tra quyền của Alice, nhưng token inbound chỉ dành cho Orders API. Nên làm gì?

Dùng **Token Exchange/OBO** nếu AS hỗ trợ, lấy token mới dành cho Inventory và đại diện Alice theo policy.

**D.** Có thể dùng `DefaultOAuth2AuthorizedClientManager` trong scheduler không?

Manager này được thiết kế cho `HttpServletRequest` context. Với service/background, dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

**E.** WebFlux scheduler cần token Client Credentials. Dùng manager nào?

Dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` ngoài `ServerWebExchange`, cùng reactive client registration/service.

**F.** Token Exchange provider có tự resolve actor token không?

Không mặc định. Nếu cần actor token, cấu hình `setActorTokenResolver` theo API phù hợp.

**G.** Downstream trả 403 vì thiếu scope. Có nên tự xin token với scope admin?

Không. Sửa authorization policy/request theo nhu cầu được phê duyệt; không tự nâng quyền.

**H.** Một WebClient mặc định gắn access token cho mọi request có an toàn không?

Rủi ro. Chọn client registration theo request và giới hạn host/destination đáng tin.

**I.** Hai người dùng Alice và Bob cùng gọi Orders API; token exchange của Alice được cache bằng principal chung `orders-api`. Có vấn đề gì?

Có. Có thể trả token Alice cho Bob. Delegated authorized client phải được phân biệt theo user/delegation context.

**J.** Orders API đã xác minh inbound JWT, vậy có thể bỏ kiểm tra quyền trong Inventory API?

Không. Inventory API phải xác minh outbound token của nó và kiểm tra quyền tài nguyên theo policy riêng.

---

## Kết luận

Một ứng dụng **Spring Security Resource Server có thể đồng thời là OAuth2 Client**. Ở chiều vào, Resource Server xác minh access token và quyền của caller. Ở chiều ra, OAuth2 Client quản lý authorized client và access token dành cho downstream. Hai luồng có thể liên quan nhưng không tự động dùng chung credential.

Hãy chọn **Client Credentials** khi downstream chỉ cần danh tính service; **token relay** khi inbound token đã được phát hành cho downstream và có đúng scope; **Token Exchange/OBO** khi cần token mới dành cho downstream nhưng vẫn giữ delegation của người dùng. Spring Security cung cấp `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager`, provider và WebClient/RestClient integration để quản lý token; Token Exchange cần provider được cấu hình rõ và Authorization Server phải hỗ trợ policy.

Trong mọi trường hợp, kiểm tra **audience, scope, principal, tenant và quyền tài nguyên** ở từng ranh giới. Không chuyển tiếp token tới host không tin, không gắn service token quá rộng, không cache token của user dưới principal global, và không log credential. **Một service có thể đóng hai vai trò OAuth2 trong cùng request flow, nhưng phải xác định rõ danh tính nào đang được đại diện ở mỗi outbound call.**

## Tài liệu tham khảo

1. [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/)
2. [Spring Security — Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
3. [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
4. [Spring Security 7.1 — Authorization Grant Support / Token Exchange](https://docs.spring.io/spring-security/reference/7.1/servlet/oauth2/client/authorization-grants.html)
5. [Spring Security — Reactive OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/)
6. [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html)
7. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html)
