# 15.5. OAuth2AuthorizedClientProviderBuilder và cấu hình grant cần dùng

## 1. Bài toán: ứng dụng lấy và làm mới token bằng cách nào?

Khi một ứng dụng Spring Security hoạt động với vai trò **OAuth 2.0/OIDC Client**, nó không chỉ cần biết Client ID, token endpoint hay authorization endpoint. Ứng dụng còn phải quyết định **khi nào được xin token, khi nào được làm mới token, grant nào được phép sử dụng và token được lưu ở đâu**.

Ví dụ, cùng một hệ thống có thể có ba nhu cầu:

1. Người dùng mở ứng dụng web và đăng nhập qua OpenID Provider bằng **Authorization Code Flow**.
2. Sau khi đăng nhập, ứng dụng gọi một API thay mặt người dùng. Khi access token hết hạn, Client có thể dùng **refresh token** đã được cấp để xin access token mới.
3. Một job nền chạy hằng đêm cần gọi API dịch vụ mà **không có người dùng tương tác**. Job dùng **Client Credentials Grant**.

Ba nhu cầu này khác nhau về nguồn danh tính, quyền được cấp, vòng đời token, cơ chế lưu trữ và điều kiện áp dụng grant. Viết một hàm tự chọn ngẫu nhiên token endpoint request rất dễ gây lỗi: gửi nhầm user token, cố refresh khi không có refresh token hoặc chạy Authorization Code Flow trong một job không có trình duyệt.

Spring Security tách trách nhiệm thành các abstraction:

- **<code>ClientRegistration</code>:** mô tả cấu hình đã đăng ký của một OAuth2 Client.
- **<code>OAuth2AuthorizedClient</code>:** liên kết ClientRegistration với principal và token đã được cấp.
- **<code>OAuth2AuthorizedClientProvider</code>:** thành phần biết cách thực hiện một hoặc nhiều **authorization grant** khi có điều kiện phù hợp.
- **<code>OAuth2AuthorizedClientProviderBuilder</code>:** builder dùng ghép các grant provider thường dùng vào một provider tổng hợp.
- **<code>OAuth2AuthorizedClientManager</code>:** điều phối đăng ký Client, authorized client hiện hành, provider và storage trong lúc gọi <code>authorize(...)</code>.
- **<code>OAuth2AuthorizedClientService</code> / <code>OAuth2AuthorizedClientRepository</code>:** lưu, tra cứu và xóa authorized client.

**Điểm cốt lõi của bài học:** <code>OAuth2AuthorizedClientProviderBuilder</code> giúp **khai báo những grant mà Client Manager được phép xử lý**, chứ không tự đăng ký Client với Authorization Server, không tự sinh ra End-User và không làm mọi grant hợp lệ với mọi ClientRegistration.

## 2. Vị trí của ProviderBuilder trong kiến trúc

~~~mermaid
flowchart TD
    C["Code ứng dụng / HTTP client"] --> M["OAuth2AuthorizedClientManager"]
    M --> R["ClientRegistrationRepository"]
    M --> S["Authorized Client Service / Repository"]
    M --> P["OAuth2AuthorizedClientProvider tổng hợp"]
    B["OAuth2AuthorizedClientProviderBuilder"] --> P
    P --> A["Authorization Code Provider"]
    P --> F["Refresh Token Provider"]
    P --> CC["Client Credentials Provider"]
    A --> AS["Authorization Server / OpenID Provider"]
    F --> AS
    CC --> AS
    AS --> T["Token response"]
    T --> P
    P --> M
    M --> S
    M --> O["OAuth2AuthorizedClient hiện hành"]
    O --> API["HTTP request tới Resource Server"]
~~~

Khi gọi <code>manager.authorize(request)</code>, manager tạo/ngữ cảnh hóa yêu cầu, tìm ClientRegistration và authorized client đã lưu, rồi đưa chúng tới provider được cấu hình. Provider áp dụng grant thích hợp nếu các điều kiện được đáp ứng.

Với một provider tổng hợp, các provider con được **thử theo thứ tự cấu hình**. Một provider không hỗ trợ ngữ cảnh hiện tại thường trả <code>null</code> để nhường bước cho provider tiếp theo. Nếu một provider thực sự gặp lỗi token endpoint hay authentication, exception cần được xử lý đúng; không giả định framework luôn bỏ qua lỗi để thử một grant kém an toàn hơn.

### 2.1. Bốn câu hỏi khác nhau

| Câu hỏi | Thành phần chịu trách nhiệm chính |
|---|---|
| Ứng dụng đã đăng ký Client ID, grant type và endpoint nào? | <code>ClientRegistration</code> |
| Đang có token nào, gắn với principal nào? | <code>OAuth2AuthorizedClient</code> |
| Grant nào có thể cấp hoặc làm mới token trong tình huống này? | <code>OAuth2AuthorizedClientProvider</code> |
| Cần tìm, cấp, làm mới, lưu hoặc xóa authorized client ra sao? | <code>OAuth2AuthorizedClientManager</code> phối hợp service/repository |

Không thay đổi <code>ClientRegistration.authorizationGrantType</code> bằng cách thêm <code>.clientCredentials()</code> vào builder. Hai cấp cấu hình phải đồng nhất: **registration xác định Client/loại grant**, còn **provider cho phép manager xử lý grant đó**.

## 3. Các grant provider thường dùng

<code>OAuth2AuthorizedClientProviderBuilder</code> trong Spring Security cung cấp cách ghép những provider phổ biến:

| Builder method | Grant/chức năng | Khi nào thích hợp? |
|---|---|---|
| <code>authorizationCode()</code> | Authorization Code Grant | Client đăng nhập người dùng qua browser hoặc đã có ngữ cảnh authorization code phù hợp |
| <code>refreshToken()</code> | Refresh Token Grant | Có authorized client với refresh token còn dùng được, access token cần được làm mới |
| <code>clientCredentials()</code> | Client Credentials Grant | Server-to-server/job nền không có End-User |
| <code>provider(customProvider)</code> | Provider tùy biến | Cần grant/điều kiện được framework/Authorization Server hỗ trợ qua extension rõ ràng |

Một số phiên bản Spring Security có thêm API hoặc provider cho những grant mở rộng, chẳng hạn JWT bearer hoặc token exchange. Những khả năng đó **phụ thuộc version**, tài liệu của Spring Security và hỗ trợ của Authorization Server. Bài học dùng ba provider nền tảng có tính ứng dụng rộng nhất.

Không dùng **Resource Owner Password Credentials Grant** làm lựa chọn mặc định cho ứng dụng mới. Grant này bị loại khỏi hướng đi OAuth 2.1 và không phù hợp mô hình đăng nhập hiện đại qua browser/OP; API hỗ trợ ở các bản Spring Security có thể thay đổi. **Implicit Grant** cũng không phải hướng đề xuất cho Client mới.

### 3.1. Authorization Code

Luồng sử dụng người dùng tương tác:

~~~text
Browser
  → /oauth2/authorization/company
  → Authorization Endpoint của OP
  → Người dùng xác thực/consent
  → /login/oauth2/code/company?code=...&state=...
  → Token Endpoint
  → Access token và ID Token nếu OIDC
~~~

Trong Spring Security Servlet, **<code>oauth2Login()</code> và các filter đăng nhập** thực hiện phần redirect/callback. Thêm <code>.authorizationCode()</code> vào ProviderBuilder **không tự tạo trang đăng nhập hoặc tự chuyển hướng một background job sang browser**.

Authorization Code Flow thường kết hợp **PKCE** theo mô hình Client và policy. Với OIDC, scope <code>openid</code> kích hoạt yêu cầu xác thực OIDC; <code>openid</code> là **scope**, không phải một <code>authorizationGrantType</code> riêng.

### 3.2. Refresh Token

Refresh token không phải loại đăng nhập thứ hai; nó là **cơ chế tiếp tục ủy quyền đã có**.

~~~text
Authorized Client hiện có
  ├─ Access token còn hợp lệ → có thể tiếp tục dùng
  ├─ Access token gần hết hạn + refresh token → thử refresh
  └─ Không có/không còn dùng được refresh token
       → không thể refresh bằng grant này
~~~

Khi refresh thành công, Client nhận token response mới và authorized client phải được cập nhật vào storage thích hợp. Nếu Authorization Server sử dụng **refresh token rotation**, token refresh mới phải thay thế bản cũ theo response.

Không giả định mọi Authorization Code Flow đều nhận refresh token; nhiều OP có chính sách riêng, đôi khi yêu cầu <code>offline_access</code> hoặc consent.

### 3.3. Client Credentials

Client Credentials thích hợp khi chính **ứng dụng/dịch vụ** được cấp quyền truy cập Resource Server:

~~~text
Batch worker / backend
  → POST /token
       grant_type=client_credentials
       client authentication của service
  ← access_token
  → Gọi API với access token của service
~~~

Grant này **không xác thực End-User** và không tạo phiên OIDC Login cho người dùng. Trong storage, manager vẫn cần một principal name để phân vùng authorized client; tên đó có thể là một chuỗi service ổn định, nhưng nó không biến token service thành token của một người dùng.

## 4. Cú pháp cơ bản của OAuth2AuthorizedClientProviderBuilder

### 4.1. Ghép ba provider phổ biến

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

Kết quả là một <code>OAuth2AuthorizedClientProvider</code> có thể xét những khả năng trên theo ngữ cảnh được truyền vào.

Nó **không** có nghĩa:

- Mọi registration đều tự động được phép dùng cả ba grant.
- Một registration kiểu authorization code tự động biến thành client credentials.
- Có thể bỏ qua client secret, redirect URI, PKCE hoặc consent.
- Không cần <code>OAuth2AuthorizedClientManager</code>.
- Mỗi lời gọi sẽ xin một access token mới.

Provider thường nhận ngữ cảnh chứa registration, authorized client hiện hành và các thuộc tính phù hợp. Chỉ provider có điều kiện phù hợp mới thực sự thực hiện grant; manager quyết định cách lưu/đọc kết quả.

### 4.2. Chỉ bật những provider cần thiết

Nếu worker chỉ dùng client credentials:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

Nếu web app dùng Authorization Code và làm mới token:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

Nếu một service chỉ có thể làm mới token đã được cấp trước:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .build();
~~~

Ví dụ cuối chỉ hữu ích khi storage **đã có authorized client và refresh token** hợp lệ; không có provider cấp token ban đầu thì manager không thể tạo authorization mới từ hư không.

**Nguyên tắc:** provider list phản ánh use case thực, không “bật hết cho tiện”. Dù bật provider không nhất thiết khiến một registration sử dụng sai grant ngay, cấu hình tối thiểu giúp hệ thống dễ hiểu và giảm nguy cơ sai khi thêm registration hoặc thay đổi token manager sau này.

### 4.3. ProviderBuilder và thứ tự ưu tiên

Builder thường ghép các provider con theo thứ tự gọi. Khi một provider trả <code>null</code> vì **không hỗ trợ ngữ cảnh** hoặc không cần xử lý, provider tổng hợp có thể thử provider kế.

Ví dụ cấu hình:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

Không nên xem danh sách này là một chuỗi “thử authorization code thất bại → tự chuyển sang client credentials”. Một lỗi token endpoint như <code>invalid_grant</code> không phải chỉ dấu để **hạ cấp** sang grant khác. Grant được dùng phụ thuộc ClientRegistration và điều kiện trong context, không phải thay thế tùy ý sau lỗi.

## 5. Cấu hình provider với clock skew

Access token có thời điểm hết hạn, nhưng đồng hồ giữa Client, Authorization Server và Resource Server có thể chênh lệch một lượng nhỏ. Spring Security hỗ trợ cấu hình **clock skew** cho các provider làm mới/cấp token.

Ví dụ chủ động refresh sớm:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken(refresh -> refresh
            .clockSkew(Duration.ofSeconds(60)))
        .clientCredentials(credentials -> credentials
            .clockSkew(Duration.ofSeconds(60)))
        .build();
~~~

Ở đây <code>Duration.ofSeconds(60)</code> là lựa chọn ví dụ, không phải một giá trị phải dùng cho mọi hệ thống. Khi token sắp hết hạn trong khoảng skew, provider có thể coi token cần được refresh/cấp lại để tránh token hết hạn giữa một HTTP request.

Cần hiểu:

- Clock skew không tăng thời hạn thật của access token.
- Không bảo đảm refresh token còn hiệu lực.
- Không thay thế đồng bộ đồng hồ hệ thống.
- Nếu skew quá lớn so với token lifetime, Client có thể yêu cầu token mới quá thường xuyên.
- Không đảm bảo an toàn tuyệt đối trước refresh race trên nhiều instance.

Với hệ thống có token lifetime rất ngắn, nên điều chỉnh skew và chính sách retry dựa trên đặc điểm của Authorization Server, độ trễ mạng và khả năng xử lý đồng thời.

## 6. Ví dụ hoàn chỉnh A: web app OIDC dùng authorization code và refresh token

Đây là use case **người dùng đăng nhập qua trình duyệt**, ứng dụng cần access token để gọi API thay mặt họ.

### 6.1. Dependency Spring Boot

Ví dụ ứng dụng Servlet sử dụng Spring Boot 3 và Spring Security 6:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 6.2. ClientRegistration cho OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Issuer, Client ID, secret, scope và URL ở đây chỉ là dữ liệu minh họa. <code>api.read</code> phải được provider hỗ trợ, và API đích phải chấp nhận token có audience/phạm vi phù hợp. Không lưu secret thật trong source code.

### 6.3. SecurityFilterChain cho OAuth2 Login

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

<code>oauth2Login()</code> cài đặt phần đăng nhập trình duyệt: authorization request, redirect, callback, token exchange và OIDC authentication. <code>oauth2Client()</code> cung cấp hỗ trợ OAuth2 Client cần thiết khi ứng dụng dùng authorized client để gọi downstream API trong Servlet.

**Lưu ý:** Với ứng dụng chỉ cần login, không phải lúc nào cũng cần bật <code>oauth2Client()</code>. Thêm nó khi use case thực sự cần các chức năng OAuth2 Client trong request processing.

### 6.4. Tạo provider cho web Authorized Client Manager

Nếu cần tự cấu hình grant providers cho web request, có thể tạo manager tường minh:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class WebAuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Đây là ví dụ **cấu hình riêng** để minh họa ProviderBuilder. Spring Security/Spring Boot có thể đã cung cấp manager, service hoặc repository phù hợp trong nhiều trường hợp, nên **không cần tạo custom manager chỉ để bật cấu hình mặc định**.

Nếu ứng dụng có nhiều bean <code>OAuth2AuthorizedClientManager</code>, phải chọn đúng bean bằng tên/qualifier và bảo đảm HTTP client thực sự được gắn với manager mong muốn. Không tạo nhiều bean cùng kiểu không có cơ chế phân giải rõ ràng.

Quan trọng: cấu hình <code>.authorizationCode()</code> trong manager **không thay thế** OAuth2 Login filters. Người dùng vẫn bắt đầu flow thông qua đường dẫn như:

~~~text
/oauth2/authorization/company
~~~

Sau callback:

~~~text
/login/oauth2/code/company
~~~

Spring Security lưu authorized client khi authorization code được đổi token thành công. Khi cần gọi API, manager dùng authorized client hiện có và <code>refreshToken()</code> provider nếu điều kiện refresh được đáp ứng.

### 6.5. Lấy authorized client từ Controller

~~~java
package example.web;

import java.util.Map;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientInfoController {

    @GetMapping("/my/authorized-client")
    public Map<String, Object> info(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient client) {

        return Map.of(
            "registrationId",
            client.getClientRegistration().getRegistrationId(),
            "hasRefreshToken",
            client.getRefreshToken() != null,
            "hasAccessToken",
            client.getAccessToken() != null
        );
    }
}
~~~

Endpoint chỉ trả metadata, **không trả access token/refresh token**. Ví dụ này giả định authorized client được resolve thành công; với ứng dụng thật, cần xử lý authorization failure/không tìm thấy authorized client theo thiết kế UI/API.

Annotation <code>@RegisteredOAuth2AuthorizedClient</code> giúp resolve authorized client theo registration ID và principal trong ngữ cảnh Servlet. Nó không cho phép ứng dụng bỏ qua authorization, scope/audience hay chính sách Resource Server.

### 6.6. Các bước vận hành token sau login

~~~text
Người dùng login qua Authorization Code
    → Client có OAuth2AuthorizedClient
        → Access token còn hạn
            → Gọi API đúng audience/scope
        → Access token gần hết hạn và có refresh token
            → refreshToken() provider xin token mới
            → Lưu authorized client cập nhật
        → Refresh không thành công / không có refresh token
            → Policy yêu cầu authorize lại hoặc trả lỗi phù hợp
~~~

Đừng suy ra scope <code>openid</code> có nghĩa access token dùng được cho API nghiệp vụ. OIDC chứng minh authentication cho Client; quyền gọi Resource Server là vấn đề khác.

## 7. Ví dụ hoàn chỉnh B: background job chỉ cần client_credentials

Một job nền dùng service credential để lấy dữ liệu tổng hợp. Nó không có browser, HTTP session, OIDC Login callback hoặc End-User đang tương tác.

### 7.1. Registration cho service

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          nightly-reports:
            provider: service-auth
            client-id: reports-worker
            client-secret: ${REPORTS_WORKER_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          service-auth:
            token-uri: https://auth.example.org/oauth2/token
~~~

Client phải được Authorization Server cho phép <code>client_credentials</code>; scope <code>reports.read</code> cũng phải hợp lệ. Grant không dùng redirect URI hay authorization endpoint trong luồng chuẩn.

### 7.2. Manager không cần HTTP request

Với job, sử dụng <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> kết hợp <code>OAuth2AuthorizedClientService</code>:

~~~java
package example.security;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundClientManagerConfig {

    @Bean("reportsAuthorizedClientManager")
    OAuth2AuthorizedClientManager reportsAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(configurer -> configurer
                    .clockSkew(Duration.ofSeconds(30)))
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Khác biệt với web manager:

- Không cần <code>HttpServletRequest</code>/<code>HttpServletResponse</code>.
- Có thể chạy trong scheduled job hoặc service layer không có browser.
- Dùng storage service để giữ authorized client theo registration/principal.
- Chỉ kích hoạt **<code>clientCredentials()</code>**, không thêm authorization code/refresh token khi use case không cần.

### 7.3. Gọi manager từ service

~~~java
package example.jobs;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class ReportsTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public ReportsTokenService(
            @Qualifier("reportsAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String accessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("nightly-reports")
                .principal("reports-worker-runtime")
                .build();

        OAuth2AuthorizedClient authorizedClient = manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Reports client could not be authorized");
        }
        return authorizedClient.getAccessToken().getTokenValue();
    }
}
~~~

<code>reports-worker-runtime</code> là **principal tổng hợp**, đóng vai trò khóa lưu authorized client cho job. Nó không phải tài khoản người dùng của OIDC.

Trả <code>String</code> token ở đây chỉ để minh họa cách nhận credential ở server-side service; **không expose method này qua controller** và không ghi token vào log. Trong ứng dụng thật nên tích hợp manager vào HTTP client/interceptor phù hợp để tránh token đi qua nhiều tầng code không cần thiết.

### 7.4. Vì sao không có refreshToken()?

Client Credentials Grant thường có thể lấy token mới bằng chính <code>grant_type=client_credentials</code> khi access token cũ hết hạn. Nhiều Authorization Server không cấp refresh token cho grant này.

Vì vậy một manager chỉ bật <code>clientCredentials()</code> là đủ cho tình huống phổ biến. Nếu provider đặc biệt có cơ chế riêng, phải theo tài liệu/chuẩn được hỗ trợ, không tự suy diễn rằng refresh token luôn cần thiết.

## 8. Ví dụ C: một ứng dụng vừa có web login vừa có service-to-service

Trong hệ thống lớn, có thể tồn tại cả hai kiểu ClientRegistration:

~~~text
company-login:
  grant = authorization_code
  mục tiêu = đăng nhập người dùng và gọi API thay mặt user

reports-job:
  grant = client_credentials
  mục tiêu = backend gọi API theo quyền của service
~~~

Có hai chiến lược:

**Chiến lược 1 — Dùng các manager riêng theo ngữ cảnh.** Web manager bật authorization code + refresh token, service manager bật client credentials. Cách này làm rõ ranh giới và dễ quản lý storage/lifecycle.

**Chiến lược 2 — Dùng một provider tổng hợp chứa nhiều grant.** Có thể phù hợp nếu manager/ngữ cảnh thực sự hỗ trợ tất cả registration cần dùng. Tuy nhiên, một manager dựa trên Servlet request không phù hợp trực tiếp cho background job không có request, ngay cả khi provider list chứa <code>clientCredentials()</code>.

Ví dụ hai manager với bean name rõ:

~~~java
@Bean("webAuthorizedClientManager")
OAuth2AuthorizedClientManager webManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository repository) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

    var manager = new DefaultOAuth2AuthorizedClientManager(
        registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}

@Bean("serviceAuthorizedClientManager")
OAuth2AuthorizedClientManager serviceManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService service) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Đây là **đoạn cấu hình thay thế** các bean manager ở mục trước. Khi đưa vào một class thật, bổ sung import từ các ví dụ tương ứng. Không khai báo tất cả những ví dụ trong bài vào cùng project để tránh bean duplication/ambiguity.

Khi inject manager phải dùng <code>@Qualifier</code> hoặc cơ chế lựa chọn rõ ràng:

~~~java
public SomeService(
    @Qualifier("serviceAuthorizedClientManager")
    OAuth2AuthorizedClientManager manager) {
    this.manager = manager;
}
~~~

Đừng vì sự tiện lợi mà gắn user token vào một job đang cần service token hoặc dùng client credentials token thay cho quyền của End-User.

## 9. Những gì OAuth2AuthorizedClientProviderBuilder không tự làm

### 9.1. Không tạo ClientRegistration

Để dùng grant, ứng dụng vẫn cần ClientRegistrationRepository chứa registration tương ứng. Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-job:
            client-id: example-client-id
            client-secret: ${REPORTS_SECRET}
            authorization-grant-type: client_credentials
            provider: service-auth
        provider:
          service-auth:
            token-uri: https://auth.example.org/token
~~~

Thêm <code>.clientCredentials()</code> vào ProviderBuilder không tự sinh registration <code>reports-job</code>, cũng không đăng ký Client với Authorization Server.

### 9.2. Không tự khởi động OAuth2 Login trong trình duyệt

Authorization Code cần frontend redirect, state/correlation, PKCE khi áp dụng và callback. Trong Servlet, những trách nhiệm này do cấu hình OAuth2 Login/Client filters đảm nhiệm. Nếu chỉ gọi <code>manager.authorize()</code> từ một method không có browser, bạn không thể mong manager mở một trang IdP.

### 9.3. Không tự biến expired token thành valid token

Làm mới token phụ thuộc vào:

- Grant phù hợp và provider đã được bật.
- Authorized client và token hiện hành có sẵn trong storage.
- Refresh token hợp lệ nếu dùng refresh grant.
- Authorization Server chấp nhận request.
- Manager lưu trạng thái token mới theo cấu hình.

Chỉ thêm <code>.refreshToken()</code> không bảo đảm mọi token đều refresh được.

### 9.4. Không cấp quyền gọi bất kỳ API nào

Provider nhận token từ Authorization Server, nhưng Resource Server vẫn phải kiểm tra audience, scope, issuer, expiration và authorization nghiệp vụ. Không coi token do manager trả về là bằng chứng người dùng có quyền với mọi endpoint.

### 9.5. Không thay thế storage và principal isolation

Provider biết cách xin token, không phải kho lưu token. Nếu manager sử dụng storage không phù hợp, hoặc principal name bị trùng giữa tenant, token vẫn có thể bị lẫn.

## 10. Quan hệ với OAuth2AuthorizeRequest và context attributes

Khi gọi manager, code thường tạo:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("nightly-reports")
        .principal("reports-worker-runtime")
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);
~~~

Các thông tin quan trọng:

| Thành phần | Chức năng |
|---|---|
| <code>clientRegistrationId</code> | Chọn ClientRegistration, từ đó biết grant type và token endpoint |
| <code>principal</code> | Phân biệt ngữ cảnh authorized client |
| Existing authorized client | Cung cấp token hiện hành để kiểm tra hết hạn/refresh |
| Attributes/context | Dữ liệu bổ sung khi một grant/extension cụ thể yêu cầu |

<code>OAuth2AuthorizeRequest</code> còn có thể mang thuộc tính bổ sung tùy API/version. Manager có cơ chế tạo <code>OAuth2AuthorizationContext</code> và ánh xạ các thuộc tính phù hợp. Điều này đặc biệt quan trọng khi dùng custom provider hoặc grant đặc thù.

**Đối với ba grant trong bài, không nên tự phát minh những attribute không được Spring Security hoặc provider quy định.** Với client credentials, thông thường đủ registration ID và principal tổng hợp; với refresh, cần authorized client chứa refresh token; với authorization code Servlet, browser flow được xử lý bởi filters.

### 10.1. Principal tổng hợp không nên phụ thuộc input không đáng tin

Mẫu hợp lý:

~~~java
.principal("reports-worker-runtime")
~~~

Mẫu nguy hiểm:

~~~java
.principal(request.getParameter("user"))
~~~

Nếu token storage dùng principal name làm khóa, cho browser tự chọn principal có thể dẫn đến truy cập authorized client không thuộc caller. Với End-User, phải dùng Authentication đã xác thực; với service, dùng principal key do backend kiểm soát.

### 10.2. Multi-tenant có thể cần tách registration

Giả sử cùng một backend phục vụ hai tenant:

~~~text
tenant-a → client ID A, scopes A, token A
tenant-b → client ID B, scopes B, token B
~~~

Nếu credential, issuer hoặc audience khác nhau, cần ClientRegistration riêng hoặc một chiến lược registration động được thiết kế kỹ. Không chỉ đổi principal name và hy vọng ClientRegistration sai vẫn phát token đúng tenant.

Principal name cũng phải có namespace để authorized client của hai tenant không bị ghi đè nếu cùng dùng một storage.

## 11. Tùy biến các provider hoặc sử dụng provider riêng

Đối với nhu cầu thông thường, builder với các method có sẵn là đủ. Nếu Authorization Server có grant extension đã được Spring Security phiên bản đó hỗ trợ, hoặc dự án có một <code>OAuth2AuthorizedClientProvider</code> tùy biến, có thể ghép nó vào provider tổng hợp.

Mô hình:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .clientCredentials()
        .provider(customProvider)
        .build();
~~~

Ở đây <code>customProvider</code> là một instance implements <code>OAuth2AuthorizedClientProvider</code> đã được định nghĩa và kiểm soát riêng; đoạn code chỉ minh họa **điểm mở rộng**, chưa tạo custom provider. Chỉ thêm extension khi grant tương ứng đã được Authorization Server hỗ trợ và có quy tắc bảo mật rõ ràng.

### 11.1. Hợp đồng OAuth2AuthorizedClientProvider

Interface cốt lõi:

~~~java
public interface OAuth2AuthorizedClientProvider {
    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context);
}
~~~

Ý nghĩa:

- Trả về <code>OAuth2AuthorizedClient</code> khi provider đã thực hiện authorization/reauthorization hoặc tạo ra kết quả phù hợp.
- Trả về <code>null</code> khi không hỗ trợ grant/ngữ cảnh hoặc không cần/có khả năng reauthorize theo hợp đồng.
- Ném exception phù hợp khi quá trình thực hiện grant thực sự thất bại.

Một provider tùy biến phải tôn trọng những điều kiện này. Không tạo token giả khi Authorization Server từ chối; không bắt mọi lỗi rồi trả <code>null</code> để provider khác cấp token theo một grant yếu hơn.

### 11.2. Khi nào cần custom provider?

Các ví dụ có thể gồm:

- Một grant extension do Spring Security phiên bản hiện tại không tích hợp sẵn.
- Hành vi đặc thù được Authorization Server và Client cùng hỗ trợ theo chuẩn/extension.
- Cần lấy credential hoặc context attributes bằng cơ chế đã được định nghĩa an toàn.

Không dùng custom provider để bỏ qua OIDC validation, thay thế Authorization Code callback bằng code tự chế, hay cho Client lấy token với principal do browser tự khai. Với các yêu cầu như HTTP header đặc biệt hoặc body token response riêng, đôi khi **tùy biến token response client** sẽ thích hợp hơn là viết hẳn provider mới.

## 12. Token storage và authorization success/failure

### 12.1. Manager lưu kết quả như thế nào?

Khi provider cấp token mới hoặc refresh thành công, manager thường sử dụng success handler để lưu <code>OAuth2AuthorizedClient</code> mới:

~~~text
OAuth2AuthorizedClientManager
  → OAuth2AuthorizedClientProvider.authorize(context)
  → OAuth2AuthorizedClient mới
  → AuthorizationSuccessHandler
  → OAuth2AuthorizedClientService hoặc Repository
~~~

Trong các manager mặc định, Spring Security thiết lập handler lưu authorized client phù hợp với kiểu manager. Nếu ứng dụng ghi đè success handler, cần bảo đảm hành vi lưu kết quả vẫn được thực hiện khi cần, thay vì vô tình khiến token mới chỉ tồn tại trong biến trả về của một request.

### 12.2. Failure handler và invalid_grant

Khi refresh token bị từ chối, Token Endpoint có thể trả <code>invalid_grant</code> do token hết hạn, bị thu hồi hoặc đã được sử dụng theo cơ chế rotation.

Manager mặc định có cơ chế failure handling có thể xóa authorized client không còn hợp lệ với một số mã lỗi (chẳng hạn <code>invalid_grant</code>), tùy manager/cấu hình. Việc xóa này giúp tránh lặp lại refresh với token không còn dùng được.

Không nên bắt mọi <code>OAuth2AuthorizationException</code> rồi xóa tất cả authorized clients. Timeout, HTTP 502 hoặc lỗi kết nối không nhất thiết chứng minh refresh token đã bị thu hồi; phân loại sai có thể làm gián đoạn phiên người dùng không cần thiết.

### 12.3. Khác biệt giữa Service và Repository

| Thành phần | Phương thức tra cứu chính | Thường dùng ở đâu |
|---|---|---|
| <code>OAuth2AuthorizedClientService</code> | registration ID + principal name | Backend service, background manager |
| <code>OAuth2AuthorizedClientRepository</code> | registration ID + Authentication + HTTP request | Servlet web request |
| <code>InMemoryOAuth2AuthorizedClientService</code> | Token trong memory của một tiến trình | Demo, local, single-instance |
| <code>JdbcOAuth2AuthorizedClientService</code> | Token trong database theo schema phù hợp | Ứng dụng cần persistence |

Không nhầm <code>OAuth2AuthorizedClientService</code> với <code>ClientRegistrationRepository</code>, cũng không nhầm với <code>HttpSessionOAuth2AuthorizationRequestRepository</code> lưu state/PKCE **trước callback**.

### 12.4. Logout và revocation là những việc khác nhau

Logout HTTP session, xóa authorized client khỏi service và thu hồi token tại Authorization Server không tự động tương đương nhau. Một refresh token vẫn có thể nằm trong persistent storage sau khi user logout nếu ứng dụng không có cleanup policy.

Khi cần thu hồi:

- Xóa authorized client local đúng registration và principal.
- Gọi token revocation endpoint nếu provider hỗ trợ và chính sách yêu cầu.
- Vô hiệu hóa session/SecurityContext thích hợp.
- Đánh giá quyền tại Resource Server hoặc domain service khi quyền có thể bị thu hồi ngoài vòng đời token.

## 13. Những bẫy thường gặp khi cấu hình grant

### 13.1. Bật clientCredentials nhưng registration là authorization_code

~~~yaml
registration:
  company:
    authorization-grant-type: authorization_code
~~~

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

Manager không thể dùng provider client credentials để thực hiện một authorization code flow đúng nghĩa cho registration này. Phải bật grant provider phù hợp với registration và use case. Với web login, Authorization Code Flow còn cần filters/redirect/callback tương ứng.

### 13.2. Chỉ bật refreshToken khi chưa có authorized client

Refresh token provider cần một authorized client **đã có refresh token**. Nếu chưa từng authorize và không có token nào được lưu, nó không thể tạo refresh token từ Client ID/secret.

### 13.3. Dùng DefaultOAuth2AuthorizedClientManager trong job nền

Web manager dựa trên ngữ cảnh Servlet. Trong scheduled job không có HttpServletRequest, nên chọn <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>. Chỉ việc thêm <code>clientCredentials()</code> vào web manager không xóa phụ thuộc vào Servlet request của manager đó.

### 13.4. Tưởng OAuth2AuthorizedClientProviderBuilder là ClientRegistration builder

Hai API khác nhau:

~~~java
ClientRegistration.withRegistrationId("company")
// mô tả thông tin Client đã đăng ký

OAuth2AuthorizedClientProviderBuilder.builder()
// tạo provider xử lý authorization grant
~~~

Không dùng builder grant để cấu hình issuer URI, redirect URI hoặc client secret. Những dữ liệu đó thuộc ClientRegistration.

### 13.5. Dùng refresh grant cho client credentials không cần thiết

Client credentials thường xin token mới khi cần, không dựa vào refresh token. Nếu provider không cấp refresh token, thêm <code>refreshToken()</code> không mang lại lợi ích và có thể gây hiểu nhầm về flow.

### 13.6. Dùng token của người dùng làm token cho service

Access token từ OIDC Login có thể được cấp cho UserInfo hoặc API theo scope/audience của user. Không mặc định gửi token đó tới internal service nếu API này yêu cầu **service credential**. Khi cần hành động thay mặt user, thiết kế ủy quyền theo audience/delegation được OP và API hỗ trợ.

### 13.7. Bỏ qua token refresh concurrency

Nếu hai request trên hai node cùng refresh một token và OP bật refresh token rotation, một request có thể làm request kia thất bại với <code>invalid_grant</code>. Cần chiến lược persistence/concurrency/handling phù hợp; lock chỉ trong một JVM không đủ cho cluster.

### 13.8. Tự retry token request một cách mù quáng

Authorization Code có thể chỉ dùng được một lần. Nếu token endpoint timeout sau khi server đã nhận request, Client không biết code đã bị tiêu thụ chưa. Không tự động retry vô hạn giống một GET idempotent thông thường; phân loại lỗi và bắt đầu lại authorization flow khi cần.

## 14. Bảo mật khi chọn grant và dùng token

### 14.1. Nguyên tắc cấp quyền tối thiểu

Mỗi ClientRegistration nên chỉ yêu cầu scopes cần thiết cho workload:

~~~text
web-login:
    openid, profile, api.read

reports-job:
    reports.read

billing-job:
    billing.write (chỉ khi thực sự cần)
~~~

Không dùng một confidential client có scope cực rộng cho cả đăng nhập người dùng lẫn các job đặc quyền chỉ vì muốn giảm số registration.

### 14.2. Phân cách End-User và service

| Tình huống | Grant thường phù hợp | Ai được đại diện? |
|---|---|---|
| Người dùng đăng nhập OIDC | Authorization Code + PKCE theo cấu hình | End-User |
| Gọi API thay mặt user đã cấp quyền | Authorized client từ login, refresh nếu có | End-User |
| Worker gọi API theo quyền dịch vụ | Client Credentials | Client/service |
| User phải đăng nhập lại vì refresh không còn hợp lệ | Authorization Code Flow mới | End-User |

Client Credentials **không cho phép service tự giả làm một người dùng cụ thể** chỉ vì đã có một <code>principalName</code> trong <code>OAuth2AuthorizeRequest</code>.

### 14.3. Bảo vệ credential và token

- Không commit <code>client-secret</code> vào source; dùng secret store hoặc biến môi trường.
- Chỉ gửi token request qua HTTPS có xác minh TLS.
- Không ghi access token, refresh token, client secret, authorization code, PKCE verifier hay HTTP Authorization header vào log.
- Không trả access/refresh token cho browser khi backend đóng vai confidential Client.
- Bảo vệ token storage bằng quyền tối thiểu, encryption-at-rest và audit thích hợp.
- Lập chính sách cleanup/revocation khi user logout, tài khoản bị khóa hoặc service bị thu hồi quyền.

### 14.4. Kiểm tra audience và scope

<code>OAuth2AuthorizedClient</code> chứa token mà Client đã được cấp; không chứng minh API nào cũng chấp nhận token đó. Resource Server phải xác minh đúng issuer, audience, expiration, scope và các điều kiện authorization nội bộ.

### 14.5. Multi-tenant và principal isolation

Khi nhiều tenant dùng chung storage, tránh:

~~~text
tenant-a principal=service
tenant-b principal=service
same registrationId
~~~

Nếu hai workload phải giữ token riêng, nên có registration hoặc principal namespace phù hợp, tùy grant và kiến trúc. Không dùng tenant ID do browser tự khai để chọn token đặc quyền. Quy tắc chọn tenant phải dựa vào authentication và policy tin cậy.

## 15. Sự cố thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| <code>manager.authorize()</code> trả null hoặc không cấp được token | Grant provider không hỗ trợ registration/context, thiếu authorized client hoặc request không phù hợp | Kiểm tra registration grant type, principal, provider list và flow |
| Đã bật <code>authorizationCode()</code> nhưng job không đăng nhập được | Không có browser/redirect/callback | Dùng client credentials cho job không có End-User |
| Web login thành công nhưng refresh không xảy ra | Không có refresh token, provider không bật hoặc token chưa đủ gần expiry | Kiểm tra refresh token, clock skew và manager được sử dụng |
| <code>invalid_client</code> tại Token Endpoint | Client ID/secret hoặc authentication method sai | Đối chiếu cấu hình với Authorization Server |
| <code>unauthorized_client</code> | Client chưa được phép dùng grant | Bật grant tương ứng phía Authorization Server |
| <code>unsupported_grant_type</code> | Provider không hỗ trợ grant hoặc request sai | Kiểm tra registration và OP metadata/docs |
| <code>invalid_scope</code> | Scope chưa được cấp hoặc không phù hợp grant | Điều chỉnh scopes và policy |
| <code>invalid_grant</code> khi refresh | Refresh token hết hạn, thu hồi hoặc bị dùng lại | Kiểm tra rotation, cleanup và reauthorization |
| Access token vẫn bị API trả 401 | Sai audience/issuer, hết hạn hoặc revoked | Kiểm tra Resource Server và token thực tế |
| Job chạy được ở dev nhưng lỗi trên multi-node | Storage in-memory không chia sẻ hoặc refresh race | Thiết kế persistent store và concurrency |
| Hai manager bean gây ambiguity | Chưa dùng <code>@Qualifier</code>/primary phù hợp | Đặt tên rõ và inject đúng manager |
| Sau khi tự set success handler, token refresh không được lưu | Custom handler không save authorized client | Duy trì persistence logic |
| Logout nhưng refresh token còn trong DB | Chưa có cleanup/revocation policy | Xóa local authorized client, thu hồi token nếu cần |
| Service A dùng token của service B | Principal/registration key không tách workload | Phân vùng token theo registration/principal/tenant |

### 15.1. Quy trình tìm nguyên nhân

~~~text
ClientRegistration có tồn tại?
    |
    v
authorizationGrantType có phù hợp use case?
    |
    v
OAuth2AuthorizeRequest có đúng principal/context?
    |
    v
Manager nào đang được sử dụng (web/service)?
    |
    v
ProviderBuilder đã bật grant tương ứng?
    |
    v
Storage có authorized client/refresh token phù hợp?
    |
    v
Token Endpoint có chấp nhận Client và grant?
    |
    v
Manager có lưu authorized client cập nhật?
    |
    v
Resource Server có chấp nhận audience/scope không?
~~~

Khi debug, có thể bật log có kiểm soát trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.security.oauth2.client: DEBUG
~~~

Mức log có thể thay đổi theo phiên bản. Không bật dump raw token request/response trong production; cần lọc token, secret và Authorization header khỏi log/telemetry.

## 16. Bài tập và tình huống

### Bài 1 — Chọn provider cho job nền

Một batch job chạy mỗi đêm, không có HTTP request hoặc người dùng. ClientRegistration có <code>authorization-grant-type=client_credentials</code>.

**Câu hỏi:** Nên bật những provider nào và dùng manager nào?

**Gợi ý:** <code>clientCredentials()</code> và <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>; principal tổng hợp ổn định, có namespace nếu phải tách tenant/workload.

### Bài 2 — Web login và refresh

Ứng dụng Servlet dùng OIDC Authorization Code Flow và lưu authorized client. OP có thể cấp refresh token.

**Câu hỏi:** Cấu hình provider list hợp lý?

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

**Giải thích:** <code>oauth2Login()</code> xử lý redirect/callback; manager có khả năng làm mới token khi đã có refresh token hợp lệ. Không mặc định có refresh token trong mọi trường hợp.

### Bài 3 — Sai grant

Registration <code>company</code> có <code>authorization_code</code>, nhưng manager chỉ có <code>clientCredentials()</code>.

**Hỏi:** Liệu Client Credentials Provider có tự chọn authorization code grant không?

**Đáp án:** Không. Phải dùng provider phù hợp grant, và với login cần browser flow. Builder không thay đổi ClientRegistration.

### Bài 4 — Refresh không có token

Một manager chỉ bật <code>refreshToken()</code> được gọi lần đầu cho registration chưa từng authorize.

**Đáp án:** Không có refresh token để thực hiện grant; cần một flow cấp token ban đầu phù hợp, sau đó mới có thể refresh nếu server cấp refresh token.

### Bài 5 — Access token của user và service

Người dùng đã OIDC Login, đồng thời worker chạy client credentials. Một lập trình viên dùng cùng principal name <code>default</code> cho cả hai, lưu vào một bộ nhớ token tự viết keyed by principal.

**Hỏi:** Thiết kế có an toàn không?

**Đáp án:** Không. Token có thể bị ghi đè hoặc nhầm ngữ cảnh, nhất là khi bỏ registration ID. Cần storage đúng abstraction, phân vùng registration/principal và tách biệt user token với service token.

### Bài 6 — Refresh token rotation

Hai node cùng đọc refresh token cũ và cố refresh đồng thời; node thứ hai nhận <code>invalid_grant</code>.

**Hỏi:** Có thể do đâu và cần làm gì?

**Đáp án:** Có thể OP đang sử dụng refresh token rotation. Cần chiến lược storage/concurrency phù hợp với multi-node, xử lý failure an toàn và không retry vô hạn token cũ.

### Bài 7 — Đọc và giải thích một provider configuration

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

**Hỏi:** Cấu hình này có thể làm gì, không thể làm gì?

**Đáp án:** Có thể refresh một authorized client đã có refresh token, hoặc cấp client credentials token cho registration phù hợp. Nó không tự bắt đầu OIDC Authorization Code Login trong browser vì không bật authorization code provider và cũng không cấu hình OAuth2 Login filters.

### Bài 8 — Thực hành có kiểm soát

1. Tạo registration <code>nightly-reports</code> dùng client credentials và scope chỉ đọc.
2. Tạo <code>OAuth2AuthorizedClientService</code> cho môi trường thử nghiệm.
3. Tạo <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> với <code>clientCredentials()</code>.
4. Gọi manager bằng <code>OAuth2AuthorizeRequest.withClientRegistrationId(...).principal(...)</code>.
5. Quan sát có authorized client, registration ID, principal và expiry hay không; **không in token value**.
6. Gọi manager lần tiếp theo để hiểu việc tái sử dụng token còn hạn và cấp lại token khi gần expiry theo provider.
7. Tách thêm một registration OIDC Login; phân biệt manager web và manager service.
8. Mô tả các nguyên nhân khiến manager không thể authorize khi secret, grant type, scope hoặc token endpoint sai.

## 17. Ghi nhớ

- **<code>OAuth2AuthorizedClientProviderBuilder</code>** tạo một provider tổng hợp từ những grant mà <code>OAuth2AuthorizedClientManager</code> được phép xử lý.
- **<code>authorizationCode()</code>** phục vụ grant có End-User và browser flow; trong Servlet, <code>oauth2Login()</code> vẫn chịu trách nhiệm redirect/callback, state và OIDC authentication.
- **<code>refreshToken()</code>** chỉ làm mới khi đã có authorized client với refresh token hợp lệ và điều kiện refresh phù hợp; không tự cấp refresh token.
- **<code>clientCredentials()</code>** dành cho server-to-server không có End-User; thường phù hợp với <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>.
- Provider list phải phù hợp với **ClientRegistration.authorizationGrantType**, manager được chọn và chính sách của Authorization Server. Bật thêm provider không biến một registration thành grant khác.
- **<code>DefaultOAuth2AuthorizedClientManager</code>** phù hợp ngữ cảnh Servlet; **<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>** phù hợp job/service không cần HTTP request.
- Storage, refresh policy, principal key, audience/scope và token revocation là các trách nhiệm **riêng** của kiến trúc; ProviderBuilder không tự giải quyết.
- Cấu hình tối thiểu theo use case, giữ credential an toàn và không đánh đồng token của service với token đại diện cho người dùng.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClientManager</code>, <code>OAuth2AuthorizedClientProvider</code>, <code>OAuth2AuthorizedClientProviderBuilder</code>, các built-in providers.
- **Spring Security Reference — OAuth2 Login (Servlet):** Authorization Code Flow, callbacks và authorized client persistence.
- **Spring Security Java API:** <code>OAuth2AuthorizedClientProviderBuilder</code>, <code>DefaultOAuth2AuthorizedClientManager</code>, <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>, <code>OAuth2AuthorizeRequest</code>.
- **Spring Security Java API:** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, <code>OAuth2AuthorizedClientProvider</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Client Credentials và Refresh Token grants.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** Authorization Code Flow và PKCE.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token.
- **OpenID Connect Core 1.0:** OIDC Authorization Code Flow, ID Token và UserInfo.
