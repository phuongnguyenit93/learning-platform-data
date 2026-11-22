# ClientRegistration và ClientRegistrationRepository trong Spring Security Servlet

> **Phạm vi:** Java 17+, Spring Boot 3.x, Spring Security 6.x trên Servlet stack (Spring MVC). Bài học tập trung vào cấu hình OAuth2 Client/OIDC: một ứng dụng Spring đăng ký với Authorization Server ra sao, lưu thông tin bằng `ClientRegistration`, tra cứu thông qua `ClientRegistrationRepository`, và phân biệt cấu hình client với access token đã được cấp.

## 1. Bối cảnh và mục tiêu

Trong OAuth 2.0, **client** là ứng dụng yêu cầu access token từ **Authorization Server** để gọi **Resource Server**. Với “Đăng nhập bằng Google” trong Spring MVC, ứng dụng Spring là OAuth2 client dùng luồng authorization code; với một backend gọi API mà không có người dùng, nó có thể là OAuth2 client dùng client credentials.

Một ứng dụng phải đăng ký với Authorization Server trước khi xin token. Provider cấp `client_id`; confidential client thường có `client_secret` hoặc cơ chế xác thực client khác. Provider đồng thời giới hạn redirect URIs, grant types và scopes. Spring Security cần biết những thông số đó:

- `ClientRegistration` mô tả **một** cấu hình client đã đăng ký: ID, credentials, grant, scope, redirect URI và provider endpoints.
- `ClientRegistrationRepository` cung cấp **hàm tra cứu registration theo ID** cho filter/component OAuth2.
- `OAuth2AuthorizedClient` mới đại diện cho **client đã được cấp token** trong ngữ cảnh principal cụ thể; hai lớp cấu hình ở trên không phải kho token.

Sau bài, bạn có thể cấu hình một hoặc nhiều registrations, hiểu đường đi login/ủy quyền, lập trình Java bean hoặc lookup registration, kiểm thử không cần gọi IdP và phân biệt các lỗi thường gặp.

## 2. ClientRegistration: các thành phần cấu hình

Class `org.springframework.security.oauth2.client.registration.ClientRegistration` là mô hình cấu hình của một OAuth2 client. Nó không phải request HTTP, không chứa trạng thái đăng nhập hiện tại và không tự động cấp access token.

| Trường / getter | Ý nghĩa |
| --- | --- |
| `registrationId` / `getRegistrationId()` | Khóa **nội bộ Spring**, ví dụ `google`, `github`, `company-login`. |
| `clientId` / `getClientId()` | ID được Authorization Server cấp; khác registrationId là chuyện bình thường. |
| `clientSecret` / `getClientSecret()` | Bí mật server-side của confidential client nếu được dùng; không gửi ra frontend/log. |
| `clientAuthenticationMethod` | Cách xác thực client với AS, chẳng hạn `client_secret_basic` hoặc `client_secret_post`. |
| `authorizationGrantType` | Grant như `authorization_code` hoặc `client_credentials`. |
| `redirectUri` | URI callback cho authorization code flow, thường `{baseUrl}/login/oauth2/code/{registrationId}`. |
| `scopes` | Các quyền client đề nghị AS cấp; OIDC thường có `openid`. |
| `clientName` | Tên dễ đọc cho giao diện. |
| `providerDetails.authorizationUri` | Endpoint bắt đầu ủy quyền qua browser (authorization code). |
| `providerDetails.tokenUri` | Endpoint trao code hoặc credential lấy token. |
| `providerDetails.jwkSetUri` / `issuerUri` | Metadata liên quan AS/OIDC và xác minh token khi phù hợp. |
| `providerDetails.userInfoEndpoint` | UserInfo URI và tên thuộc tính định danh user, khi provider hỗ trợ. |

Thông số bắt buộc thay đổi theo grant. `authorization_code` cần authorization endpoint và redirect URI; `client_credentials` cần token endpoint, client authentication và scopes, thường không cần authorization URI hay redirect URI vì không có browser callback.

### Tại sao registrationId không phải clientId?

Ví dụ:

~~~text
registrationId = company-login        (khóa trong Spring)
provider alias = company-oidc         (tên nhóm provider)
clientId       = portal-web-prod      (ID do Authorization Server cấp)
clientName     = Company SSO          (nhãn hiển thị)
~~~

Spring tra cấu hình bằng `findByRegistrationId("company-login")`; URL bắt đầu login mặc định là `/oauth2/authorization/company-login`. Còn Authorization Server nhận `client_id=portal-web-prod`. Đổi registrationId có thể làm đổi URL bắt đầu flow, callback và khóa lưu authorized client; không đổi tùy tiện chỉ để đổi nhãn.

## 3. ClientRegistrationRepository: hợp đồng tra cứu

Interface `org.springframework.security.oauth2.client.registration.ClientRegistrationRepository` định nghĩa method trọng tâm:

~~~java
ClientRegistration findByRegistrationId(String registrationId);
~~~

Đây là contract lookup. Nó **không** định nghĩa chức năng lấy access token, refresh token, liệt kê toàn bộ providers hay sửa secret. Với implementation phổ biến `InMemoryClientRegistrationRepository`, ID không tìm thấy trả `null`. Code gọi phải xử lý trường hợp đó.

`InMemoryClientRegistrationRepository` nhận một hoặc nhiều `ClientRegistration` và giữ chúng trong bộ nhớ. Nó còn triển khai `Iterable<ClientRegistration>`, nên có thể liệt kê các registrations khi cần dựng login page. Một custom repository tự viết **chỉ cần** đáp ứng lookup; không thể mặc định ép mọi repository thành Iterable.

So sánh những đối tượng dễ nhầm:

| Đối tượng | Dữ liệu và thời điểm |
| --- | --- |
| `ClientRegistration` | Cấu hình tương đối ổn định của một OAuth2 client. |
| `ClientRegistrationRepository` | Nơi tìm cấu hình theo registrationId. |
| `OAuth2AuthorizationRequest` | Yêu cầu authorization đang diễn ra: state, redirectUri, scopes và tham số liên quan. |
| `OAuth2AuthorizedClient` | Cấu hình registration gắn với principal và access token/refresh token đã được AS cấp. |
| `OAuth2AuthorizedClientRepository` | Kho authorized client trong ngữ cảnh Servlet request/response. |
| `OAuth2AuthorizedClientService` | Kho authorized client theo registration ID/principal, không gắn trực tiếp request API. |
| `OAuth2AuthorizedClientManager` | Điều phối authorize, refresh hoặc re-authorize theo grant và context phù hợp. |

**Chốt:** tra được registration chỉ chứng minh Spring biết client này, **chưa** chứng minh token hợp lệ, user đã login hay AS đã cấp phép.

## 4. Dùng Spring Boot để tạo repository từ YAML

Với ít provider cố định, cách đơn giản là khai báo `spring.security.oauth2.client.registration.*`, kèm `spring.security.oauth2.client.provider.*` nếu cần. Khi classpath có OAuth2 Client starter và cấu hình hợp lệ, Boot thường auto-configure bean `ClientRegistrationRepository`.

### 4.1 GitHub: provider có thông số mặc định

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
              - user:email
~~~

Registration ID `github` nhận các giá trị provider mặc định do Boot hỗ trợ. Trước khi chạy, đăng ký một GitHub OAuth App thật, cấp client ID/secret qua biến môi trường và đăng ký callback đúng. Không nhúng credential thật vào Git, log hay tài liệu.

URL khởi động authorization code thông thường:

~~~http
GET /oauth2/authorization/github HTTP/1.1
Host: app.example.org
~~~

Spring Security Servlet thường dùng redirect URI mẫu:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Với public app `https://app.example.org`, ví dụ callback là `https://app.example.org/login/oauth2/code/github`. URI AS chấp nhận phải khớp URI thực tế; khi chạy sau reverse proxy cần bảo đảm host/scheme public được dựng đúng. GitHub OAuth trong ví dụ không tự đồng nghĩa với OIDC; không mặc định giả định GitHub phát ID token.

### 4.2 Custom OpenID Connect provider

Khai báo registration riêng và provider alias:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company-oidc
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: "Company SSO"
        provider:
          company-oidc:
            issuer-uri: https://idp.example.org/realms/training
~~~

URL `idp.example.org` chỉ minh họa cấu trúc, phải thay bằng issuer OIDC đang hoạt động trong ứng dụng thực. `issuer-uri` cho phép dùng metadata discovery khi provider hỗ trợ; việc khởi tạo có thể cần truy cập metadata. Issuer sai hoặc không truy cập được có thể làm startup lỗi.

Ở đây `company-login` là registrationId, `company-oidc` là provider alias, còn `client-id` do AS cấp. Scope `openid` đánh dấu yêu cầu OIDC. Phương thức xác thực client phải phù hợp AS; không mặc định `client_secret_basic` cho provider chỉ hỗ trợ `client_secret_post`.

Với OAuth2 provider không có issuer discovery, có thể khai báo chính xác `authorization-uri`, `token-uri`, `user-info-uri`, `user-name-attribute` và `jwk-set-uri` nếu được sử dụng. Lấy các giá trị theo metadata/tài liệu AS thực tế.

### 4.3 Vấn đề secrets và auto-configuration

Client secret là thông tin **chỉ server được biết**. Dùng environment variables hoặc secret manager; không cung cấp qua REST endpoint dành cho frontend và không in cả object `ClientRegistration` vào log.

Khi tự tạo bean `ClientRegistrationRepository` bằng Java, auto-configuration của Boot có thể **back off**. Các registration khai báo YAML sẽ không nhất thiết tự hợp nhất với bean Java. Hãy chọn một nguồn cấu hình duy nhất hoặc chủ động xây composite repository rõ ràng.

## 5. Tạo ClientRegistration và repository bằng Java

`ClientRegistration.withRegistrationId(...)` trả builder; `CommonOAuth2Provider` có preset cho một số provider quen thuộc. Đoạn sau là class `GoogleClientRegistrationConfig.java` trong dự án Spring Boot có OAuth2 Client starter. Đây là phương án thay thế cấu hình `registration.google` bằng YAML.

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.oauth2.client.CommonOAuth2Provider;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Configuration
public class GoogleClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.google.client-id}") String clientId,
            @Value("${app.google.client-secret}") String clientSecret) {

        ClientRegistration google = CommonOAuth2Provider.GOOGLE
                .getBuilder("google")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .scope("openid", "profile", "email")
                .build();

        return new InMemoryClientRegistrationRepository(google);
    }
}
~~~

Ứng dụng có thể lấy cấu hình từ `application.properties`:

~~~properties
app.google.client-id=${GOOGLE_CLIENT_ID}
app.google.client-secret=${GOOGLE_CLIENT_SECRET}
~~~

Giải thích:

1. Preset `CommonOAuth2Provider.GOOGLE` cung cấp builder với provider endpoints và các giá trị mặc định thích hợp.
2. `clientId/clientSecret` đến từ cấu hình ngoài source; secret không nằm trong Java class.
3. `build()` tạo **cấu hình** `ClientRegistration`, chưa gọi token endpoint hay đăng nhập user.
4. Repository in-memory trả registration khi Spring gọi `findByRegistrationId("google")`.
5. Cần một OAuth2 client Google hợp lệ, callback đúng và người dùng thực hiện flow để login thành công.

**Phạm vi ví dụ:** đây là class Java trong ứng dụng Spring có dependency Spring Security OAuth2 Client, không phải Java SE độc lập. `javac` không có các libraries của dự án sẽ không biên dịch; không có stdout tự động.

### 5.1 Ví dụ client_credentials dùng builder trực tiếp

Đoạn Java sau minh họa tại nơi đã có hai biến `clientId` và `clientSecret` từ secret store:

~~~java
ClientRegistration inventory = ClientRegistration
        .withRegistrationId("inventory")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .tokenUri("https://idp.example.org/oauth2/token")
        .scope("inventory.read")
        .clientName("Inventory Service")
        .build();
~~~

Imports cần thiết:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
~~~

Với `client_credentials`, client không có browser authorization screen/callback. Nó cần token endpoint, credential/method và scope được AS cho phép. Endpoint `idp.example.org` là địa chỉ minh họa. **Định nghĩa registration không tự gọi token endpoint**; phải dùng authorized-client manager/provider được cấu hình hỗ trợ client credentials.

## 6. Spring Security Servlet dùng repository khi login

Ví dụ file `OAuth2LoginSecurityConfig.java` có thể biên dịch trong một ứng dụng Spring Boot đã có bean repository qua YAML hoặc Java, với các dependency OAuth2 Client/Web/Security:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
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

`oauth2Login` cung cấp nhánh authorization code/OIDC dùng cho đăng nhập user; `oauth2Client` bật cơ chế tích hợp OAuth2 Client phục vụ sử dụng authorized clients. Cấu hình đó không tự gắn Bearer token vào mọi HTTP request outbound; phải tích hợp HTTP client/authorized client manager đúng cách.

Luồng điển hình với registration `google`:

1. Browser GET `/oauth2/authorization/google`. `OAuth2AuthorizationRequestRedirectFilter` tra repository theo `google`, lấy client ID, provider authorization endpoint, scopes và redirect URI.
2. Spring tạo `OAuth2AuthorizationRequest` với `state` khó đoán, lưu trạng thái authorization request đang chờ, rồi redirect tới AS.
3. Sau khi user xác thực/cấp quyền tại AS, browser được chuyển về callback `/login/oauth2/code/google` mang `code` và `state`.
4. `OAuth2LoginAuthenticationFilter` xử lý callback, kiểm tra state/authorization response, tra lại registration, trao code với token endpoint bằng đúng client authentication.
5. Tùy OAuth2/OIDC, Spring tải/xác minh thông tin user cần thiết và xây `Authentication`. Token thuộc `OAuth2AuthorizedClient` và kho token tương ứng, không đặt vào registration.

~~~text
Browser -> GET /oauth2/authorization/google
        -> ClientRegistrationRepository.findByRegistrationId("google")
        -> authorization request + state
        -> redirect tới AS
AS      -> /login/oauth2/code/google?code=...&state=...
        -> kiểm tra state + lookup client
        -> token endpoint (code exchange)
        -> Authentication + OAuth2AuthorizedClient
~~~

`state` trong authorization code flow là cơ chế liên kết callback với authorization request; nó không đồng nghĩa với CSRF token do `CsrfFilter` yêu cầu ở những HTTP request thay đổi trạng thái trong session web app.

## 7. Lookup registration trong Service Java

File `ClientRegistrationLookup.java` trong package Spring Boot scan:

~~~java
package com.example.security;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class ClientRegistrationLookup {

    private final ClientRegistrationRepository repository;

    public ClientRegistrationLookup(ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public ClientRegistration require(String registrationId) {
        ClientRegistration registration =
                repository.findByRegistrationId(registrationId);
        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown client registration: " + registrationId);
        }
        return registration;
    }
}
~~~

Service này có constructor injection và báo lỗi rõ khi ID không tồn tại. Nó tra **registration ID**, không tra client ID hoặc tên provider. Không trả trực tiếp `ClientRegistration` ra JSON API công khai vì có thể chứa secret.

Với repository implementation có `Iterable<ClientRegistration>` như in-memory, có thể liệt kê registrations để hiển thị lựa chọn login. Nhưng interface gốc không đòi Iterable; custom repository không chắc hỗ trợ chức năng đó. Chỉ liệt kê thông tin công khai cần thiết, không in `getClientSecret()` hay token vào log.

## 8. Nhiều registrations cùng tồn tại, nhưng grant khác nhau

Ví dụ vừa dùng GitHub để user login vừa dùng inventory AS để service lấy token:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
          inventory:
            provider: internal-auth
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          internal-auth:
            token-uri: https://idp.example.org/oauth2/token
~~~

- `github` dùng authorization code; `/oauth2/authorization/github` có thể bắt đầu login/authorization.
- `inventory` dùng client credentials; nó không dùng browser login, không nên trỏ `/oauth2/authorization/inventory` rồi mong redirect.
- Cùng `ClientRegistrationRepository` có thể phục vụ cả hai. Nhưng muốn lấy token cho `inventory` phải cấu hình `OAuth2AuthorizedClientManager` với grant `client_credentials` và principal/service context đúng.

### Phân biệt static config với token runtime

~~~text
ClientRegistrationRepository
  "github"    -> client ID, secret, scope, provider metadata
  "inventory" -> client ID, secret, token URI, grant

OAuth2AuthorizedClientService / Repository
  ("github", principal="alice")  -> access/refresh token Alice
  ("github", principal="bob")    -> access/refresh token Bob
  ("inventory", servicePrincipal)-> token service
~~~

`DefaultOAuth2AuthorizedClientManager` thường phù hợp với Servlet request context; `AuthorizedClientServiceOAuth2AuthorizedClientManager` dùng được trong các tác vụ service/background không có Servlet request. Không coi `ClientRegistrationRepository` là nơi chứa token; token có hạn dùng, có thể refresh/revoke, trong khi registration là cấu hình dùng để xin token.

## 9. Custom repository và multi-tenant: rủi ro thiết kế

Tự viết `ClientRegistrationRepository` có ích khi registrations nằm trong DB, tenant store hoặc secret manager và phải tra cứu động. Nhưng cần lưu ý:

- **Tenant isolation:** không để request tự do chọn ID của tenant khác rồi đọc client secret.
- **Caching & rotation:** cache giúp tránh query secret store mọi request, nhưng cần invalidate an toàn khi secret/provider endpoint thay đổi.
- **Consistency giữa redirect và callback:** authorization code request bắt đầu với cấu hình A; nếu client ID/redirect/issuer thay đổi trong lúc user đang ở IdP, callback có thể không còn phù hợp.
- **Endpoint trust/SSRF:** không cho người dùng không tin cậy cung cấp token/issuer URL để server truy cập tùy ý. Validate provider metadata và domain.
- **Thread safety:** repository bean được nhiều HTTP requests dùng đồng thời; cache/updates phải an toàn.
- **Iterable:** custom lookup không tự bảo đảm default login page liệt kê đầy đủ providers.
- **Secret protection:** mã hóa/lưu ở secret store và không dump đối tượng registration khi debug.

Với ít provider cố định, YAML + externalized secrets thường dễ hiểu và ít lỗi hơn một repository động tự thiết kế.

## 10. Kiểm thử lookup không gọi Authorization Server

Ví dụ JUnit 5 trong `src/test/java/com/example/security/ClientRegistrationRepositoryTest.java`. Test cần JUnit Jupiter và Spring Security OAuth2 Client trên test classpath, không cần IdP thật:

~~~java
package com.example.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

class ClientRegistrationRepositoryTest {

    @Test
    void looksUpClientByRegistrationId() {
        ClientRegistration inventory = ClientRegistration
                .withRegistrationId("inventory")
                .clientId("inventory-service")
                .clientSecret("testing-only")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.org/oauth2/token")
                .scope("inventory.read")
                .clientName("Inventory Service")
                .build();

        ClientRegistrationRepository repository =
                new InMemoryClientRegistrationRepository(inventory);

        assertSame(inventory, repository.findByRegistrationId("inventory"));
        assertNull(repository.findByRegistrationId("missing"));
        assertEquals("inventory-service",
                inventory.getClientId());
        assertEquals("client_credentials",
                inventory.getAuthorizationGrantType().getValue());
    }
}
~~~

Test chứng minh builder/repository trả dữ liệu đúng theo ID; nó **không** chứng minh secret thật hợp lệ, AS hoạt động hay access token có thể xin được. `testing-only` là chuỗi dành cho unit test, không phải production credential. Integration test cho OAuth2 Login/manager phải có AS test sandbox và kiểm tra riêng state, callback, token endpoint, OIDC validation và token store.

## 11. Những lỗi hay gặp

| Triệu chứng | Khả năng gốc | Kiểm tra |
| --- | --- | --- |
| `findByRegistrationId("google")` trả null | ID sai, dùng clientId/provider alias hoặc registration chưa được đăng ký. | So sánh registrationId trong YAML/bean và URL. |
| `/oauth2/authorization/google` 404 | Chưa bật `oauth2Login`, filter chain không match hoặc thiếu OAuth2 Client dependency. | Kiểm tra starter, bean repository, security configuration. |
| Spring Boot không tạo repository | Cấu hình properties sai/thiếu, custom bean thay thế, issuer discovery lỗi. | Xem binding `spring.security.oauth2.client.*` và lỗi startup. |
| Token endpoint trả `invalid_client` | Client ID/secret sai, secret rotate hoặc sai client auth method. | Kiểm tra secret store và cấu hình AS. |
| AS trả `redirect_uri_mismatch` | Callback public không đúng URI đã đăng ký, reverse proxy dựng sai scheme/host. | Đối chiếu redirect URI, forwarded headers đáng tin cậy và TLS. |
| Callback thất bại vì state/session | State không khớp, cookie phiên bị loại hoặc session thay đổi. | Quan sát authorization request repository, session, callback. |
| OIDC login thất bại sau token | Issuer/JWK/UserInfo/scopes hoặc dữ liệu ID token không phù hợp. | Kiểm tra OIDC discovery/validation đúng provider. |
| Có registration nhưng không có token | Chưa gọi client manager, thiếu grant provider hoặc principal context. | Kiểm tra `OAuth2AuthorizedClientManager`, service/repository. |
| `client_credentials` không mở login | Đây là machine-to-machine grant, không có browser redirect. | Gọi manager theo grant, không dùng login URL. |
| Thêm Java bean thì YAML không còn registration | Auto config có thể back off khi đã có repository bean. | Chọn một nguồn hoặc xây composite repository. |

Khi debug, chỉ log registrationId, grant, scopes, public redirect và provider endpoints có kiểm soát. Không in `clientSecret`, authorization code, access token/refresh token. Tách ba bước: **lookup client config → authorization/token exchange → lưu/sử dụng authorized client**. Lỗi của bước sau không mặc nhiên là lỗi repository.

## 12. Lựa chọn theo use case

**Ứng dụng web đăng nhập OIDC/OAuth2:** cấu hình registration bằng YAML, để Boot tạo repository; bật `oauth2Login`, đăng ký callback với AS, kiểm tra scope, issuer, token exchange và HTTPS.

**Ứng dụng gọi API nhân danh user đã login:** lấy authorized client/access token thông qua manager/repository/service theo principal phù hợp; không tìm token trong `ClientRegistration`.

**Backend service-to-service:** tạo registration `client_credentials`, dùng manager hỗ trợ grant này, lưu secret bên server, không mở browser login.

**Nhiều tenant/client động:** custom repository chỉ khi thực sự cần; bảo vệ tenant isolation, secret rotation, cache, provider endpoints và callback consistency.

**Ghi nhớ:** `ClientRegistration` là **bản mô tả cấu hình một OAuth2 client**, `ClientRegistrationRepository` là **nguồn tra mô tả theo registrationId**. Token và trạng thái đã được ủy quyền nằm trong `OAuth2AuthorizedClient` cùng các repository/service/manager riêng.