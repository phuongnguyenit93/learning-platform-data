# ServletBearerExchangeFilterFunction và hỗ trợ WebClient trong Servlet

Trong một ứng dụng Spring MVC được bảo vệ bởi Spring Security Resource Server, request đến có thể mang access token trong header Authorization. Sau khi Resource Server xác minh token, ứng dụng đôi khi cần gọi một API khác thay mặt người dùng hiện tại. **ServletBearerExchangeFilterFunction** giúp chuyển tiếp Bearer token đang gắn với Authentication hiện tại vào request outbound do **WebClient** thực hiện.

Đây là một chức năng **token relay**: ứng dụng chuyển tiếp access token đã nhận và đã xác minh. Filter không xin token mới, không refresh token hết hạn, không đổi audience, không thêm scope và không biến token của người dùng thành token định danh của service.

Cần phân biệt hai nhu cầu:

- **Chuyển tiếp token người dùng:** downstream cần nhận đúng access token đã được gửi tới Resource Server hiện tại. Dùng ServletBearerExchangeFilterFunction.
- **Lấy access token theo OAuth2 client registration:** ứng dụng cần token riêng cho một client/service, có thể cần client_credentials, authorization_code hoặc refresh. Dùng ServletOAuth2AuthorizedClientExchangeFilterFunction cùng OAuth2AuthorizedClientManager.

Bài học giải thích cách tích hợp WebClient trong Servlet, cơ chế lấy Authentication, cách cấu hình filter, ranh giới audience/scope, lỗi thường gặp, bảo vệ token khỏi bị gửi nhầm đích và cách kiểm thử.

## 1. Token relay trong kiến trúc nhiều service

Giả sử người dùng gọi Orders API bằng access token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer user-access-token
~~~

Orders API xác minh token rồi cần gọi Inventory API để lấy thông tin hàng hóa.

~~~mermaid
sequenceDiagram
    participant U as User / Client
    participant O as Orders API (Servlet)
    participant S as Spring Security
    participant W as WebClient
    participant I as Inventory API

    U->>O: GET /api/orders/42 + Bearer token
    O->>S: Xác minh access token
    S-->>O: Authentication đã xác thực
    O->>W: Gọi Inventory API
    W->>W: ServletBearerExchangeFilterFunction
    W->>I: Authorization: Bearer cùng access token
    I->>I: Xác minh token và kiểm quyền
    I-->>W: Inventory response
    W-->>O: Mono response
    O-->>U: Orders response
~~~

**ServletBearerExchangeFilterFunction** tự thêm header Authorization cho outbound request nếu tìm thấy một OAuth2 token credential gắn với Authentication hiện tại.

Inventory API vẫn phải tự xác minh token. Việc Orders API đã xác thực không khiến Inventory API tự tin rằng request là hợp lệ.

### 1.1. Vì sao cần token relay?

Token relay hữu ích khi:

- Một request của người dùng đi qua nhiều API.
- Downstream cần biết danh tính và quyền của người dùng gốc.
- Downstream tự áp dụng authorization theo scope, role hoặc tenant.
- Hệ thống có một trust domain chung và access token được phát hành cho nhiều resource phù hợp.
- Ứng dụng trung gian không cần đổi client identity hoặc xin token khác.

Ví dụ: Orders API nhận token có scope orders.read và chuyển tiếp token đó tới một service downstream được phép nhận cùng access token. Downstream kiểm scope và audience theo policy của chính nó.

### 1.2. Token relay không phải token exchange

Relay giữ nguyên access token. **Token exchange** tạo một token mới theo một authorization contract khác, thường có audience/resource hoặc scope được giới hạn cho downstream.

Nếu token đầu vào chỉ có audience orders-api, không mặc định token đó hợp lệ cho inventory-api. Chuyển tiếp nguyên token có thể khiến Inventory API trả 401/403 vì audience hoặc scope không phù hợp.

Khi downstream cần token riêng, hãy dùng OAuth2 Client hoặc một token exchange flow được Authorization Server hỗ trợ, thay vì cố sửa payload JWT hoặc chỉ đổi header.

## 2. ServletBearerExchangeFilterFunction là gì?

Lớp này thuộc package:

~~~java
org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction
~~~

Nó triển khai **ExchangeFilterFunction** của Spring WebClient. Vì vậy có thể đăng ký nó vào WebClient builder như một filter outbound.

Cấu hình tối thiểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class DownstreamWebClientConfiguration {

    @Bean
    WebClient downstreamWebClient() {
        return WebClient.builder()
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Khi WebClient thực hiện request, filter tìm Authentication hiện tại và lấy credential nếu credential là một **AbstractOAuth2Token**. Nếu tìm thấy, nó đặt token value vào header:

~~~http
Authorization: Bearer <token-value>
~~~

Đây là hành vi được Spring Security Resource Server mô tả trong phần **Bearer Token Propagation**.

### 2.1. Filter lấy token từ đâu?

Authentication đã xác thực thường được giữ trong SecurityContext. Servlet stack mặc định dùng SecurityContextHolder, thường dựa trên ThreadLocal trong request processing.

Javadoc của ServletBearerExchangeFilterFunction mô tả việc tìm Authentication trong **Reactor Context** với key kiểu Authentication. Điều này phản ánh cách filter tích hợp với publisher của WebClient. Khi dùng trong luồng request Servlet được Spring Security quản lý, hãy giữ publisher gắn với request lifecycle và sử dụng context propagation theo cấu hình Spring đang chạy.

Không nên giả định SecurityContextHolder ThreadLocal tự xuất hiện trên mọi thread tùy ý. Nếu tự tạo raw thread, tự subscribe publisher tách khỏi request hoặc đẩy công việc sang một execution boundary không truyền context, filter có thể không tìm thấy Authentication.

### 2.2. Credential phải là AbstractOAuth2Token

Filter không chuyển tiếp mọi loại Authentication.

| Authentication hiện tại | Có thể relay bằng filter này? | Giải thích |
|---|---|---|
| JwtAuthenticationToken từ Resource Server | Có, nếu credential là AbstractOAuth2Token | JWT được xác minh và gắn với Authentication |
| OpaqueTokenAuthenticationToken | Có, nếu credential là OAuth2 token | Token opaque cũng có thể là AbstractOAuth2Token |
| UsernamePasswordAuthenticationToken | Không | Credential thường là password, không phải OAuth2 token |
| AnonymousAuthenticationToken | Không | Không có OAuth2 access token credential |
| OAuth2AuthenticationToken từ oauth2Login | Không nên giả định | OAuth2 Login lưu authorized client riêng; dùng OAuth2 Client filter để lấy access token |
| Authentication custom | Tùy implementation | Credential phải là AbstractOAuth2Token |

Một trường hợp không có token phù hợp không tự làm filter phát sinh access token mới. Request được chuyển tiếp theo filter chain mà không có token relay.

### 2.3. Filter không tự xác minh token lần nữa

Filter này không phải JwtDecoder hoặc OpaqueTokenIntrospector. Nó không:

- Xác minh chữ ký JWT.
- Gọi introspection endpoint.
- Kiểm issuer hoặc audience.
- Kiểm exp rồi refresh.
- Thêm authority.
- Chuyển scope.
- Tạo OAuth2AuthorizedClient.
- Đổi token thành token dành cho downstream.

Nó chỉ chuyển tiếp token credential gắn với Authentication hiện tại. Việc xác minh inbound token thuộc Resource Server; việc xác minh outbound token thuộc downstream Resource Server.

## 3. Cấu hình WebClient cho Servlet application

WebClient nằm trong Spring WebFlux API nhưng có thể dùng như HTTP client trong ứng dụng Spring MVC/Servlet. Dùng WebClient **không tự biến ứng dụng Spring MVC thành WebFlux server**.

Để sử dụng WebClient, dự án cần Spring WebFlux client API và một HTTP connector phù hợp, ví dụ Reactor Netty. Với Spring Boot, có thể dùng dependency management để chọn phiên bản tương thích với Spring Framework/Security.

Ví dụ Gradle dependencies:

~~~groovy
dependencies {
    implementation("org.springframework:spring-webflux")
    implementation("io.projectreactor.netty:reactor-netty")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
~~~

Nếu dự án đã quản lý dependency bằng Spring Boot BOM, không tự đặt phiên bản Spring WebFlux hoặc Reactor Netty khác với phiên bản tương thích.

### 3.1. Tạo WebClient chuyên biệt cho downstream

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://inventory.internal.example")
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Ví dụ dùng một base URL ổn định. Trong thực tế, có thể thêm:

- Connect/response timeout phù hợp.
- Connection pool và giới hạn pending requests.
- TLS trust configuration.
- Observability/correlation ID.
- Response body size limits.
- Error handling theo API contract.

**Không gắn filter token relay vào một WebClient dùng cho mọi URL bên ngoài.** Filter sẽ có cơ hội thêm token vào tất cả request phù hợp được gửi qua client đó.

### 3.2. Gọi downstream từ một service

~~~java
import java.time.Duration;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
class InventoryService {

    private final WebClient inventoryWebClient;

    InventoryService(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    Inventory findInventory(String productId) {
        return this.inventoryWebClient.get()
            .uri("/api/inventory/{id}", productId)
            .retrieve()
            .bodyToMono(Inventory.class)
            .block(Duration.ofSeconds(3));
    }
}
~~~

Đây là ví dụ đồng bộ cho một service được gọi từ Servlet/MVC. **block(Duration)** chờ kết quả và giữ servlet request thread trong thời gian outbound call. Timeout giúp giới hạn thời gian chờ, nhưng không biến đoạn code thành nonblocking ở phía caller.

Nếu muốn dùng asynchronous return type trong Spring MVC, có thể trả Mono/CompletableFuture theo khả năng của phiên bản/framework. Khi đó cần kiểm thử context propagation trong request lifecycle thực tế. Không tự gọi subscribe() bên trong controller/service để tách outbound call khỏi response lifecycle.

### 3.3. Controller minh họa

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryController {

    private final InventoryService inventoryService;

    InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @GetMapping("/api/products/{id}/inventory")
    ResponseEntity<Inventory> inventory(@PathVariable String id) {
        Inventory inventory = this.inventoryService.findInventory(id);
        return ResponseEntity.ok(inventory);
    }
}
~~~

Controller không cần tự đọc Authorization header rồi copy sang WebClient. Filter xử lý việc relay từ Authentication theo cơ chế Spring Security.

## 4. Cách hoạt động khi WebClient gửi request

Có thể mô tả filter như sau:

~~~text
WebClient request được subscribe
  -> ServletBearerExchangeFilterFunction chạy
  -> tìm Authentication trong security/reactor context
  -> lấy Authentication.credentials
  -> credentials có phải AbstractOAuth2Token?
       Có:
         lấy tokenValue
         thêm Authorization: Bearer <token>
       Không:
         không thêm token
  -> gửi request qua ExchangeFunction tiếp theo
~~~

Đây là mô tả hành vi, không phải code nội bộ của Spring Security.

### 4.1. Request đã có Authorization header

Nếu ứng dụng chủ động đặt Authorization header cho request cụ thể, filter có thể để nguyên header đó và chuyển tiếp request.

Ví dụ:

~~~java
return inventoryWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .headers(headers ->
        headers.setBearerAuth(serviceSpecificToken))
    .retrieve()
    .bodyToMono(Inventory.class);
~~~

Khi request đã có Authorization header do caller đặt, hành vi override được tài liệu Spring Security mô tả là filter không thay thế nó và chuyển request tiếp.

Điều này hữu ích khi một request cụ thể phải dùng token riêng. Tuy nhiên, **không trộn token người dùng và token service một cách tùy tiện**. Hãy ghi rõ token nào đại diện cho principal nào và downstream được phép nhận loại credential nào.

### 4.2. Không có Authentication phù hợp

Các trường hợp:

- Request public chưa được authenticate.
- Authentication là AnonymousAuthenticationToken.
- Authentication không có OAuth2 token credential.
- Publisher không nhận được Authentication trong Reactor Context.

Khi đó filter không có token phù hợp để relay. Request vẫn có thể được gửi đi mà không có Authorization header, và downstream sẽ tự áp dụng chính sách của nó.

Nếu downstream bắt buộc authentication, response có thể là 401. Không coi việc WebClient call đã được tạo thành công là bằng chứng token đã được chuyển tiếp.

## 5. Token relay không refresh access token hết hạn

Một điểm cần nhớ nhất:

**ServletBearerExchangeFilterFunction không cố gắng renew token nếu token đã hết hạn.**

Giả sử:

~~~text
Inbound request được xác thực lúc 10:00
Access token exp lúc 10:01
Ứng dụng gọi downstream lúc 10:02
~~~

Filter vẫn có thể chuyển tiếp token credential hiện tại. Downstream xác minh exp và từ chối token hết hạn.

Filter không gọi token endpoint, không sử dụng refresh token và không tự tạo access token mới.

### 5.1. Khi nào nên dùng OAuth2 Client filter?

Nếu ứng dụng cần:

- Xin access token khi chưa có authorized client.
- Dùng client_credentials để đại diện cho service.
- Lấy authorized client theo client registration.
- Refresh access token bằng refresh_token grant khi provider hỗ trợ.
- Quản lý authorized client lifecycle và failure handling.

thì sử dụng **ServletOAuth2AuthorizedClientExchangeFilterFunction** cùng **OAuth2AuthorizedClientManager**.

Đây là hai cơ chế khác nhau:

| Tiêu chí | ServletBearerExchangeFilterFunction | ServletOAuth2AuthorizedClientExchangeFilterFunction |
|---|---|---|
| Nguồn token | Credential gắn với Authentication hiện tại | OAuth2AuthorizedClient được manager quản lý |
| Mục đích | Relay access token inbound | Xin/dùng token của OAuth2 client registration |
| Lấy token mới | Không | Có thể, tùy provider/grant |
| Refresh token | Không | Có thể, nếu refresh provider được cấu hình |
| Client credentials | Không tự xin | Có thể hỗ trợ |
| Audience/scope riêng | Không tự đổi token | Theo client registration/authorization server policy |
| Cách chỉ định | Current Authentication | Client registration/authorized client request attributes |

## 6. OAuth2AuthorizedClientManager và WebClient

Khi ứng dụng gọi downstream bằng danh tính service riêng, cấu hình OAuth2 Client.

### 6.1. Tạo OAuth2AuthorizedClientManager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class OAuth2ClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
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

Ví dụ dùng AuthorizedClientServiceOAuth2AuthorizedClientManager cho service-level authorized clients. Với request gắn với HttpServletRequest/HttpServletResponse, có thể dùng DefaultOAuth2AuthorizedClientManager và OAuth2AuthorizedClientRepository theo hướng dẫn Spring Security.

### 6.2. Tạo WebClient bằng OAuth2 Client filter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class OAuth2WebClientConfiguration {

    @Bean
    WebClient serviceWebClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .baseUrl("https://inventory.internal.example")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Để chọn registration cụ thể cho request:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

return serviceWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .attributes(clientRegistrationId("inventory-service"))
    .retrieve()
    .bodyToMono(Inventory.class);
~~~

Registration ID phải khớp cấu hình OAuth2 Client trong ứng dụng. Authorization Server phải cho phép client đó xin access token có audience/scope phù hợp.

### 6.3. Client credentials khác user token relay

Khi dùng client_credentials, downstream thường thấy service client là caller. Nó không tự biết user gốc đang thực hiện request nào, trừ khi ứng dụng truyền context người dùng theo một cơ chế được thiết kế riêng.

Khi relay user token, downstream có thể xác thực user gốc nếu token dành cho downstream và issuer policy cho phép.

Không chọn client_credentials chỉ vì token relay hết hạn; hai cách đại diện cho **hai principal/trust contracts khác nhau**.

## 7. Audience, scope và downstream authorization

Giả sử inbound token:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Orders API có thể xác minh token vì audience là orders-api. Nhưng Inventory API yêu cầu:

~~~json
{
  "aud": ["inventory-api"],
  "scope": "inventory.read"
}
~~~

Việc relay token nguyên vẹn không biến audience orders-api thành inventory-api và không thêm inventory.read.

### 7.1. Những gì downstream phải kiểm

Downstream Resource Server nên tự xác minh:

- Chữ ký hoặc trạng thái introspection.
- Issuer.
- Audience dành cho downstream.
- exp, nbf và token profile.
- Scope/authorities.
- Tenant, client và domain authorization.
- Những claim/constraints đặc thù nghiệp vụ.

Không dựa vào việc request đến từ Orders API để bỏ qua xác minh token, trừ khi có một cơ chế service-to-service trust riêng như mTLS hoặc gateway identity được thiết kế và kiểm soát.

### 7.2. Khi audience không phù hợp

Các lựa chọn:

1. Authorization Server cấp access token có nhiều audiences theo đúng policy.
2. Dùng **OAuth 2.0 Token Exchange (RFC 8693)** để đổi token đầu vào thành token dành cho downstream.
3. Dùng OAuth2 Client với client_credentials nếu downstream chỉ cần danh tính service.
4. Thiết kế một delegation mechanism được AS hỗ trợ và downstream xác minh.

Không sửa claims trong JWT đã ký hoặc tạo token giả trong middleware.

### 7.3. Scope không được tự mở rộng khi relay

Nếu inbound token chỉ có orders.read, relay filter không thể thêm inventory.write. Downstream không được coi token đã qua một service trung gian là có thêm quyền.

Đây là nguyên tắc quan trọng để giữ least privilege qua nhiều service.

## 8. Rủi ro rò rỉ token qua WebClient dùng chung

Một WebClient có ServletBearerExchangeFilterFunction có khả năng thêm token hiện tại vào request outbound. Vì vậy, **đích đến của WebClient trở thành một ranh giới bảo mật**.

Ví dụ nguy hiểm:

~~~java
String userSuppliedUrl = request.getParameter("url");

return sharedWebClient.get()
    .uri(userSuppliedUrl)
    .retrieve()
    .bodyToMono(String.class);
~~~

Nếu WebClient này có token relay và URL do người dùng kiểm soát, ứng dụng có nguy cơ gửi access token tới một host không mong muốn.

### 8.1. Dùng client chuyên biệt theo downstream

Khuyến nghị:

- Một WebClient riêng cho Inventory API.
- Base URL được cấu hình trong server-side configuration.
- Không cho caller cung cấp absolute URL.
- Không đưa token relay client vào tiện ích HTTP tổng quát.
- Giới hạn redirect/host theo network policy và connector behavior.
- Không log Authorization header.
- Dùng TLS và kiểm certificate/hostname.
- Không dùng cùng client có token relay cho telemetry, webhook hoặc public URLs.

Lưu ý: **baseUrl không phải một allowlist bảo mật tuyệt đối** nếu code vẫn cho phép request URI tuyệt đối override base URL. Không nhận URI tùy ý từ request user.

### 8.2. Tránh ghi token vào log

Không log:

~~~http
Authorization: Bearer eyJhbGciOi...
~~~

Không đưa token value vào:

- Application logs.
- Trace tags hoặc baggage.
- Metrics labels.
- Exception message.
- Audit events không được bảo vệ.
- URL query parameters.

Có thể log correlation ID, downstream logical service name, status và error category mà không lộ credential.

### 8.3. Không cache token relay trong singleton field

WebClient singleton là bình thường; token người dùng không được lưu thành mutable field của bean.

Không làm:

~~~java
class UnsafeClient {
    private String currentUserToken;
}
~~~

Nhiều request đồng thời có thể ghi đè token của nhau, gây cross-user credential leakage.

Filter phải lấy Authentication theo request/publisher context, không dùng một biến toàn cục để lưu token hiện tại.

## 9. Header override và nhiều ExchangeFilterFunction

Spring WebClient cho phép xếp nhiều ExchangeFilterFunction. Thứ tự filter có thể ảnh hưởng cách request được sửa đổi trước khi gửi.

Nếu request tự đặt Authorization header, tài liệu Spring Security mô tả rằng ServletBearerExchangeFilterFunction sẽ không ghi đè header đó mà chuyển request tới filter kế tiếp.

Ví dụ token override:

~~~java
return inventoryWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .headers(headers ->
        headers.setBearerAuth(explicitToken))
    .retrieve()
    .bodyToMono(Inventory.class);
~~~

Hãy dùng override có chủ đích, chẳng hạn khi một service method nhận authorized token đã được cấp cho đúng downstream. Tránh nhận explicitToken từ caller không tin cậy.

### 9.1. Tránh hai filter cùng đặt Authorization

Một WebClient có thể có:

- ServletBearerExchangeFilterFunction.
- OAuth2 client filter.
- Custom API-key filter.
- Custom header interceptor.

Nếu nhiều filter cùng thao tác Authorization, hãy xác định thứ tự và policy rõ. Một request chỉ nên có một credential scheme phù hợp.

Không để request đồng thời mang token của user và token service theo cách downstream không thể phân biệt principal.

## 10. Xử lý lỗi từ downstream

ServletBearerExchangeFilterFunction chỉ xử lý việc thêm token. Nó không quản lý toàn bộ lỗi HTTP trả về.

Ví dụ:

~~~java
return inventoryWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .retrieve()
    .onStatus(
        status -> status.value() == 401,
        response -> response.createException()
    )
    .onStatus(
        status -> status.value() == 403,
        response -> response.createException()
    )
    .bodyToMono(Inventory.class);
~~~

Các phản hồi thường gặp:

| Downstream response | Nguyên nhân có thể |
|---|---|
| 401 Unauthorized | Token thiếu, hết hạn, sai issuer/audience, signature hoặc inactive |
| 403 Forbidden | Token hợp lệ nhưng thiếu scope/role/tenant permission |
| 429 Too Many Requests | Rate limit downstream |
| 5xx | Downstream hoặc dependency gặp lỗi |
| Timeout | Không nhận được response trong budget |

### 10.1. 401 không tự kích hoạt refresh với filter relay

Khi downstream trả 401, ServletBearerExchangeFilterFunction không tự gọi token endpoint để refresh. Nó không phải OAuth2AuthorizedClientManager.

Ứng dụng có thể ghi nhận lỗi và trả response phù hợp cho caller. Nếu cần refresh hoặc xin token mới, dùng OAuth2 Client filter với provider/failure handler phù hợp.

### 10.2. Không retry mù quáng

Retry cùng một token hết hạn sẽ tiếp tục thất bại. Retry một request POST/DELETE có thể gây side effect lặp nếu downstream đã xử lý trước khi connection bị ngắt.

Phải xét:

- HTTP method và idempotency.
- Loại lỗi.
- Access token expiration.
- Downstream retry contract.
- Overall deadline.
- Idempotency key nếu nghiệp vụ hỗ trợ.

## 11. Token relay với nhiều downstream services

Một ứng dụng có thể gọi nhiều services:

~~~text
Inbound user token
    |
    +--> Orders service
    |
    +--> Inventory service
    |
    +--> Shipping service
    |
    +--> Billing service
~~~

Không phải downstream nào cũng nên nhận cùng token.

| Downstream | Audience cần thiết | Có thể relay nguyên token? |
|---|---|---|
| Orders API | orders-api | Nếu token được cấp cho đúng audience |
| Inventory API | inventory-api | Chỉ khi audience/contract cho phép |
| Billing API | billing-api | Không nếu token chỉ dành cho Orders |
| Telemetry endpoint | telemetry resource | Thường không gửi user token |
| Public webhook | Không thuộc trust domain | Không |

Thiết kế WebClient riêng theo logical downstream giúp policy dễ đọc và hạn chế việc gửi nhầm token.

Nếu một downstream cần service identity thay cho user identity, dùng OAuth2 Client/client_credentials hoặc cơ chế workload identity phù hợp.

## 12. ServletBearerExchangeFilterFunction và ServerBearerExchangeFilterFunction

Spring Security có hai class gần tên nhưng dành cho hai môi trường khác nhau:

| Class | Môi trường | Vai trò |
|---|---|---|
| **ServletBearerExchangeFilterFunction** | Spring MVC / Servlet application | Relay Bearer token gắn với Authentication hiện tại |
| **ServerBearerExchangeFilterFunction** | WebFlux reactive server | Relay Bearer token từ reactive Authentication context |

Đối với ứng dụng Servlet, dùng ServletBearerExchangeFilterFunction. Đối với WebFlux server, dùng ServerBearerExchangeFilterFunction.

Cả hai đều là WebClient ExchangeFilterFunction, nhưng không nên chọn class chỉ dựa vào việc ứng dụng có dùng WebClient. Hãy chọn theo **server security stack**.

## 13. Kiểm thử token relay

Một test hữu ích cần xác minh outbound HTTP request thực sự có header mong đợi. Chỉ test rằng controller trả 200 không đủ.

Có thể dùng MockWebServer hoặc một HTTP stub tương đương.

### 13.1. Positive test

1. Khởi chạy test Servlet application có Spring Security Resource Server.
2. Gửi inbound request với JWT test đã được xác minh.
3. Controller gọi WebClient có ServletBearerExchangeFilterFunction.
4. Stub downstream nhận request.
5. Kiểm tra header Authorization có Bearer token đúng.
6. Kiểm tra downstream response được chuyển về caller.

### 13.2. Negative test

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không có Authentication | Không tự tạo Bearer token |
| Authentication không có AbstractOAuth2Token credential | Không relay credential tùy tiện |
| Authentication có JWT token | Relay token value tương ứng |
| Request đã có Authorization explicit | Giữ policy override đã định nghĩa |
| Token inbound hết hạn sau khi được xác thực | Filter không tự refresh |
| Token audience sai downstream | Downstream từ chối |
| Downstream thiếu scope | Downstream trả 403 |
| Gọi host ngoài allowlist | Không được dùng relay client |
| Hai user gọi đồng thời | Không được gửi chéo token |
| Publisher chạy detached khỏi request context | Không giả định Authentication vẫn có mặt |

### 13.3. Ví dụ kiểm tra outbound Authorization bằng stub

Một kiểm thử integration có thể kiểm tra request nhận được:

~~~java
RecordedRequest recorded = mockWebServer.takeRequest();

assertEquals(
    "Bearer test-access-token",
    recorded.getHeader("Authorization")
);
~~~

Ví dụ trên giả định test đã gửi inbound request và MockWebServer đã nhận outbound call. Dùng test token không phải credential thật.

### 13.4. Kiểm thử hai request đồng thời

Tạo hai inbound requests với hai access tokens khác nhau:

~~~text
Request A -> token-A -> downstream call A
Request B -> token-B -> downstream call B
~~~

Kiểm tra:

- Request A không mang token-B.
- Request B không mang token-A.
- Không có static field lưu token hiện tại.
- Mỗi publisher được gắn đúng Authentication của request.
- Cancellation hoặc timeout của request A không làm thay đổi context của request B.

Đây là kiểm thử quan trọng với singleton WebClient được dùng đồng thời.

## 14. Những lỗi thiết kế thường gặp

**1. Nhầm token relay với token refresh.** ServletBearerExchangeFilterFunction không tự xin hoặc refresh token.

**2. Nhầm token relay với OAuth2 Client.** Filter relay dùng credential hiện tại; OAuth2 Client manager quản lý authorized client và token acquisition.

**3. Forward token tới mọi URL.** Có thể làm lộ Bearer credential sang host ngoài trust boundary.

**4. Giả định downstream tự chấp nhận token.** Audience, issuer và scope vẫn phải đúng.

**5. Dùng ID Token làm access token.** ID Token dành cho OIDC client; Resource Server cần access token có audience phù hợp.

**6. Dùng client_credentials khi cần giữ user identity.** Token service đại diện cho ứng dụng, không tự đại diện cho user gốc.

**7. Tự thêm scope bằng cách sửa JWT.** Chữ ký sẽ không hợp lệ; quyền phải do Authorization Server cấp.

**8. Gọi subscribe() thủ công trong service.** Làm outbound request tách khỏi lifecycle, lỗi và cancellation của caller.

**9. Giữ token trong field của singleton.** Có nguy cơ gửi nhầm token giữa các users.

**10. Log Authorization header.** Làm lộ Bearer credential.

**11. Không đặt timeout cho outbound WebClient.** Có thể giữ servlet request thread quá lâu khi dùng block().

**12. Coi downstream 401 là lỗi của inbound Resource Server.** Hai services có thể có audience/scope/token policies khác nhau.

**13. Dùng ServletBearerExchangeFilterFunction trong WebFlux server.** Chọn filter theo Servlet hay reactive server stack.

**14. Dùng filter relay cho mọi integration.** Webhook, telemetry và public API không nhất thiết được nhận token của user.

## 15. Quy trình lựa chọn và triển khai

**Bước 1 — Xác định principal cần downstream nhìn thấy.** Là user gốc hay service hiện tại?

**Bước 2 — Kiểm tra access token contract.** Issuer, audience, scope, expiration và token type có phù hợp downstream không?

**Bước 3 — Chọn cơ chế.**
- User token được downstream chấp nhận: ServletBearerExchangeFilterFunction.
- Token riêng cho service: OAuth2AuthorizedClientManager/client_credentials.
- Token cần đổi audience hoặc scope: token exchange theo hỗ trợ của AS.

**Bước 4 — Tạo WebClient riêng.** Dùng base URL cố định, TLS, timeout, pool và metrics.

**Bước 5 — Thêm filter đúng stack.** ServletBearerExchangeFilterFunction cho Servlet; ServerBearerExchangeFilterFunction cho WebFlux.

**Bước 6 — Giữ context đúng request.** Không tự subscribe hoặc tạo thread tách khỏi request; kiểm thử async propagation.

**Bước 7 — Kiểm downstream authorization.** Không giả định token hợp lệ ở service hiện tại sẽ hợp lệ ở service khác.

**Bước 8 — Kiểm soát rò rỉ token.** Không gửi tới URL do user kiểm soát, không log header, không lưu token vào singleton state.

**Bước 9 — Xử lý 401/403 và timeout.** Phân biệt token invalid, thiếu quyền, upstream failure và timeout; chỉ refresh khi dùng OAuth2 Client flow phù hợp.

**Bước 10 — Kiểm thử end-to-end.** Xác nhận đúng token, đúng destination, đúng context và không chéo token giữa các requests.

## 16. Câu hỏi tự kiểm tra

**1. ServletBearerExchangeFilterFunction làm gì?**

Nó lấy OAuth2 token credential gắn với Authentication hiện tại và thêm vào Authorization Bearer header của WebClient outbound request.

**2. Nó có tự xin access token mới không?**

Không. Nó chỉ chuyển tiếp token hiện tại.

**3. Nó có refresh access token hết hạn không?**

Không. Dùng ServletOAuth2AuthorizedClientExchangeFilterFunction với OAuth2AuthorizedClientManager nếu cần refresh theo provider đã cấu hình.

**4. Nó có gửi mọi loại Authentication credential không?**

Không. Nó tìm credential thuộc AbstractOAuth2Token.

**5. Nó có tự đổi audience sang downstream API không?**

Không. Token được relay nguyên vẹn; downstream phải kiểm audience của chính nó.

**6. Vì sao không nên gắn filter vào WebClient dùng cho URL bất kỳ?**

Vì access token có thể bị gửi tới host không tin cậy.

**7. Có thể dùng ServletBearerExchangeFilterFunction trong WebFlux server không?**

Không nên. WebFlux server có ServerBearerExchangeFilterFunction tương ứng.

**8. Token relay có thêm scope không?**

Không. Nó không cấp thêm quyền hoặc sửa token.

**9. OAuth2 Login session có tự được relay qua filter này không?**

Không nên giả định. Dùng OAuth2 Client filter để lấy access token từ OAuth2AuthorizedClient.

**10. Khi downstream trả 401, filter có tự refresh hoặc xóa token không?**

Không. Filter chỉ gắn header; việc refresh/failure handling thuộc OAuth2 Client manager hoặc logic ứng dụng.

## Kết luận

**ServletBearerExchangeFilterFunction** giúp Spring MVC/Servlet application chuyển tiếp access token đã gắn với Authentication hiện tại khi gọi downstream bằng WebClient. Cách dùng cơ bản là đăng ký nó qua WebClient builder:

~~~java
WebClient.builder()
    .filter(new ServletBearerExchangeFilterFunction())
    .build();
~~~

Cơ chế này chỉ thực hiện **token relay**. Nó không xin token, refresh token, đổi audience, mở rộng scope hoặc xác minh quyền của downstream. Nếu ứng dụng cần token theo client registration, hãy dùng **ServletOAuth2AuthorizedClientExchangeFilterFunction** với **OAuth2AuthorizedClientManager**.

Hãy tạo WebClient chuyên biệt cho từng downstream tin cậy, kiểm tra audience/scope, giữ Authentication đúng request context, không gửi token tới URL tùy ý và không log Authorization header. **Token chỉ nên được chuyển tiếp khi downstream có hợp đồng rõ ràng để xác minh và chấp nhận chính token đó.**

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Bearer Token Propagation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security API — ServletBearerExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServletBearerExchangeFilterFunction.html)
- [Spring Security — Authorized Client Features and WebClient Integration for Servlet Environments](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security API — ServletOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
