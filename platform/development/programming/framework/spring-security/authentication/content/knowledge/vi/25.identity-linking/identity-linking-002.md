# SAML2 Login: Service Provider, Identity Provider và Assertion

## 1. Mục tiêu và bối cảnh

**SAML 2.0 Login** là cách một ứng dụng web cho phép người dùng đăng nhập thông qua hệ thống danh tính bên ngoài. Trong Spring Security, ứng dụng đóng vai trò **Service Provider (SP)**, còn hệ thống xác thực (ví dụ ADFS, Keycloak hoặc một IdP doanh nghiệp có hỗ trợ SAML) đóng vai trò **Identity Provider (IdP)**. Sau khi xác thực người dùng, IdP gửi về thông điệp SAML có chứa **Assertion** để SP kiểm tra và tạo phiên đăng nhập của ứng dụng.

Sau bài học, bạn cần:

- Phân biệt **SP / Relying Party**, **IdP / Asserting Party**, **Assertion**, **SAML Response**, **Metadata**, **Entity ID**, **ACS** và **NameID**.
- Mô tả được luồng **SP-initiated SSO** và phân biệt với **IdP-initiated SSO**.
- Hiểu Spring Security sinh `AuthnRequest`, nhận `SAMLResponse`, xác minh chữ ký/điều kiện của assertion rồi tạo `Saml2Authentication`.
- Cấu hình một ứng dụng **Spring Boot 3.x + Spring Security 6.x (Servlet, Java 17+)** làm Service Provider bằng `RelyingPartyRegistrationRepository` và `HttpSecurity.saml2Login(...)`.
- Biết đọc các trường thường gặp trong assertion, ánh xạ danh tính và quyền, kiểm thử happy path/failure path, xử lý lỗi SSO qua reverse proxy.
- Hiểu khác biệt quan trọng khi làm việc với Spring Security 5.x/6.x/7.x; tránh dùng API đã thay đổi theo phiên bản.

**Giới hạn bài:** SAML 2.0 **Web Browser SSO Profile** của Spring Security Servlet. Đây là đăng nhập dựa trên **XML assertions**, không phải giao thức OAuth 2.0 Authorization Code hoặc OpenID Connect (OIDC). Một ứng dụng cần IdP thật hoặc IdP thử nghiệm được cấu hình tin cậy mới có thể chạy toàn bộ luồng end-to-end.

## 2. Các vai trò: SP, IdP, trình duyệt và người dùng

| Vai trò | Tên trong Spring Security | Trách nhiệm |
| --- | --- | --- |
| **Service Provider (SP)** | **Relying Party** | Ứng dụng cần biết ai đang truy cập, gửi yêu cầu xác thực, tiếp nhận và xác minh SAML Response, thiết lập session/quyền |
| **Identity Provider (IdP)** | **Asserting Party** | Xác thực người dùng bằng cơ chế của tổ chức (mật khẩu, MFA, khóa bảo mật...), ký assertion và trả kết quả cho SP |
| **Browser (User Agent)** | Trình duyệt người dùng | Chuyển hướng tới IdP và gửi HTTP POST/Redirect mang SAML message; trình duyệt là môi trường **không đáng tin cậy** đối với nội dung message |
| **User** | `Principal` sau xác thực | Cá nhân hoặc tài khoản đăng nhập; chính sách quyền trong từng ứng dụng do SP quyết định |

Ví dụ:

```text
SP:      https://app.example.org
IdP:     https://login.example.org
User:    linh@example.org

SP Entity ID:  https://app.example.org/saml2/service-provider-metadata/company-idp
IdP Entity ID: https://login.example.org/idp
ACS:          https://app.example.org/login/saml2/sso/company-idp
```

`Entity ID` là **định danh logic** của một entity SAML, thường biểu diễn bằng URI. Nó **không nhất thiết là URL có thể mở bằng trình duyệt**. `ACS` (*Assertion Consumer Service*) mới là nơi SP nhận SAML Response. Hai giá trị phải đăng ký/thỏa thuận đúng giữa SP và IdP.

Trong Spring Security, một cặp SP–IdP được mô tả bởi `RelyingPartyRegistration`; `registrationId` như `company-idp` là **khóa nội bộ** để chọn cấu hình, khác với cả hai Entity ID.

## 3. SAML Assertion là gì? Phân biệt với SAML Response

**Assertion** là tuyên bố do IdP phát hành về một subject. Với SAML 2.0, assertion có thể mang:

- `Issuer`: entity đã phát hành assertion.
- `Subject` và `NameID`: danh tính của subject, chẳng hạn một mã user ổn định.
- `SubjectConfirmation`: điều kiện xác nhận subject; trong Browser SSO thường là **bearer** cùng `Recipient`, `InResponseTo`, `NotOnOrAfter`.
- `Conditions`: thời gian hợp lệ (`NotBefore`, `NotOnOrAfter`), `AudienceRestriction` nhằm giới hạn SP được nhận.
- `AuthnStatement`: thông tin về lần xác thực, thời điểm xác thực và đôi khi session index, authentication context.
- `AttributeStatement`: thuộc tính bổ sung như email, tên hiển thị hoặc nhóm; **chưa mặc nhiên là quyền của ứng dụng**.

**SAML Response** là thông điệp bao bên ngoài, mang status và một hoặc nhiều assertion (có thể được mã hóa). Response và assertion đều có thể có chữ ký XML theo cấu hình IdP và binding. Trình duyệt thường gửi `SAMLResponse` (mã hóa Base64) trong form POST tới ACS.

Ví dụ XML **sơ đồ đọc hiểu**, không phải SAML Response hoàn chỉnh hoặc có chữ ký hợp lệ:

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response123"
    InResponseTo="_request789"
    Destination="https://app.example.org/login/saml2/sso/company-idp">
  <saml:Issuer>https://login.example.org/idp</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion456">
    <saml:Issuer>https://login.example.org/idp</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user-7392</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            InResponseTo="_request789"
            Recipient="https://app.example.org/login/saml2/sso/company-idp"
            NotOnOrAfter="2030-01-01T10:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions
        NotBefore="2030-01-01T09:59:00Z"
        NotOnOrAfter="2030-01-01T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://app.example.org/saml2/service-provider-metadata/company-idp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="2030-01-01T10:00:00Z"/>
    <saml:AttributeStatement>
      <saml:Attribute Name="email">
        <saml:AttributeValue>linh@example.org</saml:AttributeValue>
      </saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>
```

**Không gửi XML mẫu này tới ACS để thử đăng nhập.** Nó cố ý lược bỏ chữ ký, namespace/type của một số phần tử và các ràng buộc giao thức. `InResponseTo` không được đặt tùy ý: nó phải liên hệ đúng yêu cầu xác thực đã gửi. `NotOnOrAfter` là mốc **không còn hợp lệ**; so sánh thời gian phải theo UTC và dung sai đồng hồ có kiểm soát.

Chữ ký XML bảo vệ tính toàn vẹn và xác định bên phát hành đã được tin cậy. **Base64 không mã hóa và không xác thực chữ ký**. Nếu assertion có thông tin nhạy cảm, có thể dùng `EncryptedAssertion`/`EncryptedAttribute` và khóa giải mã của SP theo chính sách.

## 4. Luồng SP-initiated SSO từ đầu đến cuối

```text
Người dùng       Trình duyệt            SP (Spring Security)             IdP
    |                 |                           |                      |
    | Mở /dashboard  |                           |                      |
    |---------------->| GET /dashboard            |                      |
    |                 |-------------------------->|                      |
    |                 |        chưa đăng nhập      |                      |
    |                 |<--------------------------|                      |
    |                 | GET /saml2/authenticate/company-idp               |
    |                 |-------------------------->|                      |
    |                 |        Tạo AuthnRequest + RelayState              |
    |                 |<--------------------------|                      |
    |                 | POST/Redirect request tới IdP                     |
    |                 |-------------------------------------------------->|
    |                 |                       IdP xác thực, có thể MFA    |
    |                 |<--------------------------------------------------|
    |                 | POST SAMLResponse tới ACS                          |
    |                 |-------------------------->|                      |
    |                 |      Kiểm tra chữ ký, issuer, audience, thời gian |
    |                 |      recipient, correlation, tạo Authentication   |
    |                 |<--------------------------|  session/cookie       |
    |                 | GET /dashboard            |                      |
    |                 |-------------------------->|                      |
    |<----------------|  Nội dung đã được bảo vệ  |                      |
```

Chi tiết theo Spring Security:

1. Người dùng truy cập route yêu cầu `.authenticated()`. Nếu chưa có security context phù hợp, ứng dụng khởi động SAML login; có thể hiển thị trang chọn IdP khi đăng ký nhiều `RelyingPartyRegistration`.
2. `Saml2WebSsoAuthenticationRequestFilter` xử lý endpoint như `/saml2/authenticate/{registrationId}`, tạo `<saml2:AuthnRequest>` và gửi tới IdP bằng HTTP-Redirect hoặc POST binding được cấu hình. Nó dùng `RelyingPartyRegistration` để biết SP Entity ID, ACS và IdP SSO URL.
3. IdP xác thực user theo chính sách của IdP. SAML không buộc SP phải biết password hay thuật toán MFA của IdP.
4. IdP tạo `<samlp:Response>` với assertion và chữ ký/đối tượng mã hóa theo metadata/policy, gửi qua browser tới ACS của SP. Trình duyệt không được xem như nguồn xác thực nội dung.
5. `Saml2WebSsoAuthenticationFilter` nhận POST ở `/login/saml2/sso/{registrationId}` hoặc endpoint hỗ trợ tương ứng, tạo `Saml2AuthenticationToken`, rồi ủy quyền `AuthenticationManager`/SAML authentication provider.
6. Provider dùng thông tin IdP đã đăng ký để xác minh chữ ký, giải mã khi cần, kiểm tra điều kiện trên Response/Assertion và chuyển về `Saml2Authentication`. Nếu thất bại, không được tạo phiên authenticated.
7. Sau khi thành công, Spring Security đặt `Authentication` trong `SecurityContext`; cơ chế lưu security context/session của ứng dụng quyết định các request sau thấy login ra sao.

**Correlation:** với SP-initiated SSO, AuthnRequest có `ID` và HTTP state liên quan (`RelayState` nếu dùng). Provider/request repository cần đối chiếu `InResponseTo` đúng yêu cầu đang chờ. Mặc định Spring Security sử dụng `HttpSessionSaml2AuthenticationRequestRepository` cho AuthnRequest; vì vậy cấu hình cookie/session, reverse proxy, load balancing có thể ảnh hưởng đăng nhập.

## 5. IdP-initiated SSO khác SP-initiated như thế nào?

Ở **IdP-initiated SSO**, người dùng mở một ứng dụng từ portal IdP, IdP gửi SAML Response tới ACS của SP **mà không có AuthnRequest mới từ SP**. Luồng này thường được gọi là *unsolicited SAML response*.

Điểm đánh đổi: không có AuthnRequest hiện hành để đối chiếu `InResponseTo` chặt như SP-initiated. Nếu SP và IdP hỗ trợ IdP-initiated, cần chính sách kiểm soát riêng: issuer, chữ ký, audience, recipient, thời gian, replay, định danh tenant, cookie/session, RelayState/target URL. Không chấp nhận một response không tương quan chỉ vì browser chuyển nó tới ACS.

Khi không có yêu cầu nghiệp vụ IdP-initiated, nên ưu tiên **SP-initiated** để giữ correlation tốt hơn. Việc hỗ trợ unsolicited response phụ thuộc cấu hình/phiên bản và chính sách của ứng dụng; phải kiểm thử trực tiếp thay vì suy đoán từ việc endpoint ACS có thể nhận POST.

## 6. Metadata: nền tảng thỏa thuận tin cậy giữa SP và IdP

**Metadata** là tài liệu XML mô tả cách các entity giao tiếp với nhau, thường chứa:

| Thuộc tính | Trong metadata IdP | Trong metadata SP |
| --- | --- | --- |
| `entityID` | Định danh IdP/Issuer được kỳ vọng | Định danh SP/Audience mà IdP cấp assertion cho |
| SSO service | URL IdP nhận AuthnRequest, HTTP binding | Thông thường không phải một IdP SSO URL |
| ACS | Không phải nơi IdP tiêu thụ assertion của SP | URL/các binding nhận Response |
| Verification certificates | Public key dùng để SP xác minh chữ ký IdP | Public key dùng để IdP xác minh request SP đã ký |
| Encryption certificates | Theo chính sách IdP | Public key SP cung cấp để IdP mã hóa assertion cho SP |
| Single Logout services | Có thể có, nếu hai phía hỗ trợ | Có thể có, khác với login |

`RelyingPartyRegistration` giữ cấu hình của **cặp** SP–IdP. `RelyingPartyRegistrationRepository` quản lý một hoặc nhiều cặp đó.

- `registrationId` là khóa do ứng dụng đặt, ví dụ `company-idp`.
- `RelyingPartyRegistrations.fromMetadataLocation(...)` có thể khởi tạo registration từ metadata của IdP (URL hoặc resource phù hợp).
- `InMemoryRelyingPartyRegistrationRepository` thích hợp khi cấu hình ít và cố định; với nhiều IdP, tenant hoặc metadata cần tự làm mới, cần chiến lược repository, caching và rotation rõ ràng.
- `.saml2Metadata(withDefaults())` xuất **SP metadata** qua `/saml2/metadata` hoặc `/saml2/metadata/{registrationId}` trong Spring Security có hỗ trợ DSL tương ứng.
- Phải đăng ký SP Entity ID, ACS URL, certificate public và các yêu cầu ký với IdP trước khi một SSO thật hoạt động.

**Đặc biệt:** tin một XML metadata chưa được chứng thực là rủi ro. Truy xuất từ nguồn quản trị tin cậy qua HTTPS, kiểm chứng chữ ký metadata nếu policy yêu cầu, pin hoặc quay vòng verification certificates có kiểm soát. Tự động refresh metadata phải có quan sát thay đổi khóa/issuer và đường khôi phục khi IdP không khả dụng.

## 7. Ví dụ Spring Boot 3.x + Spring Security 6.x làm Service Provider

Đây là ví dụ **Servlet** sử dụng Java 17+ và Gradle. Các lớp Java dưới đây có cấu trúc hoàn chỉnh, nhưng ứng dụng chỉ đăng nhập thật khi đã nhận **metadata IdP hợp lệ** và đăng ký SP ở IdP.

### 7.1. Dependencies

Trong `build.gradle` của một project Spring Boot 3.x đã có plugin/BOM quản lý dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-saml2-service-provider` mang phần hỗ trợ SAML Relying Party và thư viện OpenSAML tương thích. Không thêm OAuth2 Client hoặc Resource Server chỉ để có SAML Login. Đừng tự buộc các module `spring-security-*` lệch major version so với BOM của Spring Boot.

### 7.2. Chỉ ra metadata IdP đã được xác thực

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

app:
  saml:
    idp-metadata-location: ${IDP_METADATA_LOCATION:classpath:metadata/company-idp.xml}
```

File `classpath:metadata/company-idp.xml` phải là metadata **thật** do IdP tin cậy cung cấp; ví dụ không kèm file này. Có thể thay `IDP_METADATA_LOCATION` bằng HTTPS URL metadata do tổ chức quản lý. Ở production, SP phải được truy cập qua **HTTPS** tại public URL chính thức, không dùng mặc định `localhost:8080` làm ACS thực tế.

### 7.3. Security configuration và RelyingPartyRegistrationRepository

File `src/main/java/example/saml/SamlSecurityConfig.java`:

```java
package example.saml;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("${app.saml.idp-metadata-location}") String idpMetadata) {

        RelyingPartyRegistration registration =
            RelyingPartyRegistrations.fromMetadataLocation(idpMetadata)
                .registrationId("company-idp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().authenticated()
            )
            .saml2Login(withDefaults())
            .saml2Metadata(withDefaults());

        return http.build();
    }
}
```

Code chú ý:

- Khi đã tạo `RelyingPartyRegistrationRepository` bean, không đồng thời định nghĩa một repository khác từ YAML rồi nhầm cấu hình nào đang được dùng.
- `RelyingPartyRegistrations.fromMetadataLocation` đọc thông số IdP (issuer, SSO URL, verification key, điều kiện ký...) từ metadata; `registrationId` ở đây là `company-idp`.
- `saml2Login(withDefaults())` kích hoạt luồng đăng nhập SAML, đăng ký request/response filters tương ứng; `saml2Metadata(withDefaults())` công bố SP metadata để đăng ký với IdP.
- `/me` yêu cầu `Authentication` thành công; không hề cấp `ROLE_ADMIN` hay role nghiệp vụ theo email.
- Một ứng dụng có nhiều security filter chains phải chắc chắn request đăng nhập và ACS đi vào chain có `.saml2Login(...)`; matcher sai có thể khiến ACS 404/403 hoặc không bao giờ tạo Authentication.
- Trong thực tế, metadata có thể yêu cầu **AuthnRequest phải được ký**. Khi đó SP cần signing private key + certificate được quản lý an toàn; ví dụ chưa cung cấp khóa này và không bảo đảm tương thích mọi IdP.

### 7.4. Bootstrap và controller đọc danh tính

`src/main/java/example/saml/SamlDemoApplication.java`:

```java
package example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlDemoApplication.class, args);
    }
}
```

`src/main/java/example/saml/CurrentUserController.java`:

```java
package example.saml;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> currentUser(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of("nameId", principal.getName());
    }
}
```

Với Spring Security **6.x**, `Saml2AuthenticatedPrincipal` là API quen thuộc để truy cập `NameID` và attributes. Trong các bản **7.1+**, một số API principal này đã được đánh dấu deprecated theo hướng phát triển `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`. Khi nâng cấp, xem migration guide và Javadoc đúng phiên bản; không tự copy cấu hình 7.1 vào 6.x mà kỳ vọng cùng kiểu đối tượng.

Giá trị trả về là `NameID` do IdP cấp, có thể là opaque identifier thay vì email hay username hiển thị. Không mặc định `NameID` chính là khóa chính bền vững hoặc duy nhất xuyên mọi IdP. Cấu trúc DTO chỉ trả về đúng phần dữ liệu cần thiết; không nên trả toàn bộ assertion cho frontend.

Chạy ứng dụng:

```bash
./gradlew bootRun
```

Khi metadata hợp lệ và IdP đã chấp nhận SP, mở:

```text
http://localhost:8080/saml2/authenticate/company-idp
```

Đây chỉ là địa chỉ **local để bắt đầu luồng**. IdP thực tế phải cho phép ACS và SP Entity ID khớp với base URL mà ứng dụng công bố. Dự án demo muốn SSO end-to-end thường cần public HTTPS hostname hoặc môi trường test IdP tương ứng.

## 8. Cấu hình IdP thủ công bằng Spring Boot properties

Khi không lấy metadata IdP tự động, Spring Boot 3.x cho phép mô tả các thông số **Asserting Party** trong `application.yml`. Ví dụ rút gọn thay cho bean repository ở mục 7.3 (nếu dùng YAML này, **bỏ bean `relyingPartyRegistrations` ở trên** để không cấu hình trùng):

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company-idp:
            assertingparty:
              entity-id: "https://login.example.org/idp"
              sso-url: "https://login.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/idp-signing.crt"
```

`idp-signing.crt` phải là **chứng thư công khai thật** dùng để xác minh chữ ký của IdP, được quản lý/đổi khóa theo quy trình tin cậy. Các URL và Entity ID trên là placeholder, cần thay bằng giá trị do IdP cung cấp; chính xác tên property và cách nhập metadata có thể khác nhau theo phiên bản Spring Boot. Trước khi chọn hướng nào, đối chiếu `Saml2RelyingPartyProperties` của bản Boot ứng dụng đang chạy.

Những thành phần cấu hình liên quan:

| Cấu hình | Ý nghĩa |
| --- | --- |
| SP `entityId` | Audience/định danh SP được IdP dùng khi phát assertion |
| SP ACS URL | Nơi IdP gửi Response |
| IdP `entity-id` | Issuer IdP mong đợi |
| IdP SSO URL/binding | Endpoint/binding nhận AuthnRequest |
| IdP verification certificate(s) | Xác minh chữ ký Response/Assertion |
| SP signing credential | Ký AuthnRequest khi IdP yêu cầu |
| SP decryption credential | Giải mã EncryptedAssertion/EncryptedAttribute khi dùng mã hóa |

**Signing và verification là hai phía khác nhau:** SP dùng private key của chính mình để ký yêu cầu; SP dùng **public certificate của IdP** để kiểm tra phản hồi. **Decryption** lại cần private key của SP và không thể thực hiện chỉ bằng public certificate. Cất private key ở secret manager/keystore an toàn, không commit vào Git.

## 9. Chữ ký, điều kiện assertion và các kiểm tra bảo mật

Sau khi nhận `SAMLResponse`, application phải coi mọi byte đến từ browser là **dữ liệu chưa đáng tin**. SAML authentication provider/OpenSAML cần thực hiện các kiểm tra chuẩn; ứng dụng không tự Base64 decode một response rồi lấy `NameID` để cấp quyền.

Các điểm tối thiểu:

1. **Chữ ký và trust:** chữ ký của Response hoặc các assertion theo profile/policy phải hợp lệ và được kiểm với **key IdP đã đăng ký**, không phải certificate bất kỳ do request mang đến. Nếu cấu hình yêu cầu signed assertions, đừng hạ yêu cầu chỉ vì integration khó.
2. **Issuer:** Issuer trong thông điệp/assertion phải phù hợp IdP của `RelyingPartyRegistration`, không do một tham số URL tùy ý quyết định.
3. **AudienceRestriction:** Audience phải chứa Entity ID của SP nhận assertion. Không dùng assertion phát cho ứng dụng A đăng nhập ứng dụng B.
4. **Destination/Recipient:** response phải nhắm đúng ACS và SubjectConfirmationData đúng nơi nhận; các giá trị này liên quan scheme/host/port public.
5. **Time conditions:** `NotBefore`, `NotOnOrAfter` và SubjectConfirmationData phải hợp lệ theo thời điểm hiện tại. Đồng bộ NTP và giới hạn clock skew; không mở rộng vô hạn để chữa lỗi thời gian.
6. **InResponseTo:** với SP-initiated, phải liên hệ response với AuthnRequest đang chờ; session/RelayState và request ID phải được giữ/correlation theo thiết kế.
7. **SubjectConfirmation:** bearer confirmation, thời hạn, recipient và các điều kiện khác phải phù hợp Web Browser SSO Profile.
8. **Replay:** ngăn response/assertion đã dùng bị chấp nhận lại khi policy/provider yêu cầu, theo dõi ID trong thời gian phù hợp; đây là tầng bảo vệ bổ sung ngoài signature và time window.
9. **XML processing:** tránh XML signature wrapping, XXE, parser cấu hình yếu và việc tự lấy nhầm một assertion không được ký. Dùng provider đã kiểm thử, cập nhật thư viện.
10. **Trạng thái tài khoản và quyền:** assertion hợp lệ chỉ xác minh điều IdP đã khẳng định; SP còn phải quyết định user/tenant nào được phép đăng nhập, giữ session và authorities ra sao.

Trình tự kiểm tra chi tiết có khác biệt theo phiên bản OpenSAML/Spring Security, nhưng không được bỏ bớt các yêu cầu bảo mật tương ứng. Ở phiên bản hiện đại, Spring Security sử dụng OpenSAML để xác thực, giải mã và tạo principal.

**Không nhầm TLS với XML Signature:** HTTPS bảo vệ từng kết nối mạng. Chữ ký SAML bảo vệ nội dung message qua việc trình duyệt trung chuyển; hai cơ chế bổ trợ nhau.

## 10. Lấy NameID, attributes và gán quyền trong ứng dụng

Sau SSO thành công, Spring Security thiết lập một `Saml2Authentication`. Trên API thường dùng của 6.x, `getPrincipal()` là một `Saml2AuthenticatedPrincipal`; có thể đọc:

```java
String subject = samlPrincipal.getName();
Object email = samlPrincipal.getFirstAttribute("email");
var attributes = samlPrincipal.getAttributes();
String registrationId = samlPrincipal.getRelyingPartyRegistrationId();
```

Đoạn trên **minh họa** bên trong một method đã có biến `Saml2AuthenticatedPrincipal samlPrincipal`, không phải chương trình độc lập. Tên attributes thực tế (ví dụ URI claim của ADFS) tùy cấu hình IdP và có thể là nhiều giá trị, không mặc định `email` luôn tồn tại. Tên email hoặc `displayName` không đủ làm khóa account ổn định nếu IdP cho đổi.

Chọn một khóa danh tính bền vững theo chính sách, chẳng hạn `(IdP entityId, immutable subject ID)`; tránh liên kết hai danh tính từ IdP khác nhau chỉ vì email trùng. Với nhiều tenant, phải cố định đúng relying-party registration và issuer trước khi ánh xạ account.

### Xác thực và phân quyền khác nhau

- `Saml2Authentication` thành công: có một SAML assertion hợp lệ theo chính sách của SP.
- `Authentication.getAuthorities()`: tập quyền trong Spring Security; cần policy mapping riêng để có `ROLE_FINANCE`, `ROLE_ADMIN`, v.v.
- `hasRole("FINANCE")`: kỳ vọng authority `ROLE_FINANCE` theo tiền tố role mặc định; `hasAuthority("ROLE_FINANCE")` kiểm tra chuỗi chính xác.

Ví dụ controller chỉ cho xem nội dung khi đã có role do **ứng dụng cấp**:

```java
package example.saml;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class FinanceController {

    @PreAuthorize("hasAuthority('ROLE_FINANCE')")
    @GetMapping("/finance/report")
    public String report() {
        return "Allowed";
    }
}
```

Để `@PreAuthorize` chạy, cấu hình **`@EnableMethodSecurity`** trong ứng dụng và gọi qua Spring-managed bean/proxy. **Không** gán `ROLE_FINANCE` mặc định chỉ vì IdP có gửi trường `department=Finance`. Cần một policy mapping rõ ràng, allowlist/group đã xác minh và kiểm thử quyền tối thiểu; phương thức map group/authorities phải phù hợp provider và phiên bản Spring Security đang dùng.

## 11. Endpoint mặc định và lỗi dễ nhầm

| Endpoint / thành phần | Vai trò | Ghi chú |
| --- | --- | --- |
| `/saml2/authenticate/{registrationId}` | Khởi tạo SP-initiated login, gửi AuthnRequest tới IdP | `registrationId` chọn cấu hình |
| `/login/saml2/sso/{registrationId}` | Assertion Consumer Service nhận SAML Response | Thường POST chứa `SAMLResponse`; trong các bản mới cũng hỗ trợ dạng không có ID |
| `/saml2/metadata/{registrationId}` | Xuất SP metadata để IdP import | Cần bật `saml2Metadata(...)` trên phiên bản hỗ trợ |
| `Saml2WebSsoAuthenticationRequestFilter` | Tạo/sử dụng AuthnRequest | Khác với filter nhận SAML Response |
| `Saml2WebSsoAuthenticationFilter` | Xác thực SAML Response thông qua AuthenticationManager | Không tự là Identity Provider |
| `RelyingPartyRegistrationRepository` | Lưu cặp thông tin SP–IdP | Có thể có nhiều registration |
| `Saml2Authentication` | Đối tượng đã xác thực trong Spring Security | Không phải IdP-issued bearer token để phát tán tùy ý |

Cả default ACS, SP Entity ID và URL metadata có thể được tùy chỉnh; khi thay một endpoint phải cập nhật metadata và đăng ký tương ứng ở IdP. `registrationId` chỉ là khóa định tuyến, **không phải bằng chứng người dùng thuộc IdP đó**. Chứng thực issuer và chữ ký vẫn bắt buộc.

### Reverse proxy / public base URL

Triển khai thực tế thường:

```text
Browser HTTPS -> Load Balancer/Ingress -> Spring Boot (internal HTTP)
Public baseUrl: https://app.example.org
Internal URL:   http://service:8080
```

Nếu SP dựng ACS bằng URL nội bộ `http://service:8080`, IdP có thể từ chối request vì Destination/Recipient khác URL public hoặc sai scheme. Cần cấu hình reverse proxy tin cậy và forwarded headers của Spring Boot/container phù hợp, hoặc đặt SP Entity ID/ACS tường minh theo metadata đăng ký. Không cho client tự áp đặt `X-Forwarded-Host`/`X-Forwarded-Proto` qua đường bypass; proxy phải lọc header đầu vào.

Khi scale nhiều instance, đảm bảo state lưu `AuthnRequest`, HTTP session và correlation không bị mất. Dùng sticky session hoặc distributed session storage phù hợp; không tắt xác minh correlation chỉ để chữa lỗi “InResponseTo mismatch”.

### CSRF ở ACS

SAML HTTP-POST binding thường làm browser POST từ **origin của IdP** vào ACS. Điều này khác form POST của người dùng đang ở SP. Spring Security có cấu hình SAML2 xử lý luồng này; nếu thay đổi CSRF matcher, phải kiểm tra riêng ACS để không chặn POST hợp lệ và không vô hiệu hóa CSRF cho toàn bộ ứng dụng một cách không cần thiết. Việc ACS được nhận POST **không làm giảm yêu cầu signature, recipient, replay hoặc correlation**.

## 12. Kiểm thử theo các lớp

### 12.1. Kiểm tra cấu hình SP/IdP trước khi chạy

1. Xác nhận `spring-security-saml2-service-provider` và các dependency Spring Security cùng phiên bản tương thích.
2. Metadata IdP có đúng `Entity ID`, SSO URL, signing certificate và binding; SP được đăng ký ở IdP.
3. SP metadata công bố đúng **public** Entity ID, ACS và verification/signing information.
4. IdP có thể truy cập ACS HTTPS, cert TLS hợp lệ, clock hai phía đồng bộ.
5. Xác định policy signed AuthnRequest, ký SAML Response/Assertion, encryption, account identifiers, SLO nếu có.
6. Nếu có nhiều IdP, kiểm tra route `registrationId` và giới hạn tenant/issuer.

### 12.2. MockMvc chỉ kiểm tra authorization; không giả mạo xác minh chữ ký

Có thể dựng `Saml2Authentication` giả **trong test** và đưa vào MockMvc để kiểm tra controller/authorization, tách biệt khỏi phần xác minh XML SAML.

File `src/test/java/example/saml/CurrentUserTest.java`:

```java
package example.saml;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CurrentUserTest {

    @Autowired
    MockMvc mvc;

    @Test
    void principalCanReachProtectedEndpoint() throws Exception {
        var principal = new DefaultSaml2AuthenticatedPrincipal(
            "user-7392", Map.of()
        );
        var auth = new Saml2Authentication(
            principal,
            "<test-only/>",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

        mvc.perform(get("/me").with(authentication(auth)))
            .andExpect(status().isOk())
            .andExpect(content().json("{\"nameId\":\"user-7392\"}"));
    }
}
```

`"<test-only/>"` ở trên **không phải SAML Response hợp lệ**; test này chỉ bỏ qua phần giao thức để kiểm tra `SecurityContext`, controller và authorization khi đã có principal. Muốn test chạy, Spring context vẫn phải dựng được `RelyingPartyRegistrationRepository`; dùng test metadata fixture hợp lệ ở `classpath` hoặc test configuration thích hợp. Với Spring Security 7.1+, kiểm tra lại loại principal đã deprecated và API thay thế.

### 12.3. Integration test với IdP test

Mỗi đường đi cần có bằng chứng độc lập:

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| SP-initiated AuthnRequest hợp lệ; IdP đăng nhập và trả signed Response | SP xác minh, tạo session, `/me` trả danh tính |
| Chữ ký assertion/response bị thay đổi | Từ chối SAML authentication |
| Issuer IdP khác với registration được tin cậy | Từ chối |
| Audience không trùng SP Entity ID | Từ chối |
| `Recipient`/`Destination` không khớp ACS public | Từ chối |
| Assertion đã hết hạn hoặc chưa có hiệu lực | Từ chối |
| `InResponseTo` không khớp request đang chờ | Từ chối theo luồng SP-initiated |
| Response/assertion được gửi lại (replay) | Không cấp phiên mới theo chính sách chống replay |
| Assertion hợp lệ nhưng account/role không cho phép | Bị chặn bởi policy ứng dụng (thường 403 ở tài nguyên bị cấm) |
| Cookies/session mất khi redirect qua IdP hoặc đổi instance | SSO không hoàn tất; tìm nguyên nhân state/correlation |
| IdP signing key rotate | Cập nhật metadata/verification key an toàn, không nới xác minh |

Chỉ `curl` tới `/login/saml2/sso/company-idp` với một XML tự tạo **không phải integration test thành công** nếu XML không được IdP tin cậy ký. Nên dùng một IdP test (Keycloak/ADFS môi trường test hay sản phẩm SAML sandbox) cùng public SP URL có thể truy cập, bật audit hạn chế dữ liệu nhạy cảm.

## 13. Cấu hình theo phiên bản

| Giai đoạn | Điểm cần nhớ |
| --- | --- |
| **Spring Security 5.2+** | SAML 2.0 Login SP được đưa dần vào Spring Security; API/khả năng hỗ trợ có thay đổi qua các bản 5.x |
| **Spring Security 5.7–5.8** | `WebSecurityConfigurerAdapter` deprecated từ 5.7; chuyển sang `SecurityFilterChain` |
| **Spring Security 6.x / Boot 3.x** | Java 17+, `jakarta.servlet.*`; dùng `saml2Login(Customizer)` và `RelyingPartyRegistrationRepository`; OpenSAML 4 hoặc 5 tùy setup/version |
| **Spring Security 7.x / Boot 4.x** | Tiếp tục cấu hình lambda/Customizer; chú ý thay đổi provider OpenSAML, cách truy cập assertion/principal và MFA/authority marker ở các bản 7.x |

Đừng nhầm các Javadoc khác phiên bản: một số bài cũ dùng `OpenSaml4AuthenticationProvider`, còn tài liệu mới trình bày `OpenSaml5AuthenticationProvider` và `Saml2ResponseAssertionAccessor`. Tên class được dùng để custom converter/provider phải lấy từ **đúng dependency tree**. Ví dụ cơ bản trong bài chọn API cấu hình SP thông dụng, tránh phụ thuộc trực tiếp vào một vendor provider.

Ở Spring Security 7.1+, `Saml2AuthenticatedPrincipal`/`DefaultSaml2AuthenticatedPrincipal` có hướng deprecation; dùng hướng dẫn migration và API thay thế thích hợp trong version đó. Không thay đổi `Authentication` hoặc tắt kiểm tra assertion chỉ để giữ code mapper cũ hoạt động.

## 14. Những lỗi phổ biến và cách truy tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| 404 ở `/saml2/authenticate/company-idp` | Sai registrationId, thiếu registration, chain không bật `saml2Login` | Xác nhận bean repository, exact ID và chain matcher |
| IdP báo SP unknown / invalid audience | SP Entity ID không đúng metadata đã đăng ký | So sánh Entity ID **chính xác** (scheme, path, case) |
| IdP từ chối AuthnRequest | IdP yêu cầu chữ ký nhưng SP chưa có signing key, sai binding, Destination/issuer | Kiểm tra metadata/policy ký và request binding |
| POST tới ACS trả 403/404 | ACS path, CSRF matcher, security chain, proxy hoặc quyền route sai | Xác nhận endpoint/ACS đã đăng ký, filter chain, forwarded headers |
| `InResponseTo` không khớp | Mất session/request repository, cookie SameSite, load balancing hoặc response unsolicited | Kiểm tra session/cookie/RelayState/correlation; không bỏ validation |
| Assertion/Response signature validation failed | IdP cert sai/hết hạn, metadata cũ, chữ ký bị sửa, mismatch XML | Kiểm tra verification credential và rotation |
| Assertion expired / not yet valid | Clock skew, NTP lệch hoặc thời gian assertion không đúng | Đồng bộ đồng hồ, dùng tolerance nhỏ có kiểm soát |
| Destination/Recipient mismatch | SP dùng HTTP/internal host, IdP gửi HTTPS/public URL | Sửa public baseUrl, ACS và cấu hình proxy tin cậy |
| Đăng nhập thành công nhưng `/finance/report` trả 403 | Chưa gán `ROLE_FINANCE` theo policy | Kiểm tra authorities và mapping account/tenant |
| Login thành công nhưng request kế tiếp chưa authenticated | Session cookie mất, reverse proxy/session storage sai | Kiểm tra Set-Cookie, SameSite/Secure, host, session replication |
| Claim email không có hoặc sai kiểu | IdP không cấp attribute, tên URI/claim khác, nhiều giá trị | Xem metadata/claim mapping ở IdP; xử lý null và type |
| Chỉ test bằng MockMvc mà SSO thật thất bại | MockMvc giả lập authenticated principal, không thử XML signature | Kiểm thử end-to-end với IdP tin cậy |

Khi debug SAML, chỉ ghi thông tin cần thiết như thời điểm, registrationId, nguyên nhân validation, request correlation ID. Tránh ghi nguyên `SAMLResponse`, XML assertion có email/nhóm, private key, session cookie hoặc chứng thư bí mật vào production logs.

## 15. Một số ranh giới thiết kế quan trọng

- **SAML Authentication ≠ OAuth2 Access Token:** SAML Login tạo phiên đăng nhập web tại SP; không tự tạo JWT cho REST API và không phải một OAuth 2.0 authorization server.
- **IdP cung cấp thông tin xác thực, SP quyết định quyền ứng dụng:** một claim `groups=Admins` cần chính sách mapping/tenant rõ ràng trước khi thành `ROLE_ADMIN`.
- **Signed XML ≠ Encrypted XML:** chữ ký kiểm tra nguồn gốc/tính toàn vẹn; mã hóa che giấu nội dung. Không cần tắt TLS hoặc signature nếu có encryption.
- **Logout tại SP ≠ Single Logout tại IdP:** gọi `/logout` thường chỉ xử lý phiên local; SAML Single Logout cần hai bên hỗ trợ message, key và endpoint riêng (`saml2Logout` khi phù hợp).
- **NameID ≠ email:** NameID có thể transient/persistent, opaque, thay đổi theo IdP. Tổ chức cần contract về identity linking và lifecycle account.
- **Nhiều tenant/IdP cần boundary riêng:** mỗi `registrationId` đại diện cặp relying-party/aserting-party; phải kiểm tra issuer và audience thực tế, tránh trộn tenant.
- **Không dựa trên browser hay URL để xác minh IdP:** nguồn tin cậy là registration, verification key và validation của provider.

Quy tắc vận hành: để Spring Security/OpenSAML thực hiện xác minh SAML và quản lý `Authentication`; đăng ký SP/IdP metadata chính xác, giữ public HTTPS URL/ACS ổn định, quản lý certificate rotation và session correlation; ánh xạ quyền sau khi đã xác minh assertion và account.

## 16. Tài liệu tham khảo chính thức

- Spring Security – SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.3 – Security/SAML Relying Party: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security 6.5 – `Saml2AuthenticatedPrincipal` API: https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
