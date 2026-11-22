# Đối chiếu metadata, entityId và endpoint khi thay thư viện SAML

> **Module:** Spring Security – federation. **Nhóm kiến thức:** Chuyển đổi và nâng cấp. **Bối cảnh:** Di chuyển một ứng dụng **SAML 2.0 Service Provider (SP/Relying Party)** từ thư viện cũ — ví dụ **Spring Security SAML Extension 1.x** — sang **Spring Security SAML2 Service Provider** mà không làm sai hợp đồng với Identity Provider (IdP/Asserting Party). Trọng tâm là **metadata, SP/IdP entityID, ACS, SSO, SLO, URL công khai, binding, chứng thư ký/mã hóa, validation, migration, rollback và regression tests**. Ví dụ dùng Java 17, Spring Boot 3.5.x, Spring Security 6.5.x; tất cả URL, tên công ty và định danh là dữ liệu mô phỏng trong môi trường kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **SP entityID**, **IdP entityID**, URL phát metadata, `AssertionConsumerService` (ACS), `SingleLogoutService` (SLO) và `SingleSignOnService` (SSO), và vì sao chúng không thay thế nhau.
2. So **metadata của ứng dụng cũ**, **metadata bản mới** và **cấu hình IdP thực tế**, lập change ledger cho từng khác biệt.
3. Nhận diện các URL mặc định của Spring SAML Extension 1.x (`/saml/SSO`, `/saml/metadata`, `/saml/SingleLogout`) và Spring Security SAML2 6.5 (`/login/saml2/sso/{registrationId}`, `/saml2/metadata/{registrationId}`, `/logout/saml2/slo`).
4. Biết khi nào cần **giữ entityID/ACS/SLO cũ** để IdP không phải thay registration; khi nào cần chuyển sang URL mới bằng một change request.
5. Đối chiếu binding, `isDefault`/`index` của ACS, NameIDFormat, yêu cầu ký `AuthnRequest`, certificate signing/decryption và trust metadata.
6. Ánh xạ các beans/filters cũ sang `saml2Login`, `saml2Logout`, `saml2Metadata`, `RelyingPartyRegistration` và repository/resolver mới.
7. Thiết kế validation tests cho `Issuer`, `Audience`, `Destination`, `Recipient`, `InResponseTo`, `RelayState`, `SubjectConfirmation`, time/replay, signature và encryption.
8. Chẩn đoán lỗi reverse proxy HTTPS, context path, forwarded headers, cookies, session affinity và nhiều IdP trong quá trình chuyển đổi.
9. Chạy Java 17 **SamlContractDiffDemo** để phát hiện entityID/ACS/SLO/issuer/cert drift, với stdout được xác định chính xác.
10. Lập kế hoạch migration sandbox → canary → cutover → rollback, bảo toàn bảo mật và không tự phát biểu “migrated successfully” khi chỉ có HTTP 302.

**Yêu cầu đầu vào:** HTTP, TLS, SAML 2.0 Web Browser SSO, SP/IdP, AuthnRequest/Response/Assertion, XML Signature, SAML metadata, Spring Security FilterChain, Java 17 và Servlet session.

## 2. Vấn đề chính: nâng thư viện không đồng nghĩa đổi danh tính liên kết

Giả sử hiện tại IdP nhận metadata SP cũ:

~~~text
Legacy Spring SAML Extension 1.x:
  SP entityID  = urn:portal:production:sp
  SP ACS       = https://portal.example.org/saml/SSO
  SP SLO       = https://portal.example.org/saml/SingleLogout
  IdP entityID = https://idp.example.org/saml
  IdP SSO      = https://idp.example.org/sso
  SP signer    = alias sp-signing-2026

New Spring Security SAML2, nếu để default:
  SP entityID  = https://portal.example.org/saml2/service-provider-metadata/corporate
  SP ACS       = https://portal.example.org/login/saml2/sso/corporate
  SP SLO       = https://portal.example.org/logout/saml2/slo
  IdP entityID = https://idp.example.org/saml
  IdP SSO      = https://idp.example.org/sso
  SP signer    = phụ thuộc new registration

IdP vẫn registered:
  Audience     = urn:portal:production:sp
  ACS          = https://portal.example.org/saml/SSO
  SLO          = https://portal.example.org/saml/SingleLogout

=> Chỉ đổi dependency + thêm saml2Login() sẽ không đảm bảo login.
~~~

**Ba chiến lược:**

- **A — Giữ hợp đồng federation cũ:** Giữ SP entityID, ACS, SLO public, IdP entityID và signing trust; cấu hình library mới nhận các URLs cũ. Phù hợp khi có nhiều IdP/đối tác và mục tiêu là giảm blast radius. Phải kiểm rõ HTTP method/binding, login initiation, response resolver và logout thật.
- **B — Đăng ký hợp đồng mới:** Dùng new defaults, update IdP metadata/registry cùng reverse proxy, public URLs, certificates và tests. Đây là migration cấp trust/identity, không chỉ deploy bản JAR.
- **C — Chạy song song có kiểm soát:** Tạo hai SP registrations (entityIDs/ACS/keys khác nhau hoặc song song theo khả năng IdP) và route tách biệt trong sandbox/canary. Không mặc định IdP hỗ trợ hai ACS hoặc hai SP entityIDs; đặc biệt tránh để cùng một AuthnRequest ID/`RelayState` được xử lý bởi cả hai stacks.

**Không làm:** để IdP phát SAML Assertion `Audience=urn:portal:production:sp` nhưng bản mới expected entityID khác, rồi tắt AudienceRestriction validation. Hoặc cho mọi `Recipient`/`Destination` được chấp nhận “để tương thích”. Đó là phá trust, không phải migration.

## 3. Phân biệt bảy giá trị thường bị trộn lẫn

| Thuật ngữ | Ví dụ | Vai trò và điểm cần so |
| --- | --- | --- |
| **SP entityID** | `urn:portal:production:sp` | Định danh logic của Relying Party, xuất hiện trong SP metadata `EntityDescriptor/@entityID`, `AuthnRequest/Issuer` và `Assertion/AudienceRestriction` |
| **IdP entityID** | `https://idp.example.org/saml` | Định danh Asserting Party, `EntityDescriptor/@entityID` trong IdP metadata, expected `Response/Issuer`, `Assertion/Issuer` |
| **SP metadata URL** | `https://portal.example.org/saml2/metadata/corporate` | Địa chỉ HTTP tải XML metadata, **không bắt buộc bằng SP entityID** |
| **SP ACS URL** | `https://portal.example.org/login/saml2/sso/corporate` | Browser POST SAMLResponse, kiểm `Destination`/`Recipient` và ACS binding |
| **IdP SSO URL** | `https://idp.example.org/sso` | `AuthnRequest.Destination`, lấy từ IdP metadata `SingleSignOnService` |
| **SP SLO URL** | `https://portal.example.org/logout/saml2/slo` | SP nhận SAML LogoutRequest/LogoutResponse, metadata `SingleLogoutService` |
| **IdP SLO URL** | `https://idp.example.org/slo` | SP gửi LogoutRequest tới IdP và gửi LogoutResponse trong AP-initiated flow |

**Điểm phân biệt:** `urn:portal:production:sp` không phải URL có thể mở browser, nhưng vẫn là SP entityID hoàn toàn hợp lệ. Metadata URL thay `/saml/metadata` thành `/saml2/metadata/corporate` **có thể** không ảnh hưởng entityID nếu giữ explicit value. Trái lại, nếu dùng `{baseUrl}` defaults, đổi host/port/context path có thể thay đổi cả logical entityID ngoài ý muốn.

### 3.1. Cách đọc một metadata

SP metadata thường có dạng:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:portal:production:sp">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      AuthnRequestsSigned="true"
      WantAssertionsSigned="true">
    <md:KeyDescriptor use="signing">
      <!-- ds:KeyInfo chứa public verification certificate -->
    </md:KeyDescriptor>
    <md:KeyDescriptor use="encryption">
      <!-- public encryption certificate nếu SP cần decrypt -->
    </md:KeyDescriptor>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/saml/SingleLogout"/>
    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>
    <md:AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/saml/SSO"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

**Đây là metadata minh họa rút gọn**, các comments về certificate không thay một `ds:X509Certificate` thật. Khi chạy thực tế, IdP cần signing/decryption public certs tương ứng với actual credentials/trust policy. `EntityDescriptor` có thể có `ID`, `validUntil`, `cacheDuration` và chữ ký metadata; chúng cũng quan trọng trong trust/refresh policy.

IdP metadata thường gồm:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">
    <md:KeyDescriptor use="signing">
      <!-- Public IdP signing certificate(s) -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/sso"/>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Phân biệt trust:** TLS certificate của `idp.example.org` chỉ chứng minh máy chủ HTTPS theo PKI; nó không mặc nhiên là SAML signing certificate của IdP. SP phải trust signing certificates đã phê duyệt từ metadata/trust store của đúng entityID. Không lấy key từ `KeyInfo` trong một SAMLResponse chưa trusted rồi coi là xác thực thành công.

## 4. Đối chiếu endpoints cũ và mới theo chức năng

Các đường dẫn bên dưới là defaults tiêu biểu được tài liệu Spring Security Extension 1.x và Spring Security 6.5 mô tả. **Ứng dụng cũ có thể đã override**, nên căn cứ cuối cùng vẫn là metadata đang phát và IdP registration.

| Chức năng | Spring SAML Extension 1.x | Spring Security SAML2 6.5 | Migration action |
| --- | --- | --- | --- |
| Bắt đầu SP login | `/saml/login`, thường có `idp`/alias | `/saml2/authenticate/{registrationId}` | Thay link hoặc custom initiation matcher/resolver |
| SP ACS | `/saml/SSO` | `/login/saml2/sso/{registrationId}`, cũng có chế độ không có registrationId | Giữ URI cũ hoặc thay IdP ACS; kiểm binding |
| Metadata download | `/saml/metadata` | `/saml2/metadata/{registrationId}` hay `/saml2/service-provider-metadata/{registrationId}` | Đừng tự đổi entityID theo URL download |
| SP entityID default | Thường `{entityBaseURL}/saml/metadata` hoặc explicit | Thường `{baseUrl}/saml2/service-provider-metadata/{registrationId}` hoặc explicit | Pin identity đã đăng ký |
| User logout trigger | `/saml/logout`, legacy `?local=true` | `POST /logout` (SLO khi bật), có thể tách `POST /saml2/logout` | Không mở GET state-changing tùy tiện |
| SP SLO listener | `/saml/SingleLogout` | `/logout/saml2/slo` | Đồng bộ IdP metadata, protocol binding |
| SAML filters | `SAMLProcessingFilter`, `SAMLLogoutProcessingFilter` | `Saml2WebSsoAuthenticationFilter`, `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter` | So logic validator, không thay class 1:1 |
| Metadata generation | `MetadataGenerator`, `MetadataDisplayFilter` | `saml2Metadata()` + registration/repository | So XML output |
| Multi-IdP | `ExtendedMetadata`, aliases, `idp` parameter | `RelyingPartyRegistration`/`registrationId`/resolver | So chọn tenant/issuer |
| Bindings/profiles | Legacy có HTTP-POST/Artifact/PAOS/HoK tùy cấu hình | Không mặc định đủ feature parity | Kiểm unported features với migration guide |

**Lưu ý binding:** Một SAML Response thông thường về ACS dùng HTTP-POST. Các tính năng legacy như **HTTP-Artifact** hoặc **PAOS/Holder-of-Key** cần kiểm riêng vì Spring Security mới không cung cấp một-to-one replacement cho mọi profile. Tài liệu migration 6.5 có danh sách unported features; nếu đây là yêu cầu bắt buộc của IdP, **không cutover** khi chưa có phương án được chứng minh bằng integration test.

**Login initiation khác ACS:** `/saml2/authenticate/corporate` là điểm browser yêu cầu SP gửi `AuthnRequest`; `/login/saml2/sso/corporate` là điểm browser **trả** `SAMLResponse`. Đổi một URL mà quên URL kia là lỗi phổ biến. Metadata thường công bố **ACS và SLO**, không nhất thiết công bố browser initiation route.

## 5. Migration inventory: thu đủ dữ liệu trước khi chỉnh sửa

Lập bộ hiện trạng trong môi trường được phê duyệt:

~~~text
legacy-sp-metadata.xml       XML SP thực tế từ app cũ
legacy-idp-metadata.xml      XML IdP được app cũ trust
idp-registration-export      cấu hình SP mà IdP đang lưu
new-sp-metadata.xml          XML do app mới phát tại staging
new-idp-metadata.xml         metadata IdP mà app mới trust
test-idp-approved-cert       fingerprint của public signer đã duyệt
change-ledger.csv            old/new/expected/decision/owner/test
~~~

**Không tự copy private key vào tài liệu hoặc ticket.** Metadata chứa public certificates và federation topology có thể vẫn nhạy; giữ RBAC và retention. Không chỉnh sửa metadata XML production chỉ để che diff.

### 5.1. Bảng inventory bắt buộc

| Thuộc tính | Nguồn bên SP | Nguồn phía IdP | Cần chứng minh |
| --- | --- | --- | --- |
| SP entityID | `EntityDescriptor/@entityID` và config | IdP audience/SP identifier | Trùng **chính xác** |
| IdP entityID | IdP metadata/trusted config | IdP issuer | Đúng trusted provider |
| ACS | SP metadata `AssertionConsumerService` | IdP registered SSO/ACS URL | URL, binding, index trùng |
| SLO SP | SP metadata `SingleLogoutService` | IdP SLO callback | URL/binding/trust trùng nếu bật |
| SSO IdP | `SingleSignOnService` IdP metadata | IdP effective SSO route | AuthnRequest destination đúng |
| SLO IdP | `SingleLogoutService` IdP metadata | IdP effective SLO route | Request/response đúng binding |
| Signing public cert SP | `KeyDescriptor use=signing` | IdP SP trust | Public key dùng verify requests |
| Encryption public cert SP | `KeyDescriptor use=encryption` | IdP encryption config | Assertion encrypted được SP decrypt |
| Signing public cert IdP | Trusted IdP metadata | IdP active/rollover signer | SP verify response/assertion |
| `AuthnRequestsSigned` | SP metadata/actual request | IdP requires signed request | Logic và key đúng |
| `WantAssertionsSigned` | SP metadata/policy | IdP actual assertion signatures | Validation đúng, không bypass |
| NameID/format | SP metadata/request | IdP attribute policy | Stable principal mapping |
| SessionIndex | Assertion login | IdP SLO implementation | SLO nhắm đúng user/session |
| RelayState | Repository/session | Browser roundtrip | Correlation/return URL integrity |
| Timestamp/skew | SP config | IdP profile | Time validation giữ nguyên chính sách |
| Public origin | Reverse proxy, template `{baseUrl}` | IdP registered endpoints | HTTPS/host/port/path đúng |
| Entity aliases | Legacy `hostedSPName`/alias | Multi-SP/tenant registry | Không chọn sai registration |

### 5.2. Một dòng change ledger chuẩn

~~~text
Field: ACS.Location
Old: https://portal.example.org/saml/SSO
New candidate: https://portal.example.org/login/saml2/sso/corporate
IdP effective value: https://portal.example.org/saml/SSO
Decision: PRESERVE_OLD_UNTIL_IDP_APPROVES_CHANGE
Owner: IAM + App + Platform
Risks: SAML Destination/Recipient mismatch; cross-site POST callback
Test: SP-initiated and IdP-initiated signed SAMLResponse
Rollback: restore old route/registration atomically
~~~

**Không dùng nhãn “changed” rồi dừng:** Đánh giá mỗi diff là **expected**, **requires IdP update**, **security-sensitive** hay **blocker**. Người chịu trách nhiệm và test case phải rõ.

## 6. Đọc metadata theo ngữ nghĩa, không so toàn bộ XML text

Một XML xuất bởi thư viện khác có thể đổi:
- Prefix `md:` thành `m:` nhưng namespace URI vẫn như nhau.
- Thứ tự thuộc tính, indentation, line endings, namespace declarations.
- XML `ID`, `validUntil`, `cacheDuration` hoặc serialization order.
- Nhiều `KeyDescriptor` cho rollover, certificate formatting/line wraps.
- `AssertionConsumerService` có nhiều endpoints với indexes/bindings.
- `SingleLogoutService` có nhiều bindings (Redirect/POST) cùng hoặc khác URL.
- `Organization`/`ContactPerson`/`AttributeConsumingService` mang metadata bổ sung.

**Không phải tất cả thay đổi XML text đều là breaking change**, nhưng những trường sau phải so chặt:
1. `EntityDescriptor/@entityID` (SP và IdP).
2. `SPSSODescriptor/@AuthnRequestsSigned`, `/@WantAssertionsSigned` và actual signature policy.
3. `AssertionConsumerService@Binding`, `@Location`, `@index`, `@isDefault`.
4. `SingleLogoutService@Binding`/`@Location`/`@ResponseLocation` (nếu có).
5. `KeyDescriptor@use` và public key fingerprints/certificate validity/rotation.
6. `NameIDFormat` và attribute release/authentication requirements.
7. IdP `SingleSignOnService`/`SingleLogoutService` target/binding.
8. Metadata signature/trust/validUntil policy.
9. SP entityID in actual AuthnRequest, assertion expected Audience, ACS in Destination/Recipient.
10. Correlation/security validation behavior chứ không chỉ metadata snapshot.

### 6.1. Ví dụ metadata diff “giả” nhưng không breaking

~~~diff
- <md:EntityDescriptor entityID="urn:portal:production:sp">
+ <m:EntityDescriptor xmlns:m="urn:oasis:names:tc:SAML:2.0:metadata"
+                     entityID="urn:portal:production:sp">
~~~

Nếu XML có cùng namespace và giá trị thì prefix khác không đổi Entity ID. Trái lại:

~~~diff
- entityID="urn:portal:production:sp"
+ entityID="https://portal.example.org/saml2/service-provider-metadata/corporate"
~~~

Là **thay đổi SP identity** cần đăng ký/đánh giá, dù cả hai đều là chuỗi hợp lệ. Đừng “normalize” URN thành URL cho thuận tiện.

### 6.2. Binding URI phải giữ nguyên ngữ nghĩa

Hai binding thường thấy:

~~~text
urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST
urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect
~~~

Đổi ACS HTTP-POST sang HTTP-Redirect không chỉ thay thuộc tính; response encoding/signature/browser behavior khác và Spring Security mới không bảo đảm nhận SAML Response theo Redirect. Legacy có HTTP-Artifact có thể yêu cầu SOAP artifact resolution, channel trust và backend endpoints khác; không ép HTTP-POST khi IdP chỉ dùng artifact mà không có thỏa thuận thay đổi.

Với SLO, một IdP có thể hỗ trợ cả Redirect/POST và SP có thể public một hoặc nhiều `SingleLogoutService`. Khi cutover, kiểm **thông điệp inbound** được Spring hỗ trợ bằng binding/method mong đợi; không chỉ giữ URL. Không đồng nhất RP user-trigger URL với SP protocol listener.

### 6.3. ACS index và mặc định

Nếu metadata có:

~~~xml
<md:AssertionConsumerService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="0" isDefault="true"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://portal.example.org/saml/SSO"/>

<md:AssertionConsumerService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="1"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact"
    Location="https://portal.example.org/saml/SSO"/>
~~~

IdP có thể chọn theo default/index/binding. Nếu bản mới chỉ quảng cáo một ACS HTTP-POST, kiểm IdP thực sự sử dụng endpoint nào; đừng suy rằng mọi IdP tự chuyển từ index 1 sang index 0. Nếu IdP hardcode callback, cần cập nhật registration; nếu dựa metadata, cần kiểm cache/refresh và trust.

## 7. Spring Security SAML2: RelyingPartyRegistration là điểm trung tâm

**Legacy** có thể lưu IdP metadata và SP metadata trong các beans riêng. **New** lưu mô tả một cặp SP–IdP vào `RelyingPartyRegistration`:
- `registrationId`: khóa logic nội bộ, ví dụ `corporate`.
- SP `entityId`, `assertionConsumerServiceLocation`, keys signing/decryption, SLO location.
- IdP `entityId`, SSO/SLO endpoints, public verification/encryption certificates, bindings.
- Một `RelyingPartyRegistrationRepository` có thể có nhiều registrations, mỗi registration đại diện một trust pair.

`registrationId` **không phải** SAML Entity ID. Từ `corporate` thành `corp-prod` có thể đổi default URLs chứa `{registrationId}`, dù SP entityID explicit vẫn giữ nguyên. Việc đổi id cần test login links, resolver, repository và browser callbacks.

### 7.1. Java configuration fragment: giữ contract cũ

Ví dụ sau minh họa **cách tạo registration** với trusted IdP metadata và pin các URI. Nó là **Spring Configuration fragment**, cần project Spring Boot 3.5/Spring Security 6.5 có dependency `spring-security-saml2-service-provider` và test IdP metadata thật; không phải ứng dụng JDK độc lập.

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration
    .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistrations;

@Configuration
class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration rp = RelyingPartyRegistrations
            .fromMetadataLocation(
                "https://idp.test.example.org/metadata")
            .registrationId("corporate")
            .entityId("urn:portal:production:sp")
            .assertionConsumerServiceLocation(
                "https://portal.test.example.org/saml/SSO")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(rp);
    }
}
~~~

**Quan trọng:** Do mẫu này **không cấu hình SP signing/decryption credentials**, nó chỉ là **mô hình registration căn bản** để đối chiếu Entity ID và ACS; không khẳng định có thể login vào IdP yêu cầu signed AuthnRequest, encrypted Assertion hay SLO. Để SSO thực sự chạy phải thêm keys, SLO, verifier, HTTPS, IdP test registration và flow/matcher tương ứng.

### 7.2. SecurityFilterChain tương ứng đường dẫn ACS cũ

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SamlWebConfig {
    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .loginProcessingUrl("/saml/SSO"))
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Giải thích:** `loginProcessingUrl("/saml/SSO")` đổi request matcher của SAML ACS processing filter. Nó phải **khớp** `assertionConsumerServiceLocation("https://portal.test.example.org/saml/SSO")` và IdP registration. Với một registration, Spring có thể resolve từ state hoặc issuer. Với **nhiều IdP** và URL không chứa registrationId, phải kiểm resolver selection; có trường hợp cần custom `RelyingPartyRegistrationResolver`/authentication converter theo hướng dẫn của Spring. Không dùng `idp` query parameter legacy như một nguồn IdP tin cậy mà không xác minh issuer/signature.

**Không tự động giữ old login initiation:** `/saml/login` là một browser initiation endpoint khác với ACS. `loginProcessingUrl` chỉ đổi nơi **nhận SAMLResponse**, không tự thêm endpoint `GET /saml/login`. Có thể đổi UI link thành `/saml2/authenticate/corporate`, hoặc triển khai một controlled redirect từ old login link sang new initiation link; không redirect SAML POST ACS qua 302.

### 7.3. Boot properties khi muốn đăng ký new endpoints

Một registration thường được biểu diễn bằng:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "urn:portal:production:sp"
            assertion-consumer-service-location: >-
              https://portal.test.example.org/login/saml2/sso/corporate
            assertingparty:
              metadata-uri: https://idp.test.example.org/metadata
~~~

**Nội dung này là fragment, không chứa secret.** Boot starter phải có module SAML2/đúng dependency, IdP metadata test reachable. Khi dùng Java registration bean mục 7.1 thì **không giả định** Boot YAML và bean sẽ tự merge; chọn một nguồn cấu hình rõ ràng để tránh giá trị bị override không mong đợi.

### 7.4. Giữ old SLO URL khi thực sự được IdP hỗ trợ

Spring Security 6.5 cho phép tùy biến endpoint nhận incoming SAML LogoutRequest và LogoutResponse. **DSL fragment**:

~~~java
http.saml2Logout(saml -> saml
    .logoutRequest(req ->
        req.logoutUrl("/saml/SingleLogout"))
    .logoutResponse(res ->
        res.logoutUrl("/saml/SingleLogout")));
~~~

Đây là callback matcher, **chưa đủ** để SLO hoạt động. Đồng thời cần:
- `singleLogoutServiceLocation("https://portal.test.example.org/saml/SingleLogout")` trong registration hoặc Boot `singlelogout.url` tương ứng;
- IdP metadata có `SingleLogoutService` và binding cụ thể;
- SP PKCS#8 signing private key + public X.509 certificate, IdP trust SP key;
- IdP signing certificate trong trusted metadata;
- Test RP-initiated và IdP-initiated với **actual POST/Redirect binding**. Việc đổi matcher sang old URL **không tự chuyển** HTTP-POST SLO của new library sang behavior GET/Redirect legacy.

Đối với user-triggered `GET /saml/logout` legacy, cân nhắc đổi UI thành `POST /logout` với CSRF (nếu SAML SLO bật), hoặc tách local `POST /logout` và federated `POST /saml2/logout`. Không tái tạo GET side effect chỉ để giữ bookmark.

## 8. Reverse proxy: giữ canonical HTTPS public URLs

Giả sử browser nhìn thấy:

~~~text
https://portal.example.org/saml/SSO
~~~

Nhưng Spring backend chạy:

~~~text
http://portal-service:8080/saml/SSO
~~~

Nếu `RelyingPartyRegistration.entityId` hoặc `assertionConsumerServiceLocation` dùng `{baseUrl}` và edge không cung cấp trusted forwarding đúng, Spring có thể sinh:

~~~text
http://portal-service:8080/login/saml2/sso/corporate
~~~

Thay vì public ACS. IdP gửi `Destination=https://portal.example.org/...`, SP expected private URL → validation fail. Không bỏ Destination/Recipient validation để “sửa”.

### 8.1. Spring Boot behind trusted edge

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: none
~~~

**Chú ý:** `framework` chỉ xử lý `Forwarded`/`X-Forwarded-*`, **không tự xác minh edge trusted**. Reverse proxy phải loại/ghi đè client-supplied forwarded headers, kiểm allowed Host/SNI và ngăn direct access vào backend; chọn `framework` hoặc `native` hoặc `none` có chủ đích, không xử lý headers hai lần.

`SameSite=None; Secure` có thể cần cho SAML HTTP-POST cross-site ACS vì browser không gửi `SameSite=Lax` cookie trên một số cross-site POST flows, dẫn tới mất pending AuthnRequest và `InResponseTo`. Không mặc định mọi môi trường cần None: đánh giá browser/IdP bindings, CSRF và third-party-cookie restrictions bằng E2E. `Secure`/`HttpOnly` vẫn cần; login/session repositories không được fail open.

### 8.2. Prefix và context path

Nếu public SP là `https://portal.example.org/app` nhưng backend ở `http://portal-service:8080/`, các URLs sau phải nhất quán:

~~~text
Public:
  https://portal.example.org/app/saml/SSO
  https://portal.example.org/app/saml/SingleLogout

Internal:
  http://portal-service:8080/saml/SSO
  http://portal-service:8080/saml/SingleLogout
~~~

Proxy có thể strip `/app`, container có thể dùng context path `/app` hoặc application có thể dùng `X-Forwarded-Prefix` đúng một lần. Chọn **một** strategy và test cả chiều ra/vào: XML metadata có public path, AuthnRequest dùng public ACS, IdP POST tới URL public, proxy route đúng filter, cookie Path và CSRF không lệch. Không dùng 301/302 để sửa một signed SAML POST callback sai path.

## 9. Ký và mã hóa: certificate fingerprint là phần của contract

Metadata có thể chứa các public keys ở `KeyDescriptor`:
- `use="signing"`: SP public key để IdP kiểm AuthnRequest/LogoutRequest; IdP public key để SP kiểm Response/Assertion/Logout messages.
- `use="encryption"`: SP public key để IdP mã hóa Assertion hoặc NameID; SP cần **matching private decryption key** để giải.
- Không có `use`: theo SAML metadata semantics có thể áp dụng cho nhiều use cases, phải theo policy và actual keys; đừng bỏ qua key chỉ vì field trống.

### 9.1. Ba loại certificate không được nhập nhằng

| Loại | Ai giữ private key? | Chức năng | Migration check |
| --- | --- | --- | --- |
| SP SAML signing | SP | Ký AuthnRequest/LogoutRequest/LogoutResponse | IdP tin đúng public cert |
| SP SAML encryption | SP | Giải ciphertext IdP mã hóa cho SP | SP có đúng private key, IdP dùng correct public cert |
| IdP SAML signing | IdP | Ký Response/Assertion/Logout messages | SP tin đúng IdP public cert |
| HTTPS/TLS server | Ingress/IdP web server | TLS transport + hostname validation | CA chain/expiry/hostname, **không** thay SAML signing trust |

**Cách so:** fingerprint SHA-256 trên **DER certificate** (hoặc public key theo chính sách) với thuật toán chuẩn, giữ file binary/pub cert riêng; Base64 line breaks và PEM header không phải thay đổi certificate thực. Có thể có **nhiều cert hợp lệ do rollover**, đừng so mỗi phần tử đầu rồi xóa backup key. Certificate expiry không tự đồng nghĩa private key compromise; rollover SAML signer cần lịch phối hợp với IdP.

### 9.2. SP credentials trong Spring Boot (fragment)

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "urn:portal:production:sp"
            assertingparty:
              metadata-uri: https://idp.test.example.org/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/saml/sp-signing.key
                  certificate-location: file:/run/secrets/saml/sp-signing.crt
            decryption:
              credentials:
                - private-key-location: file:/run/secrets/saml/sp-decryption.key
                  certificate-location: file:/run/secrets/saml/sp-decryption.crt
~~~

**Mẫu cấu trúc cần IdP sandbox + key material riêng:** key file/cert phải tồn tại ở runtime, PKCS#8 private key format phù hợp framework; đặt trong secret mount read-only, không commit vào Git, Docker image hoặc log. Không dùng certificate TLS của Nginx thay cho signing/decryption credentials vì “đều là X.509”. Nếu IdP chỉ gửi signed unencrypted Assertion, cấu hình decryption có thể không cần; nếu IdP yêu cầu encrypted Assertion thì thiếu private decryption key là blocker.

### 9.3. Metadata signature vs message signature

Có hai việc riêng:
- **Metadata trust:** xác minh XML metadata được lấy từ nguồn đáng tin (HTTPS/TLS, pin keys, verified signed metadata khi federation policy yêu cầu), hạn chế SSRF, cache/refresh và certificate rollover.
- **Runtime SAML message validation:** xác minh chữ ký Response/Assertion/Logout, expected issuer, audience, recipient, destination, conditions và correlation.

Một `metadata.xml` “trông đúng” nhưng tải từ một URL attacker tự gửi không tạo trust. Không tắt kiểm metadata trust hoặc trust-all TLS để thay thư viện nhanh hơn. Nếu IdP metadata ký bằng metadata-signing certificate khác message-signing certificate, phải phân biệt hai trust anchors.

## 10. Các trường trong AuthnRequest/Response cần đối chiếu sau migration

### 10.1. Outbound AuthnRequest do SP phát

~~~text
AuthnRequest.ID                  unique, stored for correlation
AuthnRequest.IssueInstant        thời gian hợp lý
AuthnRequest.Issuer              SP entityID
AuthnRequest.Destination         IdP SingleSignOnService URL
AuthnRequest.AssertionConsumerServiceURL
                               SP public ACS URL (nếu được nêu)
AuthnRequest.ProtocolBinding     expected response binding
AuthnRequest.NameIDPolicy        NameID format & allowCreate policy
AuthnRequest.ForceAuthn          theo IdP policy
AuthnRequest.IsPassive           theo app policy
AuthnRequest.Signature           SP signing key theo binding
RelayState                       request/session state, không thành open redirect
~~~

**Mọi field đều phải đo từ actual generated request**, không kết luận “giữ entityID nên các field khác chắc chắn giống”. Spring cũ có thể đặt `NameIDPolicy`, `AuthnContextClassRef`, `ForceAuthn` hoặc signature algorithm khác. Nếu IdP yêu cầu signed AuthnRequest, test verify bằng public SP key.

### 10.2. Inbound SAML Response/Assertion từ IdP

~~~text
Response.Issuer                   trusted IdP entityID
Response.Destination              SP ACS public endpoint
Response.InResponseTo             pending AuthnRequest ID (SP-initiated)
Assertion.Issuer                  trusted IdP entityID
Assertion.AudienceRestriction     expected SP entityID
SubjectConfirmationData.Recipient SP ACS public endpoint
SubjectConfirmationData.InResponseTo
                                 correlation khi áp dụng
Conditions.NotBefore/NotOnOrAfter time + allowed skew
AuthenticationStatement.SessionIndex
                                 SLO session context nếu dùng
NameID and NameIDFormat          principal mapping contract
Signature(s)                     trusted IdP public cert
EncryptedAssertion/NameID        correct SP private decryption key
~~~

**IdP-initiated/unsolicited SSO** có thể không có `InResponseTo` vì không có AuthnRequest. Nếu app cũ cho phép, cần xác định **thư viện mới hỗ trợ và chính sách chấp nhận IdP-initiated thế nào**, thông qua explicit tests. Đừng bỏ `InResponseTo` validation cho mọi SP-initiated Response để cho một số unsolicited cases pass. Kiểm signer/issuer/recipient/audience/time và allowed unsolicited tenants riêng.

### 10.3. Không dùng HTTP 302 làm bằng chứng

Một login E2E pass phải chứng minh:
1. Browser được chuyển tới IdP approved endpoint; AuthnRequest issuer/ACS/signature đúng.
2. IdP ký SAMLResponse/Assertion hợp lệ; browser POST tới public ACS.
3. SP validator chấp nhận đúng issuer/certificate/audience/destination/recipient/time/correlation; invalid fixtures bị reject.
4. `Saml2Authentication`/principal và authorities phù hợp policy.
5. Servlet session được tạo/rotate an toàn, protected resource đúng authorization; `403` khi thiếu quyền không phải lỗi SAML.
6. Cả negative cases wrong signature, wrong audience, wrong recipient, replay, expired Assertion đều fail closed.

Nếu chỉ thấy 302 /home sau login, không biết authentication đến từ SAML hay form fallback; test phải kiểm authentication mechanism đã xác minh.

## 11. NameID, attributes và role mapping sau khi đổi thư viện

Migrating metadata nhưng không kiểm mapping user dễ gây **silent authorization drift**. Legacy `SAMLAuthenticationProvider` có thể trích:
- NameID/NameIDFormat (`persistent`/`transient`/`emailAddress`/`unspecified`);
- AttributeStatements với friendly name hoặc OID URI;
- `eduPersonPrincipalName`/UPN/email/employeeId;
- Group/Role attributes có multi-values;
- AuthnContextClassRef và `SessionIndex`.

Spring Security mới biểu diễn principal qua `Saml2AuthenticatedPrincipal` và `Saml2Authentication`, rồi có thể dùng converter/`UserDetailsService`/authority mapper riêng. Không giả định `Authentication.getName()` giữ nguyên nếu legacy dùng NameID khác với principal name mapping mới.

**Migration tests:**

| Case | Điều cần so |
| --- | --- |
| NameID persistent | Cùng user account nội bộ, đúng realm/issuer |
| NameID transient | Không dùng làm stable user ID khi chính sách yêu cầu persistent |
| Email thay đổi | Không cấp quyền account khác chỉ vì trùng email |
| Multivalued groups | Không đổi giá trị thứ tự thành role; validate scope/tenant |
| Signed attributes | Không tin unsigned/unknown issuer attributes |
| User disabled | Đăng nhập federation có thể pass nhưng app vẫn chặn |
| NameIDFormat không hỗ trợ | Fail theo IdP contract, không silently fallback |
| Multi-IdP cùng NameID | Dùng issuer/tenant context, tránh identity collision |
| Authorization role mapping | `403` đúng với user thiếu role, không cấp `ROLE_ADMIN` mặc định |
| SessionIndex | Có dữ liệu đúng phục vụ SLO khi IdP yêu cầu |

**Không dùng một email từ browser request làm principal** nếu SAML Assertion không có chữ ký hợp lệ và issuer đáng tin. Tầng phân quyền cần được QA độc lập dù protocol authentication pass.

## 12. SLO và logout URL: thay thư viện dễ sai cả hai chiều

SAML Single Logout có hai luồng:
- **RP/SP-initiated:** user logout tại Portal, SP sinh `LogoutRequest` tới IdP SLO, IdP trả `LogoutResponse` về SP listener.
- **IdP-initiated:** IdP gửi signed `LogoutRequest` tới SP listener, SP xác thực rồi invalidate local session và trả signed `LogoutResponse`.

Legacy có thể dùng `/saml/logout` để user khởi tạo và `/saml/SingleLogout` làm listener. Spring Security 6.5 thường dùng user POST `/logout` và listener `/logout/saml2/slo`. Đây **không phải** hai URL có thể hoán đổi.

### 12.1. Ma trận SLO migration

| Test | Expected |
| --- | --- |
| Old IdP vẫn gửi `/saml/SingleLogout`, SP mới chỉ nghe `/logout/saml2/slo` | 404/no processing; blocker nếu chưa update IdP |
| SP mới quảng bá SLO cũ và listener match cũ | IdP callback tới đúng filter; phải kiểm binding |
| IdP yêu cầu HTTP-Redirect inbound, SP mới chỉ nhận POST | Không giả định rename URL là đủ; test capability |
| RP LogoutRequest thiếu SP signer | IdP reject theo signing policy |
| IdP LogoutRequest signed bởi IdP lạ | SP reject, không forced logout |
| Signed LogoutResponse wrong `InResponseTo` | SP reject correlation |
| SessionIndex không phù hợp IdP | IdP không logout đúng session; xử lý profile |
| Browser callback cross-site POST thiếu session cookie | Detect request repository/correlation issue |
| User local logout | Chỉ SP session cleanup, không tuyên bố IdP logout |
| PartialLogout | Báo federation incomplete, không “logout mọi nơi” |
| SLO khi IdP down | Local session có thể đã dọn, federation unconfirmed |
| Replay LogoutRequest/LogoutResponse | Không có repeated side effects hoặc false success |

**Security:** Không mở `GET /saml/logout` để thực hiện state-changing user logout trừ khi đã có risk approval và bảo vệ CSRF tương đương. Với application người dùng, nên dùng POST + CSRF. Ngược lại, inbound SAML protocol POST đến SLO listener không có browser form CSRF token nhưng phải kiểm signed SAML message; không tắt `csrf.disable()` toàn bộ app.

### 12.2. Metadata SingleLogoutService có hai địa chỉ

Trong IdP metadata, `SingleLogoutService.Location` là endpoint IdP nhận LogoutRequest, `ResponseLocation` có thể chỉ endpoint IdP nhận LogoutResponse. Trong SP metadata, fields tương tự mô tả SP receiver. Khi so XML, **không** nhầm Location của IdP với Location của SP. Đổi new `singlelogout.url` là định nghĩa SP callback, không mặc nhiên thay URL IdP SLO. Trong Spring DSL, callback matchers và RelyingPartyRegistration phải thống nhất.

## 13. OpenSAML, Spring Boot và Servlet: kiểm compatibility có hệ thống

### 13.1. Các lớp di chuyển khác nhau

| Lớp | Legacy | New | Điều cần test |
| --- | --- | --- | --- |
| Spring stack | Có thể là Spring 4/5, javax.servlet | Boot 3/Jakarta Servlet | Dependencies, filter registration |
| SAML abstraction | Extension beans + custom OpenSAML | `saml2Login`/`RelyingPartyRegistration` | Semantic parity, key/URLs |
| OpenSAML | Legacy cũ | 4/5 tùy Spring version | Resolver/validators, signatures, encrypted Assertions |
| Servlet session | Container/session store cũ | Session store mới (Spring Session nếu dùng) | InResponseTo/RelayState/multi-node |
| Metadata publishing | Generator/display filter | `saml2Metadata` | EntityID, ACS, SLO, bindings, certs |
| User identity | Legacy credential/principal type | `Saml2AuthenticatedPrincipal`/`Saml2Authentication` | NameID/role mapping |
| Logout | Old filters/URL | New SLO filters/URL | RP + IdP initiated |

Không dùng `mvn dependency:tree` để chỉ xác nhận một JAR có mặt; hãy kiểm có **duplicate OpenSAML versions**/transitive conflicts hoặc unsupported plugins, đảm bảo Boot/Spring Security/OpenSAML versions tương thích theo BOM/migration guide. Mỗi version còn có khác biệt behavior như validation order, no-registration fallback và OpenSAML default; regression tests phải chạy trên đúng target artifact.

### 13.2. Vì sao không “copy” legacy validator

Legacy có thể cho phép `unsolicited response`, tùy biến signature trust, replay, clock skew, NameID, encryption và authority mapping qua OpenSAML internals. New library được thiết kế để framework defaults kiểm nhiều yếu tố theo contract. Nếu custom lại:
- Đừng đặt validator “always PASS” khi missing issuer/destination/audience.
- Không dùng `KeyInfo` trong untrusted Assertion làm trust anchor.
- Không bỏ time/replay validation để phù hợp IdP đang phát sai clock.
- Không cố dùng XML Signature wrapping-prone parse logic tự viết.
- Ghi quyết định: **defaults**, **policy-added checks**, **verified exception** với test tương ứng.

**Nếu một legacy feature chưa port:** đánh dấu blocker, tìm giải pháp supported, hoặc điều chỉnh IdP profile qua change-control. Việc lén thay binding một phía không giải quyết support gap.

## 14. Java 17 độc lập: SamlContractDiffDemo

Để review migration trước khi có IdP sandbox, dùng một comparator Java 17 với dữ liệu **đã được trích từ metadata đáng tin và IdP registry**. Chương trình **không phân tích XML, không kiểm chữ ký và không sinh AuthnRequest**: nó là **đối chiếu policy**. Demo phân biệt entityID/issuer drift, public HTTPS, ACS/SLO path, binding/cert rotation và trạng thái cutover được phê duyệt.

**Tệp `SamlContractDiffDemo.java`:**

~~~java
import java.net.URI;
import java.util.Objects;

public class SamlContractDiffDemo {

    record Contract(
        String spEntityId,
        String idpEntityId,
        String acs,
        String slo,
        String acsBinding,
        String signerFingerprint) {}

    static final Contract LEGACY = new Contract(
        "urn:portal:production:sp",
        "https://idp.example.org/saml",
        "https://portal.example.org/saml/SSO",
        "https://portal.example.org/saml/SingleLogout",
        "HTTP-POST",
        "sha256:sp-signer-v1"
    );

    static boolean approvedHttps(String input) {
        try {
            URI u = URI.create(input);
            return "https".equalsIgnoreCase(u.getScheme())
                && "portal.example.org".equalsIgnoreCase(u.getHost())
                && (u.getPort() == -1 || u.getPort() == 443)
                && u.getUserInfo() == null
                && u.getQuery() == null
                && u.getFragment() == null;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    static String compare(
            Contract old,
            Contract next,
            boolean endpointChangeApproved) {
        if (!Objects.equals(old.spEntityId(), next.spEntityId())) {
            return "BLOCK_SP_ENTITY_ID";
        }
        if (!Objects.equals(old.idpEntityId(), next.idpEntityId())) {
            return "BLOCK_IDP_ENTITY_ID";
        }
        if (!approvedHttps(next.acs()) || !approvedHttps(next.slo())) {
            return "BLOCK_NON_PUBLIC_HTTPS";
        }
        if (!Objects.equals(old.acsBinding(), next.acsBinding())) {
            return "BLOCK_ACS_BINDING";
        }
        if (!Objects.equals(
                old.signerFingerprint(), next.signerFingerprint())) {
            return "REVIEW_CERT_ROTATION";
        }
        boolean moved = !Objects.equals(old.acs(), next.acs())
                || !Objects.equals(old.slo(), next.slo());
        if (moved) {
            return endpointChangeApproved
                ? "APPROVED_ENDPOINT_CHANGE_NEEDS_E2E"
                : "BLOCK_ENDPOINT_CHANGE";
        }
        return "SAME_CONTRACT_NEEDS_E2E";
    }

    static void show(String name, Contract proposed, boolean approved) {
        System.out.println(name + "="
                + compare(LEGACY, proposed, approved));
    }

    public static void main(String[] args) {
        Contract modern = new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            "https://portal.example.org/login/saml2/sso/corporate",
            "https://portal.example.org/logout/saml2/slo",
            "HTTP-POST", LEGACY.signerFingerprint());

        show("unchanged", LEGACY, false);
        show("modernBlocked", modern, false);
        show("modernApproved", modern, true);

        show("newEntityId", new Contract(
            "https://portal.example.org/saml2/metadata/corporate",
            LEGACY.idpEntityId(), LEGACY.acs(), LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);

        show("wrongIdp", new Contract(
            LEGACY.spEntityId(), "https://evil.example/saml",
            LEGACY.acs(), LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);

        show("httpAcs", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            "http://portal-service:8080/saml/SSO", LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);

        show("wrongBinding", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            LEGACY.acs(), LEGACY.slo(),
            "HTTP-Redirect", LEGACY.signerFingerprint()), false);

        show("rotatedSigner", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            LEGACY.acs(), LEGACY.slo(),
            LEGACY.acsBinding(), "sha256:sp-signer-v2"), false);

        show("evilHost", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            "https://evil.example/saml/SSO", LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);
    }
}
~~~

**Chạy trên JDK 17+:**

~~~bash
javac SamlContractDiffDemo.java
java SamlContractDiffDemo
~~~

**Stdout chính xác:**

~~~text
unchanged=SAME_CONTRACT_NEEDS_E2E
modernBlocked=BLOCK_ENDPOINT_CHANGE
modernApproved=APPROVED_ENDPOINT_CHANGE_NEEDS_E2E
newEntityId=BLOCK_SP_ENTITY_ID
wrongIdp=BLOCK_IDP_ENTITY_ID
httpAcs=BLOCK_NON_PUBLIC_HTTPS
wrongBinding=BLOCK_ACS_BINDING
rotatedSigner=REVIEW_CERT_ROTATION
evilHost=BLOCK_NON_PUBLIC_HTTPS
~~~

**Cách đọc:**
- `SAME_CONTRACT_NEEDS_E2E`: cùng các trường policy trong demo **chưa chứng minh** login hoạt động; vẫn cần signed SAML integration tests.
- `BLOCK_ENDPOINT_CHANGE`: ACS/SLO khác nhưng IdP change chưa được phê duyệt.
- `APPROVED_ENDPOINT_CHANGE_NEEDS_E2E`: thay URL được cho phép về quy trình, vẫn cần IdP registration + browser/crypto tests.
- `BLOCK_SP_ENTITY_ID`: identity đã đổi, phải xử lý như một federation trust change.
- `BLOCK_NON_PUBLIC_HTTPS`: URL chứa HTTP hoặc host lạ, không phù hợp public policy.
- `REVIEW_CERT_ROTATION`: certificate thay đổi là một sự kiện cần trust rollout, có thể hợp lệ nếu được duyệt.
- `BLOCK_ACS_BINDING`: thay profile nhận Response; cần chứng minh IdP hỗ trợ.

**Giới hạn rõ:** Fingerprints trong code là **chuỗi giả để minh họa**, không phải hash cryptographic của certificate thật. Production comparator nên nhận **SHA-256 fingerprint đã tính từ DER public certificate đáng tin**, có multi-key rollover policy. `approvedHttps` chỉ kiểm scheme/host/port/cấu trúc, **không** kiểm DNS rebinding, certificate trust, exact path allowlist, canonicalization, XML signature, metadata provenance, OAuth-style open redirect hoặc SAML security. Không dùng Java oracle để quyết định user authentication production.

## 15. Quy trình lấy metadata và tự động hóa so sánh an toàn

### 15.1. Export đúng thời điểm

1. Từ **legacy SP staging**, tải **actual SP metadata** và ghi rõ version/git commit, timestamp, public host, entityID. Không suy ra từ old config XML khi metadata generator có thể đã tùy biến.
2. Từ **IdP sandbox**, xuất metadata trusted IdP và effective SP registration: entityID, ACS/SLO/bindings, SP trust certificates, policies.
3. Chạy bản **Spring SAML2 mới** dưới public HTTPS staging đúng reverse proxy, bật `saml2Metadata` và tải actual SP metadata.
4. Khóa snapshot metadata/sha256 fingerprint file và lưu ở kho artifact có quyền phù hợp, không đưa IdP private key hoặc SAML tokens vào report.
5. Trích các fields bằng XML parser bảo mật, so canonical values theo namespace. Không dùng grep duy nhất cho một XML có namespaces/optional elements/multiple endpoints.
6. Sinh change ledger theo trường `old/new/idpEffective` và điền decision/owner/tests.
7. Đưa kết quả cho IAM và App review, không tự publish metadata mới cho tất cả IdPs khi chưa phê duyệt.

### 15.2. XML parsing security khi viết comparator thực tế

XML metadata có thể chứa external entity/DTD hoặc XML signatures; nếu tự viết parser để **trích thông tin**, phải:
- Dùng namespace-aware XML parser.
- Bật secure processing, tắt external entities/DTD loading/XXE, giới hạn kích thước và độ sâu.
- Không dùng network fetch external entity.
- Không coi XML parse thành công là metadata signature trusted.
- Xử lý nhiều `EntityDescriptor` và chọn **đúng entityID được allowlist**, không lấy phần tử đầu tiên.
- Phân biệt SPSSODescriptor và IDPSSODescriptor.
- So **public certificates** theo DER hash, không theo PEM whitespace.
- So `Binding` là URI chuẩn, không chỉ text “POST”.
- Không bỏ qua default/index ACS hoặc `ResponseLocation` ở SLO.
- Cảnh báo khi metadata expired `validUntil` hoặc signer không được trust.

**Đối chiếu metadata là một bước review, không phải thay thế SAML validators của framework.** Nếu build parser nội bộ, phải có unit tests chống XML Signature Wrapping và XXE, nhưng không cần tự viết bộ xác thực SAML đầy đủ; dùng framework/OpenSAML đã được tích hợp và security review.

### 15.3. Đừng so private keys bằng cách in ra log

Đối chiếu nên dùng:
- SP public signing certificate fingerprint(s).
- SP public encryption certificate fingerprint(s).
- IdP public signing certificate fingerprint(s).
- Certificate validity/overlap window và SP/IdP signing policy.
- Alias/secret version ở secret manager (không chia private-key bytes).
- Thành công/chữ ký của **test AuthnRequest/Response** trong IdP sandbox.

Khi phải rotate key, làm dual-key overlap nếu IdP/metadata/framework hỗ trợ; không hứa old and new đều accepted sau một password/secret rotation. Không đưa certificates production/keys vào Git khi policy cấm; signing public cert có thể công bố trong metadata nhưng vẫn cần quản lý provenance.

## 16. Kiểm thử E2E sau khi metadata khớp

**Một phép E2E SSO cần kiểm đúng cả hai hướng:**

~~~text
User Browser                    New SP                    IdP sandbox
    |                              |                           |
    | GET /saml2/authenticate/corporate                        |
    |----------------------------->|                           |
    |       AuthnRequest (Issuer=approved SP entityID)         |
    |<----------- redirect/post ---|                           |
    |--------------------- AuthnRequest ---------------------->|
    |                              |                           |
    |                  IdP validates SP signature/policy       |
    |                              |                           |
    |<------------------ signed SAMLResponse -----------------|
    | POST public ACS             |                           |
    |----------------------------->|                           |
    |                     validate IdP signer/issuer          |
    |                     Audience/Recipient/Destination     |
    |                     InResponseTo/time/replay            |
    |                     principal/authorities               |
    |<----------------- session authenticated                 |
    | GET protected resource      |                           |
    |----------------------------->|                           |
    |<----------------- 200 or authorized 403                  |
~~~

**Đừng tự tạo AuthnRequest/SAMLResponse bằng chuỗi XML không ký rồi gọi positive test.** Một request/response thật phải ký theo policy, đúng certificate và binding, qua browser/IdP sandbox. Nếu chỉ thay XML sau khi ký để test Audience hoặc InResponseTo, signature sẽ fail trước; cần **trusted test IdP signer** ký lại fixture cố tình sai một trường.

### 16.1. Positive cases

| ID | Tình huống | Bằng chứng pass |
| --- | --- | --- |
| S01 | SP metadata mới xuất đúng entityID cũ | `EntityDescriptor/@entityID` exact |
| S02 | SP metadata mới giữ ACS theo quyết định | `Location`/`Binding`/index đúng |
| S03 | IdP metadata trusted còn đúng issuer | `IDPSSODescriptor`/`SingleSignOnService` |
| S04 | SP-initiated login | Correct AuthnRequest Issuer/ACS/IdP Destination |
| S05 | IdP ký Response/Assertion | New SP verifies cert/issuer/signatures |
| S06 | IdP Response Recipient public ACS | Match registration, not internal host |
| S07 | Audience match SP entityID | No bypass audience validation |
| S08 | InResponseTo and RelayState match | Request/session repository correlation |
| S09 | Session user attributes & authorities | Correct user mapping/role policy |
| S10 | Same user authenticates via old/new in lab | Semantically equivalent identity, not same browser session |
| S11 | IdP-initiated login if supported | Signed unsolicited Response under explicit policy |
| S12 | RP-initiated SLO | Signed LogoutRequest, IdP response verified |
| S13 | IdP-initiated SLO | Verify incoming signed LogoutRequest, clear correct session |
| S14 | Multi-IdP registrations | Correct issuer/tenant/registration selection |
| S15 | Browser behind reverse proxy HTTPS | No internal URL, proper cookie/CSRF |
| S16 | Multi-node login callback | Correlation survives permitted routing/state store |
| S17 | Certificate rollover in sandbox | Approved keys verify throughout window |
| S18 | Cutover to new ACS intentionally | IdP registry updated, signed SAML login works |

### 16.2. Negative cases

| ID | Thử lỗi | Expected |
| --- | --- | --- |
| N01 | IdP Assertion Audience vẫn là old SP nhưng new registration dùng entityID khác | Reject, không nới audience |
| N02 | IdP Response Recipient old ACS nhưng new SP expects new | Reject |
| N03 | SP metadata public URLs chứa `http://pod:8080` | QA fail trước cutover |
| N04 | IdP Response unsigned khi policy yêu cầu signed | Reject |
| N05 | Signed bởi IdP certificate chưa trust | Reject |
| N06 | Signed valid IdP message nhưng wrong issuer | Reject |
| N07 | Signed message wrong Destination | Reject |
| N08 | Signed message wrong `InResponseTo` | Reject |
| N09 | Replay Assertion/Response | Reject, no reused session |
| N10 | Expired Assertion/NotBefore future | Reject theo clock policy |
| N11 | Wrong NameIDFormat | Không map sang account khác |
| N12 | Multi-IdP same NameID, different issuer | No cross-tenant principal collision |
| N13 | IdP metadata missing/invalid signer | No trust-all fallback |
| N14 | IdP metadata expired `validUntil` | Fails/alerts per policy |
| N15 | Legacy artifact-only IdP không có POST ACS | Block migration, không pretend supported |
| N16 | Legacy old callback still registered at IdP but new filter not matching | Detect 404/not processed |
| N17 | New SLO listener khác IdP configured SLO | Detect IdP callback failure |
| N18 | IdP-initiated unsigned LogoutRequest | Reject without invalidating user session |
| N19 | LogoutResponse signed valid nhưng wrong `InResponseTo` | Reject correlation |
| N20 | SP backend direct request có spoofed X-Forwarded-Host | Not trusted, no attacker ACS |
| N21 | Browser SAML HTTP-POST không gửi session cookie | Detect SameSite/session issue, no bypass |
| N22 | Callback tới node khác, request state missing | Reject safe; fix shared repository |
| N23 | SP signing key rotated, IdP chưa cập nhật public cert | IdP rejects; coordinated rollout |
| N24 | SP decryption key missing, IdP Assertion encrypted | Reject, no plaintext fallback |
| N25 | GET user logout thiếu CSRF tại old endpoint | Không phục hồi insecure behavior mặc định |
| N26 | Authenticated principal thiếu role | 403, không cấp role để che migration error |
| N27 | Two registrations share same entityID but wrong resolver | Test routing/issuer conflicts, fail |
| N28 | Proxy rewrites SAML POST callback qua 302 | Detect loss of body/state; fix route |
| N29 | Metadata trust check disabled for convenience | Security QA fail |
| N30 | XML malformed/XXE parser attempt | Reject safely |
| N31 | IdP signing certificate rotation, new SP trust stale key | Reject, planned rollover |
| N32 | SAML logout reports PartialLogout | Not global success |

**QA không đồng nhất transport và protocol:** HTTP 302 đến IdP không chứng minh AuthnRequest signer đúng; HTTP 200 tại ACS không chứng minh Audience/time/correlation validation; `SAMLResponse` Base64 không có nghĩa signed; user được login vào `/home` có thể đến từ cơ chế khác. Cần IdP verifier events và Spring authenticated mechanism đã sanitize.

## 17. Multi-tenant / multi-IdP migration

Legacy có thể chọn IdP bằng `/saml/login?idp=partner-a` và dùng `ExtendedMetadata`/alias. Spring Security SAML2 dùng `registrationId` như `corporate-a` và `partner-b`.

~~~text
New links:
  /saml2/authenticate/corporate-a
  /saml2/authenticate/partner-b

New repository:
  corporate-a -> SP entityID urn:portal:corporate-a -> IdP A
  partner-b   -> SP entityID urn:portal:partner-b   -> IdP B

Never:
  /saml2/authenticate?assertingPartyUrl=https://evil.example
  trust IdP based only on unsigned query/header
~~~

Nếu muốn giữ một ACS chung `/saml/SSO` cho nhiều IdPs:
- `RelyingPartyRegistrationResolver` phải chọn trust registration đúng từ prior AuthnRequest state hoặc validated SAML issuer/context.
- Các IdP signing certificates/issuers phải được ràng buộc với registration tương ứng.
- Không để `NameID=alice` từ IdP B map vào user IdP A nếu không có federation identity policy.
- Test unsolicited IdP-initiated SSO khi không có `registrationId` trong path; chỉ chấp nhận nếu resolver có chính sách rõ.
- Không randomize `registrationId` mà không xem default URLs và metadata; tên registration là nội bộ nhưng được dùng trong nhiều URL templates.
- Thay metadata của một tenant không được làm thay Entity ID/ACS/keys của tenant khác.

**Nếu legacy có một SP entityID phục vụ nhiều IdPs:** Spring hỗ trợ nhiều RelyingPartyRegistration pairs, nhưng việc giữ cùng logical SP entityID cho nhiều IdPs/registrations đòi mapping/callback/session policies rõ. Không cưỡng ép một registration cho mọi đối tác và hy vọng valid signatures tự chọn đúng IdP.

## 18. Kịch bản rollout: hạn chế thời gian gián đoạn

### Giai đoạn 0 — Baseline và đồng thuận

1. Export old SP metadata, trusted IdP metadata, IdP effective registration, public URLs, keys/certificate fingerprints và login/logout behavior.
2. Kiểm feature inventory: SP-initiated, unsolicited IdP-initiated, SLO, Artifact, bindings, NameID, groups, AuthnContext, signing, decryption.
3. Quyết định preserve old entityID/ACS/SLO hay register new; lập change ledger có owner và fallback.
4. Đặt baseline authentication/authorization tests, failure metrics và SAML logs đã redact.

### Giai đoạn 1 — Staging

1. Build Spring Security SAML2 đúng Java/Boot/Spring Security/OpenSAML version.
2. Dựng `RelyingPartyRegistration` từ IdP metadata trusted, pin entityID/ACS/cert policies.
3. Bật metadata endpoint và so actual XML với old metadata.
4. Test browser HTTPS/proxy/Host/Forwarded/SameSite/session repository.
5. Kiểm signed AuthnRequest/Response với test IdP, negative tests, SLO/multi-IdP nếu dùng.
6. Nếu phải đổi URI/Entity ID, IdP sandbox registration phải được cập nhật và re-import metadata đúng.

### Giai đoạn 2 — Cutover có cửa sổ thay đổi

- Dùng DNS/ingress route có kiểm soát hoặc hai SP registrations thực sự độc lập nếu IdP hỗ trợ.
- Không chạy hai stacks nhận cùng `SAMLResponse`/RelayState một cách ngẫu nhiên khi chúng có session/request repositories khác nhau.
- Nếu giữ old ACS/SLO, đảm bảo proxy forward vào đúng new filters, không chỉ HTTP redirect.
- Nếu đổi ACS, đảm bảo IdP gửi trực tiếp POST tới new **HTTPS** endpoint.
- Giữ rollback route và old IdP registration/keys trong khoảng được phê duyệt, nhưng không giữ expired/compromised keys rộng quyền.
- Theo dõi signature/issuer/Audience/Recipient/InResponseTo failures, 401/403, SLO errors, login success by tenant, business authorization.

### Giai đoạn 3 — Sau cutover

- Re-export SP metadata từ production, so với approved contract, xác nhận IdP effective settings không drift.
- Kiểm rollout trên nhiều pods/nodes/reverse proxy routes.
- Kiểm certificate rollover/metadata refresh, key expiry, TLS expiry và session store TTL.
- Thu hồi legacy keys/endpoints/filters khi toàn bộ traffic đã chuyển và rollback window kết thúc.
- Cập nhật operational runbook, audit log fields, incident processes và long-term regression tests.
- Đừng tuyên bố migration hoàn tất nếu một tenant/IdP/legacy binding vẫn thất bại.

### 18.1. Rollback không phải chỉ rollback JAR

Nếu đã thay `entityID`/ACS/SLO/certificate trong IdP registry, rollback Spring JAR mà **không rollback IdP registration** có thể khiến old SP không nhận được Assertion. Rollback plan phải gồm:
- IdP trust/metadata/cert state,
- DNS/ingress/canonical host/path,
- old/new SP application route,
- session/request state compatibility,
- tenant rollout order,
- recovery of registered ACS/SLO/binding,
- secret/key validity and overlap.

Nếu IdP chỉ hỗ trợ một ACS, cần một cutover transaction/change window; không hứa zero downtime với cấu hình không thể chạy song song.

## 19. Troubleshooting migration theo triệu chứng

| Triệu chứng | Sai khác thường gặp | Cách chẩn đoán |
| --- | --- | --- |
| IdP báo unknown SP/entity | `entityID` đổi khi dùng new default | So SP metadata entityID với IdP registered audience |
| IdP không POST về SP | ACS mới chưa được đăng ký | So `AssertionConsumerService.Location` và IdP ACS |
| SAML Response bị reject Audience | Expected SP entityID khác Assertion Audience | Giữ identity hoặc update IdP, không disable Audience |
| SAML Response Recipient mismatch | Public ACS vs internal URL/prefix | Fix reverse proxy/canonical baseURL/registration |
| SAMLResponse signed nhưng invalid signature | IdP signer cert trust/rotation | So IdP verification certs, signed element policy |
| Encrypted Assertion decrypt fail | New SP không có private decryption key | Secret provisioning, `KeyDescriptor use=encryption` |
| RelayState/InResponseTo mismatch | Session repo/ACS flow/multi-node | Test request storage/CSRF/SameSite |
| New SP trả 404 tại `/saml/SSO` | Chỉ bật default new ACS | Set matcher hoặc update IdP |
| New SP login link `/saml/login` không chạy | Initiation route chưa migration | Thay UI link hoặc controlled redirect GET |
| New SP metadata 404 | Chưa bật `saml2Metadata` hoặc URL khác | Kiểm DSL/routes, không suy Entity ID từ URL |
| SLO trả 404 | IdP vẫn trỏ `/saml/SingleLogout` | Listener/metadata/IdP config phải khớp |
| IdP LogoutRequest signed nhưng rejected | Wrong IdP cert/issuer/recipient/binding | Test SLO validation, không bypass |
| SLO only local session cleared | IdP SLO unsupported/offline | Đánh giá federation unconfirmed, không global success |
| Metadata has new signer unexpectedly | Key alias/secret rollover | Fingerprint, IdP trust and key management |
| Artifact/PAOS flow fail | Feature không port tương đương | Capability gap, không ép POST khi không hỗ trợ |
| One tenant login, other tenant fail | registrationId/issuer/resolver selection | Test từng IdP/tenant riêng |
| HTTP redirect to Pod internal host | Forwarded headers/public origin sai | Fix trusted ingress and `{baseUrl}` |
| Login 200 nhưng role mất | NameID/attributes mapping khác | Compare principal, group mapping, authorization |
| Một Pod fail, các Pod khác pass | Config/cert/session repository drift | Node-level compare |
| Clock skew errors | JVM/IdP time khác | NTP and allowed skew, không tắt time validation |
| Upgrade OpenSAML breaks custom converter | Incompatible API/validator changes | Target version migration guide, dependency tree |
| Unsolicited response bị reject | Old app cho phép IdP-initiated, new policy khác | Xác minh requirement, configure/test explicit security policy |

**Quy trình xử lý:** Identity/IdP source → SP entityID → public ACS/SLO/bindings → signer/decryption certs → actual AuthnRequest/Response fields → browser cookies/correlation → principal/role mapping → authorization. Thay đúng tầng; không bật trust-all để che lỗi dưới tầng.

## 20. Checklist và bài tập

### 20.1. Checklist release gate

- [ ] Có snapshot metadata old/new cùng IdP effective registration.
- [ ] SP entityID và IdP entityID có quyết định preserve/change được phê duyệt.
- [ ] ACS `Location`/`Binding`/index/default và public HTTPS đúng.
- [ ] SP metadata URL đổi **không** ngầm đổi logical Entity ID.
- [ ] IdP SSO/SLO service endpoints và binding đúng.
- [ ] Signing/decryption public certs, private key mounts, rollover policy được kiểm.
- [ ] Metadata trust/signature/validUntil được duy trì theo policy.
- [ ] AuthnRequest signing, NameIDPolicy và AuthnContext được test với IdP.
- [ ] SAML Response/Assertion validation issuer/audience/destination/recipient/time/correlation pass; negatives reject.
- [ ] Legacy artifact/PAOS/HoK behavior được inventory; unsupported features có disposition.
- [ ] Multi-IdP registrationId/resolver/tenant boundaries được test.
- [ ] Principal/authorities mapping và object-level authorization không drift.
- [ ] Browser HTTPS/SameSite/CSRF và multi-node session repo được test.
- [ ] RP/IdP-initiated SLO được test nếu contract yêu cầu.
- [ ] IdP metadata, app routes, DNS/ingress và rollback cùng được duyệt.
- [ ] Không có private keys, raw SAML Response/Assertion, session cookies, NameIDs người thật trong Git/logs.
- [ ] Runbook incident và monitoring regression hoạt động sau cutover.

### 20.2. Bài tập thực hành

**Bài A – phân biệt các URI.** Cho URL metadata `/saml/metadata` và `EntityDescriptor entityID="urn:portal:production:sp"`. Khi chuyển metadata endpoint sang `/saml2/metadata/corporate`, có bắt buộc đổi Entity ID không? Giải thích vì sao không.

**Bài B – diff metadata.** Lấy hai XML fixture có cùng Entity ID nhưng prefix `md`/`m` khác. Trình bày vì sao text diff báo thay đổi còn semantic diff không báo breaking change. Nếu ACS Location thay, cần field nào ở IdP thay theo?

**Bài C – mapping Endpoint.** Lập bảng old `/saml/login`, `/saml/SSO`, `/saml/SingleLogout`, `/saml/metadata` sang new endpoints. Chỉ ra đâu là SP-initiated user trigger, đâu là ACS, đâu là SLO listener.

**Bài D – Java 17.** Chạy `SamlContractDiffDemo.java`, đối chiếu 9 dòng stdout. Đổi public ACS sang `http://portal-service:8080/saml/SSO` và giải thích `BLOCK_NON_PUBLIC_HTTPS`. Nêu giới hạn comparator này.

**Bài E – registration.** Tạo `RelyingPartyRegistration` cho IdP sandbox với SP entityID cố định và ACS cũ; thêm `SecurityFilterChain` đúng matcher. Test signed SAML Response đến ACS qua browser HTTPS, không dùng raw XML unsigned.

**Bài F – signed negative case.** Dùng IdP sandbox ký lại Response có Audience sai nhưng signer hợp lệ. Chứng minh SP reject vì audience, không chỉ vì chữ ký bị phá khi sửa XML sau khi ký.

**Bài G – migration certificate.** IdP dùng public SP cert v1, new SP có private key v2. Đề xuất overlap/approval và test inbound/outbound sign/encryption để tránh gián đoạn.

**Bài H – SLO.** Legacy IdP gửi POST `/saml/SingleLogout`, new SP chỉ nghe `/logout/saml2/slo`. Thiết kế hai phương án sửa và test RP+IdP initiated; giải thích tại sao đổi URL không tự giải quyết binding mismatch.

**Bài I – multi-tenant.** App cũ dùng `?idp=partner-a` và new app dùng `registrationId=partner-a`. Kiểm cùng NameID ở hai IdPs không map chéo user/tenant.

**Bài J – reverse proxy.** IdP POST Response `https://portal.example.org/saml/SSO`, backend tự expected `http://portal-service:8080/saml/SSO`. Nêu cách fix trusted Forwarded headers/canonical ACS; không bỏ `Recipient/Destination`.

**Bài K – artifact binding.** IdP đối tác chỉ dùng Artifact Binding, migration docs new library không hỗ trợ equivalent trực tiếp. Đưa ra blocker và phương án xử lý thay vì ép IdP gửi binding khác mà không thông báo.

**Bài L – release/rollback.** Viết playbook có IdP registration export, old/new metadata, approval, canary, login/slo tests, keys, proxy, sessions và rollback. Nhấn mạnh rollback JAR thôi chưa đủ nếu IdP đã đổi trust.

**Tiêu chí đạt:** Có thể chứng minh **old SP + new SP + IdP** thống nhất trên cùng một hợp đồng federation được phê duyệt, bảo toàn chữ ký/recipient/audience/correlation và chỉ thay đúng endpoints có kế hoạch, có Java 17 comparator, E2E tests và rollback thực tế.

## 21. Tài liệu chính thức và nguồn học tiếp

- Spring Security 6.5 – **SAML 2.0 Extension Migration**, differences in approaches and unported features: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/saml-extension-migration.html
- Spring Security 6.5 – **SAML 2.0 Login Overview**, default URI patterns, entityId/ACS placeholders, migration of legacy URLs: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security 6.5 – **SAML 2.0 Metadata**, publication/customization: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html
- Spring Security 6.5 – **Single Logout**, customizing request/response endpoints: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – **OpenSAML Support**, versioned components/selection: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security 6.5 – **Migration to Spring Security 7, SAML 2.0**, validation and API behavior: https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html
- Spring Security SAML Extension 1.x – **Reference Documentation**, legacy `/saml/SSO`, `/saml/SingleLogout`, entityBaseURL and filters: https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/
- Spring Security – **RelyingPartyRegistration API**, issuer/entityId/ACS pair: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- OASIS SAML 2.0 Metadata – EntityDescriptor, SPSSODescriptor, ACS and SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core – Issuer, Audience, Recipient, InResponseTo and Conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Bindings – HTTP-POST/Redirect/Artifact: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
