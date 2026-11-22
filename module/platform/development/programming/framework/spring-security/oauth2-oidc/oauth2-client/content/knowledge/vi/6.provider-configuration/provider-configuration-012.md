# 6.12. Tách thông tin bí mật khỏi các thuộc tính công khai

## 1. Vì sao cần tách cấu hình khi tích hợp OAuth 2.0/OIDC?

Một ứng dụng Spring Boot sử dụng **Spring Security OAuth 2.0 Client** thường có hai nhóm dữ liệu khi cấu hình nhà cung cấp danh tính (Identity Provider, **IdP**):

1. **Thông tin mô tả và định tuyến**: issuer URI, authorization endpoint, token endpoint, client ID, scope, redirect URI và các URI khác. Nhiều giá trị có thể công khai hoặc được chia sẻ giữa nhóm phát triển, vận hành và nhà cung cấp.
2. **Thông tin bí mật hoặc credential**: client secret của confidential client, khóa riêng dùng để ký client assertion, mật khẩu keystore, access token, refresh token và những thông tin xác thực khác. Các giá trị này phải được bảo vệ theo quyền sử dụng và vòng đời riêng.

Ví dụ, một **Employee Portal** dùng OIDC để đăng nhập nhân viên tại IdP công ty, sau đó dùng OAuth 2.0 access token gọi Orders API thay mặt nhân viên. Portal cần biết **issuer** và **client ID** để xây dựng authorization request. Nếu Portal là **confidential web client**, nó còn phải bảo vệ **client secret** dùng để xác thực với token endpoint.

Trong thực tế, hai loại dữ liệu này dễ bị trộn vào **application.yml**, dẫn đến việc bí mật bị commit vào Git, xuất hiện trong artifact build, container image, file đính kèm, hệ thống log hoặc tài liệu triển khai. Bài này trình bày cách **phân loại**, **lưu trữ**, **nạp vào Spring Boot** và **xoay vòng** thông tin bí mật mà vẫn giữ cấu hình provider dễ hiểu.

> Phạm vi chính: **Spring Boot 3 / Spring Security 6**, ứng dụng **server-side OAuth 2.0/OIDC Client** dùng Authorization Code Flow. Những URL, ID và chuỗi ví dụ dưới đây không đại diện cho IdP đang hoạt động. Cấu hình thực tế phải khớp khả năng và chính sách của provider.

## 2. “Công khai” không đồng nghĩa “không quan trọng”

Thông tin **công khai** là thông tin mà việc một người khác đọc được thường **không tự cung cấp quyền truy cập**. Ngược lại, **secret** có thể dùng để xác thực, phát hành token hoặc truy cập tài nguyên nếu bị đánh cắp.

Tuy nhiên, thông tin công khai vẫn phải có **tính toàn vẹn**: một issuer URI bị sửa sang IdP giả mạo, một redirect URI bị thay bằng địa chỉ của kẻ tấn công hoặc một audience sai có thể gây lỗi nghiêm trọng. Vì vậy:

- **Bảo mật tính bí mật (confidentiality)** là yêu cầu đặc biệt của secret.
- **Bảo vệ tính toàn vẹn (integrity)** cần áp dụng cho **cả secret và cấu hình công khai**.
- **Giới hạn quyền truy cập vận hành** vẫn hữu ích với một số URL/ID nội bộ, ngay cả khi chúng không phải credential.

Một **client ID** được đưa vào authorization request qua trình duyệt nên **không phải mật khẩu**. Một **client secret** của confidential client thì ngược lại: nó không được xuất hiện trong JavaScript, ứng dụng mobile phân phối cho người dùng hoặc file được công khai.

## 3. Bảng phân loại các thuộc tính OAuth 2.0/OIDC thường gặp

| Thuộc tính / dữ liệu | Thường được coi là | Lý do và cách xử lý |
|---|---|---|
| **issuer-uri**, ví dụ \`https://login.example.test/realms/company\` | Cấu hình mô tả | Dùng để xác định IdP tin cậy; phải bảo vệ tính toàn vẹn |
| **authorization-uri** | Cấu hình mô tả | Endpoint đưa trình duyệt đến để xác thực/ủy quyền |
| **token-uri** | Cấu hình mô tả | Địa chỉ server-to-server đổi code/refresh token; kết nối phải an toàn |
| **jwk-set-uri** | Cấu hình mô tả | URI lấy **khóa công khai** để xác minh chữ ký, không chứa private key |
| **user-info-uri** | Cấu hình mô tả | URL endpoint lấy claim khi được phép; dữ liệu trả về có thể nhạy cảm |
| **client-id** | Định danh công khai | Xác định client registration, không chứng minh client đã được xác thực |
| **redirect-uri** | Cấu hình mô tả, nhạy với tính toàn vẹn | Phải khớp URI đã đăng ký; hạn chế wildcard và sai scheme/host |
| **scope**, ví dụ \`openid profile orders.read\` | Mô tả quyền đề nghị | Việc khai báo scope không đồng nghĩa đã được cấp quyền |
| **client-authentication-method** | Cấu hình mô tả | Cho biết cơ chế client xác thực: \`client_secret_basic\`, \`private_key_jwt\`, ... |
| **client-secret** | **Bí mật** | Credential của confidential client; phải bảo vệ ở runtime |
| **private key** của \`private_key_jwt\` | **Bí mật** | Ai có khóa riêng có thể ký assertion theo danh tính client |
| **keystore password**, khóa TLS riêng, mTLS client private key | **Bí mật** | Credential mật mã; cần kho và quyền truy cập phù hợp |
| **access token** | **Thông tin xác thực nhạy cảm** | Bearer token có thể bị sử dụng lại nếu bị lộ, dù dạng JWT hay opaque |
| **refresh token** | **Bí mật có giá trị cao** | Có thể cấp thêm access token theo chính sách IdP |
| **authorization code**, **PKCE code_verifier** | **Dữ liệu giao dịch nhạy cảm, ngắn hạn** | Không phải cấu hình tĩnh; cần bảo vệ trong luồng authorization |
| **state**, **nonce** | Dữ liệu bảo mật theo từng giao dịch | Phải được tạo/kiểm tra chính xác; không log hoặc cố định thành một chuỗi dùng chung |
| **ID Token** | Dữ liệu danh tính và xác thực nhạy cảm | Có thể chứa thông tin cá nhân; dùng để xác minh OIDC login tại client |
| **username/password người dùng** | **Bí mật** | Ứng dụng dùng OIDC redirect thông thường không được tự thu thập mật khẩu IdP |
| **introspection client secret** | **Bí mật** | Credential của Resource Server khi gọi introspection endpoint |

Danh sách trên giúp phân loại theo **mục đích sử dụng**, không chỉ theo tên. Ví dụ:

- **JWKS** công khai chứa **public key** để xác minh chữ ký; **private key** phát hành chữ ký vẫn là secret của Authorization Server.
- Một JWT access token có payload đọc được không làm token đó trở thành “dữ liệu công khai”. Toàn bộ bearer token phải được bảo vệ.
- Thông tin **client_id** có thể public, nhưng quy trình đăng ký/thay đổi client_id và redirect URI phải được kiểm soát bởi người có quyền.

## 4. Confidential client và public client có cách quản lý secret khác nhau

Không phải OAuth Client nào cũng có khả năng giữ bí mật giống nhau.

### 4.1. Confidential web client

Employee Portal chạy trên server riêng, có thể giữ client secret hoặc private key mà browser không đọc được. IdP có thể đăng ký nó là **confidential client** và yêu cầu xác thực tại token endpoint.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Browser
    participant Portal as Spring Boot Portal
    participant IdP as OIDC Provider

    User->>Browser: Chọn đăng nhập công ty
    Browser->>Portal: GET /oauth2/authorization/company
    Portal-->>Browser: Redirect đến IdP
    Browser->>IdP: Authorization request (client_id, redirect_uri, scope...)
    IdP-->>Browser: Redirect callback với code
    Browser->>Portal: GET /login/oauth2/code/company?code=...
    Portal->>Portal: Lấy client secret từ cấu hình runtime an toàn
    Portal->>IdP: POST /token (code + xác thực confidential client)
    IdP-->>Portal: Token response
    Portal-->>Browser: Session cookie
~~~

Trong ví dụ:

- **client_id** xuất hiện trong yêu cầu trình duyệt được chuyển hướng đến IdP.
- **client_secret** chỉ được server-side Portal dùng để xác thực với token endpoint; browser **không cần biết**.
- **access token/refresh token** được Portal quản lý sau khi nhận, không tự động được trả về giao diện web.

### 4.2. Public client: SPA hoặc ứng dụng mobile

Ứng dụng SPA chạy trong browser và app mobile được phân phối tới thiết bị người dùng **không thể giữ một client secret tĩnh an toàn**. Bất kỳ secret đóng gói trong JavaScript, APK hoặc binary client đều có thể bị trích xuất; đổi tên biến hoặc làm rối mã không biến nó thành bí mật.

Với public client, mô hình thông thường là **Authorization Code Flow với PKCE**, kết hợp chính sách redirect URI, CORS và bảo vệ token phù hợp nền tảng; client **không dùng client secret như bằng chứng bí mật đáng tin cậy**. Nếu dùng mô hình **Backend for Frontend**, backend mới có thể đảm nhận vai trò confidential client, còn browser tương tác với backend bằng session cookie.

**PKCE không có nghĩa client secret là thừa trong mọi kiến trúc.** PKCE bảo vệ authorization code khỏi bị đổi bởi bên khác; còn xác thực confidential client bằng secret hoặc khóa riêng là một lớp chức năng khác. Provider và kiểu client quyết định cấu hình cụ thể.

## 5. Cách tổ chức file cấu hình trong Spring Boot

Mục tiêu của ví dụ là có một cấu hình **đọc được và commit được** trong repository, trong khi credential thực chỉ được cung cấp lúc chạy.

~~~text
employee-portal/
├── src/main/resources/
│   ├── application.yml
│   ├── application-local.yml
│   ├── application-staging.yml
│   └── application-prod.yml
├── .env.example                     # ví dụ tên biến, không có giá trị bí mật
├── .gitignore
└── deployment/
    ├── README.md                    # mô tả các input runtime
    └── ...                          # định nghĩa deploy không chứa secret thật

Runtime:
  ├── Environment variable          # ví dụ được inject từ secret manager
  └── /run/secrets/...               # file secret chỉ có trong container khi chạy
~~~

**Không bắt buộc** mọi dự án phải dùng cả hai cách nạp secret. Có thể chọn **biến môi trường** hoặc **mounted file/config tree** theo nền tảng. Điều quan trọng là secret không được được commit hoặc nhúng vào artifact đóng gói.

### 5.1. application.yml chỉ chứa thông tin chung, không ghi client secret thực

~~~yaml
# src/main/resources/application.yml (có thể commit)
spring:
  application:
    name: employee-portal

  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
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

app:
  orders:
    base-url: ${ORDERS_API_BASE_URL}
~~~

Lưu ý: trong YAML này **không hề có client-secret**. Spring Boot có thể nhận giá trị đó từ một PropertySource ưu tiên cao hơn, ví dụ biến môi trường có tên:

~~~text
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET
~~~

Spring Boot dùng cơ chế binding property với tên biến môi trường phù hợp để ánh xạ về:

~~~text
spring.security.oauth2.client.registration.company.client-secret
~~~

Với **client_secret_basic**, nếu không có credential bắt buộc, trao đổi token tại IdP sẽ thất bại; đây không phải cấu hình đã hoàn chỉnh cho production. Chúng ta sẽ cung cấp secret ở runtime trong các mục sau.

**Vì sao nên đặt client ID và issuer vào biến ngay cả khi chúng không phải secret?** Chúng thường khác giữa local, staging và production. Việc dùng placeholder tránh nhân bản source code. Nếu giá trị thật của chúng không nhạy cảm theo chính sách tổ chức, cũng có thể viết trực tiếp vào file profile.

### 5.2. Phân chia profile theo môi trường

~~~yaml
# application-local.yml
server:
  port: 8080

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

~~~yaml
# application-staging.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

~~~yaml
# application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Tùy môi trường mà có thể có issuer, redirect URI, hostname và policy cookie khác nhau. Cần bảo đảm **active profile** thực sự được chọn bởi deployment, ví dụ \`SPRING_PROFILES_ACTIVE=prod\`. Không đặt secret thật trong file profile chỉ vì file đó “chỉ dùng ở production”.

Thứ tự ưu tiên Spring Boot có thể khiến môi trường hoặc command-line argument ghi đè thuộc tính trong YAML. Khi điều tra cấu hình, cần hiểu **nguồn giá trị cuối cùng** nhưng không xuất nội dung secret ra log để “kiểm tra cho nhanh”.

## 6. Phương án A: cung cấp client secret qua biến môi trường

### 6.1. Cấu hình trong môi trường runtime

Ví dụ những biến Portal cần khi triển khai:

~~~text
SPRING_PROFILES_ACTIVE=prod
OIDC_ISSUER_URI=https://login.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-prod
ORDERS_API_BASE_URL=https://orders.example.test
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET=<gia-tri-do-secret-manager-cap>
~~~

Ở đây bốn giá trị đầu là cấu hình vận hành; biến cuối là **secret**. Tất cả đều có thể được inject vào tiến trình Java theo cơ chế của nền tảng, nhưng bí mật phải có nguồn cấp và quyền đọc riêng.

**Ví dụ PowerShell cho local (placeholder, không phải secret thật):**

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:OIDC_ISSUER_URI = 'https://login.dev.example.test/realms/company'
$env:OIDC_CLIENT_ID = 'employee-portal-local'
$env:ORDERS_API_BASE_URL = 'http://localhost:8081'

# Nhận giá trị bí mật qua công cụ được tổ chức cho phép.
$env:SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET = '<local-secret-placeholder>'

./gradlew.bat bootRun
~~~

Trong ví dụ này, shell command chứa **placeholder**; không ghi bí mật thật trực tiếp vào tài liệu, CI output hoặc hướng dẫn được chia sẻ. Trong thực tế, lệnh nhập secret thủ công có thể bị lưu vào shell history hoặc được công cụ giám sát ghi lại; nếu nền tảng cung cấp cơ chế inject secret an toàn, hãy ưu tiên cơ chế đó.

Biến môi trường là **một kênh truyền giá trị vào tiến trình**, không mặc nhiên là kho bí mật: process diagnostics, quyền quản trị host, bản ghi cấu hình CI/CD và crash dump vẫn có thể làm lộ giá trị. Vì vậy phải bảo vệ cả **nguồn secret**, **quyền truy cập tiến trình** và **đường đi triển khai**.

### 6.2. Kubernetes: ConfigMap cho dữ liệu không bí mật, Secret cho credential

Ví dụ minh họa cách phân luồng cấu hình vào container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: employee-portal
spec:
  replicas: 2
  selector:
    matchLabels:
      app: employee-portal
  template:
    metadata:
      labels:
        app: employee-portal
    spec:
      containers:
        - name: portal
          image: registry.example.test/employee-portal:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: OIDC_ISSUER_URI
              valueFrom:
                configMapKeyRef:
                  name: portal-public-config
                  key: oidcIssuerUri
            - name: OIDC_CLIENT_ID
              valueFrom:
                configMapKeyRef:
                  name: portal-public-config
                  key: oidcClientId
            - name: ORDERS_API_BASE_URL
              valueFrom:
                configMapKeyRef:
                  name: portal-public-config
                  key: ordersApiBaseUrl
            - name: SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET
              valueFrom:
                secretKeyRef:
                  name: portal-oidc-credential
                  key: client-secret
~~~

Ở đây \`portal-public-config\` là **ConfigMap**, còn \`portal-oidc-credential\` là **Kubernetes Secret** do quy trình an toàn tạo và quản lý bên ngoài manifest này.

**Kubernetes Secret không mặc nhiên là một vault hoàn chỉnh.** Dữ liệu trong Secret cần quyền RBAC phù hợp, bảo vệ etcd/encryption at rest nếu nền tảng yêu cầu, giới hạn ai có thể xem mô tả pod/log và audit truy cập. Việc mã hóa Base64 trong manifest không phải mã hóa bí mật. Không commit bản Secret chứa dữ liệu nhạy cảm ở dạng Base64 với suy nghĩ rằng nó đã được bảo vệ.

Với kiểu truyền qua **environment variables**, cập nhật Kubernetes Secret thường **không thay đổi giá trị đã được inject vào process đang chạy**; cần chiến lược rolling restart/redeploy phù hợp để phiên bản ứng dụng mới đọc credential mới.

## 7. Phương án B: mounted secret file và Spring Boot config tree

Đối với nền tảng hỗ trợ mount file bí mật, Spring Boot có thể đọc secret từ **config tree**. Khi đó, container nhận file secret ở thời điểm chạy; file không nằm trong repository hoặc JAR.

Giả sử hạ tầng tạo một file:

~~~text
/run/secrets/
└── spring.security.oauth2.client.registration.company.client-secret
~~~

Nội dung file duy nhất đó là **giá trị client secret**, không phải YAML và không bao gồm tên property. Chọn quyền đọc file sao cho chỉ tiến trình ứng dụng và những thành phần vận hành được phép mới có thể truy cập.

Trong **application-prod.yml** có thể khai báo:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Spring Boot sẽ nhập các file bên dưới thư mục này thành configuration properties. Tên file trở thành tên thuộc tính tương ứng, vì vậy file trong ví dụ cung cấp giá trị cho:

~~~text
spring.security.oauth2.client.registration.company.client-secret
~~~

**Đây là phương án thay thế cho việc inject secret bằng biến môi trường** ở mục trước; chỉ chọn một nguồn được quản lý rõ ràng để tránh mơ hồ về ưu tiên. Với file import bắt buộc, ứng dụng không nên khởi động thành công trong production khi thư mục secret không được mount.

Trong một số môi trường, config tree còn phù hợp với dữ liệu dạng PEM/certificate và password. Tuy nhiên, cần xem xét API nào nhận **giá trị** và API nào nhận **đường dẫn file**; không phải property nào cũng đọc nội dung file theo cùng một cách.

**Bảo vệ file sau khi mount:** giới hạn quyền filesystem, không cho web server phục vụ thư mục secret, không copy file vào artifact build, không backup/đồng bộ sang nơi không được cấp phép. Nếu file secret được cập nhật khi ứng dụng đang chạy, đừng giả định Spring Boot tự động refresh mọi bean OAuth2 Client; cơ chế reload/restart phải được thiết kế cụ thể.

## 8. Provider metadata công khai nhưng phải được xác minh

OpenID Connect cho phép Client lấy metadata cấu hình provider qua discovery. Ví dụ một issuer:

~~~text
https://login.example.test/realms/company
~~~

Metadata có thể cung cấp:

~~~json
{
  "issuer": "https://login.example.test/realms/company",
  "authorization_endpoint": "https://login.example.test/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.test/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.test/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://login.example.test/realms/company/protocol/openid-connect/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"]
}
~~~

Các URL trong ví dụ là cấu hình mô tả. Chúng **không phải credential**, nhưng phải đến từ IdP tin cậy và được truy cập qua TLS, với kiểm tra issuer theo yêu cầu OIDC.

Ở Spring Security, có thể cấu hình ngắn gọn:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Nếu provider tuân thủ discovery, Spring có thể suy ra các endpoint cần thiết. Việc chỉ định \`issuer-uri\` **không cấp quyền** cho bất cứ client nào và cũng **không chứa client secret**. Metadata discovery không được dùng như nguồn cấp secret.

Nếu provider không hỗ trợ discovery tương thích, có thể cấu hình riêng \`authorization-uri\`, \`token-uri\`, \`jwk-set-uri\`, \`user-info-uri\` và \`user-name-attribute\` khi cần. Dù cấu hình thủ công, các endpoint vẫn là **đối tượng cần xác minh tính toàn vẹn**; không lấy URL tùy ý từ request của người dùng rồi coi là IdP tin cậy.

### Khác biệt giữa public key và private key

- **Public key** trong JWKS dùng để xác minh chữ ký JWT; tài liệu công khai JWKS **không tiết lộ private key**.
- **Private key** dùng để ký token hoặc ký client assertion phải được bảo vệ bằng secret manager, HSM hoặc keystore có quyền kiểm soát thích hợp.
- **kid** là chỉ dấu chọn khóa từ tập khóa tin cậy; không tự chứng minh khóa trong token có thể tin cậy.

## 9. Cấu hình Spring Security dùng chung cho các môi trường

Lớp security chỉ nên xác định **quy tắc ứng dụng**, không chứa trực tiếp endpoint IdP và secret của từng môi trường.

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
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Với registration ID **company**, Spring Security mặc định cung cấp:

~~~text
Login URL:     /oauth2/authorization/company
Callback URL:  /login/oauth2/code/company
~~~

Registration được nạp từ property sources, nên \`SecurityConfig\` không cần biết client secret nằm ở environment variable hay mounted file. Không tạo các nhánh như “nếu local thì dùng secret hardcoded A, nếu production thì dùng secret hardcoded B” trong Java.

Khi cần gọi API, Client sử dụng **OAuth2AuthorizedClient** của principal hiện tại, không đọc secret để tự dựng token hoặc gửi client secret trong request đến Resource Server:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class OrdersController {

    private final RestClient ordersApi =
        RestClient.create("https://orders.example.test");

    @GetMapping("/bff/orders")
    String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken = authorizedClient.getAccessToken().getTokenValue();
        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

Để làm ứng dụng theo môi trường hoàn chỉnh, URL **orders.example.test** trong ví dụ này cũng nên được bind từ một thuộc tính công khai như \`app.orders.base-url\` thay vì ghi cố định trong Java. Token ở ví dụ là **access token**, không phải client secret; cả hai đều nhạy cảm nhưng có **mục đích khác nhau**.

## 10. Một số phương thức xác thực client và secret tương ứng

Không phải provider nào cũng sử dụng \`client_secret_basic\`. Ví dụ:

| Phương thức tại token endpoint | Credential cần bảo vệ ở confidential client | Gợi ý vận hành |
|---|---|---|
| **client_secret_basic** | Client secret | Gửi theo HTTP Basic khi trao đổi token qua TLS |
| **client_secret_post** | Client secret | Credential nằm trong POST body; chỉ dùng khi phù hợp chính sách IdP |
| **client_secret_jwt** | Shared secret dùng ký JWT assertion | Bảo vệ secret và đảm bảo algorithm/timing đúng thỏa thuận |
| **private_key_jwt** | Private signing key | Bảo vệ khóa riêng; quản lý JWKS/public key và rotation |
| **tls_client_auth / self_signed_tls_client_auth** | Private key và certificate tương ứng | Quản lý certificate, TLS binding, keystore và rotation |
| **none** (public client) | Không có shared static client secret | Dùng biện pháp phù hợp public client, điển hình Authorization Code + PKCE |

Cách cấu hình Spring Security phụ thuộc phương thức và provider. Không đổi \`client-authentication-method\` sang một giá trị khác chỉ vì muốn “giấu secret”: ví dụ \`private_key_jwt\` đòi hỏi cơ chế ký client assertion và quản lý private key thật, chứ không thể chỉ thay một dòng YAML.

**Client secret là credential của ứng dụng**, không phải mật khẩu người dùng và không phải OAuth access token. Sử dụng sai loại credential có thể làm hỏng luồng hoặc mở rộng rủi ro khi lộ dữ liệu.

## 11. Phân tách secret với dữ liệu phát sinh trong quá trình đăng nhập

Trong OIDC Authorization Code Flow, có một số giá trị không tồn tại trong file cấu hình trước khi người dùng đăng nhập:

~~~mermaid
flowchart TD
    A["Cấu hình tĩnh từ repository: issuer, client ID, redirect URI, scope"] --> C["Spring Security OAuth2 Client"]
    B["Nguồn bí mật runtime: client secret / private key"] --> C
    C --> D["Authorization request: state, nonce, PKCE"]
    D --> E["Authorization Server"]
    E --> F["Authorization code ngắn hạn"]
    F --> C
    C --> G["Token response: ID token, access token, refresh token nếu có"]
    G --> H["SecurityContext và OAuth2AuthorizedClient"]
    H --> I["Gọi Resource Server với access token"]
~~~

Sự phân loại theo vòng đời:

- **Client secret hoặc private key**: credential đăng ký của ứng dụng, thường được cấp và xoay theo chu kỳ riêng.
- **state, nonce, PKCE code_verifier**: dữ liệu gắn với một lần authorization; phải tạo riêng cho giao dịch và xác minh đúng, không hardcode một chuỗi toàn cục trong YAML.
- **authorization code**: giá trị ngắn hạn, dùng một lần trong luồng đổi token.
- **access token, refresh token và ID Token**: dữ liệu phát hành sau khi authorization/login, được giữ trong cấu trúc lưu trữ an toàn tương ứng với phiên hoặc authorized client; **không đưa vào application.yml**.

Với ứng dụng MVC/BFF, browser thường chỉ giữ **session cookie** của Portal. Token được quản lý phía server. Nếu chạy nhiều replica, hệ thống cần cơ chế lưu session/authorized client thích hợp; không coi việc lưu client secret trong vault là đã giải quyết việc bảo vệ refresh token hoặc session.

## 12. Giữ bí mật khỏi Git, artifact, container image và tài liệu

### 12.1. Mẫu .env.example

Một tệp mẫu nên mô tả **tên biến** nhưng không đi kèm credential thật:

~~~dotenv
SPRING_PROFILES_ACTIVE=local
OIDC_ISSUER_URI=https://login.dev.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-local
ORDERS_API_BASE_URL=http://localhost:8081
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET=REPLACE_WITH_LOCAL_SECRET
~~~

\`.env.example\` có thể commit, trong khi các file có secret thật như \`.env\`, \`.env.local\` cần được ignore hoặc quản lý ngoài repository theo quy định.

~~~gitignore
.env
.env.*
!.env.example
*.p12
*.pfx
*.key
~~~

Đây là ví dụ, cần chỉnh theo tập tin thực của dự án; việc ignore rộng các đuôi **.key** có thể không phù hợp nếu repository cũng có khóa công khai hoặc fixture kiểm thử được phép. **.gitignore không tự xóa những secret đã từng được commit** và không giúp bảo vệ secret trong commit history.

### 12.2. Spring Boot không tự động đọc .env

Việc có \`.env.local\` nằm ở thư mục dự án **không đồng nghĩa Spring Boot sẽ tự nạp nó**. Phải có IDE, shell script, container runtime hoặc công cụ nạp biến môi trường đã được cấu hình rõ ràng. Không nên dựa trên giả định rằng một file \`.env\` âm thầm được framework nhận biết.

### 12.3. Container image phải là artifact chung

Container image nên chứa **mã ứng dụng và cấu hình phi bí mật**, còn secret được inject lúc deploy:

~~~text
Build:
    source code + application.yml
       -> JAR / container image

Deploy:
    image + profile + provider metadata + secret nguồn an toàn
       -> tiến trình Spring Boot
~~~

Không sử dụng Dockerfile \`ENV CLIENT_SECRET=...\`, build argument chứa secret, hoặc \`COPY .env\` với secret vào image. Những giá trị này có thể bị lộ qua layer history, registry, image scan hoặc bản sao image. Nếu build cần credential riêng, sử dụng cơ chế secret dành cho build với phạm vi truy cập và thời hạn phù hợp; credential của OAuth Client runtime không cần đưa vào giai đoạn build.

## 13. Log, Actuator và các kênh vô tình làm lộ bí mật

Ngay cả khi secret không xuất hiện trong Git, các kênh sau có thể làm lộ credential:

- Log HTTP request/response chứa header **Authorization**, cookie, authorization code hoặc token endpoint response.
- **Spring Boot Actuator**, dump cấu hình, error page, heap dump hoặc endpoint chẩn đoán mở quyền không phù hợp.
- Trace/APM, reverse proxy access log, CI/CD job log, command-line history và screenshot hỗ trợ sự cố.
- Developer tools hoặc telemetry frontend nếu backend trả token về JavaScript.
- Thông báo lỗi bao gồm secret hoặc header nhạy cảm.

Ví dụ cấu hình production giới hạn endpoint Actuator được xuất ra web:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Việc giảm endpoint được expose **không thay thế** xác thực/phân quyền và cấu hình mạng cho Actuator. Nếu tổ chức cần **/actuator/env** hoặc **/actuator/configprops** để vận hành, phải hạn chế truy cập và thiết lập **sanitization/show-values** phù hợp với phiên bản Spring Boot; không coi việc framework thường che một số trường theo tên là hàng rào bảo mật duy nhất.

Khi cần xác nhận Spring đã nhận đúng giá trị:

**Nên:** log tên active profile, issuer/host đã được phê duyệt, registration ID, trạng thái “credential configured” và kết quả kết nối có che dữ liệu nhạy cảm.

**Không nên:** log \`clientSecret\`, \`OAuth2AccessToken.getTokenValue()\`, refresh token, token endpoint response, header Authorization hoặc toàn bộ \`Environment\` object.

Lưu ý issuer URI thường là cấu hình công khai nhưng vẫn có thể tiết lộ thông tin về hệ thống nội bộ. Chỉ log đủ thông tin phục vụ vận hành và tuân thủ chính sách tổ chức.

## 14. Bảo vệ redirect URI, proxy và các giá trị được coi là công khai

Một config **redirect-uri** hoặc **issuer-uri** không phải secret, nhưng nếu bị thao túng có thể phá vỡ liên kết tin cậy của luồng đăng nhập.

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

Khi Portal triển khai sau proxy:

~~~text
Browser
  -> https://portal.example.test
  -> Trusted TLS reverse proxy
  -> http://portal-service:8080
  -> Spring Boot
~~~

Portal phải tạo callback công khai:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Không phải callback nội bộ:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

Để xử lý đúng, cần cấu hình proxy/forwarded headers và đăng ký redirect URI chính xác ở IdP. **Chỉ tin cậy X-Forwarded-* hoặc Forwarded từ proxy đã lọc và kiểm soát header do client bên ngoài gửi đến.** Không sử dụng redirect URI wildcard hoặc giá trị redirect lấy tùy ý từ query parameter.

Tương tự, **issuer-uri** phải xác định một IdP tin cậy, không chọn tùy ý từ người gửi request. Nếu ứng dụng hỗ trợ nhiều issuer/tenant, cần cơ chế ánh xạ và xác minh rõ ràng.

## 15. Secret rotation: thay đổi credential mà không sửa mã nguồn

Tách secret khỏi file YAML đem lại lợi ích quan trọng: có thể xoay credential độc lập với thay đổi business logic.

Giả sử client secret hiện tại là **S1** và cần thay bằng **S2**. Quy trình điển hình:

1. **Chuẩn bị tại IdP**: xác định provider có hỗ trợ giai đoạn cùng tồn tại hai secret, phiên bản credential hay phải thay ngay. Chuẩn bị client secret mới theo cách IdP cho phép.
2. **Đưa S2 vào secret manager**: giới hạn ai được đọc/ghi; không ghi S2 vào ticket, chat, Git hoặc output pipeline.
3. **Cập nhật deployment**: ứng dụng mới nhận S2 qua environment injection hoặc mounted secret; rolling restart khi cần. Giữ cơ chế rollback theo khả năng của provider và chính sách bảo mật.
4. **Quan sát kết quả**: kiểm tra luồng đổi authorization code, refresh token và các lỗi **invalid_client**; chỉ log trạng thái, không log credential.
5. **Thu hồi S1**: khi các instance cần thiết đã chuyển sang S2 và điều kiện vận hành được thỏa mãn, vô hiệu credential cũ.
6. **Ghi nhận vận hành**: ngày rotation, hệ thống liên quan, người phụ trách và kết quả kiểm tra; không lưu giá trị secret trong biên bản.

Một số Authorization Server **không cho hai client secret cùng hiệu lực**. Khi đó rotation cần kế hoạch triển khai đồng bộ và có thể có khoảng gián đoạn ngắn. Không mặc định secret mới sẽ được Spring Security tự nạp vào bean đang chạy mà không restart hoặc refresh cấu hình đã được hỗ trợ.

Nếu dùng **private_key_jwt**, luồng rotation thay bằng quản lý cặp khóa và public key/JWKS tương ứng. Nếu dùng mTLS client authentication, rotation liên quan đến certificate và private key. Chỉ đổi một biến môi trường sẽ không đủ nếu IdP chưa tin credential mới.

## 16. Nếu bí mật đã lộ thì xử lý thế nào?

Khi phát hiện một client secret hoặc private key từng xuất hiện trong commit, log, artifact, ticket hay một nguồn không được phép, không nên chỉ xóa dòng đó khỏi file hiện tại và kết luận sự cố đã kết thúc.

Các bước kỹ thuật cần phối hợp với chủ sở hữu IdP và vận hành:

1. **Xác định credential đã lộ và môi trường bị ảnh hưởng**; giới hạn việc sao chép hoặc phát tán thêm giá trị bí mật.
2. **Thu hồi/rotate credential tại provider** và cập nhật bí mật của các instance hợp lệ.
3. **Kiểm tra vị trí phát tán** như lịch sử Git, registry image, CI logs và artifact; xử lý/xóa theo chính sách tổ chức. Lịch sử Git đã được chia sẻ cần quy trình thống nhất để tránh mất dữ liệu hoặc phát tán thêm.
4. **Đánh giá tác động**: các lần đổi token bất thường, phiên ủy quyền, token đang còn hiệu lực, quyền và phạm vi client.
5. **Cải thiện cơ chế phòng ngừa**: secret scanning, kiểm soát truy cập, môi trường tách biệt, hạn chế logging và quy trình rotation.

**Việc che secret trong file mới không vô hiệu hóa bản đã lộ.** Cần xử lý tại nguồn có quyền cấp/chấp nhận credential, nghĩa là IdP hoặc thành phần xác thực tương ứng.

## 17. Cấu hình kiểm thử và development mà vẫn giữ nguyên nguyên tắc

Khi viết test cho OAuth2 Client, có thể dùng **test client registration**, IdP giả lập hoặc các thành phần test hỗ trợ \`oidcLogin()\`. Không cần dùng confidential client secret của production cho test.

Ví dụ file **application-test.yml**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-test
            client-secret: test-only-placeholder
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            authorization-uri: http://localhost:9999/authorize
            token-uri: http://localhost:9999/token
            jwk-set-uri: http://localhost:9999/jwks
            user-info-uri: http://localhost:9999/userinfo
            user-name-attribute: sub
~~~

Trong ví dụ này, **test-only-placeholder** không phải credential của IdP thật, chỉ phục vụ một provider giả lập do test kiểm soát. Không sử dụng HTTP cho token endpoint trong môi trường ngoài test cô lập. Nếu dùng thực tế **issuer-uri**, việc discovery có thể cần server giả lập đang chạy khi khởi động Spring context.

Một lớp test có thể sử dụng **Spring Security Test** để mô phỏng OIDC principal mà không cần đăng nhập qua IdP thật. Test end-to-end vẫn nên chạy với client registration chuyên biệt và credential do môi trường kiểm thử cung cấp.

Quy trình phát triển an toàn cần phân biệt:

- **Test fixture không có giá trị xác thực thật** có thể được commit nếu không chứa thông tin nhạy cảm.
- **Secret thật dùng cho development** vẫn phải được bảo vệ và có thể bị thu hồi/rotate.
- **Không dùng client secret production** để test hoặc gỡ lỗi trên laptop.

## 18. Checklist khi triển khai cấu hình provider

Trước khi đưa Employee Portal sang staging/production, có thể dùng bảng sau để trao đổi giữa nhóm ứng dụng, bảo mật và vận hành:

| Câu hỏi | Điều kiện mong đợi |
|---|---|
| Repo có chứa **client-secret** hoặc private key thật không? | Không; chỉ có tên property/placeholder hoặc fixture giả |
| Provider có phân biệt client ID và secret? | Có; client ID dùng để định danh, secret dùng để xác thực confidential client |
| Secret đi vào runtime bằng đường nào? | Secret manager, variable injection hoặc mounted file có quyền phù hợp |
| Mỗi môi trường có client credential riêng không? | Nên có để cô lập quyền, callback và rotation |
| Issuer, endpoint và redirect URI có đúng môi trường không? | Khớp IdP đã tin cậy và callback thực tế |
| Có cấu hình client authentication method đúng không? | Phù hợp chính sách provider và loại client |
| Secret có thể lộ qua build, image, CI, log, Actuator không? | Đã kiểm soát các kênh quan sát/cấu hình |
| Session/token và client secret có được lưu riêng theo vòng đời không? | Có, vì authorized client/token là dữ liệu phát sinh |
| Khi secret rotate, instance cũ xử lý thế nào? | Có kế hoạch deploy, rollback, thu hồi và kiểm tra |
| Khi credential bị lộ, xử lý ở đâu? | Thu hồi/rotate tại IdP, kiểm tra phạm vi ảnh hưởng và nguồn rò rỉ |

Đây là checklist **vận hành khi triển khai**, không thay thế các test ứng dụng hoặc chính sách bảo mật của tổ chức.

## 19. Tình huống thực hành

Một lập trình viên chuẩn bị cấu hình Portal:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal-prod
            client-secret: s3cr3t-production-value
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://login.example.test/realms/company
~~~

Hãy xác định điều cần thay đổi trước khi commit:

1. **client-id** có phải secret không? Nếu không, tại sao vẫn phải kiểm soát việc sửa giá trị?
2. **issuer-uri** có phải secret không? Điều gì xảy ra nếu nó bị sửa sang một issuer khác?
3. **client-secret** cần chuyển về nguồn cấu hình nào?
4. Nếu giá trị **s3cr3t-production-value** đã xuất hiện trong lịch sử Git, chỉ thay bằng placeholder có đủ không?
5. Khi chạy trên Kubernetes, nên tách ConfigMap và Secret theo trách nhiệm thế nào?

Một hướng sửa cho phần đã được commit:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: ${OIDC_CLIENT_ID}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Sau đó deployment cung cấp **SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET** từ kho bí mật. **Nếu secret ví dụ đã từng là credential thật và bị commit, bắt buộc xử lý rotation/thu hồi theo phạm vi ảnh hưởng**; việc xóa trong file mới chỉ ngăn lặp lại cùng một hình thức lộ dữ liệu.

## 20. Kết luận thực hành

Trong **Spring Security OAuth 2.0/OIDC Client**, cấu hình provider thường có những giá trị công khai như **issuer URI, endpoint, client ID, redirect URI và scope**, song cũng có **credential bí mật** như **client secret hoặc private key**. Chúng có tác dụng khác nhau và phải có vòng đời quản lý khác nhau.

Thiết kế khuyến nghị là: **mã nguồn và YAML chỉ chứa cấu trúc, tên property cùng cấu hình không nhạy cảm; secret được quản lý ngoài repository và cấp vào tiến trình Spring Boot qua kênh runtime được kiểm soát.** Trong khi đó, **access token, refresh token, ID Token và dữ liệu state/nonce/PKCE** được quản lý theo phiên hoặc giao dịch, không trở thành cấu hình tĩnh.

Cuối cùng, phân loại “public” không có nghĩa có thể tin tưởng tùy ý. **Issuer, redirect URI, JWKS source, audience và client authentication method** cần được cấu hình và xác minh nhất quán với IdP. Khi vừa giữ bí mật credential, vừa giữ tính toàn vẹn cấu hình provider, ứng dụng có thể triển khai ở nhiều môi trường mà không phải sửa mã để đổi secret và có cơ chế rotation/ứng phó sự cố rõ ràng.
