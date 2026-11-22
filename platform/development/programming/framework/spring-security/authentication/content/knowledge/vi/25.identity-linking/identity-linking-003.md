# RelyingPartyRegistration, metadata và thông tin tin cậy trong SAML 2.0

Trong **Spring Security SAML 2.0 Login**, ứng dụng đóng vai trò **Service Provider (SP)**, còn hệ thống đăng nhập liên kết là **Identity Provider (IdP)**. Theo thuật ngữ Spring Security, hai phía lần lượt còn được gọi là **Relying Party (RP)** và **Asserting Party (AP)**. Để tin một kết quả SAML, ứng dụng phải biết *mình là SP nào, đang làm việc với IdP nào, gửi/nhận thông điệp ở đâu và phải dùng khóa công khai nào để kiểm tra chữ ký*. Cấu hình đó được Spring Security biểu diễn chủ yếu qua **`RelyingPartyRegistration`**.

**RelyingPartyRegistration không phải phiên đăng nhập và cũng không phải một người dùng.** Nó là cấu hình của **một cặp SP–IdP**. Một hệ thống có thể có nhiều registration khi hỗ trợ nhiều IdP, tenant hoặc môi trường, nhưng mỗi lần xác thực SAML phải được đối chiếu với **đúng** registration mà hệ thống tin cậy.

Bài học đi từ cấu trúc cấu hình, metadata hai phía, khóa và ranh giới tin cậy, đến ví dụ Spring Security Servlet, vận hành key rollover và kiểm thử.

## 1. Bốn khái niệm cần tách riêng

| Khái niệm | Chủ sở hữu / nội dung | Vai trò |
| --- | --- | --- |
| **RelyingPartyRegistration** | Cấu hình Spring Security cho một cặp RP–AP, có `registrationId` | Định nghĩa các giá trị mong đợi khi gửi và nhận SAML |
| **IdP metadata** (AP metadata) | IdP công bố `EntityDescriptor / IDPSSODescriptor` | Cho SP biết issuer/entityID, SSO endpoint, bindings, chứng thư kiểm chữ ký, tùy chọn giao thức |
| **SP metadata** (RP metadata) | SP công bố `EntityDescriptor / SPSSODescriptor` | Cho IdP biết SP entityID, ACS endpoint, chứng thư ký/giải mã nếu dùng |
| **SAML Response/Assertion** | IdP tạo ở **mỗi lần đăng nhập** | Chứa kết quả xác thực, NameID/attributes/conditions và chữ ký để SP xác minh |

Hai loại metadata là **thông tin cấu hình** giúp hai bên biết nhau; SAML Response/Assertion là **dữ liệu một lần đăng nhập**. Không nhầm việc import metadata với việc đã xác thực người dùng.

Sơ đồ trao đổi cấu hình và đăng nhập:

~~~text
GIAI ĐOẠN THIẾT LẬP TIN CẬY
IdP metadata --------------------------> SP RelyingPartyRegistration
SP metadata (entityID, ACS, key, ...) --> IdP cấu hình ứng dụng

GIAI ĐOẠN SSO
Browser --> SP /saml2/authenticate/corp
             |
             v
        AuthnRequest --> IdP SSO endpoint
                           |
                        User login
                           |
               SAML Response/Assertion
                           |
Browser -------- POST ----> SP /login/saml2/sso/corp
                           |
              Resolve registration "corp"
              Validate signature, issuer, destination,
              audience, thời gian và các điều kiện khác
                           |
                    Authentication
                           |
               Mapping account/authorization
~~~

**Trust không tự sinh ra từ XML.** Một tệp metadata XML có thể mô tả khóa và endpoint, nhưng ứng dụng chỉ nên chấp nhận nó sau khi xác nhận **nguồn metadata và quy trình phân phối khóa** đáng tin cậy.

## 2. Một registration đại diện cho những gì?

Các thuộc tính quan trọng của một `RelyingPartyRegistration`:

| Thuộc tính hoặc nhóm | Thuộc về | Ý nghĩa |
| --- | --- | --- |
| `registrationId` | Ứng dụng Spring | Tên nội bộ để chọn cấu hình, ví dụ `corp`; **không** phải SAML entityID |
| `entityId` | SP | Issuer/entityID của SP được IdP nhận biết; có thể là URI, không nhất thiết là URL có thể mở |
| `assertionConsumerServiceLocation` | SP | Địa chỉ ACS nơi browser POST SAML Response về |
| `assertionConsumerServiceBinding` | SP | Binding dùng cho ACS, thông thường HTTP-POST |
| `signingX509Credentials` | SP | Khóa riêng và certificate SP dùng để ký các SAML request khi cần |
| `decryptionX509Credentials` | SP | Khóa riêng/certificate dùng giải mã assertion/nameID/attribute đã mã hóa |
| `assertingPartyMetadata().getEntityId()` | IdP | EntityID/Issuer của IdP mong đợi trong SAML |
| `singleSignOnServiceLocation` | IdP | SSO endpoint nhận AuthnRequest |
| `singleSignOnServiceBinding` | IdP | Cách gửi AuthnRequest, như HTTP-Redirect hoặc HTTP-POST |
| `verificationX509Credentials` | IdP | Các certificate công khai đã được tin cậy để kiểm chữ ký IdP |
| `wantAuthnRequestsSigned` | IdP | Khả năng/yêu cầu IdP muốn request ký, cần phối hợp với khóa ký SP |

Tên method có thể khác theo phiên bản: ở Spring Security **6.4+**, API **`assertingPartyMetadata`** và **`getAssertingPartyMetadata`** được dùng trong tài liệu mới; một số API cũ có tên **`assertingPartyDetails`** / **`getAssertingPartyDetails`** và đã deprecated. Dùng API theo dependency version thực tế, không trộn ví dụ 6.x và 7.x.

**Ba định danh dễ nhầm**:

~~~text
registrationId  = corp
SP entityId     = https://app.example.org/saml2/service-provider-metadata/corp
IdP entityId    = https://login.example.org/saml/idp
~~~

- `corp` chỉ là khóa tra trong repository Spring.
- SP entityID là định danh **ứng dụng** mà IdP chấp nhận làm relying party/audience.
- IdP entityID là định danh **bên phát hành** (Issuer) mà SP dùng đối chiếu.
- URL login/metadata/ACS có thể chứa `corp`, nhưng việc tên giống nhau không làm các thuộc tính này trở thành một.

Một registration chỉ mô tả các giá trị **dự kiến**. Runtime SAML provider còn phải kiểm chữ ký và điều kiện assertion trước khi cấp phiên đăng nhập.

## 3. IdP metadata chứa gì và được SP dùng như thế nào?

SAML metadata là XML tuân theo SAML 2.0 Metadata specification. Với IdP, vùng cần đọc thường là:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://login.example.org/saml/idp">
    <md:IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://login.example.org/saml/sso"/>
    </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Đây là **mảnh XML để nhận diện trường**, cố ý chưa chứa `KeyDescriptor`, nên **không đủ làm cấu hình trust cho production**. Metadata thực tế thường có `KeyDescriptor use="signing"` với certificate hoặc thông tin khóa, có thể có `SingleLogoutService`, `validUntil`, `cacheDuration`, chữ ký trên metadata và nhiều entity trong một `EntitiesDescriptor`.

Khi import, cần kiểm tra các giá trị thực tế:

1. **`entityID` của IdP:** phải khớp issuer của response/assertion theo quy tắc xác minh.
2. **`SingleSignOnService` và binding:** SP sẽ gửi AuthnRequest đến endpoint phù hợp. Sai URL hoặc binding khiến login lỗi trước khi nhận response.
3. **`KeyDescriptor` dùng để ký:** tạo cơ sở kiểm chữ ký SAML Response/Assertion. Key phải lấy từ nguồn được phê duyệt, không nhận vì XML tự khai nó.
4. **Metadata expiry/signature:** khi có `validUntil`, chữ ký metadata hoặc quy trình cập nhật, phải có chiến lược xử lý hạn và xác thực metadata.
5. **Nhiều IdP entity:** phải chọn đúng entity cho registration; đừng vô tình gắn khóa và endpoint của IdP khác.

Từ metadata, Spring Security có thể xây dựng dữ liệu **`AssertingPartyMetadata`** bên trong registration. Nó cũng có thể giữ các thuộc tính OpenSAML mở rộng tùy cách import/phiên bản.

**Quan trọng về hai loại chữ ký:** chữ ký của **metadata XML** chứng minh tài liệu metadata đến từ nguồn đáng tin khi được kiểm bằng khóa tin cậy; chữ ký của **SAML Response/Assertion** chứng minh thông điệp đăng nhập do phía có khóa ký tương ứng tạo và không bị sửa. Hai bước sử dụng khóa/phạm vi và thời điểm khác nhau. Kiểm tra một cái không thay thế kiểm tra cái còn lại.

## 4. SP metadata dùng để làm gì?

IdP cần biết danh tính SP và nơi gửi SAML Response về. SP metadata thường chứa:

- `EntityDescriptor entityID="..."`: chính là SP entityID.
- `SPSSODescriptor`: thông tin khả năng SSO của SP.
- `AssertionConsumerService`: địa chỉ ACS + binding (thường POST).
- `KeyDescriptor use="signing"`: public certificate của SP để IdP kiểm AuthnRequest/LogoutRequest có chữ ký.
- `KeyDescriptor use="encryption"`: public certificate của SP nếu IdP cần mã hóa assertion cho SP.
- Một số profile có single logout endpoints, NameID format và thuộc tính khai báo khác.

Sơ đồ XML giản lược:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://app.example.org/saml2/service-provider-metadata/corp">
    <md:SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://app.example.org/login/saml2/sso/corp"
            index="0"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

Đây cũng chỉ là **mảnh nhận diện cấu trúc**, không phải toàn bộ metadata mà Spring sinh ra. Khi triển khai, dùng endpoint do Spring Security tạo ra và **kiểm tra tài liệu xuất thực tế**.

### SP metadata không phải IdP metadata

- Tải **IdP metadata** để cấu hình phía SP.
- Xuất **SP metadata** để đăng ký SP bên IdP.
- Không lấy SP metadata đưa vào `RelyingPartyRegistrations.fromMetadataLocation(...)` và mong Spring coi nó là IdP.
- Không lấy certificate TLS của website IdP làm certificate kiểm chữ ký SAML trừ khi IdP chính thức công bố đúng khóa đó cho mục đích SAML signing.

SAML metadata là **bản mô tả cấu hình/khóa công khai**, không phải secret store; nhưng thông tin endpoint, entity và certificate vẫn cần quản lý thay đổi, audit, môi trường và tenant cho chính xác.

## 5. Ví dụ cấu hình bằng metadata của IdP

Ví dụ dành cho **Spring Security Servlet** với Spring Boot + Java 17. Bạn cần một IdP thật và metadata đã xác minh; URL và entity trong bài là ví dụ thuộc domain `example.org`, không phải dịch vụ đang hoạt động.

Phụ thuộc Gradle Groovy:

~~~groovy
repositories {
    mavenCentral()
    maven { url "https://build.shibboleth.net/maven/releases" }
}

dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.security:spring-security-saml2-service-provider"
}
~~~

Dùng quản lý phiên bản Spring Boot/BOM của dự án để giữ Spring Security và OpenSAML tương thích. Kho Shibboleth là nguồn dependency có thể cần vì OpenSAML; dùng URL kho theo cấu hình hiện hành của tổ chức, không tự thêm phiên bản không tương thích.

Đặt **IdP metadata đã được kiểm chứng** tại đường dẫn classpath `saml/corp-idp-metadata.xml`. Java cấu hình:

~~~java
package demo.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
                .registrationId("corp")
                .entityId("https://app.example.org/saml2/service-provider-metadata/corp")
                .assertionConsumerServiceLocation(
                        "https://app.example.org/login/saml2/sso/corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

**Đây là class cấu hình dùng trong ứng dụng Spring Boot Servlet**, không thể chạy độc lập chỉ với `javac`. Cần main Spring Boot, tài nguyên IdP metadata, kết nối mạng và đăng ký đối ứng trên IdP. Chương trình sẽ không tự sinh ra IdP hay account thật.

Điều đã cấu hình:

- Lấy thông tin **AP/IdP** (issuer, SSO endpoint, verification certificate...) từ metadata đã phê duyệt.
- Tạo registration với tên `corp`.
- Chốt **SP entityID và ACS** khớp ứng dụng được IdP đăng ký.
- Đưa registration vào `RelyingPartyRegistrationRepository` để SAML filters tra cứu.
- Bật SAML login và endpoint phát hành SP metadata bằng hai DSL `saml2Login` và `saml2Metadata`.

Nếu IdP yêu cầu **AuthnRequest được ký**, SP phải có signing credentials thực (private key + certificate) và IdP phải biết public certificate của SP. Bản tối thiểu trên **không cấp sẵn private key ký**. Với metadata IdP yêu cầu ký mà chưa có credential phù hợp, request có thể thất bại; không nên tắt yêu cầu ký chỉ để vượt qua lỗi cấu hình.

Nếu môi trường đã có **Spring Boot property auto-configuration**, có thể chỉ cấu hình các thuộc tính `spring.security.saml2.relyingparty.registration.*` thay vì tạo repository bean. Lựa chọn một **nguồn cấu hình chính** và kiểm tra bean `RelyingPartyRegistrationRepository` nào thực sự đang được dùng.

## 6. Ví dụ cấu hình thủ công khi không dùng XML metadata

Trường hợp IdP cung cấp issuer, SSO URL và public signing certificate qua kênh quản trị riêng, có thể dựng registration thủ công bằng builder. Ví dụ mảnh mã cho **Spring Security 6.4+**:

~~~java
X509Certificate idpSigningCertificate = ...; // tải từ nguồn được phê duyệt
Saml2X509Credential idpVerification =
        Saml2X509Credential.verification(idpSigningCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistration
        .withRegistrationId("corp")
        .entityId("https://app.example.org/saml2/service-provider-metadata/corp")
        .assertionConsumerServiceLocation(
                "https://app.example.org/login/saml2/sso/corp")
        .assertingPartyMetadata(party -> party
                .entityId("https://login.example.org/saml/idp")
                .singleSignOnServiceLocation(
                        "https://login.example.org/saml/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(
                        credentials -> credentials.add(idpVerification)))
        .build();
~~~

Đây là **mảnh cấu hình, không phải chương trình độc lập**: `idpSigningCertificate` phải được tạo từ PEM/certificate thật qua API đọc certificate của Java; dấu ba chấm thể hiện đối tượng đầu vào do hạ tầng quản lý, không phải dữ liệu được ứng dụng phép thuật sinh ra. Cần import:

~~~java
import java.security.cert.X509Certificate;

import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
~~~

Giá trị `wantAuthnRequestsSigned(false)` chỉ thích hợp khi **IdP cho phép unsigned AuthnRequest và chính sách liên kết chấp nhận**. Nó **không** có nghĩa bỏ kiểm chữ ký Response/Assertion. Nếu IdP đòi request ký, dùng `signingX509Credentials` của SP và cấu hình certificate đối ứng tại IdP.

Khi chỉ làm việc với Spring Security **6.3**, API tên `assertingPartyMetadata` có thể chưa tồn tại; hãy sử dụng builder/API phù hợp với phiên bản đang chạy. Dòng Spring Security mới đã thay thế API `assertingPartyDetails` cũ bằng metadata API, nhưng mã ví dụ trong bản phát hành khác cần được xem lại trước khi sao chép.

### Cấu hình Spring Boot qua YAML

Ví dụ sau diễn tả **Spring Boot 3.x** khi khai báo trực tiếp issuer, SSO URL và IdP certificate:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/corp"
            acs:
              location: "https://app.example.org/login/saml2/sso/corp"
            assertingparty:
              entity-id: "https://login.example.org/saml/idp"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
~~~

Các property có thể đổi tên/alias giữa phiên bản **Spring Boot 3.x** và **4.x**; hãy đối chiếu với `Saml2RelyingPartyProperties` của đúng phiên bản. Khác với ví dụ Java đọc metadata, YAML trên đang khai **thông tin từng trường**, nên đường dẫn certificate phải là public certificate thực sự của IdP.

Các ví dụ Java/YAML là **hai cách thay thế để dạy cấu hình**, không nên đồng thời khai cùng registration theo hai nguồn mà không hiểu thứ tự override.

## 7. Các URI mặc định và sự liên quan đến registrationId

Trong Spring Security Servlet SAML login:

| URI phổ biến | Ai gọi | Chức năng |
| --- | --- | --- |
| `/saml2/authenticate/{registrationId}` | Browser/SP-initiated SSO | SP tạo AuthnRequest cho registration đã chọn |
| `/login/saml2/sso/{registrationId}` | Browser POST từ IdP | ACS, nhận SAMLResponse |
| `/login/saml2/sso/` | Browser POST từ IdP | Một lựa chọn ACS được hỗ trợ tùy cấu hình/khả năng xác định registration |
| `/saml2/metadata` | Admin IdP / tích hợp | Phát hành SP metadata |
| `/saml2/metadata/{registrationId}` | Admin IdP / tích hợp | Metadata của registration cụ thể |
| `/saml2/service-provider-metadata/{registrationId}` | Admin IdP / tích hợp | Đường dẫn metadata riêng từng registration, tương thích |
| `/logout/saml2/sso` | SAML Single Logout | Chỉ hoạt động khi cấu hình và hỗ trợ SLO phù hợp |

Thường có các placeholder do Spring resolve:

- `{registrationId}`: tên registration, ví dụ `corp`.
- `{baseUrl}`: scheme, host và port của ứng dụng trong ngữ cảnh request.
- `{baseScheme}`, `{baseHost}`, `{basePort}`: các thành phần base URL.

Giá trị mặc định quan trọng:

~~~text
SP entityId:
  {baseUrl}/saml2/service-provider-metadata/{registrationId}

SP Assertion Consumer Service Location:
  {baseUrl}/login/saml2/sso/{registrationId}
~~~

Khi deployed ở `https://app.example.org` với registrationId `corp`, chúng thường trở thành:

~~~text
https://app.example.org/saml2/service-provider-metadata/corp
https://app.example.org/login/saml2/sso/corp
~~~

Định dạng chính xác phụ thuộc mapping và thiết lập deployment. **EntityID không cần là URL truy cập được**; nếu dùng URI cụ thể làm entityID thì IdP phải được cấu hình khớp chính xác. **ACS URL thì phải trỏ tới endpoint có thể nhận POST**.

### Reverse proxy và forwarded headers

Nếu Internet đi qua ingress/gateway rồi vào Spring Boot bằng HTTP nội bộ, `{baseUrl}` có thể bị suy ra thành `http://127.0.0.1:8080` hoặc hostname nội bộ thay vì URL công khai. Lúc đó SP metadata, AuthnRequest issuer hoặc ACS có thể sai và IdP từ chối.

Hướng xử lý:

1. Cấu hình scheme/host/public port đúng ở ingress và cơ chế xử lý forwarded headers tin cậy của Spring/container.
2. **Chỉ tin các forwarded headers từ proxy được kiểm soát**; proxy phải loại bỏ header do client ngoài tự đặt.
3. Nếu phù hợp, cấu hình **entityID và ACS tuyệt đối** như ví dụ thay vì dựa vào baseUrl suy ra.
4. Truy cập SP metadata từ **đường public thật** và đối chiếu issuer/ACS với phần cấu hình tại IdP.

Không vô hiệu hóa kiểm tra SAML Destination/Audience để "sửa" lỗi host hoặc scheme. Sửa cấu hình tuyến đường và thông tin metadata trước.

## 8. Chính xác điều gì được tin: khóa, issuer, endpoint và điều kiện?

Một quan hệ SP–IdP an toàn dựa vào nhiều lớp, không chỉ một certificate.

| Kiểm tra | Dữ liệu tin cậy lấy ở đâu? | Rủi ro khi bỏ qua |
| --- | --- | --- |
| **IdP issuer** | `assertingPartyMetadata.entityId` đã phê duyệt | Chấp nhận assertion từ bên phát hành khác |
| **Chữ ký Response/Assertion** | `verificationX509Credentials` IdP đã tin cậy | Nhận phản hồi bị làm giả/sửa nội dung |
| **SP audience / entityID** | `RelyingPartyRegistration.entityId` | Dùng assertion phát cho SP khác |
| **Destination / Recipient** | ACS/public URL được cấu hình | Đưa response tới nơi không đúng |
| **Thời gian hiệu lực** | Conditions và SubjectConfirmation của assertion | Dùng lại assertion hết hạn hoặc chưa có hiệu lực |
| **InResponseTo / state** | AuthnRequest đã tạo và state tương ứng | Chấp nhận response không đúng phiên đăng nhập khi profile yêu cầu |
| **Decryption khi có mã hóa** | `decryptionX509Credentials` SP | Không đọc được nội dung mã hóa, hoặc cấu hình key sai |
| **Tài khoản và quyền nội bộ** | Kho user/mapping policy của ứng dụng | Liên kết sai người dùng hoặc cấp quyền quá mức |

Spring Security SAML authentication provider xử lý nhiều phép kiểm SAML trên. Tuy nhiên trách nhiệm vận hành vẫn bao gồm **cấu hình đúng giá trị mong đợi, không thay thế validator bằng logic lỏng lẻo, không tin response XML chỉ vì có nội dung NameID**.

Một trường hợp sai nguy hiểm:

~~~text
IdP tin cậy: https://login.company-a.example/saml
SAML Issuer: https://login.attacker.example/saml
Response tự khai NameID: alice@company-a.example
~~~

Nếu request không được xác minh với **đúng IdP issuer, khóa và registration** thì NameID chỉ là chuỗi do nguồn ngoài gửi. Không dùng NameID/email để tìm account trước khi xác thực SAML hoàn tất.

### Vai trò của Saml2X509Credential

Spring Security biểu diễn chứng thư/khóa SAML bằng `Saml2X509Credential` với mục đích sử dụng khác nhau:

- **VERIFICATION (IdP):** SP có **public certificate** của IdP để kiểm chữ ký SAML Response/Assertion.
- **SIGNING (SP):** SP có **private key + certificate** để ký AuthnRequest hoặc logout request khi profile yêu cầu.
- **DECRYPTION (SP):** SP có **private key + certificate** để giải mã assertion/attribute/NameID nếu IdP mã hóa.
- **ENCRYPTION (IdP):** phụ thuộc profile và nhu cầu mã hóa thông điệp SP gửi tới IdP; không tự coi mọi chứng thư public có cùng mục đích.

**Không lấy keypair SP làm verification key của IdP.** Đây là hai phía khác nhau của trust relationship. Certificate kiểm chữ ký SAML cũng không đương nhiên là certificate TLS của trang HTTPS IdP; phân biệt mục đích.

## 9. Trust bootstrap: tải metadata qua HTTPS vẫn chưa phải toàn bộ trust

Một mẫu thường thấy là:

~~~java
RelyingPartyRegistrations
        .fromMetadataLocation("https://login.example.org/metadata")
        .registrationId("corp")
        .build();
~~~

API hỗ trợ đọc metadata từ HTTPS, classpath và file. Nhưng với HTTPS, cần hiểu quy trình:

1. Ứng dụng kết nối đến URL đã cho qua TLS, dựa vào CA truststore của môi trường.
2. Metadata được parse thành thông tin IdP; certificate SAML có thể nằm **bên trong metadata**.
3. IdP signing certificate đó trở thành đầu vào cho cấu hình xác minh SAML message.

Điều này tạo ra **ranh giới quan trọng**: metadata endpoint phải là nguồn được phê duyệt và có tính toàn vẹn. Nếu attacker kiểm soát URL nội dung metadata và ứng dụng nhập khóa chưa kiểm chứng, họ có thể khiến SP tin một IdP/key không được phép.

Biện pháp phù hợp tùy tổ chức:

- **Classpath/file đã được kiểm duyệt:** cập nhật IdP metadata qua quy trình review, kiểm fingerprint/certificate và triển khai theo release.
- **HTTPS endpoint cố định:** hạn chế host/redirect, bảo đảm TLS và nguồn DNS/network tin cậy, kiểm soát ai được đổi URL; không lấy metadata URL trực tiếp từ request của người dùng.
- **Signed metadata:** nếu có chuẩn chia sẻ metadata ký, **kiểm chữ ký metadata với trust anchor được cấp từ bên ngoài**, không lấy khóa kiểm signature từ chính XML chưa tin cậy.
- **Audit thay đổi:** ghi nhận thay đổi entityID, ACS/SSO URLs, certificate, validUntil, algorithm và người phê duyệt.

**Cần phân biệt hai việc:** hệ thống tải tệp thành công và XML có cấu trúc hợp lệ không chứng minh metadata được tổ chức phê duyệt. Đây là vấn đề tin cậy ở bước nhập cấu hình.

### API xác minh metadata ở các phiên bản hỗ trợ

Tài liệu Spring Security mới giới thiệu `AssertingPartyMetadataRepository` và `OpenSaml5AssertingPartyMetadataRepository` để làm việc trực tiếp với IdP metadata, kể cả cơ chế refresh theo expiry. Khi dùng cách xây repository với `withMetadataLocation(...)`, cần cung cấp **metadata verification credentials** nếu muốn kiểm **chữ ký metadata**. Tài liệu chỉ rõ trường hợp không cung cấp credentials thì component không thực hiện signature validation của metadata.

Đây là một cơ chế **khác** với `verificationX509Credentials` của IdP trong `RelyingPartyRegistration` dùng kiểm SAML Response. Khi viết code phải phân biệt certificate ký **metadata** với certificate ký **message**, dù tổ chức có thể quản lý chúng chung một hệ PKI.

API có thể tùy phiên bản (ví dụ support OpenSAML 5 của Spring Security 6.4+/7.x). Không sao chép đoạn code của version mới vào project 6.3 nếu package/class đó chưa tồn tại; xem Javadoc phiên bản đang chạy.

## 10. Công bố metadata phía SP với Spring Security

Trong `SecurityFilterChain`, để cung cấp XML metadata cho IdP, thêm:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Đây là **mảnh DSL** thuộc cấu hình `HttpSecurity`, không phải đoạn chạy độc lập. Nó bật endpoint metadata mặc định thường là:

~~~text
GET /saml2/metadata
GET /saml2/metadata/corp
GET /saml2/service-provider-metadata/corp
~~~

Có thể tùy chỉnh endpoint, ví dụ:

~~~java
http.saml2Metadata(metadata -> metadata
        .metadataUrl("/internal/saml/metadata"));
~~~

Nếu thay đường dẫn, xác định rõ metadata URL public mà IdP sẽ truy cập và cập nhật bản đăng ký bên IdP. Việc đổi **đường dẫn metadata endpoint** không nhất thiết đồng nghĩa đổi **SP entityID**; hai trường có thể giống nhau theo convention nhưng có vai trò riêng.

Cách kiểm thử:

~~~bash
curl -fsS https://app.example.org/saml2/metadata/corp
~~~

Kết quả đúng là **XML metadata phía SP** nếu endpoint hoạt động và policy cho phép; bài học không giả định stdout cố định. Kiểm tra XML bằng parser phù hợp và so sánh:

- `EntityDescriptor@entityID` đúng SP entityID.
- `AssertionConsumerService@Location` đúng ACS Internet.
- Public certificate ký và/hoặc mã hóa xuất hiện khi SP đăng ký credentials tương ứng.
- HTTP scheme/host/path không bị sai do proxy.
- IdP đã import phiên bản metadata phù hợp.

Nếu nhiều registration và muốn xuất metadata tổng hợp, cần repository hỗ trợ **iteration** (ví dụ `InMemoryRelyingPartyRegistrationRepository`) theo yêu cầu API resolver. Một repository chỉ cung cấp `findByRegistrationId` có thể phục vụ SSO nhưng không đủ cho mọi tính năng duyệt hết registrations.

## 11. Nhiều IdP/tenant: chọn đúng registration

Một ứng dụng có thể liên kết nhiều IdP:

~~~text
corp        -> IdP của nhân viên tập đoàn
partners    -> IdP của đối tác
contractors -> IdP của nhà thầu
~~~

Trong Spring Security, `RelyingPartyRegistrationRepository` lưu tra cứu mỗi cấu hình bằng `registrationId`. Ví dụ Java (mảnh mã):

~~~java
RelyingPartyRegistration corp = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp.xml")
        .registrationId("corp")
        .build();

RelyingPartyRegistration partners = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/partners-idp.xml")
        .registrationId("partners")
        .build();

RelyingPartyRegistrationRepository repository =
        new InMemoryRelyingPartyRegistrationRepository(
                corp, partners);
~~~

Bản cấu hình thực tế cần có **SP entityID/ACS** tương ứng với những gì từng IdP đã đăng ký. Có thể chung SP entityID/ACS trong một số mô hình, hoặc khác theo tenant; cần xác nhận với từng IdP.

Một số điểm phải kiểm soát:

1. **Route login:** người dùng chọn `/saml2/authenticate/corp` hay `/saml2/authenticate/partners`.
2. **Registration resolver:** khi nhận response, Spring cần biết chính xác cấu hình áp dụng (theo trạng thái authentication request, đường dẫn hay IdP issuer theo khả năng framework). Đừng tự lấy registration tùy ý từ tham số client rồi bỏ qua kiểm issuer/audience.
3. **Tenant isolation:** nếu `alice` ở `corp` và `alice` ở `partners` là hai người khác nhau, mapping local account không thể dựa vào NameID trần.
4. **Key isolation:** các IdP có verification certificates riêng; đừng gom tất cả certificates thành một trust set chấp nhận được cho mọi tenant.
5. **Policy isolation:** quyền trên hệ thống đích có thể khác nhau theo tenant. Không cấp role từ SAML attribute `admin` khi issuer không có quyền cấp role đó.

Một khóa định danh nội bộ có thể dựa vào **(registrationId, issuer, stable subject identifier)**, với điều kiện IdP cung cấp NameID/subject identifier có tính ổn định và chính sách quản lý tái cấp. Nếu tenant di chuyển giữa IdP hoặc certificate rotate, quy trình migration/identity linking cần rõ ràng; không tự ghép tài khoản chỉ vì email giống nhau.

## 12. Metadata refresh và certificate rotation

Metadata và chứng thư không tồn tại mãi. IdP có thể đổi signing certificate, SSO URL, entityID hoặc chính sách AuthnRequest. SP cũng có thể thay signing/decryption keypair.

### Rollover IdP verification certificate

Một kế hoạch an toàn thường là:

1. Nhận thông báo hoặc phát hiện metadata mới từ nguồn đáng tin.
2. Xác minh **nguồn metadata**, người phê duyệt và certificate mới.
3. Nếu IdP hỗ trợ giai đoạn chồng lấp, tạm tin **cả certificate cũ và mới** đúng trong phạm vi IdP đó.
4. Quan sát những SAML signatures hợp lệ bằng khóa mới và kết quả SSO.
5. Sau thời gian chuyển đổi, loại bỏ certificate cũ có kiểm soát.

Không ghi đè key cũ ngay nếu IdP vẫn đang ký response bằng nó trong thời gian rollover; làm vậy có thể gây gián đoạn login. Ngược lại, không giữ vô thời hạn certificate cũ đã bị thu hồi hoặc không còn thuộc trust policy.

### Rollover SP signing/decryption certificate

- Với **signing**, cập nhật certificate public của SP để IdP biết khóa mới trước khi SP bắt đầu dùng private key mới.
- Với **decryption**, nếu IdP còn mã hóa cho public certificate cũ thì SP cần giữ private key cũ trong giai đoạn chuyển đổi, với quyền truy cập chặt.
- Key riêng phải lưu trong secret manager/keystore hoặc hạ tầng HSM/KMS thích hợp, không commit PEM private key lên Git hay nhúng trong metadata.
- Sau khi đổi, xuất SP metadata mới và kiểm tra IdP đã đồng bộ.

### Metadata không tự refresh chỉ vì URL là HTTPS

Nếu `RelyingPartyRegistrations.fromMetadataLocation(...)` được gọi **một lần lúc khởi tạo bean**, registration được tạo tại thời điểm đó. Không mặc định nó tự tải metadata sau mỗi request.

Các hướng cập nhật:

- Chủ động triển khai lại khi thay metadata classpath.
- Dùng repository/caching strategy có khả năng refresh dựa trên chính sách thời hạn.
- Dùng hỗ trợ `AssertingPartyMetadataRepository` với resolver có logic expiry và xác minh chữ ký metadata nếu phiên bản Spring Security hỗ trợ.
- Thiết kế cơ chế đồng bộ metadata có xác thực, cache, thời gian refresh, rollback và quan sát lỗi.

Đọc `validUntil`/`cacheDuration` đúng ngữ nghĩa ở metadata, nhưng đừng đồng nhất nó với **thời hạn X.509 certificate** hoặc **thời gian sống của SAML Assertion**. Đây là ba vòng đời khác nhau.

## 13. Mini lab Java 17: đối chiếu định danh của một registration

Đây là **chương trình Java độc lập để học kiểm tra những bất biến cấu hình**. Nó **không parse XML, không xác minh chữ ký, không xác thực SAML** và tuyệt đối không được dùng thay Spring Security/OpenSAML ở production.

Tệp **SamlRegistrationCheck.java**:

~~~java
import java.util.Map;

public class SamlRegistrationCheck {

    record Registration(String spEntityId, String acs, String idpEntityId) {}

    static String check(Map<String, Registration> registrations,
                        String registrationId,
                        String issuer,
                        String audience,
                        String destination) {
        Registration expected = registrations.get(registrationId);
        if (expected == null) {
            return "REJECT: registration";
        }
        if (!expected.idpEntityId().equals(issuer)) {
            return "REJECT: issuer";
        }
        if (!expected.spEntityId().equals(audience)) {
            return "REJECT: audience";
        }
        if (!expected.acs().equals(destination)) {
            return "REJECT: destination";
        }
        return "MATCHED CONFIG ONLY";
    }

    public static void main(String[] args) {
        String sp = "https://app.example.org/sp";
        String acs = "https://app.example.org/login/saml2/sso/corp";
        String idp = "https://login.example.org/idp";

        Map<String, Registration> registrations =
                Map.of("corp", new Registration(sp, acs, idp));

        System.out.println(check(registrations, "corp", idp, sp, acs));
        System.out.println(check(registrations, "corp", "other", sp, acs));
        System.out.println(check(registrations, "corp", idp, "other", acs));
        System.out.println(check(registrations, "corp", idp, sp, "other"));
        System.out.println(check(registrations, "unknown", idp, sp, acs));
    }
}
~~~

Chạy trên Java 17 trở lên:

~~~bash
javac SamlRegistrationCheck.java
java SamlRegistrationCheck
~~~

Stdout chính xác:

~~~text
MATCHED CONFIG ONLY
REJECT: issuer
REJECT: audience
REJECT: destination
REJECT: registration
~~~

Ý nghĩa: ngay cả trước khi bàn đến danh tính của người dùng, cấu hình đã phải xác định **issuer thuộc IdP nào, audience thuộc SP nào, response gửi về ACS nào, registration được chọn nào**. Lệnh `MATCHED CONFIG ONLY` chỉ có nghĩa bốn chuỗi ví dụ khớp kỳ vọng; **chưa hề chứng minh SAML Response đáng tin**. Spring Security/OpenSAML thực hiện nhiều validation về chữ ký số, SAML Conditions, SubjectConfirmation, request correlation và thời gian — không bỏ những bước đó.

## 14. Các lỗi tích hợp phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và sửa |
| --- | --- | --- |
| Không chuyển hướng đến IdP | Không có registration, registrationId sai, SSO URL thiếu/sai | Kiểm `/saml2/authenticate/corp` và SSO endpoint trong metadata |
| ACS trả lỗi/không match route | IdP POST tới URL khác, context path/proxy sai | So sánh `AssertionConsumerService@Location` trong SP metadata với IdP console |
| `Issuer` không khớp | Nhầm IdP entityID với URL SSO hoặc registration khác | Kiểm response issuer và `assertingPartyMetadata.entityId` |
| `Audience` không hợp lệ | IdP tạo assertion cho SP entityID khác | So sánh SP `entityId` và cấu hình "Audience/Entity ID" của IdP |
| Không xác minh được chữ ký | IdP signing certificate khác thực tế; key rollover chưa đồng bộ | Xác nhận trust source, certificate hiện tại và thuật toán ký |
| AuthnRequest bị IdP từ chối | IdP yêu cầu ký nhưng SP thiếu signing credentials; binding/endpoint khác | Kiểm metadata yêu cầu ký, cấu hình SP key và binding |
| Không giải mã được assertion | Thiếu/wrong SP decryption private key, IdP dùng key công khai cũ | Kiểm SP metadata encryption certificate và vòng đời khóa |
| SP metadata hiển thị `http://localhost` | Sai Forwarded headers/public baseUrl | Sửa cấu hình ingress, proxy trust hoặc dùng URI tuyệt đối |
| SSO thành công nhưng lẫn tài khoản tenant | Chỉ map theo NameID/email không xét issuer/tenant | Dùng khóa danh tính có namespace IdP và mapping được kiểm soát |
| Metadata mới không có tác dụng | Registration được dựng một lần lúc startup, không refresh | Dùng quy trình refresh/restart có xác minh |
| Metadata XML tải được nhưng login không an toàn | Metadata trust bootstrap chưa kiểm tra, tự nhận certificate | Pin nguồn, review thay đổi, xác minh metadata signature/trust anchor khi có |
| SSO thất bại ngẫu nhiên gần lúc rollover | Hai đầu chuyển key lệch thời điểm | Hỗ trợ overlap và theo dõi certificate được sử dụng |

### Lưu ý về lỗi 401/403 và quyền truy cập

Khi SAML authentication hoàn tất, Spring có thể tạo `Saml2Authentication` và principal thực hiện theo `Saml2AuthenticatedPrincipal`. `Authentication.getName()` thường phản ánh NameID được provider map. Điều đó **không đồng nghĩa** account được cấp mọi role nội bộ.

Một response từ IdP tin cậy có thể dẫn tới **đăng nhập thành công nhưng bị 403** ở resource vì người dùng không có authority phù hợp. Không "sửa" lỗi này bằng cách vô hiệu hóa xác minh signature/audience hoặc bỏ authorization. Kiểm tra identity linking và mapping quyền ở bước sau khi xác thực.

## 15. Checklist kiểm thử tích hợp trước khi triển khai

Kiểm thử ít nhất các nhóm tình huống:

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| IdP metadata xác thực nguồn, đúng entityID và certificate | Registration load đúng và export SP metadata phù hợp |
| Metadata URL sai, XML hỏng hoặc certificate thay đổi không phê duyệt | Fail rõ nguyên nhân; không tiếp tục tin giá trị không xác minh |
| Đăng nhập hợp lệ từ IdP corp | Chấp nhận với đúng registration, issuer, audience và ACS |
| SAML Response có chữ ký không hợp lệ hoặc key IdP khác | Từ chối xác thực |
| Assertion Audience/Recipient/Destination khác SP | Từ chối |
| Assertion hết hạn hoặc NotBefore ở tương lai | Từ chối |
| Response phát cho tenant A gửi đến tenant B | Từ chối hoặc không được cấp account/role của B |
| IdP yêu cầu signed AuthnRequest | SP ký bằng signing key tương ứng IdP đã đăng ký |
| IdP encrypt assertion | SP giải mã bằng private key được phép sử dụng |
| IdP signing key rollover trong giai đoạn chồng lấp | Các key được phê duyệt hoạt động, key cũ được thu hồi đúng hạn |
| Reverse proxy thay đổi host/scheme | Metadata và ACS vẫn dùng địa chỉ công khai đã phê duyệt |
| User NameID/email trùng giữa tenant | Không tự động hợp nhất hai account |
| Truy cập resource yêu cầu role | Quyền phụ thuộc mapping nội bộ, không phụ thuộc NameID text |
| Một registration bị xóa/disable | Không tiếp tục chọn hoặc tin response từ registration đó |

Với dự án Spring, dùng **integration test có IdP thật hoặc IdP mô phỏng đúng giao thức**, các certificate test riêng và HTTP test chạy qua filter chain. Unit test builder/repository chỉ kiểm cấu hình; nó **không thay thế** kiểm chứng chữ ký số, replay, state và TLS/metadata trust.

Khi điều tra, ghi log có correlation ID, registrationId, lỗi ở bước xác minh và metadata version. Tránh log nguyên SAMLResponse, assertion chứa dữ liệu cá nhân, private key hoặc password. Không hiển thị certificate private key trong endpoint metadata.

## 16. Quy tắc thiết kế và vận hành

Trước khi tích hợp một IdP, hãy chốt văn bản cấu hình:

1. **Ai là RP và AP?** Cặp entityID nào được phép tin, registrationId nội bộ là gì?
2. **Metadata đến từ đâu?** HTTPS endpoint, file đã ký hay tài liệu được cấp qua kênh quản trị? Ai chịu trách nhiệm phê duyệt và cập nhật?
3. **Các endpoint nào là public?** URL SSO của IdP, ACS của SP, metadata SP, logout nếu dùng.
4. **Các khóa có vai trò gì?** IdP public signing certificate để kiểm; SP signing/decryption keypair với quản lý secret; metadata-signature trust nếu dùng.
5. **Quy tắc xác thực là gì?** Chữ ký, issuer, audience, destination, thời gian, correlation, replay và thuật toán phải tuân theo profile.
6. **Cách liên kết người dùng?** NameID/subject nào ổn định, có xét issuer/tenant, account lifecycle và quyền không?
7. **Vận hành thế nào?** Khi IdP đổi khóa/endpoint hoặc khi SP đổi ACS/entityID, bên nào cập nhật trước và cần overlap bao lâu?

Tư duy cốt lõi: **`RelyingPartyRegistration` là hợp đồng kỹ thuật và tin cậy giữa một SP với một IdP**. Metadata giúp mô tả hợp đồng này, còn việc xác thực SAML Response phải dùng thông tin đã được tin cậy để kiểm chữ ký và các điều kiện. Sau đó, ứng dụng mới liên kết NameID/attributes với tài khoản và quyết định quyền truy cập.

### Tài liệu chính thức

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 — RelyingPartyRegistration API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- Spring Security — RelyingPartyRegistrations API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html
- Spring Boot — SAML 2.0 configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- OASIS — SAML 2.0 core specifications: https://docs.oasis-open.org/security/saml/v2.0/
