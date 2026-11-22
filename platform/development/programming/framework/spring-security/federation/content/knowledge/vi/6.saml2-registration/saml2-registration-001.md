# RelyingPartyRegistration và mô hình cấu hình một quan hệ SP–IdP

Trong Spring Security SAML 2.0, **`RelyingPartyRegistration` là cấu hình mô tả một quan hệ tin cậy cụ thể giữa Service Provider (SP) và Identity Provider (IdP)**. Ở đây, ứng dụng Spring đóng vai **SP**, cũng được gọi là *Relying Party (RP)*; hệ thống đăng nhập doanh nghiệp đóng vai **IdP**, cũng được gọi là *Asserting Party (AP)*.

Một quan hệ SP–IdP đúng phải trả lời được: SP là ai, IdP là ai, gửi yêu cầu đăng nhập ở đâu, nhận SAML Response ở đâu, dùng chứng thư nào để xác minh chữ ký, khi nào phải ký hoặc giải mã thông điệp, và principal nào được phép sử dụng tài nguyên sau đăng nhập. Chỉ khai báo URL IdP hoặc chỉ thêm dependency SAML chưa tạo được một quan hệ tin cậy an toàn.

**Mục tiêu học tập:**

- Hiểu `RelyingPartyRegistration` như một mô hình cấu hình gồm **hai phía**, không phải một “tài khoản người dùng”.
- Phân biệt `registrationId` của Spring với `entityId` của SP và IdP.
- Tạo được cấu hình SP–IdP bằng Spring Boot properties hoặc JavaConfig; hiểu nơi lưu trong `RelyingPartyRegistrationRepository`.
- Theo dõi đường đi `AuthnRequest` → IdP → `SAMLResponse` → Assertion Consumer Service (ACS) → `Authentication`.
- Kiểm tra metadata, chứng thư, chữ ký, audience/recipient, tenant, reverse proxy và các lỗi thường gặp.
- Biết cách mở rộng từ một quan hệ sang nhiều IdP mà không cho phép lẫn ranh giới tin cậy.

## 1. Khái niệm và phạm vi một registration

| Thuật ngữ | Tên trong Spring Security | Vai trò |
| --- | --- | --- |
| SP / RP | Relying Party | Ứng dụng của ta tiếp nhận kết quả SAML do IdP phát hành |
| IdP / AP | Asserting Party | Xác thực người dùng và phát hành SAML Response/Assertion |
| SP entity ID | `RelyingPartyRegistration.entityId` | Định danh SAML ổn định do SP công bố, thường là URI |
| IdP entity ID | `AssertingPartyMetadata.entityId` | Định danh issuer của IdP, dùng kiểm tra nguồn phát hành |
| Registration ID | `registrationId` | Khóa nội bộ Spring dùng tìm bản cấu hình quan hệ |
| ACS | `assertionConsumerServiceLocation` | URL của SP nhận SAML Response từ trình duyệt |
| IdP SSO URL | `singleSignOnServiceLocation` | Endpoint IdP tiếp nhận `AuthnRequest` |
| IdP verification credential | `verificationX509Credentials` | Public certificate/khóa tin cậy để SP kiểm chữ ký của IdP |
| SP signing credential | `signingX509Credentials` | Khóa riêng và certificate SP dùng ký `AuthnRequest` nếu cần |
| SP decryption credential | `decryptionX509Credentials` | Khóa riêng SP dùng giải mã assertion được IdP mã hóa |
| Repository | `RelyingPartyRegistrationRepository` | Tìm cấu hình đã phê duyệt theo `registrationId` |

**Một `RelyingPartyRegistration` mô tả cặp cấu hình SP + IdP.** Nó không lưu danh sách nhân viên, mật khẩu, vai trò nội bộ hoặc phiên đăng nhập. Các việc đó thuộc hệ thống xác thực, kho tài khoản và tầng authorization khác.

Ví dụ một SP tên Portal A tin IdP của công ty B:

- `registrationId = partner-b` do nhóm phát triển Portal A đặt.
- SP Entity ID: `https://portal.example.com/saml2/service-provider-metadata/partner-b`.
- SP ACS: `https://portal.example.com/login/saml2/sso/partner-b`.
- IdP Entity ID: `https://login.partner-b.example/saml2/idp`.
- IdP SSO URL: `https://login.partner-b.example/saml2/sso`.
- IdP certificate: chứng thư X.509 được A kiểm tra và tin cậy cho đúng B.

`registrationId` chỉ là khóa tra cứu **nội bộ**. Nó có thể là `partner-b` hoặc `corp`, nhưng **không thay cho SAML Entity ID** của bất kỳ phía nào. SP và IdP còn phải thống nhất rõ các URI, bindings, chứng thư và chính sách ký.

## 2. Vì sao không chỉ khai báo một IdP URL?

SAML Web Browser SSO trao đổi những tuyên bố được ký, có thời hạn và giới hạn nơi nhận. Thử lấy một SAML Response có chữ ký hợp lệ của IdP B gửi tới SP C rồi nộp cho Portal A: nếu Portal A chỉ xác minh chữ ký mà bỏ qua audience hoặc recipient thì có nguy cơ chấp nhận thông điệp được phát hành **cho hệ thống khác**.

Vì vậy cấu hình phải gắn cặp quan hệ:

~~~text
SPRING REGISTRATION: partner-b
    SP / Relying Party
       entityId = https://portal.example.com/saml2/service-provider-metadata/partner-b
       ACS      = https://portal.example.com/login/saml2/sso/partner-b
       signing/decryption credentials = SP-owned, nếu cần
    IdP / Asserting Party
       entityId = https://login.partner-b.example/saml2/idp
       SSO URL  = https://login.partner-b.example/saml2/sso
       verification certificate = IdP-owned, đã kiểm tra
    POLICY
       chấp nhận đúng IdP, đúng SP, đúng yêu cầu và đúng thời điểm
       ánh xạ NameID/attributes theo chính sách Portal A
       kiểm tra quyền ứng dụng / tenant riêng
~~~

Những URI chứa `.example` ở đây là dữ liệu học tập, không tồn tại để thực hiện đăng nhập thật.

## 3. Một luồng SP-initiated SSO từ đầu đến cuối

Giả sử người dùng vào một trang cần đăng nhập trên Portal A:

~~~mermaid
sequenceDiagram
    participant U as Người dùng / Browser
    participant SP as Portal A - Spring Security SP
    participant REP as RelyingPartyRegistrationRepository
    participant IDP as IdP B
    U->>SP: GET /private
    SP->>REP: Tìm registration partner-b
    REP-->>SP: SP + IdP metadata và credentials
    SP-->>U: Redirect tới IdP với AuthnRequest
    U->>IDP: Gửi SAMLRequest (HTTP-Redirect binding)
    IDP->>IDP: Xác thực người dùng, kiểm SP
    IDP-->>U: Form trả SAMLResponse (HTTP-POST binding)
    U->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Tra registration, kiểm Response/Assertion
    SP->>SP: Tạo Authentication, đánh giá quyền
    SP-->>U: Session / trang được phép
~~~

Diễn giải kỹ:

1. `Saml2WebSsoAuthenticationRequestFilter` tạo `AuthnRequest` dựa vào `RelyingPartyRegistration` đã chọn.
2. SP chỉ gửi yêu cầu tới SSO endpoint của IdP được cấu hình và thỏa các yêu cầu ký request (nếu IdP đòi hỏi).
3. IdP xác thực tài khoản, tạo Response/Assertion có issuer, subject, audience, recipient, điều kiện thời gian và chữ ký.
4. Trình duyệt chuyển Response tới ACS của SP. Trình duyệt **không phải nguồn tin cậy**: payload SAML phải được server kiểm tra.
5. `Saml2WebSsoAuthenticationFilter` lấy message, giải quyết registration và gọi `AuthenticationManager`/provider xử lý SAML; với Spring Security hiện đại, provider dựa trên OpenSAML.
6. Nếu xác minh thành công, Spring tạo `Saml2Authentication`/principal và đặt vào `SecurityContext` theo chính sách phiên.
7. Ứng dụng vẫn cần kiểm quyền truy cập URL, đối tượng dữ liệu và tenant. Chữ ký hợp lệ của IdP B không cấp quyền quản trị Portal A.

Đường đi mặc định trong nhiều cấu hình Spring Security Servlet:

| Mục đích | Đường dẫn mặc định thường dùng |
| --- | --- |
| Bắt đầu đăng nhập với một cấu hình | `/saml2/authenticate/{registrationId}` |
| ACS để nhận và xử lý Response | `/login/saml2/sso/{registrationId}` |
| ACS không gắn ID, khi resolver hỗ trợ | `/login/saml2/sso` |
| SP metadata | `/saml2/metadata`, `/saml2/metadata/{registrationId}`, hoặc `/saml2/service-provider-metadata/{registrationId}` |

Ví dụ `/saml2/authenticate/partner-b` là endpoint **bắt đầu xác thực**, không phải nơi người dùng gửi mật khẩu và cũng không phải endpoint API bảo vệ. ACS `/login/saml2/sso/partner-b` là nơi xử lý Response; nó phải khớp URI đã đăng ký với IdP. Không tự đổi một bên mà quên cập nhật phía còn lại.

## 4. Mô hình dữ liệu của `RelyingPartyRegistration`

Một registration có thể nhìn theo hai nhánh:

~~~mermaid
flowchart TB
    R["RelyingPartyRegistration<br/>registrationId = partner-b"]
    SP["SP / Relying Party"]
    AP["IdP / Asserting Party"]
    R --> SP
    R --> AP
    SP --> E["entityId / SP issuer"]
    SP --> C["ACS location + binding"]
    SP --> X["signing / decryption X.509 credentials"]
    AP --> I["IdP entityId / Issuer"]
    AP --> S["Single Sign-On Service URL + binding"]
    AP --> V["verification X.509 credentials"]
    AP --> W["AuthnRequest signing expectations"]
~~~

Các thành phần có quan hệ như sau:

**Phía SP:**

- `entityId` đại diện SP trong SAML. IdP thường đưa giá trị này vào `AudienceRestriction` của assertion dành cho SP.
- `assertionConsumerServiceLocation` là địa chỉ mà browser gửi Response đến. IdP kiểm theo registration đã cấu hình.
- `signingX509Credentials` là tài sản của SP; khóa riêng cần bí mật.
- `decryptionX509Credentials` dùng nếu nhận encrypted assertion và SP phải giải mã.
- Thông tin binding/địa chỉ logout, khi sử dụng SAML Single Logout, cần được thiết lập nhất quán; login và logout là hai luồng riêng.

**Phía IdP:**

- `entityId` là issuer mong đợi trong SAML.
- `singleSignOnServiceLocation` là nơi SP gửi `AuthnRequest`.
- `verificationX509Credentials` là public certificate mà SP tin để xác minh chữ ký.
- `wantAuthnRequestsSigned` (mô hình builder) hoặc property tương đương biểu thị IdP có yêu cầu SP ký `AuthnRequest` hay không.

Không nhầm:

- Chứng thư **verification** của IdP với **private key ký** của SP.
- SP Entity ID với IdP Entity ID.
- SP metadata với IdP metadata.
- User NameID với registrationId.
- Có một registration với có một user: một registration có thể phục vụ nhiều user IdP.

## 5. Tạo registration tối thiểu bằng Spring Boot properties

Dự án Servlet dùng Spring Boot và Spring Security SAML2 cần dependency `spring-security-saml2-service-provider`. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

Phiên bản nên do Spring Boot BOM quản lý hoặc được chọn đồng bộ với Spring Security/Framework đang chạy. Module phụ thuộc OpenSAML; tuỳ phiên bản và kho artifact, cần bổ sung kho Maven chính thức của Shibboleth như tài liệu Spring Security hướng dẫn. Không mặc định rằng mọi bản build trên mọi môi trường đều chỉ cần Maven Central.

Khi IdP cung cấp đủ thông số đã xác minh, cấu hình `application.yml` tối thiểu có thể là:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "https://portal.example.com/saml2/service-provider-metadata/partner-b"
            acs:
              location: "https://portal.example.com/login/saml2/sso/partner-b"
            assertingparty:
              entity-id: "https://login.partner-b.example/saml2/idp"
              singlesignon:
                url: "https://login.partner-b.example/saml2/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:saml/partner-b-signing.crt"
~~~

Các property như `entity-id`, `acs.location`, `assertingparty.entity-id`, `assertingparty.singlesignon.url` và `assertingparty.verification.credentials` mô tả **cặp SP–IdP**. Sau khi build, kiểm phiên bản Spring Boot đang dùng có cùng property model, nhất là khi đang nâng major; không áp dụng cấu hình từ blog Spring Security 5 cũ cho dự án mới mà không đối chiếu.

Điều kiện sử dụng ví dụ:

- File `saml/partner-b-signing.crt` chứa **public certificate thật** của IdP B đã xác minh; file không xuất hiện tự động.
- `sign-request: false` chỉ phù hợp khi IdP B **thực sự không yêu cầu ký AuthnRequest**. Trong môi trường yêu cầu ký, SP phải có signing credential và khai báo yêu cầu ký đúng cách.
- Các URI public phải được IdP B chấp nhận/đăng ký đúng, kể cả scheme HTTPS, hostname, path và trailing slash.
- Không bỏ thông tin IdP certificate chỉ để hết lỗi signature; một SP không có trust anchor đáng tin thì không xác thực SAML an toàn.
- SP metadata khi công bố sẽ chứa các thông số SP đã cấu hình; cần cung cấp nó cho quản trị IdP để nhập vào hệ thống.

Boot có thể tạo `RelyingPartyRegistrationRepository` từ properties. Spring Security sẽ sử dụng repository đó để xác định cặp SP–IdP cho mỗi yêu cầu.

### Cấu hình `SecurityFilterChain`

Một class Spring Security Servlet tối thiểu, **cần ứng dụng Boot và registration ở trên**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Lưu file `SamlSecurityConfiguration.java` trong module Spring Boot có dependency SAML. Mã thể hiện:

- `saml2Login` bật luồng Web Browser SSO cho các registration đã được cấu hình.
- `saml2Metadata` cho phép công bố SP metadata; các endpoint như `/saml2/metadata/partner-b` cần được IdP truy cập theo chính sách mạng/ứng dụng.
- `/health` là public trong ví dụ; mọi URL còn lại cần đăng nhập; `/admin/**` còn yêu cầu `ROLE_ADMIN`.
- Cấu hình **chưa tự map attribute IdP thành `ROLE_ADMIN`** và không quyết định quyền trên object/tenant; ứng dụng phải thực hiện riêng.

**Đặc biệt:** SAML Browser SSO thường POST từ trang IdP bên ngoài sang ACS. Spring Security có logic tích hợp CSRF cho luồng chuẩn; khi tự đổi ACS hoặc CSRF policy, cần kiểm luồng thực tế. Không tắt CSRF toàn bộ ứng dụng chỉ để “sửa SAML”.

## 6. Tạo repository bằng JavaConfig khi cấu hình không nằm trong YAML

Đôi khi SP phải tải metadata từ IdP thay vì nhập từng endpoint và chứng thư. Spring Security cung cấp `RelyingPartyRegistrations.fromMetadataLocation(...)`. Ví dụ khung JavaConfig đầy đủ cho một registration:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class SamlRegistrationConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("${app.saml.partner-b.metadata-url}") String trustedMetadataUrl) {

        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation(trustedMetadataUrl)
                .registrationId("partner-b")
                .entityId("https://portal.example.com/saml2/service-provider-metadata/partner-b")
                .assertionConsumerServiceLocation(
                        "https://portal.example.com/login/saml2/sso/partner-b")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

Properties minh họa:

~~~yaml
app:
  saml:
    partner-b:
      metadata-url: "https://login.partner-b.example/saml2/metadata"
~~~

**Đây là JavaConfig cho project Spring**, không chạy độc lập bằng `javac` nếu không có Spring dependencies; URL mẫu cũng không hoạt động. Khi `fromMetadataLocation` chạy, thư viện đọc metadata và dựng một phần cấu hình IdP. Đầu vào **phải là vị trí metadata đáng tin** do quản trị viên cấu hình; không lấy URL từ request bất kỳ rồi tải trực tiếp vì rủi ro SSRF và nhận sai trust anchor.

Trong production, metadata được cập nhật, verify signature và rotate certificate theo chính sách; tải một lần tại startup có thể làm key/certificate cũ tồn tại mãi. Nên cân nhắc cơ chế repository/metadata resolver hỗ trợ refresh theo thời hạn, có xác minh chữ ký metadata nếu tổ chức yêu cầu, cùng quy trình triển khai rollback. Đừng chọn cách tải metadata bất kỳ rồi tự chấp nhận mọi certificate hiện thấy.

Nếu đã khai báo `RelyingPartyRegistrationRepository` bean tùy chỉnh, cần xác định bean đó sẽ **thay hoặc được Spring sử dụng thay** auto-config repository; tránh vừa dùng YAML để quản lý một bản, vừa dùng JavaConfig quản lý một bản khác mà không biết cái nào chạy thực tế.

## 7. Khi cần dựng thủ công hai phía SP–IdP

Một số IdP không cung cấp metadata đầy đủ hoặc metadata không phản ánh hết contract. Khi đó có thể dùng builder `RelyingPartyRegistration.withRegistrationId(...)`.

Đoạn sau **chỉ là fragment mô tả mô hình**: biến `idpVerificationCertificate` là một `X509Certificate` đã được tải và xác minh từ cấu hình an toàn, không phải class standalone.

~~~java
RelyingPartyRegistration registration =
        RelyingPartyRegistration.withRegistrationId("partner-b")
            .entityId("https://portal.example.com/saml2/service-provider-metadata/partner-b")
            .assertionConsumerServiceLocation(
                    "https://portal.example.com/login/saml2/sso/partner-b")
            .assertingPartyMetadata(party -> party
                .entityId("https://login.partner-b.example/saml2/idp")
                .singleSignOnServiceLocation(
                    "https://login.partner-b.example/saml2/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(credentials ->
                    credentials.add(Saml2X509Credential.verification(
                        idpVerificationCertificate))))
            .build();
~~~

Phải import đúng `RelyingPartyRegistration` và `Saml2X509Credential` của phiên bản Spring Security đang chạy. Nếu IdP yêu cầu ký request, thêm **credential ký của SP** với certificate và private key bảo quản đúng quy định, đồng thời không đặt `wantAuthnRequestsSigned(false)` để né lỗi.

Nhận diện vị trí thông số:

| Cần khai báo | Thuộc phía nào trong builder? | Lý do |
| --- | --- | --- |
| `registrationId` | Gốc registration | Spring tìm cấu hình chính xác cho luồng |
| `entityId(...)` trên builder gốc | SP | Bên IdP nhận diện SP; assertion giới hạn audience theo SP |
| `assertionConsumerServiceLocation(...)` | SP | Browser gửi SAML Response tới ACS |
| `signingX509Credentials(...)` | SP | SP ký AuthnRequest/LogoutRequest theo contract |
| `decryptionX509Credentials(...)` | SP | SP giải mã EncryptedAssertion nếu IdP mã hóa |
| `assertingPartyMetadata(p -> p.entityId(...))` | IdP | Chỉ nhận issuer mà SP đã chọn tin |
| `singleSignOnServiceLocation(...)` trong party | IdP | Địa chỉ gửi AuthnRequest |
| `verificationX509Credentials(...)` trong party | IdP | Kiểm chữ ký SAML do IdP tạo |
| `wantAuthnRequestsSigned(...)` | Chính sách IdP | SP biết khi nào cần ký request |

Với dữ liệu certificate được nhập từ một file PEM, cần phân biệt **public certificate IdP** dùng để verify với private key của SP dùng sign/decrypt; không chép một khóa riêng vào Java source hoặc repository.

## 8. Hiểu `registrationId`, Entity ID và ánh xạ URL

Đây là ba loại định danh khác nhau:

**A. `registrationId`** là khóa do ứng dụng đặt, ví dụ `partner-b`. Nó có thể xuất hiện trong đường dẫn `/saml2/authenticate/partner-b` và `/login/saml2/sso/partner-b`, giúp Spring phân biệt nhiều registration. Nó không mang ý nghĩa danh tính người dùng.

**B. SP Entity ID** là định danh SAML được công bố cho IdP. Giá trị có thể trông giống URL nhưng **không nhất thiết là endpoint có thể GET được**. IdP thường cấu hình nó như “Audience URI” hoặc “SP Entity ID”. Không tùy tiện sửa vì đổi Entity ID có thể làm mọi assertion cũ và registration phía IdP không khớp.

**C. IdP Entity ID** nhận diện tổ chức/sản phẩm phát hành assertion. Nó thường được tìm trong metadata IdP, và phải khớp với issuer của các thông điệp được chấp nhận. URL IdP SSO là một endpoint gửi request, không nhất thiết trùng Entity ID.

Spring cho phép placeholders như `{baseUrl}`, `{registrationId}`, `{baseScheme}`, `{baseHost}` và `{basePort}` trong những URI được hỗ trợ. Ví dụ:

~~~text
SP entityId:
{baseUrl}/saml2/service-provider-metadata/{registrationId}

SP ACS:
{baseUrl}/login/saml2/sso/{registrationId}

Nếu baseUrl = https://portal.example.com, registrationId = partner-b:

SP entityId:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP ACS:
https://portal.example.com/login/saml2/sso/partner-b
~~~

Khi chạy sau reverse proxy, sai scheme/host ở `baseUrl` có thể khiến IdP cho rằng ACS/Entity ID không đúng, gây vòng lặp login hoặc lỗi Audience/Recipient/Destination. Hãy xác định public URL cố định, chỉ tin `Forwarded`/`X-Forwarded-*` từ **proxy do ứng dụng quản trị** và kiểm cấu hình forwarding. Không chấp nhận Host header tùy ý làm SP entityId nếu môi trường không kiểm soát host.

**Đặc tính quan trọng:** đường dẫn metadata thường được truy cập như tài liệu XML, nhưng **giá trị Entity ID** trong metadata chỉ là một định danh có tính nhất quán. Hai thứ có thể giống nhau về cú pháp mà không đồng nhất về chức năng.

## 9. Metadata hai phía: đọc cái nào, công bố cái nào?

### Metadata IdP

Thông thường metadata IdP chứa `EntityDescriptor`, `IDPSSODescriptor`, các endpoint `SingleSignOnService` với bindings, và khóa ký/khóa mã hóa. SP dùng dữ liệu này để hình thành phía `AssertingPartyMetadata`.

- Metadata có thể được nhập từ một URL tin cậy, file đã được quản lý hoặc kho cấu hình.
- Cần đối chiếu `entityID`, chứng thư và binding với nhà vận hành IdP.
- Metadata XML có thể được ký; nếu chính sách yêu cầu, phải xác minh chữ ký bằng trust anchor phù hợp.
- HTTPS bảo vệ truyền tải, nhưng không tự chứng minh một endpoint bất kỳ là IdP đúng của tổ chức.
- Certificate có thời hạn và có thể xoay: cần quy trình cập nhật có thời gian overlap giữa key cũ/mới nếu IdP hỗ trợ.

### Metadata SP

SP metadata thường chứa `SPSSODescriptor`, SP Entity ID, ACS location, bindings và khóa công khai SP cung cấp cho IdP. Phía IdP dùng metadata SP để biết gửi Response ở đâu và xác minh AuthnRequest có chữ ký khi được yêu cầu.

Với `saml2Metadata(Customizer.withDefaults())`, Spring Security có thể công bố metadata tại `/saml2/metadata` và biến thể gắn `registrationId` theo cơ chế của phiên bản hiện hành. Nếu dùng nhiều registration, metadata nên được cung cấp đúng cặp SP–IdP mà quản trị IdP tương ứng đã phê duyệt.

Một trình tự onboarding:

1. Đăng ký IdP B với quản trị viên A, nhận metadata IdP qua kênh tin cậy.
2. SP A cấu hình `RelyingPartyRegistration` cho B, xác định entityId, ACS, chứng thư và chính sách sign/decrypt.
3. SP A xuất metadata SP cho quản trị B.
4. Quản trị B khai báo SP A (đúng SP Entity ID, ACS, chứng thư ký), bảo đảm B chỉ phát assertion cho SP A.
5. Hai bên kiểm thử tích hợp với user test và kiểm signature, audience, time, recipient, logout nếu có.
6. Khi phiên bản/khóa thay đổi, mỗi bên cập nhật metadata theo quy trình rotate và kiểm regression.

Việc SP A phát metadata không tự tạo quyền truy cập ở B. Phải có **cấu hình đối ứng tại IdP**.

## 10. `RelyingPartyRegistrationRepository`: cấu hình được tra cứu thế nào?

`RelyingPartyRegistrationRepository` đại diện kho registration. Một implementation đơn giản là `InMemoryRelyingPartyRegistrationRepository` khi danh sách IdP ít và tương đối tĩnh. Repository được tra theo `registrationId`; Spring có các resolver để xác định registration tương ứng với request SAML.

### Một IdP

~~~text
RegistrationRepository:
  partner-b -> RelyingPartyRegistration(
      SP = Portal A,
      IdP = B
  )
~~~

Luồng chuẩn khởi đầu từ `/saml2/authenticate/partner-b`, nên registration cần duy nhất. Không cho request lựa chọn tùy ý một cấu hình khác chỉ dựa vào payload chưa xác minh.

### Nhiều IdP

~~~text
RegistrationRepository:
  corp-a    -> SP Portal A + IdP tập đoàn A
  partner-b -> SP Portal A + IdP đối tác B
  partner-c -> SP Portal A + IdP đối tác C
~~~

Mỗi entry có `registrationId` riêng, IdP Entity ID riêng, verification certificate riêng, và có thể có SP Entity ID/ACS riêng. Hai đối tác cùng dùng tên người dùng `alice` không có nghĩa họ là cùng một tài khoản nội bộ.

**Lưu ý đa tenant:** nhiều registration hỗ trợ federation đa IdP, nhưng **không tự tạo bảo vệ tenant**. Tầng ứng dụng vẫn kiểm: issuer B được phép vào tenant nào, user có membership còn hiệu lực không, role của B được ánh xạ ra sao, và tài nguyên có thuộc đúng tenant không.

### Tìm registration khi xử lý Response

Trong luồng SP-initiated, Spring có thể dùng `AuthnRequest` đã lưu và `registrationId` trong URL. Ở một số trường hợp, framework có thể dựa trên issuer Response để tìm registration phù hợp. Dù tìm bằng cách nào, **tìm ra một registration chưa có nghĩa Response hợp lệ**: vẫn phải kiểm chữ ký, issuer, audience, recipient, thời gian, request correlation và các điều kiện SAML.

Khi muốn thay cơ chế lựa chọn registration, dùng điểm mở rộng chính thức như `RelyingPartyRegistrationResolver` hoặc authentication converter/resolver tương ứng cho từng endpoint. Tránh tự ánh xạ response theo email hoặc một header tenant do client gửi.

## 11. Đăng ký nhiều quan hệ không đồng nghĩa liên kết nhiều danh tính

SAML identity federation có hai tầng riêng:

1. **Trust configuration:** `RelyingPartyRegistration` nói “SP A tin assertion từ IdP B trong giới hạn này”.
2. **Identity/account mapping:** từ assertion đã xác minh, ứng dụng quyết định user nội bộ nào được sử dụng, thuộc tenant nào và có quyền gì.

Định danh người dùng có thể lấy từ `NameID` hoặc thuộc tính có ngữ nghĩa ổn định theo hợp đồng IdP, nhưng:

- `NameID` dạng **persistent** có thể phù hợp liên kết tài khoản nếu IdP bảo đảm ngữ nghĩa và phạm vi duy nhất.
- `NameID` dạng **transient** không phù hợp làm khóa lưu dài hạn.
- Email, tên hiển thị và username có thể đổi hoặc tái sử dụng, không nên dùng để tự động gộp tài khoản liên tổ chức.
- Cùng subject/NameID từ B và C không chứng minh là cùng người.

Khóa domain gợi ý:

~~~text
ExternalIdentityKey(
   tenantId,
   assertingPartyEntityId,
   persistentNameId,
   nameIdQualifierIfRelevant
) -> localUserId
~~~

Đây là mô hình khái niệm; thuộc tính NameID và qualifiers phải được thiết kế theo hợp đồng SAML thực tế. Một số IdP phát thuộc tính người dùng phù hợp làm immutable identifier; chỉ dùng khi IdP cam kết tính bền vững. Không tự cấp quyền `ADMIN` từ một attribute `groups=admins` do IdP bên ngoài cung cấp mà chưa có mapping được tổ chức A duyệt.

**Ví dụ:** IdP B xác thực người dùng `employee-123` và SP A xác minh Response thành công. Hệ thống vẫn cần kiểm đối tác B đã được mời, hợp đồng còn hiệu lực, user có membership tenant B, và quyền xem đơn hàng của B. Đó là việc sau `RelyingPartyRegistration`.

## 12. Chữ ký, giải mã và các cặp khóa thường bị nhầm

| Hoạt động | Ai dùng private key? | Ai cần public certificate? | Gắn ở cấu hình nào? |
| --- | --- | --- | --- |
| IdP ký SAML Response/Assertion | IdP | SP để verify | `AssertingPartyMetadata.verificationX509Credentials` |
| SP ký AuthnRequest | SP | IdP để verify | `RelyingPartyRegistration.signingX509Credentials` |
| IdP mã hóa Assertion cho SP | IdP dùng public certificate SP để encrypt | SP dùng private key tương ứng để decrypt | `RelyingPartyRegistration.decryptionX509Credentials` |
| SP ký LogoutRequest khi yêu cầu | SP | IdP để verify | Signing credentials và SLO config tương ứng |

Không đưa private key của SP vào SAML metadata công khai. Metadata chỉ phân phối phần certificate/public key cần thiết. Chứng thư public IdP cũng cần lấy từ nguồn được thỏa thuận tin cậy, không chấp nhận “certificate bất kỳ có trong Response” như root of trust.

**Key rotation:** khi IdP đổi certificate, SP có thể cần chấp nhận đồng thời public key cũ và mới trong giai đoạn chuyển tiếp theo chính sách. Nếu SP đổi signing key, IdP phải cập nhật thông tin để xác minh AuthnRequest. Với SP decryption key, phải quản trị encrypted assertions đang chuyển tiếp và khóa vẫn còn cần trong thời gian hợp lệ.

**Không nhầm signing với encryption:** cần verify chữ ký và giải mã chỉ khi loại message/protocol yêu cầu, nhưng không được “vì không giải mã được nên tắt luôn verify”.

## 13. Những điều phải xác minh ở một SAML Response

Khi kiểm một Response gửi tới ACS, ít nhất cần xem:

1. **Issuer:** có khớp `AssertingPartyMetadata.entityId` đã được phê duyệt?
2. **Signature:** phần XML bắt buộc ký đã được kiểm bằng certificate tin cậy đúng IdP, chống signature wrapping?
3. **AudienceRestriction:** assertion dành cho đúng SP entityId?
4. **Recipient/Destination:** message được gửi tới ACS/endpoint thực sự mà SP đã cấu hình?
5. **Thời gian:** `NotBefore`, `NotOnOrAfter`, `IssueInstant` có hợp lệ theo clock skew được quy định?
6. **Request correlation:** với SP-initiated, `InResponseTo` có ràng buộc với `AuthnRequest` mà SP đã tạo và lưu không?
7. **Replay:** Response/Assertion ID đã bị dùng trước đó chưa, hoặc đã quá thời gian cho phép?
8. **Subject confirmation:** holder/recipient/validity phù hợp profile SAML đang dùng?
9. **Conditions/AuthnStatement:** có đáp ứng điều kiện của IdP và mức xác thực mà nghiệp vụ yêu cầu?
10. **Application authorization:** user có thể truy cập endpoint/tenant/object nào?

Spring Security SAML2 dựa vào provider và thư viện OpenSAML để xác minh chuẩn, nhưng vẫn phải cấu hình chính xác và test các tình huống âm tính. Nếu tùy chỉnh authentication provider hoặc response converter, không được vô tình bỏ mất các bước validation mặc định.

**IdP-initiated login:** luồng unsolicited Response có thể không có `AuthnRequest` tương ứng; nó không có cùng bảo đảm correlation như SP-initiated. Chỉ bật khi policy chấp nhận, có ràng buộc issuer, recipient, audience, replay và xử lý phiên/RelayState an toàn. Không xem thiếu `InResponseTo` là tự động hợp lệ chỉ vì IdP đã ký.

## 14. Đường dẫn ACS, reverse proxy và header forwarding

Một lỗi kinh điển là Spring ứng dụng chạy nội bộ `http://localhost:8080`, nhưng người dùng truy cập qua `https://portal.example.com`. Nếu SP sinh ACS từ base URL nội bộ, metadata có thể công bố URL không đúng; IdP gửi Response sai endpoint, dẫn tới lỗi `Destination`/`Recipient`/`Audience` hoặc redirect loop.

Cách xử lý:

- Ưu tiên thiết lập SP `entityId` và `acs.location` theo URL public cố định, đã đăng ký với IdP.
- Nếu dùng placeholder `{baseUrl}`, phải cấu hình trusted forwarded headers đúng cơ chế Boot, proxy và security policy; chỉ nhận từ ingress/proxy tin cậy.
- Cấu hình TLS, SNI, host, port, context path và URL redirects thống nhất.
- Không cho phép client tự gửi header `Forwarded` hoặc `X-Forwarded-Host` có thể thao túng SP Entity ID/ACS.
- Khi thay tên miền, phải điều phối thay đổi cả SP metadata và IdP registration theo chuỗi triển khai.

Đừng sửa bằng cách tắt kiểm `Recipient`/`Destination`: điều này che lỗi cấu hình, làm giảm bảo vệ nơi nhận thông điệp.

## 15. SAML bindings và giao thức không nằm hết trong một URL

**HTTP-Redirect binding** thường dùng để chuyển `AuthnRequest` từ SP đến IdP qua browser. **HTTP-POST binding** thường dùng để gửi `SAMLResponse` trở lại ACS. Tùy IdP, `AuthnRequest` có thể đi qua POST và logout có bindings khác.

Điều cần kiểm:

- IdP metadata liệt kê `SingleSignOnService` với binding nào, URL nào?
- SP chọn binding mà IdP thật sự hỗ trợ?
- IdP biết SP ACS URL/binding mong đợi?
- Request signature có bắt buộc và thuật toán ký được chấp nhận?
- Assertion có ký, mã hóa và ràng buộc chính sách đúng?
- Logout request/response có cấu hình và test riêng nếu sử dụng?

`RelyingPartyRegistration` giúp gom các thông số của một cặp SP–IdP, nhưng cấu hình sai binding vẫn khiến giao tiếp không hoạt động. Một Response đúng ký gửi qua endpoint/binding không đúng có thể bị từ chối hợp lệ.

## 16. Java 17 chạy độc lập: kiểm tra hợp đồng SP–IdP trước khi kết nối thật

Mã dưới đây là ví dụ Java thuần để tư duy **một bản cấu hình quan hệ** và đánh giá vài điều kiện logic. Mã **không xác minh chữ ký SAML/XML, không cấp phiên, không đọc metadata IdP, không dùng Spring Security**. Trong sản phẩm thật, chỉ chạy chính sách này **sau** khi Spring Security/OpenSAML đã kiểm chứng Response và chọn registration đáng tin cậy.

Tạo file `SamlRegistrationDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class SamlRegistrationDemo {
    record Registration(
            String id,
            String spEntityId,
            String acsUrl,
            String idpEntityId) {}

    record VerifiedAssertion(
            String issuer,
            String audience,
            String recipient,
            String subject) {}

    static boolean matches(
            Registration registration,
            VerifiedAssertion assertion) {
        return assertion.issuer().equals(registration.idpEntityId())
                && assertion.audience().equals(registration.spEntityId())
                && assertion.recipient().equals(registration.acsUrl());
    }

    public static void main(String[] args) {
        Registration partnerB = new Registration(
                "partner-b",
                "https://portal.example.com/saml2/service-provider-metadata/partner-b",
                "https://portal.example.com/login/saml2/sso/partner-b",
                "https://login.partner-b.example/saml2/idp");

        Map<String, Registration> repository = Map.of(
                partnerB.id(), partnerB);
        Registration selected = repository.get("partner-b");

        VerifiedAssertion valid = new VerifiedAssertion(
                partnerB.idpEntityId(),
                partnerB.spEntityId(),
                partnerB.acsUrl(),
                "employee-123");

        VerifiedAssertion wrongAudience = new VerifiedAssertion(
                partnerB.idpEntityId(),
                "https://another.example.com/sp",
                partnerB.acsUrl(),
                "employee-123");

        VerifiedAssertion wrongIssuer = new VerifiedAssertion(
                "https://login.partner-c.example/saml2/idp",
                partnerB.spEntityId(),
                partnerB.acsUrl(),
                "employee-123");

        System.out.println("Registration: " + selected.id());
        System.out.println("Valid: " + matches(selected, valid));
        System.out.println("Wrong audience: "
                + matches(selected, wrongAudience));
        System.out.println("Wrong issuer: "
                + matches(selected, wrongIssuer));
        System.out.println("Unknown registration: "
                + repository.containsKey("unknown"));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac SamlRegistrationDemo.java
java SamlRegistrationDemo
~~~

Stdout chính xác:

~~~text
Registration: partner-b
Valid: true
Wrong audience: false
Wrong issuer: false
Unknown registration: false
~~~

Giải thích:

- `registrationId = partner-b` tìm đúng cặp đã cấu hình trong repository.
- `Valid: true` chỉ khẳng định ba giá trị *đã được giả định là xác minh* phù hợp contract, không nói chữ ký/điều kiện thời gian đã hợp lệ.
- `Wrong audience: false` minh họa assertion dành cho SP khác phải bị từ chối.
- `Wrong issuer: false` minh họa IdP C không được đóng vai IdP B.
- `Unknown registration: false` minh họa repository không chấp nhận ID không được đăng ký.

Không dùng record `VerifiedAssertion` làm đối tượng tin cậy nếu nó được tạo trực tiếp từ JSON/XML người dùng gửi. Cấu trúc này chỉ minh họa tư duy; kiểm tra mật mã và SAML profile phải do thư viện đã được kiểm thử thực hiện.

## 17. Kiểm thử tích hợp registration thực tế

Tạo một IdP test có metadata và certificate rõ ràng, một SP chạy HTTPS tại URL thực (hoặc tunnel/lab đã kiểm soát). Cần ít nhất các phép thử sau:

| Test | Điều kiện đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| Repository lookup | `registrationId=partner-b` | Trả đúng SP Entity ID và IdP Entity ID B |
| Registration lạ | `registrationId=unknown` | Không bắt đầu SSO dưới trust context bất kỳ |
| Metadata SP | GET metadata registration đã cho phép | Có SP entityID, ACS, certificate chính xác |
| Metadata IdP | Đọc metadata đã kiểm tra | Issuer và SSO URL đúng tổ chức, verification cert đúng |
| SP-initiated SSO | Browser vào `/saml2/authenticate/partner-b` | AuthnRequest đến đúng IdP B; ACS nhận Response |
| Audience khác | Assertion ký đúng của B nhưng dành cho SP C | Bị từ chối |
| Issuer khác | Assertion từ IdP C tại registration B | Bị từ chối |
| ACS recipient sai | Response gửi cho ACS ngoài allowlist | Bị từ chối |
| Ticket/Assertion quá hạn | `NotOnOrAfter` đã qua | Bị từ chối |
| Request correlation sai | `InResponseTo` không khớp yêu cầu SP đã lưu | Bị từ chối trong SP-initiated flow |
| Replay Response | Nộp lại cùng assertion theo policy anti-replay | Không tạo phiên mới trái phép |
| Certificate rotation | IdP thay signing cert theo quy trình | Chỉ certificate được trust mới được chấp nhận |
| IdP-initiated nếu hỗ trợ | Không có request gốc | Áp chính sách unsolicited Response riêng |
| User không có quyền | SAML đúng nhưng role/membership không đủ | Đăng nhập có thể thành công; thao tác nhạy cảm bị 403 |
| Multi-tenant | B và C có NameID/email giống nhau | Không liên kết/gộp quyền chéo tenant |
| Proxy HTTPS | Public URL và forwarded headers hợp lệ | SP Entity ID/ACS khớp metadata và IdP |

Có thể bắt đầu kiểm metadata bằng:

~~~bash
curl -i https://portal.example.com/saml2/metadata/partner-b
~~~

Lệnh này yêu cầu ứng dụng đang chạy và endpoint có thể truy cập. Response sẽ phụ thuộc cấu hình; **không có stdout XML cố định** để sao chép. Hãy kiểm trực tiếp `EntityDescriptor entityID`, `AssertionConsumerService Location`, `KeyDescriptor` và các binding. Không coi việc metadata có HTTP 200 là chứng cứ đăng nhập đã đúng; cần thực hiện luồng với IdP thật/test.

Các bài test Spring MockMvc có thể kiểm endpoint/authorization một phần, nhưng không chứng minh signature validation, IdP certificate và SAML browser round-trip khi không có fixture phù hợp. Bộ kiểm thử tin cậy cần kết hợp cấu hình unit test, SAML integration test, end-to-end và negative cases.

## 18. Lỗi thường gặp: nhìn từ góc độ một registration

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `registration not found` khi mở login URL | Sai `registrationId` hoặc repository chưa chứa entry | Kiểm URL, bean, cấu hình Spring Boot |
| IdP báo “unknown SP” | SP entityId không đúng cấu hình tại IdP | Đối chiếu SP metadata và cấu hình IdP |
| Response bị báo “invalid issuer” | IdP entityId không khớp nguồn được trust | Kiểm IdP metadata, issuer và registration |
| “Invalid audience” | Assertion dành cho SP entityId khác | Đồng bộ audience/SP entityId; không tắt validation |
| “Invalid recipient/destination” | ACS URL khác public URL, proxy sai scheme/host | Sửa ACS và forwarded header trust |
| “Signature invalid” | Certificate sai/đã rotate, signed element không như mong đợi | Kiểm IdP signing cert và policy chữ ký |
| “Unable to decrypt” | IdP encrypt assertion, SP thiếu/wrong decryption key | Đồng bộ public SP cert và private key tương ứng |
| `InResponseTo` không tìm thấy | Phiên lưu request bị mất, SameSite/cookie/proxy hoặc sai luồng | Kiểm request repository và thiết kế IdP-initiated |
| Login loop | ACS bị chặn, session không được tạo, path/security rule sai | Trace POST ACS, filter chain, cookie và response |
| Đăng nhập được nhưng không vào trang | Chưa có local user/role/tenant hoặc rule thiếu | Kiểm mapping và authorization ứng dụng |
| Hai tenant bị gộp user | Dùng email/NameID mà quên issuer/tenant | Thiết kế identity key và account linking an toàn |
| IdP đổi metadata đột ngột gây lỗi | Certificate/endpoint thay đổi, cache chưa refresh | Quy trình rotation, metadata repository có refresh, rollback |
| Thử copy ví dụ cũ bị lỗi method | Khác Spring Security/OpenSAML major | Xác nhận tài liệu/Javadoc của đúng version |

Khi cần chẩn đoán, ghi lại version thực tế của Spring Boot, Spring Security, OpenSAML, registrationId, issuer/audience/recipient đã được kiểm tra và lỗi validation. Không log nguyên văn SAML Response, assertion, private key, cookie phiên hay thông tin cá nhân nhạy cảm.

## 19. Lưu ý phiên bản Spring Security và OpenSAML

Spring Security hiện đại hỗ trợ SAML2 trong module `spring-security-saml2-service-provider`. Tên method và các chi tiết builder/provider có thể thay đổi theo major version, đặc biệt giữa các tài liệu Spring Security 5/6/7 và bản OpenSAML đi kèm.

- Ưu tiên `SecurityFilterChain` và `saml2Login`; ví dụ cũ dựa trên `WebSecurityConfigurerAdapter` không áp dụng trực tiếp trong ứng dụng mới.
- Trong tài liệu hiện hành của Spring Security 7, quá trình kiểm SAML Response dùng `OpenSaml5AuthenticationProvider`. Không lấy API provider theo blog OpenSAML 3/4 rồi dùng nguyên vẹn.
- Spring Boot properties là mô hình config mức ứng dụng; Java builder là API Spring Security. Đừng lấy tên YAML property để suy ra tên Java method hoặc ngược lại.
- Xác định đúng servlet stack: SAML2 Web Browser SSO của Spring Security được mô tả trên nhánh **Servlet**. Đừng cho rằng tự có adapter Reactive chỉ vì ứng dụng WebFlux có dependency SAML trên classpath.
- Dùng dependency management của Spring Boot và kiểm `dependencyInsight`/`dependency:tree` để tránh nhiều phiên bản `spring-security-*` hoặc OpenSAML không đồng bộ.

Ví dụ Gradle cho module Java:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Đây là lệnh điều tra phụ thuộc; output phụ thuộc dự án, không thể xác định từ ví dụ học tập. Kết quả build thành công chỉ kiểm một phần: phải chạy SP–IdP handshake thực tế để xác minh issuer, ACS, bindings và chứng thư.

## 20. Một số quyết định thiết kế khi có nhiều đối tác

**Mỗi IdP một registration:** thường dễ phân tách certificates, endpoint, lifecycle và audit. Không dùng `registrationId = default` cho tất cả đối tác rồi cho IdP do client quyết định.

**SP entityId chung hay riêng:** một số tổ chức có thể dùng một SP entityId chung cho cùng ứng dụng; một số dùng entityId theo đối tác/tenant. Lựa chọn cần phù hợp hợp đồng IdP, ACS, metadata, chứng thư và policy; không có một đáp án bắt buộc. Nếu SP Entity ID chung, vẫn phải xác minh issuer IdP và mapping tenant đúng.

**Repository tĩnh hay động:** danh sách nhỏ có thể dùng `InMemoryRelyingPartyRegistrationRepository`. Danh sách lớn hoặc metadata thường xuyên đổi có thể có kho dữ liệu/metadata resolver/cache đáng tin cậy. Dù dynamic, chỉ quản trị viên hoặc quy trình được phê duyệt được thêm IdP; endpoint không nhận metadata URL tùy ý từ request người dùng.

**Đăng ký và thu hồi:** khi hợp đồng B kết thúc, disable registration/membership theo chính sách, thu hồi phiên đang còn hiệu lực và chặn quyền API. Xóa cấu hình IdP không tự bảo đảm mọi session cũ đã hết hiệu lực.

**Audit:** ghi nhận registrationId, issuer sau xác minh, thời gian, user nội bộ, tenant, kết quả kiểm tra và sự kiện rotate. Không lưu assertions thô trong log sản xuất nếu không có yêu cầu và cơ chế bảo vệ dữ liệu rõ ràng.

## 21. Bài tập tổng hợp: kiểm một cấu hình SP–IdP

Portal A định tích hợp IdP B. B đưa cho A các thông số:

~~~text
IdP entityId: https://login.partner-b.example/saml2/idp
IdP SSO URL: https://login.partner-b.example/saml2/sso
IdP signing certificate: partner-b-signing.crt
SP entityId đã đăng ký: https://portal.example.com/saml2/service-provider-metadata/partner-b
SP ACS đã đăng ký: https://portal.example.com/login/saml2/sso/partner-b
Yêu cầu ký AuthnRequest: không
~~~

**Câu hỏi 1:** `registrationId` cần có phải bằng IdP entityId không?

**Đáp án:** Không. Chọn khóa nội bộ `partner-b`, ánh xạ nó tới IdP entityId, SP entityId và ACS trong `RelyingPartyRegistration`. Registration ID không phải định danh giao thức SAML.

**Câu hỏi 2:** Response được ký bởi B nhưng `AudienceRestriction` ghi SP entityId của Portal C. Có được nhận không?

**Đáp án:** Không. Chữ ký IdP B không đủ; assertion phải dành cho SP A với audience phù hợp.

**Câu hỏi 3:** B thay certificate mà A chưa cập nhật. Nên bỏ signature validation để tránh downtime?

**Đáp án:** Không. Thực hiện rotation có kế hoạch, xác minh certificate mới qua trust channel và cập nhật cấu hình/metadata resolver. Nếu cần hỗ trợ key cũ-mới song song, phải theo chính sách của hai bên.

**Câu hỏi 4:** Người của B gửi Response hợp lệ, có attribute `groups=admin`. Có được cấp `ROLE_ADMIN` trong A?

**Đáp án:** Chỉ khi có policy ánh xạ quyền đã được A kiểm soát và user thuộc tenant/ngữ cảnh phù hợp. Không tự suy ra quyền admin ứng dụng từ claim bên ngoài.

**Câu hỏi 5:** Ứng dụng chạy sau TLS proxy, thấy `http://internal:8080/login/saml2/sso/partner-b` trong metadata. Phải làm gì?

**Đáp án:** Đặt ACS/public base URL đúng `https://portal.example.com/...`; kiểm trusted forwarded headers và đồng bộ cấu hình tại IdP. Không tắt kiểm `Recipient` để “cứu” login.

## 22. Checklist triển khai một quan hệ SP–IdP

1. **SP identity:** `registrationId` duy nhất, SP Entity ID ổn định, ACS đúng public URL và binding.
2. **IdP identity:** issuer/entityID chính xác, SSO endpoint và metadata được kiểm tra từ nguồn tin cậy.
3. **Certificate:** public verification cert của IdP, private signing/decryption key của SP (nếu cần), lịch xoay và xử lý hết hạn.
4. **Protocol:** AuthnRequest signing policy, Response/Assertion signing, NameID format, time condition, audience, recipient, correlation và anti-replay.
5. **Spring integration:** SAML dependency, Boot config hoặc Java repository, `saml2Login` và `saml2Metadata` được định tuyến đúng.
6. **Application identity:** mapping user dựa trên issuer + định danh bền vững, không gộp tự động bằng email.
7. **Authorization:** role, tenant, object ownership, offboarding và session revocation được quản trị riêng.
8. **Runtime:** HTTPS, reverse proxy, trusted forwarded headers, time synchronization, lỗi metadata, cache/rotation và logging an toàn.
9. **Tests:** happy path, unknown IdP, wrong audience/recipient, invalid signature, expired/replayed assertion, sai correlation, certificate rotation và quyền tenant.
10. **Operations:** tài liệu hóa owner của registration, quá trình onboarding, khóa trust, thay đổi metadata và kế hoạch rollback.

**Điểm cốt lõi:** `RelyingPartyRegistration` không đơn thuần là “URL IdP”. Nó là hợp đồng kỹ thuật giữa **một SP cụ thể** và **một IdP được chấp thuận**: định danh, nơi gửi/nhận, cách kiểm chữ ký/giải mã và các kỳ vọng giao thức. Spring Security thực hiện việc xác thực SAML dựa trên hợp đồng đó; ứng dụng vẫn sở hữu trách nhiệm ánh xạ user và cấp quyền cho tài nguyên.

### Tài liệu tham khảo chính thức

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html)
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — RelyingPartyRegistration API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html)