# Các mô hình ứng dụng: trình duyệt dùng phiên, REST API dùng token và dịch vụ gọi dịch vụ

**Ngữ cảnh:** Spring Security cho ứng dụng **reactive dùng Spring WebFlux**, Java 17+ và Spring Boot 3.x. Ba mô hình có thể cùng xuất hiện trong một hệ thống; điểm quyết định là **ai gửi request, thông tin xác thực được gửi ra sao, và máy chủ cần duy trì trạng thái gì**.

## 1. Phân biệt ba mô hình

| Mô hình | Chủ thể chính | Credential gửi ở mỗi request | Quản lý trạng thái xác thực | Trường hợp điển hình |
| --- | --- | --- | --- | --- |
| Trình duyệt dùng phiên (session) | Người dùng qua browser | Cookie chứa **session ID** | Máy chủ lưu `SecurityContext` theo `WebSession`; browser chỉ giữ định danh phiên | Trang web server-rendered, ứng dụng BFF, giao diện quản trị |
| REST API dùng token | Người dùng hoặc ứng dụng gọi API | Header `Authorization: Bearer <access-token>` | API xác minh token cho từng request; thông thường không duy trì phiên đăng nhập phía API | Mobile app, SPA dùng OAuth2, public/partner API |
| Dịch vụ gọi dịch vụ (service-to-service, M2M) | Một workload / ứng dụng backend | Thường là access token OAuth2, đôi khi mTLS | Dịch vụ gọi tự lấy/quản lý token; dịch vụ nhận xác minh token | Orders gọi Inventory, worker gọi Billing, job chạy nền |

**Ba khái niệm không đồng nghĩa:** cookie là cơ chế vận chuyển dữ liệu; session là trạng thái phía máy chủ; access token là credential để truy cập tài nguyên. Một trình duyệt vẫn có thể gọi REST API bằng Bearer token, và một service vẫn có thể dùng session nếu thiết kế như vậy, nhưng đó không phải lựa chọn điển hình.

Trong WebFlux, các thành phần cần biết gồm `SecurityWebFilterChain` (chuỗi bộ lọc bảo mật), `ServerHttpSecurity` (DSL cấu hình), `Authentication` (danh tính đã xác thực), `SecurityContext` và `ReactiveSecurityContextHolder` (ngữ cảnh bảo mật gắn với Reactor Context), `WebSession` (phiên web) và các thành phần OAuth2 Client / Resource Server.

## 2. Trình duyệt dùng phiên: xác thực người dùng và giữ đăng nhập

### 2.1 Luồng request

1. Browser mở `GET /dashboard` khi chưa đăng nhập; bộ lọc bảo mật phát hiện route cần xác thực.
2. Ứng dụng chuyển đến trang login (form login) hoặc bắt đầu OAuth2/OIDC login tại nhà cung cấp danh tính.
3. Sau khi kiểm tra thông tin đăng nhập, Spring Security tạo `Authentication` và lưu `SecurityContext` vào `WebSession` thông qua cơ chế lưu context theo phiên.
4. Response đặt cookie định danh phiên, thường là `SESSION`. Browser tự gửi cookie này cho các request phù hợp về sau.
5. Server tra phiên, khôi phục danh tính và kiểm tra quyền. Khi logout/hết hạn/phiên bị vô hiệu hóa, cookie cũ không còn tạo được phiên đã đăng nhập.

**Cookie phiên không nên chứa mật khẩu hay toàn bộ đối tượng người dùng.** Cookie định danh phiên chỉ là khóa tham chiếu đến trạng thái được máy chủ quản lý. Với nhiều instance, cần một kho phiên chung phù hợp, ví dụ Spring Session + Redis reactive, hoặc một phương án bảo đảm yêu cầu vận hành tương đương.

### 2.2 Những điều phải bảo vệ

- **CSRF:** browser tự đính kèm cookie; trang độc hại có thể lợi dụng điều đó để gửi lệnh thay người dùng. Spring Security WebFlux bật CSRF mặc định. Với POST/PUT/PATCH/DELETE dựa vào cookie, giữ CSRF protection và gửi CSRF token hợp lệ. Với WebFlux, repository mặc định cho CSRF token dùng `WebSession`.
- **Cookie:** khi triển khai HTTPS, dùng `Secure`, `HttpOnly`, `SameSite` phù hợp; cấu hình phạm vi `Domain`/`Path` tối thiểu. `SameSite` là lớp bổ sung, không tự thay thế mọi cơ chế CSRF.
- **XSS:** kiểm soát dữ liệu HTML và Content Security Policy vì script độc hại vẫn có thể thay mặt người dùng thao tác ngay trong trang, kể cả khi cookie `HttpOnly`.
- **Session lifecycle:** thời hạn hoạt động, logout, thu hồi phiên, giới hạn đăng nhập đồng thời khi cần. Đăng nhập lại nên bảo đảm không tái sử dụng session ID theo cách gây session fixation.
- **Scale-out:** nếu các node khác nhau phải xử lý cùng phiên, dùng session store phù hợp; sticky session đơn thuần không giải quyết đầy đủ vấn đề khi node mất.

**Lưu ý về OAuth2 login:** OIDC/OAuth2 authorization code xác minh danh tính với Identity Provider, nhưng ứng dụng WebFlux phía sau vẫn có thể **giữ phiên đăng nhập bằng cookie**. Việc dùng OIDC để login không tự biến mọi request trang web thành Bearer-token request.

## 3. REST API dùng Bearer token: Resource Server

### 3.1 Luồng request

1. Client nhận **access token** từ hệ thống cấp quyền phù hợp, thường là OAuth2 Authorization Server. Ứng dụng public như mobile/SPA thường dùng authorization code + PKCE.
2. Client gọi API qua HTTPS với header `Authorization: Bearer eyJ...`.
3. WebFlux Resource Server trích Bearer token, xác minh token và dựng `Authentication` trong phạm vi request.
4. Bộ lọc và method authorization kiểm tra scope/role/quyền; xử lý nghiệp vụ khi hợp lệ.
5. Request sau lại gửi token; API không cần dựa vào cookie phiên của lần trước.

Đối với **JWT**, Resource Server phải kiểm tra chữ ký với khóa tin cậy, thời hạn (`exp`, `nbf`), đơn vị phát hành (`iss`), và **audience (`aud`) dành cho API này**; sau đó kiểm tra scope/quyền. Đừng chỉ Base64-decode JWT rồi tin các claims. Với **opaque token**, Resource Server dùng cơ chế introspection của Authorization Server; trade-off là có khả năng hỏi trạng thái token gần thời gian thực hơn, nhưng thêm độ trễ/phụ thuộc mạng và cần cache hợp lý.

Trong cấu hình JWT chuẩn, Spring Security ánh xạ các giá trị trong claim `scope`/`scp` thành authority tiền tố `SCOPE_`, ví dụ scope `orders.read` → `SCOPE_orders.read`. Scope là quyền mà token được cấp; controller/service vẫn phải thực hiện kiểm tra quyền truy cập tài nguyên cụ thể, ví dụ đơn hàng có thực sự thuộc khách hàng đang truy cập hay không.

### 3.2 401, 403 và trạng thái

- **401 Unauthorized:** không có token hợp lệ, token hết hạn, sai chữ ký, sai issuer/audience hoặc không xác thực được. Client có thể xin token mới theo flow được phép.
- **403 Forbidden:** đã xác thực nhưng thiếu quyền/scope, hoặc bị chặn theo chính sách. Xin lại đúng token cũ không giúp có thêm quyền.
- **Không lưu trạng thái xác thực theo phiên:** dùng `NoOpServerSecurityContextRepository` nếu muốn tách rõ API khỏi cơ chế lưu security context vào session. Điều này **không xóa mọi `WebSession`** có thể được framework khác sử dụng.
- **CSRF:** có thể tắt riêng cho API **chỉ nhận Bearer token từ header và không dùng credential được browser tự đính kèm**. Nếu API vẫn chấp nhận cookie đăng nhập hoặc một dạng auth tự gửi, cần xem xét lại CSRF thay vì tắt toàn cục.
- **CORS khác CSRF:** CORS quyết định browser được phép đọc response và gửi một số cross-origin request; nó không thay thế xác thực, phân quyền hay CSRF protection.

Không đưa access token vào query string, URL, log, lỗi trả về hoặc local storage một cách tùy tiện. Dùng HTTPS, token sống ngắn, hạn chế scope và audience, quản lý refresh token theo loại client và yêu cầu bảo mật.

## 4. Dịch vụ gọi dịch vụ: OAuth2 Client và Resource Server phối hợp

Ví dụ `orders-service` cần gọi `inventory-service` để đọc tồn kho mà không có người dùng đang tương tác:

1. `orders-service` có một OAuth2 **client registration** riêng, với `client_id` và phương thức xác thực client (ví dụ `client_secret` được bảo vệ hoặc chứng thư).
2. Service gửi request `grant_type=client_credentials` đến token endpoint qua TLS.
3. Authorization Server cấp access token đại diện **cho service/client**, với scope và audience đã duyệt (ví dụ `inventory.read`, `inventory-api`).
4. Service gọi Inventory bằng `Authorization: Bearer <access-token>`.
5. Inventory đóng vai trò **Resource Server**, kiểm tra token và `SCOPE_inventory.read` rồi mới trả kết quả.
6. Client manager tái sử dụng token còn hạn và lấy token mới khi cần; việc đó diễn ra trong luồng reactive.

**Client credentials không đại diện cho người dùng cuối.** Nếu Orders cần truy cập Inventory **trên danh nghĩa người dùng**, cần thiết kế ủy quyền phù hợp như OAuth2 token exchange/on-behalf-of theo khả năng của Identity Provider, hoặc truyền thông tin người dùng đã được xác minh theo hợp đồng bảo mật rõ ràng. Không mặc nhiên truyền token của user cho mọi downstream service: token có thể sai audience hoặc cấp quyền quá rộng.

Các lựa chọn khác có thể là **mTLS/workload identity** cho xác thực workload. Dù dùng giải pháp nào, dịch vụ nhận vẫn phải tự kiểm soát quyền; private network hoặc API gateway không đủ để bỏ qua authorization. Mỗi service có danh tính, credential, scope và audit riêng; secret/cert phải được lưu và luân chuyển bằng cơ chế quản lý bí mật.

### 4.1 Vì sao WebFlux cần client manager dạng reactive?

`ReactiveOAuth2AuthorizedClientManager` quản lý việc cấp và tái cấp access token bất đồng bộ. Khi có `ServerWebExchange`, có thể dùng `DefaultReactiveOAuth2AuthorizedClientManager`; trong job/service nền **không có request của browser**, dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cùng `ReactiveOAuth2AuthorizedClientService`. Không dùng manager servlet (`OAuth2AuthorizedClientManager` không có `Reactive`) trong cấu hình WebFlux reactive.

## 5. Cấu hình WebFlux cho browser và API trên cùng ứng dụng

Các ví dụ này dùng Java 17+, Spring Boot 3.x/Spring Security 6.x. Trong `build.gradle` (Groovy), thêm theo vai trò ứng dụng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    // Chỉ cần nếu ứng dụng thực hiện OAuth2 login hoặc gọi downstream bằng OAuth2 Client:
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Không trộn `spring-boot-starter-web` (Servlet MVC) vào ứng dụng này nếu mục tiêu là thực hành đúng chuỗi bảo mật reactive; khi cả MVC và WebFlux cùng có mặt, Spring Boot thường chọn MVC theo mặc định.

Dưới đây là một file `SecurityConfig.java` có **hai chuỗi độc lập**. Giả định ứng dụng đã có bean `ReactiveUserDetailsService` hoặc cấu hình user store cho form login, một Authorization Server phát JWT hợp lệ và các endpoint tương ứng. Đây là cấu hình bảo mật có thể biên dịch khi nằm trong project Boot đủ dependencies, không phải chương trình Java SE độc lập để chạy bằng `javac` thuần.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/public/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

**Giải thích:**

- `@Order(1)` và `securityMatcher("/api/**")` chọn chuỗi Bearer token cho API trước; chuỗi browser ở thứ tự sau xử lý các path còn lại. Spring Security chọn **một chuỗi phù hợp** cho một request, không cộng dồn mọi chuỗi.
- API chỉ cho GET khi có `orders.read`, POST khi có `orders.write`; các method/path API chưa khai báo bị từ chối. Điều chỉnh policy theo nghiệp vụ thực tế.
- API không có form login, HTTP Basic và không ghi security context vào session; CSRF chỉ bị tắt trong chuỗi API đã xác nhận chỉ dùng Bearer header.
- Browser dùng form login và CSRF. Chỉ bật `oauth2Login(Customizer.withDefaults())` thay/hoặc cùng form login khi đã cấu hình OAuth2/OIDC client registration cho kịch bản đăng nhập qua IdP.
- Với frontend khác origin, cấu hình CORS cho đúng origin/method/header; không dùng wildcard tùy tiện khi có credentials. Với endpoint cần phân quyền nghiệp vụ sâu, bổ sung kiểm tra tại service/method security.

Ví dụ `application.yml` cho **API kiểm JWT**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
          audiences:
            - orders-api
```

`issuer-uri` phải đúng với claim `iss` do IdP thực cấp, còn `orders-api` phải xuất hiện trong `aud` của access token. Đặt đúng issuer/JWK và audience thực tế trước khi chạy; URL trên chỉ minh họa. Với opaque token, sử dụng cấu hình introspection và `oauth2ResourceServer(o -> o.opaqueToken(Customizer.withDefaults()))` thay vì JWT.

**Không chỉ đổi `csrf.disable()` toàn ứng dụng:** nếu làm vậy, các thao tác browser dựa vào cookie cũng mất CSRF protection.

## 6. Ví dụ client_credentials reactive để gọi Inventory

Thêm `spring-boot-starter-oauth2-client` và đăng ký một client riêng trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: company-idp
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          company-idp:
            token-uri: https://idp.example.com/oauth2/token
```

Hai biến môi trường cung cấp credential, không hardcode secret vào source/repository. IdP và Inventory phải cùng thống nhất token audience, scope, client authentication method và khóa ký/introspection. Client nên dùng TLS với token endpoint và downstream API.

File `InventoryOAuth2Config.java` dưới đây tạo manager dùng được cả khi chạy job nền ngoài `ServerWebExchange`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class InventoryOAuth2Config {
    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clients) {
        var manager = new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, clients);
        manager.setAuthorizedClientProvider(
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
        return manager;
    }
}
```

File `InventoryClient.java` dùng manager lấy token rồi đưa vào header khi gọi downstream. Phương thức trả về `Mono<String>`, không chặn thread:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryClient {
    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public InventoryClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient.Builder webClientBuilder) {
        this.manager = manager;
        this.webClient = webClientBuilder
            .baseUrl("https://inventory.example.com")
            .build();
    }

    public Mono<String> fetchStock() {
        var request = OAuth2AuthorizeRequest
            .withClientRegistrationId("inventory")
            .principal("orders-service")
            .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Không lấy được OAuth2 authorized client")))
            .flatMap(client -> webClient.get()
                .uri("/api/stock")
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(String.class));
    }
}
```

**Lưu ý khi chạy:** `principal("orders-service")` là tên danh tính mà manager dùng để quản lý authorized client, **không làm token trở thành token của người dùng**. Trong production, cân nhắc storage an toàn và chia sẻ cache theo kiến trúc triển khai; với nhiều node, `InMemoryReactiveOAuth2AuthorizedClientService` chỉ lưu tại từng instance. Không log `getTokenValue()`. Địa chỉ `inventory.example.com` và token endpoint là ví dụ cần thay bằng dịch vụ thật. Resource Server của Inventory cũng phải xác minh token, audience và `SCOPE_inventory.read`; chỉ lấy token thành công chưa đồng nghĩa có quyền gọi mọi API của Inventory.

## 7. SecurityContext trong reactive pipeline

Reactive WebFlux xử lý bất đồng bộ trên Reactor, vì vậy không giả định principal được lưu ổn định trong `ThreadLocal` hoặc có thể lấy từ request trước. `ReactiveSecurityContextHolder` đưa `SecurityContext` theo **Reactor Context** của cùng luồng reactive. Trong một handler/service, có thể đọc context như sau (đoạn trích nằm trong component reactive):

```java
public Mono<String> currentUsername() {
    return org.springframework.security.core.context.ReactiveSecurityContextHolder
        .getContext()
        .map(context -> context.getAuthentication().getName())
        .defaultIfEmpty("anonymous");
}
```

Method này cần chạy trong pipeline có context bảo mật; không kỳ vọng thấy user khi gọi độc lập ngoài request. Tránh `block()` trên event-loop WebFlux, tránh tự `subscribe()` và tránh tự chuyển sang thread/executor ngoài Reactor mà không bảo toàn context. Nếu dùng `@PreAuthorize` cho phương thức reactive, bật `@EnableReactiveMethodSecurity` và giữ signature trả về `Mono`/`Flux` phù hợp.

Một request Bearer token hợp lệ tạo `Authentication` riêng trong chuỗi xử lý request; nó **không đồng nghĩa** Spring cần lưu authentication vào `WebSession`. Ngược lại, browser session là cách **khôi phục** authentication ở request kế tiếp. Đây là điểm phân biệt cốt lõi khi đọc cấu hình Spring Security WebFlux.

## 8. Chọn mô hình theo bài toán

| Tình huống | Khuyến nghị ban đầu | Vì sao / điều cần kiểm tra |
| --- | --- | --- |
| Portal admin cùng origin, server giữ phiên | Browser session + form/OIDC login + CSRF | Browser gửi cookie tự động; cần quản lý logout và session store |
| Giao diện SPA kết nối backend qua BFF | Browser ↔ BFF bằng session cookie, BFF giữ token server-side khi cần | Tránh phơi token cho JavaScript; BFF vẫn cần CSRF và cookie policy |
| Mobile / SPA là OAuth2 public client trực tiếp gọi API | Authorization code + PKCE; API là Resource Server Bearer token | Không nhúng client secret trong public client; xét kỹ lưu token trên thiết bị |
| Partner API không dùng browser cookie | Bearer JWT/opaque token, audience và scope riêng | API kiểm token mỗi request, phân quyền cho từng resource |
| Worker định kỳ hoặc microservice gọi microservice | OAuth2 client_credentials hoặc workload identity; bên nhận kiểm token | Không có browser/session người dùng; danh tính service tách biệt |
| Service phải hành động nhân danh người dùng | Flow ủy quyền/token exchange hợp lệ | Client credentials chỉ phản ánh danh tính service, không mang quyền user |

**Câu hỏi quyết định nhanh:** Credential có được browser tự đính kèm dưới dạng cookie không? Nếu có, xét CSRF và phiên. Credential có chủ động gửi trong Bearer header không? Nếu có, bảo vệ Resource Server và vòng đời token. Có người dùng cuối thực sự tham gia flow không? Nếu không, dùng danh tính workload/service; đừng tự gán quyền của user.

## 9. Kịch bản kiểm thử và kết quả mong đợi

Các kết quả phụ thuộc endpoint thật, policy và dữ liệu; các trạng thái sau là kỳ vọng bảo mật, không phải stdout của một chương trình mẫu đã chạy:

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Browser chưa login mở `/dashboard` | Redirect đến login hoặc khởi động OIDC login |
| Browser login hợp lệ, có cookie phiên, mở `/dashboard` | Qua authentication/authorization; response endpoint nếu tồn tại |
| Browser gửi POST đổi dữ liệu bằng cookie nhưng thiếu CSRF token | 403 với route được CSRF bảo vệ |
| API `GET /api/orders` không gửi Bearer token | 401 |
| API gửi token sai chữ ký / hết hạn / sai `iss` / sai `aud` | 401 |
| API gửi token hợp lệ nhưng thiếu `orders.read` | 403 |
| API gửi token hợp lệ, có `orders.read` và pass kiểm tra nghiệp vụ | Có thể trả 2xx nếu endpoint/tài nguyên hợp lệ |
| Orders gọi Inventory bằng client_credentials nhưng thiếu `inventory.read` | Inventory từ chối 403 |
| M2M không lấy được token do client credential sai | Lỗi tại bước token endpoint/authorized client; không có Bearer token hợp lệ để gửi downstream |

Có thể kiểm tra riêng API sau khi có một access token hợp lệ do IdP test cấp:

```bash
curl -i https://localhost:8443/api/orders
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://localhost:8443/api/orders
```

Lệnh giả định service thực sự chạy HTTPS trên cổng 8443 và biến `ACCESS_TOKEN` được cấp hợp lệ; không có lệnh nào tự sinh JWT. Không dùng `curl -k` để bỏ kiểm tra TLS trong hướng dẫn production.

## 10. Sai lầm thường gặp và cách sửa

1. **Cho rằng JWT luôn an toàn vì có ba phần:** JWT có thể chỉ được *giải mã* mà chưa kiểm chứng. Dùng decoder Resource Server và kiểm chữ ký, issuer, audience, hạn dùng.
2. **Tắt CSRF toàn hệ thống vì API dùng token:** browser chain vẫn dùng cookie. Chỉ tắt ở chuỗi API không có credential tự động từ browser.
3. **Dùng cùng một token cho nhiều API:** thiếu ranh giới `aud` và scope, tăng thiệt hại khi rò rỉ. Cấp token theo resource/scope tối thiểu.
4. **Nhầm OAuth2 login với OAuth2 Resource Server:** login thiết lập phiên người dùng; resource server kiểm tra Bearer token đầu vào. Một app có thể cần cả hai với chain tách biệt.
5. **Dùng client_credentials thay quyền user:** service token không chứng minh user đã đồng ý hoặc sở hữu dữ liệu. Thiết kế delegation khi cần.
6. **Tin API gateway là đủ:** mỗi downstream resource server vẫn cần xác thực, phân quyền, kiểm tra đối tượng dữ liệu.
7. **Đọc `SecurityContextHolder` servlet trong reactive code:** dễ mất hoặc nhầm ngữ cảnh qua thread. Dùng `ReactiveSecurityContextHolder` và giữ Reactor chain.
8. **Lẫn lộn 401/403:** lỗi credential khác với thiếu quyền. Log có cấu trúc (không log token) để phân tích.
9. **Khóa cứng secret, log token hoặc dùng HTTP:** tiết lộ credential. Chuyển sang secret manager/env, HTTPS, xoay vòng secret/khóa.
10. **Bỏ qua phân quyền ở cấp tài nguyên:** `SCOPE_orders.read` chưa chắc cho xem *mọi* đơn hàng; kiểm tra tenant/user/ownership theo nghiệp vụ.

## 11. Tổng kết kiến thức cần nắm

- **Session browser:** server quản lý đăng nhập theo `WebSession`, browser giữ cookie, và các thao tác nhạy cảm dùng CSRF protection.
- **Bearer API:** mỗi request mang access token; Resource Server xác thực token, issuer, audience, thời hạn, scope rồi mới quyết định quyền; thường không dùng session để khôi phục đăng nhập.
- **Service-to-service:** service là OAuth2 Client chủ động lấy token bằng `client_credentials`, downstream là Resource Server; danh tính service khác danh tính người dùng.
- **Reactive:** dùng `SecurityWebFilterChain` / `ServerHttpSecurity` và các lớp `Reactive...`; context đi qua Reactor pipeline, tránh áp dụng nguyên xi cách dùng ThreadLocal/Servlet MVC.

### Tài liệu chính thức để đối chiếu

- [Spring Security WebFlux — nhiều SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security WebFlux — CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security Reactive OAuth2 Client — core interfaces](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html)
- [Spring Boot 3.3 — Resource Server properties](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
