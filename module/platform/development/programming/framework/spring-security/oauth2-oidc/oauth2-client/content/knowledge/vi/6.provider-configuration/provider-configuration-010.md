# 6.10. Khởi động ứng dụng khi discovery hoặc JWKS không khả dụng

## 1. Vấn đề thực tế: Identity Provider gặp sự cố thì ứng dụng có khởi động được không?

Trong ứng dụng Spring Security OAuth 2.0/OIDC Client, ta thường cấu hình một **OpenID Provider (OP)** hoặc **Authorization Server** bên ngoài để người dùng đăng nhập. Provider đó có thể phát hành **Discovery Document** (metadata về issuer và các endpoint) và **JWKS** (JSON Web Key Set, thường chứa khóa công khai để xác minh chữ ký ID Token).

Điều gì xảy ra nếu ứng dụng triển khai lúc nhà cung cấp đăng nhập đang mất kết nối, DNS lỗi hoặc endpoint JWKS trả HTTP 503? Câu trả lời phụ thuộc vào **thời điểm Spring Security cần truy cập từng endpoint** và **cách ClientRegistration được tạo**.

Phân biệt hai loại phụ thuộc:

1. **Discovery dependency:** ứng dụng cần lấy metadata để dựng cấu hình OAuth2/OIDC Client. Với cấu hình dựa trên <code>issuer-uri</code>, thao tác này thường xảy ra khi khởi tạo <code>ClientRegistrationRepository</code> trong lúc ứng dụng bắt đầu chạy.
2. **JWKS dependency:** ứng dụng cần khóa xác minh chữ ký ID Token. Với cấu hình OAuth2 Login/OIDC thông thường, khóa thường được tải khi cần xác minh token trong một lần đăng nhập, không nhất thiết tại thời điểm khởi động.

Vì vậy, **discovery lỗi có thể làm ứng dụng không khởi động được**, còn **JWKS lỗi có thể chỉ làm đăng nhập OIDC thất bại** dù HTTP server và các endpoint khác vẫn đang hoạt động. Đây là hành vi điển hình, không phải cam kết cho mọi phiên bản hoặc mọi cấu hình tùy biến.

> **Mấu chốt:** Hãy xác định *khi nào* ứng dụng gọi Discovery Document và *khi nào* nó tải JWKS. Đừng gộp hai lỗi vào một kết luận “IdP chết thì app không start”.

## 2. Vai trò của Discovery và JWKS trong OIDC Client

### 2.1. Discovery Document

OpenID Connect Discovery cho Client biết metadata của OP. Ví dụ với issuer:

~~~text
https://login.example.org/realms/company
~~~

OIDC Discovery Document thường được công bố tại:

~~~text
https://login.example.org/realms/company/.well-known/openid-configuration
~~~

Một response JSON rút gọn:

~~~json
{
  "issuer": "https://login.example.org/realms/company",
  "authorization_endpoint": "https://login.example.org/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.org/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.org/realms/company/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Địa chỉ và metadata trên chỉ minh họa. Discovery còn có thể công bố UserInfo endpoint, logout endpoint, supported scopes, Client authentication methods và thông tin khác.

Spring Security có thể đọc metadata để biết chính xác authorization endpoint, token endpoint, JWKS URI và issuer. Metadata phải được lấy từ provider được tin cậy, đồng thời trường <code>issuer</code> trong JSON phải khớp issuer ứng dụng kỳ vọng.

### 2.2. JWKS

JWKS là JSON chứa một hoặc nhiều **JWK (JSON Web Key)**. Với thuật toán chữ ký bất đối xứng như <code>RS256</code>, JWKS cung cấp khóa công khai để Client xác minh chữ ký ID Token:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "company-key-2026-01",
      "alg": "RS256",
      "n": "base64url-encoded-modulus-placeholder",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là **cấu trúc minh họa**, không phải khóa RSA hợp lệ để dùng xác minh token. Private key ký token nằm ở OP; JWKS thường công bố phần public key. Trường <code>kid</code> giúp Client chọn khóa phù hợp với JWT header. Provider có thể xoay khóa, nên tập khóa công khai thay đổi theo thời gian.

ID Token chỉ có thể được chấp nhận sau khi Client kiểm tra chữ ký, issuer, audience, thời gian hiệu lực và các điều kiện OIDC liên quan. Tải được JWKS không tự động bảo đảm mọi token đều hợp lệ.

### 2.3. Cùng một IdP, hai thời điểm truy cập khác nhau

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động"] --> B{"Cấu hình ClientRegistration"}
    B -->|issuer-uri / discovery| C["HTTP GET metadata từ OP"]
    B -->|Endpoint tĩnh đã cấu hình| D["Dựng ClientRegistration cục bộ"]
    C --> E{"Discovery khả dụng và hợp lệ?"}
    E -->|Không| F["Có thể lỗi khởi tạo bean / startup"]
    E -->|Có| D
    D --> G["Ứng dụng sẵn sàng xử lý HTTP"]
    G --> H["Người dùng bắt đầu OIDC Login"]
    H --> I["Authorization Code Flow"]
    I --> J["Nhận ID Token"]
    J --> K{"Khóa xác minh đã có trong cache?"}
    K -->|Có| M["Xác minh token bằng khóa cache"]
    K -->|Không / cần cập nhật| L["HTTP GET JWKS URI"]
    L --> N{"JWKS khả dụng và có khóa phù hợp?"}
    N -->|Có| M
    N -->|Không| O["Đăng nhập thất bại an toàn"]
~~~

Sơ đồ mô tả trường hợp điển hình. Một cấu hình custom có thể chủ động tải JWKS ngay khi startup, hoặc đã có khóa cache từ trước. Thời điểm gọi mạng phụ thuộc phiên bản Spring Security và bộ giải mã JWT đang được sử dụng.

## 3. Ma trận hành vi khi endpoint không khả dụng

| Tình huống | Ứng dụng có thể khởi động? | Người dùng có thể đăng nhập? | Lý do |
|---|---|---|---|
| Discovery không truy cập được, registration tạo từ <code>issuer-uri</code> lúc startup | **Có thể không** | Chưa đến bước đăng nhập | Không dựng được ClientRegistration |
| Discovery không truy cập được, nhưng registration được dựng thủ công với endpoint/issuer cố định | **Thường có** | Phụ thuộc authorization/token/JWKS endpoints | Không cần gọi discovery để dựng registration |
| JWKS không truy cập được, registration đã dựng thành công | **Thường có** | Có thể thất bại khi xác minh ID Token | Bộ giải mã cần key nhưng không tải được |
| JWKS tạm lỗi nhưng có khóa cache hợp lệ cho <code>kid</code> hiện tại | **Có** | **Có thể vẫn thành công** | Không nhất thiết cần fetch lại khóa ngay |
| JWKS tạm lỗi và OP vừa xoay key mới chưa có trong cache | **Có thể có** | Có thể thất bại | Không có public key tương ứng <code>kid</code> mới |
| Authorization endpoint không truy cập được | Thường có | Không thể bắt đầu hoặc hoàn thành đăng nhập | Trình duyệt không tới được trang xác thực |
| Token endpoint không truy cập được | Thường có | Không hoàn tất đăng nhập mới | Không đổi authorization code lấy token |
| Code tùy biến chủ động tải metadata hoặc JWKS trong <code>@Bean</code>/<code>@PostConstruct</code> | **Phụ thuộc code** | Chưa xác định | Chính ứng dụng đã tạo thêm phụ thuộc startup |

Những kết quả “thường” mô tả **OAuth2 Login Client** với cơ chế mặc định. Không lấy ma trận này áp dụng nguyên xi cho Resource Server hoặc các bộ giải mã custom.

## 4. Trường hợp A: sử dụng issuer-uri và discovery lỗi khi startup

### 4.1. Cấu hình thông dụng

Trong Spring Boot 3 / Spring Security 6, ClientRegistration có thể được cấu hình như sau:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: company-web-client
            client-secret: replace-with-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
~~~

Giá trị client secret trong ví dụ là placeholder. Khi triển khai thật, inject secret từ nguồn bảo mật; không lưu giá trị thật trong repository.

Với <code>issuer-uri</code>, Spring Security/Boot có thể khám phá metadata trong quá trình tạo ClientRegistration. Thông tin cần được lấy qua HTTP trước khi hoàn tất cấu hình của repository.

Nếu DNS không giải được tên miền, HTTP connection timeout, TLS certificate sai, metadata trả 404/503, response không hợp lệ hoặc <code>issuer</code> trong JSON không khớp issuer đã cấu hình, việc tạo bean có thể thất bại. Hệ quả là ApplicationContext không khởi tạo xong và ứng dụng không mở cổng phục vụ bình thường.

Một chuỗi lỗi có thể nhìn thấy trong log:

~~~text
Application startup failed
BeanCreationException: Error creating bean 'clientRegistrationRepository'
  ...
  Unable to resolve the Configuration with the provided Issuer
  ...
  ResourceAccessException: I/O error on GET request
  ...
  Connect timed out
~~~

Đây chỉ là **hình thức lỗi minh họa**. Class exception, thông điệp và thứ tự stack trace phụ thuộc phiên bản Spring Boot/Spring Security, HTTP client và nguyên nhân mạng. Không dựa vào một cụm text duy nhất để nhận diện lỗi.

### 4.2. Tại sao cùng một cấu hình có thể chạy hôm qua nhưng lỗi hôm nay?

Ứng dụng đã chạy hôm qua có ClientRegistration được tạo trong bộ nhớ. Khi triển khai phiên bản mới hoặc pod mới, bean được dựng lại và có thể phải gọi discovery. Do đó:

- Một instance **đang chạy** có thể tiếp tục nhận request dù metadata endpoint vừa mất kết nối.
- Một instance **vừa khởi động** có thể thất bại nếu nó cần gọi discovery ngay.
- Một lệnh rolling deployment có thể tạo instance mới không Ready, dù các instance cũ vẫn đang hoạt động.
- Việc tự động restart hàng loạt instance trong đợt sự cố IdP có thể làm ảnh hưởng rộng hơn.

Điều này là lý do phải phân biệt **startup dependency** với **runtime dependency** và thiết kế rollout phù hợp.

### 4.3. Cách quan sát phụ thuộc discovery

Khi xem log startup, tập trung vào:

1. Bean <code>ClientRegistrationRepository</code> hoặc <code>ClientRegistration</code> đang được tạo hay chưa.
2. URL/issuer nào được dùng để khám phá metadata; có trỏ đúng realm, tenant và môi trường không.
3. Loại lỗi thật: DNS, TCP timeout, TLS trust, HTTP status, JSON parsing hay issuer mismatch.
4. Proxy, firewall và network policy có cho phép ứng dụng truy cập OP qua HTTPS không.
5. Có mã custom nào đang gọi <code>ClientRegistrations.fromIssuerLocation(...)</code> hoặc tự fetch discovery khi startup không.

Giữ log ở mức đủ chẩn đoán; không bật log nhạy cảm chứa client secret, authorization code hoặc token trong production.

## 5. Trường hợp B: JWKS không khả dụng

### 5.1. Khi nào Spring Security cần JWKS?

Trong một OIDC Authorization Code Flow thông thường, Client nhận **ID Token** sau khi đổi code ở token endpoint. Nếu ID Token được ký bằng thuật toán bất đối xứng như RS256, Client cần khóa công khai tương ứng để xác minh chữ ký. <code>jwks_uri</code> được lấy từ metadata hoặc cấu hình provider.

Trong Spring Security OAuth2 Login, việc tạo decoder và truy cập JWKS thường xảy ra **khi cần giải mã/xác minh ID Token**, tức là trong luồng đăng nhập thực tế, thay vì bắt buộc tải toàn bộ khóa lúc startup. Các thay đổi tùy biến của ứng dụng có thể làm hành vi khác đi.

Ví dụ ID Token có header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "company-key-2026-01"
}
~~~

Client phải tìm một public key hợp lệ tương ứng <code>kid</code> trong JWKS của **issuer đã tin cậy**. Nếu không có khóa cache phù hợp và JWKS endpoint lỗi, Client không thể xác minh chữ ký và phải **từ chối đăng nhập**.

### 5.2. Không có cache và có cache khác nhau thế nào?

| Trạng thái | JWKS endpoint bị mất kết nối | Kết quả kỳ vọng |
|---|---|---|
| Lần đầu xác minh ID Token, chưa có khóa cache | Không thể tải key | Login thất bại |
| Khóa phù hợp đã nằm trong cache và vẫn được sử dụng theo chính sách của decoder | Có thể không cần request mạng | Login có thể thành công |
| OP ký bằng <code>kid</code> mới chưa có trong cache | Client cần tải/cập nhật JWKS | Login có thể thất bại |
| Khóa cache bị hết hạn hoặc cần refresh | Bộ giải mã có thể phải fetch JWKS | Login phụ thuộc vào chính sách cache và trạng thái kết nối |

Không mặc định **cache JWKS luôn cứu được đăng nhập**. Cache có TTL, chính sách refresh và giới hạn riêng. Nếu OP xoay khóa khi JWKS đang lỗi, cache có thể không chứa khóa mới. Nếu cache cũ không được chấp nhận, Client phải fail closed.

### 5.3. Khi JWKS hỏng, chuyện gì vẫn hoạt động?

- Ứng dụng **có thể vẫn chạy** và trả lời các endpoint không yêu cầu đăng nhập mới.
- Những phiên người dùng đã xác thực trước đó có thể tiếp tục theo cơ chế session của ứng dụng, nếu session còn hiệu lực và nghiệp vụ không cần xác minh token mới.
- Một số API downstream có thể vẫn hoạt động với token hợp lệ đã có, tùy cách ứng dụng quản lý authorized client và refresh token.
- Luồng **OIDC Login mới** có thể bị lỗi ở bước kiểm tra ID Token.

Không đánh đồng “đăng nhập mới lỗi” với “mọi request hiện tại đều lỗi”. Đồng thời, cũng không giả định session đã tồn tại có thể hoạt động vô thời hạn: expiration, logout, token refresh và các chính sách của hệ thống vẫn áp dụng.

## 6. Cách 1: Giữ discovery động và xử lý dependency startup

Đây là lựa chọn phù hợp nếu đội ngũ muốn metadata luôn được lấy từ OP khi tạo registration và chấp nhận phụ thuộc vào độ sẵn sàng của OP trong giai đoạn khởi động.

Các hướng vận hành quan trọng:

- Đảm bảo issuer chính xác, DNS/TLS và egress đến discovery endpoint hoạt động trong môi trường deploy.
- Dùng **timeout hữu hạn**, tránh treo startup vô thời hạn. Khi tùy biến HTTP client cho discovery, chọn connection timeout và read timeout phù hợp.
- Nếu có retry, giới hạn số lần, sử dụng backoff phù hợp và tránh mọi instance cùng retry dồn dập. Retry vô hạn trong giai đoạn startup sẽ che giấu lỗi cấu hình thật.
- Với rollout nhiều instance, duy trì capacity phục vụ từ instance đang chạy trong lúc instance mới không thể startup; thiết kế readiness và rolling update hợp lý.
- Theo dõi riêng **khả năng truy cập IdP/metadata endpoint** để phát hiện vấn đề trước khi triển khai.
- Chỉ đưa bean startup vào chế độ fail-fast nếu việc không có cấu hình provider thực sự khiến ứng dụng không thể đáp ứng mục tiêu an toàn.

Với cấu hình đơn giản dựa trên Boot properties, không nhất thiết phải tự viết retry trong từng bean. Nếu cần timeout hoặc chiến lược retry đặc thù, hãy xem API/cơ chế customization chính thức của phiên bản Spring Security/HTTP client đang dùng, vì cách discovery được thực hiện có thể thay đổi theo phiên bản.

## 7. Cách 2: Dựng ClientRegistration từ endpoint tĩnh để tránh discovery lúc startup

Nếu yêu cầu vận hành là **ứng dụng phải khởi động dù Discovery Document đang lỗi**, có thể tạo <code>ClientRegistration</code> từ các endpoint và issuer đã được xác minh trước đó. Khi đó bean không cần gọi discovery.

Đây là lựa chọn có đánh đổi: đội ngũ phải **duy trì cấu hình endpoint/issuer** khi OP thay đổi và vẫn phải xử lý JWKS ở runtime. Không dùng metadata thủ công từ nguồn không đáng tin cậy.

### 7.1. Properties riêng cho cấu hình tĩnh

Ví dụ <code>application.yml</code>:

~~~yaml
app:
  oidc:
    issuer-uri: https://login.example.org/realms/company
    authorization-uri: https://login.example.org/realms/company/protocol/openid-connect/auth
    token-uri: https://login.example.org/realms/company/protocol/openid-connect/token
    jwk-set-uri: https://login.example.org/realms/company/protocol/openid-connect/certs
    client-id: replace-with-client-id
    client-secret: replace-with-secret-from-secure-config
~~~

Các giá trị <code>client-id</code>/<code>client-secret</code> ở đây là placeholders. Trong production, dùng secret manager hoặc biến môi trường và không commit secret thật. Các endpoint phải là giá trị chính thức đã được xác minh từ cấu hình OP.

### 7.2. Bean Java không gọi discovery

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class OAuth2ClientConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(Environment env) {
        ClientRegistration company = ClientRegistration
            .withRegistrationId("company")
            .clientId(env.getRequiredProperty("app.oidc.client-id"))
            .clientSecret(env.getRequiredProperty("app.oidc.client-secret"))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile")
            .issuerUri(env.getRequiredProperty("app.oidc.issuer-uri"))
            .authorizationUri(env.getRequiredProperty("app.oidc.authorization-uri"))
            .tokenUri(env.getRequiredProperty("app.oidc.token-uri"))
            .jwkSetUri(env.getRequiredProperty("app.oidc.jwk-set-uri"))
            .clientName("Company SSO")
            .build();

        return new InMemoryClientRegistrationRepository(company);
    }
}
~~~

Phần khác biệt then chốt: ví dụ sử dụng <code>ClientRegistration.withRegistrationId(...)</code>, **không** gọi <code>ClientRegistrations.fromIssuerLocation(...)</code>. Nhờ đó, việc tạo bean này không cần truy cập Discovery Document.

<code>issuerUri(...)</code> vẫn được đặt rõ ràng để ứng dụng có thông tin issuer cần thiết cho OIDC validation. Không bỏ issuer vì muốn né lỗi mạng. Đường dẫn <code>jwks_uri</code> vẫn trỏ đến endpoint khóa công khai thực tế: khi xác minh ID Token, decoder có thể phải gọi endpoint đó.

Các API builder minh họa theo Spring Security 6; trong dự án thật cần dùng API và yêu cầu cấu hình OIDC của phiên bản được triển khai.

### 7.3. Kích hoạt OAuth2 Login

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Client truy cập <code>/oauth2/authorization/company</code> để bắt đầu flow. Khi OP hoạt động và token có thể được xác minh, callback mặc định là <code>/login/oauth2/code/company</code>.

**Không cần khai báo thêm một <code>ClientRegistrationRepository</code> tự động khác** nếu bean Java trên đã là nguồn registration chính thức. Spring Boot thường lùi bước trước bean ứng dụng tự cung cấp.

### 7.4. Giới hạn của cách cấu hình tĩnh

Cấu hình thủ công giải quyết **phụ thuộc discovery lúc tạo ClientRegistration**, không đảm bảo đăng nhập hoạt động khi:

- Authorization endpoint đang lỗi: trình duyệt không xác thực được.
- Token endpoint đang lỗi: Client không đổi code lấy ID Token/access token.
- JWKS endpoint đang lỗi mà không có khóa cache hợp lệ: Client không xác minh ID Token.
- OP thay đổi endpoint, issuer, authentication method hoặc key rotation mà cấu hình Client chưa theo kịp.

Nên có quy trình đối chiếu metadata chính thức định kỳ và cập nhật cấu hình khi OP thay đổi. Không chấp nhận bất cứ issuer/key nào chỉ để “cho app lên”.

## 8. Có thể cache hoặc phân phối JWKS theo cách khác không?

**Có thể**, nhưng đây là quyết định kiến trúc riêng, cần cân bằng tính sẵn sàng và an toàn xác minh chữ ký.

### 8.1. Cache JWKS trong decoder

Các thư viện JWT hiện đại thường cache khóa/JWKS sau khi tải thành công để tránh gọi IdP cho từng token. Lợi ích:

- Giảm latency và số request đến JWKS endpoint.
- Cho phép một số lần xác minh vẫn hoạt động khi JWKS tạm lỗi, nếu khóa cần thiết còn khả dụng trong cache.
- Hỗ trợ xoay khóa khi thư viện cập nhật JWKS theo cơ chế của mình.

Tuy nhiên không nên mặc định mọi decoder có cùng TTL, chiến lược cache hoặc behavior khi gặp <code>kid</code> mới. Cần kiểm tra API và cấu hình cụ thể của Spring Security/Nimbus đang sử dụng. Cache trong một instance cũng không mặc nhiên được chia sẻ sang các instance khác.

### 8.2. Đóng gói public key hoặc JWKS nội bộ

Trong một số môi trường cô lập, đội vận hành có thể cung cấp tập public key/JWKS được quản lý riêng hoặc một JWKS mirror nội bộ. Cách này có thể giảm phụ thuộc mạng trực tiếp vào IdP tại thời điểm xác minh, nhưng đồng thời phát sinh trách nhiệm:

1. Nhận khóa từ nguồn OP chính thức và xác minh tính toàn vẹn của nguồn.
2. Cập nhật khóa **trước, trong và sau** key rotation theo quy trình được thỏa thuận với OP.
3. Không chấp nhận khóa bất kỳ hoặc JWKS từ issuer khác.
4. Giới hạn thời gian sử dụng khóa cũ và xử lý việc thu hồi khóa.
5. Thiết kế alert và phương án khôi phục khi bộ khóa nội bộ không còn đồng bộ.

Không chỉ sao chép một public key cũ rồi coi là giải pháp lâu dài. Nếu OP chuyển sang <code>kid</code> mới, token mới sẽ không xác minh được khi local keyset chưa cập nhật. Nếu khóa bị thu hồi, dùng stale key vô hạn còn có thể làm suy yếu bảo mật.

### 8.3. Những fallback không được dùng

- Bỏ kiểm tra chữ ký ID Token hoặc chấp nhận <code>alg=none</code> tùy ý.
- Bỏ kiểm tra <code>iss</code> hoặc <code>aud</code> để chấp nhận token từ provider khác.
- Tin public key/JWKS URL do JWT chưa được xác minh tự khai báo.
- Cố dùng access token như ID Token thay vì xác minh danh tính OIDC.
- Tạo “chế độ đăng nhập tạm” tự nhận mọi người dùng khi IdP ngừng hoạt động.

Khi không thể xác minh token theo chính sách, login mới phải **fail closed**: từ chối đăng nhập và trả thông báo phù hợp, đồng thời giữ những chức năng không liên quan hoạt động nếu kiến trúc cho phép.

## 9. Readiness, liveness và hành vi vận hành trên Kubernetes

Một lỗi JWKS hoặc OIDC Login không nhất thiết có nghĩa cả ứng dụng không đủ điều kiện xử lý tất cả request. Do đó cần phân biệt:

| Kiểu health check | Câu hỏi được trả lời | Gợi ý |
|---|---|---|
| **Liveness** | Tiến trình ứng dụng còn hoạt động và có thể tiếp tục xử lý không? | Không nên làm phụ thuộc cứng vào tình trạng JWKS/Discovery bên ngoài để tránh restart storm |
| **Readiness** | Instance hiện có đủ điều kiện nhận traffic theo contract dịch vụ không? | Phụ thuộc vào yêu cầu nghiệp vụ; không tự động đánh rớt chỉ vì OP gián đoạn nếu endpoint khác vẫn phục vụ được |
| **Dependency monitor** | OP discovery, authorization, token, JWKS có sẵn sàng không? | Theo dõi/alert riêng để người vận hành thấy chính xác sự cố |
| **Login synthetic check** | Luồng đăng nhập có thực sự hoàn tất không? | Thực hiện bằng tài khoản/kịch bản thử an toàn, có kiểm soát tần suất và không để lộ credential |

Ví dụ trong ứng dụng có nhiều endpoint không cần login, đánh dấu liveness “down” mỗi khi JWKS trả 503 sẽ khiến Kubernetes liên tục restart những pod thực ra vẫn xử lý được công việc. Ngược lại, với một ứng dụng mà toàn bộ chức năng bắt buộc có đăng nhập mới, chính sách readiness có thể phải chặt chẽ hơn. Quyết định phải dựa trên **contract sẵn sàng của dịch vụ**, không dựa trên một mặc định chung.

Khi deployment dùng discovery trong lúc khởi tạo, cần tính đến tình huống pod mới thất bại còn pod cũ vẫn đang chạy:

~~~text
IdP gặp sự cố ngắn hạn
    ├─ Pod cũ: đã có ClientRegistration → có thể tiếp tục phục vụ
    ├─ Pod mới: cần discovery khi startup → có thể khởi tạo thất bại
    └─ Rollout: thiếu capacity nếu thay pod quá nhanh
~~~

Rolling update nên giữ đủ instance đang phục vụ, sử dụng readiness cho instance mới và không xóa sạch capacity hiện có trước khi xác nhận instance thay thế hoạt động. Nếu không có metadata tại startup, cần log lỗi rõ ràng và cho platform xử lý retry rollout theo chính sách phù hợp, thay vì tạo vô hạn request tới OP.

## 10. Thiết kế timeout, retry và xử lý lỗi đúng chỗ

### 10.1. Timeout hữu hạn

Tất cả request mạng đến discovery, JWKS, token endpoint cần có timeout rõ ràng, đặc biệt trong môi trường triển khai có proxy hoặc đường truyền không ổn định.

Phân biệt:

- **Connection timeout:** không thiết lập được kết nối tới OP.
- **Read/response timeout:** kết nối đã tạo nhưng OP phản hồi quá chậm.
- **TLS failure:** chứng chỉ hoặc handshake lỗi; retry thường không sửa được cấu hình trust sai.
- **HTTP 4xx/5xx:** chỉ một số lỗi là tạm thời; 404/401 và issuer mismatch thường là vấn đề cấu hình.

Không cài retry vô hạn ngay trong bean khởi tạo vì nó có thể khiến startup treo, khó quan sát và làm nhiều instance đồng loạt tấn công endpoint đang gặp sự cố.

### 10.2. Retry có chọn lọc

| Thao tác | Có nên retry? | Lưu ý |
|---|---|---|
| Lấy discovery metadata khi lỗi mạng/5xx | Có thể, giới hạn rõ ràng | Backoff, timeout; không che lấp lỗi issuer mismatch |
| Lấy JWKS khi lỗi mạng/5xx | Có thể theo chính sách decoder | Không dùng khóa từ issuer không tin cậy |
| Tải JWKS khi không thấy <code>kid</code> | Có thể refresh theo cơ chế thư viện | Tránh refresh vô hạn và kiểm tra key rotation |
| Token request đổi authorization code | **Rất thận trọng** | Code thường dùng một lần; retry thiếu kiểm soát có thể gây lỗi/hiểu nhầm trạng thái |
| Đăng nhập người dùng trong browser | Cho phép bắt đầu lại flow | Không tự dùng lại authorization code hết hạn hoặc đã tiêu thụ |

Khi một request đổi code lấy token đã được OP xử lý nhưng response bị mất, Client khó biết code đã được dùng chưa. Cách phục hồi an toàn thường là khởi tạo lại Authorization Code Flow cho người dùng thay vì lặp cùng code nhiều lần.

### 10.3. Trả lỗi rõ cho người dùng

Khi OP hoặc JWKS lỗi, trang đăng nhập có thể hiển thị thông báo trung tính:

> Không thể hoàn tất đăng nhập do dịch vụ xác thực đang tạm thời không khả dụng. Vui lòng thử lại sau.

Không đưa stack trace, token, client secret, tên host nội bộ hoặc dữ liệu cấu hình nhạy cảm vào trang lỗi. Phía server nên có correlation ID, loại lỗi, thời gian và tên registration/provider để hỗ trợ điều tra.

## 11. Phân biệt OAuth2 Client và Resource Server

Đây là một nguồn nhầm lẫn rất thường gặp trong Spring Security.

**OAuth2/OIDC Client**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
~~~

Thuộc tính này giúp **ClientRegistration** khám phá metadata cho luồng đăng nhập/ủy quyền. Lỗi discovery trong giai đoạn dựng registration có thể chặn startup.

**OAuth2 Resource Server**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/company
~~~

Thuộc tính này phục vụ việc **xác minh bearer JWT trong request đến API**. Tùy phiên bản và cách tạo <code>JwtDecoder</code>, Resource Server có thể discovery metadata khi khởi tạo hoặc có cơ chế khởi tạo trì hoãn. Cấu hình thêm <code>jwk-set-uri</code> ở Resource Server thường được sử dụng để tránh discovery lúc startup trong trường hợp được Spring Security hỗ trợ, đồng thời vẫn áp dụng issuer validation khi có <code>issuer-uri</code>.

Không tự suy ra behavior của OAuth2 Login Client từ tài liệu hoặc ví dụ dành cho Resource Server. Hai vai trò dùng các lớp cấu hình, lifecycle và đường xử lý token khác nhau, dù cả hai có thể dùng cùng OP/JWKS.

Một ứng dụng vừa có <code>oauth2Login()</code> vừa phục vụ API JWT có thể phải quản lý **hai** cấu hình riêng. Khi chẩn đoán lỗi, xác định loại bean nào đang khởi tạo và luồng nào đang xác minh token.

## 12. Tình huống và cách điều tra

### Tình huống A — Startup fail vì Discovery Document trả 503

Ứng dụng khai báo <code>spring.security.oauth2.client.provider.company.issuer-uri</code>, và trong lúc deploy IdP trả HTTP 503 tại well-known endpoint. Startup dừng khi dựng ClientRegistrationRepository.

**Giải thích:** Client đang cần metadata để tạo registration nên phụ thuộc discovery trong giai đoạn khởi động.

**Lựa chọn:** khôi phục kết nối/khả năng sẵn sàng của IdP; cải thiện timeout và rollout; hoặc chủ động chuyển sang ClientRegistration dựng từ endpoint tĩnh đã được xác minh nếu yêu cầu nghiệp vụ cần khởi động độc lập với discovery. Không sửa issuer bừa sang một realm khác chỉ để nhận HTTP 200.

### Tình huống B — App chạy nhưng login OIDC trả lỗi

HTTP endpoint của ứng dụng vẫn hoạt động. Người dùng được chuyển sang IdP, đăng nhập, callback nhận code và token, sau đó Spring Security báo lỗi liên quan không tải được JWKS.

**Giải thích:** Startup đã hoàn tất, nhưng bước xác minh chữ ký ID Token cần public key mà decoder chưa có. Không thể bỏ qua validation.

**Cần kiểm tra:** JWKS URI chính thức, DNS/TLS/HTTP status, <code>kid</code> trong token header, thuật toán ký và tình trạng key rotation. Nếu không có key hợp lệ, trả lỗi đăng nhập và theo dõi sự cố.

### Tình huống C — Chỉ pod mới lỗi sau khi restart

IdP discovery bị gián đoạn. Những pod chạy từ trước vẫn phục vụ được các request không cần đăng nhập mới, nhưng pod mới gặp lỗi tạo bean.

**Giải thích:** Instance cũ đã có ClientRegistration trong memory; instance mới phải chạy lại discovery. Readiness/rollout cần giữ pod cũ hoạt động cho đến khi instance thay thế sẵn sàng.

### Tình huống D — JWKS cache có key cũ, IdP vừa rotate key

ID Token mới có <code>kid</code> chưa nằm trong cache. JWKS endpoint cũng vừa bị gián đoạn.

**Giải thích:** Không đủ public key để xác minh token mới. Việc “cho phép dùng khóa cũ để kiểm chữ ký của token mới” là sai. Đợi khôi phục JWKS/đồng bộ keyset hợp lệ, không vô hiệu hóa xác minh.

### Tình huống E — Bật jwk-set-uri nhưng startup vẫn lỗi

Ứng dụng cấu hình cả <code>issuer-uri</code> và <code>jwk-set-uri</code> trong **OAuth2 Client provider properties** và kỳ vọng không còn discovery lúc startup, nhưng vẫn thấy lỗi ClientRegistration.

**Giải thích:** Việc có JWKS URI không nhất thiết làm Spring Boot bỏ qua quá trình discovery khi dựng registration bằng issuer. Đây là một nhầm lẫn với một số cấu hình của Resource Server.

**Cách xử lý:** kiểm tra thành phần tạo registration; nếu cần không có discovery startup, sử dụng cách dựng ClientRegistration bằng Java từ toàn bộ endpoint và issuer như mục 7, hoặc một cơ chế cấu hình thủ công tương đương đã được xác minh.

## 13. Quy trình chẩn đoán theo giai đoạn

~~~mermaid
flowchart TD
    A["Ứng dụng gặp lỗi liên quan IdP"] --> B{"Lỗi ở giai đoạn nào?"}
    B -->|Trước khi HTTP app sẵn sàng| C["Kiểm tra tạo ClientRegistrationRepository"]
    C --> D{"Có gọi issuer discovery?"}
    D -->|Có| E["Kiểm DNS/TLS/HTTP, JSON và issuer match"]
    D -->|Không| F["Kiểm bean custom, properties và endpoint tĩnh"]
    B -->|Khi bấm đăng nhập| G["Kiểm authorization endpoint và browser redirect"]
    B -->|Khi callback / đổi code| H["Kiểm token endpoint, client auth, PKCE và state"]
    B -->|Khi xác minh ID Token| I["Kiểm JWKS, kid, alg, iss, aud, exp"]
    E --> J["Sửa dependency/config và quan sát khởi động lại"]
    F --> J
    G --> K["Khôi phục flow OAuth/OIDC theo chuẩn"]
    H --> K
    I --> K
~~~

Đối với từng sự cố, ghi nhận:

1. **Thời điểm lỗi:** startup, bấm login, token exchange hay ID Token validation.
2. **Bean hoặc lớp xử lý:** ClientRegistrationRepository, authorization request resolver, token client hay JWT decoder.
3. **Provider chính xác:** registration ID, issuer và môi trường. Không vô tình dùng issuer staging cho production.
4. **Kênh mạng:** DNS, proxy, firewall/egress, TLS, HTTP status và timeout.
5. **Cache/trạng thái:** metadata đã được lấy chưa; JWKS key có sẵn không; <code>kid</code> có thay đổi không.
6. **Ảnh hưởng:** startup fail hoàn toàn hay chỉ login mới fail; số instance bị ảnh hưởng; session hiện có.

Chẩn đoán có cấu trúc giúp phân biệt sự cố kết nối thực sự với lỗi cấu hình issuer, redirect URI hoặc client authentication.

## 14. Thực hành tại môi trường phát triển

### Bài 1 — Khởi động khi discovery không truy cập được

**Chuẩn bị:** một IdP OIDC thử nghiệm với issuer có thể truy cập, Spring Boot ứng dụng OAuth2 Login và một môi trường có thể mô phỏng lỗi mạng.

1. Bắt đầu từ cấu hình <code>issuer-uri</code> theo mục 4; chạy ứng dụng khi IdP hoạt động.
2. Trong môi trường thử nghiệm, ngắt kết nối đến Discovery Document hoặc dùng endpoint mô phỏng trả HTTP 503 trước lúc khởi động ứng dụng mới.
3. Quan sát lỗi tạo ClientRegistration và ghi nhận nguyên nhân mạng (không log credential).
4. Chuyển sang cấu hình Java thủ công theo mục 7 với các endpoint chính xác đã được xác minh.
5. Thử khởi động lại trong lúc Discovery Document vẫn lỗi.
6. Phân biệt kết quả khởi động với kết quả đăng nhập khi các endpoint khác còn/mất kết nối.

**Điều cần rút ra:** dựng cấu hình tĩnh có thể loại bỏ dependency discovery tại startup; nó không làm hệ thống đăng nhập độc lập hoàn toàn với IdP.

### Bài 2 — Khi JWKS không khả dụng

1. Khởi động ứng dụng khi metadata hợp lệ.
2. Trong môi trường thử nghiệm, chỉ chặn hoặc mô phỏng lỗi ở JWKS endpoint, giữ authorization/token endpoints hoạt động.
3. Thực hiện một lần đăng nhập mới cần xác minh ID Token.
4. Quan sát tình huống có cache và không có cache. Nếu thư viện không gọi JWKS vì có cache, dùng instance mới hoặc môi trường test cô lập để quan sát lần tải khóa đầu tiên.
5. Khôi phục endpoint và bắt đầu **luồng đăng nhập mới**, không tái sử dụng authorization code đã được dùng hoặc đã hết hạn.

**Điều cần rút ra:** chữ ký ID Token vẫn phải được xác minh; lỗi JWKS là lỗi runtime của login, không nhất thiết là lỗi startup.

### Bài 3 — Phân tích lựa chọn kiến trúc

Một ứng dụng nội bộ cung cấp dashboard đã đăng nhập và một số API công khai. Nhà cung cấp SSO có tỷ lệ downtime ngắn nhưng công ty yêu cầu dashboard vẫn phục vụ những phiên đã xác thực khi hệ thống đăng nhập tạm lỗi.

Hãy so sánh:

| Lựa chọn | Ưu điểm | Chi phí/trách nhiệm |
|---|---|---|
| Issuer discovery lúc startup | Ít endpoint hardcode, lấy metadata từ OP | Instance mới phụ thuộc availability discovery |
| ClientRegistration tĩnh đã xác minh | Có thể startup khi discovery lỗi | Cần cập nhật endpoint, issuer, phương thức xác thực |
| JWKS cache theo thư viện | Giảm phụ thuộc JWKS cho mỗi lần login | Cache miss hoặc key rotation vẫn cần tải key |
| JWKS mirror/keyset nội bộ | Có thể giảm phụ thuộc IdP trực tiếp khi xác minh | Phải quản lý tính toàn vẹn, cache, key rotation và thu hồi khóa |
| Monitor IdP riêng và thiết kế rollout | Giữ rõ tác động, tránh restart storm | Cần metrics, alert và quy trình vận hành |

**Gợi ý:** đầu tiên xác định mục tiêu availability cụ thể: ứng dụng phải **start**, phải **phục vụ người dùng đã đăng nhập**, hay phải **cho phép đăng nhập mới** khi IdP mất kết nối? Ba mục tiêu này khác nhau và cần những giải pháp khác nhau.

## 15. Tổng kết kiến thức

- **Discovery Document** giúp dựng ClientRegistration bằng issuer. Với cách cấu hình <code>issuer-uri</code> thường dùng trong Spring Security OAuth2 Client, nếu discovery không khả dụng lúc khởi tạo repository thì **startup có thể thất bại**.
- **JWKS** dùng để xác minh chữ ký ID Token. Trong OIDC Login thông thường, việc tải khóa thường xảy ra khi xác minh token nên **JWKS lỗi thường ảnh hưởng đăng nhập mới**, không nhất thiết chặn startup.
- Nếu cần startup khi discovery down, có thể **dựng ClientRegistration thủ công** từ issuer/authorization/token/JWKS endpoints đã được tin cậy. Cách này vẫn phụ thuộc vào OP khi thực hiện đăng nhập.
- **Cache JWKS** có thể giúp qua sự cố ngắn khi có khóa phù hợp, nhưng không bảo đảm hoạt động với key mới hoặc cache đã hết hạn. Không bao giờ chấp nhận token không được xác minh để tăng availability.
- Xác định rõ **startup, login, token exchange và ID Token validation** là bốn giai đoạn khác nhau khi debug. Readiness, liveness, rollout và dependency monitoring phải phản ánh ảnh hưởng thật của từng sự cố.
- **OAuth2 Client và Resource Server** có cấu hình, thời điểm discovery và lifecycle decoder khác nhau; không áp dụng máy móc hướng dẫn của Resource Server cho OIDC Login Client.

### Tài liệu chuẩn và API nên tham khảo

- **OpenID Connect Discovery 1.0**: issuer, Provider Configuration và thông tin metadata.
- **OpenID Connect Core 1.0**: ID Token, chữ ký, issuer, audience và các bước validation.
- **RFC 7517 — JSON Web Key (JWK)**: cấu trúc các public key trong JWKS.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata**: metadata endpoint và issuer trong OAuth 2.0.
- **Spring Security Reference — OAuth2 Login, OAuth2 Client, JWT Resource Server**: cấu hình ClientRegistration, issuer, JWKS và bộ giải mã.
- **Spring Security API — ClientRegistration, ClientRegistrations, OidcIdTokenDecoderFactory, NimbusJwtDecoder**: các điểm mở rộng liên quan tạo registration và xác minh JWT.
- **Spring Boot Reference — OAuth2 Client auto-configuration và Actuator health probes**: cách Boot dựng cấu hình Client và các khái niệm readiness/liveness.
