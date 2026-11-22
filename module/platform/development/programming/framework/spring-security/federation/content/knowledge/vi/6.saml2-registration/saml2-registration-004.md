# Cấu hình spring.security.saml2.relyingparty.registration trong Spring Boot

> **Module:** Spring Security – federation · **Chủ đề:** Đăng ký SAML2. Bài học hướng dẫn cách khai báo mối quan hệ giữa **Service Provider (SP)/Relying Party (RP)** là ứng dụng Spring Boot và **Identity Provider (IdP)/Asserting Party** bằng nhánh cấu hình `spring.security.saml2.relyingparty.registration`, từ trường hợp tối giản dùng IdP metadata đến cấu hình thủ công, chứng thư số, nhiều IdP và kiểm chứng đăng nhập.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Đọc được toàn bộ đường dẫn `spring.security.saml2.relyingparty.registration.<registrationId>` trong `application.yml` và giải thích từng cấp.
2. Phân biệt **SP entity ID**, **IdP entity ID**, **ACS URL**, **IdP SSO URL**, **metadata URL**, **registrationId** và **X.509 certificate**.
3. Chọn đúng hai cách khai báo: **dựa vào metadata của IdP** hoặc **khai báo các trường IdP thủ công**.
4. Thiết lập **verification credential** của IdP, **signing credential** của SP và **decryption credential** của SP theo đúng chiều tin cậy.
5. Hiểu vai trò của Spring Boot auto-configuration, `RelyingPartyRegistrationRepository`, `SecurityFilterChain` và `saml2Login()`.
6. Tạo ứng dụng Java 17 + Spring Boot 3.3.x có endpoint SAML2 login và SP metadata; tích hợp khi đã có IdP thật.
7. Cấu hình nhiều đối tác, bảo đảm đúng `registrationId`, ACS và entity ID sau reverse proxy, kiểm tra lỗi thường gặp mà không nới kiểm tra bảo mật.

**Phạm vi:** Ví dụ là **Spring MVC/Servlet SP**. Ứng dụng không phát hành assertion và không trở thành IdP. Tên thuộc tính tham chiếu **Spring Boot 3.3.x / Spring Security 6.x**; ở phiên bản khác phải tra lại reference tương ứng, vì API Java và tên một số mục đã thay đổi theo thời gian.

## 2. Bài toán: một SP cần biết tin IdP nào

Giả sử ứng dụng `https://orders.example.org` cho nhân viên Công ty A đăng nhập bằng IdP của A. Ứng dụng cần biết:

- **Ai là IdP?** Entity ID và chứng thư xác minh chữ ký SAML Response/Assertion.
- **Gửi AuthnRequest đi đâu?** SSO service URL và HTTP binding (Redirect hay POST) của IdP.
- **SP tự nhận mình là ai?** SP entity ID mà IdP dùng làm audience/trust entry.
- **IdP phải trả kết quả về đâu?** Assertion Consumer Service (ACS URL) của SP.
- **Có yêu cầu ký AuthnRequest hoặc giải mã assertion không?** Nếu có, SP cần private key và certificate phù hợp.
- **Cấu hình nào là của đối tác A?** Mỗi cặp SP–IdP được nhận diện bằng một `registrationId`.

Spring Boot đưa những thông tin này vào cây cấu hình:

~~~text
spring
└── security
    └── saml2
        └── relyingparty
            └── registration
                ├── partner-a                  <-- registrationId (tên do SP đặt)
                │   ├── entity-id              <-- entity ID của SP
                │   ├── acs                    <-- nơi SP nhận SAMLResponse
                │   ├── signing                <-- khóa SP dùng để ký
                │   ├── decryption             <-- khóa SP dùng để giải mã
                │   ├── singlelogout           <-- tùy chọn SLO của SP
                │   └── assertingparty
                │       ├── metadata-uri       <-- metadata phía IdP
                │       ├── entity-id          <-- entity ID của IdP
                │       ├── sso-url            <-- SSO endpoint của IdP
                │       ├── verification       <-- certificate công khai của IdP
                │       └── singlelogout       <-- tùy chọn SLO của IdP
                └── partner-b                  <-- registration thứ hai
                    └── assertingparty...
~~~

Các nhánh con được dùng **tùy nhu cầu và phương án cấu hình**; không cần nhập tất cả khi metadata đã cung cấp đủ thông tin và IdP không yêu cầu khóa riêng của SP.

### Các vai trò và định danh

| Tên | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `registrationId` | Khóa nội bộ để Spring nhận diện **một cặp RP–IdP**; xuất hiện trong URL mặc định. | `partner-a` |
| **SP/RP entity ID** | Danh tính giao thức mà **ứng dụng** đăng ký với IdP; IdP dùng làm audience khi phát assertion. | `https://orders.example.org/saml2/service-provider-metadata/partner-a` |
| **IdP/Asserting Party entity ID** | Danh tính giao thức của đối tác phát assertion; SP phải kiểm tra issuer khớp IdP tin cậy. | `https://login.partner-a.example.org/saml/metadata` |
| **ACS URL** | URL HTTP của SP nhận `SAMLResponse` từ IdP. | `https://orders.example.org/login/saml2/sso/partner-a` |
| **IdP SSO URL** | Endpoint của IdP nhận yêu cầu `AuthnRequest`. | `https://login.partner-a.example.org/sso` |
| **IdP metadata URI** | Vị trí tải XML SAML metadata chứa entity ID, services, bindings và certificates của IdP. | `https://login.partner-a.example.org/metadata.xml` |
| **IdP verification certificate** | Chứng thư **công khai của IdP** mà SP tin để xác minh chữ ký. | `classpath:certs/partner-a-idp.crt` |
| **SP signing key/certificate** | Khóa riêng/cert của **SP** dùng để ký thông điệp gửi đi khi giao thức/IdP yêu cầu. | `file:/run/secrets/sp-sign.key` |
| **SP decryption key/certificate** | Khóa riêng/cert của **SP** để giải mã dữ liệu SAML gửi cho SP nếu IdP mã hóa. | `file:/run/secrets/sp-decrypt.key` |

Đây là các loại định danh khác nhau. **Registration ID không phải SAML entity ID; metadata URL không nhất thiết bằng SSO URL; ACS URL không phải IdP callback của OIDC.** Các URL `example.org` chỉ là địa chỉ minh họa.

## 3. Điều kiện tiên quyết để cấu hình hoạt động

Một SP đăng nhập SAML2 cần đủ **ba bên cấu hình khớp nhau**: Spring Boot, IdP và hạ tầng mạng.

1. Ứng dụng có dependency `spring-security-saml2-service-provider` và cấu hình `SecurityFilterChain` bật `saml2Login`.
2. IdP thật đã được quản trị viên đăng ký SP, nhận SP entity ID, ACS URL, binding, chứng thư ký của SP nếu yêu cầu, policy về NameID và ký/mã hóa assertion.
3. SP biết metadata hoặc endpoint/chứng thư công khai tin cậy của IdP; ngày giờ và chứng thư còn hợp lệ, DNS/TLS cho metadata/SSO hoạt động.
4. URL phía ngoài phải đúng với nơi browser thật truy cập; khi có reverse proxy, xử lý forwarded headers có kiểm soát.
5. Môi trường Java và Gradle tương thích; ví dụ phần sau dùng **Java 17+, Spring Boot 3.3.x, Spring Security 6.x**, ứng dụng Servlet.

SAML2 là giao thức liên kết hệ thống. **Chỉ thêm YAML không tạo được một IdP, chứng thư thực hay tài khoản liên kết**. Vì vậy ví dụ build độc lập có thể biên dịch, còn việc login thành công phụ thuộc IdP đã đăng ký và dữ liệu môi trường thật.

## 4. Cấu hình tối giản: lấy metadata từ IdP

**Ưu tiên IdP metadata** khi đối tác cung cấp nguồn metadata đáng tin cậy và định dạng được Spring Security xử lý.

Trong `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Sau khi đặt biến môi trường `PARTNER_A_IDP_METADATA_URI` thành địa chỉ metadata thực, Spring Boot có thể dựng registration từ metadata đó: IdP entity ID, SSO service location/binding và verifying certificates. SP vẫn cần được khai báo **ở phía IdP** với entity ID và ACS phù hợp. Nếu metadata không tải được, chứa nhiều cấu hình không phù hợp, hoặc IdP muốn profile khác, cần điều chỉnh cấu hình hoặc dùng registration Java tùy biến.

**Không chọn metadata URI từ query parameter của người dùng.** Ứng dụng chỉ nên tải từ nguồn IdP đã xác định trước trong hợp đồng tin cậy; truy xuất metadata qua HTTPS và xác minh tính đáng tin cậy của nguồn/đối tượng nhận, đặc biệt khi có signing metadata và certificate rotation.

Cấu hình metadata là **thông tin về IdP**, không phải bản chứng minh rằng mọi response từ URL ấy đều hợp lệ. Khi login, SP vẫn phải kiểm tra chữ ký trên đúng phần tử, issuer, audience, recipient/ACS, trạng thái, thời hạn và request correlation theo profile SAML.

### 4.1. Các URL mặc định quan trọng

Khi dùng `registrationId=partner-a`, những đường dẫn Spring Security Servlet thường thấy:

| Chức năng | Đường dẫn mặc định | Tác dụng |
| --- | --- | --- |
| Khởi tạo SP-initiated SSO | `GET /saml2/authenticate/partner-a` | Tạo AuthnRequest, chuyển browser đến IdP. |
| Nhận response (ACS) | `POST /login/saml2/sso/partner-a` | Xử lý form chứa `SAMLResponse` từ IdP. |
| Xuất SP metadata | `GET /saml2/metadata/partner-a` | Cung cấp metadata RP nếu bật `saml2Metadata()`. |
| Đường dẫn metadata tương thích | `GET /saml2/service-provider-metadata/partner-a` | Một endpoint metadata được Spring Security hỗ trợ. |
| Trang login của Spring Security | `GET /login` | Có thể cung cấp lựa chọn đăng nhập khi filter/registration được cấu hình. |

Đường dẫn là **path của ứng dụng**; URL thực có scheme, host, port, reverse proxy và context path. ACS cũng phải khớp entry của IdP, không phải chỉ khớp path nội bộ trên container.

### 4.2. Mặc định của SP entity ID và ACS

Spring Security mặc định xây SP entity ID dạng:

~~~text
{baseUrl}/saml2/service-provider-metadata/{registrationId}
~~~

ACS mặc định thường là:

~~~text
{baseUrl}/login/saml2/sso/{registrationId}
~~~

Với base URL `https://orders.example.org` và registration `partner-a`, SP entity ID là `https://orders.example.org/saml2/service-provider-metadata/partner-a`; ACS là `https://orders.example.org/login/saml2/sso/partner-a`.

**Entity ID là định danh logic của thực thể**, có thể trông giống một URL nhưng không được coi mặc nhiên là endpoint mà browser cần gọi. **ACS là URL thật phải nhận HTTP request**, còn `Destination`/`Recipient` trong response cần ràng buộc đúng đến endpoint ấy. Trong thực tế, SP entity ID có thể do chính sách IdP yêu cầu là URI cố định khác với URL metadata.

## 5. Cấu hình tường minh để khớp hợp đồng SP–IdP

Khi cần cố định SP entity ID và ACS thay vì dựa vào base URL động, khai báo rõ ràng:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Các `{baseUrl}` và `{registrationId}` là **URI template của Spring Security**, không phải placeholder của shell; chúng được mở rộng theo request và registration. `${PARTNER_A_IDP_METADATA_URI}` sau thay thế ký hiệu sẽ là **Spring property placeholder lấy biến môi trường**, phân biệt với URI template. Ví dụ trong hệ thống cần entity ID **cố định** bất kể host, thay `entity-id` bằng giá trị SP mà IdP đã đăng ký; sửa ACS cho đúng endpoint public. Không đổi tùy tiện sau khi tích hợp vì IdP sẽ phát assertion cho audience/callback cũ.

Ý nghĩa:

| Nhánh trong registration | Phía sở hữu | Khi nào nên tùy chỉnh? |
| --- | --- | --- |
| `entity-id` | SP | Khi IdP yêu cầu một SP entity ID cụ thể, không dùng mặc định. |
| `acs.location` | SP | Khi ACS có path/host cố định hoặc khác đường dẫn mặc định. |
| `acs.binding` | SP | Khi cần chỉ định POST/Binding tương ứng với cấu hình IdP và filter. |
| `assertingparty.metadata-uri` | IdP | Khi IdP công bố metadata tin cậy. |
| `signing.credentials` | SP | Khi SP phải ký AuthnRequest hoặc SLO messages. |
| `decryption.credentials` | SP | Khi IdP mã hóa assertion/name ID bằng public key của SP. |
| `singlelogout` | SP và/hoặc IdP | Khi hai phía đã thống nhất SAML Single Logout và cấu hình các endpoint/binding. |

Nếu thay đổi ACS để chạy qua custom URL, chỉ đổi YAML **chưa chắc đủ**: HTTP filter phải nhận request tại URL mới. Khi tùy biến sâu đường dẫn ACS, cần điều chỉnh `Saml2WebSsoAuthenticationFilter`/`SecurityFilterChain` tương ứng thay vì chỉ thay metadata.

## 6. Cấu hình thủ công khi không dùng metadata URI

Không phải IdP nào cũng cung cấp URL metadata sử dụng được trong mọi môi trường. Spring Boot 3.3.x cho phép đặt các thành phần IdP trực tiếp:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "https://orders.example.org/saml2/sp/partner-a"
            acs:
              location: "https://orders.example.org/login/saml2/sso/partner-a"
              binding: POST
            assertingparty:
              entity-id: "https://login.partner-a.example.org/saml"
              sso-url: "https://login.partner-a.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/partner-a-idp.crt"
~~~

Đây là **các giá trị mô phỏng** để học cấu trúc; cần thay bằng dữ liệu thực được IdP cấp và xác minh. `classpath:certs/partner-a-idp.crt` yêu cầu file tồn tại ở `src/main/resources/certs/partner-a-idp.crt` (đây là **certificate công khai của IdP**, không phải khóa riêng).

Những điểm cần chú ý:

- **`assertingparty.entity-id`** là issuer/EntityID mà response/assertion từ IdP phải khớp. Không lấy SP entity ID nhét vào trường này.
- **`assertingparty.sso-url`** chỉ tới Single Sign-On Service endpoint của **IdP**. Nó khác metadata URI và khác ACS.
- **`assertingparty.verification.credentials[*].certificate-location`** là chứng thư công khai đã được SP pin/tin cậy; không lấy certificate tùy ý bên trong SAMLResponse làm trust anchor.
- Nếu IdP dùng HTTP-Redirect hay HTTP-POST cho AuthnRequest, phải phối hợp đúng binding mà metadata/registration xác định. Không tự giả định mọi IdP chỉ dùng Redirect.
- **Cấu hình thủ công cần quy trình xoay chứng thư**. Khi IdP đổi signing key mà SP vẫn pin cert cũ, login sẽ không hợp lệ; không giải quyết bằng cách tắt signature validation.

Với Spring Boot 3.3, tham chiếu cấu hình thủ công ở tài liệu của phiên bản ấy dùng `sso-url` dưới `assertingparty`; ví dụ ở một số bản tham khảo Spring Security thế hệ khác trình bày `singlesignon.url`. Khi mang cấu hình giữa các phiên bản, kiểm tra đúng phiên bản Spring Boot và class `Saml2RelyingPartyProperties` đang chạy trước khi sao chép property.

### 6.1. Properties và YAML tương đương

Hai ví dụ này có ý nghĩa như nhau với Spring Boot property binding:

~~~properties
spring.security.saml2.relyingparty.registration.partner-a.assertingparty.entity-id=https://login.partner-a.example.org/saml
spring.security.saml2.relyingparty.registration.partner-a.assertingparty.sso-url=https://login.partner-a.example.org/sso
spring.security.saml2.relyingparty.registration.partner-a.assertingparty.verification.credentials[0].certificate-location=classpath:certs/partner-a-idp.crt
~~~

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              entity-id: "https://login.partner-a.example.org/saml"
              sso-url: "https://login.partner-a.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/partner-a-idp.crt"
~~~

Danh sách `credentials` là **list**, vì có thể cần nhiều certificates hợp lệ trong quá trình key rotation. Đừng đổi thành một string chứa nhiều đường dẫn và hy vọng binder tự phân tích theo cách phù hợp.

## 7. Ba loại credentials thường bị nhầm

SAML dùng chứng thư X.509 và khóa tương ứng để ký/xác minh hoặc mã hóa/giải mã. Tách rõ **ai cầm private key**:

| Tác vụ | Trường Spring Boot 3.3 | Khóa/cert thuộc về ai? | Để làm gì? |
| --- | --- | --- | --- |
| SP xác minh chữ ký response/assertion | `assertingparty.verification.credentials` | **Public certificate của IdP** | Tin vào chữ ký của IdP đã đăng ký. |
| SP ký AuthnRequest/SLO | `signing.credentials` | **Private key và certificate của SP** | IdP xác minh thông điệp từ SP nếu yêu cầu. |
| SP giải mã encrypted assertion/NameID | `decryption.credentials` | **Private key và certificate của SP** | Mở dữ liệu đã được mã hóa cho SP. |

### 7.1. Khi IdP yêu cầu ký AuthnRequest

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/secrets/sp-signing.crt"
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

- `private-key-location` trỏ tới **private key của SP**. Giữ ở nơi quản lý bí mật; không commit key vào Git, container image, artifact phát hành hoặc tài liệu.
- `certificate-location` là certificate tương ứng mà IdP tin, thường phải được cung cấp qua SP metadata hoặc đăng ký thủ công.
- Có signing credentials **không có nghĩa mọi loại message đều tự động được ký trong mọi tình huống**. Spring Security quyết định tạo chữ ký dựa vào cấu hình và nhu cầu giao thức/IdP; cần kiểm chứng trên request thật và yêu cầu chữ ký của đối tác.

### 7.2. Khi IdP gửi EncryptedAssertion

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/sp-decrypt.key"
                  certificate-location: "file:/run/secrets/sp-decrypt.crt"
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

IdP dùng **public key** của SP để mã hóa; SP dùng **private key** để giải mã. **Giải mã thành công không thay thế kiểm tra chữ ký** của assertion/response. Cấu hình encryption của đối tác phải khớp thuật toán, key usage, certificate được công bố cho SP và khả năng xử lý của thư viện.

### 7.3. Kết hợp signing và decryption

Một triển khai có thể dùng cùng một key pair nếu chính sách cho phép, nhưng thực tế nên đánh giá rủi ro và quy trình xoay khóa riêng cho các mục đích. Ví dụ kết hợp **sẽ có cấu trúc**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/secrets/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/sp-decrypt.key"
                  certificate-location: "file:/run/secrets/sp-decrypt.crt"
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Chỉ bật những nhánh thực sự cần. Dùng HTTPS, certificate rotation theo kế hoạch và chính sách xử lý failure an toàn. Việc thêm key vào YAML không tự khiến IdP biết public certificate tương ứng: **đăng ký SP metadata/certificate ở IdP** vẫn là bước bắt buộc.

## 8. Ví dụ ứng dụng Spring Boot hoàn chỉnh (Java 17+)

Ví dụ hướng tới một chương trình **có thể biên dịch và chạy khi cấu hình IdP có thực**. Nó minh họa giao diện Spring Security SAML2, không cố tự viết XML parser hoặc giả lập chữ ký SAML.

### 8.1. Cấu trúc dự án

~~~text
saml-registration-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlregistration/
    │   ├── SamlRegistrationApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── resources/
        └── application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-registration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // Repository chứa một số dependency OpenSAML của hệ sinh thái Shibboleth.
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Lý do các dependency:

- `spring-boot-starter-web`: runtime Servlet và REST endpoint.
- `spring-boot-starter-security`: filter chain, session security và authorization.
- `spring-security-saml2-service-provider`: AuthnRequest, response processing, metadata và integration OpenSAML.
- Shibboleth Maven Repository: có thể cần để resolve một số artifact OpenSAML theo hướng dẫn Spring Security phù hợp version.

Không thêm `spring-security-oauth2-client` để bật SAML2. OIDC/OAuth2 Client là giao thức/DSL khác với `saml2Login`.

### 8.2. Lớp main

`src/main/java/com/example/samlregistration/SamlRegistrationApplication.java`:

~~~java
package com.example.samlregistration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlRegistrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlRegistrationApplication.class, args);
    }
}
~~~

### 8.3. Cấu hình SecurityFilterChain

`src/main/java/com/example/samlregistration/SecurityConfig.java`:

~~~java
package com.example.samlregistration;

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
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Tác dụng:

1. `saml2Login` cài đặt flow SAML2 Service Provider trên HTTP filter chain.
2. `saml2Metadata` xuất SP metadata để đăng ký với IdP. Nếu bỏ dòng này, **không mặc định kết luận metadata endpoint đã được publish**.
3. Rule `authenticated()` buộc những endpoint khác đăng nhập, nhưng **không có nghĩa đã có quyền nghiệp vụ**.
4. Spring Security tự xử lý request/callback theo cấu hình. Không tạo controller nhận `SAMLResponse` và tự parse XML vì dễ bỏ sót signature/recipient/audience validation.

Mẫu trên cố tình **không tắt CSRF, signature validation, issuer validation hoặc filter mặc định**. Nếu gặp 403 ở ACS, cần kiểm tra cấu hình filter, request và binding, không tắt `csrf()` toàn cục như cách chữa tạm.

### 8.4. Quan sát principal sau login

`src/main/java/com/example/samlregistration/DemoController.java`:

~~~java
package com.example.samlregistration;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Public endpoint. Open /private to start SAML 2.0 login.";
    }

    @GetMapping("/private")
    public Map<String, Object> privatePage(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("nameId", principal.getName());
        response.put("registrationId",
            principal.getRelyingPartyRegistrationId());
        response.put("department",
            principal.getFirstAttribute("department"));
        return response;
    }
}
~~~

Với đăng nhập thật thành công, `Saml2AuthenticatedPrincipal` là principal mà Spring Security cung cấp từ assertion đã được xử lý. `registrationId` giúp biết người dùng đến từ đăng ký IdP nào. Attribute `department` tùy IdP có gửi hay không nên có thể là `null` trong `LinkedHashMap`. Không trả nguyên SAML Response, raw assertion hoặc thông tin nhạy cảm qua endpoint debug ở production.

### 8.5. application.yml cho chương trình mẫu

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Dùng cách đơn giản nhất trước. Sau khi xác nhận SP login thành công, nếu IdP yêu cầu ký AuthnRequest, decrypt assertion hoặc cố định ACS/entity ID, bổ sung các nhánh ở mục 5–7 theo thỏa thuận.

**Không tự gắn** `http://localhost:8080/login/saml2/sso/partner-a` vào IdP production nếu browser không thể truy cập localhost của máy phát triển. Cho local integration cần tunnel/host hoặc IdP test cho phép đúng redirect/ACS và cấu hình URL thực, không dùng bypass validation.

### 8.6. Chạy thử

Với Java 17 và Gradle tương thích (hoặc Gradle Wrapper phù hợp nếu dự án có sẵn):

~~~bash
gradle bootRun
~~~

Biến môi trường `PARTNER_A_IDP_METADATA_URI` **phải trỏ tới URL metadata thực** mà runtime Spring Boot truy cập được. Nếu IdP cấu hình/tài nguyên hợp lệ:

1. Mở `http://localhost:8080/` để kiểm tra endpoint công khai. Phản hồi chính xác của controller là:
   
   ~~~text
   Public endpoint. Open /private to start SAML 2.0 login.
   ~~~

2. Mở `http://localhost:8080/saml2/metadata/partner-a`, kiểm tra XML SP metadata phản ánh entity ID và ACS dự kiến. Cần xem **trường XML**, không chỉ HTTP 200.
3. Cung cấp SP metadata/entity ID/ACS cho quản trị viên IdP và bảo đảm đúng đối tác `partner-a`.
4. Mở `http://localhost:8080/private` khi chưa đăng nhập. Spring Security bắt đầu SP-initiated flow, đưa browser tới IdP, IdP trả SAMLResponse tới ACS.
5. Khi assertion có chữ ký hợp lệ, thời hạn/correlation/audience/recipient khớp, ứng dụng tạo phiên và trả JSON ở `/private`. `nameId`, `department` phụ thuộc IdP nên **không có JSON cố định**.
6. Truy cập lại `/private` trong cùng phiên SP để thấy kết quả còn được nhận diện theo session.

**Nếu chưa có IdP thực**, ví dụ vẫn trình bày code và cấu hình, nhưng không thể chứng minh SAML login thành công chỉ bằng chạy `gradle bootRun`. Nếu metadata không tải được, ứng dụng có thể thất bại ngay khi tạo `RelyingPartyRegistrationRepository`; phải dùng metadata hợp lệ trước.

## 9. Đăng ký SP với IdP: quy trình hai chiều

Cấu hình Spring Boot mới chỉ là **một nửa** tích hợp. Quy trình triển khai thực:

| Bước | Thực hiện phía nào? | Cần xác nhận điều gì? |
| --- | --- | --- |
| 1. Lấy metadata IdP đáng tin cậy | IdP → SP | Entity ID, SSO URL, bindings, certificates, trust và key rotation. |
| 2. Tạo registration trong Spring | SP | `registrationId`, đúng nguồn metadata, endpoint/certificate. |
| 3. Cấp SP metadata cho đối tác | SP → IdP | SP entity ID, ACS, supported bindings, signing/encryption cert nếu dùng. |
| 4. Đăng ký SP application | IdP | Audience/recipient/ACS khớp, name ID format, ký AuthnRequest/Assertion. |
| 5. Kiểm tra HTTP flow thật | Browser + SP + IdP | AuthnRequest đi đúng IdP; response về đúng ACS; request correlation có hiệu lực. |
| 6. Kiểm tra xác thực và quyền | SP | Xác minh SAML hợp lệ; map local account/quyền riêng; deny khi thiếu quyền. |
| 7. Giám sát và vận hành | Hai phía | Xoay cert, thay metadata, clock skew, outage và ngừng cấp tài khoản. |

### Các câu hỏi phải hỏi IdP trước khi cấu hình

- IdP có **metadata URI** hay cần pin certificate thủ công? Nguồn metadata được bảo vệ/duy trì ra sao?
- IdP yêu cầu ký **AuthnRequest** không? Đã nhận certificate SP chưa?
- IdP ký **Response, Assertion hay cả hai**? SP phải xác minh đúng profile và chính sách.
- IdP sẽ gửi **EncryptedAssertion** hoặc **EncryptedID** không? SP cần decryption key nào?
- IdP hỗ trợ HTTP-Redirect/POST binding nào? ACS endpoint, entity ID và SLO URL chính xác là gì?
- NameID format, thuộc tính tối thiểu và cơ chế thay đổi/thu hồi người dùng ra sao?
- Cần **SP-initiated SSO** hay hỗ trợ IdP-initiated; chính sách `InResponseTo` và replay áp dụng thế nào?

Không tự đổi authn request/callback requirement theo “đăng nhập được là đủ”. Những khác biệt phải được diễn đạt trong hợp đồng tích hợp rõ ràng.

## 10. Hai IdP: hai registration ID độc lập

Một Spring Boot SP có thể tin **nhiều IdP**. Ví dụ hai đối tác:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
          partner-b:
            assertingparty:
              metadata-uri: ${PARTNER_B_IDP_METADATA_URI}
~~~

Khi ấy:

~~~text
/saml2/authenticate/partner-a
/saml2/authenticate/partner-b

/login/saml2/sso/partner-a
/login/saml2/sso/partner-b

/saml2/metadata/partner-a
/saml2/metadata/partner-b
~~~

**Registration ID phải duy nhất trong repository.** Nó là một namespace nội bộ giúp chọn cặp SP–IdP; hai nguồn metadata/cert phải không bị tráo đổi. Đừng để trình duyệt tự chỉ định metadata URL/certificate tin cậy qua request. Việc người dùng chọn đối tác trên giao diện có thể quyết định **một registration có sẵn**, không được tạo ngẫu nhiên trust anchor từ URL ngoài.

**Cẩn thận với phân quyền đa tenant:** IdP A và IdP B có thể phát cùng chuỗi NameID. Local account nên liên kết theo **IdP entity ID/registration tin cậy + NameID + ngữ cảnh format/qualifiers**, rồi kiểm tra partner/tenant và permission riêng. Việc SAML authentication thành công không làm người dùng thành quản trị viên của ứng dụng.

### 10.1. Xem registration hiệu lực bằng Java

Trong môi trường phát triển, thay vì suy đoán config đã bind, có thể thêm một bean kiểm tra vào ứng dụng **nếu được phép log các thông tin không nhạy cảm**. Mã dưới đây minh họa cách đọc repository đã được Boot tạo.

~~~java
package com.example.samlregistration;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;

@Configuration
public class RegistrationDiagnostics {

    @Bean
    ApplicationRunner verifyRegistration(
            RelyingPartyRegistrationRepository repository) {
        return (ApplicationArguments ignored) -> {
            RelyingPartyRegistration registration =
                repository.findByRegistrationId("partner-a");

            if (registration == null) {
                throw new IllegalStateException(
                    "Missing SAML registration: partner-a");
            }

            System.out.println("SAML registration = "
                + registration.getRegistrationId());
            System.out.println("SP entity ID = "
                + registration.getEntityId());
            System.out.println("ACS = "
                + registration.getAssertionConsumerServiceLocation());
        };
    }
}
~~~

Nếu thêm class này vào package `com.example.samlregistration`, nó dùng Spring Boot `ApplicationRunner` để đọc registration. Với cấu hình mặc định, kết quả có **`SAML registration = partner-a`**, còn `SP entity ID`/`ACS` có thể chứa URI template cho tới lúc được phân giải trong ngữ cảnh request. Đừng dùng đoạn diagnostics để in private key, raw assertion hoặc certificate nhạy cảm ra log. Trong production, thường không cần bean này.

**Lưu ý:** `RelyingPartyRegistrationRepository` chỉ cho phép tìm bằng ID theo giao diện. Nếu muốn liệt kê mọi registration, cần repository tương thích `Iterable` hoặc một kho quản trị riêng; không tự giả định mọi implementation hỗ trợ iteration.

## 11. Khi nào cấu hình bằng Java thay vì application.yml?

YAML phù hợp khi số IdP nhỏ, cấu hình ổn định, metadata công bố rõ và không cần logic tùy biến. Java bean thường cần khi:

- Đăng ký IdP nằm trong database hay config service, cần chọn theo tenant/registration một cách kiểm soát.
- Cần bổ sung tiêu chuẩn tin cậy về metadata, kiểm tra certificate hoặc chiến lược refresh/rotation riêng.
- Cần tùy biến URI/endpoint hoặc thuộc tính SAML mà cấu hình Boot không trình bày đầy đủ.
- Cần phối hợp nhiều registration có chính sách signing/decryption khác nhau.
- Cần thay đổi cách resolve registration theo request mà không cho request tự tạo trust anchor.

Ví dụ dùng metadata URL do **hệ thống quản trị cấu hình trước**:

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class ManualSamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration registration =
            RelyingPartyRegistrations
                .fromMetadataLocation(
                    "https://idp.partner-a.example.org/metadata.xml")
                .registrationId("partner-a")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

**Đây là phương án thay thế** cho `application.yml` registration khi ứng dụng cần quản lý qua Java. Đừng đồng thời thêm class bean này và giả định Spring Boot sẽ tự hợp nhất mọi registration trong YAML vào bean thủ công: **bean `RelyingPartyRegistrationRepository` do bạn khai báo khiến auto-configuration repository tương ứng lùi lại**. Muốn hợp nhất, bạn phải thực hiện rõ trong code.

Địa chỉ `idp.partner-a.example.org` minh họa; đổi thành metadata thật để chạy. Với ứng dụng chỉ dùng YAML, **không cần** bean Java này.

### 11.1. Cẩn thận với metadata cập nhật

Một registration được dựng từ metadata lúc startup **không bảo đảm tự cập nhật theo mỗi key rotation của IdP**. Phải xem cơ chế refresh thực tế của repository/version đang sử dụng và vận hành metadata/certificate refresh có kiểm chứng. Nếu metadata bị hỏng hoặc chưa đến hạn xoay mà cert đột ngột thay đổi, hệ thống cần cảnh báo rõ và thất bại an toàn; không fallback sang “chấp nhận bất kỳ chứng thư”.

### 11.2. SAML metadata không phải OAuth discovery

| Cơ chế | SAML2 | OIDC |
| --- | --- | --- |
| Cấu hình client | `spring.security.saml2.relyingparty.registration` | `spring.security.oauth2.client.registration/provider` |
| Metadata/discovery | XML SAML metadata, entity descriptors, certificates, SSO services | JSON OpenID Provider discovery, issuer, endpoints, JWKS |
| Principal | `Saml2AuthenticatedPrincipal` | `OidcUser` |
| Login DSL | `saml2Login` | `oauth2Login` |
| Callback mặc định | `/login/saml2/sso/{registrationId}` | `/login/oauth2/code/{registrationId}` |

Không dùng OIDC `issuer-uri` dưới SAML `assertingparty` và không thay XML SAML metadata bằng OIDC discovery endpoint. Chúng có các định dạng, tham số và cơ chế xác minh khác nhau.

## 12. Deploy sau reverse proxy: base URL quyết định cấu hình

Ở local, một request có thể tới `http://localhost:8080`. Khi deploy:

~~~text
Trình duyệt
  |
  | https://orders.example.org/private
  v
Trusted ingress / reverse proxy (TLS termination)
  |
  | http://orders-service:8080/private
  v
Spring Boot app
~~~

Nếu ứng dụng dựng SP entity ID/ACS từ URL nội bộ `http://orders-service:8080`, trong khi IdP đăng ký `https://orders.example.org`, có thể xuất hiện:

- AuthnRequest chứa ACS nội bộ mà IdP từ chối;
- IdP POST về public ACS nhưng Spring đánh giá `Destination`/`Recipient` không khớp;
- SP metadata xuất sai scheme/host, khiến cấu hình IdP lỗi;
- Cookie Secure/SameSite và chuyển hướng đăng nhập không hoạt động như mong đợi.

Một cấu hình Spring Boot phù hợp khi chỉ nhận forwarded headers từ proxy **được tin cậy** có thể dùng:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Điều kiện an toàn: ingress phải **xóa/ghi đè forwarded headers do client bên ngoài tự gửi** và chỉ chuyển header từ proxy đáng tin; nếu tin header giả, ứng dụng có thể tạo URL sai/host header injection. Cần kiểm tra thực tế `/saml2/metadata/partner-a` từ domain public, không dựa vào YAML alone.

Đối với hệ thống có canonical public URL ổn định, cấu hình tường minh `entity-id` và `acs.location` đôi khi dễ kiểm soát hơn, miễn đúng filter callback và thỏa thuận IdP.

## 13. Single Logout là một cấu hình riêng

Đăng nhập SAML2 với `saml2Login` **không tự chứng minh hệ thống đã có Single Logout (SLO)**. Local logout của SP có thể kết thúc session ứng dụng nhưng IdP vẫn giữ phiên SSO và các SP khác vẫn đang đăng nhập.

Spring Boot có nhánh `singlelogout` trong registration để mô tả SLO endpoint/binding, và cấu hình `saml2Logout` của Spring Security để bật luồng SAML logout khi cần. Các phía phải thống nhất **SLO URL, response URL, binding, signing certificates, IdP metadata và session index**. Chỉ cấu hình một chiều có thể tạo trạng thái logout một phần.

Với bài học **registration** này, SLO là **tùy chọn**: chỉ bổ sung khi bài toán thực sự yêu cầu và IdP hỗ trợ. Ví dụ các trường của Spring Boot 3.3 có thể gặp:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            singlelogout:
              url: "https://orders.example.org/logout/saml2/slo"
              binding: POST
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Đoạn này **chỉ mô tả một phần** cấu hình SLO, chưa đủ để khẳng định SLO đã hoạt động. Muốn chạy thật, cần bật đúng filter/DSL, endpoint tương ứng, khóa ký và metadata từ cả hai phía theo profile. Không dùng thử logout làm chứng cứ registration login đã đúng.

## 14. Kiểm chứng một registration theo từng lớp

Để tránh “cấu hình YAML có vẻ đúng nhưng browser vẫn không login”, kiểm chứng theo thứ tự rõ ràng:

| Lớp kiểm tra | Kiểm tra thực tế | Lỗi thường thấy |
| --- | --- | --- |
| Property binding | Boot đọc đúng `spring.security.saml2.relyingparty.registration.partner-a`. | Sai dấu gạch, indent, dùng `identityprovider` kiểu cũ, sai registration ID. |
| IdP metadata | URL tải được, XML SAML metadata hợp lệ, issuer/SSO/cert khớp hợp đồng. | 404/timeout, trả HTML login page, metadata bị cũ. |
| SP metadata | `/saml2/metadata/partner-a` công bố đúng entity ID/ACS, key info cần thiết. | URL nội bộ, scheme HTTP thay HTTPS, cert sai. |
| IdP registration | IdP đã thêm SP entity ID + ACS, binding, cert, NameID policy. | `Audience`/`Destination`/`Recipient` mismatch. |
| AuthnRequest | `/saml2/authenticate/partner-a` tới đúng IdP, response correlation tồn tại. | Chọn nhầm IdP, ký request không đúng, RelayState thất lạc. |
| SAML Response | Chữ ký hợp lệ, issuer đúng, thời hạn/audience/recipient/request ID qua validation. | Invalid signature, expired assertion, replay, bad InResponseTo. |
| Local session | SP tạo Authentication từ assertion hợp lệ. | Cookie/session/csrf/binding mismatch. |
| Authorization | Người dùng có quyền trên **đúng tài nguyên**. | Đăng nhập thành công nhưng 403 do thiếu role/tenant permission. |

### 14.1. Phân biệt 3 lỗi khác nhau

**Lỗi A: ứng dụng không khởi động vì metadata/certificate không có.** Đó là lỗi **configuration/resource loading**. Cần kiểm tra đường dẫn metadata, mạng, tin cậy TLS và file certificate thật. Đừng sửa SecurityFilterChain để bỏ qua SAML.

**Lỗi B: browser tới IdP rồi quay lại ACS nhưng authentication thất bại.** Đó là lỗi **giao thức/xác minh**. Đối chiếu `Issuer`, chữ ký, `Audience`, `Destination`, `Recipient`, `InResponseTo`, giờ hệ thống và state liên quan. Không bỏ signature validation hoặc audience check để “fix”.

**Lỗi C: SAML login thành công, request nghiệp vụ trả 403.** Đó có thể là **authorization**, ví dụ principal không có authority nội bộ hoặc không thuộc tenant được phép. Cần sửa mapping quyền/chính sách, không sửa IDP metadata để cấp quyền vượt phạm vi.

### 14.2. Quan sát an toàn

Trong môi trường phát triển kiểm soát được, có thể bật log DEBUG có chọn lọc để theo dõi đường đi cấu hình mà không đăng token/assertion đầy đủ:

~~~yaml
logging:
  level:
    org.springframework.security.saml2: DEBUG
~~~

Không bật DEBUG/TRACE vô hạn ở production, vì log có thể mang thông tin đăng nhập/cấu hình và làm lộ dữ liệu nhạy cảm. Ưu tiên log **registrationId, loại lỗi, correlation ID**, hạn chế NameID/attributes và không ghi private key hoặc raw `SAMLResponse`. Sau khi chẩn đoán, trả mức log về phù hợp.

## 15. Các lỗi thường gặp khi khai báo properties

| Triệu chứng hoặc hiểu nhầm | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| Dùng `spring.security.oauth2.client.registration` cho SAML. | Nhầm OIDC với SAML2. | Dùng `spring.security.saml2.relyingparty.registration` và `saml2Login`. |
| Dùng `identityprovider` trong Boot 3.3. | Sao chép mẫu từ phiên bản cũ. | Dùng `assertingparty` theo tài liệu Boot 3.3. |
| Cấu hình `sso-url` là URL ACS. | Nhầm endpoint IdP với SP. | `sso-url` thuộc IdP; `acs.location` thuộc SP. |
| Dùng metadata URL làm SP entity ID. | Nhầm nguồn cấu hình với định danh giao thức. | Lấy SP entity ID từ SP metadata/hợp đồng với IdP. |
| Trộn certificate của SP và IdP. | Không phân biệt chiều ký và xác minh. | `assertingparty.verification` = cert IdP; `signing/decryption` = key SP. |
| Ký response nhưng SP tin cert lấy trực tiếp từ response. | Trust anchor bị do người gửi quyết định. | Chỉ tin certificate IdP đã pin/đã xác minh từ metadata nguồn tin. |
| Đổi `registrationId` mà không đổi ACS/IdP config. | Registration ID xuất hiện trong URL/template. | Cập nhật đồng bộ Spring, SP metadata và IdP. |
| Dùng http/localhost trên production. | Reverse proxy/base URL sai. | Xuất metadata public, dùng HTTPS và forwarded headers an toàn. |
| Ghi private key vào `application.yml` hoặc Git. | Lộ bí mật. | Dùng file/secret manager với quyền đọc chặt chẽ. |
| IdP xoay cert và SP ngừng login. | SP còn cert/metadata cũ. | Có quy trình refresh/rollover, kiểm thử key set tin cậy. |
| Đổi ACS nhưng filter không nhận POST mới. | Chỉ đổi metadata URL, chưa đổi URL matcher. | Đồng bộ callback filter và ACS registration. |
| Đã có `saml2Login` nhưng không có SP metadata endpoint. | Chưa bật `saml2Metadata`. | Thêm DSL tương ứng nếu cần publish metadata. |
| Login thành công nhưng quyền quá rộng. | Tin external group/NameID là role app. | Liên kết local account và least-privilege authorization. |
| Có hai IdP nhưng gộp chung issuer/cert. | Mất ranh giới tin cậy. | Khai báo registration riêng, kiểm tra từng trust anchor. |
| Tắt xác minh khi gặp lỗi issuer/audience/signature. | Biến lỗi cấu hình thành lỗ hổng. | Sửa cấu hình và bằng chứng ký; luôn fail closed. |

## 16. Bài thực hành và tiêu chí chấp nhận

### Bài A — cấu hình đơn IdP

1. Tạo dự án Java/Gradle theo mục 8.
2. Nhận **metadata URI thật** từ IdP test của bạn và khai báo `PARTNER_A_IDP_METADATA_URI` qua environment.
3. Build/run ứng dụng, đọc SP metadata được publish ở `/saml2/metadata/partner-a`.
4. Đưa SP entity ID/ACS và signing cert (nếu cần) cho phía IdP để đăng ký.
5. Mở `/saml2/authenticate/partner-a` và hoàn tất SSO trong môi trường đã cấu hình.
6. Truy cập `/private` và xác nhận `registrationId=partner-a`, NameID đến từ tài khoản test, không tiết lộ raw assertion.

**Đạt:** Metadata và ACS khớp hợp đồng, login thành công chỉ khi response qua validation, và không cần controller tự parse SAML XML.

### Bài B — chuyển metadata sang manual

Trong môi trường test, thay `assertingparty.metadata-uri` bằng **`assertingparty.entity-id`, `sso-url` và `verification.credentials`**, dùng các giá trị/certificate thực đã được tin cậy. So sánh SP metadata và flow với cấu hình metadata-based. Nếu login thất bại, tìm nguyên nhân issuer/certificate/SSO endpoint cụ thể; không vô hiệu hóa kiểm tra chữ ký.

**Đạt:** Biết giải thích từng trường và lý do metadata-based thường ít cấu hình hơn. Có thể chứng minh cert là **IdP verification certificate**, không phải private key SP.

### Bài C — hai IdP

Tạo `partner-a` và `partner-b` với metadata riêng, thiết lập hai đường đăng nhập. Thử chọn từng registration, đối chiếu IdP được gọi và kết quả. Nếu hai IdP tạo cùng NameID, local identity vẫn được phân biệt bởi nguồn đăng ký/issuer.

**Đạt:** Không dùng lẫn certificate hoặc issuer giữa hai đối tác; mỗi flow nhận đúng ACS/registration theo cấu hình.

### Bài D — lỗi chủ đích và kỳ vọng

| Thử thay đổi ở môi trường test | Kỳ vọng an toàn |
| --- | --- |
| Sai metadata URI hoặc resource không tồn tại. | App không dựng được registration hoặc báo lỗi cấu hình; không tự bật login bỏ xác minh. |
| `entity-id` SP khác hợp đồng IdP. | IdP có thể từ chối AuthnRequest hoặc SP từ chối assertion sai Audience. |
| `acs.location` không khớp public URL. | Response/Recipient/Destination có thể bị từ chối hoặc callback không tới filter. |
| Thay IdP signing certificate bằng certificate không tin cậy. | Chữ ký assertion/response không được chấp nhận. |
| Đổi `registrationId` trên SP nhưng giữ URL IdP cũ. | Login/correlation thất bại hoặc chọn sai registration; không chấp nhận lẫn IdP. |
| Xóa SP signing key khi IdP yêu cầu ký AuthnRequest. | Không tạo được request hợp lệ theo chính sách; không tự ký giả. |
| Principal hợp lệ nhưng không có permission nội bộ. | Có thể đăng nhập, nhưng endpoint nghiệp vụ bị từ chối. |

### Câu hỏi tự kiểm tra

1. **Tại sao `registrationId` khác với `entity-id`?** Registration ID là khóa trong Spring để chọn cặp SP–IdP; entity ID là danh tính SAML mà phía còn lại dùng để đối chiếu và phát hành assertion.
2. **Tại sao dùng `metadata-uri` vẫn phải đăng ký SP bên IdP?** Metadata chỉ giúp SP biết IdP; IdP còn phải biết SP entity ID, ACS, chính sách ký và khả năng giải mã.
3. **Cert ở `assertingparty.verification` là của ai?** Public certificate tin cậy của IdP để SP xác minh chữ ký.
4. **Private key ở `signing.credentials` là của ai?** SP, dùng ký message outbound khi cần.
5. **`sso-url` và `acs.location` khác gì nhau?** SSO URL thuộc IdP nhận request; ACS thuộc SP nhận response.
6. **Có phải khai báo `saml2Login` là tự có `saml2Metadata` không?** Không mặc định giả định thế; bật `saml2Metadata` để publish metadata endpoint của SP.
7. **Khi nào cần repository Java?** Khi yêu cầu custom registration/refresh/store/tenant vượt khả năng config YAML, đồng thời phải quản lý việc thay thế auto-configuration.
8. **Khi SAML login thành công, người dùng có mọi quyền trong ứng dụng?** Không. Authorization là lớp riêng; kiểm tra local account, permission, tenant và ownership.
9. **Tại sao không giải quyết lỗi ký số bằng cách tắt signature validation?** Vì đó là cách bỏ cơ chế xác thực nguồn và toàn vẹn; phải sửa metadata/certificate/chính sách đúng.
10. **Tại sao cần kiểm tra metadata ở URL public sau deploy?** Vì entity ID/ACS có thể bị dựng sai do reverse proxy/host/scheme, gây reject ở IdP/SP.

## 17. Checklist hoàn thành một registration

- [ ] Có dependency SAML2 SP và `SecurityFilterChain` dùng `saml2Login`.
- [ ] Có **registrationId** ổn định, duy nhất.
- [ ] IdP entity ID, SSO URL, binding, verification certificate/metadata xuất phát từ **nguồn được tin cậy**.
- [ ] SP entity ID và ACS đúng hợp đồng với IdP, đúng URL public.
- [ ] Nếu cần ký AuthnRequest: có **SP signing private key + certificate**; IdP đã nhận public cert.
- [ ] Nếu cần giải mã assertion: có **SP decryption private key + certificate** phù hợp.
- [ ] SP metadata đã được kiểm tra, IdP đã đăng ký SP, certificate và phương thức xác thực.
- [ ] Reverse proxy/forwarded headers/cookie/TLS xử lý đúng.
- [ ] SP từ chối response sai issuer, signature, audience, recipient, time hoặc InResponseTo.
- [ ] Nhiều IdP được tách registration và trust contract.
- [ ] SLO chỉ được đánh dấu hỗ trợ sau khi tích hợp và kiểm thử riêng.
- [ ] Quyền nghiệp vụ có kiểm tra local account/tenant, không tin external group vô điều kiện.
- [ ] Có kế hoạch certificate rollover, metadata update, log bảo mật và test hồi quy.

**Nguyên tắc ghi nhớ:** `spring.security.saml2.relyingparty.registration.<id>` khai báo **một cặp quan hệ tin cậy SP–IdP**. Nhánh ngoài là những gì **SP sở hữu/công bố**; nhánh `assertingparty` là những gì **SP biết và xác minh về IdP**. Metadata, ACS, issuer và certificate phải khớp ở cả hai phía; Spring Security xử lý SAML protocol, còn ứng dụng quyết định quyền nghiệp vụ.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Spring Security / SAML2 Relying Party](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#web.security.saml2) — nhánh `spring.security.saml2.relyingparty.registration` và cấu trúc credentials/IdP.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) — danh mục `spring.security.saml2.relyingparty.registration.*`.
- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — registration, entity ID, ACS và filter flow.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — xuất SP metadata và các endpoint.
- [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — xử lý và xác minh response.
- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.pdf) — mô hình giao thức và các phần metadata, SP/IdP.
