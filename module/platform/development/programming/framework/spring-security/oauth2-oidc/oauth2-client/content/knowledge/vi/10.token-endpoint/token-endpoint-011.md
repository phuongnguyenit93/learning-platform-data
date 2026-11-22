# 10.11. Tùy chỉnh HTTP client, timeout, TLS và kết nối proxy

## 1. Bài toán: một OAuth2/OIDC Client phải kết nối ra ngoài

Trong module **Spring Security OAuth 2.0 OIDC Client**, sau khi người dùng đăng nhập và Authorization Server (AS) chuyển trình duyệt về callback cùng một authorization code, ứng dụng phải gọi **Token Endpoint** để đổi code lấy token. Ngoài lần trao đổi mã ban đầu, ứng dụng có thể gọi cùng endpoint để làm mới token bằng refresh token hoặc lấy access token qua grant `client_credentials`.

Ví dụ request cho Authorization Code Grant của confidential client:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&code=CODE_VALUE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&code_verifier=ORIGINAL_PKCE_VERIFIER
~~~

Đây là **HTTP request do backend/client gửi đến AS**, khác với các redirect thông qua trình duyệt. Trong môi trường thật, nó có thể cần:

- Kết nối đi qua **proxy** của doanh nghiệp.
- Thời gian chờ có giới hạn để login không treo lâu khi mạng hoặc AS gặp lỗi.
- **TLS truststore** chứa CA của provider hoặc CA được tổ chức phê duyệt.
- **Client certificate** khi AS yêu cầu mutual TLS (mTLS).
- Quy tắc connection pooling, proxy authentication, log bảo mật và error handling.
- Cơ chế khác nhau cho Servlet (`RestClient`) và WebFlux (`WebClient`).

**Mục tiêu:** thay đổi cách Spring Security **gửi HTTP request tới Token Endpoint** mà vẫn để framework xử lý đúng client authentication, PKCE, form body, token response, OAuth2 errors và OIDC token validation.

Ví dụ xuyên suốt:

| Thành phần | Giá trị minh họa |
|---|---|
| Web application | `https://app.example.com` |
| Issuer của OpenID Provider | `https://id.example.com` |
| Token Endpoint | `https://id.example.com/oauth2/token` |
| OAuth2 registration ID | `demo` |
| Proxy tùy chọn | `proxy.corp.example:3128` |
| Connect timeout mẫu | 3 giây |
| Response timeout mẫu | 10 giây |
| TLS handshake timeout mẫu | 5 giây |

Các host và timeout chỉ phục vụ minh họa; hệ thống thật phải điều chỉnh theo network topology, độ trễ thực tế, SLA của IdP và khả năng chịu tải.

## 2. Phân biệt kết nối Token Endpoint với các kết nối OAuth2/OIDC khác

Một ứng dụng OIDC thường sử dụng **nhiều HTTP client hoặc nhiều lớp HTTP transport**:

| Kết nối | Mục đích | Bên thực hiện |
|---|---|---|
| Authorization Endpoint | Xác thực/consent và cấp authorization code | **Trình duyệt** được redirect |
| Token Endpoint | Đổi authorization code, refresh token, client credentials | **Backend OAuth2 Client** |
| OIDC Discovery | Tải metadata từ `/.well-known/openid-configuration` | Thành phần discovery khi tạo registration |
| JWKS Endpoint | Lấy public keys để xác minh ID Token | JWT decoder/JWK source |
| UserInfo Endpoint | Lấy thông tin người dùng theo OIDC | OIDC user service |
| Resource Server API | Gửi access token để lấy tài nguyên | REST client của ứng dụng |
| Logout Endpoint | Đăng xuất liên thông nếu provider hỗ trợ | Trình duyệt và/hoặc thành phần logout |

**Tùy chỉnh HTTP client của Token Endpoint không tự động thay đổi HTTP client dùng cho Discovery, JWKS, UserInfo hoặc API.** Đây là điểm rất quan trọng khi triển khai sau firewall/proxy: token exchange có thể thành công nhưng login vẫn thất bại vì không tải được JWKS để kiểm tra ID Token.

Sơ đồ luồng:

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant App as Spring Security OAuth2 Client
    participant Proxy as Proxy doanh nghiệp
    participant AS as Authorization Server
    participant API as Resource Server
    Browser->>App: Bắt đầu đăng nhập
    App-->>Browser: Redirect đến Authorization Endpoint
    Browser->>AS: Đăng nhập/consent
    AS-->>Browser: Redirect callback?code=...&state=...
    Browser->>App: Callback authorization code
    Note over App: Kiểm tra state, lấy PKCE verifier
    App->>Proxy: HTTP Token Request (timeout/TLS/proxy)
    Proxy->>AS: Kết nối tới Token Endpoint
    AS-->>Proxy: Token response hoặc lỗi OAuth2
    Proxy-->>App: Chuyển phản hồi
    Note over App: Xác minh ID Token nếu OIDC
    App->>API: Access token (kết nối riêng)
    API-->>App: Dữ liệu
    App-->>Browser: Trang ứng dụng
~~~

Nếu kết nối trực tiếp, bỏ thành phần proxy khỏi sơ đồ. Trong HTTPS qua HTTP proxy dạng CONNECT, ứng dụng vẫn phải kiểm tra TLS của host Token Endpoint.

## 3. Điểm mở rộng đúng của Spring Security

Spring Security có các token response clients riêng cho Servlet và WebFlux.

| Vai trò | Servlet/MVC | WebFlux/reactive |
|---|---|---|
| Security configuration | `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| Authorization Code token response client | `RestClientAuthorizationCodeTokenResponseClient` | `WebClientReactiveAuthorizationCodeTokenResponseClient` |
| Contract | `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` | `ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` |
| HTTP client | `RestClient` | `WebClient` |
| HTTP transport adapter | `ClientHttpRequestFactory` | `ClientHttpConnector` |
| Một implementation transport | `JdkClientHttpRequestFactory` | `ReactorClientHttpConnector` |
| Cách gắn client | `setRestClient(...)` | `setWebClient(...)` |

**Phiên bản cần lưu ý:** `RestClientAuthorizationCodeTokenResponseClient` xuất hiện từ dòng **Spring Security 6.4**. Ở các phiên bản cũ, nhiều dự án Servlet dùng `DefaultAuthorizationCodeTokenResponseClient` và `RestTemplate`. Không lấy một API của 6.4 rồi cho rằng nó sẽ có ở Spring Security 6.2/6.3.

Tất cả ví dụ Servlet chính bên dưới hướng đến Spring Security **6.4+** với Spring Framework hỗ trợ `RestClient`. Phần phiên bản cũ được trình bày riêng. Ví dụ WebFlux sử dụng Reactor Netty; nếu chọn transport khác, những API cấu hình timeout/proxy/TLS có thể khác.

## 4. Cần cấu hình những loại timeout nào?

Một request `POST /token` có nhiều giai đoạn:

~~~text
Token request bắt đầu
    |
    +-- DNS lookup / chọn proxy
    |
    +-- Chờ connection rảnh từ pool
    |
    +-- TCP connection
    |
    +-- HTTP proxy CONNECT (nếu có)
    |
    +-- TLS handshake + xác minh chứng chỉ
    |
    +-- Gửi form body (code, verifier, client authentication)
    |
    +-- AS xử lý giao dịch cấp token
    |
    +-- Nhận response headers/body
    |
    +-- Parse OAuth2 token response
    |
    +-- OIDC ID Token validation, nếu áp dụng
    v
Hoàn thành
~~~

### 4.1. Connect timeout

Giới hạn thời gian để thiết lập kết nối TCP tới peer. Với proxy, peer ban đầu thường là proxy; có thể cần thêm giới hạn cho việc proxy tạo tunnel hoặc thời gian TLS handshake.

Nếu không giới hạn, luồng login có thể treo khi firewall drop packet, mạng đứt hoặc route không khả dụng.

### 4.2. Response/read timeout

Giới hạn thời gian chờ phản hồi sau khi kết nối được thiết lập. Cần đọc đúng ngữ nghĩa implementation:

- JDK HTTP client được Spring bọc bằng `JdkClientHttpRequestFactory` hỗ trợ `setReadTimeout(Duration)`, đặt request timeout theo HTTP implementation của nó.
- Apache HttpComponents có `responseTimeout` và các tham số connection pool/tunnel riêng.
- Reactor Netty hỗ trợ `HttpClient.responseTimeout(Duration)`.

**Response timeout không nhất thiết bao phủ DNS, pool acquire, TLS handshake và toàn bộ logic ứng dụng.** Tên cụ thể và cách tính thời gian phụ thuộc transport.

### 4.3. TLS handshake timeout

TLS xảy ra sau TCP connect và có thể chậm/không hoàn tất ngay cả khi kết nối TCP thành công. Reactor Netty cung cấp `handshakeTimeout(...)`. Với JDK/Apache HTTP client, cấu hình timeout handshake tùy implementation và phiên bản; không giả định `connectTimeout` luôn bao phủ pha này.

### 4.4. Connection pool acquire timeout

Khi pool đầy, request phải chờ một connection rảnh. Giới hạn này khác với connect timeout. Nếu pool chờ quá lâu, nhiều người dùng có thể bị treo login/refresh đồng thời.

### 4.5. Overall deadline

Một request có thể lần lượt đi qua DNS, proxy, TLS và response. Do đó, dự án có thể thêm deadline tổng thể phù hợp với UX hoặc SLA, nhưng phải tránh hủy quá sớm các giao dịch cấp token hợp lệ.

| Timeout | Giảm nguy cơ | Cần lưu ý |
|---|---|---|
| Connect | TCP connection treo | Proxy/DNS có thể có timeout riêng |
| Proxy CONNECT | Proxy không tạo được tunnel | Chỉ áp dụng khi dùng proxy |
| TLS handshake | TLS không hoàn tất | Không sửa bằng cách tắt xác minh chứng chỉ |
| Pool acquire | Chờ connection quá lâu | Cần sizing pool và giới hạn queue |
| Response/read | AS chậm không trả phản hồi | Không phải overall deadline |
| Overall | Tổng thời gian vượt giới hạn UX | Có thể hủy khi AS đã cấp token |

## 5. Đăng ký client ở Spring Boot không tự cấu hình transport

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: example-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          example-idp:
            issuer-uri: https://id.example.com
~~~

Cấu hình này cho Spring Security biết **client registration, grant, scope và provider**. Nó không tự quy định timeout/proxy/truststore riêng cho `POST /token`.

Có thể thêm nhóm property do ứng dụng tự định nghĩa:

~~~yaml
app:
  oidc:
    token-http:
      connect-timeout: 3s
      response-timeout: 10s
      proxy-enabled: false
      proxy-host: proxy.corp.example
      proxy-port: 3128
~~~

`app.oidc.token-http.*` là ví dụ **custom application properties**. Spring Security không tự bind chúng vào token response client. Cần dùng `@ConfigurationProperties` hoặc cơ chế injection rồi truyền chúng vào HTTP client do ứng dụng tạo. Tránh đặt client secret, proxy password hoặc keystore password dưới dạng plain text trong repository.

## 6. Servlet: RestClient dành riêng cho Token Endpoint

Ở Servlet stack hiện đại, thành phần `RestClientAuthorizationCodeTokenResponseClient` chịu trách nhiệm xây token request và nhận OAuth2 token response. Nó sử dụng `RestClient` để thực hiện HTTP.

Khi thay `RestClient` mặc định, phải giữ:

- `FormHttpMessageConverter` để gửi request body `application/x-www-form-urlencoded`.
- `OAuth2AccessTokenResponseHttpMessageConverter` để đọc token response.
- `OAuth2ErrorResponseErrorHandler` để xử lý OAuth2 error response, chẳng hạn `invalid_grant`.

### 6.1. Ví dụ timeout với JDK HttpClient

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.web.client.RestClient;

@Configuration
public class TokenTransportConfiguration {

    @Bean
    RestClient tokenRestClient() {
        HttpClient jdkClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(10));

        return RestClient.builder()
            .requestFactory(factory)
            .messageConverters(converters -> {
                converters.clear();
                converters.add(new FormHttpMessageConverter());
                converters.add(
                    new OAuth2AccessTokenResponseHttpMessageConverter()
                );
            })
            .defaultStatusHandler(new OAuth2ErrorResponseErrorHandler())
            .build();
    }
}
~~~

Phân tích:

1. `HttpClient.newBuilder().connectTimeout(...)` đặt connect timeout.
2. `followRedirects(NEVER)` tránh tự đi theo redirect tới một host khác với request chứa bí mật; response 3xx cần được nhận diện và xử lý theo giao thức.
3. `JdkClientHttpRequestFactory` là cầu nối giữa Spring `RestClient` và JDK HTTP client.
4. `setReadTimeout(...)` đặt giới hạn chờ ở mức request.
5. Bộ converters bảo đảm token request/response vẫn được diễn giải theo OAuth2.
6. `OAuth2ErrorResponseErrorHandler` giữ thông tin lỗi OAuth2 theo cách framework mong đợi.

Ví dụ dùng HTTP client JDK được hỗ trợ trong các dòng Spring Framework hiện đại; nếu dự án cũ hơn hoặc dùng Apache HttpClient, các API timeout khác nhau. Những con số 3s/10s chỉ dùng làm điểm xuất phát, phải điều chỉnh cho môi trường thực tế.

### 6.2. Gắn RestClient vào token response client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.web.client.RestClient;

@Configuration
public class AuthorizationCodeTokenConfiguration {

    @Bean
    OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            authorizationCodeTokenResponseClient(RestClient tokenRestClient) {

        RestClientAuthorizationCodeTokenResponseClient client =
            new RestClientAuthorizationCodeTokenResponseClient();
        client.setRestClient(tokenRestClient);

        return client;
    }
}
~~~

Client này vẫn tự xây token request từ grant request, lấy `tokenUri` từ `ClientRegistration`, gửi `code`, `redirect_uri`, `code_verifier` nếu có, và dùng đúng client authentication method. HTTP transport được thay đổi mà không cần tự viết logic POST token request.

### 6.3. Kết nối với OAuth2 Login trong HttpSecurity

Với Servlet, có thể chỉ định token response client trong DSL:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
                    authorizationCodeTokenResponseClient)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(
                        authorizationCodeTokenResponseClient)
                )
            )
            .oauth2Client(client -> client
                .authorizationCodeGrant(grant -> grant
                    .accessTokenResponseClient(
                        authorizationCodeTokenResponseClient)
                )
            );

        return http.build();
    }
}
~~~

`oauth2Login().tokenEndpoint()` áp dụng cho code exchange khi người dùng đăng nhập. `oauth2Client().authorizationCodeGrant()` áp dụng cho phần OAuth2 Client authorization code. Với một số dòng Spring Security hiện đại, có thể công bố bean token response client và để framework phát hiện theo generic type; gắn trực tiếp giúp thể hiện rõ cách kết nối các thành phần, nhất là khi ứng dụng có cấu hình tùy chỉnh.

Nếu dự án đã có bean `SecurityFilterChain`, thêm đoạn cấu hình vào chain đang dùng. Không tạo nhiều chain trùng matcher cho toàn bộ đường dẫn khi không có chủ đích.

## 7. Servlet: cấu hình proxy qua JDK HttpClient

Nếu backend phải đi qua corporate proxy để tới Token Endpoint:

~~~java
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient jdkClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .proxy(ProxySelector.of(
        new InetSocketAddress("proxy.corp.example", 3128)))
    .build();
~~~

Truyền `jdkClient` này vào `JdkClientHttpRequestFactory`, rồi xây `RestClient` **với đầy đủ form converter, token response converter và error handler** giống mục 6.1. Mỗi ví dụ chỉ làm nổi bật phần thay đổi; khi dùng thật phải kết hợp trong cùng cấu hình hoàn chỉnh.

### 7.1. Proxy tunnel HTTPS hoạt động thế nào?

Với HTTP proxy dạng CONNECT, client thường yêu cầu mở tunnel:

~~~http
CONNECT id.example.com:443 HTTP/1.1
Host: id.example.com:443
~~~

Sau khi proxy cho phép, client thương lượng TLS tới host đích qua tunnel. Nếu proxy không can thiệp TLS, nội dung form body/response vẫn được mã hóa giữa client và AS. Nếu proxy thực hiện **TLS inspection**, nó có thể tạo chứng chỉ thay thế được ký bởi corporate CA và nhìn thấy nội dung HTTPS đã giải mã; đó là ranh giới tin cậy cần được tổ chức phê duyệt.

Vì vậy ứng dụng phải dùng truststore hợp lệ; **không tắt hostname verification hoặc chấp nhận mọi chứng chỉ** để đi qua proxy.

### 7.2. Proxy authentication khác với OAuth2 client authentication

Proxy có thể yêu cầu `Proxy-Authorization`, trong khi AS có thể yêu cầu `Authorization: Basic ...` hoặc client assertion.

| Bí mật | Đối tượng sử dụng | Không nên đưa tới |
|---|---|---|
| Proxy password | Corporate proxy | Token Endpoint như client secret |
| OAuth2 client secret | Authorization Server | Proxy credentials hoặc browser |
| PKCE `code_verifier` | Token Endpoint, theo từng code | Authorization request/front channel |
| Refresh token | Token Endpoint khi refresh | URL, log, browser công khai |

JDK `HttpClient.Builder.authenticator(...)` hỗ trợ các kịch bản authentication tương ứng với implementation; với HTTP CONNECT và proxy policy cụ thể, cần xác nhận rằng phương thức authentication được JDK và proxy hỗ trợ. Quản lý proxy password qua secrets, không gắn vào URL hoặc log.

### 7.3. No-proxy và routing nhiều provider

Một ứng dụng có thể phải truy cập IdP nội bộ trực tiếp nhưng IdP đối tác qua proxy:

~~~text
id.internal.example       -> direct
login.partner.example     -> proxy.corp.example:3128
api.internal.example      -> direct
~~~

Khi đó cần `ProxySelector` có quy tắc route rõ ràng hoặc các HTTP client riêng theo nhóm provider. Không dựa vào giả định rằng biến môi trường `HTTP_PROXY` hoặc `HTTPS_PROXY` luôn được mọi Java HTTP library tự động áp dụng.

Với một HTTP client dùng chung, đặc biệt lưu ý các request chứa credentials: route phải đưa chúng đến **đúng endpoint tin cậy**, không gửi sang host tùy ý từ dữ liệu người dùng.

## 8. TLS: truststore và xác minh chứng chỉ máy chủ

TLS bảo vệ kết nối Token Endpoint chứa authorization code, client secret, refresh token và token response. Với chứng chỉ public CA, JVM/JDK thường có truststore mặc định phù hợp. Với private CA hoặc corporate TLS inspection, ứng dụng có thể cần một truststore được quản trị.

### 8.1. Những khái niệm cần phân biệt

| Khái niệm | Công dụng |
|---|---|
| Server certificate | Chứng minh danh tính host HTTPS |
| Certificate chain | Chuỗi chứng chỉ dẫn tới trust anchor |
| Truststore | Tập CA/certificate mà client tin cậy |
| TrustManager | Thực hiện kiểm tra trust chain trong Java |
| Hostname verification | Kiểm tra chứng chỉ hợp lệ cho hostname trong Token Endpoint URL |
| Keystore + KeyManager | Lưu/trình client certificate và private key khi mTLS |
| `SSLContext` | Cấu hình TLS được HTTP transport sử dụng |

Lỗi điển hình:

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
~~~

Nguyên nhân có thể là private CA chưa được tin, chain máy chủ thiếu intermediate, chứng chỉ hết hạn hoặc proxy TLS inspection thay chứng chỉ. Cách giải quyết là sửa certificate chain/trust anchors phù hợp, **không làm trust manager bỏ qua mọi chứng chỉ**.

### 8.2. Ví dụ tạo SSLContext từ PKCS#12 truststore

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TokenTlsSupport {

    private TokenTlsSupport() {
    }

    public static SSLContext sslContext(
            Path trustStorePath, char[] trustStorePassword)
            throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream stream =
                 Files.newInputStream(trustStorePath)) {
            trustStore.load(stream, trustStorePassword);
        }

        TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            null,
            trustManagerFactory.getTrustManagers(),
            new SecureRandom()
        );
        return sslContext;
    }
}
~~~

Gắn vào JDK HTTP client:

~~~java
SSLContext sslContext = TokenTlsSupport.sslContext(
    Path.of("/secure/config/oidc-truststore.p12"),
    trustStorePassword
);

HttpClient jdkClient = HttpClient.newBuilder()
    .sslContext(sslContext)
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();
~~~

`trustStorePassword` được lấy từ secret manager/biến môi trường, không hardcode. Việc lấy trust anchors từ truststore custom **có thể thay thế** tập CA mặc định, vì thế phải đảm bảo store chứa đầy đủ các CA cần thiết. Không tự tạo trust manager tin mọi certificate chỉ vì CA doanh nghiệp chưa được cài.

### 8.3. Hostname verification bắt buộc giữ nguyên

Dù truststore có chứa CA đúng, client vẫn phải xác minh chứng chỉ dành cho **hostname trong token URI**. Nếu URL là `https://id.example.com/oauth2/token` mà chứng chỉ chỉ hợp lệ cho host khác, kết nối phải bị từ chối.

Không sửa bằng cách tắt hostname verification. Kiểm tra URL provider công bố, DNS, Server Name Indication (SNI), subject alternative names (SANs) và cấu hình reverse proxy/IdP.

### 8.4. Mutual TLS (mTLS) cần client keystore

Nếu Authorization Server yêu cầu mTLS client authentication, ngoài truststore, client cần certificate/private key riêng:

~~~text
client-keystore.p12
  -> KeyStore.load(...)
  -> KeyManagerFactory.init(...)
  -> SSLContext.init(keyManagers, trustManagers, random)
  -> HttpClient (Token Endpoint)
~~~

mTLS không tự thay `client_secret_basic` hoặc `private_key_jwt` trừ khi registration và chính sách AS nói như vậy. Với token bị ràng buộc chứng chỉ, resource server còn có yêu cầu riêng về chứng minh người gửi. Đừng nhầm việc TLS kết nối thành công với việc OAuth2 client authentication chắc chắn thành công.

### 8.5. TLS và secret rotation

Thay đổi CA, certificate hoặc client key có thể đòi hỏi tái tạo `SSLContext` và HTTP client, hoặc restart ứng dụng theo cấu hình triển khai. Không mặc định transport sẽ tự reload file truststore. Secrets cần được bảo vệ trong filesystem, container, CI/CD và observability.

## 9. Servlet với thư viện cũ: DefaultAuthorizationCodeTokenResponseClient

Một dự án Spring Security trước 6.4 có thể dùng:

- `DefaultAuthorizationCodeTokenResponseClient`.
- `RestTemplate` / `RestOperations`.
- `setRestOperations(...)` để thay HTTP client.

Ví dụ theo hướng legacy:

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.oauth2.client.endpoint.DefaultAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.web.client.RestTemplate;

SimpleClientHttpRequestFactory factory =
    new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(Duration.ofSeconds(3));
factory.setReadTimeout(Duration.ofSeconds(10));

RestTemplate restTemplate = new RestTemplate(factory);
restTemplate.setMessageConverters(List.of(
    new FormHttpMessageConverter(),
    new OAuth2AccessTokenResponseHttpMessageConverter()
));
restTemplate.setErrorHandler(new OAuth2ErrorResponseErrorHandler());

DefaultAuthorizationCodeTokenResponseClient client =
    new DefaultAuthorizationCodeTokenResponseClient();
client.setRestOperations(restTemplate);
~~~

Đoạn này minh họa API cho các **dòng phiên bản còn có class legacy**. Các phiên bản mới có thể deprecate hoặc bỏ class cũ; khi đó dùng `RestClientAuthorizationCodeTokenResponseClient` theo mục 6. Không mang code legacy sang Spring Security 7.x nếu class không còn tồn tại.

Tương tự, nếu dùng Apache HttpComponents thay JDK client, các API connection pool/proxy/TLS timeout cần được cấu hình ở Apache client và adapter `HttpComponentsClientHttpRequestFactory`. Không suy rằng mọi implementation đều có `setConnectTimeout` với cùng ngữ nghĩa; một số phương thức đã thay đổi/deprecate qua các dòng Spring Framework.

## 10. WebFlux: WebClientReactiveAuthorizationCodeTokenResponseClient

Trong ứng dụng **Spring Security WebFlux**, token exchange dựa trên `WebClientReactiveAuthorizationCodeTokenResponseClient`, nhận một `WebClient` cấu hình qua `setWebClient(...)`.

Nếu dùng Reactor Netty, `HttpClient` có thể cấu hình:

- TCP connect timeout;
- Response timeout;
- TLS handshake timeout;
- HTTP proxy và thời gian kết nối proxy;
- Connection pool/connection acquire timeout.

### 10.1. Tạo WebClient với timeout và proxy

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.transport.ProxyProvider;

@Configuration
public class ReactiveTokenTransportConfiguration {

    @Bean
    WebClient tokenWebClient() {
        HttpClient netty = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(10))
            .secure(ssl -> ssl
                .handshakeTimeout(Duration.ofSeconds(5)))
            .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.corp.example")
                .port(3128)
                .connectTimeoutMillis(5_000));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(netty))
            .build();
    }
}
~~~

Giải thích:

- `CONNECT_TIMEOUT_MILLIS` thuộc kết nối TCP.
- `responseTimeout` giới hạn chờ phản hồi theo Reactor Netty.
- `handshakeTimeout` giới hạn thời gian TLS handshake.
- `proxy(...)` thiết lập HTTP proxy. **Bỏ khối proxy** trong môi trường đi trực tiếp.
- `ReactorClientHttpConnector` kết nối HTTP transport với Spring `WebClient`.

Cấu hình proxy có thể mở rộng với `nonProxyHosts(...)`, authentication và chính sách route theo provider. Khi dùng HTTPS qua proxy, Reactor Netty hỗ trợ HTTP CONNECT; proxy phải có khả năng tạo tunnel theo yêu cầu của mạng.

### 10.2. Gắn WebClient vào reactive token response client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveTokenClientConfiguration {

    @Bean
    ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            authorizationCodeTokenResponseClient(WebClient tokenWebClient) {

        WebClientReactiveAuthorizationCodeTokenResponseClient client =
            new WebClientReactiveAuthorizationCodeTokenResponseClient();
        client.setWebClient(tokenWebClient);
        return client;
    }
}
~~~

Với Spring Security WebFlux phiên bản hỗ trợ tự động nhận bean token response client theo generic grant type, cách này có thể được các thành phần OAuth2 Client sử dụng. Nếu ứng dụng tự tạo reactive authentication manager hoặc `ReactiveOAuth2AuthorizedClientManager`, phải bảo đảm chúng tham chiếu đúng token response client.

Không tự viết `webClient.post()` để đổi code chỉ vì cần proxy. `WebClientReactiveAuthorizationCodeTokenResponseClient` vẫn phải quản lý form request, PKCE verifier, parsing và OAuth2 errors.

### 10.3. Reactive pipeline không được block event loop

Với WebFlux, kết nối Token Endpoint là I/O trong reactive pipeline. Tránh gọi `.block()` trong event loop hoặc tạo một thread blocking thủ công cho mỗi lần login. Reactor Netty thực hiện bất đồng bộ; các timeout phải được cấu hình ở client/connector hoặc trên pipeline phù hợp.

Nếu phải dùng thư viện TLS/secret access blocking khi khởi tạo bean, thực hiện ở giai đoạn cấu hình phù hợp thay vì lặp lại I/O blocking theo mỗi token request.

## 11. WebFlux: refresh token và connection pool

Khi ứng dụng refresh access token, grant đó có thể sử dụng `WebClientReactiveRefreshTokenTokenResponseClient`. Đừng cho rằng tùy chỉnh riêng authorization code client cũng được áp dụng cho refresh token.

Ví dụ bean thêm vào một class `@Configuration`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenResponseClient(WebClient tokenWebClient) {

    WebClientReactiveRefreshTokenTokenResponseClient client =
        new WebClientReactiveRefreshTokenTokenResponseClient();
    client.setWebClient(tokenWebClient);
    return client;
}
~~~

Nếu framework/manager đang được tùy chỉnh, gắn bean refresh vào provider/manager tương ứng; đừng tạo hai bean cùng generic type mà không có cơ chế lựa chọn.

### 11.1. Connection pool trong Reactor Netty

Ví dụ tạo một pool giới hạn:

~~~java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

ConnectionProvider pool =
    ConnectionProvider.builder("oidc-token-pool")
        .maxConnections(40)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(30))
        .build();

HttpClient netty = HttpClient.create(pool)
    .responseTimeout(Duration.ofSeconds(10));
~~~

`maxConnections` là số kết nối tối đa, `pendingAcquireTimeout` là thời gian chờ lấy kết nối rảnh và `maxIdleTime` kiểm soát idle lifetime. Số 40 và các thời gian trên chỉ là ví dụ, phải căn theo tải của ứng dụng và giới hạn của AS/proxy.

Tạo pool một lần và quản lý vòng đời đóng/dispose khi ứng dụng dừng. Không tạo pool mới trong mỗi callback, mỗi lần refresh hoặc mỗi HTTP request.

### 11.2. TLS trust trong Reactor Netty

Nếu IdP dùng một corporate CA theo chính sách được duyệt, có thể cấu hình Netty `SslContext`:

~~~java
import java.io.File;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import reactor.netty.http.client.HttpClient;

SslContext tls = SslContextBuilder.forClient()
    .trustManager(new File("/secure/config/corp-root-ca.pem"))
    .build();

HttpClient netty = HttpClient.create()
    .secure(spec -> spec.sslContext(tls));
~~~

CA file phải đáng tin cậy và bảo vệ khỏi thay đổi trái phép. Chỉ định một CA riêng có thể ảnh hưởng đến tập CA được tin so với transport mặc định; phải chuẩn bị đúng trust chain. Không dùng `InsecureTrustManagerFactory` hay hostname-verification bypass. Với mTLS, còn cần key material và cấu hình client auth theo AS.

## 12. Refresh Token cũng gọi Token Endpoint nhưng cần policy riêng

Các grant có thể gửi POST tới cùng Token Endpoint nhưng khác lifecycle.

| Grant | Mục đích | Rủi ro khi tự động retry |
|---|---|---|
| `authorization_code` | Đổi code dùng một lần | Code có thể đã được tiêu thụ |
| `refresh_token` | Nhận access token mới | Refresh token có thể đã rotate |
| `client_credentials` | Lấy token cho service | Retry dồn dập có thể quá tải/rate limit |
| Token exchange / JWT bearer | Theo giao thức mở rộng | Phụ thuộc token assertions và chính sách AS |

Ví dụ Servlet Spring Security 6.4+ dùng chung `RestClient` cho refresh client:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.RestClientRefreshTokenTokenResponseClient;
import org.springframework.web.client.RestClient;

@Bean
OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenResponseClient(RestClient tokenRestClient) {

    RestClientRefreshTokenTokenResponseClient client =
        new RestClientRefreshTokenTokenResponseClient();
    client.setRestClient(tokenRestClient);
    return client;
}
~~~

Đây là một method thêm vào class cấu hình Spring, không phải file độc lập. Nếu dùng `OAuth2AuthorizedClientManager` tùy chỉnh, cần kết nối refresh grant provider với token client này theo API của phiên bản đang dùng.

### 12.1. Vì sao token request không nên retry mù quáng?

Giả sử:

~~~text
t=0s  Client POST /token với code K1
t=1s  AS xác thực và đánh dấu K1 đã sử dụng
t=2s  AS cấp token, bắt đầu trả response
t=3s  Proxy/network làm mất response
t=10s Client thấy response timeout
~~~

Client **không thể kết luận** AS chưa xử lý code. Retry `K1` nhiều lần dễ gặp `invalid_grant` vì code chỉ được dùng một lần. Với refresh token rotation, retry token cũ cũng có thể kích hoạt chính sách phát hiện reuse.

Vì vậy:

- Không gắn retry interceptor chung cho mọi `POST /token`.
- Phân biệt timeout kết nối trước khi gửi request và timeout sau khi AS có thể đã xử lý.
- Khi không xác định kết quả Authorization Code Grant, thường cần **khởi tạo authorization flow mới**.
- Nếu AS và client credentials grant cho phép retry, giới hạn số lần và dùng backoff phù hợp.
- Không cache token của một principal rồi trả cho principal khác làm fallback.

## 13. Tùy chỉnh protocol request khác với tùy chỉnh HTTP transport

Có hai tầng cấu hình:

| Tầng | Trách nhiệm | Ví dụ |
|---|---|---|
| **OAuth2 protocol** | Grant type, body form, client authentication, PKCE, token/error response | `OAuth2AccessTokenResponseClient` |
| **HTTP transport** | DNS, connect/read timeout, TLS, proxy, pool | `RestClient`/`WebClient` và factory/connector |

Nếu chỉ cần thay proxy hoặc timeout, hãy thay HTTP transport; **không tự tạo lại toàn bộ token request**. Nếu provider thực sự yêu cầu một tham số mở rộng, dùng token client customization API dành cho headers/parameters theo tài liệu Spring Security.

Một lỗi dễ gặp khi tự thay `RestClient` là bỏ:

~~~java
new FormHttpMessageConverter()
new OAuth2AccessTokenResponseHttpMessageConverter()
new OAuth2ErrorResponseErrorHandler()
~~~

Khi đó ứng dụng có thể không gửi được form body, không đọc được access token response hoặc đánh mất chi tiết lỗi OAuth2. Đây là lỗi cấu hình HTTP client, không phải lỗi của authorization code.

### 13.1. Một OAuth2 error response hợp lệ

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code expired or already used"
}
~~~

Đây là phản hồi **có cấu trúc OAuth2** từ AS, không phải lỗi TCP/TLS. Token response client cần đọc error và truyền lại thông tin đã lọc phù hợp cho ứng dụng, thay vì coi đó chỉ là body JSON bất kỳ.

Nếu provider trả error không chuẩn, việc tùy chỉnh converter có thể cần thiết nhưng phải thực hiện cẩn thận, không làm mất các kiểm tra giao thức.

## 14. Bảo vệ credential trong proxy, TLS và logging

Một token request có thể chứa:

~~~text
Authorization: Basic <client_id:client_secret>
code=<authorization-code>
code_verifier=<pkce-verifier>
refresh_token=<refresh-token>
client_assertion=<signed-assertion>
~~~

Token response có thể chứa `access_token`, `id_token` và `refresh_token`. Dữ liệu này **không được ghi vào log** của ứng dụng, HTTP interceptor, trace span, APM hoặc proxy nếu không có biện pháp bảo vệ đặc biệt.

### 14.1. Logging an toàn nên ghi gì?

| Thông tin | Có nên ghi? | Ví dụ |
|---|---|---|
| Registration ID đã được duyệt | Có thể | `demo` |
| Loại grant | Có | `authorization_code`, `refresh_token` |
| Nhóm endpoint | Có | `token` |
| Thời gian HTTP | Có | `elapsed_ms=153` |
| HTTP status | Có | `200`, `400`, `502` |
| OAuth2 error code đã lọc | Có | `invalid_client`, `invalid_grant` |
| Authorization code | **Không** | Dữ liệu dùng một lần |
| Client secret/client assertion | **Không** | Credential |
| PKCE verifier | **Không** | Bí mật theo giao dịch |
| Access/refresh/ID token | **Không** | Credential và dữ liệu xác thực |
| Proxy password | **Không** | Credential proxy |

Nếu cần correlation, dùng trace ID ngẫu nhiên không chứa code/token. Không log nguyên `Authorization` và `Proxy-Authorization` headers. Không bật HTTP wiretap/body logging vô điều kiện trên production khi đang xử lý Token Endpoint.

### 14.2. TLS inspection cần được quản trị

Nếu doanh nghiệp yêu cầu proxy TLS inspection, truststore phải chứa đúng corporate CA do tổ chức phê duyệt. Cần hiểu rằng proxy có thể quan sát nội dung đã giải mã; chính sách bảo mật/đường ra mạng phải xử lý dữ liệu OAuth2 credential/token phù hợp.

Không cài CA nhận từ một nguồn chưa tin cậy. Không cấu hình global trust-all để chỉ một provider hoạt động.

## 15. Không nhầm transport lỗi với OAuth2 protocol lỗi

| Triệu chứng | Nhóm nguyên nhân | Nơi cần xem |
|---|---|---|
| `ConnectException` / connect timeout | Firewall, route, proxy không tới được | DNS/network/proxy |
| `UnknownHostException` | DNS không phân giải được | DNS trong container/VPC |
| `SSLHandshakeException` / PKIX | CA, certificate chain, TLS inspection | Truststore, server certificate |
| Hostname mismatch | Chứng chỉ không cấp cho đúng host | Token URI, SAN và SNI |
| HTTP `407` | Proxy yêu cầu xác thực | Proxy credential/method |
| HTTP `502`/`503`/`504` | Proxy/gateway/AS upstream lỗi | Proxy/AS logs |
| Response timeout | AS xử lý chậm hoặc mạng/proxy không trả | Latency, response timeout |
| `invalid_client` | Client auth method/secret/assertion sai | ClientRegistration, AS policy |
| `invalid_grant` | Code đã dùng/hết hạn, PKCE/redirect URI sai, refresh token không hợp lệ | Grant lifecycle |
| Parse token response lỗi | Converter/body extractor/Content-Type không khớp | OAuth2 HTTP codecs |
| Đổi code xong, OIDC login fail | ID Token signature/JWKS/issuer/audience lỗi | JWT decoder/JWKS |
| API trả `401` sau login | Access token/audience/scope/API policy | Resource Server |

**Ví dụ:** tăng timeout không sửa được `invalid_client`; đổi client secret không sửa được chứng chỉ HTTPS sai hostname. Việc phân loại đúng giúp điều chỉnh cấu hình tại thành phần thực sự có lỗi.

### 15.1. Kịch bản: token exchange thành công nhưng JWKS timeout

AS trả token thành công qua proxy nhưng Spring Security cần JWK Set để xác minh chữ ký ID Token. JWKS loader dùng HTTP client khác và không qua proxy, nên login thất bại.

Cách xử lý là thiết lập connectivity cho **JWKS**. Không tắt xác minh chữ ký hoặc chỉ tăng response timeout ở Token Endpoint.

### 15.2. Kịch bản: discovery fail ngay khi startup

`issuer-uri` yêu cầu Spring tải discovery metadata khi tạo registration. Nếu kết nối discovery không đi qua proxy, ứng dụng có thể không startup được. Lúc đó token response client còn **chưa chạy**.

Phải kiểm tra network/TLS cho metadata discovery hoặc dùng cấu hình endpoint tường minh phù hợp với provider, không thay đổi token client rồi mong chữa được startup.

### 15.3. Kịch bản: proxy yêu cầu authentication

Backend trả lỗi 407 khi gọi Token Endpoint. Đây là lỗi **giữa client và proxy**, không phải AS báo `invalid_client`. Cần cấu hình proxy username/password/method trong HTTP transport, không thay đổi OAuth2 client secret.

### 15.4. Kịch bản: mất session ở callback

Spring Security không tìm được authorization request/PKCE verifier sau redirect, rồi token exchange báo `invalid_grant` hoặc callback bị từ chối. Đây là vấn đề session/state/callback, không phải do response timeout mặc dù cùng xuất hiện trong login flow.

## 16. Quy trình triển khai một kết nối Token Endpoint đáng tin cậy

Có thể tổ chức các bước triển khai như sau:

1. **Xác định stack:** Servlet với `RestClient` hoặc WebFlux với `WebClient`.
2. **Xác định grant types:** chỉ authorization code hay còn refresh token/client credentials.
3. **Giữ client registration đúng:** token URI, client authentication method, scope và redirect URI.
4. **Tạo transport chuyên biệt:** connect/read/TLS/proxy/pool config.
5. **Giữ OAuth2 form converters/error handling:** không thay giao thức khi chỉ cần thay đường mạng.
6. **Gắn transport vào đúng token response client:** `setRestClient` hay `setWebClient`.
7. **Gắn token response client vào Spring Security:** bean detection hoặc DSL phù hợp phiên bản; cân nhắc refresh token flow.
8. **Xác định riêng các đường discovery/JWKS/UserInfo:** chúng có thể cần HTTP client khác.
9. **Thiết kế logging an toàn:** chỉ ghi status, latency, error category, không ghi bí mật.
10. **Quan sát lỗi theo từng pha:** DNS, connect, proxy, TLS, token response, ID Token validation.

### 16.1. Ví dụ đường mạng nhiều điểm đến

~~~text
Browser
    |
    v
App Spring Boot (private subnet)
    |
    +-- proxy.corp.example --> id.example.com/oauth2/token
    |
    +-- proxy.corp.example --> id.example.com/.well-known/jwks.json
    |
    +-- direct --------------> api.internal.example
~~~

Đường Token Endpoint có thể dùng `RestClient` custom, đường JWKS đi qua JWT decoder, còn API nội bộ do HTTP client ứng dụng quản lý. Cấu hình mạng phải nhất quán theo từng endpoint. Đừng đặt proxy toàn cục khiến những API private phải đi ra ngoài không cần thiết.

### 16.2. Property tách theo môi trường

Ví dụ custom properties do ứng dụng tự bind:

~~~yaml
# application-dev.yml
app:
  oidc:
    token-http:
      connect-timeout: 3s
      response-timeout: 10s
      proxy-enabled: false
~~~

~~~yaml
# application-prod.yml
app:
  oidc:
    token-http:
      connect-timeout: 3s
      response-timeout: 10s
      proxy-enabled: true
      proxy-host: proxy.corp.example
      proxy-port: 3128
~~~

Chú ý đây **không phải** một cấu hình Spring Security tự động hỗ trợ. HTTP client builder của ứng dụng phải đọc property tương ứng. Đừng commit proxy password hoặc private key trong YAML.

## 17. Tình huống vận dụng

### Tình huống A: chỉ cấu hình read timeout cho API client

Ứng dụng gọi API bằng `WebClient` đã có `responseTimeout(10s)`, nhưng đăng nhập vẫn treo 60 giây khi đổi code.

**Giải thích:** WebClient gọi API có thể là instance khác với HTTP client Token Endpoint. Phải kiểm tra token response client và transport mà nó dùng.

### Tình huống B: client có certificate của private CA

Browser đăng nhập được, nhưng backend `POST /token` báo `PKIX path building failed`.

**Giải thích:** Browser và backend dùng truststores riêng. Cần cấp đúng CA/truststore cho **HTTP transport của backend**, không tắt TLS verification.

### Tình huống C: authorization code đã dùng sau timeout

Client timeout khi chờ token response rồi retry cùng code và nhận `invalid_grant`.

**Giải thích:** AS có thể đã tiêu thụ code trước khi response bị mất. Không retry mù quáng; khi không khôi phục được, bắt đầu authorization flow mới.

### Tình huống D: có proxy nhưng JWKS vẫn lỗi

Token endpoint qua proxy trả access token + ID Token; sau đó lỗi khi xác minh ID Token.

**Giải thích:** kết nối JWKS độc lập cần proxy/truststore tương ứng. Không dùng ID Token chưa được xác minh.

### Tình huống E: ứng dụng dùng cả authorization code và refresh token

Đăng nhập lần đầu thành công, sau một giờ refresh token thất bại do firewall.

**Giải thích:** cấu hình chỉ áp dụng cho `RestClientAuthorizationCodeTokenResponseClient`, còn refresh grant sử dụng token client khác. Cần đảm bảo refresh client cũng dùng transport phù hợp.

### Tình huống F: ứng dụng WebFlux dùng nhầm RestTemplate

Một developer dùng `RestTemplate` blocking trong reactive login pipeline và gọi `.block()` khi chạy trên event loop.

**Giải thích:** dùng `WebClientReactiveAuthorizationCodeTokenResponseClient` và `WebClient`/Reactor Netty phù hợp; tránh blocking event loop.

### Tình huống G: proxy trả HTTP 407

Token request không tới được AS do proxy yêu cầu authentication.

**Giải thích:** credential proxy khác client secret. Cấu hình proxy authentication tại transport đúng phương thức; không gửi OAuth2 client secret làm proxy password.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Spring Security Servlet 6.4+ dùng lớp nào để đổi authorization code lấy token?

**Trả lời:** `RestClientAuthorizationCodeTokenResponseClient`, có thể gọi `setRestClient(...)` để tùy chỉnh HTTP client.

**Câu 2.** WebFlux dùng lớp nào?

**Trả lời:** `WebClientReactiveAuthorizationCodeTokenResponseClient` với `setWebClient(...)` và `ClientHttpConnector` tương ứng.

**Câu 3.** Tùy chỉnh Token Endpoint RestClient có tự thay cách tải JWKS không?

**Trả lời:** Không. JWT decoder/JWK source có thể dùng HTTP client riêng; phải xử lý kết nối của nó nếu cần.

**Câu 4.** Vì sao không bỏ `OAuth2AccessTokenResponseHttpMessageConverter` khi thay RestClient?

**Trả lời:** Spring Security cần nó để đọc phản hồi token OAuth2; bỏ converter dễ khiến token response không được parse đúng.

**Câu 5.** Có nên tự retry authorization code grant khi timeout không?

**Trả lời:** Không retry mù quáng; AS có thể đã tiêu thụ code. Cần cơ chế khôi phục phù hợp, thường là authorization flow mới.

**Câu 6.** Truststore và keystore khác gì?

**Trả lời:** Truststore chứa trust anchors để xác minh certificate server; keystore chứa client certificate/private key cho mTLS khi cần.

**Câu 7.** Vì sao tăng `server.connection-timeout` không chắc có tác dụng?

**Trả lời:** Token exchange là kết nối outbound. Timeout ở server inbound thường không thay đổi HTTP client dùng gửi `POST /token`.

**Câu 8.** Khi nhận HTTP 407, cần kiểm tra gì?

**Trả lời:** Proxy authentication và cấu hình HTTP transport, không phải OAuth2 client secret trừ khi các lỗi khác xuất hiện.

## 19. Ghi nhớ trọng tâm

| Cần làm | Servlet | WebFlux |
|---|---|---|
| Tùy chỉnh token HTTP client | Tạo `RestClient` chuyên dụng | Tạo `WebClient` chuyên dụng |
| Gắn vào token response client | `RestClientAuthorizationCodeTokenResponseClient.setRestClient` | `WebClientReactiveAuthorizationCodeTokenResponseClient.setWebClient` |
| Connect timeout | `HttpClient.Builder.connectTimeout` | `CONNECT_TIMEOUT_MILLIS` |
| Response timeout | `JdkClientHttpRequestFactory.setReadTimeout` | `HttpClient.responseTimeout` |
| TLS | `SSLContext` / truststore | Netty `SslContext` / trusted CA |
| Proxy | JDK `ProxySelector` hoặc HTTP client tương ứng | Reactor Netty `proxy(...)` |
| OAuth2 form/error handling | Giữ form + token converters + OAuth2 error handler | Giữ reactive token response parsing/error processing |
| Refresh grant | `RestClientRefreshTokenTokenResponseClient` | `WebClientReactiveRefreshTokenTokenResponseClient` |
| JWKS/Discovery/UserInfo | Cần xem kết nối riêng | Cần xem kết nối riêng |

Khi tùy chỉnh Token Endpoint trong Spring Security OAuth 2.0/OIDC Client, hãy **thay HTTP transport ở đúng token response client**, đặt timeout và proxy phù hợp mạng triển khai, giữ TLS verification chặt chẽ, và duy trì converters/error handlers theo giao thức. Đặc biệt, phải xem xét cả refresh token flow và các kết nối OIDC khác như discovery, JWKS và UserInfo. PKCE, client authentication và token validation tiếp tục là trách nhiệm của các thành phần Spring Security/Authorization Server tương ứng.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorization Grant Support (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): `RestClientAuthorizationCodeTokenResponseClient`, `setRestClient`, token response converters và error handler.
- [Spring Security — OAuth2 Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/): `oauth2Login`, `oauth2Client`, token response client beans.
- [Spring Security — Authorization Grant Support (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): `WebClientReactiveAuthorizationCodeTokenResponseClient`, `setWebClient`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cấu hình `RestClient` và request factory.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): connector và HTTP client trong WebFlux.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pool, proxy, response/connect/TLS timeouts.

