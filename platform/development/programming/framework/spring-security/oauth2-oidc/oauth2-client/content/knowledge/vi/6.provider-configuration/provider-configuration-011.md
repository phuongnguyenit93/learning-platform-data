# 6.11. Provider trong mạng nội bộ, TLS và proxy kết nối ra ngoài

## 1. Bối cảnh: OAuth2/OIDC Provider không phải lúc nào cũng ở Internet công cộng

Trong một ứng dụng **Spring Security OAuth 2.0/OIDC Client**, Authorization Server hoặc OpenID Provider có thể nằm trong mạng nội bộ doanh nghiệp, chỉ truy cập được qua VPN, Kubernetes private network, private endpoint hoặc một proxy kết nối ra ngoài. Đồng thời, ứng dụng có thể chạy sau ingress/load balancer, sử dụng chứng chỉ do CA nội bộ cấp và không được phép kết nối Internet trực tiếp.

Khi đó, cấu hình đúng **client ID, client secret và scope** vẫn chưa đủ. Một luồng OAuth2/OIDC thành công đòi hỏi tất cả các đường kết nối có liên quan đều hoạt động, sử dụng tên miền phù hợp và tin cậy chứng chỉ TLS:

- **Trình duyệt của người dùng** phải truy cập được Authorization Endpoint để thực hiện đăng nhập/chấp thuận quyền.
- **Backend chạy Spring Security** phải truy cập được các endpoint phía máy chủ như discovery, Token Endpoint, JWKS, UserInfo khi được dùng.
- **Nhà cung cấp danh tính** phải có redirect URI hợp lệ dẫn trình duyệt trở lại ứng dụng.
- **Ứng dụng** cần tin cậy danh tính TLS của provider, còn provider có thể yêu cầu ứng dụng xác thực bằng client secret, private key JWT hoặc mutual TLS (mTLS), tùy cấu hình.
- **Proxy mạng** cần được áp dụng đúng cho từng HTTP client liên quan; cấu hình proxy cho một HTTP client không mặc nhiên làm mọi thư viện trong ứng dụng đi qua proxy đó.

Mục tiêu bài học là phân tích chính xác các đường đi, cấu hình provider trong Spring Boot/Spring Security và chẩn đoán lỗi kết nối, TLS, DNS hoặc proxy mà không làm suy yếu cơ chế xác thực.

## 2. Tách luồng front-channel và back-channel

Xét ứng dụng web nội bộ truy cập qua `https://portal.example.com`, dùng OIDC Provider có issuer `https://sso.corp.example/realms/staff`.

~~~mermaid
flowchart LR
    B["Browser của nhân viên"] -->|"1. GET /login"| A["Spring Boot Web App / BFF"]
    A -.->|"2. 302 redirect đến authorization-uri"| B
    B -->|"3. Mở Authorization Endpoint"| I["OIDC Provider"]
    I -.->|"4. 302 callback + code"| B
    B -->|"5. Callback /login/oauth2/code/..."| A
    A -->|"6. Token Endpoint, JWKS, UserInfo (TLS)"| I
    A -->|"7. Session cookie"| B
~~~

**Front-channel** là các bước diễn ra qua trình duyệt: redirect tới Authorization Endpoint và redirect về callback. **Back-channel** là HTTP request do backend thực hiện để đổi authorization code lấy token, khám phá provider metadata hoặc tải khóa JWK; tùy luồng, backend còn gọi UserInfo Endpoint.

| Điểm truy cập | Ai tạo kết nối? | Có thể cần proxy? | Điều kiện quan trọng |
| --- | --- | --- | --- |
| Authorization Endpoint | Trình duyệt người dùng | Proxy/VPN của **máy người dùng** | Browser resolve DNS, truy cập HTTPS, tin cậy certificate |
| Redirect URI về ứng dụng | Trình duyệt người dùng | Reverse proxy/ingress **phía ứng dụng** | Public URL, callback đúng, cookies và session |
| OIDC discovery metadata | Backend Spring khi dựng cấu hình | Proxy hoặc đường mạng **phía backend** | Issuer chính xác, TLS và metadata hợp lệ |
| Token Endpoint | Backend Spring | Proxy egress, private network, firewall | Kết nối HTTPS, client authentication, grant |
| JWKS endpoint | Backend Spring hoặc thành phần xác minh token | Proxy/đường mạng phía backend | Tải đúng bộ khóa, TLS tin cậy |
| UserInfo Endpoint | Backend Spring nếu luồng sử dụng | Proxy/đường mạng phía backend | Access token đúng quyền, HTTPS |
| API khác được bảo vệ | Backend khi làm OAuth2 Client | Đường mạng riêng cho API đích | Bearer access token dành cho đúng Resource Server |

Đừng đồng nhất **proxy egress** với **reverse proxy/ingress**:

- Proxy **egress** điều khiển request **đi từ backend tới** IdP hoặc API ngoài.
- Reverse proxy/ingress nhận request **đi từ browser vào** ứng dụng và thường chuyển tiếp các header mô tả host/scheme bên ngoài.
- Một cấu hình `https.proxyHost` trên JVM không giúp browser truy cập IdP chỉ có tên miền nội bộ; một cấu hình `X-Forwarded-Proto` ở ingress không tự giải quyết lỗi token request đi qua egress proxy.

### 2.1. Ba hình thái triển khai phổ biến

**Trường hợp A — Provider chỉ nằm trong mạng doanh nghiệp.** Nhân viên cần ở trong văn phòng hoặc kết nối VPN để browser mở Authorization Endpoint. Backend phải có tuyến tới mạng nội bộ từ nơi triển khai (VM, container, cluster). Nếu browser ở Internet không thể resolve hoặc mở tên miền private của provider, đăng nhập vẫn thất bại dù backend đã truy cập được Token Endpoint.

**Trường hợp B — Provider có public hostname nhưng backend bị chặn outbound.** Browser có thể mở trang đăng nhập, song backend chỉ truy cập được Token Endpoint/JWKS thông qua HTTP CONNECT proxy. Cần cấu hình egress cho thành phần HTTP thực sự xử lý token request và discovery.

**Trường hợp C — Split-horizon DNS.** Cùng một hostname issuer `sso.corp.example` có thể resolve thành địa chỉ private ở mạng backend và địa chỉ public ở browser/Internet qua các DNS khác nhau. Cách này có thể hữu ích nếu **URL và issuer chuẩn vẫn thống nhất**, certificate hợp lệ cho cùng hostname và cả hai tuyến thực sự phục vụ cùng một provider.

## 3. Issuer, endpoint, DNS và tính nhất quán định danh

Một OIDC Provider có **issuer** làm định danh chuẩn, ví dụ:

~~~text
https://sso.corp.example/realms/staff
~~~

OIDC discovery cung cấp tài liệu metadata có thể chứa các trường:

~~~json
{
  "issuer": "https://sso.corp.example/realms/staff",
  "authorization_endpoint": "https://sso.corp.example/realms/staff/protocol/openid-connect/auth",
  "token_endpoint": "https://sso.corp.example/realms/staff/protocol/openid-connect/token",
  "jwks_uri": "https://sso.corp.example/realms/staff/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://sso.corp.example/realms/staff/protocol/openid-connect/userinfo"
}
~~~

Đây là ví dụ minh họa một provider có cấu trúc endpoint tương tự Keycloak; **đường dẫn thực tế phải lấy từ metadata/nhà quản trị IdP**. Các provider khác không nhất thiết dùng những URL này.

Nguyên tắc vận hành:

1. **Issuer phải là danh tính được provider công bố**, không tùy tiện thay bằng hostname nội bộ cho tiện gọi API. Claim `iss` trong ID Token phải phù hợp issuer được tin cậy.
2. Các endpoint có thể sử dụng hostname khác nhau nếu metadata của provider khai báo và chính sách triển khai cho phép; mỗi hostname đều cần resolve, có route, được cấp certificate đúng tên.
3. **Token và ID Token cần được xác minh theo issuer thực**. Việc làm reverse proxy đổi hostname, scheme hoặc path không được phép dẫn tới bỏ qua validation của issuer, audience, chữ ký hay thời hạn.
4. Dùng **hostname đúng với Subject Alternative Name (SAN)** trên certificate. Việc kết nối bằng IP trong khi certificate chỉ cấp cho tên miền thường gây lỗi hostname verification.
5. Phân biệt **DNS của laptop**, **DNS của container/pod** và **DNS của proxy**. HTTP CONNECT proxy có thể resolve đích ở phía proxy; khi bypass proxy, backend cần tự resolve và tự có route.
6. Nếu IdP được đặt sau reverse proxy, provider cần biết external hostname và HTTPS scheme để phát ra metadata/redirect nhất quán. Thay `https` thành `http` chỉ để vượt lỗi cấu hình không phải giải pháp.

### 3.1. Discovery có thể phát sinh ngay khi ứng dụng khởi động

Khi Spring Boot dùng thuộc tính `spring.security.oauth2.client.provider.<id>.issuer-uri`, quá trình xây dựng `ClientRegistration` có thể truy vấn OIDC/OAuth2 provider metadata ngay trong giai đoạn khởi tạo. Vì vậy một ứng dụng có thể **không khởi động được** khi DNS, proxy hoặc TLS tới IdP chưa sẵn sàng, dù chưa người dùng nào bấm Đăng nhập.

Khi cần khởi động độc lập với discovery hoặc provider không công bố metadata chuẩn, có thể cung cấp cấu hình endpoint một cách tường minh phù hợp phiên bản Spring Security. Với OIDC, vẫn phải bảo toàn cơ chế kiểm tra issuer và ID Token, tránh việc bỏ thuộc tính issuer rồi vô tình làm giảm validation. Với OAuth2 thuần `client_credentials`, Token Endpoint tĩnh thường đủ để khởi tạo đăng ký client mà không cần một luồng OIDC discovery.

## 4. Cấu hình provider trong Spring Boot

### 4.1. OIDC Login với issuer chuẩn

Ví dụ `application.yml` cho một web app sử dụng `authorization_code`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://sso.corp.example/realms/staff
~~~

Trong cấu hình:

- `corporate` là **registrationId** của client bên trong Spring Security; đường dẫn khởi động login mặc định là `/oauth2/authorization/corporate`.
- `corporate-oidc` là khóa khai báo **provider** dùng lại cho registration này.
- `issuer-uri` trỏ tới **issuer chính thức**; Spring Security dựa vào metadata provider để xác định Authorization Endpoint, Token Endpoint và thông tin liên quan.
- `redirect-uri` là URL mà browser quay lại **ứng dụng**, không phải URL tới IdP. Giá trị suy ra từ `{baseUrl}` phải trùng redirect URI được đăng ký tại IdP.
- Biến `CORPORATE_CLIENT_ID` và `CORPORATE_CLIENT_SECRET` cần được cấp qua cơ chế cấu hình/secret của môi trường, không hard-code bí mật trong repository.
- Scope `openid` thể hiện yêu cầu xác thực OIDC; access token và ID Token có mục đích khác nhau.

Nếu ứng dụng chạy sau ingress nhưng bên trong nhận request HTTP trên `http://portal-service:8080`, Spring phải nhận biết external URL `https://portal.example.com`; có thể cấu hình **forwarded headers** phù hợp với proxy tin cậy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Tùy nền tảng, cũng có thể dùng chiến lược xử lý native hoặc cấu hình ingress tương ứng. **Chỉ chấp nhận forwarded headers từ reverse proxy tin cậy**; không để client bên ngoài tự điều khiển host/scheme được dùng để dựng redirect URI. Nếu môi trường có tên miền cố định, có thể khai báo redirect URI cụ thể để giảm phụ thuộc vào việc suy ra host.

### 4.2. Provider nội bộ chỉ dùng cho `client_credentials`

Với backend chạy scheduled job hoặc gọi API khác bằng quyền của chính service, không cần OIDC login qua browser:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          finance-api:
            provider: finance-auth
            client-id: ${FINANCE_CLIENT_ID}
            client-secret: ${FINANCE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: finance.read
        provider:
          finance-auth:
            token-uri: https://token.corp.internal/oauth2/token
~~~

Ở đây:

- Backend cần truy cập được `token.corp.internal` qua mạng, TLS và proxy/bypass phù hợp.
- Không có authorization redirect qua browser và không tạo một phiên đăng nhập người dùng.
- `ReactiveClientRegistrationRepository` hoặc `ClientRegistrationRepository` lưu cấu hình client; thành phần **authorized client manager** mới có trách nhiệm thực hiện xin token và cung cấp token cho HTTP client gọi API.
- Token Endpoint có thể yêu cầu thêm cơ chế xác thực client (mTLS, JWT assertion hoặc cơ chế khác) theo hợp đồng với Authorization Server.

## 5. TLS: certificate, trust chain, hostname và mTLS

### 5.1. Những gì diễn ra khi kết nối HTTPS

Khi backend gọi `https://sso.corp.example`, HTTP client khởi tạo kết nối TLS và kiểm tra certificate của đầu bên kia. Trong cấu hình chuẩn, quá trình kiểm tra gồm:

1. Certificate còn hiệu lực theo thời gian và chính sách.
2. Tên host yêu cầu khớp SAN trong certificate.
3. Chuỗi chứng chỉ dẫn tới một **Certificate Authority (CA)** mà HTTP client tin cậy.
4. Thuật toán, key usage và các ràng buộc TLS đáp ứng chính sách bảo mật của thư viện/runtime.

Một provider chỉ sử dụng certificate do CA nội bộ cấp thường không có root CA đó trong truststore mặc định của JVM/container. Kết quả thường là lỗi thuộc nhóm **PKIX path building failed**, **unable to find valid certification path** hoặc **certificate verify failed**.

TLS **không** được coi là cấu hình đúng khi chỉ “kết nối thành công”. Nếu tắt kiểm tra certificate hoặc hostname, một server giả mạo cùng đường mạng có thể thu thập authorization code, access token hoặc client secret.

### 5.2. Import CA nội bộ vào truststore riêng

Nhà quản trị PKI cung cấp **root CA** và, nếu cần, intermediate CA hợp lệ của tổ chức. Có thể tạo truststore PKCS#12:

~~~bash
keytool -importcert +  -alias corporate-root-ca +  -file corporate-root-ca.pem +  -keystore corporate-truststore.p12 +  -storetype PKCS12
~~~

Lệnh sẽ yêu cầu đặt mật khẩu truststore nếu file chưa tồn tại. Chỉ import certificate CA đã được xác minh từ kênh tin cậy, **không** lấy một certificate bất kỳ do endpoint lỗi trả về rồi tin cậy ngay.

Ví dụ cấu hình JVM sử dụng truststore được mount vào container:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/certs/corporate-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<secret-managed-at-runtime>
~~~

Đây là các JVM system properties minh họa; cách truyền mật khẩu phụ thuộc nền tảng chạy và cơ chế secret. Tránh đưa mật khẩu vào Git, log, câu lệnh được ghi lịch sử hoặc thông tin process có thể bị người không có quyền xem. Cần xác nhận **HTTP client thực tế** trong Spring Security có sử dụng trust material đã cấu hình: các thư viện Netty, Apache HttpClient hoặc HTTP client tùy chỉnh có thể dùng SSL context riêng.

**Lưu ý:** khi chỉ định một truststore mới, JVM có thể không còn sử dụng danh sách CA công cộng mặc định. Nếu ứng dụng cũng gọi provider/public API khác, hãy chuẩn bị trust material phù hợp cho **tất cả đích cần tin cậy**, hoặc cấu hình trust riêng theo từng HTTP client thay vì thay thế tùy tiện global truststore.

### 5.3. Đừng nhầm server TLS với client authentication

| Cơ chế | Ai trình credential? | Mục đích |
| --- | --- | --- |
| TLS thông thường | Provider trình server certificate | Client xác thực server và mã hóa kết nối |
| Client secret tại Token Endpoint | OAuth client gửi client credential theo phương thức đã đăng ký | Authorization Server xác thực danh tính OAuth client |
| mTLS | Ngoài server certificate, client trình client certificate/private key | Hai phía xác thực danh tính TLS; có thể là phương thức OAuth client authentication |
| Private key JWT | OAuth client ký client assertion bằng private key đã đăng ký | Authorization Server xác thực OAuth client bằng chữ ký |

Thêm CA vào **truststore** chỉ giúp client tin cậy certificate phía server. Nó **không** cấu hình client certificate/private key cho mTLS. Nếu IdP bắt buộc mTLS, cần cấu hình **key material** cho HTTP client thực sự thực hiện token request và bảo đảm proxy cho phép mô hình TLS/mTLS tương ứng.

### 5.4. Proxy có thể thay đổi nơi TLS được thiết lập

- Với **HTTP CONNECT proxy** chỉ chuyển tiếp tunnel, TLS thường được xác lập giữa backend và provider bên trong đường hầm; backend kiểm tra server certificate của provider.
- Nếu doanh nghiệp dùng **TLS-intercepting proxy**, backend có thể thấy certificate do CA của proxy phát hành. Quyền tin cậy đối với CA của proxy phải được cấp theo chính sách tổ chức và chỉ trong phạm vi cho phép.
- Nếu IdP yêu cầu **mTLS end-to-end**, TLS interception có thể không tương thích với mục tiêu xác thực client certificate tới IdP; cần phối hợp đội mạng/IdP để thiết kế tuyến kết nối phù hợp.

**Không dùng** một cấu hình kiểu “trust all certificates”, bỏ qua hostname verification hoặc `curl -k` làm giải pháp triển khai. Những thao tác này có thể che lỗi DNS, CA chain hoặc proxy và làm mất tính bảo vệ của OAuth2/OIDC.

## 6. Proxy egress: hiểu đúng proxy được cấu hình ở đâu

Ứng dụng có thể có nhiều HTTP client khác nhau:

- Thư viện tạo **ClientRegistration** có thể gọi discovery metadata khi khởi động.
- Thành phần **OAuth2 token response client** gọi Token Endpoint.
- Thành phần gọi **UserInfo** hoặc tải **JWK Set** thực hiện các request HTTPS khác.
- **WebClient**, **RestClient**, **RestTemplate** hoặc SDK của ứng dụng gọi các API nghiệp vụ.

Không có bảo đảm rằng cấu hình proxy cho một trong các thành phần trên tự động áp dụng cho các thành phần còn lại.

### 6.1. Biến môi trường, JVM system properties và HTTP client

Một số công cụ dòng lệnh/SDK có thể đọc:

~~~text
HTTP_PROXY=http://proxy.corp.example:3128
HTTPS_PROXY=http://proxy.corp.example:3128
NO_PROXY=localhost,127.0.0.1,.corp.internal,.svc.cluster.local
~~~

Tuy nhiên, **không nên giả định Java hoặc Reactor Netty tự động tuân thủ mọi biến môi trường trên**. Ví dụ, JVM HTTP clients dựa trên proxy system properties có thể sử dụng:

~~~text
-Dhttps.proxyHost=proxy.corp.example
-Dhttps.proxyPort=3128
-Dhttp.proxyHost=proxy.corp.example
-Dhttp.proxyPort=3128
-Dhttp.nonProxyHosts=localhost|127.*|*.corp.internal|*.svc.cluster.local
~~~

Đối với các triển khai JDK, `http.nonProxyHosts` cũng thường được dùng để loại trừ host cho HTTPS. Dấu `|` ở đây là cú pháp phân tách trong **JVM system properties** và ký tự `*` biểu diễn wildcard, khác với pattern regex của một số HTTP client khác.

Các tham số trên **không phải hợp đồng toàn cục** cho tất cả client Spring: Reactor Netty, Apache HttpClient, JDK HttpClient và thư viện OAuth2 có thể đọc cấu hình theo những cách khác nhau. Cần kiểm tra **HTTP client nào thật sự được khởi tạo** cho mỗi request. Nếu proxy cần username/password, phải cấu hình cơ chế authentication dành cho proxy tại đúng client, và bảo vệ credential như secret.

### 6.2. Bypass proxy cho mạng nội bộ

Không phải mọi tên miền nội bộ đều cần đi qua proxy. Nếu backend có route trực tiếp tới `*.corp.internal` hoặc Kubernetes service, gửi qua proxy Internet có thể dẫn tới lỗi 502, DNS failure hoặc chặn truy cập private IP. Cần thiết kế **non-proxy hosts** theo mạng thực tế.

Ngược lại, một số doanh nghiệp bắt buộc phải đi qua **corporate egress proxy** ngay cả khi endpoint IdP có hostname dạng doanh nghiệp. Khi đó loại trừ toàn bộ `*.corp.example` bằng thói quen có thể làm request timeout. Chính sách bypass cần dựa vào **sơ đồ route/firewall của môi trường**, không dựa vào tên miền phỏng đoán.

## 7. Ví dụ WebFlux: cấu hình proxy cho một `WebClient`

Với Spring WebFlux sử dụng Reactor Netty, ta có thể chỉ định HTTP proxy cho **một WebClient cụ thể**, để các request của client đó đi theo tuyến mong muốn:

~~~java
@Configuration
class ProviderHttpClientConfig {

    @Bean("providerWebClient")
    WebClient providerWebClient(
            @Value("${network.egress.proxy-host}") String proxyHost,
            @Value("${network.egress.proxy-port}") int proxyPort) {

        HttpClient nettyClient = HttpClient.create()
            .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host(proxyHost)
                .port(proxyPort)
                .nonProxyHosts(
                    "localhost|127[.]0[.]0[.]1|.*[.]svc[.]cluster[.]local|.*[.]corp[.]internal"
                )
            )
            .responseTimeout(Duration.ofSeconds(12));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(nettyClient))
            .build();
    }
}
~~~

~~~yaml
network:
  egress:
    proxy-host: proxy.corp.example
    proxy-port: 3128
~~~

Các kiểu tương ứng gồm `reactor.netty.http.client.HttpClient`, `reactor.netty.transport.ProxyProvider`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`, `java.time.Duration` và annotation Spring. Đoạn code rút gọn phần `import`.

Ở đây:

1. `ProxyProvider.Proxy.HTTP` cấu hình một HTTP proxy; với kết nối HTTPS, Reactor Netty có thể thiết lập tunnel CONNECT theo cơ chế hỗ trợ.
2. `nonProxyHosts(...)` trong Reactor Netty dùng **regular expression**, không phải cú pháp wildcard `http.nonProxyHosts` của JVM. Pattern này minh họa bypass các host nội bộ, cần điều chỉnh theo topology thật.
3. `responseTimeout` giới hạn thời gian chờ phản hồi khi đã gửi request; trong hệ thống sản xuất còn cần cân nhắc connect timeout, proxy connect timeout, retry và khả năng giám sát.
4. `providerWebClient` là **bean riêng**. Chỉ những lời gọi dùng bean này mới chắc chắn đi theo cấu hình vừa nêu.

**Cực kỳ quan trọng:** tạo `WebClient` có proxy **không tự động chuyển** OAuth2 Login token exchange, OIDC metadata discovery, JWKS fetch hoặc UserInfo của Spring Security sang bean này. Những thành phần Spring Security sử dụng HTTP client riêng; phải cấu hình tại điểm mở rộng tương ứng với phiên bản Spring Security đang chạy.

### 7.1. Gắn proxy WebClient vào một client credentials token flow

Ví dụ với Spring Security reactive hỗ trợ `WebClientReactiveClientCredentialsTokenResponseClient` và `ReactiveOAuth2AuthorizedClientProviderBuilder`:

~~~java
@Configuration
class ServiceToServiceTokenConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService,
            @Qualifier("providerWebClient") WebClient providerWebClient) {

        var tokenClient =
            new WebClientReactiveClientCredentialsTokenResponseClient();
        tokenClient.setWebClient(providerWebClient);

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(configurer ->
                    configurer.accessTokenResponseClient(tokenClient))
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Ví dụ giả định ứng dụng đã có `ReactiveOAuth2AuthorizedClientService` và `ReactiveClientRegistrationRepository`, do cấu hình Boot hoặc do code cung cấp; phần `import` được lược bỏ. Manager này dành cho **ngữ cảnh service-to-service** và được cấu hình riêng với grant `client_credentials`. Khi gọi `authorize(...)` cho registration tương ứng, token response client sẽ sử dụng `providerWebClient` để thực hiện token request.

Nếu ứng dụng dùng **OIDC Login/authorization code**, token exchange đi qua các thành phần khác của Spring Security. Cần tùy biến **authorization-code token response client**, **OIDC UserInfo client** và **JWK retrieval** khi chúng cũng phải đi qua proxy; chỉ cấu hình grant `client_credentials` như ví dụ trên **không giải quyết** các điểm kết nối của login flow.

Đối với Spring MVC/Servlet, cách gắn HTTP client/proxy khác với WebFlux; các API như `RestClientAuthorizationCodeTokenResponseClient`, `DefaultAuthorizationCodeTokenResponseClient` hoặc những hook khác tùy phiên bản có thể sử dụng HTTP client được cấu hình riêng. Đừng đưa class reactive vào `HttpSecurity` của Servlet chỉ vì tên tương tự.

### 7.2. Vì sao discovery lúc startup vẫn có thể lỗi?

Nếu registration dùng `issuer-uri`, việc lấy metadata trong giai đoạn dựng bean có thể diễn ra **trước khi bean `providerWebClient` ở ví dụ được đưa vào token manager**. Vì vậy thành công khi gọi API bằng WebClient riêng không chứng minh OIDC discovery đã đi đúng proxy.

Những lựa chọn kiến trúc thường dùng:

- Cho phép kết nối trực tiếp tới issuer trong private network bằng DNS và route chính xác.
- Cấu hình proxy ở HTTP client/mạch khởi tạo discovery được Spring Security sử dụng, theo API của phiên bản đang chạy.
- Dùng cấu hình endpoint tường minh hoặc repository custom khi cần kiểm soát hoàn toàn quá trình khởi tạo, **đồng thời bảo đảm kiểm tra issuer và ID Token vẫn đúng**.

Mỗi lựa chọn cần được quyết định theo nơi chạy ứng dụng và hợp đồng của IdP. Không nên giải quyết lỗi kết nối bằng cách tắt validation TLS hoặc bỏ qua issuer.

## 8. Reverse proxy trước ứng dụng và vấn đề redirect URI

Một kiến trúc phổ biến:

~~~text
Browser -- HTTPS --> Ingress / Reverse Proxy -- HTTP --> Spring Boot
               Host: portal.example.com               portal-service:8080
~~~

Nếu backend tự suy ra `{baseUrl}` từ kết nối nội bộ, redirect URI có thể thành `http://portal-service:8080/login/oauth2/code/corporate` thay vì `https://portal.example.com/login/oauth2/code/corporate`. IdP sẽ từ chối vì **redirect_uri_mismatch** hoặc browser không thể truy cập URL nội bộ.

Cần xác định:

- External hostname/scheme/path thực tế mà người dùng truy cập.
- Cấu hình redirect URI đã đăng ký chính xác tại IdP.
- Proxy có gửi `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` và, khi cần, thông tin prefix đúng không.
- Spring Boot/Spring Security có được cấu hình chỉ tin các header đó qua proxy được kiểm soát không.
- Cookie dùng cho login/session có thuộc tính `Secure`, `HttpOnly`, `SameSite` hợp lý, và callback có lấy lại được session chứa trạng thái đăng nhập trước đó không.

Một callback nhận được authorization code nhưng mất session có thể báo lỗi liên quan tới `state`/authorization request. Đây là lỗi **cookie hoặc session qua reverse proxy**, không phải mặc định lỗi client secret hay TLS tới Token Endpoint.

## 9. Chẩn đoán kết nối theo từng lớp

Khi một môi trường không đăng nhập được, cách nhanh nhất là xác định **request nào hỏng và request đó chạy ở máy nào**.

### 9.1. Kiểm tra từ đúng vị trí chạy backend

Chạy các lệnh đọc trạng thái từ VM/container/pod chạy ứng dụng, hoặc từ một môi trường có cùng DNS, egress policy và trust material:

~~~bash
# DNS: tên miền được phân giải thành địa chỉ nào?
nslookup sso.corp.example

# Kiểm tra TCP reachability nếu công cụ có sẵn.
nc -vz sso.corp.example 443

# Kiểm tra TLS và metadata qua đường trực tiếp.
curl --connect-timeout 5 --max-time 15 -v +  https://sso.corp.example/realms/staff/.well-known/openid-configuration

# Với CA nội bộ: dùng bundle CA đã được tổ chức xác minh.
curl --cacert /opt/app/certs/corporate-root-ca.pem +  https://sso.corp.example/realms/staff/.well-known/openid-configuration

# Kiểm tra explicit proxy egress khi mạng yêu cầu.
curl --proxy http://proxy.corp.example:3128 +  --connect-timeout 5 --max-time 15 +  https://sso.corp.example/realms/staff/.well-known/openid-configuration
~~~

**Đường dẫn discovery chỉ mang tính ví dụ**; với một số provider/chuẩn metadata, vị trí `.well-known` có thể khác. Nên dùng URL discovery được IdP công bố. Không in access token, client secret hoặc response có credential vào ticket/log chia sẻ.

Nhận diện các tình huống:

- DNS không resolve: kiểm tra DNS server, split-horizon DNS, search domain, private zone/peering.
- TCP timeout: kiểm tra route, firewall, security group, Kubernetes NetworkPolicy và proxy.
- TCP thông nhưng TLS thất bại: kiểm tra root/intermediate CA, SAN, SNI, proxy interception và phiên bản giao thức.
- Metadata tải được nhưng claim `issuer` sai: kiểm tra canonical hostname/realm và reverse proxy **phía IdP**.
- Chỉ lỗi khi chạy bằng JVM, còn `curl` thành công: so sánh **CA store, proxy config và HTTP client implementation** của JVM với curl.
- Browser login được nhưng đổi code thất bại: tập trung Token Endpoint, client authentication, egress, truststore, time sync và việc sử dụng authorization code đúng một lần.

### 9.2. Kiểm tra certificate và hostname

Nếu có OpenSSL:

~~~bash
openssl s_client -connect sso.corp.example:443 +  -servername sso.corp.example -showcerts
~~~

Lệnh này giúp quan sát certificate chain do endpoint trực tiếp cung cấp. Nếu kết nối đi qua HTTP proxy hoặc TLS inspection, phép kiểm tra cần được thực hiện qua **đúng tuyến proxy tương ứng**; kết quả direct connect và proxied connect có thể khác nhau. Tránh kết luận “JVM sai” chỉ dựa trên một công cụ dùng truststore và đường mạng khác.

### 9.3. Mức độ log cần thiết

Trong môi trường phát triển, có thể bật log debug có thời hạn cho những thành phần Spring Security OAuth2 hoặc Reactor Netty liên quan để thấy endpoint, giai đoạn thất bại và exception. Cần cấu hình masking/redaction để **không ghi log authorization code, bearer token, refresh token, client secret, cookie, hoặc proxy authorization header**.

Tối thiểu cần quan sát:

1. **Giai đoạn**: khởi tạo/discovery, redirect, callback, token exchange, JWKS, UserInfo hay gọi API.
2. **Đích truy cập**: hostname/port, có dùng proxy không, DNS resolve ở phía nào.
3. **Lỗi kỹ thuật**: DNS, timeout, TCP reset, TLS, HTTP status/response OAuth2.
4. **Correlation/request ID** (không kèm token) để nối log ingress, app, proxy egress và IdP.

## 10. Ma trận lỗi và hướng xử lý

| Triệu chứng | Tầng cần kiểm tra | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- | --- |
| App không khởi động khi bật `issuer-uri` | Discovery/startup | Không gọi được metadata, sai DNS/TLS/proxy | Kiểm tra route, CA, metadata endpoint và cách Spring tạo registration |
| Browser không mở được trang SSO | Front-channel | IdP chỉ trong mạng private, browser không có VPN/DNS | Cấp đường truy cập hợp lệ cho browser hoặc thay đổi kiến trúc công bố IdP |
| `UnknownHostException` | DNS backend | Private zone không khả dụng ở pod/VM | Kiểm tra resolver, DNS zone, network path |
| `ConnectTimeoutException`, timeout TCP | Route/firewall/proxy | Egress bị chặn, sai host/port, bypass proxy sai | Kiểm tra route, NetworkPolicy, proxy allowlist |
| `PKIX path building failed` | TLS trust | Thiếu CA nội bộ, sai truststore/client | Cài CA chain đúng, áp dụng vào HTTP client thực |
| Hostname mismatch hoặc certificate không đúng SAN | TLS identity | Dùng IP/alias không nằm trên cert, sai SNI | Dùng hostname chuẩn hoặc cấp lại cert hợp lệ |
| HTTP `407 Proxy Authentication Required` | Egress proxy | Thiếu credential hoặc sai proxy auth | Cấu hình proxy authentication an toàn tại client |
| HTTP `502/504` từ proxy | Proxy upstream | Proxy không tới được IdP, ACL không cho phép | Kiểm tra log proxy, DNS và route từ proxy đến IdP |
| `redirect_uri_mismatch` | Login/ingress | Callback khác URL đăng ký, mất HTTPS scheme | Sửa redirect URI và cấu hình forwarded headers |
| `invalid_client` ở Token Endpoint | OAuth2 client authentication | Sai ID/secret, auth method, client cert | So lại client registration với cấu hình IdP |
| `invalid_grant` | Authorization code/token flow | Code hết hạn/đã dùng, redirect_uri/PKCE không khớp | Xem lại callback, đồng bộ thời gian, PKCE và một lần đổi code |
| `invalid_scope` | Authorization Server | Scope không được cấp cho client | Đăng ký/phê duyệt scope đúng tại provider |
| ID Token có `iss` không khớp | OIDC validation | Metadata/external URL/realm sai | Sửa cấu hình canonical issuer; giữ validation |
| Không tải được JWKS hoặc unknown `kid` | Key retrieval/rotation | JWKS không truy cập được, key thay đổi hoặc cache | Kiểm tra JWKS URL, CA, route, cache/rotation |
| API trả `401` hoặc `403` sau login | Resource Server | Sai audience, thiếu scope hoặc token không được gửi | Kiểm tra access token, sender và chính sách API |

Hai mã HTTP rất dễ nhầm: **401** thường liên quan request chưa được xác thực/token không được chấp nhận; **403** thường xuất hiện khi request đã xác thực nhưng thiếu quyền. Một số gateway/provider có chính sách trả lỗi riêng, vì vậy cần xem response OAuth2 và log của thành phần thực sự trả lỗi.

## 11. Các lưu ý riêng cho Kubernetes, container và môi trường doanh nghiệp

**DNS và mạng:** Pod có thể resolve khác host node hoặc laptop. Private Service DNS, private endpoint, NAT gateway, egress gateway và NetworkPolicy có thể tạo các tuyến hoàn toàn khác nhau. Kiểm thử từ chính pod hoặc một pod có security context/network policy tương đương.

**CA và image:** Certificate CA nội bộ có thể không nằm trong JVM truststore của image tối giản, dù máy phát triển đã cài. Mount truststore hoặc tích hợp CA qua quy trình build/deploy được kiểm soát. Cần làm rõ ứng dụng sử dụng JDK SSL context, Netty native TLS hay custom SSL context.

**Proxy policy:** Sidecar service mesh, egress gateway hoặc HTTP proxy có thể là nhiều tầng khác nhau. Xác định hop nào chịu trách nhiệm DNS, CONNECT, TLS interception và allowlist. Không cấu hình vòng lặp để proxy trỏ trở lại ingress của ứng dụng.

**Tài khoản và secret:** Client secret, proxy credential và private key là các bí mật khác nhau. Lưu chúng trong secret manager/Kubernetes Secret với quyền tối thiểu, theo dõi rotation; không commit vào YAML và không dùng chung một giá trị cho mọi môi trường.

**Đồng hồ:** Authorization code, ID Token và access token gắn với thời hạn. Nếu đồng hồ giữa backend và IdP lệch nhiều, validation hoặc token exchange có thể lỗi dù mạng/TLS hoàn toàn đúng. Đồng bộ thời gian và chẩn đoán claim `iat`/`nbf`/`exp` theo quy trình an toàn.

**Hiệu năng và khả dụng:** Nếu metadata discovery hoặc JWKS retrieval phụ thuộc mạng riêng/proxy, sự cố của các thành phần đó có thể làm chậm startup hoặc authentication. Quy định timeout hợp lý, health check có mục tiêu và chính sách cache/rotation phù hợp; tránh retry vô hạn trên luồng request đăng nhập.

**Ràng buộc proxy:** Không nhận một URL provider bất kỳ từ request của người dùng rồi cho backend kết nối tới URL đó. Đưa provider/issuer vào allowlist và kiểm tra quyền truy cập theo tenant để tránh SSRF, lạm dụng proxy và truy xuất nhầm kho nội bộ.

## 12. Tình huống thực hành

### Tình huống A — Backend trên cluster gọi được IdP, nhưng nhân viên ở nhà không đăng nhập được

IdP có Authorization Endpoint chỉ truy cập được qua VPN. Bật `https.proxyHost` trong Java không thay đổi đường kết nối của browser. Giải pháp phải nằm ở **khả năng truy cập front-channel của người dùng**: VPN/zero-trust access, hoặc một phương án công bố IdP phù hợp với chính sách doanh nghiệp. Backend vẫn phải kết nối được Token Endpoint/JWKS.

### Tình huống B — Đăng nhập redirect thành công nhưng callback báo lỗi TLS khi đổi code

Browser đã tiếp cận được IdP và đã quay về ứng dụng, chứng tỏ phần front-channel hoạt động. Backend có thể thiếu CA root nội bộ hoặc chưa dùng proxy cho **token response client**. Kiểm tra exception và thử HTTPS từ môi trường chạy backend qua đúng proxy/trust material. Không tắt TLS validation để vượt lỗi.

### Tình huống C — Ứng dụng WebFlux có proxy `WebClient` nhưng vẫn lỗi ngay khi khởi động

`WebClient` custom dành cho các request sử dụng bean đó, trong khi `issuer-uri` có thể khiến Spring Security liên hệ metadata provider trước khi manager dùng `WebClient`. Cần chỉnh đường đi **của discovery** hoặc dùng cách khai báo provider tương thích phiên bản để không phụ thuộc discovery lúc startup, trong khi vẫn duy trì issuer validation.

### Tình huống D — Một môi trường chạy được, môi trường container trả `invalid_redirect_uri`

Ở local, app chạy trực tiếp HTTPS; trên container, proxy TLS termination chuyển HTTP vào ứng dụng. `{baseUrl}` có thể suy ra nhầm scheme/host. Cần đồng bộ public hostname, forwarded headers từ proxy tin cậy và redirect URI đã đăng ký với IdP; lỗi này thường không nằm ở egress TLS.

### Tình huống E — Truy cập qua HTTP proxy trả `407`

Backend đã tới proxy nhưng proxy yêu cầu authentication. Thêm user/password vào client HTTP proxy theo cơ chế được thư viện hỗ trợ, lưu credential an toàn, và xác nhận proxy cho phép CONNECT tới hostname/port IdP. Không nhầm proxy credential với OAuth2 `client-secret`.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Browser truy cập được trang đăng nhập của IdP, nhưng backend không truy cập được Token Endpoint. Có thể kết luận toàn bộ OAuth2 flow thành công về mặt mạng không?

**Trả lời:** Không. Browser sử dụng **front-channel**, backend sử dụng **back-channel**. Phải kiểm tra riêng DNS, route, proxy và TLS từ backend tới Token Endpoint.

**Câu 2.** Cấu hình `HTTPS_PROXY` và `NO_PROXY` ở container có đảm bảo mọi yêu cầu từ Spring Security OAuth2 Client đi đúng proxy không?

**Trả lời:** Không đảm bảo. HTTP client cụ thể có thể đọc biến môi trường, JVM properties hoặc cấu hình riêng. Discovery, token, JWKS, UserInfo và WebClient nghiệp vụ có thể dùng các client khác nhau.

**Câu 3.** Import CA nội bộ vào truststore có đủ khi Token Endpoint yêu cầu mTLS không?

**Trả lời:** Không. Truststore giúp xác minh **server certificate**; mTLS còn yêu cầu **client certificate/private key** được cấu hình ở HTTP client thực hiện kết nối.

**Câu 4.** Có thể đặt `issuer-uri` là một private IP hoặc tên backend nội bộ khác với `iss` trong ID Token chỉ để tránh proxy không?

**Trả lời:** Không. Issuer là định danh chuẩn cần được xác minh. Cần xử lý DNS/route hoặc công bố provider nhất quán, không làm suy yếu issuer validation.

**Câu 5.** HTTPS login callback bị chuyển thành HTTP hostname nội bộ, nên kiểm tra proxy nào?

**Trả lời:** Kiểm tra **reverse proxy/ingress** phía ứng dụng, forwarded headers, external base URL và redirect URI đăng ký. Egress proxy cho Token Endpoint không trực tiếp quyết định hostname của callback.

## 14. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — OAuth 2.0 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Boot Reference — Spring Security và cấu hình OAuth2 Client](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705)

**Ghi nhớ:** Khi provider nằm trong mạng nội bộ hoặc backend phải đi qua proxy, hãy vẽ rõ **ai kết nối đến endpoint nào**. Sau đó cấu hình đúng **DNS/route, TLS trust và client identity, proxy cho từng HTTP client, issuer nhất quán và redirect URI của ingress**. Mỗi lớp có trách nhiệm riêng và phải hoạt động đồng thời để một luồng OAuth2/OIDC an toàn thành công.
