# 5.6. ClientRegistrationRepository trong ứng dụng Servlet

## 1. Vai trò của ClientRegistrationRepository

Trong ứng dụng **Spring Boot sử dụng Spring MVC/Servlet**, Spring Security có thể đóng vai trò **OAuth 2.0 Client** để đưa người dùng đăng nhập qua một Authorization Server hoặc OpenID Provider (OIDC), sau đó dùng access token gọi API thay mặt người dùng. Trước khi bắt đầu luồng đăng nhập, ứng dụng phải biết **client nào đã đăng ký**, **nhà cung cấp nào phục vụ client đó**, **địa chỉ chuyển hướng** và **các scope cần yêu cầu**.

Spring Security biểu diễn cấu hình một OAuth 2.0 Client bằng đối tượng **`ClientRegistration`**. Nơi lưu và tra cứu các đối tượng ấy là **`ClientRegistrationRepository`**.

Hình dung một ứng dụng cho phép đăng nhập bằng SSO doanh nghiệp và một nhà cung cấp danh tính khác:

~~~text
                    Ứng dụng Spring Boot (Servlet)
                                  |
                                  v
                     ClientRegistrationRepository
                           /               \
                          v                 v
               registrationId=corp    registrationId=partner
                      |                      |
                      v                      v
                  Corporate IdP          Partner IdP
                  (OIDC Provider)        (OIDC Provider)
~~~

Mỗi registration chứa metadata của client và provider tương ứng; repository xác định registration theo một **`registrationId`** mà Spring Security nhận diện.

Ba điểm cần nắm ngay:

- **`ClientRegistration`** mô tả *một cấu hình OAuth2/OIDC Client*.
- **`ClientRegistrationRepository`** cung cấp phép tra cứu cấu hình theo `registrationId`.
- **`InMemoryClientRegistrationRepository`** là cách triển khai có sẵn, thường đủ cho ứng dụng có tập client cố định.

Repository này **không phải** database tài khoản người dùng, **không lưu session đăng nhập** và **không phải kho lưu access token/refresh token**. Những dữ liệu đó được quản lý bởi các thành phần khác.

## 2. ClientRegistration chứa những gì?

`ClientRegistration` là đối tượng cấu hình do Spring Security cung cấp trong package:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistration
~~~

Một registration điển hình chứa những thông tin sau:

| Thuộc tính | Vai trò |
|---|---|
| `registrationId` | Định danh nội bộ duy nhất trong repository; ví dụ `corp` hoặc `google`. |
| `clientId` | ID của ứng dụng được đăng ký tại Authorization Server. |
| `clientSecret` | Bí mật dành cho confidential client nếu nhà cung cấp cấp phát và yêu cầu. |
| `clientAuthenticationMethod` | Cách client xác thực với token endpoint, ví dụ `client_secret_basic` hoặc `client_secret_post`. |
| `authorizationGrantType` | Grant type; đối với đăng nhập người dùng thường là `authorization_code`. |
| `redirectUri` | Mẫu callback URI để Authorization Server trả trình duyệt về client. |
| `scopes` | Tập scope cần xin, ví dụ `openid`, `profile`, `email` hoặc scope API. |
| `authorizationUri` | Authorization endpoint của provider. |
| `tokenUri` | Token endpoint để đổi authorization code lấy token. |
| `jwkSetUri` | Nơi công bố JWK Set, thường được dùng xác minh chữ ký JWT/ID Token. |
| `issuerUri` | Định danh issuer của OIDC Provider, dùng để ràng buộc nguồn phát hành. |
| `userInfoUri` | OIDC UserInfo endpoint khi provider hỗ trợ. |
| `userNameAttributeName` | Claim/attribute dùng làm tên định danh principal trong bối cảnh tương ứng. |
| `clientName` | Tên hiển thị của registration; thường dùng cho đường dẫn lựa chọn đăng nhập. |

Không phải provider nào cũng hỗ trợ mọi endpoint hoặc mọi scope. Cấu hình phải phản ánh metadata và điều kiện đăng ký client **thực tế** của nhà cung cấp. Với OIDC, scope `openid` khiến yêu cầu mang ý nghĩa đăng nhập OIDC và ID Token trở thành một phần của kết quả xác thực.

### 2.1. Phân biệt registrationId, clientId và issuer

Ba định danh hay bị nhầm:

~~~text
registrationId : corp
clientId       : web-portal-production
issuerUri      : https://identity.example.com/realms/employees
~~~

- `registrationId = corp` do **ứng dụng Spring Security** chọn để tham chiếu cấu hình. Nó xuất hiện trong URL mặc định của ứng dụng như `/oauth2/authorization/corp`.
- `clientId = web-portal-production` do **Authorization Server** cấp trong quá trình đăng ký OAuth2 Client. Nó đi trong authorization request và tham gia các bước xác thực client.
- `issuerUri` xác định **OpenID Provider** đáng tin cậy; ID Token cần có issuer khớp với cấu hình tương ứng.

Chúng có thể có chuỗi giống nhau trong một trường hợp cụ thể nhưng về bản chất là ba vai trò khác nhau. Việc đổi `registrationId` trong Spring mà không cập nhật đường dẫn đăng nhập và callback có thể khiến luồng đăng nhập không tìm đúng client registration.

### 2.2. Một provider có thể có nhiều client registration

Ví dụ ứng dụng có hai client khác nhau trên cùng một OIDC Provider:

| registrationId | clientId | Scope | Mục đích |
|---|---|---|---|
| `employee-login` | `employee-web` | `openid profile email` | Đăng nhập nhân viên. |
| `admin-login` | `admin-web` | `openid profile email` | Đăng nhập qua client dành cho quản trị viên. |

Cả hai có thể cùng issuer và endpoint nhưng khác client ID, redirect URI, chính sách hoặc scope. Vì vậy **repository lưu client registration**, không phải chỉ lưu danh sách tên provider.

Ngược lại, nhiều provider khác nhau có thể được khai báo trong cùng một repository, mỗi provider tương ứng một hoặc nhiều registration.

## 3. Hợp đồng của ClientRegistrationRepository

Interface `ClientRegistrationRepository` thuộc package:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistrationRepository
~~~

Hợp đồng trọng tâm:

~~~java
public interface ClientRegistrationRepository {
    ClientRegistration findByRegistrationId(String registrationId);
}
~~~

Khi Spring Security cần cấu hình của registration `corp`, nó gọi:

~~~java
ClientRegistration registration =
    clientRegistrationRepository.findByRegistrationId("corp");
~~~

Nếu có registration tương ứng, repository trả đối tượng `ClientRegistration`. Nếu không có, phương thức có thể trả `null`; code gọi phải xử lý tình huống không tìm thấy. Interface không bắt buộc cung cấp các thao tác thêm/sửa/xóa registration và cũng không quy định rằng các cấu hình phải nằm trong database.

### 3.1. Vì sao chỉ cần tìm theo registrationId?

Trong luồng authorization code điển hình:

1. Người dùng đi đến `/oauth2/authorization/corp`.
2. Spring Security trích `corp` làm `registrationId`.
3. Hệ thống tra cứu `ClientRegistrationRepository.findByRegistrationId("corp")`.
4. Registration cung cấp `clientId`, authorization endpoint, scope, callback template và các trường cần thiết.
5. Spring Security xây dựng authorization request và chuyển hướng trình duyệt đến provider.
6. Khi callback quay lại, luồng tiếp tục dùng dữ liệu của chính registration đó để trao đổi code.

Thực tế Spring Security còn lưu yêu cầu ủy quyền và kiểm tra `state`, PKCE cùng các điều kiện giao thức liên quan. `ClientRegistrationRepository` chỉ đảm nhiệm **phần cấu hình client** trong toàn bộ quy trình.

### 3.2. Repository tồn tại ở cấp ứng dụng, không phải từng người dùng

Các registration như `corp` hoặc `partner` thường được khai báo khi ứng dụng khởi động, dùng chung cho các yêu cầu đăng nhập khác nhau. Một người dùng A và người dùng B có thể đăng nhập qua cùng một registration nhưng vẫn có **phiên đăng nhập và token riêng**. Repository không tạo một bản sao `ClientRegistration` cho mỗi người dùng.

## 4. InMemoryClientRegistrationRepository

Spring Security có triển khai cơ bản:

~~~java
org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository
~~~

`InMemoryClientRegistrationRepository` giữ các `ClientRegistration` trong bộ nhớ của tiến trình ứng dụng và tra cứu bằng `registrationId`. Đây là lựa chọn phù hợp khi:

- Ứng dụng có một hoặc một số OAuth2/OIDC provider đã biết.
- Danh sách registration chủ yếu thay đổi qua cấu hình và quá trình triển khai.
- Không cần quản trị registration động khi ứng dụng đang chạy.
- Có thể bảo vệ client secret qua môi trường và hệ thống quản lý bí mật.

Ví dụ khởi tạo từ hai registration đã xây dựng:

~~~java
ClientRegistrationRepository repository =
    new InMemoryClientRegistrationRepository(corpRegistration, partnerRegistration);
~~~

Repository trong bộ nhớ **không có nghĩa access token bị lưu trong cùng map này**. Cần phân biệt rõ cấu hình đăng ký client và các token được cấp cho người dùng.

### 4.1. InMemoryClientRegistrationRepository và Iterable

Bên cạnh việc triển khai `ClientRegistrationRepository`, `InMemoryClientRegistrationRepository` còn triển khai `Iterable<ClientRegistration>`. Điều này cho phép duyệt các registration mà repository chứa:

~~~java
for (ClientRegistration registration : inMemoryRepository) {
    System.out.println(registration.getRegistrationId());
}
~~~

Với trang đăng nhập mặc định do Spring Security tạo khi sử dụng `oauth2Login()`, repository có khả năng duyệt (`Iterable<ClientRegistration>`) giúp framework khám phá các lựa chọn đăng nhập. Nếu dùng repository tự viết chỉ triển khai `findByRegistrationId`, các link đăng nhập tự động trên trang mặc định có thể không xuất hiện như mong đợi.

Việc hỗ trợ `Iterable` không có nghĩa interface `ClientRegistrationRepository` bắt buộc phải triển khai nó. Hãy phân biệt:

~~~text
ClientRegistrationRepository
    └─ findByRegistrationId(registrationId)

InMemoryClientRegistrationRepository
    ├─ findByRegistrationId(registrationId)
    └─ Iterable<ClientRegistration>
~~~

Không dùng tính năng duyệt registration để vô tình xuất thông tin nhạy cảm, đặc biệt `clientSecret`, ra endpoint công khai hoặc log.

## 5. Cách Spring Boot tạo repository từ application.yml

Đối với một ứng dụng Spring Boot Servlet, cách phổ biến nhất là **khai báo registration trong cấu hình Boot**. Khi các điều kiện auto-configuration phù hợp và chưa có bean `ClientRegistrationRepository` do ứng dụng tự cung cấp, Spring Boot có thể tạo một `InMemoryClientRegistrationRepository` từ `spring.security.oauth2.client.registration.*` và thông tin provider liên quan.

Giả sử ứng dụng phục vụ đăng nhập qua OIDC provider `https://identity.example.com/realms/employees`.

### 5.1. Thêm dependency cho Servlet web application

Ví dụ Maven — Spring Boot 3.x:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ Gradle — Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

**Lưu ý phiên bản:** Trong Spring Boot 4.x, tên starter MVC và OAuth2 Client được tổ chức lại. Các artifact tương ứng được khuyến nghị là `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`. Các ví dụ cấu hình Java trong bài vẫn minh họa ứng dụng Servlet; dự án cần dùng BOM/plugin cùng dòng Boot để quản lý phiên bản thư viện cho nhất quán.

### 5.2. Khai báo một registration OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: Corporate SSO
        provider:
          corporate-idp:
            issuer-uri: https://identity.example.com/realms/employees
~~~

Giải thích cách Spring Boot hiểu cấu hình:

| Cấu hình | Kết quả trong ClientRegistration |
|---|---|
| `registration.corp` | Tạo registration có `registrationId = "corp"`. |
| `provider: corporate-idp` | Liên kết registration đến thông tin provider mang khóa `corporate-idp`. |
| `client-id` | Đặt client ID đã được IdP cấp. |
| `client-secret` | Đặt secret cho confidential client; ví dụ lấy từ biến môi trường. |
| `authorization-grant-type` | Xác định authorization code grant. |
| `redirect-uri` | Mẫu callback; `{registrationId}` được thay bằng `corp`. |
| `scope` | Yêu cầu OIDC và các scope thông tin người dùng. |
| `provider.corporate-idp.issuer-uri` | Dùng issuer để khám phá metadata OIDC khi nhà cung cấp hỗ trợ. |

Biến `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` phải được cung cấp theo môi trường của ứng dụng. Không đặt client secret thực tế vào Git hoặc ví dụ đào tạo.

Với domain public `https://app.example.com`, callback mặc định của registration trên là:

~~~text
https://app.example.com/login/oauth2/code/corp
~~~

Hãy đăng ký URI đó tại provider. Khi chạy cục bộ, callback có thể dùng `http://localhost:8080/login/oauth2/code/corp` nếu provider cho phép redirect HTTP trên localhost.

### 5.3. Spring Boot tạo những gì?

Ở cấu hình phù hợp, Spring Boot đọc nhóm properties và tạo bean repository chứa `ClientRegistration` tương ứng. Ứng dụng có thể inject interface mà không tự viết constructor `InMemoryClientRegistrationRepository`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Service
public class OAuthProviderInfoService {

    private final ClientRegistrationRepository registrations;

    public OAuthProviderInfoService(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String getProviderDisplayName(String registrationId) {
        ClientRegistration registration =
            registrations.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                "Unknown registrationId: " + registrationId);
        }

        return registration.getClientName();
    }
}
~~~

Service chỉ đọc **tên hiển thị** của registration, không xuất client secret. Ví dụ nhằm minh họa phép lookup, không ngụ ý tên provider là một quyết định phân quyền an toàn.

### 5.4. Nhiều registration từ application.yml

Một repository có thể chứa nhiều client registrations:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: company-oidc
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            scope:
              - openid
              - profile
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope:
              - openid
              - email
        provider:
          company-oidc:
            issuer-uri: https://login.corp.example.com
          partner-oidc:
            issuer-uri: https://login.partner.example.com
~~~

Trong cấu hình trên, Spring Boot nhận diện **hai** `registrationId`: `corp` và `partner`. URI đăng nhập mặc định tương ứng là:

~~~text
/oauth2/authorization/corp
/oauth2/authorization/partner
~~~

Các registration dùng chung repository nhưng vẫn có client ID, issuer và scope riêng. Nếu nhà cung cấp yêu cầu callback cụ thể, hãy đặt `redirect-uri` cho từng registration và đăng ký chính xác URI đó.

## 6. Tích hợp repository với SecurityFilterChain của ứng dụng Servlet

Ứng dụng Servlet dùng `HttpSecurity` và `SecurityFilterChain`. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Với cấu hình trên:

- `oauth2Login()` cho phép người dùng đăng nhập qua provider và thiết lập ngữ cảnh xác thực của ứng dụng.
- `oauth2Client()` cung cấp tích hợp hỗ trợ dùng authorized client khi cần gọi API bằng access token.
- Khi luồng yêu cầu `registrationId = corp`, các thành phần OAuth2 Client tra cứu `ClientRegistrationRepository` để lấy metadata cần thiết.

Hai phương thức cấu hình liên quan nhưng không thay thế nhau. Một ứng dụng chỉ đăng nhập người dùng có thể tập trung vào `oauth2Login()`; nếu còn cần gọi API bên ngoài, `oauth2Client()` và cơ chế quản lý authorized clients thường là phần bổ sung cần thiết.

### 6.1. Sơ đồ luồng tra cứu repository

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Trình duyệt
    participant S as Spring Security Servlet
    participant R as ClientRegistrationRepository
    participant OP as Authorization Server / OIDC Provider

    B->>S: GET /oauth2/authorization/corp
    S->>R: findByRegistrationId("corp")
    R-->>S: ClientRegistration(corp)
    Note over S: Tạo authorization request từ metadata
    S-->>B: 302 tới authorization endpoint
    B->>OP: Authorization request
    OP->>B: Xác thực / consent
    OP-->>B: 302 callback?code=...&state=...
    B->>S: GET /login/oauth2/code/corp
    Note over S: Đối chiếu authorization request/state đã lưu
    S->>OP: POST token endpoint (authorization code)
    OP-->>S: Access token + ID Token nếu là OIDC
    Note over S: Xác minh token, tạo Authentication và phiên
    S-->>B: Chuyển tới trang đã yêu cầu
~~~

`ClientRegistrationRepository` tham gia trong khâu xác định cấu hình client. Nó **không tự kiểm tra state**, không tự thực hiện authorization code exchange và không tự tạo session. Các filter và authentication provider của Spring Security sử dụng nó như một phụ thuộc cấu hình.

### 6.2. Endpoint Spring Security gắn với registrationId

Theo mặc định khi dùng `oauth2Login()`:

| Đường dẫn | Chức năng |
|---|---|
| `/oauth2/authorization/{registrationId}` | Điểm bắt đầu authorization request ở ứng dụng. |
| `/login/oauth2/code/{registrationId}` | Callback nhận authorization response. |

Ví dụ `registrationId = corp`:

~~~text
GET /oauth2/authorization/corp
GET /login/oauth2/code/corp?code=...&state=...
~~~

Các đường dẫn này có thể được tùy chỉnh. Nếu tùy chỉnh authorization base URI hoặc callback URI, cần cấu hình Spring Security, `redirectUri` và callback đã đăng ký ở provider sao cho nhất quán. Đừng giả định chỉ cần đổi tên URL mà không ảnh hưởng lookup và routing.

## 7. Khai báo ClientRegistrationRepository thủ công

Khi muốn kiểm soát cách xây dựng client registration, có thể định nghĩa trực tiếp bean `ClientRegistrationRepository` thay vì khai báo toàn bộ qua Spring Boot properties.

Việc này phù hợp khi:

- Cấu hình được cấp bởi một lớp nội bộ đã có.
- Phải tổng hợp nhiều nguồn cấu hình đã được xác thực và tin cậy.
- Cần tạo registration bằng builder hoặc áp dụng logic thiết lập nâng cao.
- Dự án không dùng cơ chế property binding mặc định của Spring Boot.

### 7.1. Tạo từ OIDC Discovery

Nếu OpenID Provider hỗ trợ discovery tại issuer URI đã tin cậy, dùng `ClientRegistrations.fromIssuerLocation(...)` để lấy metadata provider, sau đó gắn thông tin client của ứng dụng:

~~~java
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
public class ClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.oidc.issuer}") String issuer,
            @Value("${app.oidc.client-id}") String clientId,
            @Value("${app.oidc.client-secret}") String clientSecret) {

        ClientRegistration corp = ClientRegistrations
            .fromIssuerLocation(issuer)
            .registrationId("corp")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .clientName("Corporate SSO")
            .build();

        return new InMemoryClientRegistrationRepository(corp);
    }
}
~~~

Các property tương ứng có thể khai báo:

~~~yaml
app:
  oidc:
    issuer: https://identity.example.com/realms/employees
    client-id: ${OIDC_CLIENT_ID}
    client-secret: ${OIDC_CLIENT_SECRET}
~~~

Những điều cần hiểu:

- `fromIssuerLocation(issuer)` sử dụng discovery endpoint tương ứng để xây dựng metadata; issuer phải được cấu hình tin cậy, không lấy tùy ý từ request của người dùng.
- `registrationId("corp")` xác định khóa tra cứu nội bộ.
- `clientId` và `clientSecret` đến từ đăng ký client tại provider.
- `clientAuthenticationMethod` phải đúng phương thức mà provider đã đăng ký/cho phép.
- `redirectUri` phải đúng với URI được phép tại provider.
- `InMemoryClientRegistrationRepository(corp)` lưu registration để Spring Security tra cứu.

Đây là **phương án thay thế** cho cách để Spring Boot tự tạo repository từ `spring.security.oauth2.client.registration.*`. Trong cùng một ứng dụng, hãy chọn cách sở hữu bean rõ ràng; nếu đã tự cung cấp bean `ClientRegistrationRepository`, Boot thường không tạo thêm repository mặc định từ properties.

Discovery có thể thực hiện các HTTP request để lấy metadata khi bean được tạo. Vì vậy issuer cần khả dụng và đáng tin cậy; lỗi mạng, chứng chỉ hoặc metadata có thể làm quá trình khởi tạo thất bại. Không coi discovery là việc khám phá issuer tùy ý theo dữ liệu người dùng gửi vào.

### 7.2. Tạo từ ClientRegistration.Builder khi không dùng discovery

Nếu provider có metadata cố định hoặc không cung cấp discovery tương thích, có thể khai báo các endpoint rõ ràng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class ExplicitClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.oidc.client-id}") String clientId,
            @Value("${app.oidc.client-secret}") String clientSecret) {

        ClientRegistration corp = ClientRegistration
            .withRegistrationId("corp")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .authorizationUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/auth")
            .tokenUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/token")
            .jwkSetUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/certs")
            .issuerUri("https://identity.example.com/realms/employees")
            .userInfoUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/userinfo")
            .userNameAttributeName("sub")
            .clientName("Corporate SSO")
            .build();

        return new InMemoryClientRegistrationRepository(corp);
    }
}
~~~

Các endpoint trên **chỉ minh họa một kiểu URL thường thấy**, không phải URL đúng cho mọi OIDC Provider. Trước khi dùng phải đối chiếu discovery metadata hoặc tài liệu của nhà cung cấp thật. Nếu provider yêu cầu một client authentication method khác, thay cho phù hợp; không dùng `client_secret_basic` theo mặc định khi đăng ký thực tế không cho phép.

Hai ví dụ trong mục 7.1 và 7.2 cùng định nghĩa bean tên `clientRegistrationRepository`; **không đưa cả hai class vào chung một ứng dụng**. Chọn một cách khởi tạo cho repository.

### 7.3. Đăng ký nhiều client thủ công

Khi đã có nhiều `ClientRegistration`:

~~~java
@Bean
ClientRegistrationRepository clientRegistrationRepository(
        ClientRegistration corp,
        ClientRegistration partner) {

    return new InMemoryClientRegistrationRepository(corp, partner);
}
~~~

Đoạn code trên chỉ minh họa cách gom hai đối tượng được tạo từ nguồn cấu hình hợp lệ; `corp` và `partner` phải có `registrationId` khác nhau. Đừng nhầm kiểu `ClientRegistration` với tên String của provider.

Một biến thể rõ ràng khi tự lắp ráp trong cùng method:

~~~java
ClientRegistrationRepository repository =
    new InMemoryClientRegistrationRepository(
        corpRegistration,
        partnerRegistration
    );
~~~

Spring Security tra cứu được các registration bằng ID độc lập, đồng thời vẫn có thể duyệt danh sách khi repository hỗ trợ `Iterable`.

## 8. Repository nào lưu gì trong Spring Security OAuth2 Client?

Đây là phần dễ gây nhầm nhất khi học `ClientRegistrationRepository`. Spring Security còn có các repository/service khác nhau, nhưng chúng giải quyết những vấn đề khác nhau.

| Thành phần | Thứ được lưu/tra cứu | Khóa/đầu vào điển hình | Phạm vi |
|---|---|---|---|
| **`ClientRegistrationRepository`** | Metadata cấu hình OAuth2/OIDC Client | `registrationId` | Cấu hình dùng chung của ứng dụng. |
| **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`** | Yêu cầu ủy quyền đang tiến hành, gồm `state` và dữ liệu tương quan | Request/response và phiên HTTP | Tạm thời trong quá trình redirect/callback. |
| **`OAuth2AuthorizedClientRepository`** | Authorized client gắn với principal và request | `registrationId` + principal + request/response | Ngữ cảnh Servlet/web và người dùng. |
| **`OAuth2AuthorizedClientService`** | Authorized client đã được cấp token | `clientRegistrationId` + principal name | Lớp service lưu authorized clients; có thể dùng in-memory hoặc persistence khác. |
| **`HttpSession` / `SecurityContextRepository`** | Ngữ cảnh xác thực/phiên của ứng dụng | Session/cookie và security context | Phiên người dùng đăng nhập ứng dụng. |

### 8.1. ClientRegistration không phải OAuth2AuthorizedClient

`ClientRegistration` là bản cấu hình tĩnh:

~~~text
registrationId: corp
clientId: web-portal
tokenUri: https://identity.example.com/.../token
scope: openid profile email
~~~

`OAuth2AuthorizedClient` lại đại diện cho một authorization đã được cấp cho một principal, gắn với registration và các token:

~~~text
clientRegistration: corp
principalName: alice
accessToken: ...
refreshToken: ... (nếu có)
~~~

Hai người dùng cùng đăng nhập `corp` sẽ cùng dùng **một cấu hình `ClientRegistration`** nhưng mỗi người có thể có **`OAuth2AuthorizedClient` riêng** chứa token khác nhau. Vì thế không nhét access token vào cấu hình registration và không dùng repository cấu hình làm nơi lưu token.

### 8.2. AuthorizationRequestRepository không phải ClientRegistrationRepository

Khi Spring Security redirect trình duyệt sang IdP, framework thường phải lưu authorization request đã tạo để lúc callback kiểm tra `state` và thông tin liên quan. Trong ứng dụng Servlet, một triển khai phổ biến là `HttpSessionOAuth2AuthorizationRequestRepository`.

Repository này lưu **giao dịch đăng nhập đang diễn ra**, không lưu metadata client lâu dài. Nếu phiên HTTP hoặc dữ liệu authorization request mất giữa lúc redirect và callback, người dùng có thể gặp lỗi state/missing authorization request dù `ClientRegistrationRepository` vẫn chứa đầy đủ thông tin client.

### 8.3. ClientRegistrationRepository không quyết định quyền của người dùng

Registration cung cấp cấu hình OAuth2 và scope yêu cầu, nhưng nó không thay thế việc xác định người dùng đã được xác thực là ai, role trong ứng dụng là gì, hoặc access token có quyền truy cập API cụ thể hay không.

Ví dụ `scope: openid profile email` không cấp quyền quản trị viên cho người dùng. Ứng dụng vẫn cần ánh xạ authorities và áp dụng authorization policy dựa trên dữ liệu đáng tin cậy.

## 9. Hợp tác với OAuth2AuthorizedClientService và OAuth2AuthorizedClientManager

Khi backend Servlet gọi API bằng access token, nó có thể lấy một authorized client nhờ `OAuth2AuthorizedClientService` hoặc `OAuth2AuthorizedClientManager`. Các thành phần ấy phụ thuộc gián tiếp hoặc trực tiếp vào `ClientRegistrationRepository` để biết client nào được cấu hình.

Luồng khái niệm:

~~~text
                    ClientRegistrationRepository
                               |
                               | ClientRegistration
                               v
               OAuth2AuthorizedClientManager
                     /                  \
                    v                    v
        OAuth2AuthorizedClient     Token endpoint
          (access/refresh token)   của Provider
                    |
                    v
           HTTP client gọi API
~~~

Ở ứng dụng Servlet, giao diện manager được dùng là:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager
~~~

Với ứng dụng WebFlux, họ API tương ứng mang tiền tố reactive, ví dụ `ReactiveClientRegistrationRepository` và `ReactiveOAuth2AuthorizedClientManager`. Không import chúng vào cấu hình Servlet rồi mong Spring tự chuyển đổi.

### 9.1. Chỉ cần repository là đã tự động xin được access token?

Chưa. Repository trả metadata như client ID, endpoints và scopes. Để có access token cho người dùng, ứng dụng phải đi qua một **grant flow** hợp lệ, ví dụ Authorization Code Grant với người dùng đăng nhập/ủy quyền. Nếu cần làm mới token, cơ chế authorized client cần có refresh token và provider cho phép.

Một cách hình dung:

~~~text
ClientRegistrationRepository:
    "Ứng dụng corp được đăng ký như thế nào?"

OAuth2AuthorizedClientRepository/Service:
    "Alice đã cấp quyền cho client corp chưa, và token đã lưu là gì?"

OAuth2AuthorizedClientManager:
    "Khi ứng dụng cần một authorized client, xử lý thế nào?"
~~~

Không gán nhiệm vụ của token manager hoặc token storage cho `ClientRegistrationRepository`.

## 10. Truy xuất ClientRegistration trong mã Java

Một use case hợp lý là cần xác định tên hiển thị, scope được khai báo hoặc endpoint của một registration để hỗ trợ cấu hình UI/quản trị nội bộ.

~~~java
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Service
public class RegistrationCatalog {

    private final ClientRegistrationRepository repository;

    public RegistrationCatalog(ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public String providerName(String registrationId) {
        ClientRegistration client =
            repository.findByRegistrationId(registrationId);

        if (client == null) {
            throw new IllegalArgumentException(
                "Unknown OAuth2 registration: " + registrationId);
        }

        return client.getClientName();
    }

    public Set<String> declaredScopes(String registrationId) {
        ClientRegistration client =
            repository.findByRegistrationId(registrationId);

        if (client == null) {
            throw new IllegalArgumentException(
                "Unknown OAuth2 registration: " + registrationId);
        }

        return client.getScopes();
    }
}
~~~

Nội dung `getScopes()` là **các scope client được cấu hình để yêu cầu**, không mặc nhiên là các scope access token thực tế đã được cấp cho từng user. Authorization Server có thể thu hẹp phạm vi. Muốn biết scope của token đã cấp, đọc thông tin authorized client/access token tương ứng.

### 10.1. Đừng trả trực tiếp ClientRegistration ra API công khai

Đối tượng có thể chứa `clientSecret` và metadata nhạy cảm. Không làm như sau:

~~~java
// KHÔNG NÊN: có nguy cơ đưa secret ra HTTP response.
@GetMapping("/debug/registration/{id}")
ClientRegistration debug(@PathVariable String id) {
    return repository.findByRegistrationId(id);
}
~~~

Nếu cần API hiển thị danh sách lựa chọn đăng nhập, tạo DTO chỉ gồm các trường public thực sự cần thiết, chẳng hạn `registrationId` và `clientName`. Cần cân nhắc xem thông tin provider có nên công khai trong ứng dụng hay không.

### 10.2. Không tin registrationId do client tự gửi một cách vô điều kiện

`registrationId` trong URL là một **selector**, không phải bằng chứng quyền truy cập hoặc cho phép truy cập provider tùy ý. Nếu hệ thống hỗ trợ nhiều IdP, cần hạn chế danh sách registration được phép dùng theo chính sách của ứng dụng, tenant hoặc người dùng.

Nếu tự xây repository động, tuyệt đối không xem một giá trị issuer hoặc URL do request cung cấp là địa chỉ tin cậy để tự động discovery mà không kiểm soát. Việc này có thể mở ra rủi ro SSRF, issuer mix-up hoặc đăng nhập vào IdP không được phép.

## 11. Cấu hình registration qua properties và bean thủ công: khi nào chọn cách nào?

| Tiêu chí | Spring Boot properties | Bean `InMemoryClientRegistrationRepository` thủ công |
|---|---|---|
| Cấu hình một vài provider cố định | Rất phù hợp | Phù hợp nhưng nhiều code hơn. |
| Dễ thay đổi client ID/secret theo môi trường | Dùng environment/property placeholders | Dùng `@Value` hoặc cơ chế config injection. |
| Sử dụng OIDC Discovery | Khai báo `issuer-uri` | `ClientRegistrations.fromIssuerLocation(...)`. |
| Cần áp dụng logic dựng registration riêng | Có giới hạn tùy property | Linh hoạt nhờ builder. |
| Dễ bảo trì các giá trị cấu hình đơn giản | Cao | Cần duy trì thêm Java config. |
| Thay registration ngay khi chạy | Không tự động chỉ vì file property thay đổi | Cũng không tự động nếu dùng in-memory bean cố định. |
| Tích hợp `oauth2Login()` | Có | Có, nếu bean và metadata hợp lệ. |

Đối với phần lớn ứng dụng Spring Boot Servlet, **properties + auto-configuration** là lựa chọn khởi đầu rõ ràng. Bean thủ công phù hợp khi có nhu cầu cụ thể về cách xây dựng hoặc cung cấp registration.

### 11.1. Nếu cần multi-tenant hoặc cấu hình động

Một ứng dụng phục vụ nhiều tổ chức có thể cần tạo registration theo tenant hoặc lấy cấu hình từ kho dữ liệu nội bộ. Khi đó có thể triển khai `ClientRegistrationRepository` riêng, bảo đảm:

- Mỗi `registrationId` ánh xạ nhất quán đến client ID, issuer và endpoints đã được quản trị.
- Các nguồn cấu hình được xác thực; không cho request tự xác định issuer/secret tùy ý.
- Luồng callback có thể tìm lại đúng registration đã dùng khi khởi tạo.
- Secrets được lưu an toàn và có cơ chế rotation phù hợp.
- Khi thay đổi cấu hình, cần cân nhắc các authorization flow đang diễn ra, tránh sửa registration khiến callback không thể xác minh.
- Nếu dựa vào trang login được Spring Security sinh tự động, xem xét yêu cầu `Iterable<ClientRegistration>`; hoặc tự xây trang login liệt kê lựa chọn đã được phép.
- Các tầng cache, cập nhật và đồng bộ phải được thiết kế cẩn thận, nhất là trong môi trường nhiều instance.

Việc đổi `ClientRegistrationRepository` thành repository đọc database chỉ giải quyết **nguồn cấu hình client**. Nó không biến `OAuth2AuthorizedClientService` hoặc HTTP session thành persistence tự động. Cần thiết kế riêng các nhu cầu lưu token và quản lý phiên.

## 12. Spring Security sử dụng repository qua những thành phần nào?

Trong luồng OAuth2/OIDC Client Servlet, các thành phần quan trọng gồm:

| Thành phần | Cách liên quan tới ClientRegistrationRepository |
|---|---|
| `OAuth2AuthorizationRequestRedirectFilter` | Dùng repository gián tiếp qua resolver để xây dựng authorization request dựa trên registration ID. |
| `DefaultOAuth2AuthorizationRequestResolver` | Tra `ClientRegistrationRepository` theo ID để lấy metadata và tạo OAuth2 authorization request. |
| `OAuth2LoginAuthenticationFilter` | Nhận authorization response/callback rồi tiến hành quy trình xác thực thông qua authentication manager/provider. |
| `OAuth2LoginAuthenticationProvider` và `OidcAuthorizationCodeAuthenticationProvider` | Tham gia xử lý authorization code và token response theo loại OAuth2/OIDC login. |
| `OAuth2AuthorizedClientRepository` | Lưu authorized client cho principal sau khi token được cấp; giữ dữ liệu khác với repository registration. |
| `OAuth2AuthorizedClientService` | Truy xuất các authorized client đã cấp token trong trường hợp dùng service. |

Những tên lớp hỗ trợ giải thích kiến trúc, không có nghĩa ứng dụng phải tạo bean cho từng class. Cấu hình `oauth2Login()` của Spring Security thường dựng chuỗi filter và provider mặc định từ các dependency và bean cần thiết.

### 12.1. Thay đổi authorization base URI phải giữ registration lookup

Ví dụ ứng dụng muốn khởi tạo đăng nhập từ `/login/sso/corp` thay vì `/oauth2/authorization/corp`. Có thể cấu hình một authorization request resolver hoặc base URI phù hợp với phiên bản Spring Security đang dùng.

Dù URL đổi, **registrationId vẫn phải được nhận diện đúng** để resolver gọi `findByRegistrationId("corp")`. Nếu cấu hình sai, request có thể 404, không redirect hoặc báo registration không tìm thấy.

Không sửa đường dẫn callback một cách độc lập với redirect URI đã đăng ký ở provider; Authorization Server có thể từ chối callback sai ngay trong bước authorize.

## 13. Vai trò của repository trong OIDC và OAuth2 thuần

`ClientRegistrationRepository` là cấu trúc **chung** cho OAuth2 Client. Nó không chỉ tồn tại trong ứng dụng OIDC.

| Trường hợp | ClientRegistration chứa gì? | Principal/đích sử dụng |
|---|---|---|
| OAuth2 Login không có `openid` | Client ID, grant type, scope API, endpoints, user info nếu dùng | OAuth2 principal theo cách tích hợp provider. |
| OIDC Login với `openid` | Thêm issuer/JWK metadata phù hợp để xử lý ID Token | `OidcUser` và ID Token đã được xử lý theo OIDC. |
| OAuth2 Client gọi API bằng authorization code | Client registration và access token được lưu riêng trong authorized client | Gọi resource server thay mặt người dùng. |
| Service-to-service dùng `client_credentials` | Client registration cho client credentials grant | Token của client/service, không đại diện một đăng nhập OIDC có người dùng. |

Cùng một interface `ClientRegistrationRepository` có thể chứa registration cho nhiều loại grant, nhưng không có nghĩa mọi registration đều tạo ra URL đăng nhập trình duyệt. Ví dụ `client_credentials` không phải luồng OAuth2 Login và không nên xuất thành một nút “Đăng nhập” dành cho người dùng.

Với OIDC, Spring Security dùng các metadata trong registration — đặc biệt issuer/JWK Set, client ID, scopes và endpoints — để thực hiện code exchange và kiểm tra ID Token theo yêu cầu giao thức. Ứng dụng vẫn phải áp dụng chính sách phân quyền phù hợp sau khi xác thực thành công.

## 14. Những lỗi thường gặp khi sử dụng ClientRegistrationRepository

### 14.1. Không tìm thấy registrationId

**Triệu chứng:** truy cập `/oauth2/authorization/corp` nhưng Spring Security không khởi tạo được đăng nhập.

**Nguyên nhân thường gặp:** file cấu hình chỉ khai báo `registration.partner`, tên ID viết khác chữ hoa/chữ thường hoặc bean custom không chứa `corp`.

**Cách xử lý:** kiểm tra `registrationId` thực tế của các `ClientRegistration` trong repository; bảo đảm link đăng nhập dùng ID có tồn tại.

### 14.2. Dùng clientId thay cho registrationId trong URL

**Triệu chứng:** dùng `/oauth2/authorization/web-portal-production` nhưng cấu hình chỉ có `registration.corp`.

**Nguyên nhân:** nhầm client ID do provider cấp với ID do ứng dụng đặt.

**Cách xử lý:** điểm khởi tạo mặc định dựa trên **registration ID**, ví dụ `/oauth2/authorization/corp`; client ID được đưa vào authorization request qua metadata.

### 14.3. Đã khai báo properties nhưng bean custom ghi đè hành vi auto-configuration

**Triệu chứng:** cấu hình trong `application.yml` không xuất hiện trong repository, chỉ các registration tạo thủ công hoạt động.

**Nguyên nhân:** ứng dụng có bean `ClientRegistrationRepository` riêng nên auto-configuration có thể back off.

**Cách xử lý:** xác định rõ **nguồn sở hữu repository**. Nếu cần trộn nhiều nguồn, tạo một repository tổng hợp có chủ đích và kiểm soát trùng ID, không giả định Boot sẽ tự hợp nhất.

### 14.4. Repository có registration nhưng metadata OIDC sai

**Triệu chứng:** authorization redirect được tạo nhưng token exchange hoặc ID Token validation thất bại.

**Nguyên nhân:** issuer sai, token endpoint sai, JWK Set URI không phù hợp, client secret/secret method sai hoặc scope không được chấp nhận.

**Cách xử lý:** đối chiếu với metadata chính thức của provider, client registration đã cấp và redirect URI được đăng ký. Repository không tự đảm bảo metadata do người viết cung cấp là chính xác.

### 14.5. Trang login mặc định không hiển thị link đăng nhập

**Triệu chứng:** repository custom tìm được registration qua ID nhưng trang đăng nhập tự tạo không liệt kê client.

**Nguyên nhân có thể:** repository không triển khai `Iterable<ClientRegistration>` hoặc đăng ký không đủ điều kiện để hiển thị với OAuth2 login.

**Cách xử lý:** dùng `InMemoryClientRegistrationRepository` khi phù hợp, hoặc xây trang login tùy chỉnh chứa các link `/oauth2/authorization/{registrationId}` đã được phép.

### 14.6. Lẫn repository lưu registration với nơi lưu token

**Triệu chứng:** lập trình viên mong `InMemoryClientRegistrationRepository` giữ refresh token, hoặc cho rằng đăng nhập user B sẽ dùng token của user A.

**Nguyên nhân:** nhầm `ClientRegistrationRepository` với `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService`.

**Cách xử lý:** thiết kế token storage theo principal và client, đồng thời giữ cấu hình registration tách khỏi dữ liệu ủy quyền được cấp.

### 14.7. Khai báo ClientRegistrationRepository cho WebFlux bằng API Servlet

**Triệu chứng:** dùng `SecurityWebFilterChain` trong ứng dụng reactive nhưng lại chỉ có bean `ClientRegistrationRepository` của Servlet; framework tìm `ReactiveClientRegistrationRepository` và không thấy.

**Nguyên nhân:** chọn sai web stack.

**Cách xử lý:** bài này áp dụng cho **Servlet**. Nếu ứng dụng sử dụng WebFlux, chuyển sang `ReactiveClientRegistrationRepository` và loại cấu hình reactive tương ứng.

### 14.8. Dùng callback khác với redirectUri

**Triệu chứng:** provider từ chối redirect URI hoặc callback đến mà không khớp endpoint Spring Security.

**Nguyên nhân:** cấu hình URI trên IdP khác giá trị client gửi; hoặc đổi cấu hình callback trên Spring mà chưa cập nhật registration.

**Cách xử lý:** đồng bộ `redirectUri`, callback login processing URL và redirect URI allowlist tại provider.

### 14.9. In nguyên ClientRegistration ra log

**Triệu chứng:** client secret hoặc metadata nội bộ xuất hiện trong log/monitoring.

**Nguyên nhân:** log nguyên object hoặc serialize object ra JSON cho mục đích debug.

**Cách xử lý:** chỉ ghi các trường cần thiết, chẳng hạn ID và tên provider, sau khi đã lọc thông tin nhạy cảm. Bí mật client phải có chính sách xử lý tương ứng.

### 14.10. Cho phép dùng provider URL từ request làm issuer

**Triệu chứng/rủi ro:** client có thể thực hiện discovery và gửi dữ liệu đến endpoint do người dùng không tin cậy chỉ định.

**Nguyên nhân:** repository động không có allowlist và không ràng buộc issuer với tenant/client tin cậy.

**Cách xử lý:** quản trị mapping từ tenant đến provider được tin cậy, hạn chế metadata source và ràng buộc callback với registration đã chọn.

## 15. Một ví dụ hoàn chỉnh: corporate login trong Servlet

Giả sử hệ thống có yêu cầu: **người dùng mở cổng nội bộ và đăng nhập với Corporate OIDC Provider**.

### 15.1. Các thành phần

- Spring Boot Servlet ứng dụng tại `https://portal.example.com`.
- Client registration ID nội bộ là `corp`.
- Client ID do IdP cấp là `portal-web`.
- Issuer là `https://identity.example.com/realms/employees`.
- Redirect URI đã đăng ký là `https://portal.example.com/login/oauth2/code/corp`.
- Scope đăng nhập là `openid profile email`.

### 15.2. Cấu hình repository

Ứng dụng khai báo trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-idp
            client-id: portal-web
            client-secret: ${CORP_OIDC_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corp-idp:
            issuer-uri: https://identity.example.com/realms/employees
~~~

Spring Boot bind registration và tạo repository theo auto-configuration khi điều kiện phù hợp. Spring Security dùng bean đó trong `oauth2Login()`.

### 15.3. Các bước tại runtime

1. Người dùng gọi một route cần xác thực hoặc chọn nút đăng nhập corporate.
2. Trình duyệt được hướng tới `/oauth2/authorization/corp`.
3. Spring Security tra repository theo `corp` và xây authorization request từ metadata.
4. Trình duyệt đi tới Authorization Server, nơi người dùng xác thực và đồng ý quyền khi cần.
5. Provider trả callback `/login/oauth2/code/corp?code=...&state=...`.
6. Spring Security đối chiếu giao dịch ủy quyền và thực hiện code exchange bằng cấu hình client tương ứng.
7. Với OIDC, ID Token được xác minh; Spring Security tạo principal đã đăng nhập và lưu phiên theo chiến lược ứng dụng.
8. Nếu ứng dụng cần gọi API, authorized client/token được truy xuất từ kho authorized client tương ứng; **repository registration không giữ token của người dùng**.

Trong bước 3, repository có vai trò rất cụ thể: “với `corp`, hãy cung cấp toàn bộ metadata của client”. Những bước xác thực và token exchange còn lại thuộc các thành phần khác của Spring Security.

### 15.4. Tại sao không cần tạo bean thủ công trong trường hợp này?

Các giá trị client registration đều đã được khai báo rõ ràng trong cấu hình Boot, issuer hỗ trợ discovery, và không có yêu cầu tạo client động. Vì vậy `application.yml` và `oauth2Login()` là đủ cho phần cấu hình registration. Việc định nghĩa thêm bean thủ công chỉ tăng gánh nặng bảo trì nếu không có yêu cầu riêng.

## 16. Tình huống vận dụng

### Tình huống A: Hai registration dùng chung issuer

Ứng dụng có:

~~~text
registrationId=corp-user,  clientId=portal-user
registrationId=corp-admin, clientId=portal-admin
issuer=https://identity.example.com
~~~

**Hiểu đúng:** repository có hai entry khác ID. Cùng issuer không có nghĩa có thể chỉ lưu một `ClientRegistration` vì client ID, scope, secret và callback có thể khác.

### Tình huống B: Một người dùng đăng nhập hai lần

Người dùng Alice đăng nhập từ trình duyệt A và B thông qua cùng `registrationId=corp`.

**Hiểu đúng:** hai luồng sử dụng cùng metadata đăng ký client trong repository nhưng có `state`, phiên và authorized clients tương ứng. Repository không dùng để lưu `state` hoặc token cho từng phiên.

### Tình huống C: Tự viết repository và không thấy lựa chọn trên login page

Lập trình viên có custom implementation chỉ viết `findByRegistrationId(...)`. Direct URL `/oauth2/authorization/corp` vẫn có thể hoạt động nhưng trang login mặc định không tự liệt kê provider.

**Hiểu đúng:** cần xem khả năng `Iterable` của repository hoặc xây trang login tùy chỉnh. Không thêm phương thức `findAll()` tự nghĩ vào interface rồi mong Spring Security gọi.

### Tình huống D: API nhận Bearer token

Một ứng dụng khác gọi `GET /api/orders` trên server hiện tại kèm Bearer token. Có người đề nghị dùng `ClientRegistrationRepository` để kiểm tra token.

**Hiểu đúng:** `ClientRegistrationRepository` không phải JWT decoder/token introspector. Nếu ứng dụng **nhận và kiểm tra** Bearer token, đó là trách nhiệm **Resource Server**, cần cấu hình và dependency phù hợp.

### Tình huống E: Cần đổi client secret

Do chính sách bảo mật, secret của registration `corp` cần được rotate.

**Hiểu đúng:** secret là dữ liệu trong `ClientRegistration`; với repository in-memory được tạo khi startup, ứng dụng thường cần cơ chế reload/restart hoặc cập nhật cấu hình có kiểm soát để dùng giá trị mới. Việc thay secret không đồng nghĩa với xóa toàn bộ tài khoản người dùng; tuy nhiên luồng code exchange đang diễn ra có thể bị ảnh hưởng nếu cấu hình client thay đổi giữa chừng.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Interface `ClientRegistrationRepository` cung cấp chức năng cốt lõi nào?

**Trả lời:** `findByRegistrationId(registrationId)`, lấy metadata cấu hình OAuth2/OIDC Client đã đăng ký.

**Câu 2.** `registrationId` có phải `clientId` không?

**Trả lời:** Không. `registrationId` là khóa nội bộ để Spring Security tra repository; `clientId` là định danh do Authorization Server cấp cho client.

**Câu 3.** Nếu ứng dụng khai báo `spring.security.oauth2.client.registration.corp` trong `application.yml`, có cần tự tạo `InMemoryClientRegistrationRepository`?

**Trả lời:** Thường không cần khi Spring Boot auto-configuration đã tạo bean tương ứng và ứng dụng không yêu cầu tùy chỉnh repository.

**Câu 4.** Repository nào lưu authorization request và `state` trong quá trình redirect/callback?

**Trả lời:** `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`, thường gắn với HTTP session trong Servlet; không phải `ClientRegistrationRepository`.

**Câu 5.** Repository nào liên quan đến authorized client và token đã cấp cho người dùng?

**Trả lời:** `OAuth2AuthorizedClientRepository` và/hoặc `OAuth2AuthorizedClientService`, tùy cách cấu hình lưu trữ; không phải `ClientRegistrationRepository`.

**Câu 6.** Vì sao trang login tự tạo có thể cần repository hỗ trợ `Iterable<ClientRegistration>`?

**Trả lời:** Vì framework cần duyệt các registration để tạo danh sách lựa chọn đăng nhập. `InMemoryClientRegistrationRepository` hỗ trợ `Iterable`, trong khi interface cơ bản chỉ yêu cầu lookup bằng ID.

**Câu 7.** Servlet và WebFlux có dùng cùng interface repository không?

**Trả lời:** Không. Ứng dụng Servlet dùng `ClientRegistrationRepository`, còn WebFlux dùng `ReactiveClientRegistrationRepository` với kiểu trả về reactive.

**Câu 8.** Có thể dùng OAuth2 Client repository để tự phát hành access token như Authorization Server không?

**Trả lời:** Không. Repository lưu metadata client của ứng dụng đóng vai trò OAuth2 Client; phát hành token là trách nhiệm Authorization Server.

## 18. Ghi nhớ trọng tâm

| Thuật ngữ | Cách nhớ |
|---|---|
| **`ClientRegistration`** | Một bộ metadata mô tả OAuth2/OIDC Client và provider. |
| **`ClientRegistrationRepository`** | Tra cứu metadata theo `registrationId`. |
| **`InMemoryClientRegistrationRepository`** | Triển khai có sẵn, dùng tập cấu hình trong bộ nhớ, hỗ trợ `Iterable`. |
| **`spring.security.oauth2.client.registration.*`** | Cách Spring Boot nhận cấu hình và tạo repository theo auto-configuration. |
| **`/oauth2/authorization/{registrationId}`** | Điểm bắt đầu login dựa trên registration ID. |
| **`/login/oauth2/code/{registrationId}`** | Callback mặc định cho authorization response ở Servlet OAuth2 Login. |
| **`AuthorizationRequestRepository`** | Lưu yêu cầu authorization tạm thời, gồm dữ liệu tương quan. |
| **`OAuth2AuthorizedClientRepository/Service`** | Lưu token/authorization đã cấp cho principal, tách biệt registration. |
| **`ReactiveClientRegistrationRepository`** | API tương ứng cho WebFlux, không sử dụng thay thế trực tiếp trong Servlet. |

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client trên Servlet**, `ClientRegistrationRepository` là **điểm tra cứu thông tin client** mà những thành phần như authorization request resolver cần để biết phải đưa người dùng đến provider nào và dùng client ID, scope, redirect URI, token endpoint nào. Cách khởi đầu thực tế là khai báo registration bằng Spring Boot properties và để framework tạo `InMemoryClientRegistrationRepository`. Chỉ tự viết repository khi có nhu cầu thật sự về nguồn cấu hình, đa tenant hoặc quản lý client nâng cao.
