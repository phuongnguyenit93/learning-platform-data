# Tích hợp ServerOAuth2AuthorizedClientExchangeFilterFunction với WebClient trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm kiến thức:** OAuth2 Client  
> **Mục tiêu:** Sử dụng `ServerOAuth2AuthorizedClientExchangeFilterFunction` để WebClient gắn Bearer access token đúng theo `OAuth2AuthorizedClient`; phân biệt `authorization_code`, `client_credentials`, `ReactiveOAuth2AuthorizedClientManager`, refresh/renewal và xử lý token không còn hiệu lực; triển khai Java 17+ với Spring WebFlux, Spring Security và kiểm thử không gọi IdP thật.

## 1. Bài toán: WebFlux ứng dụng A gọi API B sau OAuth2 authorization

Một ứng dụng WebFlux A cần gọi protected REST API B qua `WebClient`. B yêu cầu access token theo header:

~~~http
GET /v1/reports HTTP/1.1
Host: api.partner.example
Authorization: Bearer eyJhbGciOi...
Accept: application/json
~~~

Trong thực tế không được hardcode hoặc copy token từ incoming request vào mọi outbound request. Token phải được cấp **cho đúng OAuth2 client, đúng chủ thể, đúng API audience/scope** và được quản lý trước khi dùng.

Hai mô hình phổ biến:

- **Người dùng đăng nhập tại A bằng OIDC/OAuth2 Login:** A có `OAuth2AuthorizedClient` gắn với user, có access token do Identity Provider cấp; A gọi endpoint của provider hoặc API B **được phép nhận token đó**.
- **A chạy job/background/service-to-service:** A dùng grant `client_credentials` để lấy access token với danh tính **của ứng dụng**, không giả làm end-user. Cần manager/store phù hợp ngoài HTTP request.

Spring Security cung cấp `ServerOAuth2AuthorizedClientExchangeFilterFunction`, một `ExchangeFilterFunction` dành cho **WebFlux**, để áp dụng token quản lý bởi OAuth2 Client vào các request WebClient đã chỉ rõ authorized client hoặc registration.

**Giới hạn:** Filter chỉ gắn token và điều phối OAuth2 Client authorization. Nó **không** tự chứng minh user có quyền đọc mọi bản ghi ở B, không đổi ID Token thành access token, không tự làm token exchange, và không bảo đảm token A được chấp nhận ở mọi API B.

## 2. Phân biệt 5 thành phần dễ nhầm

| Thành phần | Gói/API tiêu biểu | Chức năng |
| --- | --- | --- |
| `ClientRegistration` | `org.springframework.security.oauth2.client.registration` | Metadata client: registrationId, clientId, secret, grant, endpoints, scopes |
| `OAuth2AuthorizedClient` | `org.springframework.security.oauth2.client` | Ghép ClientRegistration + principal name + access token (+ refresh token nếu có) |
| `ReactiveOAuth2AuthorizedClientManager` | OAuth2 Client | Xin token, re-authorize/refresh theo grant provider, phối hợp persistence |
| `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` | OAuth2 Client | Lưu và đọc authorized clients cho web requests hoặc application-level |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | OAuth2 Client WebClient | Chọn client và thêm `Authorization: Bearer ...` khi gửi downstream |

Một `ClientRegistration` **chưa có token**; một `OAuth2AuthorizedClient` mới đại diện client đã có authorization. Một WebClient bình thường **không tự động mang access token** vì người dùng A đã login; bạn cần filter và cách chọn client tương ứng.

`ServerOAuth2AuthorizedClientExchangeFilterFunction` nằm trong package:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

**Không dùng `ServletOAuth2AuthorizedClientExchangeFilterFunction` trong WebFlux**: tên đó dành cho Servlet runtime và `OAuth2AuthorizedClientManager` imperative. Ở Reactive dùng `ReactiveOAuth2AuthorizedClientManager` và `SecurityWebFilterChain`/`ServerHttpSecurity`.

## 3. Filter hoạt động vào thời điểm nào?

Một đoạn WebClient:

~~~java
webClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("partner"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Ở thời điểm tạo publisher, ứng dụng mới **mô tả** HTTP request. Khi có subscription, WebClient chạy filter chain, filter đọc `ClientRequest.attributes()`, chọn OAuth2 client, gọi authorized client manager nếu cần và gắn token:

~~~mermaid
flowchart TD
    A["Subscriber"] --> B["WebClient ExchangeFilterFunction"]
    B --> C{"Có OAuth2AuthorizedClient explicit?"}
    C -->|"Có"| D["Dùng explicit client; có thể re-authorize"]
    C -->|"Không"| E{"Có clientRegistrationId?"}
    E -->|"Có"| F["Manager tìm/xin authorized client"]
    E -->|"Không"| G{"Default client được bật?"}
    G -->|"Không"| H["Gửi request không tự gắn OAuth2 token"]
    G -->|"Có"| F
    D --> I{"Token còn dùng được?"}
    F --> I
    I -->|"Cần refresh/renew"| J["AuthorizedClientProvider thực hiện grant"]
    J --> K["Lưu authorized client khi phù hợp"]
    I -->|"Có"| L["Thêm Authorization Bearer"]
    K --> L
    L --> M["HTTP request đến Resource Server"]
    M --> N["Resource Server tự xác minh issuer/audience/scope"]
~~~

Filter có thể yêu cầu token mới khi client chưa được authorize, re-authorize khi token đã hết hạn hoặc gần hết hạn **nếu grant provider phù hợp**. Access token có thể được refresh khi có refresh token; `client_credentials` thường xin token **mới**, không cần giả định có refresh token.

**Reactive là lazy:** không dùng `subscribe()` tùy tiện trong service, không gọi `block()` ở WebFlux event loop. Trả `Mono`/`Flux` đến tầng sở hữu subscription (WebFlux runtime, scheduler được thiết kế, hoặc test).

## 4. Authorization Code khác Client Credentials

| Tiêu chí | `authorization_code` + OIDC | `client_credentials` |
| --- | --- | --- |
| Chủ thể | Người dùng đăng nhập/ủy quyền | Chính ứng dụng/service |
| Có browser redirect? | Có, để login/consent | Không |
| Có callback? | Có, `/login/oauth2/code/{registrationId}` thường gặp | Không |
| Có refresh token? | Tùy provider/scopes/policy | Thường không; xin token mới |
| Authorized client key | User/registration | Stable service principal/registration |
| Dùng khi | A thay mặt user gọi UserInfo/API đúng audience | Job hoặc backend A gọi API B bằng quyền của A |
| Rủi ro | Forward nhầm user token tới sai API/tenant | Dùng machine token như quyền của một end-user |

Nếu nhu cầu là **“A gọi B thay mặt người dùng”**, user access token chỉ được gửi tới B khi **B là audience hợp lệ và scope phù hợp**. Nếu token chỉ dành cho A hoặc Google UserInfo, không chuyển tiếp sang B. Có thể cần OAuth2 Token Exchange / On-Behalf-Of theo khả năng IdP thay vì tự gửi cùng token sang mọi service.

Nếu A sử dụng `oauth2ResourceServer().jwt()` để nhận inbound token, điều đó **không tự tạo authorized client** phục vụ outbound WebClient. Muốn chủ động lấy token khác, cấu hình OAuth2 Client/Authorized Client Manager riêng.

## 5. Những cách chọn authorized client

Tại từng request WebClient, nên chọn client **tường minh** bằng một trong hai cách:

### 5.1. Truyền authorized client đã có

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

return webClient.get()
    .uri("/v1/userinfo")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
~~~

Đây là **đoạn trích Java minh họa method body** (static import trên nhiều dòng ở đây chỉ thể hiện tên API, khi copy code cần viết import đúng một dòng). `authorizedClient` là `OAuth2AuthorizedClient` do Spring cung cấp hoặc manager trả về, **không** phải token string được nhận từ request body.

### 5.2. Truyền registrationId

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

return webClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Manager dùng ID để tìm registration/client và xin token theo grant. Với client_credentials gọi từ background job, vẫn cần một **service principal ổn định** để quản lý cache; không dùng một username bất kỳ của HTTP request như machine identity.

### 5.3. Không nên bật default toàn cục

Filter còn có:
- `setDefaultOAuth2AuthorizedClient(true)`: có thể chọn token từ `Authentication` của user đăng nhập OAuth2.
- `setDefaultClientRegistrationId("reports-service")`: có thể chọn registration mặc định.

**Cẩn trọng:** khi bật các lựa chọn này, mọi request qua WebClient được cấu hình có thể nhận token. Nếu URL được client điều khiển, WebClient gọi host khác, redirect follow sai hoặc cùng bean dùng nhiều mục đích, có nguy cơ **rò credential đến dịch vụ không tin cậy**. Bài này **không bật hai defaults**; caller phải chỉ rõ authorized client/registration và dùng WebClient có base URL cố định.

## 6. Hai constructor có failure handling khác nhau

Spring Security 6.x có hai constructor quan trọng:

~~~java
// Cách A: truyền manager rõ ràng.
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveAuthorizedClientManager);

// Cách B: truyền registration repo + authorized-client repo cho web.
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveClientRegistrationRepository,
    serverOAuth2AuthorizedClientRepository);
~~~

**Khác biệt quan trọng được tài liệu API ghi rõ:** constructor nhận `ReactiveClientRegistrationRepository` + `ServerOAuth2AuthorizedClientRepository` tự thiết lập `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` để xử lý một số lỗi authorization/authentication từ downstream. Constructor nhận **manager** thì **không tự đặt handler tương ứng**, nếu muốn loại client/token không còn hợp lệ phải gọi `setAuthorizationFailureHandler(...)` đúng repository/service đang lưu.

Handler chỉ gỡ authorized client theo các điều kiện/error code được hỗ trợ; **không** biến mọi 403 thành “xin token mới rồi chắc chắn thành công”. `insufficient_scope` có thể yêu cầu chính sách cấp quyền khác thay vì refresh. Không retry vô hạn khi bị 401/403, đặc biệt với HTTP POST không idempotent.

## 7. Project hoàn chỉnh: OIDC login rồi gọi Google UserInfo bằng WebClient

Để lab có hành vi end-to-end đúng audience, ta chọn **Google OpenID UserInfo API** làm downstream, thay vì gửi Google token sang một API doanh nghiệp không thuộc phạm vi Google.

- User đăng nhập Google bằng `oauth2Login()` của Spring WebFlux.
- Sau login, `OAuth2AuthorizedClient` tương ứng registration `google` chứa access token được cấp cho Google APIs/UserInfo.
- WebClient được filter gắn Bearer access token khi gọi `https://openidconnect.googleapis.com/v1/userinfo`.
- Controller chỉ trả `sub` từ UserInfo đã nhận, không trả token, email hoặc toàn bộ claims.
- Test sử dụng mock OIDC principal, fake manager và fake downstream, **không phải đăng nhập Google thật**.

Yêu cầu **Java 17+, Maven**. Ví dụ dùng Spring Boot `3.3.13` tương thích Spring Security 6.x như mốc học tập; nhánh 3.3 đã kết thúc hỗ trợ OSS. Khi triển khai production mới cần nâng lên nhánh được hỗ trợ và kiểm tra APIs/tests theo phiên bản thực tế.

~~~text
reactive-oauth2-webclient/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/client/
    │   │   ├── ClientApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── WebClientConfig.java
    │   │   └── UserInfoController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/client/
        ├── OidcWebFlowTest.java
        └── OAuth2FilterTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-oauth2-webclient</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Không thêm `spring-boot-starter-web` của Servlet**. Java/Reactive code trong lab dùng `ServerHttpSecurity`/`SecurityWebFilterChain` và `ServerOAuth2AuthorizedClientExchangeFilterFunction`, không dùng các class Servlet cùng tên.

### 7.2. ClientApplication.java

~~~java
package demo.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

### 7.3. application.yml

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID:demo-client-id}
            client-secret: ${GOOGLE_CLIENT_SECRET:demo-client-secret}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
~~~

Spring Boot có provider defaults cho `google`, vì vậy không phải viết authorization/token/userinfo URIs thủ công trong lab. Hai giá trị `demo-client-id` / `demo-client-secret` chỉ giúp **khởi tạo test context** mà không tiết lộ credential thật; Google sẽ không chấp nhận chúng cho login thật.

Để login end-to-end, tạo OAuth2 Web Application client tại Google và đăng ký redirect URL `http://localhost:8080/login/oauth2/code/google`. Đặt `GOOGLE_CLIENT_ID` và `GOOGLE_CLIENT_SECRET` bằng credentials của chính ứng dụng, không commit secret hoặc gửi sang browser.

## 8. SecurityConfig.java: bảo vệ inbound request và bật OAuth2 Login

~~~java
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/login").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/me", "/api/userinfo").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình này giải quyết **inbound authentication** cho browser. Khi user chưa đăng nhập, app chuyển đến OAuth2 login; sau login, WebSession ghi nhớ user. Nó **không** tự gắn token vào outbound HTTP — đó là nhiệm vụ của filter WebClient ở mục tiếp theo.

`anyExchange().denyAll()` bảo vệ các route chưa định nghĩa. CSRF của WebFlux vẫn được Spring bật theo mặc định, quan trọng nếu sau này thêm POST dùng browser session cookie. Đừng tắt CSRF toàn ứng dụng chỉ vì đang dùng OAuth2 Login.

## 9. WebClientConfig.java: gắn ServerOAuth2AuthorizedClientExchangeFilterFunction

~~~java
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    WebClient googleUserInfoWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var oauth = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            registrations, authorizedClients);

        // Không gọi setDefaultOAuth2AuthorizedClient(true).
        // Không gọi setDefaultClientRegistrationId("google").
        // Chỉ gửi Bearer khi caller chọn authorized client tường minh.
        return WebClient.builder()
            .baseUrl("https://openidconnect.googleapis.com")
            .filter(oauth)
            .build();
    }
}
~~~

**Tại sao chọn constructor này?** Lab là **web flow sau oauth2Login**, có `ServerOAuth2AuthorizedClientRepository`. Constructor nhận registration repo + authorized client repo tạo manager web phù hợp và tự cấu hình failure handler có thể loại authorized client không còn hiệu lực khi downstream gửi OAuth2 error tương ứng.

**Tại sao base URL cố định?** Filter có thể gắn Bearer token; không cho user kiểm soát destination URI, không gửi token sang địa chỉ được nhập trong query parameter hay lấy từ redirect không đáng tin. Khi cần gọi nhiều APIs, dùng các **WebClient beans riêng**, gắn filter/token policy ở bean dành cho host đáng tin.

Không dùng global `WebClient.Builder` đã bị gắn oauth filter cho mọi outbound call (telemetry, image fetcher, webhook, external search, download URL…). Điều đó khiến credential có thể đi tới nơi không có quyền nhận.

## 10. UserInfoController.java: lấy OAuth2AuthorizedClient và gọi WebClient

~~~java
package demo.client;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class UserInfoController {

    private final WebClient googleClient;

    public UserInfoController(WebClient googleUserInfoWebClient) {
        this.googleClient = googleUserInfoWebClient;
    }

    @GetMapping("/")
    public Mono<Map<String, String>> index() {
        return Mono.just(Map.of(
            "message", "Login at /oauth2/authorization/google"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of("subject", user.getSubject()));
    }

    @GetMapping("/api/userinfo")
    public Mono<Map<String, String>> userInfo(
            @RegisteredOAuth2AuthorizedClient("google")
            OAuth2AuthorizedClient authorizedClient) {

        return googleClient.get()
            .uri("/v1/userinfo")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(JsonNode.class)
            .map(json -> {
                String subject = json.path("sub").asText("");
                if (subject.isBlank()) {
                    throw new IllegalStateException(
                        "Provider UserInfo response has no subject");
                }
                return Map.of("subject", subject);
            });
    }
}
~~~

**Điểm tích hợp chính:**

1. `@RegisteredOAuth2AuthorizedClient("google")` giúp Spring resolve authorized client từ cơ chế OAuth2 Client và current user.
2. `.attributes(oauth2AuthorizedClient(authorizedClient))` chỉ định rõ client có token cho **request cụ thể**.
3. Filter kiểm tra/ủy quyền lại nếu phù hợp, gắn `Authorization: Bearer <access-token>` rồi gọi Google UserInfo.
4. Controller chuyển đổi JSON của Google thành chỉ `subject`, không xuất raw token hay PII khác.
5. `retrieve()` mặc định báo lỗi trên HTTP 4xx/5xx (`WebClientResponseException`). Không biến lỗi downstream thành dữ liệu hợp lệ.

Tại sao chọn Google UserInfo? Access token có OIDC scopes `openid/profile/email` từ Google là token **phù hợp để truy cập Google UserInfo**. Một partner API tùy ý không được dùng token này chỉ vì nó cũng đòi Bearer. Muốn tích hợp B của doanh nghiệp, thay registration/IdP và xác minh B thực sự là audience của token được cấp.

`/api/me` đọc thông tin trong `OidcUser` **không cần outbound WebClient**; `/api/userinfo` mới cố ý dùng OAuth2 Client filter. Điều này minh họa rõ: login và WebClient token relay là hai bước riêng.

## 11. Kiểm thử filter không cần Google thật: ý tưởng

Chúng ta không nên viết test sử dụng secret thật hoặc gọi IdP mỗi lần build. Thay vào đó:

- Tạo `ClientRegistration` và `OAuth2AuthorizedClient` giả với access token **chỉ phục vụ kiểm thử**.
- Mock `ReactiveOAuth2AuthorizedClientManager` để trả authorized client. **Không** thực hiện token endpoint request.
- Dùng `ExchangeFunction` giả làm downstream, ghi lại `ClientRequest` nhưng **không phát HTTP ra ngoài**.
- Tạo WebClient thật với OAuth2 filter và kiểm tra header Bearer; đây là kiểm thử hành vi gắn token.
- Tạo WebClient không đặt client attribute: khi defaults tắt, filter không tự gắn Bearer.
- Kiểm thử một request chọn `clientRegistrationId("reports-service")` và một request chọn `oauth2AuthorizedClient(...)`.
- Kiểm thử lỗi từ manager không bị che thành response thành công.

**Đừng dùng token giả trong production.** Test ở đây không chứng minh JWT signature, issuer/audience, refresh token server, HTTP TLS hay sự tồn tại của API thật.

## 12. OAuth2FilterTest.java: kiểm tra Bearer header thực sự

~~~java
package demo.client;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

import java.time.Instant;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OAuth2FilterTest {

    private OAuth2AuthorizedClient fakeClient() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-service")
                .clientId("not-a-real-client")
                .clientSecret("not-a-real-secret")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.invalid/oauth2/token")
                .scope("reports.read")
                .build();

        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fake-test-access-token",
            Instant.now().minusSeconds(5),
            Instant.now().plusSeconds(3600),
            Set.of("reports.read"));

        return new OAuth2AuthorizedClient(
            registration, "reports-job", token);
    }

    private ExchangeFunction fakeDownstream(
            AtomicReference<ClientRequest> observed) {
        return request -> {
            observed.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .body("ok")
                .build());
        };
    }

    @Test
    void addingRegistrationIdAddsBearerHeader() {
        var manager = mock(ReactiveOAuth2AuthorizedClientManager.class);
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(Mono.just(fakeClient()));

        var captured = new AtomicReference<ClientRequest>();
        WebClient client = WebClient.builder()
            .exchangeFunction(fakeDownstream(captured))
            .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager))
            .build();

        Mono<String> reply = client.get()
            .uri("https://api.example.invalid/v1/reports")
            .attributes(clientRegistrationId("reports-service"))
            .retrieve()
            .bodyToMono(String.class);

        StepVerifier.create(reply)
            .expectNext("ok")
            .verifyComplete();

        assertNotNull(captured.get());
        assertEquals("Bearer fake-test-access-token",
            captured.get().headers().getFirst(HttpHeaders.AUTHORIZATION));

        verify(manager).authorize(
            org.mockito.ArgumentMatchers.argThat(request ->
                "reports-service".equals(
                    request.getClientRegistrationId())));
    }

    @Test
    void explicitAuthorizedClientAddsBearerHeader() {
        OAuth2AuthorizedClient fake = fakeClient();
        var manager = mock(ReactiveOAuth2AuthorizedClientManager.class);
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(Mono.just(fake));

        var captured = new AtomicReference<ClientRequest>();
        WebClient client = WebClient.builder()
            .exchangeFunction(fakeDownstream(captured))
            .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager))
            .build();

        StepVerifier.create(client.get()
                .uri("https://api.example.invalid/v1/reports")
                .attributes(oauth2AuthorizedClient(fake))
                .retrieve()
                .bodyToMono(String.class))
            .expectNext("ok")
            .verifyComplete();

        assertEquals("Bearer fake-test-access-token",
            captured.get().headers().getFirst(HttpHeaders.AUTHORIZATION));
    }

    @Test
    void noSelectionAndNoDefaultMeansNoBearer() {
        var manager = mock(ReactiveOAuth2AuthorizedClientManager.class);
        var captured = new AtomicReference<ClientRequest>();

        WebClient client = WebClient.builder()
            .exchangeFunction(fakeDownstream(captured))
            .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager))
            .build();

        StepVerifier.create(client.get()
                .uri("https://api.example.invalid/public")
                .retrieve()
                .bodyToMono(String.class))
            .expectNext("ok")
            .verifyComplete();

        assertNotNull(captured.get());
        assertNull(captured.get().headers()
            .getFirst(HttpHeaders.AUTHORIZATION));
        org.mockito.Mockito.verifyNoInteractions(manager);
    }
}
~~~

Các assertion đầu chỉ chứng minh filter chọn đúng client và gắn đúng Bearer header. Test thứ ba chứng minh nếu không chọn OAuth2 client và không bật defaults, request không tự được thêm token.

**Đây là test không network**: `ExchangeFunction` trả response giả. Nó không chứng minh token server nhận, không thử provider refresh/revoke và không chứng minh bearer token có audience chính xác. Cần thêm integration tests với fake IdP/JWKS hoặc sandbox provider khi triển khai.

### Tại sao không chép token bằng .defaultHeader?

Sai về thiết kế:

~~~java
WebClient webClient = WebClient.builder()
    .defaultHeader("Authorization", "Bearer " + token)
    .build();
~~~

Token có thể hết hạn, bị thu hồi hoặc dùng sai principal; mọi request có header cố định dù gọi host khác. Filter + AuthorizedClientManager là cách gắn token theo client/grant/expiry policy. Dù vậy, **filter không tự bảo vệ chống token leak nếu chính bạn chọn sai client/URI**.

## 13. OidcWebFlowTest.java: xác thực HTTP app độc lập khỏi downstream

~~~java
package demo.client;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OidcWebFlowTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPageIsReadable() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").exists();
    }

    @Test
    void anonymousUserMustLoginBeforeViewingProfile() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void mockOidcLoginMakesProfileReadable() {
        client.mutateWith(
                mockOidcLogin().idToken(token ->
                    token.claim("sub", "subject-123")))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("subject-123");
    }

    @Test
    void unknownRouteIsNotAccidentallyPublic() {
        client.mutateWith(mockOidcLogin())
            .get()
            .uri("/api/unknown")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các test trên chạy WebFlux security chain và controller, **không thực hiện login Google thật**, không gọi `/api/userinfo` để tránh network. `mockOidcLogin()` là test mutator cho security context; nó không ký JWT hoặc chứng minh issuer/audience validation. Để test full login cần fake IdP hoặc môi trường IdP sandbox có code flow thực sự.

## 14. Chạy test và login end-to-end với Google

Tại thư mục `pom.xml`:

~~~bash
mvn clean test
~~~

Kỳ vọng các phương thức test trên hoạt động với Java 17+ và dependency phù hợp. Output cụ thể của Maven tùy toolchain. `OAuth2FilterTest` dùng token giả và ExchangeFunction giả, không yêu cầu Google credentials.

Để login thật, tạo OAuth2 Web Application client tại Google, cho phép callback:

~~~text
http://localhost:8080/login/oauth2/code/google
~~~

Với Bash/zsh:

~~~bash
export GOOGLE_CLIENT_ID="id-from-google-console"
export GOOGLE_CLIENT_SECRET="secret-from-google-console"
mvn spring-boot:run
~~~

Với PowerShell:

~~~powershell
$env:GOOGLE_CLIENT_ID = "id-from-google-console"
$env:GOOGLE_CLIENT_SECRET = "secret-from-google-console"
mvn spring-boot:run
~~~

Sau khi chạy, mở browser:
- `http://localhost:8080/oauth2/authorization/google` — bắt đầu Authorization Code login.
- `http://localhost:8080/api/me` — subject từ `OidcUser` trong session local.
- `http://localhost:8080/api/userinfo` — Spring resolve `OAuth2AuthorizedClient`, WebClient filter gửi Bearer tới Google UserInfo và trả subject rút gọn.

**Không có một stdout subject cố định.** Giá trị `sub` tùy user Google thật. Nếu client ID/secret hoặc redirect URI sai, login thất bại tại provider và không thể kiểm chứng đường WebClient hoàn chỉnh. Không chèn secret thật vào README, Git hoặc ảnh chụp terminal.

## 15. Mô hình client_credentials cho background job

Khác với browser login, một job scheduled/backend cần token **danh tính ứng dụng**, không phải access token của người dùng đang đăng nhập. Thay `oauth2Login` bằng registration có grant `client_credentials`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: reporting-idp
            client-id: ${REPORT_CLIENT_ID}
            client-secret: ${REPORT_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: reports.read
        provider:
          reporting-idp:
            token-uri: ${REPORT_TOKEN_URI}
~~~

Đây là **cấu hình biến thể**, không đặt chung vào project Google nếu không cần hai clients. `REPORT_TOKEN_URI` phải do IdP cung cấp và dùng HTTPS. Không sử dụng issuer URI tùy ý do caller nhập hoặc cấp client secret cho frontend.

Trong non-web environment, dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` gắn `ReactiveOAuth2AuthorizedClientService`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Bean
ReactiveOAuth2AuthorizedClientManager serviceManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClients) {

    ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager = new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
        registrations, authorizedClients);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

**Cách dùng trên là bean tùy chọn cho service-to-service**, không phải copy thẳng vào `WebClientConfig` của lab Google khi đang dùng `authorization_code`. Với `client_credentials`, không có browser, state hay login callback; token endpoint cấp access token cho ứng dụng. Manager quản lý token theo registration và **principal key** gắn với authorized client.

### Principal ổn định trong job

Một job có thể gọi manager rõ ràng, tránh phụ thuộc Authentication của HTTP request:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

public Mono<OAuth2AuthorizedClient> authorizeMachine(
        ReactiveOAuth2AuthorizedClientManager manager) {

    var authorizeRequest = OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("machine-reports")
        .build();

    return manager.authorize(authorizeRequest)
        .switchIfEmpty(Mono.error(new IllegalStateException(
            "No machine authorized client available")));
}
~~~

Từ authorized client này, gửi WebClient request bằng `.attributes(oauth2AuthorizedClient(authorizedClient))`. Trong một job **không có user Reactor SecurityContext**, filter có thể dùng principal name của explicit authorized client cho authorization/refresh. Không dùng principal của người xem báo cáo để định danh một `client_credentials` cache entry nếu token thực chất là machine token, tránh phân mảnh cache và nhầm quyền.

Nếu có inbound HTTP Authentication và cần gọi downstream bằng machine token, quản lý **ranh giới machine credential** tách khỏi user token và kiểm thử principal selection/context; đừng ép setDefaultOAuth2AuthorizedClient(true) vì lúc đó token user có thể bị gửi thay vì token service.

## 16. Manager constructor: gắn failure handler cho token cache

Khi tạo filter bằng manager:

~~~java
var oauth = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);
~~~

**Nên xem xét handler loại bỏ authorized client không còn hiệu lực**, vì constructor này không tự cấu hình handler xử lý downstream 401/403:

~~~java
import org.springframework.security.oauth2.client.RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;

// Đoạn nằm trong một @Bean WebClient ở cấu hình service-to-service.
var oauth = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);

var handler =
    new RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler(
        (registrationId, principal, attributes) ->
            authorizedClientService.removeAuthorizedClient(
                registrationId, principal.getName()));

oauth.setAuthorizationFailureHandler(handler);

WebClient webClient = WebClient.builder()
    .baseUrl("https://reports.partner.example")
    .filter(oauth)
    .build();
~~~

Đoạn này là **snippet cấu hình độc lập**, biến `authorizedClientManager` và `authorizedClientService` được inject từ Spring. Method `removeAuthorizedClient(registrationId, principalName)` phải tác động vào **chính store** nơi manager lưu authorized client. Nếu trong web flow dùng `ServerOAuth2AuthorizedClientRepository` thay vì service store, remover cũng phải phù hợp repository, không xóa nhầm cache.

**401 vs 403:** Nếu Resource Server trả `WWW-Authenticate: Bearer error="invalid_token"`, việc bỏ token cached và xin lại ở request sau có thể có ý nghĩa. Nếu trả `insufficient_scope`, thường người gọi **thiếu quyền**, không phải token đã hết hạn. Không tạo retry loop vô hạn hoặc tự cấp thêm scope ngoài quyền được IdP cho phép.

Tài liệu filter nêu rõ: **constructor registration repo + server repo** tự gắn RemoveAuthorizedClient failure handler; **constructor manager** không tự gắn. Đây là khác biệt API phải được kiểm tra khi refactor từ một constructor sang constructor kia.

## 17. Refresh token, re-authorization và expiry

Một `OAuth2AuthorizedClient` có access token với `issuedAt`/`expiresAt` và có thể có refresh token. Manager làm việc với `ReactiveOAuth2AuthorizedClientProvider` được cấu hình cho các grants:

- `authorization_code`: người dùng thực hiện browser login; về sau token có thể được refresh nếu được cấp refresh token và provider hỗ trợ.
- `refresh_token`: đổi access token hết/gần hết hạn lấy token mới; refresh token có thể bị rotate, revoke hoặc bị từ chối.
- `client_credentials`: nếu token hết hạn, service xin access token mới tại token endpoint, thường không nhận refresh token.
- Extension grants như token exchange: cần provider/registration/support riêng; không mặc định hoạt động chỉ vì có OAuth2 filter.

**Đừng tự tạo “refresh” bằng cách gửi lại cùng access token khi nhận 401.** 401 có thể do sai audience, issuer, revoked credential, clock skew hoặc user bị khóa; xin token mới không tự sửa các lỗi định tuyến/quyền. `403 insufficient_scope` thường phải sửa scope/authorization policy hơn là retry.

Đối với OAuth2 Login WebFlux, `@RegisteredOAuth2AuthorizedClient`/manager có thể re-authorize phù hợp, nhưng session/authorized client repository phải tồn tại và có thể lưu token mới. Với nhiều nodes, cần persistence nhất quán nếu cần token cache giữa các requests.

**Retry an toàn:** nếu WebClient gửi POST tạo side effect rồi bị timeout, không tự retry chỉ vì nghĩ token không đến server. Dùng idempotency key, conditional update hoặc API contract phù hợp; token renewal và HTTP retry là **hai quyết định khác nhau**.

## 18. User token, Machine token và Relay: đừng chọn sai danh tính

| Inbound request | Outbound cần gì? | Thiết kế phù hợp |
| --- | --- | --- |
| Browser login tại A | A gọi Google UserInfo | OAuth2 Login authorized client + explicit `oauth2AuthorizedClient` |
| Browser login tại A | A gọi API B thay user | Access token đúng B audience + scopes; có thể token exchange/OBO |
| HTTP request đến A mang Bearer JWT | A gọi B | Không tự giả định relay; cần token relay được cho phép hoặc token exchange |
| Background job không user | A gọi B với quyền app | `client_credentials` + service manager + stable principal |
| A gọi public HTTP endpoint | Không token | WebClient riêng không OAuth2 filter hoặc không chọn client |

**Không dùng ID Token để gọi B như access token.** ID Token có audience là OAuth2 Client, còn access token dành cho Resource Server. Không truyền một Google access token tới API doanh nghiệp chỉ vì cả hai dùng Bearer header.

**Không tự lấy tenant/owner của user từ input HTTP rồi chèn vào principal machine.** Machine token và user delegation là hai trust boundaries; nếu B cần audit end-user phải truyền actor identity theo cơ chế tin cậy, không giả danh qua một header tùy ý như `X-User: alice`.

Nếu user có nhiều tenants hoặc nhiều registrations, WebClient request phải chỉ rõ **đúng client/tenant và đúng tài nguyên**. Đừng để `registrationId` do caller đưa vào mà không có allowlist; một service có nhiều client secrets có thể bị lợi dụng để gọi APIs ngoài phạm vi.

## 19. Các vấn đề bảo mật WebClient và token leakage

**1. Default token cho mọi request:** tránh `setDefaultOAuth2AuthorizedClient(true)` trên WebClient dùng chung nhiều destinations.

**2. URL do client chọn:** nếu API chấp nhận `?url=https://...` rồi WebClient có filter OAuth2, attacker có thể buộc gửi token tới host độc hại (SSRF + credential exfiltration). Hạn chế host/path cố định và kiểm soát redirect behavior.

**3. Redirect từ downstream:** không tự giả định WebClient/connector sẽ không theo redirect hoặc khi theo redirect sẽ xóa Authorization đúng. Kiểm thử HTTP client configuration, redirect policy, allowed hosts và TLS; tuyệt đối không chuyển token qua redirect sang host mới ngoài allowlist.

**4. Không log Bearer/secret:** loại bỏ `Authorization`, `Cookie`, `Set-Cookie`, token response JSON, client secret, refresh token, code khỏi application logs, HTTP wiretap, APM và screenshots.

**5. TLS:** token endpoint và API phải dùng HTTPS với chứng chỉ hợp lệ. Đừng tắt TLS verification để “fix” `SSLHandshakeException`.

**6. Token đúng audience:** B phải xác minh token hợp lệ cho B; A cũng cần biết token do IdP cấp đúng cho B. Filter không tự làm audience validation của B.

**7. Least privilege:** scope chỉ vừa đủ, client credentials có giới hạn, rotate client secrets, token TTL ngắn, refresh token được bảo vệ server-side.

**8. Cache isolation:** authorized clients được lưu theo registration/principal; phải ngăn token của Alice được dùng cho Bob do dùng chung principal key/Repository sai.

**9. Data-level authorization:** dù token hợp lệ, B vẫn phải kiểm tra tenant/owner/action trên object; token signature không tự cấp mọi quyền.

**10. Timeout/pressure:** timeout hợp lý cho IdP/token endpoint, downstream WebClient và circuit breaking; không tạo một refresh storm khi đồng thời nhiều requests gặp token gần hết hạn.

## 20. Reactor Context và WebClient filter

Ở WebFlux, `ReactiveSecurityContextHolder` chứa authentication trong Reactor Context gắn với subscription. OAuth2 filter có thể dùng nó để xác định current principal khi manager authorization/refresh.

~~~java
public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Lưu ý:

- Đừng dùng Servlet `SecurityContextHolder` ThreadLocal rồi mong giá trị bám theo reactive scheduler.
- `publishOn` trong cùng Reactor chain thường bảo toàn Reactor Context; **tự subscribe nhánh khác** hoặc tự tạo thread/callback tách rời thì không tự có cùng context.
- Nếu có nhiều OAuth2 client cùng một user, chọn bằng `clientRegistrationId` hoặc explicit authorized client; không suy luận current OAuth2AuthenticationToken luôn là token đúng cho B.
- Với background job, context thường không có user login: dùng authorized client manager loại service và stable principal.
- Không tự gọi `block()` trong service để “lấy token rồi tạo request”; dùng `flatMap` hoặc để filter thực hiện trong reactive pipeline.
- Nếu phải gọi REST ngoài trong một DB transaction, nhớ rằng transaction DB **không rollback HTTP side effect**. Cân nhắc outbox/idempotency thay vì ghép external call với transaction rồi nghĩ atomic.

## 21. CORS và CSRF có liên quan ở tầng nào?

**Outbound WebClient là HTTP client server-side**, không chịu Same-Origin Policy/CORS của browser. Không cần thêm `Access-Control-Allow-Origin` vào request WebClient đến Google/IdP để “cho token hoạt động”.

**Inbound browser session** qua `oauth2Login` thường có WebSession cookie; các POST/PUT/PATCH/DELETE do browser tạo có thể cần CSRF token. Spring Security WebFlux bật CSRF theo mặc định. Tắt CSRF vì “đằng sau dùng Bearer WebClient” là sai: cookie browser–A và access token A–B là **hai HTTP boundaries**.

Nếu frontend khác origin gọi A bằng credentialed fetch, phải cấu hình CORS có allowlisted origin và credentials đúng, nhưng CORS không thay CSRF. API B do backend gọi qua WebClient **không** cần browser preflight.

Với SPA trực tiếp gọi Resource Server bằng Bearer header, outbound OAuth2 Client trong A có thể không cần; đó là mô hình khác. Xác định nơi access token được cấp, lưu và sử dụng trước khi chọn DSL.

## 22. HTTP 401/403/5xx và cách gỡ lỗi

| Hiện tượng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Downstream nhận request nhưng thiếu Authorization | WebClient chưa có filter hoặc không set client attribute | Kiểm tra bean, `clientRegistrationId`/`oauth2AuthorizedClient` |
| `invalid_client` khi xin token | Sai client ID/secret, method hoặc token-uri | Kiểm tra ClientRegistration và IdP config |
| `invalid_grant` khi refresh | Refresh token bị revoke/rotate/hết hạn | Loại authorized client và yêu cầu re-auth theo flow |
| 401 `invalid_token` ở B | Token expired/revoked/sai issuer/audience | Kiểm tra B validation, failure handler, lấy token đúng audience |
| 403 `insufficient_scope` ở B | Token thiếu scope, quyền nghiệp vụ | Sửa grant/scope hoặc policy, **không retry vô hạn** |
| Gặp 302 login redirect thay vì JSON | Authorization Code flow cần browser/login session | Không dùng `authorization_code` cho background job |
| Token user bị gửi tới webhook ngoài | Default client trên WebClient dùng chung, URL không allowlist | Tắt defaults, tách WebClient theo trusted API |
| 401 lặp đi lặp lại | Manager constructor chưa gắn failure handler, cache chứa token cũ | Gắn remover phù hợp với store hoặc sửa token policy |
| `no client registration` | Sai `registrationId` hoặc Boot properties không nạp | Kiểm tra registration ID chính xác |
| 401 sau logout/login mới | Authorized client/token cache stale, session đổi | Đồng bộ token store và SecurityContext |
| Chạy test offline thất bại vì gọi IdP | Test trực tiếp HTTP thật thay vì fake manager | Fake `ExchangeFunction`/mock authorized client |
| BlockingOperationError / event loop stalled | Dùng `block()` trong WebFlux | Trả Mono, cấu hình non-blocking auth/token client |
| JWT hợp lệ nhưng B chặn | Sai audience hoặc resource-level policy | Kiểm tra resource server logs an toàn (redact tokens) |
| Có token nhưng API trả dữ liệu tenant khác | B thiếu object-level auth | Đặt authorization gần DB, test IDOR/BOLA |

**Dò từng tầng:** WebClient bean đúng chưa → filter có trên builder chưa → request có attribute chọn client chưa → manager tìm/authorize thành công chưa → token còn hiệu lực và audience đúng chưa → outgoing Authorization header có thật chưa (chỉ trong test/fake) → B trả mã gì và WWW-Authenticate error code nào → failure handler có lưu/gỡ đúng store không.

Không bật full wiretap chứa access token trong production. Với test, chỉ dùng token giả; với thực tế, log registration ID/trace ID/status/error code đã được sanitise.

## 23. Test matrix mở rộng cho production

| Ca kiểm thử | Mục tiêu | Công cụ |
| --- | --- | --- |
| Registration explicit | Chỉ request được chọn client mới có Bearer | Fake manager + fake ExchangeFunction |
| No selection | Không tự gắn token khi defaults false | WebClient unit test |
| Explicit authorized client | Đúng token/client được gắn | WebClient unit test |
| Expired access token | Manager re-authorizes bằng provider hợp lệ | Fake token endpoint hoặc IdP sandbox |
| Missing refresh token | App yêu cầu login lại hoặc dùng grant phù hợp | Integration test |
| 401 invalid_token | Handler loại token không dùng được khi error code khớp | Fake Resource Server challenge |
| 403 insufficient_scope | Không retry vô hạn, fail đúng quyền | Fake Resource Server |
| Multiple users | Alice token không sang Bob | Session/store isolation integration |
| Multiple tenants | Token B audience và tenant claim đúng | Authorization tests B |
| Redirect to untrusted host | Không tiết lộ Authorization sang host lạ | HTTP client/SSRF test |
| Service job without user | Client credentials với stable machine principal | Service manager integration |
| Concurrent expiry | Không gây token endpoint refresh storm | Load/caching test |
| Token endpoint outage | Fail closed, timeout, không dùng expired token | Failure-injection test |
| Unauthorized browser route | oauth2Login redirect, API private | WebTestClient security test |
| Post with session cookie | CSRF còn hiệu lực | WebTestClient csrf() |

**Test fake header injection** không chứng minh token cryptographic validity. **Test Resource Server** không chứng minh authorization code login. Phải test từng trust boundary độc lập và có end-to-end test trên staging IdP/API thật khi đủ điều kiện.

## 24. Bài tập thực hành

### A. Thêm một WebClient an toàn khác
Tạo bean `publicWebClient` không OAuth2 filter để gọi `https://public.example`. Kiểm tra Authorization không bao giờ có trên request này, kể cả khi HTTP user đã OIDC login.

### B. Từ authorized client sang registrationId
Đổi cách gọi Google UserInfo từ `.attributes(oauth2AuthorizedClient(authorizedClient))` sang `.attributes(clientRegistrationId("google"))`. So sánh cách manager lấy principal, authorized client từ session và error khi chưa login.

### C. Hai registrations
Tạo một client cho Google UserInfo và một client cấp access token cho doanh nghiệp. Chứng minh token Google **không** được gửi tới API B và token B không được gửi tới Google; tách WebClient bean và host allowlist.

### D. Mất access token
Tạo fake authorized client đã hết hạn, fake token endpoint trả token mới, quan sát manager/provider reauthorization. Viết test trường hợp refresh token bị revoke, bảo đảm không dùng lại expired token vô hạn.

### E. Failure handler
Dựng fake downstream trả HTTP 401 cùng `WWW-Authenticate: Bearer error="invalid_token"`. Với manager constructor và remover phù hợp, kiểm tra authorized client bị xóa theo error code. Đối chiếu 403 `insufficient_scope` và tránh “refresh thì có scope mới” vô căn cứ.

### F. Background job
Dùng `client_credentials`, `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và principal `machine-reports`. Chứng minh không phụ thuộc browser session, không tự chọn user OAuth2 token.

### G. Quản lý token an toàn
Viết log sanitizer cho headers, token response và cookies; bảo đảm không có Bearer token thật ở Logback output, tracing hoặc exception message.

### H. SSRF/redirect
Thử đổi host API thông qua query parameter và chứng minh service từ chối. Kiểm tra behavior khi downstream redirect sang domain khác, tắt redirect unsafe và kiểm tra không lộ Authorization.

### I. Object-level authorization
Dù B nhận token đúng, thử truy cập report của tenant khác. Chứng minh B tự kiểm tra owner/tenant/action; WebClient filter không thay BOLA policy.

### J. CSRF boundary
Thêm POST vào ứng dụng browser OIDC và kiểm tra thiếu CSRF token bị 403. Giải thích tại sao A gọi B bằng Bearer không cho phép tắt CSRF trên browser–A session endpoint.

## 25. Checklist hoàn thành

- [ ] Phân biệt ClientRegistration, OAuth2AuthorizedClient, AuthorizedClientManager, repository/service và WebClient filter.
- [ ] Biết đúng class reactive `ServerOAuth2AuthorizedClientExchangeFilterFunction`, không dùng Servlet variant.
- [ ] WebClient được cấu hình `.filter(oauth)` và base URL trusted.
- [ ] Chọn client từng request qua `oauth2AuthorizedClient(...)` hoặc `clientRegistrationId(...)`.
- [ ] Không bật default OAuth2 token cho WebClient dùng nhiều destinations.
- [ ] Biết hai constructor có failure handler behavior khác nhau.
- [ ] Nhận biết 401 invalid_token khác 403 insufficient_scope.
- [ ] Có test thực tế trên fake ExchangeFunction chứng minh Authorization header chính xác.
- [ ] Không dùng ID Token thay access token hoặc gửi token sai audience.
- [ ] Biết authorization_code user delegation khác client_credentials machine.
- [ ] Biết manager cần grant provider và persistence/refresh policy.
- [ ] Không để nested subscribe, block event loop hoặc HTTP retries không idempotent.
- [ ] Giữ CSRF trên browser session endpoints và phân biệt CORS.
- [ ] Có chính sách token redaction, TLS, SSRF prevention, tenant authorization và secret rotation.
- [ ] Xác nhận frontend/inbound auth không tự tạo outbound token nếu chưa cấu hình OAuth2 Client.

## 26. Câu hỏi tự kiểm tra

1. WebClient bình thường có tự gắn token chỉ vì user đã OIDC login tại Spring Security không?
2. `OAuth2AuthorizedClient` có dữ liệu nào khác `ClientRegistration`?
3. Khi nào nên dùng `@RegisteredOAuth2AuthorizedClient` và `oauth2AuthorizedClient(...)`?
4. Ưu/nhược của `clientRegistrationId(...)` so với authorized client explicit là gì?
5. Vì sao filter có tên `ServerOAuth2AuthorizedClientExchangeFilterFunction` dù được dùng trong WebClient outbound?
6. Constructor nào tự cấu hình RemoveAuthorizedClient failure handler, constructor nào cần đặt thủ công?
7. Vì sao `setDefaultOAuth2AuthorizedClient(true)` nguy hiểm trên WebClient dùng chung?
8. Khi access token hết hạn nhưng không có refresh token, client_credentials xử lý khác authorization_code ra sao?
9. Vì sao access token của Google UserInfo không được gửi tới một reports API của doanh nghiệp?
10. Nếu A chỉ đóng vai Resource Server nhận Bearer inbound, có tự có authorized client outbound không?
11. Khi B trả 403 insufficient_scope, tại sao xóa cache và xin lại token không đủ giải quyết?
12. Trong job không browser, manager và principal nào phù hợp?
13. Tại sao cần WebClient fake ExchangeFunction để test outbound token mà không gọi IdP thật?
14. Vì sao CORS không liên quan đến WebClient server-side outbound như browser fetch?
15. Nếu một POST được gửi thành công nhưng response timeout, tại sao không retry vô điều kiện?

## 27. Tài liệu chính thức

- [Spring Security — OAuth2 Client in Reactive Environments](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/index.html): cấu hình OAuth2 Client, grant providers và WebClient.
- [Spring Security — Authorized Client Features for WebClient](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html): filter, explicit authorized client, registration ID và default-token cảnh báo.
- [Spring Security — Core Interfaces / Classes](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html): ClientRegistration, authorized client manager, repositories, token persistence.
- [Spring Security — ServerOAuth2AuthorizedClientExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html): constructor behavior, failure handling, request attributes.
- [Spring Security — OAuth2 Login WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html): Authorization Code login, OIDC ClientRegistration và WebSession.
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html): client_credentials, refresh token và grant providers.
- [Spring Security — Testing OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html): `mockOidcLogin` cho test HTTP auth.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): ExchangeFilterFunction, reactive response handling và filters.
- [OAuth 2.0 — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, client credentials và OAuth2 Access Tokens.
- [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707): lựa chọn resource/audience cho tokens.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): client authentication, redirect/token risks và kiến trúc an toàn.

**Kết luận:** `ServerOAuth2AuthorizedClientExchangeFilterFunction` giúp `WebClient` dùng `OAuth2AuthorizedClient` để gửi **Bearer access token** mà không hardcode token. Nhưng việc token được cấp cho ai, grant nào, lưu ở đâu, refresh ra sao, xử lý 401/403 thế nào và gửi tới **đúng audience** vẫn là trách nhiệm kiến trúc ứng dụng. Hãy chọn authorized client **tường minh cho mỗi outbound request**, tách WebClient theo trusted API, dùng manager/service phù hợp với user flow hoặc machine flow, và kiểm thử cả nhánh **có** lẫn **không có** Authorization header trước khi triển khai với provider thật.