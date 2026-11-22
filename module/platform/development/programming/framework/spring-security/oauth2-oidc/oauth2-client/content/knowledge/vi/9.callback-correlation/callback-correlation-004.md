# 9.4. Đối chiếu Redirect URI và redirectionEndpoint base URI

## 1. Tình huống: đăng nhập ở IdP thành công nhưng không quay lại được Portal

Employee Portal là ứng dụng Spring Boot dùng **Spring Security OAuth 2.0 Client** để cho nhân viên đăng nhập qua **OpenID Connect (OIDC)**. Người dùng mở:

~~~text
https://portal.example.test/oauth2/authorization/company
~~~

Spring Security chuyển trình duyệt đến Authorization Server của công ty. Người dùng xác thực thành công, nhưng sau đó nhận một trong các lỗi:

- IdP thông báo **invalid_redirect_uri / redirect_uri_mismatch**.
- Trình duyệt quay về Portal nhưng nhận **404**, bị đưa về trang đăng nhập lần nữa hoặc rơi vào vòng lặp redirect.
- Trang lỗi có **authorization_request_not_found**, **invalid_state**, hoặc một thông báo OAuth2 Login thất bại.
- Local hoạt động, nhưng staging/production lỗi vì callback sinh ra **http://** hoặc hostname nội bộ thay vì **https://** và hostname công khai.

Những triệu chứng trên thường xuất hiện khi ba nơi sau **không thống nhất**:

1. **Redirect URI** mà OAuth Client gửi cho IdP khi bắt đầu Authorization Code Flow.
2. **redirectionEndpoint base URI** mà Spring Security Servlet dùng để **nhận và xử lý callback**.
3. **Allowed/registered redirect URI** tại IdP, là danh sách callback mà Authorization Server cho phép.

Trong ngữ cảnh chương **Callback và correlation**, cần hiểu thêm cách **state** và **authorization request đã lưu** được dùng để liên kết callback với yêu cầu đăng nhập ban đầu. Callback có đường dẫn đúng nhưng session hoặc state không còn vẫn có thể thất bại.

Mục tiêu của bài là cấu hình nhất quán **Redirect URI ↔ callback matcher ↔ IdP**, hiểu vai trò từng thành phần và biết xác định lỗi nằm ở bước nào.

> Ví dụ sử dụng **Java 17+, Spring Boot 3 / Spring Security 6, Servlet stack (Spring MVC)**, registration ID **company**. Mọi domain, client ID và secret đều là ví dụ. Mô hình tương ứng với một OAuth2/OIDC web client dùng **Authorization Code Flow**; không phải mô hình Resource Server kiểm tra bearer token.

## 2. Phân biệt bốn URI trong một lần đăng nhập

Những URI này dễ bị nhầm vì có từ “authorization”, “redirect” hoặc “callback”:

| Thành phần | Ví dụ | Nằm ở đâu? | Mục đích |
|---|---|---|---|
| **Authorization request base URI** | `/oauth2/authorization` | **Portal** | URL người dùng nhấp để yêu cầu Spring bắt đầu login |
| **Authorization URI của provider** | `https://login.example.test/oauth2/authorize` | **IdP** | Endpoint nhận yêu cầu ủy quyền |
| **OAuth2 Client redirect URI** | `https://portal.example.test/login/oauth2/code/company` | **Portal**, được gửi như tham số `redirect_uri` tới IdP | Địa chỉ IdP chuyển browser trở về sau khi hoàn tất bước ủy quyền |
| **redirectionEndpoint base URI** | `/login/oauth2/code/*` | **Spring Security Servlet** | Pattern để filter tiếp nhận callback gửi vào Portal |

**Authorization request base URI** và **redirectionEndpoint base URI** nằm ở hai đầu khác nhau của luồng. Cái thứ nhất kích hoạt **bước đi đến IdP**; cái thứ hai tiếp nhận **bước từ IdP trở về**.

Ví dụ:

~~~text
Browser                                 Employee Portal
  │
  ├─ GET /oauth2/authorization/company ──────► Bắt đầu ủy quyền
  │                                                  │
  ◄──────────── 302 đến IdP (Location) ──────────────┤
  │
  ├─ GET https://login.example.test/oauth2/authorize?... ──► IdP
  │
  ◄──────────── 302 redirect_uri?code=...&state=... ─────── IdP
  │
  └─ GET /login/oauth2/code/company?code=...&state=... ──► Callback filter
~~~

**Client redirect URI là một URL đầy đủ**, gồm scheme, host, port (nếu có), path và có thể có những thành phần URL hợp lệ khác theo hợp đồng IdP. **redirectionEndpoint base URI là mẫu đường dẫn xử lý request**, thường có ký tự wildcard để match nhiều registration ID. Chúng không nhất thiết là hai chuỗi giống hệt nhau, nhưng **đường dẫn của redirect URI phải khớp pattern callback của Spring Security** sau khi proxy/context path được xử lý.

## 3. Giá trị mặc định của Spring Security Servlet

Spring Security cung cấp các mặc định giúp đăng nhập OAuth2/OIDC hoạt động mà không cần tự khai báo callback controller:

| Cấu hình / hằng số | Giá trị thường dùng |
|---|---|
| `OAuth2AuthorizationRequestRedirectFilter.DEFAULT_AUTHORIZATION_REQUEST_BASE_URI` | `/oauth2/authorization` |
| URL khởi tạo theo registration ID | `/oauth2/authorization/{registrationId}` |
| `OAuth2LoginAuthenticationFilter.DEFAULT_FILTER_PROCESSES_URI` | `/login/oauth2/code/*` |
| Redirect URI template thường dùng của client registration | `{baseUrl}/login/oauth2/code/{registrationId}` |

Với registration ID **company**, bộ giá trị này cho kết quả:

~~~text
Khởi tạo login ở Portal:
    /oauth2/authorization/company

Redirect URI được gửi tới IdP:
    https://portal.example.test/login/oauth2/code/company

Pattern callback được Spring Security xử lý:
    /login/oauth2/code/*

Registered redirect URI tại IdP:
    https://portal.example.test/login/oauth2/code/company
~~~

Hằng số filter callback có dấu `*` để chấp nhận đường dẫn theo registration, còn giá trị redirect URI thực tế có **company**. Nếu IdP áp dụng chính sách đối chiếu URI chính xác, hãy đăng ký **URL thực**, không đăng ký pattern Servlet của Spring với dấu `*`.

### 3.1. Điểm quan trọng về registrationId

Trong Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal-prod
~~~

**company** là **registration ID** nội bộ mà Spring dùng để chọn `ClientRegistration`. **employee-portal-prod** là **client ID** mà IdP cấp. Chúng không bắt buộc trùng nhau.

Giá trị `{registrationId}` trong callback template thông thường sẽ thành **company**, chứ không thành **employee-portal-prod**.

## 4. Callback được xử lý qua filter nào?

Luồng OAuth2 Login trên Servlet thường liên quan tới các thành phần sau:

- **`OAuth2AuthorizationRequestRedirectFilter`**: bắt đầu authorization request và redirect browser sang IdP.
- **`OAuth2AuthorizationRequestResolver`**: xây dựng authorization request dựa trên client registration và HTTP request.
- **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`**: lưu authorization request trước khi browser rời Portal.
- **`OAuth2LoginAuthenticationFilter`**: match callback theo URL, xử lý authorization response và chuyển việc xác thực/đổi code đến những thành phần liên quan.
- **`OAuth2AuthorizedClientRepository/Service`**: lưu authorized client và token khi quá trình authorization thành công.
- **`SecurityContext`**: lưu Authentication của người dùng sau khi đăng nhập.

Sơ đồ luồng:

~~~mermaid
sequenceDiagram
    actor User as Nhân viên
    participant Browser as Browser
    participant Portal as Portal (Spring Security)
    participant Repo as AuthorizationRequestRepository
    participant IdP as IdP / Authorization Server

    User->>Browser: Nhấn Đăng nhập công ty
    Browser->>Portal: GET /oauth2/authorization/company
    Portal->>Portal: Resolver tạo request, state và redirect_uri
    Portal->>Repo: Lưu authorization request vào phiên
    Portal-->>Browser: 302 đến authorization endpoint
    Browser->>IdP: GET /authorize?client_id=...&redirect_uri=...&state=...
    IdP->>User: Xác thực và consent khi cần
    IdP-->>Browser: 302 tới redirect_uri?code=...&state=...
    Browser->>Portal: GET /login/oauth2/code/company?code=...&state=...
    Portal->>Portal: OAuth2LoginAuthenticationFilter match callback path
    Portal->>Repo: Tìm/lấy request ban đầu để đối chiếu state
    Portal->>IdP: Đổi authorization code lấy token
    IdP-->>Portal: ID Token, access token và token khác nếu được cấp
    Portal->>Portal: Kiểm tra token, tạo Authentication và lưu authorized client
    Portal-->>Browser: Tạo session và chuyển đến trang ứng dụng
~~~

**redirectionEndpoint base URI chỉ quyết định callback nào được filter này tiếp nhận.** Nó không tự thay đổi redirect URI trong request gửi tới IdP, không tự đăng ký URL ở IdP và không thay thế kiểm tra **state**.

### 4.1. Không cần tự tạo @GetMapping cho callback mặc định

Nếu dùng `oauth2Login()` chuẩn, đường dẫn:

~~~text
/login/oauth2/code/company
~~~

được **Security Filter Chain** xử lý. Một controller như:

~~~java
@GetMapping("/login/oauth2/code/company")
String callback() {
    return "ok";
}
~~~

không phải cách chuẩn để hoàn tất OIDC login. Callback cần xử lý **state**, authorization code, token endpoint và OIDC validation; filter của Spring Security đảm nhận các bước này. Chỉ xây luồng callback tùy chỉnh khi thực sự có yêu cầu và hiểu toàn bộ trách nhiệm bảo mật liên quan.

## 5. Cấu hình mặc định tối thiểu trong Spring Boot

Giả sử Portal chạy trên `http://localhost:8080` trong môi trường phát triển.

### 5.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

**spring-boot-starter-web** chọn Servlet/MVC; **spring-boot-starter-oauth2-client** cung cấp OAuth2 Client và OIDC login. Nếu ứng dụng sử dụng WebFlux, callback filter và API cấu hình không hoàn toàn giống ví dụ này.

### 5.2. Client registration

~~~yaml
# application.yml
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
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Các giá trị trong placeholder phải được môi trường chạy cung cấp. **client secret** là bí mật của confidential web client, không được commit vào Git hoặc đưa vào frontend.

**issuer-uri** là danh tính của provider; khi IdP hỗ trợ metadata discovery, Spring Security có thể tìm các endpoint cần thiết. **redirect-uri** là template thuộc client registration, được mở rộng khi bắt đầu authorization request.

### 5.3. SecurityFilterChain

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
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong cấu hình này, không phải khai báo `redirectionEndpoint().baseUri(...)` vì matcher mặc định đã tương ứng với template redirect URI ở YAML.

Khi browser truy cập `http://localhost:8080/oauth2/authorization/company`, Portal sinh authorization request có redirect URI:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

URI đó phải được phép ở client registration bên IdP dành cho local. Không dùng client/secret production trong local nếu không có yêu cầu và chính sách cho phép.

## 6. Muốn đổi callback path: thay đổi ba nơi đồng thời

Giả sử nhóm phát triển muốn URL callback của Portal thành:

~~~text
https://portal.example.test/auth/callback/company
~~~

thay vì:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

**Chỉ sửa một nơi sẽ không đủ.** Cần cập nhật:

| Nơi cấu hình | Mới | Tại sao? |
|---|---|---|
| **ClientRegistration.redirectUri** | `{baseUrl}/auth/callback/{registrationId}` | Đưa giá trị mới vào tham số `redirect_uri` gửi tới IdP |
| **redirectionEndpoint.baseUri** | `/auth/callback/*` | Cho `OAuth2LoginAuthenticationFilter` nhận callback theo path mới |
| **Allowed redirect URI tại IdP** | `https://portal.example.test/auth/callback/company` | Cho phép Authorization Server chuyển browser về đúng Portal |

Trong đó:

- Hai giá trị đầu là **cấu hình ứng dụng**.
- Giá trị cuối là **cấu hình client ở IdP**, thường phải thay trong trang quản trị hoặc hệ thống cấp phát client registration.
- Nếu có nhiều môi trường, phải có registered redirect URI đúng cho từng môi trường.

### 6.1. application.yml sau khi đổi callback

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

### 6.2. SecurityFilterChain nhận callback mới

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .redirectionEndpoint(redirection -> redirection
                    .baseUri("/auth/callback/*")))
            .build();
    }
}
~~~

Đây là **phương án thay thế** cấu hình của mục 5, không tạo thêm `SecurityFilterChain` thứ hai giống hệt nhau.

Trong DSL này, **`redirectionEndpoint(...).baseUri("/auth/callback/*")`** điều chỉnh matcher của callback filter. Nó **không phải URL đầy đủ** và không nhận một URL IdP khác làm giá trị. Path phải tương ứng với đường dẫn redirect sau khi servlet context path được xem xét.

### 6.3. Đăng ký với IdP

Ở IdP production, đăng ký cụ thể:

~~~text
https://portal.example.test/auth/callback/company
~~~

Ở IdP staging, nếu Portal công khai qua một hostname khác:

~~~text
https://portal.staging.example.test/auth/callback/company
~~~

Với local:

~~~text
http://localhost:8080/auth/callback/company
~~~

Những URI trên thuộc **các client/môi trường được quản lý tương ứng**. Không đăng ký `/auth/callback/*` với IdP rồi giả định mọi nhà cung cấp đều cho phép wildcard. Nhiều provider đòi hỏi URI chính xác, và wildcard có thể làm tăng rủi ro nếu bị dùng quá rộng.

### 6.4. Đổi callback không có nghĩa đổi URL bắt đầu đăng nhập

Sau khi đổi callback sang `/auth/callback/*`, URL kích hoạt authorization request **vẫn có thể** là:

~~~text
/oauth2/authorization/company
~~~

Đây là hai hướng khác nhau của luồng. Nếu muốn đổi URL khởi tạo login, phải cấu hình riêng **authorization endpoint/request resolver**, ví dụ sử dụng `authorizationRequestResolver` tương ứng. Không trộn cấu hình authorization request base URI với redirectionEndpoint base URI.

## 7. Thế nào là “đối chiếu Redirect URI”?

Khi nói đến “đối chiếu Redirect URI”, cần xác định **đối chiếu ở ba tầng**:

1. **Ở Authorization Server**: URI trong tham số `redirect_uri` của authorization request phải được IdP chấp nhận theo client registration và quy tắc so khớp của IdP.
2. **Ở OAuth2 Client khi nhận callback**: HTTP path của request trả về cần khớp matcher của `OAuth2LoginAuthenticationFilter`, do `redirectionEndpoint.baseUri` quyết định.
3. **Ở luồng tương quan (correlation)**: callback cần có `state` phù hợp với authorization request đã được lưu; code và các tham số phải được xử lý theo cùng một giao dịch. Token request sau đó phải tuân theo yêu cầu Authorization Code Flow, gồm `redirect_uri` khi bắt buộc.

**Đối chiếu này không có nghĩa Spring Security có một cơ chế duy nhất tự đồng bộ cả ba nơi.** Một ứng dụng có thể cấu hình callback matcher đúng nhưng IdP từ chối URI; hoặc IdP chấp nhận URI nhưng Spring Security không match path.

### 7.1. Tại Authorization Server: so khớp URI đã đăng ký

Ví dụ IdP đã đăng ký:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

nhưng Portal gửi:

~~~text
http://portal.example.test/login/oauth2/code/company
~~~

Do khác **scheme**, URI có thể bị từ chối dù host/path trông giống nhau. Tương tự, khác **port, path, dấu /** ở cuối hoặc hostname công khai/nội bộ** đều có thể gây mismatch.

Nên cấu hình chính xác redirect URI và áp dụng quy tắc so khớp bảo mật của provider. Không dựa vào việc IdP “tự đoán” hoặc tự sửa URL để chấp nhận callback.

### 7.2. Tại Portal: match path callback

Giả sử IdP được phép chuyển về:

~~~text
https://portal.example.test/auth/callback/company?code=...&state=...
~~~

nhưng Spring Security vẫn chỉ match:

~~~text
/login/oauth2/code/*
~~~

Thì request vào `/auth/callback/company` **không được callback filter xử lý theo cấu hình đó**. Request có thể rơi sang controller, security entry point hoặc error handler khác; cụ thể trả 404, 302 hay một lỗi khác phụ thuộc ứng dụng.

### 7.3. Tại callback correlation: state và request ban đầu

Ngay cả khi callback path khớp, request vẫn có thể thất bại nếu:

- Browser mất session cookie đã dùng khi bắt đầu login.
- Authorization request đã lưu không còn tồn tại hoặc bị hết hạn/xóa.
- Callback chứa `state` khác state ban đầu.
- Callback được mở lại sau khi authorization request đã bị tiêu thụ.
- Multi-instance deployment dùng bộ lưu session không thống nhất.

Vì vậy, **callback path đúng là điều kiện cần để filter chạy, nhưng chưa đủ để hoàn tất OAuth2/OIDC login**.

## 8. AuthorizationRequestRepository và state: phần “correlation” của callback

Trong luồng Servlet thông thường:

1. `OAuth2AuthorizationRequestResolver` sinh `OAuth2AuthorizationRequest`, trong đó có `state`, redirect URI và các thông tin grant.
2. `OAuth2AuthorizationRequestRedirectFilter` lưu request bằng `AuthorizationRequestRepository` rồi chuyển hướng browser.
3. IdP nhận authorization request và sau đó gửi callback chứa authorization code, state tương ứng (nếu thành công).
4. `OAuth2LoginAuthenticationFilter` nhận callback và tìm authorization request phù hợp.
5. Spring Security sử dụng request đã lưu để xử lý authorization response và đối chiếu giao dịch trước khi đổi code lấy token.

Triển khai phổ biến ở ứng dụng Servlet có session:

~~~java
org.springframework.security.oauth2.client.web
    .HttpSessionOAuth2AuthorizationRequestRepository
~~~

Repository này khác với **`OAuth2AuthorizedClientRepository`**:

| Kho lưu trữ | Dữ liệu | Giai đoạn |
|---|---|---|
| **AuthorizationRequestRepository** | Authorization request đang chờ, gồm state và các thuộc tính cần cho callback | Từ lúc bắt đầu authorization đến lúc callback |
| **OAuth2AuthorizedClientRepository/Service** | Access token/refresh token và thông tin authorized client | Sau khi được cấp quyền thành công |
| **SecurityContextRepository/session** | Authentication của người dùng | Sau khi đăng nhập thành công |

**Không nên “sửa lỗi state” bằng cách bỏ kiểm tra state** hoặc cố định state thành một hằng số. State là thành phần bảo vệ việc liên kết authorization response với yêu cầu ban đầu. Với OIDC còn có các quy tắc nonce và xác minh ID Token riêng; không dùng nonce thay state.

### 8.1. Callback không nhất thiết phải có path chứa registration ID để tương quan

Ví dụ thường dùng có `/login/oauth2/code/company` vì template dùng `{registrationId}`. Tuy nhiên, điều cốt lõi của callback correlation không phải “đọc registration ID từ path rồi tin tưởng ngay”. Spring Security có thể dựa vào **authorization request đã lưu và state** để xác định registration/transaction phù hợp.

Khi thiết kế callback tùy chỉnh, cần đảm bảo matcher, redirect URI và repository thống nhất. Không suy ra rằng có chuỗi `company` trong path thì callback tự hợp lệ.

### 8.2. Cách kiểm soát một phiên đăng nhập đang chờ

Không nên cho người dùng mở callback URL bằng tay với `code` hoặc `state` tự tạo. Giá trị phải thuộc giao dịch Authorization Code thực sự. Dữ liệu nhạy cảm liên quan đến giao dịch không được đưa vào log hoặc công cụ phân tích web.

Ở ứng dụng nhiều tab hoặc nhiều login flow đồng thời, cần cân nhắc cách repository lưu, tìm và tiêu thụ authorization request để tránh mất state. Triển khai tùy biến phải hỗ trợ chính sách đồng thời và tương quan phù hợp; không đơn giản lưu “state mới nhất” trong một biến dùng chung cho tất cả user.

## 9. Redirect URI được tạo từ {baseUrl} như thế nào?

Trong client registration:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

**`{baseUrl}`** là template variable được Spring Security mở rộng dựa trên URL mà ứng dụng nhận diện cho request hiện tại. Nó có thể bao gồm scheme, host, port và context path bên ngoài theo thông tin request đã được xử lý.

Ví dụ khi truy cập trực tiếp local:

~~~text
http://localhost:8080 + /login/oauth2/code/company
    = http://localhost:8080/login/oauth2/code/company
~~~

Khi triển khai sau reverse proxy:

~~~text
Browser ──HTTPS──► https://portal.example.test
                     │
                     ▼
               Reverse Proxy
                     │  HTTP nội bộ
                     ▼
               portal-service:8080
~~~

Nếu ứng dụng **không nhận diện đúng scheme và hostname bên ngoài**, `{baseUrl}` có thể trở thành:

~~~text
http://portal-service:8080
~~~

và dẫn tới:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

IdP production được cấu hình cho **https://portal.example.test** thường sẽ từ chối URI nội bộ đó.

### 9.1. Forwarded headers

Spring Boot Servlet có thể được cấu hình:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Reverse proxy hoặc ingress chuyển tiếp các thông tin cần thiết như scheme/host/port/prefix thông qua `Forwarded` hoặc `X-Forwarded-*` theo cách được triển khai.

**Điều kiện an toàn:** chỉ tin tưởng forwarded headers do proxy đáng tin cậy kiểm soát. Proxy phải loại bỏ hoặc ghi đè header giả do client Internet gửi vào; nếu không, người dùng bên ngoài có thể tác động đến URL mà backend tạo ra.

Khi cấu hình xong, kiểm tra giá trị `redirect_uri` **thực sự xuất hiện trong Location redirect sang IdP**, thay vì chỉ nhìn vào property YAML và phỏng đoán Spring đã suy ra đúng URL.

### 9.2. Giữ redirect URI cố định khi hạ tầng đòi hỏi

Một phương án khác là cấu hình redirect URI qua property runtime:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: ${OIDC_REDIRECT_URI}
~~~

Ví dụ ở production:

~~~text
OIDC_REDIRECT_URI=https://portal.example.test/login/oauth2/code/company
~~~

Cách này giảm phụ thuộc vào việc suy ra public host của request khi thiết kế có **một public callback URL cố định**. Tuy nhiên, URL callback vẫn phải có khả năng đi tới Portal, phải khớp filter pattern và danh sách đăng ký IdP. Không áp dụng một redirect URI cố định chung cho nhiều domain/tenant nếu quy trình cần callback riêng.

## 10. Context path, path prefix và trailing slash

Ba loại đường dẫn cần phân biệt:

1. **Public URL** mà browser/IdP nhìn thấy.
2. **Servlet context path** mà ứng dụng được mount vào, nếu có.
3. **Filter process URI** sau khi servlet container và reverse proxy đã xử lý request.

### 10.1. Trường hợp Spring Boot có context path

Giả sử cấu hình:

~~~yaml
server:
  servlet:
    context-path: /portal
~~~

Và ứng dụng được truy cập trực tiếp qua:

~~~text
https://example.test/portal
~~~

Khi dùng template `{baseUrl}/login/oauth2/code/{registrationId}`, redirect URI có thể là:

~~~text
https://example.test/portal/login/oauth2/code/company
~~~

Trong trường hợp đó, filter matcher thường vẫn được cấu hình theo **đường dẫn bên trong Servlet context**:

~~~text
/login/oauth2/code/*
~~~

chứ không phải tự động thêm `/portal` vào `redirectionEndpoint.baseUri`. Public URL bao gồm context path, trong khi matcher được áp dụng trên đường dẫn request mà Servlet security filter nhận sau khi xử lý context.

### 10.2. Trường hợp proxy thêm hoặc cắt prefix

Giả sử browser truy cập:

~~~text
https://apps.example.test/portal/login/oauth2/code/company
~~~

nhưng proxy chuyển đến backend:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

Ứng dụng có thể cần cấu hình header về public prefix (chẳng hạn `X-Forwarded-Prefix`) và hỗ trợ forwarded header phù hợp để `{baseUrl}` phản ánh `/portal`.

Nếu URI công khai đúng nhưng filter không match, cần xem lại path mà backend thực nhận: proxy có **strip prefix** hay không, Spring Boot có context path hay không, và matcher được cấu hình theo đường dẫn nào. **Không sửa bừa cả context path, proxy rule và redirectionEndpoint.baseUri cùng lúc.**

### 10.3. Sai khác thường gặp

| Sai khác | Ví dụ | Hệ quả |
|---|---|---|
| Scheme | `http` so với `https` | IdP có thể từ chối redirect |
| Port | `:8080` so với cổng public mặc định | So khớp redirect có thể thất bại |
| Host | `portal-service` so với `portal.example.test` | IdP hoặc browser không nhận callback đúng |
| Context path | Có `/portal` so với không có | Callback gửi vào URL sai |
| Path | `/login/oauth2/code/company` so với `/auth/callback/company` | Matcher không xử lý nếu cấu hình không khớp |
| Dấu slash cuối | `/company` so với `/company/` | Có thể không khớp URI đăng ký hoặc matcher |
| Viết hoa/thường | `/Callback/company` so với `/callback/company` | Path có thể được xem là khác |

Nên bảo toàn nguyên tắc **đăng ký redirect URI chính xác** và sử dụng **HTTPS** ở các môi trường bên ngoài local.

## 11. Phân biệt redirect_uri với các URL khác sau khi login

Có những URL “redirect” hoàn toàn không phải OAuth redirect URI.

| URL/chuyển hướng | Khi nào xuất hiện? | Có phải OIDC callback URI không? |
|---|---|---|
| `redirect_uri` trong authorization request | Trước khi IdP xác thực người dùng | **Có** |
| `/login/oauth2/code/company` | Khi IdP trả authorization code/state | **Có**, path callback mặc định |
| `/dashboard` sau đăng nhập | Sau khi Spring Security hoàn tất Authentication | **Không** |
| URL ban đầu được lưu bởi RequestCache | Sau login thành công, để đưa người dùng về trang đã yêu cầu | **Không** |
| `post_logout_redirect_uri` trong OIDC RP-Initiated Logout | Khi kết thúc phiên tại IdP | **Không**, đó là redirect sau logout |

Tùy chỉnh `defaultSuccessUrl("/dashboard")` hoặc `successHandler(...)` **không thay đổi OAuth redirect URI**. Nếu login ở IdP lỗi **redirect_uri_mismatch**, sửa success handler không giải quyết nguyên nhân.

Tương tự, cấu hình logout callback hay post-logout redirect không thay đổi `redirectionEndpoint.baseUri` của Authorization Code login.

## 12. Đối chiếu trong môi trường local, staging, production

Một bảng cấu hình giúp tránh triển khai nhầm:

| Môi trường | Public base URL | Redirect URI thực cần đăng ký tại IdP | redirectionEndpoint matcher |
|---|---|---|---|
| Local | `http://localhost:8080` | `http://localhost:8080/login/oauth2/code/company` | `/login/oauth2/code/*` |
| Staging | `https://portal.staging.example.test` | `https://portal.staging.example.test/login/oauth2/code/company` | `/login/oauth2/code/*` |
| Production | `https://portal.example.test` | `https://portal.example.test/login/oauth2/code/company` | `/login/oauth2/code/*` |

Nếu dùng callback tùy chỉnh `/auth/callback/{registrationId}`, cần thay **cột redirect URI và matcher** một cách đồng bộ, rồi đăng ký public URL tương ứng tại IdP.

Mỗi môi trường nên có **client registration/secret/allowed redirects** riêng để tránh vô tình sử dụng secret hoặc callback production từ local. Cấu hình public như issuer/client ID có thể quản lý theo Spring Profiles; secret nên cấp từ secret manager hoặc môi trường chạy.

### 12.1. Ví dụ các profile YAML

~~~yaml
# application.yml: logic chung
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

~~~yaml
# application-prod.yml: hạ tầng HTTPS proxy
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Khi chạy, deployment cung cấp:

~~~text
SPRING_PROFILES_ACTIVE=prod
OIDC_CLIENT_ID=employee-portal-prod
OIDC_CLIENT_SECRET=<secret-trong-kho-bi-mat>
OIDC_ISSUER_URI=https://login.example.test/realms/company
~~~

Không sử dụng ký hiệu `<secret-trong-kho-bi-mat>` như một credential thật; đây chỉ là mô tả nơi cung cấp secret. Chú ý Spring Boot **không tự nạp file .env** chỉ vì file tồn tại; công cụ khởi chạy phải đưa biến vào môi trường Java.

## 13. Kiểm tra callback và redirect URI theo từng bước

Để xác định lỗi nhanh, nên quan sát **request/response thực tế** trong môi trường thử nghiệm đã được kiểm soát. Tránh ghi toàn bộ code/state/token ra log hoặc chia sẻ chúng lên ticket công khai.

### 13.1. Bước 1: tạo authorization request

~~~bash
curl -i "http://localhost:8080/oauth2/authorization/company"
~~~

Khi registration hợp lệ, response thường có dạng:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=employee-portal&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin%2Foauth2%2Fcode%2Fcompany&state=<redacted>
~~~

Đây là **response minh họa**, không phải kết quả đã chạy. Cookie/session header và encoding thực tế tùy cấu hình framework.

Kiểm tra **Location**:

- URL đầu tiên có phải authorization endpoint của **đúng IdP**?
- Tham số `redirect_uri` sau khi URL-decode có đúng **scheme, host, port, path**?
- `client_id` và `scope` có khớp registration?
- Có `state` và các tham số PKCE/OIDC theo cấu hình không?

Với production, nên thực hiện bằng browser developer tools hoặc công cụ được cấp quyền, chỉ lưu **giá trị đã che**. `state`, `nonce`, authorization code và token là dữ liệu nhạy cảm theo phiên.

### 13.2. Bước 2: kiểm tra allowed redirect URI ở IdP

Lấy **giá trị redirect_uri thực tế**, không chỉ xem template. Đối chiếu với đăng ký của đúng client ID và đúng môi trường ở IdP.

Ví dụ:

~~~text
request.redirect_uri:
    https://portal.example.test/login/oauth2/code/company

IdP registered redirect:
    https://portal.example.test/login/oauth2/code/company
~~~

Nếu khác, sửa nguyên nhân tạo giá trị sai hoặc cập nhật đăng ký IdP theo chính sách bảo mật. Không mở wildcard quá rộng để che lỗi hạ tầng.

### 13.3. Bước 3: kiểm tra request callback đến Portal

Sau khi IdP xác thực, browser thường gọi:

~~~http
GET /login/oauth2/code/company?code=<redacted>&state=<redacted> HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=<redacted>
~~~

Xác định:

- Browser có truy cập đúng hostname và path callback không?
- Security Filter Chain nào nhận request đó?
- `redirectionEndpoint.baseUri` có match đường dẫn sau proxy/context path không?
- Session cookie có được browser gửi kèm callback không?

Nếu filter không chạy, sửa matcher/path/proxy. Nếu filter chạy nhưng thiếu authorization request, tiếp tục kiểm tra state/session/repository.

### 13.4. Bước 4: kiểm tra correlation và token exchange

Khi path đã match, Spring cần tìm authorization request gốc, đối chiếu state và tiến hành token exchange. Nếu lỗi xảy ra ở token endpoint, có thể là:

- Client secret hoặc phương thức xác thực client không đúng.
- Authorization code hết hạn hoặc đã được dùng.
- `redirect_uri` trong token exchange không nhất quán với yêu cầu trước đó hoặc với quy định của IdP.
- PKCE code verifier không tương ứng với code challenge.
- IdP từ chối scope/permission theo chính sách.

Không sửa callback matcher nếu đã xác định lỗi thuộc **token endpoint**, **PKCE** hoặc **client authentication**.

## 14. Trường hợp response_mode=form_post và session cookie

Phần lớn ví dụ Authorization Code Flow sử dụng callback qua **GET** với `code` và `state` ở query string. Một số nhà cung cấp hỗ trợ hoặc yêu cầu **OIDC response_mode=form_post**, trong đó callback có thể là HTTP **POST**.

Khi dùng form_post cần kiểm tra thêm:

- Callback filter và cấu hình Security Filter Chain có hỗ trợ phương thức/form data được chọn không?
- **CSRF protection** của ứng dụng có chặn POST callback trước khi OAuth2 Login filter xử lý không?
- Browser có gửi session cookie trong tình huống **cross-site POST** không? `SameSite=Lax` thường không bảo đảm cookie được gửi trong cross-site POST; `SameSite=None; Secure` có thể cần cho một số thiết kế và phải được đánh giá cùng chính sách bảo mật.
- `AuthorizationRequestRepository` còn tìm được state/request ban đầu không?

**Không tùy tiện tắt CSRF cho toàn bộ ứng dụng** chỉ vì một callback POST bị chặn. Cần thiết kế xử lý đúng cho endpoint, phương thức, trạng thái phiên và nhà cung cấp, đồng thời giữ bảo vệ CSRF cho các thao tác nghiệp vụ dùng cookie.

## 15. Nhiều IdP: mỗi registration có redirect URI riêng

Giả sử Portal hỗ trợ hai provider:

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
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${COMPANY_ISSUER_URI}
          partner:
            issuer-uri: ${PARTNER_ISSUER_URI}
~~~

**Đây là cấu hình thay thế cho ví dụ một registration**, không phải đoạn YAML dán nối vào một file đã có key `spring.security.oauth2.client` trùng.

Các callback công khai tương ứng:

~~~text
https://portal.example.test/login/oauth2/code/company
https://portal.example.test/login/oauth2/code/partner
~~~

Một matcher:

~~~text
/login/oauth2/code/*
~~~

có thể xử lý hai đường dẫn. Nhưng **mỗi client ở từng IdP phải đăng ký callback đúng của mình**. Không tự lấy issuer/client_id từ query parameter rồi tạo provider tùy ý để xử lý callback.

Nếu cần callback path khác nhau giữa các provider, hãy thiết kế matcher và ClientRegistration tương ứng. Những nơi có cấu hình dynamic/tenant phải kiểm tra tính tin cậy của issuer và liên kết state với authorization request; không coi giá trị `registrationId` trên URL là một credential.

## 16. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra |
|---|---|---|
| IdP trả **redirect_uri_mismatch** trước khi callback | URI gửi tới IdP không nằm trong danh sách cho phép | Lấy `redirect_uri` đã decode, so sánh với client registration tại IdP |
| IdP redirect về `http://internal-host` | `{baseUrl}` lấy scheme/host nội bộ | Cấu hình proxy và trusted forwarded headers |
| IdP redirect về path đúng nhưng Portal trả 404 | `redirectionEndpoint.baseUri` chưa match path | Kiểm tra matcher và path request backend nhận |
| Callback quay về trang login liên tục | Callback không được filter xử lý, session mất hoặc exception handling redirect lại | Kiểm tra Network redirect chain và filter xử lý |
| **authorization_request_not_found** | Kho authorization request không có request đã khởi tạo | Kiểm tra session cookie, repository và nhiều replica |
| **invalid_state** | State không khớp request đã lưu hoặc callback bị dùng lại | Kiểm tra correlation; không tắt state validation |
| Chạy được local nhưng staging lỗi | Public URL, profile, issuer, callback hoặc proxy khác | Đối chiếu URI sinh thực tế từng môi trường |
| Callback có thêm hoặc mất `/portal` | Context path / reverse proxy strip prefix không thống nhất | Đối chiếu public URL, context path, forwarded prefix |
| Token endpoint trả **invalid_grant** | Code/redirect URI/PKCE có thể không nhất quán | Kiểm tra giao dịch đã lưu, thời hạn code và cấu hình IdP |
| Token endpoint trả **invalid_client** | Secret hoặc client authentication method sai | Kiểm tra confidential client registration/secret runtime |
| Sau login không quay về `/dashboard` | Success handler hoặc RequestCache | Phân biệt post-login redirect với OAuth callback redirect URI |

Không kết luận chỉ từ HTTP status: **401/403/404/302** đều phụ thuộc filter chain, entry point, controller và error handler. Hãy xác định request đã bị từ chối **tại IdP**, **tại callback matcher** hay **sau khi callback filter đã bắt đầu xử lý**.

## 17. Các rủi ro bảo mật khi tùy chỉnh Redirect URI

### 17.1. Không cho client tự chỉ định redirect_uri tùy ý

Ví dụ không an toàn:

~~~text
/oauth2/authorization/company?redirect_uri=https://attacker.example/callback
~~~

Rồi lấy nguyên `redirect_uri` từ query parameter để sửa authorization request. Cách này có nguy cơ redirect đến nơi không được tin cậy, đánh lạc hướng authorization code hoặc tạo lỗ hổng open redirect nếu IdP/client cấu hình sai.

**Redirect URI nên được xác định từ ClientRegistration đáng tin cậy và whitelist của IdP**, không được điều khiển tự do bởi browser.

### 17.2. Không đổi wildcard matcher thành quyết định tin cậy

Pattern `/login/oauth2/code/*` giúp filter tiếp nhận callback theo path; nó **không tự cấp quyền** cho mọi IdP hoặc mọi client ID. Việc tin cậy còn phụ thuộc client registration, state, code exchange và OIDC/token validation.

### 17.3. Giữ state, nonce và PKCE

- State ràng buộc authorization response với request đã bắt đầu.
- Nonce của OIDC giúp ràng buộc ID Token với giao dịch xác thực theo quy tắc OIDC.
- PKCE ràng buộc authorization code với code verifier đã tạo khi bắt đầu giao dịch.

Nếu cần tùy biến resolver hoặc redirect URI, không xóa, ghi đè hay ghi log các dữ liệu này một cách tùy tiện. **Client secret** cũng không thuộc query string của authorization request.

### 17.4. Tránh rò rỉ authorization code trên callback

Authorization code có thời hạn ngắn và thường dùng một lần nhưng vẫn là dữ liệu nhạy cảm. Callback URL có thể bị ghi vào web server access log, browser history, proxy hoặc hệ thống quan sát. Hạn chế log query string nhạy cảm; không đưa code/state/ID Token/access token vào analytics hoặc tài liệu công khai.

### 17.5. HTTPS và host header

Production cần HTTPS và proxy được cấu hình đúng. Không tin host/forwarded header tùy ý từ client ngoài Internet; nếu dùng URL template dựa vào request, cần kiểm soát nguồn host/scheme mà ứng dụng chấp nhận.

## 18. Bài tập áp dụng

Một ứng dụng có cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
~~~

Và:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(endpoint ->
        endpoint.baseUri("/login/oauth2/code/*"))
);
~~~

IdP đăng ký:

~~~text
https://portal.example.test/auth/callback/company
~~~

### Câu hỏi

1. Nếu `{baseUrl}` là `https://portal.example.test`, tham số `redirect_uri` gửi tới IdP là gì?
2. IdP có lý do gì để từ chối redirect URI đó không, giả sử các cấu hình khác đúng?
3. Callback có được `OAuth2LoginAuthenticationFilter` xử lý bằng matcher hiện tại không?
4. Cần sửa dòng nào trong `SecurityFilterChain` để callback đúng?
5. Sau khi sửa path, nếu vẫn báo lỗi `authorization_request_not_found`, nên kiểm tra gì?

### Gợi ý đáp án

1. `https://portal.example.test/auth/callback/company`.
2. URI đã khớp registered redirect tại IdP, nên **không có mismatch chỉ từ redirect URI** trong giả định này. IdP vẫn có thể từ chối vì lý do khác.
3. **Không.** Matcher `/login/oauth2/code/*` không khớp `/auth/callback/company`.
4. Đổi `baseUri("/auth/callback/*")` trong `redirectionEndpoint`.
5. Kiểm tra session cookie, state, `AuthorizationRequestRepository`, cách xử lý proxy và session giữa các node. Không bỏ xác minh state.

## 19. Quy trình đối chiếu ngắn cho người triển khai

Khi triển khai một callback mới, có thể thực hiện theo trình tự:

1. **Chọn URI công khai cuối cùng**, ví dụ `https://portal.example.test/auth/callback/company`.
2. **Đặt ClientRegistration.redirectUri** bằng URI cố định hoặc template tạo ra chính xác URI đó.
3. **Đặt redirectionEndpoint.baseUri** khớp **path bên trong Servlet** (ví dụ `/auth/callback/*`).
4. **Đăng ký URI cuối cùng tại IdP** cho đúng client ID/môi trường.
5. **Kiểm tra URL đã sinh khi bắt đầu login**, đặc biệt tham số `redirect_uri` và state.
6. **Kiểm tra request callback thực tế**: path, method, cookie/session và filter chain.
7. Nếu callback đã được filter bắt, **kiểm tra correlation** trước khi điều tra token endpoint và OIDC validation.

Trình tự này phân định rõ lỗi **URI đăng ký**, lỗi **route/matcher** và lỗi **state/session**. Việc xem HTTP redirect thực tế là bằng chứng tốt hơn suy luận từ một file YAML riêng lẻ.

## 20. Tổng kết

Trong Spring Security OAuth 2.0/OIDC Client trên Servlet, **Redirect URI** là địa chỉ đầy đủ được đưa vào authorization request để Authorization Server đưa trình duyệt trở về. **redirectionEndpoint base URI** là pattern mà `OAuth2LoginAuthenticationFilter` dùng để tiếp nhận callback ở ứng dụng. **Allowed redirect URI** tại IdP là giới hạn mà Authorization Server áp dụng cho client đã đăng ký.

Ba nơi này phải **thống nhất về URL và routing**, nhưng có trách nhiệm khác nhau. Với mặc định, template `{baseUrl}/login/oauth2/code/{registrationId}` phù hợp matcher `/login/oauth2/code/*`. Khi đổi callback path, hãy cập nhật **ClientRegistration.redirectUri**, **redirectionEndpoint.baseUri** và **IdP registration** cùng lúc.

Cuối cùng, callback đến đúng URL **chưa đủ để đăng nhập thành công**: Spring Security còn phải tìm authorization request đã lưu và đối chiếu **state**, bảo toàn PKCE/nonce khi áp dụng, đổi code hợp lệ và xác minh OIDC token. Hiểu rõ sự khác biệt giữa **URL callback**, **filter matcher** và **correlation** là nền tảng để chẩn đoán đúng lỗi OAuth2 Login ở local, staging và production.
