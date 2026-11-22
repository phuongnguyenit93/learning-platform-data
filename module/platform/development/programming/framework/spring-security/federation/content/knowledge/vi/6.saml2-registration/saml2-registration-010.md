# Đăng ký thông tin Service Provider tại IdP và đối chiếu cấu hình SAML 2.0 hai phía

> **Bối cảnh:** Spring Security – federation. **Menu cha:** Đăng ký SAML2. Bài học hướng dẫn đăng ký ứng dụng Spring Security làm **Service Provider (SP)** tại **Identity Provider (IdP)**, trao đổi metadata, so khớp từng trường, kiểm chứng luồng đăng nhập và vận hành thay đổi an toàn.

## 1. Vì sao phải đăng ký cả hai phía?

Trong SAML 2.0 Web Browser SSO, ứng dụng **SP/Relying Party** không tự xác thực mật khẩu người dùng; SP tin **IdP/Asserting Party** theo một quan hệ federation được cấu hình trước. IdP xác thực người dùng (có thể yêu cầu MFA), phát hành `SAMLResponse` chứa assertion đã ký và trình duyệt POST kết quả về endpoint **Assertion Consumer Service (ACS)** của SP. SP phải xác minh chữ ký, issuer, audience, thời hạn và các điều kiện trước khi tạo phiên.

Cài `spring-security-saml2-service-provider` mới chỉ cung cấp **khả năng thực hiện giao thức** trong ứng dụng; muốn đăng nhập thành công vẫn phải:

1. IdP **biết và cho phép** một SP có `entityID` và ACS URL cụ thể.
2. SP **biết và tin cậy** issuer, SSO endpoint, signing certificate/metadata của IdP.
3. Hai bên thống nhất binding, chính sách ký/mã hóa, NameID, thuộc tính và quyền.
4. Người dùng được IdP gán quyền dùng application và ứng dụng SP kiểm quyền của người đó.

**Định nghĩa quan trọng:**

| Thuật ngữ | Ý nghĩa | Ai quản lý? |
|---|---|---|
| SP Entity ID | Định danh logic của ứng dụng; xuất hiện ở `AuthnRequest/Issuer` và được IdP dùng làm Audience/Identifier | SP và IdP phải thống nhất |
| ACS URL | URL công khai của SP nhận `SAMLResponse` qua HTTP POST | SP công bố; IdP lưu làm Reply URL |
| IdP Entity ID | Định danh issuer của IdP, không nhất thiết là URL truy cập trực tiếp | IdP công bố; SP tin cậy |
| IdP SSO URL | Endpoint mà browser được chuyển tới cùng `AuthnRequest` | IdP công bố; SP sử dụng |
| `registrationId` | Khóa nội bộ Spring Security chọn `RelyingPartyRegistration` | Ứng dụng SP |
| SP metadata | XML mô tả SP: Entity ID, ACS, binding và public cert khi cần | SP xuất, IdP nhập |
| IdP metadata | XML mô tả IdP: issuer, SSO endpoint, signing cert, SLO nếu có | IdP xuất, SP nhập |
| SP signing credential | SP private key ký AuthnRequest và public certificate cho IdP kiểm chữ ký khi bắt buộc | SP giữ private; IdP nhận public |
| IdP verification credential | Public certificate của IdP để SP kiểm chữ ký Response/Assertion | IdP giữ private; SP nhận public |
| SP decryption credential | SP private key dùng giải mã EncryptedAssertion; IdP nhận SP public cert để mã hóa | SP giữ private; IdP nhận public |

`entityID` có thể là URI hoặc URN, **không bắt buộc là đường dẫn HTTP mở được**. `registrationId` không phải entityID. Các giá trị có ý nghĩa khác nhau dù cùng chứa tên đối tác.

## 2. Một ví dụ cấu hình xuyên suốt

Ví dụ dành cho ứng dụng Portal chạy trên Spring Security Servlet:

| Dữ liệu | Giá trị minh họa |
|---|---|
| Tên registration Spring | `corporate` |
| SP Entity ID | `https://portal.example.org/saml2/service-provider-metadata/corporate` |
| SP ACS URL | `https://portal.example.org/login/saml2/sso/corporate` |
| SP metadata URL | `https://portal.example.org/saml2/metadata/corporate` |
| URL khởi tạo login | `https://portal.example.org/saml2/authenticate/corporate` |
| IdP Entity ID | `https://login.example.org/saml/company` |
| IdP SingleSignOnService URL | `https://login.example.org/saml/company/sso` |
| IdP metadata URL | `https://login.example.org/saml/company/metadata` |
| ACS Binding | HTTP-POST |
| AuthnRequest Binding | Thường HTTP-Redirect, theo metadata/chính sách IdP |

Các tên miền `example.org` ở đây là minh họa. Endpoint của một IdP thực (Microsoft Entra ID, AD FS, Okta, Keycloak, Shibboleth...) có thể có cấu trúc hoàn toàn khác: **không suy đoán IdP SSO URL từ tên miền**. Phải lấy đúng giá trị do IdP phát hành.

Với mặc định Spring Security được tài liệu mô tả, **SP Entity ID** thường là `{baseUrl}/saml2/service-provider-metadata/{registrationId}`; **ACS URL** là `{baseUrl}/login/saml2/sso/{registrationId}`. Tùy version và custom config, những đường dẫn này có thể được thay đổi. URL `/saml2/metadata/corporate` là nơi **đọc tài liệu metadata**, không phải ACS và cũng không phải entityID mặc định.

## 3. Luồng thiết lập tin cậy trước khi đăng nhập

~~~text
SP Team / Spring Security                   IdP Admin
       |                                       |
       | 1. Chốt SP entityID, ACS, binding     |
       | 2. Sinh SP metadata / public cert     |
       +------------- SP metadata ----------->|
       |                                       | 3. Tạo SAML app / relying party
       |                                       | 4. Lưu SP entityID, ACS, policy
       |<------------ IdP metadata -----------+
       | 5. Import/đọc IdP issuer, SSO URL,    |
       |    signing certificate tin cậy        |
       |                                       |
       +<--------- Đối chiếu hai chiều ------->+
       |         6. Positive/negative test     |
~~~

Cần làm **hai công việc đối xứng**:

- **Đăng ký SP tại IdP:** IdP lưu chính xác SP entityID và ACS đã khai báo; chốt response signature, request signature, encryption, NameID, user assignment.
- **Đăng ký IdP trong Spring:** SP lưu chính xác IdP entityID, SSO URL/binding, public verification keys từ nguồn đáng tin; xác định `registrationId` cùng SP entityID, ACS và các private keys nếu cần.

Chỉ có IdP metadata URL **không có nghĩa** IdP đã tạo application/trust cho SP. Ngược lại, chỉ tạo SAML app tại IdP **không đủ** cho SP xác minh SAMLResponse.

### SAML login sau khi hai phía đã được đăng ký

~~~text
Browser                   SP                             IdP
   | GET /private          |                              |
   +---------------------->|                              |
   |<---- Redirect /saml2/authenticate/corporate          |
   +------------------- AuthnRequest -------------------->|
   |                                      Login / MFA      |
   |<------------------- HTML form SAMLResponse ----------+
   +-- POST /login/saml2/sso/corporate ------------------> SP
                           | Verify signature + issuer,
                           | audience, recipient, time,
                           | InResponseTo, replay, roles
   |<----------------------+ Create session / grant access
~~~

Browser chỉ chuyển thông điệp, không được phép cung cấp bất kỳ danh tính nào chỉ bằng việc sửa form hay payload.

## 4. Những trường SP phải đưa cho IdP

| Trường | Tên có thể gặp trên IdP Console | Quy tắc đối chiếu |
|---|---|---|
| **SP Entity ID** | Identifier, Audience URI, SP Entity ID, Relying Party Identifier | Phải đúng `RelyingPartyRegistration.entityId`, từng ký tự |
| **ACS URL** | Reply URL, Recipient URL, Consumer URL, SAML ACS | Phải đúng `assertionConsumerServiceLocation` công khai |
| **ACS Binding** | HTTP-POST / Response Binding | Thường HTTP-POST, phải khớp khả năng SP và IdP |
| **SP metadata XML/URL** | Upload Metadata, Import SP Metadata | Chứa EntityDescriptor + SPSSODescriptor + ACS + cert khi dùng |
| **SP signing certificate** | Request Signature Certificate | Public cert khớp private key SP ký AuthnRequest khi IdP bắt buộc |
| **SP encryption certificate** | Assertion Encryption Certificate | Public cert khớp private key SP sẽ giải mã Assertion |
| **SP SLO URL** | Single Logout URL | Có nếu IdP và SP triển khai SAML Single Logout |
| **NameID Format** | Name Identifier Format | Format ID dùng ánh xạ tài khoản: persistent, emailAddress, unspecified... |
| **Attribute contract** | Claims, Attribute statements | Tên thuộc tính, dạng giá trị, multi-value, nhóm/quyền đã thống nhất |
| **Môi trường** | Application/Tenant | Phải đúng dev/staging/prod; không dùng nhầm metadata hoặc cert |

Lưu ý **SP entityID** và **ACS URL** không thay thế cho nhau. Entity ID là định danh logic; ACS là địa chỉ HTTP thực để nhận POST. Sai scheme, hostname, path, dấu gạch chéo cuối hoặc context path đều có thể dẫn tới sai audience/destination/recipient.

### SP metadata XML mẫu

Mẫu giản lược chỉ minh họa các trường chính, không phải metadata deploy thực tế:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://portal.example.org/saml2/service-provider-metadata/corporate">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      AuthnRequestsSigned="false"
      WantAssertionsSigned="false">
    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified
    </md:NameIDFormat>
    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/login/saml2/sso/corporate"
        index="0"
        isDefault="true"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

Trong metadata được sinh từ cấu hình có signing/encryption, có thể thấy `md:KeyDescriptor use="signing"`, `md:KeyDescriptor use="encryption"` chứa `ds:KeyInfo` với public certificate; có thể có nhiều ACS, SLO service và NameID format. Chỉ nhập metadata từ **bản ứng dụng đúng môi trường**; không lấy một file sample như trên để thay metadata thật.

**Quan trọng:** `WantAssertionsSigned="false"` trong ví dụ không có nghĩa SP sẽ tin assertion không ký. Việc kiểm signature vẫn do SAML profile, policy và security provider thực thi. Khi triển khai, thống nhất phải ký Response, Assertion hay cả hai và xác minh đúng bên phát hành.

## 5. Những trường IdP phải đưa cho Spring Security

| Trường IdP | Vùng cấu hình/công dụng trong Spring |
|---|---|
| **IdP Entity ID/Issuer** | `assertingparty.entity-id`; đối chiếu Issuer trong response/assertion |
| **IdP SSO URL + Binding** | `assertingparty.singlesignon.url` và binding, hoặc lấy từ metadata |
| **IdP signing certificate(s)** | `assertingparty.verification.credentials` / metadata đáng tin; kiểm Response/Assertion |
| **IdP metadata URL/XML** | `assertingparty.metadata-uri`; có thể thay khai báo thủ công |
| **Yêu cầu ký AuthnRequest** | `WantAuthnRequestsSigned` / policy; quyết định SP phải ký và cung cấp cert |
| **Chính sách ký Response/Assertion** | Định dạng và chữ ký IdP sẽ phát |
| **Chính sách mã hóa Assertion** | Thuật toán, SP encryption cert, SP private key giải mã |
| **NameID format + attributes** | Mapping principal, groups, email, department, tenant |
| **Single Logout service** | Nếu bật SLO: endpoint/binding và signing requirement |
| **Session/MFA/điều kiện** | Những chính sách IdP thực hiện; SP vẫn phân quyền riêng |

IdP metadata thường chứa `md:EntityDescriptor.entityID` và `md:IDPSSODescriptor` với `SingleSignOnService` cùng `KeyDescriptor`. Bản mẫu lược giản:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://login.example.org/saml/company">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="false">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.org/saml/company/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Mẫu này **không có certificate nên không đủ** để xác thực response trong triển khai thật. Public IdP signing cert phải được cung cấp từ nguồn đáng tin, qua metadata thực và/hoặc trust đã xác nhận với quản trị IdP.

### Metadata và trust không phải một khái niệm

Một XML có chữ ký số hoặc chứa X.509 certificate **chưa mặc định đáng tin**: SP phải xác định được nguồn metadata, trust anchor, IdP issuer và chính sách ký metadata. Tài liệu Spring Security cung cấp các cách nạp metadata, bao gồm repository có hỗ trợ verification và refresh; không giả định mọi phương thức nạp URL đều tự kiểm chữ ký metadata. Nếu lưu tĩnh, cần kế hoạch cập nhật cert; nếu dùng metadata URL động, cần bảo vệ HTTPS, khả năng truy cập, timeout/cache và nguồn tin cậy.

## 6. Bảng đối chiếu bắt buộc trước khi nghiệm thu

| Ý nghĩa giao thức | Giá trị SP/Spring | Giá trị IdP | Kết quả đúng |
|---|---|---|---|
| Định danh SP | `entityId` | Identifier/Audience/Replying Party ID | **Trùng tuyệt đối** |
| ACS POST target | `assertionConsumerServiceLocation` | ACS/Reply URL | **Trùng URL ngoài** |
| Response Binding | HTTP-POST endpoint SP | IdP response binding | Tương thích |
| IdP issuer | `assertingparty.entity-id` | `EntityDescriptor.entityID` IdP | **Trùng tuyệt đối** |
| SP gửi yêu cầu tới | SingleSignOnService URL | IdP SSO endpoint | Đúng URL + binding |
| Chữ ký Response/Assertion | IdP verification credentials | IdP signing cert | Khóa/cert đúng issuer |
| Ký AuthnRequest nếu cần | SP private signing key | SP public signing cert tại IdP | Ký và verify thành công |
| Mã hóa Assertion nếu cần | SP private decryption key | SP public encryption cert tại IdP | Encrypt/decrypt đúng cặp |
| NameID | Principal mapping | IdP NameID/Format/Source | Thống nhất định danh |
| Nhóm/quyền | Attribute mapping → authority | SAML group/role claims | Đúng tên và ngữ nghĩa |
| Logout | SP SLO endpoint + key | IdP SLO service/binding | Cả hai hỗ trợ |
| Môi trường | SP domain, registration, cert | IdP tenant/application/cert | Dev và prod tách biệt |

**Cách kiểm thực tế:** đặt cạnh nhau **SP metadata lấy từ bản deployed**, **cấu hình IdP đã lưu** và **IdP metadata SP đang đọc**. Các bản nháp YAML/Word không chứng minh cấu hình runtime đã đúng. Nếu một bên thay đổi, xác nhận cache/rollout đã nhận giá trị mới rồi mới test lại.

### Bốn tên hay bị nhầm

- `corporate` là `registrationId` nội bộ của Spring.
- `https://portal.example.org/saml2/service-provider-metadata/corporate` là **SP entityID** và thường là Audience URI ở IdP.
- `https://login.example.org/saml/company` là **IdP entityID**, phải khớp Issuer nhận về.
- `https://portal.example.org/login/saml2/sso/corporate` là **ACS**, nơi IdP POST `SAMLResponse`. Không phải metadata endpoint.

## 7. Quy trình đăng ký SP tại IdP từng bước

### Bước 1: Chuẩn bị một hồ sơ cho từng môi trường

Chốt tên ứng dụng, môi trường, IdP tenant, chủ sở hữu SP và IdP, phiên bản Java/Spring Boot/Spring Security, external hostname, URL và proxy path, yêu cầu MFA, SLO và chính sách vòng đời khóa. Ưu tiên các application IdP riêng cho dev/staging/production; không dùng URL/cert production trong thử nghiệm.

### Bước 2: Cấu hình ứng dụng SP trước khi xuất metadata

Tạo registration tên `corporate` và chốt SP entityID, ACS HTTPS URL, các signing/decryption credentials nếu cần. Nếu dùng reverse proxy, phải biết URL trình duyệt thực sự truy cập là gì. Spring Boot có thể tạo metadata dựa trên request `baseUrl` nên proxy sai có thể làm xuất `http://localhost:8080` thay vì `https://portal.example.org`.

### Bước 3: Xuất metadata SP

Kích hoạt `saml2Metadata()` trên ứng dụng Servlet. Theo tài liệu Spring Security, endpoint có thể là:

- `/saml2/metadata`: metadata cho tập registration nếu repository hỗ trợ.
- `/saml2/metadata/{registrationId}`: metadata một registration.
- `/saml2/service-provider-metadata/{registrationId}`: endpoint metadata thay thế.

Với `corporate`, dùng `https://portal.example.org/saml2/metadata/corporate` và kiểm XML có đúng Entity ID, ACS URL, binding, public cert (nếu dùng), SLO và NameIDFormat. **Địa chỉ xuất metadata không nhất thiết trùng Entity ID**.

### Bước 4: Import vào IdP hoặc nhập tay

Trong IdP console, tạo application loại **SAML 2.0**. Nếu có hỗ trợ upload metadata, import SP metadata đúng môi trường. Nếu nhập thủ công:

~~~text
SAML application: Portal Corporate
SP Entity ID / Audience:
  https://portal.example.org/saml2/service-provider-metadata/corporate
ACS / Reply URL:
  https://portal.example.org/login/saml2/sso/corporate
ACS Binding:
  urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST
SP Request Signing:
  Theo yêu cầu đã thống nhất, có SP public signing cert nếu bắt ký
Assertion Encryption:
  Bật khi cần và IdP đã nhận SP public encryption cert
NameID and Attributes:
  Chọn format + nguồn định danh/nhóm đã thống nhất
~~~

Tên trường khác nhau theo sản phẩm (Entra ID, AD FS, Okta, Keycloak, Shibboleth...) nhưng phải khớp **ý nghĩa**. Sau import/Save, mở lại cấu hình để xác nhận IdP đã lưu đúng URL/cert; một số UI có thể tự biến đổi hoặc có nhiều "default URL".

### Bước 5: Chọn bảo vệ thông điệp

- Chữ ký **IdP Response/Assertion**: IdP ký bằng private key riêng; SP tin public cert IdP phù hợp.
- Chữ ký **AuthnRequest của SP**: SP ký bằng private key; IdP xác minh bằng public signing cert của SP nếu chính sách yêu cầu.
- **EncryptedAssertion**: IdP dùng public encryption cert của SP; SP giữ private key tương ứng để giải mã.
- **SAML Single Logout**: cấu hình riêng nếu cả hai hỗ trợ; có endpoint và signing policy riêng.

Không dùng một public certificate từ payload chưa tin cậy làm verification trust anchor. Không gửi SP private key cho IdP. Không giảm chính sách ký hoặc bỏ kiểm Audience/Recipient chỉ để SSO chạy.

### Bước 6: Cấp quyền dùng ứng dụng tại IdP

Gán user/group được phép đăng nhập, cấu hình MFA/conditional access và NameID/attribute statement. Đăng ký đúng giao thức nhưng user chưa được assign vẫn không login. Quyền tại SP vẫn do ứng dụng quyết định; IdP cho phép đăng nhập **không đồng nghĩa** người dùng có `ROLE_ADMIN`.

### Bước 7: Nhập IdP metadata vào Spring, đối chiếu và chạy test

Lấy IdP entityID, SSO URL/binding, signing cert và optional SLO từ metadata IdP đáng tin. Cấu hình Spring tương ứng, kiểm bảng mục 6 và chạy test SP-initiated trước. Sau đó kiểm negative test, permission mapping, proxy/cookie, các user/nhóm khác nhau và IdP-initiated nếu đã chủ động hỗ trợ.

## 8. Ví dụ Spring Boot / Spring Security SAML2 SP

### 8.1. Dependency Maven trong dự án Servlet

Các dependency dưới đây thuộc phần `<dependencies>` của một dự án Spring Boot có BOM/dependency management; **không phải file pom.xml hoàn chỉnh**:

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

Module SAML sử dụng OpenSAML. Theo nhánh Spring Security/Boot/OpenSAML, có thể phải thêm repository Shibboleth như tài liệu chính thức hướng dẫn; không trộn phiên bản Spring Security và OpenSAML tùy ý.

### 8.2. Cấu hình Spring Boot bằng IdP metadata

Tệp `src/main/resources/application.yml` (domain ví dụ; cần metadata IdP thực và ứng dụng đã đăng ký):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://portal.example.org/login/saml2/sso/corporate"
            assertingparty:
              metadata-uri: "https://login.example.org/saml/company/metadata"
~~~

- `registration.corporate` là khóa local.
- `entity-id` là **SP entity ID**, phải trùng Identifier/Audience URI ở IdP.
- `acs.location` phải trùng Reply URL/ACS ở IdP và là URL browser thực truy cập.
- `assertingparty.metadata-uri` là **IdP metadata**, không phải metadata SP.

Đây là cú pháp minh họa theo cấu trúc Spring Boot SAML relying party. Khi triển khai phải đối chiếu property names và API của **phiên bản Spring Boot thực chạy**. Có thể bỏ explicit SP entityID/ACS để dùng mặc định khi public baseURL chính xác; sau đó xuất metadata và kiểm kết quả.

Nếu IdP không có metadata URL, có thể cấu hình IdP issuer, URL và verification cert thủ công:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              entity-id: "https://login.example.org/saml/company"
              singlesignon:
                url: "https://login.example.org/saml/company/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-signing.crt"
~~~

Đây là **phương án thay thế cho nhánh IdP metadata URI**, không phải hai đoạn để dán trùng `registration.corporate`. `sign-request: false` chỉ phù hợp khi IdP **cho phép AuthnRequest không ký**. Nếu IdP bắt ký, phải cấu hình SP signing credential và kiểm rằng IdP đã tin public cert SP. Khi dùng cấu hình thủ công cần bổ sung SP entityID/ACS và các trường binding nếu không dùng mặc định.

### 8.3. Java 17+ cấu hình login và xuất SP metadata

Tệp `src/main/java/com/example/portal/SamlPortalApplication.java`:

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlPortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlPortalApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SP ready";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Đây là mã Java 17+ **dùng trong project Spring Boot Servlet**, không biên dịch bằng `javac` độc lập vì cần classpath Spring và IdP/registration hoạt động. Trong dự án Maven đã chuẩn bị Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Khi ứng dụng khởi động thành công, `GET /` trả văn bản `SP ready`. Truy cập `GET /me` yêu cầu xác thực SAML; sau thành công, kết quả là tên principal thực tế do IdP/mapping quyết định, không có stdout cố định.

Để lấy metadata trên hostname đã deploy:

~~~bash
curl -fsS "https://portal.example.org/saml2/metadata/corporate" -o sp-metadata.xml
~~~

Sau đó kiểm trong XML: `EntityDescriptor.entityID`, `SPSSODescriptor.AssertionConsumerService.Location`, binding, public cert và SLO nếu dùng. Lệnh chỉ thành công khi hostname, server và registration thật sự sẵn sàng; không có output cố định cần giả lập.

### 8.4. Khi yêu cầu ký AuthnRequest hoặc mã hóa assertion

Các nhánh cấu hình liên quan đến **SP signing** và **SP decryption** (hợp nhất với cấu hình ở trên khi cần):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/secrets/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/sp-decryption.key"
                  certificate-location: "file:/run/secrets/sp-decryption.crt"
            assertingparty:
              metadata-uri: "https://login.example.org/saml/company/metadata"
~~~

Cặp SP signing public/private và cặp SP encryption public/private có thể tách biệt; mỗi cặp phải đúng mục đích. Trong thực tế cấu hình có thể có nhiều credential khi rotation. **Không** đưa private key lên IdP console hoặc source control. Với signing policy, kiểm IdP metadata `WantAuthnRequestsSigned`, binding và thuật toán. Nếu IdP mã hóa, SP phải có private decryption key **khớp SP encryption cert mà IdP dùng**.

### 8.5. URL mặc định và URL tùy biến

Theo tài liệu Spring Security Servlet hiện đại:

| Chức năng | Mặc định thường gặp |
|---|---|
| Bắt đầu SP-initiated login | `/saml2/authenticate/{registrationId}` |
| Nhận SAMLResponse (ACS) | `/login/saml2/sso/{registrationId}`; có thể hỗ trợ ACS path khác theo cấu hình |
| Phát metadata SP | `/saml2/metadata/{registrationId}` sau khi bật `saml2Metadata` |
| Entity ID SP | `{baseUrl}/saml2/service-provider-metadata/{registrationId}` |

Có thể tùy biến `loginProcessingUrl` hoặc builder `assertionConsumerServiceLocation`, nhưng **thay endpoint xử lý ở filter phải đồng bộ metadata và IdP**. Không đổi path ở IdP trước rồi giả định Spring tự đổi.

## 9. Reverse proxy, URL tuyệt đối và session callback

Một cấu hình chạy được ở localhost có thể fail hoàn toàn ở production vì địa chỉ bên ngoài khác:

~~~text
Spring service nội bộ:
  http://portal-service:8080/login/saml2/sso/corporate

Public URL browser/IdP:
  https://portal.example.org/login/saml2/sso/corporate

Cấu hình đúng:
  Metadata SP + ACS IdP + Recipient/Destination cùng dùng public HTTPS URL.
~~~

Kiểm các yếu tố:

- **Scheme HTTPS:** TLS kết thúc tại proxy nhưng metadata phải thể hiện URL ngoài chính xác.
- **Host/port:** FQDN public khác tên container và cổng nội bộ.
- **Context path:** ingress có thêm/bỏ `/portal` thì ACS phải phản ánh đúng.
- **Trusted forwarded headers:** app chỉ tin `Forwarded`/`X-Forwarded-*` do proxy đáng tin đặt; proxy xóa giá trị giả từ client trước khi chuyển request.
- **Cookie/session:** IdP thường POST cross-site; kiểm `Secure`, `SameSite`, domain và storage của AuthnRequest/session trong cluster.
- **Nhiều instance:** nếu callback đến một instance khác, session/request repository phải được chia sẻ hoặc load balancing hoạt động theo thiết kế.

**Không chữa bằng cách tắt validation Destination, Recipient, Audience hoặc cho phép mọi redirect URL.** Sửa SP base URL/ACS, IdP Reply URL và proxy routing sao cho khớp.

## 10. Chữ ký, encryption và kiểm điều kiện SAML

Khi IdP gửi `SAMLResponse` tới ACS, SP phải xác minh đủ nhiều lớp:

1. **IdP trusted issuer:** Response/Assertion thực sự đến từ đúng IdP đã đăng ký.
2. **XML signature:** chữ ký Response hoặc Assertion theo profile, certificate và policy hợp lệ; không tin cert do payload chưa xác thực tự cung cấp.
3. **Audience:** Assertion dành cho **SP Entity ID** này.
4. **Destination / Recipient:** callback đúng **ACS** đã đăng ký.
5. **InResponseTo:** nếu SP-initiated, liên hệ đúng AuthnRequest pending và ngữ cảnh phiên.
6. **Thời hạn:** `NotBefore`, `NotOnOrAfter`, SubjectConfirmation và clock skew được giới hạn.
7. **Replay:** không chấp nhận reuse response/assertion trái policy.
8. **Account and authorities:** mapping principal/claims sau xác thực và áp dụng authorization của ứng dụng.

**Chữ ký ≠ mã hóa.** Response hoặc Assertion có thể được ký để bảo vệ nguồn/tính toàn vẹn; `EncryptedAssertion` nhằm bảo mật nội dung cho SP giữ private key. Giải mã thành công **không chứng minh** assertion do IdP tin cậy phát hành. Nếu assertion đã ký rồi được mã hóa, provider cần giải mã và kiểm chữ ký bên trong ở thứ tự phù hợp.

### Vòng đời certificate

- IdP rotation signing key: SP phải nhận trusted cert mới **trước khi** IdP bắt đầu ký bằng khóa mới; có thể overlap cert cũ/mới.
- SP rotation signing key: cập nhật public cert ở IdP trước khi SP ký request bằng private key mới.
- SP rotation encryption key: IdP mã hóa bằng public cert mà SP còn private key tương ứng; nếu không đồng bộ, decryption fail.
- Ghi fingerprint SHA-256, thời gian hiệu lực, chủ sở hữu và đường cập nhật metadata/cert.
- Không log private key, SAMLResponse thô chứa PII hoặc cookie; không bỏ signature check khi có lỗi.

## 11. NameID, attribute mapping và cấp quyền

Ở bước đăng ký IdP, phải xác nhận **NameID format** và cách lấy định danh người dùng: persistent ID, emailAddress, unspecified, UPN hoặc custom subject. Không tự coi email là bất biến: email có thể đổi hoặc được tái cấp; nên chọn khóa mapping gắn issuer + subject ổn định theo hợp đồng.

Các SAML attributes như `email`, `department`, `groups` hoặc `roles` không tự biến thành quyền trong Spring Security. Cần:

- Xác minh assertion/issuer/conditions trước khi đọc attribute.
- Định nghĩa tên attribute (URI/short name) và cách map multi-value.
- Map group từ **đúng tenant/issuer** sang application roles có giới hạn.
- Tách IdP entitlement "được đăng nhập ứng dụng" với quyền SP "được xem/sửa tài nguyên".
- Xử lý người dùng bị vô hiệu hóa, đổi group và vòng đời tài khoản.

Ví dụ một **fragment attribute** (không phải assertion có chữ ký hợp lệ):

~~~xml
<saml:Attribute
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Name="groups">
  <saml:AttributeValue>portal-viewers</saml:AttributeValue>
</saml:Attribute>
~~~

Chỉ sau khi SAML authentication hoàn tất, ứng dụng mới cân nhắc map `portal-viewers` sang authority được chính sách chấp nhận. Không gán quyền admin chỉ vì có một chuỗi role nằm trong form chưa xác thực.

## 12. SP-initiated, IdP-initiated và SLO

**SP-initiated**: SP gửi AuthnRequest và lưu state; IdP trả response với `InResponseTo`. Đây thường là mặc định phù hợp ứng dụng có route bảo vệ. Kiểm `RelayState` tránh open redirect và session/login CSRF.

**IdP-initiated**: người dùng chọn app từ portal IdP và nhận response có thể không gắn với AuthnRequest trong phiên SP. Chỉ hỗ trợ nếu IdP/SP có chính sách rõ ràng; rủi ro login CSRF/replay và mapping session cần được đánh giá. Không tự bỏ `InResponseTo` validation cho mọi flow để "sửa" lỗi SP-initiated.

**Single Logout (SLO)**: chức năng riêng, cần IdP hỗ trợ `SingleLogoutService`, SP cấu hình `saml2Logout`, các endpoint/binding và ký LogoutRequest/LogoutResponse theo policy. Đăng xuất local một app không mặc nhiên xóa phiên IdP hoặc mọi ứng dụng khác.

## 13. Java 17 độc lập: kiểm so khớp các giá trị quan trọng

Chương trình sau chỉ mô phỏng **so chuỗi cấu hình**; không parse XML metadata hay xác minh SAML chữ ký. Đây là mã Java 17 **độc lập, biên dịch/chạy được**.

Tệp `CompareSamlRegistration.java`:

~~~java
import java.util.Objects;

public class CompareSamlRegistration {
    static void check(String label, String spValue, String idpValue) {
        String result = Objects.equals(spValue, idpValue)
                ? "MATCH" : "MISMATCH";
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        check(
            "SP Entity ID",
            "https://portal.example.org/saml2/service-provider-metadata/corporate",
            "https://portal.example.org/saml2/service-provider-metadata/corporate"
        );
        check(
            "ACS URL",
            "https://portal.example.org/login/saml2/sso/corporate",
            "http://portal.example.org/login/saml2/sso/corporate"
        );
        check(
            "IdP Entity ID",
            "https://login.example.org/saml/company",
            "https://login.example.org/saml/company"
        );
    }
}
~~~

Lệnh:

~~~bash
javac CompareSamlRegistration.java
java CompareSamlRegistration
~~~

Stdout chính xác:

~~~text
SP Entity ID: MATCH
ACS URL: MISMATCH
IdP Entity ID: MATCH
~~~

ACS sai do IdP đang lưu `http://` còn SP phát `https://`. Cần sửa đúng bên rồi chạy lại, **không chuyển sang so gần đúng** trong kiểm SAML. Trong sản xuất, ưu tiên so metadata runtime và console IdP; chương trình này là bài tập kiểm giá trị chính xác, không phải một SAML validator.

## 14. Kế hoạch kiểm thử sau khi đăng ký

### 14.1. Kiểm thử thành công

1. Mở URL metadata SP thực; xác nhận Entity ID, ACS, public signing/encryption cert (nếu dùng).
2. Mở `/saml2/authenticate/corporate`; kiểm redirect tới đúng IdP SSO endpoint và AuthnRequest có đúng issuer/ACS.
3. Đăng nhập bằng user được assign application ở IdP, thực hiện MFA nếu cần.
4. Xác nhận IdP POST SAMLResponse tới ACS đã lưu với `Destination`/`Recipient` chính xác.
5. SP kiểm chữ ký, issuer, audience, timing, request state thành công rồi tạo Authentication.
6. Kiểm principal NameID/attributes/roles và tài nguyên được phép.
7. Kiểm user có quyền thấp hơn, user chưa được gán IdP app và policy MFA.
8. Kiểm logout local; kiểm SLO riêng nếu cả hai hỗ trợ.

### 14.2. Kiểm thử thất bại có chủ đích

| Tình huống | Kỳ vọng |
|---|---|
| SP entityID khác Audience trong assertion | SP từ chối |
| ACS bị đổi scheme/host/path hoặc Recipient sai | IdP/SP từ chối |
| `Issuer` IdP sai tenant | SP từ chối |
| IdP signing certificate không tin cậy | SP từ chối |
| Thay nội dung assertion sau khi ký | SP từ chối |
| Response/assertion hết hạn hoặc `NotBefore` chưa tới | SP từ chối |
| `InResponseTo` không thuộc pending request | SP từ chối với SP-initiated flow |
| SAMLResponse/Assertion bị phát lại trái policy | SP từ chối |
| IdP bắt ký AuthnRequest nhưng SP không ký | IdP từ chối |
| EncryptedAssertion dùng cert không khớp SP private key | SP không giải mã được |
| User không được IdP assign app | IdP từ chối cấp session hợp lệ |
| User đã login nhưng không có authority | SP từ chối tài nguyên hạn chế |
| Metadata IdP/certificate bị rotate mà SP chưa đồng bộ | Fail an toàn và cảnh báo |

Khi debug, dùng test IdP và browser/SAML tracing trong môi trường được phép. Đọc các trường không nhạy cảm như Issuer, Destination, Audience, InResponseTo, time và fingerprint key; tránh đẩy raw SAMLResponse chứa PII/session ra log công khai.

## 15. Troubleshooting theo lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm/sửa |
|---|---|---|
| Invalid Audience / Entity ID | IdP Identifier khác SP entityID | So metadata SP và app Identifier ở IdP |
| Reply URL / ACS mismatch | IdP chưa lưu đúng public ACS | So scheme/host/port/path/context path |
| Invalid Destination / Recipient | Proxy/ingress làm URL lệch | Cập nhật trusted forwarding hoặc explicit ACS |
| Invalid Issuer | Đang trỏ sai IdP tenant/metadata | So IdP metadata entityID với Spring asserting party |
| Signature validation failed | Cert IdP sai, đổi khóa hoặc chữ ký payload bị thay | Cập nhật trusted signing cert/metadata, không tắt verify |
| Unsigned AuthnRequest rejected | IdP yêu cầu SP signing | Thêm SP signing credential và public cert ở IdP |
| EncryptedAssertion decryption failure | SP key sai hoặc IdP encrypt bằng cert khác | Kiểm cặp encryption cert/private key và algorithm |
| 404 tại ACS | URL, POST binding, filter chain hoặc proxy rewrite sai | Kiểm endpoint Servlet và ingress routing |
| Invalid InResponseTo / mất session | Cookie, SameSite, session store hoặc multi-node | Kiểm AuthnRequest repository, cookie/session |
| NotBefore/NotOnOrAfter failed | Giờ/NTP lệch, response quá hạn | Đồng bộ clocks, giới hạn clock skew |
| Login thành công nhưng 403 | IdP attribute/authority mapping không khớp | Kiểm group/role policy của SP |
| User không thấy app tại IdP portal | Chưa assign user/group hoặc policy chặn | Kiểm assignment/MFA |
| Metadata endpoint 404 | Chưa bật `saml2Metadata` hoặc sai registration | Bật metadata DSL, dùng đúng URL và môi trường |
| SSO loop | Session cookie, ACS handling hoặc reverse proxy lỗi | Xem log authentication/session, cookie settings |
| SLO fail nhưng SSO login pass | Logout flow/cert/endpoint cần config riêng | Kiểm IdP SLO support, ký LogoutRequest/Response |

Thứ tự tìm lỗi tiết kiệm thời gian: **môi trường/tenant → SP entityID + ACS → IdP issuer + SSO URL → keys/cert → browser POST/session → SAML conditions → role mapping**. Không sửa authorization khi lỗi thực nằm ở issuer hoặc ACS.

## 16. Biên bản xác nhận và vận hành production

Một biên bản cấu hình sau nghiệm thu nên lưu:

- Tên SP, IdP application/tenant, environment và chủ sở hữu mỗi phía.
- **SP entityID**, ACS URL/binding lấy từ metadata thực; **IdP issuer**, SSO URL/binding lấy từ metadata IdP.
- Fingerprint SHA-256 và thời hạn cert IdP signing; cert SP signing/encryption khi dùng.
- Chính sách Response/Assertion signature, AuthnRequest signing, Assertion encryption, NameID và attributes.
- Positive/negative integration tests; tình trạng MFA/user assignment, mapping authorities và optional SLO.
- Cách đổi metadata, lập lịch **certificate rotation**, cảnh báo expiry, rollback và đầu mối incident.

Khi đổi **Entity ID** hoặc **ACS URL**, cần đồng bộ cả IdP và SP; thực hiện thay đổi có kế hoạch và kiểm lại request/response. Khi đổi cert, chuẩn bị giai đoạn **overlap** nếu phần mềm/đối tác hỗ trợ, thử trước khi dùng khóa mới, không gỡ khóa cũ khi IdP/SP vẫn còn phụ thuộc. Giữ riêng dev/staging/prod để giảm rủi ro.

Checklist go-live:

1. SP metadata runtime trùng IdP stored Identifier, ACS và binding.
2. SP chỉ tin IdP issuer và verification key đã kiểm tra; assertion expiration/audience/recipient không bị bỏ.
3. HTTPS, DNS, trusted reverse proxy, cookie/session và multiple replicas hoạt động.
4. Signing/encryption cert đúng cặp; private keys nằm trong secret store/quyền file hạn chế.
5. User/group assignment, MFA và quyền SP đã kiểm trong các tình huống hợp lệ và không hợp lệ.
6. Có monitor lỗi SSO, metadata fetch, cert expiry và kế hoạch rollback an toàn.
7. Mọi thay đổi mới có người sở hữu và có thể đối chiếu lại ba nguồn: **metadata SP thực, IdP stored settings, IdP metadata mà SP đọc**.

## 17. Câu hỏi ôn tập

1. **Nhập IdP metadata vào Spring có tự đăng ký SP trong IdP chưa?** Không. IdP vẫn phải lưu SP entityID/ACS và cho user dùng app.
2. **SP entityID có phải là ACS URL?** Không. EntityID là danh tính/audience, ACS là endpoint nhận SAMLResponse.
3. **Có nhất thiết `registrationId` trùng issuer IdP?** Không, đây là khóa nội bộ Spring chọn RelyingPartyRegistration.
4. **Ai giữ private key mã hóa Assertion?** SP giữ private decryption key; IdP nhận SP public encryption cert.
5. **Vì sao SSO fail sau khi thêm reverse proxy?** Metadata/ACS có thể phát internal HTTP URL thay vì public HTTPS URL; session cookies cũng có thể sai.
6. **Đăng nhập SSO thành công có đủ cấp quyền admin?** Không; authority mapping và authorization là công việc riêng của SP.
7. **Tại sao không bỏ signature verification khi sai cert?** Vì như vậy SP có thể chấp nhận assertion giả. Phải sửa trust/cert đúng issuer.
8. **Khi IdP rotation signing certificate?** SP cần nạp trusted public cert mới theo rollout trước khi IdP ký bằng khóa mới.

## 18. Tài liệu tham khảo chính thức

- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML2 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – Authenticating Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Single Logout: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Boot – SAML2 Relying Party: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- OASIS – SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS – SAML 2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf

**Ghi nhớ:** cấu hình SAML đúng khi **SP metadata đang được ứng dụng phát**, **thông tin SP mà IdP lưu**, và **IdP metadata/issuer/key mà Spring Security tin** thống nhất. Đăng nhập chỉ an toàn sau khi chữ ký, audience, callback, request correlation, thời hạn và phân quyền đều được kiểm đúng.
