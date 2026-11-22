# Tách entityId, ACS, khóa và chính sách thuộc tính theo đối tác trong Spring Security SAML 2.0

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng Spring Boot có thể phục vụ **nhiều doanh nghiệp, tenant hoặc đối tác** nhưng cho phép người dùng của mỗi đối tác đăng nhập qua **Identity Provider (IdP)** của họ. Trong SAML 2.0, ứng dụng đóng vai **Service Provider (SP / Relying Party)**; IdP đóng vai **Asserting Party**. Ví dụ:

- Đối tác **Alpha** sử dụng `https://alpha-idp.example.test/issuer`, yêu cầu SP Entity ID riêng, ACS riêng, signing certificate Alpha và thuộc tính `employeeId`, `groups`.
- Đối tác **Beta** sử dụng `https://beta-idp.example.test/issuer`, yêu cầu một SP Entity ID/ACS khác, khóa SP riêng và thuộc tính `uid`, `entitlements`.
- Cả hai được phục vụ bởi **cùng một codebase Java, cùng database ứng dụng và cùng giao diện web**.

Bài toán không chỉ là “thêm hai đường dẫn SSO”. Nếu hệ thống dùng nhầm **issuer, audience, ACS, certificate, signing/decryption key hoặc quy tắc ánh xạ thuộc tính** giữa các đối tác, người dùng của Beta có thể vô tình bị nhận như user Alpha, chứng thư của IdP này có thể được dùng để tin response IdP khác hoặc một group tự khai có thể biến thành quyền quản trị ở tenant khác.

Bài học thuộc nhóm **Nhiều IdP và tenant** và tập trung vào các mục tiêu sau:

1. Hiểu **`RelyingPartyRegistration` là một mối quan hệ SP–IdP**, thường gắn với một `registrationId` riêng.
2. Tách **SP entityId**, **ACS (Assertion Consumer Service)**, khóa SP và khóa xác minh IdP theo **đúng đối tác**; biết phần nào *có thể* chia sẻ có chủ đích.
3. Chọn registration khi tạo AuthnRequest và khi nhận SAML Response **mà không coi URL, RelayState hoặc Issuer chưa xác minh là bằng chứng tin cậy**.
4. Xác thực response bằng đúng IdP certificate, kiểm tra Audience/Recipient/Destination/InResponseTo, rồi mới áp chính sách **NameID, thuộc tính, groups, quyền và tenant**.
5. Thiết kế identity linking, JIT provisioning, rotation và multi-tenant authorization mà không tạo lỗi cross-tenant.
6. Kiểm thử các tình huống **cross-partner confusion** và chẩn đoán sai ACS/certificate/attribute policy.

**Nguyên tắc:** với mỗi response, phải có một **registration tin cậy được chọn đúng**. Hệ thống không được lấy “IdP A ký hợp lệ” làm lý do chấp nhận response dành cho SP B, và cũng không được dùng thuộc tính của người dùng chưa qua validation để chọn trust configuration.

## 2. Bốn lớp cần tách theo đối tác

Mô hình dễ hiểu:

~~~text
                  Ứng dụng Java / Spring Security
                            |
               RelyingPartyRegistrationRepository
                            |
                +-----------+------------+
                |                        |
      registrationId="alpha"    registrationId="beta"
                |                        |
       SP Entity ID Alpha        SP Entity ID Beta
       ACS Alpha                 ACS Beta
       SP signing key Alpha      SP signing key Beta
       SP decryption key Alpha   SP decryption key Beta
       IdP issuer Alpha          IdP issuer Beta
       IdP verification Alpha    IdP verification Beta
       Attribute policy Alpha    Attribute policy Beta
       Tenant = A                Tenant = B
                |                        |
           IdP Alpha                 IdP Beta
                |                        |
                +---------> local user / permissions
                              scoped by tenant
~~~

Trong Spring Security, **một `RelyingPartyRegistration` mô tả cặp relying party và asserting party**. `registrationId` là định danh nội bộ để phân biệt các cấu hình. Tài liệu Spring Security cho phép multi-tenant bằng cách đăng ký nhiều `RelyingPartyRegistration` trong `RelyingPartyRegistrationRepository`.

**Quan trọng:** không bắt buộc mỗi IdP phải dùng **SP Entity ID, ACS hoặc private key khác nhau** trong mọi thiết kế. Spring Security tài liệu hóa tình huống nhiều registration **cùng entityId, ACS hoặc credential**. Tuy nhiên **khi yêu cầu bài toán là tách theo đối tác**, nên chọn chính sách tách rõ những thành phần có rủi ro hoặc cần vòng đời riêng. Nếu chia sẻ một thành phần, cần tài liệu hóa **vì sao được phép chia sẻ và ranh giới kiểm soát vẫn được bảo toàn**.

### 2.1. Ma trận chính sách

| Thành phần | Alpha | Beta | Ràng buộc bắt buộc |
| --- | --- | --- | --- |
| `registrationId` | `alpha` | `beta` | **Duy nhất** trong repository |
| Tenant nội bộ | `tenant-a` | `tenant-b` | Không lấy tenant trực tiếp từ claim chưa xác minh |
| SP `entityId` | `urn:portal:sp:alpha` | `urn:portal:sp:beta` | Phải đúng Audience/SP đã đăng ký với IdP |
| ACS URL | `https://portal.example.test/login/saml2/sso/alpha` | `https://portal.example.test/login/saml2/sso/beta` | Khớp filter, Recipient/Destination, IdP config |
| IdP `entityId` | `https://alpha-idp.example.test/issuer` | `https://beta-idp.example.test/issuer` | Issuer và trust policy phải đúng |
| SP signing key | `alpha-sp-sign` | `beta-sp-sign` | Private key SP không được trộn hoặc lộ cho IdP |
| SP decryption key | `alpha-sp-decrypt` | `beta-sp-decrypt` | Chỉ giải mã bằng key ring được phép của registration |
| IdP verification cert | `alpha-idp-signing` | `beta-idp-signing` | Chỉ tin public cert của IdP đã cấp/đăng ký |
| Stable subject attr | `employeeId` | `uid` | Được kiểm chứng trong đúng policy |
| Group attr | `groups` | `entitlements` | Không biến giá trị group thành authority trực tiếp |
| Role mapping | `engineers -> ROLE_ALPHA_EDITOR` | `partner-viewer -> ROLE_BETA_READER` | Allowlist riêng, quyền nghiệp vụ của tenant |

Đây là **một ví dụ kiến trúc minh họa**, không phải chuẩn SAML bắt buộc. Các URI `example.test`/URN và alias key cần được thay bằng giá trị **đã thỏa thuận** tại hệ thống thực.

## 3. `registrationId`, SP entityId và IdP entityId là ba khái niệm khác nhau

### 3.1. registrationId là khóa local

Spring Security dùng `registrationId` để tìm `RelyingPartyRegistration`. Chẳng hạn, `alpha` thường xuất hiện ở:

~~~text
/saml2/authenticate/alpha
/login/saml2/sso/alpha
/saml2/metadata/alpha
~~~

`alpha` chỉ là **tên do ứng dụng chọn**. Không nên suy rằng tên này tự là tenant ID, IdP Entity ID hoặc SAML issuer. Nó chỉ trỏ đến một cấu hình đã được quản trị, trong đó có **tenant mapping đáng tin cậy**.

### 3.2. SP entityId là định danh bên nhận

Trong AuthnRequest, `<saml:Issuer>` thường mang **SP entityId**. Trong Assertion từ IdP, `AudienceRestriction/Audience` phải phù hợp SP mà assertion được phát hành cho.

Ví dụ:

~~~text
Alpha SP Entity ID = urn:portal:sp:alpha
Beta SP Entity ID  = urn:portal:sp:beta
~~~

Một assertion có `Audience=urn:portal:sp:alpha` **không được** mang sang registration Beta chỉ vì user ID hoặc email trùng. Audience là một trong các bước bảo vệ “assertion được phát cho ai”.

### 3.3. IdP entityId là định danh nhà phát hành

~~~text
Alpha IdP Entity ID = https://alpha-idp.example.test/issuer
Beta IdP Entity ID  = https://beta-idp.example.test/issuer
~~~

IdP entityId thường nằm trong `<saml:Issuer>` của Response/Assertion. **Không dùng domain email hoặc URL ACS để đoán IdP được tin cậy**. Issuer cần được đối chiếu với registration và **chữ ký phải hợp lệ theo certificate của chính IdP ấy**. Một text Issuer ở XML chưa xác minh chỉ có thể dùng như hint cho lookup, không được tự mở rộng danh sách certificate được phép.

### 3.4. Một thực thể có thể có nhiều tenant

Có đối tác dùng **một IdP Entity ID cho nhiều tenant** hoặc các ứng dụng con cùng tổ chức. Trong trường hợp đó, chỉ nhìn issuer **không đủ** để phân biệt tenant. Cần SP-initiated request state, route/context đã được bảo vệ hoặc một cơ chế registration resolver được thiết kế rõ ràng. Nếu không phân biệt được registration một cách không nhập nhằng, phải **từ chối**, không chọn tenant đầu tiên.

## 4. ACS: tách URL hay dùng chung?

**Assertion Consumer Service (ACS)** là endpoint phía SP tiếp nhận **SAML Response** sau khi IdP xác thực người dùng. Nó khác với **SingleSignOnService của IdP**, nơi SP gửi AuthnRequest.

Trong Spring Security Servlet, đường processing phổ biến là:

~~~text
POST /login/saml2/sso/{registrationId}
~~~

Nếu thiết kế tách theo đối tác:

~~~text
POST /login/saml2/sso/alpha
POST /login/saml2/sso/beta
~~~

Lợi ích:

- Dễ biết callback nào dự kiến phục vụ registration nào.
- Dễ xuất metadata SP riêng cho từng đối tác.
- Giảm khả năng cấu hình nhầm ACS trên portal của IdP.
- Có thể quan sát lỗi/latency/volume theo registration.
- Tương thích phương thức chọn registration bằng path hoặc request state của Spring Security.

**Nhưng đường dẫn chứa `alpha` không phải bằng chứng SAML hợp lệ.** Attacker vẫn có thể POST một `SAMLResponse` bất kỳ tới `/alpha`. Spring Security phải kiểm chữ ký, issuer, audience, destination, recipient, thời gian, correlation và các điều kiện khác **trước khi tạo Authentication**.

### 4.1. Nếu dùng một ACS chung

Một ACS chung cũng có thể hợp lệ:

~~~text
POST /login/saml2/sso
~~~

Khi đó cần cách chọn `RelyingPartyRegistration` đúng, ví dụ dựa trên **AuthnRequest đã lưu và `InResponseTo`**, hoặc custom converter/resolver có quy tắc rõ ràng. Tài liệu Spring Security cho biết khi nhận SAML Response, bộ chuyển đổi có thể tìm registration từ AuthnRequest liên quan, từ `registrationId` trên URL, hoặc từ `Response/Issuer` khi không có thông tin trước đó.

**Cảnh báo trust bootstrap:** nếu quyết định chọn cấu hình dựa vào Issuer trước khi xác minh chữ ký, xem Issuer chỉ là **giá trị giúp tìm candidate**. Sau đó phải xác minh chữ ký bằng **IdP verification credential của candidate** và kiểm tra lại toàn bộ giá trị, không tin Issuer đơn thuần.

Với **nhiều tenant dùng chung một IdP issuer**, việc chỉ dựa vào issuer có thể mơ hồ; cần một nguồn correlation đáng tin hơn. Nếu SAML Response là **IdP-initiated/unsolicited**, thường không có `InResponseTo`; phải có **chính sách rõ cho phép/từ chối** và cơ chế resolution an toàn.

### 4.2. Custom loginProcessingUrl phải khớp ACS đã công bố

Spring Security có DSL:

~~~java
http.saml2Login(saml2 -> saml2
    .loginProcessingUrl("/saml/acs/{registrationId}"));
~~~

Đây là **trích đoạn cấu hình**, không phải file Java độc lập. Nếu thay đường xử lý của filter, cần cập nhật **`assertionConsumerServiceLocation`** và metadata SP tương ứng; không chỉ đổi một đầu.

Nếu ứng dụng công bố:

~~~text
https://portal.example.test/saml/acs/alpha
~~~

nhưng IdP gửi về:

~~~text
https://portal.example.test/login/saml2/sso/alpha
~~~

thì lỗi có thể là HTTP 404, filter không bắt, hoặc `Destination/Recipient` không khớp. Sửa **hợp đồng URL giữa SP và IdP**, không tắt check Destination.

### 4.3. Reverse proxy và host-based tenants

Khi ứng dụng chạy sau proxy, `{baseUrl}` có thể được Spring Security suy ra từ request. Nếu proxy đưa host nội bộ hoặc scheme `http` chưa được cấu hình đúng, metadata/ACS sẽ sai.

Chỉ tin **forwarded headers từ proxy đã được kiểm soát**, không để HTTP Host hoặc `X-Forwarded-Host` do khách Internet tự đưa vào làm thay đổi ACS/Entity ID tùy ý. Tốt nhất dùng URL công khai cố định hoặc cơ chế base URL tin cậy đã được duyệt, và kiểm thử metadata thực tế sau deploy.

## 5. Một registration theo đối tác trong Spring Security

`RelyingPartyRegistration` chứa hai nhóm thông tin:

~~~text
RelyingPartyRegistration("alpha")
   Relying Party (SP):
       entityId
       assertionConsumerServiceLocation
       signingX509Credentials
       decryptionX509Credentials

   Asserting Party (IdP):
       entityId
       singleSignOnServiceLocation + binding
       verificationX509Credentials
       wantAuthnRequestsSigned
       metadata / encryption preferences
~~~

`InMemoryRelyingPartyRegistrationRepository` có thể lưu nhiều registrations. Dự án lớn có thể dùng repository backed bởi database, cache hoặc metadata provider được quản trị. Quan trọng là **một lookup theo registrationId trả đúng cấu hình của cặp SP–IdP**, không gộp tất cả IdP certificate vào một “global verification list” không có scope.

### 5.1. Mẫu Spring Boot YAML cho hai đối tác

Ví dụ Spring Boot 3.x/Spring Security SAML2 Servlet, với private keys được mount an toàn từ filesystem. Đây là **cấu hình minh họa để tích hợp**, không thể chạy SSO nếu thiếu certificate, metadata và IdP thật.

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          alpha:
            entity-id: "urn:portal:sp:alpha"
            acs:
              location: "https://portal.example.test/login/saml2/sso/alpha"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/alpha-sign.pem"
                  certificate-location: "file:/etc/saml/alpha-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/alpha-dec.pem"
                  certificate-location: "file:/etc/saml/alpha-dec.crt"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-alpha.xml"

          beta:
            entity-id: "urn:portal:sp:beta"
            acs:
              location: "https://portal.example.test/login/saml2/sso/beta"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/beta-sign.pem"
                  certificate-location: "file:/etc/saml/beta-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/beta-dec.pem"
                  certificate-location: "file:/etc/saml/beta-dec.crt"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-beta.xml"
~~~

**Giải thích từng tầng:**

1. `registration.alpha` và `registration.beta` tạo hai quan hệ SP–IdP khác nhau.
2. `entity-id` của SP là Audience SP mong đợi theo cấu hình của đối tác, không phải IdP Entity ID.
3. `acs.location` là callback SP dành cho **SAML Response**; khác với IdP SSO URL chứa trong metadata.
4. **signing.credentials** là cặp private key + X.509 certificate của **SP** để ký AuthnRequest hoặc thông điệp SAML khác nếu cần.
5. **decryption.credentials** là cặp private key + certificate của **SP** để giải mã EncryptedAssertion được IdP mã hóa bằng public cert SP.
6. `assertingparty.metadata-uri` trỏ tới metadata **IdP** của đúng đối tác, gồm IdP issuer, SSO endpoints và verification keys; nguồn file cục bộ vẫn cần quy trình **trust/onboarding và refresh**.
7. File `alpha-sign.pem`/`beta-sign.pem` trong ví dụ **không phải key có sẵn**; private key phải được cấp trong secret manager/volume bảo mật theo đúng entity/tenant.
8. Các đường dẫn dùng `file:` phải tồn tại **bên trong JVM/container**. Không nhúng private key production vào classpath/JAR/image.

**Điều cần kiểm phiên bản:** Spring Boot/Spring Security có thể thay tên API/property giữa các nhánh. `spring.security.saml2.relyingparty.registration.<id>.entity-id`, `acs.location`, `signing.credentials`, `decryption.credentials` và `assertingparty.metadata-uri` phải được đối chiếu với configuration metadata của **bản đang chạy**.

### 5.2. Có thể tách IdP verification certificate thủ công

Một số đối tác không cung cấp metadata URL thuận tiện. Khi đó một registration có thể khai các thuộc tính của IdP trực tiếp:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          alpha:
            entity-id: "urn:portal:sp:alpha"
            acs:
              location: "https://portal.example.test/login/saml2/sso/alpha"
            assertingparty:
              entity-id: "https://alpha-idp.example.test/issuer"
              singlesignon:
                url: "https://alpha-idp.example.test/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-alpha-sign.crt"
~~~

Đây là **cách khai báo nguồn trust phía IdP**, không phải signing credential của SP. Nếu trong thực tế IdP yêu cầu AuthnRequest signed, cần chỉnh `sign-request` và cấp **SP signing key** hợp lệ, không copy cờ `false` một cách máy móc.

Nếu IdP A và IdP B dùng issuer khác nhau, không chép file `idp-alpha-sign.crt` sang Beta chỉ để “login hết lỗi”. **Xác minh chứng thư phải được giới hạn theo nhà phát hành và đối tác.**

## 6. Cấu hình Java với RelyingPartyRegistrationRepository

Với yêu cầu nâng cao, có thể xây registrations bằng Java. Ví dụ dưới đây là **một đoạn dùng bên trong cấu hình Spring Boot**; các biến `alphaSigningCredential`, `alphaDecryptionCredential`, `betaSigningCredential`, `betaDecryptionCredential` đã được cấp phát dưới dạng `Saml2X509Credential` đúng purpose và khóa tương ứng:

~~~java
RelyingPartyRegistration alpha =
    RelyingPartyRegistrations
        .fromMetadataLocation("file:/etc/saml/idp-alpha.xml")
        .registrationId("alpha")
        .entityId("urn:portal:sp:alpha")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/alpha")
        .signingX509Credentials(c -> c.add(alphaSigningCredential))
        .decryptionX509Credentials(c -> c.add(alphaDecryptionCredential))
        .build();

RelyingPartyRegistration beta =
    RelyingPartyRegistrations
        .fromMetadataLocation("file:/etc/saml/idp-beta.xml")
        .registrationId("beta")
        .entityId("urn:portal:sp:beta")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/beta")
        .signingX509Credentials(c -> c.add(betaSigningCredential))
        .decryptionX509Credentials(c -> c.add(betaDecryptionCredential))
        .build();

RelyingPartyRegistrationRepository registrations =
    new InMemoryRelyingPartyRegistrationRepository(alpha, beta);
~~~

**Đây là snippet, không phải chương trình `javac` độc lập.** Cần imports, Spring Security dependencies, biến credentials, bean repository và SecurityFilterChain thực tế. Chức năng `fromMetadataLocation` nạp metadata nhưng **không mặc nhiên xác minh chữ ký metadata bằng trust anchor độc lập**. Nếu chính sách yêu cầu signed metadata, phải dùng metadata repository/trust engine tương thích và khóa metadata signer đã được provision trước.

Một `SecurityFilterChain` SAML đơn giản:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .saml2Metadata(Customizer.withDefaults());
    return http.build();
}
~~~

Đoạn code thứ hai **thuộc class cấu hình Spring** có imports và beans tương ứng; nó không tự nạp hai IdP nếu không có repository bean. Spring Boot thường tự kết nối repository bean với filter chain. Nếu custom nhiều repository hoặc nhiều filter chains, xác nhận **filter đang sử dụng đúng repository** thay vì chỉ nhìn tên bean.

### 6.1. Metadata SP theo từng registration

Với `saml2Metadata()` trong Spring Security, có thể dùng endpoint như:

~~~text
/saml2/metadata/alpha
/saml2/metadata/beta
/saml2/service-provider-metadata/alpha
/saml2/service-provider-metadata/beta
~~~

Bên Alpha cần nhìn thấy **SP entityId, ACS và public certificate dành cho Alpha**, bên Beta nhìn thấy cấu hình Beta. Đây là dữ liệu để IdP onboarding, không phải secret private key.

Cần kiểm tra metadata xuất thực tế:

- `EntityDescriptor/@entityID` đúng SP Entity ID đã thỏa thuận.
- `AssertionConsumerService/@Location` đúng callback public HTTPS.
- `KeyDescriptor use="signing"` hoặc `use="encryption"` phù hợp mục đích và certificate đã cấp.
- Các thuật toán/binding tương thích IdP.
- Không công bố đường dẫn `localhost`, IP nội bộ, host sai hoặc certificate của tenant khác.

Metadata có nhiều `EntityDescriptor` hoặc endpoint tổng hợp cũng có thể hợp lệ, nhưng **onboarding của từng đối tác phải chỉ rõ entity/certificate nào thuộc họ**.

## 7. Chọn registration khi phát AuthnRequest

Một login bắt đầu từ ứng dụng có thể như sau:

~~~text
GET /saml2/authenticate/alpha
      |
      v
RelyingPartyRegistrationRepository.findByRegistrationId("alpha")
      |
      +-> SP issuer = urn:portal:sp:alpha
      +-> Destination = SSO URL trong IdP Alpha metadata
      +-> ACS = https://portal.example.test/login/saml2/sso/alpha
      +-> Signing key = alpha-sign
      +-> Request ID + RelayState được lưu theo flow
      |
      v
Browser -> IdP Alpha -> SAML Response -> ACS Alpha
~~~

Điều này là **SP-initiated login**, có request state để so `InResponseTo` khi IdP phản hồi. Với Beta, đường tương ứng dùng registration `beta`, không được tái sử dụng request state của Alpha.

**Đừng chọn tenant từ email domain chưa được xác thực** rồi coi đó là trust. Email/tenant hint trên trang login có thể giúp hiển thị các tùy chọn, nhưng request cuối cùng phải gắn với **registration trong allowlist** và state không thể bị chuyển chéo bởi browser.

### 7.1. IdP-initiated/unsolicited login

IdP có thể phát SAML Response đến ACS **không có AuthnRequest do SP gửi trước**. Tùy chính sách, SP có thể chấp nhận hoặc từ chối unsolicited login.

Trong multi-tenant:

- Nếu ACS có `registrationId`, đó chỉ là **candidate lookup**.
- Nếu ACS dùng chung và hai registration có cùng issuer, có thể **không đủ thông tin** để chọn tenant một cách an toàn.
- Phải có chính sách riêng cho unsolicited response: IdP được phép nào, ACS nào, audience nào, recipient nào, có cần channel binding/hint nào.
- **Không tự chọn tenant theo NameID/email/group** từ assertion chưa xác minh.
- Nếu không thể phân giải một cách xác định, **fail closed** và yêu cầu bắt đầu SP-initiated login.

SP-initiated thường dễ kiểm soát correlation hơn khi sản phẩm có nhiều tenant cùng issuer. Đây không phải lệnh cấm chung IdP-initiated SSO; đó là quyết định bảo mật phải được thiết kế.

## 8. Chọn registration khi nhận SAML Response

Spring Security dùng `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter` và `OpenSaml5AuthenticationProvider` cho phần chính của SAML login. Tài liệu Spring Security mô tả việc tìm `RelyingPartyRegistration` theo AuthnRequest liên quan, `registrationId` trong URL hoặc Issuer trong Response trong các tình huống nhất định.

Luồng kiểm tra **ở mức ý nghĩa**, không phải triển khai thay framework:

~~~text
1. Browser POST SAMLResponse đến ACS
2. Tìm candidate registration
   - state của AuthnRequest đã phát, hoặc
   - URL registrationId, hoặc
   - issuer lookup được giới hạn như hint theo policy
3. Lấy IdP verification credentials thuộc candidate
4. Kiểm chữ ký Response/Assertion, issuer
5. Kiểm Audience là SP entityId của registration
6. Kiểm Destination/Recipient là ACS được phép
7. Kiểm InResponseTo, request/session correlation nếu flow yêu cầu
8. Kiểm thời gian, NotBefore/NotOnOrAfter, Conditions, SubjectConfirmation
9. Chống replay, kiểm cấu trúc XML và EncryptedAssertion nếu có
10. Chỉ sau PASS: lấy principal/attributes đã được xác minh
11. Áp tenant + subject policy + role mapping của registration
12. Lấy user/permissions local, tạo Authentication có quyền phù hợp
~~~

**Không dùng `SAMLResponse/Issuer` chưa xác thực làm quyết định cuối cùng.** Issuer có thể xuất hiện ở phần XML chưa được ký hoặc có thể bị attacker tạo. Việc dùng nó để tìm **candidate** là hợp lý nếu sau đó chỉ certificate của candidate đó được sử dụng và mọi claim liên quan được xác minh.

### 8.1. Cross-partner confusion

Một lỗi đặc biệt nguy hiểm:

~~~text
POST /login/saml2/sso/beta
Response.Issuer = https://alpha-idp.example.test/issuer
Response.Audience = urn:portal:sp:alpha
Response.Signature = valid by Alpha IdP key
~~~

**Kết quả đúng:** **Beta không được xác thực người dùng này**. Response của Alpha có thể hợp lệ với Alpha, nhưng không dành cho Beta. Việc gộp tất cả IdP verification certificates và chỉ hỏi “bất kỳ khóa nào xác minh được?” sẽ làm mất isolation.

Kể cả khi Alpha và Beta cố ý dùng cùng SP entityId/ACS, vẫn phải có **trust mapping/issuer scope và tenant selection rõ ràng** để tránh tái sử dụng token không đúng ngữ cảnh.

## 9. Khóa SP và certificate IdP phải có purpose và scope

Trong một registration, có các credentials sau:

| Credential | Private key ở đâu? | Dùng để làm gì? | Quy tắc scope |
| --- | --- | --- | --- |
| **SP signing** | SP | Ký AuthnRequest/SLO message | Chỉ key được duyệt cho registration |
| **SP decryption** | SP | Giải mã EncryptedAssertion/EncryptedID gửi cho SP | Chỉ key ring đăng ký; có overlap rotation khi cần |
| **IdP verification** | IdP, SP chỉ có public cert | SP xác minh chữ ký Response/Assertion | Chỉ chứng thư IdP đã tin cho registration |
| **Metadata signer verification** | IdP/federation operator | SP kiểm chữ ký metadata (nếu policy yêu cầu) | Trust anchor độc lập trước khi nhập metadata |

**Không trao private key SP cho IdP.** IdP nhận public certificate SP để xác minh AuthnRequest hoặc mã hóa assertion. SP giữ private key trong secret store/HSM theo nguyên tắc quyền tối thiểu.

### 9.1. Vì sao tách khóa có ích?

- Nếu Alpha bị compromise, rủi ro không tự lan sang khóa Beta.
- Xoay signing certificate của Alpha không buộc Beta phải cập nhật.
- Nếu Beta dùng encrypted assertions và Alpha không dùng, có thể cấp riêng decryption key cho Beta.
- Monitoring/incident response có thể khoanh vùng theo đối tác.
- Có thể dùng issuer/certificate pinning khác nhau cho từng IdP.

**Chia sẻ khóa có thể là thiết kế hợp lệ** khi một SP logic chủ ý dùng cùng entityId/certificate với nhiều IdP. Nhưng cần ghi rõ ai cùng quyền sử dụng private key, khả năng một đối tác thay đổi cấu hình tác động đối tác khác và quy trình rotation chung.

### 9.2. Rotation theo từng đối tác

SP **signing key**:
1. Tạo keypair/cert mới cho Alpha.
2. Đưa **public signing cert mới** đến IdP Alpha qua quy trình tin cậy.
3. IdP Alpha bắt đầu tin cert mới; SP Alpha mới chuyển private key ký.
4. Kiểm AuthnRequest ký thực tế rồi loại key cũ theo lịch.

SP **decryption key**:
1. SP Alpha có **private key mới trước**.
2. IdP Alpha chuyển sang mã hóa bằng **public encryption certificate mới**.
3. SP giữ key cũ/mới trong khoảng overlap được duyệt.
4. Sau khi không còn ciphertext dùng cert cũ, ngừng key cũ.

IdP **verification cert**:
1. Alpha thông báo signer rollover qua metadata/quy trình đáng tin.
2. SP Alpha cập nhật **certificate xác minh của Alpha**.
3. Kiểm thử trong overlap, loại certificate cũ sau cutover.
4. Không mang cert Alpha vào trust policy Beta.

Metadata trust cũng có vòng đời riêng; `metadata-uri` trỏ file/URL chỉ nói **lấy ở đâu**, không tự chứng minh người ký metadata đúng. Nếu chính sách yêu cầu signed metadata, kiểm bằng **metadata signer trust anchor được cấp độc lập**. Spring Security document về metadata signature validation yêu cầu cung cấp verificationCredentials tương ứng.

## 10. Chính sách thuộc tính theo đối tác: không có một schema toàn cục

SAML Attributes có thể khác nhau giữa IdP:

- `employeeId` / `uid` / `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier`;
- `email` / `mail` / `EmailAddress`;
- `groups` / `memberOf` / `entitlements`;
- `department`, `costCenter`, `tenant`, `role`.

Một đối tác có thể phát group bằng tên người dùng đọc được, đối tác khác phát group bằng GUID. Một SAML Attribute cũng có thể chứa **nhiều giá trị**, nên `getFirstAttribute` chỉ phù hợp khi schema **bảo đảm đúng một giá trị**.

### 10.1. Thiết kế AttributePolicy

Mỗi registration gắn một policy riêng:

~~~yaml
saml-attribute-policies:
  alpha:
    subject:
      attribute: employeeId
      required: true
      exactly-one: true
    display-name:
      attribute: displayName
      required: false
    groups:
      attribute: groups
      mappings:
        engineers: ROLE_ALPHA_EDITOR
        auditors: ROLE_ALPHA_AUDITOR
    jit-provisioning: false

  beta:
    subject:
      attribute: uid
      required: true
      exactly-one: true
    display-name:
      attribute: fullName
      required: false
    groups:
      attribute: entitlements
      mappings:
        partner-viewer: ROLE_BETA_READER
    jit-provisioning: false
~~~

**Đây là schema cấu hình domain tự thiết kế cho bài học, không phải Spring Boot/Spring Security built-in properties.** Muốn áp dụng, cần viết và kiểm thử component đọc policy từ config/database. Không thêm nó vào `application.yml` rồi mặc nhiên mong Spring Security tự hiểu hay tự gán role.

**Quy tắc chọn policy:** chọn bằng `registrationId` **sau khi SAML Response đã được xác minh và gắn với registration**, không chọn policy theo attribute `tenant` do IdP tự đưa vào.

### 10.2. Subject ổn định và scoped identity

Email có thể đổi hoặc tái cấp, vì vậy **không nên dùng email mặc định để tự liên kết một người dùng giữa các IdP/tenant**. Nên sử dụng:

- Persistent NameID nếu hợp đồng IdP bảo đảm ổn định và NameID Format/NameQualifier/SPNameQualifier được xử lý đúng.
- Một subject ID được IdP xác minh cam kết không tái sử dụng, ví dụ `employeeId`, `uid` hoặc immutable directory object ID.
- Khóa nội bộ scoped theo tenant/registration/IdP issuer/subject hoặc một foreign-key identity record rõ ràng.

Ví dụ định danh cục bộ:

~~~text
(tenant-a, alpha, https://alpha-idp.example.test/issuer, employeeId=u-100)
(tenant-b, beta,  https://beta-idp.example.test/issuer,  uid=u-100)
~~~

Hai bản ghi có **cùng chuỗi `u-100`** nhưng không phải một danh tính local mặc định. Chỉ **account linking có xác minh và phê duyệt** mới được gắn vào cùng một tài khoản người dùng nếu sản phẩm cho phép.

### 10.3. Bắt buộc kiểm kiểu và cardinality

Với một subject attribute được dùng làm khóa:

- Nếu **thiếu**, từ chối JIT login/linking hoặc chuyển sang luồng xử lý đã được duyệt; không lấy `email` thay tự động.
- Nếu **nhiều giá trị** nhưng policy yêu cầu một, từ chối để tránh chọn “giá trị đầu tiên” tùy thứ tự.
- Nếu rỗng hoặc quá dài, không có định dạng hợp lệ, từ chối; kiểm tra encoding/normalization theo hợp đồng.
- Không chuyển `123` dạng number và `"123"` dạng string thành hai danh tính không nhất quán; schema và serialization phải được định nghĩa.
- Không cắt/viết thường/trim một subject identifier bất biến nếu IdP không có cam kết normalization.
- Nếu IdP đổi schema hoặc NameID Format, cần migration mapping có kiểm soát.

## 11. Ánh xạ group thành quyền: allowlist theo tenant

Một lỗi điển hình:

~~~java
// KHONG AN TOAN:
String claimedGroup = principal.getFirstAttribute("group");
authority = new SimpleGrantedAuthority("ROLE_" + claimedGroup);
~~~

Nếu IdP hoặc người quản trị group có thể tạo giá trị `ADMIN`, ứng dụng có thể vô tình cấp `ROLE_ADMIN` trong toàn hệ thống. Với nhiều đối tác, group `admin` của Beta **không phải** quyền admin của Alpha.

**Cách đúng về ý nghĩa:** một map **do ứng dụng/tenant owner phê duyệt** chuyển giá trị thuộc tính đã xác minh sang các authority giới hạn:

~~~text
Alpha:
  "engineers" -> ROLE_ALPHA_EDITOR
  "auditors"  -> ROLE_ALPHA_AUDITOR

Beta:
  "partner-viewer" -> ROLE_BETA_READER
  "partner-billing" -> ROLE_BETA_BILLING
~~~

Không biến bất kỳ group không biết thành quyền. Có thể để empty roles, yêu cầu local role từ database hoặc từ chối theo chính sách. Cần kiểm tra **quyền trên từng resource** bằng tenant membership và local authorization, không chỉ vì người dùng có `ROLE_USER` từ một SAML login hợp lệ.

### 11.1. Spring Security xử lý thuộc tính sau khi xác minh thế nào?

Sau khi `OpenSaml5AuthenticationProvider` xác minh Response và Assertion, Spring Security tạo `Saml2Authentication` chứa `Saml2AuthenticatedPrincipal`. Có thể đọc:

~~~java
Saml2AuthenticatedPrincipal principal =
    (Saml2AuthenticatedPrincipal) authentication.getPrincipal();

String registrationId =
    principal.getRelyingPartyRegistrationId();

Object employeeId = principal.getFirstAttribute("employeeId");
List<Object> groups = principal.getAttribute("groups");
~~~

Đây là **đoạn dùng sau khi authentication thành công**, cần import Spring Security và ép kiểu/giá trị theo policy. Kiểu generic cụ thể của `getAttribute` phụ thuộc dữ liệu và API; không giả định luôn nhận `List<String>`.

Spring Security có `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter` để tùy chỉnh cách biến Assertion thành Authentication. Tài liệu cũng có `ResponseAuthenticationConverter` để trích NameID/attributes. **Đừng tự bỏ các bước default validation** để đọc raw XML sớm hơn; mapping và authority enrichment phải diễn ra **sau khi** issuer, signature, audience, time/SubjectConfirmation đã đạt yêu cầu.

### 11.2. Domain-level mapping sau authentication

Một service của ứng dụng có thể nhận **đầu vào đã được chuẩn hóa từ Authentication của Spring Security**, sau đó:

1. Lấy `registrationId` đã được framework gắn với principal.
2. Từ trusted config, map registration -> tenantId/attribute policy.
3. Chọn subject attribute bắt buộc, yêu cầu đúng cardinality.
4. Tìm external identity link theo scope tenant+provider+subject.
5. Ánh xạ groups qua allowlist của policy.
6. Lấy local entitlements từ database/authorization service và tính effective authorities.
7. Đặt tenant context dựa trên **thực thể local đã xác minh**, không tin tenant header/query hoặc claim chưa được quản trị.
8. Cấp session chỉ với quyền hạn tối thiểu; không tự đăng ký tenant membership chỉ vì SAML đăng nhập thành công.

**Đặc biệt:** nếu IDP được phép cung cấp quyền nghiệp vụ, hợp đồng phải quy định chính xác **attribute name, value, issuer authority, thời điểm cập nhật, thu hồi**. Nếu IdP chỉ chứng minh identity, quyền nghiệp vụ phải nằm hoàn toàn phía ứng dụng.

## 12. Mô hình dữ liệu đề xuất cho nhiều đối tác

Ví dụ PostgreSQL rút gọn:

~~~sql
CREATE TABLE saml_partner (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    registration_id TEXT NOT NULL UNIQUE,
    sp_entity_id TEXT NOT NULL,
    acs_url TEXT NOT NULL,
    idp_entity_id TEXT NOT NULL,
    idp_metadata_source TEXT NOT NULL,
    sp_signing_key_ref TEXT,
    sp_decryption_key_ref TEXT,
    idp_verification_trust_ref TEXT NOT NULL,
    attribute_policy_ref TEXT NOT NULL,
    config_version BIGINT NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE external_saml_identity (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    partner_id BIGINT NOT NULL REFERENCES saml_partner(id),
    subject_namespace TEXT NOT NULL,
    subject_value TEXT NOT NULL,
    local_user_id UUID NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, partner_id,
            subject_namespace, subject_value)
);
~~~

Đây là **mô hình học tập**, không phải schema hoàn chỉnh cho sản phẩm nhiều tenant. `subject_namespace` có thể mô tả NameID Format/qualifier hoặc attribute type đã thỏa thuận; với issuer cần có mapping đáng tin trong `saml_partner`. Không dùng một `UNIQUE(subject_value)` toàn hệ thống; nó sẽ gộp `u-100` của hai đối tác.

### 12.1. Vì sao key refs không phải PEM?

`sp_signing_key_ref` và `sp_decryption_key_ref` nên trỏ đến secret manager/keystore alias hoặc một registry quản trị có quyền kiểm soát, thay vì lưu **private key plaintext** trong bảng cấu hình tenant. Khi nạp registration:

- Chỉ service có quyền với registration đó mới resolve key reference.
- Không lấy keyRef từ SAML Response/RelayState/Attribute do browser cung cấp.
- Có version/rotation rõ, audit người đổi key reference.
- IdP verification trust phải gắn với đúng đối tác và nguồn metadata đã xác minh.

Cần nhớ **certificate public của IdP** không phải private key, nhưng nguồn của nó vẫn là **trust configuration nhạy cảm về tính toàn vẹn**: attacker thay được cert có thể khiến SP tin IdP giả.

### 12.2. Tenant-aware database access

Bảo vệ ở tầng ứng dụng chưa đủ nếu database query không lọc tenant. Sau khi xác thực, mọi truy vấn local user, nhóm, resource phải gắn tenant context **đã được xác minh**. Nên cân nhắc:

- Unique constraints scoped tenant cho external identities.
- Foreign keys bảo vệ quan hệ tenant/user khi ứng dụng đa tenant thật.
- RLS hoặc repository predicates theo tenant.
- Không cho người dùng thay tenantId từ HTTP header để truy cập data của tenant khác.
- Audit account linking, JIT provisioning, deprovisioning và cross-tenant role changes.

SAML giải quyết **đăng nhập**, không tự trở thành chính sách phân quyền dữ liệu nghiệp vụ.

## 13. Java 17 độc lập: chứng minh isolation giữa hai đối tác

Ví dụ **chạy với JDK 17+**, không cần Spring Security hay IdP thật. Nó mô hình hóa:

- Mỗi partner có `registrationId`, tenant, SP entityId, ACS, IdP issuer, key aliases và **attribute policy** riêng.
- Một đối tượng `VerifiedAssertion` giả lập **kết quả validation thành công của thư viện SAML**, không phải dữ liệu XML chưa kiểm chứng.
- Cùng subject `u-100` của Alpha và Beta tạo **hai scoped local identity keys** khác nhau.
- Group `ROLE_SUPER_ADMIN` do Alpha gửi nhưng không nằm trong policy thì **không được cấp quyền**.
- Sai issuer, audience, recipient/ACS, thiếu subject, dùng schema attributes của đối tác khác hoặc chưa được SAML verifier xác thực đều bị từ chối.

**Cảnh báo quan trọng:** biến boolean `verifiedBySamlLibrary` chỉ là **mô phỏng tin cậy trong unit test**; khi tích hợp thật, không đọc boolean này từ HTTP request, JSON, header hoặc SAML Attribute. Spring Security/OpenSAML phải làm **cryptographic/protocol validation trước**. Chương trình cũng **không ký/giải mã SAML XML, không quản lý private keys, không tạo HTTP endpoints**.

Tệp `PartnerIsolationDemo.java`:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public class PartnerIsolationDemo {
    record Partner(String registrationId, String tenantId,
                   String spEntityId, String acs,
                   String idpEntityId, String subjectAttribute,
                   String groupsAttribute,
                   Map<String, String> groupToRole,
                   String signingKeyAlias, String decryptionKeyAlias,
                   String idpCertificateFingerprint) {}

    // This is a MOCK of an output from a trusted SAML verifier, not raw XML.
    record VerifiedAssertion(String registrationId, String issuer,
                             String audience, String recipient,
                             boolean verifiedBySamlLibrary,
                             Map<String, List<String>> attributes) {}

    record LocalIdentity(String key, String tenantId, Set<String> roles) {}

    static Optional<LocalIdentity> resolve(
            Map<String, Partner> registrations, VerifiedAssertion assertion) {
        // In production registration resolution + every SAML validation
        // MUST be done by Spring Security/OpenSAML.
        if (!assertion.verifiedBySamlLibrary()) return Optional.empty();
        Partner partner = registrations.get(assertion.registrationId());
        if (partner == null
                || !partner.idpEntityId().equals(assertion.issuer())
                || !partner.spEntityId().equals(assertion.audience())
                || !partner.acs().equals(assertion.recipient())) {
            return Optional.empty();
        }
        List<String> subjects = assertion.attributes()
            .getOrDefault(partner.subjectAttribute(), List.of());
        if (subjects.size() != 1 || subjects.get(0).isBlank()) {
            return Optional.empty();
        }
        String stableId = subjects.get(0);
        Set<String> roles = new LinkedHashSet<>();
        for (String group : assertion.attributes().getOrDefault(
                partner.groupsAttribute(), List.of())) {
            String mapped = partner.groupToRole().get(group);
            if (mapped != null) roles.add(mapped);
        }
        String key = partner.tenantId() + "|" + partner.registrationId()
            + "|" + stableId;
        return Optional.of(new LocalIdentity(
            key, partner.tenantId(), Set.copyOf(roles)));
    }

    public static void main(String[] args) {
        Partner alpha = new Partner(
            "alpha", "tenant-a", "urn:portal:sp:alpha",
            "https://portal.example.test/login/saml2/sso/alpha",
            "https://alpha-idp.example.test/issuer",
            "employeeId", "groups",
            Map.of("engineers", "ROLE_ALPHA_EDITOR"),
            "alpha-sp-sign", "alpha-sp-decrypt", "cert-alpha");
        Partner beta = new Partner(
            "beta", "tenant-b", "urn:portal:sp:beta",
            "https://portal.example.test/login/saml2/sso/beta",
            "https://beta-idp.example.test/issuer",
            "uid", "entitlements",
            Map.of("partner-viewer", "ROLE_BETA_READER"),
            "beta-sp-sign", "beta-sp-decrypt", "cert-beta");
        Map<String, Partner> registrations =
            Map.of("alpha", alpha, "beta", beta);

        VerifiedAssertion a = new VerifiedAssertion(
            "alpha", alpha.idpEntityId(), alpha.spEntityId(), alpha.acs(),
            true, Map.of(
                "employeeId", List.of("u-100"),
                "groups", List.of("engineers", "ROLE_SUPER_ADMIN")));
        VerifiedAssertion b = new VerifiedAssertion(
            "beta", beta.idpEntityId(), beta.spEntityId(), beta.acs(),
            true, Map.of(
                "uid", List.of("u-100"),
                "entitlements", List.of("partner-viewer")));

        Optional<LocalIdentity> aId = resolve(registrations, a);
        Optional<LocalIdentity> bId = resolve(registrations, b);
        System.out.println("alphaAccepted=" + aId.isPresent());
        System.out.println("betaAccepted=" + bId.isPresent());
        System.out.println("sameSubjectSeparated=" +
            (aId.isPresent() && bId.isPresent()
                && !aId.get().key().equals(bId.get().key())));
        System.out.println("unmappedRoleRejected=" +
            (aId.isPresent()
                && !aId.get().roles().contains("ROLE_SUPER_ADMIN")));
        System.out.println("wrongIssuer=" + resolve(registrations,
            new VerifiedAssertion("alpha", beta.idpEntityId(),
                alpha.spEntityId(), alpha.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("wrongAudience=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                beta.spEntityId(), alpha.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("wrongAcs=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                alpha.spEntityId(), beta.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("missingSubject=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                alpha.spEntityId(), alpha.acs(), true,
                Map.of("groups", List.of("engineers")))).isPresent());
        System.out.println("wrongAttributePolicy=" + resolve(registrations,
            new VerifiedAssertion("beta", beta.idpEntityId(),
                beta.spEntityId(), beta.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("unverifiedResponse=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                alpha.spEntityId(), alpha.acs(), false, a.attributes()))
            .isPresent());
    }
}
~~~

Biên dịch/chạy với JDK 17:

~~~bash
javac --release 17 PartnerIsolationDemo.java
java PartnerIsolationDemo
~~~

**Stdout chính xác:**

~~~text
alphaAccepted=true
betaAccepted=true
sameSubjectSeparated=true
unmappedRoleRejected=true
wrongIssuer=false
wrongAudience=false
wrongAcs=false
missingSubject=false
wrongAttributePolicy=false
unverifiedResponse=false
~~~

Đọc kết quả:

- **alphaAccepted/betaAccepted=true:** cả hai partner policy cho phép subject đúng của họ.
- **sameSubjectSeparated=true:** cùng `u-100` ở hai tenant/registration không bị nối chung.
- **unmappedRoleRejected=true:** giá trị group trông giống quyền admin nhưng **không có mapping**, nên không tạo authority.
- **wrongIssuer/wrongAudience/wrongAcs=false:** một mảnh assertion của đối tác khác không thể dùng sai nơi phát/nơi nhận.
- **missingSubject=false:** chính sách bắt buộc subject thì thiếu subject phải từ chối.
- **wrongAttributePolicy=false:** attributes của Alpha không thỏa schema của Beta, dù hai nơi đều phát user `u-100`.
- **unverifiedResponse=false:** chưa được SAML verifier xác minh thì không dùng assertion cho business identity.

**Tại production**, nhiều điều kiện issuer/audience/recipient được **Spring Security/OpenSAML** xử lý trước. Hàm `resolve` ở ví dụ chỉ minh họa guard của lớp application sau validation, không phải thay thế validator và không phải API để tiếp nhận SAML Response từ trình duyệt.

## 14. Luồng hoàn chỉnh: từ tenant selection đến local user

Một kiến trúc rõ ràng có thể tổ chức thành các bước:

~~~text
HTTP request từ người dùng
   |
   v
Tenant selection (domain/path/login picker)
   |
   v
Chọn registrationId thuộc allowlist
   |
   v
Spring Security tạo AuthnRequest + lưu correlation
   |
   v
IdP tương ứng xác thực, trả SAMLResponse
   |
   v
Saml2AuthenticationTokenConverter tìm registration
   |
   v
OpenSaml5AuthenticationProvider xác minh
   - đúng IdP signing cert
   - issuer, audience, destination/recipient
   - InResponseTo, thời gian, subject, signature
   - decrypt bằng SP decryption credentials tương ứng nếu có
   |
   v
Saml2Authentication / Saml2AuthenticatedPrincipal
   |
   v
PartnerAttributePolicyService(registrationId)
   - xác định subject ổn định
   - verify cardinality/format
   - map group qua allowlist
   |
   v
LocalIdentityService
   - external identity scoped tenant + partner
   - account linking/JIT policy
   - local roles + resource permissions
   |
   v
Session/Authentication context mang tenant đã xác minh
   |
   v
Business API kiểm tenant ownership và role
~~~

**Điểm chuyển trust:** trước bước SAML validator, URL/RelayState/SAML XML chỉ là input chưa tin cậy. Sau validator, các claims đã được xác minh trong đúng registration mới có thể dùng cho mapping, nhưng **quyền nghiệp vụ** vẫn phụ thuộc local policy.

### 14.1. Tách kỹ thuật và nghiệp vụ

Một module SAML nên tập trung vào:

- RelyingPartyRegistration, metadata, keys, endpoints.
- AuthnRequest/Response, XMLDSig, XML Encryption.
- Issuer/audience/recipient/session correlation và tạo authenticated principal.

Module tenant/identity nghiệp vụ:

- Mỗi registration được gắn tenant nào.
- Subject attribute nào được phép định danh user.
- Nên cấp JIT provisioning hay không.
- Cách gắn external identity vào local user.
- Role/group mapping, deprovisioning và authorization.
- Hợp đồng truy cập dữ liệu theo tenant.

Tách hai lớp tránh lỗi “tôi thấy group ADMIN trong SAML nên cấp quyền ADMIN ngay”. Một SAML login được xác thực **không đồng nghĩa được cấp quyền quản trị của mọi tenant**.

## 15. Thiết kế tenant selection khi có domain/path chung

Nếu portal có các URL:

~~~text
https://portal.example.test/alpha/login
https://portal.example.test/beta/login
~~~

hoặc subdomain:

~~~text
https://alpha.portal.example.test/login
https://beta.portal.example.test/login
~~~

ứng dụng có thể dùng domain/path đã được quản trị để **đề xuất** registration. Tuy nhiên:

- Host header/forwarded headers chỉ được tin từ reverse proxy đã kiểm soát.
- Registration phải là **một giá trị thuộc allowlist**, không tạo động từ path tùy ý kiểu `new RelyingPartyRegistration(userInput)`.
- Tenant selection phải gắn với auth request state/cookie; callback không được chọn một tenant khác chỉ bằng cách thay URL.
- Khi phát lại Response đã ký cho Alpha vào Beta endpoint, issuer/audience/recipient/flow checks phải từ chối.
- Nếu user có quyền ở nhiều tenant, việc đổi tenant sau login phải dựa trên **local membership đã xác minh** và chính sách switch-tenant; không lấy tenant từ group hoặc query string tùy ý.

**Không phụ thuộc một mình vào referrer/header tùy ý** để xác định tenant khi nhận SAML Response từ IdP.

## 16. Nhiều IdP cùng tên hiển thị hoặc metadata chung

Có các trường hợp:

1. **Hai IdP khác nhau cùng label** `Corporate SSO`.
2. **Một IdP cung cấp nhiều tenants** và có issuer dùng chung.
3. **Federation aggregator** cung cấp nhiều `IDPSSODescriptor` trong một metadata feed.
4. **IdP đổi entityId** khi migration từ vùng cũ sang vùng mới.
5. **Một đối tác có nhiều IdP** theo vùng địa lý hoặc phương thức xác thực.

Các trường hợp này không nên giải quyết bằng display name:

- `registrationId` phải duy nhất và bền vững để quản trị cấu hình.
- `IdP entityId` và verification key phải ràng buộc đúng nguồn thực thể.
- Mỗi onboarding có owner, môi trường, metadata source/trust và configuration version.
- Nếu metadata tổng hợp chứa nhiều IdP, chỉ chọn **entity được phép** trong aggregate đã được xác minh.
- Nếu một IdP thực sự phục vụ nhiều tenants với cùng issuer, thiết kế **SP entityId/ACS hoặc request correlation riêng** khi có thể, hoặc cơ chế tenant selection tin cậy.
- Display name chỉ phục vụ UI; không dùng nó làm identity/trust key.

## 17. Account linking, JIT provisioning và vòng đời danh tính

### 17.1. Không tự liên kết tài khoản bằng email

Ví dụ:

~~~text
Alpha phát email=person@example.test, employeeId=a-123
Beta  phát email=person@example.test, uid=b-989
~~~

Hai IdP cùng phát email **không chứng minh đó là cùng một external identity**, cũng không chứng minh người ấy được phép truy cập cả hai tenant. Email có thể được chuyển nhượng, tái sử dụng hoặc thay đổi.

Khi có nhu cầu liên kết tài khoản:

1. User/administrator đi qua flow linking được phê duyệt.
2. Xác thực cả hai nguồn danh tính hoặc có bằng chứng sở hữu được chấp nhận.
3. Ghi nhận issuer/provider/subject scope, timestamp và owner.
4. Có cơ chế review/unlink và audit.
5. Không sửa một record từ tenant A sang tenant B chỉ vì email trùng.

### 17.2. JIT provisioning phải bị giới hạn

Nếu policy cho phép tạo user tự động sau SAML login, cần kiểm tra:

- Registration/IdP có được phép JIT không?
- Subject bắt buộc ổn định, chưa tồn tại conflict?
- Tenant local đã active, được phép có người dùng mới?
- User tạo mặc định ở trạng thái/quyền tối thiểu nào?
- Groups được map bằng allowlist của tenant, không có dynamic ADMIN.
- Deprovisioning: tài khoản disabled bên IdP, user rời nhóm, local account bị khóa thì xử lý thế nào?

**JIT không nên tự tạo quyền truy cập vào mọi tài nguyên tenant**. Mặc định nên tạo identity/profile và yêu cầu business authorization riêng nếu không có hợp đồng cấp quyền cụ thể.

### 17.3. Thay đổi attribute schema

Khi IdP Alpha chuyển từ `employeeId` sang `objectGUID`, không thay thẳng key mapping rồi để user cũ bị tạo nhân đôi. Cần migration:

1. IdP xác nhận tính ổn định/unique của attribute mới.
2. Tạo mapping cũ → mới có bằng chứng/tài liệu.
3. Kiểm thử trên sample accounts, xử lý collision.
4. Phiên bản hóa `attribute_policy_ref` và ngày cutover.
5. Có rollback và audit.

## 18. Kiểm thử bảo mật theo đối tác

| Test case | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Alpha login chuẩn | Alpha issuer/cert, Audience Alpha, ACS Alpha | PASS nếu mọi validation và local policy đúng |
| Beta login chuẩn | Beta issuer/cert, Audience Beta, ACS Beta | PASS theo policy Beta |
| Alpha Response gửi tới Beta ACS | URL Beta, Response Issuer/Audience Alpha | FAIL |
| Beta Response ký bằng key Alpha | Signature không thuộc IdP Beta trust | FAIL |
| IdP Alpha tự công bố key mới trong Response | KeyInfo chứa certificate lạ | Không tự trust |
| Sai Audience | Response ký đúng nhưng Audience cho SP khác | FAIL |
| Sai Recipient | SubjectConfirmationData Recipient khác ACS | FAIL |
| Sai Destination | Response tới URL không trùng policy | FAIL |
| InResponseTo sai | Response không khớp AuthnRequest đang chờ | FAIL trong SP-initiated flow |
| Response replay | Assertion/Response đã dùng lại | FAIL |
| Clock skew/expiry | NotBefore/NotOnOrAfter ngoài policy | FAIL |
| EncryptedAssertion key Alpha ở Beta | Không có private key hợp lệ theo Beta | FAIL |
| Multi-IdP cùng issuer | Chỉ issuer không đủ tìm tenant | FAIL nếu không có correlation bổ sung |
| Missing subject | Thiếu `employeeId` của Alpha | FAIL theo required policy |
| Multiple subject values | Alpha có hai employeeId | FAIL khi policy exactly-one |
| Attribute schema swapped | Beta nhận attributes Alpha | Không map identity Beta |
| Same ID across tenants | Both subject = u-100 | Hai scoped identities khác nhau |
| Same email across IdPs | Email trùng, subjects khác | Không tự link |
| Group admin tùy ý | Alpha nhận `ROLE_SUPER_ADMIN` trong groups | Không tạo authority nếu không allowlisted |
| Beta group đòi Alpha role | `entitlements=engineers` | Không dùng Alpha mapping |
| Tenant header bị sửa | User authenticated Alpha gửi `X-Tenant: beta` | Không chuyển tenant nếu local membership không cho phép |
| Proxy host giả | Attacker tự đưa forwarded host | Không đổi ACS/entityId theo host chưa tin |
| IdP metadata chưa verify | Metadata signer chưa được tin | Không cập nhật IdP trust theo chính sách |
| Cert rotation Alpha | Alpha có cert cũ/mới trong overlap | Alpha pass; Beta không thay |
| Cert revoked | Alpha cert cũ đã loại khỏi trust | Từ chối assertion ký bằng key cũ |
| Tenant deactivated | Registration disabled | Không bắt đầu hoặc chấp nhận login |
| JIT disabled | Valid SAML user chưa có local link | Không tự tạo user có quyền |
| Multi-tab SP-initiated | AuthnRequest A/B state khác | Callback gắn đúng flow |
| Unsolicited login disabled | Response không InResponseTo | FAIL |
| Aggregate metadata | Chỉ entity trong trusted signed scope | Chấp nhận những entity được duyệt |
| Logging | Assertion chứa email/groups | Không ghi full SAML XML/PII vào production log |

**Đặt tên test theo registration và vector attack**, không chỉ “login fail”. Khi chạy integration test, phải kiểm tra cả IdP metadata/certificate và hiệu ứng local: không tạo sai tenant session, không tạo user link không được phép và không cấp quyền ở database.

## 19. Troubleshooting theo lớp lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Alpha login chuyển tới IdP Beta | Sai registrationId/router/default picker | Kiểm `/saml2/authenticate/{id}`, repository và chọn tenant |
| ACS Beta nhận Response Alpha | Portal IdP đăng ký ACS sai | Kiểm metadata SP và cấu hình IdP |
| `Invalid issuer` | Dùng IdP config của đối tác khác | Đối chiếu IdP entityId trong registration |
| `Invalid audience` | SP Entity ID khác hợp đồng | Đối chiếu Audience và EntityDescriptor SP |
| `Invalid destination` | Proxy/ACS URL sai scheme/host/path | Kiểm public URL và trusted forwarded headers |
| Signature invalid | Cert IdP stale/sai đối tác | Đối chiếu fingerprint/trust theo registration |
| EncryptedAssertion decrypt fail | SP key ring sai hoặc IdP encrypt bằng cert khác | Kiểm SP decryption cert và private key |
| InResponseTo mismatch | Request state/cookie/cluster không khớp | Kiểm AuthnRequest repository, session và binding |
| Login thành công nhưng không tìm user | Subject policy dùng attribute không tồn tại | Kiểm schema IdP và required attributes |
| User Alpha xuất hiện ở Beta | Identity key chỉ dùng email/subject không scope | Sửa external identity schema và linking |
| Beta nhận ROLE_ALPHA_ADMIN | Group mapping được dùng global | Tách per-registration policy, role allowlist |
| JIT tạo quá nhiều user | IdP đổi NameID/attribute transient | Kiểm persistent identity contract và migration |
| Chỉ lỗi production | Host/proxy/cert/Entity ID khác UAT | So actual metadata/runtime config theo environment |
| Callback không map được registration | ACS chung, issuer trùng/không có request state | Thiết kế trusted resolver/correlation |
| Metadata mới khiến tất cả IdPs lỗi | Shared trust bundle/key không scope | Phân chia trust, version, rollback per partner |
| Lỗi sau rotation | IdP chưa import cert, key cached trong JVM | Kiểm cutover/reload và overlap |
| SAML success nhưng API 403 | Business authorization không có tenant membership | Kiểm local roles/resource permissions, không nới SAML validation |

### 19.1. Log tối thiểu, đủ điều tra

Nên ghi theo chính sách bảo mật:

~~~text
timestamp
registrationId
tenantId (từ config đã tin)
spEntityId
idpEntityId (sau validation)
public certificate fingerprint
signature/issuer/audience/recipient validation result
attribute policy version
local identity lookup result
correlation ID, error category
~~~

**Không ghi private keys, full XML assertion, NameID/attributes nhạy cảm, SAMLResponse Base64 hoặc session cookies** vào log production. Một certificate fingerprint là dữ liệu công khai hữu ích nhưng không nên tự biến log thành nơi duy nhất quyết định trust.

## 20. Checklist thiết kế và vận hành

- [ ] Đã lập inventory tất cả đối tác, IdP entityId, tenant, registrationId, SP entityId và ACS.
- [ ] Mỗi registrationId là duy nhất và có owner/config version.
- [ ] Có quyết định rõ **entityId/ACS/private keys nào tách và cái nào chủ ý chia sẻ**; không chia sẻ ngầm.
- [ ] IdP verification keys được giới hạn theo registration, không gom thành trust list toàn cục không scope.
- [ ] SP signing/decryption private keys được quản lý riêng theo đối tác khi chính sách yêu cầu.
- [ ] Đã xác minh SP metadata Alpha/Beta công bố đúng Entity ID, ACS và public certificates.
- [ ] Default ACS, custom `loginProcessingUrl`, reverse proxy và IdP callback URL đã khớp.
- [ ] Registration resolver xử lý SP-initiated flow, InResponseTo, IdP-initiated policy và shared issuer ambiguity an toàn.
- [ ] Issuer từ response chỉ là candidate hint trước validation; trusted IdP certificate được áp đúng.
- [ ] Audience, Recipient, Destination, time, SubjectConfirmation và replay checks không bị bỏ qua.
- [ ] EncryptedAssertion chỉ giải mã bằng SP decryption credentials của đúng registration.
- [ ] Metadata nguồn IdP được quản lý trust, expiry, rotation và signer verification nếu policy yêu cầu.
- [ ] Attribute policies gắn theo registration, không chọn theo claim tenant/email chưa xác minh.
- [ ] Subject là định danh ổn định, scoped theo tenant/provider; email không tự liên kết identity.
- [ ] Attribute bắt buộc có kiểm kiểu, cardinality, normalization và fallback policy cụ thể.
- [ ] Group/role mapping chỉ từ allowlist của đối tác; không có dynamic `ROLE_` + raw group.
- [ ] Business API vẫn kiểm tenant membership/local authorization độc lập với SAML success.
- [ ] JIT provisioning, account linking, deprovisioning và schema migration có audit và approval.
- [ ] Cert/key rotation có overlap đúng mục đích và kế hoạch riêng cho từng đối tác.
- [ ] Test cross-partner confusion, same subject/email, wrong ACS/key, missing attrs, unsolicited response, multi-node session.
- [ ] Có monitoring theo registration và secret key version, không log dữ liệu nhạy cảm.

## 21. Câu hỏi tự kiểm tra

**1. Mỗi IdP bắt buộc phải có SP Entity ID riêng không?**

Không bắt buộc về mặt Spring Security/SAML: nhiều registration có thể chủ đích chia sẻ entityId, ACS hoặc credentials. Nhưng khi muốn tách trust/tenant, dùng thông tin riêng giúp giảm nhầm lẫn và rotation độc lập. Việc chia sẻ cần có policy/correlation rõ ràng.

**2. registrationId = alpha có phải SAML Issuer không?**

Không. `registrationId` là khóa local Spring Security; SP và IdP entityId là định danh logic được trao đổi trong SAML/metadata.

**3. URL ACS chứa beta có đủ chứng minh Response từ Beta không?**

Không. Browser có thể POST bất kỳ dữ liệu tới path. Cần xác minh chữ ký IdP Beta, issuer, audience, recipient/destination, correlation và conditions.

**4. Nếu một Response Alpha có chữ ký hợp lệ, có được dùng để đăng nhập Beta không?**

Không. Chữ ký chỉ hợp lệ với IdP Alpha; response còn phải khớp SP entityId, ACS và trust policy của registration/tenant được yêu cầu. Không dùng “key nào cũng được” toàn cục.

**5. Một IdP issuer dùng cho nhiều tenant, chỉ dựa vào Issuer có đủ xác định tenant?**

Không. Cần SP-initiated request state hoặc một cơ chế routing/correlation đáng tin cậy. Nếu vẫn không phân biệt được, nên từ chối.

**6. Có nên map group từ SAML thành `ROLE_` + groupName?**

Không. Chỉ map group/entitlement đã xác minh qua **allowlist theo đối tác**; không cho giá trị `ADMIN` của Beta tạo quyền ADMIN ở Alpha.

**7. Người dùng Alpha và Beta cùng có subject `u-100` thì có phải cùng tài khoản không?**

Không mặc định. Danh tính cần scope theo tenant, registration, issuer, stable subject. Nếu muốn liên kết, phải có flow linking được xác minh.

**8. Tại sao email không nên là khóa liên kết tài khoản duy nhất?**

Email có thể đổi/tái sử dụng và cùng xuất hiện ở các IdP khác nhau. Nó không chứng minh cùng nguồn cấp danh tính hoặc quyền truy cập tenant.

**9. Nếu đổi private key SP signing của Alpha, Beta có cần đổi không?**

Không nếu hai registration sử dụng khóa riêng. Nếu cố ý chia sẻ khóa, rotation có thể ảnh hưởng cả hai và phải phối hợp với tất cả IdP liên quan.

**10. Trong Spring Security, đọc attributes ở đâu?**

Sau xác thực SAML thành công, qua `Saml2Authentication` / `Saml2AuthenticatedPrincipal` hoặc response authentication converter được hỗ trợ. Không dùng raw XML chưa xác minh cho identity/role mapping.

**11. Vì sao custom ACS phải đi cùng metadata SP và filter URL?**

IdP gửi Response theo ACS đã đăng ký, còn Spring filter phải nhận đúng path. URL không khớp có thể gây 404 hoặc Destination/Recipient validation fail.

**12. JIT provisioning với subject mới đã xác minh có tự động cấp quyền tenant không?**

Không. Phải theo chính sách onboarding, membership, allowlist roles và local authorization. Identity SAML hợp lệ chưa phải business permission.

## 22. Tài liệu kỹ thuật để đối chiếu

- Spring Security, **SAML 2.0 Login Overview**, `RelyingPartyRegistration`, nhiều asserting parties, URI patterns, duplicated relying party configurations và default ACS: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**, lookup registration, `Saml2AuthenticationTokenConverter`, `OpenSaml5AuthenticationProvider`, response authentication converter, attributes/authorities: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**, routing/signing AuthnRequest theo `RelyingPartyRegistration`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **SAML 2.0 Metadata**, SP metadata per registration và cách xác minh signed IdP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security Javadoc, **RelyingPartyRegistration**, cặp SP/IdP và `registrationId`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- Spring Security, **Saml2AuthenticatedPrincipal**, attribute access và registration association: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- OASIS, **SAML 2.0 Core**, Issuer, AudienceRestriction, SubjectConfirmationData/Recipient và NameID: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS, **SAML 2.0 Metadata**, `EntityDescriptor`, `AssertionConsumerService`, `KeyDescriptor` và IdPSSODescriptor: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS, **SAML 2.0 Profiles**, Web Browser SSO và unsolicited Response: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OWASP, **SAML Security Cheat Sheet**, chống XML Signature Wrapping, signature/trust và recipient validation: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Ghi nhớ:** một ứng dụng có nhiều IdP/tenant nên coi **mỗi `RelyingPartyRegistration` là một trust boundary**. `registrationId` chọn cặp cấu hình; **SP entityId và ACS xác định đối tượng nhận**; **IdP issuer và verification certificate xác định bên phát**; **SP signing/decryption credentials phục vụ riêng cặp kết nối**; **attribute policy quyết định cách chuyển claims đã xác minh thành scoped local identity và quyền**. Mọi quyết định tài khoản/tenant phải diễn ra **sau SAML validation** và phải có **cross-tenant authorization riêng**.