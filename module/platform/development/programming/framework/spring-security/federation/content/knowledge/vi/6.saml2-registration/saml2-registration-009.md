# Bật `saml2Login` và xác định các điểm truy cập công khai cần thiết

> **Phạm vi:** Đăng ký SAML2 trong Spring Security (ứng dụng **Service Provider/Relying Party** sử dụng **SAML 2.0 Web Browser SSO**). Nội dung tập trung vào cách bật filter đăng nhập SAML, nhận diện URL giao thức mà trình duyệt/IdP phải tới được khi chưa có phiên, và bảo vệ tất cả tài nguyên nghiệp vụ còn lại.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích tại sao ứng dụng SAML Service Provider (SP) cần một số URL **có thể truy cập khi chưa đăng nhập**, trong khi trang nghiệp vụ vẫn phải yêu cầu xác thực.
2. Bật `http.saml2Login(...)` trong `SecurityFilterChain` và hiểu mối liên hệ với `RelyingPartyRegistrationRepository`.
3. Xác định chính xác các URL thường dùng: trang vào/login, điểm khởi tạo `AuthnRequest`, **Assertion Consumer Service (ACS)** nhận `SAMLResponse`, endpoint xuất **SP metadata**, và tùy chọn Single Logout.
4. Cấu hình `authorizeHttpRequests` theo **allowlist**, phân biệt `permitAll()` với việc loại hẳn một URL khỏi filter chain.
5. Giải thích tại sao ACS phải tiếp nhận POST từ trình duyệt chưa xác thực nhưng **vẫn phải kiểm tra chặt SAML Response**.
6. Dựng ví dụ Java 17+ với Spring Boot, kiểm thử hành vi khi chưa đăng nhập, khi SAML thành công và khi bằng chứng sai.
7. Nhận diện lỗi phổ biến: mở nhầm `/**`, chặn ACS/metadata, sai `registrationId`, sai URL vì reverse proxy, lỗi CSRF, sai certificate và thiếu SAML logout.

**Điểm then chốt:** “Public endpoint” chỉ có nghĩa **không đòi sẵn một phiên người dùng trước khi request được xử lý**. Đối với URL SAML, đây là yêu cầu của luồng giao thức, **không phải quyền truy cập vào dữ liệu người dùng**.

## 2. Vai trò và các bước của Web SSO

Trong Spring Security SAML:

- **Asserting Party (AP), Identity Provider (IdP):** hệ thống xác thực người dùng và phát `SAML Response` chứa khẳng định danh tính.
- **Relying Party (RP), Service Provider (SP):** ứng dụng Spring cần đăng nhập; gửi `AuthnRequest`, tiếp nhận `SAMLResponse` qua ACS, xác minh và tạo `Authentication`/phiên local.
- **`RelyingPartyRegistration`:** cấu hình gắn một RP với một AP, gồm `registrationId`, `entityId` của SP, endpoint ACS, URL SSO của IdP, chứng thư verify và tùy chọn signing.
- **`RelyingPartyRegistrationRepository`:** nơi Spring tra cứu các registration khi xây yêu cầu hoặc xác minh response. Spring Boot có thể tạo bean này từ `spring.security.saml2.relyingparty.registration` nếu cấu hình đủ.

Luồng SP-initiated SSO điển hình:

```text
(1) Browser                  Spring SP                     SAML IdP
       |                         |                             |
       | GET /private            |                             |
       |------------------------>|                             |
       |   chưa có Authentication|                             |
       |<----- 302 login/SSO ----|                             |
       |                         |                             |
       | GET /saml2/authenticate/training                       |
       |------------------------>|                             |
       |<--- redirect AuthnRequest (SAMLRequest, RelayState) ----|
       |                                                       |
       |------------- browser đến IdP SSO --------------------->|
       |                     IdP đăng nhập                     |
       |<------------- trang HTML POST SAMLResponse ------------|
       |                                                       |
       | POST /login/saml2/sso/training                         |
       |------------------------>|  xác minh SAMLResponse       |
       |                         |  tạo Authentication + session|
       |<----- redirect /private|                             |
       | GET /private + cookie   |                             |
       |------------------------>|                             |
       |<--------- 200 ----------|                             |
```

Các URL ở bước khởi tạo và ACS phải sẵn sàng trước khi có phiên. Filter của Spring tham gia xử lý **trước bước cấp quyền ở controller**. Chỉ sau khi response hợp lệ, ứng dụng mới có người dùng đã xác thực để phục vụ `/private`, `/account` hoặc các đường dẫn nghiệp vụ.

**Lưu ý:** IdP-initiated SSO có thể không có `AuthnRequest` tương ứng; việc chấp nhận hay không, ràng buộc `InResponseTo` và chống replay phải theo chính sách giao thức/IdP. Bài tập này lấy SP-initiated làm mặc định để quan sát đầy đủ cơ chế liên kết request–response.

## 3. Lập danh sách các điểm truy cập theo mục đích

Các path sau là những giá trị **mặc định/phổ biến của Spring Security SAML2 Login**. Chúng không phải một giao diện REST do bạn tự viết, và có thể khác khi tùy chỉnh DSL, phiên bản hay reverse proxy.

| Path hoặc nhóm path | Method / người gọi | Có cần phiên trước? | Vai trò thực tế |
| --- | --- | --- | --- |
| `/`, `/about`, tài nguyên công khai `/css/**`, `/js/**`, `/images/**` | GET, browser | **Không** | Trang giới thiệu/login UI và tài nguyên tĩnh do ứng dụng chủ động xuất bản |
| `/login` | GET, browser | **Không** | Trang login do Spring tạo mặc định, hoặc trang tùy chỉnh đã có controller |
| `/saml2/authenticate/{registrationId}` | Thường GET, browser | **Không** | `Saml2WebSsoAuthenticationRequestFilter` dựng `AuthnRequest` và chuyển trình duyệt sang IdP; một số phiên bản hỗ trợ biến thể query `registrationId` |
| `/login/saml2/sso/{registrationId}` | Thường POST, browser mang response từ IdP | **Không** | **ACS** do `Saml2WebSsoAuthenticationFilter` xử lý; chỉ đăng nhập khi `SAMLResponse` hợp lệ |
| `/login/saml2/sso` | POST trong các cấu hình/phiên bản hỗ trợ | **Không** | Biến thể ACS không chứa registrationId trong path; việc resolve registration phải có cơ chế phù hợp |
| `/saml2/metadata` | GET, IdP/admin/tool | **Không, nếu chủ động công khai** | Xuất metadata của các SP registration khi `saml2Metadata(...)` bật |
| `/saml2/metadata/{registrationId}` | GET, IdP/admin/tool | **Không, nếu công khai** | Metadata của một RP registration cụ thể |
| `/saml2/service-provider-metadata/{registrationId}` | GET, IdP/admin/tool | **Không, nếu công khai** | Tên endpoint metadata tương thích được Spring hỗ trợ; **không đồng nghĩa ACS** |
| `/logout` | Thường POST, browser có phiên | Theo cơ chế logout của Spring | Kết thúc phiên cục bộ; POST thường cần CSRF token trong ứng dụng dùng session |
| `/logout/saml2/slo` | POST khi đã cấu hình SAML Single Logout | Phải tiếp nhận bản tin IdP thích hợp | Điểm nhận SAML LogoutRequest/LogoutResponse; **không tự xuất hiện chỉ bằng `saml2Login`** |
| `/private`, `/account/**`, `/admin/**`, API nghiệp vụ | GET/POST/..., browser/client | **Có** (và quyền riêng) | Nội dung phải bảo vệ bằng `authenticated()` hoặc điều kiện quyền cụ thể |

**Ba khái niệm dễ nhầm:**

1. **AuthnRequest endpoint** là điểm **đi ra tới IdP** qua trình duyệt; nó không xử lý `SAMLResponse`.
2. **ACS** là điểm **đi vào từ IdP**. Dù browser gửi POST chưa có phiên đăng nhập, `SAMLResponse` phải qua bộ kiểm tra SAML. Không tự viết controller để decode Base64 rồi tin `NameID`.
3. **SP metadata endpoint** công bố cấu hình công khai mà IdP cần biết, như `entityID`, ACS và public certificate khi cấu hình. Nó **khác** IdP metadata mà SP dùng để lấy IdP entity ID, URL SSO và verify certificate.

Một URL chỉ nên được mở công khai nếu thật sự phục vụ trang công khai hoặc giao thức SAML. Ví dụ `/actuator/**`, `/admin/**`, `/api/**` và `/internal/**` không được thêm vào allowlist chỉ để “login chạy được”.

## 4. Chuẩn bị ứng dụng và đăng ký SAML2

### 4.1. Dependency và phiên bản

Ví dụ giả định **Java 17+**, Spring Boot/Spring Security servlet stack tương thích và một **IdP SAML2 thử nghiệm** đã được cấu hình. Trong Maven dùng Spring Boot parent/BOM để quản lý version của những dependency liên quan:

```xml
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
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
</dependencies>
```

Đây là **đoạn dependencies** cần đặt trong `pom.xml` của một dự án Spring Boot Maven hoàn chỉnh, không phải toàn bộ `pom.xml`. Với Gradle, chọn dependency tương đương. API cụ thể có thể khác giữa các major version, nên ghép tài liệu/phiên bản Spring Security đúng với ứng dụng thay vì chép lẫn ví dụ Spring Security 5, 6 và 7.

### 4.2. Khai báo một RP registration tên `training`

File `src/main/resources/application.yml` minh họa **cấu hình thủ công IdP**:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          training:
            assertingparty:
              entity-id: https://idp.example.test/saml
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.example.test/saml/sso
                sign-request: false
```

**Điều kiện để chạy thật:** `https://idp.example.test/...` và `idp-signing.crt` chỉ là giá trị minh họa, **không phải máy chủ/chứng thư có thể dùng ngay**. Thay bằng `entityID`, SSO URL và chứng thư X.509 **thật của IdP test đã phê duyệt**. Đặt certificate PEM/DER theo định dạng mà cấu hình Spring hỗ trợ tại `src/main/resources/saml/idp-signing.crt`. Chứng thư dùng **xác minh chữ ký từ IdP**, không phải private key của SP.

Tùy hệ IdP, có thể lấy cấu hình từ **IdP metadata có nguồn tin cậy** thay vì nhập từng thông số:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          training:
            assertingparty:
              metadata-uri: https://idp.example.test/saml/metadata
```

Đây là **phương án thay thế**, không trộn vô điều kiện với mẫu nhập thủ công. Nếu tải metadata khi khởi động, SP có thể không khởi động nếu endpoint metadata IdP mất kết nối; cần kế hoạch cache/refresh và quản lý trust theo môi trường.

`training` chính là `registrationId` được dùng trong các URL ví dụ. Với defaults, Spring dùng giá trị tương đương:

- **SP entityID:** `{baseUrl}/saml2/service-provider-metadata/{registrationId}`.
- **ACS:** `{baseUrl}/login/saml2/sso/{registrationId}`.
- **AuthnRequest:** `/saml2/authenticate/{registrationId}`.

Ví dụ nếu URL công khai của ứng dụng là `https://app.example.test` thì ACS là `https://app.example.test/login/saml2/sso/training`. Hãy đăng ký **chính xác** SP `entityID` và ACS HTTPS ở hệ IdP. Không đánh đồng `registrationId` do ứng dụng đặt với `entityID` do giao thức SAML đối chiếu.

**Vì sao `sign-request: false`?** Giá trị này chỉ dùng khi IdP test cho phép `AuthnRequest` không ký. Nếu IdP yêu cầu request phải ký, cấu hình **SP signing certificate/private key** và cập nhật metadata/SP registration; không tắt yêu cầu ký của production IdP chỉ để kết nối thành công.

## 5. Bật `saml2Login` và định nghĩa allowlist trong Java

File `src/main/java/com/example/samllab/SecurityConfig.java`, dùng trong ứng dụng Spring Boot có package `com.example.samllab`:

```java
package com.example.samllab;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                // Cần cho error dispatch của ứng dụng
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()

                // Trang vào, trang login và tài nguyên giao diện thật sự công khai
                .requestMatchers(HttpMethod.GET,
                    "/", "/about", "/login", "/error",
                    "/css/**", "/js/**", "/images/**",
                    "/favicon.ico").permitAll()

                // Bắt đầu SAML SSO, xuất metadata cho IdP/đối tác
                .requestMatchers(HttpMethod.GET,
                    "/saml2/authenticate/**",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()

                // ACS nhận SAMLResponse bằng HTTP POST từ browser
                .requestMatchers(HttpMethod.POST,
                    "/login/saml2/sso",
                    "/login/saml2/sso/**").permitAll()

                // Điều kiện quyền nghiệp vụ phải đứng trước quy tắc chung
                .requestMatchers("/admin/**").hasRole("ADMIN")

                // Mọi URL nghiệp vụ khác phải đăng nhập
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

**Class trên là thành phần của ứng dụng Spring Boot**, không phải chương trình một file chạy bằng `javac SecurityConfig.java` vì cần dependency và bean context. Nó sử dụng kiểu import `jakarta.servlet.DispatcherType` phù hợp Spring Boot 3+/Spring Security 6+. Tại source package trên, một ứng dụng khởi động tối thiểu có thể là:

```java
package com.example.samllab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlLabApplication.class, args);
    }
}
```

Có thể thêm controller để quan sát quy tắc truy cập:

```java
package com.example.samllab;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SAML SP is ready";
    }

    @GetMapping("/private")
    public String privateArea(Authentication authentication) {
        return "Authenticated via SAML";
    }
}
```

Ở `/private` tham số `Authentication` chỉ hiện diện hợp lệ sau login; ví dụ cố tình **không trả toàn bộ SAML assertion hoặc thuộc tính nhạy cảm** ra response. Tài nguyên thực tế còn phải kiểm tra phân quyền nghiệp vụ. Endpoint `/about` chỉ cần được giữ trong allowlist nếu ứng dụng thật sự cung cấp trang công khai tương ứng; `permitAll` **không tự tạo route/controller**.

### 5.1. Phân tích chính xác từng dòng cấu hình

- `authorizeHttpRequests(...)` áp dụng luật từ trên xuống dưới theo **matcher đầu tiên khớp**. Rule `/admin/**` đứng trước `anyRequest().authenticated()` để yêu cầu quyền mạnh hơn đăng nhập thông thường.
- `.saml2Login(Customizer.withDefaults())` thêm cấu hình đăng nhập qua SAML. Spring đăng ký các filter cần thiết để tạo `AuthnRequest`, xử lý `SAMLResponse` tại ACS và tạo đối tượng xác thực. Nếu thiếu `RelyingPartyRegistrationRepository` hợp lệ, login **không thể tự hoạt động**.
- `.saml2Metadata(Customizer.withDefaults())` **bật xuất SP metadata**. Nó không đồng nghĩa tính năng login; metadata có thể cần cung cấp cho IdP để biết SP entityID và ACS.
- `.requestMatchers(...).permitAll()` cho phép một request **đi qua bước kiểm tra quyền URL khi chưa có session**, không gỡ `SecurityFilterChain`. Những bước như kiểm tra SAML signature, chống replay, security headers hay CSRF ở các endpoint khác vẫn tồn tại.
- `.requestMatchers(HttpMethod.POST, "/login/saml2/sso/**")` thể hiện ACS là điểm nhận **POST không có sẵn phiên**. Nếu request có SAML giả, sai chữ ký, sai issuer, sai thời gian hoặc sai audience, **authentication filter vẫn phải từ chối**.
- `.dispatcherTypeMatchers(DispatcherType.ERROR)` hỗ trợ trình xử lý lỗi của ứng dụng. Nếu hệ thống có trang error hiển thị thông tin nhạy cảm, giới hạn dữ liệu lỗi được trả cho người dùng; `permitAll` không phải lý do lộ stack trace.
- `.requestMatchers("/admin/**").hasRole("ADMIN")` chỉ là ví dụ quy tắc phân quyền. **SAML attribute nhóm/quyền không tự động biến thành `ROLE_ADMIN`**; cần mapping tin cậy và kiểm thử của ứng dụng. Người vừa SAML login thành công có thể vẫn bị `403` tại `/admin/**` vì chưa có role.

Nếu chỉ có **một** IdP, Spring có thể trực tiếp đưa browser sang luồng đăng nhập; với nhiều registration, login UI thường đưa ra lựa chọn IdP. Kết quả điều hướng cụ thể còn tùy cấu hình custom login page, session và phiên bản.

### 5.2. Khi sử dụng trang đăng nhập tùy chỉnh

Ví dụ HTML trên trang login công khai:

```html
<a href="/saml2/authenticate/training">Đăng nhập bằng IdP</a>
```

Khi đặt `.saml2Login(saml2 -> saml2.loginPage("/login"))`, hãy **tự triển khai** `GET /login` (controller và view/HTML), công khai URL này trong `authorizeHttpRequests` và cung cấp đường dẫn tới `/saml2/authenticate/training`. Khai báo một custom login page **không tự sinh trang HTML**. Đừng tạo đường link tới ACS như một nút đăng nhập: ACS chỉ dành cho response từ IdP.

Đối với SP-initiated flow, người dùng có thể truy cập `/private` và để Spring tạo quá trình chuyển hướng, hoặc chọn URL `/saml2/authenticate/training`. Cả hai cách đều dẫn tới xác thực IdP, miễn phần đăng ký và session/correlation hoạt động đúng.

## 6. Public không đồng nghĩa thiếu an toàn: các lớp bảo vệ bắt buộc

### 6.1. ACS phải nhận được POST trước khi người dùng có phiên

`SAMLResponse` thường được IdP chuyển qua trình duyệt bằng **HTTP-POST binding**. Do đó browser **chưa xác thực tại SP** vẫn phải có khả năng gửi POST vào ACS. Nhưng endpoint này **không phải API đăng nhập nhận user/password hay JSON tùy ý**. Spring Security xử lý response qua `Saml2WebSsoAuthenticationFilter` và bộ xác minh SAML/OpenSAML phù hợp.

Những điều cần kiểm tra cho response, tùy binding và profile:

- IdP/entityID nằm trong danh sách tin cậy và chữ ký của phần message/assertion được xác minh theo chính sách.
- `AudienceRestriction`/`Recipient`/`Destination` dành đúng SP/ACS.
- `NotBefore`/`NotOnOrAfter`, thời hạn, replay và correlation `InResponseTo` của SP-initiated flow.
- Trạng thái response thành công, chủ thể/`NameID` và các ràng buộc khác theo SAML profile.
- Đường truyền HTTPS và quản lý chứng thư ký/rollover đúng quy trình.
- Các thuộc tính group/role từ IdP chỉ được quy đổi thành quyền của SP sau khi đã được kiểm tra và ánh xạ rõ ràng.

**Không thêm `@PostMapping("/login/saml2/sso/...")` tùy tiện** để tự nhận SAMLResponse rồi đọc Base64. Việc mở controller thay filter có thể bỏ qua các bước kiểm tra giao thức và tạo lỗ hổng mạo danh danh tính.

### 6.2. ACS và CSRF: ngoại lệ hẹp, không tắt toàn ứng dụng

Spring Security mặc định bảo vệ CSRF cho các request thay đổi trạng thái của ứng dụng dùng **session cookie**. Nhưng SAML HTTP-POST từ IdP thường không mang CSRF token của ứng dụng SP. `saml2Login` đăng ký ngoại lệ **CSRF riêng cho endpoint xử lý WebSSO** tương ứng; các endpoint form POST nghiệp vụ vẫn cần CSRF.

**Không dùng** `csrf(AbstractHttpConfigurer::disable)` cho toàn bộ web chỉ vì ACS cần nhận POST. Nếu tự thay `loginProcessingUrl`/ACS matcher, kiểm tra lại rằng ngoại lệ CSRF áp dụng **đúng URL thực tế**, không mở vô hạn `/login/**`, `/**` hay tất cả POST. `permitAll` là quy tắc **ủy quyền URL**, **khác** với bỏ qua kiểm tra CSRF; thêm `permitAll` không tự chữa một mismatch CSRF.

Đừng nhầm `POST /logout` dùng cookie session với callback SAML ACS. Logout local thường phải đi qua cơ chế logout của Spring và CSRF phù hợp; nếu bật SAML SLO, dùng các endpoint/filter SLO của framework và kiểm tra chữ ký bản tin logout.

### 6.3. `permitAll` khác với `web.ignoring()`

`permitAll()`: request vẫn đi qua filter của Spring Security, còn chịu các biện pháp xác thực/giao thức và security headers liên quan. `web.ignoring()`: loại request khỏi chuỗi Spring Security; điều này có thể bỏ qua filter cần thiết hoặc security headers. Với metadata, login page và static assets, **ưu tiên `permitAll`** khi có thể. Không bao giờ dùng `web.ignoring("/login/saml2/sso/**")` hoặc `web.ignoring("/saml2/**")` để sửa lỗi 403.

### 6.4. Chỉ để lộ những gì IdP thực sự cần

**SP metadata** thường là tài liệu công khai, có thể chứa entityID, ACS, binding và **public** certificate. Việc cho phép GET từ IdP/operator không có nghĩa phải mở public internet nếu chính sách tổ chức yêu cầu trao đổi metadata theo kênh được kiểm soát. Có thể phân phối qua kênh quản trị hoặc giới hạn truy cập ở ingress, miễn IdP còn có cách nhận được metadata và cập nhật cert.

Không đưa **private key**, secret, raw SAML assertion, session cookie hoặc token vào metadata/log. Không trả về danh sách metadata của mọi tenant nếu hệ thống có lý do chính đáng để hạn chế tenant enumeration; khi đó xem xét endpoint cụ thể cho từng registration hoặc trao đổi metadata riêng.

## 7. Single Logout là tính năng bổ sung riêng

`saml2Login` đảm nhận **đăng nhập**, không mặc nhiên bật SAML **Single Logout (SLO)**. Nếu chỉ cần đăng xuất khỏi phiên local, dùng logout của Spring. Nếu IdP và SP cùng hỗ trợ SLO, cần cấu hình SP ký logout message, metadata có endpoint logout, chính sách xử lý request/response và bổ sung:

```java
http
    .saml2Logout(Customizer.withDefaults());
```

Đây là **đoạn thêm vào cùng `HttpSecurity`**, không phải một `SecurityFilterChain` độc lập hay chương trình Java hoàn chỉnh. Luồng logout SAML thường cần endpoint `/logout/saml2/slo` (hoặc URL đã cấu hình), nhận POST từ IdP; một số tài liệu và phiên bản cho biến thể path nên phải đối chiếu URL từ metadata và cấu hình thật. Không đưa mọi URL `/logout/**` vào `permitAll` theo thói quen.

SLO chỉ hoạt động khi **IdP hỗ trợ**, SP có signing key/certificate và cấu hình tương ứng. Nên kiểm thử cả **SP-initiated logout** và **IdP-initiated logout**; hết session local **không tự bảo đảm** phiên SSO tại IdP đã hết.

## 8. Nhiều SecurityFilterChain, reverse proxy và cấu hình URL

### 8.1. Matcher ở cấp chain khác matcher cấp authorization

Khi dự án có nhiều chuỗi filter, `securityMatcher("/api/**")` chỉ chọn các request thuộc API vào chain ấy. Nếu bạn đặt `saml2Login` trong một chain chỉ match `/private/**` thì các endpoint `/saml2/authenticate/**` và `/login/saml2/sso/**` **có thể không được chính chain đó xử lý**.

Ví dụ tư duy:

```text
Chain số 1: /api/**                -> Resource Server (Bearer token)
Chain số 2: các URL còn lại       -> SAML2 Login + metadata + web session
```

Trong trường hợp này, cần đảm bảo chain thứ hai được đăng ký và xử lý **cả AuthnRequest/ACS/login/metadata**. Chỉ gắn authorization matcher `permitAll` vào chain sai thì không giải quyết được lỗi. Cần kiểm tra `@Order`, `securityMatcher` và filter chain thực sự chọn cho từng URL.

Nếu dùng Spring Boot và tự tạo `@Bean SecurityFilterChain`, cấu hình security mặc định do Boot cung cấp có thể lùi lại; lúc đó bạn phải **tự gọi `saml2Login`** trong chain phù hợp. Sự tồn tại của dependency SAML2 không đảm bảo chain tùy chỉnh đã bật SSO.

### 8.2. HTTPS, baseUrl và forwarding headers

SP metadata và AuthnRequest có thể chứa `entityID`, ACS URL và `Destination`. URL sinh từ `{baseUrl}` phụ thuộc **scheme, host, port mà Spring nhìn thấy**. Khi app ở sau TLS-terminating reverse proxy, nếu Spring tự cho rằng đang ở `http://internal-host:8080`, metadata có thể công bố sai ACS dù browser dùng `https://app.example.org`.

Biện pháp:

1. Cấp một tên miền canonical HTTPS cho SP và đăng ký đúng tại IdP.
2. Cấu hình proxy chuyển tiếp scheme/host đúng; backend **chỉ tin forwarded headers từ proxy được tin**, và proxy phải loại giá trị giả do client trực tiếp gửi.
3. Chọn cách xử lý forwarded headers phù hợp Spring Boot/container, chẳng hạn `server.forward-headers-strategy` khi topology yêu cầu.
4. Sau khi triển khai, **đọc SP metadata thực tế** và so sánh `entityID`, ACS URL, binding với cấu hình IdP; kiểm thử browser redirects và POST callback.
5. Không bỏ xác minh TLS/host hoặc tự “sửa” SAMLResponse để vượt qua `Destination`/`Recipient` mismatch.

Lỗi URL do reverse proxy là một trong những nguyên nhân của đăng nhập vòng lặp: sau khi IdP xác thực thành công, browser POST về một ACS sai host hoặc HTTP, rồi SP không hoàn thành phiên.

### 8.3. Redirect sau login và RelayState

Ứng dụng nên quay lại trang người dùng định truy cập **chỉ qua cơ chế lưu request/điều hướng đáng tin**. Không lấy nguyên `RelayState` hoặc tham số `next` từ request chưa xác thực rồi `sendRedirect` tới URL bất kỳ: điều này dễ tạo open redirect. RelayState có vai trò trong liên kết SAML request/response và không phải giấy phép điều hướng tới mọi miền.

## 9. Kiểm thử từng endpoint theo ma trận

Giả sử RP chạy ở `https://app.example.test` và IdP test đã được đăng ký đúng. Các command dưới đây là minh họa; cần thay FQDN/chứng thư bằng môi trường chạy thật và **không dùng `curl -k` để bỏ TLS**.

```bash
curl -i https://app.example.test/
curl -i https://app.example.test/login
curl -i https://app.example.test/saml2/metadata/training
curl -i https://app.example.test/saml2/authenticate/training
curl -i https://app.example.test/private
```

**Ý nghĩa của kết quả:**

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| GET `/` không có cookie | HTTP 200 với nội dung “SAML SP is ready” nếu đã tạo controller |
| GET `/login` không có cookie | Trang login công khai hoặc điều hướng tới IdP theo cấu hình; không đòi một phiên đã đăng nhập trước |
| GET `/saml2/metadata/training` | HTTP 200 với XML SAML metadata nếu `saml2Metadata`/registration đúng; metadata chứa entityID/ACS hợp lệ |
| GET `/saml2/authenticate/training` | Bắt đầu SSO, thường 302 tới SAML SSO endpoint của IdP với `SAMLRequest` |
| GET `/private` không cookie | Không trả dữ liệu riêng; thường chuyển tới login/SSO bằng 302 trong ứng dụng web |
| POST `/login/saml2/sso/training` với form giả/không có SAMLResponse | **Không đăng nhập thành công**; có thể là phản hồi lỗi/redirect theo failure handler |
| Browser hoàn tất SAMLResponse hợp lệ từ IdP | SP xác minh, tạo phiên, GET `/private` trả 200 |
| Người dùng có phiên nhưng không được cấp `ROLE_ADMIN` | Truy cập `/admin/**` phải bị từ chối quyền nếu endpoint tồn tại |
| SAMLResponse đã hết hạn, sai issuer/audience/chữ ký, sai recipient, replay | SP từ chối xác thực dù ACS là URL “public” |
| GET `/internal/config` khi chưa có phiên | Không truy cập dữ liệu; bị yêu cầu đăng nhập hoặc từ chối theo chain/policy |

**Kiểm thử với browser là bắt buộc** để xác nhận binding, cookie và session, vì chỉ nhìn 302/200 bằng `curl` không chứng minh toàn bộ flow xác thực. Sau khi login thành công, inspect network ở DevTools nhưng **không copy/đăng raw SAMLResponse hay session cookie** lên issue/trang tài liệu công khai.

Bạn có thể chạy ứng dụng Maven đã có Boot parent bằng:

```bash
./mvnw spring-boot:run
```

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Nếu IdP metadata/cert/config chưa đúng, ứng dụng có thể không khởi động hoặc redirect/login thất bại; đây là lỗi tích hợp, không chứng minh rằng allowlist sai.

### 9.1. Kiểm thử cô lập access control

Một lần tự rà soát nên gồm:

1. Thử các URL nghiệp vụ không có cookie, bảo đảm **không nhận dữ liệu riêng**.
2. Kiểm tra GET `/saml2/metadata/training` xuất đúng **SP metadata**, không trả certificate private key hoặc secrets.
3. Kiểm tra GET `/saml2/authenticate/training` tạo yêu cầu đến đúng IdP; registrationId không hợp lệ không được tự map đến một IdP tùy ý.
4. Gửi POST giả tới ACS, xác nhận **không** tạo session xác thực.
5. Dùng SAMLResponse ký bởi IdP test đúng; kiểm tra thực sự vào `/private`.
6. Thử claim/role chưa được map và đường dẫn `/admin/**`; xác thực hợp lệ chưa đủ để có quyền quản trị.
7. Tắt IdP test hoặc thay certificate trong môi trường test rồi thử lại, xác nhận login **fail closed** và không fallback sang tin header/email chưa xác minh.
8. Kiểm tra CSRF vẫn được thực thi ở **POST nghiệp vụ** có session; ACS là ngoại lệ hẹp theo filter.
9. Kiểm tra logout local và nếu bật SLO thì kiểm tra luồng IdP ↔ SP hai chiều theo binding đã thỏa thuận.

HTTP status chính xác có thể phụ thuộc failure handler, error page và loại request. Kết luận cần dựa trên việc có/không có session và dữ liệu được bảo vệ, không chỉ một mã 302 hoặc 403 đơn lẻ.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Vào `/private` nhận 403 thay vì redirect | Entry point, chain/matcher hoặc cấu hình login không được áp dụng | Xác định `SecurityFilterChain` đang xử lý URL; bảo đảm `saml2Login` nằm trong web chain |
| GET `/saml2/authenticate/training` 404 hoặc không đến IdP | Sai registrationId, filter không vào chain, thiếu `RelyingPartyRegistrationRepository` | Kiểm tra tên registration, dependency, chain matcher và IdP SSO URL |
| ACS `/login/saml2/sso/training` 403 CSRF | Đổi ACS path mà ngoại lệ CSRF không khớp, hoặc request không tới đúng filter | Kiểm tra URL ACS thực và filter/CSRF matcher; không tắt CSRF toàn web |
| ACS 404 hoặc authentication failure | IdP gửi tới ACS khác cấu hình, response thiếu/sai, cert/signature/audience sai | So sánh IdP ACS, SP metadata, logs có lọc nhạy cảm và certificate |
| GET `/saml2/metadata/training` 404 | Chưa bật `saml2Metadata` hoặc filter không nằm trong chain | Bật metadata DSL ở web chain; kiểm tra endpoint đang dùng |
| GET metadata bị 302 về login | Metadata không có quy tắc public phù hợp, hoặc chain khác yêu cầu auth | Thêm GET metadata vào allowlist ở chain đúng hoặc trao đổi metadata theo kênh được kiểm soát |
| Login UI hiện nhưng bấm login lại 404 | Link trỏ thẳng ACS hoặc sai tên registration | Link phải là `/saml2/authenticate/training`, registrationId phải tồn tại |
| Đăng nhập được nhưng `/admin` bị 403 | Chưa ánh xạ role/authority hoặc người dùng không có quyền | Kiểm tra `GrantedAuthority` và logic mapping SAML attributes; không bỏ `hasRole` để chữa 403 |
| IdP xác thực thành công nhưng quay vòng về login | Chênh lệch scheme/host/proxy, cookie/session không được giữ, sai ACS hoặc assertion lỗi | So sánh URL/cookie/SAML validation; sửa trust/forwarded headers từ nguồn đáng tin |
| Log SAML hiện lỗi thời gian | Đồng hồ lệch hoặc assertion quá hạn/chưa hiệu lực | Đồng bộ NTP, kiểm tra `NotBefore`/`NotOnOrAfter`, không bỏ kiểm tra thời gian |
| GET `/actuator/health`/static không hoạt động | Path không được phép hoặc controller/resource không tồn tại | Cấp quyền đúng endpoint cần dùng; **không** mở cả actuator/internal |
| Đã bật `saml2Login` nhưng SAML Single Logout không hoạt động | Chưa cấu hình `saml2Logout`, signing credentials hoặc IdP không hỗ trợ | Tích hợp SLO riêng và kiểm thử thông điệp ký/binding |
| Một đường public vô tình bỏ qua toàn bộ Security | Dùng `web.ignoring`, chain matcher sai hoặc `permitAll("/**")` | Khôi phục allowlist hẹp; xác minh các request nhạy cảm thực sự qua filter |

**Thứ tự phân tích tối ưu:**

```text
1. URL request có thuộc SecurityFilterChain đúng không?
2. URL có route/filter của SAML tương ứng không?
3. registrationId đã đăng ký và IdP metadata/certificate hợp lệ chưa?
4. URL ACS/entityID được xuất trong SP metadata có khớp IdP không?
5. HTTP binding/method và CSRF matcher đúng chưa?
6. Response có chữ ký, issuer, audience, recipient, thời gian hợp lệ không?
7. Nếu login thành công: session cookie và GrantedAuthority được tạo đúng chưa?
8. Nếu vẫn lỗi: xác định proxy/clock/cert/IdP logs, tránh log assertion thô.
```

## 11. Những quyết định thiết kế nên viết rõ trong dự án

Đối với mỗi SP registration, ghi ngắn gọn:

- **IdP tin cậy:** entityID, endpoint SSO, nguồn metadata và certificate xác minh.
- **SP public identity:** entityID, ACS URL, canonical HTTPS host và binding được chấp nhận.
- **RegistrationId nội bộ:** giá trị và cách resolve, đặc biệt khi có nhiều IdP/tenant.
- **Public URL allowlist:** trang login/asset, AuthnRequest endpoint, ACS, metadata công bố cho IdP và error dispatch.
- **Private URL policy:** trang nghiệp vụ, API, admin, health/management endpoint; phân quyền ngoài việc chỉ authenticated.
- **CSRF:** ngoại lệ đúng ACS trong `saml2Login`; bảo vệ POST có session của ứng dụng.
- **Session:** cookie Secure/HttpOnly, SameSite phù hợp luồng SAML POST và proxy, timeout, session fixation, logout.
- **SLO có hay không:** endpoint và certificate ký riêng; không nhầm logout local với logout IdP.
- **Giám sát:** audit authentication/authorization, lỗi chữ ký/timestamp/issuer, không log raw assertion hay private key.
- **Kiểm thử regression:** cả đường công khai phải còn hoạt động khi user chưa login, và tất cả đường private phải từ chối đúng khi chưa xác thực.

**Điều kiện hoàn thành bài:** Với một IdP test thực sự đã đăng ký, truy cập `/private` khi chưa login sẽ bắt đầu SAML SSO; `AuthnRequest` đưa browser tới đúng IdP; IdP POST `SAMLResponse` hợp lệ về ACS HTTPS; Spring Security xác thực và tạo phiên; user chỉ xem được tài nguyên được phép. GET metadata hoạt động theo chính sách công bố. Các URL không nằm trong allowlist và không có quyền tiếp tục bị chặn. Khi POST sai chữ ký/issuer/audience vào ACS, SP không được tạo phiên.

## 12. Tài liệu tham khảo để đối chiếu với phiên bản đang dùng

1. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — `saml2Login`, `RelyingPartyRegistration`, AuthnRequest/ACS và URI patterns.
2. [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — URL `/saml2/authenticate/{registrationId}`, signing và binding.
3. [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — `saml2Metadata`, metadata endpoint và công bố SP descriptor.
4. [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — thứ tự matcher, `permitAll`, `hasRole`, phân biệt chain matcher và authorization matcher.
5. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — bảo vệ request thay đổi trạng thái và ngoại lệ hẹp theo endpoint.
6. [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html) — SAML SLO, logout request/response, yêu cầu ký và endpoint.
7. [Spring Security — Saml2LoginConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html) — các filter/endpoint được cấu hình trong `saml2Login`.
