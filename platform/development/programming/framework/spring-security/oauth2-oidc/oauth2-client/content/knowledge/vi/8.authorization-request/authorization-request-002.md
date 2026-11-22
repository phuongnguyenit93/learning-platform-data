# 8.2. OAuth2AuthorizationRequestResolver và resolver mặc định trên Servlet

## 1. Bài toán: ai tạo authorization request khi người dùng chọn đăng nhập?

Một ứng dụng **Spring Boot Servlet** sử dụng **Spring Security OAuth 2.0 Client** thường cho phép người dùng đăng nhập bằng tài khoản của một **OpenID Provider (OP)** hoặc bắt đầu cấp quyền truy cập một API thông qua **OAuth 2.0 Authorization Server**.

Ví dụ: Employee Portal có nút **Đăng nhập với tài khoản công ty**. Người dùng nhấp nút, trình duyệt truy cập:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
~~~

Portal cần tạo một URL tới authorization endpoint của Identity Provider (IdP). URL đó chứa các thông tin như:

- **response_type=code**: yêu cầu Authorization Code Flow.
- **client_id**: định danh OAuth Client do IdP cấp.
- **redirect_uri**: URL callback mà IdP sẽ chuyển người dùng trở về.
- **scope**: quyền được yêu cầu, chẳng hạn `openid profile orders.read`.
- **state**: giá trị gắn authorization response với yêu cầu đã khởi tạo.
- **nonce** trong trường hợp OIDC cần thiết; **code_challenge** và **code_challenge_method** nếu dùng PKCE.

Ai lấy thông tin cấu hình, tạo các tham số, sinh giá trị bảo vệ giao dịch và đóng gói authorization request trước khi chuyển hướng browser?

Trong Spring Security Servlet, phần trách nhiệm đó thuộc về **`OAuth2AuthorizationRequestResolver`** và triển khai mặc định **`DefaultOAuth2AuthorizationRequestResolver`**. Resolver giúp ứng dụng không phải tự nối chuỗi query parameter hoặc tự triển khai Authorization Code Flow.

> Bài học tập trung vào **authorization request phía OAuth2 Client trên Servlet**. Đây là yêu cầu mà client **gửi tới Authorization Server để bắt đầu ủy quyền**, không phải request HTTP có Bearer token gửi tới Resource Server, và cũng không phải authorization response chứa `code` mà IdP trả về sau đó.

## 2. Vị trí của resolver trong kiến trúc Spring Security

Giả sử hệ thống có:

| Thành phần | Vai trò |
|---|---|
| **Browser** | Gửi request đăng nhập đến Portal và đi theo redirect |
| **Employee Portal** | Spring Boot Servlet, đóng vai trò OAuth2 Client/OIDC Relying Party |
| **Company IdP** | Authorization Server và OpenID Provider; xác thực người dùng, cấp code và token |
| **Orders API** | Resource Server nhận access token sau khi Portal đã hoàn tất login/authorization |

Một request bắt đầu login đi qua các thành phần chính:

~~~text
Browser
   |
   | GET /oauth2/authorization/company
   v
Servlet Filter Chain
   |
   v
OAuth2AuthorizationRequestRedirectFilter
   |
   | gọi resolve(HttpServletRequest)
   v
OAuth2AuthorizationRequestResolver
   |
   | thường là DefaultOAuth2AuthorizationRequestResolver
   | dùng ClientRegistrationRepository
   v
OAuth2AuthorizationRequest
   |
   | lưu thông tin request để đối chiếu callback
   v
AuthorizationRequestRepository
   |
   | HTTP 302 Location: authorization endpoint của IdP
   v
Browser -> IdP
~~~

**`OAuth2AuthorizationRequestRedirectFilter`** là Servlet filter xử lý bước bắt đầu chuyển hướng. Filter gọi resolver để lấy **`OAuth2AuthorizationRequest`**, lưu request thông qua **`AuthorizationRequestRepository`**, rồi gửi redirect đến authorization endpoint.

**Resolver không tự xác thực người dùng**, không đổi authorization code lấy token và không thực hiện gọi API. Những bước đó thuộc các thành phần khác của Spring Security và Authorization Server.

## 3. Giao diện OAuth2AuthorizationRequestResolver

Ở Spring Security Servlet, interface có hai phương thức:

~~~java
package org.springframework.security.oauth2.client.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public interface OAuth2AuthorizationRequestResolver {

    OAuth2AuthorizationRequest resolve(HttpServletRequest request);

    OAuth2AuthorizationRequest resolve(
        HttpServletRequest request,
        String clientRegistrationId
    );
}
~~~

Hai phương thức nhận cùng một **`HttpServletRequest`**, nhưng khác về cách chọn client registration:

| Phương thức | Cách sử dụng |
|---|---|
| **resolve(request)** | Thường xử lý URL bắt đầu authorization, tự tìm **registrationId** phù hợp từ HTTP request |
| **resolve(request, clientRegistrationId)** | Được truyền registration ID rõ ràng; hữu ích khi caller đã biết client cần sử dụng |

Nếu request không phù hợp với điều kiện bắt đầu authorization, resolver có thể trả về **`null`**. Điều này không phải là “đăng nhập thất bại”: nó đơn giản có nghĩa resolver không tạo authorization request cho HTTP request đó.

Không nên tự giả định mọi URL đều được resolver xử lý, hoặc tự chuyển mọi request đến IdP. Trong ứng dụng có nhiều filter và endpoint, việc xác định **đúng URL khởi tạo** rất quan trọng.

### 3.1. Client registration ID là gì?

Registration ID là tên mà ứng dụng đặt cho một cấu hình OAuth Client, ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal
~~~

Ở đây:

- **`company`** là **registration ID** được sử dụng trong URL nội bộ `/oauth2/authorization/company`.
- **`employee-portal`** là **client ID** đã đăng ký với Authorization Server.

Hai giá trị có thể khác nhau. Resolver cần lấy **`ClientRegistration`** của registration ID tương ứng từ **`ClientRegistrationRepository`**; không tự lấy client ID từ query parameter do browser gửi để tin ngay đó là client hợp lệ.

## 4. OAuth2AuthorizationRequest chứa những gì?

Đối tượng **`OAuth2AuthorizationRequest`** là mô hình của một authorization request mà client chuẩn bị gửi tới Authorization Server. Nó được xây dựng từ thông tin của **`ClientRegistration`**, dữ liệu HTTP request và các giá trị bổ sung do resolver tạo.

Các thuộc tính đáng chú ý:

| Thuộc tính / API | Ý nghĩa |
|---|---|
| **authorizationUri** | Endpoint bắt đầu authorization của IdP |
| **authorizationGrantType** | Thường là `authorization_code` cho web login |
| **responseType** | Thường là `code` |
| **clientId** | ID của OAuth Client |
| **redirectUri** | Callback của Portal, cần phù hợp với URI đã đăng ký ở IdP |
| **scopes** | Tập scope mà client yêu cầu |
| **state** | Giá trị ngẫu nhiên gắn request với response |
| **additionalParameters** | Tham số protocol/provider bổ sung, ví dụ `nonce`, `prompt`, `code_challenge` nếu áp dụng |
| **attributes** | Dữ liệu nội bộ mà client cần giữ để xử lý callback, ví dụ thông tin gắn với registration và PKCE |
| **authorizationRequestUri** | URI hoàn chỉnh để browser được chuyển hướng tới IdP |

**`additionalParameters`** và **`attributes`** có ý nghĩa khác nhau:

- **Additional parameters** là thông tin cần xuất hiện trong **authorization request được gửi tới IdP**, tùy protocol và provider.
- **Attributes** là thông tin **nội bộ của request object** để framework xử lý luồng. Không phải mọi attribute đều cần hoặc được phép xuất hiện trong URL chuyển hướng.

Ví dụ, với PKCE, **`code_challenge`** là tham số gửi trong authorization request; **`code_verifier`** phải được giữ để client sử dụng khi đổi code ở token endpoint, không gửi `code_verifier` đến authorization endpoint.

### 4.1. Ví dụ về URL được tạo

Một authorization request có thể được chuyển thành URL dạng:

~~~text
https://login.example.test/oauth2/authorize
  ?response_type=code
  &client_id=employee-portal
  &scope=openid%20profile%20orders.read
  &state=<random-state>
  &redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany
  &nonce=<oidc-nonce-neu-co>
  &code_challenge=<pkce-challenge-neu-co>
  &code_challenge_method=S256
~~~

Ví dụ trên **được tách dòng để dễ đọc**; giá trị thực của header **Location** là một URL đã encode, không dùng nguyên văn các dấu xuống dòng. Những tham số `nonce` và `code_challenge` phụ thuộc luồng/cấu hình.

Client secret **không nằm trong URL này**. Với confidential client, secret dùng ở bước server-to-server với **token endpoint**, theo cơ chế xác thực client đã đăng ký.

## 5. Resolver mặc định: DefaultOAuth2AuthorizationRequestResolver

Spring Security cung cấp triển khai chuẩn:

~~~java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver
~~~

Với cấu hình Servlet OAuth2 login thông dụng, resolver mặc định:

1. Xác định request có khớp **authorization request base URI** hay không.
2. Tìm **clientRegistrationId** tương ứng.
3. Lấy **`ClientRegistration`** từ **`ClientRegistrationRepository`**.
4. Tạo **`OAuth2AuthorizationRequest`** từ thông tin đăng ký, ví dụ authorization URI, client ID, scope và redirect URI.
5. Tạo hoặc bổ sung các tham số an toàn của Authorization Code Flow như **state**, cùng các tham số OIDC/PKCE khi cần.
6. Cho phép tùy biến request thông qua một **`Consumer<OAuth2AuthorizationRequest.Builder>`** được đăng ký với `setAuthorizationRequestCustomizer(...)`.
7. Trả về request object; filter tiếp tục lưu và chuyển hướng browser.

Constructor thường dùng:

~~~java
new DefaultOAuth2AuthorizationRequestResolver(
    clientRegistrationRepository,
    authorizationRequestBaseUri
);
~~~

Trong đó:

- **`clientRegistrationRepository`** chứa các client đã được cấu hình.
- **`authorizationRequestBaseUri`** quy định tiền tố URL bắt đầu authorization.

Giá trị mặc định của Servlet redirect filter:

~~~java
OAuth2AuthorizationRequestRedirectFilter
    .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
~~~

Tương ứng với:

~~~text
/oauth2/authorization
~~~

Với registration ID **company**, điểm khởi đầu thường là:

~~~text
/oauth2/authorization/company
~~~

### 5.1. Phân biệt authorization URI và authorization request base URI

Hai URI có tên gần giống nhưng chỉ tới **hai hệ thống khác nhau**:

| URI | Ví dụ | Thuộc về |
|---|---|---|
| **Authorization request base URI** | `/oauth2/authorization` | **Portal**: đường dẫn mà browser gọi để nhờ Spring bắt đầu login |
| **Authorization URI của provider** | `https://login.example.test/oauth2/authorize` | **IdP**: endpoint nhận yêu cầu ủy quyền của OAuth Client |

Trình duyệt truy cập URI thứ nhất tại Portal. Resolver lấy cấu hình rồi tạo URL đến URI thứ hai. Không đặt trực tiếp token endpoint hay callback của Portal thành authorization request base URI.

### 5.2. URL callback là thành phần khác

Đường dẫn callback mặc định cho Authorization Code login thường là:

~~~text
/login/oauth2/code/{registrationId}
~~~

Ví dụ:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Callback được xử lý bởi **`OAuth2LoginAuthenticationFilter`** khi dùng OAuth2 Login. Resolver là thành phần **khởi tạo** authorization request, không phải callback handler. Nếu đổi base URI khởi tạo, không có nghĩa callback cũng tự đổi.

## 6. Luồng Servlet hoàn chỉnh: resolver, redirect, callback và token

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant RedirectFilter as OAuth2AuthorizationRequestRedirectFilter
    participant Resolver as DefaultOAuth2AuthorizationRequestResolver
    participant Repo as AuthorizationRequestRepository
    participant IdP as Authorization Server / OIDC Provider
    participant LoginFilter as OAuth2LoginAuthenticationFilter

    User->>Browser: Nhấn đăng nhập công ty
    Browser->>RedirectFilter: GET /oauth2/authorization/company
    RedirectFilter->>Resolver: resolve(request)
    Resolver->>Resolver: Tra ClientRegistration(company), sinh state và tham số cần thiết
    Resolver-->>RedirectFilter: OAuth2AuthorizationRequest
    RedirectFilter->>Repo: saveAuthorizationRequest(request, response)
    RedirectFilter-->>Browser: 302 Location: authorization endpoint của IdP
    Browser->>IdP: GET /authorize?...&state=...
    IdP->>User: Xác thực và consent khi cần
    IdP-->>Browser: 302 về callback với code và state
    Browser->>LoginFilter: GET /login/oauth2/code/company?code=...&state=...
    LoginFilter->>Repo: load/remove authorization request để đối chiếu
    LoginFilter->>IdP: Đổi code lấy token qua token endpoint
    IdP-->>LoginFilter: Token response
    LoginFilter-->>Browser: Tạo session đăng nhập, redirect về ứng dụng
~~~

Trình tự cho thấy **resolver chỉ xuất hiện ở giai đoạn đầu**. Callback và việc đổi code không được tự động thực thi bởi resolver, dù đều là các bước trong một lần đăng nhập.

Một số điểm bảo mật cần giữ:

- **state** phải được tạo mới cho authorization request và được đối chiếu khi callback đến.
- **nonce** được dùng trong OIDC theo điều kiện của luồng và phải được kiểm tra theo quy tắc OIDC.
- **PKCE** dùng `code_challenge` ở authorization request và `code_verifier` ở bước đổi code; hai giá trị phải tương ứng với cùng giao dịch.
- `redirect_uri` dùng ở authorization request và token exchange phải tương ứng với cấu hình được IdP chấp nhận.
- HTTP session/cơ chế lưu request cần còn hợp lệ khi browser quay về từ IdP.

## 7. Tạo dự án Servlet OAuth2/OIDC Client tối thiểu

Ví dụ dự án sử dụng Java 17+, Spring Boot 3 và Spring Security 6.

### 7.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

**`spring-boot-starter-web`** dùng Servlet stack (Spring MVC). **`spring-boot-starter-oauth2-client`** cung cấp hỗ trợ OAuth 2.0 Client và OIDC login. Nếu dùng WebFlux, cần học các resolver và filter thuộc reactive stack riêng; các chữ ký `HttpServletRequest` trong bài này không áp dụng trực tiếp cho WebFlux.

### 7.2. Cấu hình ClientRegistration

~~~yaml
# application.yml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Trong đó:

- **`OIDC_ISSUER_URI`** là issuer của provider mà client tin cậy.
- **`OIDC_CLIENT_ID`** là ID client đã đăng ký tại IdP.
- **`OIDC_CLIENT_SECRET`** phải được cấp qua môi trường chạy hoặc secret manager; không hardcode trong Git hoặc frontend.
- **`openid`** kích hoạt ngữ nghĩa OIDC login, còn **`orders.read`** chỉ là scope API minh họa và phải được IdP cấp.

Nếu provider công bố metadata OIDC qua discovery, **issuer-uri** giúp Spring Security tìm các endpoint cần thiết. Không tự dựng URL `/authorize` hoặc `/token` bằng cách ghép chuỗi nếu provider đã có metadata tin cậy.

Với cấu hình trên, người dùng khởi động login qua:

~~~text
http://localhost:8080/oauth2/authorization/company
~~~

IdP phải cho phép callback local, ví dụ:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Trên production, callback cần dùng HTTPS và hostname thực tế của Portal.

### 7.3. SecurityFilterChain

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**`oauth2Login()`** bật chuỗi filter phục vụ đăng nhập qua OAuth 2.0/OIDC. **`oauth2Client()`** bổ sung khả năng quản lý client authorization cho các tình huống ứng dụng cần gọi API. Trong ví dụ tối thiểu này, ứng dụng có thể dùng resolver mặc định, không cần tự khai báo một bean resolver.

Đường dẫn `/oauth2/authorization/company` là một **endpoint do security filter xử lý**. Nó không bắt buộc có một `@GetMapping` tương ứng trong Controller.

## 8. Cấu hình DefaultOAuth2AuthorizationRequestResolver tường minh

Khi cần tùy biến authorization request, có thể tạo resolver rồi gắn nó vào cấu hình **authorization endpoint** của `oauth2Login()`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2AuthorizationConfig {

    @Bean
    OAuth2AuthorizationRequestResolver authorizationRequestResolver(
        ClientRegistrationRepository registrations
    ) {
        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations,
                OAuth2AuthorizationRequestRedirectFilter
                    .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
            );

        return resolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationRequestResolver resolver
    ) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)))
            .build();
    }
}
~~~

Đây là **cấu hình thay thế** cho `SecurityConfig` ở mục trước khi thử resolver tùy chỉnh, không nên giữ hai `SecurityFilterChain` giống hệt nhau chỉ để minh họa.

Các phần quan trọng:

1. **ClientRegistrationRepository** do Spring Boot xây dựng từ `spring.security.oauth2.client.registration.*` và `provider.*`.
2. **DefaultOAuth2AuthorizationRequestResolver** giữ hành vi mặc định của Authorization Code Flow.
3. **authorizationEndpoint(...).authorizationRequestResolver(resolver)** chỉ định rõ resolver mà `OAuth2AuthorizationRequestRedirectFilter` sử dụng cho luồng OIDC login.

Việc khai báo một bean resolver **không nên được coi là đủ để mọi bộ lọc tự chuyển sang sử dụng bean đó**. Gắn resolver vào DSL tương ứng là cách rõ ràng để biết filter nhận instance nào.

## 9. Tùy biến tham số authorization request bằng customizer

Một số OIDC provider hỗ trợ tham số bổ sung ở authorization endpoint, ví dụ:

| Tham số | Ý nghĩa thường gặp |
|---|---|
| **prompt** | Gợi ý cách provider xử lý xác thực/consent, ví dụ `login`, `consent`, `select_account` |
| **login_hint** | Gợi ý tài khoản để provider hiển thị hoặc lựa chọn |
| **ui_locales** | Gợi ý ngôn ngữ giao diện, ví dụ `vi`, `en` |
| **acr_values** | Yêu cầu/đề nghị mức độ hoặc ngữ cảnh xác thực theo chính sách provider |
| **max_age** | Giá trị liên quan đến độ mới của phiên xác thực |

Không phải provider nào cũng hỗ trợ toàn bộ tham số; việc gửi tham số chỉ là yêu cầu/hint theo protocol và chính sách provider. Nếu cần mức xác thực bắt buộc, ứng dụng phải xác minh kết quả xác thực hoặc áp dụng chính sách server tương ứng, không dựa duy nhất vào hint.

**`DefaultOAuth2AuthorizationRequestResolver`** cung cấp:

~~~java
setAuthorizationRequestCustomizer(
    Consumer<OAuth2AuthorizationRequest.Builder> customizer
)
~~~

Ví dụ thêm **`prompt=select_account`** để IdP có thể cho người dùng chọn tài khoản:

~~~java
@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
    ClientRegistrationRepository registrations
) {
    DefaultOAuth2AuthorizationRequestResolver resolver =
        new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            OAuth2AuthorizationRequestRedirectFilter
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
        );

    resolver.setAuthorizationRequestCustomizer(builder ->
        builder.additionalParameters(parameters ->
            parameters.put("prompt", "select_account")
        )
    );

    return resolver;
}
~~~

Đoạn code là phiên bản **thay thế phần thân bean** ở mục 8. Sau đó, khi người dùng vào:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: localhost:8080
~~~

URL redirect có thể chứa:

~~~text
...&prompt=select_account
~~~

Customizer này có giá trị **cố định** cho các registration mà resolver xử lý. Nếu ứng dụng có nhiều provider, chỉ nên thêm tham số mà các provider liên quan chấp nhận, hoặc bọc resolver bằng logic lựa chọn theo registration đã xác định.

### 9.1. Bật PKCE cho confidential client

**Proof Key for Code Exchange (PKCE)** ràng buộc authorization code với client đã bắt đầu giao dịch. Trong những tình huống Spring Security hỗ trợ tự bật PKCE cho **public client**, resolver có thể thêm `code_challenge` tự động. Với confidential client, có thể yêu cầu dùng PKCE rõ ràng, nếu Authorization Server hỗ trợ:

~~~java
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;

// Sau khi tạo DefaultOAuth2AuthorizationRequestResolver:
resolver.setAuthorizationRequestCustomizer(
    OAuth2AuthorizationRequestCustomizers.withPkce()
);
~~~

Nếu muốn **cùng lúc** bật PKCE và thêm `prompt`, cần kết hợp trong **một customizer** thay vì gọi `setAuthorizationRequestCustomizer(...)` hai lần với kỳ vọng customizer trước vẫn còn:

~~~java
var withPkce = OAuth2AuthorizationRequestCustomizers.withPkce();

resolver.setAuthorizationRequestCustomizer(builder -> {
    withPkce.accept(builder);
    builder.additionalParameters(parameters ->
        parameters.put("prompt", "select_account")
    );
});
~~~

Đây là cách làm rõ rằng **mỗi yêu cầu được sinh `code_verifier` và `code_challenge` tương ứng**, trong khi client vẫn có thể xác thực bằng client secret ở token endpoint. **Không ghi code verifier hoặc client secret ra log** để kiểm tra.

## 10. Khi nào cần tự triển khai OAuth2AuthorizationRequestResolver?

Chỉ dùng **DefaultOAuth2AuthorizationRequestResolver** và một customizer tĩnh thường đủ cho:

- Thêm một tham số provider dùng chung, ví dụ `prompt=select_account`.
- Bật PKCE theo chính sách ứng dụng.
- Dùng base URI chuẩn `/oauth2/authorization` hoặc một base URI cố định riêng.

Tự triển khai interface có ích khi authorization request phụ thuộc **ngữ cảnh HTTP đầu vào đã được kiểm soát**, ví dụ:

- Gợi ý ngôn ngữ IdP theo lựa chọn **vi/en** của người dùng.
- Chọn `prompt` từ một tập giá trị an toàn do ứng dụng xác định.
- Điều chỉnh một tham số mà provider yêu cầu, trong khi vẫn giữ các giá trị security do resolver mặc định sinh.
- Tùy biến theo registration trong ứng dụng có nhiều provider.

Nên **bọc/delegate** resolver mặc định rồi thay đổi phần cần thiết, thay vì tự viết lại việc tạo state, nonce, PKCE, redirect URI và các attribute của request.

### 10.1. Ví dụ wrapper thêm ui_locales theo request

Giả sử Portal muốn hỗ trợ:

~~~text
/oauth2/authorization/company?lang=vi
/oauth2/authorization/company?lang=en
~~~

Chỉ hai giá trị `vi` và `en` được phép. Một triển khai Servlet có thể dùng:

~~~java
package com.example.portal.config;

import java.util.Set;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.web.util.UriComponentsBuilder;

public final class LocaleAuthorizationRequestResolver
    implements OAuth2AuthorizationRequestResolver {

    private static final Set<String> ALLOWED_LOCALES = Set.of("vi", "en");

    private final OAuth2AuthorizationRequestResolver delegate;

    public LocaleAuthorizationRequestResolver(
        ClientRegistrationRepository registrations
    ) {
        this.delegate = new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            OAuth2AuthorizationRequestRedirectFilter
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
        );
    }

    @Override
    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
        return withLocale(request, delegate.resolve(request));
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
        HttpServletRequest request,
        String clientRegistrationId
    ) {
        return withLocale(request,
            delegate.resolve(request, clientRegistrationId));
    }

    private OAuth2AuthorizationRequest withLocale(
        HttpServletRequest servletRequest,
        OAuth2AuthorizationRequest original
    ) {
        if (original == null) {
            return null;
        }

        String locale = servletRequest.getParameter("lang");
        if (!ALLOWED_LOCALES.contains(locale)) {
            return original;
        }

        // URI đã do resolver mặc định dựng; locale chỉ có thể là "vi" / "en".
        String uri = UriComponentsBuilder
            .fromUriString(original.getAuthorizationRequestUri())
            .queryParam("ui_locales", locale)
            .build(true)
            .toUriString();

        return OAuth2AuthorizationRequest.from(original)
            .additionalParameters(params ->
                params.put("ui_locales", locale))
            .authorizationRequestUri(uri)
            .build();
    }
}
~~~

Bean và cấu hình filter:

~~~java
@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
    ClientRegistrationRepository registrations
) {
    return new LocaleAuthorizationRequestResolver(registrations);
}

// Gắn bean trên vào:
// http.oauth2Login(login -> login.authorizationEndpoint(endpoint ->
//     endpoint.authorizationRequestResolver(authorizationRequestResolver)));
~~~

**Vì sao phải điều chỉnh `authorizationRequestUri`?** Đây là URL mà filter thực sự dùng trong HTTP 302. Khi bọc một request đã được resolver mặc định xây dựng, chỉ sửa `additionalParameters` mà không kiểm soát URI cuối cùng có thể khiến dữ liệu trong object và URL redirect không còn nhất quán. Ví dụ minh họa đồng bộ cả hai trường, đồng thời giới hạn giá trị đầu vào.

**Vì sao dùng `OAuth2AuthorizationRequest.from(original)`?** Cách này kế thừa các giá trị đã được resolver mặc định tạo, đặc biệt **state**, redirect URI, nonce, scope và attributes cho PKCE khi có. Nếu tạo request hoàn toàn mới từ vài query parameter, rất dễ làm mất state hoặc code verifier cần thiết cho callback.

Ví dụ này cố ý không chấp nhận `issuer`, `client_id`, `redirect_uri`, `scope` hay một URL bất kỳ do người dùng gửi. Những giá trị đó phải đến từ cấu hình client registration và chính sách tin cậy của ứng dụng. Khi provider đã tự có `ui_locales` hoặc hỗ trợ nhiều nguồn locale, cần quyết định rõ quy tắc ghi đè, tránh thêm query parameter trùng lặp.

## 11. AuthorizationRequestRepository: nơi lưu request cho callback

Resolver tạo **`OAuth2AuthorizationRequest`**; filter tiếp tục nhờ **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`** lưu dữ liệu cần thiết trước khi browser rời Portal đến IdP.

Với Servlet OAuth2 login, cơ chế thường dùng mặc định là:

~~~java
HttpSessionOAuth2AuthorizationRequestRepository
~~~

Nó lưu authorization request vào HTTP session và giúp luồng callback tải/xóa request đã lưu để đối chiếu.

**Điều này khác với `OAuth2AuthorizedClientRepository`**:

| Thành phần | Lưu cái gì? | Thời điểm |
|---|---|---|
| **AuthorizationRequestRepository** | Authorization request đang chờ IdP phản hồi, gồm thông tin đối chiếu như state | **Trước khi** trao đổi code lấy token |
| **OAuth2AuthorizedClientRepository/Service** | Authorized client, access token và refresh token nếu được cấp | **Sau khi** OAuth2 authorization thành công |
| **SecurityContextRepository / HTTP session** | Authentication, principal và trạng thái đăng nhập | Khi người dùng được xác thực |
| **RequestCache** | URL/truy cập ban đầu mà người dùng muốn mở trước khi phải đăng nhập | Hỗ trợ quay về trang ban đầu sau login |

Không dùng kho authorized client để thay thế kho authorization request: đó là hai giai đoạn và hai cấu trúc dữ liệu khác nhau.

### 11.1. Tùy biến repository

Nếu có nhu cầu đặc biệt, Spring Security cho phép cấu hình:

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

@Bean
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
authorizationRequestRepository() {
    return new HttpSessionOAuth2AuthorizationRequestRepository();
}
~~~

Và gắn vào login configuration:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestRepository(authorizationRequestRepository)
    )
);
~~~

Đây là **đoạn minh họa cấu hình**, không phải yêu cầu phải khai báo một bean repository khi hành vi mặc định đã phù hợp. Nếu dùng kho tùy chỉnh dựa trên cookie hoặc lưu trữ phân tán, phải giữ nguyên các bảo vệ về **state, tính toàn vẹn, thời hạn và ràng buộc với đúng browser/phiên**. Không đưa dữ liệu nhạy cảm như PKCE verifier vào cookie có thể bị sửa hoặc đọc trái phép.

### 11.2. Ứng dụng chạy nhiều instance

Trong môi trường nhiều replica, authorization request được lưu trong session của một instance có thể không có mặt ở instance xử lý callback, trừ khi ứng dụng dùng session persistence phù hợp hoặc có định tuyến phiên thích hợp.

Ví dụ:

~~~text
Login start -> Portal instance A -> lưu state trong session A
Callback    -> Portal instance B -> không tìm thấy request tương ứng
~~~

Hậu quả có thể là callback không vượt qua kiểm tra state hoặc không tìm thấy authorization request. Khi chạy nhiều node, cần cấu hình session store/affinity theo thiết kế hạ tầng và bảo vệ dữ liệu session. Resolver đơn lẻ không giải quyết vấn đề lưu state phân tán.

## 12. So sánh oauth2Login() và oauth2Client() trên Servlet

Spring Security có hai cấu hình liên quan đến OAuth Client:

| Cấu hình | Mục tiêu chính | Tình huống |
|---|---|---|
| **`oauth2Login()`** | Đăng nhập người dùng qua OAuth 2.0/OIDC và tạo Authentication của ứng dụng | Portal có nút đăng nhập SSO |
| **`oauth2Client()`** | Hỗ trợ OAuth Client authorization và quản lý token/authorized client để gọi tài nguyên | Portal cần gọi Orders API thay mặt người dùng |

Ở một số ứng dụng, chỉ dùng **`oauth2Login()`** đã đủ để bắt đầu Authorization Code login. Nếu ứng dụng vừa đăng nhập vừa gọi API, cấu hình **`oauth2Client()`** cũng thường được dùng theo nhu cầu.

Với **OAuth2 Login**, hook cấu hình resolver là:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(customResolver)
    )
);
~~~

Với **OAuth2 Client Authorization Code Grant** trên Servlet, Spring Security còn có DSL tương ứng:

~~~java
http.oauth2Client(client -> client
    .authorizationCodeGrant(grant -> grant
        .authorizationRequestResolver(customResolver)
    )
);
~~~

Chọn hook tương ứng với luồng ứng dụng thực tế. Nếu sử dụng cả hai DSL, hãy bảo đảm cấu hình filter, base URI, resolver và repository không xung đột hoặc tạo hai cơ chế bắt đầu authorization không mong đợi.

**Đừng nhầm với Resource Server**: `oauth2ResourceServer()` bảo vệ API nhận Bearer token; nó không tạo authorization request để chuyển hướng browser đến IdP.

## 13. Thay đổi authorization request base URI có ảnh hưởng gì?

Ứng dụng có thể muốn URL bắt đầu login khác, chẳng hạn:

~~~text
/signin/oauth2/company
~~~

Khi đó, resolver có thể được tạo với base URI mới:

~~~java
DefaultOAuth2AuthorizationRequestResolver resolver =
    new DefaultOAuth2AuthorizationRequestResolver(
        registrations,
        "/signin/oauth2"
    );
~~~

Cần bảo đảm URL mà `OAuth2AuthorizationRequestRedirectFilter` xử lý tương ứng với resolver đã cấu hình, ví dụ qua `authorizationEndpoint(...).authorizationRequestResolver(...)`.

Một số chú ý:

- Link đăng nhập trong template/HTML phải trỏ tới base URI mới.
- **Redirect URI callback** có thể vẫn là `/login/oauth2/code/company`; thay đổi URL bắt đầu không bắt buộc thay đổi callback.
- Nếu đổi callback, cần cấu hình **redirectionEndpoint().baseUri(...)** và **registration.redirect-uri** đồng bộ, đồng thời cập nhật redirect URI tại IdP.
- Tránh dùng chung base URI với controller nghiệp vụ có ý nghĩa khác.
- Nếu ứng dụng đứng sau reverse proxy hoặc path prefix, phải tính đến scheme/host/prefix bên ngoài khi tạo `redirect_uri`.

## 14. Nhiều provider, nhiều client registration

Một ứng dụng có thể tích hợp nhiều IdP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${COMPANY_ISSUER_URI}
          partner:
            issuer-uri: ${PARTNER_ISSUER_URI}
~~~

Đây là **ví dụ thay thế cho phần registration trong mục 7**, không phải đoạn YAML cần dán nối vào file hiện tại.

Với base URI mặc định, các link tương ứng:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Resolver lấy đúng `ClientRegistration` dựa trên ID, nên:

- **company** có issuer, client ID, redirect URI và scope của company.
- **partner** có bộ cấu hình riêng theo registration.
- ID trên URL phải được quản lý trong repository, không tự tạo một cấu hình IdP từ URL bất kỳ do client gửi.

Nếu muốn thêm `prompt=select_account` chỉ cho company, có thể dùng resolver bọc và kiểm tra registration cụ thể trước khi tùy chỉnh. Không áp dụng tham số riêng của một provider cho tất cả provider nếu nhà cung cấp khác không hỗ trợ.

## 15. Các ranh giới bảo mật khi tùy biến resolver

Resolver nằm tại điểm đầu của luồng authorization, do đó là nơi dễ phát sinh lỗi nếu tùy biến từ dữ liệu không tin cậy.

### 15.1. Không cho người dùng tự quyết định các tham số nhạy cảm

Tránh cách thiết kế:

~~~text
/oauth2/authorization/company
    ?redirect_uri=https://attacker.example/callback
    &client_id=unknown-client
    &scope=admin
~~~

Rồi chép thẳng query parameter vào `OAuth2AuthorizationRequest`. Cách đó có thể dẫn đến open redirect, yêu cầu quyền sai hoặc đánh lạc hướng luồng xác thực.

Các giá trị như **client ID**, **authorization URI**, **redirect URI**, **scope hợp lệ** và **provider** phải đến từ cấu hình đáng tin cậy hoặc một tập lựa chọn do ứng dụng kiểm soát.

### 15.2. Bảo toàn state

**state** cần được tạo mới, lưu đúng phiên và kiểm tra khi IdP gọi callback. Không dùng state cố định, không ghi đè state bằng giá trị do browser truyền và không bỏ repository chỉ để “fix lỗi invalid_state”.

### 15.3. Giữ PKCE/nonce nhất quán

Khi tùy biến builder:

- Không xóa `code_challenge` nếu đang dùng PKCE.
- Không gửi `code_verifier` đến authorization endpoint.
- Không phá hủy attributes mà Spring Security lưu để dùng khi đổi code.
- Không loại bỏ hoặc sửa sai `nonce` trong luồng OIDC.
- Không tự thay `response_type=code` bằng response type khác khi ứng dụng được cấu hình xử lý Authorization Code Flow.

### 15.4. Không lộ dữ liệu khi debug

Authorization redirect URL có thể chứa **state**, **nonce**, **login_hint** hoặc các tham số khác liên quan đến phiên người dùng. Không ghi nguyên URL đó vào log công khai hay hệ thống phân tích dữ liệu. **Client secret**, token response và code verifier càng không được log. Nếu cần điều tra, ghi tên registration, loại grant, hostname IdP đã phê duyệt và kết quả lỗi mà không ghi credential.

### 15.5. Proxy, HTTPS và callback

Khi Portal nằm sau reverse proxy, `{baseUrl}` dùng cho redirect URI phải phản ánh URL công khai, thường là **HTTPS**, thay vì hostname/port nội bộ của container. Nếu dùng:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

thì cần cấu hình trusted proxy lọc và cấp đúng `Forwarded`/`X-Forwarded-*` headers, không tin header tùy ý từ người dùng bên ngoài. Callback cuối cùng vẫn phải khớp URI được đăng ký tại IdP.

## 16. Theo dõi hành vi resolver bằng HTTP request

Khi Portal, IdP và các biến môi trường đã được cấu hình, có thể kiểm tra bước tạo authorization request mà chưa cần hoàn tất đăng nhập.

### 16.1. Gửi yêu cầu bắt đầu login

~~~bash
curl -i "http://localhost:8080/oauth2/authorization/company"
~~~

Với cấu hình hợp lệ, response thường là redirect:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=...
Set-Cookie: JSESSIONID=<session-value>; Path=/; HttpOnly
~~~

Đây là **phản hồi minh họa**, không phải output đã chạy. Header `Location` thực tế sẽ có các tham số đã encode, và cookie/header phụ thuộc cấu hình session.

### 16.2. Những điểm cần quan sát

| Điều quan sát | Kết quả mong đợi |
|---|---|
| Đường dẫn gọi Portal | `/oauth2/authorization/company` đúng base URI và registration ID |
| HTTP status | Thường là **302** đến authorization endpoint của IdP |
| **client_id** | Khớp cấu hình của **company** |
| **response_type** | `code` |
| **redirect_uri** | Callback công khai đúng scheme, host, path và registration |
| **scope** | Các scope được IdP hỗ trợ; OIDC login phải có `openid` |
| **state** | Có giá trị ngẫu nhiên, khác giữa các authorization request độc lập |
| **nonce** | Được tạo khi áp dụng OIDC theo cơ chế provider/framework |
| **code_challenge** | Có khi PKCE đã được kích hoạt; `code_verifier` không nằm trong redirect URL |
| **prompt/ui_locales** | Xuất hiện đúng khi customizer/resolver bổ sung và provider hỗ trợ |

Đừng chia sẻ nguyên `Location` thực tế nếu có state, nonce, login hint hoặc dữ liệu riêng tư. Có thể kiểm tra tên và sự có mặt của các tham số với giá trị đã che.

### 16.3. Thử request ngoài base URI

Ví dụ:

~~~text
/any/other/path
~~~

Resolver mặc định không phải một controller nhận tất cả đường dẫn; filter sẽ không biến mọi request thành authorization request. URL ngoài phạm vi xử lý tiếp tục đi qua các filter/controller khác theo cấu hình security.

### 16.4. Thử registration ID chưa được khai báo

Ví dụ:

~~~text
/oauth2/authorization/unknown
~~~

Nếu không có `ClientRegistration` tương ứng, không thể khởi tạo authorization request hợp lệ tới IdP. Hành vi lỗi HTTP chính xác phụ thuộc phiên bản framework và cấu hình xử lý ngoại lệ; không nên tự suy ra luôn trả một mã cố định mà không kiểm tra ứng dụng.

## 17. Troubleshooting: lỗi thường gặp với authorization request

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra / xử lý |
|---|---|---|
| Nhấp đăng nhập không chuyển tới IdP | URL không khớp base URI, thiếu starter hoặc OAuth2 Login chưa bật | Kiểm tra link, `oauth2Login()`, `ClientRegistrationRepository` |
| URL tạo ra không có registration đúng | Gọi sai `/oauth2/authorization/{id}` | Xác nhận registration ID trong YAML và URL |
| IdP báo **invalid_redirect_uri** | `redirect_uri` không khớp whitelist ở IdP | So sánh URL đã encode sau decode, scheme/host/port/path |
| Callback dùng HTTP dù bên ngoài là HTTPS | Reverse proxy/forwarded headers không đúng | Kiểm tra trusted proxy, `{baseUrl}` và HTTPS termination |
| Resolver tùy biến không được gọi | Chưa gắn bean vào DSL hoặc filter sử dụng resolver khác | Kiểm tra `authorizationEndpoint().authorizationRequestResolver(...)` |
| `prompt` không xuất hiện | Chỉ thay object mà không cập nhật URI cuối, hoặc customizer không chạy | Kiểm tra resolver được sử dụng và `authorizationRequestUri` |
| Tham số provider không được IdP chấp nhận | Provider không hỗ trợ hoặc sai giá trị | Đối chiếu tài liệu IdP và phạm vi registration |
| Callback báo state mismatch | Mất session, browser chặn cookie, dùng lại state hoặc kho request không nhất quán | Kiểm tra phiên browser, session store, proxy/cookie |
| Callback lỗi khi PKCE được bật | Không giữ `code_verifier` hoặc provider không chấp nhận PKCE mode đã gửi | Bảo toàn request attributes và chính sách PKCE của IdP |
| Login đôi khi lỗi trên nhiều replica | Request được lưu ở node A nhưng callback vào node B | Thiết kế session persistence hoặc routing theo hạ tầng |
| Login thành công nhưng API trả 403 | Token chưa được cấp đủ scope hoặc API áp chính sách quyền | Phân biệt bước authorization request với phân quyền ở Resource Server |

Những lỗi sau callback cũng có thể xuất phát từ **token endpoint**, client secret, token authentication hoặc OIDC validation; không quy tất cả thành vấn đề của resolver. Cần xác định yêu cầu đã **tạo URL và redirect** thành công hay chưa để khoanh vùng đúng lớp chịu trách nhiệm.

## 18. Những nhầm lẫn thường gặp

**“Resolver có nhiệm vụ gọi Authorization Server để lấy token.”** Không. Nó tạo request để browser đi tới authorization endpoint. Việc đổi code lấy token diễn ra sau callback và do các thành phần client authentication khác thực hiện.

**“Authorization request là access token.”** Không. Authorization request là yêu cầu bắt đầu cấp quyền; access token chỉ có thể được nhận ở giai đoạn phát hành token sau đó.

**“Chỉ cần tạo một URL có client_id và scope là đủ.”** Không. Authorization Code Flow còn cần redirect URI hợp lệ, state, các tham số và dữ liệu bảo vệ giao dịch. Nếu tự dựng URL mà bỏ qua repository, nonce hoặc PKCE sẽ rất dễ làm hỏng login và phát sinh rủi ro bảo mật.

**“`/oauth2/authorization/company` là endpoint của IdP.”** Không. Đó là endpoint khởi tạo ở Portal, do Spring Security filter xử lý. IdP có authorization endpoint riêng, thông thường là một URL HTTPS khác.

**“Đổi authorization request base URI đồng nghĩa đã đổi callback URI.”** Không. Bước bắt đầu và bước callback có cấu hình riêng; nếu đổi callback, phải cấu hình đồng bộ với IdP.

**“Có thể thay redirect_uri theo query parameter.”** Không nên. Redirect URI phải được đăng ký và kiểm soát; tùy biến từ dữ liệu không tin cậy dễ gây open redirect hoặc thất bại authorization.

**“Khai báo `@Bean DefaultOAuth2AuthorizationRequestResolver` là mọi filter tự dùng.”** Không nên giả định. Hãy gắn resolver thông qua cấu hình `authorizationEndpoint().authorizationRequestResolver(...)` hoặc hook OAuth2 Client phù hợp.

**“OIDC login và OAuth2 Resource Server dùng chung resolver.”** Không. Resolver thuộc OAuth2 Client bắt đầu authorization; Resource Server xác minh Bearer token cho request API.

## 19. Bài tập ứng dụng

Giả sử Portal có hai registration:

~~~text
company -> OIDC Provider công ty
partner -> OIDC Provider đối tác
~~~

Yêu cầu:

1. Người dùng công ty nhấp **Đăng nhập công ty**, ứng dụng phải chuyển tới IdP company.
2. Người dùng đối tác nhấp **Đăng nhập đối tác**, ứng dụng phải chuyển tới IdP partner.
3. Chỉ công ty yêu cầu hiển thị màn hình chọn tài khoản bằng `prompt=select_account`.
4. Cả hai cần Authorization Code Flow an toàn, state khác nhau theo request; company dùng PKCE khi IdP hỗ trợ.
5. Trên production, callback company là `https://portal.example.test/login/oauth2/code/company`.

Hãy xác định:

- Link bắt đầu authorization cho từng provider là gì?
- Thành phần nào tra cứu registration, sinh state và tạo URL redirect?
- `prompt` nên được thêm ở đâu để không ảnh hưởng partner?
- Ai lưu authorization request trước khi browser rời Portal?
- Thành phần nào nhận authorization code khi callback?
- Có thể truyền `redirect_uri` tùy ý trong query parameter của link đăng nhập không?

**Hướng giải:**

1. Link mặc định là `/oauth2/authorization/company` và `/oauth2/authorization/partner`.
2. **DefaultOAuth2AuthorizationRequestResolver** tạo `OAuth2AuthorizationRequest` dựa trên `ClientRegistrationRepository`; **OAuth2AuthorizationRequestRedirectFilter** dùng kết quả để redirect.
3. Bọc resolver mặc định hoặc có customizer với logic giới hạn theo registration **company**; không thêm prompt của company cho mọi provider.
4. **AuthorizationRequestRepository**, thường là `HttpSessionOAuth2AuthorizationRequestRepository`.
5. **OAuth2LoginAuthenticationFilter** xử lý callback trong luồng OAuth2 Login, phối hợp các thành phần đổi code/kiểm tra xác thực.
6. Không. Redirect URI phải đến từ cấu hình được kiểm soát và được IdP cho phép.

## 20. Kết luận kiến trúc

Trong **Spring Security OAuth 2.0 Client trên Servlet**, **`OAuth2AuthorizationRequestResolver`** quyết định cách xây dựng **authorization request** từ HTTP request và client registration. **`DefaultOAuth2AuthorizationRequestResolver`** đã cung cấp hành vi tiêu chuẩn cho Authorization Code Flow, gồm lựa chọn registration, tạo request và phối hợp các tham số bảo vệ giao dịch theo cấu hình.

**`OAuth2AuthorizationRequestRedirectFilter`** nhận request object, lưu dữ liệu cần thiết qua **`AuthorizationRequestRepository`** rồi chuyển hướng browser đến Authorization Server. Sau khi IdP trả về authorization code, filter xử lý callback và các thành phần OAuth Client khác mới tiếp tục xác minh trạng thái, đổi code lấy token và hoàn tất phiên đăng nhập.

Trong phần lớn dự án, hãy **dùng resolver mặc định và chỉ tùy chỉnh những tham số thật sự cần thiết** thông qua `setAuthorizationRequestCustomizer(...)`. Khi yêu cầu phụ thuộc context HTTP, bọc resolver mặc định, giữ nguyên state, nonce, PKCE và redirect URI, đồng thời giới hạn dữ liệu đầu vào. Cách phân chia này vừa phù hợp với cơ chế của Spring Security Servlet vừa giữ Authorization Code/OIDC login nhất quán và an toàn giữa các môi trường.
