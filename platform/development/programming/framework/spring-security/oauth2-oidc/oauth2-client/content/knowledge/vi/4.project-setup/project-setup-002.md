# 4.2. Dependency OAuth2 Client cho ứng dụng Servlet

## 1. Mục tiêu và phạm vi

Để một ứng dụng **Spring Boot sử dụng Servlet stack** đăng nhập bằng OAuth 2.0/OpenID Connect (OIDC), nhận token từ một Authorization Server và gọi API bên ngoài thay mặt người dùng, trước tiên cần đưa đúng thư viện **Spring Security OAuth2 Client** vào classpath.

Bài này tập trung vào bước **thiết lập dependency**: chọn starter cho đúng phiên bản Spring Boot, hiểu các thư viện được kéo vào, cấu hình tối thiểu để xác nhận tích hợp, và tránh nhầm lẫn với Resource Server hoặc ứng dụng WebFlux.

Sau bài học, bạn cần phân biệt được:

- Ứng dụng **OAuth2 Client** khởi tạo đăng nhập hoặc xin Access Token để gọi hệ thống khác.
- Ứng dụng **Resource Server** nhận Access Token và bảo vệ API của chính mình.
- Ứng dụng **Authorization Server** phát hành Authorization Code, Access Token hoặc ID Token.
- **Servlet web application** dùng Spring MVC, Servlet Filter và `SecurityFilterChain`; **reactive web application** dùng WebFlux, `SecurityWebFilterChain` và API reactive tương ứng.

**Một ứng dụng có thể đồng thời là OAuth2 Client và Resource Server**, nhưng đó là hai trách nhiệm riêng, không cần cài thêm starter Resource Server nếu chỉ muốn đăng nhập bằng nhà cung cấp OIDC.

## 2. Chọn đúng dependency theo phiên bản Spring Boot

Spring Boot cung cấp *starter*: một dependency gom các thư viện thường cần, kèm cơ chế quản lý phiên bản để bạn không phải liệt kê từng module Spring Security.

### 2.1. Bảng chọn nhanh

| Ngữ cảnh | Servlet/MVC starter | OAuth2 Client starter | Ghi chú |
| --- | --- | --- | --- |
| **Spring Boot 3.x** | `org.springframework.boot:spring-boot-starter-web` | `org.springframework.boot:spring-boot-starter-oauth2-client` | Bộ tên starter quen thuộc trong Boot 3 |
| **Spring Boot 4.x** | `org.springframework.boot:spring-boot-starter-webmvc` | `org.springframework.boot:spring-boot-starter-security-oauth2-client` | Boot 4 tách/đổi tên nhiều starter theo hướng modular; hai tên Boot 3 tương ứng đã được đánh dấu deprecated trong Boot 4 |

Việc chọn **Boot 3 hay Boot 4** phải dựa trên phiên bản plugin/parent/BOM thực tế của dự án. Không phối hợp ngẫu nhiên starter của hai nhánh trong một build.

Các ví dụ bên dưới giả định dự án đã có Spring Boot Maven parent hoặc Spring Boot Gradle plugin cùng dependency management/BOM phù hợp. **Không gắn version riêng** cho các starter Spring Boot và từng module Spring Security trong cùng bộ phiên bản đã được quản lý.

### 2.2. Gradle Groovy DSL — Spring Boot 3.x

Trong `build.gradle` của **dự án Spring Boot 3.x có plugin và dependency management đã thiết lập**:

~~~groovy
dependencies {
    // Chạy HTTP server với Spring MVC + embedded Servlet container.
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // OAuth 2.0 Login, OIDC Login và OAuth2 Client gọi downstream API.
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Kiểm thử (không đưa vào runtime artifact).
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Nếu dự án đã có `spring-boot-starter-web` thì **giữ một khai báo hiện có**, chỉ thêm starter OAuth2 Client. Không cần khai báo cả `spring-security-oauth2-client` và các module phụ thuộc thủ công khi dùng starter.

### 2.3. Gradle Kotlin DSL — Spring Boot 3.x

Trong `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Các dấu ngoặc trong Kotlin DSL là cú pháp khác Gradle Groovy DSL; ý nghĩa dependency không đổi.

### 2.4. Maven — Spring Boot 3.x

Trong `pom.xml` có Spring Boot parent hoặc import BOM quản lý dependency:

~~~xml
<dependencies>
    <!-- Spring MVC, Servlet stack, embedded container -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- OAuth2/OIDC Client -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <!-- Test-only dependencies -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Khi đã quản lý version qua Spring Boot parent/BOM, không đặt `<version>` ở mỗi starter. Nếu dự án không dùng Spring Boot parent thì cần import BOM đúng cách trong `dependencyManagement`; nếu không, Maven có thể báo thiếu phiên bản dependency.

### 2.5. Gradle — Spring Boot 4.x

Trong dự án **Spring Boot 4.x** với dependency management đúng nhánh:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-test'
}
~~~

Boot 4 cung cấp thêm các starter test chuyên biệt, chẳng hạn `spring-boot-starter-security-oauth2-client-test`, khi bài kiểm thử cần phần hỗ trợ OAuth2 Client tương ứng.

Tương đương với **Gradle Kotlin DSL**:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-test")
}
~~~

### 2.6. Maven — Spring Boot 4.x

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Lưu ý khi di chuyển Boot 3 → Boot 4:** `spring-boot-starter-oauth2-client` và `spring-boot-starter-web` được duy trì như tên cũ nhưng đã deprecated trong Boot 4. Với dự án Boot 4 mới, nên dùng các tên starter mới để tránh phát sinh phụ thuộc API đã lỗi thời về sau. Việc nâng cấp toàn bộ Spring Boot/Spring Security cần thực hiện nhất quán, không chỉ đổi một dependency rồi trộn các version.

## 3. Vì sao cần cả Servlet web starter và OAuth2 Client starter?

Một ứng dụng đăng nhập OIDC kiểu Servlet thường có **hai lớp chức năng**:

~~~mermaid
flowchart TB
    P["Ứng dụng Spring Boot Servlet"] --> W["Spring MVC / embedded Servlet container"]
    P --> S["Spring Security Filter Chain"]
    S --> O["OAuth2 Client / OIDC Login"]
    W --> C["Controller, view, session"]
    O --> AR["Authorization Request / Callback"]
    O --> TOK["ClientRegistration + AuthorizedClient + Tokens"]
    AR --> IDP["Authorization Server / OIDC Provider"]
    TOK --> API["Resource Server bên ngoài"]
~~~

**Servlet web starter** cung cấp Spring MVC, HTTP request/response và embedded Servlet container (thường là Tomcat), cần cho endpoint giao diện và callback đăng nhập. **OAuth2 Client starter** cung cấp cơ chế ủy quyền, callback, token và dữ liệu người dùng OIDC ở tầng Spring Security.

Một số thành phần tiêu biểu khi dùng Spring Security OAuth2 Client:

| Thành phần | Vai trò |
| --- | --- |
| `spring-security-oauth2-client` | Các API và implementation OAuth2 Client, OAuth2 Login, OIDC Login |
| `spring-security-oauth2-core` | Các kiểu OAuth2 core như Access Token, Authorization Grant, lỗi giao thức |
| `spring-security-oauth2-jose` | Hỗ trợ xử lý JWT/JWS/JWK cần thiết cho chức năng OAuth2/OIDC |
| `spring-security-web` | Bộ lọc, chain và cơ chế bảo mật web |
| `spring-security-config` | DSL `HttpSecurity` và cấu hình các cơ chế Spring Security |
| Spring Boot auto-configuration | Tự tạo/điều chỉnh beans theo classpath và `spring.security.oauth2.client.*` |

Danh sách phụ thuộc chính xác phụ thuộc vào phiên bản và starter đã chọn; đây là quan hệ về chức năng, **không phải danh sách để khai báo thủ công**. Với Spring Boot 4, starter OAuth2 Client mới đi cùng các thành phần security được quản lý bởi Boot.

### Khi nào cần `spring-boot-starter-security` riêng?

Bạn có thể khai báo starter Spring Security để thể hiện rõ mục đích bảo mật tổng thể, nhưng không nên thêm theo phản xạ nếu starter OAuth2 Client đã kéo vào các thành phần cần thiết. Trên Boot 4, OAuth2 Client starter mới đã phụ thuộc starter Spring Security. Điều cần kiểm tra là **dependency graph thực tế** của dự án, không dựa vào cảm giác “càng nhiều starter càng đầy đủ”.

### Những dependency thường không bắt buộc

| Dependency | Khi nào nên thêm? | Có bắt buộc cho OAuth2 Login Servlet không? |
| --- | --- | --- |
| `spring-boot-starter-thymeleaf` | Render login page/trang hồ sơ theo template Thymeleaf | Không; trang login mặc định có thể được Spring Security tạo |
| `spring-boot-starter-actuator` | Health, metrics, vận hành | Không |
| `spring-boot-starter-validation` | Validate request DTO | Không |
| `spring-boot-starter-oauth2-resource-server` (Boot 3) / `spring-boot-starter-security-oauth2-resource-server` (Boot 4) | Ứng dụng **nhận** bearer token và bảo vệ API của chính nó | Không, nếu chỉ là OAuth2 Client |
| Starter Authorization Server tương ứng | Ứng dụng tự phát hành authorization code/token cho client khác | Không |
| `spring-boot-starter-webflux` | Xây ứng dụng reactive hoặc cần thư viện WebClient theo thiết kế đã chọn | Không chỉ vì cấu hình OAuth2 Client cho Servlet |
| `spring-security-test` hoặc security test starter của Boot 4 | Kiểm thử security filter, OAuth2 login, mock users | Chỉ cho test scope |

## 4. Servlet stack và Reactive stack là hai mô hình khác nhau

Spring Security OAuth2 Client hỗ trợ cả Servlet và Reactive nhưng class và cấu hình không giống nhau.

| Tiêu chí | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Mô hình xử lý | Servlet request, Spring MVC | Reactive pipeline |
| Cấu hình security | `SecurityFilterChain`, `HttpSecurity` | `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Ngữ cảnh request | `HttpServletRequest` và Spring SecurityContext tương ứng | `ServerWebExchange` và Reactor Context |
| Authorized client manager | `DefaultOAuth2AuthorizedClientManager` / `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Reactive authorized client manager |
| OAuth2 Client login | `oauth2Login()` trên `HttpSecurity` | `oauth2Login()` trên `ServerHttpSecurity` |
| HTTP client thường gặp | `RestClient` hoặc `RestTemplate`; có thể dùng WebClient nếu muốn | `WebClient` |

**“OAuth2 Client” không đồng nghĩa “Reactive Client”.** Ví dụ ứng dụng dùng `@RestController`, Spring MVC và Tomcat vẫn có thể là OAuth2 Client hoàn chỉnh. Nếu thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên mô hình Servlet khi cả hai cùng có mặt, nhưng không nên tạo cấu hình lai chỉ để thử OAuth2.

Khi đang học Servlet Client, import:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Không dùng `ServerHttpSecurity` hoặc `SecurityWebFilterChain` trong cùng ví dụ.

## 5. Từ dependency đến một ứng dụng đăng nhập OIDC tối thiểu

Starter mới chỉ cung cấp class và auto-configuration. Để chạy được đăng nhập cần thêm **đăng ký client tại nhà cung cấp danh tính** và cấu hình `ClientRegistration`.

### 5.1. Đăng ký ứng dụng tại OIDC Provider

Ví dụ backend Servlet ở địa chỉ `http://localhost:8080`:

| Thông số | Giá trị ví dụ |
| --- | --- |
| Client type | Confidential web application (backend giữ được client secret) |
| Authorization grant | Authorization Code |
| Client ID | `demo-web` |
| Client secret | Cấu hình riêng trên máy hoặc secret manager |
| Redirect URI | `http://localhost:8080/login/oauth2/code/demo` |
| Scope | `openid profile email` |
| Issuer | `https://id.example.com/realms/demo` |

Tên `demo` là **registrationId của Spring Security**; `demo-web` là **client ID đã đăng ký ở provider**. Hai giá trị không bắt buộc giống nhau. Provider phải công bố issuer và endpoint thật tương ứng; các URL trong bài là minh họa.

### 5.2. Cấu hình `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-provider:
            issuer-uri: https://id.example.com/realms/demo
~~~

Khi có `issuer-uri` và provider hỗ trợ OIDC discovery, Spring có thể tìm các endpoint authorization, token, UserInfo và JWKS từ metadata của provider. **Không cần khai báo thủ công mọi endpoint** nếu discovery hoạt động.

Các chú ý:

- `client-id` / `client-secret` lấy từ biến môi trường hoặc hệ thống quản lý bí mật; không commit secret.
- `issuer-uri` phải khớp chính xác issuer do provider công bố. Đường dẫn ví dụ không có giá trị với mọi nhà cung cấp.
- `openid` kích hoạt ngữ cảnh OIDC; không có `openid` thì OAuth2 Login vẫn có thể hoạt động với một số provider, nhưng không được giả định có ID Token.
- `redirect-uri` phải trùng với redirect URI đã đăng ký (bao gồm scheme, host, port và path).
- Việc chạy local qua HTTP chỉ phục vụ phát triển nếu provider cho phép; production nên dùng HTTPS.

### 5.3. Cấu hình `SecurityFilterChain`

Ví dụ cho Spring Security kiểu Servlet:

~~~java
package com.example.demo.security;

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
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` dùng cho login của người dùng thông qua authorization code/OIDC. `oauth2Client()` cấu hình khả năng OAuth2 Client khi cần quản lý và sử dụng authorized client để gọi API. Ứng dụng chỉ muốn dùng client credentials ở tác vụ backend mà không có login sẽ cần luồng authorized-client manager khác; không nên bật `oauth2Login()` như điều kiện bắt buộc cho mọi client.

Không cần thêm `@EnableWebSecurity` chỉ để chạy ví dụ khi Spring Boot đã auto-configure thành phần web/security đúng; dùng `SecurityFilterChain` để biểu đạt chính sách bảo vệ URL.

### 5.4. Controller đọc principal OIDC đã xác minh

~~~java
package com.example.demo.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/")
    public String home() {
        return "Open /me to start OIDC login";
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
~~~

Khi truy cập `/me` chưa có phiên đăng nhập, Spring Security chuyển người dùng vào luồng login phù hợp. Nếu trong ứng dụng có nhiều registration, trang login mặc định có thể hiển thị các lựa chọn; có thể bắt đầu trực tiếp ở `/oauth2/authorization/demo`.

Vì scope chứa `openid`, principal thành công thường là `OidcUser`. Nếu thực hiện OAuth2 Login **không có OIDC**, principal có thể là `OAuth2User`; không nên ép kiểu `OidcUser` trong mọi kịch bản OAuth2.

**Lưu ý bảo mật:** controller chỉ trả issuer và subject minh họa, không xuất `id_token`, `access_token`, `refresh_token` hoặc secret ra response.

## 6. Dependency chạy đến đâu trong request đăng nhập?

Các thành phần chính có thể hình dung theo sơ đồ:

~~~mermaid
sequenceDiagram
    actor User as Browser
    participant MVC as Spring MVC / Servlet
    participant Filter as Spring Security Filter Chain
    participant AS as OIDC Provider
    User->>MVC: GET /me
    MVC->>Filter: Request đi qua security filters
    Filter-->>User: 302 đến /oauth2/authorization/demo
    User->>Filter: GET /oauth2/authorization/demo
    Filter-->>User: 302 đến authorization endpoint
    User->>AS: Người dùng xác thực và cấp quyền
    AS-->>User: 302 callback?code=...&state=...
    User->>Filter: GET /login/oauth2/code/demo?code=...
    Filter->>AS: POST token endpoint
    AS-->>Filter: ID Token + Access Token
    Filter->>Filter: Xác minh token; tạo Authentication
    Filter-->>User: Redirect về URL ban đầu
    User->>MVC: GET /me có session
    MVC-->>User: JSON issuer + subject
~~~

Trong thực tế, **Servlet Filter Chain** chạy trước controller, nên các URL dành riêng cho OAuth2 authorization và callback được Spring Security xử lý thay vì tạo controller thủ công.

Các endpoint mặc định quan trọng:

| Đường dẫn | Vai trò |
| --- | --- |
| `/oauth2/authorization/{registrationId}` | Khởi tạo authorization request, redirect đến provider |
| `/login/oauth2/code/{registrationId}` | Nhận callback Authorization Code mặc định |
| `/login` | Trang login mặc định, nếu Spring Security tạo và cấu hình cho trường hợp tương ứng |
| `/logout` | Cơ chế logout của ứng dụng theo Spring Security; logout tại OIDC Provider có thể cần cấu hình riêng |

Tên `registrationId` trong URL phải đúng với khóa khai báo tại `spring.security.oauth2.client.registration`.

## 7. Các dependency phục vụ từng trách nhiệm

Không phải ứng dụng nào cũng cần đủ mọi chức năng OAuth2 trong một dự án:

| Nhiệm vụ | Starter chính | Điểm triển khai |
| --- | --- | --- |
| Người dùng đăng nhập bằng Google, Keycloak hoặc OIDC Provider | OAuth2 Client starter + MVC starter | `oauth2Login()`, client registration, session |
| Servlet backend gọi API bên ngoài thay người dùng đã đăng nhập | OAuth2 Client starter + MVC starter | `OAuth2AuthorizedClient` và client HTTP thích hợp |
| Batch job backend xin token bằng Client Credentials | OAuth2 Client starter; web starter tùy nhu cầu | `OAuth2AuthorizedClientManager` cho context không có Servlet request |
| API của mình xác minh Bearer Access Token | Resource Server starter (Servlet hoặc Reactive tùy API) | `oauth2ResourceServer()` và cấu hình JWT/opaque |
| Hệ thống cấp token, quản lý authorization endpoint | Authorization Server starter/cấu hình riêng | Phát hành token, quản lý client, policy |
| Cùng ứng dụng vừa login OIDC vừa bảo vệ một API nội bộ | Client starter và Resource Server starter thích hợp | Cần tách/định nghĩa rõ security chains, định dạng yêu cầu và chính sách |

### Client Credentials có cần Servlet starter không?

**Không nhất thiết.** Một batch process chỉ gọi API bằng OAuth2 Client có thể không cần Spring MVC hoặc Servlet container. Nhưng chủ đề bài là **OAuth2 Client cho ứng dụng Servlet**, vì thế ví dụ web login cần web starter tương ứng. Hãy chọn dependency theo kiến trúc ứng dụng, không theo tên giao thức đơn lẻ.

## 8. Quản lý version và dependency graph

### 8.1. Vì sao không nên tự chọn từng version?

Spring Boot BOM quản lý các nhóm thư viện Spring Security, Spring Framework, Jackson, Tomcat và nhiều dependency khác theo một tập đã được kiểm thử cùng nhau. Nếu khai báo trực tiếp:

~~~groovy
// Không khuyến nghị: trộn phiên bản độc lập so với BOM đang dùng.
implementation 'org.springframework.security:spring-security-oauth2-client:SOME_OTHER_VERSION'
~~~

bạn có thể tạo ra tổ hợp không tương thích với `spring-security-config`, `spring-security-web` hoặc Spring Framework. Lỗi có thể xuất hiện ở runtime dưới dạng `NoSuchMethodError` / `ClassNotFoundException`, dù compilation của một phần mã đã thành công.

Với Boot-managed project, dùng starter **không chỉ ngắn gọn mà còn giữ version nhất quán**. Chỉ override version khi có lý do cụ thể và đã đánh giá ảnh hưởng dependency tree.

### 8.2. Lệnh xem dependency thực tế

Gradle trong thư mục dự án:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

Trên Windows có thể dùng wrapper:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

Những lệnh này dùng để **kiểm tra sơ đồ phụ thuộc**, không phải thao tác cấu hình OAuth2 ở runtime. Nếu thiếu `spring-security-oauth2-client` trong runtime classpath, khả năng cao dự án chưa thêm đúng starter vào module chạy ứng dụng hoặc scope được cấu hình sai.

### 8.3. Phân biệt compile/runtime/test scope

Đối với OAuth2 Login, starter cần ở **runtime classpath** của ứng dụng:

- Gradle: dùng `implementation`, không phải `testImplementation`.
- Maven: dùng compile scope mặc định, không để `<scope>test</scope>`.
- `spring-security-test` hoặc security test starter dùng ở **test scope**.

Trong multi-module build, phải thêm dependency tại **module ứng dụng cần OAuth2 Client**, hoặc qua convention/plugin được cấu hình để module ấy nhận runtime dependency. Chỉ thêm ở một module library không được package vào executable JAR sẽ không giải quyết classpath của ứng dụng chạy thật.

## 9. Auto-configuration hoạt động khi có dependency

Khi Spring Boot phát hiện OAuth2 Client library và các thuộc tính `spring.security.oauth2.client.*`, Boot có thể tự tạo các thành phần như `ClientRegistrationRepository`. Trong một ứng dụng Servlet, Spring Security dùng chúng để điều phối login và authorized client.

| Thành phần | Ý nghĩa |
| --- | --- |
| `ClientRegistration` | Một cấu hình client: client ID, grant type, redirect URI, scope, provider endpoints |
| `ClientRegistrationRepository` | Tập cấu hình các client registration |
| `OAuth2AuthorizedClient` | Kết quả client đã được ủy quyền cho principal; có Access Token và có thể có Refresh Token |
| `OAuth2AuthorizedClientRepository` | Lưu/tải authorized client theo ngữ cảnh Servlet |
| `OAuth2AuthorizedClientService` | Abstraction lưu/tải authorized client ở tầng service |
| `OAuth2AuthorizedClientManager` | Điều phối lấy mới/làm mới token tùy provider và trạng thái |
| `OAuth2AuthenticationToken` | Authentication thể hiện OAuth2 Login thành công |
| `OidcUser` | Principal người dùng OIDC khi login với `openid` và token đã được xác minh |

Bạn **không cần tự tạo các bean mặc định chỉ vì đã thêm starter**. Khi luồng login tiêu chuẩn hoạt động, hãy dùng cơ chế sẵn có; chỉ tự cấu hình thêm nếu cần custom storage, provider, token refresh hay policy.

Để gọi downstream API, `oauth2Client()` và `OAuth2AuthorizedClientManager` có thể được dùng tùy ngữ cảnh. **Dependency không tự động thêm Bearer token vào mọi request HTTP**; phải dùng HTTP client/tích hợp được cấu hình để tìm authorized client, chọn đúng registration và gắn token cho đúng resource server.

## 10. Các lỗi thường gặp khi thiết lập dependency

### 10.1. Không có lớp `OAuth2AuthorizedClient` hoặc `OidcUser`

**Hiện tượng:** IDE báo không import được `org.springframework.security.oauth2.client.OAuth2AuthorizedClient` hoặc `org.springframework.security.oauth2.core.oidc.user.OidcUser`.

**Kiểm tra:** đúng starter đã có trong module ứng dụng chưa; dependency được đặt ở `implementation` / compile scope chưa; Gradle/Maven đã đồng bộ sau khi sửa build file chưa. Với Spring Boot 4, dùng tên starter mới nếu đang tạo project mới.

### 10.2. Dùng nhầm WebFlux trong bài Servlet

**Hiện tượng:** cấu hình `ServerHttpSecurity` nhưng chương trình là Tomcat/Spring MVC, bean không được áp dụng như mong đợi.

**Nguyên nhân:** đã import API reactive thay vì `HttpSecurity` / `SecurityFilterChain`. Chọn đúng stack; không thêm WebFlux starter chỉ để sửa lỗi import.

### 10.3. Chỉ thêm `spring-boot-starter-security`

**Hiện tượng:** ứng dụng bảo vệ URL bằng form login hoặc Basic Authentication, nhưng không có OAuth2 Client API/registration như mong đợi.

**Nguyên nhân:** starter Security cơ bản không thay thế OAuth2 Client starter. Hãy thêm OAuth2 Client starter đúng phiên bản.

### 10.4. Dùng Resource Server starter thay OAuth2 Client starter

**Hiện tượng:** chỉ có cấu hình nhận JWT Bearer token, không có luồng redirect tới IdP và callback.

**Nguyên nhân:** Resource Server bảo vệ API, OAuth2 Client khởi tạo đăng nhập/lấy token. Chọn starter theo trách nhiệm; thêm cả hai chỉ nếu ứng dụng thật sự đảm nhận cả hai.

### 10.5. Khởi động lỗi khi tải OIDC metadata

**Hiện tượng:** exception liên quan `issuer-uri`, discovery, kết nối HTTPS, TLS hoặc response metadata khi tạo client registration.

**Nguyên nhân:** issuer sai, provider không hoạt động, mạng/certificate không hợp lệ hoặc metadata không khớp. Đây thường là lỗi **cấu hình nhà cung cấp** sau khi dependency đã đúng, không phải thiếu OAuth2 Client starter.

### 10.6. Redirect URI mismatch

**Hiện tượng:** provider trả lỗi `redirect_uri_mismatch`, `invalid_redirect_uri` hoặc một mã lỗi tương tự.

**Nguyên nhân:** URI cấu hình tại provider khác URI Spring Security dùng. Kiểm tra scheme, hostname, port, context path, reverse proxy và `{baseUrl}`. Trong môi trường proxy, chỉ cấu hình forwarded headers khi có trusted proxy và chính sách phù hợp.

### 10.7. Thêm dependency nhưng không có login OAuth2

**Hiện tượng:** người dùng bị chuyển đến Basic/form login mặc định, hoặc không thấy link tới provider.

**Kiểm tra:** đã có registration (`client-id`, provider, scope, redirect URI) chưa; `SecurityFilterChain` có cấu hình `oauth2Login()` phù hợp không; URL bắt đầu login đúng `/oauth2/authorization/{registrationId}` không; có custom chain khác bắt request trước không.

### 10.8. Dự án Boot 4 vẫn copy nguyên hướng dẫn starter Boot 3

**Hiện tượng:** dự án sử dụng tên artifact cũ với cảnh báo deprecated, hoặc tài liệu và dependency graph khó đối chiếu.

**Cách xử lý:** trên Boot 4 mới, ưu tiên `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`. Không cần tự đổi version Spring Security để “hợp” với starter.

### 10.9. Lỗi javax/jakarta ở dự án cũ

Spring Boot 3/4 dựa trên hệ sinh thái **Jakarta**, ví dụ `jakarta.servlet.http.HttpServletRequest`. Nếu copy code dùng `javax.servlet.*` từ Spring Boot 2.x, ứng dụng có thể lỗi import hoặc xung đột runtime. Chuyển API phù hợp phiên bản Spring Boot; không thêm servlet API cũ để vá sự không tương thích.

## 11. Kiểm thử tối thiểu mà ứng dụng nên hỗ trợ

Khi dự án được chạy với IdP thử nghiệm hoặc cấu hình test phù hợp, bạn có thể quan sát quy trình:

| Thao tác | Kết quả mong đợi |
| --- | --- |
| Mở `http://localhost:8080/` | Trang công khai trả nội dung |
| Mở `http://localhost:8080/me` khi chưa login | Browser bắt đầu luồng xác thực |
| Mở `http://localhost:8080/oauth2/authorization/demo` | Chuyển đến authorization endpoint của provider |
| Đăng nhập thành công tại provider | Browser trở về `/login/oauth2/code/demo`, ứng dụng tạo Authentication/session |
| Gọi lại `/me` | Trả issuer/subject đã xác minh từ OIDC principal |
| Đăng nhập thành công nhưng gọi API ngoài bị `401`/`403` | Điều tra Access Token/audience/scope của API, không chỉ dependency |

Trong test code, Spring Security có thể mô phỏng principal với `spring-security-test` / test starter tương ứng; không nên thực hiện login thật qua Internet trong tất cả unit test. Các integration test end-to-end có thể dùng một IdP test hoặc môi trường tích hợp được cấu hình riêng.

**Các dấu hiệu trên chỉ xác nhận luồng thiết lập về mặt chức năng**, không chứng minh ứng dụng đã đáp ứng đầy đủ yêu cầu bảo mật production. Hệ thống thực tế còn cần kiểm soát HTTPS, cookie session, CSRF, secret rotation, proxy, logout và quyền API.

## 12. Ví dụ lựa chọn dependency theo yêu cầu

### Kịch bản A — Web MVC có đăng nhập doanh nghiệp bằng OIDC

Ứng dụng có controller và trang hồ sơ; người dùng đăng nhập qua provider. Chọn Servlet web starter + OAuth2 Client starter, khai báo registration với `openid`, cấu hình `oauth2Login()`. Có thể thêm Thymeleaf nếu cần template UI.

### Kịch bản B — Backend Servlet vừa login vừa gọi API thay người dùng

Giữ bộ dependency ở kịch bản A, dùng `OAuth2AuthorizedClient` và cơ chế authorized client manager để lấy Access Token khi gọi API. **Phải đảm bảo token có audience/scope đúng cho API đích**; việc OIDC login thành công không tự làm token dùng được cho mọi hệ thống.

### Kịch bản C — API của mình chỉ nhận Bearer JWT

Nếu ứng dụng không cần redirect browser sang IdP và không xin token để gọi hệ thống khác, OAuth2 Client starter có thể không cần. Nhiệm vụ này phù hợp với Resource Server starter.

### Kịch bản D — Scheduled job gọi API bằng client credentials

Nếu không có web UI, thường không cần Servlet web starter. Dùng OAuth2 Client starter với registration `client_credentials` và manager phù hợp ngữ cảnh service/background, không cấu hình `oauth2Login()` như một bước bắt buộc.

### Kịch bản E — Đang nâng cấp từ Boot 3 lên Boot 4

Cập nhật bản Spring Boot/Java/build tool theo yêu cầu nâng cấp, sau đó dùng starter tên mới cho MVC và OAuth2 Client. Kiểm tra compatibility của những dependency khác theo BOM, thay imports `javax.servlet` cũ còn sót, rồi kiểm tra lại cấu hình đăng nhập. Việc đổi tên starter là một phần của migration chứ không thay thế toàn bộ công việc nâng cấp.

## 13. Nguồn tài liệu tham khảo

- **Spring Boot — Build Systems / Starters:** https://docs.spring.io/spring-boot/reference/using/build-systems.html
- **Spring Boot — Spring Security and OAuth2 Client auto-configuration:** https://docs.spring.io/spring-boot/reference/web/spring-security.html
- **Spring Security — Servlet OAuth2 Client / OAuth2 Login:** https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- **Spring Boot — Modularizing Spring Boot (đổi tên starter ở Boot 4):** https://spring.io/blog/2025/10/28/modularizing-spring-boot

## 14. Kết luận thực hành

Đối với **Spring Boot Servlet OAuth2/OIDC Client**, cấu hình dependency tối thiểu là **Servlet MVC starter + OAuth2 Client starter đúng nhánh Boot**:

~~~text
Spring Boot 3:
  spring-boot-starter-web
  spring-boot-starter-oauth2-client

Spring Boot 4:
  spring-boot-starter-webmvc
  spring-boot-starter-security-oauth2-client
~~~

Sau khi có dependency, ứng dụng vẫn cần **Client Registration**, **Authorization Server/OIDC Provider**, các **scope** phù hợp và **SecurityFilterChain** cho Servlet. Starter giúp đưa đúng thư viện và cấu hình mặc định vào classpath; ứng dụng chịu trách nhiệm thiết kế quyền, phiên đăng nhập, lưu trữ token và endpoint theo nhu cầu thực tế.
