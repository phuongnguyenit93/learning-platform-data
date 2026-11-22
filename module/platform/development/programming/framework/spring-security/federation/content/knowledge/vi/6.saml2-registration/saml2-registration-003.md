# Khởi tạo đăng ký bằng RelyingPartyRegistrations và metadata của IdP

**Module:** Spring Security – federation  
**Mạch kiến thức:** Đăng ký SAML2  
**Phạm vi:** Ứng dụng Spring MVC/Servlet đóng vai trò SAML 2.0 Service Provider (SP), Java 17+, Spring Boot 3.x, Spring Security 6.x.

## 1. Bài toán cần giải quyết

Khi ứng dụng tích hợp **SAML 2.0 Single Sign-On (SSO)** với Identity Provider (IdP) của doanh nghiệp, hai bên phải biết cách trao đổi thông điệp, nhận diện nhau và xác minh chữ ký. Nhà cung cấp IdP thường phát hành một **tệp hoặc URL metadata XML** chứa định danh IdP, endpoint đăng nhập và chứng thư công khai dùng để kiểm tra SAML Response/Assertion.

Spring Security cung cấp utility **RelyingPartyRegistrations** để đọc metadata đó và tạo một **RelyingPartyRegistration.Builder**. Sau khi hoàn tất những thông số dành riêng cho ứng dụng SP, ta gọi **build()** thành **RelyingPartyRegistration**, đặt nó vào **RelyingPartyRegistrationRepository**, rồi bật **saml2Login()** trong SecurityFilterChain.

Mục tiêu cuối cùng là một quan hệ tin cậy có cấu hình rõ ràng:

~~~text
                 Metadata XML của IdP (nguồn được duyệt)
                   |  entityID, SSO URL, binding,
                   |  verification certificates, ...
                   v
       RelyingPartyRegistrations.fromMetadataLocation(...)
                   |
                   v
       RelyingPartyRegistration.Builder
                   |  .registrationId("company")
                   |  .entityId(SP entityID)
                   |  .assertionConsumerServiceLocation(SP ACS)
                   |  .signingX509Credentials(...) nếu cần
                   v
            RelyingPartyRegistration
                   |
                   v
       RelyingPartyRegistrationRepository
                   |
             saml2Login()
                   |
              Browser SSO
~~~

**Điều quan trọng:** IdP metadata là thông tin **bên phát hành IdP công bố cho SP**. SP metadata là thông tin **ứng dụng SP công bố cho IdP**. Hai tài liệu có vai trò khác nhau, không thay thế cho nhau.

## 2. Thuật ngữ phải nắm

| Thuật ngữ | Ý nghĩa trong Spring Security SAML2 |
| --- | --- |
| **Identity Provider (IdP)** / **Asserting Party (AP)** | Hệ thống xác thực người dùng và phát hành SAML Assertion/Response. |
| **Service Provider (SP)** / **Relying Party (RP)** | Ứng dụng dựa vào assertion của IdP để thiết lập Authentication/session. |
| **IdP metadata** | XML mô tả IdP: entityID, SSO endpoint, binding, chứng thư công khai dùng xác minh, v.v. |
| **SP metadata** | XML mô tả SP: entityID, ACS endpoint và thông tin certificate/capability của SP. |
| **RelyingPartyRegistrations** | Tiện ích tĩnh để chuyển metadata IdP thành builder; **không phải** repository lưu đăng ký. |
| **RelyingPartyRegistration** | Cấu hình **một cặp SP ↔ IdP/AP**, bao gồm thông tin hai bên. |
| **RelyingPartyRegistrationRepository** | Tra cứu registration theo ID; Spring sử dụng khi tạo request, xử lý callback và xuất metadata. |
| **registrationId** | Khóa nội bộ do ứng dụng đặt, ví dụ **company**; dùng trong URL SAML. |
| **entityID** | Định danh giao thức của IdP hoặc SP; không nhất thiết phải là URL có thể truy cập. |
| **ACS (Assertion Consumer Service)** | Endpoint của SP nhận SAML Response, thường là HTTP POST. |
| **SSO service endpoint** | Endpoint IdP nhận AuthnRequest, có thể dùng binding HTTP-Redirect hoặc HTTP-POST. |
| **SAML binding** | Cách mang SAML message qua HTTP (Redirect, POST, ...). |
| **X.509 certificate** | Chứng thư công khai dùng xác minh chữ ký hoặc mã hóa, tùy vai trò; khác với private key của SP. |

**registrationId ≠ entityID:** **company** là tên dễ nhớ để tra cứu trong ứng dụng, còn **IdP entityID** và **SP entityID** là các định danh dùng trong giao thức SAML. Việc tự đặt registrationId không tự tạo một quan hệ tin cậy với IdP. IdP vẫn phải được cấu hình để nhận SP entityID/ACS hợp lệ.

## 3. IdP metadata XML chứa gì?

Metadata thường sử dụng namespace **urn:oasis:names:tc:SAML:2.0:metadata** và các cấu trúc như:

- **EntityDescriptor entityID:** định danh bên phát hành IdP, ví dụ **https://idp.example.org/saml/company**.
- **IDPSSODescriptor:** mô tả IdP có hỗ trợ SAML 2.0 Web Browser SSO.
- **KeyDescriptor / KeyInfo / X509Certificate:** chứng thư công khai dùng kiểm tra chữ ký SAML Response/Assertion; có thể có nhiều chứng thư để phục vụ luân phiên khóa.
- **SingleSignOnService Binding + Location:** vị trí IdP nhận AuthnRequest qua binding cụ thể.
- **SingleLogoutService:** nếu hỗ trợ single logout; không mặc định cho rằng IdP nào cũng bật hoặc vận hành SLO giống nhau.
- **NameIDFormat:** những định dạng subject identifier mà IdP công bố.
- Các thuộc tính về yêu cầu ký AuthnRequest, metadata validity/cache và khả năng khác tùy IdP.

Ví dụ sau là **mảnh XML minh họa về cấu trúc**, không phải metadata dùng được ngay vì chứng thư đã được thay bằng ký hiệu:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/saml/company">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="false">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>CHUNG_THU_THAT_CUA_IDP</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Ý nghĩa dữ liệu:**

1. **entityID** là danh tính IdP để SP đối chiếu với Issuer trong thông điệp SAML. Không chỉ kiểm tra hostname có chung đuôi.
2. **KeyDescriptor** cung cấp **public certificate**, không chứa private signing key của IdP. SP sử dụng chứng thư đã được tin cậy để kiểm tra chữ ký.
3. **SingleSignOnService** cho Spring biết gửi AuthnRequest đến endpoint nào với binding nào.
4. **WantAuthnRequestsSigned** thể hiện yêu cầu/ưu tiên của IdP đối với AuthnRequest có chữ ký. Nếu yêu cầu ký, SP phải cung cấp cặp khóa/chứng thư ký phù hợp.
5. **SingleLogoutService**, mã hóa assertion, thuật toán, nhiều endpoint và nhiều entity descriptor có thể cần quyết định bổ sung. Tạo registration từ metadata giúp giảm nhập tay, nhưng không thay thế kiểm tra chính sách.

**Chú ý về độ tin cậy:** XML metadata có thể tải thành công nhưng vẫn không phải thông tin đáng tin. Phải lấy từ **IdP đã phê duyệt** qua đường truyền/nguồn được kiểm soát hoặc xác minh chữ ký metadata theo quy trình quản trị. Không tải metadata từ URL do người dùng tùy ý truyền vào request để tạo issuer mới.

## 4. Phân biệt dữ liệu của IdP và SP trong RelyingPartyRegistration

| Thông tin | Đến từ đâu? | Ví dụ | Dùng để làm gì? |
| --- | --- | --- | --- |
| **IdP entityID** | IdP metadata | https://idp.example.org/saml/company | Ràng buộc bên phát hành (Issuer). |
| **IdP SSO URL / binding** | IdP metadata | https://idp.example.org/saml/sso, HTTP-Redirect | Gửi AuthnRequest đúng endpoint. |
| **IdP verification credentials** | IdP metadata đã được tin cậy | Chứng thư X.509 công khai | Xác minh chữ ký SAML. |
| **SP registrationId** | Ứng dụng chọn | company | Tra cứu cấu hình và tạo endpoint trong Spring. |
| **SP entityID** | Ứng dụng/SP xác định, IdP đăng ký | https://app.example.org/saml2/service-provider-metadata/company | Audience/định danh SP theo cấu hình. |
| **SP ACS URL** | Ứng dụng/SP xác định, IdP đăng ký | https://app.example.org/login/saml2/sso/company | Nơi IdP gửi SAMLResponse. |
| **SP signing certificate + private key** | SP quản lý | Cặp khóa do SP sở hữu | Ký AuthnRequest khi yêu cầu. |
| **SP decryption private key** | SP quản lý | Khóa giải mã riêng | Giải mã assertion khi dùng mã hóa. |

**Không tráo chứng thư:** certificate IdP lấy từ metadata dùng xác minh chữ ký IdP. **Private key của SP** dùng ký request/giải mã dữ liệu gửi tới SP, không có trong IdP metadata và không nên đưa lên public metadata.

Một registration chứa cả **asserting party metadata** và **relying party metadata**. Phương thức **RelyingPartyRegistrations.fromMetadataLocation(...)** khởi tạo phần IdP từ XML, nhưng SP vẫn phải chọn **registrationId**, cấu hình entityID/ACS nếu giá trị mặc định chưa phù hợp, và thêm credentials của SP khi giao thức yêu cầu.

## 5. API cốt lõi và những điểm dễ nhầm

### 5.1. Ba kiểu tạo builder

**Từ URL hoặc resource location:**

~~~java
RelyingPartyRegistration.Builder builder =
    RelyingPartyRegistrations.fromMetadataLocation(
        "https://idp.example.org/saml/metadata");
~~~

**Từ tệp nằm trong classpath:**

~~~java
RelyingPartyRegistration.Builder builder =
    RelyingPartyRegistrations.fromMetadataLocation(
        "classpath:metadata/company-idp.xml");
~~~

**Từ InputStream đã được hệ thống tin cậy cung cấp:**

~~~java
try (InputStream in = /* InputStream metadata đáng tin */) {
    RelyingPartyRegistration.Builder builder =
        RelyingPartyRegistrations.fromMetadata(in);
}
~~~

Ba snippet trên là **mã giải thích API**, không phải chương trình Java độc lập; với **fromMetadata(InputStream)** caller có trách nhiệm đóng stream. Các import chính thuộc package **org.springframework.security.saml2.provider.service.registration**.

Metadata location có thể trỏ tới nội dung lưu trong classpath hoặc endpoint HTTPS, tùy ResourceLoader/cơ chế Spring hỗ trợ. URL cần được **kiểm soát và bảo vệ**, không dùng tham số HTTP tùy ý làm đường dẫn.

### 5.2. build() và repository

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("classpath:metadata/company-idp.xml")
        .registrationId("company")
        .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(registration);
~~~

- **RelyingPartyRegistrations** (số nhiều): helper tĩnh để phân tích metadata thành builder.
- **RelyingPartyRegistration** (số ít): đối tượng mô tả **một** cặp SP–IdP.
- **InMemoryRelyingPartyRegistrationRepository:** lưu cấu hình trong bộ nhớ, tra cứu theo ID; không đồng nghĩa IdP đang online hoặc đã kiểm chứng tài khoản.
- **SecurityFilterChain.saml2Login()** sử dụng repository để xác định IdP, endpoint và chứng thư ở thời điểm xử lý.

Nếu ứng dụng tự khai báo **@Bean RelyingPartyRegistrationRepository**, Spring Boot sử dụng bean đó thay cho repository được tự cấu hình từ các thuộc tính mặc định. Không tạo hai cơ chế cấu hình mâu thuẫn rồi kỳ vọng chúng tự gộp.

### 5.3. Các giá trị mặc định đáng nhớ

Trong cấu hình Spring Security SAML2 thường gặp:

- **registrationId:** ví dụ **company**, do bạn chọn rõ.
- **SP entityID mặc định:** **{baseUrl}/saml2/service-provider-metadata/{registrationId}**.
- **ACS URL mặc định:** đường dẫn **/login/saml2/sso/{registrationId}**, được triển khai thành địa chỉ của ứng dụng.
- **SP-initiated login:** **/saml2/authenticate/{registrationId}**, ví dụ **/saml2/authenticate/company**.
- **Metadata SP endpoint** khi bật **saml2Metadata():** **/saml2/metadata** hoặc **/saml2/metadata/{registrationId}**; Spring còn hỗ trợ **/saml2/service-provider-metadata/{registrationId}**.
- **SAMLResponse** thường được POST đến **/login/saml2/sso/{registrationId}** và do **Saml2WebSsoAuthenticationFilter** xử lý.

Đặc biệt: **SP entityID là một định danh**, dù có hình dạng URL. Nó không bắt buộc trỏ đến một trang web đang phục vụ ở URL đó. **Metadata endpoint** là nơi thực sự trả XML mô tả SP. Hai giá trị có thể giống nhau về URL trong nhiều cấu hình, nhưng có vai trò khác nhau.

## 6. Ví dụ Spring Boot 3 + Java 17: khởi tạo repository từ IdP metadata

Mục tiêu ví dụ: ứng dụng tên **staff-portal** đăng nhập qua IdP **company**. Cấu hình IdP metadata được cấp và kiểm duyệt trước, ứng dụng tạo **RelyingPartyRegistrationRepository** trực tiếp bằng API Java.

**Điều kiện để chạy SSO thật:**

1. Có Spring Boot 3.x / Spring Security 6.x trên Java 17+.
2. IdP cung cấp **metadata XML hợp lệ thực tế** và một quan hệ đăng ký SP đã được tạo ở IdP.
3. IdP đã nhận **SP entityID** và **ACS URL** tương ứng; các chính sách ký request, mã hóa và NameID đã thống nhất.
4. URL công khai, TLS, reverse proxy và session/cookie được cấu hình cho môi trường triển khai.

Ví dụ dưới đây **biên dịch trong dự án Boot có đủ dependency**, nhưng sẽ **không thể hoàn thành login** nếu chưa thay IdP metadata mẫu bằng dữ liệu thật. Không tự giả lập chứng thư hoặc phản hồi SAML để “cho chạy được” bằng cách bỏ kiểm tra chữ ký.

### 6.1. pom.xml

Trong dự án Maven sử dụng **spring-boot-starter-parent** hoặc BOM quản lý phiên bản tương thích, thêm các dependency:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

**spring-security-saml2-service-provider** cung cấp chức năng SAML 2.0 RP/SP; đây không phải starter OAuth2 client hay resource server. Một số môi trường cần cấu hình kho artifact nội bộ/được phê duyệt để tải các dependency OpenSAML theo hướng dẫn của phiên bản Spring được sử dụng. Không pha trộn tùy tiện OpenSAML 4/5 với phiên bản Spring Security khác.

### 6.2. application.yml

**src/main/resources/application.yml:**

~~~yaml
app:
  saml:
    idp-metadata-location: classpath:metadata/company-idp.xml

server:
  port: 8080
~~~

Đặt metadata XML thật đã được kiểm duyệt ở **src/main/resources/metadata/company-idp.xml**. Khi đóng gói JAR, classpath resource vẫn được ứng dụng truy cập. Nếu chọn URL HTTPS thay vì classpath, cấu hình có thể là:

~~~yaml
app:
  saml:
    idp-metadata-location: https://idp.example.org/saml/metadata
~~~

Chỉ dùng URL **được duyệt trước**. Nếu tải metadata ở lúc khởi tạo bean mà IdP unavailable, việc xây dựng repository có thể thất bại khiến app không khởi động; một bản metadata đã được kiểm duyệt trong classpath có thể hỗ trợ khởi động ổn định hơn. Ngược lại, metadata classpath là **snapshot**, cần cập nhật/quản lý vòng đời khóa khi IdP thay đổi.

### 6.3. SsoSamlApplication.java

**src/main/java/com/example/saml/SsoSamlApplication.java:**

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SsoSamlApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoSamlApplication.class, args);
    }
}
~~~

### 6.4. SamlSecurityConfig.java: bean đăng ký và chain

**src/main/java/com/example/saml/SamlSecurityConfig.java:**

~~~java
package com.example.saml;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("${app.saml.idp-metadata-location}") String metadataLocation) {

        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(metadataLocation)
                .registrationId("company")
                .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
                .assertionConsumerServiceLocation(
                    "{baseUrl}/login/saml2/sso/{registrationId}")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/",
                    "/error",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**")
                .permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Giải thích từng lớp:**

- **RelyingPartyRegistrations.fromMetadataLocation(metadataLocation):** phân tích XML IdP thành builder có thông tin IdP như entityID/SSO/certificate.
- **registrationId("company"):** định danh ổn định của cấu hình, dùng trong URL **/saml2/authenticate/company** và **/login/saml2/sso/company**.
- **entityId(...):** chỉ định định danh SP sẽ thông báo cho IdP. Ví dụ khi triển khai tại **https://portal.example.org**, entityID trở thành **https://portal.example.org/saml2/service-provider-metadata/company**.
- **assertionConsumerServiceLocation(...):** địa chỉ ACS mà IdP phải gửi SAML Response tới. Với public base URL như trên là **https://portal.example.org/login/saml2/sso/company**.
- **InMemoryRelyingPartyRegistrationRepository:** lưu registration; Spring có thể tìm theo ID khi tạo AuthnRequest hoặc tiếp nhận Response.
- **saml2Login():** đăng ký filter/login flow SAML2, ví dụ **Saml2WebSsoAuthenticationRequestFilter** và **Saml2WebSsoAuthenticationFilter**.
- **saml2Metadata():** bật xuất SP metadata cho IdP. Không nhầm với **RelyingPartyRegistrations** là phần **đọc IdP metadata**.
- **requestMatchers(...).permitAll():** cho phép tải metadata SP dễ dàng để đăng ký với IdP; trong hệ thống thật có thể giới hạn quyền truy cập metadata tùy chính sách. **permitAll** không có nghĩa bỏ qua validation của SAML Response.
- **anyRequest().authenticated():** mọi endpoint nghiệp vụ còn lại yêu cầu đăng nhập.

**CSRF:** SAML Web Browser SSO theo HTTP POST cần hoạt động tại ACS. Khi dùng cấu hình **saml2Login()** chuẩn, Spring Security thiết lập ngoại lệ CSRF thích hợp cho endpoint xử lý SAML; không tắt CSRF toàn ứng dụng bằng **csrf.disable()**. Nếu đổi loginProcessingUrl, kiểm tra lại matcher CSRF và cấu hình cùng một đường dẫn với ACS.

**Metadata nguồn và runtime:** ví dụ chỉ khởi tạo repository khi bean được tạo. Nó không tự hẹn giờ tải mới metadata IdP mỗi vài phút. Nếu IdP luân phiên chứng thư, cần cơ chế cập nhật/reload và kế hoạch chấp nhận nhiều certificate trong giai đoạn chuyển tiếp.

### 6.5. SamlController.java: điểm truy cập để quan sát

**src/main/java/com/example/saml/SamlController.java:**

~~~java
package com.example.saml;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlController {

    @GetMapping("/")
    public String home() {
        return "SAML SP is running";
    }

    @GetMapping("/me")
    public String currentUser(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID: " + principal.getName()
            + ", registrationId: " + principal.getRelyingPartyRegistrationId();
    }
}
~~~

Khi người dùng chưa đăng nhập vào **/me**, Spring sẽ khởi động SAML2 login; khi đăng nhập thành công, controller có thể đọc principal **Saml2AuthenticatedPrincipal**. **NameID** có thể là định danh dài, opaque hoặc thay đổi theo cấu hình IdP; không tự giả định là email hoặc khóa vĩnh viễn của hệ thống.

### 6.6. Chạy và quan sát

Sau khi cấu hình metadata thật, chạy trong thư mục Maven của dự án:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint không cần đăng nhập:

~~~bash
curl -i http://localhost:8080/
~~~

Nội dung response body từ controller:

~~~text
SAML SP is running
~~~

Để xem **SP metadata**, khi ứng dụng đang chạy:

~~~bash
curl -i http://localhost:8080/saml2/metadata/company
~~~

Nếu endpoint khả dụng, response trả **XML metadata SP**; nội dung thực tế phụ thuộc public base URL, registration và cấu hình credentials. Không có stdout XML cố định để chép sẵn vì đó là dữ liệu chạy thực tế.

Trên trình duyệt, bắt đầu **SP-initiated SSO**:

~~~text
http://localhost:8080/saml2/authenticate/company
~~~

Với IdP đã đăng ký đúng, trình duyệt được chuyển tới IdP, thực hiện login, sau đó IdP gửi **SAMLResponse** về ACS **/login/saml2/sso/company**. Nếu response hợp lệ, ứng dụng tạo Authentication/session và cho phép truy cập **/me**.

**Thận trọng khi thử local:** Nếu IdP chỉ chấp nhận ACS HTTPS public, **http://localhost:8080** sẽ không khớp. Cần môi trường kiểm thử có public URL, cấu hình proxy/port và SP entityID/ACS đã đăng ký chính xác. Không giải quyết sai ACS bằng cách tắt Audience/Recipient/Signature validation.

## 7. Trao đổi metadata hai chiều giữa IdP và SP

Đây là quy trình triển khai thực tế khuyến nghị:

1. **Nhận metadata từ IdP:** quản trị IdP cung cấp URL HTTPS/tệp XML qua kênh được phê duyệt; xác định đúng tenant/environment (dev/staging/prod).
2. **Kiểm tra metadata:** đối chiếu **IdP entityID**, endpoint SSO, certificate, yêu cầu ký AuthnRequest, binding, thời hạn và dữ liệu liên quan với thông tin được bàn giao.
3. **Tạo RelyingPartyRegistration:** dùng **RelyingPartyRegistrations.fromMetadataLocation()**, chọn **registrationId ổn định**, kiểm soát SP entityID và ACS.
4. **Cấu hình keys của SP** nếu IdP yêu cầu AuthnRequest ký hoặc mã hóa assertion (xem mục 8).
5. **Xuất SP metadata:** bật **saml2Metadata()**, mở URL **/saml2/metadata/company**, kiểm tra EntityID và ACS trong XML.
6. **Đăng ký SP ở IdP:** upload SP metadata hoặc nhập thủ công đúng **SP entityID / ACS / chứng thư ký hoặc mã hóa**.
7. **Kích hoạt tin cậy ở IdP:** IdP duyệt ứng dụng, policy người dùng/nhóm, yêu cầu ký và định dạng NameID.
8. **Kiểm thử SSO hai chiều:** kiểm tra SP-initiated; kiểm thử IdP-initiated nếu IdP và ứng dụng hỗ trợ/phê duyệt; xác nhận Issuer, Audience, Recipient, InResponseTo/time và chữ ký.
9. **Chốt vận hành:** giám sát certificate rotation, thay đổi endpoint, metadata validity, session và quy trình rollback.

Đăng ký chỉ một phía thường không đủ: SP phải biết IdP đáng tin; **IdP cũng phải biết và cho phép SP**. Nếu SP metadata có ACS/domain khác với cấu hình lưu ở IdP, login thất bại hoặc bị từ chối.

## 8. Khi cần ký AuthnRequest hoặc giải mã assertion

Metadata IdP có thể yêu cầu **WantAuthnRequestsSigned=true**. Trong trường hợp đó, SP cần cặp **private key + certificate** dành cho signing, được khai báo trong **RelyingPartyRegistration**. Cấu hình mẫu một phần:

~~~java
// Những biến sau phải được cung cấp từ nơi lưu bí mật an toàn:
PrivateKey spPrivateKey = /* khóa riêng SP đã nạp an toàn */;
X509Certificate spCertificate = /* certificate tương ứng */;

Saml2X509Credential signing =
    Saml2X509Credential.signing(spPrivateKey, spCertificate);

RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation(trustedMetadataLocation)
        .registrationId("company")
        .signingX509Credentials(credentials -> credentials.add(signing))
        .build();
~~~

Đây là **minh họa cách bổ sung credentials**, không phải một class độc lập chạy được: **spPrivateKey**, **spCertificate** và **trustedMetadataLocation** cần được ứng dụng cung cấp; import **java.security.PrivateKey**, **java.security.cert.X509Certificate**, **org.springframework.security.saml2.core.Saml2X509Credential** và các lớp registration. Không copy các dấu chú thích **/* ... */** làm giá trị thật.

- **signingX509Credentials** là credentials của **SP**, không phải certificate xác minh của IdP.
- Đối với assertion mã hóa, SP cần **decryptionX509Credentials** với khóa riêng và certificate của SP theo cấu hình IdP.
- Chứng thư xác minh chữ ký **IdP** được cung cấp từ IdP metadata và nằm trong asserting-party metadata.
- Việc ứng dụng có khóa ký **không đồng nghĩa mọi AuthnRequest luôn được ký**: còn phụ thuộc yêu cầu IdP, binding, cấu hình ký và cách Spring xây AuthnRequest.
- IdP có thể yêu cầu certificate ký của SP được upload trước; hãy kiểm tra **SP metadata** thực sự công bố certificate thích hợp và phù hợp chính sách IdP.
- Không nhúng private key vào mã nguồn, Git, log hoặc metadata XML công khai. Sử dụng secret manager, keystore hoặc cơ chế quản lý khóa được phê duyệt.

Nếu IdP không yêu cầu AuthnRequest ký, ví dụ cơ bản ở mục 6 có thể đủ cho login; nhưng không được suy ra tất cả IdP cho phép request không ký.

## 9. Những biến thể của nguồn metadata

### 9.1. Metadata từ URL HTTPS

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("https://idp.example.org/metadata.xml")
        .registrationId("company")
        .build();
~~~

**Ưu điểm:** ít nhập tay, có thể lấy dữ liệu phù hợp với cấu hình IdP được quản trị. **Rủi ro:** phụ thuộc mạng/IdP tại thời điểm đọc; URL sai hoặc bị thay nguồn có thể làm hỏng cấu hình trust. Không có nghĩa runtime tự refresh metadata khi IdP đổi key.

### 9.2. Metadata được đóng gói cùng ứng dụng

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("classpath:metadata/company-idp.xml")
        .registrationId("company")
        .build();
~~~

**Ưu điểm:** triển khai có thể tái lập, dễ kiểm soát biến đổi và rollback qua quy trình phát hành ứng dụng. **Rủi ro:** metadata/certificate bị cũ nếu không cập nhật theo kế hoạch rotation. Sử dụng kênh tải và duyệt tệp ban đầu an toàn.

### 9.3. Metadata từ database qua InputStream

Nếu hệ thống lưu một **snapshot metadata XML đã được duyệt** trong database, có thể cấp InputStream:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

public final class MetadataRegistrationFactory {

    private MetadataRegistrationFactory() { }

    public static RelyingPartyRegistration fromTrustedXml(String xml) {
        try (InputStream input = new ByteArrayInputStream(
                xml.getBytes(StandardCharsets.UTF_8))) {
            return RelyingPartyRegistrations
                .fromMetadata(input)
                .registrationId("company")
                .build();
        } catch (java.io.IOException exception) {
            throw new IllegalStateException(
                "Cannot close metadata stream", exception);
        }
    }
}
~~~

Đây là class Java có thể **biên dịch trong dự án có dependency SAML2 Spring Security**, nhưng nó chỉ là **factory cho metadata đã được tin cậy**. Không truyền thẳng XML tùy ý từ HTTP request hoặc một bảng dữ liệu mà người dùng có thể sửa tự do. Nếu luồng XML invalid, việc parse/build có thể phát sinh exception tương ứng; code trên chỉ minh họa xử lý lỗi **IOException khi đóng stream**.

### 9.4. Metadata chứa nhiều IdP entity

Một metadata document có thể chứa **EntitiesDescriptor** hoặc nhiều **IDPSSODescriptor**. API **collectionFromMetadataLocation(...)** trả tập builder:

~~~java
Collection<RelyingPartyRegistration.Builder> builders =
    RelyingPartyRegistrations.collectionFromMetadataLocation(metadataLocation);
~~~

Cần **quy tắc chọn IdP/định danh ổn định** và tạo **registrationId khác nhau** cho từng registration trước khi build/repository. Không lấy đại phần tử đầu tiên nếu không xác định được nhà phát hành, không dùng UUID ngẫu nhiên mỗi lần khởi động nếu URL/định danh của ứng dụng phải ổn định. Với các IdP khác nhau, SP cần allowlist tin cậy, mapping endpoint và chính sách tenant phù hợp. Mỗi registration tương ứng một quan hệ RP–AP đã được duyệt.

## 10. Nhiều IdP: đăng ký tường minh trong cùng repository

Khi hỗ trợ hai IdP đã được duyệt (ví dụ công ty và đối tác), có thể tạo hai registration độc lập:

~~~java
@Bean
RelyingPartyRegistrationRepository relyingPartyRegistrations() {
    RelyingPartyRegistration company =
        RelyingPartyRegistrations
            .fromMetadataLocation(
                "classpath:metadata/company-idp.xml")
            .registrationId("company")
            .build();

    RelyingPartyRegistration partner =
        RelyingPartyRegistrations
            .fromMetadataLocation(
                "classpath:metadata/partner-idp.xml")
            .registrationId("partner")
            .build();

    return new InMemoryRelyingPartyRegistrationRepository(
        company, partner);
}
~~~

**Đây là một bean thay thế** cho bean ở ví dụ mục 6, không đặt cả hai vào cùng project với cùng bean name rồi kỳ vọng Spring tự hợp nhất. Từng registration được nạp từ metadata tương ứng và phải đăng ký SP/ACS với đúng IdP.

- **/saml2/authenticate/company** khởi tạo login tới IdP company.
- **/saml2/authenticate/partner** khởi tạo login tới IdP partner.
- Các callback tương ứng dùng registrationId hoặc trạng thái AuthnRequest để Spring tìm đúng registration.
- IdP partner không tự động được phép cấp quyền như IdP company: danh tính, nhóm và role phải được mapping theo chính sách từng bên.
- Không phân biệt hai người dùng bằng NameID/email **đơn lẻ** khi IdP khác nhau; liên kết tài khoản cần dựa trên định danh IdP đã xác minh + subject phù hợp.
- SP entityID và ACS có thể khác nhau theo registrationId mặc định. Nếu muốn **SP entityID/ACS chung**, cần cấu hình cẩn thận theo federation profile và bảo đảm cách tìm registration lúc nhận Response là đúng, không chỉ sửa URL theo sở thích.

**InMemoryRelyingPartyRegistrationRepository** thích hợp cho danh sách nhỏ và cấu hình không đổi thường xuyên. Với hệ thống cần quản lý metadata động, tạo repository có kiểm soát, tính toàn vẹn cấu hình và caching/refresh. Không dùng database/URL điều khiển bởi người dùng để mở rộng IdP trust tức thì.

## 11. Quản trị metadata và certificate rotation

### 11.1. Metadata không phải cơ chế “luôn cập nhật tự động”

Lệnh **fromMetadataLocation(...)** đọc metadata khi được gọi để xây builder; registration đã build và lưu trong **InMemoryRelyingPartyRegistrationRepository** là cấu hình ở thời điểm đó. Nếu IdP thay chứng thư ký ngày hôm sau, repository cũ **không tự biết** nếu không có cơ chế refresh/redeploy tương ứng.

Có thể thiết kế một repository cập nhật định kỳ với cache/supplier theo API Spring Security phù hợp phiên bản, hoặc triển khai pipeline cập nhật artifact metadata đã duyệt. Khi làm vậy cần:

- Chỉ tải từ **IdP location đã được duyệt**, hạn chế SSRF, redirect ra domain lạ và giới hạn thời gian chờ/kích thước XML.
- Xác thực metadata theo kênh tin cậy; nếu IdP có chữ ký metadata, sử dụng quy trình xác minh chữ ký và trust anchor phù hợp.
- Hỗ trợ certificate rotation có giai đoạn **overlap** giữa chứng thư cũ/mới theo chính sách IdP.
- Phân biệt thay đổi certificate hợp lệ với IdP bị thay thế hoặc metadata bất thường.
- Giữ cấu hình last-known-good nếu policy cho phép và có cơ chế báo lỗi; không tự “bỏ xác minh chữ ký để phục hồi SSO”.
- Thay đổi metadata có kiểm toán, rollback và smoke test tại staging trước production.

### 11.2. SP credential rotation khác IdP credential rotation

- **IdP verification certificates:** được SP dùng để kiểm tra chữ ký từ IdP, thường đến từ metadata IdP.
- **SP signing credentials:** dùng cho AuthnRequest ký; private key phải do SP giữ.
- **SP decryption credentials:** dùng giải mã dữ liệu mà IdP mã hóa cho SP.
- Khi luân phiên certificate SP, phải cập nhật SP metadata và đăng ký tương ứng ở IdP. Khi luân phiên certificate IdP, phải cập nhật thông tin xác minh IdP tin cậy.
- Không xóa khóa cũ quá sớm khi các hệ thống còn đang sử dụng dữ liệu đã ký/mã hóa bằng khóa cũ.

### 11.3. Validation của SAML Response vẫn quan trọng

RelyingPartyRegistration chỉ là **cấu hình trust và endpoint**. Khi nhận SAMLResponse, Spring Security/OpenSAML còn cần kiểm tra theo profile:

- **Chữ ký** của Response/Assertion bằng certificate phù hợp từ IdP được tin.
- **Issuer** đúng IdP/AP đã đăng ký.
- **AudienceRestriction** chứa SP entityID phù hợp.
- **SubjectConfirmationData.Recipient** và **Destination** đúng ACS/callback.
- **Conditions (NotBefore/NotOnOrAfter)** và session/time/skew.
- **InResponseTo** cho SP-initiated login, trạng thái request và chống replay.
- Định dạng NameID, thuộc tính và chính sách người dùng sau khi xác thực.

Không coi một XML parser thành công hoặc signature từ bất kỳ certificate nào là đăng nhập thành công. Hãy dùng filter/provider chuẩn, không tự viết controller đọc Base64 SAMLResponse rồi lấy NameID mà bỏ qua validation.

## 12. Reverse proxy, tên miền công khai và tính ổn định của ACS

Khi Spring Boot chạy nội bộ tại **http://127.0.0.1:8080** nhưng public URL là **https://portal.example.org**, các placeholder như **{baseUrl}** phải giải quyết theo **public URL** mà IdP được đăng ký. Sai scheme/host/port có thể làm:

- SP metadata xuất **http://...** hoặc hostname nội bộ.
- IdP từ chối AuthnRequest hoặc không chấp nhận ACS URL.
- SAML Response gửi đến URL không được Spring route đúng.
- Kiểm tra Audience/Recipient/Destination thất bại.

Định hướng xử lý:

1. Đăng ký **SP entityID và ACS chính xác** theo public URL trên IdP.
2. Cấu hình reverse proxy chuyển tiếp **Forwarded / X-Forwarded-*** đáng tin; Spring chỉ nên tin những headers do proxy được quản lý gửi.
3. Khi cần cố định SP entityID và ACS, đặt giá trị HTTPS public tường minh trong builder.
4. Kiểm tra XML từ **/saml2/metadata/company** khi truy cập qua domain production và so sánh với IdP.
5. Không cho client tùy ý gửi Host/X-Forwarded-Host để ảnh hưởng entityID/ACS (host-header poisoning).

Ví dụ cấu hình tường minh:

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("classpath:metadata/company-idp.xml")
        .registrationId("company")
        .entityId("https://portal.example.org/saml2/sp/company")
        .assertionConsumerServiceLocation(
            "https://portal.example.org/login/saml2/sso/company")
        .build();
~~~

Nếu SP entityID khác với URL metadata, điều đó vẫn hợp lệ theo SAML khi IdP và SP thống nhất, miễn các định danh/đích nhận được kiểm tra chính xác. Chỉ sử dụng hostname **example.org** làm minh họa; không giả định dịch vụ thật tồn tại.

## 13. Kiểm tra kết quả khởi tạo repository

Khi tạo bean thành công, có thể dùng code Java để quan sát những giá trị cần thiết mà **không in private key, token, certificate nhạy cảm**.

Ví dụ một bean đơn giản trong dự án Spring Boot:

~~~java
package com.example.saml;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;

@Configuration
public class RegistrationDiagnostics {

    @Bean
    ApplicationRunner printRegistration(
            RelyingPartyRegistrationRepository repository) {

        return args -> {
            RelyingPartyRegistration rp =
                repository.findByRegistrationId("company");
            if (rp == null) {
                throw new IllegalStateException("Missing company registration");
            }

            System.out.println("registrationId=" + rp.getRegistrationId());
            System.out.println("spEntityId=" + rp.getEntityId());
            System.out.println("idpEntityId="
                + rp.getAssertingPartyMetadata().getEntityId());
            System.out.println("acs=" + rp.getAssertionConsumerServiceLocation());
        };
    }
}
~~~

**Đây là class có thể biên dịch trong dự án Boot dùng các dependency nêu trên**. Tuy nhiên giá trị **spEntityId** và **acs** được tính theo cấu hình và ngữ cảnh runtime, nên **không có stdout cố định** phù hợp mọi môi trường. Những dòng như sau chỉ là **mẫu theo public URL giả định**, không phải kết quả được bảo đảm:

~~~text
registrationId=company
spEntityId=https://portal.example.org/saml2/service-provider-metadata/company
idpEntityId=https://idp.example.org/saml/company
acs=https://portal.example.org/login/saml2/sso/company
~~~

Trong production, thông thường không cần bean chẩn đoán này; dùng log có kiểm soát, kiểm tra metadata đầu ra và công cụ quan sát an toàn. Nếu metadata XML chứa nhiều entity hoặc các giá trị sai khác, hãy kiểm tra **đầu vào đã duyệt và registration** thay vì chỉ sửa stdout để khớp kỳ vọng.

## 14. Lỗi thường gặp khi tạo RelyingPartyRegistration

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| App không khởi động khi nạp registration | URL metadata lỗi/timeout, file classpath thiếu, XML không đúng định dạng hoặc không có IdP descriptor phù hợp | Kiểm tra nguồn metadata đã duyệt, URL/tệp, nội dung XML, khả năng truy cập và lỗi parse |
| Đã có metadata nhưng không tìm được registration | **registrationId** khác đường dẫn login/callback hoặc repository không chứa ID đó | Dùng một ID ổn định xuyên suốt và đối chiếu URL |
| Nhấn login nhưng không redirect tới IdP | Chưa bật **saml2Login()**, chain/matcher không bao phủ đường dẫn hoặc metadata không có SSO service phù hợp | Kiểm tra SecurityFilterChain, endpoint và binding |
| 404/403 tại ACS | IdP gửi tới URL không khớp, proxy sai, callback không nằm trong chain, CSRF bị tùy biến sai | So sánh ACS đã đăng ký, endpoint Spring và forwarding |
| IdP từ chối AuthnRequest | SP entityID/ACS không được đăng ký; IdP đòi request ký nhưng SP thiếu signing credential | So sánh SP metadata và cấu hình IdP, bổ sung signing credentials an toàn |
| SAMLResponse có chữ ký không được chấp nhận | Certificate IdP đang dùng khác certificate tin cậy, metadata đã lỗi thời hoặc chain validation lỗi | Kiểm tra IdP rotation/metadata, không bỏ signature validation |
| AudienceRestriction/Recipient/Destination mismatch | SP entityID hoặc ACS không giống giá trị IdP sử dụng | Cập nhật cấu hình hai bên chính xác, tránh sửa workaround |
| AuthnRequest thành công nhưng login fail do InResponseTo | Browser mất phiên/request correlation, nhiều node không chia sẻ session hoặc unsolicited response không được policy chấp nhận | Kiểm tra session, cookie, sticky session/distributed store và policy SP-initiated |
| Có nhiều IdP và user được ánh xạ sai | Định danh NameID/email không unique giữa IdP | Liên kết identity theo IdP issuer và subject đã xác minh |
| Chứng thư IdP thay và SSO ngừng | Repository snapshot hoặc metadata classpath chưa được cập nhật | Áp dụng kế hoạch certificate overlap/refresh |
| SP metadata không mở được | Chưa bật **saml2Metadata()** hoặc endpoint bị authorization chặn | Bật filter xuất metadata và cho phép GET endpoint phù hợp |
| IdP cấu hình HTTP nhưng ứng dụng public HTTPS | Forwarded headers/baseUrl sai hoặc URL tường minh chưa cập nhật | Sửa reverse proxy và đồng bộ SP metadata/IdP |

Các lỗi cụ thể và status code tùy binding, IdP, Spring Security version và cấu hình callback. Hãy xem thông báo lỗi đã được lọc dữ liệu nhạy cảm; tránh log đầy đủ **SAMLResponse**, session cookie, private key hoặc thông tin nhận dạng người dùng.

## 15. Bài tập kiểm tra hiểu biết

### Câu 1 – Vì sao phải dùng metadata IdP đã duyệt?

Một HTTP request đưa lên URL mới, SP tải metadata và tạo repository theo URL đó. Vấn đề là gì?

**Trả lời:** URL do client đưa lên không phải một trust anchor. Attacker có thể chỉ tới IdP do họ kiểm soát, cung cấp certificate và issuer giả nhưng tự nhất quán, dẫn đến xác thực sai nguồn; còn có rủi ro SSRF. Chỉ chọn từ allowlist IdP đã phê duyệt hoặc từ cấu hình quản trị có kiểm toán.

### Câu 2 – Vì sao đã đọc IdP metadata mà vẫn phải đăng ký SP ở IdP?

**Trả lời:** Metadata IdP cho SP biết IdP. IdP còn phải biết **SP entityID**, **ACS**, chứng thư/capability của SP và chính sách truy cập. Quan hệ liên kết là hai chiều.

### Câu 3 – registrationId có bắt buộc trùng IdP entityID?

**Trả lời:** Không. registrationId là khóa nội bộ (**company**), IdP entityID là định danh do IdP công bố; không thể thay thế nhau. Đường dẫn Spring thường chứa registrationId.

### Câu 4 – SP có thể dùng certificate trong IdP metadata để ký AuthnRequest?

**Trả lời:** Không. Certificate của IdP là khóa công khai phục vụ xác minh chữ ký IdP. SP cần **private key + certificate riêng** để ký AuthnRequest khi có yêu cầu.

### Câu 5 – Đã gọi fromMetadataLocation một lần, IdP đổi certificate thì tự cập nhật?

**Trả lời:** Không. Builder/repository tạo từ metadata là trạng thái lúc nạp. Cần refresh/reload theo chiến lược đã quản trị, hỗ trợ rotation và kiểm chứng metadata mới.

### Câu 6 – Nếu chỉ có một IdP, có cần tự viết controller xử lý POST SAMLResponse không?

**Trả lời:** Không. Kích hoạt **saml2Login()**, đăng ký repository và để **Saml2WebSsoAuthenticationFilter** cùng provider của Spring Security xác minh Response/Assertion. Tự giải mã Base64 rồi đọc NameID mà không kiểm tra đầy đủ là nguy hiểm.

### Câu 7 – Metadata SP được tạo từ đâu?

**Trả lời:** Spring Security có thể xuất SP metadata từ **RelyingPartyRegistration** khi bật **saml2Metadata()**, thường tại **/saml2/metadata/company**. IdP dùng metadata SP để biết entityID và ACS, còn SP dùng IdP metadata để tạo builder.

### Câu 8 – Khi ứng dụng đặt sau reverse proxy, thành phần nào phải nhất quán?

**Trả lời:** Public base URL, SP entityID, ACS, reverse-proxy forwarded headers, metadata SP và thông tin đã lưu tại IdP. Không tự sửa response validation để qua lỗi URL.

## 16. Checklist triển khai

- [ ] Nhận **IdP metadata đúng tenant/môi trường** qua kênh tin cậy; kiểm tra entityID, SSO endpoint, binding và signing certificate.
- [ ] Chọn **registrationId** ổn định, khác nhau cho từng quan hệ SP–IdP.
- [ ] Dùng **RelyingPartyRegistrations.fromMetadataLocation(...)** hoặc **fromMetadata(InputStream)** từ nguồn đã duyệt, rồi **build()**.
- [ ] Khai báo một **RelyingPartyRegistrationRepository** được Spring sử dụng; không trùng bean gây mâu thuẫn.
- [ ] Xác định rõ **SP entityID và ACS**, nhất là khi đặt sau proxy/multiple domains.
- [ ] Cấu hình **SP signing/decryption credentials** nếu IdP yêu cầu, lưu private key an toàn.
- [ ] Bật **saml2Login()** cho SP và **saml2Metadata()** khi cần xuất metadata.
- [ ] Đăng ký **SP metadata** ở IdP; đối chiếu entityID, ACS, binding, certificate/policy hai bên.
- [ ] Kiểm thử SP-initiated SSO, callback POST, response signature, issuer, audience, recipient, thời hạn và request correlation.
- [ ] Có chính sách kiểm soát **IdP metadata trust**, certificate rotation, cache/reload, rollback và giám sát.
- [ ] Phân quyền/ghép tài khoản sau login theo IdP issuer + subject; không tự cho admin vì assertion hợp lệ.

**Ghi nhớ:** **RelyingPartyRegistrations** giúp biến **IdP metadata được tin cậy** thành cấu hình; **RelyingPartyRegistration** mô tả quan hệ **SP–IdP**, và **RelyingPartyRegistrationRepository** cung cấp cấu hình đó cho các filter SAML2. Muốn SSO vận hành an toàn, SP metadata/ACS, khóa ký và quan hệ tin cậy tại IdP phải khớp nhau.

## 17. Tài liệu tham khảo

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): metadata IdP, repository, registration builder và endpoints.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html): phân tích IdP metadata, xuất SP metadata với saml2Metadata().
- [Spring Security – SAML Authentication Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html): AuthnRequest, binding và ký request.
- [Spring Security – SAML Authentication Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): xử lý SAMLResponse và các bước xác minh.
- [RelyingPartyRegistrations API – Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html): fromMetadataLocation, fromMetadata, collectionFromMetadataLocation.
- [OASIS SAML V2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): cấu trúc metadata entity, endpoint và certificate.
