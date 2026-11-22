# 4.5. Cấu trúc dự án, profile và cấu hình theo môi trường

## 1. Bài toán khi đưa OAuth 2.0/OIDC Client vào dự án thực tế

Một ứng dụng Spring Boot dùng **Spring Security OAuth 2.0 Client** thường hoạt động ở nhiều môi trường:

- **Local**: lập trình viên chạy ứng dụng trên máy, kết nối với một nhà cung cấp danh tính (Identity Provider, **IdP**) dành cho phát triển.
- **Development/Integration**: nhiều dịch vụ chạy cùng nhau để kiểm thử luồng đăng nhập và gọi API.
- **Staging**: môi trường gần giống production để kiểm thử trước khi phát hành.
- **Production**: người dùng thật đăng nhập qua OIDC, ứng dụng sử dụng OAuth 2.0 access token để gọi các API được bảo vệ.

Logic đăng nhập có thể giống nhau trên cả bốn môi trường, nhưng các giá trị cấu hình lại khác: **issuer URI**, **client ID**, **client secret**, **redirect URI**, địa chỉ API, HTTPS, cookie, proxy, logging và cơ chế lưu session.

Nếu viết cứng mọi giá trị vào mã Java hoặc trộn cấu hình môi trường trong một lớp security, việc triển khai trở nên khó kiểm soát. Bài học này xây dựng cách **tổ chức dự án**, **dùng Spring Profile** và **nạp cấu hình theo môi trường**, đồng thời giữ bí mật OAuth Client và bảo đảm callback OIDC hoạt động đúng.

> Ví dụ minh họa dùng **Java 17+, Spring Boot 3 và Spring Security 6**, ứng dụng web phía server (MVC/BFF) tên **Employee Portal**, registration ID là **company**, và một **Orders API** mà Portal gọi thay mặt người dùng. Các hostname, client ID, secret và endpoint chỉ là giá trị ví dụ, không phải dịch vụ đang hoạt động.

## 2. Ba nguyên tắc thiết kế

**Một mã ứng dụng, nhiều bộ cấu hình.** Cùng một artifact có thể chạy local, staging và production. Sự khác nhau chủ yếu nằm ở property, biến môi trường, secret và hạ tầng; không cần sao chép source code cho từng môi trường.

**Tách trách nhiệm của các lớp.** Security configuration quyết định yêu cầu nào phải xác thực và sử dụng OIDC login. OAuth2 Client configuration mô tả Authorization Server/client registration. Controller và service chỉ xử lý nghiệp vụ; HTTP client gọi API bằng access token của người dùng.

**Không lưu bí mật vào Git.** Client secret, refresh token, khóa riêng, mật khẩu và credential introspection không nằm trong file cấu hình được commit. Các file YAML trong repository chỉ chứa cấu trúc, tên biến, giá trị phi nhạy cảm và cấu hình mặc định an toàn.

Các nguyên tắc này đặc biệt quan trọng với OAuth 2.0/OIDC vì một cấu hình sai có thể khiến callback lỗi, token gửi sai nơi nhận hoặc credential bị lộ.

## 3. Cấu trúc thư mục đề xuất

Một ứng dụng Spring Boot đóng vai trò **OIDC Relying Party + OAuth 2.0 Client** có thể tổ chức:

~~~text
employee-portal/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── .gitignore
├── .env.example                    # tên biến/giá trị mẫu, không chứa secret thật
├── README.md
├── src/
│   ├── main/
│   │   ├── java/com/example/portal/
│   │   │   ├── PortalApplication.java
│   │   │   ├── config/
│   │   │   │   ├── SecurityConfig.java
│   │   │   │   └── OrdersApiProperties.java
│   │   │   ├── web/
│   │   │   │   ├── HomeController.java
│   │   │   │   └── OrdersController.java
│   │   │   ├── service/
│   │   │   │   └── OrdersService.java
│   │   │   └── client/
│   │   │       └── OrdersApiClient.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       ├── application-staging.yml
│   │       ├── application-prod.yml
│   │       ├── static/
│   │       └── templates/
│   └── test/
│       ├── java/com/example/portal/
│       │   └── web/
│       │       └── HomeControllerTest.java
│       └── resources/
│           └── application-test.yml
└── deployment/
    ├── README.md                   # hướng dẫn biến môi trường và redirect URI
    └── ...                         # manifest hoặc tài liệu deploy theo công nghệ sử dụng
~~~

Đây là **một cấu trúc gợi ý**, không phải cấu trúc bắt buộc của Spring Boot. Khi dự án nhỏ, có thể gộp một số lớp; khi dự án lớn, có thể tổ chức theo feature thay vì theo tầng kỹ thuật. Điều cần giữ là các trách nhiệm được nhận diện rõ:

| Vị trí | Trách nhiệm |
|---|---|
| **PortalApplication** | Khởi tạo Spring Boot, quét bean và cấu hình properties |
| **config/SecurityConfig** | **SecurityFilterChain**, **oauth2Login()**, **oauth2Client()**, chính sách URL |
| **config/OrdersApiProperties** | Ánh xạ property riêng của ứng dụng thành kiểu Java |
| **client/OrdersApiClient** | Gọi Orders API qua HTTP, sử dụng access token đã cấp |
| **service/OrdersService** | Điều phối nghiệp vụ; không chứa bí mật cấu hình |
| **web/** | Endpoint trình bày danh tính OIDC, gọi service hoặc trả dữ liệu BFF |
| **application.yml** | Cấu hình chung không phụ thuộc môi trường |
| **application-{profile}.yml** | Các phần ghi đè cho môi trường tương ứng |
| **test/** | Kiểm tra endpoint và bảo mật với cấu hình kiểm thử riêng |
| **deployment/** | Mô tả đầu vào runtime, secret, callback URI và hạ tầng |

**Không tạo một bản sao của SecurityConfig cho mỗi môi trường** nếu chỉ có issuer, client ID hoặc hostname khác nhau; những khác biệt đó phù hợp với configuration properties hơn.

## 4. Dependency tối thiểu cho Portal

Ví dụ Gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0' // chọn phiên bản được dự án hỗ trợ
    id 'io.spring.dependency-management' version '1.1.6'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter-oauth2-client** cung cấp phần cần thiết cho OAuth 2.0 Client và OIDC login. Khi Portal là một ứng dụng dùng session phía server, không cần tự thêm OAuth2 Resource Server starter trừ khi **chính Portal cũng cần nhận và xác minh bearer access token ở endpoint của nó**. Resource Server bảo vệ Orders API thường là một ứng dụng khác.

Spring Boot quản lý phiên bản tương thích của phần lớn dependency thông qua BOM. Với dự án thực tế, dùng phiên bản Boot được tổ chức lựa chọn và cập nhật bảo mật theo quy trình; số phiên bản trong snippet chỉ giúp hình dung cú pháp.

## 5. Hiểu cơ chế Spring Profile và Configuration Data

**Spring Profile** là tên logic dùng để bật phần cấu hình hoặc bean phù hợp với một hoàn cảnh chạy ứng dụng. Các profile phổ biến là **local**, **test**, **staging**, **prod**.

Spring Boot đọc **application.yml** làm nguồn cấu hình chung. Khi profile **local** đang active, Boot đọc thêm **application-local.yml** nếu file tồn tại. Cùng một property ở file theo profile có thể ghi đè property trong file chung theo quy tắc ưu tiên của Spring Boot.

~~~text
application.yml
      │
      ├── active profile = local
      │       └── application-local.yml
      │
      ├── active profile = staging
      │       └── application-staging.yml
      │
      └── active profile = prod
              └── application-prod.yml

Runtime environment variables / CLI arguments
      └── có thể ghi đè giá trị từ các tệp cấu hình
~~~

Trong thực tế, **Spring Boot có nhiều PropertySource** với thứ tự ưu tiên cụ thể. Với các trường hợp thông dụng, **command-line arguments** có thể ghi đè giá trị trong file YAML; **biến môi trường của hệ điều hành** cũng có thể ghi đè các property trong YAML. Không nên coi một file profile là nơi có độ ưu tiên tuyệt đối.

Ví dụ:

~~~yaml
# application.yml
server:
  port: 8080
~~~

~~~yaml
# application-staging.yml
server:
  port: 8085
~~~

Khi chạy với profile **staging**, ứng dụng dùng cổng **8085** trừ khi có nguồn cấu hình ưu tiên cao hơn, ví dụ **SERVER_PORT=9000**.

Một số điểm cần nhớ:

- Nếu không chỉ định active profile, Spring sử dụng profile mặc định **default**.
- **SPRING_PROFILES_ACTIVE=local** hoặc **--spring.profiles.active=local** là các cách chỉ định profile.
- Có thể bật nhiều profile, ví dụ **local,debug**, nhưng thứ tự và các ghi đè cần được quản lý cẩn thận; tránh vô tình kích hoạt **prod** cùng profile thử nghiệm.
- Không khai báo **spring.profiles.active** trong **application-local.yml** hoặc trong tài liệu chỉ được kích hoạt bởi một profile. Hãy đặt lựa chọn active profile ở môi trường chạy hoặc tài liệu cấu hình không phụ thuộc profile.
- Có thể dùng các YAML document với **spring.config.activate.on-profile** khi cần nhóm nhiều profile trong một file, nhưng những file **application-{profile}.yml** riêng thường dễ đọc hơn cho người mới học.

**Profile chỉ chọn cấu hình. Profile không tự tạo ranh giới bảo mật.** Không thể suy ra rằng chạy với profile **prod** thì TLS, quyền truy cập, secret và cấu hình IdP đã an toàn nếu chúng chưa được thiết lập đúng.

## 6. Tệp application.yml: cấu hình chung của OAuth 2.0/OIDC Client

Đầu tiên, định nghĩa những thuộc tính chung và sử dụng placeholder để nhận giá trị phụ thuộc môi trường:

~~~yaml
# src/main/resources/application.yml
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

server:
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax

app:
  orders:
    base-url: ${ORDERS_API_BASE_URL}
~~~

Giải thích những phần quan trọng:

| Property | Vai trò |
|---|---|
| **spring.security.oauth2.client.registration.company** | Khai báo một OAuth Client registration có ID **company** |
| **provider: company** | Liên kết registration với cấu hình nhà cung cấp tương ứng |
| **client-id** | Định danh ứng dụng do IdP cấp; có thể khác giữa local/staging/prod |
| **client-secret** | Bí mật của **confidential client**; không được commit vào Git |
| **client-authentication-method** | Phương thức client xác thực tại token endpoint; phải khớp IdP |
| **authorization-grant-type** | Dùng **authorization_code** cho ứng dụng web đăng nhập qua redirect |
| **redirect-uri** | Mẫu URL callback; **{baseUrl}** và **{registrationId}** do Spring Security thay thế |
| **scope: openid** | Yêu cầu OIDC login; các scope khác tùy yêu cầu và chính sách IdP |
| **provider.company.issuer-uri** | Issuer định danh của OpenID Provider; dùng để discovery và kiểm tra issuer |
| **app.orders.base-url** | Thuộc tính nghiệp vụ riêng để Portal gọi Orders API |

**issuer-uri** không phải authorization endpoint hay token endpoint. Nó cần khớp chính xác issuer được công bố trong tài liệu discovery của IdP. Với nhà cung cấp hỗ trợ discovery chuẩn, Spring Security có thể lấy metadata về authorization endpoint, token endpoint, JWKS và user-info endpoint từ issuer.

**registration ID** (**company**) là tên nội bộ của client registration trong ứng dụng, khác với **client-id** do IdP cấp. Spring Security sử dụng registration ID trong URL mặc định:

~~~text
Khởi động login: /oauth2/authorization/company
Callback:        /login/oauth2/code/company
~~~

Giá trị redirect được đăng ký ở IdP phải khớp URL thực mà browser quay về. Thông thường **mỗi môi trường có một client registration riêng ở IdP** để có client secret, allowed redirect URI và chính sách phân quyền độc lập.

**openid** cần thiết cho đăng nhập OIDC. Scope **orders.read** là ví dụ quyền gọi Orders API; IdP phải hỗ trợ cấp scope/token phù hợp với **audience** của API. Việc thêm một scope vào YAML không tự khiến Authorization Server cấp thêm quyền.

## 7. Tệp application-local.yml: phát triển trên máy cá nhân

Tệp local chỉ chứa phần khác so với cấu hình chung:

~~~yaml
# src/main/resources/application-local.yml
server:
  port: 8080

app:
  orders:
    base-url: http://localhost:8081

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Ví dụ trên giả định Orders API chạy trên **localhost:8081**. Client ID, secret và issuer vẫn lấy từ biến môi trường, vì local cũng có thể kết nối IdP riêng và phải bảo vệ credential.

Redirect URI được tạo từ base URL khi Portal chạy local:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Cần đăng ký chính xác URI này trong phần cấu hình client của IdP dùng cho local. Một IdP có thể cho phép HTTP với loopback callback trong môi trường phát triển, nhưng production phải sử dụng HTTPS và redirect URI đáp ứng chính sách của nhà cung cấp.

Không cần đưa **spring.profiles.active: local** vào file này. Local profile sẽ được chọn từ lệnh chạy hoặc biến môi trường.

## 8. application-staging.yml và application-prod.yml

Ở staging và production, Portal thường chạy sau reverse proxy, API gateway hoặc ingress để cung cấp HTTPS và hostname công khai.

### 8.1. Staging

~~~yaml
# src/main/resources/application-staging.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Ví dụ biến môi trường tương ứng:

~~~text
SPRING_PROFILES_ACTIVE=staging
OIDC_ISSUER_URI=https://login.staging.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-staging
OIDC_CLIENT_SECRET=<secret-tu-kho-bi-mat>
ORDERS_API_BASE_URL=https://orders.staging.example.test
~~~

Callback mà IdP staging cần cho phép, giả sử Portal truy cập công khai qua **https://portal.staging.example.test**:

~~~text
https://portal.staging.example.test/login/oauth2/code/company
~~~

### 8.2. Production

~~~yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
  error:
    include-message: never
    include-stacktrace: never

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Ví dụ các biến mà deployment phải cung cấp:

~~~text
SPRING_PROFILES_ACTIVE=prod
OIDC_ISSUER_URI=https://login.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-prod
OIDC_CLIENT_SECRET=<secret-tu-kho-bi-mat>
ORDERS_API_BASE_URL=https://orders.example.test
~~~

Trong production, **OIDC_CLIENT_SECRET** được nạp từ secret manager hoặc cơ chế bí mật của nền tảng deploy, không ghi giá trị thực vào YAML, Dockerfile, command line hiển thị công khai hay tài liệu. Những ví dụ **<secret-tu-kho-bi-mat>** ở trên là ký hiệu mô tả, không phải secret có thể sử dụng.

**Lưu ý về HTTPS phía proxy:** **server.forward-headers-strategy: framework** cho phép Spring xử lý các header forwarded để suy ra scheme/host bên ngoài. Chỉ tin cậy các header đó khi reverse proxy **loại bỏ header Forwarded/X-Forwarded-* do client tùy ý gửi vào** rồi cung cấp header chuẩn từ một proxy đáng tin. Nếu không, kẻ tấn công có thể ảnh hưởng đến URL do ứng dụng tạo.

Trong trường hợp người dùng đến Portal qua HTTPS nhưng backend giữa proxy và ứng dụng chạy HTTP, việc cấu hình forwarded headers đúng là điều kiện quan trọng để **{baseUrl}** tạo redirect URI dạng **https://portal.example.test/...**, thay vì một hostname nội bộ hay **http://...**.

## 9. Bảng so sánh cấu hình các môi trường

| Yếu tố | Local | Staging | Production |
|---|---|---|---|
| Active profile | **local** | **staging** | **prod** |
| URL Portal công khai | **http://localhost:8080** | **https://portal.staging.example.test** | **https://portal.example.test** |
| Issuer | IdP dành cho phát triển | IdP hoặc realm staging | IdP/realm production |
| Client registration | Client ID local | Client ID staging | Client ID prod |
| Client secret | Secret phát triển, chỉ lưu cục bộ an toàn | Secret từ hạ tầng staging | Secret từ secret manager production |
| Redirect URI | Loopback callback | HTTPS staging callback | HTTPS production callback |
| Orders API URL | **http://localhost:8081** | API staging | API production |
| Session cookie **Secure** | Tùy HTTP/HTTPS local | **true** khi chạy qua HTTPS | **true** |
| Forwarded headers | Thường không cần nếu truy cập trực tiếp | Cần khi đứng sau trusted proxy | Cần khi đứng sau trusted proxy |
| Log bảo mật | Mức đủ để debug, có kiểm soát | INFO | INFO, theo chính sách logging |

Không dùng chung client secret giữa local và production để “tiện triển khai”. Phân tách client registration giúp thu hồi, xoay secret và giới hạn redirect URI độc lập giữa các môi trường.

## 10. Cách chạy ứng dụng với profile được chọn

### 10.1. PowerShell trên Windows

Ví dụ trong phiên terminal của lập trình viên:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:OIDC_ISSUER_URI = 'https://login.dev.example.test/realms/company'
$env:OIDC_CLIENT_ID = 'employee-portal-local'
$env:OIDC_CLIENT_SECRET = '<local-dev-client-secret>'

./gradlew.bat bootRun
~~~

Property **app.orders.base-url** được lấy từ **application-local.yml**, nên không cần truyền **ORDERS_API_BASE_URL** trong ví dụ này. Nếu muốn ghi đè bằng biến môi trường:

~~~powershell
$env:ORDERS_API_BASE_URL = 'http://localhost:8099'
~~~

Biến môi trường thường có độ ưu tiên cao hơn giá trị trong **application-local.yml**, vì vậy Portal sẽ dùng URL mới. Các giá trị secret ở ví dụ là placeholder: sử dụng secret thực được cấp riêng cho môi trường, không paste secret thật vào tài liệu hay output chia sẻ.

### 10.2. Bash hoặc terminal Linux/macOS

~~~bash
export SPRING_PROFILES_ACTIVE=local
export OIDC_ISSUER_URI=https://login.dev.example.test/realms/company
export OIDC_CLIENT_ID=employee-portal-local
export OIDC_CLIENT_SECRET='<local-dev-client-secret>'

./gradlew bootRun
~~~

### 10.3. Chỉ định profile khi chạy JAR

~~~bash
java -jar build/libs/employee-portal.jar --spring.profiles.active=prod
~~~

Tên file JAR tùy cấu hình build. Cần cấp **OIDC_ISSUER_URI**, **OIDC_CLIENT_ID**, **OIDC_CLIENT_SECRET** và **ORDERS_API_BASE_URL** qua môi trường chạy hoặc nguồn cấu hình bảo mật trước khi khởi động.

### 10.4. Vì sao không nên mặc định local trong application.yml?

Nếu thêm:

~~~yaml
spring:
  profiles:
    active: local
~~~

vào cấu hình chung, một deployment vô tình không truyền profile có thể chạy với cấu hình local. Tốt hơn là buộc môi trường deploy chọn profile rõ ràng, đặc biệt trong production. Nếu khởi động không có profile và thiếu placeholder bắt buộc, ứng dụng nên thất bại sớm để người vận hành biết cấu hình chưa hoàn chỉnh.

## 11. Tổ chức SecurityFilterChain dùng chung cho mọi profile

Khi các môi trường dùng cùng luồng OIDC và cùng chính sách bảo vệ endpoint, chỉ cần một cấu hình Spring Security:

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
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình này:

1. Cho phép truy cập trang public và static asset được khai báo.
2. Yêu cầu xác thực đối với các endpoint còn lại.
3. Bật **oauth2Login()** để đăng nhập OIDC qua Authorization Code Flow. Spring Security mặc định khởi động login từ **/oauth2/authorization/company**, xử lý callback ở **/login/oauth2/code/company**.
4. Bật **oauth2Client()** để có nền tảng sử dụng authorized client khi gọi API.
5. Giữ **CSRF protection** mặc định của ứng dụng web dùng session cookie; không tắt CSRF toàn cục chỉ để các request từ frontend “dễ chạy”.

Một client registration có **scope openid** sẽ kích hoạt xử lý OIDC login phù hợp. Ứng dụng cần một Identity Provider tương thích với cấu hình đã khai báo; các ví dụ YAML không tự tạo IdP.

### 11.1. Tránh kiểm tra profile để đổi chính sách bảo mật tùy tiện

Ví dụ sau khó kiểm soát:

~~~java
// Cách làm cần tránh:
// if ("local".equals(activeProfile)) {
//     http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
// }
~~~

Nếu môi trường staging/prod vô tình nhận sai profile, hoặc một nhánh cấu hình bị triển khai nhầm, endpoint có thể bị mở quyền. Dùng chung chính sách bảo mật cốt lõi và chỉ thay đổi property môi trường. Khi thật sự cần SecurityFilterChain chuyên biệt cho test, hãy giới hạn bằng test configuration rõ ràng, không đưa nhánh bỏ qua security vào artifact production.

## 12. Đóng gói cấu hình ứng dụng bằng @ConfigurationProperties

Ngoài property có sẵn của Spring Security, ứng dụng thường có các property riêng như base URL của API. Thay vì rải **@Value** trên nhiều lớp, dùng một kiểu cấu hình:

~~~java
package com.example.portal.config;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.orders")
public record OrdersApiProperties(URI baseUrl) {
}
~~~

Đăng ký quét configuration properties ở lớp main:

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortalApplication.class, args);
    }
}
~~~

Khi đó property **app.orders.base-url** trong các file YAML được bind thành **OrdersApiProperties.baseUrl()** kiểu **URI**. Service có thể nhận bean này qua constructor; cách này dễ kiểm soát và mở rộng khi có thêm timeout, API path hoặc các cờ nghiệp vụ.

Ví dụ client gọi Orders API:

~~~java
package com.example.portal.client;

import com.example.portal.config.OrdersApiProperties;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OrdersApiClient {

    private final RestClient restClient;

    public OrdersApiClient(RestClient.Builder builder,
                           OrdersApiProperties properties) {
        this.restClient = builder
            .baseUrl(properties.baseUrl().toString())
            .build();
    }

    public String getOrders(String accessToken) {
        return restClient.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

Với Spring Security OAuth 2.0 Client, controller có thể nhận access token của chính người dùng hiện tại qua authorized client:

~~~java
package com.example.portal.web;

import com.example.portal.client.OrdersApiClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    private final OrdersApiClient ordersApiClient;

    public OrdersController(OrdersApiClient ordersApiClient) {
        this.ordersApiClient = ordersApiClient;
    }

    @GetMapping("/bff/orders")
    public String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        return ordersApiClient.getOrders(
            authorizedClient.getAccessToken().getTokenValue());
    }
}
~~~

**Điểm quan trọng:** tên registration **company** không đổi giữa các profile, nhưng các giá trị **client ID**, **secret**, **issuer** và **Orders API URL** có thể thay đổi theo môi trường. Nhờ vậy logic controller/service không cần biết ứng dụng đang chạy local hay prod.

Ví dụ trên dùng RestClient đồng bộ để đơn giản hóa luồng. Trong ứng dụng thực tế cần thêm timeout, xử lý lỗi 401/403, retry phù hợp, refresh access token khi được cấp và bảo vệ token trong log. **OAuth2AuthorizedClientManager** có thể quản lý việc lấy lại token theo cấu hình và ngữ cảnh, tránh tự xây dựng cơ chế refresh thủ công.

## 13. File .env, biến môi trường và secret manager

### 13.1. .env.example dùng để mô tả đầu vào

Có thể đặt một tệp **.env.example** trong repository:

~~~dotenv
# Chỉ là tên và ví dụ, KHÔNG chứa secret thật
SPRING_PROFILES_ACTIVE=local
OIDC_ISSUER_URI=https://login.dev.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-local
OIDC_CLIENT_SECRET=REPLACE_WITH_LOCAL_SECRET
ORDERS_API_BASE_URL=http://localhost:8081
~~~

Lưu ý: **Spring Boot không tự động đọc file .env chỉ vì file tồn tại**. Công cụ khởi chạy (IDE, Docker Compose, script, bộ nạp environment hoặc cơ chế import config được cấu hình rõ ràng) phải nạp các biến vào môi trường của tiến trình Java. Chạy ứng dụng bằng IDE có thể cần cấu hình environment variables trong Run Configuration.

Tệp chứa secret thật, chẳng hạn **.env.local**, không được commit. Ví dụ:

~~~gitignore
.env
.env.*
!.env.example
~~~

Quy tắc trên chỉ là ví dụ cho loại file .env; phải kiểm tra kỹ quy ước .gitignore chung của repository, đặc biệt khi có các file .env phi bí mật vốn đã được quản lý.

### 13.2. Secret trong staging và production

Trong deployment nên dùng cơ chế của nền tảng, ví dụ:

- Kubernetes Secret kết hợp quyền truy cập tối thiểu, hoặc secret manager của cloud provider.
- Biến môi trường do nền tảng deploy chèn lúc chạy, không in vào log cấu hình.
- Mounted secret file/config tree nếu hệ thống chọn kiểu nạp bằng file và có cơ chế bảo vệ phù hợp.

Không đặt secret trong Docker image, Git repository, frontend bundle, tham số URL, log hoặc thông báo lỗi. Cần có quy trình **rotation**: cập nhật credential trên IdP, cập nhật secret runtime, tái triển khai/khởi động lại workload theo cách có kiểm soát và thu hồi credential cũ.

### 13.3. Biến môi trường trực tiếp cho Spring Security

Spring Boot còn hỗ trợ **relaxed binding** từ tên biến môi trường sang property, ví dụ:

~~~text
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_ID
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_COMPANY_ISSUER_URI
~~~

Tuy nhiên, cách dùng **${OIDC_CLIENT_ID}**, **${OIDC_CLIENT_SECRET}**, **${OIDC_ISSUER_URI}** trong YAML chung giúp nhóm các đầu vào của dự án thành các tên ngắn, ổn định và dễ ghi vào tài liệu deploy. Chọn một quy ước rõ ràng, tránh có quá nhiều tên tương đương gây khó biết nguồn nào thực sự thắng khi cấu hình được ghi đè.

## 14. Redirect URI và reverse proxy: lỗi hay gặp khi đổi môi trường

Trong OAuth 2.0 Authorization Code Flow, browser đến IdP, đăng nhập, rồi quay về **redirect URI** của Portal cùng authorization code. IdP thường kiểm tra redirect URI có nằm trong danh sách cho phép hay không.

Giả sử production chạy theo đường đi:

~~~text
Browser
  -> https://portal.example.test
  -> Reverse proxy / ingress (TLS termination)
  -> http://portal-service:8080
  -> Spring Boot Portal
~~~

Nếu Portal suy ra **{baseUrl}** từ request nội bộ, nó có thể tạo callback sai:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

Trong khi IdP đã đăng ký:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Khi đó IdP có thể trả lỗi **redirect_uri mismatch**, hoặc callback đi về một địa chỉ mà browser không truy cập được.

Các bước xử lý:

1. Đăng ký callback công khai **chính xác** ở cấu hình OAuth client của IdP.
2. Đảm bảo proxy chuyển tiếp các header về scheme/host/port/prefix mà Spring cần.
3. Cấu hình **server.forward-headers-strategy** phù hợp với hạ tầng và chỉ tin cậy forwarded headers do proxy kiểm soát.
4. Kiểm tra request login sinh ra **redirect_uri=https://portal.example.test/login/oauth2/code/company** trong môi trường tương ứng.
5. Nếu ứng dụng đặt sau path prefix như **/portal**, cần tính cả prefix vào base URL/callback và cấu hình proxy nhất quán.

Có thể cố định **redirect-uri** theo biến môi trường trong trường hợp hạ tầng khó tái tạo base URL, ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: ${OIDC_REDIRECT_URI}
~~~

Tuy nhiên, khi cùng source chạy nhiều host, template **{baseUrl}** với cấu hình proxy chính xác thường linh hoạt hơn. Dù chọn cách nào, **giá trị redirect thực tế phải đúng với whitelist tại IdP**. Không dùng wildcard redirect URI tùy tiện.

## 15. Session, cookie, SameSite và môi trường nhiều instance

Đăng nhập OIDC thành công thường tạo một **SecurityContext** gắn với HTTP session của Portal. Trong ứng dụng web phía server:

~~~text
Browser --session cookie--> Portal
Portal  --access token----> Orders API
~~~

Cookie session không phải OAuth access token, và access token không cần được đưa vào JavaScript để trình duyệt gọi các endpoint BFF.

Các thuộc tính cookie cần xem xét:

- **HttpOnly**: ngăn JavaScript đọc cookie session trực tiếp.
- **Secure**: chỉ gửi cookie qua HTTPS; bật ở môi trường có HTTPS thực tế.
- **SameSite**: **Lax** thường phù hợp với luồng OIDC redirect qua top-level GET, nhưng các cơ chế callback như **response_mode=form_post**, nhúng iframe hoặc luồng cross-site đặc biệt có thể cần **SameSite=None** kết hợp **Secure** theo thiết kế bảo mật.
- **Domain, Path**: cần tương ứng với hostname/path công khai; tránh đặt phạm vi cookie rộng không cần thiết.
- **CSRF protection**: cần giữ hoặc thiết kế đúng cho các endpoint dùng session cookie để thay đổi trạng thái.

Khi ứng dụng chạy nhiều replica/instance, cần xem xét lưu trữ session và **OAuth2AuthorizedClient**:

| Vấn đề | Tác động | Hướng xử lý |
|---|---|---|
| Session chỉ nằm trong RAM một instance | Request chuyển node có thể mất trạng thái đăng nhập | Lưu session chia sẻ phù hợp, ví dụ Spring Session với backend được hỗ trợ, hoặc hạ tầng đảm bảo phiên theo chính sách |
| Authorized client/token chỉ lưu cục bộ | Một node khác không có token để gọi API | Chọn **OAuth2AuthorizedClientService/Repository** phù hợp cách lưu và vòng đời |
| Secret/issuer khác nhau giữa các replica | Login và refresh token không nhất quán | Cung cấp cấu hình cùng phiên bản cho cùng deployment |
| Ứng dụng bị redeploy | Session/token đang giữ có thể bị mất hoặc hết hạn | Thiết kế lại authorization/login hoặc lưu state phù hợp với yêu cầu |

Không mặc định Spring Boot tự cung cấp session phân tán và token repository bền vững. Chọn giải pháp lưu trữ, bảo vệ dữ liệu nhạy cảm và thời gian sống dựa trên kiến trúc thực tế.

## 16. Khi có nhiều OIDC Provider hoặc nhiều client registration

Một ứng dụng có thể cho phép đăng nhập qua nhiều nhà cung cấp, ví dụ **company** và **partner**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_OIDC_CLIENT_ID}
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
          partner:
            issuer-uri: ${PARTNER_OIDC_ISSUER_URI}
~~~

Đây là **ví dụ thay thế** cấu hình registration **company** ở mục 6, không phải đoạn cần dán nối nguyên vẹn vào YAML trước đó.

Mỗi registration có URL bắt đầu login riêng:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Tương ứng, callback mặc định theo registration ID:

~~~text
/login/oauth2/code/company
/login/oauth2/code/partner
~~~

Trong hệ thống đa tenant hoặc nhiều IdP, cần quản lý issuer, callback, principal mapping, quyền và audience cẩn thận. Không suy ra hai người dùng có cùng email từ hai issuer khác nhau là cùng một danh tính nội bộ. Một cách nhận diện chắc chắn thường kết hợp **issuer** và **subject** theo chính sách của ứng dụng.

## 17. Kiểm thử cấu hình theo profile

Profile **test** có thể dùng trong test suite, nhưng không nên dựa vào một IdP production thật để mỗi lần chạy unit/integration test. Những cách thường dùng:

- **Spring Security Test** để mô phỏng principal OIDC khi kiểm tra controller hoặc chính sách endpoint.
- **Stub/WireMock** cho metadata discovery, authorization/token/user-info/JWKS endpoints trong integration test nếu kiểm thử luồng với IdP giả lập.
- Testcontainers hoặc môi trường IdP chuyên biệt cho những bài kiểm thử end-to-end bắt buộc có nhà cung cấp danh tính thực sự.
- Đặt **application-test.yml** với endpoint/credential thử nghiệm và cô lập khỏi production. Test configuration cần có cấu hình client hợp lệ để Spring Boot khởi tạo context, kể cả khi request sử dụng mock principal.

Ví dụ, trước hết tạo một endpoint chỉ dùng OIDC principal, không gọi API bên ngoài:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("sub", user.getSubject());
    }
}
~~~

Sau đó kiểm tra bằng **spring-security-test**:

~~~java
package com.example.portal.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ProfileControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void authenticatedOidcUserCanAccessProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/me").with(oidcLogin()
                .idToken(token -> token.claim("sub", "employee-42"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("employee-42"));
    }
}
~~~

Để chạy **@SpringBootTest**, profile **test** còn phải cung cấp hoặc mock **ClientRegistrationRepository** hợp lệ; nếu cấu hình provider dùng **issuer-uri**, có thể cần stub discovery endpoint trong quá trình khởi tạo context. **oidcLogin()** chỉ mô phỏng người dùng đã đăng nhập trong MockMvc, không tự cung cấp một Authorization Server thử nghiệm. Những test này chưa chứng minh IdP phát hành token đúng trong môi trường thật; kiểm tra end-to-end vẫn cần xác nhận redirect URI, issuer, audience, scope, token refresh, logout và trạng thái session trên hạ tầng tương ứng.

## 18. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách tiếp cận xử lý |
|---|---|---|
| Khởi động lỗi vì thiếu **OIDC_CLIENT_SECRET** hoặc issuer | Chưa nạp biến môi trường; file .env chưa được đọc | Xác nhận nguồn runtime, profile và placeholder, không in secret ra log |
| IdP báo **invalid_redirect_uri** | Redirect thực tế không khớp whitelist | Kiểm tra hostname, scheme, port, path và đăng ký IdP |
| Login chuyển đến **http://internal-host** | Proxy không gửi hoặc Spring không tin forwarded headers | Cấu hình trusted proxy, forwarded headers và base URL |
| Login thành công local, thất bại staging | Issuer/client ID/secret/callback sai môi trường | So sánh cấu hình non-secret và cấu hình client registration ở IdP staging |
| **invalid_client** khi đổi authorization code | Client secret hoặc phương thức client authentication sai | Kiểm tra registration tương ứng và credential đang deploy |
| **invalid_scope** hoặc API trả **403** | Scope chưa được cấp hoặc mapping authority chưa đúng | Kiểm tra quyền được cấp, scope thực tế và rule của Resource Server |
| API trả **401** dù Portal login thành công | Access token hết hạn, sai issuer/audience hoặc không hợp lệ | Kiểm tra token lifecycle và cấu hình Resource Server; không dùng ID Token thay access token |
| Cookie đăng nhập không được gửi sau redirect | Secure/SameSite/domain/path hoặc TLS/proxy không phù hợp | Kiểm tra attribute cookie và mode callback |
| Deploy nhiều instance thì login chập chờn | Session/authorized client không dùng kho lưu trữ phù hợp | Kiểm tra chiến lược session và lưu token giữa các instance |
| File **application-prod.yml** tồn tại nhưng không áp dụng | Chưa bật profile **prod** hoặc có nguồn khác ghi đè | Kiểm tra active profiles và nguồn property có ưu tiên cao hơn |
| Endpoint đăng nhập không xuất hiện | Thiếu dependency OAuth2 Client, registration hoặc SecurityFilterChain | Kiểm tra starter, bean và tên registration ID |

Khi điều tra, chỉ bật log chi tiết trong môi trường kiểm soát, thời gian ngắn và đã xác định dữ liệu nào có thể xuất hiện. **Không ghi authorization code, access token, refresh token, client secret hoặc session cookie vào log chia sẻ.**

## 19. Quy trình triển khai một môi trường mới

Giả sử cần mở thêm môi trường **preprod**. Có thể làm tuần tự:

1. **Tạo client tại IdP preprod**: cấp client ID, phương thức xác thực, secret; đăng ký callback chính xác; bật grant **authorization_code**, scope OIDC/API cần thiết và chính sách PKCE nếu được yêu cầu.
2. **Tạo file application-preprod.yml** chỉ với khác biệt không nhạy cảm như forwarded headers, cookie, log và feature cần thiết; giữ cấu hình logic security chung.
3. **Cung cấp runtime variables**: **SPRING_PROFILES_ACTIVE=preprod**, **OIDC_ISSUER_URI**, **OIDC_CLIENT_ID**, **OIDC_CLIENT_SECRET**, **ORDERS_API_BASE_URL**.
4. **Thiết lập HTTPS, proxy và DNS**: browser phải truy cập URL công khai; Spring tạo **{baseUrl}** đúng theo đường đi bên ngoài.
5. **Đảm bảo Resource Server tương ứng**: Orders API preprod chấp nhận access token đúng issuer, audience và scope; Portal không tự sửa access token.
6. **Kiểm tra hành vi thực tế**: chuyển hướng đăng nhập, callback, session cookie, gọi API bằng token của người dùng, lỗi 401/403, hết hạn/refresh, logout và môi trường nhiều instance nếu có.
7. **Ghi nhận đầu vào vận hành**: tên biến, URL redirect, phương thức rotation secret, người/phân hệ chịu trách nhiệm IdP và hạ tầng.

Các bước này giúp thêm môi trường mới chủ yếu qua cấu hình và đăng ký IdP, trong khi logic business và SecurityFilterChain được dùng lại.

## 20. Tóm lược mối liên hệ giữa cấu trúc dự án, profile và OAuth 2.0/OIDC

Một ứng dụng Spring Boot OAuth 2.0/OIDC Client vận hành ổn định khi ba lớp được phân tách:

1. **Mã nguồn** diễn tả hành vi chung: bảo vệ URL, đăng nhập OIDC, lấy authorized client và gọi API thay mặt người dùng.
2. **Configuration Data + Spring Profiles** chọn các giá trị phù hợp: issuer, client registration, địa chỉ API, proxy, cookie và logging.
3. **Hạ tầng/secret manager** cung cấp secret, hostname HTTPS, session storage và thông tin thực sự nhạy cảm ở thời điểm chạy.

Với cấu trúc đó, cùng một Portal có thể chạy local, staging và production mà không cần sao chép lớp bảo mật. Bài học cốt lõi là **giữ registration ID và luồng nghiệp vụ ổn định**, thay đổi thông tin môi trường qua property được quản lý có chủ đích, và luôn xác nhận **issuer + client ID/secret + redirect URI + TLS/proxy + quyền API** hoạt động đúng trong từng môi trường.
