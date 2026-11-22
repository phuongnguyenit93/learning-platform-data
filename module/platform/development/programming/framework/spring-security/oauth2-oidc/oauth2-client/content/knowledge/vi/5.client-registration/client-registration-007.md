# 5.7. InMemoryClientRegistrationRepository và cấu hình bằng Java

## 1. Bối cảnh: ứng dụng Spring Security lấy thông tin OAuth 2.0 Client ở đâu?

Khi một ứng dụng Spring Boot đăng nhập bằng OAuth 2.0 hoặc OpenID Connect (OIDC), nó cần biết mình đã đăng ký với Authorization Server/OpenID Provider như thế nào. Những thông tin đó bao gồm **client ID**, cách xác thực Client, authorization endpoint, token endpoint, redirect URI, scope và có thể cả issuer/JWK Set URI nếu dùng OIDC.

Spring Security biểu diễn một cấu hình như vậy bằng đối tượng **<code>ClientRegistration</code>**. Mỗi registration có một **<code>registrationId</code>** duy nhất bên trong ứng dụng, ví dụ <code>google</code>, <code>github</code>, <code>company-sso</code>.

Spring Security không bắt buộc ứng dụng phải lưu các registration trong <code>application.yml</code>. Framework chỉ cần một bean có kiểu **<code>ClientRegistrationRepository</code>** để tra cứu registration theo ID.

**<code>InMemoryClientRegistrationRepository</code>** là một implementation đơn giản của interface này. Nó giữ tập hợp <code>ClientRegistration</code> trong bộ nhớ ứng dụng, phù hợp khi danh sách provider cố định hoặc được tạo từ cấu hình Java lúc khởi động.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Cấu hình Java / biến môi trường / discovery"] --> B["Tạo ClientRegistration"]
    B --> C["InMemoryClientRegistrationRepository"]
    D["GET /oauth2/authorization/company-sso"] --> E["Spring Security OAuth2 Login"]
    E --> F["findByRegistrationId('company-sso')"]
    F --> C
    C --> G["ClientRegistration phù hợp"]
    G --> H["Tạo authorization request"]
    H --> I["Authorization Server / OpenID Provider"]
~~~

> **Phân biệt ngay từ đầu:** Repository này lưu **cấu hình Client**, không phải nơi lưu access token, refresh token, ID Token hoặc phiên đăng nhập của người dùng.

## 2. Các kiểu dữ liệu và vai trò của từng thành phần

| Thành phần | Vai trò | Ví dụ dữ liệu |
|---|---|---|
| <code>ClientRegistration</code> | Mô tả **một** OAuth 2.0/OIDC Client đã đăng ký với provider | <code>clientId</code>, <code>redirectUri</code>, <code>authorizationUri</code>, <code>scope</code> |
| <code>ClientRegistrationRepository</code> | Hợp đồng tra cứu registration theo <code>registrationId</code> | <code>findByRegistrationId("company-sso")</code> |
| <code>InMemoryClientRegistrationRepository</code> | Implementation giữ nhiều registration trong memory | Tập registrations <code>company-sso</code>, <code>github</code> |
| <code>OAuth2AuthorizedClient</code> | Liên kết ClientRegistration và principal với token đã được cấp | Access token, refresh token nếu có |
| <code>OAuth2AuthorizedClientService</code> | Quản lý authorized clients theo registration/principal, thường phục vụ service layer | <code>loadAuthorizedClient(...)</code> |
| <code>OAuth2AuthorizedClientRepository</code> | Lưu/tra cứu authorized client trong ngữ cảnh web request | Token gắn với phiên/request |
| <code>SecurityFilterChain</code> | Cấu hình cách ứng dụng kích hoạt OAuth2 Login hoặc OAuth2 Client | <code>oauth2Login()</code>, <code>oauth2Client()</code> |

Tên <code>InMemory...</code> dễ gây hiểu nhầm. <code>InMemoryClientRegistrationRepository</code> **không tự lưu trạng thái đăng nhập**. Việc chọn nơi lưu user session, authorized client và token là quyết định khác, được thực hiện bằng những component khác.

### 2.1. Interface ClientRegistrationRepository

Hợp đồng cốt lõi của interface rất nhỏ:

~~~java
public interface ClientRegistrationRepository {
    ClientRegistration findByRegistrationId(String registrationId);
}
~~~

Spring Security dùng <code>registrationId</code> để chọn một registration khi bắt đầu đăng nhập, nhận callback, hoặc xử lý OAuth2 Client. Nếu không tìm thấy ID, <code>findByRegistrationId</code> trả về <code>null</code>; các lớp gọi tiếp theo có thể báo lỗi do không tìm thấy cấu hình Client.

<code>InMemoryClientRegistrationRepository</code> còn triển khai <code>Iterable&lt;ClientRegistration&gt;</code>, cho phép Spring Security duyệt danh sách registration trong các tình huống như dựng trang login có nhiều OAuth provider.

### 2.2. Các cách khởi tạo repository

Hai cách sử dụng thông dụng:

~~~java
ClientRegistration first = /* tạo ClientRegistration thứ nhất */;
ClientRegistration second = /* tạo ClientRegistration thứ hai */;

ClientRegistrationRepository byVarargs =
        new InMemoryClientRegistrationRepository(first, second);

ClientRegistrationRepository byList =
        new InMemoryClientRegistrationRepository(List.of(first, second));
~~~

Cần import <code>java.util.List</code> và các class Spring Security tương ứng. Đây là đoạn minh họa API, không phải một file Java độc lập: hai biến <code>first</code>/<code>second</code> phải được tạo từ các cấu hình hợp lệ trước đó.

Repository lưu tập registration được đưa vào lúc dựng bean. Nó phù hợp với **danh sách cấu hình ổn định**; API này không cung cấp nghiệp vụ quản trị provider động hay tự đồng bộ registration từ database giữa các instance.

## 3. Cấu hình OIDC bằng Java và Discovery từ issuer

Đây là cách dễ bảo trì khi ứng dụng sử dụng một OpenID Provider hỗ trợ **OIDC Discovery Document**. Thay vì tự khai báo authorization URL, token URL và JWKS URL, ứng dụng cung cấp <code>issuer-uri</code> để thư viện khám phá metadata.

### 3.1. Dependency

Với Spring Boot 3 và Spring Security 6, dùng OAuth2 Client starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Nếu dùng Maven, dependency tương đương là <code>org.springframework.boot:spring-boot-starter-oauth2-client</code> cùng các starter web/security phù hợp.

### 3.2. Thuộc tính cấu hình riêng của ứng dụng

Vì sẽ tự tạo bean bằng Java, ta có thể đặt thông tin provider trong nhóm cấu hình riêng thay vì dùng nhóm auto-config <code>spring.security.oauth2.client.registration</code>:

~~~yaml
# application.yml
app:
  oidc:
    issuer-uri: https://login.example.org/realms/training
    client-id: ${APP_OIDC_CLIENT_ID}
    client-secret: ${APP_OIDC_CLIENT_SECRET}
~~~

<code>APP_OIDC_CLIENT_ID</code> và <code>APP_OIDC_CLIENT_SECRET</code> là biến môi trường do hệ thống triển khai cung cấp. <code>https://login.example.org/realms/training</code> là issuer giả định, cần thay bằng issuer chính thức của OP.

Giữ client secret trong secret manager/biến môi trường phù hợp; không commit giá trị thật vào file hoặc source code.

### 3.3. Tạo ClientRegistrationRepository bean

~~~java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class OAuth2ClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.oidc.issuer-uri}") String issuerUri,
            @Value("${app.oidc.client-id}") String clientId,
            @Value("${app.oidc.client-secret}") String clientSecret) {

        ClientRegistration training = ClientRegistrations
            .fromIssuerLocation(issuerUri)
            .registrationId("training")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .build();

        return new InMemoryClientRegistrationRepository(training);
    }
}
~~~

Diễn giải từng phần:

1. <code>ClientRegistrations.fromIssuerLocation(issuerUri)</code> lấy metadata từ issuer phù hợp với cơ chế discovery mà phiên bản Spring Security hỗ trợ. Metadata giúp xây dựng các endpoint và thông tin provider. URL issuer phải đến từ cấu hình đáng tin cậy.
2. <code>registrationId("training")</code> đặt khóa nội bộ cho registration, không nhất thiết trùng tên host, tenant hay Client ID.
3. <code>clientId</code>/<code>clientSecret</code> là thông tin ứng dụng đã đăng ký với OP.
4. <code>CLIENT_SECRET_BASIC</code> xác định cách confidential Client xác thực ở token endpoint; cần trùng registration thực tế trên OP.
5. <code>AUTHORIZATION_CODE</code> chọn Authorization Code Flow.
6. <code>redirectUri</code> dùng URI template mặc định của Spring Security, được thay thế từ request và registration ID lúc thực thi. Redirect URI sau khi triển khai phải khớp URI được đăng ký tại OP.
7. Scope <code>openid</code> yêu cầu OIDC; các scope <code>profile</code>/<code>email</code> chỉ được cấp khi OP và chính sách của Client cho phép.
8. Repository được tạo với một <code>ClientRegistration</code>. Spring Security tra cứu nó bằng ID <code>training</code>.

Đối với phương thức <code>fromIssuerLocation</code>, thư viện có thể gọi mạng **trong lúc tạo bean**, thường là giai đoạn khởi động ứng dụng. Nếu OP không sẵn sàng, issuer sai hoặc cấu hình TLS/DNS có vấn đề, khởi tạo ClientRegistration có thể thất bại. Điều này cần được tính đến trong kế hoạch triển khai và vận hành.

Nếu hệ thống yêu cầu public client, không dùng client secret; cần đăng ký đúng loại Client, chọn <code>ClientAuthenticationMethod.NONE</code> và bảo đảm PKCE được áp dụng. Ví dụ ở trên dành cho **confidential web Client** phía server.

### 3.4. Kích hoạt OAuth2 Login

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
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Khi chạy ứng dụng, đường dẫn bắt đầu flow theo mặc định là:

~~~http
GET /oauth2/authorization/training HTTP/1.1
Host: app.example.org
~~~

Spring Security tìm registration ID <code>training</code>, dựng authorization request và chuyển trình duyệt đến OP. Callback mặc định tương ứng:

~~~text
https://app.example.org/login/oauth2/code/training
~~~

Sau khi xác thực, Spring Security xử lý code/token và thiết lập principal dựa trên OAuth2/OIDC. Nếu provider phát ID Token OIDC hợp lệ, framework xử lý theo luồng OIDC Login.

> Chỉ cần <code>oauth2Login()</code> cho use case đăng nhập người dùng. Nếu ứng dụng còn chủ động gọi downstream API với tư cách OAuth2 Client, có thể cần cấu hình thêm <code>oauth2Client()</code>, authorized client manager và cơ chế lưu token phù hợp.

## 4. Cấu hình Java với endpoint được khai báo thủ công

Không phải provider OAuth 2.0 nào cũng hỗ trợ OIDC Discovery. Khi dùng OAuth 2.0 provider có endpoint cố định, có thể trực tiếp tạo <code>ClientRegistration</code> bằng <code>ClientRegistration.withRegistrationId(...)</code>.

Ví dụ một OAuth 2.0 provider minh họa có UserInfo endpoint trả JSON với thuộc tính <code>id</code>:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class ManualProviderConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration legacy = ClientRegistration
            .withRegistrationId("legacy")
            .clientId("replace-with-client-id")
            .clientSecret("replace-with-secret")
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("read_profile")
            .authorizationUri("https://legacy.example.org/oauth2/authorize")
            .tokenUri("https://legacy.example.org/oauth2/token")
            .userInfoUri("https://legacy.example.org/api/user")
            .userNameAttributeName("id")
            .clientName("Legacy Provider")
            .build();

        return new InMemoryClientRegistrationRepository(legacy);
    }
}
~~~

Đây là **một phương án thay thế độc lập** cho bean ở mục 3.3; không khai báo cùng lúc hai bean <code>ClientRegistrationRepository</code> nếu không có chủ đích và cơ chế chọn bean rõ ràng. Dữ liệu mẫu phải được thay bằng cấu hình chính thức của provider, đặc biệt secret không nên hardcode trong ứng dụng thật.

Các trường quan trọng của builder:

| Phương thức | Ý nghĩa |
|---|---|
| <code>withRegistrationId("legacy")</code> | Tạo builder cho registration mang ID <code>legacy</code> |
| <code>clientId(...)</code> | Client ID do Authorization Server cấp |
| <code>clientSecret(...)</code> | Secret của confidential Client, nếu phương thức xác thực cần |
| <code>clientAuthenticationMethod(...)</code> | Cách xác thực Client ở token endpoint |
| <code>authorizationGrantType(...)</code> | Loại grant, trong ví dụ là authorization code |
| <code>redirectUri(...)</code> | Callback của Client |
| <code>scope(...)</code> | Những scope yêu cầu |
| <code>authorizationUri(...)</code> | Authorization endpoint |
| <code>tokenUri(...)</code> | Token endpoint |
| <code>userInfoUri(...)</code> | Địa chỉ UserInfo của provider nếu dùng lấy thông tin người dùng |
| <code>userNameAttributeName(...)</code> | Thuộc tính định danh principal trong user info response của OAuth2 provider |
| <code>jwkSetUri(...)</code> | URI JWKS khi cần xác minh JWT/ID Token |
| <code>issuerUri(...)</code> | Issuer OP trong cấu hình có hỗ trợ trường này |
| <code>clientName(...)</code> | Tên hiển thị Client, hữu ích trên trang login |

Với một **OIDC provider** không công bố discovery metadata, phải bảo đảm ứng dụng có đủ thông tin để xác thực **issuer, chữ ký ID Token, audience** và những ràng buộc OIDC khác. Việc thêm scope <code>openid</code> vào ví dụ OAuth 2.0 thông thường không tự biến provider thành OIDC hoặc bảo đảm validation đúng.

### 4.1. Dùng CommonOAuth2Provider cho provider phổ biến

Spring Security còn cung cấp enum <code>CommonOAuth2Provider</code> với các builder được định nghĩa sẵn cho một số provider thông dụng. Ví dụ một registration Google:

~~~java
import org.springframework.security.config.oauth2.client.CommonOAuth2Provider;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Bean
ClientRegistrationRepository clientRegistrationRepository() {
    ClientRegistration google = CommonOAuth2Provider.GOOGLE
        .getBuilder("google")
        .clientId("replace-with-google-client-id")
        .clientSecret("replace-with-google-client-secret")
        .scope("openid", "profile", "email")
        .build();

    return new InMemoryClientRegistrationRepository(google);
}
~~~

Đây chỉ là một đoạn bean minh họa để đặt trong class <code>@Configuration</code>, **không được khai báo cùng lúc với các bean cùng tên/kiểu ở ví dụ khác**. Trên thực tế, nên inject credential từ secret manager hoặc thuộc tính cấu hình. Builder của provider thường điền sẵn các endpoint và cấu hình mặc định phù hợp, nhưng vẫn phải đăng ký OAuth Client và callback đúng với nhà cung cấp.

## 5. Nhiều provider trong cùng một InMemoryClientRegistrationRepository

Ứng dụng có thể cho người dùng đăng nhập bằng SSO doanh nghiệp và một provider bên ngoài. Khi đó tạo **hai ClientRegistration** với hai registration ID khác nhau:

~~~java
@Bean
ClientRegistrationRepository clientRegistrationRepository(
        @Value("${app.oidc.issuer-uri}") String issuer,
        @Value("${app.oidc.client-id}") String ssoClientId,
        @Value("${app.oidc.client-secret}") String ssoSecret,
        @Value("${app.google.client-id}") String googleClientId,
        @Value("${app.google.client-secret}") String googleSecret) {

    ClientRegistration sso = ClientRegistrations.fromIssuerLocation(issuer)
        .registrationId("company-sso")
        .clientId(ssoClientId)
        .clientSecret(ssoSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile")
        .build();

    ClientRegistration google = CommonOAuth2Provider.GOOGLE
        .getBuilder("google")
        .clientId(googleClientId)
        .clientSecret(googleSecret)
        .scope("openid", "profile", "email")
        .build();

    return new InMemoryClientRegistrationRepository(sso, google);
}
~~~

Đây là ví dụ thay thế các bean repository trước đó. Để sử dụng, import các class tương ứng từ các ví dụ trên và tạo thêm bốn thuộc tính <code>app.google.*</code>/<code>app.oidc.*</code> với giá trị bảo mật phù hợp.

Khi dùng <code>oauth2Login()</code> mặc định, ứng dụng có thể bắt đầu qua:

~~~text
/oauth2/authorization/company-sso
/oauth2/authorization/google
~~~

Callback mặc định:

~~~text
/login/oauth2/code/company-sso
/login/oauth2/code/google
~~~

Điều kiện quan trọng là **registrationId phải duy nhất** trong cùng repository. Không tạo hai registration với cùng ID rồi mong Spring tự chọn dựa trên hostname hoặc issuer. Nếu nhiều provider/tenant dùng chung một app, phải có cách chọn đúng registration từ đầu flow và kiểm tra token theo provider đã chọn.

### 5.1. Tra cứu ClientRegistration bằng Java

Ở một component khác trong ứng dụng, inject interface:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Service
public class ProviderInfoService {
    private final ClientRegistrationRepository registrations;

    public ProviderInfoService(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String authorizationEndpoint(String registrationId) {
        ClientRegistration registration =
                registrations.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown registrationId: " + registrationId);
        }

        return registration.getProviderDetails().getAuthorizationUri();
    }
}
~~~

Ví dụ này chỉ cho thấy cách lấy metadata của provider. Nó không thực hiện OAuth Authorization Request. Trong code xử lý đăng nhập thực tế, để Spring Security dùng OAuth2 authorization request resolver thay vì tự ghép URL thiếu <code>state</code>, PKCE hoặc những tham số bảo mật khác.

### 5.2. Duyệt các registration

Một đặc điểm của <code>InMemoryClientRegistrationRepository</code> là triển khai <code>Iterable&lt;ClientRegistration&gt;</code>. Có thể dùng trong thành phần được chủ động gắn với implementation này:

~~~java
for (ClientRegistration registration : inMemoryRepository) {
    String id = registration.getRegistrationId();
    String displayName = registration.getClientName();
    // Dùng id và displayName để dựng lựa chọn đăng nhập.
}
~~~

Trong ví dụ này, <code>inMemoryRepository</code> là biến có kiểu <code>InMemoryClientRegistrationRepository</code>. Interface <code>ClientRegistrationRepository</code> tự nó **không kế thừa Iterable**, vì vậy không nên ép tất cả các implementation khác đều có tính năng duyệt.

Không hiển thị <code>clientSecret</code> hoặc giá trị nhạy cảm nào trong giao diện chọn provider.

## 6. Quan hệ với Spring Boot auto-configuration

Khi khai báo cấu hình quen thuộc:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            client-id: some-client-id
            client-secret: some-client-secret
            scope: [openid, profile]
        provider:
          training:
            issuer-uri: https://login.example.org/realms/training
~~~

Spring Boot có thể tự tạo repository từ các properties này khi dependency và điều kiện auto-configuration phù hợp.

Khi ứng dụng **tự định nghĩa bean <code>ClientRegistrationRepository</code>**, auto-configuration thường **nhường** cho bean do ứng dụng cung cấp. Điều đó có nghĩa Boot không mặc nhiên gộp các registration trong YAML ở trên vào repository Java của bạn.

| Cách cấu hình | Ai tạo ClientRegistrationRepository? | Khi nào phù hợp? |
|---|---|---|
| Chỉ <code>spring.security.oauth2.client.*</code> | Spring Boot auto-configuration | Cấu hình đơn giản, ít Java code |
| Bean Java trả <code>InMemoryClientRegistrationRepository</code> | Ứng dụng | Cần điều kiện, tổ hợp nguồn cấu hình hoặc custom builder |
| Bean Java được dựng từ properties do ứng dụng bind | Ứng dụng | Muốn dùng Java logic nhưng vẫn quản lý dữ liệu trong file/env |
| Repository tự xây dựng từ database/secret store | Ứng dụng | Danh sách provider động, quản trị tập trung, yêu cầu nghiệp vụ riêng |

Nếu chọn Java configuration, cần chủ động thêm **tất cả** registration cần dùng vào bean đó hoặc xây dựng chính sách kết hợp rõ ràng. Không giả định khai báo <code>registration.google</code> trong YAML sẽ tự xuất hiện bên cạnh registration Java.

Tương tự, tránh tạo hai bean <code>ClientRegistrationRepository</code> không có qualifier/primary/phân giải rõ ràng. Các thành phần của Spring Security thường kỳ vọng một repository được chọn nhất quán.

## 7. In-memory registration có được dùng trong production không?

**Có**, nếu danh sách OAuth/OIDC Client được biết trước, cấu hình ổn định và mỗi lần khởi động ứng dụng có thể dựng lại đầy đủ metadata. Không cần database chỉ để chứa hai hoặc ba ClientRegistration cố định.

Tuy nhiên cần hiểu giới hạn:

- **Vòng đời:** repository được dựng lại khi ứng dụng khởi động; nó không cung cấp thao tác thêm/xóa registration động trong lúc chạy theo hợp đồng public API.
- **Triển khai nhiều instance:** mỗi instance có repository riêng. Cần đảm bảo cấu hình nhất quán giữa các instance và các môi trường.
- **Thay đổi credential:** khi client secret thay đổi, cần có chiến lược làm mới cấu hình/redeploy phù hợp. Repository không tự theo dõi secret store.
- **Discovery lúc startup:** nếu xây từ issuer và thư viện cần fetch metadata, ứng dụng có thể phụ thuộc vào khả năng truy cập OP khi khởi động.
- **Dữ liệu nhạy cảm:** <code>ClientRegistration</code> có thể chứa client secret trong memory. Không log toàn bộ object, không trả qua REST API và không đặt secret trực tiếp vào source code.

In-memory ở đây không phải lỗi bảo mật tự thân. Lựa chọn phụ thuộc vào yêu cầu cập nhật provider, vận hành, tính sẵn sàng và quản trị bí mật.

### 7.1. Phân biệt lưu registration và lưu token

~~~mermaid
flowchart LR
    A["ClientRegistrationRepository"] --> B["Metadata Client và provider"]
    C["OAuth2AuthorizedClientService / Repository"] --> D["Access token / refresh token theo principal"]
    E["HTTP Session / SecurityContext"] --> F["Trạng thái đăng nhập và authentication"]
    B --> G["Dùng khi tạo authorization request / token request"]
    D --> H["Dùng khi Client gọi API được bảo vệ"]
    F --> I["Dùng khi xác định người dùng đã đăng nhập"]
~~~

<code>InMemoryOAuth2AuthorizedClientService</code> là một lớp **khác hẳn** <code>InMemoryClientRegistrationRepository</code>. Lớp thứ nhất liên quan lưu các authorized client/token theo principal và registration ID; lớp thứ hai lưu định nghĩa các Client. Không suy luận token được chia sẻ giữa các instance chỉ vì dùng cùng provider registration.

Nếu ứng dụng server-side chạy nhiều instance và muốn chia sẻ trạng thái đăng nhập, cần cân nhắc session store, token persistence và các thành phần liên quan tùy kiến trúc, độc lập với lựa chọn repository metadata.

## 8. Những chi tiết cấu hình quan trọng

### 8.1. registrationId được dùng ở đâu?

<code>registrationId</code> là khóa nội bộ được dùng để:

1. Chọn provider từ URL bắt đầu đăng nhập: <code>/oauth2/authorization/{registrationId}</code>.
2. Kết nối callback mặc định: <code>/login/oauth2/code/{registrationId}</code>.
3. Tra cứu ClientRegistration cho token exchange và xử lý authorized client.
4. Chọn đúng cấu hình provider khi ứng dụng tích hợp nhiều OAuth 2.0/OIDC Client.

Tên ID không cần trùng <code>clientId</code> do nhà cung cấp cấp. Ví dụ nội bộ có thể gọi <code>company-sso</code> trong khi <code>clientId</code> là <code>hr-portal-prod-01</code>.

### 8.2. Redirect URI và reverse proxy

Mặc định Spring Security thường dùng URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Trong môi trường reverse proxy, <code>{baseUrl}</code> phải phản ánh hostname, scheme và port **bên ngoài**. Nếu ứng dụng thực tế chạy trên HTTPS nhưng backend chỉ nhìn thấy HTTP và host nội bộ, redirect URI có thể không khớp cấu hình đã đăng ký tại OP.

Cần cấu hình proxy/forwarded headers đúng với mô hình triển khai và chỉ tin forwarded headers từ proxy đáng tin cậy. Không sửa provider registration bằng cách cho phép wildcard redirect URI rộng để né lỗi callback.

### 8.3. Scope và phân biệt OAuth 2.0 với OIDC

Trong OIDC, scope phải có <code>openid</code>. Nếu không có <code>openid</code>, đây có thể là OAuth 2.0 Login thông thường và ứng dụng không nên kỳ vọng ID Token.

Với OIDC, issuer/JWKS và validation của ID Token rất quan trọng. Cấu hình provider bằng <code>fromIssuerLocation</code> giúp lấy metadata đáng tin cậy và để thư viện thực hiện xác minh tương ứng. Nếu tự khai báo endpoint, phải bảo đảm cấu hình validation đầy đủ.

Các scope khác như <code>profile</code>, <code>email</code> chỉ yêu cầu thêm thông tin; giá trị claim thực sự phụ thuộc provider, consent và chính sách cấp quyền.

### 8.4. Client authentication và PKCE

Một confidential web Client thường dùng <code>CLIENT_SECRET_BASIC</code> hoặc phương thức khác được provider đăng ký. Public Client không thể giữ bí mật client secret lâu dài và thường sử dụng <code>ClientAuthenticationMethod.NONE</code>.

Authorization Code + **PKCE S256** ràng buộc authorization code với client đã khởi tạo yêu cầu. Với public Client, Spring Security có cơ chế hỗ trợ PKCE phù hợp; với confidential Client có thể chủ động cấu hình PKCE qua authorization request customizer khi Authorization Server hỗ trợ.

Không đưa client secret vào JavaScript trình duyệt, URL đăng nhập hoặc log. Không coi PKCE là sự thay thế cho kiểm tra <code>state</code>, issuer, ID Token hay chính sách bảo mật token.

## 9. Lỗi thường gặp khi tự tạo repository

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| <code>/oauth2/authorization/training</code> không nhận provider | Bean không chứa <code>training</code>, registrationId khác chữ hoặc OAuth2 Login chưa được cấu hình | Kiểm tra ID của registration, bean được inject và <code>oauth2Login()</code> |
| Spring Boot properties có provider nhưng Java repository không thấy | Bean custom khiến auto-config không tự tạo/gộp repository từ YAML | Chủ động dựng registration đó trong Java hoặc dùng một hướng cấu hình nhất quán |
| Lỗi tạo bean lúc startup | <code>fromIssuerLocation</code> không truy cập được discovery, issuer metadata không khớp, TLS/DNS lỗi | Kiểm tra public issuer, kết nối mạng, chứng chỉ và metadata |
| Provider từ chối redirect URI | URI callback bị sai scheme/host/path hoặc chưa được đăng ký | Đối chiếu redirect URI thực tế với OP; kiểm tra reverse proxy |
| Token endpoint trả <code>invalid_client</code> | Client ID/secret sai hoặc authentication method không khớp | Kiểm tra registration tại OP, môi trường và cách xác thực Client |
| Có authorization code nhưng đổi token lỗi | Grant/callback/PKCE bị cấu hình sai, code hết hạn hoặc dùng lại | Kiểm tra flow và những thành phần Spring Security đang quản lý |
| Đăng nhập OAuth thành công nhưng không nhận <code>OidcUser</code> | Không có scope <code>openid</code> hoặc provider không phát ID Token OIDC | Xác nhận OP hỗ trợ OIDC và scope hợp lệ |
| Chữ ký hoặc issuer ID Token không hợp lệ | Metadata/JWKS sai, token đến từ provider khác hoặc claim không phù hợp | Dùng issuer chính thức, JWKS của issuer đó và validation chuẩn |
| Lỗi ambiguous bean | Có nhiều ClientRegistrationRepository bean và thiếu cơ chế chọn | Dọn cấu hình bean, đảm bảo thành phần dùng repository mong muốn |
| Nhiều instance có trạng thái người dùng khác nhau | Nhầm repository metadata với session/token persistence | Thiết kế session/authorized client persistence riêng |

### 9.1. Cách chẩn đoán theo chuỗi phụ thuộc

Khi người dùng không đăng nhập được, hãy lần lượt xem:

~~~text
registrationId hợp lệ?
    → tìm được ClientRegistration?
        → authorizationUri/tokenUri/redirectUri đúng?
            → OP chấp nhận Client?
                → Authorization Code Flow thành công?
                    → ID Token hợp lệ (với OIDC)?
                        → authentication/session hoàn tất?
~~~

Đừng in client secret, access token, refresh token, ID Token hoặc authorization code đầy đủ ra log để debug. Cách hữu ích hơn là ghi nhận loại lỗi, registration ID, thời điểm, endpoint loại nào gặp lỗi và correlation ID an toàn.

## 10. Bài tập thực hành

### Bài 1 — Một provider OIDC với Java config

Giả sử OP phát issuer <code>https://login.example.org/realms/training</code> và đã đăng ký Client ID <code>training-web</code>:

1. Tạo ứng dụng Spring Boot có OAuth2 Client starter.
2. Khai báo issuer, Client ID và secret trong thuộc tính riêng của ứng dụng/secret store.
3. Tạo <code>ClientRegistration</code> bằng <code>ClientRegistrations.fromIssuerLocation</code> và đặt ID <code>training</code>.
4. Trả về <code>new InMemoryClientRegistrationRepository(training)</code> từ bean Java.
5. Bật <code>oauth2Login()</code> và truy cập <code>/oauth2/authorization/training</code>.
6. Đối chiếu redirect URI đang gửi với redirect URI đã đăng ký tại OP, xác nhận ID Token được thư viện xác minh.

Điểm cần hiểu: <code>ClientRegistrationRepository</code> tham gia từ giai đoạn **chọn provider** cho đến cấu hình token exchange, không tự thực hiện xác thực người dùng.

### Bài 2 — Hai provider

Thêm <code>ClientRegistration</code> thứ hai với registration ID <code>google</code> hoặc một OP khác. Dùng một repository:

~~~java
return new InMemoryClientRegistrationRepository(training, secondProvider);
~~~

Quan sát hai URL bắt đầu đăng nhập, hai callback và việc ứng dụng chọn đúng registration ID. Không chia sẻ cùng một <code>clientSecret</code> cho các OP trừ khi đó là cấu hình được cấp phép chính thức; mỗi provider cần credential/registration riêng.

### Bài 3 — Tìm lỗi cấu hình

Một nhóm tạo repository Java chỉ chứa <code>company-sso</code>, nhưng vẫn khai báo <code>spring.security.oauth2.client.registration.google</code> trong YAML. URL <code>/oauth2/authorization/google</code> không hoạt động.

**Giải thích:** Repository do ứng dụng tự tạo là nguồn mà Spring Security nhận để tra cứu registration; YAML không mặc nhiên được merge vào bean ấy. Cần tự tạo/đưa registration <code>google</code> vào repository Java, hoặc thống nhất dùng Spring Boot auto-configuration nếu không cần logic Java riêng.

### Bài 4 — Phân biệt dữ liệu

Cho ba yêu cầu:

1. Lưu <code>clientId</code>, <code>authorizationUri</code>, <code>scope</code> của Google.
2. Lưu access token/refresh token được cấp cho người dùng đăng nhập.
3. Lưu trạng thái phiên HTTP sau khi người dùng xác thực.

**Lời giải:** (1) là phạm vi <code>ClientRegistrationRepository</code>; (2) thuộc <code>OAuth2AuthorizedClientService</code> hoặc <code>OAuth2AuthorizedClientRepository</code> tùy luồng; (3) thuộc session và SecurityContext strategy tương ứng. Không dùng <code>InMemoryClientRegistrationRepository</code> để giải quyết cả ba.

## 11. Ghi nhớ

- <code>ClientRegistration</code> mô tả **một** OAuth 2.0/OIDC Client; <code>ClientRegistrationRepository</code> cho phép tìm registration theo **<code>registrationId</code>**.
- <code>InMemoryClientRegistrationRepository</code> giữ các registration trong memory và hỗ trợ cả tra cứu lẫn duyệt danh sách, phù hợp với cấu hình provider tương đối tĩnh.
- Có thể dựng registration bằng **<code>ClientRegistrations.fromIssuerLocation(...)</code>** cho OIDC có discovery, **<code>ClientRegistration.withRegistrationId(...)</code>** cho cấu hình endpoint thủ công, hoặc **<code>CommonOAuth2Provider</code>** cho provider phổ biến.
- Khi tự cung cấp bean repository, Spring Boot thường nhường auto-configuration. Các registration trong YAML **không được tự động hợp nhất** vào bean Java.
- Repository metadata **không lưu token hoặc session**. Authorized client persistence, HTTP session, client secret management, TLS, issuer validation và PKCE là những trách nhiệm riêng cần thiết kế đúng.

### Tài liệu để tìm hiểu sâu hơn

- **Spring Security Reference — OAuth2 Client / OAuth2 Login:** cách cấu hình OAuth2 Client, ClientRegistrationRepository, authorization request và login.
- **Spring Security Java API:** <code>ClientRegistration</code>, <code>ClientRegistrations</code>, <code>ClientRegistrationRepository</code>, <code>InMemoryClientRegistrationRepository</code> và <code>CommonOAuth2Provider</code>.
- **Spring Boot Reference — OAuth2 Client:** ánh xạ properties và cơ chế auto-configuration.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Client Registration, Authorization Code Grant và Client authentication.
- **OpenID Connect Discovery 1.0** và **OpenID Connect Core 1.0:** issuer, discovery metadata và xác minh ID Token.
