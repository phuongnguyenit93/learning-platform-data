# 19.1. `ServletOAuth2AuthorizedClientExchangeFilterFunction` và `WebClient`

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client** chạy trên **Servlet stack (Spring MVC)**, người dùng có thể đăng nhập qua OpenID Connect, sau đó backend cần thay mặt họ gọi một API được bảo vệ bằng OAuth 2.0. Thay vì tự lấy access token, ghép chuỗi `Authorization: Bearer ...` tại từng chỗ và tự kiểm tra hạn token, Spring Security cung cấp **`ServletOAuth2AuthorizedClientExchangeFilterFunction`** để kết nối **`WebClient`** với hệ thống **OAuth2 Authorized Client**.

Đây là một lớp đóng vai trò **`ExchangeFilterFunction`** cho WebClient: trước khi WebClient gửi request ra ngoài, filter có thể tìm hoặc cấp lại `OAuth2AuthorizedClient` tương ứng với một `ClientRegistration` và một principal, sau đó đính kèm access token phù hợp vào HTTP request.

Điểm dễ nhầm nhất của chủ đề là **`WebClient` dùng API reactive nhưng ứng dụng đang ở môi trường Servlet**, còn thông tin principal, request/session và kho authorized client lại thuộc Spring Security Servlet. Hiểu rõ ranh giới này sẽ giúp tránh các lỗi “không tìm thấy authorized client”, “không có Servlet request”, gửi token nhầm API, hoặc hiểu sai việc làm mới token.

## 1. Bài toán: Backend Spring MVC gọi API sau khi người dùng đăng nhập

Giả sử một cổng báo cáo hoạt động như sau:

1. Người dùng mở `https://portal.example.test`.
2. Spring Security chuyển người dùng tới OpenID Provider của công ty.
3. Người dùng xác thực; Spring nhận authorization code, đổi code và xác minh ID Token.
4. Spring duy trì đăng nhập bằng `SecurityContext`/session và lưu `OAuth2AuthorizedClient` của Client đã cấp quyền.
5. Controller gọi `https://reports-api.example.test/v1/reports` để lấy báo cáo theo quyền user.
6. Reports API yêu cầu HTTP header `Authorization: Bearer <access_token>`.

Nếu tự viết:

```java
// Ý tưởng chưa tốt: mỗi controller tự quản lý token.
String token = someSessionMap.get("access_token");

String result = webClient.get()
    .uri("https://reports-api.example.test/v1/reports")
    .headers(headers -> headers.setBearerAuth(token))
    .retrieve()
    .bodyToMono(String.class)
    .block();
```

bạn phải tự giải quyết hàng loạt vấn đề:

- Token thuộc đúng `ClientRegistration` nào?
- Token đang dùng là access token, ID Token hay refresh token?
- Token có thuộc người dùng hiện tại không?
- Access token đã hết hạn và có refresh token để làm mới chưa?
- Làm sao cập nhật refresh token mới khi provider bật rotation?
- Xử lý HTTP 401/403 từ Resource Server thế nào?
- Không gửi Bearer token tới API khác hoặc URL redirect do người dùng điều khiển ra sao?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` giúp **tập trung hóa cơ chế chọn và gắn access token** thông qua các abstraction của Spring Security. Tuy nhiên, filter không tự giải quyết toàn bộ authorization nghiệp vụ hay bảo đảm token được cấp đúng audience/scope. Ứng dụng vẫn phải chọn ClientRegistration và API đích một cách có kiểm soát.

## 2. Hai mặt của kiến trúc: Servlet Security và Reactive WebClient

Một ứng dụng Spring Boot có thể đồng thời dùng:

- **`spring-boot-starter-web`**: chạy Servlet stack với Spring MVC, `HttpServletRequest`, `HttpSession` và filter chain Servlet.
- **`spring-boot-starter-oauth2-client`**: xử lý OAuth2 Login, ClientRegistration, authorized clients và token management.
- **`spring-boot-starter-webflux`**: cung cấp `WebClient` và Reactor APIs để thực hiện HTTP client calls.

Việc đưa `spring-boot-starter-webflux` vào một ứng dụng đã có Spring MVC **không nhất thiết biến server thành WebFlux**. Trong cấu hình Spring Boot thông dụng, khi cả MVC và WebFlux cùng có mặt, server-side web application vẫn chạy Servlet MVC, còn WebClient được dùng như một HTTP client hỗ trợ reactive.

| Thành phần | Thuộc tầng | Công việc |
|---|---|---|
| `SecurityFilterChain` / `oauth2Login` | Spring Security Servlet | Xác thực HTTP request từ browser, xử lý callback |
| `HttpServletRequest` / `HttpSession` | Servlet container | Request/session của người dùng |
| `OAuth2AuthorizedClientRepository` | OAuth2 Client trong web request | Lưu và tìm authorized client gắn với ngữ cảnh Servlet |
| `OAuth2AuthorizedClientManager` | OAuth2 Client | Quyết định có cần cấp/làm mới token |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Cầu nối Servlet Security → WebClient | Lấy authorized client và gắn token |
| `WebClient` | HTTP client Reactor | Gửi HTTP request tới downstream API |
| `Resource Server` | API đích | Kiểm tra access token, audience, scope và quyền |

```mermaid
flowchart LR
    B["Browser"] --> MVC["Spring MVC Controller"]
    MVC --> SC["SecurityContext / OidcUser"]
    MVC --> WC["WebClient"]
    WC --> F["ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    F --> M["OAuth2AuthorizedClientManager / Repository"]
    M --> CR["ClientRegistrationRepository"]
    M --> TK["Token Endpoint nếu cần refresh"]
    F --> API["Downstream Resource Server"]
    API --> WC
    WC --> MVC
```

**Lưu ý:** Sơ đồ giản lược. Trong triển khai thực, filter áp dụng trước khi HTTP client gửi request và có thể không gọi Token Endpoint nếu authorized client đã có access token phù hợp.

### 2.1. Vì sao không dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction`?

Spring Security có hai tên tương tự:

| Lớp | Môi trường chính | Cơ chế liên quan |
|---|---|---|
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | **Servlet / Spring MVC** | `OAuth2AuthorizedClientRepository` hoặc Servlet-compatible manager |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | **Reactive / Spring WebFlux server** | Reactive client repositories/managers và reactive security context |

Trong một backend sử dụng `HttpServletRequest`, `oauth2Login` theo Servlet và `SecurityFilterChain`, hãy chọn **Servlet** variant. Đừng lấy cấu hình `ServerOAuth2AuthorizedClientExchangeFilterFunction` trong một tutorial WebFlux rồi dán vào Spring MVC mà không xem khác biệt repository, principal và Reactor context.

## 3. Những lớp cốt lõi cần nắm

### 3.1. `ClientRegistration`

`ClientRegistration` mô tả ứng dụng Client đã được đăng ký với Authorization Server. Nó có thể bao gồm:

```text
registrationId = company-api
clientId = portal-web
clientSecret = (giữ bí mật ở backend)
authorizationGrantType = authorization_code
redirectUri = {baseUrl}/login/oauth2/code/{registrationId}
scopes = [openid, profile, reports.read]
provider = company-op
```

Đây là **cấu hình Client**, chưa phải một access token.

### 3.2. `OAuth2AuthorizedClient`

Sau khi Client được cấp quyền, Spring biểu diễn kết quả bằng:

```text
OAuth2AuthorizedClient
  ├── clientRegistration
  ├── principalName
  ├── accessToken
  │    ├── tokenValue
  │    ├── tokenType (thường là Bearer)
  │    ├── issuedAt
  │    ├── expiresAt
  │    └── scopes
  └── refreshToken? (có thể null)
```

Một authorized client thường được phân biệt theo **registration** và **principal**. Khi browser user A và user B cùng đăng nhập qua một OP, họ không được chia sẻ access token của nhau.

### 3.3. `OAuth2AuthorizedClientRepository` và `OAuth2AuthorizedClientService`

- `OAuth2AuthorizedClientRepository` cung cấp cơ chế lưu/tìm authorized client trong ngữ cảnh HTTP Servlet request.
- `OAuth2AuthorizedClientService` cung cấp cơ chế lưu/tìm không bắt buộc phải có `HttpServletRequest`.
- Một repository có thể ủy quyền dữ liệu cho service trong một số cấu hình, nhưng **không nên mặc định hai kho là một** nếu chưa kiểm tra.

### 3.4. `OAuth2AuthorizedClientManager`

Manager điều phối việc cấp và tái cấp authorized client thông qua provider cho các grant như `authorization_code`, `refresh_token` hoặc `client_credentials`, theo cấu hình và context.

Điều này quan trọng vì filter function không tự tạo “token mới cho mọi request”. Nó nhờ manager/repository tìm authorized client phù hợp; nếu cần, manager/provider có thể làm mới.

### 3.5. `ExchangeFilterFunction`

`ExchangeFilterFunction` là một bộ lọc trong pipeline WebClient. Nó có thể xử lý `ClientRequest` trước khi gọi `ExchangeFunction` tiếp theo, ví dụ:

```text
Application WebClient call
  -> OAuth2 ExchangeFilterFunction
     -> lấy/authorize OAuth2AuthorizedClient
     -> gắn Authorization: Bearer ...
     -> gọi HTTP client/Resource Server
  -> trả ClientResponse
  -> xử lý status/body
```

Filter là điểm mở rộng hợp lý để đính kèm token, nhưng **không nên biến nó thành bộ tự động gửi mọi token tới mọi URL**.

## 4. Cấu hình dependencies cho Spring MVC + WebClient

Ví dụ Maven cho một ứng dụng Spring Boot 3.x dùng Servlet và OAuth2 Client:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Không tự ghim từng version dependency nếu Spring Boot BOM đang quản lý. Tên artifact và tích hợp WebClient có thể thay đổi theo phiên bản Boot/Security mới hơn; hãy dùng starter tương thích với dự án thực tế.

Ví dụ Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

Ở những hệ thống chỉ dùng Spring MVC và muốn HTTP client đồng bộ, `RestClient` có thể là một lựa chọn khác. Bài này cố ý tập trung vào **WebClient trong Servlet** vì đó là trường hợp cần `ServletOAuth2AuthorizedClientExchangeFilterFunction`.

## 5. Đăng ký OIDC Client trong `application.yml`

Ví dụ một OP được tin cậy qua OIDC discovery:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-api:
            provider: company-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - reports.read
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"

        provider:
          company-op:
            issuer-uri: https://login.example.test/realms/company
```

Giải thích:

- `company-api` là **registration ID** dùng trong Java.
- `openid` kích hoạt OIDC login và ID Token.
- `reports.read` là scope API giả định; provider phải thật sự hỗ trợ, cấp và đưa vào access token đúng tài nguyên.
- `issuer-uri` xác định OP cho việc discovery metadata, Token Endpoint và JWKS.
- `redirect-uri` dùng cho Authorization Code callback; không phải URL báo cáo.
- `client-secret` được cấp qua secret manager/biến môi trường; không hard-code vào source.

**Cảnh báo về audience:** OAuth2 Login thành công không đảm bảo access token được cấp có thể gọi bất kỳ downstream API nào. Resource Server có thể đòi audience riêng, resource indicator hoặc scope theo hợp đồng với OP. Nếu API yêu cầu token cho resource khác, cần đăng ký/cấp quyền chính xác theo provider.

### 5.1. Cấu hình Servlet login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login` xử lý flow người dùng đăng nhập; `oauth2Client` bổ sung cấu hình hỗ trợ OAuth2 Client khi cần. Với ứng dụng thực tế có nhiều security filter chains/đường dẫn, các request matchers và CSRF/session policy phải được thiết kế phù hợp.

## 6. Tạo WebClient với Servlet OAuth2 filter

Cách cấu hình trực tiếp thường thấy là tạo filter từ `ClientRegistrationRepository` và `OAuth2AuthorizedClientRepository`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
            ClientRegistrationRepository clientRegistrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            clientRegistrations,
            authorizedClients
        );

        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
```

Tên package dài được ngắt thành hai dòng sau `import` chỉ để trình bày; **Java không cho phép xuống dòng tùy ý trong một identifier**. Trong file nguồn thực tế, hãy viết nguyên dòng import:

```java
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
```

Hoặc sử dụng IDE auto-import chính xác.

### 6.1. Vì sao gọi `oauth2Configuration()`?

`oauth2.oauth2Configuration()` là một `Consumer<WebClient.Builder>` giúp đăng ký OAuth2 filter và cấu hình hỗ trợ để filter làm việc với ngữ cảnh Servlet phù hợp.

Cách dùng:

```java
WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
```

phù hợp với mẫu cấu hình Spring Security. So với tự xây một filter đặt `Authorization` header, nó giữ việc tìm authorized client thông qua abstraction của framework.

### 6.2. Khi nào dùng constructor nhận `OAuth2AuthorizedClientManager`?

Bạn có thể muốn chủ động chọn grant providers, refresh behavior và persistence:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository
            );
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

Sau đó:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean("reportsWebClient")
WebClient reportsWebClient(
        OAuth2AuthorizedClientManager webAuthorizedClientManager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        webAuthorizedClientManager
    );

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .apply(oauth2.oauth2Configuration())
        .build();
}
```

**Chỉ chọn một trong hai cấu hình `reportsWebClient`**, không tạo hai bean cùng tên trong một dự án. Constructor nhận manager hữu ích khi ứng dụng đã định nghĩa manager theo chính sách riêng.

### 6.3. Sự khác nhau về failure handler mặc định

Một chi tiết vận hành quan trọng của `ServletOAuth2AuthorizedClientExchangeFilterFunction`:

- Khi filter được tạo bằng **`ClientRegistrationRepository` + `OAuth2AuthorizedClientRepository`**, các phiên bản Spring Security hiện đại hỗ trợ cấu hình `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` mặc định cho các phản hồi Resource Server lỗi theo OAuth2.
- Khi filter được tạo bằng **`OAuth2AuthorizedClientManager`**, hãy kiểm tra và **chủ động cấu hình failure handler** nếu ứng dụng muốn loại bỏ authorized client trên các lỗi API như `invalid_token`. Không giả định constructor nào cũng có cùng default behavior.

Cần xem tài liệu đúng **phiên bản Spring Security** đang dùng. Ngoài ra, failure handler cho API 401/403 khác với failure handler khi Token Endpoint từ chối refresh token.

## 7. Chọn ClientRegistration một cách tường minh khi gọi WebClient

Cách an toàn, dễ kiểm soát là chỉ định registration cho request cần Bearer token bằng static helper:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

String response = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .bodyToMono(String.class)
    .block();
```

Trong một Servlet controller có principal và request context phù hợp, filter sẽ tìm hoặc authorize client ứng với registration `company-api` và gửi access token đến Reports API.

### 7.1. Tại sao đặt `clientRegistrationId` trên từng request?

Một WebClient có thể dùng để gọi nhiều endpoint, hoặc nhiều `ClientRegistration` khác nhau có cùng API host. Lựa chọn tường minh giúp:

- Code review thấy rõ token của Client nào sẽ được dùng.
- Tránh vô tình gắn token của user hiện tại vào API không cần token.
- Đặt chính sách quyền/audience riêng theo registration.
- Tránh sử dụng một “default token” cho mọi HTTP request.
- Dễ phân biệt lỗi `invalid_scope`, `invalid_client` và mapping provider.

### 7.2. Một controller MVC sử dụng WebClient

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@RestController
public class ReportsController {

    private final WebClient reportsWebClient;

    public ReportsController(
            @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports")
    public String reports() {
        return reportsWebClient.get()
            .uri("/v1/reports")
            .attributes(clientRegistrationId("company-api"))
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(10));
    }
}
```

Dòng `import static` trong ví dụ được chia để dễ đọc; trong file Java thật, hãy viết một dòng liên tục:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
```

Đoạn controller minh họa cách gắn OAuth2 attributes. Khi dùng `.block(...)` trong Spring MVC, **Servlet request thread bị chờ** đến khi downstream API trả dữ liệu. Điều này có thể chấp nhận cho một số hệ thống MVC, nhưng cần timeout, giới hạn concurrency và đánh giá tải.

Không dùng `block()` trên một **Reactor non-blocking event-loop thread** hoặc WebFlux runtime có quy tắc không cho block. Có thể giữ pipeline reactive và để MVC xử lý asynchronous return type khi framework/phiên bản hỗ trợ, nhưng phải chú ý truyền đầy đủ context OAuth2.

### 7.3. Không cần UserInfo để gọi API

`OidcUser` có thể chứa ID Token và UserInfo claims, nhưng API cần **access token** đúng scope/audience. Filter dùng `OAuth2AuthorizedClient#getAccessToken()`, không tự lấy `OidcUser#getIdToken()` để gửi Bearer.

Không viết:

```java
// SAI mục đích:
String idToken = oidcUser.getIdToken().getTokenValue();
headers.setBearerAuth(idToken);
```

ID Token dùng cho OIDC Client xác minh danh tính, không phải access token dùng gọi Resource Server.

## 8. Truyền trực tiếp một `OAuth2AuthorizedClient` đã biết

Trong Servlet MVC, Spring Security hỗ trợ `@RegisteredOAuth2AuthorizedClient` để tìm authorized client theo registration phù hợp. Khi có authorized client sẵn, có thể đưa chính object ấy cho filter:

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class ProfileProxyController {

    private final WebClient reportsWebClient;

    public ProfileProxyController(
            @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/profile")
    public String profile(
            @RegisteredOAuth2AuthorizedClient("company-api")
            OAuth2AuthorizedClient authorizedClient) {

        return reportsWebClient.get()
            .uri("/v1/me")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(10));
    }
}
```

Cách này làm **authorized client được chọn trước** và truyền trực tiếp tới WebClient request. Ưu điểm là minh bạch: filter không cần đoán registration dựa trên security context hay quy tắc mặc định.

### 8.1. Khác nhau giữa hai helper

| Helper | Giá trị truyền | Khi nào nên dùng |
|---|---|---|
| `clientRegistrationId("company-api")` | ID cấu hình Client | Muốn filter/manager tìm đúng authorized client theo principal |
| `oauth2AuthorizedClient(authorizedClient)` | Object đã được chọn/lấy trước | Controller/service đã có authorized client hợp lệ |

Không tự tạo một `OAuth2AuthorizedClient` từ raw token do browser gửi rồi đưa vào helper; object phải thuộc registration và principal đáng tin.

### 8.2. Nếu client chưa được cấp quyền thì sao?

`@RegisteredOAuth2AuthorizedClient` và manager có thể khởi động các thao tác authorization được hỗ trợ theo context. Nhưng nếu chưa có authorization code/consent cần thiết, một HTTP client filter **không thể tự hiển thị login screen đúng nghĩa** trong một background thread.

Với OAuth2 Login, hãy để người dùng đi qua `/oauth2/authorization/{registrationId}`, nhận callback và lưu authorized client. Sau đó mới gọi downstream API theo user đã được xác thực.

## 9. Nguy cơ của `setDefaultOAuth2AuthorizedClient(true)`

Một số ví dụ sử dụng:

```java
var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrations, authorizedClients
);

oauth2.setDefaultOAuth2AuthorizedClient(true);
```

Cấu hình này yêu cầu filter tự dùng authorized client gắn với `OAuth2AuthenticationToken` hiện tại làm **mặc định** khi không chỉ định client cho request.

Tính năng tiện lợi nhưng **cần hết sức thận trọng**. Theo lưu ý của Spring Security, một WebClient được cấu hình như vậy có thể gắn access token vào **mọi request** đi qua nó, bao gồm request không cần OAuth2 hoặc request tới host không liên quan.

### 9.1. Ví dụ rủi ro

```java
// WebClient dùng chung đã bật defaultOAuth2AuthorizedClient(true)
sharedWebClient.get()
    .uri("https://third-party.example.test/public-data")
    .retrieve()
    .bodyToMono(String.class);
```

Nếu filter chọn authorized client từ user hiện tại rồi gắn Bearer, access token của hệ thống có thể bị gửi tới bên thứ ba. Đây là nguy cơ lộ credential, không chỉ lỗi logic.

**Khuyến nghị thiết kế:**

1. Không bật `setDefaultOAuth2AuthorizedClient(true)` trên WebClient dùng chung cho nhiều origin.
2. Ưu tiên `clientRegistrationId(...)` hoặc `oauth2AuthorizedClient(...)` trên request cụ thể.
3. Tạo WebClient riêng cho từng Resource Server đáng tin, với `baseUrl` cố định.
4. Không cho người dùng trực tiếp quyết định absolute URL mà backend gửi Bearer token.
5. Kiểm soát HTTP redirects, proxy và việc chuyển `Authorization` header sang host khác.
6. Nếu thật sự cần default, đặt nó trên client có phạm vi rất hẹp và kiểm tra end-to-end.

### 9.2. `setDefaultClientRegistrationId(...)` cũng cần lưu ý

Ngoài mặc định theo principal đang đăng nhập, filter còn có thể được đặt một **default client registration ID**:

```java
oauth2.setDefaultClientRegistrationId("service-api");
```

Điều này hữu ích với một WebClient chuyên biệt chỉ gọi một API, nhưng nó cũng làm request không chỉ định registration có thể dùng token mặc định.

Nếu WebClient được tái sử dụng cho một host không mong muốn, vấn đề lộ token vẫn tồn tại. **Tính mặc định không thay thế allowlist API đích**.

### 9.3. WebClient theo nguyên tắc least privilege

Một thiết kế tốt có thể có:

```text
reportsWebClient:
  baseUrl = https://reports-api.example.test
  chỉ dùng company-api authorized client
  scope = reports.read

billingWebClient:
  baseUrl = https://billing-api.example.test
  chỉ dùng billing-api authorized client
  scope = invoices.read

publicWebClient:
  không có OAuth2 filter
  chỉ dùng cho dữ liệu công khai
```

Tách client như vậy làm rõ ranh giới token và giảm nguy cơ vô tình dùng một Bearer token cho nhiều Resource Server khác nhau.

## 10. OAuth2 Login principal và authorized client được chọn thế nào?

Khi người dùng đăng nhập OIDC, Spring Security có một `Authentication` trong `SecurityContext`. Với OAuth2 Login, đó thường là `OAuth2AuthenticationToken` chứa:

- Principal là `OidcUser` hoặc `OAuth2User`.
- Authorities của phiên.
- `authorizedClientRegistrationId` để biết registration đã dùng cho login.

`OAuth2AuthorizedClientRepository` và manager dùng principal/ngữ cảnh phù hợp để tra authorized client đã được cấp.

### 10.1. Một user có thể có nhiều authorized clients

Ví dụ một account nội bộ kết nối cả calendar và reports:

```text
Principal: user-782
  ├── registrationId = company-api   -> access token A
  └── registrationId = calendar-api  -> access token B
```

Khi gọi Reports API, phải chọn `company-api` chứ không tự lấy “authorized client gần nhất”. Hai token có thể có issuer, audience, scope và consent khác nhau.

### 10.2. Principal name phải ổn định và đúng user

Một authorized client thường được lưu theo `(clientRegistrationId, principalName)` trong service hoặc theo repository/session phù hợp. Nếu sau login bạn tự thay `principalName` tùy ý hoặc dùng tên user khác, filter có thể không tìm thấy token hoặc dùng sai thông tin.

Không truyền user ID lấy từ HTTP query để truy cập authorized client của một người khác. Việc chọn token theo principal phải gắn với **SecurityContext và ownership** đã được kiểm chứng.

### 10.3. Scope và role là hai thứ khác nhau

Scope `reports.read` mô tả quyền access token với API, không đồng nghĩa role `ROLE_REPORT_ADMIN` trong ứng dụng. Resource Server kiểm tra scope/audience; backend Spring MVC vẫn phải kiểm tra authorization của user với tài nguyên nội bộ.

Đừng coi việc filter đính kèm token thành công là bảo đảm user được phép xem báo cáo của account khác.

## 11. Vòng đời token: khi nào WebClient thực hiện refresh?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` không tự “đổi token” bằng cách parse JWT và tạo một Bearer token mới. Nó dùng Spring Security authorized-client infrastructure.

Một lần gọi có thể diễn ra:

```mermaid
sequenceDiagram
    autonumber
    participant C as MVC Controller
    participant F as OAuth2 WebClient Filter
    participant M as Authorized Client Manager
    participant S as Authorized Client Repository/Service
    participant AS as Authorization Server
    participant API as Reports API

    C->>F: WebClient.get() với clientRegistrationId
    F->>M: authorize theo registration + principal
    M->>S: Đọc authorized client hiện có
    alt Access token còn phù hợp
        S-->>M: Authorized client hiện tại
        M-->>F: Token hiện tại
    else Có refresh token, token cần làm mới
        M->>AS: POST /token grant_type=refresh_token
        AS-->>M: Access token mới (+ refresh token mới?)
        M->>S: Lưu authorized client mới
        M-->>F: Access token mới
    end
    F->>API: GET /v1/reports + Bearer access token
    API-->>F: HTTP response
    F-->>C: Mono / dữ liệu trả về
```

### 11.1. Access token hết hạn khác refresh token bị thu hồi

- Access token hết hạn là tình huống bình thường của OAuth2.
- Refresh token có thể giúp nhận access token mới khi Authorization Server cho phép.
- Khi refresh token bị thu hồi hoặc đã rotation, Token Endpoint có thể trả `invalid_grant`.
- Spring Security manager có cơ chế xử lý lỗi và loại bỏ authorized client hỏng theo cấu hình.
- Không mặc định mọi `OAuth2AuthorizedClient` đều có refresh token.
- HTTP session của người dùng có thể còn hợp lệ dù downstream API connection cần reauthorization.

### 11.2. `expiresAt` không phải bằng chứng API chấp nhận token

`OAuth2AccessToken#getExpiresAt()` cho biết thời hạn mà Client quản lý. API có thể vẫn từ chối token do:

- Token đã bị thu hồi.
- Audience không khớp.
- Scope không đủ.
- Issuer hoặc signing key không hợp lệ với API.
- Tenant/resource policy khác.
- Đồng hồ giữa các hệ thống lệch.

Do đó cần phân biệt lỗi **Token Endpoint** (xin/làm mới token) với lỗi **Resource Server** (sử dụng access token).

### 11.3. PKCE, nonce và OIDC ID Token nằm ở đâu?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` xử lý **outbound API call**, không thay thế các bước giao thức lúc OAuth2 Login:

- `state`/PKCE liên quan authorization request/callback.
- `nonce`/ID Token validation liên quan OIDC Login.
- Refresh token được dùng tại Token Endpoint khi cần.
- Access token được gắn vào outbound API request.
- ID Token không được đưa vào `Authorization` header của API như access token.

## 12. Xử lý 401 và 403 từ Resource Server

Ví dụ WebClient gửi:

```http
GET /v1/reports HTTP/1.1
Host: reports-api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

API có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

hoặc:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Hai lỗi có ý nghĩa khác nhau:

| Lỗi | Ý nghĩa thường gặp | Hành động phù hợp |
|---|---|---|
| HTTP 401 `invalid_token` | Access token không còn được API chấp nhận | Kiểm tra expiry, revocation, audience; cân nhắc invalidate/reacquire theo chính sách |
| HTTP 403 `insufficient_scope` | Token thiếu quyền cần thiết | Xem scope/consent/role, không refresh vô hạn |
| HTTP 401 không có OAuth error | Có thể do API auth scheme khác hoặc proxy | Kiểm tra response/Resource Server |
| HTTP 429 | Rate limit API | Backoff có giới hạn, không xóa token tùy tiện |
| HTTP 5xx | Lỗi API | Retry đúng idempotency policy, không tự quy kết OAuth2 |
| Token Endpoint `invalid_grant` | Refresh token/code không hợp lệ | Dọn authorized client lỗi và yêu cầu reauthorization khi cần |

### 12.1. Phân biệt failure handler của manager và filter

Có hai giai đoạn:

1. Manager/provider xin hoặc refresh token. Nếu Token Endpoint từ chối, lỗi thuộc **authorization/reauthorization**.
2. WebClient đã gửi access token tới API. Nếu API trả 401/403, lỗi thuộc **resource access**.

Với constructor nhận repositories, filter có thể cấu hình mặc định handler xóa authorized client dựa trên một số OAuth2 errors trả về từ Resource Server. Với constructor nhận manager, có thể cần gắn handler tường minh.

Không tự viết catch-all “cứ 401/403 thì xóa mọi token và redirect tới login”. Lỗi thiếu scope hoặc sai resource không được giải quyết bằng vô hạn lần đăng nhập lại.

### 12.2. `retrieve()` và exception của WebClient

WebClient mặc định có thể chuyển HTTP 4xx/5xx thành `WebClientResponseException` khi sử dụng `retrieve()`.

```java
import org.springframework.web.reactive.function.client.WebClientResponseException;

try {
    String body = reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(clientRegistrationId("company-api"))
        .retrieve()
        .bodyToMono(String.class)
        .block();
} catch (WebClientResponseException.Unauthorized ex) {
    // 401 từ downstream API; không mặc định là invalid_grant.
} catch (WebClientResponseException.Forbidden ex) {
    // 403, có thể do insufficient_scope hoặc business policy.
}
```

`clientRegistrationId` cần static import như ví dụ trước. Đây là đoạn minh họa xử lý lỗi, không phải service hoàn chỉnh.

Có thể cấu hình `onStatus(...)` để tạo domain exception:

```java
String body = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .onStatus(status -> status.value() == 401,
        response -> Mono.error(
            new IllegalStateException("Downstream API rejected token")
        ))
    .bodyToMono(String.class)
    .block();
```

Cần import `reactor.core.publisher.Mono`. Không đưa response headers chứa credential hoặc token thô vào exception trả frontend. Khi dùng `onStatus`, phải hiểu việc tùy biến error mapping và filter failure handling của phiên bản đang dùng để không vô tình loại bỏ thông tin lỗi OAuth2 cần thiết.

### 12.3. Khi nào cần xử lý 401 tự động?

Có thể muốn request bị 401 `invalid_token` được thực hiện lại sau khi authorized client đã bị loại bỏ hoặc cập nhật. Nhưng cần đặt giới hạn:

- Chỉ retry khi API operation có thể lặp an toàn.
- Không retry vô hạn.
- Không coi 403 `insufficient_scope` là lỗi do token hết hạn.
- Tránh retry request POST gây side effects nếu thiếu idempotency strategy.
- Không gửi token mới tới host do redirect/user input điều khiển.
- Với refresh token rotation, cần xử lý concurrency nếu nhiều request cùng refresh.

## 13. Khi filter có custom `OAuth2AuthorizedClientManager`

Nếu dự án muốn quản lý behavior của Token Endpoint, có thể cấu hình manager chủ động và đưa nó vào filter.

Ví dụ:

```java
@Bean("webAuthorizedClientManager")
OAuth2AuthorizedClientManager webAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

    var manager = new DefaultOAuth2AuthorizedClientManager(
        registrations, authorizedClients);

    manager.setAuthorizedClientProvider(provider);

    return manager;
}
```

Cần imports như mục 6.2. Sau đó:

```java
@Bean("reportsWebClient")
WebClient reportsWebClient(
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        manager);

    // Khi muốn xử lý OAuth2 resource errors riêng, cấu hình
    // oauth2.setAuthorizationFailureHandler(...) theo phiên bản
    // và kho authorized clients thực tế.

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .apply(oauth2.oauth2Configuration())
        .build();
}
```

### 13.1. Khi nào cần manager riêng?

- Nhiều ClientRegistrations/grants cần chính sách chọn grant rõ ràng.
- Muốn cấu hình Clock Skew cho refresh token provider theo phiên bản.
- Có custom access token response client/provider-specific Token Endpoint.
- Cần failure handlers/persistence khác mặc định.
- Có nhiều nguồn authorized client khác nhau trong ứng dụng.
- Muốn sử dụng manager chung ở một số tích hợp HTTP client.

Tuy nhiên, **tăng customization làm tăng trách nhiệm bảo mật và vận hành**. Nếu mặc định đã đáp ứng, không cần tự tạo custom manager cho mọi dự án.

### 13.2. Handler khi `invalid_grant`

Khi refresh token bị từ chối, Spring Security managers có những failure handling defaults nhằm loại bỏ authorized client bị lỗi khỏi repository/service phù hợp. Nếu bạn thay handler, hãy bảo toàn behavior cần thiết; nếu không, lần request tiếp theo có thể lại dùng refresh token hỏng và gây vòng lặp.

Không nhầm lỗi `invalid_grant` của Token Endpoint với 401 `invalid_token` của API. Một handler cho cái này không nhất thiết được gọi ở chỗ kia.

## 14. Servlet request context và các lời gọi bất đồng bộ

`WebClient` xây dựng pipeline Reactor. Điều này **không xóa bỏ** thực tế rằng OAuth2 state trong ứng dụng Servlet có thể phụ thuộc vào:

- `HttpServletRequest` hiện tại.
- `HttpServletResponse`, khi repository cần lưu authorized client.
- `Authentication` trong `SecurityContext`.
- Session/cookie và principal name được dùng để tra authorized client.

Vì vậy hãy nghĩ rõ context truyền tới filter.

### 14.1. Trên thread của một MVC controller

Một lệnh `WebClient` được bắt đầu và xử lý ngay trong request Servlet thường có thể lấy ngữ cảnh thích hợp theo integration. Nhưng nếu chuyển sang scheduler/async worker hoặc gọi từ một pipeline được subscribe muộn, **không được tự giả định tất cả ThreadLocal Servlet/SecurityContext còn nguyên**.

Ví dụ:

```java
@GetMapping("/reports")
public Mono<String> reports() {
    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(clientRegistrationId("company-api"))
        .retrieve()
        .bodyToMono(String.class);
}
```

Spring MVC có thể hỗ trợ return type `Mono` qua reactive adapters, nhưng thời điểm subscribe và thread xử lý có thể khác với lúc controller trả về. Với những kiến trúc như vậy, việc cung cấp authorized client/principal phù hợp **một cách tường minh** giúp giảm phụ thuộc vào ThreadLocal.

### 14.2. Chủ động lấy authorized client trước khi tạo pipeline

```java
@GetMapping("/reports")
public Mono<String> reports(
        @RegisteredOAuth2AuthorizedClient("company-api")
        OAuth2AuthorizedClient authorizedClient) {

    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

Trong nhiều trường hợp, cách này dễ lý giải hơn khi downstream call bị subscribe ở thời điểm khác. Dù vậy, object authorized client đã được lấy trước có thể trở nên cũ nếu response bị trì hoãn rất lâu hoặc refresh diễn ra ở nơi khác; ứng dụng cần hiểu lifecycle khi xử lý async kéo dài.

### 14.3. Không chuyển token tự do qua message queue

Nếu xử lý được đẩy sang hàng đợi/background job, không nên nhét raw access token vào message rồi hy vọng khi worker chạy nó vẫn còn hạn.

Một lựa chọn tốt hơn là message mang **định danh nghiệp vụ tin cậy** và worker dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` hoặc cơ chế token service phù hợp để lấy credential khi thực thi. Worker phải kiểm tra ownership trước khi tra token của user.

## 15. Khi nào không nên dùng `ServletOAuth2AuthorizedClientExchangeFilterFunction`?

Tên lớp nêu rõ mục tiêu chính là **OAuth2 WebClient trên Servlet**. Một số tình huống cần phương án khác:

| Ngữ cảnh | Phương án thích hợp |
|---|---|
| Spring MVC controller gọi API theo user đã đăng nhập | `ServletOAuth2AuthorizedClientExchangeFilterFunction` với authorized client đúng user |
| Spring WebFlux reactive server | `ServerOAuth2AuthorizedClientExchangeFilterFunction` và reactive repositories/managers |
| `@Scheduled`, queue worker, command-line task ngoài HTTP request | `AuthorizedClientServiceOAuth2AuthorizedClientManager`; tích hợp HTTP client theo service context |
| Gọi API public không cần token | WebClient không gắn OAuth2 filter |
| Backend Spring MVC muốn client đồng bộ đơn giản | `RestClient` và OAuth2 Client interceptor ở phiên bản hỗ trợ |
| Gọi resource theo quyền ứng dụng không có user | Client Credentials Grant với service manager |
| Cần nhận token do external client gửi tới API | Cấu hình Resource Server, không phải OAuth2 Client filter |

### 15.1. Job `@Scheduled` dùng manager nào?

Nếu một scheduled job gọi API bằng `client_credentials`, nó không có `HttpServletRequest`. Khi đó nên cấu hình:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

var manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        oauth2AuthorizedClientService
    );
manager.setAuthorizedClientProvider(provider);
```

Đoạn minh họa cần imports và các bean thực tế. Job gọi manager với một service principal name ổn định. **Đừng giả lập Servlet request** chỉ để dùng filter vốn được thiết kế cho web request.

### 15.2. WebClient không tự quyết định quyền của user

Với user-delegated API call, Authorization Server cấp quyền qua scope/consent, Resource Server kiểm tra access token, còn ứng dụng cần bảo vệ chính các endpoint của mình. Filter chỉ gắn token phù hợp với context mà nó được cấu hình; nó không kiểm tra ownership của từng report hoặc hóa đơn trong database nghiệp vụ.

## 16. Một ví dụ hoàn chỉnh hơn: service riêng cho Reports API

Tách cấu hình HTTP client khỏi controller và logic nghiệp vụ giúp tránh controller biết quá nhiều về token.

### 16.1. Bean WebClient chuyên dụng

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsClientConfiguration {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClientRepository) {

        var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            registrations, authorizedClientRepository);

        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
```

### 16.2. Service nhận authorized client

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@Service
public class ReportsApiClient {

    private final WebClient reportsWebClient;

    public ReportsApiClient(
            @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    public String listReports(OAuth2AuthorizedClient client) {
        if (!"company-api".equals(
                client.getClientRegistration().getRegistrationId())) {
            throw new IllegalArgumentException(
                "Unexpected OAuth2 client registration");
        }

        return reportsWebClient.get()
            .uri("/v1/reports")
            .attributes(oauth2AuthorizedClient(client))
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(10));
    }
}
```

Ở đây service chủ động kiểm tra registration ID, tránh truyền một authorized client của API khác. Với ứng dụng sản xuất, nên deserialize response thành DTO có schema, đặt timeout ở HTTP client và xử lý lỗi API theo domain.

### 16.3. Controller chỉ phối hợp

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    private final ReportsApiClient api;

    public ReportsController(ReportsApiClient api) {
        this.api = api;
    }

    @GetMapping("/reports")
    public String reports(
            @RegisteredOAuth2AuthorizedClient("company-api")
            OAuth2AuthorizedClient authorizedClient) {

        return api.listReports(authorizedClient);
    }
}
```

Các class `ReportsClientConfiguration`, `ReportsApiClient` và `ReportsController` là ba phần trong cùng một ứng dụng. Không khai báo thêm một bean `reportsWebClient` trùng tên từ ví dụ trước.

### 16.4. Trách nhiệm vẫn thuộc về ứng dụng

Khi sử dụng mẫu trên:

- Registration `company-api` phải được provider cấp access token cho Reports API.
- Người dùng phải có scope và quyền theo hợp đồng.
- Controller endpoint được bảo vệ bởi Spring Security.
- Không expose access token ra browser.
- API đích phải được kiểm soát host/route.
- Nếu token hết hạn hoặc bị thu hồi, phần authorized-client manager và failure handler cần xử lý theo chính sách.
- Không dùng ID Token hoặc refresh token làm Bearer cho Resource Server.

## 17. Thêm timeout và quản lý kết nối

WebClient dùng reactive HTTP client nhưng vẫn cần thời hạn và tài nguyên phù hợp. Đừng dùng `.block()` vô hạn trong Servlet thread.

Ví dụ timeout ở mức reactive chain:

```java
import java.time.Duration;

String result = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(8))
    .block(Duration.ofSeconds(10));
```

Đây là giá trị minh họa, không phải ngưỡng chuẩn. Với production, cần cấu hình connection timeout, response timeout, connection pool và retry theo SLO. Ngoài ra:

- Timeout trong chain có thể ngắt chờ phía Client nhưng server đích có thể đã xử lý request.
- Không retry một POST có side effect nếu thiếu idempotency strategy.
- Timeout khi refresh token rotation cần xử lý thận trọng vì Token Endpoint có thể đã tiêu thụ refresh token.
- Không log HTTP Authorization header trong quá trình chẩn đoán timeout.
- Phân biệt API timeout với Token Endpoint timeout khi thống kê lỗi.

### 17.1. SSL/TLS

Outbound OAuth2/API requests phải dùng HTTPS cho môi trường thật, trừ trường hợp phát triển đã được kiểm soát. Không tắt xác minh chứng chỉ, hostname verification hoặc đặt HTTP client “trust all” để sửa lỗi TLS.

Nếu backend chạy sau proxy hoặc dùng mTLS, hãy cấu hình truststore, client credentials và transport theo chính sách hạ tầng; không đưa token lên query string để “debug dễ hơn”.

## 18. Bảo mật khi dùng WebClient OAuth2 filter

### 18.1. Không gửi Bearer token tới host tùy ý

Giả sử controller nhận:

```java
@GetMapping("/proxy")
public String proxy(@RequestParam String url) {
    return reportsWebClient.get()
        .uri(url)
        .attributes(clientRegistrationId("company-api"))
        .retrieve()
        .bodyToMono(String.class)
        .block();
}
```

Đây là thiết kế nguy hiểm: người dùng có thể đưa một URL thuộc host bên ngoài, trong khi filter vẫn gắn access token, gây **credential exfiltration** và **SSRF**.

Thay vào đó:

- Cấu hình base URL cố định và chỉ cho phép relative paths đã được kiểm soát.
- Tách public HTTP client khỏi authenticated HTTP client.
- Không cho user chọn scheme/host/port của outbound request có token.
- Kiểm soát redirect behavior; cân nhắc chặn cross-origin redirect đối với request chứa Authorization.
- Chỉ chọn `ClientRegistration` từ allowlist server-side.

### 18.2. Lưu ý về HTTP redirect

Một HTTP client có thể tự follow 301/302/307/308 tùy cấu hình. Nếu server đích trả redirect tới host khác, cần bảo đảm token không bị chuyển sang origin không tin cậy.

Đừng dựa vào giả định “mọi HTTP client tự xóa Authorization header khi đổi host”. Hãy xem hành vi của HTTP connector/version và thiết kế URL đích, redirect policy phù hợp.

### 18.3. Không log token

Không log:

```text
Authorization: Bearer ...
access_token
refresh_token
id_token
client_secret
OAuth2 callback authorization code
raw Token Endpoint response
```

Log hữu ích hơn:

```text
registrationId=company-api
downstreamService=reports-api
httpStatus=200
oauth2Stage=RESOURCE_CALL
durationMs=123
```

Một `OAuth2AuthorizedClient` chứa credential; không gọi `toString()` rồi chuyển toàn bộ object vào log nếu không biết chính xác phiên bản redaction. Trong hỗ trợ kỹ thuật, chỉ cung cấp HAR/trace đã làm sạch.

### 18.4. Không nhầm CORS và CSRF

CORS kiểm soát browser JavaScript gọi cross-origin resources; việc **backend WebClient** gọi API là server-to-server call và thường không cần cấu hình CORS ở backend caller theo cùng cách.

CSRF protection vẫn quan trọng với HTTP endpoints dùng cookie session trong ứng dụng Spring MVC. Việc dùng OAuth2 filter trên WebClient không tự thay thế CSRF validation cho POST/PUT/DELETE mà browser gửi tới portal.

## 19. Quan sát cấu hình và gỡ lỗi

### 19.1. Checklist theo giai đoạn

Khi một call WebClient không thành công, hãy phân loại:

1. **SecurityContext:** Người dùng đã authenticated chưa? Đúng principal/OIDC provider không?
2. **ClientRegistration:** `registrationId` được yêu cầu có tồn tại không? Grant/issuer/scope đúng không?
3. **Authorized client lookup:** Có token được lưu cho principal và registration không?
4. **Token acquisition/refresh:** Có lỗi Token Endpoint như `invalid_client`, `invalid_grant` không?
5. **Outbound HTTP:** WebClient có gắn Bearer token vào đúng host/path không?
6. **Resource Server:** API trả 401, 403, 429 hay 5xx? Có Bearer error code không?
7. **Response mapping:** Lỗi decode JSON, content type, timeout hay business rule?
8. **Persistence/concurrency:** Token mới đã lưu chưa, refresh token rotation có race không?

### 19.2. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `No qualifying bean of type WebClient` | Chưa khai báo bean WebClient, thiếu WebFlux dependency | Tạo bean WebClient/Builder phù hợp |
| Không tìm thấy registration | Sai `registrationId` | So sánh YAML và `clientRegistrationId(...)` |
| `ClientAuthorizationRequiredException` hoặc cần user authorization | Chưa có authorized client và flow cần browser | Bắt đầu OAuth2 Login/consent phù hợp |
| `No thread-bound request` | Gọi request-based manager ở background | Dùng service-based manager hoặc context rõ ràng |
| API 401 `invalid_token` | Token hết hạn/thu hồi/sai audience | Chẩn đoán token/API, cơ chế cleanup nếu phù hợp |
| API 403 `insufficient_scope` | Token thiếu quyền | Xem scope/consent, không refresh vô hạn |
| Token Endpoint `invalid_grant` | Refresh token hết hạn, bị thu hồi, rotation race | Dọn state lỗi, yêu cầu reauthorization khi cần |
| Chỉ controller này không gắn token | Thiếu `attributes(...)` hoặc default chưa bật | Chỉ định client tường minh |
| Request public bị gửi Bearer token | Bật defaultOAuth2AuthorizedClient trên shared WebClient | Tách HTTP client, bỏ default, dùng explicit selection |
| Token đúng mà API vẫn 401 | Audience khác, issuer mismatch, proxy header | Xem Resource Server contract, không chỉ expiry |
| Refresh token mới không được lưu | Manager/repository/persistence sai | Kiểm tra success handler/kho lưu |
| Hai request refresh đồng thời | Rotation và concurrency | Đánh giá single-flight/locking/versioned storage |
| Controller bị treo | `.block()` thiếu timeout, downstream chậm | Đặt timeout, giới hạn tài nguyên |
| `block()` ném lỗi non-blocking thread | Dùng blocking call trong Reactor event loop | Giữ chain reactive hoặc dùng client phù hợp |
| GitHub OAuth2 login có `OAuth2User`, không có `OidcUser` | Provider không phải OIDC | Không ép cast OIDC; dùng Client registration phù hợp |
| Bean WebClient gắn sai manager | Nhiều manager cùng type, DI mơ hồ | Dùng `@Qualifier`/tên bean rõ |
| Đăng nhập vẫn được nhưng API token không còn hợp lệ | HTTP session và access token có vòng đời riêng | Refresh/reconnect đúng connection, không tự logout toàn portal |

### 19.3. Cách chẩn đoán an toàn

Trong môi trường phát triển, có thể tăng log Spring Security ở mức đủ để nhận diện flow:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Tuy nhiên, không bật wire-level HTTP logging có thể ghi Token Endpoint requests, Bearer header hay cookies vào log chia sẻ.

Một bộ dữ liệu vận hành an toàn hơn:

```text
event=reports_api_call
registrationId=company-api
principalCategory=authenticated_user
tokenPresent=true
httpStatus=403
oauth2Error=insufficient_scope
```

Không sử dụng access token hoặc `state` làm correlation ID trong log. Với dữ liệu user/tenant, áp dụng chính sách riêng tư phù hợp.

## 20. Kiểm thử ý tưởng mà không làm lộ token

### 20.1. Kiểm thử outbound header

Một test tích hợp WebClient có thể sử dụng HTTP mock server để kiểm tra:

1. Lệnh gọi đúng `https://reports-api.example.test/v1/reports` hoặc mock base URL.
2. Header `Authorization` có dạng Bearer khi authorized client được chọn.
3. WebClient gọi API công khai **không** gửi token khi không dùng OAuth2 filter.
4. Khi request không chọn registration, ứng dụng không vô tình gửi default token.
5. Error response 401/403 được xử lý thành domain error như chính sách yêu cầu.

Không in giá trị token thực vào test logs hoặc snapshot.

### 20.2. Kiểm thử nhiều registration

Cho:

```text
registrationId=reports -> access token token-A
registrationId=billing -> access token token-B
```

Kiểm thử để chắc chắn:

- Reports API nhận token A.
- Billing API nhận token B.
- Public API không nhận token.
- Request cố dùng token B ở Reports API bị từ chối theo chính sách của client/service.
- Không có code path gắn tự động token A vào host do user chỉ định.

### 20.3. Kiểm thử refresh token rotation

Giả lập Token Endpoint:

```text
Lần refresh 1:
  request refresh_token=RT-1
  response access_token=AT-2, refresh_token=RT-2

Lần refresh 2:
  request refresh_token=RT-2
  response access_token=AT-3, refresh_token=RT-3
```

Mục tiêu là xác nhận manager/repository lưu token mới và không tiếp tục dùng RT-1. Với hệ thống nhiều instance, cần kiểm thử race/concurrency và chính sách xử lý `invalid_grant`.

Đây là **các kịch bản đề xuất cho bước kiểm thử**, không phải chứng nhận rằng code demo đã được chạy hoặc QA.

## 21. Bài tập thực hành

### Bài tập 1: Chọn đúng filter

Một ứng dụng Spring Boot có Spring MVC controller, `SecurityFilterChain` và `HttpServletRequest`. Developer chọn `ServerOAuth2AuthorizedClientExchangeFilterFunction` từ hướng dẫn WebFlux.

**Câu hỏi:** có phù hợp không?

**Gợi ý đáp án:** Trong Servlet stack, nên sử dụng `ServletOAuth2AuthorizedClientExchangeFilterFunction` và kho/manager Servlet phù hợp. Variant `Server...` hướng tới reactive server context.

### Bài tập 2: Gắn access token cho một API cụ thể

Bạn có bean `reportsWebClient` với OAuth2 filter. Hãy yêu cầu registration `company-api` trên request `GET /v1/reports`.

**Gợi ý đáp án:**

```java
reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .bodyToMono(String.class);
```

### Bài tập 3: Chặn lộ token sang public API

Một shared WebClient bật `setDefaultOAuth2AuthorizedClient(true)` rồi gọi cả private API lẫn public API ở một host khác.

**Gợi ý đáp án:** Đây là rủi ro gửi nhầm Bearer token. Tách WebClient public không có OAuth2 filter, và trên private client ưu tiên chọn registration tường minh/giới hạn host đáng tin.

### Bài tập 4: Token hết hạn

Access token của user hết hạn; Client có refresh token còn hợp lệ.

**Gợi ý đáp án:** Configured manager/provider có thể thực hiện Refresh Token Grant và cập nhật authorized client. Không cần controller tự parse JWT rồi POST token refresh thủ công nếu Spring Security đã quản lý.

### Bài tập 5: API 401 nhưng token chưa hết `expiresAt`

**Gợi ý đáp án:** Có thể do revocation, audience hoặc issuer. `expiresAt` là thông tin thời gian Client có, không chứng minh Resource Server chắc chắn chấp nhận token.

### Bài tập 6: Background task dùng WebClient

Một `@Scheduled` chạy ngoài HTTP request cần gọi API bằng `client_credentials`.

**Gợi ý đáp án:** Dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` với `clientCredentials()` provider và service principal ổn định. Không cố phụ thuộc Servlet request/session.

### Bài tập 7: Dùng ID Token gọi Resource Server

Developer thấy `OidcUser#getIdToken()` nên dùng nó trong `Authorization: Bearer`.

**Gợi ý đáp án:** Sai mục đích. Dùng access token từ authorized client, đúng audience và scope của API; ID Token chỉ dùng cho xác minh danh tính tại OIDC Client.

### Bài tập 8: WebClient chuyển hướng sang host lạ

Reports API trả 302 sang một domain do user cung cấp. WebClient đang có Bearer token.

**Gợi ý đáp án:** Cần kiểm soát redirects và bảo đảm Authorization header không được gửi sang host không tin cậy. Đừng giả định connector luôn xử lý an toàn nếu chưa xác minh cấu hình.

### Bài tập 9: Nhiều authorized clients của một user

User kết nối `company-api` và `billing-api`. Controller reports gọi WebClient với mặc định “authorized client hiện tại”.

**Gợi ý đáp án:** Dễ chọn nhầm. Chỉ định `clientRegistrationId("company-api")` hoặc truyền đúng `OAuth2AuthorizedClient` để tránh lộ token và sai quyền.

### Bài tập 10: 403 khi thiếu scope

API trả `insufficient_scope`. Có nên tự refresh token 100 lần?

**Gợi ý đáp án:** Không. Refresh token thường không tự tăng quyền. Cần xin scope/consent phù hợp hoặc từ chối thao tác theo chính sách.

## 22. Checklist thiết kế

- [ ] Ứng dụng là Servlet MVC, dùng đúng **Servlet** variant của OAuth2 WebClient filter.
- [ ] `ClientRegistration` và OIDC issuer được cấu hình từ nhà cung cấp tin cậy.
- [ ] Access token được cấp đúng **Resource Server audience/scope**, không giả định login đồng nghĩa có mọi API quyền.
- [ ] WebClient có base URL đáng tin, không nhận arbitrary external URL.
- [ ] Request chọn `clientRegistrationId(...)` hoặc `oauth2AuthorizedClient(...)` rõ ràng.
- [ ] Không bật default authorized client cho một WebClient dùng chung nhiều origin.
- [ ] Không gắn ID Token hoặc refresh token vào `Authorization: Bearer` của API.
- [ ] Repository/manager lựa chọn đúng Servlet context và user principal.
- [ ] Có chính sách refresh token/rotation và xử lý `invalid_grant`.
- [ ] Phân biệt Token Endpoint errors và Resource Server HTTP 401/403.
- [ ] Với constructor manager, xem xét failure handler của filter theo version.
- [ ] Với HTTP client redirects, kiểm soát host và Authorization header.
- [ ] Có timeout và giới hạn retry phù hợp với idempotency.
- [ ] Background jobs không phụ thuộc request-based manager.
- [ ] Token/secret không xuất hiện trong URL, log hoặc frontend response.
- [ ] Đã có ý tưởng kiểm thử trường hợp API public, multi-registration và expired token.

## 23. Tài liệu tham khảo

1. [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): tổng quan OAuth2 Authorized Client và cách tích hợp HTTP clients.
2. [Spring Security Reference — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): cấu hình WebClient, chọn authorized client và failure handling.
3. [Spring Security API — ServletOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html): constructors, `clientRegistrationId(...)`, `oauth2AuthorizedClient(...)`, `oauth2Configuration()` và các cài đặt mặc định.
4. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): access token, refresh token và ClientRegistration.
5. [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): quản lý authorization và reauthorization.
6. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager cho Servlet HTTP request.
7. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager dành cho tác vụ ngoài HTTP request.
8. [Spring Security API — RegisteredOAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/annotation/RegisteredOAuth2AuthorizedClient.html): inject authorized client theo registration trong controller.
9. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): `ExchangeFilterFunction`, request/response, xử lý status và Reactor.
10. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): authorization code, access/refresh token và Token Endpoint.
11. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer` và `WWW-Authenticate` errors.
12. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): quản lý token, ràng buộc quyền và các thực hành bảo mật.

## 24. Tổng kết

**`ServletOAuth2AuthorizedClientExchangeFilterFunction` là cầu nối giữa Spring Security OAuth2 Client trên Servlet stack và các HTTP requests tạo bằng `WebClient`.** Nó giúp ứng dụng sử dụng authorized client phù hợp, có khả năng liên kết với manager/repository để lấy hoặc làm mới access token khi được phép, rồi đưa token vào `Authorization: Bearer` cho downstream API.

Các điểm không thể bỏ qua là **chọn ClientRegistration rõ ràng**, **dùng đúng access token của principal**, **bảo vệ đích HTTP được phép nhận token**, và **phân biệt lỗi Token Endpoint với lỗi Resource Server**. Sử dụng `clientRegistrationId(...)` hoặc `oauth2AuthorizedClient(...)` khi có thể; hạn chế bật default authorized client trên WebClient dùng chung. Với scheduler/worker ngoài HTTP request, hãy chuyển sang service-based authorized client manager thay vì phụ thuộc Servlet request.

Khi những ranh giới này được giữ đúng, Spring MVC vẫn có thể khai thác WebClient và Reactor để gọi các API OAuth2 an toàn, quản lý vòng đời token tập trung và hạn chế lỗi phát sinh khi ứng dụng mở rộng.
